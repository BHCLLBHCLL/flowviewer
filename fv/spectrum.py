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
    # R113 convention.  What the old code called "psd" is a periodogram
    # POWER per bin: |S|^2 / n.  The number is right (for A*sin(2*pi*f*t) the
    # peak bin is exactly A^2*n/4, so sum(power) == var*n/2 and
    # A = sqrt(4*power_peak/n) recovers A exactly), but the name promised a
    # density and the scaling was undocumented, so cross-record comparisons
    # silently did not line up.  Both readings are now reported explicitly:
    #   power   -- |S|^2/n, the raw per-bin power (unchanged, so existing
    #              consumers and stored reports keep their numbers)
    #   density -- power / (n*df), the one-sided power spectral DENSITY, so
    #              sum(density) * df == variance and levels compare across
    #              record lengths regardless of n
    #   psd     -- kept as an alias of power (the historical meaning), because
    #              the mode/energy-share consumers treat it as relative bin
    #              energy and only ratios matter to them
    #   amplitude -- sqrt(2 * power * 2 / n) for the interior bins, the
    #              amplitude of the sinusoid at that frequency;
    #              sqrt(2*2*power/n) reproduces A for an exact-bin tone
    power = (np.abs(S) ** 2) / n
    df = float(freqs[1] - freqs[0]) if freqs.size > 1 else 0.0
    # A one-sided density must satisfy sum(density) * df == variance.  power
    # is |S|^2/n, whose sum over the full two-sided spectrum is var*n; the
    # one-sided rfft already carries the mirror energy, so the density is
    # power / (n * df).
    density = 2.0 * power / (n * df) if df > 0 else np.zeros_like(power)
    psd = power
    amp = np.zeros_like(power)
    if power.size:
        interior = np.zeros(power.size, dtype=bool)
        interior[1:] = True
        if n % 2 == 0 and power.size:
            interior[-1] = False          # Nyquist bin is not a sinusoid
        amp[interior] = np.sqrt(2.0 * power[interior] * 2.0 / n)
    nyquist = float(0.5 / dt)
    pos = np.flatnonzero(freqs > 0)
    dom_freq = 0.0
    dom_power = 0.0
    dom_amp = 0.0
    dom_density = 0.0
    if pos.size:
        i = int(pos[np.argmax(power[pos])])
        dom_freq = float(freqs[i])
        dom_power = float(power[i])
        dom_amp = float(amp[i])
        dom_density = float(density[i])
    total_power = float(power.sum())
    return {
        "n": n, "dt": dt, "ymin": float(v.min()), "ymax": float(v.max()),
        "mean": mean, "std": float(det.std(ddof=1)) if n > 1 else 0.0,
        "nyquist": nyquist, "dominant_freq": dom_freq,
        "dominant_psd": dom_power, "dominant_density": dom_density,
        "dominant_amplitude": dom_amp, "df": df,
        "total_power": total_power,
        # sum(power) == var*n/2; sum(psd)*df == var
        "power": [float(x) for x in power],
        "amplitude": [float(x) for x in amp],
        "density": [float(x) for x in density],
        "dc_energy": float(mean ** 2),
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
