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

def cell_filter_mask(ff: FieldFile, obj) -> Optional[np.ndarray]:
    """Boolean mask over cells for MAT / Volume Region filtering (P3.8).

    - FLD: ``display_mats`` selects cells whose material id (``ff.material``,
      1-based) is in the set. Empty list → all cells (None).
    - FPH: ``display_volume_regions`` selects cells whose volume-region /
      part classification matches (via ``classify_volume_region_cells``).
      Empty list → all cells (None).

    Returns ``None`` when no filter applies so callers can keep the full
    grid unchanged.
    """
    mats = getattr(obj, "display_mats", None) or []
    regions = getattr(obj, "display_volume_regions", None) or []
    if not mats and not regions:
        return None

    if ff.kind == "fph":
        if not regions:
            return None
        from ..crdl.mesh_gph import classify_volume_region_cells
        cvol = ff.cvol_id
        parts = ff.parts_with_cvol or []
        n = ff.n_cells
        if cvol is None or len(cvol) != n or not parts:
            return None
        keep = np.zeros(n, dtype=bool)
        for name in regions:
            keep |= classify_volume_region_cells(name, parts, cvol, n)
        return keep

    # FLD material filter
    mat = ff.material
    if mat is None or len(mat) != ff.n_cells:
        return None
    want = {int(m) for m in mats}
    return np.isin(np.asarray(mat, dtype=np.int64), list(want))


def filter_ugrid_cells(ugrid, mask: Optional[np.ndarray]):
    """Return a copy of ``ugrid`` keeping only cells where ``mask`` is True.

    ``vtkThreshold`` renumbers the points; attached CellData/PointData arrays
    are preserved for the surviving cells.
    """
    if mask is None or mask.all():
        return ugrid
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(mask, dtype=np.float64),
                           deep=True)
    fa.SetName("__keep__")
    ugrid.GetCellData().AddArray(fa)
    th = vtk.vtkThreshold()
    th.SetInputData(ugrid)
    th.SetInputArrayToProcess(
        0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS, "__keep__")
    th.SetLowerThreshold(0.5)
    th.SetUpperThreshold(1.5)
    th.Update()
    return th.GetOutput()


def _masked_cell_rows(ff: FieldFile, mask: Optional[np.ndarray]):
    """Indices of cells to keep (all when ``mask`` is None/empty)."""
    if mask is None or mask.all():
        return None
    return np.flatnonzero(mask)


def _slice_field_array(arr: Optional[np.ndarray],
                       rows: Optional[np.ndarray]):
    """Subset a per-cell field array to the kept-cell rows."""
    if arr is None:
        return None
    if rows is None:
        return arr
    return np.ascontiguousarray(np.asarray(arr)[rows], dtype=np.float64)


def build_ugrid(ff: FieldFile, cell_mask: Optional[np.ndarray] = None):
    """Return ``(ugrid, cell_centered: bool)`` for cutting.

    FPH: cell-centred fields → build cells from ``LS_Links`` owner/neighbour
    faces (``vtkConvexPointSet`` for general polyhedra). Returns
    ``cell_centered=True`` so scalar data is attached as CellData.

    FLD: hexahedra from ``LS_Elements``; node fields → PointData
    (``cell_centered=False``).

    ``cell_mask`` (optional, from :func:`cell_filter_mask`) keeps only the
    surviving cells (MAT / Volume Region filtering). FLD node-centred arrays
    stay full-length; FPH cell-centred arrays are subset to the kept rows.
    """
    if not _HAS_VTK:
        return None, True
    rows = _masked_cell_rows(ff, cell_mask)
    # P3.5: reuse the last-built grid when nothing changed (animation frames)
    cache = getattr(ff, "_ugrid_cache", None)
    key = None if cell_mask is None else (cell_mask.tobytes(),
                                          int(np.count_nonzero(cell_mask)))
    if cache is not None and cache[0] == key:
        return cache[1], cache[2]
    if ff.kind == "fph":
        ug = _build_fph_ugrid(ff, rows), True
    else:
        ug = _build_fld_ugrid(ff, rows), False
    try:
        ff._ugrid_cache = (key, ug[0], ug[1])
    except Exception:  # pragma: no cover - frozen dataclass
        pass
    return ug


