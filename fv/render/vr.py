"""VR mode support (scPOST VR, 7d) - availability detection + render window.
"""

from __future__ import annotations


def vr_available() -> bool:
    """True when a VTK OpenVR/VR backend is importable (7d)."""
    try:
        import vtkmodules.vtkRenderingOpenVR  # noqa: F401
        return True
    except Exception:
        return False


def vr_render_window_supported() -> bool:
    """True when vtkVRRenderWindow exists (generic VR path)."""
    try:
        import vtk
        return hasattr(vtk, "vtkVRRenderWindow")
    except Exception:
        return False