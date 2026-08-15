"""Field variable parsing on top of GPH / FLD / FPH mesh layouts.

* FPH (scFLOW results): the ``LS_SPHFile`` section stores cell-centred
  float32 variables (``EC_Scalar:NAME`` / ``EC_Vector:NAME``).
* FLD: solution fields are per-vertex float64 blocks inside named sections
  (``Pressure``, ``Temperature``, ``CN01``, ``VECT``, ``HVEC``).

Converged from ``fph2cgns._parse_fph_flow_solution`` and
``fld_model.parse_fld`` (DEV_PLAN.md R1/R2).
"""

from typing import Optional

import numpy as np

from .core import (
    find_section,
    section_end,
    iter_data_blocks,
    open_buffer,
    f32_be_array,
    read_i32_be,
    read_f64_be,
)


def parse_cycle_meta(data) -> tuple[Optional[int], Optional[float]]:
    """Parse header ``Cycle`` section → ``(cycle_id, time)``.

    scPOST Draw Window overlay uses these as ``Cycle`` / ``Time``.
    Layout: after the section name, the first I4 data block is the cycle
    number and the first R8 (float64) data block is the physical time.
    """
    sec_start = find_section(data, "Cycle")
    if sec_start < 0:
        return None, None
    sec_end = section_end(data, sec_start)
    cycle: Optional[int] = None
    time: Optional[float] = None
    pos = sec_start + 40
    while pos + 12 <= sec_end:
        if read_i32_be(data, pos) != 12:
            pos += 4
            continue
        bc = read_i32_be(data, pos + 4)
        # I4 payload: [12][4][value][4]
        if (bc == 4 and pos + 16 <= sec_end
                and read_i32_be(data, pos + 12) == 4):
            val = read_i32_be(data, pos + 8)
            if cycle is None and 0 <= val < 10_000_000:
                cycle = int(val)
            pos += 16
            continue
        # R8 payload: [12][8][f64][8]
        if (bc == 8 and pos + 20 <= sec_end
                and read_i32_be(data, pos + 16) == 8):
            val = read_f64_be(data, pos + 8)
            if time is None and abs(val) < 1e20:
                time = float(val)
            pos += 20
            continue
        # Descriptor [12, type∈{4,8}, dim0, dim1]
        if bc in (4, 8) and pos + 16 <= sec_end:
            pos += 16
            continue
        if bc >= 0 and pos + 8 + bc + 4 <= sec_end:
            pos = pos + 8 + bc + 4
            continue
        pos += 4
    return cycle, time


def has_particle_results(data) -> bool:
    """True if the file contains scFLOW particle result sections."""
    for name in ("LS_ParticlesPosition", "LS_ParticleV:VELP"):
        # Section names may be longer than 32? Cradle pads to 32.
        # LS_ParticleV:VELP fits in 32 with spaces.
        if find_section(data, name) >= 0:
            return True
        # Fallback: raw name search with leading I4=32 marker
        padded = name.ljust(32).encode("ascii")
        idx = data.find(padded)
        if idx >= 4 and read_i32_be(data, idx - 4) == 32:
            return True
    return False


def _particle_frame_blocks(data, sec_start: int, boundary: int) -> list[np.ndarray]:
    """Coordinate arrays inside a particle section.

    Layout: ``[12][4][N][1]`` descriptor (N = particles per coordinate;
    followed by one ``[12][4N]`` float32 payload block.  One coordinate
    array per block; consecutive equal-length arrays form X/Y/Z triplets
    (one triplet per time frame).  Works for any N, so particle counts
    beyond 50 accumulate instead of truncating.
    """
    out: list[np.ndarray] = []
    pos = sec_start + 40
    end = min(boundary, len(data))
    while pos + 16 <= end:
        if read_i32_be(data, pos) != 12:
            pos += 4
            continue
        a = read_i32_be(data, pos + 4)
        n0 = read_i32_be(data, pos + 8)
        n1 = read_i32_be(data, pos + 12)
        if a == 4 and n1 == 1 and 2 <= n0 <= 10_000_000:
            plen = n0 * 4
            p2 = pos + 16
            if (p2 + 8 + plen + 4 <= end
                    and read_i32_be(data, p2) == 12
                    and read_i32_be(data, p2 + 4) == plen):
                out.append(f32_be_array(data, p2 + 8, n0))
                pos = p2 + 8 + plen + 4
                continue
        pos += 4
    return out


