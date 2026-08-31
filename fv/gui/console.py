"""R25-S3: Qt console pane wrapping a headless :class:`ConsoleSession`.

The pane is a prompt + output widget: type into the single-line editor, press
Enter to run, keep command history with Up/Down, and read any captured
stdout/stderr/error in the read-only log. The session is pre-seeded by
:func:`fv.console.default_context`, so ``ff`` / ``open_file`` /
``register_derived_function`` & friends are live inside the GUI.
"""

from __future__ import annotations

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPlainTextEdit,
        QVBoxLayout,
        QWidget,
    )
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    Qt = None
    _HAS_QT = False


class ConsolePane(QWidget):
    """A minimal interactive Python prompt backed by a ConsoleSession."""

    def __init__(self, session=None, parent=None):
        super().__init__(parent)
        from ..console import ConsoleSession, default_context
        self.session = session or ConsoleSession(default_context())

        self.log = QPlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        self.log.setObjectName("console_output")

        prompt = QLabel(">>>", self)
        self.entry = QLineEdit(self)
        self.entry.setObjectName("console_input")
        self.entry.returnPressed.connect(self._exec)
        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 0)
        line.addWidget(prompt)
        line.addWidget(self.entry, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.addWidget(self.log, 1)
        root.addLayout(line)

        self._history = []
        self._hist_idx = 0
        self._write("Python console - type code, press Enter to run.\n")

    # ── interaction ────────────────────────────────────────────────────────
    def _exec(self):
        code = self.entry.text().strip()
        if not code:
            return
        self.entry.clear()
        self._history.append(code)
        self._hist_idx = len(self._history)
        ok, output = self.session.run(code)
        self._write("%s>>> %s\n" % ("" if self.log.document().isEmpty()
                                    else "\n", code))
        if output:
            self._write(output if output.endswith("\n") else output + "\n")
        if not ok:
            self._write("ConsoleError\n")
        self.log.verticalScrollBar().setValue(
            self.log.verticalScrollBar().maximum())

    def _write(self, text: str):
        self.log.appendPlainText(text.rstrip("\n") if text.strip() else "")

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Up, Qt.Key_Down) and self._history:
            delta = -1 if event.key() == Qt.Key_Up else 1
            self._hist_idx = max(0, min(len(self._history),
                                        self._hist_idx + delta))
            if 0 <= self._hist_idx < len(self._history):
                self.entry.setText(self._history[self._hist_idx])
                return
        super().keyPressEvent(event)
