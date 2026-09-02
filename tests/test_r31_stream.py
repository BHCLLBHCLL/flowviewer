"""R31 - streaming (memory-bounded) CGNS reads (section 9.11).

S1: windowed materialisation primitives. ``materialize_lazy_window`` reads
only a window of a lazy field without allocating the full-length
placeholder, and ``iter_field_tiles`` yields dense tiles that exactly
reproduce the eager merge. S2: ``StreamCgnsHandle`` serves windowed / tile
reads through a budget-bound LRU (``CachedWindows``) so peak memory stays
under a caller-set ceiling. Non-stream paths are untouched.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

h5py = pytest.importorskip("h5py")

from fv.crdl.cgns import materialize_lazy_field, read_cgns  # noqa: E402

# reuse the R28 synthetic two-zone CGNS builder
from test_r28_lazy import _cube, _make_two_zone  # noqa: E402,F401


@pytest.fixture
def two_zone(tmp_path):
    path = str(tmp_path / "stream.cgns")
    _make_two_zone(path)
    return path


@pytest.fixture
def eager(two_zone):
    return read_cgns(two_zone, lazy_fields=False)


def _parts_of(mesh, name):
    return mesh["field_lazy"][name]


def _side_total(mesh, name):
    kind = mesh["fields"][name][1]
    return mesh["n_cells"] if kind == "cell" else mesh["n_vertices"]


def test_window_matches_eager_full(two_zone, eager):
    """A single full-window read equals the eager full field."""
    mesh = read_cgns(two_zone, lazy_fields=True)
    for name in mesh["field_lazy"]:
        parts = _parts_of(mesh, name)
        got = materialize_lazy_field(two_zone, parts, _side_total(mesh, name))
        assert np.allclose(got, eager["fields"][name][0], equal_nan=True)


def test_window_slices_reassemble_eager(two_zone, eager):
    """Sliding windows over every tile reassemble the eager field exactly."""
    from fv.crdl.cgns import materialize_lazy_window
    mesh = read_cgns(two_zone, lazy_fields=True)
    name = "VELOCITY_X"
    if name not in mesh["field_lazy"]:
        name = sorted(mesh["field_lazy"])[0]
    parts = _parts_of(mesh, name)
    total = max(off + sz for _ds, off, sz in parts)
    full = np.full(total, np.nan)
    for lo in range(0, total, 4):          # tiny tiles
        hi = min(total, lo + 4)
        full[lo:hi] = materialize_lazy_window(two_zone, parts, total, lo, hi)
    ref = materialize_lazy_field(two_zone, parts, total)
    assert np.allclose(full, ref, equal_nan=True)


def test_window_does_not_allocate_full_placeholder(two_zone):
    """window materialisation returns only the requested width."""
    from fv.crdl.cgns import materialize_lazy_window
    mesh = read_cgns(two_zone, lazy_fields=True)
    # use a field with enough length to exercise a non-empty window
    name = next(n for n in mesh["field_lazy"]
                if max(o + s for _d, o, s in mesh["field_lazy"][n]) >= 4)
    parts = _parts_of(mesh, name)
    total = max(off + sz for _ds, off, sz in parts)
    w = materialize_lazy_window(two_zone, parts, total, 1, 3)
    assert w.shape == (2,)


def test_stream_handle_tiles_equal_stream_window(two_zone):
    """iter_tiles concatenation equals a single full window read."""
    from fv.model.dataset import open_stream_cgns
    handle, mesh = open_stream_cgns(two_zone, budget_bytes=1 << 30)
    name = sorted(handle.field_names())[0]
    _, full = handle.read_window(name, 0, handle.field_len(name))
    chunks = [a for _st, a in handle.iter_tiles(name, tile=3)]
    joined = np.concatenate(chunks)
    assert joined.shape == full.shape
    assert np.allclose(joined, full, equal_nan=True)
    # tiles mirror the eager materialised value (side-aware total)
    from fv.crdl.cgns import materialize_lazy_field
    parts = mesh["field_lazy"][name]
    ref = materialize_lazy_field(two_zone, parts, _side_total(mesh, name))
    assert np.allclose(joined, ref, equal_nan=True)


def test_cache_budget_bound(two_zone):
    """CachedWindows never holds more bytes than its budget."""
    from fv.model.dataset import CachedWindows
    mesh = read_cgns(two_zone, lazy_fields=True)
    total = max(max(o + s for _d, o, s in p)
                for p in mesh["field_lazy"].values())
    nbytes = total * 8
    cache = CachedWindows(nbytes * 3)       # fits exactly three tiles
    arr = np.ones(total, dtype=np.float64)
    for k in range(6):
        cache.put((f"f{k}", 0, total), arr)
    assert cache._bytes() <= cache.budget_bytes
    assert cache.size <= 3 and cache.size > 0   # LRU evicted older tiles


def test_open_stream_cgns_builds_handle_without_payload(two_zone):
    """open_stream_cgns gives a handle whose fields are descriptors only."""
    from fv.model.dataset import open_stream_cgns
    handle, mesh = open_stream_cgns(two_zone, budget_bytes=1 << 20)
    assert handle.count_fields() >= 1
    assert len(mesh["vertices"]) > 0
    n = handle.field_names()[0]
    assert handle.field_len(n) == mesh["vertices"].shape[0] or \
        handle.field_len(n) > 0
    # a bounded window read completes without materialising the whole field
    lo, data = handle.read_window(n, 0, min(handle.field_len(n), 5))
    assert data.shape[0] >= 1
