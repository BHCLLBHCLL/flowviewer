"""R39: cycle-by-cycle comparison of two time sequences (baseline vs scenario).

R36 reported *one* sequence per field; R38 traced monitoring points along *one*
sequence. R39 closes the compare axis: **two** CGNS sequences compared on their
shared cycles, producing per-field, per-cycle bounded difference metrics
(RMSE / MAE / max-abs / relative-L2) plus a rolled-up summary across cycles.
This is the classic "baseline vs perturbed run" check done headlessly on
streaming data.

The ``compare`` module already does single-dataset abs/signed/relative & IDW
mapping; here the *time* dimension is added. Memory stays bounded: per cycle
the two handles are opened/consumed/released, and each field is diffed a tile
at a time (``ha.iter_tiles`` in lockstep with ``hb.read_window``), so only one
budgeted tile per side is ever live — independent of field length, no full
array, no CGNS/vtk dependency in the core.

Pipeline::

   two SessionTimelines (or (cycle, handle, mesh) iterables)
     → compare_sequences: per common cycle, per field → tile diff
     → report dict → write_compare_files → <field>.json + summary.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Union

import numpy as np

Progress = Optional[Callable[[int, int], None]]


# ── per-field tile diff (bounded) ──────────────────────────────────────────


def field_tile_difference(ha, hb, field: str) -> dict:
    """Bounded per-field difference metrics between two stream handles.

    Walks ``ha.iter_tiles(field)`` and reads the matching window from ``hb``
    (``hb.read_window``), aligned by absolute index — safe even when the two
    sides choose different tile sizes. Only finite A∩B pairs are counted.

    Returns ``{"n", "rmse", "mae", "max", "lrel"}`` (or all NaNs when no
    overlap / field missing).
    """
    if field not in ha.field_names() or field not in hb.field_names():
        return _empty_diff()
    total = min(int(ha.field_len(field)), int(hb.field_len(field)))
    if total <= 0:
        return _empty_diff()

    n = 0
    sumsq = 0.0
    sumabs = 0.0
    rel_ss = 0.0
    maxd = 0.0
    for start, arr in ha.iter_tiles(field):
        end = min(total, start + int(np.asarray(arr).size))
        if end <= start:
            continue
        lo, bwindow = hb.read_window(field, start, end)
        a = np.asarray(arr, dtype=np.float64).ravel()[: end - start]
        b = np.asarray(bwindow, dtype=np.float64).ravel()
        m = np.isfinite(a) & np.isfinite(b)
        if not m.any():
            continue
        a, b = a[m], b[m]
        d = a - b
        cnt = int(d.size)
        n += cnt
        sumsq += float((d * d).sum())
        sumabs += float(np.abs(d).sum())
        rel_ss += float(((d / (np.abs(b) + 1e-30)) ** 2).sum())
        mx = float(np.abs(d).max())
        if mx > maxd:
            maxd = mx
    if n == 0:
        return _empty_diff()
    return {
        "n": n,
        "rmse": float(math.sqrt(sumsq / n)),
        "mae": float(sumabs / n),
        "max": float(maxd),
        "lrel": float(math.sqrt(rel_ss / n)),
    }


def _empty_diff() -> dict:
    nan = float("nan")
    return {"n": 0, "rmse": nan, "mae": nan, "max": nan, "lrel": nan}


# ── cycle-wise sequence compare ────────────────────────────────────────────


def compare_sequences(tl_a, tl_b, fields: Optional[Sequence[str]] = None,
                      on_progress: Optional[Progress] = None) -> dict:
    """Compare two timelines on their (index-aligned) cycles.

    ``tl_a`` / ``tl_b`` are any iterables of ``(cycle, handle, mesh)`` —
    commonly :class:`~fv.session.SessionTimeline` objects of the *same*
    sequence (B vs A), walked in lockstep. When both are empty, returns an
    empty report. ``fields`` restricts the compared fields; by default every
    field present on the first cycle of A is used.

    Returns::

        {"cycles": [...], "fields": {name: {
            "per_cycle": [{"cycle", "n", "rmse", "mae", "max", "lrel"}, ...],
            "summary": {"mean_rmse", "mean_mae", "max_max", "mean_lrel",
                        "max_lrel"}}}}

    A field missing on a given cycle is recorded as all-NaN (skipped in the
    rolling summary) rather than raising.
    """
    it_a = iter(tl_a)
    it_b = iter(tl_b)

    want: Optional[List[str]] = list(fields) if fields else None
    cycles: List[int] = []
    per_field: dict = {}

    done = 0
    for (ca, ha, _ma), (cb, hb, _mb) in zip(it_a, it_b):
        cycles.append(int(ca))
        if want is None:
            want = ha.field_names()
        if not per_field:
            per_field = {f: {"per_cycle": []} for f in want}
        for f in want:
            per_field[f]["per_cycle"].append(
                {"cycle": int(ca), **field_tile_difference(ha, hb, f)})
        done += 1
        if on_progress is not None:
            on_progress(done, done + 1)

    # rolling summary (ignore NaN cycles)
    fields_out = {}
    for f, blk in per_field.items():
        rows = blk["per_cycle"]
        picks = {k: [r[k] for r in rows if np.isfinite(r[k])]
                 for k in ("rmse", "mae", "max", "lrel")}
        fields_out[f] = {
            "per_cycle": rows,
            "summary": {
                "mean_rmse": _mean(picks["rmse"]),
                "mean_mae": _mean(picks["mae"]),
                "max_max": _max(picks["max"]),
                "mean_lrel": _mean(picks["lrel"]),
                "max_lrel": _max(picks["lrel"]),
                "n_cycles": len(rows),
            },
        }
    return {"cycles": cycles, "fields": fields_out}


def _mean(vals: list) -> float:
    return float(sum(vals)) / len(vals) if vals else float("nan")


def _max(vals: list) -> float:
    return float(max(vals)) if vals else float("nan")


# ── I/O ────────────────────────────────────────────────────────────────────


def write_compare_files(report: dict, out_dir: str) -> dict:
    """Write one ``<field>.json`` per field plus ``summary.json``.

    Returns the summary manifest. Files live under *out_dir* (created needed).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "cycles": report["cycles"],
        "fields": {},
        "n_fields": len(report["fields"]),
    }
    for fname, blk in report["fields"].items():
        safe = "".join(ch if ch.isalnum() else "_" for ch in fname) or "field"
        path = out / f"{safe}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"name": fname, **blk}, fh)
        summary["fields"][fname] = {"file": path.name, "summary": blk["summary"]}
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary


