"""R68 tests: Named parameter presets for the Analysis report family.

R67 added a per-kind parameter schema (``report_params`` / ``default_params`` /
``normalize_params``) and a GUI dialog, but every report still started from the
built-in defaults — a user's tuned snapshot could not be recalled. R68 introduces
``default_preset_path`` and ``PresetStore`` in ``fv.gui.analysis``: a named
preset store keyed by ``{kind: {name: normalized_params}}`` that can be persisted
to a JSON file (``~/.flowviewer/analysis_presets.json``) or held in memory when
``path=None`` (useful for tests and headless use).

These tests cover the preset CRUD lifecycle (save/load/delete/names/kinds/clear),
the normalisation-and-guard rules (unknown kind raises, unknown keys dropped,
invalid snapshots load as ``None``) and JSON persistence (file written on save,
reloaded by a fresh store, malformed file falling back to empty).

Pure NumPy/pathlib, headless — no display, no PyQt widgets are instantiated.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fv.gui.analysis import (
    PresetStore,
    default_params,
    default_preset_path,
    normalize_params,
)


def test_default_preset_path_is_home_dotflowviewer():
    expected = Path.home() / ".flowviewer" / "analysis_presets.json"
    assert default_preset_path() == expected
    assert default_preset_path().is_absolute()


def test_preset_store_memory_mode_no_path():
    assert PresetStore().path is None
    assert PresetStore(path=None).path is None


def test_preset_store_path_is_pathlib_path():
    p = PresetStore(path="x.json")
    assert isinstance(p.path, Path)
    assert str(p.path) == "x.json"


def test_save_normalizes_and_roundtrips():
    store = PresetStore()
    d = default_params("spectral")
    snap = store.save("spectral", "my preset", dict(d, k=9, bogus=123))
    assert snap == normalize_params("spectral", dict(d, k=9, bogus=123))
    assert "bogus" not in snap
    assert snap["k"] == 9
    assert store.load("spectral", "my preset") == snap


def test_save_unknown_kind_raises():
    with pytest.raises(ValueError):
        PresetStore().save("nope", "x", {})


def test_load_missing_kind_and_name():
    store = PresetStore()
    assert store.load("spectral", "nope") is None
    store.save("spectral", "keep", default_params("spectral"))
    assert store.load("coherence", "keep") is None


def test_load_invalid_snapshot_returns_none():
    store = PresetStore()
    store._data = {"spectral": {"bad": ["not", "a", "dict"]}}
    assert store.load("spectral", "bad") is None
    store._data = {"spectral": {"none": None}}
    assert store.load("spectral", "none") is None


def test_delete_returns_presence_and_cleans_bucket():
    store = PresetStore()
    assert store.delete("spectral", "x") is False
    store.save("spectral", "keep", default_params("spectral"))
    assert store.delete("spectral", "keep") is True
    assert store.load("spectral", "keep") is None
    assert store.names("spectral") == []
    assert "spectral" not in store.kinds()
    assert store.delete("spectral", "keep") is False


def test_names_sorted():
    store = PresetStore()
    for name in ("zeta", "alpha", "mid"):
        store.save("spectral", name, default_params("spectral"))
    assert store.names("spectral") == ["alpha", "mid", "zeta"]


def test_kinds_sorted_nonempty_only():
    store = PresetStore()
    assert store.kinds() == []
    store.save("coherence", "c", default_params("coherence"))
    store.save("evolution", "e", default_params("evolution"))
    assert store.kinds() == ["coherence", "evolution"]


def test_clear_empties():
    store = PresetStore()
    store.save("spectral", "a", default_params("spectral"))
    store.save("console", "b", default_params("console"))
    store.clear()
    assert store.kinds() == []
    assert store.load("spectral", "a") is None


def test_persists_to_file_and_reloads(tmp_path):
    p = tmp_path / "sub" / "presets.json"
    store = PresetStore(path=p)
    assert not p.exists()
    store.save("spectral", "keep", default_params("spectral"))
    assert p.exists()

    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert set(loaded) == {"spectral"}
    assert "keep" in loaded["spectral"]

    fresh = PresetStore(path=p)
    assert fresh.load("spectral", "keep") == store.load("spectral", "keep")


def test_persist_creates_parent_dir(tmp_path):
    p = tmp_path / "a" / "b" / "presets.json"
    PresetStore(path=p).save("spectral", "x", default_params("spectral"))
    assert p.parent.is_dir() and p.exists()


def test_memory_store_does_not_touch_disk(tmp_path):
    p = tmp_path / "presets.json"
    store = PresetStore()
    store.save("spectral", "x", default_params("spectral"))
    assert not p.exists()
    assert store._path is None


def test_reload_malformed_file_falls_back_to_empty(tmp_path):
    p = tmp_path / "presets.json"
    p.write_text("{ not json", encoding="utf-8")
    assert PresetStore(path=p).kinds() == []
