"""R35 tests: generic object-keyframe Timeline engine + Scene wiring.

These are headless-safe and have *no* h5py/CGNS dependency: the engine is
pure computation, and Scene.animate applies a Timeline before any field-file
guard (object-keyframe-only animation works without a dataset).  Rendering
writes PNGs only when VTK actually renders; the JSON + manifest contract is
asserted regardless.
"""

from __future__ import annotations

import json

import pytest
from fv.render.scene import Scene
from fv.timeline import (
    INTERP_HOLD,
    INTERP_LINEAR,
    INTERP_SPLINE,
    KeyframeTrack,
    Timeline,
    normalize_time,
    render_timeline,
)


class _Box:
    """Minimal stand-in object with the props the timeline drives."""

    def __init__(self):
        self.position = (0.0, 0.0, 0.0)
        self.opacity = 1.0
        self.visible = True


# ── engine primitives ──────────────────────────────────────────────────────

def test_normalize_time_loop_and_clamp():
    assert normalize_time(3.5, 4.0, True) == pytest.approx(3.5)
    assert normalize_time(7.0, 4.0, True) == pytest.approx(3.0)
    assert normalize_time(9.0, 4.0, True) == pytest.approx(1.0)
    assert normalize_time(5.0, 4.0, False) == pytest.approx(4.0)
    assert normalize_time(0.0, 0.0, True) == 0.0


def test_track_duration_and_count():
    tr = KeyframeTrack(_Box(), "opacity", {0.0: 0.0, 1.0: 1.0, 2.0: 0.0})
    assert tr.duration() == 2.0
    assert tr.count() == 3


def test_hold_interpolation():
    box = _Box()
    tr = KeyframeTrack(box, "opacity", {0.0: 0.2, 1.0: 0.9},
                       interp=INTERP_HOLD, loop=False)
    assert tr.evaluate(-1) == 0.2  # clamped to start
    assert tr.evaluate(0.5) == 0.2
    assert tr.evaluate(1.0) == pytest.approx(0.9)
    assert tr.evaluate(5.0) == pytest.approx(0.9)  # clamped to end keyframe


def test_linear_scalar_and_bounds():
    tr = KeyframeTrack(_Box(), "opacity", {0.0: 0.0, 2.0: 1.0},
                       interp=INTERP_LINEAR, loop=False)
    assert tr.evaluate(0.0) == pytest.approx(0.0)
    assert tr.evaluate(1.0) == pytest.approx(0.5)
    assert tr.evaluate(2.0) == pytest.approx(1.0)
    assert tr.evaluate(10.0) == pytest.approx(1.0)  # clamped to end


def test_linear_vec3_memberwise():
    tr = KeyframeTrack(_Box(), "position",
                       {0.0: (0, 0, 0), 1.0: (10, 20, 30)},
                       interp=INTERP_LINEAR)
    v = tr.evaluate(0.5)
    assert v == pytest.approx((5.0, 10.0, 15.0))


def test_spline_vec3_passes_through_keyframes():
    # Catmull-Rom through every keyframe for >= 3 vec3 controls.
    kfs = {0.0: (0.0, 0.0, 0.0),
           1.0: (0.0, 10.0, 0.0),
           2.0: (10.0, 10.0, 0.0),
           3.0: (10.0, 0.0, 0.0)}
    tr = KeyframeTrack(_Box(), "position", kfs, interp=INTERP_SPLINE,
                       loop=False)
    for t, coord in kfs.items():
        v = tr.evaluate(t)
        assert v[0] == pytest.approx(coord[0], abs=1e-6)
        assert v[1] == pytest.approx(coord[1], abs=1e-6)


# ── Timeline container ──────────────────────────────────────────────────────

