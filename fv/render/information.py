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
    """All variable values at *point* -> {name: value} (P2.4)."""
    if ff.vertices is None:
        return {}
    verts = np.asarray(ff.vertices, dtype=np.float64)
    p = np.asarray(point, dtype=np.float64)
    d = verts - p
    idx = int(np.argmin(np.einsum("ij,ij->i", d, d)))
    out = {}
    for name, vi in ff.variables.items():
        a = vi.array
        if a is None:
            continue
        a = np.asarray(a, dtype=np.float64)
        if a.ndim == 1:
            if len(a) > idx:
                out[name] = float(a[idx])
        elif a.ndim == 2 and a.shape[0] > idx:
            out[name] = tuple(float(v) for v in a[idx])
    return out


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
