"""R49 tests: POD low-rank reconstruction + per-probe filtering.

Pure NumPy, headless, no CGNS/vtk dependencies; consumes R38 trace artifacts.
"""

from __future__ import annotations

import csv
import json

import numpy as np
from fv.pod import pod_decompose
from fv.podfilter import (
    filter_probe,
    modes_to_energy,
    pod_reconstruct,
    write_recon,
)


def _art(series_list, name="P"):
    t = np.arange(0.0, 20.0, 0.05)
    return {
        "name": name, "cycles": list(t),
        "probes": [{"node": i, "query": (float(i), 0.0, 0.0),
                    "values": list(v)} for i, v in enumerate(series_list)],
    }


def test_pod_reconstruct_exact_for_rank1():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), np.sin(a), -np.sin(a), -np.sin(a)])
    recon = pod_reconstruct(art, k=1)
    assert recon["k"] == 1
    assert abs(recon["captured_var"] - 1.0) < 1e-9
    assert recon["total_rmse"] < 1e-9


def test_pod_reconstruct_truncated_captures_part():
    t = np.arange(0.0, 20.0, 0.05)
    a1 = 2 * np.pi * 1.0 * t
    a3 = 2 * np.pi * 3.0 * t
    art = _art([2 * np.sin(a1), 2 * np.sin(a1), np.sin(a3), np.sin(a3)])
    r1 = pod_reconstruct(art, k=1)
    r2 = pod_reconstruct(art, k=2)
    assert r1["captured_var"] == r1["captured_var"]  # finite
    assert 0.7 < r1["captured_var"] < 0.9            # ~0.8
    assert abs(r2["captured_var"] - 1.0) < 1e-9
    assert r2["total_rmse"] < 1e-9
    assert all(v < 1e-9 for v in r2["per_probe_rmse"])


def test_modes_to_energy():
    t = np.arange(0.0, 20.0, 0.05)
    a1 = 2 * np.pi * 1.0 * t
    a3 = 2 * np.pi * 3.0 * t
    art = _art([2 * np.sin(a1), 2 * np.sin(a1), np.sin(a3), np.sin(a3)])
    pod = pod_decompose(art)
    assert modes_to_energy(pod, 0.5)["k"] == 1
    assert modes_to_energy(pod, 0.99)["k"] == 2
    assert modes_to_energy(pod, 1.000001)["k"] is None
    assert modes_to_energy(pod, 1.0)["k"] == 2


def test_filter_probe_denoises_sine_plus_noise():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    clean = np.sin(a)
    # independent noise per probe: the coherent (shared) mode is the clean sine,
    # the noise is incoherent across probes so it lands in the higher modes and
    # is dropped by the top-1 reconstruction.
    rng = np.random.default_rng(0)
    meas = [clean + 0.5 * rng.standard_normal(t.size) for _ in range(4)]
    art = _art(meas)
    filtered = filter_probe(art, 0, k=1)
    f = np.array(filtered)
    # filtered is much closer to the clean sine than the noisy input
    assert np.sqrt(np.mean((f - clean) ** 2)) < np.sqrt(
        np.mean((meas[0] - clean) ** 2))
    assert abs(np.mean(f)) < 0.05         # noise mostly removed


def test_filter_probe_restores_mean():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([10.0 + np.sin(a), np.sin(a), -np.sin(a), -np.sin(a)])
    filtered = filter_probe(art, 0, k=1)
    assert abs(np.mean(filtered) - 10.0) < 0.1   # DC offset preserved


def test_filter_probe_out_of_range():
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a)])
    assert filter_probe(art, 5, k=1) == []
    assert filter_probe(art, -1, k=1) == []


def test_write_recon_artifacts(tmp_path):
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a), np.sin(a), -np.sin(a), -np.sin(a)])
    top = write_recon(art, k=1, out_dir=str(tmp_path))
    assert (tmp_path / "P_recon.json").exists()
    assert (tmp_path / "P_rmse.csv").exists()
    assert (tmp_path / "summary.json").exists()
    with open(tmp_path / "P_recon.json", "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["k"] == 1 and data["n_probes"] == 4
    with open(tmp_path / "P_rmse.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["probe", "rmse", "captured_var"]
    assert len(rows) == 1 + 4
    assert top["k"] == 1


def test_write_recon_sanitises_weird_names(tmp_path):
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = _art([np.sin(a)], name="pres sure")
    top = write_recon(art, k=1, out_dir=str(tmp_path))
    assert (tmp_path / "pres_sure_recon.json").exists()
    assert top["field"] == "pres sure"
