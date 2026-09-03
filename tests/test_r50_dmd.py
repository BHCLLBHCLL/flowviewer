"""R50 tests: Dynamic Mode Decomposition of monitoring-point data.

Pure NumPy, headless, no CGNS/vtk dependencies; consumes R38 trace artifacts.
"""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest
from fv.dmd import dmd_decompose, write_dmd


def _art(series_list, name="P"):
    t = np.arange(0.0, 20.0, 0.05)
    return {
        "name": name, "cycles": list(t),
        "probes": [{"node": i, "query": (float(i), 0.0, 0.0),
                    "values": list(v)} for i, v in enumerate(series_list)],
    }


def test_dmd_recovers_single_frequency():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a)] * 4)            # embedded rank 2 -> conjugate pair
    d = dmd_decompose(art)
    assert d["r"] == 2 and len(d["modes"]) == 2
    assert d["dominant"]["freq"] == pytest.approx(1.0, abs=1e-3)
    assert abs(d["dominant"]["growth"]) < 1e-3


def test_dmd_two_frequencies_ranking():
    t = np.arange(0.0, 20.0, 0.05)
    a1 = 2 * np.pi * 1.0 * t
    a3 = 2 * np.pi * 3.0 * t
    art = _art([2 * np.sin(a1), 2 * np.sin(a1), np.sin(a3), np.sin(a3)])
    d = dmd_decompose(art)
    freqs = sorted(round(m["freq"], 6) for m in d["modes"])
    assert freqs == pytest.approx([1.0, 1.0, 3.0, 3.0], abs=1e-3)
    assert d["dominant"]["freq"] == pytest.approx(1.0, abs=1e-3)  # amp-2 wins
    es = [m["energy"] for m in d["modes"]]
    assert es == sorted(es, reverse=True)


def test_dmd_cross_checks_r41():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a)] * 4)
    d = dmd_decompose(art)
    from fv.spectrum import analyze_series
    spec = analyze_series(list(t), list(np.sin(a)))
    assert abs(d["dominant"]["freq"] - spec["dominant_freq"]) < 1e-3


def test_dmd_dc_mode_excluded_from_dominant():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([10.0 + np.sin(a), 10.0 + np.sin(a),
                5.0 + np.zeros_like(t), 5.0 + np.zeros_like(t)])
    d = dmd_decompose(art)
    assert any(m["freq"] < 1e-9 for m in d["modes"])   # static mode present
    assert d["dominant"]["freq"] == pytest.approx(1.0, abs=1e-3)


def test_dmd_r_cap():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a)] * 4)
    d = dmd_decompose(art, r=1)            # truncate the conjugate pair to one
    assert d["r"] == 1 and len(d["modes"]) == 1


def test_dmd_degenerate():
    empty = dmd_decompose({"probes": []})
    assert empty["r"] == 0 and empty["modes"] == []
    short = dmd_decompose({"name": "P", "cycles": [0.0, 0.05, 0.1],
                           "probes": [{"values": [1.0, 2.0, 3.0]},
                                      {"values": [1.0, 2.0, 3.0]}]})
    assert short["r"] == 0 and short["modes"] == []


def test_dmd_probe_participation_complex():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), np.sin(a), np.zeros_like(t), np.zeros_like(t)])
    d = dmd_decompose(art)
    assert d["dominant"]["freq"] == pytest.approx(1.0, abs=1e-3)
    # dominant mode lives on probes {0,1}; flat probes barely participate
    mags = d["modes"][0]["mode_mag"][:4]
    assert mags[0] > 1e-3 and mags[1] > 1e-3
    assert mags[2] < 1e-6 and mags[3] < 1e-6


def test_write_dmd_artifacts(tmp_path):
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a)] * 4)
    summary = dmd_decompose(art)
    top = write_dmd(summary, str(tmp_path))
    assert (tmp_path / "P_dmd.json").exists()
    assert (tmp_path / "P_modes.csv").exists()
    assert (tmp_path / "summary.json").exists()
    with open(tmp_path / "P_dmd.json", "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["n_probes"] == 4 and data["r"] == 2
    assert len(data["modes"][0]["mode"][0]) == 2   # [re, im] pairs, JSON-safe
    with open(tmp_path / "P_modes.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["i", "freq", "growth", "amplitude", "share"]
    assert len(rows) == 1 + 2
    assert top["dominant_freq"] == pytest.approx(1.0, abs=1e-3)


def test_write_dmd_sanitises_weird_names(tmp_path):
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a)], name="pres sure")
    summary = dmd_decompose(art)
    top = write_dmd(summary, str(tmp_path))
    assert (tmp_path / "pres_sure_dmd.json").exists()
    assert top["field"] == "pres sure"
