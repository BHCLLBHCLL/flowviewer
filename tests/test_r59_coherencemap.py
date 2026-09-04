"""R59 tests: spatio-temporal coherence (co-oscillation) field map.

Pure NumPy, headless, no CGNS, no VTK. Lifts R42's Welch magnitude-squared
coherence to the whole mesh: every vertex's reconstructed frame sequence is
cohered against a reference probe, yielding peak_coherence / peak freq / mean
coherence / cross-phase fields. Reuses R57 ``reconstruct_sequence`` and R41
``mean_dt``.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fv.coherencemap import (
    build_coherence_report,
    coherence_field,
    main,
    render_html,
    write_coherence_report,
)


def _grid3() -> np.ndarray:
    return np.array([[i, j, 0.0] for i in range(3) for j in range(3)],
                    dtype=np.float64)


def _art(name="P"):
    dt = 0.05
    t = np.arange(0.0, 20.0, dt)                       # 400 cycles
    v = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)        # 1 Hz tone
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


def _frames_ref():
    M = 400
    t = np.arange(M) * 0.05
    ref = np.sin(2 * np.pi * 1.0 * t) + 1.0            # 1 Hz tone + DC
    same = ref.copy()                                  # identical
    const = np.full(M, 3.0)                            # no fluctuation
    anti = -np.sin(2 * np.pi * 1.0 * t) + 1.5          # anti-phase 1 Hz
    return np.stack([same, const, anti], axis=1), ref, 0.05


def test_coherence_field_same_const_reverse():
    frames, ref, dt = _frames_ref()
    cf = coherence_field(frames, ref, dt=dt)
    assert cf["peak_coherence"].shape == (3,)
    # identical -> unit coherence at the ref tone
    assert abs(cf["peak_coherence"][0] - 1.0) < 1e-3
    assert 0.8 < cf["peak_freq"][0] < 1.2
    # constant column -> no shared power
    assert cf["mean_coherence"][1] < 1e-6
    # anti-phase still fully coherent (magnitude-squared, phase-blind) at 1 Hz
    assert abs(cf["peak_coherence"][2] - 1.0) < 1e-3
    assert 0.8 < cf["peak_freq"][2] < 1.2
    assert abs(abs(cf["phase"][2]) - np.pi) < 0.2       # ±π cross phase
    assert cf["nseg"] >= 1 and cf["nperseg"] > 2 and cf["nyquist"] > 9.9


def test_coherence_field_errors():
    frames, ref, dt = _frames_ref()
    with pytest.raises(ValueError):
        coherence_field(frames, ref[:-1], dt=dt)        # ref length mismatch
    # M<2 -> all-NaN, no exception
    degen = coherence_field(np.zeros((1, 3)), ref[:1], dt=dt)
    assert np.isnan(degen["peak_coherence"]).all()


def test_build_report_ref_node_fully_coherent():
    rep = build_coherence_report(_grid3(), _art(), ref_probe=0, dt=0.05)
    assert rep["n_frames"] > 2 and rep["n_vertices"] == 9
    # node 0 is the reference probe's own node -> recon frames == ref series
    assert rep["maps"]["peak_coherence"][0] > 0.9
    assert abs(rep["maps"]["peak_freq"][0] - 1.0) < 0.2
    for m in ("peak_coherence", "peak_freq", "mean_coherence", "phase"):
        assert rep["maps"][m].shape == (9,)
        assert m in rep["stats"] and m in rep["previews"]
    assert rep["previews"]["peak_coherence"].shape == (24, 24)
    assert rep["nseg"] >= 1 and rep["dt"] == 0.05

    # dt inferred via mean_dt matches the explicit value
    rep2 = build_coherence_report(_grid3(), _art(), ref_probe=0)
    assert abs(rep2["dt"] - 0.05) < 1e-9


def test_build_report_ref_probe_oor_and_empty():
    with pytest.raises(ValueError):
        build_coherence_report(_grid3(), _art(), ref_probe=3)
    art = {"name": "x", "cycles": [], "probes": []}
    empty = build_coherence_report(_grid3(), art)
    assert empty["n_probes"] == 0 and empty["n_frames"] == 0
    assert np.isnan(empty["maps"]["peak_coherence"]).all()
    assert empty["stats"]["peak_coherence"]["coverage"] == 0


def test_render_html_sections_and_escaping():
    art = _art("<script>alert(1)</script>")
    rep = build_coherence_report(_grid3(), art, ref_probe=0, dt=0.05)
    h = render_html(rep)
    for title in ("Peak coherence", "Peak-coherence frequency", "Mean coherence"):
        assert title in h
    assert h.count("<canvas") == 4
    assert "<script>" in h
    assert "&lt;script&gt;" in h


def test_render_html_empty():
    art = {"name": "x", "cycles": [], "probes": []}
    h = render_html(build_coherence_report(_grid3(), art))
    assert "No data." in h


def test_write_report_files_slim_and_csv(tmp_path):
    write_coherence_report(_grid3(), _art("pres sure"), str(tmp_path / "o"),
                           ref_probe=0, dt=0.05)
    out = tmp_path / "o"
    assert (out / "pres_sure_coherence.html").exists()
    assert (out / "pres_sure_coherence.json").exists()
    assert (out / "pres_sure_coherence_nodes.csv").exists()
    assert (out / "summary.json").exists()
    payload = json.loads((out / "pres_sure_coherence.json")
                         .read_text(encoding="utf-8"))
    assert "maps" not in payload                       # no (N,) node arrays
    assert payload["ref_probe"] == 0
    assert payload["stats"]["peak_coherence"]["coverage"] > 0
    csv_head = (out / "pres_sure_coherence_nodes.csv").read_text(
        encoding="utf-8").splitlines()[0]
    assert csv_head == "node,x,y,z,peak_coherence,peak_freq,mean_coherence,phase"


def test_cli_error_cases(tmp_path, capsys):
    good_trace = tmp_path / "t.json"
    good_trace.write_text(json.dumps(_art()), encoding="utf-8")
    vpath = tmp_path / "v.npy"
    np.save(vpath, _grid3())

    bad_trace = tmp_path / "no_probe.json"
    bad_trace.write_text(json.dumps({"name": "x", "cycles": [0, 1, 2]}),
                         encoding="utf-8")
    assert main([str(bad_trace), str(vpath)]) == 2

    badv = tmp_path / "badv.json"
    badv.write_text(json.dumps([[1.0, 2.0]]), encoding="utf-8")
    assert main([str(good_trace), str(badv)]) == 2

    assert main([str(good_trace), str(vpath), "--cycles", "500:600"]) == 2

    # out-of-range reference probe -> exit 2
    assert main([str(good_trace), str(vpath), "--ref", "99"]) == 2

    rc = main([str(good_trace), str(vpath), "--cycles", "0:80",
               "--dt", "0.05", "--out", str(tmp_path / "ok")])
    assert rc == 0
    assert (tmp_path / "ok" / "P_coherence.html").exists()
