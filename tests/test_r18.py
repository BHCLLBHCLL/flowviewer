"""R18: beyond-scPOST variable registration upgrade tests.

- register_derived_function: trusted user callable -> scalar/vector var.
- auto_scalarize: magnitude + component scalars for vector variables.
"""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"


def _ff(n, variables=None, kind="fld"):
    from fv.model.dataset import FIELD_KIND_SCALAR, FieldFile, VarInfo
    ff = FieldFile(path="synthetic", kind=kind)
    ff.vertices = np.zeros((n, 3), dtype=np.float64)
    ff.n_vertices = n
    ff.n_cells = n
    ff.variables["PRES"] = VarInfo(name="PRES", kind=FIELD_KIND_SCALAR,
                                   location="node",
                                   array=np.arange(n, dtype=np.float64))
    for name, vi in (variables or {}).items():
        ff.variables[name] = vi
    return ff


def test_register_derived_function_scalar():
    """User callable returning a scalar array (R18)."""
    from fv.model.varreg import register_derived_function
    ff = _ff(5)
    vi = register_derived_function(ff, "DP", lambda PRES: PRES * 2.0 + 1.0)
    np.testing.assert_allclose(vi.array, ff.variables["PRES"].array * 2.0 + 1.0)
    assert vi.kind == "scalar"
    assert ff.variables["DP"].array is vi.array


def test_register_derived_function_vector():
    """User callable returning an (n,3) vector (R18)."""
    from fv.model.dataset import FIELD_KIND_SCALAR, VarInfo
    from fv.model.varreg import register_derived_function
    n = 4
    ff = _ff(n)
    for k, c in enumerate("XYZ"):
        arr = np.linspace(1, n, n) ** (k + 1)
        ff.variables[c] = VarInfo(name=c, kind=FIELD_KIND_SCALAR,
                                  location="node", array=arr)
    def combiner(X, Y, Z):
        return np.column_stack([X, Y, Z])
    vi = register_derived_function(ff, "CV", combiner)
    assert vi.kind == "vector"
    assert vi.array.shape == (n, 3)
    np.testing.assert_allclose(vi.array[:, 0], ff.variables["X"].array)


def test_register_derived_function_rejects():
    """Bad name / duplicate / wrong shape are rejected (R18)."""
    from fv.model.varreg import register_derived_function
    ff = _ff(5)
    with pytest.raises(ValueError):
        register_derived_function(ff, "PRES", lambda PRES: PRES)   # duplicate
    with pytest.raises(ValueError):
        register_derived_function(ff, "bad name", lambda PRES: PRES)  # invalid
    with pytest.raises(ValueError):
        register_derived_function(ff, "SHORT", lambda PRES: PRES[:3])  # shape
    with pytest.raises(ValueError):
        register_derived_function(ff, "TOOBIG", lambda PRES: np.zeros((5, 5)))
    assert "SHORT" not in ff.variables and "TOOBIG" not in ff.variables


def test_auto_scalarize_from_vector_var():
    """Vector kind VarInfo -> _mag + _X/_Y/_Z scalars (R18)."""
    from fv.model.dataset import FIELD_KIND_VECTOR, VarInfo
    from fv.model.varreg import auto_scalarize
    n = 6
    vec = np.column_stack([np.ones(n), np.full(n, 2.0), np.full(n, 2.0)])
    ff = _ff(n, {"VEL": VarInfo(name="VEL", kind=FIELD_KIND_VECTOR,
                                location="node", array=vec)})
    new = auto_scalarize(ff)
    names = {v.name for v in new}
    assert names == {"VEL_mag", "VEL_X", "VEL_Y", "VEL_Z"}
    np.testing.assert_allclose(ff.variables["VEL_mag"].array, np.full(n, 3.0))
    np.testing.assert_allclose(ff.variables["VEL_X"].array, np.ones(n))
    assert ff.variables["VEL_mag"].location == "node"


def test_auto_scalarize_from_triplets():
    """X/Y/Z component triplets are detected as a vector base (R18)."""
    from fv.model.dataset import FIELD_KIND_VECTOR, VarInfo
    from fv.model.varreg import auto_scalarize
    n = 5
    comps = {}
    for k, c in enumerate("XYZ"):
        comps["VEL" + c] = VarInfo(name="VEL" + c, kind=FIELD_KIND_VECTOR,
                                   location="node",
                                   array=np.full(n, float(k + 1)))
    ff = _ff(n, comps)
    new = auto_scalarize(ff)
    names = {v.name for v in new}
    assert "VEL_mag" in names and "VEL_X" in names and "VEL_Y" in names
    np.testing.assert_allclose(
        ff.variables["VEL_mag"].array, np.full(n, np.sqrt(1 + 4 + 9)))


def test_auto_scalarize_idempotent_and_filtered():
    """Second call adds nothing; vector_names filter limits bases (R18)."""
    from fv.model.dataset import FIELD_KIND_VECTOR, VarInfo
    from fv.model.varreg import auto_scalarize
    n = 4
    vec = np.ones((n, 3))
    ff = _ff(n, {
        "V1": VarInfo(name="V1", kind=FIELD_KIND_VECTOR, location="node",
                      array=vec),
        "V2": VarInfo(name="V2", kind=FIELD_KIND_VECTOR, location="node",
                      array=vec),
    })
    first = auto_scalarize(ff)
    assert len(first) == 8
    second = auto_scalarize(ff)
    assert second == []  # idempotent
    # filtered to one base
    ff2 = _ff(n, {
        "V1": VarInfo(name="V1", kind=FIELD_KIND_VECTOR, location="node",
                      array=vec),
        "V2": VarInfo(name="V2", kind=FIELD_KIND_VECTOR, location="node",
                      array=vec),
    })
    got = auto_scalarize(ff2, ["V2"])
    names = {v.name for v in got}
    assert all(nm.startswith("V2") for nm in names)
    assert "V1_mag" not in ff2.variables


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_r18_api_wrappers_on_sample():
    """fv.api registers a derived function and scalarizes VEL on FPH (R18)."""
    from fv import api
    from fv.model.dataset import load_file
    ff = load_file(FPH)
    scalar = api.register_derived_function(
        ff, "DP2", lambda PRES: PRES * 2.0)
    assert scalar.kind == "scalar"
    before = set(ff.variables)
    added = api.auto_scalarize(ff, vector_names=["VEL"])
    assert "VEL_mag" in ff.variables
    assert "VEL_X" in ff.variables
    # registered scalars are reusable in the expression engine
    from fv.model.varreg import register_variable
    vi = register_variable(ff, "SPEED2", "VEL_mag + DP2")
    assert vi.array.shape == (ff.n_cells,)
    assert added  # some new variables were created
    assert before < set(ff.variables)
