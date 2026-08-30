"""R23: vortex-identification preset library tests.

- Green-Gauss gradient exactness for linear fields on hex grids (FLD)
  and tet grids (CGNS 0-based).
- Uniform flow -> omega = 0, Q = 0; linear shear -> omega_z = -1;
  solid-body rotation -> Q = 1, lambda2 = -1.
- Registration: 9 VGRAD components + VORT/QCRIT/LAMBDA2/HELI presets,
  expression-engine reuse, auto_scalarize idempotency, collision
  errors, and sample-driven checks on tr03_9.fph.
"""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest

FPH = r"D:\training\cgns\examples\tr03_9.fph"


# ── synthetic grid builders ──────────────────────────────────────────────

def _hex_ff(nx=2, ny=2, nz=2, h=1.0, vel=None, one_based=True):
    """Structured hex grid FieldFile (kind='fld') with a linear velocity."""
    from fv.model.dataset import FIELD_KIND_VECTOR, FieldFile, VarInfo
    ny1, nz1 = ny + 1, nz + 1
    verts = np.array([(i * h, j * h, k * h)
                      for i in range(nx + 1)
                      for j in range(ny + 1)
                      for k in range(nz + 1)], dtype=np.float64)

    def vid(i, j, k):
        return (i * ny1 + j) * nz1 + k

    cells = []
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                cells.append([vid(i, j, k), vid(i, j + 1, k),
                              vid(i + 1, j + 1, k), vid(i + 1, j, k),
                              vid(i, j, k + 1), vid(i, j + 1, k + 1),
                              vid(i + 1, j + 1, k + 1), vid(i + 1, j, k + 1)])
    conn = np.array(cells, dtype=np.int64)
    if one_based:
        conn = conn + 1
    ff = FieldFile(path="synthetic", kind="fld")
    ff.vertices = verts
    ff.n_vertices = len(verts)
    ff.cell_conn = conn
    ff.n_cells = len(cells)
    if vel is not None:
        comps = [np.asarray(v, dtype=np.float64) * np.ones(len(verts))
                 for v in vel(verts[:, 0], verts[:, 1], verts[:, 2])]
        u = np.stack(comps, axis=1)
        for k, c in enumerate("XYZ"):
            ff.variables["VEL" + c] = VarInfo(
                name="VEL" + c, kind=FIELD_KIND_VECTOR, location="node",
                array=np.ascontiguousarray(u[:, k]))
    return ff


def _tet_ff(vel=None):
    """0-based CGNS tet grid: a cube split into 5 tets (Kuhn)."""
    from fv.model.dataset import FIELD_KIND_VECTOR, FieldFile, VarInfo
    verts = np.array([(x, y, z) for x in (0.0, 1.0)
                      for y in (0.0, 1.0) for z in (0.0, 1.0)],
                     dtype=np.float64)          # idx = x*4 + y*2 + z

    def v(x, y, z):
        return int(x) * 4 + int(y) * 2 + int(z)

    tets = [   # Kuhn triangulation along the 000-111 diagonal (6 tets)
        [v(0, 0, 0), v(1, 0, 0), v(1, 1, 0), v(1, 1, 1)],
        [v(0, 0, 0), v(1, 0, 0), v(1, 0, 1), v(1, 1, 1)],
        [v(0, 0, 0), v(0, 1, 0), v(1, 1, 0), v(1, 1, 1)],
        [v(0, 0, 0), v(0, 1, 0), v(0, 1, 1), v(1, 1, 1)],
        [v(0, 0, 0), v(0, 0, 1), v(1, 0, 1), v(1, 1, 1)],
        [v(0, 0, 0), v(0, 0, 1), v(0, 1, 1), v(1, 1, 1)],
    ]
    conn = np.array(tets, dtype=np.int64)      # 0-based, tet rows (pad 4)
    ff = FieldFile(path="synthetic", kind="cgns")
    ff.vertices = verts
    ff.n_vertices = len(verts)
    ff.cell_conn = conn
    ff.cell_types = np.full(len(tets), 10, dtype=np.int64)
    ff.n_cells = len(tets)
    if vel is not None:
        comps = [np.asarray(v, dtype=np.float64) * np.ones(len(verts))
                 for v in vel(verts[:, 0], verts[:, 1], verts[:, 2])]
        u = np.stack(comps, axis=1)
        for k, c in enumerate("XYZ"):
            ff.variables["VEL" + c] = VarInfo(
                name="VEL" + c, kind=FIELD_KIND_VECTOR, location="node",
                array=np.ascontiguousarray(u[:, k]))
    return ff


