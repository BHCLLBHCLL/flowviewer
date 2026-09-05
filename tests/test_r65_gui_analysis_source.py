"""R65 tests: Analysis data-source selection (Time Series -> artifact).

R64 wired the Analysis menu to a report registry but left the menu "dead":
``on_analysis_report`` had no real data source, so clicking an item would raise
an ``AttributeError``. R65 adds the data-source path: the applied Time Series
becomes an R38-style trace artifact via ``artifact_from_timeseries``, and the
menu can then run *any* report on it. These tests exercise the pure helpers in
``fv.gui.analysis`` (``field_names`` / ``artifact_from_timeseries`` /
``artifact_summary``) and the end-to-end ``run_report`` path on an artifact
built from a Time Series.

Pure NumPy, headless — no display, no PyQt widgets are instantiated.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fv.gui.analysis import (
    artifact_from_timeseries,
    artifact_summary,
    field_names,
    run_report,
)

CY = [0.0, 0.05, 0.10, 0.15, 0.20]


class _FakeTS:
    """Minimal ``TimeSeriesObject``-shaped stand-in (duck-typed access only)."""

    def __init__(self, cycles, series, probes, times=None, columns=None):
        self.cycles = cycles
        self.times = times if times is not None else []
        self.series = series
        self.probes = probes
        self.columns = columns if columns is not None else []


def _ts(series=None, probes=None, cycles=None):
    return _FakeTS(
        cycles if cycles is not None else CY,
        series if series is not None else {
            "P1": [1.0, 1.5, 2.0, 1.5, 1.0],
            "P2": [0.0, 0.1, 0.2, 0.1, 0.0],
        },
        probes if probes is not None else [
            ("P1", 0.0, 0.0, 0.0),
            ("P2", 2.0, 0.0, 0.0),
        ],
    )


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def test_field_names_lists_series():
    assert field_names(_ts()) == ["P1", "P2"]


def test_field_names_empty_and_none():
    assert field_names(None) == []
    assert field_names(_FakeTS([], {}, [])) == []


def test_artifact_all_series():
    a = artifact_from_timeseries(_ts())
    assert a["name"] == "Time Series"
    assert list(a["cycles"]) == CY
    assert len(a["probes"]) == 2
    p0, p1 = a["probes"]
    assert p0["xyz"] == (0.0, 0.0, 0.0)
    assert p0["query"] == (0.0, 0.0, 0.0)
    assert p0["node"] == -1
    assert list(p0["values"]) == [1.0, 1.5, 2.0, 1.5, 1.0]
    assert p1["xyz"] == (2.0, 0.0, 0.0)
    assert list(p1["values"]) == [0.0, 0.1, 0.2, 0.1, 0.0]


def test_artifact_single_field():
    a = artifact_from_timeseries(_ts(), field="P2")
    assert a["name"] == "P2"
    assert len(a["probes"]) == 1
    assert a["probes"][0]["xyz"] == (2.0, 0.0, 0.0)
    assert list(a["probes"][0]["values"]) == [0.0, 0.1, 0.2, 0.1, 0.0]


def test_artifact_missing_probe_coord_defaults_zero():
    ts = _ts(series={"PX": [1.0, 2.0]}, probes=[])
    a = artifact_from_timeseries(ts)
    assert len(a["probes"]) == 1
    assert a["probes"][0]["xyz"] is None
    assert a["probes"][0]["query"] == (0.0, 0.0, 0.0)


def test_artifact_value_float_cast():
    ts = _ts(series={"P1": np.array([1, 2, 3, 4, 5], dtype=np.int64)},
             probes=[])
    a = artifact_from_timeseries(ts)
    assert all(isinstance(v, float) for v in a["probes"][0]["values"])


def test_artifact_no_series_raises():
    with pytest.raises(ValueError):
        artifact_from_timeseries(_FakeTS(CY, {}, []))
    with pytest.raises(ValueError):
        artifact_from_timeseries(_ts(series={"P1": [1.0]}), field="nope")


def test_artifact_summary_formats():
    assert artifact_summary(None) == "none"
    assert artifact_summary({}) == "none"
    s = artifact_summary(artifact_from_timeseries(_ts()))
    assert "Time Series" in s
    assert "2 probe(s)" in s
    assert "5 cycle(s)" in s


def _rich_ts():
    dt = 0.05
    t = np.arange(0.0, 10.0, dt)
    v = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    v2 = 1.5 + np.sin(2 * np.pi * 1.0 * t + 0.5)
    return _FakeTS(
        list(t),
        {"P1": list(v), "P2": list(v2)},
        [("P1", 0.0, 0.0, 0.0), ("P2", 2.0, 0.0, 0.0)],
    )


def test_run_report_on_timeseries_artifact(tmp_path):
    a = artifact_from_timeseries(_rich_ts())
    verts = _grid3()
    path = run_report("spectral", verts, a, str(tmp_path), dt=0.05,
                      cycles=list(range(len(a["cycles"]))))
    assert path and path.endswith("_spectral.html")
    p = Path(path)
    assert p.exists()
    html = p.read_text(encoding="utf-8")
    assert "<canvas" in html
