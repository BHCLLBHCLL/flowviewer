"""VR mode support (scPOST VR, 7d).

Availability detection plus real VR render-window backends.  VTK ships
several VR paths:

* OpenVR backend - vtkOpenVRRenderWindow / vtkOpenVRRenderer /
  vtkOpenVRRenderWindowInteractor / vtkOpenVRCamera (HTC Vive / Index /
  SteamVR headsets);
* OpenXR backend - vtkOpenXRRenderWindow / vtkOpenXRRenderer /
  vtkOpenXRRenderWindowInteractor / vtkOpenXRCamera (VTK >= 9.1);
* generic VR path - vtkVRRenderWindow (base class exposed by some builds).

``create_vr_window`` prefers OpenVR, then OpenXR, then the generic path;
it returns ``None`` when no backend can build a window so callers can
degrade to a normal 3D viewport.  ``vr_runtime_available`` reports whether
an OpenVR/OpenXR runtime DLL (SteamVR / WMR / Oculus loader) is present.
"""

from __future__ import annotations


def _vtk():
    """Import vtk, or None when unavailable."""
    try:
        import vtk
        return vtk
    except Exception:
        return None


def _dll_loadable(*names):
    """True when any named native DLL can be loaded (no HMD required)."""
    try:
        import ctypes
    except Exception:
        return False
    for n in names:
        try:
            ctypes.WinDLL(n)
            return True
        except Exception:
            continue
    return False


def vr_runtime_available() -> bool:
    """True when an OpenVR or OpenXR runtime DLL is loadable (7d)."""
    return _dll_loadable("openvr_api.dll", "vrclient_x64.dll",
                         "openxr_loader.dll")


def _has_openvr(vtk):
    return hasattr(vtk, "vtkOpenVRRenderWindow")


def _has_openxr(vtk):
    return hasattr(vtk, "vtkOpenXRRenderWindow")


def vr_available() -> bool:
    """True when any VTK VR backend is importable (7d)."""
    vtk = _vtk()
    if vtk is None:
        return False
    return _has_openvr(vtk) or _has_openxr(vtk) or hasattr(vtk, "vtkVRRenderWindow")


def vr_render_window_supported() -> bool:
    """True when a VTK VR render window class exists (any backend)."""
    return vr_available()


def vr_backend() -> str:
    """Detected backend name: openvr, openxr, generic or none."""
    vtk = _vtk()
    if vtk is None:
        return "none"
    if _has_openvr(vtk):
        return "openvr"
    if _has_openxr(vtk):
        return "openxr"
    if hasattr(vtk, "vtkVRRenderWindow"):
        return "generic"
    return "none"


def _apply_physical_scale(window, scale):
    """Set the VR world scale (metres per unit) when supported."""
    fn = getattr(window, "SetPhysicalScale", None)
    if fn is not None:
        try:
            fn(float(scale))
        except Exception:
            pass


def _attach_renderer(window, renderer, background):
    if renderer is not None:
        try:
            window.AddRenderer(renderer)
        except Exception:
            pass
        try:
            renderer.SetBackground(*background)
        except Exception:
            pass


def _make_backend(vtk, kind, renderer, background, physical_scale):
    """Shared construction for openvr / openxr windows."""
    win_cls = getattr(vtk, "vtkOpenVRRenderWindow" if kind == "openvr"
                    else "vtkOpenXRRenderWindow", None)
    if win_cls is None:
        return None
    try:
        win = win_cls()
        ren = renderer
        if ren is None:
            ren_cls = getattr(vtk, "vtkOpenVRRenderer" if kind == "openvr"
                              else "vtkOpenXRRenderer", None)
            if ren_cls is not None:
                ren = ren_cls()
        _attach_renderer(win, ren, background)
        iren = None
        iren_cls = getattr(vtk, "vtkOpenVRRenderWindowInteractor"
                           if kind == "openvr" else "vtkOpenXRRenderWindowInteractor", None)
        if iren_cls is not None:
            iren = iren_cls()
            iren.SetRenderWindow(win)
        camera = None
        if ren is not None:
            cam_cls = getattr(vtk, "vtkOpenVRCamera" if kind == "openvr"
                              else "vtkOpenXRCamera", None)
            if cam_cls is not None:
                camera = cam_cls()
                ren.SetActiveCamera(camera)
        _apply_physical_scale(win, physical_scale)
        try:
            win.Initialize()
        except Exception:
            pass
        return {"window": win, "interactor": iren, "camera": camera,
                "renderer": ren, "backend": kind}
    except Exception:
        return None


def _make_generic_backend(vtk, renderer, background, physical_scale):
    """Build a generic vtkVRRenderWindow path (fallback)."""
    if not hasattr(vtk, "vtkVRRenderWindow"):
        return None
    try:
        win = vtk.vtkVRRenderWindow()
        ren = renderer
        if ren is None and hasattr(vtk, "vtkVRRenderer"):
            ren = vtk.vtkVRRenderer()
        _attach_renderer(win, ren, background)
        _apply_physical_scale(win, physical_scale)
        try:
            win.Initialize()
        except Exception:
            pass
        return {"window": win, "interactor": None, "camera": None,
                "renderer": ren, "backend": "generic"}
    except Exception:
        return None


def create_vr_window(renderer=None, background=(0.1, 0.1, 0.1),
                     physical_scale=1.0):
    """Create a VR render window: OpenVR -> OpenXR -> generic fallback.

    Returns a dict with keys window/interactor/camera/renderer/backend,
    or ``None`` when no backend can build a window (no HMD driver).  Never
    raises: callers that get ``None`` fall back to a normal viewport.
    """
    vtk = _vtk()
    if vtk is None:
        return None
    for kind in ("openvr", "openxr"):
        handle = _make_backend(vtk, kind, renderer, background, physical_scale)
        if handle is not None:
            return handle
    return _make_generic_backend(vtk, renderer, background, physical_scale)


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
