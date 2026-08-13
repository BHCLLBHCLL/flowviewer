"""CGNS-HDF5 reader (P1.2).

Reads the standard CGNS SIDS tree stored in HDF5 (h5py) into the
same dict shape the mesh parsers produce: vertices, cell connectivity,
node/cell fields, volume region names and boundary condition faces.
Supports unstructured zones with a single element type per Elements
section (HEXA_8 / TETRA_4 / PENTA_6 / PYRA_5 / MIXED best-effort) and
element-type-coded connectivity via 'cell_types'.
"""

from __future__ import annotations

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
    """Read the 'data' dataset of a CGNS node (name may be ' data')."""
    if group is None:
        return None
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
    return _attr_text(zt, "data") or "Unstructured"


def _read_coordinates(zone) -> Optional[np.ndarray]:
    gc = zone.get("GridCoordinates")
    if gc is None:
        return None
    comps = [];
    for axis in ("CoordinateX", "CoordinateY", "CoordinateZ"):
        c = gc.get(axis);
        arr = _data_of(c) if c is not None else None
        if arr is None:
            return None
        comps.append(np.asarray(arr, dtype=np.float64))
    if len(comps) != 3 or any(a.size == 0 for a in comps):
        return None
    return np.column_stack(comps)


def _elements_sections(zone) -> list:
    """Every Elements_t section (volume or boundary) in the zone."""
    out = [];
    for name, obj in _children(zone):
        if not isinstance(obj, h5py.Group):
            continue
        if "ElementConnectivity" in obj and "ElementRange" in obj:
            out.append((name, obj));
    return out


def _read_cells(zone):
    """Read volume cells -> (cell_conn, cell_types) or (None, None)."""
    cell_conn = [];
    cell_types = [];
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
        n_elems = int(rng[1] - rng[0] + 1)
        if et in _VOLUME_TYPES:
            vtk_t, nn = _VTK_FOR_CGNS[et]
            n_elems = conn.size // nn
            arr = np.asarray(conn, dtype=np.int64).reshape(n_elems, nn) - 1
            cell_conn.append(arr);
            cell_types.extend([vtk_t] * n_elems);
        elif et == "MIXED":
            # Each element: [type_code, nodes...]
            raise ValueError("MIXED elements not yet supported")
        else:
            # Boundary-only section (TRI_3 / QUAD_4 etc.) - skip
            continue
    if not cell_conn:
        return None, None
    return np.vstack(cell_conn), np.asarray(cell_types, dtype=np.int64)


def _read_flow_solution(zone, n_nodes: int):
    """FlowSolution fields -> dict name -> (array, location)."""
    out = {};
    fs = zone.get("FlowSolution");
    if fs is None:
        return out
    for name, obj in _children(fs):
        if isinstance(obj, h5py.Group):
            raw = _data_of(obj)
            if raw is None:
                continue
            try:
                arr = np.asarray(raw, dtype=np.float64)
            except Exception:
                continue
            if arr.ndim != 1 or arr.size == 0:
                continue
            loc = "node" if arr.size == n_nodes else "cell"
            out[name] = (arr, loc);
    return out


def _read_bcs(zone, n_faces: int):
    """ZoneBC boundary conditions -> [(name, face_ids 0-based)]."""
    out = [];
    zbc = zone.get("ZoneBC");
    if zbc is None:
        return out
    for name, obj in _children(zbc):
        if not isinstance(obj, h5py.Group):
            continue
        pl = obj.get("PointList");
        raw = _data_of(pl) if pl is not None else None
        if raw is None:
            continue
        try:
            ids = np.asarray(raw, dtype=np.int64).ravel() - 1
        except Exception:
            continue
        out.append((name, ids));
    return out


def read_cgns(path: str) -> Optional[dict]:
    """Read a CGNS-HDF5 file into the mesh-dict shape (P1.2).

    Returns a dict with keys: vertices, cell_conn, cell_types,
    n_vertices, n_cells, fields (name -> (array, location)),
    surface_regions, volume_regions, bcs, zone_name, base_name.
    Returns None when the file is not a readable CGNS-HDF5.
    """
    if not _HAS_H5:
        return None
    with h5py.File(path, "r") as f:
        # find the first CGNSBase_t group (top-level, excluding format)
        bases = [k for k in f.keys() if isinstance(f[k], h5py.Group)
                 and k.strip() not in ("format", "hdf5version")]
        if not bases:
            return None
        base = f[bases[0]];
        zones = [k for k in base.keys() if isinstance(base[k], h5py.Group)
                 and "ZoneType" in base[k]]
        if not zones:
            return None
        zone = base[zones[0]];
        vertices = _read_coordinates(zone);
        if vertices is None:
            return None
        cell_conn, cell_types = _read_cells(zone);
        n_vertices = int(vertices.shape[0]);
        n_cells = int(cell_conn.shape[0]) if cell_conn is not None else 0;
        fields = _read_flow_solution(zone, n_vertices);
        # boundary faces: count TRI/QUAD elements for BC indexing
        bc_sections = [s for n, s in _elements_sections(zone)
                       if _elem_type_name(s) in ("TRI_3", "QUAD_4")];
        n_faces = 0
        for s in bc_sections:
            r = _data_of(s["ElementRange"])
            if r is not None:
                n_faces += int(r[1]) - int(r[0]) + 1
        bcs = _read_bcs(zone, n_faces);
        surface_regions = [(n, ids) for n, ids in bcs];
        return {
            "vertices": vertices,
            "cell_conn": cell_conn,
            "cell_types": cell_types,
            "n_vertices": n_vertices,
            "n_cells": n_cells,
            "fields": fields,
            "surface_regions": surface_regions,
            "volume_regions": [zones[0]],
            "zone_name": zones[0],
            "base_name": bases[0],
        }


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