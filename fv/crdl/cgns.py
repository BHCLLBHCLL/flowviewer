"""CGNS-HDF5 reader (P1.2, P2.1).

Reads the standard CGNS SIDS tree stored in HDF5 (h5py) into the
same dict shape the mesh parsers produce: vertices, cell connectivity,
node/cell fields, volume region names and boundary condition faces.

P2.1: MIXED element streams are decoded per element; multiple zones
(including Structured zones, converted to HEXA_8 grids) are merged
into one mesh with vertex indices offset per zone.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np

try:
    import h5py
    _HAS_H5 = True
except Exception:  # pragma: no cover - optional dep
    _HAS_H5 = False


# CGNS ElementType numeric codes (SIDS) -> type names
_CODE_TO_NAME = {
    3: "BAR_2", 5: "TRI_3", 7: "QUAD_4", 10: "TETRA_4",
    12: "PYRA_5", 14: "PENTA_6", 17: "HEXA_8", 20: "MIXED",
}

# SIDS element code -> (vtk cell type, n_nodes) for MIXED streams (P2.1)
_CODE_CELLS = {
    5: (5, 3),     # TRI_3
    7: (9, 4),     # QUAD_4
    10: (10, 4),   # TETRA_4
    12: (14, 5),   # PYRA_5
    13: (13, 6),   # PENTA_6
    14: (14, 5),   # PYRA_5 alt code (some writers)
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


def _read_cells(zone):
    """Read volume cells -> (cell_conn, cell_types) or (None, None)."""
    cell_conn = []
    cell_types = []
    for name, sec in _elements_sections(zone):
        et = _elem_type_name(sec)
        conn = _data_of(sec["ElementConnectivity"])
        if conn is None:
            continue
        if conn.size == 0:
            continue
        rng = _data_of(sec["ElementRange"])
        if rng is None:
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
    if not cell_conn:
        return None, None
    width = max(a.shape[1] for a in cell_conn)
    merged = np.full((sum(a.shape[0] for a in cell_conn), width),
                     -1, dtype=np.int64)
    r = 0
    for a in cell_conn:
        merged[r:r + a.shape[0], :a.shape[1]] = a
        r += a.shape[0]
    return merged, np.asarray(cell_types, dtype=np.int64)


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


def _read_flow_solution(zone, n_nodes: int, lazy: bool = False):
    """FlowSolution fields -> dict name -> (array, location).

    ``lazy=True`` (R28) skips payload reads: each field maps to a
    ``(ds_path, size)`` descriptor — the HDF5 dataset's absolute path and
    element count taken from shape metadata only, so a lazy open never
    touches field payloads.
    """
    out = {}
    fs = zone.get("FlowSolution")
    if fs is None:
        return out
    for name, obj in _children(fs):
        if not isinstance(obj, h5py.Group):
            continue
        ds = None
        if "data" in obj:
            ds = obj["data"]
        elif " data" in obj:
            ds = obj[" data"]
        if not isinstance(ds, h5py.Dataset):
            continue
        if lazy:
            shape = ds.shape
            if len(shape) != 1 or shape[0] == 0:
                continue
            out[name] = (ds.name, int(shape[0]))
            continue
        try:
            arr = np.asarray(ds[()], dtype=np.float64)
        except Exception:
            continue
        if arr.ndim != 1 or arr.size == 0:
            continue
        loc = "node" if arr.size == n_nodes else "cell"
        out[name] = (arr, loc)
    return out


def _read_bcs(zone, n_faces: int):
    """ZoneBC boundary conditions -> [(name, face_ids 0-based)]."""
    out = []
    zbc = zone.get("ZoneBC")
    if zbc is None:
        return out
    for name, obj in _children(zbc):
        if not isinstance(obj, h5py.Group):
            continue
        pl = obj.get("PointList")
        raw = _data_of(pl) if pl is not None else None
        if raw is None:
            continue
        try:
            ids = np.asarray(raw, dtype=np.int64).ravel() - 1
        except Exception:
            continue
        out.append((name, ids))
    return out


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
    """
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
        conn, ctypes = _read_cells(zone)
    n_v = verts.shape[0]
    n_c = conn.shape[0] if conn is not None else 0
    bcs = []
    if ztype != "Structured":
        for n, ids in _read_bcs(zone, 0):
            bcs.append((n, ids))
    return (verts, conn, ctypes,
            _read_flow_solution(zone, n_v, lazy=lazy_fields), bcs, n_v, n_c)


def _decode_zone_hdf5(args: tuple) -> Optional[tuple]:
    """Module-level worker for :func:`read_cgns` (picklable for a Pool).

    Reopens the file in the worker and decodes a single zone; returns the
    same 7-tuple as :func:`_decode_zone` (numpy arrays pickle cleanly).
    """
    path, base_name, zone_name = args[:3]
    lazy_fields = len(args) > 3 and bool(args[3])
    if not _HAS_H5:
        return None
    with h5py.File(path, "r") as f:
        base = f[base_name]
        zone = base[zone_name]
        return _decode_zone(zone, _zone_type(zone), lazy_fields)


