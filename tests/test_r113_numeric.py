"""R113: numerical correctness goldens for the quantities that were wrong."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"
FLD = r"D:\training\cgns\examples\ex1_100.fld"


def test_spectrum_recovers_the_amplitude_and_the_frequency():
    """A sine of amplitude A must come back as A, on the right frequency."""
    from fv.spectrum import analyze_series

    n, dt, amp = 400, 0.01, 3.0
    freq = 7.0                      # bin-aligned: df = 0.25 Hz
    t = np.arange(n) * dt
    x = amp * np.sin(2 * np.pi * freq * t)
    d = analyze_series(t, x)
    assert d["dt"] == pytest.approx(dt)
    assert d["dominant_freq"] == pytest.approx(freq, rel=1e-9)
    assert d["dominant_amplitude"] == pytest.approx(amp, rel=1e-9)
    # sum(power) == var * n/2; the density form satisfies Parseval exactly:
    # sum(density) * df == variance, which is what makes levels comparable
    # across record lengths.  psd stays an alias of power for the mode /
    # energy-share consumers, which only use ratios.
    assert d["total_power"] == pytest.approx(np.var(x) * n / 2, rel=1e-6)
    assert (np.asarray(d["density"]).sum() * d["df"]) == pytest.approx(
        np.var(x), rel=1e-6)
    assert np.asarray(d["psd"]) == pytest.approx(np.asarray(d["power"]))


def test_spectrum_amplitude_is_independent_of_record_length():
    """The density form is what makes levels comparable across records."""
    from fv.spectrum import analyze_series

    for n in (256, 512, 1024):
        dt, amp = 0.01, 2.5
        df = 1.0 / (n * dt)
        freq = round(9.0 / df) * df   # bin-aligned for every record length
        t = np.arange(n) * dt
        d = analyze_series(t, amp * np.sin(2 * np.pi * freq * t))
        assert d["dominant_freq"] == pytest.approx(freq, rel=1e-9), n
        assert d["dominant_amplitude"] == pytest.approx(amp, rel=1e-9), n


def test_coherence_refuses_to_conclude_from_one_segment():
    """One segment divides the cross-spectrum by its own magnitude."""
    from fv.relate import coherence

    rng = np.random.default_rng(0)
    for n in (50, 100, 256):
        c = coherence(rng.normal(size=n), rng.normal(size=n))
        assert c["nseg"] == 1
        assert np.isnan(c["mean_coherence"])
        assert np.isnan(c["peak_coherence"])
        assert "at least 2 segments" in c["reason"]
    # two independent signals with enough segments are NOT coherent
    c = coherence(rng.normal(size=1024), rng.normal(size=1024))
    assert c["nseg"] >= 2
    assert c["mean_coherence"] < 0.5


def test_cross_correlation_lag_sign_matches_the_docstring():
    """Positive lag must mean x leads y (y[n] == x[n - lag])."""
    from fv.relate import cross_correlate

    rng = np.random.default_rng(3)
    n = 400
    a = rng.normal(size=n)
    for lead in (0, 7, 25):
        y = np.concatenate([np.zeros(lead), a[: n - lead]])
        res = cross_correlate(a, y)
        assert res["best_lag"] == lead
        assert res["best_rho"] > 0.9


def test_cross_correlation_picks_the_smallest_of_tied_peaks():
    """A periodic signal ties at every period multiple; report lag 0."""
    from fv.relate import cross_correlate

    x = np.sin(np.linspace(0, 4 * np.pi, 100))
    assert cross_correlate(x, x)["best_lag"] == 0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_fph_cell_volume_uses_the_closed_shell():
    """Owner-faces-only integration gave a median of 0.424x the truth."""
    from fv.model import dataset
    from fv.model import topology as T

    ff = dataset.load_file(FPH)
    ld = ff.link_data
    verts = np.asarray(ff.vertices, dtype=float)
    fn = np.asarray(ld["face_nodes"], dtype=np.int64)
    off = np.asarray(ld["face_offsets"], dtype=np.int64)

    def reference(c):
        faces = list(ld["cell_owner_faces"].get(c, []))
        faces += list(ld["cell_neighbour_faces"].get(c, []))
        polys = [verts[fn[off[f]: off[f + 1]]] for f in faces]
        if not polys:
            return 0.0
        ctr = np.vstack(polys).mean(axis=0)
        vol = 0.0
        for p in polys:
            for i in range(1, len(p) - 1):
                tri = p[[0, i, i + 1]]
                m = np.stack([tri[1] - tri[0], tri[2] - tri[0], ctr - tri[0]])
                vol += abs(float(np.linalg.det(m))) / 6.0
        return vol

    n = ff.n_cells
    sample = np.arange(0, n, max(1, n // 120))[:120]
    for c in sample:
        assert T.volume_of_element(ff, int(c)) == pytest.approx(
            reference(int(c)), rel=1e-9)
    # the closed shell also means every interior cell reports all its faces
    c0 = int(np.argmax([len(ld["cell_neighbour_faces"].get(i, []))
                        for i in range(min(n, 500))]))
    assert T.face_count_of_element(ff, c0) >= 4


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_dst_measures_to_the_wall_surface():
    """Vertex-cloud distance over-estimated by a median of +47.7%."""
    from fv.model import dataset, varreg
    from fv.model.wallgeom import implicit_distance

    ff = dataset.load_file(FPH)
    centers = varreg._cell_centers_fph(ff)
    truth = implicit_distance(ff, None, centers)
    assert truth is not None and np.isfinite(truth).all()

    vi = varreg.register_dst(ff, "DST")
    assert vi.location == "cell"
    assert np.allclose(vi.array, truth, atol=1e-12)


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_dst_works_on_fld():
    """FLD keeps its boundaries in bc_plan; this used to raise."""
    from fv.model import dataset, varreg

    ff = dataset.load_file(FLD)
    vi = varreg.register_dst(ff, "DST")
    assert vi.location == "node"
    assert vi.array.size == ff.n_vertices
    assert np.isfinite(vi.array).all()
    assert vi.array.min() >= 0.0
