"""R53: reconstruct the full mesh node field at a chosen cycle from POD modes.

R49 ``podfilter.pod_reconstruct`` rebuilds only the *sparse probe* histories;
R52 ``modalfield`` spreads a single mode's shape onto the whole mesh but never
forms a usable physical field. R53 fuses the two: it reconstructs the **entire
node field at any cycle** from the dominant POD modes by lifting each mode's
per-probe weight onto the domain (R52 ``idw_field``) and re-composing

    recon_field(node, cycle) = mean_field(node) + Σⱼₖ shapeⱼ(node)·coeffⱼ(cycle),

so the low-rank, noise-filtered spatial snapshot of a physical field can be
written out for a renderer / field loader. On the probe nodes the IDW ties are
exact, so the reconstruction there *is* R49's, and with all modes kept it
reproduces the measured probe values to numerical precision — giving an exact,
headless-verifiable quality measure.

Pure NumPy, headless, no CGNS, no VTK. Reuses R48 ``pod_decompose`` and R52
``idw_field``. Only POD reconstruction is supported here (exact, verifiable);
full-field DMD reconstruction needs complex-envelope approximation and is left
out of scope.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from .modalfield import idw_field
from .pod import pod_decompose


def _finite(v) -> bool:
    try:
        return bool(np.isfinite(float(v)))
    except (TypeError, ValueError):
        return False


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name) or "field"


def _probe_means(probes: list) -> np.ndarray:
    """Per-probe temporal mean over each probe's finite values (all-NaN -> 0)."""
    means = []
    for pr in probes:
        vals = [float(v) for v in pr.get("values", []) if _finite(v)]
        means.append(float(np.mean(vals)) if vals else 0.0)
    return np.asarray(means, dtype=np.float64)


# ── temporal-mean field ─────────────────────────────────────────────────────


def mean_field(verts: np.ndarray, probes: list, *, p: float = 2.0,
               neighbors: int = 4) -> np.ndarray:
    """Full-mesh node field of each probe's temporal mean (IDW spread)."""
    means = _probe_means(probes)
    return idw_field(verts, probes, means, p=p, neighbors=neighbors)


# ── field reconstruction ────────────────────────────────────────────────────


def reconstruct_field(verts: np.ndarray, artifact: dict, *, cycle: int = 0,
                      k: Optional[int] = None, p: float = 2.0,
                      neighbors: int = 4) -> dict:
    """Reconstruct the full mesh node field at cycle index *cycle*.

    Returns a dict with ``mean_field``, per-mode ``mode_fields`` and the
    assembled ``recon_field``, plus bookkeeping (``k``, ``captured_var``,
    coverage). Empty artifact -> graceful empty recon (all-NaN). ``cycle`` /
    ``k`` out of range -> ``ValueError``.
    """
    vert = np.asarray(verts, dtype=np.float64)
    N = vert.shape[0]
    if not artifact.get("probes") or not artifact.get("cycles"):
        return {"cycle": int(cycle), "n_cycles": 0, "n_probes": 0, "k": 0,
                "mean_field": np.full(N, np.nan, dtype=np.float64)
                if N else np.empty((0,), dtype=np.float64),
                "mode_fields": [], "recon_field": np.full(N, np.nan,
                dtype=np.float64) if N else np.empty((0,), dtype=np.float64),
                "finite_fraction": 0.0, "captured_var": 0.0,
                "coverage": 0}
    pod = pod_decompose(artifact)
    n_cycles = int(pod["n_cycles"])
    if not (0 <= int(cycle) < n_cycles):
        raise ValueError(
            f"cycle={cycle} out of range (n_cycles={n_cycles})")
    kk = int(k) if k is not None else int(pod["n_modes"])
    kk = max(0, min(kk, int(pod["n_modes"])))

    probe_means = _probe_means(artifact["probes"])
    mean_f = idw_field(vert, artifact["probes"], probe_means, p=p,
                       neighbors=neighbors)
    recon = mean_f.copy()
    mode_fields = []
    for i in range(kk):
        shape = idw_field(vert, artifact["probes"],
                          pod["modes"][i], p=p, neighbors=neighbors)
        mode_fields.append(shape)
        recon += shape * pod["coeffs"][i][int(cycle)]
    finite = np.isfinite(recon) & np.isfinite(mean_f)
    recon[~finite] = np.nan
    captured = float(pod["cum_energy"][kk - 1]) if kk > 0 else 0.0
    return {"cycle": int(cycle), "n_cycles": n_cycles,
            "n_probes": int(pod["n_probes"]), "k": kk,
            "mean_field": mean_f,
            "mode_fields": mode_fields,
            "recon_field": recon,
            "finite_fraction": float(finite.sum() / N) if N else 0.0,
            "captured_var": captured,
            "coverage": int(finite.sum())}


# ── reconstruction quality (verified at the probe nodes) ────────────────────


