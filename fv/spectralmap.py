"""R58: spatio-temporal spectral maps of a reconstructed field sequence.

R57 turns the full-field reconstruction (R53/R55) into a *frame sequence* over a
cycle window and summarises it in the temporal domain (mean / std / range / rms).
R58 lifts the probe-level frequency family (R41 periodogram, R44 turbulence
intensity) onto the **whole mesh**: it FFTs the reconstructed time series at
every vertex and maps four scalars back onto the domain — the time-mean field,
the fluctuation RMS (and its mean-normalised intensity), and the dominant
oscillation frequency. Mindful counterpart of R52's "spread modal *weights*":
R52 spreads temporal-mode weights, R58 spreads spectral features.

Pure NumPy + standard HTML/Canvas (no vtk, no image lib, headless). Reuses R57's
``reconstruct_sequence`` / ``binned_preview`` / HTML conventions and R41's
``mean_dt``.
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

from .spatialanim import _f, _safe, _stats, binned_preview, reconstruct_sequence
from .spectrum import mean_dt


def _esc(s) -> str:
    return html.escape(str(s)) if s is not None else ""


def _empty_maps(n: int, dt) -> dict:
    nan = np.full(n, np.nan) if n else np.empty((0,), dtype=np.float64)
    return {"mean": nan, "rms": nan, "rms_intensity": nan, "freq": nan,
            "dom_amp": nan, "dt": float(dt or 1.0), "nyquist": 0.0}


# ── per-vertex spectrum ─────────────────────────────────────────────────────


def temporal_spectrum_field(frames, dt=None) -> dict:
    """Per-vertex temporal statistics + dominant frequency of a frame matrix.

    ``frames`` is ``(M, N)`` (M frame snapshots of an N-vertex field). Returns
    per-vertex ``mean`` / ``rms`` (detrended std) / ``rms_intensity`` (rms over
    ``|mean|`` with a small floor; near-zero-mean vertices -> NaN) / ``freq``
    (dominant non-DC frequency) / ``dom_amp`` (physical amplitude of that tone),
    plus ``dt`` / ``nyquist``. Vertices with fewer than two finite samples, or the
    degenerate (M<2 / N==0) case, collapse to all-NaN maps.
    """
    A = np.asarray(frames, dtype=np.float64)
    if A.ndim != 2 or A.shape[0] < 2 or A.shape[1] == 0:
        return _empty_maps(A.shape[1] if A.ndim == 2 else 0, dt)
    M, N = A.shape
    if dt is None:
        dt = 1.0
    mask = np.isfinite(A)
    good = mask.sum(axis=0) >= 2                       # usable vertices
    mean = np.nanmean(A, axis=0)
    centered = np.where(mask, A - mean[None, :], np.nan)
    rms = np.sqrt(np.nanmean(centered * centered, axis=0))
    filled = np.nan_to_num(centered, nan=0.0)          # detrended, NaN->0
    F = np.fft.rfft(filled, axis=0)                    # (M//2+1, N)
    freq = np.fft.rfftfreq(M, d=float(dt))
    Fmag = np.abs(F)
    Fmag1 = Fmag[1:, :]                                # drop DC (detrended ~0)
    pos = np.argmax(Fmag1, axis=0)
    dom_freq = freq[1:][pos]
    dom_amp = 2.0 * np.max(Fmag1, axis=0) / M          # physical tone amplitude
    mean[~good] = np.nan
    rms[~good] = np.nan
    dom_freq[~good] = np.nan
    dom_amp[~good] = np.nan

    absmean = np.abs(mean)
    peak = np.nanmax(absmean) if np.isfinite(absmean).any() else 0.0
    floor = max(1e-12, 1e-6 * (peak or 1.0))
    inten = rms / (absmean + floor)
    inten[absmean < floor] = np.nan
    inten[~good] = np.nan
    return {"mean": mean, "rms": rms, "rms_intensity": inten, "freq": dom_freq,
            "dom_amp": dom_amp, "dt": float(dt), "nyquist": float(freq[-1])}


# ── report construction ─────────────────────────────────────────────────────


def _subsample(cycle_idx, frames):
    if frames is None or len(cycle_idx) <= frames:
        return list(cycle_idx)
    m = len(cycle_idx)
    keep = sorted({round(i * (m - 1) / (frames - 1)) for i in range(frames)})
    return [cycle_idx[i] for i in keep]


def build_spectral_report(verts: np.ndarray, artifact: dict, *, cycles=None,
                          step: int = 1, frames=None, k=None, p: float = 2.0,
                          neighbors: int = 4, source: str = "pod",
                          preview: int = 24, dt=None) -> dict:
    """Digest vertices + an R38 trace artifact into a spectral-map report dict."""
    v = np.asarray(verts, dtype=np.float64)
    N = v.shape[0]
    probes = list(artifact.get("probes", []))
    n_cycles = int(len(list(artifact.get("cycles", []))))
    field = artifact.get("name") or ""
    base = {"field": field, "source": source, "n_probes": len(probes),
            "n_cycles": n_cycles, "n_frames": 0, "n_vertices": N,
            "k": int(k) if k else None, "p": float(p), "neighbors": int(neighbors),
            "dt": None, "nyquist": 0.0, "preview": int(preview),
            "extent": {"xmin": None, "xmax": None, "ymin": None, "ymax": None},
            "maps": _empty_maps(N, dt), "stats": _empty_stats(),
            "previews": {"mean": [], "rms": [], "intensity": [], "freq": []}}
    if N == 0:
        return base
    x, y = v[:, 0], v[:, 1]
    base["extent"] = {"xmin": float(x.min()), "xmax": float(x.max()),
                      "ymin": float(y.min()), "ymax": float(y.max())}
    if not probes or not n_cycles:
        return base
    seq = reconstruct_sequence(v, artifact, cycles=cycles, step=step, k=k,
                               p=p, neighbors=neighbors, source=source)
    if not seq["frames"] or len(seq["frames"]) < 2:
        return base
    idx = list(seq["cycle_idx"])
    if frames is not None:
        idx = _subsample(idx, int(frames))
        frame_map = {c: f for c, f in zip(seq["cycle_idx"], seq["frames"])}
        seq_frames = [frame_map[c] for c in idx]
    else:
        seq_frames = seq["frames"]
    if len(seq_frames) < 2:
        return base
    if dt is None:
        try:
            times = np.asarray(list(artifact["cycles"]), dtype=np.float64)[idx]
            dt0 = float(mean_dt(times))
        except (TypeError, ValueError, IndexError):
            dt0 = 1.0
    else:
        dt0 = float(dt)
    sp = temporal_spectrum_field(seq_frames, dt=dt0)
    base["dt"] = sp["dt"]
    base["nyquist"] = sp["nyquist"]
    base["n_frames"] = len(seq_frames)
    maps = {"mean": sp["mean"], "rms": sp["rms"],
            "intensity": sp["rms_intensity"], "freq": sp["freq"]}
    base["maps"] = maps
    base["stats"] = {name: _stats(arr) for name, arr in maps.items()}
    base["previews"] = {name: binned_preview(v, arr, gridsize=preview)
                        for name, arr in maps.items()}
    return base


def _empty_stats() -> dict:
    e = {"min": None, "max": None, "mean": None, "finite_fraction": 0.0,
         "coverage": 0}
    return {"mean": dict(e), "rms": dict(e), "intensity": dict(e),
            "freq": dict(e)}


# ── HTML render ─────────────────────────────────────────────────────────────

_DRAW_JS = __import__("inspect").cleandoc("""
  const MAPS=__MAPS__; const VM=__VM__; const G=__GRID__; const NAMES=__NAMES__;
  function cmap(t){t=t<0?0:(t>1?1:t);
    const stops=[[0,38,0,115],[.25,58,124,185],[.5,255,255,255],[.75,255,120,40],[1,90,0,0]];
    let i=0; while(i<stops.length-2&&t>=stops[i+1][0])i++;
    const a=stops[i],b=stops[i+1],u=(t-a[0])/(b[0]-a[0]);
    return 'rgb('+Math.round(a[1]+(b[1]-a[1])*u)+','+Math.round(a[2]+(b[2]-a[2])*u)+','+Math.round(a[3]+(b[3]-a[3])*u)+')';
  }
  function paint(){
    for(const nm of NAMES){
      const cv=document.getElementById('cv_'+nm); const c=cv.getContext('2d');
      const g=MAPS[nm], lo=VM[nm][0], hi=VM[nm][1], span=(hi-lo)||1;
      for(let gy=0;gy<G;gy++)for(let gx=0;gx<G;gx++){
        const vv=g[gy]&&g[gy][gx]; if(vv===null||vv===undefined){continue;}
        c.fillStyle=cmap((vv-lo)/span); c.fillRect(gx*6,gy*6,6,6);
      }
    }
  }
  window.addEventListener('load',paint);
