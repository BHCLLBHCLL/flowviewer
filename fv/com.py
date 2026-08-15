"""COM automation interface (scPOST VBS/COM, 7c) via pywin32.

Exposes a flowviewer.Application COM class with:

* lifecycle  - open_file / close / quit / release and context-manager use;
* properties - version, file_path, kind, n_cells, n_vertices, cycle, time,
  variable_names, has_file (read-only attributes);
* events     - a standard IConnectionPointContainer / IConnectionPoint pair
  (Advise/Unadvise/EnumConnections) so a VBS client can connect a sink via
  app.FindConnectionPoint(iid).Advise(sink), plus subscribe/unsubscribe as a
  thin Python-friendly alias.

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


class FlowviewerApplicationEvents:
    """COM event (outgoing) interface contract for VBS WithEvents (3).

    The sink object a client registers must implement::

        on_open(path)   # fired after open_file loads a file
        on_close()      # fired after close()/quit() releases it
    """

    _reg_clsid_ = EVENTS_IID
    _public_methods_ = ["on_open", "on_close"]


class ConnectionPoint:
    """IConnectionPoint semantics: Advise / Unadvise / EnumConnections (3)."""

    _public_methods_ = [
        "Advise", "Unadvise", "EnumConnections", "GetConnectionInterface",
    ]

    def __init__(self, owner):
        self._owner = owner
        self._lock = threading.RLock()
        self._sinks = {}
        self._next = 1

    def GetConnectionInterface(self):
        """The IID of the outgoing event interface."""
        return EVENTS_IID

    def Advise(self, sink):
        """Register a sink; returns an opaque connection cookie."""
        if sink is None:
            return 0
        with self._lock:
            cookie = self._next
            self._next += 1
            self._sinks[cookie] = sink
            return cookie

    def Unadvise(self, cookie):
        """Remove a sink by cookie; returns True when it existed."""
        with self._lock:
            return self._sinks.pop(cookie, None) is not None

    def EnumConnections(self):
        """Snapshot of currently advised sinks (IEnumConnections flavour)."""
        with self._lock:
            return list(self._sinks.values())

    def sinks(self):
        """Alias of EnumConnections for the Python event dispatcher."""
        return self.EnumConnections()

    def clear(self):
        """Drop every advised sink."""
        with self._lock:
            self._sinks.clear()


class ConnectionPointContainer:
    """IConnectionPointContainer semantics (3)."""

    _public_methods_ = ["EnumConnectionPoints", "FindConnectionPoint"]

    def __init__(self, cp):
        self._cp = cp

    def EnumConnectionPoints(self):
        """The single outgoing connection point (IEnumConnectionPoints)."""
        return [self._cp]

    def FindConnectionPoint(self, iid):
        """Return the connection point for the event IID (or None)."""
        if _iid_matches(iid, EVENTS_IID):
            return self._cp
        return None


def _iid_matches(a, b):
    """Compare GUID strings, ignoring case and optional braces."""
    a = (a or "").strip().strip("{}").lower()
    b = (b or "").strip().strip("{}").lower()
    return a == b


class FlowviewerApplication:
    """COM-exposed flowviewer Application object (7c).

    Lifecycle: open_file replaces any previously loaded file and fires
    on_open; close()/quit() release the file and fire on_close; the object
    also works as a context manager (with) and releases in __del__.

    Events: a VBS client may connect via
    app.FindConnectionPoint(iid).Advise(sink); subscribe/unsubscribe are a
    Python-friendly alias over the same connection point.
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
        self._cpc = ConnectionPointContainer(self._cp)
        if _HAS_COM:
            try:
                import pythoncom as _pc
                self._com_interfaces_ = [_pc.IID_IConnectionPointContainer]
            except Exception:
                pass

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
        """Load a field file and return a metadata dict (fires on_open)."""
        from .model.dataset import load_file
        ff = load_file(path)
        with self._lock:
            self._ff = ff
        self._emit("on_open", path=str(path))
        return self._metadata()

    def close(self):
        """Release the loaded file (fires on_close)."""
        with self._lock:
            had = self._ff is not None
            self._ff = None
        if had:
            self._emit("on_close")

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
        return self._cpc.EnumConnectionPoints()

    def FindConnectionPoint(self, iid):
        """Return the connection point for an event IID (or None)."""
        return self._cpc.FindConnectionPoint(iid)

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

    def _emit(self, event, **data):
        """Deliver event to every advised sink without one breaking others."""
        for cb in self._cp.sinks():
            try:
                handler = getattr(cb, event, None)
                if handler is None:
                    # VBS/IDispatch case-insensitive fallback (OnOpen/OnClose)
                    for cand in dir(cb):
                        if cand.lower() == event.replace("_", "").lower():
                            handler = getattr(cb, cand, None)
                            break
                if handler is not None:
                    if data:
                        handler(**data)
                    else:
                        handler()
                else:
                    payload = {"event": event}
                    payload.update(data)
                    cb(payload)
            except Exception:
                continue


def register_server() -> bool:
    """Register the COM class in the Windows registry (7c)."""
    if not _HAS_COM:
        return False
    try:
        import win32com.server.register
        win32com.server.register.UseCommandLine(FlowviewerApplication)
        return True
    except Exception:
        return False
