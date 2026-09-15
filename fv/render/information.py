"""Information object (scPOST Information, P2.4) — point probe.

Queries every variable at a point and renders an optional marker.
FPH uses the nearest cell-centre value; FLD the nearest node value.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import vtk

from ..model.dataset import FieldFile


def probe_values(ff: FieldFile, point) -> dict:
    """All variable values at *point* -> {name: value} (P2.4, fixed in R118).

    The nearest VERTEX index was used for every array.  Cell-centred arrays are
    indexed by cell, not by vertex, so for those the lookup was meaningless --
    and because the guard is "len(a) > idx", a probe past the last cell index
    silently returned NOTHING (measured on tr03_9.fph: 11 variables at vertex
    10 and 50000, but 0 variables at vertex 200000, i.e. for two thirds of the
    model).  Each variable is now resolved in its own index space: node fields
    by nearest vertex, cell fields by nearest cell centre.
    """
    if ff.vertices is None:
        return {}
    verts = np.asarray(ff.vertices, dtype=np.float64)
    p = np.asarray(point, dtype=np.float64)

    def _nearest(points):
        if points is None or len(points) == 0:
            return None
        d = np.asarray(points, dtype=np.float64) - p
        return int(np.argmin(np.einsum("ij,ij->i", d, d)))

    node_idx = _nearest(verts)
    centres = None
    cell_idx = None
    out = {}
    for name, vi in ff.variables.items():
        a = vi.array
        if a is None:
            continue
        a = np.asarray(a, dtype=np.float64)
        if getattr(vi, "location", "cell") == "node":
            idx = node_idx
        else:
            if cell_idx is None:
                centres = _cell_centres(ff)
                cell_idx = _nearest(centres) if centres is not None else -1
            idx = cell_idx if cell_idx is not None and cell_idx >= 0 else None
        if idx is None:
            continue
        if a.ndim == 1:
            if len(a) > idx:
                out[name] = float(a[idx])
        elif a.ndim == 2 and a.shape[0] > idx:
            out[name] = tuple(float(v) for v in a[idx])
    return out


def _cell_centres(ff: FieldFile):
    """Cell centres in the same index space as the cell arrays (R118)."""
    try:
        if getattr(ff, "poly", False):
            from ..model.varreg import _cell_centers_fph

            return _cell_centers_fph(ff)
        conn = getattr(ff, "cell_conn", None)
        if conn is None:
            return None
        verts = np.asarray(ff.vertices, dtype=np.float64)
        off = 1 if (np.asarray(conn).min() > 0
                    and np.asarray(conn).max() >= len(verts)) else 0
        c = np.asarray(conn, dtype=np.int64) - off
        c = np.where(c >= 0, c, 0)
        return verts[c].mean(axis=1)
    except Exception:
        return None


def marker_actor(obj, bounds=None) -> Optional[vtk.vtkActor]:
    """Small sphere at the probe position.

    R0.7: the radius follows the model extent (0.5% of the bounds
    diagonal) so the marker stays visible at any model scale; the old
    fixed 0.002 vanished on large models.
    """
    if not getattr(obj, "show_marker", True):
        return None
    r = 0.002
    if bounds is not None:
        try:
            lo = np.asarray(bounds[0], dtype=np.float64)
            hi = np.asarray(bounds[1], dtype=np.float64)
            diag = float(np.linalg.norm(hi - lo))
            if diag > 0.0:
                r = 0.005 * diag
        except (TypeError, ValueError, IndexError):
            pass
    sphere = vtk.vtkSphereSource()
    sphere.SetRadius(r)
    pos = getattr(obj, "position", (0.0, 0.0, 0.0))
    sphere.SetCenter(float(pos[0]), float(pos[1]), float(pos[2]))
    sphere.SetThetaResolution(12); sphere.SetPhiResolution(12)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(sphere.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    try:
        actor.GetProperty().SetColor(*getattr(obj, "marker_color",
                                                (1.0, 0.0, 0.0)))
    except (TypeError, IndexError):
        actor.GetProperty().SetColor(1.0, 0.0, 0.0)
    return actor
