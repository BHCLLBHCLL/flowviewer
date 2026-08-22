"""Marc / Mentat mesh and post-file readers.

``.dat``: comma-separated node/element cards (existing text mesh).
``.t16`` / ``.t19``: Mentat post files (style 14 ``=beg=`` / ``=end=``
sections).  Binary ``.t16`` is Fortran unformatted sequential with A1
characters stored one per 4-byte word.  Formatted ``.t19`` uses the
same section codes as plain text.  Last increment nodal displacements
and element post-codes are imported.
"""

from __future__ import annotations

import struct
from typing import Optional

import numpy as np

_NODE_COUNT_TO_VTK = {8: (12, 8), 4: (10, 4), 6: (13, 6), 5: (14, 5)}
_VTK_3D = {4: (10, 4), 5: (14, 5), 6: (13, 6), 8: (12, 8), 10: (24, 10)}
_DISP_NAMES = ("Displacement_X", "Displacement_Y", "Displacement_Z")


def parse_marc(path: str):
    """Parse Marc .dat free text -> mesh-dict (3)."""
    nodes = {}
    cells = []
    cell_types = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s[0] in ("$", "*", "!"):
                    continue
                parts = [p.strip() for p in s.split(",")]
                if len(parts) < 4:
                    continue
                try:
                    nums = [float(p) for p in parts]
                except ValueError:
                    continue
                if len(parts) == 4 and abs(float(parts[1])) < 1e9:
                    nodes[int(float(parts[0]))] = [float(x) for x in parts[1:4]]
                    continue
                n_nodes = len(parts) - 2
                if n_nodes in _NODE_COUNT_TO_VTK:
                    vtk_t, nn = _NODE_COUNT_TO_VTK[n_nodes]
                    gids = [int(float(parts[i])) for i in range(2, 2 + nn)]
                    cells.append(gids)
                    cell_types.append(vtk_t)
    except Exception:
        return None
    if not nodes or not cells:
        return None
    return _mesh_from_nodes_cells(nodes, cells, cell_types)


def parse_marc_results(path: str, order: dict, n_vertices: int,
                       names: Optional[list] = None):
    """Import node scalar results from an ASCII results file (7).

    Each non-comment line is ``node_id value [value ...]`` where ``node_id``
    is the Marc global node id (matching the .dat).  Values are mapped
    through ``order`` (global -> local index) into node-located variables.
    Column 1 -> name ``RES1`` (or ``names[0]``), column 2 -> ``RES2``, ...
    """
    if not order or n_vertices <= 0:
        return {}
    cols = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s[0] in ("$", "*", "!", "#"):
                    continue
                parts = s.replace(",", " ").split()
                if len(parts) < 2:
                    continue
                try:
                    gid = int(float(parts[0]))
                    vals = [float(x) for x in parts[1:]]
                except ValueError:
                    continue
                if gid not in order:
                    continue
                li = order[gid]
                if li >= n_vertices:
                    continue
                if not cols:
                    cols = [[] for _ in vals]
                for ci, v in enumerate(vals):
                    if ci >= len(cols):
                        cols.append([])
                    cols[ci].append((li, v))
    except Exception:
        return {}
    if not cols or not cols[0]:
        return {}
    fields = {}
    for ci, pairs in enumerate(cols):
        arr = np.full(n_vertices, np.nan, dtype=np.float64)
        for li, v in pairs:
            arr[li] = v
        name = (names[ci] if names and ci < len(names) else "RES" + str(ci + 1))
        fields[name] = (arr, "node")
    return fields


def is_marc_post(path: str) -> bool:
    """True if *path* looks like a Mentat ``=beg=`` post file."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(320)
    except OSError:
        return False
    return _is_beg_binary(head) or _is_beg_text(head)


def parse_marc_post(path: str):
    """Parse Mentat ``.t16`` / ``.t19`` post file -> mesh-dict.

    Geometry comes from sections 50702 / 50800; last-increment nodal
    displacements (52401) and element post-codes (52300) become fields.
    Returns ``None`` if the file is not a readable ``=beg=`` post file.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    if _is_beg_binary(data):
        raw = _collect_binary_sections(data)
        if not raw:
            return None
        return _mesh_from_beg_sections(raw, binary=True)
    if _is_beg_text(data):
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            return None
        raw = _collect_text_sections(text)
        if not raw:
            return None
        return _mesh_from_beg_sections(raw, binary=False)
    return None


