"""Property dialogs for Isosurface / Point / Streamline / Volume / Colorbar.

Follows the same non-modal ``ObjectSettingsPanel`` pattern as Surface/Plane /
Particle (tiled in the Control Window's PropertyHost), with ``apply_to``
writing the widget state back onto the corresponding ``*Object``.
"""

from __future__ import annotations

try:
    from PyQt5.QtWidgets import (
        QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
        QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
        QPushButton, QSpinBox, QVBoxLayout, QWidget,
    )
    _HAS_QT = True
except Exception:  # pragma: no cover
    _HAS_QT = False

from .object_dialogs import (
    ObjectSettingsPanel, _ColorButton, _scalar_vars, _VarRow, _hline,
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


class LightDialog(ObjectSettingsPanel):
    """Global Light — Brightness / Colour / Direction (P0.3)."""

    def __init__(self, light, field_file=None, parent=None):
        super().__init__(getattr(light, "label", "Light"), parent)
        if not _HAS_QT:
            self.light = light
            return
        self.light = light
        page = QWidget(self)
        form = QFormLayout()
        self.enabled = QCheckBox("Light enabled", page)
        self.enabled.setChecked(bool(getattr(light, "enabled", True)))
        form.addRow("", self.enabled)
        self.brightness = _dspin(getattr(light, "brightness", 1.0),
                                0.0, 2.0, 2)
        form.addRow("Brightness:", self.brightness)
        self.color = _ColorButton(getattr(light, "color", (1.0, 1.0, 1.0)),
                                  page)
        form.addRow("Colour:", self.color)
        px, py, pz = getattr(light, "position", (1.0, 1.0, 1.0))
        self.pos_x = _dspin(px, -1e6, 1e6, 4)
        self.pos_y = _dspin(py, -1e6, 1e6, 4)
        self.pos_z = _dspin(pz, -1e6, 1e6, 4)
        row = QHBoxLayout()
        row.addWidget(QLabel("Direction:", page))
        row.addWidget(self.pos_x)
        row.addWidget(self.pos_y)
        row.addWidget(self.pos_z)
        form.addRow(row)
        lay = QVBoxLayout(page)
        lay.addLayout(form)
        lay.addStretch(1)
        self.tabs.addTab(page, "Brightness")

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.enabled = self.enabled.isChecked()
        obj.brightness = float(self.brightness.value())
        obj.color = self.color.rgb()
        obj.position = (float(self.pos_x.value()),
                        float(self.pos_y.value()),
                        float(self.pos_z.value()))


class PathlineDialog(ObjectSettingsPanel):
    """Pathline (PCL) — Seed / Direction / Display (P1.5)."""

    def __init__(self, pl, field_file=None, parent=None):
        super().__init__(getattr(pl, "label", "Pathline"), parent)
        if not _HAS_QT:
            self.pl = pl
            return
        self.pl = pl
        self.field_file = field_file
        self.vectors = _vector_bases(field_file)
        self.tabs.addTab(self._build_seed(), "Seed")
        self.tabs.addTab(self._build_direction(), "Direction")
        self.tabs.addTab(self._build_display(), "Display")

    def _build_seed(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout()
        self.axis = QComboBox(page)
        for a in ("X", "Y", "Z", "Arbitrary"):
            self.axis.addItem(a, a)
        self.axis.setCurrentIndex(max(0, self.axis.findData(
            getattr(self.pl, "seed_axis", "Z"))))
        form.addRow("Axis:", self.axis)
        c = getattr(self.pl, "seed_coordinate", None)
        self.coord = _dspin(0.0 if c is None else c, -1e9, 1e9, 6)
        form.addRow("Coordinate:", self.coord)
        self.du = QSpinBox(page);
        self.du.setRange(1, 200);
        self.du.setValue(int(getattr(self.pl, "density_u", 8)))
        form.addRow("Density U:", self.du)
        self.dv = QSpinBox(page);
        self.dv.setRange(1, 200);
        self.dv.setValue(int(getattr(self.pl, "density_v", 8)))
        form.addRow("Density V:", self.dv)
        lay = QVBoxLayout(page);
        lay.addLayout(form);
        lay.addStretch(1)
        return page

    def _build_direction(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout()
        self.vector = _var_combo(self.vectors, self.pl.vector_var)
        form.addRow("Vector field:", self.vector)
        self.dir = QComboBox(page)
        for d in ("Forward", "Backward"):
            self.dir.addItem(d, d)
        self.dir.setCurrentIndex(max(0, self.dir.findData(
            self.pl.direction)))
        form.addRow("Direction:", self.dir)
        self.steps = QSpinBox(page);
        self.steps.setRange(1, 1000);
        self.steps.setValue(int(getattr(self.pl, "steps_per_cycle", 10)))
        form.addRow("Steps per cycle:", self.steps)
        lay = QVBoxLayout(page);
        lay.addLayout(form);
        lay.addStretch(1)
        return page

    def _build_display(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout()
        self.draw = QComboBox(page)
        for d in ("Line", "Triangle", "Tube"):
            self.draw.addItem(d, d)
        self.draw.setCurrentIndex(max(0, self.draw.findData(
            self.pl.draw_type)))
        form.addRow("Draw:", self.draw)
        self.thick = _dspin(getattr(self.pl, "thickness", 1.0), 1.0, 20.0, 1)
        form.addRow("Thickness:", self.thick)
        self.color = _ColorButton(self.pl.mono_color, page)
        form.addRow("Color:", self.color)
        self.transp = QCheckBox("Transparent", page)
        self.transp.setChecked(bool(self.pl.transparent))
        lay = QVBoxLayout(page);
        lay.addLayout(form);
        lay.addWidget(self.transp);
        lay.addStretch(1)
        return page

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.seed_axis = self.axis.currentData() or "Z"
        obj.seed_coordinate = float(self.coord.value())
        obj.density_u = int(self.du.value())
        obj.density_v = int(self.dv.value())
        obj.vector_var = self.vector.currentData() or "VEL"
        obj.direction = self.dir.currentData() or "Forward"
        obj.steps_per_cycle = int(self.steps.value())
        obj.draw_type = self.draw.currentData() or "Line"
        obj.thickness = float(self.thick.value())
        obj.mono_color = self.color.rgb()
        obj.transparent = self.transp.isChecked()

class CylinderDialog(ObjectSettingsPanel):
    """Cylinder — Coordinate / Contour / Vector / Mesh (P2.1)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Cylinder"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        self.field_file = field_file
        self.scalars = _scalar_vars(field_file)
        self.vectors = _vector_bases(field_file)
        self.tabs.addTab(self._build_coord(), "Coordinate")
        self.tabs.addTab(self._build_contour(), "Contour")
        self.tabs.addTab(self._build_vector(), "Vector")
        self.tabs.addTab(self._build_mesh(), "Mesh")

    def _build_coord(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout()
        self.axis = QComboBox(page)
        for a in ("X", "Y", "Z"):
            self.axis.addItem(a, a)
        self.axis.setCurrentIndex(max(0, self.axis.findData(self.obj.axis)))
        form.addRow("Axis:", self.axis)
        cx, cy, cz = self.obj.center
        self.cx = _dspin(cx, -1e9, 1e9, 6);
        self.cy = _dspin(cy, -1e9, 1e9, 6);
        self.cz = _dspin(cz, -1e9, 1e9, 6)
        row = QHBoxLayout();
        row.addWidget(self.cx); row.addWidget(self.cy); row.addWidget(self.cz)
        form.addRow("Center X/Y/Z:", row)
        self.radius = _dspin(self.obj.radius, 1e-6, 1e9, 6)
        form.addRow("Radius:", self.radius)
        self.height = _dspin(self.obj.height, 1e-6, 1e9, 6)
        form.addRow("Half-height:", self.height)
        lay = QVBoxLayout(page); lay.addLayout(form); lay.addStretch(1)
        return page

    def _build_contour(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.contour = _VarRow("Display", self.scalars, self.obj.contour_var)
        self.contour.check.setChecked(bool(self.obj.show_contour))
        lay.addWidget(self.contour)
        self.transp = QCheckBox("Transparent", page)
        self.transp.setChecked(bool(self.obj.contour_transparent))
        lay.addWidget(self.transp)
        lay.addStretch(1)
        return page

    def _build_vector(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.vector = _VarRow("Display", self.vectors, self.obj.vector_var)
        self.vector.check.setChecked(bool(self.obj.show_vector))
        lay.addWidget(self.vector)
        form = QFormLayout()
        self.scale = _dspin(self.obj.vector_scale_length, decimals=3)
        form.addRow("Scale length:", self.scale)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def _build_mesh(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.mesh = QCheckBox("Display mesh", page)
        self.mesh.setChecked(bool(self.obj.show_mesh))
        lay.addWidget(self.mesh)
        form = QFormLayout()
        self.mcolor = _ColorButton(self.obj.mesh_color, page)
        form.addRow("Color:", self.mcolor)
        self.mthick = QSpinBox(page); self.mthick.setRange(1, 10)
        self.mthick.setValue(int(self.obj.mesh_thickness))
        form.addRow("Thickness:", self.mthick)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.axis = self.axis.currentData() or "Z"
        obj.center = (float(self.cx.value()), float(self.cy.value()),
                     float(self.cz.value()))
        obj.radius = float(self.radius.value())
        obj.height = float(self.height.value())
        obj.show_contour = self.contour.check.isChecked()
        obj.contour_var = self.contour.var_name()
        obj.contour_transparent = self.transp.isChecked()
        obj.show_vector = self.vector.check.isChecked()
        obj.vector_var = self.vector.var_name()
        obj.vector_scale_length = float(self.scale.value())
        obj.show_mesh = self.mesh.isChecked()
        obj.mesh_color = self.mcolor.rgb()
        obj.mesh_thickness = int(self.mthick.value())


class CircleDialog(ObjectSettingsPanel):
    """Circle — Coordinate / Contour / Vector / Mesh (P2.1)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Circle"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        self.field_file = field_file
        self.scalars = _scalar_vars(field_file)
        self.vectors = _vector_bases(field_file)
        self.tabs.addTab(self._build_coord(), "Coordinate")
        self.tabs.addTab(self._build_contour(), "Contour")
        self.tabs.addTab(self._build_vector(), "Vector")
        self.tabs.addTab(self._build_mesh(), "Mesh")

    def _build_coord(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout()
        self.axis = QComboBox(page)
        for a in ("X", "Y", "Z"):
            self.axis.addItem(a, a)
        self.axis.setCurrentIndex(max(0, self.axis.findData(self.obj.axis)))
        form.addRow("Axis:", self.axis)
        self.coord = _dspin(self.obj.coordinate, -1e9, 1e9, 6)
        form.addRow("Coordinate:", self.coord)
        cx, cy, cz = self.obj.center
        self.cx = _dspin(cx, -1e9, 1e9, 6);
        self.cy = _dspin(cy, -1e9, 1e9, 6);
        self.cz = _dspin(cz, -1e9, 1e9, 6)
        row = QHBoxLayout();
        row.addWidget(self.cx); row.addWidget(self.cy); row.addWidget(self.cz)
        form.addRow("Center X/Y/Z:", row)
        self.radius = _dspin(self.obj.radius, 1e-6, 1e9, 6)
        form.addRow("Radius:", self.radius)
        lay = QVBoxLayout(page); lay.addLayout(form); lay.addStretch(1)
        return page

    def _build_contour(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.contour = _VarRow("Display", self.scalars, self.obj.contour_var)
        self.contour.check.setChecked(bool(self.obj.show_contour))
        lay.addWidget(self.contour)
        lay.addStretch(1)
        return page

    def _build_vector(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.vector = _VarRow("Display", self.vectors, self.obj.vector_var)
        self.vector.check.setChecked(bool(self.obj.show_vector))
        lay.addWidget(self.vector)
        lay.addStretch(1)
        return page

    def _build_mesh(self) -> QWidget:
        page = QWidget(self)
        lay = QVBoxLayout(page)
        self.mesh = QCheckBox("Display mesh", page)
        self.mesh.setChecked(bool(self.obj.show_mesh))
        lay.addWidget(self.mesh)
        form = QFormLayout()
        self.mcolor = _ColorButton(self.obj.mesh_color, page)
        form.addRow("Color:", self.mcolor)
        lay.addLayout(form)
        lay.addStretch(1)
        return page

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.axis = self.axis.currentData() or "Z"
        obj.coordinate = float(self.coord.value())
        obj.center = (float(self.cx.value()), float(self.cy.value()),
                     float(self.cz.value()))
        obj.radius = float(self.radius.value())
        obj.show_contour = self.contour.check.isChecked()
        obj.contour_var = self.contour.var_name()
        obj.show_vector = self.vector.check.isChecked()
        obj.vector_var = self.vector.var_name()
        obj.show_mesh = self.mesh.isChecked()
        obj.mesh_color = self.mcolor.rgb()

class TextDialog(ObjectSettingsPanel):
    """Text annotation — Content / Position / Font (P2.3)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Text"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        page = QWidget(self)
        form = QFormLayout()
        self.text = QLineEdit(getattr(obj, "text", "Text"), page)
        form.addRow("Text:", self.text)
        px, py = getattr(obj, "position", (0.1, 0.85))
        self.px = _dspin(px, 0.0, 1.0, 3);
        self.py = _dspin(py, 0.0, 1.0, 3)
        row = QHBoxLayout(); row.addWidget(self.px); row.addWidget(self.py)
        form.addRow("Position X/Y:", row)
        self.size = QSpinBox(page); self.size.setRange(6, 100)
        self.size.setValue(int(getattr(obj, "font_size", 14)))
        form.addRow("Font size:", self.size)
        self.color = _ColorButton(getattr(obj, "color", (0.0, 0.0, 0.0)), page)
        form.addRow("Color:", self.color)
        self.bg = QCheckBox("White background", page)
        self.bg.setChecked(bool(getattr(obj, "background", False)))
        lay = QVBoxLayout(page); lay.addLayout(form); lay.addWidget(self.bg); lay.addStretch(1)
        self.tabs.addTab(page, "Text")

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.text = self.text.text()
        obj.position = (float(self.px.value()), float(self.py.value()))
        obj.font_size = int(self.size.value())
        obj.color = self.color.rgb()
        obj.background = self.bg.isChecked()


class BitmapDialog(ObjectSettingsPanel):
    """Bitmap image — File / Position / Scale (P2.3)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Bitmap"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        page = QWidget(self)
        form = QFormLayout()
        row = QHBoxLayout()
        self.file = QLineEdit(getattr(obj, "file", ""), page)
        btn = QPushButton("Browse…", page)
        btn.clicked.connect(self._browse)
        row.addWidget(self.file, 1); row.addWidget(btn)
        form.addRow("Image file:", row)
        px, py = getattr(obj, "position", (0.05, 0.05))
        self.px = _dspin(px, 0.0, 1.0, 3);
        self.py = _dspin(py, 0.0, 1.0, 3)
        row2 = QHBoxLayout(); row2.addWidget(self.px); row2.addWidget(self.py)
        form.addRow("Position X/Y:", row2)
        self.scale = _dspin(getattr(obj, "scale", 1.0), 0.05, 10.0, 2)
        form.addRow("Scale:", self.scale)
        self.transp = QCheckBox("Transparent", page)
        self.transp.setChecked(bool(getattr(obj, "transparent", False)))
        lay = QVBoxLayout(page); lay.addLayout(form); lay.addWidget(self.transp); lay.addStretch(1)
        self.tabs.addTab(page, "Bitmap")

    def _browse(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.file.setText(path)

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.file = self.file.text()
        obj.position = (float(self.px.value()), float(self.py.value()))
        obj.scale = float(self.scale.value())
        obj.transparent = self.transp.isChecked()

class InformationDialog(ObjectSettingsPanel):
    """Information probe — coordinates + Query (P2.4)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Information"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        self.field_file = field_file
        page = QWidget(self)
        form = QFormLayout()
        px, py, pz = getattr(obj, "position", (0.0, 0.0, 0.0))
        self.px = _dspin(px, -1e9, 1e9, 6);
        self.py = _dspin(py, -1e9, 1e9, 6);
        self.pz = _dspin(pz, -1e9, 1e9, 6)
        row = QHBoxLayout(); row.addWidget(self.px); row.addWidget(self.py); row.addWidget(self.pz)
        form.addRow("X/Y/Z:", row)
        self.marker = QCheckBox("Show marker", page)
        self.marker.setChecked(bool(getattr(obj, "show_marker", True)))
        self.query = QPushButton("Query", page)
        self.query.clicked.connect(self._on_query)
        self.result = QLabel(" ", page)
        self.result.setWordWrap(True);
        self.result.setStyleSheet("color:#333; font-size:11px;")
        lay = QVBoxLayout(page);
        lay.addLayout(form); lay.addWidget(self.marker); lay.addWidget(self.query); lay.addWidget(self.result); lay.addStretch(1)
        self.tabs.addTab(page, "Information")

    def _on_query(self) -> None:
        if self.field_file is None:
            self.result.setText("No field file loaded");
            return
        from ..render.information import probe_values
        pt = (float(self.px.value()), float(self.py.value()),
              float(self.pz.value()))
        vals = probe_values(self.field_file, pt)
        if not vals:
            self.result.setText("No variables at this point");
            return
        lines = [f"({pt[0]:.6g}, {pt[1]:.6g}, {pt[2]:.6g})"]
        for name in sorted(vals):
            v = vals[name]
            if isinstance(v, tuple):
                lines.append(f"{name}: ({', '.join(f'{x:.6g}' for x in v)})")
            else:
                lines.append(f"{name}: {v:.6g}")
        self.result.setText("\n".join(lines))
        parent = self.parent();
        if parent is not None and hasattr(parent, "message_win"):
            for ln in lines:
                parent.message_win.log(ln)

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.position = (float(self.px.value()), float(self.py.value()),
                       float(self.pz.value()))
        obj.show_marker = self.marker.isChecked()

class MirrorCopyDialog(ObjectSettingsPanel):
    """Mirror Copy — Source / Plane / Color (P2.6)."""

    def __init__(self, obj, field_file=None, parent=None, siblings=None):
        super().__init__(getattr(obj, "label", "Mirror Copy"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        page = QWidget(self)
        form = QFormLayout()
        self.source = QComboBox(page)
        for s in siblings or []:
            if getattr(s, "kind", "") == "surface":
                self.source.addItem(getattr(s, "label", ""), s.label)
        idx = self.source.findData(getattr(obj, "source_label", ""))
        if idx >= 0:
            self.source.setCurrentIndex(idx)
        form.addRow("Source surface:", self.source)
        self.plane = QComboBox(page)
        for pl in ("YZ", "ZX", "XY"):
            self.plane.addItem(pl, pl)
        self.plane.setCurrentIndex(max(0, self.plane.findData(
            getattr(obj, "mirror_plane", "YZ"))))
        form.addRow("Mirror plane:", self.plane)
        self.color = _ColorButton(getattr(obj, "color", (0.4, 0.4, 0.4)), page)
        form.addRow("Color:", self.color)
        self.transp = QCheckBox("Transparent", page)
        self.transp.setChecked(bool(getattr(obj, "transparent", False)))
        lay = QVBoxLayout(page); lay.addLayout(form); lay.addWidget(self.transp); lay.addStretch(1)
        self.tabs.addTab(page, "Mirror")

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.source_label = self.source.currentData() or ""
        obj.mirror_plane = self.plane.currentData() or "YZ"
        obj.color = self.color.rgb()
        obj.transparent = self.transp.isChecked()

class TimeSeriesDialog(ObjectSettingsPanel):
    """Time Series — CSV import + table (P2.10)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Time Series"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        page = QWidget(self)
        form = QFormLayout()
        row = QHBoxLayout()
        self.file = QLineEdit(getattr(obj, "file", ""), page)
        btn = QPushButton("Load…", page)
        btn.clicked.connect(self._load)
        row.addWidget(self.file, 1); row.addWidget(btn)
        form.addRow("CSV file:", row)
        lay = QVBoxLayout(page); lay.addLayout(form)
        self.info = QLabel(" ", page)
        self.info.setWordWrap(True);
        self.info.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(self.info); lay.addStretch(1)
        self.tabs.addTab(page, "Time Series")
        self._refresh_info()

    def _load(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Time Series", "", "CSV (*.csv *.tm)")
        if path:
            self.file.setText(path);
            self._refresh_info()

    def _refresh_info(self) -> None:
        path = self.file.text()
        from pathlib import Path
        if not path or not Path(path).exists():
            self.info.setText("No file loaded");
            return
        from ..model.tsmm import parse_time_series
        cyc, tim = parse_time_series(path)
        self.info.setText(f"{len(cyc)} steps, cycle {cyc[0] if cyc else '-'} → "
                         f"{cyc[-1] if cyc else '-'}")

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.file = self.file.text()
        from pathlib import Path
        if obj.file and Path(obj.file).exists():
            from ..model.tsmm import parse_time_series
            obj.cycles, obj.times = parse_time_series(obj.file)


class MaxMinDialog(ObjectSettingsPanel):
    """Max and Min — CSV import + table (P2.10)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Max and Min"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        page = QWidget(self)
        form = QFormLayout()
        row = QHBoxLayout()
        self.file = QLineEdit(getattr(obj, "file", ""), page)
        btn = QPushButton("Load…", page)
        btn.clicked.connect(self._load)
        row.addWidget(self.file, 1); row.addWidget(btn)
        form.addRow("CSV file:", row)
        lay = QVBoxLayout(page); lay.addLayout(form)
        self.info = QLabel(" ", page)
        self.info.setWordWrap(True);
        self.info.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(self.info); lay.addStretch(1)
        self.tabs.addTab(page, "Max and Min")
        self._refresh_info()

    def _load(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Max and Min", "", "CSV (*.csv *.ot)")
        if path:
            self.file.setText(path);
            self._refresh_info()

    def _refresh_info(self) -> None:
        path = self.file.text()
        from pathlib import Path
        if not path or not Path(path).exists():
            self.info.setText("No file loaded");
            return
        from ..model.tsmm import parse_max_min
        vals = parse_max_min(path)
        lines = [f"{n}: {v[0]:.6g} … {v[1]:.6g}" for n, v in
                 sorted(vals.items())[:6]]
        self.info.setText("\n".join(lines) or "No rows");

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.file = self.file.text()
        from pathlib import Path
        if obj.file and Path(obj.file).exists():
            from ..model.tsmm import parse_max_min
            obj.values = parse_max_min(obj.file)

class GraphDialog(ObjectSettingsPanel):
    """Graph — Variable / X mode / Plot (P2.2)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Graph"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        self.field_file = field_file
        page = QWidget(self)
        form = QFormLayout()
        self.var = _var_combo(_scalar_vars(field_file), obj.variable)
        form.addRow("Variable:", self.var)
        self.xmode = QComboBox(page)
        for m in ("Index", "Cycle"):
            self.xmode.addItem(m, m)
        self.xmode.setCurrentIndex(max(0, self.xmode.findData(
            getattr(obj, "x_mode", "Index"))))
        form.addRow("X axis:", self.xmode)
        self.title = QLineEdit(getattr(obj, "title_text", ""), page)
        form.addRow("Title:", self.title)
        self.plot = QPushButton("Plot", page)
        self.plot.clicked.connect(self._on_plot)
        self.info = QLabel(" ", page)
        self.info.setStyleSheet("color:#666; font-size:11px;")
        lay = QVBoxLayout(page)
        lay.addLayout(form); lay.addWidget(self.plot); lay.addWidget(self.info); lay.addStretch(1)
        self.tabs.addTab(page, "Graph")

    def _on_plot(self) -> None:
        self.apply_to(self.obj)
        from ..render.graph import plot_graph
        dlg = plot_graph(self.obj, parent=self, ff0=self.field_file)
        if dlg is None:
            self.info.setText("Graph unavailable (need >=2 cycles or matplotlib)");
        else:
            self.info.setText("Plotted");

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.variable = self.var.currentData() or ""
        obj.x_mode = self.xmode.currentData() or "Index"
        obj.title_text = self.title.text()

class GroupingDialog(ObjectSettingsPanel):
    """Grouping — member visibility (P2.5)."""

    def __init__(self, obj, field_file=None, parent=None, siblings=None):
        super().__init__(getattr(obj, "label", "Grouping"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        self.siblings = siblings or []
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Members (checked objects toggle together):", page))
        self.members = QListWidget(page)
        self.members.setSelectionMode(QAbstractItemView.MultiSelection)
        for s in self.siblings:
            item = QListWidgetItem(getattr(s, "label", ""), self.members)
            if getattr(s, "label", "") in getattr(obj, "member_labels", []):
                item.setSelected(True)
        lay.addWidget(self.members)
        lay.addStretch(1)
        self.tabs.addTab(page, "Grouping")

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.member_labels = [i.text() for i in self.members.selectedItems()]

class CurveDialog(ObjectSettingsPanel):
    """Curve — control points / variable / display (A1)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Curve"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        self.field_file = field_file
        page = QWidget(self)
        lay = QVBoxLayout(page)
        lay.addWidget(QLabel("Control points (x,y,z):", page))
        self.pts = QListWidget(page)
        for p in getattr(obj, "points", []) or []:
            self.pts.addItem(",".join(f"{v:.6g}" for v in p))
        lay.addWidget(self.pts)
        prow = QHBoxLayout()
        badd = QPushButton("Add", page)
        badd.clicked.connect(self._add)
        bdel = QPushButton("Delete", page)
        bdel.clicked.connect(self._del)
        prow.addWidget(badd); prow.addWidget(bdel); prow.addStretch(1)
        lay.addLayout(prow)
        form = QFormLayout()
        self.var = _var_combo(_scalar_vars(field_file), obj.variable)
        form.addRow("Variable:", self.var)
        self.samples = QSpinBox(page); self.samples.setRange(8, 2000)
        self.samples.setValue(int(getattr(obj, "samples", 64)))
        form.addRow("Samples:", self.samples)
        self.color = _ColorButton(getattr(obj, "color", (0.9, 0.2, 0.2)), page)
        form.addRow("Color:", self.color)
        self.thick = QSpinBox(page); self.thick.setRange(1, 10)
        self.thick.setValue(int(getattr(obj, "thickness", 2)))
        form.addRow("Thickness:", self.thick)
        lay.addLayout(form)
        lay.addStretch(1)
        self.tabs.addTab(page, "Curve")

    def _add(self) -> None:
        self.pts.addItem("0,0,0")
        self.pts.setCurrentRow(self.pts.count() - 1)

    def _del(self) -> None:
        row = self.pts.currentRow()
        if row >= 0:
            self.pts.takeItem(row)

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        pts = []
        for i in range(self.pts.count()):
            try:
                parts = [float(x) for x in self.pts.item(i).text().split(",")]
                if len(parts) == 3:
                    pts.append(tuple(parts))
            except ValueError:
                continue
        obj.points = pts
        obj.variable = self.var.currentData() or ""
        obj.samples = int(self.samples.value())
        obj.color = self.color.rgb()
        obj.thickness = int(self.thick.value())

class PeriodicalCopyDialog(ObjectSettingsPanel):
    """Periodical Copy — Source / Axis / Copies (A2)."""

    def __init__(self, obj, field_file=None, parent=None, siblings=None):
        super().__init__(getattr(obj, "label", "Periodical Copy"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        page = QWidget(self)
        form = QFormLayout()
        self.source = QComboBox(page)
        for s in siblings or []:
            if getattr(s, "kind", "") == "surface":
                self.source.addItem(getattr(s, "label", ""), s.label)
        idx = self.source.findData(getattr(obj, "source_label", ""))
        if idx >= 0:
            self.source.setCurrentIndex(idx)
        form.addRow("Source surface:", self.source)
        self.axis = QComboBox(page)
        for a in ("X", "Y", "Z"):
            self.axis.addItem(a, a)
        self.axis.setCurrentIndex(max(0, self.axis.findData(
            getattr(obj, "axis", "Z"))))
        form.addRow("Axis:", self.axis)
        self.copies = QSpinBox(page); self.copies.setRange(2, 360)
        self.copies.setValue(int(getattr(obj, "copies", 6)))
        form.addRow("Copies:", self.copies)
        self.color = _ColorButton(getattr(obj, "color", (0.4, 0.4, 0.4)), page)
        form.addRow("Color:", self.color)
        self.transp = QCheckBox("Transparent", page)
        self.transp.setChecked(bool(getattr(obj, "transparent", False)))
        lay = QVBoxLayout(page); lay.addLayout(form); lay.addWidget(self.transp); lay.addStretch(1)
        self.tabs.addTab(page, "Periodical")

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.source_label = self.source.currentData() or ""
        obj.axis = self.axis.currentData() or "Z"
        obj.copies = int(self.copies.value())
        obj.color = self.color.rgb()
        obj.transparent = self.transp.isChecked()

class MeasureDialog(ObjectSettingsPanel):
    """Measure — Distance / Angle between points (C2)."""

    def __init__(self, obj, field_file=None, parent=None):
        super().__init__(getattr(obj, "label", "Measure"), parent)
        if not _HAS_QT:
            self.obj = obj
            return
        self.obj = obj
        page = QWidget(self)
        form = QFormLayout()
        self.mode = QComboBox(page)
        for m in ("Distance", "Angle"):
            self.mode.addItem(m, m)
        self.mode.setCurrentIndex(max(0, self.mode.findData(
            getattr(obj, "mode", "Distance"))))
        form.addRow("Mode:", self.mode)
        pts = list(getattr(obj, "points", None) or [])
        while len(pts) < 3:
            pts.append((0.0, 0.0, 0.0))
        self.spins = []
        for i in range(3):
            px, py, pz = pts[i]
            sx = _dspin(px, -1e9, 1e9, 6);
            sy = _dspin(py, -1e9, 1e9, 6);
            sz = _dspin(pz, -1e9, 1e9, 6)
            row = QHBoxLayout(); row.addWidget(sx); row.addWidget(sy); row.addWidget(sz)
            form.addRow(f"Point {i + 1} x/y/z:", row)
            self.spins.append((sx, sy, sz))
        self.calc = QPushButton("Calculate", page)
        self.calc.clicked.connect(self._on_calc)
        self.result = QLabel(" ", page)
        self.result.setStyleSheet("font-weight:bold;")
        lay = QVBoxLayout(page); lay.addLayout(form); lay.addWidget(self.calc); lay.addWidget(self.result); lay.addStretch(1)
        self.tabs.addTab(page, "Measure")

    def _on_calc(self) -> None:
        self.apply_to(self.obj)
        from ..render.measure import compute
        self.obj.result = compute(self.obj)
        self.result.setText(self.obj.result)
        parent = self.parent();
        if parent is not None and hasattr(parent, "message_win"):
            parent.message_win.log(self.obj.result)

    def apply_to(self, obj) -> None:
        if not _HAS_QT:
            return
        obj.mode = self.mode.currentData() or "Distance"
        pts = []
        for sx, sy, sz in self.spins:
            pts.append((float(sx.value()), float(sy.value()),
                       float(sz.value())))
        obj.points = pts
