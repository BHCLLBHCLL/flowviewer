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
  pages and in ``/api/report/snippet`` (R95).
* :mod:`fv.automation`        - headless AutomationSession + serve HTTP-RPC
  bridge.
"""

from .report import render_report
from .report_server import (
    ReportBundleServer,
    bundle_summary,
    content_snippet,
    content_snippets,
    dashboard_html,
    highlight_html,
    query_reports,
    report_content,
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
    "content_snippet",
    "content_snippets",
    "dashboard_html",
    "highlight_html",
    "query_reports",
    "render_report",
    "report_content",
    "report_detail",
    "report_detail_html",
    "report_meta",
    "serve_bundle",
    "serve_session",
    "window_reports",
]