def _is_beg_binary(data: bytes) -> bool:
    if len(data) < 16:
        return False
    ln = struct.unpack_from("<I", data, 0)[0]
    if ln > len(data) - 8 or ln < 20:
        return False
    payload = data[4:4 + ln]
    return _a1(payload).lstrip().startswith("=beg=")


def _is_beg_text(data: bytes) -> bool:
    head = data[:240].lstrip()
    return head.startswith(b"=beg=")


def _a1(payload: bytes) -> str:
    return "".join(
        chr(payload[k]) if 32 <= payload[k] < 127 else "."
        for k in range(0, len(payload), 4)
    )


def _iter_unformatted(data: bytes):
    i = 0
    n = len(data)
    while i + 8 <= n:
        (ln,) = struct.unpack_from("<I", data, i)
        end = i + 4 + ln
        if end + 4 > n:
            break
        (endm,) = struct.unpack_from("<I", data, end)
        if endm != ln:
            break
        yield data[i + 4:end]
        i = end + 4


def _collect_binary_sections(data: bytes) -> dict:
    sections: dict[str, list] = {}
    cur = None
    bucket = None
    for payload in _iter_unformatted(data):
        txt = _a1(payload).rstrip()
        if txt.startswith("=beg="):
            cur = txt[5:10] if len(txt) >= 10 else txt[5:]
            bucket = []
            sections.setdefault(cur, []).append(bucket)
            continue
        if txt == "=end=":
            cur = None
            bucket = None
            continue
        if bucket is not None:
            bucket.append(payload)
    return sections


def _collect_text_sections(text: str) -> dict:
    sections: dict[str, list] = {}
    cur = None
    bucket = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("=beg="):
            cur = s[5:10] if len(s) >= 10 else s[5:]
            bucket = []
            sections.setdefault(cur, []).append(bucket)
            continue
        if s.startswith("=end="):
            cur = None
            bucket = None
            continue
        if bucket is not None and s:
            bucket.append(s)
    return sections


def _ints_of(item, binary: bool) -> list[int]:
    if binary:
        n = len(item) // 4
        if n <= 0:
            return []
        return list(struct.unpack("<" + "i" * n, item[:n * 4]))
    return [int(float(x)) for x in _tokens(item)]


def _floats_of(item, binary: bool, prefer64: bool = False) -> list[float]:
    if binary:
        if prefer64 and len(item) % 8 == 0:
            n = len(item) // 8
            return list(struct.unpack("<" + "d" * n, item))
        if len(item) % 4 == 0:
            n = len(item) // 4
            return list(struct.unpack("<" + "f" * n, item))
        return []
    return [float(x) for x in _tokens(item)]


def _tokens(line: str) -> list[str]:
    s = line.strip().replace(",", " ")
    if not s:
        return []
    parts = s.split()
    if len(parts) >= 2:
        return parts
    # packed Fortran I13 / E13.6
    if len(s) > 13 and " " not in s:
        return [s[i:i + 13] for i in range(0, len(s), 13) if s[i:i + 13].strip()]
    return parts


