"""R61: unified spectral-field console (Spectral / Coherence / Evolution).

R58 (single-point spectral maps), R59 (coherence field) and R60 (spectral
evolution / non-stationarity) each emit their own HTML field report. R61 folds
them into one **single-page tabbed console**: a dependency-free HTML page with a
summary header and per-panel tabs (Spectral / Coherence / Evolution), each panel
showing its four <canvas> heatmaps plus per-map statistics, painted by one
shared inline JS. Same "integration round" spirit as R54 (POD spatial report) and
R51 (probe family) — the console keeps three recently-added field dimensions
side-by-side for cross-comparison.

Pure NumPy + standard HTML/CSS/JS, headless. Reuses R58 ``build_spectral_report``,
R59 ``build_coherence_report`` and R60 ``build_spectevol_report`` (which share the
maps/stats/previews/meta layout and draw-JS semantics), plus ``binned_preview``
previews and ``_safe``/``_esc``/``_grid_range``/``_f``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from .coherencemap import build_coherence_report
from .spatialanim import _f, _safe
from .spectevol import build_spectevol_report
from .spectralmap import _esc, _field_js, _grid_range, _probes_xy, build_spectral_report

PANEL_SPEC = {
    "spectral": {
        "title": "Spectral (R58)",
        "maps": [("mean", "Time-mean field"), ("rms", "Fluctuation RMS"),
                 ("intensity", "Intensity rms/|mean|"),
                 ("freq", "Dominant frequency (Hz)")],
    },
    "coherence": {
        "title": "Coherence (R59)",
        "maps": [("peak_coherence", "Peak coherence"),
                 ("peak_freq", "Peak-coherence freq (Hz)"),
                 ("mean_coherence", "Mean coherence (f>0)"),
                 ("phase", "Cross phase at peak (rad)")],
    },
    "spectevol": {
        "title": "Evolution (R60)",
        "maps": [("centroid", "Spectral centroid (Hz)"),
                 ("bandwidth", "Spectral bandwidth (Hz)"),
                 ("drift", "Centroid drift (Hz)"),
                 ("intermittency", "Energy intermittency")],
    },
}


def build_console(verts: np.ndarray, artifact: dict, *,
                  panels=("spectral", "coherence", "spectevol"),
                  ref_probe: int = 0, cycles=None, step: int = 1, frames=None,
                  k=None, p: float = 2.0, neighbors: int = 4,
                  source: str = "pod", preview: int = 24, nperseg=None,
                  dt=None) -> dict:
    """Build a tabbed console over ``panels`` of field reports (see PANEL_SPEC)."""
    v = np.asarray(verts, dtype=np.float64)
    field = artifact.get("name") or ""
    probes = list(artifact.get("probes", []))
    selected = tuple(n for n in panels if n in PANEL_SPEC)
    if v.shape[0]:
        ex = {"xmin": float(v[:, 0].min()), "xmax": float(v[:, 0].max()),
              "ymin": float(v[:, 1].min()), "ymax": float(v[:, 1].max())}
    else:
        ex = {"xmin": None, "xmax": None, "ymin": None, "ymax": None}
    console = {"kind": "fieldconsole", "field": field, "source": source,
               "n_probes": len(probes),
               "n_cycles": int(len(list(artifact.get("cycles", [])))),
               "n_vertices": v.shape[0], "k": int(k) if k else None,
               "p": float(p), "neighbors": int(neighbors),
               "probes_xy": _probes_xy(probes), "extent": ex,
               "preview": int(preview), "panels": {}, "panel_order": list(selected)}
    common = dict(cycles=cycles, step=step, frames=frames, k=k, p=p,
                  neighbors=neighbors, source=source, preview=preview, dt=dt)
    for name in selected:
        if name == "spectral":
            rep = build_spectral_report(v, artifact, **common)
        elif name == "coherence":
            rep = build_coherence_report(v, artifact, ref_probe=ref_probe,
                                         nperseg=nperseg, **common)
        else:  # spectevol
            rep = build_spectevol_report(v, artifact, nperseg=nperseg, **common)
        console["panels"][name] = {
            "meta": {"n_frames": rep.get("n_frames", 0),
                     "n_vertices": rep.get("n_vertices", 0),
                     "dt": rep.get("dt"), "nyquist": rep.get("nyquist"),
                     "stats": rep.get("stats", {})},
            "stats": rep.get("stats", {}),
            "previews": rep.get("previews", {}),
        }
    return console


def render_html(console: dict) -> str:
    field = _esc(console.get("field"))
    header = f"<h1>Field console — {field}</h1>"
    if not console.get("panel_order") or not console.get("n_probes"):
        return (_DOC.replace("__TITLE__", field)
                .replace("__HEADER__", header, 1)
                .replace("__BODY__", "<p>No data.</p>", 1))
    order = [n for n in console["panel_order"] if n in console.get("panels", {})]
    if not order:
        return (_DOC.replace("__TITLE__", field)
                .replace("__HEADER__", header, 1)
                .replace("__BODY__", "<p>No data.</p>", 1))

    summ = [("field", console["field"]), ("source", console["source"]),
            ("probes", console["n_probes"]), ("cycles", console["n_cycles"]),
            ("vertices", console["n_vertices"]), ("k", console["k"]),
            ("p", console["p"]), ("neighbors", console["neighbors"]),
            ("preview grid", f"{console['preview']}×{console['preview']}")]
    tabs = "<div class='tabs'>" + "".join(
        f"<button class='tbtn{' active' if i == 0 else ''}' "
        f"data-pan='{n}'>{_esc(PANEL_SPEC[n]['title'])}</button>"
        for i, n in enumerate(order)) + "</div>"

    g = max(4, int(console["preview"]))
    sections = ""
    pan_js = {}
    for i, n in enumerate(order):
        pane = console["panels"][n]
        spec = PANEL_SPEC[n]
        prevs = pane.get("previews", {})
        maps_js = {m: [[None if v != v else float(v) for v in row]
                       for row in prevs.get(m, [])] for m, _ in spec["maps"]}
        vm_js = {m: list(_grid_range(prevs.get(m, []))) for m, _ in spec["maps"]}
        pan_js[n] = {"maps": maps_js, "vm": vm_js,
                     "names": [m for m, _ in spec["maps"]]}
        rows = ""
        for m, title in spec["maps"]:
            st = pane["stats"].get(m, {})
            rows += (f"<h3>{_esc(title)}</h3>" +
                     "<div style='margin:4px 0;color:#666;font-size:12px'>" +
                     f"min {_f(st.get('min'))} · max {_f(st.get('max'))} · " +
                     f"mean {_f(st.get('mean'))} · finite {_f(st.get('finite_fraction'))}</div>" +
                     f'<canvas id="cv_{n}_{m}" width="{g*6+32}" height="{g*6}"></canvas>')
        style = "" if i == 0 else ' style="display:block"'
        sections += (f"<section class='panel' data-pan='{n}'{style}>" +
                     rows + "</section>")

    js = _field_js(pan_js, g, console.get("extent"),
                   console.get("probes_xy") or []) + "\n" + _TABS_JS
    body = ("<h2>Summary</h2>" + _table(summ) + tabs + sections +
            "<script>" + js + "</script>")
    return (_DOC.replace("__TITLE__", field)
            .replace("__HEADER__", header, 1)
            .replace("__BODY__", body, 1))


def _table(rows) -> str:
    return "<table>" + "".join(f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
                               for k, v in rows) + "</table>"


# Canvas painting + hover tooltips + legend + probe overlay shared by all field
# reports live in ``spectralmap._field_js`` (this console reuses it with the
# panel name as the canvas-id prefix). Only the tab switching is local.
_TABS_JS = __import__("inspect").cleandoc("""
  function tabs(){const bs=document.querySelectorAll('.tbtn');
    bs.forEach(b=>b.addEventListener('click',()=>{
      bs.forEach(x=>x.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(s2=>s2.style.display='none');
      b.classList.add('active');
      document.querySelector('.panel[data-pan="'+b.dataset.pan+'"]').style.display='block';}));}
  window.addEventListener('load',tabs);
""")


_DOC = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Field console — __TITLE__</title><style>
  body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a}
  h1{font-size:22px}h2{font-size:17px;margin:20px 0 8px}h3{font-size:14px;margin:14px 0 4px}
  table{border-collapse:collapse;margin:6px 0}
  th,td{border:1px solid #d0d0d0;padding:4px 10px;font-size:13px;text-align:right}
  th{background:#f4f4f4;text-align:left}
  canvas{border:1px solid #ddd;margin-bottom:6px}
  .tabs{margin:10px 0}
  .tbtn{border:1px solid #bbb;padding:6px 14px;margin-right:4px;background:#f4f4f4;cursor:pointer;font-size:13px}
  .tbtn.active{background:#cfd8ea;font-weight:600}
  .panel{display:none}
</style></head><body>
__HEADER____BODY__
</body></html>"""


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_console(verts: np.ndarray, artifact: dict, out_dir: str, *,
                  panels=("spectral", "coherence", "spectevol"),
                  ref_probe: int = 0, cycles=None, step: int = 1, frames=None,
                  k=None, p: float = 2.0, neighbors: int = 4,
                  source: str = "pod", preview: int = 24, nperseg=None,
                  dt=None, field: str = "") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = field or artifact.get("name") or "field"
    safe = _safe(name)
    console = build_console(verts, artifact, panels=panels, ref_probe=ref_probe,
                            cycles=cycles, step=step, frames=frames, k=k, p=p,
                            neighbors=neighbors, source=source, preview=preview,
                            nperseg=nperseg, dt=dt)
    (out / f"{safe}_fieldconsole.html").write_text(render_html(console),
                                                   encoding="utf-8")
    slim = {"field": name, "source": console["source"], "k": console["k"],
            "n_probes": console["n_probes"], "n_cycles": console["n_cycles"],
            "n_vertices": console["n_vertices"], "preview": console["preview"],
            "panels": {n: {"stats": console["panels"][n]["stats"],
                           "meta": console["panels"][n]["meta"],
                           "previews": _preview_lists(console["panels"][n]["previews"])}
                       for n in console["panel_order"]}}
    with open(out / f"{safe}_fieldconsole.json", "w", encoding="utf-8") as fh:
        json.dump(slim, fh, indent=2)
    summ = {"field": name, "html": f"{safe}_fieldconsole.html",
            "json": f"{safe}_fieldconsole.json", "panels": list(console["panel_order"]),
            "source": console["source"], "k": console["k"],
            "n_probes": console["n_probes"], "n_cycles": console["n_cycles"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summ, fh, indent=2)
    return summ




def _preview_lists(prevs: dict) -> dict:
    """Convert binned-preview ndarrays to JSON-safe [[float-or-None]] lists."""
    return {m: [[None if v is None or v != v else float(v) for v in row]
                for row in grid]
            for m, grid in prevs.items()}

def _read_verts(path: str) -> np.ndarray:
    from .reconfield import _read_verts as _rv
    return _rv(path)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.fieldconsole",
        description="FlowViewer R61 unified spectral-field console")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("verts", help=".npy or .json (N,3) vertex array")
    ap.add_argument("--panels", default="spectral,coherence,spectevol",
                    help="comma list of panels to include")
    ap.add_argument("--ref", type=int, default=0, help="reference probe index (coherence)")
    ap.add_argument("--source", choices=("pod", "dmd"), default="pod")
    ap.add_argument("--cycles", default=None, help="cycle range 'A:B'")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--p", type=float, default=2.0)
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--nperseg", type=int, default=None)
    ap.add_argument("--preview", type=int, default=24)
    ap.add_argument("--dt", type=float, default=None)
    ap.add_argument("--out", default="fieldconsole_out")
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
    panels = tuple(p for p in args.panels.split(",") if p.strip())
    for p in panels:
        if p not in PANEL_SPEC:
            print(f"error: unknown panel '{p}'", file=sys.stderr)
            return 2
    n_cycles = int(len(list(art.get("cycles", []))))
    cycles = None
    if args.cycles:
        try:
            a, _, b = args.cycles.partition(":")
            a = int(a) if a.strip() else 0
            b = int(b) if b.strip() else n_cycles
            if b < 0:
                b = n_cycles + b
            if not (0 <= a and a <= b and b <= n_cycles):
                raise ValueError("out of range")
            cycles = list(range(a, b))
        except ValueError as e:
            print(f"error: bad '--cycles': {e}", file=sys.stderr)
            return 2
    try:
        summary = write_console(verts, art, args.out, panels=panels,
                                ref_probe=args.ref, cycles=cycles, step=args.step,
                                frames=args.frames, k=args.k, p=args.p,
                                neighbors=args.neighbors, source=args.source,
                                preview=args.preview, nperseg=args.nperseg,
                                dt=args.dt)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
