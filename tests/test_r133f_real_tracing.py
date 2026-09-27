"""R133f - the three tracing paths on a real file (opt-in, marked slow).

Run:
    python -m pytest tests/test_r133f_real_tracing.py -m slow -q

R133d changed how these paths resolve their vector field; the unit tests in
tests/test_r133d_vector_consumers.py cover the failure paths.  This module
proves the success paths on the real sample (E:/cradle/tr03_9.fph, FPH,
221786 nodes / 63697 cells) and found one more defect on the way:

  * Streamline  2020 points / 10 lines, all finite and inside the model box;
  * Oil Flow    7960 points / 362 lines;
  * Pathline    used to draw NOTHING on any FPH file: _trace handed the
    cell-centred grid to vtkStreamTracer, which only reads point vectors, so
    the trace returned zero points and the object silently stayed empty.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from samples import sample  # noqa: E402

pytest.importorskip("vtk")

SAMPLE = sample("tr03_9.fph")

pytestmark = pytest.mark.slow


def _points_of(actor):
    """Point coordinates of the polydata an actor draws."""
    assert actor is not None, "no actor"
    prod = actor.GetMapper().GetInputConnection(0, 0).GetProducer()
    prod.Update()
    pd = prod.GetOutputDataObject(0)
    assert pd.GetNumberOfPoints() > 0, "actor draws nothing"
    return np.asarray(pd.GetPoints().GetData(), dtype=np.float64)


def _assert_inside_model(pts, lo, hi):
    """Every traced point must sit inside the model box (5% slack)."""
    slack = 0.05 * (hi - lo)
    inside = ((pts >= lo - slack).all(axis=1)
              & (pts <= hi + slack).all(axis=1))
    assert bool(np.isfinite(pts).all()), "non-finite trace points"
    assert inside.all(), "traced points outside the model box"


@pytest.fixture(scope="module")
def real_file():
    if SAMPLE is None:
        pytest.skip("tr03_9.fph sample not present")
    from fv.model.dataset import load_file
    from fv.render.plane import build_ugrid
    ff = load_file(str(SAMPLE))
    ugrid, cell_centered = build_ugrid(ff)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    return {
        "ff": ff,
        "ugrid": ugrid,
        "cc": cell_centered,
        "lo": verts.min(axis=0),
        "hi": verts.max(axis=0),
    }


def test_r133f_real_streamline_folds_a_component_name(real_file):
    """vector_var = VELX (a component) must fold to VEL and trace."""
    from fv.model.objects import StreamlineObject
    from fv.render.streamline import build_streamline_actors

    ff, ug = real_file["ff"], real_file["ugrid"]
    lo, hi = real_file["lo"], real_file["hi"]
    centre = 0.5 * (lo + hi)
    span = float((hi - lo).max())
    obj = StreamlineObject(index=1, vector_var="VELX",
                           seed_center=tuple(float(x) for x in centre),
                           seed_normal=(0.0, 0.0, 1.0),
                           seed_density_u=4, seed_density_v=4,
                           length=0.5 * span, step_size=0.005 * span,
                           max_steps=200)
    out = build_streamline_actors(ff, obj, ugrid=ug,
                                  cell_centered=real_file["cc"])
    assert "streamline" in out, "no streamline actor"
    pts = _points_of(out["streamline"])
    _assert_inside_model(pts, lo, hi)
    assert pts.shape[0] > 100


def test_r133f_real_oilflow_draws_lines(real_file):
    from fv.model.objects import PlaneObject
    from fv.render.oilflow import build_oilflow_actor

    ff, ug = real_file["ff"], real_file["ugrid"]
    lo, hi = real_file["lo"], real_file["hi"]
    centre = 0.5 * (lo + hi)
    span = float((hi - lo).max())
    obj = PlaneObject(index=1, point=tuple(float(x) for x in centre),
                      normal=(0.0, 0.0, 1.0), oilflow_display=True,
                      oilflow_var="VEL", oilflow_steps=20,
                      oilflow_length=0.5 * span)
    actor = build_oilflow_actor(ff, obj, ugrid=ug,
                                cell_centered=real_file["cc"])
    pts = _points_of(actor)
    _assert_inside_model(pts, lo, hi)
    assert pts.shape[0] > 100


def test_r133f_real_pathline_draws_lines(real_file):
    """Regression: the FPH (cell-centred) path produced no points at all."""
    from fv.model.objects import PathlineObject
    from fv.render.pathline import build_pathline_actors

    ff = real_file["ff"]
    lo, hi = real_file["lo"], real_file["hi"]
    span = float((hi - lo).max())
    centre = 0.5 * (lo + hi)
    obj = PathlineObject(index=1, files=[str(SAMPLE)], vector_var="VELX",
                         seed_axis="Z", seed_coordinate=float(centre[2]),
                         density_u=3, density_v=3, steps_per_cycle=10,
                         step_size=0.002 * span)
    out = build_pathline_actors(obj, [str(SAMPLE)], ff)
    assert "pathline" in out, "no pathline actor"
    pts = _points_of(out["pathline"])
    _assert_inside_model(pts, lo, hi)
    assert pts.shape[0] > 10


def test_r133f_real_paths_refuse_an_unknown_field(real_file, caplog):
    """An incomplete field must be reported, not traced from zeros."""
    from fv.model.objects import PathlineObject, PlaneObject, StreamlineObject
    from fv.render.oilflow import build_oilflow_actor
    from fv.render.pathline import build_pathline_actors
    from fv.render.streamline import build_streamline_actors

    ff, ug = real_file["ff"], real_file["ugrid"]
    lo, hi = real_file["lo"], real_file["hi"]
    centre = tuple(float(x) for x in 0.5 * (lo + hi))
    with caplog.at_level("WARNING"):
        assert build_streamline_actors(
            ff, StreamlineObject(index=1, vector_var="NOPE"),
            ugrid=ug, cell_centered=real_file["cc"]) == {}
        assert build_oilflow_actor(
            ff, PlaneObject(index=1, point=centre, normal=(0.0, 0.0, 1.0),
                            oilflow_display=True, oilflow_var="NOPE"),
            ugrid=ug, cell_centered=real_file["cc"]) is None
        assert build_pathline_actors(
            PathlineObject(index=1, files=[str(SAMPLE)], vector_var="NOPE"),
            [str(SAMPLE)], ff) == {}
    messages = [r.getMessage() for r in caplog.records]
    assert sum("has no X/Y/Z component" in m for m in messages) >= 3, messages
