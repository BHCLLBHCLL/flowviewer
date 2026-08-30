"""Marc Mentat .t16 / .t19 post-file reader."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from fv.crdl.marc import _post_name, is_marc_post, parse_marc, parse_marc_post
from fv.model import loaders
from fv.model.dataset import load_file, marc_load

EXAMPLE_DAT = (
    Path(__file__).resolve().parents[1]
    / "Marc_Mentat_Scripting-main"
    / "marcmentat_files"
    / "example_model_0.dat"
)
EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "Marc_Mentat_Scripting-main"
    / "marcmentat_files"
    / "example_model_0.t16"
)


def _rec(payload: bytes) -> bytes:
    n = len(payload)
    return struct.pack("<I", n) + payload + struct.pack("<I", n)


def _a1(text: str, nwords: int = 70) -> bytes:
    s = (text + " " * nwords)[:nwords]
    return b"".join(bytes((ord(c), 0x20, 0x20, 0x20)) for c in s)


def _beg(code: str, name: str) -> bytes:
    return _rec(_a1("=beg=%s (%s)" % (code, name)))


def _end() -> bytes:
    return _rec(_a1("=end="))


def _i4(*vals: int) -> bytes:
    return _rec(struct.pack("<" + "i" * len(vals), *vals))


def _f4(*vals: float) -> bytes:
    return _rec(struct.pack("<" + "f" * len(vals), *vals))


def _coord(nid: int, x: float, y: float) -> bytes:
    return _rec(struct.pack("<iff", nid, x, y))


def write_tiny_t16(path: Path) -> Path:
    """2-D unit quad, one increment, one post-code, known displacements."""
    blob = b"".join([
        _beg("50100", "Analysis Title"),
        _rec(_a1("tiny")),
        _end(),
        _beg("50200", "Analysis Verification Data"),
        _i4(1, 4, 1, 2, 1, -1, 1, 0, 2, 4, 1, 0, 0, 14, 0, 0, 0, 0),
        _end(),
        _beg("50602", "Element Variable Postcodes"),
        _rec(struct.pack("<i", 681) + _a1("", 48)),
        _end(),
        _beg("50702", "Element Connectivities"),
        _i4(0, 4, 4),
        _i4(1, 11, 4, 1, 2, 3, 4),
        _end(),
        _beg("50800", "Nodal Coordinates"),
        _coord(1, 0.0, 0.0),
        _coord(2, 1.0, 0.0),
        _coord(3, 1.0, 1.0),
        _coord(4, 0.0, 1.0),
        _end(),
        _beg("51701", "Integer Increment Verification Data"),
        _i4(0, 1, 0, 101, 2, 0, 0, 0, 0, 0, 0, 0),
        _end(),
        _beg("51801", "Real Increment Verification Data"),
        _i4(0),
        _rec(struct.pack("<d", 0.5) + b"\x00" * 88),
        _end(),
        _beg("52300", "Element Integration Point Values"),
        _f4(42.0),
        _end(),
        _beg("52401", "Nodal Results"),
        _i4(1, 2),
        _rec(_a1("Displacement", 48)),
        _i4(1, 0, 0, 2, 0, 0, -1, 0, 0, 0, 0, 0),
        _f4(0.0, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
        _end(),
    ])
    path.write_bytes(blob)
    return path


def write_tiny_t19(path: Path) -> Path:
    path.write_text("\n".join([
        "=beg=50100 (Analysis Title)",
        "tiny",
        "=end=",
        "=beg=50200 (Analysis Verification Data)",
        "1 4 1 2 1 -1 1 0 2 4 1 0 0 14 0 0 0 0",
        "=end=",
        "=beg=50602 (Element Variable Postcodes)",
        "681",
        "=end=",
        "=beg=50702 (Element Connectivities)",
        "0 4 4",
        "1 11 4 1 2 3 4",
        "=end=",
        "=beg=50800 (Nodal Coordinates)",
        "1 0.0 0.0",
        "2 1.0 0.0",
        "3 1.0 1.0",
        "4 0.0 1.0",
        "=end=",
        "=beg=51701 (Integer Increment Verification Data)",
        "0 2 0 101 2 0 0 0 0 0 0 0",
        "=end=",
        "=beg=52401 (Nodal Results)",
        "1 2",
        "0.0 0.0 0.1 0.2 0.3 0.4 0.5 0.6",
        "=end=",
    ]), encoding="utf-8")
    return path


def test_tiny_t16_mesh_and_fields(tmp_path):
    path = write_tiny_t16(tmp_path / "tiny.t16")
    assert is_marc_post(str(path))
    mesh = parse_marc_post(str(path))
    assert mesh is not None
    assert mesh["n_cells"] == 1
    assert mesh["n_vertices"] == 4
    assert mesh["cell_types"].tolist() == [9]
    assert mesh["meta"]["postrv"] == 14
    assert mesh["meta"]["last_increment"] == 1
    dx = mesh["fields"]["Displacement_X"][0]
    dy = mesh["fields"]["Displacement_Y"][0]
    assert dx.tolist() == pytest.approx([0.0, 0.1, 0.3, 0.5])
    assert dy.tolist() == pytest.approx([0.0, 0.2, 0.4, 0.6])
    assert mesh["fields"]["Cauchy_XX"][1] == "cell"
    assert mesh["fields"]["Cauchy_XX"][0].tolist() == pytest.approx([42.0])
    assert mesh["meta"]["times"][0] == pytest.approx(0.5)


def test_tiny_t19_and_load_file(tmp_path):
    path = write_tiny_t19(tmp_path / "tiny.t19")
    assert is_marc_post(str(path))
    ff = load_file(str(path))
    assert ff.kind == "marc"
    assert ff.n_cells == 1 and ff.n_vertices == 4
    assert ff.cycle == 2
    assert "Displacement" in ff.variables
    assert ff.variables["Displacement_X"].array[1] == pytest.approx(0.1)


def test_marc_load_t16_registry(tmp_path):
    path = write_tiny_t16(tmp_path / "q.t16")
    assert loaders.can_load(str(path))
    assert loaders.probe_format(str(path)) == "marc-post"
    ff = marc_load(str(path))
    assert ff.n_cells == 1
    assert ff.meta["ncrd"] == 2


def test_parse_rejects_junk(tmp_path):
    p = tmp_path / "nope.t16"
    p.write_bytes(b"not a marc post file")
    assert is_marc_post(str(p)) is False
    assert parse_marc_post(str(p)) is None
    with pytest.raises(ValueError, match="post file"):
        marc_load(str(p))


@pytest.mark.skipif(not EXAMPLE.exists(), reason="Mentat example t16 not present")
def test_example_model_0_t16():
    """Mentat 2021.4 sample: 25x25 unit, 2461 quads, last-inc displacements."""
    ff = load_file(str(EXAMPLE))
    assert ff.kind == "marc"
    assert ff.n_cells == 2461
    assert ff.cell_types[0] == 9
    assert ff.n_vertices == 2582
    assert ff.cycle == 90
    assert "Displacement_X" in ff.variables
    verts = ff.vertices
    corner = np.argmin((verts[:, 0] - 25.0) ** 2 + verts[:, 1] ** 2)
    assert verts[corner, 0] == pytest.approx(25.0)
    assert ff.variables["Displacement_X"].array[corner] == pytest.approx(
        3.1814255714416504)
    assert ff.variables["Displacement_Y"].array[corner] == pytest.approx(
        1.8095834255218506)
    assert "Cauchy_XX" in ff.variables
    assert ff.variables["Cauchy_XX"].location == "cell"
    assert ff.meta["postrv"] == 14
    assert ff.meta["n_increments"] == 91
    assert ff.meta["spec"] == "PLDUMP2000"
    assert len(ff.meta["times"]) == 91


def test_post_code_names():
    assert _post_name(17) == "Equiv_Mises"
    assert _post_name(47) == "Equiv_Cauchy"
    assert _post_name(341) == "Cauchy_XX"
    assert _post_name(686) == "Cauchy_ZX"
    assert _post_name(681, "My Label") == "My_Label"


def write_tiny_k7(path: Path) -> Path:
    """Classic K7 PLDUMP: 70A1 title, 18 ints, one quad, four nodes."""
    title = _a1("k7job")
    vfy = struct.pack("<18i", 0, 4, 1, 2, 1, 0, 1, 0, 2, 4, 1, 0, 0, 0, 0, 0, 0, 0)
    conn = struct.pack("<7i", 1, 11, 4, 1, 2, 3, 4)
    blob = b"".join([
        _rec(title),
        _rec(vfy),
        _rec(conn),
        _coord(1, 0.0, 0.0),
        _coord(2, 1.0, 0.0),
        _coord(3, 1.0, 1.0),
        _coord(4, 0.0, 1.0),
    ])
    path.write_bytes(blob)
    return path


def test_classic_k7_pldump(tmp_path):
    path = write_tiny_k7(tmp_path / "old.t16")
    assert is_marc_post(str(path))
    mesh = parse_marc_post(str(path))
    assert mesh is not None
    assert mesh["meta"]["spec"] == "PLDUMP-K7"
    assert mesh["n_cells"] == 1 and mesh["n_vertices"] == 4
    assert mesh["cell_types"].tolist() == [9]


@pytest.mark.skipif(not EXAMPLE_DAT.exists(), reason="Mentat example dat not present")
def test_example_model_0_mentat_dat():
    """Volume C Mentat deck: connectivity + coordinates, 2582 geometric nodes."""
    mesh = parse_marc(str(EXAMPLE_DAT))
    assert mesh is not None
    assert mesh["n_cells"] == 2461
    assert mesh["n_vertices"] == 2582
    assert mesh["cell_types"][0] == 9
    assert mesh["vertices"][mesh["node_order"][2]][0] == pytest.approx(25.0)
