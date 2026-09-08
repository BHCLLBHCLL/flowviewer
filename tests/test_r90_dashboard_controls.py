"""R90 tests: interactive dashboard controls (section 8.85).

R88 made ``/`` and ``/api/meta`` queryable / re-rankable with ``q``/``sort``/``dir``
and R89 windowed them with ``limit``/``offset``, but a browser user still had to
hand-edit the URL to search, re-rank or page through a bundle. R90 makes ``/``
interactive without JavaScript: ``dashboard_html`` emits a dependency-free ``GET``
form (``<form class="dashboard-controls">``) whose ``q`` / ``sort`` / ``dir`` /
``limit`` controls reflect the current query and, when submitted, drive the same
report_server routes. This suite exercises the control form, the option-selection
reflection, the HTML-escaping of a hostile ``q``, the bundle_listings-parsability
of a control-bearing dashboard, and the live ``/?q=&sort=&dir=&limit=`` interaction
-- no third-party deps.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.request
from pathlib import Path

from fv.web.report_server import (
    _controls_html,
    bundle_listings,
    dashboard_html,
    serve_bundle,
)

M_TIME = {
    "alpha": 1000000000.0,  # 2001-09-09
    "beta": 1100000000.0,  # 2004-11-09
    "gamma": 1200000000.0,  # 2008-01-10
    "delta": 1300000000.0,  # 2011-03-12
    "epsilon": 1400000000.0,  # 2014-05-13
}
INDEX_ORDER = ["gamma", "epsilon", "alpha", "delta", "beta"]
PAD = {"alpha": 10, "beta": 50, "gamma": 100, "delta": 200, "epsilon": 400}
TASK = "Field Map"
CAP = "analysis"


def _write_report(dirpath: Path, stem: str) -> Path:
    out = dirpath / f"{stem}_report.html"
    out.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{stem.title()} {CAP}</title></head><body>{stem.title()} {CAP}"
        f"{'x' * PAD[stem]}</body></html>\n",
        encoding="utf-8")
    return out


def _make_bundle(dirpath: Path) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    paths = {stem: _write_report(dirpath, stem) for stem in M_TIME}
    for stem, path in paths.items():
        mt = M_TIME[stem]
        os.utime(path, (mt, mt))
    lis = "".join(
        f'<li><a href="{stem}_report.html">{stem.title()} {TASK}</a></li>'
        for stem in INDEX_ORDER)
    (dirpath / "index.html").write_text(
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">"
        "<title>paginated bundle</title></head><body>"
        "<h1>paginated bundle</h1>"
        f"<p>{len(INDEX_ORDER)} report(s) generated.</p>"
        f"<ul>{lis}</ul></body></html>\n", encoding="utf-8")
    return dirpath


def _http(method, port, path):
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:  # non-2xx is still a response
        return exc.code, exc.read()


def _shutdown(server, thread):
    try:
        server.shutdown()
    except Exception:  # pragma: no cover
        pass
    try:
        server.server_close()
    except Exception:  # pragma: no cover
        pass
    if thread and thread.is_alive():
        thread.join(timeout=2.0)


# ── _controls_html: pure form building ─────────────────────────────────────


def test_controls_form_defaults_to_index_order():
    """A bare dashboard emits a form defaulting to index / asc / all pages."""
    form = _controls_html(None, None, "asc", None)
    assert 'class="dashboard-controls"' in form
    assert 'method="get"' in form and 'action="/"' in form
    assert 'name="q" value=""' in form
    assert 'name="sort"' in form and 'value="" selected' in form
    assert 'name="dir"' in form and 'value="asc" selected' in form
    assert 'name="limit"' in form and 'value="" selected' in form


def test_controls_form_reflects_current_query():
    """The form controls are pre-selected / pre-filled to the current query."""
    form = _controls_html("flow", "size", "desc", 25)
    assert 'name="q" value="flow"' in form
    assert 'value="size" selected' in form
    assert 'value="desc" selected' in form
    assert 'value="25" selected' in form
    assert 'value="alpha"' not in form  # not a real option


def test_controls_form_lists_all_sort_keys_and_page_sizes():
    """Every sortable key and page size appears as a selectable option."""
    form = _controls_html(None, None, "asc", None)
    for key in ("name", "label", "title", "size", "mtime"):
        assert f'value="{key}"' in form
    for size in ("10", "25", "50", "100"):
        assert f'value="{size}"' in form


def test_controls_form_escapes_hostile_q():
    """An attacker-typed q is HTML-escaped, never injected raw."""
    form = _controls_html("a<b>&\"c", None, "asc", None)
    assert "<b>" not in form
    assert "&lt;b&gt;" in form


# ── dashboard_html: control-bearing page ───────────────────────────────────


def test_dashboard_html_embeds_controls(tmp_path):
    """dashboard_html always renders the controls form above the list."""
    page = dashboard_html(_make_bundle(tmp_path / "b"))
    assert 'class="dashboard-controls"' in page
    assert 'name="q" value=""' in page
    assert "Gamma Field Map" in page  # index order preserved by default


def test_dashboard_html_controls_reflect_query_after_apply(tmp_path):
    """Applying q/sort/dir/limit via the form reflects in the served page."""
    page = dashboard_html(_make_bundle(tmp_path / "b"), limit=2,
                          q="eps", sort="name", dir="asc")
    assert 'value="eps"' in page
    assert 'value="name" selected' in page
    assert 'value="asc" selected' in page
    assert 'value="2" selected' not in page  # 2 is not a preset page size
    assert "Epsilon Field Map" in page
    assert "Gamma Field Map" not in page  # only the eps match is rendered


def test_dashboard_html_controls_paginate_with_form(tmp_path):
    """With a limit the form + pager coexist and head to the same query."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle, q="field", sort="name", dir="asc", limit=2)
    assert 'class="dashboard-controls"' in page
    assert 'class="pagination"' in page
    assert "showing 1–2 of 5" in page


