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
        poly = _numeric_trace_fld(ff, obj)
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
    method = str(getattr(obj, "integration_method", "Runge-Kutta")
                 or "Runge-Kutta").lower()
    if method == "euler":
        tracer.SetIntegratorTypeToEuler()
    elif hasattr(tracer, "SetIntegratorTypeToRungeKutta4"):
        tracer.SetIntegratorTypeToRungeKutta4()   # P1.2: real RK4
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


class NodeFieldSampler:
    """Nearest-node sampler with KD-tree acceleration (P1.2).

    FLD node-centred fields are evaluated at the nearest mesh node;
    scipy's cKDTree gives O(log n) lookups, with a vectorised brute-force
    argmin fallback when scipy is unavailable.
    """

    def __init__(self, verts: np.ndarray):
        self.verts = np.ascontiguousarray(verts, dtype=np.float64)
        self._tree = None
        try:
            from scipy.spatial import cKDTree
            self._tree = cKDTree(self.verts)
        except Exception:  # pragma: no cover - scipy absent
            self._tree = None

    def nearest(self, p: np.ndarray) -> int:
        if self._tree is not None:
            return int(self._tree.query(p)[1])
        d = self.verts - p
        return int(np.argmin(np.einsum("ij,ij->i", d, d)))


# VTK hexahedron vertex signs for the trilinear shape functions.
_HEX_SIGNS = np.array([
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
], dtype=np.float64)


def _trilinear_weights(corners: np.ndarray, r: np.ndarray) -> np.ndarray:
    """Hex8 shape-function weights at local coords ``r`` (k×3 → k×8)."""
    one = 1.0 + r[:, None, :] * _HEX_SIGNS[None, :, :]     # (k, 8, 3)
    return 0.125 * one.prod(axis=2)


class FldCellInterpolator:
    """True hex-cell interpolation for FLD node-centred fields (P2-1).

    Finds the hexahedron containing a query point (per-cell bbox prefilter
    + Newton solve of the trilinear map) and returns the cell's 8 node ids
    with the trilinear weights, so node data is interpolated inside the
    cell instead of sampled at the nearest node.  Points outside the mesh,
    in inter-cell gaps or inside non-hex cells fall back to the nearest
    node (``locate`` returns ``(None, None)``).
    """

    _EPS = 1e-6

    def __init__(self, ff):
        self.verts = np.asarray(ff.vertices, dtype=np.float64)
        conn = getattr(ff, "cell_conn", None)
        self.conn = None
        self._bmin = None
        self._bmax = None
        self._hex_mask = None
        self._nn = NodeFieldSampler(self.verts)
        if conn is not None and getattr(conn, "size", 0):
            c0 = np.asarray(conn, dtype=np.int64)
            valid = c0[c0 >= 0]
            if valid.size:
                base = (1 if (valid.min() > 0
                              and valid.max() >= self.verts.shape[0]) else 0)
                c0 = np.where(c0 >= 0, c0 - base, -1)
            self.conn = c0
            n_cells = c0.shape[0]
            types = getattr(ff, "cell_types", None)
            if types is not None and len(types) == n_cells:
                t = np.asarray(types, dtype=np.int64)
                self._hex_mask = (t == 0) | (t == 12)
            else:
                self._hex_mask = np.ones(n_cells, dtype=bool)
            safe = np.where(c0 >= 0, c0, 0)
            coords = self.verts[safe]                      # (n_cells, 8, 3)
            mask = (c0 >= 0)[..., None]                    # (n_cells, 8, 1)
            finite = np.where(mask, coords, np.inf)
            neginf = np.where(mask, coords, -np.inf)
            self._bmin = finite.min(axis=1)
            self._bmax = neginf.max(axis=1)

    def locate(self, p):
        """``(node_ids (8,), weights (8,))`` of the containing hex cell,
        or ``(None, None)`` when no hex cell contains *p*."""
        p = np.asarray(p, dtype=np.float64)
        if self.conn is None or self._bmin is None:
            return None, None
        inb = ((p >= self._bmin) & (p <= self._bmax)).all(axis=1)
        cands = np.flatnonzero(inb & self._hex_mask)
        if cands.size == 0:
            return None, None
        ids = self.conn[cands]
        ok = (ids >= 0).all(axis=1)
        cands = cands[ok]
        if cands.size == 0:
            return None, None
        ids = self.conn[cands]
        V = self.verts[ids]                                # (k, 8, 3)
        r = np.zeros((cands.size, 3), dtype=np.float64)
        r_prev = np.full_like(r, np.inf)
        for _ in range(24):
            one = 1.0 + r[:, None, :] * _HEX_SIGNS[None, :, :]
            N = 0.125 * one.prod(axis=2)                   # (k, 8)
            X = np.einsum("ki,kij->kj", N, V)              # (k, 3)
            res = p[None, :] - X
            if np.abs(r - r_prev).max() < 1e-12:
                break
            r_prev = r.copy()
            dNr = 0.125 * _HEX_SIGNS[:, 0][None, :] * np.prod(one[:, :, 1:], axis=2)
            dNs = 0.125 * _HEX_SIGNS[:, 1][None, :] * np.prod(one[:, :, [0, 2]], axis=2)
            dNt = 0.125 * _HEX_SIGNS[:, 2][None, :] * np.prod(one[:, :, :2], axis=2)
            J = np.stack([
                np.einsum("ki,kij->kj", dNr, V),
                np.einsum("ki,kij->kj", dNs, V),
                np.einsum("ki,kij->kj", dNt, V),
            ], axis=1)                                     # (k, 3, 3)
            try:
                delta = np.linalg.solve(J, res[:, :, None])[:, :, 0]
            except np.linalg.LinAlgError:
                break
            r = r + delta
        inside = (np.abs(r) <= 1.0 + self._EPS).all(axis=1)
        if not inside.any():
            return None, None
        i = int(np.flatnonzero(inside)[0])
        N = _trilinear_weights(V[i:i + 1], r[i:i + 1])[0]
        return ids[i], N

    def sample(self, p, field: np.ndarray) -> np.ndarray:
        """Interpolate a node array at *p*; nearest-node fallback."""
        ids, w = self.locate(p)
        if ids is not None:
            return np.dot(w, field[ids])
        return field[self._nn.nearest(p)]


