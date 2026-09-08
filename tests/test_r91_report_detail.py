"""R91: single-report detail view + detail JSON API (Web 呈现)."""

import json
import os
import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    _detail_nav,
    report_detail,
    report_detail_html,
    serve_bundle,
)

INDEX_ORDER = ("gamma_report.html", "epsilon_report.html", "alpha_report.html",
               "delta_report.html", "beta_report.html")


def _write_report(root, name: str, title: str, mtime: float, pad: int):
    path = root / name
    body = (f"<!doctype html><html><head><title>{title}</title></head>"
            "<body>report</body></html>")
    path.write_text(body, encoding="utf-8")
    with open(path, "ab") as fh:
        fh.write(b"x" * pad)
    os.utime(path, (mtime, mtime))
    return path


def _label(name: str) -> str:
    return name.removesuffix(".html").replace("_", " ").title()


def _make_bundle(tmp_path):
    b = tmp_path / "b"
    b.mkdir(exist_ok=True)
    for i, name in enumerate(INDEX_ORDER):
        _write_report(b, name, f"{_label(name)} Field Map",
                      1_700_000_000 + i, 100 * i)
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


# ── report_detail (pure) ────────────────────────────────────────────────────


def test_report_detail_returns_row_with_index(bundle):
    entry = report_detail(bundle, "gamma_report.html")
    assert entry is not None
    assert entry["name"] == "gamma_report.html"
    assert entry["label"] == "Gamma Report"
    assert entry["title"] == "Gamma Report Field Map"
    assert entry["index"] == 0
    assert entry["size_bytes"] > 0


def test_report_detail_unknown_returns_none(bundle):
    assert report_detail(bundle, "nope_report.html") is None


def test_report_detail_blocks_path_escape(bundle):
    assert report_detail(bundle, "../index.html") is None


# ── _detail_nav (pure) ──────────────────────────────────────────────────────


def test_detail_nav_middle():
    rows = [{"name": n} for n in
            ("alpha_report.html", "beta_report.html", "delta_report.html",
             "epsilon_report.html", "gamma_report.html")]
    assert _detail_nav(rows, "delta_report.html") == ("beta_report.html",
                                                      "epsilon_report.html")
    assert _detail_nav(rows, "alpha_report.html") == (None, "beta_report.html")
    assert _detail_nav(rows, "gamma_report.html") == ("epsilon_report.html",
                                                      None)
    assert _detail_nav(rows, "unknown.html") == (None, None)


# ── report_detail_html (pure) ───────────────────────────────────────────────


def test_detail_html_heading_meta_and_open_link(bundle):
    body = report_detail_html(bundle, "gamma_report.html")
    assert body is not None
    assert "<h1>Gamma Report</h1>" in body
    assert 'class="crumbs"' in body
    assert 'class="report-meta"' in body
    assert "Gamma Report Field Map" in body
    assert 'class="report-open"' in body
    assert 'href="gamma_report.html"' in body


def test_detail_html_unknown_returns_none(bundle):
    assert report_detail_html(bundle, "nope_report.html") is None


def test_detail_html_index_order_navigation(bundle):
    body = report_detail_html(bundle, "gamma_report.html")
    assert 'class="detail-next"' in body
    assert "epsilon_report.html" in body
    assert 'class="detail-prev"' not in body


def test_detail_html_name_sort_navigation(bundle):
    body = report_detail_html(bundle, "gamma_report.html", sort="name", dir="asc")
    assert 'class="detail-prev"' in body
    assert "epsilon_report.html" in body
    assert 'class="detail-next"' not in body


def test_detail_html_backlink_preserves_query(bundle):
    body = report_detail_html(bundle, "alpha_report.html", q="field",
                              sort="name", dir="asc")
    assert 'href="/?q=field&amp;sort=name"' in body


# ── HTTP routes ─────────────────────────────────────────────────────────────


def test_route_api_report_returns_json(server):
    status, body = _fetch(server, "/api/report?name=gamma_report.html")
    assert status == 200
    data = json.loads(body)
    assert data["ok"] is True
    assert data["report"]["name"] == "gamma_report.html"
    assert data["report"]["index"] == 0
    assert data["report"]["title"] == "Gamma Report Field Map"


def test_route_api_report_missing_name_400(server):
    status, body = _fetch(server, "/api/report")
    assert status == 400
    assert json.loads(body)["ok"] is False
    assert json.loads(body)["error"] == "missing name"


def test_route_api_report_unknown_404(server):
    status, body = _fetch(server, "/api/report?name=nope.html")
    assert status == 404
    assert json.loads(body)["ok"] is False


def test_route_detail_page(server):
    status, body = _fetch(server, "/report/gamma_report.html")
    assert status == 200
    assert "<h1>Gamma Report</h1>" in body
    assert "dashboard" in body


def test_route_detail_unknown_404(server):
    status, body = _fetch(server, "/report/nope_report.html")
    assert status == 404


def test_route_detail_preserves_sort_for_nav(server):
    status, body = _fetch(server, "/report/gamma_report.html?sort=name&dir=asc")
    assert status == 200
    assert "epsilon_report.html" in body
    assert 'class="detail-prev"' in body
    assert 'class="detail-next"' not in body


def test_route_detail_next_for_first_entry(server):
    status, body = _fetch(server, "/report/alpha_report.html?sort=name&dir=asc")
    assert status == 200
    assert "beta_report.html" in body
    assert 'class="detail-next"' in body
    assert 'class="detail-prev"' not in body
