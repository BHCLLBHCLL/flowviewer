"""Graph (1D) plotting with matplotlib (scPOST Graph, P2.2).

'plot_graph' extracts a variable along the cycle sequence (or index) and
draws it into a Qt window.  matplotlib is an optional dependency; when
missing the plot falls back to a simple text summary in the message log.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def collect_series(obj, ff0=None, curves=None) -> tuple:
    """(x, y, label) for the GraphObject over its cycle files (single)."""
    return _collect_var(obj, getattr(obj, "variable", "") or "", ff0, curves)


def collect_multi_series(obj, ff0=None, curves=None) -> list:
    """R1.5: ``[(xs, ys, label), …]`` for every requested variable.

    Falls back to ``variable`` when ``variables`` is empty, so existing
    single-series graphs keep working unchanged.
    """
    vars_ = list(getattr(obj, "variables", None) or [])
    if not vars_ and getattr(obj, "variable", ""):
        vars_ = [obj.variable]
    out = []
    for var in vars_:
        xs, ys, label = _collect_var(obj, var, ff0, curves)
        if xs:
            out.append((xs, ys, label or var))
    return out


def _collect_var(obj, var, ff0, curves) -> tuple:
    """(x, y, label) for one variable name (R1.5)."""
    var = (var or "").strip()
    mode = (getattr(obj, "x_mode", "Index") or "Index")
    # Curve mode: sample along a Curve object (arc-length X) (6)
    if mode.lower() == "curve":
        for c in curves or []:
            if getattr(c, "kind", "") == "curve" and getattr(c, "label", "") == getattr(obj, "curve_label", ""):
                from .curve import sample_along_curve
                arc, vals, v = sample_along_curve(ff0, c)
                return list(arc), list(vals), v
        return [], [], var
    if not var:
        return [], [], var
    from ..model.dataset import load_file
    files = list(getattr(obj, "files", None) or [])
    if not files and ff0 is not None:
        files = [ff0.path]
    xs = []
    ys = []
    for k, path in enumerate(files):
        try:
            ff = load_file(path)
        except Exception:
            continue
        a = ff.variable_array(var)
        if a is None:
            continue
        a = np.asarray(a, dtype=np.float64)
        if a.ndim == 2:
            a = np.linalg.norm(a, axis=1)
        if a.size == 0:
            continue
        if mode.lower() == "cycle":
            xs.append(ff.cycle if ff.cycle is not None else k)
        else:
            xs.append(k)
        ys.append(float(np.nanmean(a)))
    return xs, ys, var


def _build_figure_axes(obj, ff0):
    """Shared matplotlib figure/axes setup for plot & save (R1.5)."""
    series = collect_multi_series(obj, ff0=ff0)
    if not series:
        return None, None
    from matplotlib.figure import Figure
    fig = Figure(figsize=(5.6, 3.8))
    ax = fig.add_subplot(111)
    for xs, ys, label in series:
        ax.plot(xs, ys, "-o", ms=3, label=label)
    ax.set_xlabel("Cycle" if str(getattr(obj, "x_mode", ""))
                  .lower() == "cycle" else "Index")
    ax.grid(True, ls=":")
    if len(series) > 1 and getattr(obj, "show_legend", True):
        ax.legend()
    if getattr(obj, "log_scale", False):
        ax.set_yscale("log")
    return fig, ax


def plot_graph(obj, parent=None, ff0=None) -> Optional[object]:
    """Open a matplotlib window with the series (R1.5 multi-series).

    Returns the dialog (or None when matplotlib/Qt is unavailable).
    """
    try:
        import matplotlib
        matplotlib.use("Qt5Agg")
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        from PyQt5.QtWidgets import QDialog, QVBoxLayout
        fig, _ax = _build_figure_axes(obj, ff0)
        if fig is None:
            return None
        dlg = QDialog(parent)
        dlg.setWindowTitle(getattr(obj, "title_text", "") or "Graph")
        dlg.resize(560, 380)
        canvas = FigureCanvasQTAgg(fig)
        lay = QVBoxLayout(dlg)
        lay.addWidget(canvas)
        dlg.show()
        return dlg
    except Exception:
        return None


def save_graph(obj, path: str, ff0=None) -> bool:
    """R1.5: render the graph to a PNG/PDF file via matplotlib (Agg)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        fig, _ax = _build_figure_axes(obj, ff0)
        if fig is None:
            return False
        fig.savefig(path)
        return True
    except Exception:
        return False
