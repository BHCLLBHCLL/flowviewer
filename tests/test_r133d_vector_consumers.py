"""R133d - every vector consumer folds component names and reports gaps.

R133/R133b/R133c fixed the Plane, Surface and volume/isosurface paths.  The
remaining consumers still looked up "{name}X/Y/Z" literally, and three of them
papered over a missing component:

* fv/render/streamline.py and fv/render/oilflow.py substituted np.zeros() for a
  missing component and then integrated that fabricated field;
* fv/render/pathline.py returned in silence, so the trace kept whatever array
  the previous cycle had left attached;
* fv/render/point.py reported 0.0 for missing components (_probe_fld) and read
  the cut array by the raw name (_probe_vtk);
* fv/render/cylinder.py never attached a vector at all, so the Cylinder and
  Circle Vector tabs could not draw anything on any file.

Every expectation below is analytic: the folded name, the exact node value, the
tuple count, and the warning that names the missing component.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fv.render import cylinder as cylinder_mod  # noqa: E402
from fv.render import oilflow as oilflow_mod  # noqa: E402
from fv.render import pathline as pathline_mod  # noqa: E402
from fv.render import point as point_mod  # noqa: E402
from fv.render import streamline as streamline_mod  # noqa: E402
from samples import sample  # noqa: E402

vtk = pytest.importorskip("vtk")

SAMPLE = sample("tr03_9.fph")


class _Var:
    def __init__(self, arr):
        self.kind = "vector"
        self.location = "cell"
        self.array = np.asarray(arr, dtype=np.float64)


class _FF:
    """Minimal FieldFile stand-in with vertices + component arrays."""

    def __init__(self, comps, vertices=None, kind="fld"):
        self.variables = {n: _Var(a) for n, a in comps.items()}
        n = len(next(iter(comps.values())))
        self.vertices = (np.zeros((n, 3)) if vertices is None
                         else np.asarray(vertices, dtype=np.float64))
        self.n_vertices = len(self.vertices)
        self.n_cells = n
        self.kind = kind

    def variable_array(self, name):
        v = self.variables.get(name)
        return None if v is None else v.array


def _hex_grid(nx=3, ny=3, nz=3):
    """A structured nx*ny*nz hex block as a vtkUnstructuredGrid."""
    ug = vtk.vtkUnstructuredGrid()
    pts = vtk.vtkPoints()
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                pts.InsertNextPoint(float(i), float(j), float(k))
    ug.SetPoints(pts)

    def vid(i, j, k):
        return i + (nx + 1) * (j + (ny + 1) * k)

    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                ids = vtk.vtkIdList()
                for v in (vid(i, j, k), vid(i + 1, j, k),
                          vid(i + 1, j + 1, k), vid(i, j + 1, k),
                          vid(i, j, k + 1), vid(i + 1, j, k + 1),
                          vid(i + 1, j + 1, k + 1), vid(i, j + 1, k + 1)):
                    ids.InsertNextId(v)
                ug.InsertNextCell(vtk.VTK_HEXAHEDRON, ids)
    return ug


def _complete(n=27, value=1.0):
    return {"VELX": np.full(n, value), "VELY": np.zeros(n),
            "VELZ": np.zeros(n)}


def _warnings(caplog):
    return [r.getMessage() for r in caplog.records]


# --- the two numeric FLD tracers must not fabricate a component -------------

def test_r133d_streamline_refuses_an_incomplete_field(caplog):
    from fv.model.objects import StreamlineObject
    ff = _FF({"VELX": np.ones(3), "VELY": np.ones(3)})       # no VELZ
    obj = StreamlineObject(index=1, vector_var="VEL")
    with caplog.at_level("WARNING"):
        assert streamline_mod._numeric_trace_fld(ff, obj) is None
    assert any("streamline vector 'VEL' has no Z component" in m
               for m in _warnings(caplog)), _warnings(caplog)


def test_r133d_oilflow_refuses_an_incomplete_field(caplog):
    from fv.model.objects import PlaneObject
    ff = _FF({"VELX": np.ones(3), "VELY": np.ones(3)})
    obj = PlaneObject(index=1, oilflow_var="VEL")
    with caplog.at_level("WARNING"):
        assert oilflow_mod._numeric_trace_fld(ff, obj) is None
    assert any("oil-flow vector 'VEL' has no Z component" in m
               for m in _warnings(caplog)), _warnings(caplog)


# --- pathline: fold the name, and stop instead of reusing the old field -----

def test_r133d_pathline_attach_returns_false_and_reports(caplog):
    ug = _hex_grid()
    ff = _FF({"VELX": np.ones(27), "VELY": np.ones(27)})
    with caplog.at_level("WARNING"):
        assert pathline_mod._attach_vectors(ug, ff, "VEL", True) is False
    assert any("pathline vector 'VEL' has no Z component" in m
               for m in _warnings(caplog)), _warnings(caplog)
    assert ug.GetCellData().GetVectors() is None


def test_r133d_pathline_attach_accepts_a_component_name():
    ug = _hex_grid()
    ff = _FF(_complete())
    assert pathline_mod._attach_vectors(ug, ff, "VELX", True) is True
    vecs = ug.GetCellData().GetVectors()
    assert vecs is not None and vecs.GetName() == "VEL"
    assert vecs.GetNumberOfTuples() == 27


# --- point probe ------------------------------------------------------------

def test_r133d_probe_folds_the_component_name_and_reads_the_node():
    verts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    ff = _FF({"VELX": [1.0, 2.0, 3.0], "VELY": [4.0, 5.0, 6.0],
              "VELZ": [7.0, 8.0, 9.0]}, vertices=verts)
    out = point_mod._probe_fld(ff, (1.0, 0.0, 0.0), "", "VELX", False, True)
    assert out["vector"] == ("VEL", (2.0, 5.0, 8.0))     # nearest node = 1


def test_r133d_probe_reports_a_missing_component(caplog):
    verts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    ff = _FF({"VELX": [1.0, 2.0], "VELY": [3.0, 4.0]}, vertices=verts)
    with caplog.at_level("WARNING"):
        out = point_mod._probe_fld(ff, (0.0, 0.0, 0.0), "", "VEL", False, True)
    assert "vector" not in out, "a fabricated 0.0 vector used to be reported"
    assert any("probe vector 'VEL' has no Z component" in m
               for m in _warnings(caplog)), _warnings(caplog)


# --- cylinder / circle: the field has to be attached at all -----------------

def test_r133d_cylinder_prepare_attaches_point_vectors():
    from fv.model.objects import CylinderObject
    ug = _hex_grid()
    ff = _FF(_complete())
    obj = CylinderObject(index=1, show_vector=True, vector_var="VELX")
    grid, name = cylinder_mod._prepare_vector(ff, obj, ug, True)
    assert name == "VEL"
    vecs = grid.GetPointData().GetVectors()
    assert vecs is not None and vecs.GetName() == "VEL"
    assert vecs.GetNumberOfTuples() == grid.GetNumberOfPoints() == 64


def test_r133d_cylinder_prepare_reports_and_attaches_nothing(caplog):
    from fv.model.objects import CylinderObject
    ug = _hex_grid()
    ff = _FF({"VELX": np.ones(27), "VELY": np.ones(27)})
    obj = CylinderObject(index=1, show_vector=True, vector_var="VEL")
    with caplog.at_level("WARNING"):
        grid, name = cylinder_mod._prepare_vector(ff, obj, ug, True)
    assert name == "" and grid is ug
    assert ug.GetCellData().GetVectors() is None
    assert any("vector 'VEL' has no Z component" in m
               for m in _warnings(caplog)), _warnings(caplog)


def test_r133d_surface_actor_survives_objects_without_the_plane_tab():
    """SurfaceObject carries vector_var only (no vector_type / arrow knobs).

    R133c made surface.vector_actor build its glyph source through the plane's
    vector_glyph_source(), which read obj.vector_type directly -- that raised
    AttributeError for every Surface, Cylinder and Circle object.
    """
    from fv.model.objects import SurfaceObject
    from fv.render.surface import vector_actor as surface_vector_actor

    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    for p in ((0, 0, 0), (1, 0, 0), (0, 1, 0)):
        pts.InsertNextPoint(*p)
    pd.SetPoints(pts)
    polys = vtk.vtkCellArray()
    polys.InsertNextCell(3)
    for i in range(3):
        polys.InsertCellPoint(i)
    pd.SetPolys(polys)
    from vtk.util import numpy_support as _vns
    arr = _vns.numpy_to_vtk(
        np.ascontiguousarray(np.array([[1.0, 2.0, 3.0]])), deep=True)
    arr.SetName("VEL")
    pd.GetCellData().SetVectors(arr)

    obj = SurfaceObject(index=1, show_vector=True, vector_var="VELX")
    actor = surface_vector_actor(pd, obj, True)
    assert actor is not None
    prod = actor.GetMapper().GetInputConnection(0, 0).GetProducer()
    prod.Update()
    assert prod.GetOutputDataObject(0).GetNumberOfPoints() > 0


# --- one real file, end to end ---------------------------------------------

@pytest.mark.skipif(SAMPLE is None, reason="tr03_9.fph sample not present")
def test_r133d_real_file_cylinder_draws_arrows():
    """The Cylinder Vector tab used to draw nothing on every file."""
    from fv.model.dataset import load_file
    from fv.model.objects import CylinderObject
    from fv.render.cylinder import build_cylinder_actors

    ff = load_file(str(SAMPLE))
    names = set(ff.variables)
    bases = sorted({n[:-1] for n in names
                    if n.endswith("X") and all(n[:-1] + s in names
                                               for s in "XYZ")})
    assert bases, "sample carries no complete vector field"
    v = np.asarray(ff.vertices, dtype=np.float64)
    centre = tuple(float(x) for x in 0.5 * (v.min(axis=0) + v.max(axis=0)))
    span = float((v.max(axis=0) - v.min(axis=0)).max())
    obj = CylinderObject(index=1, show_vector=True, vector_var=bases[0] + "X",
                         show_contour=False, show_mesh=False,
                         center=centre, radius=0.25 * span, height=span)
    out = build_cylinder_actors(ff, obj)
    assert "vector" in out, "cylinder vector actor missing"
    prod = out["vector"].GetMapper().GetInputConnection(0, 0).GetProducer()
    prod.Update()
    glyph = prod.GetOutputDataObject(0)
    assert glyph.GetNumberOfPoints() > 0
    assert all(np.isfinite(b) for b in glyph.GetBounds())
