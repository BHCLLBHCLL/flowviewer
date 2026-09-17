"""CGNS-HDF5 reader (P1.2, P2.1).

Reads the standard CGNS SIDS tree stored in HDF5 (h5py) into the
same dict shape the mesh parsers produce: vertices, cell connectivity,
node/cell fields, volume region names and boundary condition faces.

P2.1: MIXED element streams are decoded per element; multiple zones
(including Structured zones, converted to HEXA_8 grids) are merged
into one mesh with vertex indices offset per zone.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np

_LOG = logging.getLogger(__name__)

try:
    import h5py
    _HAS_H5 = True
except Exception:  # pragma: no cover - optional dep
    _HAS_H5 = False


# CGNS ElementType numeric codes (SIDS ElementType_t) -> type names.
#
# R124: 22/23 are NGON_n (faces) and NFACE_n (cells) -- the polyhedral
# sections a Cradle FPH-sourced export actually writes.  They were missing
# from this table, so such a file reported every cell section as an unknown
# type and opened with ZERO cells (measured on tr03_9_orig.cgns and
# exPRE04-1_37.cgns, both entirely polyhedral).
_CODE_TO_NAME = {
    2: "NODE", 3: "BAR_2", 4: "BAR_3", 5: "TRI_3", 6: "TRI_6",
    7: "QUAD_4", 8: "QUAD_8", 9: "QUAD_9", 10: "TETRA_4", 11: "TETRA_10",
    12: "PYRA_5", 13: "PYRA_14", 14: "PENTA_6", 15: "PENTA_15",
    16: "PENTA_18", 17: "HEXA_8", 18: "HEXA_20", 19: "HEXA_27",
    20: "MIXED", 21: "PYRA_13", 22: "NGON_n", 23: "NFACE_n",
}

#: CGNS SIDS bookkeeping nodes that live *inside* FlowSolution_t next to the
#: real data arrays.  R124: GridLocation was read as if it were a field, so
#: every Cradle CGNS file gained a bogus "GridLocation" variable whose values
#: were the ASCII codes of the string "CellCenter".
_SIDS_NON_FIELDS = frozenset({
    "GridLocation", "Descriptor", "DataClass", "DimensionalUnits",
    "DimensionalExponents", "AdditionalFamilyName", "FamilyName",
    "FlowSolution_t", "GridConnectivity", "Periodic",
})

#: GridLocation values that make a field node- or cell-centred.
_NODE_LOCATIONS = frozenset({"Vertex", "VertexBased"})
_CELL_LOCATIONS = frozenset({"CellCenter", "CellBased"})

#: GridLocation values that index faces, i.e. what ZoneBC PointList holds for
#: a boundary condition written on a face-based (polyhedral) zone.
_FACE_LOCATIONS = frozenset({"FaceCenter", "IFaceCenter", "JFaceCenter",
                             "KFaceCenter", "FaceBased"})

# SIDS element code -> (vtk cell type, n_nodes) for MIXED streams (P2.1).
#
# R111: 13/14 were swapped against the SIDS table (cgnslib.h: PYRA_5=12,
# PYRA_14=13, PENTA_6=14).  With the old mapping a PENTA_6 element was
# consumed as a 5-node pyramid, so the stream desynchronised and every later
# element in that section was lost or mis-typed.  Codes 22/23 (NGON_n /
# NFACE_n polyhedra) are carried through with n_nodes = -1: their size is
# per element and must be read from the stream, which _decode_mixed does not
# implement yet (R124).
_CODE_CELLS = {
    5: (5, 3),     # TRI_3
    7: (9, 4),     # QUAD_4
    10: (10, 4),   # TETRA_4
    12: (14, 5),   # PYRA_5
    13: (14, 5),   # PYRA_14 -> rendered as its 5 base nodes
    14: (13, 6),   # PENTA_6
    17: (12, 8),   # HEXA_8
}


def _elem_type_name(sec) -> str:
    """Element type of an Elements_t section (code or string)."""
    d = _data_of(sec)
    if d is None:
        return _attr_text(sec, "data")
    if d.dtype.kind in "iu":
        return _CODE_TO_NAME.get(int(np.asarray(d).ravel()[0]), "")
    return _attr_text(sec, "data")

# CGNS ElementType codes (SIDS) relevant to volume meshes
_VTK_FOR_CGNS = {
    "TETRA_4": (10, 4),     # (vtk type, n_nodes)
    "HEXA_8": (12, 8),
    "PENTA_6": (13, 6),
    "PYRA_5": (14, 5),
    "TRI_3": (5, 3),
    "QUAD_4": (9, 4),
}

_CELL_TYPES = {10: "TETRA_4", 12: "HEXA_8", 13: "PENTA_6", 14: "PYRA_5"}

_VOLUME_TYPES = {"TETRA_4", "HEXA_8", "PENTA_6", "PYRA_5"}



def _data_of(group):
    """Read the 'data' dataset of a CGNS node (name may be ' data').

    Accepts both the standard node mapping (group wrapping a `` data``
    dataset) and bare datasets written by non-conforming tools.
    """
    if group is None:
        return None
    if isinstance(group, h5py.Dataset):
        return group[()]
    if "data" in group:
        return group["data"][()]
    if " data" in group:
        return group[" data"][()]
    return None


def _attr_text(group, name: str) -> str:
    try:
        node = group[name]
        arr = _data_of(node)
    except Exception:
        return ""
    if arr is None:
        return ""
    if isinstance(arr, bytes):
        return arr.decode("utf-8", "replace").strip("\x00").strip()
    try:
        return b"".join(arr).decode("utf-8", "replace").strip("\x00").strip()
    except Exception:
        return ""


def _children(group) -> list:
    """Ordered (name, obj) pairs of a h5py group."""
    return [(k, group[k]) for k in group.keys()]


def _zone_type(zone) -> str:
    zt = zone.get("ZoneType")
    if zt is None:
        return "Unstructured"
    arr = _data_of(zt)
    if arr is not None:
        try:
            txt = b"".join(np.asarray(arr).ravel()).decode(
                "utf-8", "replace").strip("\x00").strip()
            if txt:
                return txt
        except Exception:
            pass
    return _attr_text(zt, "data") or "Unstructured"


def _read_coordinates(zone) -> Optional[np.ndarray]:
    gc = zone.get("GridCoordinates")
    if gc is None:
        return None
    comps = []
    for axis in ("CoordinateX", "CoordinateY", "CoordinateZ"):
        c = gc.get(axis)
        arr = _data_of(c) if c is not None else None
        if arr is None:
            return None
        comps.append(np.asarray(arr, dtype=np.float64))
    if len(comps) != 3 or any(a.size == 0 for a in comps):
        return None
    return np.column_stack(comps)


def _elements_sections(zone) -> list:
    """Every Elements_t section (volume or boundary) in the zone."""
    out = []
    for name, obj in _children(zone):
        if not isinstance(obj, h5py.Group):
            continue
        if "ElementConnectivity" in obj and "ElementRange" in obj:
            out.append((name, obj))
    return out


def _read_mixed_stream(conn):
    """Decode a MIXED connectivity stream -> (rows, vtk_types) (P2.1).

    The flat array holds ``[type_code, node_1..node_k, ...]`` per
    element; rows are padded to the widest element with -1 (renderers
    read only the first n_nodes entries per type).
    """
    stream = np.asarray(conn, dtype=np.int64).ravel()
    rows = []
    types = []
    i = 0
    n = stream.size
    while i < n:
        code = int(stream[i])
        info = _CODE_CELLS.get(code)
        if info is None:
            break  # unknown code: stop rather than mis-align
        vtk_t, nn = info
        rows.append(stream[i + 1:i + 1 + nn] - 1)
        types.append(vtk_t)
        i += 1 + nn
    if not rows:
        return None, None
    width = max(r.size for r in rows)
    out = np.full((len(rows), width), -1, dtype=np.int64)
    for k, r in enumerate(rows):
        out[k, :r.size] = r
    return out, np.asarray(types, dtype=np.int64)


# ---------------------------------------------------------------------------
# R124: polyhedral sections (NGON_n faces / NFACE_n cells)
# ---------------------------------------------------------------------------

#: Faces of each fixed-size volume element, as indices into the zone's local
#: node list.  Only the decomposition has to be right: the face table is keyed
#: on the sorted node set and the orientation is fixed up from the owner.
_ELEMENT_FACES = {
    10: ((0, 2, 1), (0, 1, 3), (1, 2, 3), (0, 3, 2)),              # TETRA_4
    12: ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
         (2, 3, 7, 6), (3, 0, 4, 7)),                              # HEXA_8
    13: ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4),
         (2, 0, 3, 5)),                                            # PENTA_6
    14: ((0, 3, 2, 1), (0, 1, 4), (1, 2, 4), (2, 3, 4),
         (3, 0, 4)),                                               # PYRA_5
}


def _section_code(sec) -> int:
    """Numeric ElementType code of an Elements_t section (-1 when absent)."""
    for key in (" data", "data"):
        if key in sec:
            arr = np.asarray(sec[key][()]).ravel()
            if arr.size:
                return int(arr[0])
    return -1


def _section_range(sec):
    """ElementRange (first, last) 1-based, or None."""
    rng = sec.get("ElementRange")
    arr = _data_of(rng) if rng is not None else None
    if arr is None:
        return None
    arr = np.asarray(arr, dtype=np.int64).ravel()
    return (int(arr[0]), int(arr[1])) if arr.size >= 2 else None


def _offsets_of(sec, n_elems: int):
    """ElementStartOffset as a 0-based offset array, or None.

    CGNS stores a variable-length section either with an explicit
    ElementStartOffset (length n_elems + 1, as Cradle writes it) or as a
    [count, ids...] stream; the caller falls back to :func:_stream_rows.
    """
    node = sec.get("ElementStartOffset")
    arr = _data_of(node) if node is not None else None
    if arr is None:
        return None
    off = np.asarray(arr, dtype=np.int64).ravel()
    if n_elems and off.size == n_elems + 1:
        return off
    if n_elems and off.size == n_elems:
        return np.concatenate([off, off[-1:]])
    return None


def _stream_rows(conn):
    """Decode a [count, ids...] connectivity stream -> (offsets, flat)."""
    stream = np.asarray(conn, dtype=np.int64).ravel()
    rows = []
    i = 0
    n = stream.size
    while i < n:
        k = int(stream[i])
        if k <= 0 or i + 1 + k > n:
            break
        rows.append(stream[i + 1:i + 1 + k])
        i += 1 + k
    if not rows:
        return None, None
    offsets = np.zeros(len(rows) + 1, dtype=np.int64)
    np.cumsum([r.size for r in rows], out=offsets[1:])
    return offsets, np.concatenate(rows)


def _pad_ragged(flat, offsets, width=None):
    """Ragged flat data -> (n_rows, width) padded with -1."""
    flat = np.asarray(flat, dtype=np.int64)
    offsets = np.asarray(offsets, dtype=np.int64)
    cnt = np.diff(offsets)
    n_rows = int(cnt.size)
    if width is None:
        width = int(cnt.max()) if n_rows else 0
    out = np.full((n_rows, width), -1, dtype=np.int64)
    if n_rows and width:
        mask = np.arange(width)[None, :] < cnt[:, None]
        out[mask] = flat
    return out


def _ngon_table(sec):
    """NGON_n section -> (face_offsets, face_nodes 0-based) or None."""
    conn = _data_of(sec["ElementConnectivity"])
    if conn is None:
        return None
    conn = np.asarray(conn, dtype=np.int64).ravel()
    rng = _section_range(sec)
    n_faces = int(rng[1] - rng[0] + 1) if rng else 0
    off = _offsets_of(sec, n_faces)
    if off is None:
        off, conn = _stream_rows(conn)
        if off is None:
            return None
    if off.size < 2:
        return None
    nodes = conn - 1
    if nodes.size and int(nodes.min()) < -1:
        # CGNS connectivity is 1-based; a node id below 1 means the section
        # is not what its type code claims, so refuse it rather than shift it.
        _LOG.warning("NGON_n section %r: node id below 1, skipped", sec.name)
        return None
    return off, nodes


def _nface_refs(sec):
    """NFACE_n section -> (cell_offsets, face ids 1-based, reverse mask)."""
    conn = _data_of(sec["ElementConnectivity"])
    if conn is None:
        return None
    conn = np.asarray(conn, dtype=np.int64).ravel()
    rng = _section_range(sec)
    n_cells = int(rng[1] - rng[0] + 1) if rng else 0
    off = _offsets_of(sec, n_cells)
    if off is None:
        off, conn = _stream_rows(conn)
        if off is None:
            return None
    if off.size < 2:
        return None
    return off, np.abs(conn), conn < 0


def _element_face_instances(conn, ctypes):
    """Per-(cell, face) instances for fixed-size elements (R124).

    Returns (rows, counts, cell) with rows padded to the widest face.  Each
    instance is one face entry candidate; the shared-face collapse happens
    afterwards, keyed on the sorted node set, so a zone mixing polyhedral and
    fixed-size element sections still ends up in one face table.
    """
    conn = np.asarray(conn, dtype=np.int64)
    ctypes = np.asarray(ctypes, dtype=np.int64)
    parts = []
    counts = []
    cells = []
    for code in sorted(_ELEMENT_FACES):
        sel = np.flatnonzero(ctypes == code)
        if sel.size == 0:
            continue
        block = conn[sel]
        for face in _ELEMENT_FACES[code]:
            cols = np.asarray(face, dtype=np.int64)
            if cols.size > block.shape[1]:  # pragma: no cover - defensive
                continue
            parts.append(np.asarray(block[:, cols]))
            counts.append(np.full(sel.size, cols.size, dtype=np.int64))
            cells.append(sel)
    if not parts:
        return None
    width = max(p.shape[1] for p in parts)
    rows = np.full((sum(p.shape[0] for p in parts), width), -1, dtype=np.int64)
    r = 0
    for p in parts:
        rows[r:r + p.shape[0], :p.shape[1]] = p
        r += p.shape[0]
    cells_all = np.concatenate(cells)
    order = np.argsort(cells_all, kind="stable")
    return (rows[order], np.concatenate(counts)[order], cells_all[order])


def _dedupe_rows(rows, counts):
    """Collapse identical padded rows.

    Returns (inverse, representative node list, representative counts,
    n_unique) with rows in first-appearance order.  Generated per-cell faces
    of a fixed-size element zone are duplicated between the two cells sharing
    them, so they are keyed on the sorted node set; NGON_n faces are already
    unique in the file and keep their element numbering, which ZoneBC
    PointList ids depend on.
    """
    width = rows.shape[1]
    n_v = int(rows.max()) + 1 if rows.size else 0
    valid = np.arange(width)[None, :] < counts[:, None]
    key = np.sort(np.where(valid, rows, n_v), axis=1)
    dt = np.dtype((np.void, key.dtype.itemsize * width))
    uniq, first_idx, inverse = np.unique(
        np.ascontiguousarray(key).view(dt).ravel(),
        return_index=True, return_inverse=True)
    rep_counts = counts[first_idx]
    rep = rows[first_idx]
    mask = np.arange(width)[None, :] < rep_counts[:, None]
    return (inverse.astype(np.int64), rep[mask], rep_counts, int(uniq.size))


def _owner_neighbour(face_of, cell_of, reverse, n_faces):
    """Owner/neighbour per face from the per-instance face references (R124).

    A boundary face is referenced once; an interior face twice, and the CGNS
    negative-orientation sign then says which of the two cells stores the
    outward order -- that cell owns the face.  Faces no cell references keep
    owner -1 (they stay in the table so ZoneBC ids keep addressing them).
    """
    owner = np.full(n_faces, -1, dtype=np.int64)
    neighbour = np.full(n_faces, -1, dtype=np.int64)
    if face_of.size == 0:
        return owner, neighbour
    occ = np.bincount(face_of, minlength=n_faces)
    order = np.argsort(face_of, kind="stable")
    starts = np.concatenate([[0], np.cumsum(occ)[:-1]])
    last = order.size - 1
    first = order[np.minimum(starts, last)]
    owner = np.where(occ >= 1, cell_of[first], -1)
    two = occ >= 2
    if bool(two.any()):
        second = order[np.minimum(starts + 1, last)]
        if reverse is not None:
            swap = two & reverse[first] & ~reverse[second]
            neighbour = np.where(two, np.where(swap, cell_of[first],
                                                cell_of[second]), -1)
            owner = np.where(swap, cell_of[second], owner)
        else:
            neighbour = np.where(two, cell_of[second], -1)
    if int(occ.max()) > 2:
        _LOG.warning("CGNS face table: %d faces are referenced by more than "
                     "two cells", int((occ > 2).sum()))
    return owner, neighbour


def _poly_zone_faces(ngon_secs, nface_secs, elem_conn, elem_types):
    """Face instances of one polyhedral zone (R124).

    NFACE_n lists, per cell, the element ids of its faces (1-based, in the
    zone's face-element numbering) with a negative sign when the stored face
    orientation points into the cell.  Those ids are mapped onto the
    concatenated NGON_n face table, and any fixed-size element sections in the
    same zone add their own faces, so a zone always yields one instance list.
    """
    tables = []
    spans = []          # (base id, count, local offset)
    local_off = 0
    for sec in ngon_secs:
        got = _ngon_table(sec)
        if got is None:
            continue
        off, nodes = got
        rng = _section_range(sec)
        base = rng[0] if rng else 1
        n_faces = off.size - 1
        tables.append((off, nodes))
        spans.append((base, n_faces, local_off))
        local_off += n_faces
    if not spans:
        return None
    face_nodes = np.concatenate([t[1] for t in tables])
    face_offsets = np.zeros(local_off + 1, dtype=np.int64)
    r = 0
    for off, _nodes in tables:
        face_offsets[r:r + off.size] = off + face_offsets[r]
        r += off.size - 1
    # element id -> local face index
    base_min = min(s[0] for s in spans)
    base_max = max(s[0] + s[1] for s in spans)
    id_map = np.full(base_max - base_min, -1, dtype=np.int64)
    for base, count, off in spans:
        id_map[base - base_min:base - base_min + count] = off + np.arange(count)

    inst_face = []
    inst_cell = []
    inst_rev = []
    n_cells = 0
    for sec in nface_secs:
        got = _nface_refs(sec)
        if got is None:
            continue
        off, ids, reverse = got
        n_z = off.size - 1
        cell_of = np.repeat(np.arange(n_cells, n_cells + n_z, dtype=np.int64),
                            np.diff(off))
        n_cells += n_z
        if cell_of.size != ids.size:
            # ElementStartOffset and the connectivity must agree; if a writer
            # disagrees, follow the shorter of the two and say so instead of
            # indexing out of bounds.
            n_ref = min(int(cell_of.size), int(ids.size))
            _LOG.warning("NFACE_n section %r: start offsets cover %d "
                         "references but the connectivity holds %d; using the "
                         "shorter", sec.name, cell_of.size, ids.size)
            cell_of = cell_of[:n_ref]
            ids = ids[:n_ref]
            reverse = reverse[:n_ref]
        idx = ids - base_min
        ok = (idx >= 0) & (idx < id_map.size) & (ids > 0)
        if not bool(ok.all()):
            _LOG.warning("NFACE_n section %r: %d face references outside the "
                         "NGON_n range", sec.name, int((~ok).sum()))
        safe = np.clip(idx, 0, max(0, id_map.size - 1))
        local = np.where(ok, id_map[safe], -1)
        keep = local >= 0
        if bool(keep.any()):
            inst_face.append(local[keep])
            inst_cell.append(cell_of[keep])
            inst_rev.append(reverse[keep])
    if elem_conn:
        merged_conn = _pad_stack(elem_conn)
        n_elem = int(merged_conn.shape[0])
        inst = _element_face_instances(
            merged_conn, np.asarray(elem_types, dtype=np.int64))
        if inst is not None:
            rows_e, counts_e, cells_e = inst
            inv, gen_nodes, gen_counts, n_gen = _dedupe_rows(rows_e, counts_e)
            base = int(face_offsets[-1])
            face_offsets = np.concatenate(
                [face_offsets, base + np.cumsum(gen_counts)])
            face_nodes = np.concatenate([face_nodes, gen_nodes])
            inst_face.append(inv + local_off)
            inst_cell.append(cells_e + n_cells)
            inst_rev.append(np.zeros(inv.size, dtype=bool))
            n_cells += n_elem
    if not inst_face:
        return None
    face_of = np.concatenate(inst_face)
    cell_of = np.concatenate(inst_cell)
    reverse_i = np.concatenate(inst_rev)
    # cell-ordered instances, so the cell face lists are contiguous
    order = np.argsort(cell_of, kind="stable")
    face_of = face_of[order]
    cell_of = cell_of[order]
    reverse_i = reverse_i[order]
    n_faces = int(face_offsets.size - 1)
    owner, neighbour = _owner_neighbour(face_of, cell_of, reverse_i, n_faces)
    cell_faces_offsets = np.zeros(n_cells + 1, dtype=np.int64)
    np.cumsum(np.bincount(cell_of, minlength=n_cells),
              out=cell_faces_offsets[1:])
    npe = np.diff(face_offsets)
    table = {
        "n_faces": n_faces,
        "npe": npe,
        "face_nodes": face_nodes,
        "face_offsets": face_offsets,
        "owner": owner,
        "neighbour": neighbour,
        "boundary_faces": np.flatnonzero((neighbour < 0) & (owner >= 0)),
        "cell_faces": face_of,
        "cell_faces_offsets": cell_faces_offsets,
        "n_cells": n_cells,
    }
    table["cell_conn"] = _pad_ragged(face_of, cell_faces_offsets)
    table["cell_types"] = np.full(n_cells, 42, dtype=np.int64)
    # ZoneBC PointList ids are element ids of the zone, so a zone whose face
    # range does not start at 1 needs this base subtracted to index the table.
    table["face_base"] = base_min
    return table


def _read_cells(zone):
    """Read volume cells.

    Returns (cell_conn, cell_types, poly).  poly is None for a zone built from
    fixed-size element sections (the historical node-connectivity path).  For a
    polyhedral zone (NGON_n + NFACE_n, as Cradle writes for FPH-sourced
    exports) it carries the zone face instances so the merge can build the
    link_data face table the renderer needs.
    """
    cell_conn = []
    cell_types = []
    ngon = []
    nface = []
    for name, sec in _elements_sections(zone):
        et = _elem_type_name(sec)
        conn = _data_of(sec["ElementConnectivity"])
        if conn is None or conn.size == 0:
            continue
        if et == "NGON_n":
            ngon.append(sec)
            continue
        if et == "NFACE_n":
            nface.append(sec)
            continue
        if et in _VOLUME_TYPES:
            vtk_t, nn = _VTK_FOR_CGNS[et]
            n_elems = conn.size // nn
            arr = np.asarray(conn, dtype=np.int64).reshape(n_elems, nn) - 1
            cell_conn.append(arr)
            cell_types.extend([vtk_t] * n_elems)
        elif et == "MIXED":
            # P2.1: decode the per-element [code, nodes...] stream
            rows, types = _read_mixed_stream(conn)
            if rows is not None:
                cell_conn.append(rows)
                cell_types.extend(int(t) for t in types)
        else:
            # Boundary-only section (TRI_3 / QUAD_4 etc.) - skip
            continue
    if not nface:
        if not cell_conn:
            return None, None, None
        width = max(a.shape[1] for a in cell_conn)
        merged = np.full((sum(a.shape[0] for a in cell_conn), width),
                         -1, dtype=np.int64)
        r = 0
        for a in cell_conn:
            merged[r:r + a.shape[0], :a.shape[1]] = a
            r += a.shape[0]
        return merged, np.asarray(cell_types, dtype=np.int64), None
    poly = _poly_zone_faces(ngon, nface, cell_conn, cell_types)
    if poly is None:
        return None, None, None
    return poly["cell_conn"], poly["cell_types"], poly


def _structured_zone(zone):
    """Structured zone -> (vertices, hexa_conn) or None (P2.1).

    GridCoordinates arrays are (nk, nj, ni); node id = ((k*nj)+j)*ni+i.
    Cells become HEXA_8 bricks across the (i, j, k) lattice.
    """
    gc = zone.get("GridCoordinates")
    if gc is None:
        return None
    comps = []
    dims = None
    for axis in ("CoordinateX", "CoordinateY", "CoordinateZ"):
        c = gc.get(axis)
        arr = _data_of(c) if c is not None else None
        if arr is None:
            return None
        a = np.asarray(arr, dtype=np.float64)
        if a.ndim == 1:
            a = a.reshape(a.size, 1, 1)
        if dims is None:
            dims = a.shape
        elif a.shape != dims:
            return None
        comps.append(a)
    assert dims is not None          # set by the first axis, all axes agree
    nk, nj, ni = dims[0], dims[1], dims[2]
    vertices = np.stack([c.ravel(order="C") for c in comps], axis=1)
    if ni < 2 or nj < 2 or nk < 2:
        return vertices, None
    ii, jj, kk = np.meshgrid(np.arange(ni - 1), np.arange(nj - 1),
                             np.arange(nk - 1), indexing="ij")
    base = ((kk * nj) + jj) * ni + ii
    j_off = ((kk * nj) + (jj + 1)) * ni    # +1 in j
    k_off = (((kk + 1) * nj) + jj) * ni    # +1 in k
    conn = np.stack([
        base, base + 1, j_off + ii + 1, j_off + ii,
        k_off + ii, k_off + ii + 1,
        ((kk + 1) * nj + jj + 1) * ni + ii + 1,
        ((kk + 1) * nj + jj + 1) * ni + ii,
    ], axis=-1).reshape(-1, 8)
    return vertices, conn


def _text_of(group, name: str) -> str:
    """Text of a CGNS string node ('GridLocation', 'ZoneType', ...)."""
    node = group.get(name)
    arr = _data_of(node) if node is not None else None
    if arr is None:
        return ""
    a = np.asarray(arr).ravel()
    if a.dtype.kind == "S":            # fixed-width char array
        return b"".join(a).decode("ascii", "replace").strip("\x00 \t\r\n")
    if a.dtype.kind == "U":            # h5py str dtype
        return "".join(a.tolist()).strip("\x00 \t\r\n")
    try:                               # int8 / uint8 character codes
        raw = a.astype("uint8").tobytes()
    except Exception:  # pragma: no cover - defensive
        return ""
    return raw.decode("ascii", "replace").strip("\x00 \t\r\n")


def _guess_location(size: int, n_nodes: int, n_cells: int) -> str:
    """Field location from its length, for files without GridLocation.

    Returns "" when the length matches neither side, so the field is reported
    as skipped instead of being attached to the wrong mesh entities.
    """
    if n_cells and size == n_cells and size != n_nodes:
        return "cell"
    if size == n_nodes:
        return "node"
    return ""


def _location_of(text: str, size: int, n_nodes: int, n_cells: int) -> str:
    """GridLocation text -> 'node' / 'cell' / "" (unsupported or unknown)."""
    if text in _NODE_LOCATIONS:
        return "node"
    if text in _CELL_LOCATIONS:
        return "cell"
    if text:
        return ""
    return _guess_location(size, n_nodes, n_cells)


def _flow_solution_groups(zone) -> list:
    """Every FlowSolution container of a zone, in file order."""
    out = []
    for name, obj in _children(zone):
        if not isinstance(obj, h5py.Group):
            continue
        if name.startswith("FlowSolution") or "GridLocation" in obj:
            out.append((name, obj))
    return out


def _point_ids(obj):
    """ZoneBC point ids as a flat 1-based array (PointList or PointRange)."""
    pl = obj.get("PointList")
    arr = _data_of(pl) if pl is not None else None
    if arr is not None:
        return np.asarray(arr, dtype=np.int64).ravel()
    pr = obj.get("PointRange")
    arr = _data_of(pr) if pr is not None else None
    if arr is None:
        return None
    rng = np.asarray(arr, dtype=np.int64).ravel()
    if rng.size < 2:
        return None
    step = int(rng[2]) if rng.size > 2 and int(rng[2]) else 1
    return np.arange(int(rng[0]), int(rng[1]) + 1, step, dtype=np.int64)


def _read_flow_solution(zone, n_nodes: int, n_cells: int = 0,
                        lazy: bool = False):
    """FlowSolution fields -> dict name -> (array, location).

    ``lazy=True`` (R28) skips payload reads: each field maps to a
    ``(ds_path, size)`` descriptor — the HDF5 dataset's absolute path and
    element count taken from shape metadata only, so a lazy open never
    touches field payloads.

    R124: the location comes from the group's GridLocation node instead of
    being guessed from the array length (which labelled a cell field as node
    data whenever a zone had as many cells as nodes), every FlowSolution
    index is read (later indices win), and the SIDS bookkeeping nodes stored
    beside the data arrays are no longer offered as variables.
    """
    out: dict = {}
    skipped: list = []
    for _gname, fs in _flow_solution_groups(zone):
        loc_text = _text_of(fs, "GridLocation")
        for name, obj in _children(fs):
            if name in _SIDS_NON_FIELDS:
                continue
            if not isinstance(obj, h5py.Group):
                continue
            ds = None
            if "data" in obj:
                ds = obj["data"]
            elif " data" in obj:
                ds = obj[" data"]
            if not isinstance(ds, h5py.Dataset):
                continue
            size = int(ds.shape[0]) if ds.shape else 0
            loc = _location_of(loc_text, size, n_nodes, n_cells)
            if not loc:
                skipped.append((name, "GridLocation=%r" % (loc_text,)
                                if loc_text else "size %d matches neither the "
                                "%d nodes nor the %d cells"
                                % (size, n_nodes, n_cells)))
                continue
            if lazy:
                if len(ds.shape) != 1 or size == 0:
                    continue
                out[name] = (ds.name, size, loc)
                continue
            try:
                arr = np.asarray(ds[()], dtype=np.float64)
            except Exception as exc:
                # R111: an unreadable field used to vanish from the variable
                # list with no trace at all.  Keep the load going (one bad
                # array must not fail the whole file) but record it.
                skipped.append((name, "%s: %s" % (type(exc).__name__, exc)))
                continue
            if arr.ndim != 1 or arr.size == 0:
                continue
            out[name] = (arr, loc)
    if skipped:
        # R111: surface the fields that could not be read instead of letting
        # them disappear from the variable list silently.  Callers merge this
        # into FieldFile.meta["skipped_fields"].
        for fname, why in skipped:
            _LOG.warning("CGNS field %r skipped: %s", fname, why)
        out["__skipped__"] = skipped
    return out


def _read_bcs(zone, face_base: int = 1):
    """ZoneBC boundary conditions -> ([(name, face_ids 0-based)], skipped).

    R124: PointList holds 1-based *element* ids when GridLocation is a face
    location (FaceCenter / IFaceCenter / ...) and node ids when it is Vertex,
    so the first element id of the zone's face section is subtracted and
    Vertex BCs are reported as unrepresentable instead of being indexed as
    faces (the old code always subtracted 1, which silently mis-addressed
    every BC of a zone whose face range does not start at 1).
    """
    out: list = []
    skipped: list = []
    zbc = zone.get("ZoneBC")
    if zbc is None:
        return out, skipped
    for name, obj in _children(zbc):
        if not isinstance(obj, h5py.Group):
            continue
        ids = _point_ids(obj)
        if ids is None or ids.size == 0:
            continue
        loc = _text_of(obj, "GridLocation")
        if loc and loc not in _FACE_LOCATIONS:
            skipped.append((name, loc))
            continue
        out.append((name, ids - int(face_base)))
    return out, skipped


def _pad_stack(arrays: list) -> np.ndarray:
    """Stack 2-D int arrays of differing widths, padding with -1."""
    width = max(a.shape[1] for a in arrays)
    total = sum(a.shape[0] for a in arrays)
    out = np.full((total, width), -1, dtype=np.int64)
    r = 0
    for a in arrays:
        out[r:r + a.shape[0], :a.shape[1]] = a
        r += a.shape[0]
    return out


def _decode_zone(zone, ztype: str, lazy_fields: bool = False):
    """Decode one HDF5 zone -> (verts, conn, ctypes, fields, bcs, n_v, n_c).

    ``fields`` is the per-zone FlowSolution dict name -> (array, location);
    ``bcs`` the ZoneBC [(name, ids)] list. All rows are zone-local (no
    vertex offset applied) so the caller can merge in zone order.

    R124: returns one record dict per zone (zone, verts, conn, ctypes, poly,
    fields, bcs, vertex_bcs, n_v, n_c).  poly carries the zone face table of a
    polyhedral zone; vertex_bcs lists the ZoneBC entries whose GridLocation
    indexes nodes rather than faces, which cannot become face regions.
    """
    poly = None
    if ztype == "Structured":
        out = _structured_zone(zone)
        if out is None:
            return None
        verts, conn = out
        ctypes = (np.full(conn.shape[0], 12, dtype=np.int64)
                  if conn is not None else None)
    else:
        verts = _read_coordinates(zone)
        if verts is None:
            return None
        conn, ctypes, poly = _read_cells(zone)
    n_v = int(verts.shape[0])
    n_c = int(conn.shape[0]) if conn is not None else 0
    bcs = []
    vertex_bcs = []
    if ztype != "Structured":
        bcs, vertex_bcs = _read_bcs(zone, (poly or {}).get("face_base", 1))
    return {
        "zone": (getattr(zone, "name", "") or "").rsplit("/", 1)[-1],
        "verts": verts,
        "conn": conn,
        "ctypes": ctypes,
        "poly": poly,
        "fields": _read_flow_solution(zone, n_v, n_c, lazy=lazy_fields),
        "bcs": bcs,
        "vertex_bcs": vertex_bcs,
        "n_v": n_v,
        "n_c": n_c,
    }


def _decode_zone_hdf5(args: tuple) -> Optional[tuple]:
    """Module-level worker for :func:`read_cgns` (picklable for a Pool).

    Reopens the file in the worker and decodes a single zone; returns the
    same record dict as :func:`_decode_zone` (numpy arrays pickle cleanly).
    """
    path, base_name, zone_name = args[:3]
    lazy_fields = len(args) > 3 and bool(args[3])
    if not _HAS_H5:
        return None
    with h5py.File(path, "r") as f:
        base = f[base_name]
        zone = base[zone_name]
        return _decode_zone(zone, _zone_type(zone), lazy_fields)


#: Above this many cells the duplicate-zone scan is skipped: it has to sort
#: every zone's cell keys, and a mesh this large is far past the interactive
#: envelope.  The decision is reported in mesh["zone_selection"].
_ZONE_SCAN_CELL_CAP = 12_000_000

#: 24-byte row type used to compare rounded cell centres exactly and cheaply.
_ROW3 = np.dtype([("x", "<f8"), ("y", "<f8"), ("z", "<f8")])


def _element_zone_table(rec):
    """Face table of a fixed-size element zone inside a polyhedral file."""
    n_cells = int(rec["n_c"])
    inst = _element_face_instances(rec["conn"], rec["ctypes"])
    if inst is None:
        return None
    rows, counts, cells = inst
    inv, gen_nodes, gen_counts, n_faces = _dedupe_rows(rows, counts)
    face_offsets = np.zeros(n_faces + 1, dtype=np.int64)
    np.cumsum(gen_counts, out=face_offsets[1:])
    owner, neighbour = _owner_neighbour(inv, cells, None, n_faces)
    cell_faces_offsets = np.zeros(n_cells + 1, dtype=np.int64)
    np.cumsum(np.bincount(cells, minlength=n_cells),
              out=cell_faces_offsets[1:])
    return {
        "n_faces": n_faces,
        "npe": gen_counts,
        "face_nodes": gen_nodes,
        "face_offsets": face_offsets,
        "owner": owner,
        "neighbour": neighbour,
        "boundary_faces": np.flatnonzero((neighbour < 0) & (owner >= 0)),
        "cell_faces": inv,
        "cell_faces_offsets": cell_faces_offsets,
        "n_cells": n_cells,
    }


def _empty_face_table(n_cells: int) -> dict:
    """Face table of a zone that has no cells (nodes only)."""
    z = np.zeros(0, dtype=np.int64)
    return {
        "n_faces": 0,
        "npe": z,
        "face_nodes": z,
        "face_offsets": np.zeros(1, dtype=np.int64),
        "owner": z,
        "neighbour": z,
        "cell_faces": z,
        "cell_faces_offsets": np.zeros(n_cells + 1, dtype=np.int64),
        "n_cells": n_cells,
    }


def _cell_centres(rec):
    """(centres, valid) per cell of a zone record; the R124 zone key."""
    n_c = int(rec["n_c"])
    verts = np.asarray(rec["verts"], dtype=np.float64)
    out = np.zeros((max(n_c, 0), 3), dtype=np.float64)
    ok = np.zeros(max(n_c, 0), dtype=bool)
    if n_c == 0:
        return out, ok
    poly = rec["poly"]
    if poly is not None:
        fo = np.asarray(poly["face_offsets"], dtype=np.int64)
        fcnt = np.diff(fo)
        good = fcnt > 0
        fsum = np.zeros((fcnt.size, 3), dtype=np.float64)
        if bool(good.any()):
            nodes = np.asarray(poly["face_nodes"], dtype=np.int64)
            fsum[good] = np.add.reduceat(verts[nodes], fo[:-1][good], axis=0)
        fctr = np.zeros_like(fsum)
        fctr[good] = fsum[good] / fcnt[good, None]
        cf = np.asarray(poly["cell_faces"], dtype=np.int64)
        co = np.asarray(poly["cell_faces_offsets"], dtype=np.int64)
        ccnt = np.diff(co)
        keep = ccnt > 0
        if cf.size:
            cell_of = np.repeat(np.arange(n_c, dtype=np.int64), ccnt)
            for d in range(3):
                out[:, d] = np.bincount(cell_of, weights=fctr[cf, d],
                                        minlength=n_c)
            out[keep] /= ccnt[keep, None]
        return out, keep
    conn = np.asarray(rec["conn"], dtype=np.int64)
    good = conn >= 0
    cnt = good.sum(axis=1)
    keep = cnt > 0
    if bool(keep.any()):
        # -1 padding must not contribute: a ragged row (MIXED / a section of
        # narrower elements) would otherwise sum node 0 several extra times
        safe = np.where(good, conn, 0)
        coords = np.where(good[:, :, None], verts[safe], 0.0)
        out[keep] = coords.sum(axis=1)[keep] / cnt[keep, None]
    return out, keep


def _row_keys(centres, ok):
    """Sorted exact rows of the rounded centres (R124 comparison key)."""
    if centres.size == 0:
        return np.zeros(0, dtype=_ROW3)
    rows = np.ascontiguousarray(np.round(centres, 9))
    return np.sort(rows.view(_ROW3).ravel()[ok])


def _rows_contained(rows, ref) -> bool:
    """True when every row appears in the sorted reference row array."""
    if rows.size == 0:
        return True
    if ref.size == 0:
        return False
    idx = np.clip(np.searchsorted(ref, rows), 0, ref.size - 1)
    return bool(np.all(ref[idx] == rows))


def _row_diff(rows, ref) -> int:
    """How many rows are missing from the sorted reference row array."""
    if rows.size == 0:
        return 0
    if ref.size == 0:
        return int(rows.size)
    idx = np.clip(np.searchsorted(ref, rows), 0, ref.size - 1)
    return int((ref[idx] != rows).sum())


def select_zones(records, cell_cap: int = _ZONE_SCAN_CELL_CAP):
    """Drop zones whose cells are all already present in another zone (R124).

    A Cradle CGNS export writes one zone per named volume region and repeats
    the same cells under the region, part and FPHPARTS.* names.  Measured on
    tr03_9_orig.cgns: FluidRegion is the exact disjoint union of
    Rotate_MovingVolumeRegion and Case[2], and three further zones are
    bit-identical copies of the first -- merging all seven gives 127396 cells
    where the source FPH has 63697.  A zone is therefore dropped when every
    one of its cells is already covered by a zone kept before it, largest
    first.  Nothing is dropped silently: the outcome is reported in
    mesh["dropped_zones"] and mesh["zone_selection"].

    Returns (kept records in file order, dropped, note).
    """
    total = sum(int(r["n_c"] or 0) for r in records)
    if total > cell_cap:
        return (list(records), [],
                "duplicate-zone scan skipped: %d cells over the %d cell cap"
                % (total, cell_cap))
    order = sorted(range(len(records)),
                   key=lambda i: -int(records[i]["n_c"] or 0))
    kept_idx = []
    dropped = []
    refs: list = []    # (zone name, sorted cell rows) of the kept zones
    for idx in order:
        rec = records[idx]
        centres, ok = _cell_centres(rec)
        rows = _row_keys(centres, ok)
        covering = None
        for name, ref in refs:
            if _rows_contained(rows, ref):
                covering = name
                break
        if covering is not None:
            dropped.append((rec["zone"],
                            "cells duplicated by zone %r" % covering,
                            int(rec["n_c"])))
            continue
        kept_idx.append(idx)
        if rows.size:
            refs.append((rec["zone"], rows))
    kept_idx.sort()
    note = ("%d zone(s) dropped as duplicates of other zones" % len(dropped)
            if dropped else "")
    return [records[i] for i in kept_idx], dropped, note


def _link_data_from_arrays(n_faces, npe, face_nodes, face_offsets, owner,
                           neighbour, n_cells):
    """Assemble the link_data dict the renderer expects (R124)."""
    from .mesh_gph import _group_faces_by_cell_id
    all_faces = np.arange(int(n_faces), dtype=np.int64)
    own_ok = owner >= 0
    owner_faces = _group_faces_by_cell_id(owner[own_ok], all_faces[own_ok],
                                          n_cells)
    nb_ok = neighbour >= 0
    neigh_faces = _group_faces_by_cell_id(neighbour[nb_ok], all_faces[nb_ok],
                                          n_cells)
    return {
        "n_faces": int(n_faces),
        "npe": npe,
        "face_nodes": face_nodes,
        "face_offsets": face_offsets,
        "owner": owner,
        "neighbour": neighbour,
        "boundary_faces": np.flatnonzero((neighbour < 0) & own_ok),
        "cell_owner_faces": owner_faces,
        "cell_neighbour_faces": neigh_faces,
        "n_cells": int(n_cells),
    }


def _merge_zones(records, base_names, lazy_fields: bool = False,
                 dropped=None, zone_selection: str = ""):
    """Merge per-zone ``_decode_zone`` results into the mesh dict.

    The merge is identical for the serial and parallel paths: vertices are
    concatenated with per-zone index offsets, connectivity/types
    concatenated, and same-name node/cell fields padded with NaN.

    R124: records come from :func:_decode_zone and carry explicit field
    locations and, for polyhedral zones, a face table; the merged mesh then
    also exposes link_data, the per-cell zone id (material) and the dropped
    duplicate zones.
    """
    all_verts = []
    all_conn = []
    all_types = []
    zone_nv = []
    zone_nc = []
    surface_regions = []
    volume_regions = []
    vertex_bcs = []
    zone_of_cell = []
    vert_offset = 0
    cell_offset = 0
    face_offset = 0
    cell_flat = 0
    poly_mode = any(r["poly"] is not None for r in records)
    face_npe = []
    face_nodes_l = []
    face_off_l = []
    owner_l = []
    neighbour_l = []
    cell_faces_l = []
    cell_faces_off_l = []
    for rec in records:
        verts = rec["verts"]
        n_v = int(rec["n_v"])
        n_c = int(rec["n_c"])
        table = None
        if poly_mode:
            table = (rec["poly"] if rec["poly"] is not None
                     else _element_zone_table(rec))
            if table is None:
                table = _empty_face_table(n_c)
        n_f = int(table["n_faces"]) if table is not None else 0
        if not poly_mode and rec["conn"] is not None:
            conn = rec["conn"]
            all_conn.append(conn + vert_offset if vert_offset else conn)
            all_types.append(rec["ctypes"])
        all_verts.append(verts)
        zone_nv.append(n_v)
        zone_nc.append(n_c)
        volume_regions.append(rec["zone"])
        zone_of_cell.append(np.full(n_c, len(volume_regions), dtype=np.int64))
        for name, ids in rec["bcs"]:
            if ids.size == 0:
                continue
            if poly_mode:
                bad = (ids < 0) | (ids >= n_f)
                if bool(bad.any()):
                    _LOG.warning("ZoneBC %r: %d of %d face ids outside the "
                                 "zone face range", name, int(bad.sum()),
                                 ids.size)
                    ids = ids[~bad]
                if ids.size == 0:
                    continue
                ids = ids + face_offset
            surface_regions.append((name, ids))
        vertex_bcs.extend(rec["vertex_bcs"])
        if table is not None:
            base_flat = cell_flat
            if n_f:
                face_npe.append(table["npe"])
                face_nodes_l.append(
                    np.asarray(table["face_nodes"], np.int64) + vert_offset)
                face_off_l.append(
                    np.asarray(table["face_offsets"], np.int64) + face_offset)
                owner = np.asarray(table["owner"], np.int64)
                neighbour = np.asarray(table["neighbour"], np.int64)
                owner_l.append(np.where(owner >= 0, owner + cell_offset, -1))
                neighbour_l.append(np.where(neighbour >= 0,
                                            neighbour + cell_offset, -1))
                cf = np.asarray(table["cell_faces"], np.int64) + face_offset
                cell_faces_l.append(cf)
                cell_flat += int(cf.size)
            cell_faces_off_l.append(
                np.asarray(table["cell_faces_offsets"], np.int64) + base_flat)
        vert_offset += n_v
        cell_offset += n_c
        face_offset += n_f
    if not all_verts:
        return None
    vertices = np.vstack(all_verts)
    n_cells = int(cell_offset)
    material = (np.concatenate(zone_of_cell) if zone_of_cell
                else np.zeros(0, dtype=np.int64))
    skipped_fields = []
    for rec in records:
        for fname, why in rec["fields"].get("__skipped__", []):
            skipped_fields.append((fname, why))
    fields = {}
    field_lazy = {}
    names = []
    for rec in records:
        for n in rec["fields"]:
            if n.startswith("__") or n in names:
                continue
            names.append(n)
    for fname in names:
        if lazy_fields:
            # R28 lazy merge: NaN placeholders shaped exactly like the eager
            # result, plus per-field (ds_path, offset, size) parts on the
            # winning side for on-demand materialisation.
            node_arr = np.full(vertices.shape[0], np.nan)
            cell_arr = np.full(n_cells, np.nan)
            parts = []
            n_node = n_cell = 0
            v_off = c_off = 0
            for rec, n_v, n_c in zip(records, zone_nv, zone_nc):
                desc = rec["fields"].get(fname)
                v_off_end = v_off + n_v
                c_off_end = c_off + n_c
                if desc is not None:
                    ds_path, size, loc = desc
                    if loc == "node" and size == n_v:
                        n_node += size
                        parts.append((ds_path, v_off, size, "node"))
                    elif loc == "cell" and size == n_c:
                        n_cell += size
                        parts.append((ds_path, c_off, size, "cell"))
                    else:
                        skipped_fields.append(
                            (fname, "%s field of size %d does not match zone "
                             "%r (%d nodes / %d cells)"
                             % (loc, size, rec["zone"], n_v, n_c)))
                v_off, c_off = v_off_end, c_off_end
            if n_node >= n_cell:
                fields[fname] = (node_arr, "node")
                field_lazy[fname] = [q[:3] for q in parts if q[3] == "node"]
            else:
                fields[fname] = (cell_arr, "cell")
                field_lazy[fname] = [q[:3] for q in parts if q[3] == "cell"]
            if n_node and n_cell:
                skipped_fields.append(
                    (fname, "field is node-centred in some zones and "
                     "cell-centred in others; only the %s side is kept"
                     % ("node" if n_node >= n_cell else "cell")))
            continue
        node_parts = []
        cell_parts = []
        n_node = n_cell = 0
        for rec, n_v, n_c in zip(records, zone_nv, zone_nc):
            entry = rec["fields"].get(fname)
            if entry is None:
                node_parts.append(np.full(n_v, np.nan))
                cell_parts.append(np.full(n_c, np.nan))
                continue
            arr, loc = entry
            arr = np.asarray(arr, dtype=np.float64)
            if loc == "node" and arr.size == n_v:
                node_parts.append(arr)
                cell_parts.append(np.full(n_c, np.nan))
                n_node += arr.size
            elif loc == "cell" and arr.size == n_c:
                node_parts.append(np.full(n_v, np.nan))
                cell_parts.append(arr)
                n_cell += arr.size
            else:
                skipped_fields.append(
                    (fname, "%s field of size %d does not match zone %r "
                     "(%d nodes / %d cells)"
                     % (loc, arr.size, rec["zone"], n_v, n_c)))
                node_parts.append(np.full(n_v, np.nan))
                cell_parts.append(np.full(n_c, np.nan))
        node_arr = np.concatenate(node_parts)
        cell_arr = np.concatenate(cell_parts)
        if not (np.isfinite(node_arr).any() or np.isfinite(cell_arr).any()):
            # every contribution was a size mismatch or a NaN pad: the file
            # holds no usable values for this field, so do not offer a
            # variable that can only ever be empty.
            skipped_fields.append((fname, "no values for any kept zone"))
            continue
        if n_node >= n_cell:
            fields[fname] = (node_arr, "node")
        else:
            fields[fname] = (cell_arr, "cell")
        if n_node and n_cell:
            skipped_fields.append(
                (fname, "field is node-centred in some zones and cell-centred "
                 "in others; only the %s side is kept"
                 % ("node" if n_node >= n_cell else "cell")))
    mesh = {
        "vertices": vertices,
        "n_vertices": int(vertices.shape[0]),
        "n_cells": n_cells,
        "fields": fields,
        "field_lazy": field_lazy,
        "surface_regions": surface_regions,
        "volume_regions": volume_regions,
        "material": material,
        "zone_name": volume_regions[0] if volume_regions else "",
        "base_name": base_names[0] if base_names else "",
        "base_names": list(base_names),
        "dropped_zones": list(dropped or []),
        "zone_selection": zone_selection,
    }
    if vertex_bcs:
        mesh["vertex_bcs"] = vertex_bcs
    if skipped_fields:
        mesh["skipped_fields"] = skipped_fields
    if not poly_mode:
        mesh["link_data"] = None
        mesh["cell_conn"] = _pad_stack(all_conn) if all_conn else None
        mesh["cell_types"] = np.concatenate(all_types) if all_types else None
        return mesh
    n_faces = int(face_offset)
    face_offsets = np.zeros(n_faces + 1, dtype=np.int64)
    pos = 0
    for off in face_off_l:
        n_f = int(off.size) - 1
        face_offsets[pos:pos + n_f + 1] = off
        pos += n_f
    cell_faces_offsets = np.zeros(n_cells + 1, dtype=np.int64)
    pos = 0
    for off in cell_faces_off_l:
        n_c = int(off.size) - 1
        cell_faces_offsets[pos:pos + n_c + 1] = off
        pos += n_c
    npe = np.concatenate(face_npe) if face_npe else np.zeros(0, dtype=np.int64)
    face_nodes = (np.concatenate(face_nodes_l) if face_nodes_l
                  else np.zeros(0, dtype=np.int64))
    cell_faces = (np.concatenate(cell_faces_l) if cell_faces_l
                  else np.zeros(0, dtype=np.int64))
    owner = np.concatenate(owner_l) if owner_l else np.zeros(0, dtype=np.int64)
    neighbour = (np.concatenate(neighbour_l) if neighbour_l
                 else np.zeros(0, dtype=np.int64))
    mesh["link_data"] = _link_data_from_arrays(
        n_faces, npe, face_nodes, face_offsets, owner, neighbour, n_cells)
    mesh["n_faces"] = n_faces
    mesh["cell_conn"] = _pad_ragged(cell_faces, cell_faces_offsets)
    mesh["cell_types"] = np.full(n_cells, 42, dtype=np.int64)
    return mesh


def _zone_refs(f):
    """(base names, [(base, zone) ...]) for every base holding zones (R124).

    Every base is read, in the order h5py lists them (HDF5 name order), instead
    of only the first one that happened to contain zones: a file whose volume
    and boundary meshes live in separate bases silently lost the second
    one.  A zone is any subgroup that
    carries a ZoneType or GridCoordinates node, so the CGNS format markers and
    Cradle's ReferenceState container are not mistaken for zones.
    """
    bases: list = []
    refs: list = []
    for k in f.keys():
        g = f[k]
        if not isinstance(g, h5py.Group):
            continue
        zones = [z for z in g.keys()
                 if isinstance(g[z], h5py.Group)
                 and ("ZoneType" in g[z] or "GridCoordinates" in g[z])]
        if zones:
            bases.append(k)
            refs.extend((k, z) for z in zones)
    return bases, refs


def read_cgns(path: str, workers: int = 0, use_threads: bool = False,
              lazy_fields: bool = False) -> Optional[dict]:
    """Read a CGNS-HDF5 file into the mesh-dict shape (P1.2, P2.1).

    Multiple zones (Unstructured or Structured) are merged into a single
    mesh: vertices are concatenated with per-zone index offsets, cell
    connectivity/types concatenated, and same-name node/cell fields
    concatenated in zone order -- the order h5py lists the zone groups, i.e.
    HDF5 name order, not the order they were written in (missing
    contributions padded with NaN).
    Returns None when the file is not a readable CGNS-HDF5.

    R124: zones from every base are merged; polyhedral zones (NGON_n /
    NFACE_n) are decoded into a link_data face table so the renderer can cut
    them, and zones whose cells are entirely duplicated by another zone are
    dropped (reported in mesh["dropped_zones"]).

    ``workers`` (R26-S2) > 1 decodes zones concurrently and 0/1 keeps the
    serial path. By default a process pool is used (``use_threads=False``);
    when process-pool pickling/spawn overhead dominates on a tiny sample
    (regression-guard) pass ``use_threads=True`` to fall back to a thread
    pool — harness decode is numpy-vectorised and releases the GIL, so
    threads can still overlap. The merge order and output are identical
    regardless of concurrency model or worker count.
    """
    if not _HAS_H5:
        return None
    with h5py.File(path, "r") as f:
        bases, refs = _zone_refs(f)
        if not refs:
            return None
    if workers and workers > 1 and len(refs) > 1:
        jobs = [(path, b, z, lazy_fields) for b, z in refs]
        if use_threads:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                zone_results = list(ex.map(_decode_zone_hdf5, jobs))
        else:
            import multiprocessing as mp
            with mp.Pool(processes=workers) as pool:
                zone_results = pool.map(_decode_zone_hdf5, jobs)
    else:
        with h5py.File(path, "r") as f:
            zone_results = [
                _decode_zone(f[b][z], _zone_type(f[b][z]), lazy_fields)
                for b, z in refs]
    records = [r for r in zone_results if r is not None]
    if not records:
        return None
    kept, dropped, note = select_zones(records)
    for name, why, n_c in dropped:
        _LOG.info("CGNS zone %r dropped: %s (%d cells)", name, why, n_c)
    return _merge_zones(kept, bases, lazy_fields, dropped=dropped,
                        zone_selection=note)


def materialize_lazy_field(path: str, parts: list, total: int) -> np.ndarray:
    """R28: materialise one lazily-merged CGNS field (on demand).

    ``parts`` is the ``(ds_path, offset, size)`` list recorded by a lazy
    :func:`_merge_zones`; the result matches the eager merge exactly,
    including NaN padding for zones that lack the field.
    """
    out = np.full(total, np.nan)
    if not parts:
        return out
    if not _HAS_H5:
        raise OSError(f"h5py unavailable, cannot read: {path}")
    with h5py.File(path, "r") as f:
        for ds_path, off, size in parts:
            arr = np.asarray(f[ds_path][()], dtype=np.float64).ravel()
            out[off:off + size] = arr[:size]
    return out


def materialize_lazy_window(path: str, parts: list, total: int,
                            lo: int, hi: int) -> np.ndarray:
    """R31-S1: materialise only ``out[lo:hi]`` of a lazy CGNS field.

    Unlike :func:`materialize_lazy_field` this does **not** allocate the
    full-length placeholder — it bounds allocation to the requested
    window (the core of beyond-memory streaming). ``parts`` is the
    ``(ds_path, offset, size)`` list from a lazy :func:`_merge_zones`;
    ``lo``/``hi`` are half-open indices into the merged (length ``total``)
    field. Only the sub-rows overlapping ``(lo, hi)`` are read.
    Returns a length ``hi - lo`` array (NaN outside any zone coverage).
    """
    lo = max(0, int(lo))
    hi = min(total, int(hi))
    width = hi - lo
    out = np.full(width, np.nan)
    if width <= 0 or not parts or not _HAS_H5:
        return out
    with h5py.File(path, "r") as f:
        for ds_path, off, size in parts:
            seg_lo = max(lo, off)
            seg_hi = min(hi, off + size)
            if seg_hi <= seg_lo:
                continue
            arr = np.asarray(f[ds_path][()], dtype=np.float64).ravel()
            out[seg_lo - lo:seg_hi - lo] = arr[seg_lo - off:seg_hi - off]
    return out


def iter_field_tiles(path: str, parts: list, total: int, tile: int,
                     lo: int = 0, hi: Optional[int] = None):
    """R31-S1: yield non-overlapping window (lo, arr) covering [lo, hi).

    ``tile`` is the tile size; each yielded ``arr`` is at most the tile
    length and is produced without allocating the whole field, so peak
    memory stays bounded. The union of yielded windows tiles exactly the
    requested ``[lo, hi)`` range (NaN-filled for gaps/zone padding).
    """
    hi = total if hi is None else min(total, int(hi))
    lo = max(0, int(lo))
    if hi <= lo or tile <= 0:
        return
    for start in range(lo, hi, int(tile)):
        end = min(hi, start + int(tile))
        yield start, materialize_lazy_window(path, parts, total, start, end)


def is_cgns_hdf5(path: str) -> bool:
    """Best-effort HDF5 + CGNS format-marker check."""
    if not _HAS_H5:
        return False
    try:
        with h5py.File(path, "r") as f:
            # CGNS-HDF5: CGNSLibraryVersion marker or a base group holding
            # zones (format dataset varies between writers)
            if "CGNSLibraryVersion" in f:
                return True
            # a base group holds zones; the CGNSLibraryVersion check above
            # covers files whose base has not been written yet
            return any(isinstance(f[k], h5py.Group) and "ZoneType" in f[k]
                       for k in f.keys())
    except Exception:
        return False
