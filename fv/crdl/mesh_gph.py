"""GPH / FPH mesh parsing (LS_Nodes, LS_Links, regions, parts).

Converged from the tested GPH decoders ``gph_model.py`` / ``gph2cgns.py`` /
``fph2cgns.py`` (DEV_PLAN.md R1).  The FPH result files used by scFLOW store
the same LS_Links polyhedral topology with a float32 LS_Nodes coordinate
set; the dialect is auto-detected at parse time.

Public entry point: :func:`parse_gph_mesh`.
"""

from collections import Counter, defaultdict
from typing import Optional

import numpy as np

from .core import (
    find_section,
    section_end,
    iter_data_blocks,
    read_i32_be,
    f64_be_array,
    f64_wr_array,
    f32_be_array,
    i32_be_array,
    open_buffer,
    parse_header_meta,
)

_CONN_CHUNK_BYTES = 1073741824  # 1 GiB cap per LS_Links conn payload block

# Coordinate plausibility bounds (see gph_model._score_coord_axes).
_COORD_MIN_ABSMAX = 1e-4
_COORD_MAX_ABSMAX = 1e6
_COORD_SCORE_SAMPLE = 256
_ELEM_PRIOR_MISMATCH = 1e15
_F32_ON_F64_ALIGNED_PRIOR = 10.0

# Part → either one cvol_id or a membership set (composite / background parts).
PartCvolSpec = int | frozenset[int]


# ─────────────────────────────────────────────────────────────────────────────
# LS_Nodes – vertex coordinates
# ─────────────────────────────────────────────────────────────────────────────


def _score_coord_axes(axes: list[np.ndarray]) -> float:
    """Lower score = more plausible CFD vertex coordinate axes.

    Penalises non-finite values, coordinate magnitudes outside
    ~[``_COORD_MIN_ABSMAX``, ``_COORD_MAX_ABSMAX``], a high fraction of such
    outliers (typical of wrong float32/float64 decode), and grossly mismatched
    axis scales.
    """
    score = 0.0
    axis_absmax: list[float] = []
    for ax in axes:
        arr = np.asarray(ax, dtype=np.float64)
        finite = np.isfinite(arr)
        if not finite.all():
            score += 1e30
            continue
        absv = np.abs(arr[finite])
        if absv.size == 0:
            axis_absmax.append(0.0)
            continue
        absmax = float(np.max(absv))
        axis_absmax.append(absmax)
        if absmax > _COORD_MAX_ABSMAX or (
                absmax < _COORD_MIN_ABSMAX and absmax != 0.0
        ):
            score += absmax + (1.0 / max(absmax, 1e-300))
        else:
            score += absmax
        if absmax < _COORD_MIN_ABSMAX and absmax != 0.0:
            bad_frac = float(
                ((absv > _COORD_MAX_ABSMAX)
                 | ((absv < _COORD_MIN_ABSMAX) & (absv != 0.0))).mean()
            )
            if bad_frac > 0.01:
                score += 1e20 * bad_frac
        elif absmax > _COORD_MAX_ABSMAX:
            bad_frac = float((absv > _COORD_MAX_ABSMAX).mean())
            if bad_frac > 0.01:
                score += 1e20 * bad_frac
    pos = [v for v in axis_absmax if v > 0]
    if len(pos) >= 2:
        ratio = max(pos) / min(pos)
        if ratio > 1e6:
            score += ratio
    return score


def ls_nodes_descriptor_elem_bytes(data, sec_start: int, sec_end: int) -> Optional[int]:
    """Return element size (4=float32, 8=float64) from LS_Nodes descriptors."""
    counts = {4: 0, 8: 0}
    pos = sec_start + 40
    n = len(data)
    while pos + 16 <= sec_end and pos + 16 <= n:
        if read_i32_be(data, pos) == 12:
            tc = read_i32_be(data, pos + 4)
            if tc in (4, 8):
                dim0 = read_i32_be(data, pos + 8)
                dim1 = read_i32_be(data, pos + 12)
                if dim0 > 1 and 0 < dim1 < 10_000_000:
                    counts[tc] += 1
        pos += 4
    if counts[8] > counts[4]:
        return 8
    if counts[4] > counts[8]:
        return 4
    return None


