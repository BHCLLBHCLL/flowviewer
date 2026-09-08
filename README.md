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
- R52 - beyond-scPOST: modal spatial map (inverse-distance-weighted IDW spread of a
  chosen probe-level mode onto the full mesh: idw_field pins exact weights at the
  probe nodes and blends nearest neighbour weights onto every other vertex with
  bounded-memory chunked distances; mode_weights sources a POD mode or the DMD
  dominant mode's per-probe participation; build_mode_field returns the node field
  + coverage stats; write_mode_field emits <field>_mode<k>.json +
  <field>_mode<k>_nodes.csv (node,x,y,z,weight) + summary.json;
  CLI fv.modalfield, pure NumPy, headless, no CGNS/vtk deps).
- R53 - beyond-scPOST: full-field modal reconstruction at a cycle (reconstructs the
  whole mesh node field at any cycle from the dominant POD modes as
  recon = mean_field + Σ mode_shapeⱼ·coeffⱼ(cycle), lifting each mode's per-probe weight
  onto the domain via R52's idw_field; mean_field spreads the probe temporal means onto
  the mesh; recon_quality verifies the reconstruction at the probe nodes where the IDW
  ties are exact (≈0 RMSE with all modes); write_reconfield emits <field>_recon_cycle<N>.json
  + <field>_recon_nodes.csv (node,x,y,z,recon) + <field>_recon_quality.json + summary.json;
  CLI fv.reconfield, pure NumPy, headless, no CGNS/vtk deps).
- R54 - beyond-scPOST: spatial analysis HTML report (R51's structural report in the
  spatial domain: digests the temporal-mean field, the top POD mode shape fields and the
  full-field reconstruction at a cycle into one dependency-free page — summary, mean-field
  stats, per-mode energy bars + shape range, reconstruction snapshot + captured energy and
  probe-node reconstruction quality; build_spatial_report fuses R53 mean_field/
  reconstruct_field/recon_quality with R52 build_mode_field; render_html emits the
  self-contained page; write_spatial_report writes <field>_spatial.html +
  <field>_spatial.json + summary.json; CLI fv.spatialreport, pure NumPy, headless,
  no CGNS/vtk deps).
- R55 - beyond-scPOST: full-field DMD modal reconstruction (R50's dynamic counterpart
  to R53's POD reconstruction): re-derives DMD's full complex pieces (λᵢ, αᵢ, per-probe
  φᵢ) and rebuilds the whole node field at any cycle as recon = Re(Σ αᵢ·Qᵢ·λᵢ^cycle)
  where Qᵢ is the complex IDW mode shape (Re/Im spread separately by R52 idw_field, so
  probe nodes tie back exactly to the per-probe DMD value); the DC eigenmode carries the
  mean, so no explicit mean re-add; captured_var/RMSE from the full snapshot matrix;
  write_dmdrecon emits <field>_dmdrecon_cycle<N>.json + _nodes.csv + _quality.json +
  summary.json; CLI fv.dmdrecon, pure NumPy, headless, no CGNS/vtk deps).
- R56 - beyond-scPOST: spatial report gains the DMD POD/DMD pair (R54's deferred
  "DMD into report": with --dmd the whole-mesh page now also digests the top DMD
  mode-shape magnitude fields (R55 build_dmd_mode_field: freq/growth/amplitude/
  energy_share + range), the DMD full-field reconstruction (R55) and DMD quality,
  rendered as DMD modes / DMD reconstruction / DMD quality sections; DMD is opt-in
  (default off keeps R54 output byte-identical); CLI fv.spatialreport --dmd
  --dmd-top N, pure NumPy, headless, no CGNS/vtk deps).
- R57 - beyond-scPOST: spatial reconstruction animation over a cycle window + a
  temporal/unsteadiness report. Rebuilds the full node field frame-by-frame across
  a cycle window (pod via R53 reconstruct_field, dmd via R55 reconstruct_field_dmd),
  gives a coarse HTML <canvas> field-preheat browser (binned_preview, standard JS,
  no vtk/image libs) and per-vertex mean/std/range/rms unsteadiness; write_anim_report
  emits <field>_anim.html + <field>_anim.json (frame stats + cycle_idx + unsteadiness,
  no full-node frames) + <field>_anim_nodes.csv + summary.json; CLI fv.spatialanim
  <trace> <verts> --source pod|dmd --cycles A:B --frames --k --p --neighbors
  --preview --out, pure NumPy, headless, no CGNS/vtk deps).
