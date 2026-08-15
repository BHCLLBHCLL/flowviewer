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
    parse_header_meta,
)


def _parse_ls_nodes(data) -> tuple[Optional[np.ndarray], int]:
    sec_start = find_section(data, "LS_Nodes")
    if sec_start < 0:
        return None, 0
    sec_end = section_end(data, sec_start)
    blocks = list(iter_data_blocks(data, sec_start, sec_end))
    # descriptor-guided: vertex count + element width decide the layout
    from ..crdl.mesh_gph import ls_nodes_descriptors
    elem_hint, n_desc = ls_nodes_descriptors(data, sec_start, sec_end)
    if n_desc:
        for elem, dt in ((8, ">f8"), (4, ">f4")):
            bc_target = n_desc * elem
            trio = [(p, bc) for p, bc in blocks if bc == bc_target][:3]
            if len(trio) == 3:
                axes = [
                    np.frombuffer(data, dtype=dt, count=n_desc, offset=p)
                    .astype(np.float64).copy()
                    for p, _ in trio
                ]
                return np.column_stack(axes), n_desc
        if elem_hint is None:
            for elem, dt in ((8, ">f8"), (4, ">f4")):
                bc_target = n_desc * elem
                trio = [(p, bc) for p, bc in blocks if bc == bc_target][:3]
                if len(trio) == 3:
                    axes = [
                        np.frombuffer(data, dtype=dt, count=n_desc, offset=p)
                        .astype(np.float64).copy()
                        for p, _ in trio
                    ]
                    return np.column_stack(axes), n_desc
    # fallback: largest block size appearing >= 3 times
    f64_blocks = [(p, bc) for p, bc in blocks
                  if bc >= 8 and bc % 8 == 0]
    if len(f64_blocks) < 3:
        return None, 0
    sizes = [bc for _, bc in f64_blocks]
    from collections import Counter
    counts = Counter(sizes)
    candidates = [s for s, c in counts.items() if c >= 3]
    if not candidates:
        return None, 0
    target = max(candidates)
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

def _parse_ls_nodes_f32(data):
    """f32 LS_Nodes fallback (minimumHexa-style small files)."""
    sec_start = find_section(data, "LS_Nodes")
    if sec_start < 0:
        return None, 0
    sec_end = section_end(data, sec_start)
    f32_blocks = [(p, bc) for p, bc in iter_data_blocks(data, sec_start, sec_end)
                  if bc >= 12 and bc % 4 == 0]
    if len(f32_blocks) < 3:
        return None, 0
    from collections import Counter
    sizes = [bc for _, bc in f32_blocks]
    counts = Counter(sizes)
    candidates = [s for s, c in counts.items() if c >= 3]
    if not candidates:
        return None, 0
    target = max(candidates)
    trio = [(p, bc) for p, bc in f32_blocks if bc == target][:3]
    if len(trio) < 3:
        return None, 0
    n_vertices = trio[0][1] // 4
    axes = [
        np.frombuffer(data, dtype=">f4", count=n_vertices, offset=p)
        .astype(np.float64).copy()
        for p, _ in trio
    ]
    return np.column_stack(axes), n_vertices


