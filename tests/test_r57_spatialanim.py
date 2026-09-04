"""R57 tests: spatial reconstruction animation sequence + unsteadiness report.

Pure NumPy, headless, no CGNS, no VTK. Reuses R53 ``reconstruct_field`` and R55
``reconstruct_field_dmd`` behind ``reconstruct_sequence`` on an R38 trace
artifact; verifies the coarse ``binned_preview``, the frame sequence, the
per-vertex temporal statistics, the HTML report and the CLI.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.spatialanim import (
    binned_preview,
    build_anim_report,
    main,
    reconstruct_sequence,
    render_html,
    stationarity,
    write_anim_report,
)


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)                       # 400 cycles
    v = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    v2 = 1.5 + np.sin(2 * np.pi * 1.0 * t + 0.5)
    return {
        "name": name, "cycles": list(t),
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "xyz": (0.0, 0.0, 0.0),
             "values": list(v)},
            {"query": (2.0, 0.0, 0.0), "node": 2, "xyz": (2.0, 0.0, 0.0),
             "values": list(v2)},
            {"query": (0.0, 2.0, 0.0), "node": 6, "xyz": (0.0, 2.0, 0.0),
             "values": list(np.zeros_like(t))},
        ],
    }


def _const_art(name="C"):
    t = list(np.arange(0.0, 4.0, 0.5))                 # 8 constant cycles
    return {
        "name": name, "cycles": t,
        "probes": [
            {"query": (0.0, 0.0, 0.0), "node": 0, "xyz": (0.0, 0.0, 0.0),
             "values": [3.5] * len(t)},
            {"query": (2.0, 0.0, 0.0), "node": 2, "xyz": (2.0, 0.0, 0.0),
             "values": [3.5] * len(t)},
            {"query": (0.0, 2.0, 0.0), "node": 6, "xyz": (0.0, 2.0, 0.0),
             "values": [3.5] * len(t)},
        ],
    }


def test_binned_preview_shape_and_single_vertex():
    v = np.array([[1.0, 2.0, 0.0]])
    out = binned_preview(v, np.array([7.5]), gridsize=10)
    assert out.shape == (10, 10)
    assert out[0, 0] == 7.5
    assert np.isnan(out).sum() == 99          # every other cell empty

    # empty grid -> all NaN, no exception
    empty = binned_preview(np.empty((0, 3)), np.empty(0), gridsize=5)
    assert empty.shape == (5, 5) and np.isnan(empty).all()

    # degenerate span (single x/y extent) is safe
    d = binned_preview(np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]),
                       np.array([1.0, 2.0]), gridsize=6)
    # both vertices land in bin (0,0); mean = 1.5
    assert abs(d[0, 0] - 1.5) < 1e-9


def test_reconstruct_sequence_pod_dmd_and_degrade():
    seq = reconstruct_sequence(_grid3(), _art(), cycles=[0, 1, 2])
    assert seq["steps"] == 3
    assert seq["cycle_idx"] == [0, 1, 2]
    assert len(seq["frames"]) == 3
    assert seq["n_vertices"] == 9 and seq["n_cycles"] == 400
    assert all(np.isfinite(f).any() for f in seq["frames"])

    # dmd path produces real frames too
    seqd = reconstruct_sequence(_grid3(), _art(), source="dmd",
                                cycles=[0, 1, 2])
    assert seqd["steps"] == 3 and seqd["source"] == "dmd"

    # empty probes -> empty sequence, no exception
    seq0 = reconstruct_sequence(_grid3(), {"name": "x", "cycles": [0, 1],
                                            "probes": []},
                                cycles=[0, 1])
    assert seq0["steps"] == 0 and seq0["frames"] == [] and seq0["cycle_idx"] == []


def test_reconstruct_sequence_oor_cycle_raises():
    with pytest.raises(ValueError):
        reconstruct_sequence(_grid3(), _art(), cycles=[400])


def test_stationarity_constant_field():
    st = stationarity(_grid3(), _const_art(), cycles=[0, 1, 2, 3])
    assert st["steps"] == 4
    assert st["n_vertices"] == 9
    assert np.allclose(st["std"], 0.0, atol=1e-9)
    assert np.allclose(st["range"], 0.0, atol=1e-9)
    assert np.isfinite(st["mean"]).any()
    for key in ("mean", "std", "range", "rms"):
        s = st[f"{key}_stats"]
        for field in ("min", "max", "mean", "finite_fraction", "coverage"):
            assert field in s


def test_build_anim_report_caps_frames_and_preview():
    rep = build_anim_report(_grid3(), _art(), frames=3)
    assert len(rep["frames"]) <= 3
    assert rep["cycle_idx"] == [fr["cycle"] for fr in rep["frames"]]
    assert rep["n_vertices"] == 9 and rep["n_cycles"] == 400
    assert rep["preview_data"] and rep["preview_data"][0].shape == (24, 24)
    for fr in rep["frames"]:
        assert fr["captured_var"] is not None and fr["captured_var"] > 0
        assert None not in (fr["min"], fr["max"], fr["mean"])
    assert rep["extent"]["xmin"] == 0.0


def test_render_html_sections_and_escaping():
    art = _art("<script>alert(1)</script>")
    rep = build_anim_report(_grid3(), art, cycles=[0, 1, 2])
    html = render_html(rep)
    for section in ("Frame browser", "Unsteadiness", "<canvas"):
        assert section in html
    assert "<script>" in html               # the frame-browser JS block
    assert "&lt;script&gt;" in html         # the field name escaped


def test_empty_artifact_graceful():
    art = {"name": "x", "cycles": [], "probes": []}
    rep = build_anim_report(_grid3(), art)
    assert rep["n_probes"] == 0 and rep["frames"] == []
    html = render_html(rep)
    assert "No data." in html
    # write path must not raise either
    summ = write_anim_report(_grid3(), art, "out_empty")
    assert summ["n_frames"] == 0


def test_write_anim_report_strange_name(tmp_path):
    write_anim_report(_grid3(), _art("pres sure"), str(tmp_path / "o"),
                      cycles=[0, 1, 2])
    assert (tmp_path / "o" / "pres_sure_anim.html").exists()
    assert (tmp_path / "o" / "pres_sure_anim.json").exists()
    assert (tmp_path / "o" / "pres_sure_anim_nodes.csv").exists()
    assert (tmp_path / "o" / "summary.json").exists()
    payload = json.loads((tmp_path / "o" / "pres_sure_anim.json")
                         .read_text(encoding="utf-8"))
    assert payload["n_probes"] == 3 and payload["cycle_idx"] == [0, 1, 2]


def test_cli_error_cases(tmp_path, capsys):
    good_trace = tmp_path / "t.json"
    good_trace.write_text(json.dumps(_art()), encoding="utf-8")
    vpath = tmp_path / "v.npy"
    np.save(vpath, _grid3())

    # trace without 'probes'
    bad_trace = tmp_path / "no_probe.json"
    bad_trace.write_text(json.dumps({"name": "x", "cycles": [0, 1, 2]}),
                         encoding="utf-8")
    assert main([str(bad_trace), str(vpath)]) == 2

    # malformed verts (not Nx3)
    badv = tmp_path / "badv.json"
    badv.write_text(json.dumps([[1.0, 2.0]]), encoding="utf-8")
    assert main([str(good_trace), str(badv)]) == 2

    # out-of-range cycles window
    assert main([str(good_trace), str(vpath), "--cycles", "500:600"]) == 2

    # happy path end-to-end
    rc = main([str(good_trace), str(vpath), "--cycles", "0:5",
               "--out", str(tmp_path / "ok")])
    assert rc == 0
    assert (tmp_path / "ok" / "P_anim.html").exists()
