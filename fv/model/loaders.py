"""File-format registry: which extensions have real loaders + format probe.

The GUI filter list mirrors scPOST's catalogue.  Working parsers are
whatever ``dataset._register_loaders`` advertised (FLD/FPH/GPH plus
CGNS, Marc ``.dat``/``.t16``/``.t19``, Nastran, Neutral, …).
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
    if suf == "op2":
        try:
            from ..crdl.op2 import _HAS_PYNASTRAN
            return "op2" if _HAS_PYNASTRAN else "op2-unavailable"
        except Exception:  # pragma: no cover
            return "op2"
    if suf == "cgns":
        try:
            from ..crdl.cgns_adf import is_cgns_adf
            if is_cgns_adf(str(p)):
                return "cgns-adf"
        except Exception:  # pragma: no cover
            pass
        try:
            import h5py
            if h5py.is_hdf5(str(p)):
                return "cgns-hdf5"
        except ImportError:  # pragma: no cover - h5py absent
            return "cgns"
        return "cgns-adf"
    if suf in ("fph", "gph", "emt"):
        return "fph"      # EMT is a Cradle binary result, fph-family
    if suf in ("fld", "ifld"):
        return "fld"
    if suf in ("t16", "t19"):
        try:
            from ..crdl.marc import is_marc_post
            return "marc-post" if is_marc_post(str(p)) else "marc"
        except Exception:  # pragma: no cover
            return "marc"
    if suf == "dat":
        return "marc"
    if suf in ("cradleviewer", "cvff", "cvw"):
        return "cvff"
    return "other"


def describe(path: str) -> str:
    """Human-readable loadability line used in logs / dialog info."""
    if can_load(path):
        return f"loadable ({', '.join(sorted(LOADERS))})"
    tag = probe_format(path)
    if tag.startswith("cgns"):
        return f"CGNS file detected ({tag}) — loadable via cgns loader"
    return f"{Path(path).suffix or '(no extension)'} — no loader registered"