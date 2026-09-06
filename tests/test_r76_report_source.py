"""R76 tests: headless report CLI built straight from a raw result sequence.

R74 fed the report pipeline a pre-built ``verts``+``artifact`` JSON. R76 closes
the loop further: ``python -m fv.report --source`` treats the first positional
argument as a *raw CGNS result sequence*, samples the chosen field (or the first
field on the first cycle) at the given monitoring points, and builds the same
``(verts, artifact)`` the GUI exports - so a result sequence goes straight to
reports with no intermediate data-source file.

These tests keep streaming open and report generation out of scope by
monkeypatching ``fv.session.SessionTimeline`` and ``fv.trace.time_trace``; they
exercise only the source→artifact building, the probe parsing, and the CLI /
``run`` dispatch. Pure stdlib, headless.
"""

from __future__ import annotations

import numpy as np
import pytest
from fv import report as report_cli


def _mesh():
    return {"vertices": [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]}


class _FakeHandle:
    def __init__(self, names):
        self._names = list(names)

    def field_names(self):
        return list(self._names)


_FRAMES = [(0, _FakeHandle(("Pressure",)), _mesh()),
           (1, _FakeHandle(("Pressure",)), _mesh()),
           (2, _FakeHandle(("Pressure",)), _mesh())]


def _patch_timeline(monkeypatch, frames=None):
    frames = frames if frames is not None else list(_FRAMES)

    class _TL:
        def __init__(self, _fr):
            self._fr = _fr

        @classmethod
        def from_sequence(cls, seq, budget_mb=64):
            return cls(frames)

        def __iter__(self):
            return iter(self._fr)

    monkeypatch.setattr("fv.session.SessionTimeline", _TL)


def _patch_trace(monkeypatch, fields):
    def fake(tl, probes, wants):
        return {"fields": fields}

    monkeypatch.setattr("fv.trace.time_trace", fake)


def _field_trace(name="Pressure", cycles=(0, 1, 2), values=(1.0, 2.0, 3.0)):
    return {"name": name, "cycles": list(cycles),
            "probes": [{"query": (0.0, 0.0, 0.0), "node": 0,
                        "xyz": (0.0, 0.0, 0.0), "values": list(values)}]}


def test_build_source_returns_verts_and_artifact(monkeypatch):
    _patch_timeline(monkeypatch)
    _patch_trace(monkeypatch, {"Pressure": _field_trace()})
    verts, artifact = report_cli.build_source("seq", [(0.0, 0.0, 0.0)])
    assert verts.tolist() == _mesh()["vertices"]
    assert artifact == {"name": "Pressure", "cycles": [0, 1, 2],
                        "probes": [{"query": [0.0, 0.0, 0.0], "node": 0,
                                    "xyz": [0.0, 0.0, 0.0],
                                    "values": [1.0, 2.0, 3.0]}]}


def test_build_source_defaults_to_first_field(monkeypatch):
    handles = [("Pressure", "Velocity"), ("Pressure", "Velocity"),
               ("Pressure", "Velocity")]
    frames = [(i, _FakeHandle(names), _mesh()) for i, names in enumerate(handles)]
    _patch_timeline(monkeypatch, frames)
    _patch_trace(monkeypatch, {"Pressure": _field_trace()})
    verts, artifact = report_cli.build_source("seq", [(0.0, 0.0, 0.0)])
    assert artifact["name"] == "Pressure"
    assert verts.shape == (3, 3)


def test_build_source_selects_requested_field(monkeypatch):
    _patch_timeline(monkeypatch)
    _patch_trace(monkeypatch, {"Velocity": _field_trace("Velocity")})
    verts, artifact = report_cli.build_source("seq", [(0.0, 0.0, 0.0)],
                                              field="Velocity")
    assert artifact["name"] == "Velocity"


def test_build_source_empty_sequence_raises(monkeypatch):
    _patch_timeline(monkeypatch, frames=[])
    with pytest.raises(ValueError, match="result sequence is empty"):
        report_cli.build_source("seq", [(0.0, 0.0, 0.0)])


def test_build_source_no_fields_raises(monkeypatch):
    frames = [(i, _FakeHandle(()), _mesh()) for i in range(3)]
    _patch_timeline(monkeypatch, frames)
    with pytest.raises(ValueError, match="exposes no fields"):
        report_cli.build_source("seq", [(0.0, 0.0, 0.0)])


