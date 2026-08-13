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
    direction = (getattr(obj, "direction", "Forward") or "Forward")
    reverse = str(direction).lower().startswith("back")
    cur = np.asarray(seeds, dtype=np.float64)
    n_seeds = cur.shape[0]
    chain = [[] for _ in range(n_seeds)]
    for fi, path in enumerate(files):
        ffc = ff if fi == 0 else load_file(path)
        if ffc is None:
            continue
        _attach_vectors(ugrid, ffc, var, cc)
        seg, ends = _trace(ugrid, ffc, cur, steps, reverse, cc)
        if seg is None:
            break
        for s in range(n_seeds):
            chain[s].append(seg[s])
        cur = ends
    lines = _assemble(chain)
    if lines is None:
        return {}
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
             cell_centered: bool = False):
    """Integrate each seed for *steps* through the current field.

    FLD grids bypass VTK locators (known heap corruption) with a numpy
    nearest-node Euler tracer.  Returns (segments, end_points) or
    (None, None) on failure.
    """
    if getattr(ff, "kind", "") == "fld":
        return _trace_fld_euler(ff, seeds, steps, reverse)
    pts = vtk.vtkPoints()
    pts.SetData(_vns.numpy_to_vtk(
        np.ascontiguousarray(seeds, dtype=np.float64), deep=True))
    src = vtk.vtkPolyData();
    src.SetPoints(pts)
    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(ugrid)
    tracer.SetSourceData(src)
    tracer.SetMaximumPropagation(max(1, steps));
    tracer.SetInitialIntegrationStep(0.001);
    tracer.SetIntegrationDirectionToForward()
    if reverse:
        tracer.SetIntegrationDirectionToBackward()
    tracer.Update()
    out = tracer.GetOutput()
    if out is None or out.GetNumberOfPoints() == 0:
        return None, None
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
    return segs, np.asarray(ends, dtype=np.float64)




def _trace_fld_euler(ff, seeds, steps: int, reverse: bool):
    """Numerical pathline step for FLD node fields (no VTK locator)."""
    verts = np.asarray(ff.vertices, dtype=np.float64)
    if verts is None or len(verts) == 0:
        return None, None
    base = (getattr(ff, "_path_var", "") or "VECT")
    comps = []
    for suff in ("X", "Y", "Z"):
        a = ff.variable_array(base + suff)
        comps.append(np.asarray(a, dtype=np.float64) if a is not None
                     else np.zeros(len(verts)))
    field = np.column_stack(comps)
    lo = verts.min(axis=0)
    hi = verts.max(axis=0)
    n = len(verts)
    box = (hi - lo) * 0.5
    step_len = max(1e-6, 0.001 * steps)
    sign = -1.0 if reverse else 1.0
    segs = []
    ends = []
    for s0 in seeds:
        p = np.asarray(s0, dtype=np.float64)
        path = [p.copy()]
        for _ in range(max(1, steps)):
            d = verts - p
            idx = int(np.argmin(np.einsum("ij,ij->i", d, d)))
            if idx >= n:
                break
            v = field[idx] * sign
            p = p + v * step_len
            if not (lo - box <= p).all() or not (p <= hi + box).all():
                break
            path.append(p.copy())
        segs.append(np.asarray(path));
        ends.append(path[-1])
    return segs, np.asarray(ends, dtype=np.float64)


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
    actor = vtk.vtkActor();
    actor.SetMapper(mapper);
    prop = actor.GetProperty();
    prop.SetLineWidth(max(1, int(getattr(obj, "thickness", 1) or 1)));
    try:
        prop.SetColor(*getattr(obj, "mono_color", (0.1, 0.1, 0.8)));
    except (TypeError, IndexError):
        prop.SetColor(0.1, 0.1, 0.8);
    if getattr(obj, "transparent", False):
        prop.SetOpacity(0.5);
    return actor
