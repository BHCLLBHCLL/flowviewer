"""R74: headless command-line entry for the analysis-report family.

Brings the R64-R73 headless machinery (``run_report`` / ``run_report_bundle`` /
``run_project`` / ``export_report_bundle``) to a terminal and to CI: read a
JSON input (``verts`` + ``artifact``) and emit HTML reports to a directory,
optionally bordered by an ``index.html`` and zipped into a shareable bundle.

Invoke via ``python -m fv.report``:

    python -m fv.report input.json -o reports --all -z reports.zip
    python -m fv.report input.json -o reports -k spectral -k coherence
    python -m fv.report input.json -o reports --project "my batch"

The ``input.json`` layout is ``{"verts": [[x, y, z], ...], "artifact": {...}}``.
When the top-level ``artifact`` key is absent the whole JSON object is treated
as the artifact (``verts`` then defaults to an empty array), so a bare report
workload can be pointed at a plain artifact file. ``--project`` overrides both
``--kind`` and ``--all`` and loads a named batch from ``ProjectStore``.

The machine-readable manifest is printed to stdout as a single JSON object:

    {"out_dir": "...", "reports": {kind: rel_html}, "index": rel_html|null,
     "zip": rel_zip|null, "count": n}

No PyQt is imported here; the module stays headless and CI-friendly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .gui.analysis import (
    ProjectStore,
    export_report_bundle,
    project_store_path,
    run_project,
    run_report_bundle,
)


def _as_verts(verts: Any) -> np.ndarray:
    """Coerce a raw ``verts`` value into an ``(N, 3)`` float array."""
    if verts is None:
        return np.empty((0, 3), dtype=np.float64)
    v = np.asarray(verts, dtype=np.float64)
    if v.ndim == 1:
        return v.reshape((-1, 3))
    if v.ndim == 2 and v.shape[1] >= 3:
        return v[:, :3]
    raise ValueError("verts must be a flat (N*3) or an (N, 3) array")


def load_input(path: str) -> tuple[np.ndarray, dict]:
    """Parse a CLI input JSON file into ``(verts, artifact)``."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read analysis input: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("analysis input must be a JSON object")
    artifact = data.get("artifact", data)
    if not isinstance(artifact, dict):
        raise ValueError("input artifact must be a JSON object")
    verts = _as_verts(data.get("verts"))
    return verts, artifact


def load_params(path: Optional[str]) -> dict:
    """Load a ``{kind: {param: value}}`` overlay from JSON (empty when absent)."""
    if not path:
        return {}
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read params: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("params must be a JSON object of {kind: {param: value}}")
    return data


def _rel(path: str, base: Path) -> str:
    """Return ``path`` as a posix path relative to ``base``.

    ``base`` need not be an ancestor (e.g. a bundle written beside the output
    directory yields ``../name.zip``); an unresolvable cross-drive path falls
    back to its absolute posix form.
    """
    try:
        rel = os.path.relpath(str(Path(path).resolve()),
                              str(Path(base).resolve()))
    except ValueError:
        return str(Path(path))
    return Path(rel).as_posix()


def run(config: dict) -> dict:
    """Execute a report run from a parsed config and return the manifest."""
    out_dir = Path(config.get("out_dir") or "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    verts, artifact = load_input(config["input"])
    params = config.get("params") or {}
    kinds = config.get("kinds")
    project = config.get("project")
    dt = config.get("dt")
    title = config.get("title") or "flowviewer analysis bundle"
    zip_path = config.get("zip")

    if project:
        store = ProjectStore(path=project_store_path())
        paths = run_project(store, project, verts, artifact, str(out_dir), dt=dt)
        if paths is None:
            raise ValueError(f"unknown analysis project: {project!r}")
    else:
        paths = run_report_bundle(verts, artifact, str(out_dir),
                                  kinds=kinds, params=params, dt=dt)

    reports = {kind: _rel(str(p), out_dir) for kind, p in paths.items()}
    index = _rel(str(out_dir / "index.html"), out_dir) if paths else None
    zpath = None
    if zip_path and paths:
        zpath = export_report_bundle(paths, zip_path, title=title)
    return {
        "out_dir": str(out_dir.resolve()),
        "reports": reports,
        "index": index,
        "zip": _rel(str(zpath), out_dir) if zpath else None,
        "count": len(reports),
    }


def main(argv: Optional[list] = None) -> int:
    """Argument-parsing entry point; returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m fv.report",
        description="Generate flowviewer analysis reports headlessly.")
    parser.add_argument("input", help="analysis input JSON (verts + artifact)")
    parser.add_argument("-o", "--out-dir", default="reports",
                        help="output directory for generated reports")
    parser.add_argument("-k", "--kind", dest="kinds", action="append",
                        help="report kind to run (repeatable)"
                             "; default/--all runs every registered kind")
    parser.add_argument("--all", action="store_true",
                        help="run every registered report kind")
    parser.add_argument("-p", "--params",
                        help="per-kind params JSON overlay")
    parser.add_argument("-P", "--project",
                        help="named analysis project to run")
    parser.add_argument("-z", "--zip",
                        help="export the generated bundle to a zip archive")
    parser.add_argument("-t", "--title", default="flowviewer analysis bundle",
                        help="index / bundle title")
    parser.add_argument("-d", "--dt", type=float, default=None,
                        help="sample period fallback (seconds)")
    args = parser.parse_args(argv)

    kinds = None if (args.all or not args.kinds) else args.kinds
    config = {
        "input": args.input,
        "out_dir": args.out_dir,
        "kinds": kinds,
        "params": load_params(args.params),
        "project": args.project,
        "zip": args.zip,
        "title": args.title,
        "dt": args.dt,
    }
    try:
        manifest = run(config)
    except (ValueError, OSError) as exc:
        print(f"fv.report: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
