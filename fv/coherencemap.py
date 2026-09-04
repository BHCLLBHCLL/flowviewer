"""R59: spatio-temporal co-oscillation (coherence) field map.

R58 maps a *per-vertex* frequency picture (mean / rms / dominant freq) onto the
whole reconstructed field. R59 adds the **spatial-correlation** axis: it lifts
R42's probe-pair Welch magnitude-squared *coherence* to the whole mesh, so every
vertex's reconstructed frame sequence (R57) is cohered against a **reference
probe** and four scalars land back on the domain — peak coherence (0..1), the
frequency at which that peak occurs, the mean coherence over positive freqs, and
the cross-spectrum phase at the peak (spatially revealing propagation). This is
R47's "coherent probe group" extrapolated to a *continuous* region, and it is
orthogonal to R58's single-point spectra; together with R52 (modal weights) and
R58 (per-point spectra) it completes the "probe-level quantity -> whole-field"
lifting family.

Pure NumPy + standard HTML/Canvas, headless. Reuses R57 ``reconstruct_sequence`` /
``binned_preview`` / ``_safe`` / ``_stats``, R58 ``_DRAW_JS``/``_grid_range`` and
R41 ``mean_dt``; the Welch algorithm mirrors R42 ``coherence`` but vectorised
over a vertex chunk (``blocksize``).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from .relate import DEFAULT_NPSEG
from .spatialanim import _f, _safe, _stats, binned_preview, reconstruct_sequence
from .spectralmap import _DRAW_JS, _esc, _grid_range
from .spectrum import mean_dt


def _empty_field(n: int, dt) -> dict:
    nan = np.full(n, np.nan) if n else np.empty((0,), dtype=np.float64)
    zer = np.full(n, np.nan) if n else np.empty((0,), dtype=np.float64)
    return {"peak_freq": nan, "peak_coherence": zer, "mean_coherence": zer,
            "phase": nan, "nseg": 0, "nperseg": 0, "dt": float(dt or 1.0),
            "nyquist": 0.0}


def coherence_field(vert_frames, ref, *, nperseg=None, dt=1.0, overlap=0.5,
                    blocksize=4096) -> dict:
    """Welch magnitude-squared coherence of each vertex series vs ``ref``.

    ``vert_frames`` is ``(M, N)``; ``ref`` is ``(M,)``. Returns per-vertex
    ``peak_coherence`` / ``peak_freq`` / ``mean_coherence`` / ``phase`` (angle of
    the cross spectrum at the peak bin) + ``nseg`` / ``nperseg`` / ``dt`` /
    ``nyquist``. Vertices with fewer than two finite samples, or the degenerate
    (M<2 / nperseg<2 / N==0) cases, collapse to all-NaN maps.
    """
    A = np.asarray(vert_frames, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64).ravel()
    if A.ndim != 2 or A.shape[0] == 0 or A.shape[1] == 0:
        return _empty_field(A.shape[1] if A.ndim == 2 else 0, dt)
    M, N = A.shape
    if ref.size != M:
        raise ValueError("ref length must equal the number of frames")
    mask = np.isfinite(A) & np.isfinite(ref)[:, None]
    good = mask.sum(axis=0) >= 2
    nperseg = int(nperseg) if nperseg else min(DEFAULT_NPSEG, M)
    nperseg = int(min(nperseg, M))
    if nperseg < 2:
        return _empty_field(N, dt)
    step = max(1, int(nperseg * (1.0 - overlap)))
    starts = list(range(0, M - nperseg + 1, step))
    nseg = len(starts)
    fn = nperseg // 2 + 1
    freqs = np.fft.rfftfreq(nperseg, d=float(dt))
    pos = np.flatnonzero(freqs > 0)
    peak_freq = np.full(N, np.nan)
    peak_c = np.full(N, np.nan)
    mean_c = np.full(N, np.nan)
    phase = np.full(N, np.nan)
    if nseg == 0 or pos.size == 0:
        return _empty_field(N, dt)
    blk = max(1, int(blocksize))
    for b0 in range(0, N, blk):
        b = slice(b0, min(N, b0 + blk))
        sub = A[:, b]
        Nb = sub.shape[1]
        pxx = np.zeros((fn, Nb))
        pyy = np.zeros(fn)
        pxy = np.zeros((fn, Nb), dtype=np.complex128)
        for s in starts:
            w = sub[s:s + nperseg].copy()
            w -= np.nanmean(w, axis=0)[None, :]
            np.nan_to_num(w, copy=False, nan=0.0)
            wr = ref[s:s + nperseg].copy()
            wr = wr - np.nanmean(wr)
            np.nan_to_num(wr, copy=False, nan=0.0)
            fw = np.fft.rfft(w, axis=0)
            fr = np.fft.rfft(wr, axis=0)
            scale = nperseg
            pxx += np.abs(fw) ** 2 / scale
            pyy += np.abs(fr) ** 2 / scale
            pxy += fw * np.conj(fr)[:, None] / scale
        pxx /= nseg
        pyy /= nseg
        pxy /= nseg
        mscoh = np.zeros((fn, Nb))
        denom = pxx * pyy[:, None]
        np.divide(np.abs(pxy) ** 2, denom, out=mscoh, where=denom > 0)
        sub_pos = mscoh[pos, :]
        jj = np.argmax(sub_pos, axis=0)
        kk = pos[jj]
        peak_c[b] = sub_pos[jj, np.arange(Nb)]
        peak_freq[b] = freqs[kk]
        mean_c[b] = np.nanmean(sub_pos, axis=0)
        phase[b] = np.angle(pxy[kk, np.arange(Nb)])
    for arr in (peak_freq, peak_c, mean_c, phase):
        arr[~good] = np.nan
    return {"peak_freq": peak_freq, "peak_coherence": peak_c,
            "mean_coherence": mean_c, "phase": phase, "nseg": nseg,
            "nperseg": nperseg, "dt": float(dt), "nyquist": float(freqs[-1])}


# ── report construction ─────────────────────────────────────────────────────


def _subsample(cycle_idx, frames):
    if frames is None or len(cycle_idx) <= frames:
        return list(cycle_idx)
    m = len(cycle_idx)
    keep = sorted({round(i * (m - 1) / (frames - 1)) for i in range(frames)})
    return [cycle_idx[i] for i in keep]


def build_coherence_report(verts: np.ndarray, artifact: dict, *,
                           ref_probe: int = 0, cycles=None, step: int = 1,
                           frames=None, k=None, p: float = 2.0,
                           neighbors: int = 4, source: str = "pod",
                           preview: int = 24, nperseg=None, dt=None,
                           blocksize: int = 4096) -> dict:
    """Digest vertices + an R38 trace artifact into a coherence-map report dict."""
    v = np.asarray(verts, dtype=np.float64)
    N = v.shape[0]
    probes = list(artifact.get("probes", []))
    n_cycles = int(len(list(artifact.get("cycles", []))))
    field = artifact.get("name") or ""
    base = {"field": field, "source": source, "ref_probe": int(ref_probe),
            "n_probes": len(probes), "n_cycles": n_cycles, "n_frames": 0,
            "n_vertices": N, "k": int(k) if k else None,
            "p": float(p), "neighbors": int(neighbors),
            "nperseg": int(nperseg) if nperseg else None, "nseg": 0,
            "dt": None, "nyquist": 0.0, "preview": int(preview),
            "extent": {"xmin": None, "xmax": None, "ymin": None, "ymax": None},
            "maps": _empty_field(N, dt), "stats": _empty_stats(),
            "previews": {"peak_coherence": [], "peak_freq": [],
                         "mean_coherence": [], "phase": []}}
    if N == 0:
        return base
    x, y = v[:, 0], v[:, 1]
    base["extent"] = {"xmin": float(x.min()), "xmax": float(x.max()),
                      "ymin": float(y.min()), "ymax": float(y.max())}
    if not probes or not n_cycles:
        return base
    rp = int(ref_probe)
    if not (0 <= rp < len(probes)):
        raise ValueError(f"ref_probe={rp} out of range (n_probes={len(probes)})")
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
    ref_all = np.asarray(list(probes[rp].get("values", [])), dtype=np.float64)
    if len(ref_all) < max(idx, default=0) + 1:
        return base
    ref = ref_all[np.asarray(idx, dtype=np.int64)]
    if dt is None:
        try:
            times = np.asarray(list(artifact["cycles"]), dtype=np.float64)[idx]
            dt0 = float(mean_dt(times))
        except (TypeError, ValueError, IndexError):
            dt0 = 1.0
    else:
        dt0 = float(dt)
    cf = coherence_field(seq_frames, ref, nperseg=nperseg, dt=dt0,
                         blocksize=blocksize)
    base["dt"] = cf["dt"]
    base["nyquist"] = cf["nyquist"]
    base["nseg"] = cf["nseg"]
    base["nperseg"] = cf["nperseg"]
    base["n_frames"] = len(seq_frames)
    maps = {"peak_coherence": cf["peak_coherence"], "peak_freq": cf["peak_freq"],
            "mean_coherence": cf["mean_coherence"], "phase": cf["phase"]}
    base["maps"] = maps
    base["stats"] = {name: _stats(arr) for name, arr in maps.items()}
    base["previews"] = {name: binned_preview(v, arr, gridsize=preview)
                        for name, arr in maps.items()}
    return base


def _empty_stats() -> dict:
    e = {"min": None, "max": None, "mean": None, "finite_fraction": 0.0,
         "coverage": 0}
    return {"peak_coherence": dict(e), "peak_freq": dict(e),
            "mean_coherence": dict(e), "phase": dict(e)}


# ── HTML render ─────────────────────────────────────────────────────────────


def render_html(report: dict) -> str:
    field = _esc(report.get("field"))
    header = f"<h1>Coherence field — {field}</h1>"
    if not report.get("n_probes") or not report.get("stats", {}) \
            .get("peak_coherence", {}).get("coverage"):
        return (_DOC.replace("__TITLE__", field)
                .replace("__HEADER__", header, 1)
                .replace("__BODY__", "<p>No data.</p>", 1))
    summ = [
        ("field", report["field"]), ("source", report["source"]),
        ("ref probe", report["ref_probe"]), ("probes", report["n_probes"]),
        ("cycles", report["n_cycles"]), ("frames analysed", report["n_frames"]),
        ("vertices", report["n_vertices"]), ("k", report["k"]),
        ("p", report["p"]), ("neighbors", report["neighbors"]),
        ("nperseg", report["nperseg"]), ("segments", report["nseg"]),
        ("dt", report["dt"]), ("nyquist", report["nyquist"]),
        ("preview grid", f"{report['preview']}×{report['preview']}"),
    ]
    summ_html = "<table>" + "".join(
        f"<tr><th>{_esc(k)}</th><td>{_f(v)}</td></tr>"
        for k, v in summ) + "</table>"

    metas = [("peak_coherence", "Peak coherence with ref probe"),
             ("peak_freq", "Peak-coherence frequency (Hz)"),
             ("mean_coherence", "Mean coherence (f>0)"),
             ("phase", "Cross phase at peak (rad)")]
    prevs = report.get("previews", {})
    maps_js = {name: [[None if v != v else float(v) for v in row]
                      for row in prevs.get(name, [])] for name, _ in metas}
    vm_js = {name: list(_grid_range(prevs.get(name, []))) for name, _ in metas}
    g = max(4, int(report["preview"]))
    canvas_rows = ""
    for name, title in metas:
        st = report["stats"].get(name, {})
        canvas_rows += (f"<h2>{_esc(title)}</h2>" +
                        "<div style='margin:6px 0;color:#666;font-size:12px'>" +
                        f"min {_f(st.get('min'))} · max {_f(st.get('max'))} · " +
                        f"mean {_f(st.get('mean'))} · finite {_f(st.get('finite_fraction'))}</div>" +
                        f'<canvas id="cv_{name}" width="{g*6}" height="{g*6}"></canvas>')
    js = (_DRAW_JS
          .replace("__MAPS__", json.dumps(maps_js))
          .replace("__VM__", json.dumps(vm_js))
          .replace("__GRID__", str(g))
          .replace("__NAMES__", json.dumps([n for n, _ in metas])))
    body = ("<h2>Summary</h2>" + summ_html +
            "<h2>Coherence maps</h2>" + canvas_rows +
            "<script>" + js + "</script>")
    return (_DOC.replace("__TITLE__", field)
            .replace("__HEADER__", header, 1)
            .replace("__BODY__", body, 1))


_DOC = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Coherence field — __TITLE__</title><style>
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


def write_coherence_report(verts: np.ndarray, artifact: dict, out_dir: str, *,
                           ref_probe: int = 0, cycles=None, step: int = 1,
                           frames=None, k=None, p: float = 2.0, neighbors: int = 4,
                           source: str = "pod", preview: int = 24,
                           nperseg=None, dt=None, blocksize: int = 4096,
                           field: str = "") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = field or artifact.get("name") or "field"
    safe = _safe(name)
    rep = build_coherence_report(verts, artifact, ref_probe=ref_probe,
                                 cycles=cycles, step=step, frames=frames, k=k,
                                 p=p, neighbors=neighbors, source=source,
                                 preview=preview, nperseg=nperseg, dt=dt,
                                 blocksize=blocksize)
    (out / f"{safe}_coherence.html").write_text(render_html(rep), encoding="utf-8")
    slim = {"field": name, "source": rep["source"], "ref_probe": rep["ref_probe"],
            "k": rep["k"], "n_probes": rep["n_probes"], "n_cycles": rep["n_cycles"],
            "n_frames": rep["n_frames"], "n_vertices": rep["n_vertices"],
            "nperseg": rep["nperseg"], "nseg": rep["nseg"],
            "dt": rep["dt"], "nyquist": rep["nyquist"],
            "preview": rep["preview"], "extent": rep["extent"],
            "stats": rep["stats"],
            "previews": {nm: [[None if v != v else float(v) for v in row]
                              for row in grd]
                         for nm, grd in rep["previews"].items()}}
    with open(out / f"{safe}_coherence.json", "w", encoding="utf-8") as fh:
        json.dump(slim, fh, indent=2)
    vert = np.asarray(verts, dtype=np.float64)
    m = rep["maps"]
    with open(out / f"{safe}_coherence_nodes.csv", "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["node", "x", "y", "z", "peak_coherence", "peak_freq",
                    "mean_coherence", "phase"])
        for i in range(len(vert)):
            w.writerow([i, f"{vert[i][0]:.6g}", f"{vert[i][1]:.6g}",
                        f"{vert[i][2]:.6g}",
                        *_col(m["peak_coherence"], i), *_col(m["peak_freq"], i),
                        *_col(m["mean_coherence"], i), *_col(m["phase"], i)])
    summ = {"field": name, "html": f"{safe}_coherence.html",
            "json": f"{safe}_coherence.json",
            "csv": f"{safe}_coherence_nodes.csv",
            "source": rep["source"], "ref_probe": rep["ref_probe"],
            "n_frames": rep["n_frames"], "n_cycles": rep["n_cycles"],
            "k": rep["k"], "dt": rep["dt"], "nperseg": rep["nperseg"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summ, fh, indent=2)
    return summ


def _col(arr, i) -> tuple:
    val = arr[i]
    return (f"{float(val):.6g}",) if np.isfinite(val) else ("",)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.coherencemap",
        description="FlowViewer R59 co-oscillation (coherence) field map report")
    ap.add_argument("trace_json", help="R38 trace <field>.json (cycles + probes)")
    ap.add_argument("verts", help=".npy or .json (N,3) vertex array")
    ap.add_argument("--ref", type=int, default=0, help="reference probe index")
    ap.add_argument("--source", choices=("pod", "dmd"), default="pod")
    ap.add_argument("--cycles", default=None,
                    help="cycle range 'A:B' (optional, default full; step via --step)")
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--frames", type=int, default=None,
                    help="optional cap on analysed frames (default: full window)")
    ap.add_argument("--k", type=int, default=None)
    ap.add_argument("--p", type=float, default=2.0)
    ap.add_argument("--neighbors", type=int, default=4)
    ap.add_argument("--nperseg", type=int, default=None)
    ap.add_argument("--preview", type=int, default=24)
    ap.add_argument("--dt", type=float, default=None,
                    help="sample interval override (default: mean_dt(cycles))")
    ap.add_argument("--blocksize", type=int, default=4096)
    ap.add_argument("--out", default="coherencemap_out")
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
        summary = write_coherence_report(verts, art, args.out, ref_probe=args.ref,
                                         cycles=cycles, step=args.step,
                                         frames=args.frames, k=args.k, p=args.p,
                                         neighbors=args.neighbors, source=args.source,
                                         preview=args.preview, nperseg=args.nperseg,
                                         dt=args.dt, blocksize=args.blocksize)
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
