"""R124 - CGNS from real (polyhedral) Cradle exports.

Two measured defects drove this round.  tr03_9_orig.cgns and
exPRE04-1_37.cgns are entirely polyhedral (NGON_n faces + NFACE_n cells): the
reader had no entry for type codes 22/23, so both opened with ZERO cells while
still reporting every node, and both grew a bogus "GridLocation" variable read
out of the SIDS bookkeeping node beside the real data arrays.

The same files also revealed that a Cradle export writes one zone per named
volume region, with the region zones repeated under part and FPHPARTS.* names:
in tr03_9_orig.cgns, FluidRegion (221786 nodes / 63697 cells) is the exact
disjoint union of Rotate_MovingVolumeRegion (44842 cells) and Case[2] (18855
cells), and Rotate_Moving, Rotate[2] and FPHPARTS.Rotate are bit-identical
copies of the first; the FPH written from the same run holds exactly the 63697
cells of FluidRegion.  Reading every zone therefore double counted the mesh
(127396 cells), so a zone whose cells are all present in another zone is now
dropped and the decision is reported.  The tests below pin the decoder on
synthetic files with hand-computable geometry, and check the real files
against the FPH numbers when the samples are on this machine.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

h5py = pytest.importorskip("h5py")

from fv.crdl.cgns import _location_of, read_cgns  # noqa: E402

#: Real Cradle samples used by the acceptance tests (skipped when absent).
TR03 = Path(r"D:\training\cgns\examples\tr03_9_orig.cgns")
EXPRE = Path(r"D:\training\cgns\examples\exPRE04-1_37.cgns")

#: Measured from the same-source .fph files (see the module docstring).
TR03_FPH_NV, TR03_FPH_NC, TR03_FPH_NF = 221786, 63697, 323827
EXPRE_FPH_NV, EXPRE_FPH_NC, EXPRE_FPH_NF = 585872, 531434, 1649182

#: The variables the same-source FPH files expose.
TR03_FPH_VARS = ["EVIS", "LNAM_RV001X", "LNAM_RV001Y", "LNAM_RV001Z", "PRES",
                 "TEPS", "TPRS", "TURK", "VELX", "VELY", "VELZ"]
EXPRE_FPH_VARS = ["ENTL", "EVIS", "PRES", "TEMP", "TEPS", "TPRS", "TURK",
                  "VELX", "VELY", "VELZ"]


# ---------------------------------------------------------------------------
# synthetic CGNS writers
# ---------------------------------------------------------------------------

def _node(parent, name, data):
    """A CGNS node: a group holding a ' data' dataset."""
    g = parent.create_group(name)
    if isinstance(data, bytes):
        data = np.frombuffer(data, dtype="S1")
    g.create_dataset(" data", data=np.asarray(data))
    return g


def _cube(offset):
    return np.array([[x + offset, y, z]
                     for z in (0.0, 1.0) for y in (0.0, 1.0)
                     for x in (0.0, 1.0)])


def _write_coords(zone, coords):
    gc = zone.create_group("GridCoordinates")
    for ax, col in zip(("CoordinateX", "CoordinateY", "CoordinateZ"),
                       range(3)):
        _node(gc, ax, coords[:, col])


#: Two unit cubes sharing the face at x=1 (cube B is cube A shifted by +1 in
#: x).  Node order is the z-major order of _cube: cube A is 0..7, B is 8..15.
_TWO_CUBE_NODES = np.vstack([_cube(0.0), _cube(1.0)])
_SHARED_FACE = (1, 3, 7, 5)          # A's x=1 face, in A's node numbering
_TWO_CUBE_FACES = [
    (0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (1, 3, 7, 5), (2, 3, 7, 6),
    (0, 2, 6, 4),                                     # cube A, faces 1..6
    (8, 9, 11, 10), (12, 13, 15, 14), (8, 9, 13, 12), (9, 11, 15, 13),
    (10, 11, 15, 14),
]                                                     # cube B, 5 own faces
#: Cell 1 lists face 4 (the shared face) negatively: the stored order points
#: into cell 1, so cell 0 owns it and cell 1 is its neighbour.
_TWO_CUBE_CELLS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, -4]
_TWO_CUBE_OFFSETS = np.array([0, 6, 12])


def _write_poly_zone(zone, coords, faces, cells, cell_offsets, fields=None,
                     bcs=None, face_base=1):
    """A polyhedral zone: NGON_n faces + NFACE_n cells (R124)."""
    _write_coords(zone, coords)
    flat = np.array([n + 1 for f in faces for n in f], dtype=np.int64)
    off = np.zeros(len(faces) + 1, dtype=np.int64)
    np.cumsum([len(f) for f in faces], out=off[1:])
    fsec = zone.create_group("GridElements_Faces")
    # the element type code lives in a bare " data" dataset (CGNS SIDS)
    fsec.create_dataset(" data", data=np.array([22, 0], dtype=np.int32))
    _node(fsec, "ElementRange",
          np.array([face_base, face_base + len(faces) - 1], dtype=np.int64))
    _node(fsec, "ElementStartOffset", off)
    _node(fsec, "ElementConnectivity", flat)
    csec = zone.create_group("Cells")
    csec.create_dataset(" data", data=np.array([23, 0], dtype=np.int32))
    _node(csec, "ElementRange",
          np.array([1, len(cell_offsets) - 1], dtype=np.int64))
    _node(csec, "ElementStartOffset", np.asarray(cell_offsets))
    _node(csec, "ElementConnectivity", np.asarray(cells, dtype=np.int64))
    if fields:
        fs = zone.create_group("FlowSolution")
        for name, (arr, loc) in fields.items():
            _node(fs, "GridLocation", loc.encode("ascii"))
            _node(fs, name, arr)
    for name, (loc, ids) in (bcs or {}).items():
        zbc = zone.get("ZoneBC")
        if zbc is None:
            zbc = zone.create_group("ZoneBC")
        bc = zbc.create_group(name)
        _node(bc, "GridLocation", loc.encode("ascii"))
        _node(bc, "PointList", np.asarray(ids, dtype=np.int64))


def _two_cube_zone(parent, name, offset=0.0, cells=None, faces=None,
                   coords=None, cell_offsets=None):
    zone = parent.create_group(name)
    _node(zone, "ZoneType", b"Unstructured")
    _write_poly_zone(zone,
                     _TWO_CUBE_NODES + np.array([offset, 0.0, 0.0])
                     if coords is None else coords,
                     _TWO_CUBE_FACES if faces is None else faces,
                     _TWO_CUBE_CELLS if cells is None else cells,
                     _TWO_CUBE_OFFSETS if cell_offsets is None
                     else np.asarray(cell_offsets))
    return zone


def _two_cube_file(path):
    with h5py.File(path, "w") as f:
        _two_cube_zone(f.create_group("Base"), "ZonePoly")
    return str(path)


# ---------------------------------------------------------------------------
# polyhedral decoding
# ---------------------------------------------------------------------------

def test_r124_poly_zone_decodes_faces_cells_and_ownership(tmp_path):
    """NGON_n/NFACE_n decode into a face table with owner/neighbour."""
    mesh = read_cgns(_two_cube_file(tmp_path / "poly.cgns"))
    assert mesh is not None
    assert (mesh["n_vertices"], mesh["n_cells"]) == (16, 2)
    # the file lists 11 face elements and the table keeps that numbering,
    # because ZoneBC PointList ids address exactly those element ids
    assert mesh["n_faces"] == 11
    ld = mesh["link_data"]
    assert ld["n_faces"] == 11
    assert ld["owner"].tolist() == [0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1]
    assert ld["neighbour"].tolist() == [-1, -1, -1, 1, -1, -1, -1, -1, -1,
                                        -1, -1]
    # face 4 (index 3) is the shared face, so only ten faces are boundary
    assert sorted(int(f) for f in ld["boundary_faces"]) == [0, 1, 2, 4, 5, 6, 7,
                                                            8, 9, 10]
    assert ld["cell_owner_faces"][0].tolist() == [0, 1, 2, 3, 4, 5]
    assert ld["cell_owner_faces"][1].tolist() == [6, 7, 8, 9, 10]
    assert ld["cell_neighbour_faces"][1].tolist() == [3]
    # every cell keeps its full face list (owner + neighbour side)
    assert mesh["cell_conn"].tolist() == [[0, 1, 2, 3, 4, 5],
                                          [6, 7, 8, 9, 10, 3]]
    assert ld["npe"].tolist() == [4] * 11
    assert set(mesh["cell_types"].tolist()) == {42}      # VTK_POLYHEDRON


def test_r124_poly_cell_centres_match_the_analytic_cubes(tmp_path):
    """The face table describes the same geometry the coordinates do."""
    from fv.crdl.cgns import _cell_centres, _decode_zone, _zone_type
    path = _two_cube_file(tmp_path / "poly.cgns")
    with h5py.File(path, "r") as f:
        zone = f["Base"]["ZonePoly"]
        rec = _decode_zone(zone, _zone_type(zone))
    assert (rec["n_v"], rec["n_c"]) == (16, 2)
    assert rec["poly"] is not None
    centres, ok = _cell_centres(rec)
    assert ok.tolist() == [True, True]
    # cube A spans (0..1)^3, cube B (1..2) x (0..1)^2
    assert np.allclose(centres, [[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]], atol=1e-12)


def test_r124_mixed_zone_cell_centres_ignore_row_padding():
    """A ragged MIXED row must not fold its -1 padding into the centre."""
    from fv.crdl.cgns import _cell_centres
    # a tetra in an 8-wide MIXED row: the -1 tail would add node 0 four times
    conn = np.array([[0, 1, 2, 3, -1, -1, -1, -1]], dtype=np.int64)
    verts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
                      [0.0, 0.0, 1.0]])
    rec = {"n_c": 1, "verts": verts, "conn": conn, "poly": None}
    centres, ok = _cell_centres(rec)
    assert ok.tolist() == [True]
    assert np.allclose(centres[0], [0.25, 0.25, 0.25], atol=1e-15)


def test_r124_face_node_table_has_the_file_node_lists(tmp_path):
    """Face node lists survive decoding in the order the file stores them."""
    mesh = read_cgns(_two_cube_file(tmp_path / "poly.cgns"))
    ld = mesh["link_data"]
    fo = np.asarray(ld["face_offsets"])
    fn = np.asarray(ld["face_nodes"])
    assert int(fo[-1]) == 4 * 11          # every face here has four nodes
    assert fo[3:5].tolist() == [12, 16]
    # node ids are decoded to 0-based, so face 4 reads back as stored
    assert fn[12:16].tolist() == list(_SHARED_FACE)


def test_r124_poly_zone_builds_a_cuttable_ugrid(tmp_path):
    """A polyhedral CGNS must produce a grid a plane can cut."""
    vtk = pytest.importorskip("vtk")
    from fv.model.dataset import cgns_load
    from fv.render.plane import build_ugrid
    ff = cgns_load(_two_cube_file(tmp_path / "poly.cgns"))
    assert ff.poly is True
    ug, cell_centered = build_ugrid(ff)
    assert ug.GetNumberOfCells() == 2 and cell_centered is True
    cutter = vtk.vtkCutter()
    cutter.SetInputData(ug)
    plane = vtk.vtkPlane()
    plane.SetOrigin(1.0, 0.5, 0.5)
    plane.SetNormal(1.0, 0.0, 0.0)
    cutter.SetCutFunction(plane)
    cutter.Update()
    assert cutter.GetOutput().GetNumberOfCells() >= 1


# ---------------------------------------------------------------------------
# FlowSolution fidelity
# ---------------------------------------------------------------------------

def test_r124_gridlocation_is_not_offered_as_a_variable(tmp_path):
    """SIDS bookkeeping nodes must not appear in the variable list."""
    path = tmp_path / "field.cgns"
    with h5py.File(path, "w") as f:
        base = f.create_group("Base")
        zone = _two_cube_zone(base, "ZonePoly")
        fs = zone.create_group("FlowSolution")
        _node(fs, "GridLocation", b"CellCenter")
        _node(fs, "PRES", np.array([1.0, 2.0]))
        _node(fs, "Descriptor", b"Pressure")
    mesh = read_cgns(str(path))
    assert "GridLocation" not in mesh["fields"]
    assert "Descriptor" not in mesh["fields"]
    arr, loc = mesh["fields"]["PRES"]
    assert loc == "cell" and arr.tolist() == [1.0, 2.0]


def test_r124_location_of_prefers_gridlocation_over_array_length():
    """A cell field must stay cell data when nodes == cells in a zone."""
    # the old code compared the array length with the node count only, so a
    # CellCenter field of a zone with as many cells as nodes became node data
    assert _location_of("CellCenter", 4, 4, 4) == "cell"
    assert _location_of("Vertex", 4, 4, 4) == "node"
    assert _location_of("IFaceCenter", 4, 4, 4) == ""
    # no GridLocation: fall back to the length
    assert _location_of("", 4, 4, 2) == "node"
    assert _location_of("", 4, 8, 4) == "cell"
    assert _location_of("", 3, 8, 4) == ""


def test_r124_mismatched_field_is_reported_not_silently_attached(tmp_path):
    """A field whose length matches neither side is skipped and recorded."""
    path = tmp_path / "bad.cgns"
    with h5py.File(path, "w") as f:
        zone = _two_cube_zone(f.create_group("Base"), "ZonePoly")
        fs = zone.create_group("FlowSolution")
        _node(fs, "GridLocation", b"Vertex")
        _node(fs, "JUNK", np.arange(5.0))
    mesh = read_cgns(str(path))
    assert "JUNK" not in mesh["fields"]
    assert any(name == "JUNK" for name, _why in mesh["skipped_fields"])
    # and it must not leak into the variable list as a pre-merged key
    from fv.model.dataset import cgns_load
    ff = cgns_load(str(path))
    assert list(ff.variables) == []
    assert any(name == "JUNK" for name, _why in ff.meta["skipped_fields"])


def test_r124_unreadable_field_is_reported(tmp_path):
    """A field dataset numpy cannot turn into floats is skipped, not fatal."""
    path = tmp_path / "text.cgns"
    with h5py.File(path, "w") as f:
        zone = _two_cube_zone(f.create_group("Base"), "ZonePoly")
        fs = zone.create_group("FlowSolution")
        _node(fs, "GridLocation", b"CellCenter")
        _node(fs, "BROKEN", np.array([b"not-a-number"]))
        _node(fs, "PRES", np.array([7.0, 8.0]))
    mesh = read_cgns(str(path))
    assert sorted(mesh["fields"]) == ["PRES"]
    assert any(name == "BROKEN" for name, _why in mesh["skipped_fields"])
    from fv.model.dataset import cgns_load
    assert list(cgns_load(str(path)).variables) == ["PRES"]


# ---------------------------------------------------------------------------
# bases, zones and boundary conditions
# ---------------------------------------------------------------------------

def test_r124_every_base_is_read(tmp_path):
    """Zones from all bases are merged, not just the first base."""
    path = tmp_path / "bases.cgns"
    with h5py.File(path, "w") as f:
        for bname, off in (("BaseA", 0.0), ("BaseB", 10.0)):
            zone = f.create_group(bname).create_group("Zone" + bname[-1])
            _write_coords(zone, _cube(off))
            el = zone.create_group("Elements")
            el.create_dataset(" data", data=np.array([17], dtype=np.int32))
            _node(el, "ElementRange", np.array([1, 1], dtype=np.int64))
            _node(el, "ElementConnectivity", np.arange(1, 9, dtype=np.int64))
    mesh = read_cgns(str(path))
    assert (mesh["n_vertices"], mesh["n_cells"]) == (16, 2)
    assert mesh["base_names"] == ["BaseA", "BaseB"]
    assert mesh["volume_regions"] == ["ZoneA", "ZoneB"]


def test_r124_zone_bc_face_ids_are_rebased_on_the_face_range(tmp_path):
    """BC ids address the zone face elements, whatever their first id is."""
    path = tmp_path / "bc.cgns"
    with h5py.File(path, "w") as f:
        zone = f.create_group("Base").create_group("ZonePoly")
        _node(zone, "ZoneType", b"Unstructured")
        # the cell face references use the same element numbering as the
        # face section, which starts at 101 here
        refs = [c + 100 if c > 0 else c - 100 for c in _TWO_CUBE_CELLS]
        _write_poly_zone(zone, _TWO_CUBE_NODES, _TWO_CUBE_FACES, refs,
                         _TWO_CUBE_OFFSETS, face_base=101,
                         bcs={"walls": ("FaceCenter", [101, 102, 104])})
    mesh = read_cgns(str(path))
    assert mesh["n_faces"] == 11
    regions = dict(mesh["surface_regions"])
    assert regions["walls"].tolist() == [0, 1, 3]


def test_r124_vertex_bcs_are_reported_not_indexed_as_faces(tmp_path):
    """A node-based ZoneBC cannot become a face region; say so."""
    path = tmp_path / "vbc.cgns"
    with h5py.File(path, "w") as f:
        zone = f.create_group("Base").create_group("ZonePoly")
        _node(zone, "ZoneType", b"Unstructured")
        _write_poly_zone(zone, _TWO_CUBE_NODES, _TWO_CUBE_FACES, _TWO_CUBE_CELLS,
                         _TWO_CUBE_OFFSETS,
                         bcs={"inlet": ("Vertex", [1, 2, 3, 4])})
    mesh = read_cgns(str(path))
    assert mesh["surface_regions"] == []
    assert mesh["vertex_bcs"] == [("inlet", "Vertex")]


# ---------------------------------------------------------------------------
# duplicate / nested zone selection
# ---------------------------------------------------------------------------

def test_r124_duplicated_zone_is_dropped_and_reported(tmp_path):
    """Zones whose cells are all present elsewhere must not double count."""
    path = tmp_path / "dup.cgns"
    with h5py.File(path, "w") as f:
        base = f.create_group("Base")
        _two_cube_zone(base, "FluidRegion")
        # cube A again under a part name ...
        _two_cube_zone(base, "FPHPARTS.A", coords=_TWO_CUBE_NODES[:8],
                       faces=_TWO_CUBE_FACES[:6], cells=[1, 2, 3, 4, 5, 6],
                       cell_offsets=[0, 6])
        # ... and a copy of the whole mesh far away, which must survive
        _two_cube_zone(base, "FarZone", offset=10.0)
    mesh = read_cgns(str(path))
    # zones are read in HDF5 name order, so FarZone comes before FluidRegion
    assert mesh["volume_regions"] == ["FarZone", "FluidRegion"]
    assert mesh["n_cells"] == 4                     # 2 kept zones, 2 cells each
    assert mesh["n_vertices"] == 32
    dropped = mesh["dropped_zones"]
    assert len(dropped) == 1
    name, why, n_c = dropped[0]
    assert name == "FPHPARTS.A" and n_c == 1
    assert "FluidRegion" in why
    assert mesh["zone_selection"]
    # part ids follow the kept zones: FarZone 1, FluidRegion 2
    assert mesh["material"].tolist() == [1, 1, 2, 2]


def test_r124_overset_zone_inside_a_coarse_cell_is_kept(tmp_path):
    """A zone that merely sits inside another zone is not a duplicate."""
    path = tmp_path / "overset.cgns"
    fine = np.array([[0.0, 0.0, 0.0], [0.5, 0.0, 0.0], [0.0, 0.5, 0.0],
                     [0.0, 0.0, 0.5]])
    with h5py.File(path, "w") as f:
        base = f.create_group("Base")
        _two_cube_zone(base, "Coarse")
        zone = base.create_group("Fine")
        _node(zone, "ZoneType", b"Unstructured")
        _write_poly_zone(zone, fine, [(0, 2, 1), (0, 1, 3), (1, 2, 3),
                                      (0, 3, 2)], [1, 2, 3, 4],
                         np.array([0, 4]))
    mesh = read_cgns(str(path))
    assert mesh["volume_regions"] == ["Coarse", "Fine"]
    assert mesh["n_cells"] == 3
    assert mesh["dropped_zones"] == []


def test_r124_volume_region_filter_selects_zone_cells(tmp_path):
    """display_volume_regions picks the cells of the named zone (R124)."""
    path = tmp_path / "regions.cgns"
    with h5py.File(path, "w") as f:
        base = f.create_group("Base")
        _two_cube_zone(base, "Zone0")
        _two_cube_zone(base, "Zone1", offset=10.0)
    from fv.model.dataset import cgns_load
    from fv.render.plane import cell_filter_mask

    class Obj:
        display_mats = []
        display_volume_regions = ["Zone1"]

    ff = cgns_load(str(path))
    assert ff.volume_regions == ["Zone0", "Zone1"]
    mask = cell_filter_mask(ff, Obj())
    assert mask.tolist() == [False, False, True, True]


# ---------------------------------------------------------------------------
# real Cradle samples (acceptance)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not TR03.exists(), reason="tr03_9_orig.cgns not present")
def test_r124_real_tr03_matches_the_fph_mesh():
    """The real polyhedral file decodes to exactly the FPH mesh."""
    from fv.model.dataset import cgns_load
    from fv.render.plane import build_ugrid
    ff = cgns_load(str(TR03))
    assert (ff.n_vertices, ff.n_cells) == (TR03_FPH_NV, TR03_FPH_NC)
    assert ff.link_data["n_faces"] == TR03_FPH_NF
    assert ff.volume_regions == ["FluidRegion"]
    assert sorted(name for name, _why, _n in ff.meta["dropped_zones"]) == [
        "Case[2]", "FPHPARTS.Rotate", "FPHPARTS.tr03.Case", "Rotate[2]",
        "Rotate_Moving", "Rotate_MovingVolumeRegion"]
    assert sorted(ff.variables) == TR03_FPH_VARS
    assert all(v.location == "cell" for v in ff.variables.values())
    ug, cell_centered = build_ugrid(ff)
    assert cell_centered is True
    assert ug.GetNumberOfCells() == TR03_FPH_NC


@pytest.mark.skipif(not EXPRE.exists(), reason="exPRE04-1_37.cgns not present")
def test_r124_real_expre_matches_the_fph_mesh():
    """Six Cradle zones collapse to the one the FPH actually contains."""
    from fv.model.dataset import cgns_load
    ff = cgns_load(str(EXPRE))
    assert (ff.n_vertices, ff.n_cells) == (EXPRE_FPH_NV, EXPRE_FPH_NC)
    assert ff.link_data["n_faces"] == EXPRE_FPH_NF
    assert ff.volume_regions == ["FluidRegion"]
    assert len(ff.meta["dropped_zones"]) == 5
    assert sorted(ff.variables) == EXPRE_FPH_VARS
    assert all(v.location == "cell" for v in ff.variables.values())
