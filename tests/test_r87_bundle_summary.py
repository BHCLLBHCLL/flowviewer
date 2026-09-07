"""R87 tests: bundle overview summary + /api/summary (section 8.82).

R86 gives the report family a metadata dashboard at ``/`` and an ``/api/meta``
JSON surface. R87 adds a bundle *overview*: ``bundle_summary`` aggregates the
per-report metadata into a report count / total size / generated span, the
dashboard renders it as a ``<p class="summary">`` block, and ``/api/meta`` (plus
the new ``/api/summary`` endpoint) exposes it machine-readably. This suite
exercises the pure helper (``bundle_summary``), the dashboard block, the new
``/api/summary`` route, the extended ``/api/meta`` payload, and re-checks the
R86 anchors so a served bundle stays parseable. No third-party deps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from fv.web.report_server import (
    bundle_listings,
    bundle_summary,
    dashboard_html,
    report_meta,
    serve_bundle,
)

# ── fixtures / helpers ─────────────────────────────────────────────────────

M_TIME_OLD = 1000000000.0  # 2001-09-09 (UTC)
M_TIME_NEW = 1500000000.0  # 2017-07-14 (UTC)


def _write_report(dirpath: Path, name: str, title: str) -> Path:
    out = dirpath / name
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>{title}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path, *, with_index: bool = True) -> Path:
    """Two-report bundle with deterministic, distinct report mtimes."""
    dirpath.mkdir(parents=True, exist_ok=True)
    old = _write_report(dirpath, "spectral_report.html", "Spectral analysis")
    new = _write_report(dirpath, "coherence_report.html", "Coherence analysis")
    os.utime(old, (M_TIME_OLD, M_TIME_OLD))
    os.utime(new, (M_TIME_NEW, M_TIME_NEW))
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


def _fmt_local(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


# ── bundle_summary ─────────────────────────────────────────────────────────


def test_bundle_summary_aggregates_count_size_and_span(tmp_path):
    """bundle_summary counts reports, sums bytes and spans old->new mtimes."""
    bundle = _make_bundle(tmp_path / "b")
    summary = bundle_summary(bundle)
    assert summary["report_count"] == 2
    total = sum(row["size_bytes"] for row in report_meta(bundle))
    assert summary["total_bytes"] == total
    assert summary["total_bytes"] > 0
    assert summary["oldest"] == _fmt_local(M_TIME_OLD)
    assert summary["newest"] == _fmt_local(M_TIME_NEW)
    assert summary["oldest"] != summary["newest"]


def test_bundle_summary_empty_bundle_degrades_cleanly(tmp_path):
    """An empty bundle yields a clean zero overview instead of raising."""
    bundle = tmp_path / "b"
    bundle.mkdir(parents=True, exist_ok=True)
    summary = bundle_summary(bundle)
    assert summary == {
        "report_count": 0,
        "total_bytes": 0,
        "oldest": "",
        "newest": "",
    }


def test_bundle_summary_missing_report_degrades(tmp_path):
    """A stale index entry contributes 0 bytes and no mtime to the summary."""
    bundle = _make_bundle(tmp_path / "b")
    (bundle / "index.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        "<title>my analysis bundle</title></head><body><h1>x</h1>"
        "<ul><li><a href=\"spectral_report.html\">Spectral Field Map</a></li>"
        "<li><a href=\"missing.html\">Missing report</a></li></ul>"
        "</body></html>\n", encoding="utf-8")
    summary = bundle_summary(bundle)
    assert summary["report_count"] == 2
    assert summary["total_bytes"] == (bundle / "spectral_report.html").stat().st_size
    # only the valid report carries an mtime, so old == new == its timestamp
    assert summary["oldest"] == _fmt_local(M_TIME_OLD)
    assert summary["newest"] == _fmt_local(M_TIME_OLD)


# ── dashboard_html ─────────────────────────────────────────────────────────


def test_dashboard_html_renders_summary_block(tmp_path):
    """dashboard_html shows a `<p class="summary">` block above the list."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle)
    assert '<p class="summary">' in page
    assert "2 report(s)" in page
    assert "total" in page
    assert _fmt_local(M_TIME_OLD) in page
    assert _fmt_local(M_TIME_NEW) in page
    # R86 captions still present -- the summary block is additive.
    assert '<li class="meta">' in page


def test_dashboard_html_stays_bundle_listings_parseable(tmp_path):
    """The summary block does not break the `<li><a>` anchor parsing."""
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


def test_serve_bundle_summary_api(tmp_path):
    """/api/summary returns the bundle overview as JSON."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, headers, data = _http("GET", server.port, "/api/summary")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("application/json")
        body = json.loads(data)
        assert body["ok"] is True
        assert body["title"] == "my analysis bundle"
        summary = body["summary"]
        assert summary["report_count"] == 2
        assert summary["total_bytes"] > 0
        assert summary["oldest"] == _fmt_local(M_TIME_OLD)
        assert summary["newest"] == _fmt_local(M_TIME_NEW)
    finally:
        _shutdown(server, thread)


def test_serve_meta_api_includes_summary(tmp_path):
    """/api/meta now carries an aggregate summary alongside the reports."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/api/meta")
        assert status == 200
        body = json.loads(data)
        summary = body["summary"]
        assert summary["report_count"] == len(body["reports"]) == 2
        assert summary["total_bytes"] > 0
    finally:
        _shutdown(server, thread)


def test_serve_bundle_summary_api_empty(tmp_path):
    """/api/summary on an empty bundle reports zeros without error."""
    bundle = tmp_path / "b"
    bundle.mkdir(parents=True, exist_ok=True)
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/api/summary")
        assert status == 200
        body = json.loads(data)
        assert body["ok"] is True
        assert body["summary"] == {
            "report_count": 0,
            "total_bytes": 0,
            "oldest": "",
            "newest": "",
        }
    finally:
        _shutdown(server, thread)
