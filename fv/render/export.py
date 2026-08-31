"""Export helpers: PNG snapshot, STA (status) save/load, Print (P4.1).

* ``snapshot_png`` uses ``vtkWindowToImageFilter`` on the scene's render
  window (3D); when headless it fails cleanly and returns ``False``.
* ``save_status`` / ``load_status`` persist the Control Window object tree
  (each ``PostObject``'s dataclass fields) as a JSON-based ``.sta`` file so
  the same sc:POST setup can be restored after reopening the field file.
* ``print_scene`` sends the rendered view to the system printer via
  ``QPrinter`` (falls back to a PNG export when QtPrintSupport is missing).
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Optional

try:
    import vtk
    from vtk.util import numpy_support  # noqa: F401  (kept for parity)
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False


def snapshot_png(renderer_or_window, filename: str,
                 scale: float = 1.0, dpi: float = 72.0) -> bool:
    """Capture the VTK render window to a PNG file (R25-S1: hires export).

    ``renderer_or_window``: a renderer (during tests) or a
    ``vtkRenderWindow``. Returns True on success, False if VTK is missing or
    the window has nothing to render (headless).

    ``scale`` multiplies the native window resolution (e.g. 2.0 => 2x pixels
    for print / poster export); ``dpi`` is honoured when given a non-default
    value by deriving ``scale = max(scale, dpi / 72.0)``. Both are
    back-compatible - callers that omit them keep the old 1x capture.
    """
    if not _HAS_VTK:
        return False
    import vtk

    win = renderer_or_window
    if hasattr(win, "GetRenderWindow"):
        win = win.GetRenderWindow()
    if win is None:
        return False
    if dpi and dpi > 0 and dpi != 72.0:
        scale = max(float(scale), float(dpi) / 72.0)
    try:
        base, ext = os.path.splitext(filename)
        if ext.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".tif"):
            filename = base + ".png"
        w2i = vtk.vtkWindowToImageFilter()
        w2i.SetInput(win)
        w2i.SetInputBufferTypeToRGB()
        if scale and scale > 1.0:
            # vtkWindowToImageFilter.SetScale takes an integer magnification
            # in this VTK line; round to honour the requested dpi/scale.
            w2i.SetScale(int(round(float(scale))))
        w2i.Update()
        # Honest writers per extension (P0.6): BMP/TIF get their native
        # VTK writers instead of PNG bytes in a mismatched container.
        ext_l = ext.lower()
        if ext_l in (".jpg", ".jpeg"):
            writer = vtk.vtkJPEGWriter()
        elif ext_l == ".bmp":
            writer = vtk.vtkBMPWriter()
        elif ext_l == ".tif":
            writer = vtk.vtkTIFFWriter()
        else:
            writer = vtk.vtkPNGWriter()
        writer.SetFileName(str(filename))
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Write()
        return os.path.exists(filename) and os.path.getsize(filename) > 0
    except Exception:  # pragma: no cover
        return False


# ── STA (status) save / load ───────────────────────────────────────────────

_KIND_CLASSES: dict[str, type] = {}


def _object_class(kind: str):
    """Resolve a kind string to its PostObject subclass.

    All PostObject subclasses register automatically via reflection on the
    class-level ``kind`` default, so newly added object kinds round-trip
    through STA without touching this module (P0.2).
    """
    if not _KIND_CLASSES:
        import dataclasses as _dc

        from ..model import objects as _om
        for cls in vars(_om).values():
            if (isinstance(cls, type) and issubclass(cls, _om.PostObject)
                    and _dc.is_dataclass(cls) and cls is not _om.PostObject):
                k = getattr(cls, "kind", None)
                if isinstance(k, str) and k:
                    _KIND_CLASSES[k] = cls
    return _KIND_CLASSES.get(kind)


def _json_safe(value):
    """Convert dataclass fields (tuples, Paths) to JSON-safe structures."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _json_safe(getattr(value, f.name))
                for f in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return {"__tuple__": True, "data": [_json_safe(v) for v in value]}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _from_json(value):
    if isinstance(value, dict):
        if value.get("__tuple__"):
            return tuple(_from_json(v) for v in value["data"])
        return {k: _from_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_json(v) for v in value]
    return value


