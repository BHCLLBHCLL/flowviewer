"""iFLD lightweight metadata scan (D3).

iFLD shares the CRDL container; scanning reads only the section index and
the small descriptor blocks, never the full field payloads - the local/
trimming-read building block.  Returns counts + variable names.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .core import (find_section, iter_data_blocks, open_buffer,
                   read_i32_be, section_end)

def scan_ifld(path: str):
    """Quick metadata scan of an iFLD/FLD file (D3)."""
    try:
        with open_buffer(path) as data:
            return _scan(data)
    except Exception:
        return None


def _scan(data) -> dict:
    n_cells = 0
    sec = find_section(data, "LS_MatOfElements")
    if sec >= 0:
        for p, bc in iter_data_blocks(data, sec, section_end(data, sec)):
            if bc > 0 and bc % 4 == 0:
                n_cells = bc // 4
                break
    n_vertices = 0
    sec = find_section(data, "LS_Nodes")
    if sec >= 0:
        for p, bc in iter_data_blocks(data, sec, section_end(data, sec)):
            if bc in (4, 8):
                continue
            if bc > n_vertices:
                n_vertices = bc
    variables = []
    for name in ("Pressure", "Temperature", "CN01", "VECT", "HVEC"):
        if find_section(data, name) >= 0:
            variables.append(name)
    return {
        "n_cells": n_cells,
        "n_vertices": n_vertices,
        "variables": variables,
        "file_size": len(data),
    }
