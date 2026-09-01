"""Pure-Python ADF (CGNS legacy) reader + writer.

Disk layout transcribed from cgnslib 4.5.1 src/adf/ADF_internals.c spec
comment block.  Header numbers are ASCII-hex text; a DISK_POINTER is
8 hex chars (block) + 4 hex chars (offset), 4096-byte blocks.  Data
payloads are raw binary with endianness from the file-header numeric
format char (B = IEEE big, L = IEEE little, N = writer native).
Chunked data (number_of_data_chunks > 1) goes through a DCtb table.

read_cgns_adf maps a CGNS ADF tree onto the same mesh-dict shape as
cgns.read_cgns (HDF5 path) so both backends feed the same loader.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np

BLOCK_SIZE = 4096

_TYPE_INFO = {
    "C1": (1, "bytes"), "B1": (1, "u1"), "I1": (1, "i1"),
    "I2": (2, "i2"), "I4": (4, "i4"), "I8": (8, "i8"),
    "U4": (4, "u4"), "U8": (8, "u8"),
    "R4": (4, "f4"), "R8": (8, "f8"),
    "X4": (8, "c8"), "X8": (16, "c16"),
}


class AdfNode:
    """One ADF tree node: name, label, data-type, dims, data, children."""

    __slots__ = ("name", "label", "data_type", "dims", "data", "children",
             "_off", "_sub_off", "_data_off")

    def __init__(self, name, label, data_type="MT", dims=(), data=None):
        self.name = name
        self.label = label
        self.data_type = data_type
        self.dims = tuple(int(d) for d in dims)
        self.data = data
        self.children: dict = {}

    def get(self, name):
        return self.children.get(name)

    def text(self, name):
        n = self.get(name)
        if n is None or n.data is None:
            return ""
        if isinstance(n.data, bytes):
            return n.data.decode("utf-8", "replace").strip().strip("\x00")
        return str(n.data)


def _ptr_abs(data, off):
    """Absolute byte offset of the 12-char DISK_POINTER at off."""
    try:
        blk = int(data[off:off + 8], 16)
        ofs = int(data[off + 8:off + 12], 16)
    except ValueError as exc:
        raise ValueError("bad DISK_POINTER at %d" % off) from exc
    return blk * BLOCK_SIZE + ofs


def _ptr_bytes(off):
    """12-char ASCII-hex DISK_POINTER for absolute offset off."""
    blk, ofs = divmod(off, BLOCK_SIZE)
    return ("%08X%04X" % (blk, ofs)).encode("ascii")


def _decode_array(data_type, dims, payload, fmt):
    info = _TYPE_INFO.get(data_type)
    if info is None:
        if data_type in ("MT", ""):
            return None
        raise ValueError("unsupported ADF data type %r" % data_type)
    es, kind = info
    n = 1
    for d in dims:
        n *= int(d)
    if n == 0:
        return np.zeros(dims or (0,), dtype="f8")
    need = n * es
    if len(payload) < need:
        raise ValueError("ADF data payload shorter than dims")
    payload = payload[:need]
    if kind == "bytes":
        return bytes(payload)
    prefix = {"B": ">", "L": "<"}.get(fmt, "=")
    arr = np.frombuffer(payload, dtype=prefix + kind, count=n)
    arr = np.array(arr, copy=True)
    return arr.reshape(dims) if len(dims) > 1 else arr


def _encode_array(node, fmt):
    """Serialize node.data per its data_type into fmt endianness."""
    if node.data is None:
        return b""
    info = _TYPE_INFO.get(node.data_type)
    if info is None:
        raise ValueError("unsupported ADF data type %r" % node.data_type)
    _, kind = info
    if kind == "bytes":
        return bytes(node.data)
    prefix = {"B": ">", "L": "<"}.get(fmt, "=")
    arr = np.asarray(node.data).astype(prefix + kind)
    return arr.tobytes()


def _data_payload(data, ptr, total):
    """Payload of a single data chunk (tolerates DaTa wrapper or raw)."""
    if ptr + 4 <= len(data) and data[ptr:ptr + 4] == b"DaTa":
        return data[ptr + 16:ptr + 16 + total]
    return data[ptr:ptr + total]


def _read_data(data, data_type, dims, nchunks, ptr, fmt):
    """Read node data payload (chunk table aware)."""
    if nchunks == 0 or not dims or data_type in ("MT", ""):
        return None
    es = _TYPE_INFO.get(data_type, (0,))[0]
    if es == 0:
        return None
    total = int(np.prod(dims)) * es
    if total == 0:
        return None
    if nchunks == 1:
        payload = _data_payload(data, ptr, total)
    else:
        if data[ptr:ptr + 4] != b"DCtb":
            raise ValueError("ADF chunk table tag missing")
        parts = []
        for i in range(nchunks):
            start = _ptr_abs(data, ptr + 16 + 24 * i)
            end = _ptr_abs(data, ptr + 28 + 24 * i)
            size = end - start + 1
            parts.append(_data_payload(data, start, size))
        payload = b"".join(parts)[:total]
    return _decode_array(data_type, dims, payload, fmt)


def read_adf(path):
    """Parse an ADF file into an AdfNode tree (root = first node).

    The file is memory-mapped so large databases are not copied into a
    Python ``bytes`` object before the node walk.  Array payloads are
    copied out of the map so the result survives after the file closes.
    """
    import mmap
    with open(path, "rb") as f:
        data = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            return _parse_adf(data, path)
        finally:
            data.close()


def _parse_adf(data, path):
    if len(data) < 186 or data[32:36] != b"AdF0":
        raise ValueError(path + ": not an ADF database")
    fmt = chr(data[100] if isinstance(data[100], int) else ord(data[100]))
    if fmt not in ("B", "L", "N"):
        raise ValueError(path + ": unsupported numeric format " + repr(fmt))
    root_abs = _ptr_abs(data, 134)

    def _node(abs_off):
        h = data[abs_off:abs_off + 246]
        if len(h) < 246 or h[:4] != b"NoDe":
            raise ValueError("ADF node tag missing at %d" % abs_off)
        name = h[4:36].split(b"\x00")[0].decode("ascii", "replace").strip()
        label = h[36:68].split(b"\x00")[0].decode("ascii", "replace").strip()
        num_sub = int(h[68:76], 16)
        sub_ptr = _ptr_abs(h, 84)
        data_type = h[96:128].split(b"\x00")[0].decode("ascii", "replace").strip()
        ndim = int(h[128:130], 16)
        dims = tuple(int(h[130 + 8 * i:138 + 8 * i], 16) for i in range(ndim))
        nchunks = int(h[226:230], 16)
        dptr = _ptr_abs(h, 230)
        node = AdfNode(name, label, data_type, dims,
                       _read_data(data, data_type, dims, nchunks, dptr, fmt))
        for i in range(num_sub):
            e = sub_ptr + 16 + 44 * i
            cname = (data[e:e + 32].split(b"\x00")[0]
                     .decode("ascii", "replace").strip())
            cptr = _ptr_abs(data, e + 32)
            node.children[cname] = _node(cptr)
        return node

    return _node(root_abs)


def _node_size(node):
    """Serialized byte size of a node + sub-table + data chunk."""
    sub = 20 + 44 * len(node.children) if node.children else 0
    payload = _encode_array(node, "B")
    chunk = 32 if node.data is not None else 0
    kids = sum(_node_size(ch) for ch in node.children.values())
    return 246 + sub + chunk + len(payload) + kids


def _place(node, off):
    """Assign absolute offsets (pre-order); return next free byte."""
    node._off = off
    nxt = off + 246
    if node.children:
        node._sub_off = nxt
        nxt += 20 + 44 * len(node.children)
    if node.data is not None:
        node._data_off = nxt
        nxt += 32 + len(_encode_array(node, "B"))
    for ch in node.children.values():
        nxt = _place(ch, nxt)
    return nxt


def _emit(data, node, fmt):
    """Write a node header + sub-table + data chunk at its offsets."""
    o = node._off
    h = bytearray(246)
    h[0:4] = b"NoDe"
    h[4:36] = node.name[:32].encode("ascii", "replace").ljust(32)
    h[36:68] = node.label[:32].encode("ascii", "replace").ljust(32)
    h[68:76] = ("%08X" % len(node.children)).encode()
    h[76:84] = ("%08X" % len(node.children)).encode()
    h[84:96] = _ptr_bytes(node._sub_off) if node.children else b"0" * 12
    h[96:128] = node.data_type[:32].encode("ascii", "replace").ljust(32)
    h[128:130] = ("%02X" % len(node.dims)).encode()
    for i, d in enumerate(node.dims):
        h[130 + 8 * i:138 + 8 * i] = ("%08X" % int(d)).encode()
    if node.data is not None:
        h[226:230] = ("%04X" % 1).encode()
        h[230:242] = _ptr_bytes(node._data_off)
    else:
        h[226:230] = ("%04X" % 0).encode()
        h[230:242] = b"0" * 12
    h[242:246] = b"TaiL"
    data[o:o + 246] = h
    if node.children:
        so = node._sub_off
        data[so:so + 4] = b"SNTb"
        data[so + 4:so + 16] = _ptr_bytes(so + 16 + 44 * len(node.children))
        for i, (cname, ch) in enumerate(node.children.items()):
            e = so + 16 + 44 * i
            data[e:e + 32] = cname[:32].encode("ascii", "replace").ljust(32)
            data[e + 32:e + 44] = _ptr_bytes(ch._off)
        end_tag = so + 16 + 44 * len(node.children)
        data[end_tag:end_tag + 4] = b"snTE"
    if node.data is not None:
        payload = _encode_array(node, fmt)
        d0 = node._data_off
        data[d0:d0 + 4] = b"DaTa"
        data[d0 + 4:d0 + 16] = _ptr_bytes(d0 + 16 + len(payload))
        data[d0 + 16:d0 + 16 + len(payload)] = payload
        tail = d0 + 16 + len(payload)
        data[tail:tail + 4] = b"dEnD"
    for ch in node.children.values():
        _emit(data, ch, fmt)


def write_adf(path, root, big_endian=True):
    """Serialize an AdfNode tree into a new ADF file (R3.5 fixtures)."""
    fmt = "B" if big_endian else "L"
    total = 186 + 80 + _node_size(root)
    data = bytearray(total)
    data[0:32] = b"@(#)ADF Database Version AXXxxx".ljust(32)
    data[32:36] = b"AdF0"
    data[36:64] = b"flowviewer created".ljust(28)
    data[64:68] = b"AdF1"
    data[68:96] = b"flowviewer created".ljust(28)
    data[96:100] = b"AdF2"
    data[100] = ord(fmt)
    data[101] = ord(fmt)
    data[102:106] = b"AdF3"
    sizes = [1, 2, 4, 4, 4, 8, 8, 8, 8, 8, 8, 8]
    for i, s in enumerate(sizes):
        data[106 + 2 * i:108 + 2 * i] = ("%02X" % s).encode()
    data[130:134] = b"AdF4"
    root_off = 186 + 80
    data[134:146] = _ptr_bytes(root_off)
    nxt = _place(root, root_off)
    data[146:158] = _ptr_bytes(nxt - 1)
    data[158:170] = _ptr_bytes(root_off - 80)
    data[170:182] = b"0" * 12
    data[182:186] = b"AdF5"
    ft = root_off - 80
    data[ft:ft + 4] = b"fCbt"
    data[ft + 4:ft + 76] = b"0" * 72
    data[ft + 76:ft + 80] = b"fcte"
    _emit(data, root, fmt)
    with open(path, "wb") as f:
        f.write(bytes(data))


def is_cgns_adf(path):
    """True when path looks like an ADF database."""
    try:
        with open(path, "rb") as f:
            head = f.read(186)
    except OSError:
        return False
    return len(head) >= 186 and head[32:36] == b"AdF0"


# ---- CGNS ADF to mesh-dict ----


def _num(node):
    d = node.data if node is not None else None
    if isinstance(d, np.ndarray):
        return np.asarray(d, dtype=np.float64).ravel()
    return None


def _iarr(node):
    d = node.data if node is not None else None
    if isinstance(d, np.ndarray):
        return np.asarray(d, dtype=np.int64).ravel()
    return None


def _cgns_zones(base):
    return [n for n in base.children.values() if n.label == "Zone_t"]


def _zone_type(zone):
    zt = zone.get("ZoneType")
    if zt is not None and isinstance(zt.data, bytes):
        return zt.data.decode("utf-8", "replace").strip("\x00").strip()
    return "Unstructured"


def _coordinates(zone):
    gc = zone.get("GridCoordinates")
    if gc is None:
        return None
    comps = []
    for axis in ("CoordinateX", "CoordinateY", "CoordinateZ"):
        arr = _num(gc.get(axis))
        if arr is None:
            return None
        comps.append(arr)
    if not comps or any(a.size == 0 for a in comps):
        return None
    return np.column_stack(comps)


def _elements_sections(zone):
    out = []
    for name, n in zone.children.items():
        if n.label == "Elements_t" and "ElementConnectivity" in n.children:
            out.append((name, n))
    return out


def _elem_type(sec):
    et = sec.get("ElementType")
    if et is not None and isinstance(et.data, bytes):
        return et.data.decode("utf-8", "replace").strip("\x00").strip()
    return ""


def _read_cells_adf(zone):
    from .cgns import _VOLUME_TYPES, _VTK_FOR_CGNS, _read_mixed_stream
    conns = []
    types = []
    for _name, sec in _elements_sections(zone):
        et = _elem_type(sec)
        raw = _iarr(sec.get("ElementConnectivity"))
        if raw is None or raw.size == 0:
            continue
        if et in _VOLUME_TYPES:
            vtk_t, nn = _VTK_FOR_CGNS[et]
            n = raw.size // nn
            conns.append(raw[:n * nn].reshape(n, nn) - 1)
            types.extend([vtk_t] * n)
        elif et == "MIXED":
            rows, t = _read_mixed_stream(raw)
            if rows is not None:
                conns.append(rows)
                types.extend(int(x) for x in t)
    if not conns:
        return None, None
    width = max(a.shape[1] for a in conns)
    merged = np.full((sum(a.shape[0] for a in conns), width), -1,
                     dtype=np.int64)
    r = 0
    for a in conns:
        merged[r:r + a.shape[0], :a.shape[1]] = a
        r += a.shape[0]
    return merged, np.asarray(types, dtype=np.int64)


def _structured_adf(zone):
    """Structured zone -> (vertices, hexa_conn); dims from coords."""
    gc = zone.get("GridCoordinates")
    if gc is None:
        return None
    comps = []
    dims = None
    for axis in ("CoordinateX", "CoordinateY", "CoordinateZ"):
        arr = _num(gc.get(axis))
        if arr is None:
            return None
        comps.append(arr)
    if any(a.size == 0 for a in comps):
        return None
    n = comps[0].size
    if any(a.size != n for a in comps):
        return None
    dims = tuple(int(d) for d in (gc.get("CoordinateX").dims or (n,)))
    verts = np.column_stack(comps)
    if len(dims) != 3:
        return verts, None
    ni, nj, nk = dims[0], dims[1], dims[2]
    if ni < 2 or nj < 2 or nk < 2:
        return verts, None
    ii, jj, kk = np.meshgrid(np.arange(ni - 1), np.arange(nj - 1),
                             np.arange(nk - 1), indexing="ij")
    base = ((kk * nj) + jj) * ni + ii
    j_off = ((kk * nj) + (jj + 1)) * ni
    k_off = (((kk + 1) * nj) + jj) * ni
    conn = np.stack([
        base, base + 1, j_off + ii + 1, j_off + ii,
        k_off + ii, k_off + ii + 1,
        ((kk + 1) * nj + jj + 1) * ni + ii + 1,
        ((kk + 1) * nj + jj + 1) * ni + ii,
    ], axis=-1).reshape(-1, 8)
    return verts, conn


def _fields_adf(zone, n_vertices):
    out = {}
    fs = zone.get("FlowSolution")
    if fs is None:
        return out
    for name, n in fs.children.items():
        arr = _num(n)
        if arr is None or arr.ndim != 1 or arr.size == 0:
            continue
        loc = "node" if arr.size == n_vertices else "cell"
        out[name] = (arr, loc)
    return out


def _bcs_adf(zone):
    out = []
    zbc = zone.get("ZoneBC")
    if zbc is None:
        return out
    for name, bc in zbc.children.items():
        pl = bc.get("PointList")
        ids = _iarr(pl) if pl is not None else None
        if ids is None:
            pr = bc.get("PointRange")
            ids = _iarr(pr) if pr is not None else None
        if ids is None or ids.size == 0:
            continue
        out.append((name, ids - 1))
    return out


def _decode_zone_adf(args):
    """Module-level worker for :func:`read_cgns_adf` (picklable for a Pool).

    args = (path, base_name, zone_name). Re-reads the ADF file in the
    worker, locates the base/zone, decodes to a picklable 8-tuple:
    (verts, conn, ctypes, fields, bcs, n_v, n_c, vol_name).
    """
    path, base_name, zone_name = args
    root = read_adf(path)
    if root is None:
        return None
    bases = [n for n in root.children.values() if n.label == "CGNSBase_t"]
    if not bases:
        bases = [root]
    multi_base = len(bases) > 1
    base = next((b for b in bases if b.name == base_name), bases[0])
    zone = base.get(zone_name)
    if zone is None:
        return None
    if _zone_type(zone) == "Structured":
        out = _structured_adf(zone)
        if out is None:
            return None
        verts, conn = out
        ctypes = (np.full(conn.shape[0], 12, dtype=np.int64)
                  if conn is not None else None)
    else:
        verts = _coordinates(zone)
        if verts is None:
            return None
        conn, ctypes = _read_cells_adf(zone)
    n_v = verts.shape[0]
    n_c = conn.shape[0] if conn is not None else 0
    bcs = []
    for n, ids in _bcs_adf(zone):
        n = ("%s/%s" % (base.name, n)) if multi_base else n
        bcs.append((n, ids))
    vol_name = ("%s/%s" % (base.name, zone.name)) if multi_base else zone.name
    return verts, conn, ctypes, _fields_adf(zone, n_v), bcs, n_v, n_c, vol_name


def _decode_zone_adf_local(base, zone, multi_base):
    """Serial-path decoder for :func:`read_cgns_adf`.

    base/zone are already-parsed :class:`AdfNode` values; returns the same
    picklable 8-tuple as :func:`_decode_zone_adf` so both paths merge
    identically.
    """
    if _zone_type(zone) == "Structured":
        out = _structured_adf(zone)
        if out is None:
            return None
        verts, conn = out
        ctypes = (np.full(conn.shape[0], 12, dtype=np.int64)
                  if conn is not None else None)
    else:
        verts = _coordinates(zone)
        if verts is None:
            return None
        conn, ctypes = _read_cells_adf(zone)
    n_v = verts.shape[0]
    n_c = conn.shape[0] if conn is not None else 0
    bcs = []
    for n, ids in _bcs_adf(zone):
        n = ("%s/%s" % (base.name, n)) if multi_base else n
        bcs.append((n, ids))
    vol_name = ("%s/%s" % (base.name, zone.name)) if multi_base else zone.name
    return verts, conn, ctypes, _fields_adf(zone, n_v), bcs, n_v, n_c, vol_name


def read_cgns_adf(path, workers: int = 0, use_threads: bool = False):
    """Read a CGNS ADF file into the mesh-dict shape (R3.5).

    Mirrors cgns.read_cgns (HDF5 path): merged multi-zone mesh, per-cell
    types, node/cell fields, surface regions from ZoneBC PointList/
    PointRange.  Returns None for a non-ADF file.

    ``workers`` (R26-S2) > 1 decodes zones concurrently and 0/1 keeps the
    serial path. By default a process pool is used (``use_threads=False``);
    pass ``use_threads=True`` to use a thread pool (regression-guard when
    process-pool spawn overhead dominates a tiny sample). The merge order
    and output are identical either way.
    """
    if not is_cgns_adf(path):
        return None
    try:
        root = read_adf(path)
    except Exception:
        return None
    bases = [n for n in root.children.values() if n.label == "CGNSBase_t"]
    if not bases:
        bases = [root]
    zone_jobs = []  # (base, zone)
    for base in bases:
        for zone in _cgns_zones(base):
            zone_jobs.append((base, zone))
    if not zone_jobs:
        return None
    multi_base = len(bases) > 1
    if workers and workers > 1 and len(zone_jobs) > 1:
        args = [(path, b.name, z.name) for b, z in zone_jobs]
        if use_threads:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                zone_outs = list(ex.map(_decode_zone_adf, args))
        else:
            import multiprocessing as mp
            with mp.Pool(processes=workers) as pool:
                zone_outs = pool.map(_decode_zone_adf, args)
    else:
        zone_outs = []
        for base, zone in zone_jobs:
            zone_outs.append(_decode_zone_adf_local(base, zone, multi_base))
    all_verts = []
    all_conn = []
    all_types = []
    zone_fields = []
    zone_nv = []
    zone_nc = []
    surface_regions = []
    volume_regions = []
    vert_offset = 0
    for out in zone_outs:
        if out is None:
            continue
        verts, conn, ctypes, fields, bcs, n_v, n_c, vol_name = out
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
        volume_regions.append(vol_name)
        vert_offset += n_v
    if not all_verts:
        return None
    vertices = np.vstack(all_verts)
    width = max(a.shape[1] for a in all_conn) if all_conn else 8
    total_c = sum(a.shape[0] for a in all_conn) if all_conn else 0
    cell_conn = np.full((total_c, width), -1, dtype=np.int64)
    r = 0
    for a in all_conn:
        cell_conn[r:r + a.shape[0], :a.shape[1]] = a
        r += a.shape[0]
    cell_types = np.concatenate(all_types) if all_types else None
    names = []
    for zf in zone_fields:
        for n in zf:
            if n not in names:
                names.append(n)
    fields = {}
    for fname in names:
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
        node_arr = np.concatenate(node_parts) if node_parts else np.zeros(0)
        cell_arr = np.concatenate(cell_parts) if cell_parts else np.zeros(0)
        if node_arr.size and (cell_arr.size == 0 or
                np.isfinite(node_arr).sum() >= np.isfinite(cell_arr).sum()):
            fields[fname] = (node_arr, "node")
        elif cell_arr.size:
            fields[fname] = (cell_arr, "cell")
    first_base, first_zone = zone_jobs[0]
    return {
        "vertices": vertices,
        "cell_conn": cell_conn,
        "cell_types": cell_types,
        "n_vertices": int(vertices.shape[0]),
        "n_cells": total_c,
        "fields": fields,
        "surface_regions": surface_regions,
        "volume_regions": volume_regions,
        "zone_name": first_zone.name,
        "base_name": ",".join(b.name for b in bases),
        "n_bases": len(bases),
        "adf": True,
    }
