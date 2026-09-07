"""R82/R86: headless HTTP service for report-family bundles (R64-R81).

``run_report_bundle`` / ``write_report_index`` / ``export_report_bundle``
(``fv.gui.analysis``) produce a bundle directory of self-contained single-file
HTML reports plus an ``index.html`` linking them by basename. R32
(:mod:`fv.web.server`) serves only the R31 *streaming CGNS* surface; it cannot
browse or share a report bundle. This module closes that gap by mounting a
bundle directory on a stdlib ``ThreadingHTTPServer`` -- no GUI, no third-party
dependencies -- so the report family can be opened, shared and downloaded from
any browser, in the R30 headless close-out spirit.

Endpoints:

* ``GET /``                     -> metadata dashboard (report label + title +
  size + mtime; ``/index.html`` stays the untouched bundle index file)
* ``GET /index.html``           -> bundle index page (generated if absent)
* ``GET /api/list``             -> JSON report listing (name + human label)
* ``GET /api/meta``             -> JSON per-report metadata + aggregate summary
  (label/title/size/mtime)
* ``GET /api/summary``          -> JSON bundle overview (count / total size /
  generated span)
* ``GET /api/bundle.zip``       -> download the whole bundle as an archive
* ``GET /<report>.html``        -> a single report (path-traversal safe)

R86 deepens the web presentation: ``/`` is no longer a bare ``<ul>`` of links but
a live dashboard built from ``report_meta`` (report's own ``<title>`` plus
``os.stat`` size / mtime), and ``/api/meta`` exposes that same metadata as JSON.
R87 adds a bundle overview: ``bundle_summary`` aggregates the per-report metadata
into a count / total size / generated span, the dashboard renders it as a summary
block, and ``/api/meta`` (plus the new ``/api/summary``) exposes it machine-
readably. No third-party dependencies are added.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import tempfile
import threading
import urllib.parse
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

VERSION = "1.0.0"
_DEFAULT_TITLE = "flowviewer analysis bundle"
_HTML_SUFFIXES = (".html", ".htm")

# ``report_index_html`` emits one `<li><a href="X">label</a></li>` per report.
_ITEM_RE = re.compile(r'<li>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>\s*</li>',
                      re.S)


# ── helpers ────────────────────────────────────────────────────────────────


def _send_json(handler: BaseHTTPRequestHandler, obj, status: int = 200) -> None:
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler: BaseHTTPRequestHandler, status: int, msg: str) -> None:
    _send_json(handler, {"ok": False, "error": msg}, status)


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def bundle_title(index) -> str:
    """Return the ``<title>`` of a bundle index, or a sensible default."""
    if index is not None and Path(index).is_file():
        try:
            text = Path(index).read_text(encoding="utf-8")
        except OSError:
            text = ""
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        if m:
            value = html.unescape(_strip_tags(m.group(1))).strip()
            if value:
                return value
    return _DEFAULT_TITLE


def bundle_listings(bundle_dir) -> list[dict]:
    """Ordered report listings ``[{"name", "label"}]`` for a bundle directory.

    Prefers the ``<li><a href="X">Y</a></li>`` entries in ``index.html`` (the
    format emitted by ``fv.gui.analysis.report_index_html``) so the index order
    and labels survive; falls back to a sorted ``*.html`` scan (excluding
    ``index.html``) when the index is absent or unparseable.
    """
    bdir = Path(bundle_dir)
    index = bdir / "index.html"
    if index.is_file():
        try:
            text = index.read_text(encoding="utf-8")
        except OSError:
            text = ""
        items = []
        for match in _ITEM_RE.finditer(text):
            href = html.unescape(match.group(1))
            label = html.unescape(_strip_tags(match.group(2))).strip()
            items.append({"name": href, "label": label or href})
        if items:
            return items
    rows = []
    for path in sorted(bdir.glob("*.html")):
        if path.name == "index.html":
            continue
        rows.append({"name": path.name, "label": path.stem})
    return rows


def _fallback_index_html(listings: list[dict], title: str) -> str:
    items = "".join(
        f'<li><a href="{html.escape(item["name"])}">'
        f"{html.escape(item['label'])}</a></li>"
        for item in listings)
    return ("<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title></head><body>"
            f"<h1>{html.escape(title)}</h1>"
            f"<p>{len(listings)} report(s) generated.</p>"
            f"<ul>{items}</ul></body></html>\n")


def _fmt_size(nbytes: int) -> str:
    """Human-readable byte size (e.g. ``1.2 kB``) for a dashboard caption."""
    n = float(nbytes)
    if n < 1024.0:
        return f"{int(n)} B"
    for unit in ("kB", "MB", "GB"):
        n /= 1024.0
        if n < 1024.0 or unit == "GB":
            return f"{n:.1f} {unit}"
    return f"{n:.1f} GB"


def _fmt_mtime(timestamp: float) -> str:
    """Human-readable local mtime (``YYYY-MM-DD HH:MM``), or ``""``."""
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def report_meta(bundle_dir) -> list[dict]:
    """Per-report metadata ``[{name, label, title, size_bytes, mtime}]``.

    Builds on :func:`bundle_listings` so the index order and human labels
    survive, then augments every report with its own ``<title>`` plus the
    ``os.stat`` size / mtime. A report that the index names but that is missing
    or unreadable degrades to ``size 0`` / ``mtime 0.0`` / ``title ""`` without
    raising, so a stale index never breaks a dashboard or ``/api/meta``.
    """
    bdir = Path(bundle_dir)
    rows = []
    for item in bundle_listings(bdir):
        target = (bdir / item["name"]).resolve()
        stat = None
        try:
            stat = target.stat()
        except OSError:
            stat = None
        title = bundle_title(target) if stat is not None else ""
        rows.append({
            "name": item["name"],
            "label": item["label"],
            "title": title,
            "size_bytes": int(stat.st_size) if stat else 0,
            "mtime": float(stat.st_mtime) if stat else 0.0,
        })
    return rows


def _summary_from_rows(rows: list[dict]) -> dict:
    """Aggregate overview from a list of :func:`report_meta` rows."""
    total = 0
    times = []
    for row in rows:
        total += row["size_bytes"]
        if row["mtime"]:
            times.append(row["mtime"])
    return {
        "report_count": len(rows),
        "total_bytes": total,
        "oldest": _fmt_mtime(min(times)) if times else "",
        "newest": _fmt_mtime(max(times)) if times else "",
    }


def bundle_summary(bundle_dir) -> dict:
    """Aggregate overview of a bundle: count, total size, generated span.

    Built on :func:`report_meta` so it honours the index order and degrades the
    same way (missing / unreadable entries contribute 0 bytes and no mtime).
    ``oldest`` / ``newest`` are formatted local mtimes (``YYYY-MM-DD HH:MM``) or
    ``""`` when no report carries an mtime, so an empty or all-degenerate bundle
    yields a clean zero overview instead of raising.
    """
    return _summary_from_rows(report_meta(bundle_dir))


_SORT_KEYS = ("name", "label", "title", "size", "mtime")


def query_reports(rows, *, q=None, sort=None, dir="asc") -> list[dict]:
    """Filter / sort a list of :func:`report_meta` rows (R88).

    ``q`` is a case-insensitive substring match against a row's ``name``,
    ``label`` or ``title``. ``sort`` orders by ``name``/``label``/``title``
    (text, case-insensitive) or ``size``/``mtime`` (numeric); ``dir`` is
    ``"asc"`` (default) or ``"desc"``. An unknown ``sort`` key raises
    :class:`ValueError`. With no arguments the rows are returned in their given
    (index) order, so the dashboard and ``/api/meta`` stay backward compatible.
    """
    result = list(rows)
    if q:
        needle = q.lower()
        result = [
            row for row in result
            if needle in row["name"].lower()
            or needle in row["label"].lower()
            or needle in row["title"].lower()
        ]
    if sort:
        if sort not in _SORT_KEYS:
            raise ValueError(f"unknown sort key {sort!r}")
        key = {"size": "size_bytes", "mtime": "mtime"}.get(sort, sort)

        def _key(row):
            value = row[key]
            return value.lower() if isinstance(value, str) else value

        result = sorted(result, key=_key, reverse=dir == "desc")
    return result


def dashboard_html(bundle_dir, title=None, *, q=None, sort=None, dir="asc") -> str:
    """A richer bundle overview page with per-report metadata (R86).

    Keeps the ``report_index_html`` ``<li><a href="X">label</a></li>`` anchors so
    :func:`bundle_listings` still parses the page, and adds a ``<li class="meta">``
    caption after each report with its own ``<title>``, size and modified time —
    so a served bundle reads as a navigable dashboard instead of a bare link
    list. R87 renders a ``<p class="summary">`` block above the list (report
    count, total size, generated span) built from :func:`bundle_summary`. R88
    lets ``q`` filter by title/label/name and ``sort``/``dir`` re-order the
    reports, so ``/?q=&sort=&dir=`` gives a searchable, re-rankable dashboard
    (the summary block tracks the visible subset). ``title`` (fallback: the
    bundle's ``<title>``) drives the ``<h1>``.
    """
    bdir = Path(bundle_dir)
    heading = title or bundle_title(bdir / "index.html")
    rows = query_reports(report_meta(bdir), q=q, sort=sort, dir=dir)
    summary = _summary_from_rows(rows)
    summary_parts = [
        f'{summary["report_count"]} report(s)',
        f'{_fmt_size(summary["total_bytes"])} total',
    ]
    if summary["oldest"]:
        summary_parts.append(
            f'generated {summary["oldest"]} – {summary["newest"]}')
    items = []
    for row in rows:
        items.append(
            f'<li><a href="{html.escape(row["name"])}">'
            f"{html.escape(row['label'])}</a></li>\n")
        caption_parts = [part for part in (row["title"], _fmt_size(
            row["size_bytes"]), _fmt_mtime(row["mtime"])) if part]
        items.append(f'<li class="meta">{html.escape(" · ".join(caption_parts))}'
                     f"</li>\n")
    body = "".join(items)
    return ("<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(heading)}</title></head><body>"
            f"<h1>{html.escape(heading)}</h1>"
            f'<p class="summary">{html.escape(" · ".join(summary_parts))}</p>'
            f"<ul>\n{body}</ul></body></html>\n")


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _HTML_SUFFIXES:
        return "text/html; charset=utf-8"
    if suffix == ".png":
        return "image/png"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"


# ── HTTP handler ───────────────────────────────────────────────────────────


class ReportBundleHandler(BaseHTTPRequestHandler):
    """Serve a report bundle directory over ``/`` and ``/api/*``.

    ``bundle_dir`` and ``index`` are injected per-request via
    :func:`make_handler`; the class attributes keep ``BaseHTTPRequestHandler``
    happy and are always replaced before a request arrives.
    """

    bundle_dir: Path = None  # type: ignore[assignment]
    index: Optional[Path] = None

    def log_message(self, fmt, *args):  # keep the gate's stderr clean
        return

    # -- dispatch -----------------------------------------------------------
    def do_GET(self):  # noqa: N802 (http.server convention)
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        if route == "/":
            return self._route_dashboard()
        if route == "/index.html":
            return self._route_index()
        if route == "/api/list":
            return self._route_list()
        if route == "/api/meta":
            return self._route_meta()
        if route == "/api/summary":
            return self._route_summary()
        if route == "/api/bundle.zip":
            return self._route_zip()
        return self._route_file(route)

    # -- endpoint bodies ----------------------------------------------------
    def _route_index(self):
        index = self.index
        if index is not None and Path(index).is_file():
            return self._serve_path(Path(index), "text/html; charset=utf-8")
        title = bundle_title(index)
        listings = bundle_listings(self.bundle_dir)
        html_body = _fallback_index_html(listings, title)
        payload = html_body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _param(self, key: str) -> Optional[str]:
        """First value of a query string parameter, or ``None``."""
        parsed = urllib.parse.urlsplit(self.path)
        return urllib.parse.parse_qs(parsed.query).get(key, [None])[0]

    def _route_dashboard(self):
        """Serve the metadata dashboard at ``/`` (R86, queryable in R88)."""
        title = bundle_title(self.index)
        try:
            payload = dashboard_html(
                self.bundle_dir, title, q=self._param("q"),
                sort=self._param("sort"), dir=self._param("dir") or "asc",
            ).encode("utf-8")
        except ValueError as exc:
            return _send_error(self, 400, str(exc))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _route_meta(self):
        try:
            rows = query_reports(
                report_meta(self.bundle_dir), q=self._param("q"),
                sort=self._param("sort"), dir=self._param("dir") or "asc",
            )
        except ValueError as exc:
            return _send_error(self, 400, str(exc))
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "reports": rows,
            "summary": _summary_from_rows(rows),
        })

    def _route_summary(self):
        """Serve the bundle overview as JSON (R87)."""
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "summary": bundle_summary(self.bundle_dir),
        })

    def _route_list(self):
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "reports": bundle_listings(self.bundle_dir),
        })

    def _route_zip(self):
        bdir = Path(self.bundle_dir)
        files = sorted(p for p in bdir.rglob("*") if p.is_file())
        if not files:
            return _send_error(self, 404, "empty bundle")
        fd, tmp = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in files:
                    zf.write(path, arcname=path.relative_to(bdir).as_posix())
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header(
                "Content-Disposition", 'attachment; filename="bundle.zip"')
            self.send_header("Content-Length", str(os.path.getsize(tmp)))
            self.end_headers()
            with open(tmp, "rb") as fh:
                shutil.copyfileobj(fh, self.wfile)
        except OSError as exc:
            return _send_error(self, 500, f"zip failed: {exc}")
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _route_file(self, route: str):
        rel = urllib.parse.unquote(route.lstrip("/"))
        if not rel:
            return _send_error(self, 400, "empty path")
        bdir = Path(self.bundle_dir)
        target = (bdir / rel).resolve()
        if bdir not in (target, *target.parents):
            return _send_error(self, 403, "path escapes bundle")
        if not target.is_file():
            return _send_error(self, 404, f"not found: {route}")
        return self._serve_path(target, _content_type(target))

    # -- I/O ----------------------------------------------------------------
    def _serve_path(self, path: Path, content_type: str):
        try:
            size = path.stat().st_size
        except OSError as exc:
            return _send_error(self, 404, f"not readable: {exc}")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(path, "rb") as fh:
            shutil.copyfileobj(fh, self.wfile)


def make_handler(bundle_dir, index=None) -> type:
    """Threading handler bound to a fixed *bundle_dir* / *index*."""
    bdir = Path(bundle_dir)
    idx = Path(index) if index else None

    class _BoundHandler(ReportBundleHandler):
        bundle_dir = bdir
        index = idx

    return _BoundHandler


class ReportBundleServer(ThreadingHTTPServer):
    """A ``ThreadingHTTPServer`` mounted on a report bundle directory."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, bundle_dir, index=None,
                 *, host: str = "127.0.0.1", port: int = 0):
        bdir = Path(bundle_dir)
        super().__init__(
            (host, port), make_handler(bdir, index if index else
                                       (bdir / "index.html" if
                                        (bdir / "index.html").is_file() else
                                        None)))

    @property
    def port(self) -> int:
        return int(self.server_address[1])


def serve_bundle(bundle_dir, port: int = 0, host: str = "127.0.0.1",
                 *, in_thread: bool = False):
    """Start a :class:`ReportBundleServer` hosting a report bundle.

    *bundle_dir* is a directory of self-contained single-file HTML reports
    (with or without an ``index.html``). Returns either the server (when
    ``in_thread=False``; caller serves) or a ``(server, thread)`` pair already
    running in the background.
    """
    bdir = Path(bundle_dir)
    if not bdir.is_dir():
        raise ValueError(f"not a bundle directory: {bdir}")
    index = bdir / "index.html"
    server = ReportBundleServer((host, port), bdir,
                                index if index.is_file() else None,
                                host=host, port=port)
    if not in_thread:
        return server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
