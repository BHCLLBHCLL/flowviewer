"""scPOST-style boundary-surface rendering pipeline (``Surface@pst``).

Builds a ``vtkPolyData`` of the selected boundary faces from a ``FieldFile``
(FPH polyhedral face table or FLD quad boundary faces), then produces
scPOST-matching actors:

- **Contour**  — scalar map on the surface (Paint Front/Back, Transparent).
- **Vector**   — ``vtkGlyph3D`` arrows at surface nodes.
- **Mesh**     — edge lines of the surface.
- **Trim**     — clip the surface against X/Y/Z min/max planes.
- **Scalar Integration** — ``∫ψ dS`` over the surface triangles.

Scalar/vector data handling mirrors the plane pipeline: FPH stores
cell-centred fields (each boundary face inherits its owner cell's value),
FLD stores node-centred fields (indexed directly by face vertex ids).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from ..model.dataset import FieldFile

try:
    import vtk
    from vtk.util import numpy_support as _vns
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    _vns = None


# ---------------------------------------------------------------------------
# Boundary surface polydata
# ---------------------------------------------------------------------------

def build_surface_polydata(ff: FieldFile, obj):
    """Boundary-face polydata for a ``SurfaceObject``.

    Returns ``(polydata, cell_centered, face_indices)`` where
    ``face_indices`` are the selected boundary-face indices (FPH face table
    or FLD face list) and ``cell_centered`` tells whether attached fields
    live in CellData (FPH) or PointData (FLD).
    """
    if not _HAS_VTK:
        return None, False, None
    if ff.poly:
        return _fph_surface_polydata(ff, obj)
    return _fld_surface_polydata(ff, obj)


def _fph_surface_polydata(ff: FieldFile, obj):
    ld = ff.link_data
    if ld is None or ff.vertices is None:
        return None, True, None
    face_nodes = np.asarray(ld["face_nodes"], dtype=np.int64)
    face_offsets = np.asarray(ld["face_offsets"], dtype=np.int64)
    owner = np.asarray(ld["owner"], dtype=np.int64)
    verts = np.asarray(ff.vertices, dtype=np.float64)

    sel = _selected_faces(ff, obj)
    # MAT / Volume Region filter (P0.5): keep faces owned by kept cells
    from .plane import cell_filter_mask
    mask = cell_filter_mask(ff, obj)
    if mask is not None and len(mask) == ff.n_cells:
        keep_set = {int(c) for c in np.flatnonzero(mask)}
        sel = sel[np.asarray([int(owner[fi]) in keep_set for fi in sel],
                             dtype=bool)]
    points = vtk.vtkPoints()
    points.SetData(_vns.numpy_to_vtk(verts, deep=True))
    polys = vtk.vtkCellArray()
    cell_owner = []
    ids = vtk.vtkIdList()
    for fi in sel:
        lo, hi = int(face_offsets[fi]), int(face_offsets[fi + 1])
        n = hi - lo
        if n < 3:
            continue
        ids.Reset()
        for vi in face_nodes[lo:hi]:
            ids.InsertNextId(int(vi))
        polys.InsertNextCell(ids)
        cell_owner.append(int(owner[fi]))
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetPolys(polys)
    return pd, True, np.asarray(cell_owner, dtype=np.int64)


def _fld_surface_polydata(ff: FieldFile, obj):
    if ff.vertices is None or not ff.faces:
        return None, False, None
    verts = np.asarray(ff.vertices, dtype=np.float64)
    sel = _selected_faces(ff, obj)
    # MAT filter (G4): keep faces whose owning cell survives the mask
    from .plane import cell_filter_mask
    mask = cell_filter_mask(ff, obj)
    face_cells = getattr(ff, "face_cells", None)
    if mask is not None and face_cells is not None and len(face_cells):
        n = len(mask)
        keep = np.zeros(len(sel), dtype=bool)
        for i, fi in enumerate(sel):
            c = int(face_cells[fi])
            keep[i] = c < n and bool(mask[c])
        sel = sel[keep]
    points = vtk.vtkPoints()
    points.SetData(_vns.numpy_to_vtk(verts, deep=True))
    quads = vtk.vtkCellArray()
    ids = vtk.vtkIdList()
    for fi in sel:
        quad = ff.faces[fi]
        ids.Reset()
        for vi in quad:
            ids.InsertNextId(int(vi))
        quads.InsertNextCell(ids)
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetPolys(quads)
    return pd, False, np.asarray(sel, dtype=np.int64)


def _selected_faces(ff: FieldFile, obj) -> np.ndarray:
    """Boundary-face indices to draw.

    ``selected_regions`` empty → all boundary faces; otherwise the union of
    the named regions' face sets (intersected with the boundary).
    """
    regions = ff.boundary_regions()
    names = set(getattr(obj, "selected_regions", None) or [])
    if not names:
        ids = np.concatenate([r.face_ids for r in regions]) if regions else \
            np.array([], dtype=np.int64)
    else:
        ids = np.concatenate(
            [r.face_ids for r in regions if r.name in names]) if regions else \
            np.array([], dtype=np.int64)
    if ids.size == 0:
        return np.array([], dtype=np.int64)
    if ff.poly:
        ld = ff.link_data
        neighbour = np.asarray(ld["neighbour"], dtype=np.int64)
        bnd = np.flatnonzero(neighbour == -1)
        keep = np.intersect1d(ids, bnd)
        return keep
    return np.unique(ids)


# ---------------------------------------------------------------------------
# Field attachment
# ---------------------------------------------------------------------------

def attach_scalar(ff: FieldFile, pd, face_idx, var_name: str,
                  cell_centered: bool):
    """Attach ``var_name`` to the surface as CellData (FPH) / PointData (FLD)."""
    if var_name is None or var_name == "":
        return None
    arr = ff.variable_array(var_name)
    if arr is None:
        return None
    data = np.asarray(arr, dtype=np.float64)
    if cell_centered:
        face_vals = data[face_idx]
        fa = _vns.numpy_to_vtk(np.ascontiguousarray(face_vals,
                                                    dtype=np.float64),
                               deep=True)
        fa.SetName(var_name)
        pd.GetCellData().SetScalars(fa)
        return fa
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(data, dtype=np.float64),
                           deep=True)
    fa.SetName(var_name)
    pd.GetPointData().SetScalars(fa)
    return fa


def attach_vector(ff: FieldFile, pd, face_idx, base: str,
                  cell_centered: bool):
    """Attach vector field ``base``X/Y/Z to the surface."""
    for suff in ("X", "Y", "Z"):
        if ff.variable_array(f"{base}{suff}") is None:
            return None
    vx = np.asarray(ff.variable_array(f"{base}X"), dtype=np.float64)
    vy = np.asarray(ff.variable_array(f"{base}Y"), dtype=np.float64)
    vz = np.asarray(ff.variable_array(f"{base}Z"), dtype=np.float64)
    if cell_centered:
        vec = np.column_stack((vx[face_idx], vy[face_idx], vz[face_idx]))
        fa = _vns.numpy_to_vtk(np.ascontiguousarray(vec, dtype=np.float64),
                               deep=True)
        fa.SetName(base)
        pd.GetCellData().SetVectors(fa)
        return fa
    vec = np.column_stack((vx, vy, vz))
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(vec, dtype=np.float64),
                           deep=True)
    fa.SetName(base)
    pd.GetPointData().SetVectors(fa)
    return fa


# ---------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------

def contour_actor(pd, scalar_array_name: str, obj) -> Optional[vtk.vtkActor]:
    """Scalar contour map on the surface (CellData/PointData auto-detect)."""
    if not _HAS_VTK:
        return None
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    if pd.GetPointData().GetArray(scalar_array_name) is not None:
        mapper.SetScalarModeToUsePointData()
    else:
        mapper.SetScalarModeToUseCellData()
    mapper.SelectColorArray(scalar_array_name)
    mapper.SetScalarRange(_data_range(pd, scalar_array_name))
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    if obj.contour_transparent:
        prop.SetOpacity(0.5)
    if not getattr(obj, "contour_paint_front", True):
        prop.SetFrontFaceCulling(1)
    if not getattr(obj, "contour_paint_back", True):
        prop.SetBackFaceCulling(1)
    from .material import apply_sheen
    apply_sheen(prop, getattr(obj, "contour_luster", False),
                getattr(obj, "contour_water", False))
    return actor


def vector_actor(pd, obj, cell_centered: bool) -> Optional[vtk.vtkActor]:
    """Vector glyphs at surface nodes from already-attached vectors."""
    if not _HAS_VTK:
        return None
    base = obj.vector_var
    if not base:
        return None
    if cell_centered and pd.GetCellData().GetVectors() is None:
        return None
    if not cell_centered and pd.GetPointData().GetVectors() is None:
        return None
    work = pd
    if cell_centered:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(pd)
        c2p.PassCellDataOn()
        c2p.Update()
        work = c2p.GetOutput()
    work.GetPointData().SetActiveVectors(base)
    src = vtk.vtkArrowSource()
    glyph = vtk.vtkGlyph3D()
    glyph.SetInputData(work)
    glyph.SetSourceConnection(src.GetOutputPort())
    glyph.SetInputArrayToProcess(
        1, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS, base)
    glyph.SetScaleFactor(_vector_scale(work, obj))
    glyph.OrientOn()
    glyph.SetVectorModeToUseVector()
    glyph.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(glyph.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    from .vector import apply_vector_coloring
    apply_vector_coloring(obj, work, mapper, actor)
    return actor


def mesh_lines_actor(pd, obj) -> vtk.vtkActor:
    """Mesh edge lines of the surface."""
    edges = vtk.vtkExtractEdges()
    edges.SetInputData(pd)
    edges.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(edges.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*obj.mesh_color)
    prop.SetLineWidth(max(1, int(obj.mesh_thickness)))
    if obj.mesh_transparent:
        prop.SetOpacity(0.5)
    from .material import apply_sheen
    apply_sheen(prop, getattr(obj, "mesh_luster", False),
                getattr(obj, "mesh_water", False))
    return actor


def trim_surface(pd, obj) -> vtk.vtkPolyData:
    """Clip the surface against Trim tab X/Y/Z min/max planes."""
    out = pd
    for axis, key in (("X", "xmin"), ("X", "xmax"), ("Y", "ymin"),
                      ("Y", "ymax"), ("Z", "zmin"), ("Z", "zmax")):
        if not getattr(obj, f"trim_{key}", False):
            continue
        i = {"X": 0, "Y": 1, "Z": 2}[axis]
        bounds = out.GetBounds()
        sign = -1.0 if key.endswith("min") else 1.0
        normal = [0.0, 0.0, 0.0]
        normal[i] = sign
        origin = [0.0, 0.0, 0.0]
        origin[i] = bounds[2 * i + (0 if sign < 0 else 1)]
        clip = vtk.vtkPlane()
        clip.SetOrigin(*origin)
        clip.SetNormal(*normal)
        clipper = vtk.vtkClipPolyData()
        clipper.SetInputData(out)
        clipper.SetClipFunction(clip)
        clipper.Update()
        out = clipper.GetOutput()
    return out


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

def integrate_surface(pd, scalar_name: Optional[str]):
    """Integrate scalar over the surface triangles.

    Returns dict with ``area``, ``sum``, ``average``.
    """
    from .plane import integrate_cut
    return integrate_cut(pd, scalar_name)



# ---------------------------------------------------------------------------
# R21 bump-mapped surface
# ---------------------------------------------------------------------------

def bump_surface_actor(ff: FieldFile, obj, pd=None,
                       cell_centered=None, face_idx=None
                       ) -> Optional[vtk.vtkActor]:
    """Bump-mapped surface: vertices displaced along normals by a scalar.

    ``obj.bump_var`` selects the height field (falls back to
    ``obj.contour_var``). ``obj.bump_factor`` (default 0.05) displaces each
    vertex along its outward surface normal by ``factor * diag * (s - s0)/span``
    where ``diag`` is the model diagonal - so the peak scalar bumps the
    surface by ``factor`` of the model size. The displaced surface is
    coloured by the same scalar. Returns None when no height field is given
    or the surface is empty.
    """
    if not _HAS_VTK:
        return None
    var = ((getattr(obj, "bump_var", "") or "")
           or (getattr(obj, "contour_var", "") or "")).strip()
    if not var or var not in ff.variables:
        return None
    if pd is None:
        pd, cell_centered, face_idx = build_surface_polydata(ff, obj)
    if pd is None or pd.GetNumberOfCells() == 0:
        return None
    attach_scalar(ff, pd, face_idx, var, cell_centered)
    work = pd
    if cell_centered:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(pd)
        c2p.PassCellDataOn()
        c2p.Update()
        work = c2p.GetOutput()
    sarr = work.GetPointData().GetArray(var)
    if sarr is None:
        return None
    pts = _vns.vtk_to_numpy(work.GetPoints().GetData())
    pts = pts.astype(np.float64, copy=False)
    norms = _vertex_normals(pd, pts)
    s = _vns.vtk_to_numpy(sarr).astype(np.float64, copy=False)
    rng = float(sarr.GetRange()[0]), float(sarr.GetRange()[1])
    span = (rng[1] - rng[0]) or 1.0
    diag = max(float(pts[:, 0].max() - pts[:, 0].min()),
               float(pts[:, 1].max() - pts[:, 1].min()),
               float(pts[:, 2].max() - pts[:, 2].min()), 1e-9)
    _bump = getattr(obj, "bump_factor", None)
    factor = max(0.0, float(0.05 if _bump is None else _bump))
    h = (s - rng[0]) / span
    new_pts = pts + norms * (factor * diag * h[:, None])
    vp = vtk.vtkPoints()
    vp.SetData(_vns.numpy_to_vtk(np.ascontiguousarray(new_pts, dtype=np.float64),
                                 deep=True))
    # keep the point-scalar grid (work) as topology; only its geometry moves
    out = vtk.vtkPolyData()
    out.DeepCopy(work)
    out.SetPoints(vp)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(out)
    mapper.SetScalarModeToUsePointData()
    mapper.SelectColorArray(var)
    mapper.SetScalarRange(float(rng[0]), float(rng[1]))
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    return actor



def _vertex_normals(pd: vtk.vtkPolyData, pts: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals aligned with the polydata point order.

    Accumulates each face's Newell normal onto its vertices, then normalises,
    so the result is ordered 1:1 with ``pd``'s points (unused vertices keep a
    zero normal and are left unmoved by the bump).  Handled in numpy because
    ``vtkPolyDataNormals`` may re-order geometry points on C2P-transformed
    grids (R21).
    """
    n = pts.shape[0]
    norms = np.zeros((n, 3), dtype=np.float64)
    cellarr = pd.GetPolys()
    if cellarr is None:
        return norms
    ids = vtk.vtkIdList()
    cellarr.InitTraversal()
    while cellarr.GetNextCell(ids):
        m = ids.GetNumberOfIds()
        if m < 3:
            continue
        nids = [ids.GetId(i) for i in range(m)]
        p = pts[nids]
        face = np.zeros(3)
        for a in range(m):
            a0 = p[a]
            a1 = p[(a + 1) % m]
            face[0] += (a0[1] - a1[1]) * (a0[2] + a1[2])
            face[1] += (a0[2] - a1[2]) * (a0[0] + a1[0])
            face[2] += (a0[0] - a1[0]) * (a0[1] + a1[1])
        norms[nids] += face
    mag = np.linalg.norm(norms, axis=1, keepdims=True)
    mag[mag < 1e-300] = 1.0
    return norms / mag



