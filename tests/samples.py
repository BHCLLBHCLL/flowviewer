"""Real Cradle samples used by the suite, resolved at run time.

The samples used to live in D:/training/cgns/examples.  On this machine they
were relocated to the E: drive (E:/cradle) and to D:/training/cradle, which
turned a *missing sample* into a *test failure*: tests/test_pod.py failed with
FileNotFoundError on tr03_9.fph (found while starting R133c) while the other
modules that use the same file skip.

sample(name) returns the first existing candidate or None so a test can skip
with a reason instead of blowing up.  Adopt it where a real sample is needed;
the wider repointing of the ~28 modules is tracked in analysis/gap_table.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

#: search roots, most specific first
ROOTS = [
    Path(r"D:\training\cgns\examples"),
    Path(r"E:\cradle"),
    Path(r"D:\training\cradle"),
]


def sample(name: str) -> Optional[Path]:
    """First existing ROOT / name, or None when the sample is absent."""
    for root in ROOTS:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None
