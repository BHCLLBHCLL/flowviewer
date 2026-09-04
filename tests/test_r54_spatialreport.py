"""R54 tests: spatial analysis HTML report.

Pure NumPy, headless, no CGNS, no VTK. Reuses R52 build_mode_field and R53
mean_field/reconstruct_field/recon_quality on an R38 trace artifact.
"""

from __future__ import annotations

import json

import numpy as np
from fv.spatialreport import (
    _read_verts,
    build_spatial_report,
    main,
    render_html,
    write_spatial_report,
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


def test_report_blocks_populated():
    art = _art()
    rep = build_spatial_report(_grid3(), art, top=5, cycle=3)
    assert rep["field"] == "P"
    assert rep["n_probes"] == 3 and rep["n_cycles"] == len(art["cycles"])
    assert rep["n_vertices"] == len(_grid3())
    assert 1 <= len(rep["modes"]) <= 3  # == min(top, n_modes)
    for k in ("min", "max", "mean", "finite_fraction", "coverage"):
        assert k in rep["mean"]
    assert "captured_var" in rep["recon"]
    assert rep["recon"]["captured_var"] > 0
    assert "total_rmse" in rep["quality"]
    assert rep["quality"]["n_probes"] == 3


def test_mode_energy_descending():
    art = _art()
    rep = build_spatial_report(_grid3(), art, top=None)
    shares = [m["energy_share"] for m in rep["modes"]]
    assert shares == sorted(shares, reverse=True)


def test_render_html_sections_and_escaping():
    art = _art("<script>alert(1)</script>")
    rep = build_spatial_report(_grid3(), art)
    html = render_html(rep)
    for section in ("Summary", "Mean field", "Modes", "Reconstruction"):
        assert section in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_no_probes():
    art = {"name": "x", "cycles": [], "probes": []}
    rep = build_spatial_report(_grid3(), art)
    html = render_html(rep)
    assert "No probes." in html
    assert "Modes" not in html


def test_empty_artifact_graceful(tmp_path):
    art = {"name": "x", "cycles": [], "probes": []}
    rep = build_spatial_report(_grid3(), art)
    assert rep["n_probes"] == 0 and rep["modes"] == []
    assert rep["n_vertices"] == len(_grid3())
    # write path must not raise either
    summary = write_spatial_report(_grid3(), art, str(tmp_path / "out"))
    assert summary["n_probes"] == 0


def test_write_spatial_report_emits_files_sanitised(tmp_path):
    write_spatial_report(_grid3(), _art(), str(tmp_path), top=3, cycle=0)
    assert (tmp_path / "P_spatial.html").exists()
    assert (tmp_path / "P_spatial.json").exists()
    assert (tmp_path / "summary.json").exists()
    payload = json.loads((tmp_path / "P_spatial.json").read_text(encoding="utf-8"))
    assert payload["n_probes"] == 3 and payload["modes"]

    tmp2 = tmp_path / "weird"
    write_spatial_report(_grid3(), _art("pres sure"), str(tmp2), top=2)
    assert (tmp2 / "pres_sure_spatial.html").exists()
    assert (tmp2 / "pres_sure_spatial.json").exists()
    summary = json.loads((tmp2 / "summary.json").read_text(encoding="utf-8"))
    assert summary["top1_energy"] is not None
    assert "recon_captured" in summary


def test_cli_roundtrip_and_errors(tmp_path, capsys):
    trace = tmp_path / "trace.json"
    verts = tmp_path / "verts.npy"
    out = tmp_path / "out"
    trace.write_text(json.dumps(_art()), encoding="utf-8")
    np.save(verts, _grid3())
    assert main([str(trace), str(verts), "--out", str(out),
                 "--cycle", "2", "--top", "3"]) == 0
    assert (out / "P_spatial.html").exists()
    assert (out / "P_spatial.json").exists()
    assert (out / "summary.json").exists()

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "x", "cycles": []}), encoding="utf-8")
    assert main([str(bad), str(verts), "--out", str(tmp_path / "o2")]) == 2
    assert "probes" in capsys.readouterr().err

    bj = tmp_path / "bad_verts.json"
    bj.write_text(json.dumps([[0, 0]]), encoding="utf-8")
    assert main([str(trace), str(bj), "--out", str(tmp_path / "o3")]) == 2

    # cycle out of range -> 2
    assert main([str(trace), str(verts), "--out", str(tmp_path / "o4"),
                 "--cycle", "99999"]) == 2


def test_top_one_consistency():
    art = _art()
    rep = build_spatial_report(_grid3(), art, top=1)
    assert len(rep["modes"]) == 1
    # full-k reconstruction captured variance should match the quality block
    assert rep["recon"]["captured_var"] == rep["quality"]["captured_var"]


def test_read_verts_handles_json_and_npy(tmp_path):
    jp = tmp_path / "v.json"
    jp.write_text(json.dumps([[0, 0, 0.0], [1, 0, 0.0]]), encoding="utf-8")
    assert _read_verts(str(jp)).shape == (2, 3)
    npv = tmp_path / "v.npy"
    np.save(npv, _grid3())
    np.testing.assert_array_equal(_read_verts(str(npv)), _grid3())
