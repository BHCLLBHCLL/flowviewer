"""Variable Registration engine tests (P1.1)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_register_arithmetic():
    """+ - * / ^ ( ) unary minus over real variables (P1.1)."""
    from fv.model.dataset import load_file
    from fv.model.varreg import register_variable
    ff = load_file(FPH)
    base = ff.variables["PRES"].array
    vi = register_variable(ff, "DP", "PRES * 2.0 + 1.0")
    np.testing.assert_allclose(vi.array, base * 2.0 + 1.0, rtol=1e-6)
    assert vi.kind == "scalar" and vi.location == "cell"
    vi2 = register_variable(ff, "SQ", "(PRES - 1.0) ^ 2")
    np.testing.assert_allclose(vi2.array, (base - 1.0) ** 2, rtol=1e-6)
    vi3 = register_variable(ff, "NEG", "-PRES")
    np.testing.assert_allclose(vi3.array, -base, rtol=1e-6)

@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_register_mag_and_logic():
    """mag(VEC), ifgt/ifeq and & / @ behave element-wise (P1.1)."""
    from fv.model.dataset import load_file
    from fv.model.varreg import register_variable
    ff = load_file(FPH)
    vx = ff.variables["VELX"].array
    vy = ff.variables["VELY"].array
    vz = ff.variables["VELZ"].array
    vi = register_variable(ff, "SPEED", "mag(VEL)")
    np.testing.assert_allclose(vi.array, np.sqrt(vx * vx + vy * vy + vz * vz),
                              rtol=1e-5)
    hi = register_variable(ff, "HIP", "ifgt(PRES, 0.5)")
    assert set(np.unique(hi.array)).issubset({0.0, 1.0})
    logic = register_variable(ff, "LX", "ifgt(PRES,0.0) & ifeq(PRES,PRES)")
    assert set(np.unique(logic.array)).issubset({0.0, 1.0})
    orl = register_variable(ff, "ORL", "ifgt(PRES,1e9) @ ifeq(PRES,PRES)")
    assert set(np.unique(orl.array)) == {1.0}

@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_register_rejects_bad():
    """Invalid names / expressions are rejected safely (P1.1)."""
    from fv.model.dataset import load_file
    from fv.model.varreg import register_variable
    ff = load_file(FPH)
    with pytest.raises(ValueError):
        register_variable(ff, "PRES", "PRES + 1")  # duplicate name
    with pytest.raises(ValueError):
        register_variable(ff, "HACK", "__import__('os')")
    with pytest.raises(ValueError):
        register_variable(ff, "BAD1", "PRES +")
    with pytest.raises(ValueError):
        register_variable(ff, "BAD2", "NOSUCHVAR * 2")
    assert "HACK" not in ff.variables

@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_registered_var_visible_in_dialogs():
    """Registered variables appear in the object dialog combos (P1.1)."""
    from fv.gui.object_dialogs import _scalar_vars
    from fv.model.dataset import load_file
    from fv.model.varreg import register_variable
    ff = load_file(FPH)
    assert "DP" not in _scalar_vars(ff)
    register_variable(ff, "DP", "PRES * 2.0")
    assert "DP" in _scalar_vars(ff)
@pytest.fixture(scope="module")
def qapp():
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt5 unavailable")
    return QApplication.instance() or QApplication([])


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_variable_registration_dialog(qapp):
    """Dialog previews expressions and applies registrations (P1.1)."""
    from fv.gui.dialogs import VariableRegistrationDialog
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    d = VariableRegistrationDialog(ff)
    d.expr.setText("PRES + 1.0")
    d._update_preview()
    assert "OK" in d.preview.text()
    d.result_name.setText("PP1")
    d._on_apply()
    assert "PP1" in ff.variables
    d.expr.setText("PRES +")
    d._update_preview()
    assert "Error" in d.preview.text()
