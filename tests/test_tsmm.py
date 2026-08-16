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
