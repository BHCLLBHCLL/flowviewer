"""R33: batch export/render pipeline (bounded memory) over streaming datasets.

The roadmap promised that batch/video export would run under a fixed memory
bound on streaming files (R31-S3 note). This module delivers it: a
:class:`BatchExporter` walks an explicit list of datasets through the R31
windowed reader, keeping **one dataset resident at a time** under a single
streaming budget. For each dataset it optionally extracts fields:

* ``fmt="json"`` - a bounded sample window ``[0, window_len)`` written as
  ``{stem}__{name}.json`` (metadata + values list);
* ``fmt="bin"``  - the *full* field streamed tile-by-tile to raw float64
  ``{stem}__{name}.bin`` (memory stays bounded; ``n == field_len``);
* ``render=True`` - a coarse-scene snapshot ``{stem}.png`` via
  ``AutomationSession`` (honestly ``False`` when headless).

Everything is recorded in ``manifest.json``. A progress callback keeps it
GUI- and CLI-friendly; ``python -m fv.batch job.json`` is the CLI entry point.
Peak RSS is bounded by "one dataset resident + budget LRU + sequential tile
write" - never the whole batch held at once.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from dataclasses import field as _dataclass_field
from pathlib import Path
from typing import Callable, Optional, Union

import numpy as np

DEFAULT_SAMPLE = 1024
Progress = Callable[[int, int], None]


# ── job model ──────────────────────────────────────────────────────────────


@dataclass
class BatchJob:
    """A batch-export job: a list of datasets + extraction/render options."""

    inputs: list
    out_dir: str = "batch_out"
    stream_budget_mb: int = 64
    extract: list = _dataclass_field(default_factory=list)
    render: bool = False
    fmt: str = "json"          # "json" (sample) | "bin" (full streamed)
    window_len: int = DEFAULT_SAMPLE
    view: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.inputs, (str, Path)):
            self.inputs = [str(self.inputs)]
        self.inputs = [str(p) for p in self.inputs]
        if self.fmt not in ("json", "bin"):
            raise ValueError(f"unsupported fmt: {self.fmt!r}")

    def to_dict(self) -> dict:
        return {
            "inputs": list(self.inputs),
            "out_dir": self.out_dir,
            "stream_budget_mb": int(self.stream_budget_mb),
            "extract": list(self.extract),
            "render": bool(self.render),
            "fmt": self.fmt,
            "window_len": int(self.window_len),
            "view": self.view,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BatchJob":
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in fields})

    @classmethod
    def from_path(cls, path: Union[str, Path]) -> "BatchJob":
        with open(str(path), "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))


def write_job_file(path: str, job: BatchJob) -> None:
    """Persist a job as JSON so collaborators can rerun it unchanged."""
    with open(str(path), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(job.to_dict(), indent=2))


# ── exporter ───────────────────────────────────────────────────────────────


class BatchExporter:
    """Sequential, memory-bounded batch export over streaming datasets."""

    def __init__(self, job: BatchJob) -> None:
        self.job = job
        self.manifest: Optional[dict] = None

    def run(self, on_progress: Optional[Progress] = None) -> dict:
        """Execute the job, write outputs + ``manifest.json``, return it."""
        from .automation import AutomationSession

        out = Path(self.job.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        total = len(self.job.inputs)
        results = []
        # one persistent session; each dataset closed on the next open => the
        # aggregation memory never exceeds one resident dataset + its budget.
        with AutomationSession(budget_mb=self.job.stream_budget_mb) as sess:
            for i, inp in enumerate(self.job.inputs):
                self._notify(on_progress, i, total)
                results.append(self._process_one(sess, inp, out))
        self._notify(on_progress, total, total)
        manifest = {"job": self.job.to_dict(), "results": results}
        with open(out / "manifest.json", "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        self.manifest = manifest
        return manifest

    # -- internals ----------------------------------------------------------
    def _process_one(self, sess, inp: str, out: Path) -> dict:
        stem = Path(inp).stem
        sess.open(str(inp), stream=True, budget_mb=self.job.stream_budget_mb)
        handle = sess.handle
        wants = list(self.job.extract) or handle.field_names()
        writes = []
        for name in wants:
            if name not in handle.field_names():
                continue
            total = int(handle.field_len(name))
            if self.job.fmt == "bin":
                fname = f"{stem}__{name}.bin"
                n = self._write_bin(handle, name, out / fname)
                writes.append({"field": name, "file": fname, "n": n,
                               "total": total})
            else:
                fname = f"{stem}__{name}.json"
                lo, arr = handle.read_window(
                    name, 0, min(total, int(self.job.window_len)))
                self._write_json(out / fname, arr, total)
                writes.append({"field": name, "file": fname,
                               "n": int(arr.size), "total": total})
        render_ok = None
        if self.job.render:
            render_ok = bool(sess.render(str(out / f"{stem}.png")))
            writes.append({"field": "<render>", "file": f"{stem}.png",
                           "ok": render_ok})
        return {"input": str(inp), "n_fields": len(writes),
                "writes": writes, "render_ok": render_ok}

    @staticmethod
    def _write_bin(handle, name: str, path: Path) -> int:
        """Stream the full field tile-by-tile: memory stays ~ tile-sized."""
        written = 0
        with open(path, "wb") as fh:
            for _start, arr in handle.iter_tiles(name):
                a = np.asarray(arr, dtype=np.float64).ravel()
                if a.size == 0:
                    continue
                fh.write(struct.pack("%sd" % int(a.size), *a.tolist()))
                written += int(a.size)
        return written

    @staticmethod
    def _write_json(path: Path, arr, total: int) -> None:
        vals = np.asarray(arr, dtype=np.float64).ravel().tolist() if arr.size \
            else []
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"total": int(total), "n": len(vals), "values": vals},
                      fh)

    @staticmethod
    def _notify(cb: Optional[Progress], done: int, total: int) -> None:
        if cb is not None:
            cb(int(done), int(total))


def run_batch(job: BatchJob, on_progress: Optional[Progress] = None) -> dict:
    """Convenience wrapper: build an exporter and run it."""
    return BatchExporter(job).run(on_progress)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.batch", description="FlowViewer R33 batch exporter")
    ap.add_argument("job", help="batch job JSON file (BatchJob.to_dict)")
    args = ap.parse_args(argv)
    job = BatchJob.from_path(args.job)
    results = run_batch(job)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
