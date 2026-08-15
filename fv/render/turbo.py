"""Turbo views (scPOST Turbo, 7a) - meridional + blade-to-blade transforms.

Meridional maps (x,y,z) to (r, z) about the rotation axis; Blade-to-Blade
unwraps points near a radius to (r*theta, z).  Both return 2D point sets
rendered as scatter actors.
"""

from __future__ import annotations

import numpy as np


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
    import vtk
    from vtk.util import numpy_support as _vns
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


# ── blade aerodynamics post-processing (item 5) ────────────────────────

def _field_coords(ff, a):
    """Coordinates matching a field array length (vertices or cell centres)."""
    a = np.asarray(a, dtype=np.float64)
    v = np.asarray(ff.vertices, dtype=np.float64)
    if len(a) == len(v):
        return v
    try:
        from ..model.varreg import _cell_centers_fph
        c = _cell_centers_fph(ff)
        if c is not None and c.shape[0] == len(a):
            return c
    except Exception:
        pass
    return None


def _density_array(ff):
    """Density field for mass weighting, or None when absent."""
    for name in ("DENS", "RHO", "DENSITY", "Density"):
        a = ff.variable_array(name)
        if a is not None and np.asarray(a).ndim == 1:
            return np.asarray(a, dtype=np.float64)
    return None


def _velocity_magnitude(ff):
    """Speed |V| from VELX/VELY/VELZ or a 3-component VECT field."""
    vx = ff.variable_array("VELX")
    vy = ff.variable_array("VELY")
    vz = ff.variable_array("VELZ")
    if vx is not None and vy is not None and vz is not None:
        return np.sqrt(np.asarray(vx) ** 2 + np.asarray(vy) ** 2
                       + np.asarray(vz) ** 2)
    vt = ff.variable_array("VECT")
    if vt is not None:
        vt = np.asarray(vt)
        if vt.ndim == 2 and vt.shape[1] == 3:
            return np.linalg.norm(vt, axis=1)
    return None


def _axial_velocity(ff, axis):
    """Axial velocity component for a rotation axis (X/Y/Z)."""
    comp = {"X": "VELX", "Y": "VELY", "Z": "VELZ"}.get(axis.upper())
    if comp is None:
        return None
    a = ff.variable_array(comp)
    return np.asarray(a, dtype=np.float64) if a is not None else None


def pressure_coefficient(ff, p_ref, v_ref=1.0, rho=1.0):
    """Pressure coefficient Cp = (p - p_ref) / (0.5 rho v_ref^2)."""
    p = ff.variable_array("PRES")
    if p is None:
        p = ff.variable_array("Pressure")
    if p is None:
        return None
    p = np.asarray(p, dtype=np.float64)
    denom = 0.5 * float(rho) * float(v_ref) ** 2
    if abs(denom) < 1e-12:
        denom = 1.0
    return (p - float(p_ref)) / denom


def area_average(ff, var, axis="Z", n_bins=64):
    """Average of *var* in bins along the rotation axis (meridional).

    Falls back to arithmetic binning when no face-area metric is available.
    Returns (axis_centres, values).
    """
    a = ff.variable_array(var)
    if a is None or np.asarray(a).ndim != 1:
        return None, None
    a = np.asarray(a, dtype=np.float64)
    v = _field_coords(ff, a)
    if v is None:
        return None, None
    coord = v[:, {"X": 0, "Y": 1, "Z": 2}[axis.upper()]]
    lo, hi = float(coord.min()), float(coord.max())
    edges = np.linspace(lo, hi, n_bins + 1)
    idx = np.clip(np.digitize(coord, edges) - 1, 0, n_bins - 1)
    acc = np.zeros(n_bins)
    cnt = np.zeros(n_bins)
    np.add.at(acc, idx, a)
    np.add.at(cnt, idx, 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        vals = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)
    centres = 0.5 * (edges[:-1] + edges[1:])
    return centres, vals


def mass_flow_average(ff, var, axis="Z"):
    """Mass-flow weighted average = Σ(rho |V_ax| var) / Σ(rho |V_ax|).

    Uses the density field when present (rho = 1 otherwise), so it degrades
    to an axial-speed weighted average on incompressible data.
    """
    a = ff.variable_array(var)
    if a is None or np.asarray(a).ndim != 1:
        return None
    a = np.asarray(a, dtype=np.float64)
    vax = _axial_velocity(ff, axis)
    w = np.ones(len(a))
    if vax is not None and len(vax) == len(a):
        w = np.abs(vax)
    rho = _density_array(ff)
    if rho is not None and len(rho) == len(a):
        w = w * rho
    s = float(w.sum())
    if s < 1e-12:
        return float(np.mean(a))
    return float((a * w).sum() / s)


def circumferential_mass_average(ff, var, axis="Z", n_r=64, n_z=64):
    """Circumferential mass-flow-weighted average onto the (r, z) plane.

    Like circumferential_average but weights each sample by rho |V| (the
    mass-flux weighting used for meridional turbomachinery views).
    Returns (r_centres, z_centres, values).
    """
    a = ff.variable_array(var)
    if a is None or np.asarray(a).ndim != 1:
        return None, None, None
    a = np.asarray(a, dtype=np.float64)
    v = _field_coords(ff, a)
    if v is None:
        return None, None, None
    vmag = _velocity_magnitude(ff)
    w = np.ones(len(a)) if vmag is None or len(vmag) != len(a) else np.abs(vmag)
    rho = _density_array(ff)
    if rho is not None and len(rho) == len(a):
        w = w * rho
    ax = axis.upper()
    if ax == "X":
        r = np.sqrt(v[:, 1] ** 2 + v[:, 2] ** 2); z = v[:, 0]
    elif ax == "Y":
        r = np.sqrt(v[:, 0] ** 2 + v[:, 2] ** 2); z = v[:, 1]
    else:
        r = np.sqrt(v[:, 0] ** 2 + v[:, 1] ** 2); z = v[:, 2]
    r_edges = np.linspace(r.min(), r.max(), n_r + 1)
    z_edges = np.linspace(z.min(), z.max(), n_z + 1)
    ri = np.clip(np.digitize(r, r_edges) - 1, 0, n_r - 1)
    zi = np.clip(np.digitize(z, z_edges) - 1, 0, n_z - 1)
    acc = np.zeros((n_r, n_z))
    wsum = np.zeros((n_r, n_z))
    np.add.at(acc, (ri, zi), a * w)
    np.add.at(wsum, (ri, zi), w)
    with np.errstate(invalid="ignore", divide="ignore"):
        vals = np.where(wsum > 0, acc / np.maximum(wsum, 1e-12), np.nan)
    return 0.5 * (r_edges[:-1] + r_edges[1:]), 0.5 * (z_edges[:-1] + z_edges[1:]), vals