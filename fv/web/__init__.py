"""R32: web presentation + collaboration automation (beyond-scPOST).

* :mod:`fv.web.server`        - headless HTTP streaming data service over the
  R31 windowed CGNS reader (zero third-party deps).
* :mod:`fv.web.report`        - bake a self-contained interactive HTML report.
* :mod:`fv.web.report_server` - host a report-family bundle (R64-R81) over
  HTTP for browsing / sharing (R82).
* :mod:`fv.automation`        - headless AutomationSession + serve HTTP-RPC
  bridge.
"""

from .report import render_report
from .report_server import ReportBundleServer, serve_bundle
from .server import WebViewerServer, serve_session

__all__ = [
    "ReportBundleServer",
    "WebViewerServer",
    "render_report",
    "serve_bundle",
    "serve_session",
]
