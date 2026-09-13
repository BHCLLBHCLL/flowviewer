"""R19 - large-data plane-cut performance caching.

Validates the UGrid memoization in :mod:`fv.render.plane`:

- ``build_ugrid`` returns the same grid object when geometry and cell mask are
  unchanged (animation / repeated-render reuse), keyed by a mesh fingerprint.
- ``_mesh_fingerprint`` is stable under repeated calls and reacts to geometry
  changes (vertex / cell count).
- FPH grids are built in one packed ``vtkIdTypeArray`` batch; every cell keeps
  its deduplicated node set, and degenerate cells (empty owner faces, present
  in real samples) stay as 0-point cells so 1:1 cell-centred data
  stays aligned without crashing ``vtkCutter``.
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"

from fv.model.objects import PlaneObject  # noqa: E402
from fv.render.plane import (  # noqa: E402
    _HAS_VTK,
    _mesh_fingerprint,
    attach_scalar,
    build_ugrid,
    cut_grid,
)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_mesh_fingerprint_stability():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    assert _mesh_fingerprint(ff) == _mesh_fingerprint(ff)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_mesh_fingerprint_reacts_to_geometry():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    a = SimpleNamespace(vertices=ff.vertices, link_data=ff.link_data,
                        n_cells=ff.n_cells)
    b = SimpleNamespace(vertices=ff.vertices, link_data=ff.link_data,
                        n_cells=ff.n_cells + 1)
    assert _mesh_fingerprint(a) != _mesh_fingerprint(b)


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_ugrid_cache_reuses_unchanged_grid():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    ug, cc = build_ugrid(ff)
    assert ug.GetNumberOfCells() == ff.n_cells
    ug2, cc2 = build_ugrid(ff)
    assert ug is ug2 and cc == cc2


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_ugrid_mask_produces_distinct_subset_grid():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    ug, _ = build_ugrid(ff)
    mask = np.ones(ff.n_cells, dtype=bool)
    mask[::2] = False
    ug3, _ = build_ugrid(ff, mask)
    assert ug3 is not ug
    assert ug3.GetNumberOfCells() == int(mask.sum())


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_fph_grid_is_closed_polyhedra_with_1to1_cell_indexing():
    """R110: every FPH cell is a closed VTK_POLYHEDRON, 1:1 with the field data.

    R19 kept degenerate (owner-face-only) cells as 0-*point* cells; R109 then
    switched to true VTK_POLYHEDRON cells built from the full owner+neighbour
    shell.  Measuring the face stream on the real sample shows the shells are
    now closed, so no defective cell remains: the old "0 in seen_npts"
    expectation described a defect that no longer exists.

    What must hold now:
      * one cell per FieldFile cell, in order (cell-centred fields index it);
      * every cell is a polyhedron;
      * every cell carries a closed shell (>= 4 faces, 0 is impossible).
    """
    import vtk
    from fv.model.dataset import load_file

    ff = load_file(FPH)
    ug, _ = build_ugrid(ff)
    assert ug.GetNumberOfCells() == ff.n_cells

    zero_face = 0
    min_faces = None
    for cid in range(ug.GetNumberOfCells()):
        assert ug.GetCellType(cid) == vtk.VTK_POLYHEDRON
        stream = vtk.vtkIdList()
        ug.GetFaceStream(cid, stream)  # empty stream <=> no faces at all
        n = stream.GetNumberOfIds()
        if n == 0:
            zero_face += 1
            continue
        faces = stream.GetId(0)  # the stream starts with the face count
        min_faces = faces if min_faces is None else min(min_faces, faces)

    assert zero_face == 0, "defective (face-less) cells: %d" % zero_face
    assert min_faces is not None and min_faces >= 4


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_cut_on_cached_grid_returns_data():
    """The cached FPH grid still cuts (regression: empty-cut bug)."""
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    ug, cc = build_ugrid(ff)
    attach_scalar(ug, ff, "PRES", cc)
    obj = PlaneObject()
    v = np.asarray(ff.vertices)
    zc = float(v[:, 2].mean())
    obj.point = [float(v[:, 0].mean()), float(v[:, 1].mean()), zc]
    obj.normal = [0, 0, 1]
    pd = cut_grid(ug, obj)
    assert pd.GetNumberOfPoints() > 0
