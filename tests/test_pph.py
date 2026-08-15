"""PPH (scFLOW project ZIP) loader tests against real .pph samples.

Primary sample: the pphdecoding box2 project (404 KB, 944 cells) - fast.
Tests are skipped when the sample directory is absent.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

PPH_BOX2 = Path(r"D:\training\cgns\pphdecoding\box2.pph")
PPH_BOX = Path(r"D:\training\cgns\examples\box\box.pph")


@pytest.fixture(scope="module")
def sample():
    if not PPH_BOX2.exists():
        pytest.skip("pphdecoding box2.pph sample not present")
    return PPH_BOX2


def test_pph_members_and_project(sample):
    """Member list + main.xml project name."""
    from fv.crdl.pph import pph_members, pph_project_name
    names = [n for n, _, _ in pph_members(str(sample))]
    assert "main.xml" in names
    assert "meshinggroup1.gph" in names
    assert pph_project_name(str(sample)) == "box"


def test_parse_pph_mesh_counts(sample):
    """Embedded volume mesh parses with known counts (box2)."""
    from fv.crdl.pph import parse_pph
    m = parse_pph(str(sample))
    assert m["n_vertices"] == 1305
    assert m["n_cells"] == 944
    assert m["link_data"]["n_faces"] == 3168
    assert m["pph_gph_member"] == "meshinggroup1.gph"
    assert m["pph_project"] == "box"
    assert "FluidRegion" in m["volume_regions"]


def test_pph_load_fieldfile(sample):
    """Loader registry + FieldFile consumable by the renderer."""
    from fv.model.dataset import pph_load
    from fv.model.loaders import can_load, probe_format
    assert can_load(str(sample)) is True
    assert probe_format(str(sample)) == "pph"
    ff = pph_load(str(sample))
    assert ff.kind == "pph"
    assert ff.n_cells == 944 and ff.n_vertices == 1305
    assert ff.link_data is not None
    assert ff.pph_project == "box"
    assert "meshinggroup1.gph" in ff.pph_members
    # volume grid builds from the polyhedral topology
    from fv.render.plane import build_ugrid
    ug, cc = build_ugrid(ff)
    assert ug.GetNumberOfCells() == 944


def test_pph_variant_without_part_mdl():
    """examples/box/box.pph lacks _part.mdl - still loads."""
    if not PPH_BOX.exists():
        pytest.skip("box.pph sample not present")
    from fv.crdl.pph import parse_pph
    m = parse_pph(str(PPH_BOX))
    assert m["n_vertices"] == 52 and m["n_cells"] == 135
    assert not any(n.endswith("_part.mdl") for n in m["pph_members"])


def test_pph_no_gph_member_raises(tmp_path):
    """A zip without a .gph member is rejected with a clear error."""
    p = tmp_path / "no_mesh.pph"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("main.xml", "<project><name>x</name></project>")
    from fv.crdl.pph import parse_pph
    with pytest.raises(ValueError, match="no embedded"):
        parse_pph(str(p))


def test_pph_not_zip_raises(tmp_path):
    p = tmp_path / "junk.pph"
    p.write_bytes(b"not a zip at all")
    from fv.crdl.pph import parse_pph
    with pytest.raises(ValueError, match="not a PPH"):
        parse_pph(str(p))