def _build_fph_ugrid(ff: FieldFile, rows=None):
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
    if rows is not None:
        keep = rows
    else:
        keep = range(n_cells)
    for c in keep:
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


def _build_fld_ugrid(ff: FieldFile, rows=None):
    if ff.vertices is None or ff.cell_conn is None:
        return None
    verts = np.asarray(ff.vertices, dtype=np.float64)
    conn = np.asarray(ff.cell_conn, dtype=np.int64)
    ctypes = getattr(ff, "cell_types", None)
    points = vtk.vtkPoints()
    points.SetData(_vns.numpy_to_vtk(verts, deep=True))
    ug = vtk.vtkUnstructuredGrid()
    ug.SetPoints(points)
    cells = vtk.vtkCellArray()
    if rows is not None:
        sel = conn[rows]
        sel_types = ctypes[rows] if ctypes is not None else None
    else:
        sel = conn
        sel_types = ctypes
    if sel_types is None:
        for row in sel:
            h = vtk.vtkHexahedron()
            for k in range(8):
                h.GetPointIds().SetId(k, int(row[k]))
            cells.InsertNextCell(h)
        ug.SetCells(vtk.VTK_HEXAHEDRON, cells)
        return ug
    # CGNS / mixed types: build per-cell vtk cells (P1.2)
    makers = {
        10: (vtk.vtkTetra, 4),
        12: (vtk.vtkHexahedron, 8),
        13: (vtk.vtkWedge, 6),
        14: (vtk.vtkPyramid, 5),
    }
    for c, row in enumerate(sel):
        t = int(sel_types[c])
        maker, nn = makers.get(t, (vtk.vtkHexahedron, 8))
        cell = maker()
        n = min(nn, len(row))
        for k in range(n):
            cell.GetPointIds().SetId(k, int(row[k]))
        cells.InsertNextCell(cell)
    ug.SetCells(vtk.VTK_UNSTRUCTURED_GRID, cells)
    return ug


def _cell_centers(ugrid):
    cc = vtk.vtkCellCenters()
    cc.SetInputData(ugrid)
    cc.Update()
    return cc.GetOutput()


def attach_scalar(ugrid, ff: FieldFile, var_name: str, cell_centered: bool,
                  rows=None):
    """Attach the variable array to the grid. Returns vtkDataArray or None.

    ``rows`` (optional kept-cell indices) subsets cell-centred arrays so they
    match a MAT / Volume Region filtered grid.
    """
    if var_name is None or var_name == "":
        return None
    arr = ff.variable_array(var_name)
    if arr is None:
        return None
    data = arr if rows is None or not cell_centered else np.asarray(arr)[rows]
    fa = _vns.numpy_to_vtk(np.ascontiguousarray(data, dtype=np.float64),
                           deep=True)
    fa.SetName(var_name)
    if cell_centered:
        ugrid.GetCellData().SetScalars(fa)
    else:
        ugrid.GetPointData().SetScalars(fa)
    return fa


def attach_vector(ugrid, ff: FieldFile, base: str, cell_centered: bool,
                  rows=None):
    """Attach a vector field (``base``X/Y/Z) to the grid."""
    for suff in ("X", "Y", "Z"):
        arr = ff.variable_array(f"{base}{suff}")
        if arr is None:
            return None
    vx = np.asarray(ff.variable_array(f"{base}X"), dtype=np.float64)
    vy = np.asarray(ff.variable_array(f"{base}Y"), dtype=np.float64)
    vz = np.asarray(ff.variable_array(f"{base}Z"), dtype=np.float64)
    if cell_centered and rows is not None:
        vx = vx[rows]
        vy = vy[rows]
        vz = vz[rows]
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

    Honour flags: ``contour_transparent``, ``contour_mono_color``
    (flat colour instead of scalar map), ``contour_luster`` (specular) and
    ``contour_water`` (higher transparency/sheen).
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
    prop = actor.GetProperty()
    if obj.contour_mono_color:
        mapper.ScalarVisibilityOff()
        prop.SetColor(*obj.contour_mono_rgb)
    opacity = 1.0
    if obj.contour_transparent:
        opacity = 0.5
    if obj.contour_water:
        opacity = min(opacity, 0.65)
        prop.SetSpecular(0.9)
        prop.SetSpecularPower(60.0)
        prop.SetInterpolationToGouraud()
    if obj.contour_luster:
        prop.SetSpecular(0.5)
        prop.SetSpecularPower(20.0)
    prop.SetOpacity(opacity)
    if not (obj.contour_water or obj.contour_luster):
        prop.SetInterpolationToPhong()
    return actor


