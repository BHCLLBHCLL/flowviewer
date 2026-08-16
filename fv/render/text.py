"""Text / Bitmap object rendering (scPOST, P2.3).

Text draws a vtkTextActor in normalized display coordinates; Bitmap
pastes an image (PNG/JPEG/BMP) as a textured quad.  Both are 2D
overlays added as vtkActor2D / textured actor.
"""

from __future__ import annotations

from typing import Optional

import vtk


def text_actor(obj) -> Optional[object]:
    """Text annotation: 2D ``vtkTextActor`` (default) or a
    world-anchored ``vtkBillboardTextActor3D`` when ``anchor_3d`` (R3.4)."""
    if getattr(obj, "anchor_3d", False):
        return _text_actor_3d(obj)
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


def _text_actor_3d(obj):
    """Camera-facing, world-anchored text (R3.4)."""
    a = vtk.vtkBillboardTextActor3D()
    a.SetInput(getattr(obj, "text", "Text") or " ")
    tp = a.GetTextProperty()
    tp.SetFontSize(max(6, int(getattr(obj, "font_size", 14) or 14)))
    tp.SetBold(1)
    try:
        tp.SetColor(*getattr(obj, "color", (0.0, 0.0, 0.0)))
    except (TypeError, IndexError):
        tp.SetColor(0.0, 0.0, 0.0)
    pos = getattr(obj, "anchor_position", (0.0, 0.0, 0.0))
    a.SetPosition(float(pos[0]), float(pos[1]), float(pos[2]))
    return a


def bitmap_uv_corners(scale, offset):
    """Four (u, v) texture coordinates for a bitmap quad with UV tiling (9).

    vtkPlaneSource emits four points in order (origin, point1, point2,
    opposite corner); each maps to a texture coordinate scaled by ``scale``
    and shifted by ``offset``.
    """
    us, vs = (float(scale[0]), float(scale[1])) if scale else (1.0, 1.0)
    uo, vo = (float(offset[0]), float(offset[1])) if offset else (0.0, 0.0)
    return [(uo, vo), (uo + us, vo), (uo, vo + vs), (uo + us, vo + vs)]


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
    uv = bitmap_uv_corners(
        getattr(obj, "uv_scale", (1.0, 1.0)),
        getattr(obj, "uv_offset", (0.0, 0.0)))
    tcoords = vtk.vtkFloatArray()
    tcoords.SetNumberOfComponents(2)
    tcoords.SetNumberOfTuples(4)
    for i, (u, v) in enumerate(uv):
        tcoords.SetTuple2(i, u, v)
    plane.GetOutput().GetPointData().SetTCoords(tcoords)
    tex.SetRepeat(True)
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(plane.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.SetTexture(tex)
    if getattr(obj, "transparent", False):
        actor.GetProperty().SetOpacity(0.5)
    return actor