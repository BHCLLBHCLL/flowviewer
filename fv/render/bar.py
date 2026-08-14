"""Bar object (scPOST Bar, A4) - variable along a two-point line."""

from __future__ import annotations

from typing import Optional

import numpy as np
import vtk
from vtk.util import numpy_support as _vns

from ..model.dataset import FieldFile


def sample_bar(ff: FieldFile, obj) -> tuple:
    """(t, values, var) along the bar (t in [0,1]) (A4)."""
    var = (getattr(obj, "variable", "") or "").strip()
    p1 = np.asarray(getattr(obj, "point1", (0.0, 0.0, 0.0)), dtype=np.float64)
    p2 = np.asarray(getattr(obj, "point2", (1.0, 0.0, 0.0)), dtype=np.float64)
    n = max(2, int(getattr(obj, "samples", 32) or 32))
    ts = np.linspace(0.0, 1.0, n)
    pts = p1[None, :] + ts[:, None] * (p2 - p1)[None, :]
    from .information import probe_values
    vals = np.array([probe_values(ff, pt).get(var, 0.0) for pt in pts])
    return ts, vals, var

def build_bar_actors(ff: FieldFile, obj) -> dict:
    """Bar line actor coloured by the sampled variable (A4)."""
    p1 = np.asarray(getattr(obj, "point1", (0.0, 0.0, 0.0)), dtype=np.float64)
    p2 = np.asarray(getattr(obj, "point2", (1.0, 0.0, 0.0)), dtype=np.float64)
    n = max(2, int(getattr(obj, "samples", 32) or 32))
    ts = np.linspace(0.0, 1.0, n)
    pts = p1[None, :] + ts[:, None] * (p2 - p1)[None, :]
    vpts = vtk.vtkPoints()
    for pt in pts:
        vpts.InsertNextPoint(float(pt[0]), float(pt[1]), float(pt[2]))
    line = vtk.vtkPolyLine()
    line.GetPointIds().SetNumberOfIds(n)
    for i in range(n):
        line.GetPointIds().SetId(i, i)
    cells = vtk.vtkCellArray()
    cells.InsertNextCell(line)
    pd = vtk.vtkPolyData()
    pd.SetPoints(vpts)
    pd.SetLines(cells)
    var = (getattr(obj, "variable", "") or "").strip()
    mapper = vtk.vtkPolyDataMapper()
    if var:
        _t, vals, _v = sample_bar(ff, obj)
        arr = _vns.numpy_to_vtk(np.ascontiguousarray(vals), deep=True)
        arr.SetName("BarScalar")
        pd.GetPointData().AddArray(arr)
        mapper.SetScalarModeToUsePointData()
        mapper.SelectColorArray("BarScalar")
        mapper.SetScalarRange(float(vals.min()), float(vals.max()))
        mapper.ScalarVisibilityOn()
    else:
        mapper.ScalarVisibilityOff()
    mapper.SetInputData(pd)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    try:
        actor.GetProperty().SetColor(*getattr(obj, "color", (0.2, 0.4, 0.9)))
    except (TypeError, IndexError):
        actor.GetProperty().SetColor(0.2, 0.4, 0.9)
    actor.GetProperty().SetLineWidth(max(1, int(getattr(obj, "thickness", 2) or 2)))
    return {"bar": actor}
