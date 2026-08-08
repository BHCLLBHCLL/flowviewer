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
)


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
    from .core import f64_be_array
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