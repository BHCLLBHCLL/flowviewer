"""R55 tests: full-field DMD modal reconstruction (complex envelope).

Pure NumPy, headless (no CGNS/vtk). Asserts the complex-IDW exactness at probe
nodes, the node↔probe reconstruction tie, matrix-level captured variance, the
energy ordering, and the write/CLI round-trip incl. degradation and exit-code
paths.
"""

import csv
import json
import subprocess
import sys

import numpy as np
import pytest
from fv.dmdrecon import (
    _dmd_pieces,
    complex_idw_field,
    dmd_recon_quality,
    reconstruct_field_dmd,
    write_dmdrecon,
)


def _grid3():
    return np.asarray([[0.0, 0.0, 0.0], [0.25, 0.0, 0.0], [0.5, 0.0, 0.0],
                       [0.75, 0.0, 0.0], [1.0, 0.0, 0.0], [1.5, 0.0, 0.0],
                       [2.0, 0.0, 0.0]], dtype=np.float64)


def _art(nodes=(0, 1, 2, 3), n_cycles=200):
    """Stable (|λ|≈1) monitoring data: offsets + a 0.7 Hz tone + low sine."""
    t = np.arange(n_cycles, dtype=np.float64)
    x = [0.0, 0.25, 0.5, 0.75]
    off = [1.0, 1.5, 2.0, 2.5]
    probes = []
    for j in range(4):
        base = 2 * np.pi * 0.7 * t * 0.05
        v = off[j] + (2.0 * np.sin(base) if j < 2 else np.cos(base))
        probes.append({"name": f"p{j}", "node": int(nodes[j]),
                       "query": [x[j], 0.0, 0.0], "xyz": [x[j], 0.0, 0.0],
                       "values": [float(z) for z in v]})
    return {"name": "dmd_field", "cycles": [float(tt) for tt in t],
            "probes": probes}


def test_complex_idw_exact_at_probe_nodes():
    art = _art()
    w = np.array([1.0 + 0.5j, -2.0 - 1.0j, 3.0 + 2.0j, -4.0 + 0.25j])
    f = complex_idw_field(_grid3(), art["probes"], w)
    assert f.dtype.kind == "c"
    for j, pr in enumerate(art["probes"]):
        assert f[pr["node"]] == w[j]


def test_probe_node_matches_probe_recon():
    art = _art()
    res = reconstruct_field_dmd(_grid3(), art, cycle=13, k=None)
    for j, pr in enumerate(art["probes"]):
        assert abs(res["recon_field"][pr["node"]] -
                   res["probe_recon"][j]) < 1e-9


def test_full_reconstruction_captures_variance():
    art = _art()
    res = reconstruct_field_dmd(_grid3(), art, cycle=7, k=None)
    assert res["captured_var"] > 0.99
    assert res["finite_fraction"] == 1.0
    full = dmd_recon_quality(art, k=None)
    assert full["captured_var"] > 0.99
    assert full["total_rmse"] < 1e-3


def test_captured_var_monotonic_in_k():
    art = _art()
    full = dmd_recon_quality(art, k=None)
    trunc = dmd_recon_quality(art, k=2)
    assert trunc["captured_var"] > 0
    assert trunc["captured_var"] <= full["captured_var"] + 1e-6


def test_cycle_out_of_range_raises():
    art = _art(n_cycles=40)
    with pytest.raises(ValueError):
        reconstruct_field_dmd(_grid3(), art, cycle=40)
    with pytest.raises(ValueError):
        reconstruct_field_dmd(_grid3(), art, cycle=-1)


def test_empty_artifact_degrades():
    res = reconstruct_field_dmd(_grid3(), {"cycles": [], "probes": []}, cycle=0)
    assert res["captured_var"] == 0.0
    assert res["n_probes"] == 0 and res["r"] == 0
    assert np.isnan(res["recon_field"]).all()


def test_short_artifact_degrades():
    art = {"cycles": [0.0, 1.0, 2.0],
           "probes": [{"node": 0, "values": [1, 2, 3]}]}
    res = reconstruct_field_dmd(_grid3(), art, cycle=0)
    assert res["r"] == 0 and res["captured_var"] == 0.0


def test_dmd_pieces_energy_descending():
    art = _art()
    p = _dmd_pieces(art)
    assert p is not None and p["r"] >= 1
    kidx = np.arange(256)
    energy = []
    for i in range(p["r"]):
        vand = p["lam"][i] ** kidx
        energy.append(abs(p["alpha"][i]) ** 2
                      * np.sum(np.abs(vand) ** 2))
    assert np.all(np.diff(energy) <= 1e-12)


def test_write_and_cli_roundtrip(tmp_path):
    art = _art()
    verts = _grid3()
    verts_path = tmp_path / "verts.npy"
    np.save(verts_path, verts)
    tr_path = tmp_path / "field.json"
    tr_path.write_text(json.dumps(art), encoding="utf-8")

    # weird field name -> safe filenames
    art2 = dict(art, name="pres sure")
    n2 = tmp_path / "weird.json"
    n2.write_text(json.dumps(art2), encoding="utf-8")
    summ = write_dmdrecon(verts, art2, str(tmp_path / "out"), cycle=3)
    assert (tmp_path / "out" / "pres_sure_dmdrecon_cycle3.json").exists()
    assert (tmp_path / "out" / "pres_sure_dmdrecon_nodes.csv").exists()
    assert (tmp_path / "out" / "pres_sure_dmdrecon_quality.json").exists()
    assert (tmp_path / "out" / "summary.json").exists()
    act = json.loads(
        (tmp_path / "out" / "pres_sure_dmdrecon_cycle3.json").read_text())
    assert abs(act["captured_var"] - summ["captured_var"]) < 1e-12
    with open(str(tmp_path / "out" / "pres_sure_dmdrecon_nodes.csv"),
              encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == ["node", "x", "y", "z", "recon"]
    assert len(rows) == len(verts) + 1

    # CLI round-trip
    r = subprocess.run(
        [sys.executable, "-m", "fv.dmdrecon", str(tr_path), str(verts_path),
         "--out", str(tmp_path / "cli"), "--cycle", "1"],
        capture_output=True, text=True)
    assert r.returncode == 0
    assert (tmp_path / "cli" / "dmd_field_dmdrecon_cycle1.json").exists()

    # bad verts file -> exit 2
    bad = tmp_path / "bad.npy"
    bad.write_bytes(b"not a numpy file")
    r2 = subprocess.run(
        [sys.executable, "-m", "fv.dmdrecon", str(tr_path), str(bad),
         "--out", str(tmp_path / "cli2")],
        capture_output=True, text=True)
    assert r2.returncode == 2

    # missing probes -> exit 2
    no = tmp_path / "noprobe.json"
    no.write_text(json.dumps({"cycles": [0, 1, 2]}), encoding="utf-8")
    r3 = subprocess.run(
        [sys.executable, "-m", "fv.dmdrecon", str(no), str(verts_path),
         "--out", str(tmp_path / "cli3")],
        capture_output=True, text=True)
    assert r3.returncode == 2
