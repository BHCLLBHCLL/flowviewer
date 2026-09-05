"""R73 tests: named Analysis batch projects (save / run / delete).

R68-R70 persisted per-kind parameter presets and let the user run a saved
single-report config; R71/R72 run the whole batch and pack it. R73 adds a
``ProjectStore`` that captures *which* report kinds a batch should run plus the
per-kind parameter snapshots to feed them, so a tuned subset can be saved and
re-run in one click from the Analysis menu. Pure stdlib/pathlib, headless.
"""

from __future__ import annotations

from fv.gui import analysis


def test_project_store_path_under_dot_flowviewer(tmp_path):
    path = analysis.project_store_path()
    assert path.name == "analysis_projects.json"
    assert ".flowviewer" in path.parts


def test_names_empty_initially():
    store = analysis.ProjectStore()
    assert store.names() == []


def test_save_get_round_trip():
    store = analysis.ProjectStore()
    store.save("demo", ["spectral", "coherence"], {})
    proj = store.get("demo")
    assert proj["kinds"] == ["spectral", "coherence"]
    assert "spectral" in proj["params"]


def test_get_returns_deep_copy():
    store = analysis.ProjectStore()
    store.save("demo", ["spectral"], {"spectral": {"frames": 3}})
    proj = store.get("demo")
    proj["params"]["spectral"]["frames"] = 99
    assert store.get("demo")["params"]["spectral"]["frames"] == 3


def test_save_drops_unknown_kinds():
    store = analysis.ProjectStore()
    proj = store.save("demo", ["spectral", "bogus"], {})
    assert proj["kinds"] == ["spectral"]


def test_save_no_valid_kinds_raises():
    store = analysis.ProjectStore()
    try:
        store.save("bad", ["nope", "also_nope"], {})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for no valid kinds")


def test_save_normalises_params():
    store = analysis.ProjectStore()
    proj = store.save("demo", ["spectral"],
                      {"spectral": {"frames": "7", "bogus": 99}})
    assert proj["params"]["spectral"]["frames"] == 7
    assert "bogus" not in proj["params"]["spectral"]


def test_save_prunes_params_to_kinds():
    store = analysis.ProjectStore()
    proj = store.save("demo", ["spectral"],
                      {"spectral": {"frames": 3}, "coherence": {"ref_probe": 2}})
    assert "coherence" not in proj["params"]


def test_delete_present_and_absent():
    store = analysis.ProjectStore()
    store.save("demo", ["spectral"], {})
    assert store.delete("demo") is True
    assert store.delete("demo") is False
    assert store.names() == []


def test_clear_empties():
    store = analysis.ProjectStore()
    store.save("a", ["spectral"], {})
    store.save("b", ["coherence"], {})
    store.clear()
    assert store.names() == []


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "projects.json"
    store = analysis.ProjectStore(path=path)
    store.save("demo", ["spectral"], {"spectral": {"frames": 5}})
    reloaded = analysis.ProjectStore(path=path)
    assert reloaded.names() == ["demo"]
    assert reloaded.get("demo")["params"]["spectral"]["frames"] == 5


def test_project_menu_lists_with_kinds():
    store = analysis.ProjectStore()
    store.save("b", ["spectral"], {})
    store.save("a", ["coherence", "evolution"], {})
    menu = analysis.project_menu(store)
    assert [name for name, _kinds in menu] == ["a", "b"]
    assert menu[0][1] == ["coherence", "evolution"]


def test_run_project_missing_returns_none():
    store = analysis.ProjectStore()
    assert analysis.run_project(store, "nope", "V", "A", "out") is None


def test_run_project_dispatches_project(monkeypatch, tmp_path):
    store = analysis.ProjectStore()
    store.save("demo", ["spectral"], {"spectral": {"frames": 3}})
    seen = {}

    def fake(kind, verts, artifact, out_dir, **kw):
        seen[kind] = kw
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    out = analysis.run_project(store, "demo", "V", "A", str(tmp_path))
    assert list(seen.keys()) == ["spectral"]
    assert seen["spectral"]["frames"] == 3
    assert out == {"spectral": "spectral.html"}
    assert (tmp_path / "index.html").is_file()


def test_run_project_dt_fallback(monkeypatch, tmp_path):
    store = analysis.ProjectStore()
    store.save("demo", ["spectral"], {"spectral": {"dt": None, "frames": 2}})
    seen = {}

    def fake(kind, verts, artifact, out_dir, **kw):
        seen[kind] = kw
        return f"{kind}.html"

    monkeypatch.setattr(analysis, "run_report", fake)
    analysis.run_project(store, "demo", "V", "A", str(tmp_path), dt=0.25)
    assert seen["spectral"]["dt"] == 0.25
