"""R44 tests: spectral mode detection over a power spectrum.

Pure NumPy + the R41 spectrum module; headless, no CGNS/vtk.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.modes import (
    energy_shares,
    modes_from_spectrum,
    spectral_peaks,
    turbulent_intensity,
    write_modes,
)
from fv.spectrum import analyze_series

# fixture spectra -----------------------------------------------------------

def _harmonic_spectrum():
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)            # n = 400
    # fundamental 2.0 amplitude, first harmonic 1.0 amplitude -> energy 4:1
    y = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t) + np.sin(2 * np.pi * 3.0 * t)
    res = analyze_series(t, y)
    return res


def test_spectral_peaks_finds_and_sorts_harmonics():
    res = _harmonic_spectrum()
    peaks = spectral_peaks(res["freq"], res["psd"])
    freqs = sorted(p["freq"] for p in peaks)
    assert len(peaks) == 2
    assert freqs[0] == pytest.approx(1.0, abs=0.1)
    assert freqs[1] == pytest.approx(3.0, abs=0.1)
    # sorted by energy: fundamental first
    assert peaks[0]["freq"] == pytest.approx(1.0, abs=0.1)


def test_spectral_peaks_prominence_threshold_filters_weak_modes():
    res = _harmonic_spectrum()
    strong = spectral_peaks(res["freq"], res["psd"], prominence_frac=0.05)
    # a very strict floor keeps only the dominant mode
    strict = spectral_peaks(res["freq"], res["psd"], prominence_frac=0.9)
    assert len(strong) == 2
    assert len(strict) == 1


def test_spectral_peaks_degrades_gracefully():
    assert spectral_peaks([], []) == []
    assert spectral_peaks([1.0, 2.0, 3.0], [0.0, 0.0, 0.0]) == []  # zero energy
    with pytest.raises(ValueError):
        spectral_peaks([1.0, 2.0], [1.0])       # unequal lengths


def test_energy_shares_split_by_amplitude_squared():
    res = _harmonic_spectrum()
    es = energy_shares(res["freq"], res["psd"])
    assert es["n_peaks"] == 2
    # energy ∝ amplitude²: 2.0² : 1.0² = 4 : 1  -> 0.8 / 0.2
    assert es["peaks"][0]["share"] == pytest.approx(0.8, abs=0.1)
    assert es["peaks"][1]["share"] == pytest.approx(0.2, abs=0.1)
    assert es["top_k"][-1]["cumulative_share"] == pytest.approx(1.0, abs=0.1)


def test_turbulent_intensity_of_oscillating_signal():
    # mean + sine(std = A/sqrt(2)); ti = std/mean
    t = np.arange(0.0, 10.0, 0.05)
    y = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    ti = turbulent_intensity(y)
    assert ti["n"] == len(t)
    assert ti["mean"] == pytest.approx(1.0, abs=0.05)
    assert ti["std"] == pytest.approx(2.0 / np.sqrt(2), rel=0.05)
    assert ti["ti_pct"] == pytest.approx(2.0 / np.sqrt(2) * 100, rel=0.05)


def test_turbulent_intensity_degenerate():
    assert np.isnan(turbulent_intensity([1.0])["ti_pct"])


# ── spectrum-artifact runner ───────────────────────────────────────────────

def test_modes_from_spectrum_reports_dominant_and_count():
    res = _harmonic_spectrum()
    m = modes_from_spectrum(res)
    assert m["n"] == 400
    assert m["organized"]["n_peaks"] == 2
    assert m["dominant"]["freq"] == pytest.approx(1.0, abs=0.1)


# ── I/O ────────────────────────────────────────────────────────────────────

def test_write_modes_emits_json_and_summary(tmp_path):
    res = _harmonic_spectrum()
    m = modes_from_spectrum(res)
    summary = write_modes("P", m, str(tmp_path))
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "P_modes.json").exists()
    assert summary["field"] == "P"
    assert summary["n_peaks"] == 2
    with open(tmp_path / "P_modes.json", "r", encoding="utf-8") as fh:
        json.load(fh)                        # valid json


def test_write_modes_sanitises_weird_names(tmp_path):
    res = _harmonic_spectrum()
    m = modes_from_spectrum(res)
    summary = write_modes("pres sure", m, str(tmp_path))
    assert (tmp_path / "pres_sure_modes.json").exists()
    assert summary["field"] == "pres sure"
