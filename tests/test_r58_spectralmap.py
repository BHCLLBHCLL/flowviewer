"""R58 tests: spatio-temporal spectral maps of a reconstructed field sequence.

Pure NumPy, headless, no CGNS, no VTK. Lifts the probe-level frequency family
(R41/R44) onto the whole mesh: FFTs the reconstructed frame sequence per vertex
and maps time-mean / fluctuation RMS (+ intensity) / dominant frequency.
Reuses R57 ``reconstruct_sequence`` and R41 ``mean_dt``.
"""

from __future__ import annotations

import json

import numpy as np
from fv.spectralmap import (
    build_spectral_report,
    main,
    render_html,
    temporal_spectrum_field,
    write_spectral_report,
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


def _frames_2col():
    M = 400
    t = np.arange(M) * 0.05
    sin = 1.0 + 2.0 * np.sin(2 * np.pi * 1.0 * t)
    const = np.full(M, 0.5)
    return np.stack([sin, const], axis=1), 0.05


def test_temporal_spectrum_field_tone_and_constant():
    frames, dt = _frames_2col()
    sp = temporal_spectrum_field(frames, dt=dt)
    assert sp["mean"].shape == (2,) and sp["rms"].shape == (2,)
    # sine column
    assert abs(sp["mean"][0] - 1.0) < 1e-9
    assert abs(sp["rms"][0] - np.sqrt(2.0)) < 1e-6     # std of A sin = A/√2
    assert abs(sp["freq"][0] - 1.0) < 0.05              # 1 Hz dominant
    assert abs(sp["dom_amp"][0] - 2.0) < 1e-3           # physical tone amplitude
    assert sp["rms_intensity"][0] > 0.5
    # constant column: no fluctuation
    assert sp["rms"][1] < 1e-9
    assert sp["nyquist"] > 9.9                           # ~10 Hz


def test_temporal_spectrum_field_degenerate():
    empty = temporal_spectrum_field(np.empty((0, 3)), dt=0.1)
    assert empty["mean"].shape == (3,) and np.isnan(empty["mean"]).all()

    two_row = temporal_spectrum_field(np.zeros((1, 4)), dt=1.0)  # M<2
    assert np.isnan(two_row["mean"]).all()


def test_build_spectral_report_maps_and_freq():
    rep = build_spectral_report(_grid3(), _art(), dt=0.05)
    assert rep["n_frames"] > 2 and rep["n_vertices"] == 9
    for m in ("mean", "rms", "intensity", "freq"):
        assert rep["maps"][m].shape == (9,)
        assert m in rep["stats"] and m in rep["previews"]
    assert rep["previews"]["mean"].shape == (24, 24)
    # node 0 is a probe carrying the 1 Hz tone -> its field FFT peaks at ~1 Hz
    assert abs(rep["maps"]["freq"][0] - 1.0) < 0.1
    assert rep["stats"]["freq"]["coverage"] > 0
    assert rep["nyquist"] > 0 and rep["dt"] == 0.05


def test_build_spectral_report_dt_inference_and_empty():
    # default dt inferred via mean_dt(cycles) matches the explicit value
    rep = build_spectral_report(_grid3(), _art())
    assert abs(rep["dt"] - 0.05) < 1e-9

    art = {"name": "x", "cycles": [], "probes": []}
    empty = build_spectral_report(_grid3(), art)
    assert empty["n_probes"] == 0 and empty["n_frames"] == 0
    assert np.isnan(empty["maps"]["mean"]).all()
    assert empty["stats"]["mean"]["coverage"] == 0


def test_render_html_sections_and_escaping():
    art = _art("<script>alert(1)</script>")
    rep = build_spectral_report(_grid3(), art, dt=0.05)
    h = render_html(rep)
    for title in ("Time-mean field", "Fluctuation RMS", "Dominant frequency"):
        assert title in h
    assert h.count("<canvas") == 4                        # one per map
    assert "<script>" in h                                # the draw JS
    assert "&lt;script&gt;" in h                          # escaped field name


def test_render_html_empty():
    art = {"name": "x", "cycles": [], "probes": []}
    h = render_html(build_spectral_report(_grid3(), art))
    assert "No data." in h


def test_write_spectral_report_files_slim_and_csv(tmp_path):
    write_spectral_report(_grid3(), _art("pres sure"), str(tmp_path / "o"),
                          dt=0.05)
    out = tmp_path / "o"
    assert (out / "pres_sure_spectral.html").exists()
    assert (out / "pres_sure_spectral.json").exists()
    assert (out / "pres_sure_spectral_nodes.csv").exists()
    assert (out / "summary.json").exists()
    payload = json.loads((out / "pres_sure_spectral.json")
                         .read_text(encoding="utf-8"))
    # slim JSON must NOT embed full (N,) node arrays
    assert "maps" not in payload
    assert payload["stats"]["freq"]["coverage"] > 0
    csv_head = (out / "pres_sure_spectral_nodes.csv").read_text(
        encoding="utf-8").splitlines()[0]
    assert csv_head == "node,x,y,z,mean,rms,intensity,freq"


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

    rc = main([str(good_trace), str(vpath), "--cycles", "0:80",
               "--dt", "0.05", "--out", str(tmp_path / "ok")])
    assert rc == 0
    assert (tmp_path / "ok" / "P_spectral.html").exists()
