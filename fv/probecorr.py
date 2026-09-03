"""R47: cross-probe correlation matrix + probe clustering (coherent structure).

R42 related a *pair* of monitoring points (lagged cross-correlation, coherence);
R47 generalises to **all probes at once** — the correlation matrix of a probe
set — and answers "which monitoring points oscillate together". Two consumers:

* ``pairwise_correlation`` — NaN-safe Pearson correlation between every probe
  pair, so one gets the full ``n_probes × n_probes`` matrix (with gap handling:
  each pair only uses their common finite samples).
* ``cluster_probes`` — single-linkage clustering on ``|rho| ≥ threshold``,
  grouping probes that co-oscillate; ``top_pairs`` lists the strongest links.

Input is an R38 trace artifact (``{name, cycles, probes:[{values, …}]}``) —
pure NumPy, headless, no CGNS/vtk dependencies.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import List

import numpy as np

DEFAULT_THRESHOLD = 0.8
DEFAULT_TOP = 5


# ── matrix construction ────────────────────────────────────────────────────


def history_matrix(artifact: dict):
    """(n_cycles, n_probes) float matrix of the probe histories.

    NaN-padded so probes with fewer samples still line up on the cycle axis.
    """
    probes = list(artifact.get("probes", []))
    cycles = list(artifact.get("cycles", []))
    n = len(probes)
    if not n:
        return np.zeros((0, 0), dtype=np.float64), cycles
    length = max(len(p.get("values", [])) for p in probes)
    M = np.full((length, n), np.nan, dtype=np.float64)
    for j, p in enumerate(probes):
        for t, v in enumerate(p.get("values", [])):
            try:
                M[t, j] = float(v)
            except (TypeError, ValueError):
                M[t, j] = np.nan
    return M, cycles


# ── correlation ────────────────────────────────────────────────────────────


def pairwise_correlation(matrix) -> np.ndarray:
    """NaN-safe Pearson correlation matrix of probe histories.

    Each pair correlates only over rows where *both* probes are finite; pairs
    with fewer than 2 common samples yield NaN. Diagonal is 1.0.
    """
    M = np.asarray(matrix, dtype=np.float64)
    n = M.shape[1]
    corr = np.full((n, n), np.nan, dtype=np.float64)
    for i in range(n):
        corr[i, i] = 1.0
        for j in range(i + 1, n):
            a = M[:, i]
            b = M[:, j]
            m = np.isfinite(a) & np.isfinite(b)
            if int(m.sum()) < 2:
                continue
            av = a[m] - a[m].mean()
            bv = b[m] - b[m].mean()
            den = float(np.sqrt((av * av).sum() * (bv * bv).sum()))
            corr[i, j] = corr[j, i] = float((av * bv).sum() / den) \
                if den > 0 else 0.0
    return corr


# ── structure ──────────────────────────────────────────────────────────────


def top_pairs(corr, k: int = DEFAULT_TOP) -> List[dict]:
    """Strongest ``k`` distinct probe pairs, by |rho| desc."""
    n = corr.shape[0]
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            v = corr[i, j]
            if not np.isnan(v):
                pairs.append({"i": int(i), "j": int(j), "rho": float(v)})
    pairs.sort(key=lambda p: abs(p["rho"]), reverse=True)
    return pairs[:k]


def cluster_probes(corr, threshold: float = DEFAULT_THRESHOLD) -> List[List[int]]:
    """Single-linkage clustering of probes linked by ``|rho| ≥ threshold``.

    Returns clusters (lists of probe indices) sorted by size descending —
    including size-1 clusters, so callers can drop ``len==1`` for the
    "coherent groups" view.
    """
    n = corr.shape[0]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if np.isnan(corr[i, j]):
                continue
            if abs(corr[i, j]) >= threshold:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    groups: dict = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    clusters = [sorted(v) for v in groups.values()]
    clusters.sort(key=len, reverse=True)
    return clusters


# ── artifact runner ────────────────────────────────────────────────────────


def probe_corr_summary(artifact: dict, *, threshold: float = DEFAULT_THRESHOLD,
                       top: int = DEFAULT_TOP) -> dict:
    """Full cross-probe analysis of an R38 trace artifact."""
    M, _cycles = history_matrix(artifact)
    corr = pairwise_correlation(M)
    _nan = None
    matrix = [[(_nan if np.isnan(v) else float(v)) for v in row] for row in corr]
    clusters = cluster_probes(corr, threshold)
    return {
        "field": artifact.get("name") or "",
        "n_probes": int(corr.shape[0]),
        "threshold": float(threshold),
        "matrix": matrix,
        "top_pairs": top_pairs(corr, top),
        "clusters": [{"size": len(c), "members": c} for c in clusters],
        "n_clusters": len(clusters),
        "coherent_groups": [{"size": len(c), "members": c}
                            for c in clusters if len(c) > 1],
    }


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_probecorr(summary: dict, out_dir: str) -> dict:
    """Write matrix JSON, clusters JSON, pairs CSV, and summary.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    field = summary.get("field") or "field"
    safe = "".join(ch if ch.isalnum() else "_" for ch in field) or "field"

    with open(out / f"{safe}_probecorr.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    with open(out / f"{safe}_clusters.json", "w", encoding="utf-8") as fh:
        json.dump({"field": field, "threshold": summary["threshold"],
                   "clusters": summary["clusters"],
                   "coherent_groups": summary["coherent_groups"]},
                  fh, indent=2)
    with open(out / f"{safe}_pairs.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["i", "j", "rho"])
        for p in summary["top_pairs"]:
            w.writerow([p["i"], p["j"], f"{p['rho']:.6g}"])
    top_summary = {"field": field, "file": f"{safe}_probecorr.json",
                   "clusters_file": f"{safe}_clusters.json",
                   "pairs_csv": f"{safe}_pairs.csv",
                   "n_probes": summary["n_probes"],
                   "n_clusters": summary["n_clusters"],
                   "coherent_groups": summary["coherent_groups"],
                   "top_pairs": summary["top_pairs"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(top_summary, fh, indent=2)
    return top_summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.probecorr",
        description="FlowViewer R47 cross-probe correlation + clustering")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("--out", default="probecorr_out")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                    help="|rho| linkage threshold for clustering (default 0.8)")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP,
                    help="how many strongest pairs to list (default 5)")
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    if "probes" not in art:
        print("error: trace_json must contain 'probes'",
              file=__import__("sys").stderr)
        return 2
    summary = probe_corr_summary(art, threshold=args.threshold, top=args.top)
    if not summary["field"]:
        summary["field"] = Path(args.trace_json).stem
    top_summary = write_probecorr(summary, args.out)
    print(json.dumps(top_summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