- R58 - beyond-scPOST: spatio-temporal spectral maps lifting the probe-level
  frequency family (R41/R44) onto the whole reconstructed field. FFTs the R57
  frame sequence per vertex and maps time-mean / fluctuation RMS + intensity
  (rms/|mean|) / dominant frequency as four HTML <canvas> heatmaps (binned
  previews, standard JS, no vtk/image libs); write_spectral_report emits
  <field>_spectral.html + <field>_spectral.json (stats + previews + dt/nyquist,
  no (N,) node arrays) + <field>_spectral_nodes.csv + summary.json; CLI
  fv.spectralmap <trace> <verts> --source pod|dmd --cycles A:B --dt --frames
  --k --p --neighbors --preview --out, pure NumPy, headless, no CGNS/vtk deps).
- R59 - beyond-scPOST: spatio-temporal co-oscillation (coherence) field map, the
  spatial-correlation counterpart of R58 (single-point spectra). Coheres every
  vertex's reconstructed frame sequence against a reference probe via Welch
  magnitude-squared coherence (R42 semantics, vectorised over vertex chunks) and
  maps peak coherence / its frequency / mean coherence / cross-phase as four HTML
  <canvas> heatmaps; write_coherence_report emits <field>_coherence.html +
  <field>_coherence.json (stats + previews + meta, no (N,) node arrays) +
  <field>_coherence_nodes.csv + summary.json; CLI fv.coherencemap <trace> <verts>
  --ref <i> --source pod|dmd --cycles A:B --nperseg --dt --frames --k --p
  --neighbors --preview --out, pure NumPy, headless, no CGNS/vtk deps).
- R60 - beyond-scPOST: spatio-temporal spectral-evolution (non-stationarity)
  field map, the time-varying counterpart of R58's time-averaged single-point
  spectra. Slides a short-time spectral window over every vertex's reconstructed
  frame sequence and maps spectral centroid / bandwidth / centroid drift
  (>0 = non-stationary) / energy intermittency as four HTML <canvas> heatmaps;
  write_spectevol_report emits <field>_spectevol.html + <field>_spectevol.json
  (stats + previews + meta, no (N,) node arrays) + <field>_spectevol_nodes.csv +
  summary.json; CLI fv.spectevol <trace> <verts> --source pod|dmd --cycles A:B
  --nperseg --dt --frames --k --p --neighbors --preview --out, pure NumPy,
  headless, no CGNS/vtk deps).
- R61 - beyond-scPOST: unified spectral-field console (Field Console), folding the
  three R58/R59/R60 field reports into one single-page dependency-free HTML page:
  summary header + tab bar (Spectral / Coherence / Evolution) switching which panel
  of four HTML <canvas> heatmaps + per-map stats is shown, all painted by one shared
  stdin-free inline JS; build_console re-runs build_spectral_report /
  build_coherence_report / build_spectevol_report (panels selectable, ref_probe and
  nperseg forwarded only where relevant) and keeps meta/stats/previews per panel
  (no (N,) node arrays); write_console emits <field>_fieldconsole.html +
  <field>_fieldconsole.json (JSON-safe previews) + summary.json; CLI fv.fieldconsole
  <trace> <verts> --panels --ref --source pod|dmd --cycles A:B --dt --frames --k
  --p --neighbors --preview --out, pure NumPy, headless, no CGNS/vtk deps).
- R62 - beyond-scPOST: spatial report folded with the field maps (spatial-frequency
  integration round). The R54 spatial report gains an opt-in ``--field`` that folds
  the R58 spectral / R59 coherence / R60 spectral-evolution field reports onto the
  same single-page HTML (each panel keeps its four <canvas> heatmaps + per-map
  stats + meta, no (N,) node arrays), so POD/DMD modal space and frequency-domain
  maps are comparable on one page; default output stays byte-identical to R54;
  build_spatial_report field_maps block re-runs build_spectral_report /
  build_coherence_report / build_spectevol_report (ref_probe/nperseg only where
  relevant) and render_html appends one shared-JS Field maps section (lazy imports
  avoid the spatialanim<->spatialreport cycle); write_spatial_report emits
  <field>_spatial.html + <field>_spatial.json (slim field_maps, JSON-safe previews)
  + summary.json (field_maps flag + field_source); CLI fv.spatialreport --field
  --source pod|dmd --cycles A:B --step --frames --preview --nperseg --dt --ref,
  pure NumPy, headless, no CGNS/vtk deps).
- R64 - GUI integration of the analysis-report family: wires the standalone
  R54/R55/R58-R62 HTML report generators into the GUI — an ``Analysis`` menu
  lists the report kinds (fv.gui.analysis registers spectral/coherence/evolution/
  console/spatial_pod/spatial_dmd/spatial_field as ReportKind; report_menu orders
  them; prepare_verts extracts an (N,3) vertex array with an empty fallback;
  run_report dispatches to write_* and returns the HTML path, forwarding only the
  kwargs each writer accepts), and a dockable ReportPanel (fv.gui.reportview)
  renders the result inline via QWebEngineView when PyQt5.QtWebEngineWidgets is
  importable, falling back to an "Open in browser" button otherwise. Pure logic
  stays headless-testable; only main.py wires the menu + on_analysis_report.
