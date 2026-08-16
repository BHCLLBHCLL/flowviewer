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
