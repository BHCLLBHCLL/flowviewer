"""R79 tests: the headless CLI honours a self-contained project's own source.

R78 made saved projects self-contained (a JSON-serialisable data-source
descriptor), but only the GUI re-materialised it; ``fv.report --project`` still
required a separate input and ignored the stored descriptor. R79 closes the
loop: ``run`` resolves the project's own source first (falling back to the
external ``--source`` / JSON pair for legacy R73 projects or an unreadable
recipe), and ``main`` lets the positional INPUT be omitted for a self-contained
project. Report generation stays out of scope by monkeypatching
``run_report_bundle`` / ``run_project`` / ``sequence_source``, and the project
store is steered via ``project_store_path`` so no home-directory state is
touched. Pure stdlib + numpy, headless.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fv import report as report_cli
from fv.gui import analysis as gui_analysis


def _store_path(tmp_path):
    return tmp_path / "projects.json"


def _input(tmp_path) -> str:
    p = tmp_path / "in.json"
    p.write_text(json.dumps(
        {"verts": [[0, 0, 0], [1, 1, 1]],
         "artifact": {"name": "T", "cycles": [0, 1], "probes": []}}),
        encoding="utf-8")
    return str(p)


def test_run_project_self_contained_json_source(monkeypatch, tmp_path):
    """A project carrying a JSON recipe re-runs with no external input."""
    path = _store_path(tmp_path)
    store = gui_analysis.ProjectStore(path=str(path))
    store.save("demo", ["spectral"], {},
               source=gui_analysis.json_desc(_input(tmp_path)))
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))

    seen = {}

    def fake_project(store2, name, verts, artifact, out_dir, *, dt=None):
        seen["name"] = name
        seen["nverts"] = verts.shape
        seen["artifact_name"] = artifact["name"]
        return {"spectral": str(Path(out_dir) / "spectral.html")}

    monkeypatch.setattr(report_cli, "run_project", fake_project)
    manifest = report_cli.run({"out_dir": str(tmp_path / "reports"),
                               "project": "demo"})
    assert seen["name"] == "demo"
    assert seen["nverts"] == (2, 3)
    assert seen["artifact_name"] == "T"
    assert manifest["reports"] == {"spectral": "spectral.html"}


def test_run_project_self_contained_sequence_source(monkeypatch, tmp_path):
    """A project carrying a sequence recipe re-materialises its source."""
    path = _store_path(tmp_path)
    store = gui_analysis.ProjectStore(path=str(path))
    store.save("demo", ["spectral"], {},
               source=gui_analysis.sequence_desc(
                   "seq", [(0.0, 0.0, 0.0)], field="P", budget_mb=16))
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))

    seen = {}

    def fake_seq(paths, probes, **kw):
        seen["paths"] = paths
        seen["probes"] = probes
        return np.zeros((2, 3)), {"name": "S", "cycles": [0], "probes": []}

    monkeypatch.setattr(gui_analysis, "sequence_source", fake_seq)

    def fake_project(store2, name, verts, artifact, out_dir, *, dt=None):
        seen["artifact_name"] = artifact["name"]
        return {"spectral": str(Path(out_dir) / "spectral.html")}

    monkeypatch.setattr(report_cli, "run_project", fake_project)
    report_cli.run({"out_dir": str(tmp_path / "reports"), "project": "demo"})
    assert seen["paths"] == "seq"
    assert seen["probes"] == [(0.0, 0.0, 0.0)]
    assert seen["artifact_name"] == "S"


def test_run_project_no_source_falls_back_to_input(monkeypatch, tmp_path):
    """A legacy R73 project (no source) uses the external input."""
    path = _store_path(tmp_path)
    store = gui_analysis.ProjectStore(path=str(path))
    store.save("legacy", ["spectral"], {})
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))

    seen = {}

    def fake_project(store2, name, verts, artifact, out_dir, *, dt=None):
        seen["artifact_name"] = artifact["name"]
        return {"spectral": str(Path(out_dir) / "spectral.html")}

    monkeypatch.setattr(report_cli, "run_project", fake_project)
    report_cli.run({"input": _input(tmp_path),
                    "out_dir": str(tmp_path / "reports"),
                    "project": "legacy"})
    assert seen["artifact_name"] == "T"


def test_run_project_source_wins_over_input(monkeypatch, tmp_path):
    """A rebuildable stored source takes precedence over the external input."""
    path = _store_path(tmp_path)
    store = gui_analysis.ProjectStore(path=str(path))
    store.save("demo", ["spectral"], {},
               source=gui_analysis.json_desc(_input(tmp_path)))
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))

    seen = {}

    def fake_project(store2, name, verts, artifact, out_dir, *, dt=None):
        seen["artifact_name"] = artifact["name"]
        return {"spectral": str(Path(out_dir) / "spectral.html")}

    monkeypatch.setattr(report_cli, "run_project", fake_project)
    report_cli.run({"input": str(tmp_path / "other.json"),
                    "out_dir": str(tmp_path / "reports"),
                    "project": "demo"})
    assert seen["artifact_name"] == "T"


def test_run_unknown_project_raises(monkeypatch, tmp_path):
    """An unknown project name still raises, even with a valid input."""
    path = _store_path(tmp_path)
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    monkeypatch.setattr(report_cli, "run_project",
                        lambda store, name, v, a, o, *, dt=None: None)
    with pytest.raises(ValueError):
        report_cli.run({"input": _input(tmp_path),
                        "out_dir": str(tmp_path / "reports"),
                        "project": "missing"})


def test_run_no_input_no_project_raises(tmp_path):
    """No input, no source, no project: a clear error instead of a silent no-op."""
    with pytest.raises(ValueError):
        report_cli.run({"out_dir": str(tmp_path / "reports")})


def test_main_self_contained_project_end_to_end(monkeypatch, tmp_path, capsys):
    """``--project`` alone re-runs a self-contained project end-to-end."""
    path = _store_path(tmp_path)
    store = gui_analysis.ProjectStore(path=str(path))
    store.save("demo", ["spectral"], {},
               source=gui_analysis.json_desc(_input(tmp_path)))
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    out_dir = tmp_path / "reports"
    monkeypatch.setattr(gui_analysis, "run_report_bundle",
                        lambda v, a, o, **kw: {"spectral": str(Path(o) / "spectral.html")})
    rc = report_cli.main(["--project", "demo", "-o", str(out_dir)])
    out = capsys.readouterr()
    assert rc == 0
    manifest = json.loads(out.out)
    assert manifest["reports"] == {"spectral": "spectral.html"}
    assert manifest["count"] == 1


def test_main_no_input_no_project_exit_two(capsys):
    """No input and no project is rejected at the CLI gate."""
    rc = report_cli.main([])
    out = capsys.readouterr()
    assert rc == 2
    assert "error:" in out.err


def test_main_source_needs_input_exit_two(capsys):
    """``--source`` without a raw sequence path is rejected."""
    rc = report_cli.main(["--source"])
    out = capsys.readouterr()
    assert rc == 2
    assert "--source needs" in out.err
