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
- R40 - beyond-scPOST: monitoring-point sequence-vs-sequence comparison
  (trace_report reuses R38's pre-bound nodes so A/B read the same node indices;
  point_compare aligns two sequences' probe histories on common cycles → per
  probe: a/b/diff series + mean/max abs, max relative; per-field JSON +
  summary.json + CLI, bounded memory, no CGNS/vtk deps).
- R41 - beyond-scPOST: monitoring-point frequency/power-spectrum analysis
  (mean_dt robust sampling interval + analyze_series FFT periodogram on a probe
  series → DC-detrended power spectrum, dominant/peak frequency & Nyquist;
  spectrum_from_trace reads R38 trace JSON; per-probe PSD CSV + summary.json +
  CLI, pure NumPy, headless, no CGNS/vtk deps).
- R42 - beyond-scPOST: relating two monitoring series — lagged
  cross-correlation + Welch coherence (cross_correlate normalized lagged
  Pearson correlation → best (lag, rho) relative offset between two probes, or
  baseline vs perturb at one probe; coherence segment-averaged magnitude-squared
  coherence → shared-oscillation peak frequency; relate_probes reads R38 trace
  JSON; per-pair JSON + summary.json + CLI, pure NumPy, headless, no CGNS/vtk
  deps).
- R43 - beyond-scPOST: monitoring-point time-frequency spectrogram
  (sliding-window rfft spectrogram → S matrix + per-window peak_freq showing how
  the dominant frequency evolves across a transient/mode-swap run; freq_evolution
  collapses to fastest/slowest/range/drift; spectrogram_from_trace reads R38
  trace JSON and infers dt from the cycle axis; per-probe JSON + summary.json +
  CLI, pure NumPy, headless, no CGNS/vtk deps).
- R44 - beyond-scPOST: spectral mode detection + energy decomposition
  (spectral_peaks lists a probe's significant oscillation modes as local maxima
  above a prominence floor — fundamental + harmonics / vortex-shedding order;
  energy_shares gives each mode's share of the DC-excluded fluctuation energy
  and the top-k cumulative share; turbulent_intensity offers std/mean;
  modes_from_spectrum consumes an R41 analyze_series dict; per-field JSON +
  summary.json + CLI, pure NumPy, headless, no CGNS/vtk deps).
- R45 - beyond-scPOST: one-command per-probe monitoring analysis bundle
  (analyze_probe fuses spectrum R41 + spectrogram trend R43 + mode decomposition
  R44 + turbulent intensity into one "monitoring card"; analyze_monitor extends
  to every probe; write_monitor emits a compact per-probe CSV table + bundle
  JSON + summary.json; CLI fv.monitor, pure NumPy reusing the tested spectral
  family, headless, no CGNS/vtk deps).
- R46 - beyond-scPOST: render the monitoring analysis as a self-contained HTML
  report (build_report digests a trace artifact; render_html emits a
  dependency-free page with a cross-probe summary table, per-probe cards and
  inline sqrt-compressed power-spectrum bars; write_monitor_report writes
  <field>_monitor.html + summary.json; CLI fv.monreport, styled-html + inline
  bars only, no plotting lib, headless-testable).
- R47 - beyond-scPOST: cross-probe correlation matrix + probe clustering
  (history_matrix builds the cycles×probes matrix; pairwise_correlation gives a
  NaN-safe Pearson matrix with per-pair gap handling; top_pairs lists the
  strongest links; cluster_probes does single-linkage clustering on |rho|≥
  threshold so probes that co-oscillate group together; write_probecorr emits
  matrix JSON + clusters JSON + pairs CSV + summary.json; CLI fv.probecorr,
  pure NumPy reading R38 trace artifacts, headless, no CGNS/vtk deps).
- R48 - beyond-scPOST: POD (Proper Orthogonal Decomposition) of monitoring-point
  data (snapshot_matrix builds the centered (n_probes, n_cycles) matrix with
  NaN imputation; pod_decompose factors it with the SVD → spatial modes
  (probe weightings) + time coefficients, ranked by fluctuation energy with
  effective-rank trimming; pod_summary adds the leading mode's dominant
  frequency via R41; write_pod emits pod JSON + modes CSV + summary.json;
  CLI fv.pod, pure NumPy, headless, no CGNS/vtk deps).
- R49 - beyond-scPOST: POD low-rank reconstruction + probe filtering
  (pod_reconstruct rebuilds the data from the top-k modes as Σ mode⊗coeff and
  reports captured variance + per-probe/total RMSE; modes_to_energy tells how
  many modes reach a target energy share; filter_probe returns a denoised
  single-probe history with its mean restored; write_recon emits recon JSON +
  rmse CSV + summary.json; CLI fv.podfilter, pure NumPy reusing R48, headless,
  no CGNS/vtk deps).
- R50 - beyond-scPOST: DMD (Dynamic Mode Decomposition) of monitoring-point
  data (time-delay/Hankel embedding lifts each probe series into delayed copies
  so pure tones expose rank-2; exact projected DMD on the embedded matrix then
  gives each mode a frequency and growth/damping rate via ω=ln(λ)/dt, ranked by
  reconstructed energy, with the dominant oscillating mode reported and DC
  excluded; modes carry per-probe complex participation; write_dmd emits dmd
  JSON + modes CSV + summary.json; CLI fv.dmd, pure NumPy, headless, no CGNS/vtk
  deps).
- R51 - beyond-scPOST: structural / modal analysis HTML report (one dependency-free
  page tying R47–R50 together: build_structure_report digests an R38 trace
  artifact into the correlation matrix + coherent groups (R47), POD energy
  spectrum (R48) and DMD modes table (R50); render_html emits a self-contained
  HTML document with an inline red→white→blue correlation heat-map, coherent
  groups, strongest pairs, POD energy bars and a DMD modes table; write_structure_report
  writes <field>_struct.html + summary.json; CLI fv.structreport, pure NumPy,
  headless, no CGNS/vtk deps).
