"""R78 tests: analysis projects carry (and re-materialise) their own source.

R73 projects store ``{kinds, params}`` but not the Analysis data source, so
re-running a saved batch means manually re-establishing a Time Series, an
imported JSON, or a sequence source. R78 makes projects self-contained: a save
also records a JSON-serialisable data-source descriptor (sequence or imported
JSON), and ``resolve_source`` rebuilds ``(verts, artifact)`` from that descriptor
when the project is run — degrading gracefully to the live source when the
descriptor is absent (a Time Series), unknown, or unreadable.

Pure stdlib + numpy, headless; ``resolve_source`` is checked by monkeypatching
the underlying pure builders so no Qt / CGNS / streaming is exercised.
"""

from __future__ import annotations

import json

import numpy as np
from fv.gui import analysis as gui_analysis


def test_sequence_desc_single_path():
    desc = gui_analysis.sequence_desc(
        "seq", [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)],
        field="Pressure", budget_mb=16)
    assert desc == {
        "type": "sequence",
        "paths": "seq",
        "probes": [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
        "field": "Pressure",
        "budget_mb": 16,
    }


def test_sequence_desc_list_paths_keeps_list():
    desc = gui_analysis.sequence_desc(["a.cgns", "b.cgns"], [(0, 0, 0)])
    assert desc["paths"] == ["a.cgns", "b.cgns"]
    assert desc["budget_mb"] == 64


def test_sequence_desc_is_json_serialisable():
    desc = gui_analysis.sequence_desc("seq", [(0.0, 0.0, 0.0)])
    assert json.loads(json.dumps(desc)) == desc


def test_json_desc():
    assert gui_analysis.json_desc("/x/in.json") == {"type": "json",
                                                    "path": "/x/in.json"}


def test_resolve_source_none_returns_current():
    current = (np.zeros((2, 3)), {"name": "T", "cycles": [0], "probes": []})
    verts, artifact = gui_analysis.resolve_source(None, current=current)
    assert verts is current[0]
    assert artifact is current[1]


def test_resolve_source_no_current_returns_none():
    assert gui_analysis.resolve_source(None) == (None, None)


def test_resolve_source_timeseries_returns_current():
    current = (None, {"name": "T", "cycles": [0], "probes": []})
    result = gui_analysis.resolve_source({"type": "timeseries"}, current=current)
    assert result == current


def test_resolve_source_unknown_type_returns_current():
    current = (None, {})
    assert gui_analysis.resolve_source({"type": "mystery"}, current=current) == current


def test_resolve_source_non_dict_returns_current():
    current = (None, {"name": "T"})
    assert gui_analysis.resolve_source("nope", current=current) == current


def test_resolve_source_json_calls_load(monkeypatch):
    seen = {}

    def fake_load(path):
        seen["path"] = path
        return np.zeros((3, 3)), {"name": "J", "cycles": [0, 1], "probes": []}

    monkeypatch.setattr("fv.gui.analysis.load_analysis_source", fake_load)
    verts, artifact = gui_analysis.resolve_source(
        {"type": "json", "path": "in.json"})
    assert seen["path"] == "in.json"
    assert artifact == {"name": "J", "cycles": [0, 1], "probes": []}


def test_resolve_source_sequence_calls_sequence_source(monkeypatch):
    seen = {}

    def fake_seq(paths, probes, **kw):
        seen["paths"] = paths
        seen["probes"] = probes
        seen["kw"] = kw
        return np.zeros((2, 3)), {"name": "S", "cycles": [0], "probes": []}

    monkeypatch.setattr("fv.gui.analysis.sequence_source", fake_seq)
    desc = gui_analysis.sequence_desc(
        "seq", [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)],
        field="Pressure", budget_mb=32)
    verts, artifact = gui_analysis.resolve_source(desc)
    assert seen["paths"] == "seq"
    assert seen["probes"] == [(0.0, 0.0, 0.0), (1.0, 2.0, 3.0)]
    assert seen["kw"]["field"] == "Pressure"
    assert seen["kw"]["budget_mb"] == 32
    assert artifact["name"] == "S"


def test_project_save_stores_source():
    store = gui_analysis.ProjectStore()
    src = gui_analysis.json_desc("in.json")
    store.save("demo", ["spectral"], {}, source=src)
    assert store.get("demo")["source"] == src


def test_project_save_without_source_stays_none():
    store = gui_analysis.ProjectStore()
    store.save("demo", ["spectral"], {})
    assert store.get("demo").get("source") is None


def test_project_get_deep_copies_source():
    store = gui_analysis.ProjectStore()
    store.save("demo", ["spectral"], {},
               source=gui_analysis.json_desc("in.json"))
    got = store.get("demo")
    got["source"]["path"] = "mutated"
    assert store.get("demo")["source"]["path"] == "in.json"


def test_project_self_contained_run_resolves_json(tmp_path, monkeypatch):
    """A project carrying a JSON recipe rebuilds its source then runs."""
    in_json = tmp_path / "in.json"
    in_json.write_text(
        json.dumps({"verts": [[0, 0, 0], [1, 0, 0]],
                    "artifact": {"name": "T", "cycles": [0, 1], "probes": []}}),
        encoding="utf-8")
    store = gui_analysis.ProjectStore()
    store.save("demo", ["spectral"], {},
               source=gui_analysis.json_desc(str(in_json)))
    project = store.get("demo")
    verts, artifact = gui_analysis.resolve_source(project["source"])
    assert verts.shape == (2, 3)
    assert artifact["name"] == "T"

    called = {}

    def fake_bundle(v, a, out, *, kinds=None, params=None, dt=None):
        called["kinds"] = kinds
        return {"spectral": "s.html"}

    monkeypatch.setattr(gui_analysis, "run_report_bundle", fake_bundle)
    out = gui_analysis.run_project(store, "demo", verts, artifact,
                                   str(tmp_path), dt=None)
    assert called["kinds"] == ["spectral"]
    assert out == {"spectral": "s.html"}
