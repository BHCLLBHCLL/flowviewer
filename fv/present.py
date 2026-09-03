"""R36: multi-cycle temporal report (Sequence -> offline report bundle).

Caps the R31->R35 automation stack: ``sequence_report`` walks an R34
:class:`fv.session.SessionTimeline` (each cycle opened as an R31 streaming
handle), scans every field in bounded tiles, and assembles a **self-contained
offline deliverable** per cycle:

* ``report.html`` — dependency-free (embedded base64 PNG thumbnails when a
  ``snapshot`` callback provides them; per-cycle per-variable stats with a
  delta-from-baseline column), sibling to the R32 web report but *temporal*
  (across cycles, not one dataset).
* ``data.csv`` — one row per (cycle, variable): name / n / min / max / sample
  head, machine-readable and diff-friendly across runs.
* ``manifest.json`` — the run recipe + per-cycle summary.

The pure assembly path (:func:`report_from_cycles`) has no VTK/h5py/GUI
dependency, so it is deterministically headless-testable; the sequence walk is
a thin adapter over existing streaming/session primitives.
"""

from __future__ import annotations

import base64
import csv
import json
import os
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from .session import SessionTimeline

# ── bounded per-field stats (mirrors fv/web/report._field_stats) ───────────

def field_stats(handle, name: str, embed_window: int = 256) -> dict:
    """Scan a stream handle field in bounded tiles -> {n,min,max,sample}."""
    total = int(handle.field_len(name))
    vmin = float("+inf")
    vmax = float("-inf")
    sample: list = []
    for _start, arr in handle.iter_tiles(name):
        a = np.asarray(arr, dtype=np.float64).ravel()
        if a.size == 0:
            continue
        good = a[np.isfinite(a)]
        if good.size:
            vmin = min(vmin, float(good.min()))
            vmax = max(vmax, float(good.max()))
        if len(sample) < embed_window:
            need = embed_window - len(sample)
            sample.extend(float(x) for x in a[:need].tolist())
    if not np.isfinite(vmin) or vmin > vmax:
        vmin, vmax = 0.0, 0.0
    return {"n": total, "min": float(vmin), "max": float(vmax),
            "sample": sample}


def cycle_report(handle, name: str = "", embed_window: int = 256) -> dict:
    """Bundle stats for every field of a stream handle (per cycle)."""
    vars_out = {}
    for fname in handle.field_names():
        vars_out[fname] = field_stats(handle, fname, embed_window)
    return {"name": name or getattr(handle, "path", ""), "vars": vars_out}


# ── pure HTML / CSV / manifest assembly (headless-testable) ────────────────

_CYCLE_MARK = "__FV36_CYCLES__"
_TITLE_MARK = "__FV36_TITLE__"

