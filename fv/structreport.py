"""R51: render the structural / modal analysis as a self-contained HTML report.

R47–R50 built the *structural* family — cross-probe correlation + clustering
(R47), POD (R48/R49) and DMD (R50) — but each only writes JSON/CSV. R51 turns
the whole family into one **browsable, dependency-free page** (the structural
counterpart of R46's spectral ``fv.monreport``):

* an inline **correlation heat-map** (per-pair ``rho`` colour-coded red→white→blue),
* the **coherent groups** from single-linkage clustering,
* the **POD energy spectrum** as horizontal bars,
* a **DMD modes** table (frequency, growth rate, amplitude, energy share).

Pure Python (embedded CSS, no plotting library), headless-testable; reuses
R47/R48/R50 on the same R38 trace artifact.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from .dmd import dmd_decompose
from .pod import pod_decompose
from .probecorr import probe_corr_summary


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _f(v) -> str:
    if v is None:
        return "–"
    try:
        return f"{float(v):.6g}"
    except (TypeError, ValueError):
        return _esc(v)


def _rho_color(rho: float) -> str:
    """Map a correlation in [-1, 1] to a heat-map background (None → white)."""
    if rho is None:
        return "#ffffff"
    t = abs(float(rho))
    t = min(1.0, t)
    if rho < 0:
        return f"rgb({int(255*t)}, {int(255*(1-t))}, {int(255*(1-t))})"
    return f"rgb({int(255*(1-t))}, {int(255*(1-t))}, {int(255*t)})"


# ── report construction ────────────────────────────────────────────────────


def build_structure_report(artifact: dict, *, corr_threshold: float = 0.8,
                           top: int = 5, pod_modes=None,
                           dmd_r=None, embed_d=None) -> dict:
    """Digest an R38 trace artifact into a structural report."""
    corr = probe_corr_summary(artifact, threshold=corr_threshold, top=top)
    pod = pod_decompose(artifact, n_modes=pod_modes)
    dmd = dmd_decompose(artifact, r=dmd_r, embed_d=embed_d)
    return {
        "field": artifact.get("name") or "",
        "n_probes": len(list(artifact.get("probes", []))),
        "n_cycles": len(list(artifact.get("cycles", []))),
        "corr": {"matrix": corr["matrix"], "threshold": corr["threshold"],
                 "coherent_groups": corr["coherent_groups"],
                 "top_pairs": corr["top_pairs"]},
        "pod": {"n_modes": pod["n_modes"],
                "energy_shares": pod["energy_shares"],
                "cum_energy": pod["cum_energy"]},
        "dmd": {"modes": dmd["modes"], "dominant": dmd["dominant"],
                "r": dmd["r"]},
    }


# ── HTML render ────────────────────────────────────────────────────────────


def render_html(report: dict) -> str:
    """A self-contained HTML document for a structural report."""
    field = _esc(report.get("field"))
    header = f"<h1>Structure report — {field}</h1>"
    if not report.get("n_probes"):
        return _DOC_TEMPLATE.replace("__TITLE__", field).replace(
            "__HEADER__", header, 1).replace("__SUMMARY__",
            "<p>No probes.</p>", 1).replace("__BODY__", "")

    dmd_dom = report["dmd"]["dominant"]
    pod_shares = report["pod"].get("energy_shares", [])
    summary_rows = [
        ("probes", report["n_probes"]), ("cycles", report["n_cycles"]),
        ("correlation threshold", report["corr"]["threshold"]),
        ("coherent groups", len(report["corr"]["coherent_groups"])),
        ("POD modes", report["pod"]["n_modes"]),
        ("POD top-1 energy", pod_shares[0] if pod_shares else None),
        ("DMD modes", report["dmd"]["r"]),
        ("DMD dominant freq", (dmd_dom or {}).get("freq")),
        ("DMD dominant growth", (dmd_dom or {}).get("growth")),
    ]
    summary_html = "<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
        for k, v in summary_rows) + "</table>"

    # correlation heat-map
    matrix = report["corr"]["matrix"]
    n = len(matrix)
    cells = []
    for i in range(n):
        row = []
        for j in range(n):
            v = matrix[i][j]
            if v is None:
                row.append('<td class="nan"></td>')
            else:
                row.append(f'<td class="c" style="background:{_rho_color(v)}" '
                           f'title="rho({i},{j})={float(v):.3f}">{float(v):.2f}'
                           f"</td>")
        cells.append("<tr>" + "".join(row) + "</tr>")
    corr_html = ("<table class=\"heat\">" + "".join(cells) + "</table>")

    # coherent groups + top pairs
    groups = report["corr"]["coherent_groups"]
    if groups:
        group_html = "<ul>" + "".join(
            f"<li>group: {_esc(', '.join(str(m) for m in g['members']))}</li>"
            for g in groups) + "</ul>"
    else:
        group_html = "<p>No coherent groups at this threshold.</p>"
    pairs = report["corr"]["top_pairs"]
    pairs_html = ("<table><tr><th>i</th><th>j</th><th>rho</th></tr>" + "".join(
        f"<tr><td>{p['i']}</td><td>{p['j']}</td><td>{_f(p['rho'])}</td></tr>"
        for p in pairs) + "</table>") if pairs else "<p>—</p>"

    # POD energy spectrum bars
    if pod_shares:
        pod_html = "".join(
            f'<div class="bar"><span class="lab">m{i}</span>'
            f'<span class="fill" style="width:{max(1.0, float(s)*100):.1f}%">'
            f'</span><span class="pct">{float(s)*100:.1f}%</span></div>'
            for i, s in enumerate(pod_shares))
    else:
        pod_html = "<p>No POD modes.</p>"

    # DMD modes table
    dmd_modes = report["dmd"]["modes"]
    dmd_html = ("<table><tr><th>i</th><th>freq</th><th>growth</th>"
                "<th>amplitude</th><th>share</th></tr>" + "".join(
        f"<tr><td>{m['i']}</td><td>{_f(m['freq'])}</td>"
        f"<td>{_f(m['growth'])}</td><td>{_f(m['amplitude'])}</td>"
        f"<td>{_f(m['share'])}</td></tr>" for m in dmd_modes)
        + "</table>") if dmd_modes else "<p>No DMD modes.</p>"

    body = (
        "<h2>Summary</h2>" + summary_html +
        "<h2>Correlation</h2>" + corr_html +
        "<h2>Coherent groups</h2>" + group_html +
        "<h2>Strongest pairs</h2>" + pairs_html +
        "<h2>POD energy</h2>" + pod_html +
        "<h2>DMD modes</h2>" + dmd_html)

    return (_DOC_TEMPLATE.replace("__TITLE__", field)
            .replace("__HEADER__", header, 1)
            .replace("__SUMMARY__", "", 1)
            .replace("__BODY__", body, 1))


_DOC_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Structure — __TITLE__</title><style>
  body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a}
  h1{font-size:22px}h2{font-size:16px;margin:22px 0 8px}
  table{border-collapse:collapse;margin:6px 0}
  th,td{border:1px solid #d0d0d0;padding:4px 10px;font-size:13px;text-align:right}
  th{background:#f4f4f4;text-align:left}
  table.heat td{padding:2px 6px;text-align:center;font-size:11px;min-width:34px}
  table.heat td.nan{background:#fff;border:1px solid #eee}
  .bar{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:13px}
  .lab{width:34px;color:#888}.pct{width:70px;color:#888;text-align:right}
  .fill{display:inline-block;height:14px;background:#2c6fd0;border-radius:3px}
</style></head><body>
__HEADER____SUMMARY____BODY__
</body></html>"""


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_structure_report(artifact: dict, out_dir: str, *, field: str = "",
                           corr_threshold: float = 0.8, pod_modes=None,
                           dmd_r=None, embed_d=None) -> dict:
    """Render + write ``<field>_struct.html`` and ``summary.json``."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = build_structure_report(
        artifact, corr_threshold=corr_threshold, pod_modes=pod_modes,
        dmd_r=dmd_r, embed_d=embed_d)
    name = field or report.get("field") or "field"
    safe = "".join(ch if ch.isalnum() else "_" for ch in name) or "field"
    html_path = out / f"{safe}_struct.html"
    html_path.write_text(render_html(report), encoding="utf-8")
    dmd_dom = report["dmd"]["dominant"]
    pod_shares = report["pod"].get("energy_shares", [])
    top = {"field": name, "file": html_path.name,
           "n_probes": report["n_probes"], "n_cycles": report["n_cycles"],
           "n_coherent_groups": len(report["corr"]["coherent_groups"]),
           "pod_top1_share": pod_shares[0] if pod_shares else None,
           "dmd_r": report["dmd"]["r"],
           "dmd_dominant_freq": (dmd_dom or {}).get("freq"),
           "dmd_dominant_growth": (dmd_dom or {}).get("growth")}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(top, fh, indent=2)
    return top


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.structreport",
        description="FlowViewer R51 structural / modal analysis HTML report")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("--out", default="structreport_out")
    ap.add_argument("--corr-threshold", type=float, default=0.8)
    ap.add_argument("--pod-modes", type=int, default=None)
    ap.add_argument("--dmd-r", type=int, default=None)
    ap.add_argument("--embed-d", type=int, default=None)
    args = ap.parse_args(argv)
    with open(args.trace_json, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    if "probes" not in art:
        print("error: trace_json must contain 'probes'",
              file=__import__("sys").stderr)
        return 2
    top = write_structure_report(art, args.out,
                                 corr_threshold=args.corr_threshold,
                                 pod_modes=args.pod_modes,
                                 dmd_r=args.dmd_r, embed_d=args.embed_d)
    print(json.dumps(top, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