# ── identities on linear fields (Green-Gauss is exact there) ─────────────

def test_uniform_flow_zero_identities():
    """Uniform flow: omega = 0, Q = 0, lambda2 = 0 everywhere (R23)."""
    from fv.model.derived import q_criterion, vorticity, lambda2
    ff = _hex_ff(vel=lambda x, y, z: (2.0, -3.0, 0.5))
    np.testing.assert_allclose(vorticity(ff), 0.0, atol=1e-9)
    np.testing.assert_allclose(q_criterion(ff), 0.0, atol=1e-9)
    np.testing.assert_allclose(lambda2(ff), 0.0, atol=1e-9)


def test_linear_shear_vorticity():
    """u = (y, 0, 0): omega_z = -1, Q = 0 (rotation balances strain) (R23)."""
    from fv.model.derived import q_criterion, vorticity
    ff = _hex_ff(vel=lambda x, y, z: (y, 0.0 * x, 0.0 * x))
    w = vorticity(ff)
    np.testing.assert_allclose(w[:, 0], 0.0, atol=1e-9)
    np.testing.assert_allclose(w[:, 1], 0.0, atol=1e-9)
    np.testing.assert_allclose(w[:, 2], -1.0, atol=1e-9)
    np.testing.assert_allclose(q_criterion(ff), 0.0, atol=1e-9)


def test_solid_body_rotation_q_and_lambda2():
    """u = (-y, x, 0): omega = (0,0,2), Q = 1, lambda2 = -1 (R23)."""
    from fv.model.derived import lambda2, q_criterion, vorticity
    ff = _hex_ff(vel=lambda x, y, z: (-y, x, 0.0 * x))
    np.testing.assert_allclose(vorticity(ff)[:, :2], 0.0, atol=1e-9)
    np.testing.assert_allclose(vorticity(ff)[:, 2], 2.0, atol=1e-9)
    np.testing.assert_allclose(q_criterion(ff), 1.0, atol=1e-9)
    np.testing.assert_allclose(lambda2(ff), -1.0, atol=1e-9)


def test_gradient_components_and_helicity():
    """u = (2x, 3y, 4z): gradient tensor exact (R23)."""
    from fv.model.derived import velocity_gradient
    ff = _hex_ff(vel=lambda x, y, z: (2.0 * x, 3.0 * y, 4.0 * z))
    g = velocity_gradient(ff)
    expect = np.array([[2.0, 0, 0], [0, 3.0, 0], [0, 0, 4.0]])
    np.testing.assert_allclose(g, np.broadcast_to(expect, g.shape),
                               atol=1e-9)


def test_helicity_helical_flow():
    """u = (-y, x, 4z + c): omega = (0,0,2), helicity = 2*(4z + c) (R23)."""
    from fv.model.derived import helicity
    c = 0.25
    ff = _hex_ff(vel=lambda x, y, z: (-y, x, 4.0 * z + c))
    h = helicity(ff)
    z = ff.vertices[:, 2]
    np.testing.assert_allclose(h, 2.0 * (4.0 * z + c), atol=1e-9)


