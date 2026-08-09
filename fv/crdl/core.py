"""CRDL container primitives shared by GPH / FPH / FLD binary files.

Both GPH and FLD files share the CRDL-FLD big-endian container layout:

    [I4=8]["CRDL-FLD"][I4=8][dims...]

followed by named sections of the form ``[I4=32][name padded to 32B][I4=32]
[section body]``.  Within a section each payload is ``[I4=12][I4=byte_count]
[payload][I4=byte_count]``, interleaved with 16-byte descriptors
``[12, type_code, dim0, dim1]``.

These primitives are converged from the tested GPH / FLD decoders:
``gph_model.py``, ``gph2cgns.py``, ``fph2cgns.py`` and ``fld_model.py``
(see DEV_PLAN.md R1 / R2).
"""

import mmap
import struct
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import numpy as np

LARGE_FILE_BYTES = 512 * 1024 * 1024  # mmap threshold

# Named sections that can terminate another section.  Union of the GPH and
# FLD candidate lists (order matters only for earliest-offset lookup).
SECTION_BOUNDARY_NAMES = [
    "FileRevision", "Application", "ApplicationVersion", "ReleaseDate",
    "GridType", "Dimension", "Bias", "Date", "Comments", "Cycle",
    "Unused", "Encoding", "HeaderDataEnd", "OverlapStart_0",
    "LS_CoordinateSystem",
    "LS_CvolIdOfElements", "LS_Links", "LS_Nodes", "LS_SurfaceRegions",
    "LS_SolverUnusedRegions", "LS_VolumeRegions", "LS_Parts",
    "LS_Assemblies", "LS_SPHFile", "Element_InformationFlag",
    "LS_MatOfElements", "LS_Elements", "LS_VolumeGeometryArray",
    "LS_SurfaceGeometryArray", "LS_SFile", "Pressure", "Temperature",
    "CN01", "VECT", "HVEC", "LS_STREAMcoc", "LS_STREAMmultiblock",
    "OverlapEnd",
]


def read_i32_be(data, pos: int) -> int:
    return int.from_bytes(data[pos : pos + 4], "big")


def read_f32_be(data, pos: int) -> float:
    return struct.unpack(">f", data[pos : pos + 4])[0]


def read_f64_be(data, pos: int) -> float:
    return struct.unpack(">d", data[pos : pos + 8])[0]


def read_f64_wr(data, pos: int) -> float:
    """Read float64 stored in word-reversed (middle-endian) format.

    Some legacy GPH files encode each 8-byte double as two 32-bit
    big-endian words in reversed order: ``[lower_32bit_word][upper]``.
    """
    lower = int.from_bytes(data[pos : pos + 4], "big")
    upper = int.from_bytes(data[pos + 4 : pos + 8], "big")
    combined = ((upper << 32) | lower).to_bytes(8, "big")
    return struct.unpack(">d", combined)[0]


def find_section(data, name: str) -> int:
    """Return offset of the ``I4=32`` marker that precedes *name*, or -1."""
    name_padded = name.ljust(32).encode("ascii")
    idx = data.find(name_padded)
    if idx < 4:
        return -1
    if read_i32_be(data, idx - 4) == 32:
        return idx - 4
    return -1


# ── section-offset index ───────────────────────────────────────────────────
#
# ``section_end`` used to re-scan the whole file for every boundary name on
# every call (≈31 × bytes.find per section).  Building the index once per
# buffer turns that into a single pass over the boundary list.

_section_index_cache: dict = {}          # id(data) → (len(data), offsets, data)


def _section_offsets(data) -> dict:
    """``{boundary_name: first_offset}`` for *data*, built once per buffer."""
    key = id(data)
    entry = _section_index_cache.get(key)
    if entry is not None and entry[0] == len(data):
        return entry[1]
    offsets: dict = {}
    for name in SECTION_BOUNDARY_NAMES:
        off = find_section(data, name)
        if off >= 0:
            offsets[name] = off
    _section_index_cache[key] = (len(data), offsets, data)  # keep data alive
    return offsets


def section_end(data, sec_start: int) -> int:
    """End offset of the section (start of next known section or EOF)."""
    best = len(data)
    for off in _section_offsets(data).values():
        if off > sec_start and off < best:
            best = off
    return best


def iter_data_blocks(data, sec_start: int, sec_end: int):
    """Yield ``(payload_start, byte_count)`` for each data block in a section."""
    pos = sec_start + 40  # skip [I4=32][32B name][I4=32]
    n = len(data)
    while pos + 8 <= sec_end and pos + 8 <= n:
        if read_i32_be(data, pos) != 12:
            pos += 4
            continue
        v = read_i32_be(data, pos + 4)

        # Descriptor [12, type_code in {4,8}, dim0, dim1] is 16 bytes.
        if v in (4, 8) and pos + 16 <= sec_end:
            dim0 = read_i32_be(data, pos + 8)
            dim1 = read_i32_be(data, pos + 12)
            if 0 < dim0 < 10_000_000 and 0 < dim1 < 10_000_000:
                pos += 16
                continue

        # Otherwise treat as a data header [12, byte_count].
        bc = v
        if bc <= 0 or pos + 8 + bc + 4 > sec_end:
            pos += 4
            continue
        payload_end = pos + 8 + bc
        if read_i32_be(data, payload_end) != bc:
            pos += 4
            continue
        yield pos + 8, bc
        pos = payload_end + 4


@contextmanager
def open_buffer(filepath: str):
    """Yield a bytes-like buffer; mmap files larger than 512 MiB."""
    size = Path(filepath).stat().st_size
    if size <= LARGE_FILE_BYTES:
        with open(filepath, "rb") as f:
            yield f.read()
        return
    import mmap
    f = open(filepath, "rb")
    try:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            yield mm
        finally:
            mm.close()
    finally:
        f.close()


def f32_be_array(data, offset: int, count: int) -> np.ndarray:
    return np.frombuffer(data, dtype=">f4", count=count, offset=offset).astype(np.float64).copy()


def f64_be_array(data, offset: int, count: int) -> np.ndarray:
    return np.frombuffer(data, dtype=">f8", count=count, offset=offset).copy()


def f64_wr_array(data, offset: int, count: int) -> np.ndarray:
    """Read *count* word-reversed float64 values from *data* at *offset*."""
    raw = np.frombuffer(data, dtype=">u4", count=count * 2, offset=offset)
    lower = raw[0::2].astype(np.uint64)
    upper = raw[1::2].astype(np.uint64)
    bits = (upper << 32) | lower
    return bits.view(">f8").astype(np.float64)


def i32_be_array(data, offset: int, count: int) -> np.ndarray:
    return np.frombuffer(data, dtype=">i4", count=count, offset=offset).astype(np.int64).copy()


def cell_count_from_data(data) -> Optional[int]:
    """Return number of cells from LS_MatOfElements, or None if missing."""
    sec = find_section(data, "LS_MatOfElements")
    if sec < 0:
        return None
    blocks = list(iter_data_blocks(data, sec, section_end(data, sec)))
    if not blocks:
        return None
    return blocks[0][1] // 4