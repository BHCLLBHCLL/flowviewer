"""R32: headless HTTP data service over the R31 streaming CGNS reader.

Zero third-party dependencies - ``ThreadingHTTPServer`` + stdlib
json/urllib.parse/struct. Each ``POST /api/open`` mints a
:class:`fv.model.dataset.StreamCgnsHandle` (R31) into a shared, read-only
session; windowed field reads are served as raw float64 bytes (or JSON) so a
browser/script can pull a large CGNS field tile by tile under a fixed memory
budget. Rendering reuses ``fv.api.render_png`` and degrades honestly (503 +
JSON error) when headless, per the R30 external-dependency close-out spirit.

Thread-safety: a ``StreamCgnsHandle.read_window`` re-opens the HDF5 handle per
call, so concurrent clients can read the same session handle safely.
"""

from __future__ import annotations

import json
import struct
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

VERSION = "1.0.0"


# ── JSON / binary I/O helpers ──────────────────────────────────────────────


def _send_json(handler: BaseHTTPRequestHandler, obj, status: int = 200) -> None:
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler: BaseHTTPRequestHandler, status: int, msg: str) -> None:
    obj = {"ok": False, "error": msg}
    _send_json(handler, obj, status)


# ── Session ────────────────────────────────────────────────────────────────


class _Session:
    """A read-only streaming session shared by concurrent clients."""

    def __init__(self, budget_bytes: int) -> None:
        self.budget_bytes = int(budget_bytes)
        self.handle = None
        self.mesh = None
        self.path: Optional[str] = None

    def open(self, path: str, budget_bytes: Optional[int] = None) -> None:
        from ..model.dataset import open_stream_cgns
        if budget_bytes:
            self.budget_bytes = int(budget_bytes)
        handle, mesh = open_stream_cgns(
            str(path), budget_bytes=self.budget_bytes)
        self.handle = handle
        self.mesh = mesh
        self.path = str(path)


# ── HTTP handler ───────────────────────────────────────────────────────────


