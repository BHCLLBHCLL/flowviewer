"""R42 tests: relating two monitoring time series (cross-correlation + coherence).

Pure NumPy, headless, no CGNS/vtk dependencies.
"""

from __future__ import annotations

import numpy as np
import pytest
from fv.relate import (
    coherence,
    cross_correlate,
    relate_probes,
    write_relate,
)

# ── cross-correlation ──────────────────────────────────────────────────────

def test_cross_correlate_recovers_delay_in_samples():
    t = np.arange(0.0, 10.0, 0.05)
    x = np.sin(2 * np.pi * 1.0 * t)
    tau = 8                            # shift y by +8 samples relative to x
    y = np.concatenate([np.zeros(tau), x[:-tau]])
    res = cross_correlate(x, y, max_lag=40)
    assert res["n"] == len(t)
    # y is a delayed copy of x -> strong correlation at |best_lag| == tau
    assert abs(res["best_lag"]) == tau
    assert res["best_rho"] > 0.9


def test_cross_correlate_identical_series_zero_lag():
    x = np.sin(np.linspace(0, 4 * np.pi, 100))
    res = cross_correlate(x, x, max_lag=None)
    assert res["best_lag"] == 0
    assert res["best_rho"] == pytest.approx(1.0)


def test_cross_correlate_max_lag_restricts_window():
    x = np.sin(np.linspace(0, 8 * np.pi, 200))
    res = cross_correlate(x, x, max_lag=5)
    assert max(abs(lag) for lag in res["lags"]) == 5


def test_cross_correlate_length_mismatch_raises_and_degenerate():
    with pytest.raises(ValueError):
        cross_correlate([1.0, 2.0], [1.0])
    res = cross_correlate([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])  # constant -> nan
    assert np.isnan(res["best_rho"])


# ── coherence ──────────────────────────────────────────────────────────────

def test_coherence_same_frequency_is_high_at_peak():
    fs = 50.0
    dt = 1.0 / fs
    t = np.arange(0.0, 8.0, dt)
    f_shared = 3.0
    x = np.sin(2 * np.pi * f_shared * t) + 0.5 * np.sin(2 * np.pi * 9.0 * t)
    y = 0.8 * np.sin(2 * np.pi * f_shared * t)       # shares only 3.0 Hz
    res = coherence(x, y, nperseg=64, dt=dt)
    assert res["nseg"] >= 3          # enough segments to be meaningful
    assert res["peak_freq"] == pytest.approx(f_shared, abs=0.5)
    assert res["peak_coherence"] > 0.8
    assert res["mean_coherence"] < res["peak_coherence"]


def test_coherence_disjoint_frequencies_is_low():
    fs = 50.0
    dt = 1.0 / fs
    t = np.arange(0.0, 8.0, dt)
    x = np.sin(2 * np.pi * 2.0 * t)
    y = np.sin(2 * np.pi * 7.0 * t)
    res = coherence(x, y, nperseg=64, dt=dt)
    assert res["peak_coherence"] < 0.4


def test_coherence_too_short_is_nan():
    res = coherence([1.0], [2.0], nperseg=2, dt=0.1)
    assert res["nseg"] == 0
    assert np.isnan(res["peak_freq"])


# ── trace-artifact runner ──────────────────────────────────────────────────

def test_relate_probes_reads_two_probe_series():
    fs = 20.0
    dt = 1.0 / fs
    t = np.arange(0.0, 4.0, dt)
    art = {
        "name": "P", "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0,
             "values": list(np.sin(2 * np.pi * 1.0 * t))},
            {"query": (1.0, 0.0, 0.0), "node": 1,
             "values": list(0.8 * np.sin(2 * np.pi * 1.0 * t))},
        ],
    }
    r = relate_probes(art, 0, 1, nperseg=32)
    assert r["probe_x"] == 0 and r["probe_y"] == 1
    assert r["dt"] == pytest.approx(dt)      # from cycle axis
    assert r["cross_correlate"]["best_rho"] > 0.8
    assert r["coherence"]["peak_coherence"] > 0.8


def test_relate_probes_out_of_range_returns_error():
    art = {"cycles": [1, 2], "probes": [{"values": [1, 2]}]}
    r = relate_probes(art, 0, 5)
    assert "error" in r


# ── I/O ────────────────────────────────────────────────────────────────────

def test_write_relate_emits_pair_json_and_summary(tmp_path):
    t = np.arange(0.0, 4.0, 0.1)
    art = {
        "name": "P", "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0,
             "values": list(np.sin(2 * np.pi * 1.0 * t))},
            {"query": (1.0, 0.0, 0.0), "node": 1,
             "values": list(np.sin(2 * np.pi * 1.0 * t))},
        ],
    }
    res = relate_probes(art, 0, 1, nperseg=32)
    manifest = write_relate("P", [res], str(tmp_path))
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "P__probe0_vs_1.json").exists()
    assert manifest["pairs"][0]["best_rho"] > 0.8


def test_write_relate_sanitises_weird_field_names(tmp_path):
    t = np.arange(0.0, 2.0, 0.1)
    art = {"cycles": list(t),
           "probes": [{"values": list(np.sin(t))}, {"values": list(np.sin(t))}]}
    res = relate_probes(art, 0, 1, nperseg=16)
    manifest = write_relate("pres sure", [res], str(tmp_path))
    assert (tmp_path / "pres_sure__probe0_vs_1.json").exists()
    assert manifest["field"] == "pres sure"