def contour_value_actor(pd, scalar_array_name: str, obj) -> "vtk.vtkActor":
    """Value labels over the cut (scPOST Contour → Value)."""
    # keep only points carrying a value (deduplicate for labels)
    dd = vtk.vtkCleanPolyData()
    dd.SetInputData(pd)
    dd.Update()
    lm = vtk.vtkLabeledDataMapper()
    lm.SetInputConnection(dd.GetOutputPort())
    lm.SetLabelModeToLabelFieldData()
    lm.SetFieldDataName(scalar_array_name)
    tp = lm.GetLabelTextProperty()
    tp.SetFontSize(max(8, int(getattr(obj, "font_size", 9) or 9)))
    tp.SetFontFamilyToCourier()
    tp.SetColor(0.0, 0.0, 0.0)
    actor = vtk.vtkActor2D()
    actor.SetMapper(lm)
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
# Colorbar / Texture / Font (P3.9)
# ---------------------------------------------------------------------------

def colorbar_actor(mapper, obj, title: str = "") -> Optional["vtk.vtkScalarBarActor"]:
    """Global-style ``vtkScalarBarActor`` for a plane's contour/vector map.

    The plane's Others tab names a colorbar via ``colorbar_contour`` /
    ``colorbar_vector``; when set, the matching mapper's lookup table is
    shown. Title text and label font honour the Font tab.
    """
    if not _HAS_VTK:
        return None
    lut = mapper.GetLookupTable()
    if lut is None:
        return None
    sb = vtk.vtkScalarBarActor()
    sb.SetLookupTable(lut)
    sb.SetNumberOfLabels(7)
    sb.SetMaximumNumberOfColors(256)
    sb.SetOrientationToHorizontal()
    sb.SetPosition(0.12, 0.03)
    sb.SetWidth(0.55)
    sb.SetHeight(0.06)
    if title:
        sb.SetTitle(title)
    fp = sb.GetLabelTextProperty()
    fp.SetFontFamilyToArial()
    fp.SetFontSize(max(8, int(getattr(obj, "font_size", 9) or 9)))
    fp.SetColor(0.0, 0.0, 0.0)
    tp = sb.GetTitleTextProperty()
    tp.SetFontFamilyToArial()
    tp.SetFontSize(max(8, int(getattr(obj, "font_size", 9) or 9)) + 2)
    tp.SetColor(0.0, 0.0, 0.0)
    return sb


