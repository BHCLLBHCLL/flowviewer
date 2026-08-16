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


POLY_KINDS = ("fph", "gph", "pph")   # polyhedral LS_Links topology kinds


@dataclass
class FieldFile:
    """Parsed mesh + variables + regions ready for the renderer.

    FPH/GPH: polyhedral LS_Links topology, cell-centred variables.
    FLD: hex8 LS_Elements connectivity, vertex-centred variables.
    """

    path: str
    @property
    def poly(self) -> bool:
        """True for polyhedral (LS_Links) topology: fph / gph / pph."""
        return self.kind in POLY_KINDS
    kind: str = "fph"            # 'fph' | 'fld'
    vertices: Optional[np.ndarray] = None
    n_vertices: int = 0
    n_cells: int = 0
    link_data: Optional[dict] = None      # FPH/GPH topology
    cell_conn: Optional[np.ndarray] = None  # FLD (n_cells, 8)
    cell_types: Optional[np.ndarray] = None  # CGNS per-cell vtk type codes
    material: Optional[np.ndarray] = None
    faces: list = field(default_factory=list)
    bc_plan: list = field(default_factory=list)
    surface_regions: list = field(default_factory=list)
    volume_regions: list = field(default_factory=list)
    parts: list = field(default_factory=list)
    cvol_id: Optional[np.ndarray] = None
    parts_with_cvol: list = field(default_factory=list)
    variables: dict = field(default_factory=dict)
    file_size: int = 0
    cycle: Optional[int] = None
    time: Optional[float] = None
    has_particles: bool = False
    _particle_vars: Optional[list] = field(default=None, repr=False)
    pph_project: Optional[str] = None      # PPH main.xml project name
    pph_members: list = field(default_factory=list)  # PPH zip member list
    meta: dict = field(default_factory=dict)  # header metadata (GPH/FPH/FLD)
    element_flags: Optional[np.ndarray] = None  # Element_InformationFlag

    @property
    def particle_vars(self) -> list:
        """Particle variable names (e.g. VELP), parsed lazily (P0.4)."""
        if self._particle_vars is None:
            self._particle_vars = []
            if self.has_particles:
                try:
                    from ..crdl.fields import parse_particle_variables
                    with open(self.path, "rb") as fh:
                        self._particle_vars = sorted(
                            parse_particle_variables(fh.read()))
                except Exception:  # pragma: no cover - best effort
                    pass
        return self._particle_vars

    # ── helpers ────────────────────────────────────────────────────────────

    def boundary_regions(self) -> list[Region]:
        """Boundary surface regions → (name, face_ids)."""
        if self.poly:
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



def cgns_load(filepath: str) -> FieldFile:
    """CGNS-HDF5 loader (P1.2): mesh + fields -> FieldFile(kind='cgns')."""
    from ..crdl.cgns import read_cgns
    path = Path(filepath)
    mesh = read_cgns(str(path))
    if mesh is None:
        raise ValueError(f"not a readable CGNS-HDF5 file: {filepath}")
    ff = FieldFile(path=str(path), kind="cgns")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.cell_conn = mesh["cell_conn"]
    ff.cell_types = mesh["cell_types"]
    ff.n_cells = mesh["n_cells"]
    ff.surface_regions = mesh["surface_regions"]
    ff.volume_regions = mesh["volume_regions"]
    ff.file_size = mesh["vertices"].nbytes
    for name, (arr, loc) in mesh["fields"].items():
        ff.variables[name] = VarInfo(
            name=name,
            kind=FIELD_KIND_SCALAR,
            location=loc,
            array=np.asarray(arr, dtype=np.float64),
        )
    return ff


def xdmf_load(filepath: str) -> FieldFile:
    """XDMF loader (D1): XML mesh + fields -> FieldFile(kind='xdmf')."""
    from ..crdl.xdmf import parse_xdmf
    path = Path(filepath)
    mesh = parse_xdmf(str(path))
    if mesh is None:
        raise ValueError(f"not a readable XDMF file: {filepath}")
    ff = FieldFile(path=str(path), kind="xdmf")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.cell_conn = mesh["cell_conn"]
    ff.cell_types = mesh["cell_types"]
    ff.n_cells = mesh["n_cells"]
    ff.surface_regions = mesh["surface_regions"]
    ff.volume_regions = mesh["volume_regions"]
    ff.file_size = mesh["vertices"].nbytes
    for name, (arr, loc) in mesh["fields"].items():
        ff.variables[name] = VarInfo(
            name=name, kind=FIELD_KIND_SCALAR, location=loc,
            array=np.asarray(arr, dtype=np.float64),
        )
    return ff


def nastran_load(filepath: str) -> FieldFile:
    """Nastran free-field mesh loader (D2)."""
    from ..crdl.nastran import parse_nastran
    path = Path(filepath)
    mesh = parse_nastran(str(path))
    if mesh is None:
        raise ValueError(f"not a readable Nastran mesh: {filepath}")
    ff = FieldFile(path=str(path), kind="nastran")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.cell_conn = mesh["cell_conn"]
    ff.cell_types = mesh["cell_types"]
    ff.n_cells = mesh["n_cells"]
    ff.volume_regions = mesh["volume_regions"]
    ff.file_size = mesh["vertices"].nbytes
    return ff


