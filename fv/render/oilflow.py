"""Oil Flow: surface streamlines traced from a cut-plane seed grid.

scPOST Plane → Oil Flow traces the velocity field from a grid of seed points
on the cut plane, rendering each streamline as a line/tube with configurable
length, density and integration method.

Seeds are placed on the plane using ``oilflow_space_u/v``; the field is
converted to point data (``vtkCellDataToPointData``) and traced through the
volume grid with ``vtkStreamTracer``.
"""

from typing import Optional

import numpy as np

try:
    import vtk
    from vtk.util import numpy_support as _vns
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    _vns = None

from ..model.dataset import FieldFile
from ..render.plane import attach_vector


def build_oilflow_actor(ff: FieldFile, obj, ugrid=None,
                        cell_centered: bool = True,
                        rows=None) -> Optional["vtk.vtkActor"]:
    """Oil Flow actor: streamlines traced from cut-plane seed points.

    ``obj.oilflow_display`` gates the actor; ``obj.oilflow_var`` names the
    vector base (``X/Y/Z``). Returns ``None`` when disabled or data missing.
    """
    if not _HAS_VTK:
        return None
    if not getattr(obj, "oilflow_display", False):
        return None
    base = getattr(obj, "oilflow_var", "") or ""
    if not base:
        return None
    if ugrid is None:
        from ..render.plane import build_ugrid
        ugrid, cell_centered = build_ugrid(ff, cell_mask=None)
    if ugrid is None:
        return None

    vec = attach_vector(ugrid, ff, base, cell_centered, rows=rows)
    if vec is None:
        return None

    color_var = (getattr(obj, "oilflow_color_var", "") or "").strip()
    if color_var and ff.variable_array(color_var) is not None:
        from ..render.plane import attach_scalar
        attach_scalar(ugrid, ff, color_var, cell_centered, rows=rows)

    # Work grid with vector as point data (stream tracer needs point vectors)
    work = ugrid
    if cell_centered:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(ugrid)
        c2p.PassCellDataOn()
        c2p.Update()
        work = c2p.GetOutput()

    seeds = _seed_grid(ugrid, obj)
    if seeds is None or seeds.GetNumberOfPoints() == 0:
        return None

    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(work)
    tracer.SetSourceData(seeds)
    tracer.SetInputArrayToProcess(
        0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, base)
    method = str(getattr(obj, "oilflow_integration_method",
                          "Runge-Kutta") or "Runge-Kutta").lower()
    if method == "euler":
        tracer.SetIntegratorTypeToEuler()
    elif method in ("rk2", "runge-kutta2"):
        tracer.SetIntegratorTypeToRungeKutta2()
    else:
        # R0.8: "Runge-Kutta" uses RK4, matching the streamline tracer.
        tracer.SetIntegratorTypeToRungeKutta4()
    tracer.SetMaximumPropagation(
        float(getattr(obj, "oilflow_length", 1.0) or 1.0))
    tracer.SetInitialIntegrationStep(
        max(1e-6, float(getattr(obj, "oilflow_accuracy", 1) or 1) * 1e-3))
    tracer.SetMaximumNumberOfSteps(
        int(getattr(obj, "oilflow_steps", 10) or 10))
    tracer.Update()

    out = tracer.GetOutput()
    if out.GetNumberOfCells() == 0:
        return None

    draw_type = getattr(obj, "oilflow_draw_type", "Line") or "Line"
    if draw_type in ("Simple", "Line"):
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(out)
    else:
        # Tube the lines (Standard / Triangle / 3D readout via thickness)
        tube = vtk.vtkTubeFilter()
        tube.SetInputData(out)
        tube.SetNumberOfSides(
            3 if str(draw_type) == "Triangle" else 8)
        tube.SetRadius(
            max(1e-4, float(getattr(obj, "oilflow_thickness", 1.0) or 1.0)
                * 1e-3))
        tube.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tube.GetOutputPort())

    use_color = bool(color_var) and \
        out.GetPointData().GetArray(color_var) is not None
    if use_color:
        mapper.SetScalarModeToUsePointData()
        mapper.SelectColorArray(color_var)
        mapper.SetScalarRange(
            out.GetPointData().GetArray(color_var).GetRange())

    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetLineWidth(max(1, int(getattr(obj, "oilflow_thickness", 1.0))))
    if not use_color:
        mapper.ScalarVisibilityOff()
    if getattr(obj, "oilflow_transparent", False):
        prop.SetOpacity(0.5)
    return actor


def _seed_grid(ugrid, obj) -> Optional["vtk.vtkPolyData"]:
    """Even seed grid on the cut plane (scPOST Oil Flow Space u/v)."""
    b = ugrid.GetBounds()
    u = max(b[1] - b[0], 1e-9)
    v = max(b[3] - b[2], 1e-9)
    su = float(getattr(obj, "oilflow_space_u", 1.0) or 1.0)
    sv = float(getattr(obj, "oilflow_space_v", 1.0) or 1.0)
    step = max(u, v) / 40.0
    nx = max(1, int(u / max(step * su, 1e-9)))
    ny = max(1, int(v / max(step * sv, 1e-9)))
    origin = np.asarray(getattr(obj, "point", (0.0, 0.0, 0.0)))
    n = np.asarray(getattr(obj, "normal", (0.0, 0.0, 1.0)))
    n = n / np.linalg.norm(n)
    e1 = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(e1, n)) > 0.99:
        e1 = np.array([0.0, 1.0, 0.0])
    e1 = e1 - np.dot(e1, n) * n
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)

    pts = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    for i in range(nx):
        for j in range(ny):
            p = (origin + (i - (nx - 1) / 2) * step * su * e1
                 + (j - (ny - 1) / 2) * step * sv * e2)
            points.InsertNextPoint(*p)
    pts.SetPoints(points)
    return pts
