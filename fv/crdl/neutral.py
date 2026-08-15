"""Neutral geometry reader (OBJ / STL / PLY) for the Neutral File object (1).

PLY additionally imports per-vertex scalar properties as node-located
variables (Neutral variable import, item 7).
"""

from __future__ import annotations

import struct
from typing import Optional

import numpy as np


def parse_obj(path: str):
    """Wavefront OBJ -> vertices + faces (1)."""
    verts = []
    faces = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.split()
                if parts[0] == "v" and len(parts) >= 4:
                    verts.append([float(x) for x in parts[1:4]])
                elif parts[0] == "f" and len(parts) >= 4:
                    ids = []
                    for tok in parts[1:]:
                        idx = int(tok.split("/")[0]) - 1
                        ids.append(idx)
                    faces.append(ids)
    except Exception:
        return None
    return _build(verts, faces)


def parse_stl(path: str):
    """ASCII STL -> vertices + triangle faces (1)."""
    verts = []
    faces = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            cur = []
            for line in fh:
                s = line.strip()
                if s.startswith("vertex "):
                    cur.append([float(x) for x in s.split()[1:4]])
                elif s.startswith("endfacet"):
                    if len(cur) == 3:
                        ids = []
                        for v in cur:
                            ids.append(len(verts))
                            verts.append(v)
                        faces.append(ids)
                    cur = []
    except Exception:
        return None
    return _build(verts, faces)


def _parse_ply_header_bytes(lines):
    """Parse PLY header lines (bytes) -> (fmt, n_v, n_f, vprops, flist)."""
    if not lines or lines[0].strip() != b"ply":
        return None
    fmt = None
    vertex_count = face_count = 0
    vertex_props = []
    face_list_prop = None
    in_vertex = in_face = False
    for raw in lines[1:]:
        line = raw.strip()
        if line == b"end_header":
            break
        if line.startswith(b"format "):
            fmt = line.split()[1].decode()
        elif line.startswith(b"element vertex "):
            vertex_count = int(line.split()[2])
            in_vertex, in_face = True, False
        elif line.startswith(b"element face "):
            face_count = int(line.split()[2])
            in_vertex, in_face = False, True
        elif line.startswith(b"element "):
            in_vertex = in_face = False
        elif line.startswith(b"property "):
            parts = line.split()
            if in_vertex and len(parts) == 3:
                vertex_props.append((parts[2].decode(), parts[1].decode()))
            elif in_face and parts[1] == b"list" and len(parts) == 5:
                face_list_prop = (parts[2].decode(), parts[3].decode())
    return fmt, vertex_count, face_count, vertex_props, face_list_prop


def _scalar_dtype(kind):
    """struct-format base char for a PLY scalar type (no endian prefix)."""
    return {
        "float": "f", "double": "d", "uchar": "B", "char": "b",
        "ushort": "H", "short": "h", "uint": "I", "int": "i",
    }.get(kind)


def _read_ascii_prop(tokens, kind):
    if kind in ("float", "double"):
        return float(tokens[0])
    return int(tokens[0])


def parse_ply(path: str):
    """PLY (ascii or binary) -> vertices + faces + node scalar fields (7).

    Returns the same mesh dict as parse_obj/parse_stl plus a fields key
    {name: (array, "node")} for every non-coordinate numeric vertex
    property.  Binary little/big endian are both supported.
    """
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        idx = raw.find(b"end_header")
        if idx < 0:
            return None
        idx += len(b"end_header")
        while idx < len(raw) and raw[idx:idx + 1] in (b"\n", b"\r"):
            idx += 1
        header_blob = raw[:idx]
        payload = raw[idx:]
        header_lines = header_blob.split(b"\n")
        hdr = _parse_ply_header_bytes(header_lines)
        if hdr is None:
            return None
        fmt, n_v, n_f, vprops, flist = hdr
        if fmt and fmt.startswith("binary"):
            endian = "<" if fmt.endswith("little_endian") else ">"
            return _parse_ply_binary(payload, endian, n_v, n_f, vprops, flist)
        text = payload.decode("utf-8", errors="replace").splitlines()
        return _parse_ply_ascii(text, n_v, n_f, vprops, flist)
    except Exception:
        return None


