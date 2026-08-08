"""FieldFile: wraps a parsed GPH/FPH/FLD file into a viewable dataset."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from ..crdl import (
    mesh_gph,
    mesh_fld,
    fields as fld_fields,
    open_buffer,
    find_section,
)


FIELD_KIND_SCALAR = "scalar"
FIELD_KIND_VECTOR = "vector"


@dataclass
class VarInfo:
    """One registered variable."""

    name: str
    kind: str = FIELD_KIND_SCALAR
    location: str = "cell"  # 'cell' | 'node' | 'face'
    array: Optional[np.ndarray] = None


@dataclass
class Region:
    name: str
    face_ids: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.int64))


@dataclass
class FieldFile:
    """Parsed mesh + variables + regions ready for the renderer.

    FPH/GPH: polyhedral LS_Links topology, cell-centred variables.
    FLD: hex8 LS_Elements connectivity, vertex-centred variables.
    """

    path: str
    kind: str = "fph"            # 'fph' | 'fld'
    vertices: Optional[np.ndarray] = None
    n_vertices: int = 0
    n_cells: int = 0
    link_data: Optional[dict] = None      # FPH/GPH topology
    cell_conn: Optional[np.ndarray] = None  # FLD (n_cells, 8)
    material: Optional[np.ndarray] = None
    faces: list = field(default_factory=list)
    bc_plan: list = field(default_factory=list)
    surface_regions: list = field(default_factory=list)
    volume_regions: list = field(default_factory=list)
    parts: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    file_size: int = 0
    cycle: Optional[int] = None
    time: Optional[float] = None
    has_particles: bool = False

    # ── helpers ────────────────────────────────────────────────────────────

    def boundary_regions(self) -> list[Region]:
        """Boundary surface regions → (name, face_ids)."""
        if self.kind == "fph":
            return [Region(n, ids) for n, ids in self.surface_regions]
        return [Region(n, np.arange(st, st + cnt, dtype=np.int64))
                for n, st, cnt in self.bc_plan if cnt]

    def variable_names(self) -> list[str]:
        return list(self.variables)

    def variable_array(self, name: str) -> Optional[np.ndarray]:
        vi = self.variables.get(name)
        return vi.array if vi is not None else None


def _looks_like_fld(filepath: str) -> bool:
    with open_buffer(filepath) as data:
        return find_section(data, "LS_Elements") >= 0 or find_section(data, "LS_MatOfElements") >= 0


def load_file(filepath: str) -> FieldFile:
    """Detect GPH/FPH vs FLD by section layout and parse into a FieldFile."""
    path = Path(filepath)
    is_fld = _looks_like_fld(str(path))

    if is_fld or path.suffix.lower() == ".fld":
        mesh = mesh_fld.parse_fld(str(path))
        ff = FieldFile(path=str(path), kind="fld")
        ff.vertices = mesh["vertices"]
        ff.n_vertices = mesh["n_vertices"]
        ff.cell_conn = mesh["cell_conn"]
        ff.material = mesh["material"]
        ff.n_cells = mesh["n_cells"]
        ff.faces = mesh["faces"]
        ff.bc_plan = mesh["bc_plan"]
        ff.volume_regions = mesh["volume_names"]
        ff.file_size = mesh["file_size"]
        for name, arr in mesh["fields"].items():
            ff.variables[name] = VarInfo(
                name=name,
                kind=_field_kind(name),
                location="node",
                array=arr,
            )
        with open_buffer(str(path)) as data:
            ff.cycle, ff.time = fld_fields.parse_cycle_meta(data)
            ff.has_particles = fld_fields.has_particle_results(data)
        if ff.cycle is None:
            ff.cycle = _cycle_from_filename(path)
        return ff

    mesh = mesh_gph.parse_gph_mesh(str(path))
    ff = FieldFile(path=str(path), kind="fph")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.n_cells = mesh["n_cells"]
    ff.link_data = mesh["link_data"]
    ff.surface_regions = mesh["surface_regions"]
    ff.volume_regions = mesh["volume_regions"]
    ff.parts = mesh["parts"]
    ff.file_size = mesh["file_size"]

    with open_buffer(str(path)) as data:
        sph = fld_fields.parse_fph_flow_solution(data, ff.n_cells)
        for name, arr in sph.items():
            ff.variables[name] = VarInfo(
                name=name,
                kind=_field_kind(name),
                location="cell",
                array=arr,
            )
        ff.cycle, ff.time = fld_fields.parse_cycle_meta(data)
        ff.has_particles = fld_fields.has_particle_results(data)
    if ff.cycle is None:
        ff.cycle = _cycle_from_filename(path)
    return ff


def _cycle_from_filename(path: Path) -> Optional[int]:
    """Fallback: ``ex1_100.fld`` / ``tr03_9.fph`` → cycle from trailing digits."""
    import re
    m = re.search(r"_(\d+)$", path.stem)
    if m:
        return int(m.group(1))
    return None


def _field_kind(name: str) -> str:
    if name in ("VELX", "VELY", "VELZ",
                "VECTX", "VECTY", "VECTZ",
                "HVECX", "HVECY", "HVECZ"):
        return FIELD_KIND_VECTOR
    return FIELD_KIND_SCALAR