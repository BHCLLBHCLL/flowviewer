"""Cylinder / Circle object rendering (scPOST, P2.1).

Cylinder cuts the volume grid with an implicit cylinder surface (with
optional half-height planes); Circle takes a plane cut and clips it to
a disk of the given radius.  Both map the contour scalar / vectors
exactly like the plane pipeline.
"""

from __future__ import annotations

import vtk

from ..model.dataset import FieldFile


def _prepare_vector(ff: FieldFile, obj, ugrid, cell_centered: bool):
    """Attach the object's vector to the grid as point data (R133d).

    Returns (grid, name); *name* is "" when the Vector tab is off or the field
    is incomplete (the shared resolver reports that).  Cell-centred input is
    converted with vtkCellDataToPointData so the cutter interpolates the
    vector onto the cut -- the plane pipeline does the same.
    """
    if not (getattr(obj, "show_vector", False)
            and getattr(obj, "vector_var", "")):
        return ugrid, ""
    from .plane import attach_vector
    vec = attach_vector(ugrid, ff, obj.vector_var, cell_centered)
    if vec is None:
        return ugrid, ""
    grid = ugrid
    if cell_centered:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(ugrid)
        c2p.PassCellDataOn()
        c2p.Update()
        grid = c2p.GetOutput()
    grid.GetPointData().SetActiveVectors(vec.GetName())
    return grid, vec.GetName()


def build_cylinder_actors(ff: FieldFile, obj) -> dict:
    """Cylinder-surface contour / vector / mesh actors."""
    out: dict = {}
    from .plane import (
        attach_scalar,
        build_ugrid,
        cell_filter_mask,
        contour_actor,
        mesh_lines_actor,
    )

    # R133d: this used to import plane.vector_actor (ugrid, ff, obj, cc) and
    # call it with three arguments, so enabling the Vector tab raised
    # TypeError; the cut-surface version is the one meant here.
    from .surface import vector_actor
    mask = cell_filter_mask(ff, obj)
    ugrid, cc = build_ugrid(ff, cell_mask=mask)
    if ugrid is None:
        return out
    var = getattr(obj, "contour_var", "") or ""
    if getattr(obj, "show_contour", True) and var and var in ff.variables:
        attach_scalar(ugrid, ff, var, cc)
    # R133d: the Vector tab never attached a field, so it always drew nothing.
    ugrid, vec_name = _prepare_vector(ff, obj, ugrid, cc)
    # transform the grid into cylinder-local coordinates
    t = vtk.vtkTransform()
    axis = (getattr(obj, "axis", "Z") or "Z").upper()
    if axis == "X":
        t.RotateY(90.0)
    elif axis == "Y":
        t.RotateX(-90.0)
    c = getattr(obj, "center", (0.0, 0.0, 0.0))
    t.Translate(float(c[0]), float(c[1]), float(c[2]))
    tf = vtk.vtkTransformFilter()
    tf.SetTransform(t)
    # R133d: carry every vector array (not just the active one) onto the cut
    tf.TransformAllInputVectorsOn()
    tf.SetInputData(ugrid)
    tf.Update()
    cyl = vtk.vtkCylinder()
    cyl.SetRadius(float(getattr(obj, "radius", 0.1) or 0.1))
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(cyl)
    cutter.SetInputConnection(tf.GetOutputPort())
    cutter.Update()
    cut = cutter.GetOutput()
    # half-height clip (two planes at +-h along the local Z)
    h = max(1e-6, float(getattr(obj, "height", 1.0) or 1.0))
    for sign in (1.0, -1.0):
        plane = vtk.vtkPlane()
        plane.SetOrigin(0.0, 0.0, sign * h)
        plane.SetNormal(0.0, 0.0, sign)
        clip = vtk.vtkClipPolyData()
        clip.SetInputData(cut)
        clip.SetClipFunction(plane)
        clip.InsideOutOn()
        clip.Update()
        cut = clip.GetOutput()
    if cut.GetNumberOfPoints() == 0:
        return out
    if getattr(obj, "show_contour", True) and var and var in ff.variables:
        a = contour_actor(cut, var, obj)
        if a is not None:
            out["contour"] = a
    if vec_name:
        # R133d: the cut carries the vector as point data under the name
        # attach_vector chose (the base name, even for a component request).
        if cut.GetPointData().GetArray(vec_name) is not None:
            cut.GetPointData().SetActiveVectors(vec_name)
        a = vector_actor(cut, obj, False)
        if a is not None:
            out["vector"] = a
    if getattr(obj, "show_mesh", True):
        out["mesh"] = mesh_lines_actor(cut, obj)
    return out


def build_circle_actors(ff: FieldFile, obj) -> dict:
    """Disk (plane cut clipped to the circle radius) actors."""
    out: dict = {}
    from .plane import (
        attach_scalar,
        build_ugrid,
        cell_filter_mask,
        contour_actor,
        mesh_lines_actor,
    )

    # R133d: same wrong import as the cylinder path -- see the note there.
    from .surface import vector_actor
    mask = cell_filter_mask(ff, obj)
    ugrid, cc = build_ugrid(ff, cell_mask=mask)
    if ugrid is None:
        return out
    var = getattr(obj, "contour_var", "") or ""
    if getattr(obj, "show_contour", True) and var and var in ff.variables:
        attach_scalar(ugrid, ff, var, cc)
    # R133d: the Vector tab never attached a field, so it always drew nothing.
    ugrid, vec_name = _prepare_vector(ff, obj, ugrid, cc)
    # move the grid so the circle lies in the local XY plane at the center
    t = vtk.vtkTransform()
    axis = (getattr(obj, "axis", "Z") or "Z").upper()
    if axis == "X":
        t.RotateY(90.0)
    elif axis == "Y":
        t.RotateX(-90.0)
    c = getattr(obj, "center", (0.0, 0.0, 0.0))
    coord = float(getattr(obj, "coordinate", 0.0) or 0.0)
    t.Translate(float(c[0]), float(c[1]), float(c[2]))
    t.Translate(0.0, 0.0, coord)
    tf = vtk.vtkTransformFilter()
    tf.SetTransform(t)
    # R133d: carry every vector array (not just the active one) onto the cut
    tf.TransformAllInputVectorsOn()
    tf.SetInputData(ugrid)
    tf.Update()
    plane = vtk.vtkPlane()
    plane.SetOrigin(0.0, 0.0, 0.0)
    plane.SetNormal(0.0, 0.0, 1.0)
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(plane)
    cutter.SetInputConnection(tf.GetOutputPort())
    cutter.Update()
    cut = cutter.GetOutput()
    # clip to the disk radius
    cyl = vtk.vtkCylinder()
    cyl.SetRadius(float(getattr(obj, "radius", 0.1) or 0.1))
    clip = vtk.vtkClipPolyData()
    clip.SetInputData(cut)
    clip.SetClipFunction(cyl)
    clip.InsideOutOn()
    clip.Update()
    cut = clip.GetOutput()
    if cut.GetNumberOfPoints() == 0:
        return out
    if getattr(obj, "show_contour", True) and var and var in ff.variables:
        a = contour_actor(cut, var, obj)
        if a is not None:
            out["contour"] = a
    if vec_name:
        # R133d: the cut carries the vector as point data under the name
        # attach_vector chose (the base name, even for a component request).
        if cut.GetPointData().GetArray(vec_name) is not None:
            cut.GetPointData().SetActiveVectors(vec_name)
        a = vector_actor(cut, obj, False)
        if a is not None:
            out["vector"] = a
    if getattr(obj, "show_mesh", True):
        out["mesh"] = mesh_lines_actor(cut, obj)
    return out
