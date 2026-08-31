"""R25-S2 - multi-viewport layout + camera linking unit tests.

* ``viewport_rects`` partitions the unit square into a 2x2 grid.
* ``layout`` assigns each renderer its normalised viewport and paints.
* ``sync_cameras`` mirrors one renderer's camera pose onto its siblings so
  a 2x2 viewer keeps all four cameras locked together.
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


def _rw_with(renderers):
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetSize(600, 400)
    for r in renderers:
        rw.AddRenderer(r)
    return rw


def _make_renderer():
    ren = vtk.vtkRenderer()
    ren.SetBackground(0.1, 0.2, 0.3)
    return ren


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_viewport_rects_2x2_partition_unit_square():
    """The four 2x2 viewports exactly tile the [0,1]^2 square."""
    from fv.render.viewport import LAYOUT_2x2, viewport_rects
    rects = viewport_rects(LAYOUT_2x2)
    assert len(rects) == 4
    assert all(len(r) == 4 for r in rects)
    # no gaps / overlaps along both axes
    xs = sorted({r[0] for r in rects} | {r[2] for r in rects})
    ys = sorted({r[1] for r in rects} | {r[3] for r in rects})
    assert xs == [0.0, 0.5, 1.0]
    assert ys == [0.0, 0.5, 1.0]


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_layout_single_is_full_viewport():
    from fv.render.viewport import LAYOUT_SINGLE, layout
    ren = _make_renderer()
    rw = _rw_with([ren])
    n = layout([ren], rw, LAYOUT_SINGLE)
    assert n == 1
    vp = ren.GetViewport()
    assert (vp[0], vp[2], vp[1], vp[3]) == (0.0, 1.0, 0.0, 1.0)


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_layout_2x2_assigns_distinct_viewports():
    from fv.render.viewport import LAYOUT_2x2, layout
    renderers = [_make_renderer(), _make_renderer(), _make_renderer(),
                 _make_renderer()]
    rw = _rw_with(renderers)
    n = layout(renderers, rw, LAYOUT_2x2)
    assert n == 4
    result = [tuple(round(v, 6) for v in r.GetViewport()) for r in renderers]
    assert len(set(result)) == 4  # all quadrants distinct


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_read_pose_matches_camera():
    from fv.render.viewport import read_pose
    ren = _make_renderer()
    rw = _rw_with([ren])
    cam = ren.GetActiveCamera()
    cam.SetPosition(10.0, 1.0, 20.0)
    cam.SetFocalPoint(0.0, 0.0, 0.0)
    cam.SetViewUp(0.0, 1.0, 0.0)
    rw.Render()
    pose = read_pose(ren)
    assert pose["position"] == (10.0, 1.0, 20.0)
    assert pose["focal_point"] == (0.0, 0.0, 0.0)
    assert pose["view_up"][1] == 1.0


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_sync_cameras_links_all_viewports():
    """A pose change on the source propagates to every sibling (R25-S2)."""
    from fv.render.viewport import LAYOUT_2x2, layout, read_pose, sync_cameras
    renderers = [_make_renderer() for _ in range(4)]
    rw = _rw_with(renderers)
    layout(renderers, rw, LAYOUT_2x2)

    src = renderers[0]
    cam = src.GetActiveCamera()
    cam.SetPosition(5.0, 6.0, 7.0)
    cam.SetFocalPoint(1.0, 2.0, 3.0)
    cam.SetViewUp(0.0, 0.0, 1.0)

    n = sync_cameras(src, renderers[1:])
    assert n == 3
    ref = read_pose(src)
    for other in renderers[1:]:
        assert read_pose(other) == ref
