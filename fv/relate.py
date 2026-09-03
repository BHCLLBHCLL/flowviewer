"""R42: relate two time series — lagged cross-correlation + coherence.

R41 gave a *single* monitoring-point FFT spectrum. R42 adds the two-series
relations that an unsteady/experimental pit typically wants next: *how do two
sensors relate, in time and in frequency*? Two pure-NumPy primitives:

* ``cross_correlate(x, y, max_lag)`` — normalized (Pearson) cross-correlation
  over lags, returning the best (lag, rho) — the optimal relative time offset
  between two probe histories (e.g. pressure at two stations, or baseline vs
  perturbed at one probe).
* ``coherence(x, y, nperseg, dt)`` — Welch magnitude-squared coherence
  (segment-averaged cross/auto periodograms) returning the sharing-region peak
  frequency — the dominant frequency the two probes oscillate at together.

Both are pure NumPy (``np.correlate`` / ``rfft``), headless, no CGNS/vtk
dependencies. ``relate_probes`` reads two probe series out of an R38 trace
artifact, and the CLI writes a JSON bundle per probe pair.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

DEFAULT_NPSEG = 256


# ── helpers ────────────────────────────────────────────────────────────────


def _finite_pair(x: np.ndarray, y: np.ndarray) -> tuple:
    """Return the finite-A∩B aligned value slices; () guards via caller."""
    m = np.isfinite(x) & np.isfinite(y)
    return x[m], y[m]


# ── cross-correlation ──────────────────────────────────────────────────────


def cross_correlate(x, y, max_lag: Optional[int] = None) -> dict:
    """Normalized lagged cross-correlation of two same-length series.

    Returns ``{"n", "best_lag", "best_rho", "lags": [...], "rho": [...]}``.
    ``best_lag`` is in samples; positive means ``x`` leads ``y``. Constant /
    degenerate series yield ``best_rho = NaN``.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    if x.size != y.size:
        raise ValueError("x and y length mismatch")
    x, y = _finite_pair(x, y)
    n = int(x.size)
    if n < 2:
        return _empty_cross()
    mx, my = float(x.mean()), float(y.mean())
    dx, dy = x - mx, y - my
    denom = float(np.sqrt((dx @ dx) * (dy @ dy)))
    full = np.correlate(dx, dy, mode="full")          # length 2n-1
    rho = (full / denom) if denom > 0 else \
        np.full(full.shape, np.nan)
    lags = np.arange(-(n - 1), n, dtype=np.int64)
    if max_lag is not None and max_lag >= 0:
        keep = np.abs(lags) <= max_lag
        lags, rho = lags[keep], rho[keep]
    finite = np.isfinite(rho)
    best_lag = float("nan")
    best_rho = float("nan")
    if finite.any():
        i = int(np.argmax(rho[finite]))
        best_lag = int(lags[finite][i])
        best_rho = float(rho[finite][i])
    return {
        "n": n, "best_lag": best_lag, "best_rho": best_rho,
        "lags": [int(v) for v in lags], "rho": [float(v) for v in rho],
    }


def _empty_cross() -> dict:
    nan = float("nan")
    return {"n": 0, "best_lag": nan, "best_rho": nan, "lags": [], "rho": []}


# ── Welch coherence ────────────────────────────────────────────────────────


def _segments(x: np.ndarray, nperseg: int, overlap: float):
    step = max(1, int(nperseg * (1.0 - overlap)))
    for i in range(0, len(x) - nperseg + 1, step):
        yield x[i:i + nperseg]


