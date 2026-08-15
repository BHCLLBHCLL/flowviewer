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
