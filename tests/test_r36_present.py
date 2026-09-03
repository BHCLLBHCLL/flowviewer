"""R36 tests: multi-cycle temporal report (Sequence -> report bundle).

The pure assembly (:func:`report_from_cycles`, :func:`field_stats`) and the
sequence walk (via a stubbed timeline / stream handle) are fully headless and
need no h5py/CGNS/VTK, so the whole round verifies locally.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest
from fv.present import (
    cycle_report,
    field_stats,
    report_from_cycles,
    sequence_report,
)


class _FakeHandle:
    """Minimal stream-style handle: one contiguous field, no tiles beyond 1."""

    def __init__(self, values, name="P"):
        self._values = np.asarray(values, dtype=np.float64)
        self._name = name

    def field_names(self):
        return [self._name]

    def field_len(self, name):
        return len(self._values)

    def iter_tiles(self, name, tile=0):
        yield 0, self._values


def _fake_tl(cls, arrs):
    """Return a stub SessionTimeline-like object yielding (cycle, handle, mesh)."""
    class _TL:
        paths = []
        budget_mb = 64

        def __init__(self, _paths, budget_mb=64):
            self.paths = _paths

        def __iter__(self):
            for i, vals in enumerate(arrs, start=1):
                yield i, _FakeHandle(vals), None
    return _TL


# ── bounded field stats ────────────────────────────────────────────────────

def test_field_stats_min_max_count_and_sample():
    h = _FakeHandle([1.0, 2.0, 3.0, 4.0])
    s = field_stats(h, "P", embed_window=3)
    assert s["n"] == 4
    assert s["min"] == pytest.approx(1.0)
    assert s["max"] == pytest.approx(4.0)
    assert s["sample"] == pytest.approx([1.0, 2.0, 3.0])  # capped window


def test_field_stats_ignores_nonfinite():
    h = _FakeHandle([float("nan"), 2.0, float("inf"), 3.0])
    s = field_stats(h, "P")
    assert s["min"] == pytest.approx(2.0)
    assert s["max"] == pytest.approx(3.0)


def test_cycle_report_bundles_all_fields():
    h = _FakeHandle([0.0, 5.0, 10.0])
    rep = cycle_report(h, name="cycle 1")
    assert rep["name"] == "cycle 1"
    assert set(rep["vars"]) == {"P"}
    assert rep["vars"]["P"]["min"] == 0.0 and rep["vars"]["P"]["max"] == 10.0


# ── pure report assembly ───────────────────────────────────────────────────

def _two_cycles():
    return [
        {"cycle": 1, "name": "cycle 1",
         "vars": {"P": {"n": 3, "min": 0.0, "max": 1.0, "sample": [0, 0.5, 1.0]},
                  "Q": {"n": 3, "min": 2.0, "max": 4.0, "sample": []}}},
        {"cycle": 2, "name": "cycle 2",
         "vars": {"P": {"n": 3, "min": 0.5, "max": 1.5, "sample": []}}},
    ]


def test_report_from_cycles_writes_manifest(tmp_path):
    man = report_from_cycles(_two_cycles(), str(tmp_path))
    assert man["n_cycles"] == 2
    assert man["report"] == "report.html" and man["csv"] == "data.csv"
    assert man["cycles"][0]["variables"] == ["P", "Q"]
    assert man["cycles"][1]["variables"] == ["P"]
    assert (tmp_path / "manifest.json").exists()


def test_report_from_cycles_csv_rows(tmp_path):
    report_from_cycles(_two_cycles(), str(tmp_path))
    rows = list(csv.DictReader(
        (tmp_path / "data.csv").read_text().splitlines()))
    assert len(rows) == 3  # (1,P),(1,Q),(2,P)
    assert all(r["variable"] == "P" or r["variable"] == "Q" for r in rows)
    p_baseline = next(r for r in rows if r["cycle"] == "1" and r["variable"] == "P")
    assert float(p_baseline["n"]) == 3 and float(p_baseline["min"]) == 0.0


def test_report_html_has_cycles_and_delta_column(tmp_path):
    report_from_cycles(_two_cycles(), str(tmp_path))
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "Cycle 1" in html and "Cycle 2" in html
    assert "Δ from base" in html
    assert "variable" in html


def test_report_html_embeds_base64_png(tmp_path):
    cyc = {"cycle": 1, "name": "c",
           "vars": {"P": {"n": 1, "min": 0.0, "max": 1.0, "sample": []}}}
    png = tmp_path / "f1.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"1234")
    cyc["png"] = str(png)
    report_from_cycles([cyc], str(tmp_path))
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "data:image/png;base64," in html


def test_report_html_escapes_variable_names(tmp_path):
    cyc = {"cycle": 1, "name": "c",
           "vars": {"a<b>": {"n": 1, "min": 0.0, "max": 1.0, "sample": []}}}
    report_from_cycles([cyc], str(tmp_path))
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "a&lt;b&gt;" in html
    assert "<b>" not in html.split('lt;b')[0][-6:]


# ── sequence walk (stubbed timeline, no CGNS) ──────────────────────────────

def test_sequence_report_wires_timeline_stub(tmp_path, monkeypatch):
    import fv.present as present
    fake = _fake_tl(None, [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
    monkeypatch.setattr(present, "SessionTimeline", fake)

    man = sequence_report(["a_1.cgns", "a_2.cgns"], str(tmp_path),
                          window_len=4, budget_mb=4)
    assert man["n_cycles"] == 2
    assert man["cycles"][0]["cycle"] == 1
    assert man["cycles"][1]["cycle"] == 2
    assert (tmp_path / "report.html").exists()
    assert (tmp_path / "data.csv").exists()
    # per-cycle min across the sequence
    rows = list(csv.DictReader(
        (tmp_path / "data.csv").read_text().splitlines()))
    mins = sorted(float(r["min"]) for r in rows if r["variable"] == "P")
    assert mins == [1.0, 4.0]
