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

import hashlib
import mmap
import re
import struct
from collections import OrderedDict
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
    "LS_ParticlesPosition", "LS_ParticleV:VELP",
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
# section_end used to re-scan the whole file for every boundary name on every
# call.  R127 replaced the per-id cache, which stored the buffer itself under
# the comment "keep data alive": every file opened in a session then stayed
# resident for the rest of the session (measured: a 1.36 GB FPH pinned after
# indexing) and a reopened file could never hit the cache anyway, because
# open_buffer hands out a new object each time.  The index is now keyed by a
# sampled content digest, holds only the offsets, and lives in a small LRU.

#: Section header: the I4=32 marker followed by the 32-byte name field.
_SECTION_MARK = re.compile(rb"\x00\x00\x00\x20([ -~]{4,32})")

#: Boundary names as a set, for the single-pass scan.
_BOUNDARY_SET = frozenset(SECTION_BOUNDARY_NAMES)

#: How many buffer indexes to keep alive (each is a few dozen ints).
_SECTION_INDEX_MAX = 16

#: Bytes sampled at the start, middle and end of a buffer for its key.
_KEY_SAMPLE = 64 * 1024

_section_index_cache: OrderedDict = OrderedDict()


def _buffer_key(data) -> bytes:
    """Content key for *data*: its size plus three sampled windows (R127).

    The parsers all receive the buffer, never the path, so a path key would
    have to be threaded through every signature -- and it would still miss
    copies of the same buffer.  A content key survives both.  Sampling makes
    the digest about 200x cheaper than hashing a 1.4 GB buffer: a collision
    would mean two different files agreeing on their size and on 64 KiB at
    their start, middle and end.
    """
    n = len(data)
    parts = [n.to_bytes(8, "little")]
    for start in (0, max(0, n // 2 - _KEY_SAMPLE // 2),
                  max(0, n - _KEY_SAMPLE)):
        parts.append(bytes(data[start:start + _KEY_SAMPLE]))
    return hashlib.blake2b(b"".join(parts), digest_size=16).digest()


def _scan_section_offsets(data) -> dict:
    """{name: first offset} for every boundary-name header, in one pass.

    The old build called find_section once per boundary name, i.e. scanned
    the whole buffer 40 times: measured 6.57 s on a 1.36 GB FPH against
    1.54 s for this single pass.  The regex captures the same space-padded
    name field find_section matches (printable run after the I4=32 marker,
    right-trimmed).
    """
    out: dict = {}
    for m in _SECTION_MARK.finditer(data):
        name = m.group(1).decode("ascii", "replace").rstrip()
        if name in _BOUNDARY_SET:
            out.setdefault(name, m.start())
    return out


def _section_offsets(data) -> dict:
    """{boundary_name: first_offset} for *data* (cached, R127)."""
    key = _buffer_key(data)
    entry = _section_index_cache.get(key)
    if entry is not None:
        try:
            _section_index_cache.move_to_end(key)
        except KeyError:  # pragma: no cover - evicted by another thread
            pass
        return entry
    offsets = _scan_section_offsets(data)
    _section_index_cache[key] = offsets
    while len(_section_index_cache) > _SECTION_INDEX_MAX:
        _section_index_cache.popitem(last=False)
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


_HEADER_META_NAMES = ("FileRevision", "Application", "ApplicationVersion",
                      "ReleaseDate", "GridType", "Dimension", "Bias",
                      "Date", "Comments", "Unit:$TEMP")


def parse_header_meta(data) -> dict[str, str]:
    """Best-effort header metadata → ``{section_name: value}``.

    Header sections store either a small printable text payload
    (e.g. ``Application`` = "SCRYUTET") or descriptor dims; the first
    printable payload wins, otherwise the first descriptor dims pair is
    formatted as ``"d0xd1"``.
    """
    meta: dict[str, str] = {}
    for nm in _HEADER_META_NAMES:
        s = find_section(data, nm)
        if s < 0:
            continue
        e = section_end(data, s)
        texts: list[str] = []
        dims: list[tuple[int, int]] = []
        pos = s + 40
        while pos + 12 <= e:
            if read_i32_be(data, pos) != 12:
                pos += 4
                continue
            v = read_i32_be(data, pos + 4)
            if v in (1, 2, 4, 8) and pos + 16 <= e:
                d0 = read_i32_be(data, pos + 8)
                d1 = read_i32_be(data, pos + 12)
                if 0 <= d0 < 10_000_000 and 0 <= d1 < 10_000_000:
                    dims.append((d0, d1))
                    pos += 16
                    continue
            bc = v
            if 0 < bc <= 256 and pos + 8 + bc + 4 <= e:
                raw = data[pos + 8:pos + 8 + bc]
                if raw and all(b == 0 or 32 <= b < 127 for b in raw):
                    txt = raw.decode("ascii", "replace")
                    txt = txt.strip("\x00 ").strip()
                    if txt:
                        texts.append(txt)
                pos += 8 + bc + 4
                continue
            pos += 4
        if texts:
            meta[nm] = texts[0]
        elif dims:
            meta[nm] = f"{dims[0][0]}x{dims[0][1]}"
    return meta

@contextmanager
def open_buffer(filepath: str):
    """Yield a bytes-like buffer; mmap files larger than 512 MiB."""
    size = Path(filepath).stat().st_size
    if size <= LARGE_FILE_BYTES:
        with open(filepath, "rb") as f:
            yield f.read()
        return
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
