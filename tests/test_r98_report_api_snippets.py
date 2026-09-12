"""R98: content-search excerpts on the machine-readable ``/api/meta`` surface.

R97 gave ``/api/meta`` each report's body match *count* in a content search, but
the *excerpts* that show where / why a report matched stayed on the HTML pages or
behind one ``/api/report/snippet`` request per report -- so a client assembling a
full content-search result still needed N+1 calls. R98 closes that gap:

* a content-mode ``/api/meta`` row now also carries its ``snippets`` (the
  :func:`content_snippets` windows the dashboard / detail pages render, uncapped
  so the JSON surface is the complete result), alongside the existing ``matches``
  count, so one call yields the whole ranked content-search result.

Everything stays purely additive: rows gain ``snippets`` only in a content
search, a non-content ``/api/meta`` response is unchanged, and the existing
report anchors / metadata search / sort keys are untouched. No third-party deps.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    content_snippets,
    dashboard_html,
    highlight_html,
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


def _report_body(name: str, count: int) -> str:
    block = f"<p>{FILLER}</p>"
    for i in range(count):
        block += f"<p>segment {i} mentions the {KEYWORD} here</p><p>{FILLER}</p>"
    title = f"{_label(name)} Field Map"
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{title}</title></head><body>{block}</body></html>")


def _write_report(root, name: str, mtime: float, pad: int):
    path = root / name
    path.write_text(_report_body(name, COUNTS[name]), encoding="utf-8")
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


# ── /api/meta: per-report snippets ─────────────────────────────────────────


def test_meta_content_search_adds_per_report_snippets(server, bundle):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    got = {row["name"]: row["snippets"] for row in data["reports"]}
    assert set(got) == set(INDEX_ORDER)
    for name in INDEX_ORDER:
        assert got[name] == content_snippets(bundle, name, KEYWORD)


def test_meta_snippets_are_non_empty_strings(server):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    for row in data["reports"]:
        assert row["snippets"]
        assert all(isinstance(s, str) and s for s in row["snippets"])


def test_meta_snippets_contain_the_query(server):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    for row in data["reports"]:
        assert all(KEYWORD in s.lower() for s in row["snippets"])


def test_meta_snippets_length_agrees_with_matches(server):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    for row in data["reports"]:
        assert len(row["snippets"]) == row["matches"] == COUNTS[row["name"]]


def test_meta_snippets_are_uncapped(tmp_path):
    # A report with more body matches than the page's _MAX_SNIPPETS (5): the JSON
    # surface returns the complete list while the dashboard truncates.
    b = tmp_path / "many"
    b.mkdir(exist_ok=True)
    (b / "many_report.html").write_text(
        _report_body("many_report.html", 7), encoding="utf-8")
    (b / "index.html").write_text(
        '<!doctype html><html><head><title>t</title></head><body><ul>'
        '<li><a href="many_report.html">Many Report</a></li></ul></body></html>',
        encoding="utf-8")
    srv, thread = serve_bundle(b, port=0, in_thread=True)
    try:
        data = _meta(srv, f"?q={KEYWORD}&content=1")
        row = data["reports"][0]
        assert row["matches"] == len(row["snippets"]) == 7
        page = dashboard_html(b, q=KEYWORD, content=True)
        assert page.count('<li class="snippet">') == 5
        assert "snippet-more" in page
    finally:
        srv.shutdown()
        thread.join()


def test_meta_snippets_agree_with_snippet_endpoint(server):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    for row in data["reports"]:
        status, body = _fetch(
            server, f"/api/report/snippet?name={row['name']}&q={KEYWORD}")
        assert status == 200
        assert row["snippets"] == json.loads(body)["snippets"]


def test_meta_snippets_case_insensitive_query(server, bundle):
    data = _meta(server, f"?q={KEYWORD.upper()}&content=1")
    for row in data["reports"]:
        assert row["snippets"] == content_snippets(
            bundle, row["name"], KEYWORD)


def test_meta_content_search_preserves_row_keys(server):
    data = _meta(server, f"?q={KEYWORD}&content=1")
    row = data["reports"][0]
    for key in ("name", "label", "title", "size_bytes", "mtime",
                "matches", "snippets"):
        assert key in row


def test_meta_non_content_search_has_no_snippets(server):
    data = _meta(server, "?q=alpha")
    assert all("snippets" not in row for row in data["reports"])


def test_meta_content_flag_without_q_has_no_snippets(server):
    data = _meta(server, "?content=1")
    assert all("snippets" not in row for row in data["reports"])


def test_meta_metadata_only_hit_has_empty_snippets(server):
    data = _meta(server, "?q=html&content=1")
    assert [row["name"] for row in data["reports"]] == list(INDEX_ORDER)
    assert all(row["snippets"] == [] for row in data["reports"])
    assert all(row["matches"] == 0 for row in data["reports"])


def test_meta_snippets_track_matches_ranking(server):
    data = _meta(server, f"?q={KEYWORD}&sort=matches&content=1")
    assert [row["name"] for row in data["reports"]] == list(RANKED)
    assert [len(row["snippets"]) for row in data["reports"]] == [
        COUNTS[name] for name in RANKED]


def test_meta_snippets_only_for_page_rows_but_aggregate_over_all(server):
    data = _meta(server, f"?q={KEYWORD}&content=1&limit=2")
    assert [row["name"] for row in data["reports"]] == [
        "alpha_report.html", "beta_report.html"]
    assert all(row["snippets"] for row in data["reports"])
    assert "snippets" not in data
    assert data["matches"] == sum(COUNTS.values())
    assert data["total"] == len(INDEX_ORDER)


def test_meta_content_search_no_match_is_empty(server):
    data = _meta(server, "?q=absent-keyword&content=1")
    assert data["reports"] == []
    assert data["matches"] == 0


def test_meta_unknown_sort_still_400(server):
    status, body = _fetch(server, f"/api/meta?q={KEYWORD}&sort=bogus&content=1")
    assert status == 400
    assert json.loads(body)["ok"] is False


def test_meta_snippets_mark_the_match_on_the_page(server, bundle):
    # The dashboard renders the same excerpts (highlighted); the JSON windows
    # are the plain-text source of those <li class="snippet"> lines.
    data = _meta(server, f"?q={KEYWORD}&content=1")
    page = dashboard_html(bundle, q=KEYWORD, content=True)
    alpha = next(r for r in data["reports"]
                 if r["name"] == "alpha_report.html")
    for snippet in alpha["snippets"]:
        assert highlight_html(snippet, KEYWORD) in page
