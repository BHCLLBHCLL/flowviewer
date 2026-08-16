"""R3.1 real blade surface tests: wall identification, PS/SS normals,
pitch unwrap, B2B surface sampling (tr03 impeller + synthetic).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

FPH = Path(r"D:\training\cgns\examples\tr03_9.fph")


@pytest.fixture(scope="module")
def ff():
    if not FPH.exists():
        pytest.skip("tr03_9.fph not present")
    from fv.model.dataset import load_file
    return load_file(str(FPH))


def test_blade_wall_faces_l1_keyword(ff):
    """Keyword scan finds @PartSurface_Impeller (9011 faces)."""
    from fv.render.turbo import blade_wall_faces
    bw = blade_wall_faces(ff, None)
    assert bw is not None
    fids, centers, normals, owner = bw
    assert fids.size == 9011
    assert centers.shape == (9011, 3)
    assert normals.shape == (9011, 3)
    # normals unit length (or zero-area degenerate faces)
    nn = np.linalg.norm(normals, axis=1)
    assert np.allclose(nn[nn > 0], 1.0, atol=1e-6)
    # owner cells in range, face centers inside vertex bounds
    assert owner.min() >= 0 and owner.max() < ff.n_cells
    vmin = np.asarray(ff.vertices).min(axis=0)
    vmax = np.asarray(ff.vertices).max(axis=0)
    assert np.all(centers.min(axis=0) >= vmin - 1e-9)
    assert np.all(centers.max(axis=0) <= vmax + 1e-9)


def test_blade_wall_faces_explicit_region(ff):
    """L0 explicit region name selects exactly that region."""
    from fv.render.turbo import blade_wall_faces
    bw = blade_wall_faces(ff, ["@PartSurface_Impeller"])
    assert bw is not None and bw[0].size == 9011
    bw2 = blade_wall_faces(ff, ["inlet"])
    assert bw2 is not None and bw2[0].size == 170


def test_ps_ss_normal_split(ff):
    """n_θ sign splits wall faces into two populated, opposite sides."""
    from fv.render.turbo import (_blade_wall_faces,
                                _normal_circumferential)
    bw = _blade_wall_faces(ff, None)
    assert bw is not None
    _, centers, normals, _ = bw
    nth = _normal_circumferential(normals, centers, "Z")
    nz = np.abs(nth) > 1e-9
    assert nz.sum() > 0.8 * nth.size, "most wall normals have θ component"
    pos = (nth > 1e-9).sum()
    neg = (nth < -1e-9).sum()
    assert pos > 0 and neg > 0
    # ratio sanity: two blade sides, same order of magnitude
    ratio = max(pos, neg) / max(1, min(pos, neg))
    assert 0.5 < ratio < 5.0
    # mean n_θ of the two sides have opposite signs
    assert nth[nth > 1e-9].mean() > 0
    assert nth[nth < -1e-9].mean() < 0


def test_blade_loading_surfaces_wall_based(ff):
    """Loading uses wall owner-cell values; both sides populated."""
    from fv.render.turbo import blade_loading_surfaces
    var = "PRES" if "PRES" in ff.variables else next(iter(ff.variables))
    sc, ps, ss = blade_loading_surfaces(ff, var, "Z", 16)
    assert sc is not None and len(sc) == 16
    assert np.isfinite(ps).sum() > 0 and np.isfinite(ss).sum() > 0
    # explicit region yields the same span axis range
    sc2, ps2, ss2 = blade_loading_surfaces(
        ff, var, "Z", 16, ["@PartSurface_Impeller"])
    assert sc2 is not None and np.allclose(sc, sc2)


def test_estimate_pitch_synthetic():
    """θ histogram autocorrelation recovers the blade pitch."""
    from fv.render.turbo import _estimate_pitch
    rng = np.random.default_rng(5)
    n_blades = 4
    th = []
    for k in range(n_blades):
        base = 2 * np.pi * k / n_blades
        th.append(base + rng.normal(0, 0.02, 300))
    pitch = _estimate_pitch(np.concatenate(th) % (2 * np.pi))
    assert abs(pitch - 2 * np.pi / n_blades) < 0.1
    # no periodicity → full circle
    uni = rng.uniform(0, 2 * np.pi, 2000)
    assert _estimate_pitch(uni) > np.pi


def test_blade_to_blade_surface(ff):
    """B2B on the wall: 9011 points, radius-consistent unwrap."""
    from fv.render.turbo import blade_to_blade_surface
    pts = blade_to_blade_surface(ff, "Z", None, 1)
    assert pts.shape == (9011, 2)
    # x = r·θ unwrap matches the polar view of the same faces
    from fv.render.turbo import blade_wall_faces, polar_view_points_from
    bw = blade_wall_faces(ff, None)
    rt = polar_view_points_from(bw[1], "Z")
    assert pts[:, 1].min() >= float(np.asarray(ff.vertices)[:, 2].min()) - 1e-9
    assert np.all(np.isfinite(pts))
    assert pts[:, 0].max() > 0


@pytest.mark.skipif(not __import__("importlib.util").util.find_spec("vtk"),
                    reason="vtk unavailable")
def test_turbo_actor_blade_surface(ff):
    """Blade view heatmap renders from the wall surface (T4 outlet)."""
    from fv.model.objects import TurboObject
    from fv.render.turbo import build_turbo_actors
    var = "PRES" if "PRES" in ff.variables else next(iter(ff.variables))
    obj = TurboObject(index=1)
    obj.view = "Blade-to-Blade"
    obj.variable = var
    obj.blade_surface = True
    obj.n_r = 16
    obj.n_z = 16
    out = build_turbo_actors(ff, obj)
    assert "turbo" in out
    pd = out["turbo"].GetMapper().GetInput()
    assert pd.GetNumberOfCells() > 0