def _frames_from_blocks(blocks: list[np.ndarray]
                        ) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Group consecutive equal-length blocks into X/Y/Z frames.

    Returns ``[(x, y, z), ...]``.  A trailing partial triplet is dropped.
    """
    frames: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    k = 0
    while k + 2 < len(blocks):
        a, b, c = blocks[k], blocks[k + 1], blocks[k + 2]
        if a.size == b.size == c.size and a.size > 0:
            frames.append((a, b, c))
            k += 3
        else:
            k += 1
    return frames


def parse_particle_frames(data) -> list[tuple[np.ndarray, np.ndarray]]:
    """All particle time frames → ``[(positions (N,3), velocities (N,3)), ...]``.

    ``LS_ParticlesPosition`` frames are matched with ``LS_ParticleV:VELP``
    frames by index; missing velocity frames fall back to zeros.  Empty
    list when the file has no particle results.
    """
    pos_sec = find_section(data, "LS_ParticlesPosition")
    if pos_sec < 0:
        return []
    pos_end = section_end(data, pos_sec)
    vel_sec = find_section(data, "LS_ParticleV:VELP")
    vel_end = len(data)

    pos_frames = _frames_from_blocks(
        _particle_frame_blocks(data, pos_sec, pos_end))
    if not pos_frames:
        return []
    if vel_sec >= 0:
        vel_frames = _frames_from_blocks(
            _particle_frame_blocks(data, vel_sec, vel_end))
    else:
        vel_frames = []

    out: list[tuple[np.ndarray, np.ndarray]] = []
    for i, (x, y, z) in enumerate(pos_frames):
        positions = np.column_stack([x, y, z]).astype(np.float64)
        if i < len(vel_frames):
            vx, vy, vz = vel_frames[i]
            velocities = np.column_stack([vx, vy, vz]).astype(np.float64)
        else:
            velocities = np.zeros_like(positions)
        out.append((positions, velocities))
    return out


def parse_particles(data) -> Optional[tuple[np.ndarray, np.ndarray]]:
    """First particle frame → ``(positions (N,3), velocities (N,3))``.

    Backward-compatible single-frame entry point; use
    :func:`parse_particle_frames` for every time frame.
    """
    frames = parse_particle_frames(data)
    if not frames:
        return None
    return frames[0]


def parse_particle_variable_frames(data) -> dict[str, list[np.ndarray]]:
    """Every 'LS_ParticleV:<var>' nested section -> {var: [frame (N,3), ...]}."""
    out: dict[str, list[np.ndarray]] = {}
    marker = b"LS_ParticleV:"
    pos = 0
    while True:
        idx = data.find(marker, pos)
        if idx < 0:
            break
        pos = idx + 1
        if idx < 4 or read_i32_be(data, idx - 4) != 32:
            continue
        raw_name = data[idx:idx + 32].split(b"\x00")[0].strip()
        try:
            name = raw_name.decode("ascii")
        except UnicodeDecodeError:
            continue
        if not name.startswith("LS_ParticleV:"):
            continue
        var = name[len("LS_ParticleV:"):].strip()
        sec_start = idx - 4
        sec_end = section_end(data, sec_start)
        frames = [np.column_stack(c).astype(np.float64)
                  for c in _frames_from_blocks(
                      _particle_frame_blocks(data, sec_start, sec_end))]
        if frames:
            out[var] = frames
    return out


def parse_particle_variables(data) -> dict:
    """Every 'LS_ParticleV:<var>' nested section -> {var: first-frame (N,3)}.

    Backward-compatible single-frame entry point; use
    :func:`parse_particle_variable_frames` for every time frame.
    """
    return {var: frames[0] for var, frames
            in parse_particle_variable_frames(data).items() if frames}


def parse_fph_flow_solution(data, n_cells: int) -> dict[str, np.ndarray]:
    """Parse ``LS_SPHFile`` → ``{var: float64 (n_cells,)}`` (cell-centred)."""
    sec_start = find_section(data, "LS_SPHFile")
    if sec_start < 0:
        return {}
    sec_end = section_end(data, sec_start)

    blocks = list(iter_data_blocks(data, sec_start, sec_end))
    if not blocks:
        return {}

    expected_data_bytes = n_cells * 4  # float32 BE

    name_indices: list[tuple[int, str]] = []
    for i, (p, bc) in enumerate(blocks):
        if bc != 32:
            continue
        raw = data[p:p + bc]
        if not all(b == 0 or 32 <= b < 127 for b in raw):
            continue
        s = raw.decode("ascii", errors="replace").rstrip("\x00 ").rstrip()
        if s.startswith("EC_Scalar:") or s.startswith("EC_Vector:"):
            name_indices.append((i, s))

    if not name_indices:
        return {}

    scalars: list[tuple[str, np.ndarray]] = []
    vectors: list[tuple[str, list[np.ndarray]]] = []

    for vi, (bi, name) in enumerate(name_indices):
        next_bi = (name_indices[vi + 1][0]
                   if vi + 1 < len(name_indices) else len(blocks))
        data_blocks: list[np.ndarray] = []
        for j in range(bi + 1, next_bi):
            p, bc = blocks[j]
            if bc == expected_data_bytes:
                arr = f32_be_array(data, p, bc // 4)
                data_blocks.append(arr)
        if not data_blocks:
            continue

        if name.startswith("EC_Scalar:"):
            var = name[len("EC_Scalar:"):]
            scalars.append((var, data_blocks[0]))
        else:  # EC_Vector:
            var = name[len("EC_Vector:"):]
            if len(data_blocks) >= 3:
                vectors.append((var, data_blocks[:3]))

    result: dict[str, np.ndarray] = {}
    for var, arr in scalars:
        result[var] = arr
    for var, comps in vectors:
        for ax, suffix in enumerate(("X", "Y", "Z")):
            result[f"{var}{suffix}"] = comps[ax]
    return result


def parse_fields_from_file(filepath: str) -> dict[str, np.ndarray]:
    """Inspect a GPH/FPH/FLD file and return whichever variables it carries.

    FPH selects cell-centered ``LS_SPHFile`` variables
    (keyed as ``SCALAR`` / ``VECT``+X/Y/Z);
    FLD selects vertex-centered sections keyed as ``PRES`` / ``TEMP`` /
    ``VECTX`` …
    """
    with open_buffer(filepath) as data:
        if find_section(data, "LS_Elements") >= 0 or find_section(data, "LS_MatOfElements") >= 0:
            n_vertices = _fld_vertex_count(data)
            return _collect_fld_fields(data, n_vertices)

        n_cells_est = _estimate_cells(data)
        return parse_fph_flow_solution(data, n_cells=n_cells_est)


def _fld_vertex_count(data) -> int:
    """Best-effort FLD vertex count (LS_Nodes f64 block first element)."""
    from . import mesh_fld
    xyz, n = mesh_fld._parse_ls_nodes(data)
    return n


def _estimate_cells(data) -> int:
    """Best-effort cell count from LS_SPHFile array sizes."""
    total = 0
    sec_start = find_section(data, "LS_SPHFile")
    if sec_start < 0:
        return 0
    sec_end = section_end(data, sec_start)
    for p, bc in iter_data_blocks(data, sec_start, sec_end):
        if bc >= 16 and bc % 4 == 0:
            total = max(total, bc // 4)
    return total


def _f64_field_blocks(data, section_name: str) -> list[np.ndarray]:
    """Return all float64 payload arrays in a named field section."""
    sec_start = find_section(data, section_name)
    if sec_start < 0:
        return []
    sec_end = section_end(data, sec_start)
    out: list[np.ndarray] = []
    for p, bc in iter_data_blocks(data, sec_start, sec_end):
        if bc >= 8 and bc % 8 == 0:
            out.append(
                np.frombuffer(data, dtype=">f8", count=bc // 8, offset=p)
                .astype(np.float64).copy()
            )
    return out


def _collect_fld_fields(data, n_vertices: int) -> dict[str, np.ndarray]:
    """Extract vertex-centred FLD solution fields (converged from fld_model)."""
    n = n_vertices or 0
    def _blocks(name: str) -> list[np.ndarray]:
        return _f64_field_blocks(data, name)

    temp_blocks = _blocks("Temperature")
    cn01_blocks = _blocks("CN01")
    pres_blocks = _blocks("Pressure")
    vect_blocks = _blocks("VECT")
    hvec_blocks = _blocks("HVEC")

    fields: dict[str, np.ndarray] = {}
    if pres_blocks and pres_blocks[0].size == n:
        fields["PRES"] = pres_blocks[0]
    if temp_blocks:
        if temp_blocks[0].size == n:
            fields["TEMP"] = temp_blocks[0]
            fields["ATMS"] = temp_blocks[0].copy()
        if len(temp_blocks) > 3 and temp_blocks[3].size == n:
            fields["TURK"] = temp_blocks[3]
        if len(temp_blocks) > 6 and temp_blocks[6].size == n:
            fields["TEPS"] = temp_blocks[6]
    if cn01_blocks:
        if cn01_blocks[0].size == n:
            fields["CN01"] = cn01_blocks[0]
        if len(cn01_blocks) > 3 and cn01_blocks[3].size == n:
            fields["HTRC"] = cn01_blocks[3]
        if len(cn01_blocks) > 6 and cn01_blocks[6].size == n:
            fields["SURT"] = cn01_blocks[6]
        if len(cn01_blocks) > 9 and cn01_blocks[9].size == n:
            fields["HTFX"] = cn01_blocks[9]
    if len(vect_blocks) >= 3 and all(a.size == n for a in vect_blocks[:3]):
        fields["VECTX"] = vect_blocks[0]
        fields["VECTY"] = vect_blocks[1]
        fields["VECTZ"] = vect_blocks[2]
    if len(hvec_blocks) >= 3 and all(a.size == n for a in hvec_blocks[:3]):
        fields["HVECX"] = hvec_blocks[0]
        fields["HVECY"] = hvec_blocks[1]
        fields["HVECZ"] = hvec_blocks[2]
    return fields