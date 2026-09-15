"""R118: render-output correctness -- pixels, not just pipelines.

Every defect here was measured as output a user would see as wrong or absent,
and each fix is pinned by a test that fails on the old behaviour.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

vtk = pytest.importorskip("vtk")

from fv.model import dataset  # noqa: E402
from fv.model import objects as O  # noqa: E402
from fv.render import information as INF  # noqa: E402
from fv.render import particle as PA  # noqa: E402
from fv.render import plane as P  # noqa: E402
from fv.render import surface as SU  # noqa: E402
from fv.render import volume as V  # noqa: E402

FLD = r"D:\training\cgns\examples\ex1_100.fld"
FPH = r"D:\training\cgns\examples\tr03_9.fph"


def _nonblack(actor) -> int:
    """Render one actor/volume offscreen and count lit pixels."""
    ren = vtk.vtkRenderer()
    ren.SetBackground(0, 0, 0)
    if isinstance(actor, vtk.vtkVolume):
        ren.AddVolume(actor)
    else:
        ren.AddActor(actor)
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.AddRenderer(ren)
    rw.SetSize(200, 150)
    ren.ResetCamera()
    rw.Render()
    shot = vtk.vtkWindowToImageFilter()
    shot.SetInput(rw)
    shot.Update()
    img = shot.GetOutput()
    arr = vtk.util.numpy_support.vtk_to_numpy(
        img.GetPointData().GetScalars()).reshape(-1, 3)
    return int((arr.sum(axis=1) > 12).sum())


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_fld_volume_actually_renders():
    """Hex cells went to the tetra-only ray-cast mapper: 0 pixels."""
    ff = dataset.load_file(FLD)
    ug, cc = P.build_ugrid(ff)
    obj = O.VolumeObject()
    obj.show_scalar = True
    obj.scalar_var = "PRES"
    actors = V.build_volume_actors(ff, obj, ugrid=ug, cell_centered=cc)
    assert actors, "no volume actor was built"
    for name, actor in actors.items():
        assert _nonblack(actor) > 100, "%s rendered %d pixels" % (
            name, _nonblack(actor))


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_fld_sentinel_values_become_nan():
    """1e20 undefined markers used to poison every derived range."""
    ff = dataset.load_file(FLD)
    pres = np.asarray(ff.variable_array("PRES"), dtype=float)
    assert np.isnan(pres).any(), "the fixture has no sentinel entries"
    assert np.nanmax(np.abs(pres)) < 1e10, "a sentinel survived"
    assert np.isfinite(pres[~np.isnan(pres)]).all()


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_surface_trim_keeps_the_requested_half():
    """Clipping on the surface own bbox left 0 of 5556 faces."""
    ff = dataset.load_file(FLD)
    obj = O.SurfaceObject()
    obj.selected_regions = []
    pd = SU.build_surface_polydata(ff, obj)[0]
    total = pd.GetNumberOfPolys()
    assert total > 0
    b = pd.GetBounds()
    half = (b[0] + b[1]) / 2.0

    lower = O.SurfaceObject()
    lower.selected_regions = []
    lower.trim_xmin = half
    keep_hi = SU.trim_surface(pd, lower)
    assert 0 < keep_hi.GetNumberOfPolys() < total
    assert keep_hi.GetBounds()[0] >= half - 1e-9

    upper = O.SurfaceObject()
    upper.selected_regions = []
    upper.trim_xmax = half
    keep_lo = SU.trim_surface(pd, upper)
    assert 0 < keep_lo.GetNumberOfPolys() < total
    assert keep_lo.GetBounds()[1] <= half + 1e-9

    at_zero = O.SurfaceObject()
    at_zero.selected_regions = []
    at_zero.trim_xmin = 0.0
    assert SU.trim_surface(pd, at_zero).GetNumberOfPolys() > 0

    none_set = O.SurfaceObject()
    none_set.selected_regions = []
    assert SU.trim_surface(pd, none_set).GetNumberOfPolys() == total


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_particle_points_are_drawable():
    """Loose vtkPoints are not cells, so the cloud rendered nothing."""
    ff = dataset.load_file(FPH)
    obj = O.ParticleObject()
    actors = PA.build_particle_actors(obj, ff)
    assert actors, "no particle actor was built"
    for name, actor in actors.items():
        pd = actor.GetMapper().GetInput()
        assert pd.GetNumberOfPoints() > 0
        assert pd.GetNumberOfVerts() == pd.GetNumberOfPoints(), (
            "%s has no vertex cells, so nothing can be drawn" % name)
        assert _nonblack(actor) > 0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_information_probe_covers_the_whole_domain():
    """A vertex index was used for cell arrays, silently returning {}."""
    ff = dataset.load_file(FPH)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    n_vars = len(ff.variables)
    for vtx in (10, 50_000, 200_000):
        got = INF.probe_values(ff, tuple(float(x) for x in verts[vtx]))
        assert len(got) == n_vars, (
            "probe at vertex %d returned %d of %d variables"
            % (vtx, len(got), n_vars))


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_fph_volume_still_renders():
    """The R118 dispatch change must not regress the polyhedral path."""
    ff = dataset.load_file(FPH)
    ug, cc = P.build_ugrid(ff)
    obj = O.VolumeObject()
    obj.show_scalar = True
    obj.scalar_var = "PRES"
    actors = V.build_volume_actors(ff, obj, ugrid=ug, cell_centered=cc)
    assert actors
    for name, actor in actors.items():
        assert _nonblack(actor) > 100, name
