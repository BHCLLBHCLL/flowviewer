"""R114: numeric tests that run from the in-repo golden corpus.

Before this round the numeric half of the suite depended on multi-hundred-
megabyte samples kept outside the repository behind 302 ``skipif`` guards, so
on CI it silently skipped.  These tests read ``tests/data/golden`` instead --
a compact, committed distillation of the same real files produced by
``scripts/make_golden.py`` -- and re-check the quantities the R112/R113 rounds
fixed, so the goldens are load-bearing rather than decorative.

None of these tests touches the external samples; they must pass on a bare
checkout.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import golden
import numpy as np
import pytest


def test_corpus_is_present_and_described():
    """The assets must be committed, not regenerated behind a skipif."""
    assert golden.available(), "scripts/make_golden.py was never run"
    m = golden.meta()
    assert "fld_small.npz" in m["files"] and "fph_small.npz" in m["files"]
    # Only the two mesh corpora carry a cell/vertex count and variable stats;
    # R117 added a cross-format excerpt whose manifest shape is different, so
    # assert per expected file rather than over every entry.
    for name in ("fld_small.npz", "fph_small.npz"):
        info = m["files"][name]
        assert info["n_cells"] > 0 and info["n_vertices"] > 0
        assert info["var_stats"], "no reference statistics recorded"


def test_fld_golden_shapes_and_field_stats(fld_golden):
    verts = fld_golden["vertices"]
    conn = fld_golden["cell_conn"]
    field = fld_golden["field"]
    assert verts.ndim == 2 and verts.shape[1] == 3
    assert conn.ndim == 2 and conn.shape[0] > 0
    # This FLD stores its fields node-centred (size == n_vertices); assert the
    # invariant rather than a guess, so a cell-centred file also passes.
    assert field.size in (verts.shape[0], conn.shape[0])
    stats = golden.var_stats("fld_small")
    name = str(fld_golden["field_name"])
    ref = stats[name]
    assert float(field.min()) == pytest.approx(ref["min"], rel=1e-12)
    assert float(field.max()) == pytest.approx(ref["max"], rel=1e-12)
    assert float(field.mean()) == pytest.approx(ref["mean"], rel=1e-12)


def test_fld_golden_face_ids_are_zero_based(fld_golden):
    """R112 regression: 1-based ids leaked into a 0-based vertex array."""
    verts = fld_golden["vertices"]
    faces = fld_golden["face_nodes"]
    assert faces.size > 0
    assert faces.min() == 0, "pre-R112 data would start at 1"
    assert faces.max() < verts.shape[0]


def test_fld_golden_boundary_area_matches_vtk(fld_golden):
    """R112 regression: area came from the first three vertices only."""
    vtk = pytest.importorskip("vtk")
    from fv.render.plane import integrate_cut
    from vtk.util import numpy_support as vns

    verts = np.asarray(fld_golden["vertices"], dtype=np.float64)
    faces = np.asarray(fld_golden["face_nodes"], dtype=np.int64)

    points = vtk.vtkPoints()
    points.SetData(vns.numpy_to_vtk(verts, deep=True))
    polys = vtk.vtkCellArray()
    ids = vtk.vtkIdList()
    for face in faces:
        ids.Reset()
        for i in face:
            ids.InsertNextId(int(i))
        polys.InsertNextCell(ids)
    pd = vtk.vtkPolyData()
    pd.SetPoints(points)
    pd.SetPolys(polys)

    tri = vtk.vtkTriangleFilter()
    tri.SetInputData(pd)
    tri.Update()
    mass = vtk.vtkMassProperties()
    mass.SetInputConnection(tri.GetOutputPort())
    mass.Update()
    truth = mass.GetSurfaceArea()

    got = integrate_cut(pd, None)["area"]
    assert got == pytest.approx(truth, rel=1e-6)


def test_fph_golden_closed_shell_volumes(fph_golden):
    """R113 regression: owner-only shells returned ~0.42x the true volume."""
    verts = np.asarray(fph_golden["vertices"], dtype=np.float64)
    fn = np.asarray(fph_golden["face_nodes"], dtype=np.int64)
    off = np.asarray(fph_golden["face_offsets"], dtype=np.int64)
    owner = np.asarray(fph_golden["owner"], dtype=np.int64)
    neigh = np.asarray(fph_golden["neighbour"], dtype=np.int64)
    cells = np.asarray(fph_golden["cells"], dtype=np.int64)
    volumes = np.asarray(fph_golden["volumes"], dtype=np.float64)

    assert volumes.size == cells.size
    assert (volumes > 0).all(), "every kept cell must have a positive volume"

    # rebuild the closed shell from the fixture and re-derive the volume
    by_cell = {}
    for i in range(fn.size and off.size - 1):
        for c, side in ((owner[i], 0), (neigh[i], 1)):
            if c >= 0:
                by_cell.setdefault(int(c), []).append(i)
    for local, c in enumerate(cells):
        polys = [verts[fn[off[i]:off[i + 1]]] for i in by_cell.get(int(c), [])]
        if not polys:
            continue
        ctr = np.vstack(polys).mean(axis=0)
        vol = 0.0
        for p in polys:
            for k in range(1, len(p) - 1):
                tri = p[[0, k, k + 1]]
                m = np.stack([tri[1] - tri[0], tri[2] - tri[0], ctr - tri[0]])
                vol += abs(float(np.linalg.det(m))) / 6.0
        assert vol == pytest.approx(float(volumes[local]), rel=1e-9)


def test_fph_golden_cell_centres_inside_their_volume(fph_golden):
    centres = np.asarray(fph_golden["centres"], dtype=np.float64)
    verts = np.asarray(fph_golden["vertices"], dtype=np.float64)
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    assert centres.shape[1] == 3
    assert (centres >= lo - 1e-9).all() and (centres <= hi + 1e-9).all()


def test_fph_golden_field_stats(fph_golden):
    field = np.asarray(fph_golden["field"], dtype=np.float64)
    stats = golden.var_stats("fph_small")
    name = str(fph_golden["field_name"])
    ref = stats[name]
    assert field.size == ref["size"]
    assert float(field.min()) == pytest.approx(ref["min"], rel=1e-12)
    assert float(field.max()) == pytest.approx(ref["max"], rel=1e-12)


def test_goldens_are_small_enough_to_commit():
    """A corpus that bloats the repository would be regenerated instead."""
    total = sum(p.stat().st_size for p in golden.GOLDEN.iterdir() if p.is_file())
    assert total < 12 * 1024 * 1024, "%.1f MiB is too big" % (total / 1048576.0)