def compare_runs(paths_a: Union[str, Sequence[str]],
                 paths_b: Union[str, Sequence[str]], *,
                 fields: Optional[Sequence[str]] = None,
                 out_dir: str = "seqcmp_out", budget_mb: int = 64) -> dict:
    """Open two sequences and write their cycle-by-cycle comparison."""
    from .session import SessionTimeline
    tl_a = SessionTimeline.from_sequence(str(paths_a), budget_mb=budget_mb) \
        if isinstance(paths_a, (str, Path)) else SessionTimeline(list(paths_a))
    tl_b = SessionTimeline.from_sequence(str(paths_b), budget_mb=budget_mb) \
        if isinstance(paths_b, (str, Path)) else SessionTimeline(list(paths_b))
    report = compare_sequences(tl_a, tl_b, fields=fields)
    return write_compare_files(report, out_dir)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.seqcmp", description="FlowViewer R39 sequence-vs-sequence compare")
    ap.add_argument("seq_a", nargs="+", help="sequence A first file / list")
    ap.add_argument("seq_b", nargs="+", help="sequence B first file / list")
    ap.add_argument("--out", default="seqcmp_out")
    ap.add_argument("--fields", nargs="*", default=None)
    ap.add_argument("--budget-mb", type=int, default=64)
    args = ap.parse_args(argv)
    a = args.seq_a if len(args.seq_a) > 1 else args.seq_a[0]
    b = args.seq_b if len(args.seq_b) > 1 else args.seq_b[0]
    summary = compare_runs(a, b, fields=args.fields, out_dir=args.out,
                           budget_mb=args.budget_mb)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    from sys import exit as _exit
    _exit(main())