- R65 - Analysis data-source selection: makes the R64 Analysis menu actually
  functional by bridging the applied Time Series to an R38-style trace artifact
  (fv.gui.analysis adds field_names / artifact_from_timeseries / artifact_summary;
  artifact_from_timeseries maps each named series to a probe carrying its
  coordinate + values plus the object cycles, and artifact_summary gives a
  status-bar one-liner). main.py adds "Set Analysis Data Source..." / "Clear
  Analysis Data Source" menu items plus the handlers (set_analysis_artifact,
  _set_analysis_source, on_analysis_report, _analysis_out_dir, _open_report), so
  clicking an Analysis report no longer raises - the menu now has a real data
  source. Pure logic stays headless-testable.
- R66 - Analysis report export + recent history: makes the R64/R65 report
  results persist instead of vanishing in the temp dir. fv.gui.analysis adds
  copy_report(src, dest_dir, name=None) (pure, headless-testable) which copies
  a self-contained single-file HTML report to a destination directory
  (creating it as needed, returning None for a missing source). The ReportPanel
  gains a Save As... button (QFileDialog -> copy_report) and a Recent reports
  combo fed by the open(path) history, so generated reports can be re-opened
  with one click. main.py adds an "Export Report..." menu item routing to the
  panel's export(). Pure logic stays headless-testable.
- R67 - Analysis parameter panel: surfaces the run_report tunable defaults as a
  per-kind GUI dialog instead of hiding them in code. fv.gui.analysis adds a
  Param frozen dataclass (key/label/type/default/choices/min/max/help) plus pure
  schema helpers report_params/default_params/normalize_params/param_summary/
  _coerce (type-driven coercions int/float/bool/choice/str/str_opt/tuple, JSON-
  serializable so a snapshot round-trips through the dialog) and expands
  run_report to take every previously-defaulted kw (dt/cycles/step/frames/
  ref_probe/nperseg/blocksize/top/p/neighbors/preview/source/dmd/field/panels/
  field_name/cycle/dmd_top), forwarding only what each writer accepts. New
  fv.gui.paramdialog.ParamDialog renders the schema as Qt widgets (QFormLayout
  walking report_params). main.py wires a "Report Options..." menu item
  (QInputDialog kind pick -> ParamDialog -> normalize -> store per-kind snapshot
  -> status shows param_summary) and on_analysis_report normalizes stored params,
  falls back to _analysis_dt for dt, and forwards **params. Pure logic stays
  headless-testable.
- R68 - Named parameter presets: persists the per-kind parameter snapshot so a
  tuned config can be recalled next session instead of resetting to defaults.
  fv.gui.analysis adds default_preset_path() (-> ~/.flowviewer/
  analysis_presets.json) and a PresetStore class ({kind: {name: normalized}}
  layout) with save/load/delete/names/kinds/clear; save normalizes via
  normalize_params (unknown kind raises, only known/coerced keys stored), load
  returns a deep copy or None for missing/invalid, and every mutation is flushed
  to the JSON file when a path is set (path=None => pure in-memory for tests).
  fv.gui.paramdialog.ParamDialog gains an injectable store (defaulting to the
  per-user JSON path) plus a Presets row (QComboBox + Load/Save/Delete): Save
  names result_params() via QInputDialog, Load back-fills the widgets
  (_apply_params/_set_value handle both QSpinBox/QLineEdit int-float widgets),
  Delete removes the chosen preset. main.py builds one shared _preset_store and
  passes it into the dialog, and the status line appends the preset count for
  the kind. Pure logic stays headless-testable.

- R69 - Running presets: lets a saved preset be run directly from the Analysis
  menu instead of re-editing Report Options each time. fv.gui.analysis adds
  preset_menu(store, kind=None) (-> [(kind, name, title)], listing every kind
  that holds presets in registry order with names sorted, empty when none, and
  ValueError for an unknown kind) and run_preset(kind, name, verts, artifact,
  out_dir, store=None, *, dt=None) which loads the (kind, name) snapshot and
  forwards it verbatim to run_report(**params) (honoring per-kind source/panels/
  field_name, falling back dt when the snapshot's is None, returning None for a
  missing preset or None artifact). main.py adds a "Presets" submenu under
  Analysis, refilled on aboutToShow from preset_menu(self._preset_store), with a
  disabled "(no saved presets)" placeholder when empty, each item labelled
  "{name}  —  {title}" and routed to the new _run_selected_preset handler (which
  mirrors on_analysis_report: ensure a data source, prepare verts, run_preset with
  the shared store and _analysis_dt, then open the report). Pure logic stays
  headless-testable.
