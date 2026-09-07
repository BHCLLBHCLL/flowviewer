"""R83 - AutomationSession publishes a report-family bundle (section 8.78).

R32's :class:`AutomationSession` shares only the streaming-CGNS surface via
``serve``; R82 added a standalone ``serve_bundle`` HTTP server for report
bundles with no automation-facing entry point. R83 raises ``serve_bundle`` onto
the session so one automation context can expose both the live windowed data
*and* the rendered report bundle a collaborator needs, with the bundle server
torn down on :meth:`AutomationSession.close`. Pure stdlib; no data file needed
for the bundle path (it does not require the stream handle to be open).
"""

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fv.automation import AutomationSession


def _write_report(dirpath: Path, name: str, body: str) -> Path:
    out = dirpath / name
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{name}</title></head><body>{body}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    _write_report(dirpath, "spectral_report.html", "<h1>spectral</h1>")
    _write_report(dirpath, "coherence_report.html", "<h1>coherence</h1>")
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


# ── serve_bundle on the session ─────────────────────────────────────────────


def test_session_serve_bundle_publishes(tmp_path):
    """serve_bundle returns a live port that serves the bundle (no stream)."""
    bundle = _make_bundle(tmp_path / "b")
    session = AutomationSession()
    try:
        port = session.serve_bundle(bundle)
        assert session._bundle_server is not None
        assert session._bundle_thread is not None
        status, _, data = _http(port, "/api/list")
        assert status == 200
        body = json.loads(data)
        assert body["ok"] is True
        assert body["title"] == "my analysis bundle"
        names = [item["name"] for item in body["reports"]]
        assert names == ["spectral_report.html", "coherence_report.html"]
        status, headers, data = _http(port, "/spectral_report.html")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("text/html")
        assert b"<h1>spectral</h1>" in data
    finally:
        session.close()


def test_session_serve_bundle_requires_no_stream(tmp_path):
    """The bundle path is independent of the streaming handle."""
    bundle = _make_bundle(tmp_path / "b")
    session = AutomationSession()
    try:
        port = session.serve_bundle(bundle)
        status, _, _ = _http(port, "/")
        assert status == 200
    finally:
        session.close()


def test_session_serve_bundle_rejects_non_dir(tmp_path):
    """A missing / non-directory bundle raises ValueError."""
    session = AutomationSession()
    try:
        with pytest.raises(ValueError):
            session.serve_bundle(str(tmp_path / "missing"))
        assert session._bundle_server is None
    finally:
        session.close()


def test_session_close_stops_bundle_server(tmp_path):
    """close() tears down the live server and clears its thread state."""
    bundle = _make_bundle(tmp_path / "b")
    session = AutomationSession()
    port = session.serve_bundle(bundle)
    assert session._bundle_server is not None
    assert session._bundle_thread is not None
    # the port was served (HTTP replied) before close, so the server was live
    status, _, _ = _http(port, "/api/list")
    assert status == 200
    session.close()
    assert session._bundle_server is None
    assert session._bundle_thread is None


def test_session_serve_requires_stream(tmp_path):
    """serve() still guards on an open stream (unchanged R32 contract)."""
    session = AutomationSession()
    try:
        with pytest.raises(RuntimeError):
            session.serve()
    finally:
        session.close()
