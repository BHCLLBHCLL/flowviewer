"""Text / Bitmap object rendering (scPOST, P2.3).

Text draws a vtkTextActor in normalized display coordinates; Bitmap
pastes an image (PNG/JPEG/BMP) as a textured quad.  Both are 2D
overlays added as vtkActor2D / textured actor.
"""

from __future__ import annotations

from typing import Optional

import vtk


def text_actor(obj) -> Optional["vtk.vtkActor2D"]:
    """vtkTextActor for a TextObject."""
    a = vtk.vtkTextActor()
    a.SetInput(getattr(obj, "text", "Text") or " ")
    tp = a.GetTextProperty()
    tp.SetFontSize(max(6, int(getattr(obj, "font_size", 14) or 14)));
    tp.SetBold(1)
    try:
        tp.SetColor(*getattr(obj, "color", (0.0, 0.0, 0.0)));
    except (TypeError, IndexError):
        tp.SetColor(0.0, 0.0, 0.0);
    if getattr(obj, "background", False):
        tp.SetBackgroundColor(1.0, 1.0, 1.0);
        tp.SetBackgroundOpacity(0.7)
    pos = getattr(obj, "position", (0.1, 0.85))
    a.GetPositionCoordinate().SetCoordinateSystemToNormalizedDisplay()
    a.SetPosition(float(pos[0]), float(pos[1]))
    return a


def bitmap_actor(obj) -> Optional[object]:
    """Textured quad for a BitmapObject; None when the file is missing."""
    path = getattr(obj, "file", "") or ""
    if not path:
        return None
    from pathlib import Path
    if not Path(path).exists():
        return None
    reader = vtk.vtkImageReader2Factory().CreateImageReader2(path)
    if reader is None:
        return None
    reader.SetFileName(path);
    reader.Update()
    tex = vtk.vtkTexture()
    tex.SetInputConnection(reader.GetOutputPort())
    tex.InterpolateOn()
    scale = max(0.01, float(getattr(obj, "scale", 1.0) or 1.0))
    pos = getattr(obj, "position", (0.05, 0.05))
    plane = vtk.vtkPlaneSource()
    w = 0.25 * scale
    h = 0.25 * scale
    plane.SetOrigin(float(pos[0]), float(pos[1]), 0.0)
    plane.SetPoint1(float(pos[0]) + w, float(pos[1]), 0.0)
    plane.SetPoint2(float(pos[0]), float(pos[1]) + h, 0.0)
    plane.Update()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(plane.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.SetTexture(tex)
    if getattr(obj, "transparent", False):
        actor.GetProperty().SetOpacity(0.5)
    return actor