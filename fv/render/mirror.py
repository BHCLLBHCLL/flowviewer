"""Mirror Copy object (scPOST Mirror Copy, P2.6).

Re-renders the source SurfaceObject's boundary polydata reflected
across a coordinate plane, as a separate actor.
"""

from __future__ import annotations

from typing import Optional

import vtk

from ..model.dataset import FieldFile


def build_mirror_actors(ff: FieldFile, obj, siblings=None) -> dict:
    """Mirrored surface actor -> {'mirror': actor} (or {})."""
    if not siblings:
        return {}
    src = None
    for s in siblings:
        if (getattr(s, "kind", "") == "surface"
                and getattr(s, "label", "") == getattr(obj, "source_label", "")):
            src = s;
            break
    if src is None:
        return {}
    from .surface import build_surface_polydata
    pd, cc, _ = build_surface_polydata(ff, src)
    if pd is None or pd.GetNumberOfCells() == 0:
        return {}
    t = vtk.vtkTransform()
    plane = (getattr(obj, "mirror_plane", "YZ") or "YZ").upper()
    if plane == "YZ":
        t.Scale(-1.0, 1.0, 1.0)
    elif plane == "ZX":
        t.Scale(1.0, -1.0, 1.0)
    else:
        t.Scale(1.0, 1.0, -1.0)
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
        actor.GetProperty().SetColor(0.4, 0.4, 0.4);
    if getattr(obj, "transparent", False):
        actor.GetProperty().SetOpacity(0.5);
    return {"mirror": actor}