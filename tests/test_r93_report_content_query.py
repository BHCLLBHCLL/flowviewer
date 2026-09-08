"""R93: content-aware search + machine-readable report content endpoint.

R88 made ``/`` and ``/api/meta`` queryable via ``q``, but ``q`` only matched a
report's ``name``/``label``/``title`` -- a keyword found *inside* a report body
got no matches, and there was no machine way to fetch a single report's content
over HTTP. R93 deepens ``query_reports`` with an opt-in ``content=True`` mode
(plus ``bundle_dir`` to read bodies) so ``q`` also matches report body text,
threads a ``content=1`` flag through the dashboard, its controls form and the
pager / detail navigation (so a content-mode query survives paging and prev /
next), and adds ``/api/report/content?name=`` -- the JSON counterpart to
``/api/report`` that returns a report's raw HTML text. This suite exercises the
pure content-mode query, the content checkbox in the controls form, the
dashboard / detail pages that carry a content search, and the live
``/api/report/content`` and ``content=1`` / /api/meta routes -- no third-party
deps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    _controls_html,
    _pager_href,
    dashboard_html,
    query_reports,
    report_content,
    report_detail_html,
    report_meta,
    serve_bundle,
)

INDEX_ORDER = ("gamma_report.html", "epsilon_report.html", "alpha_report.html",
               "delta_report.html", "beta_report.html")

# A body-only keyword per report -- never in the name / label / title.
BODY_KEYWORD = {
    "gamma_report.html": "volcanic",
    "epsilon_report.html": "quartz",
    "alpha_report.html": "zebra",
    "delta_report.html": "marble",
    "beta_report.html": "nebula",
}


def _write_report(root, name: str, title: str, mtime: float, pad: int):
    path = root / name
    keyword = BODY_KEYWORD[name]
    body = (f"<!doctype html><html><head><title>{title}</title></head>"
            f"<body>report {keyword}</body></html>")
    path.write_text(body, encoding="utf-8")
    with open(path, "ab") as fh:
        fh.write(b"x" * pad)
    os.utime(path, (mtime, mtime))
    return path


def _label(name: str) -> str:
    return name.removesuffix(".html").replace("_", " ").title()


def _make_bundle(tmp_path):
    b = tmp_path / "b"
    b.mkdir(exist_ok=True)
    for i, name in enumerate(INDEX_ORDER):
        _write_report(b, name, f"{_label(name)} Field Map",
                      1_700_000_000 + i, 100 * i)
    items = "".join(
        f'<li><a href="{n}">{_label(n)}</a></li>' for n in INDEX_ORDER)
    (b / "index.html").write_text(
        f"<!doctype html><html><head><title>test bundle</title></head>"
        f"<body><ul>{items}</ul></body></html>", encoding="utf-8")
    return b


@pytest.fixture
def bundle(tmp_path):
    return _make_bundle(tmp_path)


@pytest.fixture
def server(bundle):
    srv, thread = serve_bundle(bundle, port=0, in_thread=True)
    yield srv
    srv.shutdown()
    thread.join()


def _fetch(server, path: str):
    url = f"http://127.0.0.1:{server.port}{path}"
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


# ── query_reports: content mode (pure) ─────────────────────────────────────


def test_query_reports_content_matches_body_keyword(bundle):
    rows = report_meta(bundle)
    matched = query_reports(rows, q="zebra", content=True, bundle_dir=bundle)
    assert [row["name"] for row in matched] == ["alpha_report.html"]


def test_query_reports_content_off_ignores_body(bundle):
    rows = report_meta(bundle)
    matched = query_reports(rows, q="zebra")
    assert matched == []


def test_query_reports_content_still_matches_metadata(bundle):
    """Content mode broadens, not replaces, the metadata match."""
    rows = report_meta(bundle)
    matched = query_reports(rows, q="epsilon", content=True, bundle_dir=bundle)
    assert [row["name"] for row in matched] == ["epsilon_report.html"]


def test_query_reports_content_without_bundle_dir_skips_body(bundle):
    rows = report_meta(bundle)
    matched = query_reports(rows, q="zebra", content=True, bundle_dir=None)
    assert matched == []


def test_query_reports_content_matches_two_body_keywords(bundle):
    """Content mode matches any report whose body carries the keyword."""
    rows = report_meta(bundle)
    for keyword in ("zebra", "nebula"):
        matched = query_reports(rows, q=keyword, content=True,
                                bundle_dir=bundle)
        assert len(matched) == 1
        assert keyword in report_content(bundle, matched[0]["name"])


# ── _pager_href / _controls_html: content flag surface ─────────────────────


def test_pager_href_includes_content_when_set():
    href = _pager_href(2, 10, "zebra", "name", "asc", content=True)
    assert "content=1" in href


def test_pager_href_omits_content_when_unset():
    href = _pager_href(2, 10, "zebra", "name", "asc")
    assert "content=1" not in href


def test_controls_form_has_content_checkbox_default_unchecked():
    form = _controls_html(None, None, "asc", None)
    assert 'name="content"' in form
    assert 'value="1"' in form
    assert "search report content" in form
    assert "checked" not in form


def test_controls_form_content_checkbox_checked_when_active():
    form = _controls_html("zebra", None, "asc", None, content=True)
    assert 'name="content" value="1" checked' in form


# ── dashboard_html: content-aware page ─────────────────────────────────────


def test_dashboard_html_content_search_filters_by_body(bundle):
    page = dashboard_html(bundle, q="zebra", content=True)
    assert 'class="content-toggle"' in page
    assert 'name="content" value="1" checked' in page
    assert "Alpha Report" in page
    assert "Gamma Report" not in page


def test_dashboard_html_content_pager_preserves_content_flag(bundle):
    page = dashboard_html(bundle, q="field", sort="name", limit=2,
                          content=True)
    assert "content=1" in page


def test_dashboard_html_non_content_search_does_not_check_box(bundle):
    page = dashboard_html(bundle, q="field")
    assert 'name="content" value="1" checked' not in page


# ── report_detail_html: nav preserves content ──────────────────────────────


def test_detail_html_backlink_preserves_content(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q="zebra",
                              content=True)
    assert body is not None
    assert 'href="/?q=zebra&amp;content=1"' in body


def test_detail_html_next_preserves_content(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q="field",
                              sort="name", dir="asc", content=True)
    assert body is not None
    assert 'class="detail-next"' in body
    assert "content=1" in body


def test_detail_html_content_query_narrows_matches(bundle):
    """A body-only keyword narrows the matched set and its crumb count."""
    body = report_detail_html(bundle, "alpha_report.html", q="zebra",
                              content=True)
    assert "1 match(es)" in body


# ── HTTP routes ─────────────────────────────────────────────────────────────


def test_route_api_report_content_returns_json(server):
    status, body = _fetch(server, "/api/report/content?name=alpha_report.html")
    assert status == 200
    data = json.loads(body)
    assert data["ok"] is True
    assert data["name"] == "alpha_report.html"
    assert "zebra" in data["content"]


def test_route_api_report_content_missing_name_400(server):
    status, body = _fetch(server, "/api/report/content")
    assert status == 400
    assert json.loads(body)["ok"] is False
    assert json.loads(body)["error"] == "missing name"


def test_route_api_report_content_unknown_404(server):
    status, body = _fetch(server, "/api/report/content?name=nope.html")
    assert status == 404
    assert json.loads(body)["ok"] is False


def test_route_meta_content_search_filters_by_body(server):
    status, body = _fetch(server, "/api/meta?q=zebra&content=1")
    assert status == 200
    data = json.loads(body)
    assert [row["name"] for row in data["reports"]] == ["alpha_report.html"]
    assert data["total"] == 1


def test_route_dashboard_content_search_filters(server):
    status, body = _fetch(server, "/?q=zebra&content=1")
    assert status == 200
    assert "Alpha Report" in body
    assert "Gamma Report" not in body
    assert 'name="content" value="1" checked' in body


def test_route_detail_preserves_content_in_nav(server):
    status, body = _fetch(server, "/report/alpha_report.html?q=zebra&content=1")
    assert status == 200
    assert "1 match(es)" in body
