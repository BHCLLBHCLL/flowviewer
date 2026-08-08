"""VTK scene builder: FieldFile → wireframe grid + objects + text overlay."""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..model.dataset import FieldFile

try:
    import vtk
    from vtk.util import numpy_support as _vns
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    _vns = None


class Scene:
    """Holds VTK renderer + actors for one dataset.

    ``enable_3d=False`` disables real rendering (headless tests): actors are
    replaced by a placeholder list and every build call is a no-op that still
    records the actor *names*.
    """

    def __init__(self, enable_3d: bool = True):
        self.enable_3d = enable_3d and _HAS_VTK
        self.renderer = None
        self._layer_actors: dict[str, list] = {}
        self._overlay = None
        self._overlay_text = ""
        self._bounds: Optional[tuple] = None
        if self.enable_3d:
            self.renderer = vtk.vtkRenderer()
            # Light scPOST Draw Window (near-white)
            self.renderer.SetBackground(1.0, 1.0, 1.0)
            self.renderer.SetBackground2(0.92, 0.94, 0.97)
            self.renderer.GradientBackgroundOn()
            self.renderer.GetActiveCamera().ParallelProjectionOn()

    def reset(self) -> None:
        if self.enable_3d and self.renderer is not None:
            for actors in self._layer_actors.values():
                for a in actors:
                    if isinstance(a, str):
                        continue
                    self.renderer.RemoveActor(a)
            if self._overlay is not None:
                try:
                    self.renderer.RemoveActor2D(self._overlay)
                except Exception:
                    pass
                self._overlay = None
        self._layer_actors = {}
        self._overlay_text = ""
        self._bounds = None

    def add_actor(self, layer: str, actor) -> None:
        if self.enable_3d:
            self.renderer.AddActor(actor)
        self._layer_actors.setdefault(layer, []).append(actor)

    def actor_names(self) -> list[str]:
        return [name for name, actors in self._layer_actors.items() if actors]

    def layer_count(self, layer: str) -> int:
        return len(self._layer_actors.get(layer, []))

    def set_layer_visible(self, layer: str, visible: bool) -> None:
        for a in self._layer_actors.get(layer, []):
            if self.enable_3d and not isinstance(a, str):
                a.SetVisibility(1 if visible else 0)

    def fit(self) -> None:
        if self.enable_3d and self.renderer:
            self.renderer.ResetCamera()

    # ── overlay (File / Cycle / Time) ─────────────────────────────────────

    def set_overlay(self, file_name: str, cycle=None, time=None) -> None:
        """Top-left Draw Window info matching scPOST."""
        cyc = "—" if cycle is None else str(cycle)
        if time is None:
            tim = "—"
        else:
            tim = f"{time:.6g}"
        text = f"File : {file_name}\nCycle : {cyc}\nTime : {tim}"
        self._overlay_text = text
        if not self.enable_3d or self.renderer is None:
            return
        if self._overlay is None:
            self._overlay = vtk.vtkTextActor()
            tp = self._overlay.GetTextProperty()
            tp.SetFontFamilyToCourier()
            tp.SetFontSize(14)
            tp.SetBold(1)
            tp.SetColor(0.0, 0.0, 0.0)
            tp.SetLineSpacing(1.15)
            self._overlay.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
            self._overlay.SetPosition(0.02, 0.92)
            self.renderer.AddActor2D(self._overlay)
        self._overlay.SetInput(text)

    def overlay_text(self) -> str:
        return self._overlay_text

    # ── builders ───────────────────────────────────────────────────────────

    def build(self, ff: FieldFile, main=None) -> None:
        """Rebuild actors: wireframe grid + default Surface/Plane[/Particle]."""
        self.reset()
        from pathlib import Path
        self.set_overlay(
            Path(ff.path).name,
            getattr(ff, "cycle", None),
            getattr(ff, "time", None),
        )

        if not self.enable_3d:
            self._layer_actors["grid"] = ["wireframe"]
            self._layer_actors["surface"] = ["surface_1"]
            self._layer_actors["plane"] = ["plane_1"]
            if getattr(ff, "has_particles", False) or (
                    main is not None and getattr(main, "has_particles", False)):
                self._layer_actors["particle"] = ["particle_1"]
            return

        if ff.kind == "fph":
            self._build_fph_wireframe(ff)
        else:
            self._build_fld_wireframe(ff)

        # Default objects (Magic-open style)
        children = list(getattr(main, "children", []) or [])
        if not children:
            from ..model.objects import MainObject
            children = MainObject.from_field_file(ff).children
        for obj in children:
            if obj.kind == "surface" and obj.visible:
                # Surface shares the boundary wireframe (already in grid);
                # keep a named layer for visibility toggles.
                self._layer_actors.setdefault("surface", [])
                if self._layer_actors.get("grid"):
                    self._layer_actors["surface"] = list(
                        self._layer_actors["grid"])
            elif obj.kind == "plane" and obj.visible:
                self._add_plane_actors(ff, obj)
            elif obj.kind == "particle" and obj.visible:
                self._add_particle_placeholder(obj)

    def _polydata_boundary(self, ff: FieldFile):
        ld = ff.link_data
        if ld is None or ff.vertices is None:
            return None
        face_nodes = np.asarray(ld["face_nodes"], dtype=np.int64)
        face_offsets = np.asarray(ld["face_offsets"], dtype=np.int64)
        neighbour = np.asarray(ld["neighbour"], dtype=np.int64)
        verts = np.asarray(ff.vertices, dtype=np.float64)
        self._bounds = (
            tuple(verts.min(axis=0).tolist()),
            tuple(verts.max(axis=0).tolist()),
        )

        bnd = np.flatnonzero(neighbour == -1)
        if bnd.size == 0:
            bnd = np.arange(max(0, len(face_offsets) - 1))
        bnd = np.asarray(bnd, dtype=np.int64)

        points = vtk.vtkPoints()
        points.SetData(_vns.numpy_to_vtk(verts, deep=True))
        polys = vtk.vtkCellArray()
        ids = vtk.vtkIdList()
        for fi in bnd:
            lo = int(face_offsets[fi])
            hi = int(face_offsets[fi + 1])
            ids.Reset()
            for vi in face_nodes[lo:hi]:
                ids.InsertNextId(int(vi))
            polys.InsertNextCell(ids)
        pd = vtk.vtkPolyData()
        pd.SetPoints(points)
        pd.SetPolys(polys)
        return pd

    def _build_fph_wireframe(self, ff: FieldFile) -> None:
        pd = self._polydata_boundary(ff)
        if pd is None:
            return
        # Extract edges for crisp black wireframe (scPOST mesh lines)
        edges = vtk.vtkExtractEdges()
        edges.SetInputData(pd)
        edges.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(edges.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(0.05, 0.05, 0.08)
        prop.SetLineWidth(1.0)
        prop.SetRepresentationToWireframe()
        self.add_actor("grid", actor)

    def _build_fld_wireframe(self, ff: FieldFile) -> None:
        if ff.vertices is None or ff.cell_conn is None:
            return
        verts = np.asarray(ff.vertices, dtype=np.float64)
        conn = np.asarray(ff.cell_conn, dtype=np.int64)
        self._bounds = (
            tuple(verts.min(axis=0).tolist()),
            tuple(verts.max(axis=0).tolist()),
        )
        ugrid = vtk.vtkUnstructuredGrid()
        points = vtk.vtkPoints()
        points.SetData(_vns.numpy_to_vtk(verts, deep=True))
        ugrid.SetPoints(points)
        cells = vtk.vtkCellArray()
        for row in conn:
            hexa = vtk.vtkHexahedron()
            for k in range(8):
                hexa.GetPointIds().SetId(k, int(row[k]))
            cells.InsertNextCell(hexa)
        ugrid.SetCells(vtk.VTK_HEXAHEDRON, cells)
        edges = vtk.vtkExtractEdges()
        edges.SetInputData(ugrid)
        edges.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(edges.GetOutputPort())
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(0.05, 0.05, 0.08)
        prop.SetLineWidth(1.0)
        self.add_actor("grid", actor)

    def _add_plane_actors(self, ff: FieldFile, obj) -> None:
        """Cut-plane pipeline: contour / vector / mesh / boundary / subline
        actors from :func:`fv.render.plane.build_plane_actors`, plus a
        semi-transparent base rectangle for orientation.
        """
        from . import plane as plane_render
        actors = plane_render.build_plane_actors(ff, obj)
        for key, actor in actors.items():
            self.add_actor(f"plane:{key}", actor)
        if "contour" not in actors and self._bounds is not None:
            lo, hi = self._bounds
            axis = (obj.axis or "Z").upper()
            c = float(obj.coordinate)
            src = vtk.vtkPlaneSource()
            if axis == "X":
                src.SetOrigin(c, lo[1], lo[2])
                src.SetPoint1(c, hi[1], lo[2])
                src.SetPoint2(c, lo[1], hi[2])
            elif axis == "Y":
                src.SetOrigin(lo[0], c, lo[2])
                src.SetPoint1(hi[0], c, lo[2])
                src.SetPoint2(lo[0], c, hi[2])
            else:
                src.SetOrigin(lo[0], lo[1], c)
                src.SetPoint1(hi[0], lo[1], c)
                src.SetPoint2(lo[0], hi[1], c)
            src.SetResolution(1, 1)
            src.Update()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(src.GetOutputPort())
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            prop = actor.GetProperty()
            color = getattr(obj, "mesh_color", (0.8, 0.2, 0.5))
            prop.SetColor(*color)
            prop.SetOpacity(0.35)
            prop.EdgeVisibilityOn()
            prop.SetEdgeColor(*color)
            self.add_actor("plane", actor)

    def _add_particle_placeholder(self, obj) -> None:
        """Record particle layer; full glyph rendering comes later."""
        self._layer_actors.setdefault("particle", ["particle_1"])


def numpy_to_vtk_array(arr: np.ndarray, name: str):
    """Convert a 1-D array to a vtkFloatArray for PointData/CellData."""
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(arr, dtype=np.float64), deep=True)
    fa.SetName(name)
    return fa
