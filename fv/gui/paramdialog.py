"""R67: report parameter panel dialog (per-report-kind tunables).

``analysis.report_params`` gives a pure ``Param`` schema per report kind; this
module renders that schema as a ``QDialog`` so users can set the
otherwise-defaulted tunables (cycles window, ``dt``, mode count ``k``, IDW power
``p``, neighbours, reference probe, Welch segment, panels, snapshot cycle, DMD
top, source, ...). The dialog collects raw widget values and hands them to
``analysis.normalize_params``, so the pure coercion/clamping logic lives wholly
in ``analysis`` (headless-testable) and this module only owns the widgets.

R68 adds a named-preset strip (Load/Save/Delete) backed by ``PresetStore``: a
tuned snapshot can be stored under a name and recalled next time, either by
sharing the app-wide store (passed in) or the default per-user JSON store.

PyQt is imported at module scope — this module is only ever imported from the
live GUI, never headless. It is a pure widget layer: it does not run reports.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QWidget,
)

from .analysis import PresetStore, default_preset_path, normalize_params, report_params

_HUGE = 10 ** 9


class ParamDialog(QDialog):
    """Edit the tunable parameters for one Analysis report ``kind``."""

    def __init__(self, kind: str, parent=None, store: PresetStore | None = None):
        super().__init__(parent)
        self._kind = kind
        self._store = store if store is not None else PresetStore(path=default_preset_path())
        self.setWindowTitle("Report Options — " + kind)
        self._fields = []  # (key, Param, widget, getter)
        form = QFormLayout(self)
        for p in report_params(kind):
            widget, getter = self._widget_for(p)
            label = QLabel(p.label)
            if p.help:
                label.setToolTip(p.help)
            form.addRow(label, widget)
            self._fields.append((p.key, p, widget, getter))
        form.addRow(QLabel("Presets"), self._preset_widgets())
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _preset_widgets(self) -> QWidget:
        row = QWidget()
        lay = QHBoxLayout(row)
        self._preset_combo = QComboBox()
        self._preset_combo.setMinimumWidth(180)
        self._refresh_presets()
        lay.addWidget(self._preset_combo, 1)
        load = QPushButton("Load")
        load.clicked.connect(self._load_preset)
        save = QPushButton("Save")
        save.clicked.connect(self._save_preset)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete_preset)
        lay.addWidget(load)
        lay.addWidget(save)
        lay.addWidget(delete)
        return row

    def _refresh_presets(self) -> None:
        self._preset_combo.clear()
        self._preset_combo.addItems(self._store.names(self._kind))

    def _save_preset(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if not ok or not name.strip():
            return
        self._store.save(self._kind, name.strip(), self.result_params())
        self._refresh_presets()
        self._preset_combo.setCurrentText(name.strip())

    def _load_preset(self) -> None:
        name = self._preset_combo.currentText()
        if not name:
            return
        snap = self._store.load(self._kind, name)
        if snap is not None:
            self._apply_params(snap)

    def _delete_preset(self) -> None:
        name = self._preset_combo.currentText()
        if not name:
            return
        if self._store.delete(self._kind, name):
            self._refresh_presets()

    def _apply_params(self, params: dict) -> None:
        for key, p, widget, _getter in self._fields:
            if key in params:
                self._set_value(widget, p, params[key])

    def _set_value(self, widget, p, v) -> None:
        if p.type == "int":
            if isinstance(widget, QSpinBox):
                widget.setValue(int(v))
            else:
                widget.setText("" if v is None else str(int(v)))
        elif p.type == "float":
            if isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(v))
            else:
                widget.setText("" if v is None else str(float(v)))
        elif p.type == "bool":
            widget.setChecked(bool(v))
        elif p.type == "choice":
            if v in p.choices:
                widget.setCurrentIndex(list(p.choices).index(v))
        elif p.type == "tuple":
            widget.setText(", ".join(str(x) for x in v) if v else "")
        else:
            widget.setText("" if v is None else str(v))

    def _widget_for(self, p):
        v = p.default
        if p.type == "int":
            if v is None:
                line = QLineEdit("")
                return line, line.text
            sp = QSpinBox()
            sp.setMinimum(p.min if p.min is not None else 0)
            sp.setMaximum(p.max if p.max is not None else _HUGE)
            sp.setValue(int(v))
            return sp, sp.value
        if p.type == "float":
            if v is None:
                line = QLineEdit("")
                return line, line.text
            sp = QDoubleSpinBox()
            sp.setMinimum(float(p.min) if p.min is not None else -_HUGE)
            sp.setMaximum(float(p.max) if p.max is not None else _HUGE)
            sp.setDecimals(6)
            sp.setValue(float(v))
            return sp, sp.value
        if p.type == "bool":
            cb = QCheckBox()
            cb.setChecked(bool(v))
            return cb, cb.isChecked
        if p.type == "choice":
            cb = QComboBox()
            cb.addItems([str(c) for c in p.choices])
            cb.setCurrentIndex(list(p.choices).index(v) if v in p.choices else 0)
            return cb, cb.currentText
        if p.type == "tuple":
            line = QLineEdit(", ".join(str(x) for x in v) if v else "")
            return line, line.text
        line = QLineEdit("" if v is None else str(v))
        return line, line.text

    def result_params(self) -> dict:
        """Build a normalized, JSON-serializable parameter snapshot."""
        raw = {}
        for key, _p, _w, getter in self._fields:
            raw[key] = getter()
        return normalize_params(self._kind, raw)
