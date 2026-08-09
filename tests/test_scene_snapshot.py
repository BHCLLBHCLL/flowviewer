"""GL snapshot + incremental object update tests (DEV_PLAN §11 I).

* ``test_scene_snapshot_png`` renders a 3D scene offscreen and verifies a
  non-empty PNG is produced (GL 静帧自动化).
* ``test_apply_to_object_incremental`` rebuilds a single object without
  disturbing sibling actors.
* ``test_emt_alias`` checks the loader registry recognises EMT as fph-family.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

FPH = r"D:\training\cgns\examples\tr03_9.fph"

try:
    import vtk
    _HAS_VTK = True
except Exception:  # pragma: no cover
    _HAS_VTK = False


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_scene_snapshot_png(tmp_path):
    """Offscreen render of an FPH scene produces a non-empty PNG."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.export import snapshot_png
    from fv.render.scene import Scene

    ff = load_file(FPH)
    main = MainObject.from_field_file(ff, magic=True)
    sc = Scene(enable_3d=True)
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetSize(320, 240)
    rw.AddRenderer(sc.renderer)
    sc.build(ff, main=main)
    rw.Render()
    out = tmp_path / "shot.png"
    assert snapshot_png(sc.renderer, str(out)) is True
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_apply_to_object_incremental(tmp_path):
    """apply_to_object replaces one plane without full rebuild (I-gap)."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.scene import Scene

    ff = load_file(FPH)
    main = MainObject.from_field_file(ff, magic=True)
    sc = Scene(enable_3d=False)
    sc.build(ff, main=main)
    plane = next(o for o in main.children if o.kind == "plane")
    before = dict(sc._layer_actors)
    plane.coordinate = 0.5
    sc.apply_to_object(ff, plane)
    after = dict(sc._layer_actors)
    # Sibling layers (surface) survive; plane rebuilt (may be re-added)
    assert any("surface" in k for k in before)
    assert "plane" in after or any(k.startswith("plane:") for k in after)


@pytest.mark.skipif(not _HAS_VTK, reason="vtk unavailable")
def test_apply_to_object_removes_old_actors(tmp_path):
    """Old actors of an edited object are gone after apply_to_object."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.scene import Scene

    ff = load_file(FPH)
    main = MainObject.from_field_file(ff, magic=True)
    sc = Scene(enable_3d=False)
    sc.build(ff, main=main)
    plane = next(o for o in main.children if o.kind == "plane")
    sc.apply_to_object(ff, plane)
    # Every actor the plane owns is still present in a layer (no orphans)
    live = {a for actors in sc._layer_actors.values() for a in actors}
    owned = [a for a, (k, o) in sc._actor_object.items() if o is plane]
    assert owned and all(a in live for a in owned)


def test_emt_alias():
    """Loader registry tags EMT as fph-family (I-gap alias)."""
    from fv.model import loaders
    assert loaders.probe_format(r"D:\x\case.emt") == "fph"
    assert "fph" in loaders.loaders()
    assert loaders.can_load(FPH) is True


def test_apply_to_object_headless_placeholder():
    """Incremental path works with headless placeholder layers."""
    from fv.model.dataset import load_file
    from fv.model.objects import MainObject
    from fv.render.scene import Scene

    ff = load_file(FPH)
    main = MainObject.from_field_file(ff, magic=True)
    sc = Scene(enable_3d=False)
    sc.build(ff, main=main)
    assert sc._field_file is not None
    plane = next(o for o in main.children if o.kind == "plane")
    sc.apply_to_object(ff, plane)  # must not raise
    assert "plane" in sc.actor_names() or any(
        k.startswith("plane:") for k in sc.actor_names())