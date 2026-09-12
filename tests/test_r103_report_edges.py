"""R103: first / last ordering edges (Web 呈现).

R100/R101/R102 gave the detail page labelled prev / next links and a
"report N of M" readout, but navigation could only move *one* report at a time:
reaching the first or last report of a large bundle meant clicking through every
neighbour. R103 closes that reach gap:

* ``report_edges()`` -- a pure helper returning the ``first`` / ``last`` rows of
  an ordered :func:`report_meta` row list (each summarised as ``{name, label}``,
  ``None`` when the list is empty);
* the detail page renders ``detail-first`` / ``detail-last`` jump links to the
  ends of the active ``q``/``sort``/``dir``/``content`` ordering;
* ``/api/report`` attaches the same two jump targets as an ``edges`` field.

Everything stays purely additive: ``report_context`` is unchanged, the jump
links carry distinct classes and are only added when the report is in the
ordering and not already at that end, and the ``prev`` / ``next`` links are
untouched. No third-party deps.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import pytest
from fv.web import report_edges as packaged_report_edges
from fv.web.report_server import (
    query_reports,
    report_context,
    report_detail_html,
    report_edges,
    report_meta,
    serve_bundle,
)

INDEX_ORDER = ("gamma_report.html", "epsilon_report.html", "alpha_report.html",
               "delta_report.html", "beta_report.html")

LABELS = {
    "gamma_report.html": "Gamma Report",
    "epsilon_report.html": "Epsilon Report",
    "alpha_report.html": "Alpha Report",
    "delta_report.html": "Delta Report",
    "beta_report.html": "Beta Report",
}

# Body occurrences of KEYWORD per report, deliberately *not* aligned with the
# index order so a ``sort=matches`` ranking produces different edges.
KEYWORD = "needle"
BODY_COUNTS = {
    "gamma_report.html": 1,
    "epsilon_report.html": 5,
    "alpha_report.html": 3,
    "delta_report.html": 2,
    "beta_report.html": 4,
}


def _report_body(name: str, count: int) -> str:
    title = f"{LABELS[name]} Field Map"
    hits = "".join(
        f"<p>segment {i} sees the {KEYWORD}</p>" for i in range(count))
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<title>{title}</title></head><body>{hits}</body></html>")


def _write_index(b, names, labels):
    items = "".join(
        f'<li><a href="{n}">{labels[n]}</a></li>' for n in names)
    (b / "index.html").write_text(
        f"<!doctype html><html><head><title>test bundle</title></head>"
        f"<body><ul>{items}</ul></body></html>", encoding="utf-8")


def _make_bundle(tmp_path):
    b = tmp_path / "b"
    b.mkdir(exist_ok=True)
    for name in INDEX_ORDER:
        (b / name).write_text(
            _report_body(name, BODY_COUNTS[name]), encoding="utf-8")
    _write_index(b, INDEX_ORDER, LABELS)
    return b


def _make_single_bundle(tmp_path):
    b = tmp_path / "one"
    b.mkdir(exist_ok=True)
    labels = {"only_report.html": "Only Report"}
    (b / "only_report.html").write_text(
        "<!doctype html><html><head><title>Only</title></head>"
        "<body>report</body></html>", encoding="utf-8")
    _write_index(b, ("only_report.html",), labels)
    return b


def _make_escape_bundle(tmp_path):
    b = tmp_path / "esc"
    b.mkdir(exist_ok=True)
    order = ("beta_report.html", "alpha_report.html")
    labels = {"beta_report.html": "Beta & Co",
              "alpha_report.html": 'Alpha & "Co"'}
    for name in order:
        (b / name).write_text(
            f"<!doctype html><html><head><title>{name}</title></head>"
            "<body>report</body></html>", encoding="utf-8")
    _write_index(b, order, labels)
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


def _href_of(body: str, cls: str):
    match = re.search(rf'<a class="{cls}" href="([^"]*)">', body)
    return match.group(1) if match else None


# ── report_edges (pure) ─────────────────────────────────────────────────────


def test_report_edges_default_order(bundle):
    assert report_edges(report_meta(bundle)) == {
        "first": {"name": "gamma_report.html", "label": "Gamma Report"},
        "last": {"name": "beta_report.html", "label": "Beta Report"},
    }


def test_report_edges_follows_sort_asc(bundle):
    rows = query_reports(report_meta(bundle), sort="name", dir="asc")
    edges = report_edges(rows)
    assert edges["first"]["name"] == "alpha_report.html"
    assert edges["last"]["name"] == "gamma_report.html"


def test_report_edges_follows_sort_desc(bundle):
    rows = query_reports(report_meta(bundle), sort="name", dir="desc")
    edges = report_edges(rows)
    assert edges["first"]["name"] == "gamma_report.html"
    assert edges["last"]["name"] == "alpha_report.html"


def test_report_edges_follows_content_ranking(bundle):
    rows = query_reports(report_meta(bundle), q=KEYWORD, sort="matches",
                         dir="desc", content=True, bundle_dir=bundle)
    edges = report_edges(rows)
    assert edges["first"]["name"] == "epsilon_report.html"
    assert edges["last"]["name"] == "gamma_report.html"


def test_report_edges_shape(bundle):
    edges = report_edges(report_meta(bundle))
    assert set(edges) == {"first", "last"}
    for end in edges.values():
        assert set(end) == {"name", "label"}


def test_report_edges_empty_returns_none_ends():
    assert report_edges([]) == {"first": None, "last": None}


def test_report_edges_single_row_ends_match(bundle):
    rows = [report_meta(bundle)[2]]
    edges = report_edges(rows)
    assert edges["first"] == edges["last"]
    assert edges["first"]["name"] == "alpha_report.html"


def test_report_edges_exported_from_package(bundle):
    assert packaged_report_edges is report_edges
    assert packaged_report_edges(report_meta(bundle))["last"]["name"] == \
        "beta_report.html"


# ── detail page: first / last jumps ─────────────────────────────────────────


def test_detail_middle_has_first_and_last(bundle):
    body = report_detail_html(bundle, "alpha_report.html")
    assert "first: Gamma Report" in body
    assert "last: Beta Report" in body
    assert _href_of(body, "detail-first") == "/report/gamma_report.html?"
    assert _href_of(body, "detail-last") == "/report/beta_report.html?"


def test_detail_first_entry_has_no_first_jump(bundle):
    body = report_detail_html(bundle, "gamma_report.html")
    assert 'class="detail-first"' not in body
    assert "first: " not in body
    assert _href_of(body, "detail-last") == "/report/beta_report.html?"


def test_detail_last_entry_has_no_last_jump(bundle):
    body = report_detail_html(bundle, "beta_report.html")
    assert 'class="detail-last"' not in body
    assert "last: " not in body
    assert _href_of(body, "detail-first") == "/report/gamma_report.html?"


def test_detail_single_report_has_no_jumps(tmp_path):
    b = _make_single_bundle(tmp_path)
    body = report_detail_html(b, "only_report.html")
    assert 'class="detail-first"' not in body
    assert 'class="detail-last"' not in body


def test_detail_jumps_follow_sort(bundle):
    body = report_detail_html(bundle, "delta_report.html", sort="name",
                              dir="asc")
    assert _href_of(body, "detail-first") == "/report/alpha_report.html?sort=name"
    assert (_href_of(body, "detail-last")
            == "/report/gamma_report.html?sort=name")


def test_detail_jumps_follow_content_ranking(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q=KEYWORD,
                              sort="matches", dir="desc", content=True)
    assert (_href_of(body, "detail-first")
            == "/report/epsilon_report.html?q=needle&amp;sort=matches"
               "&amp;dir=desc&amp;content=1")
    assert (_href_of(body, "detail-last")
            == "/report/gamma_report.html?q=needle&amp;sort=matches"
               "&amp;dir=desc&amp;content=1")


def test_detail_jumps_preserve_content_flag(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q=KEYWORD,
                              sort="matches", content=True)
    assert "content=1" in _href_of(body, "detail-first")
    assert "content=1" in _href_of(body, "detail-last")


def test_detail_jumps_preserve_full_flag(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q=KEYWORD,
                              sort="matches", content=True, full=True)
    assert (_href_of(body, "detail-first")
            == "/report/epsilon_report.html?q=needle&amp;sort=matches"
               "&amp;dir=desc&amp;content=1&amp;full=1")
    assert (_href_of(body, "detail-last")
            == "/report/gamma_report.html?q=needle&amp;sort=matches"
               "&amp;dir=desc&amp;content=1&amp;full=1")


def test_detail_first_before_prev_and_last_after_next(bundle):
    body = report_detail_html(bundle, "alpha_report.html")
    positions = [body.index('class="detail-first"'),
                 body.index('class="detail-prev"'),
                 body.index('class="detail-next"'),
                 body.index('class="detail-last"')]
    assert positions == sorted(positions)


def test_detail_jump_labels_are_escaped(tmp_path):
    b = _make_escape_bundle(tmp_path)
    body = report_detail_html(b, "alpha_report.html")
    assert "first: Beta &amp; Co" in body
    body = report_detail_html(b, "beta_report.html")
    assert "last: Alpha &amp; &quot;Co&quot;" in body


def test_detail_jumps_absent_when_filtered_out(bundle):
    body = report_detail_html(bundle, "gamma_report.html", q="epsilon")
    assert 'class="detail-first"' not in body
    assert 'class="detail-last"' not in body
    assert 'class="report-position"' not in body
    assert 'class="crumbs"' in body


# ── backward compatibility ──────────────────────────────────────────────────


def test_detail_prev_next_unchanged(bundle):
    body = report_detail_html(bundle, "alpha_report.html")
    assert "previous: Epsilon Report" in body
    assert "next: Delta Report" in body
    assert 'class="detail-prev"' in body
    assert 'class="detail-next"' in body


def test_detail_nav_and_crumbs_classes_unchanged(bundle):
    body = report_detail_html(bundle, "alpha_report.html")
    assert '<p class="detail-nav">' in body
    assert '<p class="crumbs">' in body
    assert '<span class="report-position">report 3 of 5</span>' in body


def test_report_context_has_no_edges_key(bundle):
    ctx = report_context(report_meta(bundle), "alpha_report.html")
    assert set(ctx) == {"index", "total", "prev", "next"}


# ── /api/report edges ───────────────────────────────────────────────────────


def test_api_edges_default_order(server):
    status, body = _fetch(server, "/api/report?name=alpha_report.html")
    assert status == 200
    assert json.loads(body)["edges"] == {
        "first": {"name": "gamma_report.html", "label": "Gamma Report"},
        "last": {"name": "beta_report.html", "label": "Beta Report"},
    }


def test_api_edges_follows_sort(server):
    status, body = _fetch(
        server, "/api/report?name=alpha_report.html&sort=name&dir=asc")
    assert status == 200
    edges = json.loads(body)["edges"]
    assert edges["first"]["name"] == "alpha_report.html"
    assert edges["last"]["name"] == "gamma_report.html"


def test_api_edges_follows_content_ranking(server):
    status, body = _fetch(
        server, f"/api/report?name=alpha_report.html&q={KEYWORD}"
                "&sort=matches&dir=desc&content=1")
    assert status == 200
    edges = json.loads(body)["edges"]
    assert edges["first"]["name"] == "epsilon_report.html"
    assert edges["last"]["name"] == "gamma_report.html"


def test_api_edges_populated_when_context_null(server):
    status, body = _fetch(server, "/api/report?name=gamma_report.html&q=epsilon")
    assert status == 200
    data = json.loads(body)
    assert data["context"] is None
    assert data["edges"] == {
        "first": {"name": "epsilon_report.html", "label": "Epsilon Report"},
        "last": {"name": "epsilon_report.html", "label": "Epsilon Report"},
    }


def test_api_edges_shape(server):
    status, body = _fetch(server, "/api/report?name=alpha_report.html")
    assert status == 200
    edges = json.loads(body)["edges"]
    assert set(edges) == {"first", "last"}
    for end in edges.values():
        assert set(end) == {"name", "label"}