""")


def _grid_range(grid) -> tuple:
    vals = [v for row in grid for v in row if v is not None and v == v]
    if not vals:
        return 0.0, 1.0
    return float(min(vals)), float(max(vals))


def render_html(report: dict) -> str:
    field = _esc(report.get("field"))
    header = f"<h1>Spatio-temporal spectral maps — {field}</h1>"
    if not report.get("n_probes") or not report.get("stats","mean")["mean"].get("coverage"):
        return (_DOC.replace("__TITLE__", field)
                .replace("__HEADER__", header, 1)
                .replace("__BODY__", "<p>No data.</p>", 1))
    summ = [
        ("field", report["field"]), ("source", report["source"]),
        ("probes", report["n_probes"]), ("cycles", report["n_cycles"]),
        ("frames analysed", report["n_frames"]), ("vertices", report["n_vertices"]),
        ("k", report["k"]), ("p", report["p"]), ("neighbors", report["neighbors"]),
        ("dt", report["dt"]), ("nyquist", report["nyquist"]),
        ("preview grid", f"{report['preview']}×{report['preview']}"),
    ]
    summ_html = "<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
        for k, v in summ) + "</table>"

    metas = [("mean", "Time-mean field"), ("rms", "Fluctuation RMS"),
             ("intensity", "Fluctuation intensity rms/|mean|"),
             ("freq", "Dominant frequency (Hz)")]
    prevs = report.get("previews", {})
    maps_js = {name: [[None if v != v else float(v) for v in row]
                      for row in prevs.get(name, [])] for name, *_ in metas}
    vm_js = {name: list(_grid_range(prevs.get(name, []))) for name, *_ in metas}
    g = max(4, int(report["preview"]))
    canvas_rows = ""
    for name, title in metas:
        st = report["stats"].get(name, {})
        block = (f"<h2>{_esc(title)}</h2>" +
                 "<div style='margin:6px 0;color:#666;font-size:12px'>" +
                 f"min {_f(st.get('min'))} · max {_f(st.get('max'))} · " +
                 f"mean {_f(st.get('mean'))} · finite {_f(st.get('finite_fraction'))}</div>" +
                 f'<canvas id="cv_{name}" width="{g*6}" height="{g*6}"></canvas>')
        canvas_rows += block
    js = (_DRAW_JS
          .replace("__MAPS__", json.dumps(maps_js))
          .replace("__VM__", json.dumps(vm_js))
          .replace("__GRID__", str(g))
          .replace("__NAMES__", json.dumps([n for n, _ in metas])))
    body = ("<h2>Summary</h2>" + summ_html +
            "<h2>Spectral maps</h2>" + canvas_rows +
            "<script>" + js + "</script>")
    return (_DOC.replace("__TITLE__", field)
            .replace("__HEADER__", header, 1)
            .replace("__BODY__", body, 1))


_DOC = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Spectral maps — __TITLE__</title><style>
  body{font-family:system-ui,sans-serif;margin:24px;color:#1a1a1a}
  h1{font-size:22px}h2{font-size:16px;margin:22px 0 8px}
  table{border-collapse:collapse;margin:6px 0}
  th,td{border:1px solid #d0d0d0;padding:4px 10px;font-size:13px;text-align:right}
  th{background:#f4f4f4;text-align:left}
  canvas{border:1px solid #ddd;margin-top:8px}
</style></head><body>
__HEADER____BODY__
</body></html>"""


