"""R123: what the FLD decoder reports must match what the file says.

Three fidelity defects, all measured on ex1_100.fld:

* ATMS was FABRICATED: three sites assigned it a copy of TEMP, so the GUI
  offered a physical quantity the file does not contain (the reader exposed
  15 variables where the file declares 8 LS_Scalar sections plus 2 vectors).
* names were decoded as ASCII with errors=replace, so the Japanese region
  names became "Xmax\ufffd\ufffd\ufffd", and the printability guard tested for
  pure ASCII -- which DROPPED any block containing a multi-byte character
  entirely, leaving volume region names EMPTY on a file that has four.
* the resulting None/str mix also made a legitimate 0.0 trim bound ambiguous
  elsewhere; here the visible symptom was the missing names.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest
from fv.crdl.mesh_fld import _decode_name, _looks_like_text  # noqa: E402
from fv.model import dataset  # noqa: E402

FLD = r"D:\training\cgns\examples\ex1_100.fld"


def test_utf8_names_decode_instead_of_replacing():
    """Cradle writes UTF-8; the reader decoded ASCII."""
    raw = "Xmax面".encode("utf-8")
    assert _decode_name(raw) == "Xmax面"
    assert "\ufffd" not in _decode_name(raw)


def test_printability_accepts_valid_utf8_and_rejects_binary():
    """The old ASCII-only guard silently discarded non-ASCII name blocks."""
    assert _looks_like_text("直方体領域".encode("utf-8"))
    assert _looks_like_text("PARTS1".encode("utf-8"))
    assert _looks_like_text(b"name\x00\x00")
    assert not _looks_like_text(b"\x01\x02\x03\x04")
    assert not _looks_like_text(b"")
    assert not _looks_like_text(b"\xff\xfe\x00\x01")


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_no_fabricated_variables():
    """ATMS was a copy of TEMP; the file declares neither as an alias."""
    ff = dataset.load_file(FLD)
    assert "ATMS" not in ff.variables, (
        "ATMS is fabricated: the fixture has no such variable")
    assert "TEMP" in ff.variables and "PRES" in ff.variables
    # every exposed scalar must be finite somewhere (no all-sentinel field)
    for name, info in ff.variables.items():
        arr = np.asarray(ff.variable_array(name), dtype=float)
        assert np.isfinite(arr).any(), name


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_region_names_are_readable_utf8():
    """They used to come back with replacement characters or not at all."""
    ff = dataset.load_file(FLD)
    names = [n for n, _ in (ff.surface_regions or [])]
    names += [n for n, _, c in (ff.bc_plan or []) if c]
    names += list(ff.volume_regions or [])
    assert names, "no regions were reported at all"
    for name in names:
        assert "\ufffd" not in name, ("%r was not decoded as UTF-8" % name)
        assert name.strip() == name and name


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_volume_region_names_are_not_empty():
    """A file with four volume regions reported none, because of the guard."""
    ff = dataset.load_file(FLD)
    assert ff.volume_regions, "volume region names are empty"
    assert all(isinstance(n, str) and n for n in ff.volume_regions)


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_multibyte_bc_name_survives_the_round_trip():
    """Xmax面 is the concrete case the ASCII decode corrupted."""
    ff = dataset.load_file(FLD)
    plan = [n for n, _, c in (ff.bc_plan or []) if c]
    joined = " ".join(plan)
    assert "Xmax面" in joined, joined[:200]
    # This fixture carries exactly five BC names with multi-byte text:
    # Xmax面, Xmin面, Ymax面 and the two (MAT) variants of Ymax面.  The ASCII
    # decode used to mangle every one of them.
    multibyte = [n for n in plan if any(ord(ch) > 127 for ch in n)]
    assert len(multibyte) == 5, multibyte
    assert "Xmin面" in multibyte and "Ymax面" in multibyte
