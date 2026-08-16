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

    # FLD hex grids crash VTK cell-locator filters (vtkProbeFilter /
    # vtkStreamTracer — heap corruption), same workaround as streamline:
    # trace numerically with nearest-node sampling + RK4 (P0-5).
    if ff.kind == "fld":
        poly = _numeric_trace_fld(ff, obj)
        if poly is None:
            return None
        return _render_actor(poly, base, obj)

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


def _seed_points_np(obj, verts) -> Optional[np.ndarray]:
    """Seed points as an (N, 3) array on the cut plane (FLD numeric path)."""
    b = verts.min(axis=0), verts.max(axis=0)
    u = max(b[1][0] - b[0][0], 1e-9)
    v = max(b[1][1] - b[0][1], 1e-9)
    su = float(getattr(obj, "oilflow_space_u", 1.0) or 1.0)
    sv = float(getattr(obj, "oilflow_space_v", 1.0) or 1.0)
    step = max(u, v) / 40.0
    nx = max(1, int(u / max(step * su, 1e-9)))
    ny = max(1, int(v / max(step * sv, 1e-9)))
    origin = np.asarray(getattr(obj, "point", (0.0, 0.0, 0.0)), dtype=np.float64)
    n = np.asarray(getattr(obj, "normal", (0.0, 0.0, 1.0)), dtype=np.float64)
    n = n / max(np.linalg.norm(n), 1e-12)
    e1 = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(e1, n)) > 0.99:
        e1 = np.array([0.0, 1.0, 0.0])
    e1 = e1 - np.dot(e1, n) * n
    e1 /= max(np.linalg.norm(e1), 1e-12)
    e2 = np.cross(n, e1)
    out = []
    for i in range(nx):
        for j in range(ny):
            out.append(origin + (i - (nx - 1) / 2) * step * su * e1
                       + (j - (ny - 1) / 2) * step * sv * e2)
    return np.asarray(out, dtype=np.float64) if out else None


def _numeric_trace_fld(ff: FieldFile, obj) -> Optional["vtk.vtkPolyData"]:
    """Numerical oil-flow for FLD node-centred data (no VTK locator).

    Mirrors the streamline FLD fallback: nearest-node sampling of the
    ``oilflow_var`` field with RK4 integration (Euler when requested),
    honouring ``oilflow_length`` / ``oilflow_steps`` / ``oilflow_accuracy``
    and attaching ``oilflow_color_var`` point data for line colouring.
    """
    from ..render.streamline import NodeFieldSampler
    verts = np.asarray(ff.vertices, dtype=np.float64)
    if verts is None or len(verts) == 0:
        return None
    base = getattr(obj, "oilflow_var", "") or ""
    comps = []
    for suff in ("X", "Y", "Z"):
        a = ff.variable_array(f"{base}{suff}")
        comps.append(np.asarray(a, dtype=np.float64) if a is not None
                     else np.zeros(len(verts)))
    field = np.column_stack(comps)
    color_var = (getattr(obj, "oilflow_color_var", "") or "").strip()
    color_vals = None
    if color_var:
        a = ff.variable_array(color_var)
        if a is not None and len(a) == len(verts):
            color_vals = np.asarray(a, dtype=np.float64)

    sampler = NodeFieldSampler(verts)
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    box = (hi - lo) * 0.5
    seeds = _seed_points_np(obj, verts)
    if seeds is None or len(seeds) == 0:
        return None
    max_steps = int(getattr(obj, "oilflow_steps", 10) or 10)
    step_len = max(1e-6, float(getattr(obj, "oilflow_accuracy", 1) or 1)
                   * 1e-3)
    length = float(getattr(obj, "oilflow_length", 1.0) or 1.0)
    rk4 = str(getattr(obj, "oilflow_integration_method", "Runge-Kutta")
              or "Runge-Kutta").lower() not in ("euler", "rk2")

    def velocity(p: np.ndarray) -> np.ndarray:
        return field[sampler.nearest(p)]

    def advance(p: np.ndarray) -> np.ndarray:
        if rk4:
            k1 = velocity(p)
            k2 = velocity(p + 0.5 * step_len * k1)
            k3 = velocity(p + 0.5 * step_len * k2)
            k4 = velocity(p + step_len * k3)
            return p + (step_len / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        k1 = velocity(p)
        k2 = velocity(p + 0.5 * step_len * k1)
        return p + step_len * k2

    poly = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    lines = vtk.vtkCellArray()
    scalars: list[float] = []
    for s0 in seeds:
        p = s0.copy()
        chain = [p.copy()]
        vals = [color_vals[sampler.nearest(p)]
                if color_vals is not None else 0.0]
        travel = 0.0
        for _ in range(max_steps):
            nxt = advance(p)
            travel += float(np.linalg.norm(nxt - p))
            p = nxt
            if not (lo - box <= p).all() or not (p <= hi + box).all():
                break
            chain.append(p.copy())
            if color_vals is not None:
                vals.append(color_vals[sampler.nearest(p)])
            if length > 0.0 and travel >= length:
                break
        if len(chain) < 2:
            continue
        lc = vtk.vtkPolyLine()
        lc.GetPointIds().SetNumberOfIds(len(chain))
        for k, p in enumerate(chain):
            lc.GetPointIds().SetId(k, pts.InsertNextPoint(*p))
            if color_vals is not None:
                scalars.append(vals[k])
        lines.InsertNextCell(lc)

    if lines.GetNumberOfCells() == 0:
        return None
    poly.SetPoints(pts)
    poly.SetLines(lines)
    if color_vals is not None and scalars:
        arr = _vns.numpy_to_vtk(np.asarray(scalars, dtype=np.float64),
                                deep=True)
        arr.SetName(color_var)
        poly.GetPointData().SetScalars(arr)
    return poly


def _render_actor(poly, base: str, obj) -> Optional["vtk.vtkActor"]:
    """Actor for a traced polyline set (colour by oilflow_color_var)."""
    color_var = (getattr(obj, "oilflow_color_var", "") or "").strip()
    use_color = bool(color_var) and \
        poly.GetPointData().GetArray(color_var) is not None
    draw_type = getattr(obj, "oilflow_draw_type", "Line") or "Line"
    if draw_type in ("Simple", "Line"):
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
    else:
        tube = vtk.vtkTubeFilter()
        tube.SetInputData(poly)
        tube.SetNumberOfSides(3 if str(draw_type) == "Triangle" else 8)
        tube.SetRadius(
            max(1e-4, float(getattr(obj, "oilflow_thickness", 1.0) or 1.0)
                * 1e-3))
        tube.Update()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tube.GetOutputPort())

    if use_color:
        mapper.SetScalarModeToUsePointData()
        mapper.SelectColorArray(color_var)
        mapper.SetScalarRange(
            poly.GetPointData().GetArray(color_var).GetRange())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetLineWidth(max(1, int(getattr(obj, "oilflow_thickness", 1.0))))
    if not use_color:
        mapper.ScalarVisibilityOff()
    if getattr(obj, "oilflow_transparent", False):
        prop.SetOpacity(0.5)
    return actor
