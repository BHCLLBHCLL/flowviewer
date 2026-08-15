"""scPOST-style panes: PaneFrame, MessageWindow, ObjectTree, TimelineWindow."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

try:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
        QPlainTextEdit, QPushButton, QRadioButton, QSlider, QSplitter,
        QSplitterHandle, QStackedWidget, QTreeWidget, QTreeWidgetItem,
        QVBoxLayout, QWidget,
    )
    _HAS_QT = True
except Exception:  # pragma: no cover - headless
    _HAS_QT = False
    QtWidgets = None
    pyqtSignal = lambda *a, **k: None  # type: ignore
    QFrame = object  # type: ignore
    QWidget = object  # type: ignore
    QPlainTextEdit = object  # type: ignore
    QTreeWidget = object  # type: ignore
    QSplitter = object  # type: ignore
    QSplitterHandle = object  # type: ignore


class PaneFrame(QFrame if _HAS_QT else object):
    """Title bar + content pane (cabdecoding / Cradle chrome)."""

    def __init__(self, title: str, content=None, parent=None):
        super().__init__(parent)
        if not _HAS_QT:
            self.body = content
            return
        self.setObjectName("PaneFrame")
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        bar = QFrame(self)
        bar.setObjectName("PaneTitleBar")
        bar.setFixedHeight(24)
        bar.setAutoFillBackground(True)
        bar.setAttribute(Qt.WA_StyledBackground, True)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(8, 0, 6, 0)
        self.title_label = QLabel(title, bar)
        self.title_label.setObjectName("PaneTitle")
        hb.addWidget(self.title_label)
        hb.addStretch(1)
        lay.addWidget(bar)
        host = QFrame(self)
        host.setObjectName("PaneBody")
        host.setAutoFillBackground(True)
        host.setAttribute(Qt.WA_StyledBackground, True)
        hl = QVBoxLayout(host)
        hl.setContentsMargins(0, 0, 0, 0)
        if content is not None:
            hl.addWidget(content, 1)
        lay.addWidget(host, 1)
        self.body = content

    def set_title(self, title: str) -> None:
        if _HAS_QT:
            self.title_label.setText(title)


class MessageWindow(QWidget if _HAS_QT else object):
    """Message Window: operation / progress / warning log."""

    def __init__(self, parent=None):
        super().__init__(parent)
        if not _HAS_QT:
            return
        v = QVBoxLayout(self)
        v.setContentsMargins(2, 2, 2, 2)
        self.text = QPlainTextEdit(self)
        self.text.setReadOnly(True)
        self.text.setMaximumBlockCount(4000)
        self.text.setPlaceholderText("Messages…")
        v.addWidget(self.text)

    def log(self, msg: str, level: str = "INFO") -> None:
        if not _HAS_QT:
            print(f"[{level}] {msg}")
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.appendPlainText(f"[{ts}] {level}: {msg}")
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def write(self, text: str) -> None:
        """Backward-compatible plain append."""
        self.log(text.rstrip("\n"), "INFO")

    def clear(self) -> None:
        if _HAS_QT:
            self.text.clear()


class ObjectTree(QTreeWidget if _HAS_QT else object):
    """Control-window object tree mirroring scPOST POST application."""

    visibility_changed = pyqtSignal(str, bool) if _HAS_QT else None
    item_activated_name = pyqtSignal(str) if _HAS_QT else None
    # kind, label  (e.g. "surface", "Surface (1)")
    object_activated = pyqtSignal(str, str) if _HAS_QT else None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: dict[str, QTreeWidgetItem] = {}
        self._object_kinds: dict[str, str] = {}
        if not _HAS_QT:
            return
        self.setHeaderLabels(["Object", "Status"])
        self.setColumnWidth(0, 240)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.itemChanged.connect(self._on_item_changed)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.build_startup_tree()

    def build_startup_tree(self) -> None:
        """Empty-session tree matching scPOST Layout of Windows / Control Window."""
        if not _HAS_QT:
            return
        self.blockSignals(True)
        self.clear()
        self._items.clear()
        self._object_kinds.clear()
        root = QTreeWidgetItem(["POST application", ""])
        root.setFlags(root.flags() & ~Qt.ItemIsUserCheckable)
        self.addTopLevelItem(root)
        self._items["POST application"] = root

        for name, checked in (
            ("Unit", False),
            ("Draw Window : DisplayList mode", True),
            ("Message Window", True),
            ("Timeline Window", True),
        ):
            it = QTreeWidgetItem([name, ""])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            it.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)
            root.addChild(it)
            self._items[name] = it

        glob = QTreeWidgetItem(["Global Objects", ""])
        glob.setFlags(glob.flags() & ~Qt.ItemIsUserCheckable)
        root.addChild(glob)
        self._items["Global Objects"] = glob
        for name in ("Option", "Camera"):
            it = QTreeWidgetItem([name, ""])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            it.setCheckState(0, Qt.Checked)
            glob.addChild(it)
            self._items[name] = it

        root.setExpanded(True)
        glob.setExpanded(True)
        self.blockSignals(False)

    def load_main(self, main) -> None:
        """Insert field-file Main node with Surface/Plane[/Particle] children.

        Layout matches scPOST Magic-open tree (screenshot)::

            POST application
              …
              ..path\\file.fph
                Surface (1)
                Plane (1)
                Particle (1)   # if particle results
              Global Objects
                Option / Camera / Light (1)
        """
        if not _HAS_QT:
            return
        from .icons import AppIcons
        self.build_startup_tree()
        root = self._items["POST application"]
        glob = self._items["Global Objects"]
        self.blockSignals(True)

        file_item = QTreeWidgetItem([main.display_name, ""])
        file_item.setFlags(
            file_item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        file_item.setCheckState(0, Qt.Checked)
        try:
            file_item.setIcon(0, AppIcons.get("project", 16))
        except Exception:
            pass
        # Insert before Global Objects
        root.insertChild(root.indexOfChild(glob), file_item)
        self._items[main.display_name] = file_item
        self._items["__main__"] = file_item
        self._object_kinds[main.display_name] = "main"

        # Folders first, then members under their folder (A3)
        folder_objs = [o for o in main.children if o.kind == "folder"]
        for obj in main.children:
            if obj.kind == "folder":
                self._add_object_item(file_item, obj)
        for obj in main.children:
            if obj.kind == "folder":
                continue
            parent = file_item
            for f in folder_objs:
                if obj.label in (f.member_labels or []):
                    parent = self._items.get(f.label, file_item)
                    break
            self._add_object_item(parent, obj)

        file_item.setExpanded(True)

        # Light (1) under Global Objects (scPOST default after open)
        light = QTreeWidgetItem(["Light (1)", ""])
        light.setFlags(light.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        light.setCheckState(0, Qt.Checked)
        try:
            light.setIcon(0, AppIcons.get("display", 16))
        except Exception:
            pass
        glob.addChild(light)
        self._items["Light (1)"] = light
        self._object_kinds["Light (1)"] = "light"
        glob.setExpanded(True)
        self.blockSignals(False)

    @staticmethod
    def _icon_for_kind(kind: str) -> str:
        return {
            "surface": "surface",
            "plane": "plane_xy",
            "particle": "point",
            "isosurface": "isosurface",
            "streamline": "streamline",
            "pathline": "streamline",
            "cylinder": "plane_xy",
            "circle": "plane_xy",
            "volume": "volume",
            "vector": "vector",
            "colorbar": "colorbar",
            "point": "point",
        }.get(kind, "project")

    def _add_object_item(self, parent, obj) -> "QTreeWidgetItem":
        """Insert one object row under *parent*, recording kind / visibility."""
        label = obj.label
        it = QTreeWidgetItem([label, ""])
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        it.setCheckState(0, Qt.Checked if obj.visible else Qt.Unchecked)
        try:
            it.setIcon(0, AppIcons.get(self._icon_for_kind(obj.kind), 16))
        except Exception:
            pass
        parent.addChild(it)
        self._items[label] = it
        self._object_kinds[label] = obj.kind
        return it

    def add_object(self, obj) -> "QTreeWidgetItem":
        """Append an object created at runtime under the current Main node."""
        if not _HAS_QT:
            return None
        file_item = self._items.get("__main__")
        if file_item is None:
            return None
        self.blockSignals(True)
        try:
            it = self._add_object_item(file_item, obj)
            file_item.setExpanded(True)
            self.setCurrentItem(it)
        finally:
            self.blockSignals(False)
        return it

    def clear_and_rebuild(self, root_items: list[tuple]) -> None:
        """Legacy rebuild helper (kept for tests / non-Main listings)."""
        if not _HAS_QT:
            return
        self.build_startup_tree()
        root = self._items["POST application"]
        self.blockSignals(True)
        for label, children in root_items:
            top = QTreeWidgetItem([label, ""])
            top.setFlags(top.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            top.setCheckState(0, Qt.Checked)
            for child in children:
                if isinstance(child, QTreeWidgetItem):
                    c = child
                else:
                    c = QTreeWidgetItem([str(child), ""])
                    c.setFlags(c.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    c.setCheckState(0, Qt.Checked)
                top.addChild(c)
            root.addChild(top)
            self._items[label] = top
            top.setExpanded(True)
        self.blockSignals(False)

    def _on_item_changed(self, item, column) -> None:
        if column != 0 or self.visibility_changed is None:
            return
        name = item.text(0)
        on = item.checkState(0) == Qt.Checked
        self.visibility_changed.emit(name, on)

    def _on_double_clicked(self, item, _column) -> None:
        name = item.text(0)
        if self.item_activated_name is not None:
            self.item_activated_name.emit(name)
        kind = self._object_kinds.get(name, "")
        if kind and self.object_activated is not None:
            self.object_activated.emit(kind, name)

    _RENDERABLE_KINDS = ("surface", "plane", "particle", "isosurface",
                         "streamline", "volume", "colorbar", "point",
                         "light", "pathline", "cylinder", "circle",
                         "text", "bitmap", "information", "mirror",
                         "timeseries", "maxmin", "graph", "grouping",
                         "curve", "periodical", "measure", "folder",
                         "bar", "regionbc", "gradation", "camera", "region",
                         "turbo", "ufo")

    def _on_selection_changed(self) -> None:
        """Single-click a renderable object → show tiled settings (scPOST)."""
        items = self.selectedItems() if _HAS_QT else []
        if not items:
            return
        name = items[0].text(0)
        kind = self._object_kinds.get(name, "")
        if kind in self._RENDERABLE_KINDS and self.object_activated:
            self.object_activated.emit(kind, name)


class DrawSplitterHandle(QSplitterHandle if _HAS_QT else object):
    """scPOST grip bar with Draw (mallet) button on the left.

    Clicking Draw commits the current settings pane and redraws the
    Draw Window — replacing per-panel Apply buttons.
    """

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        if not _HAS_QT:
            return
        from .icons import AppIcons
        self.setObjectName("DrawSplitterHandle")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 0, 4, 0)
        lay.setSpacing(4)
        self.btn_draw = QPushButton(self)
        self.btn_draw.setObjectName("DrawButton")
        self.btn_draw.setIcon(AppIcons.get("draw", 16))
        self.btn_draw.setIconSize(self.btn_draw.iconSize())
        try:
            from PyQt5.QtCore import QSize
            self.btn_draw.setIconSize(QSize(16, 16))
        except Exception:
            pass
        self.btn_draw.setFixedSize(22, 18)
        self.btn_draw.setToolTip("Draw: apply settings and redraw (scPOST)")
        self.btn_draw.setCursor(Qt.PointingHandCursor)
        self.btn_draw.setStyleSheet(
            "QPushButton#DrawButton {"
            "  border: 1px solid #9a9a9a; border-radius: 2px;"
            "  background: #f0f0f0; padding: 0;"
            "}"
            "QPushButton#DrawButton:hover { background: #e3f2fd;"
            "  border-color: #90caf9; }"
            "QPushButton#DrawButton:pressed { background: #bbdefb; }"
        )
        self.btn_draw.clicked.connect(self._emit_draw)
        lay.addWidget(self.btn_draw, 0, Qt.AlignLeft | Qt.AlignVCenter)
        # Grip hint (double embossed line feel)
        grip = QLabel("══", self)
        grip.setStyleSheet("color:#9a9a9a; font-size:9px;")
        lay.addWidget(grip, 0, Qt.AlignVCenter)
        lay.addStretch(1)
        self.setStyleSheet(
            "#DrawSplitterHandle { background: #d8d8d8;"
            "  border-top: 1px solid #9a9a9a;"
            "  border-bottom: 1px solid #9a9a9a; }"
        )

    def _emit_draw(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "draw_requested"):
            parent.draw_requested.emit()

    def sizeHint(self):
        from PyQt5.QtCore import QSize
        if self.orientation() == Qt.Horizontal:
            return QSize(6, 22)
        return QSize(22, 22)


class DrawSplitter(QSplitter if _HAS_QT else object):
    """Vertical splitter whose handle carries the scPOST Draw button."""

    draw_requested = pyqtSignal() if _HAS_QT else None

    def __init__(self, orientation=None, parent=None):
        if not _HAS_QT:
            super().__init__()
            return
        if orientation is None:
            orientation = Qt.Vertical
        super().__init__(orientation, parent)
        self.setHandleWidth(22)
        self.setChildrenCollapsible(False)

    def createHandle(self):  # noqa: N802 — Qt API
        return DrawSplitterHandle(self.orientation(), self)


class PropertyHost(QWidget if _HAS_QT else object):
    """Lower half of Control Window — hosts tiled Surface/Plane/Particle sheets.

    Replaces modal popups: selecting a tree object fills this pane.
    """

    applied = pyqtSignal(object) if _HAS_QT else None  # after Draw / apply
    hidden = pyqtSignal() if _HAS_QT else None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._obj = None
        self._panel = None
        self._kind = ""
        if not _HAS_QT:
            return
        self.setObjectName("PaneFrame")
        self.setAutoFillBackground(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._stack = QStackedWidget(self)
        self._empty = QLabel(
            "Select Surface / Plane / Particle\nin the tree above", self)
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setStyleSheet("color:#666; font-size:11px;")
        self._stack.addWidget(self._empty)
        lay.addWidget(self._stack, 1)

    @property
    def current_object(self):
        return self._obj

    @property
    def current_panel(self):
        return self._panel

    def clear(self) -> None:
        if not _HAS_QT:
            return
        if self._panel is not None:
            self._stack.removeWidget(self._panel)
            self._panel.deleteLater()
        self._panel = None
        self._obj = None
        self._kind = ""
        self._stack.setCurrentWidget(self._empty)

    def show_object(self, kind: str, obj, field_file=None,
                    siblings=None) -> None:
        """Embed Surface/Plane/Particle settings panel for *obj*."""
        if not _HAS_QT:
            return
        from .object_dialogs import ParticleDialog, PlaneDialog, SurfaceDialog
        from .object_dialogs2 import (
            BarDialog, BitmapDialog, CameraDialog, CircleDialog, ColorbarDialog,
            CurveDialog, RegionDialog, TurboDialog, UFODialog,
            GradationDialog, RegionBCDialog,
            CylinderDialog, GraphDialog, GroupingDialog, InformationDialog,
            IsosurfaceDialog, LightDialog, MaxMinDialog, MeasureDialog,
            MirrorCopyDialog, PathlineDialog, PeriodicalCopyDialog,
            PointDialog, StreamlineDialog, TextDialog, TimeSeriesDialog,
            VolumeDialog,
        )
        cls = {
            "surface": SurfaceDialog,
            "plane": PlaneDialog,
            "particle": ParticleDialog,
            "isosurface": IsosurfaceDialog,
            "point": PointDialog,
            "streamline": StreamlineDialog,
            "volume": VolumeDialog,
            "colorbar": ColorbarDialog,
            "light": LightDialog,
            "pathline": PathlineDialog,
            "cylinder": CylinderDialog,
            "circle": CircleDialog,
            "text": TextDialog,
            "bitmap": BitmapDialog,
            "information": InformationDialog,
            "mirror": MirrorCopyDialog,
            "curve": CurveDialog,
            "timeseries": TimeSeriesDialog,
            "maxmin": MaxMinDialog,
            "graph": GraphDialog,
            "grouping": GroupingDialog,
            "folder": GroupingDialog,
            "periodical": PeriodicalCopyDialog,
            "measure": MeasureDialog,
            "bar": BarDialog,
            "regionbc": RegionBCDialog,
            "gradation": GradationDialog,
            "camera": CameraDialog,
            "region": RegionDialog,
            "turbo": TurboDialog,
            "ufo": UFODialog,
        }.get(kind)
        if cls is None:
            return
        # Reuse panel if same object already shown
        if self._obj is obj and self._panel is not None:
            self._stack.setCurrentWidget(self._panel)
            return
        self.clear()
        panel = cls(obj, field_file=field_file, parent=self)
        panel.apply_requested.connect(self._on_apply)
        panel.close_requested.connect(self._on_hide)
        # Trim "Trimmed by" needs the sibling objects (F-gap)
        if siblings:
            panel._trim_objects = list(siblings)
        else:
            panel._trim_objects = [o for o in
                                   getattr(field_file, "_siblings", []) or []]
            if not panel._trim_objects:
                panel._trim_objects = []
        self._panel = panel
        self._obj = obj
        self._kind = kind
        self._stack.addWidget(panel)
        self._stack.setCurrentWidget(panel)

    def apply_now(self) -> bool:
        """Commit current panel → object and emit ``applied`` (Draw button).

        Returns True if a panel was applied.  Unpinned panels close after
        Draw so the Draw Window stays readable (scPOST pin behaviour).
        """
        if self._panel is None or self._obj is None:
            return False
        if hasattr(self._panel, "apply_to"):
            self._panel.apply_to(self._obj)
        if self.applied is not None:
            self.applied.emit(self._obj)
        panel = self._panel
        if panel is not None and not panel.is_pinned():
            self._on_hide()
        return True

    def _on_apply(self) -> None:
        """Legacy slot (panel apply_requested); prefer ``apply_now`` / Draw."""
        self.apply_now()

    def _on_hide(self) -> None:
        self.clear()
        if self.hidden is not None:
            self.hidden.emit()


class TimelineWindow(QWidget if _HAS_QT else object):
    """scPOST Timeline Window: Static / Cycle / Time + playback + slider."""

    mode_changed = pyqtSignal(str) if _HAS_QT else None
    step_changed = pyqtSignal(int) if _HAS_QT else None
    play_requested = pyqtSignal() if _HAS_QT else None
    pause_requested = pyqtSignal() if _HAS_QT else None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0
        self._max = 0
        self._playing = False
        if not _HAS_QT:
            return

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 4, 6, 4)
        root.setSpacing(4)

        row1 = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        for i, label in enumerate(("Static", "Cycle", "Time")):
            rb = QRadioButton(label, self)
            if i == 0:
                rb.setChecked(True)
            self._mode_group.addButton(rb, i)
            row1.addWidget(rb)
        self._mode_group.buttonClicked.connect(self._on_mode)
        row1.addSpacing(12)
        self.chk_preview = QCheckBox("Preview", self)
        self.chk_preview.setChecked(True)
        self.chk_sync = QCheckBox("Sync", self)
        self.chk_loop = QCheckBox("Loop", self)
        for w in (self.chk_preview, self.chk_sync, self.chk_loop):
            row1.addWidget(w)
        row1.addStretch(1)
        root.addLayout(row1)

        row2 = QHBoxLayout()
        self.btn_start = QPushButton("|◀", self)
        self.btn_prev = QPushButton("◀", self)
        self.btn_play = QPushButton("▶", self)
        self.btn_pause = QPushButton("❚❚", self)
        self.btn_next = QPushButton("▶|", self)
        self.btn_end = QPushButton("▶|", self)
        # Distinguish next-step vs jump-end visually
        self.btn_next.setText("›")
        self.btn_end.setText("»")
        self.btn_start.setText("«")
        self.btn_prev.setText("‹")
        for b in (self.btn_start, self.btn_prev, self.btn_play,
                  self.btn_pause, self.btn_next, self.btn_end):
            b.setFixedWidth(32)
            row2.addWidget(b)
        row2.addStretch(1)
        root.addLayout(row2)

        self.lbl_range = QLabel("MIN — MAX", self)
        self.lbl_range.setStyleSheet("color:#555; font-size:11px;")
        root.addWidget(self.lbl_range)

        self.slider = QSlider(Qt.Horizontal, self)
        self.slider.setRange(0, 0)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._on_slider)
        root.addWidget(self.slider)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Step", self))
        self.edit_step = QLineEdit("0", self)
        self.edit_step.setFixedWidth(56)
        row3.addWidget(self.edit_step)
        row3.addWidget(QLabel("Ver", self))
        self.edit_ver = QLineEdit("0", self)
        self.edit_ver.setFixedWidth(48)
        row3.addWidget(self.edit_ver)
        row3.addWidget(QLabel("Time", self))
        self.edit_time = QLineEdit("0", self)
        self.edit_time.setFixedWidth(72)
        row3.addWidget(self.edit_time)
        row3.addWidget(QLabel("Scale", self))
        self.edit_scale = QLineEdit("1", self)
        self.edit_scale.setFixedWidth(48)
        row3.addWidget(self.edit_scale)
        self.btn_set = QPushButton("Set", self)
        self.btn_set.clicked.connect(self._on_set)
        row3.addWidget(self.btn_set)
        row3.addStretch(1)
        root.addLayout(row3)

        self.btn_start.clicked.connect(lambda: self._jump(self._min))
        self.btn_end.clicked.connect(lambda: self._jump(self._max))
        self.btn_prev.clicked.connect(lambda: self._nudge(-1))
        self.btn_next.clicked.connect(lambda: self._nudge(1))
        self.btn_play.clicked.connect(self._on_play)
        self.btn_pause.clicked.connect(self._on_pause)

    def set_range(self, lo: int, hi: int) -> None:
        self._min = int(lo)
        self._max = int(hi)
        if not _HAS_QT:
            return
        self.slider.blockSignals(True)
        self.slider.setRange(self._min, max(self._min, self._max))
        self.slider.setEnabled(self._max > self._min)
        self.slider.blockSignals(False)
        self.lbl_range.setText(f"MIN {self._min}    MAX {self._max}")
        self.edit_step.setText(str(self._min))

    def set_step(self, step: int) -> None:
        if not _HAS_QT:
            return
        step = max(self._min, min(self._max, int(step)))
        self.slider.blockSignals(True)
        self.slider.setValue(step)
        self.slider.blockSignals(False)
        self.edit_step.setText(str(step))

    def current_step(self) -> int:
        if not _HAS_QT:
            return 0
        return int(self.slider.value())

    def mode(self) -> str:
        if not _HAS_QT:
            return "Static"
        btn = self._mode_group.checkedButton()
        return btn.text() if btn else "Static"

    def _on_mode(self, _btn) -> None:
        if self.mode_changed is not None:
            self.mode_changed.emit(self.mode())

    def _on_slider(self, value: int) -> None:
        self.edit_step.setText(str(value))
        if self.chk_preview.isChecked() and self.step_changed is not None:
            self.step_changed.emit(int(value))

    def _on_set(self) -> None:
        try:
            step = int(self.edit_step.text().strip())
        except ValueError:
            return
        self.set_step(step)
        if self.step_changed is not None:
            self.step_changed.emit(self.current_step())

    def _jump(self, value: int) -> None:
        self.set_step(value)
        if self.step_changed is not None:
            self.step_changed.emit(self.current_step())

    def _nudge(self, delta: int) -> None:
        self._jump(self.current_step() + delta)

    def _on_play(self) -> None:
        self._playing = True
        if self.play_requested is not None:
            self.play_requested.emit()

    def _on_pause(self) -> None:
        self._playing = False
        if self.pause_requested is not None:
            self.pause_requested.emit()
