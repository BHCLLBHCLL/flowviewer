"""R37 tests: probe-grid memoization + generic local polydata extraction.

Headless-safe and free of ``vtkCutter`` (which is what crashes on VTK >= 9.4.2
convex-point-set grids): only plain polydata point/array access and pure NumPy
nearest lookup are exercised, so the whole round verifies in any environment.
"""

from __future__ import annotations

import numpy as np
import pytest
import vtk
from fv.render.probe import (
    from_polydata,
    get_probe_grid,
    nearest_point,
    probe_polydata,
    probe_summary,
    reset_probe_grid,
)
from vtk.util import numpy_support

# ── pure NumPy nearest point ───────────────────────────────────────────────

def test_nearest_point_picks_closest_node():
    pts = np.array([[0.0, 0, 0], [1.0, 0, 0], [0.0, 1, 0], [50.0, 50, 50]])
    idx, sq = nearest_point(pts, (0.9, 0.1, 0.0))
    assert idx == 1  # [1,0,0]
    assert sq == pytest.approx(0.02)


def test_nearest_point_empty_yields_inf():
    idx, sq = nearest_point(np.zeros((0, 3)), (0.0, 0.0, 0.0))
    assert idx == -1
    assert np.isinf(sq)


# ── polydata → arrays ──────────────────────────────────────────────────────

def _tiny_polydata():
    pts = vtk.vtkPoints()
    for p in [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]:
        pts.InsertNextPoint(*p)
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    scal = numpy_support.numpy_to_vtk(np.array([10.0, 20.0, 30.0]),
                                      deep=True)
    scal.SetName("P")
    pd.GetPointData().AddArray(scal)
    vec = numpy_support.numpy_to_vtk(
        np.array([[1.0, 0, 0], [0.0, 2, 0], [0.0, 0, 3.0]]), deep=True)
    vec.SetName("V")
    pd.GetPointData().SetVectors(vec)
    return pd


def test_from_polydata_digs_points_and_arrays():
    points, parrs, _c = from_polydata(_tiny_polydata())
    assert points.shape == (3, 3)
    assert set(parrs) == {"P", "V"}
    assert parrs["P"][1] == "scalar"
    assert parrs["V"][1] == "vector"


# ── probe_polydata (data cursor) ───────────────────────────────────────────

def test_probe_polydata_nearest_point_and_values():
    res = probe_polydata(_tiny_polydata(), (0.9, 0.1, 0.0))
    assert res["query"] == pytest.approx((0.9, 0.1, 0.0))
    idx, coords = res["point"]
    assert idx == 1 and coords == pytest.approx((1.0, 0.0, 0.0))
    nearest = res["nearest"]
    assert nearest["P"] == ("scalar", 20.0)
    kind, vec = nearest["V"]
    assert kind == "vector" and vec == pytest.approx((0.0, 2.0, 0.0))


def test_probe_polydata_empty_safe():
    pd = vtk.vtkPolyData()
    res = probe_polydata(pd, (0.0, 0.0, 0.0))
    assert res["nearest"] == {}


def test_probe_polydata_tuple_input_without_vtk():
    # dependency-lite form: points + {name:(ndarray, kind)} + cell_arrays
    pts = np.array([[0.0, 0, 0], [5.0, 0, 0]])
    arrs = {"P": (np.array([1.0, 2.0]), "scalar")}
    res = probe_polydata((pts, arrs, {}), (4.9, 0.0, 0.0))
    assert res["point"][0] == 1
    assert res["nearest"]["P"] == ("scalar", 2.0)


def test_probe_summary_line():
    res = {"point": (0, (1.0, 2.0, 3.0)),
           "nearest": {"P": ("scalar", 0.25), "V": ("vector", (0.0, 1.0, 0.0))}}
    line = probe_summary(res)
    assert "xyz=1,2,3" in line
    assert "P=0.25" in line
    assert "V=(0,1,0)" in line


def test_probe_summary_empty():
    assert probe_summary({"nearest": {}}) == "(no data)"


# ── get_probe_grid memoization ─────────────────────────────────────────────

def test_get_probe_grid_builds_once_per_dataset(monkeypatch):
    calls = []

    def fake_build_ugrid(ff):
        calls.append(id(ff))
        return ("G", True)

    import fv.render.probe as probe
    monkeypatch.setattr(probe, "build_ugrid", fake_build_ugrid)
    reset_probe_grid()

    class FF:
        pass

    ff = FF()
    a = get_probe_grid(ff)
    b = get_probe_grid(ff)
    assert a == ("G", True) and b == ("G", True)
    assert calls == [id(ff)]  # one build, two lookups


def test_get_probe_grid_new_dataset_rebuilds_and_lru(monkeypatch):
    import fv.render.probe as probe
    monkeypatch.setattr(probe, "_PROBE_GRID_MAX", 2)
    imports = []

    def fake_build_ugrid(ff):
        imports.append(id(ff))
        return (id(ff), True)

    monkeypatch.setattr(probe, "build_ugrid", fake_build_ugrid)
    reset_probe_grid()

    class FF:
        pass

    ff1, ff2, ff3 = FF(), FF(), FF()
    get_probe_grid(ff1)
    get_probe_grid(ff2)  # evicts ff1 when ff3 arrives (cap 2)
    get_probe_grid(ff3)
    # ff1 was evicted → rebuilding it again re-invokes build_ugrid
    get_probe_grid(ff1)
    assert imports.count(id(ff1)) == 2


def test_get_probe_grid_returns_same_instances_then_rebuilds(monkeypatch):
    import fv.render.probe as probe
    monkeypatch.setattr(probe, "build_ugrid",
                        lambda ff: (f"G{id(ff)}", True), raising=False)
    reset_probe_grid()

    class FF:
        pass

    ff = FF()
    assert get_probe_grid(ff) == get_probe_grid(ff) == (f"G{id(ff)}", True)
