"""R129 - analytic goldens for the analysis stack.

The audit that opened this round measured how many of the analysis tests carry
an independent expectation: 65 of 125 across the POD / DMD / spectral /
modal-field files.  These three cases pin the numeric behaviour of the kernels
against closed-form answers instead of shapes and round trips:

* POD of a rank-2 field with known amplitudes must return the analytic energy
  shares, the analytic modes and an exact rank-2 reconstruction;
* IDW must be exact at probe nodes and reproduce the analytic interpolant
  between them;
* the coherence peak must sit on the frequency the signal was built from.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fv.model.pod import pod_decompose  # noqa: E402


def _analytic_rank_two(n_fields=40, n_samples=60, amp_a=1.0, amp_b=0.5):
    """X = a(t) phi1 + b(t) phi2 with orthonormal analytic modes."""
    t = np.linspace(0.0, 1.0, n_samples)
    a = amp_a * np.sin(2.0 * np.pi * t)
    b = amp_b * np.cos(4.0 * np.pi * t)
    i = np.arange(n_fields, dtype=np.float64)
    phi1 = np.cos(np.pi * i / n_fields)
    phi2 = np.sin(2.0 * np.pi * i / n_fields)
    phi1 /= np.linalg.norm(phi1)
    phi2 /= np.linalg.norm(phi2)
    phi2 -= phi1 * float(phi1 @ phi2)          # orthogonalise to machine eps
    phi2 /= np.linalg.norm(phi2)
    X = np.outer(a, phi1) + np.outer(b, phi2)
    return X, phi1, phi2, float(a.var()), float(b.var())


def test_r129_pod_energy_shares_and_modes_are_analytic():
    X, phi1, phi2, var_a, var_b = _analytic_rank_two()
    mean, modes, energies, _sv, tc = pod_decompose(X, 2)
    total = var_a + var_b
    assert abs(float(energies[0]) - var_a / total) < 1e-9
    assert abs(float(energies[1]) - var_b / total) < 1e-9
    # modes are recovered up to sign, in energy order
    assert abs(float(np.asarray(modes[0]) @ phi1)) > 1.0 - 1e-9
    assert abs(float(np.asarray(modes[1]) @ phi2)) > 1.0 - 1e-9
    # a rank-2 field is reproduced exactly by two modes
    rec = mean + tc @ np.asarray(modes)
    assert float(np.abs(rec - X).max()) < 1e-9


def test_r129_pod_mode_order_follows_the_amplitude():
    """Swap the amplitudes and the dominant mode must swap with them."""
    X, phi1, phi2, var_a, var_b = _analytic_rank_two(amp_a=0.2, amp_b=1.0)
    mean, modes, energies, _sv, tc = pod_decompose(X, 2)
    assert var_b > var_a
    assert abs(float(np.asarray(modes[0]) @ phi2)) > 1.0 - 1e-9
    assert abs(float(energies[0]) - var_b / (var_a + var_b)) < 1e-9
    assert float(np.abs(mean + tc @ np.asarray(modes) - X).max()) < 1e-9


def test_r129_idw_is_exact_at_probes_and_linear_between():
    from fv.modalfield import idw_field
    verts = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [1.0, 0.0, 0.0],
                      [2.0, 0.0, 0.0]])
    probes = [{"node": 0, "xyz": [0.0, 0.0, 0.0]},
              {"node": 2, "xyz": [1.0, 0.0, 0.0]}]
    field = idw_field(verts, probes, [0.0, 10.0], p=1.0, neighbors=2)
    assert abs(float(field[0]) - 0.0) < 1e-12        # exact at the probe node
    assert abs(float(field[2]) - 10.0) < 1e-12
    assert abs(float(field[1]) - 5.0) < 1e-9         # midpoint of p=1 IDW
    assert abs(float(field[3]) - 10.0 * 2.0 / 3.0) < 1e-9   # 1/(1+0.5) split
    assert np.isnan(idw_field(verts, [], [])).all()


def test_r129_coherence_peak_is_the_analytic_frequency():
    pytest.importorskip("scipy")
    from fv.coherencemap import coherence_field
    dt, f0 = 0.01, 5.0
    n = 256
    t = np.arange(n) * dt
    sig = np.sin(2.0 * np.pi * f0 * t)
    # vert_frames is (n_frames, n_vertices) and ref is (n_frames,)
    pure = np.tile(sig[:, None], (1, 3))
    # coherence is per-bin and scale invariant, so a different-frequency term
    # does not lower it at f0: the contaminated series needs broadband noise
    noise = np.random.default_rng(0).normal(0.0, 1.0, n)
    noisy = np.column_stack([sig, sig * 0.5, sig + noise])
    res = coherence_field(noisy, sig, nperseg=64, dt=dt)
    assert res["nseg"] >= 3 and res["nperseg"] == 64
    peak = np.asarray(res["peak_freq"], dtype=np.float64)
    coh = np.asarray(res["peak_coherence"], dtype=np.float64)
    resolution = 1.0 / (64 * dt)          # Welch bin width
    assert abs(float(peak[0]) - f0) <= resolution
    assert float(coh[0]) > 0.9            # the reference against itself
    # a rescaled copy keeps the peak (and unit coherence), the contaminated
    # series loses coherence at that frequency
    assert abs(float(peak[1]) - f0) <= resolution
    assert float(coh[0]) > 0.99
    # recorded with this seed and signal: broadband noise pulls the peak
    # coherence of that vertex down to 0.9147 (was 1.0 without it)
    assert abs(float(coh[2]) - 0.9147) < 0.005
    pure_res = coherence_field(pure, sig, nperseg=64, dt=dt)
    assert float(np.asarray(pure_res["peak_coherence"]).min()) > 0.9