def save_status(main_object, filepath: str) -> bool:
    """Persist one MainObject (its children settings) as a JSON ``.sta``.

    Only declared dataclass fields are written, so new fields added later
    load with their defaults.
    """
    if main_object is None:
        return False
    children = getattr(main_object, "children", []) or []
    payload = {
        "format": "flowviewer-sta",
        "version": 1,
        "display_name": getattr(main_object, "display_name", ""),
        "children": [_json_safe(o)
                     if dataclasses.is_dataclass(o)
                     else {"kind": str(getattr(o, "kind", "")),
                           "fields": vars(o)}
                     for o in children],
    }
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return Path(filepath).exists()


def load_status(filepath: str) -> Optional[list]:
    """Read a ``.sta`` file; rebuild the saved child ``PostObject`` list.

    Returns a list of reconstructed dataclass instances, or ``None`` when the
    file is missing / not a status file.
    """
    try:
        with open(filepath, encoding="utf-8") as fh:
            doc = json.load(fh)
    except Exception:
        return None
    if not isinstance(doc, dict) or doc.get("format") != "flowviewer-sta":
        return None
    out: list = []
    for child in doc.get("children", []) or []:
        cls = _object_class(child.get("kind") or "")
        if cls is None:
            continue
        # Dataclass children store their fields directly at top level;
        # plain-object records wrap them under ``fields``.
        if "fields" in child and isinstance(child.get("fields"), dict):
            raw = child["fields"]
        else:
            raw = child
        fields = _from_json(raw or {})
        declared = {f.name for f in dataclasses.fields(cls)}
        kwargs = {k: v for k, v in fields.items() if k in declared}
        try:
            out.append(cls(**kwargs))
        except TypeError:  # pragma: no cover - future-proof
            continue
    return out


# ── Print ──────────────────────────────────────────────────────────────────

def export_surface_stl(ff, filename: str, obj=None) -> bool:
    """Write the boundary surface polydata as STL (P3.2)."""
    if not _HAS_VTK:
        return False
    from ..model.objects import SurfaceObject
    from .surface import build_surface_polydata
    obj = obj or SurfaceObject(index=1)
    pd, _, _ = build_surface_polydata(ff, obj)
    if pd is None or pd.GetNumberOfCells() == 0:
        return False
    writer = vtk.vtkSTLWriter()
    writer.SetFileName(filename)
    writer.SetInputData(pd)
    writer.Write()
    return True


def export_scene_vrml(render_window, filename: str) -> bool:
    """Export the whole scene as VRML (P3.2)."""
    if not _HAS_VTK:
        return False
    try:
        writer = vtk.vtkVRMLExporter()
        writer.SetRenderWindow(render_window)
        writer.SetFileName(filename)
        writer.Write()
        return True
    except Exception:
        return False


def export_scene_gltf(render_window, filename: str) -> bool:
    """Export the whole scene as glTF (P3.2)."""
    if not _HAS_VTK:
        return False
    try:
        writer = vtk.vtkGLTFExporter()
        writer.SetRenderWindow(render_window)
        writer.SetFileName(filename)
        writer.Write()
        return True
    except Exception:
        return False

def export_animation_frames(ff, main, scene, render_window,
                            out_dir: str, frames: int = 30,
                            fps: int = 15, base: str = "frame") -> int:
    """Render automove animation frames to PNGs (G5).

    Advances the scene once per frame (scene.animate) and snapshots each
    one into *out_dir* as base_0000.png ... Returns the number written.
    """
    from pathlib import Path
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0
    written = 0
    for t in range(max(1, int(frames))):
        try:
            scene.animate(t, fps=int(fps))
        except Exception:
            continue
        path = out_dir / f"{base}_{t:04d}.png"
        if snapshot_png(render_window, str(path)):
            written += 1
    return written


