"""Streamline object (scPOST Streamline) — seeded from a plane grid.

Seeds are generated on a plane (``seed_center``/``seed_normal`` or
axis+coordinate) at ``seed_density_u``×``seed_density_v`` points and traced
through the volume vector field with ``vtkStreamTracer``. The rendered
polylines can be coloured by a scalar variable ``color_var`` and drawn as
lines / tubes.
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


def build_streamline_actors(ff: FieldFile, obj,
                            ugrid=None, cell_centered=None) -> dict:
    """Streamline actors → ``{"streamline"}``.

    ``obj.vector_var`` names the trace field; ``obj.color_var`` a scalar to
    colour lines with. Returns ``{}`` when disabled or data missing.
    """
    out: dict = {}
    if not _HAS_VTK:
        return out
    base = getattr(obj, "vector_var", "") or ""
    if not base:
        return out
    for suff in ("X", "Y", "Z"):
        if ff.variable_array(f"{base}{suff}") is None:
            return out

    from .plane import build_ugrid
    if ugrid is None or cell_centered is None:
        ugrid, cell_centered = build_ugrid(ff, cell_mask=None)
    if ugrid is None:
        return out

    # FLD hex grids crash VTK cell-locator filters (vtkProbeFilter /
    # vtkStreamTracer — heap corruption), so trace numerically instead.
    if ff.kind == "fld":
        poly = _euler_trace_fld(ff, obj)
        if poly is None:
            return out
        actor = _render_actor(poly, base, obj)
        if actor is not None:
            out["streamline"] = actor
        return out

    _attach_field(ff, ugrid, base, cell_centered,
                  getattr(obj, "color_var", "") or "")

    work = ugrid
    if cell_centered:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(ugrid)
        c2p.PassCellDataOn()
        c2p.Update()
        work = c2p.GetOutput()

    seeds = _seed_grid(ugrid, obj)
    if seeds is None or seeds.GetNumberOfPoints() == 0:
        return out

    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(work)
    tracer.SetSourceData(seeds)
    tracer.SetInputArrayToProcess(
        0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, base)
    method = (getattr(obj, "integration_method", "Runge-Kutta") or "")
    if str(method).lower() == "euler":
        tracer.SetIntegratorTypeToEuler()
    else:
        tracer.SetIntegratorTypeToRungeKutta2()
    direction = (getattr(obj, "direction", "Forward") or "Forward")
    if str(direction).lower() == "backward":
        tracer.SetIntegrationDirectionToBackward()
    elif str(direction).lower() == "both":
        tracer.SetIntegrationDirectionToBoth()
    else:
        tracer.SetIntegrationDirectionToForward()
    tracer.SetMaximumPropagation(
        float(getattr(obj, "length", 1.0) or 1.0))
    tracer.SetInitialIntegrationStep(
        max(1e-6, float(getattr(obj, "step_size", 0.01) or 0.01)))
    tracer.SetMaximumNumberOfSteps(
        int(getattr(obj, "max_steps", 200) or 200))
    tracer.Update()

    lines_out = tracer.GetOutput()
    if lines_out.GetNumberOfCells() == 0:
        return out

    actor = _render_actor(lines_out, base, obj)
    if actor is not None:
        out["streamline"] = actor
    return out


def _attach_field(ff: FieldFile, ugrid, base: str, cell_centered: bool,
                  color_var: str = "") -> None:
    """Attach vectors (and optional scalar) onto the grid."""
    from .plane import attach_scalar, attach_vector
    attach_vector(ugrid, ff, base, cell_centered)
    if color_var:
        attach_scalar(ugrid, ff, color_var, cell_centered)


def _euler_trace_fld(ff: FieldFile, obj) -> Optional["vtk.vtkPolyData"]:
    """Numerical streamline for FLD node-centred data (no VTK locator).

    Seeds are stepped with explicit Euler through the node field, using
    nearest-node vector lookup; the trace is bounded to the mesh box.
    """
    import numpy as np
    verts = np.asarray(ff.vertices, dtype=np.float64)
    if verts is None or len(verts) == 0:
        return None
    base = getattr(obj, "vector_var", "") or ""
    comps = []
    for suff in ("X", "Y", "Z"):
        a = ff.variable_array(f"{base}{suff}")
        comps.append(np.asarray(a, dtype=np.float64) if a is not None
                     else np.zeros(len(verts)))
    field = np.column_stack(comps)
    lo = verts.min(axis=0)
    hi = verts.max(axis=0)
    n = len(verts)
    box = (hi - lo) * 0.5

    seeds = _seed_centers(ff, obj)
    if not seeds:
        return None
    max_steps = int(getattr(obj, "max_steps", 200) or 200)
    step_len = max(1e-6, float(getattr(obj, "step_size", 0.001) or 0.001))
    direction = (getattr(obj, "direction", "Forward") or "Forward")
    sign = 1.0
    if str(direction).lower() == "backward":
        sign = -1.0
    poly = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    lines = vtk.vtkCellArray()
    for s0 in seeds:
        p = np.asarray(s0, dtype=np.float64)
        ids = []
        for _ in range(max_steps):
            d = verts - p
            idx = int(np.argmin(np.einsum("ij,ij->i", d, d)))
            if idx >= n:
                break
            v = field[idx] * sign
            ids.append(pts.InsertNextPoint(*p))
            p = p + v * step_len
            if not (lo - box <= p).all() or not (p <= hi + box).all():
                break
        if len(ids) >= 2:
            lc = vtk.vtkPolyLine()
            lc.GetPointIds().SetNumberOfIds(len(ids))
            for k, i in enumerate(ids):
                lc.GetPointIds().SetId(k, i)
            lines.InsertNextCell(lc)
    if lines.GetNumberOfCells() == 0:
        return None
    poly.SetPoints(pts)
    poly.SetLines(lines)
    return poly


def _seed_centers(ff: FieldFile, obj) -> list:
    """Seed points for FLD numerical tracing (node-aligned grid center)."""
    import numpy as np
    verts = np.asarray(ff.vertices, dtype=np.float64)
    lo = verts.min(axis=0)
    hi = verts.max(axis=0)
    c = np.asarray(getattr(obj, "seed_center", (0.0, 0.0, 0.0)),
                   dtype=np.float64)
    axis = getattr(obj, "seed_axis", "Arbitrary") or "Arbitrary"
    if axis != "Arbitrary":
        idx = {"X": 0, "Y": 1, "Z": 2}[str(axis).upper()]
        coord = float(getattr(obj, "seed_coordinate", 0.0) or 0.0)
        c = [0.5 * (lo[i] + hi[i]) for i in range(3)]
        c[idx] = coord
    nu = max(1, int(getattr(obj, "seed_density_u", 6) or 6))
    nv = max(1, int(getattr(obj, "seed_density_v", 6) or 6))
    n = np.asarray(getattr(obj, "seed_normal", (0.0, 0.0, 1.0)),
                   dtype=np.float64)
    n = n / (np.linalg.norm(n) + 1e-12)
    e1 = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(e1, n)) > 0.99:
        e1 = np.array([0.0, 1.0, 0.0])
    e1 -= np.dot(e1, n) * n
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    span = (hi - lo) * 0.5
    out = []
    for i in range(nu):
        for j in range(nv):
            p = (c + (i - (nu - 1) / 2.0) * span / max(1, nu - 1) * e1
                 + (j - (nv - 1) / 2.0) * span / max(1, nv - 1) * e2)
            out.append(p)
    return out


def _seed_grid(ugrid, obj) -> Optional["vtk.vtkPolyData"]:
    """Uniform seed grid on the Streamline's seed plane."""
    b = ugrid.GetBounds()
    c = np.asarray(getattr(obj, "seed_center", (0.0, 0.0, 0.0)),
                   dtype=np.float64)
    if getattr(obj, "seed_axis", "Arbitrary") != "Arbitrary":
        axis = (getattr(obj, "seed_axis", "Z") or "Z").upper()
        idx = {"X": 0, "Y": 1, "Z": 2}[axis]
        coord = float(getattr(obj, "seed_coordinate", 0.0) or 0.0)
        c = np.array([
            (coord, c[1], c[2]),
            (c[0], coord, c[2]),
            (c[0], c[1], coord),
        ][idx])
        n = np.zeros(3)
        n[idx] = 1.0
    else:
        n = np.asarray(getattr(obj, "seed_normal", (0.0, 0.0, 1.0)),
                       dtype=np.float64)
    n = n / (np.linalg.norm(n) + 1e-12)
    e1 = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(e1, n)) > 0.99:
        e1 = np.array([0.0, 1.0, 0.0])
    e1 -= np.dot(e1, n) * n
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)

    extents = np.array([b[1] - b[0], b[3] - b[2], b[5] - b[4]])
    radius = 0.5 * np.linalg.norm(extents)
    nu = max(1, int(getattr(obj, "seed_density_u", 10) or 10))
    nv = max(1, int(getattr(obj, "seed_density_v", 10) or 10))
    spacing = float(getattr(obj, "seed_spacing", 1.0) or 1.0)
    step = radius / max(2.0, max(nu, nv)) * spacing

    pts = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    half = (nu - 1) / 2.0 if nu > 1 else 0.0
    for i in range(nu):
        for j in range(nv):
            p = (c + (i - half) * step * e1
                 + (j - ((nv - 1) / 2.0 if nv > 1 else 0)) * step * e2)
            points.InsertNextPoint(*p)
    pts.SetPoints(points)
    return pts


