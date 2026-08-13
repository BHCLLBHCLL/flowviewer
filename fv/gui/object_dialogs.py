"""Property dialogs for Surface / Plane / Particle (scPOST-style tabs)."""

from __future__ import annotations

from typing import Optional

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QButtonGroup, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
        QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
        QPushButton, QRadioButton, QSlider, QSpinBox, QTabWidget,
        QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QColorDialog,
    )
    from PyQt5.QtGui import QColor
    _HAS_QT = True
except Exception:  # pragma: no cover
    _HAS_QT = False
    QDialog = object  # type: ignore


def _scalar_vars(ff) -> list[str]:
    if ff is None:
        return []
    return sorted(n for n, v in ff.variables.items() if v.kind == "scalar")


def _vector_vars(ff) -> list[str]:
    if ff is None:
        return []
    return sorted(n for n, v in ff.variables.items() if v.kind == "vector")


def _mat_numbers(ff) -> list[int]:
    if ff is None or ff.material is None:
        return []
    import numpy as np
    return sorted(int(m) for m in np.unique(ff.material))


class _ColorButton(QPushButton if _HAS_QT else object):
    """Push button acting as a color swatch + picker."""

    def __init__(self, rgb=(1.0, 1.0, 1.0), parent=None):
        super().__init__(parent)
        self._rgb = tuple(rgb)
        self._refresh()
        self.clicked.connect(self._pick)

    def _refresh(self) -> None:
        r, g, b = (int(min(1.0, max(0.0, c)) * 255) for c in self._rgb)
        self.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); min-height: 22px;")

    def _pick(self) -> None:
        r, g, b = (int(min(1.0, max(0.0, c)) * 255) for c in self._rgb)
        col = QColorDialog.getColor(QColor(r, g, b), self, "Select color")
        if col.isValid():
            self._rgb = (col.redF(), col.greenF(), col.blueF())
            self._refresh()

    def rgb(self) -> tuple[float, float, float]:
        return self._rgb


class _VarRow(QWidget if _HAS_QT else object):
    """Display checkbox + Variable combo (data-filtering row)."""

    def __init__(self, title: str, variables: list[str], value: str = "",
                 parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.check = QCheckBox(title)
        lay.addWidget(self.check)
        lay.addWidget(QLabel("Variable:"))
        self.combo = QComboBox()
        for n in variables:
            self.combo.addItem(n, n)
        idx = self.combo.findData(value)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        lay.addWidget(self.combo, 1)

    def is_checked(self) -> bool:
        return self.check.isChecked()

    def var_name(self) -> str:
        return self.combo.currentData() or ""


class _CheckTree(QWidget if _HAS_QT else object):
    """Search box + checkable tree (one group). Data-filtering widget."""

    def __init__(self, title: str, items: list[str], checked: list[str],
                 parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        srow = QHBoxLayout()
        self.search = QLineEdit()
        btn = QPushButton("Search")
        btn.clicked.connect(self._filter)
        srow.addWidget(self.search, 1)
        srow.addWidget(btn)
        lay.addLayout(srow)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([title])
        sel = set(checked)
        self._items: list[QTreeWidgetItem] = []
        for name in items:
            it = QTreeWidgetItem([name])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked if name in sel else Qt.Unchecked)
            self._items.append(it)
        if items:
            root = QTreeWidgetItem([title])
            for it in self._items:
                root.addChild(it)
            root.setExpanded(True)
            self.tree.addTopLevelItem(root)
        lay.addWidget(self.tree, 1)

    def _filter(self) -> None:
        q = self.search.text().strip().lower()
        for it in self._items:
            it.setHidden(bool(q) and q not in it.text(0).lower())

    def checked(self) -> list[str]:
        return [it.text(0) for it in self._items
                if it.checkState(0) == Qt.Checked]

    def check_all(self, on: bool = True) -> None:
        st = Qt.Checked if on else Qt.Unchecked
        for it in self._items:
            it.setCheckState(0, st)


if _HAS_QT:
    from PyQt5.QtCore import pyqtSignal as _Sig
else:  # pragma: no cover
    _Sig = lambda *a, **k: None  # type: ignore


class ObjectSettingsPanel(QWidget if _HAS_QT else object):
    """scPOST Control-Window lower pane: tiled (not modal) object settings."""

    apply_requested = _Sig()
    close_requested = _Sig()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        if not _HAS_QT:
            return
        self.setWindowTitle(title)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)

        bar = QFrame(self)
        bar.setObjectName("PaneTitleBar")
        bar.setFixedHeight(24)
        bar.setAutoFillBackground(True)
        bar.setAttribute(Qt.WA_StyledBackground, True)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(8, 0, 4, 0)
        self._title_label = QLabel(title, bar)
        self._title_label.setObjectName("PaneTitle")
        hb.addWidget(self._title_label)
        hb.addStretch(1)
        self._btn_pin = QPushButton("P", bar)
        self._btn_pin.setFixedSize(22, 20)
        self._btn_pin.setCheckable(True)
        self._btn_pin.setChecked(True)
        self._btn_pin.setToolTip("Keep settings pane open (pin)")
        self._btn_pin.setStyleSheet(
            "QPushButton { border: none; font-size: 11px; font-weight: bold; }"
            "QPushButton:checked { background: #c8e0f8; }")
        hb.addWidget(self._btn_pin)
        self._btn_hide = QPushButton("x", bar)
        self._btn_hide.setFixedSize(22, 20)
        self._btn_hide.setToolTip("Hide settings pane")
        self._btn_hide.setStyleSheet(
            "QPushButton { border: none; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background: #e0e0e0; }")
        self._btn_hide.clicked.connect(self._on_hide)
        hb.addWidget(self._btn_hide)
        self._root.addWidget(bar)

        body = QWidget(self)
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(4, 4, 4, 4)
        body_lay.setSpacing(4)
        self.tabs = QTabWidget(body)
        body_lay.addWidget(self.tabs, 1)
        # Apply removed — scPOST uses the Draw (mallet) button on the
        # Control Window splitter grip to commit settings + redraw.
        self._root.addWidget(body, 1)

    def set_title(self, title: str) -> None:
        self.setWindowTitle(title)
        if _HAS_QT:
            self._title_label.setText(title)

    def is_pinned(self) -> bool:
        return bool(_HAS_QT and self._btn_pin.isChecked())

    def _on_apply(self) -> None:
        self.apply_requested.emit()

    def _on_hide(self) -> None:
        self.close_requested.emit()


# Backward-compatible alias used by older call sites / docs
_PinnedDialog = ObjectSettingsPanel


def _hline(parent) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


