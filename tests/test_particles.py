"""FPH particle parsing tests: multi-frame accumulation (B)."""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

SAMPLE_FPH = Path(r"D:\training\cgns\examples\tr03_9.fph")


def _section(name: str, *payloads: bytes) -> bytes:
    """CRDL section: [I4=32][name][I4=32] + [12][bc][payload][bc] blocks."""
    body = b""
    for pay in payloads:
        body += struct.pack(">ii", 12, len(pay)) + pay
        body += struct.pack(">i", len(pay))
    return (struct.pack(">i", 32) + name.ljust(32).encode("ascii")
            + struct.pack(">i", 32) + body)


def _coordinate(values: np.ndarray) -> bytes:
    """Descriptor [12,4,N,1] + payload [12][4N][N float32 BE][4N]."""
    n = values.size
    payload = np.asarray(values, dtype=">f4").tobytes()
    return (struct.pack(">iiii", 12, 4, n, 1)
            + struct.pack(">ii", 12, len(payload)) + payload
            + struct.pack(">i", len(payload)))


def _fph_with_two_frames() -> bytes:
    """LS_ParticlesPosition with 6x200B blocks (2 frames) + VELP."""
    rng = np.random.default_rng(7)
    pos_blocks = [_coordinate(rng.random(50)) for _ in range(6)]
    vel_blocks = [_coordinate(rng.random(50)) for _ in range(6)]
    data = b"CRDL-FLD"
    data += _section("LS_ParticlesPosition", *pos_blocks)
    data += _section("LS_ParticleV:VELP", *vel_blocks)
    return data


def test_particle_frames_synthetic():
    """Two frames x 50 particles accumulate from six 200B blocks."""
    from fv.crdl.fields import (
        parse_particle_frames,
        parse_particle_variable_frames,
        parse_particle_variables,
        parse_particles,
    )
    data = _fph_with_two_frames()
    frames = parse_particle_frames(data)
    assert len(frames) == 2
    for pos, vel in frames:
        assert pos.shape == (50, 3) and vel.shape == (50, 3)
    # first frame == backward-compatible single-frame API
    parsed = parse_particles(data)
    assert parsed is not None
    pos0, vel0 = parsed
    assert np.array_equal(pos0, frames[0][0])
    assert np.array_equal(vel0, frames[0][1])
    vf = parse_particle_variable_frames(data)
    assert len(vf["VELP"]) == 2
    assert vf["VELP"][0].shape == (50, 3)
    sv = parse_particle_variables(data)
    assert sv["VELP"].shape == (50, 3)


def test_particle_frames_odd_blocks_dropped():
    """A trailing partial triplet is dropped, not misaligned."""
    from fv.crdl.fields import parse_particle_frames
    rng = np.random.default_rng(3)
    blocks = [_coordinate(rng.random(50)) for _ in range(5)]
    data = b"CRDL-FLD" + _section("LS_ParticlesPosition", *blocks)
    frames = parse_particle_frames(data)
    assert len(frames) == 1  # 3 blocks = 1 frame; 2 trailing dropped


@pytest.mark.skipif(not SAMPLE_FPH.exists(), reason="tr03_9.fph not present")
def test_particle_frames_tr03():
    """Real scFLOW result: 3+3 coordinate blocks → 1 frame of 50."""
    from fv.crdl.fields import parse_particle_frames, parse_particles
    data = SAMPLE_FPH.read_bytes()
    frames = parse_particle_frames(data)
    assert len(frames) == 1
    pos, vel = frames[0]
    assert pos.shape == (50, 3)
    assert vel.shape == (50, 3)
    # legacy entry still returns the first frame
    parsed = parse_particles(data)
    assert parsed is not None and parsed[0].shape == (50, 3)


def test_particle_frames_large_count():
    """120 particles per coordinate: N=120 descriptors, no truncation."""
    from fv.crdl.fields import parse_particle_frames
    rng = np.random.default_rng(11)
    blocks = [_coordinate(rng.random(120)) for _ in range(3)]
    data = b"CRDL-FLD" + _section("LS_ParticlesPosition", *blocks)
    frames = parse_particle_frames(data)
    assert len(frames) == 1
    assert frames[0][0].shape == (120, 3)