def ls_nodes_vertex_count_from_descriptors(data, sec_start: int, sec_end: int) -> Optional[int]:
    best = 0
    pos = sec_start + 40
    n = len(data)
    while pos + 16 <= sec_end and pos + 16 <= n:
        if read_i32_be(data, pos) == 12:
            tc = read_i32_be(data, pos + 4)
            if tc in (4, 8):
                dim0 = read_i32_be(data, pos + 8)
                dim1 = read_i32_be(data, pos + 12)
                if dim0 > 1 and 0 < dim1 < 10_000_000:
                    best = max(best, dim0)
        pos += 4
    return best if best > 0 else None


def ls_nodes_descriptors(data, sec_start: int, sec_end: int
                         ) -> tuple[Optional[int], Optional[int]]:
    """Single-pass scan of the LS_Nodes descriptor region.

    Returns ``(elem_bytes, vertex_count)``.  A data block starts with the
    ``[12, byte_count]`` header, so a ``12`` at the descriptor slot followed
    by ``type_code in {4,8}`` marks a real ``[12, tc, dim0, dim1]``
    descriptor.  The whole region is read once as a big-endian int32 array
    and scanned with numpy, which is far faster than per-word Python reads.
    """
    lo = sec_start + 40
    n = len(data)
    count = (min(sec_end, n) - lo) // 4
    if count <= 0:
        return None, None
    arr = np.frombuffer(data, dtype=">i4", count=count, offset=lo)
    # Positions where a descriptor [12, tc, dim0, dim1] could start.
    head = np.flatnonzero(arr[:-3] == 12)
    if head.size == 0:
        return None, None
    tc = arr[head + 1]
    dim0 = arr[head + 2]
    dim1 = arr[head + 3]
    ok = (np.isin(tc, (4, 8))) & (dim0 > 1) & (dim1 > 0) & (dim1 < 10_000_000)
    if not ok.any():
        return None, None
    t4 = int(np.count_nonzero(ok & (tc == 4)))
    t8 = int(np.count_nonzero(ok & (tc == 8)))
    best = int(dim0[ok].max())
    elem = 8 if t8 > t4 else (4 if t4 > t8 else None)
    return elem, best if best > 0 else None


def parse_ls_nodes_xyz(data) -> tuple[Optional[np.ndarray], int]:
    """Parse LS_Nodes → ``(xyz float64 N×3, n_vertices)``.

    Supports standard BE float64, word-reversed float64, and BE float32
    (FPH / ``tests/tr03_9.fph``).
    """
    sec_start = find_section(data, "LS_Nodes")
    if sec_start < 0:
        return None, 0
    sec_end = section_end(data, sec_start)

    blocks = list(iter_data_blocks(data, sec_start, sec_end))
    f_blocks = [(p, bc) for p, bc in blocks if bc >= 4 and bc % 4 == 0]
    if len(f_blocks) < 3:
        return None, 0

    sizes = [bc for _, bc in f_blocks]
    target = max(set(sizes), key=sizes.count)
    trio = [(p, bc) for p, bc in f_blocks if bc == target][:3]
    if len(trio) < 3:
        return None, 0

    bc = trio[0][1]
    elem_hint, n_desc = ls_nodes_descriptors(data, sec_start, sec_end)

    def _ranked_score(sample_axes: list[np.ndarray], elem_bytes: int) -> float:
        s = _score_coord_axes(sample_axes)
        if elem_hint is not None and elem_bytes != elem_hint:
            s += _ELEM_PRIOR_MISMATCH
        elif elem_hint is None and elem_bytes == 4 and bc % 8 == 0:
            s += _F32_ON_F64_ALIGNED_PRIOR
        return s

    ranked: list[tuple[float, str]] = []

    if bc % 8 == 0:
        n_f64 = bc // 8
        if n_desc is None or n_desc == n_f64:
            n_sample = min(n_f64, _COORD_SCORE_SAMPLE)
            ranked.append((
                _ranked_score([f64_be_array(data, p, n_sample) for p, _ in trio], 8),
                "be",
            ))
            ranked.append((
                _ranked_score([f64_wr_array(data, p, n_sample) for p, _ in trio], 8),
                "wr",
            ))

    if bc % 4 == 0 and elem_hint != 8:
        n_f32 = n_desc if n_desc is not None else bc // 4
        if n_desc is None or n_desc == bc // 4:
            n_sample = min(n_f32, _COORD_SCORE_SAMPLE)
            ranked.append((
                _ranked_score([f32_be_array(data, p, n_sample) for p, _ in trio], 4),
                "f32",
            ))

    if not ranked:
        return None, 0

    _, kind = min(ranked, key=lambda item: item[0])
    if kind == "be":
        n_vertices = n_desc if n_desc is not None else bc // 8
        axes = [f64_be_array(data, p, n_vertices) for p, _ in trio]
        is_wr = False
    elif kind == "wr":
        n_vertices = n_desc if n_desc is not None else bc // 8
        axes = [f64_wr_array(data, p, n_vertices) for p, _ in trio]
        is_wr = True
    else:
        n_vertices = n_desc if n_desc is not None else bc // 4
        axes = [f32_be_array(data, p, n_vertices) for p, _ in trio]
        is_wr = False

    xyz = np.column_stack(axes)
    if is_wr:
        xyz = xyz[:, [0, 2, 1]]
    return xyz, n_vertices


