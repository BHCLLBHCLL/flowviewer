"""R3.5 Nastran .op2 binary result loader tests (pyNastran optional).

Skipped when pyNastran or the vendored fixture is absent.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

OP2_SAMPLE = Path(__file__).resolve().parent / "data" / "plate_py.op2"

try:
    from pyNastran.op2.op2 import read_op2  # noqa: F401
    _HAS_PYNASTRAN = True
except Exception:
    _HAS_PYNASTRAN = False

pytestmark = pytest.mark.skipif(
    not _HAS_PYNASTRAN or not OP2_SAMPLE.exists(),
    reason="pyNastran or plate_py.op2 fixture not present")


def test_op2_parse_counts():
    """Geometry parses: vertices + cells + per-cell types."""
    from fv.crdl.op2 import parse_op2
    m = parse_op2(str(OP2_SAMPLE))
    assert m is not None and m["op2"] is True
    assert m["n_vertices"] > 0 and m["n_cells"] > 0
    assert m["vertices"].shape == (m["n_vertices"], 3)
    assert m["cell_conn"].shape[0] == m["n_cells"]
    assert np.asarray(m["cell_types"]).size == m["n_cells"]
    # 0-based ids in range
    ids = m["cell_conn"][m["cell_conn"] >= 0]
    assert ids.size and ids.max() < m["n_vertices"]


def test_op2_fields():
    """Displacement magnitude (node) or von Mises (cell) when present."""
    from fv.crdl.op2 import parse_op2
    m = parse_op2(str(OP2_SAMPLE))
    assert m is not None
    fields = m["fields"]
    # plate_py.op2 carries displacements; assert at least one field
    assert fields, "expected at least one result field"
    for name, (arr, loc) in fields.items():
        assert loc in ("node", "cell")
        assert np.asarray(arr).size > 0


def test_op2_loader_fieldfile():
    """op2_load produces a renderer-consumable FieldFile."""
    from fv.model.dataset import op2_load
    from fv.model.loaders import can_load
    assert can_load(str(OP2_SAMPLE)) is True
    ff = op2_load(str(OP2_SAMPLE))
    assert ff.kind == "op2"
    assert ff.n_cells > 0 and ff.n_vertices > 0
    assert ff.cell_types is not None
    from fv.render.plane import build_ugrid
    ug, _cc = build_ugrid(ff)
    assert ug is not None and ug.GetNumberOfCells() == ff.n_cells


def test_op2_probe_without_lib(tmp_path, monkeypatch):
    """probe reports op2; parse returns None without pyNastran."""
    import fv.crdl.op2 as op2mod
    from fv.model.loaders import probe_format
    p = tmp_path / "x.op2"
    p.write_bytes(b"\x00" * 64)
    monkeypatch.setattr(op2mod, "_HAS_PYNASTRAN", False)
    assert probe_format(str(p)).startswith("op2")
    assert op2mod.parse_op2(str(p)) is None


def test_op2_mock_model_mapping(monkeypatch):
    """Mapping logic validated against a fake pyNastran model (no fixture)."""
    import fv.crdl.op2 as op2mod

    class GRID:
        def __init__(self, xyz):
            self.xyz = np.asarray(xyz, dtype=np.float64)

    class Elem:
        def __init__(self, etype, nodes):
            self.type = etype
            self.nodes = list(nodes)

    class Disp:
        subcase = 1
        def __init__(self, data):
            self.data = np.asarray(data, dtype=np.float64)

    model = type("Fake", (), {})()
    model.nodes = {1: GRID([0, 0, 0]), 2: GRID([1, 0, 0]),
                   3: GRID([1, 1, 0]), 4: GRID([0, 1, 0]),
                   5: GRID([0, 0, 1]), 6: GRID([1, 0, 1]),
                   7: GRID([1, 1, 1]), 8: GRID([0, 1, 1])}
    model.elements = {1: Elem("CHEXA8", [1, 2, 3, 4, 5, 6, 7, 8])}
    model.displacements = {1: Disp(np.tile([0.0, 0.0, 0.0, 0, 0, 0],
                                             (8, 1)))}
    monkeypatch.setattr(op2mod, "_HAS_PYNASTRAN", True)
    monkeypatch.setattr(op2mod, "read_op2",
                        lambda *a, **k: model)
    import pathlib
    import tempfile
    p = pathlib.Path(tempfile.gettempdir()) / "fake.op2"
    p.write_bytes(b"\x00" * 8)
    m = op2mod.parse_op2(str(p))
    assert m is not None
    assert m["n_vertices"] == 8 and m["n_cells"] == 1
    assert m["cell_conn"].tolist() == [[0, 1, 2, 3, 4, 5, 6, 7]]
    assert np.asarray(m["cell_types"]).tolist() == [12]
    assert "DISPMAG(SUB1)" in m["fields"]
    p.unlink()
