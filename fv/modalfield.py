"""R52: turn probe-level modal weights into a full-mesh spatial field.

R47–R51 completed the *probe-level* modal stack — correlation matrix (R47),
POD (R48/R49), DMD (R50) and their HTML report (R51) — but every result never
leaves the sparse monitoring points. R52 closes that gap: given the mesh
vertices plus a single-field R38 trace artifact (probes already bound to
global mesh nodes), it spreads the chosen mode's per-probe weight over the
whole grid with **inverse-distance weighting (IDW)** and exports it as a
per-node field a renderer / field loader can consume. This is the spatial
counterpart of R51's report: the "mode shape / coherent structure" over the
domain, not just at sensors.

Pure NumPy, headless (no CGNS open needed in the core, no VTK). Weights are
sourced from either a POD mode (R48 ``pod_decompose``) or the DMD dominant
mode (R50 ``dmd_decompose``), reusing R51's I/O and naming conventions.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np

from .dmd import dmd_decompose
from .pod import pod_decompose

_EPS = float(np.finfo(np.float64).eps)


# ── inverse-distance weighting onto the mesh ───────────────────────────────


def idw_field(verts: np.ndarray, probes: Sequence[dict],
              weights: Sequence[float], *, p: float = 2.0,
              neighbors: int = 4) -> np.ndarray:
    """Spread per-probe *weights* onto every mesh vertex by IDW.

    ``verts`` is the ``(N, 3)`` mesh vertex array; ``probes`` is
    ``artifact["probes"]`` (each with ``node`` = global mesh index and ``xyz``
    = the bound node coordinate, falling back to ``query`` when ``xyz`` is
    missing). Returns an ``(N,)`` float64 field whose probe nodes carry their
    exact weight (averaged when several probes bind one node) and whose other
    vertices are the inverse-distance-weighted blend of their ``neighbors``
    nearest probe weights; vertices with no usable reference stay ``nan``.

    Distances are computed in vertex **blocks** so peak memory is bounded for
    very large meshes, and a near-zero distance is floored to ``eps`` so a
    coincident vertex is dominated by that probe — no extra special-case.
    """
    vert = np.asarray(verts, dtype=np.float64)
    N = vert.shape[0]
    if N == 0:
        return np.empty((0,), dtype=np.float64)
    if not probes:
        return np.full(N, np.nan, dtype=np.float64)

    # reference points + weights (drop probes with neither xyz nor query)
    P = []
    w = []
    for pr in probes:
        ref = pr.get("xyz") if pr.get("xyz") is not None else pr.get("query")
        if ref is None:
            continue
        P.append([float(v) for v in ref])
        w.append(weights[len(w)])
    if not P:
        return np.full(N, np.nan, dtype=np.float64)
    P_ref = np.asarray(P, dtype=np.float64)
    w = np.asarray(w, dtype=np.float64)
    J = P_ref.shape[0]

    # exact binding at probe nodes (average if shared)
    out = np.full(N, np.nan, dtype=np.float64)
    sums = np.zeros(N, dtype=np.float64)
    cnt = np.zeros(N, dtype=np.int64)
    for pr, wj in zip(probes, w):
        nd = pr.get("node")
        if isinstance(nd, (int, np.integer)) and 0 <= int(nd) < N:
            sums[int(nd)] += float(wj)
            cnt[int(nd)] += 1
    msk = cnt > 0
    out[msk] = sums[msk] / cnt[msk]

    p = float(p) if p and p > 0 else 0.1
    k = max(1, min(neighbors or J, J))

    CH = 1 << 20  # vertices per distance block
    for a in range(0, N, CH):
        m = min(CH, N - a)
        blk = vert[a:a + m]
        # squared distances (J, m)
        diff = P_ref[:, None, :] - blk[None, :, :]
        D2 = (diff * diff).sum(axis=2)
        idx = np.argpartition(D2, k - 1, axis=0)[:k]   # (k, m) row indices
        cols = np.arange(m)[None, :]
        dn = D2[idx, cols]                               # (k, m) squared dists
        d = np.sqrt(dn)
        d[d < _EPS] = _EPS
        inv = 1.0 / d ** p
        wsel = w[idx]                                    # (k, m) neighbour weights
        num = (wsel * inv).sum(axis=0)
        den = inv.sum(axis=0)
        fld = np.divide(num, den, out=np.full_like(num, np.nan),
                        where=den != 0)
        # reachability: only set vertices that are not already exact-bound and
        # whose chosen neighbours include at least one finite reference weight
        reach = np.isfinite(wsel).any(axis=0)
        fld[~reach] = np.nan
        write = np.isnan(out[a:a + m]) & reach & (den != 0)
        out[a:a + m][write] = fld[write]
    return out


# ── per-mode weight source ─────────────────────────────────────────────────


def mode_weights(artifact: dict, *, source: str = "pod", k: int = 0,
                 weight: str = "signed") -> Tuple[np.ndarray, dict]:
    """Extract a chosen mode's per-probe weights from a trace artifact.

    ``source="pod"`` returns POD mode *k* (signed, from ``pod_decompose``);
    ``source="dmd"`` returns the DMD dominant mode's participation (this
    rounds the ``weight`` option: ``"signed"`` = real part of the delay-0
    component, ``"mag"`` = ``mode_mag``). ``weight`` is ignored for POD (its
    mode vectors are inherently signed). Returns ``(weights, meta)`` where
    *weights* is aligned 1:1 to ``artifact["probes"]``.
    """
    if source == "pod":
        pod = pod_decompose(artifact)
        if k >= pod["n_modes"]:
            raise ValueError(
                f"pod mode k={k} out of range (n_modes={pod['n_modes']})")
        w = np.asarray(pod["modes"][k], dtype=np.float64)
        meta = {"source": "pod", "k": int(k),
                "energy_share": pod["energy_shares"][k],
                "n_modes": pod["n_modes"]}
        return w, meta
    if source == "dmd":
        dmd = dmd_decompose(artifact)
        dom = dmd["dominant"]
        if dom is None:
            raise ValueError(
                "dmd: no dominant oscillating mode (n_cycles<4 or static/DC)")
        mode = dmd["modes"][dom["i"]]
        if weight == "mag":
            w = np.asarray(mode["mode_mag"], dtype=np.float64)
        else:
            w = np.asarray([m[0] for m in mode["mode"]], dtype=np.float64)
        meta = {"source": "dmd", "k": int(dom["i"]), "weight": weight,
                "freq": dom["freq"], "growth": dom["growth"],
                "share": dom["share"]}
        return w, meta
    raise ValueError(f"unknown mode source: {source!r}")


# ── assemble the spatial field ─────────────────────────────────────────────


def build_mode_field(verts: np.ndarray, artifact: dict, *, source: str = "pod",
                     k: int = 0, p: float = 2.0, neighbors: int = 4,
                     weight: str = "signed") -> dict:
    """Build the full-mesh node field for a chosen mode + coverage stats."""
    N = int(np.asarray(verts).shape[0])
    if not artifact.get("probes") or not artifact.get("cycles"):
        return {"weights": [], "node_field": np.full(N, np.nan, dtype=np.float64)
                if N else np.empty((0,), dtype=np.float64),
                "meta": {"n_vertices": N, "n_probes": 0, "finite_count": 0,
                         "finite_fraction": 0.0, "min_abs": None,
                         "max_abs": None, "mean_abs": 0.0,
                         "dominant_probe_index": None,
                         "source": source, "k": int(k), "p": p,
                         "neighbors": neighbors}}
    w, meta = mode_weights(artifact, source=source, k=k, weight=weight)
    field = idw_field(verts, artifact["probes"], w, p=p, neighbors=neighbors)
    finite = np.isfinite(field)
    n_fin = int(finite.sum())
    fin = field[finite]
    meta = dict(meta)
    meta.update({
        "n_vertices": N,
        "n_probes": int(len(artifact["probes"])),
        "finite_count": n_fin,
        "finite_fraction": float(n_fin / N) if N else 0.0,
        "min_abs": float(fin.min()) if n_fin else None,
        "max_abs": float(fin.max()) if n_fin else None,
        "mean_abs": float(np.abs(fin).mean()) if n_fin else 0.0,
        "dominant_probe_index": int(np.argmax(np.abs(w))) if len(w) else None,
        "p": p,
        "neighbors": neighbors if neighbors else int(len(artifact["probes"])),
    })
    return {"weights": w.tolist(), "node_field": field.tolist(), "meta": meta}


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name) or "field"


def write_mode_field(verts: np.ndarray, artifact: dict, out_dir: str, *,
                     source: str = "pod", k: int = 0, p: float = 2.0,
                     neighbors: int = 4, weight: str = "signed") -> dict:
    """Write ``<field>_mode<k>.json`` + ``<field>_mode<k>_nodes.csv`` + summary."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = artifact.get("name") or "field"
    safe = _safe(name)
    res = build_mode_field(verts, artifact, source=source, k=k, p=p,
                           neighbors=neighbors, weight=weight)
    with open(out / f"{safe}_mode{k}.json", "w", encoding="utf-8") as fh:
        json.dump({"field": name, "source": source, "k": int(k),
                   "meta": res["meta"], "weights": res["weights"],
                   "node_field": res["node_field"]}, fh)
    vert = np.asarray(verts, dtype=np.float64)
    field = np.asarray(res["node_field"], dtype=np.float64)
    with open(out / f"{safe}_mode{k}_nodes.csv", "w", newline="",
              encoding="utf-8") as fh:
        wcsv = csv.writer(fh)
        wcsv.writerow(["node", "x", "y", "z", "weight"])
        for i in range(len(vert)):
            v = vert[i]
            f = field[i]
            wcell = f"{float(f):.6g}" if np.isfinite(f) else ""
            wcsv.writerow([i, f"{v[0]:.6g}", f"{v[1]:.6g}", f"{v[2]:.6g}",
                           wcell])
    summary = {"field": name, "source": source, "k": int(k),
               "json": f"{safe}_mode{k}.json", "csv": f"{safe}_mode{k}_nodes.csv",
               **res["meta"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def _read_verts(path: str) -> np.ndarray:
    """Load an ``(N, 3)`` vertex array from a ``.npy`` or ``.json`` file."""
    p = Path(path)
    if p.suffix.lower() == ".npy":
        arr = np.load(path, allow_pickle=False)
    else:
        with open(path, "r", encoding="utf-8") as fh:
            arr = np.asarray(json.load(fh), dtype=np.float64)
    return arr


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.modalfield",
        description="FlowViewer R52 inverse-distance-weighted modal spatial map")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("verts", help=".npy or .json (N,3) vertex array")
    ap.add_argument("--source", default="pod", choices=["pod", "dmd"])
    ap.add_argument("--k", type=int, default=0)
    ap.add_argument("--p", type=float, default=2.0)
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--weight", default="signed", choices=["signed", "mag"])
    ap.add_argument("--out", default="modalfield_out")
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    if "probes" not in art:
        print("error: trace_json must contain 'probes'", file=sys.stderr)
        return 2
    try:
        verts = _read_verts(args.verts)
    except (ValueError, FileNotFoundError, OSError) as e:
        print(f"error: bad verts: {e}", file=sys.stderr)
        return 2
    if verts.ndim != 2 or verts.shape[1] != 3 or verts.shape[0] == 0:
        print("error: verts must be an (N,3) array with N>0", file=sys.stderr)
        return 2
    try:
        summary = write_mode_field(verts, art, args.out, source=args.source,
                                   k=args.k, p=args.p, neighbors=args.neighbors,
                                   weight=args.weight)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