def _write_vtk_video(scene, render_window, filename: str,
                     frames: int = 30, fps: int = 15) -> int:
    """Encode scene animation frames to a video via a VTK writer (R3.2).

    Uses ``vtkOggTheoraWriter`` for ``.ogv``, or ``vtkAVIWriter`` for
    ``.avi`` when that writer is available on this build.  Advances *scene*
    once per frame and writes it from *render_window*.  Returns the number
    of frames written, or 0 on failure.
    """
    if not _HAS_VTK:
        return 0
    import vtk
    ext = os.path.splitext(filename)[1].lower()
    writer = None
    if ext == ".avi" and hasattr(vtk, "vtkAVIWriter"):
        writer = vtk.vtkAVIWriter()
    elif hasattr(vtk, "vtkOggTheoraWriter"):
        writer = vtk.vtkOggTheoraWriter()
    if writer is None:
        return 0
    try:
        writer.SetFileName(str(filename))
        if hasattr(writer, "SetRate"):
            writer.SetRate(int(fps))
        w2i = vtk.vtkWindowToImageFilter()
        w2i.SetInput(render_window)
        w2i.SetInputBufferTypeToRGB()
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Start()
        written = 0
        for t in range(max(1, int(frames))):
            try:
                if scene is not None:
                    scene.animate(t, fps=int(fps))
            except Exception:
                pass
            render_window.Render()
            w2i.Modified()
            writer.Write()
            written += 1
        writer.End()
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            return written
        return 0
    except Exception:
        return 0


def export_animation_video(ff, main, scene, render_window, filename: str,
                           frames: int = 30, fps: int = 15,
                           base: str = "frame") -> int:
    """Render an animation and encode it to a video file (R3.2).

    Writes the animation via VTK's native writer (Ogg Theora ``.ogv``, or
    AVI when available).  ``ff`` / ``main`` / ``base`` are accepted for API
    parity with :func:`export_animation_frames` but only ``scene`` and
    ``render_window`` are required.  Returns the number of frames written,
    or 0 when VTK / the render window is missing.
    """
    if render_window is None:
        return 0
    return _write_vtk_video(scene, render_window, filename, frames=frames,
                            fps=fps)


def export_surface_obj(ff, filename: str, obj=None) -> bool:
    """Write the boundary surface as Wavefront OBJ (4, FBX-neutral).

    FBX has no native VTK writer; OBJ is the neutral interchange format
    most FBX converters accept.  Since P2-4 the OBJ also carries per-vertex
    normals and a planar UV map (``vn``/``vt`` + ``v/vt/vn`` faces) so the
    mesh can be re-lit and textured in DCC / FBX pipelines.
    """
    if not _HAS_VTK:
        return False
    import vtk

    from ..model.objects import SurfaceObject
    from .surface import build_surface_polydata
    obj = obj or SurfaceObject(index=1)
    pd, _, _ = build_surface_polydata(ff, obj)
    if pd is None or pd.GetNumberOfCells() == 0:
        return False
    try:
        # P2-4: per-vertex normals + planar UV mapping
        norms = vtk.vtkPolyDataNormals()
        norms.SetInputData(pd)
        norms.ComputePointNormalsOn()
        norms.ComputeCellNormalsOff()
        norms.SplittingOff()
        norms.Update()
        npd = norms.GetOutput()
        normals = npd.GetPointData().GetNormals()
        uv = vtk.vtkTextureMapToPlane()
        uv.SetInputData(npd)
        uv.SetAutomaticPlaneGeneration(1)
        uv.Update()
        tcoords = uv.GetOutput().GetPointData().GetTCoords()

        with open(filename, "w", encoding="utf-8") as f:
            f.write("# flowviewer OBJ export\n")
            npts = pd.GetNumberOfPoints()
            for i in range(npts):
                x, y, z = pd.GetPoint(i)
                f.write(f"v {x} {y} {z}\n")
            if tcoords is not None:
                for i in range(npts):
                    u, vv = tcoords.GetTuple2(i)
                    f.write(f"vt {u} {vv}\n")
            if normals is not None:
                for i in range(npts):
                    nx, ny, nz = normals.GetTuple3(i)
                    f.write(f"vn {nx} {ny} {nz}\n")
            has_uv = tcoords is not None
            has_nn = normals is not None
            for i in range(pd.GetNumberOfCells()):
                cell = pd.GetCell(i)
                ids = cell.GetPointIds()
                parts = []
                for k in range(ids.GetNumberOfIds()):
                    vid = ids.GetId(k) + 1
                    if has_uv and has_nn:
                        parts.append(f"{vid}/{vid}/{vid}")
                    elif has_uv:
                        parts.append(f"{vid}/{vid}")
                    elif has_nn:
                        parts.append(f"{vid}//{vid}")
                    else:
                        parts.append(str(vid))
                f.write("f " + " ".join(parts) + "\n")
        return True
    except OSError:
        return False


