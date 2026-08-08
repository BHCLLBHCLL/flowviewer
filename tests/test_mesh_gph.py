"""GPH / FPH mesh parser tests against the real tr03_9.fph sample."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fv.crdl import mesh_gph  # noqa: E402

SAMPLE_FPH = r"D:\training\cgns\examples\tr03_9.fph"


@pytest.mark.skipif(not Path(SAMPLE_FPH).exists(), reason="sample fph not present")
def test_parse_fph_tr03_counts():
    m = mesh_gph.parse_gph_mesh(SAMPLE_FPH)
    assert m["n_vertices"] == 221_786
    assert m["n_cells"] == 63_697
    ld = m["link_data"]
    assert ld is not None
    assert ld["n_faces"] == 323_827
    assert m["n_vertices"] == 221_786


@pytest.mark.skipif(not Path(SAMPLE_FPH).exists(), reason="sample fph not present")
def test_parse_fph_regions():
    m = mesh_gph.parse_gph_mesh(SAMPLE_FPH)
    assert "Case" in m["parts"]
    assert "Rotate" in m["parts"]
    assert any("inlet" in n for n, _ in m["surface_regions"])


@pytest.mark.skipif(not Path(SAMPLE_FPH).exists(), reason="sample fph not present")
def test_parse_fph_face_nodes_in_bounds():
    m = mesh_gph.parse_gph_mesh(SAMPLE_FPH)
    fn = m["link_data"]["face_nodes"]
    assert fn.min() >= 0
    assert fn.max() < m["n_vertices"]


def test_parse_ls_nodes_none_for_empty():
    data = b"CRDL-FLD" + b"\x00" * 64
    xyz, n = mesh_gph.parse_ls_nodes_xyz(data)
    assert n == 0
    assert xyz is None