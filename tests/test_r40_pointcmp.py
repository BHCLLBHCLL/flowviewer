"""R40 tests: pointwise time-trace comparison of two sequences.

Headless and dependency-light (no VTK, no CGNS/h5py): a minimal fake streaming
handle stands in for ``StreamCgnsHandle`` and a dict mesh for the streaming
mesh, so the whole round verifies in any environment (mirroring R37–R39).
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.pointcmp import (
    point_compare,
    trace_report,
    write_point_compare,
)
from fv.trace import resolve_probe_nodes

# ── fakes ──────────────────────────────────────────────────────────────────

class FakeHandle:
    """Minimal streaming handle: 1D node fields as plain arrays."""

    def __init__(self, fields):
        self._f = {k: np.asarray(v, dtype=np.float64) for k, v in fields.items()}

    def field_names(self):
        return list(self._f)

    def field_len(self, name):
        return int(self._f[name].size)

    def iter_tiles(self, name, tile=0):
        data = self._f[name]
        n = int(data.size)
        tsize = int(tile) if tile > 0 else 4
        for start in range(0, n, tsize):
            yield start, data[start:start + tsize]


_MESH = {"vertices": np.array([[0.0, 0, 0], [1.0, 0, 0],
                               [0.0, 1, 0], [0.0, 0, 1]])}


def _handle(fields):
    return FakeHandle(fields)


def _tl(cycles_values):
    for cycle, fields in cycles_values:
        yield cycle, _handle(fields), _MESH


NODES = resolve_probe_nodes(_MESH, [(0.95, 0.05, 0.0),   # -> node 1
                                    (0.05, 0.05, 0.05)])  # -> node 0
N0 = [{"query": (0.05, 0.05, 0.05), "node": 0, "xyz": (0.0, 0.0, 0.0)}]


# ── per-sequence trace report ──────────────────────────────────────────────

def test_trace_report_collects_series_with_bound_nodes():
    tl = _tl([(1, {"P": [10.0, 11.0, 20.0, 30.0]}),
              (2, {"P": [20.0, 21.0, 40.0, 60.0]}),
              (3, {"P": [30.0, 31.0, 60.0, 90.0]})])
    rep = trace_report(tl, NODES, ["P"])
    p = rep["P"]
    assert p["cycles"] == [1, 2, 3]
    # probe 0 -> node 1
    assert p["probes"][0]["node"] == 1
    assert p["probes"][0]["values"] == pytest.approx([11.0, 21.0, 31.0])
    # probe 1 -> node 0
    assert p["probes"][1]["values"] == pytest.approx([10.0, 20.0, 30.0])


# ── pointwise compare ──────────────────────────────────────────────────────

def test_point_compare_constant_offset_metrics():
    # A = B + 2 at every probe on cycles 1..3
    rep_a = trace_report(
        _tl([(1, {"P": [3.0, 4.0]}), (2, {"P": [5.0, 6.0]}),
             (3, {"P": [7.0, 8.0]})]),
        N0, ["P"])
    rep_b = trace_report(
        _tl([(1, {"P": [1.0, 2.0]}), (2, {"P": [3.0, 4.0]}),
             (3, {"P": [5.0, 6.0]})]),
        N0, ["P"])
    rep = point_compare(rep_a, rep_b)
    p = rep["fields"]["P"]["probes"][0]
    assert rep["fields"]["P"]["cycles"] == [1, 2, 3]
    assert p["a"] == pytest.approx([3.0, 5.0, 7.0])
    assert p["b"] == pytest.approx([1.0, 3.0, 5.0])
    assert p["diff"] == pytest.approx([2.0, 2.0, 2.0])
    m = p["metrics"]
    assert m["n"] == 3
    assert m["mean_abs"] == pytest.approx(2.0)
    assert m["max_abs"] == pytest.approx(2.0)
    assert m["max_rel"] == pytest.approx(2.0 / 1.0)  # smallest |b| = 1.0


def test_point_compare_skips_nan_cycles_in_metrics():
    # node 0 has a NaN on cycle 2 (missing) -> only cycles 1,3 counted
    rep_a = trace_report(
        _tl([(1, {"P": [10.0]}), (2, {"P": [np.nan]}), (3, {"P": [30.0]})]),
        N0, ["P"])
    rep_b = trace_report(
        _tl([(1, {"P": [8.0]}), (2, {"P": [8.0]}), (3, {"P": [8.0]})]),
        N0, ["P"])
    rep = point_compare(rep_a, rep_b)
    p = rep["fields"]["P"]["probes"][0]
    assert np.isnan(p["diff"][1])          # cycle 2 masked
    assert p["metrics"]["n"] == 2
    assert p["metrics"]["mean_abs"] == pytest.approx((2 + 22) / 2)


def test_point_compare_aligns_on_common_cycle_intersection():
    # A has cycles 1,2,4 ; B has 1,2,3,4 -> common = 1,2,4
    rep_a = trace_report(
        _tl([(1, {"P": [1.0]}), (2, {"P": [2.0]}), (4, {"P": [4.0]})]),
        N0, ["P"])
    rep_b = trace_report(
        _tl([(1, {"P": [1.0]}), (2, {"P": [2.0]}), (3, {"P": [3.0]}),
             (4, {"P": [4.0]})]),
        N0, ["P"])
    rep = point_compare(rep_a, rep_b)
    blk = rep["fields"]["P"]
    assert blk["cycles"] == [1, 2, 4]
    p = blk["probes"][0]
    assert p["a"] == pytest.approx([1.0, 2.0, 4.0])
    assert p["b"] == pytest.approx([1.0, 2.0, 4.0])
    assert p["metrics"]["max_abs"] == pytest.approx(0.0)


def test_point_compare_different_fields_are_kept_separately():
    rep_a = trace_report(_tl([(1, {"P": [1.0], "T": [7.0]})]), N0,
                         ["P", "T"])
    rep_b = trace_report(_tl([(1, {"P": [1.0], "T": [8.0]})]), N0,
                         ["P", "T"])
    rep = point_compare(rep_a, rep_b)
    assert set(rep["fields"]) == {"P", "T"}
    assert rep["fields"]["T"]["probes"][0]["metrics"]["max_abs"] == \
        pytest.approx(1.0)


# ── I/O ────────────────────────────────────────────────────────────────────

def test_write_point_compare_emits_field_json_and_summary(tmp_path):
    rep_a = trace_report(_tl([(1, {"P": [3.0]}), (2, {"P": [5.0]})]),
                         N0, ["P"])
    rep_b = trace_report(_tl([(1, {"P": [1.0]}), (2, {"P": [3.0]})]),
                         N0, ["P"])
    report = point_compare(rep_a, rep_b)
    summary = write_point_compare(report, str(tmp_path))
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "P.json").exists()
    assert summary["fields"]["P"]["probes"] == 1
    with open(tmp_path / "P.json", "r", encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["probes"][0]["diff"] == pytest.approx([2.0, 2.0])
    assert summary["fields"]["P"]["sample"]["mean_abs"] == pytest.approx(2.0)


def test_write_point_compare_sanitises_weird_names(tmp_path):
    probe = {"query": (0.0, 0.0, 0.0), "node": 0, "xyz": (0.0, 0.0, 0.0),
             "a": [], "b": [], "diff": [],
             "metrics": {"n": 0, "mean_abs": float("nan"),
                         "max_abs": float("nan"), "max_rel": float("nan")}}
    report = {"fields": {"pres sure": {"cycles": [1], "probes": [probe]}}}
    summary = write_point_compare(report, str(tmp_path))
    assert (tmp_path / "pres_sure.json").exists()
    assert summary["fields"]["pres sure"]["file"] == "pres_sure.json"
