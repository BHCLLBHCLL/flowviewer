"""Time Series (TM) / Max and Min (OT) file support (P2.10).

Both are simple CSV/text files: TimeSeries carries cycle,time rows;
MaxMin carries variable,min,max rows.  Parsers never raise on malformed
input - they return whatever rows were readable.
"""

from __future__ import annotations

import csv


def parse_time_series(path: str) -> tuple:
    """CSV cycle,time rows -> ([cycles], [times])."""
    cycles = [];
    times = []
    with open(path, newline="", encoding="utf-8") as fh:
        rd = csv.reader(fh)
        header = next(rd, None)
        for row in rd:
            if len(row) < 2:
                continue
            try:
                cycles.append(int(float(row[0])));
                times.append(float(row[1]));
            except ValueError:
                continue
    return cycles, times


def parse_max_min(path: str) -> dict:
    """CSV variable,min,max rows -> {var: (min, max)}."""
    out = {}
    with open(path, newline="", encoding="utf-8") as fh:
        rd = csv.reader(fh)
        header = next(rd, None)
        for row in rd:
            if len(row) < 3:
                continue
            try:
                out[row[0].strip()] = (float(row[1]), float(row[2]));
            except ValueError:
                continue
    return out