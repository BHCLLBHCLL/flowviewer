"""Curve object (scPOST Curve, A1) — variable sampled along a polyline.

Interpolates a polyline through control points (vtkParametricSpline),
samples a variable along it by nearest-node lookup, and colours the
line by the sampled values.  The same sampling feeds Graph as an X-axis
data source (arc-length vs variable).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import vtk
from vtk.util import numpy_support as _vns

from ..model.dataset import FieldFile


def _curve_points(obj) -> Optional[np.ndarray]:
    """Control points as (k, 3), or None when fewer than 2."""
    pts = list(getattr(obj, "points", None) or [])
    if len(pts) < 2:
        return None
    return np.asarray(pts, dtype=np.float64)


def _spline_polyline(ctrl: np.ndarray, n: int) -> Optional[object]:
    """vtkPolyData line through *ctrl*, resampled to *n* points."""
    pts = vtk.vtkPoints()
    for i in range(len(ctrl)):
        pts.InsertNextPoint(float(ctrl[i, 0]), float(ctrl[i, 1]),
                            float(ctrl[i, 2]))
    src = vtk.vtkPolyData()
    src.SetPoints(pts)
    spline = vtk.vtkParametricSpline()
    spline.SetPoints(pts)
    fs = vtk.vtkParametricFunctionSource()
    fs.SetParametricFunction(spline)
    fs.SetUResolution(max(2, n - 1))
    fs.Update()
    out = fs.GetOutput()
    if out.GetNumberOfPoints() < 2:
        return None
    return out


def sample_along_curve(ff: FieldFile, obj) -> tuple:
    """(arc_lengths, values, var) sampled along the curve (A1)."""
    var = (getattr(obj, "variable", "") or "").strip()
    ctrl = _curve_points(obj)
    if ctrl is None:
        return [], [], var
    n = max(8, int(getattr(obj, "samples", 64) or 64))
    pd = _spline_polyline(ctrl, n)
    if pd is None:
        return [], [], var
    from .information import probe_values
    pts = np.array([pd.GetPoint(i) for i in range(pd.GetNumberOfPoints())])
    seg = np.sqrt(np.sum(np.diff(pts, axis=0) ** 2, axis=1))
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    vals = []
    for i in range(len(pts)):
        vals.append(probe_values(ff, pts[i]).get(var, 0.0))
    return arc, np.asarray(vals, dtype=np.float64), var


def build_curve_actors(ff: FieldFile, obj) -> dict:
    """Curve line actor, coloured by the sampled variable (A1)."""
    if not getattr(obj, "show_curve", True):
        return {}
    ctrl = _curve_points(obj)
    if ctrl is None:
        return {}
    n = max(8, int(getattr(obj, "samples", 64) or 64))
    pd = _spline_polyline(ctrl, n)
    if pd is None:
        return {}
    var = (getattr(obj, "variable", "") or "").strip()
    mapper = vtk.vtkPolyDataMapper()
    if var:
        arc, vals, _ = sample_along_curve(ff, obj)
        arr = _vns.numpy_to_vtk(np.ascontiguousarray(vals), deep=True)
        arr.SetName("CurveScalar")
        pd.GetPointData().AddArray(arr)
        mapper.SetScalarModeToUsePointData()
        mapper.SelectColorArray("CurveScalar")
        mapper.SetScalarRange(float(vals.min()), float(vals.max()))
        mapper.ScalarVisibilityOn()
    else:
        mapper.ScalarVisibilityOff()
    mapper.SetInputData(pd)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    try:
        prop.SetColor(*getattr(obj, "color", (0.9, 0.2, 0.2)))
    except (TypeError, IndexError):
        prop.SetColor(0.9, 0.2, 0.2)
    prop.SetLineWidth(max(1, int(getattr(obj, "thickness", 2) or 2)))
    return {"curve": actor}
