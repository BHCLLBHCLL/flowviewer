"""Property dialogs for Isosurface / Point / Streamline / Volume / Colorbar.

Follows the same non-modal ``ObjectSettingsPanel`` pattern as Surface/Plane /
Particle (tiled in the Control Window's PropertyHost), with ``apply_to``
writing the widget state back onto the corresponding ``*Object``.
"""

from __future__ import annotations

try:
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
        QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget,
    )
    _HAS_QT = True
except Exception:  # pragma: no cover
    _HAS_QT = False

from .object_dialogs import (
    ObjectSettingsPanel, _ColorButton, _scalar_vars, _hline,
)


def _var_combo(variables: list[str], value: str) -> QComboBox:
    """Combo with a leading "(none)" plus the variable list."""
    cb = QComboBox()
    cb.addItem("(none)", "")
    for n in variables:
        cb.addItem(n, n)
    idx = cb.findData(value)
    if idx >= 0:
        cb.setCurrentIndex(idx)
    return cb


def _dspin(value: float, lo: float = -1e9, hi: float = 1e9,
           decimals: int = 6) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setDecimals(decimals)
    sb.setValue(float(value))
    return sb


def _vector_bases(ff) -> list[str]:
    """Unique vector base names (component minus trailing X/Y/Z)."""
    if ff is None:
        return []
    out = []
    for n, v in ff.variables.items():
        if v.kind == "vector" and n.endswith(("X", "Y", "Z")):
            base = n[:-1]
            if base and base not in out:
                out.append(base)
    return sorted(out)


def _parse_floats(text: str) -> list[float]:
    out = []
    for tok in str(text).replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            pass
    return out