- R70 - Sharing presets: lets a saved preset set be exported to a JSON file or
  imported from one, so tuned configs can be shared or backed up across machines
  (closing the create -> save -> run -> share loop). fv.gui.analysis adds
  PresetStore.dump(kinds=None) (a deep, JSON-serializable copy, optionally
  filtered by report kind), PresetStore.export(dest, kinds=None) (writes the dump
  to dest as UTF-8 pretty JSON, returning the Path or None when the store is
  empty) and PresetStore.import_(src, *, kinds=None, overwrite=False) (loads from
  a JSON file path or an already-parsed dict, normalizing every params dict via
  normalize_params, keeping an existing preset on a name conflict when
  overwrite=False / replacing it when True, skipping unknown kinds, non-dict
  buckets and non-dict params, returning a {kind: [imported_names]} summary). Two
  module-level helpers export_presets(store, dest, kinds=None) and
  import_presets(store, src, *, kinds=None, overwrite=False) wrap the methods.
  main.py adds "Import Presets..." and "Export Presets..." under Analysis
  (QFileDialog to pick a source/destination) wired to _import_presets
  (merge, no overwrite; status shows the count imported) and _export_presets
  (dump every preset; status shows the written path). Pure logic stays
  headless-testable.
- R71 - Batch report generation: lets every Analysis report kind be produced at
  once and folded into a single index page, so the user no longer has to click
  the seven report items one at a time. fv.gui.analysis adds run_reports(verts,
  artifact, out_dir, *, kinds=None, params=None, dt=None) (runs several kinds in
  registry order, dropping unknown kinds, merging a per-kind params overlay that
  is normalised via normalize_params, filling a missing snapshot dt from the
  supplied dt, omitting kinds that produce no output and returning {} early when
  artifact is None), write_report_index(paths, out_dir, title=...) (writes an
  index.html linking each generated report by its basename, HTML-escaping both
  the report titles and the file names) and run_report_bundle(verts, artifact,
  out_dir, *, kinds=None, params=None, dt=None) (a convenience that runs the
  batch and writes the index page only when at least one report is produced).
  main.py adds a "Run All Reports..." item under Analysis wired to
  _run_all_reports, which ensures a data source, prepares verts, normalises the
  current per-kind params, runs the bundle and opens the generated index in the
  report pane. Pure logic stays headless-testable.
- R72 - Batch report packaging: lets a run-all batch be packed into one
  shareable .zip and reopened later, so the batch no longer lives only in a
  scratch temp dir that is overwritten on the next run. fv.gui.analysis adds
  report_index_html(paths, title=...) (the shared index-page HTML builder),
  export_report_bundle(paths, zip_path, title=...) (writes each report and an
  index.html into a single .zip, returning the Path or None when there is
  nothing readable to pack) and open_report_bundle(zip_path, out_dir) (safely
  extracts the archive into out_dir -- skipping directory entries and any
  entry that would escape out_dir via an absolute path or a '..' segment -- and
  returns the reopened index.html path, or None when the archive is missing,
  corrupt, or has no index). write_report_index now reuses report_index_html.
  main.py adds "Export Bundle..." and "Open Bundle..." under Analysis wired to
  _export_report_bundle (zip the last run-all batch to a chosen .zip) and
  _open_report_bundle (choose a .zip and reopen it in the report pane);
  _run_all_reports records the latest batch for export. Pure logic stays
  headless-testable.
- R73 - Named batch projects: lets the current batch ("which report kinds", plus
  the per-kind Report Options snapshot) be saved under a name and re-run from
  the Analysis menu in one click, so a tuned subset no longer has to be
  re-picked and re-edited each time. fv.gui.analysis adds project_store_path()
  (a per-user JSON file under ~/.flowviewer), the ProjectStore class (an
  optional on-disk store whose {name: {kinds, params}} records are normalised
  -- unknown kinds dropped, params coerced and pruned to the selected kinds --
  and flushed on every mutation; path=None keeps it in-memory for tests),
  project_menu(store) (ordered (name, kinds) pairs for the menu) and
  run_project(store, name, verts, artifact, out_dir, *, dt=None) (loads a
  project and forwards its kinds+params to run_report_bundle, returning None
  when the project is missing). main.py adds a "Projects" submenu under
  Analysis wired to _save_project (name the current batch kinds+params), a
  refreshed list that runs _run_selected_project(name), and _delete_project;
  _run_selected_project reuses run_project and opens the batch index in the
  report pane. Pure logic stays headless-testable.
