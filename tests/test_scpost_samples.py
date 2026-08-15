"""Parsing coverage for the official scPOST sample FLD files.

Covers the format variants found in CradleCFD2025.2 Samples_POST/FLD:

* hex8 with a full mesh + result sections (scSTREAM_example1_100);
* result-only cycle files (200/300) that inherit the mesh from a sibling;
* tet-style meshes (Klein / 2cars / SCTeta) with NGON face lists;
* the minimumHexa minimal f32-coordinate sample.

Tests are skipped when the sample directory is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCPOST_DIR = Path(r"C:\Program Files\Cradle\CradleCFD2025.2")
SAMPLES_DIR = SCPOST_DIR / "Programs_x64" / "Samples_POST" / "FLD"


@pytest.fixture(scope="module")
def samples():
    if not SAMPLES_DIR.is_dir():
        pytest.skip("scPOST sample directory not present")
    return SAMPLES_DIR


ALL_SAMPLES = [
    "2cars.fld", "Klein_1.fld", "Klein_300.fld", "minimumHexa.fld",
    "scSTREAM_example1_100.fld", "scSTREAM_example1_200.fld",
    "scSTREAM_example1_300.fld", "SCTeta_tutorial.fld",
]


def test_scpost_all_samples_load(samples):
    """Every official sample parses without raising (format variants)."""
    from fv.model.dataset import load_file
    for name in ALL_SAMPLES:
        ff = load_file(str(samples / name))
        assert ff.kind == "fld", name
        assert ff.vertices is not None and ff.n_vertices > 0, name


def test_scpost_minimum_hexa_f32(samples):
    """minimumHexa uses f32 coordinates: 8 hex vertices (descriptor-guided)."""
    from fv.model.dataset import load_file
    ff = load_file(str(samples / "minimumHexa.fld"))
    assert ff.n_vertices == 8
    import numpy as np
    v = np.asarray(ff.vertices)
    assert abs(v[:, 0].max() - 1.0) < 1e-6  # unit hex: x in [0, 1]
    assert abs(v[:, 0].min() - 0.0) < 1e-6


def test_scpost_ex1_full_mesh(samples):
    """scSTREAM_example1_100 carries the full hex mesh + variables."""
    from fv.model.dataset import load_file
    ff = load_file(str(samples / "scSTREAM_example1_100.fld"))
    assert ff.n_cells == 18240 and ff.n_vertices == 21145
    assert "PRES" in ff.variables
    assert ff.cell_conn is not None and ff.cell_conn.shape[1] == 8


def test_scpost_result_only_inherits_mesh(samples):
    """Cycle files without mesh sections inherit the sibling mesh."""
    from fv.model.dataset import load_file
    ff200 = load_file(str(samples / "scSTREAM_example1_200.fld"))
    assert ff200.n_vertices == 21145
    assert getattr(ff200, "mesh_from", "") .endswith("scSTREAM_example1_100.fld")
    assert "PRES" in ff200.variables
    ff300 = load_file(str(samples / "scSTREAM_example1_300.fld"))
    assert ff300.n_vertices == 21145
    assert "VECTX" in ff300.variables


def test_scpost_klein_tet_mesh(samples):
    """Klein_1 is a tet grid: cells + nodes + faces all parse."""
    from fv.model.dataset import load_file
    ff = load_file(str(samples / "Klein_1.fld"))
    assert ff.n_vertices == 164343
    assert ff.n_cells == 686497
    assert ff.cell_conn is not None and ff.cell_conn.shape[1] == 4
    assert sorted(set(ff.cell_types.tolist())) == [10]  # vtk tetra
    assert "PRES" in ff.variables
    assert len(ff.faces) > 0  # NGON face list recovered
    k300 = load_file(str(samples / "Klein_300.fld"))
    assert getattr(k300, "mesh_from", "") .endswith("Klein_1.fld")
    assert k300.n_vertices == 164343


def test_scpost_scteta_tet_mesh(samples):
    """SCTeta_tutorial is a tet grid with temperature variables."""
    from fv.model.dataset import load_file
    ff = load_file(str(samples / "SCTeta_tutorial.fld"))
    assert ff.n_cells == 361868 and ff.n_vertices == 116691
    assert ff.cell_conn.shape[1] == 4
    assert "TEMP" in ff.variables


def test_scpost_2cars_mixed(samples):
    """2cars is a mixed-cell NGON variant: nodes/fields parse; the
    per-cell connectivity block layout is not yet decoded (known gap)."""
    from fv.model.dataset import load_file
    ff = load_file(str(samples / "2cars.fld"))
    assert ff.n_vertices == 338713
    assert "PRES" in ff.variables
    assert len(ff.faces) > 0
