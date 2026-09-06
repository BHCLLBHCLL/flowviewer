"""R80 tests: the headless CLI manages the whole project lifecycle.

R73-R79 let a project be *run* headlessly via ``--project`` and *saved* only in
the GUI (``ProjectStore``), so creating / listing / deleting a project could not
be scripted. R80 closes that gap: ``--save-project NAME`` records the current
``--source`` sequence or JSON input as a new self-contained project (persisting
the same ``sequence_desc`` / ``json_desc`` descriptor the GUI tracks),
``--list-projects`` prints every saved project as JSON, and ``--delete-project
NAME`` removes one. Report generation stays out of scope by monkeypatching
``run_report_bundle`` / ``run_project`` and the store is steered via
``project_store_path`` so no home-directory state is touched. Pure stdlib +
numpy, headless.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from fv import report as report_cli
from fv.gui import analysis as gui_analysis


def _store_path(tmp_path) -> Path:
    return tmp_path / "projects.json"


def _input(tmp_path) -> str:
    p = tmp_path / "in.json"
    p.write_text(json.dumps(
        {"verts": [[0, 0, 0], [1, 1, 1]],
         "artifact": {"name": "T", "cycles": [0, 1], "probes": []}}),
        encoding="utf-8")
    return str(p)


def test_save_project_json_input(monkeypatch, tmp_path, capsys):
    """``--save-project`` records a JSON input as a self-contained project."""
    path = _store_path(tmp_path)
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    rc = report_cli.main(["--save-project", "demo", _input(tmp_path)])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    assert body["saved"] is True
    assert body["name"] == "demo"
    assert "spectral" in body["kinds"]
    store = gui_analysis.ProjectStore(path=str(path))
    proj = store.get("demo")
    assert proj is not None
    assert proj["source"] == {"type": "json", "path": _input(tmp_path)}


def test_save_project_sequence_with_probes(monkeypatch, tmp_path, capsys):
    """``--save-project --source`` records a sequence descriptor with probes."""
    path = _store_path(tmp_path)
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    rc = report_cli.main(["--save-project", "demo", "seq", "--source",
                          "--probe", "0.5,0.5,0.5", "--field", "Pressure"])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    assert body["saved"] is True
    store = gui_analysis.ProjectStore(path=str(path))
    proj = store.get("demo")
    assert proj is not None
    assert proj["source"] == gui_analysis.sequence_desc(
        "seq", [(0.5, 0.5, 0.5)], field="Pressure", budget_mb=64)


def test_list_projects_empty(monkeypatch, tmp_path, capsys):
    """``--list-projects`` on an empty store prints an empty list."""
    path = _store_path(tmp_path)
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    rc = report_cli.main(["--list-projects"])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    assert body["projects"] == []


def test_list_projects_marks_self_contained(monkeypatch, tmp_path, capsys):
    """``--list-projects`` shows each project with its self_contained flag."""
    path = _store_path(tmp_path)
    store = gui_analysis.ProjectStore(path=str(path))
    store.save("with_source", ["spectral"], {},
               source=gui_analysis.json_desc(_input(tmp_path)))
    store.save("legacy", ["coherence"], {})
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    rc = report_cli.main(["--list-projects"])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    by = {p["name"]: p for p in body["projects"]}
    assert by["with_source"]["self_contained"] is True
    assert by["legacy"]["self_contained"] is False
    assert by["with_source"]["kinds"] == ["spectral"]
    assert by["legacy"]["kinds"] == ["coherence"]


def test_delete_project(monkeypatch, tmp_path, capsys):
    """``--delete-project`` removes a project and reports success."""
    path = _store_path(tmp_path)
    store = gui_analysis.ProjectStore(path=str(path))
    store.save("demo", ["spectral"], {},
               source=gui_analysis.json_desc(_input(tmp_path)))
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    rc = report_cli.main(["--delete-project", "demo"])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    assert body["deleted"] is True
    assert body["name"] == "demo"
    assert gui_analysis.ProjectStore(path=str(path)).get("demo") is None


def test_delete_project_missing(monkeypatch, tmp_path, capsys):
    """Deleting a project that does not exist fails with exit code 1."""
    path = _store_path(tmp_path)
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    rc = report_cli.main(["--delete-project", "missing"])
    out = capsys.readouterr()
    assert rc == 1
    assert "project not found" in out.err


def test_save_project_no_input_exit_two(capsys):
    """``--save-project`` without an input or source is rejected."""
    rc = report_cli.main(["--save-project", "demo"])
    out = capsys.readouterr()
    assert rc == 2
    assert "--save-project needs" in out.err


def test_save_project_source_needs_input_exit_two(capsys):
    """``--save-project --source`` without a raw sequence path is rejected."""
    rc = report_cli.main(["--save-project", "demo", "--source"])
    out = capsys.readouterr()
    assert rc == 2
    assert "--source needs" in out.err


def test_save_project_source_needs_probes_exit_two(capsys):
    """``--save-project --source`` without monitoring points is rejected."""
    rc = report_cli.main(["--save-project", "demo", "seq", "--source"])
    out = capsys.readouterr()
    assert rc == 2
    assert "needs monitoring points" in out.err


def test_save_then_run_roundtrip(monkeypatch, tmp_path, capsys):
    """A project saved headlessly re-runs headlessly with no extra input."""
    path = _store_path(tmp_path)
    monkeypatch.setattr(report_cli, "project_store_path", lambda: str(path))
    src = _input(tmp_path)
    rc = report_cli.main(["--save-project", "demo", src])
    assert rc == 0
    capsys.readouterr()

    out_dir = tmp_path / "reports"

    def fake_bundle(verts, artifact, o, **kw):
        assert isinstance(verts, np.ndarray)
        assert verts.shape == (2, 3)
        assert artifact["name"] == "T"
        return {"spectral": str(Path(o) / "spectral.html")}

    monkeypatch.setattr(gui_analysis, "run_report_bundle", fake_bundle)
    rc = report_cli.main(["--project", "demo", "-o", str(out_dir)])
    out = capsys.readouterr()
    assert rc == 0
    manifest = json.loads(out.out)
    assert manifest["reports"] == {"spectral": "spectral.html"}
    assert manifest["count"] == 1