def export_surface_fbx(ff, filename: str, obj=None) -> bool:
    """Write the boundary surface as ASCII FBX 7.3 (r15, zero-dependency).

    FBX has no VTK writer; instead of shelling out to a converter this
    emits the well-documented ASCII FBX variant directly (accepted by
    Blender/Maya/Unity importers).  Shares the OBJ pipeline's per-vertex
    normals and planar UVs so the mesh re-lits in DCC tools.
    """
    if not _HAS_VTK:
        return False
    import vtk

    from ..model.objects import SurfaceObject
    from .surface import build_surface_polydata
    obj = obj or SurfaceObject(index=1)
    pd, _, _ = build_surface_polydata(ff, obj)
    if pd is None or pd.GetNumberOfCells() == 0:
        return False
    try:
        norms = vtk.vtkPolyDataNormals()
        norms.SetInputData(pd)
        norms.ComputePointNormalsOn()
        norms.ComputeCellNormalsOff()
        norms.SplittingOff()
        norms.Update()
        normals = norms.GetOutput().GetPointData().GetNormals()
        uv = vtk.vtkTextureMapToPlane()
        uv.SetInputData(pd)
        uv.SetAutomaticPlaneGeneration(1)
        uv.Update()
        tcoords = uv.GetOutput().GetPointData().GetTCoords()

        npts = pd.GetNumberOfPoints()
        verts = [pd.GetPoint(i) for i in range(npts)]
        # FBX polygon encoding: last index of every polygon is -(i+1).
        polys = []
        for i in range(pd.GetNumberOfCells()):
            ids = pd.GetCell(i).GetPointIds()
            poly = [ids.GetId(k) for k in range(ids.GetNumberOfIds())]
            if len(poly) < 3:
                continue
            polys.append(poly)

        def _nums(seq):
            return ",".join(("%.9g" % v) for v in seq)

        vflat = [c for p in verts for c in p]
        iflat = [-(i + 1) if k == len(poly) - 1 else i
                 for poly in polys for k, i in enumerate(poly)]

        import time
        now = time.gmtime()
        with open(filename, "w", encoding="utf-8", newline="\n") as f:
            w = f.write
            w("; FBX 7.3.0 project file\n")
            w('; Generated by flowviewer\n\n')
            w("FBXHeaderExtension:  {\n")
            w("\tFBXHeaderVersion: 1003\n")
            w("\tFBXVersion: 7300\n")
            w("\tCreationTimeStamp:  {\n\t\tVersion: 1000\n")
            w("\t\tYear: %d\n\t\tMonth: %d\n\t\tDay: %d\n"
              % (now.tm_year, now.tm_mon, now.tm_mday))
            w("\t\tHour: %d\n\t\tMinute: %d\n\t\tSecond: %d\n\t\tMillisecond: 0\n"
              % (now.tm_hour, now.tm_min, now.tm_sec))
            w("\t}\n\tCreator: \"flowviewer\"\n}\n")
            w("GlobalSettings:  {\n\tVersion: 1000\n\tProperties70:  {\n")
            w('\t\tP: "UpAxis", "int", "Integer", "",1\n')
            w('\t\tP: "UpAxisSign", "int", "Integer", "",1\n')
            w('\t\tP: "FrontAxis", "int", "Integer", "",2\n')
            w('\t\tP: "FrontAxisSign", "int", "Integer", "",1\n')
            w('\t\tP: "CoordAxis", "int", "Integer", "",0\n')
            w('\t\tP: "CoordAxisSign", "int", "Integer", "",1\n')
            w('\t\tP: "UnitScaleFactor", "double", "Number", "",1\n')
            w("\t}\n}\n")
            w("Definitions:  {\n\tVersion: 100\n\tCount: 2\n")
            w('\tObjectType: "Geometry" {\n\t\tCount: 1\n\t}\n')
            w('\tObjectType: "Model" {\n\t\tCount: 1\n\t}\n}\n')
            w("Objects:  {\n")
            w('\tGeometry: 1000000, "Geometry::surface", "Mesh" {\n')
            w("\t\tVertices: *%d {\n\t\t\ta: " % len(vflat))
            w(_nums(vflat))
            w("\n\t\t}\n")
            w("\t\tPolygonVertexIndex: *%d {\n\t\t\ta: " % len(iflat))
            w(_nums(iflat))
            w("\n\t\t}\n")
            w("\t\tGeometryVersion: 124\n")
            if normals is not None:
                nflat = [c for i in range(npts)
                         for c in normals.GetTuple3(i)]
                w("\t\tLayerElementNormal: 0 {\n\t\t\tVersion: 101\n")
                w('\t\t\tName: ""\n')
                w('\t\t\tMappingInformationType: "ByVertice"\n')
                w('\t\t\tReferenceInformationType: "Direct"\n')
                w("\t\t\tNormals: *%d {\n\t\t\t\ta: " % len(nflat))
                w(_nums(nflat))
                w("\n\t\t\t}\n\t\t}\n")
            if tcoords is not None:
                uflat = [c for i in range(npts)
                         for c in tcoords.GetTuple2(i)]
                w("\t\tLayerElementUV: 0 {\n\t\t\tVersion: 101\n")
                w('\t\t\tName: "UVMap"\n')
                w('\t\t\tMappingInformationType: "ByVertice"\n')
                w('\t\t\tReferenceInformationType: "Direct"\n')
                w("\t\t\tUV: *%d {\n\t\t\t\ta: " % len(uflat))
                w(_nums(uflat))
                w("\n\t\t\t}\n\t\t}\n")
            w("\t\tLayer: 0 {\n\t\t\tVersion: 100\n")
            if normals is not None:
                w("\t\t\tLayerElement:  {\n"
                  '\t\t\t\tType: "LayerElementNormal"\n'
                  "\t\t\t\tTypedIndex: 0\n\t\t\t}\n")
            if tcoords is not None:
                w("\t\t\tLayerElement:  {\n"
                  '\t\t\t\tType: "LayerElementUV"\n'
                  "\t\t\t\tTypedIndex: 0\n\t\t\t}\n")
            w("\t\t}\n\t}\n")
            w('\tModel: 1000001, "Model::surface", "Mesh" {\n')
            w("\t\tVersion: 232\n\t\tProperties70:  {\n")
            w('\t\t\tP: "Lcl Translation", "Lcl Translation", "", "A",0,0,0\n')
            w("\t\t}\n\t\tShading: T\n\t\tCulling: \"CullingOff\"\n\t}\n")
            w("}\n")
            w("Connections:  {\n")
            w("\tC: \"OO\",1000001,0\n")
            w("\tC: \"OO\",1000000,1000001\n")
            w("}\n")
        return True
    except OSError:
        return False


