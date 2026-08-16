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
        # status / export
        "SaveSTA", "ApplySTA", "SaveSTL",
        # application state (Set* family + animation)
        "SetDisplayAxis", "SetDisplayFLD", "SetDisplayTitleCycle",
        "SetDisplayTitlePath", "SetDisplayTitleTime", "SetDisplayObjName",
        "SetUseUndoBuffer", "SetUseAutoSave", "AnimationStart",
        "AnimationStop", "PrepareMinMaxPos", "SplitView",
        "ObjectNameArrange",
    ]
    _public_attrs_ = [
        "version", "file_path", "kind", "n_cells", "n_vertices",
        "cycle", "time", "variable_names", "has_file",
        "ErrorCode", "ErrorString",
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
        self._err_code = 0
        self._err_str = "OK"
        self._flags = {
            "display_axis": True, "display_fld": True,
            "display_title_cycle": True, "display_title_path": True,
            "display_title_time": True, "display_obj_name": False,
            "use_undo_buffer": True, "use_autosave": False,
            "minmax_pos": False, "split_view": 0, "animating": False,
        }
        self._lock = threading.RLock()
        self._cp = ConnectionPoint(self)
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
                self._ff = load_member(fs, 1, cache=rt.cache)
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

    # ── status / export (P3) ──────────────────────────────────────────────

    def SaveSTA(self, filepath):
        """Save the current object tree to a .sta status file (SaveSTA)."""
        try:
            from . import api
            from .model.objects import MainObject
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
        """Begin animation (AnimationStart; state flag headless)."""
        return self._set_flag("animating", True)

    def AnimationStop(self):
        """Stop animation (AnimationStop; state flag headless)."""
        return self._set_flag("animating", False)

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
