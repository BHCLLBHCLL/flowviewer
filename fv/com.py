"""COM automation interface (scPOST VBS/COM, 7c) via pywin32.

Registers a 'flowviewer.Application' COM class exposing open_file and
variable queries.  Requires pywin32; registration writes to the Windows
registry (run RegisterServer() with the right privileges).
"""

from __future__ import annotations


try:
    import pythoncom  # noqa: F401
    import win32com.server.register  # noqa: F401
    _HAS_COM = True
except Exception:
    _HAS_COM = False


class FlowviewerApplication:
    """COM-exposed flowviewer Application object (7c)."""

    _reg_clsid_ = "{A1B2C3D4-0000-0000-0000-FLOWVIEWER0}"
    _reg_progid_ = "flowviewer.Application"
    _reg_desc_ = "flowviewer post-processor"
    _public_methods_ = ["open_file", "variables", "cycles", "quit"]
    _public_attrs_ = ["__module__"]

    def __init__(self):
        self._ff = None

    def open_file(self, path):
        """Load a field file and return a metadata dict."""
        from .model.dataset import load_file
        ff = load_file(path)
        self._ff = ff
        return {
            "kind": ff.kind,
            "n_cells": ff.n_cells,
            "n_vertices": ff.n_vertices,
            "variables": sorted(ff.variables),
        }

    def variables(self):
        """Variable names of the currently loaded file."""
        return sorted(self._ff.variables) if self._ff is not None else []

    def cycles(self):
        """Cycle id of the loaded file (0 when absent)."""
        if self._ff is None:
            return 0
        return self._ff.cycle if self._ff.cycle is not None else 0

    def quit(self):
        """Release the loaded file."""
        self._ff = None


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