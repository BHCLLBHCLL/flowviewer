"""Generic object-keyframe Timeline engine + per-keyframe render pipeline.

R35 lifts the plane/particle automove special-cases in ``Scene.animate``
into a reusable, headless-testable ``Timeline`` of per-object *property*
keyframe tracks (position / visibility / opacity / arbitrary scalars /
vectors), and adds ``render_timeline`` — a batch that advances a renderer
through the timeline writing one PNG + one JSON per frame.  It is the
object-keyframe sibling of ``fv.render.camera.capture_camera_sequence``
(camera keyframes) and ``fv.session.record_sequence`` (time-series
datasets): the whole module is pure/headless-safe (computation has no GL
dependency; rendering degrades to metadata-only when VTK is absent).
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

try:
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False

INTERP_HOLD = "hold"
INTERP_LINEAR = "linear"
INTERP_SPLINE = "spline"
_INTERPS = (INTERP_HOLD, INTERP_LINEAR, INTERP_SPLINE)

# Object properties the timeline drives as *visibility* / *opacity*; these
# map onto a target actor's SetVisibility/SetOpacity when the actor has been
# linked via ``Timeline.attach_actor``.
_VISIBILITY_PROPS = ("visibility", "visible")
_OPACITY_PROPS = ("opacity", "transparent")


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _as_vec3(value) -> Optional[tuple[float, float, float]]:
    """Best-effort view of ``value`` as a 3-vector (else None)."""
    if isinstance(value, (int, float)):
        return None
    try:
        parts = tuple(float(v) for v in value)
    except (TypeError, ValueError):
        return None
    return parts if len(parts) == 3 else None


def _cr(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Catmull-Rom scalar at parameter t in [0, 1]."""
    t2 = t * t
    t3 = t2 * t
    return (0.5 * ((2.0 * p1)
                   + (-p0 + p2) * t
                   + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                   + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3))


def _cr_vec3(p0, p1, p2, p3, t):
    return tuple(_cr(p0[i], p1[i], p2[i], p3[i], t) for i in range(3))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _interp_hold(keyframes, order, t):
    """Latest keyframe at or before t (hold)."""
    last = order[0]
    for k in order:
        if k > t:
            break
        last = k
    return keyframes[last]


def _interp_linear(keyframes, order, t):
    a = order[0]
    if t <= a:
        return keyframes[a]
    b = order[-1]
    if t >= b:
        return keyframes[b]
    for i in range(len(order) - 1):
        k0, k1 = order[i], order[i + 1]
        if k0 <= t <= k1:
            span = k1 - k0
            u = 0.0 if span <= 0 else (t - k0) / span
            va, vb = keyframes[k0], keyframes[k1]
            v3a, v3b = _as_vec3(va), _as_vec3(vb)
            if v3a is not None and v3b is not None:
                return tuple(_lerp(v3a[i], v3b[i], u) for i in range(3))
            return _lerp(va, vb, u) if isinstance(va, (int, float)) \
                else (va if u < 1.0 else vb)
    return keyframes[b]


def _interp_spline(keyframes, order, t):
    if len(order) < 3 or t <= order[0]:
        return keyframes[order[0]]
    if t >= order[-1]:
        return keyframes[order[-1]]
    for i in range(len(order) - 1):
        k0, k1 = order[i], order[i + 1]
        if k0 <= t <= k1:
            span = k1 - k0
            u = 0.0 if span <= 0 else (t - k0) / span
            km1 = order[i - 1] if i > 0 else order[0]
            k2 = order[i + 2] if i + 2 < len(order) else order[-1]
            p0, p1, p2, p3 = (keyframes[km1], keyframes[k0],
                              keyframes[k1], keyframes[k2])
            v3 = [_as_vec3(p) for p in (p0, p1, p2, p3)]
            if all(v is not None for v in v3):
                return _cr_vec3(v3[0], v3[1], v3[2], v3[3], u)
            if all(isinstance(p, (int, float)) for p in (p0, p1, p2, p3)):
                return _cr(p0, p1, p2, p3, u)
            return p1 if u < 0.5 else p2
    return keyframes[order[-1]]


def normalize_time(t: float, duration: float, loop: bool) -> float:
    """Fold ``t`` into ``[0, duration)`` (loop) or clamp at ``duration``."""
    if duration <= 0:
        return 0.0
    if loop:
        m = t % duration
        return 0.0 if m == 0.0 else m
    return max(0.0, min(duration, t))