def test_dashboard_html_controls_stay_parsable_by_bundle_listings(tmp_path):
    """The controls form must not be mistaken for a report anchor."""
    bundle = _make_bundle(tmp_path / "b")
    page = dashboard_html(bundle, limit=2)
    outdir = tmp_path / "served"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(page, encoding="utf-8")
    listings = bundle_listings(outdir)
    assert [item["name"] for item in listings] == [
        "gamma_report.html", "epsilon_report.html"]
    assert all("pager" not in item["name"] for item in listings)
    assert all("apply" not in item["name"] for item in listings)


# ── HTTP interaction ───────────────────────────────────────────────────────


def test_serve_dashboard_controls_visible(tmp_path):
    """/ carries the interactive controls form (GET, index default)."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, data = _http("GET", server.port, "/")
        text = data.decode("utf-8")
        assert 'class="dashboard-controls"' in text
        assert 'name="q" value=""' in text
        assert 'name="limit"' in text
    finally:
        _shutdown(server, thread)


def test_serve_dashboard_query_via_form_params(tmp_path):
    """The form params (q/sort/dir/limit) drive / the same as the URL."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, data = _http("GET", server.port, "/?q=eps&sort=name&limit=1")
        text = data.decode("utf-8")
        assert "Epsilon Field Map" in text
        assert 'value="eps"' in text
        assert "showing 1–1 of 1" in text
    finally:
        _shutdown(server, thread)


def test_serve_dashboard_controls_escape_q(tmp_path):
    """A hostile q in the URL is escaped in the echoed form value."""
    bundle = _make_bundle(tmp_path / "b")
    server, thread = serve_bundle(bundle, port=0, in_thread=True)
    try:
        status, data = _http("GET", server.port, "/?q=<b>x</b>")
        text = data.decode("utf-8")
        assert "<b>xml" not in text
        assert "&lt;b&gt;" in text
    finally:
        _shutdown(server, thread)
