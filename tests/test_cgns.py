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