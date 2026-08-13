"""Cylinder / Circle object rendering (scPOST, P2.1).

Cylinder cuts the volume grid with an implicit cylinder surface (with
optional half-height planes); Circle takes a plane cut and clips it to
a disk of the given radius.  Both map the contour scalar / vectors
exactly like the plane pipeline.
"""

from __future__ import annotations

import numpy as np
import vtk

from ..model.dataset import FieldFile


def build_cylinder_actors(ff: FieldFile, obj) -> dict:
    """Cylinder-surface contour / vector / mesh actors."""
    out: dict = {}
    from .plane import (attach_scalar, build_ugrid, cell_filter_mask,
                      contour_actor, mesh_lines_actor, vector_actor)
    mask = cell_filter_mask(ff, obj)
    ugrid, cc = build_ugrid(ff, cell_mask=mask)
    if ugrid is None:
        return out
    var = getattr(obj, "contour_var", "") or ""
    if getattr(obj, "show_contour", True) and var and var in ff.variables:
        attach_scalar(ugrid, ff, var, cc)
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
    if getattr(obj, "show_vector", False) and getattr(obj, "vector_var", ""):
        a = vector_actor(cut, obj, cc)
        if a is not None:
            out["vector"] = a
    if getattr(obj, "show_mesh", True):
        out["mesh"] = mesh_lines_actor(cut, obj)
    return out


def build_circle_actors(ff: FieldFile, obj) -> dict:
    """Disk (plane cut clipped to the circle radius) actors."""
    out: dict = {}
    from .plane import (attach_scalar, build_ugrid, cell_filter_mask,
                      contour_actor, mesh_lines_actor, plane_from_object,
                      vector_actor)
    mask = cell_filter_mask(ff, obj)
    ugrid, cc = build_ugrid(ff, cell_mask=mask)
    if ugrid is None:
        return out
    var = getattr(obj, "contour_var", "") or ""
    if getattr(obj, "show_contour", True) and var and var in ff.variables:
        attach_scalar(ugrid, ff, var, cc)
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
    if getattr(obj, "show_vector", False) and getattr(obj, "vector_var", ""):
        a = vector_actor(cut, obj, cc)
        if a is not None:
            out["vector"] = a
    if getattr(obj, "show_mesh", True):
        out["mesh"] = mesh_lines_actor(cut, obj)
    return out