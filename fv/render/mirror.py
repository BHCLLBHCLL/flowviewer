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


def _source_scalar(ff, src, pd, cell_centered, face_idx):
    """Attach the source surface's contour field; return its name (R0.5).

    The mirror inherits the source's displayed variable so the copy is
    painted with the same scalar map (and the shared colorbar LUT).
    """
    var = getattr(src, "contour_var", "") or ""
    if not getattr(src, "show_contour", False) or not var:
        return None
    if cell_centered and face_idx is None:
        return None
    from .surface import attach_scalar
    if attach_scalar(ff, pd, face_idx, var, cell_centered) is None:
        return None
    return var


def _field_mapper(mapper, pd, var):
    """Configure a mapper like the source contour actor (R0.5)."""
    if not var:
        return
    from .surface import _data_range
    if pd.GetPointData().GetArray(var) is not None:
        mapper.SetScalarModeToUsePointData()
    else:
        mapper.SetScalarModeToUseCellData()
    mapper.SelectColorArray(var)
    mapper.SetScalarRange(_data_range(pd, var))


def build_mirror_actors(ff: FieldFile, obj, siblings=None) -> dict:
    """Mirrored surface actors -> {"mirror_0": actor, ...} (or {})."""
    sources = _find_sources(obj, siblings)
    if not sources:
        return {}
    from .surface import build_surface_polydata
    plane = getattr(obj, "mirror_plane", "YZ") or "YZ"
    out = {}
    for i, src in enumerate(sources):
        pd, cc, fi = build_surface_polydata(ff, src)
        if pd is None or pd.GetNumberOfCells() == 0:
            continue
        var = _source_scalar(ff, src, pd, cc, fi)
        mirrored = _mirror_polydata(pd, plane)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(mirrored)
        mapper.SetScalarModeToUseCellData()
        _field_mapper(mapper, mirrored, var)
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
        key = "mirror" if len(sources) == 1 else "mirror_" + str(i)
        out[key] = actor
    return out
