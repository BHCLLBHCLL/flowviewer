"""R56 tests: spatial HTML report with the DMD POD/DMD pair (opt-in).

Pure NumPy, headless, no CGNS/VTK. Extends R54's spatial report with the DMD
mode-shape fields (R55 build_dmd_mode_field), DMD full-field reconstruction and
DMD quality — all gated behind ``dmd=True`` (default off keeps R54 output byte-
identical).
"""

import json

import numpy as np
from fv.dmdrecon import _dmd_pieces, _mode_meta, build_dmd_mode_field
from fv.spatialreport import (
    _read_verts,
    build_spatial_report,
    main,
    render_html,
    write_spatial_report,
)


def _grid3():
    return np.asarray([[0.0, 0.0, 0.0], [0.25, 0.0, 0.0], [0.5, 0.0, 0.0],
                       [0.75, 0.0, 0.0], [1.0, 0.0, 0.0], [1.5, 0.0, 0.0],
                       [2.0, 0.0, 0.0]], dtype=np.float64)


def _art(name="D", n_cycles=200):
    t = np.arange(n_cycles, dtype=np.float64)
    x = [0.0, 0.25, 0.5, 0.75]
    off = [1.0, 1.5, 2.0, 2.5]
    probes = []
    for j in range(4):
        base = 2 * np.pi * 0.7 * t * 0.05
        v = off[j] + (2.0 * np.sin(base) if j < 2 else np.cos(base))
        probes.append({"name": f"p{j}", "node": int(j),
                       "query": [x[j], 0.0, 0.0], "xyz": [x[j], 0.0, 0.0],
                       "values": [float(z) for z in v]})
    return {"name": name, "cycles": [float(tt) for tt in t],
            "probes": probes}


def test_dmd_disabled_keeps_report_pod_only():
    rep = build_spatial_report(_grid3(), _art(), dmd=False)
    assert rep["dmd"]["enabled"] is False
    assert rep["dmd"]["modes"] == []
    assert rep["dmd"]["recon"]["captured_var"] == 0.0
    html = render_html(rep)
    assert "DMD modes" not in html
    assert "Modes" in html


def test_dmd_enabled_populates_report():
    rep = build_spatial_report(_grid3(), _art(), dmd=True)
    assert rep["dmd"]["enabled"] is True
    assert 1 <= len(rep["dmd"]["modes"]) <= 3
    shares = [m["energy_share"] for m in rep["dmd"]["modes"]]
    assert shares == sorted(shares, reverse=True)
    assert rep["dmd"]["recon"]["captured_var"] > 0
    assert rep["dmd"]["quality"]["n_probes"] == 4
    assert rep["dmd"]["quality"]["n_cycles"] == 200


def test_render_html_dmd_sections_when_enabled():
    rep = build_spatial_report(_grid3(), _art(), dmd=True, dmd_top=2)
    html = render_html(rep)
    for s in ("Summary", "Mean field", "Modes", "Reconstruction",
              "DMD modes", "DMD reconstruction", "DMD quality"):
        assert s in html


def test_dmd_mode_field_exact_at_probe_nodes():
    art = _art()
    p = _dmd_pieces(art)
    assert p is not None and p["r"] >= 1
    bf = build_dmd_mode_field(_grid3(), art, k=0)
    assert bf["enabled"] is True
    for j, pr in enumerate(art["probes"]):
        assert abs(bf["node_field"][pr["node"]] - abs(p["phi"][j, 0])) < 1e-9
    assert bf["meta"]["freq"] >= 0          # any real mode returns a freq
    assert bf["meta"]["energy_share"] > 0
    # at least one DMD mode is oscillating (freq > 0)
    assert any(_mode_meta(p["lam"][i], p["dt"])[0] > 0
               for i in range(p["r"]))


def test_dmd_degraded_on_empty_artifact():
    rep = build_spatial_report(_grid3(), {"name": "x", "cycles": [],
                                          "probes": []}, dmd=True)
    assert rep["dmd"]["enabled"] is True
    assert rep["dmd"]["modes"] == []
    assert rep["dmd"]["recon"]["captured_var"] == 0.0
    html = render_html(rep)
    assert "No DMD modes." not in html      # no-probe path short-circuits


def test_write_dmd_report_emits_and_summary(tmp_path):
    summ = write_spatial_report(_grid3(), _art("pres sure"), str(tmp_path),
                                top=2, dmd=True, dmd_top=2)
    assert (tmp_path / "pres_sure_spatial.html").exists()
    assert (tmp_path / "pres_sure_spatial.json").exists()
    assert (tmp_path / "summary.json").exists()
    payload = json.loads((tmp_path / "pres_sure_spatial.json").read_text())
    assert payload["dmd"]["enabled"] is True
    assert payload["dmd"]["modes"]
    assert summ["dmd"] is True
    assert summ["dmd_top_energy"] is not None
    assert "dmd_captured" in summ


def test_cli_dmd_flag(tmp_path):
    trace = tmp_path / "trace.json"
    verts = tmp_path / "verts.npy"
    out = tmp_path / "out"
    trace.write_text(json.dumps(_art()), encoding="utf-8")
    np.save(verts, _grid3())
    assert main([str(trace), str(verts), "--out", str(out),
                 "--dmd", "--dmd-top", "2"]) == 0
    assert (out / "D_spatial.html").exists()
    payload = json.loads((out / "D_spatial.json").read_text())
    assert payload["dmd"]["enabled"] is True
    assert payload["dmd"]["quality"]["n_probes"] == 4


def test_read_verts_from_json_and_npy(tmp_path):
    jp = tmp_path / "v.json"
    jp.write_text(json.dumps(_grid3().tolist()), encoding="utf-8")
    np.testing.assert_array_equal(_read_verts(str(jp)), _grid3())
    npv = tmp_path / "v.npy"
    np.save(npv, _grid3())
    np.testing.assert_array_equal(_read_verts(str(npv)), _grid3())
