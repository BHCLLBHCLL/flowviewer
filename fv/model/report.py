"""Multi-dataset statistics and automated reporting (R20, beyond-scPOST).

Aggregates scalar statistics across any number of FieldFile datasets (e.g.
consecutive cycles / multiple FileSets) and emits a flat table that can be
written to CSV for automated post-processing:

- ``dataset_stats``   per-variable min/max/mean/rms/std/n for one dataset;
- ``aggregate_report`` rows (dataset, var) of those stats across all datasets;
- ``delta_report``     rows (dataset, var) of the difference against a
  reference dataset (|A - ref| by default; ``mode`` supports signed/relative);
- ``to_csv``           serialize any report table to a CSV string.

Statistics are computed over finite values only, matching the element-wise
norms used elsewhere in the model.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from typing import Dict, List, Optional

import numpy as np

from .dataset import FieldFile

_STAT_KEYS = ("n", "min", "max", "mean", "rms", "std")


def _stats(arr) -> Dict[str, float]:
    a = np.asarray(arr, dtype=np.float64).ravel()
    v = a[np.isfinite(a)]
    if v.size == 0:
        return {"n": int(a.size), "min": 0.0, "max": 0.0,
                "mean": 0.0, "rms": 0.0, "std": 0.0}
    return {"n": int(a.size), "min": float(v.min()), "max": float(v.max()),
            "mean": float(v.mean()), "rms": float(np.sqrt(np.mean(v ** 2))),
            "std": float(v.std())}


def _label(ff: FieldFile, index: int, labels: Optional[Iterable[str]] = None) -> str:
    if labels is not None:
        labels = list(labels)
        if index < len(labels) and labels[index]:
            return str(labels[index])
    path = getattr(ff, "path", None)
    if path:
        p = str(path).replace("\\\\", "/")
        return p.rsplit("/", 1)[-1]
    return f"#{index}"


def _shared_vars(ffs: List[FieldFile], variables: Optional[Iterable[str]] = None) -> List[str]:
    if variables is not None:
        return list(variables)
    return sorted(set().union(*[set(f.variables) for f in ffs]))


def dataset_stats(ff: FieldFile,
                  variables: Optional[Iterable[str]] = None) -> Dict[str, dict]:
    """Per-variable ``{var: {location, kind, n, min, max, mean, rms, std}}``."""
    out: Dict[str, dict] = {}
    for name in _shared_vars([ff], variables):
        arr = ff.variable_array(name)
        vi = ff.variables.get(name)
        if arr is None or vi is None:
            continue
        row = {"var": name, "location": vi.location, "kind": vi.kind}
        row.update(_stats(arr))
        out[name] = row
    return out


def aggregate_report(datasets: List[FieldFile],
                     variables: Optional[Iterable[str]] = None,
                     labels: Optional[Iterable[str]] = None) -> List[dict]:
    """Flat table row-per-(dataset, variable) of scalar statistics."""
    rows: List[dict] = []
    names = _shared_vars(datasets, variables)
    for didx, ff in enumerate(datasets):
        lab = _label(ff, didx, labels)
        for name in names:
            arr = ff.variable_array(name)
            vi = ff.variables.get(name)
            if arr is None or vi is None:
                continue
            row = {"dataset": lab, "var": name, "location": vi.location,
                   "kind": vi.kind}
            row.update(_stats(arr))
            rows.append(row)
    return rows


def _ref_array(datasets, reference, name):
    arr = datasets[reference].variable_array(name)
    if arr is None:
        return None
    return np.asarray(arr, dtype=np.float64)


def delta_report(datasets: List[FieldFile], reference: int = 0,
                 mode: str = "abs", mapping: str = "nearest",
                 variables: Optional[Iterable[str]] = None,
                 labels: Optional[Iterable[str]] = None) -> List[dict]:
    """Distance of every dataset against the ``reference`` one, per variable.

    ``mode``: ``abs`` (|A - ref|, default), ``signed`` (A - ref), ``relative``
    ((A - ref)/(|ref| + eps)).  Datasets whose mesh does not share the
    reference shape are mapped onto it (reusing :func:`compare.difference_field`
    semantics).  Rows: ``(dataset, var, location, kind, n, min, max, mean, rms)``
    of the difference array.
    """
    from . import compare
    rows: List[dict] = []
    names = _shared_vars(datasets, variables)
    if not datasets or reference >= len(datasets):
        raise ValueError("reference index out of range")
    for didx, ff in enumerate(datasets):
        lab = _label(ff, didx, labels)
        for name in names:
            res = compare.difference_field(datasets[reference], ff, name,
                                           mode=mode, mapping=mapping)
            if res is None:
                continue
            row = {"dataset": lab, "var": name, "location": res["location"],
                   "kind": "scalar"}
            row.update({k: float(res[k]) for k in ("n", "min", "max",
                                                   "mean", "rms")})
            rows.append(row)
    return rows


def to_csv(rows: List[dict]) -> str:
    """CSV string for a report table (empty string when no rows)."""
    if not rows:
        return ""
    fieldnames: List[str] = []
    for r in rows:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()
