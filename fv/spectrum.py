"""R41: frequency / power-spectrum analysis of monitoring-point time series.

R38 recorded field-value histories at fixed monitoring points (and R40 compared
two sequences there). R41 adds the classic *unsteady* post-processing step on
top: given a per-monitoring-point series ``(cycle, value)``, detrend the DC,
FFT it to a power spectrum, and report the dominant (peak) frequency — the kind
of "vortex-shedding frequency at a probe" estimate used to check an unsteady
CFD solution.

Everything is pure NumPy (``numpy.fft.rfft`` / ``rfftfreq``), so the module is
headless-safe and dependency-light. Non-uniform / NaN-gapped snapshots are
handled by taking the median sampling interval over the finite pairs and
ignoring NaN values. The CLI consumes an R38-style trace artifact (a
``<field>.json`` with ``cycles`` + ``probes[].values``) and writes, per probe,
a PSD CSV plus a ``summary.json`` with the dominant frequency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import numpy as np

# ── core analysis ──────────────────────────────────────────────────────────


def mean_dt(cycles: np.ndarray) -> float:
    """Median sampling interval of a sorted cycle axis (robust to gaps).

    Returns ``0.0`` when fewer than two distinct times are present (caller must
    guard). Non-uniform cycles still get a sensible average spacing so ``dt`` is
    never zero unless the series is essentially a single instant.
    """
    c = np.asarray(cycles, dtype=np.float64).ravel()
    if c.size < 2:
        return 0.0
    diffs = np.diff(np.sort(c))
    diffs = diffs[diffs > 0]
    if diffs.size == 0:
        return 0.0
    return float(np.median(diffs))


def analyze_series(cycles, values) -> dict:
    """FFT power spectrum of ``(cycles, values)``.

    Detrends the mean (DC), estimates ``dt = mean_dt(cycles)``, then returns::

        {"n", "dt", "ymin", "ymax", "mean", "std",
         "nyquist", "dominant_freq", "dominant_psd", "dc_energy",
         "freq": [..], "psd": [..]}

    ``freq`` / ``psd`` are the one-sided (real) spectrum up to Nyquist; energy is
    ``|F|^2 / n`` (un-normalised periodogram). Fewer than two finite samples
    yields ``{"n": 0, ...}`` all-NA.
    """
    cycles = np.asarray(cycles, dtype=np.float64).ravel()
    values = np.asarray(values, dtype=np.float64).ravel()
    if cycles.size != values.size:
        raise ValueError("cycles and values length mismatch")
    m = np.isfinite(values)
    if int(m.sum()) < 2:
        return _empty()
    c = cycles[m]
    v = values[m]
    if np.all(v[0] == v):          # constant -> no oscillation
        d = {"n": int(v.size), "dt": mean_dt(c), "ymin": float(v.min()),
             "ymax": float(v.max()), "mean": float(v.mean()), "std": 0.0,
             "nyquist": 0.0, "dominant_freq": 0.0, "dominant_psd": 0.0,
             "dc_energy": float(v[0] ** 2), "freq": [], "psd": []}
        return d

    dt = mean_dt(c)
    if not (dt > 0):
        return _empty()
    n = int(v.size)
    mean = float(v.mean())
    det = v - mean
    S = np.fft.rfft(det, n=n)
    freqs = np.fft.rfftfreq(n, d=dt)
    psd = (np.abs(S) ** 2) / n
    nyquist = float(0.5 / dt)
    pos = np.flatnonzero(freqs > 0)
    dom_freq = 0.0
    dom_psd = 0.0
    if pos.size:
        i = int(pos[np.argmax(psd[pos])])
        dom_freq = float(freqs[i])
        dom_psd = float(psd[i])
    return {
        "n": n, "dt": dt, "ymin": float(v.min()), "ymax": float(v.max()),
        "mean": mean, "std": float(det.std(ddof=1)) if n > 1 else 0.0,
        "nyquist": nyquist, "dominant_freq": dom_freq,
        "dominant_psd": dom_psd, "dc_energy": float(mean ** 2),
        "freq": [float(x) for x in freqs], "psd": [float(x) for x in psd],
    }


def _empty() -> dict:
    nan = float("nan")
    return {"n": 0, "dt": nan, "ymin": nan, "ymax": nan, "mean": nan,
            "std": nan, "nyquist": nan, "dominant_freq": nan,
            "dominant_psd": nan, "dc_energy": nan, "freq": [], "psd": []}


# ── trace-artifact runner ──────────────────────────────────────────────────


def spectrum_from_trace(artifact: dict, probe: int = 0) -> dict:
    """Analyze probe *probe* of an R38 trace ``<field>.json`` artifact.

    ``artifact`` has ``{"cycles": [...], "probes": [{values: [...]}, ...]}``.
    Returns the :func:`analyze_series` result with ``probe``/``query``/``node``
    attached.
    """
    cycles = list(artifact.get("cycles", []))
    probes = list(artifact.get("probes", []))
    if not probes:
        return {**_empty(), "probe": int(probe), "query": None, "node": None}
    p = probes[int(probe)]
    res = analyze_series(cycles, p.get("values", []))
    res["probe"] = int(probe)
    res["query"] = p.get("query")
    res["node"] = p.get("node")
    return res


# ── I/O ────────────────────────────────────────────────────────────────────


def write_spectrum(field_name: str, results: Sequence[dict], out_dir: str) -> dict:
    """Write one PSD CSV per probe plus ``summary.json``.

    ``results`` is a list of :func:`analyze_series`-shaped dicts (one per
    probe). Returns the summary manifest; files live under *out_dir*.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in field_name) or "field"
    rows = []
    for i, r in enumerate(results):
        fname = f"{safe}__probe{i}.csv"
        _write_psd_csv(out / fname, r)
        rows.append({
            "probe": i, "file": fname, "n": int(r["n"]),
            "dominant_freq": r["dominant_freq"],
            "dominant_psd": r["dominant_psd"], "nyquist": r["nyquist"],
            "mean": r["mean"], "std": r["std"],
        })
    summary = {"field": field_name, "probes": rows}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def _write_psd_csv(path: Path, r: dict) -> None:
    import csv
    freqs = list(r.get("freq", []))
    psd = list(r.get("psd", []))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# n", r["n"]])
        w.writerow(["# dt", r["dt"]])
        w.writerow(["# nyquist", r["nyquist"]])
        w.writerow(["# dominant_freq", r["dominant_freq"]])
        w.writerow(["# dominant_psd", r["dominant_psd"]])
        w.writerow(["freq", "psd"])
        for fq, pv in zip(freqs, psd):
            w.writerow(["%.9g" % fq, "%.9g" % pv])


# ── CLI ────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.spectrum", description="FlowViewer R41 monitoring-point spectrum")
    ap.add_argument("trace_json", help="R38 trace <field>.json with cycles+probes")
    ap.add_argument("--out", default="spectrum_out")
    ap.add_argument("--probe", type=int, default=None,
                    help="only analyze this probe index (default: all)")
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    probes = list(art.get("probes", []))
    which = [args.probe] if args.probe is not None \
        else list(range(len(probes)))
    results = [spectrum_from_trace(art, i) for i in which]
    field_name = art.get("name") or Path(args.trace_json).stem
    summary = write_spectrum(field_name, results, args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
