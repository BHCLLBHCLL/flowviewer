"""R57: spatial reconstruction animation over a cycle window + unsteadiness.

R53 (POD) and R55 (DMD) reconstruct the full node field at a **single** cycle;
R54/R56 embed that one snapshot in an HTML report. R57 adds the **time axis**:
rebuild the whole field over a cycle window into a frame sequence, give a
headless coarse field-preheat view (pure HTML <canvas> + a couple of lines of
standard JS, no VTK, no image library) and summarise the temporal
_fluctuation/unsteadiness_ of the reconstructed field (per-vertex mean / std /
range / rms). This finally makes a spatial field *visible and animated* without
leaving the pure-NumPy, headless path.

Reuses R53 ``reconstruct_field`` (source="pod") and R55 ``reconstruct_field_dmd``
(source="dmd"), and R54/R56's HTML/_safe conventions.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from .dmdrecon import reconstruct_field_dmd
from .reconfield import reconstruct_field

# local re-binding of the same helper family used by R54/R56 for cache reuse
from .spatialreport import _safe


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _f(v) -> str:
    if v is None:
        return "–"
    try:
        return f"{float(v):.6g}"
    except (TypeError, ValueError):
        return _esc(v)


def _stats(arr: np.ndarray) -> dict:
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


def _resolve_cycles(n_cycles: int, cycles=None, step: int = 1) -> list:
    if cycles is None:
        return list(range(0, n_cycles, max(1, int(step))))
    idx = []
    for c in cycles:
        cc = int(c)
        if not (0 <= cc < n_cycles):
            raise ValueError(f"cycle={cc} out of range (n_cycles={n_cycles})")
        idx.append(cc)
    return sorted(set(idx))


# ── coarse scalar preview (headless, pure HTML/CSS/Canvas) ─────────────────


def binned_preview(verts: np.ndarray, field: np.ndarray, *,
                   gridsize: int = 24) -> np.ndarray:
    """Average ``field`` per (x, y) bin over a square grid; empty -> NaN.

    Projects vertices onto their (x, y) coordinates, bins them into a
    ``gridsize × gridsize`` grid and averages the *finite* field values in each
    cell (cells with no finite value -> NaN). Used as a lightweight, dependency
    -free scalar-field view in the HTML report.
    """
    g = max(4, int(gridsize))
    v = np.asarray(verts, dtype=np.float64)
    f = np.asarray(field, dtype=np.float64)
    out = np.full((g, g), np.nan, dtype=np.float64)
    if v.shape[0] == 0 or f.shape[0] != v.shape[0]:
        return out
    x = v[:, 0]
    y = v[:, 1]
    xmin, xmax = float(np.min(x)), float(np.max(x))
    ymin, ymax = float(np.min(y)), float(np.max(y))
    sx = (xmax - xmin) or 1.0
    sy = (ymax - ymin) or 1.0
    gx = np.clip(((x - xmin) / sx * g).astype(np.int64), 0, g - 1)
    gy = np.clip(((y - ymin) / sy * g).astype(np.int64), 0, g - 1)
    finite = np.isfinite(f)
    if not finite.any():
        return out
    sums = np.zeros((g, g), dtype=np.float64)
    cnt = np.zeros((g, g), dtype=np.int64)
    np.add.at(sums, (gy[finite], gx[finite]), f[finite])
    cnt += np.bincount(gx[finite] + g * gy[finite],
                       minlength=g * g).reshape(g, g)
    nz = cnt > 0
    out[nz] = sums[nz] / cnt[nz]
    return out


# ── frame sequence ─────────────────────────────────────────────────────────


def _recon_frame(verts, artifact, cycle: int, k, p, neighbors, source: str):
    if source == "dmd":
        return reconstruct_field_dmd(verts, artifact, cycle=cycle, k=k,
                                     p=p, neighbors=neighbors)["recon_field"]
    return reconstruct_field(verts, artifact, cycle=cycle, k=k, p=p,
                             neighbors=neighbors)["recon_field"]


def reconstruct_sequence(verts: np.ndarray, artifact: dict, *,
                         cycles=None, step: int = 1, k=None, p: float = 2.0,
                         neighbors: int = 4, source: str = "pod") -> dict:
    """Reconstruct the node field at an (ordered) sequence of cycles.

    Returns ``{"field", "source", "steps", "cycle_idx", "frames", "n_vertices",
    "n_cycles"}`` — ``frames`` is a list of ``(N,)`` real recon fields. Empty
    artifact -> empty sequence.
    """
    probes = list(artifact.get("probes", []))
    n_cycles = int(len(list(artifact.get("cycles", []))))
    empty = {"field": artifact.get("name") or "", "source": source,
             "steps": 0, "cycle_idx": [], "frames": [],
             "n_vertices": int(np.asarray(verts).shape[0]),
             "n_cycles": n_cycles}
    if not probes or not n_cycles:
        return empty
    if source not in ("pod", "dmd"):
        raise ValueError(f"source={source!r} must be 'pod' or 'dmd'")
    idx = _resolve_cycles(n_cycles, cycles, step)
    frames = []
    vert = np.asarray(verts, dtype=np.float64)
    for c in idx:
        frames.append(np.asarray(_recon_frame(vert, artifact, c, k, p,
                                              neighbors, source),
                                 dtype=np.float64))
    if not frames:
        return empty
    return {**empty, "steps": len(frames), "cycle_idx": idx,
            "frames": frames}


# ── temporal (unsteadiness) statistics over frames ─────────────────────────


def stationarity(verts: np.ndarray, artifact: dict, *, cycles=None,
                 step: int = 1, k=None, p: float = 2.0, neighbors: int = 4,
                 source: str = "pod") -> dict:
    """Per-vertex mean / std / range / rms of the reconstructed sequence."""
    seq = reconstruct_sequence(verts, artifact, cycles=cycles, step=step,
                               k=k, p=p, neighbors=neighbors, source=source)
    N = int(np.asarray(verts).shape[0])
    if not seq["frames"]:
        return {"field": seq["field"], "source": source, "n_vertices": N,
                "steps": 0, "mean": np.full(N, np.nan) if N else np.empty((0,)),
                "std": np.full(N, np.nan) if N else np.empty((0,)),
                "range": np.full(N, np.nan) if N else np.empty((0,)),
                "rms": np.full(N, np.nan) if N else np.empty((0,)),
                "mean_stats": _stats([]), "std_stats": _stats([]),
                "range_stats": _stats([]), "rms_stats": _stats([])}
    A = np.stack(seq["frames"], axis=0)                 # (M, N)
    mean = np.nanmean(A, axis=0)
    std = np.nanstd(A, axis=0)
    rmin = np.nanmin(A, axis=0)
    rmax = np.nanmax(A, axis=0)
    rng = rmax - rmin
    rms = np.sqrt(np.nanmean(A * A, axis=0))
    return {"field": seq["field"], "source": source, "n_vertices": N,
            "steps": len(seq["frames"]), "mean": mean, "std": std,
            "range": rng, "rms": rms,
            "mean_stats": _stats(mean), "std_stats": _stats(std),
            "range_stats": _stats(rng), "rms_stats": _stats(rms)}


# ── report construction ────────────────────────────────────────────────────


def _pick_frames(cycle_idx: list, frames: int) -> tuple:
    """Evenly sample the (already ordered) cycle list down to <= ``frames``."""
    m = len(cycle_idx)
    if frames is None or m <= frames:
        return list(cycle_idx), [i for i in range(m)], m
    keep_pos = sorted({round(i * (m - 1) / (frames - 1)) for i in range(frames)})
    return [cycle_idx[i] for i in keep_pos], keep_pos, len(keep_pos)


def build_anim_report(verts: np.ndarray, artifact: dict, *, cycles=None,
                      step: int = 1, frames: int = 24, k=None, p: float = 2.0,
                      neighbors: int = 4, source: str = "pod",
                      preview: int = 24) -> dict:
    """Assemble a spatial-animation report dict (frames stats + previews + unsteadiness)."""
    v = np.asarray(verts, dtype=np.float64)
    N = v.shape[0]
    probes = list(artifact.get("probes", []))
    n_cycles = int(len(list(artifact.get("cycles", []))))
    field = artifact.get("name") or ""
    base = {"field": field, "source": source, "n_probes": len(probes),
            "n_cycles": n_cycles, "n_vertices": N, "k": int(k) if k else None,
            "p": float(p), "neighbors": int(neighbors), "frames": [],
            "preview": int(preview), "cycle_idx": [],
            "extent": {"xmin": None, "xmax": None, "ymin": None, "ymax": None},
            "unsteady": no_unsteady()}
    if N == 0:
        return base
    x, y = v[:, 0], v[:, 1]
    base["extent"] = {"xmin": float(x.min()), "xmax": float(x.max()),
                      "ymin": float(y.min()), "ymax": float(y.max())}
    if not probes or not n_cycles:
        return base
    seq = reconstruct_sequence(v, artifact, cycles=cycles, step=step, k=k,
                               p=p, neighbors=neighbors, source=source)
    if not seq["frames"]:
        return base
    idx, pos, m = _pick_frames(seq["cycle_idx"], frames)
    # captured_var for the report comes from the full-k reconstruction of each frame
    rec = []
    vert = v
    for c in idx:
        if source == "dmd":
            r = reconstruct_field_dmd(vert, artifact, cycle=c, k=k, p=p,
                                      neighbors=neighbors)
            cv = r["captured_var"]
        else:
            r = reconstruct_field(vert, artifact, cycle=c, k=k, p=p,
                                  neighbors=neighbors)
            cv = r["captured_var"]
        rec.append((r["recon_field"], r["finite_fraction"], cv))
    fr0 = _stats(rec[0][0]) if rec else _stats([])
    base["frames"] = [
        {"cycle": int(c), "finite_fraction": rec[i][1],
         "captured_var": float(rec[i][2]) if rec[i][2] == rec[i][2] else None,
         "min": fr0["min"] if i == 0 else None, "max": None, "mean": None}
        for i, c in enumerate(idx)]
    # per-frame stats
    for i, (rf, ff, cv) in enumerate(rec):
        st = _stats(rf)
        base["frames"][i]["min"] = st["min"]
        base["frames"][i]["max"] = st["max"]
        base["frames"][i]["mean"] = st["mean"]
        base["frames"][i]["finite_fraction"] = float(ff) if ff == ff else 0.0
    base["cycle_idx"] = idx
    base["preview_data"] = [binned_preview(vert, rec[i][0], gridsize=preview)
                            for i in range(m)]
    base["unsteady"] = stationarity_on(vert, artifact, idx, k, p, neighbors,
                                       source)
    return base


def no_unsteady() -> dict:
    return {"steps": 0, "mean": _stats([]), "std": _stats([]),
            "range": _stats([]), "rms": _stats([])}


def stationarity_on(verts, artifact, idx, k, p, neighbors, source):
    if len(idx) < 2:
        return no_unsteady()
    st = stationarity(verts, artifact, cycles=idx, k=k, p=p,
                      neighbors=neighbors, source=source)
    return {"steps": st["steps"], "mean": st["mean_stats"],
            "std": st["std_stats"], "range": st["range_stats"],
            "rms": st["rms_stats"]}


# ── HTML render ────────────────────────────────────────────────────────────


_RENDER_JS = __import__("inspect").cleandoc("""
  const FRAMES=__FRAMES__;
  const G=__GRID__; const VMIN=__VMIN__, VMAX=__VMAX__;
  const STATS=__STATS__;
  function cmap(t){t=t<0?0:(t>1?1:t);
    const stops=[[0,38,0,115],[.25,58,124,185],[.5,255,255,255],[.75,255,120,40],[1,150,0,0]];
    let i=0; while(i<stops.length-2&&t>=stops[i+1][0])i++;
    const a=stops[i],b=stops[i+1],u=(t-a[0])/(b[0]-a[0]);
    return 'rgb('+Math.round(a[1]+(b[1]-a[1])*u)+','+Math.round(a[2]+(b[2]-a[2])*u)+','+Math.round(a[3]+(b[3]-a[3])*u)+')';
  }
  function draw(ev){
    const i=+document.getElementById('sl').value-1;
    document.getElementById('lbl').textContent='cycle '+STATS.cyc[i];
    document.getElementById('fmin').textContent='min '+fmt(STATS.min[i]);
    document.getElementById('fmax').textContent='max '+fmt(STATS.max[i]);
    document.getElementById('fmean').textContent='mean '+fmt(STATS.mean[i]);
    const cv=document.getElementById('cv'); cv.width=G*6; cv.height=G*6;
    const c=cv.getContext('2d'); const f=FRAMES[i];
    for(let gy=0;gy<G;gy++)for(let gx=0;gx<G;gx++){
      const vv=f[gy][gx]; if(vv===null){continue;}
      c.fillStyle=cmap((vv-VMIN)/(VMAX-VMIN)); c.fillRect(gx*6,gy*6,6,6);
    }
  }
  function fmt(x){return (Math.round(x*1e6)/1e6).toString().replace(/(\\.\\d{3})\\d+$/,'$1');}
  document.getElementById('sl').addEventListener('input',draw);draw();
