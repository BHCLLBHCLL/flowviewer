"""R40: pointwise time-trace comparison of two sequences (per monitoring point).

R38 traced *one* sequence at fixed monitoring points; R39 compared *two*
sequences per *field* (whole-domain). R40 merges the two axes: **compare two
sequences (baseline vs perturb) at the same monitoring points**, per field,
per cycle, keeping the bounded per-tile read model of R38.

The same monitoring points are bound to mesh nodes **once** (from sequence A's
first cycle; both sequences must share the same grid / node ordering, as in a
typical baseline-vs-perturbed pair). Sequence A and B are then walked
cycle-by-cycle, reading only the chosen node rows via the R31 windowed reader,
and the per-probe histories are aligned on the common cycle intersection to
give ``a``, ``b``, per-cycle ``diff`` and a time-rollup of pointwise metrics
(mean/max abs, max relative).

Core functions reuse :mod:`fv.trace` (``resolve_probe_nodes`` /
``field_probe_values``); the whole module is headless-safe, bounded-memory,
and free of CGNS/vtk dependencies in the core.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence, Union

import numpy as np

from .trace import field_probe_values, resolve_probe_nodes

# ── per-sequence trace report with pre-bound nodes ─────────────────────────


def trace_report(tl, nodes, fields: Sequence[str]) -> dict:
    """Walk one timeline and collect per-probe node series (nodes pre-bound).

    ``nodes`` is the list from :func:`fv.trace.resolve_probe_nodes` bound once
    externally (so A and B read the *same* node indices). Returns the R38-style
    structure ``{field: {"name", "cycles", "probes":[{"query","node","xyz",
    "values":[...]}]}}``. A probe reading a missing/out-of-range field yields
    NaN; only the selected node rows are retained (bounded memory).
    """
    fields = list(fields)
    structure = {
        f: {
            "name": f,
            "cycles": [],
            "probes": [
                {"query": p["query"], "node": p["node"], "xyz": p["xyz"],
                 "values": []}
                for p in nodes
            ],
        }
        for f in fields
    }
    for cycle, handle, _mesh in tl:
        for f in fields:
            structure[f]["cycles"].append(int(cycle))
            for p in structure[f]["probes"]:
                p["values"].append(field_probe_values(handle, f, p["node"]))
    return structure


def point_compare(rep_a: dict, rep_b: dict) -> dict:
    """Align two trace reports on their common cycles and diff each probe.

    ``rep_a`` / ``rep_b`` are :func:`trace_report` outputs for the two
    sequences (same bound nodes / same probe order). Returns::

        {"fields": {name: {"cycles": [...common...], "probes": [
            {"query","node","xyz","a":[...],"b":[...],"diff":[...],
             "metrics": {"n","mean_abs","max_abs","max_rel"}}]}}}

    ``a``/``b``/``diff`` line up on the **common** cycles (intersection). Only
    finite A∩B pairs enter ``diff``/metrics; a cycle where A or B is NaN is
    kept in ``a``/``b`` as NaN but excluded from the difference (masks it).
    """
    common = [f for f in rep_a if f in rep_b]
    fields_out: dict = {}
    for f in common:
        fa, fb = rep_a[f], rep_b[f]
        ia = {c: i for i, c in enumerate(fa["cycles"])}
        ib = {c: i for i, c in enumerate(fb["cycles"])}
        cycles = [c for c in fa["cycles"] if c in ib]
        probes_out = []
        for pa, pb in zip(fa["probes"], fb["probes"]):
            aval = [pa["values"][ia[c]] if c in ia else float("nan")
                    for c in cycles]
            bval = [pb["values"][ib[c]] if c in ib else float("nan")
                    for c in cycles]
            diff, metrics = _diff_series(aval, bval)
            probes_out.append({
                "query": pa["query"],
                "node": pa["node"],
                "xyz": pa["xyz"],
                "a": aval,
                "b": bval,
                "diff": diff,
                "metrics": metrics,
            })
        fields_out[f] = {"cycles": cycles, "probes": probes_out}
    return {"fields": fields_out}


def _diff_series(a: list, b: list) -> tuple:
    """Align finite pairs -> (diff list, metrics dict)."""
    n = 0
    sum_abs = 0.0
    max_abs = 0.0
    max_rel = 0.0
    diff = []
    for x, y in zip(a, b):
        if not (np.isfinite(x) and np.isfinite(y)):
            diff.append(float("nan"))
            continue
        d = float(x - y)
        diff.append(d)
        ad = abs(d)
        n += 1
        sum_abs += ad
        if ad > max_abs:
            max_abs = ad
        rel = ad / (abs(y) + 1e-30)
        if rel > max_rel:
            max_rel = rel
    metrics = {
        "n": n,
        "mean_abs": float(sum_abs / n) if n else float("nan"),
        "max_abs": float(max_abs) if n else float("nan"),
        "max_rel": float(max_rel) if n else float("nan"),
    }
    return diff, metrics


# ── I/O ────────────────────────────────────────────────────────────────────


def write_point_compare(report: dict, out_dir: str) -> dict:
    """Write one ``<field>.json`` per field plus ``summary.json``.

    Returns the summary manifest. Files live under *out_dir* (created needed).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {"fields": {}, "n_fields": len(report["fields"])}
    for fname, blk in report["fields"].items():
        safe = "".join(ch if ch.isalnum() else "_" for ch in fname) or "field"
        with open(out / f"{safe}.json", "w", encoding="utf-8") as fh:
            json.dump({"name": fname, **blk}, fh)
        p0 = blk["probes"][0]["metrics"] if blk["probes"] else {}
        summary["fields"][fname] = {
            "file": f"{safe}.json",
            "cycles": len(blk["cycles"]),
            "probes": len(blk["probes"]),
            "sample": p0,
        }
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def point_compare_runs(paths_a: Union[str, Sequence[str]],
                       paths_b: Union[str, Sequence[str]], probes: Sequence,
                       fields: Optional[Sequence[str]] = None, *,
                       out_dir: str = "pointcmp_out", budget_mb: int = 64) -> dict:
    """Open two sequences at monitoring points, write their compare bundle."""
    from .session import SessionTimeline
    tl_a = SessionTimeline.from_sequence(str(paths_a), budget_mb=budget_mb) \
        if isinstance(paths_a, (str, Path)) else SessionTimeline(list(paths_a))
    tl_b = SessionTimeline.from_sequence(str(paths_b), budget_mb=budget_mb) \
        if isinstance(paths_b, (str, Path)) else SessionTimeline(list(paths_b))
    # bind nodes once from A's first cycle mesh
    nodes = None
    for _cyc, _h, mesh in tl_a:
        nodes = resolve_probe_nodes(mesh, probes)
        break
    if nodes is None:
        raise ValueError("sequence A has no cycles")
    wants = list(fields) if fields else None
    if wants is None:
        for _cyc, h, _m in tl_a:
            wants = h.field_names()
            break
    rep_a = trace_report(tl_a, nodes, wants or [])
    rep_b = trace_report(tl_b, nodes, wants or [])
    report = point_compare(rep_a, rep_b)
    return write_point_compare(report, out_dir)


def _parse_probe(s: str):
    try:
        return tuple(float(x) for x in s.split(","))
    except Exception:  # noqa: BLE001
        raise ValueError(f"bad probe point {s!r} (expect 'x,y,z')") from None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.pointcmp",
        description="FlowViewer R40 monitoring-point sequence-vs-sequence compare")
    ap.add_argument("seq_a", nargs="+", help="sequence A first file / list")
    ap.add_argument("seq_b", nargs="+", help="sequence B first file / list")
    ap.add_argument("--out", default="pointcmp_out")
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
    a = args.seq_a if len(args.seq_a) > 1 else args.seq_a[0]
    b = args.seq_b if len(args.seq_b) > 1 else args.seq_b[0]
    summary = point_compare_runs(a, b, probes, fields=args.fields,
                                 out_dir=args.out, budget_mb=args.budget_mb)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
