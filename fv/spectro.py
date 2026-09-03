"""R43: time-frequency spectrogram of a monitoring-point series.

R41 gave a single full-span power spectrum; R43 adds the *time* axis back:
a sliding-window FFT over the record yields a spectrogram, so one can read how
the dominant frequency **evolves** — transient start-up, sudden mode swap, or
slow drift on an unsteady run. Beyond the 2-D map, ``freq_evolution`` collapses
each window to its dominant frequency, exposing that trend directly for a
headless check / CSV/x-y plot.

Fully pure NumPy (``rfft`` over sliding windows, no librosa/scipy), headless,
no CGNS/vtk dependencies. ``spectrogram_from_trace`` consumes an R38 trace
artifact (one probe), and the CLI writes a per-probe spectrogram JSON plus a
``summary.json`` with the dominant-frequency walk.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

DEFAULT_NPSEG = 128


# ── helpers ────────────────────────────────────────────────────────────────


def _fill_finite(x: np.ndarray) -> np.ndarray:
    """Linearly interpolate over the non-finite samples of ``x``.

    Returns ``None`` when fewer than two finite samples remain (caller guards).
    """
    x = np.asarray(x, dtype=np.float64).ravel()
    m = np.isfinite(x)
    if m.sum() < 2:
        return None
    if m.all():
        return x
    idx = np.arange(x.size)
    return np.interp(idx, idx[m], x[m])


# ── spectrogram ────────────────────────────────────────────────────────────


def spectrogram(x, nperseg: Optional[int] = None, dt: float = 1.0,
                overlap: float = 0.5) -> dict:
    """Sliding-window FFT power spectrogram of ``x``.

    Returns::

        {"n", "dt", "nperseg", "nw", "freq": [...], "time": [...],
         "S": [[...] per window], "peak_freq": [...per window],
         "mean_peak_freq"}

    ``time`` is the midpoint time (in ``dt`` units) of each window; ``S[w]`` is
    the one-sided ``|F|²/nperseg`` periodogram of window ``w`` (up to Nyquist).
    ``peak_freq[w]`` is the dominant (non-zero) frequency of that window. Fewer
    than two finite samples / too-small ``nperseg`` yield all-NA.
    """
    arr = _fill_finite(np.asarray(x, dtype=np.float64))
    if arr is None:
        return _empty(n=0)
    n = int(arr.size)
    if nperseg is None:
        nperseg = min(DEFAULT_NPSEG, n)
    nperseg = min(int(nperseg), n)
    if nperseg < 2:
        return _empty(n=n)
    step = max(1, int(nperseg * (1.0 - overlap)))
    starts = list(range(0, n - nperseg + 1, step))
    nw = len(starts)
    fn = nperseg // 2 + 1
    freqs = np.fft.rfftfreq(nperseg, d=float(dt))
    S = np.zeros((nw, fn))
    time = np.zeros(nw)
    peak = np.zeros(nw)
    pos = np.flatnonzero(freqs > 0)
    for w, s0 in enumerate(starts):
        seg = arr[s0:s0 + nperseg]
        seg = seg - seg.mean()
        P = (np.abs(np.fft.rfft(seg, n=nperseg)) ** 2) / nperseg
        S[w] = P
        time[w] = (s0 + nperseg / 2.0) * float(dt)
        if pos.size:
            peak[w] = float(freqs[int(pos[np.argmax(P[pos])])])
    return {
        "n": n, "dt": float(dt), "nperseg": int(nperseg), "nw": nw,
        "freq": [float(f) for f in freqs],
        "time": [float(t) for t in time],
        "S": [[float(v) for v in row] for row in S],
        "peak_freq": [float(p) for p in peak],
        "mean_peak_freq": float(peak.mean()) if nw and pos.size else float("nan"),
    }


def _empty(n: int) -> dict:
    nan = float("nan")
    return {"n": int(n), "dt": nan, "nperseg": 0, "nw": 0, "freq": [],
            "time": [], "S": [], "peak_freq": [], "mean_peak_freq": nan}


def freq_evolution(ss: dict) -> dict:
    """Summarise the dominant-frequency walk across the spectrogram windows."""
    peak = [p for p in ss.get("peak_freq", [])]
    if not peak:
        return {"nw": 0, "fastest": float("nan"), "slowest": float("nan"),
                "range": float("nan"), "start_freq": float("nan"),
                "end_freq": float("nan"), "drift": float("nan")}
    fast = float(max(peak))
    slow = float(min(peak))
    return {
        "nw": len(peak), "fastest": fast, "slowest": slow,
        "range": fast - slow,
        "start_freq": peak[0], "end_freq": peak[-1],
        "drift": float(peak[-1]) - float(peak[0]),
    }


# ── trace-artifact runner ──────────────────────────────────────────────────


def spectrogram_from_trace(artifact: dict, probe: int = 0, *,
                           nperseg: Optional[int] = None,
                           dt: float = 0.0) -> dict:
    """Spectrogram of one probe history in an R38 trace artifact.

    ``artifact`` has ``cycles`` + ``probes[].values``. When ``dt`` is falsy it
    is inferred from the cycle axis (median spacing, reusing ``fv.spectrum``).
    """
    cycles = list(artifact.get("cycles", []))
    probes = list(artifact.get("probes", []))
    if not probes:
        return {**_empty(0), "probe": int(probe), "query": None, "node": None}
    p = probes[int(probe)]
    if not dt and len(cycles) >= 2:
        from .spectrum import mean_dt
        dt = mean_dt(cycles)
    res = spectrogram(p.get("values", []), nperseg=nperseg, dt=float(dt))
    res["probe"] = int(probe)
    res["query"] = p.get("query")
    res["node"] = p.get("node")
    return res


# ── I/O ────────────────────────────────────────────────────────────────────


def write_spectrogram(field_name: str, results: Sequence[dict],
                      out_dir: str) -> dict:
    """Write one spectrogram JSON per probe plus ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in field_name) or "field"
    rows = []
    for r in results:
        fname = f"{safe}__probe{r['probe']}_spectro.json"
        out_js = {"probe": r["probe"], "query": r["query"], "node": r["node"],
                  "n": r["n"], "dt": r["dt"], "nperseg": r["nperseg"],
                  "freq": r["freq"], "time": r["time"], "S": r["S"],
                  "peak_freq": r["peak_freq"],
                  "mean_peak_freq": r["mean_peak_freq"],
                  "evolution": freq_evolution(r)}
        with open(out / fname, "w", encoding="utf-8") as fh:
            json.dump(out_js, fh)
        ev = out_js["evolution"]
        rows.append({"probe": r["probe"], "file": fname,
                     "mean_peak_freq": r["mean_peak_freq"],
                     **ev})
    summary = {"field": field_name, "probes": rows}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.spectro",
        description="FlowViewer R43 monitoring-point time-frequency spectrogram")
    ap.add_argument("trace_json", help="R38 trace <field>.json with cycles+probes")
    ap.add_argument("--out", default="spectro_out")
    ap.add_argument("--probe", type=int, default=None,
                    help="only analyze this probe index (default: all)")
    ap.add_argument("--nperseg", type=int, default=None)
    ap.add_argument("--dt", type=float, default=0.0)
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    probes = list(art.get("probes", []))
    which = [args.probe] if args.probe is not None \
        else list(range(len(probes)))
    results = [spectrogram_from_trace(art, i, nperseg=args.nperseg, dt=args.dt)
               for i in which]
    field_name = art.get("name") or Path(args.trace_json).stem
    summary = write_spectrogram(field_name, results, args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
