"""Nastran .op2 binary result reader (pyNastran, optional dependency).

Geometry comes from the OP2 when it carries a GEOM table, else from a
same-stem .dat/.bdf/.nas sidecar (results-only POST op2 files are
common).  Result blocks mapped: displacements (per subcase) and
eigenvectors (per mode) as node-located magnitude fields; solid
element stresses (chexa/cpenta/ctetra/cpyram families) as cell-located
von Mises fields.

pyNastran is optional: the module imports defensively and callers
degrade gracefully (probe reports op2 only when importable).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    from pyNastran.bdf.bdf import read_bdf
    from pyNastran.op2.op2 import read_op2
    _HAS_PYNASTRAN = True
except Exception:  # pragma: no cover - optional dep
    read_op2 = None
    read_bdf = None
    _HAS_PYNASTRAN = False

_VTK_FOR = {
    "CTETRA4": (10, 4), "CTETRA10": (24, 10), "CHEXA8": (12, 8),
    "CHEXA20": (25, 20), "CPENTA6": (13, 6), "CPENTA15": (26, 15),
    "CPYRAM5": (14, 5), "CPYRAM13": (27, 13),
    "CTRIA3": (5, 3), "CTRIA6": (22, 6),
    "CQUAD4": (9, 4), "CQUAD8": (23, 8),
    "CROD": (3, 2), "CBAR": (3, 2), "CBEAM": (3, 2),
    "CELAS1": (3, 2), "CELAS2": (3, 2),
}


def _geometry_from_model(model):
    """nodes/elements of a pyNastran model -> (verts, nid_map, conn, types)."""
    nodes = getattr(model, "nodes", None)
    elements = getattr(model, "elements", None)
    if not nodes or not elements:
        return None
    nid_map = {int(nid): i for i, nid in enumerate(sorted(nodes))}
    vertices = np.zeros((len(nodes), 3))
    for i, nid in enumerate(sorted(nodes)):
        g = nodes[nid]
        xyz = getattr(g, "xyz", None)
        if xyz is None:
            xyz = getattr(g, "xyz_cid0", None)
        if xyz is not None:
            vertices[i] = np.asarray(xyz, dtype=np.float64)[:3]
    conns = []
    types = []
    for _eid, el in sorted(elements.items()):
        info = _VTK_FOR.get(str(getattr(el, "type", "")).upper())
        if info is None:
            continue
        vtk_t, nn = info
        enodes = [int(n) for n in getattr(el, "nodes", [])][:nn]
        ids = [nid_map.get(n, -1) for n in enodes]
        if -1 in ids or len(ids) < nn:
            continue
        conns.append(np.asarray(ids, dtype=np.int64))
        types.append(vtk_t)
    if not conns:
        return None
    width = max(len(a) for a in conns)
    cell_conn = np.full((len(conns), width), -1, dtype=np.int64)
    for i, a in enumerate(conns):
        cell_conn[i, :len(a)] = a
    return (vertices, nid_map, cell_conn, np.asarray(types, dtype=np.int64))


def _read_bdf_sidecar(path):
    """Same-stem .dat/.bdf/.nas geometry via pyNastran, or None."""
    if read_bdf is None:
        return None
    p = Path(path)
    for suf in (".dat", ".bdf", ".nas"):
        cand = p.with_suffix(suf)
        if cand.exists():
            try:
                return read_bdf(str(cand), debug=None)
            except Exception:
                continue
    return None


def _node_field(arr_data, node_gridtype, nid_map, n_nodes):
    """Map a (nodes, 3+) result array onto the full node index space."""
    d = np.asarray(arr_data, dtype=np.float64)
    if d.ndim == 2 and d.shape[1] >= 3:
        rows = [d]
    elif d.ndim == 3:
        rows = [d[i] for i in range(d.shape[0])]
    else:
        return None
    ng = None
    if node_gridtype is not None:
        ng = np.asarray(node_gridtype, dtype=np.int64).reshape(-1, 2)
    out = []
    for r in rows:
        full = np.zeros(n_nodes)
        mag = np.linalg.norm(r[:, :3], axis=1)
        if ng is not None and ng.shape[0] == mag.size:
            for j in range(mag.size):
                idx = nid_map.get(int(ng[j, 0]))
                if idx is not None:
                    full[idx] = mag[j]
        elif mag.size == n_nodes:
            full = mag
        else:
            continue
        out.append(full)
    return out or None


def _von_mises(data, names):
    want = ("oxx", "oyy", "ozz", "txy", "tyz", "tzx")
    cols = []
    for w in want:
        try:
            idx = list(names).index(w)
        except (ValueError, TypeError):
            return None
        cols.append(data[:, idx])
    sxx, syy, szz, txy, tyz, tzx = cols
    return np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2
                          + (szz - sxx) ** 2
                          + 6 * (txy ** 2 + tyz ** 2 + tzx ** 2)))


def _fields_from_op2(model, nid_map, n_nodes, n_cells):
    fields = {}
    ev = getattr(model, "eigenvectors", None) or {}
    for sub, arr in ev.items():
        frames = _node_field(getattr(arr, "data", None),
                             getattr(arr, "node_gridtype", None),
                             nid_map, n_nodes)
        if not frames:
            continue
        for mi, full in enumerate(frames):
            fields[f"MODE{mi + 1}"] = (full, "node")
    disp = getattr(model, "displacements", None) or {}
    for sub, arr in disp.items():
        frames = _node_field(getattr(arr, "data", None),
                             getattr(arr, "node_gridtype", None),
                             nid_map, n_nodes)
        if frames:
            fields[f"DISPMAG(SUB{sub})"] = (frames[0], "node")
    # solid stress families (op2_results.stress.* in pyNastran >= 1.4)
    res = getattr(model, "op2_results", None)
    stress = getattr(res, "stress", None) if res is not None else None
    for fam in ("chexa_stress", "cpenta_stress", "ctetra_stress",
                "cpyram_stress", "ctetrar_stress"):
        cases = getattr(stress, fam, None) if stress is not None else None
        if not isinstance(cases, dict):
            continue
        for sub, arr in cases.items():
            d = getattr(arr, "data", None)
            names = getattr(arr, "data_dtype", None)
            if d is None or names is None:
                continue
            d = np.asarray(d, dtype=np.float64)
            if hasattr(names, "names"):
                names = names.names
            if d.ndim == 3:  # (elements, nodes, ndof) → centre node
                d = d[:, 0, :]
            vm = _von_mises(d, names)
            if vm is not None and vm.size:
                fields[f"VONMISES(SUB{sub})"] = (vm[:n_cells], "cell")
    return fields


def parse_op2(path):
    """Read an .op2 (plus optional .dat sidecar) into the mesh-dict shape."""
    if not _HAS_PYNASTRAN:
        return None
    try:
        model = read_op2(path, load_geometry=True, debug=None,
                         build_dataframe=False)
    except Exception:
        return None
    if model is None:
        return None
    geom = _geometry_from_model(model)
    if geom is None:
        bdf = _read_bdf_sidecar(path)
        geom = _geometry_from_model(bdf) if bdf is not None else None
    if geom is None:
        return None
    vertices, nid_map, cell_conn, cell_types = geom
    fields = _fields_from_op2(model, nid_map,
                              int(vertices.shape[0]),
                              int(cell_conn.shape[0]))
    return {
        "vertices": vertices,
        "cell_conn": cell_conn,
        "cell_types": cell_types,
        "n_vertices": int(vertices.shape[0]),
        "n_cells": int(cell_conn.shape[0]),
        "fields": fields,
        "surface_regions": [],
        "volume_regions": [],
        "op2": True,
    }
