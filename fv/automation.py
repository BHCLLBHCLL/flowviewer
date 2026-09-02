"""R32: headless collaboration-automation session over the streaming reader.

:class:`AutomationSession` is a script/COM-friendly facade that unifies the
R31 streaming handle with the existing :mod:`fv.api` scene/render path so a
collaborator (another process, a batch script, or an HTTP client) can:

* ``open(path, stream=True, budget_mb=64)`` — open a CGNS streaming-closed
  (fields zero-payload) and, for render/report, a lazy FieldFile;
* ``fields()`` / ``query(name, lo, hi)`` — windowed field reads;
* ``render(png, w, h)`` — coarse-scene snapshot (honestly False when headless);
* ``export_report(html, live=...)`` — bake a self-contained HTML report;
* ``serve(port=0)`` — publish the handle over the R32 HTTP RPC in a background
  thread so other processes can collaborate over localhost.

``query`` returns ``(lo, np.ndarray)`` — the *same* contract as
``StreamCgnsHandle.read_window``, so existing streaming tests remain valid.
"""

from __future__ import annotations

import threading
from typing import Optional


class AutomationSession:
    """A one-dataset collaboration/automation context."""

    def __init__(self, budget_mb: int = 64, *, live: bool = False):
        self.budget_mb = int(budget_mb)
        self.live = bool(live)
        self.handle = None            # StreamCgnsHandle (query)
        self.mesh = None             # geometry dict from open_stream_cgns
        self.ff = None               # lazy FieldFile (render/report)
        self.path: Optional[str] = None
        self._server = None
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ----------------------------------------------------------
    def open(self, path: str, *, stream: bool = True,
             budget_mb: Optional[int] = None) -> "AutomationSession":
        from .model.dataset import load_file, open_stream_cgns
        self.path = str(path)
        if stream:
            budget = int(budget_mb or self.budget_mb) * 1024 * 1024
            self.handle, self.mesh = open_stream_cgns(self.path,
                                                      budget_bytes=budget)
        else:
            self.handle = None
            self.mesh = None
        # lazy FieldFile for scene build / render (geometry only)
        self.ff = load_file(self.path, lazy_vars=True)
        return self

    def close(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:  # pragma: no cover
                pass
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.handle = None
        self.ff = None
        self.mesh = None

    def __enter__(self) -> "AutomationSession":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- query --------------------------------------------------------------
    def fields(self) -> list:
        if self.handle is None:
            raise RuntimeError("no stream open; call open(stream=True)")
        return list(self.handle.field_names())

    def query(self, name: str, lo: int, hi: int, *, tile: int = 0) -> tuple:
        """Windowed read ``[lo, hi)`` -> ``(lo, np.ndarray float64)``."""
        if self.handle is None:
            raise RuntimeError("no stream open; call open(stream=True)")
        return self.handle.read_window(name, lo, hi, tile=tile)

    # -- output -------------------------------------------------------------
    def render(self, png_path: str, w: int = 1280, h: int = 720,
               objects=None) -> bool:
        """Coarse-scene snapshot; False when headless (honest degrade)."""
        if self.ff is None:
            raise RuntimeError("no dataset open")
        from . import api as fv
        return fv.render_png(self.ff, str(png_path), objects=objects)

    def export_report(self, html_path: str, *, live: Optional[bool] = None) -> bool:
        """Bake a self-contained HTML report from the stream handle."""
        if self.handle is None:
            raise RuntimeError("no stream open; call open(stream=True)")
        from .web.report import render_report
        return render_report(
            self.handle, str(html_path), live=self.live if live is None
            else live, mesh=self.mesh, source_name=self.path or "")

    # -- collaboration RPC --------------------------------------------------
    def serve(self, port: int = 0, host: str = "127.0.0.1") -> int:
        """Publish this dataset over the R32 HTTP RPC in a background thread.

        Returns the actual bound port. Clients can then hit ``/api/fields``
        et al. over localhost to pull windowed data for collaboration.
        """
        if self.handle is None:
            raise RuntimeError("no stream open; call open(stream=True)")
        from .web.server import serve_session
        self._server, self._thread = serve_session(
            self.handle, port=port, host=host,
            budget_bytes=int(self.budget_mb) * 1024 * 1024, in_thread=True)
        return self._server.port
