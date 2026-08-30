"""Isosurface rendering (scPOST Isosurface).

Builds the volume unstructured grid via ``fv.render.plane.build_ugrid``,
converts the scalar to point data, and extracts iso-surfaces with
``vtkContourFilter`` at a number of evenly spaced (or explicit) values.
Optional contour lines and vector glyphs can be stacked on top.
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


def build_isosurface_actors(ff: FieldFile, obj,
                            ugrid=None, cell_centered=True) -> dict:
    """Iso-surface actors → ``{"contour", "contour_line", "vector"}``.

    ``obj.contour_var`` names the scalar; values come from
    ``obj.contour_values`` when given, else ``obj.contour_number`` evenly
    spaced levels over the scalar range. ``obj.show_vector`` adds vector
    glyphs on the iso-surface.
    """
    out: dict = {}
    if not _HAS_VTK:
        return out
    var = getattr(obj, "contour_var", "") or ""
    if not var or var not in ff.variables:
        return out
    if ugrid is None or cell_centered is None:
        ugrid, cell_centered = _pipeline_grid(ff, obj)
    if ugrid is None:
        return out

    _attach_scalar(ugrid, ff, var, cell_centered)
    work = _to_points(ugrid, cell_centered)
    iso = _contour_values(work, obj, var)
    if iso is None or iso.GetNumberOfCells() == 0:
        return out

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(iso)
    mapper.SetScalarModeToUsePointData()
    mapper.SelectColorArray(var)
    mapper.SetScalarRange(_data_range(iso, var))
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    prop = actor.GetProperty()
    if getattr(obj, "contour_mono_color", False):
        mapper.ScalarVisibilityOff()
        prop.SetColor(*obj.contour_mono_rgb)
    if getattr(obj, "contour_transparent", False):
        prop.SetOpacity(0.6)
    out["contour"] = actor

    if getattr(obj, "contour_line", False):
        ex = vtk.vtkExtractEdges()
        ex.SetInputData(iso)
        ex.Update()
        lm = vtk.vtkPolyDataMapper()
        lm.SetInputConnection(ex.GetOutputPort())
        la = vtk.vtkActor()
        la.SetMapper(lm)
        lp = la.GetProperty()
        lp.SetColor(0.0, 0.0, 0.0)
        lp.SetRepresentationToWireframe()
        out["contour_line"] = la

    if getattr(obj, "show_vector", False) and getattr(obj, "vector_var", ""):
        from .vector import vector_glyph_actor
        va = vector_glyph_actor(ff, obj, iso,
                                source_grid=ugrid,
                                cell_centered=cell_centered)
        if va is not None:
            out["vector"] = va

    return out



def build_iso_animation(fields, obj, ugrid=None, cell_centered=True) -> list:
    """Per-cycle isosurface actor frames sharing one geometry grid (R21).

    ``fields`` is a sequence of :class:`FieldFile` (one per cycle/FileSet,
    normally the same geometry with a different scalar). The unstructured
    grid is built once from the first field (or taken from ``ugrid``) and
    reused; each field's scalar is attached and one
    ``{"contour", "contour_line", "vector"}`` frame is built. Returns a list
    aligned 1:1 with ``fields`` so a renderer can cycle the frames.
    """
    if not _HAS_VTK or not fields:
        return []
    if ugrid is None or cell_centered is None:
        ugrid, cell_centered = _pipeline_grid(fields[0], obj)
    if ugrid is None:
        return []
    var = getattr(obj, "contour_var", "") or ""
    frames = []
    for ff in fields:
        # attach_scalar overwrites the cell array in place; build_isosurface_
        # actors then cell-to-points each frame, so the contour outputs are
        # independent even though one grid is reused.
        if var and ff.variable_array(var) is not None:
            _attach_scalar(ugrid, ff, var, cell_centered)
        frames.append(build_isosurface_actors(ff, obj, ugrid=ugrid,
                                              cell_centered=cell_centered))
    return frames


def _pipeline_grid(ff, obj):
    """(ugrid, cell_centered) with MAT / Volume Region filtering applied."""
    from .plane import build_ugrid, cell_filter_mask
    mask = cell_filter_mask(ff, obj)
    return build_ugrid(ff, cell_mask=mask)


def _attach_scalar(ugrid, ff, var, cell_centered):
    """Attach the scalar to the grid (CellData for cell-centred FPH)."""
    from .plane import attach_scalar
    return attach_scalar(ugrid, ff, var, cell_centered)


def _to_points(ugrid, cell_centered):
    """Work grid with the scalar as point data (vtkContourFilter needs it)."""
    if not cell_centered:
        return ugrid
    c2p = vtk.vtkCellDataToPointData()
    c2p.SetInputData(ugrid)
    c2p.PassCellDataOn()
    c2p.Update()
    return c2p.GetOutput()


def _contour_values(work, obj, var) -> Optional[vtk.vtkPolyData]:
    """vtkContourFilter output for the numeric levels (auto or explicit)."""
    explicit = list(getattr(obj, "contour_values", []) or [])
    if explicit:
        values = [float(v) for v in explicit]
    else:
        arr = work.GetPointData().GetArray(var)
        if arr is None:
            return None
        r = arr.GetRange()
        n = max(1, int(getattr(obj, "contour_number", 5) or 5))
        if r[0] == r[1]:
            r = (r[0] - 1.0, r[1] + 1.0)
        values = [float(r[0] + (r[1] - r[0]) * (i + 1) / (n + 1))
                  for i in range(n)]
    cf = vtk.vtkContourFilter()
    cf.SetInputData(work)
    cf.SetNumberOfContours(len(values))
    for i, v in enumerate(values):
        cf.SetValue(i, v)
    cf.Update()
    return cf.GetOutput()


def _data_range(pd, name: str) -> tuple[float, float]:
    arr = pd.GetPointData().GetArray(name)
    if arr is None:
        return (0.0, 1.0)
    r = arr.GetRange()
    if r[0] == r[1]:
        r = (r[0] - 1.0, r[1] + 1.0)
    return (float(r[0]), float(r[1]))
