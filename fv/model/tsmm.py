"""Time Series (TM/TSER) / Max and Min (OT) file support.

scPOST writes two official text formats (Cradle ST Operation examples):

* ``TSER`` (``*_tm.csv`` / ``*.tm``) — probe coordinates plus per-cycle
  variable columns (CYCL, TIME, VAR@probe…).
* ``CRDL-OT`` (``*.ot``) — per-cycle PARTS min/max blocks.

Plain CSV (``cycle,time`` / ``var,min,max``) remains the fallback so
older tests and user-exported tables keep working.  Parsers never raise
on malformed input — they return whatever rows were readable.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field


@dataclass
class TimeSeriesData:
    """Parsed Time Series table."""

    cycles: list = field(default_factory=list)
    times: list = field(default_factory=list)
    series: dict = field(default_factory=dict)   # name -> [values]
    probes: list = field(default_factory=list)   # [(name, x, y, z), ...]
    columns: list = field(default_factory=list)  # series names in file order


@dataclass
class MaxMinData:
    """Parsed Max and Min table (last cycle + optional history)."""

    values: dict = field(default_factory=dict)   # name -> (min, max)
    history: list = field(default_factory=list)  # [{name: (min, max)}, ...]
    cycles: list = field(default_factory=list)


def _peek_tag(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                tag = line.strip().lstrip("\ufeff")
                if tag:
                    return tag.split()[0].upper()
    except OSError:
        return ""
    return ""


def _split(line: str) -> list:
    return [p.strip() for p in line.split(",")]


def _floats(tokens) -> list:
    out = []
    for tok in tokens:
        tok = str(tok).strip()
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            continue
    return out


def load_time_series(path: str) -> TimeSeriesData:
    """Auto-detect TSER vs CSV and return a ``TimeSeriesData``."""
    tag = _peek_tag(path)
    if tag.startswith("TSER") or "TSER" in tag:
        return _parse_tser(path)
    return _parse_csv_time_series(path)


def parse_time_series(path: str) -> tuple:
    """CSV/TSER cycle,time rows -> ([cycles], [times])."""
    data = load_time_series(path)
    return data.cycles, data.times


def _parse_tser(path: str) -> TimeSeriesData:
    """Cradle TSER: probes + CYCL/TIME/variable columns (ST Operation)."""
    data = TimeSeriesData()
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = [ln.rstrip("\n") for ln in fh]
    if not lines or not lines[0].strip().lstrip("\ufeff").upper().startswith("TSER"):
        return data
    i = 1
    # Skip the three integer header counts (n_probes, unused, n_cols).
    while i < len(lines) and not lines[i].upper().startswith("NAME"):
        i += 1
    if i >= len(lines):
        return data
    i += 1  # past NAME,CODX,CODY,CODZ
    while i < len(lines):
        raw = lines[i].strip()
        up = raw.upper()
        if up.startswith("POSITION") or up.startswith("CYCL"):
            break
        parts = _split(raw)
        if len(parts) >= 4:
            nums = _floats(parts[1:4])
            if len(nums) == 3:
                data.probes.append((parts[0], nums[0], nums[1], nums[2]))
        i += 1
    probes_by_pos = []
    while i < len(lines) and lines[i].strip().upper().startswith("POSITION"):
        parts = _split(lines[i])
        probes_by_pos = [p for p in parts[1:] if p]
        i += 1
    var_names = []
    while i < len(lines) and lines[i].strip().upper().startswith("CYCL"):
        parts = _split(lines[i])
        var_names = [p for p in parts[2:] if p]
        i += 1
        break
    columns = []
    for idx, var in enumerate(var_names):
        probe = probes_by_pos[idx] if idx < len(probes_by_pos) else ""
        name = f"{var}@{probe}" if probe else var
        if name in columns:
            name = f"{var}[{idx}]"
        columns.append(name)
        data.series[name] = []
    data.columns = columns
    for line in lines[i:]:
        parts = _split(line)
        nums = _floats(parts)
        if len(nums) < 2:
            continue
        data.cycles.append(int(nums[0]))
        data.times.append(float(nums[1]))
        for j, name in enumerate(columns):
            val = nums[2 + j] if 2 + j < len(nums) else float("nan")
            data.series[name].append(val)
    return data


def _parse_csv_time_series(path: str) -> TimeSeriesData:
    data = TimeSeriesData()
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rd = csv.reader(fh)
        header = next(rd, None)
        extra = []
        if header and len(header) > 2:
            extra = [h.strip() for h in header[2:] if h.strip()]
            for name in extra:
                data.series[name] = []
            data.columns = list(extra)
        for row in rd:
            if len(row) < 2:
                continue
            try:
                data.cycles.append(int(float(row[0])))
                data.times.append(float(row[1]))
            except ValueError:
                continue
            for j, name in enumerate(extra):
                try:
                    data.series[name].append(float(row[2 + j]))
                except (ValueError, IndexError):
                    data.series[name].append(float("nan"))
    return data


def load_max_min(path: str) -> MaxMinData:
    """Auto-detect CRDL-OT vs CSV and return a ``MaxMinData``."""
    tag = _peek_tag(path)
    if tag.startswith("CRDL"):
        return _parse_ot(path)
    return _parse_csv_max_min(path)


def parse_max_min(path: str) -> dict:
    """CSV/OT variable,min,max rows -> {var: (min, max)}."""
    return load_max_min(path).values


def _parse_ot(path: str) -> MaxMinData:
    """Cradle CRDL-OT: repeated PARTS min/max blocks (ST Operation)."""
    data = MaxMinData()
    block = {}
    cycle = len(data.history) + 1
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            up = line.upper()
            if up.startswith("CRDL"):
                if block:
                    data.history.append(block)
                    data.cycles.append(cycle)
                    cycle = len(data.history) + 1
                    block = {}
                continue
            if up in ("PARTS", "/", "LAST"):
                if up == "/" or up == "LAST":
                    if block:
                        data.history.append(block)
                        data.cycles.append(cycle)
                        cycle = len(data.history) + 1
                        block = {}
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                a = float(parts[1])
                b = float(parts[2])
            except ValueError:
                continue
            mn, mx = (a, b) if a <= b else (b, a)
            block[parts[0]] = (mn, mx)
    if block:
        data.history.append(block)
        data.cycles.append(cycle)
    if data.history:
        data.values = dict(data.history[-1])
    return data


def _parse_csv_max_min(path: str) -> MaxMinData:
    data = MaxMinData()
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        rd = csv.reader(fh)
        header = next(rd, None)
        for row in rd:
            if len(row) < 3:
                continue
            try:
                data.values[row[0].strip()] = (float(row[1]), float(row[2]))
            except ValueError:
                continue
    if data.values:
        data.history.append(dict(data.values))
        data.cycles.append(1)
    return data


def time_at_cycle(data: TimeSeriesData, cycle: int):
    """Physical time for ``cycle``, or None if the table has no such row."""
    try:
        idx = data.cycles.index(int(cycle))
    except ValueError:
        return None
    if 0 <= idx < len(data.times):
        return data.times[idx]
    return None
