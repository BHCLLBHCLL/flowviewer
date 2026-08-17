"""Topology queries aligned with the scPOST FLD-class accessors (P0.2).

Pure numpy queries over a FieldFile (no VTK): element/node/face adjacency,
region membership and per-element/face geometry.  FPH uses LS_Links; FLD
uses LS_Elements cells with faces derived from the cell types.
"""

from __future__ import annotations

import numpy as np


def _verts(ff):
    return np.asarray(ff.vertices, dtype=np.float64)


def node_count(ff) -> int:
    """Number of vertices (GetNodeCount)."""
    return int(getattr(ff, "n_vertices", 0))


def element_count(ff) -> int:
    """Number of cells (GetElementCount)."""
    return int(getattr(ff, "n_cells", 0))


def node_xyz(ff, node_id):
    """(x, y, z) of a vertex (GetNodeXYZ)."""
    v = _verts(ff)
    i = int(node_id)
    if i < 0 or i >= len(v):
        raise IndexError("node_id out of range")
    return tuple(float(x) for x in v[i])


def node_neighbours(ff, node_id) -> list:
    """Nodes sharing an edge with *node_id* (GetNextNodes).

    Edges are taken from the face polygons (consecutive vertex pairs), so
    the result is exact for FPH links and FLD cells alike.  The
    node→nodes adjacency is built once and cached on the FieldFile.
    """
    adj = getattr(ff, "_node_adj", None)
    if adj is None:
        adj = [set() for _ in range(int(getattr(ff, "n_vertices", 0)))]
        if getattr(ff, "poly", False):
            ld = ff.link_data
            fn = np.asarray(ld["face_nodes"], dtype=np.int64)
            off = np.asarray(ld["face_offsets"], dtype=np.int64)
            for f in range(len(off) - 1):
                lo, hi = int(off[f]), int(off[f + 1])
                ring = fn[lo:hi]
                for k in range(len(ring)):
                    a, b = int(ring[k]), int(ring[k - 1])
                    adj[a].add(b)
                    adj[b].add(a)
        else:
            n = int(getattr(ff, "n_cells", 0))
            faces = getattr(ff, "faces", None)
            if faces:
                # FLD NGON: use the face rings directly (exact edges)
                off = _fld_offset(ff)
                for ring in faces:
                    r = [int(x) - off for x in ring]
                    for k in range(len(r)):
                        a, b = r[k], r[k - 1]
                        adj[a].add(b)
                        adj[b].add(a)
            else:
                for c in range(n):
                    for face in _fld_cell_faces_raw(ff, c):
                        for k in range(len(face)):
                            a, b = face[k], face[k - 1]
                            adj[a].add(b)
                            adj[b].add(a)
        try:
            ff._node_adj = adj  # cache (FieldFile is a plain dataclass)
        except Exception:
            pass
    i = int(node_id)
    if i < 0 or i >= len(adj):
        raise IndexError("node_id out of range")
    return sorted(adj[i])


def _fld_cell_faces_raw(ff, cell_id):
    """Raw vertex groups of one FLD cell for edge extraction."""
    faces = faces_of_cell(ff, cell_id)
    if getattr(ff, "poly", False):
        return [face_nodes(ff, f) for f in faces]
    return [[int(x) for x in f if int(x) >= 0] for f in faces]


def _fph_face_nodes(ff, face_id):
    ld = ff.link_data
    fn = np.asarray(ld["face_nodes"], dtype=np.int64)
    off = np.asarray(ld["face_offsets"], dtype=np.int64)
    lo, hi = int(off[face_id]), int(off[face_id + 1])
    return [int(x) for x in fn[lo:hi]]


def _fld_offset(ff):
    """1 when FLD LS_Elements connectivity is 1-based, else 0."""
    conn = getattr(ff, "cell_conn", None)
    if conn is None:
        return 0
    conn = np.asarray(conn, dtype=np.int64)
    if conn.size == 0:
        return 0
    if conn.min() == 0:
        return 0
    if conn.max() >= getattr(ff, "n_vertices", conn.max() + 1):
        return 1
    return 0


