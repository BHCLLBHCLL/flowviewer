"""Universal Field Object (scPOST UFO, 7b) — point-cloud / surface rendering.

A UFO carries an arbitrary point set (plus optional scalar values) or
colour-maps a field-file variable.  Two render modes:

* ``points``  - scatter of points (vtkVertexGlyphFilter);
* ``surface`` - triangle mesh from obj.data["cells"] or FieldFile.faces.
"""

from __future__ import annotations

import numpy as np


def _cell_centers(ff):
    """(n_cells, 3) cell-centre coordinates for node/cell placement (2)."""
    if getattr(ff, "kind", "") == "fph":
        try:
            from ..model.varreg import _cell_centers_fph
            c = _cell_centers_fph(ff)
            if c is not None and c.shape[0] == ff.n_cells:
                return c
        except Exception:
            pass
    conn = getattr(ff, "cell_conn", None)
    if conn is not None and ff.vertices is not None:
        conn = np.asarray(conn, dtype=np.int64)
        verts = np.asarray(ff.vertices, dtype=np.float64)
        out = np.zeros((conn.shape[0], 3))
        for c, row in enumerate(conn):
            ids = row[row >= 0]
            if len(ids) and ids.max() < len(verts):
                out[c] = verts[ids].mean(axis=0)
        return out
    return None


def ufo_points_values(ff, obj):
    """Resolve a UFO to (points Nx3, values N|None) without VTK (2).

    Priority:
    1. external obj.data["points"] / obj.data["values"];
    2. a field-file variable obj.variable sampled at its own location
       (nodes -> vertices, cells -> cell centres);
    3. all field-file vertices with no scalar.
    """
    data = getattr(obj, "data", None) or {}
    ext_pts = data.get("points")
    ext_vals = data.get("values")
    if ext_pts is not None:
        pts = np.asarray(ext_pts, dtype=np.float64)
        vals = np.asarray(ext_vals, dtype=np.float64) if ext_vals is not None else None
        return pts, vals
    name = getattr(obj, "variable", "") or ""
    if name:
        vi = getattr(ff, "variables", {}).get(name)
        arr = ff.variable_array(name)
        if arr is not None and np.asarray(arr).ndim == 1:
            arr = np.asarray(arr, dtype=np.float64)
            loc = getattr(vi, "location", "") if vi is not None else ""
            if loc == "cell" or (ff.vertices is not None and len(arr) == ff.n_cells):
                centers = _cell_centers(ff)
                if centers is not None and len(centers) == len(arr):
                    return centers, arr
            if ff.vertices is not None and len(arr) == ff.n_vertices:
                return np.asarray(ff.vertices, dtype=np.float64), arr
    if ff.vertices is not None:
        return np.asarray(ff.vertices, dtype=np.float64), None
    return None, None


def triangulate(cells):
    """Fan-triangulate faces (list of index lists) -> (M,3) int array."""
    tris = []
    for face in cells:
        f = [int(x) for x in face]
        if len(f) < 3:
            continue
        for i in range(1, len(f) - 1):
            tris.append([f[0], f[i], f[i + 1]])
    return np.asarray(tris, dtype=np.int64) if tris else None


def ufo_triangles(ff, obj):
    """Resolve a UFO surface to triangle indices (M,3), or None (3)."""
    data = getattr(obj, "data", None) or {}
    cells = data.get("cells")
    if cells is not None:
        arr = np.asarray(cells, dtype=np.int64)
        if arr.ndim == 2 and arr.shape[1] == 3:
            return arr
        if arr.ndim == 2 and arr.shape[1] > 3:
            return triangulate([row for row in arr])
        return triangulate(cells)
    faces = getattr(ff, "faces", None)
    if faces:
        return triangulate(faces)
    return None


def _vtk_scalars(pts_len, vals):
    """Return a vtkFloatArray when vals matches the target length, else None."""
    if vals is None or len(vals) != pts_len:
        return None
    import vtk
    sarr = vtk.vtkFloatArray()
    sarr.SetName("ufo_value")
    sarr.SetNumberOfComponents(1)
    sarr.SetNumberOfTuples(len(vals))
    for i, v in enumerate(vals):
        sarr.SetTuple1(i, float(v))
    return sarr


