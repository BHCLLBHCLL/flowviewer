"""scPOST-style panes: PaneFrame, MessageWindow, ObjectTree, TimelineWindow."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

try:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
        QPlainTextEdit, QPushButton, QRadioButton, QSlider, QTreeWidget,
        QTreeWidgetItem, QVBoxLayout, QWidget,
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: dict[str, QTreeWidgetItem] = {}
        if not _HAS_QT:
            return
        self.setHeaderLabels(["Object", "Status"])
        self.setColumnWidth(0, 220)
        self.setRootIsDecorated(True)
        self.setUniformRowHeights(True)
        self.itemChanged.connect(self._on_item_changed)
        self.itemDoubleClicked.connect(self._on_double_clicked)
        self.build_startup_tree()

    def build_startup_tree(self) -> None:
        """Empty-session tree matching scPOST Layout of Windows / Control Window."""
        if not _HAS_QT:
            return
        self.blockSignals(True)
        self.clear()
        self._items.clear()
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

    def clear_and_rebuild(self, root_items: list[tuple]) -> None:
        """Rebuild after loading a field file (keeps POST application chrome)."""
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
        if self.item_activated_name is not None:
            self.item_activated_name.emit(item.text(0))


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