class KeyframeTrack:
    """Keyframes over a single object property.

    ``keyframes`` maps ``time -> value`` (scalar or 3-vector).  ``interp``
    is one of ``hold`` / ``linear`` / ``spline``; ``spline`` uses componentwise
    Catmull-Rom for 3-vectors and scalars once there are >= 3 keyframes.
    ``loop`` folds evaluation times back into the track duration.
    """

    def __init__(self, obj: Any, property_name: str,
                 keyframes: Optional[dict] = None,
                 interp: str = INTERP_LINEAR,
                 loop: bool = True) -> None:
        self.obj = obj
        self.property_name = property_name
        self.interp = interp if interp in _INTERPS else INTERP_LINEAR
        self.loop = loop
        self._kf: dict[float, Any] = {float(t): v
                                      for t, v in (keyframes or {}).items()}
        self._order = sorted(self._kf)

    # -- queries --
    def duration(self) -> float:
        return self._order[-1] if self._order else 0.0

    def count(self) -> int:
        return len(self._order)

    def normalized(self, t: float) -> float:
        return normalize_time(t, self.duration(), self.loop)

    def evaluate(self, t: float):
        if not self._order:
            return None
        u = self.normalized(t)
        if self.interp == INTERP_HOLD:
            return _interp_hold(self._kf, self._order, u)
        if self.interp == INTERP_SPLINE:
            return _interp_spline(self._kf, self._order, u)
        return _interp_linear(self._kf, self._order, u)

    def apply(self, t: float) -> bool:
        """Set ``self.obj.<property>`` to the interpolated value at ``t``."""
        value = self.evaluate(t)
        if value is None:
            return False
        try:
            setattr(self.obj, self.property_name, value)
        except (AttributeError, TypeError):
            return False
        return True

    # -- actor reflection --
    def attach_actor(self, actor: Any) -> None:
        self._actor = actor

    def reflect_actor(self, value) -> None:
        """Best-effort push visibility/opacity onto a linked actor."""
        actor = getattr(self, "_actor", None)
        if actor is None or not _HAS_VTK:
            return
        try:
            if self.property_name in _VISIBILITY_PROPS:
                actor.SetVisibility(1 if _scalar_truthy(value) else 0)
            elif self.property_name in _OPACITY_PROPS:
                actor.GetProperty().SetOpacity(_clamp01(float(value)))
        except Exception:  # pragma: no cover - prop may not exist
            pass


def _scalar_truthy(value) -> bool:
    try:
        return bool(float(value))
    except (TypeError, ValueError):
        return bool(value)


class Timeline:
    """Ordered collection of per-object property tracks.

    ``keys(t)`` returns every ``(obj, property, value)`` the tracks resolve
    to at time ``t`` (deduplicated by ``(id(obj), property)``); ``apply(t)``
    writes them onto the target objects and reflects visibility/opacity onto
    any linked actors.  ``render_timeline`` drives a whole Timeline through
    the animation and snapshots each solved frame.
    """

    def __init__(self) -> None:
        self._tracks: list[KeyframeTrack] = []

    def add_track(self, track: KeyframeTrack) -> "Timeline":
        self._tracks.append(track)
        return self

    def __len__(self) -> int:
        return len(self._tracks)

    def __iter__(self):
        return iter(self._tracks)

    def duration(self) -> float:
        return max((t.duration() for t in self._tracks), default=0.0)

    def normalized(self, t: float) -> float:
        return normalize_time(t, self.duration(), True)

    def keys(self, t: float) -> list:
        """Resolved ``[(obj, property, value), …]`` at time ``t``."""
        seen = {}
        for tr in self._tracks:
            value = tr.evaluate(t)
            if value is None:
                continue
            seen[(id(tr.obj), tr.property_name)] = \
                (tr.obj, tr.property_name, value)
        return list(seen.values())

    def apply(self, t: float) -> None:
        """Write every track's interpolated value to its object."""
        for tr in self._tracks:
            value = tr.evaluate(t)
            if value is None:
                continue
            try:
                setattr(tr.obj, tr.property_name, value)
            except (AttributeError, TypeError):
                continue
            tr.reflect_actor(value)


def render_timeline(timeline: Timeline, renderer,
                    n_frames: int = 24, out_dir: str = "tl_out",
                    base: str = "kf",
                    loop: bool = True) -> dict:
    """Advance a Timeline ``n_frames`` steps, writing PNG + JSON per frame.

    Each frame solves the timeline at ``t = i * duration / (n_frames-1)``,
    applies it to the target objects, snapshots the renderer (best-effort,
    PNG only when VTK can render) and writes a ``{t, duration, n_tracks,
    values:{prop: value}}`` JSON.  A ``manifest.json`` summarises the run.
    Returns the manifest (always; ``ok`` reflects PNG write availability).
    """
    os.makedirs(out_dir, exist_ok=True)
    duration = timeline.duration()
    n_frames = max(2, int(n_frames))
    frames = []
    written = 0
    for i in range(n_frames):
        u = i / float(n_frames - 1)
        t = normalize_time(u * duration, duration, loop)
        timeline.apply(t)
        values = {tr.property_name: tr.evaluate(t)
                  for tr in timeline
                  if tr.evaluate(t) is not None}
        path = os.path.join(out_dir, f"{base}_{i:04d}.png")
        ok = False
        if renderer is not None:
            from .render.export import snapshot_png
            ok = bool(snapshot_png(renderer, path))
            if ok:
                written += 1
        with open(os.path.join(out_dir, f"{base}_{i:04d}.json"), "w") as fh:
            json.dump({"frame": i, "t": t, "duration": duration,
                       "n_tracks": len(timeline), "values": values,
                       "png": ok}, fh)
        frames.append({"frame": i, "t": t, "frame_file": base + f"_{i:04d}"})
    manifest = {"timeline": {"n_tracks": len(timeline), "duration": duration,
                             "loop": loop, "n_frames": n_frames},
                "frames": frames, "png_frames": written}
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest
