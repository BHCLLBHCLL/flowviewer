"""R69 tests: Running Analysis reports from saved presets.

R68 let the user save a tuned parameter snapshot as a named preset, but the
Analysis menu's report entries still started from the in-memory ``_analysis_params``
— a saved preset could not be run directly. R69 adds ``preset_menu`` and
``run_preset`` in ``fv.gui.analysis``: ``preset_menu`` lists the runnable
``(kind, name, title)`` triples, and ``run_preset`` loads a named snapshot and
forwards it verbatim to :func:`run_report` (falling back to a supplied ``dt``
when the snapshot's is ``None``).

These tests keep report generation out of scope by monkeypatching
``analysis.run_report`` with a recorder, so they exercise only the
listing/loading/forwarding logic. Pure NumPy/pathlib, headless.
"""

from __future__ import annotations

import pytest
from fv.gui import analysis
from fv.gui.analysis import PresetStore, default_params, preset_menu, run_preset


def test_preset_menu_empty_store():
    assert preset_menu(PresetStore()) == []


def test_preset_menu_lists_all_kinds_in_registry_order():
    st = PresetStore()
    st.save("spectral", "zz", default_params("spectral"))
    st.save("spectral", "aa", default_params("spectral"))
    st.save("coherence", "bb", default_params("coherence"))
    st.save("spatial_pod", "cc", default_params("spatial_pod"))
    items = preset_menu(st)
    assert [k for k, _n, _t in items] == [
        "spectral", "spectral", "coherence", "spatial_pod"]
    assert [n for _k, n, _t in items] == ["aa", "zz", "bb", "cc"]
    assert items[0][2] == "Spectral Field Map (R58)"


def test_preset_menu_kind_filter():
    st = PresetStore()
    st.save("spectral", "beta", default_params("spectral"))
    st.save("spectral", "alpha", default_params("spectral"))
    st.save("coherence", "c", default_params("coherence"))
    items = preset_menu(st, "spectral")
    assert [n for _k, n, _t in items] == ["alpha", "beta"]
    assert all(k == "spectral" for k, _n, _t in items)


def test_preset_menu_unknown_kind_raises():
    with pytest.raises(ValueError):
        preset_menu(PresetStore(), "nope")


def test_run_preset_missing_returns_none():
    assert run_preset("spectral", "nope", None, object(), "out") is None


def test_run_preset_forwards_snapshot_to_run_report(monkeypatch):
    calls = {}

    def fake_run_report(kind, verts, artifact, out_dir, **kw):
        calls.update(kind=kind, verts=verts, artifact=artifact,
                     out_dir=out_dir, kw=kw)
        return "report.html"

    monkeypatch.setattr(analysis, "run_report", fake_run_report)

    st = PresetStore()
    st.save("spatial_field", "pod", dict(default_params("spatial_field"),
                                         source="dmd", top=7))
    out = run_preset("spatial_field", "pod", "V", "A", "OUT", store=st)
    assert out == "report.html"
    assert calls["kind"] == "spatial_field"
    assert calls["verts"] == "V"
    assert calls["artifact"] == "A"
    assert calls["out_dir"] == "OUT"
    assert calls["kw"]["source"] == "dmd"
    assert calls["kw"]["top"] == 7


def test_run_preset_dt_fallback(monkeypatch):
    calls = {}

    def fake_run_report(kind, verts, artifact, out_dir, **kw):
        calls["kw"] = kw
        return "report.html"

    monkeypatch.setattr(analysis, "run_report", fake_run_report)

    st = PresetStore()
    d = default_params("spectral")
    d["dt"] = None
    st.save("spectral", "none", d)
    run_preset("spectral", "none", None, object(), "out", store=st, dt=0.5)
    assert calls["kw"]["dt"] == 0.5

    d2 = default_params("spectral")
    d2["dt"] = 0.125
    st.save("spectral", "kept", d2)
    run_preset("spectral", "kept", None, object(), "out", store=st, dt=0.5)
    assert calls["kw"]["dt"] == 0.125


def test_run_preset_none_artifact_returns_none(monkeypatch):
    def fake_run_report(kind, verts, artifact, out_dir, **kw):
        return None  # run_report returns None when artifact is missing

    monkeypatch.setattr(analysis, "run_report", fake_run_report)
    st = PresetStore()
    st.save("spectral", "a", default_params("spectral"))
    assert run_preset("spectral", "a", None, None, "out", store=st) is None
