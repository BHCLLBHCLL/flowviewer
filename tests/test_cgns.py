"""CGNS-HDF5 reader + pipeline tests (P1.2)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

CGNS = r"D:\training\cgns\CGNS-4.5.1\src\tests\data\cgnslib_vers-4400.cgns"
FPH = r"D:\training\cgns\examples\tr03_9.fph"


@pytest.mark.skipif(not Path(CGNS).exists(), reason="sample not present")
def test_read_cgns_counts():
    """CGNS-HDF5 sample: 3213 nodes / 2560 hexahedra / node fields (P1.2)."""
    from fv.crdl.cgns import is_cgns_hdf5, read_cgns
    assert is_cgns_hdf5(CGNS) is True
    d = read_cgns(CGNS)
    assert d is not None
    assert d["vertices"].shape == (3213, 3)
    assert d["cell_conn"].shape == (2560, 8)
    assert set(d["cell_types"]) == {12}  # VTK_HEXAHEDRON
    assert "Density" in d["fields"] and "Pressure" in d["fields"]
    assert d["fields"]["Pressure"][1] == "node"
    names = [n for n, _ in d["surface_regions"]]
    assert "Walls" in names

@pytest.mark.skipif(not Path(CGNS).exists(), reason="sample not present")
def test_cgns_not_hdf5():
    """Non-CGNS HDF5/legacy files are rejected by the probe."""
    from fv.crdl.cgns import is_cgns_hdf5
    if Path(FPH).exists():
        assert is_cgns_hdf5(FPH) is False
    assert is_cgns_hdf5(r"D:\training\cgns\no_such_file.cgns") is False

@pytest.mark.skipif(not Path(CGNS).exists(), reason="sample not present")
def test_cgns_load_fieldfile():
    """cgns_load produces a FieldFile consumable by the renderer (P1.2)."""
    from fv.model.dataset import cgns_load
    from fv.model.loaders import can_load
    assert can_load(CGNS) is True
    ff = cgns_load(CGNS)
    assert ff.kind == "cgns"
    assert ff.n_cells == 2560 and ff.n_vertices == 3213
    assert ff.cell_types is not None
    assert "Pressure" in ff.variables
    assert ff.variables["Pressure"].location == "node"
    # volume grid builds with mixed-cell support
    from fv.render.plane import build_ugrid
    ug, cc = build_ugrid(ff)
    assert ug.GetNumberOfCells() == 2560
    assert cc is False

@pytest.mark.skipif(not Path(CGNS).exists(), reason="sample not present")
def test_cgns_scene_headless():
    """Scene.build accepts a CGNS FieldFile (headless layers)."""
    from fv.model.dataset import cgns_load
    from fv.render.scene import Scene
    ff = cgns_load(CGNS)
    sc = Scene(enable_3d=False)
    sc.build(ff)
    assert "grid" in sc.actor_names()


def _write_zone(zone, coords, conn, etype_code, field=None):
    """Create a minimal CGNS SIDS zone inside an h5py parent."""
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


def _write_structured_zone(zone, coords3d):
    zt = zone.create_group("ZoneType")
    zt.create_dataset(" data", data=np.array([b"Structured"]))
    gc = zone.create_group("GridCoordinates")
    for ax, idx in zip(("CoordinateX", "CoordinateY", "CoordinateZ"),
                       range(3)):
        g = gc.create_group(ax)
        g.create_dataset(" data", data=coords3d[..., idx])


def test_cgns_mixed_multi_zone_structured_p21(tmp_path):
    """P2.1: MIXED streams, multi-zone merge and structured zones."""
    import h5py
    from fv.crdl.cgns import read_cgns
    path = tmp_path / "p21.cgns"
    cube = np.array([[x, y, z] for z in (0.0, 1.0) for y in (0.0, 1.0)
                     for x in (0.0, 1.0)])
    with h5py.File(path, "w") as f:
        base = f.create_group("Base")
        # zone 1: MIXED = one TETRA + one HEXA (SIDS 1-based ids)
        z1 = base.create_group("ZoneMixed")
        _write_zone(z1, cube,
                    [[10, 1, 2, 3, 4, 17, 1, 2, 3, 4, 5, 6, 7, 8]], 20,
                    field=np.arange(8, dtype=np.float64))
        # zone 2: structured (2,2,2) -> one hexa
        z2 = base.create_group("ZoneStruct")
        _write_structured_zone(z2, cube.reshape(2, 2, 2, 3))
    d = read_cgns(str(path))
    assert d is not None
    # two zones merged: 16 vertices, 3 cells (tet + hex + struct hex)
    assert d["n_vertices"] == 16
    assert d["n_cells"] == 3
    assert set(int(t) for t in d["cell_types"]) == {10, 12}
    assert d["volume_regions"] == ["ZoneMixed", "ZoneStruct"]
    # node field merged with NaN padding for the zone lacking it
    p, loc = d["fields"]["P"]
    assert loc == "node" and p.shape == (16,)
    assert np.isfinite(p[:8]).all() and not np.isfinite(p[8:]).any()
    # tet connectivity padded with -1 in the 8-wide merge
    assert d["cell_conn"].shape == (3, 8)
    # merged mesh builds in the renderer (tet + hex + struct hex)
    pytest.importorskip("vtk")
    from fv.model.dataset import cgns_load
    from fv.render.plane import build_ugrid
    ff = cgns_load(str(path))
    ug, _ = build_ugrid(ff)
    assert ug.GetNumberOfCells() == 3


def test_cgns_mixed_stream_decode_p21():
    """P2.1: MIXED stream decoder handles ragged element widths."""
    import numpy as np
    from fv.crdl.cgns import _read_mixed_stream
    stream = np.array([10, 1, 2, 3, 4, 17, 5, 6, 7, 8, 9, 10, 11, 12])
    rows, types = _read_mixed_stream(stream)
    assert rows.shape == (2, 8)
    assert list(types) == [10, 12]
    assert rows[0, :4].tolist() == [0, 1, 2, 3]
    assert rows[0, 4:].tolist() == [-1] * 4
    assert rows[1].tolist() == [4, 5, 6, 7, 8, 9, 10, 11]