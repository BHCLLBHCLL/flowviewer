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


# ── P2.2: differential operators on non-hex cells + mismatch errors ──────

def _ff_with(cells, types, verts, field=None, name="F"):
    """Synthetic node-field FieldFile with given connectivity."""
    from fv.model.dataset import FIELD_KIND_SCALAR, FieldFile, VarInfo
    verts = np.asarray(verts, dtype=np.float64)
    conn = np.full((len(cells), max(len(c) for c in cells)), -1,
                   dtype=np.int64)
    for r, c in enumerate(cells):
        conn[r, :len(c)] = c
    ff = FieldFile(path="synthetic", kind="cgns")
    ff.vertices = verts
    ff.n_vertices = len(verts)
    ff.cell_conn = conn
    ff.cell_types = np.asarray(types, dtype=np.int64)
    ff.n_cells = len(cells)
    arr = verts[:, 0] if field is None else field
    ff.variables[name] = VarInfo(name=name, kind=FIELD_KIND_SCALAR,
                                 location="node",
                                 array=np.asarray(arr, dtype=np.float64))
    return ff


def test_delx_hex_grid_linear():
    """FLD-style hex path still differentiates f=x to 1 (P2.2)."""
    from fv.model.varreg import evaluate_expression
    cells = [[0, 1, 2, 3, 4, 5, 6, 7], [4, 5, 6, 7, 8, 9, 10, 11]]
    verts = [(x, y, z) for x in (0.0, 1.0, 2.0)
             for y in (0.0, 1.0) for z in (0.0, 1.0)]
    # vertex order: idx = x*4 + y*2 + z
    cells = [[0, 2, 6, 4, 1, 3, 7, 5], [4, 6, 10, 8, 5, 7, 11, 9]]
    ff = _ff_with(cells, [12, 12], verts)
    out = evaluate_expression("delx(F)", {"F": ff.variables["F"].array},
                              ff.n_vertices, ff=ff)
    assert out.shape == (12,)
    assert abs(out[4] - 1.0) < 1e-9   # interior plane x=1


def test_delx_tet_wedge_pyra_mixed():
    """tet/wedge/pyra cells build correct adjacency (P2.2).

    Two tet + one wedge + one pyra chained along x; interior nodes
    must give df/dx = 1 for the linear field F = x.
    """
    from fv.model.varreg import evaluate_expression
    verts = np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 1.0, 0.0], [0.5, 0.5, 1.0],  # tets
        [2.0, 0.0, 0.0], [1.5, 1.0, 0.0],                                     # tet2
        [2.5, 0.0, 0.0], [2.5, 1.0, 0.0], [2.5, 0.5, 1.0],                    # wedge cap
        [3.5, 0.5, 0.0],                                                      # pyra apex
    ])
    tets = [[0, 1, 2, 3], [1, 4, 5, 3]]
    wedge = [[1, 4, 5, 3, 6, 8]]              # bottom tri (1,4,5), top (3,6,8)
    pyra = [[6, 8, 3, 5, 9]]                  # degenerate-ish quad + apex
    ff = _ff_with(tets + wedge + pyra, [10, 10, 13, 14], verts)
    out = evaluate_expression("delx(F)", {"F": ff.variables["F"].array},
                              ff.n_vertices, ff=ff)
    assert out.shape == (10,)
    assert abs(out[1] - 1.0) < 1e-9   # tet interior node
    assert abs(out[6] - 1.0) < 1e-9   # wedge/pyra interior node


def test_mismatch_explicit_errors():
    """Missing/shifted/unknown connectivity raises explicit errors (P2.2)."""
    from fv.model.varreg import evaluate_expression

    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, 1.0, 0.0), (0.5, 0.5, 1.0)]
    cells = [[0, 1, 2, 3]]
    f = np.array([0.0, 1.0, 0.5, 0.5])

    # no connectivity at all
    ff0 = _ff_with(cells, [10], verts, field=f)
    ff0.cell_conn = None
    with pytest.raises(ValueError, match="connectivity"):
        evaluate_expression("delx(F)", {"F": f}, ff0.n_vertices, ff=ff0)

    # ids out of vertex range (index-base detection fails)
    ff1 = _ff_with([[2, 3, 4, 5]], [10], verts, field=f)
    with pytest.raises(ValueError, match="mismatch"):
        evaluate_expression("delx(F)", {"F": f}, ff1.n_vertices, ff=ff1)

    # unsupported cell type (vtk line = 3)
    ff2 = _ff_with([[0, 1]], [3], verts, field=f)
    with pytest.raises(ValueError, match="unsupported cell type"):
        evaluate_expression("delx(F)", {"F": f}, ff2.n_vertices, ff=ff2)

    # field length != n_vertices
    ff3 = _ff_with(cells, [10], verts, field=f)
    ff3.variables["F"].array = f[:3]
    with pytest.raises(ValueError, match="vertices"):
        evaluate_expression("delx(F)", {"F": f[:3]}, ff3.n_vertices, ff=ff3)
