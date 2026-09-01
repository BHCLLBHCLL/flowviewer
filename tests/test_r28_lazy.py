"""R28 - CGNS variable-level lazy materialization tests (section 9.8).

A lazy open reads geometry (coords/connectivity/BC) but leaves every
FlowSolution payload unread; the merge records per-field
``(ds_path, offset, size)`` parts so ``load_variable()`` materialises the
exact eager array on first access, NaN padding included.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

h5py = pytest.importorskip("h5py")

from fv.crdl.cgns import read_cgns  # noqa: E402


def _cube(offset):
    return np.array([[x + offset, y, z] for z in (0.0, 1.0) for y in (0.0, 1.0)
                     for x in (0.0, 1.0)])


def _write_zone(zone, coords, fields):
    """One unstructured HEXA_8 zone with optional FlowSolution fields."""
    zt = zone.create_group("ZoneType")
    zt.create_dataset(" data", data=np.array([b"Unstructured"]))
    gc = zone.create_group("GridCoordinates")
    for ax, col in zip(("CoordinateX", "CoordinateY", "CoordinateZ"), range(3)):
        g = gc.create_group(ax)
        g.create_dataset(" data", data=coords[:, col])
    el = zone.create_group("Elements")
    el.create_dataset(" data", data=np.array([17], dtype=np.int32))
    el.create_dataset("ElementRange",
                      data=np.array([1, 1], dtype=np.int64))
    el.create_dataset("ElementConnectivity",
                      data=np.arange(1, 9, dtype=np.int64))
    if fields:
        fs = zone.create_group("FlowSolution")
        for fname, arr in fields.items():
            pg = fs.create_group(fname)
            pg.create_dataset(" data", data=arr)


def _make_two_zone(path):
    """ZoneA (P node + C cell) and ZoneB (P node only), one hexa each."""
    with h5py.File(path, "w") as f:
        base = f.create_group("Base")
        _write_zone(base.create_group("ZoneA"), _cube(0.0),
                    {"P": np.arange(8.0), "C": np.array([42.0])})
        _write_zone(base.create_group("ZoneB"), _cube(10.0),
                    {"P": np.arange(8.0) + 100.0})
    return str(path)


def test_lazy_mesh_geometry_matches_eager(tmp_path):
    """Lazy open keeps geometry identical and skips field payloads."""
    path = _make_two_zone(tmp_path / "r28.cgns")
    eager = read_cgns(path)
    lazy = read_cgns(path, lazy_fields=True)
    assert eager is not None and lazy is not None
    assert lazy["n_vertices"] == eager["n_vertices"] == 16
    assert lazy["n_cells"] == eager["n_cells"] == 2
    assert np.array_equal(lazy["vertices"], eager["vertices"])
    assert np.array_equal(lazy["cell_conn"], eager["cell_conn"])
    assert np.array_equal(lazy["cell_types"], eager["cell_types"])
    # placeholders: right shape/location, all NaN (nothing was read)
    for name, (arr, loc) in lazy["fields"].items():
        eloc = eager["fields"][name][1]
        assert loc == eloc
        assert arr.shape == eager["fields"][name][0].shape
        assert not np.isfinite(arr).any()
    # descriptors: P spans both zones on the node side, C only ZoneA cells
    assert len(lazy["field_lazy"]["P"]) == 2
    assert len(lazy["field_lazy"]["C"]) == 1


def test_lazy_materialize_matches_eager(tmp_path):
    """First access materialises the exact eager array, NaN padding included."""
    from fv.model.dataset import cgns_load
    path = _make_two_zone(tmp_path / "r28.cgns")
    ff_eager = cgns_load(path)
    ff_lazy = cgns_load(path, lazy_vars=True)
    assert set(ff_lazy.variables) == set(ff_eager.variables)
    for name, vi in ff_lazy.variables.items():
        assert vi.array is None and vi.lazy_kind == "cgns"
        assert vi.location == ff_eager.variables[name].location
    p_lazy = ff_lazy.load_variable("P")
    p_eager = ff_eager.load_variable("P")
    assert np.array_equal(p_lazy, p_eager)
    # C is cell-centred: ZoneA value + NaN padding for ZoneB
    c_lazy = ff_lazy.load_variable("C")
    c_eager = ff_eager.load_variable("C")
    assert np.array_equal(c_lazy, c_eager, equal_nan=True)
    assert c_lazy.shape == (2,) and c_lazy[0] == 42.0 and np.isnan(c_lazy[1])


def test_load_variable_caches_after_materialize(tmp_path):
    """Second access returns the cached array (no re-read)."""
    from fv.model.dataset import cgns_load
    path = _make_two_zone(tmp_path / "r28.cgns")
    ff = cgns_load(path, lazy_vars=True)
    a1 = ff.load_variable("P")
    assert ff.variables["P"].array is a1
    a2 = ff.variable_array("P")
    assert a2 is a1


def test_load_file_lazy_dispatch(tmp_path):
    """load_file(lazy_vars=True) routes .cgns through the lazy loader."""
    from fv.model.dataset import load_file
    path = _make_two_zone(tmp_path / "r28.cgns")
    ff_lazy = load_file(path, lazy_vars=True)
    assert ff_lazy.kind == "cgns"
    assert ff_lazy.variables["P"].array is None
    assert ff_lazy.variables["P"].lazy_kind == "cgns"
    ff_eager = load_file(path)
    assert ff_eager.variables["P"].array is not None
    assert np.array_equal(ff_lazy.load_variable("P"),
                          ff_eager.variables["P"].array)


def test_lazy_parallel_merge_matches_serial(tmp_path):
    """The R26 parallel decode path honours lazy_fields identically."""
    path = _make_two_zone(tmp_path / "r28.cgns")
    serial = read_cgns(path, lazy_fields=True)
    par = read_cgns(path, workers=2, use_threads=True, lazy_fields=True)
    assert np.array_equal(par["vertices"], serial["vertices"])
    assert par["field_lazy"]["P"] == serial["field_lazy"]["P"]
    assert par["field_lazy"]["C"] == serial["field_lazy"]["C"]
    from fv.crdl.cgns import materialize_lazy_field
    for name in ("P", "C"):
        loc = par["fields"][name][1]
        total = par["n_vertices"] if loc == "node" else par["n_cells"]
        a = materialize_lazy_field(path, par["field_lazy"][name], total)
        b = read_cgns(path)["fields"][name][0]
        assert np.array_equal(a, b, equal_nan=True)