def print_scene(scene, parent=None) -> bool:
    """Print the current scene to the default printer (fallback PNG).

    Tries PyQt5's QtPrintSupport/QPrinter; if unavailable, exports the
    current render to ``export_print.png`` next to the working directory and
    returns True so the user at least gets an image.
    """
    if scene is None:
        return False
    if not scene.enable_3d or scene.renderer is None:
        return snapshot_png(scene, "export_view.png")
    try:
        from PyQt5.QtGui import QPainter, QPixmap
        from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
        _HAS_PRINT = True
    except Exception:  # pragma: no cover
        _HAS_PRINT = False
    win = scene.renderer.GetRenderWindow()
    size = win.GetSize()
    if not size or not size[0]:
        return False
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_print_buffer.png")
    if not snapshot_png(scene, tmp):
        return False
    if not _HAS_PRINT:
        return True
    printer = QPrinter(QPrinter.HighResolution)
    dialog = QPrintDialog(printer, parent)
    if parent is not None and getattr(parent, "isVisible", lambda: True)():
        if dialog.exec_() != 1:  # QDialog.Accepted
            os.remove(tmp)
            return False
    painter = QPainter(printer)
    painter.drawPixmap(0, 0, QPixmap(tmp))
    painter.end()
    os.remove(tmp)
    return True


