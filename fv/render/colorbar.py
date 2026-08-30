"""Global Colorbar object (scPOST Colorbar) facade.

The global colorbar regulates the colour scale shared by every object. The
``ColorbarObject`` carries Gradation (``gradation``), colour scheme
(``color_map``), range mode (Auto/Fix with ``min``/``max``) and the
display/font settings.

This module applies the global settings onto a concrete ``vtkScalarBarActor``
and its lookup table (LUT). It stores the current global LUT so the renderer
pipeline can hand it to each contour mapper.
"""

import csv
from typing import Optional

import numpy as np

try:
    import vtk
    from vtk.util import numpy_support as _vns
    _HAS_VTK = True
except Exception:  # pragma: no cover - headless / no vtk
    _HAS_VTK = False
    _vns = None


class ColorbarRegistry:
    """Process-wide global colorbar state (LUT + actor factory)."""

    _lut = None                     # vtkLookupTable shared by all mappers
    _gradation = 256

    @classmethod
    def lut(cls) -> "vtk.vtkLookupTable":
        if cls._lut is None or cls._lut.GetNumberOfTableValues() != \
                cls._gradation:
            cls._lut = build_lut(cls._gradation, "Rainbow")
        return cls._lut

    @classmethod
    def reset(cls) -> None:
        cls._lut = None


# R1.4: named colormaps defined by RGB control points (t -> (r, g, b)).
_COLORMAPS = {
    "rainbow": [(0.0, (0.0, 0.0, 1.0)), (0.25, (0.0, 1.0, 1.0)),
                (0.5, (0.0, 1.0, 0.0)), (0.75, (1.0, 1.0, 0.0)),
                (1.0, (1.0, 0.0, 0.0))],
    "jet": [(0.0, (0.0, 0.0, 0.5)), (0.125, (0.0, 0.0, 1.0)),
            (0.375, (0.0, 1.0, 1.0)), (0.625, (1.0, 1.0, 0.0)),
            (0.875, (1.0, 0.0, 0.0)), (1.0, (0.5, 0.0, 0.0))],
    "hot": [(0.0, (0.0, 0.0, 0.0)), (0.35, (1.0, 0.0, 0.0)),
            (0.66, (1.0, 1.0, 0.0)), (1.0, (1.0, 1.0, 1.0))],
    "cool": [(0.0, (0.0, 1.0, 1.0)), (1.0, (1.0, 0.0, 1.0))],
    "turbo": [(0.0, (0.190, 0.071, 0.232)), (0.25, (0.133, 0.473, 0.918)),
              (0.5, (0.134, 0.829, 0.643)), (0.75, (0.906, 0.754, 0.112)),
              (1.0, (0.479, 0.015, 0.010))],
    "viridis": [(0.0, (0.267, 0.005, 0.329)), (0.25, (0.282, 0.318, 0.537)),
                (0.5, (0.192, 0.499, 0.483)), (0.75, (0.383, 0.700, 0.345)),
                (1.0, (0.993, 0.906, 0.144))],
    "parula": [(0.0, (0.208, 0.166, 0.529)), (0.25, (0.037, 0.446, 0.830)),
               (0.5, (0.023, 0.688, 0.733)), (0.75, (0.761, 0.700, 0.197)),
               (1.0, (0.977, 0.920, 0.089))],
    "dst": [(0.0, (0.0, 0.00, 0.50)), (0.25, (0.0, 0.55, 1.0)),
            (0.5, (0.15, 1.0, 0.55)), (0.75, (1.0, 0.85, 0.0)),
            (1.0, (0.85, 0.0, 0.0))],
}
_COLORMAPS["spectrum"] = _COLORMAPS["rainbow"]


def build_lut(gradation: int = 256, color_map: str = "Rainbow"):
    """vtkLookupTable for the shared colorbar band (R1.4 expanded maps)."""
    lut = vtk.vtkLookupTable()
    lut.SetNumberOfTableValues(max(2, int(gradation)))
    lut.Build()
    key = str(color_map).lower()
    if key in ("gray", "grey"):
        _fill_gray(lut)
        return lut
    invert = key in ("invert", "reverse")
    ctrl = _COLORMAPS.get(key, _COLORMAPS["rainbow"])
    _fill_from_control_points(lut, ctrl, invert=invert)
    return lut


def _fill_from_control_points(lut, ctrl, invert: bool = False):
    """Fill a LUT by linear interpolation of RGB control points (R1.4)."""
    n = lut.GetNumberOfTableValues()
    pts = [(1.0 - t, c) for t, c in reversed(ctrl)] if invert else list(ctrl)
    xs = np.array([t for t, _ in pts], dtype=np.float64)
    cs = np.array([c for _, c in pts], dtype=np.float64)
    for i in range(n):
        t = i / max(1, n - 1)
        j = int(np.searchsorted(xs, t, side="right")) - 1
        j = max(0, min(j, len(xs) - 2))
        f = float(np.clip((t - xs[j]) / max(xs[j + 1] - xs[j], 1e-12), 0.0, 1.0))
        c = cs[j] * (1.0 - f) + cs[j + 1] * f
        lut.SetTableValue(i, float(c[0]), float(c[1]), float(c[2]), 1.0)


def _fill_gray(lut):
    n = lut.GetNumberOfTableValues()
    for i in range(n):
        v = i / max(1, n - 1)
        lut.SetTableValue(i, v, v, v, 1.0)


