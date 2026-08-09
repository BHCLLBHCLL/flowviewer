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