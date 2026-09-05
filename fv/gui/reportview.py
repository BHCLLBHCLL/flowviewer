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
        QComboBox,
        QFileDialog,
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
        self._save_btn = QPushButton("Save As…", self)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._export)
        self._recent = QComboBox(self)
        self._recent.setMinimumWidth(180)
        self._recent.currentIndexChanged.connect(self._on_recent)
        self._status = QLabel("", self)
        bar.addWidget(self._open_btn)
        bar.addWidget(self._reload_btn)
        bar.addWidget(self._save_btn)
        bar.addWidget(self._recent)
        bar.addWidget(self._status)
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
        self._history: list = []

    def open(self, path: str) -> None:
        """Load ``path`` (an HTML file) into the panel, or enable the browser button."""
        self._current = str(path)
        self._open_btn.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._add_recent(self._current)
        if self._view is not None:
            self._view.load(QUrl(_as_uri(self._current)))

    def _reload(self) -> None:
        if self._view is not None and self._current is not None:
            self._view.load(QUrl(_as_uri(self._current)))

    def _open_external(self) -> None:
        if self._current is not None:
            QDesktopServices.openUrl(QUrl(_as_uri(self._current)))

    def export(self) -> None:
        """Save the currently shown report to a user-chosen location."""
        self._export()

    def _export(self) -> None:
        if not self._current:
            self._status.setText("No report to export")
            return
        default = str(Path(self._current).name)
        dest, _ = QFileDialog.getSaveFileName(
            self, "Save Report As", default,
            "HTML files (*.html);;All files (*)")
        if not dest:
            return
        from .analysis import copy_report
        out = copy_report(self._current, str(Path(dest).parent),
                          name=Path(dest).name)
        self._status.setText(
            "Saved: {}".format(out) if out else "Export failed")

    def _add_recent(self, path: str) -> None:
        if path in self._history:
            self._history.remove(path)
        self._history.insert(0, path)
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        self._recent.blockSignals(True)
        self._recent.clear()
        self._recent.addItem("Recent reports")
        for p in self._history:
            self._recent.addItem(Path(p).name, p)
        self._recent.setCurrentIndex(0)
        self._recent.blockSignals(False)

    def _on_recent(self, idx: int) -> None:
        p = self._recent.itemData(idx)
        if p:
            self.open(str(p))