def neutral_load(filepath: str) -> FieldFile:
    """Neutral geometry loader (OBJ/STL/PLY) (1, 7)."""
    from ..crdl.neutral import parse_obj, parse_stl, parse_ply
    path = Path(filepath)
    suf = path.suffix.lower()
    if suf == ".ply":
        mesh = parse_ply(str(path))
    elif suf == ".obj":
        mesh = parse_obj(str(path))
    else:
        mesh = parse_stl(str(path))
    if mesh is None:
        raise ValueError("not a readable neutral mesh: " + filepath)
    ff = FieldFile(path=str(path), kind="neutral")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.faces = mesh["faces"]
    ff.surface_regions = [("Neutral", np.arange(mesh["n_faces"], dtype=np.int64))]
    ff.file_size = mesh["vertices"].nbytes
    for name, (arr, loc) in (mesh.get("fields") or {}).items():
        ff.variables[name] = VarInfo(
            name=name, kind=FIELD_KIND_SCALAR, location=loc,
            array=np.asarray(arr, dtype=np.float64),
        )
    return ff


def marc_load(filepath: str) -> FieldFile:
    """Marc/Mentat .dat mesh loader + optional node results sidecar (3, 7)."""
    from ..crdl.marc import parse_marc, parse_marc_results
    path = Path(filepath)
    mesh = parse_marc(str(path))
    if mesh is None:
        raise ValueError("not a readable Marc .dat mesh: " + filepath)
    ff = FieldFile(path=str(path), kind="marc")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.cell_conn = mesh["cell_conn"]
    ff.cell_types = mesh["cell_types"]
    ff.n_cells = mesh["n_cells"]
    ff.volume_regions = mesh["volume_regions"]
    ff.file_size = mesh["vertices"].nbytes
    # optional ASCII node results sidecar (same stem, .res/.csv)
    for suf in (".res", ".csv"):
        side = path.with_suffix(suf)
        if side.exists():
            fields = parse_marc_results(
                str(side), mesh["node_order"], mesh["n_vertices"])
            for name, (arr, loc) in fields.items():
                ff.variables[name] = VarInfo(
                    name=name, kind=FIELD_KIND_SCALAR, location=loc,
                    array=np.asarray(arr, dtype=np.float64),
                )
            break
    return ff

def pph_load(filepath: str) -> FieldFile:
    """PPH (scFLOW project ZIP) loader: embedded volume mesh -> FieldFile."""
    from ..crdl.pph import parse_pph
    path = Path(filepath)
    mesh = parse_pph(str(path))
    ff = FieldFile(path=str(path), kind="pph")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.n_cells = mesh["n_cells"]
    ff.link_data = mesh["link_data"]
    ff.surface_regions = mesh["surface_regions"]
    ff.volume_regions = mesh["volume_regions"]
    ff.parts = mesh["parts"]
    ff.cvol_id = mesh.get("cvol_id")
    ff.parts_with_cvol = mesh.get("parts_with_cvol") or []
    ff.file_size = mesh["file_size"]
    ff.pph_project = mesh.get("pph_project")
    ff.pph_members = mesh.get("pph_members") or []
    ff.meta = mesh.get("meta") or {}
    ff.element_flags = mesh.get("element_flags")
    ff.element_centers = mesh.get("element_centers")
    return ff


def ifld_load(filepath: str, bounds=None) -> FieldFile:
    """iFLD loader: quick metadata scan (D3) + full FLD parse.

    With ``bounds`` = ``(xmin, xmax, ymin, ymax, zmin, zmax)`` the
    parsed mesh is spatially trimmed before the FieldFile is built
    (scPOST Trimming Open, P2.6): only vertices inside the box and the
    cells/faces they fully own are kept, re-indexed, with per-node
    fields sliced to match (``ff.meta["ifld_trim"]`` records the kept
    counts).  The full-file scan summary stays attached as
    ``ff.meta["ifld_scan"]`` for fast previews.
    """
    from ..crdl.ifld import scan_ifld, trim_fld_mesh
    path = Path(filepath)
    mesh = mesh_fld.parse_fld(str(path))
    if not mesh["n_vertices"] and not mesh["n_cells"]:
        mesh = _inherit_mesh_from_sibling(mesh, path)
    if bounds is not None:
        mesh = trim_fld_mesh(mesh, bounds)
    ff = _ff_from_fld_mesh(mesh, path)
    _fld_cycle_meta(str(path), ff)
    summary = scan_ifld(str(path))
    if summary:
        ff.meta["ifld_scan"] = summary
    return ff
