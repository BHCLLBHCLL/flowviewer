"""Mirror Copy object (scPOST Mirror Copy, P2.6).

Re-renders one or more source SurfaceObject boundary polydata reflected
across a coordinate plane, each as a separate actor (multi-source, 8).
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


def _mirror_polydata(pd, plane):
    t = vtk.vtkTransform()
    plane = (plane or "YZ").upper()
    if plane == "YZ":
        t.Scale(-1.0, 1.0, 1.0)
    elif plane == "ZX":
        t.Scale(1.0, -1.0, 1.0)
    else:
        t.Scale(1.0, 1.0, -1.0)
    tf = vtk.vtkTransformFilter()
    tf.SetTransform(t)
    tf.SetInputData(pd)
    tf.Update()
    return tf.GetOutput()


def build_mirror_actors(ff: FieldFile, obj, siblings=None) -> dict:
    """Mirrored surface actors -> {"mirror_0": actor, ...} (or {})."""
    sources = _find_sources(obj, siblings)
    if not sources:
        return {}
    from .surface import build_surface_polydata
    plane = getattr(obj, "mirror_plane", "YZ") or "YZ"
    out = {}
    for i, src in enumerate(sources):
        pd, cc, _ = build_surface_polydata(ff, src)
        if pd is None or pd.GetNumberOfCells() == 0:
            continue
        mirrored = _mirror_polydata(pd, plane)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(mirrored)
        mapper.SetScalarModeToUseCellData()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        try:
            actor.GetProperty().SetColor(*getattr(obj, "color", (0.4, 0.4, 0.4)))
        except (TypeError, IndexError):
            actor.GetProperty().SetColor(0.4, 0.4, 0.4)
        if getattr(obj, "transparent", False):
            actor.GetProperty().SetOpacity(0.5)
        key = "mirror" if len(sources) == 1 else "mirror_" + str(i)
        out[key] = actor
    return out
