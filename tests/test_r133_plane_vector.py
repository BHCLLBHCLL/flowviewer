"""R133 - the Plane Vector tab must draw arrows (or say why it cannot).

Measured on laptop_thermal_steady_scaled_v3_block_10.fph: the loader exposes
the components as VELX, VELY, VELZ, each individually with kind == "vector".
The Vector tab listed vectors by kind, so it offered the components; choosing
one made attach_vector look for VELXX/VELXY/VELXZ, find nothing and return
None -- the plane was painted by its contour and no glyphs appeared, which is
the reported difference from scPOST.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fv.gui.object_dialogs import _vector_vars  # noqa: E402
from fv.render.plane import attach_vector  # noqa: E402

vtk = pytest.importorskip("vtk")


class _Var:
    def __init__(self, kind="vector"):
        self.kind = kind
        self.location = "cell"
        self.array = np.zeros(3)


class _FF:
    def __init__(self, names, kind="vector"):
        self.variables = {n: _Var(kind) for n in names}
        self.n_cells = 3

    def variable_array(self, name):
        v = self.variables.get(name)
        return None if v is None else v.array


def test_r133_vector_list_offers_the_base_name_not_the_components():
    ff = _FF(["VELX", "VELY", "VELZ", "PRES"])
    assert _vector_vars(ff) == ["VEL"]


def test_r133_incomplete_component_set_is_not_offered():
    assert _vector_vars(_FF(["VELX", "VELY"])) == []


def test_r133_attach_vector_accepts_a_component_name():
    ff = _FF(["VELX", "VELY", "VELZ"])
    ff.variables["VELX"].array = np.array([1.0, 2.0, 3.0])
    ff.variables["VELY"].array = np.array([4.0, 5.0, 6.0])
    ff.variables["VELZ"].array = np.array([7.0, 8.0, 9.0])
    ug = vtk.vtkUnstructuredGrid()
    arr = attach_vector(ug, ff, "VELX", True)
    assert arr is not None
    assert arr.GetName() == "VEL"
    got = vtk.util.numpy_support.vtk_to_numpy(ug.GetCellData().GetVectors())
    assert got.shape == (3, 3)
    # row 1 = (VELX[1], VELY[1], VELZ[1]) = (2, 5, 8)
    assert got[1].tolist() == [2.0, 5.0, 8.0]


def test_r133_missing_component_reports_instead_of_drawing_nothing(caplog):
    ff = _FF(["VELX", "VELY", "VELZ"])
    ff.variables.pop("VELZ")
    ug = vtk.vtkUnstructuredGrid()
    with caplog.at_level("WARNING"):
        assert attach_vector(ug, ff, "VEL", True) is None
    # the warning names the vector and the missing suffix, not the full name
    assert any("vector 'VEL' has no Z component" in r.getMessage()
               for r in caplog.records)
    vecs = ug.GetCellData().GetVectors()
    assert vecs is None or vecs.GetNumberOfTuples() == 0
