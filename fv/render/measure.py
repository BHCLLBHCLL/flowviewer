"""Measure (scPOST Measure, C2) - distance / angle between picked points."""

from __future__ import annotations

import numpy as np


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