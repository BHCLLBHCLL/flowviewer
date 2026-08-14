"""Nastran (.nas/.bdf) text mesh reader (D2).

Parses free-field GRID / CHEXA / CTETRA / CPENTA / CPYRAM cards into
the mesh-dict shape.  Results (.op2/.f06) are out of scope.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

_VTK = {"CHEXA": (12, 8), "CTETRA": (10, 4), "CPENTA": (13, 6),
        "CPYRAM": (14, 5)}


def parse_nastran(path: str):
    """Parse free-field Nastran mesh -> mesh-dict (D2)."""
    nodes = {}
    cells = []
    cell_types = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.split("$", 1)[0].strip().upper()
            if not s or s.startswith(("ENDDATA", "SOL ")):
                continue
            parts = [p.strip() for p in s.split(",")]
            card = parts[0]
            if card == "GRID" and len(parts) >= 5:
                try:
                    gid = int(parts[1])
                    xyz = [float(parts[i]) for i in (3, 4, 5)]
                    nodes[gid] = xyz
                except (ValueError, IndexError):
                    continue
            elif card in _VTK and len(parts) >= 3:
                try:
                    vtk_t, nn = _VTK[card]
                    gids = [int(parts[i]) for i in range(3, 3 + nn)]
                    cells.append(gids)
                    cell_types.append(vtk_t)
                except (ValueError, IndexError):
                    continue
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
        "fields": {},
        "surface_regions": [],
        "volume_regions": ["Nastran"],
    }
