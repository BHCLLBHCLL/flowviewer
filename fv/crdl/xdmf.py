"""XDMF reader (D1) - XML + inline/HDF5 data into the mesh-dict shape."""

from __future__ import annotations

from typing import Optional

import numpy as np
import xml.etree.ElementTree as ET


_VTK_TYPE = {
    "Hexahedron": (12, 8),
    "Tetrahedron": (10, 4),
    "Wedge": (13, 6),
    "Pyramid": (14, 5),
    "Triangle": (5, 3),
    "Quadrilateral": (9, 4),
}

def _read_dataitem(item, base_dir: str):
    """Read a DataItem (inline XML text or HDF5 dataset)."""
    fmt = (item.get("Format") or "XML")
    dims = item.get("Dimensions") or ""
    try:
        shape = tuple(int(x) for x in dims.split())
    except ValueError:
        shape = None
    if fmt.upper() == "HDF":
        text = (item.text or "").strip()
        fname, _, dpath = text.partition(":")
        import os
        if not os.path.isabs(fname):
            fname = os.path.join(base_dir, fname)
        try:
            import h5py
            with h5py.File(fname, "r") as f:
                a = np.asarray(f[dpath][()], dtype=np.float64)
            return a
        except Exception:
            return None
    raw = " ".join((item.text or "").split())
    if not raw:
        return None
    a = np.fromstring(raw, sep=" ", dtype=np.float64)
    if shape is not None and int(np.prod(shape)) == a.size:
        a = a.reshape(shape)
    return a

def parse_xdmf(path: str):
    """Parse an XDMF XML into the mesh-dict shape (D1)."""
    import os
    base_dir = os.path.dirname(path)
    try:
        tree = ET.parse(path)
    except Exception:
        return None
    root = tree.getroot()
    grid = root.find(".//Grid")
    if grid is None:
        return None
    topo = grid.find("Topology")
    geom = grid.find("Geometry")
    if topo is None or geom is None:
        return None
    ttype = topo.get("TopologyType") or "Hexahedron"
    vtk_t, nn = _VTK_TYPE.get(ttype, (12, 8))
    conn_item = topo.find("DataItem")
    geom_item = geom.find("DataItem")
    conn = _read_dataitem(conn_item, base_dir) if conn_item is not None else None
    verts = _read_dataitem(geom_item, base_dir) if geom_item is not None else None
    if conn is None or verts is None:
        return None
    verts = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    conn = np.asarray(conn, dtype=np.int64).reshape(-1, nn)
    n_cells = conn.shape[0]
    fields = {}
    for attr in grid.findall("Attribute"):
        name = attr.get("Name") or "var"
        center = attr.get("Center") or "Node"
        di = attr.find("DataItem")
        if di is None:
            continue
        a = _read_dataitem(di, base_dir)
        if a is None:
            continue
        a = np.asarray(a, dtype=np.float64)
        if a.size == verts.shape[0]:
            fields[name] = (a, "node")
        elif a.size == n_cells:
            fields[name] = (a, "cell")
        else:
            fields[name] = (a, center.lower())
    return {
        "vertices": verts,
        "cell_conn": conn,
        "cell_types": np.full(n_cells, vtk_t, dtype=np.int64),
        "n_vertices": verts.shape[0],
        "n_cells": n_cells,
        "fields": fields,
        "surface_regions": [],
        "volume_regions": ["XDMF"],
    }