# ── I/O / CLI ──────────────────────────────────────────────────────────────


def write_spectral_report(verts: np.ndarray, artifact: dict, out_dir: str, *,
                          cycles=None, step: int = 1, frames=None, k=None,
                          p: float = 2.0, neighbors: int = 4,
                          source: str = "pod", preview: int = 24, dt=None,
                          field: str = "") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = field or artifact.get("name") or "field"
    safe = _safe(name)
    rep = build_spectral_report(verts, artifact, cycles=cycles, step=step,
                                frames=frames, k=k, p=p, neighbors=neighbors,
                                source=source, preview=preview, dt=dt)
    (out / f"{safe}_spectral.html").write_text(render_html(rep), encoding="utf-8")
    slim = {"field": name, "source": rep["source"], "k": rep["k"],
            "n_probes": rep["n_probes"], "n_cycles": rep["n_cycles"],
            "n_frames": rep["n_frames"], "n_vertices": rep["n_vertices"],
            "dt": rep["dt"], "nyquist": rep["nyquist"],
            "preview": rep["preview"], "extent": rep["extent"],
            "stats": rep["stats"],
            "previews": {nm: [[None if v != v else float(v) for v in row]
                              for row in grd]
                         for nm, grd in rep["previews"].items()}}
    with open(out / f"{safe}_spectral.json", "w", encoding="utf-8") as fh:
        json.dump(slim, fh, indent=2)
    vert = np.asarray(verts, dtype=np.float64)
    m = rep["maps"]
    with open(out / f"{safe}_spectral_nodes.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["node", "x", "y", "z", "mean", "rms", "intensity", "freq"])
        for i in range(len(vert)):
            w.writerow([i, f"{vert[i][0]:.6g}", f"{vert[i][1]:.6g}",
                        f"{vert[i][2]:.6g}",
                        *_col(m["mean"], i), *_col(m["rms"], i),
                        *_col(m["intensity"], i), *_col(m["freq"], i)])
    summ = {"field": name, "html": f"{safe}_spectral.html",
            "json": f"{safe}_spectral.json", "csv": f"{safe}_spectral_nodes.csv",
            "source": rep["source"], "n_frames": rep["n_frames"],
            "n_cycles": rep["n_cycles"], "k": rep["k"], "dt": rep["dt"],
            "nyquist": rep["nyquist"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summ, fh, indent=2)
    return summ


def _col(arr, i) -> tuple:
    val = arr[i]
    return (f"{float(val):.6g}",) if np.isfinite(val) else ("",)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.spectralmap",
        description="FlowViewer R58 spatio-temporal spectral maps report")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("verts", help=".npy or .json (N,3) vertex array")
    ap.add_argument("--source", choices=("pod", "dmd"), default="pod")
    ap.add_argument("--cycles", default=None,
                    help="cycle range 'A:B' (optional, default full; step via --step)")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--frames", type=int, default=None,
                    help="optional cap on analysed frames (default: full window)")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--p", type=float, default=2.0)
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--preview", type=int, default=24)
    ap.add_argument("--dt", type=float, default=None,
                    help="sample interval override (default: mean_dt(cycles))")
    ap.add_argument("--out", default="spectralmap_out")
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
        summary = write_spectral_report(verts, art, args.out, cycles=cycles,
                                        step=args.step, frames=args.frames, k=args.k,
                                        p=args.p, neighbors=args.neighbors,
                                        source=args.source, preview=args.preview,
                                        dt=args.dt)
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
