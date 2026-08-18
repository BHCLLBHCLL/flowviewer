"""COM automation interface (scPOST VBS/COM, 7c) via pywin32.

Exposes a flowviewer.Application COM class with:

* lifecycle  - open_file / close / quit / release and context-manager use;
* properties - version, file_path, kind, n_cells, n_vertices, cycle, time,
  variable_names, has_file (read-only attributes);
* events     - a real IConnectionPointContainer / IConnectionPoint pair
  (QueryInterface-visible, following the pywin32 ConnectableServer pattern)
  so both VBS WithEvents clients and win32com.client.connect.SimpleConnection
  can receive on_open / on_close.

Requires pywin32; registration writes to the Windows registry (run
register_server() with the right privileges).
"""

from __future__ import annotations

import threading

try:
    import pythoncom  # noqa: F401
    import win32com.server.register  # noqa: F401
    _HAS_COM = True
except Exception:
    _HAS_COM = False

VERSION = "1.0.0"
EVENTS_IID = "{E1A2B3C4-5D6E-4F7A-8B9C-0D1E2F3A4B5C}"

try:
    from .com_typelib import ensure_typelib, TYPELIB_GUID
    _TYPLIB_FILE = ensure_typelib()
except Exception:
    TYPELIB_GUID = "{F1A2B3C4-5D6E-4F7A-8B9C-0D1E2F3A4B5D}"
    _TYPLIB_FILE = None


# ── COM→GUI bridge singleton (R2.7) ──────────────────────────────────────

_BRIDGE = {"gui": None}


def attach_gui(instance):
    """Register a running FlowViewer instance for COM→GUI forwarding."""
    _BRIDGE["gui"] = instance


def detach_gui(instance=None):
    """Unregister the running FlowViewer instance (by identity when given)."""
    if instance is None or _BRIDGE["gui"] is instance:
        _BRIDGE["gui"] = None


def _bridge_gui():
    """The currently attached FlowViewer instance, or None (headless)."""
    return _BRIDGE["gui"]


class FlowviewerApplicationEvents:
    """COM event (outgoing) interface contract for VBS WithEvents (3).

    The sink object a client registers must implement::

        on_open(path)   # fired after open_file loads a file
        on_close()      # fired after close()/quit() releases it
    """

    _reg_clsid_ = EVENTS_IID
    _public_methods_ = ["on_open", "on_close"]


def _iid_matches(a, b):
    """Compare GUIDs (str or PyIID), ignoring case and optional braces."""
    a = str(a or "").strip().strip("{}").lower()
    b = str(b or "").strip().strip("{}").lower()
    return a == b


class ConnectionPoint:
    """IConnectionPoint + IConnectionPointContainer in one object (3).

    Follows the pywin32 ConnectableServer pattern: the same object answers
    both interfaces, _connect_interfaces_ names the outgoing event interface,
    and the owning application forwards QI via its _query_interface_.
    Advise accepts a COM sink (QueryInterface to the event IID) and falls
    back to a plain Python callable for the non-COM smoke tests.
    """

    _public_methods_ = [
        "EnumConnectionPoints", "FindConnectionPoint",
        "EnumConnections", "Unadvise", "Advise",
        "GetConnectionPointContainer", "GetConnectionInterface",
    ]
    _connect_interfaces_ = [EVENTS_IID]
    _DISPIDS = {"on_open": 1000, "on_close": 1001}

    def __init__(self, owner):
        self._owner = owner
        self._lock = threading.RLock()
        self._sinks = {}
        self._next = 1
        if _HAS_COM:
            try:
                import pythoncom as _pc
                self._com_interfaces_ = [
                    _pc.IID_IConnectionPoint,
                    _pc.IID_IConnectionPointContainer,
                ]
            except Exception:
                pass

    # IConnectionPointContainer

    def EnumConnectionPoints(self):
        """The single outgoing connection point (COM-facing, wrapped)."""
        import win32com.server.util
        return [win32com.server.util.wrap(self)]

    def FindConnectionPoint(self, iid):
        """Return the connection point for the event IID (COM-facing)."""
        if not _iid_matches(iid, EVENTS_IID):
            return None
        import win32com.server.util
        return win32com.server.util.wrap(self)

    # IConnectionPoint

    def GetConnectionInterface(self):
        """The IID of the outgoing event interface."""
        return EVENTS_IID

    def GetConnectionPointContainer(self):
        """The container owning this point (the point itself here)."""
        import win32com.server.util
        return win32com.server.util.wrap(self)

    def Advise(self, sink):
        """Register a sink; returns an opaque connection cookie."""
        if sink is None:
            return 0
        stored = sink
        if _HAS_COM:
            try:
                import pythoncom as _pc
                stored = sink.QueryInterface(
                    self._connect_interfaces_[0], _pc.IID_IDispatch)
            except Exception:
                stored = sink  # plain Python sink fallback
        with self._lock:
            cookie = self._next
            self._next += 1
            self._sinks[cookie] = stored
            return cookie

    def Unadvise(self, cookie):
        """Remove a sink by cookie; returns True when it existed."""
        with self._lock:
            return self._sinks.pop(cookie, None) is not None

    def EnumConnections(self):
        """Snapshot of currently advised sinks (IEnumConnections)."""
        with self._lock:
            return list(self._sinks.values())

    # event dispatch

    def sinks(self):
        """Alias of EnumConnections for the Python dispatcher."""
        return self.EnumConnections()

    def clear(self):
        """Drop every advised sink."""
        with self._lock:
            self._sinks.clear()

    def fire(self, event_name, *args):
        """Deliver an event to every sink without one breaking others."""
        dispid = self._DISPIDS.get(event_name)
        with self._lock:
            targets = list(self._sinks.values())
        for sink in targets:
            try:
                if dispid is not None and hasattr(sink, "Invoke"):
                    # COM IDispatch sink: DISPATCH_METHOD with reversed args
                    import pythoncom as _pc
                    if args:
                        sink.Invoke(dispid, 0, _pc.DISPATCH_METHOD,
                                    len(args), *reversed(args))
                    else:
                        sink.Invoke(dispid, 0, _pc.DISPATCH_METHOD, 0)
                else:
                    handler = getattr(sink, event_name, None)
                    if handler is None:
                        # VBS case-insensitive fallback (OnOpen / OnClose)
                        for cand in dir(sink):
                            if cand.lower() == event_name.replace("_", "").lower():
                                handler = getattr(sink, cand, None)
                                break
                    if handler is not None:
                        handler(*args)
                    else:
                        payload = {"event": event_name}
                        if args:
                            payload["args"] = args
                        sink(payload)
            except Exception:
                continue


class MessageWindowClass:
    """COM Message Window (scPOST MessageWindow class, r12.1).

    Wraps the attached GUI message pane when present; otherwise keeps an
    in-process message list so headless COM scripts still get the log.
    """

    _public_methods_ = ["AddMessage", "GetMessages", "Clear",
                        "SaveLogFile"]
    _public_attrs_ = ["Count"]

    def __init__(self, app):
        self._app = app
        self._messages = []

    def AddMessage(self, msg, level="INFO"):
        """Append a message line (shown in the GUI message window)."""
        line = str(msg)
        self._messages.append((str(level), line))
        gui = _bridge_gui()
        msg_win = getattr(gui, "message_win", None) if gui else None
        if msg_win is not None and hasattr(msg_win, "log"):
            try:
                msg_win.log(line, str(level))
            except Exception:
                pass
        return True

    def GetMessages(self):
        """All recorded message lines as [(level, text), ...]."""
        return list(self._messages)

    def Clear(self):
        """Clear the message list (and the GUI pane when attached)."""
        self._messages = []
        gui = _bridge_gui()
        msg_win = getattr(gui, "message_win", None) if gui else None
        if msg_win is not None and hasattr(msg_win, "clear"):
            try:
                msg_win.clear()
            except Exception:
                pass
        return True

    def SaveLogFile(self, path):
        """Write the recorded messages to *path* (one line each)."""
        try:
            with open(str(path), "w", encoding="utf-8") as fh:
                for level, text in self._messages:
                    fh.write(f"[{level}] {text}\n")
            return True
        except Exception:
            return False

    @property
    def Count(self):
        return len(self._messages)


class GlobalWindowClass:
    """COM Global Window (scPOST GlobalWindow class, r12.1).

    Holds the process-wide Colorbar / Gradation / Camera / Light global
    objects; forwards to the attached GUI's global window, falling back
    to a headless model instance.
    """

    _public_methods_ = ["GetColorbar", "GetGradation", "GetCamera",
                        "GetLight", "SetLight"]

    def __init__(self, app):
        self._app = app
        self._model = None

    def _gw(self):
        gui = _bridge_gui()
        gw = getattr(gui, "global_window", None) if gui else None
        if gw is not None:
            return gw
        if self._model is None:
            from .model.objects import GlobalWindow
            self._model = GlobalWindow()
        return self._model

    def GetColorbar(self):
        """The global Colorbar object (or None)."""
        return self._gw().colorbar

    def GetGradation(self):
        """The global Gradation object (or None)."""
        return self._gw().gradation

    def GetCamera(self):
        """The global Camera object (or None)."""
        return self._gw().camera

    def GetLight(self):
        """The global Light object (or None)."""
        return self._gw().light

    def SetLight(self, brightness=None, color=None, position=None):
        """Set global-light parameters, creating the Light when absent."""
        from .model.objects import LightObject
        light = self._gw().light
        if light is None:
            light = LightObject()
            self._gw().light = light
        if brightness is not None:
            light.brightness = max(0.0, min(2.0, float(brightness)))
        if color is not None:
            light.color = tuple(float(c) for c in color)
        if position is not None:
            light.position = tuple(float(p) for p in position)
        return light


class DrawWindowClass:
    """COM Draw Window (scPOST DrawWindow class, r12.1).

    Represents the drawing window; when a GUI is attached its render
    window is driven directly, headless COM keeps window state only.
    """

    _public_methods_ = ["Refresh", "GetRenderWindow", "IsVisible",
                        "SetVisible", "Screenshot"]
    _public_attrs_ = ["Visible"]

    def __init__(self, app):
        self._app = app
        self._visible = True

    def Refresh(self):
        """Repaint the drawing window (renderer Render when attached)."""
        gui = _bridge_gui()
        if gui is not None:
            try:
                if getattr(gui, "renderer", None) is not None:
                    gui.renderer.GetRenderWindow().Render()
                elif hasattr(gui, "on_redraw"):
                    gui.on_redraw()
            except Exception:
                pass
        return True

    def GetRenderWindow(self):
        """The vtkRenderWindow when a GUI is attached, else None."""
        gui = _bridge_gui()
        widget = getattr(gui, "vtk_widget", None) if gui else None
        return widget.GetRenderWindow() if widget is not None else None

    def IsVisible(self):
        return bool(self._visible)

    def SetVisible(self, visible):
        self._visible = bool(visible)
        gui = _bridge_gui()
        if gui is not None and hasattr(gui, "setVisible"):
            try:
                gui.setVisible(bool(visible))
            except Exception:
                pass
        return True

    def Screenshot(self, path):
        """Save a PNG of the drawing window (needs attached GUI)."""
        rw = self.GetRenderWindow()
        if rw is None:
            return False
        try:
            from .render.export import snapshot_png
            return bool(snapshot_png(rw.GetRenderers().GetFirstRenderer(),
                                     str(path)))
        except Exception:
            return False

    @property
    def Visible(self):
        return self._visible


