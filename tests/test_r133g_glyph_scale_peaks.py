"""R133g - the last two glyph scales must use the shared peak.

fv/render/vector.py and fv/render/particle.py each computed their own
reference magnitude with a plain mags.max():

* one NaN entry made the factor NaN (vtkGlyph3D then drew nothing sane);
* one 1e20 "undefined" sentinel became the peak, so every real arrow was
  scaled to ~0 (the same failure R133c measured on the block sample).

Both now call vector_peak(), which drops NaN and the sentinel.  Expectations
are analytic: the factor is 0.03 * diagonal / peak.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fv.render import particle as particle_mod  # noqa: E402
from fv.render.vector import _glyph_scale, vector_peak  # noqa: E402

vtk = pytest.importorskip("vtk")
from vtk.util import numpy_support as _vns  # noqa: E402


def _pd(vecs, scale=1.0):
    pd = vtk.vtkPolyData()
    pts = vtk.vtkPoints()
    for i in range(len(vecs)):
        pts.InsertNextPoint(scale * float(i), 0.0, 0.0)
    pd.SetPoints(pts)
    arr = _vns.numpy_to_vtk(
        np.ascontiguousarray(np.asarray(vecs, dtype=np.float64)), deep=True)
    arr.SetName("VEL")
    pd.GetPointData().SetVectors(arr)
    return pd


def test_r133g_vector_scale_uses_the_finite_peak():
    """diagonal = 1.0 over three unit-spaced points; peak |v| = 5 (3,4,...)."""
    pd = _pd([[3.0, 4.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    assert vector_peak(pd) == pytest.approx(5.0)
    assert _glyph_scale(pd) == pytest.approx(0.03 * 2.0 / 5.0)


def test_r133g_vector_scale_ignores_nan_and_sentinel():
    pd = _pd([[np.nan, np.nan, np.nan],
              [1.0e20, 1.0e20, 1.0e20],
              [0.5, 0.0, 0.0]])
    got = _glyph_scale(pd)
    assert np.isfinite(got)
    assert got == pytest.approx(0.03 * 2.0 / 0.5)


def test_r133g_vector_scale_without_finite_data_keeps_the_old_fallback():
    pd = _pd([[np.nan, 0.0, 0.0], [1.0e20, 0.0, 0.0]])
    assert _glyph_scale(pd) == 1.0


def test_r133g_particle_scale_ignores_nan_and_sentinel():
    pd = _pd([[np.nan, 0.0, 0.0], [1.0e20, 1.0e20, 1.0e20],
              [2.0, 0.0, 0.0]])
    got = particle_mod._glyph_scale(pd)
    assert np.isfinite(got)
    assert got == pytest.approx(0.03 * 2.0 / 2.0)


def test_r133g_both_scales_agree_on_the_same_field():
    pd = _pd([[1.0, 0.0, 0.0], [4.0, 0.0, 0.0]])
    assert particle_mod._glyph_scale(pd) == pytest.approx(_glyph_scale(pd))
