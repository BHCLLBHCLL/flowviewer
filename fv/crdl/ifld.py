"""iFLD lightweight metadata scan (D3).

iFLD shares the CRDL container; scanning reads only the section index and
the small descriptor blocks, never the full field payloads - the local/
trimming-read building block.  Returns counts + variable names.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .core import (find_section, iter_data_blocks, open_buffer,
                   read_i32_be, section_end)

def scan_ifld(path: str):
    """Quick metadata scan of an iFLD/FLD file (D3)."""
    try:
        with open_buffer(path) as data:
            return _scan(data)
    except Exception:
        return None


def _scan(data) -> dict:
    n_cells = 0
    sec = find_section(data, "LS_MatOfElements")
    if sec >= 0:
        for p, bc in iter_data_blocks(data, sec, section_end(data, sec)):
            if bc > 0 and bc % 4 == 0:
                n_cells = bc // 4
                break
    n_vertices = 0
    sec = find_section(data, "LS_Nodes")
    if sec >= 0:
        for p, bc in iter_data_blocks(data, sec, section_end(data, sec)):
            if bc in (4, 8):
                continue
            if bc > n_vertices:
                n_vertices = bc
    variables = []
    for name in ("Pressure", "Temperature", "CN01", "VECT", "HVEC"):
        if find_section(data, name) >= 0:
            variables.append(name)
    return {
        "n_cells": n_cells,
        "n_vertices": n_vertices,
        "variables": variables,
        "file_size": len(data),
    }


# ── Trimming Open: spatially partial load (P2.6) ────────────────────────

def trim_fld_mesh(mesh: dict, bounds) -> dict:
    """Spatially trim a parsed FLD mesh dict to an axis-aligned box.

    ``bounds`` is ``(xmin, xmax, ymin, ymax, zmin, zmax)``.  Vertices
    inside the box are kept together with the cells and faces whose
    nodes all survive; connectivity, per-node fields, the BC plan and
    the face->cell map are compacted and re-indexed (keeping the
    original 0/1-based node id convention).  ``meta["ifld_trim"]``
    records the bounds and kept counts.  Raises ValueError for a
    missing mesh, an inverted box or an empty result.
    """
    verts = mesh.get("vertices")
    if verts is None or not getattr(verts, "size", 0):
        raise ValueError("trimming needs FLD mesh vertices")
    xmin, xmax, ymin, ymax, zmin, zmax = (float(b) for b in bounds)
    if xmin > xmax or ymin > ymax or zmin > zmax:
        raise ValueError("inverted trim box: %r" % (bounds,))
    inside = ((verts[:, 0] >= xmin) & (verts[:, 0] <= xmax)
              & (verts[:, 1] >= ymin) & (verts[:, 1] <= ymax)
              & (verts[:, 2] >= zmin) & (verts[:, 2] <= zmax))
    keep_v = np.flatnonzero(inside)
    if not keep_v.size:
        raise ValueError("trim box contains no vertices")
    n_all = int(verts.shape[0])
    n_declared = int(mesh.get("n_vertices") or 0) or n_all
    remap = np.full(n_all, -1, dtype=np.int64)
    remap[keep_v] = np.arange(keep_v.size, dtype=np.int64)
    out = dict(mesh)
    out["vertices"] = verts[keep_v]
    out["n_vertices"] = int(keep_v.size)

    # cells: keep rows whose (non-padding) nodes all survived
    conn = mesh.get("cell_conn")
    cell_remap = None
    base = 0
    if conn is not None and getattr(conn, "size", 0):
        valid = conn[conn >= 0]
        base = 1 if (valid.size and valid.min() > 0
                     and valid.max() >= n_declared) else 0
        c0 = np.where(conn >= 0, conn - base, -1)
        in_rng = c0 >= 0
        node_ok = np.where(in_rng, inside[np.clip(c0, 0, n_all - 1)],
                           True)
        keep_c = node_ok.all(axis=1) & in_rng.any(axis=1)
        cell_remap = np.full(conn.shape[0], -1, dtype=np.int64)
        cell_remap[np.flatnonzero(keep_c)] = np.arange(
            int(keep_c.sum()), dtype=np.int64)
        new_ids = np.where(in_rng,
                           remap[np.clip(c0, 0, n_all - 1)] + base, -1)
        out["cell_conn"] = new_ids[keep_c]
        ct = mesh.get("cell_types")
        if ct is not None:
            out["cell_types"] = np.asarray(ct)[keep_c]
        mat = mesh.get("material")
        if mat is not None:
            out["material"] = np.asarray(mat)[keep_c]
        out["n_cells"] = int(keep_c.sum())

    # faces + BC plan + face->cell ownership
    faces = list(mesh.get("faces") or [])
    total_faces = len(faces)
    kept_idx = []
    if faces:
        for i, f in enumerate(faces):
            ids = [int(v) - base for v in f] if conn is not None else None
            if ids is None or not ids:
                continue
            if all(0 <= j < n_all and inside[j] for j in ids):
                kept_idx.append((i, tuple(remap[j] + base for j in ids)))
        out["faces"] = [t for _, t in kept_idx]
        if cell_remap is None:
            out["face_cells"] = np.full(len(kept_idx), -1, dtype=np.int64)
        else:
            fc = mesh.get("face_cells")
            if fc is not None and len(fc):
                out["face_cells"] = np.asarray(
                    [cell_remap[int(fc[i])] if 0 <= int(fc[i])
                     < len(cell_remap) else -1 for i, _ in kept_idx],
                    dtype=np.int64)
        kept_set = {i for i, _ in kept_idx}
        new_bp = []
        pos = 0
        for name, start, cnt in (mesh.get("bc_plan") or []):
            k = sum(1 for i in range(int(start), int(start) + int(cnt))
                    if i in kept_set)
            new_bp.append((name, pos, k))
            pos += k
        out["bc_plan"] = new_bp

    # per-node solution fields
    fields = {}
    for name, arr in (mesh.get("fields") or {}).items():
        a = np.asarray(arr)
        fields[name] = a[keep_v] if a.ndim == 1 and a.size == n_all else a
    out["fields"] = fields

    meta = dict(mesh.get("meta") or {})
    meta["ifld_trim"] = {
        "bounds": (xmin, xmax, ymin, ymax, zmin, zmax),
        "total_vertices": n_all, "kept_vertices": int(keep_v.size),
        "total_cells": int(mesh.get("n_cells") or 0),
        "kept_cells": int(out.get("n_cells") or 0),
        "total_faces": total_faces,
        "kept_faces": len(out.get("faces") or []),
    }
    out["meta"] = meta
    return out
