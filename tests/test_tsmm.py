# -*- coding: utf-8 -*-
"""Time-series (TSMM) parser tests (fv.model.tsmm, P3)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


def test_time_series_max_min_parsers(tmp_path):
    """TM/OT CSV parsers read cycle/time and min/max rows (P2.10)."""
    from fv.model.tsmm import parse_max_min, parse_time_series
    tm = tmp_path / "series.csv"
    tm.write_text("cycle,time\n100,0.1\n200,0.2\n300,0.3\n", encoding="utf-8")
    cyc, tim = parse_time_series(str(tm))
    assert cyc == [100, 200, 300]
    assert abs(tim[2] - 0.3) < 1e-9
    mm = tmp_path / "mm.csv"
    mm.write_text("var,min,max\nPRES,-1.5,2.5\nTEMP,0,100\n", encoding="utf-8")
    vals = parse_max_min(str(mm))
    assert vals["PRES"] == (-1.5, 2.5)
    assert vals["TEMP"] == (0.0, 100.0)


ST_TM = Path(r"D:\training\cradle\CradleCFD_2023.2_ST_Example\Operation_e\ex1\ex1_e_tm.csv")
ST_OT = Path(r"D:\training\cradle\CradleCFD_2023.2_ST_Example\Operation_e\ex1\ex1_e.ot")


@pytest.mark.skipif(not ST_TM.exists(), reason="ST TSER sample not present")
def test_official_tser_parser():
    """Cradle TSER (ST Operation ex1) yields probes + TEMP@Point columns."""
    from fv.model.tsmm import load_time_series, parse_time_series, time_at_cycle
    data = load_time_series(str(ST_TM))
    assert len(data.probes) == 3
    assert data.probes[0][0] == "Point1"
    assert len(data.cycles) >= 10
    assert data.cycles[0] == 1
    assert "TEMP@Point1" in data.series
    assert len(data.series["TEMP@Point1"]) == len(data.cycles)
    cyc, tim = parse_time_series(str(ST_TM))
    assert cyc == data.cycles and tim == data.times
    assert time_at_cycle(data, data.cycles[0]) == data.times[0]


@pytest.mark.skipif(not ST_OT.exists(), reason="ST CRDL-OT sample not present")
def test_official_ot_parser():
    """Cradle CRDL-OT (ST Operation ex1) yields PARTS min/max history."""
    from fv.model.tsmm import load_max_min, parse_max_min
    data = load_max_min(str(ST_OT))
    assert "PARTS1" in data.values
    mn, mx = data.values["PARTS1"]
    assert mn < mx
    assert len(data.history) >= 2
    vals = parse_max_min(str(ST_OT))
    assert vals["PARTS1"] == data.values["PARTS1"]


FPH = r"D:\training\cgns\examples\tr03_9.fph"

try:
    from PyQt5.QtWidgets import QApplication
    _HAS_QT = True
except Exception:  # pragma: no cover
    _HAS_QT = False


@pytest.fixture(scope="module")
def qapp():
    if not _HAS_QT:
        pytest.skip("PyQt5 unavailable")
    app = QApplication.instance() or QApplication([])
    return app


@pytest.mark.skipif(not Path(FPH).exists() or not ST_TM.exists(),
                    reason="FPH or ST TSER sample not present")
def test_timeseries_drives_timeline(qapp):
    """Applying a TSER Time Series object sets the Timeline range."""
    from fv.gui.main import FlowViewer
    from fv.model.objects import TimeSeriesObject
    from fv.model.tsmm import load_time_series
    w = FlowViewer(filepath=FPH, enable_3d=False)
    data = load_time_series(str(ST_TM))
    obj = TimeSeriesObject(index=1, file=str(ST_TM),
                           cycles=data.cycles, times=data.times,
                           series=data.series, probes=data.probes)
    w._apply_timeseries_timeline(obj)
    assert w.timeline._min == int(min(data.cycles))
    assert w.timeline._max == int(max(data.cycles))
    step = int(data.cycles[5])
    w._on_timeline_step(step)
    ov = w.scene.overlay_text()
    assert f"Cycle : {step}" in ov
