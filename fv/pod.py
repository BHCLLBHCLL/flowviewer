"""R48: Proper Orthogonal Decomposition (POD) of monitoring-point data.

R47 correlated the probe set; R48 goes one step further and *decomposes* the
space–time monitoring data: the ``(n_probes, n_cycles)`` snapshot matrix is
centred and factored with the SVD so one gets an ordered list of spatial modes
(probe weightings) ranked by fluctuation energy, with each mode's time
coefficient. This is the classic "which spatial structures drive the
unsteadiness" analysis — e.g. a dominant von-Kármán street mode versus a
low-energy mean-flow correction.

Consumes an R38 trace artifact (``{name, cycles, probes:[{values,…}]}``) via
``history_matrix`` (R47). Pure NumPy (``numpy.linalg.svd``), headless, no
CGNS/vtk dependencies.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from .probecorr import history_matrix

# ── matrix construction ────────────────────────────────────────────────────


def snapshot_matrix(artifact: dict, center: bool = True):
    """(n_probes, n_cycles) data matrix for POD.

    Rows are probe histories (transposed ``history_matrix``). NaN is imputed
    per row with that row's finite mean (an all-NaN probe becomes a zero row,
    contributing no energy). When ``center`` the rows are de-meaned so modes
    capture fluctuations, not static offsets.
    """
    M, cycles = history_matrix(artifact)
    X = np.asarray(M, dtype=np.float64).T          # (n_probes, n_cycles)
    for i in range(X.shape[0]):
        row = X[i]
        m = np.isfinite(row)
        if not m.all():
            fill = float(row[m].mean()) if m.any() else 0.0
            X[i][~m] = fill
    if center and X.shape[1] >= 2:
        X = X - X.mean(axis=1, keepdims=True)
    return X, cycles


# ── decomposition ──────────────────────────────────────────────────────────


def pod_decompose(artifact: dict, n_modes=None, center: bool = True) -> dict:
    """SVD POD of the monitoring-point snapshot matrix.

    Returns::

        {"n_probes", "n_cycles", "n_modes", "cycles": [...],
         "energy": [σᵢ² per kept mode],
         "energy_shares": [σᵢ²/Σσ²],
         "cum_energy": [...cumulative shares...],
         "modes": [[probe weights of mode i] ...],
         "coeffs": [[time coefficient of mode i] ...]}

    ``modes`` (columns of the left singular vectors) are the spatial modes;
    ``coeffs[i] = σᵢ·Vᵢ`` the mode's time series. Modes are kept in energy
    order; ``n_modes`` (default ``min(n_probes, n_cycles)``) caps the count.
    """
    X, cycles = snapshot_matrix(artifact, center=center)
    n_probes, n_cycles = X.shape
    if n_probes == 0 or n_cycles == 0:
        return {"n_probes": int(n_probes), "n_cycles": int(n_cycles),
                "n_modes": 0, "cycles": list(cycles), "energy": [],
                "energy_shares": [], "cum_energy": [], "modes": [],
                "coeffs": []}
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    k = int(min(n_probes, n_cycles))
    s2 = S * S
    total = float(s2.sum()) or 0.0
    # effective rank: drop modes carrying negligible energy
    tol = (s2.max() * 1e-12) if s2.size else 0.0
    eff = int((s2 > tol).sum()) if tol > 0 else 0
    if n_modes is None:
        n_modes = eff
    n_modes = max(0, min(int(n_modes), eff, k))
    energy = [float(s2[t]) for t in range(n_modes)]
    shares = [e / total if total > 0 else 0.0 for e in energy]
    cum = []
    acc = 0.0
    for s in shares:
        acc += s
        cum.append(acc)
    modes = [[float(v) for v in U[:, t]] for t in range(n_modes)]
    coeffs = [[float(v * S[t]) for v in Vt[t, :]] for t in range(n_modes)]
    return {"n_probes": int(n_probes), "n_cycles": int(n_cycles),
            "n_modes": n_modes, "cycles": list(cycles), "energy": energy,
            "energy_shares": shares, "cum_energy": cum, "modes": modes,
            "coeffs": coeffs}


def pod_summary(artifact: dict, n_modes=None, center: bool = True) -> dict:
    """POD plus the leading mode's temporal dominant frequency (R41)."""
    pod = pod_decompose(artifact, n_modes=n_modes, center=center)
    mode1_freq = None
    if pod["n_modes"] > 0 and len(pod["coeffs"][0]) >= 4:
        from .spectrum import analyze_series
        spec = analyze_series(pod["cycles"], pod["coeffs"][0])
        mode1_freq = spec.get("dominant_freq")
    return {**pod, "field": artifact.get("name") or "",
            "mode1_dominant_freq": mode1_freq}


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_pod(summary: dict, out_dir: str) -> dict:
    """Write ``<field>_pod.json``, ``<field>_modes.csv``, ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    field = summary.get("field") or "field"
    safe = "".join(ch if ch.isalnum() else "_" for ch in field) or "field"

    with open(out / f"{safe}_pod.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    with open(out / f"{safe}_modes.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["mode", "probe", "weight"])
        for t, mode in enumerate(summary["modes"]):
            for j, wgt in enumerate(mode):
                w.writerow([t, j, f"{wgt:.6g}"])
    top = {"field": field, "file": f"{safe}_pod.json",
           "modes_csv": f"{safe}_modes.csv",
           "n_probes": summary["n_probes"], "n_cycles": summary["n_cycles"],
           "n_modes": summary["n_modes"],
           "energy_shares": summary["energy_shares"],
           "cum_energy": summary["cum_energy"],
           "mode1_dominant_freq": summary.get("mode1_dominant_freq")}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(top, fh, indent=2)
    return top


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.pod",
        description="FlowViewer R48 POD of monitoring-point data")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("--out", default="pod_out")
    ap.add_argument("--modes", type=int, default=None,
                    help="keep at most N modes (default: min(n_probes, n_cycles))")
    ap.add_argument("--no-center", action="store_true",
                    help="do not de-mean each probe row")
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    if "probes" not in art:
        print("error: trace_json must contain 'probes'",
              file=__import__("sys").stderr)
        return 2
    summary = pod_summary(art, n_modes=args.modes, center=not args.no_center)
    if not summary.get("field"):
        summary["field"] = Path(args.trace_json).stem
    top = write_pod(summary, args.out)
    print(json.dumps(top, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
