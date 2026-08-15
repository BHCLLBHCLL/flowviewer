"""Marc / Mentat .dat text mesh reader (3).

Parses comma-separated node (id,x,y,z) and element (id,type,n1..nk) cards.
Element node counts map to VTK types (8=hex, 4=tet, 6=wedge, 5=pyramid).
Binary .t16/.t19 results are out of scope.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
_NODE_COUNT_TO_VTK = {8: (12, 8), 4: (10, 4), 6: (13, 6), 5: (14, 5)}


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
    order = {}
    for gids in cells:
        for g in gids:
            if g not in order:
                order[g] = len(order)
    n_vertices = len(order)
    verts = np.zeros((n_vertices, 3))
    for g, i in order.items():
        verts[i] = nodes[g]
    conn = np.zeros((len(cells), 8), dtype=np.int64) - 1
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
    }


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