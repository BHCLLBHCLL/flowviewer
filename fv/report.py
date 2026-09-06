"""R74: headless command-line entry for the analysis-report family.

Brings the R64-R73 headless machinery (``run_report`` / ``run_report_bundle`` /
``run_project`` / ``export_report_bundle``) to a terminal and to CI: read a
JSON input (``verts`` + ``artifact``) and emit HTML reports to a directory,
optionally bordered by an ``index.html`` and zipped into a shareable bundle.

Invoke via ``python -m fv.report``:

    python -m fv.report input.json -o reports --all -z reports.zip
    python -m fv.report input.json -o reports -k spectral -k coherence
    python -m fv.report input.json -o reports --project "my batch"
    python -m fv.report out/*_step*.cgns -o reports --source \
        --probe 0.5,0.5,0.5 --field Pressure --all
    python -m fv.report --project "my batch" -o reports

The ``input.json`` layout is ``{"verts": [[x, y, z], ...], "artifact": {...}}``.
When the top-level ``artifact`` key is absent the whole JSON object is treated
as the artifact (``verts`` then defaults to an empty array), so a bare report
workload can be pointed at a plain artifact file. ``--project`` overrides both
``--kind`` and ``--all`` and loads a named batch from ``ProjectStore``.

R76 adds a fully headless source path: pass ``--source`` (plus repeatable
``--probe x,y,z`` / ``--probes-file`` and an optional ``--field``) and the
first positional argument is treated as a **raw CGNS result sequence** —
directory, first file, or explicit list — instead of a JSON. ``vertices`` come
from the first cycle's mesh and the artifact is the selected field's per-probe
time history, so a result sequence goes straight to reports with no pre-built
data-source JSON.

R79 lets the headless CLI honour a self-contained project's own source: when
``--project`` names a batch saved with a rebuildable data-source descriptor
(R78), ``run`` re-materialises ``(verts, artifact)`` from that descriptor
instead of requiring a separate input, so ``python -m fv.report --project "x"``
alone re-runs the project exactly as the GUI does. Projects saved without a
rebuildable descriptor (a Time Series) or a project with no stored recipe fall
back to the external ``--source`` / JSON input; with neither, the run degrades
to an empty manifest. The positional INPUT becomes optional (``nargs="?"``)
only so a self-contained project can be re-run with no input file.

The machine-readable manifest is printed to stdout as a single JSON object:

    {"out_dir": "...", "reports": {kind: rel_html}, "index": rel_html|null,
     "zip": rel_zip|null, "count": n}

No PyQt is imported here; the module stays headless and CI-friendly.

R80 adds headless project management alongside running: ``--list-projects`` prints every saved project as JSON, ``--save-project NAME`` records the current ``--source`` / JSON input as a new self-contained project (persisting the same ``sequence_desc`` / ``json_desc`` data-source descriptor the GUI tracks), and ``--delete-project NAME`` removes one -- so a project's whole lifecycle can be scripted without opening ``FlowViewer``.

"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from .gui.analysis import (
    REPORTS,
    ProjectStore,
    export_report_bundle,
    json_desc,
    project_store_path,
    resolve_source,
    run_project,
    run_report_bundle,
    sequence_desc,
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


def _parse_probe(s: str) -> tuple:
    """Parse a single ``'x,y,z'`` monitoring point into a float tuple."""
    try:
        return tuple(float(x) for x in s.split(","))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bad probe point {s!r} (expect 'x,y,z')") from exc


def _mesh_verts(mesh: Any) -> np.ndarray:
    """Extract an ``(N, 3)`` vertex array from a streaming mesh dict."""
    if mesh is None:
        return np.empty((0, 3), dtype=np.float64)
    verts = mesh.get("vertices")
    if verts is None:
        return np.empty((0, 3), dtype=np.float64)
    return np.asarray(verts, dtype=np.float64).reshape((-1, 3))


def build_source(paths: Any, probes: Sequence, field: Optional[str] = None,
                 *, budget_mb: int = 64) -> tuple[np.ndarray, dict]:
    """Build ``(verts, artifact)`` directly from a raw CGNS result sequence (R76).

    Walks *paths* (a sequence directory, its first file, or an explicit list)
    via :class:`fv.session.SessionTimeline`, binds each monitoring point to its
    nearest mesh node, and records the chosen ``field`` (or the first field the
    first cycle exposes) at every cycle — exactly the values the GUI's exported
    analysis source carries. ``verts`` comes from the first cycle's mesh, so the
    returned pair feeds the unchanged report pipeline below.

    ``field`` selects a single field because the analysis-report writers consume
    one artifact per run; run the CLI with a different ``--field`` to report on
    another field.
    """
    from .session import SessionTimeline
    from .trace import time_trace

    def make_tl() -> SessionTimeline:
        if isinstance(paths, (str, Path)):
            return SessionTimeline.from_sequence(str(paths), budget_mb=budget_mb)
        return SessionTimeline(list(paths), budget_mb=budget_mb)

    tl = make_tl()
    try:
        _cyc, handle, mesh = next(iter(tl))
    except StopIteration as exc:
        raise ValueError("result sequence is empty") from exc
    verts = _mesh_verts(mesh)

    wants = list(handle.field_names()) if not field else [field]
    if not wants:
        raise ValueError("result sequence exposes no fields to trace")
    tl = make_tl()

    report = time_trace(tl, list(probes), [wants[0]])
    trace_field = report.get("fields", {}).get(wants[0])
    if trace_field is None:
        raise ValueError(f"field {wants[0]!r} produced no trace")
    artifact = {
        "name": trace_field.get("name") or wants[0],
        "cycles": list(trace_field.get("cycles", [])),
        "probes": [
            {
                "query": list(p.get("query", [])),
                "node": int(p["node"]),
                "xyz": list(p["xyz"]) if p.get("xyz") is not None else None,
                "values": list(p.get("values", [])),
            }
            for p in trace_field.get("probes", [])
        ],
    }
    return verts, artifact


def parse_probe_points(probes: Sequence[str],
                       probes_file: Optional[str] = None) -> list:
    """Expand repeatable probe points plus an optional probe-point file (R77).

    Parses each entry of ``probes`` (a ``'x,y,z'`` string) and, when
    ``probes_file`` is given, every non-comment line of that text file into a
    list of ``(x, y, z)`` float tuples. Shared by the CLI (``--probe`` /
    ``--probes-file``) and the GUI sequence source so both parse monitoring
    points identically; invalid points raise :class:`ValueError`.
    """
    out = [_parse_probe(p) for p in probes]
    if probes_file:
        with open(probes_file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(_parse_probe(line))
    return out


def _load_probes(probes: list, probes_file: Optional[str]) -> list:
    """Expand repeatable ``--probe`` points plus an optional ``--probes-file``."""
    return parse_probe_points(probes, probes_file)


def run(config: dict) -> dict:
    """Execute a report run from a parsed config and return the manifest."""
    out_dir = Path(config.get("out_dir") or "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    params = config.get("params") or {}
    kinds = config.get("kinds")
    project = config.get("project")
    dt = config.get("dt")
    title = config.get("title") or "flowviewer analysis bundle"
    zip_path = config.get("zip")

    verts, artifact = (None, None)

    # Lazy external-source builder (R79): build the --source / JSON pair only
    # when it is actually needed, so a self-contained project's own descriptor
    # is not shadowed by a dead ``input`` that would raise while loading.
    def build_external() -> tuple:
        nonlocal verts, artifact
        if verts is not None or artifact is not None:
            return verts, artifact
        if config.get("source"):
            verts, artifact = build_source(
                config["source"], config.get("probes") or [],
                field=config.get("field"),
                budget_mb=int(config.get("budget_mb") or 64))
        elif config.get("input"):
            verts, artifact = load_input(config["input"])
        return verts, artifact

    if project:
        store = ProjectStore(path=project_store_path())
        # R79: a saved project's self-contained source takes precedence so it
        # re-runs headlessly with no separate input; fall back to the external
        # (--source / JSON) pair for legacy R73 projects or when the stored
        # descriptor is unknown, unreadable or flagged as a timeseries marker.
        stored = store.get(project)
        verts, artifact = resolve_source(
            (stored or {}).get("source"), current=(None, None))
        if verts is None and artifact is None:
            verts, artifact = build_external()
        paths = run_project(store, project, verts, artifact, str(out_dir), dt=dt)
        if paths is None:
            raise ValueError(f"unknown analysis project: {project!r}")
    else:
        verts, artifact = build_external()
        if artifact is None:
            raise ValueError(
                "no analysis input: pass a JSON input or --source, "
                "or use --project for a self-contained project")
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


def _all_kinds() -> list:
    """Every registered report kind, in registration order."""
    return list(REPORTS.keys())


def main(argv: Optional[list] = None) -> int:
    """Argument-parsing entry point; returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="python -m fv.report",
        description="Generate flowviewer analysis reports headlessly.")
    parser.add_argument("input", nargs="?", default=None,
                        help="analysis input JSON (verts + artifact), or a raw "
                             "CGNS result sequence with --source; optional when "
                             "--project names a self-contained project (R79)")
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
    parser.add_argument("--source", action="store_true",
                        help="treat INPUT as a raw CGNS result sequence and "
                             "build verts+artifact on the fly (R76)")
    parser.add_argument("--probe", dest="probes", action="append", default=[],
                        help="monitoring point 'x,y,z' to sample"
                             " (repeatable; --source only)")
    parser.add_argument("--probes-file", default=None,
                        help="text file of 'x,y,z' per line (--source only)")
    parser.add_argument("--field", default=None,
                        help="field to trace into the artifact (--source only; "
                             "default = first field on the first cycle)")
    parser.add_argument("--budget-mb", type=int, default=64,
                        help="per-cycle memory budget in MB for streaming"
                             " (--source only)")
    parser.add_argument("--list-projects", action="store_true",
                        help="print the saved analysis projects as JSON (R80)")
    parser.add_argument("--save-project", metavar="NAME",
                        help="save INPUT / --source as a new self-contained "
                             "analysis project (R80)")
    parser.add_argument("--delete-project", metavar="NAME",
                        help="delete a saved analysis project (R80)")
    args = parser.parse_args(argv)

    # R80: project-management actions run instead of generating reports.
    if args.list_projects:
        store = ProjectStore(path=project_store_path())
        projects = []
        for name in store.names():
            proj = store.get(name) or {}
            projects.append({
                "name": name,
                "kinds": list(proj.get("kinds", [])),
                "params": proj.get("params", {}),
                "self_contained": bool(proj.get("source")),
            })
        print(json.dumps({"projects": projects}, indent=2))
        return 0

    if args.delete_project:
        store = ProjectStore(path=project_store_path())
        if not store.delete(args.delete_project):
            print(f"fv.report: project not found: {args.delete_project!r}",
                  file=sys.stderr)
            return 1
        print(json.dumps({"deleted": True, "name": args.delete_project},
                         indent=2))
        return 0

    if args.save_project:
        kinds = _all_kinds() if (args.all or not args.kinds) else args.kinds
        if args.source and not args.input:
            print("error: --source needs a raw CGNS result sequence as INPUT",
                  file=sys.stderr)
            return 2
        probes = []
        if args.source:
            try:
                probes = _load_probes(args.probes, args.probes_file)
            except (OSError, ValueError) as exc:
                print(f"fv.report: {exc}", file=sys.stderr)
                return 2
            if not probes:
                print("error: --source needs monitoring points"
                      " (--probe x,y,z or --probes-file)", file=sys.stderr)
                return 2
            desc = sequence_desc(args.input, probes, field=args.field,
                                 budget_mb=args.budget_mb)
        elif args.input:
            desc = json_desc(args.input)
        else:
            print("error: --save-project needs a --source sequence or a JSON "
                  "INPUT to record as the project's data source", file=sys.stderr)
            return 2
        try:
            store = ProjectStore(path=project_store_path())
            saved = store.save(args.save_project, kinds,
                               load_params(args.params), source=desc)
        except ValueError as exc:
            print(f"fv.report: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"saved": True, "name": args.save_project, **saved},
                         indent=2))
        return 0

    if args.source and not args.input:
        print("error: --source needs a raw CGNS result sequence as INPUT",
              file=sys.stderr)
        return 2
    if not args.input and not args.project:
        print("error: an input (JSON or --source sequence) is required unless "
              "--project names a self-contained project", file=sys.stderr)
        return 2
    kinds = None if (args.all or not args.kinds) else args.kinds
    probes = []
    if args.source:
        try:
            probes = _load_probes(args.probes, args.probes_file)
        except (OSError, ValueError) as exc:
            print(f"fv.report: {exc}", file=sys.stderr)
            return 2
        if not probes:
            print("error: --source needs monitoring points"
                  " (--probe x,y,z or --probes-file)", file=sys.stderr)
            return 2
    config = {
        "input": args.input,
        "source": args.input if args.source else None,
        "probes": probes,
        "field": args.field,
        "budget_mb": args.budget_mb,
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
