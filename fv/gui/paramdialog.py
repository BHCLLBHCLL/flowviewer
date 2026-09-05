"""R67: report parameter panel dialog (per-report-kind tunables).

``analysis.report_params`` gives a pure ``Param`` schema per report kind; this
module renders that schema as a ``QDialog`` so users can set the
otherwise-defaulted tunables (cycles window, ``dt``, mode count ``k``, IDW power
``p``, neighbours, reference probe, Welch segment, panels, snapshot cycle, DMD
top, source, ...). The dialog collects raw widget values and hands them to
``analysis.normalize_params``, so the pure coercion/clamping logic lives wholly
in ``analysis`` (headless-testable) and this module only owns the widgets.

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
    QLabel,
    QLineEdit,
    QSpinBox,
)

from .analysis import normalize_params, report_params

_HUGE = 10 ** 9


class ParamDialog(QDialog):
    """Edit the tunable parameters for one Analysis report ``kind``."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind
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
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

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
