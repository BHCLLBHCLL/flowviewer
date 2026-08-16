"""Periodical Copy object (scPOST Periodical Copy, A2).

Reflects one or more source SurfaceObject boundary polydata into N-1
rotated copies about an axis (turbomachinery periodicity, multi-source 8).
"""

from __future__ import annotations

import vtk

from ..model.dataset import FieldFile


def _find_sources(obj, siblings):
    """All surface siblings selected by source_label / source_labels (8)."""
    labels = list(getattr(obj, "source_labels", []) or [])
    single = getattr(obj, "source_label", "")
    if single and single not in labels:
        labels.append(single)
    out = []
    for s in siblings or []:
        if getattr(s, "kind", "") != "surface":
            continue
        if getattr(s, "label", "") in labels:
            out.append(s)
    return out


def build_periodical_actors(ff: FieldFile, obj, siblings=None) -> dict:
    """Rotated copies -> {"0_copy1".."N_copyK": actor, ...} (A2)."""
    sources = _find_sources(obj, siblings)
    if not sources:
        return {}
    from .surface import build_surface_polydata
    from .mirror import _field_mapper, _source_scalar
    axis = (getattr(obj, "axis", "Z") or "Z").upper()
    d = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}[axis]
    ap = getattr(obj, "axis_point", (0.0, 0.0, 0.0))
    copies = max(2, int(getattr(obj, "copies", 6) or 6))
    out = {}
    for si, src in enumerate(sources):
        pd, cc, fi = build_surface_polydata(ff, src)
        if pd is None or pd.GetNumberOfCells() == 0:
            continue
        var = _source_scalar(ff, src, pd, cc, fi)
        for k in range(1, copies):
            angle = 360.0 * k / copies
            t = vtk.vtkTransform()
            t.Translate(float(ap[0]), float(ap[1]), float(ap[2]))
            t.RotateWXYZ(angle, *d)
            t.Translate(-float(ap[0]), -float(ap[1]), -float(ap[2]))
            tf = vtk.vtkTransformFilter()
            tf.SetTransform(t)
            tf.SetInputData(pd)
            tf.Update()
            mapper = vtk.vtkPolyDataMapper()
            mapper.SetInputConnection(tf.GetOutputPort())
            mapper.SetScalarModeToUseCellData()
            _field_mapper(mapper, tf.GetOutput(), var)
            actor = vtk.vtkActor()
            actor.SetMapper(mapper)
            if var is None:
                try:
                    actor.GetProperty().SetColor(
                        *getattr(obj, "color", (0.4, 0.4, 0.4)))
                except (TypeError, IndexError):
                    actor.GetProperty().SetColor(0.4, 0.4, 0.4)
            if getattr(obj, "transparent", False):
                actor.GetProperty().SetOpacity(0.5)
            prefix = str(si) + "_" if len(sources) > 1 else ""
            out[prefix + "copy" + str(k)] = actor
    return out
