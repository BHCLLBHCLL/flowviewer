"""R89 tests: bundle pagination / windowing layer (section 8.84).

R86 gave the report family a metadata dashboard (``/``) and an ``/api/meta``
JSON surface; R87 added a bundle overview (``bundle_summary`` + ``/api/summary``);
R88 made ``/`` and ``/api/meta`` queryable / re-rankable with ``q``/``sort``/``dir``.
R89 deepens the web presentation for large bundles: ``window_reports`` slices a
``report_meta`` row list by ``limit``/``offset``, ``dashboard_html`` renders a
paginated slice with previous / next pager links (preserving ``q``/``sort``/``dir``)
and ``/api/meta`` returns ``total``/``offset``/``limit`` alongside the page. This
suite exercises the pure windowing helper, the paginated dashboard (and its
bundle_listings-parsability), the ``/?limit=&offset=`` and ``/api/meta?limit=&offset=``
routes, the invalid-parameter 400 paths, and backward compatibility with R86-R88
-- no third-party deps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from fv.web.report_server import (
    bundle_listings,
    dashboard_html,
    query_reports,
    report_meta,
    serve_bundle,
    window_reports,
)

# ── fixtures / helpers ─────────────────────────────────────────────────────

M_TIME = {
    "alpha": 1000000000.0,  # 2001-09-09
    "beta": 1100000000.0,  # 2004-11-09
    "gamma": 1200000000.0,  # 2008-01-10
    "delta": 1300000000.0,  # 2011-03-12
    "epsilon": 1400000000.0,  # 2014-05-13
}
INDEX_ORDER = ["gamma", "epsilon", "alpha", "delta", "beta"]
PAD = {"alpha": 10, "beta": 50, "gamma": 100, "delta": 200, "epsilon": 400}
TASK = "Field Map"
CAP = "analysis"


def _write_report(dirpath: Path, stem: str) -> Path:
    out = dirpath / f"{stem}_report.html"
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{stem.title()} {CAP}</title></head><body>{stem.title()} {CAP}"
        f"{'x' * PAD[stem]}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path) -> Path:
    """Five-report bundle whose index order is NOT alphabetically sorted.

    Index lists gamma -> epsilon -> alpha -> delta -> beta, so the raw
    ``report_meta`` order is unsorted. Padding makes sizes strictly increasing
    (alpha < beta < gamma < delta < epsilon) and mtimes are too, so sort
    interactions are meaningful.
    """
    dirpath.mkdir(parents=True, exist_ok=True)
    paths = {stem: _write_report(dirpath, stem) for stem in M_TIME}
    for stem, path in paths.items():
        mt = M_TIME[stem]
        os.utime(path, (mt, mt))
    lis = "".join(
        f'<li><a href="{stem}_report.html">{stem.title()} {TASK}</a></li>'
        for stem in INDEX_ORDER)
    (dirpath / "index.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        "<title>paginated bundle</title></head><body>"
        "<h1>paginated bundle</h1>"
        f"<p>{len(INDEX_ORDER)} report(s) generated.</p>"
        f"<ul>{lis}</ul></body></html>\n", encoding="utf-8")
    return dirpath


def _names(rows) -> list[str]:
    return [row["name"] for row in rows]


def _http(method, port, path):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # non-2xx is still a response
        return exc.code, exc.read()


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


# ── window_reports: pure windowing ─────────────────────────────────────────


def test_window_reports_no_limit_preserves_all(tmp_path):
    """limit=None returns everything unchanged (R88 backward compatible)."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    assert _names(window_reports(rows)) == [
        "gamma_report.html", "epsilon_report.html", "alpha_report.html",
        "delta_report.html", "beta_report.html"]
    assert _names(window_reports(rows, limit=None)) == _names(rows)


def test_window_reports_slices_by_limit_offset(tmp_path):
    """limit + offset window the (ordered) row list page by page."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    assert _names(window_reports(rows, limit=2)) == [
        "gamma_report.html", "epsilon_report.html"]
    assert _names(window_reports(rows, limit=2, offset=2)) == [
        "alpha_report.html", "delta_report.html"]
    assert _names(window_reports(rows, limit=2, offset=4)) == [
        "beta_report.html"]
    assert _names(window_reports(rows, limit=10)) == _names(rows)
    assert _names(window_reports(rows, limit=2, offset=10)) == []
    assert window_reports(rows, limit=0) == []


def test_window_reports_does_not_mutate_input(tmp_path):
    """Windowing returns new lists and leaves the source untouched."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    before = [dict(r) for r in rows]
    window_reports(rows, limit=2)
    window_reports(rows, limit=None)
    assert rows == before


def test_window_reports_rejects_negative_values(tmp_path):
    """Negative limit / offset are rejected loudly, not silently clamped."""
    rows = report_meta(_make_bundle(tmp_path / "b"))
    with pytest.raises(ValueError):
        window_reports(rows, limit=-1)
    with pytest.raises(ValueError):
        window_reports(rows, offset=-1)


def test_window_reports_composes_after_query(tmp_path):
    """Window applies on top of the R88 filter/sort (q then limit/offset)."""
    bundle = _make_bundle(tmp_path / "b")
    rows = report_meta(bundle)
    matched = query_reports(rows, q="field", sort="name")
    assert _names(matched) == [
        "alpha_report.html", "beta_report.html", "delta_report.html",
        "epsilon_report.html", "gamma_report.html"]
    assert _names(window_reports(matched, limit=2, offset=1)) == [
        "beta_report.html", "delta_report.html"]


