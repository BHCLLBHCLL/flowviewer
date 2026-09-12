"""R102: "report N of M" position readout in the detail crumbs.

R100's :func:`report_context` computes each report's 0-based ``index`` and the
``total`` in the active ordering and exposes them on ``/api/report``, but the
detail page consumed only the ``prev`` / ``next`` neighbours -- the crumb trail
showed the total match count yet never *where* the current report sat. R102
closes that gap:

* :func:`report_detail_html` renders the position from the same
  :func:`report_context` result the page already computes as a
  ``<span class="report-position">`` "report N of M" readout (1-based) inside
  the crumbs, so the human surface shows the ``index``/``total`` the machine
  surface (R100) already returns.

Everything stays purely additive: the dashboard back link and the
``N match(es)`` crumb are unchanged, the span is only added when the report is
in the active ordering, and the ``prev`` / ``next`` labels / hrefs are
untouched. No third-party deps.
"""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    query_reports,
    report_context,
    report_detail_html,
    report_meta,
    serve_bundle,
)

INDEX_ORDER = ("many_report.html", "some_report.html", "one_report.html")

# Body-only keyword, occurring a different number of times per report so the
# ``matches`` ranking has a well-defined (non-index) order.
KEYWORD = "signal"

COUNTS = {
    "many_report.html": 7,
    "some_report.html": 3,
    "one_report.html": 1,
}

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


def _span(index: int, total: int) -> str:
    return f'<span class="report-position">report {index + 1} of {total}</span>'


# ── report_detail_html: 1-based position within the index order ─────────────


def test_position_first_report(bundle):
    page = report_detail_html(bundle, "many_report.html")
    assert _span(0, 3) in page


def test_position_middle_report(bundle):
    page = report_detail_html(bundle, "some_report.html")
    assert _span(1, 3) in page


def test_position_last_report(bundle):
    page = report_detail_html(bundle, "one_report.html")
    assert _span(2, 3) in page


def test_position_is_one_based(bundle):
    page = report_detail_html(bundle, "many_report.html")
    assert "report 0 of" not in page


def test_position_matches_report_context(bundle):
    rows = report_meta(bundle)
    for name in INDEX_ORDER:
        ctx = report_context(rows, name)
        page = report_detail_html(bundle, name)
        assert _span(ctx["index"], ctx["total"]) in page


# ── position reflects the active sort / dir / content ordering ───────────────


def test_position_reflects_name_sort(bundle):
    page = report_detail_html(bundle, "one_report.html", sort="name")
    assert _span(1, 3) in page


def test_position_reflects_matches_sort_ascending(bundle):
    page = report_detail_html(bundle, "one_report.html", q=KEYWORD,
                              content=True, sort="matches", dir="asc")
    assert _span(0, 3) in page


def test_position_reflects_matches_sort_descending(bundle):
    page = report_detail_html(bundle, "many_report.html", q=KEYWORD,
                              content=True, sort="matches")
    assert _span(0, 3) in page


def test_position_reflects_windowed_order(bundle):
    rows = query_reports(report_meta(bundle), sort="name", dir="desc")
    ctx = report_context(rows, "one_report.html")
    page = report_detail_html(bundle, "one_report.html", sort="name",
                              dir="desc")
    assert ctx["index"] == 1
    assert _span(ctx["index"], ctx["total"]) in page


# ── filtered total / omitted position ───────────────────────────────────────


def test_position_total_shrinks_with_query(bundle):
    page = report_detail_html(bundle, "one_report.html", q="one")
    assert _span(0, 1) in page


def test_position_omitted_when_report_filtered_out(bundle):
    page = report_detail_html(bundle, "many_report.html", q="one")
    assert "report-position" not in page


def test_position_span_absent_when_not_in_ordering_but_crumbs_remain(bundle):
    page = report_detail_html(bundle, "many_report.html", q="one")
    assert 'class="crumbs"' in page
    assert "1 match(es)" in page


# ── crumbs / back link / neighbours stay intact (purely additive) ───────────


def test_crumbs_marker_preserved(bundle):
    page = report_detail_html(bundle, "some_report.html")
    assert 'class="crumbs"' in page


def test_match_count_crumb_preserved(bundle):
    page = report_detail_html(bundle, "some_report.html")
    assert "3 match(es)" in page


def test_position_sits_between_dashboard_link_and_match_count(bundle):
    page = report_detail_html(bundle, "some_report.html")
    dash = page.index(">dashboard</a>")
    pos = page.index("report-position")
    count = page.index("3 match(es)")
    assert dash < pos < count


def test_dashboard_back_link_preserved(bundle):
    page = report_detail_html(bundle, "some_report.html")
    assert '>dashboard</a>' in page


def test_dashboard_back_link_preserves_query(bundle):
    page = report_detail_html(bundle, "some_report.html", q=KEYWORD,
                              content=True, sort="matches")
    crumbs = page[:page.index("</p>")]
    assert "q=signal" in crumbs
    assert "content=1" in crumbs
    assert "sort=matches" in crumbs


def test_prev_next_navigation_untouched(bundle):
    page = report_detail_html(bundle, "some_report.html")
    assert 'class="detail-prev"' in page
    assert 'class="detail-next"' in page


def test_unknown_report_returns_none(bundle):
    assert report_detail_html(bundle, "missing_report.html") is None


# ── HTTP: the rendered detail page ──────────────────────────────────────────


def test_http_position_first_report(server):
    status, body = _fetch(server, "/report/many_report.html")
    assert status == 200
    assert _span(0, 3) in body


def test_http_position_reflects_sort(server):
    status, body = _fetch(server, "/report/one_report.html?sort=name")
    assert status == 200
    assert _span(1, 3) in body


def test_http_position_omitted_when_filtered_out(server):
    status, body = _fetch(server, "/report/many_report.html?q=one")
    assert status == 200
    assert "report-position" not in body
    assert "1 match(es)" in body


def test_http_position_with_content_query(server):
    path = (f"/report/one_report.html?q={KEYWORD}&content=1"
            "&sort=matches&dir=asc")
    status, body = _fetch(server, path)
    assert status == 200
    assert _span(0, 3) in body


def test_http_position_with_full_flag(server):
    status, body = _fetch(
        server, f"/report/many_report.html?q={KEYWORD}&content=1&full=1")
    assert status == 200
    assert _span(0, 3) in body
