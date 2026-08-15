"""Universal Field Object (scPOST UFO, 7b) — generic point-cloud rendering.

A UFO carries an arbitrary point set (plus optional scalar values) or
colour-maps a field-file variable at its nodes, rendered as a scatter of
points (vtkVertexGlyphFilter).  This replaces the former placeholder with a
real render pipeline (item 2).
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
    1. external ``obj.data["points"]`` / ``obj.data["values"]``;
    2. a field-file variable ``obj.variable`` sampled at its own location
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


def build_ufo_actors(ff, obj) -> dict:
    """Scatter actor for a UFO: {"ufo": vtkActor} (or {})."""
    pts, vals = ufo_points_values(ff, obj)
    if pts is None or len(pts) == 0:
        return {}
    if pts.ndim == 1:
        pts = pts.reshape(1, -1)
    if pts.shape[1] != 3:
        return {}
    import vtk
    from vtk.util import numpy_support as _vns
    vpts = vtk.vtkPoints()
    vpts.SetData(_vns.numpy_to_vtk(np.ascontiguousarray(pts), deep=True))
    pd = vtk.vtkPolyData()
    pd.SetPoints(vpts)
    has_vals = vals is not None and len(vals) == len(pts)
    if has_vals:
        sarr = vtk.vtkFloatArray()
        sarr.SetName("ufo_value")
        sarr.SetNumberOfComponents(1)
        sarr.SetNumberOfTuples(len(vals))
        for i, v in enumerate(vals):
            sarr.SetTuple1(i, float(v))
        pd.GetPointData().SetScalars(sarr)
    glyph = vtk.vtkVertexGlyphFilter()
    glyph.SetInputData(pd)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(glyph.GetOutputPort())
    if has_vals:
        lo = float(np.nanmin(vals))
        hi = float(np.nanmax(vals))
        if hi <= lo:
            hi = lo + 1.0
        mapper.SetScalarModeToUsePointData()
        mapper.SetColorModeToMapScalars()
        mapper.SetScalarRange(lo, hi)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetPointSize(float(getattr(obj, "point_size", 3.0) or 3.0))
    color = getattr(obj, "color", (0.2, 0.2, 0.8))
    try:
        actor.GetProperty().SetColor(*color)
    except (TypeError, IndexError):
        actor.GetProperty().SetColor(0.2, 0.2, 0.8)
    return {"ufo": actor}