# ── dashboard_html: pagination ─────────────────────────────────────────────


def test_dashboard_html_pagination_renders_ranges_and_links(tmp_path):
    """limit renders a pager; summary always reflects the whole match."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle, limit=2)
    assert "5 report(s)" in page  # summary reflects the full match
    assert "showing 1–2 of 5" in page
    assert 'class="pager-prev"' not in page  # first page has no previous
    assert 'class="pager-next"' in page
    assert "Alpha Field Map" not in page  # only the first slice is rendered
    assert "Gamma Field Map" in page
    assert "Epsilon Field Map" in page

    page2 = dashboard_html(bundle, limit=2, offset=2)
    assert "showing 3–4 of 5" in page2
    assert 'class="pager-prev"' in page2
    assert 'class="pager-next"' in page2
    assert "Alpha Field Map" in page2
    assert "Delta Field Map" in page2

    page3 = dashboard_html(bundle, limit=2, offset=4)
    assert "showing 5–5 of 5" in page3
    assert 'class="pager-prev"' in page3
    assert 'class="pager-next"' not in page3
    assert "Beta Field Map" in page3


def test_dashboard_html_pager_href_preserves_sort_and_dir(tmp_path):
    """Pager links keep q/sort/dir and advance the offset by the limit."""
    page = dashboard_html(_make_bundle(tmp_path / "b"), limit=2,
                          q="field", sort="size", dir="desc")
    next_href = 'href="?limit=2&offset=2&q=field&sort=size&dir=desc"'
    assert next_href in page


def test_dashboard_html_no_limit_has_no_pagination(tmp_path):
    """Without limit the dashboard stays the R86-R88 full page (no pager)."""
    page = dashboard_html(_make_bundle(tmp_path / "b"))
    assert 'class="pagination"' not in page
    assert "showing" not in page
    assert "5 report(s)" in page


def test_dashboard_html_paginated_page_parses_via_bundle_listings(tmp_path):
    """Pagination <a> links don't get picked up as report anchors."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle, limit=2)
    # write the paginated page as a bundle index and re-parse it
    outdir = tmp_path / "served"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(page, encoding="utf-8")
    listings = bundle_listings(outdir)
    assert _names(listings) == ["gamma_report.html", "epsilon_report.html"]
    assert all("pager" not in item["name"] for item in listings)


def test_dashboard_html_rejects_negative_limit(tmp_path):
    """A negative limit is propagated as a ValueError (route maps to 400)."""
    with pytest.raises(ValueError):
        dashboard_html(_make_bundle(tmp_path / "b"), limit=-1)


# ── HTTP routes ────────────────────────────────────────────────────────────


def test_serve_meta_api_paginates(tmp_path):
    """/api/meta?limit=&offset= returns a page plus total / offset / limit."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, data = _http("GET", server.port, "/api/meta?limit=2")
        body = json.loads(data)
        assert [r["name"] for r in body["reports"]] == [
            "gamma_report.html", "epsilon_report.html"]
        assert body["total"] == 5 and body["offset"] == 0 and body["limit"] == 2
        assert body["summary"]["report_count"] == 5  # full match

        status, data = _http("GET", server.port, "/api/meta?limit=2&offset=2")
        body = json.loads(data)
        assert [r["name"] for r in body["reports"]] == [
            "alpha_report.html", "delta_report.html"]
        assert body["total"] == 5 and body["offset"] == 2

        status, data = _http("GET", server.port, "/api/meta?limit=2&offset=4")
        body = json.loads(data)
        assert [r["name"] for r in body["reports"]] == ["beta_report.html"]

        # no params -> full, index-ordered, backward compatible (limit None)
        status, data = _http("GET", server.port, "/api/meta")
        body = json.loads(data)
        assert body["total"] == 5 and body["limit"] is None and body["offset"] == 0
        assert len(body["reports"]) == 5
    finally:
        _shutdown(server, thread)


def test_serve_dashboard_paginates(tmp_path):
    """/?limit=&offset= renders a paginated slice with previous / next."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, data = _http("GET", server.port, "/?limit=2")
        text = data.decode("utf-8")
        assert "showing 1–2 of 5" in text
        assert "Gamma Field Map" in text and "Epsilon Field Map" in text
        assert "Alpha Field Map" not in text
        assert "&offset=2" in text  # next link advances past the first page

        status, data = _http("GET", server.port, "/?limit=2&offset=2")
        text = data.decode("utf-8")
        assert "showing 3–4 of 5" in text
        assert "Alpha Field Map" in text and "Delta Field Map" in text
    finally:
        _shutdown(server, thread)


def test_serve_invalid_pagination_returns_400(tmp_path):
    """Bad limit/offset (non-int, negative) yield 400 on / and /api/meta."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        for path in ("/?limit=abc", "/api/meta?limit=abc",
                     "/?limit=-1", "/api/meta?offset=-3"):
            status, data = _http("GET", server.port, path)
            assert status == 400
            body = json.loads(data)
            assert body["ok"] is False
            assert "error" in body
    finally:
        _shutdown(server, thread)