def texture_actor(cut, obj) -> Optional["vtk.vtkActor"]:
    """Apply ``texture_file`` (BMP/PNG/JPG) onto the cut plane (P3.9).

    ``vtkTextureMapToPlane`` generates UVs from the cut's own coordinates,
    scaled/rotated by the Texture tab. Returns ``None`` when disabled or the
    image can't be loaded.
    """
    if not _HAS_VTK:
        return None
    if not getattr(obj, "texture_enabled", False):
        return None
    path = getattr(obj, "texture_file", "") or ""
    if not path:
        return None
    import os
    reader = None
    ext = os.path.splitext(path)[1].lower()
    if ext == ".bmp":
        reader = vtk.vtkBMPReader()
    elif ext in (".png",):
        reader = vtk.vtkPNGReader()
    elif ext in (".jpg", ".jpeg"):
        reader = vtk.vtkJPEGReader()
    else:
        return None
    reader.SetFileName(path)
    try:
        reader.Update()
    except Exception:
        return None
    tex = vtk.vtkTexture()
    tex.SetInputConnection(reader.GetOutputPort())
    tex.InterpolateOn()
    tex.RepeatOff()

    tmap = vtk.vtkTextureMapToPlane()
    tmap.SetInputData(cut)
    scale = float(getattr(obj, "texture_scale", 1.0) or 1.0)
    ang = float(getattr(obj, "texture_angle", 0.0) or 0.0)
    if scale != 1.0 or ang != 0.0:
        tr = vtk.vtkTransformTextureCoords()
        tr.SetInputConnection(tmap.GetOutputPort())
        tr.SetScale(1.0 / scale, 1.0 / scale, 1.0)
        if ang:
            import math
            tr.SetOrigin(0.5, 0.5, 0.0)
            tr.SetPosition(math.radians(ang), 0.0, 0.0)
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tr.GetOutputPort())
    else:
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(tmap.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.SetTexture(tex)
    return actor


def _apply_font(actor, obj) -> None:
    """Apply Font tab to 2D text actors (contour value / pick numbers)."""
    if not _HAS_VTK or actor is None:
        return
    size = max(8, int(getattr(obj, "font_size", 9) or 9))
    tp = None
    if isinstance(actor, vtk.vtkActor2D):
        m = actor.GetMapper()
        if m is not None and hasattr(m, "GetLabelTextProperty"):
            tp = m.GetLabelTextProperty()
    if tp is None:
        return
    tp.SetFontSize(size)
    tp.SetFontFamilyToArial()


# ---------------------------------------------------------------------------
# Vector
# ---------------------------------------------------------------------------

def _glyph_actor(pts_pd, obj, scale: float,
                 project_normal: Optional[np.ndarray] = None) -> "vtk.vtkActor":
    """Orient + scale arrow glyphs from ``pts_pd`` PointData vectors.

    ``project_normal`` (unit vector, optional) zeroes the normal component of
    each vector (scPOST Vector → Projection). ``vector_constant_length`` makes
    every arrow the same length (unit direction × scale).
    """
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
        src.SetTipLength(max(0.05, float(getattr(obj, "vector_arrow_angle",
                                                 1.0) or 1.0) * 0.35))
        src.SetTipRadius(max(0.05, float(getattr(obj, "vector_arrow_size",
                                                 1.0) or 1.0) * 0.1))
        src.SetShaftRadius(0.04)

    work = pts_pd
    if project_normal is not None or getattr(obj, "vector_constant_length",
                                             False):
        arr = _vns.vtk_to_numpy(vec).reshape(-1, 3).astype(np.float64)
        if project_normal is not None:
            n = np.asarray(project_normal)
            arr = arr - np.outer(np.dot(arr, n), n)
        if getattr(obj, "vector_constant_length", False):
            lens = np.linalg.norm(arr, axis=1)
            ok = lens > 1e-12
            arr[ok] = arr[ok] / lens[ok, None]
        new_vec = _vns.numpy_to_vtk(arr, deep=True)
        new_vec.SetName(vec.GetName())
        work = vtk.vtkPolyData()
        work.ShallowCopy(pts_pd)
        work.GetPointData().SetVectors(new_vec)

    glyph = vtk.vtkGlyph3D()
    glyph.SetInputData(work)
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
                 cell_centered: bool, rows=None) -> Optional["vtk.vtkActor"]:
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
    vec = attach_vector(ugrid, ff, base, cell_centered, rows=rows)
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
    proj = None
    if getattr(obj, "vector_projection", False):
        proj = np.asarray(getattr(obj, "normal", (0.0, 0.0, 1.0)))
        proj = proj / (np.linalg.norm(proj) + 1e-12)
    return _glyph_actor(glyph_in, obj, scale, project_normal=proj)


def cut_vector_array(ugrid, ff: FieldFile, obj,
                     cell_centered: bool) -> Optional[np.ndarray]:
    """Interpolated vector field on the cut vertices, as ``(n_pts, 3)``.

    Cell-centred vectors are converted to point data first so ``vtkCutter``
    interpolates them. Used by Vector Integration (``∫v·n dS``).
    """
    base = obj.vector_var
    if not base:
        return None
    vec = attach_vector(ugrid, ff, base, cell_centered)
    if vec is None:
        return None
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
    arr = cut.GetPointData().GetVectors(base)
    if arr is None:
        arr = cut.GetPointData().GetArray(base)
    if arr is None:
        return None
    return np.asarray(_vns.vtk_to_numpy(arr), dtype=np.float64).reshape(-1, 3)


