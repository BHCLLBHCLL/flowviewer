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
