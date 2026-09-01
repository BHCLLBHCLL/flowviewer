"""R25-S2: multi-viewport layouts + camera linking (2x2 / single).

Headless-friendly building blocks so a Qt window can divide one VTK render
window into several renderers (2x2 grid or a single full viewport) and keep
their cameras linked: changing any one viewer's pose mirrors it to the rest.

* :func:`viewport_rects`  - normalised [x0,y0,x1,y1] viewport cadence.
* :func:`layout`          - apply a layout to a list of renderers and paint.
* :func:`read_pose`       - capture a camera pose dict from a renderer.
* :func:`copy_pose`       - apply a pose dict to a camera **without** reset.
* :func:`sync_cameras`    - copy one renderer's pose onto sibling renderers.

R29 additions (independent-camera mode):

* :func:`unlink_camera`         - give a renderer its own camera, cloned pose.
* :func:`standard_views`       - front/right/top/iso pose dicts from bounds.
* :func:`apply_standard_views` - lay the four standard views on a 2x2 grid.

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


def unlink_camera(renderer) -> bool:
    """R29: replace *renderer*'s active camera with an independent clone.

    The new ``vtkCamera`` copies the current pose component-wise, so
    switching to independent mode causes no visible jump; afterwards the
    renderer no longer shares the camera object with its siblings. Returns
    True when a camera was swapped in.
    """
    pose = read_pose(renderer)
    if pose is None:
        return False
    import vtk
    cam = renderer.GetActiveCamera()
    parallel_scale = cam.GetParallelScale()
    new_cam = vtk.vtkCamera()
    new_cam.SetPosition(*pose["position"])
    new_cam.SetFocalPoint(*pose["focal_point"])
    new_cam.SetViewUp(*pose["view_up"])
    new_cam.SetParallelProjection(1 if pose["parallel"] else 0)
    new_cam.SetParallelScale(parallel_scale)
    renderer.SetActiveCamera(new_cam)
    return True


def standard_views(bounds) -> dict:
    """R29: canonical front/right/top/iso camera poses for *bounds*.

    ``bounds`` is an (xmin, ymin, zmin, xmax, ymax, zmax) tuple; the eye
    distance is the bounding-box diagonal so every view frames the model.
    Poses match the :func:`read_pose` dict shape.
    """
    if not bounds or len(bounds) != 6:
        bounds = (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
    xmin, ymin, zmin, xmax, ymax, zmax = (float(v) for v in bounds)
    cx, cy, cz = ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0,
                  (zmin + zmax) / 2.0)
    d = max(((xmax - xmin) ** 2 + (ymax - ymin) ** 2
             + (zmax - zmin) ** 2) ** 0.5, 1e-9)
    return {
        # front: look along -y with z up
        "front": {"position": (cx, cy + d, cz),
                  "focal_point": (cx, cy, cz),
                  "view_up": (0.0, 0.0, 1.0), "parallel": True},
        # right: look along -x with z up
        "right": {"position": (cx + d, cy, cz),
                  "focal_point": (cx, cy, cz),
                  "view_up": (0.0, 0.0, 1.0), "parallel": True},
        # top: look along -z; y becomes screen-up
        "top": {"position": (cx, cy, cz + d),
                "focal_point": (cx, cy, cz),
                "view_up": (0.0, 1.0, 0.0), "parallel": True},
        # iso: classic (1, 1, 1) corner view
        "iso": {"position": (cx + d / 2.0, cy + d / 2.0, cz + d / 2.0),
                "focal_point": (cx, cy, cz),
                "view_up": (0.0, 0.0, 1.0), "parallel": True},
    }


def apply_standard_views(renderers, bounds) -> int:
    """R29: lay front/right/top/iso on a 2x2 grid (TL, TR, BL, BR).

    Writes each standard pose onto the renderers' active cameras in
    order; returns the number of cameras written (0 for an empty list).
    """
    views = standard_views(bounds)
    order = (views["front"], views["right"], views["top"], views["iso"])
    n = 0
    for ren, pose in zip(renderers or [], order):
        if copy_pose(ren, pose):
            n += 1
    return n


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