def cut_with_fields(ugrid, ff: FieldFile, obj, cell_centered: bool,
                    scalar: Optional[str] = None,
                    vector: Optional[str] = None):
    """Attach scalar + vector, convert to point data, cut once.

    Returns ``(cut_polydata, vector_np_or_None)``. The single cut carries the
    scalar in CellData and the interpolated vector in PointData, so Scalar and
    Vector integration run on one consistent surface.
    """
    if scalar:
        attach_scalar(ugrid, ff, scalar, cell_centered)
    if vector:
        attach_vector(ugrid, ff, vector, cell_centered)
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
        return cut, None
    vec = None
    if vector:
        arr = cut.GetPointData().GetVectors(vector)
        if arr is None:
            arr = cut.GetPointData().GetArray(vector)
        if arr is not None:
            vec = np.asarray(_vns.vtk_to_numpy(arr), dtype=np.float64) \
                .reshape(-1, 3)
    return cut, vec


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
    from .material import apply_sheen
    apply_sheen(prop, getattr(obj, "mesh_luster", False),
                getattr(obj, "mesh_water", False))
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

def trim_by_objects(pd, ff, obj, siblings=None) -> "vtk.vtkPolyData":
    """Clip the cut against objects listed in the Trim 'Trimmed by' tab.

    Each sibling whose label matches 'obj.trim_objects' contributes an
    implicit distance field from its boundary surface (P1.6); the cut is
    kept on the inside (distance <= 0) side of every such surface.  This
    approximates the scPOST Trim-by-object region.
    """
    names = set(getattr(obj, "trim_objects", None) or [])
    if not names or not siblings:
        return pd
    from . import surface as surface_render
    for sib in siblings:
        if getattr(sib, "kind", "") != "surface":
            continue
        if getattr(sib, "label", "") not in names:
            continue
        spd, _, _ = surface_render.build_surface_polydata(ff, sib)
        if spd is None or spd.GetNumberOfCells() == 0:
            continue
        imp = vtk.vtkImplicitPolyDataDistance()
        imp.SetInput(spd)
        clip = vtk.vtkClipPolyData()
        clip.SetInputData(pd)
        clip.SetClipFunction(imp)
        clip.InsideOutOff()
        clip.Update()
        pd = clip.GetOutput()
    return pd


def _limited_basis(normal):
    """Two orthonormal in-plane unit vectors (u, v) from the plane normal."""
    n = np.asarray(normal, dtype=np.float64)
    norm = float(np.linalg.norm(n))
    if norm < 1e-12:
        n = np.array([0.0, 0.0, 1.0])
    else:
        n = n / norm
    ref = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(n, ref)
    u = u / max(1e-12, float(np.linalg.norm(u)))
    v = np.cross(n, u)
    v = v / max(1e-12, float(np.linalg.norm(v)))
    return u, v


def _limited_clip(pd, obj):
    """Clip the cut to a finite width x height rectangle on the plane (5c).

    The rectangle is centred on the plane point, width along the in-plane u
    basis vector and height along v (instead of an axis-aligned cube).
    """
    if not getattr(obj, "limited", False):
        return pd
    p = np.asarray(getattr(obj, "point", (0.0, 0.0, 0.0)), dtype=np.float64)
    n = np.asarray(getattr(obj, "normal", (0.0, 0.0, 1.0)), dtype=np.float64)
    size = float(getattr(obj, "limited_size", 1.0) or 1.0)
    w = max(1e-9, float(getattr(obj, "limited_width", size) or size))
    h = max(1e-9, float(getattr(obj, "limited_height", size) or size))
    u, v = _limited_basis(n)
    for axis, half in ((u, w / 2.0), (v, h / 2.0)):
        for sign in (1.0, -1.0):
            origin = p + sign * half * axis
            normal = sign * axis
            plane = vtk.vtkPlane()
            plane.SetOrigin(*tuple(origin))
            plane.SetNormal(*tuple(normal))
            clip = vtk.vtkClipPolyData()
            clip.SetInputData(pd)
            clip.SetClipFunction(plane)
            clip.InsideOutOn()
            clip.Update()
            pd = clip.GetOutput()
    return pd


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
        for bound, sign in ((lo, 1.0), (hi, -1.0)):
            if bound is None:
                continue
            clip = vtk.vtkPlane()
            clip.SetOrigin(*_point_axis(i, bound))
            # keep coords >= lo  and  coords <= hi
            clip.SetNormal(*_axis_vec(i, sign))
            clipper = vtk.vtkClipPolyData()
            clipper.SetInputData(out)
            clipper.SetClipFunction(clip)
            clipper.Update()
            out = clipper.GetOutput()
    return out