def test_timeline_duration_and_keys_dedup():
    box = _Box()
    tl = Timeline()
    tl.add_track(KeyframeTrack(box, "opacity", {0.0: 0.0, 1.0: 1.0}))
    tl.add_track(KeyframeTrack(box, "position", {0.0: (0, 0, 0), 1.0: (1, 1, 1)}))
    assert tl.duration() == 1.0
    keys = tl.keys(0.5)
    by_prop = {prop: (obj, val) for obj, prop, val in keys}
    assert set(by_prop) == {"opacity", "position"}
    assert len(keys) == 2  # deduped (one record per property)


def test_timeline_apply_writes_attributes():
    box = _Box()
    tl = Timeline()
    tl.add_track(KeyframeTrack(box, "opacity", {0.0: 0.0, 1.0: 0.8}))
    tl.add_track(KeyframeTrack(box, "position",
                               {0.0: (0, 0, 0), 1.0: (2, 4, 6)}))
    tl.apply(0.5)
    assert box.opacity == pytest.approx(0.4)
    assert box.position == pytest.approx((1.0, 2.0, 3.0))


def test_timeline_apply_reflects_visibility_and_opacity():
    import vtk  # noqa: F401  (guard: ignore in test-only import)
    from vtkmodules.vtkRenderingCore import vtkActor  # type: ignore[import]

    box = _Box()
    tl = Timeline()
    vis = KeyframeTrack(box, "visible", {0.0: True, 1.0: False},
                        interp=INTERP_HOLD, loop=False)
    op = KeyframeTrack(box, "opacity", {0.0: 1.0, 1.0: 0.25},
                       loop=False)
    actor = vtkActor()
    actor.SetVisibility(1)
    actor.GetProperty().SetOpacity(1.0)
    vis.attach_actor(actor)
    op.attach_actor(actor)
    tl.add_track(vis)
    tl.add_track(op)
    tl.apply(1.0)
    assert actor.GetVisibility() == 0
    assert actor.GetProperty().GetOpacity() == pytest.approx(0.25)


# ── Scene wiring (headless: no field file) ─────────────────────────────────

def test_scene_animate_drives_timeline_without_field_file():
    box = _Box()
    tl = Timeline()
    tl.add_track(KeyframeTrack(box, "position",
                               {0.0: (0, 0, 0), 1.0: (5, 5, 5)}))
    scene = Scene(enable_3d=False)
    scene.set_timeline(tl)
    scene.animate(0.5)  # field_file is None → still applies the timeline
    assert box.position == pytest.approx((2.5, 2.5, 2.5))


# ── render_timeline pipeline ───────────────────────────────────────────────

def test_render_timeline_writes_manifest_and_json(tmp_path):
    box = _Box()
    tl = Timeline()
    tl.add_track(KeyframeTrack(box, "opacity", {0.0: 0.0, 1.0: 1.0}))
    out = tmp_path / "tl"
    manifest = render_timeline(tl, renderer=None, n_frames=5,
                               out_dir=str(out), base="kf", loop=False)
    assert manifest["timeline"]["n_tracks"] == 1
    assert manifest["timeline"]["duration"] == 1.0
    assert manifest["timeline"]["n_frames"] == 5
    assert len(manifest["frames"]) == 5
    for i in range(5):
        jf = out / f"kf_{i:04d}.json"
        assert jf.exists()
        data = json.loads(jf.read_text())
        assert data["n_tracks"] == 1
        assert "values" in data and "opacity" in data["values"]
    # png available only when a renderer actually renders
    assert manifest["png_frames"] == 0  # renderer=None → no PNGs
    assert (out / "manifest.json").exists()


def test_render_timeline_values_span_keyframe_range(tmp_path):
    box = _Box()
    tl = Timeline()
    tl.add_track(KeyframeTrack(box, "opacity", {0.0: 0.0, 1.0: 1.0},
                               loop=False))
    out = tmp_path / "tl2"
    render_timeline(tl, renderer=None, n_frames=3, out_dir=str(out), base="kf",
                    loop=False)
    first = json.loads((out / "kf_0000.json").read_text())
    last = json.loads((out / "kf_0002.json").read_text())
    assert first["values"]["opacity"] == pytest.approx(0.0)
    assert last["values"]["opacity"] == pytest.approx(1.0)