# ─────────────────────────────────────────────────────────────────────────────
# LS_Links – face / cell connectivity
# ─────────────────────────────────────────────────────────────────────────────


def _read_conn_continuations(data, pos: int, sec_end: int, got: int, expected: int,
                             conn_parts=None) -> tuple[int, int, int]:
    """Read connector payload.  Continuation blocks are bare
    ``[I4=byte_count][payload]`` (no ``[I4=12]`` header)."""
    n_continuations = 0
    while got < expected and pos + 4 <= sec_end:
        need_bytes = (expected - got) * 4
        bare_bc = read_i32_be(data, pos)

        if (bare_bc == _CONN_CHUNK_BYTES
                and pos + 4 + _CONN_CHUNK_BYTES <= sec_end):
            n = _CONN_CHUNK_BYTES // 4
            if conn_parts is not None:
                conn_parts.append(
                    np.frombuffer(data, dtype=">u4", count=n, offset=pos + 4)
                    .astype(np.int64).copy())
            got += n
            pos += 4 + _CONN_CHUNK_BYTES
            n_continuations += 1
            continue

        if (bare_bc == _CONN_CHUNK_BYTES
                and need_bytes < _CONN_CHUNK_BYTES
                and pos + 8 <= sec_end):
            inner_bc = read_i32_be(data, pos + 4)
            if (inner_bc == need_bytes
                    and pos + 8 + need_bytes <= sec_end):
                n = need_bytes // 4
                if conn_parts is not None:
                    conn_parts.append(
                        np.frombuffer(data, dtype=">u4", count=n, offset=pos + 8)
                        .astype(np.int64).copy())
                got += n
                pos += 8 + need_bytes
                n_continuations += 1
                break

        if (bare_bc == _CONN_CHUNK_BYTES
                and pos + 4 + need_bytes <= sec_end):
            n = need_bytes // 4
            if conn_parts is not None:
                conn_parts.append(
                    np.frombuffer(data, dtype=">u4", count=n, offset=pos + 4)
                    .astype(np.int64).copy())
            got += n
            pos += 4 + need_bytes
            n_continuations += 1
            break

        if (bare_bc == need_bytes
                and pos + 4 + need_bytes <= sec_end):
            n = need_bytes // 4
            if conn_parts is not None:
                conn_parts.append(
                    np.frombuffer(data, dtype=">u4", count=n, offset=pos + 4)
                    .astype(np.int64).copy())
            got += n
            n_continuations += 1
            break

        if (bare_bc >= need_bytes and bare_bc % 4 == 0
                and pos + 4 + bare_bc <= sec_end):
            n = bare_bc // 4
            if conn_parts is not None:
                conn_parts.append(
                    np.frombuffer(data, dtype=">u4", count=n, offset=pos + 4)
                    .astype(np.int64).copy())
            got += n
            pos += 4 + bare_bc
            n_continuations += 1
            continue

        if read_i32_be(data, pos) == 12 and pos + 8 <= sec_end:
            bc2 = read_i32_be(data, pos + 4)
            if (bc2 > 0 and bc2 % 4 == 0
                    and pos + 8 + bc2 + 4 <= sec_end
                    and read_i32_be(data, pos + 8 + bc2) == bc2):
                n = bc2 // 4
                if conn_parts is not None:
                    conn_parts.append(
                        np.frombuffer(data, dtype=">u4", count=n, offset=pos + 8)
                        .astype(np.int64).copy())
                got += n
                pos += 8 + bc2 + 4
                n_continuations += 1
                continue
        break
    return got, pos, n_continuations


