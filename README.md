# flowviewer

Post-processing viewer for Cradle CFD `fph` / `fld` / `cgns` files.
Reads, renders, cuts, and post-processes Cradle STREAM/SCFLOW/FLOW results,
with a CradleViewer (`cvw`) byte-faithful export path.

## Requirements

- Python 3.9+
- `numpy>=1.24`
- `vtk>=9.3` (plane-cut/ugrid features)
- `PyQt5>=5.15` (GUI)

> **VTK version note:** VTK 9.4.2 and newer trigger an access violation
> (`0xC0000005`) in `vtkCutter` for `vtkConvexPointSet` grids.
> Install `pip install --user vtk==9.3.1` if plane-cut tests crash.
> Check `python -c "import vtk; print(vtk.VTK_VERSION)"` first.

## Installation

```bash
pip install -e .
# or, in a virtualenv
pip install .
```

After installing, the `flowviewer` command-line entry point is available:

```bash
flowviewer            # launch the GUI
flowviewer file.fph   # open a result file at startup
flowviewer --version  # print the version and exit
```

Without installing, you can run from the source tree:

```bash
python fv_gui.py file.fph
```

## Usage

- Load `fph` / `fld` / `cgns` result files.
- Render scalars/vectors on cuts, surfaces, streamlines, isosurfaces, etc.
- Register derived variables with user-defined functions (R18).
- Vortex identification presets: vorticity, Q-criterion, lambda-2,
  helicity and the velocity-gradient components (R23).
- Compare two datasets and generate scalar-statistics CSV reports (R20).
- Export cuts/scenes; CradleViewer `cvw` round-trips preserve `fph`
  (104 regions) and `fld` (13 regions) structure.

## Testing

```bash
pip install -e .[dev]
python -m pytest
```

## Benchmarks

```bash
python scripts/benchmark.py [file ...]
```

Times the hot paths (dataset load, cold/cached ugrid build, scalar variable
registration, Green-Gauss velocity gradient) over the bundled sample files.

## Quality gate

One command runs lint + type-check + tests + performance thresholds:

```bash
python scripts/check.py            # all four stages
python scripts/check.py --fix      # autofix import/sorting, then gate
python scripts/check.py --skip=test  # lint + types + bench only
```

Stages and rules (see `pyproject.toml`):
- **lint** — `ruff check fv/ tests/`; critical defect rules (E/F/W/B) enforced,
  style rules relaxed for legacy debt (E501/E7xx/E731/E741/B007 ignored).
- **types** — `mypy` on the progressively-typed core modules
  (`fv/model/varreg.py`, `derived.py`, `report.py`); third-party deps skipped.
- **test** — `pytest tests -q` (394 passed / 3 skipped baseline).
- **bench** — `scripts/benchmark.py --check` asserts each hot-path phase stays
  under its bound; a threshold violation exits non-zero (exit 2) and fails the
  gate.

### Benchmark thresholds

`scripts/benchmarks.json` stores upper-bound seconds per phase. Defaults are
~4-5x the 2026-08-30 dev-machine baseline so normal CI variance does not false-
fail, while a real regression must blow the bound:

| phase | threshold(s) |
|-------|-------------|
| load | 6.00 |
| ugrid_build | 10.00 |
| ugrid_cached | 1.00 |
| register_var | 0.50 |
| vortex_grad | 5.00 |

Refresh the baseline with `python scripts/benchmark.py` and edit
`scripts/benchmarks.json` when hardware/algorithm changes legitimately shift
the hot-path costs.

A GitHub Actions workflow (`.github/workflows/quality-gate.yml`) mirrors the
gate on push/PR.

## Development map