def _mesh_from_beg_sections(sections: dict, binary: bool):
    vfy = sections.get("50200")
    if not vfy or not vfy[0]:
        return None
    ints = []
    for item in vfy[0]:
        ints.extend(_ints_of(item, binary))
    if len(ints) < 11:
        return None
    inum = ints[0]
    lnum = ints[1]
    mnum = ints[2]
    ndeg = max(ints[3], 1)
    nstres = max(ints[4], 1)
    ncrd = ints[8] if len(ints) > 8 else 3
    nnodmx = ints[9] if len(ints) > 9 else 8
    iantyp = ints[10] if len(ints) > 10 else 0
    postrv = ints[13] if len(ints) > 13 else 0
    if ncrd <= 0:
        ncrd = 3

    post_codes = []
    for recs in sections.get("50602", []):
        for item in recs:
            vals = _ints_of(item, binary)
            if vals:
                post_codes.append(int(vals[0]))

    nodes = {}
    node_ids = []
    for recs in sections.get("50800", []):
        for item in recs:
            parsed = _parse_coord_item(item, ncrd, binary)
            if parsed is None:
                continue
            nid, xyz = parsed
            nodes[nid] = xyz
            node_ids.append(nid)
    if not nodes:
        return None

    cells = []
    cell_types = []
    for recs in sections.get("50702", []):
        items = recs
        if items and len(_ints_of(items[0], binary)) <= 3:
            items = items[1:]
        for item in items:
            vals = _ints_of(item, binary)
            if len(vals) < 4:
                continue
            nnode = int(vals[2]) if vals[2] > 0 else nnodmx
            gids = [int(v) for v in vals[3:3 + nnode] if int(v) > 0]
            mapped = _vtk_for_element(ncrd, gids, nodes)
            if mapped is None:
                continue
            vtk_t, kept = mapped
            cells.append(kept)
            cell_types.append(vtk_t)
    if not cells:
        return None

    last_evar = None
    evar_blocks = sections.get("52300") or []
    if evar_blocks:
        rows = []
        for item in evar_blocks[-1]:
            vals = _floats_of(item, binary)
            if vals:
                rows.append(vals[: max(inum, 1)])
        if rows:
            width = max(len(r) for r in rows)
            last_evar = np.full((len(rows), width), np.nan, dtype=np.float64)
            for i, r in enumerate(rows):
                last_evar[i, :len(r)] = r

    last_disp = None
    nvec = 1
    disp_blocks = sections.get("52401") or []
    for recs in reversed(disp_blocks):
        got = _parse_nodal_block(recs, lnum, ndeg, binary)
        if got is not None:
            last_disp, nvec, ndeg = got
            break

    n_inc = len(sections.get("51701") or [])
    last_inc = 0
    last_time = None
    if sections.get("51701"):
        ivals = _ints_of(sections["51701"][-1][0], binary)
        if len(ivals) > 1:
            last_inc = int(ivals[1])
    if sections.get("51801"):
        recs = sections["51801"][-1]
        for item in recs:
            if binary and len(item) < 8:
                continue
            vals = _floats_of(item, binary, prefer64=True)
            if vals:
                last_time = float(vals[0])
                break

    title = ""
    if sections.get("50100"):
        item = sections["50100"][0][0]
        title = (_a1(item) if binary else str(item)).strip()

    mesh = _mesh_from_nodes_cells(nodes, cells, cell_types)
    fields = mesh["fields"]
    order = mesh["node_order"]
    n_vertices = mesh["n_vertices"]
    if last_disp is not None and node_ids:
        ncomp = min(last_disp.shape[1], 3)
        comps = [np.full(n_vertices, np.nan, dtype=np.float64) for _ in range(ncomp)]
        nid_to_row = {nid: i for i, nid in enumerate(node_ids)}
        for nid, li in order.items():
            row = nid_to_row.get(nid)
            if row is None or row >= last_disp.shape[0]:
                continue
            for c in range(ncomp):
                comps[c][li] = last_disp[row, c]
        for c, arr in enumerate(comps):
            fields[_DISP_NAMES[c]] = (arr, "node")
        mag = np.sqrt(sum(a * a for a in comps))
        fields["Displacement"] = (mag, "node")
    if last_evar is not None and last_evar.shape[0] == mesh["n_cells"]:
        for ci in range(last_evar.shape[1]):
            code = post_codes[ci] if ci < len(post_codes) else ci + 1
            name = "POST_%d" % int(code)
            fields[name] = (np.asarray(last_evar[:, ci], dtype=np.float64), "cell")
    mesh["meta"] = {
        "title": title,
        "inum": inum,
        "lnum": lnum,
        "mnum": mnum,
        "ndeg": ndeg,
        "ncrd": ncrd,
        "iantyp": iantyp,
        "postrv": postrv,
        "n_increments": n_inc,
        "last_increment": last_inc,
        "time": last_time,
        "post_codes": post_codes,
        "n_vectors": nvec,
        "nstres": nstres,
    }
    return mesh


