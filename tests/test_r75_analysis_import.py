"""R75 tests: import analysis data source (``fv.gui.analysis.load_analysis_source``).

The GUI's ``Import Analysis Data Source`` round-trips the JSON that R74's
``Export Analysis Data Source`` writes (and that ``fv.report`` consumes on
disk). The parse itself is delegated to ``fv.report.load_input``; these tests
cover that the GUI-facing entry point resolves it correctly, including the
bare-artifact and error cases. Pure stdlib, headless.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.gui.analysis import load_analysis_source


def _artifact(name="probe set") -> dict:
    return {"name": name, "cycles": 1,
            "probes": [{"query": "p0", "node": 0, "xyz": None,
                        "values": [1.0]}]}


def _write(tmp_path, *, verts=None, bare=False) -> tuple[str, np.ndarray, dict]:
    """Write an exported analysis-source JSON and return ``(path, verts, artifact)``."""
    v = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                   dtype=np.float64)
    artifact = _artifact()
    if bare:
        data = artifact
    else:
        verts_list = v.tolist() if verts is not False else []
        data = {"verts": verts_list, "artifact": artifact}
    p = tmp_path / "source.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p), v, artifact


def test_load_analysis_source_roundtrip(tmp_path):
    path, v, artifact = _write(tmp_path)
    got_verts, got_artifact = load_analysis_source(path)
    np.testing.assert_array_equal(got_verts, v)
    assert got_artifact == artifact


def test_load_analysis_source_bare_artifact(tmp_path):
    path, _v, artifact = _write(tmp_path, bare=True)
    got_verts, got_artifact = load_analysis_source(path)
    assert got_verts.shape == (0, 3)
    assert got_artifact == artifact


def test_load_analysis_source_missing_verts(tmp_path):
    path, _v, artifact = _write(tmp_path, verts=False)
    got_verts, got_artifact = load_analysis_source(path)
    assert got_verts.shape == (0, 3)
    assert got_artifact == artifact


def test_load_analysis_source_bad_json(tmp_path):
    p = tmp_path / "source.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_analysis_source(str(p))


def test_load_analysis_source_not_object(tmp_path):
    p = tmp_path / "source.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_analysis_source(str(p))


def test_load_analysis_source_missing_file(tmp_path):
    with pytest.raises(ValueError):
        load_analysis_source(str(tmp_path / "nope.json"))
