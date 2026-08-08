"""Pane wrappers: PaneFrame, MessageWindow, ObjectTree (headless-tolerant)."""

from __future__ import annotations

from typing import Optional

try:
    from PyQt5 import QtCore, QtWidgets
    from PyQt5.QtWidgets import (
        QFrame, QLabel, QPlainTextEdit, QTreeWidget, QTreeWidgetItem,
        QVBoxLayout,
    )
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    _HAS_QT = False
    QtWidgets = None


class PaneFrame(QFrame if _HAS_QT else object):
    """QFrame with a title bar + body that fills the remaining space."""

    def __init__(self, title: str, body=None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QLabel(title)
        bar.setObjectName("paneTitle")
        bar.setStyleSheet(
            "background:#2b3a55; color:#e8ecf4; padding:3px 8px;"
            "font-weight:600;")
        lay.addWidget(bar)
        if body is not None:
            lay.addWidget(body, 1)
        self.body = body


class MessageWindow(QPlainTextEdit if _HAS_QT else object):
    def __init__(self, parent=None):
        super().__init__(parent)
        if _HAS_QT:
            self.setReadOnly(True)
            self.setMaximumBlockCount(4000)

    def write(self, text: str) -> None:
        if _HAS_QT:
            self.appendPlainText(text.rstrip("\n"))
        else:
            print(text, end="")


class ObjectTree(QTreeWidget if _HAS_QT else object):
    """Object tree (Control Window) mirroring the scPost object model."""

    def __init__(self, parent=None):
        super().__init__(parent)
        if _HAS_QT:
            self.setHeaderLabels(["Object", "Status"])
            self.setColumnWidth(0, 200)

    def clear_and_rebuild(self, root_items: list[tuple]):
        if not _HAS_QT:
            return
        self.clear()
        for label, children in root_items:
            top = QTreeWidgetItem([label, ""])
            for child in children:
                c = child if isinstance(child, QTreeWidgetItem) else QTreeWidgetItem([str(child)])
                top.addChild(c)
            self.addTopLevelItem(top)
        self.expandAll()