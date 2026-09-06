"""R77: sequence data-source dialog.

Lets the GUI build the Analysis data source straight from a raw CGNS result
sequence — the same path the R76 headless CLI covers with ``--source`` — instead
of requiring a Time Series object (R65) or an exported JSON (R75). The dialog
collects the sequence directory/file, the monitoring points (as ``x,y,z`` lines
or a ``#``-commentable text file), an optional field, and a per-cycle memory
budget, then hands those raw strings to the caller so the pure parsing
(:func:`fv.report.parse_probe_points`) stays headless-testable.

PyQt is imported at module scope — this module is only ever imported from the
live GUI, never headless. It is a pure widget layer: it does not run reports.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)


class SequenceSourceDialog(QDialog):
    """Collect the inputs for a raw-sequence Analysis data source (R77)."""

    def __init__(self, parent=None, start_dir: str | None = None):
        super().__init__(parent)
        self.setWindowTitle("Sequence Data Source")
        self.setMinimumWidth(520)
        self._start = start_dir or ""
        form = QFormLayout(self)

        self._paths = QLineEdit()
        self._paths.setToolTip("Result-sequence directory, first file, or list")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_paths)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._paths, 1)
        lay.addWidget(browse)
        form.addRow("Sequence:", row)

        self._probes = QPlainTextEdit()
        self._probes.setToolTip("One monitoring point 'x,y,z' per line")
        self._probes.setPlaceholderText("0.5, 0.5, 0.5\n1.0, 0.5, 0.5")
        self._probes.setFixedHeight(64)
        form.addRow("Probes:", self._probes)

        self._probes_file = QLineEdit()
        self._probes_file.setToolTip("Optional text file of 'x,y,z' per line")
        browse2 = QPushButton("Browse…")
        browse2.clicked.connect(self._browse_probes_file)
        row2 = QWidget()
        lay2 = QHBoxLayout(row2)
        lay2.setContentsMargins(0, 0, 0, 0)
        lay2.addWidget(self._probes_file, 1)
        lay2.addWidget(browse2)
        form.addRow("Probes file:", row2)

        self._field = QLineEdit()
        self._field.setToolTip("Leave blank to use the first field on the first cycle")
        form.addRow("Field:", self._field)

        self._budget = QSpinBox()
        self._budget.setRange(1, 4096)
        self._budget.setValue(64)
        self._budget.setSuffix(" MB")
        form.addRow("Budget:", self._budget)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _browse_paths(self) -> None:
        start = self._paths.text().strip() or self._start
        path = QFileDialog.getExistingDirectory(self, "Select Result Sequence", start)
        if path:
            self._paths.setText(path)

    def _browse_probes_file(self) -> None:
        start = self._start
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Probes File", start, "Text (*.txt *.csv);;All (*)")
        if path:
            self._probes_file.setText(path)

    def result(self) -> dict:
        """Return raw dialog values for the caller to parse headlessly."""
        probe_lines = [ln.strip() for ln in self._probes.toPlainText().splitlines()
                       if ln.strip()]
        paths = self._paths.text().strip()
        return {
            "paths": paths,
            "probes": probe_lines,
            "probes_file": self._probes_file.text().strip() or None,
            "field": self._field.text().strip() or None,
            "budget_mb": self._budget.value(),
        }
