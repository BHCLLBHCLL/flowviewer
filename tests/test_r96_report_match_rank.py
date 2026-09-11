"""R96: relevance ranking by body match count + visible match counts.

R95 rendered ``every`` body match (a ``content_snippets`` list + a ``count``) and
surfaced it on the dashboard / detail pages, but the results stayed in index /
metadata order and the page never showed ``how many`` times a report matched. A
content search therefore had no relevance ordering: the report where the query
recurs most was not surfaced.

R96 adds:

* :func:`content_match_count` -- the number of non-overlapping body matches,
  sharing :func:`_match_indices` with :func:`content_snippets` so a report's
  count and its excerpts always agree;
* a ``matches`` sort key for :func:`query_reports` (valid only for a content
  search), ranking rows by descending match count with ``dir`` defaulting to
  ``desc``;
* a visible ``<li class="matches">N match(es) in body</li>`` /
  ``<p class="matches">`` line per report plus a total in the summary block;
* a ``matches`` field in ``/api/report/snippet``.

Everything stays purely additive: the existing report anchors, metadata search
and sort keys are unchanged, and ``bundle_listings`` still parses the pages. No
third-party deps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    bundle_listings,
    content_match_count,
    content_snippets,
    dashboard_html,
    query_reports,
    report_detail_html,
    report_meta,
    serve_bundle,
)

INDEX_ORDER = ("alpha_report.html", "beta_report.html", "gamma_report.html")

# One shared body-only keyword, occurring a different number of times per report
# so a content search has a meaningful relevance order (beta > alpha > gamma).
KEYWORD = "signal"

# Body occurrences per report: alpha 2, beta 5, gamma 1.
COUNTS = {
    "alpha_report.html": 2,
    "beta_report.html": 5,
    "gamma_report.html": 1,
}

# Ranked (descending match count) order the ``matches`` sort must produce.
RANKED = ("beta_report.html", "alpha_report.html", "gamma_report.html")

# Long filler between occurrences so a width-120 window never overlaps the next.
FILLER = " ".join(["lorem"] * 40)


def _label(name: str) -> str:
    return name.removesuffix(".html").replace("_", " ").title()


def _write_report(root, name: str, mtime: float, pad: int):
    path = root / name
    block = f"<p>{FILLER}</p>"
    for i in range(COUNTS[name]):
        block += f"<p>segment {i} mentions the {KEYWORD} here</p><p>{FILLER}</p>"
    title = f"{_label(name)} Field Map"
    body = ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{title}</title></head><body>{block}</body></html>")
    path.write_text(body, encoding="utf-8")
    with open(path, "ab") as fh:
        fh.write(b"x" * pad)
    os.utime(path, (mtime, mtime))
    return path


def _make_bundle(tmp_path):
    b = tmp_path / "b"
    b.mkdir(exist_ok=True)
    for i, name in enumerate(INDEX_ORDER):
        _write_report(b, name, 1_700_000_000 + i, 100 * i)
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


def _names(rows):
    return [row["name"] for row in rows]


# ── content_match_count (pure) ─────────────────────────────────────────────


def test_content_match_count_counts_all_occurrences(bundle):
    for name in INDEX_ORDER:
        assert content_match_count(bundle, name, KEYWORD) == COUNTS[name]


def test_content_match_count_is_case_insensitive(bundle):
    assert content_match_count(
        bundle, "beta_report.html", KEYWORD.upper()) == COUNTS["beta_report.html"]


def test_content_match_count_empty_or_absent_is_zero(bundle):
    assert content_match_count(bundle, "alpha_report.html", "") == 0
    assert content_match_count(bundle, "alpha_report.html", "absent") == 0
    assert content_match_count(bundle, "missing.html", KEYWORD) == 0


def test_content_match_count_agrees_with_snippet_count(bundle):
    for name in INDEX_ORDER:
        snippets = content_snippets(bundle, name, KEYWORD)
        assert content_match_count(bundle, name, KEYWORD) == len(snippets)


# ── query_reports: matches sort key ────────────────────────────────────────


def test_query_reports_matches_sort_ranks_desc(bundle):
    rows = report_meta(bundle)
    ranked = query_reports(rows, q=KEYWORD, sort="matches", dir="desc",
                           content=True, bundle_dir=bundle)
    assert _names(ranked) == list(RANKED)


def test_query_reports_matches_sort_asc(bundle):
    rows = report_meta(bundle)
    ranked = query_reports(rows, q=KEYWORD, sort="matches", dir="asc",
                           content=True, bundle_dir=bundle)
    assert _names(ranked) == list(reversed(RANKED))


def test_query_reports_matches_sort_requires_content(bundle):
    rows = report_meta(bundle)
    with pytest.raises(ValueError):
        query_reports(rows, q=KEYWORD, sort="matches")


def test_query_reports_matches_sort_requires_bundle_dir(bundle):
    rows = report_meta(bundle)
    with pytest.raises(ValueError):
        query_reports(rows, q=KEYWORD, sort="matches", content=True)


def test_query_reports_unknown_sort_still_raises(bundle):
    rows = report_meta(bundle)
    with pytest.raises(ValueError):
        query_reports(rows, sort="bogus")


# ── dashboard_html: ranking + visible counts ───────────────────────────────


def test_dashboard_matches_sort_defaults_desc(bundle):
    page = dashboard_html(bundle, q=KEYWORD, sort="matches", content=True)
    beta = page.index('href="beta_report.html"')
    alpha = page.index('href="alpha_report.html"')
    gamma = page.index('href="gamma_report.html"')
    assert beta < alpha < gamma


def test_dashboard_renders_per_report_match_count(bundle):
    page = dashboard_html(bundle, q=KEYWORD, sort="matches", content=True)
    assert '<li class="matches">5 match(es) in body</li>' in page
    assert '<li class="matches">2 match(es) in body</li>' in page
    assert '<li class="matches">1 match(es) in body</li>' in page


def test_dashboard_summary_reports_total_match_count(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True)
    total = sum(COUNTS.values())
    assert f"{total} match(es)" in page


def test_dashboard_metadata_only_hit_has_zero_body_count(bundle):
    page = dashboard_html(bundle, q="html", content=True)
    assert "Alpha Report" in page
    assert '<li class="matches">0 match(es) in body</li>' in page
    assert 'class="snippet"' not in page


def test_dashboard_non_content_search_has_no_matches_line(bundle):
    page = dashboard_html(bundle, q="alpha")
    assert "Alpha Report" in page
    assert 'class="matches"' not in page


def test_controls_form_lists_matches_sort_option(bundle):
    page = dashboard_html(bundle, q=KEYWORD, sort="matches", content=True)
    assert 'value="matches"' in page


def test_dashboard_matches_page_stays_bundle_listings_parseable(bundle, tmp_path):
    page = dashboard_html(bundle, q=KEYWORD, sort="matches", content=True)
    outdir = tmp_path / "served"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(page, encoding="utf-8")
    listings = bundle_listings(outdir)
    # the ``matches`` lines must not be mistaken for report anchors -- the
    # parsed order tracks the ranked page order.
    assert [item["name"] for item in listings] == list(RANKED)


# ── report_detail_html: visible count ──────────────────────────────────────


def test_detail_renders_match_count_line(bundle):
    body = report_detail_html(bundle, "beta_report.html", q=KEYWORD,
                              content=True)
    assert body is not None
    assert '<p class="matches">5 match(es) in body</p>' in body


def test_detail_nav_follows_matches_ranking(bundle):
    body = report_detail_html(bundle, "beta_report.html", q=KEYWORD,
                              sort="matches", content=True)
    assert body is not None
    # beta is first in the ranking, so it only has a "next" (alpha).
    assert 'class="detail-next"' in body
    assert 'class="detail-prev"' not in body


# ── HTTP routes ────────────────────────────────────────────────────────────


def test_route_dashboard_matches_sort_ranks(server):
    status, body = _fetch(server, f"/?q={KEYWORD}&sort=matches&content=1")
    assert status == 200
    beta = body.index('href="beta_report.html"')
    alpha = body.index('href="alpha_report.html"')
    gamma = body.index('href="gamma_report.html"')
    assert beta < alpha < gamma


def test_route_meta_matches_sort_ranks(server):
    status, body = _fetch(
        server, f"/api/meta?q={KEYWORD}&sort=matches&content=1")
    assert status == 200
    data = json.loads(body)
    assert [row["name"] for row in data["reports"]] == list(RANKED)


def test_route_matches_sort_without_content_400(server):
    for path in ("/?sort=matches", "/api/meta?sort=matches"):
        status, body = _fetch(server, path)
        assert status == 400
        assert json.loads(body)["ok"] is False


def test_route_snippet_includes_matches_count(server):
    status, body = _fetch(server, f"/api/report/snippet?name=beta_report.html"
                          f"&q={KEYWORD}")
    assert status == 200
    data = json.loads(body)
    assert data["matches"] == COUNTS["beta_report.html"]
    assert data["count"] == COUNTS["beta_report.html"]
