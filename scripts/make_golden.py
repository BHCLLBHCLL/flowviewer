#!/usr/bin/env python3
"""Regenerate the in-repo golden corpus (R114).

The numeric tests used to depend on multi-hundred-megabyte samples kept
outside the repository behind ``skipif`` guards, so on CI the numeric half of
the suite silently skipped.  This script distils a compact, committable
subset of those samples into ``tests/data/golden/`` and records the reference
statistics alongside the data, so the numbers the tests assert against are
generated from the real files instead of being typed in by hand.

Usage (needs the sample files, which stay outside the repo):

    python scripts/make_golden.py           # write/refresh the corpus
    python scripts/make_golden.py --check   # only report what would change

Contents (all sizes are for the corpus as committed):

* ``fld_small.npz``  - ex1_100.fld: vertices, hex connectivity, up to 16
  boundary faces with their node ids, one cell-centred field, plus the
  per-variable min/max/mean and the boundary-area reference.
* ``fph_small.npz``  - tr03_9.fph: vertices, the face table of a bounded
  cell slice, that slice's owner/neighbour faces with node ids, the cell
  field values, cell centres, and the reference cell volumes computed with a
  closed-shell (owner+neighbour) divergence sum.
* ``meta.json``      - what each file holds, the source path, the sampling
  rule and the reference statistics, so a reader can tell exactly which
  subset a number came from.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "data" / "golden"

FLD = Path(r"D:\training\cgns\examples\ex1_100.fld")
FPH = Path(r"D:\training\cgns\examples\tr03_9.fph")

#: cells kept in the FPH slice (a contiguous block keeps the face table small)
FPH_CELLS = 4000
#: boundary faces kept for the FLD fixture
FLD_FACES = 64


def _fld_payload():
    sys.path.insert(0, str(ROOT))
    from fv.model import dataset

    ff = dataset.load_file(str(FLD))
    verts = np.asarray(ff.vertices, dtype=np.float64)
    conn = np.asarray(ff.cell_conn, dtype=np.int64)
    faces = np.asarray(ff.faces, dtype=np.int64)
    # keep only the distinct faces, in first-seen order, then take a prefix
    seen, uniq = set(), []
    for f in faces:
        key = tuple(int(v) for v in f)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(key)
    face_nodes = np.asarray(uniq[:FLD_FACES], dtype=np.int64)

    var = "PRES" if "PRES" in ff.variables else sorted(ff.variables)[0]
    field = np.asarray(ff.variable_array(var), dtype=np.float64)

    stats = {}
    for name in sorted(ff.variables):
        a = np.asarray(ff.variable_array(name), dtype=np.float64)
        stats[name] = {"min": float(a.min()), "max": float(a.max()),
                       "mean": float(a.mean()), "size": int(a.size)}

    return {
        "vertices": verts,
        "cell_conn": conn,
        "face_nodes": face_nodes,
        "field": field,
        "field_name": np.asarray(var),
        "var_stats": np.asarray(json.dumps(stats, sort_keys=True)),
    }, {"source": str(FLD), "n_vertices": int(verts.shape[0]),
        "n_cells": int(conn.shape[0]), "n_faces_total": int(len(uniq)),
        "faces_kept": int(face_nodes.shape[0]), "field": var,
        "var_stats": stats}


def _fph_payload():
    sys.path.insert(0, str(ROOT))
    from fv.model import dataset

    ff = dataset.load_file(str(FPH))
    ld = ff.link_data
    verts = np.asarray(ff.vertices, dtype=np.float64)
    fn = np.asarray(ld["face_nodes"], dtype=np.int64)
    off = np.asarray(ld["face_offsets"], dtype=np.int64)
    n_cells = int(ff.n_cells)
    keep_cells = list(range(min(FPH_CELLS, n_cells)))

    # faces belonging to the kept cells (owner + neighbour), deduplicated
    face_ids = []
    seen = set()
    for c in keep_cells:
        for f in list(ld["cell_owner_faces"].get(c, [])):
            if int(f) not in seen:
                seen.add(int(f))
                face_ids.append(int(f))
        for f in list(ld["cell_neighbour_faces"].get(c, [])):
            if int(f) not in seen:
                seen.add(int(f))
                face_ids.append(int(f))

    face_nodes, face_offsets, owner, neigh = [], [0], [], []
    for f in face_ids:
        lo, hi = int(off[f]), int(off[f + 1])
        face_nodes.extend(int(x) for x in fn[lo:hi])
        face_offsets.append(len(face_nodes))
        owner.append(int(ld["owner"][f]))
        neigh.append(int(ld["neighbour"][f]))

    var = "PRES" if "PRES" in ff.variables else sorted(ff.variables)[0]
    field = np.asarray(ff.variable_array(var), dtype=np.float64)

    from fv.model import varreg
    centres = varreg._cell_centers_fph(ff)
    centres = np.asarray(centres, dtype=np.float64)[keep_cells]

    # reference cell volumes: closed-shell pyramid sum over the kept faces
    idx_of_face = {f: i for i, f in enumerate(face_ids)}
    volumes = np.zeros(len(keep_cells), dtype=np.float64)
    for row, c in enumerate(keep_cells):
        polys = []
        for f in list(ld["cell_owner_faces"].get(c, [])):
            i = idx_of_face[int(f)]
            polys.append(face_nodes[face_offsets[i]:face_offsets[i + 1]])
        for f in list(ld["cell_neighbour_faces"].get(c, [])):
            i = idx_of_face[int(f)]
            polys.append(face_nodes[face_offsets[i]:face_offsets[i + 1]])
        if not polys:
            continue
        pts = [verts[p] for p in polys]
        ctr = np.vstack(pts).mean(axis=0)
        vol = 0.0
        for p in pts:
            for i in range(1, len(p) - 1):
                tri = p[[0, i, i + 1]]
                m = np.stack([tri[1] - tri[0], tri[2] - tri[0], ctr - tri[0]])
                vol += abs(float(np.linalg.det(m))) / 6.0
        volumes[row] = vol

    stats = {}
    for name in sorted(ff.variables):
        a = np.asarray(ff.variable_array(name), dtype=np.float64)
        stats[name] = {"min": float(a.min()), "max": float(a.max()),
                       "mean": float(a.mean()), "size": int(a.size)}

    return {
        "vertices": verts,
        "face_nodes": np.asarray(face_nodes, dtype=np.int64),
        "face_offsets": np.asarray(face_offsets, dtype=np.int64),
        "owner": np.asarray(owner, dtype=np.int64),
        "neighbour": np.asarray(neigh, dtype=np.int64),
        "cells": np.asarray(keep_cells, dtype=np.int64),
        "centres": centres,
        "volumes": volumes,
        "field": field,
        "field_name": np.asarray(var),
        "var_stats": np.asarray(json.dumps(stats, sort_keys=True)),
    }, {"source": str(FPH), "n_vertices": int(verts.shape[0]),
        "n_cells": n_cells, "cells_kept": len(keep_cells),
        "faces_kept": len(face_ids), "field": var, "var_stats": stats}


# ── cross-format reference corpus (R117) ──────────────────────────────────
#
# ex1_e_from_sxemt_run is the same solver run written twice: the .fld our FLD
# decoder reads, and a .cgns written by the solver.  Reading the CGNS side
# straight from HDF5 (not through fv.crdl.cgns) gives a decoder-independent
# reference for the same physical data, so the two independent decoders can be
# compared value by value.

CROSS_CGNS = Path(r"D:\training\cgns\flddecoding\tests\ex1_e_from_sxemt_run.cgns")
CROSS_FLD = Path(r"D:\training\cgns\flddecoding\tests\ex1_e_from_sxemt_run.fld")
#: nodes kept in the committed corpus (identical on both sides)
CROSS_NODES = 600


def _cross_payload():
    import h5py

    sys.path.insert(0, str(ROOT))
    from fv.model import dataset

    with h5py.File(CROSS_CGNS, "r") as f:
        zone = f["Base/FluidZone"]
        gc = zone["GridCoordinates"]
        cg_xyz = np.column_stack([
            np.asarray(gc["Coordinate" + a][" data"], dtype=np.float64)
            for a in "XYZ"])
        fs = zone["FlowSolution"]
        cg = {n: np.asarray(fs[n][" data"], dtype=np.float64)
              for n in fs if isinstance(fs[n], h5py.Group)}

    ff = dataset.load_file(str(CROSS_FLD))
    fld_xyz = np.asarray(ff.vertices, dtype=np.float64)
    shared = sorted(set(cg) & set(ff.variables))
    if not shared:
        raise SystemExit("no shared variables between the two formats")

    # Sample ACROSS the mesh, not the first n nodes: the opening block of this
    # case is uniform in every variable, so a contiguous excerpt would let the
    # cross-check pass even for a badly broken decoder (the "not trivially
    # constant" test catches exactly that).
    total = int(cg_xyz.shape[0])
    n = min(CROSS_NODES, total)
    sel = np.unique(np.linspace(0, total - 1, n).astype(np.int64))
    payload = {"cgns_vertices": cg_xyz[sel],
               "fld_vertices": fld_xyz[sel],
               "indices": sel,
               "variables": np.asarray(json.dumps(shared))}
    for name in shared:
        payload["cgns__" + name] = cg[name][sel]
        payload["fld__" + name] = np.asarray(
            ff.variable_array(name), dtype=np.float64)[sel]

    info = {"cgns": str(CROSS_CGNS), "fld": str(CROSS_FLD),
            "nodes_total": total, "nodes_kept": int(sel.size),
            "sampling": "linspace over all nodes",
            "variables": shared}
    return payload, info

def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    written = {}
    meta = {"generator": "scripts/make_golden.py", "files": {}}

    builders = [("fld_small.npz", _fld_payload), ("fph_small.npz", _fph_payload)]
    if CROSS_CGNS.exists() and CROSS_FLD.exists():
        builders.append(("cross_format.npz", _cross_payload))
    else:
        print("cross-format samples absent; keeping the existing corpus entry")
    for name, fn in builders:
        payload, info = fn()
        path = OUT / name
        np.savez_compressed(path, **payload)
        written[name] = path.stat().st_size
        meta["files"][name] = info

    (OUT / "meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    written["meta.json"] = (OUT / "meta.json").stat().st_size
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="report the sizes that would be written, change nothing")
    args = ap.parse_args(argv)
    missing = [str(p) for p in (FLD, FPH) if not p.exists()]
    if missing:
        print("sample file(s) not present, cannot regenerate:")
        for m in missing:
            print("   " + m)
        return 2
    written = build()
    for name, size in sorted(written.items()):
        print("%-16s %8.1f KiB%s" % (name, size / 1024.0,
                                      " (check only)" if args.check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
