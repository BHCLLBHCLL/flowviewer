# -*- coding: utf-8 -*-
"""Compare operator tests (fv.model.compare, P3)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

FPH = r"D:\training\cgns\examples\tr03_9.fph"

try:
    from PyQt5.QtWidgets import QApplication
    _HAS_QT = True
except Exception:  # pragma: no cover
    _HAS_QT = False


@pytest.fixture(scope="module")
def qapp():
    if not _HAS_QT:
        pytest.skip("PyQt5 unavailable")
    app = QApplication.instance() or QApplication([])
    return app



@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_compare_dialog_headless(qapp):
    """CompareDialog builds headless with labelled panes (G2)."""
    from fv.gui.dialogs import CompareDialog
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    d = CompareDialog(ff, ff, enable_3d=False)
    assert "Compare" in d.windowTitle()


@pytest.mark.skipif(not Path(FPH).exists(), reason='sample not present')
def test_compare_dialog_panes(qapp):
    '''CompareDialog builds headless with labelled panes (G2).'''
    from fv.gui.dialogs import CompareDialog
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    d = CompareDialog(ff, ff, enable_3d=False)
    assert d.layout().count() >= 1


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r16_compare_same_file_zero_diff():
    """R1.6: comparing a file with itself yields a zero difference field."""
    from fv.model.dataset import load_file
    from fv.model.compare import (common_variables, difference_field,
                                  compare_stats, compare_summary)
    ff = load_file(FPH)
    common = common_variables(ff, ff)
    assert "PRES" in common
    res = difference_field(ff, ff, "PRES")
    assert res is not None
    assert res["min"] == 0.0 and res["max"] == 0.0
    assert res["mean"] == 0.0 and res["rms"] == 0.0
    assert res["diff"].shape == ff.variable_array("PRES").shape
    st = compare_stats(ff, ff, "PRES")
    assert st["var"] == "PRES" and st["min"] == 0.0
    summary = compare_summary(ff, ff)
    assert "PRES" in summary and "TURK" in summary


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r16_compare_constant_offset():
    """R1.6: a constant offset gives uniform |A−B| equal to the offset."""
    import numpy as np
    from dataclasses import replace
    from fv.model.dataset import load_file, VarInfo
    from fv.model.compare import difference_field, diff_field_file
    a = load_file(FPH)
    b = replace(a)
    b.variables = dict(a.variables)
    b.variables["PRES"] = VarInfo(name="PRES", kind="scalar", location="cell",
                                  array=np.asarray(a.variable_array("PRES")) + 2.5)
    res = difference_field(a, b, "PRES")
    assert res["min"] == pytest.approx(2.5)
    assert res["max"] == pytest.approx(2.5)
    assert res["mean"] == pytest.approx(2.5)
    diff_ff = diff_field_file(a, "PRES", res["diff"], res["location"])
    arr = diff_ff.variable_array("PRES")
    assert arr is not None and len(arr) == len(res["diff"])


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_compare_signed_relative_and_idw():
    """Signed / relative modes and IDW mapping (depth beyond |A−B|)."""
    import numpy as np
    from dataclasses import replace
    from fv.model.dataset import load_file, VarInfo
    from fv.model.compare import difference_field
    a = load_file(FPH)
    b = replace(a)
    b.variables = dict(a.variables)
    src = np.asarray(a.variable_array("PRES"))
    b.variables["PRES"] = VarInfo(name="PRES", kind="scalar", location="cell",
                                  array=src + 4.0)
    signed = difference_field(a, b, "PRES", mode="signed")
    assert signed["min"] == pytest.approx(-4.0)
    assert signed["max"] == pytest.approx(-4.0)
    rel = difference_field(a, b, "PRES", mode="relative")
    # (A - (A+4)) / (|A|+eps) is negative
    assert rel["max"] < 0.0
    absr = difference_field(a, b, "PRES", mode="abs")
    assert absr["mean"] == pytest.approx(4.0)
    # IDW on identical mesh equals nearest (same shape short-circuits mapping)
    idw = difference_field(a, b, "PRES", mapping="idw")
    assert idw["mean"] == pytest.approx(4.0)


def test_compare_idw_midpoint():
    """IDW of two samples at the midpoint is the arithmetic mean."""
    import numpy as np
    from fv.model.compare import _map_idw
    src_pts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    src_vals = np.array([0.0, 10.0])
    dst = np.array([[0.5, 0.0, 0.0]])
    out = _map_idw(src_vals, src_pts, dst)
    assert out[0] == pytest.approx(5.0)
