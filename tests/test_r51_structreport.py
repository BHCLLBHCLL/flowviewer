"""R51 tests: render the structural / modal analysis into an HTML report.

Reuses R47 (correlation), R48 (POD) and R50 (DMD) on an R38 trace artifact.
Pure NumPy, headless, no CGNS/vtk, no browser.
"""

from __future__ import annotations

import json

import numpy as np
from fv.structreport import (
    build_structure_report,
    main,
    render_html,
    write_structure_report,
)


def _trace_artifact(name="P"):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)  # 400 samples
    v0 = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    v1 = 1.5 + 1.0 * np.sin(2 * np.pi * 1.0 * t + 0.5)  # in-phase with v0
    return {
        "name": name, "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "values": list(v0)},
            {"query": (1.0, 0.0, 0.0), "node": 1, "values": list(v1)},
            {"query": (2.0, 0.0, 0.0), "node": 2,
             "values": list(np.zeros_like(t))},
            {"query": (3.0, 0.0, 0.0), "node": 3,
             "values": list(0.5 * np.sin(2 * np.pi * 3.0 * t))},
        ],
    }


def test_build_structure_report_assembles_all_blocks():
    rep = build_structure_report(_trace_artifact())
    assert rep["field"] == "P"
    assert rep["n_probes"] == 4
    assert rep["n_cycles"] == 400

    corr = rep["corr"]
    assert len(corr["matrix"]) == 4
    assert corr["matrix"][0][0] == 1.0
    assert corr["matrix"][1][0] > 0.8          # v0/v1 co-oscillate
    assert any(0 in g["members"] and 1 in g["members"]
               for g in corr["coherent_groups"])
    assert corr["top_pairs"][0]["rho"] > 0.8

    pod = rep["pod"]
    assert pod["n_modes"] > 0
    assert pod["energy_shares"][0] > 0.5       # 1 Hz pair dominates
    assert abs(sum(pod["energy_shares"]) - 1.0) < 1e-9

    dmd = rep["dmd"]
    assert dmd["r"] > 0
    assert dmd["dominant"] is not None
    assert abs(dmd["dominant"]["freq"] - 1.0) < 0.05
    assert len(dmd["modes"]) == dmd["r"]


def test_render_html_contains_all_sections():
    html_text = render_html(build_structure_report(_trace_artifact()))
    assert "<h1>Structure report — P</h1>" in html_text
    for section in ("Correlation", "Coherent groups", "Strongest pairs",
                    "POD energy", "DMD modes"):
        assert f"<h2>{section}</h2>" in html_text
    assert "class=\"heat\"" in html_text
    assert "class=\"bar\"" in html_text
    assert "<table><tr><th>i</th><th>freq</th>" in html_text


def test_render_html_no_probes():
    html_text = render_html({"field": "P", "n_probes": 0})
    assert "No probes" in html_text


def test_render_escapes_markup_in_field_name():
    html_text = render_html(build_structure_report(_trace_artifact(
        "<script>P</script>")))
    assert "<script>" not in html_text


def test_write_structure_report_emits_html_and_summary(tmp_path):
    summary = write_structure_report(_trace_artifact(), str(tmp_path))
    html_path = tmp_path / "P_struct.html"
    assert html_path.exists()
    assert (tmp_path / "summary.json").exists()
    assert summary["file"] == "P_struct.html"
    assert summary["n_probes"] == 4
    text = html_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in text
    assert "DMD modes" in text


def test_write_structure_report_sanitises_weird_names(tmp_path):
    summary = write_structure_report(_trace_artifact("pres sure"),
                                     str(tmp_path))
    assert (tmp_path / "pres_sure_struct.html").exists()
    assert summary["field"] == "pres sure"


def test_write_respects_thresholds(tmp_path):
    # a lax threshold joins all probes; a strict one keeps only the 1 Hz pair
    lax = write_structure_report(_trace_artifact(), str(tmp_path),
                                 corr_threshold=0.1)
    strict = write_structure_report(_trace_artifact(), str(tmp_path) + "_s",
                                    corr_threshold=0.99)
    assert lax["n_coherent_groups"] >= strict["n_coherent_groups"]


def test_cli_roundtrip_and_error(tmp_path, capsys):
    trace = tmp_path / "trace.json"
    out = tmp_path / "out"
    trace.write_text(json.dumps(_trace_artifact()), encoding="utf-8")
    assert main([str(trace), "--out", str(out)]) == 0
    assert (out / "P_struct.html").exists()
    assert (out / "summary.json").exists()

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"name": "x", "cycles": []}), encoding="utf-8")
    assert main([str(bad), "--out", str(tmp_path / "out2")]) == 2
    assert "probes" in capsys.readouterr().err
