"""R45 tests: one-command per-probe monitoring analysis bundle.

Pure NumPy, headless, no CGNS/vtk dependencies; reuses R41/R43/R44 modules.
"""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest
from fv.monitor import (
    analyze_monitor,
    analyze_probe,
    write_monitor,
)


def _trace_artifact():
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)
    # probe 0: mean + clean 1 Hz oscillation (amplitude 2)
    v0 = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    # probe 1: constant
    v1 = 5.0 + np.zeros_like(t)
    return {
        "name": "P", "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "values": list(v0)},
            {"query": (1.0, 0.0, 0.0), "node": 1, "values": list(v1)},
        ],
    }


def test_analyze_probe_fuses_all_spectral_cards():
    art = _trace_artifact()
    c = analyze_probe(art, 0)
    assert c["probe"] == 0 and c["node"] == 0
    assert float(c["spectrum"]["dominant_freq"] or 0) == pytest.approx(1.0)
    assert c["spectrum"]["nyquist"] > 0
    assert c["trend"]["nw"] > 0
    assert c["modes"]["n_peaks"] >= 1
    assert c["intensity"]["ti_pct"] > 0


def test_analyze_probe_constant_series_known_intensity():
    art = _trace_artifact()
    c = analyze_probe(art, 1)
    assert c["intensity"]["ti_pct"] == 0.0           # constant -> no fluctuation


def test_analyze_probe_empty_probes():
    c = analyze_probe({"cycles": [1, 2], "probes": []}, 0)
    assert c["probe"] == 0 and c["spectrum"] == {}


def test_analyze_monitor_builds_all_probes():
    art = _trace_artifact()
    b = analyze_monitor(art)
    assert b["n_probes"] == 2
    assert len(b["probes"]) == 2
    assert b["probes"][0]["probe"] == 0 and b["probes"][1]["probe"] == 1


def test_write_monitor_emits_csv_and_bundle_and_summary(tmp_path):
    art = _trace_artifact()
    b = analyze_monitor(art)
    summary = write_monitor(b, str(tmp_path))
    csv_path = tmp_path / "P_monitor.csv"
    bundle_path = tmp_path / "P_monitor.json"
    assert csv_path.exists() and bundle_path.exists()
    assert (tmp_path / "summary.json").exists()
    # CSV has header + two probe rows
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) == 3
    assert rows[0][0] == "probe"
    with open(bundle_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["n_probes"] == 2
    assert summary["n_probes"] == 2


def test_write_monitor_sanitises_weird_field_names(tmp_path):
    art = _trace_artifact()
    art["name"] = "pres sure"
    b = analyze_monitor(art)
    summary = write_monitor(b, str(tmp_path))
    assert (tmp_path / "pres_sure_monitor.csv").exists()
    assert summary["field"] == "pres sure"
