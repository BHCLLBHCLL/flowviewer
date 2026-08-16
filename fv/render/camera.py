"""Camera keyframes and continuous screenshot capture (scPOST Camera 5b).

A keyframe is a camera pose dict::

    {"position": (x, y, z), "focal_point": (x, y, z),
     "view_up": (x, y, z), "parallel": bool}

``keyframe_poses`` linearly interpolates between consecutive keyframes and
``capture_camera_sequence`` drives a renderer through those poses, writing
one PNG per frame via the export snapshot helper (SaveBmp equivalent).
"""

from __future__ import annotations

import math
import os


def _v3(a, b, t):
    """Linear interpolation of two 3-tuples."""
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _slerp_v3(a, b, t):
    """Spherical linear interpolation of two 3-vectors (R3.3).

    Keeps ``view_up`` unit length while rotating between two keyframes,
    avoiding the over-the-top jump of naive Cartesian interpolation.
    """
    an = (a[0] ** 2 + a[1] ** 2 + a[2] ** 2) ** 0.5
    bn = (b[0] ** 2 + b[1] ** 2 + b[2] ** 2) ** 0.5
    if an < 1e-12 and bn < 1e-12:
        return (0.0, 0.0, 1.0)
    if an < 1e-12:
        return (b[0] / bn, b[1] / bn, b[2] / bn)
    if bn < 1e-12:
        return (a[0] / an, a[1] / an, a[2] / an)
    ua = (a[0] / an, a[1] / an, a[2] / an)
    ub = (b[0] / bn, b[1] / bn, b[2] / bn)
    dot = max(-1.0, min(1.0, ua[0] * ub[0] + ua[1] * ub[1] + ua[2] * ub[2]))
    theta = math.acos(dot)
    if theta < 1e-6:
        return ua
    sin_theta = math.sin(theta)
    wa = math.sin((1.0 - t) * theta) / sin_theta
    wb = math.sin(t * theta) / sin_theta
    return (wa * ua[0] + wb * ub[0],
            wa * ua[1] + wb * ub[1],
            wa * ua[2] + wb * ub[2])


def _cr_v3(p0, p1, p2, p3, t):
    """Catmull-Rom spline of four 3-tuples at parameter t in [0, 1]."""
    t2 = t * t
    t3 = t2 * t
    out = []
    for i in range(3):
        v = (0.5 * ((2.0 * p1[i])
                    + (-p0[i] + p2[i]) * t
                    + (2.0 * p0[i] - 5.0 * p1[i] + 4.0 * p2[i] - p3[i]) * t2
                    + (-p0[i] + 3.0 * p1[i] - 3.0 * p2[i] + p3[i]) * t3))
        out.append(float(v))
    return tuple(out)


def interpolate_pose(p0, p1, t):
    """Interpolate between two camera poses by factor t in [0, 1]."""
    t = max(0.0, min(1.0, float(t)))
    return {
        "position": _v3(p0["position"], p1["position"], t),
        "focal_point": _v3(p0["focal_point"], p1["focal_point"], t),
        "view_up": _slerp_v3(p0["view_up"], p1["view_up"], t),
        "parallel": p0["parallel"] if t < 0.5 else p1["parallel"],
    }


def _spline_pose(km1, k0, k1, k2, t):
    """Catmull-Rom pose between k0 and k1 using adjacent keyframes (P1.5)."""
    t = max(0.0, min(1.0, float(t)))
    up = _cr_v3(km1["view_up"], k0["view_up"], k1["view_up"], k2["view_up"], t)
    n = (up[0] ** 2 + up[1] ** 2 + up[2] ** 2) ** 0.5
    if n < 1e-12:
        up = k0["view_up"]
    else:
        up = (up[0] / n, up[1] / n, up[2] / n)
    return {
        "position": _cr_v3(km1["position"], k0["position"],
                           k1["position"], k2["position"], t),
        "focal_point": _cr_v3(km1["focal_point"], k0["focal_point"],
                              k1["focal_point"], k2["focal_point"], t),
        "view_up": up,
        "parallel": k0["parallel"] if t < 0.5 else k1["parallel"],
    }


def keyframe_poses(keyframes, n_frames):
    """Expand keyframes into n_frames evenly spaced camera poses.

    With a single keyframe every frame repeats it.  Two keyframes
    interpolate linearly (no neighbourhood for a spline); three or more
    use Catmull-Rom splines through every keyframe (C1-continuous, P1.5).
    The last frame is always the final keyframe.
    """
    n_frames = max(1, int(n_frames))
    if not keyframes:
        return []
    if n_frames == 1:
        return [dict(keyframes[0])]
    if len(keyframes) == 1:
        return [dict(keyframes[0]) for _ in range(n_frames)]
    segs = len(keyframes) - 1
    spline = len(keyframes) >= 3
    poses = []
    for i in range(n_frames):
        u = i * segs / float(n_frames - 1)
        k = int(u)
        if k >= segs:
            poses.append(dict(keyframes[-1]))
            continue
        if spline:
            km1 = keyframes[k - 1] if k > 0 else keyframes[0]
            k2 = keyframes[k + 2] if k + 2 < len(keyframes) \
                else keyframes[-1]
            poses.append(_spline_pose(km1, keyframes[k],
                                      keyframes[k + 1], k2, u - k))
        else:
            poses.append(interpolate_pose(keyframes[k], keyframes[k + 1],
                                          u - k))
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