def _fld_face_nodes(ff, face_id):
    """Vertex ids of a FLD NGON face (GetNodesOfFace)."""
    faces = getattr(ff, "faces", None)
    if not faces:
        return []
    f = int(face_id)
    if f < 0 or f >= len(faces):
        raise IndexError("face_id out of range")
    off = _fld_offset(ff)
    return [int(x) - off for x in faces[f]]


def face_nodes(ff, face_id) -> list:
    """Vertex ids of a face (GetNodesOfFace)."""
    if getattr(ff, "poly", False):
        return _fph_face_nodes(ff, int(face_id))
    return _fld_face_nodes(ff, int(face_id))


def _fld_cell_faces(cell, cell_type):
    """Face vertex groups for one FLD cell (VTK ordering)."""
    if cell_type == 12 or cell_type == 0:  # hexahedron
        c = [int(x) for x in cell[:8]]
        return [[c[0], c[3], c[2], c[1]], [c[4], c[5], c[6], c[7]],
                [c[0], c[1], c[5], c[4]], [c[1], c[2], c[6], c[5]],
                [c[2], c[3], c[7], c[6]], [c[3], c[0], c[4], c[7]]]
    if cell_type == 10:  # tetrahedron
        c = [int(x) for x in cell[:4]]
        return [[c[0], c[1], c[2]], [c[0], c[3], c[1]],
                [c[1], c[3], c[2]], [c[2], c[3], c[0]]]
    if cell_type == 13:  # wedge
        c = [int(x) for x in cell[:6]]
        return [[c[0], c[1], c[2]], [c[3], c[4], c[5]],
                [c[0], c[1], c[4], c[3]], [c[1], c[2], c[5], c[4]],
                [c[2], c[0], c[3], c[5]]]
    if cell_type == 14:  # pyramid
        c = [int(x) for x in cell[:5]]
        return [[c[0], c[1], c[2], c[3]], [c[0], c[3], c[4]],
                [c[3], c[2], c[4]], [c[2], c[1], c[4]],
                [c[1], c[0], c[4]]]
    return []


def faces_of_cell(ff, cell_id) -> list:
    """Faces of a cell: FPH face ids, or FLD face vertex groups."""
    if getattr(ff, "poly", False):
        ld = ff.link_data
        return [int(x) for x in ld["cell_owner_faces"].get(int(cell_id), [])]
    conn = getattr(ff, "cell_conn", None)
    if conn is None or int(cell_id) >= len(conn):
        return []
    ctypes = getattr(ff, "cell_types", None)
    t = int(ctypes[int(cell_id)]) if ctypes is not None else 12
    off = _fld_offset(ff)
    groups = _fld_cell_faces(conn[int(cell_id)], t)
    return [[x - off for x in g if x - off >= 0] for g in groups]


def face_count_of_element(ff, cell_id) -> int:
    """Number of faces of a cell (GetFaceCountOfElement)."""
    return len(faces_of_cell(ff, cell_id))


def nodes_of_element(ff, cell_id) -> list:
    """Vertex ids of a cell (GetNodesOfElement)."""
    if getattr(ff, "poly", False):
        ld = ff.link_data
        fn = np.asarray(ld["face_nodes"], dtype=np.int64)
        off = np.asarray(ld["face_offsets"], dtype=np.int64)
        out = set()
        for fi in ld["cell_owner_faces"].get(int(cell_id), []):
            lo, hi = int(off[fi]), int(off[fi + 1])
            out.update(int(x) for x in fn[lo:hi])
        return sorted(out)
    conn = getattr(ff, "cell_conn", None)
    if conn is None or int(cell_id) >= len(conn):
        return []
    off = _fld_offset(ff)
    return [int(x) - off for x in conn[int(cell_id)] if int(x) - off >= 0]


def node_count_of_element(ff, cell_id) -> int:
    """Number of vertices of a cell (GetNodeCountOfElement)."""
    return len(nodes_of_element(ff, cell_id))


