"""VTK scene builder: convert a FieldFile into renderable actors."""

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
        if self.enable_3d:
            self.renderer = vtk.vtkRenderer()
            self.renderer.SetBackground(0.15, 0.17, 0.2)
            self.renderer.SetBackground2(0.4, 0.45, 0.52)
            self.renderer.GradientBackgroundOn()
            self.renderer.GetActiveCamera().ParallelProjectionOn()

    def reset(self) -> None:
        if self.enable_3d:
            for actors in self._layer_actors.values():
                for a in actors:
                    self.renderer.RemoveActor(a)
        self._layer_actors = {}

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
            if self.enable_3d:
                a.SetVisibility(1 if visible else 0)

    def fit(self) -> None:
        if self.enable_3d and self.renderer:
            self.renderer.ResetCamera()

    # ── builders ───────────────────────────────────────────────────────────

    def build(self, ff: FieldFile) -> None:
        """Rebuild all actors for *ff* into layers 'grid' and 'bc'."""
        self.reset()
        if not self.enable_3d:
            # Headless: record layer names so tests can assert structure.
            if ff.kind == "fph":
                self._layer_actors["grid"] = ["fph_boundary"]
            else:
                self._layer_actors["grid"] = ["fld_hex"]
            if ff.surface_regions or ff.bc_plan:
                self._layer_actors["bc"] = [n for n in self._region_names(ff)]
            return

        if ff.kind == "fph":
            self._build_fph(ff)
        else:
            self._build_fld(ff)

    @staticmethod
    def _region_names(ff: FieldFile) -> list[str]:
        names = [n for n, _ in ff.surface_regions]
        if not names and ff.bc_plan:
            names = [n for n, _, cnt in ff.bc_plan if cnt]
        return names

    def _build_fph(self, ff: FieldFile) -> None:
        ld = ff.link_data
        if ld is None or ff.vertices is None:
            return
        face_nodes = np.asarray(ld["face_nodes"], dtype=np.int64)
        face_offsets = np.asarray(ld["face_offsets"], dtype=np.int64)
        neighbour = np.asarray(ld["neighbour"], dtype=np.int64)
        verts = np.asarray(ff.vertices, dtype=np.float64)

        # Boundary faces: neighbour == -1.
        bnd = np.flatnonzero(neighbour == -1)
        if bnd.size == 0:
            bnd = np.arange(len(face_offsets) - 1)
        bnd = np.asarray(bnd, dtype=np.int64)
        n_faces = bnd.size

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

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(pd)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(0.75, 0.78, 0.85)
        prop.SetEdgeColor(0.35, 0.38, 0.45)
        prop.EdgeVisibilityOn()
        prop.SetLineWidth(1.0)
        self.add_actor("grid", actor)
        self._fph_boundary = bnd

    def _build_fld(self, ff: FieldFile) -> None:
        if ff.vertices is None or ff.cell_conn is None:
            return
        verts = np.asarray(ff.vertices, dtype=np.float64)
        conn = np.asarray(ff.cell_conn, dtype=np.int64)

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

        mapper = vtk.vtkDataSetMapper()
        mapper.SetInputData(ugrid)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(0.7, 0.76, 0.85)
        prop.SetEdgeColor(0.3, 0.34, 0.42)
        prop.EdgeVisibilityOn()
        self.add_actor("grid", actor)


def numpy_to_vtk_array(arr: np.ndarray, name: str):
    """Convert a 1-D array to a vtkFloatArray for PointData/CellData."""
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(arr, dtype=np.float64), deep=True)
    fa.SetName(name)
    return fa