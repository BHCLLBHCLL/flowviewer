"""Volume object (scPOST Volume) — whole-domain scalar/vector display.

Builds the volume unstructured grid with MAT / Volume Region filtering,
attaches the scalar to CellData and renders an opaque / translucent
volume with an optional vector glyph overlay. Sampling/resolution is
respected by decimating the cell list for large grids (``obj.sampling``).
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
    """Stride-decimate cells when ``sampling`` > 1 (Sampled / accuracy).

    P1.1: keeps every *sampling*-th cell across the whole domain instead
    of truncating to the first ``n//sampling`` cells (which dropped the
    entire tail of the grid).
    """
    sampling = int(getattr(obj, "sampling", 1) or 1)
    if sampling <= 1:
        return ugrid
    cells = ugrid.GetCells()
    if cells is None or cells.GetNumberOfCells() < 8:
        return ugrid
    cell_ids = list(range(0, cells.GetNumberOfCells(), sampling))
    ids = vtk.vtkIdList()
    for c in cell_ids:
        ids.InsertNextId(c)
    extract = vtk.vtkExtractCells()
    extract.SetInputData(ugrid)
    extract.SetCellList(ids)
    extract.Update()
    return extract.GetOutput()


def _attach_scalar(ugrid, ff, var, cell_centered):
    """Attach scalar to the grid (CellData for cell-centred/fld-centred)."""
    from .plane import attach_scalar
    return attach_scalar(ugrid, ff, var, cell_centered)


def _volume_actor(ugrid, var: str, obj) -> Optional[object]:
    """Real volume rendering (P1.1/P1.3).

    * hex/tet/wedge/pyramid cells → unstructured ray-cast volume;
    * polyhedral cells (FPH ConvexPointSet-family) → vtkResampleToImage
      → vtkSmartVolumeMapper (P1.1), bypassing the cell-type limitation;
    * mono-colour mode → translucent dataset actor.
    """
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
    try:
        n_cells = ugrid.GetNumberOfCells()
        first_type = ugrid.GetCellType(0) if n_cells > 0 else -1
        if n_cells > 0 and first_type in (
                vtk.VTK_HEXAHEDRON, vtk.VTK_TETRA, vtk.VTK_WEDGE,
                vtk.VTK_PYRAMID):
            return _raycast_volume_actor(ugrid, var, obj, opacity)
        if n_cells > 0:
            resampled = _resampled_volume_actor(ugrid, var, obj, opacity)
            if resampled is not None:
                return resampled
    except Exception:
        pass
    return _plain_volume_actor(ugrid, var, obj, opacity)


def _transfer_functions(obj, lo: float, hi: float, opacity: float):
    """Colour/opacity transfer functions from object parameters (P1.1).

    Colours follow the object's colorbar palette (Rainbow default, Gray /
    Invert honoured via :func:`fv.render.colorbar.build_lut`) at the
    colorbar gradation instead of a hard-coded 8-stop ramp; opacity uses a
    3-point ramp (low → mid → high, P2-4) for a smoother depth cue, with
    the floor lowered for Transparent / Sampled draw types.
    """
    from .colorbar import build_lut
    palette = (getattr(obj, "colorbar", "") or "").strip() or "Rainbow"
    grad = int(getattr(obj, "gradation", 0) or 0) or 256
    lut = build_lut(gradation=grad, color_map=palette)
    ctf = vtk.vtkColorTransferFunction()
    span = (hi - lo) or 1.0
    n = lut.GetNumberOfTableValues()
    for i in range(n):
        v = lut.GetTableValue(i)  # (r, g, b, a)
        ctf.AddRGBPoint(lo + (i / max(1, n - 1)) * span, v[0], v[1], v[2])
    otf = vtk.vtkPiecewiseFunction()
    floor = opacity * (0.25 if getattr(obj, "transparent", False)
                       or (getattr(obj, "draw_type", "") or ""
                           in ("Transparent", "Sampled"))
                       else 0.6)
    mid_frac = float(getattr(obj, "opacity_mid", 0.75) or 0.75)
    # P2-4: 3-point opacity ramp (low → mid → high) instead of 2 stops
    otf.AddPoint(lo, floor)
    otf.AddPoint(lo + 0.5 * span, max(floor, opacity * min(1.0, mid_frac)))
    otf.AddPoint(hi, opacity)
    return ctf, otf


def _raycast_volume_actor(ugrid, var: str, obj, opacity: float):
    """Unstructured-grid ray-cast volume (P1.3) with parameterised TFs."""
    lo, hi = _data_range(ugrid, var)
    if not (hi > lo):
        hi = lo + 1.0
    ctf, otf = _transfer_functions(obj, lo, hi, opacity)
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


def _resampled_volume_actor(ugrid, var: str, obj, opacity: float):
    """Polyhedral volume path (P1.1): resample to a vtkImageData and
    render with vtkSmartVolumeMapper.

    ``obj.sampling`` trades resolution for speed (1 → 64³, 2 → 32³ …).
    Cell-centred scalars are converted to point data before resampling;
    out-of-domain NaN samples are clamped to the scalar minimum.
    """
    if not hasattr(vtk, "vtkResampleToImage") or \
            not hasattr(vtk, "vtkSmartVolumeMapper"):
        return None
    work = ugrid
    if work.GetPointData().GetArray(var) is None:
        c2p = vtk.vtkCellDataToPointData()
        c2p.SetInputData(work)
        c2p.Update()
        work = c2p.GetOutput()
        if work.GetPointData().GetArray(var) is None:
            return None
    sampling = max(1, int(getattr(obj, "sampling", 1) or 1))
    # 64³ default balances fidelity against the ConvexPointSet probe cost
    # (96³ ≈ 885k samples over 63k polyhedra ≈ minutes).
    dim = max(16, min(64, 64 // sampling))
    rs = vtk.vtkResampleToImage()
    # VTK ≥9.2 ships the parallel vtkPResampleToImage under this alias,
    # which only accepts connections — bridge the data object through a
    # trivial producer.
    if hasattr(rs, "SetInputData"):
        rs.SetInputData(work)
    else:
        tp = vtk.vtkTrivialProducer()
        tp.SetOutput(work)
        rs.SetInputConnection(tp.GetOutputPort())
    rs.SetSamplingDimensions(dim, dim, dim)
    rs.Update()
    img = rs.GetOutput()
    arr = img.GetPointData().GetArray(var)
    if arr is None:
        return None
    vals = _vns.vtk_to_numpy(arr)
    if not np.isfinite(vals).all():
        lo = float(np.nanmin(vals[np.isfinite(vals)]))
        vals = np.where(np.isfinite(vals), vals, lo)
        arr.DeepCopy(_vns.numpy_to_vtk(vals))
    lo, hi = _data_range(img, var)
    if not (hi > lo):
        hi = lo + 1.0
    ctf, otf = _transfer_functions(obj, lo, hi, opacity)
    smap = vtk.vtkSmartVolumeMapper()
    smap.SetInputData(img)
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
