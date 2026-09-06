"""R81 tests: the headless CLI recalls named parameter presets.

The GUI (R68-R70) can save and re-run a named per-kind parameter preset through
``PresetStore``, but the headless CLI (R74) could previously only overlay raw
``--params`` JSON and never referenced a preset by name. R81 closes that gap:
``--preset KIND:NAME`` (repeatable) loads a normalised preset snapshot from the
per-user ``PresetStore`` and merges it over the raw ``--params`` overlay so a
scripted run reproduces a GUI preset run, and ``--list-presets [KIND]`` prints
every stored preset (or one kind's) as JSON for discovery. Report generation is
stubbed by monkeypatching ``run_report_bundle`` and the store is steered via
``default_preset_path`` so no home-directory state is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from fv import report as report_cli
from fv.gui import analysis as gui_analysis


def _preset_path(tmp_path) -> Path:
    return tmp_path / "presets.json"


def _input(tmp_path) -> str:
    p = tmp_path / "in.json"
    p.write_text(json.dumps(
        {"verts": [[0, 0, 0], [1, 1, 1]],
         "artifact": {"name": "T", "cycles": [0, 1], "probes": []}}),
        encoding="utf-8")
    return str(p)


def _pad_preset(tmp_path):
    """Build a seeded preset store at the isolated path (and patch the path)."""
    path = _preset_path(tmp_path)
    store = gui_analysis.PresetStore(path=str(path))
    store.save("spectral", "Foo", {"k": 3, "p": 4.0})
    store.save("coherence", "Bar", {"k": 2, "nperseg": 128})
    return path, store


def test_list_presets_empty(monkeypatch, tmp_path, capsys):
    """``--list-presets`` on an empty store prints an empty list."""
    path = _preset_path(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    rc = report_cli.main(["--list-presets"])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    assert body["presets"] == []
    assert body["count"] == 0


def test_list_presets_all_kinds(monkeypatch, tmp_path, capsys):
    """``--list-presets`` prints every stored preset across kinds as JSON."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    rc = report_cli.main(["--list-presets"])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    assert body["count"] == 2
    by = {(p["kind"], p["name"]): p for p in body["presets"]}
    assert by["spectral", "Foo"]["params"]["k"] == 3
    assert by["spectral", "Foo"]["params"]["p"] == 4.0
    assert by["coherence", "Bar"]["params"]["nperseg"] == 128


def test_list_presets_one_kind(monkeypatch, tmp_path, capsys):
    """``--list-presets spectral`` prints only that kind's presets."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    rc = report_cli.main(["--list-presets", "spectral"])
    out = capsys.readouterr()
    assert rc == 0
    body = json.loads(out.out)
    assert body["count"] == 1
    assert [p["kind"] for p in body["presets"]] == ["spectral"]
    assert body["presets"][0]["name"] == "Foo"


def test_list_presets_unknown_kind_exit_two(monkeypatch, tmp_path, capsys):
    """Asking for an unknown kind from ``--list-presets`` exits 2."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    rc = report_cli.main(["--list-presets", "bogus"])
    out = capsys.readouterr()
    assert rc == 2
    assert "unknown report kind" in out.err


def test_run_merges_preset_into_params(monkeypatch, tmp_path, capsys):
    """``--preset KIND:NAME`` merges the preset snapshot into run params."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    captured = {}

    def fake(verts, artifact, o, **kw):
        captured["params"] = kw["params"]
        return {"spectral": str(Path(o) / "spectral.html")}

    monkeypatch.setattr(report_cli, "run_report_bundle", fake)
    rc = report_cli.main(["--preset", "spectral:Foo", _input(tmp_path)])
    out = capsys.readouterr()
    assert rc == 0
    manifest = json.loads(out.out)
    assert manifest["reports"] == {"spectral": "spectral.html"}
    assert captured["params"]["spectral"]["k"] == 3
    assert captured["params"]["spectral"]["p"] == 4.0


def test_run_preset_overridden_by_params(monkeypatch, tmp_path, capsys):
    """A raw ``--params`` overlay overrides a preset's same-kind values."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    params_file = tmp_path / "params.json"
    params_file.write_text(json.dumps({"spectral": {"k": 7}}), encoding="utf-8")
    captured = {}

    def fake(verts, artifact, o, **kw):
        captured["params"] = kw["params"]
        return {"spectral": str(Path(o) / "spectral.html")}

    monkeypatch.setattr(report_cli, "run_report_bundle", fake)
    rc = report_cli.main(["--preset", "spectral:Foo",
                          "-p", str(params_file), _input(tmp_path)])
    capsys.readouterr()
    assert rc == 0
    assert captured["params"]["spectral"]["k"] == 7
    assert captured["params"]["spectral"]["p"] == 4.0


def test_run_multiple_presets_distinct_kinds(monkeypatch, tmp_path, capsys):
    """Repeatable ``--preset`` seeds each named kind independently."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    captured = {}

    def fake(verts, artifact, o, **kw):
        captured["params"] = kw["params"]
        return {"spectral": str(Path(o) / "spectral.html")}

    monkeypatch.setattr(report_cli, "run_report_bundle", fake)
    rc = report_cli.main(["--preset", "spectral:Foo", "--preset", "coherence:Bar",
                          _input(tmp_path)])
    capsys.readouterr()
    assert rc == 0
    assert captured["params"]["spectral"]["k"] == 3
    assert captured["params"]["coherence"]["k"] == 2
    assert captured["params"]["coherence"]["nperseg"] == 128


def test_preset_missing_exit_two(monkeypatch, tmp_path, capsys):
    """A ``KIND:NAME`` that names no stored preset exits 2."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    rc = report_cli.main(["--preset", "spectral:Missing", _input(tmp_path)])
    out = capsys.readouterr()
    assert rc == 2
    assert "unknown preset" in out.err


def test_preset_unknown_kind_exit_two(monkeypatch, tmp_path, capsys):
    """A ``--preset`` naming an unknown report kind exits 2."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    rc = report_cli.main(["--preset", "bogus:name", _input(tmp_path)])
    out = capsys.readouterr()
    assert rc == 2
    assert "unknown report kind" in out.err


def test_preset_bad_format_exit_two(monkeypatch, tmp_path, capsys):
    """A malformed ``--preset`` (no ``:``) exits 2."""
    path, _ = _pad_preset(tmp_path)
    monkeypatch.setattr(report_cli, "default_preset_path", lambda: str(path))
    rc = report_cli.main(["--preset", "spectralFoo", _input(tmp_path)])
    out = capsys.readouterr()
    assert rc == 2
    assert "bad --preset" in out.err