def _group_faces_by_cell_id(cell_ids: np.ndarray, face_indices: np.ndarray,
                            n_cells: int) -> dict:
    """Return ``{cell_id: face-index array}`` for parallel arrays.

    Values are array views on the sorted index buffer (not Python lists):
    on multi-million-face meshes this avoids tens of millions of Python
    ints and the GC pressure that goes with them.
    """
    out: dict = defaultdict(list)
    if cell_ids.size == 0:
        return out
    order = np.argsort(cell_ids, kind="mergesort")
    sorted_ids = cell_ids[order]
    sorted_faces = face_indices[order]
    boundaries = np.concatenate([
        [0],
        np.flatnonzero(sorted_ids[1:] != sorted_ids[:-1]) + 1,
        [sorted_ids.size],
    ])
    for i in range(len(boundaries) - 1):
        lo, hi = boundaries[i], boundaries[i + 1]
        cid = int(sorted_ids[lo])
        if 0 <= cid < n_cells:
            out[cid] = sorted_faces[lo:hi]
    return out


def parse_ls_links(data):
    """Parse the LS_Links section.

    Returns a dict with keys::

        n_faces, face_nodes, owner, neighbour (-1 = boundary),
        boundary_faces, cell_owner_faces, cell_neighbour_faces, n_cells
    """
    sec_start = find_section(data, "LS_Links")
    if sec_start < 0:
        return None
    sec_end = section_end(data, sec_start)

    blocks = [(p, bc) for p, bc in iter_data_blocks(data, sec_start, sec_end) if bc > 0]
    if not blocks:
        return None

    block_sizes = [bc for _, bc in blocks]
    common = Counter(block_sizes).most_common()
    n_faces_block_size = None
    for size, count in common:
        if count >= 3 and size % 4 == 0 and size >= 4:
            n_faces_block_size = size
            break
    if n_faces_block_size is None:
        return None
    n_faces = n_faces_block_size // 4

    triples = [b for b in blocks if b[1] == n_faces_block_size][:3]
    while len(triples) < 3:
        triples.append((0, 0))
    owner_p, _ = triples[0]
    neigh_p, _ = triples[1]
    npe_p, _ = triples[2]

    BNDRY_U = 0xFFFFFFFF
    if triples[0][1] == 0:
        return None
    owner = np.frombuffer(data[owner_p: owner_p + n_faces_block_size],
                          dtype=">u4").astype(np.int64).copy()
    npe = np.frombuffer(data[npe_p: npe_p + n_faces_block_size],
                        dtype=">u4").astype(np.int64).copy()
    neigh_raw = np.frombuffer(data[neigh_p: neigh_p + n_faces_block_size],
                              dtype=">u4").copy()
    neigh = neigh_raw.astype(np.int64)
    neigh[neigh_raw == BNDRY_U] = -1

    conn_total_expected = int(npe.sum())
    conn_block = None
    for p, bc in blocks:
        if (p, bc) in triples:
            continue
        if bc % 4 != 0:
            continue
        if bc // 4 == conn_total_expected:
            conn_block = (p, bc)
            break
    if conn_block is None:
        for p, bc in blocks:
            if (p, bc) in triples:
                continue
            if bc % 4 != 0:
                continue
            if bc < 12:
                continue
            if conn_block is None or bc > conn_block[1]:
                conn_block = (p, bc)
    if conn_block is None:
        return None
    conn_p, conn_bc = conn_block
    conn_parts = [
        np.frombuffer(data, dtype=">u4", count=conn_bc // 4, offset=conn_p)
        .astype(np.int64)
        .copy()
    ]
    got = int(conn_parts[0].size)

    if got < conn_total_expected:
        pos = conn_p + conn_bc + 4
        got, _, _ = _read_conn_continuations(
            data, pos, sec_end, got, conn_total_expected, conn_parts,
        )
        if got < conn_total_expected:
            return None
        conn = np.concatenate(conn_parts)[:conn_total_expected]
    else:
        conn = conn_parts[0][:conn_total_expected]

    face_offsets = np.empty(n_faces + 1, dtype=np.int64)
    face_offsets[0] = 0
    np.cumsum(npe, out=face_offsets[1:])
    face_nodes = conn  # flat 0-based vertex indices

    n_cells = int(max(int(owner.max()) + 1, int((neigh.max() + 1) if (neigh >= 0).any() else 0)))
    all_faces = np.arange(n_faces, dtype=np.int64)
    cell_owner_faces = _group_faces_by_cell_id(owner, all_faces, n_cells)
    neigh_valid = neigh >= 0
    cell_neighbour_faces = _group_faces_by_cell_id(
        neigh[neigh_valid], all_faces[neigh_valid], n_cells,
    )

    return {
        "n_faces": n_faces,
        "npe": npe,
        "face_nodes": face_nodes,
        "face_offsets": face_offsets,
        "owner": owner,
        "neighbour": neigh,
        "boundary_faces": np.flatnonzero(neigh == -1).tolist(),
        "cell_owner_faces": cell_owner_faces,
        "cell_neighbour_faces": cell_neighbour_faces,
        "n_cells": n_cells,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LS_CvolIdOfElements / LS_VolumeRegions / LS_Parts / LS_SurfaceRegions
# ─────────────────────────────────────────────────────────────────────────────


def parse_ls_cvol_ids(data) -> Optional[np.ndarray]:
    sec_start = find_section(data, "LS_CvolIdOfElements")
    if sec_start < 0:
        return None
    sec_end = section_end(data, sec_start)
    best = None
    for p, bc in iter_data_blocks(data, sec_start, sec_end):
        if bc % 4 == 0 and bc >= 4:
            if best is None or bc > best[1]:
                best = (p, bc)
    if best is None:
        return None
    p, bc = best
    return i32_be_array(data, p, bc // 4)


def parse_ls_string_list(data, section_name: str) -> list[str]:
    """Return the list of ASCII strings stored in a section."""
    sec_start = find_section(data, section_name)
    if sec_start < 0:
        return []
    sec_end = section_end(data, sec_start)
    out: list[str] = []
    for p, bc in iter_data_blocks(data, sec_start, sec_end):
        raw = data[p : p + bc]
        if all(b == 0 or 32 <= b < 127 for b in raw):
            s = raw.decode("ascii", errors="replace").strip("\x00").rstrip()
            if s:
                out.append(s)
    return out


def _ls_parts_name_blocks(data, sec_start: int, sec_end: int):
    """Return ``[(name, name_header_pos, after_trailer_pos), ...]`` in order."""
    name_blocks: list[tuple[str, int, int]] = []
    for p, bc in iter_data_blocks(data, sec_start, sec_end):
        if bc <= 0 or bc > 512:
            continue
        raw = data[p : p + bc]
        if not all(b == 0 or 32 <= b < 127 for b in raw):
            continue
        name = raw.decode("ascii", errors="replace").strip("\x00").rstrip()
        if not name or not any(c.isalpha() for c in name):
            continue
        name_blocks.append((name, p - 8, p + bc + 4))
    return name_blocks


def _scan_cvol_descriptor_chain(data, start: int, end: int) -> list[int]:
    chain: list[int] = []
    pos = start
    while pos + 16 <= end:
        if (read_i32_be(data, pos) == 12
                and read_i32_be(data, pos + 4) == 4
                and read_i32_be(data, pos + 12) == 4):
            chain.append(read_i32_be(data, pos + 8))
        pos += 4
    return chain


def part_cvol_cell_mask(cvol_id: np.ndarray, spec: PartCvolSpec) -> np.ndarray:
    """Boolean mask of cells belonging to a Part (single id or id set)."""
    if isinstance(spec, frozenset):
        if not spec:
            return np.zeros(len(cvol_id), dtype=bool)
        return np.isin(cvol_id, list(spec))
    return cvol_id == spec


def _parse_part_cvol_membership(data, start: int, end: int,
                                actual_set) -> Optional[frozenset[int]]:
    chain = _scan_cvol_descriptor_chain(data, start, end)
    if not chain:
        return None
    chain_counts = set(chain)
    for p, bc in iter_data_blocks(data, start, end):
        if bc < 8 or bc % 4 != 0:
            continue
        n = bc // 4
        if n not in chain_counts:
            continue
        vals = [int(x) for x in np.frombuffer(data, dtype=">i4", count=n, offset=p)]
        if len(vals) != n or len(set(vals)) != n:
            continue
        if actual_set is not None and not all(v in actual_set for v in vals):
            continue
        if n >= 2:
            return frozenset(vals)
    return None


def _resolve_single_part_cvol(chain: list[int], actual_set) -> int:
    if not chain:
        return 1
    return int(chain[-1])


def parse_ls_parts(data, cvol_id: Optional[np.ndarray] = None):
    """Parse LS_Parts → ``[(part_name, cvol_spec), ...]`` in file order."""
    sec_start = find_section(data, "LS_Parts")
    if sec_start < 0:
        return []
    sec_end = section_end(data, sec_start)
    name_blocks = _ls_parts_name_blocks(data, sec_start, sec_end)

    actual_set = None
    if cvol_id is not None and len(cvol_id) > 0:
        actual_set = {int(x) for x in np.unique(cvol_id)}

    out: list[tuple[str, PartCvolSpec]] = []
    for i, (name, _, after_trailer) in enumerate(name_blocks):
        scan_end = name_blocks[i + 1][1] if i + 1 < len(name_blocks) else sec_end
        membership = _parse_part_cvol_membership(data, after_trailer, scan_end, actual_set)
        if membership is not None:
            out.append((name, membership))
            continue
        chain = _scan_cvol_descriptor_chain(data, after_trailer, scan_end)
        out.append((name, _resolve_single_part_cvol(chain, actual_set)))
    return out


def parse_ls_surface_regions(data) -> list[tuple[str, np.ndarray]]:
    """Parse ``LS_SurfaceRegions`` into ``(name, gph_face_ids 0-based)``."""
    sec_start = find_section(data, "LS_SurfaceRegions")
    if sec_start < 0:
        return []
    sec_end = section_end(data, sec_start)
    blocks = list(iter_data_blocks(data, sec_start, sec_end))

    regions: list[tuple[str, np.ndarray]] = []
    i = 0
    while i + 2 < len(blocks):
        p_n, bc_n = blocks[i]
        p_i, bc_i = blocks[i + 1]
        p_w, bc_w = blocks[i + 2]
        name_raw = data[p_n : p_n + bc_n]
        if not all(b == 0 or 32 <= b < 127 for b in name_raw):
            i += 1
            continue
        name = name_raw.decode("ascii", errors="replace").strip("\x00").rstrip()
        if not name:
            i += 1
            continue
        if bc_i > 0 and bc_i == bc_w and bc_i % 4 == 0:
            face_ids = i32_be_array(data, p_i, bc_i // 4)
            regions.append((name, face_ids))
            i += 3
        else:
            i += 1
    return regions


def parse_ls_assemblies(data) -> dict:
    """Parse ``LS_Assemblies`` XML (part paths / root empty prefix)."""
    empty: dict = {
        "part_paths": {},
        "root_empty_prefix": None,
        "has_assemblies": False,
        "raw_xml": "",
    }
    sec_start = find_section(data, "LS_Assemblies")
    if sec_start < 0:
        return empty
    sec_end = section_end(data, sec_start)
    xml_bytes = b""
    for p, bc in iter_data_blocks(data, sec_start, sec_end):
        chunk = data[p : p + bc]
        if chunk.lstrip().startswith(b"<?xml") or b"<part" in chunk:
            xml_bytes = chunk
            break
    if not xml_bytes:
        return empty
    try:
        from xml.etree import ElementTree as ET
        root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))
    except Exception:
        return empty

    part_paths: dict[str, Optional[str]] = {}
    has_assemblies = any(True for _ in root.iter("assembly"))

    def _walk(node, ancestors: list[str]):
        for child in node:
            if child.tag == "assembly":
                aname = child.get("name", "")
                _walk(child, ancestors + [aname] if aname else ancestors)
            elif child.tag == "part":
                pname = child.get("name", "")
                if not pname:
                    continue
                part_paths[pname] = ".".join(ancestors + [pname]) if ancestors else None

    _walk(root, [])
    return {
        "part_paths": part_paths,
        "root_empty_prefix": empty.get("root_empty_prefix"),
        "has_assemblies": has_assemblies,
        "raw_xml": xml_bytes.decode("utf-8", errors="replace"),
    }


def classify_volume_region_cells(region_name: str, parts_with_cvol,
                                 cvol_id: Optional[np.ndarray], n_cells: int) -> np.ndarray:
    """Boolean cell-mask for a volume region / part name.

    ``FluidRegion`` = whole mesh; a region named after a Part selects exactly
    those part's cells (via cvol_id)."""
    all_mask = np.ones(n_cells, dtype=bool)
    if region_name == "FluidRegion":
        return all_mask
    if cvol_id is None or len(cvol_id) != n_cells or not parts_with_cvol:
        return all_mask
    name_to_cvol = {name: cv for name, cv in parts_with_cvol}
    if region_name in name_to_cvol:
        return part_cvol_cell_mask(cvol_id, name_to_cvol[region_name])
    if region_name.startswith("@VPartRegion_"):
        rem = region_name[len("@VPartRegion_"):]
        rem = rem.split("[", 1)[0]
        if rem in name_to_cvol:
            return part_cvol_cell_mask(cvol_id, name_to_cvol[rem])
    if region_name.startswith("FPHPARTS."):
        candidate = region_name[len("FPHPARTS."):].rsplit(".", 1)[-1]
        if candidate in name_to_cvol:
            return part_cvol_cell_mask(cvol_id, name_to_cvol[candidate])
    matches = sorted((p for p, _ in parts_with_cvol if p and p in region_name),
                     key=len, reverse=True)
    if matches:
        return part_cvol_cell_mask(cvol_id, name_to_cvol[matches[0]])
    return all_mask


# ─────────────────────────────────────────────────────────────────────────────
# GPH front-end
# ─────────────────────────────────────────────────────────────────────────────


def _renumber_by_first_use(face_nodes_flat: np.ndarray, n_vertices: int) -> np.ndarray:
    """Permutation ``perm`` s.t. ``perm[old] = new`` (first-use scan order)."""
    perm = np.full(n_vertices, -1, dtype=np.int64)
    flat = np.asarray(face_nodes_flat).reshape(-1)
    flat_valid = flat[(flat >= 0) & (flat < n_vertices)]
    if flat_valid.size:
        uniq, first_idx = np.unique(flat_valid, return_index=True)
        order = np.argsort(first_idx)
        unique_in_scan_order = uniq[order]
        perm[unique_in_scan_order] = np.arange(len(unique_in_scan_order), dtype=np.int64)
        next_id = len(unique_in_scan_order)
    else:
        next_id = 0
    missing = np.where(perm == -1)[0]
    perm[missing] = np.arange(next_id, next_id + missing.size, dtype=np.int64)
    return perm


def _n_cells_array(data, name: str, n_cells: int, elem: int,
                  dtype: str = "f4") -> Optional[np.ndarray]:
    """Payload after a ``[12][4][n_cells][1]`` descriptor in *name* section.

    Used for per-element arrays (Element_InformationFlag i4 /
    Element_Center f32).
    """
    sec = find_section(data, name)
    if sec < 0 or n_cells <= 0:
        return None
    end = section_end(data, sec)
    pos = sec + 40
    while pos + 16 <= end:
        if read_i32_be(data, pos) != 12:
            pos += 4
            continue
        v = read_i32_be(data, pos + 4)
        n0 = read_i32_be(data, pos + 8)
        n1 = read_i32_be(data, pos + 12)
        if v == 4 and n0 == n_cells and n1 == 1:
            p2 = pos + 16
            plen = n0 * elem
            if (p2 + 8 + plen + 4 <= end
                    and read_i32_be(data, p2) == 12
                    and read_i32_be(data, p2 + 4) == plen
                    and read_i32_be(data, p2 + 8 + plen) == plen):
                if dtype == "i4":
                    return i32_be_array(data, p2 + 8, n0).astype(np.int64)
                return f32_be_array(data, p2 + 8, n0).astype(np.float64)
        pos += 4
    return None


def parse_element_information_flag(data, n_cells: int) -> Optional[np.ndarray]:
    """Element_InformationFlag → per-element flag array (int64)."""
    return _n_cells_array(data, "Element_InformationFlag", n_cells, 4,
                          dtype="i4")


def parse_element_centers(data, n_cells: int) -> Optional[np.ndarray]:
    """Element_Center → ``(n_cells, 3)`` float64 precomputed cell centres.

    Layout: three ``[12][4][n_cells][1]`` + ``[12][4*n_cells]`` float32
    coordinate payloads (X, Y, Z).
    """
    sec = find_section(data, "Element_Center")
    if sec < 0 or n_cells <= 0:
        return None
    end = section_end(data, sec)
    comps: list[np.ndarray] = []
    pos = sec + 40
    while pos + 16 <= end and len(comps) < 3:
        if read_i32_be(data, pos) != 12:
            pos += 4
            continue
        v = read_i32_be(data, pos + 4)
        n0 = read_i32_be(data, pos + 8)
        n1 = read_i32_be(data, pos + 12)
        if v == 4 and n0 == n_cells and n1 == 1:
            p2 = pos + 16
            plen = n0 * 4
            if (p2 + 8 + plen + 4 <= end
                    and read_i32_be(data, p2) == 12
                    and read_i32_be(data, p2 + 4) == plen
                    and read_i32_be(data, p2 + 8 + plen) == plen):
                comps.append(f32_be_array(data, p2 + 8, n0))
                pos = p2 + 8 + plen + 4
                continue
        pos += 4
    if len(comps) != 3 or any(a.size != n_cells for a in comps):
        return None
    return np.column_stack(comps).astype(np.float64)

def parse_gph_mesh(filepath: str) -> dict:
    """Extract mesh data (vertices, faces, parts) from a GPH / FPH file."""
    with open_buffer(filepath) as data:
        result: dict = {
            "file_size": len(data),
            "vertices": None,
            "n_vertices": 0,
            "link_data": None,
            "n_cells": 0,
            "cvol_id": None,
            "volume_regions": [],
            "parts": [],
            "parts_with_cvol": [],
            "part_assembly": {},
            "assembly_info": None,
            "surface_regions": [],
            "element_flags": None,
            "element_centers": None,
            "meta": {},
        }

        xyz, n_vertices = parse_ls_nodes_xyz(data)
        link_data = parse_ls_links(data)

        result["assembly_info"] = parse_ls_assemblies(data)
        result["cvol_id"] = parse_ls_cvol_ids(data)
        result["parts_with_cvol"] = parse_ls_parts(data, cvol_id=result["cvol_id"])
        result["parts"] = [name for name, _ in result["parts_with_cvol"]]
        result["volume_regions"] = parse_ls_string_list(data, "LS_VolumeRegions")
        result["surface_regions"] = parse_ls_surface_regions(data)
        legacy_part_asm: dict = {}
        if result["assembly_info"]:
            for pname, path in result["assembly_info"]["part_paths"].items():
                if path is None:
                    legacy_part_asm[pname] = None
                else:
                    comps = path.split(".")
                    legacy_part_asm[pname] = comps[-2] if len(comps) >= 2 else None
        result["part_assembly"] = legacy_part_asm

        if xyz is None or n_vertices == 0 or link_data is None:
            return result

        fn = link_data["face_nodes"]
        bad = fn >= n_vertices
        if bad.any():
            fn = fn.copy()
            fn[bad] = n_vertices - 1
            link_data["face_nodes"] = fn

        perm = _renumber_by_first_use(link_data["face_nodes"], n_vertices)
        inv_perm = np.argsort(perm)
        xyz_renum = xyz[inv_perm]
        link_data["face_nodes"] = perm[link_data["face_nodes"]]
        link_data["face_offsets"] = link_data["face_offsets"]

        result["vertices"] = xyz_renum
        result["n_vertices"] = n_vertices
        result["link_data"] = link_data
        result["n_cells"] = link_data["n_cells"]
        result["meta"] = parse_header_meta(data)
        result["element_flags"] = parse_element_information_flag(
            data, result["n_cells"])
        result["element_centers"] = parse_element_centers(
            data, result["n_cells"])
        return result


__all__ = [
    "parse_gph_mesh",
    "parse_ls_nodes_xyz",
    "parse_ls_links",
    "parse_ls_cvol_ids",
    "parse_ls_string_list",
    "parse_ls_parts",
    "parse_ls_surface_regions",
    "parse_ls_assemblies",
    "classify_volume_region_cells",
    "part_cvol_cell_mask",
]