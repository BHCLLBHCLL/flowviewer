"""scPOST-style dialogs: DialogHeader, PostDialogBase, OpenDialog."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
        QListWidget, QPushButton, QSplitter, QVBoxLayout, QWidget,
    )
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    _HAS_QT = False
    QtWidgets = None
    QDialog = object  # type: ignore
    QWidget = object  # type: ignore


class DialogHeader(QWidget if _HAS_QT else object):
    """Icon + bold caption + separator (cabdecoding / Cradle dialog band)."""

    def __init__(self, caption: str, icon: str = "open", parent=None):
        super().__init__(parent)
        if not _HAS_QT:
            return
        from .icons import AppIcons
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 2)
        lay.setSpacing(2)
        row = QHBoxLayout()
        row.setContentsMargins(2, 2, 2, 0)
        if icon:
            ic = QLabel(self)
            ic.setPixmap(AppIcons.get(icon, 20).pixmap(20, 20))
            row.addWidget(ic)
        text = QLabel(caption, self)
        text.setStyleSheet("font-weight: bold; font-size: 12px;")
        row.addWidget(text)
        row.addStretch(1)
        lay.addLayout(row)
        self.caption_label = text
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line)

    def set_caption(self, caption: str) -> None:
        if _HAS_QT:
            self.caption_label.setText(caption)


class PostDialogBase(QDialog if _HAS_QT else object):
    """Common dialog chrome: header + body + OK/Cancel (scPOST / STpre style)."""

    def __init__(self, title: str, header: str, *, icon: str = "option",
                 parent=None, buttons=("OK", "Cancel")):
        super().__init__(parent)
        if not _HAS_QT:
            return
        self.setWindowTitle(title)
        self._applied = False
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        self.header = DialogHeader(header, icon, self)
        lay.addWidget(self.header)
        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        lay.addLayout(self.body, 1)
        self._build_body(self.body)

        brow = QHBoxLayout()
        brow.addStretch(1)
        self._buttons = {}
        for label in buttons:
            btn = QPushButton(label, self)
            if label == "OK":
                btn.setDefault(True)
                btn.clicked.connect(self._on_ok)
            elif label == "Cancel":
                btn.clicked.connect(self.reject)
            elif label == "Apply":
                btn.clicked.connect(self._on_apply)
            elif label == "Open":
                btn.setDefault(True)
                btn.clicked.connect(self._on_ok)
            else:
                handler = getattr(self, f"_on_{label.lower()}", None)
                if handler is not None:
                    btn.clicked.connect(handler)
            brow.addWidget(btn)
            self._buttons[label] = btn
        lay.addLayout(brow)

    def _build_body(self, layout: QVBoxLayout) -> None:
        """Fill the dialog body (override)."""

    def _on_apply(self) -> None:
        self._applied = True

    def _on_ok(self) -> None:
        self._on_apply()
        self.accept()


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


def file_in_summary(path) -> str:
    """File info preview for the Open dialog (scPOST File-Open right pane)."""
    try:
        from ..model.dataset import load_file
        ff = load_file(str(path))
        lines = [
            f"File size        : {ff.file_size:,} bytes",
            f"Kind             : {ff.kind.upper()}",
            f"Number of nodes  : {ff.n_vertices:,}",
            f"Element count    : {ff.n_cells:,}",
            f"Number of parts  : {len(ff.parts) if ff.parts else 0}",
            f"Surface areas    : {len(ff.surface_regions) if ff.surface_regions else 0}",
            f"Variables        : {len(ff.variables)}",
        ]
        if ff.variable_names():
            names = ff.variable_names()
            shown = ", ".join(names[:10])
            if len(names) > 10:
                shown += f" … (+{len(names) - 10})"
            lines.append(f"Var list         : {shown}")
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"size: {stat_quiet(path)}\nerror: {exc}"


def stat_quiet(path) -> str:
    try:
        n = Path(path).stat().st_size
        return f"{n:,} bytes"
    except Exception:  # noqa: BLE001
        return "?"


class OpenDialog(QDialog if _HAS_QT else object):
    """scPOST [File]-[Open]: file list + right-side file information pane."""

    def __init__(self, parent=None):
        super().__init__(parent)
        if not _HAS_QT:
            self._current = None
            return
        self.setWindowTitle("Open")
        self.resize(720, 440)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        lay.addWidget(DialogHeader("Open Field File", "open", self))

        hint = QLabel(
            "Field file (*.fld, *.fph, *.gph) — select a directory, then a file.",
            self)
        hint.setStyleSheet("color:#555; font-size:11px;")
        lay.addWidget(hint)

        split = QSplitter(Qt.Horizontal, self)
        left = QWidget(self)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        browse_row = QHBoxLayout()
        self._dir_label = QLabel("(no directory)", self)
        self._dir_label.setStyleSheet("color:#444;")
        browse_row.addWidget(self._dir_label, 1)
        btn_browse = QPushButton("Browse…", self)
        btn_browse.clicked.connect(self.browse)
        browse_row.addWidget(btn_browse)
        ll.addLayout(browse_row)
        self._list = QListWidget(self)
        ll.addWidget(self._list, 1)
        split.addWidget(left)

        right = QWidget(self)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.addWidget(QLabel("File information", right))
        self._info = QLabel("(no selection)", right)
        self._info.setWordWrap(True)
        self._info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._info.setStyleSheet(
            "background:#f7f7f7; border:1px solid #9a9a9a; padding:8px;"
            "font-family:Consolas,monospace; font-size:11px; color:#202a3a;")
        self._info.setMinimumWidth(260)
        rl.addWidget(self._info, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([400, 300])
        lay.addWidget(split, 1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        lay.addWidget(self._buttons)

        self._dirs: list[Path] = []
        self._current: Optional[Path] = None
        self._list.itemSelectionChanged.connect(self._on_select)
        self._list.itemDoubleClicked.connect(lambda _=None: self.accept())

    def browse(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Choose directory with fld/fph/gph files")
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
        if _HAS_QT:
            self._dir_label.setText(str(p))
            self._list.clear()
            for f in files:
                self._list.addItem(f.name)
            if files:
                self._list.setCurrentRow(0)
            else:
                self._info.setText("(no field files in this directory)")

    def _on_select(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._dirs):
            self._info.setText("(no selection)")
            self._current = None
            return
        path = self._dirs[row]
        self._current = path
        self._info.setText(file_in_summary(path))

    def selected_path(self) -> Optional[str]:
        return str(self._current) if self._current is not None else None
