"""R100: report neighbourhood / ordering context (Web 呈现).

R91's detail page stepped between reports with bare "previous" / "next" links
that named neither neighbour, and ``/api/report`` returned a single report with
no sense of *where* it sat in the bundle. R100 closes that gap:

* ``report_context()`` -- a pure helper returning a report's 0-based ``index`` and
  the ``total`` within an ordered :func:`report_meta` row list plus its ``prev`` /
  ``next`` neighbours (each summarised as ``{name, label}``, ``None`` at either
  end; ``None`` for the whole block when the report is filtered out);
* the detail page labels its prev / next links with the neighbour's own ``label``;
* ``/api/report`` attaches the same context, computed against the active
  ``q`` / ``sort`` / ``dir`` / ``content`` ordering, as a ``context`` field.

Everything stays purely additive: ``_detail_nav`` keeps its
``(prev_name, next_name)`` contract, the existing ``report`` field is untouched,
and the anchor classes / hrefs are unchanged. No third-party deps.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    _detail_nav,
    query_reports,
    report_context,
    report_detail_html,
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
# index order so a ``sort=matches`` ranking produces a different neighbourhood.
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


# ── report_context (pure) ───────────────────────────────────────────────────


def test_report_context_middle(bundle):
    rows = report_meta(bundle)
    ctx = report_context(rows, "alpha_report.html")
    assert ctx == {
        "index": 2,
        "total": 5,
        "prev": {"name": "epsilon_report.html", "label": "Epsilon Report"},
        "next": {"name": "delta_report.html", "label": "Delta Report"},
    }


def test_report_context_first_has_no_prev(bundle):
    ctx = report_context(report_meta(bundle), "gamma_report.html")
    assert ctx["index"] == 0
    assert ctx["total"] == 5
    assert ctx["prev"] is None
    assert ctx["next"]["name"] == "epsilon_report.html"


def test_report_context_last_has_no_next(bundle):
    ctx = report_context(report_meta(bundle), "beta_report.html")
    assert ctx["index"] == 4
    assert ctx["next"] is None
    assert ctx["prev"]["name"] == "delta_report.html"


def test_report_context_single_row(bundle):
    rows = [report_meta(bundle)[2]]
    ctx = report_context(rows, "alpha_report.html")
    assert ctx == {"index": 0, "total": 1, "prev": None, "next": None}


def test_report_context_unknown_returns_none(bundle):
    assert report_context(report_meta(bundle), "nope.html") is None
    assert report_context([], "alpha_report.html") is None


def test_report_context_follows_query_order(bundle):
    rows = query_reports(report_meta(bundle), sort="name", dir="asc")
    ctx = report_context(rows, "alpha_report.html")
    assert ctx["index"] == 0
    assert ctx["prev"] is None
    assert ctx["next"]["name"] == "beta_report.html"


def test_report_context_matches_detail_nav(bundle):
    rows = query_reports(report_meta(bundle), sort="size", dir="desc")
    for name in INDEX_ORDER:
        ctx = report_context(rows, name)
        prev_name, next_name = _detail_nav(rows, name)
        assert (ctx["prev"] or {}).get("name") == prev_name
        assert (ctx["next"] or {}).get("name") == next_name


# ── detail page: labelled prev / next ───────────────────────────────────────


def test_detail_labels_next_with_neighbour_label(bundle):
    body = report_detail_html(bundle, "gamma_report.html")
    assert "next: Epsilon Report" in body
    assert 'class="detail-next"' in body
    assert 'class="detail-prev"' not in body


def test_detail_labels_prev_and_next(bundle):
    body = report_detail_html(bundle, "alpha_report.html")
    assert "previous: Epsilon Report" in body
    assert "next: Delta Report" in body


def test_detail_first_entry_only_next_label(bundle):
    body = report_detail_html(bundle, "gamma_report.html")
    assert "next: Epsilon Report" in body
    assert "previous" not in body


def test_detail_last_entry_only_prev_label(bundle):
    body = report_detail_html(bundle, "beta_report.html")
    assert "previous: Delta Report" in body
    assert "next" not in body


def test_detail_labels_follow_sort(bundle):
    body = report_detail_html(bundle, "delta_report.html", sort="name", dir="asc")
    assert "previous: Beta Report" in body
    assert "next: Epsilon Report" in body


def test_detail_labels_follow_content_ranking(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q=KEYWORD,
                              sort="matches", dir="desc", content=True)
    assert "previous: Beta Report" in body
    assert "next: Delta Report" in body


def test_detail_label_is_escaped(tmp_path):
    b = _make_escape_bundle(tmp_path)
    body = report_detail_html(b, "alpha_report.html")
    assert "previous: Beta &amp; Co" in body
    body = report_detail_html(b, "beta_report.html")
    assert "next: Alpha &amp; &quot;Co&quot;" in body


# ── /api/report context ─────────────────────────────────────────────────────


def test_api_report_context_default_order(server):
    status, body = _fetch(server, "/api/report?name=gamma_report.html")
    assert status == 200
    data = json.loads(body)
    assert data["context"] == {
        "index": 0,
        "total": 5,
        "prev": None,
        "next": {"name": "epsilon_report.html", "label": "Epsilon Report"},
    }


def test_api_report_context_middle(server):
    status, body = _fetch(server, "/api/report?name=alpha_report.html")
    assert status == 200
    ctx = json.loads(body)["context"]
    assert ctx["index"] == 2
    assert ctx["prev"]["name"] == "epsilon_report.html"
    assert ctx["next"]["name"] == "delta_report.html"


def test_api_report_context_follows_sort_asc(server):
    status, body = _fetch(
        server, "/api/report?name=alpha_report.html&sort=name&dir=asc")
    assert status == 200
    ctx = json.loads(body)["context"]
    assert ctx["index"] == 0
    assert ctx["prev"] is None
    assert ctx["next"]["name"] == "beta_report.html"


def test_api_report_context_follows_sort_desc(server):
    status, body = _fetch(
        server, "/api/report?name=delta_report.html&sort=name&dir=desc")
    assert status == 200
    ctx = json.loads(body)["context"]
    assert ctx["index"] == 2
    assert ctx["prev"]["name"] == "epsilon_report.html"
    assert ctx["next"]["name"] == "beta_report.html"


def test_api_report_context_follows_content_ranking(server):
    status, body = _fetch(
        server, f"/api/report?name=alpha_report.html&q={KEYWORD}"
                "&sort=matches&dir=desc&content=1")
    assert status == 200
    ctx = json.loads(body)["context"]
    assert ctx["index"] == 2
    assert ctx["prev"]["name"] == "beta_report.html"
    assert ctx["next"]["name"] == "delta_report.html"


def test_api_report_context_single_match(server):
    status, body = _fetch(server, "/api/report?name=gamma_report.html&q=gamma")
    assert status == 200
    ctx = json.loads(body)["context"]
    assert ctx == {"index": 0, "total": 1, "prev": None, "next": None}


def test_api_report_context_null_when_filtered_out(server):
    status, body = _fetch(server, "/api/report?name=gamma_report.html&q=epsilon")
    assert status == 200
    data = json.loads(body)
    assert data["context"] is None
    assert data["report"]["name"] == "gamma_report.html"


def test_api_report_field_unchanged(server):
    status, body = _fetch(
        server, "/api/report?name=gamma_report.html&sort=name&dir=asc")
    assert status == 200
    data = json.loads(body)
    assert data["report"]["name"] == "gamma_report.html"
    assert data["report"]["index"] == 0
    assert data["report"]["title"] == "Gamma Report Field Map"
    assert data["ok"] is True
