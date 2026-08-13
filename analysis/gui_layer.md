# FlowViewer GUI Layer Analysis

Scope: fv_gui.py, fv/gui/*, tests, and a full pytest run.
Date: session run — no source code was modified.

---

## 1. Main window layout, menus, toolbar

### Layout (FlowViewer._build_central, main.py:152)
Nested QSplitters, scPOST-style Layout of Windows:

- **main** (horizontal, 300/1300)
  - **left** = DrawSplitter (vertical, stretch 3/2):
    - PaneFrame("Control Window", ObjectTree)
    - PropertyHost (tiled settings, lower half)
    - splitter handle carries the scPOST **Draw (mallet)** button -> draw_requested -> _on_draw_clicked commits the active panel and redraws (replaces per-panel Apply buttons)
  - **right** = QSplitter (vertical, 640/180):
    - PaneFrame("Draw Window", QVTKRenderWindowInteractor) (VTK renderer, near-white gradient background, parallel projection; headless fallback = placeholder QLabel when enable_3d=False)
    - **bottom** = QSplitter (horizontal, 400/600): PaneFrame("Message", MessageWindow) | PaneFrame("Timeline Window", TimelineWindow)
- **Status bar** (main.py:228): permanent (x,y,z) coord label (updated by VTK mouse move), mode label, operation label, cycle label + transient showMessage.

### Menus (_build_menus, main.py:246) — every item and its wiring
"Real" = connected to a concrete handler; "stub" = falls through to self._nyi(name) (main.py:242, logs "[name] not yet implemented").

**File**: Open… (on_open_dialog, real — native QFileDialog); Save Status (on_save_status, real — JSON .sta); Print (on_print, real); Export PNG… (on_export_png, real); Exit (close, real).

**Create** (from _CREATE_MENU, main.py:37): Surface (real), Plane (real), **Cylinder (stub)**, **Circle (stub)**, Point (real), Volume (real), Isosurface (real), Streamline (real), **Vector (stub)**, Colorbar (real), **Light (stub — "Create light")**, **Text (stub)**, **Graph (stub)**.

**Display**: Redraw (real), Show All (real), Hide All (real).

**View**: Fit (real, shortcut F); YZ(X)/XZ(Y)/XY(Z) (on_plane_view, real); Iso Metric (real); **Compare (partial — logs "split-screen, TBD", no actual rendering)**; Message Window / Timeline Window / Status Bar (checkable toggles, real).

**Option**: Mouse 1-Button (trackball), 2-Button (rubber), 3-Button (trackball) — all real; Environment Settings (real — EnvironmentDialog.exec_()); Diagnostics (real — dumps state to message log).

**Toolbar** menu: File/Create/Display/View/Mouse/Option checkable toggles (_toggle_toolbar, real).

**Help**: About flowviewer (real QMessageBox).

### Toolbars (_build_toolbars, main.py:338) — actions
- **tb_file**: Open (real), Save (real), Print (real)
- **tb_create**: Surface, Plane, Iso, Stream, Volume, Colorbar, Point (real, via _create_object); **Vector (stub — maps to None kind)**
- **tb_display**: Contour (real — rebuilds scene with contour colours), Show (real), Redraw (real)
- **tb_view**: YZ/XZ/XY/Fit/Reset (real)
- **tb_mouse**: Trackball (real), Rubber (real — sets vtkInteractorStyleRubberBandZoom), **Select (inert — logs "Select (not yet wired)" and falls back to trackball style)**
- **tb_option**: Option (real), **Camera (stub)**, **Unit (stub)**

**Menu stub count: 8** (Create: Cylinder, Circle, Vector, Light, Text, Graph; Option toolbar: Camera, Unit). Additional _nyi call sites in tree activation: Unit settings, Option, Camera, Draw Window settings (main.py:762–770).

---

## 2. Object tree (ObjectTree, panes.py:105)

- **Startup tree** (build_startup_tree): root "POST application" with children "Unit" (unchecked), "Draw Window : DisplayList mode", "Message Window", "Timeline Window" (all checkable), and "Global Objects" -> Option, Camera (checkable).
- **After open** (load_main): inserts the field-file Main node (icon "project") before Global Objects; children from MainObject; adds "Light (1)" under Global Objects (icon "display").
- **Kinds rendered** (labels + _object_kinds map): main, surface, plane, particle, isosurface, streamline, volume, colorbar, point, light. Icons via AppIcons (_icon_for_kind: surface->"surface", plane->"plane_xy", particle->"point", isosurface, streamline, volume, vector, colorbar, point; fallback "project").
- **Eye/hand**: every object row is Qt.ItemIsUserCheckable; check state column 0 -> itemChanged -> visibility_changed(name, on) -> _on_tree_visibility (main.py:720): toggles scene layer ("grid"+"surface" for surface, else the kind's layer), sets obj.visible, refreshes GL; special-cases Draw Window/Message/Timeline pane visibility and ignores Option/Camera/Unit/Light (1).
- **Activation to dialogs**: single-click selection (_on_selection_changed) and double-click (_on_double_clicked) emit object_activated(kind, label) for the 8 _RENDERABLE_KINDS -> _on_object_activated -> property_host.show_object(kind, obj, field_file, siblings) (tiled panel, no modal). Double-click of non-renderable names ("Unit", "Option", "Camera", "Draw Window…") -> _nyi. Double-click also emits item_activated_name.
- **Create wiring**: _create_object(kind) (main.py:820) instantiates SurfaceObject/PlaneObject/PointObject/VolumeObject/IsosurfaceObject/StreamlineObject/ColorbarObject with unique labels, appends to main, rebuilds scene, refreshes tree, opens the panel. None-kind -> _nyi; vector/light kinds not in makers -> _nyi.
- **PropertyHost** (panes.py:402): QStackedWidget hosting one panel at a time; pin (P) / hide (x) buttons on the panel title bar; unpinned panels close after Draw; apply_now() -> apply_to(obj) + applied signal -> _on_property_applied -> incremental Scene.apply_to_object when scene already built.

---

## 3. Property dialogs inventory (tabs and key fields per tab; wiring)

All are tiled ObjectSettingsPanel (non-modal) with a full apply_to(obj) write-back and a pin/hide bar. "Wired" = panel's controls are read back into the object on Draw/apply.

### SurfaceDialog (object_dialogs.py:226) — 8 tabs
1. **Region**: search+filter tree (Registered Surfaces / Hidden Surfaces / MATs Boundary), Easy Mode radios (Original/Standard/Name Tree/Select one). Wired.
2. **MAT**: check-tree of material numbers + Select All/None (empty = all). Wired.
3. **Volume Region**: check-tree of volume regions. Wired.
4. **Contour**: Display + scalar var combo, Paint Front/Back, Transparent. Wired.
5. **Vector**: Display + vector var. Wired.
6. **Mesh**: Front/Back/Transparent, Color, Thickness. Wired.
7. **Trim**: "Trim all"/"All" buttons, X/Y/Z min-max checkboxes. Wired.
8. **Scalar Integration**: Integrate checkbox + Calculate projected area. Wired (flags only — no run button).

### PlaneDialog (object_dialogs.py:489) — 16 tabs
1. **Coordinate**: axis radios; coordinate spin + slider (bounds from mesh); Operate Object; Arbitrary (point+normal triplets); Pick/Hide buttons; Rotate sub-tab (XYZ/Arb, X±/Y±/Z±/+/− with angle); Usage Guide checkbox + Horz/Vert/Axis/Line-Paint/Color buttons (persist immediately without Draw). Wired (rotation math live).
2. **MAT**: check-tree. Wired.
3. **Volume Region**: check-tree. Wired.
4. **Contour**: Display var; Paint/Luster/Water/Transparent; Line: Contour line/Transparent/Broken; Mono color + swatch; Value; Thickness. Wired.
5. **Vector**: Display var; Location (Uniform/Actual/Center/Nodes); Space u/v; Type (Simple/Standard/Triangle/3D/Animation); Constant length; Transparent; Mono color; Contour Color; Projection; Scale Length/Thickness; Arrow Angle/Size. Wired.
6. **Mesh**: Boundary (Auto/Broken/Color/Transparent); Mesh (Transparent/Block/Color/Thickness); Paint (+color/Luster/Water); Subline (External frame/Automatic/Display location). Wired.
7. **Oil Flow**: Display + var; Transparent/Thickness/Space u/v/Length; draw type; Integration Method (Runge-Kutta/Euler); Steps/Accuracy. Wired (renderer honours it).
8. **Trim**: "Trimmed by" object check-tree (siblings passed in by PropertyHost); X/Y/Z min–max spins with "(off)" special value -> None. Wired.
9. **Automove**: Enable; Method (Line/Sin/Cos/Rotation/Custom Path — swaps standard/path param groups); Starting plane, Reference plane, Rotational axis triplets; Angle/Offset; Loop/Ready/Frames; custom path: CSV file, Show Path, sync-at-time, Path Distance/Start/End. Wired; playback animated by timeline (scene.animate).
10. **Clip**: Clip plane object; X/Y range; Display clipping region. Wired.
11. **Pick**: Scalar/Vector rows; IJK, Cycle Graph; Show all vars; Show numbers; Color; Shape (Sphere/Cube/Point); Line/Solid colours. Wired.
12. **Scalar Integration**: integrate scalar + common block (Output-to-file + CSV + Browse; Include labels; Beep; **Integrate button runs the real cut integration** -> area/sum/average + optional CSV; Recalc after redraw; result label). Wired.
13. **Vector Integration**: same + normal flux (m²/s, m/s). Wired.
14. **Others**: Colorbar for contour/vector combos (auto only); Use model coordinate; "Do not display vector and contour simultaneously"; intersection-line flags (surface/isosurface/plane/undisplayed — **flags only, no execution**). Mostly wired flags.
15. **Texture**: Use texture mapping; file + Browse; Method (Plane); Scale/Angle/Position u/v. Wired (renderer honours).
16. **Font**: Fonts (MS Gothic…Courier), Size, Float. Wired (persisted to object).

### ParticleDialog (object_dialogs.py:1777) — 7 tabs
1. **Scalar**: Display + var; Show scalar value; Mono color swatch; type Points/Sphere/Specify/Actual; Size (px); Transparent. Wired.
2. **Vector**: "Vectors on particle" + var; Show vector value. Wired.
3. **Intersection**: region list + New/Modify/Delete (regex-parsed cuboids); Display the regions. Wired.
4. **Trim**: Display Range (Particle No / Attribute No / Particle Size text); "Trimmed by" object check-tree. Wired.
5. **Others**: Use the model coordinate system. Wired.
6. **Font**: Fonts/Size/Float. Wired.
7. **Special**: Cloth/String; Variable generalization; **"Run checked functions"** (applies + rebuilds). Wired (conversion itself is renderer-side).

### IsosurfaceDialog (object_dialogs2.py:71) — 2 tabs
- **Contour**: Display + var; Auto (distribute values) / Values (comma list) / Auto number; Transparent; Mesh lines; Mono color + swatch. Wired.
- **Vector**: Display + vector base; Scale length. Wired.

### PointDialog (object_dialogs2.py:163) — 2 tabs
- **Coordinate**: X/Y/Z; Shape (Sphere/Cross/Plus); Size; Color; Transparent. Wired.
- **Probe**: Scalar (+var), Vector (+var), Show values. Wired.

### StreamlineDialog (object_dialogs2.py:240) — 3 tabs
- **Seed**: Axis (Arbitrary/X/Y/Z); Coordinate; Center x/y/z; Density U/V. Wired.
- **Direction**: Vector field; Direction (Forward/Backward/Both); Method (Runge-Kutta/Euler); Length; Step size. Wired.
- **Display**: Color by scalar; Draw (Line/Triangle/Tube); Thickness; Transparent. Wired.

### VolumeDialog (object_dialogs2.py:366) — 2 tabs
- **Scalar**: Display + var; Opacity; Sampling; Draw type (Solid/Transparent/Sampled); Mono color + swatch. Wired.
- **Vector**: Display + vector base; Scale length. Wired.

### ColorbarDialog (object_dialogs2.py:449) — 1 tab
- **Colorbar**: Gradation (16–1024); Color map (Rainbow/Gray/Invert); Range (Auto/Fix); Min/Max; Orientation (Horizontal/Vertical). Wired.

**Total: 41 tabs** (8+16+7+2+2+3+2+1). No inert controls found inside panels; the only "inert" panel-level items are the Others-tab intersection flags and colorbar combo (auto only).

---

## 4. Timeline window (TimelineWindow, panes.py:522)

- **Modes**: Static / Cycle / Time radio group (mode()); mode_changed -> logged.
- **Slider**: enabled only when max > min; step_changed emitted on move when **Preview** checked.
- **Checkboxes**: Preview (default on, gates live reload), **Sync (inert — never read anywhere)**, Loop (used by play-back wrap).
- **Transport**: « ‹ ▶ ❚❚ › » buttons -> start/prev/play/pause/next/end (_jump/_nudge); play/pause emit signals -> main window _on_timeline_play/_on_timeline_pause (QTimer 250 ms, _play_tick steps through the FileSet cycle range, wraps if Loop else pauses).
- **Step/Ver/Time/Scale** line edits + **Set** button (_on_set -> set_step + emit). Ver/Scale/Time are display-only; Time is also updated by main window after loads.
- **Sync with data**: _on_timeline_step (main.py:860) — in Cycle/Time mode loads the sequence member (fileset.find(step) -> load_file), rebuilds scene, updates cycle/time label; automove planes animate via scene.animate(step).

---

## 5. Message window, status bar, options, tasks, dialogs

- **MessageWindow** (panes.py:72): read-only QPlainTextEdit, max 4000 blocks, timestamped log(msg, level) with autoscroll; write/clear helpers.
- **Status bar**: permanent widgets (coordinates, mode, operation, cycle) + transient messages from every action.
- **Options** (options.py): QSettings-backed typed get/set (bool/int/float coercion), keys last_dir, station_mode (unused by UI), env_gradient_bg, env_show_status, env_show_units; load_window/save_window restore geometry/state on start/close. Headless-safe in-memory fallback.
- **Tasks** (tasks.py): LoadWorker QObject run on a QThread (progress/finished/failed signals) with launch_load helper; **documented as "not yet wired to the UI"** — File→Open still loads synchronously.
- **Dialogs** (dialogs.py):
  - OpenDialog — full custom browser (Look-in, Up, Browse, file list + File-information preview via file_in_summary, "Files of type" combo over 17 scPOST filter groups, Import-options checkboxes -> OpenOptions). **Not wired to File→Open** (main window uses native QFileDialog). Options honoured on load: close_current (_close_current_files); accelerate_memory/read_faster only logged as deferred; magic/trimming/remote explicitly reserved (tip label + code).
  - EnvironmentDialog — Draw group: gradient background / status bar / units checkboxes; **only chk_status is applied on OK** (status bar visibility); gradient and units flags are inert.
  - qt_file_filters correctly joins filter groups with ;; ; file_in_summary gives node/element/variable preview for fld/ifld/fph/gph only (others: "(Preview for this type is not available yet.)").

---

## 6. Tests

### Per-file test functions
**tests/test_gui.py (66):** test_window_fph_layout, test_window_fld_layout, test_window_without_file, test_open_dialog_chrome, test_headless_imports, test_scene_fph_actor_build, test_scene_reset_with_string_placeholders, test_surface_plane_dialogs, test_tiled_property_host, test_trim_objects_populated, test_pin_transient_panel, test_particle_run_special, test_usage_click_persists, test_loader_registry_registered, test_cgns_detection_probe, test_open_dialog_is_loadable_honest, test_options_qsettings_headless, test_tasks_load_worker_sync, test_options_wired_into_window, test_create_object_menu_wiring, test_surface_dialog_all_tabs_and_filter, test_plane_dialog_all_tabs, test_particle_dialog_all_tabs, test_mat_filter_from_fld, test_plane_automove_roundtrip, test_scene_plane_pipeline_3d, test_automove_math_fph, test_plane_pick, test_plane_automove_animation, test_plane_render_pipeline_fph, test_plane_trim_coordinate_ranges, test_plane_trim_dialog_roundtrip, test_plane_vector_integration, test_plane_integration_csv_output, test_plane_oilflow_streamlines, test_plane_clip_region, test_plane_vector_extras, test_plane_colorbar_texture, test_plane_contour_extras, test_plane_volume_region_filter, test_plane_material_filter, test_plane_render_pipeline_fld, test_surface_render_pipeline_fph, test_surface_render_pipeline_fld, test_particle_render_pipeline_fph, test_particle_render_pipeline_scene, test_new_object_dialogs_tabs_and_apply, test_new_object_dialogs_with_field_file, test_isosurface_render_pipeline_fld, test_point_render_pipeline_fph, test_point_probe_fld_nearest_node, test_streamline_render_pipeline_fph, test_streamline_render_pipeline_fld, test_volume_render_pipeline_fph, test_colorbar_actor_and_lut, test_scene_build_renders_colorbar, test_scene_build_colorbar_headless, test_fileset_scan_sequence, test_fileset_scans_real_v3_sequence, test_timeline_cycle_switch, test_sta_save_load_roundtrip, test_snapshot_png_headless_returns_false, test_export_handlers_wired, test_menu_stubs_wired, test_environment_dialog, test_on_contour_display_headless.

**tests/test_scene_snapshot.py (5):** test_scene_snapshot_png, test_apply_to_object_incremental, test_apply_to_object_removes_old_actors, test_emt_alias, test_apply_to_object_headless_placeholder.

**tests/test_crdl.py (5):** test_core_primitives_exist, test_find_section_and_iter_data_blocks, test_read_i32_be, test_open_buffer_context, test_cell_count_from_data.

**tests/test_mesh_fld.py (4):** test_parse_fld_counts, test_parse_fld_bcs, test_parse_fld_fields, test_parse_fld_missing_file.

**tests/test_mesh_gph.py (4):** test_parse_fph_tr03_counts, test_parse_fph_regions, test_parse_fph_face_nodes_in_bounds, test_parse_ls_nodes_none_for_empty.

**Total: 84 test functions.**

### Pytest run (command: python -m pytest tests -q, workdir D:\training\cgns\flowviewer)
Result: **1 failed, 76 passed, 7 errors in 661.94s (0:11:01)** — 84 collected, **0 skipped** (all skipif conditions false: samples present, VTK/PyQt5 available).

**Failure (verbatim, tests/test_gui.py:674):**

    def test_plane_integration_csv_output(qapp):
        """Integration result written to CSV when Output-to-file checked (P1.3)."""
        ...
        with tempfile.TemporaryDirectory(
                dir=r"C:\Users\sdcll\AppData\Local\Temp\opencode") as td:
            out_csv = Path(td) / "integral.csv"
            d = PlaneDialog(obj, ff)
            d.int_scalar.setChecked(True)
            d.int_out.setChecked(True)
            d.int_csv.setText(str(out_csv))
            d._on_integrate()
    >       assert out_csv.exists()
    E       AssertionError: assert False
    E        +  where False = <bound method Path.exists of WindowsPath('C:/Users/sdcll/AppData/Local/Temp/opencode/tmpvs9lev4z/integral.csv')>()
    tests\test_gui.py:674: AssertionError

Followed by a PermissionError: [WinError 5] (access denied) while cleaning up the temp dir — the test hard-codes a temp dir outside the session workspace, so the write is denied by the file sandbox. **Environmental, not a code defect.**

**Errors (7, verbatim shape):** all at fixture setup (tmp_path) — PermissionError: [WinError 5] (access denied) on 'C:\Users\sdcll\AppData\Local\Temp\dsh-4QErXA\pytest-of-sdcll' from pathlib.Path.iterdir. Affected: test_fileset_scan_sequence, test_timeline_cycle_switch, test_sta_save_load_roundtrip, test_snapshot_png_headless_returns_false (test_gui.py) and test_scene_snapshot_png, test_apply_to_object_incremental, test_apply_to_object_removes_old_actors (test_scene_snapshot.py). All are pytest-basetemp sandbox denials outside the workspace — **environmental, not code defects**. Every GUI/logic test that could run passed (76/76 executed cleanly).

### Skipped/xfailed
None (0 skipped, 0 xfailed reported).

---

## 7. Gaps for scPOST parity

**Missing menus/dialogs (stubs or absent):**
- **Unit** — only a stub (_nyi("Unit settings")) from Option-toolbar and tree node; no dialog.
- **Camera** — stub (_nyi("Camera")); tree node present but no settings dialog (basic views via View menu only).
- **Variable Registration** — absent (no UI anywhere).
- **Graph object** — Create-menu stub; no Graph dialog/window.
- **Text object** — Create-menu stub; no Text dialog (plane Font tab exists but is per-plane).
- **Bitmap** — absent entirely.
- **Light** — Create-menu stub ("Create light"); "Light (1)" tree node exists but activation does nothing (kind not renderable) and visibility is ignored (_on_tree_visibility returns early); no light settings dialog.
- **Cylinder / Circle** — Create-menu stubs; no dialogs.
- **Mirror / Periodic copy** — absent.
- **Information dialog** — absent (only File-Open info preview and Diagnostics log dump).
- **Max/Min** — absent.
- **Time Series object** — absent (Time-series file filter exists in the Open dialog only).
- **Turbo** — absent.
- **VR** — absent.
- **VBS macro** — absent.
- **Vector create** — menu + toolbar stub (vector rendering exists only via Surface/Plane/Isosurface/Streamline tabs).

**Inert / partially wired controls:**
- Timeline **Sync** checkbox — never read; **Ver** and **Scale** edits display-only.
- **Compare view** — logs "split-screen, TBD"; no rendering.
- **Mouse Select mode** — logs "Select (not yet wired)" and reverts to trackball style.
- **Environment dialog** — gradient-background and units checkboxes not applied (only status-bar visibility); stored env_gradient_bg/env_show_units/station_mode unused by the UI.
- **OpenDialog import options** — accelerate_memory/read_faster logged "deferred"; magic/trimming/remote reserved; OpenDialog itself not wired to File→Open (native dialog used).
- **LoadWorker** — implemented but not wired; loads are synchronous.
- Plane **Others**-tab intersection-line flags and colorbar-for-contour/vector combos — persisted but not executed (auto only).
- Surface **Scalar Integration** tab — flags only, no execute button (Plane integration runs).
