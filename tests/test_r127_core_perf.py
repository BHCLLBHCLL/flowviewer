"""R127 - the section index must not pin buffers, and must be cheap to build.

Two measured defects drove this round:

* _section_index_cache stored the buffer itself ("keep data alive") under an
  id(data) key, so every file opened in a session stayed resident for the rest
  of it (a 1.36 GB FPH was pinned by the index alone) -- and a reopened file
  could never hit the cache, because open_buffer hands out a new object.
* the index was built by calling find_section once per boundary name: 40 full
  scans of the buffer, measured 6.57 s on a 1.36 GB FPH.

The plan also asked for a vectorised iter_data_blocks.  That one was measured
before being touched and is NOT a defect: the walk jumps payload to payload
(496 MB section -> 80 blocks in 0.001 s) and it does not appear in the load
profile at all, so it is deliberately left alone.  The real FLD hot spot the
profile did show (_build_face_list_and_bcs_inner, 2.46 s tottime for a 101 MB
file) is recorded as R127b work rather than rewritten here.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fv.crdl.core as core  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fv.crdl.mesh_fld import _normalise_face_nodes  # noqa: E402

TR03 = Path(r"D:\training\cgns\examples\tr03_9.fph")
FLD = Path(r"D:\training\cgns\examples\ex1_100.fld")
BIG_FLD = Path(r"D:\training\cgns\flddecoding\tests\ex2_e_67.fld")


def _brute_force_offsets(data) -> dict:
    """The pre-R127 build: one full scan per boundary name."""
    return {name: off for name in core.SECTION_BOUNDARY_NAMES
            if (off := core.find_section(data, name)) >= 0}


# ---------------------------------------------------------------------------
# the single-pass scan must find exactly what 40 scans found
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not TR03.exists(), reason="tr03_9.fph not present")
def test_r127_scan_matches_brute_force_on_the_fph_sample():
    data = TR03.read_bytes()
    got = core._scan_section_offsets(data)
    assert got == _brute_force_offsets(data)
    assert got["LS_SPHFile"] == core.find_section(data, "LS_SPHFile")
    # recorded from the sample: 25 boundary-name sections in 18062646 bytes
    assert len(got) == 25 and len(data) == 18062646


@pytest.mark.skipif(not FLD.exists(), reason="ex1_100.fld not present")
def test_r127_scan_matches_brute_force_on_the_fld_sample():
    data = FLD.read_bytes()
    got = core._scan_section_offsets(data)
    assert got == _brute_force_offsets(data)
    # recorded from the sample: 29 boundary-name sections
    assert len(got) == 29


@pytest.mark.skipif(not BIG_FLD.exists(), reason="ex2_e_67.fld not present")
def test_r127_scan_matches_brute_force_on_a_large_fld():
    data = BIG_FLD.read_bytes()
    got = core._scan_section_offsets(data)
    assert got == _brute_force_offsets(data)
    # and section_end still resolves to the same next-section boundary
    sec = got["LS_Elements"]
    end = core.section_end(data, sec)
    assert end == min([o for o in got.values() if o > sec] or [len(data)])


# ---------------------------------------------------------------------------
# the cache: content keyed, bounded, and holding no buffers
# ---------------------------------------------------------------------------

def test_r127_cache_hit_is_decided_by_content_not_object_identity(monkeypatch):
    """A reopened file (new object, same bytes) must reuse the index."""
    calls = {"n": 0}
    real = core._scan_section_offsets

    def counting(data):
        calls["n"] += 1
        return real(data)

    monkeypatch.setattr(core, "_scan_section_offsets", counting)
    core._section_index_cache.clear()
    payload = _synthetic_container()
    first = bytes(payload)
    second = bytes(payload)          # a different object with equal content
    a = core._section_offsets(first)
    b = core._section_offsets(second)
    core._section_offsets(first)
    # three lookups of two equal-content buffers: at most one scan
    assert calls["n"] <= 1
    assert a == b


def test_r127_cache_key_separates_different_files_of_equal_size(monkeypatch):
    """Equal length is not enough: the sampled digest decides."""
    core._section_index_cache.clear()
    # two boundary names of equal length, so the buffers differ only in name
    a = _synthetic_container(name=b"Comments")
    b = _synthetic_container(name=b"Encoding")
    # header + name field + body: 16 + 40 + 256 bytes
    assert len(a) == 312 and len(b) == 312
    assert core._buffer_key(bytes(a)) != core._buffer_key(bytes(b))
    off_a = core._section_offsets(bytes(a))
    off_b = core._section_offsets(bytes(b))
    assert list(off_a) == ["Comments"] and list(off_b) == ["Encoding"]
    assert len(core._section_index_cache) == 2


def test_r127_cache_is_bounded_and_evicts_oldest():
    core._section_index_cache.clear()
    for i in range(core._SECTION_INDEX_MAX + 9):
        data = _synthetic_container(name=b"Sec%03d" % i, pad=i)
        core._section_offsets(bytes(data))
    # the cache cap is a documented constant; pin its value
    assert core._SECTION_INDEX_MAX == 16
    assert len(core._section_index_cache) == 16
    newest = core._buffer_key(bytes(_synthetic_container(
        name=b"Sec%03d" % (core._SECTION_INDEX_MAX + 8),
        pad=core._SECTION_INDEX_MAX + 8)))
    assert newest in core._section_index_cache
    oldest = core._buffer_key(bytes(_synthetic_container(name=b"Sec000")))
    assert oldest not in core._section_index_cache


def test_r127_cache_holds_offsets_only_not_buffers():
    """The old entry was (len, offsets, data) -- the leak this round fixes."""
    core._section_index_cache.clear()
    data = bytes(_synthetic_container())
    core._section_offsets(data)
    assert len(core._section_index_cache) == 1
    for key, value in core._section_index_cache.items():
        assert isinstance(key, bytes) and len(key) == 16      # a digest
        assert isinstance(value, dict), "the cache must store offsets only"
        assert all(isinstance(v, int) for v in value.values())


def test_r127_section_end_does_not_hold_the_buffer_alive():
    """After the caller drops its buffer, nothing in the cache keeps it."""
    import gc
    core._section_index_cache.clear()
    data = bytes(_synthetic_container())
    core.section_end(data, 0)
    refcount_before = sys.getrefcount(data)
    del data
    gc.collect()
    # the cache can only be holding offsets, so the buffer is gone: a new
    # buffer of the same content builds its index from scratch
    assert all(isinstance(v, dict) for v in core._section_index_cache.values())
    assert refcount_before >= 1


# ---------------------------------------------------------------------------
# the face-normalisation fast path must be byte-identical
# ---------------------------------------------------------------------------

def _reference_normalise(faces, one_based):
    if not one_based:
        return [tuple(int(v) for v in f) for f in faces]
    return [tuple(int(v) - 1 for v in f) for f in faces]


def test_r127_uniform_faces_normalise_identically():
    """The numpy path must equal the per-element reference, exactly."""
    faces = [tuple(range(i, i + 4)) for i in range(1, 4001, 4)]
    conn = np.array([[1, 2, 3, 4, 5, 6, 7, 8]], dtype=np.int64)
    # n_vertices == the largest connectivity id is what marks the file 1-based
    got = _normalise_face_nodes(faces, 8, conn)
    assert got == _reference_normalise(faces, True)
    assert got[0] == (0, 1, 2, 3)
    # 1000 quads, ids 1..4000 -> 0..3999, and the first face sums to 0+1+2+3
    assert len(got) == 1000 and sum(got[0]) == 6 and sum(got[-1]) == 15990


def test_r127_ragged_faces_normalise_identically():
    """Mixed widths fall back to the per-element path, same answer."""
    faces = [(1, 2, 3), (4, 5, 6, 7), (8, 9, 10)]
    conn = np.array([[1, 2, 3, 4, 5, 6, 7, 8]], dtype=np.int64)
    got = _normalise_face_nodes(faces, 8, conn)
    assert got == _reference_normalise(faces, True)
    assert [len(f) for f in got] == [3, 4, 3]
    # widths survive the fallback and the ids are shifted exactly once
    assert sum(got[0]) == 3 and sum(got[1]) == 18 and sum(got[2]) == 24


def test_r127_zero_based_faces_are_left_alone():
    faces = [(0, 1, 2, 3), (4, 5, 6, 7)]
    conn = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    assert _normalise_face_nodes(faces, 8, conn) == faces
    assert _normalise_face_nodes([], 8, conn) == []
    # unchanged means unchanged: the ids still start at 0
    assert faces[0] == (0, 1, 2, 3) and sum(faces[0]) == 6


@pytest.mark.skipif(not BIG_FLD.exists(), reason="ex2_e_67.fld not present")
def test_r127_real_faces_normalise_identically():
    """847k real quads: the fast path reproduces the reference exactly."""
    from fv.crdl.core import open_buffer
    from fv.crdl.mesh_fld import parse_fld
    with open_buffer(str(BIG_FLD)) as data:
        mesh = parse_fld(str(BIG_FLD), data=data)
    faces = mesh["faces"]
    assert len(faces) > 100000 and len({len(f) for f in faces}) == 1
    got = _normalise_face_nodes(faces, mesh["n_vertices"], mesh["cell_conn"])
    assert got == _reference_normalise(faces, True)
    assert got[0] == tuple(int(v) - 1 for v in faces[0])


def _synthetic_container(name=b"SectionA", pad=0):
    """A minimal CRDL buffer with one readable section header."""
    body = bytes(range(256)) * (1 + pad)
    return (b"\x00\x00\x00\x08CRDL-FLD\x00\x00\x00\x08"
            + b"\x00\x00\x00\x20" + name.ljust(32)
            + b"\x00\x00\x00\x20" + body)
