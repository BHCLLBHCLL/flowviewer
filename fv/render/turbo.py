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


def circumferential_average(ff, var, axis="Z", n_r=64, n_z=64):
    """Circumferential (theta) average of a field onto the (r, z) plane.

    Bins vertices by radius and axial coordinate, averaging *var* over the
    circumferential direction - the standard turbomachinery meridional view.
    Returns (r_centers, z_centers, values) where values is (n_r, n_z).
    """
    a = ff.variable_array(var)
    if a is None:
        return None, None, None
    a = np.asarray(a, dtype=np.float64)
    v = np.asarray(ff.vertices, dtype=np.float64)
    if len(a) != len(v):
        # cell-centred field: use cell centres
        try:
            from ..model.varreg import _cell_centers_fph
            v = _cell_centers_fph(ff)
            if v is None or v.shape[0] != len(a):
                return None, None, None
        except Exception:
            return None, None, None
    if axis.upper() == "X":
        r = np.sqrt(v[:, 1] ** 2 + v[:, 2] ** 2); z = v[:, 0]
    elif axis.upper() == "Y":
        r = np.sqrt(v[:, 0] ** 2 + v[:, 2] ** 2); z = v[:, 1]
    else:
        r = np.sqrt(v[:, 0] ** 2 + v[:, 1] ** 2); z = v[:, 2]
    r_min, r_max = r.min(), r.max()
    z_min, z_max = z.min(), z.max()
    r_edges = np.linspace(r_min, r_max, n_r + 1)
    z_edges = np.linspace(z_min, z_max, n_z + 1)
    ri = np.clip(np.digitize(r, r_edges) - 1, 0, n_r - 1)
    zi = np.clip(np.digitize(z, z_edges) - 1, 0, n_z - 1)
    acc = np.zeros((n_r, n_z))
    cnt = np.zeros((n_r, n_z))
    np.add.at(acc, (ri, zi), a)
    np.add.at(cnt, (ri, zi), 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        values = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    r_c = 0.5 * (r_edges[:-1] + r_edges[1:])
    z_c = 0.5 * (z_edges[:-1] + z_edges[1:])
    return r_c, z_c, values


def blade_loading_curve(ff, var, axis="Z", n_span=32):
    """Pressure-side vs suction-side value difference along the span.

    Approximates the two blade surfaces by the max/min field value in each
    spanwise bin; returns (span, dp) where dp = max - min (loading).
    """
    v = np.asarray(ff.vertices, dtype=np.float64)
    a = ff.variable_array(var)
    if a is None or len(a) != len(v):
        try:
            from ..model.varreg import _cell_centers_fph
            cc = _cell_centers_fph(ff)
            if cc is None or cc.shape[0] != len(a):
                return None, None
            v = cc
        except Exception:
            return None, None
    a = np.asarray(a, dtype=np.float64)
    if axis.upper() == "X":
        span = v[:, 0]
    elif axis.upper() == "Y":
        span = v[:, 1]
    else:
        span = v[:, 2]
    edges = np.linspace(span.min(), span.max(), n_span + 1)
    idx = np.clip(np.digitize(span, edges) - 1, 0, n_span - 1)
    pmin = np.full(n_span, np.inf)
    pmax = np.full(n_span, -np.inf)
    np.minimum.at(pmin, idx, a)
    np.maximum.at(pmax, idx, a)
    valid = np.isfinite(pmin) & np.isfinite(pmax)
    sc = 0.5 * (edges[:-1] + edges[1:])
    return sc, np.where(valid, pmax - pmin, 0.0)


def polar_view_points(ff, axis="Z"):
    """(r, theta) polar coordinates of all vertices (7a deepening)."""
    v = np.asarray(ff.vertices, dtype=np.float64)
    if axis.upper() == "X":
        r = np.sqrt(v[:, 1] ** 2 + v[:, 2] ** 2); th = np.arctan2(v[:, 2], v[:, 1])
    elif axis.upper() == "Y":
        r = np.sqrt(v[:, 0] ** 2 + v[:, 2] ** 2); th = np.arctan2(v[:, 0], v[:, 2])
    else:
        r = np.sqrt(v[:, 0] ** 2 + v[:, 1] ** 2); th = np.arctan2(v[:, 1], v[:, 0])
    return np.column_stack([r, th])
