"""FileSet: sequence scan of result files (scPOST FileSet, P3.1).

A time-stepped simulation stores one file per step. The files share a
common stem (``tr03_``) and differ by a trailing cycle number
(``tr03_1.fph`` … ``tr03_9.fph``).  ``scan_sequence`` collects those
sibling files sorted by cycle so the Timeline window can step through the
unsteady field files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from ..crdl.core import open_buffer
from ..crdl.fields import parse_cycle_meta


_TRAILING_DIGITS = re.compile(r"^(.*?)(\d+)$")


@dataclass
class SequenceMember:
    """One time-step file in a FileSet."""

    path: str
    cycle: int
    time: Optional[float] = None

    def refresh_meta(self) -> None:
        """Read ``Cycle`` / ``Time`` from the file header (lazy)."""
        try:
            with open_buffer(self.path) as data:
                cycle, time = parse_cycle_meta(data)
            if cycle is not None:
                self.cycle = cycle
            self.time = time
        except Exception:  # noqa: BLE001
            pass


@dataclass
class FileSet:
    """Ordered sequence of field files sharing a common stem."""

    directory: str                  # parent dir of the opened file
    members: list[SequenceMember] = field(default_factory=list)
    operation_mode: str = "None"    # SetCycOpeMode: None|Add|Sub|Mul|Div

    def __bool__(self) -> bool:
        return bool(self.members)

    def __len__(self) -> int:
        return len(self.members)

    def cycles(self) -> list[int]:
        return [m.cycle for m in self.members]

    def min_cycle(self) -> Optional[int]:
        return self.members[0].cycle if self.members else None

    def max_cycle(self) -> Optional[int]:
        return self.members[-1].cycle if self.members else None

    def find(self, cycle: int) -> Optional[SequenceMember]:
        """Member for a cycle; nearest at-or-after (playback wrap handled by
        the caller)."""
        for m in self.members:
            if m.cycle >= cycle:
                return m
        return self.members[-1] if self.members else None

    def refresh_meta(self) -> None:
        for m in self.members:
            m.refresh_meta()


def _split_stem(stem: str) -> tuple[str, Optional[int]]:
    """``'tr03_9'`` → ``('tr03_', 9)``; ``'mesh'`` → ``('mesh', None)``."""
    m = _TRAILING_DIGITS.match(stem)
    if m:
        return m.group(1), int(m.group(2))
    return stem, None


def scan_sequence(first_file: str, limit: int = 500) -> FileSet:
    """Scan ``first_file``'s directory for same-stem sibling field files.

    ``first_file`` establishes the directory, extension and stem prefix;
    every sibling sharing that prefix+extension (and carrying a trailing
    cycle in its filename) becomes a ``SequenceMember``, sorted by cycle.
    ``member.path`` is absolute; meta (cycle/time from the file's own
    ``Cycle`` section) is read lazily via :meth:`SequenceMember.refresh_meta`.
    """
    path = Path(first_file)
    prefix, _ = _split_stem(path.stem)
    members: list[SequenceMember] = []
    candidates = sorted(
        path.parent.glob(f"{prefix}*.{path.suffix.lstrip('.')}"))
    for cand in candidates[:limit]:
        if not cand.is_file():
            continue
        stem_digits = _split_stem(cand.stem)[1]
        if stem_digits is None:
            continue
        members.append(SequenceMember(
            path=str(cand.resolve()),
            cycle=stem_digits,
        ))
    members.sort(key=lambda m: m.cycle)
    return FileSet(directory=str(path.parent), members=members)

def add_cycle(fs, path, cycle=None):
    """Append a file to the cycle list (scPOST AddCycList)."""
    member_path = str(Path(path).resolve())
    if cycle is None:
        _, num = _split_stem(Path(member_path).stem)
        cycle = num if num is not None else (len(fs.members) + 1)
    m = SequenceMember(path=member_path, cycle=int(cycle))
    fs.members.append(m)
    fs.members.sort(key=lambda x: x.cycle)
    return m


def remove_cycle(fs, cycle):
    """Drop the member with the given cycle (scPOST DelCycList)."""
    before = len(fs.members)
    fs.members = [m for m in fs.members if m.cycle != int(cycle)]
    return len(fs.members) < before


# scPOST SetCycOpeMode numeric modes 0–7 (8 modes, see vb_fldfile.txt).
_CYC_OPE_BY_NUM = {
    0: "Sum0",      # Sum (initial value = 0)
    1: "Average",   # Average (initial value = 0)
    2: "Add",       # Sum (initial value = current value)
    3: "Sub",       # Subtract (initial value = current value)
    4: "Mul",       # Multiply (initial value = current value)
    5: "Div",       # Divide (initial value = current value)
    6: "SqSum",     # Square and sum (initial value = 0)
    7: "SqAvg",     # Square and average (initial value = 0)
}
# String aliases (case-insensitive); legacy names map onto the same modes.
_CYC_OPE_ALIASES = {
    "none": "None", "sum0": "Sum0", "average": "Average", "sum": "Add",
    "add": "Add", "sub": "Sub", "subtract": "Sub", "mul": "Mul",
    "multiply": "Mul", "div": "Div", "divide": "Div", "sqsum": "SqSum",
    "sqavg": "SqAvg",
}


def set_cycle_operation(fs, mode):
    """Set the cycle-to-cycle operation mode (scPOST SetCycOpeMode).

    Accepts either the numeric scPOST mode (0–7) or a (legacy/descriptive)
    string name; ``"None"`` resets the operation.
    """
    if isinstance(mode, bool):
        mode = int(mode)
    if isinstance(mode, (int, float)):
        n = int(mode)
        if n not in _CYC_OPE_BY_NUM:
            raise ValueError("unknown cycle operation mode " + repr(mode))
        fs.operation_mode = _CYC_OPE_BY_NUM[n]
        return fs.operation_mode
    key = str(mode or "None").strip().lower()
    if key not in _CYC_OPE_ALIASES:
        raise ValueError("unknown cycle operation " + repr(mode))
    fs.operation_mode = _CYC_OPE_ALIASES[key]
    return fs.operation_mode


# ── time interpolation + cycle runtime (P2.4) ────────────────────────────

class LruCache:
    """Ordered mapping with a capacity cap (P1-2).

    Timeline playback / POD / register-all-cycles load many cycle files;
    without a cap every parsed FieldFile (mesh + variables) stays pinned
    for the session.  ``maxsize`` entries are kept and re-accessed keys
    move to the back (LRU eviction); ``None`` disables eviction (plain
    unbounded dict semantics).
    """

    __slots__ = ("_d", "_max")

    def __init__(self, maxsize=None):
        self._d = {}
        self._max = None if maxsize is None else int(maxsize)

    def get(self, key, default=None):
        d = self._d
        v = d.get(key, _MISS)
        if v is _MISS:
            return default
        if self._max is not None:
            d.pop(key)
            d[key] = v                      # refresh recency
        return v

    def put(self, key, value) -> None:
        d = self._d
        if key in d:
            d.pop(key)
        d[key] = value
        if self._max is not None:
            while len(d) > self._max:
                d.pop(next(iter(d)))        # evict oldest

    def __setitem__(self, key, value):
        self.put(key, value)

    def __getitem__(self, key):
        return self.get(key)

    def __contains__(self, key) -> bool:
        return key in self._d

    def __iter__(self):
        return iter(self._d)

    def keys(self):
        return self._d.keys()

    def __len__(self) -> int:
        return len(self._d)

    def __bool__(self) -> bool:
        return bool(self._d)

    def clear(self) -> None:
        self._d.clear()


_MISS = object()


def load_member(fs, cycle: int, cache: Optional[dict] = None):
    """Load the member carrying *cycle*, through an optional cache.

    The cache (``{path: FieldFile}`` or :class:`LruCache`) lets timeline
    playback, POD and register-all-cycles share already parsed members
    instead of re-reading and re-parsing each file on every access.
    """
    m = None
    for cand in fs.members:
        if cand.cycle == int(cycle):
            m = cand
            break
    if m is None:
        return None
    if cache is not None:
        hit = cache.get(m.path)
        if hit is not None:
            return hit
    from .dataset import load_file
    ff = load_file(m.path)
    if cache is not None:
        cache[m.path] = ff
    return ff


def interpolate_files(ff0, ff1, f: float):
    """Linear time interpolation of two same-mesh FieldFiles (P2.4).

    Returns a FieldFile sharing ff0's mesh/parts with every common
    variable blended as ``(1-f)*a0 + f*a1``; variables missing on one
    side keep the other side's values.  ``f`` is clamped to [0, 1].
    """
    if not 0.0 <= f <= 1.0:
        f = min(1.0, max(0.0, f))
    from .dataset import FieldFile, VarInfo
    out = FieldFile(path=ff0.path, kind=ff0.kind)
    for attr in ("vertices", "n_vertices", "n_cells", "link_data",
                 "cell_conn", "cell_types", "material", "faces",
                 "bc_plan", "surface_regions", "volume_regions",
                 "parts", "cvol_id", "parts_with_cvol", "meta",
                 "element_flags", "has_particles", "_particle_vars"):
        setattr(out, attr, getattr(ff0, attr))
    out.variables = {}
    for name, vi in ff0.variables.items():
        v1 = ff1.variables.get(name)
        if v1 is not None and np.shape(v1.array) == np.shape(vi.array):
            arr = (1.0 - f) * np.asarray(vi.array, dtype=np.float64) \
                + f * np.asarray(v1.array, dtype=np.float64)
        else:
            arr = vi.array
        out.variables[name] = VarInfo(name=name, kind=vi.kind,
                                      location=vi.location, array=arr)
    out.cycle = ff0.cycle
    out.time = (1.0 - f) * (ff0.time or 0.0) + f * (ff1.time or 0.0) \
        if (ff0.time is not None or ff1.time is not None) else None
    return out


def interpolate_at(fs, cycle_id: float, cache: Optional[dict] = None):
    """FieldFile at a fractional cycle id (1-based, scPOST SetCurCycleID_F).

    ``cycle_id = cyc_i + cyc_f`` with integer part selecting the member
    and the fraction blending it with the next member's variables.
    Integer ids snap to the member itself; ids outside the sequence
    raise ``ValueError``.
    """
    if not fs.members:
        raise ValueError("empty FileSet")
    cyc_i = int(np.floor(cycle_id))
    cyc_f = float(cycle_id) - cyc_i
    if cyc_i < 1 or cyc_i > len(fs.members):
        raise ValueError(
            "cycle id %g out of range 1..%d" % (cycle_id, len(fs.members)))
    m0 = fs.members[cyc_i - 1]
    ff0 = load_member(fs, m0.cycle, cache)
    if cyc_f <= 0.0 or cyc_i >= len(fs.members):
        return ff0
    m1 = fs.members[cyc_i]
    ff1 = load_member(fs, m1.cycle, cache)
    return interpolate_files(ff0, ff1, cyc_f)


class CycleRuntime:
    """Runtime cycle state over a FileSet (scPOST AddCycList family, P2.4).

    Cycle ids are 1-based positions into ``fs.members`` exactly like
    the COM ``SetCurCycleID`` family; fractional ids time-interpolate
    between the two adjacent members.
    """

    def __init__(self, fs: FileSet, cache: Optional[dict] = None):
        self.fs = fs
        self.cache = cache if cache is not None else LruCache(maxsize=8)
        self.cur_id = 1.0
        self.auto = False

    # ── queries ───────────────────────────────────────────────────────────
    def get_cycle_num(self) -> int:
        """Number of cycles in the list (GetCycleNum)."""
        return len(self.fs.members)

    def cycle_ids(self) -> list:
        """Cycle numbers (as stored per member) in order."""
        return self.fs.cycles()

    def get_cur_cycle_id(self) -> int:
        """Current integer cycle id (GetCurCycleID)."""
        return int(np.floor(self.cur_id))

    def get_cur_time(self) -> Optional[float]:
        """Time of the current member, header-read lazily (GetCurTime)."""
        idx = self.get_cur_cycle_id() - 1
        if not (0 <= idx < len(self.fs.members)):
            return None
        m = self.fs.members[idx]
        if m.time is None:
            m.refresh_meta()
        return m.time

    # ── mutations ─────────────────────────────────────────────────────────
    def set_cur_cycle_id(self, cycid: int) -> int:
        """Jump to cycle *cycid*; returns the new id or -1 (SetCurCycleID)."""
        if not (1 <= int(cycid) <= len(self.fs.members)):
            return -1
        self.cur_id = float(int(cycid))
        return int(cycid)

    def set_cur_cycle_id_f(self, cyc_i: int, cyc_f: float) -> int:
        """Set a fractional cycle id; interpolates variables (…_F)."""
        cyc_i = int(cyc_i)
        if not (1 <= cyc_i <= len(self.fs.members)) or not (0.0 <= cyc_f < 1.0):
            return -1
        if cyc_f > 0.0 and cyc_i >= len(self.fs.members):
            return -1
        self.cur_id = float(cyc_i) + float(cyc_f)
        return cyc_i

    def set_auto_cycle(self, is_auto: bool) -> bool:
        """Toggle the cycle-shift auto set flag (SetAutoCycle)."""
        self.auto = bool(is_auto)
        return True

    def reset_cyc_ope(self) -> bool:
        """Reset the cycle operation mode to None (ResetCycOpe)."""
        self.fs.operation_mode = "None"
        return True

    # ── data access ───────────────────────────────────────────────────────
    def current_file(self):
        """FieldFile at the current (possibly fractional) cycle id."""
        return interpolate_at(self.fs, self.cur_id, cache=self.cache)


# ── multi-FileSet lockstep (R3.6 Timeline Sync) ───────────────────────────

class SyncedTimeline:
    """Several FileSets played back in lockstep (R3.6 Timeline Sync).

    A single timeline value (a cycle number, or a 0-based index) drives
    every registered :class:`FileSet`. ``align="cycle"`` resolves the
    value against each FileSet's own cycle list (nearest at-or-after, like
    :meth:`FileSet.find`); ``align="index"`` maps the value to the same
    ordinal member of every sequence so differently-numbered series
    advance together.
    """

    def __init__(self, align: str = "cycle"):
        self.filesets: list[FileSet] = []
        self.align = align if align in ("cycle", "index") else "cycle"

    def __bool__(self) -> bool:
        return bool(self.filesets)

    def __len__(self) -> int:
        return len(self.filesets)

    def add(self, fs: Optional[FileSet]) -> "SyncedTimeline":
        if fs is not None and fs not in self.filesets:
            self.filesets.append(fs)
        return self

    def remove(self, fs: FileSet) -> "SyncedTimeline":
        if fs in self.filesets:
            self.filesets.remove(fs)
        return self

    def clear(self) -> "SyncedTimeline":
        self.filesets = []
        return self

    # ── unified range ─────────────────────────────────────────────────────
    def min_cycle(self) -> Optional[int]:
        vals = [fs.min_cycle() for fs in self.filesets
                if fs.min_cycle() is not None]
        return min(vals) if vals else None

    def max_cycle(self) -> Optional[int]:
        vals = [fs.max_cycle() for fs in self.filesets
                if fs.max_cycle() is not None]
        return max(vals) if vals else None

    def max_index(self) -> int:
        lens = [len(fs) for fs in self.filesets if len(fs) > 0]
        return (max(lens) - 1) if lens else 0

    def range(self) -> tuple[int, int]:
        """Unified ``(lo, hi)`` for the active alignment mode."""
        if self.align == "index":
            return 0, self.max_index()
        lo, hi = self.min_cycle(), self.max_cycle()
        if lo is None or hi is None:
            return 0, 0
        return lo, hi

    # ── resolution / loading ──────────────────────────────────────────────
    def member_for(self, fs: FileSet, value: int) -> Optional[SequenceMember]:
        if self.align == "index":
            idx = int(value)
            if 0 <= idx < len(fs.members):
                return fs.members[idx]
            return None
        return fs.find(int(value))

    def members_at(self, value: int) -> list[tuple[FileSet, Optional[SequenceMember]]]:
        return [(fs, self.member_for(fs, value)) for fs in self.filesets]

    def load_all(self, value: int, cache: Optional[dict] = None):
        """``[(FileSet, FieldFile | None), ...]`` at *value* across every FileSet."""
        out = []
        for fs, member in self.members_at(value):
            ff = None
            if member is not None:
                ff = load_member(fs, member.cycle, cache)
            out.append((fs, ff))
        return out