class IsosurfaceDialog(ObjectSettingsPanel):
    """scPOST Isosurface — Contour / Vector."""

    def __init__(self, isosurface, field_file=None, parent=None):
        super().__init__(getattr(isosurface, "label", "Isosurface (1)"),
                         parent)
        if not _HAS_QT:
            self.sc = isosurface
            return
        self.sc = isosurface
        self.field_file = field_file
        self.scalars = _scalar_vars(field_file)
        self.vectors = _vector_bases(field_file)
        self.tabs.addTab(self._build_contour(), "Contour")
        self.tabs.addTab(self._build_vector(), "Vector")

    def _build_contour(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        row = QHBoxLayout()
        self.display = QCheckBox("Display", page)
        self.display.setChecked(bool(self.sc.show_contour))
        row.addWidget(self.display)
        row.addWidget(QLabel("Variable:", page))
        self.var = _var_combo(self.scalars, self.sc.contour_var)
        row.addWidget(self.var, 1)
        lay.addLayout(row)

        form = QFormLayout()
        self.use_auto = QCheckBox("Auto (distribute values)", page)
        self.use_auto.setChecked(bool(self.sc.contour_auto))
        form.addRow("Levels:", self.use_auto)
        self.values_edit = QLineEdit(
            ", ".join(f"{v:.6g}" for v in self.sc.contour_values), page)
        form.addRow("Values:", self.values_edit)
        self.number = QSpinBox(page)
        self.number.setRange(1, 100)
        self.number.setValue(int(self.sc.contour_number))
        form.addRow("Auto number:", self.number)
        lay.addLayout(form)

        lay.addWidget(_hline(page))
        self.transparent = QCheckBox("Transparent", page)
        self.transparent.setChecked(bool(self.sc.contour_transparent))
        lay.addWidget(self.transparent)
        self.line = QCheckBox("Mesh lines", page)
        self.line.setChecked(bool(self.sc.contour_line))
        lay.addWidget(self.line)
        self.mono = QCheckBox("Mono color", page)
        self.mono.setChecked(bool(self.sc.contour_mono_color))
        lay.addWidget(self.mono)
        self.mono_rgb = _ColorButton(self.sc.contour_mono_rgb, page)
        lay.addWidget(self.mono_rgb)
        lay.addStretch(1)
        return page

    def _build_vector(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        row = QHBoxLayout()
        self.vector_display = QCheckBox("Display", page)
        self.vector_display.setChecked(bool(self.sc.show_vector))
        row.addWidget(self.vector_display)
        row.addWidget(QLabel("Vector:", page))
        self.vector_var = _var_combo(self.vectors, self.sc.vector_var)
        row.addWidget(self.vector_var, 1)
        lay.addLayout(row)
        form = QFormLayout()
        self.vector_scale = _dspin(self.sc.vector_scale_length,
                                   decimals=3)
        form.addRow("Scale length:", self.vector_scale)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.show_contour = self.display.isChecked()
        obj.contour_var = self.var.currentData() or ""
        obj.contour_auto = self.use_auto.isChecked()
        obj.contour_values = _parse_floats(self.values_edit.text())
        obj.contour_number = int(self.number.value())
        obj.contour_transparent = self.transparent.isChecked()
        obj.contour_line = self.line.isChecked()
        obj.contour_mono_color = self.mono.isChecked()
        obj.contour_mono_rgb = self.mono_rgb.rgb()
        obj.show_vector = self.vector_display.isChecked()
        obj.vector_var = self.vector_var.currentData() or ""
        obj.vector_scale_length = float(self.vector_scale.value())


class PointDialog(ObjectSettingsPanel):
    """scPOST Point — Coordinate / Probe."""

    def __init__(self, pt, field_file=None, parent=None):
        super().__init__(getattr(pt, "label", "Point (1)"), parent)
        if not _HAS_QT:
            self.pt = pt
            return
        self.pt = pt
        self.field_file = field_file
        self.scalars = _scalar_vars(field_file)
        self.vectors = _vector_bases(field_file)
        self.tabs.addTab(self._build_coordinate(), "Coordinate")
        self.tabs.addTab(self._build_probe(), "Probe")

    def _build_coordinate(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout()
        self.pos = [_dspin(self.pt.position[i], decimals=8) for i in range(3)]
        for lbl, sb in zip(("X", "Y", "Z"), self.pos):
            form.addRow(f"{lbl}:", sb)
        self.shape_box = QComboBox(page)
        for name in ("Sphere", "Cross", "Plus"):
            self.shape_box.addItem(name, name)
        self.shape_box.setCurrentIndex(
            max(0, self.shape_box.findData(self.pt.shape)))
        form.addRow("Shape:", self.shape_box)
        self.size = _dspin(self.pt.size, 0.1, 100, decimals=2)
        form.addRow("Size:", self.size)
        self.color = _ColorButton(self.pt.color, page)
        form.addRow("Color:", self.color)
        self.transparent = QCheckBox("Transparent", page)
        self.transparent.setChecked(bool(self.pt.transparent))
        form.addRow("", self.transparent)
        lay = QVBoxLayout(page)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _build_probe(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        row = QHBoxLayout()
        self.probe_scalar = QCheckBox("Scalar", page)
        self.probe_scalar.setChecked(bool(self.pt.probe_scalar))
        row.addWidget(self.probe_scalar)
        self.scalar_var = _var_combo(self.scalars, self.pt.probe_scalar_var)
        row.addWidget(self.scalar_var, 1)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        self.probe_vector = QCheckBox("Vector", page)
        self.probe_vector.setChecked(bool(self.pt.probe_vector))
        row2.addWidget(self.probe_vector)
        self.vector_var = _var_combo(self.vectors, self.pt.probe_vector_var)
        row2.addWidget(self.vector_var, 1)
        lay.addLayout(row2)
        self.show_values = QCheckBox("Show values", page)
        self.show_values.setChecked(bool(self.pt.probe_show_values))
        lay.addWidget(self.show_values)
        lay.addStretch(1)
        return page

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.position = tuple(float(s.value()) for s in self.pos)
        obj.shape = self.shape_box.currentData() or "Sphere"
        obj.size = float(self.size.value())
        obj.color = self.color.rgb()
        obj.transparent = self.transparent.isChecked()
        obj.probe_scalar = self.probe_scalar.isChecked()
        obj.probe_scalar_var = self.scalar_var.currentData() or ""
        obj.probe_vector = self.probe_vector.isChecked()
        obj.probe_vector_var = self.vector_var.currentData() or ""
        obj.probe_show_values = self.show_values.isChecked()


class StreamlineDialog(ObjectSettingsPanel):
    """scPOST Streamline — Seed / Direction / Display."""

    def __init__(self, sl, field_file=None, parent=None):
        super().__init__(getattr(sl, "label", "Streamline (1)"), parent)
        if not _HAS_QT:
            self.sl = sl
            return
        self.sl = sl
        self.field_file = field_file
        self.scalars = _scalar_vars(field_file)
        self.vectors = _vector_bases(field_file)
        self.tabs.addTab(self._build_seed(), "Seed")
        self.tabs.addTab(self._build_direction(), "Direction")
        self.tabs.addTab(self._build_display(), "Display")

    def _build_seed(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        form = QFormLayout()
        self.axis_box = QComboBox(page)
        for name in ("Arbitrary", "X", "Y", "Z"):
            self.axis_box.addItem(name, name)
        self.axis_box.setCurrentIndex(
            max(0, self.axis_box.findData(self.sl.seed_axis)))
        form.addRow("Axis:", self.axis_box)
        self.coord = _dspin(self.sl.seed_coordinate, decimals=6)
        form.addRow("Coordinate:", self.coord)
        cent = QHBoxLayout()
        self.center = [_dspin(self.sl.seed_center[i], decimals=6)
                       for i in range(3)]
        for lbl, sb in zip(("x", "y", "z"), self.center):
            cent.addWidget(QLabel(lbl, page))
            cent.addWidget(sb)
        form.addRow("Center:", self._wrap_hl(cent))
        self.density_u = QSpinBox(page)
        self.density_u.setRange(1, 200)
        self.density_u.setValue(int(self.sl.seed_density_u))
        form.addRow("Density U:", self.density_u)
        self.density_v = QSpinBox(page)
        self.density_v.setRange(1, 200)
        self.density_v.setValue(int(self.sl.seed_density_v))
        form.addRow("Density V:", self.density_v)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _build_direction(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("Vector field:", page))
        self.vector = _var_combo(self.vectors, self.sl.vector_var)
        row.addWidget(self.vector, 1)
        lay.addLayout(row)
        form = QFormLayout()
        self.direction = QComboBox(page)
        for name in ("Forward", "Backward", "Both"):
            self.direction.addItem(name, name)
        self.direction.setCurrentIndex(
            max(0, self.direction.findData(self.sl.direction)))
        form.addRow("Direction:", self.direction)
        self.method = QComboBox(page)
        for name in ("Runge-Kutta", "Euler"):
            self.method.addItem(name, name)
        self.method.setCurrentIndex(
            max(0, self.method.findData(self.sl.integration_method)))
        form.addRow("Method:", self.method)
        self.length = _dspin(self.sl.length, 0.0, 1e9, decimals=4)
        form.addRow("Length:", self.length)
        self.step = _dspin(self.sl.step_size, 1e-9, 1, decimals=6)
        form.addRow("Step size:", self.step)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _build_display(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        row = QHBoxLayout()
        row.addWidget(QLabel("Color by:", page))
        self.color = _var_combo(self.scalars, self.sl.color_var)
        row.addWidget(self.color, 1)
        lay.addLayout(row)
        form = QFormLayout()
        self.draw_type = QComboBox(page)
        for name in ("Line", "Triangle", "Tube"):
            self.draw_type.addItem(name, name)
        self.draw_type.setCurrentIndex(
            max(0, self.draw_type.findData(self.sl.draw_type)))
        form.addRow("Draw:", self.draw_type)
        self.thickness = _dspin(self.sl.thickness, 0.1, 50, 1)
        form.addRow("Thickness:", self.thickness)
        lay.addLayout(form)
        self.transparent = QCheckBox("Transparent", page)
        self.transparent.setChecked(bool(self.sl.transparent))
        lay.addWidget(self.transparent)
        lay.addStretch(1)
        return page

    def _wrap_hl(self, hl) -> QWidget:
        w = QWidget(self)
        inner = QHBoxLayout(w)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addLayout(hl)
        return w

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.seed_axis = self.axis_box.currentData() or "Arbitrary"
        obj.seed_coordinate = float(self.coord.value())
        obj.seed_center = tuple(float(s.value()) for s in self.center)
        obj.seed_density_u = int(self.density_u.value())
        obj.seed_density_v = int(self.density_v.value())
        obj.vector_var = self.vector.currentData() or ""
        obj.direction = self.direction.currentData() or "Forward"
        obj.integration_method = self.method.currentData() or "Runge-Kutta"
        obj.length = float(self.length.value())
        obj.step_size = float(self.step.value())
        obj.color_var = self.color.currentData() or ""
        obj.draw_type = self.draw_type.currentData() or "Line"
        obj.thickness = float(self.thickness.value())
        obj.transparent = self.transparent.isChecked()


class VolumeDialog(ObjectSettingsPanel):
    """scPOST Volume — Scalar / Vector."""

    def __init__(self, vobj, field_file=None, parent=None):
        super().__init__(getattr(vobj, "label", "Volume (1)"), parent)
        if not _HAS_QT:
            self.vobj = vobj
            return
        self.vobj = vobj
        self.field_file = field_file
        self.scalars = _scalar_vars(field_file)
        self.vectors = _vector_bases(field_file)
        self.tabs.addTab(self._build_scalar(), "Scalar")
        self.tabs.addTab(self._build_vector(), "Vector")

    def _build_scalar(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        row = QHBoxLayout()
        self.display = QCheckBox("Display", page)
        self.display.setChecked(bool(self.vobj.show_scalar))
        row.addWidget(self.display)
        row.addWidget(QLabel("Variable:", page))
        self.var = _var_combo(self.scalars, self.vobj.scalar_var)
        row.addWidget(self.var, 1)
        lay.addLayout(row)
        form = QFormLayout()
        self.opacity = _dspin(self.vobj.scalar_opacity, 0.0, 1.0, 2)
        form.addRow("Opacity:", self.opacity)
        self.sampling = QSpinBox(page)
        self.sampling.setRange(1, 100)
        self.sampling.setValue(int(self.vobj.sampling))
        form.addRow("Sampling:", self.sampling)
        lay.addLayout(form)
        lay.addWidget(_hline(page))
        self.draw = QComboBox(page)
        for name in ("Solid", "Transparent", "Sampled"):
            self.draw.addItem(name, name)
        self.draw.setCurrentIndex(
            max(0, self.draw.findData(self.vobj.draw_type)))
        lay.addWidget(QLabel("Draw type:", page))
        lay.addWidget(self.draw)
        self.mono = QCheckBox("Mono color", page)
        self.mono.setChecked(bool(self.vobj.scalar_mono_color))
        lay.addWidget(self.mono)
        self.mono_rgb = _ColorButton(self.vobj.scalar_mono_rgb, page)
        lay.addWidget(self.mono_rgb)
        lay.addStretch(1)
        return page

    def _build_vector(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        row = QHBoxLayout()
        self.vector_display = QCheckBox("Display", page)
        self.vector_display.setChecked(bool(self.vobj.show_vector))
        row.addWidget(self.vector_display)
        row.addWidget(QLabel("Vector:", page))
        self.vector_var = _var_combo(self.vectors, self.vobj.vector_var)
        row.addWidget(self.vector_var, 1)
        lay.addLayout(row)
        form = QFormLayout()
        self.vector_scale = _dspin(self.vobj.vector_scale_length, decimals=3)
        form.addRow("Scale length:", self.vector_scale)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.show_scalar = self.display.isChecked()
        obj.scalar_var = self.var.currentData() or ""
        obj.scalar_opacity = float(self.opacity.value())
        obj.sampling = int(self.sampling.value())
        obj.draw_type = self.draw.currentData() or "Solid"
        obj.scalar_mono_color = self.mono.isChecked()
        obj.scalar_mono_rgb = self.mono_rgb.rgb()
        obj.show_vector = self.vector_display.isChecked()
        obj.vector_var = self.vector_var.currentData() or ""
        obj.vector_scale_length = float(self.vector_scale.value())


class ColorbarDialog(ObjectSettingsPanel):
    """Global Colorbar — Range / Gradation / Display."""

    def __init__(self, cbar, field_file=None, parent=None):
        super().__init__(getattr(cbar, "label", "Colorbar"), parent)
        if not _HAS_QT:
            self.cbar = cbar
            return
        self.cbar = cbar
        page = QWidget(self)
        form = QFormLayout()
        self.gradation = QSpinBox(page)
        self.gradation.setRange(16, 1024)
        self.gradation.setValue(int(cbar.gradation))
        form.addRow("Gradation:", self.gradation)
        self.color_map = QComboBox(page)
        for name in ("Rainbow", "Gray", "Invert"):
            self.color_map.addItem(name, name)
        self.color_map.setCurrentIndex(
            max(0, self.color_map.findData(cbar.color_map)))
        form.addRow("Color map:", self.color_map)
        self.range_mode = QComboBox(page)
        for name in ("Auto", "Fix"):
            self.range_mode.addItem(name, name)
        self.range_mode.setCurrentIndex(
            max(0, self.range_mode.findData(cbar.range_mode)))
        form.addRow("Range:", self.range_mode)
        self.min = _dspin(cbar.min, -1e12, 1e12, 6)
        form.addRow("Min:", self.min)
        self.max = _dspin(cbar.max, -1e12, 1e12, 6)
        form.addRow("Max:", self.max)
        self.orientation = QComboBox(page)
        for name in ("Horizontal", "Vertical"):
            self.orientation.addItem(name, name)
        self.orientation.setCurrentIndex(
            max(0, self.orientation.findData(cbar.orientation)))
        form.addRow("Orientation:", self.orientation)
        lay = QVBoxLayout(page)
        lay.addLayout(form)
        lay.addStretch(1)
        self.tabs.addTab(page, "Colorbar")

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.gradation = int(self.gradation.value())
        obj.color_map = self.color_map.currentData() or "Rainbow"
        obj.range_mode = self.range_mode.currentData() or "Auto"
        obj.min = float(self.min.value())
        obj.max = float(self.max.value())
        obj.orientation = self.orientation.currentData() or "Horizontal"