def _build_points_actor(ff, obj):
    """Scatter actor (points mode)."""
    pts, vals = ufo_points_values(ff, obj)
    if pts is None or len(pts) == 0:
        return None
    if pts.ndim == 1:
        pts = pts.reshape(1, -1)
    if pts.shape[1] != 3:
        return None
    import vtk
    from vtk.util import numpy_support as _vns
    vpts = vtk.vtkPoints()
    vpts.SetData(_vns.numpy_to_vtk(np.ascontiguousarray(pts), deep=True))
    pd = vtk.vtkPolyData()
    pd.SetPoints(vpts)
    has_vals = vals is not None and len(vals) == len(pts)
    if has_vals:
        pd.GetPointData().SetScalars(_vtk_scalars(len(pts), vals))
    glyph = vtk.vtkVertexGlyphFilter()
    glyph.SetInputData(pd)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(glyph.GetOutputPort())
    if has_vals:
        lo = float(np.nanmin(vals)); hi = float(np.nanmax(vals))
        if hi <= lo:
            hi = lo + 1.0
        mapper.SetScalarModeToUsePointData()
        mapper.SetColorModeToMapScalars()
        mapper.SetScalarRange(lo, hi)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetPointSize(float(getattr(obj, "point_size", 3.0) or 3.0))
    return actor


def _build_surface_actor(ff, obj):
    """Triangle-mesh actor (surface mode)."""
    pts, vals = ufo_points_values(ff, obj)
    tris = ufo_triangles(ff, obj)
    if pts is None or len(pts) == 0 or tris is None or len(tris) == 0:
        return None
    if pts.ndim == 1:
        pts = pts.reshape(1, -1)
    if pts.shape[1] != 3:
        return None
    import vtk
    from vtk.util import numpy_support as _vns
    vpts = vtk.vtkPoints()
    vpts.SetData(_vns.numpy_to_vtk(np.ascontiguousarray(pts), deep=True))
    pd = vtk.vtkPolyData()
    pd.SetPoints(vpts)
    ca = vtk.vtkCellArray()
    for tri in tris:
        cell = vtk.vtkTriangle()
        for k in range(3):
            cell.GetPointIds().SetId(k, int(tri[k]))
        ca.InsertNextCell(cell)
    pd.SetPolys(ca)
    # scalar: point-level (len==pts) or cell-level (len==tris)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    if vals is not None and len(vals) == len(pts):
        pd.GetPointData().SetScalars(_vtk_scalars(len(pts), vals))
        lo = float(np.nanmin(vals)); hi = float(np.nanmax(vals))
        if hi <= lo:
            hi = lo + 1.0
        mapper.SetScalarModeToUsePointData()
        mapper.SetColorModeToMapScalars()
        mapper.SetScalarRange(lo, hi)
    elif vals is not None and len(vals) == len(tris):
        pd.GetCellData().SetScalars(_vtk_scalars(len(tris), vals))
        lo = float(np.nanmin(vals)); hi = float(np.nanmax(vals))
        if hi <= lo:
            hi = lo + 1.0
        mapper.SetScalarModeToUseCellData()
        mapper.SetColorModeToMapScalars()
        mapper.SetScalarRange(lo, hi)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor


def build_ufo_actors(ff, obj) -> dict:
    """UFO actor(s): {"ufo": vtkActor} or {} (points or surface mode)."""
    mode = (getattr(obj, "mode", "points") or "points").lower()
    actor = (_build_surface_actor(ff, obj) if mode.startswith("surface")
             else _build_points_actor(ff, obj))
    if actor is None:
        return {}
    color = getattr(obj, "color", (0.2, 0.2, 0.8))
    try:
        actor.GetProperty().SetColor(*color)
    except (TypeError, IndexError):
        actor.GetProperty().SetColor(0.2, 0.2, 0.8)
    if getattr(obj, "transparent", False):
        actor.GetProperty().SetOpacity(0.5)
    return {"ufo": actor}