def _parse_coord_item(item, ncrd: int, binary: bool):
    if binary:
        if len(item) == 4 + 4 * ncrd:
            t = struct.unpack("<i" + "f" * ncrd, item)
        elif len(item) == 4 + 8 * ncrd:
            t = struct.unpack("<i" + "d" * ncrd, item)
        elif len(item) >= 12 and ncrd == 2:
            t = struct.unpack("<iff", item[:12])
        else:
            return None
        xyz = [0.0, 0.0, 0.0]
        for i, v in enumerate(t[1:1 + ncrd]):
            xyz[i] = float(v)
        return int(t[0]), xyz
    toks = _tokens(item) if isinstance(item, str) else []
    if len(toks) < 1 + ncrd:
        return None
    try:
        nid = int(float(toks[0]))
        xyz = [0.0, 0.0, 0.0]
        for i in range(ncrd):
            xyz[i] = float(toks[1 + i])
        return nid, xyz
    except ValueError:
        return None


def _parse_nodal_block(recs, lnum: int, ndeg: int, binary: bool):
    """Return ``(array(lnum, ncomp), nvec, ndeg)`` or None."""
    if not recs:
        return None
    nvec = 1
    if binary:
        hdr = recs[0]
        if len(hdr) >= 8:
            a, b = struct.unpack_from("<ii", hdr, 0)
            if 1 <= a <= 8 and 1 <= b <= 6:
                nvec, ndeg = a, b
        target32 = lnum * nvec * ndeg * 4
        target64 = lnum * nvec * ndeg * 8
        for item in recs:
            if len(item) == target32:
                vals = np.frombuffer(item, dtype="<f4").astype(np.float64)
                return vals.reshape(lnum, nvec * ndeg), nvec, ndeg
            if len(item) == target64:
                vals = np.frombuffer(item, dtype="<f8").copy()
                return vals.reshape(lnum, nvec * ndeg), nvec, ndeg
        return None
    floats = []
    for item in recs:
        toks = _tokens(item)
        # skip header-ish integer-only lines
        if toks and all(_is_int_token(t) for t in toks) and len(toks) <= 12:
            ints = [int(float(t)) for t in toks]
            if len(ints) >= 2 and 1 <= ints[0] <= 8 and 1 <= ints[1] <= 6:
                nvec, ndeg = ints[0], ints[1]
            continue
        for t in toks:
            try:
                floats.append(float(t))
            except ValueError:
                continue
    need = lnum * nvec * ndeg
    if need > 0 and len(floats) >= need:
        arr = np.asarray(floats[:need], dtype=np.float64).reshape(
            lnum, nvec * ndeg)
        return arr, nvec, ndeg
    return None


def _is_int_token(tok: str) -> bool:
    try:
        float(tok)
    except ValueError:
        return False
    return "." not in tok and "e" not in tok.lower()


def _vtk_for_element(ncrd: int, gids: list, nodes: dict):
    ids = list(gids)
    if ncrd <= 2:
        while len(ids) > 4:
            last = ids[-1]
            xyz = nodes.get(last)
            if (xyz is not None
                    and abs(xyz[0]) <= 1e-20
                    and abs(xyz[1]) <= 1e-20
                    and last not in ids[:-1]):
                ids.pop()
                continue
            break
        if len(ids) >= 4:
            return 9, ids[:4]
        if len(ids) == 3:
            return 5, ids
        return None
    n = len(ids)
    info = _VTK_3D.get(n)
    if info is None:
        return None
    vtk_t, nn = info
    return vtk_t, ids[:nn]


def _mesh_from_nodes_cells(nodes: dict, cells: list, cell_types: list):
    order = {}
    for gids in cells:
        for g in gids:
            if g not in order:
                order[g] = len(order)
    n_vertices = len(order)
    verts = np.zeros((n_vertices, 3))
    for g, i in order.items():
        xyz = nodes.get(g)
        if xyz is not None:
            verts[i, :len(xyz)] = xyz[:3]
    width = max((len(g) for g in cells), default=8)
    width = max(width, 8)
    conn = np.zeros((len(cells), width), dtype=np.int64) - 1
    for ci, gids in enumerate(cells):
        for k, g in enumerate(gids):
            conn[ci, k] = order[g]
    return {
        "vertices": verts,
        "cell_conn": conn,
        "cell_types": np.asarray(cell_types, dtype=np.int64),
        "n_vertices": n_vertices,
        "n_cells": len(cells),
        "node_order": order,
        "fields": {},
        "surface_regions": [],
        "volume_regions": ["Marc"],
        "meta": {},
    }
