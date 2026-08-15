"""scPOST-style dialogs: DialogHeader, PostDialogBase, OpenDialog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from PyQt5 import QtWidgets
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
        QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
        QSplitter, QVBoxLayout, QWidget,
    )
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    _HAS_QT = False
    QtWidgets = None
    QDialog = object  # type: ignore
    QWidget = object  # type: ignore


# ---------------------------------------------------------------------------
# File-type filters — scPOST [File]-[Open] "Files of type" (2025.2 UI)
# ---------------------------------------------------------------------------

# (label, extensions without dot, lowercase for matching)
FILE_TYPE_FILTERS: list[tuple[str, tuple[str, ...]]] = [
    ("Field files",
     ("fld", "ifld", "fph", "gph", "pph", "cgns", "xmf", "xdmf")),
    ("Time series files", ("tm", "csv")),
    ("Status files", ("sta",)),
    ("Neutral files", ("neu", "nfb", "stl", "gbf", "obj")),
    ("IPC2581 files", ("xml", "cvg")),
    ("Variable list files", ("hen",)),
    ("Initialization files", ("ini", "env", "xenv")),
    ("XEMT/XML/EMT files", ("xemt", "xml", "emt")),
    ("OT files", ("ot",)),
    ("VIEW Files", ("xview", "view")),
    ("PCL files", ("pcl",)),
    ("Solution files", ("csln",)),
    ("3D-ROM files", ("3dr",)),
    ("Adams Solver Dataset files", ("adm",)),
    ("Marc post files", ("t16", "t19")),
    ("Nastran files", ("h5", "nas", "dat", "bdf")),
    ("Parasolid files", ("xmt_txt", "x_t", "xmt_bin", "x_b")),
]

# Currently loadable by flowviewer core (others accepted in dialog, then NYI).
# Kept for backward compatibility; prefer :func:`loadable_extensions`, which
# derives the set from the live loader registry (P0.6: .emt/.cgns/… drift).
LOADABLE_EXTENSIONS = frozenset({"fld", "ifld", "fph", "gph", "pph"})


def loadable_extensions() -> frozenset[str]:
    """Extensions with real loaders, from :mod:`fv.model.loaders`.

    Importing :mod:`fv.model.dataset` triggers loader registration, so the
    dialog's info pane and the registry can never drift apart again.
    """
    try:
        from ..model import dataset  # noqa: F401  (registers loaders)
        from ..model import loaders
        exts = loaders.loaders()
        if exts:
            return exts
    except Exception:  # pragma: no cover - registry is best-effort
        pass
    return LOADABLE_EXTENSIONS


def _filter_label(name: str, exts: tuple[str, ...]) -> str:
    """scPOST-style display label: ``Field files (*.fld; *.iFLD; …)``."""
    parts = []
    for e in exts:
        if e == "ifld":
            parts.append("*.iFLD")
        else:
            parts.append(f"*.{e}")
    return f"{name} ({'; '.join(parts)})"


def _qt_name_filter(name: str, exts: tuple[str, ...]) -> str:
    """QFileDialog name-filter entry (space-separated patterns)."""
    parts = []
    for e in exts:
        if e == "ifld":
            parts.append("*.iFLD")
            parts.append("*.ifld")
        else:
            parts.append(f"*.{e}")
    return f"{name} ({' '.join(parts)})"


def qt_file_filters(selected_index: int = 0) -> tuple[str, str]:
    """Return ``(all_filters, selected_filter)`` for ``QFileDialog``.

    Qt separates filter *groups* with ``;;``.  Joining groups with a single
    ``;`` (as in an earlier bug) collapses everything into one broken filter
    so ``*.fph`` never matches in the native Browse / Open dialog.
    """
    parts = [_qt_name_filter(n, e) for n, e in FILE_TYPE_FILTERS]
    parts.append("All files (*)")
    idx = min(max(0, int(selected_index)), len(parts) - 1)
    return ";;".join(parts), parts[idx]


def filter_extensions(index: int) -> frozenset[str]:
    if 0 <= index < len(FILE_TYPE_FILTERS):
        return frozenset(FILE_TYPE_FILTERS[index][1])
    return frozenset()


@dataclass
class OpenOptions:
    """Import options from scPOST [File]-[Open] checkboxes."""

    close_current: bool = False
    accelerate_memory: bool = True
    read_faster: bool = True
    magic_open: bool = False
    trimming_open: bool = False
    remote_open: bool = False
    filter_index: int = 0
    filter_name: str = "Field files"

    def summary_lines(self) -> list[str]:
        flags = []
        if self.close_current:
            flags.append("close current files")
        if self.accelerate_memory:
            flags.append("accelerate (hash table)")
        if self.read_faster:
            flags.append("read faster (estimate size)")
        if self.magic_open:
            flags.append("magic open")
        if self.trimming_open:
            flags.append("trimming open")
        if self.remote_open:
            flags.append("remote open")
        return flags


# ---------------------------------------------------------------------------
# Shared dialog chrome
# ---------------------------------------------------------------------------


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
    return file_in_summary(filepath)


def file_in_summary(path) -> str:
    """File info preview for the Open dialog (scPOST File-Open info pane)."""
    p = Path(path)
    ext = _suffix_key(p)
    if ext not in loadable_extensions():
        return "\n".join([
            f"File name        : {p.name}",
            f"File size        : {stat_quiet(p)}",
            f"Extension        : .{ext or '?'}",
            "",
            "(Preview for this type is not available yet.",
            " Open is reserved; loader support is planned.)",
        ])
    try:
        from ..model.dataset import load_file
        ff = load_file(str(p))
        lines = [
            f"File size        : {ff.file_size:,} bytes",
            f"Kind             : {ff.kind.upper()}",
            f"Number of nodes  : {ff.n_vertices:,}",
            f"Element count    : {ff.n_cells:,}",
            f"Number of parts  : {len(ff.parts) if ff.parts else 0}",
            f"Surface areas    : "
            f"{len(ff.surface_regions) if ff.surface_regions else 0}",
            f"Variables        : {len(ff.variables)}",
        ]
        if ff.poly and ff.link_data is not None:
            n_faces = max(0, len(ff.link_data.get("neighbour", [])) )
            lines.insert(4, f"Number of faces  : {n_faces:,}")
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


def _suffix_key(path: Path) -> str:
    """Return lowercase extension key; handle multi-part Parasolid names."""
    name = path.name.lower()
    for multi in ("xmt_txt", "xmt_bin", "x_t", "x_b"):
        if name.endswith("." + multi):
            return multi
    return path.suffix.lower().lstrip(".")


# ---------------------------------------------------------------------------
# Open dialog
# ---------------------------------------------------------------------------


class OpenDialog(QDialog if _HAS_QT else object):
    """scPOST [File]-[Open]: filters, import options, file information."""

    def __init__(self, parent=None, start_dir: Optional[str] = None):
        super().__init__(parent)
        self._dirs: list[Path] = []
        self._current: Optional[Path] = None
        self._dirpath: Optional[Path] = None
        if not _HAS_QT:
            return

        self.setWindowTitle("Open")
        self.resize(820, 520)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        lay.addWidget(DialogHeader("Open", "open", self))

        # Look in
        look = QHBoxLayout()
        look.addWidget(QLabel("Look in:", self))
        self._dir_edit = QLineEdit(self)
        self._dir_edit.setPlaceholderText("Directory path")
        self._dir_edit.returnPressed.connect(self._on_dir_entered)
        look.addWidget(self._dir_edit, 1)
        btn_up = QPushButton("Up", self)
        btn_up.setFixedWidth(40)
        btn_up.setToolTip("Go to parent folder")
        btn_up.clicked.connect(self._go_up)
        look.addWidget(btn_up)
        btn_browse = QPushButton("Browse…", self)
        btn_browse.clicked.connect(self.browse)
        look.addWidget(btn_browse)
        lay.addLayout(look)

        split = QSplitter(Qt.Horizontal, self)

        # Left: file list
        left = QWidget(self)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget(self)
        self._list.itemSelectionChanged.connect(self._on_select)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        ll.addWidget(self._list, 1)
        split.addWidget(left)

        # Right: file information
        right = QWidget(self)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.addWidget(QLabel("File information", right))
        self._info = QLabel(
            "Select a field file to show size / nodes / elements / …",
            right)
        self._info.setWordWrap(True)
        self._info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._info.setStyleSheet(
            "background:#f7f7f7; border:1px solid #9a9a9a; padding:8px;"
            "font-family:Consolas,monospace; font-size:11px; color:#202a3a;")
        self._info.setMinimumWidth(280)
        rl.addWidget(self._info, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([480, 320])
        lay.addWidget(split, 1)

        # File name + type + buttons (scPOST bottom row)
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        form.addWidget(QLabel("File name:", self), 0, 0)
        self._name_edit = QLineEdit(self)
        self._name_edit.returnPressed.connect(self._try_accept)
        form.addWidget(self._name_edit, 0, 1)
        self._btn_open = QPushButton("Open", self)
        self._btn_open.setDefault(True)
        self._btn_open.clicked.connect(self._try_accept)
        form.addWidget(self._btn_open, 0, 2)
        form.addWidget(QLabel("Files of type:", self), 1, 0)
        self._type_combo = QComboBox(self)
        for name, exts in FILE_TYPE_FILTERS:
            self._type_combo.addItem(_filter_label(name, exts))
        self._type_combo.currentIndexChanged.connect(self._on_filter_changed)
        form.addWidget(self._type_combo, 1, 1)
        self._btn_cancel = QPushButton("Cancel", self)
        self._btn_cancel.clicked.connect(self.reject)
        form.addWidget(self._btn_cancel, 1, 2)
        form.setColumnStretch(1, 1)
        lay.addLayout(form)

        # Import options (scPOST Open checkboxes)
        opts = QGroupBox("Import options", self)
        og = QVBoxLayout(opts)
        og.setSpacing(2)
        og.setContentsMargins(8, 6, 8, 6)
        self.chk_close_current = QCheckBox(
            "Read field file after closing current files", opts)
        self.chk_accelerate = QCheckBox(
            "Accelerate using more memory (create a hash table)", opts)
        self.chk_accelerate.setChecked(True)
        self.chk_read_faster = QCheckBox(
            "Read faster by estimating the file size "
            "(for old field file only)", opts)
        self.chk_read_faster.setChecked(True)
        self.chk_magic = QCheckBox(
            "Magic open (Automatic set plane and streamline)", opts)
        self.chk_trimming = QCheckBox(
            "Trimming Open (Low memory)", opts)
        self.chk_remote = QCheckBox(
            "Remote Open (Partial plotting)", opts)
        for w in (
            self.chk_close_current, self.chk_accelerate, self.chk_read_faster,
            self.chk_magic, self.chk_trimming, self.chk_remote,
        ):
            w.setStyleSheet("color:#333; font-size:11px;")
            og.addWidget(w)
        tip = QLabel(
            "Note: Magic / Trimming / Remote open are reserved (P4); "
            "FLD·FPH·GPH loaders ignore unsupported flags for now.",
            opts)
        tip.setStyleSheet("color:#666; font-size:10px;")
        tip.setWordWrap(True)
        og.addWidget(tip)
        lay.addWidget(opts)

        if start_dir:
            self.load_directory(start_dir)
        else:
            self.load_directory(str(Path.cwd()))

    # ── options / selection ───────────────────────────────────────────────

    def open_options(self) -> OpenOptions:
        idx = self._type_combo.currentIndex() if _HAS_QT else 0
        name = FILE_TYPE_FILTERS[idx][0] if FILE_TYPE_FILTERS else "Field files"
        if not _HAS_QT:
            return OpenOptions(filter_index=idx, filter_name=name)
        return OpenOptions(
            close_current=self.chk_close_current.isChecked(),
            accelerate_memory=self.chk_accelerate.isChecked(),
            read_faster=self.chk_read_faster.isChecked(),
            magic_open=self.chk_magic.isChecked(),
            trimming_open=self.chk_trimming.isChecked(),
            remote_open=self.chk_remote.isChecked(),
            filter_index=idx,
            filter_name=name,
        )

    def selected_path(self) -> Optional[str]:
        if self._current is not None:
            return str(self._current)
        if not _HAS_QT:
            return None
        name = self._name_edit.text().strip().strip('"')
        if not name or self._dirpath is None:
            return None
        p = Path(name)
        if not p.is_absolute():
            p = self._dirpath / name
        return str(p) if p.is_file() else None

    def is_loadable(self, path: Optional[str] = None) -> bool:
        p = Path(path or self.selected_path() or "")
        from ..model import loaders
        return loaders.can_load(str(p))

    # ── directory / filter ────────────────────────────────────────────────

    def browse(self) -> None:
        """Open a file picker (shows *.fph etc.) — not a directory-only dialog.

        Selecting a file updates Look-in + the list and pre-selects that file.
        """
        start = str(self._dirpath) if self._dirpath else str(Path.cwd())
        filters, selected = qt_file_filters(self._type_combo.currentIndex())
        path, chosen = QFileDialog.getOpenFileName(
            self, "Open Field File", start, filters, selected)
        if not path:
            return
        p = Path(path)
        # Sync "Files of type" when the user changed the native filter
        if chosen:
            for i in range(self._type_combo.count()):
                if self._type_combo.itemText(i).split(" (")[0] == chosen.split(" (")[0]:
                    self._type_combo.blockSignals(True)
                    self._type_combo.setCurrentIndex(i)
                    self._type_combo.blockSignals(False)
                    break
        self.load_directory(str(p.parent))
        for i, entry in enumerate(self._dirs):
            if entry.resolve() == p.resolve() or entry.name.lower() == p.name.lower():
                self._list.setCurrentRow(i)
                break
        else:
            self._current = p
            self._name_edit.setText(p.name)
            self._info.setText(file_in_summary(p))


    def _on_dir_entered(self) -> None:
        text = self._dir_edit.text().strip().strip('"')
        if text:
            self.load_directory(text)

    def _go_up(self) -> None:
        if self._dirpath is not None and self._dirpath.parent != self._dirpath:
            self.load_directory(str(self._dirpath.parent))

    def load_directory(self, dirpath: str) -> None:
        p = Path(dirpath)
        if not p.is_dir():
            if _HAS_QT:
                self._info.setText(f"(not a directory: {dirpath})")
            return
        self._dirpath = p
        if _HAS_QT:
            self._dir_edit.setText(str(p))
        self._refresh_list()

    def _on_filter_changed(self, _index: int = 0) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        if self._dirpath is None or not _HAS_QT:
            return
        exts = filter_extensions(self._type_combo.currentIndex())
        entries: list[Path] = []
        try:
            children = list(self._dirpath.iterdir())
        except OSError as exc:
            self._info.setText(f"(cannot read directory: {exc})")
            self._dirs = []
            self._list.clear()
            return
        # folders first, then matching files
        folders = sorted(
            [c for c in children if c.is_dir()],
            key=lambda f: f.name.lower())
        files = sorted(
            [c for c in children
             if c.is_file() and _suffix_key(c) in exts],
            key=lambda f: f.name.lower())
        self._dirs = folders + files
        self._list.clear()
        for f in self._dirs:
            self._list.addItem(f"[{f.name}]" if f.is_dir() else f.name)
        if files:
            # select first file
            self._list.setCurrentRow(len(folders))
        elif not folders:
            self._info.setText(
                f"(no {_filter_label(*FILE_TYPE_FILTERS[self._type_combo.currentIndex()])} "
                f"in this directory)")
            self._current = None

    def _on_select(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._dirs):
            self._info.setText("(no selection)")
            self._current = None
            return
        path = self._dirs[row]
        if path.is_dir():
            self._current = None
            self._name_edit.clear()
            self._info.setText(f"Folder: {path.name}\nDouble-click to open.")
            return
        self._current = path
        self._name_edit.setText(path.name)
        self._info.setText(file_in_summary(path))

    def _on_double_click(self, _item=None) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._dirs):
            return
        path = self._dirs[row]
        if path.is_dir():
            self.load_directory(str(path))
        else:
            self._try_accept()

    def _try_accept(self) -> None:
        # Resolve from name edit if needed
        name = self._name_edit.text().strip().strip('"')
        if name and self._dirpath is not None:
            p = Path(name)
            if not p.is_absolute():
                p = self._dirpath / name
            if p.is_file():
                self._current = p
        if self._current is None or not self._current.is_file():
            self._info.setText("(select a file to open)")
            return
        self.accept()


class EnvironmentDialog(PostDialogBase):
    """Option → Environment Settings: background + status/units display."""

    def __init__(self, parent=None):
        super().__init__("Environment Settings",
                         "Environment Settings",
                         icon="option",
                         parent=parent,
                         buttons=("OK", "Cancel"))
        if not _HAS_QT:
            return

    def _build_body(self, layout: QVBoxLayout) -> None:
        group = QGroupBox("Draw", self)
        g = QVBoxLayout(group)
        self.chk_bggrad = QCheckBox("Use gradient background", self)
        self.chk_bggrad.setChecked(True)
        g.addWidget(self.chk_bggrad)
        self.chk_status = QCheckBox("Show status bar", self)
        self.chk_status.setChecked(True)
        g.addWidget(self.chk_status)
        self.chk_units = QCheckBox("Display units in status bar", self)
        self.chk_units.setChecked(True)
        g.addWidget(self.chk_units)
        layout.addWidget(group)
        hint = QLabel(
            "These settings apply to the Draw Window/status display.",
            self)
        hint.setStyleSheet("color:#666; font-size:11px;")
        layout.addWidget(hint)

    def _on_ok(self) -> None:
        self._applied = True
        parent = self.parent()
        if parent is not None and hasattr(parent, "statusBar"):
            parent.statusBar().setVisible(self.chk_status.isChecked())
        self.accept()


class VariableRegistrationDialog(QDialog):
    """scPOST Main > Variable Registration (P1.1).

    Defines a derived variable from a safe arithmetic expression over
    the loaded variables (see 'fv.model.varreg').  Live preview shows
    min/max or the parse error; Apply registers the variable on the
    FieldFile so every object's variable list picks it up.
    """

    def __init__(self, field_file, parent=None):
        super().__init__(parent)
        if not _HAS_QT:
            self.field_file = field_file
            return
        self.field_file = field_file
        self.setWindowTitle("Variable Registration")
        self.resize(560, 380)
        lay = QVBoxLayout(self)

        row = QHBoxLayout()
        self.var_list = QListWidget(self)
        for name in sorted(field_file.variable_names()):
            self.var_list.addItem(name)
        self.var_list.itemDoubleClicked.connect(self._insert_var)
        row.addWidget(self.var_list, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Expression:", self))
        self.expr = QLineEdit(self)
        right.addWidget(self.expr)
        right.addWidget(QLabel("Result name:", self))
        self.result_name = QLineEdit(self)
        self.result_name.setPlaceholderText("e.g. DP")
        right.addWidget(self.result_name)
        self.preview = QLabel(" ", self)
        self.preview.setStyleSheet("color:#666; font-size:11px;")
        self.preview.setWordWrap(True)
        right.addWidget(self.preview)
        hint = QLabel(
            "Ops: + - * / ^ & @  |  fns: abs sqrt log exp sin min max "
            "mag(V) ifgt/ifet/ifeq/iflt/ifle/ifne(a,b) "
            "delx/dely/delz(V) grad(V) div(V) rot(V)", self)
        hint.setStyleSheet("color:#888; font-size:10px;")
        right.addWidget(hint)
        right.addStretch(1)
        row.addLayout(right, 2)
        lay.addLayout(row)

        self.expr.textChanged.connect(self._update_preview)

        btns = QHBoxLayout()
        self.btn_apply = QPushButton("Apply", self)
        self.btn_apply.clicked.connect(self._on_apply)
        btn_cancel = QPushButton("Close", self)
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(self.btn_apply)
        btns.addWidget(btn_cancel)
        lay.addLayout(btns)

    def _insert_var(self, item) -> None:
        """Double-click a variable to insert its name at the cursor."""
        self.expr.insert(str(item.text()))

    def _update_preview(self) -> None:
        expr = self.expr.text().strip()
        if not expr:
            self.preview.setText(" ");
            return
        try:
            from ..model.varreg import _resolved_vars, evaluate_expression
            ff = self.field_file
            variables = _resolved_vars(ff)
            n = 0
            for a in variables.values():
                if a is not None and getattr(a, "size", 0):
                    n = int(a.shape[0]);
                    break
            if n == 0:
                n = ff.n_vertices or ff.n_cells
            arr = evaluate_expression(expr, variables, max(1, n))
            self.preview.setText(
                f"OK: min={float(arr.min()):.6g} max={float(arr.max()):.6g}")
        except Exception as exc:
            self.preview.setText(f"Error: {exc}")

    def _on_apply(self) -> None:
        name = self.result_name.text().strip()
        expr = self.expr.text().strip()
        if not name or not expr:
            self.preview.setText("Enter a result name and an expression.");
            return
        try:
            from ..model.varreg import register_variable
            register_variable(self.field_file, name, expr)
        except Exception as exc:
            self.preview.setText(f"Error: {exc}");
            return
        self.preview.setText(f"Registered: {name}");
        self.result_name.clear()
        self.var_list.addItem(name)
        if self.parent() is not None and hasattr(self.parent(),
                "message_win"):
            self.parent().message_win.log(f"Registered variable {name}")
        if self.parent() is not None and hasattr(self.parent(),
                "status"):
            self.parent().status.showMessage(f"Registered {name}", 3000)

class CompareDialog(QDialog):
    """Side-by-side comparison of two datasets (G2).

    Two render windows share one vtkCamera so navigation stays in sync;
    headless mode falls back to labelled placeholders.
    """

    def __init__(self, dataset_a, dataset_b, parent=None,
                 enable_3d: bool = True):
        super().__init__(parent)
        if not _HAS_QT:
            self.dataset_a = dataset_a;
            self.dataset_b = dataset_b
            return
        from pathlib import Path
        self.setWindowTitle("Compare — "
                         + Path(dataset_a.path).name
                         + "  vs  " + Path(dataset_b.path).name)
        self.resize(1200, 620)
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal, self)
        lay.addWidget(split)
        cam = None
        for ff in (dataset_a, dataset_b):
            pane = QWidget(split)
            vbox = QVBoxLayout(pane)
            title = QLabel(Path(ff.path).name, pane)
            title.setStyleSheet("font-weight:bold;");
            vbox.addWidget(title)
            if enable_3d:
                try:
                    from vtk.qt.QVTKRenderWindowInteractor import (
                        QVTKRenderWindowInteractor)
                    from ..render.scene import Scene
                    from ..model.objects import MainObject
                    widget = QVTKRenderWindowInteractor(pane)
                    sc = Scene(enable_3d=True)
                    sc.build(ff, main=MainObject.from_field_file(ff))
                    rw = widget.GetRenderWindow()
                    rw.AddRenderer(sc.renderer)
                    if cam is not None:
                        sc.renderer.SetActiveCamera(cam)
                    else:
                        cam = sc.renderer.GetActiveCamera()
                    widget.Initialize();
                    widget.Start()
                    vbox.addWidget(widget)
                except Exception:  # pragma: no cover - GL unavailable
                    vbox.addWidget(QLabel("3D unavailable", pane))
            else:
                vbox.addWidget(QLabel("3D disabled (headless)", pane))
            split.addWidget(pane)
        split.setSizes([600, 600])
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept);
        lay.addWidget(close, 0, Qt.AlignRight)
