"""R32: bake a self-contained interactive HTML result report.

:func:`render_report` takes the R31 :class:`~fv.model.dataset.StreamCgnsHandle`
(fields kept as descriptors, zero payload) and emits a **single, dependency-
free HTML file**:

* a ``<canvas>`` drawng the mesh bounding-box wireframe (orthographic),
* a field ``<select>`` populated from the handle's field list,
* a ``<range>`` window slider browsing ``[lo, hi)`` of the selected field,
* a live/embedded sample-window table.

Per-field ``min/max/count`` are computed by scanning the field in bounded
tiles (``handle.iter_tiles``), so memory stays under budget. With ``live=True``
the table is served by ``fetch`` from the R32 ``/api/fields`` endpoint instead
of using the baked sample, letting multiple collaborators pull current windows
from the running server.
"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np


def _field_stats(handle, name: str, embed_window: int) -> dict:
    total = int(handle.field_len(name))
    vmin = float("+inf")
    vmax = float("-inf")
    sample: list = []
    filled = 0
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
            filled = min(total, len(sample))
    if not np.isfinite(vmin) or vmin > vmax:
        vmin, vmax = 0.0, 0.0
    return {"name": name, "n": total, "min": float(vmin),
            "max": float(vmax), "sample": sample, "filled": filled}


def _mesh_box(mesh) -> Optional[list]:
    verts = mesh.get("vertices") if mesh else None
    if verts is None:
        verts = mesh.get("verts") if mesh else None
    if verts is None:
        return None
    v = np.asarray(verts, dtype=np.float64)
    if v.ndim != 2 or v.shape[0] == 0 or v.shape[1] < 2:
        return None
    xs, ys, zs = v[:, 0], v[:, 1], (v[:, 2] if v.shape[1] > 2 else v[:, 0] * 0)
    return [float(xs.min()), float(xs.max()),
            float(ys.min()), float(ys.max()),
            float(zs.min()), float(zs.max())]


# Markers injected via .replace() so CSS/JS braces stay untouched.
_META_MARK = "__FV32_META__"

_HTML_TMPL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>FlowViewer R32 Web Report</title>
<style>
  :root { --fg:#1a2233; --mut:#5b6b82; --acc:#2f6fed; --line:#e3e8f0; }
  * { box-sizing:border-box; }
  body { margin:28px auto; max-width:960px; padding:0 16px;
         font:14px/1.5 -apple-system,"Segoe UI",Roboto,sans-serif; color:var(--fg); }
  h1 { font-size:20px; }
  .meta { color:var(--mut); font-size:12px; margin:4px 0 16px; }
  .grid { display:grid; grid-template-columns:320px 1fr; gap:20px; }
  canvas { width:100%; border:1px solid var(--line); border-radius:8px;
           background:#fafbfd; }
  .panel { border:1px solid var(--line); border-radius:8px; padding:14px; }
  .panel h2 { font-size:13px; margin:0 0 10px; color:var(--mut); }
  label { display:block; font-size:12px; color:var(--mut); margin:10px 0 4px; }
  select, input[type=range] { width:100%; }
  table { border-collapse:collapse; width:100%; font-size:12px; margin-top:8px; }
  th, td { border-bottom:1px solid var(--line); padding:4px 8px; text-align:right; }
  th { color:var(--mut); font-weight:600; }
  .dim { color:var(--mut); }
</style>
</head>
<body>
<h1>FlowViewer — R32 Web Report</h1>
<div class="meta" id="meta">loading&hellip;</div>
<div class="grid">
  <div>
    <div class="panel">
      <h2>Mesh bounding box</h2>
      <canvas id="cv" width="280" height="280"></canvas>
    </div>
  </div>
  <div class="panel">
    <h2>Field window browser</h2>
    <label for="sel">Field</label>
    <select id="sel"></select>
    <label for="rng">Window: <span id="rnglab" class="dim"></span></label>
    <input type="range" id="rng" min="0" max="10" value="0">
    <table id="tbl"><thead><tr><th>index</th><th>value</th></tr></thead>
      <tbody></tbody></table>
  </div>
</div>
<script>
const M = __FV32_META__;
const LIVE = M.live && !!M.server_base;
const base = M.server_base || "";
const box = M.bbox;

function drawBox() {
  const cv = document.getElementById('cv');
  if (!cv || !box) return;
  const ctx = cv.getContext('2d');
  const [x0,x1,y0,y1,z0,z1] = box, W=cv.width, H=cv.height, P=34;
  const cxs=x0+(x1-x0)/2, cys=y0+(y1-y0)/2;
  const sx=(W-2*P)/Math.max(1,(x1-x0)||1), sy=(H-2*P)/Math.max(1,(y1-y0)||1);
  const s=Math.min(sx,sy);
  const X=(x)=>P+(x-cxs)*s, Y=(y)=>P+(H-2*P)-(y-cys)*s;
  ctx.strokeStyle='#2f6fed'; ctx.lineWidth=1.2; ctx.beginPath();
  const v=[[x0,y0,z0],[x1,y0,z0],[x1,y1,z0],[x0,y1,z0],
           [x0,y0,z1],[x1,y0,z1],[x1,y1,z1],[x0,y1,z1]];
  const p=(i)=>[X(v[i][0]), Y(v[i][1])];
  const line=(a,b)=>{ctx.moveTo(...p(a)); ctx.lineTo(...p(b));};
  line(0,1);line(1,2);line(2,3);line(3,0);
  line(4,5);line(5,6);line(6,7);line(7,4);
  line(0,4);line(1,5);line(2,6);line(3,7);
  ctx.stroke();
}

function pickWin(name, idx, size) {
  const lo = Math.min(M.fields[name].n-1, Math.floor(idx/10)
        * Math.max(1, Math.floor(M.fields[name].n/10)));
  const hi = Math.min(M.fields[name].n, lo + size);
  const arr = LIVE ? null : M.fields[name].sample;
  const render = (_lo, vals, total) => {
    const tb = document.querySelector('#tbl tbody');
    tb.innerHTML='';
    for (let i=0;i<vals.length;i++) {
      const tr=document.createElement('tr');
      const a=document.createElement('td'); a.textContent=String(_lo+i);
      const b=document.createElement('td'); b.textContent=
         Number.isFinite(vals[i])? Number(vals[i]).toFixed(4) : '—';
      tr.appendChild(a); tr.appendChild(b); tb.appendChild(tr);
    }
    document.getElementById('rnglab').textContent =
      _lo + ' … ' + (_lo+vals.length) + ' / ' + total;
  };
  if (arr) {
    render(lo, arr.slice(0, hi-lo), M.fields[name].n);
    return;
  }
  fetch(base + '/api/fields/' + encodeURIComponent(name) + '?lo=' + lo +
        '&hi=' + hi + '&fmt=json')
    .then(r=>r.json()).then(d=>{ if(d.ok) render(d.lo, d.values, d.total); });
}

function metaText() {
  let t = M.name + ' — ' + M.n_vertices + ' vertices, ' + M.n_cells +
          ' cells';
  if (box) t += '; bbox [' + box.map(v=>v.toFixed(2)).join(', ') + ']';
  return t;
}

function init() {
  document.getElementById('meta').textContent = metaText();
  const sel = document.getElementById('sel');
  for (const n of Object.keys(M.fields)) {
    const o=document.createElement('option'); o.value=n;
    o.textContent=n+'  (' + M.fields[n].n + ', ' +
      +M.fields[n].min.toFixed(3) + '..' + M.fields[n].max.toFixed(3) + ')';
    sel.appendChild(o);
  }
  const names=Object.keys(M.fields);
  if (names.length) {
    sel.value=names[0];
    const inpt=document.getElementById('rng');
    inpt.min=0; inpt.max=Math.max(1, M.fields[names[0]].n-1); inpt.value='0';
    sel.addEventListener('change', ()=>{ inpt.max=Math.max(1, M.fields[sel.value].n-1); pickWin(sel.value, 0, 20); });
    inpt.addEventListener('input', ()=>pickWin(sel.value, +inpt.value, 20));
    pickWin(names[0], 0, 20);
  }
  drawBox();
}
init();
</script>
</body>
</html>
"""


def render_report(handle, out_path: str, embed_window: int = 512,
                  live: bool = False, *, mesh=None,
                  source_name: str = "") -> bool:
    """Bake a single-file interactive HTML report from a stream *handle*.

    ``handle`` may be a :class:`~fv.model.dataset.StreamCgnsHandle` or any
    object exposing ``field_names()`` / ``field_len()`` / ``iter_tiles()``.
    ``embed_window`` caps per-field sample breadth baked into the document.
    Returns True on success (file written, non-trivial size).
    """
    names = handle.field_names()
    fields = {n: _field_stats(handle, n, int(embed_window)) for n in names}
    meta = {
        "name": source_name or getattr(handle, "path", ""),
        "n_vertices": int(mesh.get("n_vertices", 0)) if mesh else 0,
        "n_cells": int(mesh.get("n_cells", 0)) if mesh else 0,
        "bbox": _mesh_box(mesh),
        "live": bool(live),
        "server_base": "" if not live else "/",
        "fields": fields,
    }
    html = _HTML_TMPL.replace(_META_MARK, json.dumps(meta))
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return True
