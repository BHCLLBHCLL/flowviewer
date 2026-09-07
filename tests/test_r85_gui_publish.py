"""R85 tests: GUI publishes the current analysis report bundle over HTTP.

R82 gives the report family a headless HTTP server (``fv.web.report_server``),
R83 raises it onto ``AutomationSession`` and R84 adds a CLI ``--serve`` flag, but
the GUI itself (``fv.gui.main``) could not share the bundle it just generated.
R85 adds ``analysis.serve_report_bundle`` (pure logic in ``fv.gui.analysis``)
that starts the R82 server on a background daemon thread and returns
``(info, server, thread)`` so the Analysis menu's "Publish Bundle over HTTP…"
action can show the URL and a "Stop Publishing…" action can shut it down.

These tests exercise only the pure ``serve_report_bundle`` helper against a
synthetic bundle; the PyQt menu wiring is out of scope (headless). See
``test_r72_report_bundle`` for the bundle-building convention.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fv.gui import analysis


def _write_html(dirpath: Path, name: str, title: str) -> Path:
    out = dirpath / name
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>{title}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    _write_html(dirpath, "spectral_report.html", "Spectral analysis")
    _write_html(dirpath, "coherence_report.html", "Coherence analysis")
    (dirpath / "index.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        "<title>my analysis bundle</title></head><body>"
        "<h1>my analysis bundle</h1><p>2 report(s) generated.</p>"
        "<ul><li><a href=\"spectral_report.html\">Spectral analysis</a></li>"
        "<li><a href=\"coherence_report.html\">Coherence analysis</a></li>"
        "</ul></body></html>\n", encoding="utf-8")
    return dirpath


def _http(port, path):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def _stop(server) -> None:
    server.shutdown()
    server.server_close()


def test_serve_report_bundle_serves_bundle(tmp_path):
    """serve_report_bundle starts a real HTTP server on the bundle dir."""
    bundle = _make_bundle(tmp_path / "b")
    info, server, thread = analysis.serve_report_bundle(str(bundle))
    try:
        assert thread is not None and thread.is_alive()
        assert info["bundle"] == str(bundle.resolve())
        assert info["host"] == "127.0.0.1"
        assert info["port"] == server.port
        assert info["url"] == f"http://127.0.0.1:{server.port}/"
        status, _, data = _http(server.port, "/api/list")
        assert status == 200
        body = json.loads(data)
        assert body["title"] == "my analysis bundle"
        assert len(body["reports"]) == 2
        status, headers, _ = _http(server.port, "/spectral_report.html")
        assert status == 200
        assert headers["Content-Type"].startswith("text/html")
    finally:
        _stop(server)


def test_serve_report_bundle_honours_host_and_port(tmp_path):
    """host/port are reflected in the returned info dict."""
    bundle = _make_bundle(tmp_path / "b")
    info, server, thread = analysis.serve_report_bundle(
        str(bundle), port=0, host="0.0.0.0")
    try:
        assert info["host"] == "0.0.0.0"
        assert info["port"] == server.port
        assert info["url"].startswith(f"http://0.0.0.0:{server.port}/")
    finally:
        _stop(server)


def test_serve_report_bundle_rejects_non_dir(tmp_path):
    """A missing / non-directory bundle_dir raises ValueError."""
    with pytest.raises(ValueError):
        analysis.serve_report_bundle(str(tmp_path / "missing"))


def test_serve_report_bundle_stops_cleanly(tmp_path):
    """shutdown+server_close recycles the server and its thread."""
    bundle = _make_bundle(tmp_path / "b")
    info, server, thread = analysis.serve_report_bundle(str(bundle))
    assert _http(server.port, "/api/list")[0] == 200
    _stop(server)
    thread.join(timeout=5)
    assert not thread.is_alive()
    with pytest.raises(urllib.error.URLError):
        _http(server.port, "/api/list")
