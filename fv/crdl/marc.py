"""Marc / Mentat mesh and post-file readers.

``.dat``: Mentat ``connectivity`` / ``coordinates`` cards (Volume C input)
or comma-separated node/element lines.
``.t16`` / ``.t19``: PLDUMP2000 revision-9+ post files (Volume D Ch.9):
Fortran unformatted sequential records wrapped in ``=beg=NNNNN`` /
``=end=`` sections (A1 one character per word).  Formatted ``.t19``
uses the same section codes as text.  Pre-revision-9 files without
``=beg=`` are read as classic K7 PLDUMP.  Last-increment nodal vectors
and element post-codes are imported; every increment's time is kept.
"""

from __future__ import annotations

import re
import struct
from typing import Optional

import numpy as np

_NODE_COUNT_TO_VTK = {8: (12, 8), 4: (10, 4), 6: (13, 6), 5: (14, 5)}
_VTK_3D = {4: (10, 4), 5: (14, 5), 6: (13, 6), 8: (12, 8), 10: (24, 10)}
_DISP_NAMES = ("Displacement_X", "Displacement_Y", "Displacement_Z")
# Volume B / HyperView element families (2-D vs 3-D decided with NCRD).
_TRI_TYPES = frozenset({2, 6, 31, 37, 124, 125, 128, 138, 156, 173})
_QUAD_TYPES = frozenset({
    3, 10, 11, 18, 26, 27, 28, 30, 32, 39, 41, 55, 68, 72, 75,
    114, 115, 116, 118, 139, 174, 185,
})
_TET_TYPES = frozenset({127, 134, 157})
_HEX_TYPES = frozenset({7, 21, 35, 43, 117, 149})
_WEDGE_TYPES = frozenset({136, 202})
# Volume C POST + HyperView MARC reader; 6xx = Mentat 2014+ Cauchy aliases
# (341–346 + 340 → 681–686).
_POST_NAMES = {
    7: "Equiv_Plastic_Strain", 8: "Equiv_Creep_Strain",
    9: "Total_Temperature", 10: "Temperature_Increment",
    17: "Equiv_Mises", 20: "Thickness", 38: "Swelling_Strain",
    47: "Equiv_Cauchy", 48: "Strain_Energy_Density", 58: "Elastic_SED",
    78: "Volume",
}
_TENSOR_FAMILIES = (
    (1, "Strain"), (11, "Stress"), (21, "Plastic_Strain"),
    (301, "Total_Strain"), (311, "Stress"), (321, "Plastic_Strain"),
    (331, "Creep_Strain"), (341, "Cauchy"), (391, "Cauchy_Preferred"),
    (411, "Stress_Global"), (681, "Cauchy"),
)
_COMP6 = ("XX", "YY", "ZZ", "XY", "YZ", "ZX")
_NODAL_QTY = {
    1: "Displacement", 2: "Rotation", 3: "External_Force",
    5: "Reaction_Force", 14: "Temperature", 15: "External_Heat_Flux",
    16: "Reaction_Heat_Flux", 17: "Electric_Potential",
    28: "Velocity", 30: "Acceleration", 34: "Contact_Normal_Stress",
    35: "Contact_Normal_Force", 37: "Contact_Friction_Force",
    40: "Herrmann",
}
_MARC_EXP = re.compile(
    r"^([+-]?(?:\d+\.\d+|\d+\.|\.\d+|\d+))([+-]\d+)$")


def _marc_float(tok: str) -> float:
    """Marc/Fortran token: ``2.5+1`` and ``1.0D-3`` both accepted."""
    s = tok.strip().replace("D", "E").replace("d", "e")
    m = _MARC_EXP.match(s)
    if m:
        return float(m.group(1) + "E" + m.group(2))
    return float(s)


def _post_name(code: int, label: str = "") -> str:
    lab = (label or "").strip().replace(" ", "_")
    if lab and re.search(r"[A-Za-z]", lab):
        return lab
    if code in _POST_NAMES:
        return _POST_NAMES[code]
    for base, stem in _TENSOR_FAMILIES:
        if base <= code < base + 6:
            return "%s_%s" % (stem, _COMP6[code - base])
    return "POST_%d" % int(code)