def export_surface_cvff(ff, filename: str) -> bool:
    """Write named boundary-region groups as a CradleViewer CVFF scene (R17-T4b).

    Inverse of ``fv.model.dataset.cvff_load``: every boundary region
    becomes one named tree group; per-region vertices are compacted and
    re-indexed, so re-loading the exported file reproduces the same
    region split (mesh geometry only, no scalar fields - CVFF is a
    geometry-viewer format like the STL/FBX exports).  FPH/GPH/PPH
    surfaces come from the ``link_data`` face table (boundary faces are
    the ``neighbour == -1`` rows); FLD/neutral kinds use ``ff.faces``.
    """
    import numpy as np

    from ..crdl.cvff import build_scene, write_cvff
    if ff.vertices is None:
        return False
    region_faces = []
    if ff.poly and ff.link_data is not None:
        ld = ff.link_data
        face_nodes = np.asarray(ld["face_nodes"], dtype=np.int64)
        face_offsets = np.asarray(ld["face_offsets"], dtype=np.int64)
        neighbour = np.asarray(ld["neighbour"], dtype=np.int64)
        bnd = set(np.flatnonzero(neighbour == -1).tolist())
        for reg in ff.boundary_regions():
            faces = [face_nodes[int(face_offsets[i]):int(face_offsets[i + 1])]
                     .tolist()
                     for i in np.asarray(reg.face_ids, dtype=np.int64).tolist()
                     if int(i) in bnd]
            if faces:
                region_faces.append((reg.name, faces))
    elif ff.faces:
        # FLD faces carry the file's 1-based node ids (OBJ/STL/PLY/CVFF
        # loaders already emit 0-based indices).
        shift = 1 if ff.kind == "fld" else 0
        for reg in ff.boundary_regions():
            faces = [[int(v) - shift for v in ff.faces[i]]
                     for i in np.asarray(reg.face_ids, dtype=np.int64).tolist()
                     if 0 <= i < len(ff.faces)]
            if faces:
                region_faces.append((reg.name, faces))
        if not region_faces:   # anonymous single group over the whole boundary
            region_faces = [("Boundary",
                             [[int(v) - shift for v in f]
                              for f in ff.faces if len(f)])]
    if not region_faces:
        return False
    verts_all = np.asarray(ff.vertices, dtype=np.float64)
    groups = []
    for name, faces in region_faces:
        faces = [f for f in faces if len(f)]
        if not faces:
            continue
        used = sorted({int(v) for f in faces for v in f})
        remap = {v: k for k, v in enumerate(used)}
        groups.append((str(name), verts_all[used],
                       [[remap[int(v)] for v in f] for f in faces]))
    if not groups:
        return False
    try:
        write_cvff(str(filename), build_scene(groups))
    except (OSError, ValueError, IndexError):
        return False
    return True


