"""R121: a saved session must restore the scene-wide objects too.

Two gaps: save_status wrote only main_object.children, and the global objects
(camera pose and keyframes, light, Draw Window settings, global
colorbar/gradation) live outside children -- so a carefully framed session
saved and restored none of it; and the GUI could write a .sta but had no way
to read one back (load_status was reachable only from the script/COM facade).
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fv.model import objects as O  # noqa: E402
from fv.render.export import (  # noqa: E402
    instantiate_globals,
    load_status,
    load_status_document,
    save_status,
)


def _document() -> tuple:
    main = O.MainObject("x.fph", "x.fph")
    plane = O.PlaneObject()
    plane.coordinate = 0.25
    main.children = [plane]
    camera = O.CameraObject(index=1)
    camera.position = (1.0, 2.0, 3.0)
    light = O.LightObject(index=1)
    light.brightness = 0.5
    globals_ = {
        "camera": camera,
        "light": light,
        "draw_window": O.DrawWindowObject(index=1),
        "colorbar": O.ColorbarObject(index=1),
        "gradation": O.GradationObject(index=1),
    }
    return main, globals_


def test_children_still_round_trip(tmp_path):
    """The pre-existing contract must not regress."""
    main, _ = _document()
    path = tmp_path / "s.sta"
    assert save_status(main, str(path)) is True
    restored = load_status(str(path))
    assert restored is not None and len(restored) == 1
    assert restored[0].kind == "plane"
    assert restored[0].coordinate == pytest.approx(0.25)


def test_global_objects_are_persisted(tmp_path):
    """They live outside children, so they used to vanish entirely."""
    main, globals_ = _document()
    path = tmp_path / "s.sta"
    assert save_status(main, str(path), global_objects=globals_) is True
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] >= 2
    assert set(raw["globals"]) == set(globals_)


def test_global_objects_restore_field_by_field(tmp_path):
    main, globals_ = _document()
    path = tmp_path / "s.sta"
    save_status(main, str(path), global_objects=globals_)
    doc = load_status_document(str(path))
    assert doc is not None
    restored = instantiate_globals(doc["globals"])
    assert set(restored) == set(globals_)
    assert restored["camera"].position == (1.0, 2.0, 3.0)
    assert restored["light"].brightness == pytest.approx(0.5)
    assert restored["camera"].kind == "camera"


def test_a_version_1_file_still_loads(tmp_path):
    """Older status files have no globals section at all."""
    main, globals_ = _document()
    path = tmp_path / "s.sta"
    save_status(main, str(path), global_objects=globals_)
    raw = json.loads(path.read_text(encoding="utf-8"))
    legacy = tmp_path / "legacy.sta"
    legacy.write_text(json.dumps({
        "format": "flowviewer-sta",
        "version": 1,
        "display_name": raw["display_name"],
        "children": raw["children"],
    }), encoding="utf-8")
    doc = load_status_document(str(legacy))
    assert doc is not None
    assert doc["globals"] == {}
    assert len(doc["children"]) == 1
    assert instantiate_globals(doc["globals"]) == {}


def test_unknown_globals_are_skipped_not_fatal(tmp_path):
    """A newer writer must not break an older reader."""
    main, globals_ = _document()
    path = tmp_path / "s.sta"
    save_status(main, str(path), global_objects=globals_)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["globals"]["future_thing"] = {"kind": "future"}
    path.write_text(json.dumps(raw), encoding="utf-8")
    doc = load_status_document(str(path))
    restored = instantiate_globals(doc["globals"])
    assert "future_thing" not in restored
    assert "camera" in restored


def test_not_a_status_file_is_rejected(tmp_path):
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"hello": 1}), encoding="utf-8")
    assert load_status_document(str(path)) is None
    assert load_status(str(path)) is None
    assert load_status_document(str(tmp_path / "missing.sta")) is None


def test_gui_exposes_a_load_status_entry():
    """Saving without a way to load was the second half of the defect."""
    src = Path(__file__).resolve().parents[1] / "fv" / "gui" / "main.py"
    text = src.read_text(encoding="utf-8-sig")
    assert "def on_load_status" in text
    assert '"Load Status"' in text
    # and it must actually restore globals, not just the children
    assert "instantiate_globals" in text
    assert "global_objects=self._global_objects()" in text
