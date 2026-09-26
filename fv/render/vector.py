"""Shared vector glyphs (vtkGlyph3D arrows) for grid / surface-like objects."""

import logging
from typing import Optional

import numpy as np

try:
    import vtk
    from vtk.util import numpy_support as _vns
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    _vns = None

from ..model.dataset import FIELD_SENTINEL, FieldFile


def resolve_vector_base(ff: FieldFile, name: str, label: str = "vector"):
    """Fold a component name (VELX) back to its base (VEL).

    The loaders register every component with ``kind == "vector"``, so the
    Vector tab and a saved session can hand over either form (R133).  A name
    is only folded when all three components exist; otherwise it is left
    alone and the missing suffixes are reported.

    Returns ``(base, missing)``.  When ``missing`` is non-empty the caller
    must draw nothing -- R133c: the plane and surface actors kept the *raw*
    name for ``SetActiveVectors``/``GetVectors``, so a session holding VELX
    still drew no arrows even after attach_vector folded the name.
    """
    base = str(name or "")
    if base.endswith(("X", "Y", "Z")) and base[:-1] and all(
            (base[:-1] + s) in ff.variables for s in ("X", "Y", "Z")):
        base = base[:-1]
    missing = [s for s in ("X", "Y", "Z")
               if ff.variable_array(f"{base}{s}") is None]
    if missing:
        logging.getLogger(__name__).warning(
            "%s %r has no %s component(s): no vector arrows are drawn",
            label, base, "/".join(missing))
    return base, missing


def vector_peak(field) -> float:
    """Largest FINITE vector magnitude attached to *field* (0.0 when none).

    Undefined entries are NaN once the sentinel normalisation has run (R118
    for FLD, R133c for FPH), so they must not become the reference magnitude.
    """
    if not _HAS_VTK or field is None:
        return 0.0
    data = field.GetPointData()
    vec = data.GetVectors() if data is not None else None
    if vec is None:
        data = field.GetCellData()
        vec = data.GetVectors() if data is not None else None
    if vec is None or vec.GetNumberOfTuples() == 0:
        return 0.0
    mags = np.asarray(_vns.vtk_to_numpy(vec), dtype=np.float64)
    mags = np.linalg.norm(mags.reshape(-1, 3), axis=1)
    # Undefined entries are either NaN (normalised) or the raw 1e20 sentinel
    # when a field reached the renderer without normalisation; neither may
    # become the reference magnitude.
    mags = mags[np.isfinite(mags) & (np.abs(mags) < FIELD_SENTINEL)]
    return float(mags.max()) if mags.size else 0.0


def glyph_scale(field, width: float, scale_length: float = 1.0,
                fraction: float = 0.05) -> float:
    """``vtkGlyph3D`` factor putting the fastest arrow at ``fraction``*width.

    The factor has to be relative to the field's own peak magnitude: |v|
    carries physical units, so a fixed factor times the model size drew
    9.8e-6 m arrows in a 0.536 m model on the real block sample (invisible),
    while one 1e20 "undefined" entry stretched the glyph bounds to 1e18 and
    the camera followed it.  render/vector.py already normalised this way
    (0.03) for volume/isosurface; the plane and surface paths did not.
    """
    base = float(fraction) * float(width) * float(scale_length)
    peak = vector_peak(field)
    if not np.isfinite(peak) or peak <= 0.0:
        return base
    return base / peak


def attach_vector(ugrid, ff: FieldFile, base: str, cell_centered: bool,
                  rows=None):
    """Attach a vector field (``base``X/Y/Z) onto a grid (shared)."""
    if not _HAS_VTK:
        return None
    from .plane import attach_vector as _plane_attach
    return _plane_attach(ugrid, ff, base, cell_centered, rows=rows)


def apply_vector_coloring(obj, glyph_input, mapper, actor) -> None:
    """R0.6 (B7): colour vector glyphs by variable / magnitude / mono.

    - ``vector_contour_color`` + a ``contour_var`` array present on the
      glyph input → mapper colours by that variable (shared colorbar LUT);
    - ``vector_contour_color`` alone → colour by vector magnitude |v|;
    - ``vector_mono_color`` → flat ``vector_mono_rgb``;
    - default → scPOST black arrows.

    ``glyph_input`` is the polydata fed to ``vtkGlyph3D``; the colour
    array must live in its PointData so the glyph copies it to the output.
    """
    if getattr(obj, "vector_contour_color", False):
        pd = glyph_input.GetPointData() if glyph_input is not None else None
        name = None
        var = getattr(obj, "contour_var", "") or ""
        if var and pd is not None and pd.GetArray(var) is not None:
            name = var
        elif pd is not None and pd.GetVectors() is not None:
            base = pd.GetVectors().GetName() or "vec"
            name = base + "_mag"
            if pd.GetArray(name) is None:
                mags = np.linalg.norm(
                    np.asarray(_vns.vtk_to_numpy(pd.GetVectors())
                               ).reshape(-1, 3), axis=1)
                fa = _vns.numpy_to_vtk(
                    np.ascontiguousarray(mags, dtype=np.float64), deep=True)
                fa.SetName(name)
                pd.AddArray(fa)
        if (name is not None and pd is not None
                and pd.GetArray(name) is not None):
            rng = pd.GetArray(name).GetRange()
            if rng[0] == rng[1]:
                rng = (rng[0] - 1.0, rng[1] + 1.0)
            mapper.SetScalarModeToUsePointData()
            mapper.SelectColorArray(name)
            mapper.SetScalarRange(float(rng[0]), float(rng[1]))
            try:
                from .colorbar import ColorbarRegistry
                mapper.SetLookupTable(ColorbarRegistry.lut())
            except Exception:  # pragma: no cover - headless
                pass
            return
    rgb = getattr(obj, "vector_mono_rgb", None)
    if getattr(obj, "vector_mono_color", False) and rgb:
        actor.GetProperty().SetColor(
            float(rgb[0]), float(rgb[1]), float(rgb[2]))
    else:
        actor.GetProperty().SetColor(0.0, 0.0, 0.0)


