"""R94: content-search match snippets + ``<mark>`` highlighting.

R93 made a content search (``content=1``) match a report's *body*, but the
dashboard / detail pages gave no clue *where* the match lived -- a body-only hit
looked identical to a title hit. R94 adds ``content_snippet()`` (a pure
plain-text excerpt of a body around a ``q`` match) and ``highlight_html()``
(HTML-escape the text and wrap each ``q`` match in ``<mark>``), renders a
``<li class="snippet">`` / ``<p class="snippet">`` excerpt on the dashboard /
detail pages when a content search is active, and exposes
``/api/report/snippet?name=&q=`` machine-readably. The snippets are purely
additive -- the existing report anchors are untouched, so ``bundle_listings``
stays parseable and a metadata search is unchanged. No third-party deps.
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
    dashboard_html,
    highlight_html,
    report_detail_html,
    serve_bundle,
)

INDEX_ORDER = ("gamma_report.html", "alpha_report.html", "beta_report.html")

# A body-only keyword per report -- never in the name / label / title.
BODY_KEYWORD = {
    "gamma_report.html": "volcanic",
    "alpha_report.html": "zebra",
    "beta_report.html": "nebula",
}

# Long filler so a snippet window is genuinely truncated at both ends.
FILLER = " ".join(["lorem"] * 40)


def _label(name: str) -> str:
    return name.removesuffix(".html").replace("_", " ").title()


def _write_report(root, name: str, mtime: float, pad: int):
    path = root / name
    keyword = BODY_KEYWORD[name]
    title = f"{_label(name)} Field Map"
    body = ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{title}</title></head><body>"
            f"<p>{FILLER}</p><p>report {keyword}</p><p>{FILLER}</p>"
            "</body></html>")
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


# ── highlight_html (pure) ──────────────────────────────────────────────────


def test_highlight_html_no_query_is_escaped():
    assert highlight_html("a<b & c", None) == "a&lt;b &amp; c"


def test_highlight_html_empty_query_is_escaped():
    assert highlight_html("a<b", "") == "a&lt;b"


def test_highlight_html_wraps_case_insensitive_match():
    assert highlight_html("Alpha report", "alpha") == "<mark>Alpha</mark> report"


def test_highlight_html_wraps_all_occurrences():
    assert highlight_html("cat catalog", "cat") == \
        "<mark>cat</mark> <mark>cat</mark>alog"


def test_highlight_html_escapes_hostile_text_and_query():
    assert highlight_html("a<q", "<") == "a<mark>&lt;</mark>q"


# ── content_snippet (pure) ─────────────────────────────────────────────────


def test_content_snippet_returns_plain_excerpt(bundle):
    snip = content_snippet(bundle, "alpha_report.html", "zebra")
    assert snip is not None
    assert "zebra" in snip
    assert "<" not in snip and ">" not in snip


def test_content_snippet_is_case_insensitive(bundle):
    snip = content_snippet(bundle, "alpha_report.html", "ZEBRA")
    assert snip is not None
    assert "zebra" in snip


def test_content_snippet_none_without_query(bundle):
    assert content_snippet(bundle, "alpha_report.html", None) is None
    assert content_snippet(bundle, "alpha_report.html", "") is None


def test_content_snippet_none_when_keyword_absent(bundle):
    assert content_snippet(bundle, "alpha_report.html", "no-such-word") is None


def test_content_snippet_none_for_unknown_report(bundle):
    assert content_snippet(bundle, "nope.html", "zebra") is None


def test_content_snippet_none_for_path_escape(bundle):
    assert content_snippet(bundle, "../index.html", "zebra") is None


def test_content_snippet_truncates_with_ellipses(bundle):
    snip = content_snippet(bundle, "alpha_report.html", "zebra")
    assert snip is not None
    assert snip.startswith("…") and snip.endswith("…")


def test_content_snippet_window_centres_match(bundle):
    snip = content_snippet(bundle, "alpha_report.html", "zebra", width=20)
    assert snip is not None
    assert "zebra" in snip
    assert snip.startswith("…") and snip.endswith("…")


# ── dashboard_html: content-search snippet ─────────────────────────────────


def test_dashboard_content_search_renders_snippet(bundle):
    page = dashboard_html(bundle, q="zebra", content=True)
    assert 'class="snippet"' in page
    assert "<mark>zebra</mark>" in page
    assert "Alpha Report" in page


def test_dashboard_metadata_search_has_no_snippet(bundle):
    page = dashboard_html(bundle, q="alpha")
    assert "Alpha Report" in page
    assert 'class="snippet"' not in page
    assert "<mark>" not in page


def test_dashboard_content_search_no_snippet_for_metadata_only_hit(bundle):
    page = dashboard_html(bundle, q="html", content=True)
    assert "Gamma Report" in page  # matched via the name, not the body
    assert 'class="snippet"' not in page
    assert "<mark>" not in page


def test_dashboard_snippet_stays_parsable_by_bundle_listings(bundle, tmp_path):
    page = dashboard_html(bundle, q="zebra", content=True)
    outdir = tmp_path / "served"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(page, encoding="utf-8")
    listings = bundle_listings(outdir)
    assert [item["name"] for item in listings] == ["alpha_report.html"]
    assert listings[0]["label"] == "Alpha Report"


# ── report_detail_html: content-search snippet ─────────────────────────────


def test_detail_content_search_renders_snippet(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q="zebra",
                              content=True)
    assert body is not None
    assert 'class="snippet"' in body
    assert "<mark>zebra</mark>" in body


def test_detail_metadata_search_has_no_snippet(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q="alpha")
    assert body is not None
    assert 'class="snippet"' not in body
    assert "<mark>" not in body


# ── HTTP: /api/report/snippet + content-search pages ───────────────────────


def test_route_snippet_returns_json(server):
    status, body = _fetch(
        server, "/api/report/snippet?name=alpha_report.html&q=zebra")
    assert status == 200
    data = json.loads(body)
    assert data["ok"] is True
    assert data["name"] == "alpha_report.html"
    assert data["q"] == "zebra"
    assert "zebra" in data["snippet"]
    assert "<" not in data["snippet"]


def test_route_snippet_missing_name_400(server):
    status, body = _fetch(server, "/api/report/snippet?q=zebra")
    assert status == 400
    assert json.loads(body)["error"] == "missing name"


def test_route_snippet_missing_q_400(server):
    status, body = _fetch(server, "/api/report/snippet?name=alpha_report.html")
    assert status == 400
    assert json.loads(body)["error"] == "missing q"


def test_route_snippet_unknown_report_404(server):
    status, body = _fetch(
        server, "/api/report/snippet?name=nope.html&q=zebra")
    assert status == 404
    assert json.loads(body)["ok"] is False


def test_route_snippet_no_match_is_null(server):
    status, body = _fetch(
        server, "/api/report/snippet?name=alpha_report.html&q=absent")
    assert status == 200
    assert json.loads(body)["snippet"] is None


def test_route_dashboard_content_search_renders_snippet(server):
    status, body = _fetch(server, "/?q=zebra&content=1")
    assert status == 200
    assert 'class="snippet"' in body
    assert "<mark>zebra</mark>" in body


def test_route_dashboard_without_content_has_no_snippet(server):
    status, body = _fetch(server, "/?q=zebra")
    assert status == 200
    assert 'class="snippet"' not in body


def test_route_detail_content_search_renders_snippet(server):
    status, body = _fetch(
        server, "/report/alpha_report.html?q=zebra&content=1")
    assert status == 200
    assert 'class="snippet"' in body
    assert "<mark>zebra</mark>" in body
