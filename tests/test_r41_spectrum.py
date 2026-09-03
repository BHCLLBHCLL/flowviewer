"""R41 tests: frequency / power-spectrum analysis of time series.

Pure NumPy (numpy.fft), headless, no CGNS/vtk dependencies.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.spectrum import (
    analyze_series,
    mean_dt,
    spectrum_from_trace,
    write_spectrum,
)

# ── sampling interval ──────────────────────────────────────────────────────

def test_mean_dt_uniform_spacing():
    assert mean_dt([1, 2, 3, 4]) == pytest.approx(1.0)
    assert mean_dt([0.0, 0.1, 0.2, 0.3]) == pytest.approx(0.1)


def test_mean_dt_tolerates_gaps_and_singletons():
    # gap at 2 missing; median of [2,1,2] = 2 ...  let's use 0,1,4,5,6
    assert mean_dt([0.0, 1.0, 4.0, 5.0, 6.0]) == pytest.approx(1.0)
    assert mean_dt([7.0]) == 0.0


# ── core FFT analysis ──────────────────────────────────────────────────────

def test_analyze_series_recovers_dominant_sine_frequency():
    fs = 20.0          # 20 samples per second
    dt = 1.0 / fs
    f_true = 2.0
    t = np.arange(0.0, 8.0, dt)
    y = 3.0 * np.sin(2 * np.pi * f_true * t) + 5.0   # + DC offset
    res = analyze_series(t, y)
    assert res["n"] == len(t)
    assert res["nyquist"] == pytest.approx(fs / 2)
    # DC removed so a strong peak sits at the true frequency
    assert res["dominant_freq"] == pytest.approx(f_true, abs=0.2)
    # peak PSD is well above the DC energy floor
    assert res["dominant_psd"] > res["dc_energy"]


def test_analyze_series_constant_series_no_oscillation():
    res = analyze_series([0, 1, 2, 3, 4, 5], [7.0] * 6)
    assert res["n"] == 6
    assert res["std"] == 0.0
    assert res["dominant_freq"] == 0.0
    assert res["dominant_psd"] == 0.0


def test_analyze_series_insufficient_points_is_nan():
    res = analyze_series([0.0, 1.0], [1.0, 2.0])  # way too short (n<2 after) -> actually n=2 ok
    if res["n"] >= 2:                            # n=2 is analyzable
        assert res["n"] == 2
    res1 = analyze_series([0.0], [1.0])          # single point -> empty
    assert res1["n"] == 0
    assert np.isnan(res1["dominant_freq"])


def test_analyze_series_ignores_nan_values():
    # NaN in the middle does not corrupt the dominant frequency
    fs = 20.0
    dt = 1.0 / fs
    t = np.arange(0.0, 8.0, dt)
    y = 3.0 * np.sin(2 * np.pi * 2.0 * t)
    y[10] = np.nan
    res = analyze_series(t, y)
    assert res["n"] == len(t) - 1
    assert res["dominant_freq"] == pytest.approx(2.0, abs=0.2)


def test_analyze_series_length_mismatch_raises():
    with pytest.raises(ValueError):
        analyze_series([1.0, 2.0], [1.0])


# ── trace-artifact runner ──────────────────────────────────────────────────

def test_spectrum_from_trace_reads_probe_series():
    art = {
        "name": "P",
        "cycles": list(np.arange(0.0, 4.0, 0.1)),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0,
             "values": list(3.0 * np.sin(2 * np.pi * 1.0 *
                            np.arange(0.0, 4.0, 0.1)))},
            {"query": (1.0, 0.0, 0.0), "node": 1,
             "values": [0.0] * 40},
        ],
    }
    r0 = spectrum_from_trace(art, 0)
    assert r0["probe"] == 0 and r0["node"] == 0
    assert r0["dominant_freq"] == pytest.approx(1.0, abs=0.2)
    r1 = spectrum_from_trace(art, 1)   # constant -> 0
    assert r1["node"] == 1
    assert r1["dominant_freq"] == 0.0


def test_spectrum_from_trace_empty_probes():
    r = spectrum_from_trace({"cycles": [1, 2], "probes": []}, 0)
    assert r["n"] == 0
    assert r["query"] is None


# ── I/O ────────────────────────────────────────────────────────────────────

def test_write_spectrum_emits_psd_csv_and_summary(tmp_path):
    t = np.arange(0.0, 2.0, 0.05)
    res = analyze_series(t, np.sin(2 * np.pi * 4.0 * t))
    summary = write_spectrum("P", [res, res], str(tmp_path))
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "P__probe0.csv").exists()
    assert (tmp_path / "P__probe1.csv").exists()
    assert summary["probes"][0]["dominant_freq"] == pytest.approx(4.0, abs=0.5)
    with open(tmp_path / "summary.json", "r", encoding="utf-8") as fh:
        json.load(fh)   # valid json


def test_write_spectrum_sanitises_weird_field_names(tmp_path):
    res = analyze_series([0.0, 1.0, 2.0], [1.0, 2.0, 3.0])
    summary = write_spectrum("pres sure", [res], str(tmp_path))
    assert (tmp_path / "pres_sure__probe0.csv").exists()
    assert summary["field"] == "pres sure"
