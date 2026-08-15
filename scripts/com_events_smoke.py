"""COM events smoke test for flowviewer.Application (WithEvents path).

Usage::

    python scripts/com_events_smoke.py --register            # register (admin)
    python scripts/com_events_smoke.py --smoke <file.fph>    # real COM smoke
    python scripts/com_events_smoke.py --inproc <file.fph>   # no-registration smoke

The smoke exercises the scPOST VBS "WithEvents" equivalent: connect a sink
through IConnectionPoint (FindConnectionPoint -> Advise), fire open_file and
close, and verify on_open / on_close reach the sink.  The win32com
DispatchWithEvents helper requires a typelib, which the generic pywin32
server does not ship, so it is attempted first and reported when it is
unavailable; the manual connection-point path is the authoritative fallback.
"""

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fv.com import EVENTS_IID, FlowviewerApplication, register_server


class Sink:
    """COM event sink: wrap-able (public methods) + event-IID QI."""

    _public_methods_ = ["OnOpen", "OnClose"]  # first method -> DISPID 1000

    def __init__(self):
        self.opened = []
        self.closed = 0

    def _query_interface_(self, iid):
        import win32com.server.util
        if str(iid).strip("{}").lower() == EVENTS_IID.strip("{}").lower():
            return win32com.server.util.wrap(self)
        return None

    def OnOpen(self, path):
        self.opened.append(path)

    def OnClose(self):
        self.closed += 1


def run_inproc(path):
    """Smoke without COM registration via a real connection-point link.

    Wraps the Python application as a COM gateway and links a COM sink
    through SimpleConnection (QI IConnectionPointContainer ->
    FindConnectionPoint -> Advise), exercising the genuine COM path.
    """
    import win32com.client.dynamic
    import win32com.client.connect
    import win32com.server.util
    app = FlowviewerApplication()
    server = win32com.client.dynamic.Dispatch(
        win32com.server.util.wrap(app))
    sink = Sink()
    conn = win32com.client.connect.SimpleConnection()
    try:
        conn.Connect(server, sink, EVENTS_IID)
        server.open_file(path)
        server.close()
    finally:
        conn.Disconnect()
    ok = path in sink.opened and sink.closed == 1
    return {"ok": ok, "opened": sink.opened, "closed": sink.closed}


def run_com(path):
    """Smoke against the registered flowviewer.Application ProgID."""
    result = {"dispatch_with_events": "skipped"}
    try:
        import win32com.client
        try:
            # Requires a typelib; reports cleanly when the generic server
            # lacks one (raises TypeError / ValueError).
            app = win32com.client.DispatchWithEvents(
                "flowviewer.Application", Sink)
            result["dispatch_with_events"] = "available"
            app.open_file(path)
            app.close()
            return {"ok": True, "path": "dispatch_with_events",
                    "dispatch_with_events": "available"}
        except (TypeError, ValueError, AttributeError) as exc:
            result["dispatch_with_events"] = "unavailable: " + str(exc)[:80]
        # Manual connection-point fallback (Dispatch + FindConnectionPoint)
        app = win32com.client.Dispatch("flowviewer.Application")
        cp = app.FindConnectionPoint(EVENTS_IID)
        if cp is None:
            return {"ok": False, "reason": "FindConnectionPoint returned None",
                    "dispatch_with_events": result["dispatch_with_events"]}
        sink = Sink()
        cookie = cp.Advise(sink)
        app.open_file(path)
        app.close()
        cp.Unadvise(cookie)
        ok = path in sink.opened and sink.closed == 1
        return {"ok": ok, "opened": sink.opened, "closed": sink.closed,
                "dispatch_with_events": result["dispatch_with_events"]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc),
                "dispatch_with_events": result.get("dispatch_with_events")}


def main(argv):
    if "--register" in argv:
        ok = register_server()
        print("register_server:", "OK" if ok else "failed (pywin32 + admin needed)")
        return 0 if ok else 1
    path = None
    for i, a in enumerate(argv):
        if a in ("--smoke", "--inproc") and i + 1 < len(argv):
            path = argv[i + 1]
    if not path:
        print(__doc__)
        return 2
    if "--smoke" in argv:
        r = run_com(path)
    else:
        r = run_inproc(path)
    print("SMOKE:", "OK" if r.get("ok") else "FAIL", r)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
