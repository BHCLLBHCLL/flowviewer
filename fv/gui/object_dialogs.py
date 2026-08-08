"""Property dialogs for Surface / Plane / Particle (scPOST-style tabs)."""

from __future__ import annotations

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


class _PinnedDialog(QDialog if _HAS_QT else object):
    """Title bar chrome shared by object property dialogs."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        if not _HAS_QT:
            return
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | Qt.Window)
        self.resize(480, 420)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(6, 6, 6, 6)
        self._root.setSpacing(4)
        from .dialogs import DialogHeader
        self._root.addWidget(DialogHeader(title, "surface", self))
        self.tabs = QTabWidget(self)
        self._root.addWidget(self.tabs, 1)
        brow = QHBoxLayout()
        brow.addStretch(1)
        ok = QPushButton("OK", self)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        brow.addWidget(ok)
        brow.addWidget(cancel)
        self._root.addLayout(brow)


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
    Mesh / Automove / Trim tabs."""

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
        self.tabs.addTab(self._build_automove(), "Automove")
        self.tabs.addTab(self._build_trim(), "Trim")

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
        lay.addWidget(self.operate)

        lay.addWidget(_hline(coord))
        arb_row = QHBoxLayout()
        arb_row.addWidget(QLabel("Arbitrary:", coord))
        self.arbitrary = QCheckBox("Define by point and normal", coord)
        arb_row.addWidget(self.arbitrary)
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
        lay.addStretch(1)

        self.axis_group.buttonClicked.connect(self._on_axis)
        return coord

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

    # ── shared tabs ──────────────────────────────────────────────────────

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

    def _build_contour(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.contour = _VarRow("Display", _scalar_vars(self.field_file),
                               getattr(self.plane, "contour_var", ""))
        self.contour.check.setChecked(bool(self.plane.show_contour))
        lay.addWidget(self.contour)
        lay.addStretch(1)
        return page

    def _build_vector(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.vector = _VarRow("Display", _vector_vars(self.field_file),
                              getattr(self.plane, "vector_var", ""))
        self.vector.check.setChecked(bool(self.plane.show_vector))
        lay.addWidget(self.vector)
        lay.addStretch(1)
        return page

    def _build_mesh(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.boundary = QCheckBox("Boundary", page)
        self.boundary.setChecked(self.plane.boundary_line)
        lay.addWidget(self.boundary)
        self.b_transp = QCheckBox("Transparent", page)
        self.b_transp.setChecked(self.plane.boundary_transparent)
        lay.addWidget(self.b_transp)
        form = QFormLayout()
        self.b_color = _ColorButton(self.plane.boundary_color, page)
        form.addRow("Color:", self.b_color)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

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
        mrow.addWidget(self.method, 1)
        lay.addLayout(mrow)
        form = QFormLayout()
        self.auto_speed = QDoubleSpinBox(page)
        self.auto_speed.setRange(0, 1e6)
        self.auto_speed.setValue(1.0)
        self.auto_speed.setSuffix(" m/step")
        form.addRow("Speed:", self.auto_speed)
        self.auto_start = QDoubleSpinBox(page)
        self.auto_start.setRange(-1e6, 1e6)
        self.auto_start.setValue(self._lo)
        form.addRow("Start:", self.auto_start)
        self.auto_end = QDoubleSpinBox(page)
        self.auto_end.setRange(-1e6, 1e6)
        self.auto_end.setValue(self._hi)
        form.addRow("End:", self.auto_end)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _build_trim(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        objects = [o.label for o in getattr(self, "_trim_objects", [])]
        lay.addWidget(QLabel("Trimmed by:", page))
        self.trim_tree = _CheckTree(
            "Object", objects, list(self.plane.trim_objects))
        lay.addWidget(self.trim_tree, 1)
        return page

    # ── apply ────────────────────────────────────────────────────────────

    def apply_to(self, plane) -> None:
        ax = {0: "X", 1: "Y", 2: "Z"}.get(self.axis_group.checkedId(), "Z")
        plane.axis = ax
        plane.coordinate = float(self.coord_edit.value())
        from ..model.objects import _normal_for_axis, _point_on_axis
        if self.arbitrary.isChecked():
            plane.point = (self.point_x.value(), self.point_y.value(),
                           self.point_z.value())
            plane.normal = (self.norm_x.value(), self.norm_y.value(),
                            self.norm_z.value())
        else:
            plane.point = _point_on_axis(ax, plane.coordinate)
            plane.normal = _normal_for_axis(ax)
        plane.display_mats = [int(m) for m in self.mat_tree.checked()]
        plane.display_volume_regions = self.vol_tree.checked()
        plane.show_contour = self.contour.is_checked()
        plane.contour_var = self.contour.var_name()
        plane.show_vector = self.vector.is_checked()
        plane.vector_var = self.vector.var_name()
        plane.boundary_line = self.boundary.isChecked()
        plane.boundary_transparent = self.b_transp.isChecked()
        plane.boundary_color = self.b_color.rgb()
        plane.automove_enabled = self.auto_enabled.isChecked()
        plane.automove_method = self.method.currentData() or "Line"
        plane.trim_objects = self.trim_tree.checked()


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

        self.tabs.addTab(self._build_scalar(), "Scalar")
        self.tabs.addTab(self._build_vector(), "Vector")
        self.tabs.addTab(self._build_intersection(), "Intersection")
        self.tabs.addTab(self._build_trim(), "Trim")
        self.tabs.addTab(self._build_others(), "Others")
        self.tabs.addTab(self._build_font(), "Font")
        self.tabs.addTab(self._build_special(), "Special")

    def _build_scalar(self) -> QWidget:
        scalar = QWidget(self)
        lay = QVBoxLayout(scalar)

        self.scalar = _VarRow("Display", _scalar_vars(self.field_file),
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
                              _vector_vars(self.field_file),
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
        self.trim_tree = _CheckTree("Object", [], self.particle.trim_objects)
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
        lay.addWidget(run)
        lay.addStretch(1)
        return page

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