# ---------------------------------------------------------------------------
# High-level entry
# ---------------------------------------------------------------------------

def build_surface_actors(ff: FieldFile, obj, pd=None,
                         cell_centered=None, face_idx=None) -> dict:
    """Produce every actor for a SurfaceObject.

    Returns ``{"contour", "vector", "mesh"}`` (keys present only when
    enabled), all derived from one boundary-face polydata.
    """
    out: dict = {}
    if not _HAS_VTK:
        return out
    if pd is None:
        pd, cell_centered, face_idx = build_surface_polydata(ff, obj)
    if pd is None or pd.GetNumberOfCells() == 0:
        return out

    # Attach contour scalar + vector before trim so the fields survive the
    # clip (trim renumbers cells but keeps attached arrays).
    if (getattr(obj, "show_contour", False)
            and getattr(obj, "contour_var", "")):
        attach_scalar(ff, pd, face_idx, obj.contour_var, cell_centered)
    if (getattr(obj, "show_vector", False)
            and getattr(obj, "vector_var", "")):
        attach_vector(ff, pd, face_idx, obj.vector_var, cell_centered)

    pd = trim_surface(pd, obj)
    if pd.GetNumberOfCells() == 0:
        return out

    if (getattr(obj, "show_contour", False)
            and getattr(obj, "contour_var", "")
            and obj.contour_var in ff.variables):
        c = contour_actor(pd, obj.contour_var, obj)
        if c is not None:
            out["contour"] = c
    if getattr(obj, "show_vector", False) and getattr(obj, "vector_var", ""):
        v = vector_actor(pd, obj, cell_centered)
        if v is not None:
            out["vector"] = v
    if getattr(obj, "show_mesh", False):
        out["mesh"] = mesh_lines_actor(pd, obj)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _vector_scale(pd, obj) -> float:
    b = pd.GetBounds()
    w = max(b[1] - b[0], b[3] - b[2], b[5] - b[4], 1e-9)
    return 0.05 * w * getattr(obj, "vector_scale_length", 1.0)
