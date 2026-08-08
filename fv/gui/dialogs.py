"""Open-file dialog with file information preview (scPost File-Open style)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from PyQt5 import QtCore, QtWidgets
    from PyQt5.QtWidgets import QDialog, QFileDialog, QLabel, QListWidget, QVBoxLayout
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    _HAS_QT = False
    QtWidgets = None


def file_information(filepath: str) -> str:
    """Return a human-readable summary of *filepath* (mesh + variable info)."""
    from ..model.dataset import load_file
    p = Path(filepath)
    try:
        ff = load_file(str(p))
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc}"
    lines = [
        f"size     : {ff.file_size:,} bytes",
        f"kind     : {ff.kind.upper()}",
        f"vertices : {ff.n_vertices:,}",
        f"cells    : {ff.n_cells:,}",
        f"variables: {len(ff.variables)}",
    ]
    if ff.parts:
        lines.append(f"parts    : {', '.join(ff.parts)}")
    if ff.variable_names():
        names = ff.variable_names()
        shown = ", ".join(names[:12])
        if len(names) > 12:
            shown += f" ... (+{len(names) - 12})"
        lines.append(f"vars     : {shown}")
    return "\n".join(lines)


class OpenDialog(QDialog if _HAS_QT else object):
    """Modal file chooser that previews mesh/variable info before opening."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Open File")
        self.resize(560, 380)
        lay = QVBoxLayout(self)
        self._list = QListWidget(self)
        lay.addWidget(QLabel("Choose a file:"))
        lay.addWidget(self._list)
        self._info = QLabel("(no selection)", self)
        self._info.setWordWrap(True)
        self._info.setStyleSheet("background:#202a3a; padding:6px; font-family:Consolas;")
        lay.addWidget(self._info)
        from PyQt5.QtWidgets import QDialogButtonBox
        self._buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        lay.addWidget(self._buttons)

        self._dirs: list[Path] = []
        self._current: Optional[Path] = None
        self._list.itemSelectionChanged.connect(self._on_select)

    def browse(self) -> None:
        """Populate the list from a directory picker, then refresh info."""
        d = QFileDialog.getExistingDirectory(self, "Choose directory with fld/fph files")
        if not d:
            return
        self.load_directory(d)

    def load_directory(self, dirpath: str) -> None:
        p = Path(dirpath)
        files = sorted(
            [f for f in p.iterdir()
             if f.suffix.lower() in (".fld", ".fph", ".gph") and f.is_file()],
            key=lambda f: f.name.lower(),
        )
        self._dirs = files
        self._list.clear()
        for f in files:
            self._list.addItem(f.name)
        if files:
            self._list.setCurrentRow(0)

    def _on_select(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._dirs):
            self._info.setText("(no selection)")
            return
        path = self._dirs[row]
        self._current = path
        self._info.setText(file_in_summary(path))

    def selected_path(self) -> Optional[str]:
        return str(self._current) if self._current is not None else None


def file_in_summary(path) -> str:
    """Preview info (fast: count of sections + size).  Parse is heavy so only
    size / suffix shown until real open."""
    try:
        from ..model.dataset import load_file
        ff = load_file(str(path))
        return "\n".join([
            f"file    : {Path(path).name}",
            f"size    : {ff.file_size:,} bytes",
            f"kind    : {ff.kind.upper()}",
            f"vertices: {ff.n_vertices:,}",
            f"cells   : {ff.n_cells:,}",
            f"variables: {len(ff.variables)}",
        ])
    except Exception as exc:  # noqa: BLE001
        return f"size: {stat_quiet(path)}\nerror: {exc}"


def stat_quiet(path) -> str:
    try:
        n = Path(path).stat().st_size
        return f"{n:,} bytes"
    except Exception:  # noqa: BLE001
        return "?"