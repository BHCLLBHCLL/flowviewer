"""Vortex-identification preset library (R23).

Computes the velocity-gradient tensor with a Green-Gauss kernel over
the file's own mesh topology, then derives the standard vortex
identification quantities on top:

- vorticity        ω = ∇×u                          (vector)
- Q-criterion      Q = ½(‖Ω‖² − ‖S‖²)               (scalar)
- lambda2          λ₂ = middle eigenvalue of S²+Ω²  (scalar)
- helicity         H = u·ω                          (scalar)

Topology handling:

- FPH/GPH/PPH (polyhedral LS_Links): cell-centred fields, face-based
  Green-Gauss over owner/neighbour faces; face area vectors via the
  Newell polygon formula with per-face orientation fix; cell volumes
  from the divergence theorem.  Output stays cell-centred.
- FLD/CGNS (cell_conn hex/tet/penta/pyra): node-centred fields, per-cell
  Green-Gauss from face-averaged vertex values, then volume-weighted
  averaging back onto the vertices.  Output stays node-centred.

The kernel is exact for linear fields on any (non-degenerate) mesh,
which the regression tests exploit: uniform flow → ω=0, Q=0; linear
shear u=(y,0,0) → ω_z=−1.

Gradient components are also registrable as nine scalars
VGRADXX..VGRADZZ (VGRAD<i><j> = ∂u_i/∂x_j) so they can feed the
expression engine (varreg) like any other variable.
"""

from __future__ import annotations

import numpy as np

from .dataset import FIELD_KIND_SCALAR, FIELD_KIND_VECTOR, VarInfo
from .varreg import _base_location, _cell_centers_fph, _resolved_vars

# face node tables per vtk cell type (R23), consistent with varreg's
# _CELL_EDGES topology (any winding works: orientation is fixed per
# face from geometry, see _conn_cell_faces).
_CELL_FACES = {
    12: ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),        # HEXA_8
         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)),
    10: ((0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)),      # TETRA_4
    13: ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3),               # PENTA_6
         (1, 2, 5, 4), (2, 0, 3, 5)),
    14: ((0, 3, 2, 1), (0, 1, 4), (1, 2, 4),               # PYRA_5
         (2, 3, 4), (3, 0, 4)),
}

_VOL_EPS = 1e-30   # degenerate-volume guard


# ── field access ─────────────────────────────────────────────────────────

def _field(ff, base: str) -> np.ndarray:
    """Resolved (n,3) velocity (or other vector base) array."""
    resolved = _resolved_vars(ff)
    if base in resolved and np.asarray(resolved[base]).ndim == 2:
        return np.ascontiguousarray(resolved[base], dtype=np.float64)
    raise ValueError(
        "vortex presets need a vector variable %r (component triplet "
        "or (n,3) base) on this file" % base)


def _field_location(ff, base: str) -> str:
    return _base_location(ff, base)


# ── FPH: vectorised face geometry from LS_Links ──────────────────────────

def _fph_face_geometry(ff):
    """Per-face raw Newell area vector + centroid from LS_Links.

    Returns (n_faces,3) raw areas (winding-dependent sign) and
    (n_faces,3) centroids, fully vectorised.
    """
    ld = ff.link_data
    fn = np.asarray(ld["face_nodes"], dtype=np.int64)
    off = np.asarray(ld["face_offsets"], dtype=np.int64)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    n_faces = len(off) - 1
    counts = (off[1:] - off[:-1]).astype(np.int64)
    fid = np.repeat(np.arange(n_faces, dtype=np.int64), counts)
    starts = np.repeat(off[:-1], counts)
    pos = np.arange(fn.size, dtype=np.int64) - starts
    nxt = starts + (pos + 1) % np.repeat(counts, counts)
    p = verts[fn]
    q = verts[fn[nxt]]
    cross = np.cross(p, q)
    areas = np.empty((n_faces, 3), dtype=np.float64)
    for k in range(3):
        areas[:, k] = np.bincount(fid, weights=cross[:, k],
                                  minlength=n_faces)
    areas *= 0.5
    fcent = np.empty((n_faces, 3), dtype=np.float64)
    for k in range(3):
        fcent[:, k] = np.bincount(fid, weights=p[:, k],
                                  minlength=n_faces)
    fcent /= np.maximum(counts, 1)[:, None]
    return areas, fcent


