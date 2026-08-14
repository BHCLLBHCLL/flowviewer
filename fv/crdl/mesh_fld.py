"""FLD (CRDL-FLD) binary mesh + solution parser.

FLD shares the CRDL-FLD container with GPH, but stores hex cell
connectivity, per-vertex solution fields, and surface BC metadata instead
of polyhedral LS_Links topology.

Converged from the tested decoder ``fld_model.py`` (DEV_PLAN.md R2).

Public entry point: :func:`parse_fld`.
"""

from typing import Any, Optional

import numpy as np

from .core import (
    find_section,
    section_end,
    iter_data_blocks,
    read_i32_be,
    open_buffer,
)


def _parse_ls_nodes(data) -> tuple[Optional[np.ndarray], int]:
    sec_start = find_section(data, "LS_Nodes")
    if sec_start < 0:
        return None, 0
    sec_end = section_end(data, sec_start)
    f64_blocks = [(p, bc) for p, bc in iter_data_blocks(data, sec_start, sec_end)
                  if bc >= 8 and bc % 8 == 0]
    if len(f64_blocks) < 3:
        return None, 0
    sizes = [bc for _, bc in f64_blocks]
    target = max(set(sizes), key=sizes.count)
    trio = [(p, bc) for p, bc in f64_blocks if bc == target][:3]
    if len(trio) < 3:
        return None, 0
    n_vertices = trio[0][1] // 8
    axes = [
        np.frombuffer(data, dtype=">f8", count=n_vertices, offset=p)
        .astype(np.float64).copy()
        for p, _ in trio
    ]
    return np.column_stack(axes), n_vertices


def _parse_hex_cells(data) -> tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """Return ``(cell_conn (n_cells, 8), material_id (n_cells,))``."""
    sec_mat = find_section(data, "LS_MatOfElements")
    sec_elem = find_section(data, "LS_Elements")
    if sec_mat < 0 or sec_elem < 0:
        return None, None
    mat_blocks = list(iter_data_blocks(data, sec_mat, section_end(data, sec_mat)))
    elem_blocks = list(iter_data_blocks(data, sec_elem, section_end(data, sec_elem)))
    if not mat_blocks or not elem_blocks:
        return None, None
    mat = np.frombuffer(
        data, dtype=">i4", count=mat_blocks[0][1] // 4, offset=mat_blocks[0][0],
    ).astype(np.int64).copy()
    n_cells = mat.size
    conn_p, conn_bc = max(elem_blocks, key=lambda b: b[1])
    if conn_bc != n_cells * 32:
        return None, None
    conn = np.frombuffer(
        data, dtype=">i4", count=conn_bc // 4, offset=conn_p,
    ).astype(np.int64).copy()
    if conn.size % 8 != 0:
        return None, None
    return conn.reshape(-1, 8), mat