def parse_marc(path: str):
    """Parse Marc .dat (Mentat cards or comma-separated) -> mesh-dict."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None
    mesh = _parse_mentat_dat(text)
    if mesh is not None:
        return mesh
    return _parse_comma_dat(text)


def _parse_comma_dat(text: str):
    nodes = {}
    cells = []
    cell_types = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s[0] in ("$", "*", "!"):
            continue
        parts = [p.strip() for p in s.split(",")]
        if len(parts) < 4:
            continue
        try:
            [float(p) for p in parts]
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
    if not nodes or not cells:
        return None
    return _mesh_from_nodes_cells(nodes, cells, cell_types)


def _parse_mentat_dat(text: str):
    """Volume C Mentat deck: ``connectivity`` + ``coordinates`` sections."""
    lines = text.splitlines()
    if not any(ln.strip().lower() == "connectivity" for ln in lines):
        return None
    if not any(ln.strip().lower().startswith("coordinates") for ln in lines):
        return None
    nodes = {}
    cells = []
    section = ""
    coord_header_seen = False
    default_type = 0
    for raw in lines:
        s = raw.strip()
        if not s or s[0] in ("$", "*", "!"):
            continue
        key = s.split()[0].lower()
        if key == "elements" and section != "connectivity":
            toks = s.split()
            if len(toks) >= 2:
                try:
                    default_type = int(float(toks[1]))
                except ValueError:
                    pass
            continue
        if key == "connectivity":
            section = "connectivity"
            continue
        if key.startswith("coordinate"):
            section = "coordinates"
            coord_header_seen = False
            continue
        if s[0].isalpha():
            if section in ("connectivity", "coordinates"):
                section = ""
            continue
        if section == "connectivity":
            ints = _ints_line(s)
            if len(ints) < 4 or ints[0] <= 0:
                continue
            jtype = ints[1] if ints[1] > 0 else default_type
            gids = [int(v) for v in ints[2:] if int(v) > 0]
            cells.append((jtype, gids))
        elif section == "coordinates":
            if not coord_header_seen:
                coord_header_seen = True
                continue
            parsed = _coord_line(s)
            if parsed is not None:
                nodes[parsed[0]] = parsed[1]
    if not nodes or not cells:
        return None
    out_cells = []
    out_types = []
    ncrd = 2 if all(abs(xyz[2]) < 1e-12 for xyz in nodes.values()) else 3
    for jtype, gids in cells:
        kept = [g for g in gids if g in nodes]
        mapped = _vtk_for_element(ncrd, kept, nodes, jtype=jtype)
        if mapped is None:
            continue
        vtk_t, ids = mapped
        out_cells.append(ids)
        out_types.append(vtk_t)
    if not out_cells:
        return None
    mesh = _mesh_from_nodes_cells(nodes, out_cells, out_types)
    mesh["meta"] = {"format": "mentat-dat", "ncrd": ncrd}
    return mesh


def _ints_line(s: str) -> list[int]:
    out = []
    for tok in s.replace(",", " ").split():
        try:
            out.append(int(float(tok)))
        except ValueError:
            return []
    return out


def _coord_line(s: str):
    toks = s.replace(",", " ").split()
    if len(toks) < 3:
        return None
    try:
        nid = int(float(toks[0]))
        xyz = [0.0, 0.0, 0.0]
        for i, tok in enumerate(toks[1:4]):
            xyz[i] = _marc_float(tok)
        return nid, xyz
    except ValueError:
        return None


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
        with open(path, encoding="utf-8", errors="replace") as fh:
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
    """True if *path* looks like a Mentat/PLDUMP post file."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(320)
    except OSError:
        return False
    return (_is_beg_binary(head) or _is_beg_text(head)
            or _is_classic_pldump(head))


