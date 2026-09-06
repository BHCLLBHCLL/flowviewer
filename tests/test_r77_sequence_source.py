"""R77 tests: GUI sequence data source mirrors the headless report source.

R76 let ``python -m fv.report --source`` build ``(verts, artifact)`` straight
from a raw CGNS result sequence. R77 exposes that same capability to the GUI —
"Set Sequence Data Source…" — through a dialog plus a pure ``sequence_source``
helper in ``fv.gui.analysis`` that delegates to ``fv.report.build_source`` so
the GUI and the headless CLI stay in lock-step. The probe-point parsing was
lifted out of the CLI-only ``_load_probes`` into a shared public
``parse_probe_points``.

These tests keep streaming open and report generation out of scope:
``sequence_source`` is checked by monkeypatching ``fv.report.build_source``,
and ``parse_probe_points`` / the ``_load_probes`` refactor are tested directly.
Pure stdlib, headless.
"""

from __future__ import annotations

import numpy as np
import pytest
from fv import report as report_cli
from fv.gui import analysis as gui_analysis


def test_parse_probe_points_no_file():
    out = report_cli.parse_probe_points(["1,2,3", "4,5,6"])
    assert out == [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)]


def test_parse_probe_points_expands_file(tmp_path):
    p = tmp_path / "probes.txt"
    p.write_text("# probes\n0,0,0\n# comment\n2,2,2\n", encoding="utf-8")
    out = report_cli.parse_probe_points(["5,5,5"], str(p))
    assert out == [(5.0, 5.0, 5.0), (0.0, 0.0, 0.0), (2.0, 2.0, 2.0)]


def test_parse_probe_points_file_skips_comments(tmp_path):
    p = tmp_path / "probes.txt"
    p.write_text("# only a comment\n\n", encoding="utf-8")
    assert report_cli.parse_probe_points([], str(p)) == []


def test_parse_probe_points_bad_raises():
    with pytest.raises(ValueError, match="bad probe point"):
        report_cli.parse_probe_points(["a,b,c"])


def test_load_probes_still_works(tmp_path):
    """The CLI-facing ``_load_probes`` wrapper still expands probes + file."""
    p = tmp_path / "probes.txt"
    p.write_text("0,0,0\n2,2,2\n", encoding="utf-8")
    out = report_cli._load_probes(["5,5,5"], str(p))
    assert out == [(5.0, 5.0, 5.0), (0.0, 0.0, 0.0), (2.0, 2.0, 2.0)]


def test_sequence_source_delegates_to_build_source(monkeypatch):
    """``sequence_source`` fans out to the headless ``build_source``."""
    seen = {}

    def fake_build(paths, probes, *, field=None, budget_mb=64):
        seen["paths"] = paths
        seen["probes"] = probes
        seen["field"] = field
        seen["budget_mb"] = budget_mb
        return np.zeros((2, 3)), {"name": "T", "cycles": [0, 1], "probes": []}

    monkeypatch.setattr("fv.report.build_source", fake_build)
    verts, artifact = gui_analysis.sequence_source(
        "seq", [(0.0, 0.0, 0.0)], field="Pressure", budget_mb=16)
    assert seen == {"paths": "seq", "probes": [(0.0, 0.0, 0.0)],
                    "field": "Pressure", "budget_mb": 16}
    assert verts.shape == (2, 3)
    assert artifact == {"name": "T", "cycles": [0, 1], "probes": []}


def test_sequence_source_forwards_url_via_list(monkeypatch):
    """A list of sequences travels through as-is (no from_sequence path)."""
    seen = {}

    def fake_build(paths, probes, *, field=None, budget_mb=64):
        seen["paths"] = paths
        return np.empty((0, 3)), {"name": "T", "cycles": [0], "probes": []}

    monkeypatch.setattr("fv.report.build_source", fake_build)
    gui_analysis.sequence_source(["a.cgns", "b.cgns"], [(0, 0, 0)])
    assert seen["paths"] == ["a.cgns", "b.cgns"]


def test_parse_probe_points_integrates_with_cli(monkeypatch, tmp_path, capsys):
    """The CLI build path still round-trips through the shared parser."""
    manifest = {"out_dir": str(tmp_path), "reports": {"spectral": "x.html"},
                "index": "index.html", "zip": None, "count": 1}
    seen = {}

    def fake_run(config):
        seen.update(config)
        return dict(manifest)

    monkeypatch.setattr(report_cli, "run", fake_run)
    rc = report_cli.main(["seq", "--source", "--probe", "0,0,0",
                          "--field", "Pressure", "-o", str(tmp_path)])
    seen.pop("params", None)
    assert rc == 0
    assert seen["source"] == "seq"
    assert seen["probes"] == [(0.0, 0.0, 0.0)]
