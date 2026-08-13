"""Graph (1D) plotting with matplotlib (scPOST Graph, P2.2).

'plot_graph' extracts a variable along the cycle sequence (or index) and
draws it into a Qt window.  matplotlib is an optional dependency; when
missing the plot falls back to a simple text summary in the message log.
"""

from __future__ import annotations

from typing import Optional

import numpy as np


def collect_series(obj, ff0=None) -> tuple:
    """(x, y, label) for the GraphObject over its cycle files."""
    var = (getattr(obj, "variable", "") or "").strip()
    if not var:
        return [], [], var
    from ..model.dataset import load_file
    files = list(getattr(obj, "files", None) or [])
    if not files and ff0 is not None:
        files = [ff0.path]
    xs = [];
    ys = []
    mode = (getattr(obj, "x_mode", "Index") or "Index")
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


def plot_graph(obj, parent=None, ff0=None) -> Optional[object]:
    """Open a matplotlib window with the series (P2.2).

    Returns the dialog (or None when matplotlib/Qt is unavailable).
    """
    xs, ys, var = collect_series(obj, ff0=ff0)
    if not xs or len(xs) < 2:
        return None
    try:
        import matplotlib
        matplotlib.use("Qt5Agg")
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
        from matplotlib.figure import Figure
        from PyQt5.QtWidgets import QDialog, QVBoxLayout
        dlg = QDialog(parent);
        dlg.setWindowTitle(
            getattr(obj, "title_text", "") or f"Graph: {var}");
        dlg.resize(560, 380)
        fig = Figure(figsize=(5.6, 3.8));
        ax = fig.add_subplot(111)
        ax.plot(xs, ys, "-o", ms=3)
        ax.set_xlabel("Cycle" if str(getattr(obj, "x_mode", ""))
                     .lower() == "cycle" else "Index")
        ax.set_ylabel(var)
        ax.grid(True, ls=":")
        canvas = FigureCanvasQTAgg(fig)
        lay = QVBoxLayout(dlg); lay.addWidget(canvas)
        dlg.show();
        return dlg
    except Exception:
        return None