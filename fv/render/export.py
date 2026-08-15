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


def snapshot_png(renderer_or_window, filename: str) -> bool:
    """Capture the VTK render window to a PNG file.

    ``renderer_or_window``: a renderer (during tests) or a
    ``vtkRenderWindow``. Returns True on success, False if VTK is missing or
    the window has nothing to render (headless).
    """
    if not _HAS_VTK:
        return False
    import vtk

    win = renderer_or_window
    if hasattr(win, "GetRenderWindow"):
        win = win.GetRenderWindow()
    if win is None:
        return False
    try:
        base, ext = os.path.splitext(filename)
        if ext.lower() not in (".png", ".jpg", ".jpeg", ".bmp", ".tif"):
            filename = base + ".png"
        if str(ext).lower() in (".jpg", ".jpeg"):
            w2i = vtk.vtkWindowToImageFilter()
            w2i.SetInput(win)
            w2i.SetInputBufferTypeToRGB()
            w2i.Update()
            writer = vtk.vtkJPEGWriter()
            writer.SetFileName(filename)
            writer.SetInputConnection(w2i.GetOutputPort())
            writer.Write()
        else:
            w2i = vtk.vtkWindowToImageFilter()
            w2i.SetInput(win)
            w2i.SetInputBufferTypeToRGB()
            w2i.Update()
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
    if not _KIND_CLASSES:
        from ..model import objects as _om
        _KIND_CLASSES.update({
            "surface": _om.SurfaceObject,
            "plane": _om.PlaneObject,
            "particle": _om.ParticleObject,
            "isosurface": _om.IsosurfaceObject,
            "point": _om.PointObject,
            "streamline": _om.StreamlineObject,
            "volume": _om.VolumeObject,
            "light": _om.LightObject,
            "colorbar": _om.ColorbarObject,
        })
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
        with open(filepath, "r", encoding="utf-8") as fh:
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
    from .surface import build_surface_polydata
    from ..model.objects import SurfaceObject
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


def export_surface_obj(ff, filename: str, obj=None) -> bool:
    """Write the boundary surface as Wavefront OBJ (4, FBX-neutral).

    FBX has no native VTK writer; OBJ is the neutral interchange format
    most FBX converters accept.
    """
    if not _HAS_VTK:
        return False
    from .surface import build_surface_polydata
    from ..model.objects import SurfaceObject
    obj = obj or SurfaceObject(index=1)
    pd, _, _ = build_surface_polydata(ff, obj)
    if pd is None or pd.GetNumberOfCells() == 0:
        return False
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write("# flowviewer OBJ export\n")
            for i in range(pd.GetNumberOfPoints()):
                x, y, z = pd.GetPoint(i)
                f.write(f"v {x} {y} {z}\n")
            for i in range(pd.GetNumberOfCells()):
                cell = pd.GetCell(i)
                ids = cell.GetPointIds()
                verts = [str(ids.GetId(k) + 1)
                         for k in range(ids.GetNumberOfIds())]
                f.write("f " + " ".join(verts) + "\n")
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