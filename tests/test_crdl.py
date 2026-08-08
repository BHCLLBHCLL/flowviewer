"""CRDL container primitives."""

import sys
from pathlib import Path

import pytest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fv.crdl import core  # noqa: E402


def test_core_primitives_exist():
    assert callable(core.find_section)
    assert callable(core.section_end)
    assert callable(core.iter_data_blocks)
    assert callable(core.read_i32_be)


def _section_bytes(name: str, payload: bytes) -> bytes:
    """Build one named section: [I4=32][32B name][I4=32][body]."""
    block = (
        (12).to_bytes(4, "big")
        + len(payload).to_bytes(4, "big")
        + payload
        + len(payload).to_bytes(4, "big")
    )
    return (
        (32).to_bytes(4, "big")
        + name.ljust(32).encode("ascii")
        + (32).to_bytes(4, "big")
        + block
    )


def test_find_section_and_iter_data_blocks():
    header = b"CRDL-FLD"
    sec1 = _section_bytes("LS_Nodes", b"\x01\x02\x03\x04" * 4)
    sec2 = _section_bytes("Pressure", b"\x05" * 8)
    data = header + sec1 + sec2
    off = core.find_section(data, "LS_Nodes")
    assert off >= 0
    blocks = list(core.iter_data_blocks(data, off, core.section_end(data, off)))
    assert blocks == [(off + 40 + 8, 16)]


def test_read_i32_be():
    assert core.read_i32_be(b"\x00\x00\x00\x20", 0) == 32
    assert core.read_i32_be(b"\x00\x00\x01\x00", 0) == 256


def test_open_buffer_context():
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(b"hello" * 3)
        name = f.name
    with core.open_buffer(name) as data:
        assert data[:5] == b"hello"
    Path(name).unlink()


def test_cell_count_from_data():
    import tempfile
    from fv.crdl.core import cell_count_from_data
    payload = np.array([1, 2, 3], dtype=">i4").tobytes()
    sec = _section_bytes("LS_MatOfElements", payload)
    data = b"CRDL-FLD" + sec
    assert cell_count_from_data(data) == 3