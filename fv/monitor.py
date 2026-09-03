"""R45: one-command monitoring-point analysis bundle per probe.

The spectral family (R41 spectrum, R43 spectrogram, R44 modes) plus a cheap
turbulence-intensity measure are run together over an R38 trace artifact so a
single call yields everything one needs to a "monitoring card" for each probe:

* ``analyze_probe`` — fuses spectrum (dominant freq/Nyquist/energy),
  spectrogram trend (drift / fastest / slowest), mode decomposition (n_peaks,
  dominant, top-1 energy share) and turbulent intensity into one dict.
* ``analyze_monitor`` — the same for every probe, plus a manifest.
* ``write_monitor`` — a per-probe CSV table (all probes × key scalars), the
  bundle JSON and ``summary.json``.

All numbers come from the existing, tested pure-NumPy modules, so the bundle is
headless, dependency-light, and no CGNS/vtk code is touched.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .modes import modes_from_spectrum, turbulent_intensity
from .spectro import freq_evolution, spectrogram_from_trace
from .spectrum import analyze_series


def analyze_probe(artifact: dict, probe: int = 0) -> dict:
    """One probe's full spectral/modal/intensity analysis card."""
    cycles = list(artifact.get("cycles", []))
    probes = list(artifact.get("probes", []))
    if not probes:
        return {"probe": int(probe), "query": None, "node": None,
                "spectrum": {}, "trend": {}, "modes": {}, "intensity": {}}
    p = probes[int(probe)]
    values = list(p.get("values", []))
    spec = analyze_series(cycles, values)
    modes = modes_from_spectrum(spec)
    specro = spectrogram_from_trace(artifact, int(probe))
    ev = freq_evolution(specro) if isinstance(specro, dict) else {}
    dom = modes.get("dominant") or {}
    es = modes.get("organized", {})
    top1 = es.get("peaks", [{}])[0].get("share") if es.get("peaks") else None
    return {
        "probe": int(probe),
        "query": p.get("query"),
        "node": p.get("node"),
        "spectrum": {
            "n": spec.get("n"), "dominant_freq": spec.get("dominant_freq"),
            "dominant_psd": spec.get("dominant_psd"),
            "nyquist": spec.get("nyquist"),
        },
        "trend": {
            "nw": specro.get("nw", 0),
            "drift": ev.get("drift"),
            "fastest": ev.get("fastest"),
            "slowest": ev.get("slowest"),
        },
        "modes": {
            "n_peaks": es.get("n_peaks", 0),
            "dominant_freq": dom.get("freq"),
            "top1_share": top1,
        },
        "intensity": {"ti_pct": turbulent_intensity(values).get("ti_pct")},
    }


def analyze_monitor(artifact: dict) -> dict:
    """Analyze every probe of an R38 trace artifact."""
    probes = list(artifact.get("probes", []))
    cards = [analyze_probe(artifact, i) for i in range(len(probes))]
    return {"field": artifact.get("name"), "probes": cards,
            "n_probes": len(cards)}


# ── I/O ────────────────────────────────────────────────────────────────────


def write_monitor(bundle: dict, out_dir: str) -> dict:
    """Write ``<field>_monitor.csv``, ``<field>_monitor.json``, ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_"
                   for ch in (bundle.get("field") or "field")) or "field"
    csv_path = out / f"{safe}_monitor.csv"
    rows = []
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["probe", "node", "query", "dominant_freq", "nyquist",
                    "drift", "n_peaks", "top1_share", "ti_pct"])
        for c in bundle["probes"]:
            spec = c["spectrum"]
            trend = c["trend"]
            modes = c["modes"]
            intensity = c["intensity"]
            row = [str(c["probe"]), c["node"],
                   ",".join(f"{v:.6g}" for v in (c["query"] or []))
                   if c["query"] else "",
                   spec.get("dominant_freq"), spec.get("nyquist"),
                   trend.get("drift"), modes.get("n_peaks"),
                   modes.get("top1_share"), intensity.get("ti_pct")]
            w.writerow(row)
            rows.append(dict(zip(["probe", "node", "query", "dominant_freq",
                                  "nyquist", "drift", "n_peaks", "top1_share",
                                  "ti_pct"], row)))
    bundle_path = out / f"{safe}_monitor.json"
    with open(bundle_path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, indent=2)
    summary = {"field": bundle.get("field"), "file": bundle_path.name,
               "csv": csv_path.name, "n_probes": bundle.get("n_probes"),
               "probes": rows}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.monitor",
        description="FlowViewer R45 per-probe monitoring analysis bundle")
    ap.add_argument("trace_json", help="R38 trace <field>.json with cycles+probes")
    ap.add_argument("--out", default="monitor_out")
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    bundle = analyze_monitor(art)
    if bundle["field"] is None:
        bundle["field"] = Path(args.trace_json).stem
    summary = write_monitor(bundle, args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
