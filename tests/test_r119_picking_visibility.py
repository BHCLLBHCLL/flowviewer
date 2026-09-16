"""R119: picking and tree visibility must reach every object kind.

Two mechanisms were broken in a way that looked like working UI:

* pick resolution relied on each renderer remembering to call
  register_actor_object.  Surface and Particle - the default object and the
  particle cloud - never did, so clicking them (and rubber-band selecting,
  and Delete/Hide Selected) did nothing, while isosurface/point/plane worked.
* pipelines record namespaced layer keys ("surface:contour", "plane:mesh")
  while the object tree asks for the bare kind, so an exact dict lookup
  matched nothing and the eye checkbox did nothing for every kind except
  grid and colorbar.

Both are now enforced at choke points rather than by convention, and these
tests drive real scenes (enable_3d=True, offscreen) so visibility is observed
on actual vtkActors rather than on placeholder strings.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

vtk = pytest.importorskip("vtk")

from fv.model import dataset  # noqa: E402
from fv.model import objects as O  # noqa: E402
from fv.render import scene as S  # noqa: E402

FPH = r"D:\training\cgns\examples\tr03_9.fph"
FLD = r"D:\training\cgns\examples\ex1_100.fld"


def _make(kind):
    for name in dir(O):
        cls = getattr(O, name)
        if isinstance(cls, type) and getattr(cls, "kind", None) == kind:
            return cls()
    return None


def _scene_for(path, kind, **cfg):
    ff = dataset.load_file(path)
    sc = S.Scene()
    main = O.MainObject(path, Path(path).name)
    obj = _make(kind)
    assert obj is not None, kind
    for key, value in cfg.items():
        if hasattr(obj, key):
            setattr(obj, key, value)
    main.children = [obj]
    sc.build(ff, main=main)
    return sc, obj


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_surface_actors_are_resolvable_by_pick():
    """The default Surface used to be invisible to pick_actor."""
    sc, obj = _scene_for(FLD, "surface", show_contour=True,
                         contour_var="PRES", show_mesh=True)
    owners = {kind for kind, o in sc._actor_object.values() if o is obj}
    assert owners == {"surface"}, owners
    actors = [a for a in sc._layer_actors_for("surface")
              if not isinstance(a, str)]
    assert actors, "no surface actor was built"
    # pick_actor resolves a screen position through the actor-to-object map, so
    # this map entry is what a click needs in order to find the object.
    for actor in actors:
        kind, resolved = sc._actor_object.get(actor, (None, None))
        assert resolved is obj and kind == "surface"


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_particle_actors_are_resolvable_by_pick():
    sc, obj = _scene_for(FPH, "particle")
    owners = {kind for kind, o in sc._actor_object.values() if o is obj}
    assert owners == {"particle"}, owners


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_bare_kind_selects_every_namespaced_layer():
    """The tree asks for "surface"; pipelines stored "surface:contour"."""
    sc, obj = _scene_for(FPH, "volume", show_scalar=True,
                         scalar_var="PRES")
    assert sc.layer_count("volume") > 0, "bare lookup found nothing"
    named = [k for k in sc._layer_actors if k.startswith("volume:")]
    assert named, "the pipeline should record a namespaced key"
    direct = sc.layer_count(named[0])
    assert direct > 0


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_tree_visibility_actually_hides_the_actors():
    """A checkbox that changes no actor is indistinguishable from a no-op."""
    sc, obj = _scene_for(FPH, "volume", show_scalar=True,
                         scalar_var="PRES")
    actors = [a for a in sc._layer_actors_for("volume")
              if not isinstance(a, str)]
    assert actors, "no volume actor to toggle"

    sc.set_layer_visible("volume", False)
    assert all(a.GetVisibility() == 0 for a in actors)
    sc.set_layer_visible("volume", True)
    assert all(a.GetVisibility() == 1 for a in actors)


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_unknown_kind_toggles_nothing_and_does_not_raise():
    sc, _ = _scene_for(FLD, "surface", show_contour=True,
                       contour_var="PRES")
    sc.set_layer_visible("no_such_kind", False)  # must be a silent no-op
    assert sc.layer_count("no_such_kind") == 0


@pytest.mark.skipif(not Path(FLD).exists(), reason="sample not present")
def test_every_built_layer_uses_a_kind_prefixed_key():
    """Otherwise the bare-kind lookup above cannot reach it."""
    sc, obj = _scene_for(FLD, "surface", show_contour=True,
                         contour_var="PRES", show_mesh=True)
    keys = [k for k in sc._layer_actors if k != "grid"]
    assert keys
    for key in keys:
        head = key.split(":")[0]
        assert head in {obj.kind, "colorbar"}, (
            "layer %r would be unreachable from the tree" % key)
        assert sc.layer_count(head) > 0
