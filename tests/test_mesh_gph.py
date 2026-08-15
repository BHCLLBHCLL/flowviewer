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


SAMPLE_GPH = r"D:\training\cgns\examples\tr03.gph"


@pytest.mark.skipif(not Path(SAMPLE_FPH).exists(), reason="sample fph not present")
def test_parse_fph_meta_and_element_centers():
    """Header metadata + precomputed Element_Center (n_cells, 3)."""
    m = mesh_gph.parse_gph_mesh(SAMPLE_FPH)
    assert m["meta"]["Application"] == "SCFLOW"
    assert m["meta"].get("Comments") == "PolyHedra"
    ec = m["element_centers"]
    assert ec is not None and ec.shape == (63_697, 3)
    import numpy as np
    assert np.isfinite(ec).all()


@pytest.mark.skipif(not Path(SAMPLE_GPH).exists(), reason="sample gph not present")
def test_parse_gph_element_flags():
    """Element_InformationFlag → per-element flag array (i4)."""
    import numpy as np
    m = mesh_gph.parse_gph_mesh(SAMPLE_GPH)
    assert m["meta"]["Application"] == "SCTpre"
    flags = m["element_flags"]
    assert flags is not None and flags.shape == (63_882,)
    valid = {0, 1, 4, 5, 8, 9, -2147483648, -2147483647}
    assert set(np.unique(flags).tolist()) <= valid


@pytest.mark.skipif(not Path(SAMPLE_GPH).exists(), reason="sample gph not present")
def test_load_file_gph_kind():
    """Standalone .gph loads with kind "gph" (metadata item)."""
    from fv.model.dataset import load_file
    ff = load_file(SAMPLE_GPH)
    assert ff.kind == "gph"
    assert ff.meta.get("Application") == "SCTpre"


def test_ply_loader_registered():
    """neutral_load covers PLY and "ply" is registered."""
    from fv.model import loaders
    assert "ply" in loaders.loaders()