- R74 - Headless report CLI: exposes the R64-R73 batch / bundle / project
  machinery at a terminal and to CI, so a report workflow can be scripted
  instead of clicked. fv/report.py adds a ``python -m fv.report`` entry point
  that reads a JSON input ``{"verts": [[x, y, z], ...], "artifact": {...}}``
  (a bare artifact file is also accepted, verts then defaulting to empty) and
  emits HTML reports to an output directory, optionally an index page and a
  shareable zip. load_input / load_params parse the input and per-kind params
  overlay; run orchestrates run_report_bundle (or run_project when --project is
  given) and prints a machine-readable manifest to stdout
  ``{"out_dir", "reports", "index", "zip", "count"}`` with paths relative to the
  output directory; main is the argparse entry (--all / -k repeatable /
  --project / -p params / -z zip / -t title / -d dt). No PyQt is imported, so it
  stays headless. main.py adds "Export Analysis Data Source..." under Analysis,
  dumping the current verts+artifact as a CLI-ready JSON so the same workload
  can be re-run from the terminal.
- R75 - Import analysis data source: lets a CLI-ready analysis-source JSON (the
  exact payload R74's CLI consumes) be re-opened in the GUI, so an exported
  workload can be resumed or inspected without re-picking the trace.
  fv.gui.analysis adds load_analysis_source(path) (delegating to
  fv.report.load_input so the GUI import and the headless CLI parser stay in
  lock-step; returns (verts, artifact), coercing top-level verts to an (N, 3)
  array and treating the object itself as artifact when there is no "artifact"
  key). main.py adds an Analysis menu "Import Analysis Data Source..." wired to
  _import_analysis_source (pick a .json, load it, store the imported verts in
  self._analysis_verts, set the artifact via set_analysis_artifact and report
  the imported vert count); reports now route their verts through
  _analysis_source_verts, which prefers imported verts and falls back to the
  dataset.
- R76 - Raw-sequence report input: lets the ``fv.report`` CLI skip the pre-built
  data-source JSON and build ``(verts, artifact)`` straight from a CGNS result
  sequence, completing the headless "result files → reports" loop. With
  ``--source`` the first positional argument becomes a raw sequence (directory,
  first file, or explicit list) sampled at the repeatable ``--probe x,y,z`` /
  ``--probes-file`` monitoring points for the ``--field`` (or the first field
  the first cycle exposes); verts come from the first cycle's mesh. fv/report.py
  adds build_source (which reuses fv.session.SessionTimeline + fv.trace.time_trace
  to produce a single-field artifact identical to the GUI export) plus the
  --source/--probe/--probes-file/--field/--budget-mb flags; run dispatches to
  build_source when config["source"] is set, otherwise the JSON path is
  unchanged. A missing monitoring point exits 2; the produced artifact is fully
  compatible with every report kind.
- R77 - GUI sequence data source: exposes the R76 raw-sequence source to the GUI
  so a report family can be built straight from a CGNS result sequence without a
  Time Series object (R65) or an exported JSON (R75). fv/report.py lifts the
  probe parsing out of the CLI-only `_load_probes` into a shared public
  parse_probe_points(probes, probes_file=None); fv/gui/analysis.py adds
  sequence_source(paths, probes, field=None, *, budget_mb=64) which delegates to
  fv.report.build_source so the GUI and the headless CLI stay in lock-step; a new
  fv/gui/sequencedialog.py SequenceSourceDialog collects the sequence path,
  monitoring-point lines (or a probes file), an optional field, and a per-cycle
  memory budget; and main.py adds an Analysis menu "Set Sequence Data Source..."
  wired to _set_sequence_source, which parses the points via parse_probe_points,
  calls sequence_source, and stores the resulting verts/artifact as the Analysis
  data source.
- R78 - Self-contained analysis projects: R73's named projects store
  {kinds, params} but not the Analysis data source, so re-running a saved batch
  meant manually re-establishing a Time Series, an imported JSON, or a sequence
  source. R78 makes projects self-contained: a save also records a
  JSON-serialisable data-source descriptor (sequence_desc for a raw sequence,
  json_desc for an imported JSON), and resolve_source rebuilds (verts, artifact)
  from that descriptor when the project is run — degrading gracefully to the live
  source when the descriptor is absent (a Time Series), unknown, or unreadable.
  fv/gui/analysis.py adds sequence_desc/json_desc/resolve_source and extends
  ProjectStore.save(..., source=None) to persist the descriptor (deep-copied);
  main.py tracks the active descriptor via _analysis_source_desc (cleared on a
  Time Series source, set on an import or a sequence source) and rewrites
  _run_selected_project to resolve the project's own source first, falling back
  to the live source for legacy R73 projects.

- R79 - Headless CLI honours a self-contained project's source: R78 made saved
  projects self-contained, but only the GUI re-materialised the data-source
  descriptor; fv.report --project still required a separate input and ignored the
  stored descriptor, so the same batch could not be re-run headlessly. R79 closes
  the loop in fv/report.py: run resolves the project's own source first via
  resolve_source (falling back to the external --source / JSON pair for a legacy
  R73 project, an absent/unknown descriptor, or a timeseries marker), loading it
  lazily only when needed so a self-contained descriptor is never shadowed by a
  dead input; and main lets the positional INPUT be omitted for a self-contained
  project (with new gates that reject --source without an INPUT and an INPUT-less
  run without --project). Usage example and tests (tests/test_r79_selfcontained_cli.py)
  cover the self-contained JSON/sequence paths, source-wins-over-input precedence,
  and the CLI error gates.

- R80 - Headless project-management lifecycle: a named project could only be
  created in the GUI (ProjectStore), so creating / listing / deleting one could
  not be scripted. R80 lets fv.report drive the whole lifecycle: --save-project
  NAME records the current --source sequence or JSON input as a new
  self-contained project (persisting the same sequence_desc / json_desc
  data-source descriptor the GUI tracks), --list-projects prints every saved
  project as JSON (with a self_contained flag), and --delete-project NAME
  removes one. fv/report.py adds a shared _all_kinds() helper plus the three
  action flags, handled before any report generation; invalid inputs (no input
  and no source, --source without an INPUT, --source without monitoring points)
  exit 2, and deleting an unknown project exits 1. Tests
  (tests/test_r80_project_cli.py) cover the JSON/sequence save descriptors, the
  list/delete output, the CLI error gates, and a save-then-run round trip.

- R81 - Headless CLI recalls named parameter presets: the GUI (R68-R70) can save
  and re-run a per-kind named preset through PresetStore, but the headless CLI
  could only overlay raw --params JSON and never referenced a preset by name —
  the last report-family GUI/CLI asymmetry. R81 closes it in fv/report.py:
  --preset KIND:NAME (repeatable) loads that kind's normalised preset snapshot
  from the per-user PresetStore and merges it under the raw --params overlay
  (so --params can still tweak a preset) via a new _merge_preset_params helper,
  while --list-presets [KIND] prints every stored preset (or one kind's) as
  JSON for discovery. A malformed KIND:NAME, an unknown report kind, or a
  missing preset exits 2, mirroring the R80 management gates. Tests
  (tests/test_r81_preset_cli.py) cover empty/one-kind/all-kind list output, the
  preset-merge and preset-plus-params-override paths, repeatable --preset across
  distinct kinds, and the three error gates.

- R82 - Headless HTTP service shares report-family bundles: R32 (fv/web/server.py)
  only serves the R31 streaming CGNS surface (info/open/fields/render); the report
  family (R64-R81) produces self-contained HTML bundles plus an index.html and a
  zip in fv/gui/analysis.py but offers no way to browse or share them over HTTP.
  R82 closes the gap in fv/web/report_server.py: serve_bundle mounts a bundle
  directory (with or without an index.html) on a stdlib ThreadingHTTPServer — no
  GUI, no third-party dependencies — serving the bundle index page (/ and
  /index.html), a JSON report listing (/api/list), an on-demand archive download
  (/api/bundle.zip), and every single report by basename with path-traversal
  protection. fv.web re-exports serve_bundle / ReportBundleServer. Tests
  (tests/test_r82_report_web.py) cover index/list/file serving, the traversal
  403, the zip download, the generated fallback index for an index-less bundle,
  and the empty-bundle 404.
- R83 - AutomationSession publishes a report bundle (unified collaboration
  surface): R32's AutomationSession.streaming serve() shares only live windowed
  data; R82's serve_bundle was a standalone entry with no automation-facing
  hook. R83 raises it onto the session in fv/automation.py as
  AutomationSession.serve_bundle(bundle_dir, port=0, host="127.0.0.1") -> int,
  which starts an R82 ReportBundleServer in a background thread (no stream open
  required) and tracks it so close() tears down both the streaming and the
  bundle server. Tests (tests/test_r83_automation_bundle.py) cover bundle
  publishing /api/list and report serving, the no-stream path, the non-directory
  ValueError, the close() lifecycle, and the unchanged R32 serve() guard.
- R84 - headless CLI --serve (one-shot generate + publish): R82 served a report
  bundle over HTTP and R83 raised it onto AutomationSession, but the fv.report
  CLI's run() still had no HTTP entry once it produced a bundle. R84 adds
  --serve (plus --serve-port / --serve-host) so python -m fv.report in.json -o
  reports --serve renders the bundle and then blocks serving it; the manifest is
  printed first and augmented with a serve object carrying the bound port and
  url. fv/report.py gains _serve_info(out_dir, port, host) -> (info, server),
  and main() starts the R82 ReportBundleServer before blocking on
  serve_forever, stopping on Ctrl-C. Tests (tests/test_r84_serve_cli.py) cover
  the live /api/list serve, host/port reflection, the non-directory ValueError,
  and the main() --serve manifest augmentation plus its exit-1 failure path.
- R85 - GUI publishes the current analysis report bundle over HTTP: R82 gave the
  report family a headless HTTP server and R83/R84 raised it onto
  AutomationSession / the fv.report CLI, but the GUI itself could not share the
  bundle it had just generated. R85 adds analysis.serve_report_bundle
  (fv/gui/analysis.py) that starts the R82 server on a background daemon thread
  and returns (info, server, thread) so the Analysis menu's "Publish Bundle over
  HTTP…" action can show the URL and a "Stop Publishing…" action (plus closeEvent
  cleanup) can shut it down. fv/gui/main.py tracks _bundle_server / _bundle_thread
  / _bundle_info for the active publish lifecycle. Tests (tests/test_r85_gui_publish.py)
  cover the live serve /api/list, host/port reflection, the non-directory
  ValueError, and the clean shutdown/recycle path.
- R86 - Web presentation: bundle metadata dashboard + /api/meta: R82 served a
  bundle as a bare link list and R83/R84/R85 only mounted or published it — the
  served index page carried no report metadata. R86 deepens fv/web/report_server.py:
  report_meta() augments every report with its own <title>, byte size and mtime,
  dashboard_html() renders / as a live dashboard (per-report label + title + size
  + modified time) while keeping the report_index_html <li><a> anchors so
  bundle_listings still parses it, and a new /api/meta JSON endpoint exposes the
  same metadata machine-readably (/index.html stays the untouched bundle index).
  fv.web re-exports dashboard_html / report_meta. Tests (tests/test_r86_report_dashboard.py)
  cover meta ordering and the scan fallback, missing-report degradation, the
  dashboard HTML (and its bundle_listings-parsability), and the / dashboard vs
  /index.html vs /api/meta routes with and without an index.
- R87 - Web presentation: bundle overview summary + /api/summary: R86 gave each
  report its own metadata but exposed no bundle-level aggregate. R87 deepens
  fv/web/report_server.py: bundle_summary() aggregates the per-report metadata
  into a report count / total size / generated span (oldest–newest mtimes),
  dashboard_html() renders that summary as a <p class="summary"> block above the
  list (keeping the <li class="meta"> captions and <li><a> anchors), /api/meta
  now carries the same "summary" field, and a new /api/summary JSON endpoint
  serves the overview alone. Empty / all-degenerate bundles degrade to a clean
  zero overview. fv.web re-exports bundle_summary. Tests
  (tests/test_r87_bundle_summary.py) cover the aggregate, empty-degradation,
  missing-report degradation, the dashboard summary block (and its
  bundle_listings-parsability), plus the /api/summary and extended /api/meta
  routes.
- R88 - Web presentation: bundle query / sort / filter layer: R86/R87 made the
  served / a rich overview but always in a fixed, full index order — a growing
  bundle could not be searched or re-ranked. R88 deepens fv/web/report_server.py:
  query_reports() filters a report_meta row list by a case-insensitive substring
  (q matching name / label / title) and re-orders it by sort/dir (text keys
  name/label/title, numeric keys size/mtime; unknown sort key raises ValueError;
  no args returns the index order), dashboard_html() gains keyword q/sort/dir
  and its summary block tracks the visible subset, and both /?q=&sort=&dir= and
  /api/meta?q=&sort=&dir= route through it (invalid sort key returns a 400 JSON
  error). fv.web re-exports query_reports. Tests
  (tests/test_r88_bundle_query.py) cover the pure helper (filter, text/numeric
  sort, unknown-key ValueError, index-order default), the queryable dashboard
  (and its bundle_listings-parsability), plus the / and /api/meta query-string
  routes and the 400 path.
- R89 - Web presentation: bundle pagination / windowing layer: R86-R88 made /
  rich, searchable and re-rankable, yet still rendered the *whole* (matched) set
  on one page — a large bundle had no paged browsing. R89 deepens
  fv/web/report_server.py: window_reports() slices a report_meta row list by
  limit/offset (limit=None returns everything for R86-R88 compatibility;
  negative limit/offset raise ValueError), dashboard_html() gains keyword
  limit/offset and renders a pager <p class="pagination"> (showing range +
  previous/next links that preserve q/sort/dir via _pager_href) while the summary
  block always reflects the full matched set, and both /?limit=&offset= and
  /api/meta?limit=&offset= window their output (/api/meta adds total/offset/limit
  fields; invalid pagination params return a 400 JSON error). fv.web re-exports
  window_reports. Tests (tests/test_r89_bundle_pagination.py) cover the pure
  windowing helper (no-limit identity, slicing, input immutability, negative
  rejection, q-composition), the paginated dashboard (range/links/href-preserving
  q/sort/dir, no-pager-when-no-limit, bundle_listings-parsability), plus the
  / and /api/meta paginated routes and the invalid-pagination 400 path.
- R90 - Web presentation: interactive dashboard controls: R86-R89 made /
  searchable, re-rankable and paged, but those abilities (q/sort/dir/limit) were
  only reachable by hand-editing the URL — a browser user had no search box,
  dropdowns or button, so they were undiscoverable. R90 makes / interactive with
  no JavaScript: dashboard_html() emits a dependency-free GET form
  (<form class="dashboard-controls">) whose q (search input) / sort / dir / limit
  (three <select>s) controls reflect the current query (via _option) and, on
  submit, drive the same report_server routes; a hostile q is HTML-escaped in
  the echoed value. fv/web/report_server.py adds _SORT_LABELS, _PAGE_SIZES,
  _option and _controls_html. Tests (tests/test_r90_dashboard_controls.py) cover
  the pure form builder (defaults index/asc/All, current-query reflection, all
  sort keys/page sizes listed, hostile-q escaping), the control-bearing dashboard
  (form always embedded, applies the query, coexists with the pager, stays
  bundle_listings-parsable), and the live /?q=&sort=&dir=&limit= interaction.
- R91 - Web presentation: single-report detail view + detail JSON API: R86-R90
  made / an interactive, paged dashboard, but clicking a report just served the
  raw .html file — there was no in-context detail page carrying that report's
  metadata, a back-to-dashboard link, or previous/next navigation inside the
  current ordering, and no machine-readable single-report endpoint. R91 deepens
  fv/web/report_server.py: report_detail() returns one metadata row (plus its
  0-based index in the index-order listing) or None when the name is unknown or
  escapes the bundle; _detail_nav() yields the (prev, next) neighbours within an
  ordered list; report_detail_html() renders the detail page (label <h1>, crumb
  trail with a back-to-dashboard link preserving q/sort/dir and the match count,
  a metadata caption of title/size/mtime, an "open report" link, and previous/
  next navigation within the current q/sort/dir ordering — None on unknown or
  escape so the caller can 404). Routes: /api/report?name=… -> _route_report_api
  (JSON; 400 on a missing name, 404 on unknown), /report/<name> ->
  _route_report_detail (HTML detail page preserving q/sort/dir; 404 on unknown).
  fv.web re-exports report_detail / report_detail_html. Tests
  (tests/test_r91_report_detail.py) cover the pure detail row / nav / html and
  the live /api/report and /report/<name> routes.
- R92 - Web presentation: report content preview embedded in the detail page:
  R91's /report/<name> only noted the raw file via a relative "open report"
  link, so the report body was never visible in context and that link resolved
  back to the page itself. R92 deepens fv/web/report_server.py: report_content()
  returns a report's raw HTML text (path-safe, None on unknown / escape /
  unreadable) as the machine counterpart to report_detail(); report_detail_html()
  embeds the report inline (an <iframe class="report-frame"> referencing the raw
  report at its absolute path) so a user pages through a bundle with previous /
  next and reads each report without clicking out, the "open report" link now
  targets the absolute raw path, and the preview is skipped when the report is
  unreadable. fv.web re-exports report_content. Tests
  (tests/test_r92_report_detail_preview.py) cover the pure content helper, the
  embedded preview (and its absence for an unreadable report), the navigation
  preserved alongside it, and the live /report/<name> and /<report>.html routes
  backing the iframe.
