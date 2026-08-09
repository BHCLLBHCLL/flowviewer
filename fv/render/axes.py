"""Orientation marker / axes triad for the Draw Window (cabdecoding style)."""

from __future__ import annotations

try:
    import vtk
    _HAS_VTK = True
except Exception:  # pragma: no cover
    vtk = None
    _HAS_VTK = False

# Magenta / green / blue — matches Cradle Draw Window gnomon
_AXIS_COLOR_X = (0.90, 0.20, 0.55)
_AXIS_COLOR_Y = (0.15, 0.72, 0.22)
_AXIS_COLOR_Z = (0.18, 0.40, 0.95)


def axes_actor(length: float = 1.0):
    """XYZ orientation triad (shaft + cone tip)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    axes = vtk.vtkAxesActor()
    axes.SetTotalLength(length, length, length)
    axes.SetShaftTypeToCylinder()
    try:
        axes.SetNormalizedShaftLength(0.70, 0.70, 0.70)
        axes.SetNormalizedTipLength(0.30, 0.30, 0.30)
    except Exception:
        pass
    axes.SetCylinderRadius(0.035)
    axes.SetConeRadius(0.12)
    axes.SetConeResolution(20)
    axes.SetCylinderResolution(16)
    axes.AxisLabelsOn()
    axes.SetXAxisLabelText("x")
    axes.SetYAxisLabelText("y")
    axes.SetZAxisLabelText("z")
    for getter, color in (
            (axes.GetXAxisShaftProperty, _AXIS_COLOR_X),
            (axes.GetXAxisTipProperty, _AXIS_COLOR_X),
            (axes.GetYAxisShaftProperty, _AXIS_COLOR_Y),
            (axes.GetYAxisTipProperty, _AXIS_COLOR_Y),
            (axes.GetZAxisShaftProperty, _AXIS_COLOR_Z),
            (axes.GetZAxisTipProperty, _AXIS_COLOR_Z)):
        try:
            prop = getter()
            prop.SetColor(*color)
            prop.SetAmbient(0.4)
            prop.SetDiffuse(0.7)
        except Exception:
            pass
    for cap, color in (
            (axes.GetXAxisCaptionActor2D(), _AXIS_COLOR_X),
            (axes.GetYAxisCaptionActor2D(), _AXIS_COLOR_Y),
            (axes.GetZAxisCaptionActor2D(), _AXIS_COLOR_Z)):
        try:
            tp = cap.GetCaptionTextProperty()
            tp.SetFontSize(16)
            tp.SetBold(1)
            tp.ShadowOff()
            tp.SetColor(*color)
            cap.SetWidth(0.12)
            cap.SetHeight(0.08)
        except Exception:
            pass
    return axes


def orientation_marker_widget(interactor, size_frac: float = 0.15,
                              corner: str = "top-right"):
    """Screen-space XYZ marker (scPOST Draw Window gnomon)."""
    if not _HAS_VTK:
        raise RuntimeError("vtk is not installed")
    widget = vtk.vtkOrientationMarkerWidget()
    widget.SetOrientationMarker(axes_actor())
    widget.SetInteractor(interactor)
    f = float(size_frac)
    if corner == "top-right":
        widget.SetViewport(1.0 - f, 1.0 - f, 1.0, 1.0)
    else:
        widget.SetViewport(0.0, 0.0, f, f)
    widget.SetEnabled(1)
    widget.InteractiveOff()
    return widget


def plane_view_camera(plane: str, *, negative: bool = False
                      ) -> tuple[tuple[float, float, float],
                                 tuple[float, float, float]]:
    """Camera (position, view_up) for an orthogonal plane view."""
    sign = -1.0 if negative else 1.0
    p = (plane or "").lower()
    if p in ("xy", "z"):
        return (0.0, 0.0, sign), (0.0, 1.0, 0.0)
    if p in ("xz", "y"):
        return (0.0, sign, 0.0), (0.0, 0.0, 1.0)
    # yz / x
    return (sign, 0.0, 0.0), (0.0, 0.0, 1.0)


def iso_metric_camera() -> tuple[tuple[float, float, float],
                                 tuple[float, float, float]]:
    """Isometric view—camera along the (+,+,+) diagonal, Z-up-ish."""
    pos = (1.0, 1.0, 1.0)
    up = (0.0, 0.0, 1.0)
    return pos, up
