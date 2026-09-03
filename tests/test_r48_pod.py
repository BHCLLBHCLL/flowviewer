"""R48 tests: POD of monitoring-point data.

Pure NumPy, headless, no CGNS/vtk dependencies; consumes R38 trace artifacts.
"""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest
from fv.pod import (
    pod_decompose,
    pod_summary,
    snapshot_matrix,
    write_pod,
)


def _art(series_list, name="P"):
    t = np.arange(0.0, 20.0, 0.05)
    return {
        "name": name, "cycles": list(t),
        "probes": [{"node": i, "query": (float(i), 0.0, 0.0),
                    "values": list(v)} for i, v in enumerate(series_list)],
    }


def test_snapshot_matrix_is_probes_by_cycles_and_centered():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), 5.0 + np.zeros_like(t)])
    X, cycles = snapshot_matrix(art)
    assert X.shape == (2, 400)
    assert len(cycles) == 400
    assert abs(X[0].mean()) < 1e-10       # centered
    assert abs(X[1].mean()) < 1e-10       # constant row -> ~0 after centering


def test_pod_single_rank_antiphase_group():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), np.sin(a), -np.sin(a), -np.sin(a)])
    pod = pod_decompose(art)
    assert pod["n_probes"] == 4
    assert pod["n_modes"] == 1            # rank-1 data
    assert pod["energy_shares"][0] == 1.0
    m = np.array(pod["modes"][0])
    assert np.allclose(m[:2], m[0])       # in-phase probes share the weight
    assert np.allclose(m[2:], -m[0])      # anti-phase probes opposite sign
    assert np.isclose(np.linalg.norm(m), 1.0)


def test_pod_two_structures_energy_and_weights():
    t = np.arange(0.0, 20.0, 0.05)
    a1 = 2 * np.pi * 1.0 * t
    a3 = 2 * np.pi * 3.0 * t
    # amplitude 2 (f=1) vs amplitude 1 (f=3) -> energy 4:1, ordering fixed
    art = _art([2 * np.sin(a1), 2 * np.sin(a1), np.sin(a3), np.sin(a3)])
    pod = pod_decompose(art)
    assert pod["n_modes"] == 2
    assert pod["energy_shares"][0] > 0.7 and pod["energy_shares"][1] < 0.3
    m0 = np.array(pod["modes"][0])
    # mode 1 weights concentrate on the {0,1} pair
    assert np.isclose(m0[0], m0[1]) and np.isclose(m0[2], m0[3])
    assert abs(m0[0]) > abs(m0[2])


def test_pod_mode1_dominant_frequency():
    t = np.arange(0.0, 20.0, 0.05)
    a1 = 2 * np.pi * 1.0 * t
    a3 = 2 * np.pi * 3.0 * t
    art = _art([2 * np.sin(a1), 2 * np.sin(a1), np.sin(a3), np.sin(a3)])
    s = pod_summary(art)
    assert s["mode1_dominant_freq"] == s["mode1_dominant_freq"]  # not NaN
    assert float(s["mode1_dominant_freq"] or 0) == pytest.approx(1.0, abs=1e-9)


def test_pod_center_removes_flat_probes():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), np.sin(a), 5.0 + np.zeros_like(t),
                5.0 + np.zeros_like(t)])
    pod = pod_decompose(art)
    assert pod["n_modes"] == 1            # flats contribute nothing
    m = np.array(pod["modes"][0])
    assert np.allclose(m[2:], 0.0, atol=1e-9)


def test_pod_n_modes_cap_and_degenerate():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), np.sin(a), -np.sin(a), -np.sin(a)])
    pod = pod_decompose(art, n_modes=1)
    assert pod["n_modes"] == 1
    empty = pod_decompose({"probes": []})
    assert empty["n_modes"] == 0
    assert empty["modes"] == []


def test_write_pod_artifacts(tmp_path):
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), np.sin(a), -np.sin(a), -np.sin(a)])
    summary = pod_summary(art)
    top = write_pod(summary, str(tmp_path))
    assert (tmp_path / "P_pod.json").exists()
    assert (tmp_path / "P_modes.csv").exists()
    assert (tmp_path / "summary.json").exists()
    with open(tmp_path / "P_pod.json", "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["n_modes"] == 1
    with open(tmp_path / "P_modes.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["mode", "probe", "weight"]
    assert len(rows) == 1 + 4             # header + 4 probes of mode 0
    assert top["n_probes"] == 4


def test_write_pod_sanitises_weird_names(tmp_path):
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), np.sin(a)], name="pres sure")
    summary = pod_summary(art)
    top = write_pod(summary, str(tmp_path))
    assert (tmp_path / "pres_sure_pod.json").exists()
    assert top["field"] == "pres sure"