class WebHandler(BaseHTTPRequestHandler):
    """Serve ``/api/*`` from a shared :class:`_Session`.

    * ``GET  /api/info``                    -> server capabilities
    * ``POST /api/open {"path", "budget_mb"}`` -> open stream handle (zero
      field payload loaded); body may be JSON or form-urlencoded
    * ``GET  /api/fields/<name>?lo=&hi=``   -> windowed field read
      (``fmt=json`` => JSON array, else raw float64 octet-stream)
    * ``GET  /api/render?w=&h=``            -> coarse-scene PNG snapshot
      (503 + JSON when no display is available)
    """

    # fields are injected per-request via ``make_handler``; class attr keeps
    # BaseHTTPRequestHandler happy and is always replaced before a request.
    session: _Session = None  # type: ignore[assignment]

    # -- boilerplate --------------------------------------------------------
    def log_message(self, fmt, *args):  # keep the gate's stderr clean
        return

    def _read_session(self) -> Optional[_Session]:
        sess = getattr(self, "session", None)
        if sess is None or sess.handle is None:
            return None
        return sess

    # -- dispatch -----------------------------------------------------------
    def do_GET(self):  # noqa: N802 (http.server convention)
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        q = urllib.parse.parse_qs(parsed.query)
        if route == "/api/info":
            return self._route_info()
        if route == "/api/render":
            return self._route_render(q)
        if route.startswith("/api/fields/"):
            name = urllib.parse.unquote(route[len("/api/fields/"):])
            return self._route_fields(name, q)
        return _send_error(self, 404, f"unknown route: {route}")

    def do_POST(self):  # noqa: N802 (http.server convention)
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/open":
            return self._route_open()
        return _send_error(self, 404, f"unknown route: {parsed.path}")

    # -- endpoint bodies ----------------------------------------------------
    def _route_info(self):
        _send_json(self, {
            "ok": True,
            "version": VERSION,
            "budget_bytes": self.session.budget_bytes if self.session else 0,
            "caps": ["info", "open", "fields", "render"],
        })

    def _read_body_obj(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        ctype = (self.headers.get("Content-Type") or "")
        if "json" in ctype:
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return {}
        # form-urlencoded
        return dict(urllib.parse.parse_qsl(raw.decode("utf-8")))

    def _route_open(self):
        data = self._read_body_obj()
        path = data.get("path")
        if not path:
            return _send_error(self, 400, "missing 'path'")
        try:
            budget_mb = int(float(data.get("budget_mb"))) if data.get(
                "budget_mb") else 0
            self.session.open(
                str(path), budget_bytes=budget_mb * 1024 * 1024 if budget_mb
                else None)
        except Exception as exc:  # noqa: BLE001
            return _send_error(self, 500, f"open failed: {exc}")
        handle = self.session.handle
        fields = [{"name": n, "n": int(handle.field_len(n))}
                  for n in handle.field_names()]
        mesh = self.session.mesh or {}
        _send_json(self, {
            "ok": True,
            "path": self.session.path,
            "n_vertices": int(mesh.get("n_vertices", 0)),
            "n_cells": int(mesh.get("n_cells", 0)),
            "fields": fields,
        })

    def _route_fields(self, name: str, q: dict):
        sess = self._read_session()
        if sess is None:
            return _send_error(self, 409, "no dataset open")
        handle = sess.handle
        if name not in handle.field_names():
            return _send_error(self, 404, f"no field {name!r}")
        try:
            lo = int(q.get("lo", ["0"])[0])
            hi = int(q.get("hi", [str(handle.field_len(name))])[0])
            fmt = q.get("fmt", ["bin"])[0].lower()
        except Exception as exc:  # noqa: BLE001
            return _send_error(self, 400, f"bad query: {exc}")
        try:
            lo0, data = handle.read_window(name, lo, hi)
        except Exception as exc:  # noqa: BLE001
            return _send_error(self, 500, f"read failed: {exc}")
        total = int(handle.field_len(name))
        if fmt == "json":
            vals = data.ravel().tolist() if data.size else []
            _send_json(self, {"ok": True, "name": name, "lo": lo0,
                              "n": int(data.size), "total": total,
                              "values": vals})
            return
        payload = struct.pack("%sd" % int(data.size),
                              *data.ravel().tolist())
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("X-Total", str(total))
        self.send_header("X-Lo", str(int(lo0)))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _route_render(self, q: dict):
        sess = self._read_session()
        if sess is None:
            return _send_error(self, 409, "no dataset open")
        if not getattr(self, "_has_display", True):
            return _send_error(
                self, 503, "render unavailable headless; data paths remain live")
        import io

        from .. import api as fv
        path = sess.path or ""
        try:
            ff = fv.open_file(path)  # FieldFile for scene build
            buf = io.BytesIO()
            ok = fv.render_png(ff, str(buf))
            if not ok:
                return _send_error(
                    self, 503,
                    "render produced no image (no display); data paths remain live")
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(buf.getvalue().__len__()))
            self.end_headers()
            self.wfile.write(buf.getvalue())
        except Exception as exc:  # noqa: BLE001
            return _send_error(self, 503, f"render unavailable: {exc}")


def make_handler(session: _Session) -> type:
    """Threading handler bound to a shared *session*."""
    sess = session  # local name so the class body resolves it from the scope

    class _BoundHandler(WebHandler):
        session = sess

    return _BoundHandler


class WebViewerServer(ThreadingHTTPServer):
    """A drop-in ``ThreadingHTTPServer`` mounted on a streaming session."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, session: _Session,
                 *, host: str = "127.0.0.1", port: int = 0):
        self._session = session
        super().__init__((host, port), make_handler(session))

    @property
    def port(self) -> int:
        return int(self.server_address[1])


def serve_session(handle, port: int = 0, host: str = "127.0.0.1",
                  *, budget_bytes: int = 32 * 1024 * 1024,
                  in_thread: bool = False):
    """Start a :class:`WebViewerServer` around an existing *handle*.

    Returns either the server (when ``in_thread=False``; caller serves) or a
    ``(server, thread)`` pair already running in the background.
    """
    sess = _Session(budget_bytes)
    sess.handle = handle
    server = WebViewerServer((host, port), sess, host=host, port=port)
    if not in_thread:
        return server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
