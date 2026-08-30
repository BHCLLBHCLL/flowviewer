"""Measure (scPOST Measure, C2) - distance / angle between picked points."""

from __future__ import annotations

import numpy as np

try:
    import vtk
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    vtk = None


def distance(p1, p2) -> float:
    """Euclidean distance between two points."""
    return float(np.linalg.norm(np.asarray(p1) - np.asarray(p2)))


def angle(p1, p2, p3) -> float:
    """Angle (degrees) at p2 formed by p1-p2-p3."""
    v1 = np.asarray(p1) - np.asarray(p2)
    v2 = np.asarray(p3) - np.asarray(p2)
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-12 or n2 < 1e-12:
        return 0.0
    c = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
    return float(np.degrees(np.arccos(c)))


def compute(obj) -> str:
    """Human-readable result for a MeasureObject's points."""
    pts = list(getattr(obj, "points", None) or [])
    mode = (getattr(obj, "mode", "Distance") or "Distance")
    if mode.lower().startswith("angle"):
        if len(pts) < 3:
            return "Angle needs 3 points"
        return "Angle: " + str(angle(pts[0], pts[1], pts[2])) + " deg"
    if len(pts) < 2:
        return "Distance needs 2 points"
    return "Distance: " + str(distance(pts[0], pts[1])) + " m"

def ratio(m1, m2) -> float:
    """Scale ratio = distance(m1) / distance(m2) between two measures (9).

    Each measure must have at least two points; returns 0.0 when the
    denominator is ~zero.  Mirrors scPOST Compare Scales.
    """
    d1 = _measure_distance(m1)
    d2 = _measure_distance(m2)
    if d2 < 1e-12:
        return 0.0
    return d1 / d2


def _measure_distance(m) -> float:
    pts = list(getattr(m, "points", None) or [])
    if len(pts) < 2:
        return 0.0
    return distance(pts[0], pts[1])


def compute_ratio(obj, other) -> str:
    """Human-readable ratio result comparing two MeasureObjects (9)."""
    r = ratio(obj, other)
    return "Scale ratio: " + format(r, ".6g") + "x"


def build_measure_actors(ff, obj) -> dict:
    """R1.3: 3D line(s) + billboard label for a Measure object.

    Distance draws a single segment between the first two points; Angle
    draws two segments meeting at the vertex and labels the angle value.
    ``ff`` is accepted for signature parity but unused.
    """
    out: dict = {}
    if not _HAS_VTK:
        return out
    pts = list(getattr(obj, "points", None) or [])
    mode = (getattr(obj, "mode", "Distance") or "Distance").lower()
    text = compute(obj)
    label = None
    if mode.startswith("angle"):
        if len(pts) < 3:
            return out
        a = _line_actor(pts[0], pts[1])
        b = _line_actor(pts[1], pts[2])
        if a is not None:
            out["line1"] = a
        if b is not None:
            out["line2"] = b
        label = _label_actor(text, pts[1])
    else:
        if len(pts) < 2:
            return out
        seg = _line_actor(pts[0], pts[1])
        if seg is not None:
            out["line"] = seg
        mid = tuple((pts[0][i] + pts[1][i]) / 2.0 for i in range(3))
        label = _label_actor(text, mid)
    if label is not None:
        out["label"] = label
    return out


def _line_actor(p1, p2):
    """Red line segment between two world points (R1.3)."""
    src = vtk.vtkLineSource()
    src.SetPoint1(*p1)
    src.SetPoint2(*p2)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(src.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(1.0, 0.0, 0.0)
    actor.GetProperty().SetLineWidth(2.0)
    return actor


def _label_actor(text: str, pos):
    """Camera-facing billboard label anchored at a world point (R1.3)."""
    ta = vtk.vtkBillboardTextActor3D()
    ta.SetInput(text)
    ta.SetPosition(*pos)
    tp = ta.GetTextProperty()
    tp.SetFontSize(14)
    tp.SetColor(1.0, 0.0, 0.0)
    tp.BoldOn()
    return ta
