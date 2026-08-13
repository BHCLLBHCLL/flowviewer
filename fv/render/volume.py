"""Volume object (scPOST Volume) — whole-domain scalar/vector display.

Builds the volume unstructured grid with MAT / Volume Region filtering,
attaches the scalar to CellData and renders an opaque / translucent
volume with an optional vector glyph overlay. Sampling/resolution is
respected by decimating the cell list for large grids (``obj.sampling``).
"""

from typing import Optional

try:
    import vtk
    from vtk.util import numpy_support as _vns
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    _vns = None

from ..model.dataset import FieldFile


def build_volume_actors(ff: FieldFile, obj,
                        ugrid=None, cell_centered=None) -> dict:
    """Volume actors → ``{"scalar", "vector"}``.

    ``obj.show_scalar`` gates the scalar-capacity actor; ``obj.scalar_var``
    names the field. ``draw_type`` Solid / Transparent / Sampled controls
    opacity and cell decimation.
    """
    out: dict = {}
    if not _HAS_VTK:
        return out
    from .plane import build_ugrid, cell_filter_mask
    mask = cell_filter_mask(ff, obj)
    if ugrid is None or cell_centered is None:
        ugrid, cell_centered = build_ugrid(ff, cell_mask=mask)
    if ugrid is None:
        return out

    ugrid = _apply_sampling(ugrid, obj)
    var = getattr(obj, "scalar_var", "") or ""
    if getattr(obj, "show_scalar", True) and var and var in ff.variables:
        _attach_scalar(ugrid, ff, var, cell_centered)
        actor = _volume_actor(ugrid, var, obj)
        if actor is not None:
            out["scalar"] = actor

    if getattr(obj, "show_vector", False) and getattr(obj, "vector_var", ""):
        from .vector import vector_glyph_actor
        work = ugrid
        if cell_centered:
            c2p = vtk.vtkCellDataToPointData()
            c2p.SetInputData(ugrid)
            c2p.PassCellDataOn()
            c2p.Update()
            work = c2p.GetOutput()
        va = vector_glyph_actor(ff, obj, work,
                                source_grid=ugrid,
                                cell_centered=cell_centered)
        if va is not None:
            out["vector"] = va
    return out


def _apply_sampling(ugrid, obj):
    """Decimate hexahedra when ``sampling`` > 1 (Sampled / accuracy)."""
    sampling = int(getattr(obj, "sampling", 1) or 1)
    if sampling <= 1:
        return ugrid
    cells = ugrid.GetCells()
    if cells is None or cells.GetNumberOfCells() < 8:
        return ugrid
    keep_cells = cells.GetNumberOfCells() // sampling
    if keep_cells < 1:
        keep_cells = 1
    cell_ids = list(range(keep_cells))
    ids = vtk.vtkIdList()
    for c in cell_ids:
        ids.InsertNextId(c)
    extract = vtk.vtkExtractUnstructuredGrid()
    extract.SetInputData(ugrid)
    extract.SetCellList(ids)
    extract.Update()
    return extract.GetOutput()


def _attach_scalar(ugrid, ff, var, cell_centered):
    """Attach scalar to the grid (CellData for cell-centred/fld-centred)."""
    from .plane import attach_scalar
    return attach_scalar(ugrid, ff, var, cell_centered)


def _volume_actor(ugrid, var: str, obj) -> Optional[object]:
    """Real volume rendering (P1.3): vtkSmartVolumeMapper + transfer
    functions; falls back to a translucent vtkDataSetMapper when the
    smart mapper is unavailable."""
    draw_type = (getattr(obj, "draw_type", "Solid") or "Solid")
    opacity = 1.0
    if draw_type in ("Transparent", "Sampled"):
        opacity = 0.35
    if getattr(obj, "transparent", False):
        opacity = min(opacity, 0.5)
    opacity = min(1.0, opacity * float(getattr(obj, "scalar_opacity", 1.0)
                                    or 1.0))
    if getattr(obj, "scalar_mono_color", False):
        return _plain_volume_actor(ugrid, var, obj, opacity)
    # vtkSmartVolumeMapper only accepts image/rectilinear grids; for
    # unstructured volume cells (FLD hex / CGNS tet) use the ray-cast
    # mapper; polyhedral FPH grids fall back to the translucent actor.
    try:
        if ugrid.GetNumberOfCells() > 0 and ugrid.GetCellType(0) in (
                vtk.VTK_HEXAHEDRON, vtk.VTK_TETRA, vtk.VTK_WEDGE,
                vtk.VTK_PYRAMID):
            return _raycast_volume_actor(ugrid, var, obj, opacity)
    except Exception:
        pass
    return _plain_volume_actor(ugrid, var, obj, opacity)


def _raycast_volume_actor(ugrid, var: str, obj, opacity: float):
    """Unstructured-grid ray-cast volume (P1.3)."""
    lo, hi = _data_range(ugrid, var)
    if not (hi > lo):
        hi = lo + 1.0
    ctf = vtk.vtkColorTransferFunction()
    for t, rgb in ((0.0, (0.2, 0.2, 1.0)),
                   (0.33, (0.2, 1.0, 0.2)),
                   (0.66, (1.0, 1.0, 0.2)),
                   (1.0, (1.0, 0.2, 0.2))):
        ctf.AddRGBPoint(lo + t * (hi - lo), *rgb)
    otf = vtk.vtkPiecewiseFunction()
    otf.AddPoint(lo, opacity);
    otf.AddPoint(hi, opacity)
    smap = vtk.vtkUnstructuredGridVolumeRayCastMapper()
    smap.SetInputData(ugrid)
    vol = vtk.vtkVolume()
    vol.SetMapper(smap)
    prop = vol.GetProperty()
    prop.SetColor(ctf)
    prop.SetScalarOpacity(otf)
    prop.ShadeOn()
    prop.SetAmbient(0.25)
    prop.SetDiffuse(0.8)
    prop.SetSpecular(0.3)
    return vol


def _plain_volume_actor(ugrid, var: str, obj, opacity: float):
    """Fallback: translucent vtkDataSetMapper volume (pre-P1.3)."""
    mapper = vtk.vtkDataSetMapper()
    mapper.SetInputData(ugrid)
    mapper.SetScalarModeToUseCellData()
    mapper.SelectColorArray(var)
    mapper.SetScalarRange(_data_range(ugrid, var))
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    if getattr(obj, "scalar_mono_color", False):
        mapper.ScalarVisibilityOff()
        try:
            actor.GetProperty().SetColor(*obj.scalar_mono_rgb)
        except (AttributeError, TypeError):
            actor.GetProperty().SetColor(0.6, 0.7, 0.8)
    actor.GetProperty().SetOpacity(opacity)
    return actor


def _data_range(ugrid, name: str) -> tuple[float, float]:
    arr = ugrid.GetCellData().GetArray(name)
    if arr is None:
        arr = ugrid.GetPointData().GetArray(name)
    if arr is None:
        return (0.0, 1.0)
    r = arr.GetRange()
    if r[0] == r[1]:
        r = (r[0] - 1.0, r[1] + 1.0)
    return (float(r[0]), float(r[1]))