def _numeric_trace_fld(ff: FieldFile, obj) -> Optional["vtk.vtkPolyData"]:
    """Numerical streamline for FLD node-centred data (no VTK locator).

    P1.2: RK4 integration when ``obj.integration_method`` is
    "Runge-Kutta" (4 field evaluations per step) with explicit Euler as
    the fallback; the trace honours ``length`` (arc-length cap) and
    Forward / Backward / Both directions. When ``obj.color_var`` names a
    node scalar it is sampled at every trace point and attached as point
    data so lines can be coloured by it.
    """
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
    color_var = (getattr(obj, "color_var", "") or "").strip()
    color_vals = None
    if color_var:
        a = ff.variable_array(color_var)
        if a is not None:
            color_vals = np.asarray(a, dtype=np.float64)
            if color_vals.shape[0] != len(verts):
                color_vals = None

    interp = FldCellInterpolator(ff)
    lo = verts.min(axis=0)
    hi = verts.max(axis=0)
    box = (hi - lo) * 0.5

    seeds = _seed_centers(ff, obj)
    if not seeds:
        return None
    max_steps = int(getattr(obj, "max_steps", 200) or 200)
    step_len = max(1e-6, float(getattr(obj, "step_size", 0.01) or 0.01))
    length = float(getattr(obj, "length", 0.0) or 0.0)
    rk4 = str(getattr(obj, "integration_method", "Runge-Kutta")
              or "Runge-Kutta").lower() != "euler"
    direction = str(getattr(obj, "direction", "Forward")
                    or "Forward").lower()

    def velocity(p: np.ndarray, sign: float) -> np.ndarray:
        # P2-1: true hex-cell trilinear interpolation (nearest-node fallback)
        ids, w = interp.locate(p)
        if ids is not None:
            return np.dot(w, field[ids]) * sign
        return field[interp._nn.nearest(p)] * sign

    def color_at(p):
        if color_vals is None:
            return 0.0
        ids, w = interp.locate(p)
        if ids is not None:
            return float(np.dot(w, color_vals[ids]))
        return float(color_vals[interp._nn.nearest(p)])

    def advance(p: np.ndarray, sign: float) -> np.ndarray:
        if rk4:
            k1 = velocity(p, sign)
            k2 = velocity(p + 0.5 * step_len * k1, sign)
            k3 = velocity(p + 0.5 * step_len * k2, sign)
            k4 = velocity(p + step_len * k3, sign)
            return p + (step_len / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
        return p + step_len * velocity(p, sign)

    signs = {"backward": (-1.0,), "both": (1.0, -1.0)}.get(direction, (1.0,))
    poly = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    lines = vtk.vtkCellArray()
    scalars: list[float] = []

    def trace(p, sign):
        chain = [p.copy()]
        vals = [color_at(p)]
        travel = 0.0
        for _ in range(max_steps):
            nxt = advance(p, sign)
            travel += float(np.linalg.norm(nxt - p))
            p = nxt
            if not (lo - box <= p).all() or not (p <= hi + box).all():
                break
            chain.append(p.copy())
            if color_vals is not None:
                vals.append(color_at(p))
            if length > 0.0 and travel >= length:
                break
        return chain, vals

    for s0 in seeds:
        segments = []
        all_vals: list[float] = []
        if -1.0 in signs:  # Backward / Both: prepend reversed backward trace
            chain, vals = trace(np.asarray(s0, dtype=np.float64), -1.0)
            if len(chain) > 1:
                segments.append(chain[:0:-1])
                if color_vals is not None:
                    all_vals.extend(vals[:0:-1])
        chain, vals = trace(np.asarray(s0, dtype=np.float64), 1.0)
        segments.append(chain)
        if color_vals is not None:
            all_vals.extend(vals)
        total = sum(len(sg) for sg in segments)
        if total < 2:
            continue
        lc = vtk.vtkPolyLine()
        lc.GetPointIds().SetNumberOfIds(total)
        k = 0
        for sg in segments:
            for p in sg:
                lc.GetPointIds().SetId(k, pts.InsertNextPoint(*p))
                if color_vals is not None:
                    scalars.append(all_vals[k])
                k += 1
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


def _tube_radius(lines_out) -> float:
    """R0.7: tube radius scales with the streamline extent (0.2% diag)."""
    b = lines_out.GetBounds()
    diag = ((b[1] - b[0]) ** 2 + (b[3] - b[2]) ** 2
            + (b[5] - b[4]) ** 2) ** 0.5
    return max(1e-6, 0.002 * diag) if diag > 0.0 else 1e-3


def _render_actor(lines_out, base: str, obj) -> Optional["vtk.vtkActor"]:
    draw_type = (getattr(obj, "draw_type", "Line") or "Line")
    color_var = getattr(obj, "color_var", "") or ""
    use_color = bool(color_var)

    mapper = vtk.vtkPolyDataMapper()
    if draw_type in ("Tube", "Triangle"):
        tube = vtk.vtkTubeFilter()
        tube.SetInputData(lines_out)
        tube.SetNumberOfSides(3 if str(draw_type) == "Triangle" else 8)
        tube.SetRadius(_tube_radius(lines_out))
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
    return (float(r[0]), float(r[1]))