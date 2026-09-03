"""R43 tests: time-frequency spectrogram of a monitoring-point series.

Pure NumPy, headless, no CGNS/vtk dependencies.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.spectro import (
    freq_evolution,
    spectrogram,
    spectrogram_from_trace,
    write_spectrogram,
)

# ── spectrogram ────────────────────────────────────────────────────────────

def test_spectrogram_peak_frequency_tracks_constant_freq():
    dt = 0.1
    t = np.arange(0.0, 20.0, dt)
    x = np.sin(2 * np.pi * 1.0 * t)
    ss = spectrogram(x, nperseg=32, dt=dt)
    assert ss["n"] == len(t)
    assert ss["nw"] >= 8
    # dominant frequency stable near 1.0 across all windows
    assert np.allclose(ss["peak_freq"], 1.0, atol=1.0)
    assert ss["mean_peak_freq"] == pytest.approx(1.0, abs=1.0)


def test_spectrogram_tracks_frequency_step_up():
    dt = 0.1
    t = np.arange(0.0, 20.0, dt)
    n = len(t)
    half = n // 2
    x = np.sin(2 * np.pi * 1.0 * t)
    x[half:] = np.sin(2 * np.pi * 4.0 * t[half:])
    ss = spectrogram(x, nperseg=32, dt=dt)
    assert ss["peak_freq"][0] < 2.0                 # early windows -> low
    assert ss["peak_freq"][-1] > 3.0                # late windows  -> high
    assert freq_evolution(ss)["drift"] > 0.0        # drift upward


def test_spectrogram_fills_mid_series_nan():
    dt = 0.1
    t = np.arange(0.0, 20.0, dt)
    x = np.sin(2 * np.pi * 2.0 * t)
    x[40:60] = np.nan
    ss = spectrogram(x, nperseg=32, dt=dt)
    assert ss["mean_peak_freq"] == pytest.approx(2.0, abs=1.0)


def test_spectrogram_too_short_is_empty():
    ss = spectrogram([1.0], nperseg=8, dt=0.1)
    assert ss["nw"] == 0
    assert np.isnan(ss["mean_peak_freq"])


# ── frequency evolution summary ────────────────────────────────────────────

def test_freq_evolution_reports_drift():
    ss = {"peak_freq": [1.0, 1.0, 5.0, 5.0]}
    ev = freq_evolution(ss)
    assert ev["nw"] == 4
    assert ev["range"] == pytest.approx(4.0)
    assert ev["drift"] == pytest.approx(4.0)       # 5.0 - 1.0
    assert freq_evolution({})["nw"] == 0


# ── trace-artifact runner ──────────────────────────────────────────────────

def test_spectrogram_from_trace_reads_probe_and_infers_dt():
    dt = 0.1
    t = np.arange(0.0, 10.0, dt)
    art = {
        "name": "P", "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0,
             "values": list(np.sin(2 * np.pi * 1.0 * t))},
        ],
    }
    r = spectrogram_from_trace(art, 0, nperseg=32)
    assert r["probe"] == 0 and r["node"] == 0
    assert r["dt"] == pytest.approx(dt)            # from cycle axis
    assert r["mean_peak_freq"] == pytest.approx(1.0, abs=1.0)


def test_spectrogram_from_trace_empty_probes():
    r = spectrogram_from_trace({"cycles": [1, 2], "probes": []}, 0)
    assert r["n"] == 0
    assert r["query"] is None


# ── I/O ────────────────────────────────────────────────────────────────────

def test_write_spectrogram_emits_json_and_summary(tmp_path):
    dt = 0.1
    t = np.arange(0.0, 12.0, dt)
    r1 = spectrogram_from_trace({
        "name": "P", "cycles": list(t),
        "probes": [{"query": (0.0, 0.0, 0.0), "node": 0,
                    "values": list(np.sin(2 * np.pi * 1.0 * t))}],
    }, 0, nperseg=16)
    summary = write_spectrogram("P", [r1], str(tmp_path))
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "P__probe0_spectro.json").exists()
    assert summary["field"] == "P"
    with open(tmp_path / "P__probe0_spectro.json", "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert "S" in data and "peak_freq" in data and "evolution" in data


def test_write_spectrogram_sanitises_weird_names(tmp_path):
    t = np.arange(0.0, 3.0, 0.1)
    r = spectrogram_from_trace({
        "name": "pres sure", "cycles": list(t),
        "probes": [{"values": list(np.sin(2 * np.pi * 2.0 * t))}],
    }, 0, nperseg=16)
    summary = write_spectrogram("pres sure", [r], str(tmp_path))
    assert (tmp_path / "pres_sure__probe0_spectro.json").exists()
    assert summary["field"] == "pres sure"
