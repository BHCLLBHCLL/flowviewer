"""R82/R86: headless HTTP service for report-family bundles (R64-R81).

``run_report_bundle`` / ``write_report_index`` / ``export_report_bundle``
(``fv.gui.analysis``) produce a bundle directory of self-contained single-file
HTML reports plus an ``index.html`` linking them by basename. R32
(:mod:`fv.web.server`) serves only the R31 *streaming CGNS* surface; it cannot
browse or share a report bundle. This module closes that gap by mounting a
bundle directory on a stdlib ``ThreadingHTTPServer`` -- no GUI, no third-party
dependencies -- so the report family can be opened, shared and downloaded from
any browser, in the R30 headless close-out spirit.

Endpoints:

* ``GET /``                     -> metadata dashboard (report label + title +
  size + mtime; ``/index.html`` stays the untouched bundle index file)
* ``GET /index.html``           -> bundle index page (generated if absent)
* ``GET /api/list``             -> JSON report listing (name + human label)
* ``GET /api/meta``             -> JSON per-report metadata + aggregate summary
  (label/title/size/mtime)
* ``GET /api/summary``          -> JSON bundle overview (count / total size /
  generated span)
* ``GET /api/bundle.zip``       -> download the whole bundle as an archive
* ``GET /api/report?name=<n>``  -> JSON single-report metadata (name / label /
  title / size / mtime / index)
* ``GET /api/report/content?name=<n>`` -> JSON single-report content (raw HTML
  text; 400 on a missing name, 404 on unknown / unreadable) (R93)
* ``GET /api/report/snippet?name=<n>&q=<q>`` -> JSON plain-text excerpts of a
  report body around every ``q`` match (``count`` + ``snippets`` list, ``snippet``
  = the first or ``null``; 400 on a missing name / q, 404 on unknown) (R94/R95)
* ``GET /<report>.html``        -> a single report (path-traversal safe)
* ``GET /report/<name>``        -> dashboard-context detail page for one report
  (back link, metadata, open link, embedded report preview, prev/next
  navigation) (R91/R92)

R86 deepens the web presentation: ``/`` is no longer a bare ``<ul>`` of links but
a live dashboard built from ``report_meta`` (report's own ``<title>`` plus
``os.stat`` size / mtime), and ``/api/meta`` exposes that same metadata as JSON.
R87 adds a bundle overview: ``bundle_summary`` aggregates the per-report metadata
into a count / total size / generated span, the dashboard renders it as a summary
block, and ``/api/meta`` (plus the new ``/api/summary``) exposes it machine-
readably. R88 makes both ``/`` and ``/api/meta`` queryable/re-rankable via
``q`` / ``sort`` / ``dir``. R89 adds ``limit`` / ``offset`` windowing so a large
bundle is browsable in pages -- ``/`` renders a pager (previous / next, preserving
``q``/``sort``/``dir``) and ``/api/meta`` returns ``total`` / ``offset`` / ``limit``
alongside the page. R90 makes ``/`` interactive without JavaScript: ``dashboard_html``
emits a dependency-free ``GET`` form (``<form class="dashboard-controls">``) whose
``q`` / ``sort`` / ``dir`` / ``limit`` controls drive the query, so a browser user
can search / re-rank / page through a bundle without hand-editing the URL. R91
closes two Web-呈现 gaps: clicking a report lands on the raw file with no bundle
context, and there is no machine way to fetch a single report's metadata
(``/api/meta`` always returns the whole list). It adds ``/report/<name>``, a
dashboard-context detail page (back link that preserves ``q``/``sort``/``dir``,
the report's metadata, an "open report" link and previous / next report
navigation within the current query ordering), plus ``/api/report?name=``, a
JSON single-report metadata endpoint. R92 closes the last Web-呈现 gap in the
detail view: the detail page only linked to the raw file, so the report body
was never visible in context. It embeds the report content inline via an
``<iframe class="report-frame">`` referencing the raw report at its absolute
path, so a browser user pages through a bundle with previous / next and reads
each report without clicking out (the "open report" link now targets the
absolute raw path instead of a relative one that resolved back to the page
itself). It also adds ``report_content()``, a pure path-safe helper returning
the report's raw HTML text, as the machine counterpart to ``report_detail()``.
R93 closes the last Web-呈现 content gap: ``/``, ``/api/meta`` and
``/report/<name>`` could only search a report's name / label / title, so a user
typing a keyword found *inside* a report's body got no matches, and there was no
machine way to fetch a single report's content over HTTP. It deepens
``query_reports`` with an opt-in ``content=True`` mode (plus a ``bundle_dir``
to read bodies) so ``q`` also matches the report body text, threads a
``content=1`` flag through the dashboard, its controls form and the pager /
detail navigation (so a content-mode query survives paging and prev / next),
and adds
``/api/report/content?name=``, the JSON counterpart to ``/api/report`` that
returns a report's raw HTML text.
R94 closes the last Web-呈现 search-usability gap: a content search (R93) can
now match a report's body, but the dashboard / detail pages gave no clue *where*
the match lived -- a body-only hit looked identical to a title hit. It adds
``content_snippet()``, a pure helper returning a short plain-text excerpt of a
report body centred on a ``q`` match (HTML tags stripped, whitespace collapsed,
``…`` when truncated; ``None`` when ``q`` is empty / absent or the body is
unreadable), and ``highlight_html()``, which HTML-escapes text and wraps each
case-insensitive ``q`` match in ``<mark>``. When a content search is active the
dashboard renders a ``<li class="snippet">`` excerpt under each matched report
and the detail page renders a ``<p class="snippet">`` excerpt, so a browser user
sees *why* a report matched; ``/api/report/snippet?name=&q=`` exposes the same
excerpt machine-readably. The snippets are purely additive (existing report
anchors are untouched, so ``bundle_listings`` stays parseable and the metadata
search output is unchanged).
R95 closes the last Web-呈现 snippet gap: R94's excerpt showed only the *first*
body match, so a report where the term recurs gave no sense of how many matches
there are or where the rest are. It adds ``content_snippets()``, a pure helper
returning one excerpt per non-overlapping body match (overlapping windows merged,
optionally capped by ``limit``), reimplements ``content_snippet()`` as its first
element (so R94 behaviour is unchanged), renders one ``<li class="snippet">`` /
``<p class="snippet">`` per match on the dashboard / detail pages (capped at
``_MAX_SNIPPETS``, with an "… and N more match(es)" note when the rest are
collapsed), and extends ``/api/report/snippet?name=&q=`` with ``count`` and a
``snippets`` list (``snippet`` stays the first excerpt for backward
compatibility). Everything stays purely additive.
No third-party dependencies are added.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import tempfile
import threading
import urllib.parse
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

VERSION = "1.0.0"
_DEFAULT_TITLE = "flowviewer analysis bundle"
_HTML_SUFFIXES = (".html", ".htm")

# Most content-search match excerpts rendered per report on the dashboard / detail
# pages before collapsing the rest into a "… and N more" note (R95).
_MAX_SNIPPETS = 5

# ``report_index_html`` emits one `<li><a href="X">label</a></li>` per report.
_ITEM_RE = re.compile(r'<li>\s*<a\s+href="([^"]+)"[^>]*>(.*?)</a>\s*</li>',
                      re.S)


# ── helpers ────────────────────────────────────────────────────────────────


def _send_json(handler: BaseHTTPRequestHandler, obj, status: int = 200) -> None:
    body = json.dumps(obj).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler: BaseHTTPRequestHandler, status: int, msg: str) -> None:
    _send_json(handler, {"ok": False, "error": msg}, status)


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def highlight_html(text: str, q: Optional[str]) -> str:
    """HTML-escaped *text* with each case-insensitive ``q`` match in ``<mark>`` (R94).

    Returns plain HTML-escaped ``text`` when ``q`` is empty, so a caller without
    a query renders exactly as before. Every non-overlapping occurrence is marked
    in order, and each unmarked / marked piece is escaped separately, so a
    hostile ``q`` or text cannot inject markup.
    """
    if not q:
        return html.escape(text)
    needle = q.lower()
    lower = text.lower()
    n = len(needle)
    parts = []
    i = 0
    while True:
        j = lower.find(needle, i)
        if j < 0:
            parts.append(html.escape(text[i:]))
            break
        parts.append(html.escape(text[i:j]))
        parts.append(f"<mark>{html.escape(text[j:j + n])}</mark>")
        i = j + n
    return "".join(parts)


def bundle_title(index) -> str:
    """Return the ``<title>`` of a bundle index, or a sensible default."""
    if index is not None and Path(index).is_file():
        try:
            text = Path(index).read_text(encoding="utf-8")
        except OSError:
            text = ""
        m = re.search(r"<title>(.*?)</title>", text, re.S)
        if m:
            value = html.unescape(_strip_tags(m.group(1))).strip()
            if value:
                return value
    return _DEFAULT_TITLE


def bundle_listings(bundle_dir) -> list[dict]:
    """Ordered report listings ``[{"name", "label"}]`` for a bundle directory.

    Prefers the ``<li><a href="X">Y</a></li>`` entries in ``index.html`` (the
    format emitted by ``fv.gui.analysis.report_index_html``) so the index order
    and labels survive; falls back to a sorted ``*.html`` scan (excluding
    ``index.html``) when the index is absent or unparseable.
    """
    bdir = Path(bundle_dir)
    index = bdir / "index.html"
    if index.is_file():
        try:
            text = index.read_text(encoding="utf-8")
        except OSError:
            text = ""
        items = []
        for match in _ITEM_RE.finditer(text):
            href = html.unescape(match.group(1))
            label = html.unescape(_strip_tags(match.group(2))).strip()
            items.append({"name": href, "label": label or href})
        if items:
            return items
    rows = []
    for path in sorted(bdir.glob("*.html")):
        if path.name == "index.html":
            continue
        rows.append({"name": path.name, "label": path.stem})
    return rows


def _fallback_index_html(listings: list[dict], title: str) -> str:
    items = "".join(
        f'<li><a href="{html.escape(item["name"])}">'
        f"{html.escape(item['label'])}</a></li>"
        for item in listings)
    return ("<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(title)}</title></head><body>"
            f"<h1>{html.escape(title)}</h1>"
            f"<p>{len(listings)} report(s) generated.</p>"
            f"<ul>{items}</ul></body></html>\n")


def _fmt_size(nbytes: int) -> str:
    """Human-readable byte size (e.g. ``1.2 kB``) for a dashboard caption."""
    n = float(nbytes)
    if n < 1024.0:
        return f"{int(n)} B"
    for unit in ("kB", "MB", "GB"):
        n /= 1024.0
        if n < 1024.0 or unit == "GB":
            return f"{n:.1f} {unit}"
    return f"{n:.1f} GB"


def _fmt_mtime(timestamp: float) -> str:
    """Human-readable local mtime (``YYYY-MM-DD HH:MM``), or ``""``."""
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def report_meta(bundle_dir) -> list[dict]:
    """Per-report metadata ``[{name, label, title, size_bytes, mtime}]``.

    Builds on :func:`bundle_listings` so the index order and human labels
    survive, then augments every report with its own ``<title>`` plus the
    ``os.stat`` size / mtime. A report that the index names but that is missing
    or unreadable degrades to ``size 0`` / ``mtime 0.0`` / ``title ""`` without
    raising, so a stale index never breaks a dashboard or ``/api/meta``.
    """
    bdir = Path(bundle_dir)
    rows = []
    for item in bundle_listings(bdir):
        target = (bdir / item["name"]).resolve()
        stat = None
        try:
            stat = target.stat()
        except OSError:
            stat = None
        title = bundle_title(target) if stat is not None else ""
        rows.append({
            "name": item["name"],
            "label": item["label"],
            "title": title,
            "size_bytes": int(stat.st_size) if stat else 0,
            "mtime": float(stat.st_mtime) if stat else 0.0,
        })
    return rows


def _summary_from_rows(rows: list[dict]) -> dict:
    """Aggregate overview from a list of :func:`report_meta` rows."""
    total = 0
    times = []
    for row in rows:
        total += row["size_bytes"]
        if row["mtime"]:
            times.append(row["mtime"])
    return {
        "report_count": len(rows),
        "total_bytes": total,
        "oldest": _fmt_mtime(min(times)) if times else "",
        "newest": _fmt_mtime(max(times)) if times else "",
    }


def bundle_summary(bundle_dir) -> dict:
    """Aggregate overview of a bundle: count, total size, generated span.

    Built on :func:`report_meta` so it honours the index order and degrades the
    same way (missing / unreadable entries contribute 0 bytes and no mtime).
    ``oldest`` / ``newest`` are formatted local mtimes (``YYYY-MM-DD HH:MM``) or
    ``""`` when no report carries an mtime, so an empty or all-degenerate bundle
    yields a clean zero overview instead of raising.
    """
    return _summary_from_rows(report_meta(bundle_dir))


_SORT_KEYS = ("name", "label", "title", "size", "mtime", "matches")


def _default_dir(sort: Optional[str], dir: Optional[str]) -> str:
    """Resolve a sort direction, defaulting to ``desc`` for ``matches`` (R96).

    ``None`` / empty ``dir`` falls back to ``desc`` when ``sort`` is
    ``"matches"`` (a relevance ranking wants the most-matched report first) and
    ``asc`` otherwise, so the existing callers keep their ascending default
    while a match-count query ranks without an explicit ``dir=``.
    """
    if dir:
        return dir
    return "desc" if sort == "matches" else "asc"


def query_reports(rows, *, q=None, sort=None, dir="asc", content=False,
                  bundle_dir=None) -> list[dict]:
    """Filter / sort a list of :func:`report_meta` rows (R88; content R93).

    ``q`` is a case-insensitive substring match against a row's ``name``,
    ``label`` or ``title``. ``sort`` orders by ``name``/``label``/``title``
    (text, case-insensitive) or ``size``/``mtime`` (numeric); ``dir`` is
    ``"asc"`` (default) or ``"desc"``. An unknown ``sort`` key raises
    :class:`ValueError`. With no arguments the rows are returned in their given
    (index) order, so the dashboard and ``/api/meta`` stay backward compatible.

    When ``content`` is ``True`` *and* ``bundle_dir`` is given, ``q`` also
    matches a report's body text (read lazily via :func:`report_content`); a
    body that is missing or unreadable is treated as a non-match, so a content
    search never breaks on a stale index. Without ``bundle_dir`` the content
    branch is skipped, so the metadata-only behaviour is unchanged.

    R96 adds the ``matches`` sort key: a *relevance* ranking that orders rows by
    their descending body match count (via :func:`content_match_count`), so the
    report where ``q`` recurs most surfaces first. It only makes sense for a
    content search, so using it without ``content`` / ``bundle_dir`` raises
    :class:`ValueError` instead of silently behaving like an index order.
    """
    result = list(rows)
    if q:
        needle = q.lower()
        if content and bundle_dir is not None:
            def _matches(row):
                if (needle in row["name"].lower()
                        or needle in row["label"].lower()
                        or needle in row["title"].lower()):
                    return True
                text = report_content(bundle_dir, row["name"])
                return text is not None and needle in text.lower()

            result = [row for row in result if _matches(row)]
        else:
            result = [
                row for row in result
                if needle in row["name"].lower()
                or needle in row["label"].lower()
                or needle in row["title"].lower()
            ]
    if sort:
        if sort not in _SORT_KEYS:
            raise ValueError(f"unknown sort key {sort!r}")
        if sort == "matches":
            if not (content and bundle_dir is not None):
                raise ValueError("sort 'matches' requires a content search")
            counts = {row["name"]: content_match_count(
                bundle_dir, row["name"], q) for row in result}
            result = sorted(result, key=lambda row: counts[row["name"]],
                            reverse=dir == "desc")
        else:
            key = {"size": "size_bytes", "mtime": "mtime"}.get(sort, sort)

            def _key(row):
                value = row[key]
                return value.lower() if isinstance(value, str) else value

            result = sorted(result, key=_key, reverse=dir == "desc")
    return result


def window_reports(rows, *, limit=None, offset=0) -> list[dict]:
    """Window a (filtered / sorted) :func:`report_meta` row list (R89).

    ``limit`` is ``None`` for no windowing (return everything) or a non-negative
    row count for the page size; ``offset`` is a non-negative skip. The slice
    ``rows[offset:offset+limit]`` is returned, so an ``offset`` past the end
    yields ``[]`` and ``limit`` ``0`` yields ``[]``. Negative ``limit`` /
    ``offset`` raise :class:`ValueError`. With ``limit`` ``None`` the rows are
    returned unchanged, so ``dashboard_html`` and ``/api/meta`` stay backward
    compatible when no pagination is requested.
    """
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0")
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit is None:
        return list(rows)
    return list(rows[offset:offset + limit])


def _pager_href(offset: int, limit: Optional[int], q: Optional[str],
                sort: Optional[str], dir: str, dir_default: str = "asc",
                content: bool = False) -> str:
    """Build a dashboard query string that preserves q/sort/dir for a pager."""
    parts = []
    if limit is not None:
        parts.append(f"limit={limit}")
    if offset:
        parts.append(f"offset={offset}")
    if q:
        parts.append(f"q={urllib.parse.quote(q, safe='')}")
    if sort:
        parts.append(f"sort={sort}")
    if dir and dir != dir_default:
        parts.append(f"dir={dir}")
    if content:
        parts.append("content=1")
    return "?" + "&".join(parts)


# ``<select>`` choices for the interactive dashboard controls (R90), in the
# order they should appear (index order first, then the sortable keys).
_SORT_LABELS = (
    ("name", "Name"),
    ("label", "Label"),
    ("title", "Title"),
    ("size", "Size"),
    ("mtime", "Modified"),
    ("matches", "Matches (body)"),
)
_PAGE_SIZES = ("", "10", "25", "50", "100")


def _option(selected: Optional[str], value: str, text: str) -> str:
    """Render a single ``<option>`` (``selected`` marks the current value)."""
    is_selected = (selected is None and value == "") or selected == value
    sel = ' selected' if is_selected else ""
    return (f'<option value="{html.escape(value, quote=True)}"'
            f"{sel}>{html.escape(text)}</option>")


def _controls_html(q: Optional[str], sort: Optional[str], dir: str,
                   limit: Optional[int], content: bool = False) -> str:
    """A dependency-free ``GET`` form driving the dashboard query (R90).

    Lets a browser user type a ``q`` substring, pick a ``sort`` key / ``dir``
    direction and a ``limit`` page size, then submit -- so ``/`` becomes a
    searchable / re-rankable / paged view without hand-editing the URL. Every
    control reflects the current ``dashboard_html`` argument, and the form
    defaults to the index order / ascending / all pages when no query is set.

    R93 adds an opt-in ``content`` checkbox: when checked the form submits
    ``content=1`` (reflected as ``checked`` when the current query is a content
    search), so ``q`` also matches report body text on submission.
    """
    q_esc = html.escape(q or "", quote=True)
    sort_opts = _option(sort, "", "Index order") + "".join(
        _option(sort, key, label) for key, label in _SORT_LABELS)
    dir_opts = _option(dir, "asc", "Ascending") + _option(dir, "desc", "Descending")
    limit_cur = "" if limit is None else str(limit)
    limit_opts = "".join(
        _option(limit_cur, size, "All" if not size else size)
        for size in _PAGE_SIZES)
    content_attr = ' checked' if content else ""
    return ('<form class="dashboard-controls" method="get" action="/">\n'
            f'<input type="search" name="q" value="{q_esc}" '
            'placeholder="filter by name / label / title">\n'
            f'<select name="sort">{sort_opts}</select>\n'
            f'<select name="dir">{dir_opts}</select>\n'
            f'<select name="limit">{limit_opts}</select>\n'
            f'<label class="content-toggle"><input type="checkbox" '
            f'name="content" value="1"{content_attr}>search report content'
            '</label>\n'
            '<button type="submit">apply</button>\n'
            '</form>\n')


def dashboard_html(bundle_dir, title=None, *, q=None, sort=None, dir=None,
                   limit=None, offset=0, content=False) -> str:
    """A richer bundle overview page with per-report metadata (R86).

    Keeps the ``report_index_html`` ``<li><a href="X">label</a></li>`` anchors so
    :func:`bundle_listings` still parses the page, and adds a ``<li class="meta">``
    caption after each report with its own ``<title>``, size and modified time —
    so a served bundle reads as a navigable dashboard instead of a bare link
    list. R87 renders a ``<p class="summary">`` block above the list (report
    count, total size, generated span) built from :func:`bundle_summary`. R88
    lets ``q`` filter by title/label/name and ``sort``/``dir`` re-order the
    reports, so ``/?q=&sort=&dir=`` gives a searchable, re-rankable dashboard
    (the summary block tracks the matched subset). R89 adds ``limit``/``offset``
    windowing: with a ``limit`` the page renders only that slice and a
    ``<p class="pagination">`` ranges line plus previous / next links (which
    preserve ``q``/``sort``/``dir``) appears, so a large bundle is browsable in
    pages. The summary block always reflects the *whole* match (``q``/``sort``
    applied), not just the page. R90 adds a dependency-free ``GET`` form
    (``<form class="dashboard-controls">``) letting a browser user type a ``q``
    substring, pick a ``sort`` key / ``dir`` direction and a ``limit`` page
    size, so ``/`` is a searchable / re-rankable / paged view without hand-
    editing the URL. R93 makes the search content-aware: when ``content`` is
    ``True`` the ``q`` filter also matches report body text (via
    :func:`report_content`), an opt-in ``content`` checkbox appears in the
    controls form (pre-checked for a content search), and the pager links
    preserve ``content=1`` so a content-mode query survives paging. R94 renders a
    ``<li class="snippet">`` plain-text excerpt under each matched report when a
    content search is active (``content`` and ``q``), with the ``q`` match marked
    via :func:`highlight_html`, so a browser user sees *why* a report matched.
    R95 renders one ``<li class="snippet">`` excerpt per body match (via
    :func:`content_snippets`), capped at ``_MAX_SNIPPETS`` with a
    ``<li class="snippet-more">`` "… and N more match(es)" note for the rest, so a
    report where the term recurs shows every occurrence instead of just the
    first. R96 makes a content search *rankable* and its match count visible:
    each matched report gets a ``<li class="matches">N match(es) in body</li>``
    line (from :func:`content_match_count`), the summary block appends the total
    match count, and ``sort="matches"`` orders the reports by descending match
    count (with ``dir`` defaulting to ``desc``) so the most relevant report is
    first.
    ``title``
    (fallback: the bundle's ``<title>``) drives the ``<h1>``.
    """
    bdir = Path(bundle_dir)
    dir = _default_dir(sort, dir)
    heading = title or bundle_title(bdir / "index.html")
    matched = query_reports(report_meta(bdir), q=q, sort=sort, dir=dir,
                            content=content, bundle_dir=bdir)
    total = len(matched)
    rows = window_reports(matched, limit=limit, offset=offset)
    summary = _summary_from_rows(matched)
    summary_parts = [
        f'{summary["report_count"]} report(s)',
        f'{_fmt_size(summary["total_bytes"])} total',
    ]
    if content and q:
        total_matches = sum(
            content_match_count(bdir, row["name"], q) for row in matched)
        summary_parts.append(f"{total_matches} match(es)")
    if summary["oldest"]:
        summary_parts.append(
            f'generated {summary["oldest"]} – {summary["newest"]}')
    items = []
    for row in rows:
        items.append(
            f'<li><a href="{html.escape(row["name"])}">'
            f"{html.escape(row['label'])}</a></li>\n")
        caption_parts = [part for part in (row["title"], _fmt_size(
            row["size_bytes"]), _fmt_mtime(row["mtime"])) if part]
        items.append(f'<li class="meta">{html.escape(" · ".join(caption_parts))}'
                     f"</li>\n")
        if content and q:
            count = content_match_count(bdir, row["name"], q)
            items.append(
                f'<li class="matches">{count} match(es) in body</li>\n')
            snippets = content_snippets(bdir, row["name"], q)
            shown = snippets[:_MAX_SNIPPETS]
            for snippet in shown:
                items.append(
                    f'<li class="snippet">{highlight_html(snippet, q)}</li>\n')
            extra = len(snippets) - len(shown)
            if extra:
                items.append(
                    f'<li class="snippet-more">… and {extra} more match(es)'
                    "</li>\n")
    body = "".join(items)
    pagination = ""
    if limit is not None:
        if rows:
            start = offset + 1
            end = offset + len(rows)
            range_text = f"showing {start}–{end} of {total}"
        else:
            range_text = f"showing 0 of {total}"
        pager_parts = [f'<span class="pager-range">{html.escape(range_text)}'
                       f"</span>"]
        if offset > 0:
            prev = max(0, offset - limit)
            pager_parts.append(
                f'<a class="pager-prev" href='
                f'"{_pager_href(prev, limit, q, sort, dir, content=content)}"'
                f'>previous</a>')
        if offset + len(rows) < total:
            nxt = offset + len(rows)
            pager_parts.append(
                f'<a class="pager-next" href='
                f'"{_pager_href(nxt, limit, q, sort, dir, content=content)}"'
                f'>next</a>')
        pagination = f'<p class="pagination">{" · ".join(pager_parts)}</p>\n'
    controls = _controls_html(q, sort, dir, limit, content=content)
    return ("<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(heading)}</title></head><body>"
            f"<h1>{html.escape(heading)}</h1>"
            f'<p class="summary">{html.escape(" · ".join(summary_parts))}</p>'
            f"{controls}{pagination}<ul>\n{body}</ul></body></html>\n")


def report_detail(bundle_dir, name) -> Optional[dict]:
    """Single-report metadata row for *name*, or ``None`` if absent (R91).

    *name* must resolve inside the bundle (a path that escapes it returns
    ``None``, so ``/api/report?name=../../x`` is refused). Returns the matching
    :func:`report_meta` row plus its 0-based ``index`` in the index-order
    listing; an unknown name returns ``None`` instead of raising.
    """
    bdir = Path(bundle_dir)
    target = (bdir / name).resolve()
    if bdir not in (target, *target.parents):
        return None
    for i, row in enumerate(report_meta(bdir)):
        if row["name"] == name:
            entry = dict(row)
            entry["index"] = i
            return entry
    return None


def report_content(bundle_dir, name) -> Optional[str]:
    """Raw HTML text of a report, or ``None`` if absent / unreadable (R92).

    The machine counterpart to :func:`report_detail`'s metadata: *name* must
    resolve inside the bundle (a path that escapes it returns ``None``) and
    point at a readable file; otherwise ``None`` is returned instead of
    raising, so a stale index entry never breaks a caller. The text is read as
    UTF-8 -- a report that cannot be decoded degrades to ``None`` just like a
    missing one.
    """
    bdir = Path(bundle_dir)
    target = (bdir / name).resolve()
    if bdir not in (target, *target.parents):
        return None
    if not target.is_file():
        return None
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _match_indices(plain: str, needle: str):
    """Yield the start index of every non-overlapping ``needle`` in ``plain`` (R96).

    ``needle`` must already be lower-cased; matching runs against a lowered copy
    of ``plain`` so it is case-insensitive while the yielded indices still refer
    to the original text. Shared by :func:`content_match_count` and
    :func:`content_snippets`, so a report's match count and its excerpts always
    agree on where the matches are.
    """
    lowered = plain.lower()
    n = len(needle)
    i = 0
    while True:
        j = lowered.find(needle, i)
        if j < 0:
            return
        yield j
        i = j + n


def _snippet_window(plain: str, idx: int, width: int, qlen: int) -> tuple:
    """``(start, end, text)`` window of ``plain`` centred on a match at ``idx`` (R95)."""
    pad = max(0, (width - qlen) // 2)
    start = max(0, idx - pad)
    end = min(len(plain), start + width)
    start = max(0, end - width)
    text = plain[start:end]
    if start > 0:
        text = "…" + text
    if end < len(plain):
        text = text + "…"
    return start, end, text


def content_snippets(bundle_dir, name, q, *, width: int = 120,
                     limit: Optional[int] = None) -> list:
    """Plain-text excerpts around *every* ``q`` match in a report body (R95).

    Strips the report's HTML tags and collapses whitespace, then returns one
    ``width``-character window per non-overlapping case-insensitive ``q`` match
    (each prefixed / suffixed with ``…`` when truncated at either end). Windows
    that would overlap the previous one are merged (skipped), so a term that
    recurs within a single window yields one excerpt rather than duplicates. A
    ``limit`` caps the number of excerpts. Returns ``[]`` when ``q`` is empty,
    the body is missing / unreadable, or ``q`` does not appear -- so a caller can
    fall back to metadata alone. The excerpts carry no markup; callers escape /
    highlight them for HTML (see :func:`highlight_html`).
    """
    if not q:
        return []
    text = report_content(bundle_dir, name)
    if text is None:
        return []
    plain = " ".join(_strip_tags(text).split())
    needle = q.lower()
    qlen = len(needle)
    snippets = []
    prev_end = -1
    for j in _match_indices(plain, needle):
        start, end, window = _snippet_window(plain, j, width, qlen)
        if start > prev_end:
            snippets.append(window)
            prev_end = end
            if limit is not None and len(snippets) >= limit:
                break
    return snippets


def content_match_count(bundle_dir, name, q) -> int:
    """Count the ``q`` matches in a report body (R96).

    Strips the report's HTML tags and collapses whitespace exactly as
    :func:`content_snippets` does, then counts the non-overlapping
    case-insensitive ``q`` matches via the shared :func:`_match_indices` scan --
    so a report's match count and its excerpts always agree on where the
    matches are. Returns ``0`` when ``q`` is empty or the body is missing /
    unreadable, so it can be used as a ranking / display key without
    special-casing a degenerate report.
    """
    if not q:
        return 0
    text = report_content(bundle_dir, name)
    if text is None:
        return 0
    plain = " ".join(_strip_tags(text).split())
    return sum(1 for _ in _match_indices(plain, q.lower()))


def content_snippet(bundle_dir, name, q, *, width: int = 120) -> Optional[str]:
    """A short plain-text excerpt of a report body around a ``q`` match (R94).

    The first of :func:`content_snippets` (window centred on the first
    case-insensitive ``q`` match, ``…`` when truncated), or ``None`` when ``q``
    is empty, the body is missing / unreadable, or ``q`` does not appear -- so a
    caller can fall back to metadata alone. The excerpt carries no markup;
    callers escape / highlight it for HTML (see :func:`highlight_html`).
    """
    snippets = content_snippets(bundle_dir, name, q, width=width, limit=1)
    return snippets[0] if snippets else None


def _detail_nav(rows, name) -> tuple[Optional[str], Optional[str]]:
    """``(prev_name, next_name)`` neighbours of *name* in an ordered row list."""
    names = [row["name"] for row in rows]
    try:
        i = names.index(name)
    except ValueError:
        return None, None
    prev = names[i - 1] if i > 0 else None
    nxt = names[i + 1] if i < len(names) - 1 else None
    return prev, nxt


def _dashboard_href(q: Optional[str], sort: Optional[str], dir: str,
                    content: bool = False) -> str:
    """Dashboard ``/`` URL that preserves ``q``/``sort``/``dir`` (R91; content R93)."""
    return "/" + _pager_href(0, None, q, sort, dir, content=content)


def _detail_href(name: str, q: Optional[str], sort: Optional[str], dir: str,
                 content: bool = False) -> str:
    """Detail ``/report/<name>`` URL preserving query (R91; content R93)."""
    return ("/report/" + urllib.parse.quote(name, safe="")
            + _pager_href(0, None, q, sort, dir, content=content))


def report_detail_html(bundle_dir, name, *, q=None, sort=None, dir=None,
                       content=False) -> Optional[str]:
    """A dashboard-context detail page for a single report (R91/R92).

    Renders the report's ``label`` (or ``name``) as the ``<h1>``, a crumb trail
    with a back-to-dashboard link (which preserves ``q``/``sort``/``dir``), a
    metadata caption (own ``<title>``, size, modified time), an "open report"
    link to the raw file, and previous / next report navigation within the
    current ``q``/``sort``/``dir`` ordering. R92 embeds the report body inline
    (an ``<iframe class="report-frame">`` referencing the raw report at its
    absolute path) so a user reads each report in context, and the "open
    report" link now targets that absolute raw path instead of a relative one
    that resolved back to the page itself; the preview is skipped when the
    report is unreadable. R93 threads ``content`` through the nav (dashboard
    back-link and prev / next hrefs preserve ``content=1``) and the query, so a
    content-mode search survives leaving a report. R94 renders a
    ``<p class="snippet">`` plain-text excerpt around the ``q`` match when a
    content search is active (``content`` and ``q``), with the match marked via
    :func:`highlight_html`, so a user landing here from a content search sees
    *why* the report matched. R95 renders one ``<p class="snippet">`` excerpt per
    body match (via :func:`content_snippets`), capped at ``_MAX_SNIPPETS``, so a
    report where the term recurs shows every occurrence. R96 renders the report's
    body match count as a ``<p class="matches">`` line (from
    :func:`content_match_count`) and defaults the direction to ``desc`` for a
    ``sort="matches"`` ranking. Returns ``None`` when
    *name*
    is unknown or escapes the bundle, so the caller can 404.
    """
    bdir = Path(bundle_dir)
    dir = _default_dir(sort, dir)
    entry = report_detail(bdir, name)
    if entry is None:
        return None
    heading = entry["label"] or entry["name"]
    matched = query_reports(report_meta(bdir), q=q, sort=sort, dir=dir,
                            content=content, bundle_dir=bdir)
    prev, nxt = _detail_nav(matched, name)
    dash = _dashboard_href(q, sort, dir, content=content)
    crumbs = (f'<p class="crumbs"><a href="{html.escape(dash)}">dashboard</a>'
              f" · {len(matched)} match(es)</p>\n")
    caption = " · ".join(part for part in (
        entry["title"], _fmt_size(entry["size_bytes"]),
        _fmt_mtime(entry["mtime"])) if part)
    meta = (f'<p class="report-meta">{html.escape(caption or "no metadata")}'
            f"</p>\n")
    raw = "/" + urllib.parse.quote(name, safe="")
    open_link = (f'<p class="report-open"><a href="{raw}" target="_blank">'
                 "open report</a></p>\n")
    nav_parts = []
    if prev:
        prev_href = html.escape(_detail_href(prev, q, sort, dir,
                                             content=content))
        nav_parts.append(f'<a class="detail-prev" href="{prev_href}">'
                         f'previous</a>')
    if nxt:
        nxt_href = html.escape(_detail_href(nxt, q, sort, dir,
                                            content=content))
        nav_parts.append(f'<a class="detail-next" href="{nxt_href}">'
                         f'next</a>')
    nav = ""
    if nav_parts:
        nav = f'<p class="detail-nav">{" · ".join(nav_parts)}</p>\n'
    snippet_para = ""
    if content and q:
        count = content_match_count(bdir, name, q)
        snippet_para = (f'<p class="matches">{count} match(es) in body</p>\n')
        snippets = content_snippets(bdir, name, q)[:_MAX_SNIPPETS]
        snippet_para += "".join(
            f'<p class="snippet">{highlight_html(snippet, q)}</p>\n'
            for snippet in snippets)
    preview = ""
    if report_content(bdir, name) is not None:
        preview = ('<div class="report-preview">\n'
                   f'<iframe class="report-frame" src="{raw}" title="'
                   f"{html.escape(heading)} report\" height=\"600\"></iframe>\n"
                   "</div>\n")
    return ("<!doctype html>\n<html><head><meta charset=\"utf-8\">"
            f"<title>{html.escape(heading)}</title></head><body>"
            f"<h1>{html.escape(heading)}</h1>{crumbs}{meta}{open_link}{nav}"
            f"{snippet_para}{preview}"
            f'<p class="detail-path">{html.escape(entry["name"])}</p>'
            "</body></html>\n")


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _HTML_SUFFIXES:
        return "text/html; charset=utf-8"
    if suffix == ".png":
        return "image/png"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"


# ── HTTP handler ───────────────────────────────────────────────────────────


class ReportBundleHandler(BaseHTTPRequestHandler):
    """Serve a report bundle directory over ``/`` and ``/api/*``.

    ``bundle_dir`` and ``index`` are injected per-request via
    :func:`make_handler`; the class attributes keep ``BaseHTTPRequestHandler``
    happy and are always replaced before a request arrives.
    """

    bundle_dir: Path = None  # type: ignore[assignment]
    index: Optional[Path] = None

    def log_message(self, fmt, *args):  # keep the gate's stderr clean
        return

    # -- dispatch -----------------------------------------------------------
    def do_GET(self):  # noqa: N802 (http.server convention)
        parsed = urllib.parse.urlsplit(self.path)
        route = parsed.path
        if route == "/":
            return self._route_dashboard()
        if route == "/index.html":
            return self._route_index()
        if route == "/api/list":
            return self._route_list()
        if route == "/api/meta":
            return self._route_meta()
        if route == "/api/summary":
            return self._route_summary()
        if route == "/api/bundle.zip":
            return self._route_zip()
        if route == "/api/report/content":
            return self._route_report_content()
        if route == "/api/report/snippet":
            return self._route_report_snippet()
        if route == "/api/report":
            return self._route_report_api()
        if route.startswith("/report/"):
            return self._route_report_detail(route)
        return self._route_file(route)

    # -- endpoint bodies ----------------------------------------------------
    def _route_index(self):
        index = self.index
        if index is not None and Path(index).is_file():
            return self._serve_path(Path(index), "text/html; charset=utf-8")
        title = bundle_title(index)
        listings = bundle_listings(self.bundle_dir)
        html_body = _fallback_index_html(listings, title)
        payload = html_body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _param(self, key: str) -> Optional[str]:
        """First value of a query string parameter, or ``None``."""
        parsed = urllib.parse.urlsplit(self.path)
        return urllib.parse.parse_qs(parsed.query).get(key, [None])[0]

    def _param_int(self, key: str) -> Optional[int]:
        """First query value as an ``int``, ``None`` if absent, else ``ValueError``."""
        value = self._param(key)
        if value is None or value == "":
            return None
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"invalid {key}: {value!r}") from None

    def _param_flag(self, key: str) -> bool:
        """True when a boolean query flag (``content=1``) is set (R93)."""
        return self._param(key) == "1"

    def _route_dashboard(self):
        """Serve the metadata dashboard at ``/`` (R86; queryable R88, windowed R89)."""
        title = bundle_title(self.index)
        content = self._param_flag("content")
        try:
            payload = dashboard_html(
                self.bundle_dir, title, q=self._param("q"),
                sort=self._param("sort"), dir=self._param("dir"),
                limit=self._param_int("limit"),
                offset=self._param_int("offset") or 0,
                content=content,
            ).encode("utf-8")
        except ValueError as exc:
            return _send_error(self, 400, str(exc))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _route_meta(self):
        try:
            limit = self._param_int("limit")
            offset = self._param_int("offset") or 0
            matched = query_reports(
                report_meta(self.bundle_dir), q=self._param("q"),
                sort=self._param("sort"),
                dir=_default_dir(self._param("sort"), self._param("dir")),
                content=self._param_flag("content"), bundle_dir=self.bundle_dir,
            )
            rows = window_reports(matched, limit=limit, offset=offset)
        except ValueError as exc:
            return _send_error(self, 400, str(exc))
        total = len(matched)
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "total": total,
            "offset": offset,
            "limit": limit,
            "reports": rows,
            "summary": _summary_from_rows(matched),
        })

    def _route_summary(self):
        """Serve the bundle overview as JSON (R87)."""
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "summary": bundle_summary(self.bundle_dir),
        })

    def _route_report_api(self):
        """Serve a single report's metadata as JSON (R91)."""
        name = self._param("name")
        if not name:
            return _send_error(self, 400, "missing name")
        entry = report_detail(self.bundle_dir, name)
        if entry is None:
            return _send_error(self, 404, f"unknown report: {name}")
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "report": entry,
        })

    def _route_report_content(self):
        """Serve a single report's raw content as JSON (R93)."""
        name = self._param("name")
        if not name:
            return _send_error(self, 400, "missing name")
        content = report_content(self.bundle_dir, name)
        if content is None:
            return _send_error(self, 404, f"unknown report: {name}")
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "name": name,
            "content": content,
        })

    def _route_report_snippet(self):
        """Serve a report's body excerpts around a ``q`` match as JSON (R94/R95)."""
        name = self._param("name")
        if not name:
            return _send_error(self, 400, "missing name")
        q = self._param("q")
        if not q:
            return _send_error(self, 400, "missing q")
        if report_detail(self.bundle_dir, name) is None:
            return _send_error(self, 404, f"unknown report: {name}")
        snippets = content_snippets(self.bundle_dir, name, q)
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "name": name,
            "q": q,
            "count": len(snippets),
            "matches": content_match_count(self.bundle_dir, name, q),
            "snippet": snippets[0] if snippets else None,
            "snippets": snippets,
        })

    def _route_report_detail(self, route: str):
        """Serve the dashboard-context detail page for one report (R91)."""
        name = urllib.parse.unquote(route[len("/report/"):])
        body = report_detail_html(
            self.bundle_dir, name, q=self._param("q"),
            sort=self._param("sort"), dir=self._param("dir"),
            content=self._param_flag("content"),
        )
        if body is None:
            return _send_error(self, 404, f"unknown report: {name}")
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _route_list(self):
        _send_json(self, {
            "ok": True,
            "bundle": str(Path(self.bundle_dir).resolve()),
            "title": bundle_title(self.index),
            "reports": bundle_listings(self.bundle_dir),
        })

    def _route_zip(self):
        bdir = Path(self.bundle_dir)
        files = sorted(p for p in bdir.rglob("*") if p.is_file())
        if not files:
            return _send_error(self, 404, "empty bundle")
        fd, tmp = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        try:
            with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
                for path in files:
                    zf.write(path, arcname=path.relative_to(bdir).as_posix())
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header(
                "Content-Disposition", 'attachment; filename="bundle.zip"')
            self.send_header("Content-Length", str(os.path.getsize(tmp)))
            self.end_headers()
            with open(tmp, "rb") as fh:
                shutil.copyfileobj(fh, self.wfile)
        except OSError as exc:
            return _send_error(self, 500, f"zip failed: {exc}")
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _route_file(self, route: str):
        rel = urllib.parse.unquote(route.lstrip("/"))
        if not rel:
            return _send_error(self, 400, "empty path")
        bdir = Path(self.bundle_dir)
        target = (bdir / rel).resolve()
        if bdir not in (target, *target.parents):
            return _send_error(self, 403, "path escapes bundle")
        if not target.is_file():
            return _send_error(self, 404, f"not found: {route}")
        return self._serve_path(target, _content_type(target))

    # -- I/O ----------------------------------------------------------------
    def _serve_path(self, path: Path, content_type: str):
        try:
            size = path.stat().st_size
        except OSError as exc:
            return _send_error(self, 404, f"not readable: {exc}")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(path, "rb") as fh:
            shutil.copyfileobj(fh, self.wfile)


def make_handler(bundle_dir, index=None) -> type:
    """Threading handler bound to a fixed *bundle_dir* / *index*."""
    bdir = Path(bundle_dir)
    idx = Path(index) if index else None

    class _BoundHandler(ReportBundleHandler):
        bundle_dir = bdir
        index = idx

    return _BoundHandler


class ReportBundleServer(ThreadingHTTPServer):
    """A ``ThreadingHTTPServer`` mounted on a report bundle directory."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address, bundle_dir, index=None,
                 *, host: str = "127.0.0.1", port: int = 0):
        bdir = Path(bundle_dir)
        super().__init__(
            (host, port), make_handler(bdir, index if index else
                                       (bdir / "index.html" if
                                        (bdir / "index.html").is_file() else
                                        None)))

    @property
    def port(self) -> int:
        return int(self.server_address[1])


def serve_bundle(bundle_dir, port: int = 0, host: str = "127.0.0.1",
                 *, in_thread: bool = False):
    """Start a :class:`ReportBundleServer` hosting a report bundle.

    *bundle_dir* is a directory of self-contained single-file HTML reports
    (with or without an ``index.html``). Returns either the server (when
    ``in_thread=False``; caller serves) or a ``(server, thread)`` pair already
    running in the background.
    """
    bdir = Path(bundle_dir)
    if not bdir.is_dir():
        raise ValueError(f"not a bundle directory: {bdir}")
    index = bdir / "index.html"
    server = ReportBundleServer((host, port), bdir,
                                index if index.is_file() else None,
                                host=host, port=port)
    if not in_thread:
        return server
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