class SurfaceDialog(_PinnedDialog):
    """scPOST Surface — Region / MAT / Volume Region / Contour / Vector /
    Mesh / Trim / Scalar Integration tabs."""

    def __init__(self, surface, field_file=None, parent=None):
        super().__init__(surface.label if hasattr(surface, "label")
                         else "Surface (1)", parent)
        if not _HAS_QT:
            self.surface = surface
            return
        self.surface = surface
        self.field_file = field_file

        self.tabs.addTab(self._build_region(), "Region")
        self.tabs.addTab(self._build_mat(), "MAT")
        self.tabs.addTab(self._build_volume_region(), "Volume Region")
        self.tabs.addTab(self._build_contour(), "Contour")
        self.tabs.addTab(self._build_vector(), "Vector")
        self.tabs.addTab(self._build_mesh(), "Mesh")
        self.tabs.addTab(self._build_trim(), "Trim")
        self.tabs.addTab(self._build_scalar_integration(),
                         "Scalar Integration")

    # ── tab builders ─────────────────────────────────────────────────────

    def _build_region(self) -> QWidget:
        region = QWidget(self)
        lay = QVBoxLayout(region)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Show Regions", region))
        self.search = QLineEdit(region)
        search_row.addWidget(self.search, 1)
        btn = QPushButton("Search", region)
        btn.clicked.connect(self._filter)
        search_row.addWidget(btn)
        lay.addLayout(search_row)

        self.tree = QTreeWidget(region)
        self.tree.setHeaderLabels(["Region"])
        self.tree.setRootIsDecorated(True)
        root = QTreeWidgetItem(["ROOT"])
        reg = QTreeWidgetItem(["Registered Surfaces"])
        hid = QTreeWidgetItem(["Hidden Surfaces"])
        mats = QTreeWidgetItem(["MATs Boundary"])
        mats.setFlags(mats.flags() | Qt.ItemIsUserCheckable)
        mats.setCheckState(0, Qt.Checked)
        root.addChild(reg)
        root.addChild(hid)
        root.addChild(mats)
        self._region_items: list[QTreeWidgetItem] = []
        regions = []
        if self.field_file is not None:
            if self.field_file.surface_regions:
                regions = [n for n, _ in self.field_file.surface_regions]
            elif self.field_file.bc_plan:
                regions = [n for n, _, c in self.field_file.bc_plan if c]
        selected = set(getattr(self.surface, "selected_regions", []) or [])
        for name in regions:
            it = QTreeWidgetItem([name])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(
                0, Qt.Checked if (not selected or name in selected)
                else Qt.Unchecked)
            reg.addChild(it)
            self._region_items.append(it)
        self.tree.addTopLevelItem(root)
        root.setExpanded(True)
        reg.setExpanded(True)
        lay.addWidget(self.tree, 1)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Easy Mode:", region))
        self.mode_group = QButtonGroup(region)
        for i, label in enumerate(("Original", "Standard", "Name Tree",
                                   "Select one")):
            rb = QRadioButton(label, region)
            if label == (getattr(self.surface, "region_mode", "Standard")
                         or "Standard"):
                rb.setChecked(True)
            self.mode_group.addButton(rb, i)
            mode_row.addWidget(rb)
        mode_row.addStretch(1)
        lay.addLayout(mode_row)
        return region

    def _build_mat(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        mats = _mat_numbers(self.field_file)
        self.mat_tree = _CheckTree(
            "MAT", [str(m) for m in mats],
            [str(m) for m in getattr(self.surface, "display_mats", [])])
        lay.addWidget(self.mat_tree, 1)
        btn_row = QHBoxLayout()
        all_btn = QPushButton("Select All", page)
        all_btn.clicked.connect(lambda: self.mat_tree.check_all(True))
        none_btn = QPushButton("Select None", page)
        none_btn.clicked.connect(lambda: self.mat_tree.check_all(False))
        btn_row.addWidget(all_btn)
        btn_row.addWidget(none_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        hint = QLabel("Empty selection = display all MATs", page)
        hint.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(hint)
        return page

    def _build_volume_region(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        vrs = [n for n in (self.field_file.volume_regions
                           if self.field_file else [])]
        self.vol_tree = _CheckTree(
            "Volume Region", vrs,
            list(getattr(self.surface, "display_volume_regions", [])))
        lay.addWidget(self.vol_tree, 1)
        return page

    def _build_contour(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.contour = _VarRow("Display", _scalar_vars(self.field_file),
                               getattr(self.surface, "contour_var", ""))
        self.contour.check.setChecked(bool(self.surface.show_contour))
        lay.addWidget(self.contour)
        paint_row = QHBoxLayout()
        paint_row.addWidget(QLabel("Paint:"))
        self.c_front = QCheckBox("Front")
        self.c_front.setChecked(self.surface.contour_paint_front)
        self.c_back = QCheckBox("Back")
        self.c_back.setChecked(self.surface.contour_paint_back)
        paint_row.addWidget(self.c_front)
        paint_row.addWidget(self.c_back)
        paint_row.addStretch(1)
        lay.addLayout(paint_row)
        self.c_transp = QCheckBox("Transparent")
        self.c_transp.setChecked(self.surface.contour_transparent)
        lay.addWidget(self.c_transp)
        lay.addStretch(1)
        return page

    def _build_vector(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.vector = _VarRow("Display", _vector_vars(self.field_file),
                              getattr(self.surface, "vector_var", ""))
        self.vector.check.setChecked(bool(self.surface.show_vector))
        lay.addWidget(self.vector)
        lay.addStretch(1)
        return page

    def _build_mesh(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        frow = QHBoxLayout()
        frow.addWidget(QLabel("Mesh:"))
        self.m_front = QCheckBox("Front")
        self.m_front.setChecked(self.surface.mesh_front)
        self.m_back = QCheckBox("Back")
        self.m_back.setChecked(self.surface.mesh_back)
        frow.addWidget(self.m_front)
        frow.addWidget(self.m_back)
        frow.addStretch(1)
        lay.addLayout(frow)
        self.m_transp = QCheckBox("Transparent")
        self.m_transp.setChecked(self.surface.mesh_transparent)
        lay.addWidget(self.m_transp)
        form = QFormLayout()
        self.m_color = _ColorButton(self.surface.mesh_color, page)
        form.addRow("Color:", self.m_color)
        self.m_thick = QSpinBox(page)
        self.m_thick.setRange(1, 10)
        self.m_thick.setValue(int(self.surface.mesh_thickness))
        form.addRow("Thickness:", self.m_thick)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _build_trim(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        top = QHBoxLayout()
        ta = QPushButton("Trim all", page)
        ta.clicked.connect(lambda: self._set_trim(True))
        na = QPushButton("All", page)
        na.clicked.connect(lambda: self._set_trim(False))
        top.addWidget(QLabel("Always trim at:"))
        top.addWidget(ta)
        top.addWidget(na)
        top.addStretch(1)
        lay.addLayout(top)
        self.trim_checks = {}
        grid = QHBoxLayout()
        for axis, lo, hi in (("X", "xmin", "xmax"), ("Y", "ymin", "ymax"),
                             ("Z", "zmin", "zmax")):
            col = QVBoxLayout()
            col.addWidget(QLabel(f"{axis}-Axis"))
            for key in (lo, hi):
                cb = QCheckBox(key.upper())
                cb.setChecked(bool(getattr(self.surface, f"trim_{key}")))
                col.addWidget(cb)
                self.trim_checks[key] = cb
            grid.addLayout(col)
        lay.addLayout(grid)
        lay.addStretch(1)
        return page

    def _set_trim(self, on: bool) -> None:
        for cb in self.trim_checks.values():
            cb.setChecked(on)

    def _build_scalar_integration(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.integrate = QCheckBox(
            "Integrate the displayed scalar variable on this surface")
        self.integrate.setChecked(self.surface.integrate_scalar)
        lay.addWidget(self.integrate)
        self.proj_area = QCheckBox("Calculate the projected area")
        self.proj_area.setChecked(self.surface.projected_area)
        lay.addWidget(self.proj_area)
        lay.addStretch(1)
        return page

    # ── helpers ──────────────────────────────────────────────────────────

    def _filter(self) -> None:
        q = self.search.text().strip().lower()
        for it in self._region_items:
            it.setHidden(bool(q) and q not in it.text(0).lower())

    def apply_to(self, surface) -> None:
        names = [it.text(0) for it in self._region_items
                 if it.checkState(0) == Qt.Checked]
        surface.selected_regions = names
        btn = self.mode_group.checkedButton()
        if btn is not None:
            surface.region_mode = btn.text()
        # MAT / Volume Region
        surface.display_mats = [int(m) for m in self.mat_tree.checked()]
        surface.display_volume_regions = self.vol_tree.checked()
        # Contour / Vector / Mesh
        surface.show_contour = self.contour.is_checked()
        surface.contour_var = self.contour.var_name()
        surface.contour_paint_front = self.c_front.isChecked()
        surface.contour_paint_back = self.c_back.isChecked()
        surface.contour_transparent = self.c_transp.isChecked()
        surface.show_vector = self.vector.is_checked()
        surface.vector_var = self.vector.var_name()
        surface.mesh_front = self.m_front.isChecked()
        surface.mesh_back = self.m_back.isChecked()
        surface.mesh_transparent = self.m_transp.isChecked()
        surface.mesh_color = self.m_color.rgb()
        surface.mesh_thickness = int(self.m_thick.value())
        # Trim
        for key, cb in self.trim_checks.items():
            setattr(surface, f"trim_{key}", cb.isChecked())
        # Integration
        surface.integrate_scalar = self.integrate.isChecked()
        surface.projected_area = self.proj_area.isChecked()


class PlaneDialog(_PinnedDialog):
    """scPOST Plane — Coordinate / MAT / Volume Region / Contour / Vector /
    Mesh / Oil Flow / Trim / Automove / Clip / Pick / Scalar Integration /
    Vector Integration / Others / Texture / Font tabs.

    UI layout reverse-engineered from ``PostGUI_Dx64.dll`` string tables and
    the scPOST 2025.2 ``Post_eng`` manual.
    """

    def __init__(self, plane, field_file=None, parent=None):
        super().__init__(plane.label if hasattr(plane, "label")
                         else "Plane (1)", parent)
        if not _HAS_QT:
            self.plane = plane
            return
        self.plane = plane
        self.field_file = field_file

        self.tabs.addTab(self._build_coordinate(), "Coordinate")
        self.tabs.addTab(self._build_mat(), "MAT")
        self.tabs.addTab(self._build_volume_region(), "Volume Region")
        self.tabs.addTab(self._build_contour(), "Contour")
        self.tabs.addTab(self._build_vector(), "Vector")
        self.tabs.addTab(self._build_mesh(), "Mesh")
        self.tabs.addTab(self._build_oilflow(), "Oil Flow")
        self.tabs.addTab(self._build_trim(), "Trim")
        self.tabs.addTab(self._build_automove(), "Automove")
        self.tabs.addTab(self._build_clip(), "Clip")
        self.tabs.addTab(self._build_pick(), "Pick")
        self.tabs.addTab(self._build_scalar_integration(),
                         "Scalar Integration")
        self.tabs.addTab(self._build_vector_integration(),
                         "Vector Integration")
        self.tabs.addTab(self._build_others(), "Others")
        self.tabs.addTab(self._build_texture(), "Texture")
        self.tabs.addTab(self._build_font(), "Font")

    # ── Coordinate ───────────────────────────────────────────────────────

    def _build_coordinate(self) -> QWidget:
        coord = QWidget(self)
        lay = QVBoxLayout(coord)

        axis_row = QHBoxLayout()
        axis_row.addWidget(QLabel("Perpendicular to:", coord))
        self.axis_group = QButtonGroup(coord)
        for i, ax in enumerate(("X-Axis", "Y-Axis", "Z-Axis")):
            rb = QRadioButton(ax, coord)
            self.axis_group.addButton(rb, i)
            axis_row.addWidget(rb)
        axis_row.addStretch(1)
        lay.addLayout(axis_row)
        ax = (self.plane.axis or "Z").upper()
        self.axis_group.button({"X": 0, "Y": 1, "Z": 2}.get(ax, 2)).setChecked(True)

        lo, hi = -1.0, 1.0
        if self.field_file is not None and self.field_file.vertices is not None:
            import numpy as np
            v = np.asarray(self.field_file.vertices, dtype=np.float64)
            idx = {"X": 0, "Y": 1, "Z": 2}.get(ax, 2)
            lo, hi = float(v[:, idx].min()), float(v[:, idx].max())
        self._lo, self._hi = lo, hi

        form = QFormLayout()
        self.coord_edit = QDoubleSpinBox(coord)
        self.coord_edit.setDecimals(8)
        self.coord_edit.setRange(lo - abs(hi - lo), hi + abs(hi - lo))
        self.coord_edit.setValue(float(self.plane.coordinate))
        self.coord_edit.setSuffix(" m")
        form.addRow("Coordinate:", self.coord_edit)
        lay.addLayout(form)

        range_lbl = QLabel(f"{lo:.6g} m  —  {hi:.6g} m", coord)
        range_lbl.setStyleSheet("color:#555; font-size:11px;")
        lay.addWidget(range_lbl)

        self.slider = QSlider(Qt.Horizontal, coord)
        self.slider.setRange(0, 1000)
        t = 0 if hi == lo else int(1000 * (self.plane.coordinate - lo) / (hi - lo))
        self.slider.setValue(max(0, min(1000, t)))
        self.slider.valueChanged.connect(self._slider_to_coord)
        self.coord_edit.valueChanged.connect(self._coord_to_slider)
        lay.addWidget(self.slider)

        self.operate = QCheckBox("Operate Object", coord)
        self.operate.setChecked(self.plane.operate_object)
        lay.addWidget(self.operate)

        lay.addWidget(_hline(coord))

        # Arbitrary (point + normal, or 3-point Pick)
        arb_row = QHBoxLayout()
        arb_row.addWidget(QLabel("Arbitrary:", coord))
        self.arbitrary = QCheckBox("Define by point and normal", coord)
        self.arbitrary.setChecked(self.plane.arbitrary_enabled)
        arb_row.addWidget(self.arbitrary)
        self.pick_btn = QPushButton("Pick", coord)
        self.pick_btn.setCheckable(True)
        self.pick_btn.setChecked(self.plane.pick_mode)
        self.pick_btn.setToolTip("Define the plane by picking three points")
        arb_row.addWidget(self.pick_btn)
        self.pick_hide_btn = QPushButton("Hide", coord)
        self.pick_hide_btn.setChecked(self.plane.pick_hide)
        self.pick_hide_btn.setToolTip("Hide the three picked points")
        arb_row.addWidget(self.pick_hide_btn)
        arb_row.addStretch(1)
        lay.addLayout(arb_row)

        iform = QFormLayout()
        self.point_x = QDoubleSpinBox(coord)
        self.point_y = QDoubleSpinBox(coord)
        self.point_z = QDoubleSpinBox(coord)
        for sb, val in ((self.point_x, self.plane.point[0]),
                        (self.point_y, self.plane.point[1]),
                        (self.point_z, self.plane.point[2])):
            sb.setDecimals(6)
            sb.setRange(-1e6, 1e6)
            sb.setValue(float(val))
        iform.addRow("Point:", self._triplet(self.point_x, self.point_y,
                                             self.point_z, coord))
        self.norm_x = QDoubleSpinBox(coord)
        self.norm_y = QDoubleSpinBox(coord)
        self.norm_z = QDoubleSpinBox(coord)
        for sb, val in ((self.norm_x, self.plane.normal[0]),
                        (self.norm_y, self.plane.normal[1]),
                        (self.norm_z, self.plane.normal[2])):
            sb.setDecimals(6)
            sb.setRange(-1e6, 1e6)
            sb.setValue(float(val))
        iform.addRow("Normal:", self._triplet(self.norm_x, self.norm_y,
                                              self.norm_z, coord))
        lay.addLayout(iform)

        # Rotate sub-tab
        rot_box = QFrame(coord)
        rot_box.setFrameShape(QFrame.StyledPanel)
        rot_lay = QVBoxLayout(rot_box)
        rot_lay.setContentsMargins(6, 4, 6, 4)
        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Rotate:"))
        self.rotate_axis_group = QButtonGroup(rot_box)
        for i, label in enumerate(("XYZ", "Arb.")):
            rb = QRadioButton(label, rot_box)
            if label == self.plane.rotate_axis:
                rb.setChecked(True)
            self.rotate_axis_group.addButton(rb, i)
            rrow.addWidget(rb)
        rrow.addStretch(1)
        rot_lay.addLayout(rrow)
        bts = QHBoxLayout()
        for label, cmd in (("X+", "xp"), ("X-", "xm"), ("Y+", "yp"),
                           ("Y-", "ym"), ("Z+", "zp"), ("Z-", "zm")):
            b = QPushButton(label, rot_box)
            b.setFixedWidth(34)
            b.clicked.connect(
                lambda _=False, c=cmd: self._rotate_click(c))
            bts.addWidget(b)
        self._btn_plus = QPushButton("+", rot_box)
        self._btn_plus.setFixedWidth(34)
        self._btn_plus.clicked.connect(lambda: self._rotate_click("arb+"))
        self._btn_minus = QPushButton("-", rot_box)
        self._btn_minus.setFixedWidth(34)
        self._btn_minus.clicked.connect(lambda: self._rotate_click("arb-"))
        bts.addWidget(self._btn_plus)
        bts.addWidget(self._btn_minus)
        bts.addStretch(1)
        rot_lay.addLayout(bts)
        arow = QHBoxLayout()
        arow.addWidget(QLabel("Angle:"))
        self.rotate_angle = QDoubleSpinBox(rot_box)
        self.rotate_angle.setRange(0.01, 360.0)
        self.rotate_angle.setDecimals(2)
        self.rotate_angle.setValue(float(self.plane.rotate_angle))
        self.rotate_angle.setSuffix(" deg")
        arow.addWidget(self.rotate_angle)
        arow.addStretch(1)
        rot_lay.addLayout(arow)
        lay.addWidget(rot_box)

        # Usage Guide sub-tab
        self._usage_guide_ck = QCheckBox("Usage Guide", coord)
        self._usage_guide_ck.setChecked(self.plane.usage_guide)
        self._usage_guide_ck.toggled.connect(self._on_usage)
        lay.addWidget(self._usage_guide_ck)
        self.usage_row = QWidget(coord)
        ul = QHBoxLayout(self.usage_row)
        ul.setContentsMargins(0, 0, 0, 0)
        self.usage_buttons: dict[str, QPushButton] = {}
        for label, key in (("Horz/Vert", "hv"), ("Axis", "axis"),
                           ("Line/Paint", "lp"), ("Color", "color")):
            b = QPushButton(label, self.usage_row)
            b.setCheckable(True)
            b.setChecked(getattr(self.plane, f"usage_{key}", False))
            b.clicked.connect(lambda _=False, k=key: self._usage_click(k))
            ul.addWidget(b)
            self.usage_buttons[key] = b
        ul.addStretch(1)
        lay.addWidget(self.usage_row)

        lay.addStretch(1)
        self.axis_group.buttonClicked.connect(self._on_axis)
        self._on_usage(self.plane.usage_guide)
        return coord

    def _rotate_click(self, cmd: str) -> None:
        """Rotate the plane about the current point (scPOST Coordinate Rotate)."""
        import numpy as np
        from ..render.plane import _rotate_vector, _rotate_around
        ang = float(self.rotate_angle.value())
        ax = self.axis_group.checkedId()
        axes = {0: (1, 0, 0), 1: (0, 1, 0), 2: (0, 0, 1)}
        basis = np.array(axes.get(ax, (0, 0, 1)), dtype=float)
        sign = -1.0 if cmd.endswith("-") else 1.0
        if self.rotate_axis_group.checkedId() == 1:  # Arb.
            basis = np.asarray(self.plane.normal)
        n = _rotate_vector(np.asarray(self.plane.normal), basis,
                           sign * ang)
        p = _rotate_around(np.asarray(self.plane.point),
                           np.asarray(self.plane.point), basis, sign * ang)
        self.plane.normal = tuple(n)
        self.plane.point = tuple(p)
        self.norm_x.setValue(n[0])
        self.norm_y.setValue(n[1])
        self.norm_z.setValue(n[2])
        self.point_x.setValue(p[0])
        self.point_y.setValue(p[1])
        self.point_z.setValue(p[2])

    def _usage_click(self, key: str) -> None:
        # Persist the toggled usage-guide flag onto the plane immediately so
        # the state is visible without an explicit Apply.
        btn = getattr(self, "usage_buttons", {}).get(key)
        on = bool(btn is not None and btn.isChecked())
        if hasattr(self, "plane"):
            setattr(self.plane, f"usage_{key}", bool(on))

    def _on_usage(self, on: bool) -> None:
        self.usage_row.setVisible(on)

    def _triplet(self, a, b, c, parent) -> QWidget:
        w = QWidget(parent)
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for sb in (a, b, c):
            h.addWidget(sb, 1)
        return w

    def _slider_to_coord(self, v: int) -> None:
        c = self._lo + (self._hi - self._lo) * (v / 1000.0)
        self.coord_edit.blockSignals(True)
        self.coord_edit.setValue(c)
        self.coord_edit.blockSignals(False)

    def _coord_to_slider(self, c: float) -> None:
        if self._hi == self._lo:
            return
        t = int(1000 * (c - self._lo) / (self._hi - self._lo))
        self.slider.blockSignals(True)
        self.slider.setValue(max(0, min(1000, t)))
        self.slider.blockSignals(False)

    def _on_axis(self) -> None:
        if self.field_file is None or self.field_file.vertices is None:
            return
        import numpy as np
        ax = self.axis_group.checkedId()
        v = np.asarray(self.field_file.vertices, dtype=np.float64)
        self._lo = float(v[:, ax].min())
        self._hi = float(v[:, ax].max())
        mid = 0.5 * (self._lo + self._hi)
        self.coord_edit.setRange(
            self._lo - abs(self._hi - self._lo),
            self._hi + abs(self._hi - self._lo))
        self.coord_edit.setValue(mid)

    # ── MAT / Volume Region ──────────────────────────────────────────────

    def _build_mat(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        mats = _mat_numbers(self.field_file)
        self.mat_tree = _CheckTree(
            "MAT", [str(m) for m in mats],
            [str(m) for m in getattr(self.plane, "display_mats", [])])
        lay.addWidget(self.mat_tree, 1)
        return page

    def _build_volume_region(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        vrs = [n for n in (self.field_file.volume_regions
                           if self.field_file else [])]
        self.vol_tree = _CheckTree(
            "Volume Region", vrs,
            list(getattr(self.plane, "display_volume_regions", [])))
        lay.addWidget(self.vol_tree, 1)
        return page

    # ── Contour ──────────────────────────────────────────────────────────

    def _build_contour(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.contour = _VarRow("Display", _scalar_vars(self.field_file),
                               getattr(self.plane, "contour_var", ""))
        self.contour.check.setChecked(bool(self.plane.show_contour))
        lay.addWidget(self.contour)

        paint_row = QHBoxLayout()
        paint_row.addWidget(QLabel("Paint:"))
        self.c_paint = QCheckBox("Paint")
        self.c_paint.setChecked(self.plane.contour_paint)
        paint_row.addWidget(self.c_paint)
        self.c_luster = QCheckBox("Luster")
        self.c_luster.setChecked(self.plane.contour_luster)
        paint_row.addWidget(self.c_luster)
        self.c_water = QCheckBox("Water")
        self.c_water.setChecked(self.plane.contour_water)
        paint_row.addWidget(self.c_water)
        self.c_transp = QCheckBox("Transparent")
        self.c_transp.setChecked(self.plane.contour_transparent)
        paint_row.addWidget(self.c_transp)
        paint_row.addStretch(1)
        lay.addLayout(paint_row)

        line_row = QHBoxLayout()
        line_row.addWidget(QLabel("Line:"))
        self.c_contour_line = QCheckBox("Contour line")
        self.c_contour_line.setChecked(self.plane.contour_line)
        line_row.addWidget(self.c_contour_line)
        self.c_line_transp = QCheckBox("Transparent")
        self.c_line_transp.setChecked(self.plane.contour_line_transparent)
        line_row.addWidget(self.c_line_transp)
        self.c_line_broken = QCheckBox("Broken line")
        self.c_line_broken.setChecked(self.plane.contour_broken_line)
        line_row.addWidget(self.c_line_broken)
        line_row.addStretch(1)
        lay.addLayout(line_row)

        form = QFormLayout()
        self.c_mono = QCheckBox("Mono color")
        self.c_mono.setChecked(self.plane.contour_mono_color)
        self.c_mono_rgb = _ColorButton(self.plane.contour_mono_rgb, page)
        mono_row = QHBoxLayout()
        mono_row.addWidget(self.c_mono)
        mono_row.addWidget(self.c_mono_rgb, 1)
        form.addRow("Line:", mono_row)
        self.c_value = QCheckBox("Value")
        self.c_value.setChecked(self.plane.contour_value)
        form.addRow("", self.c_value)
        self.c_thick = QSpinBox(page)
        self.c_thick.setRange(1, 10)
        self.c_thick.setValue(int(self.plane.contour_thickness))
        form.addRow("Thickness:", self.c_thick)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    # ── Vector ───────────────────────────────────────────────────────────

    def _build_vector(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.vector = _VarRow("Display", _vector_vars(self.field_file),
                              getattr(self.plane, "vector_var", ""))
        self.vector.check.setChecked(bool(self.plane.show_vector))
        lay.addWidget(self.vector)

        loc_row = QHBoxLayout()
        loc_row.addWidget(QLabel("Location:"))
        self.loc_group = QButtonGroup(page)
        for i, label in enumerate(("Uniform", "Actual", "Center", "Nodes")):
            rb = QRadioButton(label, page)
            if label == self.plane.vector_location:
                rb.setChecked(True)
            self.loc_group.addButton(rb, i)
            loc_row.addWidget(rb)
        loc_row.addStretch(1)
        lay.addLayout(loc_row)

        space_form = QFormLayout()
        self.v_space_u = QDoubleSpinBox(page)
        self.v_space_u.setRange(0.01, 1e6)
        self.v_space_u.setValue(float(self.plane.vector_space_u))
        space_form.addRow("Space (u):", self.v_space_u)
        self.v_space_v = QDoubleSpinBox(page)
        self.v_space_v.setRange(0.01, 1e6)
        self.v_space_v.setValue(float(self.plane.vector_space_v))
        space_form.addRow("Space (v):", self.v_space_v)
        lay.addLayout(space_form)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox(page)
        for t in ("Simple", "Standard", "Triangle", "3D", "Animation"):
            self.type_combo.addItem(t, t)
        idx = self.type_combo.findData(self.plane.vector_type)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        type_row.addWidget(self.type_combo, 1)
        lay.addLayout(type_row)

        chk_row = QHBoxLayout()
        self.v_const = QCheckBox("Constant length")
        self.v_const.setChecked(self.plane.vector_constant_length)
        chk_row.addWidget(self.v_const)
        self.v_transp = QCheckBox("Transparent")
        self.v_transp.setChecked(self.plane.vector_transparent)
        chk_row.addWidget(self.v_transp)
        chk_row.addStretch(1)
        lay.addLayout(chk_row)

        form = QFormLayout()
        self.v_mono = QCheckBox("Mono color")
        self.v_mono.setChecked(self.plane.vector_mono_color)
        self.v_mono_rgb = _ColorButton(self.plane.vector_mono_rgb, page)
        mono_row = QHBoxLayout()
        mono_row.addWidget(self.v_mono)
        mono_row.addWidget(self.v_mono_rgb, 1)
        form.addRow("", mono_row)
        self.v_ccolor = QCheckBox("Contour Color")
        self.v_ccolor.setChecked(self.plane.vector_contour_color)
        form.addRow("", self.v_ccolor)
        self.v_proj = QCheckBox("Projection")
        self.v_proj.setChecked(self.plane.vector_projection)
        form.addRow("", self.v_proj)
        lay.addLayout(form)

        scale_form = QFormLayout()
        self.v_len = QDoubleSpinBox(page)
        self.v_len.setRange(0.0, 1e6)
        self.v_len.setValue(float(self.plane.vector_scale_length))
        scale_form.addRow("Scale — Length:", self.v_len)
        self.v_thick = QDoubleSpinBox(page)
        self.v_thick.setRange(0.0, 1e6)
        self.v_thick.setValue(float(self.plane.vector_scale_thickness))
        scale_form.addRow("Thickness:", self.v_thick)
        arrow_form = QFormLayout()
        self.v_arrow_angle = QDoubleSpinBox(page)
        self.v_arrow_angle.setRange(0.0, 1e6)
        self.v_arrow_angle.setValue(float(self.plane.vector_arrow_angle))
        arrow_form.addRow("Arrow — Angle:", self.v_arrow_angle)
        self.v_arrow_size = QDoubleSpinBox(page)
        self.v_arrow_size.setRange(0.0, 1e6)
        self.v_arrow_size.setValue(float(self.plane.vector_arrow_size))
        arrow_form.addRow("Size:", self.v_arrow_size)
        lay.addLayout(scale_form)
        lay.addLayout(arrow_form)
        lay.addStretch(1)
        return page

    # ── Mesh ─────────────────────────────────────────────────────────────

    def _build_mesh(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)

        # Boundary (cut plane × boundary surface)
        bbox = QFrame(page)
        bbox.setFrameShape(QFrame.StyledPanel)
        bl = QVBoxLayout(bbox)
        bl.setContentsMargins(6, 4, 6, 4)
        self.boundary = QCheckBox("Boundary", bbox)
        self.boundary.setChecked(self.plane.boundary_line)
        bl.addWidget(self.boundary)
        brow = QHBoxLayout()
        self.b_auto = QCheckBox("Auto", bbox)
        self.b_auto.setChecked(self.plane.boundary_auto)
        brow.addWidget(self.b_auto)
        self.b_broken = QCheckBox("Broken line", bbox)
        self.b_broken.setChecked(self.plane.boundary_broken_line)
        brow.addWidget(self.b_broken)
        brow.addStretch(1)
        bl.addLayout(brow)
        bform = QFormLayout()
        self.b_color = _ColorButton(self.plane.boundary_color, bbox)
        bform.addRow("Color:", self.b_color)
        self.b_transp = QCheckBox("Transparent", bbox)
        self.b_transp.setChecked(self.plane.boundary_transparent)
        bform.addRow("", self.b_transp)
        bl.addLayout(bform)
        lay.addWidget(bbox)

        # Mesh intersection lines
        mrow = QHBoxLayout()
        self.mesh_display = QCheckBox("Mesh", page)
        self.mesh_display.setChecked(self.plane.show_mesh)
        mrow.addWidget(self.mesh_display)
        self.m_transp = QCheckBox("Transparent", page)
        self.m_transp.setChecked(self.plane.mesh_transparent)
        mrow.addWidget(self.m_transp)
        self.m_block = QCheckBox("Block", page)
        self.m_block.setChecked(self.plane.mesh_block)
        mrow.addWidget(self.m_block)
        mrow.addStretch(1)
        lay.addLayout(mrow)
        mform = QFormLayout()
        self.m_color = _ColorButton(self.plane.mesh_color, page)
        mform.addRow("Color:", self.m_color)
        self.m_thick = QSpinBox(page)
        self.m_thick.setRange(1, 10)
        self.m_thick.setValue(int(self.plane.mesh_thickness))
        mform.addRow("Thickness:", self.m_thick)
        lay.addLayout(mform)

        # Paint
        pform = QFormLayout()
        self.m_paint = QCheckBox("Paint", page)
        self.m_paint.setChecked(self.plane.mesh_paint)
        self.m_paint_rgb = _ColorButton(self.plane.mesh_paint_rgb, page)
        prow = QHBoxLayout()
        prow.addWidget(self.m_paint)
        prow.addWidget(self.m_paint_rgb, 1)
        pform.addRow("", prow)
        self.m_luster = QCheckBox("Luster", page)
        self.m_luster.setChecked(self.plane.mesh_luster)
        pform.addRow("", self.m_luster)
        self.m_water = QCheckBox("Water", page)
        self.m_water.setChecked(self.plane.mesh_water)
        pform.addRow("", self.m_water)
        lay.addLayout(pform)

        # Subline
        subrow = QHBoxLayout()
        subrow.addWidget(QLabel("Subline:"))
        self.sub_ext = QCheckBox("External frame", page)
        self.sub_ext.setChecked(self.plane.subline_external)
        subrow.addWidget(self.sub_ext)
        self.sub_auto = QCheckBox("Automatic", page)
        self.sub_auto.setChecked(self.plane.subline_automatic)
        subrow.addWidget(self.sub_auto)
        self.sub_loc = QCheckBox("Display location", page)
        self.sub_loc.setChecked(self.plane.subline_display_location)
        subrow.addWidget(self.sub_loc)
        subrow.addStretch(1)
        lay.addLayout(subrow)
        lay.addStretch(1)
        return page

    # ── Oil Flow ─────────────────────────────────────────────────────────

    def _build_oilflow(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.oil_display = QCheckBox("Display", page)
        self.oil_display.setChecked(self.plane.oilflow_display)
        lay.addWidget(self.oil_display)
        var_row = QHBoxLayout()
        var_row.addWidget(QLabel("Variable:"))
        self.oil_var = QComboBox(page)
        for v in _vector_vars(self.field_file):
            self.oil_var.addItem(v, v)
        idx = self.oil_var.findData(self.plane.oilflow_var)
        if idx >= 0:
            self.oil_var.setCurrentIndex(idx)
        var_row.addWidget(self.oil_var, 1)
        lay.addLayout(var_row)

        form = QFormLayout()
        self.oil_transp = QCheckBox("Transparent", page)
        self.oil_transp.setChecked(self.plane.oilflow_transparent)
        form.addRow("", self.oil_transp)
        self.oil_thick = QDoubleSpinBox(page)
        self.oil_thick.setRange(0.1, 100)
        self.oil_thick.setValue(float(self.plane.oilflow_thickness))
        form.addRow("Thickness:", self.oil_thick)
        self.oil_space_u = QDoubleSpinBox(page)
        self.oil_space_u.setRange(0.1, 100)
        self.oil_space_u.setValue(float(self.plane.oilflow_space_u))
        form.addRow("Space (u):", self.oil_space_u)
        self.oil_space_v = QDoubleSpinBox(page)
        self.oil_space_v.setRange(0.1, 100)
        self.oil_space_v.setValue(float(self.plane.oilflow_space_v))
        form.addRow("Space (v):", self.oil_space_v)
        self.oil_length = QDoubleSpinBox(page)
        self.oil_length.setRange(0.1, 100)
        self.oil_length.setValue(float(self.plane.oilflow_length))
        form.addRow("Length:", self.oil_length)
        lay.addLayout(form)

        draw_row = QHBoxLayout()
        draw_row.addWidget(QLabel("draw type:"))
        self.oil_draw = QComboBox(page)
        for d in ("Line", "Simple", "Standard", "Triangle", "3D"):
            self.oil_draw.addItem(d, d)
        idx = self.oil_draw.findData(self.plane.oilflow_draw_type)
        if idx >= 0:
            self.oil_draw.setCurrentIndex(idx)
        draw_row.addWidget(self.oil_draw, 1)
        lay.addLayout(draw_row)

        im = QHBoxLayout()
        im.addWidget(QLabel("Integration Method:"))
        self.oil_int = QComboBox(page)
        for m in ("Runge-Kutta", "Euler"):
            self.oil_int.addItem(m, m)
        idx = self.oil_int.findData(self.plane.oilflow_integration_method)
        if idx >= 0:
            self.oil_int.setCurrentIndex(idx)
        im.addWidget(self.oil_int, 1)
        lay.addLayout(im)
        sform = QFormLayout()
        self.oil_steps = QSpinBox(page)
        self.oil_steps.setRange(1, 1000)
        self.oil_steps.setValue(int(self.plane.oilflow_steps))
        sform.addRow("Steps in each element:", self.oil_steps)
        self.oil_acc = QSpinBox(page)
        self.oil_acc.setRange(1, 10)
        self.oil_acc.setValue(int(self.plane.oilflow_accuracy))
        sform.addRow("Accuracy:", self.oil_acc)
        lay.addLayout(sform)
        lay.addStretch(1)
        return page

    # ── Trim ─────────────────────────────────────────────────────────────

    def _build_trim(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Trimmed by:", page))
        objects = [o.label for o in getattr(self, "_trim_objects", [])]
        self.trim_tree = _CheckTree(
            "Object", objects, list(self.plane.trim_objects))
        lay.addWidget(self.trim_tree, 1)
        lay.addWidget(_hline(page))
        lay.addWidget(QLabel("Coordinate range (blank = not trimmed):", page))
        form = QFormLayout()
        self._trim_eds: dict[str, QDoubleSpinBox] = {}
        for axis in ("X", "Y", "Z"):
            lo_ed = QDoubleSpinBox(page)
            hi_ed = QDoubleSpinBox(page)
            for ed, key in ((lo_ed, f"trim_{axis.lower()}min"),
                            (hi_ed, f"trim_{axis.lower()}max")):
                ed.setDecimals(8)
                ed.setRange(-1e9, 1e9)
                ed.setSpecialValueText("(off)")
                val = getattr(self.plane, key, None)
                ed.setValue(float(val) if val is not None else ed.minimum())
                self._trim_eds[key] = ed
            row = QHBoxLayout()
            row.addWidget(lo_ed, 1)
            row.addWidget(QLabel("to", page))
            row.addWidget(hi_ed, 1)
            form.addRow(f"{axis}:", row)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _trim_vals(self) -> dict[str, Optional[float]]:
        """Trim coordinates → {key: float|None}. A spin at its minimum
        (special-value ``(off)``) is treated as untrimmed."""
        out: dict[str, Optional[float]] = {}
        for key, ed in getattr(self, "_trim_eds", {}).items():
            if ed.value() <= -1e9 + 1.0:
                out[key] = None
            else:
                out[key] = float(ed.value())
        return out

    # ── Automove ─────────────────────────────────────────────────────────

    def _build_automove(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.auto_enabled = QCheckBox("Enable Automove", page)
        self.auto_enabled.setChecked(self.plane.automove_enabled)
        lay.addWidget(self.auto_enabled)

        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("Method:", page))
        self.method = QComboBox(page)
        for m in ("Line", "Sin", "Cos", "Rotation", "Custom Path"):
            self.method.addItem(m, m)
        idx = self.method.findData(self.plane.automove_method)
        if idx >= 0:
            self.method.setCurrentIndex(idx)
        self.method.currentIndexChanged.connect(self._on_method)
        mrow.addWidget(self.method, 1)
        lay.addLayout(mrow)

        # Standard params (Line / Sin / Cos / Rotation)
        self.auto_std = QWidget(page)
        std = QVBoxLayout(self.auto_std)
        std.setContentsMargins(0, 0, 0, 0)
        sform = QFormLayout()
        sform.addRow("Starting plane:", self._plane_edits(
            "auto_start", self.plane.automove_start_point,
            self.plane.automove_start_normal))
        sform.addRow("Reference plane:", self._plane_edits(
            "auto_ref", self.plane.automove_ref_point,
            self.plane.automove_ref_normal))
        sform.addRow("Rotational axis:", self._axis_edits())
        sform.addRow("Angle:", self._spin("auto_angle",
                                          self.plane.automove_angle, " deg"))
        sform.addRow("Offset:", self._spin("auto_offset",
                                           self.plane.automove_offset, " deg"))
        std.addLayout(sform)
        chk = QHBoxLayout()
        self.auto_loop = QCheckBox("Loop")
        self.auto_loop.setChecked(self.plane.automove_loop)
        chk.addWidget(self.auto_loop)
        self.auto_standby = QCheckBox("Ready")
        self.auto_standby.setChecked(self.plane.automove_standby)
        chk.addWidget(self.auto_standby)
        chk.addWidget(QLabel("Frames:"))
        self.auto_frames = QSpinBox(page)
        self.auto_frames.setRange(2, 1000)
        self.auto_frames.setValue(int(self.plane.automove_frames))
        chk.addWidget(self.auto_frames)
        chk.addStretch(1)
        std.addLayout(chk)
        lay.addWidget(self.auto_std)

        # Custom path params
        self.auto_path = QWidget(page)
        path = QVBoxLayout(self.auto_path)
        path.setContentsMargins(0, 0, 0, 0)
        pform = QFormLayout()
        self.auto_csv = QLineEdit(self.plane.automove_csv)
        pform.addRow("CSV file:", self.auto_csv)
        self.auto_show_path = QCheckBox("Show Path")
        self.auto_show_path.setChecked(self.plane.automove_show_path)
        pform.addRow("", self.auto_show_path)
        self.auto_sync = QCheckBox("Position at the current transient time")
        self.auto_sync.setChecked(self.plane.automove_path_sync)
        pform.addRow("", self.auto_sync)
        self.auto_dist = QDoubleSpinBox(page)
        self.auto_dist.setRange(0, 1e9)
        self.auto_dist.setValue(float(self.plane.automove_path_distance))
        pform.addRow("Path Distance:", self.auto_dist)
        self.auto_ps = QDoubleSpinBox(page)
        self.auto_ps.setRange(0, 1e9)
        self.auto_ps.setValue(float(self.plane.automove_path_start))
        pform.addRow("Start:", self.auto_ps)
        self.auto_pe = QDoubleSpinBox(page)
        self.auto_pe.setRange(0, 1e9)
        self.auto_pe.setValue(float(self.plane.automove_path_end))
        pform.addRow("End:", self.auto_pe)
        path.addLayout(pform)
        lay.addWidget(self.auto_path)

        lay.addStretch(1)
        self._on_method(self.method.currentIndex())
        return page

    def _plane_edits(self, tag, point, normal) -> QWidget:
        # Unique object names:
        #   point  → {tag}_px / {tag}_py / {tag}_pz
        #   normal → {tag}_n_px / {tag}_n_py / {tag}_n_pz
        spins = [
            self._spin(f"{tag}_px", point[0], " m"),
            self._spin(f"{tag}_py", point[1], " m"),
            self._spin(f"{tag}_pz", point[2], " m"),
            self._spin(f"{tag}_n_px", normal[0]),
            self._spin(f"{tag}_n_py", normal[1]),
            self._spin(f"{tag}_n_pz", normal[2]),
        ]
        w = QWidget(self)
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        for sb in spins:
            h.addWidget(sb)
        return w

    def _axis_edits(self) -> QWidget:
        w = QWidget(self)
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        names = ("auto_axp_px", "auto_axp_py", "auto_axp_pz",
                 "auto_axd_n_px", "auto_axd_n_py", "auto_axd_n_pz")
        vals = list(self.plane.automove_axis_point) + \
            list(self.plane.automove_axis_dir)
        for name, val in zip(names, vals):
            h.addWidget(self._spin(name, val,
                                   " m" if name.startswith("auto_axp") else ""))
        return w

    def _spin(self, tag, value, suffix="") -> QDoubleSpinBox:
        sb = QDoubleSpinBox(self)
        sb.setObjectName(tag)
        sb.setRange(-1e9, 1e9)
        sb.setDecimals(6)
        sb.setValue(float(value))
        if suffix:
            sb.setSuffix(suffix)
        return sb

    def _on_method(self, idx: int) -> None:
        method = self.method.itemData(idx)
        is_path = method == "Custom Path"
        self.auto_std.setVisible(not is_path)
        self.auto_path.setVisible(is_path)

    # ── Clip ─────────────────────────────────────────────────────────────

    def _build_clip(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.clip_enabled = QCheckBox("Clip plane object", page)
        self.clip_enabled.setChecked(self.plane.clip_enabled)
        lay.addWidget(self.clip_enabled)
        form = QFormLayout()
        self.clip_xmin = QDoubleSpinBox(page)
        self.clip_xmin.setRange(-1e9, 1e9)
        self.clip_xmin.setValue(float(self.plane.clip_xmin))
        form.addRow("X range:", self.clip_xmin)
        self.clip_xmax = QDoubleSpinBox(page)
        self.clip_xmax.setRange(-1e9, 1e9)
        self.clip_xmax.setValue(float(self.plane.clip_xmax))
        form.addRow("to:", self.clip_xmax)
        self.clip_ymin = QDoubleSpinBox(page)
        self.clip_ymin.setRange(-1e9, 1e9)
        self.clip_ymin.setValue(float(self.plane.clip_ymin))
        form.addRow("Y range:", self.clip_ymin)
        self.clip_ymax = QDoubleSpinBox(page)
        self.clip_ymax.setRange(-1e9, 1e9)
        self.clip_ymax.setValue(float(self.plane.clip_ymax))
        form.addRow("to:", self.clip_ymax)
        lay.addLayout(form)
        self.clip_display = QCheckBox("Display clipping region", page)
        self.clip_display.setChecked(self.plane.clip_display_region)
        lay.addWidget(self.clip_display)
        lay.addStretch(1)
        return page

    # ── Pick ─────────────────────────────────────────────────────────────

    def _build_pick(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.pick_scalar = _VarRow("Scalar", _scalar_vars(self.field_file),
                                   self.plane.pick_scalar_var)
        self.pick_scalar.check.setChecked(self.plane.pick_scalar)
        lay.addWidget(self.pick_scalar)
        self.pick_vector = _VarRow("Vector", _vector_vars(self.field_file),
                                   self.plane.pick_vector_var)
        self.pick_vector.check.setChecked(self.plane.pick_vector)
        lay.addWidget(self.pick_vector)
        chk = QHBoxLayout()
        self.pick_ijk = QCheckBox("IJK")
        self.pick_ijk.setChecked(self.plane.pick_ijk)
        chk.addWidget(self.pick_ijk)
        self.pick_cycle = QCheckBox("Cycle Graph")
        self.pick_cycle.setChecked(self.plane.pick_cycle_graph)
        chk.addWidget(self.pick_cycle)
        chk.addStretch(1)
        lay.addLayout(chk)
        self.pick_allvars = QCheckBox(
            "Show all variables in the message window")
        self.pick_allvars.setChecked(self.plane.pick_show_all_vars)
        lay.addWidget(self.pick_allvars)
        self.pick_numbers = QCheckBox("Show numbers")
        self.pick_numbers.setChecked(self.plane.pick_show_numbers)
        lay.addWidget(self.pick_numbers)
        form = QFormLayout()
        self.pick_color = QCheckBox("Color")
        self.pick_color.setChecked(self.plane.pick_color_enabled)
        form.addRow("", self.pick_color)
        self.pick_shape = QComboBox(page)
        for s in ("Sphere", "Cube", "Point"):
            self.pick_shape.addItem(s, s)
        idx = self.pick_shape.findData(self.plane.pick_shape)
        if idx >= 0:
            self.pick_shape.setCurrentIndex(idx)
        form.addRow("Shape:", self.pick_shape)
        self.pick_line = _ColorButton(self.plane.pick_line_color, page)
        form.addRow("Line:", self.pick_line)
        self.pick_solid = _ColorButton(self.plane.pick_solid_color, page)
        form.addRow("Solid:", self.pick_solid)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    # ── Integration ──────────────────────────────────────────────────────

    def _build_scalar_integration(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.int_scalar = QCheckBox(
            "Integrate the displayed scalar variable on this plane")
        self.int_scalar.setChecked(self.plane.integrate_scalar_enabled)
        lay.addWidget(self.int_scalar)
        self._build_integration_common(lay, page)
        return page

    def _build_vector_integration(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.int_vector = QCheckBox(
            "Integrate the displayed vector variable on this plane")
        self.int_vector.setChecked(self.plane.integrate_vector_enabled)
        lay.addWidget(self.int_vector)
        self._build_integration_common(lay, page)
        return page

    def _build_integration_common(self, lay, page) -> None:
        lay.addWidget(_hline(page))
        out_row = QHBoxLayout()
        self.int_out = QCheckBox("Output to file", page)
        self.int_out.setChecked(self.plane.integrate_output_file)
        out_row.addWidget(self.int_out)
        self.int_csv = QLineEdit(self.plane.integrate_output_csv)
        out_row.addWidget(self.int_csv, 1)
        browse = QPushButton("Browse", page)
        browse.clicked.connect(self._int_browse)
        out_row.addWidget(browse)
        lay.addLayout(out_row)
        form = QFormLayout()
        self.int_labels = QCheckBox("Include labels", page)
        self.int_labels.setChecked(self.plane.integrate_include_labels)
        form.addRow("", self.int_labels)
        self.int_beep = QCheckBox("Beep", page)
        self.int_beep.setChecked(self.plane.integrate_beep)
        form.addRow("", self.int_beep)
        lay.addLayout(form)
        btn = QPushButton("Integrate", page)
        btn.clicked.connect(self._on_integrate)
        lay.addWidget(btn)
        self.int_recalc = QCheckBox("Recalc. after redraw", page)
        self.int_recalc.setChecked(self.plane.integrate_recalc_redraw)
        lay.addWidget(self.int_recalc)
        self.integrate_result = QLabel("", page)
        self.integrate_result.setWordWrap(True)
        self.integrate_result.setStyleSheet("color:#333; font-size:11px;")
        lay.addWidget(self.integrate_result)
        lay.addStretch(1)

    def _int_browse(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Output CSV",
                                              self.int_csv.text(), "CSV (*.csv)")
        if path:
            self.int_csv.setText(path)

    def _on_integrate(self) -> None:
        """Execute the scPOST integral over the current cut."""
        try:
            from ..render.plane import (
                build_ugrid, integrate_cut, cut_with_fields,
                write_integration_csv)
            if self.field_file is None:
                return
            ug, cc = build_ugrid(self.field_file)
            if ug is None:
                return
            scalar = None
            vector = None
            if self.int_scalar.isChecked() and self.plane.contour_var:
                scalar = self.plane.contour_var
            if self.int_vector.isChecked() and self.plane.vector_var:
                vector = self.plane.vector_var
            cut, vec = cut_with_fields(ug, self.field_file, self.plane, cc,
                                       scalar=scalar, vector=vector)
            res = integrate_cut(cut, scalar, vec)
            txt = f"Area : {res['area']:.6g} m^2"
            if scalar:
                txt += (f"\nSum  : {res['sum']:.6g}"
                        f"\nAverage : {res['average']:.6g}")
            if vec is not None:
                txt += (f"\nNormal flux : {res['in_normal']:.6g} m^3/s"
                        f"\nAverage : {res['avg_normal']:.6g} m/s")
            if self.int_out.isChecked() and self.int_csv.text():
                write_integration_csv(
                    self.int_csv.text(), res, self.plane,
                    include_labels=self.int_labels.isChecked())
                txt += f"\nCSV: {self.int_csv.text()}"
            self.integrate_result.setText(txt)
        except Exception as exc:  # noqa: BLE001
            self.integrate_result.setText(f"Integral failed: {exc}")

    # ── Others ───────────────────────────────────────────────────────────

    def _build_others(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        form = QFormLayout()
        self.cb_contour = QComboBox(page)
        self.cb_contour.addItem("(auto)", "")
        self.cb_contour.setCurrentIndex(0)
        form.addRow("Colorbar for contour:", self.cb_contour)
        self.cb_vector = QComboBox(page)
        self.cb_vector.addItem("(auto)", "")
        self.cb_vector.setCurrentIndex(0)
        form.addRow("Colorbar for vector:", self.cb_vector)
        lay.addLayout(form)
        self.others_model_coord = QCheckBox(
            "Use the model coordinate system", page)
        self.others_model_coord.setChecked(self.plane.use_model_coord)
        lay.addWidget(self.others_model_coord)
        self.others_no_simul = QCheckBox(
            "Do not display vector and contour simultaneously", page)
        self.others_no_simul.setChecked(
            self.plane.no_vector_contour_simultaneous)
        lay.addWidget(self.others_no_simul)
        lay.addWidget(_hline(page))
        lay.addWidget(QLabel("Calculate the intersection line with:", page))
        self.inter_surface = QCheckBox("a surface")
        self.inter_surface.setChecked(self.plane.inter_surface)
        lay.addWidget(self.inter_surface)
        self.inter_isosurface = QCheckBox("an isosurface")
        self.inter_isosurface.setChecked(self.plane.inter_isosurface)
        lay.addWidget(self.inter_isosurface)
        self.inter_plane = QCheckBox("another plane")
        self.inter_plane.setChecked(self.plane.inter_plane)
        lay.addWidget(self.inter_plane)
        self.inter_undisp = QCheckBox("an undisplayed object")
        self.inter_undisp.setChecked(self.plane.inter_undisplayed)
        lay.addWidget(self.inter_undisp)
        lay.addStretch(1)
        return page

    # ── Texture ──────────────────────────────────────────────────────────

    def _build_texture(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.tex_enabled = QCheckBox("Use texture mapping", page)
        self.tex_enabled.setChecked(self.plane.texture_enabled)
        lay.addWidget(self.tex_enabled)
        form = QFormLayout()
        trow = QHBoxLayout()
        self.tex_file = QLineEdit(self.plane.texture_file)
        trow.addWidget(self.tex_file, 1)
        browse = QPushButton("Browse", page)
        browse.clicked.connect(self._tex_browse)
        trow.addWidget(browse)
        form.addRow("Texture file:", trow)
        self.tex_method = QComboBox(page)
        for m in ("Plane",):
            self.tex_method.addItem(m, m)
        form.addRow("Method:", self.tex_method)
        self.tex_scale = QDoubleSpinBox(page)
        self.tex_scale.setRange(0.01, 1e6)
        self.tex_scale.setValue(float(self.plane.texture_scale))
        form.addRow("Scale:", self.tex_scale)
        self.tex_angle = QDoubleSpinBox(page)
        self.tex_angle.setRange(0, 360)
        self.tex_angle.setValue(float(self.plane.texture_angle))
        self.tex_angle.setSuffix(" deg")
        form.addRow("Angle:", self.tex_angle)
        pos_row = QHBoxLayout()
        self.tex_pos_u = QDoubleSpinBox(page)
        self.tex_pos_u.setRange(0, 1)
        self.tex_pos_u.setValue(float(self.plane.texture_pos_u))
        pos_row.addWidget(self.tex_pos_u, 1)
        self.tex_pos_v = QDoubleSpinBox(page)
        self.tex_pos_v.setRange(0, 1)
        self.tex_pos_v.setValue(float(self.plane.texture_pos_v))
        pos_row.addWidget(self.tex_pos_v, 1)
        form.addRow("Position:", pos_row)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _tex_browse(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Texture file", "", "Images (*.bmp *.png *.jpg *.jpeg)")
        if path:
            self.tex_file.setText(path)

    # ── Font ─────────────────────────────────────────────────────────────

    def _build_font(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        form = QFormLayout()
        self.font_name = QComboBox(page)
        for name in ("MS Gothic", "MS UI Gothic", "Arial", "Tahoma", "Courier"):
            self.font_name.addItem(name, name)
        idx = self.font_name.findData(self.plane.font_name)
        if idx >= 0:
            self.font_name.setCurrentIndex(idx)
        form.addRow("Fonts:", self.font_name)
        self.font_size = QSpinBox(page)
        self.font_size.setRange(4, 72)
        self.font_size.setValue(int(self.plane.font_size))
        form.addRow("Size:", self.font_size)
        self.font_float = QDoubleSpinBox(page)
        self.font_float.setRange(0, 1e6)
        self.font_float.setValue(float(self.plane.font_float))
        form.addRow("Float:", self.font_float)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    # ── apply ────────────────────────────────────────────────────────────

    def _triplet_vals(self) -> tuple:
        return (self.point_x.value(), self.point_y.value(), self.point_z.value())

    def _normal_vals(self) -> tuple:
        return (self.norm_x.value(), self.norm_y.value(), self.norm_z.value())

    def apply_to(self, plane) -> None:
        ax = {0: "X", 1: "Y", 2: "Z"}.get(self.axis_group.checkedId(), "Z")
        plane.axis = ax
        plane.coordinate = float(self.coord_edit.value())
        plane.operate_object = self.operate.isChecked()
        plane.arbitrary_enabled = self.arbitrary.isChecked()
        plane.pick_mode = self.pick_btn.isChecked()
        plane.pick_hide = self.pick_hide_btn.isChecked()
        plane.rotate_angle = float(self.rotate_angle.value())
        plane.rotate_axis = ("Arb." if self.rotate_axis_group.checkedId() == 1
                             else "XYZ")
        plane.usage_guide = self.usage_guide_is_on()

        from ..model.objects import _normal_for_axis, _point_on_axis
        if self.arbitrary.isChecked():
            plane.point = self._triplet_vals()
            plane.normal = self._normal_vals()
        else:
            plane.point = _point_on_axis(ax, plane.coordinate)
            plane.normal = _normal_for_axis(ax)

        plane.display_mats = [int(m) for m in self.mat_tree.checked()]
        plane.display_volume_regions = self.vol_tree.checked()

        # Contour
        plane.show_contour = self.contour.is_checked()
        plane.contour_var = self.contour.var_name()
        plane.contour_paint = self.c_paint.isChecked()
        plane.contour_luster = self.c_luster.isChecked()
        plane.contour_water = self.c_water.isChecked()
        plane.contour_transparent = self.c_transp.isChecked()
        plane.contour_line = self.c_contour_line.isChecked()
        plane.contour_line_transparent = self.c_line_transp.isChecked()
        plane.contour_broken_line = self.c_line_broken.isChecked()
        plane.contour_mono_color = self.c_mono.isChecked()
        plane.contour_mono_rgb = self.c_mono_rgb.rgb()
        plane.contour_value = self.c_value.isChecked()
        plane.contour_thickness = int(self.c_thick.value())

        # Vector
        plane.show_vector = self.vector.is_checked()
        plane.vector_var = self.vector.var_name()
        btn = self.loc_group.checkedButton()
        if btn is not None:
            plane.vector_location = btn.text()
        plane.vector_space_u = float(self.v_space_u.value())
        plane.vector_space_v = float(self.v_space_v.value())
        plane.vector_type = self.type_combo.currentData() or "Standard"
        plane.vector_constant_length = self.v_const.isChecked()
        plane.vector_transparent = self.v_transp.isChecked()
        plane.vector_mono_color = self.v_mono.isChecked()
        plane.vector_mono_rgb = self.v_mono_rgb.rgb()
        plane.vector_contour_color = self.v_ccolor.isChecked()
        plane.vector_projection = self.v_proj.isChecked()
        plane.vector_scale_length = float(self.v_len.value())
        plane.vector_scale_thickness = float(self.v_thick.value())
        plane.vector_arrow_angle = float(self.v_arrow_angle.value())
        plane.vector_arrow_size = float(self.v_arrow_size.value())

        # Mesh / Boundary / Subline
        plane.boundary_line = self.boundary.isChecked()
        plane.boundary_auto = self.b_auto.isChecked()
        plane.boundary_broken_line = self.b_broken.isChecked()
        plane.boundary_color = self.b_color.rgb()
        plane.boundary_transparent = self.b_transp.isChecked()
        plane.show_mesh = self.mesh_display.isChecked()
        plane.mesh_transparent = self.m_transp.isChecked()
        plane.mesh_block = self.m_block.isChecked()
        plane.mesh_color = self.m_color.rgb()
        plane.mesh_thickness = int(self.m_thick.value())
        plane.mesh_paint = self.m_paint.isChecked()
        plane.mesh_paint_rgb = self.m_paint_rgb.rgb()
        plane.mesh_luster = self.m_luster.isChecked()
        plane.mesh_water = self.m_water.isChecked()
        plane.subline_external = self.sub_ext.isChecked()
        plane.subline_automatic = self.sub_auto.isChecked()
        plane.subline_display_location = self.sub_loc.isChecked()

        # Oil Flow
        plane.oilflow_display = self.oil_display.isChecked()
        plane.oilflow_var = self.oil_var.currentData() or ""
        plane.oilflow_transparent = self.oil_transp.isChecked()
        plane.oilflow_thickness = float(self.oil_thick.value())
        plane.oilflow_space_u = float(self.oil_space_u.value())
        plane.oilflow_space_v = float(self.oil_space_v.value())
        plane.oilflow_length = float(self.oil_length.value())
        plane.oilflow_draw_type = self.oil_draw.currentData() or "Line"
        plane.oilflow_integration_method = self.oil_int.currentData() or "Runge-Kutta"
        plane.oilflow_steps = int(self.oil_steps.value())
        plane.oilflow_accuracy = int(self.oil_acc.value())

        # Trim
        plane.trim_objects = self.trim_tree.checked()
        for key, val in self._trim_vals().items():
            setattr(plane, key, val)

        # Automove
        plane.automove_enabled = self.auto_enabled.isChecked()
        plane.automove_method = self.method.currentData() or "Line"
        plane.automove_loop = self.auto_loop.isChecked()
        plane.automove_standby = self.auto_standby.isChecked()
        plane.automove_frames = int(self.auto_frames.value())
        plane.automove_angle = float(self._get_spin("auto_angle",
                                                    plane.automove_angle))
        plane.automove_offset = float(self._get_spin("auto_offset",
                                                     plane.automove_offset))
        plane.automove_start_point = self._get_triplet(
            "auto_start", plane.automove_start_point)
        plane.automove_start_normal = self._get_triplet(
            "auto_start_n", plane.automove_start_normal)
        plane.automove_ref_point = self._get_triplet(
            "auto_ref", plane.automove_ref_point)
        plane.automove_ref_normal = self._get_triplet(
            "auto_ref_n", plane.automove_ref_normal)
        plane.automove_axis_point = self._get_triplet(
            "auto_axp", plane.automove_axis_point)
        plane.automove_axis_dir = self._get_triplet(
            "auto_axd", plane.automove_axis_dir)
        plane.automove_csv = self.auto_csv.text()
        plane.automove_show_path = self.auto_show_path.isChecked()
        plane.automove_path_sync = self.auto_sync.isChecked()
        plane.automove_path_distance = float(self.auto_dist.value())
        plane.automove_path_start = float(self.auto_ps.value())
        plane.automove_path_end = float(self.auto_pe.value())

        # Clip / Pick / Others
        plane.clip_enabled = self.clip_enabled.isChecked()
        plane.clip_xmin = float(self.clip_xmin.value())
        plane.clip_xmax = float(self.clip_xmax.value())
        plane.clip_ymin = float(self.clip_ymin.value())
        plane.clip_ymax = float(self.clip_ymax.value())
        plane.clip_display_region = self.clip_display.isChecked()
        plane.pick_scalar = self.pick_scalar.is_checked()
        plane.pick_scalar_var = self.pick_scalar.var_name()
        plane.pick_vector = self.pick_vector.is_checked()
        plane.pick_vector_var = self.pick_vector.var_name()
        plane.pick_ijk = self.pick_ijk.isChecked()
        plane.pick_cycle_graph = self.pick_cycle.isChecked()
        plane.pick_show_all_vars = self.pick_allvars.isChecked()
        plane.pick_show_numbers = self.pick_numbers.isChecked()
        plane.pick_color_enabled = self.pick_color.isChecked()
        plane.pick_shape = self.pick_shape.currentData() or "Sphere"
        plane.pick_line_color = self.pick_line.rgb()
        plane.pick_solid_color = self.pick_solid.rgb()

        # Integration
        plane.integrate_scalar_enabled = self.int_scalar.isChecked()
        plane.integrate_vector_enabled = self.int_vector.isChecked()
        plane.integrate_output_file = self.int_out.isChecked()
        plane.integrate_output_csv = self.int_csv.text()
        plane.integrate_include_labels = self.int_labels.isChecked()
        plane.integrate_beep = self.int_beep.isChecked()
        plane.integrate_recalc_redraw = self.int_recalc.isChecked()

        # Others / Texture / Font
        plane.use_model_coord = self.others_model_coord.isChecked()
        plane.no_vector_contour_simultaneous = self.others_no_simul.isChecked()
        plane.inter_surface = self.inter_surface.isChecked()
        plane.inter_isosurface = self.inter_isosurface.isChecked()
        plane.inter_plane = self.inter_plane.isChecked()
        plane.inter_undisplayed = self.inter_undisp.isChecked()
        plane.texture_enabled = self.tex_enabled.isChecked()
        plane.texture_file = self.tex_file.text()
        plane.texture_method = self.tex_method.currentData() or "Plane"
        plane.texture_scale = float(self.tex_scale.value())
        plane.texture_angle = float(self.tex_angle.value())
        plane.texture_pos_u = float(self.tex_pos_u.value())
        plane.texture_pos_v = float(self.tex_pos_v.value())
        plane.font_name = self.font_name.currentData() or "MS Gothic"
        plane.font_size = int(self.font_size.value())
        plane.font_float = float(self.font_float.value())

    def _get_spin(self, name: str, default: float) -> float:
        sb = self.findChild(QDoubleSpinBox, name)
        return float(sb.value()) if sb is not None else float(default)

    def _get_triplet(self, tag: str, default) -> tuple:
        vals = []
        for suff in ("px", "py", "pz"):
            sb = self.findChild(QDoubleSpinBox, f"{tag}_{suff}")
            if sb is not None:
                vals.append(float(sb.value()))
        if len(vals) == 3:
            return tuple(vals)
        p = self.findChild(QDoubleSpinBox, f"{tag}")
        if p is not None:
            return (float(p.value()),) * 3
        return tuple(default)

    def usage_guide_is_on(self) -> bool:
        return bool(getattr(self, "_usage_guide_ck", None) is not None
                    and self._usage_guide_ck.isChecked())


class ParticleDialog(_PinnedDialog):
    """scPOST Particle — Scalar / Vector / Intersection / Trim / Others /
    Font / Special tabs."""

    def __init__(self, particle, field_file=None, parent=None):
        super().__init__(particle.label if hasattr(particle, "label")
                         else "Particle (1)", parent)
        if not _HAS_QT:
            self.particle = particle
            return
        self.particle = particle
        self.field_file = field_file
        self._pvars = self._particle_vars()

        self.tabs.addTab(self._build_scalar(), "Scalar")
        self.tabs.addTab(self._build_vector(), "Vector")
        self.tabs.addTab(self._build_intersection(), "Intersection")
        self.tabs.addTab(self._build_trim(), "Trim")
        self.tabs.addTab(self._build_others(), "Others")
        self.tabs.addTab(self._build_font(), "Font")
        self.tabs.addTab(self._build_special(), "Special")

    def _particle_vars(self) -> list:
        """Particle variable names available in the file (P0.4)."""
        ff = self.field_file
        if ff is None or not getattr(ff, "has_particles", False):
            return []
        out = list(getattr(ff, "particle_vars", []) or [])
        if "VELP" not in out:
            out.insert(0, "VELP")
        return out

    def _build_scalar(self) -> QWidget:
        scalar = QWidget(self)
        lay = QVBoxLayout(scalar)

        self.scalar = _VarRow(
            "Display",
            _scalar_vars(self.field_file) + self._pvars,
            getattr(self.particle, "scalar_var", ""))
        self.scalar.check.setChecked(bool(self.particle.show_scalar))
        lay.addWidget(self.scalar)
        self.show_scalar_value = QCheckBox("Show scalar variable", scalar)
        self.show_scalar_value.setChecked(self.particle.show_scalar_value)
        lay.addWidget(self.show_scalar_value)

        lay.addWidget(_hline(scalar))
        color_row = QHBoxLayout()
        self.mono = QRadioButton("Mono color", scalar)
        self.mono.setChecked(True)
        color_row.addWidget(self.mono)
        self.color_btn = _ColorButton(self.particle.mono_color, scalar)
        color_row.addWidget(self.color_btn, 1)
        lay.addLayout(color_row)

        lay.addWidget(_hline(scalar))
        type_row = QHBoxLayout()
        self.type_group = QButtonGroup(scalar)
        for i, label in enumerate(("Points", "Sphere", "Specify", "Actual")):
            rb = QRadioButton(label, scalar)
            if label == getattr(self.particle, "particle_type", "Points"):
                rb.setChecked(True)
            self.type_group.addButton(rb, i)
            type_row.addWidget(rb)
        type_row.addStretch(1)
        lay.addLayout(type_row)

        form = QFormLayout()
        self.size = QDoubleSpinBox(scalar)
        self.size.setRange(1, 100)
        self.size.setValue(float(getattr(self.particle, "size_px", 7)))
        self.size.setSuffix(" Pixel")
        form.addRow("Size:", self.size)
        lay.addLayout(form)

        self.chk_transparent = QCheckBox("Transparent", scalar)
        self.chk_transparent.setChecked(bool(getattr(self.particle,
                                                     "transparent", False)))
        lay.addWidget(self.chk_transparent)
        lay.addStretch(1)
        return scalar

    def _build_vector(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.vector = _VarRow("Vectors on particle",
                              _vector_vars(self.field_file) + self._pvars,
                              getattr(self.particle, "vector_var", ""))
        self.vector.check.setChecked(bool(self.particle.show_vector))
        lay.addWidget(self.vector)
        self.show_vector_value = QCheckBox("Show vector value", page)
        self.show_vector_value.setChecked(self.particle.show_vector_value)
        lay.addWidget(self.show_vector_value)
        lay.addStretch(1)
        return page

    def _build_intersection(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Regions to test intersection:", page))
        self.region_list = QListWidget(page)
        for cub in getattr(self.particle, "intersection_regions", []):
            (x1, y1, z1), (x2, y2, z2) = cub
            self.region_list.addItem(
                f"({x1:g}, {y1:g}, {z1:g})-({x2:g}, {y2:g}, {z2:g})")
        lay.addWidget(self.region_list, 1)
        brow = QHBoxLayout()
        new_btn = QPushButton("New", page)
        new_btn.clicked.connect(self._intersection_new)
        mod_btn = QPushButton("Modify", page)
        mod_btn.clicked.connect(self._intersection_modify)
        del_btn = QPushButton("Delete", page)
        del_btn.clicked.connect(self._intersection_delete)
        for b in (new_btn, mod_btn, del_btn):
            brow.addWidget(b)
        brow.addStretch(1)
        lay.addLayout(brow)
        self.show_intersections = QCheckBox("Display the regions", page)
        self.show_intersections.setChecked(
            self.particle.show_intersection_regions)
        lay.addWidget(self.show_intersections)
        return page

    def _intersection_new(self) -> None:
        self.region_list.addItem("(0, 0, 0)-(1, 1, 1)")

    def _intersection_modify(self) -> None:
        it = self.region_list.currentItem()
        if it is None:
            return
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Intersection region",
                                        "Start-End (x1, y1, z1)-(x2, y2, z2)",
                                        text=it.text())
        if ok and text.strip():
            it.setText(text.strip())

    def _intersection_delete(self) -> None:
        row = self.region_list.currentRow()
        if row >= 0:
            self.region_list.takeItem(row)

    def _build_trim(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Display Range:", page))
        form = QFormLayout()
        self.trim_no = QLineEdit(self.particle.display_particle_no)
        form.addRow("Particle No:", self.trim_no)
        self.trim_attr = QLineEdit(self.particle.display_attribute_no)
        form.addRow("Attribute No:", self.trim_attr)
        self.trim_size = QLineEdit(self.particle.display_particle_size)
        form.addRow("Particle Size:", self.trim_size)
        lay.addLayout(form)
        lay.addWidget(_hline(page))
        lay.addWidget(QLabel("Trimmed by:", page))
        objects = [o.label for o in getattr(self, "_trim_objects", [])]
        self.trim_tree = _CheckTree(
            "Object", objects, list(self.particle.trim_objects))
        lay.addWidget(self.trim_tree, 1)
        return page

    def _build_others(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.use_model_coord = QCheckBox("Use the model coordinate system",
                                         page)
        self.use_model_coord.setChecked(self.particle.use_model_coord)
        lay.addWidget(self.use_model_coord)
        lay.addStretch(1)
        return page

    def _build_font(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        form = QFormLayout()
        self.font_name = QComboBox(page)
        for name in ("MS Gothic", "MS UI Gothic", "Arial", "Tahoma", "Courier"):
            self.font_name.addItem(name, name)
        idx = self.font_name.findData(self.particle.font_name)
        if idx >= 0:
            self.font_name.setCurrentIndex(idx)
        form.addRow("Fonts:", self.font_name)
        self.font_size = QSpinBox(page)
        self.font_size.setRange(4, 72)
        self.font_size.setValue(int(self.particle.font_size))
        form.addRow("Size:", self.font_size)
        self.font_float = QDoubleSpinBox(page)
        self.font_float.setRange(0, 1e6)
        self.font_float.setValue(float(self.particle.font_float))
        form.addRow("Float:", self.font_float)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _build_special(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.special_cloth = QCheckBox(
            "Cloth/String — convert particles to surface", page)
        self.special_cloth.setChecked(self.particle.special_cloth)
        lay.addWidget(self.special_cloth)
        self.special_gen = QCheckBox(
            "Variable generalization", page)
        self.special_gen.setChecked(
            self.particle.special_variable_generalization)
        lay.addWidget(self.special_gen)
        run = QPushButton("Run checked functions", page)
        run.clicked.connect(self._run_special)
        lay.addWidget(run)
        lay.addStretch(1)
        return page

    def _run_special(self) -> None:
        """Run checked Special functions (Cloth/String, generalization).

        Applies the current settings to the object and triggers a rebuild of
        the scene so the conversion can take effect.
        """
        if hasattr(self, "particle"):
            self.apply_to(self.particle)
        self.apply_requested.emit()

    def apply_to(self, particle) -> None:
        particle.show_scalar = self.scalar.is_checked()
        particle.scalar_var = self.scalar.var_name()
        particle.show_scalar_value = self.show_scalar_value.isChecked()
        particle.mono_color = self.color_btn.rgb()
        particle.size_px = float(self.size.value())
        particle.transparent = self.chk_transparent.isChecked()
        btn = self.type_group.checkedButton()
        if btn is not None:
            particle.particle_type = btn.text()
        particle.show_vector = self.vector.is_checked()
        particle.vector_var = self.vector.var_name()
        particle.show_vector_value = self.show_vector_value.isChecked()
        particle.intersection_regions = self._parse_regions()
        particle.show_intersection_regions = self.show_intersections.isChecked()
        particle.display_particle_no = self.trim_no.text()
        particle.display_attribute_no = self.trim_attr.text()
        particle.display_particle_size = self.trim_size.text()
        particle.trim_objects = self.trim_tree.checked()
        particle.use_model_coord = self.use_model_coord.isChecked()
        particle.font_name = self.font_name.currentData() or "MS Gothic"
        particle.font_size = int(self.font_size.value())
        particle.font_float = float(self.font_float.value())
        particle.special_cloth = self.special_cloth.isChecked()
        particle.special_variable_generalization = self.special_gen.isChecked()

    def _parse_regions(self) -> list:
        out = []
        for i in range(self.region_list.count()):
            text = self.region_list.item(i).text()
            p = self._parse_cuboid(text)
            if p is not None:
                out.append(p)
        return out

    @staticmethod
    def _parse_cuboid(text: str):
        import re
        m = re.match(r"\(([-\d.eE]+),\s*([-\d.eE]+),\s*([-\d.eE]+)\)-"
                     r"\(([-\d.eE]+),\s*([-\d.eE]+),\s*([-\d.eE]+)\)", text)
        if m:
            a = tuple(float(m.group(i)) for i in range(1, 4))
            b = tuple(float(m.group(i)) for i in range(4, 7))
            return a, b
        return None
