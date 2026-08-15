"""Neutral geometry reader (OBJ / STL) for the Neutral File object (1)."""

from __future__ import annotations

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