def clip_cut(pd, obj) -> "vtk.vtkPolyData":
    """Clip the cut against the Clip tab X/Y region.

    ``obj.clip_enabled`` gates the clip; ``clip_xmin/xmax/ymin/ymax`` are
    world-coordinate bounds. ``clip_display_region`` additionally returns the
    rectangular boundary frame as an actor (see :func:`clip_region_actor`).
    """
    if not getattr(obj, "clip_enabled", False):
        return pd
    out = pd
    for axis, key in (("X", "clip_xmin"), ("X", "clip_xmax"),
                      ("Y", "clip_ymin"), ("Y", "clip_ymax")):
        val = getattr(obj, key, None)
        if val is None:
            continue
        i = {"X": 0, "Y": 1}[axis]
        # vtkClipPolyData keeps the side the normal points toward; for a
        # "min" bound we keep coords >= min (normal +axis), for "max" we keep
        # coords <= max (normal -axis).
        sign = 1.0 if key.endswith("min") else -1.0
        clip = vtk.vtkPlane()
        clip.SetOrigin(*_point_axis(i, float(val)))
        clip.SetNormal(*_axis_vec(i, sign))
        clipper = vtk.vtkClipPolyData()
        clipper.SetInputData(out)
        clipper.SetClipFunction(clip)
        clipper.Update()
        out = clipper.GetOutput()
    return out


def clip_region_actor(obj) -> Optional["vtk.vtkActor"]:
    """Wireframe rectangle for the Clip region (``clip_display_region``)."""
    if not getattr(obj, "clip_enabled", False):
        return None
    if not getattr(obj, "clip_display_region", False):
        return None
    x0 = getattr(obj, "clip_xmin", None)
    x1 = getattr(obj, "clip_xmax", None)
    y0 = getattr(obj, "clip_ymin", None)
    y1 = getattr(obj, "clip_ymax", None)
    if None in (x0, x1, y0, y1):
        return None
    p = np.asarray(getattr(obj, "point", (0.0, 0.0, 0.0)))
    n = np.asarray(getattr(obj, "normal", (0.0, 0.0, 1.0)))
    n = n / (np.linalg.norm(n) + 1e-12)
    e1 = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(e1, n)) > 0.99:
        e1 = np.array([0.0, 1.0, 0.0])
    e1 = e1 - np.dot(e1, n) * n
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    # project (x,y) bounds onto the plane frame
    lines = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    corners = [
        p + float(x0) * e1 + float(y0) * e2,
        p + float(x1) * e1 + float(y0) * e2,
        p + float(x1) * e1 + float(y1) * e2,
        p + float(x0) * e1 + float(y1) * e2,
    ]
    for c in corners:
        pts.InsertNextPoint(*c)
    lines.SetPoints(pts)
    la = vtk.vtkCellArray()
    la.InsertNextCell(5)
    for k in range(5):
        la.InsertCellPoint(k % 4)
    lines.SetLines(la)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(lines)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.0, 0.0, 0.0)
    actor.GetProperty().SetLineWidth(1)
    return actor


def _axis_vec(i: int, s: float):
    v = [0.0, 0.0, 0.0]
    v[i] = s
    return tuple(v)


def _point_axis(i: int, v: float):
    p = [0.0, 0.0, 0.0]
    p[i] = v
    return tuple(p)


# ---------------------------------------------------------------------------
# Pick (scPOST Pick tab: probe scalar/vector at a world point)
# ---------------------------------------------------------------------------

