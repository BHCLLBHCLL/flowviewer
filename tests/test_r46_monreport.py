"""R46 tests: render the monitoring analysis into a self-contained HTML report.

Pure NumPy + reuse of R45/R41; headless, no CGNS/vtk, no browser.
"""

from __future__ import annotations

import numpy as np
from fv.monreport import (
    _psd_bars,
    build_report,
    render_html,
    write_monitor_report,
)


def _trace_artifact(name="P"):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)
    v0 = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    return {
        "name": name, "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "values": list(v0)},
            {"query": (1.0, 0.0, 0.0), "node": 1,
             "values": list(np.zeros_like(t))},
        ],
    }


def test_build_report_assembles_cards_with_psd_bars():
    rep = build_report(_trace_artifact())
    assert rep["field"] == "P"
    assert rep["n_probes"] == 2
    assert len(rep["cards"]) == 2
    c = rep["cards"][0]
    assert c["dominant_freq"] == c["dominant_freq"]  # not nan for clean sine
    assert 0 < len(c["psd_bars"]) <= 32
    assert all(0.0 <= v <= 1.0 for v in c["psd_bars"])


def test_render_html_contains_summary_table_and_cards():
    html_text = render_html(build_report(_trace_artifact()))
    assert "<h1>Monitoring report — P</h1>" in html_text
    assert "dominant&nbsp;freq" in html_text
    assert "Per probe" in html_text
    assert "Probe 0" in html_text and "Probe 1" in html_text
    assert "class=\"spectro\"" in html_text


def test_render_html_no_probes():
    html_text = render_html({"field": "P", "n_probes": 0, "cards": []})
    assert "No probes" in html_text


def test_render_escapes_markup_in_field_name():
    html_text = render_html(build_report(_trace_artifact("<script>P</script>")))
    assert "<script>" not in html_text


def test_write_monitor_report_emits_html_and_summary(tmp_path):
    summary = write_monitor_report(_trace_artifact(), str(tmp_path))
    html_path = tmp_path / "P_monitor.html"
    assert html_path.exists()
    assert (tmp_path / "summary.json").exists()
    assert summary["file"] == "P_monitor.html"
    assert summary["n_probes"] == 2
    text = html_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in text and "Per probe" in text


def test_write_monitor_report_sanitises_weird_names(tmp_path):
    summary = write_monitor_report(_trace_artifact("pres sure"), str(tmp_path))
    assert (tmp_path / "pres_sure_monitor.html").exists()
    assert summary["field"] == "pres sure"


def test_psd_bars_down_samples_and_degrades():
    freq = list(np.arange(0.0, 3.0, 0.01))
    psd = list(abs(np.sin(freq)) + 1.0)
    bars = _psd_bars(freq, psd)
    assert len(bars) == 32
    assert max(bars) <= 1.0
    assert _psd_bars([], []) == []
    assert _psd_bars([1.0, 2.0], [0.0, 0.0]) == []
