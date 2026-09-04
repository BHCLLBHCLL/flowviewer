"""R55: full-field modal reconstruction from DMD modes (complex envelope).

R53 reconstructed the whole node field at any cycle from **POD** modes (exact,
verifiable); R50's DMD has the same goal but needs its **complex** modes — each
carries a frequency, growth/damping and a complex spatial pattern — so a real
reconstruction must sum the complex envelopes ``αᵢ Qᵢ λᵢᶜ`` and take the real
part. R55 fills the POD/DMD spatial pair left out by R53's scope note.

Design:
- DMD is run on the **uncentred** snapshots (as R50), so the DC eigenmode
  (λ≈1) encodes the temporal mean itself; unlike R53 we do **not** re-add an
  explicit mean field to the reconstruction — the DC mode carries it. A nominal
  ``mean_field`` (IDW of per-probe temporal means) is still reported for the
  renderer but is informational only.
- Each complex per-probe mode is lifted onto the mesh by IDW on the real and
  imaginary parts separately (IDW is linear in the weights), the probe nodes
  tying back exactly to the per-probe DMD value. That gives a headless-verifiable
  quality path identical in spirit to R53.

Pure NumPy, headless, no CGNS/VTK. Reuses `dmd` internals (embedding + effective
rank) so the R50 decomposition is re-derived here with the full complex pieces
(λᵢ, αᵢ, φᵢ) that ``dmd_decompose`` does not retain.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from .dmd import _effective_rank, _embedded_snapshot_matrix
from .modalfield import idw_field
from .pod import snapshot_matrix
from .reconfield import _read_verts, _safe, mean_field
from .spectrum import mean_dt

# ── internal: re-derive DMD with the full complex pieces ────────────────────


def _dmd_pieces(artifact: dict, *, r: Optional[int] = None,
                dt: Optional[float] = None,
                embed_d: Optional[int] = None) -> Optional[dict]:
    """Complex DMD objects needed for reconstruction (energy-sorted).

    Returns ``{"lam", "alpha", "phi", "r", "n_probes", "n_cycles", "dt"}`` or
    ``None`` when the data is too short / degenerate. ``phi`` is the ``(n_probes,
    r)`` delay-0 block of each mode; ``lam``/``alpha`` follow the same energy
    ordering as R50's ``dmd_decompose``.
    """
    probes = list(artifact.get("probes", []))
    cycles = list(artifact.get("cycles", []))
    n_probes = len(probes)
    n_cycles = len(cycles)
    if n_cycles < 4 or n_probes == 0:
        return None
    if dt is None:
        dt = mean_dt(cycles) or 1.0
    if embed_d is None:
        embed_d = min(20, max(2, n_cycles // 5))
    embed_d = max(1, int(embed_d))
    X, _L = _embedded_snapshot_matrix(artifact, embed_d)
    n_rows, L = X.shape
    if L < 2 or n_rows == 0:
        return None

    X1 = X[:, :-1]
    X2 = X[:, 1:]
    U, S, Vh = np.linalg.svd(X1, full_matrices=False)
    r_eff = _effective_rank(S)
    if r_eff == 0:
        return None
    r = r_eff if r is None else int(r)
    r = max(1, min(r, r_eff))
    Ur = U[:, :r]
    Sr = S[:r]
    Vhr = Vh[:r, :]
    A_tilde = Ur.T @ X2 @ Vhr.T @ np.diag(1.0 / Sr)
    evals, W = np.linalg.eig(A_tilde)
    Phi = X2 @ Vhr.T @ np.diag(1.0 / Sr) @ W

    kidx = np.arange(L - 1)
    Vand = evals[:, None] ** kidx[None, :]              # (r, L-1): λᵢᵏ
    M = np.stack([(Phi[:, i, None] * Vand[i, None, :]).ravel()
                  for i in range(r)], axis=1)
    alpha = np.linalg.lstsq(M, X1.ravel(), rcond=None)[0]

    # delay-0 block of each probe, energy-ordered like R50
    lam = evals.astype(complex)
    phi = np.stack([Phi[p * embed_d, :] for p in range(n_probes)], axis=0)
    energy = np.asarray([float(abs(alpha[i]) ** 2
                                * np.sum(np.abs(Vand[i]) ** 2))
                         for i in range(r)])
    order = np.argsort(energy)[::-1]
    return {"lam": lam[order], "alpha": alpha[order], "phi": phi[:, order],
            "energy": energy[order], "r": int(r),
            "n_probes": int(n_probes), "n_cycles": int(n_cycles),
            "dt": float(dt)}


# ── IDW on complex weights ──────────────────────────────────────────────────


def complex_idw_field(verts: np.ndarray, probes: list,
                      weights: np.ndarray) -> np.ndarray:
    """IDW-spread a complex per-probe weight vector onto every mesh vertex."""
    w = np.asarray(weights, dtype=np.complex128).ravel()
    re = idw_field(verts, probes, w.real)
    im = idw_field(verts, probes, w.imag)
    out = np.empty_like(re, dtype=np.complex128)
    out.real = re
    out.imag = im
    return out


def _mode_meta(lam: complex, dt: float):
    """(freq, growth) of a complex eigenvalue in continuous time (as R50)."""
    if dt and lam != 0:
        w = np.log(lam) / dt
        freq = abs(w.imag) / (2 * np.pi)
        growth = float(w.real)
    else:
        freq, growth = 0.0, 0.0
    return float(freq), growth


def build_dmd_mode_field(verts: np.ndarray, artifact: dict, *, k: int = 0,
                         p: float = 2.0, neighbors: int = 4,
                         r: Optional[int] = None,
                         embed_d: Optional[int] = None) -> dict:
    """DMD mode-shape *magnitude* field: the R52 ``build_mode_field`` for DMD.

    Returns ``{"enabled", "i", "node_field", "meta"}`` where ``node_field`` is
    the per-vertex ``|Q_k|`` magnitude of the k-th (energy-ordered) DMD mode,
    and ``meta`` carries ``freq``/``growth``/``amplitude``/``energy_share`` plus
    shape range/coverage. Probe nodes carry their exact ``|φᵢ[k]|``. Empty or
    too-short artifacts degrade to ``enabled=False`` with an all-NaN field.
    """
    v = np.asarray(verts, dtype=np.float64)
    N = v.shape[0]
    empty = {"enabled": False, "i": int(k),
             "node_field": np.full(N, np.nan)
             if N else np.empty((0,), dtype=np.float64),
             "meta": {"i": int(k), "freq": 0.0, "growth": 0.0,
                      "amplitude": 0.0, "energy_share": 0.0,
                      "finite_fraction": 0.0, "min_abs": None,
                      "max_abs": None, "coverage": 0}}
    if not artifact.get("probes") or not artifact.get("cycles"):
        return empty
    pieces = _dmd_pieces(artifact, r=r, dt=None, embed_d=embed_d)
    if pieces is None:
        return empty
    rr = int(pieces["r"])
    if not (0 <= int(k) < rr):
        raise ValueError(f"DMD mode k={k} out of range (r={rr})")
    lam, alpha, phi, energy = (pieces["lam"], pieces["alpha"],
                               pieces["phi"], pieces["energy"])
    q = complex_idw_field(v, artifact["probes"], phi[:, int(k)])
    mag = np.abs(q)
    mag[(np.isnan(q.real)) & (np.isnan(q.imag))] = np.nan
    freq, growth = _mode_meta(lam[int(k)], pieces["dt"])
    total = float(energy.sum()) or 0.0
    share = float(energy[int(k)] / total) if total > 0 else 0.0
    fin = np.isfinite(mag)
    n_fin = int(fin.sum())
    return {"enabled": True, "i": int(k), "node_field": mag,
            "meta": {"i": int(k), "freq": freq, "growth": growth,
                     "amplitude": float(abs(alpha[int(k)])),
                     "energy_share": share,
                     "finite_fraction": float(n_fin / N) if N else 0.0,
                     "min_abs": float(mag[fin].min()) if n_fin else None,
                     "max_abs": float(mag[fin].max()) if n_fin else None,
                     "coverage": n_fin}}


# ── reconstruction ──────────────────────────────────────────────────────────


def reconstruct_field_dmd(verts: np.ndarray, artifact: dict, *, cycle: int = 0,
                          k: Optional[int] = None, p: float = 2.0,
                          neighbors: int = 4, r: Optional[int] = None,
                          embed_d: Optional[int] = None) -> dict:
    """Reconstruct the full mesh node field at cycle index *cycle* from DMD.

    ``recon(node) = Re( Σ_{i<k} αᵢ Qᵢ(node) λᵢ^cycle )`` with ``Qᵢ`` the IDW
    complex mode shape. Returns a dict with ``mean_field`` (informational),
    per-mode complex ``mode_fields``, the real ``recon_field``, the per-probe
    model value ``probe_recon`` and matrix-level ``captured_var`` / ``total_rmse``.
    Empty/too-short artifacts degrade to an all-NaN field (as R53).
    """
    vert = np.asarray(verts, dtype=np.float64)
    N = vert.shape[0]
    n_cycles = int(len(list(artifact.get("cycles", []))))

    def _empty():
        return {"cycle": int(cycle), "n_cycles": n_cycles, "n_probes": 0,
                "k": 0, "r": 0, "mean_field": np.full(N, np.nan)
                if N else np.empty((0,)), "mode_fields": [],
                "recon_field": np.full(N, np.nan) if N else np.empty((0,)),
                "probe_recon": [], "finite_fraction": 0.0,
                "captured_var": 0.0, "total_rmse": float("nan"),
                "coverage": 0}

    if not artifact.get("probes") or not artifact.get("cycles"):
        return _empty()
    pieces = _dmd_pieces(artifact, r=r, dt=None, embed_d=embed_d)
    if pieces is None:
        return _empty()
    n_cycles = int(pieces["n_cycles"])
    if not (0 <= int(cycle) < n_cycles):
        raise ValueError(f"cycle={cycle} out of range (n_cycles={n_cycles})")
    rr = int(pieces["r"])
    kk = int(k) if k is not None else rr
    kk = max(0, min(kk, rr))
    lam, alpha, phi = pieces["lam"], pieces["alpha"], pieces["phi"]

    probes = artifact["probes"]
    mean_f = mean_field(vert, probes, p=p, neighbors=neighbors)
    recon = np.zeros(N, dtype=np.complex128)
    mode_fields = []
    for i in range(kk):
        Q = complex_idw_field(vert, probes, phi[:, i])
        mode_fields.append(Q)
        recon += alpha[i] * Q * lam[i] ** int(cycle)
    recon_real = recon.real.copy()
    finite = np.isfinite(recon_real) & np.isfinite(mean_f)
    recon_real[~finite] = np.nan

    # probe-node model value: exact because IDW ties the node to its probe
    probe_recon = np.zeros(len(probes), dtype=np.float64)
    for j, pr in enumerate(probes):
        nd = pr.get("node")
        if isinstance(nd, (int, np.integer)) and 0 <= int(nd) < N:
            probe_recon[j] = float(recon_real[int(nd)])

    captured, rmse = _matrix_quality(artifact, lam, alpha, phi, kk)
    return {"cycle": int(cycle), "n_cycles": n_cycles,
            "n_probes": int(pieces["n_probes"]), "k": kk, "r": rr,
            "mean_field": mean_f, "mode_fields": mode_fields,
            "recon_field": recon_real, "probe_recon": probe_recon,
            "finite_fraction": float(finite.sum() / N) if N else 0.0,
            "captured_var": float(captured), "total_rmse": float(rmse),
            "coverage": int(finite.sum())}


def _matrix_quality(artifact: dict, lam: np.ndarray, alpha: np.ndarray,
                    phi: np.ndarray, kk: int):
    """Variance explained + RMSE of the top-kk DMD reconstruction at probes."""
    X, _c = snapshot_matrix(artifact, center=False)
    n_probes, n_cycles = X.shape
    if kk <= 0 or n_cycles == 0:
        return 0.0, float("nan")
    c = np.arange(n_cycles)
    xhat = np.zeros((n_probes, n_cycles), dtype=np.complex128)
    for i in range(kk):
        xhat += (alpha[i] * phi[:, i])[:, None] * lam[i] ** c[None, :]
    diff = X - xhat.real
    sse = float(np.sum(diff * diff))
    sst = float(np.sum((X - X.mean()) ** 2))
    captured = max(0.0, 1.0 - sse / sst) if sst > 0 else 0.0
    rmse = float(np.sqrt(sse / (n_probes * n_cycles)))
    return captured, rmse


# ── quality (matrix level, at the probe nodes) ──────────────────────────────


def dmd_recon_quality(artifact: dict, *, k: Optional[int] = None,
                      r: Optional[int] = None,
                      embed_d: Optional[int] = None) -> dict:
    """Reconstruction error of the DMD model at the probe nodes.

    ``captured_var = 1 − SSE/SStot`` over all cycles and probes of the top-k
    reconstruction; ``total_rmse ≈ 0`` when the DMD model spans the data and all
    modes are kept.
    """
    probes = list(artifact.get("probes", []))
    n_probes = len(probes)
    n_cycles = int(len(list(artifact.get("cycles", []))))
    empty = {"k": 0, "r": 0, "captured_var": 0.0, "per_probe_rmse": [],
             "per_cycle_rmse": [], "total_rmse": float("nan"),
             "n_probes": n_probes, "n_cycles": n_cycles}
    pieces = _dmd_pieces(artifact, r=r, dt=None, embed_d=embed_d)
    if pieces is None:
        return empty
    rr = int(pieces["r"])
    kk = int(k) if k is not None else rr
    kk = max(0, min(kk, rr))
    lam, alpha, phi = pieces["lam"], pieces["alpha"], pieces["phi"]
    X, _c = snapshot_matrix(artifact, center=False)
    c = np.arange(n_cycles)
    xhat = np.zeros((n_probes, n_cycles), dtype=np.complex128)
    for i in range(kk):
        xhat += (alpha[i] * phi[:, i])[:, None] * lam[i] ** c[None, :]
    diff = np.asarray(X - xhat.real, dtype=np.float64)
    per_probe = [float(np.sqrt(np.mean(diff[j] ** 2))) for j in range(n_probes)]
    per_cycle = [float(np.sqrt(np.mean(diff[:, c0] ** 2)))
                 for c0 in range(n_cycles)]
    sse = float(np.sum(diff * diff))
    sst = float(np.sum((X - X.mean()) ** 2))
    captured = max(0.0, 1.0 - sse / sst) if sst > 0 else 0.0
    return {"k": kk, "r": rr, "captured_var": float(captured),
            "per_probe_rmse": per_probe, "per_cycle_rmse": per_cycle,
            "total_rmse": float(np.sqrt(sse / (n_probes * n_cycles))),
            "n_probes": n_probes, "n_cycles": n_cycles}


# ── I/O / CLI ───────────────────────────────────────────────────────────────


def write_dmdrecon(verts: np.ndarray, artifact: dict, out_dir: str, *,
                   cycle: int = 0, k: Optional[int] = None, p: float = 2.0,
                   neighbors: int = 4, r: Optional[int] = None,
                   embed_d: Optional[int] = None, field: str = "") -> dict:
    """Write DMD recon snapshot, node CSV, quality JSON and summary."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = field or artifact.get("name") or "field"
    safe = _safe(name)
    res = reconstruct_field_dmd(verts, artifact, cycle=cycle, k=k, p=p,
                                neighbors=neighbors, r=r, embed_d=embed_d)
    qual = dmd_recon_quality(artifact, k=k, r=r, embed_d=embed_d)
    modes = []
    for i, mf in enumerate(res["mode_fields"]):
        mg = np.abs(mf)
        modes.append({"i": i, "finite": int(np.isfinite(mg).sum()),
                      "mag_min": float(np.nanmin(mg)) if mg.size else None,
                      "mag_max": float(np.nanmax(mg)) if mg.size else None})
    payload = {"field": name, "cycle": res["cycle"], "k": res["k"],
               "r": res["r"], "n_probes": res["n_probes"],
               "n_cycles": res["n_cycles"], "captured_var": res["captured_var"],
               "total_rmse": res["total_rmse"],
               "finite_fraction": res["finite_fraction"],
               "mean_field": [None if v != v else float(v)
                              for v in res["mean_field"]],
               "recon_field": [None if v != v else float(v)
                               for v in res["recon_field"]],
               "mode_shape": modes}
    with open(out / f"{safe}_dmdrecon_cycle{cycle}.json", "w",
              encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    vert = np.asarray(verts, dtype=np.float64)
    recon = res["recon_field"]
    with open(out / f"{safe}_dmdrecon_nodes.csv", "w", newline="",
              encoding="utf-8") as fh:
        wcsv = csv.writer(fh)
        wcsv.writerow(["node", "x", "y", "z", "recon"])
        for i2 in range(len(vert)):
            rc = f"{float(recon[i2]):.6g}" if np.isfinite(recon[i2]) else ""
            wcsv.writerow([i2, f"{vert[i2][0]:.6g}", f"{vert[i2][1]:.6g}",
                           f"{vert[i2][2]:.6g}", rc])
    with open(out / f"{safe}_dmdrecon_quality.json", "w",
              encoding="utf-8") as fh:
        json.dump(qual, fh, indent=2)
    summary = {"field": name, "cycle": res["cycle"], "k": res["k"],
               "r": res["r"], "json": f"{safe}_dmdrecon_cycle{cycle}.json",
               "csv": f"{safe}_dmdrecon_nodes.csv",
               "quality": f"{safe}_dmdrecon_quality.json",
               "captured_var": res["captured_var"],
               "finite_fraction": res["finite_fraction"],
               "total_rmse": qual["total_rmse"],
               "coverage": res["coverage"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.dmdrecon",
        description="FlowViewer R55 full-field DMD reconstruction at a cycle")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("verts", help=".npy or .json (N,3) vertex array")
    ap.add_argument("--cycle", type=int, default=0)
    ap.add_argument("--k", type=int, default=None, help="keep top-k modes")
    ap.add_argument("--p", type=float, default=2.0)
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--r", type=int, default=None)
    ap.add_argument("--embed-d", type=int, default=None)
    ap.add_argument("--out", default="dmdrecon_out")
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
        summary = write_dmdrecon(verts, art, args.out, cycle=args.cycle,
                                 k=args.k, p=args.p, neighbors=args.neighbors,
                                 r=args.r, embed_d=args.embed_d)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
