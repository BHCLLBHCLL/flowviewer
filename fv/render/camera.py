"""Camera keyframes and continuous screenshot capture (scPOST Camera 5b).

A keyframe is a camera pose dict::

    {"position": (x, y, z), "focal_point": (x, y, z),
     "view_up": (x, y, z), "parallel": bool}

``keyframe_poses`` linearly interpolates between consecutive keyframes and
``capture_camera_sequence`` drives a renderer through those poses, writing
one PNG per frame via the export snapshot helper (SaveBmp equivalent).
"""

from __future__ import annotations

import os


def _v3(a, b, t):
    """Linear interpolation of two 3-tuples."""
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def interpolate_pose(p0, p1, t):
    """Interpolate between two camera poses by factor t in [0, 1]."""
    t = max(0.0, min(1.0, float(t)))
    return {
        "position": _v3(p0["position"], p1["position"], t),
        "focal_point": _v3(p0["focal_point"], p1["focal_point"], t),
        "view_up": _v3(p0["view_up"], p1["view_up"], t),
        "parallel": p0["parallel"] if t < 0.5 else p1["parallel"],
    }


def keyframe_poses(keyframes, n_frames):
    """Expand keyframes into n_frames evenly spaced camera poses.

    With a single keyframe every frame repeats it; with two or more the
    segment count is split evenly (the last frame is the final keyframe).
    """
    n_frames = max(1, int(n_frames))
    if not keyframes:
        return []
    if n_frames == 1:
        return [dict(keyframes[0])]
    if len(keyframes) == 1:
        return [dict(keyframes[0]) for _ in range(n_frames)]
    segs = len(keyframes) - 1
    poses = []
    for i in range(n_frames):
        u = i * segs / float(n_frames - 1)
        k = int(u)
        if k >= segs:
            poses.append(dict(keyframes[-1]))
        else:
            poses.append(interpolate_pose(keyframes[k], keyframes[k + 1], u - k))
    return poses


def apply_pose(renderer, pose) -> bool:
    """Apply a camera pose to a renderer active camera (best-effort)."""
    if renderer is None:
        return False
    try:
        cam = renderer.GetActiveCamera()
        cam.SetPosition(*pose["position"])
        cam.SetFocalPoint(*pose["focal_point"])
        cam.SetViewUp(*pose["view_up"])
        cam.SetParallelProjection(1 if pose.get("parallel") else 0)
        renderer.ResetCamera()
        return True
    except Exception:
        return False


def capture_camera_sequence(renderer, keyframes, n_frames, out_dir,
                            base="cam") -> int:
    """Drive the camera through keyframes and write PNG frames.

    Returns the number of frames written (0 when VTK is unavailable).
    Frames are named base_0000.png, base_0001.png, ...
    """
    if renderer is None:
        return 0
    poses = keyframe_poses(keyframes, n_frames)
    if not poses:
        return 0
    os.makedirs(out_dir, exist_ok=True)
    from .export import snapshot_png
    written = 0
    for i, pose in enumerate(poses):
        if not apply_pose(renderer, pose):
            continue
        path = os.path.join(out_dir, base + "_{:04d}.png".format(i))
        if snapshot_png(renderer, path):
            written += 1
    return written