def _register_loaders() -> None:
    """Advertise the real parsers in :mod:`fv.model.loaders` registry."""
    try:
        from . import loaders
        loaders.register("fld", fld_only_load)
        loaders.register("ifld", ifld_load)
        loaders.register("fph", load_file)
        loaders.register("gph", load_file)
        loaders.register("pph", pph_load)
        loaders.register("cgns", cgns_load)
        loaders.register("emt", load_file)  # EMT: fph-family binary
        loaders.register("xmf", xdmf_load)
        loaders.register("xdmf", xdmf_load)
        loaders.register("nas", nastran_load)
        loaders.register("bdf", nastran_load)
        loaders.register("obj", neutral_load)
        loaders.register("stl", neutral_load)
        loaders.register("neu", neutral_load)
        loaders.register("ply", neutral_load)
        loaders.register("dat", marc_load)
    except Exception:  # pragma: no cover - registry is best-effort
        pass


def _inherit_mesh_from_sibling(mesh: dict, path: Path) -> dict:
    """Result-only FLD: inherit the mesh from a same-stem sibling file.

    scSTREAM-style series store the grid in one file and only the result
    fields in later cycle files (LS_MatOfElements/LS_Elements/LS_Nodes are
    absent).  This copies the mesh sections from the first sibling that has
    them, keeping the current file's fields.
    """
    prefix, num = path.stem, None
    m = None
    for i in range(len(prefix) - 1, -1, -1):
        if not prefix[i].isdigit():
            break
        num = prefix[i:]
        m = i
    base = prefix[:m] if m is not None else prefix
    try:
        cands = sorted(path.parent.glob(base + "*" + path.suffix))
    except Exception:
        cands = []
    for cand in cands:
        if str(cand.resolve()) == str(path.resolve()):
            continue
        try:
            m2 = mesh_fld.parse_fld(str(cand))
        except Exception:
            continue
        if m2.get("n_vertices"):
            for key in ("vertices", "n_vertices", "cell_conn", "material",
                        "n_cells", "faces", "bc_plan", "face_cells",
                        "volume_names"):
                mesh[key] = m2[key]
            mesh["mesh_from"] = str(cand)
            break
    return mesh


def _ff_from_fld_mesh(mesh, path) -> FieldFile:
    """Build the FLD-kind FieldFile from a parse_fld mesh dict."""
    ff = FieldFile(path=str(path), kind="fld")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.cell_conn = mesh["cell_conn"]
    ff.cell_types = mesh.get("cell_types")
    ff.material = mesh["material"]
    ff.n_cells = mesh["n_cells"]
    ff.faces = mesh["faces"]
    ff.bc_plan = mesh["bc_plan"]
    ff.face_cells = mesh.get("face_cells")
    ff.volume_regions = mesh["volume_names"]
    ff.file_size = mesh["file_size"]
    ff.meta = mesh.get("meta") or {}
    if mesh.get("mesh_from"):
        ff.mesh_from = mesh["mesh_from"]
    for name, arr in mesh["fields"].items():
        ff.variables[name] = VarInfo(
            name=name,
            kind=_field_kind(name),
            location="node",
            array=arr,
        )
    return ff


def _fld_cycle_meta(filepath: str, ff: FieldFile) -> None:
    """Fill cycle/time/particle flags from the file (filename fallback)."""
    with open_buffer(str(filepath)) as data:
        ff.cycle, ff.time = fld_fields.parse_cycle_meta(data)
        ff.has_particles = fld_fields.has_particle_results(data)
    if ff.cycle is None:
        ff.cycle = _cycle_from_filename(Path(filepath))


def fld_only_load(filepath: str) -> FieldFile:
    """Direct FLD loader (no magic detection), mirror of the 'fld' branch."""
    path = Path(filepath)
    mesh = mesh_fld.parse_fld(str(path))
    if not mesh["n_vertices"] and not mesh["n_cells"]:
        mesh = _inherit_mesh_from_sibling(mesh, path)
    ff = _ff_from_fld_mesh(mesh, path)
    _fld_cycle_meta(str(path), ff)
    return ff


def load_file(filepath: str) -> FieldFile:
    """Detect GPH/FPH vs FLD by section layout and parse into a FieldFile."""
    path = Path(filepath)
    is_fld = _looks_like_fld(str(path))

    if is_fld or path.suffix.lower() == ".fld":
        return fld_only_load(str(path))

    mesh = mesh_gph.parse_gph_mesh(str(path))
    ff = FieldFile(path=str(path), kind="gph" if path.suffix.lower() == ".gph" else "fph")
    ff.vertices = mesh["vertices"]
    ff.n_vertices = mesh["n_vertices"]
    ff.n_cells = mesh["n_cells"]
    ff.link_data = mesh["link_data"]
    ff.surface_regions = mesh["surface_regions"]
    ff.volume_regions = mesh["volume_regions"]
    ff.parts = mesh["parts"]
    ff.cvol_id = mesh.get("cvol_id")
    ff.parts_with_cvol = mesh.get("parts_with_cvol") or []
    ff.file_size = mesh["file_size"]
    ff.meta = mesh.get("meta") or {}
    ff.element_flags = mesh.get("element_flags")
    ff.element_centers = mesh.get("element_centers")

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


_register_loaders()