# ── R25-S1: off-screen frame sequences + video (PNG / MP4 / ogv / avi) ─────

def _frame_actors(frame) -> list:
    """Flatten one animation frame into a printable actor list.

    ``frame`` is either one of :func:`~fv.render.isosurface.build_iso_animation`'s
    per-cycle actor dicts (``{"contour":..,"contour_line":..,"vector":..}``) or
    a plain list/tuple of actors/render props. Empty entries are skipped.
    """
    out: list = []
    if isinstance(frame, dict):
        frames_ = frame.values()
    elif frame is None:
        frames_ = []
    elif isinstance(frame, (list, tuple)):
        frames_ = frame
    else:
        frames_ = [frame]
    for a in frames_:
        if a is not None:
            out.append(a)
    return out


def _show_frame(renderer, render_window, actors) -> None:
    """Add a frame's actors to the renderer and paint once (offscreen-safe)."""
    if render_window is None:
        return
    for a in actors:
        if isinstance(a, vtk.vtkActor2D):
            renderer.AddActor2D(a)
        else:
            renderer.AddActor(a)
    render_window.Render()


def _hide_frame(renderer, actors) -> None:
    """Remove a frame's actors from the renderer (paint happens next frame)."""
    for a in actors:
        if isinstance(a, vtk.vtkActor2D):
            try:
                renderer.RemoveActor2D(a)
            except Exception:  # pragma: no cover
                pass
        else:
            try:
                renderer.RemoveActor(a)
            except Exception:  # pragma: no cover
                pass


