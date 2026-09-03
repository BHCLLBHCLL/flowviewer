"""R46: render the per-probe monitoring analysis as a self-contained HTML report.

R45 bundles the spectral family (R41 spectrum, R43 spectrogram trend, R44 modes,
turbulence intensity) behind ``fv.monitor`` as CSV + JSON. R46 turns that into a
**browsable, dependency-free page**: per-probe cards with the key scalars, an
inline bar preview of the power spectrum, and the same cross-probe table from
R45 — all in one HTML string with embedded CSS and no external plotting library
(so it is headless-testable and opens in any browser).

``build_report`` digests an R38 trace artifact; ``render_html`` stringifies it;
``write_monitor_report`` writes ``<field>_monitor.html`` + ``summary.json``; the
CLI accepts either a trace JSON (analyzes first) or an R45 bundle JSON.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Sequence

from .monitor import analyze_monitor
from .spectrum import analyze_series

_MAX_BARS = 32


def _f(v) -> str:
    """Compact number formatting for table cells."""
    if v is None:
        return "–"
    try:
        return f"{float(v):.6g}"
    except (TypeError, ValueError):
        return html.escape(str(v))


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _psd_bars(freq: Sequence, psd: Sequence) -> list:
    """Down-sampled, sqrt-compressed power-spectrum bars in [0, 1]."""
    pos = [i for i, f in enumerate(freq) if float(f) > 0]
    p = [float(psd[i]) for i in pos]
    if not p or max(p) <= 0:
        return []
    pmax = max(p)
    if len(p) > _MAX_BARS:
        step = len(p) / _MAX_BARS
        p = [p[int(i * step)] for i in range(_MAX_BARS)]
    return [float((v / pmax) ** 0.5) for v in p]


# ── report construction ────────────────────────────────────────────────────


def build_report(artifact: dict) -> dict:
    """Digest an R38 trace artifact into a renderable monitoring report."""
    bundle = analyze_monitor(artifact)
    cycles = list(artifact.get("cycles", []))
    probes = list(artifact.get("probes", []))
    cards = []
    for i, p in enumerate(probes):
        spec = analyze_series(cycles, p.get("values", []))
        cards.append({
            "probe": i,
            "query": p.get("query"),
            "node": p.get("node"),
            "dominant_freq": bundle["probes"][i]["spectrum"]["dominant_freq"],
            "nyquist": bundle["probes"][i]["spectrum"]["nyquist"],
            "drift": bundle["probes"][i]["trend"]["drift"],
            "n_peaks": bundle["probes"][i]["modes"]["n_peaks"],
            "top1_share": bundle["probes"][i]["modes"]["top1_share"],
            "ti_pct": bundle["probes"][i]["intensity"]["ti_pct"],
            "psd_bars": _psd_bars(spec.get("freq", []), spec.get("psd", [])),
        })
    return {"field": bundle.get("field") or "", "n_probes": len(cards),
            "cards": cards}


# ── HTML render ────────────────────────────────────────────────────────────


def render_html(report: dict) -> str:
    """A self-contained, dependency-free HTML document for ``report``."""
    field = _esc(report.get("field"))
    cards = report.get("cards", [])
    header = f"<h1>Monitoring report — {field}</h1>"
    if not cards:
        return _DOC_TEMPLATE.replace("__TITLE__", field).replace(
            "__HEADER__", header).replace(
            "__SUMMARY__", "<p>No probes.</p>", 1).replace("__CARDS__", "")

    # cross-probe summary table
    rows = ["<tr><th>probe</th><th>node</th><th>query</th>"
            "<th>dominant&nbsp;freq</th><th>nyquist</th><th>drift</th>"
            "<th>n&nbsp;peaks</th><th>top1&nbsp;share</th><th>ti&nbsp;%</th></tr>"]
    for c in cards:
        q = ",".join(_f(v) for v in c["query"]) if c.get("query") else "–"
        rows.append(
            f"<tr><td>{c['probe']}</td><td>{_f(c['node'])}</td><td>{_esc(q)}"
            f"</td><td>{_f(c['dominant_freq'])}</td><td>{_f(c['nyquist'])}"
            f"</td><td>{_f(c['drift'])}</td><td>{c['n_peaks']}</td>"
            f"<td>{_f(c['top1_share'])}</td><td>{_f(c['ti_pct'])}</td></tr>")
    summary_html = ("<table>" + "".join(rows) + "</table>")

    # per-probe cards with inline PSD bars
    cards_html = []
    for c in cards:
        q = _esc(",".join(_f(v) for v in c["query"])) if c.get("query") else "–"
        bars = "".join(
            f"<span class=\"bar\" style=\"height:{max(2.0, v*100):.1f}%\"></span>"
            for v in c["psd_bars"])
        if not bars:
            bars = "<span class=\"empty\">no finite spectrum</span>"
        cards_html.append(
            f"<div class=\"card\"><h2>Probe {c['probe']} @ {q}</h2>"
            f"<table><tr><th>dominant freq</th><td>{_f(c['dominant_freq'])}"
            f"</td><th>trend drift</th><td>{_f(c['drift'])}</td></tr>"
            f"<tr><th>nyquist</th><td>{_f(c['nyquist'])}</td>"
            f"<th>modes (peaks)</th><td>{c['n_peaks']}</td></tr>"
            f"<tr><th>top-1 energy share</th><td>{_f(c['top1_share'])}</td>"
            f"<th>turbulence intensity</th><td>{_f(c['ti_pct'])}%</td></tr>"
            f"</table><div class=\"spectro\">{bars}</div></div>")
    cards_html = "".join(cards_html)

    return (_DOC_TEMPLATE.replace("__TITLE__", field)
            .replace("__HEADER__", header)
            .replace("__SUMMARY__", summary_html, 1)
            .replace("__CARDS__", cards_html))


_DOC_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Monitoring — __TITLE__</title><style>
  body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a}
  h1{font-size:22px}h2{font-size:16px;margin:0 0 8px}
  table{border-collapse:collapse;margin:8px 0 20px}
  th,td{border:1px solid #d0d0d0;padding:4px 10px;font-size:13px;text-align:right}
  th{background:#f4f4f4;text-align:left}td:first-child{text-align:left}
  .card{border:1px solid #e0e0e0;border-radius:8px;padding:14px;margin:12px 0}
  .spectro{display:flex;align-items:flex-end;height:90px;margin-top:10px;
    border-bottom:1px solid #ccc;gap:1px}
  .bar{flex:1;background:#2c6fd0;min-width:2px}
  .empty{color:#999;font-size:12px}
</style></head><body>
__HEADER__<h2>Summary</h2>__SUMMARY__<h2>Per probe</h2>__CARDS__
</body></html>"""


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_monitor_report(artifact: dict, out_dir: str) -> dict:
    """Render + write ``<field>_monitor.html`` and ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = build_report(artifact)
    field = report.get("field") or "field"
    safe = "".join(ch if ch.isalnum() else "_" for ch in field) or "field"
    html_path = out / f"{safe}_monitor.html"
    html_path.write_text(render_html(report), encoding="utf-8")
    summary = {"field": field, "file": html_path.name,
               "n_probes": report.get("n_probes"),
               "cards": report.get("cards")}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.monreport",
        description="FlowViewer R46 render per-probe monitoring analysis to HTML")
    ap.add_argument("input_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("--out", default="monreport_out")
    args = ap.parse_args(argv)
    with open(args.input_json, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "cycles" not in data or "probes" not in data:
        print("error: input_json must be an R38 trace artifact (cycles + probes)",
              file=__import__("sys").stderr)
        return 2
    summary = write_monitor_report(data, args.out)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
