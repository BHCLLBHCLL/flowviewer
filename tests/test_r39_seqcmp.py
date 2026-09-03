"""R39 tests: cycle-by-cycle sequence comparison (baseline vs scenario).

Headless and dependency-light (no VTK, no CGNS/h5py): a minimal fake streaming
handle with ``field_names`` / ``field_len`` / ``iter_tiles`` / ``read_window``
stands in for ``StreamCgnsHandle``, so the whole round verifies in any
environment (mirroring R36/R37/R38).
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.seqcmp import (
    compare_sequences,
    field_tile_difference,
    write_compare_files,
)

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
        tsize = int(tile) if tile > 0 else max(1, (n + 3) // 4)
        for start in range(0, n, tsize):
            yield start, data[start:start + tsize]

    def read_window(self, name, lo, hi, tile=0):
        if name not in self._f:
            raise KeyError(name)
        data = self._f[name]
        lo = max(0, int(lo))
        hi = min(int(data.size), int(hi))
        return lo, np.asarray(data[lo:hi], dtype=np.float64).copy()


def _handle(fields):
    return FakeHandle(fields)


def _timeline(cycles_values):
    """iterable of (cycle, handle, mesh): cycles->list of {field:array}."""
    for cycle, fields in cycles_values:
        yield cycle, _handle(fields), {}


# ── per-field tile difference ──────────────────────────────────────────────

def test_field_tile_difference_exact_match_is_zero():
    ha = _handle({"P": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]})
    hb = _handle({"P": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]})
    d = field_tile_difference(ha, hb, "P")
    assert d["n"] == 8
    assert d["rmse"] == pytest.approx(0.0)
    assert d["mae"] == pytest.approx(0.0)
    assert d["max"] == pytest.approx(0.0)
    assert d["lrel"] == pytest.approx(0.0)


def test_field_tile_difference_constant_offset():
    ha = _handle({"P": [1.0, 2.0, 3.0, 4.0]})
    hb = _handle({"P": [3.0, 4.0, 5.0, 6.0]})   # +2 per node
    d = field_tile_difference(ha, hb, "P")
    assert d["rmse"] == pytest.approx(2.0)
    assert d["mae"] == pytest.approx(2.0)
    assert d["max"] == pytest.approx(2.0)


def test_field_tile_difference_relative_and_nan_skip():
    # nan in one side is skipped (finite A∩B pairs only)
    ha = _handle({"P": [1.0, 2.0, np.nan, 4.0]})
    hb = _handle({"P": [1.0, 4.0, 1.0, 4.0]})
    d = field_tile_difference(ha, hb, "P")
    assert d["n"] == 3                      # nodes 0,1,3
    assert d["mae"] == pytest.approx((0 + 2 + 0) / 3)
    assert d["lrel"] == pytest.approx(math_sqrt(((0 / 1) ** 2 + (2 / 4) ** 2 + 0) / 3))


def math_sqrt(x):
    import math
    return math.sqrt(x)


def test_field_tile_difference_missing_field_is_nan():
    d = field_tile_difference(_handle({"P": [1.0]}), _handle({"Q": [1.0]}), "P")
    assert d["n"] == 0
    assert np.isnan(d["rmse"])


# ── sequence compare ───────────────────────────────────────────────────────

def test_compare_sequences_reports_per_cycle_and_summary():
    # sequence A: P[n] = cycle*10 + n ; sequence B: A + 2 (baseline vs perturbed)
    seq_a = [(1, {"P": [11.0, 12.0], "T": [0.0, 0.0]}),
             (2, {"P": [21.0, 22.0], "T": [0.0, 0.0]}),
             (3, {"P": [31.0, 32.0], "T": [0.0, 0.0]})]
    seq_b = [(1, {"P": [13.0, 14.0], "T": [0.0, 0.0]}),
             (2, {"P": [23.0, 24.0], "T": [0.0, 0.0]}),
             (3, {"P": [33.0, 34.0], "T": [0.0, 0.0]})]
    rep = compare_sequences(_timeline(seq_a), _timeline(seq_b))
    assert rep["cycles"] == [1, 2, 3]
    assert set(rep["fields"]) == {"P", "T"}
    p = rep["fields"]["P"]
    assert [r["cycle"] for r in p["per_cycle"]] == [1, 2, 3]
    assert all(r["mae"] == pytest.approx(2.0) for r in p["per_cycle"])
    assert p["summary"]["mean_mae"] == pytest.approx(2.0)
    assert p["summary"]["max_max"] == pytest.approx(2.0)
    # T identical everywhere -> zero
    t = rep["fields"]["T"]
    assert t["summary"]["max_max"] == pytest.approx(0.0)


def test_compare_sequences_fields_subset_and_missing_cycle():
    seq_a = [(1, {"P": [1.0], "Q": [5.0]}),
             (2, {"P": [2.0]})]          # Q missing on cycle 2
    seq_b = [(1, {"P": [1.0], "Q": [5.0]}),
             (2, {"P": [2.0]})]
    rep = compare_sequences(_timeline(seq_a), _timeline(seq_b), fields=["P"])
    assert set(rep["fields"]) == {"P"}
    assert len(rep["fields"]["P"]["per_cycle"]) == 2


def test_compare_sequences_empty_produces_empty_report():
    rep = compare_sequences(iter(()), iter(()))
    assert rep == {"cycles": [], "fields": {}}


# ── I/O ────────────────────────────────────────────────────────────────────

def test_write_compare_files_emits_field_json_and_summary(tmp_path):
    seq_a = [(1, {"P": [1.0, 2.0]}),
             (2, {"P": [3.0, 4.0]})]
    seq_b = [(1, {"P": [3.0, 4.0]}),
             (2, {"P": [5.0, 6.0]})]
    rep = compare_sequences(_timeline(seq_a), _timeline(seq_b))
    summary = write_compare_files(rep, str(tmp_path))
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "P.json").exists()
    assert summary["n_fields"] == 1
    with open(tmp_path / "P.json", "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # offset +2 per node per cycle
    assert data["per_cycle"][0]["mae"] == pytest.approx(2.0)
    assert summary["fields"]["P"]["summary"]["mean_mae"] == pytest.approx(2.0)


def test_write_compare_files_sanitises_weird_names(tmp_path):
    rep = {"cycles": [1],
           "fields": {"pres sure": {"per_cycle": [], "summary": {
               "mean_rmse": 0.0, "mean_mae": 0.0, "max_max": 0.0,
               "mean_lrel": 0.0, "max_lrel": 0.0, "n_cycles": 1}}}}
    summary = write_compare_files(rep, str(tmp_path))
    assert (tmp_path / "pres_sure.json").exists()
    assert summary["fields"]["pres sure"]["file"] == "pres_sure.json"
