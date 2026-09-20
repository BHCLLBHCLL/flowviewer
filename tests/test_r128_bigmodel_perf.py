"""R128 - big-model costs: cell lookup per trace step, and cell centres.

Measured before touching anything (ex2_e_67.fld, 409188 cells):

* FldCellInterpolator.locate tested the bounding box of every cell on every
  query: 17.11 ms per call, and RK4 streamlines call it four times per step,
  so a single 200-step line spent about 13.7 s in lookups alone.
* _cell_centers_fph built one Python list per cell plus one .tolist() per face
  owner face: 22.77 s for the 63697-cell tr03_9_orig.cgns mesh.

Both now run off a vectorised path, and the results are pinned to the old ones:
the lookup digest below was recorded with the pre-R128 full-scan code, and the
cell-centre checksum with the pre-R128 per-cell loop.
"""

import os
import sys
import tracemalloc
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

FLD = Path(r"D:\training\cgns\flddecoding\tests\ex2_e_67.fld")
CGNS = Path(r"D:\training\cgns\examples\tr03_9_orig.cgns")

#: digest of the (cell id, weights) results for the 400 seeded query points
#: below, recorded with the pre-R128 full-scan locate (409188 cells)
LOCATE_DIGEST = "98fe23661e0b1ad0"

#: sum of every cell centre (x + y + z) on tr03_9_orig.cgns, recorded with the
#: pre-R128 per-cell loop
CENTRE_CHECKSUM = 57.648126


def _query_points(ff, n=400):
    """The first *n* of the 400 seeded query points used for the digest."""
    rng = np.random.default_rng(0)
    conn = np.asarray(ff.cell_conn, dtype=np.int64)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    offs = rng.normal(0, 1e-3, size=(400, 3))
    return verts[conn[:n, 0]] + offs[:n], None


def _digest(interp, pts):
    import hashlib
    dig = hashlib.blake2b(digest_size=8)
    found = 0
    for p in pts:
        ids, w = interp.locate(p)
        if ids is None:
            dig.update(b"none")
            continue
        found += 1
        dig.update(np.asarray(ids, dtype=np.int64).tobytes())
        dig.update(np.round(np.asarray(w, dtype=np.float64), 9).tobytes())
    return dig.hexdigest(), found


# ---------------------------------------------------------------------------
# locate: same answers as the full scan, at a fraction of the cost
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not FLD.exists(), reason="ex2_e_67.fld not present")
def test_r128_locate_reproduces_the_recorded_full_scan_results():
    """The indexed lookup must return exactly what the full scan returned."""
    from fv.model.dataset import load_file
    from fv.render.streamline import FldCellInterpolator
    ff = load_file(str(FLD))
    interp = FldCellInterpolator(ff)
    pts, _ = _query_points(ff)
    digest, found = _digest(interp, pts)
    assert digest == LOCATE_DIGEST
    assert found == 174          # recorded with the full-scan implementation
    assert ff.n_cells == 409188


@pytest.mark.skipif(not FLD.exists(), reason="ex2_e_67.fld not present")
def test_r128_locate_weights_reproduce_the_query_point():
    """An independent geometric check: sum(N_i V_i) must equal the point."""
    from fv.model.dataset import load_file
    from fv.render.streamline import FldCellInterpolator
    ff = load_file(str(FLD))
    interp = FldCellInterpolator(ff)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    pts, _ = _query_points(ff, n=120)
    inside = 0
    worst = 0.0
    for p in pts:
        ids, w = interp.locate(p)
        if ids is None:
            continue
        inside += 1
        x = (verts[ids] * w[:, None]).sum(axis=0)
        worst = max(worst, float(np.abs(x - p).max()))
        # the returned weights are trilinear shape functions: they sum to one
        assert abs(float(np.sum(w)) - 1.0) < 1e-9
    assert inside >= 30          # 33 of these 120 points land inside a hex
    assert worst < 1e-6


@pytest.mark.skipif(not FLD.exists(), reason="ex2_e_67.fld not present")
def test_r128_locate_only_visits_nearby_cells():
    """The point of the index: a handful of candidates, not every cell."""
    from fv.model.dataset import load_file
    from fv.render.streamline import FldCellInterpolator
    ff = load_file(str(FLD))
    interp = FldCellInterpolator(ff)
    assert interp._tree is not None
    assert interp._radius > 0.0
    pts, _ = _query_points(ff, n=40)
    worst = 0
    for p in pts:
        worst = max(worst, len(interp._tree.query_ball_point(p, interp._radius)))
    assert worst < ff.n_cells                    # far fewer than a full scan
    assert worst <= 256                          # measured 204 for these points


@pytest.mark.skipif(not FLD.exists(), reason="ex2_e_67.fld not present")
def test_r128_locate_returns_nothing_far_outside_the_mesh():
    from fv.model.dataset import load_file
    from fv.render.streamline import FldCellInterpolator
    ff = load_file(str(FLD))
    interp = FldCellInterpolator(ff)
    lo = np.asarray(ff.vertices, dtype=np.float64).min(axis=0)
    hi = np.asarray(ff.vertices, dtype=np.float64).max(axis=0)
    far = hi + 10.0 * (hi - lo + 1.0)
    assert interp.locate(far) == (None, None)
    # the point really is far outside the mesh it was told to search
    assert float(np.linalg.norm(far - lo)) > 10.0
    assert ff.n_cells == 409188


# ---------------------------------------------------------------------------
# cell centres: same numbers as the loop, one pass over the face table
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not CGNS.exists(), reason="tr03_9_orig.cgns not present")
def test_r128_cell_centres_match_the_per_cell_loop():
    from fv.model.dataset import load_file
    from fv.model.varreg import _cell_centers_fph
    ff = load_file(str(CGNS))
    assert ff.n_cells == 63697
    assert getattr(ff, "element_centers", None) is None   # the loop path runs
    got = _cell_centers_fph(ff)

    ld = ff.link_data
    fn = np.asarray(ld["face_nodes"], dtype=np.int64)
    fo = np.asarray(ld["face_offsets"], dtype=np.int64)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    ref = np.zeros((ff.n_cells, 3))
    for c, pf in ld["cell_owner_faces"].items():
        pts = []
        for fi in pf:
            pts.extend(fn[int(fo[fi]):int(fo[fi + 1])].tolist())
        if pts and 0 <= c < ff.n_cells:
            ref[c] = verts[pts].mean(axis=0)

    assert float(np.abs(got - ref).max()) < 1e-12
    # recorded checksum of the same quantity from the pre-R128 loop
    assert abs(float(got.sum()) - CENTRE_CHECKSUM) < 1e-3
    assert got.shape == (63697, 3)


@pytest.mark.skipif(not CGNS.exists(), reason="tr03_9_orig.cgns not present")
def test_r128_cell_centres_peak_memory_stays_bounded():
    """The vectorised path trades a little peak RAM for the speed-up.

    Measured on this mesh: 1.5 MB peak for the old per-cell loop (22.77 s)
    against about 42 MB for the one-pass version (4.4 s).  The bound below is
    what keeps a future change from materialising a per-node array instead.
    """
    from fv.model.dataset import load_file
    from fv.model.varreg import _cell_centers_fph
    ff = load_file(str(CGNS))
    tracemalloc.start()
    _cell_centers_fph(ff)
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 256 * 1024 * 1024
    assert peak > 0