def recon_quality(artifact: dict, *, k: Optional[int] = None) -> dict:
    """Reconstruction error of the full-field reconstruction at probe nodes.

    Since the mesh has no ground truth away from the sensors, quality is
    measured where the IDW ties are exact — the probe nodes, where
    ``recon(node, cycle) = probe_mean + Σ mode·coeff`` (the R49 value with mean
    restored). Returns per-probe / per-cycle / total RMSE and ``captured_var``;
    ``total_rmse ≈ 0`` when all modes are kept.
    """
    probes = list(artifact.get("probes", []))
    pod = pod_decompose(artifact)
    n_probes = int(pod["n_probes"])
    n_cycles = int(pod["n_cycles"])
    empty = {"k": 0, "captured_var": 0.0, "per_probe_rmse": [],
             "per_cycle_rmse": [], "total_rmse": float("nan"),
             "n_probes": n_probes, "n_cycles": n_cycles}
    if pod["n_modes"] == 0 or n_probes == 0 or n_cycles == 0:
        return empty
    kk = int(k) if k is not None else int(pod["n_modes"])
    kk = max(0, min(kk, int(pod["n_modes"])))

    probe_means = _probe_means(probes)
    actual = np.full((n_probes, n_cycles), np.nan, dtype=np.float64)
    M = pod["modes"]
    C = pod["coeffs"]
    recon = np.zeros((n_probes, n_cycles), dtype=np.float64)
    for j, pr in enumerate(probes):
        for c, v in enumerate(pr.get("values", [])):
            if c < n_cycles and _finite(v):
                actual[j, c] = float(v)
        for i in range(kk):
            recon[j] += M[i][j] * np.asarray(C[i], dtype=np.float64)
        recon[j] += probe_means[j]

    diff = actual - recon
    per_probe = [float(np.sqrt(np.nanmean(diff[j] ** 2)))
                 if np.isfinite(actual[j]).any() else float("nan")
                 for j in range(n_probes)]
    per_cycle = [float(np.sqrt(np.nanmean(diff[:, c] ** 2)))
                 if np.isfinite(actual[:, c]).any() else float("nan")
                 for c in range(n_cycles)]
    captured = float(pod["cum_energy"][kk - 1]) if kk > 0 else 0.0
    return {"k": kk, "captured_var": captured,
            "per_probe_rmse": per_probe, "per_cycle_rmse": per_cycle,
            "total_rmse": float(np.sqrt(np.nanmean(diff ** 2))),
            "n_probes": n_probes, "n_cycles": n_cycles}


# ── I/O / CLI ───────────────────────────────────────────────────────────────


def write_reconfield(verts: np.ndarray, artifact: dict, out_dir: str, *,
                     cycle: int = 0, k: Optional[int] = None, p: float = 2.0,
                     neighbors: int = 4, field: str = "") -> dict:
    """Write recon field snapshots, node CSV, quality JSON and summary."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = field or artifact.get("name") or "field"
    safe = _safe(name)
    res = reconstruct_field(verts, artifact, cycle=cycle, k=k, p=p,
                            neighbors=neighbors)
    qual = recon_quality(artifact, k=k)
    payload = {"field": name, "cycle": res["cycle"], "k": res["k"],
               "n_probes": res["n_probes"], "n_cycles": res["n_cycles"],
               "captured_var": res["captured_var"],
               "finite_fraction": res["finite_fraction"],
               "mean_field": [None if v != v else float(v)
                              for v in res["mean_field"]],
               "mode_fields": [[None if v != v else float(v) for v in mf]
                               for mf in res["mode_fields"]],
               "recon_field": [None if v != v else float(v)
                               for v in res["recon_field"]]}
    with open(out / f"{safe}_recon_cycle{cycle}.json", "w",
              encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    vert = np.asarray(verts, dtype=np.float64)
    recon = res["recon_field"]
    with open(out / f"{safe}_recon_nodes.csv", "w", newline="",
              encoding="utf-8") as fh:
        wcsv = csv.writer(fh)
        wcsv.writerow(["node", "x", "y", "z", "recon"])
        for i in range(len(vert)):
            rc = f"{float(recon[i]):.6g}" if np.isfinite(recon[i]) else ""
            wcsv.writerow([i, f"{vert[i][0]:.6g}", f"{vert[i][1]:.6g}",
                           f"{vert[i][2]:.6g}", rc])
    with open(out / f"{safe}_recon_quality.json", "w", encoding="utf-8") as fh:
        json.dump(qual, fh, indent=2)
    summary = {"field": name, "cycle": res["cycle"], "k": res["k"],
               "json": f"{safe}_recon_cycle{cycle}.json",
               "csv": f"{safe}_recon_nodes.csv",
               "quality": f"{safe}_recon_quality.json",
               "captured_var": res["captured_var"],
               "finite_fraction": res["finite_fraction"],
               "total_rmse": qual["total_rmse"],
               "coverage": res["coverage"]}
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
        prog="fv.reconfield",
        description="FlowViewer R53 full-field POD reconstruction at a cycle")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("verts", help=".npy or .json (N,3) vertex array")
    ap.add_argument("--cycle", type=int, default=0)
    ap.add_argument("--k", type=int, default=None, help="keep top-k modes")
    ap.add_argument("--p", type=float, default=2.0)
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--out", default="reconfield_out")
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
        summary = write_reconfield(verts, art, args.out, cycle=args.cycle,
                                   k=args.k, p=args.p, neighbors=args.neighbors)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
