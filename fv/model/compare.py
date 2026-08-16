"""Quantitative comparison of two FieldFile datasets (R1.6).

``difference_field`` computes the |A−B| field for a shared variable together
with min/max/mean/rms statistics.  When the two datasets share a mesh the
difference is element-wise; otherwise ``b`` is mapped onto ``a``'s sampling
positions (node or cell centres) by nearest neighbour.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

import numpy as np

from .dataset import FIELD_KIND_SCALAR, FieldFile, VarInfo


def common_variables(a: FieldFile, b: FieldFile) -> list:
    """Sorted variable names present in both datasets."""
    return sorted(set(a.variables) & set(b.variables))


def _as_float(arr) -> np.ndarray:
    return np.asarray(arr, dtype=np.float64)


def _sample_points(ff: FieldFile, location: str) -> Optional[np.ndarray]:
    """Sampling coordinates for a node- or cell-located field."""
    if location == "node":
        if ff.vertices is None:
            return None
        return np.asarray(ff.vertices, dtype=np.float64)
    from ..api import cell_centers
    return cell_centers(ff)


def _map_nearest(src_vals, src_pts, dst_pts) -> np.ndarray:
    """Map ``src_vals`` (sampled at ``src_pts``) onto ``dst_pts``."""
    src_pts = np.asarray(src_pts, dtype=np.float64)
    dst_pts = np.asarray(dst_pts, dtype=np.float64)
    src_vals = np.asarray(src_vals, dtype=np.float64)
    try:
        from scipy.spatial import cKDTree
        _d, idx = cKDTree(src_pts).query(dst_pts, k=1)
        return src_vals[np.asarray(idx, dtype=np.int64)]
    except Exception:  # pragma: no cover - scipy missing; brute force
        out = np.empty(len(dst_pts), dtype=np.float64)
        for i, p in enumerate(dst_pts):
            out[i] = src_vals[int(np.argmin(np.linalg.norm(src_pts - p, axis=1)))]
        return out


def _stats(diff: np.ndarray) -> dict:
    valid = diff[np.isfinite(diff)]
    if valid.size == 0:
        return {"n": int(diff.size), "min": 0.0, "max": 0.0,
                "mean": 0.0, "rms": 0.0}
    return {
        "n": int(diff.size),
        "min": float(valid.min()),
        "max": float(valid.max()),
        "mean": float(valid.mean()),
        "rms": float(np.sqrt(np.mean(valid ** 2))),
    }


def difference_field(a: FieldFile, b: FieldFile, var: str) -> Optional[dict]:
    """Return ``{var, diff, location, n, min, max, mean, rms}`` or None.

    ``diff`` is the |A−B| array on ``a``'s mesh (same length as ``a``'s
    variable array), suitable for rendering as a scalar field.
    """
    aa = a.variable_array(var)
    bb = b.variable_array(var)
    if aa is None or bb is None:
        return None
    aa = _as_float(aa)
    bb = _as_float(bb)
    location = a.variables[var].location
    if aa.shape == bb.shape:
        diff = np.abs(aa - bb)
    else:
        a_pts = _sample_points(a, location)
        b_pts = _sample_points(b, location)
        if (a_pts is None or b_pts is None
                or len(a_pts) != len(aa) or len(b_pts) != len(bb)):
            return None
        diff = np.abs(aa - _map_nearest(bb, b_pts, a_pts))
    out = {"var": var, "diff": diff, "location": location}
    out.update(_stats(diff))
    return out


def compare_stats(a: FieldFile, b: FieldFile, var: str) -> Optional[dict]:
    """Statistics-only summary for one variable."""
    res = difference_field(a, b, var)
    if res is None:
        return None
    return {k: res[k] for k in ("var", "location", "n", "min", "max",
                                "mean", "rms")}


def compare_summary(a: FieldFile, b: FieldFile) -> dict:
    """``{var: stats}`` for every shared variable (R1.6)."""
    out = {}
    for var in common_variables(a, b):
        st = compare_stats(a, b, var)
        if st is not None:
            out[var] = st
    return out


def diff_field_file(a: FieldFile, var: str, diff: np.ndarray,
                    location: str) -> FieldFile:
    """Clone ``a`` carrying only the difference field as a scalar variable.

    Used by the GUI to render ``|A−B|`` as a normal coloured contour.
    """
    ff = replace(a)
    ff.path = str(a.path)
    ff.variables = {
        var: VarInfo(name=var, kind=FIELD_KIND_SCALAR, location=location,
                     array=np.asarray(diff, dtype=np.float64)),
    }
    return ff
