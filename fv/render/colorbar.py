"""Global Colorbar object (scPOST Colorbar) facade.

The global colorbar regulates the colour scale shared by every object. The
``ColorbarObject`` carries Gradation (``gradation``), colour scheme
(``color_map``), range mode (Auto/Fix with ``min``/``max``) and the
display/font settings.

This module applies the global settings onto a concrete ``vtkScalarBarActor``
and its lookup table (LUT). It stores the current global LUT so the renderer
pipeline can hand it to each contour mapper.
"""

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


def build_lut(gradation: int = 256, color_map: str = "Rainbow"):
    """vtkLookupTable for the shared colorbar band."""
    lut = vtk.vtkLookupTable()
    lut.SetNumberOfTableValues(max(2, int(gradation)))
    lut.Build()
    if str(color_map).lower() in ("gray", "grey"):
        _fill_gray(lut)
    elif str(color_map).lower() in ("invert", "reverse"):
        _fill_rainbow(lut, invert=True)
    else:
        _fill_rainbow(lut)
    return lut


def _fill_rainbow(lut, invert: bool = False):
    n = lut.GetNumberOfTableValues()
    hues = np.linspace(0.0, 0.8 if not invert else 0.8, n)
    if invert:
        hues = hues[::-1]
    cols = _hsv_to_rgb(np.column_stack((hues, np.ones(n), np.ones(n))))
    for i in range(n):
        lut.SetTableValue(i, cols[i][0], cols[i][1], cols[i][2], 1.0)


def _fill_gray(lut):
    n = lut.GetNumberOfTableValues()
    for i in range(n):
        v = i / max(1, n - 1)
        lut.SetTableValue(i, v, v, v, 1.0)


def _hsv_to_rgb(hsv: np.ndarray) -> np.ndarray:
    import colorsys
    rows = []
    for h, s, v in hsv:
        rows.append(colorsys.hsv_to_rgb(h, s, v))
    return np.asarray(rows, dtype=np.float64)


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
    sb.SetNumberOfLabels(7)
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
    fp = sb.GetLabelTextProperty()
    fp.SetFontFamilyToArial()
    fp.SetFontSize(max(8, int(getattr(obj, "font_size", 9) or 9)))
    fp.SetColor(0.0, 0.0, 0.0)
    tp = sb.GetTitleTextProperty()
    tp.SetFontFamilyToArial()
    tp.SetFontSize(max(8, int(getattr(obj, "font_size", 9) or 9)) + 2)
    tp.SetColor(0.0, 0.0, 0.0)
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