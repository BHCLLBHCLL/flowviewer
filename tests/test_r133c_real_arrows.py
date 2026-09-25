"""R133c acceptance on the real block sample (opt-in, marked slow).

Run:
    python -m pytest tests/test_r133c_real_arrows.py -m slow -q

The sample is a 174 MB FPH on this machine; the module costs about a minute
(10 s parse + 52 s unstructured-grid build), which is why it is not in the
default tier.  It is the check R133b deferred: do arrows actually appear on a
real file, and are they the size the Scale Length promises?

Measured 2026-09-13 (before the R133c fixes):
  * vector_actor(..., 'VEL')  -> 26040 points / 12600 cells, arrows 9.8e-6 m
    long in a 0.536 m model at Scale Length 1.0 (invisible);
  * vector_actor(..., 'VELX') -> None (the raw name never reached
    SetActiveVectors);
  * location Nodes/Center -> glyph bounds 1.6e18, because 14112 cells carry
    the 1e20 sentinel.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

SAMPLE = Path("D:/training/cradle/laptop/"
              "laptop_thermal_steady_scaled_v3_block/"
              "laptop_thermal_steady_scaled_v3_block_50.fph")

#: cells whose three components hold Cradle's 1e20 'undefined' sentinel
SENTINEL_CELLS = 14112

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def block_file():
    if not SAMPLE.is_file():
        pytest.skip("block sample not present")
    from fv.model.dataset import load_file
    return load_file(str(SAMPLE))


@pytest.fixture(scope="module")
def block_grid(block_file):
    from fv.render.plane import build_ugrid
    ug, cell_centered = build_ugrid(block_file)
    assert ug is not None
    return ug, cell_centered


def _plane(ff, var, **kw):
    from fv.model.objects import PlaneObject, _default_plane, _normal_for_axis, _point_on_axis
    lo, hi, axis, mid = _default_plane(ff)
    obj = PlaneObject(index=1, axis=axis, coordinate=mid,
                      point=_point_on_axis(axis, mid),
                      normal=_normal_for_axis(axis),
                      show_vector=True, vector_var=var)
    for key, value in kw.items():
        setattr(obj, key, value)
    return obj


def _glyph_output(actor):
    assert actor is not None
    prod = actor.GetMapper().GetInputConnection(0, 0).GetProducer()
    prod.Update()
    return prod.GetOutputDataObject(0)


def test_r133c_real_file_exposes_the_base_vector_name(block_file):
    from fv.gui.object_dialogs import _vector_vars
    for suffix in ("X", "Y", "Z"):
        assert block_file.variables["VEL" + suffix].kind == "vector"
    assert "VEL" not in block_file.variables
    assert _vector_vars(block_file) == ["VEL"]


def test_r133c_real_file_undefined_cells_are_nan_not_1e20(block_file):
    vx = np.asarray(block_file.variable_array("VELX"), dtype=np.float64)
    assert int(np.isnan(vx).sum()) == SENTINEL_CELLS
    assert np.nanmax(np.abs(vx)) < 1.0, "no 1e20 m/s velocity may survive"
    mag = np.sqrt(sum(
        np.asarray(block_file.variable_array("VEL" + s), dtype=np.float64) ** 2
        for s in "XYZ"))
    finite = mag[np.isfinite(mag)]
    assert 1e-5 < float(np.median(finite)) < 1e-1


def test_r133c_real_file_draws_arrows_of_the_promised_length(block_file,
                                                            block_grid):
    from fv.render.plane import _vector_scale, attach_vector, vector_actor
    ug, cell_centered = block_grid
    b = ug.GetBounds()
    width = max(b[1] - b[0], b[3] - b[2], b[5] - b[4])

    for name in ("VEL", "VELX"):          # base name and component name
        act = vector_actor(ug, block_file, _plane(block_file, name),
                           cell_centered)
        out = _glyph_output(act)
        assert out.GetNumberOfPoints() > 0, name
        gb = out.GetBounds()
        assert all(np.isfinite(v) for v in gb), (name, gb)
        assert max(gb[1] - gb[0], gb[3] - gb[2], gb[5] - gb[4]) < 3.0 * width

    # Scale Length = 1 must put the fastest vector at 5% of the model width.
    attach_vector(ug, block_file, "VEL", cell_centered)
    mag = np.sqrt(sum(
        np.asarray(block_file.variable_array("VEL" + s), dtype=np.float64) ** 2
        for s in "XYZ"))
    peak = float(np.nanmax(mag))
    scale = _vector_scale(ug, _plane(block_file, "VEL"))
    assert peak * scale == pytest.approx(0.05 * width, rel=1e-6)