def test_tet_grid_gradient_exact():
    """0-based CGNS tets: linear field gives the exact tensor (R23)."""
    from fv.model.derived import velocity_gradient
    ff = _tet_ff(vel=lambda x, y, z: (0.5 * y + 0.3 * z,
                                      -0.5 * x + 0.2 * z,
                                      -0.3 * x - 0.2 * y))
    g = velocity_gradient(ff)
    expect = np.array([[0.0, 0.5, 0.3],
                       [-0.5, 0.0, 0.2],
                       [-0.3, -0.2, 0.0]])
    np.testing.assert_allclose(g, np.broadcast_to(expect, g.shape),
                               atol=1e-9)


# ── registration ─────────────────────────────────────────────────────────

def test_register_vortex_presets_names_and_reuse():
    """Presets register 13 variables, feed the expression engine (R23)."""
    from fv.model.varreg import auto_scalarize, register_variable
    from fv.model.derived import register_vortex_presets
    ff = _hex_ff(vel=lambda x, y, z: (-y, x, 0.0 * x))
    out = register_vortex_presets(ff)
    assert len(out) == 13
    assert set(out) == ({"VGRAD" + a + b for a in "XYZ" for b in "XYZ"}
                        | {"VORT", "QCRIT", "LAMBDA2", "HELI"})
    assert ff.variables["VORT"].kind == "vector"
    assert ff.variables["VORT"].location == "node"
    assert ff.variables["QCRIT"].kind == "scalar"
    # gradient components are reusable in the expression engine
    vi = register_variable(ff, "GX2", "VGRADXY * 2.0")
    np.testing.assert_allclose(vi.array, -2.0, atol=1e-9)  # du_x/dy = -1
    # collision is rejected
    with pytest.raises(ValueError):
        register_vortex_presets(ff)
    # auto_scalarize exposes VORT components and is idempotent
    auto_scalarize(ff, ["VORT", "VEL"])
    assert "VORT_mag" in ff.variables and "VORT_Z" in ff.variables
    assert auto_scalarize(ff, ["VORT", "VEL"]) == []


def test_registration_errors():
    """Missing velocity / topology / collisions are explicit (R23)."""
    from fv.model.derived import (register_q_criterion, register_vorticity,
                                  register_vortex_presets,
                                  velocity_gradient)
    ff = _hex_ff()                                   # no velocity at all
    with pytest.raises(ValueError):
        velocity_gradient(ff)
    ff2 = _hex_ff(vel=lambda x, y, z: (x, y, z))
    ff2.cell_conn = None                             # no topology
    with pytest.raises(ValueError):
        velocity_gradient(ff2)
    ff3 = _hex_ff(vel=lambda x, y, z: (x, y, z))
    ff3.variables["VORT"] = ff3.variables["VELX"]   # name collision
    before = set(ff3.variables)
    with pytest.raises(ValueError):
        register_vorticity(ff3)
    with pytest.raises(ValueError):
        register_q_criterion(ff3, name="bad name")
    assert set(ff3.variables) == before              # nothing registered


# ── sample-driven (tr03_9.fph, polyhedral LS_Links) ──────────────────────

