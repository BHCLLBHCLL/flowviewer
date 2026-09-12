"""R99: on-demand uncapped body excerpts on the HTML dashboard / detail pages.

R98 made the machine-readable content-search result complete (``/api/meta``
returns every ``snippets`` window), but the HTML dashboard / detail pages still
capped at ``_MAX_SNIPPETS`` excerpts, with the "… and N more match(es)" note
dead-ending -- a browser user could not reach the rest. R99 closes that gap:

* a ``full=1`` flag (threaded through the controls form, the pager / detail /
  back-link hrefs and the dashboard / detail routes) renders *every* body
  match when set, and otherwise the "… and N more match(es)" note becomes a link
  that re-runs the same query with ``full=1`` -- so the page reaches the same
  complete result ``/api/meta`` returns (R98).

Everything stays purely additive: default ``full=False`` keeps the R95
five-snippet cap and the plain note, so existing anchors / listings are
unchanged. No third-party deps.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    dashboard_html,
    report_detail_html,
    serve_bundle,
)

INDEX_ORDER = ("many_report.html", "some_report.html", "one_report.html")

# One shared body-only keyword, occurring a different number of times per report
# so the cap (``_MAX_SNIPPETS = 5``) is exercised by the first report only.
KEYWORD = "signal"

# Body occurrences per report: many 7 (capped), some 3, one 1.
COUNTS = {
    "many_report.html": 7,
    "some_report.html": 3,
    "one_report.html": 1,
}

MAX = 5

# Long filler between occurrences so a width-120 window never overlaps the next.
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
        (b / name).write_text(_report_body(name, COUNTS[name]), encoding="utf-8")
    _write_index(b, INDEX_ORDER)
    return b


def _single_bundle(tmp_path, count):
    b = tmp_path / f"solo{count}"
    b.mkdir(exist_ok=True)
    (b / "solo_report.html").write_text(
        _report_body("solo_report.html", count), encoding="utf-8")
    _write_index(b, ("solo_report.html",))
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


# ── dashboard_html: cap, uncap and the linked note ─────────────────────────


def test_dashboard_default_caps_snippets(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True)
    assert page.count('<li class="snippet">') == MAX + COUNTS["some_report.html"] + 1
    assert '<li class="snippet-more">' in page
    assert "and 2 more match(es)" in page


def test_dashboard_full_renders_all_snippets(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True, full=True)
    assert page.count('<li class="snippet">') == sum(COUNTS.values())


def test_dashboard_full_drops_the_more_note(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True, full=True)
    assert "snippet-more" not in page


def test_dashboard_default_more_note_links_to_full(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True)
    assert ('<li class="snippet-more"><a href='
            '"q=signal&amp;content=1&amp;full=1">' in page
            or '<li class="snippet-more"><a href='
            '"?q=signal&amp;content=1&amp;full=1">' in page)


def test_dashboard_pager_preserves_full(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True, full=True, limit=2)
    assert ('class="pager-next" href="?limit=2&offset=2&q=signal&content=1&full=1"'
            in page)


def test_dashboard_pager_default_has_no_full(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True, limit=2)
    assert ('class="pager-next" href="?limit=2&offset=2&q=signal&content=1"'
            in page)


def test_dashboard_controls_offer_full_flag(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True)
    assert 'name="full" value="1"' in page
    assert 'name="full" value="1" checked' not in page


def test_dashboard_controls_reflect_full(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True, full=True)
    assert 'name="full" value="1" checked' in page


def test_dashboard_full_without_content_shows_no_snippets(bundle):
    page = dashboard_html(bundle, q=KEYWORD, full=True)
    assert '<li class="snippet">' not in page
    assert '<li class="matches">' not in page


def test_dashboard_exact_cap_has_no_note(tmp_path):
    page = dashboard_html(_single_bundle(tmp_path, MAX),
                          q=KEYWORD, content=True)
    assert page.count('<li class="snippet">') == MAX
    assert "snippet-more" not in page


def test_dashboard_over_cap_has_note(tmp_path):
    page = dashboard_html(_single_bundle(tmp_path, MAX + 1),
                          q=KEYWORD, content=True)
    assert page.count('<li class="snippet">') == MAX
    assert "and 1 more match(es)" in page


# ── report_detail_html: cap, uncap and preserved hrefs ─────────────────────


def test_detail_default_caps_snippets(bundle):
    page = report_detail_html(bundle, "many_report.html", q=KEYWORD, content=True)
    assert page.count('<p class="snippet">') == MAX
    assert '<p class="snippet-more">' in page
    assert "and 2 more match(es)" in page


def test_detail_full_renders_all_snippets(bundle):
    page = report_detail_html(
        bundle, "many_report.html", q=KEYWORD, content=True, full=True)
    assert page.count('<p class="snippet">') == COUNTS["many_report.html"]


def test_detail_full_drops_the_more_note(bundle):
    page = report_detail_html(
        bundle, "many_report.html", q=KEYWORD, content=True, full=True)
    assert "snippet-more" not in page


def test_detail_default_more_note_links_to_full(bundle):
    page = report_detail_html(bundle, "many_report.html", q=KEYWORD, content=True)
    assert ('<p class="snippet-more"><a href='
            '"/report/many_report.html?q=signal&amp;content=1&amp;full=1">'
            in page)


def test_detail_back_link_preserves_full(bundle):
    page = report_detail_html(
        bundle, "many_report.html", q=KEYWORD, content=True, full=True)
    assert '<a href="/?q=signal&amp;content=1&amp;full=1">dashboard</a>' in page


def test_detail_nav_preserves_full(bundle):
    page = report_detail_html(
        bundle, "some_report.html", q=KEYWORD, content=True, full=True)
    assert ('/report/many_report.html?q=signal&amp;content=1&amp;full=1'
            in page)
    assert ('/report/one_report.html?q=signal&amp;content=1&amp;full=1'
            in page)


# ── HTTP routes: the flag is honoured end to end ───────────────────────────


def test_route_dashboard_default_caps(server):
    status, body = _fetch(server, f"/?q={KEYWORD}&content=1")
    assert status == 200
    assert body.count('<li class="snippet">') == (
        MAX + COUNTS["some_report.html"] + 1)
    assert '<li class="snippet-more">' in body


def test_route_dashboard_full_renders_all(server):
    status, body = _fetch(server, f"/?q={KEYWORD}&content=1&full=1")
    assert status == 200
    assert body.count('<li class="snippet">') == sum(COUNTS.values())
    assert "snippet-more" not in body


def test_route_dashboard_full_zero_is_capped(server):
    status, body = _fetch(server, f"/?q={KEYWORD}&content=1&full=0")
    assert status == 200
    assert body.count('<li class="snippet">') == (
        MAX + COUNTS["some_report.html"] + 1)


def test_route_detail_default_caps(server):
    status, body = _fetch(
        server, f"/report/many_report.html?q={KEYWORD}&content=1")
    assert status == 200
    assert body.count('<p class="snippet">') == MAX


def test_route_detail_full_renders_all(server):
    status, body = _fetch(
        server, f"/report/many_report.html?q={KEYWORD}&content=1&full=1")
    assert status == 200
    assert body.count('<p class="snippet">') == COUNTS["many_report.html"]
    assert "snippet-more" not in body


def test_route_meta_ignores_full_and_stays_complete(server):
    # ``full`` is a page-side flag only: the JSON surface was already complete
    # (R98), so it must be uncapped with or without ``full=1``.
    for query in (f"?q={KEYWORD}&content=1", f"?q={KEYWORD}&content=1&full=1"):
        status, body = _fetch(server, f"/api/meta{query}")
        assert status == 200
        data = json.loads(body)
        many = next(r for r in data["reports"]
                    if r["name"] == "many_report.html")
        assert many["matches"] == len(many["snippets"]) == COUNTS["many_report.html"]


def test_route_meta_row_keys_unchanged(server):
    status, body = _fetch(server, f"/api/meta?q={KEYWORD}&content=1&full=1")
    assert status == 200
    row = json.loads(body)["reports"][0]
    for key in ("name", "label", "title", "size_bytes", "mtime",
                "matches", "snippets"):
        assert key in row