def colorbar_actor(obj, range_: Optional[tuple] = None,
                   ) -> Optional["vtk.vtkScalarBarActor"]:
    """Global ``vtkScalarBarActor`` for the ColorbarObject.

    ``range_`` (optional) sets the LUT range (Fix mode). Honors
    ``obj.orientation`` and ``obj.position``.
    """
    if not _HAS_VTK:
        return None
    lut = ColorbarRegistry.lut()
    if range_ is not None:
        lo = float(range_[0])
        hi = max(float(range_[1]), lo + 1e-12)
        lut.SetRange(lo, hi)
        lut.Build()
    sb = vtk.vtkScalarBarActor()
    sb.SetLookupTable(lut)
    sb.SetNumberOfLabels(max(2, int(getattr(obj, "num_labels", 7) or 7)))
    sb.SetMaximumNumberOfColors(lut.GetNumberOfTableValues())
    orient = (getattr(obj, "orientation", "Horizontal") or "Horizontal")
    if str(orient).lower().startswith("v"):
        sb.SetOrientationToVertical()
    else:
        sb.SetOrientationToHorizontal()
    pos = tuple(getattr(obj, "position", (0.12, 0.03)))
    sb.SetPosition(*pos)
    if getattr(obj, "show_title", True):
        title = getattr(obj, "title", "") or ""
    else:
        title = ""
    if title:
        sb.SetTitle(title)
    lc = tuple(getattr(obj, "label_color", (0.0, 0.0, 0.0)))
    fp = sb.GetLabelTextProperty()
    fp.SetFontFamilyToArial()
    fp.SetFontSize(max(8, int(getattr(obj, "font_size", 9) or 9)))
    fp.SetColor(float(lc[0]), float(lc[1]), float(lc[2]))
    tp = sb.GetTitleTextProperty()
    tp.SetFontFamilyToArial()
    tp.SetFontSize(max(8, int(getattr(obj, "font_size", 9) or 9)) + 2)
    tp.SetColor(float(lc[0]), float(lc[1]), float(lc[2]))
    sb.SetLabelFormat(getattr(obj, "label_format", "%.4g") or "%.4g")
    return sb


def apply_to_mapper(mapper, obj, range_: Optional[tuple] = None) -> None:
    """Point a mapper at the global LUT / range (Auto or Fix)."""
    if mapper is None:
        return
    mapper.SetLookupTable(ColorbarRegistry.lut())
    mode = (getattr(obj, "range_mode", "Auto") or "Auto")
    if mode.lower() == "fix":
        lo = float(getattr(obj, "min", 0.0))
        hi = max(float(getattr(obj, "max", 1.0)), lo + 1e-12)
        mapper.SetScalarRange(lo, hi)



# ── R3.7 color-table editor: control points + CSV ──────────────────────────

def normalize_control_points(points):
    """Sort/clamp/dedupe control points ``[(t, (r, g, b)), ...]`` and force
    the ``[0, 1]`` endpoints so the table always spans the full range."""
    pts = []
    for t, rgb in points:
        r, g, b = rgb
        t = min(1.0, max(0.0, float(t)))
        r = min(1.0, max(0.0, float(r)))
        g = min(1.0, max(0.0, float(g)))
        b = min(1.0, max(0.0, float(b)))
        pts.append((t, (r, g, b)))
    dedup = {}
    for t, c in pts:
        dedup[round(t, 9)] = (t, c)
    pts = sorted(dedup.values(), key=lambda p: p[0])
    if not pts:
        pts = [(0.0, (0.0, 0.0, 1.0)), (1.0, (1.0, 0.0, 0.0))]
    if pts[0][0] > 0.0:
        pts.insert(0, (0.0, pts[0][1]))
    if pts[-1][0] < 1.0:
        pts.append((1.0, pts[-1][1]))
    return pts


def add_control_point(points, t, rgb):
    """Return a normalized table with ``(t, rgb)`` inserted."""
    return normalize_control_points(list(points) + [(t, rgb)])


def remove_control_point(points, t):
    """Return a normalized table without the control point nearest ``t``."""
    keep = [(tt, c) for tt, c in points if abs(tt - float(t)) > 1e-9]
    return normalize_control_points(keep)


def register_colormap(name, points):
    """Register a custom named colormap from control points (R3.7)."""
    key = str(name).strip().lower()
    _COLORMAPS[key] = normalize_control_points(points)
    ColorbarRegistry.reset()
    return key


def unregister_colormap(name):
    """Remove a custom colormap (built-ins are kept)."""
    key = str(name).strip().lower()
    builtin = {"rainbow", "spectrum", "jet", "hot", "cool",
               "turbo", "viridis", "parula"}
    if key in _COLORMAPS and key not in builtin:
        del _COLORMAPS[key]
        ColorbarRegistry.reset()
        return True
    return False


def list_colormaps():
    """All selectable colormap names (built-ins + custom)."""
    names = set(_COLORMAPS.keys())
    names.update(("gray", "grey", "invert", "reverse"))
    return sorted(names)


def colormap_control_points(name):
    """Control points for a named colormap (rainbow fallback)."""
    key = str(name).strip().lower()
    return _COLORMAPS.get(key, _COLORMAPS["rainbow"])


def load_colormap_csv(path):
    """Import control points from a CSV (``t,r,g,b`` per row; header skipped)."""
    pts = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if not row or not str(row[0]).strip():
                continue
            try:
                t = float(row[0])
            except ValueError:
                continue  # header / non-numeric row
            if len(row) >= 4:
                pts.append((t, (float(row[1]), float(row[2]), float(row[3]))))
            else:
                pts.append((t, (t, t, t)))  # gray ramp from a single value
    return normalize_control_points(pts)


def save_colormap_csv(path, points):
    """Export control points to a CSV (``t,r,g,b`` with a header row)."""
    pts = normalize_control_points(points)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["t", "r", "g", "b"])
        for t, (r, g, b) in pts:
            w.writerow([f"{t:.6g}", f"{r:.6g}", f"{g:.6g}", f"{b:.6g}"])
    return str(path)
