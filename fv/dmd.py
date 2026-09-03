"""R50: Dynamic Mode Decomposition (DMD) of monitoring-point data.

R48/R49 gave the *static* POD picture; DMD is its **dynamic** companion: it
fits the monitoring snapshots to ``x_{k+1} = A x_k`` and extracts eigen-modes of
``A``, so every mode carries a **frequency** and a **growth/damping rate** in
addition to its spatial pattern. That answers "which oscillating dynamics
dominate and are they growing or decaying".

A pure tone lives in a rank-1 real snapshot matrix, so exact DMD collapses its
conjugate pair into a real eigenvalue and loses the frequency. We therefore use
**time-delay (Hankel) embedding**: each probe series is lifted into ``d`` delayed
copies (state vector ``[s_k, s_{k+1}, …]``), which exposes oscillation as rank-2
and lets DMD recover the true frequencies.

Exact (projected) DMD on the embedded ``(n_probes·d, L)`` matrix:

1. ``X1 = X[:, :-1]``, ``X2 = X[:, 1:]``; SVD ``X1 = U Σ V*``, truncate to the
   effective rank ``r`` (drop singular values below ``σ_max·1e-12``).
2. Reduced operator ``Ã = Uᵣᵀ X2 Vᵣ Σᵣ⁻¹``; eigendecompose ``Ã W = W Λ``.
3. DMD modes ``Φ = X2 Vᵣ Σᵣ⁻¹ W``; amplitudes ``α`` by least-squares fit of the
   whole time series against the exponential basis ``Φᵢ αᵢ λᵢᵏ``.
4. Continuous-time ``ω = ln(λ)/dt`` → ``freq = |Im ω|/(2π)``, ``growth = Re ω``.

Consumes an R38 trace artifact. Pure NumPy, headless, no CGNS/vtk dependencies.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np

from .pod import snapshot_matrix

_EPS = 1e-12


def _effective_rank(s: np.ndarray) -> int:
    if s.size == 0 or float(s[0]) <= 0:
        return 0
    return int((s > s[0] * _EPS).sum())


def _embedded_snapshot_matrix(artifact: dict, d: int):
    """(n_probes·d, L) Hankel-embedded snapshot matrix + its length L."""
    X, cycles = snapshot_matrix(artifact, center=False)
    n_probes, n_cycles = X.shape
    if d >= n_cycles:
        d = n_cycles - 1
    L = n_cycles - d + 1
    rows = []
    for i in range(n_probes):
        s = X[i]
        for k in range(d):
            rows.append(s[k:k + L])
    return np.stack(rows, axis=0), L


def dmd_decompose(artifact: dict, r: Optional[int] = None,
                  dt: Optional[float] = None,
                  embed_d: Optional[int] = None) -> dict:
    """DMD (with time-delay embedding) of the monitoring snapshots.

    Returns::

        {"field", "n_probes", "n_cycles", "embed_d", "r", "dt", "nyquist",
         "modes": [{"i", "freq", "growth", "amplitude", "energy", "share",
                    "mode": [[re, im] probe weights], "mode_mag": [...]}, ...],
         "dominant": {"i", "freq", "growth", "amplitude", "share"} | None}

    ``modes`` are sorted by reconstructed energy descending; ``dominant`` is the
    highest-energy *oscillating* mode (``freq > 1e-9``), so a static (DC) offset
    never wins. ``mode`` is the delay-0 block of the (complex) DMD eigenvector —
    the per-probe participation — encoded as [real, imag] pairs for JSON.
    """
    from .spectrum import mean_dt

    probes = list(artifact.get("probes", []))
    cycles = list(artifact.get("cycles", []))
    n_probes = len(probes)
    n_cycles = len(cycles)
    empty = {"field": artifact.get("name") or "", "n_probes": int(n_probes),
             "n_cycles": int(n_cycles), "embed_d": 0, "r": 0, "dt": None,
             "nyquist": None, "modes": [], "dominant": None}
    if n_cycles < 4 or n_probes == 0:
        return empty
    if dt is None:
        dt = mean_dt(cycles) or 1.0
    nyquist = 0.5 / dt if dt else None
    if embed_d is None:
        embed_d = min(20, max(2, n_cycles // 5))
    embed_d = max(1, int(embed_d))
    X, _L = _embedded_snapshot_matrix(artifact, embed_d)
    n_rows, L = X.shape
    if L < 2 or n_rows == 0:
        return empty

    X1 = X[:, :-1]
    X2 = X[:, 1:]
    U, S, Vh = np.linalg.svd(X1, full_matrices=False)
    r_eff = _effective_rank(S)
    if r_eff == 0:
        return empty
    r = r_eff if r is None else int(r)
    r = max(1, min(r, r_eff))
    Ur = U[:, :r]
    Sr = S[:r]
    Vhr = Vh[:r, :]
    A_tilde = Ur.T @ X2 @ Vhr.T @ np.diag(1.0 / Sr)
    evals, W = np.linalg.eig(A_tilde)
    Phi = X2 @ Vhr.T @ np.diag(1.0 / Sr) @ W

    kidx = np.arange(L - 1)
    Vand = evals[:, None] ** kidx[None, :]          # (r, L-1): λᵢᵏ
    M = np.stack([(Phi[:, i, None] * Vand[i, None, :]).ravel()
                  for i in range(r)], axis=1)
    alpha = np.linalg.lstsq(M, X1.ravel(), rcond=None)[0]

    modes = []
    for i in range(r):
        lam = complex(evals[i])
        if dt and lam != 0:
            w = np.log(lam) / dt
            freq = abs(w.imag) / (2 * np.pi)
            growth = float(w.real)
        else:
            freq, growth = 0.0, 0.0
        pw = np.asarray([Phi[p * embed_d, i] for p in range(n_probes)],
                        dtype=complex)    # delay-0 block of each probe
        mag = [float(abs(v)) for v in pw]
        energy = float(abs(alpha[i]) ** 2 * np.sum(np.abs(Vand[i]) ** 2))
        modes.append({"i": int(i), "freq": float(freq), "growth": float(growth),
                      "amplitude": float(abs(alpha[i])), "energy": energy,
                      "mode": [[float(v.real), float(v.imag)] for v in pw],
                      "mode_mag": mag})
    total = sum(m["energy"] for m in modes) or 0.0
    for m in modes:
        m["share"] = float(m["energy"] / total) if total > 0 else 0.0
    modes.sort(key=lambda m: m["energy"], reverse=True)

    dominant = None
    for m in modes:
        if m["freq"] > 1e-9 and m["amplitude"] > 1e-9:
            dominant = {"i": m["i"], "freq": m["freq"], "growth": m["growth"],
                        "amplitude": m["amplitude"], "share": m["share"]}
            break
    return {"field": artifact.get("name") or "", "n_probes": int(n_probes),
            "n_cycles": int(n_cycles), "embed_d": int(embed_d), "r": r,
            "dt": float(dt), "nyquist": nyquist, "modes": modes,
            "dominant": dominant}


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_dmd(summary: dict, out_dir: str) -> dict:
    """Write ``<field>_dmd.json``, ``<field>_modes.csv``, ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    field = summary.get("field") or "field"
    safe = "".join(ch if ch.isalnum() else "_" for ch in field) or "field"

    with open(out / f"{safe}_dmd.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    _write_modes_csv(out / f"{safe}_modes.csv", summary["modes"])
    top = {"field": field, "file": f"{safe}_dmd.json",
           "modes_csv": f"{safe}_modes.csv", "r": summary["r"],
           "embed_d": summary["embed_d"], "dt": summary["dt"],
           "n_modes": len(summary["modes"]),
           "dominant_freq": (summary["dominant"] or {}).get("freq"),
           "dominant_growth": (summary["dominant"] or {}).get("growth"),
           "dominant_share": (summary["dominant"] or {}).get("share")}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(top, fh, indent=2)
    return top


def _write_modes_csv(path: Path, modes: list) -> None:
    import csv
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["i", "freq", "growth", "amplitude", "share"])
        for m in modes:
            w.writerow([m["i"], f"{m['freq']:.6g}", f"{m['growth']:.6g}",
                        f"{m['amplitude']:.6g}", f"{m['share']:.6g}"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.dmd",
        description="FlowViewer R50 DMD of monitoring-point data")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("--out", default="dmd_out")
    ap.add_argument("--r", type=int, default=None,
                    help="truncate SVD to r modes (default: effective rank)")
    ap.add_argument("--embed-d", type=int, default=None,
                    help="time-delay embedding depth (default: min(20, n//5))")
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    if "probes" not in art:
        print("error: trace_json must contain 'probes'",
              file=__import__("sys").stderr)
        return 2
    summary = dmd_decompose(art, r=args.r, embed_d=args.embed_d)
    top = write_dmd(summary, args.out)
    print(json.dumps(top, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