def _render_actor(lines_out, base: str, obj) -> Optional["vtk.vtkActor"]:
    draw_type = (getattr(obj, "draw_type", "Line") or "Line")
    color_var = getattr(obj, "color_var", "") or ""
    use_color = bool(color_var)

    mapper = vtk.vtkPolyDataMapper()
    if draw_type in ("Tube", "Triangle"):
        tube = vtk.vtkTubeFilter()
        tube.SetInputData(lines_out)
        tube.SetNumberOfSides(3 if str(draw_type) == "Triangle" else 8)
        tube.SetRadius(1e-3)
        tube.Update()
        mapper.SetInputConnection(tube.GetOutputPort())
    else:
        mapper.SetInputData(lines_out)
    if use_color:
        mapper.SetScalarModeToUsePointData()
        mapper.SelectColorArray(color_var)
        mapper.SetScalarRange(_data_range(lines_out, color_var))
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetLineWidth(max(1, int(getattr(obj, "thickness", 1.0) or 1.0)))
    if not use_color:
        try:
            prop.SetColor(*getattr(obj, "mono_color", (0.2, 0.4, 0.9)))
        except (AttributeError, TypeError):
            prop.SetColor(0.2, 0.4, 0.9)
        mapper.ScalarVisibilityOff()
    if getattr(obj, "transparent", False):
        prop.SetOpacity(0.5)
    return actor


def _data_range(pd, name: str) -> tuple[float, float]:
    arr = pd.GetPointData().GetArray(name)
    if arr is None:
        arr = pd.GetCellData().GetArray(name)
    if arr is None:
        return (0.0, 1.0)
    r = arr.GetRange()
    if r[0] == r[1]:
        r = (r[0] - 1.0, r[1] + 1.0)
    return (float(r[0]), float(r[1]))