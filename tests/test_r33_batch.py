"""R33 - batch export/render pipeline (bounded memory) (section 9.13).

BatchJob/BatchExporter walk several streaming CGNS datasets through the R31
windowed reader under one memory budget (one dataset resident at a time),
extracting fields as JSON samples or full-field raw float64 (tile-streamed),
plus an optional coarse render, and write a manifest + progress callback. All
data paths are headless-safe; render is honestly False headless (R30 closed
loop). Non-stream defaults stay unchanged.
"""

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("h5py")

from fv.model.dataset import open_stream_cgns  # noqa: E402

# reuse the R28 synthetic two-zone CGNS builder
from test_r28_lazy import _make_two_zone  # noqa: E402,F401


@pytest.fixture
def two_cgns(tmp_path):
    a = str(tmp_path / "r33_a.cgns")
    b = str(tmp_path / "r33_b.cgns")
    _make_two_zone(a)
    _make_two_zone(b)
    return [a, b]


def _field_of(path):
    handle, _ = open_stream_cgns(path, budget_bytes=1 << 22)
    name = sorted(handle.field_names())[0]
    total = int(handle.field_len(name))
    lo, ref = handle.read_window(name, 0, total)
    return name, total, ref


def test_batch_json_sample_matches_handle(two_cgns, tmp_path):
    from fv.batch import BatchJob, run_batch
    name, total, _ = _field_of(two_cgns[0])
    job = BatchJob(inputs=two_cgns, out_dir=str(tmp_path / "out"),
                   extract=[name], window_len=32)
    manifest = run_batch(job)
    res = manifest["results"]
    assert len(res) == len(two_cgns)
    for entry, inp in zip(res, two_cgns):
        assert entry["writes"], "no fields extracted"
        w = entry["writes"][0]
        assert w["field"] == name
        payload = json.loads((tmp_path / "out" / w["file"]).read_text("utf-8"))
        expected = min(total, 32)
        assert payload["n"] == expected and payload["total"] == total
        ref = open_stream_cgns(inp, budget_bytes=1 << 22)[0].read_window(
            name, 0, expected)[1]
        assert np.allclose(np.asarray(payload["values"]), ref, equal_nan=True)


def test_batch_bin_full_field_tile_streamed(two_cgns, tmp_path):
    """bin export writes the whole field; byte count and values match."""
    from fv.batch import BatchJob, run_batch
    name, total, _ = _field_of(two_cgns[0])
    job = BatchJob(inputs=two_cgns, out_dir=str(tmp_path / "bin"),
                   extract=[name], fmt="bin")
    manifest = run_batch(job)
    w = manifest["results"][0]["writes"][0]
    assert w["n"] == total
    path = tmp_path / "bin" / w["file"]
    assert path.stat().st_size == total * 8
    raw = path.read_bytes()
    got = np.frombuffer(raw, dtype=np.float64)
    handle, _ = open_stream_cgns(two_cgns[0], budget_bytes=1 << 22)
    _, ref = handle.read_window(name, 0, total)
    assert np.array_equal(got, ref, equal_nan=True)


def test_batch_manifest_and_progress(two_cgns, tmp_path):
    from fv.batch import BatchJob, run_batch
    job = BatchJob(inputs=two_cgns, out_dir=str(tmp_path / "m"), window_len=8)
    calls = []

    def cb(done, total):
        calls.append((done, total))

    manifest = run_batch(job, on_progress=cb)
    assert manifest["job"] == job.to_dict()
    assert len(manifest["results"]) == len(two_cgns)
    # progress fires for each dataset plus a final (n, n) tick
    assert calls[-1] == (len(two_cgns), len(two_cgns))
    assert len(calls) >= len(two_cgns) + 1


def test_batch_tight_budget_still_correct(two_cgns, tmp_path):
    """A very small budget still yields bit-exact extraction (bounded LRU)."""
    from fv.batch import BatchJob, run_batch
    name, _, _ = _field_of(two_cgns[0])
    job = BatchJob(inputs=two_cgns[:1], out_dir=str(tmp_path / "tiny"),
                   stream_budget_mb=1, extract=[name], fmt="bin")
    manifest = run_batch(job)
    w = manifest["results"][0]["writes"][0]
    raw = (tmp_path / "tiny" / w["file"]).read_bytes()
    got = np.frombuffer(raw, dtype=np.float64)
    handle, _ = open_stream_cgns(two_cgns[0], budget_bytes=1 << 22)
    _, ref = handle.read_window(name, 0, handle.field_len(name))
    assert np.array_equal(got, ref, equal_nan=True)


def test_job_write_read_roundtrip(two_cgns, tmp_path):
    from fv.batch import BatchJob, write_job_file
    job = BatchJob(inputs=two_cgns, window_len=7, render=True)
    p = str(tmp_path / "job.json")
    write_job_file(p, job)
    back = BatchJob.from_path(p)
    assert back.to_dict() == job.to_dict()


def test_batch_cli_produces_manifest(two_cgns, tmp_path):
    from fv.batch import BatchJob, main, write_job_file
    job = BatchJob(inputs=two_cgns[:1], out_dir=str(tmp_path / "cli"))
    p = str(tmp_path / "job.json")
    write_job_file(p, job)
    assert main([p]) == 0
    assert (tmp_path / "cli" / "manifest.json").exists()


def test_gui_batch_action_present(two_cgns, _qapp):
    """File > Export Batch… action is wired (no dialog opened headless)."""
    from fv.gui.main import FlowViewer
    w = FlowViewer(filepath=None, enable_3d=True)
    try:
        assert hasattr(w, "on_batch_export") and callable(w.on_batch_export)
    finally:
        w.close()


@pytest.fixture
def _qapp():
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception:
        pytest.skip("PyQt5 unavailable")
    return QApplication.instance() or QApplication([])
