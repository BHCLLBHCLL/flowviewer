"""R27 - multi-viewport wiring unit tests.

S1 verifies :class:`fv.render.scene.Scene` mirrors its actor set onto extra
renderers (2x2 viewports rendering the same scene) while sharing the primary
camera, and that add/remove/reset stay consistent across every viewport.
S2-level GUI wiring (View -> Layout menu) is covered by the headless-safe
building blocks exercised here plus the offscreen tests in test_gui.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

try:
    import vtk
    _HAS_VTK = True
except Exception:  # pragma: no cover
    _HAS_VTK = False


def _make_renderer():
    ren = vtk.vtkRenderer()
    ren.SetBackground(0.2, 0.2, 0.2)
    return ren


def _make_scene():
    from fv.render.scene import Scene
    return Scene(enable_3d=True)


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_scene_broadcasts_3d_actor_to_extra_renderers():
    """A 3D actor added to the scene lands in every registered renderer."""
    sc = _make_scene()
    ren_a = sc.renderer
    ren_b = _make_renderer()
    sc.add_renderer(ren_b)

    actor = vtk.vtkActor()
    sc.add_actor("surface:mesh", actor)

    assert ren_b is not ren_a
    assert actor in list(ren_a.GetActors())
    assert actor in list(ren_b.GetActors())


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_scene_camera_sharing_keeps_viewports_linked():
    """Assigning an extra renderer shares the primary camera object."""
    sc = _make_scene()
    ren_b = _make_renderer()
    sc.add_renderer(ren_b)
    # add_renderer mirrors the primary camera -> identical object identity
    assert ren_b.GetActiveCamera() is sc.renderer.GetActiveCamera()
    # nudging the shared camera updates both
    cam = sc.renderer.GetActiveCamera()
    cam.SetPosition(3.0, 4.0, 5.0)
    assert ren_b.GetActiveCamera().GetPosition() == (3.0, 4.0, 5.0)


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_scene_add_renderer_idempotent_and_dedupes():
    sc = _make_scene()
    ren_b = _make_renderer()
    assert sc.add_renderer(ren_b) == 1
    assert sc.add_renderer(ren_b) == 1          # no duplicate entries
    assert sc.add_renderer(sc.renderer) == 1    # primary excluded
    assert list(sc.renderers()) == [sc.renderer, ren_b]


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_scene_remove_object_actors_clears_all_viewports():
    sc = _make_scene()
    ren_b = _make_renderer()
    sc.add_renderer(ren_b)
    actor = vtk.vtkActor()
    from fv.model.objects import SurfaceObject
    obj = SurfaceObject()
    sc.add_actor("surface:mesh", actor)
    sc.register_actor_object(actor, "surface", obj)

    sc.remove_object_actors(obj)

    assert actor not in list(ren_b.GetActors())
    assert actor not in list(sc.renderer.GetActors())
    assert "surface" not in sc.actor_names()


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_scene_reset_drop_extra_renderers_and_actors():
    sc = _make_scene()
    ren_b = _make_renderer()
    sc.add_renderer(ren_b)
    actor = vtk.vtkActor()
    sc.add_actor("surface:mesh", actor)
    assert actor in list(ren_b.GetActors())

    sc.reset()

    assert sc._extra_renderers == []
    assert actor not in list(ren_b.GetActors())
    assert sc.actor_names() == []


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_scene_actor_names_consistent_across_viewports():
    sc = _make_scene()
    ren_b = _make_renderer()
    sc.add_renderer(ren_b)
    sc.add_actor("surface:contour", vtk.vtkActor())
    sc.add_actor("plane:mesh", vtk.vtkActor())
    assert sc.actor_names() == ["surface:contour", "plane:mesh"]
    # both renderers see the same set of 3D props
    assert list(ren_b.GetActors()) == list(sc.renderer.GetActors())


# ── S2 GUI wiring (offscreen Qt + real VTK render window) ─────────────────

_FPH = r"D:\training\cgns\examples\tr03_9.fph"

try:
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt5.QtWidgets import QApplication
    _HAS_QT = True
except Exception:  # pragma: no cover
    _HAS_QT = False


@pytest.fixture(scope="module")
def _qapp():
    if not _HAS_QT:
        pytest.skip("PyQt5 unavailable")
    return QApplication.instance() or QApplication([])


@pytest.mark.skipif(not _HAS_QT or not _HAS_VTK, reason="qt/vtk unavailable")
def test_gui_2x2_layout_assigns_four_viewports(_qapp):
    from fv.gui.main import FlowViewer
    w = FlowViewer(filepath=None, enable_3d=True)
    try:
        rw = w.vtk_widget.GetRenderWindow()
        assert w._apply_viewport_layout("2x2", rw) == 4
        rns = rw.GetRenderers()
        rns.InitTraversal()
        count = 0
        viewports = set()
        ren = rns.GetNextItem()
        while ren is not None:
            count += 1
            viewports.add(tuple(round(v, 4) for v in ren.GetViewport()))
            ren = rns.GetNextItem()
        assert count == 4
        assert len(viewports) == 4        # all four quadrants distinct
        for vp in viewports:
            assert min(vp[0], vp[2]) >= 0.0 and max(vp[0], vp[2]) <= 1.0
        assert w._viewport_layout == "2x2"
    finally:
        w.close()


@pytest.mark.skipif(not _HAS_QT or not _HAS_VTK, reason="qt/vtk unavailable")
def test_gui_2x2_then_single_round_trip(_qapp):
    from fv.gui.main import FlowViewer
    w = FlowViewer(filepath=None, enable_3d=True)
    try:
        rw = w.vtk_widget.GetRenderWindow()
        assert w._apply_viewport_layout("2x2", rw) == 4
        assert len(list(w.scene.renderers())) == 4
        assert w._apply_viewport_layout("single", rw) == 1
        assert w._viewport_layout == "single"
        assert len(list(w.scene.renderers())) == 1
        assert w._extra_renderers == []
    finally:
        w.close()


@pytest.mark.skipif(not _HAS_QT or not _HAS_VTK, reason="qt/vtk unavailable")
def test_gui_2x2_camera_linked_across_viewports(_qapp):
    """Moving the shared camera reflects in every viewport (linked)."""
    from fv.gui.main import FlowViewer
    w = FlowViewer(filepath=None, enable_3d=True)
    try:
        rw = w.vtk_widget.GetRenderWindow()
        assert w._apply_viewport_layout("2x2", rw) == 4
        cam = w.renderer.GetActiveCamera()
        cam.SetPosition(2.5, 3.5, 4.5)
        for ren in w.scene.renderers():
            assert ren.GetActiveCamera() is cam
            assert ren.GetActiveCamera().GetPosition() == (2.5, 3.5, 4.5)
    finally:
        w.close()