def _coord_and_scalars(vprops):
    """Split vertex props into (xyz names, scalar names)."""
    coords = []
    scalars = []
    for name, kind in vprops:
        if name in ("x", "y", "z"):
            coords.append((name, kind))
        else:
            scalars.append((name, kind))
    return coords, scalars


def _parse_ply_ascii(lines, n_v, n_f, vprops, flist):
    coords, scalars = _coord_and_scalars(vprops)
    verts = []
    scalar_vals = {name: [] for name, _ in scalars}
    xyz_pos = {name: i for i, (name, _) in enumerate(vprops)}
    li = 0
    for _ in range(n_v):
        while li < len(lines) and not lines[li].strip():
            li += 1
        if li >= len(lines):
            break
        tokens = lines[li].split(); li += 1
        if len(tokens) < len(vprops):
            break
        try:
            x = float(tokens[xyz_pos["x"]]); y = float(tokens[xyz_pos["y"]]); z = float(tokens[xyz_pos["z"]])
            verts.append([x, y, z])
            for name, kind in scalars:
                scalar_vals[name].append(_read_ascii_prop([tokens[xyz_pos[name]]], kind))
        except (ValueError, IndexError, KeyError):
            break
    faces = []
    for _ in range(n_f):
        while li < len(lines) and not lines[li].strip():
            li += 1
        if li >= len(lines):
            break
        tokens = lines[li].split(); li += 1
        try:
            n = int(tokens[0])
            ids = [int(t) for t in tokens[1:1 + n]]
            faces.append(ids)
        except (ValueError, IndexError):
            continue
    return _build_with_fields(verts, faces, scalar_vals)


def _parse_ply_binary(data, endian, n_v, n_f, vprops, flist):
    coords, scalars = _coord_and_scalars(vprops)
    prop_dtypes = []
    for name, kind in vprops:
        dt = _scalar_dtype(kind)
        prop_dtypes.append(endian + (dt or "f"))
    count_dtype = endian + ((_scalar_dtype(flist[0]) or "B") if flist else "B")
    idx_dtype = endian + ((_scalar_dtype(flist[1]) or "i") if flist else "i")
    verts = np.zeros((n_v, 3), dtype=np.float64)
    scalar_arrs = {name: np.zeros(n_v, dtype=np.float64) for name, _ in scalars}
    off = 0
    xyz_pos = {name: i for i, (name, _) in enumerate(vprops)}
    for i in range(n_v):
        row = []
        for d in prop_dtypes:
            sz = struct.calcsize(d)
            (val,) = struct.unpack_from(d, data, off)
            row.append(val)
            off += sz
        verts[i] = [row[xyz_pos["x"]], row[xyz_pos["y"]], row[xyz_pos["z"]]]
        for name, _ in scalars:
            scalar_arrs[name][i] = row[xyz_pos[name]]
    faces = []
    cs = struct.calcsize(count_dtype)
    isz = struct.calcsize(idx_dtype)
    for _ in range(n_f):
        (cnt,) = struct.unpack_from(count_dtype, data, off); off += cs
        fmt = idx_dtype[0] + idx_dtype[1:] * cnt
        ids = list(struct.unpack_from(fmt, data, off)); off += cnt * isz
        faces.append(list(ids))
    return _build_with_fields(verts.tolist(), faces, scalar_arrs)


def _build(verts, faces):
    if not verts or not faces:
        return None
    verts = np.asarray(verts, dtype=np.float64)
    return {
        "vertices": verts,
        "faces": faces,
        "n_vertices": verts.shape[0],
        "n_faces": len(faces),
    }


def _build_with_fields(verts, faces, scalar_vals):
    out = _build(verts, faces)
    if out is None:
        return None
    fields = {}
    for name, arr in scalar_vals.items():
        a = np.asarray(arr, dtype=np.float64)
        if a.ndim == 1 and a.shape[0] == out["n_vertices"]:
            fields[name] = (a, "node")
    out["fields"] = fields
    return out