def parse_marc_post(path: str):
    """Parse Mentat ``.t16`` / ``.t19`` post file -> mesh-dict.

    PLDUMP2000 (rev ≥ 9): sections 507nn/50800 geometry, 524nn nodal
    vectors, 52300 element post-codes.  Pre-rev-9 files use the classic
    K7 sequential blocks from Volume D.
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
    if _is_classic_pldump(data):
        return _parse_classic_pldump(data)
    return None


def _is_classic_pldump(data: bytes) -> bool:
    """K7 binary: first record is 70 A1 words, not ``=beg=``."""
    if len(data) < 16:
        return False
    ln = struct.unpack_from("<I", data, 0)[0]
    if ln != 280 or ln + 8 > len(data):
        return False
    payload = data[4:4 + ln]
    title = _a1(payload).strip()
    return bool(title) and not title.startswith("=beg=")


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
    post_labels = []
    for recs in _first_present(sections, "50602", "50600"):
        for item in recs:
            code, lab = _postcode_item(item, binary)
            if code is None:
                continue
            post_codes.append(code)
            post_labels.append(lab)

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
    for recs in _first_present(sections, "50702", "50700"):
        items = recs
        if items and len(_ints_of(items[0], binary)) <= 3:
            items = items[1:]
        for item in items:
            vals = _ints_of(item, binary)
            if len(vals) < 4:
                continue
            jtype = int(vals[1])
            nnode = int(vals[2]) if vals[2] > 0 else nnodmx
            gids = [int(v) for v in vals[3:3 + nnode] if int(v) > 0]
            mapped = _vtk_for_element(ncrd, gids, nodes, jtype=jtype)
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
    nodal_name = "Displacement"
    disp_blocks = _all_present(sections, "52401", "52400")
    for recs in reversed(disp_blocks):
        got = _parse_nodal_pldump2000(recs, lnum, ndeg, binary)
        if got is None:
            got = _parse_nodal_block(recs, lnum, ndeg, binary)
            if got is not None:
                last_disp, nvec, ndeg = got
                break
        else:
            last_disp, nvec, ndeg, nodal_name = got
            break

    inc_meta = _increment_table(sections, binary)
    n_inc = len(inc_meta)
    last_inc = inc_meta[-1]["inc"] if inc_meta else 0
    last_time = inc_meta[-1]["time"] if inc_meta else None

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
        stem = nodal_name or "Displacement"
        for c, arr in enumerate(comps):
            fields[_DISP_NAMES[c] if stem == "Displacement"
                   else "%s_%s" % (stem, "XYZ"[c])] = (arr, "node")
        mag = np.sqrt(sum(a * a for a in comps))
        fields[stem] = (mag, "node")
    if last_evar is not None and last_evar.shape[0] == mesh["n_cells"]:
        for ci in range(last_evar.shape[1]):
            code = post_codes[ci] if ci < len(post_codes) else ci + 1
            lab = post_labels[ci] if ci < len(post_labels) else ""
            name = _post_name(int(code), lab)
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
        "times": [row["time"] for row in inc_meta],
        "increments": inc_meta,
        "post_codes": post_codes,
        "n_vectors": nvec,
        "nstres": nstres,
        "spec": "PLDUMP2000",
    }
    return mesh


def _first_present(sections: dict, *codes):
    for code in codes:
        if sections.get(code):
            return sections[code]
    return []


def _all_present(sections: dict, *codes):
    out = []
    for code in codes:
        out.extend(sections.get(code) or [])
    return out


def _postcode_item(item, binary: bool):
    if binary:
        if len(item) < 4:
            return None, ""
        code = struct.unpack_from("<i", item, 0)[0]
        lab = _a1(item[8:]).strip() or _a1(item[4:]).strip()
        return int(code), lab
    toks = _tokens(item) if isinstance(item, str) else []
    if not toks:
        return None, ""
    try:
        code = int(float(toks[0]))
    except ValueError:
        return None, ""
    lab = " ".join(toks[1:]).strip()
    return code, lab


def _increment_table(sections: dict, binary: bool) -> list:
    """PLDUMP2000 51701 + 51801 → [{inc, time, jantyp, energy}, ...]."""
    i_blocks = sections.get("51701") or sections.get("51700") or []
    r_blocks = sections.get("51801") or sections.get("51800") or []
    rows = []
    for i, ib in enumerate(i_blocks):
        ivals = _ints_of(ib[0], binary) if ib else []
        inc = int(ivals[1]) if len(ivals) > 1 else i
        jantyp = int(ivals[3]) if len(ivals) > 3 else 0
        time = None
        energy = None
        if i < len(r_blocks):
            for item in r_blocks[i]:
                if binary and len(item) < 8:
                    continue
                vals = _floats_of(item, binary, prefer64=True)
                if vals:
                    time = float(vals[0])
                    if len(vals) > 8:
                        energy = float(vals[8])
                    break
        rows.append({"inc": inc, "time": time, "jantyp": jantyp,
                     "strain_energy": energy})
    return rows


def _parse_nodal_pldump2000(recs, lnum: int, ndeg: int, binary: bool):
    """Volume D 524nn: nnqnod/nnvnod, 48-char name, ivec(12), optional data.

    ``ivec(7) == -1`` means values for all nodes (1-based; index 6).
    """
    if not recs:
        return None
    if binary:
        if len(recs[0]) < 8:
            return None
        nnqnod, nnvnod = struct.unpack_from("<ii", recs[0], 0)
        if nnqnod < 1 or nnqnod > 32:
            return None
        i = 1
        last = None
        for _ in range(nnqnod):
            if i >= len(recs):
                break
            name = _a1(recs[i]).strip() if len(recs[i]) >= 8 else ""
            i += 1
            if i >= len(recs):
                break
            ivec = _ints_of(recs[i], True)
            i += 1
            ncomp = ivec[3] if len(ivec) > 3 and ivec[3] > 0 else ndeg
            flag = ivec[6] if len(ivec) > 6 else 0
            qty = ivec[0] if ivec else 1
            stem = name or _NODAL_QTY.get(qty, "Displacement")
            if flag == -1 and i < len(recs):
                payload = recs[i]
                i += 1
                need = lnum * ncomp
                if len(payload) == need * 4:
                    vals = np.frombuffer(payload, dtype="<f4").astype(np.float64)
                elif len(payload) == need * 8:
                    vals = np.frombuffer(payload, dtype="<f8").copy()
                else:
                    continue
                last = (vals.reshape(lnum, ncomp), nnqnod, ncomp, stem)
            # skip imaginary block if present
            if len(ivec) > 5 and ivec[5] in (4, 5) and i < len(recs):
                i += 1
        return last
    # formatted: reuse size-based reader but keep the label
    got = _parse_nodal_block(recs, lnum, ndeg, False)
    if got is None:
        return None
    arr, nvec, nd = got
    return arr, nvec, nd, "Displacement"


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


def _vtk_for_element(ncrd: int, gids: list, nodes: dict, jtype: int = 0):
    """Map Marc element type (Volume B) + node list to VTK."""
    ids = [g for g in gids if g in nodes] or list(gids)
    # Herrmann / unused trailing nodes sit at the origin and are not
    # geometric (Mentat .dat omits them from the coordinates table).
    if ncrd <= 2 or jtype in _QUAD_TYPES or jtype in _TRI_TYPES:
        while len(ids) > 4:
            last = ids[-1]
            xyz = nodes.get(last)
            if (xyz is not None
                    and abs(xyz[0]) <= 1e-20
                    and abs(xyz[1]) <= 1e-20
                    and last not in ids[:-1]):
                ids.pop()
                continue
            if last not in nodes:
                ids.pop()
                continue
            break
    if jtype in _TRI_TYPES or (ncrd <= 2 and len(ids) == 3):
        return (5, ids[:3]) if len(ids) >= 3 else None
    if jtype in _QUAD_TYPES or (ncrd <= 2 and len(ids) >= 4):
        return (9, ids[:4]) if len(ids) >= 4 else None
    if jtype in _TET_TYPES or (ncrd >= 3 and len(ids) == 4):
        return (10, ids[:4]) if len(ids) >= 4 else None
    if jtype in _WEDGE_TYPES or (ncrd >= 3 and len(ids) == 6):
        return (13, ids[:6]) if len(ids) >= 6 else None
    if jtype in _HEX_TYPES or (ncrd >= 3 and len(ids) >= 8):
        return (12, ids[:8]) if len(ids) >= 8 else None
    if ncrd <= 2:
        if len(ids) >= 4:
            return 9, ids[:4]
        if len(ids) == 3:
            return 5, ids
        return None
    info = _VTK_3D.get(len(ids))
    if info is None:
        return None
    vtk_t, nn = info
    return vtk_t, ids[:nn]


def _parse_classic_pldump(data: bytes):
    """Volume D K7 sequential blocks (no ``=beg=`` wrappers)."""
    recs = list(_iter_unformatted(data))
    if len(recs) < 4:
        return None
    title = _a1(recs[0]).strip()
    if title.startswith("=beg=") or len(recs[1]) < 72:
        return None
    ints = list(struct.unpack("<" + "i" * (len(recs[1]) // 4), recs[1][:72]))
    if len(ints) < 11:
        return None
    inum, lnum, mnum = ints[0], ints[1], ints[2]
    ncrd = ints[8] if ints[8] > 0 else 3
    nnodmx = ints[9] if ints[9] > 0 else 8
    postrv = ints[13] if len(ints) > 13 else 7
    i = 2
    # K7: block 3 (12 ints), 4 (1), 5 (2) then INUM postcode records
    if postrv >= 7 and i < len(recs) and len(recs[i]) == 48:
        i += 1
    if postrv >= 7 and i < len(recs) and len(recs[i]) == 4:
        i += 1
    if postrv >= 7 and i < len(recs) and len(recs[i]) == 8:
        i += 1
    i += inum  # skip postcode records
    nodes = {}
    node_ids = []
    cells = []
    cell_types = []
    # connectivity: MNUM records of about (nnodmx+3)*4 bytes
    conn_w = (nnodmx + 3) * 4
    taken = 0
    while i < len(recs) and taken < mnum:
        if len(recs[i]) < 16:
            i += 1
            continue
        vals = list(struct.unpack("<" + "i" * (len(recs[i]) // 4), recs[i]))
        if len(vals) >= 4:
            jtype = vals[1]
            nnode = vals[2] if vals[2] > 0 else nnodmx
            gids = [int(v) for v in vals[3:3 + nnode] if int(v) > 0]
            mapped = _vtk_for_element(ncrd, gids, nodes, jtype=jtype)
            if mapped is not None:
                cells.append(mapped[1])
                cell_types.append(mapped[0])
                taken += 1
        i += 1
        if len(recs[i - 1]) != conn_w and taken and taken < 3:
            # not actually connectivity; rewind this record
            cells.clear()
            cell_types.clear()
            taken = 0
            break
    if not cells:
        return None
    # coordinates
    coord_w = 4 + 4 * ncrd
    taken = 0
    while i < len(recs) and taken < lnum:
        parsed = _parse_coord_item(recs[i], ncrd, True)
        if parsed is not None:
            nid, xyz = parsed
            nodes[nid] = xyz
            node_ids.append(nid)
            taken += 1
        i += 1
        if taken == 0 and len(recs[i - 1]) != coord_w:
            break
    if not nodes:
        return None
    # remap cells now that nodes exist
    remapped_cells = []
    remapped_types = []
    for gids, vtk_t in zip(cells, cell_types):
        mapped = _vtk_for_element(ncrd, gids, nodes)
        if mapped is None:
            remapped_cells.append(gids)
            remapped_types.append(vtk_t)
        else:
            remapped_cells.append(mapped[1])
            remapped_types.append(mapped[0])
    mesh = _mesh_from_nodes_cells(nodes, remapped_cells, remapped_types)
    mesh["meta"] = {
        "title": title,
        "inum": inum,
        "lnum": lnum,
        "mnum": mnum,
        "ncrd": ncrd,
        "postrv": postrv,
        "spec": "PLDUMP-K7",
        "n_increments": 0,
        "last_increment": 0,
        "time": None,
        "times": [],
        "increments": [],
        "post_codes": [],
    }
    return mesh


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