def cells_of_face(ff, face_id):
    """(owner, neighbour) cells sharing a face (GetAdjacentElementOfFace).

    FPH reads LS_Links owner/neighbour directly.  FLD NGON faces carry
    only an owning cell (``face_cells``); the neighbour side is unknown,
    so ``(-1, -1)``/``(owner, -1)`` is returned when unavailable.
    """
    if not getattr(ff, "poly", False):
        fc = getattr(ff, "face_cells", None)
        f = int(face_id)
        if fc is not None and 0 <= f < len(fc):
            owner = int(fc[f])
            return (owner, -1) if owner >= 0 else (-1, -1)
        return (-1, -1)  # FLD stores no face table
    ld = ff.link_data
    owner = np.asarray(ld["owner"], dtype=np.int64)
    neigh = np.asarray(ld["neighbour"], dtype=np.int64)
    f = int(face_id)
    if f >= len(owner):
        raise IndexError("face_id out of range")
    return (int(owner[f]), int(neigh[f]))


def _region_cell_mask(ff, region_name):
    """Boolean cell mask for a named volume region."""
    name = region_name or ""
    n = int(getattr(ff, "n_cells", 0))
    if not name or name == "FluidRegion":
        return np.ones(n, dtype=bool)
    if getattr(ff, "poly", False):
        from ..crdl.mesh_gph import classify_volume_region_cells
        mask = classify_volume_region_cells(
            name, ff.parts_with_cvol, ff.cvol_id, n)
        return np.asarray(mask, dtype=bool)
    return np.zeros(n, dtype=bool)


def elements_of_region(ff, region_name) -> list:
    """Cell ids in a volume region (GetElementsOfVolumeRegion)."""
    mask = _region_cell_mask(ff, region_name)
    return [int(i) for i in np.flatnonzero(mask)]


def nodes_of_region(ff, region_name) -> list:
    """Vertex ids used by a volume region (GetNodesOfVolumeRegion)."""
    out = set()
    for c in elements_of_region(ff, region_name):
        out.update(nodes_of_element(ff, c))
    return sorted(out)


def nodes_of_surface_region(ff, region_name) -> list:
    """Vertex ids of a boundary region (GetNodesOfSurfaceRegion)."""
    for name, ids in ff.surface_regions:
        if name != region_name:
            continue
        out = set()
        if getattr(ff, "poly", False):
            for f in ids:
                out.update(_fph_face_nodes(ff, int(f)))
        return sorted(out)
    return []


def _polygon_area(pts):
    """Newell polygon area of a point list."""
    if len(pts) < 3:
        return 0.0
    a = np.zeros(3)
    p = np.asarray(pts, dtype=np.float64)
    for i in range(len(p)):
        a += np.cross(p[i], p[(i + 1) % len(p)])
    return float(0.5 * np.linalg.norm(a))


def area_of_face(ff, face_id) -> float:
    """Area of a face (GetAreaOfFace)."""
    ids = face_nodes(ff, int(face_id))
    if not ids:
        return 0.0
    v = _verts(ff)
    return _polygon_area([v[i] for i in ids])


def volume_of_element(ff, cell_id) -> float:
    """Volume of a cell (GetVolumeOfElement) via face-pyramid sum."""
    v = _verts(ff)
    faces = faces_of_cell(ff, int(cell_id))
    if not faces:
        return 0.0
    groups = []
    if getattr(ff, "poly", False):
        for f in faces:
            groups.append([v[i] for i in _fph_face_nodes(ff, int(f))])
    else:
        for g in faces:
            groups.append([v[i] for i in g if 0 <= i < len(v)])
    pts = [p for g in groups for p in g]
    if not pts:
        return 0.0
    center = np.asarray(pts).mean(axis=0)
    vol = 0.0
    for g in groups:
        if len(g) < 3:
            continue
        p = np.asarray(g)
        for i in range(1, len(p) - 1):
            tri = p[[0, i, i + 1]]
            m = np.stack([tri[1] - tri[0], tri[2] - tri[0], center - tri[0]])
            vol += abs(float(np.linalg.det(m))) / 6.0
    return vol
