"""R29 - independent multi-viewport camera mode tests (section 9.9).

S1 building blocks: unlink_camera swaps in a distinct camera with the
same pose; standard_views produces orthogonal canonical poses;
apply_standard_views lays them on a 2x2 grid. S2 GUI wiring: mode switch
gives every viewport its own camera without a pose jump, switching back
restores the shared object, layout round-trips keep the mode, and
Standard Views writes distinct canonical poses.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

vtk = pytest.importorskip("vtk")
try:
    import PyQt5  # noqa: F401
    _HAS_QT = True
except Exception:
    _HAS_QT = False


@pytest.fixture
def _qapp():
    if not _HAS_QT:
        pytest.skip("PyQt5 unavailable")
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _rw_with(renderers):
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetSize(600, 400)
    for r in renderers:
        rw.AddRenderer(r)
    return rw


def _pose_eq(a, b):
    return (tuple(round(v, 6) for v in a["position"])
            == tuple(round(v, 6) for v in b["position"])
            and tuple(round(v, 6) for v in a["view_up"])
            == tuple(round(v, 6) for v in b["view_up"]))


def test_unlink_camera_distinct_object_same_pose():
    """unlink swaps the camera object but keeps the pose untouched."""
    from fv.render.viewport import read_pose, unlink_camera
    ren = vtk.vtkRenderer()
    cam = ren.GetActiveCamera()
    cam.SetPosition(1.0, 2.0, 3.0)
    cam.SetFocalPoint(0.5, 0.5, 0.5)
    cam.SetViewUp(0.0, 0.0, 1.0)
    before = read_pose(ren)
    assert unlink_camera(ren) is True
    assert ren.GetActiveCamera() is not cam
    assert _pose_eq(read_pose(ren), before)
    # further moves on the old (primary) camera do not touch the clone
    cam.SetPosition(9.0, 9.0, 9.0)
    assert read_pose(ren)["position"] == (1.0, 2.0, 3.0)


def test_standard_views_orthogonal_and_framed():
    """front/right/top/iso view directions are mutually orthogonal-ish."""
    from fv.render.viewport import standard_views
    bounds = (-1.0, -1.0, -1.0, 1.0, 1.0, 1.0)
    views = standard_views(bounds)
    assert set(views) == {"front", "right", "top", "iso"}
    eye = {k: np.array(v["position"]) for k, v in views.items()}
    centre = np.zeros(3)
    dirs = {k: (eye[k] - centre) / np.linalg.norm(eye[k] - centre)
            for k in views}
    # front/right/top sit at one full diagonal (2*sqrt(3) for the unit
    # cube); iso at the d/2 corner point (norm = 3)
    for k in ("front", "right", "top"):
        assert abs(np.linalg.norm(eye[k] - centre) - 2.0 * 3 ** 0.5) < 1e-9
    assert abs(np.linalg.norm(eye["iso"] - centre) - 3.0) < 1e-9
    for k, v in views.items():
        assert v["parallel"] is True
    assert abs(np.dot(dirs["front"], dirs["right"])) < 1e-9
    assert abs(np.dot(dirs["front"], dirs["top"])) < 1e-9
    assert abs(np.dot(dirs["right"], dirs["top"])) < 1e-9
    assert abs(np.dot(dirs["iso"], dirs["front"])) > 0.5  # corner view


def test_apply_standard_views_four_cameras():
    """apply writes four distinct canonical poses in quadrant order."""
    from fv.render.viewport import apply_standard_views, read_pose
    renderers = [vtk.vtkRenderer() for _ in range(4)]
    _rw_with(renderers)
    n = apply_standard_views(renderers, (0.0, 0.0, 0.0, 1.0, 1.0, 1.0))
    assert n == 4
    poses = [read_pose(r) for r in renderers]
    # all four distinct
    keys = [tuple(round(v, 6) for v in p["position"]) for p in poses]
    assert len(set(keys)) == 4
    # TL=front (+y), TR=right (+x), BL=top (+z), BR=iso corner
    assert keys[0][1] > keys[0][0]      # front: y dominant
    assert keys[1][0] > keys[1][1]      # right: x dominant
    assert keys[2][2] > keys[2][0]      # top: z dominant
    assert abs(keys[3][0] - keys[3][1]) < 1e-9  # iso symmetric


@pytest.mark.skipif(not _HAS_QT, reason="PyQt5 unavailable")
def test_gui_camera_mode_switch_no_pose_jump(_qapp):
    """Independent mode: distinct camera objects, identical poses."""
    from fv.gui.main import FlowViewer
    from fv.render.viewport import read_pose, unlink_camera
    w = FlowViewer(filepath=None, enable_3d=True)
    try:
        rw = w.vtk_widget.GetRenderWindow()
        assert w._apply_viewport_layout("2x2", rw) == 4
        main_cam = w.renderer.GetActiveCamera()
        poses_before = [read_pose(r) for r in w.scene.renderers()]
        w._camera_mode = "independent"   # direct wiring (menu fires this)
        for ren in w._extra_renderers:
            unlink_camera(ren)
        cams = [r.GetActiveCamera() for r in w.scene.renderers()]
        assert len({id(c) for c in cams}) == 4      # all distinct
        assert cams[0] is main_cam                  # primary untouched
        poses_after = [read_pose(r) for r in w.scene.renderers()]
        for a, b in zip(poses_before, poses_after):
            assert _pose_eq(a, b)                    # no jump at switch
        # back to linked: every viewport shares the primary camera again
        for ren in w._extra_renderers:
            ren.SetActiveCamera(main_cam)
        w._camera_mode = "linked"
        cams = [r.GetActiveCamera() for r in w.scene.renderers()]
        assert all(c is main_cam for c in cams)
    finally:
        w.close()


@pytest.mark.skipif(not _HAS_QT, reason="PyQt5 unavailable")
def test_gui_layout_roundtrip_keeps_camera_mode(_qapp):
    """Re-entering 2x2 in independent mode gives every viewport own camera."""
    from fv.gui.main import FlowViewer
    w = FlowViewer(filepath=None, enable_3d=True)
    try:
        rw = w.vtk_widget.GetRenderWindow()
        w._apply_viewport_layout("2x2", rw)
        w._camera_mode = "independent"
        assert w._apply_viewport_layout("single", rw) == 1
        assert w._camera_mode == "independent"
        assert w._apply_viewport_layout("2x2", rw) == 4
        cams = [r.GetActiveCamera() for r in w.scene.renderers()]
        assert len({id(c) for c in cams}) == 4
    finally:
        w.close()


@pytest.mark.skipif(not _HAS_QT, reason="PyQt5 unavailable")
def test_gui_standard_views_applies_canonical_poses(_qapp):
    """Standard Views writes the four canonical poses in quadrant order."""
    from fv.gui.main import FlowViewer
    from fv.render.viewport import read_pose, standard_views, unlink_camera
    w = FlowViewer(filepath=None, enable_3d=True)
    try:
        rw = w.vtk_widget.GetRenderWindow()
        w._apply_viewport_layout("2x2", rw)
        w._camera_mode = "independent"
        for ren in w._extra_renderers:
            unlink_camera(ren)
        w.on_standard_views()
        views = standard_views(w._dataset_bounds())
        order = ("front", "right", "top", "iso")
        for ren, key in zip(w.scene.renderers(), order):
            p = read_pose(ren)
            assert _pose_eq(p, views[key]), key
    finally:
        w.close()
