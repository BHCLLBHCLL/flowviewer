"""R32: web presentation + collaboration automation (beyond-scPOST).

* :mod:`fv.web.server`  - headless HTTP streaming data service over the R31
  windowed CGNS reader (zero third-party deps).
* :mod:`fv.web.report`  - bake a self-contained interactive HTML report.
* :mod:`fv.automation`  - headless AutomationSession + serve HTTP-RPC bridge.
"""

from .report import render_report
from .server import WebViewerServer, serve_session

__all__ = ["WebViewerServer", "serve_session", "render_report"]
