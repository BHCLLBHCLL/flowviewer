"""R130 - missing-format decisions: binary STL, .neu, .rph.

Binary STL is what CAD tools write by default, and parse_stl read the file as
text: the 80-byte header and 50-byte records carry NULs, no "vertex " line
survives, and the mesh was rejected as unreadable. The .rph decision was
already taken in R111 (an explicit "no RPH parser" error, pinned by
test_r111_errors), and .neu is not registered at all, so this file pins the
binary reader and the honest failure of an unsupported extension.
"""

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fv.crdl.neutral import parse_stl  # noqa: E402

#: two triangles of a unit tetrahedron corner, in both STL encodings
TRIS = [((0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        ((0.0, 1.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))]


def _write_binary(path):
    with open(path, "wb") as fh:
        fh.write(b"binary stl".ljust(80, b"\0"))
        fh.write(struct.pack("<I", len(TRIS)))
        for n, a, b, c in TRIS:
            fh.write(struct.pack("<3f", *n) + struct.pack("<3f", *a)
                     + struct.pack("<3f", *b) + struct.pack("<3f", *c)
                     + struct.pack("<H", 0))
    return str(path)


def _write_ascii(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("solid t\n")
        for n, a, b, c in TRIS:
            fh.write("facet normal %g %g %g\n outer loop\n" % n)
            for v in (a, b, c):
                fh.write("  vertex %g %g %g\n" % v)
            fh.write(" endloop\nendfacet\n")
        fh.write("endsolid t\n")
    return str(path)


def test_r130_binary_stl_matches_the_ascii_encoding(tmp_path):
    """The same mesh in both encodings must give identical arrays."""
    bin_mesh = parse_stl(_write_binary(tmp_path / "bin.stl"))
    ascii_mesh = parse_stl(_write_ascii(tmp_path / "ascii.stl"))
    assert bin_mesh is not None and ascii_mesh is not None
    assert bin_mesh["n_vertices"] == 6 and bin_mesh["n_faces"] == 2
    assert ascii_mesh["n_vertices"] == 6 and ascii_mesh["n_faces"] == 2
    assert bin_mesh["faces"] == ascii_mesh["faces"]
    assert (bin_mesh["vertices"] == ascii_mesh["vertices"]).all()
    # recorded coordinates of the first record
    assert bin_mesh["vertices"][0].tolist() == [0.0, 0.0, 0.0]
    assert bin_mesh["vertices"][2].tolist() == [0.0, 1.0, 0.0]


def test_r130_binary_stl_loads_through_the_dataset(tmp_path):
    from fv.model.dataset import load_file
    ff = load_file(_write_binary(tmp_path / "bin.stl"))
    assert ff.n_vertices == 6
    assert ff.kind == "neutral"


def test_r130_truncated_binary_stl_is_rejected_not_guessed(tmp_path):
    path = tmp_path / "cut.stl"
    path.write_bytes(b"bin".ljust(80, b"\0") + struct.pack("<I", 4))
    assert parse_stl(str(path)) is None


def test_r130_unregistered_neutral_extension_fails_loudly(tmp_path):
    """.neu has no loader: it must raise, not open as an empty model."""
    from fv.model.dataset import load_file
    path = tmp_path / "gambit.neu"
    path.write_text("       5\n  1 0.0 0.0 0.0\n", encoding="utf-8")
    with pytest.raises(ValueError) as err:
        load_file(str(path))
    msg = str(err.value)
    # the message must name the real cause: no Gambit parser, not a bad file
    assert "Gambit" in msg and ".neu" in msg
    assert "OBJ, STL (ascii and binary) and PLY" in msg
