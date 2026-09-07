"""R88 tests: bundle query / sort / filter layer (section 8.83).

R86 gives the report family a metadata dashboard at ``/`` and an ``/api/meta``
JSON surface; R87 adds a bundle overview (``bundle_summary`` + ``/api/summary``).
R88 deepens the web presentation *in place*: ``query_reports`` filters a
:func:`report_meta` row list by a case-insensitive substring (``q``) and
re-orders it by ``sort``/``dir``, and both ``dashboard_html`` and the
``/api/meta`` route accept those query parameters so ``/?q=&sort=&dir=`` gives
a searchable, re-rankable dashboard. This suite exercises the pure helper, the
queryable dashboard, the query-string routes, and the 400 path on an unknown
sort key -- no third-party deps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fv.web.report_server import (
    dashboard_html,
    query_reports,
    report_meta,
    serve_bundle,
)

# ── fixtures / helpers ─────────────────────────────────────────────────────

M_TIME_ALPHA = 1000000000.0  # 2001-09-09 (UTC)
M_TIME_BETA = 1200000000.0  # 2008-01-10 (UTC)
M_TIME_GAMMA = 1500000000.0  # 2017-07-14 (UTC)


def _write_report(dirpath: Path, name: str, title: str, pad: int) -> Path:
    out = dirpath / name
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{title}</title></head><body>{title}"
        f"{'x' * pad}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path) -> Path:
    """Three-report bundle whose index order is NOT already sorted.

    The index lists reports gamma -> alpha -> beta, so the raw ``report_meta``
    order differs from any ``sort`` key. Padding makes sizes strictly
    increasing (alpha < beta < gamma); mtimes are alpha < beta < gamma too.
    """
    dirpath.mkdir(parents=True, exist_ok=True)
    alpha = _write_report(dirpath, "alpha_report.html", "Alpha analysis", 10)
    beta = _write_report(dirpath, "beta_report.html", "Beta analysis", 100)
    gamma = _write_report(dirpath, "gamma_report.html", "Gamma analysis", 200)
    os.utime(alpha, (M_TIME_ALPHA, M_TIME_ALPHA))
    os.utime(beta, (M_TIME_BETA, M_TIME_BETA))
    os.utime(gamma, (M_TIME_GAMMA, M_TIME_GAMMA))
    (dirpath / "index.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        "<title>queryable bundle</title></head><body>"
        "<h1>queryable bundle</h1><p>3 report(s) generated.</p>"
        "<ul><li><a href=\"gamma_report.html\">Gamma Field Map</a></li>"
        "<li><a href=\"alpha_report.html\">Alpha Field Map</a></li>"
        "<li><a href=\"beta_report.html\">Beta Field Map</a></li>"
        "</ul></body></html>\n", encoding="utf-8")
    return dirpath


def _names(rows) -> list[str]:
    return [row["name"] for row in rows]


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


# ── query_reports: filtering ───────────────────────────────────────────────


def test_query_reports_no_args_preserves_index_order(tmp_path):
    """Without q/sort the rows come back in their given (index) order."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    assert _names(rows) == [
        "gamma_report.html", "alpha_report.html", "beta_report.html"]
    assert _names(query_reports(rows)) == [
        "gamma_report.html", "alpha_report.html", "beta_report.html"]


def test_query_reports_filters_by_q_on_name_label_title(tmp_path):
    """q matches a case-insensitive substring on name, label or title."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    assert _names(query_reports(rows, q="beta")) == ["beta_report.html"]
    assert _names(query_reports(rows, q="BETA")) == ["beta_report.html"]
    # "field" appears only in the labels, "analysis" only in the titles
    assert _names(query_reports(rows, q="field")) == [
        "gamma_report.html", "alpha_report.html", "beta_report.html"]
    assert _names(query_reports(rows, q="analysis")) == [
        "gamma_report.html", "alpha_report.html", "beta_report.html"]
    assert query_reports(rows, q="no-such-report") == []


def test_query_reports_empty_q_is_noop(tmp_path):
    """An empty/whitespace q returns everything unchanged."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    assert _names(query_reports(rows, q="")) == _names(rows)
    assert _names(query_reports(rows, q=None)) == _names(rows)


# ── query_reports: sorting ─────────────────────────────────────────────────


