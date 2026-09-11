"""R95: every body match (multi-snippet) + a content-search match count.

R94 rendered a single body excerpt per matched report, so a term that recurred
inside a report gave no sense of how many matches there were or where the rest
lived. R95 adds ``content_snippets()`` -- one plain-text window per
non-overlapping body match (overlapping windows merged, optional ``limit``) --
reimplements ``content_snippet()`` as its first element (so R94 is unchanged),
renders one ``<li class="snippet">`` / ``<p class="snippet">`` per match on the
dashboard / detail pages (capped at ``_MAX_SNIPPETS``, with an "… and N more
match(es)" note when the rest are collapsed), and extends ``/api/report/snippet``
with ``count`` + a ``snippets`` list. Everything stays purely additive so
``bundle_listings`` still parses and a metadata search is unchanged. No
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
    content_snippet,
    content_snippets,
    dashboard_html,
    report_detail_html,
    serve_bundle,
)

INDEX_ORDER = ("alpha_report.html", "beta_report.html", "gamma_report.html")

# A body-only keyword per report -- never in the name / label / title.
KEYWORD = {
    "alpha_report.html": "zebra",
    "beta_report.html": "nebula",
    "gamma_report.html": "volcanic",
}

# Explicit body occurrences per report: alpha 3, beta 1, gamma 7 (over the cap).
OCCURRENCES = {
    "alpha_report.html": 3,
    "beta_report.html": 1,
    "gamma_report.html": 7,
}

# Long filler between occurrences so a width-120 window never overlaps the next.
FILLER = " ".join(["lorem"] * 40)


def _label(name: str) -> str:
    return name.removesuffix(".html").replace("_", " ").title()


def _write_report(root, name: str, mtime: float, pad: int):
    path = root / name
    block = f"<p>{FILLER}</p>"
    for i in range(OCCURRENCES[name]):
        block += f"<p>segment {i} report {KEYWORD[name]}</p><p>{FILLER}</p>"
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


# ── content_snippets (pure) ────────────────────────────────────────────────


def test_content_snippets_one_per_occurrence(bundle):
    snips = content_snippets(bundle, "alpha_report.html", "zebra")
    assert len(snips) == OCCURRENCES["alpha_report.html"]
    for snip in snips:
        assert "zebra" in snip
        assert "<" not in snip and ">" not in snip


def test_content_snippets_counts_single_and_many(bundle):
    assert len(content_snippets(bundle, "beta_report.html", "nebula")) == 1
    assert len(content_snippets(bundle, "gamma_report.html", "volcanic")) == 7


def test_content_snippets_is_case_insensitive(bundle):
    snips = content_snippets(bundle, "alpha_report.html", "ZEBRA")
    assert len(snips) == OCCURRENCES["alpha_report.html"]


def test_content_snippets_empty_without_query(bundle):
    assert content_snippets(bundle, "alpha_report.html", None) == []
    assert content_snippets(bundle, "alpha_report.html", "") == []


def test_content_snippets_empty_when_absent(bundle):
    assert content_snippets(bundle, "alpha_report.html", "no-such-word") == []


def test_content_snippets_empty_for_unknown_report(bundle):
    assert content_snippets(bundle, "nope.html", "zebra") == []


def test_content_snippets_empty_for_path_escape(bundle):
    assert content_snippets(bundle, "../index.html", "zebra") == []


def test_content_snippets_limit_caps(bundle):
    snips = content_snippets(bundle, "gamma_report.html", "volcanic", limit=2)
    assert len(snips) == 2


def test_content_snippets_windows_are_distinct(bundle):
    snips = content_snippets(bundle, "alpha_report.html", "zebra")
    assert len(snips) == len(set(snips))


def test_content_snippets_truncated_with_ellipses(bundle):
    snips = content_snippets(bundle, "alpha_report.html", "zebra")
    assert all(s.startswith("…") and s.endswith("…") for s in snips)


def test_content_snippets_merges_overlapping_windows(bundle):
    dense = ("<!doctype html><html><head><title>dense</title></head>"
             "<body><p>zebra zebra zebra</p></body></html>")
    (bundle / "dense_report.html").write_text(dense, encoding="utf-8")
    snips = content_snippets(bundle, "dense_report.html", "zebra")
    assert len(snips) == 1
    assert "zebra" in snips[0]


def test_content_snippet_equals_first_of_snippets(bundle):
    snips = content_snippets(bundle, "alpha_report.html", "zebra")
    assert content_snippet(bundle, "alpha_report.html", "zebra") == snips[0]


# ── dashboard_html: one snippet per match ──────────────────────────────────


def test_dashboard_content_search_renders_one_snippet_per_match(bundle):
    page = dashboard_html(bundle, q="zebra", content=True)
    assert page.count('<li class="snippet">') == 3
    assert "<mark>zebra</mark>" in page
    assert "Alpha Report" in page


def test_dashboard_content_search_caps_and_notes_more(bundle):
    page = dashboard_html(bundle, q="volcanic", content=True)
    assert page.count('<li class="snippet">') == 5
    assert '<li class="snippet-more">' in page
    assert "and 2 more match(es)" in page


def test_dashboard_metadata_search_has_no_snippet(bundle):
    page = dashboard_html(bundle, q="alpha")
    assert "Alpha Report" in page
    assert 'class="snippet"' not in page
    assert "<mark>" not in page


def test_dashboard_content_only_metadata_hit_no_snippet(bundle):
    page = dashboard_html(bundle, q="html", content=True)
    assert "Alpha Report" in page
    assert 'class="snippet"' not in page


def test_dashboard_snippets_stay_parsable_by_bundle_listings(bundle, tmp_path):
    page = dashboard_html(bundle, q="zebra", content=True)
    outdir = tmp_path / "served"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(page, encoding="utf-8")
    listings = bundle_listings(outdir)
    assert [item["name"] for item in listings] == ["alpha_report.html"]
    assert listings[0]["label"] == "Alpha Report"


# ── report_detail_html: one snippet per match ──────────────────────────────


def test_detail_content_search_renders_one_snippet_per_match(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q="zebra",
                              content=True)
    assert body is not None
    assert body.count('<p class="snippet">') == 3
    assert "<mark>zebra</mark>" in body


def test_detail_content_search_caps(bundle):
    body = report_detail_html(bundle, "gamma_report.html", q="volcanic",
                              content=True)
    assert body is not None
    assert body.count('<p class="snippet">') == 5


def test_detail_metadata_search_has_no_snippet(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q="alpha")
    assert body is not None
    assert 'class="snippet"' not in body


# ── HTTP: /api/report/snippet + content-search pages ───────────────────────


def test_route_snippet_reports_count_and_list(server):
    status, body = _fetch(
        server, "/api/report/snippet?name=alpha_report.html&q=zebra")
    assert status == 200
    data = json.loads(body)
    assert data["ok"] is True
    assert data["name"] == "alpha_report.html"
    assert data["q"] == "zebra"
    assert data["count"] == 3
    assert len(data["snippets"]) == 3
    assert data["snippet"] == data["snippets"][0]
    assert all("zebra" in s for s in data["snippets"])


def test_route_snippet_single_match(server):
    status, body = _fetch(
        server, "/api/report/snippet?name=beta_report.html&q=nebula")
    assert status == 200
    data = json.loads(body)
    assert data["count"] == 1
    assert len(data["snippets"]) == 1


def test_route_snippet_no_match_count_zero(server):
    status, body = _fetch(
        server, "/api/report/snippet?name=alpha_report.html&q=absent")
    assert status == 200
    data = json.loads(body)
    assert data["count"] == 0
    assert data["snippets"] == []
    assert data["snippet"] is None


def test_route_snippet_missing_name_400(server):
    status, body = _fetch(server, "/api/report/snippet?q=zebra")
    assert status == 400
    assert json.loads(body)["error"] == "missing name"


def test_route_snippet_missing_q_400(server):
    status, body = _fetch(server, "/api/report/snippet?name=alpha_report.html")
    assert status == 400
    assert json.loads(body)["error"] == "missing q"


def test_route_snippet_unknown_report_404(server):
    status, body = _fetch(server, "/api/report/snippet?name=nope.html&q=zebra")
    assert status == 404
    assert json.loads(body)["ok"] is False


def test_route_dashboard_content_search_renders_all_snippets(server):
    status, body = _fetch(server, "/?q=zebra&content=1")
    assert status == 200
    assert body.count('<li class="snippet">') == 3
    assert "<mark>zebra</mark>" in body


def test_route_dashboard_without_content_has_no_snippet(server):
    status, body = _fetch(server, "/?q=zebra")
    assert status == 200
    assert 'class="snippet"' not in body
