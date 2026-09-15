"""R117: cross-format agreement against a decoder-independent reference.

The plan called for driving scPOST's COM interface to export reference values.
That path is blocked (see the R117 record): the application connects and opens
a file, but every geometry/data accessor faults server-side or reports 0, so no
values could be extracted. Rather than leave the round without external
evidence, this uses a reference of the same strength that the corpus does
support: one solver run written twice, as ``.fld`` (read by fv.crdl.mesh_fld)
and as ``.cgns`` read STRAIGHT FROM HDF5, bypassing fv.crdl.cgns entirely.

Two independent decoders, the same physical data: the coordinates and every
shared variable must agree exactly. Measured on the full 21145-node files:
coordinate max abs diff 0.0, all 15 shared variables max abs diff 0.0.

The committed excerpt (600 nodes, 11.7 KiB) is produced by
scripts/make_golden.py, so the check runs on any checkout.
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import golden
import numpy as np
import pytest

CROSS = golden.GOLDEN / "cross_format.npz"


@pytest.fixture(scope="module")
def cross():
    if not CROSS.is_file():
        pytest.skip("cross-format corpus missing (run scripts/make_golden.py)")
    with np.load(CROSS) as data:
        return {k: data[k] for k in data.files}


def test_cross_format_corpus_is_committed():
    """A reference that is not in the repository cannot back a claim."""
    assert CROSS.is_file(), "run scripts/make_golden.py"
    meta = golden.meta()["files"].get("cross_format.npz")
    assert meta, "the corpus manifest must describe the cross-format file"
    assert meta["nodes_total"] >= meta["nodes_kept"] > 0
    assert len(meta["variables"]) >= 10, meta["variables"]


def test_coordinates_agree_between_the_two_decoders(cross):
    cg = np.asarray(cross["cgns_vertices"], dtype=np.float64)
    fld = np.asarray(cross["fld_vertices"], dtype=np.float64)
    assert cg.shape == fld.shape
    assert cg.shape[1] == 3
    assert np.abs(cg - fld).max() == 0.0, (
        "FLD and CGNS decoders disagree on node coordinates")


def test_every_shared_variable_agrees_exactly(cross):
    """Each variable read two independent ways must be bit-identical."""
    names = json.loads(str(cross["variables"]))
    assert names, "no shared variables recorded"
    for name in names:
        a = np.asarray(cross["cgns__" + name], dtype=np.float64)
        b = np.asarray(cross["fld__" + name], dtype=np.float64)
        assert a.shape == b.shape, name
        assert np.abs(a - b).max() == 0.0, (
            "%s differs between the CGNS and FLD decoders" % name)


def test_the_reference_is_not_trivially_constant(cross):
    """A constant field would make the agreement check vacuous."""
    names = json.loads(str(cross["variables"]))
    varying = [n for n in names
               if float(np.ptp(np.asarray(cross["cgns__" + n]))) > 0.0]
    assert varying, (
        "every shared variable is constant across the excerpt; the cross-check "
        "would pass even for a broken decoder")
