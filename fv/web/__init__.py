"""R32: web presentation + collaboration automation (beyond-scPOST).

* :mod:`fv.web.server`        - headless HTTP streaming data service over the
  R31 windowed CGNS reader (zero third-party deps).
* :mod:`fv.web.report`        - bake a self-contained interactive HTML report.
* :mod:`fv.web.report_server` - host a report-family bundle (R64-R81) over
  HTTP for browsing / sharing (R82); deepen the presentation with a metadata
  dashboard at ``/`` and an ``/api/meta`` JSON surface (R86), a single-report
  detail page at ``/report/<name>`` (with an embedded report preview) and an
  ``/api/report`` JSON endpoint (R91/R92), content-aware search plus an
  ``/api/report/content`` JSON endpoint (R93), a match snippet /
  ``<mark>`` highlight surfaced on the dashboard / detail pages plus an
  ``/api/report/snippet`` JSON endpoint (R94), and every-match excerpts (a
  ``content_snippets`` list with a match ``count``) on the dashboard / detail
  pages and in ``/api/report/snippet`` (R95), relevance ranking by body
  match count (a ``matches`` sort key) plus visible per-report / total match
  counts (``content_match_count``) on the dashboard / detail pages (R96), and
  those same per-report / total match counts on the machine-readable
  ``/api/meta`` surface, computed once via ``content_match_counts`` (R97), and
  each matched report's ``snippets`` excerpts on that surface too, so one
  ``/api/meta`` call yields the whole content-search result (R98), and an
  on-demand ``full=1`` flag that lifts the page-side ``_MAX_SNIPPETS`` cap so
  the dashboard / detail pages render every body match, with the "… and N more
  match(es)" note linked to the uncapped view (R99), and report-neighbourhood
  context (``report_context``) that labels the detail prev / next links with the
  neighbour's ``label`` and attaches an ordering ``context`` block (index /
  total / prev / next) to ``/api/report`` (R100).
* :mod:`fv.automation`        - headless AutomationSession + serve HTTP-RPC
  bridge.
"""

from .report import render_report
from .report_server import (
    ReportBundleServer,
    bundle_summary,
    content_match_count,
    content_match_counts,
    content_snippet,
    content_snippets,
    dashboard_html,
    highlight_html,
    query_reports,
    report_content,
    report_context,
    report_detail,
    report_detail_html,
    report_meta,
    serve_bundle,
    window_reports,
)
from .server import WebViewerServer, serve_session

__all__ = [
    "ReportBundleServer",
    "WebViewerServer",
    "bundle_summary",
    "content_match_count",
    "content_match_counts",
    "content_snippet",
    "content_snippets",
    "dashboard_html",
    "highlight_html",
    "query_reports",
    "render_report",
    "report_content",
    "report_context",
    "report_detail",
    "report_detail_html",
    "report_meta",
    "serve_bundle",
    "serve_session",
    "window_reports",
]