def export_iso_png_frames(frames, renderer_or_window, out_dir: str,
                          base: str = "frame", scale: float = 1.0,
                          dpi: float = 72.0) -> int:
    """Render each animation frame to a PNG in *out_dir* (R25-S1).

    ``frames`` is the list produced by ``build_iso_animation``; every frame is
    added to *renderer_or_window*'s renderer, rendered, and snapped to
    ``out_dir/base_%04d.png`` at the given ``scale``/``dpi`` before the next
    frame replaces it. Returns the number of frames written (0 if no render
    window / VTK missing).
    """
    if not _HAS_VTK:
        return 0
    win = renderer_or_window
    renderer = None
    if hasattr(win, "GetRenderWindow"):
        renderer = win
        win = win.GetRenderWindow()
    elif hasattr(win, "GetLayers") or hasattr(win, "Render"):
        renderer = getattr(win, "GetRenderers", None) and win.GetRenderers() \
            and win.GetRenderers().GetFirstRenderer()
    if win is None:
        return 0
    out_dir = Path(out_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 0
    written = 0
    for t, frame in enumerate(frames or []):
        actors = _frame_actors(frame)
        if renderer is not None:
            _show_frame(renderer, win, actors)
        path = out_dir / f"{base}_{t:04d}.png"
        if snapshot_png(win, str(path), scale=scale, dpi=dpi):
            written += 1
        if renderer is not None:
            _hide_frame(renderer, actors)
    return written


def _ffmpeg_path() -> Optional[str]:
    """Locate ffmpeg on PATH (R25-S1 optional video encoder)."""
    import shutil
    return shutil.which("ffmpeg")


def _encode_video_ffmpeg(png_dir: str, pattern: str, filename: str,
                         fps: int) -> int:
    """Encode a ``glob`` PNG sequence into a video via ffmpeg (R25-S1).

    Returns the number of input frames ffmpeg reported, or 0 on any failure.
    Explicit closes of stdin are harmless on Windows (the child reads the
    glob, not stdin).
    """
    import subprocess
    png_dir = os.fspath(png_dir)
    pattern = os.path.join(png_dir, pattern) if not os.path.isabs(pattern) \
        else pattern
    cmd = ["ffmpeg", "-y", "-framerate", str(int(fps)),
           "-i", pattern, "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-loglevel", "error", str(filename)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=300)
    except Exception:  # pragma: no cover - ffmpeg failed to launch
        return 0
    if proc.returncode != 0:
        return 0
    if os.path.exists(filename) and os.path.getsize(filename) > 0:
        return 1
    return 0


def export_iso_video(frames, renderer_or_window, filename: str,
                     fps: int = 15, scale: float = 1.0, dpi: float = 72.0,
                     tmp_dir: Optional[str] = None) -> int:
    """Render an iso/animation frame list to a video (R25-S1).

    Frames are first we-written into a temporary PNG sequence, then encoded:

    - ``.mp4`` -> ffmpeg (libx264) when available on PATH;
    - otherwise the VTK-native path (``.ogv`` via vtkOggTheoraWriter, or
      ``.avi`` via vtkAVIWriter when that writer exists) is driven by the same
      actor frames.

    Returns the number of frames the encoder consumed (>0 on success) or 0.
    """
    if not _HAS_VTK:
        return 0
    import tempfile
    win = renderer_or_window
    renderer = None
    if hasattr(win, "GetRenderWindow"):
        renderer = win
        win = win.GetRenderWindow()
    if win is None:
        return 0
    frames = list(frames or [])
    cleaned = None
    if tmp_dir is None:
        cleaned = tempfile.mkdtemp(prefix="fv_export_")
        tmp_dir = cleaned
    written = export_iso_png_frames(frames, renderer_or_window, tmp_dir,
                                    base="frame", scale=scale, dpi=dpi)
    if not written:
        if cleaned is not None:
            import shutil
            shutil.rmtree(cleaned, ignore_errors=True)
        return 0
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".mp4" and _ffmpeg_path():
        n = _encode_video_ffmpeg(
            tmp_dir, "frame_%04d.png", filename,
            fps=int(fps))
        ok = n > 0
    else:
        n = _write_frame_video(frames, renderer, win, filename,
                               fps=int(fps))
        ok = n > 0
    if cleaned is not None:
        import shutil
        shutil.rmtree(cleaned, ignore_errors=True)
    return n if ok else 0


def _write_frame_video(frames, renderer, render_window, filename: str,
                       fps: int = 15) -> int:
    """Drive a VTK video writer frame-by-frame (R25-S1, non-ffmpeg path).

    Picks ``vtkOggTheoraWriter`` for ``.ogv`` or ``vtkAVIWriter`` for ``.avi``
    when that writer is present, adds each frame's actors, paints, encodes a
    frame, then replaces them - unlike :func:`_write_vtk_video` which reuses
    ``scene.animate``. Returns frames written, or 0 on failure.
    """
    import vtk
    writer = None
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".avi" and hasattr(vtk, "vtkAVIWriter"):
        writer = vtk.vtkAVIWriter()
    elif hasattr(vtk, "vtkOggTheoraWriter"):
        writer = vtk.vtkOggTheoraWriter()
    if writer is None:
        return 0
    try:
        writer.SetFileName(str(filename))
        if hasattr(writer, "SetRate"):
            writer.SetRate(int(fps))
        w2i = vtk.vtkWindowToImageFilter()
        w2i.SetInput(render_window)
        w2i.SetInputBufferTypeToRGB()
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Start()
        written = 0
        for frame in frames or []:
            actors = _frame_actors(frame)
            if renderer is not None:
                _show_frame(renderer, render_window, actors)
            render_window.Render()
            w2i.Modified()
            writer.Write()
            written += 1
            if renderer is not None:
                _hide_frame(renderer, actors)
        writer.End()
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            return written
        return 0
    except Exception:  # pragma: no cover
        return 0