class SaveBitmapsClass:
    """COM Camera object (scPOST savebitmaps class, r12.1).

    Bitmap-series recorder: registers output paths and saves drawing-
    window snapshots (used per animation frame).
    """

    _public_methods_ = ["AddBitmap", "SaveBitmaps", "GetCount", "Clear"]

    def __init__(self, app):
        self._app = app
        self._paths = []

    def AddBitmap(self, path):
        """Register the next bitmap output path."""
        self._paths.append(str(path))
        return len(self._paths)

    def SaveBitmaps(self):
        """Snapshot the drawing window to every registered path."""
        saved = 0
        for p in list(self._paths):
            if self._app._draw_window.Screenshot(p):
                saved += 1
        return saved

    def GetCount(self):
        return len(self._paths)

    def Clear(self):
        self._paths = []
        return True


class EnvironmentClass:
    """COM Environment object (scPOST Environment class, r12.1).

    Key/value view over the application environment: the display /
    backup / mouse-operation settings exposed by the Set* family.
    """

    _public_methods_ = ["GetValue", "SetValue", "GetAll", "Reset"]

    def __init__(self, app):
        self._app = app

    _ENV_KEYS = (
        "display_axis", "display_fld", "display_title_cycle",
        "display_title_path", "display_title_time", "display_obj_name",
        "display_logo", "display_hint", "display_draw_mode",
        "use_undo_buffer", "use_autosave", "beep_all",
        "no_default_obj", "no_progress_bar", "no_next_elements",
        "not_reduce_riddge", "operate_object_enabled",
        "operation_type", "user_control", "write_back_to_env_file",
    )

    def GetValue(self, key):
        """One environment flag by key (""-valued keys return None)."""
        return self._app._flags.get(str(key))

    def SetValue(self, key, value):
        """Set one environment flag; unknown keys are rejected."""
        k = str(key)
        if k not in self._ENV_KEYS:
            return False
        self._app._flags[k] = bool(value)
        return True

    def GetAll(self):
        """The whole environment as a {key: value} dict."""
        return {k: self._app._flags.get(k)
                for k in self._ENV_KEYS if k in self._app._flags}

    def Reset(self):
        """Restore the default environment (SetDefaultAll)."""
        self._app.SetDefaultAll(0)
        return True


