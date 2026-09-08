"""R92: report content preview embedded in the detail page (Web 呈现).

R91 gave the report family a dashboard-context detail page at ``/report/<name>``
and an ``/api/report`` JSON endpoint, but the page only noted the raw file via a
relative "open report" link -- the report body was never shown in context, and
that relative link resolved back to the detail page itself. R92 deepens
``fv/web/report_server.py``: ``report_content()`` exposes a report's raw HTML
text (path-safe, ``None`` on unknown / escape / unreadable) as the machine
counterpart to ``report_detail()``, and ``report_detail_html()`` embeds the
report inline (an ``<iframe class="report-frame">`` referencing the raw report
at its absolute path) so a browser user pages through a bundle with previous /
next and reads each report without clicking out. The "open report" link now
targets the absolute raw path, and the preview is skipped when the report is
unreadable. This suite exercises the pure content helper, the embedded preview
in the detail page (and its absence for an unreadable report), and the live
``/report/<name>`` and ``/<report>.html`` routes that back the iframe -- no
third-party deps.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest
from fv.web.report_server import (
    report_content,
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


def _make_ghost_bundle(tmp_path):
    """A bundle whose index lists a report file that was never written."""
    b = tmp_path / "b"
    b.mkdir(exist_ok=True)
    _write_report(b, "gamma_report.html", "Gamma Report Field Map",
                  1_700_000_000, 100)
    (b / "index.html").write_text(
        "<!doctype html><html><head><title>ghost bundle</title></head>"
        "<body><ul>"
        '<li><a href="gamma_report.html">Gamma Report</a></li>'
        '<li><a href="ghost_report.html">Ghost Report</a></li>'
        "</ul></body></html>", encoding="utf-8")
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


# ── report_content (pure) ───────────────────────────────────────────────────


def test_report_content_returns_report_text(bundle):
    text = report_content(bundle, "gamma_report.html")
    assert text is not None
    assert "<body>report</body>" in text
    assert "Gamma Report Field Map" in text


def test_report_content_unknown_returns_none(bundle):
    assert report_content(bundle, "nope_report.html") is None


def test_report_content_blocks_path_escape(bundle):
    assert report_content(bundle, "../index.html") is None


def test_report_content_missing_file_returns_none(tmp_path):
    bundle = _make_ghost_bundle(tmp_path)
    assert report_content(bundle, "ghost_report.html") is None


# ── report_detail_html: embedded preview ────────────────────────────────────


def test_detail_html_embeds_report_frame(bundle):
    body = report_detail_html(bundle, "alpha_report.html")
    assert body is not None
    assert 'class="report-frame"' in body
    assert 'src="/alpha_report.html"' in body
    assert "alpha_report.html" in body


def test_detail_html_open_link_targets_raw_absolute(bundle):
    body = report_detail_html(bundle, "alpha_report.html")
    assert 'class="report-open"' in body
    assert 'href="/alpha_report.html"' in body


def test_detail_html_keeps_nav_with_preview(bundle):
    body = report_detail_html(bundle, "alpha_report.html", sort="name", dir="asc")
    assert 'class="report-frame"' in body
    assert 'class="detail-next"' in body
    assert "beta_report.html" in body


def test_detail_html_skips_frame_when_unreadable(tmp_path):
    bundle = _make_ghost_bundle(tmp_path)
    body = report_detail_html(bundle, "ghost_report.html")
    assert body is not None
    assert 'class="report-frame"' not in body
    assert 'class="report-open"' in body


# ── HTTP routes ─────────────────────────────────────────────────────────────


def test_route_detail_page_embeds_report_frame(server):
    status, body = _fetch(server, "/report/alpha_report.html")
    assert status == 200
    assert 'class="report-frame"' in body
    assert 'src="/alpha_report.html"' in body


def test_route_raw_report_served_for_iframe(server):
    status, body = _fetch(server, "/alpha_report.html")
    assert status == 200
    assert "<body>report</body>" in body
