"""R125 - what an FPH file holds that the variable list does not show.

An FPH LS_SPHFile section carries more than the cell-centred EC_Scalar /
EC_Vector sections the reader parses: every file measured here also holds
face-centred FC_Scalar / FC_Vector sections, i.e. wall quantities such as
YPLS, USTR and HTFX.  They were read by nobody and reported by nobody, so a
file full of wall data opened exactly like one without it.

Decoding them is not possible from the file alone: the arrays are plain 1-D
float32 blocks whose length is a *face* count (measured on tr03_9.fph: 12537
= the face count of two surface regions, plus 311, 141 and 12707) and there is
no index array tying a value to a face.  Guessing the association would invent
data, which is what R123 was about, so this round reports the sections with
their exact dimensions instead.

Also measured while checking the plan's "keep every nodal frame" item: the
EC_* sections of the four FPH files on this machine hold exactly one array per
scalar and three per vector (the X/Y/Z components) -- there are no extra time
frames to keep, so the existing single-frame read is correct for them.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fv.crdl.fields import (  # noqa: E402
    fph_unparsed_fields,
    parse_fph_flow_solution,
)

TR03 = Path(r"D:\training\cgns\examples\tr03_9.fph")
EXPRE = Path(r"D:\training\cgns\examples\exPRE04-1_37.fph")


# ---------------------------------------------------------------------------
# synthetic LS_SPHFile container
# ---------------------------------------------------------------------------

def _i4(v):
    return int(v).to_bytes(4, "big", signed=True)


def _block(payload):
    """A container payload: [12][byte_count][payload][byte_count]."""
    return _i4(12) + _i4(len(payload)) + payload + _i4(len(payload))


def _name_block(text):
    return _block(text.encode("ascii").ljust(32, b"\0"))


def _array_block(values):
    """One array: [dim0][1] descriptor, then the float32 payload."""
    arr = np.asarray(values, dtype=">f4")
    return _i4(arr.size) + _i4(1) + _block(arr.tobytes())


def _fph_buffer(fields):
    """A CRDL container holding one LS_SPHFile section.

    Each field is a (name, description, [arrays]) triple written the way the
    real files are: name block, descriptive name block, then its arrays.
    """
    body = b""
    for name, description, arrays in fields:
        body += _name_block(name)
        if description:
            body += _name_block(description)
        for values in arrays:
            body += _array_block(values)
    # the container pads the 32-byte section name with spaces
    section = _i4(32) + b"LS_SPHFile".ljust(32) + _i4(32) + body
    return _i4(8) + b"CRDL-FLD" + _i4(8) + section


N_CELLS = 3


def _cell_buffer():
    """Two cell fields (one scalar, one vector) and two face sections."""
    return _fph_buffer([
        ("EC_Scalar:PRES", "pressure", [[1.5, -2.25, 3.0]]),
        ("EC_Vector:VEL", "velocity", [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0],
                                       [7.0, 8.0, 9.0]]),
        ("FC_Scalar:YPLS", "YPLS", [[0.5, 1.5], [2.5, 3.5], [4.5, 5.5]]),
        ("FC_Vector:WALL", "wall velocity", [[1.0, 2.0], [3.0, 4.0],
                                             [5.0, 6.0], [7.0, 8.0],
                                             [9.0, 10.0]]),
    ])


# ---------------------------------------------------------------------------
# parsing stays exact
# ---------------------------------------------------------------------------

def test_r125_cell_fields_parse_to_the_stored_values():
    """The EC fields keep their exact values and component order."""
    out = parse_fph_flow_solution(_cell_buffer(), N_CELLS)
    assert sorted(out) == ["PRES", "VELX", "VELY", "VELZ"]
    assert out["PRES"].tolist() == [1.5, -2.25, 3.0]
    assert out["VELX"].tolist() == [1.0, 2.0, 3.0]
    assert out["VELY"].tolist() == [4.0, 5.0, 6.0]
    assert out["VELZ"].tolist() == [7.0, 8.0, 9.0]


def test_r125_lazy_descriptors_point_at_the_same_blocks():
    """Lazy mode describes the same arrays without reading them."""
    eager = parse_fph_flow_solution(_cell_buffer(), N_CELLS)
    lazy = parse_fph_flow_solution(_cell_buffer(), N_CELLS, lazy=True)
    assert sorted(lazy) == sorted(eager)
    buf = _cell_buffer()
    for _name, desc in lazy.items():
        section, _bidx, dtype, count = desc
        assert section == "LS_SPHFile" and dtype == ">f4"
        assert count == N_CELLS
    # materialising the descriptor reproduces the eager array
    from fv.crdl.core import find_section, iter_data_blocks, section_end
    _sec, bidx, _dt, _count = lazy["PRES"]
    s = find_section(buf, "LS_SPHFile")
    e = section_end(buf, s)
    blocks = list(iter_data_blocks(buf, s, e))
    p, bc = blocks[bidx]
    got = np.frombuffer(buf, dtype=">f4", count=bc // 4, offset=p)
    assert got.tolist() == eager["PRES"].tolist()


# ---------------------------------------------------------------------------
# what is not attached
# ---------------------------------------------------------------------------

def test_r125_face_sections_are_reported_with_their_dimensions():
    """FC_* sections are listed with their arrays, not dropped in silence."""
    out = fph_unparsed_fields(_cell_buffer(), N_CELLS)
    by_name = {u["name"]: u for u in out}
    assert sorted(by_name) == ["FC_Scalar:YPLS", "FC_Vector:WALL"]
    ypls = by_name["FC_Scalar:YPLS"]
    assert ypls["location"] == "face" and ypls["variable"] == "YPLS"
    assert [d for d, _nb in ypls["arrays"]] == [2, 2, 2]
    wall = by_name["FC_Vector:WALL"]
    assert wall["components"] == 3
    assert [d for d, _nb in wall["arrays"]] == [2, 2, 2, 2, 2]
    assert "face index list" in wall["reason"]
    # the parsed cell fields must not be reported as unparsed
    assert "EC_Scalar:PRES" not in by_name
    assert "EC_Vector:VEL" not in by_name


def test_r125_unreadable_cell_field_is_reported_not_skipped():
    """A cell field whose arrays are the wrong length cannot vanish."""
    buf = _fph_buffer([("EC_Scalar:ODD", "odd", [[1.0, 2.0]])])
    assert parse_fph_flow_solution(buf, N_CELLS) == {}
    out = fph_unparsed_fields(buf, N_CELLS)
    assert [u["name"] for u in out] == ["EC_Scalar:ODD"]
    assert out[0]["location"] == "cell"
    assert "does not match the 3 cells" in out[0]["reason"]


def test_r125_unknown_field_prefix_is_reported():
    """An unrecognised *_Scalar prefix is surfaced rather than ignored."""
    buf = _fph_buffer([("XX_Scalar:FOO", "foo", [[1.0, 2.0, 3.0]])])
    out = fph_unparsed_fields(buf, N_CELLS)
    assert [u["name"] for u in out] == ["XX_Scalar:FOO"]
    assert out[0]["location"] == "unknown"
    assert out[0]["reason"] == "unknown field section prefix 'XX_Scalar'"


# ---------------------------------------------------------------------------
# the real files
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not TR03.exists(), reason="tr03_9.fph not present")
def test_r125_real_tr03_reports_its_wall_sections():
    """tr03_9.fph: seven face sections, measured dimensions."""
    raw = TR03.read_bytes()
    out = fph_unparsed_fields(raw, 63697)
    by_name = {u["name"]: u for u in out}
    assert sorted(by_name) == [
        "FC_Scalar:PRES", "FC_Scalar:TEPS", "FC_Scalar:TPRS", "FC_Scalar:TURK",
        "FC_Scalar:USTR", "FC_Scalar:YPLS", "FC_Vector:VEL"]
    assert [d for d, _nb in by_name["FC_Scalar:YPLS"]["arrays"]] == [12537] * 3
    assert [d for d, _nb in by_name["FC_Vector:VEL"]["arrays"]] == [12707] * 5
    assert [d for d, _nb in by_name["FC_Scalar:TURK"]["arrays"]] == [311] * 3
    assert by_name["FC_Scalar:PRES"]["arrays"][0][0] == 141
    assert by_name["FC_Scalar:TPRS"]["arrays"] == []
    # and the cell fields are still parsed, one array per scalar
    cell = parse_fph_flow_solution(raw, 63697)
    assert sorted(cell) == ["EVIS", "LNAM_RV001X", "LNAM_RV001Y", "LNAM_RV001Z",
                            "PRES", "TEPS", "TPRS", "TURK", "VELX", "VELY",
                            "VELZ"]
    assert all(arr.shape == (63697,) for arr in cell.values())


@pytest.mark.skipif(not TR03.exists(), reason="tr03_9.fph not present")
def test_r125_loader_records_unparsed_sections_in_meta():
    """The loader keeps the report on the FieldFile, not just in a log."""
    from fv.model.dataset import load_file
    ff = load_file(str(TR03))
    assert list(ff.variables) == ["PRES", "TURK", "TEPS", "EVIS", "TPRS",
                                  "VELX", "VELY", "VELZ", "LNAM_RV001X",
                                  "LNAM_RV001Y", "LNAM_RV001Z"]
    names = [u["name"] for u in ff.meta["unparsed_fields"]]
    assert "FC_Scalar:YPLS" in names and "FC_Vector:VEL" in names
    assert len(names) == 7
    assert all(v.location == "cell" for v in ff.variables.values())
