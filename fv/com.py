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
    """

    _reg_clsid_ = "{A1B2C3D4-5E6F-4A7B-8C9D-0E1F2A3B4C5D}"
    _reg_progid_ = "flowviewer.Application"
    _reg_desc_ = "flowviewer post-processor"
    _public_methods_ = [
        "open_file", "variables", "cycles", "quit",
        "close", "release", "subscribe", "unsubscribe",
        "EnumConnectionPoints", "FindConnectionPoint",
    ]
    _public_attrs_ = [
        "version", "file_path", "kind", "n_cells", "n_vertices",
        "cycle", "time", "variable_names", "has_file",
    ]
    _readonly_attrs_ = [
        "version", "file_path", "kind", "n_cells", "n_vertices",
        "cycle", "time", "variable_names", "has_file",
    ]

    def __init__(self):
        self._ff = None
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
