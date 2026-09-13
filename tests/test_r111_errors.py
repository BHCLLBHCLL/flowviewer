"""R111: load failures must be loud instead of producing an empty viewer.

Before R111 a file whose container or section layout was not understood fell
through to the GPH parser and came back as a FieldFile with 0 vertices,
0 cells and no variables - indistinguishable from a valid empty model.  A
1.1 GB .rph (a CRDL-FLD container holding Ph_R* result sections) took ~10 s
to scan and then produced a blank viewport with no message.  The same class
of silence hid corrupt connectivity (out-of-range node ids were clamped onto
the last vertex) and unreadable CGNS fields (dropped from the variable list).

These tests pin the loud behaviour.
"""

import os
import sys
import warnings
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"
GPH = r"D:\training\cgns\examples\tr03.gph"

def _crdl_container(payload: bytes) -> bytes:
    """Minimal CRDL-FLD file: 8-byte header, magic, then *payload*."""
    return b"\x00\x00\x00\x08" + b"CRDL-FLD" + b"\x00\x00\x00\x08" + payload


def test_non_cradle_file_raises(tmp_path):
    p = tmp_path / "random.bin"
    p.write_bytes(b"this is not a Cradle file at all\n" * 40)
    from fv.model.dataset import load_file

    with pytest.raises(ValueError) as exc:
        load_file(str(p))
    msg = str(exc.value)
    assert "cannot read" in msg
    assert "not a Cradle CRDL-FLD container" in msg


def test_crdl_container_without_known_sections_raises(tmp_path):
    p = tmp_path / "mystery.fph"
    p.write_bytes(_crdl_container(b"\x00" * 256))
    from fv.model.dataset import load_file

    with pytest.raises(ValueError) as exc:
        load_file(str(p))
    assert "unsupported section layout" in str(exc.value)


def test_rph_layout_is_named_in_the_error(tmp_path):
    """An RPH is a CRDL-FLD container with Ph_R* sections; say so."""
    name = b"Ph_R1_BasicData1".ljust(32)  # find_section needs the full 32 bytes
    payload = b"\x00\x00\x00\x20" + name + b"\x00" * 64
    p = tmp_path / "sample.rph"
    p.write_bytes(_crdl_container(payload))
    from fv.model.dataset import load_file

    with pytest.raises(ValueError) as exc:
        load_file(str(p))
    msg = str(exc.value)
    assert "RPH" in msg and "Ph_R" in msg


def test_empty_field_file_is_never_returned(tmp_path):
    """The old failure mode: a silent FieldFile(0 vertices, 0 cells)."""
    p = tmp_path / "junk.fph"
    p.write_bytes(b"\xab" * 512)
    from fv.model.dataset import load_file

    try:
        ff = load_file(str(p))
    except ValueError:
        return  # loud failure = the contract
    pytest.fail(
        "load_file returned %r instead of raising (vertices=%r cells=%r)"
        % (ff, ff.n_vertices, ff.n_cells))


@pytest.mark.skipif(not Path(GPH).exists(), reason="sample not present")
def test_geometry_only_gph_reports_no_fields():
    """A GPH has a mesh but no field variables; that must be stated."""
    from fv.model.dataset import load_file

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ff = load_file(GPH)
    assert ff.variables == {}
    assert ff.meta.get("no_fields") is True
    assert any("no field variables" in str(w.message) for w in caught)
    assert ff.n_vertices > 0  # the mesh itself still loads


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_fph_with_fields_does_not_flag_no_fields():
    from fv.model.dataset import load_file

    ff = load_file(FPH)
    assert ff.variables
    assert "no_fields" not in ff.meta


def test_out_of_range_face_nodes_raise():
    from fv.crdl.mesh_gph import validate_face_nodes

    ok = np.array([0, 1, 2, 3], dtype=np.int64)
    validate_face_nodes(ok, 4)  # must not raise
    validate_face_nodes(np.array([], dtype=np.int64), 0)  # empty is fine

    with pytest.raises(ValueError) as exc:
        validate_face_nodes(np.array([0, 1, 2, 9], dtype=np.int64), 4)
    msg = str(exc.value)
    assert "out of range" in msg and "max id 9" in msg


def test_sids_element_codes_match_the_standard():
    """R111: 13/14 were swapped, desynchronising MIXED streams."""
    from fv.crdl.cgns import _CODE_CELLS

    # cgnslib SIDS: PYRA_5=12, PYRA_14=13, PENTA_6=14.
    assert _CODE_CELLS[12] == (14, 5)   # PYRA_5
    assert _CODE_CELLS[13] == (14, 5)   # PYRA_14 (rendered as its 5 base nodes)
    assert _CODE_CELLS[14] == (13, 6)   # PENTA_6, six nodes
    assert _CODE_CELLS[17] == (12, 8)   # HEXA_8