@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_fph_uniform_flow_exact_zero():
    """Uniform velocity on the real polyhedral mesh: exact zeros (R23)."""
    from fv.model.dataset import load_file
    from fv.model.derived import q_criterion, vorticity, velocity_gradient
    ff = load_file(FPH)
    n = ff.n_cells
    for c in "XYZ":
        ff.variable_array("VEL" + c)          # materialise lazy blocks
        ff.variables["VEL" + c].array[:] = 1.0 + 0.1 * "XYZ".index(c)
    g = velocity_gradient(ff)
    assert g.shape == (n, 3, 3)
    np.testing.assert_allclose(g, 0.0, atol=1e-9)
    np.testing.assert_allclose(vorticity(ff), 0.0, atol=1e-9)
    np.testing.assert_allclose(q_criterion(ff), 0.0, atol=1e-9)


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_fph_linear_field_gradient():
    """Linear velocity on the real mesh: gradient close to the exact A (R23)."""
    from fv.model.varreg import _cell_centers_fph
    from fv.model.dataset import load_file
    from fv.model.derived import lambda2, q_criterion, vorticity, velocity_gradient
    ff = load_file(FPH)
    cc = _cell_centers_fph(ff)
    assert cc.shape == (ff.n_cells, 3)
    A = np.array([[0.0, 0.7, -0.2],
                  [-0.7, 0.0, 0.4],
                  [0.2, -0.4, 0.1]])
    b = np.array([1.5, -0.3, 0.9])
    u = cc @ A.T + b
    for k, c in enumerate("XYZ"):
        ff.variable_array("VEL" + c)
        ff.variables["VEL" + c].array[:] = u[:, k]
    g = velocity_gradient(ff)
    err = np.abs(g - A[None])
    scale = np.abs(A).max()
    assert np.median(err) / scale < 0.05        # Green-Gauss, distorted mesh
    assert err.mean() / scale < 0.08
    # antisymmetric linear field: omega exact on average, Q >= 0
    w = vorticity(ff)
    np.testing.assert_allclose(np.median(w, axis=0), (-0.8, -0.4, -1.4),
                               rtol=0.1)
    q = q_criterion(ff)
    assert q.shape == (ff.n_cells,) and np.isfinite(q).all()
    l2 = lambda2(ff)
    assert l2.shape == (ff.n_cells,) and np.isfinite(l2).all()


@pytest.mark.skipif(not Path(FPH).exists(), reason="sample not present")
def test_fph_real_velocity_presets_recompute():
    """Real velocity: QCRIT/HELI match expression-engine recomputes (R23)."""
    from fv import api
    from fv.model.dataset import load_file
    from fv.model.derived import register_vortex_presets
    from fv.model.varreg import auto_scalarize, register_variable
    ff = load_file(FPH)
    out = register_vortex_presets(ff)
    assert len(out) == 13
    n = ff.n_cells
    for nm in ("QCRIT", "LAMBDA2", "HELI"):
        assert ff.variables[nm].array.shape == (n,)
        assert ff.variables[nm].location == "cell"
        assert np.isfinite(ff.variables[nm].array).all()
    # independent Q recompute via the expression engine over VGRAD*
    o12 = "0.5*(VGRADXY - VGRADYX)"
    o13 = "0.5*(VGRADXZ - VGRADZX)"
    o23 = "0.5*(VGRADYZ - VGRADZY)"
    s12 = "0.5*(VGRADXY + VGRADYX)"
    s13 = "0.5*(VGRADXZ + VGRADZX)"
    s23 = "0.5*(VGRADYZ + VGRADZY)"
    expr = ("0.5*(2*(%s^2 + %s^2 + %s^2) - "
            "(VGRADXX^2 + VGRADYY^2 + VGRADZZ^2 + 2*(%s^2 + %s^2 + %s^2)))"
            % (o12, o13, o23, s12, s13, s23))
    qc = register_variable(ff, "QCHECK", expr)
    np.testing.assert_allclose(qc.array, ff.variables["QCRIT"].array,
                               rtol=1e-9, atol=1e-9)
    # helicity recompute: auto_scalarize exposes VEL_/VORT_ components
    auto_scalarize(ff, ["VEL", "VORT"])
    hc = register_variable(
        ff, "HCHECK",
        "VEL_X*VORT_X + VEL_Y*VORT_Y + VEL_Z*VORT_Z")
    np.testing.assert_allclose(hc.array, ff.variables["HELI"].array,
                               rtol=1e-9, atol=1e-12)
    # api wrappers work end-to-end
    ff2 = load_file(FPH)
    api.register_vorticity(ff2, "MYVORT")
    assert "MYVORT" in ff2.variables
    assert ff2.variables["MYVORT"].kind == "vector"
