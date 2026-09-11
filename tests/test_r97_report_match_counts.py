"""R97: content match counts threaded through the machine-readable API.

R96 made a content search *rankable* and showed each report's body match count
on the dashboard / detail pages, but the machine-readable ``/api/meta`` surface
still carried no match metadata -- a script could order by ``sort=matches`` yet
could not read *why* the order was what it was. R97 closes that API-parity gap:

* :func:`content_match_counts` -- a pure helper returning ``{name: count}`` for
  many reports at once, reused by ``dashboard_html`` so the summary total and
  the per-report lines come from a single scan per report;
* a per-report ``matches`` body match count plus an aggregate ``matches`` total
  on the ``/api/meta`` payload, when a content search is active.

Everything stays purely additive: a non-content ``/api/meta`` response is
unchanged, the existing report anchors / metadata search / sort keys are
untouched, and ``bundle_listings`` still parses the pages. No third-party deps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    content_match_count,
    content_match_counts,
    content_snippets,
    dashboard_html,
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

# Ranked (descending match count) order a ``matches`` sort must produce.
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


def _meta(server, query: str):
    status, body = _fetch(server, f"/api/meta{query}")
    assert status == 200
    return json.loads(body)


# ── content_match_counts (pure) ────────────────────────────────────────────


def test_match_counts_returns_one_entry_per_name(bundle):
    counts = content_match_counts(bundle, INDEX_ORDER, KEYWORD)
    assert counts == COUNTS


def test_match_counts_agrees_with_single_count(bundle):
    counts = content_match_counts(bundle, INDEX_ORDER, KEYWORD)
    for name in INDEX_ORDER:
        assert counts[name] == content_match_count(bundle, name, KEYWORD)


def test_match_counts_is_case_insensitive(bundle):
    counts = content_match_counts(bundle, INDEX_ORDER, KEYWORD.upper())
    assert counts == COUNTS


def test_match_counts_empty_query_is_all_zero(bundle):
    counts = content_match_counts(bundle, INDEX_ORDER, "")
    assert counts == {name: 0 for name in INDEX_ORDER}


def test_match_counts_missing_name_counts_zero_but_keeps_key(bundle):
    counts = content_match_counts(bundle, ["missing.html"], KEYWORD)
    assert counts == {"missing.html": 0}


def test_match_counts_empty_names_is_empty_dict(bundle):
    assert content_match_counts(bundle, [], KEYWORD) == {}


def test_match_counts_duplicate_names_collapse(bundle):
    counts = content_match_counts(
        bundle, ["alpha_report.html", "alpha_report.html"], KEYWORD)
    assert counts == {"alpha_report.html": COUNTS["alpha_report.html"]}


def test_match_counts_matches_snippet_list_length(bundle):
    for name in INDEX_ORDER:
        counts = content_match_counts(bundle, [name], KEYWORD)
        assert counts[name] == len(content_snippets(bundle, name, KEYWORD))


# ── dashboard_html: single-pass counts stay correct ────────────────────────


def test_dashboard_still_renders_per_report_counts(bundle):
    page = dashboard_html(bundle, q=KEYWORD, sort="matches", content=True)
    assert '<li class="matches">5 match(es) in body</li>' in page
    assert '<li class="matches">2 match(es) in body</li>' in page
    assert '<li class="matches">1 match(es) in body</li>' in page


def test_dashboard_still_reports_total_match_count(bundle):
    page = dashboard_html(bundle, q=KEYWORD, content=True)
    assert f"{sum(COUNTS.values())} match(es)" in page


# ── /api/meta: per-report + aggregate match counts ─────────────────────────


def test_meta_content_search_adds_per_report_matches(server):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    counts = {row["name"]: row["matches"] for row in data["reports"]}
    assert counts == COUNTS


def test_meta_content_search_adds_aggregate_matches(server):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    assert data["matches"] == sum(COUNTS.values())


def test_meta_content_search_preserves_row_keys(server):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    row = data["reports"][0]
    for key in ("name", "label", "title", "size_bytes", "mtime", "matches"):
        assert key in row


def test_meta_non_content_search_has_no_matches(server):
    data = _meta(server, "?q=alpha")
    assert "matches" not in data
    assert all("matches" not in row for row in data["reports"])


def test_meta_content_flag_without_q_has_no_matches(server):
    data = _meta(server, "?content=1")
    assert "matches" not in data
    assert all("matches" not in row for row in data["reports"])


def test_meta_metadata_only_hit_counts_zero(server):
    data = _meta(server, "?q=html&content=1")
    assert data["matches"] == 0
    assert all(row["matches"] == 0 for row in data["reports"])
    assert [row["name"] for row in data["reports"]] == list(INDEX_ORDER)


def test_meta_matches_sort_counts_track_ranking(server):
    data = _meta(server, f"?q={KEYWORD}&sort=matches&content=1")
    assert [row["name"] for row in data["reports"]] == list(RANKED)
    assert [row["matches"] for row in data["reports"]] == [
        COUNTS[name] for name in RANKED]


def test_meta_pagination_counts_page_rows_but_aggregates_all(server):
    data = _meta(server, f"?q={KEYWORD}&content=1&limit=2")
    # the page holds the first two (index order) reports ...
    assert [row["name"] for row in data["reports"]] == [
        "alpha_report.html", "beta_report.html"]
    assert [row["matches"] for row in data["reports"]] == [2, 5]
    # ... while the aggregate covers the whole matched set.
    assert data["matches"] == sum(COUNTS.values())
    assert data["total"] == len(INDEX_ORDER)


def test_meta_content_search_no_match_is_empty_with_zero_total(server):
    data = _meta(server, "?q=absent-keyword&content=1")
    assert data["reports"] == []
    assert data["matches"] == 0
    assert data["total"] == 0


def test_meta_unknown_sort_still_400(server):
    status, body = _fetch(server, f"/api/meta?q={KEYWORD}&sort=bogus&content=1")
    assert status == 400
    assert json.loads(body)["ok"] is False
