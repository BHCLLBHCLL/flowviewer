"""R53 tests: full-field POD reconstruction at a cycle.

Pure NumPy, headless, no CGNS, no VTK. Reuses R48 pod_decompose and R52
idw_field on an R38 trace artifact.
"""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest
from fv.pod import pod_decompose
from fv.reconfield import (
    _read_verts,
    main,
    mean_field,
    recon_quality,
    reconstruct_field,
    write_reconfield,
)


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)
    v = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    v2 = 1.5 + np.sin(2 * np.pi * 1.0 * t + 0.5)
    return {
        "name": name, "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "xyz": (0.0, 0.0, 0.0),
             "values": list(v)},
            {"query": (2.0, 0.0, 0.0), "node": 2, "xyz": (2.0, 0.0, 0.0),
             "values": list(v2)},
            {"query": (0.0, 2.0, 0.0), "node": 6, "xyz": (0.0, 2.0, 0.0),
             "values": list(np.zeros_like(t))},
        ],
    }


def test_mean_field_at_probe_node_is_probe_mean():
    art = _art()
    mf = mean_field(_grid3(), art["probes"])
    for pr in art["probes"]:
        expected = float(np.mean(pr["values"]))
        assert abs(mf[pr["node"]] - expected) < 1e-9


def test_reconstruct_field_matches_manual_formula():
    art = _art()
    pod = pod_decompose(art)
    k = 2
    res = reconstruct_field(_grid3(), art, cycle=3, k=k)
    assert res["k"] == k
    assert res["n_cycles"] == len(art["cycles"])
    for j, pr in enumerate(art["probes"]):
        manual = float(np.mean(pr["values"])) + sum(
            pod["modes"][i][j] * pod["coeffs"][i][3] for i in range(k))
        assert abs(res["recon_field"][pr["node"]] - manual) < 1e-9
    # capturing energy grows with k
    assert res["captured_var"] > 0


def test_reconstruct_all_modes_recovers_probe_values():
    art = _art()
    res = reconstruct_field(_grid3(), art, cycle=7, k=None)
    for j, pr in enumerate(art["probes"]):
        assert abs(res["recon_field"][pr["node"]] - pr["values"][7]) < 1e-6


def test_recon_quality_improves_with_k():
    art = _art()
    q1 = recon_quality(art, k=1)
    qall = recon_quality(art, k=None)
    assert q1["captured_var"] > 0
    assert 0 <= q1["total_rmse"]
    # more modes -> no worse, and all modes recovers the values
    assert qall["k"] >= q1["k"]
    assert np.isnan(qall["total_rmse"]) or qall["total_rmse"] < 1e-6
    assert len(qall["per_probe_rmse"]) == qall["n_probes"]
    assert len(qall["per_cycle_rmse"]) == qall["n_cycles"]


def test_empty_artifact_graceful():
    art = {"name": "x", "cycles": [], "probes": []}
    res = reconstruct_field(_grid3(), art, cycle=0)
    assert res["k"] == 0 and res["n_probes"] == 0
    assert np.isnan(np.asarray(res["recon_field"])).all()
    assert res["finite_fraction"] == 0.0


def test_cycle_out_of_range_raises():
    art = _art()
    with pytest.raises(ValueError):
        reconstruct_field(_grid3(), art, cycle=99999)


def test_write_reconfield_emits_files_sanitised(tmp_path):
    write_reconfield(_grid3(), _art(), str(tmp_path), cycle=0, k=1)
    assert (tmp_path / "P_recon_cycle0.json").exists()
    assert (tmp_path / "P_recon_nodes.csv").exists()
    assert (tmp_path / "P_recon_quality.json").exists()
    assert (tmp_path / "summary.json").exists()
    rows = list(csv.reader(open(tmp_path / "P_recon_nodes.csv",
                                encoding="utf-8")))
    assert rows[0] == ["node", "x", "y", "z", "recon"]
    assert len(rows) == len(_grid3()) + 1
    q = json.loads((tmp_path / "P_recon_quality.json").read_text(encoding="utf-8"))
    assert "total_rmse" in q and "captured_var" in q

    tmp2 = tmp_path / "weird"
    write_reconfield(_grid3(), _art("pres sure"), str(tmp2), cycle=0, k=1)
    assert (tmp2 / "pres_sure_recon_nodes.csv").exists()
    assert (tmp2 / "pres_sure_recon_cycle0.json").exists()


def test_cli_roundtrip_and_missing_probes(tmp_path, capsys):
    trace = tmp_path / "trace.json"
    verts = tmp_path / "verts.npy"
    out = tmp_path / "out"
    trace.write_text(json.dumps(_art()), encoding="utf-8")
    np.save(verts, _grid3())
    assert main([str(trace), str(verts), "--out", str(out), "--cycle", "2"]) == 0
    assert (out / "P_recon_cycle2.json").exists()
    assert (out / "summary.json").exists()

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "x", "cycles": []}), encoding="utf-8")
    assert main([str(bad), str(verts), "--out", str(tmp_path / "o2")]) == 2
    assert "probes" in capsys.readouterr().err

    # cycle out of range -> 2
    assert main([str(trace), str(verts), "--out", str(tmp_path / "o3"),
                 "--cycle", "99999"]) == 2


def test_read_verts_handles_json_and_npy(tmp_path):
    jp = tmp_path / "v.json"
    jp.write_text(json.dumps([[0, 0, 0.0], [1, 0, 0.0]]), encoding="utf-8")
    assert _read_verts(str(jp)).shape == (2, 3)
    npv = tmp_path / "v.npy"
    np.save(npv, _grid3())
    np.testing.assert_array_equal(_read_verts(str(npv)), _grid3())
