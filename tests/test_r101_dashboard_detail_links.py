"""R101: a dashboard entry point into the R91/R92 detail view.

R91/R92 added the dashboard-context detail page at ``/report/<name>``, but the
dashboard's per-report anchors pointed straight at the raw report files, so the
detail view was reachable only by hand-editing the URL or stepping prev / next
from another report's detail page. R101 closes that gap:

* every dashboard row gains a sibling
  ``<li class="actions"><a class="detail-link" href="/report/<name>?…">details``
  link that opens ``/report/<name>`` while preserving the active
  ``q``/``sort``/``dir``/``content``/``full`` -- so a browser user reaches the
  dashboard-context detail page directly.

Everything stays purely additive: the row's primary
``<li><a href="name">label</a></li>`` anchor is untouched (so
:func:`bundle_listings` keeps parsing the page), and the action ``<li>`` carries
a class so :data:`_ITEM_RE` ignores it. No third-party deps.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    bundle_listings,
    dashboard_html,
    serve_bundle,
)

INDEX_ORDER = ("many_report.html", "some_report.html", "one_report.html")

# A body-only keyword so a content search keeps every report (each body carries
# it), letting the details-link assertions run against the full row set.
KEYWORD = "signal"

FILLER = " ".join(["lorem"] * 40)


def _label(name: str) -> str:
    return name.removesuffix(".html").replace("_", " ").title()


def _report_body(name: str, count: int) -> str:
    block = f"<p>{FILLER}</p>"
    for i in range(count):
        block += f"<p>segment {i} mentions the {KEYWORD} here</p><p>{FILLER}</p>"
    title = f"{_label(name)} Field Map"
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{title}</title></head><body>{block}</body></html>")


def _write_index(b, names):
    items = "".join(
        f'<li><a href="{n}">{_label(n)}</a></li>' for n in names)
    (b / "index.html").write_text(
        f"<!doctype html><html><head><title>test bundle</title></head>"
        f"<body><ul>{items}</ul></body></html>", encoding="utf-8")


def _make_bundle(tmp_path):
    b = tmp_path / "b"
    b.mkdir(exist_ok=True)
    for name in INDEX_ORDER:
        (b / name).write_text(_report_body(name, 3), encoding="utf-8")
    _write_index(b, INDEX_ORDER)
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


# ── dashboard_html: the per-row details link ───────────────────────────────


def test_dashboard_each_row_gains_details_link(bundle):
    page = dashboard_html(bundle)
    for name in INDEX_ORDER:
        assert ('<li class="actions"><a class="detail-link" '
                f'href="/report/{name}?">details</a></li>' in page)


def test_dashboard_one_details_link_per_report(bundle):
    page = dashboard_html(bundle)
    assert page.count('class="detail-link"') == len(INDEX_ORDER)
    assert page.count('class="actions"') == len(INDEX_ORDER)


def test_details_link_targets_the_detail_route(bundle):
    page = dashboard_html(bundle)
    assert 'href="/report/many_report.html?' in page
    assert ">details</a>" in page


def test_details_link_is_a_sibling_of_the_primary_anchor(bundle):
    page = dashboard_html(bundle)
    primary = ('<li><a href="many_report.html">Many Report</a></li>\n')
    assert primary in page
    assert page.index(primary) < page.index('class="detail-link"')


# ── query survival ─────────────────────────────────────────────────────────


def test_details_link_preserves_q(bundle):
    page = dashboard_html(bundle, q="some")
    assert ('<li class="actions"><a class="detail-link" '
            'href="/report/some_report.html?q=some">details</a></li>' in page)
    assert page.count('class="detail-link"') == 1


def test_details_link_preserves_sort_and_dir(bundle):
    page = dashboard_html(bundle, sort="size", dir="desc")
    assert ('href="/report/many_report.html?sort=size&amp;dir=desc">details</a>'
            in page)


def test_details_link_preserves_content(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True)
    assert ('href="/report/many_report.html?q=signal&amp;content=1">details</a>'
            in page)


def test_details_link_preserves_content_and_full(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True, full=True)
    assert ('href="/report/many_report.html?'
            'q=signal&amp;content=1&amp;full=1">details</a>' in page)


def test_details_link_default_omits_content_and_full(bundle):
    page = dashboard_html(bundle, q="many")
    assert 'href="/report/many_report.html?q=many">details</a>' in page


def test_details_link_escapes_the_ampersand(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True, full=True)
    assert "&amp;" in page
    assert 'href="/report/many_report.html?q=signal&amp;content=1' in page


def test_details_link_url_quotes_the_report_name(tmp_path):
    b = tmp_path / "q"
    b.mkdir(exist_ok=True)
    name = "odd report.html"
    (b / name).write_text(_report_body(name, 1), encoding="utf-8")
    _write_index(b, (name,))
    page = dashboard_html(b)
    assert 'href="/report/odd%20report.html?' in page


# ── windowing ──────────────────────────────────────────────────────────────


def test_details_link_only_for_the_rendered_window(bundle):
    page = dashboard_html(bundle, limit=1)
    assert page.count('class="detail-link"') == 1


def test_details_link_survives_windowing_offset(bundle):
    page = dashboard_html(bundle, limit=1, offset=1)
    assert 'class="detail-link"' in page
    assert page.count('class="detail-link"') == 1


# ── the listing stays parseable ────────────────────────────────────────────


def test_bundle_listings_parses_a_rendered_dashboard(tmp_path, bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True, full=True)
    served = tmp_path / "served"
    served.mkdir(exist_ok=True)
    (served / "index.html").write_text(page, encoding="utf-8")
    for name in INDEX_ORDER:
        (served / name).write_text("<p>x</p>", encoding="utf-8")
    listings = bundle_listings(served)
    assert [row["name"] for row in listings] == list(INDEX_ORDER)
    assert [row["label"] for row in listings] == [_label(n) for n in INDEX_ORDER]


def test_bundle_listings_ignores_the_action_rows(bundle):
    listings = bundle_listings(bundle)
    assert [row["name"] for row in listings] == list(INDEX_ORDER)
    assert all(row["label"] != "details" for row in listings)


# ── over HTTP ──────────────────────────────────────────────────────────────


def test_http_dashboard_exposes_detail_links(server):
    status, page = _fetch(server, "/")
    assert status == 200
    assert page.count('class="detail-link"') == len(INDEX_ORDER)
    assert 'href="/report/many_report.html?' in page


def test_http_detail_link_resolves(server):
    status, page = _fetch(server, "/report/some_report.html?")
    assert status == 200
    assert _label("some_report.html") in page


def test_http_dashboard_detail_link_preserves_query(server):
    status, page = _fetch(server, "/?q=signal&content=1&full=1")
    assert status == 200
    assert ('href="/report/many_report.html?'
            'q=signal&amp;content=1&amp;full=1">details</a>' in page)
