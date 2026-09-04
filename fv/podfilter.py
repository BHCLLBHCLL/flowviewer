"""R49: POD low-rank reconstruction + per-probe filtering.

R48 *decomposed* the monitoring-point data into spatial modes; R49 uses those
modes to answer "how much of the fluctuation does the top-k capture" and to
**denoise a probe's history**: keeping only the leading modes reconstructs the
coherent (periodic) part and drops the incoherent tail — the classic
low-rank / POD filtering view.

Pure NumPy, headless, no CGNS/vtk dependencies. Reuses R48 (``pod_decompose`` /
``snapshot_matrix``) and consumes an R38 trace artifact.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Optional

import numpy as np

from .pod import pod_decompose, snapshot_matrix

DEFAULT_ENERGY_TARGET = 0.95


# ── reconstruction ─────────────────────────────────────────────────────────


def pod_reconstruct(artifact: dict, k: Optional[int] = None) -> dict:
    """Low-rank (top-k) reconstruction of the centered monitoring data.

    ``X_k = Σᵢ<k modeᵢ ⊗ coeffᵢ`` (mode outer-product its time coefficient).
    Returns::

        {"k", "n_probes", "n_cycles", "cycles", "captured_var",
         "per_probe_rmse": [...], "total_rmse", "reconstructed": [[...]]}

    ``captured_var`` is the cumulative energy share of the kept modes; the RMSEs
    are measured against the centred original (in data units). ``k=None`` keeps
    every mode (reconstruction ~ exact).
    """
    pod = pod_decompose(artifact)
    X, _cycles = snapshot_matrix(artifact, center=True)
    n_probes, n_cycles = X.shape
    if pod["n_modes"] == 0 or n_probes == 0:
        return {"k": 0, "n_probes": int(n_probes), "n_cycles": int(n_cycles),
                "cycles": pod["cycles"], "captured_var": 0.0,
                "per_probe_rmse": [], "total_rmse": float("nan"),
                "reconstructed": []}
    kk = int(k) if k is not None else pod["n_modes"]
    kk = max(0, min(kk, pod["n_modes"]))
    recon = np.zeros((n_probes, n_cycles), dtype=np.float64)
    for i in range(kk):
        m = np.asarray(pod["modes"][i], dtype=np.float64)
        c = np.asarray(pod["coeffs"][i], dtype=np.float64)
        recon += np.outer(m, c)
    diff = X - recon
    per_probe = [float(np.sqrt(np.mean((diff[i] ** 2), axis=0)))
                 for i in range(n_probes)]
    captured = float(pod["cum_energy"][kk - 1]) if kk > 0 else 0.0
    return {
        "k": kk, "n_probes": int(n_probes), "n_cycles": int(n_cycles),
        "cycles": pod["cycles"], "captured_var": captured,
        "per_probe_rmse": per_probe,
        "total_rmse": float(np.sqrt(np.mean(diff ** 2))),
        "reconstructed": [[float(v) for v in row] for row in recon],
    }


def modes_to_energy(pod: dict, target: float = DEFAULT_ENERGY_TARGET) -> dict:
    """Fewest modes reaching ``target`` cumulative energy.

    Returns ``{"k", "captured"}`` — ``k=None`` when the target is never reached.
    The cumulative shares can sum to ``1-ε`` (not exactly ``1.0``) under float,
    so a tiny relative tolerance treats a target within ``1e-9`` of a cumulative
    value as reached (e.g. ``target=1.0`` with the full mode set).
    """
    cum = pod.get("cum_energy", [])
    eps = 1e-9 * max(1.0, float(abs(target)))
    for i, v in enumerate(cum):
        if v + eps >= target:
            return {"k": int(i + 1), "captured": float(v)}
    return {"k": None, "captured": float(cum[-1]) if cum else 0.0}


# ── filtering ──────────────────────────────────────────────────────────────


def filter_probe(artifact: dict, probe: int, k: Optional[int] = None) -> list:
    """Low-rank-denoised series of one probe (mean restored, so values are in
    original data units). Out-of-range probe → ``[]``."""
    probes = list(artifact.get("probes", []))
    if probe < 0 or probe >= len(probes):
        return []
    recon = pod_reconstruct(artifact, k=k)
    if recon["k"] == 0 or probe >= recon["n_probes"]:
        return []
    vals = [float(v) for v in probes[probe].get("values", [])
            if _finite(v)]
    mean = float(np.mean(vals)) if vals else 0.0
    return [float(v) + mean for v in recon["reconstructed"][probe]]


def _finite(v) -> bool:
    try:
        return bool(np.isfinite(float(v)))
    except (TypeError, ValueError):
        return False


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_recon(artifact: dict, k: Optional[int], out_dir: str,
                field: str = "") -> dict:
    """Write ``<field>_recon.json``, ``<field>_rmse.csv``, ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    recon = pod_reconstruct(artifact, k=k)
    name = field or artifact.get("name") or "field"
    safe = "".join(ch if ch.isalnum() else "_" for ch in name) or "field"
    out_payload = {**recon, "field": name}
    with open(out / f"{safe}_recon.json", "w", encoding="utf-8") as fh:
        json.dump(out_payload, fh, indent=2)
    with open(out / f"{safe}_rmse.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["probe", "rmse", "captured_var"])
        for i, r in enumerate(recon["per_probe_rmse"]):
            w.writerow([i, f"{r:.6g}", f"{recon['captured_var']:.6g}"])
    top = {"field": name, "file": f"{safe}_recon.json",
           "rmse_csv": f"{safe}_rmse.csv",
           "k": recon["k"], "captured_var": recon["captured_var"],
           "total_rmse": recon["total_rmse"],
           "n_probes": recon["n_probes"], "n_cycles": recon["n_cycles"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(top, fh, indent=2)
    return top


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.podfilter",
        description="FlowViewer R49 POD low-rank reconstruction + filtering")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("--out", default="podfilter_out")
    ap.add_argument("--k", type=int, default=None,
                    help="keep top-k modes (default: all)")
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    if "probes" not in art:
        print("error: trace_json must contain 'probes'",
              file=__import__("sys").stderr)
        return 2
    top = write_recon(art, args.k, args.out)
    print(json.dumps(top, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