- R93 - Web presentation: content-aware search + machine-readable report content
  endpoint: R86-R92 made / an interactive, paged, detail-able dashboard, but the
  search/q box only matched report *titles* (metadata), never the report body, and
  there was no machine-readable route to fetch a single report's content — a user
  searching for a term that only appears inside a report could never find it. R93
  deepens fv/web/report_server.py: query_reports() gains an opt-in content mode —
  when content=True and a bundle_dir is given, q also matches report body text
  (read lazily via report_content(); body missing/unreadable treated as a
  non-match, and without a bundle_dir the content branch is skipped so the
  metadata-only path is unchanged); a _param_flag() handler helper parses
  content=1; the content flag is threaded through _controls_html(), dashboard_html(),
  _dashboard_href() and _detail_href() (so a content-mode query survives the form,
  pager, back-links and previous/next navigation); report_detail_html() and the /
  dashboard and /api/meta routes all honour it; and a new /api/report/content?name=…
  -> _route_report_content route returns {ok, bundle, title, name, content} JSON
  (400 on a missing name, 404 on unknown). The dashboard emits a dependency-free
  <label class="content-toggle"> checkbox so a browser user can switch on
  content search with no JavaScript. Tests (tests/test_r93_report_content_query.py)
  cover the content-mode query matcher, the content checkbox, the content-aware
  dashboard / detail pages, the preserved content flag through the pager and
  navigation, and the live /api/report/content, /api/meta?content=1, /?content=1
  and /report/<name>?content=1 routes.
