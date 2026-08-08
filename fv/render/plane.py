"""scPOST-style cut-plane rendering pipeline (``CutPlane@pst``).

Builds a VTK unstructured grid from a ``FieldFile`` (FPH polyhedral links or
FLD hexahedra), slices it with ``vtkCutter`` on the plane defined by a
``PlaneObject``, then produces scPOST-matching actors:

- **Contour**  — scalar map on the cut (Paint / Line / Contour line /
  Transparent / Luster / Water) via ``vtkPolyDataMapper``.
- **Vector**   — ``vtkGlyph3D`` arrows placed Uniform / Actual / Center /
  Nodes, typed Simple / Standard / Triangle / 3D.
- **Mesh**     — boundary intersection line, mesh-face intersection lines,
  Block volume intersection, and the external-frame Subline.
- **Trim**     — clip the cut against other objects.
- **Integration** — ``∫ψ dS`` and ``∫ v·n dS`` on the cut triangles.
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
# Grid construction
# ---------------------------------------------------------------------------

def build_ugrid(ff: FieldFile):
    """Return ``(ugrid, cell_centered: bool)`` for cutting.

    FPH: cell-centred fields → build cells from ``LS_Links`` owner/neighbour
    faces (``vtkConvexPointSet`` for general polyhedra). Returns
    ``cell_centered=True`` so scalar data is attached as CellData.

    FLD: hexahedra from ``LS_Elements``; node fields → PointData
    (``cell_centered=False``).
    """
    if not _HAS_VTK:
        return None, True
    if ff.kind == "fph":
        return _build_fph_ugrid(ff), True
    return _build_fld_ugrid(ff), False


def _build_fph_ugrid(ff: FieldFile):
    ld = ff.link_data
    if ld is None or ff.vertices is None:
        return None
    verts = np.asarray(ff.vertices, dtype=np.float64)
    n_cells = int(np.asarray(ld["n_cells"]).item())
    cell_owner_faces = ld["cell_owner_faces"]

    points = vtk.vtkPoints()
    points.SetData(_vns.numpy_to_vtk(verts, deep=True))
    ug = vtk.vtkUnstructuredGrid()
    ug.SetPoints(points)

    cells = vtk.vtkCellArray()
    face_nodes = np.asarray(ld["face_nodes"], dtype=np.int64)
    face_offsets = np.asarray(ld["face_offsets"], dtype=np.int64)
    for c in range(n_cells):
        pf = cell_owner_faces[c]
        ids = []
        for fi in pf:
            lo, hi = int(face_offsets[fi]), int(face_offsets[fi + 1])
            ids.extend(face_nodes[lo:hi].tolist())
        cell = vtk.vtkConvexPointSet()
        n = len(ids)
        cell.GetPointIds().SetNumberOfIds(n)
        for k, vid in enumerate(ids):
            cell.GetPointIds().SetId(k, int(vid))
        cells.InsertNextCell(cell)
    ug.SetCells(vtk.VTK_CONVEX_POINT_SET, cells)
    return ug


def _build_fld_ugrid(ff: FieldFile):
    if ff.vertices is None or ff.cell_conn is None:
        return None
    verts = np.asarray(ff.vertices, dtype=np.float64)
    conn = np.asarray(ff.cell_conn, dtype=np.int64)
    points = vtk.vtkPoints()
    points.SetData(_vns.numpy_to_vtk(verts, deep=True))
    ug = vtk.vtkUnstructuredGrid()
    ug.SetPoints(points)
    cells = vtk.vtkCellArray()
    for row in conn:
        h = vtk.vtkHexahedron()
        for k in range(8):
            h.GetPointIds().SetId(k, int(row[k]))
        cells.InsertNextCell(h)
    ug.SetCells(vtk.VTK_HEXAHEDRON, cells)
    return ug


def _cell_centers(ugrid):
    cc = vtk.vtkCellCenters()
    cc.SetInputData(ugrid)
    cc.Update()
    return cc.GetOutput()


def attach_scalar(ugrid, ff: FieldFile, var_name: str, cell_centered: bool):
    """Attach the variable array to the grid. Returns vtkDataArray or None."""
    if var_name is None or var_name == "":
        return None
    arr = ff.variable_array(var_name)
    if arr is None:
        return None
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(arr, dtype=np.float64),
                           deep=True)
    fa.SetName(var_name)
    if cell_centered:
        ugrid.GetCellData().SetScalars(fa)
    else:
        ugrid.GetPointData().SetScalars(fa)
    return fa


def attach_vector(ugrid, ff: FieldFile, base: str, cell_centered: bool):
    """Attach a vector field (``base``X/Y/Z) to the grid."""
    for suff in ("X", "Y", "Z"):
        arr = ff.variable_array(f"{base}{suff}")
        if arr is None:
            return None
    vx = np.asarray(ff.variable_array(f"{base}X"), dtype=np.float64)
    vy = np.asarray(ff.variable_array(f"{base}Y"), dtype=np.float64)
    vz = np.asarray(ff.variable_array(f"{base}Z"), dtype=np.float64)
    vec = np.column_stack((vx, vy, vz))
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(vec, dtype=np.float64),
                           deep=True)
    fa.SetName(base)
    if cell_centered:
        ugrid.GetCellData().SetVectors(fa)
    else:
        ugrid.GetPointData().SetVectors(fa)
    return fa


# ---------------------------------------------------------------------------
# Plane cutting
# ---------------------------------------------------------------------------

def plane_from_object(obj):
    """vtkPlane from a PlaneObject (point + normal)."""
    p = vtk.vtkPlane()
    p.SetOrigin(*tuple(obj.point))
    p.SetNormal(*tuple(obj.normal))
    return p


def cut_grid(ugrid, obj) -> "vtk.vtkPolyData":
    """Slice the grid with the plane → closed contour polydata."""
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(plane_from_object(obj))
    cutter.SetInputData(ugrid)
    cutter.GenerateValues(1, 0.0, 0.0)
    cutter.GenerateTrianglesOn()
    cutter.Update()
    return cutter.GetOutput()


def make_plane_actor(pd, color=(1.0, 0.4, 0.7), opacity=0.35):
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*color)
    prop.SetOpacity(opacity)
    prop.EdgeVisibilityOn()
    prop.SetEdgeColor(*color)
    return actor


# ---------------------------------------------------------------------------
# Contour
# ---------------------------------------------------------------------------

def contour_actor(pd, scalar_array_name: str, obj,
                  lut=None) -> "vtk.vtkActor":
    """scPOST Contour map on a cut polydata.

    ``pd`` carries the scalar in CellData (cell-centred FPH source) or
    PointData (node-centred FLD source); the mapper picks the right mode.
    """
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(pd)
    if pd.GetPointData().GetArray(scalar_array_name) is not None:
        mapper.SetScalarModeToUsePointData()
    else:
        mapper.SetScalarModeToUseCellData()
    mapper.SelectColorArray(scalar_array_name)
    mapper.SetScalarRange(_data_range(pd, scalar_array_name))
    if lut is not None:
        mapper.SetLookupTable(lut)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if obj.contour_transparent:
        actor.GetProperty().SetOpacity(0.5)
    actor.GetProperty().SetInterpolationToPhong()
    return actor


def contour_line_actor(pd, scalar_array_name: str, obj) -> "vtk.vtkActor":
    """Contour-line isolines on the cut (vtkContourFilter)."""
    cf = vtk.vtkContourFilter()
    cf.SetInputData(pd)
    cf.ComputeNormalsOn()
    cf.SetNumberOfContours(10)
    in_pts = pd.GetPointData().GetArray(scalar_array_name) is not None
    cf.SetInputArrayToProcess(
        0, 0, 0,
        vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS if in_pts
        else vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS,
        scalar_array_name)
    cf.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(cf.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if obj.contour_line_transparent or obj.contour_transparent:
        actor.GetProperty().SetOpacity(0.5)
    if obj.contour_broken_line:
        actor.GetProperty().SetLineStipplePattern(0xF0F0)
        actor.GetProperty().SetLineStippleRepeatFactor(2)
    actor.GetProperty().SetLineWidth(max(1, int(obj.contour_thickness)))
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


# ---------------------------------------------------------------------------
# Vector
# ---------------------------------------------------------------------------

def _glyph_actor(pts_pd, obj, scale: float) -> "vtk.vtkActor":
    """Orient + scale arrow glyphs from ``pts_pd`` PointData vectors."""
    vec = pts_pd.GetPointData().GetVectors()
    if vec is None:
        return None
    if obj.vector_type in ("Simple", "Animation"):
        src = vtk.vtkLineSource()
    elif obj.vector_type == "3D":
        src = vtk.vtkConeSource()
        src.SetHeight(0.4)
        src.SetRadius(0.15)
    else:  # Standard | Triangle
        src = vtk.vtkArrowSource()
        src.SetTipLength(0.35)
        src.SetTipRadius(0.1)
        src.SetShaftRadius(0.04)
    glyph = vtk.vtkGlyph3D()
    glyph.SetInputData(pts_pd)
    glyph.SetSourceConnection(src.GetOutputPort())
    glyph.SetInputArrayToProcess(
        1, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS,
        vec.GetName())
    glyph.SetScaleFactor(scale)
    glyph.OrientOn()
    glyph.SetVectorModeToUseVector()
    glyph.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(glyph.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if obj.vector_mono_color:
        actor.GetProperty().SetColor(*obj.vector_mono_color)
    if obj.vector_transparent:
        actor.GetProperty().SetOpacity(0.5)
    return actor


def vector_actor(ugrid, ff: FieldFile, obj,
                 cell_centered: bool) -> Optional["vtk.vtkActor"]:
    """Vector arrows on the cut plane (Uniform/Center/Nodes/Actual).

    Cell-centred vector fields are first converted to point data
    (``vtkCellDataToPointData``) so ``vtkCutter`` can interpolate the vector
    onto the cut; glyph placement then follows scPOST's Location radio:

    - ``Nodes``   — arrows at cut mesh vertices
    - ``Center``  — arrows at cut triangle centres
    - ``Uniform`` — arrows on an even grid over the cut bounding box
    - ``Actual``  — arrows on an even grid clipped to the cut extent
    """
    base = obj.vector_var
    if not base:
        return None
    vec = attach_vector(ugrid, ff, base, cell_centered)
    if vec is None:
        return None

    # Make the vector field point data so cutting interpolates it.
    work = ugrid
    if cell_centered:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(ugrid)
        c2p.PassCellDataOn()
        c2p.Update()
        work = c2p.GetOutput()

    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(plane_from_object(obj))
    cutter.SetInputData(work)
    cutter.Update()
    cut = cutter.GetOutput()
    if cut.GetNumberOfPoints() == 0:
        return None

    location = getattr(obj, "vector_location", "Uniform") or "Uniform"
    if location == "Nodes":
        glyph_in = cut
    elif location == "Center":
        centers = vtk.vtkCellCenters()
        centers.SetInputData(cut)
        centers.Update()
        probe = vtk.vtkProbeFilter()
        probe.SetInputData(centers.GetOutput())
        probe.SetSourceData(cut)
        probe.Update()
        glyph_in = probe.GetOutput()
    else:  # Uniform | Actual
        pts = _uniform_points_on_cut(ugrid, obj)
        probe = vtk.vtkProbeFilter()
        probe.SetInputData(pts)
        probe.SetSourceData(cut)
        probe.Update()
        glyph_in = probe.GetOutput()
    # Probe/cutter copy arrays but lose the active-attribute flag.
    glyph_in.GetPointData().SetActiveVectors(base)
    scale = _vector_scale(ugrid, obj)
    return _glyph_actor(glyph_in, obj, scale)


def _uniform_points_on_cut(ugrid, obj):
    """Evenly spaced sample points on the plane (scPOST Uniform location)."""
    b = ugrid.GetBounds()
    u = max(b[1] - b[0], 1e-9)
    v = max(b[3] - b[2], 1e-9)
    spacing = getattr(obj, "vector_space_u", 1.0) or 1.0
    step = max(u, v) / 40.0 * spacing
    nx = max(2, int(u / max(step, 1e-9)))
    ny = max(2, int(v / max(step, 1e-9)))
    pts = vtk.vtkPolyData()
    points = vtk.vtkPoints()
    origin = np.asarray(obj.point)
    n = np.asarray(obj.normal)
    e1 = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(e1, n)) > 0.99:
        e1 = np.array([0.0, 1.0, 0.0])
    e1 = e1 - np.dot(e1, n) * n
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    for i in range(nx):
        for j in range(ny):
            p = origin + (i - nx / 2) * step * e1 + (j - ny / 2) * step * e2
            points.InsertNextPoint(*p)
    pts.SetPoints(points)
    return pts


def _vector_scale(ugrid, obj) -> float:
    b = ugrid.GetBounds()
    w = max(b[1] - b[0], b[3] - b[2], b[5] - b[4], 1e-9)
    return 0.05 * w * getattr(obj, "vector_scale_length", 1.0)


# ---------------------------------------------------------------------------
# Mesh / Boundary / Subline
# ---------------------------------------------------------------------------

def mesh_lines_actor(pd, obj) -> "vtk.vtkActor":
    """Mesh intersection lines on the cut (vtkExtractEdges)."""
    edges = vtk.vtkExtractEdges()
    edges.SetInputData(pd)
    edges.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(edges.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    prop.SetColor(*obj.mesh_color)
    prop.SetLineWidth(obj.mesh_thickness)
    if obj.mesh_transparent:
        prop.SetOpacity(0.5)
    return actor


def boundary_line_actor(ff, obj) -> Optional["vtk.vtkActor"]:
    """Boundary: line of intersection between cut plane and boundary surface."""
    if not obj.boundary_line:
        return None
    pd = _boundary_polydata(ff)
    if pd is None:
        return None
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(plane_from_object(obj))
    cutter.SetInputData(pd)
    cutter.Update()
    if cutter.GetOutput().GetNumberOfPoints() == 0:
        return None
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(cutter.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    if obj.boundary_color is None:
        prop.SetColor(0.0, 0.0, 0.0)
    else:
        prop.SetColor(*obj.boundary_color)
    prop.SetLineWidth(max(1, obj.mesh_thickness))
    if obj.boundary_transparent:
        prop.SetOpacity(0.5)
    return actor


def _boundary_polydata(ff: FieldFile):
    if ff.kind == "fld":
        return _fld_boundary_polydata(ff)
    ld = ff.link_data
    if ld is None or ff.vertices is None:
        return None
    face_nodes = np.asarray(ld["face_nodes"], dtype=np.int64)
    face_offsets = np.asarray(ld["face_offsets"], dtype=np.int64)
    neighbour = np.asarray(ld["neighbour"], dtype=np.int64)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    bnd = np.flatnonzero(neighbour == -1)
    if bnd.size == 0:
        bnd = np.arange(max(0, len(face_offsets) - 1))
    points = vtk.vtkPoints()
    points.SetData(_vns.numpy_to_vtk(verts, deep=True))
    polys = vtk.vtkCellArray()
    ids = vtk.vtkIdList()
    for fi in bnd:
        lo, hi = int(face_offsets[fi]), int(face_offsets[fi + 1])
        ids.Reset()
        for vi in face_nodes[lo:hi]:
            ids.InsertNextId(int(vi))
        polys.InsertNextCell(ids)
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetPolys(polys)
    return pd


def _fld_boundary_polydata(ff: FieldFile):
    if ff.vertices is None or ff.cell_conn is None:
        return None
    verts = np.asarray(ff.vertices, dtype=np.float64)
    conn = np.asarray(ff.cell_conn, dtype=np.int64)
    points = vtk.vtkPoints()
    points.SetData(_vns.numpy_to_vtk(verts, deep=True))
    polys = vtk.vtkCellArray()
    # exterior faces: a hex face is exterior if not shared by another cell
    faces = _exterior_hex_faces(conn)
    ids = vtk.vtkIdList()
    for f in faces:
        ids.Reset()
        for vi in f:
            ids.InsertNextId(int(vi))
        polys.InsertNextCell(ids)
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetPolys(polys)
    return pd


def _exterior_hex_faces(conn: np.ndarray):
    from collections import Counter
    hex_faces = [
        (0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (0, 3, 7, 4),
    ]
    counts: Counter = Counter()
    for row in conn:
        for f in hex_faces:
            key = tuple(sorted(int(row[i]) for i in f))
            counts[key] += 1
    out = []
    for row in conn:
        for f in hex_faces:
            key = tuple(sorted(int(row[i]) for i in f))
            if counts[key] == 1:
                out.append([int(row[i]) for i in f])
    return out


def subline_actor(ff, obj) -> Optional["vtk.vtkActor"]:
    """External frame + display-location marks (Subline tab)."""
    if not obj.subline_external:
        return None
    pd = _boundary_polydata(ff)
    if pd is None:
        return None
    b = pd.GetBounds()
    p = vtk.vtkPlane()
    p.SetOrigin(*obj.point)
    p.SetNormal(*obj.normal)
    cutter = vtk.vtkCutter()
    cutter.SetCutFunction(p)
    cutter.SetInputData(pd)
    cutter.Update()
    frame = vtk.vtkPolyData()
    fpts = vtk.vtkPoints()
    fpts.InsertNextPoint(b[0], b[2], b[4])
    fpts.InsertNextPoint(b[1], b[2], b[4])
    fpts.InsertNextPoint(b[1], b[3], b[4])
    fpts.InsertNextPoint(b[0], b[3], b[4])
    fpts.InsertNextPoint(b[0], b[2], b[5])
    fpts.InsertNextPoint(b[1], b[2], b[5])
    fpts.InsertNextPoint(b[1], b[3], b[5])
    fpts.InsertNextPoint(b[0], b[3], b[5])
    frame.SetPoints(fpts)
    flines = vtk.vtkCellArray()
    for e in ((0, 1), (1, 2), (2, 3), (3, 0),
              (4, 5), (5, 6), (6, 7), (7, 4),
              (0, 4), (1, 5), (2, 6), (3, 7)):
        line = vtk.vtkLine()
        line.GetPointIds().SetId(0, e[0])
        line.GetPointIds().SetId(1, e[1])
        flines.InsertNextCell(line)
    frame.SetLines(flines)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(frame)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.5, 0.5, 0.5)
    actor.GetProperty().SetLineWidth(1)
    return actor


# ---------------------------------------------------------------------------
# Trim
# ---------------------------------------------------------------------------

def trim_cut(pd, obj) -> "vtk.vtkPolyData":
    """Clip the cut against coordinate ranges (Trim tab).

    ``obj.trim_{x,y,z}{min,max}`` are ``Optional[float]`` coordinate bounds;
    ``None`` means that side is not trimmed. The positive side of each bound
    plane is kept (scPOST-style near/far keep).
    """
    out = pd
    for axis in ("X", "Y", "Z"):
        lo = getattr(obj, f"trim_{axis.lower()}min", None)
        hi = getattr(obj, f"trim_{axis.lower()}max", None)
        if lo is None and hi is None:
            continue
        i = {"X": 0, "Y": 1, "Z": 2}[axis]
        for bound in (lo, hi):
            if bound is None:
                continue
            clip = vtk.vtkPlane()
            clip.SetOrigin(*_point_axis(i, bound))
            # keep coords >= lo  and  coords <= hi
            clip.SetNormal(*_axis_vec(i, 1.0 if bound is lo else -1.0))
            clipper = vtk.vtkClipPolyData()
            clipper.SetInputData(out)
            clipper.SetClipFunction(clip)
            clipper.Update()
            out = clipper.GetOutput()
    return out


def _axis_vec(i: int, s: float):
    v = [0.0, 0.0, 0.0]
    v[i] = s
    return tuple(v)


def _point_axis(i: int, v: float):
    p = [0.0, 0.0, 0.0]
    p[i] = v
    return tuple(p)


# ---------------------------------------------------------------------------
# Automove (scPOST CutPlaneAutoMove@pst)
# ---------------------------------------------------------------------------

def automove_coordinate(obj, t: float, frames: Optional[int] = None) -> tuple:
    """Plane position/rotation for animation frame ``t``.

    Methods: Line / Sin / Cos / Rotation. ``t`` in [0, 1] unless loop.
    Returns ``(point, normal)`` of the moving plane.
    """
    method = (getattr(obj, "automove_method", "Line") or "Line")
    loop = bool(getattr(obj, "automove_loop", False))
    if frames:
        t = (t % frames) / max(1, frames - 1)
    if loop:
        t = t % 1.0
    t = max(0.0, min(1.0, t))

    start_p = np.asarray(getattr(obj, "automove_start_point", obj.point),
                         dtype=np.float64)
    ref_p = np.asarray(getattr(obj, "automove_ref_point", obj.point),
                       dtype=np.float64)
    start_n = np.asarray(getattr(obj, "automove_start_normal", obj.normal),
                         dtype=np.float64)
    ref_n = np.asarray(getattr(obj, "automove_ref_normal", obj.normal),
                       dtype=np.float64)

    if method == "Rotation":
        # rotate start plane about automove_axis_point/automove_axis_dir
        axp = np.asarray(getattr(obj, "automove_axis_point", start_p),
                         dtype=np.float64)
        axd = np.asarray(getattr(obj, "automove_axis_dir", np.array([0, 0, 1])),
                         dtype=np.float64)
        axd = axd / np.linalg.norm(axd)
        angle = float(getattr(obj, "automove_angle", 0.0)) * t + \
            float(getattr(obj, "automove_offset", 0.0))
        p = _rotate_around(axp, start_p, axd, angle)
        n = _rotate_vector(start_n, axd, angle)
        return tuple(p), tuple(n)

    # Line / Sin / Cos: interpolate position along p_ref - p_start
    f = t
    if method == "Sin":
        f = np.sin(0.5 * np.pi * t)
    elif method == "Cos":
        f = 1.0 - np.cos(0.5 * np.pi * t)
    p = start_p + f * (ref_p - start_p)
    n = start_n + f * (ref_n - start_n)
    n = n / (np.linalg.norm(n) + 1e-12)
    return tuple(p), tuple(n)


def _rotate_around(origin, point, axis, angle_deg):
    """Rodrigues rotation of ``point`` about ``axis`` through ``origin``."""
    import math
    a = math.radians(angle_deg)
    k = np.asarray(axis)
    v = np.asarray(point) - np.asarray(origin)
    cos, sin = math.cos(a), math.sin(a)
    vrot = (v * cos + np.cross(k, v) * sin
            + k * np.dot(k, v) * (1 - cos))
    return np.asarray(origin) + vrot


def _rotate_vector(v, axis, angle_deg):
    import math
    a = math.radians(angle_deg)
    k = np.asarray(axis)
    v = np.asarray(v)
    cos, sin = math.cos(a), math.sin(a)
    return (v * cos + np.cross(k, v) * sin + k * np.dot(k, v) * (1 - cos))


# ---------------------------------------------------------------------------
# Integration (scPOST Scalar/Vector Integration)
# ---------------------------------------------------------------------------

def integrate_cut(pd, scalar_name: Optional[str],
                  vector: Optional[np.ndarray] = None):
    """Integrate over the cut triangles.

    Returns dict with ``area``, ``sum``/``in_normal``/``in_axes`` and
    corresponding ``average`` fields, mirroring the scPOST readout.
    """
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(pd)
    normals.ComputePointNormalsOn()
    normals.ComputeCellNormalsOn()
    normals.Update()
    cut = normals.GetOutput()
    cell_normals = cut.GetCellData().GetNormals()

    pd_array = cut.GetPointData().GetArray(scalar_name) if scalar_name else None
    cd_array = cut.GetCellData().GetArray(scalar_name) if scalar_name else None

    area = 0.0
    scalar_sum = 0.0
    vec_normal = np.zeros(3)
    vec_axes = np.zeros(3)
    n_cells = cut.GetNumberOfCells()

    for c in range(n_cells):
        cell = cut.GetCell(c)
        ids = cell.GetPointIds()
        n = ids.GetNumberOfIds()
        if n < 3:
            continue
        p0 = np.array(cut.GetPoint(ids.GetId(0)))
        p1 = np.array(cut.GetPoint(ids.GetId(1)))
        p2 = np.array(cut.GetPoint(ids.GetId(2)))
        tri_area = 0.5 * np.linalg.norm(np.cross(p1 - p0, p2 - p0))
        area += tri_area
        cn = np.array(cell_normals.GetTuple3(c))
        # scalar: cell-centred → per-triangle value; node-centred → mean of
        # vertices
        if scalar_name is not None:
            if cd_array is not None:
                s = float(cd_array.GetTuple1(c))
            elif pd_array is not None:
                vals = [pd_array.GetTuple1(ids.GetId(k)) for k in range(n)]
                s = float(np.mean(vals))
            else:
                s = 0.0
            scalar_sum += s * tri_area
        if vector is not None:
            vsum = np.zeros(3)
            for k in range(n):
                vsum += np.asarray(vector[ids.GetId(k)]) / n
            vec_normal += np.dot(vsum, cn) * tri_area
            vec_axes += vsum * tri_area

    out = {"area": area}
    if scalar_name is not None:
        out["sum"] = scalar_sum
        out["average"] = scalar_sum / area if area else 0.0
    if vector is not None:
        out["in_normal"] = float(vec_normal)
        out["in_axes"] = tuple(vec_axes)
        out["avg_normal"] = float(vec_normal) / area if area else 0.0
        out["avg_axes"] = tuple(vec_axes / area) if area else (0, 0, 0)
    return out


def build_plane_actors(ff: FieldFile, obj, ugrid=None,
                       cell_centered: bool = True) -> dict:
    """High-level entry: produce every actor for a PlaneObject.

    Returns ``{"plane", "contour", "contour_line", "vector", "mesh",
    "boundary", "subline"}`` (keys present only when enabled).
    """
    out: dict = {}
    if not _HAS_VTK:
        return out
    if ugrid is None:
        ugrid, cell_centered = build_ugrid(ff)
    if ugrid is None:
        return out

    # Attach contour scalar before cutting so vtkCutter propagates it.
    if (getattr(obj, "show_contour", False) and getattr(obj, "contour_var", "")
            and obj.contour_var in ff.variables):
        attach_scalar(ugrid, ff, obj.contour_var, cell_centered)

    # Cut once
    cut = cut_grid(ugrid, obj)
    if cut.GetNumberOfPoints() == 0:
        return out

    # Trim
    cut = trim_cut(cut, obj)

    # Contour
    if (getattr(obj, "show_contour", False) and getattr(obj, "contour_var", "")
            and obj.contour_var in ff.variables):
        out["contour"] = contour_actor(cut, obj.contour_var, obj)
        if getattr(obj, "contour_line", False):
            out["contour_line"] = contour_line_actor(
                cut, obj.contour_var, obj)

    # Vector
    if getattr(obj, "show_vector", False) and getattr(obj, "vector_var", ""):
        actor = vector_actor(ugrid, ff, obj, cell_centered)
        if actor is not None:
            out["vector"] = actor

    # Mesh lines on the cut
    if getattr(obj, "show_mesh", False) or getattr(obj, "mesh_display", False):
        out["mesh"] = mesh_lines_actor(cut, obj)

    # Boundary line (cut-plane × boundary surface)
    if getattr(obj, "boundary_line", False):
        b = boundary_line_actor(ff, obj)
        if b is not None:
            out["boundary"] = b

    # Subline external frame
    if getattr(obj, "subline_external", False):
        s = subline_actor(ff, obj)
        if s is not None:
            out["subline"] = s

    return out
