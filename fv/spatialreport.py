"""R54: render the spatial modal analysis as a self-contained HTML report.

R51 turned the *probe-level* structural/modal family into one browsable page;
R52 spread a single mode's shape onto the whole mesh; R53 reconstructed the
full node field at any cycle — but neither spatial product had a viewable
surface, only CSV/JSON. R54 is R51's counterpart in the **spatial** domain: it
digests the mean field, the per-mode shape fields and the reconstruction
quality into a single dependency-free HTML page (summary, mean-field stats,
per-mode energy bars + shape range, reconstruction snapshot + captured energy,
probe-node reconstruction-vs-measured quality).

Pure Python (embedded CSS, no plotting library), headless-testable; reuses R52
``build_mode_field``, R53 ``mean_field``/``reconstruct_field``/``recon_quality``
and R51's HTML/document conventions on the same R38 trace artifact + vertices.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

import numpy as np

from .dmdrecon import _dmd_pieces, build_dmd_mode_field, dmd_recon_quality, reconstruct_field_dmd
from .modalfield import build_mode_field
from .pod import pod_decompose
from .reconfield import mean_field, recon_quality, reconstruct_field


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _f(v) -> str:
    if v is None:
        return "–"
    try:
        return f"{float(v):.6g}"
    except (TypeError, ValueError):
        return _esc(v)


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name) or "field"


def _stats(arr: np.ndarray) -> dict:
    """min/max/mean/finite_fraction/coverage of a node field array."""
    a = np.asarray(arr, dtype=np.float64)
    finite = np.isfinite(a)
    n_fin = int(finite.sum())
    if n_fin:
        fin = a[finite]
        return {"min": float(fin.min()), "max": float(fin.max()),
                "mean": float(fin.mean()),
                "finite_fraction": float(n_fin / a.size) if a.size else 0.0,
                "coverage": n_fin}
    return {"min": None, "max": None, "mean": None,
            "finite_fraction": 0.0, "coverage": 0}


# ── report construction ────────────────────────────────────────────────────


def build_spatial_report(verts: np.ndarray, artifact: dict, *, top=5,
                         p: float = 2.0, neighbors: int = 4,
                         cycle: int = 0, dmd: bool = False,
                         dmd_top: int = 3, field: bool = False,
                         source: str = "pod", preview: int = 24,
                         nperseg=None, dt=None, ref_probe: int = 0,
                         cycles=None, step: int = 1, frames=None) -> dict:
    """Digest vertices + an R38 trace artifact into a spatial report dict.

    Fuses the temporal-mean field (R53), the top ``top`` POD mode shape fields
    (R52), the full-field reconstruction at ``cycle`` (R53) and its probe-node
    quality (R53). When ``dmd`` is true it additionally digests the top
    ``dmd_top`` DMD mode-shape fields (R55/R52), the DMD full-field
    reconstruction and its quality — the POD/DMD spatial pair. When ``field``
    is true it additionally folds the R58/R59/R60 field reports (their binned
    previews + stats + meta, no ``(N,)`` node arrays) under ``field_maps`` so
    the one page shows POD/DMD and frequency-domain maps together (default
    keeps the report byte-identical to R54). Empty artifact / empty vertices ->
    graceful empty result (no exception). ``top=None`` (and ``dmd_top=None``)
    keeps every mode.
    """
    v = np.asarray(verts, dtype=np.float64)
    N = v.shape[0]
    field_name = artifact.get("name") or ""
    probes = list(artifact.get("probes", []))
    cycles_l = list(artifact.get("cycles", []))
    base = {"field": field_name, "n_probes": len(probes), "n_cycles": len(cycles_l),
            "n_vertices": N, "p": float(p), "neighbors": int(neighbors),
            "cycle": int(cycle),
            "mean": {"min": None, "max": None, "mean": None,
                     "finite_fraction": 0.0, "coverage": 0},
            "modes": [],
            "recon": {"finite_fraction": 0.0, "captured_var": 0.0,
                      "min": None, "max": None, "coverage": 0},
            "quality": {"total_rmse": None, "captured_var": 0.0,
                        "n_probes": 0, "n_cycles": 0, "k": 0},
            "dmd": {"enabled": bool(dmd), "modes": [],
                    "recon": {"finite_fraction": 0.0, "captured_var": 0.0,
                              "min": None, "max": None, "coverage": 0},
                    "quality": {"total_rmse": None, "captured_var": 0.0,
                                "n_probes": 0, "n_cycles": 0, "k": 0, "r": 0}},
            "field_maps": {"enabled": bool(field), "preview": int(preview),
                           "spectral": {}, "coherence": {}, "spectevol": {}}}
    if field and probes and cycles_l and N > 0:
        from .coherencemap import build_coherence_report
        from .spectevol import build_spectevol_report
        from .spectralmap import _probes_xy, build_spectral_report
        fm = base["field_maps"]
        fm["probes_xy"] = _probes_xy(probes)
        fm["extent"] = {"xmin": float(v[:, 0].min()), "xmax": float(v[:, 0].max()),
                        "ymin": float(v[:, 1].min()), "ymax": float(v[:, 1].max())}
        common = dict(cycles=cycles, step=step, frames=frames, k=None, p=p,
                      neighbors=neighbors, source=source, preview=preview, dt=dt)
        reps = {"spectral": build_spectral_report(v, artifact, **common),
                "coherence": build_coherence_report(v, artifact, ref_probe=ref_probe,
                                                    nperseg=nperseg, **common),
                "spectevol": build_spectevol_report(v, artifact, nperseg=nperseg,
                                                    **common)}
        for name, rep in reps.items():
            fm[name] = {"meta": {"n_frames": rep.get("n_frames", 0),
                                 "n_vertices": rep.get("n_vertices", 0),
                                 "dt": rep.get("dt"), "nyquist": rep.get("nyquist")},
                        "stats": rep.get("stats", {}),
                        "previews": rep.get("previews", {})}
    if not probes or not cycles_l or N == 0:
        return base

    mean_f = mean_field(v, probes, p=p, neighbors=neighbors)
    base["mean"] = _stats(mean_f)

    pod = pod_decompose(artifact)
    n_modes = int(pod["n_modes"])
    kk = n_modes if top is None else min(int(top or 0), n_modes)
    for i in range(kk):
        bf = build_mode_field(v, artifact, source="pod", k=i, p=p,
                              neighbors=neighbors)
        m = bf["meta"]
        base["modes"].append({
            "i": int(i),
            "energy_share": float(m.get("energy_share") or 0.0),
            "finite_fraction": float(m.get("finite_fraction") or 0.0),
            "min": m.get("min_abs"), "max": m.get("max_abs"),
        })

    recon = reconstruct_field(v, artifact, cycle=cycle, k=None, p=p,
                              neighbors=neighbors)
    recon_field = np.asarray(recon["recon_field"], dtype=np.float64)
    rs = _stats(recon_field)
    base["recon"] = {"finite_fraction": recon["finite_fraction"],
                     "captured_var": recon["captured_var"],
                     "min": rs["min"], "max": rs["max"],
                     "coverage": rs["coverage"]}

    qual = recon_quality(artifact, k=None)
    base["quality"] = {"total_rmse": qual["total_rmse"],
                       "captured_var": qual["captured_var"],
                       "n_probes": qual["n_probes"],
                       "n_cycles": qual["n_cycles"], "k": qual["k"]}

    if dmd:
        dd = _dmd_pieces(artifact, r=None, dt=None, embed_d=None)
        dmd_n = int(dd["r"]) if dd else 0
        kk_d = dmd_n if dmd_top is None else min(int(dmd_top or 0), dmd_n)
        for i in range(kk_d):
            bf = build_dmd_mode_field(v, artifact, k=i, p=p,
                                      neighbors=neighbors)
            m = bf["meta"]
            base["dmd"]["modes"].append({
                "i": int(i), "freq": m.get("freq"),
                "growth": m.get("growth"),
                "amplitude": m.get("amplitude"),
                "energy_share": float(m.get("energy_share") or 0.0),
                "finite_fraction": float(m.get("finite_fraction") or 0.0),
                "min": m.get("min_abs"), "max": m.get("max_abs"),
            })
        drec = reconstruct_field_dmd(v, artifact, cycle=cycle, k=None,
                                     p=p, neighbors=neighbors)
        ds = _stats(drec["recon_field"])
        base["dmd"]["recon"] = {
            "finite_fraction": drec["finite_fraction"],
            "captured_var": drec["captured_var"],
            "min": ds["min"], "max": ds["max"], "coverage": ds["coverage"]}
        dq = dmd_recon_quality(artifact, k=None)
        base["dmd"]["quality"] = {
            "total_rmse": dq["total_rmse"],
            "captured_var": dq["captured_var"],
            "n_probes": dq["n_probes"], "n_cycles": dq["n_cycles"],
            "k": dq["k"], "r": dq["r"]}
    return base


# ── HTML render ────────────────────────────────────────────────────────────


def _field_maps_html(fm: dict) -> str:
    """HTML block + inline JS for the R58/R59/R60 previews folded into the page.

    Renders one sub-section per non-empty field panel (each with its four
    ``<canvas id="cv_{panel}_{map}">`` heatmaps + per-map stats), painted by one
    shared interactive JS (hover tooltip / legend / probe overlay) from
    ``spectralmap._field_js`` (lazy imports avoid the
    spatialreport <- spatialanim <- spectralmap import cycle).
    Returns "" when no panel carries previews.
    """
    from .fieldconsole import PANEL_SPEC
    from .spectralmap import _field_js, _grid_range

    order = [n for n in ("spectral", "coherence", "spectevol")
             if fm.get(n, {}).get("previews")]
    if not order:
        return ""
    g = max(4, int(fm.get("preview", 24) or 24))
    pan_js = {}
    rows = ""
    for n in order:
        pane = fm[n]
        prevs = pane["previews"]
        spec = PANEL_SPEC[n]
        maps_js = {m: [[None if v != v else float(v) for v in row]
                       for row in prevs.get(m, [])] for m, _ in spec["maps"]}
        vm_js = {m: list(_grid_range(prevs.get(m, []))) for m, _ in spec["maps"]}
        pan_js[n] = {"maps": maps_js, "vm": vm_js,
                     "names": [m for m, _ in spec["maps"]]}
        rows += f"<h2>{_esc(spec['title'])}</h2>"
        for m, title in spec["maps"]:
            st = pane["stats"].get(m, {})
            rows += (f"<h3>{_esc(title)}</h3>" +
                     "<div style='margin:6px 0;color:#666;font-size:12px'>" +
                     f"min {_f(st.get('min'))} · max {_f(st.get('max'))} · " +
                     f"mean {_f(st.get('mean'))} · finite {_f(st.get('finite_fraction'))}</div>" +
                     f'<canvas id="cv_{n}_{m}" width="{g*6+32}" height="{g*6}" '
                     'style="border:1px solid #ddd"></canvas>')
    js = _field_js(pan_js, g, fm.get("extent"), fm.get("probes_xy") or [])
    return "<h2>Field maps</h2>" + rows + "<script>" + js + "</script>"


def render_html(report: dict) -> str:
    """A self-contained HTML document for a spatial report."""
    field = _esc(report.get("field"))
    header = f"<h1>Spatial report — {field}</h1>"
    if not report.get("n_probes"):
        return (_DOC_TEMPLATE.replace("__TITLE__", field)
                .replace("__HEADER__", header, 1)
                .replace("__SUMMARY__", "", 1)
                .replace("__BODY__", "<p>No probes.</p>", 1))

    summary_rows = [
        ("probes", report["n_probes"]), ("cycles", report["n_cycles"]),
        ("vertices", report["n_vertices"]), ("p", report["p"]),
        ("neighbors", report["neighbors"]),
        ("chosen cycle", report["cycle"]),
        ("modes shown", len(report["modes"])),
    ]
    if report["dmd"]["enabled"]:
        summary_rows.append(
            ("DMD modes shown", len(report["dmd"]["modes"])))
    summary_html = "<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
        for k, v in summary_rows) + "</table>"

    mean = report["mean"]
    mean_html = ("<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(mean[k])}</td></tr>"
        for k in ("min", "max", "mean", "finite_fraction", "coverage"))
        + "</table>")

    modes = report["modes"]
    if modes:
        modes_html = "".join(
            '<div class="bar"><span class="lab">m{}</span>'
            '<span class="fill" style="width:{:.1f}%"></span>'
            '<span class="pct">{:.1f}%</span>'
            '<span class="stat">finite {:.6g} · range '
            '[{} , {}]</span></div>'.format(
                m["i"], float(m["energy_share"]) * 100.0,
                float(m["energy_share"]) * 100.0,
                m["finite_fraction"], _f(m["min"]), _f(m["max"]))
            for m in modes)
    else:
        modes_html = "<p>No modes.</p>"

    recon = report["recon"]
    recon_rows = [
        ("finite_fraction", recon["finite_fraction"]),
        ("captured_var", recon["captured_var"]),
        ("min", recon["min"]), ("max", recon["max"]),
        ("coverage", recon["coverage"]),
    ]
    recon_html = ("<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
        for k, v in recon_rows) + "</table>")

    qual = report["quality"]
    qual_rows = [
        ("total_rmse", qual["total_rmse"]),
        ("captured_var", qual["captured_var"]),
        ("n_probes", qual["n_probes"]), ("n_cycles", qual["n_cycles"]),
        ("k (modes kept)", qual["k"]),
    ]
    qual_html = ("<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
        for k, v in qual_rows) + "</table>")

    dmd_html = ""
    if report["dmd"]["enabled"]:
        dm = report["dmd"]["modes"]
        if dm:
            dmodes_html = "".join(
                '<div class="bar"><span class="lab">d{}</span>'
                '<span class="fill" style="width:{:.1f}%"></span>'
                '<span class="pct">{:.1f}%</span>'
                '<span class="stat">freq {:.6g} · growth {:.6g} · '
                'finite {:.6g} · range [{} , {}]</span></div>'.format(
                    m["i"], float(m["energy_share"]) * 100.0,
                    float(m["energy_share"]) * 100.0,
                    m["freq"], m["growth"], m["finite_fraction"],
                    _f(m["min"]), _f(m["max"]))
                for m in dm)
        else:
            dmodes_html = "<p>No DMD modes.</p>"
        drecon = report["dmd"]["recon"]
        drec_rows = [
            ("finite_fraction", drecon["finite_fraction"]),
            ("captured_var", drecon["captured_var"]),
            ("min", drecon["min"]), ("max", drecon["max"]),
            ("coverage", drecon["coverage"]),
        ]
        drec_html = ("<table>" + "".join(
            f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
            for k, v in drec_rows) + "</table>")
        dq = report["dmd"]["quality"]
        dq_rows = [
            ("total_rmse", dq["total_rmse"]),
            ("captured_var", dq["captured_var"]),
            ("n_probes", dq["n_probes"]), ("n_cycles", dq["n_cycles"]),
            ("k (modes kept)", dq["k"]), ("r (rank)", dq["r"]),
        ]
        dq_html = ("<table>" + "".join(
            f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
            for k, v in dq_rows) + "</table>")
        dmd_html = ("<h2>DMD modes</h2>" + dmodes_html +
                    "<h2>DMD reconstruction</h2>" + drec_html +
                    "<h2>DMD quality</h2>" + dq_html)

    body = (
        "<h2>Summary</h2>" + summary_html +
        "<h2>Mean field</h2>" + mean_html +
        "<h2>Modes</h2>" + modes_html +
        "<h2>Reconstruction</h2>" + recon_html +
        "<h2>Probe quality</h2>" + qual_html + dmd_html)

    fm = report.get("field_maps") or {}
    if fm.get("enabled"):
        body += _field_maps_html(fm)

    return (_DOC_TEMPLATE.replace("__TITLE__", field)
            .replace("__HEADER__", header, 1)
            .replace("__SUMMARY__", "", 1)
            .replace("__BODY__", body, 1))


_DOC_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Spatial — __TITLE__</title><style>
  body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a}
  h1{font-size:22px}h2{font-size:16px;margin:22px 0 8px}
  table{border-collapse:collapse;margin:6px 0}
  th,td{border:1px solid #d0d0d0;padding:4px 10px;font-size:13px;text-align:right}
  th{background:#f4f4f4;text-align:left}
  .bar{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:13px}
  .lab{width:30px;color:#888}.pct{width:60px;color:#888;text-align:right}
  .fill{display:inline-block;height:14px;background:#2c6fd0;border-radius:3px}
  .stat{color:#888}
</style></head><body>
__HEADER____SUMMARY____BODY__
</body></html>"""


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_spatial_report(verts: np.ndarray, artifact: dict, out_dir: str, *,
                         top=5, p: float = 2.0, neighbors: int = 4,
                         cycle: int = 0, dmd: bool = False,
                         dmd_top: int = 3, field: bool = False,
                         source: str = "pod", preview: int = 24,
                         nperseg=None, dt=None, ref_probe: int = 0,
                         cycles=None, step: int = 1, frames=None) -> dict:
    """Render + write ``<field>_spatial.html`` / ``_spatial.json`` + summary."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = build_spatial_report(verts, artifact, top=top, p=p,
                                  neighbors=neighbors, cycle=cycle,
                                  dmd=dmd, dmd_top=dmd_top, field=field,
                                  source=source, preview=preview,
                                  nperseg=nperseg, dt=dt, ref_probe=ref_probe,
                                  cycles=cycles, step=step, frames=frames)
    name = artifact.get("name") or "field"
    safe = _safe(name)
    html_path = out / f"{safe}_spatial.html"
    html_path.write_text(render_html(report), encoding="utf-8")
    payload = {k: report[k] for k in
               ("field", "n_probes", "n_cycles", "n_vertices", "p",
                "neighbors", "cycle", "mean", "modes", "recon", "quality",
                "dmd")}
    if report["field_maps"]["enabled"]:
        payload["field_maps"] = _field_maps_slim(report["field_maps"])
    with open(out / f"{safe}_spatial.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    modes = report["modes"]
    dmodes = report["dmd"]["modes"]
    summary = {
        "field": name, "html": f"{safe}_spatial.html",
        "json": f"{safe}_spatial.json",
        "n_probes": report["n_probes"], "n_cycles": report["n_cycles"],
        "n_vertices": report["n_vertices"], "top": int(top or 0),
        "cycle": int(cycle),
        "dmd": bool(dmd), "dmd_top": int(dmd_top or 0),
        "field_maps": bool(field), "field_source": source if field else None,
        "top1_energy": modes[0]["energy_share"] if modes else None,
        "total_rmse": report["quality"]["total_rmse"],
        "recon_captured": report["recon"]["captured_var"],
        "recon_finite_fraction": report["recon"]["finite_fraction"],
        "dmd_top_energy": dmodes[0]["energy_share"] if dmodes else None,
        "dmd_total_rmse": report["dmd"]["quality"]["total_rmse"],
        "dmd_captured": report["dmd"]["recon"]["captured_var"],
    }
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def _field_maps_slim(fm: dict) -> dict:
    """JSON-safe copy of field_maps: stats/meta + list-of-lists previews."""
    slim = {"enabled": bool(fm.get("enabled")), "preview": int(fm.get("preview", 24)),
            "extent": fm.get("extent"), "probes_xy": fm.get("probes_xy", [])}
    for n in ("spectral", "coherence", "spectevol"):
        pane = fm.get(n) or {}
        prevs = pane.get("previews", {})
        slim[n] = {"meta": pane.get("meta", {}),
                   "stats": pane.get("stats", {}),
                   "previews": {m: [[None if v is None or v != v else float(v)
                                     for v in row]
                                    for row in grid]
                                for m, grid in prevs.items()}}
    return slim


def _read_verts(path: str) -> np.ndarray:
    """Load an ``(N, 3)`` vertex array from a ``.npy`` or ``.json`` file."""
    p = Path(path)
    if p.suffix.lower() == ".npy":
        arr = np.load(path, allow_pickle=False)
    else:
        with open(path, "r", encoding="utf-8") as fh:
            arr = np.asarray(json.load(fh), dtype=np.float64)
    return arr


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.spatialreport",
        description="FlowViewer R54 spatial analysis HTML report")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("verts", help=".npy or .json (N,3) vertex array")
    ap.add_argument("--top", type=int, default=5, help="max POD modes")
    ap.add_argument("--p", type=float, default=2.0)
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--cycle", type=int, default=0)
    ap.add_argument("--dmd", action="store_true",
                    help="also report the DMD mode shapes + DMD reconstruction")
    ap.add_argument("--dmd-top", type=int, default=3, help="max DMD modes")
    ap.add_argument("--field", action="store_true",
                    help="also fold the R58/R59/R60 field maps into this report")
    ap.add_argument("--source", choices=("pod", "dmd"), default="pod",
                    help="reconstruction source for the field maps")
    ap.add_argument("--preview", type=int, default=24,
                    help="binned preview grid for the field maps")
    ap.add_argument("--nperseg", type=int, default=None)
    ap.add_argument("--dt", type=float, default=None)
    ap.add_argument("--ref", type=int, default=0,
                    help="reference probe index (coherence field map)")
    ap.add_argument("--cycles", default=None,
                    help="field-map cycle range 'A:B' (default full; step via --step)")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--frames", type=int, default=None)
    ap.add_argument("--out", default="spatialreport_out")
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
        summary = write_spatial_report(verts, art, args.out, top=args.top,
                                       p=args.p, neighbors=args.neighbors,
                                       cycle=args.cycle, dmd=args.dmd,
                                       dmd_top=args.dmd_top, field=args.field,
                                       source=args.source, preview=args.preview,
                                       nperseg=args.nperseg, dt=args.dt,
                                       ref_probe=args.ref, cycles=cycles,
                                       step=args.step, frames=args.frames)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