_HTML_TMPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FlowViewer R36 Sequence Report</title>
<style>
  :root { --fg:#1a2233; --mut:#5b6b82; --acc:#2f6fed; --line:#e3e8f0; --up:#c0392b; }
  * { box-sizing:border-box; }
  body { margin:28px auto; max-width:1000px; padding:0 16px;
         font:14px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif; color:var(--fg); }
  h1 { font-size:20px; }
  .meta { color:var(--mut); font-size:12px; margin:4px 0 20px; }
  .cycle { border:1px solid var(--line); border-radius:10px; padding:14px;
           margin:18px 0; }
  .cycle h2 { font-size:14px; margin:0 0 4px; }
  .cycle .sub { color:var(--mut); font-size:12px; margin-bottom:10px; }
  .thumbs { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px; }
  .thumbs img { height:90px; border:1px solid var(--line); border-radius:6px; }
  table { border-collapse:collapse; width:100%; font-size:12px; }
  th, td { border-bottom:1px solid var(--line); padding:4px 8px;
           text-align:right; font-variant-numeric:tabular-nums; }
  th { color:var(--mut); font-weight:600; }
  td.left, th.left { text-align:left; }
  .up { color:var(--up); }
</style>
</head>
<body>
<h1>FlowViewer — R36 Sequence Report</h1>
<div class="meta">__FV36_TITLE__</div>
__FV36_CYCLES__
</body>
</html>
"""


def _b64_data_uri(path) -> Optional[str]:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if not data:
        return None
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _cycle_html(cyc: dict, baseline_vars: dict, embed: bool) -> str:
    name = cyc.get("name") or f"cycle {cyc.get('cycle', '?')}"
    parts = [f"<div class='cycle'><h2>Cycle {cyc.get('cycle', '?')}</h2>"]
    parts.append(f"<div class='sub'>{_html_escape(str(name))}</div>")
    png_path = cyc.get("png")
    if embed and png_path:
        uri = _b64_data_uri(png_path)
        if uri:
            parts.append(f"<div class='thumbs'><img src='{uri}' alt='cycle'></div>")
    vars_map = cyc.get("vars") or {}
    if vars_map:
        parts.append(
            "<table><thead><tr><th class='left'>variable</th>"
            "<th>n</th><th>min</th><th>max</th><th>Δ from base</th>"
            "<th class='left'>sample head</th></tr></thead><tbody>")
        for vname in sorted(vars_map):
            s = vars_map[vname]
            base = baseline_vars.get(vname)
            delta = ""
            if base and base.get("min") is not None and s.get("min") is not None:
                d = float(s["min"]) - float(base["min"])
                delta = f"<span class='up'>{d:+.4g}</span>"
            head = ", ".join(f"{x:.4g}" for x in (s.get("sample") or [])[:4])
            parts.append(
                f"<tr><td class='left'>{_html_escape(vname)}</td>"
                f"<td>{s.get('n', 0)}</td><td>{s.get('min', 0):.6g}</td>"
                f"<td>{s.get('max', 0):.6g}</td><td>{delta}</td>"
                f"<td class='left'>{_html_escape(head)}</td></tr>")
        parts.append("</tbody></table>")
    parts.append("</div>")
    return "".join(parts)


def _html_escape(text) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def report_from_cycles(cycles: List[dict], out_dir: str, *,
                       html: bool = True, csv_out: bool = True,
                       title: str = "") -> dict:
    """Assemble report.html / data.csv / manifest.json from cycle dicts.

    ``cycles`` entries: ``{cycle, name, vars:{name:{n,min,max,sample}},
    png?}``.  Pure (no VTK/h5py); returns the manifest.  ``write_html`` embeds
    PNG thumbnails only when ``cyc['png']`` paths exist.
    """
    os.makedirs(out_dir, exist_ok=True)
    baseline = {}
    for cyc in cycles:
        for vname, s in (cyc.get("vars") or {}).items():
            baseline.setdefault(vname, s)

    # CSV — one row per (cycle, variable)
    csv_path = os.path.join(out_dir, "data.csv")
    if csv_out:
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["cycle", "name", "variable", "n", "min", "max",
                        "sample_head"])
            for cyc in cycles:
                for vname in sorted((cyc.get("vars") or {})):
                    s = cyc["vars"][vname]
                    head = ", ".join(f"{x:.4g}"
                                     for x in (s.get("sample") or [])[:4])
                    w.writerow([cyc.get("cycle"), cyc.get("name"),
                                vname, s.get("n", 0),
                                f"{s.get('min', 0):.6g}",
                                f"{s.get('max', 0):.6g}", head])

    html_path = os.path.join(out_dir, "report.html")
    if html:
        body = "\n".join(_cycle_html(c, baseline, embed=True) for c in cycles)
        doc = _HTML_TMPL.replace(_TITLE_MARK,
                                 _html_escape(title or
                                              f"{len(cycles)} cycle(s)"))
        doc = doc.replace(_CYCLE_MARK, body)
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(doc)

    manifest = {"cycles": [],
                "n_cycles": len(cycles),
                "report": os.path.basename(html_path) if html else None,
                "csv": os.path.basename(csv_path) if csv_out else None}
    for cyc in cycles:
        entry = {"cycle": cyc.get("cycle"),
                 "name": cyc.get("name"),
                 "variables": sorted(cyc.get("vars") or {})}
        if cyc.get("png"):
            entry["png"] = os.path.basename(cyc["png"])
        manifest["cycles"].append(entry)
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


# ── sequence walk ──────────────────────────────────────────────────────────

def sequence_report(paths, out_dir: str, *, window_len: int = 256,
                    budget_mb: int = 64,
                    snapshot: Optional[Callable[[int], Optional[str]]] = None,
                    html: bool = True, csv_out: bool = True,
                    title: str = "") -> dict:
    """Walk a session sequence and emit the offline report bundle.

    ``paths`` is either a list of cycle CGNS paths or a single first file
    (globbed into a cycle sequence via ``fv.session``).  Each cycle is opened
    as an R31 streaming handle (one resident at a time, bounded memory:
    per-cycle RSS ~= budget_mb LRU + field scan window).  ``snapshot(cycle)``
    may return a PNG path for thumbnail embedding; None skips the image.
    """
    if isinstance(paths, (str, os.PathLike)):
        tl = SessionTimeline.from_sequence(str(paths), budget_mb=budget_mb)
    else:
        tl = SessionTimeline(list(paths), budget_mb=budget_mb)

    cycles: List[dict] = []
    for cycle, handle, _mesh in tl:
        rep = cycle_report(handle, name=f"cycle {cycle}",
                           embed_window=int(window_len))
        entry: dict = {"cycle": cycle, "name": rep["name"],
                       "vars": rep["vars"]}
        if snapshot is not None:
            png = snapshot(cycle)
            if png:
                entry["png"] = png
        cycles.append(entry)
    return report_from_cycles(cycles, out_dir, html=html, csv_out=csv_out,
                              title=title)


# ── CLI ────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        prog="python -m fv.present",
        description="R36: walk a CGNS cycle sequence into an offline "
                    "report bundle (report.html + data.csv + manifest.json).")
    p.add_argument("source", help="first cycle file (or comma list of files)")
    p.add_argument("--out", default="present_out", help="output directory")
    p.add_argument("--window", type=int, default=256,
                   help="per-field sample window baked into the report")
    p.add_argument("--budget-mb", type=int, default=64,
                   help="streaming LRU budget per dataset (MB)")
    p.add_argument("--no-html", action="store_true", help="skip report.html")
    p.add_argument("--no-csv", action="store_true", help="skip data.csv")
    p.add_argument("--title", default="", help="report title")
    args = p.parse_args(argv)

    paths = [x.strip() for x in args.source.split(",") if x.strip()]
    first = paths[0] if len(paths) == 1 else paths
    manifest = sequence_report(
        first, args.out, window_len=args.window, budget_mb=args.budget_mb,
        html=not args.no_html, csv_out=not args.no_csv, title=args.title)
    print(json.dumps({"ok": True, "n_cycles": manifest["n_cycles"],
                      "out": args.out}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
