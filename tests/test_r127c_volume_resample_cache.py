"""R127c - the resampled volume image is memoised (and invalidated by data).

fv/render/volume.py rebuilds a vtkResampleToImage + vtkSmartVolumeMapper on
every call.  Measured on the real 63,697-polyhedron sample
(tr03_9.fph, 64^3 samples): the resample alone is 34.2 s, while the rest of the
volume build (transfer functions, mapper, actor) is milliseconds.  Nothing in
that resample depends on a display parameter, so moving an opacity slider used
to re-pay it -- and so did every test that built a volume for the same file.

The cache key carries a content fingerprint of the scalar, because the
timeline rewrites the values of the same grid on a cycle switch; the tests
below pin both the hit and the invalidation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fv.render import volume as V  # noqa: E402

vtk = pytest.importorskip("vtk")
from vtk.util import numpy_support as _vns  # noqa: E402


def _grid(nx=3, ny=3, nz=3, values=None):
    """Small hex block with a cell scalar named PRES."""
    ug = vtk.vtkUnstructuredGrid()
    pts = vtk.vtkPoints()
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                pts.InsertNextPoint(float(i), float(j), float(k))
    ug.SetPoints(pts)

    def vid(i, j, k):
        return i + (nx + 1) * (j + (ny + 1) * k)

    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                ids = vtk.vtkIdList()
                for v in (vid(i, j, k), vid(i + 1, j, k),
                          vid(i + 1, j + 1, k), vid(i, j + 1, k),
                          vid(i, j, k + 1), vid(i + 1, j, k + 1),
                          vid(i + 1, j + 1, k + 1), vid(i, j + 1, k + 1)):
                    ids.InsertNextId(v)
                ug.InsertNextCell(vtk.VTK_HEXAHEDRON, ids)
    n_cells = ug.GetNumberOfCells()
    vals = np.arange(n_cells, dtype=np.float64) if values is None else values
    arr = _vns.numpy_to_vtk(np.ascontiguousarray(vals), deep=True)
    arr.SetName("PRES")
    ug.GetCellData().SetScalars(arr)
    return ug


@pytest.fixture(autouse=True)
def _clear_cache():
    V._RESAMPLE_CACHE.clear()
    yield
    V._RESAMPLE_CACHE.clear()


def test_r127c_resampled_image_is_reused():
    ug = _grid()
    first = V._resampled_image(ug, "PRES", 16)
    second = V._resampled_image(ug, "PRES", 16)
    assert first is not None
    assert second is first, "the second build re-ran the resample"
    assert len(V._RESAMPLE_CACHE) == 1


def test_r127c_changed_values_invalidate_the_cached_image():
    """A cycle switch rewrites the same grid; the image must not go stale."""
    ug = _grid()
    first = V._resampled_image(ug, "PRES", 16)
    vals = np.asarray(V._vns.vtk_to_numpy(
        ug.GetCellData().GetArray("PRES")), dtype=np.float64)
    arr = _vns.numpy_to_vtk(np.ascontiguousarray(vals * 10.0), deep=True)
    arr.SetName("PRES")
    ug.GetCellData().SetScalars(arr)
    second = V._resampled_image(ug, "PRES", 16)
    assert second is not None and second is not first
    assert len(V._RESAMPLE_CACHE) == 2
    r1 = first.GetPointData().GetArray("PRES").GetRange()
    r2 = second.GetPointData().GetArray("PRES").GetRange()
    assert r2[0] > r1[1] or r2[1] > r1[1], (r1, r2)


def test_r127c_sampling_dimension_is_part_of_the_key():
    ug = _grid()
    a = V._resampled_image(ug, "PRES", 16)
    b = V._resampled_image(ug, "PRES", 32)
    assert a is not None and b is not None and a is not b
    assert a.GetDimensions() != b.GetDimensions()


def test_r127c_cache_is_bounded():
    ug = _grid()
    for dim in (16, 20, 24, 28, 32, 36):
        V._resampled_image(ug, "PRES", dim)
    assert len(V._RESAMPLE_CACHE) <= V._RESAMPLE_CACHE_MAX


def test_r127c_missing_scalar_returns_none():
    ug = _grid()
    assert V._resampled_image(ug, "NOPE", 16) is None
    assert V._scalar_fingerprint(ug, "NOPE") is None


def test_r127c_volume_actor_reuses_the_image_between_builds():
    from fv.model.objects import VolumeObject
    ug = _grid()
    obj = VolumeObject()
    obj.show_scalar = True
    obj.scalar_var = "PRES"
    first = V._volume_actor(ug, "PRES", obj)
    second = V._volume_actor(ug, "PRES", obj)
    assert first is not None and second is not None
    img1 = first.GetMapper().GetInput()
    img2 = second.GetMapper().GetInput()
    assert img1 is img2, "the volume rebuild resampled again"
