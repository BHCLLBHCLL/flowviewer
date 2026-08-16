"""iFLD metadata scan + EMT alias loader tests (F)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FLD_EX1 = Path(r"D:\training\cgns\flddecoding\tests\ex1_e_from_sxemt_run.fld")
FPH_TR03 = Path(r"D:\training\cgns\examples\tr03_9.fph")
SCTETA = Path(r"C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64")
SCTETA = SCTETA / "Samples_POST" / "FLD" / "SCTeta_tutorial.fld"


def test_scan_ifld_on_fld():
    """scan_ifld reads counts + variable names without full parse (D3)."""
    from fv.crdl.ifld import scan_ifld
    if not SCTETA.exists():
        pytest.skip("SCTeta sample not present")
    s = scan_ifld(str(SCTETA))
    assert s is not None
    assert s["n_cells"] == 361_868
    assert s["n_vertices"] > 0
    assert "Pressure" in s["variables"]
    assert s["file_size"] == SCTETA.stat().st_size


def test_ifld_loader_scan_attached(tmp_path):
    """ifld loader = FLD parse + ifld_scan meta summary."""
    if not FLD_EX1.exists():
        pytest.skip("ex1 fld sample not present")
    dst = tmp_path / "case.ifld"
    shutil.copyfile(FLD_EX1, dst)
    from fv.model.dataset import ifld_load
    from fv.model.loaders import can_load
    assert can_load(str(dst)) is True
    ff = ifld_load(str(dst))
    assert ff.kind == "fld" and ff.n_cells == 18_240
    scan = ff.meta.get("ifld_scan")
    assert scan is not None and scan["n_cells"] == 18_240


def test_emt_alias_loads_fph_family(tmp_path):
    """EMT registry alias: CRDL content routes to the GPH/FPH parser."""
    if not FPH_TR03.exists():
        pytest.skip("tr03_9.fph not present")
    dst = tmp_path / "case.emt"
    shutil.copyfile(FPH_TR03, dst)
    from fv.model.dataset import load_file
    from fv.model.loaders import can_load, probe_format
    assert can_load(str(dst)) is True
    assert probe_format(str(dst)) == "fph"  # fph-family alias
    ff = load_file(str(dst))
    assert ff.kind == "fph" and ff.n_cells == 63_697
    assert ff.link_data is not None


def test_ifld_trimming_partial_load(tmp_path):
    """Trimming Open: bounds-limited iFLD load re-indexes mesh+fields (P2.6)."""
    if not FLD_EX1.exists():
        pytest.skip("ex1 fld sample not present")
    import numpy as np
    from fv import api
    from fv.crdl.ifld import trim_fld_mesh
    from fv.crdl.mesh_fld import parse_fld
    from fv.model.dataset import ifld_load

    full = parse_fld(str(FLD_EX1))
    v = full["vertices"]
    bounds = (float(np.median(v[:, 0])), float(v[:, 0].max()),
              float(np.median(v[:, 1])), float(v[:, 1].max()),
              float(np.median(v[:, 2])), float(v[:, 2].max()))
    mesh = trim_fld_mesh(full, bounds)
    assert 0 < mesh["n_vertices"] < full["n_vertices"]
    assert 0 < mesh["n_cells"] < full["n_cells"]
    nv = mesh["n_vertices"]
    assert mesh["vertices"][:, 0].min() >= bounds[0]
    ids = mesh["cell_conn"][mesh["cell_conn"] >= 0]
    assert ids.min() >= 0 and ids.max() <= nv  # 0- or 1-based, in range
    assert all(a.size == nv for a in mesh["fields"].values())
    t = mesh["meta"]["ifld_trim"]
    assert t["kept_vertices"] == nv and t["kept_cells"] == mesh["n_cells"]
    assert t["total_cells"] == full["n_cells"]

    # end-to-end: trimmed loader keeps scan meta + trim record
    dst = tmp_path / "case.ifld"
    shutil.copyfile(FLD_EX1, dst)
    ff = ifld_load(str(dst), bounds)
    assert ff.n_vertices == nv and ff.n_cells == mesh["n_cells"]
    assert ff.meta["ifld_trim"]["bounds"] == bounds
    assert "ifld_scan" in ff.meta
    assert all(vi.array.size == nv for vi in ff.variables.values())

    # api passthrough matches the loader
    ff2 = api.open_ifld(str(dst), bounds)
    assert ff2.n_vertices == nv

    # degenerate boxes raise instead of returning junk
    with pytest.raises(ValueError):
        trim_fld_mesh(full, (1e18, 2e18, 1e18, 2e18, 1e18, 2e18))
    with pytest.raises(ValueError):
        trim_fld_mesh(full, (1.0, -1.0, 1.0, -1.0, 1.0, -1.0))


def test_parse_fld_trim_during_parse(tmp_path):
    """P1-3: bounds in parse_fld trim in-parse == post-process trim."""
    if not FLD_EX1.exists():
        pytest.skip("ex1 fld sample not present")
    import numpy as np
    from fv.crdl.ifld import trim_fld_mesh
    from fv.crdl.mesh_fld import parse_fld

    full = parse_fld(str(FLD_EX1))
    v = full["vertices"]
    bounds = (float(np.median(v[:, 0])), float(v[:, 0].max()),
              float(np.median(v[:, 1])), float(v[:, 1].max()),
              float(np.median(v[:, 2])), float(v[:, 2].max()))
    post = trim_fld_mesh(full, bounds)
    # in-parse trimming shares the index math, so mesh + fields agree
    direct = parse_fld(str(FLD_EX1), bounds=bounds)
    assert direct["n_vertices"] == post["n_vertices"]
    assert direct["n_cells"] == post["n_cells"]
    assert np.array_equal(direct["vertices"], post["vertices"])
    assert np.array_equal(direct["cell_conn"], post["cell_conn"])
    assert set(direct["fields"]) == set(post["fields"])
    for name in post["fields"]:
        assert np.allclose(direct["fields"][name], post["fields"][name])
    t = direct["meta"]["ifld_trim"]
    assert t["bounds"] == bounds
    assert t["kept_vertices"] == post["n_vertices"]
    assert t["kept_cells"] == post["n_cells"]
    assert t["total_cells"] == full["n_cells"]
    # in-parse trim raises on an empty box too
    with pytest.raises(ValueError):
        parse_fld(str(FLD_EX1), bounds=(1e18, 2e18, 1e18, 2e18, 1e18, 2e18))
    with pytest.raises(ValueError):
        parse_fld(str(FLD_EX1), bounds=(1.0, -1.0, 1.0, -1.0, 1.0, -1.0))