def _fph_green_gauss(ff, phi: np.ndarray) -> np.ndarray:
    """Green-Gauss gradient of a cell-centred field on an FPH mesh.

    phi: (n_cells,) or (n_cells,3).  Returns (n_cells,3) or
    (n_cells,3,3) with g[..., i, j] = ∂phi_i/∂x_j.
    """
    dim = 1 if phi.ndim == 1 else phi.shape[1]
    n_cells = int(ff.n_cells)
    ld = ff.link_data
    owner = np.asarray(ld["owner"], dtype=np.int64)
    neigh = np.asarray(ld["neighbour"], dtype=np.int64)
    areas, fcent = _fph_face_geometry(ff)
    centers = _cell_centers_fph(ff)
    if centers is None or centers.shape[0] != n_cells:
        raise ValueError("cannot compute cell centres for the gradient")

    # orient each face outward from its "primary" cell (owner if valid,
    # else neighbour) using the geometry sign fix
    prim = np.where(owner >= 0, owner, neigh)
    internal = (owner >= 0) & (neigh >= 0)
    ref = np.where(internal[:, None],
                   centers[neigh] - centers[owner],
                   fcent - centers[prim])
    dot = (areas * ref).sum(axis=1)
    s = np.where(dot >= 0.0, 1.0, -1.0)
    S = s[:, None] * areas                     # outward from primary
    n_sign = np.where(owner >= 0, -1.0, 1.0)   # neighbour side sign

    # face value: distance-weighted interpolation on internal faces
    # (exact for linear fields when the face centre lies on the o-n
    # segment; more accurate than the plain midpoint on distorted
    # meshes), boundary faces take the primary cell value
    phi_f = np.zeros((len(S), dim), dtype=np.float64)
    if internal.any():
        oi, ni = owner[internal], neigh[internal]
        d_o = np.linalg.norm(fcent[internal] - centers[oi], axis=1)
        d_n = np.linalg.norm(fcent[internal] - centers[ni], axis=1)
        w = d_o + d_n
        w = np.where(w < 1e-30, 1.0, w)
        phi_f[internal] = (d_n[:, None] * phi[oi]
                           + d_o[:, None] * phi[ni]) / w[:, None]
    ob = (owner >= 0) & ~internal
    if ob.any():
        phi_f[ob] = phi[owner[ob]]
    nb = (owner < 0) & (neigh >= 0)
    if nb.any():
        phi_f[nb] = phi[neigh[nb]]

    vol = np.zeros(n_cells, dtype=np.float64)
    cfs = (fcent * S).sum(axis=1) / 3.0
    ov, nv = owner >= 0, neigh >= 0
    np.add.at(vol, owner[ov], cfs[ov])
    np.add.at(vol, neigh[nv], cfs[nv] * n_sign[nv])

    gsum = np.zeros((n_cells, dim, 3), dtype=np.float64)
    contrib = phi_f[:, :, None] * S[:, None, :]
    np.add.at(gsum, owner[ov], contrib[ov])
    np.add.at(gsum, neigh[nv],
              contrib[nv] * n_sign[nv][:, None, None])

    good = vol > _VOL_EPS
    out = np.zeros_like(gsum)
    out[good] = gsum[good] / vol[good, None, None]
    return out


# ── FLD/CGNS: per-cell Green-Gauss then vertex averaging ────────────────

def _conn_offset(ff, conn, types):
    """0/1 base detection shared with varreg's adjacency builder."""
    valid = conn[conn >= 0]
    if valid.size == 0:
        raise ValueError("element connectivity has no valid node ids")
    n_vertices = int(getattr(ff, "n_vertices", 0)) or int(conn.max()) + 1
    offset = 0
    if valid.min() > 0 and valid.max() >= n_vertices:
        offset = 1
    shifted = valid - offset
    if shifted.min() < 0 or shifted.max() >= n_vertices:
        raise ValueError(
            "connectivity/vertex mismatch: node ids span [%d, %d] but "
            "the mesh has %d vertices"
            % (int(valid.min()), int(valid.max()), n_vertices))
    return offset


