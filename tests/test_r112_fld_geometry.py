"""R112: FLD geometry fidelity — face index base, region duplicates, areas.

Three defects measured on the real corpus:

1. LS_SurfaceGeometryArray face ids are 1-based in the same file whose
   vertices are 0-based, and only the cell connectivity was normalised.  The
   surface renderer therefore fed ids 1..N into a 0-based vtkPoints: every
   face used the wrong vertices (ex1_100.fld used ids 1..21145 with no 0 and
   one out-of-range reference).

2. ff.faces is region-concatenated: one physical face appears once per BC
   region it belongs to.  ex1_100.fld carries 34978 entries for 5556 distinct
   faces, and the renderer drew all of them, inflating every area by ~6.3x.

3. integrate_cut took each polygon's area from its first three vertices only,
   under-reporting an n-gon by (n-2)/n: a unit quad integrated as 0.5, the
   FPH wall surface came out at 17.9% of truth.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

FLD = r"D:\training\cgns\examples\ex1_100.fld"
FPH = r"D:\training\cgns\examples\tr03_9.fph"

vtk = pytest.importorskip("vtk")


def _polygon(points, scalar=None):
    """One polygon as vtkPolyData, optionally carrying a cell scalar."""
    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    for p in points:
        pts.InsertNextPoint(*p)
    pd.SetPoints(pts)
    ca = vtk.vtkCellArray()
    idl = vtk.vtkIdList()
    for i in range(len(points)):
        idl.InsertNextId(i)
    ca.InsertNextCell(idl)
    pd.SetPolys(ca)
    if scalar is not None:
        arr = vtk.vtkDoubleArray()
        arr.SetName("S")
        arr.SetNumberOfTuples(1)
        arr.SetTuple1(0, float(scalar))
        pd.GetCellData().AddArray(arr)
    return pd


def test_unit_quad_area_is_exactly_one():
    """(n-2)/n under-reporting: a quad used to integrate as 0.5."""
    from fv.render.plane import integrate_cut

    res = integrate_cut(_polygon([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], 1.0), "S")
    assert res["area"] == pytest.approx(1.0, abs=1e-12)
    assert res["sum"] == pytest.approx(1.0, abs=1e-12)


def test_pentagon_area_matches_the_shoelace_formula():
    from fv.render.plane import integrate_cut

    xy = np.array([(0, 0), (2, 0), (2, 1), (1, 1.5), (0, 1)], dtype=float)
    x, y = xy[:, 0], xy[:, 1]
    shoelace = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
    pts = [(float(a), float(b), 0.0) for a, b in xy]
    res = integrate_cut(_polygon(pts), None)
    assert res["area"] == pytest.approx(shoelace, rel=1e-12)


def test_scaled_quad_weights_the_scalar_by_area():
    from fv.render.plane import integrate_cut

    res = integrate_cut(_polygon([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)], 3.0), "S")
    assert res["area"] == pytest.approx(4.0, abs=1e-12)
    assert res["sum"] == pytest.approx(12.0, abs=1e-12)


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_fld_face_ids_are_zero_based_and_in_range():
    from fv.model.dataset import load_file

    ff = load_file(FLD)
    n = len(np.asarray(ff.vertices))
    flat = np.asarray([int(v) for f in ff.faces for v in f], dtype=np.int64)
    assert flat.min() == 0, "1-based ids leaked into the 0-based vertex array"
    assert flat.max() < n, "face references a vertex that does not exist"


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_fld_surface_draws_each_face_once():
    """The region-concatenated list must not be drawn 6.3x over."""
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.render import surface as SU

    ff = load_file(FLD)
    distinct = len({tuple(sorted(int(v) for v in f)) for f in ff.faces})
    assert distinct < len(ff.faces), "fixture no longer has region duplicates"

    obj = SurfaceObject()
    obj.selected_regions = []
    pd = SU.build_surface_polydata(ff, obj)[0]
    assert pd.GetNumberOfPolys() == distinct


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_fld_surface_area_matches_vtk():
    from fv.model.dataset import load_file
    from fv.model.objects import SurfaceObject
    from fv.render import surface as SU
    from fv.render.plane import integrate_cut

    ff = load_file(FLD)
    obj = SurfaceObject()
    obj.selected_regions = []
    pd = SU.build_surface_polydata(ff, obj)[0]

    tri = vtk.vtkTriangleFilter()
    tri.SetInputData(pd)
    tri.Update()
    mass = vtk.vtkMassProperties()
    mass.SetInputConnection(tri.GetOutputPort())
    mass.Update()
    truth = mass.GetSurfaceArea()

    got = integrate_cut(pd, None)["area"]
    assert got == pytest.approx(truth, rel=1e-6)
    assert got == pytest.approx(0.00666, rel=0.02)
