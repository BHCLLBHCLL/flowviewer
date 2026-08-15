"""File-format registry: which extensions have real loaders + format probe.

The GUI filter list intentionally mirrors scPOST's catalogue (CGNS/XDMF/
Nastran/…), but only ``fld/ifld/fph/gph`` have working parsers.  This module
keeps a single registry so the dialog and ``main.open_file`` can answer
"is this file actually loadable?" honestly and give a useful message for
formats that are detected-but-not-yet-parsed (e.g. CGNS/HDF5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

# extension (lowercase) → loader function returning a FieldFile
LOADERS: dict[str, Callable] = {}


def register(ext: str, fn: Callable) -> None:
    LOADERS[ext.lower().lstrip(".")] = fn


def loaders() -> frozenset[str]:
    return frozenset(LOADERS)


def can_load(path: str) -> bool:
    return _suffix(Path(path)) in LOADERS


def _suffix(p: Path) -> str:
    return p.suffix.lower().lstrip(".")


def probe_format(path: str) -> str:
    """Return a short diagnostic tag: 'fld' | 'fph' | 'cgns' | 'other'."""
    p = Path(path)
    suf = _suffix(p)
    if suf == "pph":
        return "pph"
    if suf == "cgns":
        try:
            import h5py
            if h5py.is_hdf5(str(p)):
                return "cgns-hdf5"
            return "cgns-adf"
        except ImportError:  # pragma: no cover - h5py absent
            return "cgns"
    if suf in ("fph", "gph", "emt"):
        return "fph"      # EMT is a Cradle binary result, fph-family
    if suf in ("fld", "ifld"):
        return "fld"
    return "other"


def describe(path: str) -> str:
    """Human-readable loadability line used in logs / dialog info."""
    if can_load(path):
        return f"loadable ({', '.join(sorted(LOADERS))})"
    tag = probe_format(path)
    if tag.startswith("cgns"):
        return f"CGNS file detected ({tag}) — loadable via cgns loader"
    return f"{Path(path).suffix or '(no extension)'} — no loader registered"