def test_build_source_missing_field_trace_raises(monkeypatch):
    _patch_timeline(monkeypatch)
    _patch_trace(monkeypatch, {"Pressure": _field_trace()})
    with pytest.raises(ValueError, match="produced no trace"):
        report_cli.build_source("seq", [(0.0, 0.0, 0.0)], field="None")


def test_build_source_seq_accepts_path(monkeypatch):
    """A ``Path`` routes through ``from_sequence`` exactly like a string."""
    _patch_timeline(monkeypatch)
    _patch_trace(monkeypatch, {"Pressure": _field_trace()})
    verts, artifact = report_cli.build_source("seq", [(0.0, 0.0, 0.0)])
    assert verts.shape == (3, 3)


def test_parse_probe():
    assert report_cli._parse_probe("1,2,3") == (1.0, 2.0, 3.0)


def test_parse_probe_bad_raises():
    with pytest.raises(ValueError, match="bad probe point"):
        report_cli._parse_probe("a,b,c")


def test_load_probes_expands_file(tmp_path):
    p = tmp_path / "probes.txt"
    p.write_text("# probes\n0,0,0\n2,2,2\n", encoding="utf-8")
    out = report_cli._load_probes(["5,5,5"], str(p))
    assert out == [(5.0, 5.0, 5.0), (0.0, 0.0, 0.0), (2.0, 2.0, 2.0)]


def test_run_source_builds_then_dispatches(monkeypatch, tmp_path):
    out_dir = tmp_path / "reports"
    paths = {"spectral": str(out_dir / "spectral.html")}
    seen = {}

    def fake_source(src, probes, *, field=None, budget_mb=64):
        seen["src"] = src
        seen["probes"] = probes
        seen["field"] = field
        seen["budget_mb"] = budget_mb
        return (np.zeros((3, 3)), {"name": "Pressure", "cycles": [0, 1],
                                   "probes": []})

    monkeypatch.setattr(report_cli, "build_source", fake_source)
    monkeypatch.setattr(report_cli, "run_report_bundle",
                        lambda v, a, o, **kw: dict(paths))
    manifest = report_cli.run({"source": "seq", "probes": [(0.0, 0.0, 0.0)],
                               "field": "Pressure", "budget_mb": 32,
                               "out_dir": str(out_dir)})
    assert seen == {"src": "seq", "probes": [(0.0, 0.0, 0.0)],
                    "field": "Pressure", "budget_mb": 32}
    assert manifest["reports"] == {"spectral": "spectral.html"}
    assert manifest["index"] == "index.html"


def test_run_non_source_uses_load_input(monkeypatch, tmp_path):
    """Without ``source`` the CLI still consumes the pre-built JSON path."""
    seen = {}

    def fake_load(path):
        seen["input"] = path
        return np.zeros((2, 3)), {"name": "t", "cycles": [0], "probes": []}

    monkeypatch.setattr(report_cli, "load_input", fake_load)
    monkeypatch.setattr(report_cli, "run_report_bundle",
                        lambda v, a, o, **kw: {})
    in_path = str(tmp_path / "in.json")
    report_cli.run({"input": in_path, "out_dir": str(tmp_path / "reports")})
    assert seen["input"] == in_path


def test_main_source_parses_probes_and_succeeds(monkeypatch, tmp_path, capsys):
    manifest = {"out_dir": str(tmp_path), "reports": {"spectral": "x.html"},
                "index": "index.html", "zip": None, "count": 1}
    seen = {}

    def fake_run(config):
        seen.update(config)
        return dict(manifest)

    monkeypatch.setattr(report_cli, "run", fake_run)
    rc = report_cli.main(["seq", "--source", "--probe", "0,0,0",
                          "--field", "Pressure",
                          "--budget-mb", "16", "-o", str(tmp_path)])
    seen.pop("params", None)
    assert rc == 0
    assert seen["source"] == "seq"
    assert seen["probes"] == [(0.0, 0.0, 0.0)]
    assert seen["field"] == "Pressure"
    assert seen["budget_mb"] == 16


def test_main_source_missing_probes_exits_two(tmp_path, capsys):
    rc = report_cli.main(["seq", "--source", "-o", str(tmp_path)])
    out = capsys.readouterr()
    assert rc == 2
    assert "--source needs monitoring points" in out.err
