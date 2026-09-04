"""R52 tests: modal spatial map (IDW from probe weights onto the mesh).

Pure NumPy, headless, no CGNS, no VTK. Reuses R48 pod_decompose and R50
dmd_decompose on an R38 trace artifact.
"""

from __future__ import annotations

import csv
import json

import numpy as np
from fv.dmd import dmd_decompose
from fv.modalfield import (
    _read_verts,
    build_mode_field,
    idw_field,
    main,
    mode_weights,
    write_mode_field,
)
from fv.pod import pod_decompose


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    """3x3 planar mesh, 4 corner probes with a dominant 1 Hz pair."""
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)
    v = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    v2 = 1.5 + np.sin(2 * np.pi * 1.0 * t + 0.5)
    # node order of _grid3(): j-major, so corners are 0=(0,0) 2=(2,0) 6=(0,2) 8=(2,2)
    return {
        "name": name, "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "xyz": (0.0, 0.0, 0.0),
             "values": list(v)},
            {"query": (2.0, 0.0, 0.0), "node": 2, "xyz": (2.0, 0.0, 0.0),
             "values": list(v2)},
            {"query": (0.0, 2.0, 0.0), "node": 6, "xyz": (0.0, 2.0, 0.0),
             "values": list(np.zeros_like(t))},
            {"query": (2.0, 2.0, 0.0), "node": 8, "xyz": (2.0, 2.0, 0.0),
             "values": list(0.5 * np.sin(2 * np.pi * 3.0 * t))},
        ],
    }


def test_idw_exact_at_probe_node():
    verts = _grid3()
    probes = _art()["probes"]
    weights = [1.0, -2.0, 3.0, -4.0]
    field = idw_field(verts, probes, weights, neighbors=4)
    for j, pr in enumerate(probes):
        assert field[pr["node"]] == weights[j]


def test_idw_halfway_plane_midpoint_and_nearest():
    verts = np.array([[0, 0, 0.0], [0.25, 0, 0.0], [1.0, 0, 0.0],
                      [1.5, 0, 0.0], [2, 0, 0.0]])
    probes = [
        {"node": 0, "xyz": (0.0, 0.0, 0.0)},
        {"node": 4, "xyz": (2.0, 0.0, 0.0)},
    ]
    # all-neighbours, p=1: equidistant midpoint blends to 0.5
    field_all = idw_field(verts, probes, [0.0, 1.0], p=1.0, neighbors=4)
    assert abs(field_all[1] - 0.125) < 1e-9      # 0.25: closer to left probe
    assert abs(field_all[2] - 0.5) < 1e-9        # 1.0: equidistant -> 0.5
    # nearest neighbour = 1: each vertex takes its closest probe's weight
    field_n1 = idw_field(verts, probes, [0.0, 1.0], p=1.0, neighbors=1)
    assert field_n1[1] == 0.0                    # closer to left probe (w=0)
    assert field_n1[3] == 1.0                    # closer to right probe (w=1)


def test_pod_source_matches_mode0_at_probe_nodes():
    art = _art()
    res = build_mode_field(_grid3(), art, source="pod", k=0)
    pod = pod_decompose(art)
    assert res["meta"]["energy_share"] > 0.5
    assert res["meta"]["finite_count"] == len(_grid3())   # interior all covered
    for j, pr in enumerate(art["probes"]):
        assert res["node_field"][pr["node"]] == pod["modes"][0][j]
    _w, _m = mode_weights(art, source="pod", k=0)
    assert np.allclose(np.asarray(_w), pod["modes"][0])


def test_dmd_source_uses_dominant_mode_mag():
    art = _art()
    dmd = dmd_decompose(art)
    assert dmd["dominant"] is not None
    dom_i = dmd["dominant"]["i"]
    w_mag, meta = mode_weights(art, source="dmd", weight="mag")
    assert np.allclose(w_mag, dmd["modes"][dom_i]["mode_mag"])
    assert meta["freq"] > 0
    w_signed, meta_s = mode_weights(art, source="dmd", weight="signed")
    expect = np.asarray([m[0] for m in dmd["modes"][dom_i]["mode"]])
    assert np.allclose(w_signed, expect)


def test_idw_nan_out_of_reach():
    verts = _grid3()
    # probe with neither xyz nor query -> no usable reference -> all NaN
    field = idw_field(verts, [{"node": 0, "query": None}], [1.0])
    assert not np.isfinite(field).any()
    # and no probes at all -> all NaN
    assert np.isnan(idw_field(verts, [], [])).all()


def test_write_emits_csv_json_summary_sanitised(tmp_path):
    summary = write_mode_field(_grid3(), _art(), str(tmp_path), source="pod", k=0)
    assert (tmp_path / "P_mode0.json").exists()
    assert (tmp_path / "P_mode0_nodes.csv").exists()
    assert (tmp_path / "summary.json").exists()
    assert summary["csv"] == "P_mode0_nodes.csv"
    j = json.loads((tmp_path / "P_mode0.json").read_text(encoding="utf-8"))
    assert "node_field" in j and "meta" in j
    rows = list(csv.reader(open(tmp_path / "P_mode0_nodes.csv",
                                encoding="utf-8")))
    assert rows[0] == ["node", "x", "y", "z", "weight"]
    assert len(rows) == len(_grid3()) + 1

    tmp2 = tmp_path / "weird"
    write_mode_field(_grid3(), _art("pres sure"), str(tmp2), source="pod", k=0)
    assert (tmp2 / "pres_sure_mode0_nodes.csv").exists()


def test_build_empty_graceful():
    res = build_mode_field(_grid3(), {"name": "x", "cycles": [], "probes": []})
    assert res["weights"] == []
    assert res["meta"]["finite_fraction"] == 0.0
    assert np.isnan(np.asarray(res["node_field"])).all()


def test_cli_roundtrip_and_missing_probes(tmp_path, capsys):
    trace = tmp_path / "trace.json"
    verts = tmp_path / "verts.npy"
    out = tmp_path / "out"
    trace.write_text(json.dumps(_art()), encoding="utf-8")
    np.save(verts, _grid3())
    assert main([str(trace), str(verts), "--out", str(out)]) == 0
    assert (out / "P_mode0.json").exists()
    assert (out / "summary.json").exists()

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "x", "cycles": []}), encoding="utf-8")
    assert main([str(bad), str(verts), "--out", str(tmp_path / "o2")]) == 2
    assert "probes" in capsys.readouterr().err

    # out-of-range POD mode index -> 2
    assert main([str(trace), str(verts), "--out", str(tmp_path / "o3"),
                 "--source", "pod", "--k", "999"]) == 2


def test_read_verts_handles_json_and_bad_shape(tmp_path):
    jp = tmp_path / "v.json"
    jp.write_text(json.dumps([[0, 0, 0.0], [1, 0, 0.0]]), encoding="utf-8")
    assert _read_verts(str(jp)).shape == (2, 3)
    bad = tmp_path / "badv.json"
    bad.write_text(json.dumps([0, 1, 2]), encoding="utf-8")
    assert _read_verts(str(bad)).shape == (3,)   # caller validates ndim
