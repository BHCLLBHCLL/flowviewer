"""R70 tests: Sharing named analysis presets (export / import).

R68 keeps a per-user preset file and R69 runs a preset from the Analysis menu,
but a preset could not leave the machine: there was no way to export the tuning
to a file (share with a colleague / back it up) or import one back into the
store. R70 adds ``PresetStore.dump``/``export``/``import_`` plus the module-level
``export_presets``/``import_presets``: ``export`` writes a deep JSON snapshot of
the store (optionally filtered by kind) and ``import_`` loads a JSON file/object
into the store, merging with a configurable overwrite and skipping unknown
kinds / malformed entries. Pure pathlib/json, headless.
"""

from __future__ import annotations

import json

import pytest
from fv.gui.analysis import (
    PresetStore,
    default_params,
    export_presets,
    import_presets,
)


def test_dump_empty_store():
    assert PresetStore().dump() == {}


def test_dump_filters_by_kind():
    st = PresetStore()
    st.save("spectral", "a", default_params("spectral"))
    st.save("coherence", "b", default_params("coherence"))
    only = st.dump(["spectral"])
    assert list(only.keys()) == ["spectral"]
    assert "coherence" not in only
    assert set(only["spectral"].keys()) == {"a"}


def test_dump_is_deep_copy():
    st = PresetStore()
    st.save("spatial_pod", "a", default_params("spatial_pod"))
    snap = st.dump()
    snap["spatial_pod"]["a"]["top"] = 999
    assert st.load("spatial_pod", "a")["top"] == 5


def test_export_writes_json_and_returns_path(tmp_path):
    st = PresetStore()
    st.save("spatial_pod", "fast", dict(default_params("spatial_pod"), top=7))
    dest = tmp_path / "presets.json"
    out = export_presets(st, dest)
    assert out == dest
    assert dest.is_file()
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["spatial_pod"]["fast"]["top"] == 7


def test_export_empty_returns_none(tmp_path):
    dest = tmp_path / "empty.json"
    assert export_presets(PresetStore(), dest) is None
    assert not dest.exists()


def test_export_kind_filter(tmp_path):
    st = PresetStore()
    st.save("spectral", "a", default_params("spectral"))
    st.save("coherence", "b", default_params("coherence"))
    dest = tmp_path / "only_spectral.json"
    out = export_presets(st, dest, kinds=["spectral"])
    data = json.loads(out.read_text(encoding="utf-8"))
    assert sorted(data.keys()) == ["spectral"]


def test_import_from_file(tmp_path):
    st = PresetStore()
    st.save("spectral", "src", default_params("spectral"))
    src = tmp_path / "export.json"
    export_presets(st, src)
    target = PresetStore()
    stats = import_presets(target, src)
    assert stats == {"spectral": ["src"]}
    assert target.load("spectral", "src") is not None


def test_import_from_dict():
    payload = {"coherence": {"c1": default_params("coherence")}}
    target = PresetStore()
    stats = import_presets(target, payload)
    assert stats == {"coherence": ["c1"]}
    assert target.names("coherence") == ["c1"]


def test_import_skips_existing_without_overwrite():
    st = PresetStore()
    st.save("spatial_pod", "a", dict(default_params("spatial_pod"), top=3))
    payload = {"spatial_pod": {"a": dict(default_params("spatial_pod"), top=9)}}
    stats = import_presets(st, payload)
    assert stats == {}
    assert st.load("spatial_pod", "a")["top"] == 3


def test_import_overwrite():
    st = PresetStore()
    st.save("spatial_pod", "a", dict(default_params("spatial_pod"), top=3))
    payload = {"spatial_pod": {"a": dict(default_params("spatial_pod"), top=9)}}
    stats = import_presets(st, payload, overwrite=True)
    assert stats == {"spatial_pod": ["a"]}
    assert st.load("spatial_pod", "a")["top"] == 9


def test_import_skips_malformed():
    st = PresetStore()
    payload = {
        "spectral": {"good": default_params("spectral")},
        "bogus_kind": {"x": default_params("spectral")},
        "coherence": {"valid": default_params("coherence"), "bad": "not-a-dict"},
    }
    stats = import_presets(st, payload)
    assert stats == {"spectral": ["good"], "coherence": ["valid"]}
    assert st.names("spectral") == ["good"]
    assert st.names("coherence") == ["valid"]


def test_import_kind_filter():
    st = PresetStore()
    payload = {
        "spectral": {"a": default_params("spectral")},
        "coherence": {"b": default_params("coherence")},
    }
    stats = import_presets(st, payload, kinds=["spectral"])
    assert stats == {"spectral": ["a"]}
    assert st.names("coherence") == []


def test_import_invalid_source_raises():
    st = PresetStore()
    with pytest.raises(ValueError):
        import_presets(st, [1, 2, 3])
    with pytest.raises(ValueError):
        import_presets(st, 42)


def test_import_invalid_json_file_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        import_presets(PresetStore(), bad)
