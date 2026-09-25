"""R133c - the Vector tab's arrows must appear, and its controls must act.

Measured on the real sample
'D:/training/cradle/laptop/laptop_thermal_steady_scaled_v3_block/
laptop_thermal_steady_scaled_v3_block_50.fph' (this machine, 2026-09-13):

* the loader exposes VELX/VELY/VELZ with kind == 'vector' and no VEL, so the
  tab offers 'VEL' (R133);
* 14112 of 1262424 cells (1.1178%) carry Cradle's 1e20 'undefined' sentinel in
  all three components.  The FLD path has normalised that to NaN since R118;
  the FPH path had not, so those cells survived as 1e20 m/s velocities;
* the scale both 3-D paths applied (0.05 * model width, never divided by the
  field's own peak) drew arrows 9.8e-6 m long in a 0.536 m model at the
  default Scale Length = 1.0 -- invisible -- and the 1e20 entries stretched
  the glyph bounds to 1e18 so the camera followed them;
* vector_space_v ('Space (v)') and vector_scale_thickness ('Scale -
  Thickness') were written by the dialog, stored on the object and read by
  nobody (they sat in tests/field_exemptions.json as 'planned R118').

scPOST's manual fixes the semantics (HTML_POST_eng):
  P2011_0038_base0062 '[Uniform] ... enter a value for [Space(u)] and
  [Space(v)] to adjust the spacing.  The value is a relative value and
  irrelevant to the coordinates.'
  P2011_0034_base0058 'enter a relative factor to the default value in
  [Length] and/or [Thickness] ... [Angle] and/or [Size] of [Arrow]'.
so every one of those controls has to change what is drawn.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fv.model.dataset import normalise_field_sentinels  # noqa: E402
from fv.model.objects import PlaneObject  # noqa: E402
from fv.render import plane as plane_mod  # noqa: E402
from fv.render import surface as surface_mod  # noqa: E402
from fv.render.plane import (  # noqa: E402
    _uniform_points_on_cut,
    _vector_scale,
    attach_vector,
    vector_actor,
)
from fv.render.vector import (  # noqa: E402
    glyph_scale,
    resolve_vector_base,
    vector_peak,
)

vtk = pytest.importorskip("vtk")
from vtk.util import numpy_support as _vns  # noqa: E402

# --- fixtures -------------------------------------------------------------

class _Var:
    def __init__(self, arr):
        self.kind = "vector"
        self.location = "cell"
        self.array = np.asarray(arr, dtype=np.float64)


class _FF:
    """Minimal FieldFile stand-in: component names + cell arrays."""

    def __init__(self, comps, n_cells=None):
        self.variables = {n: _Var(a) for n, a in comps.items()}
        self.n_cells = n_cells or len(next(iter(comps.values())))
        self.kind = "fph"

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


def _mid_plane(var="VEL", scale_length=1.0, **kw):
    obj = PlaneObject()
    obj.point = (1.5, 1.5, 1.5)
    obj.normal = (0.0, 0.0, 1.0)
    obj.show_vector = True
    obj.vector_var = var
    obj.vector_scale_length = scale_length
    kwargs = dict(vector_space_u=1.0, vector_space_v=1.0,
                  vector_scale_thickness=1.0, vector_arrow_angle=1.0,
                  vector_arrow_size=1.0, vector_location="Uniform")
    kwargs.update(kw)
    for key, value in kwargs.items():
        setattr(obj, key, value)
    return obj


def _glyph_output(actor):
    """The polydata vtkGlyph3D produced for actor (None when there is none)."""
    if actor is None:
        return None
    port = actor.GetMapper().GetInputConnection(0, 0)
    if port is None:
        return None
    prod = port.GetProducer()
    prod.Update()
    return prod.GetOutputDataObject(0)


def _pd_with_vectors(vecs):
    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    for i in range(len(vecs)):
        pts.InsertNextPoint(float(i), 0.0, 0.0)
    pd.SetPoints(pts)
    arr = _vns.numpy_to_vtk(
        np.ascontiguousarray(np.asarray(vecs, dtype=np.float64)), deep=True)
    arr.SetName("VEL")
    pd.GetPointData().SetVectors(arr)
    return pd


# --- the name the tab offers must reach the arrows ------------------------

def test_r133c_plane_actor_draws_arrows_for_the_base_name():
    ug = _hex_grid()
    ff = _FF({"VELX": np.full(27, 1.0), "VELY": np.zeros(27),
              "VELZ": np.zeros(27)})
    act = vector_actor(ug, ff, _mid_plane("VEL"), True)
    out = _glyph_output(act)
    assert act is not None and out.GetNumberOfPoints() > 0


def test_r133c_plane_actor_accepts_a_component_name_end_to_end():
    """R133b folded the name inside attach_vector only; the actor still used
    the raw name for SetActiveVectors, so a saved session holding VELX drew
    no arrows at all."""
    ug = _hex_grid()
    ff = _FF({"VELX": np.full(27, 1.0), "VELY": np.zeros(27),
              "VELZ": np.zeros(27)})
    act = vector_actor(ug, ff, _mid_plane("VELX"), True)
    out = _glyph_output(act)
    assert act is not None, "component name must still draw arrows"
    assert out.GetNumberOfPoints() > 0
    b = out.GetBounds()
    assert all(abs(v) < 100.0 for v in b), b


def test_r133c_missing_component_still_reports_and_draws_nothing(caplog):
    ug = _hex_grid()
    ff = _FF({"VELX": np.full(27, 1.0), "VELY": np.zeros(27)})
    with caplog.at_level("WARNING"):
        assert vector_actor(ug, ff, _mid_plane("VEL"), True) is None
    assert any("has no Z component" in r.getMessage() for r in caplog.records)


def test_r133c_surface_actor_accepts_a_component_name():
    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    for p in ((0, 0, 0), (1, 0, 0), (0, 1, 0)):
        pts.InsertNextPoint(*p)
    pd.SetPoints(pts)
    # A polydata needs its cell arrays allocated (SetPolys), not a bare
    # InsertNextCell: the latter leaves the structure inconsistent and the
    # glyph filter then dies with a native access violation.
    polys = vtk.vtkCellArray()
    polys.InsertNextCell(3)
    for i in range(3):
        polys.InsertCellPoint(i)
    pd.SetPolys(polys)
    arr = _vns.numpy_to_vtk(
        np.ascontiguousarray(np.array([[1.0, 2.0, 3.0]])), deep=True)
    arr.SetName("VEL")
    pd.GetCellData().SetVectors(arr)
    obj = _mid_plane("VELX")
    act = surface_mod.vector_actor(pd, obj, True)
    out = _glyph_output(act)
    assert act is not None and out.GetNumberOfPoints() > 0


# --- scale: relative to the field, immune to undefined entries ------------

def test_r133c_scale_is_relative_to_the_field_peak():
    """Scale Length = 1 puts the fastest arrow at 5% of the model size.

    Independent expectation: the factor is 0.05 * width / peak, so
    peak * factor == 0.05 * width whatever units the field is in.
    """
    pd = _pd_with_vectors([[3.0, 4.0, 0.0], [0.0, 0.0, 0.0]])  # peak |v| = 5
    obj = _mid_plane("VEL", scale_length=2.0)
    got = _vector_scale(pd, obj)                      # width (bounds) = 1.0
    assert got == pytest.approx(0.05 * 1.0 * 2.0 / 5.0)
    assert 5.0 * got == pytest.approx(0.05 * 1.0 * 2.0)


def test_r133c_same_field_scaled_up_draws_the_same_arrows():
    """A field expressed in different units must not change the drawing."""
    small = _pd_with_vectors([[3.0, 4.0, 0.0]])
    big = _pd_with_vectors([[3.0e4, 4.0e4, 0.0]])
    obj = _mid_plane("VEL")
    assert _vector_scale(small, obj) == pytest.approx(
        _vector_scale(big, obj) * 1.0e4)


def test_r133c_scale_ignores_undefined_entries():
    """1e20 sentinels and NaN must not become the reference magnitude."""
    pd = _pd_with_vectors([[1.0e20, 1.0e20, 1.0e20],
                           [0.5, 0.0, 0.0],
                           [np.nan, np.nan, np.nan]])
    assert vector_peak(pd) == pytest.approx(0.5)
    obj = _mid_plane("VEL")
    # width is the polyline's extent (2.0), not 1.0
    assert _vector_scale(pd, obj) == pytest.approx(0.05 * 2.0 / 0.5)


def test_r133c_fph_undefined_sentinel_becomes_nan():
    arr = normalise_field_sentinels(
        np.array([1.0, 1.0e20, -1.0e20, np.nan, 2.0]))
    assert np.isnan(arr[1]) and np.isnan(arr[2]) and np.isnan(arr[3])
    assert arr[0] == 1.0 and arr[4] == 2.0


def test_r133c_glyph_scale_falls_back_without_vectors():
    empty = vtk.vtkPolyData()
    assert glyph_scale(empty, 10.0, 1.0) == pytest.approx(0.05 * 10.0)


# --- Space (u) / Space (v) / Thickness must change the drawing ------------

def test_r133c_space_u_and_v_move_the_sample_grid_independently():
    """[Uniform] samples max(u,v)/40 * Space in each in-plane direction.

    Independent expectation for a 4x4x4 block: step 0.1 -> 40x40 = 1600
    points; Space(v) = 4 -> 40x10 = 400; Space(u) = 4 -> 10x40 = 400.
    """
    ug = _hex_grid(4, 4, 4)
    n0 = _uniform_points_on_cut(ug, _mid_plane()).GetNumberOfPoints()
    nv = _uniform_points_on_cut(
        ug, _mid_plane(vector_space_v=4.0)).GetNumberOfPoints()
    nu = _uniform_points_on_cut(
        ug, _mid_plane(vector_space_u=4.0)).GetNumberOfPoints()
    assert (n0, nv, nu) == (1600, 400, 400)


def test_r133c_thickness_scales_the_arrow_shaft():
    base = plane_mod.vector_glyph_source(_mid_plane())
    thick = plane_mod.vector_glyph_source(
        _mid_plane(vector_scale_thickness=10.0))
    assert base.GetShaftRadius() == pytest.approx(0.04)
    assert thick.GetShaftRadius() == pytest.approx(0.4)


def test_r133c_arrow_head_controls_scale_the_source():
    src = plane_mod.vector_glyph_source(
        _mid_plane(vector_arrow_size=2.0, vector_arrow_angle=2.0))
    assert src.GetTipRadius() == pytest.approx(0.2)      # size * 0.1
    assert src.GetTipLength() == pytest.approx(0.7)      # angle * 0.35
    # vtkArrowSource caps the tip length at 1.0, so a huge factor saturates
    capped = plane_mod.vector_glyph_source(
        _mid_plane(vector_arrow_angle=10.0))
    assert capped.GetTipLength() == pytest.approx(1.0)


def test_r133c_simple_and_3d_types_keep_their_own_sources():
    assert plane_mod.vector_glyph_source(
        _mid_plane(vector_type="Simple")).IsA("vtkLineSource")
    assert plane_mod.vector_glyph_source(
        _mid_plane(vector_type="3D")).IsA("vtkConeSource")


# --- shared resolver ------------------------------------------------------

def test_r133c_resolver_folds_only_complete_component_sets():
    ff = _FF({"VELX": np.zeros(2), "VELY": np.zeros(2),
              "VELZ": np.zeros(2), "VECTX": np.zeros(2),
              "VECTY": np.zeros(2), "VECTZ": np.zeros(2)})
    assert resolve_vector_base(ff, "VELX") == ("VEL", [])
    assert resolve_vector_base(ff, "VECT") == ("VECT", [])
    assert resolve_vector_base(ff, "PRESX") == ("PRESX", ["X", "Y", "Z"])


def test_r133c_attach_vector_returns_the_folded_name_field():
    ug = _hex_grid()
    ff = _FF({"VELX": np.full(27, 2.0), "VELY": np.zeros(27),
              "VELZ": np.zeros(27)})
    arr = attach_vector(ug, ff, "VELX", True)
    assert arr is not None and arr.GetName() == "VEL"
    assert ug.GetCellData().GetVectors().GetName() == "VEL"
