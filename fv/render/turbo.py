"""Turbo views (scPOST Turbo, 7a) - meridional + blade-to-blade transforms.

Meridional maps (x,y,z) to (r, z) about the rotation axis; Blade-to-Blade
unwraps points near a radius to (r*theta, z).  Both return 2D point sets
rendered as scatter actors.
"""

from __future__ import annotations

import numpy as np
import vtk
from vtk.util import numpy_support as _vns


def meridional_points(ff, axis="Z"):
    """(r, z) coordinates of all vertices about the axis (7a)."""
    v = np.asarray(ff.vertices, dtype=np.float64)
    if axis.upper() == "X":
        r = np.sqrt(v[:, 1] ** 2 + v[:, 2] ** 2)
        z = v[:, 0]
    elif axis.upper() == "Y":
        r = np.sqrt(v[:, 0] ** 2 + v[:, 2] ** 2)
        z = v[:, 1]
    else:
        r = np.sqrt(v[:, 0] ** 2 + v[:, 1] ** 2)
        z = v[:, 2]
    return np.column_stack([r, z])

def blade_to_blade_points(ff, radius, axis="Z", tol=0.005):
    """(r*theta, z) points near *radius* (7a)."""
    v = np.asarray(ff.vertices, dtype=np.float64)
    if axis.upper() == "X":
        r = np.sqrt(v[:, 1] ** 2 + v[:, 2] ** 2)
        th = np.arctan2(v[:, 2], v[:, 1])
        z = v[:, 0]
    elif axis.upper() == "Y":
        r = np.sqrt(v[:, 0] ** 2 + v[:, 2] ** 2)
        th = np.arctan2(v[:, 0], v[:, 2])
        z = v[:, 1]
    else:
        r = np.sqrt(v[:, 0] ** 2 + v[:, 1] ** 2)
        th = np.arctan2(v[:, 1], v[:, 0])
        z = v[:, 2]
    mask = np.abs(r - radius) < tol
    return np.column_stack([(r * th)[mask], z[mask]])


def build_turbo_actors(ff, obj):
    """2D scatter actor for the selected turbo view (7a)."""
    view = (getattr(obj, "view", "Meridional") or "Meridional")
    if view.lower().startswith("blade"):
        pts = blade_to_blade_points(ff, getattr(obj, "radius", 0.05),
                                    getattr(obj, "axis", "Z"),
                                    getattr(obj, "tolerance", 0.005))
    else:
        pts = meridional_points(ff, getattr(obj, "axis", "Z"))
    if pts.shape[0] == 0:
        return {}
    pts3 = np.column_stack([pts[:, 0], pts[:, 1], np.zeros(pts.shape[0])])
    vpts = vtk.vtkPoints()
    vpts.SetData(_vns.numpy_to_vtk(np.ascontiguousarray(pts3), deep=True))
    pd = vtk.vtkPolyData()
    pd.SetPoints(vpts)
    glyph = vtk.vtkVertexGlyphFilter()
    glyph.SetInputData(pd)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(glyph.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetPointSize(2)
    actor.GetProperty().SetColor(0.2, 0.2, 0.8)
    return {"turbo": actor}
