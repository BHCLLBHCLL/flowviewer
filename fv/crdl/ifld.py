"""iFLD lightweight metadata scan (D3).

iFLD shares the CRDL container; scanning reads only the section index and
the small descriptor blocks, never the full field payloads - the local/
trimming-read building block.  Returns counts + variable names.
"""

from __future__ import annotations

import numpy as np

from .core import find_section, iter_data_blocks, open_buffer, section_end


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
    from .mesh_fld import _trim_faces, _trim_indices
    verts = mesh.get("vertices")
    if verts is None or not getattr(verts, "size", 0):
        raise ValueError("trimming needs FLD mesh vertices")
    n_all = int(verts.shape[0])
    n_declared = int(mesh.get("n_vertices") or 0) or n_all
    conn = mesh.get("cell_conn")
    has_conn = conn is not None and getattr(conn, "size", 0)
    keep_v, remap, base, keep_c, cell_remap, inside = _trim_indices(
        verts, conn, bounds, n_declared)
    out = dict(mesh)
    out["vertices"] = verts[keep_v]
    out["n_vertices"] = int(keep_v.size)

    if has_conn and keep_c is not None:
        c0 = np.where(conn >= 0, conn - base, -1)
        new_ids = np.where(c0 >= 0,
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
    total_faces = len(list(mesh.get("faces") or []))
    if total_faces:
        nf, nfc, nbp, _ = _trim_faces(
            mesh.get("faces"), mesh.get("face_cells"), mesh.get("bc_plan"),
            base, inside, remap, n_all, has_conn, cell_remap)
        out["faces"] = nf
        out["face_cells"] = nfc
        out["bc_plan"] = nbp

    # per-node solution fields
    fields = {}
    for name, arr in (mesh.get("fields") or {}).items():
        a = np.asarray(arr)
        fields[name] = a[keep_v] if a.ndim == 1 and a.size == n_all else a
    out["fields"] = fields

    meta = dict(mesh.get("meta") or {})
    meta["ifld_trim"] = {
        "bounds": tuple(bounds),
        "total_vertices": n_all, "kept_vertices": int(keep_v.size),
        "total_cells": int(mesh.get("n_cells") or 0),
        "kept_cells": int(out.get("n_cells") or 0),
        "total_faces": total_faces,
        "kept_faces": len(out.get("faces") or []),
    }
    out["meta"] = meta
    return out
