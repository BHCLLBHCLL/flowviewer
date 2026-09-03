"""R37: probe-grid memoization + generic local polydata value extraction.

Two layers:

* ``get_probe_grid(ff)`` — a bounded, memoized ``plane.build_ugrid`` shared by
  the probe entry points (Point objects, Information, left-click picking), so a
  dataset is converted to its working grid **once** instead of again on every
  event (a real first-frame / repeated-interaction win on large meshes,
  mirroring R26's plane-cut cache).  It returns the same ``(ugrid,
  cell_centered)`` pair the caller already gets from ``build_ugrid``.

* ``probe_polydata(pd, query)`` — a dependency-light *data cursor*: local value
  extraction from **any rendered polydata** (cut plane, isosurface, particle
  cloud, pathline …), returning ``{name: (kind, value)}`` for the nearest
  point and nearest cell, plus the query/nearest coordinates.  Nearest lookup
  is pure NumPy (``einsum``), so the whole module is unit-testable headless
  and never touches ``vtkCutter``.

``probe_summary`` formats a compact ``name=value …`` line for the status-bar
data cursor.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Tuple

import numpy as np

try:
    from vtk.util import numpy_support
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False

from .plane import attach_scalar, attach_vector, build_ugrid

# ── probe-grid memo (bounded) ─────────────────────────────────────────────

_PROBE_GRID_CACHE: "OrderedDict[int, tuple]" = OrderedDict()
_PROBE_GRID_MAX = 4


def get_probe_grid(ff):
    """Memoized ``build_ugrid(ff)`` keyed by dataset identity.

    Returns the same ``(ugrid, cell_centered)`` pair as ``build_ugrid`` but
    only builds it the first time a given ``FieldFile`` is seen (a fresh
    :class:`~fv.model.dataset.FieldFile` object → new id → rebuilt, which is
    exactly the reload boundary).  The cache is a tiny LRU so memory stays
    bounded.
    """
    key = id(ff)
    cache = _PROBE_GRID_CACHE
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    grid = build_ugrid(ff)
    cache[key] = grid
    while len(cache) > _PROBE_GRID_MAX:
        cache.popitem(last=False)
    return grid


def reset_probe_grid() -> None:
    """Drop the memo (used by tests and on dataset teardown)."""
    _PROBE_GRID_CACHE.clear()


# ── arrays of a polydata ──────────────────────────────────────────────────

def _ndim_kind(a: np.ndarray) -> str:
    return "vector" if a.ndim == 2 else "scalar"


def from_polydata(pd) -> Tuple[np.ndarray, dict, dict]:
    """Dig ``(points, point_arrays, cell_arrays)`` out of a polydata.

    ``pd`` may be a ``vtkPolyData`` (read point/cell data arrays via VTK) or a
    plain tuple ``(pts, point_arrays, cell_arrays)`` for dependency-lite use.
    Array values are returned as NumPy arrays; each entry is
    ``name -> (ndarray, kind)`` (kind = scalar/vector, by ``ndim``).
    ``points`` is always an ``(N, 3)`` float64 array.
    """
    if isinstance(pd, tuple):
        # dependency-lite form: points + {name:(ndarray, kind)} + cell_arrays
        pts, parrs, carrs = pd
        return (np.asarray(pts, dtype=np.float64), dict(parrs), dict(carrs))
    if not _HAS_VTK or not hasattr(pd, "GetPoints"):
        return (np.zeros((0, 3)), {}, {})

    pts = pd.GetPoints()
    points = (np.zeros((0, 3), dtype=np.float64) if pts is None
              else numpy_support.vtk_to_numpy(pts.GetData()).astype(np.float64)
              )
    parrs: dict = {}
    pdata = pd.GetPointData()
    for i in range(pdata.GetNumberOfArrays()):
        name = pdata.GetArrayName(i)
        if name:
            a = numpy_support.vtk_to_numpy(pdata.GetArray(i))
            parrs[name] = (a, _ndim_kind(a))
    return points, parrs, {}


def nearest_point(pts: np.ndarray, query) -> Tuple[int, float]:
    """Nearest node index + squared distance (pure NumPy)."""
    d = np.asarray(pts, dtype=np.float64) - np.asarray(query, dtype=np.float64)
    sq = np.einsum("ij,ij->i", d, d)
    if sq.size == 0:
        return -1, float("+inf")
    idx = int(np.argmin(sq))
    return idx, float(sq[idx])


def probe_polydata(pd, query) -> dict:
    """Local value extraction from any polydata (data cursor).

    Returns ``{"point": (idx, [x,y,z]), "nearest": merged point+cell values}``.
    Only arrays whose length matches ``points`` (point data) are mapped; every
    mapping is ``{name: (kind, value_or_tuple)}``.  Empty/protected inputs yield
    an empty ``"nearest"`` dict.
    """
    points, parrs, _carrs = from_polydata(pd)
    out: dict = {"query": tuple(float(x) for x in query)}
    if points.shape[0] == 0:
        out["nearest"] = {}
        return out
    idx, _dist = nearest_point(points, query)
    out["point"] = (idx, tuple(float(v) for v in points[idx]))
    merged: dict = {}
    for name, (a, kind) in parrs.items():
        a = np.asarray(a)
        if a.ndim == 1 and a.shape[0] <= idx:
            continue
        if a.ndim == 2 and a.shape[0] <= idx:
            continue
        if a.ndim == 1:
            merged[name] = (kind, float(a[idx]))
        elif a.ndim == 2:
            merged[name] = (kind, tuple(float(v) for v in a[idx]))
    out["nearest"] = merged
    return out


def probe_summary(result: dict) -> str:
    """Compact ``"name=value …"`` status line for a data cursor result."""
    nearest = result.get("nearest") or {}
    parts = []
    pt = result.get("point")
    if pt:
        _idx, coords = pt
        parts.append("xyz=" + ",".join(f"{v:.4g}" for v in coords))
    for name, (kind, value) in sorted(nearest.items()):
        if kind == "vector":
            parts.append(f"{name}=(" +
                         ",".join(f"{v:.4g}" for v in value) + ")")
        else:
            parts.append(f"{name}={float(value):.4g}")
    return " | ".join(parts) if parts else "(no data)"


# ── attach helper reuse for probes ─────────────────────────────────────────

def attach_probe_arrays(ugrid, ff, scalar_var: str, vector_var: str,
                        cell_centered: bool) -> None:
    """Attach named scalar/vector arrays to a grid for probing (best-effort)."""
    if scalar_var:
        attach_scalar(ugrid, ff, scalar_var, cell_centered)
    if vector_var:
        attach_vector(ugrid, ff, vector_var, cell_centered)