def _f64_field_blocks(data, section_name: str) -> list[np.ndarray]:
    """Return all float64 payload arrays in a named field section."""
    sec_start = find_section(data, section_name)
    if sec_start < 0:
        return []
    sec_end = section_end(data, sec_start)
    out: list[np.ndarray] = []
    for p, bc in iter_data_blocks(data, sec_start, sec_end):
        if bc >= 8 and bc % 8 == 0:
            out.append(
                np.frombuffer(data, dtype=">f8", count=bc // 8, offset=p)
                .astype(np.float64).copy()
            )
    return out


def _parse_volume_names(data) -> list[str]:
    sec_start = find_section(data, "LS_VolumeGeometryArray")
    if sec_start < 0:
        return []
    sec_end = section_end(data, sec_start)
    for p, bc in iter_data_blocks(data, sec_start, sec_end):
        raw = data[p : p + bc]
        if bc >= 256 and all(b == 0 or 32 <= b < 127 for b in raw):
            slot_names: list[str] = []
            for off in range(0, bc, 256):
                chunk = raw[off : off + 256]
                text = chunk.split(b"\x00")[0].decode("ascii", errors="replace").strip()
                if text:
                    slot_names.append(text)
            if slot_names:
                return slot_names
            text = raw.decode("ascii", errors="replace").strip("\x00").rstrip()
            if text:
                names = [s.strip() for s in text.split() if s.strip()]
                if names:
                    return names
    return []


def _filter_by_mat(quads, arr3_slice: np.ndarray, mat: np.ndarray, material: int):
    return [
        quads[i] for i in range(len(quads))
        if mat[int(arr3_slice[i]) - 1] == material
    ]


def _build_face_list_and_bcs(data, mat: np.ndarray):
    """Build the NGON face list and BC index ranges.

    Returns ``(faces, bc_plan)`` where each BC entry is
    ``(name, start_index_0based, count)`` into *faces*.
    """
    sec_start = find_section(data, "LS_SurfaceGeometryArray")
    if sec_start < 0:
        return [], []
    sec_end = section_end(data, sec_start)
    blocks = list(iter_data_blocks(data, sec_start, sec_end))
    if len(blocks) < 6:
        return [], []

    meta1 = [
        read_i32_be(data, blocks[1][0] + i * 4)
        for i in range(min(18, blocks[1][1] // 4))
    ]
    while len(meta1) < 15:
        meta1.append(0)

    arr3 = np.frombuffer(
        data, dtype=">i4", count=blocks[3][1] // 4, offset=blocks[3][0],
    )
    arr5 = np.frombuffer(
        data, dtype=">i4", count=blocks[5][1] // 4, offset=blocks[5][0],
    )
    quads = [tuple(arr5[i : i + 4]) for i in range(0, len(arr5), 4)]

    c_entb, c_entf, c_mom, c_parts = meta1[2], meta1[3], meta1[7], meta1[10]
    c_xmax, c_xmin, c_ymax, c_surf = meta1[12], meta1[13], meta1[14], meta1[11]
    c_ymin = meta1[15] if len(meta1) > 15 else 0
    c_zmax = meta1[16] if len(meta1) > 16 else 0
    c_zmin = meta1[17] if len(meta1) > 17 else 0

    off = 0
    slices: list[slice] = []
    for c in [c_entb, c_entf, c_mom, c_parts, c_xmax, c_xmin, c_ymax, c_surf, c_ymin, c_zmax, c_zmin]:
        slices.append(slice(off, off + c))
        off += c

    mat1_idx = [i for i in range(len(arr3)) if mat[arr3[i] - 1] == 1]
    mat2_idx = [i for i in range(len(arr3)) if mat[arr3[i] - 1] == 2]
    qm1 = [quads[i] for i in mat1_idx]
    qm2 = [quads[i] for i in mat2_idx]

    entb_m2 = len([
        q for i, q in enumerate(quads[slices[0]])
        if mat[int(arr3[slices[0]][i]) - 1] == 2
    ])
    entb_m1 = c_entb - entb_m2
    parts_m1 = _filter_by_mat(quads[slices[3]], arr3[slices[3]], mat, 1)
    parts_m2 = _filter_by_mat(quads[slices[3]], arr3[slices[3]], mat, 2)
    ymax_m2_n = len(qm2) - entb_m2 - 2 * len(parts_m2)
    ymax_m1_n = c_ymax - ymax_m2_n

    seg1 = sum([list(quads[s]) for s in slices], [])
    seg2 = (
        qm1[:entb_m1] + qm2[:entb_m2]
        + parts_m1 + parts_m2 + parts_m1 + parts_m2
        + qm1[-ymax_m1_n:] + qm2[-ymax_m2_n:]
    )
    faces = seg1 + seg2

    bc_names: list[str] = []
    for p, bc in blocks[8:]:
        if bc == 18:
            bc_names.append(data[p : p + bc].decode("ascii", errors="replace").strip())

    def _pick_name(prefix: str, default: str) -> str:
        for n in bc_names:
            if n == prefix or n.startswith(prefix):
                return n
        return default

    ymax_name = _pick_name("Ymax", "Ymax")
    seg1_counts = [c_entb, c_entf, c_mom, c_parts, c_surf, c_xmax, c_xmin, c_ymax]
    seg1_bc_names = [
        "@UNDEFINEDENTB",
        "@UNDEFINEDENTF",
        "@UNDEFINEDMOM",
        "PARTS",
        "SURFACE",
        _pick_name("Xmax", "Xmax"),
        _pick_name("Xmin", "Xmin"),
        ymax_name,
    ]

    bc_plan: list[tuple[str, int, int]] = []
    idx = 0
    for name, cnt in zip(seg1_bc_names, seg1_counts):
        bc_plan.append((name, idx, cnt))
        idx += cnt

    mat_bc_names = [
        "@UNDEFINEDENTB(MAT1)", "@UNDEFINEDENTB(MAT2)",
        "PARTS(MAT1)", "PARTS(MAT2)",
        "SURFACE(MAT1)", "SURFACE(MAT2)",
        f"{ymax_name}(MAT1)", f"{ymax_name}(MAT2)",
    ]
    mat_counts = [
        entb_m1, entb_m2, len(parts_m1), len(parts_m2),
        len(parts_m1), len(parts_m2), ymax_m1_n, ymax_m2_n,
    ]
    seg2_start = len(seg1)
    for name, cnt in zip(mat_bc_names, mat_counts):
        bc_plan.append((name, seg2_start, cnt))
        seg2_start += cnt

    # face -> owning cell id (0-based), aligned with `faces` by vertex tuple:
    # faces reorders quads (MAT1/MAT2 segments), so a direct index map would
    # drift; a dict on the 4-node tuple stays aligned regardless of order.
    cell_of = {}
    for i in range(len(quads)):
        cell_of.setdefault(quads[i], int(arr3[i]) - 1)
    face_cells = np.asarray([cell_of.get(f, -1) for f in faces],
                            dtype=np.int64)
    return faces, bc_plan, face_cells


def parse_fld(filepath: str) -> dict[str, Any]:
    """Parse an FLD file into a structured mesh + solution dict."""
    with open_buffer(filepath) as data:
        result: dict[str, Any] = {
            "file_size": len(data),
            "vertices": None,
            "n_vertices": 0,
            "cell_conn": None,
            "material": None,
            "n_cells": 0,
            "faces": [],
            "bc_plan": [],
            "face_cells": [],
            "volume_names": [],
            "fields": {},
        }

        xyz, n_verts = _parse_ls_nodes(data)
        cell_conn, mat = _parse_hex_cells(data)
        if xyz is not None:
            result["vertices"] = xyz
            result["n_vertices"] = n_verts
        if cell_conn is not None and mat is not None:
            result["cell_conn"] = cell_conn
            result["material"] = mat
            result["n_cells"] = int(cell_conn.shape[0])

        result["volume_names"] = _parse_volume_names(data)
        if mat is not None:
            faces, bc_plan, face_cells = _build_face_list_and_bcs(data, mat)
            result["faces"] = faces
            result["bc_plan"] = bc_plan
        result["face_cells"] = face_cells

        n = n_verts or 0
        temp_blocks = _f64_field_blocks(data, "Temperature")
        cn01_blocks = _f64_field_blocks(data, "CN01")
        pres_blocks = _f64_field_blocks(data, "Pressure")
        vect_blocks = _f64_field_blocks(data, "VECT")
        hvec_blocks = _f64_field_blocks(data, "HVEC")

        fields: dict[str, np.ndarray] = {}
        if pres_blocks and pres_blocks[0].size == n:
            fields["PRES"] = pres_blocks[0]
        if temp_blocks:
            if temp_blocks[0].size == n:
                fields["TEMP"] = temp_blocks[0]
                fields["ATMS"] = temp_blocks[0].copy()
            if len(temp_blocks) > 3 and temp_blocks[3].size == n:
                fields["TURK"] = temp_blocks[3]
            if len(temp_blocks) > 6 and temp_blocks[6].size == n:
                fields["TEPS"] = temp_blocks[6]
        if cn01_blocks:
            if cn01_blocks[0].size == n:
                fields["CN01"] = cn01_blocks[0]
            if len(cn01_blocks) > 3 and cn01_blocks[3].size == n:
                fields["HTRC"] = cn01_blocks[3]
            if len(cn01_blocks) > 6 and cn01_blocks[6].size == n:
                fields["SURT"] = cn01_blocks[6]
            if len(cn01_blocks) > 9 and cn01_blocks[9].size == n:
                fields["HTFX"] = cn01_blocks[9]
        if len(vect_blocks) >= 3 and all(a.size == n for a in vect_blocks[:3]):
            fields["VECTX"] = vect_blocks[0]
            fields["VECTY"] = vect_blocks[1]
            fields["VECTZ"] = vect_blocks[2]
        if len(hvec_blocks) >= 3 and all(a.size == n for a in hvec_blocks[:3]):
            fields["HVECX"] = hvec_blocks[0]
            fields["HVECY"] = hvec_blocks[1]
            fields["HVECZ"] = hvec_blocks[2]

        result["fields"] = fields
        return result


__all__ = ["parse_fld"]