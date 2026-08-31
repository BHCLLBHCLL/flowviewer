"""R25-S2: multi-viewport layouts + camera linking (2x2 / single).

Headless-friendly building blocks so a Qt window can divide one VTK render
window into several renderers (2x2 grid or a single full viewport) and keep
their cameras linked: changing any one viewer's pose mirrors it to the rest.

* :func:`viewport_rects`  - normalised [x0,y0,x1,y1] viewport cadence.
* :func:`layout`          - apply a layout to a list of renderers and paint.
* :func:`read_pose`       - capture a camera pose dict from a renderer.
* :func:`copy_pose`       - apply a pose dict to a camera **without** reset.
* :func:`sync_cameras`    - copy one renderer's pose onto sibling renderers.

The pose dict is the same shape used by :mod:`fv.render.camera`
(``{"position","focal_point","view_up","parallel"}``).
"""

from __future__ import annotations

from typing import List, Optional, Tuple

Rect = Tuple[float, float, float, float]

LAYOUT_SINGLE = "single"
LAYOUT_2x2 = "2x2"

# normalised viewports: 2x2 reads TL, TR, BL, BR (view Y up => y=1 is top).
_VIEWPORTS = {
    LAYOUT_SINGLE: [(0.0, 0.0, 1.0, 1.0)],
    LAYOUT_2x2: [
        (0.0, 0.5, 0.5, 1.0),
        (0.5, 0.5, 1.0, 1.0),
        (0.0, 0.0, 0.5, 0.5),
        (0.5, 0.0, 1.0, 0.5),
    ],
}


def viewport_rects(layout: str = LAYOUT_2x2) -> List[Rect]:
    """Return normalised viewport rectangles for a named layout."""
    if layout not in _VIEWPORTS:
        raise ValueError("unknown layout %r (expected %s)"
                         % (layout, "single | 2x2"))
    return list(_VIEWPORTS[layout])


def apply_viewport(renderer, rect: Rect) -> None:
    """Set one renderer's normalised viewport rectangle."""
    if renderer is None:
        return
    renderer.SetViewport(*rect)


def layout(renderers, render_window, layout: str = LAYOUT_2x2) -> int:
    """Apply *layout* to *renderers* within *render_window*; paint once.

    Returns the number of viewport slots used (extra renderers are left
    untouched). No-op for an empty/None render_window.
    """
    if render_window is None:
        return 0
    rects = viewport_rects(layout)
    for i, ren in enumerate(renderers):
        if i >= len(rects):
            break
        apply_viewport(ren, rects[i])
    render_window.Render()
    return min(len(rects), len(renderers or []))


def read_pose(renderer) -> Optional[dict]:
    """Capture the active-camera pose dict from a renderer (or None)."""
    if renderer is None:
        return None
    try:
        cam = renderer.GetActiveCamera()
        return {
            "position": tuple(float(v) for v in cam.GetPosition()),
            "focal_point": tuple(float(v) for v in cam.GetFocalPoint()),
            "view_up": tuple(float(v) for v in cam.GetViewUp()),
            "parallel": bool(cam.GetParallelProjection()),
        }
    except Exception:  # pragma: no cover
        return None


def copy_pose(renderer, pose: dict) -> bool:
    """Write a pose dict onto a renderer's active camera (no ResetCamera).

    Unlike :func:`fv.render.camera.apply_pose` this does not call
    ``ResetCamera``, so every linked viewport ends up with byte-for-byte the
    same pose (useful for camera-lock across 2x2 viewports).
    """
    if renderer is None or pose is None:
        return False
    try:
        cam = renderer.GetActiveCamera()
        cam.SetPosition(*pose["position"])
        cam.SetFocalPoint(*pose["focal_point"])
        cam.SetViewUp(*pose["view_up"])
        cam.SetParallelProjection(1 if pose.get("parallel") else 0)
        return True
    except Exception:
        return False


def sync_cameras(source, targets) -> int:
    """Mirror *source* renderer's camera pose onto every *target* renderer.

    Only targets with a resolvable active camera are written. Returns the
    number of targets updated (0 if a source pose is unavailable).
    """
    pose = read_pose(source)
    if pose is None:
        return 0
    n = 0
    for t in targets or []:
        if t is None or t is source:
            continue
        if copy_pose(t, pose):
            n += 1
    return n
