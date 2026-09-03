"""R47 tests: cross-probe correlation matrix + probe clustering.

Pure NumPy, headless, no CGNS/vtk dependencies; consumes R38 trace artifacts.
"""

from __future__ import annotations

import csv
import json

import numpy as np
from fv.probecorr import (
    cluster_probes,
    history_matrix,
    pairwise_correlation,
    probe_corr_summary,
    top_pairs,
    write_probecorr,
)


def _trace(n=4):
    """n probes: 0&1 in-phase sine, 2 anti-phase, 3 flat."""
    t = np.arange(0.0, 20.0, 0.05)
    v = 2.0 * np.sin(2 * np.pi * 1.0 * t)
    probes = [
        {"query": (0.0, 0.0, 0.0), "node": 0, "values": list(v)},
        {"query": (1.0, 0.0, 0.0), "node": 1,
         "values": list(v + 0.5 * np.sin(2 * np.pi * 1.0 * t + 0.1))},
        {"query": (2.0, 0.0, 0.0), "node": 2, "values": list(-v)},
        {"query": (3.0, 0.0, 0.0), "node": 3,
         "values": list(np.full_like(t, 7.0))},
    ][:n]
    return {"name": "P", "cycles": list(t), "probes": probes}


def test_history_matrix_builds_cycles_by_probes():
    art = _trace()
    M, cycles = history_matrix(art)
    assert M.shape == (400, 4)
    assert len(cycles) == 400
    assert M[0, 0] == M[0, 0]  # finite


def test_pairwise_correlation_inphase_antiphase_flat():
    M, _ = history_matrix(_trace())
    corr = pairwise_correlation(M)
    assert corr[0, 1] > 0.99            # in-phase
    assert corr[0, 2] < -0.99           # anti-phase
    assert abs(corr[0, 3]) < 0.05       # vs flat -> ~0


def test_pairwise_correlation_nan_gap_pairs():
    art = _trace()
    art["probes"][1]["values"][20:40] = [float("nan")] * 20
    M, _ = history_matrix(art)
    corr = pairwise_correlation(M)
    assert not np.isnan(corr[0, 1])     # still enough common samples
    assert corr[0, 1] > 0.99


def test_pairwise_correlation_too_few_samples_is_nan():
    art = _trace()
    art["probes"][0]["values"] = [1.0, 2.0]
    art["probes"][1]["values"] = [3.0, 4.0]
    M, _ = history_matrix(art)
    corr = pairwise_correlation(M)
    assert not np.isnan(corr[0, 1])     # exactly 2 samples -> valid (±1)
    art2 = _trace()
    art2["probes"][0]["values"] = [1.0]
    M2, _ = history_matrix(art2)
    c2 = pairwise_correlation(M2)
    assert np.isnan(c2[0, 1])           # 1 common sample -> NaN


def test_top_pairs_lists_strongest_first():
    M, _ = history_matrix(_trace())
    corr = pairwise_correlation(M)
    pairs = top_pairs(corr, k=3)
    assert pairs and abs(pairs[0]["rho"]) >= abs(pairs[-1]["rho"])


def test_cluster_probes_groups_correlated():
    # single-linkage on |rho|: 0&1 (in-phase), 0&2 & 1&2 (anti-phase) all have
    # |rho|≈1, so they form one coherent cluster; flat probe 3 stays alone.
    M, _ = history_matrix(_trace())
    corr = pairwise_correlation(M)
    clusters = cluster_probes(corr, threshold=0.8)
    members = [sorted(c) for c in clusters]
    assert [0, 1, 2] in members
    assert [3] in members


def test_cluster_probes_threshold_controls_linkage():
    # dedicated fixture: probe 1 shifted by 0.5 rad -> rho≈cos(0.5)≈0.88
    t = np.arange(0.0, 20.0, 0.05)
    a = 2 * np.pi * 1.0 * t
    art = {"name": "T", "cycles": list(t), "probes": [
        {"values": list(np.sin(a))},
        {"values": list(np.sin(a + 0.5))},
        {"values": list(-np.sin(a))},
    ]}
    M, _ = history_matrix(art)
    corr = pairwise_correlation(M)
    strict = cluster_probes(corr, threshold=0.999)   # only |rho|≈1 links {0,2}
    loose = cluster_probes(corr, threshold=0.5)      # all linked
    strict_members = [sorted(c) for c in strict]
    loose_members = [sorted(c) for c in loose]
    assert [0, 2] in strict_members and [1] in strict_members
    assert [0, 1, 2] in loose_members


def test_probe_corr_summary_and_write(tmp_path):
    art = _trace()
    summary = probe_corr_summary(art, threshold=0.8, top=3)
    assert summary["n_probes"] == 4
    assert len(summary["matrix"]) == 4
    assert summary["coherent_groups"]
    top_summary = write_probecorr(summary, str(tmp_path))
    assert (tmp_path / "P_probecorr.json").exists()
    assert (tmp_path / "P_clusters.json").exists()
    assert (tmp_path / "P_pairs.csv").exists()
    assert (tmp_path / "summary.json").exists()
    with open(tmp_path / "P_probecorr.json", "r", encoding="utf-8") as fh:
        data = json.load(fh)            # valid json, NaN -> None
    assert data["matrix"][0][0] == 1.0
    with open(tmp_path / "P_pairs.csv", newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["i", "j", "rho"]
    assert top_summary["n_probes"] == 4


def test_write_probecorr_sanitises_weird_names(tmp_path):
    art = _trace()
    art["name"] = "pres sure"
    summary = probe_corr_summary(art)
    top_summary = write_probecorr(summary, str(tmp_path))
    assert (tmp_path / "pres_sure_probecorr.json").exists()
    assert top_summary["field"] == "pres sure"
