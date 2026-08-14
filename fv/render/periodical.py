"""Periodical Copy object (scPOST Periodical Copy, A2).

Reflects the source SurfaceObject's boundary polydata into N-1 rotated
copies about an axis (turbomachinery periodicity).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import vtk

from ..model.dataset import FieldFile


def _find_source(ff, obj, siblings):
    for s in siblings or []:
        if (getattr(s, "kind", "") == "surface"
                and getattr(s, "label", "") == getattr(obj, "source_label", "")):
            return s
    return None


def build_periodical_actors(ff: FieldFile, obj, siblings=None) -> dict:
    """Rotated copies -> copy1..copyN actors (A2)."""
    src = _find_source(ff, obj, siblings)
    if src is None:
        return {}
    from .surface import build_surface_polydata
    pd, cc, _ = build_surface_polydata(ff, src)
    if pd is None or pd.GetNumberOfCells() == 0:
        return {}
    axis = (getattr(obj, "axis", "Z") or "Z").upper()
    d = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}[axis]
    ap = getattr(obj, "axis_point", (0.0, 0.0, 0.0))
    copies = max(2, int(getattr(obj, "copies", 6) or 6))
    out = {}
    for k in range(1, copies):
        angle = 360.0 * k / copies
        t = vtk.vtkTransform()
        t.Translate(float(ap[0]), float(ap[1]), float(ap[2]))
        t.RotateWXYZ(angle, *d)
        t.Translate(-float(ap[0]), -float(ap[1]), -float(ap[2]))
        tf = vtk.vtkTransformFilter();
        tf.SetTransform(t);
        tf.SetInputData(pd);
        tf.Update()
        mapper = vtk.vtkPolyDataMapper();
        mapper.SetInputConnection(tf.GetOutputPort());
        mapper.SetScalarModeToUseCellData()
        actor = vtk.vtkActor();
        actor.SetMapper(mapper)
        try:
            actor.GetProperty().SetColor(*getattr(obj, "color", (0.4, 0.4, 0.4)));
        except (TypeError, IndexError):
            actor.GetProperty().SetColor(0.4, 0.4, 0.4)
        if getattr(obj, "transparent", False):
            actor.GetProperty().SetOpacity(0.5)
        out["copy" + str(k)] = actor
    return out