""")


def render_html(report: dict) -> str:
    field = _esc(report.get("field"))
    header = f"<h1>Spatial animation — {field}</h1>"
    if not report.get("n_probes"):
        return (_DOC.replace("__TITLE__", field)
                .replace("__HEADER__", header, 1)
                .replace("__BODY__", "<p>No data.</p>", 1))
    frames = report.get("frames", [])
    if not frames:
        return (_DOC.replace("__TITLE__", field)
                .replace("__HEADER__", header, 1)
                .replace("__BODY__", "<p>No data.</p>", 1))

    summ = [
        ("field", report["field"]), ("source", report["source"]),
        ("probes", report["n_probes"]), ("cycles", report["n_cycles"]),
        ("vertices", report["n_vertices"]), ("k", report["k"]),
        ("p", report["p"]), ("neighbors", report["neighbors"]),
        ("frames shown", len(frames)),
        ("preview grid", f"{report['preview']}×{report['preview']}"),
        ("cycle range", f"{frames[0]['cycle']} … {frames[-1]['cycle']}"),
    ]
    summ_html = "<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
        for k, v in summ) + "</table>"

    # inline data as JSON so a handful of standard-JS lines can paint a canvas
    pdata = report.get("preview_data", [])
    allv = [v for pr in pdata for row in pr for v in row
            if v is not None and v == v]
    vmin = min(allv) if allv else 0.0
    vmax = max(allv) if allv else 1.0
    span = (vmax - vmin) or 1.0
    frames_json = json.dumps(
        [[[None if v != v else float(v) for v in row] for row in pr]
         for pr in pdata])
    stats_json = json.dumps({
        "cyc": [fr["cycle"] for fr in frames],
        "min": [fr["min"] if fr["min"] is not None else 0 for fr in frames],
        "max": [fr["max"] if fr["max"] is not None else 0 for fr in frames],
        "mean": [fr["mean"] if fr["mean"] is not None else 0 for fr in frames],
    })
    js = (_RENDER_JS.replace("__FRAMES__", frames_json)
          .replace("__GRID__", str(report["preview"]))
          .replace("__VMIN__", json.dumps(float(vmin)))
          .replace("__VMAX__", json.dumps(float(vmin + span)))
          .replace("__STATS__", stats_json))

    un = report.get("unsteady", no_unsteady())
    un_rows = [
        ("mean-finite", un["mean"]["finite_fraction"]),
        ("std min", un["std"]["min"]), ("std max", un["std"]["max"]),
        ("std mean", un["std"]["mean"]),
        ("range max", un["range"]["max"]),
        ("rms mean", un["rms"]["mean"]),
    ]
    un_html = ("<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
        for k, v in un_rows) + "</table>")

    browser = (
        '<div><input type="range" id="sl" min="1" max="{m}" value="1" '
        'class="slider"><span id="lbl" class="stat">cycle {c0}</span> '
        '<span id="fmin" class="stat"></span> <span id="fmax" class="stat">'
        '</span> <span id="fmean" class="stat"></span></div>'
        '<canvas id="cv" width="{w}" height="{w}"></canvas>'.format(
            m=max(1, len(frames)), c0=frames[0]["cycle"],
            w=int(report["preview"]) * 6))
    body = (
        "<h2>Summary</h2>" + summ_html +
        "<h2>Frame browser</h2>" + browser +
        "<h2>Unsteadiness</h2>" + un_html +
        "<script>" + js + "</script>")

    return (_DOC.replace("__TITLE__", field)
            .replace("__HEADER__", header, 1)
            .replace("__BODY__", body, 1))


_DOC = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Spatial animation — __TITLE__</title><style>
  body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a}
  h1{font-size:22px}h2{font-size:16px;margin:22px 0 8px}
  table{border-collapse:collapse;margin:6px 0}
  th,td{border:1px solid #d0d0d0;padding:4px 10px;font-size:13px;text-align:right}
  th{background:#f4f4f4;text-align:left}
  .slider{width:320px;vertical-align:middle}.stat{color:#888;margin-left:8px}
  canvas{border:1px solid #ddd;margin-top:8px}
</style></head><body>
__HEADER____BODY__
</body></html>"""


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_anim_report(verts: np.ndarray, artifact: dict, out_dir: str, *,
                      cycles=None, step: int = 1, frames: int = 24, k=None,
                      p: float = 2.0, neighbors: int = 4, source: str = "pod",
                      preview: int = 24, field: str = "") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = field or artifact.get("name") or "field"
    safe = _safe(name)
    rep = build_anim_report(verts, artifact, cycles=cycles, step=step,
                            frames=frames, k=k, p=p, neighbors=neighbors,
                            source=source, preview=preview)
    (out / f"{safe}_anim.html").write_text(render_html(rep), encoding="utf-8")
    payload = {"field": name, "source": rep["source"], "k": rep["k"],
               "n_probes": rep["n_probes"], "n_cycles": rep["n_cycles"],
               "n_vertices": rep["n_vertices"],
               "cycle_idx": [int(c) for c in rep["cycle_idx"]],
               "frames": rep["frames"], "unsteady": unstat_to_json(rep["unsteady"])}
    with open(out / f"{safe}_anim.json", "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    # node CSV: node,x,y,z + one col per report frame
    vert = np.asarray(verts, dtype=np.float64)
    seq = reconstruct_sequence(vert, artifact, cycles=rep["cycle_idx"],
                               k=k, p=p, neighbors=neighbors, source=source)
    cols = f"node,x,y,z,{','.join('f'+str(c) for c in rep['cycle_idx'])}"
    with open(out / f"{safe}_anim_nodes.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols.split(","))
        frames_m = seq["frames"] if seq["frames"] else [[np.nan] * len(vert)]
        for i2 in range(len(vert)):
            w.writerow([i2, f"{vert[i2][0]:.6g}", f"{vert[i2][1]:.6g}",
                        f"{vert[i2][2]:.6g}"] +
                       [f"{float(fr[i2]):.6g}" if np.isfinite(fr[i2]) else ""
                        for fr in frames_m])
    summ = {"field": name, "html": f"{safe}_anim.html",
            "json": f"{safe}_anim.json", "csv": f"{safe}_anim_nodes.csv",
            "source": rep["source"], "n_frames": len(rep["frames"]),
            "n_cycles": rep["n_cycles"], "k": rep["k"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summ, fh, indent=2)
    return summ


def unstat_to_json(un: dict) -> dict:
    return {"steps": int(un["steps"]),
            "mean": _stats_nan(un["mean"]), "std": _stats_nan(un["std"]),
            "range": _stats_nan(un["range"]), "rms": _stats_nan(un["rms"])}


def _stats_nan(d: dict) -> dict:
    mm = d.get("min")
    return {"min": None if mm != mm else mm, "max": d.get("max"),
            "mean": d.get("mean"),
            "finite_fraction": d.get("finite_fraction", 0.0),
            "coverage": d.get("coverage", 0)}


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.spatialanim",
        description="FlowViewer R57 spatial reconstruction animation report")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("verts", help=".npy or .json (N,3) vertex array")
    ap.add_argument("--source", choices=("pod", "dmd"), default="pod")
    ap.add_argument("--cycles", default=None,
                    help="cycle range 'A:B' (optional, default full; step via --step)")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--frames", type=int, default=24, help="report frame cap")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--p", type=float, default=2.0)
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--preview", type=int, default=24)
    ap.add_argument("--out", default="spatialanim_out")
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
        if not cycles:
            cycles = None if cycles is None else cycles
    try:
        summary = write_anim_report(verts, art, args.out, cycles=cycles,
                                    step=args.step, frames=args.frames, k=args.k,
                                    p=args.p, neighbors=args.neighbors,
                                    source=args.source, preview=args.preview)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


def _read_verts(path: str) -> np.ndarray:
    from .reconfield import _read_verts as _rv
    return _rv(path)


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
