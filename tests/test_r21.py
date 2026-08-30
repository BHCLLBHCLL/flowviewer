"""R21 - rendering depth: DST colormap preset, isosurface cycle animation,
and bump-mapped boundary surfaces (beyond-scPOST).
"""

import os
import sys
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"
print("test_r21 FPH exists:", Path(FPH).exists())


def _cycle(ff, offset):
    base = np.asarray(ff.variables["PRES"].array)
    f2 = replace(ff)
    v = dict(f2.variables)
    v["PRES"] = replace(v["PRES"], array=base + offset)
    f2.variables = v
    return f2


def test_dst_colormap_registered_and_distinct():
    from fv.render.colorbar import build_lut
    lut = build_lut(256, "dst")
    assert lut.GetNumberOfTableValues() == 256
    rainbow = build_lut(256, "Rainbow")
    for i in range(256):
        if lut.GetTableValue(i) != rainbow.GetTableValue(i):
            break
    else:
        pytest.fail("DST lookup table identical to Rainbow")


def test_dst_colormap_red_endpoints():
    from fv.render.colorbar import build_lut
    lut = build_lut(256, "DST")
    assert lut.GetNumberOfTableValues() > 0
    assert lut.GetTableValue(0)[0] < 0.1
    assert lut.GetTableValue(255)[0] > 0.5


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_iso_animation_one_frame_per_cycle():
    from types import SimpleNamespace

    from fv.model.dataset import load_file
    from fv.render.isosurface import build_iso_animation
    ff = load_file(FPH)
    cycles = [_cycle(ff, 0.0), _cycle(ff, 10.0)]
    obj = SimpleNamespace(contour_var="PRES", contour_number=4,
                          contour_values=None, contour_line=False,
                          show_vector=False, vector_var="",
                          contour_mono_color=False, contour_transparent=False)
    frames = build_iso_animation(cycles, obj)
    assert len(frames) == 2
    assert "contour" in frames[0] and "contour" in frames[1]


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_iso_animation_frames_use_own_scalar_range():
    from types import SimpleNamespace

    from fv.model.dataset import load_file
    from fv.render.isosurface import build_iso_animation
    ff = load_file(FPH)
    cycles = [_cycle(ff, 0.0), _cycle(ff, 50.0)]
    obj = SimpleNamespace(contour_var="PRES", contour_number=4,
                          contour_values=None, contour_line=False,
                          show_vector=False, vector_var="",
                          contour_mono_color=False, contour_transparent=False)
    frames = build_iso_animation(cycles, obj)
    a0 = frames[0]["contour"].GetMapper().GetScalarRange()
    a1 = frames[1]["contour"].GetMapper().GetScalarRange()
    assert a1[1] > a0[1]


def _pd_points(pd):
    from vtk.util import numpy_support as vns
    return vns.vtk_to_numpy(pd.GetPoints().GetData()).astype(np.float64, copy=False)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_bump_surface_zero_factor_keeps_vertices():
    from types import SimpleNamespace

    from fv.model.dataset import load_file
    from fv.render.surface import build_surface_polydata, bump_surface_actor
    ff = load_file(FPH)
    obj = SimpleNamespace(bump_var="PRES", bump_factor=0.0,
                          contour_var="PRES", selected_regions=None)
    pd, cc, fi = build_surface_polydata(ff, obj)
    if pd is None or pd.GetNumberOfCells() == 0:
        pytest.skip("no boundary surface in sample")
    act = bump_surface_actor(ff, obj, pd=pd, cell_centered=cc, face_idx=fi)
    assert act is not None
    out = act.GetMapper().GetInput()
    in_pts = _pd_points(pd)
    out_pts = _pd_points(out)
    assert out_pts.shape == in_pts.shape
    np.testing.assert_allclose(out_pts, in_pts, atol=1e-9)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_bump_surface_moves_high_scalar_region():
    from types import SimpleNamespace

    from fv.model.dataset import load_file
    from fv.render.surface import build_surface_polydata, bump_surface_actor
    ff = load_file(FPH)
    obj = SimpleNamespace(bump_var="PRES", bump_factor=0.1,
                          contour_var="PRES", selected_regions=None)
    pd, cc, fi = build_surface_polydata(ff, obj)
    if pd is None or pd.GetNumberOfCells() == 0:
        pytest.skip("no boundary surface in sample")
    act = bump_surface_actor(ff, obj, pd=pd, cell_centered=cc, face_idx=fi)
    assert act is not None
    out = act.GetMapper().GetInput()
    in_pts = _pd_points(pd)
    out_pts = _pd_points(out)
    assert out_pts.shape == in_pts.shape
    assert np.any(np.linalg.norm(out_pts - in_pts, axis=1) > 1e-6)
