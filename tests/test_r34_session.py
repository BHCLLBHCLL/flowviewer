"""R34 - session recording / sequence render pipeline (section 9.14).

SessionTimeline walks a CGNS cycle sequence (scan_sequence) yielding each
cycle's streaming handle one at a time (open/consume/release, bounded memory);
SessionRecorder writes per-cycle PNG (coarse, honestly False headless) + JSON
sample window + manifest.json. record_sequence / encode_video / CLI wrap it.
All data paths are headless-safe; non-stream defaults stay unchanged.
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("h5py")

# reuse the R28 synthetic two-zone CGNS builder
from test_r28_lazy import _make_two_zone  # noqa: E402,F401


@pytest.fixture
def seq(tmp_path):
    """A 3-cycle CGNS sequence (suffix _1/_2/_3) + the first-file path."""
    paths = []
    for c in (1, 2, 3):
        p = str(tmp_path / f"seq_{c}.cgns")
        _make_two_zone(p)
        paths.append(p)
    return paths


def _first_field(path):
    from fv.model.dataset import open_stream_cgns
    handle, _ = open_stream_cgns(path, budget_bytes=1 << 22)
    name = sorted(handle.field_names())[0]
    return name, handle.field_len(name)


def test_timeline_cycles_sorted_and_iterable(seq):
    from fv.session import SessionTimeline
    tl = SessionTimeline.from_sequence(seq[0], budget_mb=4)
    assert tl.count == len(seq)
    assert tl.cycles() == [1, 2, 3]           # sorted by trailing cycle
    seen = [cyc for cyc, _h, _m in tl]
    assert seen == [1, 2, 3]


def test_recorder_frames_manifest_json_match(seq, tmp_path):
    """Per-cycle JSON sample equals that cycle's streamed window; manifest ok."""
    from fv.session import SessionRecorder, SessionTimeline
    tl = SessionTimeline(seq, budget_mb=4)
    rec = SessionRecorder(tl, out_dir=str(tmp_path / "out"), render=False,
                          window_len=16)
    manifest = rec.run()
    assert len(manifest["frames"]) == len(seq)
    assert manifest["job"]["timeline"] == seq
    for frame, cyc, path in zip(manifest["frames"], tl.cycles(), seq):
        assert frame["cycle"] == cyc
        name, total = _first_field(path)
        jsons = [f for f in frame["files"] if f["kind"] == "json"
                 and f["field"] == name]
        assert jsons, f"no json for {name} on cycle {cyc}"
        jf = jsons[0]
        payload = json.loads((tmp_path / "out" / jf["name"]).read_text("utf-8"))
        assert payload["n"] == min(total, 16) and payload["total"] == total
        from fv.model.dataset import open_stream_cgns
        handle, _ = open_stream_cgns(path, budget_bytes=1 << 22)
        _, ref = handle.read_window(name, 0, min(total, 16))
        assert np.allclose(np.asarray(payload["values"]), ref, equal_nan=True)


def test_recorder_render_optional(seq, tmp_path):
    """render=False never attempts a scene; render=True is honest headless."""
    from fv.session import SessionRecorder, SessionTimeline
    tl = SessionTimeline(seq, budget_mb=4)
    rec = SessionRecorder(tl, out_dir=str(tmp_path / "no"), render=False)
    m = rec.run()
    assert all(not any(f["kind"] == "png" for f in fr["files"])
               for fr in m["frames"])
    rec2 = SessionRecorder(tl, out_dir=str(tmp_path / "yes"), render=True)
    m2 = rec2.run()
    for fr in m2["frames"]:
        pngs = [f for f in fr["files"] if f["kind"] == "png"]
        assert pngs
        ok = pngs[0]["ok"]
        assert ok is (os.environ.get("QT_QPA_PLATFORM") != "offscreen")


def test_record_sequence_convenience(seq, tmp_path):
    """record_sequence accepts a list; writes frames + manifest."""
    from fv.session import record_sequence
    manifest = record_sequence(seq, out_dir=str(tmp_path / "s"),
                               render=False)
    assert (tmp_path / "s" / "manifest.json").exists()
    assert len(manifest["frames"]) == len(seq)


def test_encode_video_missing_ffmpeg_returns_zero(seq, tmp_path):
    """Without ffmpeg the encoder honestly returns 0 (no exception)."""
    from fv.session import encode_video
    # build a couple of dummy frames first
    rec_dir = tmp_path / "f"
    rec_dir.mkdir(exist_ok=True)
    for i in range(2):
        (rec_dir / f"frame_{i:04d}.png").write_bytes(b"x")
    n = encode_video(str(rec_dir), str(tmp_path / "v.ogv"),
                     ffmpeg="definitely-not-ffmpeg-xyz")
    assert n == 0


def test_session_cli_produces_manifest(seq, tmp_path):
    from fv.session import main
    assert main([seq[0], "--out", str(tmp_path / "cli"),
                 "--no-render"]) == 0
    assert (tmp_path / "cli" / "manifest.json").exists()


def test_gui_record_sequence_action_present(seq, _qapp):
    """File > Record Sequence… is wired (no dialog opened headless)."""
    from fv.gui.main import FlowViewer
    w = FlowViewer(filepath=None, enable_3d=True)
    try:
        assert hasattr(w, "on_record_sequence") and callable(w.on_record_sequence)
    finally:
        w.close()


@pytest.fixture
def _qapp():
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt5 unavailable")
    return QApplication.instance() or QApplication([])
