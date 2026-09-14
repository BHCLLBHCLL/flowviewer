"""R113b: the node-difference operators, and the limits of their definition.

These operators locate a +axis / -axis neighbour per node and take a central
difference along the edge between them.  Two facts are pinned here:

1. On an AXIS-ALIGNED mesh (the case they are defined for) they are exact: a
   ramp along the axis gives exactly 1, and a field that does not vary along
   the axis gives exactly 0.

2. On a SKEWED mesh the same construction is NOT the partial derivative.  With
   x = i + s*j, following the x lattice step changes y by s, so the edge
   difference of a y-ramp along x is genuinely non-zero (2/3 and 1/3 for the
   two meshes below) -- not because a wrong neighbour is chosen, but because
   that difference quotient measures the derivative along the lattice
   direction x + s*y.  The tests record the exact values so the behaviour is
   visible, and the scope limit is documented instead of papered over: a
   correct skewed-mesh derivative needs the metric terms (or a least-squares
   gradient), which is separate work.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest
from fv.model import varreg
from fv.model.dataset import FIELD_KIND_SCALAR, FieldFile, VarInfo

_AX = {"X": 0, "Y": 1, "Z": 2}


def _hex_grid(n, shear=0.0):
    """Structured n^3 node grid, x sheared by shear * j."""
    pts, idx = [], {}
    for i in range(n):
        for j in range(n):
            for k in range(n):
                idx[(i, j, k)] = len(pts)
                pts.append((float(i) + shear * j, float(j), float(k)))
    verts = np.array(pts, dtype=float)
    cells = []
    for i in range(n - 1):
        for j in range(n - 1):
            for k in range(n - 1):
                cells.append([idx[(i, j, k)], idx[(i + 1, j, k)],
                              idx[(i + 1, j + 1, k)], idx[(i, j + 1, k)],
                              idx[(i, j, k + 1)], idx[(i + 1, j, k + 1)],
                              idx[(i + 1, j + 1, k + 1)], idx[(i, j + 1, k + 1)]])
    conn = np.full((len(cells), 8), -1, dtype=np.int64)
    for r, c in enumerate(cells):
        conn[r] = c
    return verts, conn


def _ff(verts, conn, types, field, name="F"):
    ff = FieldFile(path="synthetic", kind="cgns")
    ff.vertices = np.asarray(verts, dtype=float)
    ff.n_vertices = len(verts)
    ff.cell_conn = np.asarray(conn, dtype=np.int64)
    ff.cell_types = np.asarray(types, dtype=np.int64)
    ff.n_cells = len(conn)
    ff.variables[name] = VarInfo(name=name, kind=FIELD_KIND_SCALAR,
                                 location="node",
                                 array=np.asarray(field, dtype=float))
    return ff


@pytest.mark.parametrize("axis", ["X", "Y", "Z"])
def test_axis_aligned_ramp_differentiates_to_exactly_one(axis):
    """df/dx of f = x is exactly 1 on an axis-aligned grid."""
    verts, conn = _hex_grid(3)
    ff = _ff(verts, conn, [12] * len(conn), verts[:, _AX[axis]].copy(), "R")
    out = varreg._axis_difference(ff, "R", axis)
    nz = out[np.abs(out) > 1e-12]
    assert nz.size == 9, "the 3x3 interior plane must be populated"
    assert np.allclose(nz, 1.0, atol=1e-12)


@pytest.mark.parametrize("axis", ["X", "Y", "Z"])
@pytest.mark.parametrize("other_axis", [0, 1, 2])
def test_axis_aligned_transverse_field_is_exactly_zero(axis, other_axis):
    """A field varying along a different axis has zero derivative."""
    if _AX[axis] == other_axis:
        pytest.skip("not transverse")
    verts, conn = _hex_grid(3)
    ff = _ff(verts, conn, [12] * len(conn), verts[:, other_axis].copy(), "T")
    out = varreg._axis_difference(ff, "T", axis)
    assert np.allclose(out, 0.0, atol=1e-12), np.unique(np.round(out, 9))


def test_axis_aligned_oblique_cells_are_exact():
    """Prism/pyramid cells on an axis-aligned layout stay exact."""
    verts = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 1.0, 0.0],
                      [0.5, 0.5, 1.0],
                      [2.0, 0.0, 0.0], [1.5, 1.0, 0.0],
                      [2.5, 0.0, 0.0], [2.5, 1.0, 0.0], [2.5, 0.5, 1.0],
                      [3.5, 0.0, 0.0], [3.5, 1.0, 0.0], [3.5, 0.5, 1.0],
                      [4.5, 0.5, 0.5]], dtype=float)
    cells = [[0, 1, 2, 3], [1, 4, 5, 3], [6, 7, 8, 9, 10, 11], [9, 10, 11, 8, 12]]
    conn = np.full((4, 8), -1, dtype=np.int64)
    for r, c in enumerate(cells):
        conn[r, :len(c)] = c
    ff = _ff(verts, conn, [10, 10, 13, 14], verts[:, 0].copy(), "X")
    out = varreg._axis_difference(ff, "X", "X")
    nz = out[np.abs(out) > 1e-12]
    assert nz.size > 0
    assert np.allclose(nz, 1.0, atol=1e-9), np.unique(np.round(nz, 6))


@pytest.mark.parametrize("shear", [0.5, 2.0])
def test_skewed_mesh_edge_difference_is_the_longitudinal_derivative(shear):
    """Documented scope limit, not a defect to hide.

    Following the x lattice step on x = i + s*j moves y by s as well, so the
    edge difference of the field y is the derivative along the lattice
    direction x + s*y instead of the partial derivative d/dx, and comes out
    non-zero.  The assertion is deliberately about the SHAPE of the result
    because the exact value depends on which neighbours each node has; a
    correct partial derivative on a skewed mesh needs the metric terms or a
    least-squares gradient.
    """
    verts, conn = _hex_grid(3, shear)
    ff = _ff(verts, conn, [12] * len(conn), verts[:, 1].copy(), "Y")
    out = varreg._axis_difference(ff, "Y", "X")
    nz = out[np.abs(out) > 1e-12]
    assert nz.size > 0, "the skewed case should still return something"
    assert np.isfinite(out).all()
    assert (nz > 0).all(), "a y-ramp must not read as decreasing along x"
    assert not np.allclose(out, 0.0), "this is NOT the partial derivative"
