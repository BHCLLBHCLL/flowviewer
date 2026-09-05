"""R64: dockable report viewer (WebEngine when available, browser fallback).

``analysis.run_report`` hands back an HTML path; the GUI shows it in a
``ReportPanel`` — a small QWidget with a "Open in browser" / "Reload" toolbar
and a ``QWebEngineView`` body when the optional ``PyQt5.QtWebEngineWidgets``
module is importable (the canonical dependency list only ships ``PyQt5`` core).
Without WebEngine the panel degrades to a hint + browser-open button, so the
GUI stays usable on stripped installs. Import-safe headless: no Qt symbol is
referenced at module import time unless PyQt is present.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from PyQt5.QtCore import QUrl
    from PyQt5.QtGui import QDesktopServices
    from PyQt5.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    _QT = True
except Exception:  # pragma: no cover - headless without PyQt
    _QT = False


def _webengine():
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        return QWebEngineView
    except Exception:  # pragma: no cover
        return None


def supports_webview() -> bool:
    """True when an embedded ``QWebEngineView`` is available."""
    return _webengine() is not None


def _as_uri(path: str) -> str:
    """Absolute ``file://`` URI for a report path (HTML or directory)."""
    p = Path(path).resolve()
    if p.is_dir():
        return p.as_uri()
    return p.as_uri()


class ReportPanel(QWidget if _QT else object):  # type: ignore[misc]
    """Host a generated report HTML, embedded or opened externally."""

    def __init__(self, parent=None):
        if not _QT:  # pragma: no cover - headless
            raise RuntimeError("ReportPanel requires PyQt5")
        super().__init__(parent)
        Web = _webengine()
        self._webengine = Web
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        self._open_btn = QPushButton("Open in browser", self)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_external)
        self._reload_btn = QPushButton("Reload", self)
        self._reload_btn.clicked.connect(self._reload)
        bar.addWidget(self._open_btn)
        bar.addWidget(self._reload_btn)
        bar.addStretch(1)
        lay.addLayout(bar)
        self._view = Web(self) if Web is not None else None
        if self._view is not None:
            lay.addWidget(self._view)
        else:
            self._hint = QLabel(
                'WebEngine not available — use "Open in browser" to view.', self)
            lay.addWidget(self._hint)
        self._current: Optional[str] = None

    def open(self, path: str) -> None:
        """Load ``path`` (an HTML file) into the panel, or enable the browser button."""
        self._current = str(path)
        self._open_btn.setEnabled(True)
        if self._view is not None:
            self._view.load(QUrl(_as_uri(self._current)))

    def _reload(self) -> None:
        if self._view is not None and self._current is not None:
            self._view.load(QUrl(_as_uri(self._current)))

    def _open_external(self) -> None:
        if self._current is not None:
            QDesktopServices.openUrl(QUrl(_as_uri(self._current)))