- R17 - CradleViewer (`cvw`) format reverse-engineering, loader and byte-faithful writer.
- R18 - variable registration: derived expressions, user-defined functions, vector auto-scalarization.
- R19 - plane-cut performance: batched FPH ugrid build + mesh-fingerprint cache.
- R20 - multi-dataset statistics and automated CSV reports.
- R21 - rendering depth: DST colormap / isosurface animation.
- R22 - packaging engineering: `pyproject.toml`, CLI entry point, benchmarks.
- R23 - vortex-identification presets: Green-Gauss gradient kernel,
  vorticity / Q-criterion / lambda-2 / helicity, VGRAD component library.
- R24 - quality gate & sustainability: ruff + mypy + benchmark thresholds,
  `scripts/check.py` one-click gate, GitHub Actions CI.
- R25 - presentation depth: off-screen PNG sequence + MP4/ogv video,
  2x2 multi-viewport + camera linking, embedded Python console.
- R26 - performance depth: plane-cut result LRU cache, multi-zone CGNS
  parallel parse (process pool + thread-pool fallback), tightened benchmark
  thresholds.
- R27 - GUI viewport wiring: multi-viewport layout (single/2x2) +
  shared-camera camera linking in the Draw Window (headless-safe wiring).
- R28 - data depth: CGNS variable-level lazy materialization
  (lazy open + on-demand field read, HDF5 paths).
- R29 - GUI depth: independent multi-viewport cameras
  (Linked/Independent mode switch + Standard Views four-view).
- R30 - parity close-out + attribute-level audit (0 gap, machine matrix)
- R31 - beyond-scPOST: streaming (memory-bounded) CGNS reads
  (GUI Streaming toggle + budget-bounded windowed reader.)
  (bounded-LRU window/tile materialisation; offset total-by-side).
- R32 - beyond-scPOST: web presentation + collaboration automation
  (headless HTTP streaming data service + self-contained HTML report +
  AutomationSession + serve HTTP-RPC, zero new deps).
- R33 - beyond-scPOST: batch export/render pipeline (bounded memory)
  (BatchJob/BatchExporter over streaming datasets: JSON sample / full-field
  raw float64 tile-stream export + manifest + CLI & GUI "Export Batch…").
- R34 - beyond-scPOST: session recording / sequence render pipeline
  (SessionTimeline over a CGNS cycle sequence + SessionRecorder → per-cycle
  PNG/JSON + manifest; record_sequence + encode_video + GUI "Record Sequence…").
- R35 - beyond-scPOST: generic object-keyframe Timeline engine + per-keyframe
  render pipeline (KeyframeTrack/Timeline with hold/linear/Catmull-Rom spline
  over arbitrary object properties; Scene.set_timeline drives them in animate;
  render_timeline → per-frame PNG/JSON + manifest, headless-safe).
- R36 - beyond-scPOST: multi-cycle temporal report (Sequence → offline report
  bundle): walk a session sequence with streaming handles, scan every field in
  bounded tiles, and emit report.html + data.csv + manifest.json (+ optional
  base64 PNG thumbnails) via a pure headless-testable assembly.
- R37 - beyond-scPOST: probe-grid memoization + generic local data cursor
  (get_probe_grid caches build_ugrid once per dataset with a bounded LRU,
  shared by Point/Information/pick probes; probe_polydata does pure-NumPy
  nearest local value extraction from any rendered polydata, no vtkCutter).
- R38 - beyond-scPOST: monitoring-point field-value time traces (probe history)
  (resolve_probe_nodes maps points to nearest nodes once, then time_trace walks
  a session sequence and, per cycle and per field, keeps only the chosen node
  rows via bounded iter_tiles → per-field/probe series JSON + manifest + CLI,
  headless-safe and no CGNS/vtk dependencies).
- R39 - beyond-scPOST: cycle-by-cycle sequence comparison (baseline vs scenario)
  (field_tile_difference diffs two streaming handles tile-by-tile via
  iter_tiles/read_window for RMSE/MAE/max/relative-L2; compare_sequences walks
  two timelines in lockstep → per-cycle field metrics + rolling summary, then
  per-field JSON + summary.json + CLI, bounded memory, no CGNS/vtk deps).