def _parse_mixed_connectivity(data, sec_elem, sec_end, n_cells, type_codes,
                              node_counts):
    """Mixed-cell connectivity: per-type node counts + segmented conn.

    scFLOW type codes 34/35/36 map to tet(4)/pyramid(5)/wedge(6).  The
    connectivity array may be split into a standard block plus bare
    continuation blocks (same pattern as GPH LS_Links conn >1 GiB).
    Returns (conn padded to 6 nodes, vtk type codes).
    """
    from ..crdl.mesh_gph import _read_conn_continuations
    blocks = list(iter_data_blocks(data, sec_elem, sec_end))
    expected = int(sum(node_counts[int(x)] for x in type_codes))
    type_bc = n_cells * 4
    conn_parts = []
    got = 0
    conn_p = None
    for p, bc in sorted(blocks, key=lambda b: -b[1]):
        if bc == type_bc:
            continue
        if bc >= 12 and bc % 4 == 0:
            part = np.frombuffer(data, dtype=">i4", count=bc // 4, offset=p)
            part = part.astype(np.int64).copy()
            conn_parts.append(part)
            got += part.size
            conn_p = p + bc + 4  # p is the payload start; +trailer
            break
    if conn_p is None:
        return None, None
    if got < expected:
        got, _, _ = _read_conn_continuations(
            data, conn_p, sec_end, got, expected, conn_parts)
    if got < expected:
        return None, None
    conn = np.concatenate(conn_parts)[:expected]
    _VTK = {34: 10, 35: 14, 36: 13}
    out = np.full((n_cells, 6), -1, dtype=np.int64)
    ctypes = np.zeros(n_cells, dtype=np.int64)
    pos = 0
    for i, tc in enumerate(type_codes):
        nn = node_counts[int(tc)]
        out[i, :nn] = conn[pos:pos + nn]
        ctypes[i] = _VTK[int(tc)]
        pos += nn
    return out, ctypes


def _parse_minimal_cells(data, sec_elem, sec_end):
    """Descriptor-dense minimal files (minimumHexa-style).

    No LS_MatOfElements data block exists; the element type (38 = hex) and
    nodes-per-cell are carried in [12,4,type,4] / [12,4,nnodes,4]
    descriptors, and the connectivity is one small i4 block.
    """
    type_code = None
    nodes_per = None
    pos = sec_elem + 40
    while pos + 16 <= sec_end:
        if read_i32_be(data, pos) == 12 and read_i32_be(data, pos + 4) == 4:
            d0 = read_i32_be(data, pos + 8)
            d1 = read_i32_be(data, pos + 12)
            if d0 in (34, 35, 36, 38) and d1 == 4:
                type_code = d0
            elif 4 <= d0 <= 8 and d1 == 4:
                nodes_per = d0
        pos += 4
    if type_code is None or nodes_per is None:
        return None, None
    for p, bc in iter_data_blocks(data, sec_elem, sec_end):
        if bc % 4 != 0:
            continue
        total = bc // 4
        if total % nodes_per != 0:
            continue
        n_cells = total // nodes_per
        if not (1 <= n_cells <= 10_000):
            continue
        conn = np.frombuffer(data, dtype=">i4", count=total, offset=p)
        conn = conn.astype(np.int64).copy().reshape(n_cells, nodes_per)
        vtk_t = {34: 10, 35: 14, 36: 13, 38: 12}[type_code]
        ctypes = np.full(n_cells, vtk_t, dtype=np.int64)
        mat = np.ones(n_cells, dtype=np.int64)
        return conn, ctypes, mat
    return None, None


def _parse_hex_cells(data) -> tuple[Optional[np.ndarray], Optional[np.ndarray],
                                   Optional[np.ndarray]]:
    """Return ``(cell_conn (n_cells, nn), cell_types, material_id)``.

    Supports hex(8) / wedge(6) / pyramid(5) / tet(4) FLD variants: the
    connectivity block is matched by ``n_cells * nnodes`` i4 words rather
    than assuming hexahedra.
    """
    sec_mat = find_section(data, "LS_MatOfElements")
    sec_elem = find_section(data, "LS_Elements")
    if sec_mat < 0 or sec_elem < 0:
        return None, None, None
    mat_blocks = list(iter_data_blocks(data, sec_mat, section_end(data, sec_mat)))
    elem_blocks = list(iter_data_blocks(data, sec_elem, section_end(data, sec_elem)))
    if not mat_blocks or not elem_blocks:
        if not mat_blocks and elem_blocks:
            conn, ctypes, mmat = _parse_minimal_cells(
                data, sec_elem, section_end(data, sec_elem))
            if conn is not None:
                return conn, ctypes, mmat
        return None, None, None
    mat = np.frombuffer(
        data, dtype=">i4", count=mat_blocks[0][1] // 4, offset=mat_blocks[0][0],
    ).astype(np.int64).copy()
    n_cells = mat.size
    if n_cells == 0:
        return None, None, None
    # mixed-cell variant: a per-cell type-code block (34/35/36) drives a
    # segmented connectivity accumulation
    for p, bc in elem_blocks:
        if bc == n_cells * 4:
            tarr = np.frombuffer(data, dtype=">i4", count=n_cells, offset=p)
            uniq = set(np.unique(tarr).tolist())
            if uniq and uniq <= {34, 35, 36}:
                conn, ctypes = _parse_mixed_connectivity(
                    data, sec_elem, section_end(data, sec_elem),
                    n_cells, tarr, {34: 4, 35: 5, 36: 6})
                if conn is not None:
                    return conn, ctypes, mat
    _NN_TO_VTK = {4: 10, 5: 14, 6: 13, 8: 12}
    for p, bc in sorted(elem_blocks, key=lambda b: -b[1]):
        if bc % 4 != 0:
            continue
        total = bc // 4
        # connectivity may share its block with trailing face/BC words
        # (tet-style files): match the n_cells*nn i4 prefix, trying hex
        # first and falling back to smaller cells
        for nn in (8, 6, 5, 4):
            need = n_cells * nn
            if need > total:
                continue
            arr = np.frombuffer(data, dtype=">i4", count=need, offset=p)
            conn = arr.astype(np.int64).copy().reshape(n_cells, nn)
            ctypes = None if nn == 8 else np.full(n_cells, _NN_TO_VTK[nn],
                                                  dtype=np.int64)
            return conn, ctypes, mat
    # legacy: hex-only path (conn == n_cells * 32 bytes)
    for p, bc in sorted(elem_blocks, key=lambda b: -b[1]):
        if bc == n_cells * 32:
            conn = np.frombuffer(data, dtype=">i4", count=bc // 4, offset=p)
            conn = conn.astype(np.int64).copy().reshape(-1, 8)
            return conn, np.full(n_cells, 12, dtype=np.int64), mat
    return None, None, mat


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
    """Build the NGON face list and BC index ranges (best-effort).

    The block layout differs between hex and tet FLD variants; when the
    expected layout does not match, fall back to an empty face list so the
    mesh itself still loads.
    """
    try:
        return _build_face_list_and_bcs_inner(data, mat)
    except Exception:
        return [], [], np.asarray([], dtype=np.int64)


def _build_face_list_and_bcs_inner(data, mat: np.ndarray):
    """Layout-specific NGON face list and BC index ranges.

    Returns ``(faces, bc_plan, face_cells)`` where each BC entry is
    ``(name, start_index_0based, count)`` into *faces*.
    """
    sec_start = find_section(data, "LS_SurfaceGeometryArray")
    if sec_start < 0:
        return [], [], np.asarray([], dtype=np.int64)
    sec_end = section_end(data, sec_start)
    blocks = list(iter_data_blocks(data, sec_start, sec_end))
    if len(blocks) < 6:
        return [], [], np.asarray([], dtype=np.int64)

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

    mat1_idx = [i for i in range(len(arr3))
                if i < len(quads) and mat[arr3[i] - 1] == 1]
    mat2_idx = [i for i in range(len(arr3))
                if i < len(quads) and mat[arr3[i] - 1] == 2]
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


_BC_NAME_PREFIXES = (b"FLUX(", b"WALL(", b"THERM(", b"PRES(", b"INLT(",
                     b"OUTL(", b"SYMM(", b"PERI(", b"CYCL(", b"MOVI(",
                     b"RADI(")


def _parse_bc_sections(data) -> list[tuple[str, bytes]]:
    """Named per-zone BC sections -> ``[(zone_name, payload_bytes), ...]``.

    scSTREAM/sCtetra FLD stores one nested named section per BC zone;
    its body is a ``[12][1][N][1]`` descriptor followed by one
    ``[12][N]`` payload (zone settings text with a leading 4-char type
    code).  Sections are located by scanning the known scSTREAM BC name
    prefixes, so arbitrary zone names (FLUX(velocity), WALL(static),
    THERM(adiabatic), ...) are picked up.
    """
    out: list[tuple[str, bytes]] = []
    for prefix in _BC_NAME_PREFIXES:
        pos = 0
        while True:
            idx = data.find(prefix, pos)
            if idx < 0:
                break
            pos = idx + 1
            if idx < 4 or read_i32_be(data, idx - 4) != 32:
                continue
            raw = data[idx:idx + 32].split(b"\x00")[0].strip()
            try:
                name = raw.decode("ascii")
            except UnicodeDecodeError:
                continue
            sec = idx - 4
            end = section_end(data, sec)
            p = sec + 40
            while p + 16 <= end:
                if read_i32_be(data, p) != 12:
                    p += 4
                    continue
                v = read_i32_be(data, p + 4)
                n0 = read_i32_be(data, p + 8)
                n1 = read_i32_be(data, p + 12)
                if v == 1 and n1 == 1 and 0 < n0 <= 1_000_000:
                    p2 = p + 16
                    if (p2 + 8 + n0 + 4 <= end
                            and read_i32_be(data, p2) == 12
                            and read_i32_be(data, p2 + 4) == n0
                            and read_i32_be(data, p2 + 8 + n0) == n0):
                        out.append((name, bytes(data[p2 + 8:p2 + 8 + n0])))
                        break
                p += 4
            pass
    return out


def _parse_ls_sfile(data) -> Optional[dict]:
    """LS_SFile -> embedded scSTREAM surface-file header info.

    Body: descriptors ``[12,4,1,1],[12,4,1,4],[12,4,1,1],[12,4,N,4]``
    then ``[12][1][N][1]`` + ``[12][N]`` payload whose head is ASCII
    (``SDAT`` surface-file header).  A nested ``LS_Scalar:`` section may
    follow inside the same section range.
    """
    sec = find_section(data, "LS_SFile")
    if sec < 0:
        return None
    end = section_end(data, sec)
    p = sec + 40
    while p + 16 <= end:
        if read_i32_be(data, p) != 12:
            p += 4
            continue
        v = read_i32_be(data, p + 4)
        n0 = read_i32_be(data, p + 8)
        n1 = read_i32_be(data, p + 12)
        if v == 1 and n1 == 1 and 0 < n0 <= 1_000_000:
            p2 = p + 16
            if (p2 + 8 + n0 + 4 <= end and read_i32_be(data, p2) == 12
                    and read_i32_be(data, p2 + 4) == n0
                    and read_i32_be(data, p2 + 8 + n0) == n0):
                payload = bytes(data[p2 + 8:p2 + 8 + n0])
                head = payload[:64].decode("ascii", "replace")
                magic = head.split("\n")[0].strip() if head else ""
                return {"bytes": n0, "magic": magic, "head": head}
        p += 4
    return None

def parse_fld(filepath: str) -> dict[str, Any]:
    """Parse an FLD file into a structured mesh + solution dict."""
    with open_buffer(filepath) as data:
        result: dict[str, Any] = {
            "file_size": len(data),
            "vertices": None,
            "n_vertices": 0,
            "cell_conn": None,
            "cell_types": None,
            "material": None,
            "n_cells": 0,
            "faces": [],
            "bc_plan": [],
            "face_cells": [],
            "volume_names": [],
            "fields": {},
            "bc_sections": [],
            "ls_sfile": None,
            "meta": {},
        }

        xyz, n_verts = _parse_ls_nodes(data)
        if xyz is None:
            xyz, n_verts = _parse_ls_nodes_f32(data)
        cell_conn, cell_types, mat = _parse_hex_cells(data)
        if xyz is not None:
            result["vertices"] = xyz
            result["n_vertices"] = n_verts
        if cell_conn is not None and mat is not None:
            result["cell_conn"] = cell_conn
            result["cell_types"] = cell_types
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
        def _size_ok(arr):
            """Match the mesh vertex count, or accept any block when the
            mesh is absent (result-only files inherit it later)."""
            return arr.size > 0 and (n == 0 or arr.size == n)
        if pres_blocks and _size_ok(pres_blocks[0]):
            fields["PRES"] = pres_blocks[0]
        if temp_blocks:
            if _size_ok(temp_blocks[0]):
                fields["TEMP"] = temp_blocks[0]
                fields["ATMS"] = temp_blocks[0].copy()
            if len(temp_blocks) > 3 and _size_ok(temp_blocks[3]):
                fields["TURK"] = temp_blocks[3]
            if len(temp_blocks) > 6 and _size_ok(temp_blocks[6]):
                fields["TEPS"] = temp_blocks[6]
        if cn01_blocks:
            if _size_ok(cn01_blocks[0]):
                fields["CN01"] = cn01_blocks[0]
            if len(cn01_blocks) > 3 and _size_ok(cn01_blocks[3]):
                fields["HTRC"] = cn01_blocks[3]
            if len(cn01_blocks) > 6 and _size_ok(cn01_blocks[6]):
                fields["SURT"] = cn01_blocks[6]
            if len(cn01_blocks) > 9 and _size_ok(cn01_blocks[9]):
                fields["HTFX"] = cn01_blocks[9]
        if len(vect_blocks) >= 3 and all(_size_ok(a) for a in vect_blocks[:3]):
            fields["VECTX"] = vect_blocks[0]
            fields["VECTY"] = vect_blocks[1]
            fields["VECTZ"] = vect_blocks[2]
        if len(hvec_blocks) >= 3 and all(_size_ok(a) for a in hvec_blocks[:3]):
            fields["HVECX"] = hvec_blocks[0]
            fields["HVECY"] = hvec_blocks[1]
            fields["HVECZ"] = hvec_blocks[2]

        result["fields"] = fields
        result["bc_sections"] = _parse_bc_sections(data)
        result["ls_sfile"] = _parse_ls_sfile(data)
        result["meta"] = parse_header_meta(data)

        return result


__all__ = ["parse_fld"]