def _conn_green_gauss_node(ff, phi: np.ndarray) -> np.ndarray:
    """Green-Gauss gradient of a node-centred field on an FLD/CGNS mesh.

    Per-cell gradient from face-averaged vertex values, then the cell
    gradients are averaged onto the vertices.  phi: (n_vertices,) or
    (n_vertices,3); output (n_vertices,3) or (n_vertices,3,3).
    """
    conn = ff.cell_conn
    if conn is None:
        raise ValueError(
            "gradient presets need element connectivity "
            "(LS_Elements/cell_conn) on this file")
    conn = np.asarray(conn, dtype=np.int64)
    if conn.ndim != 2 or conn.shape[0] == 0:
        raise ValueError("element connectivity is empty")
    types = getattr(ff, "cell_types", None)
    if types is None:
        types = np.full(conn.shape[0], 12, dtype=np.int64)  # FLD hex8
    types = np.asarray(types, dtype=np.int64)
    bad = set(int(t) for t in np.unique(types)) - set(_CELL_FACES)
    if bad:
        raise ValueError(
            "unsupported cell type(s) %s for gradient presets "
            "(supported: hexa/penta/pyra/tetra)"
            % sorted(int(t) for t in bad))
    offset = _conn_offset(ff, conn, types)
    verts = np.asarray(ff.vertices, dtype=np.float64)
    dim = 1 if phi.ndim == 1 else phi.shape[1]
    n_vertices = verts.shape[0]

    gsum = np.zeros((n_vertices, dim, 3), dtype=np.float64)
    count = np.zeros(n_vertices, dtype=np.float64)
    for row, t in zip(conn, types):
        ids = np.asarray(row, dtype=np.int64)
        ids = ids[ids >= 0] - offset
        if ids.size < 3:
            continue
        pv = verts[ids]
        pf = phi[ids]
        cc = pv.mean(axis=0)
        cg = np.zeros((dim, 3), dtype=np.float64)
        vol = 0.0
        ok = True
        for face in _CELL_FACES[int(t)]:
            if max(face) >= ids.size:
                ok = False       # row narrower than this type needs
                break
            fp = pv[list(face)]
            fv = pf[list(face)]
            nxt = np.roll(fp, -1, axis=0)
            S = 0.5 * np.cross(fp, nxt).sum(axis=0)
            fc = fp.mean(axis=0)
            s = 1.0 if (S @ (fc - cc)) >= 0.0 else -1.0
            S = s * S           # outward from the cell
            cg += np.outer(fv.mean(axis=0), S)
            vol += (fc @ S) / 3.0
        if not ok or abs(vol) <= _VOL_EPS:
            continue            # skip degenerate cells (R23 scope)
        cg /= vol
        gsum[ids] += cg
        count[ids] += 1.0
    hit = count > 0
    out = np.zeros_like(gsum)
    out[hit] = gsum[hit] / count[hit, None, None]
    return out


# ── public kernel ────────────────────────────────────────────────────────

def velocity_gradient(ff, base: str = "VEL") -> np.ndarray:
    """Gradient tensor ∇u of a vector base: (n,3,3), g[:, i, j] = ∂u_i/∂x_j.

    Location follows the source field: cell-centred on polyhedral
    LS_Links meshes (FPH), node-centred on cell_conn meshes (FLD/CGNS).
    """
    phi = _field(ff, base)
    n = phi.shape[0]
    if ff.poly:
        if ff.link_data is None:
            raise ValueError(
                "polyhedral file is missing LS_Links topology for gradients")
        if n != int(ff.n_cells):
            raise ValueError(
                "vector %r has %d values but the mesh has %d cells"
                % (base, n, int(ff.n_cells)))
        return _fph_green_gauss(ff, phi)
    if n == int(ff.n_vertices):
        return _conn_green_gauss_node(ff, phi)
    raise ValueError(
        "gradient presets support cell fields on polyhedral meshes and "
        "node fields on cell_conn meshes; vector %r has %d values "
        "(cells=%d, vertices=%d)"
        % (base, n, int(ff.n_cells), int(ff.n_vertices)))


# ── vortex quantities (pure functions of the gradient tensor) ────────────

def vorticity_tensor(g: np.ndarray) -> np.ndarray:
    """ω = ∇×u from the gradient tensor g[:, i, j] = ∂u_i/∂x_j → (n,3)."""
    return np.stack([
        g[:, 2, 1] - g[:, 1, 2],
        g[:, 0, 2] - g[:, 2, 0],
        g[:, 1, 0] - g[:, 0, 1],
    ], axis=1)


def q_criterion_tensor(g: np.ndarray) -> np.ndarray:
    """Q = ½(‖Ω‖² − ‖S‖²), Ω/S the antisymmetric/symmetric parts of ∇u."""
    gt = np.transpose(g, (0, 2, 1))
    sym = 0.5 * (g + gt)
    anti = 0.5 * (g - gt)
    s2 = (sym * sym).sum(axis=(1, 2))
    a2 = (anti * anti).sum(axis=(1, 2))
    return 0.5 * (a2 - s2)


def lambda2_tensor(g: np.ndarray) -> np.ndarray:
    """λ₂: middle eigenvalue of S² + Ω² (Jeong & Hussain, 1995)."""
    gt = np.transpose(g, (0, 2, 1))
    sym = 0.5 * (g + gt)
    anti = 0.5 * (g - gt)
    m = sym @ sym + anti @ anti
    eig = np.linalg.eigvalsh(m)      # ascending
    return eig[:, 1]


