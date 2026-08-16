"""Pathline object (scPOST PCL) - particle traces across cycles (P1.5).

A pathline is the trajectory of a fluid particle over time: the seed
points are integrated through the velocity field of each cycle file in
a sequence, and each cycle continues from the previous cycle's end
points.  The result is one polyline per seed spanning all cycles.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import vtk
from vtk.util import numpy_support as _vns

from ..model.dataset import FieldFile


def build_pathline_actors(obj, files: list, ff0: Optional[FieldFile] = None) -> dict:
    """Pathline actors -> {'pathline': actor}.

    files: cycle file paths in time order (from a FileSet).  The
    geometry comes from the first file; later files only need to supply
    the velocity field (FLD 'first file has geometry' semantics).
    Returns {} when no usable data is present.
    """
    if not files:
        return {}
    from ..model.dataset import load_file
    from .plane import build_ugrid
    ff = ff0 or load_file(files[0])
    var = (getattr(obj, "vector_var", "") or "").strip() or "VEL"
    seeds = _seed_points(ff, obj)
    if seeds is None or seeds.shape[0] == 0:
        return {}
    ugrid, cc = build_ugrid(ff)
    if ugrid is None:
        return {}
    steps = max(1, int(getattr(obj, "steps_per_cycle", 10) or 10))
    step_len = max(1e-6, float(getattr(obj, "step_size", 0.001) or 0.001))
    direction = (getattr(obj, "direction", "Forward") or "Forward")
    reverse = str(direction).lower().startswith("back")
    color_var = (getattr(obj, "color_var", "") or "").strip()
    cur = np.asarray(seeds, dtype=np.float64)
    n_seeds = cur.shape[0]
    chain = [[] for _ in range(n_seeds)]
    scalar_chain = [[] for _ in range(n_seeds)]
    for fi, path in enumerate(files):
        ffc = ff if fi == 0 else load_file(path)
        if ffc is None:
            continue
        _attach_vectors(ugrid, ffc, var, cc)
        seg, ends, vals = _trace(ugrid, ffc, cur, steps, reverse, cc,
                                 step_len=step_len, color_var=color_var)
        if seg is None:
            break
        for s in range(n_seeds):
            chain[s].append(seg[s])
            scalar_chain[s].append(vals[s] if vals is not None else None)
        cur = ends
    lines = _assemble(chain)
    if lines is None:
        return {}
    if color_var:
        scalars = _assemble_scalars(chain, scalar_chain)
        if scalars is not None:
            arr = _vns.numpy_to_vtk(np.asarray(scalars, dtype=np.float64),
                                    deep=True)
            arr.SetName(color_var)
            lines.GetPointData().SetScalars(arr)
    actor = _line_actor(lines, obj)
    return {"pathline": actor}


def _seed_points(ff, obj) -> Optional[np.ndarray]:
    """Seed grid on a plane through the model (like Streamline)."""
    if ff.vertices is None:
        return None
    verts = np.asarray(ff.vertices, dtype=np.float64)
    lo = verts.min(axis=0);
    hi = verts.max(axis=0)
    axis = (getattr(obj, "seed_axis", "Z") or "Z").upper()
    ax = {"X": 0, "Y": 1, "Z": 2}[axis]
    c = float(getattr(obj, "seed_coordinate", None) or
            0.5 * (lo[ax] + hi[ax]))
    du = max(1, int(getattr(obj, "density_u", 8) or 8));
    dv = max(1, int(getattr(obj, "density_v", 8) or 8));
    if axis == "X":
        xs, ys = np.meshgrid(np.linspace(lo[1], hi[1], du),
                             np.linspace(lo[2], hi[2], dv))
        pts = np.column_stack((np.full(ys.size, c), xs.ravel(), ys.ravel()))
    elif axis == "Y":
        xs, ys = np.meshgrid(np.linspace(lo[0], hi[0], du),
                             np.linspace(lo[2], hi[2], dv))
        pts = np.column_stack((xs.ravel(), np.full(ys.size, c), ys.ravel()))
    else:
        xs, ys = np.meshgrid(np.linspace(lo[0], hi[0], du),
                             np.linspace(lo[1], hi[1], dv))
        pts = np.column_stack((xs.ravel(), ys.ravel(), np.full(ys.size, c)))
    return pts


def _attach_vectors(ugrid, ff, var: str, cell_centered: bool) -> None:
    """(Re)attach the velocity vector array for the current cycle."""
    ff._path_var = var
    comps = [ff.variable_array(var + c) for c in "XYZ"]
    if not all(a is not None for a in comps):
        return
    v = np.column_stack(comps).astype(np.float64)
    arr = _vns.numpy_to_vtk(v, deep=True)
    arr.SetName(var)
    if cell_centered:
        ugrid.GetCellData().AddArray(arr);
        ugrid.GetCellData().SetActiveVectors(var)
    else:
        ugrid.GetPointData().AddArray(arr);
        ugrid.GetPointData().SetActiveVectors(var)


def _trace(ugrid, ff, seeds, steps: int, reverse: bool,
             cell_centered: bool = False, step_len: float = 0.001,
             color_var: str = ""):
    """Integrate each seed for *steps* through the current field.

    FLD grids bypass VTK locators (known heap corruption) with a numpy
    nearest-node RK4 tracer (P1.2).  Returns (segments, end_points,
    scalar_values) or (None, None, None) on failure; scalar_values is
    ``None`` unless *color_var* was resolvable.
    """
    if getattr(ff, "kind", "") == "fld":
        return _trace_fld_numeric(ff, seeds, steps, reverse,
                                  step_len=step_len, color_var=color_var)
    pts = vtk.vtkPoints()
    pts.SetData(_vns.numpy_to_vtk(
        np.ascontiguousarray(seeds, dtype=np.float64), deep=True))
    src = vtk.vtkPolyData();
    src.SetPoints(pts)
    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(ugrid)
    tracer.SetSourceData(src)
    tracer.SetMaximumPropagation(max(1, steps));
    tracer.SetInitialIntegrationStep(max(1e-6, step_len));
    tracer.SetIntegrationDirectionToForward()
    if reverse:
        tracer.SetIntegrationDirectionToBackward()
    tracer.Update()
    out = tracer.GetOutput()
    if out is None or out.GetNumberOfPoints() == 0:
        return None, None, None
    segs = [];
    ends = [];
    lines = out.GetLines()
    n_lines = lines.GetNumberOfCells() if lines else 0
    for li in range(n_lines):
        ids = vtk.vtkIdList();
        lines.GetCellAtId(li, ids);
        n = ids.GetNumberOfIds();
        if n < 2:
            segs.append(np.zeros((0, 3)));
            ends.append(seeds[li]);
            continue
        arr = np.array([out.GetPoint(ids.GetId(k)) for k in range(n)])
        segs.append(arr);
        ends.append(arr[-1]);
    while len(segs) < len(seeds):
        segs.append(np.zeros((0, 3)));
        ends.append(seeds[len(segs) - 1]);
    return segs, np.asarray(ends, dtype=np.float64), None




def _trace_fld_numeric(ff, seeds, steps: int, reverse: bool,
                       step_len: float = 0.001, color_var: str = ""):
    """Numerical pathline step for FLD node fields (no VTK locator).

    P1.2: RK4 integration (KD-tree nearest-node sampling) with the step
    length taken from ``obj.step_size`` instead of a hard-coded 0.001;
    ``color_var`` is sampled at each trace point when resolvable.
    """
    from .streamline import FldCellInterpolator
    verts = np.asarray(ff.vertices, dtype=np.float64)
    if verts is None or len(verts) == 0:
        return None, None, None
    base = (getattr(ff, "_path_var", "") or "VECT")
    comps = []
    for suff in ("X", "Y", "Z"):
        a = ff.variable_array(base + suff)
        comps.append(np.asarray(a, dtype=np.float64) if a is not None
                     else np.zeros(len(verts)))
    field = np.column_stack(comps)
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
    step_len = max(1e-6, float(step_len))
    sign = -1.0 if reverse else 1.0

    def velocity(p):
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

    def advance(p):
        k1 = velocity(p)
        k2 = velocity(p + 0.5 * step_len * k1)
        k3 = velocity(p + 0.5 * step_len * k2)
        k4 = velocity(p + step_len * k3)
        return p + (step_len / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

    segs = []
    ends = []
    vals_out = [] if color_vals is not None else None
    for s0 in seeds:
        p = np.asarray(s0, dtype=np.float64)
        path = [p.copy()]
        vals = [color_at(p)]
        for _ in range(max(1, steps)):
            p = advance(p)
            if not (lo - box <= p).all() or not (p <= hi + box).all():
                break
            path.append(p.copy())
            if color_vals is not None:
                vals.append(color_at(p))
        segs.append(np.asarray(path))
        ends.append(path[-1])
        if vals_out is not None:
            vals_out.append(vals)
    return segs, np.asarray(ends, dtype=np.float64), vals_out


def _assemble_scalars(chain, scalar_chain):
    """Per-point scalar values aligned with :func:`_assemble` insertion."""
    scalars = []
    for parts, vals in zip(chain, scalar_chain):
        total = sum(p.shape[0] for p in parts)
        if total < 2:
            continue
        seed_vals = []
        for seg_vals in vals:
            if seg_vals is None:
                return None
            seed_vals.extend(seg_vals)
        if len(seed_vals) != total:
            return None
        scalars.extend(seed_vals)
    return scalars or None


def _assemble(chain) -> Optional["vtk.vtkPolyData"]:
    """Join per-cycle segments into one polyline per seed."""
    if not chain:
        return None
    pts = vtk.vtkPoints();
    lines = vtk.vtkCellArray();
    ids = vtk.vtkIdList();
    for parts in chain:
        total = sum(p.shape[0] for p in parts)
        if total < 2:
            continue
        ids.Reset();
        for p in parts:
            for row in p:
                ids.InsertNextId(pts.InsertNextPoint(float(row[0]),
                                                   float(row[1]),
                                                   float(row[2])));
        lines.InsertNextCell(ids);
    pd = vtk.vtkPolyData();
    pd.SetPoints(pts);
    pd.SetLines(lines);
    return pd


def _line_actor(pd, obj) -> Optional["vtk.vtkActor"]:
    draw = (getattr(obj, "draw_type", "Line") or "Line");
    color_var = (getattr(obj, "color_var", "") or "").strip()
    mapper = vtk.vtkPolyDataMapper();
    if str(draw).lower() in ("tube", "triangle"):
        tube = vtk.vtkTubeFilter();
        tube.SetInputData(pd);
        tube.SetRadius(max(1e-4, float(
            getattr(obj, "thickness", 1.0) or 1.0)) * 1e-3);
        tube.SetNumberOfSides(
            3 if str(draw).lower() == "triangle" else 8);
        mapper.SetInputConnection(tube.GetOutputPort());
    else:
        mapper.SetInputData(pd);
    use_color = bool(color_var) and \
        pd.GetPointData().GetArray(color_var) is not None
    if use_color:
        mapper.SetScalarModeToUsePointData()
        mapper.SelectColorArray(color_var)
        mapper.SetScalarRange(
            pd.GetPointData().GetArray(color_var).GetRange())
    actor = vtk.vtkActor();
    actor.SetMapper(mapper);
    prop = actor.GetProperty();
    prop.SetLineWidth(max(1, int(getattr(obj, "thickness", 1) or 1)));
    if not use_color:
        try:
            prop.SetColor(*getattr(obj, "mono_color", (0.1, 0.1, 0.8)));
        except (TypeError, IndexError):
            prop.SetColor(0.1, 0.1, 0.8);
        mapper.ScalarVisibilityOff();
    if getattr(obj, "transparent", False):
        prop.SetOpacity(0.5);
    return actor
