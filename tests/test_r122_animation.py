"""R122: animation must actually advance, and must not throw the view away.

Two defects, both measured before and after:

* a looping automove plane was FROZEN at its start pose and a non-looping one
  snapped straight to the end pose, because the frame count never reached
  automove_coordinate: without it the step index is not normalised, falls
  through as-is and is then clamped to [0, 1].
* playback called scene.fit() on every step, and fit() ends in ResetCamera,
  so the viewpoint was discarded several times a second.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

vtk = pytest.importorskip("vtk")

from fv.model import dataset  # noqa: E402
from fv.model import objects as O  # noqa: E402
from fv.render import scene as S  # noqa: E402
from fv.render.plane import automove_coordinate  # noqa: E402

FPH = r"D:\training\cgns\examples\tr03_9.fph"


def _plane() -> O.PlaneObject:
    pl = O.PlaneObject()
    pl.automove_enabled = True
    pl.automove_method = "Line"
    pl.automove_loop = True
    pl.automove_frames = 10
    pl.point = (0.0, 0.0, 0.0)
    pl.normal = (0.0, 0.0, 1.0)
    pl.automove_start_point = (0.0, 0.0, -0.02)
    pl.automove_ref_point = (0.0, 0.0, 0.02)
    pl.automove_start_normal = (0.0, 0.0, 1.0)
    pl.automove_ref_normal = (0.0, 0.0, 1.0)
    return pl


def test_without_a_frame_count_the_plane_is_frozen():
    """This is the old behaviour, pinned so the cause stays visible."""
    pl = _plane()
    zs = [automove_coordinate(pl, t, frames=None)[0][2] for t in range(6)]
    assert len(set(round(z, 9) for z in zs)) == 1, (
        "without frames the step index clamps to [0, 1] and cannot move")


def test_with_a_frame_count_the_plane_advances_monotonically():
    """Every step must be a distinct, forward position."""
    pl = _plane()
    zs = [automove_coordinate(pl, t, frames=10)[0][2] for t in range(6)]
    assert len(set(round(z, 9) for z in zs)) == 6, zs
    assert all(b > a for a, b in zip(zs, zs[1:])), zs


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_scene_animate_forwards_the_frame_count():
    """The frame count has to survive Scene.animate, not just the helper."""
    ff = dataset.load_file(FPH)
    pl = _plane()
    main = O.MainObject("x", "x")
    main.children = [pl]
    sc = S.Scene()
    sc.build(ff, main=main)

    frozen = []
    for t in range(6):
        sc.animate(t)
        frozen.append(round(pl.point[2], 9))
    assert len(set(frozen)) == 1, "the default path should stay frozen"

    moved = []
    for t in range(6):
        sc.animate(t, frames=10)
        moved.append(round(pl.point[2], 9))
    assert len(set(moved)) == 6, moved
    assert all(b > a for a, b in zip(moved, moved[1:])), moved


def test_fit_resets_the_camera_which_is_why_playback_must_not_call_it():
    """Documents the mechanism behind the viewpoint loss."""
    ren = vtk.vtkRenderer()
    src = vtk.vtkSphereSource()
    src.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(src.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    ren.AddActor(actor)
    cam = ren.GetActiveCamera()
    ren.ResetCamera()
    cam.SetPosition(5.0, 5.0, 5.0)
    cam.SetFocalPoint(0.0, 0.0, 0.0)
    before = tuple(cam.GetPosition())
    ren.ResetCamera()
    assert tuple(cam.GetPosition()) != before, (
        "ResetCamera is expected to move the camera; that is the whole risk")


def test_gui_preserves_and_restores_the_view_pose():
    """The GUI must capture and re-apply the pose around a rebuild."""
    pytest.importorskip("PyQt5.QtWidgets")
    from fv.gui import main as M

    src = Path(M.__file__).read_text(encoding="utf-8-sig")
    assert "def _capture_view_pose" in src
    assert "def _restore_view_pose" in src
    # the playback path must use them rather than fitting every frame
    assert "self._restore_view_pose(pose)" in src
    assert "def _animation_frame_span" in src
    assert "frames=self._animation_frame_span()" in src


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_animating_one_plane_leaves_the_others_alone():
    """animate() used to delete EVERY plane actor and rebuild only its own.

    One animated plane therefore made every other plane disappear on the
    first frame.  The scene is built with two planes, only one of which
    moves, and the stationary one must still own its actors afterwards.
    """
    ff = dataset.load_file(FPH)
    moving = _plane()
    still = O.PlaneObject()
    still.point = (0.0, 0.0, 0.0)
    still.normal = (0.0, 0.0, 1.0)
    still.show_contour = True
    still.contour_var = "PRES"
    moving.contour_var = "PRES"
    main = O.MainObject("x", "x")
    main.children = [moving, still]
    sc = S.Scene()
    sc.build(ff, main=main)

    def owned(obj):
        return [a for a, (k, o) in sc._actor_object.items() if o is obj]

    before = len(owned(still))
    assert before > 0, "the stationary plane built no actors"
    for t in range(3):
        sc.animate(t, frames=10)
    after = len(owned(still))
    assert after == before, (
        "the stationary plane lost %d of its %d actors to the animation"
        % (before - after, before))


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_animated_plane_stays_registered_for_picking():
    """Rebuilt actors must keep their object mapping, or picks stop working."""
    ff = dataset.load_file(FPH)
    moving = _plane()
    moving.contour_var = "PRES"
    main = O.MainObject("x", "x")
    main.children = [moving]
    sc = S.Scene()
    sc.build(ff, main=main)
    sc.animate(2, frames=10)
    owners = {k for k, o in sc._actor_object.values() if o is moving}
    assert owners == {"plane"}, owners
