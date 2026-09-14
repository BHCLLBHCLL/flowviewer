"""Shared loader for the in-repo golden corpus (R114).

The corpus is produced by ``scripts/make_golden.py`` from the real sample
files and committed under ``tests/data/golden/``.  Tests that use it run on
any machine (and on CI) instead of skipping for want of a 100 MB sample.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

GOLDEN = Path(__file__).resolve().parent / "data" / "golden"


def available() -> bool:
    return (GOLDEN / "meta.json").is_file()


@lru_cache(maxsize=4)
def load(name: str) -> dict:
    """Load ``fld_small`` / ``fph_small`` as a plain dict of arrays."""
    path = GOLDEN / (name + ".npz")
    with np.load(path) as data:
        return {k: data[k] for k in data.files}


@lru_cache(maxsize=1)
def meta() -> dict:
    return json.loads((GOLDEN / "meta.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def var_stats(name: str) -> dict:
    """Per-variable min/max/mean/size recorded for a corpus file."""
    return json.loads(str(load(name)["var_stats"]))
