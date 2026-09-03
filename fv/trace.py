"""R38: field-value over time at monitoring points (probe history / time trace).

The R36 temporal report scanned *every* field into *bounded* statistics; the
R37 data cursor grabbed values at a *single* point on a *single* dataset.
R38 closes the gap between them: **monitoring-point histories** — a handful of
fixed points probed across the whole CGNS *time sequence*, producing a
``field -> probes -> series over cycles`` table. This is the classic "probe
points / 监测点历程" workflow: place sensors once, read their field values at
every time step, and get back a per-probe time series.

It reuses the R31 windowed reader (``StreamCgnsHandle.iter_tiles``) so a cycle
is consumed tile-by-tile and only the *selected* node rows are kept — peak
memory stays ``~ one budgeted tile``, independent of field length. Point→node
binding uses R37's pure-NumPy ``nearest_point`` (no VTK, no ``vtkCutter``), so
the whole module verifies headless and dependency-light.

Pipeline::

   timeline (cycle, handle, mesh) ──► bind probe→node once (first cycle)
        └► per cycle, per field, via iter_tiles: keep only node rows
   → report dict → write_probe_json + manifest.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional, Sequence, Union

import numpy as np

from .render.probe import nearest_point

# ── probe → node binding ───────────────────────────────────────────────────


def resolve_probe_nodes(mesh, points) -> List[dict]:
    """Map each monitoring point to the nearest mesh node.

    ``mesh`` only needs a ``"vertices"`` array (as produced by every streaming
    open). Returns one entry per point: ``{"query", "node", "xyz"|None}``. A
    point on an empty/degenerate mesh resolves to ``node=-1, xyz=None`` (its
    series reads as NaN) rather than failing.
    """
    verts = np.asarray(mesh.get("vertices"), dtype=np.float64) \
        if mesh is not None and mesh.get("vertices") is not None \
        else np.zeros((0, 3), dtype=np.float64)
    if verts.ndim != 2 or verts.shape[0] == 0:
        return [{"query": tuple(float(v) for v in p), "node": -1, "xyz": None}
                for p in points]
    out: List[dict] = []
    for p in points:
        idx, _sq = nearest_point(verts, p)
        if idx < 0:
            out.append({"query": tuple(float(v) for v in p),
                        "node": -1, "xyz": None})
        else:
            out.append({"query": tuple(float(v) for v in p),
                        "node": int(idx),
                        "xyz": tuple(float(v) for v in verts[idx])})
    return out


# ── per-field per-cycle probe values ───────────────────────────────────────


def field_probe_values(handle, name: str, node: int) -> float:
    """Read the value of field *name* at node index *node* (bounded).

    Iterates ``handle.iter_tiles(name)`` and keeps only the tile covering
    *node*, so no whole field is ever materialised. A missing field, an
    out-of-range node, or an empty read yields ``nan``.
    """
    if name not in handle.field_names():
        return float("nan")
    total = int(handle.field_len(name))
    if node < 0 or node >= total:
        return float("nan")
    for start, arr in handle.iter_tiles(name):
        if start <= node < start + int(arr.size):
            a = np.asarray(arr, dtype=np.float64)
            v = a[node - start]
            # a node "value" may be a vector row -> keep its first component
            return float(v[0]) if np.ndim(v) else float(v)
    return float("nan")


# ── main trace walk ────────────────────────────────────────────────────────


def time_trace(timeline, probes: Sequence, fields: Sequence[str]) -> dict:
    """Walk *timeline* and record each field's series at each monitoring point.

    ``timeline`` is any iterable of ``(cycle, handle, mesh)`` — commonly a
    :class:`~fv.session.SessionTimeline` (open/consume/release per cycle) or a
    handcrafted list of ``(cycle, fake_handle, fake_mesh)`` for headless tests.
    Probe→node indices are bound on the **first** cycle's mesh (node ordering
    is stable across a CGNS series) and reused thereafter.

    Returns a self-describing report::

        {"fields": {name: {"name", "cycles": [...], "probes":
            [{"query", "node", "xyz", "values": [...]} , ...]}}}

    Memory stays bounded: per cycle only a budgeted tile per field is live, and
    only the chosen node rows are retained.
    """
    fields = [f for f in fields]
    structure: dict = {}
    cycles: List[int] = []

    first = True
    for cycle, handle, mesh in timeline:
        cycles.append(int(cycle))
        if first:
            probes_n = resolve_probe_nodes(mesh, probes)
            for f in fields:
                structure[f] = {
                    "name": f,
                    "cycles": [],
                    "probes": [
                        {"query": p["query"], "node": p["node"],
                         "xyz": p["xyz"], "values": []}
                        for p in probes_n
                    ],
                }
            first = False
        for f in fields:
            for p in structure[f]["probes"]:
                p["values"].append(field_probe_values(handle, f, p["node"]))

    for f in fields:
        structure[f]["cycles"] = list(cycles)
    return {"fields": structure}


# ── I/O ────────────────────────────────────────────────────────────────────


def write_traces(report: dict, out_dir: str) -> dict:
    """Write one ``<field>.json`` per field plus ``manifest.json``.

    Returns the manifest. Files live under *out_dir* (created if missing).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"fields": {}}
    for fname, finfo in report["fields"].items():
        safe = "".join(ch if ch.isalnum() else "_" for ch in fname) or "field"
        path = out / f"{safe}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(finfo, fh)
        manifest["fields"][fname] = {
            "file": path.name,
            "cycles": len(finfo["cycles"]),
            "probes": len(finfo["probes"]),
        }
    with open(out / "manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


def run_traces(paths: Union[str, Sequence[str]], probes: Sequence,
               fields: Optional[Sequence[str]] = None, *,
               out_dir: str = "trace_out", budget_mb: int = 64) -> dict:
    """Full R38 entry: open a sequence, produce traces, write outputs.

    ``paths`` is a sequence first file / explicit list (same contract as
    :func:`fv.present.sequence_report`). Returns the manifest.
    """
    from .session import SessionTimeline
    if isinstance(paths, (str, Path)):
        tl = SessionTimeline.from_sequence(str(paths), budget_mb=budget_mb)
    else:
        tl = SessionTimeline(list(paths), budget_mb=budget_mb)
    wants = list(fields) if fields else []
    # default: all fields present on the first cycle
    if not wants:
        _cyc, handle, _mesh = next(iter(tl))
        wants = handle.field_names()
        tl = SessionTimeline.from_sequence(str(paths), budget_mb=budget_mb) \
            if isinstance(paths, (str, Path)) else SessionTimeline(list(paths))
    report = time_trace(tl, probes, wants)
    return write_traces(report, out_dir)


def _parse_probe(s: str):
    try:
        return tuple(float(x) for x in s.split(","))
    except Exception:  # noqa: BLE001
        raise ValueError(f"bad probe point {s!r} (expect 'x,y,z')") from None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.trace", description="FlowViewer R38 monitoring-point time traces")
    ap.add_argument("paths", nargs="+", help="sequence dir / first file / list")
    ap.add_argument("--out", default="trace_out")
    ap.add_argument("--probe", action="append", dest="probes", default=[],
                    help="monitoring point 'x,y,z' (repeatable)")
    ap.add_argument("--probes-file", default=None,
                    help="text file of 'x,y,z' per line")
    ap.add_argument("--fields", nargs="*", default=None)
    ap.add_argument("--budget-mb", type=int, default=64)
    args = ap.parse_args(argv)

    probes = [_parse_probe(p) for p in args.probes]
    if args.probes_file:
        with open(args.probes_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    probes.append(_parse_probe(line))
    if not probes:
        print("error: no monitoring points (--probe x,y,z or --probes-file)",
              file=__import__("sys").stderr)
        return 2
    paths = args.paths if len(args.paths) > 1 else args.paths[0]
    manifest = run_traces(paths, probes, fields=args.fields, out_dir=args.out,
                          budget_mb=args.budget_mb)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
