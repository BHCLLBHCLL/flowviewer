"""R44: spectral mode detection over a power spectrum.

R41/R43 report the *dominant* frequency; R44 automates enumerating **all**
significant oscillation modes of a probe. Given a power spectrum ``(freq,
psd)`` it:

* ``spectral_peaks`` — picks the local maxima above a relative prominence floor,
  so the harmonic order of a probe (fundamental + overtones / vortex-shedding +
  harmonics) is listed with its frequency and energy.
* ``energy_shares`` — each accepted peak's share of the (DC-excluded) fluctu
  ation energy, plus the top-k cumulative share, so one can state "the first
  three modes carry ~80% of the fluctuation energy".
* ``turbulent_intensity`` — a cheap ``std/mean`` fluctuation measure on the raw
  time series (usable from a trace directly).

Pure NumPy, headless, no CGNS/vtk dependencies. ``modes_from_spectrum`` consumes
an R41-style ``analyze_series`` dict (``freq`` + ``psd`` lists); the CLI writes
a ``modes.json`` + ``summary.json``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Sequence

import numpy as np

DEFAULT_PROMINENCE = 0.05


# ── peak detection ─────────────────────────────────────────────────────────


def spectral_peaks(freq, psd, prominence_frac: float = DEFAULT_PROMINENCE) \
        -> List[dict]:
    """Local maxima of ``psd`` above ``prominence_frac * max(psd@f>0)``.

    ``freq`` / ``psd`` are equal-length arrays. DC (``f<=0``) is excluded, so
    only genuine oscillation modes qualify. Returns peaks sorted by energy
    (desc): ``[{"freq": …, "psd": …}, …]``. Degenerate inputs yield ``[]``.
    """
    freq = np.asarray(freq, dtype=np.float64).ravel()
    psd = np.asarray(psd, dtype=np.float64).ravel()
    if freq.size != psd.size:
        raise ValueError("freq and psd length mismatch")
    pos = np.flatnonzero((freq > 0) & np.isfinite(psd))
    if pos.size < 3:
        return []
    f = freq[pos]
    p = psd[pos]
    pmax = float(p.max())
    if not (pmax > 0):
        return []
    thr = prominence_frac * pmax
    picks = []
    for i in range(1, p.size - 1):
        if p[i] >= p[i - 1] and p[i] >= p[i + 1] and p[i] >= thr:
            picks.append({"freq": float(f[i]), "psd": float(p[i])})
    picks.sort(key=lambda d: d["psd"], reverse=True)
    return picks


# ── energy decomposition ───────────────────────────────────────────────────


def energy_shares(freq, psd,
                  prominence_frac: float = DEFAULT_PROMINENCE) -> dict:
    """Fluctuation-energy decomposition of the spectrum.

    Returns ``{"total", "n_peaks", "peaks":[{freq, psd, share}], "top_k":[
    {k, cumulative_share}], "top_k_endpoint": {..}}``. ``total`` is the sum of
    ``psd`` over ``f>0``; each peak's ``share`` is its energy / total.
    """
    freq = np.asarray(freq, dtype=np.float64).ravel()
    psd = np.asarray(psd, dtype=np.float64).ravel()
    finite = (freq > 0) & np.isfinite(psd)
    total = float(psd[finite].sum()) if finite.any() else 0.0
    peaks = spectral_peaks(freq, psd, prominence_frac)
    out_peaks = []
    for pk in peaks:
        share = (pk["psd"] / total) if total > 0 else float("nan")
        out_peaks.append({"freq": pk["freq"], "psd": pk["psd"],
                          "share": share})
    cumsum = 0.0
    top_k = []
    for k, pk in enumerate(out_peaks, start=1):
        cumsum += pk["share"]
        top_k.append({"k": k, "cumulative_share": cumsum})
    return {"total": total, "n_peaks": len(out_peaks), "peaks": out_peaks,
            "top_k": top_k}


def turbulent_intensity(values: Sequence) -> dict:
    """RMS/mean fluctuation intensity of a raw time series (as %)."""
    v = np.asarray(values, dtype=np.float64).ravel()
    v = v[np.isfinite(v)]
    n = int(v.size)
    if n < 2:
        nan = float("nan")
        return {"n": n, "mean": nan, "std": nan, "ti_pct": nan}
    mean = float(v.mean())
    std = float(v.std(ddof=1))
    ti = (std / abs(mean)) * 100.0 if mean else float("nan")
    return {"n": n, "mean": mean, "std": std, "ti_pct": ti}


# ── spectrum-artifact runner ───────────────────────────────────────────────


def modes_from_spectrum(res: dict,
                        prominence_frac: float = DEFAULT_PROMINENCE) -> dict:
    """Consume an R41 ``analyze_series`` dict → modes + energy decomposition."""
    freq = list(res.get("freq", []))
    psd = list(res.get("psd", []))
    es = energy_shares(freq, psd, prominence_frac)
    return {
        "n": res.get("n"),
        "organized": es,
        "dominant": es["peaks"][0] if es["peaks"] else None,
    }


# ── I/O ────────────────────────────────────────────────────────────────────


def write_modes(field_name: str, result: dict, out_dir: str) -> dict:
    """Write ``<field>_modes.json`` (via summary) + ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in field_name) or "field"
    fname = f"{safe}_modes.json"
    with open(out / fname, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    es = result.get("organized", {})
    summary = {
        "field": field_name, "file": fname,
        "total": es.get("total"), "n_peaks": es.get("n_peaks"),
        "dominant": result.get("dominant"),
        "top_k": es.get("top_k", [])[-1] if es.get("top_k") else None,
    }
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.modes",
        description="FlowViewer R44 spectral mode detection (freq + psd JSON)")
    ap.add_argument("spectrum_json", help="JSON with 'freq'[] and 'psd'[] lists "
                                          "(e.g. an R41 analyze_series dict)")
    ap.add_argument("--out", default="modes_out")
    ap.add_argument("--prominence", type=float, default=DEFAULT_PROMINENCE)
    args = ap.parse_args(argv)
    with open(args.spectrum_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "freq" not in data or "psd" not in data:
        print("error: spectrum_json must contain 'freq' and 'psd' arrays",
              file=__import__("sys").stderr)
        return 2
    res = modes_from_spectrum(data, prominence_frac=args.prominence)
    field_name = data.get("name") or Path(args.spectrum_json).stem
    summary = write_modes(field_name, res, args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
