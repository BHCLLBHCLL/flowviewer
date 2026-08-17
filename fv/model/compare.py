"""Quantitative comparison of two FieldFile datasets (R1.6).

``difference_field`` computes A−B (or |A−B| / relative) for a shared
variable together with min/max/mean/rms statistics.  When the two
datasets share a mesh the difference is element-wise; otherwise ``b`` is
mapped onto ``a``'s sampling positions by nearest neighbour or inverse-
distance weighting (``mapping='idw'``).
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


def _map_idw(src_vals, src_pts, dst_pts, k: int = 4, power: float = 2.0) -> np.ndarray:
    """Inverse-distance weighted map of ``src_vals`` onto ``dst_pts``."""
    src_pts = np.asarray(src_pts, dtype=np.float64)
    dst_pts = np.asarray(dst_pts, dtype=np.float64)
    src_vals = np.asarray(src_vals, dtype=np.float64)
    nsrc = max(1, len(src_pts))
    kk = max(1, min(int(k), nsrc))
    try:
        from scipy.spatial import cKDTree
        dist, idx = cKDTree(src_pts).query(dst_pts, k=kk)
    except Exception:  # pragma: no cover
        return _map_nearest(src_vals, src_pts, dst_pts)
    idx = np.asarray(idx, dtype=np.int64)
    dist = np.asarray(dist, dtype=np.float64)
    if kk == 1:
        dist = dist.reshape(-1, 1)
        idx = idx.reshape(-1, 1)
    exact = dist[:, 0] <= 1e-15
    dist = np.maximum(dist, 1e-15)
    w = 1.0 / np.power(dist, float(power))
    wsum = w.sum(axis=1)
    mapped = (w * src_vals[idx]).sum(axis=1) / np.maximum(wsum, 1e-30)
    mapped[exact] = src_vals[idx[exact, 0]]
    return mapped


def _combine(aa, bb, mode: str) -> np.ndarray:
    """Combine two aligned arrays: abs | signed | relative."""
    signed = aa - bb
    key = (mode or "abs").lower()
    if key in ("signed", "a-b", "diff"):
        return signed
    if key in ("relative", "rel", "pct"):
        return signed / (np.abs(aa) + 1e-30)
    return np.abs(signed)


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


def difference_field(a: FieldFile, b: FieldFile, var: str,
                     mode: str = "abs", mapping: str = "nearest") -> Optional[dict]:
    """Return ``{var, diff, location, n, min, max, mean, rms}`` or None.

    ``diff`` is the difference array on ``a``'s mesh (same length as ``a``'s
    variable array), suitable for rendering as a scalar field.

    ``mode``: ``abs`` (|A−B|, default), ``signed`` (A−B), ``relative``
    ((A−B)/(|A|+eps)).  ``mapping``: ``nearest`` or ``idw`` when the meshes
    do not share a shape.
    """
    aa = a.variable_array(var)
    bb = b.variable_array(var)
    if aa is None or bb is None:
        return None
    aa = _as_float(aa)
    bb = _as_float(bb)
    location = a.variables[var].location
    if aa.shape == bb.shape:
        mapped = bb
    else:
        a_pts = _sample_points(a, location)
        b_pts = _sample_points(b, location)
        if (a_pts is None or b_pts is None
                or len(a_pts) != len(aa) or len(b_pts) != len(bb)):
            return None
        mapper = _map_idw if str(mapping).lower() == "idw" else _map_nearest
        mapped = mapper(bb, b_pts, a_pts)
    diff = _combine(aa, mapped, mode)
    out = {"var": var, "diff": diff, "location": location,
           "mode": (mode or "abs").lower(),
           "mapping": "idw" if aa.shape != bb.shape and str(mapping).lower() == "idw"
           else "nearest"}
    out.update(_stats(diff))
    return out


def compare_stats(a: FieldFile, b: FieldFile, var: str,
                  mode: str = "abs", mapping: str = "nearest") -> Optional[dict]:
    """Statistics-only summary for one variable."""
    res = difference_field(a, b, var, mode=mode, mapping=mapping)
    if res is None:
        return None
    return {k: res[k] for k in ("var", "location", "n", "min", "max",
                                "mean", "rms") if k in res}


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
