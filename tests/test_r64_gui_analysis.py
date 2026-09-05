"""R64 tests: GUI analysis-report hooks (report registry + generation).

Pure NumPy, headless — no display, no PyQt widgets are instantiated. The chunk
under test is ``fv/gui/analysis`` (report registry, vertex extraction and the
``run_report`` dispatcher that backs the GUI ``Analysis`` menu). It must import
cleanly without a display and produce self-contained HTML for every report kind
on a tiny mesh + an R38-style trace artifact (the same fixture R63 used).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest
from fv.gui.analysis import (
    REPORTS,
    _call,
    prepare_verts,
    report_menu,
    run_report,
)
from fv.spectralmap import write_spectral_report

CY = list(range(0, 60))


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    dt = 0.05
    t = np.arange(0.0, 10.0, dt)
    v = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    v2 = 1.5 + np.sin(2 * np.pi * 1.0 * t + 0.5)
    flat = np.zeros_like(t)
    return {
        "name": name, "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "xyz": (0.0, 0.0, 0.0),
             "values": list(v)},
            {"query": (2.0, 0.0, 0.0), "node": 2, "xyz": (2.0, 0.0, 0.0),
             "values": list(v2)},
            {"query": (0.0, 2.0, 0.0), "node": 6, "xyz": (0.0, 2.0, 0.0),
             "values": list(flat)},
        ],
    }


class _FakeDataset:
    def __init__(self, verts, path="a.cgns"):
        self.vertices = verts
        self.path = path


def test_registry_complete_and_ordered():
    assert [k for k, _ in report_menu()] == list(REPORTS)
    for k, r in REPORTS.items():
        assert r.key == k
        assert callable(r.build) and callable(r.write)
        assert r.title


def test_prepare_verts_from_dataset():
    v = prepare_verts(_FakeDataset(_grid3()))
    assert v.shape == (9, 3)
    assert float(v[0, 0]) == 0.0 and float(v[-1, 1]) == 2.0


def test_prepare_verts_empty_when_no_buffer():
    assert prepare_verts(_FakeDataset(None)).shape == (0, 3)
    assert prepare_verts(None).shape == (0, 3)


def test_run_report_unknown_kind_raises():
    with pytest.raises(ValueError):
        run_report("nope", _grid3(), _art(), "out")


def test_run_report_no_artifact_returns_none(tmp_path):
    assert run_report("spectral", _grid3(), None, str(tmp_path)) is None


def test_call_filters_unaccepted_kwargs(tmp_path):
    # 'top' is not in the spectral writer's signature -> must be dropped
    assert "top" not in inspect.signature(write_spectral_report).parameters
    out = _call(write_spectral_report, _grid3(), _art(), str(tmp_path),
                dt=0.05, top=3)
    assert "html" in out


def test_run_report_spectral(tmp_path):
    path = run_report("spectral", _grid3(), _art(), str(tmp_path), dt=0.05,
                      cycles=CY)
    assert path and path.endswith("P_spectral.html")
    p = Path(path)
    assert p.exists()
    html = p.read_text(encoding="utf-8")
    assert "<canvas" in html and "mousemove" in html


@pytest.mark.parametrize("kind", ["coherence", "evolution", "console"])
def test_run_report_field_kinds(tmp_path, kind):
    path = run_report(kind, _grid3(), _art(), str(tmp_path), dt=0.05,
                      cycles=CY, preview=12)
    assert path and path.endswith(".html")
    assert Path(path).exists()


@pytest.mark.parametrize("kind", ["spatial_pod", "spatial_dmd", "spatial_field"])
def test_run_report_spatial_kinds(tmp_path, kind):
    path = run_report(kind, _grid3(), _art(), str(tmp_path), dt=0.05,
                      cycles=CY, top=2)
    assert path and path.endswith(".html")
    assert "<html" in Path(path).read_text(encoding="utf-8").lower()
