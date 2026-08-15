"""VR mode support (scPOST VR, 7d).

Availability detection plus a real VR render-window backend.  VTK ships
two VR paths:

* OpenVR backend  - vtkOpenVRRenderWindow / vtkOpenVRRenderer /
  vtkOpenVRRenderWindowInteractor / vtkOpenVRCamera (HTC Vive / Index /
  SteamVR headsets);
* generic VR path - vtkVRRenderWindow (base class exposed by some builds).

``create_vr_window`` prefers the OpenVR backend and falls back to the
generic window; it returns ``None`` when neither is importable so callers
can degrade to a normal 3D viewport.  VR rendering also needs an HMD
driver (SteamVR), so construction is best-effort and never raises.
"""

from __future__ import annotations


def _vtk():
    """Import vtk, or None when unavailable."""
    try:
        import vtk
        return vtk
    except Exception:
        return None


def vr_available() -> bool:
    """True when a VTK OpenVR/VR backend is importable (7d)."""
    vtk = _vtk()
    if vtk is None:
        return False
    return (hasattr(vtk, "vtkOpenVRRenderWindow")
            or hasattr(vtk, "vtkVRRenderWindow"))


def vr_render_window_supported() -> bool:
    """True when a VTK VR render window class exists (any backend)."""
    vtk = _vtk()
    if vtk is None:
        return False
    return (hasattr(vtk, "vtkOpenVRRenderWindow")
            or hasattr(vtk, "vtkVRRenderWindow"))


def vr_backend() -> str:
    """Name of the detected VR backend: openvr, generic or none."""
    vtk = _vtk()
    if vtk is None:
        return "none"
    if hasattr(vtk, "vtkOpenVRRenderWindow"):
        return "openvr"
    if hasattr(vtk, "vtkVRRenderWindow"):
        return "generic"
    return "none"


def _configure_common(window, renderer, background):
    """Attach a renderer and set the background colour (best-effort)."""
    if renderer is not None:
        try:
            window.AddRenderer(renderer)
        except Exception:
            pass
        try:
            renderer.SetBackground(*background)
        except Exception:
            pass


def _make_openvr_backend(vtk, renderer, background):
    """Build the OpenVR window + interactor + camera (preferred path)."""
    if not hasattr(vtk, "vtkOpenVRRenderWindow"):
        return None
    try:
        win = vtk.vtkOpenVRRenderWindow()
        ren = renderer
        if ren is None and hasattr(vtk, "vtkOpenVRRenderer"):
            ren = vtk.vtkOpenVRRenderer()
        if ren is not None:
            win.AddRenderer(ren)
            try:
                ren.SetBackground(*background)
            except Exception:
                pass
        iren = None
        if hasattr(vtk, "vtkOpenVRRenderWindowInteractor"):
            iren = vtk.vtkOpenVRRenderWindowInteractor()
            iren.SetRenderWindow(win)
        camera = None
        if ren is not None and hasattr(vtk, "vtkOpenVRCamera"):
            camera = vtk.vtkOpenVRCamera()
            ren.SetActiveCamera(camera)
        try:
            win.Initialize()
        except Exception:
            pass
        return {"window": win, "interactor": iren, "camera": camera,
                "renderer": ren, "backend": "openvr"}
    except Exception:
        return None


def _make_generic_backend(vtk, renderer, background):
    """Build a generic vtkVRRenderWindow path (fallback)."""
    if not hasattr(vtk, "vtkVRRenderWindow"):
        return None
    try:
        win = vtk.vtkVRRenderWindow()
        ren = renderer
        if ren is None and hasattr(vtk, "vtkVRRenderer"):
            ren = vtk.vtkVRRenderer()
        if ren is not None:
            try:
                win.AddRenderer(ren)
            except Exception:
                pass
            try:
                ren.SetBackground(*background)
            except Exception:
                pass
        try:
            win.Initialize()
        except Exception:
            pass
        return {"window": win, "interactor": None, "camera": None,
                "renderer": ren, "backend": "generic"}
    except Exception:
        return None


def create_vr_window(renderer=None, background=(0.1, 0.1, 0.1)):
    """Create a VR render window, preferring OpenVR then the generic path.

    Returns a dict with keys window/interactor/camera/renderer/backend,
    or ``None`` when no VR backend is available.  Never raises: callers
    that get ``None`` should fall back to a normal viewport.
    """
    vtk = _vtk()
    if vtk is None:
        return None
    handle = _make_openvr_backend(vtk, renderer, background)
    if handle is None:
        handle = _make_generic_backend(vtk, renderer, background)
    return handle


def release_vr_window(handle) -> bool:
    """Finalize / delete a VR window handle returned by create_vr_window."""
    if not handle:
        return False
    win = handle.get("window")
    if win is None:
        return False
    for meth in ("Finalize", "Delete"):
        fn = getattr(win, meth, None)
        if fn is not None:
            try:
                fn()
            except Exception:
                pass
    return True
