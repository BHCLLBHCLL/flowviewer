"""R126 - an exported file must be the format its name promises.

Measured defect: the video writers picked their encoder from the extension
only for .avi; every other extension fell back to vtkOggTheoraWriter.  Asking
for movie.mp4 therefore wrote Ogg Theora bytes into a file called movie.mp4
and reported the frame count as a success, and the GUI dialog even said
"encode MP4/AVI via ffmpeg" while calling a path that never used ffmpeg.  On
this VTK build (9.6.2) vtkAVIWriter does not exist either, so .avi was wrong
in the same way, and ffmpeg is not on PATH, so .mp4 could not be produced at
all -- the honest answer is a refusal with a reason.

The same rule is applied to snapshot_png: an extension it cannot write is
refused instead of being silently rewritten to .png (which reported True for a
file the caller never asked for), and .tiff is honoured like .tif.

Also covered here: the FBX and CVFF surface writers, which the API exposed but
no test ever exercised, and the GUI wording that promised formats the code
could not write.
"""

import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

vtk = pytest.importorskip("vtk")

import fv.render.export as EX  # noqa: E402
from test_r115_three_meshes import _fph  # noqa: E402


def _offscreen_window(size=64):
    """A tiny offscreen window with one sphere, for real writes."""
    ren = vtk.vtkRenderer()
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetSize(size, size)
    src = vtk.vtkSphereSource()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(src.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    ren.AddActor(actor)
    win.Render()
    return win, ren


# ---------------------------------------------------------------------------
# encoder decision table
# ---------------------------------------------------------------------------

def test_r126_encoder_table_is_decided_by_extension_and_capability(monkeypatch):
    """Every extension maps to the encoder that can really write it."""
    monkeypatch.setattr(EX, "_vtk_has", lambda n: n == "vtkOggTheoraWriter")
    monkeypatch.setattr(EX, "_ffmpeg_path", lambda: None)
    assert EX.video_encoder_for("a.ogv") == ("vtk-ogg-theora", "")
    assert EX.video_encoder_for("a.AVI")[0] == ""
    assert "vtkAVIWriter" in EX.video_encoder_for("a.avi")[1]
    assert EX.video_encoder_for("a.mp4")[0] == ""
    assert "ffmpeg" in EX.video_encoder_for("a.mp4")[1]
    assert EX.video_encoder_for("a.wmv")[0] == ""
    assert ".wmv" in EX.video_encoder_for("a.wmv")[1]
    assert EX.video_encoder_for("noext")[0] == ""
    # capability changes the answer, nothing else
    monkeypatch.setattr(EX, "_ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(EX, "_vtk_has", lambda n: True)
    assert EX.video_encoder_for("a.MP4")[0] == "ffmpeg"
    assert EX.video_encoder_for("a.avi")[0] == "vtk-avi"
    assert EX.video_encoder_for("a.ogv")[0] == "vtk-ogg-theora"


def test_r126_offered_formats_are_the_deliverable_ones(monkeypatch):
    """The GUI list is derived from the same table, so it cannot promise more."""
    monkeypatch.setattr(EX, "_vtk_has", lambda n: n == "vtkOggTheoraWriter")
    monkeypatch.setattr(EX, "_ffmpeg_path", lambda: None)
    assert [g for g, _label in EX.video_formats_available()] == ["*.ogv"]
    monkeypatch.setattr(EX, "_ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(EX, "_vtk_has", lambda n: True)
    assert [g for g, _label in EX.video_formats_available()] == [
        "*.ogv", "*.avi", "*.mp4"]


# ---------------------------------------------------------------------------
# refusal instead of a wrong container
# ---------------------------------------------------------------------------

def test_r126_mp4_without_ffmpeg_is_refused_and_writes_nothing(
        tmp_path, monkeypatch):
    """The old code wrote Ogg Theora into the .mp4 and returned success."""
    monkeypatch.setattr(EX, "_ffmpeg_path", lambda: None)
    win, _ren = _offscreen_window()
    dest = tmp_path / "anim.mp4"
    issues = []
    n = EX.export_animation_video(None, None, None, win, str(dest),
                                  frames=2, fps=10, issues=issues)
    assert n == 0
    assert not dest.exists()
    assert len(issues) == 1 and "ffmpeg" in issues[0]
    # and the same request through the frame-list path
    issues2 = []
    assert EX.export_iso_video([{"contour": None}], win, str(dest),
                               fps=10, issues=issues2) == 0
    assert not dest.exists()
    assert "ffmpeg" in issues2[0]


def test_r126_avi_without_vtk_writer_is_refused(tmp_path, monkeypatch):
    """A build without vtkAVIWriter must not fake an AVI."""
    monkeypatch.setattr(EX, "_vtk_has", lambda n: n == "vtkOggTheoraWriter")
    win, _ren = _offscreen_window()
    dest = tmp_path / "anim.avi"
    issues = []
    assert EX.export_animation_video(None, None, None, win, str(dest),
                                     frames=2, issues=issues) == 0
    assert not dest.exists()
    assert "vtkAVIWriter" in issues[0]


def test_r126_iso_video_refuses_before_rendering_any_frame(
        tmp_path, monkeypatch):
    """An impossible request must not leave a half-done PNG sequence."""
    monkeypatch.setattr(EX, "_vtk_has", lambda n: False)
    win, _ren = _offscreen_window()
    frame_dir = tmp_path / "frames"
    issues = []
    n = EX.export_iso_video([{"contour": None}], win, str(tmp_path / "a.ogv"),
                            tmp_dir=str(frame_dir), issues=issues)
    assert n == 0
    assert not (tmp_path / "a.ogv").exists()
    assert not frame_dir.exists() or not list(frame_dir.iterdir())
    assert "vtkOggTheoraWriter" in issues[0]


# ---------------------------------------------------------------------------
# what IS written holds the right container
# ---------------------------------------------------------------------------

def test_r126_ogv_really_holds_ogg_data(tmp_path):
    """Three frames become one Ogg container, not just a non-empty file."""
    win, _ren = _offscreen_window()
    dest = tmp_path / "anim.ogv"
    n = EX.export_animation_video(None, None, None, win, str(dest),
                                  frames=3, fps=10)
    assert n == 3
    assert dest.read_bytes()[:4] == b"OggS"


def test_r126_ffmpeg_encoder_reports_the_frame_count(tmp_path, monkeypatch):
    """It used to return 1 for every success, whatever the frame count."""
    for i in range(3):
        (tmp_path / ("f_%04d.png" % i)).write_bytes(b"\x89PNG")
    dest = tmp_path / "v.mp4"

    def fake_run(cmd, **_kw):
        assert cmd[0].endswith("ffmpeg")
        Path(cmd[-1]).write_bytes(b"fake-mp4")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(EX, "_ffmpeg_path", lambda: "/usr/bin/ffmpeg")
    dest.unlink(missing_ok=True)
    # the printf pattern is counted through its glob form when the caller
    # does not know the frame count
    assert EX._encode_video_ffmpeg(str(tmp_path), "f_%04d.png", str(dest),
                                   10) == 3
    # and the caller-supplied count wins when it is given
    dest.unlink()
    assert EX._encode_video_ffmpeg(str(tmp_path), "f_%04d.png", str(dest),
                                   10, n_frames=7) == 7


def test_r126_snapshot_png_refuses_extensions_it_cannot_write(tmp_path):
    """A .xyz request used to silently produce a .png and return True."""
    win, _ren = _offscreen_window()
    bad = tmp_path / "shot.xyz"
    assert EX.snapshot_png(win, str(bad)) is False
    assert not bad.exists()
    assert not (tmp_path / "shot.png").exists()
    # .tiff is a real TIFF, not a renamed PNG
    tif = tmp_path / "shot.tiff"
    assert EX.snapshot_png(win, str(tif)) is True
    assert tif.read_bytes()[:4] in (b"II*\x00", b"MM\x00*")


# ---------------------------------------------------------------------------
# FBX / CVFF labels and writers
# ---------------------------------------------------------------------------

def test_r126_fbx_and_cvff_exports_write_their_own_formats(tmp_path, fph_golden):
    """Both writers existed but no test ever ran them."""
    ff, _cells, _vols = _fph(fph_golden)
    bnd = np.flatnonzero(np.asarray(ff.link_data["neighbour"]) == -1)[:64]
    ff.surface_regions = [("wall", bnd)]

    fbx = tmp_path / "surface.fbx"
    assert EX.export_surface_fbx(ff, str(fbx)) is True
    head = fbx.read_text(encoding="utf-8", errors="replace")[:200]
    assert head.startswith("; FBX 7.3.0 project file")
    assert "FBXVersion: 7300" in head

    cvw = tmp_path / "scene.cvw"
    assert EX.export_surface_cvff(ff, str(cvw)) is True
    from fv.model.dataset import cvff_load
    back = cvff_load(str(cvw))
    assert [n for n, _ids in back.surface_regions] == ["wall"]
    assert back.n_vertices > 0


def test_r126_gui_offers_the_formats_it_can_write():
    """The menu/dialog text must match what the code can actually produce."""
    src = (Path(__file__).resolve().parents[1] / "fv" / "gui"
           / "main.py").read_text(encoding="utf-8")
    assert "video_formats_available" in src
    # the old hard-coded filter promised AVI on a build without a writer
    assert '"Ogg Theora video (*.ogv);;AVI video (*.avi)"' not in src
    assert "encode MP4/AVI via ffmpeg" not in src
    assert 'add(m, "Export FBX' in src and 'add(m, "Export CVFF' in src
    assert "def on_export_fbx" in src and "def on_export_cvff" in src
    # OBJ is OBJ: the entry no longer claims to be FBX
    assert "FBX-neutral" not in src
