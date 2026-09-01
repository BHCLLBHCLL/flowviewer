"""R26-S1 - plane-cut result caching.

The cut is a pure function of (grid identity, plane pose). Repeated cuts on
the same grid & plane must reuse the previous ``vtkCutter`` output instead of
re-running the cutter, bounded by an LRU cache.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"

from fv.model.objects import PlaneObject  # noqa: E402
from fv.render.plane import (  # noqa: E402
    _CUT_CACHE_MAX,
    _HAS_VTK,
    _cut_cache,
    build_ugrid,
    clear_cut_cache,
    cut_grid,
)


@pytest.fixture(autouse=True)
def _reset_cut_cache():
    clear_cut_cache()
    yield
    clear_cut_cache()


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_same_plane_reuses_output_object():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    ug, _ = build_ugrid(ff)
    obj = PlaneObject()
    v = np.asarray(ff.vertices)
    obj.point = [float(v[:, 0].mean()), float(v[:, 1].mean()),
                 float(v[:, 2].mean())]
    obj.normal = [0, 0, 1]
    pd1 = cut_grid(ug, obj)
    pd2 = cut_grid(ug, obj)
    assert pd1 is pd2


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_distinct_plane_pose_productive_fresh_cut():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    ug, _ = build_ugrid(ff)
    v = np.asarray(ff.vertices)
    base = [float(v[:, 0].mean()), float(v[:, 1].mean()),
            float(v[:, 2].mean())]
    o1 = PlaneObject()
    o1.point = base
    o1.normal = [0, 0, 1]
    o2 = PlaneObject()
    o2.point = [base[0], base[1], base[2] - 1.0]
    o2.normal = [0, 0, 1]
    pd1 = cut_grid(ug, o1)
    pd2 = cut_grid(ug, o2)
    assert pd1 is not pd2


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_cut_cache_respects_lru_capacity():
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    ug, _ = build_ugrid(ff)
    v = np.asarray(ff.vertices)
    base = [float(v[:, 0].mean()), float(v[:, 1].mean()),
            float(v[:, 2].mean())]
    for i in range(_CUT_CACHE_MAX + 4):
        obj = PlaneObject()
        obj.point = [base[0] + float(i), base[1], base[2]]
        obj.normal = [0, 0, 1]
        cut_grid(ug, obj)
    assert len(_cut_cache) <= _CUT_CACHE_MAX