def vector_glyph_actor(ff: FieldFile, obj, polydata,
                       source_grid=None,
                       cell_centered=False) -> Optional["vtk.vtkActor"]:
    """Arrow glyphs over ``polydata`` (probe vector onto its points).

    ``source_grid`` (unstructured grid with point vectors) is used to
    interpolate the vector onto ``polydata``; when absent the raw vector
    array is copied direct (node-centred inputs only).
    """
    if not _HAS_VTK:
        return None
    base = getattr(obj, "vector_var", "") or ""
    if not base:
        return None
    # R133c: same folding and same explicit report as the plane and surface
    # paths -- this one returned None in silence for a component name (VELX)
    # and for a missing component (the volume/isosurface Vector tab shares
    # _vector_vars with the plane).
    base, missing = resolve_vector_base(ff, base)
    if missing or not base:
        return None

    out = _probe_vector(ff, polydata, base, source_grid, cell_centered)
    if out is None:
        return None
    scale_length = float(getattr(obj, "vector_scale_length", 1.0) or 1.0)

    arrow = vtk.vtkArrowSource()
    g = vtk.vtkGlyph3D()
    g.SetInputData(out)
    g.SetSourceConnection(arrow.GetOutputPort())
    g.SetScaleFactor(_glyph_scale(out, scale_length))
    g.SetVectorModeToUseVector()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(g.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    apply_vector_coloring(obj, out, mapper, actor)
    return actor


def _probe_vector(ff, pd, base, source_grid, cell_centered):
    """PolyData copy with ``base`` vectors in PointData.

    ``source_grid`` should be the *original* unstructured grid. When the
    field is cell-centred it is attached as CellData and converted to point
    data before probing; node-centred fields are attached directly.

    FLD node-centred grids skip the ``vtkProbeFilter``/locator entirely
    (VTK crashes on ``vtkHexahedron`` cell locators — heap corruption), so
    the node array is copied straight into ``pd``.
    """
    if ff.kind == "fld":
        vx = np.asarray(ff.variable_array(f"{base}X"), dtype=np.float64)
        vy = np.asarray(ff.variable_array(f"{base}Y"), dtype=np.float64)
        vz = np.asarray(ff.variable_array(f"{base}Z"), dtype=np.float64)
        n = pd.GetNumberOfPoints()
        src = np.column_stack((vx, vy, vz))[:n]
        fa = _vns.numpy_to_vtk(
            np.ascontiguousarray(src, dtype=np.float64), deep=True)
        fa.SetName(base)
        pd.GetPointData().SetVectors(fa)
        return pd
    if source_grid is not None:
        from .plane import attach_vector as _plane_attach
        if cell_centered:
            _plane_attach(source_grid, ff, base, cell_centered=True)
            c2p = vtk.vtkCellDataToPointData()
            c2p.SetInputData(source_grid)
            c2p.PassCellDataOn()
            c2p.Update()
            work = c2p.GetOutput()
        else:
            _plane_attach(source_grid, ff, base, cell_centered=False)
            work = source_grid
        if work.GetPointData().GetVectors(base) is None:
            return None
        probe = vtk.vtkProbeFilter()
        probe.SetInputData(pd)
        probe.SetSourceData(work)
        probe.Update()
        return probe.GetOutput()
    # Direct injection: read node-centred array (all nodes) without probing
    vx = np.asarray(ff.variable_array(f"{base}X"), dtype=np.float64)
    vy = np.asarray(ff.variable_array(f"{base}Y"), dtype=np.float64)
    vz = np.asarray(ff.variable_array(f"{base}Z"), dtype=np.float64)
    n = pd.GetNumberOfPoints()
    src = np.column_stack((vx, vy, vz))[:n]
    fa = _vns.numpy_to_vtk(
        np.ascontiguousarray(src, dtype=np.float64), deep=True)
    fa.SetName(base)
    pd.GetPointData().SetVectors(fa)
    return pd


def _glyph_scale(pd, scale_length: float = 1.0) -> float:
    """Glyph factor putting the longest vector at 3% of the model diagonal.

    R133g: the reference peak comes from :func:`vector_peak`, which ignores
    NaN and the 1e20 "undefined" sentinel.  A plain mags.max() returned NaN
    (the factor became NaN) or 1e20 (every arrow collapsed to nothing).
    """
    vec = pd.GetPointData().GetVectors()
    if vec is None:
        return 1.0
    pts = pd.GetPoints()
    if pts is None or pts.GetNumberOfPoints() < 2:
        return 1.0
    b = pts.GetBounds()
    diag = np.sqrt((b[1] - b[0]) ** 2 + (b[3] - b[2]) ** 2 + (b[5] - b[4]) ** 2)
    peak = vector_peak(pd)
    if peak <= 0:
        return 1.0
    return 0.03 * diag / peak * scale_length