class FlowviewerApplication:
    """COM-exposed flowviewer Application object (7c).

    Lifecycle: open_file replaces any previously loaded file and fires
    on_open; close()/quit() release the file and fire on_close; the object
    also works as a context manager (with) and releases in __del__.

    Events: real COM connection points - a client may
    QueryInterface(IConnectionPointContainer) and Advise a sink, or call
    app.FindConnectionPoint(iid).Advise(sink) through IDispatch;
    subscribe/unsubscribe are a Python-friendly alias.

    scPOST surface (P3): the AddCycList/SetCurCycleID cycle family over
    open_sequence, geometry/region queries (GetBoundingBox,
    LocalXYZ2GlobalXYZ, GetOverlappingRegionCount, GetMATIDofVOL, ...),
    SaveSTA/ApplySTA/SaveSTL and the SetDisplay*/animation state
    setters.  Every method records failures in the ErrorCode /
    ErrorString properties instead of raising through IDispatch.
    """

    _reg_clsid_ = "{A1B2C3D4-5E6F-4A7B-8C9D-0E1F2A3B4C5D}"
    _reg_progid_ = "flowviewer.Application"
    _reg_desc_ = "flowviewer post-processor"
    _public_methods_ = [
        "open_file", "variables", "cycles", "quit",
        "close", "release", "subscribe", "unsubscribe",
        "EnumConnectionPoints", "FindConnectionPoint",
        # sequence / cycle runtime (scPOST AddCycList family)
        "open_sequence", "GetCycleNum", "GetCurCycleID", "GetCurCycleID_F",
        "GetCurTime", "GetCycleByCycleID", "GetTimeByCycleID",
        "SetCurCycleID", "SetCurCycleID_F", "SetAutoCycle", "ResetCycOpe",
        "SetCycOpeMode", "AddCycList", "DelCycList",
        # geometry / region queries
        "GetBoundingBox", "LocalXYZ2GlobalXYZ", "GlobalXYZ2LocalXYZ",
        "GetOverlappingRegionCount", "GetMATNumFLD", "GetMATIDofVOL",
        "GetVOLNum", "GetVOLorgnameAsArray",
        "GetNodeCount", "GetElementCount", "GetNodeOfs", "GetNodeXYZ",
        "GetNodeCountOfElement", "GetNodeCountOfFace", "GetNodesOfElement",
        "GetNodesOfFace", "GetFaceCountOfElement",
        "GetAdjacentElementOfFace", "GetAreaOfFace", "GetVolumeOfElement",
        "GetElementsOfVolumeRegion", "GetNodesOfVolumeRegion",
        "GetNodesOfSurfaceRegion",
        # adjacency / region tables (r12.1)
        "GetNextNodes", "GetElemBySurf", "GetSurfaceArray",
        "GetSurfaceArray2", "GetVolumeArray2", "GetCurCycOpeNum",
        "GetLatestStaPath",
        "GetMATNbyMATID", "GetMATIDbyMATN", "GetMATemtnamebyMATID",
        "GetMATIDbyMATemtname", "GetMATNumOfVOL", "GetMATNOfElement",
        "GetVOLemtnameAsArray", "GetVOLemtnamebyVOLID", "GetVOLIDbyElement",
        "GetVOLIDbyVOLemtname", "GetVOLIDbyVOLorgname",
        "GetVOLorgnamebyVOLID", "GetRgnName", "GetRgnNum",
        "GetFaceNumOfRgn",
        "GetVariableInfo", "GetVariableMin", "GetVariableMax",
        # status / export
        "SaveSTA", "ApplySTA", "SaveSTL", "SaveVariableOutput",
        "SaveVRML", "SaveGLTF", "SaveFBX", "SaveCradleViewer",
        # compare / viewpoint (r12 P0-1)
        "Compare", "GetCurCycle", "GetBaseScale",
        "GetViewPoint", "SetViewPoint", "SetViewPort",
        # FLD open variants (r12 P0-2)
        "CreateObjectFLD", "CreateObjectFLD2", "CreateObjectFLDbySTA",
        "CreateObjectFld_TRIM", "IsThisFldValid", "Quit",
        # application state (Set* family + animation)
        "SetDisplayAxis", "SetDisplayFLD", "SetDisplayTitleCycle",
        "SetDisplayTitlePath", "SetDisplayTitleTime", "SetDisplayObjName",
        "SetUseUndoBuffer", "SetUseAutoSave", "AnimationStart",
        "AnimationStop", "PrepareMinMaxPos", "SplitView",
        "ObjectNameArrange",
        # application misc (R2.6)
        "GetPID", "GetTickCount", "GetTickCountEx",
        "CreateFolder", "GetAllFilesForWildCard",
        "GetOneOfFilesForWildCard", "GetRandomFilename",
        "ShellExecute", "GetEnvFilePath", "GetHomeFolder",
        "IsThisPathValid", "SetLogFilename",
        "SetMessageLevel", "OpenMessageLogFile",
        "CloseMessageLogFile", "UpdateAll",
        "AnimationFrame", "AnimationSecond",
        # Application window / config family (r12.1, scPOST 100%)
        "GetDrawWindow", "GetGlobalWindow", "GetMessageWindow",
        "CreateDrawWnd", "GetDockableWindow", "Dock",
        "GetObjectActiveFLD", "GetObjectFLDbyID",
        "AlignObjectsAlongAnotherObject", "AlignObjectsAlongPane",
        "DefineVar", "DropFile", "GetCurNP", "GetDisplayLOGO",
        "GetEnvInfo", "ObjectNameDisplay", "PikaPika", "SetBeepAll",
        "SetDefaultAll", "SetDisplayDrawMode", "SetDisplayHint",
        "SetDisplayLOGO", "SetNoControls", "SetNoDefaultObj",
        "SetNoNextElements", "SetNoProgressBar", "SetNotReduceRiddge",
        "SetOperateObjectEnabled", "SetOperationType",
    ]
    _public_attrs_ = [
        "version", "file_path", "kind", "n_cells", "n_vertices",
        "cycle", "time", "variable_names", "has_file",
        "ErrorCode", "ErrorString",
        "UserControl", "Visible", "WriteBackToEnvFile",
    ]
    _readonly_attrs_ = [
        "version", "file_path", "kind", "n_cells", "n_vertices",
        "cycle", "time", "variable_names", "has_file",
        "ErrorCode", "ErrorString",
    ]

    def __init__(self):
        self._ff = None
        self._fs = None          # FileSet behind open_sequence
        self._rt = None          # CycleRuntime over _fs
        self._main = None        # object tree from ApplySTA
        self._sta_path = None    # last applied STA (GetLatestStaPath)
        self._err_code = 0
        self._err_str = "OK"
        self._start_time = None
        self._msg_level = 0
        self._msg_log_file = None
        self._log_file = None
        self._flags = {
            "display_axis": True, "display_fld": True,
            "display_title_cycle": True, "display_title_path": True,
            "display_title_time": True, "display_obj_name": False,
            "use_undo_buffer": True, "use_autosave": False,
            "minmax_pos": False, "split_view": 0, "animating": False,
            # r12.1: scPOST Set*/window state
            "display_logo": False, "display_hint": True,
            "display_draw_mode": False, "beep_all": False,
            "no_default_obj": False, "no_progress_bar": False,
            "no_next_elements": False, "not_reduce_riddge": False,
            "operate_object_enabled": True, "operation_type": "1",
            "no_controls": False, "user_control": False,
            "write_back_to_env_file": True, "visible": False,
        }
        self._defined_vars = []   # DefineVar STA commands
        self._lock = threading.RLock()
        self._cp = ConnectionPoint(self)
        # r12.1 window classes
        self._message_window = MessageWindowClass(self)
        self._global_window = GlobalWindowClass(self)
        self._draw_window = DrawWindowClass(self)
        self._savebitmaps = SaveBitmapsClass(self)
        self._environment = EnvironmentClass(self)
        if _HAS_COM:
            try:
                import pythoncom as _pc
                self._com_interfaces_ = [
                    _pc.IID_IConnectionPoint,
                    _pc.IID_IConnectionPointContainer,
                ]
            except Exception:
                pass

    # ── error channel (scPOST ErrorCode / ErrorString) ────────────────────

    @property
    def ErrorCode(self):
        """Error code of the last method call (0 = OK)."""
        return self._err_code

    @property
    def ErrorString(self):
        """Error message of the last method call."""
        return self._err_str

    # ── scPOST Application properties (r12.1) ─────────────────────────────

    @property
    def UserControl(self):
        """Program-control flag: True keeps Postprocessor alive at script
        end (UserControl)."""
        return self._flags["user_control"]

    @UserControl.setter
    def UserControl(self, value):
        self._flags["user_control"] = bool(value)

    @property
    def Visible(self):
        """Main-window visibility flag (Visible; default False)."""
        return self._flags["visible"]

    @Visible.setter
    def Visible(self, value):
        self._flags["visible"] = bool(value)
        gui = _bridge_gui()
        if gui is not None and hasattr(gui, "setVisible"):
            try:
                gui.setVisible(bool(value))
            except Exception:
                pass

    @property
    def WriteBackToEnvFile(self):
        """Overwrite the environment file at termination (default True)."""
        return self._flags["write_back_to_env_file"]

    @WriteBackToEnvFile.setter
    def WriteBackToEnvFile(self, value):
        self._flags["write_back_to_env_file"] = bool(value)

    def _ok(self, value):
        self._err_code, self._err_str = 0, "OK"
        return value

    def _fail(self, exc):
        self._err_code, self._err_str = -1, str(exc)
        return None

    def _need_ff(self):
        if self._ff is None:
            raise ValueError("no field file open")
        return self._ff

    def _need_rt(self):
        if self._rt is None:
            raise ValueError("no cycle sequence open (open_sequence first)")
        return self._rt

    def _query_interface_(self, iid):
        """Answer QI for the connection-point interfaces (COM events)."""
        if not _HAS_COM:
            return None
        import pythoncom as _pc
        import win32com.server.util
        if iid in (_pc.IID_IConnectionPoint,
                   _pc.IID_IConnectionPointContainer):
            return win32com.server.util.wrap(self._cp)
        return None

    # lifecycle

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def __del__(self):
        try:
            self._ff = None
        except Exception:
            pass

    def open_file(self, path):
        """Load a field file (fires on_open).  Returns None; the metadata
        is exposed through the read-only properties (COM-VARIANT safe)."""
        from .model.dataset import load_file
        ff = load_file(path)
        with self._lock:
            self._ff = ff
        self._cp.fire("on_open", str(path))
        return None

    def close(self):
        """Release the loaded file (fires on_close)."""
        with self._lock:
            had = self._ff is not None
            self._ff = None
        if had:
            self._cp.fire("on_close")

    def quit(self):
        """Alias of close (scPOST VBS compatibility)."""
        self.close()

    def Quit(self):
        """Exit the post-processor (scPOST Quit); releases the loaded
        file (fires on_close).  The scPOST-spelled alias of quit()."""
        self.close()
        return True

    def release(self):
        """Release the file and drop all event sinks."""
        self.close()
        self._cp.clear()

    # properties

    @property
    def version(self):
        return VERSION

    @property
    def file_path(self):
        return self._ff.path if self._ff is not None else ""

    @property
    def kind(self):
        return self._ff.kind if self._ff is not None else ""

    @property
    def n_cells(self):
        return self._ff.n_cells if self._ff is not None else 0

    @property
    def n_vertices(self):
        return self._ff.n_vertices if self._ff is not None else 0

    @property
    def cycle(self):
        if self._ff is None or self._ff.cycle is None:
            return 0
        return self._ff.cycle

    @property
    def time(self):
        if self._ff is None or self._ff.time is None:
            return 0.0
        return float(self._ff.time)

    @property
    def variable_names(self):
        """Variable names of the currently loaded file."""
        return sorted(self._ff.variables) if self._ff is not None else []

    @property
    def has_file(self):
        return self._ff is not None

    # methods

    def variables(self):
        """Variable names of the currently loaded file (legacy alias)."""
        return self.variable_names

    def cycles(self):
        """Cycle id of the loaded file (0 when absent)."""
        return self.cycle

    def EnumConnectionPoints(self):
        """Return the outgoing event connection points (IConnectionPointContainer)."""
        return self._cp.EnumConnectionPoints()

    def FindConnectionPoint(self, iid):
        """Return the connection point for an event IID (or None)."""
        return self._cp.FindConnectionPoint(iid)

    def subscribe(self, callback):
        """Register a sink; returns the connection cookie (Python alias)."""
        return self._cp.Advise(callback)

    def unsubscribe(self, callback):
        """Remove a sink object previously registered via subscribe."""
        for cookie, sink in list(self._cp._sinks.items()):
            if sink is callback:
                self._cp.Unadvise(cookie)
        return len(self._cp._sinks)

    # ── cycle sequence runtime (scPOST AddCycList / SetCurCycleID, P3) ─────

    def open_sequence(self, path):
        """Open a cycle sequence around *path* (same-stem siblings) and
        load its first member as the current file (fires on_open)."""
        try:
            from . import api
            from .model.fileset import load_member, scan_sequence
            fs = scan_sequence(str(path))
            if not len(fs):
                raise ValueError("no sibling cycle files around %r" % path)
            rt = api.cycle_runtime(fs)
            with self._lock:
                self._fs, self._rt = fs, rt
                # cycle id 1 = first member (its stored cycle number,
                # which is not necessarily 1)
                self._ff = load_member(fs, fs.members[0].cycle,
                                       cache=rt.cache)
            self._cp.fire("on_open", str(path))
            return self._ok(len(fs))
        except Exception as exc:
            return self._fail(exc)

    def GetCycleNum(self):
        """Number of files in the open cycle series (GetCycleNum)."""
        try:
            return self._ok(self._need_rt().get_cycle_num())
        except Exception as exc:
            return self._fail(exc)

    def GetCurCycleID(self):
        """Current (1-based, integer) cycle id (GetCurCycleID)."""
        try:
            return self._ok(self._need_rt().get_cur_cycle_id())
        except Exception as exc:
            return self._fail(exc)

    def GetCurCycleID_F(self):
        """Fractional part of the current cycle id (GetCurCycleID_F)."""
        try:
            from . import api
            return self._ok(api.get_cur_cycle_id_f(self._need_rt()))
        except Exception as exc:
            return self._fail(exc)

    def GetCurTime(self):
        """Time stored in the current cycle file (GetCurTime)."""
        try:
            return self._ok(self._need_rt().get_cur_time())
        except Exception as exc:
            return self._fail(exc)

    def GetCycleByCycleID(self, cycle_id):
        """Cycle number of the member at 1-based *cycle_id*."""
        try:
            from . import api
            return self._ok(api.get_cycle_by_cycle_id(self._need_rt().fs,
                                                      cycle_id))
        except Exception as exc:
            return self._fail(exc)

    def GetTimeByCycleID(self, cycle_id):
        """Time of the member at 1-based *cycle_id* (GetTimeByCycleID)."""
        try:
            from . import api
            return self._ok(api.get_time_by_cycle_id(self._need_rt().fs,
                                                     cycle_id))
        except Exception as exc:
            return self._fail(exc)

    def SetCurCycleID(self, cycid):
        """Jump to cycle *cycid*; new id, or -1 when out of range."""
        try:
            from . import api
            return self._ok(api.set_cur_cycle_id(self._need_rt(), cycid))
        except Exception as exc:
            return self._fail(exc)

    def SetCurCycleID_F(self, cyc_i, cyc_f):
        """Fractional cycle id with time interpolation (SetCurCycleID_F)."""
        try:
            from . import api
            return self._ok(api.set_cur_cycle_id_f(self._need_rt(),
                                                   cyc_i, cyc_f))
        except Exception as exc:
            return self._fail(exc)

    def SetAutoCycle(self, is_auto):
        """Select the cycle-shift [Auto Set] checkbox (SetAutoCycle)."""
        try:
            from . import api
            return self._ok(api.set_auto_cycle(self._need_rt(), is_auto))
        except Exception as exc:
            return self._fail(exc)

    def ResetCycOpe(self):
        """Reset the between-cycle operation (ResetCycOpe)."""
        try:
            from . import api
            return self._ok(api.reset_cyc_ope(self._need_rt()))
        except Exception as exc:
            return self._fail(exc)

    def SetCycOpeMode(self, mode):
        """Between-cycle operation None|Add|Sub|Mul|Div (SetCycOpeMode)."""
        try:
            from . import api
            return self._ok(api.set_cyc_ope_mode(self._need_rt().fs, mode))
        except Exception as exc:
            return self._fail(exc)

    def AddCycList(self, path, cycle=0):
        """Append a file to the cycle list (AddCycList)."""
        try:
            from . import api
            cyc = int(cycle) if int(cycle) > 0 else None
            m = api.add_cyc_list(self._need_rt().fs, str(path), cyc)
            return self._ok(int(m.cycle))
        except Exception as exc:
            return self._fail(exc)

    def DelCycList(self, cycle):
        """Drop the member with the given cycle (DelCycList)."""
        try:
            from . import api
            return self._ok(api.del_cyc_list(self._need_rt().fs, cycle))
        except Exception as exc:
            return self._fail(exc)

    # ── geometry / region queries (P3) ────────────────────────────────────

    def GetBoundingBox(self, name=None):
        """Bounding box (xmin, xmax, ymin, ymax, zmin, zmax) of the file
        or one volume region (GetBoundingBox).

        scPOST takes a required ``name`` and writes the six values ByRef,
        returning LONG; the Python COM layer returns the six values as a
        tuple and keeps ``name`` optional (None = whole mesh).
        """
        try:
            from . import api
            return self._ok(api.get_bounding_box(self._need_ff(), name))
        except Exception as exc:
            return self._fail(exc)

    def LocalXYZ2GlobalXYZ(self, x, y, z):
        """Convert a local-frame coordinate to global (LocalXYZ2GlobalXYZ).

        The local coordinate system is read from the loaded file; returns
        (gx, gy, gz).
        """
        try:
            from . import api
            g = api.local_xyz_to_global_xyz(
                (float(x), float(y), float(z)), ff=self._need_ff())
            return self._ok((float(g[0]), float(g[1]), float(g[2])))
        except Exception as exc:
            return self._fail(exc)

    def GlobalXYZ2LocalXYZ(self, x, y, z):
        """Inverse of LocalXYZ2GlobalXYZ; returns (lx, ly, lz)."""
        try:
            from . import api
            l = api.global_xyz_to_local_xyz(
                (float(x), float(y), float(z)), ff=self._need_ff())
            return self._ok((float(l[0]), float(l[1]), float(l[2])))
        except Exception as exc:
            return self._fail(exc)

    def GetOverlappingRegionCount(self):
        """Cells belonging to more than one volume region
        (GetOverlappingRegionCount)."""
        try:
            from . import api
            return self._ok(api.get_overlapping_region_count(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    def GetMATNumFLD(self):
        """Number of materials = maximum MAT-ID (GetMATNumFLD)."""
        try:
            from . import api
            return self._ok(api.get_mat_num(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    def GetMATIDofVOL(self, volid):
        """MAT-ID filling a volume region (GetMATIDofVOL).

        *volid* is the 1-based volume-region id (scPOST) or a region name;
        returns -1 when the region mixes materials, None when it has no
        cells.  The MAT count (scPOST ByRef ``n``) is exposed by
        :func:`api.get_mat_num_of_vol`.
        """
        try:
            from . import api
            return self._ok(api.get_mat_id_of_vol(self._need_ff(), volid))
        except Exception as exc:
            return self._fail(exc)

    def GetVOLNum(self):
        """Number of volume regions (GetVOLNum)."""
        try:
            from . import api
            return self._ok(api.get_vol_num(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    def GetVOLorgnameAsArray(self):
        """Internal volume-region names (GetVOLorgnameAsArray)."""
        try:
            from . import api
            return self._ok(api.get_vol_org_names(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    # ── overlap-region geometry family (scPOST ov 参数族, R2.2) ──────────

    def GetNodeCount(self, ov=0):
        """Number of nodes in an overlap region (GetNodeCount)."""
        try:
            from . import api
            return self._ok(api.get_node_count(self._need_ff(), ov))
        except Exception as exc:
            return self._fail(exc)

    def GetElementCount(self, ov=0):
        """Number of elements in an overlap region (GetElementCount)."""
        try:
            from . import api
            return self._ok(api.get_element_count(self._need_ff(), ov))
        except Exception as exc:
            return self._fail(exc)

    def GetNodeOfs(self):
        """Initial node number (0 or 1) (GetNodeOfs)."""
        try:
            from . import api
            return self._ok(api.get_node_ofs(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    def GetNodeXYZ(self, nodeid):
        """(x, y, z) of a node (GetNodeXYZ)."""
        try:
            from . import api
            return self._ok(api.get_node_xyz(self._need_ff(), nodeid))
        except Exception as exc:
            return self._fail(exc)

    def GetNodeCountOfElement(self, ov, elem):
        """Number of nodes of an element (GetNodeCountOfElement)."""
        try:
            from . import api
            return self._ok(api.get_node_count_of_element(
                self._need_ff(), elem, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetNodeCountOfFace(self, ov, elem, face):
        """Number of nodes on a local element face (GetNodeCountOfFace)."""
        try:
            from . import api
            return self._ok(api.get_node_count_of_face(
                self._need_ff(), elem, face, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetNodesOfElement(self, ov, elem):
        """Node ids of an element (GetNodesOfElement)."""
        try:
            from . import api
            return self._ok(api.get_nodes_of_element(
                self._need_ff(), elem, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetNodesOfFace(self, ov, elem, face):
        """Node ids on a local element face (GetNodesOfFace)."""
        try:
            from . import api
            return self._ok(api.get_nodes_of_face(
                self._need_ff(), elem, face, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetFaceCountOfElement(self, ov, elem):
        """Number of faces of an element (GetFaceCountOfElement)."""
        try:
            from . import api
            return self._ok(api.get_face_count_of_element(
                self._need_ff(), elem, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetAdjacentElementOfFace(self, ov, elem, face):
        """Element adjacent to a local face (GetAdjacentElementOfFace)."""
        try:
            from . import api
            return self._ok(api.get_adjacent_element_of_face(
                self._need_ff(), elem, face, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetAreaOfFace(self, ov, elem, face):
        """Area of a local element face (GetAreaOfFace)."""
        try:
            from . import api
            return self._ok(api.get_area_of_face(
                self._need_ff(), elem, face, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetVolumeOfElement(self, ov, elem):
        """Volume of an element (GetVolumeOfElement)."""
        try:
            from . import api
            return self._ok(api.get_volume_of_element(
                self._need_ff(), elem, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetElementsOfVolumeRegion(self, volid):
        """Element ids in a volume region (GetElementsOfVolumeRegion)."""
        try:
            from . import api
            return self._ok(api.get_elements_of_volume_region(
                self._need_ff(), volid))
        except Exception as exc:
            return self._fail(exc)

    def GetNodesOfVolumeRegion(self, volid):
        """Node ids in a volume region (GetNodesOfVolumeRegion)."""
        try:
            from . import api
            return self._ok(api.get_nodes_of_volume_region(
                self._need_ff(), volid))
        except Exception as exc:
            return self._fail(exc)

    def GetNodesOfSurfaceRegion(self, surface_name):
        """Node ids of a boundary region (GetNodesOfSurfaceRegion)."""
        try:
            from . import api
            return self._ok(api.get_nodes_of_surface_region(
                self._need_ff(), surface_name))
        except Exception as exc:
            return self._fail(exc)

    # ── adjacency / region-table queries (r12.1: ex10/ex9 VBS samples) ────

    def GetNextNodes(self, node, nextnodes=None):
        """Neighbour node ids of *node* (GetNextNodes).

        scPOST fills the ByRef ``nextnodes`` VARIANT and returns the
        count; the Python COM layer returns the id list itself (its
        length is the scPOST return value).  ``nextnodes`` is accepted
        and ignored for call-shape compatibility.
        """
        try:
            from . import api
            return self._ok(api.get_next_nodes(self._need_ff(), node))
        except Exception as exc:
            return self._fail(exc)

    def GetElemBySurf(self, ngfb):
        """Element owning boundary face *ngfb* (GetElemBySurf)."""
        try:
            from . import api
            return self._ok(api.get_elem_by_surf(self._need_ff(), ngfb))
        except Exception as exc:
            return self._fail(exc)

    def GetSurfaceArray(self, size=None, names=None):
        """Registered surface-region table (GetSurfaceArray).

        scPOST fills ByRef ``size`` / ``names`` and returns BOOL; the
        Python COM layer returns ``[(name, [face_id, ...]), ...]`` so
        both the names and the per-region face ids are available.
        """
        try:
            from . import api
            return self._ok(api.surface_region_table(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    def GetSurfaceArray2(self, ngfb, num=None, names=None):
        """Surface-region names containing face *ngfb* (GetSurfaceArray2).

        scPOST fills ByRef ``num`` / ``names``; the Python COM layer
        returns the name list itself.
        """
        try:
            from . import api
            return self._ok(api.get_surface_regions_of_face(
                self._need_ff(), ngfb))
        except Exception as exc:
            return self._fail(exc)

    def GetVolumeArray2(self, elem, num=None, names=None):
        """Volume-region names containing element *elem* (GetVolumeArray2).

        scPOST fills ByRef ``num`` / ``names``; the Python COM layer
        returns the name list itself.
        """
        try:
            from . import api
            return self._ok(api.get_volume_regions_of_element(
                self._need_ff(), elem))
        except Exception as exc:
            return self._fail(exc)

    def GetCurCycOpeNum(self):
        """Files in the current cycle-operation list (GetCurCycOpeNum)."""
        try:
            from . import api
            return self._ok(api.get_cur_cyc_ope_num(self._need_rt()))
        except Exception as exc:
            return self._fail(exc)

    def GetLatestStaPath(self):
        """Full path of the last applied STA file (GetLatestStaPath).

        Empty string when no STA has been applied yet (scPOST returns a
        NULL string in that case).
        """
        return self._ok(self._sta_path or "")

    # ── MAT / VOL / RGN lookup family (scPOST 互查族, R2.3) ───────────────

    def GetMATNbyMATID(self, matid):
        """MAT-number from MAT-ID (GetMATNbyMATID)."""
        try:
            from . import api
            return self._ok(api.get_mat_n_by_mat_id(self._need_ff(), matid))
        except Exception as exc:
            return self._fail(exc)

    def GetMATIDbyMATN(self, matn):
        """MAT-ID from MAT-number (GetMATIDbyMATN)."""
        try:
            from . import api
            return self._ok(api.get_mat_id_by_mat_n(self._need_ff(), matn))
        except Exception as exc:
            return self._fail(exc)

    def GetMATemtnamebyMATID(self, matid):
        """Material name from MAT-ID (GetMATemtnamebyMATID)."""
        try:
            from . import api
            return self._ok(api.get_mat_emtname_by_mat_id(
                self._need_ff(), matid))
        except Exception as exc:
            return self._fail(exc)

    def GetMATIDbyMATemtname(self, matname):
        """MAT-ID from material name (GetMATIDbyMATemtname)."""
        try:
            from . import api
            return self._ok(api.get_mat_id_by_mat_emtname(
                self._need_ff(), matname))
        except Exception as exc:
            return self._fail(exc)

    def GetMATNumOfVOL(self, volid):
        """Number of MAT kinds in a volume region (GetMATNumOfVOL)."""
        try:
            from . import api
            return self._ok(api.get_mat_num_of_vol(self._need_ff(), volid))
        except Exception as exc:
            return self._fail(exc)

    def GetMATNOfElement(self, ov, elem):
        """MAT-number of an element (GetMATNOfElement)."""
        try:
            from . import api
            return self._ok(api.get_mat_n_of_element(
                self._need_ff(), elem, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetVOLemtnameAsArray(self):
        """Volume-region EMT names (GetVOLemtnameAsArray)."""
        try:
            from . import api
            return self._ok(api.get_vol_emt_names(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    def GetVOLemtnamebyVOLID(self, volid):
        """Volume-region EMT name by id (GetVOLemtnamebyVOLID)."""
        try:
            from . import api
            return self._ok(api.get_vol_emtname_by_vol_id(
                self._need_ff(), volid))
        except Exception as exc:
            return self._fail(exc)

    def GetVOLIDbyElement(self, ov, elem):
        """Volume-region id owning an element (GetVOLIDbyElement)."""
        try:
            from . import api
            return self._ok(api.get_vol_id_by_element(
                self._need_ff(), elem, ov))
        except Exception as exc:
            return self._fail(exc)

    def GetVOLIDbyVOLemtname(self, emtname):
        """Volume-region id from EMT name (GetVOLIDbyVOLemtname)."""
        try:
            from . import api
            return self._ok(api.get_vol_id_by_vol_emtname(
                self._need_ff(), emtname))
        except Exception as exc:
            return self._fail(exc)

    def GetVOLIDbyVOLorgname(self, orgname):
        """Volume-region id from internal name (GetVOLIDbyVOLorgname)."""
        try:
            from . import api
            return self._ok(api.get_vol_id_by_vol_orgname(
                self._need_ff(), orgname))
        except Exception as exc:
            return self._fail(exc)

    def GetVOLorgnamebyVOLID(self, volid):
        """Volume-region internal name by id (GetVOLorgnamebyVOLID)."""
        try:
            from . import api
            return self._ok(api.get_vol_orgname_by_vol_id(
                self._need_ff(), volid))
        except Exception as exc:
            return self._fail(exc)

    def GetRgnName(self, ngfax):
        """Surface registration area name by id (GetRgnName)."""
        try:
            from . import api
            return self._ok(api.get_rgn_name(self._need_ff(), ngfax))
        except Exception as exc:
            return self._fail(exc)

    def GetRgnNum(self):
        """Number of surface registration areas (GetRgnNum)."""
        try:
            from . import api
            return self._ok(api.get_rgn_num(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    def GetFaceNumOfRgn(self, ngfax):
        """Number of faces in a surface registration area (GetFaceNumOfRgn)."""
        try:
            from . import api
            return self._ok(api.get_face_num_of_rgn(self._need_ff(), ngfax))
        except Exception as exc:
            return self._fail(exc)

    def GetVariableInfo(self, LNAM, x, y, z):
        """Field information at (x, y, z) (GetVariableInfo).

        Returns a dict with name/kind/values/elem/ov/mat/isinarea for the
        variable *LNAM*.
        """
        try:
            from . import api
            return self._ok(api.variable_at_point(
                self._need_ff(), LNAM, x, y, z))
        except Exception as exc:
            return self._fail(exc)

    def GetVariableMin(self, LNAM):
        """Minimum value of a variable (GetVariableMin)."""
        try:
            from . import api
            return self._ok(api.variable_range(self._need_ff(), LNAM)[0])
        except Exception as exc:
            return self._fail(exc)

    def GetVariableMax(self, LNAM):
        """Maximum value of a variable (GetVariableMax)."""
        try:
            from . import api
            return self._ok(api.variable_range(self._need_ff(), LNAM)[1])
        except Exception as exc:
            return self._fail(exc)

    # ── status / export (P3) ──────────────────────────────────────────────

    def SaveSTA(self, filepath):
        """Save the current object tree to a .sta status file (SaveSTA).

        When a running FlowViewer is attached via the bridge its live object
        tree is persisted; otherwise the headless ``_main`` tree (or the
        magic default) is used.
        """
        try:
            from . import api
            from .model.objects import MainObject
            gui = _bridge_gui()
            if gui is not None and getattr(gui, "main_object", None) is not None:
                return self._ok(api.save_sta(gui.main_object, str(filepath)))
            main = self._main
            if main is None:
                main = MainObject.from_field_file(self._need_ff(),
                                                  magic=True)
            return self._ok(api.save_sta(main, str(filepath)))
        except Exception as exc:
            return self._fail(exc)

    def ApplySTA(self, filepath):
        """Load a .sta status file onto the current field (ApplySTA)."""
        try:
            from . import api
            main = api.apply_sta(self._need_ff(), str(filepath))
            if main is None:
                raise ValueError("not a status file: %r" % filepath)
            self._main = main
            self._sta_path = str(filepath)
            return self._ok(True)
        except Exception as exc:
            return self._fail(exc)

    def SaveSTL(self, filepath):
        """Export the boundary surface as STL (SaveSTL)."""
        try:
            from . import api
            return self._ok(api.export_stl(self._need_ff(), str(filepath)))
        except Exception as exc:
            return self._fail(exc)

    def _export_scene(self, fname, writer_name):
        """Shared scene-export path for VRML / glTF (needs a render window)."""
        gui = _bridge_gui()
        rw = None
        if gui is not None and getattr(gui, "vtk_widget", None) is not None:
            rw = gui.vtk_widget.GetRenderWindow()
        if rw is None:
            raise ValueError(
                "%s needs a running GUI (scene render window); "
                "headless COM has no scene" % fname)
        from .render.export import export_scene_vrml, export_scene_gltf
        fn = {"SaveVRML": export_scene_vrml,
              "SaveGLTF": export_scene_gltf}[fname]
        ok = fn(rw, str(writer_name))
        if not ok:
            raise IOError("scene export failed: %s" % writer_name)
        return True

    def SaveVRML(self, filepath):
        """Export the whole scene as VRML (SaveVRML; needs attached GUI)."""
        try:
            return self._ok(self._export_scene("SaveVRML", filepath))
        except Exception as exc:
            return self._fail(exc)

    def SaveGLTF(self, filepath):
        """Export the whole scene as glTF (SaveGLTF; needs attached GUI)."""
        try:
            return self._ok(self._export_scene("SaveGLTF", filepath))
        except Exception as exc:
            return self._fail(exc)

    def SaveFBX(self, filepath):
        """Export the boundary surface as ASCII FBX 7.3 (SaveFBX)."""
        try:
            from . import api
            return self._ok(api.export_fbx(self._need_ff(), str(filepath)))
        except Exception as exc:
            return self._fail(exc)

    def SaveCradleViewer(self, filepath):
        """CradleViewer export (SaveCradleViewer).

        Format identified from official AR samples as ``CVFF`` v2 with a
        custom ``ENCD`` encoding (not zlib, not chunk-TLV); reversible in
        principle once that encoding is mapped — blocked pending dedicated
        reverse engineering of the sample files.
        """
        return self._fail(NotImplementedError(
            "CradleViewer CVFF v2 custom encoding not yet reversed "
            "(samples available under D:/training/cradle */AR/*)"))

    def Compare(self, other_path, var=None):
        """Compare the current FLD with another file (Compare).

        scPOST opens the comparison dialog; the COM layer returns the
        ``compare_summary`` statistics directly (common variables, per
        variable min/max diff).  With *var* returns the single-variable
        ``compare_stats`` result.
        """
        try:
            from .model.dataset import load_file
            from .model.compare import compare_summary, compare_stats
            a = self._need_ff()
            b = load_file(str(other_path))
            if var:
                res = compare_stats(a, b, str(var))
                if res is None:
                    raise ValueError("no common variable %r" % var)
                return self._ok(res)
            return self._ok(compare_summary(a, b))
        except Exception as exc:
            return self._fail(exc)

    def GetCurCycle(self):
        """Current cycle number of the loaded file (GetCurCycle)."""
        try:
            ff = self._need_ff()
            cyc = getattr(ff, "cycle", None)
            return self._ok(0 if cyc is None else int(cyc))
        except Exception as exc:
            return self._fail(exc)

    def GetBaseScale(self):
        """Scale factor of the main object display (GetBaseScale)."""
        try:
            from .model.objects import MainObject
            ff = self._need_ff()
            gui = _bridge_gui()
            main = getattr(gui, "main_object", None) if gui else None
            if main is None:
                main = self._main
            scale = getattr(main, "scale", None) if main is not None else None
            return self._ok(1.0 if scale is None else float(scale))
        except Exception as exc:
            return self._fail(exc)

    def GetViewPoint(self):
        """Camera viewpoint (GetViewPoint) as a pose set.

        Returns ``{position, focal_point, view_up, parallel,
        parallel_scale}`` of the active camera when a GUI is attached;
        headless returns the stored SetViewPoint pose (magic default if
        never set).
        """
        try:
            self._need_ff()
            gui = _bridge_gui()
            renderer = getattr(gui, "renderer", None) if gui else None
            if renderer is not None:
                cam = renderer.GetActiveCamera()
                if cam is not None:
                    return self._ok({
                        "position": tuple(cam.GetPosition()),
                        "focal_point": tuple(cam.GetFocalPoint()),
                        "view_up": tuple(cam.GetViewUp()),
                        "parallel": bool(cam.GetParallelProjection()),
                        "parallel_scale": float(cam.GetParallelScale()),
                    })
            pose = self._flags.get("view_point")
            if pose is None:
                raise ValueError("no viewpoint available (GUI not attached "
                                 "and SetViewPoint never called)")
            return self._ok(dict(pose))
        except Exception as exc:
            return self._fail(exc)

    def SetViewPoint(self, position, focal_point=None, view_up=None):
        """Set the camera viewpoint (SetViewPoint).

        ``position`` is (x, y, z); optional ``focal_point`` / ``view_up``
        complete the pose.  Applied to the attached GUI camera; headless
        stores the pose for GetViewPoint / later apply.
        """
        try:
            self._need_ff()
            pos = tuple(float(v) for v in position)
            if len(pos) != 3:
                raise ValueError("position must be (x, y, z)")
            pose = {"position": pos, "view_up": (0.0, 1.0, 0.0),
                    "focal_point": (0.0, 0.0, 0.0), "parallel": False}
            if focal_point is not None:
                pose["focal_point"] = tuple(float(v)
                                            for v in focal_point)
            if view_up is not None:
                pose["view_up"] = tuple(float(v) for v in view_up)
            self._flags["view_point"] = pose
            gui = _bridge_gui()
            renderer = getattr(gui, "renderer", None) if gui else None
            if renderer is not None:
                from .render.camera import apply_pose
                apply_pose(renderer, pose)
            return self._ok(True)
        except Exception as exc:
            return self._fail(exc)

    def SetViewPort(self, xmin, ymin, xmax, ymax):
        """Location of the clipping frame (SetViewPort) in normalised
        [0,1] coords; sets the attached renderer viewport, headless
        stores the rect."""
        try:
            rect = tuple(float(v) for v in (xmin, ymin, xmax, ymax))
            if not all(0.0 <= v <= 1.0 for v in rect) or \
                    rect[0] >= rect[2] or rect[1] >= rect[3]:
                raise ValueError("viewport must be 0<=x0<x1<=1, 0<=y0<y1<=1")
            self._flags["view_port"] = rect
            gui = _bridge_gui()
            renderer = getattr(gui, "renderer", None) if gui else None
            if renderer is not None:
                renderer.SetViewport(*rect)
                try:
                    gui.vtk_widget.GetRenderWindow().Render()
                except Exception:
                    pass
            return self._ok(True)
        except Exception as exc:
            return self._fail(exc)

    def SaveVariableOutput(self, path, items="all"):
        """Save a variable output file (SaveVariableOutput).

        ``items`` is ``"all"`` or a list of column keys (title/coords/
        normal/scalar/vector/elem/node/rank).  Exports the probe objects
        held on the current object tree, or a single default probe at the
        first vertex/cell centre when no object tree is loaded.
        """
        try:
            from . import api
            objects = None
            if self._main is not None:
                objects = list(getattr(self._main, "children", []) or [])
            return self._ok(api.save_variable_output(
                self._need_ff(), str(path), items=items, objects=objects))
        except Exception as exc:
            return self._fail(exc)

    # ── variable registration (scPOST CreateVar* family, P0-2) ────────────

    def CreateVar(self, lnam, expr):
        """Register an expression variable (scPOST CreateVar)."""
        try:
            from . import api
            return self._ok(api.register_variable(self._need_ff(), lnam, expr))
        except Exception as exc:
            return self._fail(exc)

    def CreateVarALLCYC(self, lnam, expr):
        """Register *expr* on every cycle of the sequence (CreateVarALLCYC).

        Uses the open_sequence FileSet when present; otherwise registers on
        the current file only.
        """
        try:
            from . import api
            if self._fs is not None:
                return self._ok(api.register_var_all_cycles(
                    self._fs, lnam, expr, cache=self._rt.cache
                    if self._rt is not None else None))
            return self._ok(api.register_variable(self._need_ff(), lnam, expr))
        except Exception as exc:
            return self._fail(exc)

    def CreateVarCombinationVelocity(self, static_lnam="CMBVEL", volid_array=None,
                                     lnam_array=None):
        """Create the CMBVEL combination velocity (CreateVarCombinationVelocity)."""
        try:
            from . import api
            return self._ok(api.register_combination_velocity(
                self._need_ff(), static_lnam))
        except Exception as exc:
            return self._fail(exc)

    def CreateVarDST(self, maxlen=None):
        """Create the DST distance-to-wall field (CreateVarDST)."""
        try:
            from . import api
            return self._ok(api.register_dst(self._need_ff()))
        except Exception as exc:
            return self._fail(exc)

    def CreateVarDST2(self, surfaces=None, maxlen=None):
        """Create DST against the specified surfaces (CreateVarDST2)."""
        try:
            from . import api
            regions = None
            if surfaces:
                if isinstance(surfaces, (list, tuple)):
                    regions = list(surfaces)
                else:
                    regions = [str(surfaces)]
            return self._ok(api.register_dst(self._need_ff(),
                                             surface_regions=regions))
        except Exception as exc:
            return self._fail(exc)

    def CreateVarNORMAL(self, region_names=None):
        """Create the NORMAL wall-normal field (CreateVarNORMAL)."""
        try:
            from . import api
            regions = None
            if region_names:
                regions = (list(region_names) if isinstance(
                    region_names, (list, tuple)) else [str(region_names)])
            return self._ok(api.register_normal(self._need_ff(),
                                                surface_regions=regions))
        except Exception as exc:
            return self._fail(exc)

    def DeleteVar(self, lnam):
        """Remove a registered variable (DeleteVar)."""
        try:
            from . import api
            return self._ok(api.delete_variable(self._need_ff(), lnam))
        except Exception as exc:
            return self._fail(exc)

    def SetVarTitle(self, lnam, title):
        """Store a display title for a variable (SetVarTitle)."""
        try:
            from . import api
            return self._ok(api.set_variable_title(self._need_ff(), lnam, title))
        except Exception as exc:
            return self._fail(exc)

    # ── object query family (scPOST GetObj*/GetObject*, P0-3) ─────────────

    def _object_main(self):
        """The object tree backing GetObj* methods."""
        return self._object_tree()

    def GetObjNum(self):
        """Number of child objects (GetObjNum)."""
        try:
            from . import api
            return self._ok(api.object_count(self._object_main()))
        except Exception as exc:
            return self._fail(exc)

    def GetObjType(self, obj):
        """Type name of an object class (GetObjType)."""
        try:
            return self._ok(str(getattr(obj, "kind", "")))
        except Exception as exc:
            return self._fail(exc)

    def GetObjectActiveObj(self):
        """The active object (first visible child; GetObjectActiveObj)."""
        try:
            main = self._object_main()
            for o in (getattr(main, "children", None) or []):
                if getattr(o, "visible", True):
                    return self._ok(o)
            return self._ok(None)
        except Exception as exc:
            return self._fail(exc)

    def GetObjectByGID(self, gid):
        """Child object by global id (GetObjectByGID)."""
        try:
            from . import api
            return self._ok(api.object_by_gid(self._object_main(), gid))
        except Exception as exc:
            return self._fail(exc)

    def GetObjectByNumber(self, number):
        """Child object by its Number (GetObjectByNumber)."""
        try:
            from . import api
            return self._ok(api.object_by_number(self._object_main(), number))
        except Exception as exc:
            return self._fail(exc)

    def GetObjectByType(self, type_name):
        """Child objects of one type (GetObjectByType)."""
        try:
            from . import api
            return self._ok(api.objects_by_type(self._object_main(),
                                                str(type_name)))
        except Exception as exc:
            return self._fail(exc)

    def GetObjectByLongTitle(self, title):
        """Child object whose label/long title matches (GetObjectByLongTitle)."""
        try:
            t = str(title).lower()
            for o in (getattr(self._object_main(), "children", None) or []):
                if getattr(o, "title", "") and o.title.lower() == t:
                    return self._ok(o)
                if o.label.lower() == t:
                    return self._ok(o)
            return self._ok(None)
        except Exception as exc:
            return self._fail(exc)

    def RemoveAllObj(self):
        """Remove every child object but the Main (RemoveAllObj)."""
        try:
            from . import api
            return self._ok(api.remove_all_objects(self._object_main()))
        except Exception as exc:
            return self._fail(exc)

    def RemoveRelatedObj(self, obj):
        """Remove all objects of the same kind as *obj* (RemoveRelatedObj)."""
        try:
            from . import api
            kind = getattr(obj, "kind", None)
            if kind is None:
                return self._ok(0)
            return self._ok(api.remove_related_objects(self._object_main(),
                                                       kind))
        except Exception as exc:
            return self._fail(exc)

    def SetDisplayChildAllObj(self, on):
        """Show/hide every FLD object (SetDisplayChildAllObj)."""
        try:
            for o in (getattr(self._object_main(), "children", None) or []):
                o.visible = bool(on)
            return self._ok(True)
        except Exception as exc:
            return self._fail(exc)

    # ── variable value query family (scPOST GetScalar*/GetVecteor*, P0-3) ──

    def GetScalar(self, LNAM, index):
        """Scalar variable value at an index (GetScalar)."""
        try:
            from . import api
            return self._ok(api.scalar_at(self._need_ff(), LNAM, index))
        except Exception as exc:
            return self._fail(exc)

    def GetScalarArray(self, LNAM):
        """Full scalar variable array (GetScalarArray)."""
        try:
            from . import api
            return self._ok(api.scalar_array(self._need_ff(), LNAM))
        except Exception as exc:
            return self._fail(exc)

    def GetScalarMinMaxByVol(self, LNAM, volid):
        """Min/max of a scalar variable in a volume region (GetScalarMinMaxByVol)."""
        try:
            from . import api
            name = api.get_vol_emtname_by_vol_id(self._need_ff(), volid)
            if not name:
                return self._ok(None)
            return self._ok(api.scalar_range_by_region(self._need_ff(),
                                                       LNAM, name))
        except Exception as exc:
            return self._fail(exc)

    def GetVecteor(self, LNAM, index):
        """Vector variable value at an index (scPOST spelling GetVecteor)."""
        try:
            from . import api
            return self._ok(api.vector_at(self._need_ff(), LNAM, index))
        except Exception as exc:
            return self._fail(exc)

    def GetVecteorArray(self, LNAM):
        """Full vector variable array (GetVecteorArray)."""
        try:
            from . import api
            return self._ok(api.vector_array(self._need_ff(), LNAM))
        except Exception as exc:
            return self._fail(exc)

    def GetVectorMinMaxByVol(self, LNAM, volid):
        """Min/max magnitude of a vector variable in a volume region
        (GetVectorMinMaxByVol)."""
        try:
            from . import api
            name = api.get_vol_emtname_by_vol_id(self._need_ff(), volid)
            if not name:
                return self._ok(None)
            return self._ok(api.scalar_range_by_region(self._need_ff(),
                                                       LNAM, name))
        except Exception as exc:
            return self._fail(exc)

    # ── object creation (scPOST CreateObject* family, P0-1) ───────────────

    def _object_tree(self):
        """Lazily-built MainObject tree (always the COM-owned tree).

        The COM layer keeps its own object tree independent of any attached
        GUI; methods that genuinely need the live GUI tree (SaveSTA) read
        ``_bridge_gui()`` explicitly.
        """
        if self._main is None:
            from .model.objects import MainObject
            self._main = MainObject.from_field_file(self._need_ff(), magic=False)
        return self._main

    def _create_kind(self, kind: str, **kw):
        """Create a PostObject of *kind*, attach it to the object tree
        with an auto-incremented index, and return it."""
        from . import api
        ff = self._need_ff()
        obj = api.create_object(ff, kind, **kw)
        tree = self._object_tree()
        children = getattr(tree, "children", None)
        if children is None:
            children = tree.children = []
        same = [o for o in children if getattr(o, "kind", "") == kind]
        obj.index = (max((int(getattr(o, "index", 0)) for o in same),
                         default=0)) + 1
        children.append(obj)
        return obj

    def CreateObjectNeutral(self, path):
        """Open a Neutral file and return its metadata (CreateObjectNeutral)."""
        try:
            from . import api
            ff = api.open_file(str(path))
            with self._lock:
                self._ff = ff
            return self._ok({"path": ff.path, "kind": getattr(ff, "kind", ""),
                             "n_cells": ff.n_cells,
                             "n_vertices": ff.n_vertices})
        except Exception as exc:
            return self._fail(exc)

    # ── FLD open variants (scPOST CreateObjectFLD family, r12 P0-2) ───────

    def _open_fld_result(self, ff, sta_path=None):
        """Adopt a freshly opened FieldFile and build the COM result."""
        with self._lock:
            self._ff = ff
        if sta_path:
            from . import api
            main = api.apply_sta(ff, str(sta_path))
            if main is None:
                raise ValueError("not a status file: %r" % sta_path)
            self._main = main
        return {"path": ff.path, "kind": getattr(ff, "kind", ""),
                "n_cells": ff.n_cells, "n_vertices": ff.n_vertices}

    def CreateObjectFLD(self, path):
        """Read an FLD file and get the FLD class (CreateObjectFLD)."""
        try:
            from . import api
            return self._ok(self._open_fld_result(api.open_file(str(path))))
        except Exception as exc:
            return self._fail(exc)

    def CreateObjectFLD2(self, path):
        """Read an FLD file using a hash table (CreateObjectFLD2).

        flowviewer always indexes nodes/elements by id maps; identical to
        CreateObjectFLD here (hash-table mode is a scPOST internal)."""
        try:
            from . import api
            return self._ok(self._open_fld_result(api.open_file(str(path))))
        except Exception as exc:
            return self._fail(exc)

    def CreateObjectFLDbySTA(self, path, sta_path):
        """Read an FLD file referring an STA file (CreateObjectFLDbySTA)."""
        try:
            from . import api
            res = self._open_fld_result(api.open_file(str(path)),
                                        sta_path=sta_path)
            self._sta_path = str(sta_path)
            return self._ok(res)
        except Exception as exc:
            return self._fail(exc)

    def CreateObjectFld_TRIM(self, path, xmin=None, xmax=None,
                             ymin=None, ymax=None, zmin=None, zmax=None):
        """Load an FLD selectively (CreateObjectFld_TRIM).

        The six optional bounds select the spatial region kept during the
        parse (iFLD partial load); None keeps that side untrimmed."""
        try:
            from .model.dataset import ifld_load
            parts = ((xmin, ymin, zmin), (xmax, ymax, zmax))
            if all(b is None for b in parts[0] + parts[1]):
                bounds = None
            else:
                fill = (float("-inf"), float("inf"))
                bounds = tuple(fill[i % 2] if b is None else float(b)
                               for i, b in enumerate((xmin, xmax, ymin,
                                                      ymax, zmin, zmax)))
            ff = ifld_load(str(path), bounds=bounds)
            return self._ok(self._open_fld_result(ff))
        except Exception as exc:
            return self._fail(exc)

    def IsThisFldValid(self, path):
        """Whether the file is a loadable FLD-family file (IsThisFldValid).

        A parse that yields no mesh at all counts as invalid (the FLD
        parser returns an empty FieldFile instead of raising)."""
        try:
            from .model import dataset as _ds
            try:
                ff = _ds.load_file(str(path))
            except Exception:
                return self._ok(False)
            return self._ok(bool(getattr(ff, "kind", "")) and
                            (ff.n_vertices > 0 or ff.n_cells > 0))
        except Exception as exc:
            return self._fail(exc)

    def CreateSurfacesOfVolumeRegions(self):
        """Create one Surface per volume region (CreateSurfacesOfVolumeRegions)."""
        try:
            from . import api
            self._need_ff()
            created = []
            for nm in api.volume_region_names(self._need_ff()):
                created.append(self._create_kind("surface",
                                                 display_volume_regions=[nm]))
            return self._ok(created)
        except Exception as exc:
            return self._fail(exc)

    # ── application state setters (P3) ────────────────────────────────────

    def _set_flag(self, key, value):
        self._flags[key] = bool(value)
        return True

    def SetDisplayAxis(self, on):
        """Show/hide the axis (SetDisplayAxis)."""
        return self._set_flag("display_axis", on)

    def SetDisplayFLD(self, on):
        """Show/hide the loaded FLD (SetDisplayFLD)."""
        return self._set_flag("display_fld", on)

    def SetDisplayTitleCycle(self, on):
        """Show/hide the cycle number title (SetDisplayTitleCycle)."""
        return self._set_flag("display_title_cycle", on)

    def SetDisplayTitlePath(self, on):
        """Show/hide the file-name title (SetDisplayTitlePath)."""
        return self._set_flag("display_title_path", on)

    def SetDisplayTitleTime(self, on):
        """Show/hide the time title (SetDisplayTitleTime)."""
        return self._set_flag("display_title_time", on)

    def SetDisplayObjName(self, on):
        """Show/hide object names (SetDisplayObjName)."""
        return self._set_flag("display_obj_name", on)

    def SetUseUndoBuffer(self, on):
        """Use/unuse the undo buffer (SetUseUndoBuffer)."""
        return self._set_flag("use_undo_buffer", on)

    def SetUseAutoSave(self, on):
        """Set/unset auto backup (SetUseAutoSave)."""
        return self._set_flag("use_autosave", on)

    def AnimationStart(self):
        """Begin animation (AnimationStart); drives the GUI timeline when attached."""
        self._set_flag("animating", True)
        gui = _bridge_gui()
        if gui is not None and hasattr(gui, "_on_timeline_play"):
            try:
                gui._on_timeline_play()
            except Exception:
                pass
        return True

    def AnimationStop(self):
        """Stop animation (AnimationStop); pauses the GUI timeline when attached."""
        self._set_flag("animating", False)
        gui = _bridge_gui()
        if gui is not None and hasattr(gui, "_on_timeline_pause"):
            try:
                gui._on_timeline_pause()
            except Exception:
                pass
        return True

    def PrepareMinMaxPos(self, mode=0, loop=6, show=0):
        """Use the max/min position display (PrepareMinMaxPos).

        scPOST arguments: mode 0=current cycle, 1=active object, 2=draw
        window; loop = iteration count (mode 2 only); show = 1 show / 0
        hide the setting dialog.  Returns 0 (scPOST contract).
        """
        self._flags["minmax_pos_mode"] = int(mode)
        self._flags["minmax_pos_loop"] = int(loop)
        self._flags["minmax_pos_show"] = int(show)
        self._flags["minmax_pos"] = True
        return 0

    def SplitView(self, mode=1):
        """Side-by-side display mode (SplitView); the renderer exposes
        it as api.split_view, headless COM stores the mode."""
        self._flags["split_view"] = int(mode)
        return True

    def ObjectNameArrange(self):
        """Rearrange the object-name balloons (ObjectNameArrange)."""
        return True

    # ── scPOST Application window / config family (r12.1, 100% surface) ──

    _ALIGN_POSITIONS = ("left", "horizontal center", "right", "top",
                        "vertical center", "bottom")
    _MOUSE_OPERATION_TYPES = ("1", "2", "3C", "3", "A", "B", "C", "D",
                              "E", "F", "G")

    def GetDrawWindow(self):
        """The DrawWindow class (GetDrawWindow)."""
        return self._ok(self._draw_window)

    def GetGlobalWindow(self):
        """The GlobalWindow class holding the Global objects."""
        return self._ok(self._global_window)

    def GetMessageWindow(self):
        """The MessageWindow class."""
        return self._ok(self._message_window)

    def CreateDrawWnd(self, ocx=None):
        """Create the draw window (CreateDrawWnd).

        scPOST passes an OCX dispatch for split-window callbacks; the
        flowviewer draw window is part of the main window, so the flag
        is recorded and the DrawWindow class is returned.
        """
        self._flags["draw_window_created"] = True
        return self._ok(self._draw_window)

    def GetDockableWindow(self, wtype):
        """Window handle of MAINWINDOW/DRAWWINDOW/MESSAGEWINDOW/
        CONTROLWINDOW (GetDockableWindow); 0 when headless."""
        gui = _bridge_gui()
        name = str(wtype or "").upper()
        if gui is None or not hasattr(gui, "winId"):
            return self._ok(0)
        try:
            if name in ("MAINWINDOW", "DRAWWINDOW", ""):
                return self._ok(int(gui.winId()))
            if name == "MESSAGEWINDOW":
                msg_win = getattr(gui, "message_win", None)
                return self._ok(int(msg_win.winId())
                                if msg_win is not None else 0)
        except Exception:
            pass
        return self._ok(0)          # CONTROLWINDOW: no separate pane

    def Dock(self, myClassType, toWndName="", to_mu=1, to_rate=0.5):
        """Dock a window into another (Dock); always 0 (recorded only —
        the flowviewer layout is fixed)."""
        self._flags["dock"] = (str(myClassType), str(toWndName),
                               int(to_mu), float(to_rate))
        return 0

    def GetObjectActiveFLD(self):
        """The active FLDFile (GetObjectActiveFLD).

        The flowviewer Application merges the scPOST Application and
        FLDFile roles into one object, so the active FLD is this same
        instance; its metadata dict is returned for scripting."""
        try:
            self._need_ff()
            return self._ok(self._metadata())
        except Exception as exc:
            return self._fail(exc)

    def GetObjectFLDbyID(self, fid):
        """FLDFile by id (GetObjectFLDbyID); flowviewer holds one FLD at
        a time so only id 0 is valid."""
        try:
            if int(fid) != 0:
                raise ValueError(
                    "flowviewer holds a single FLD; only id 0 exists")
            self._need_ff()
            return self._ok(self._metadata())
        except Exception as exc:
            return self._fail(exc)

    def AlignObjectsAlongAnotherObject(self, position):
        """Align selected objects along the last-selected object
        (AlignObjectsAlongAnotherObject).  Needs a GUI selection."""
        pos = str(position or "").lower()
        if pos not in self._ALIGN_POSITIONS:
            return self._fail(ValueError(
                "position must be one of %s" %
                ", ".join(self._ALIGN_POSITIONS)))
        gui = _bridge_gui()
        handler = getattr(gui, "align_objects_along_object", None) \
            if gui else None
        if handler is None:
            return self._ok(False)   # no GUI selection to align
        try:
            return self._ok(bool(handler(pos)))
        except Exception as exc:
            return self._fail(exc)

    def AlignObjectsAlongPane(self, position):
        """Align selected objects along the pane / clipping frame
        (AlignObjectsAlongPane).  Needs a GUI selection."""
        pos = str(position or "").lower()
        if pos not in self._ALIGN_POSITIONS:
            return self._fail(ValueError(
                "position must be one of %s" %
                ", ".join(self._ALIGN_POSITIONS)))
        gui = _bridge_gui()
        handler = getattr(gui, "align_objects_along_pane", None) \
            if gui else None
        if handler is None:
            return self._ok(False)
        try:
            return self._ok(bool(handler(pos)))
        except Exception as exc:
            return self._fail(exc)

    def DefineVar(self, varname):
        """Register a user STA command (DefineVar); returns its id."""
        name = str(varname or "")
        if not name:
            return self._fail(ValueError("empty varname"))
        if name in self._defined_vars:
            return self._ok(self._defined_vars.index(name))
        self._defined_vars.append(name)
        return self._ok(len(self._defined_vars) - 1)

    def DropFile(self, path):
        """Emulate drag & drop (DropFile): FLD-family files open, STA
        files apply onto the current field; anything else fails."""
        try:
            p = str(path)
            low = p.lower()
            if low.endswith(".sta"):
                return self._ok(bool(self.ApplySTA(p)))
            from .model.dataset import load_file
            ff = load_file(p)
            if not (getattr(ff, "n_vertices", 0) or
                    getattr(ff, "n_cells", 0)):
                raise ValueError("no mesh in %r" % p)
            gui = _bridge_gui()
            if gui is not None and hasattr(gui, "_load_field_file"):
                gui._load_field_file(p)
                return self._ok(True)
            with self._lock:
                self._ff = ff
            self._cp.fire("on_open", p)
            return self._ok(True)
        except Exception as exc:
            return self._fail(exc)

    def GetCurNP(self):
        """Processing parallel number (GetCurNP); flowviewer is
        single-threaded, always 1."""
        return self._ok(1)

    def GetDisplayLOGO(self):
        """Whether the company logo is displayed (GetDisplayLOGO)."""
        return self._ok(bool(self._flags["display_logo"]))

    def GetEnvInfo(self):
        """Start-up environment info string (GetEnvInfo)."""
        import platform
        import sys
        try:
            return self._ok(
                "flowviewer %s / Python %s / %s" %
                (VERSION, sys.version.split()[0],
                 platform.platform(True)))
        except Exception as exc:
            return self._fail(exc)

    def ObjectNameDisplay(self, show):
        """Show/hide object-name balloons (ObjectNameDisplay)."""
        self._set_flag("display_obj_name", int(show) != 0)
        return 0

    def PikaPika(self, mode):
        """Direct light-preset button (PikaPika): 1 weak / 2 bright /
        3 Evaluation / 4 Metalic / 5 Shick / 6 Glossy."""
        try:
            m = int(mode)
            if not 1 <= m <= 6:
                raise ValueError("mode must be 1..6")
            brightness = {1: 0.6, 2: 1.4, 3: 1.0, 4: 1.0, 5: 1.2,
                          6: 1.3}[m]
            light = self._global_window.SetLight(brightness=brightness)
            light.title = "Light (%d)" % m
            return self._ok(True)
        except Exception as exc:
            return self._fail(exc)

    def SetBeepAll(self, use):
        """Enable/disable all beeps (SetBeepAll)."""
        return self._set_flag("beep_all", use)

    def SetDefaultAll(self, mode):
        """Reset every setting to default (SetDefaultAll); mode must
        be 0."""
        if int(mode) != 0:
            return self._fail(ValueError("mode must be 0"))
        self._flags.update({
            "display_axis": True, "display_fld": True,
            "display_title_cycle": True, "display_title_path": True,
            "display_title_time": True, "display_obj_name": False,
            "display_logo": False, "display_hint": True,
            "display_draw_mode": False, "use_undo_buffer": True,
            "use_autosave": False, "beep_all": False,
            "no_default_obj": False, "no_progress_bar": False,
            "no_next_elements": False, "not_reduce_riddge": False,
            "operate_object_enabled": True, "operation_type": "1",
            "no_controls": False, "user_control": False,
            "write_back_to_env_file": True, "visible": False,
        })
        return self._ok(True)

    def SetDisplayDrawMode(self, show):
        """Show/hide the draw mode in the drawing window."""
        return self._set_flag("display_draw_mode", show)

    def SetDisplayHint(self, show):
        """Show/hide hints (SetDisplayHint)."""
        return self._set_flag("display_hint", show)

    def SetDisplayLOGO(self, show):
        """Show/hide the logo (SetDisplayLOGO)."""
        return self._set_flag("display_logo", show)

    def SetNoControls(self):
        """Shrink the app window to the desktop corner (SetNoControls)."""
        self._flags["no_controls"] = True
        return True

    def SetNoDefaultObj(self, nouse):
        """Suppress default-object creation (SetNoDefaultObj)."""
        return self._set_flag("no_default_obj", nouse)

    def SetNoNextElements(self, ondisk):
        """Store neighbouring-element data on disk (SetNoNextElements)."""
        return self._set_flag("no_next_elements", ondisk)

    def SetNoProgressBar(self, nouse):
        """Hide the file-reading progress bar (SetNoProgressBar)."""
        return self._set_flag("no_progress_bar", nouse)

    def SetNotReduceRiddge(self, enabled):
        """Disable outline thinning (SetNotReduceRiddge)."""
        return self._set_flag("not_reduce_riddge", enabled)

    def SetOperateObjectEnabled(self, enabled):
        """Enable/disable the operate object (SetOperateObjectEnabled)."""
        return self._set_flag("operate_object_enabled", enabled)

    def SetOperationType(self, name):
        """Select the mouse-operation system (SetOperationType): "1",
        "2", "3C", "3", "A".."G"."""
        t = str(name or "").strip().upper()
        if t not in self._MOUSE_OPERATION_TYPES:
            return self._ok(False)
        self._flags["operation_type"] = t
        return self._ok(True)

    # ── application misc (scPOST R2.6) ─────────────────────────────────

    def GetPID(self):
        """Process id of this process (GetPID)."""
        import os
        try:
            return self._ok(int(os.getpid()))
        except Exception as exc:
            return self._fail(exc)

    def GetTickCount(self):
        """Elapsed milliseconds since this Application started (GetTickCount)."""
        import time
        try:
            if self._start_time is None:
                self._start_time = time.monotonic()
            return self._ok(int((time.monotonic() - self._start_time) * 1000))
        except Exception as exc:
            return self._fail(exc)

    def GetTickCountEx(self):
        """Elapsed seconds since the machine started (GetTickCountEx)."""
        import sys
        try:
            if sys.platform == "win32":
                import ctypes
                millis = ctypes.windll.kernel32.GetTickCount64()
                return self._ok(float(millis) / 1000.0)
            # POSIX: uptime from /proc/uptime, else time.monotonic fallback
            try:
                with open("/proc/uptime", "r", encoding="ascii") as fh:
                    return self._ok(float(fh.read().split()[0]))
            except Exception:
                import time
                return self._ok(float(time.monotonic()))
        except Exception as exc:
            return self._fail(exc)

    def CreateFolder(self, path):
        """Create a folder (CreateFolder); non-zero on success, 0 on fail."""
        import os
        try:
            p = str(path)
            os.makedirs(p, exist_ok=True)
            return self._ok(1 if os.path.isdir(p) else 0)
        except Exception as exc:
            return self._fail(exc)

    def GetAllFilesForWildCard(self, folder, wildcard):
        """Space-delimited quoted names matching a wildcard (GetAllFilesForWildCard)."""
        import glob
        import os
        try:
            hits = sorted(glob.glob(os.path.join(str(folder), str(wildcard))))
            return self._ok(" ".join('"%s"' % os.path.basename(h) for h in hits))
        except Exception as exc:
            return self._fail(exc)

    def GetOneOfFilesForWildCard(self, folder, wildcard):
        """First file name matching a wildcard (GetOneOfFilesForWildCard)."""
        import glob
        import os
        try:
            hits = sorted(glob.glob(os.path.join(str(folder), str(wildcard))))
            return self._ok(hits[0] if hits else "")
        except Exception as exc:
            return self._fail(exc)

    def GetRandomFilename(self):
        """A non-conflicting filename (GetRandomFilename)."""
        import tempfile
        try:
            return self._ok(tempfile.mktemp(prefix="flowviewer_", suffix=".tmp"))
        except Exception as exc:
            return self._fail(exc)

    def ShellExecute(self, path, data=""):
        """Open *path* via the Windows shell (ShellExecute).

        Uses ``os.startfile`` (win32 ``ShellExecuteW``); falls back to
        ``webbrowser``/open for non-Windows hosts.  Returns True on success.
        """
        import os
        import sys
        try:
            target = str(path)
            if not target:
                return self._ok(False)
            if sys.platform == "win32":
                os.startfile(target)          # ShellExecuteW(open)
            else:
                import subprocess
                subprocess.Popen(["xdg-open", target])
            return self._ok(True)
        except Exception as exc:
            return self._fail(exc)

    def GetEnvFilePath(self):
        """Best-effort path of the environment file (GetEnvFilePath)."""
        import os
        try:
            return self._ok(os.path.join(os.path.expanduser("~"),
                                         "flowviewer.env"))
        except Exception as exc:
            return self._fail(exc)

    def GetHomeFolder(self):
        """Current home folder (GetHomeFolder)."""
        import os
        try:
            return self._ok(os.path.expanduser("~"))
        except Exception as exc:
            return self._fail(exc)

    def IsThisPathValid(self, path):
        """Writability of a path (IsThisPathValid).

        100 empty / 1 existing file / 2 existing folder / 0 writable /
        4 not writable.
        """
        import os
        p = str(path or "")
        if not p:
            return self._ok(100)
        if os.path.isdir(p):
            return self._ok(2)
        if os.path.isfile(p):
            return self._ok(1)
        try:
            d = os.path.dirname(p) or "."
            if not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
            with open(p, "w"):
                pass
            os.remove(p)
            return self._ok(0)
        except Exception:
            return self._ok(4)

    def SetLogFilename(self, path):
        """Append call history to a file (SetLogFilename)."""
        try:
            self._log_file = str(path)
            return self._ok(True)
        except Exception as exc:
            return self._fail(exc)

    def SetMessageLevel(self, level):
        """Message verbosity 0 Simple / 1 Details / 2 Details+ (SetMessageLevel)."""
        self._msg_level = int(level)
        return 0

    def OpenMessageLogFile(self, path, dmy=0):
        """Mirror subsequent messages to a file (OpenMessageLogFile)."""
        self._msg_log_file = str(path)
        return 0

    def CloseMessageLogFile(self):
        """Stop mirroring messages to a file (CloseMessageLogFile)."""
        self._msg_log_file = None
        return 0

    def UpdateAll(self):
        """Refresh GUI/draw window (UpdateAll); calls on_redraw when attached."""
        gui = _bridge_gui()
        if gui is not None and hasattr(gui, "on_redraw"):
            try:
                gui.on_redraw()
            except Exception:
                pass
        return True

    def AnimationFrame(self, frame):
        """Animate to a frame (AnimationFrame); drives the GUI timeline when attached."""
        self._flags["anim_frame"] = int(frame)
        self._flags["animating"] = True
        gui = _bridge_gui()
        if gui is not None and hasattr(gui, "_on_timeline_step"):
            try:
                tl = getattr(gui, "timeline", None)
                if tl is not None and hasattr(tl, "set_step"):
                    tl.set_step(int(frame))
                gui._on_timeline_step(int(frame))
            except Exception:
                pass
        return int(frame)

    def AnimationSecond(self, second):
        """Animate for a duration (AnimationSecond); returns the frame count."""
        frames = max(1, int(float(second) * 15))
        self._flags["anim_frame"] = frames
        self._flags["anim_second"] = float(second)
        self._flags["animating"] = True
        gui = _bridge_gui()
        if gui is not None and hasattr(gui, "_on_timeline_step"):
            try:
                tl = getattr(gui, "timeline", None)
                if tl is not None and hasattr(tl, "set_step"):
                    tl.set_step(frames)
                gui._on_timeline_step(frames)
            except Exception:
                pass
        return frames

    # internals

    def _metadata(self):
        return {
            "kind": self.kind,
            "n_cells": self.n_cells,
            "n_vertices": self.n_vertices,
            "variables": self.variable_names,
        }


# _reg_typelib_filename_ makes UseCommandLine register the bundled typelib.
# _typelib_guid_ is deliberately NOT set: DesignatedWrapPolicy would try to
# load the typelib at wrap time (universal interfaces), which fails before
# registration.
if _TYPLIB_FILE:
    FlowviewerApplication._reg_typelib_filename_ = _TYPLIB_FILE


# ── CreateObject* family (scPOST 21/22, P0-1) ─────────────────────────────
# CreateObjectNeutral is implemented as a method on the class (opens a
# Neutral file); the remaining 21 kinds map onto api.create_object and are
# generated below so every scPOST CreateObject* name is callable.

_CREATE_OBJECT_KINDS = {
    "CreateObjectBitmap": "bitmap",
    "CreateObjectCircle": "circle",
    "CreateObjectCurve": "curve",
    "CreateObjectCutplane": "plane",
    "CreateObjectCylinder": "cylinder",
    "CreateObjectGradation": "gradation",
    "CreateObjectGrouping": "grouping",
    "CreateObjectInformation": "information",
    "CreateObjectIsosurface": "isosurface",
    "CreateObjectLight": "light",
    "CreateObjectMirror": "mirror",
    "CreateObjectOT": "maxmin",
    "CreateObjectParticles": "particle",
    "CreateObjectPCL": "pathline",
    "CreateObjectPeriod": "periodical",
    "CreateObjectPoints": "point",
    "CreateObjectRNAT": "regionbc",
    "CreateObjectStreamlines": "streamline",
    "CreateObjectSurface": "surface",
    "CreateObjectUFO": "ufo",
    "CreateObjectVolume": "volume",
}


def _make_create_object(method_name: str, kind: str):
    def method(self, *args, **kw):
        try:
            self._need_ff()
            if args and "title" not in kw:
                kw["title"] = str(args[0])
            return self._ok(self._create_kind(kind, **kw))
        except Exception as exc:
            return self._fail(exc)
    method.__name__ = method_name
    method.__doc__ = "Create a %s object (scPOST %s)." % (kind, method_name)
    return method


for _name, _kind in _CREATE_OBJECT_KINDS.items():
    setattr(FlowviewerApplication, _name, _make_create_object(_name, _kind))
del _name, _kind


def register_server() -> bool:
    """Register the COM class (and the bundled typelib) in the registry (7c)."""
    if not _HAS_COM:
        return False
    try:
        import pythoncom
        import win32com.server.register
        if _TYPLIB_FILE:
            tlb = pythoncom.LoadTypeLib(_TYPLIB_FILE)
            pythoncom.RegisterTypeLib(tlb, _TYPLIB_FILE)
        win32com.server.register.UseCommandLine(FlowviewerApplication)
        return True
    except Exception:
        return False
