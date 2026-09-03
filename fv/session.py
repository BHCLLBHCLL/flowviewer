"""R34: session recording / batch render pipeline (Timeline -> frames/video).

The roadmap promised that batch / video export would run on streaming datasets
(R31-S3 note). R33 delivered single-dataset bounded-memory export; this module
adds the **time axis**: a :class:`SessionTimeline` walks a CGNS *sequence*
(``scan_sequence``: same stem, trailing cycle in the filename, sorted) - or an
explicit list - and yields each cycle's streaming handle one at a time (open /
consume / release, so memory stays bounded). :class:`SessionRecorder` then
writes, per cycle, a coarse-scene PNG snapshot and a JSON sample window plus a
``manifest.json``, reusing the R33 progress/manifest conventions.

This gives an automation-friendly, headless-verifiable pipeline that turns a
set of time-series result files into shareable frames, a video (via ffmpeg
when present - honestly 0 otherwise), and an index document, consuming the R31
windowed reader and the R32/AutomationSession render path.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, List, Optional, Sequence, Union

import numpy as np

from .model.fileset import scan_sequence

Progress = Callable[[int, int], None]


# ── timeline ───────────────────────────────────────────────────────────────


@dataclass
class SessionTimeline:
    """An ordered, cycle-sorted collection of streaming datasets.

    ``paths``: sequence members (absolute, sorted by cycle) - from
    ``scan_sequence(first_file)`` or given explicitly. ``count`` /
    ``cycles`` expose the axis; iteration opens each dataset with its own
    streaming handle (released afterwards), so peak memory stays ~ one dataset.
    """

    paths: List[str]
    budget_mb: int = 64

    def __post_init__(self) -> None:
        if isinstance(self.paths, (str, Path)):
            self.paths = [str(self.paths)]
        self.paths = [str(p) for p in self.paths]
        # order by the cycle parsed from the filename stem
        self.paths.sort(key=_cycle_of)

    @classmethod
    def from_sequence(cls, first_file: str, *, limit: int = 500,
                      budget_mb: int = 64) -> "SessionTimeline":
        fs = scan_sequence(first_file, limit=limit)
        paths = [m.path for m in fs.members]
        if not paths:
            raise ValueError(f"no sequence found around {first_file!r}")
        return cls(paths, budget_mb=budget_mb)

    @property
    def count(self) -> int:
        return len(self.paths)

    def cycles(self) -> List[int]:
        return [_cycle_of(p) for p in self.paths]

    def __iter__(self) -> Iterator[tuple]:
        from .model.dataset import open_stream_cgns
        for p in self.paths:
            handle, mesh = open_stream_cgns(
                str(p), budget_bytes=int(self.budget_mb) * 1024 * 1024)
            yield _cycle_of(p), handle, mesh


def _cycle_of(path: str) -> int:
    """Extract the trailing integer from a filename stem (``tr03_10`` -> 10)."""
    stem = Path(path).stem
    digits = ""
    for ch in reversed(stem):
        if ch.isdigit():
            digits = ch + digits
        elif digits:
            break
    return int(digits) if digits else 0


# ── recorder ───────────────────────────────────────────────────────────────


@dataclass
class SessionRecorder:
    """Record each cycle of a timeline to PNG + JSON + manifest."""

    timeline: SessionTimeline
    out_dir: str = "session_out"
    render: bool = True
    extract: List[str] = None  # type: ignore[assignment]
    window_len: int = 128

    def __post_init__(self) -> None:
        if self.extract is None:
            self.extract = []

    def run(self, on_progress: Optional[Progress] = None) -> dict:
        out = Path(self.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        total = self.timeline.count
        frames = []
        for i, (cycle, handle, mesh) in enumerate(self.timeline):
            self._notify(on_progress, i, total)
            frames.append(self._record_one(cycle, handle, mesh, out))
        self._notify(on_progress, total, total)
        manifest = {
            "job": {"timeline": list(self.timeline.paths),
                    "budget_mb": self.timeline.budget_mb},
            "frames": frames,
        }
        with open(out / "manifest.json", "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        return manifest

    def _record_one(self, cycle: int, handle, mesh, out: Path) -> dict:
        entry = {"cycle": int(cycle), "files": []}
        # coarse scene snapshot (honestly False when headless)
        if self.render:
            from .automation import AutomationSession
            with AutomationSession(budget_mb=self.timeline.budget_mb) as sess:
                sess.open(handle.path, stream=True)
                ok = sess.render(str(out / f"frame_{cycle:04d}.png"))
            entry["files"].append({"kind": "png", "name": f"frame_{cycle:04d}.png",
                                   "ok": bool(ok)})
        # field sample window (always available, headless-safe)
        wants = list(self.extract) or handle.field_names()
        for name in wants:
            if name not in handle.field_names():
                continue
            total = int(handle.field_len(name))
            lo, arr = handle.read_window(name, 0, min(total, self.window_len))
            fname = f"frame_{cycle:04d}__{name}.json"
            self._write_json(out / fname, arr, total)
            entry["files"].append({"kind": "json", "field": name,
                                   "name": fname, "n": int(arr.size)})
        entry["n_files"] = len(entry["files"])
        return entry

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


def record_sequence(paths: Union[str, Sequence[str]], out_dir: str = "session_out",
                    *, render: bool = True, extract: Optional[list] = None,
                    window_len: int = 128, budget_mb: int = 64,
                    on_progress: Optional[Progress] = None) -> dict:
    """Record a CGNS sequence (or explicit list) into frames + JSON + manifest."""
    if isinstance(paths, (str, Path)):
        tl = SessionTimeline.from_sequence(str(paths), budget_mb=budget_mb)
    else:
        tl = SessionTimeline(list(paths), budget_mb=budget_mb)
    rec = SessionRecorder(tl, out_dir=out_dir, render=render,
                          extract=list(extract) if extract else [],
                          window_len=window_len)
    return rec.run(on_progress)


def encode_video(frame_dir: str, out_path: str, *, fps: int = 15,
                 pattern: str = "frame_%04d.png", ffmpeg: Optional[str] = None) -> int:
    """Encode a PNG frame sequence to a video with ffmpeg (best-effort).

    Returns the number of frames encoded, or 0 when ffmpeg is unavailable /
    fails (honest degrade; the GUI's existing .ogv path stays the fallback).
    """
    exe = ffmpeg or os.environ.get("FFMPEG", "ffmpeg")
    if not shutil_which(exe):
        return 0
    frame_dir = Path(frame_dir)
    if not frame_dir.exists():
        return 0
    n = len(list(frame_dir.glob(pattern)))
    if n == 0:
        return 0
    cmd = [exe, "-y", "-framerate", str(int(fps)), "-i",
           str(frame_dir / pattern), str(out_path)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=300)
    except Exception:  # pragma: no cover - external tool
        return 0
    return n if os.path.exists(out_path) and os.path.getsize(out_path) > 0 \
        else 0


def shutil_which(exe: str) -> Optional[str]:
    from shutil import which
    return which(exe)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="fv.session", description="FlowViewer R34 sequence recorder")
    ap.add_argument("paths", nargs="+", help="sequence dir / first file / list")
    ap.add_argument("--out", default="session_out")
    ap.add_argument("--no-render", action="store_true",
                    help="skip coarse PNG snapshots (headless-safe)")
    ap.add_argument("--window", type=int, default=128)
    ap.add_argument("--budget-mb", type=int, default=64)
    ap.add_argument("--fields", nargs="*", default=None)
    args = ap.parse_args(argv)
    paths = args.paths if len(args.paths) > 1 else args.paths[0]
    manifest = record_sequence(
        paths, out_dir=args.out, render=not args.no_render,
        extract=args.fields, window_len=args.window,
        budget_mb=args.budget_mb)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