def _merge_zones(zone_results, zone_names, base_name,
                 lazy_fields: bool = False):
    """Merge per-zone ``_decode_zone`` results into the mesh dict.

    The merge is identical for the serial and parallel paths: vertices are
    concatenated with per-zone index offsets, connectivity/types
    concatenated, and same-name node/cell fields padded with NaN.
    """
    all_verts = []
    all_conn = []
    all_types = []
    zone_fields = []
    zone_nv = []
    zone_nc = []
    surface_regions = []
    vert_offset = 0
    merged_any = False
    for res in zone_results:
        if res is None:
            continue
        verts, conn, ctypes, fields, bcs, n_v, n_c = res
        merged_any = True
        if conn is not None:
            if vert_offset:
                conn = conn + vert_offset
            all_conn.append(conn)
            all_types.append(ctypes)
        all_verts.append(verts)
        zone_fields.append(fields)
        zone_nv.append(n_v)
        zone_nc.append(n_c)
        for n, ids in bcs:
            surface_regions.append((n, ids))
        vert_offset += n_v
    if not merged_any:
        return None
    vertices = np.vstack(all_verts)
    cell_conn = _pad_stack(all_conn) if all_conn else None
    cell_types = np.concatenate(all_types) if all_types else None
    names = []
    for zf in zone_fields:
        for n in zf:
            if n not in names:
                names.append(n)
    fields = {}
    field_lazy = {}
    n_cells = int(cell_conn.shape[0]) if cell_conn is not None else 0
    for fname in names:
        if lazy_fields:
            # R28 lazy merge: NaN placeholders shaped exactly like the
            # eager result, plus per-field (ds_path, offset, size) parts
            # on the winning side for on-demand materialisation.
            node_arr = np.full(vertices.shape[0], np.nan)
            cell_arr = np.full(n_cells, np.nan)
            parts = []
            n_node_finite = n_cell_finite = 0
            v_off = c_off = 0
            for zf, n_v, n_c in zip(zone_fields, zone_nv, zone_nc):
                desc = zf.get(fname)
                if desc is not None:
                    ds_path, size = desc
                    if size == n_v and n_v != n_c:
                        n_node_finite += size
                        parts.append((ds_path, v_off, size, "node"))
                    elif size == n_c:
                        n_cell_finite += size
                        parts.append((ds_path, c_off, size, "cell"))
                v_off += n_v
                c_off += n_c
            if n_node_finite >= n_cell_finite:
                fields[fname] = (node_arr, "node")
                field_lazy[fname] = [q[:3] for q in parts if q[3] == "node"]
            else:
                fields[fname] = (cell_arr, "cell")
                field_lazy[fname] = [q[:3] for q in parts if q[3] == "cell"]
            continue
        node_parts = []
        cell_parts = []
        for zf, n_v, n_c in zip(zone_fields, zone_nv, zone_nc):
            arr = zf.get(fname)
            if arr is not None and arr[0].size == n_v and n_v != n_c:
                node_parts.append(arr[0])
                cell_parts.append(np.full(n_c, np.nan))
            elif arr is not None and arr[0].size == n_c:
                node_parts.append(np.full(n_v, np.nan))
                cell_parts.append(arr[0])
            else:
                node_parts.append(np.full(n_v, np.nan))
                cell_parts.append(np.full(n_c, np.nan))
        node_arr = np.concatenate(node_parts)
        cell_arr = np.concatenate(cell_parts)
        if np.isfinite(node_arr).sum() >= np.isfinite(cell_arr).sum():
            fields[fname] = (node_arr, "node")
        else:
            fields[fname] = (cell_arr, "cell")
    return {
        "vertices": vertices,
        "cell_conn": cell_conn,
        "cell_types": cell_types,
        "n_vertices": int(vertices.shape[0]),
        "n_cells": n_cells,
        "fields": fields,
        "field_lazy": field_lazy,
        "surface_regions": surface_regions,
        "volume_regions": list(zone_names),
        "zone_name": zone_names[0],
        "base_name": base_name,
    }


def read_cgns(path: str, workers: int = 0, use_threads: bool = False,
              lazy_fields: bool = False) -> Optional[dict]:
    """Read a CGNS-HDF5 file into the mesh-dict shape (P1.2, P2.1).

    Multiple zones (Unstructured or Structured) are merged into a single
    mesh: vertices are concatenated with per-zone index offsets, cell
    connectivity/types concatenated, and same-name node/cell fields
    concatenated in zone order (missing contributions padded with NaN).
    Returns None when the file is not a readable CGNS-HDF5.

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
        # find the first CGNSBase_t group (top-level, excluding format)
        bases = [k for k in f.keys() if isinstance(f[k], h5py.Group)
                 and k.strip() not in ("format", "hdf5version")]
        if not bases:
            return None
        base = f[bases[0]]
        zone_names = [k for k in base.keys()
                      if isinstance(base[k], h5py.Group)
                      and "ZoneType" in base[k]]
        if not zone_names:
            return None
    base_name = bases[0]
    if workers and workers > 1 and len(zone_names) > 1:
        jobs = [(path, base_name, z, lazy_fields) for z in zone_names]
        if use_threads:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                zone_results = list(ex.map(_decode_zone_hdf5, jobs))
        else:
            import multiprocessing as mp
            with mp.Pool(processes=workers) as pool:
                zone_results = pool.map(_decode_zone_hdf5, jobs)
    else:
        with h5py.File(path, "r") as f:
            base = f[base_name]
            zone_results = [_decode_zone(base[z], _zone_type(base[z]),
                                         lazy_fields)
                            for z in zone_names]
    return _merge_zones(zone_results, zone_names, base_name, lazy_fields)


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
            return any(isinstance(f[k], h5py.Group)
                       and any("ZoneType" in (g or {}) for g in [])
                       for k in f.keys()) or any(
                isinstance(f[k], h5py.Group) and "ZoneType" in f[k]
                for k in f.keys())
    except Exception:
        return False
