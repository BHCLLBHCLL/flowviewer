"""R25-S1 - off-screen export: hi-res PNG frames + video (PNG sequence / MP4).

* ``snapshot_png`` honours a ``scale`` / ``dpi`` multiplier for hires export.
* ``export_iso_png_frames`` renders each iso/animation frame (per-cycle actor
  set from ``build_iso_animation``) to ``base_%04d.png`` offscreen.
* ``export_iso_video`` encodes those frames to ``.mp4`` via ffmpeg when
  present, else to ``.ogv`` via the VTK OggTheora path - both frame-driven.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FPH = r"D:\training\cgns\examples\tr03_9.fph"
_HAS_FPH = Path(FPH).exists()

try:
    import vtk
    _HAS_VTK = True
except Exception:  # pragma: no cover
    _HAS_VTK = False


def _offscreen_window(renderer=None, w=320, h=240):
    if renderer is None:
        renderer = vtk.vtkRenderer()
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetSize(w, h)
    rw.AddRenderer(renderer)
    return rw, renderer


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_snapshot_png_scale_gives_larger_image(tmp_path):
    """A 2x scale snapshot is strictly larger in pixel count (R25-S1)."""
    from fv.render.export import snapshot_png

    rw, ren = _offscreen_window()
    ren.SetBackground(0.1, 0.2, 0.3)
    cone = vtk.vtkConeSource()
    cone.SetResolution(40)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(cone.GetOutputPort())
    act = vtk.vtkActor()
    act.SetMapper(mapper)
    ren.AddActor(act)
    rw.Render()

    p1 = tmp_path / "x1.png"
    p2 = tmp_path / "x2.png"
    assert snapshot_png(rw, str(p1)) is True
    assert snapshot_png(rw, str(p2), scale=2.0) is True
    img1 = _read_png(p1)
    img2 = _read_png(p2)
    assert img2.size > img1.size


def _read_png(path):
    from vtk.util import numpy_support as vns
    rdr = vtk.vtkPNGReader()
    rdr.SetFileName(str(path))
    rdr.Update()
    return vns.vtk_to_numpy(rdr.GetOutput().GetPointData().GetScalars())


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_snapshot_png_dpi_matches_scale(tmp_path):
    """dpi>0 is mapped to a pixel scale (144 dpi => 2x pixels, R25-S1)."""
    from fv.render.export import snapshot_png

    rw, _ = _offscreen_window()
    rw.Render()
    p1 = tmp_path / "a.png"
    p2 = tmp_path / "b.png"
    assert snapshot_png(rw, str(p1)) is True
    assert snapshot_png(rw, str(p2), dpi=144.0) is True
    assert _read_png(p2).size > _read_png(p1).size


@pytest.mark.skipif(not (_HAS_VTK and _HAS_FPH), reason="vtk or sample missing")
def test_iso_png_frame_sequence(tmp_path):
    """Exporting iso-animation frames yields one PNG per cycle (R25-S1)."""
    from dataclasses import replace
    from types import SimpleNamespace

    import numpy as np
    from fv.model.dataset import load_file
    from fv.render.export import export_iso_png_frames
    from fv.render.isosurface import build_iso_animation

    ff = load_file(FPH)

    def cycle(offset):
        base = np.asarray(ff.variables["PRES"].array)
        f2 = replace(ff)
        v = dict(f2.variables)
        v["PRES"] = replace(v["PRES"], array=base + offset)
        f2.variables = v
        return f2

    obj = SimpleNamespace(contour_var="PRES", contour_number=4,
                          contour_values=None, contour_line=False,
                          show_vector=False, vector_var="",
                          contour_mono_color=False, contour_transparent=False)
    frames = build_iso_animation([cycle(0.0), cycle(50.0)], obj)
    assert len(frames) == 2

    rw, ren = _offscreen_window()
    ren.AddActor(frames[0]["contour"])
    rw.Render()

    out_dir = tmp_path / "frames"
    n = export_iso_png_frames(frames, ren, str(out_dir))
    assert n == 2
    for i in range(2):
        p = out_dir / f"frame_{i:04d}.png"
        assert p.exists() and p.stat().st_size > 0


@pytest.mark.skipif(not (_HAS_VTK and _HAS_FPH), reason="vtk or sample missing")
def test_iso_video_fallback_ogv(tmp_path):
    """Without ffmpeg the frame list still encodes via VTK (R25-S1)."""
    from dataclasses import replace
    from types import SimpleNamespace

    import numpy as np
    from fv.model.dataset import load_file
    from fv.render.export import export_iso_video
    from fv.render.isosurface import build_iso_animation

    ff = load_file(FPH)

    def cycle(offset):
        base = np.asarray(ff.variables["PRES"].array)
        f2 = replace(ff)
        v = dict(f2.variables)
        v["PRES"] = replace(v["PRES"], array=base + offset)
        f2.variables = v
        return f2

    obj = SimpleNamespace(contour_var="PRES", contour_number=4,
                          contour_values=None, contour_line=False,
                          show_vector=False, vector_var="",
                          contour_mono_color=False, contour_transparent=False)
    frames = build_iso_animation([cycle(0.0), cycle(50.0)], obj)

    rw, ren = _offscreen_window()
    ren.AddActor(frames[0]["contour"])
    rw.Render()

    if _has_ffmpeg():
        dest = tmp_path / "anim.mp4"
        n = export_iso_video(frames, ren, str(dest), fps=10)
        assert n > 0 and dest.exists() and dest.stat().st_size > 0
    else:
        dest = tmp_path / "anim.ogv"
        n = export_iso_video(frames, ren, str(dest), fps=10)
        assert dest.exists() and dest.stat().st_size > 0


def _has_ffmpeg():
    import shutil
    return shutil.which("ffmpeg") is not None