def coherence(x, y, nperseg: Optional[int] = None, dt: float = 1.0,
              overlap: float = 0.5) -> dict:
    """Welch magnitude-squared coherence between two same-length series.

    ``nperseg`` (default :data:`DEFAULT_NPSEG`, capped to the input length)
    controls segment length; ``dt`` the sampling interval for the frequency
    axis. Returns ``{"n", "nseg", "dt", "peak_freq", "peak_coherence",
    "mean_coherence", "freq": [...], "mscoh": [...]}``. Degenerate / too-short
    input yields all-NA.
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    y = np.asarray(y, dtype=np.float64).ravel()
    if x.size != y.size:
        raise ValueError("x and y length mismatch")
    x, y = _finite_pair(x, y)
    n = int(x.size)
    if nperseg is None:
        nperseg = min(DEFAULT_NPSEG, n)
    nperseg = min(int(nperseg), n)
    if nperseg < 2:
        return _empty_coherence(n)
    segs_x = list(_segments(x, nperseg, overlap))
    segs_y = list(_segments(y, nperseg, overlap))
    nseg = len(segs_x)
    fn = nperseg // 2 + 1
    pxx = np.zeros(fn)
    pyy = np.zeros(fn)
    pxy = np.zeros(fn, dtype=np.complex128)
    for sx, sy in zip(segs_x, segs_y):
        sx = sx - sx.mean()
        sy = sy - sy.mean()
        fx = np.fft.rfft(sx, n=nperseg)
        fy = np.fft.rfft(sy, n=nperseg)
        scale = nperseg
        pxx += (np.abs(fx) ** 2) / scale
        pyy += (np.abs(fy) ** 2) / scale
        pxy += fx * np.conj(fy) / scale
    pxx /= nseg
    pyy /= nseg
    pxy /= nseg
    denom = pxx * pyy
    mscoh = np.zeros(fn)
    np.divide(np.abs(pxy) ** 2, denom, out=mscoh, where=denom > 0)
    freqs = np.fft.rfftfreq(nperseg, d=float(dt))
    pos = np.flatnonzero(freqs > 0)
    peak_freq = float("nan")
    peak_c = float("nan")
    if pos.size:
        i = int(pos[np.argmax(mscoh[pos])])
        peak_freq = float(freqs[i])
        peak_c = float(mscoh[i])
    return {
        "n": n, "nseg": nseg, "dt": float(dt),
        "peak_freq": peak_freq, "peak_coherence": peak_c,
        "mean_coherence": float(mscoh[pos].mean()) if pos.size else float("nan"),
        "freq": [float(f) for f in freqs], "mscoh": [float(v) for v in mscoh],
    }


def _empty_coherence(n: int) -> dict:
    nan = float("nan")
    return {"n": int(n), "nseg": 0, "dt": nan, "peak_freq": nan,
            "peak_coherence": nan, "mean_coherence": nan, "freq": [], "mscoh": []}


# ── trace-artifact runner ──────────────────────────────────────────────────


def relate_probes(artifact: dict, probe_x: int, probe_y: int, *,
                  max_lag: Optional[int] = None,
                  nperseg: Optional[int] = None, dt: float = 0.0) -> dict:
    """Cross-corr + coherence between two probe histories of an R38 artifact.

    ``artifact`` has ``cycles`` + ``probes[].values`` (see ``fv.trace``). The
    cycle axis gives ``dt`` (median spacing) when ``dt`` is not supplied.
    """
    cycles = list(artifact.get("cycles", []))
    probes = list(artifact.get("probes", []))
    if len(probes) <= max(int(probe_x), int(probe_y)):
        return {"error": "probe index out of range"}
    vx = list(probes[int(probe_x)].get("values", []))
    vy = list(probes[int(probe_y)].get("values", []))
    if not dt and len(cycles) >= 2:
        from .spectrum import mean_dt
        dt = mean_dt(cycles)
    cc = cross_correlate(vx, vy, max_lag=max_lag)
    ch = coherence(vx, vy, nperseg=nperseg, dt=float(dt))
    return {
        "probe_x": int(probe_x), "probe_y": int(probe_y),
        "query_x": probes[int(probe_x)].get("query"),
        "query_y": probes[int(probe_y)].get("query"),
        "dt": float(dt),
        "cross_correlate": cc,
        "coherence": {k: ch[k] for k in ("n", "nseg", "peak_freq",
                                         "peak_coherence", "mean_coherence")},
    }


# ── I/O ────────────────────────────────────────────────────────────────────


def write_relate(field_name: str, results: Sequence[dict], out_dir: str) -> dict:
    """Write one JSON per probe pair plus ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in field_name) or "field"
    manifest: dict = {"field": field_name, "pairs": []}
    for r in results:
        fname = f"{safe}__probe{r['probe_x']}_vs_{r['probe_y']}.json"
        with open(out / fname, "w", encoding="utf-8") as fh:
            json.dump(r, fh)
        cc = r.get("cross_correlate", {})
        ch = r.get("coherence", {})
        manifest["pairs"].append({
            "file": fname, "probe_x": r["probe_x"], "probe_y": r["probe_y"],
            "best_lag": cc.get("best_lag"),
            "best_rho": cc.get("best_rho"),
            "peak_freq": ch.get("peak_freq"),
            "peak_coherence": ch.get("peak_coherence"),
        })
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


# ── CLI ────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.relate",
        description="FlowViewer R42 relate two monitoring-point series")
    ap.add_argument("trace_json", help="R38 trace <field>.json with cycles+probes")
    ap.add_argument("--out", default="relate_out")
    ap.add_argument("--px", type=int, default=0, help="probe X index")
    ap.add_argument("--py", type=int, default=1, help="probe Y index")
    ap.add_argument("--max-lag", type=int, default=None)
    ap.add_argument("--nperseg", type=int, default=None)
    ap.add_argument("--dt", type=float, default=0.0)
    ap.add_argument("--all", action="store_true",
                    help="relate every probe pair (default: px vs py)")
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    probes = list(art.get("probes", []))
    if args.all:
        pairs = [(i, j) for i in range(len(probes))
                 for j in range(i + 1, len(probes))]
        if not pairs:
            print("error: need at least two probes for --all",
                  file=__import__("sys").stderr)
            return 2
    else:
        pairs = [(args.px, args.py)]
    results = [relate_probes(art, a, b, max_lag=args.max_lag,
                             nperseg=args.nperseg, dt=args.dt)
               for a, b in pairs]
    field_name = art.get("name") or Path(args.trace_json).stem
    manifest = write_relate(field_name, results, args.out)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
