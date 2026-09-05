"""R71 tests: Batch Analysis report generation (run-all + index page).

R64-R70 let the user run one report kind at a time (optionally from a named
preset). R71 adds ``run_reports``/``run_report_bundle``/``write_report_index``
in ``fv.gui.analysis`` so several kinds can be generated at once into one output
folder with an ``index.html`` that links each result.

These tests keep report generation out of scope by monkeypatching
``analysis.run_report`` with a recorder, so they exercise only the
batch-ordering / param-merge / dt-fallback / index-write logic. Pure
NumPy/pathlib, headless.
"""

from __future__ import annotations

from fv.gui import analysis


def test_run_reports_none_artifact_returns_empty(tmp_path):
    assert analysis.run_reports("V", None, str(tmp_path)) == {}


def test_run_reports_all_kinds_in_registry_order(monkeypatch, tmp_path):
    calls = []

    def fake(kind, verts, artifact, out_dir, **kw):
        calls.append(kind)
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    out = analysis.run_reports("V", "A", str(tmp_path))
    assert list(out.keys()) == list(analysis.REPORTS.keys())
    assert calls == list(analysis.REPORTS.keys())


def test_run_reports_kind_filter_orders_result(monkeypatch, tmp_path):
    calls = []

    def fake(kind, verts, artifact, out_dir, **kw):
        calls.append(kind)
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    out = analysis.run_reports("V", "A", str(tmp_path),
                               kinds=["coherence", "spectral", "bogus"])
    assert calls == ["coherence", "spectral"]
    assert list(out.keys()) == ["coherence", "spectral"]


def test_run_reports_param_overlay_normalised(monkeypatch, tmp_path):
    seen = {}

    def fake(kind, verts, artifact, out_dir, **kw):
        seen[kind] = kw
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    analysis.run_reports("V", "A", str(tmp_path), kinds=["spectral"],
                         params={"spectral": {"frames": 3, "bogus": 99}})
    assert seen["spectral"]["frames"] == 3
    assert "bogus" not in seen["spectral"]


def test_run_reports_dt_fallback(monkeypatch, tmp_path):
    seen = {}

    def fake(kind, verts, artifact, out_dir, **kw):
        seen[kind] = kw
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    analysis.run_reports("V", "A", str(tmp_path), kinds=["spectral"], dt=0.5)
    assert seen["spectral"]["dt"] == 0.5


def test_run_reports_dt_preserved_when_set(monkeypatch, tmp_path):
    seen = {}

    def fake(kind, verts, artifact, out_dir, **kw):
        seen[kind] = kw
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    analysis.run_reports("V", "A", str(tmp_path), kinds=["spectral"],
                         params={"spectral": {"dt": 0.125}}, dt=0.5)
    assert seen["spectral"]["dt"] == 0.125


def test_run_reports_omits_empty_paths(monkeypatch, tmp_path):
    def fake(kind, verts, artifact, out_dir, **kw):
        return None if kind == "spectral" else f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    out = analysis.run_reports("V", "A", str(tmp_path),
                               kinds=["spectral", "coherence"])
    assert "spectral" not in out
    assert list(out.keys()) == ["coherence"]


def test_write_report_index_creates_links(tmp_path):
    paths = {"spectral": str(tmp_path / "spectral.html"),
             "spatial_pod": str(tmp_path / "pod.html")}
    index = analysis.write_report_index(paths, str(tmp_path))
    assert index == tmp_path / "index.html"
    text = index.read_text(encoding="utf-8")
    assert "Spectral Field Map (R58)" in text
    assert "Spatial POD Report (R54)" in text
    assert 'href="spectral.html"' in text
    assert 'href="pod.html"' in text
    assert "2 report(s) generated." in text


def test_write_report_index_escapes_html(tmp_path):
    index = analysis.write_report_index(
        {"spectral": str(tmp_path / "a<&>.html")}, str(tmp_path),
        title='X "y" & <z>')
    text = index.read_text(encoding="utf-8")
    assert "&lt;z&gt;" in text
    assert "&amp;" in text
    assert 'href="a&lt;&amp;&gt;.html"' in text


def test_run_report_bundle_writes_index(monkeypatch, tmp_path):
    def fake(kind, verts, artifact, out_dir, **kw):
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    out = analysis.run_report_bundle("V", "A", str(tmp_path),
                                     kinds=["spectral", "coherence"])
    assert list(out.keys()) == ["spectral", "coherence"]
    assert (tmp_path / "index.html").is_file()


def test_run_report_bundle_none_artifact_no_index(tmp_path):
    out = analysis.run_report_bundle("V", None, str(tmp_path))
    assert out == {}
    assert not (tmp_path / "index.html").exists()


def test_run_report_bundle_empty_params_uses_defaults(monkeypatch, tmp_path):
    seen = {}

    def fake(kind, verts, artifact, out_dir, **kw):
        seen[kind] = kw
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    analysis.run_report_bundle("V", "A", str(tmp_path), kinds=["coherence"])
    assert "ref_probe" in seen["coherence"]
    assert (tmp_path / "index.html").is_file()
