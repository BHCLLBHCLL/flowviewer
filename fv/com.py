"""COM automation interface (scPOST VBS/COM, 7c) via pywin32.

Exposes a flowviewer.Application COM class with:

* lifecycle  - open_file / close / quit / release and context-manager use;
* properties - version, file_path, kind, n_cells, n_vertices, cycle, time,
  variable_names, has_file (read-only attributes);
* events     - subscribe/unsubscribe callbacks fired on open/close.

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


class FlowviewerApplication:
    """COM-exposed flowviewer Application object (7c).

    Lifecycle: open_file replaces any previously loaded file and fires the
    on_open event; close()/quit() release the file and fire on_close; the
    object also works as a context manager (with) and releases the file in
    __del__.

    Events: subscribe(callback)/unsubscribe(callback) register a COM
    callback object; on each event the object calls callback.on_open(path)
    / callback.on_close() when present, else callback(event_dict).
    """

    _reg_clsid_ = "{A1B2C3D4-5E6F-4A7B-8C9D-0E1F2A3B4C5D}"
    _reg_progid_ = "flowviewer.Application"
    _reg_desc_ = "flowviewer post-processor"
    _public_methods_ = [
        "open_file", "variables", "cycles", "quit",
        "close", "release", "subscribe", "unsubscribe",
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
        self._sinks = []

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
        with self._lock:
            self._sinks = []

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

    def subscribe(self, callback):
        """Register a COM event sink object."""
        if callback is None:
            return 0
        with self._lock:
            if callback not in self._sinks:
                self._sinks.append(callback)
            return len(self._sinks)

    def unsubscribe(self, callback):
        """Remove a previously registered event sink."""
        with self._lock:
            if callback in self._sinks:
                self._sinks.remove(callback)
            return len(self._sinks)

    # internals

    def _metadata(self):
        return {
            "kind": self.kind,
            "n_cells": self.n_cells,
            "n_vertices": self.n_vertices,
            "variables": self.variable_names,
        }

    def _emit(self, event, **data):
        """Deliver event to every sink without letting one break others."""
        with self._lock:
            sinks = list(self._sinks)
        for cb in sinks:
            try:
                handler = getattr(cb, event, None)
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
