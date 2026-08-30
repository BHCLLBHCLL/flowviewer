"""FLD parser tests against the real ex1_e_from_sxemt_run.fld sample."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fv.crdl import mesh_fld  # noqa: E402

SAMPLE_FLD = r"D:\training\cgns\flddecoding\tests\ex1_e_from_sxemt_run.fld"


@pytest.mark.skipif(not Path(SAMPLE_FLD).exists(), reason="sample fld not present")
def test_parse_fld_counts():
    m = mesh_fld.parse_fld(SAMPLE_FLD)
    assert m["n_vertices"] == 21_145
    assert m["n_cells"] == 18_240
    assert m["cell_conn"] is not None
    assert m["cell_conn"].shape == (18_240, 8)


@pytest.mark.skipif(not Path(SAMPLE_FLD).exists(), reason="sample fld not present")
def test_parse_fld_bcs():
    m = mesh_fld.parse_fld(SAMPLE_FLD)
    assert len(m["faces"]) == 12_430
    assert any("Xmax" in n or n == "Xmax" for n, _, _ in m["bc_plan"])


@pytest.mark.skipif(not Path(SAMPLE_FLD).exists(), reason="sample fld not present")
def test_parse_fld_fields():
    m = mesh_fld.parse_fld(SAMPLE_FLD)
    fields = m["fields"]
    assert fields["PRES"].size == 21_145
    assert "TEMP" in fields
    assert "VECTX" in fields and "VECTZ" in fields


def test_parse_fld_missing_file():
    with pytest.raises(OSError):
        mesh_fld.parse_fld(r"D:\training\cgns\flowviewer\tests\__missing__.fld")