def test_query_reports_sorts_by_text_key(tmp_path):
    """sort=name/label/title orders case-insensitively; dir='desc' reverses."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    expected = ["alpha_report.html", "beta_report.html", "gamma_report.html"]
    assert _names(query_reports(rows, sort="name")) == expected
    assert _names(query_reports(rows, sort="name", dir="desc")) == list(
        reversed(expected))
    assert _names(query_reports(rows, sort="label")) == expected
    assert _names(query_reports(rows, sort="title")) == expected


def test_query_reports_sorts_by_numeric_key(tmp_path):
    """sort=size/mtime orders numerically; dir='desc' reverses."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    ascending = ["alpha_report.html", "beta_report.html", "gamma_report.html"]
    assert _names(query_reports(rows, sort="size")) == ascending
    assert _names(query_reports(rows, sort="size", dir="desc")) == list(
        reversed(ascending))
    assert _names(query_reports(rows, sort="mtime")) == ascending
    sizes = {r["name"]: r["size_bytes"] for r in rows}
    assert sizes["alpha_report.html"] < sizes["beta_report.html"] \
        < sizes["gamma_report.html"]


def test_query_reports_unknown_sort_key_raises(tmp_path):
    """An unknown sort key is rejected loudly, not silently ignored."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    with pytest.raises(ValueError):
        query_reports(rows, sort="bogus")


# ── dashboard_html: queryable ──────────────────────────────────────────────


def test_dashboard_html_filters_with_q(tmp_path):
    """dashboard_html(q=...) renders only the matching reports."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle, q="beta")
    assert "Beta Field Map" in page
    assert "Alpha Field Map" not in page
    assert "Gamma Field Map" not in page
    assert "1 report(s)" in page  # summary tracks the visible subset


def test_dashboard_html_sorts_and_orders(tmp_path):
    """dashboard_html(sort=name, dir=asc) re-orders the reported anchors."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle, sort="name", dir="asc")
    alpha = page.index("Alpha Field Map")
    beta = page.index("Beta Field Map")
    gamma = page.index("Gamma Field Map")
    assert alpha < beta < gamma


def test_dashboard_html_title_param_drives_heading(tmp_path):
    """An explicit title still overrides the bundle <title> under querying."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle, "My Queryable Bundle", sort="name")
    assert "My Queryable Bundle" in page
    assert page.index("Alpha Field Map") < page.index("Gamma Field Map")


# ── HTTP service ───────────────────────────────────────────────────────────


def test_serve_root_dashboard_accepts_query_params(tmp_path):
    """/?q=&sort=&dir= filters and re-orders the served dashboard."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/?q=beta")
        assert status == 200
        text = data.decode("utf-8")
        assert "Beta Field Map" in text and "Alpha Field Map" not in text
        assert "1 report(s)" in text

        status, _, data = _http(
            "GET", server.port, "/?sort=name&dir=asc")
        text = data.decode("utf-8")
        assert text.index("Alpha Field Map") < text.index("Beta Field Map") \
            < text.index("Gamma Field Map")

        # no params -> full, index-ordered dashboard (backward compatible)
        status, _, data = _http("GET", server.port, "/")
        text = data.decode("utf-8")
        assert text.index("Gamma Field Map") < text.index("Alpha Field Map") \
            < text.index("Beta Field Map")
    finally:
        _shutdown(server, thread)


def test_serve_meta_api_accepts_query_params(tmp_path):
    """/api/meta?q= filters, ?sort= re-orders and summary tracks the subset."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, _, data = _http("GET", server.port, "/api/meta?q=beta")
        assert status == 200
        body = json.loads(data)
        assert [r["name"] for r in body["reports"]] == ["beta_report.html"]
        assert body["summary"]["report_count"] == 1

        status, _, data = _http(
            "GET", server.port, "/api/meta?sort=name&dir=asc")
        body = json.loads(data)
        assert [r["name"] for r in body["reports"]] == [
            "alpha_report.html", "beta_report.html", "gamma_report.html"]

        status, _, data = _http("GET", server.port, "/api/meta")
        body = json.loads(data)
        assert [r["name"] for r in body["reports"]] == [
            "gamma_report.html", "alpha_report.html", "beta_report.html"]
        assert body["summary"]["report_count"] == 3
    finally:
        _shutdown(server, thread)


def test_serve_unknown_sort_key_returns_400(tmp_path):
    """An invalid sort key yields a 400 JSON error, on / and /api/meta."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        for path in ("/?sort=bogus", "/api/meta?sort=bogus"):
            status, _, data = _http("GET", server.port, path)
            assert status == 400
            body = json.loads(data)
            assert body["ok"] is False
            assert "bogus" in body["error"]
    finally:
        _shutdown(server, thread)