def vorticity(ff, base: str = "VEL") -> np.ndarray:
    return vorticity_tensor(velocity_gradient(ff, base))


def q_criterion(ff, base: str = "VEL") -> np.ndarray:
    return q_criterion_tensor(velocity_gradient(ff, base))


def lambda2(ff, base: str = "VEL") -> np.ndarray:
    return lambda2_tensor(velocity_gradient(ff, base))


def helicity(ff, base: str = "VEL") -> np.ndarray:
    u = _field(ff, base)
    return (vorticity_tensor(velocity_gradient(ff, base)) * u).sum(axis=1)


# ── registration (scPOST CreateVar-style presets, R23) ──────────────────

_GRAD_COMPS = ("XX", "XY", "XZ", "YX", "YY", "YZ", "ZX", "ZY", "ZZ")


def _register(ff, name, kind, location, array) -> VarInfo:
    if not name or not name.isidentifier():
        raise ValueError("invalid variable name: " + repr(name))
    if name in ff.variables:
        raise ValueError("variable already exists: " + repr(name))
    vi = VarInfo(name=name, kind=kind, location=location,
                 array=np.asarray(array, dtype=np.float64))
    ff.variables[name] = vi
    return vi


def register_velocity_gradient(ff, base: str = "VEL",
                               prefix: str = "VGRAD") -> list:
    """Register the nine gradient components as scalars (R23).

    VGRAD<i><j> = ∂u_i/∂x_j, e.g. VGRADXY = ∂u_x/∂y.  The components
    are ordinary scalar variables usable in the expression engine.
    """
    g = velocity_gradient(ff, base)
    loc = _field_location(ff, base)
    out = []
    for i, a in enumerate("XYZ"):
        for j, b in enumerate("XYZ"):
            out.append(_register(ff, prefix + a + b,
                                 FIELD_KIND_SCALAR, loc, g[:, i, j]))
    return out


def register_vorticity(ff, name: str = "VORT",
                       base: str = "VEL") -> VarInfo:
    """Register the vorticity vector ω = ∇×u (R23)."""
    w = vorticity_tensor(velocity_gradient(ff, base))
    return _register(ff, name, FIELD_KIND_VECTOR,
                     _field_location(ff, base), w)


def register_q_criterion(ff, name: str = "QCRIT",
                         base: str = "VEL") -> VarInfo:
    """Register the Q-criterion scalar (R23)."""
    q = q_criterion_tensor(velocity_gradient(ff, base))
    return _register(ff, name, FIELD_KIND_SCALAR,
                     _field_location(ff, base), q)


def register_lambda2(ff, name: str = "LAMBDA2",
                     base: str = "VEL") -> VarInfo:
    """Register the λ₂ vortex-core scalar (R23)."""
    l2 = lambda2_tensor(velocity_gradient(ff, base))
    return _register(ff, name, FIELD_KIND_SCALAR,
                     _field_location(ff, base), l2)


def register_helicity(ff, name: str = "HELI",
                      base: str = "VEL") -> VarInfo:
    """Register the helicity scalar u·ω (R23)."""
    h = helicity(ff, base)
    return _register(ff, name, FIELD_KIND_SCALAR,
                     _field_location(ff, base), h)


def register_vortex_presets(ff, base: str = "VEL",
                            prefix: str = "VGRAD") -> dict:
    """Register all R23 vortex presets for one vector base (R23).

    VGRADXX..VGRADZZ (9 scalars) + VORT (vector) + QCRIT + LAMBDA2 +
    HELI.  Returns {name: VarInfo}; name collisions raise ValueError
    so the whole call is transactional: compute first, register last.
    """
    g = velocity_gradient(ff, base)
    u = _field(ff, base)
    loc = _field_location(ff, base)
    out: dict = {}
    for i, a in enumerate("XYZ"):
        for j, b in enumerate("XYZ"):
            nm = prefix + a + b
            out[nm] = _register(ff, nm, FIELD_KIND_SCALAR, loc, g[:, i, j])
    w = vorticity_tensor(g)
    out["VORT"] = _register(ff, "VORT", FIELD_KIND_VECTOR, loc, w)
    out["QCRIT"] = _register(ff, "QCRIT", FIELD_KIND_SCALAR, loc,
                             q_criterion_tensor(g))
    out["LAMBDA2"] = _register(ff, "LAMBDA2", FIELD_KIND_SCALAR, loc,
                               lambda2_tensor(g))
    out["HELI"] = _register(ff, "HELI", FIELD_KIND_SCALAR, loc,
                            (w * u).sum(axis=1))
    return out