def pick_point(ff: FieldFile, obj, point, *, ugrid=None,
               cell_centered: Optional[bool] = None) -> dict:
    """Probe scalar / vector fields at a world-space ``point`` (P3.11).

    Follows the Pick tab flags: ``pick_scalar_var`` and ``pick_vector_var``
    name the fields to report. Returns a dict like ``{"scalar": (name, value),
    "vector": (base, (x, y, z))}`` — keys omitted when disabled/unknown.
    """
    out: dict = {"point": tuple(float(v) for v in point)}
    if not _HAS_VTK:
        return out
    scalar_var = getattr(obj, "pick_scalar_var", "") or ""
    vector_var = getattr(obj, "pick_vector_var", "") or ""
    if not scalar_var and not vector_var:
        return out
    if ugrid is None:
        mask = cell_filter_mask(ff, obj)
        rows = _masked_cell_rows(ff, mask)
        ugrid, cell_centered = build_ugrid(ff, cell_mask=mask)
    if ugrid is None:
        return out
    if cell_centered is None:
        cell_centered = (ff.kind == "fph")
    mask = cell_filter_mask(ff, obj)
    rows = _masked_cell_rows(ff, mask)

    if scalar_var and getattr(obj, "pick_scalar", True):
        attach_scalar(ugrid, ff, scalar_var, cell_centered, rows=rows)
    if vector_var and getattr(obj, "pick_vector", False):
        attach_vector(ugrid, ff, vector_var, cell_centered, rows=rows)

    # Convert cell-centred fields to point data so the probe can interpolate.
    work = ugrid
    if cell_centered:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(ugrid)
        c2p.PassCellDataOn()
        c2p.Update()
        work = c2p.GetOutput()

    pts = vtk.vtkPoints()
    pts.InsertNextPoint(*point)
    pt_pd = vtk.vtkPolyData()
    pt_pd.SetPoints(pts)
    probe = vtk.vtkProbeFilter()
    probe.SetInputData(pt_pd)
    probe.SetSourceData(work)
    probe.Update()
    pout = probe.GetOutput()

    if scalar_var:
        arr = pout.GetPointData().GetArray(scalar_var)
        if arr is not None:
            out["scalar"] = (scalar_var, float(arr.GetTuple1(0)))
    if vector_var:
        arr = pout.GetPointData().GetArray(vector_var)
        if arr is None:
            arr = pout.GetPointData().GetVectors(vector_var)
        if arr is not None:
            out["vector"] = (vector_var, tuple(float(v) for v in arr.GetTuple3(0)))
    return out


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

    if method == "Custom Path":
        # P2.9: interpolate along a CSV path (x,y,z per row, optional time col)
        import csv as _csv
        from pathlib import Path as _Path
        csv_path = getattr(obj, "automove_csv", "") or ""
        if csv_path and _Path(csv_path).exists():
            rows = []
            with open(csv_path, newline="", encoding="utf-8") as fh:
                rd = _csv.reader(fh)
                header = next(rd, None)
                for row in rd:
                    try:
                        rows.append([float(v) for v in row[:3]])
                    except ValueError:
                        continue
            if rows:
                arr = np.asarray(rows, dtype=np.float64)
                idx = min(len(arr) - 1, int(round(t * (len(arr) - 1))))
                p = arr[idx]
                n = start_n
                return tuple(p), tuple(n)
        # fall back to Line when the CSV is missing
        f = t
        p = start_p + f * (ref_p - start_p)
        n = start_n + f * (ref_n - start_n)
        n = n / (np.linalg.norm(n) + 1e-12)
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

    ``vector`` (optional) is a ``(n_points, 3)`` array indexed by the *input*
    ``pd`` point ids, so normals are computed from the triangle geometry
    directly (no ``vtkPolyDataNormals``, which would reindex points).
    """
    pd_array = pd.GetPointData().GetArray(scalar_name) if scalar_name else None
    cd_array = pd.GetCellData().GetArray(scalar_name) if scalar_name else None

    area = 0.0
    scalar_sum = 0.0
    vec_normal = 0.0
    vec_axes = np.zeros(3)
    n_cells = pd.GetNumberOfCells()

    for c in range(n_cells):
        cell = pd.GetCell(c)
        ids = cell.GetPointIds()
        n = ids.GetNumberOfIds()
        if n < 3:
            continue
        p0 = np.array(pd.GetPoint(ids.GetId(0)))
        p1 = np.array(pd.GetPoint(ids.GetId(1)))
        p2 = np.array(pd.GetPoint(ids.GetId(2)))
        cross = np.cross(p1 - p0, p2 - p0)
        tri_area = 0.5 * np.linalg.norm(cross)
        area += tri_area
        if tri_area == 0.0:
            continue
        cn = cross / (2.0 * tri_area)
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


def write_integration_csv(path: str, res: dict, obj, *,
                          include_labels: bool = True) -> None:
    """Persist a Scalar/Vector Integration result to CSV (P1.3).

    ``res`` is the dict from :func:`integrate_cut`. Writes a small
    label/value table; ``include_labels=False`` skips the label column.
    """
    import csv
    from pathlib import Path
    out_path = Path(path)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, float | str]] = [("Area [m^2]", res["area"])]
    if "sum" in res:
        rows.append((f"{obj.contour_var} sum", res["sum"]))
        rows.append((f"{obj.contour_var} average", res["average"]))
    if "in_normal" in res:
        rows.append(("Normal flux [m^3/s]", res["in_normal"]))
        rows.append(("Normal flux average [m/s]", res["avg_normal"]))
        rows.append(("Flux X [m^3/s]", res["in_axes"][0]))
        rows.append(("Flux Y [m^3/s]", res["in_axes"][1]))
        rows.append(("Flux Z [m^3/s]", res["in_axes"][2]))
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Item", "Value"] if include_labels else ["Value"])
        for label, value in rows:
            if include_labels:
                writer.writerow([label, f"{value:.9g}"])
            else:
                writer.writerow([f"{value:.9g}"])


def build_plane_actors(ff: FieldFile, obj, ugrid=None,
                       cell_centered: bool = True,
                       siblings=None) -> dict:
    """High-level entry: produce every actor for a PlaneObject.

    Returns ``{"plane", "contour", "contour_line", "vector", "mesh",
    "boundary", "subline"}`` (keys present only when enabled).
    """
    out: dict = {}
    if not _HAS_VTK:
        return out
    mask = cell_filter_mask(ff, obj)
    rows = _masked_cell_rows(ff, mask)
    if ugrid is None:
        ugrid, cell_centered = build_ugrid(ff, cell_mask=mask)
    if ugrid is None:
        return out

    # Attach contour scalar before cutting so vtkCutter propagates it.
    if (getattr(obj, "show_contour", False) and getattr(obj, "contour_var", "")
            and obj.contour_var in ff.variables):
        attach_scalar(ugrid, ff, obj.contour_var, cell_centered, rows=rows)

    # Cut once
    cut = cut_grid(ugrid, obj)
    if cut.GetNumberOfPoints() == 0:
        return out

    # Trim
    cut = trim_cut(cut, obj)
    # Limited plane (5c): clip to a finite box centred on the plane point
    cut = _limited_clip(cut, obj)
    # Trim by other objects (P1.6)
    cut = trim_by_objects(cut, ff, obj, siblings)
    # Clip (X/Y region)
    cut = clip_cut(cut, obj)

    # Clip region frame
    if getattr(obj, "clip_display_region", False):
        r = clip_region_actor(obj)
        if r is not None:
            out["clip_region"] = r

    # Contour
    if (getattr(obj, "show_contour", False) and getattr(obj, "contour_var", "")
            and obj.contour_var in ff.variables):
        out["contour"] = contour_actor(cut, obj.contour_var, obj)
        if getattr(obj, "contour_line", False):
            out["contour_line"] = contour_line_actor(
                cut, obj.contour_var, obj)
        if getattr(obj, "contour_value", False):
            cv = contour_value_actor(cut, obj.contour_var, obj)
            if cv is not None:
                _apply_font(cv, obj)
                out["contour_value"] = cv

    # Colorbar (Others tab) for contour / vector
    cb_var = getattr(obj, "colorbar_contour", "") or ""
    if cb_var and cb_var != "(auto)" and "contour" in out:
        cb = colorbar_actor(out["contour"].GetMapper(), obj, title=cb_var)
        if cb is not None:
            out["colorbar"] = cb
    if not out.get("colorbar"):
        cbv = getattr(obj, "colorbar_vector", "") or ""
        if cbv and cbv != "(auto)" and "vector" in out:
            cb = colorbar_actor(out["vector"].GetMapper(), obj, title=cbv)
            if cb is not None:
                out["colorbar"] = cb

    # Texture (Texture tab) over the cut plane
    if getattr(obj, "texture_enabled", False):
        tx = texture_actor(cut, obj)
        if tx is not None:
            out["texture"] = tx

    # Vector
    if getattr(obj, "show_vector", False) and getattr(obj, "vector_var", ""):
        actor = vector_actor(ugrid, ff, obj, cell_centered, rows=rows)
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

    # Oil Flow (streamlines from cut-plane seeds)
    if getattr(obj, "oilflow_display", False):
        from .oilflow import build_oilflow_actor
        o = build_oilflow_actor(ff, obj, ugrid=ugrid,
                                cell_centered=cell_centered, rows=rows)
        if o is not None:
            out["oilflow"] = o

    return out
