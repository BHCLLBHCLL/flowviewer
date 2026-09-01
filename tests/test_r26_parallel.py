"""R26-S2: process-pool multi-zone CGNS reads are bit-identical to serial.

Both backends (HDF5 ``read_cgns`` and ADF ``read_cgns_adf``) accept a
``workers`` argument.  When workers > 1 the zones are decoded in a
process pool and then merged on the main thread in zone order; the result
must be byte-for-byte equal to the serial path so the output is
deterministic regardless of worker count.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest
from fv.crdl.cgns import read_cgns  # noqa: E402
from fv.crdl.cgns_adf import (  # noqa: E402
    AdfNode,
    is_cgns_adf,
    read_cgns_adf,
    write_adf,
)


def _assert_mesh_equal(a, b):
    assert a is not None and b is not None
    assert a["n_vertices"] == b["n_vertices"]
    assert a["n_cells"] == b["n_cells"]
    assert a["volume_regions"] == b["volume_regions"]
    assert a["base_name"] == b["base_name"]
    np.testing.assert_array_equal(a["vertices"], b["vertices"])
    if a["cell_conn"] is None:
        assert b["cell_conn"] is None
    else:
        np.testing.assert_array_equal(a["cell_conn"], b["cell_conn"])
    if a["cell_types"] is None:
        assert b["cell_types"] is None
    else:
        np.testing.assert_array_equal(a["cell_types"], b["cell_types"])
    assert a["fields"].keys() == b["fields"].keys()
    for k in a["fields"]:
        np.testing.assert_array_equal(a["fields"][k][0], b["fields"][k][0])
        assert a["fields"][k][1] == b["fields"][k][1]
    assert len(a["surface_regions"]) == len(b["surface_regions"])
    for (n1, i1), (n2, i2) in zip(a["surface_regions"], b["surface_regions"]):
        assert n1 == n2
        np.testing.assert_array_equal(i1, i2)


# ---- HDF5 helpers -----------------------------------------------------


def _h5_zone(zone, coords, conn, etype_code, field=None):
    zt = zone.create_group("ZoneType")
    zt.create_dataset(" data", data=np.array([b"Unstructured"]))
    gc = zone.create_group("GridCoordinates")
    for ax, col in zip(("CoordinateX", "CoordinateY", "CoordinateZ"),
                       range(3)):
        g = gc.create_group(ax)
        g.create_dataset(" data", data=coords[:, col])
    el = zone.create_group("Elements")
    el.create_dataset(" data", data=np.array([etype_code], dtype=np.int32))
    el.create_dataset("ElementRange",
                      data=np.array([1, len(conn)], dtype=np.int64))
    el.create_dataset("ElementConnectivity",
                      data=np.asarray(conn, dtype=np.int64).ravel())
    if field is not None:
        fs = zone.create_group("FlowSolution")
        pg = fs.create_group("P")
        pg.create_dataset(" data", data=field)


def _h5_structured_zone(zone, coords3d):
    zt = zone.create_group("ZoneType")
    zt.create_dataset(" data", data=np.array([b"Structured"]))
    gc = zone.create_group("GridCoordinates")
    for ax, idx in zip(("CoordinateX", "CoordinateY", "CoordinateZ"),
                       range(3)):
        g = gc.create_group(ax)
        g.create_dataset(" data", data=coords3d[..., idx])


def _make_multi_zone_hdf5(path):
    import h5py
    cube = np.array([[x, y, z] for z in (0.0, 1.0) for y in (0.0, 1.0)
                     for x in (0.0, 1.0)])
    with h5py.File(path, "w") as f:
        base = f.create_group("Base")
        z1 = base.create_group("ZoneA")
        _h5_zone(z1, cube, [[1, 2, 3, 4, 5, 6, 7, 8]], 17,
                 field=np.arange(8, dtype=np.float64))
        z2 = base.create_group("ZoneB")
        _h5_zone(z2, cube * 2.0, [[1, 2, 3, 4, 5, 6, 7, 8]], 17,
                 field=np.arange(8, 16, dtype=np.float64))
        z3 = base.create_group("ZoneC")
        _h5_structured_zone(z3, cube.reshape(2, 2, 2, 3))


# ---- ADF helpers ------------------------------------------------------


def _adf_hex_zone(name, verts, value):
    zone = AdfNode(name, "Zone_t")
    zone.children["ZoneType"] = AdfNode(
        "ZoneType", "ZoneType_t", "C1", (12,), b"Unstructured")
    gc = AdfNode("GridCoordinates", "GridCoordinates_t")
    zone.children["GridCoordinates"] = gc
    verts = np.asarray(verts, dtype=np.float64)
    for axis, col in zip(("CoordinateX", "CoordinateY", "CoordinateZ"),
                         verts.T):
        gc.children[axis] = AdfNode(axis, "DataArray_t", "R8",
                                    (verts.shape[0],),
                                    np.ascontiguousarray(col))
    els = AdfNode("Hex", "Elements_t")
    zone.children["Hex"] = els
    els.children["ElementType"] = AdfNode(
        "ElementType", "ElementType_t", "C1", (6,), b"HEXA_8")
    els.children["ElementRange"] = AdfNode(
        "ElementRange", "IndexRange_t", "I4", (2,),
        np.array([1, 1], dtype="i4"))
    els.children["ElementConnectivity"] = AdfNode(
        "ElementConnectivity", "DataArray_t", "I4", (8,),
        np.arange(1, 9, dtype="i4"))
    fs = AdfNode("FlowSolution", "FlowSolution_t")
    zone.children["FlowSolution"] = fs
    fs.children["Pressure"] = AdfNode(
        "Pressure", "DataArray_t", "R8", (verts.shape[0],),
        np.full(verts.shape[0], value, dtype=np.float64))
    return zone


def _make_multi_zone_adf(path):
    root = AdfNode("HDF5 MotherNode", "RootNode_t")
    base = AdfNode("Base", "CGNSBase_t")
    root.children["Base"] = base
    base.children["ZoneA"] = _adf_hex_zone(
        "ZoneA", [[x, y, z] for z in (0.0, 1.0) for y in (0.0, 1.0)
                  for x in (0.0, 1.0)], 1.0)
    base.children["ZoneB"] = _adf_hex_zone(
        "ZoneB", [[x * 2, y * 2, z * 2] for z in (0.0, 1.0)
                  for y in (0.0, 1.0) for x in (0.0, 1.0)], 2.0)
    write_adf(str(path), root)


# ---- tests ------------------------------------------------------------


def test_cgns_hdf5_parallel_equals_serial(tmp_path):
    """read_cgns(workers=k) is bit-identical to read_cgns(workers=0)."""
    pytest.importorskip("h5py")
    path = tmp_path / "multi.cgns"
    _make_multi_zone_hdf5(str(path))
    serial = read_cgns(str(path), workers=0)
    assert serial is not None
    assert serial["n_vertices"] == 24 and serial["n_cells"] == 3
    for n in (2, 3):
        par = read_cgns(str(path), workers=n)
        _assert_mesh_equal(serial, par)
    # regression-guard thread-pool path stays bit-identical too
    th = read_cgns(str(path), workers=3, use_threads=True)
    _assert_mesh_equal(serial, th)


def test_cgns_hdf5_worker_picklable(tmp_path):
    """Module-level HDF5 worker is picklable and returns a 7-tuple."""
    pytest.importorskip("h5py")
    import pickle

    from fv.crdl.cgns import _decode_zone_hdf5
    path = tmp_path / "multi.cgns"
    _make_multi_zone_hdf5(str(path))
    fn = pickle.loads(pickle.dumps(_decode_zone_hdf5))
    out = fn((str(path), "Base", "ZoneA"))
    assert out is not None and len(out) == 7
    assert out[0].shape == (8, 3)


def test_cgns_adf_parallel_equals_serial(tmp_path):
    """read_cgns_adf(workers=k) is bit-identical to read_cgns_adf(0)."""
    path = tmp_path / "multi.cgns"
    _make_multi_zone_adf(str(path))
    assert is_cgns_adf(str(path)) is True
    serial = read_cgns_adf(str(path), workers=0)
    assert serial is not None
    assert serial["n_vertices"] == 16 and serial["n_cells"] == 2
    for n in (2, 3):
        par = read_cgns_adf(str(path), workers=n)
        _assert_mesh_equal(serial, par)
    # regression-guard thread-pool path stays bit-identical too
    th = read_cgns_adf(str(path), workers=3, use_threads=True)
    _assert_mesh_equal(serial, th)


def test_cgns_adf_worker_picklable(tmp_path):
    """Module-level ADF worker is picklable and returns an 8-tuple."""
    import pickle

    from fv.crdl.cgns_adf import _decode_zone_adf
    path = tmp_path / "multi.cgns"
    _make_multi_zone_adf(str(path))
    fn = pickle.loads(pickle.dumps(_decode_zone_adf))
    out = fn((str(path), "Base", "ZoneA"))
    assert out is not None and len(out) == 8
    assert out[0].shape == (8, 3)
