"""R86 tests: report-bundle metadata dashboard + /api/meta (section 8.81).

R82 gives the report family a headless HTTP server; ``/`` serves the bundle's
static ``index.html``. R86 deepens the web presentation: ``/`` becomes a live
metadata dashboard (each report's own ``<title>`` plus os.stat size / mtime)
and ``/api/meta`` exposes that metadata as JSON -- no third-party deps. This
suite exercises the pure helpers (``report_meta`` / ``dashboard_html``) and the
``/``, ``/index.html`` and ``/api/meta`` routes against a synthetic bundle.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from fv.web.report_server import (
    bundle_listings,
    dashboard_html,
    report_meta,
    serve_bundle,
)

# ── fixtures / helpers ─────────────────────────────────────────────────────


def _write_report(dirpath: Path, name: str, title: str) -> Path:
    out = dirpath / name
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>{title}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path, *, with_index: bool = True) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    _write_report(dirpath, "spectral_report.html", "Spectral analysis")
    _write_report(dirpath, "coherence_report.html", "Coherence analysis")
    if with_index:
        (dirpath / "index.html").write_text(
            "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            "<title>my analysis bundle</title></head><body>"
            "<h1>my analysis bundle</h1><p>2 report(s) generated.</p>"
            "<ul><li><a href=\"spectral_report.html\">Spectral Field Map</a></li>"
            "<li><a href=\"coherence_report.html\">Coherence Field Map</a></li>"
            "</ul></body></html>\n", encoding="utf-8")
    return dirpath


def _http(method, port, path, body=None, headers=None):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:  # non-2xx is still a response
        return exc.code, exc.headers, exc.read()


def _shutdown(server, thread):
    try:
        server.shutdown()
    except Exception:  # pragma: no cover
        pass
    try:
        server.server_close()
    except Exception:  # pragma: no cover
        pass
    if thread and thread.is_alive():
        thread.join(timeout=2.0)


# ── report_meta ────────────────────────────────────────────────────────────


def test_report_meta_reads_index_order_and_metadata(tmp_path):
    """report_meta follows the index order and augments title/size/mtime."""
    bundle = _make_bundle(tmp_path / "b")
    rows = report_meta(bundle)
    assert [r["name"] for r in rows] == [
        "spectral_report.html", "coherence_report.html"]
    assert [r["label"] for r in rows] == [
        "Spectral Field Map", "Coherence Field Map"]
    assert [r["title"] for r in rows] == [
        "Spectral analysis", "Coherence analysis"]
    assert all(r["size_bytes"] > 0 for r in rows)
    assert all(r["mtime"] > 0 for r in rows)


def test_report_meta_falls_back_to_scan(tmp_path):
    """Without index.html, report_meta falls back to a sorted *.html scan."""
    bundle = _make_bundle(tmp_path / "b", with_index=False)
    rows = report_meta(bundle)
    assert [r["name"] for r in rows] == [
        "coherence_report.html", "spectral_report.html"]
    assert [r["label"] for r in rows] == ["coherence_report", "spectral_report"]
    assert [r["title"] for r in rows] == [
        "Coherence analysis", "Spectral analysis"]


def test_report_meta_missing_report_degrades(tmp_path):
    """An index entry with no backing file degrades to zero metadata."""
    bundle = _make_bundle(tmp_path / "b")
    (bundle / "index.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        "<title>my analysis bundle</title></head><body><h1>x</h1>"
        "<ul><li><a href=\"spectral_report.html\">Spectral Field Map</a></li>"
        "<li><a href=\"missing.html\">Missing report</a></li></ul>"
        "</body></html>\n", encoding="utf-8")
    rows = report_meta(bundle)
    assert len(rows) == 2
    assert rows[0]["size_bytes"] > 0 and rows[0]["mtime"] > 0
    assert rows[1]["name"] == "missing.html"
    assert rows[1]["title"] == ""
    assert rows[1]["size_bytes"] == 0
    assert rows[1]["mtime"] == 0.0


# ── dashboard_html ─────────────────────────────────────────────────────────


def test_dashboard_html_includes_metadata(tmp_path):
    """dashboard_html lists every report with label + title + size + mtime."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle)
    assert "Spectral Field Map" in page and "Coherence Field Map" in page
    assert "Spectral analysis" in page and "Coherence analysis" in page
    assert '<li class="meta">' in page
    assert "B" in page  # a human-readable size caption is present


def test_dashboard_html_stays_bundle_listings_parseable(tmp_path):
    """The dashboard keeps `<li><a>` anchors so bundle_listings reads it."""
    bundle = _make_bundle(tmp_path / "b")
    dest = tmp_path / "db"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "index.html").write_text(dashboard_html(bundle), encoding="utf-8")
    listings = bundle_listings(dest)
    assert [item["name"] for item in listings] == [
        "spectral_report.html", "coherence_report.html"]
    assert [item["label"] for item in listings] == [
        "Spectral Field Map", "Coherence Field Map"]


# ── HTTP service ───────────────────────────────────────────────────────────


def test_serve_root_dashboard_and_index_file(tmp_path):
    """/ serves the metadata dashboard; /index.html serves the raw index."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, headers, data = _http("GET", server.port, "/")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("text/html")
        text = data.decode("utf-8")
        assert "Spectral Field Map" in text and "Coherence Field Map" in text
        assert '<li class="meta">' in text
        status, _, data = _http("GET", server.port, "/index.html")
        assert status == 200
        raw = data.decode("utf-8")
        assert "Spectral Field Map" in raw and "Coherence Field Map" in raw
        assert '<li class="meta">' not in raw  # untouched bundle index file
    finally:
        _shutdown(server, thread)


def test_serve_bundle_meta_api(tmp_path):
    """/api/meta returns JSON per-report metadata."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, headers, data = _http("GET", server.port, "/api/meta")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("application/json")
        body = json.loads(data)
        assert body["ok"] is True
        assert body["title"] == "my analysis bundle"
        reports = body["reports"]
        assert [r["name"] for r in reports] == [
            "spectral_report.html", "coherence_report.html"]
        assert reports[0]["label"] == "Spectral Field Map"
        assert reports[0]["title"] == "Spectral analysis"
        assert reports[0]["size_bytes"] > 0
        assert reports[0]["mtime"] > 0
    finally:
        _shutdown(server, thread)


def test_serve_meta_api_no_index_scans(tmp_path):
    """/api/meta on a bundle without index.html still returns scan metadata."""
    bundle = _make_bundle(tmp_path / "b", with_index=False)
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/api/meta")
        assert status == 200
        reports = json.loads(data)["reports"]
        assert [r["name"] for r in reports] == [
            "coherence_report.html", "spectral_report.html"]
    finally:
        _shutdown(server, thread)
