# Render Layer Analysis — fv/render (PyQt5 + VTK scPOST-like post-processor)

Scope: fv/render only (13 modules + __init__.py). No source modified.
Rough totals: ~3,900 lines; the heavyweight is plane.py (1,371) and scene.py (498).
No TODO / FIXME / NYI / _nyi markers exist anywhere in fv/render (grep-verified).

---

## 1. Per-file inventory

| File | Lines | Main functions (one-line purpose) | VTK classes used |
|---|---|---|---|
| scene.py | 498 | Scene — renderer+actor registry, layer visibility, build/apply_to_object, overlay, fit, pick, animate; numpy_to_vtk_array; _build_fph/fld_wireframe, _polydata_boundary | vtkRenderer, vtkTextActor, vtkPropPicker, vtkPlaneSource, vtkExtractEdges, vtkPolyDataMapper, vtkUnstructuredGrid, vtkHexahedron |
| surface.py | 370 | build_surface_polydata / _fph_ / _fld_ (boundary-face poly), attach_scalar / attach_vector (CellData FPH / PointData FLD), contour_actor, vector_actor, mesh_lines_actor, trim_surface, integrate_surface, build_surface_actors (entry) | vtkCellDataToPointData, vtkGlyph3D, vtkArrowSource, vtkExtractEdges, vtkClipPolyData, vtkPlane |
| plane.py | 1371 | build_ugrid (FPH vtkConvexPointSet / FLD hex), cell_filter_mask (MAT / Volume Region), attach_scalar/vector, cut_grid (vtkCutter), contour_actor, contour_value_actor (labels), contour_line_actor (isolines), colorbar_actor, texture_actor, vector_actor + _glyph_actor (4 locations, projection/constant-length), mesh_lines_actor, boundary_line_actor, subline_actor, trim_cut / clip_cut / clip_region_actor, pick_point, automove_coordinate, integrate_cut, write_integration_csv, build_plane_actors (entry) | vtkCutter, vtkPlane, vtkThreshold, vtkCellCenters, vtkProbeFilter, vtkGlyph3D (Line/Cone/Arrow sources), vtkExtractEdges, vtkClipPolyData, vtkContourFilter, vtkCleanPolyData, vtkLabeledDataMapper, vtkScalarBarActor, vtkTextureMapToPlane, vtkTransformTextureCoords, BMP/PNG/JPEG readers, vtkStreamTracer (via oilflow) |
| particle.py | 165 | build_particle_actors (parse LS_ParticlesPosition / VELP from raw bytes), _attach_scalar (velocity magnitude), _points_actor, _sphere_actor, _glyph_actor | vtkSphereSource, vtkGlyph3D, vtkArrowSource, vtkPolyDataMapper |
| isosurface.py | 142 | build_isosurface_actors (entry), _pipeline_grid (MAT/VolRegion), _to_points (cell→point), _contour_values (auto/explicit levels) | vtkCellDataToPointData, vtkContourFilter, vtkExtractEdges |
| point.py | 197 | build_point_actors (entry), _probe / _probe_fld (nearest-node) / _probe_vtk (vtkProbeFilter), _marker_actor, _label_actor, _format_lines | vtkGlyph3D, vtkSphereSource, vtkRegularPolygonSource, vtkLineSource, vtkProbeFilter, vtkTextActor |
| streamline.py | 302 | build_streamline_actors (entry), _euler_trace_fld (pure-numpy tracer), _seed_grid / _seed_centers, _render_actor (line/tube) | vtkStreamTracer (RK2/Euler, fwd/bwd/both), vtkCellDataToPointData, vtkTubeFilter, vtkPolyLine |
| volume.py | 129 | build_volume_actors (entry), _apply_sampling (decimation), _volume_actor (vtkDataSetMapper w/ opacity) | vtkDataSetMapper, vtkExtractUnstructuredGrid, vtkCellDataToPointData |
| vector.py | 132 | vector_glyph_actor (shared arrow glyphs over any polydata), _probe_vector, _glyph_scale | vtkGlyph3D, vtkArrowSource, vtkProbeFilter, vtkCellDataToPointData |
| oilflow.py | 142 | build_oilflow_actor (surface streamlines from plane seeds), _seed_grid | vtkStreamTracer, vtkCellDataToPointData, vtkTubeFilter |
| colorbar.py | 135 | ColorbarRegistry (process-global LUT), build_lut, colorbar_actor, apply_to_mapper | vtkLookupTable, vtkScalarBarActor |
| axes.py | 106 | axes_actor (triad), orientation_marker_widget (gnomon), plane_view_camera, iso_metric_camera | vtkAxesActor, vtkOrientationMarkerWidget |
| export.py | 218 | snapshot_png (window→PNG/JPEG/BMP/TIF), save_status / load_status (JSON .sta), print_scene (QPrinter or fallback PNG) | vtkWindowToImageFilter, vtkPNGWriter, vtkJPEGWriter, QtPrintSupport |

---

## 2. Per-object-kind rendering matrix

### Surface (SurfaceObject)
Pipeline: boundary-face polydata (FPH face table / FLD quads) → attach scalar (FPH CellData via owner-cell index, FLD PointData) → attach vector → trim_surface (X/Y/Z min/max boolean clip, 6× vtkClipPolyData) → contour_actor (vtkPolyDataMapper, auto point/cell scalar mode, front/back face culling, 0.5 opacity when transparent) → vector_actor (cell→point, vtkGlyph3D arrows, scale 0.05×diag×vector_scale_length) → mesh_lines_actor (vtkExtractEdges).

- Consumed: selected_regions, show_contour, contour_var, contour_paint_front, contour_paint_back, contour_transparent, show_vector, vector_var, vector_scale_length, show_mesh, mesh_color, mesh_thickness, mesh_transparent, trim_xmin/xmax/ymin/ymax/zmin/zmax.
- **Ignored**: region_mode, **display_mats, display_volume_regions** (MAT/Volume Region tabs never filtered for surfaces — cell_filter_mask is not applied), mesh_front, mesh_back, integrate_scalar, projected_area, font_name/font_float (font_size unused too), index/title (naming only). integrate_surface exists but is not called by build_surface_actors.

### Plane (PlaneObject) — richest pipeline
Pipeline: build_ugrid + cell_filter_mask → attach scalar → vtkCutter (1 cut) → trim_cut (coordinate-range clip) → clip_cut (X/Y region clip) → contour map / contour_line isolines / contour_value labels → optional per-other colorbar, texture, vectors, mesh, boundary line, subline frame, oil flow.

- Consumed: point, normal, axis/coordinate (only for scene fallback rectangle), display_mats, display_volume_regions, show_contour, contour_var, contour_transparent, contour_luster (specular 0.5/20), contour_water (specular 0.9/60 + opacity), contour_line, contour_line_transparent, contour_broken_line (stipple 0xF0F0), contour_mono_color/rgb, contour_value (labels), contour_thickness, font_size, colorbar_contour/vector, texture_enabled/file/scale/angle, show_vector, vector_var, vector_location, vector_space_u (**v ignored**), vector_type, vector_constant_length, vector_transparent, vector_mono_color, vector_projection (normal-component removal), vector_scale_length, vector_arrow_angle/size, show_mesh, mesh_display, mesh_color/thickness/transparent, boundary_line/color/transparent, subline_external, trim_xmin..zmax, clip_enabled/xmin/xmax/ymin/ymax/display_region, oilflow_* (all 11), automove_* (via Scene.animate), pick_scalar(_var)/pick_vector(_var).
- **Ignored**: arbitrary_enabled, arbitrary_normal_r/t/p (spherical arbitrary normal — renderer only reads point/normal), operate_object, rotate_axis/rotate_angle, usage_* (5), pick_mode/pick_hide, **contour_paint** (Paint flag not consulted), **vector_space_v, vector_contour_color, vector_scale_thickness**, **mesh_paint/paint_rgb, mesh_block, mesh_luster, mesh_water** (mesh luster/water completely absent), boundary_auto, boundary_broken_line, subline_automatic, subline_display_location, automove_standby, automove_frames (GUI passes fps), **automove_csv / show_path / path_sync / path_distance / path_start / path_end (Custom Path not implemented)**, **trim_objects** (trim against other objects not implemented — only coordinate ranges), integrate_scalar_enabled/vector_enabled/output_file/output_csv/include_labels/beep/recalc_redraw (functions exist but not wired into build), texture_method (only "Plane"), texture_pos_u/v, font_name/font_float, use_model_coord, no_vector_contour_simultaneous, inter_surface/isosurface/plane/undisplayed, pick_ijk, pick_cycle_graph, pick_show_all_vars, pick_show_numbers, pick_color_enabled, pick_shape, pick_line_color, pick_solid_color.

### Particle (ParticleObject)
Pipeline: parse_particles on raw file bytes → vtkPoints → PointId array → velocity-magnitude scalar → points (vtkPolyDataMapper, point size) or spheres (vtkSphereSource + vtkGlyph3D) → optional arrow glyphs.

- Consumed: particle_type, size_px, transparent, mono_color, show_vector.
- **Ignored**: show_scalar, scalar_var, show_scalar_value, **vector_var** (vectors hard-coded to the VELP section regardless), show_vector_value, intersection_regions/show_intersection_regions, display_particle_no/attribute_no/size (trimming), trim_objects, font_*, use_model_coord, special_cloth, special_variable_generalization.

### Isosurface (IsosurfaceObject)
Pipeline: build_ugrid + mask → attach scalar → vtkCellDataToPointData → vtkContourFilter (explicit contour_values or auto contour_number evenly spaced) → mapper (mono or scalar) → optional contour_line (vtkExtractEdges wireframe) → vector glyphs via vector.vector_glyph_actor.

- Consumed: contour_var, contour_number, contour_values, contour_transparent, contour_line, contour_mono_color/rgb, show_vector, vector_var, vector_scale_length.
- **Ignored**: **contour_auto, contour_value (single-value field ignored — only the list is used)**, vector_space, colorbar, font_*; show_contour itself is not gated (presence of contour_var decides). Model has no display_mats/display_volume_regions so no MAT filtering.

### Point (PointObject)
Pipeline: single point → marker (vtkGlyph3D × Sphere / 4-side RegularPolygon "Cross" / LineSource "Plus") → probe (FLD: numpy nearest-node — vtkProbeFilter deliberately avoided, "VTK heap corruption"; FPH: vtkProbeFilter) → vtkTextActor label (fixed top-left position, not anchored to the marker).

- Consumed: position, shape, size, color, transparent, probe_scalar(_var), probe_vector(_var), probe_show_values, font_size.
- **Ignored**: pick_show_numbers, font_name/font_float.

### Streamline (StreamlineObject)
Pipeline: build_ugrid (**cell_mask=None — no MAT/VolRegion**) → attach vector + color scalar → cell→point → plane seed grid → vtkStreamTracer (RK2 default / Euler; fwd/bwd/both; max propagation; initial step; max steps) → line or vtkTubeFilter (Triangle=3 sides, Tube=8) → mapper. FLD input bypasses VTK locators entirely with a **pure-numpy explicit-Euler nearest-node tracer**.

- Consumed: vector_var, color_var, seed_center/normal/axis/coordinate/density_u/density_v/spacing, direction, length, integration_method, max_steps, step_size, draw_type, mono_color, transparent, thickness.
- **Ignored**: **constant_length**, font_*; FLD path additionally drops "Both" direction (sign only), uses a different seed layout and step_size default (0.001 vs 0.01) than the FPH path; FLD nearest-node search is O(N) per step.

### Volume (VolumeObject)
Pipeline: build_ugrid (**cell_mask=None hard-coded** — MAT/Volume Region ignored) → _apply_sampling (vtkExtractUnstructuredGrid decimation when sampling>1) → attach scalar (CellData) → **vtkDataSetMapper with opacity** (Solid=1.0, Transparent/Sampled=0.35, ×scalar_opacity) → optional vector glyph overlay.

- Consumed: show_scalar, scalar_var, draw_type, transparent, scalar_opacity, scalar_mono_color/rgb, show_vector, vector_var, vector_scale_length, sampling.
- **Ignored**: display_mats, display_volume_regions, vector_space, font_*, colorbar.
- **No real volume rendering**: there is no vtkVolume / vtkSmartVolumeMapper / raycasting / transfer function anywhere — translucent cell geometry only.

### Colorbar (ColorbarObject)
Pipeline: ColorbarRegistry (process-global vtkLookupTable, Rainbow / Gray / Invert) → colorbar_actor (vtkScalarBarActor) added by Scene.build_global_colorbar; apply_to_mapper can point mappers at it but **no build path calls it**.

- Consumed: gradation, color_map (only "gray"/"invert" special-cased; "Spectrum" falls back to rainbow), range_mode (Fix → range), min/max, title, show_title, orientation, position, font_size.
- **Ignored**: font_name/font_float. Gap: contour mappers (plane/surface/isosurface) use per-mapper default LUTs — the shared global LUT/range is not actually wired to object colors.

### Axes / camera
axes_actor (vtkAxesActor triad, magenta/green/blue Cradle gnomon colors), orientation_marker_widget (screen corner), plane_view_camera (XY/XZ/YZ ±) and iso_metric_camera ((1,1,1) diagonal) — applied in fv/gui/main.py (lines ~618–642), not in scene.py.

---

## 3. Scene management (scene.py)

- **Layer naming**: every object's actors are added under "<kind>:<subkey>" layers — grid; surface:contour|vector|mesh; plane:contour|contour_line|contour_value|vector|mesh|boundary|subline|colorbar|texture|clip_region|oilflow; particle:particle|vector; isosurface:contour|contour_line|vector; point:point|label; streamline:streamline; volume:scalar|vector; colorbar. Fallback: plane with no contour gets a semi-transparent vtkPlaneSource rect in layer "plane"; empty surface shares the grid wireframe.
- **Eye/hand visibility**: **no eye/hand (left/right) concept exists** in the render layer (grep-verified). Visibility is per-object (obj.visible honored in build/apply_to_object) and per-layer via set_layer_visible; actor visibility is toggled but actors stay in the renderer.
- **apply_to_object**: incremental single-object rebuild — remove_object_actors(obj) walks the _actor_object registry (vtkActor→(kind,obj)) to detach and drop exactly that object's actors from renderer + layer registry, then re-dispatchs via _dispatch_object. Falls back to full build if never rendered. remove_object_actors works in headless mode too (placeholder strings).
- **Global colorbar registry**: build_global_colorbar creates the vtkScalarBarActor (horizontal, 7 labels), sets the global LUT range in Fix mode, and registers it under layer "colorbar"; ColorbarRegistry.lut() lazily builds a Rainbow LUT (invalidated by gradation change).
- **Camera / view**: only fit() (ResetCamera) lives in Scene; plane-view/iso-view camera setups are in fv/gui/main.py using axes helpers. Scene constructor enables ParallelProjectionOn + gradient background (scPOST Draw Window style).
- **Overlay text**: set_overlay drives one vtkTextActor (Courier, top-left, File/Cycle/Time), text cached in _overlay_text for headless.
- **Headless (enable_3d=False)**: Scene.__init__(enable_3d=False) (or missing VTK) skips the renderer; every builder records only placeholder **strings** (e.g. "surface_1", "wireframe") in the layer registry so tests can assert actor names/layers; add_actor, remove_object_actors, set_layer_visible all no-op on strings; snapshot_png returns False.
- **Animation**: Scene.animate(t, fps) (driven from fv/gui/main.py ~line 891) finds automove planes, computes point/normal via automove_coordinate (Line/Sin/Cos interpolation, Rotation via Rodrigues about axis; loop + frame normalization), mutates obj.point/normal, removes all plane:* layers (_remove_layer_prefix), and rebuilds the plane's actors in place.
- **Pick**: pick_actor(x,y) → vtkPropPicker + _actor_object registry → (world point, (kind,obj)); pick_point in plane.py probes scalar/vector honoring Pick-tab flags.

---

## 4. Export (export.py)

- **snapshot_png(renderer_or_window, filename)**: vtkWindowToImageFilter (RGB) → vtkPNGWriter (default) or vtkJPEGWriter for .jpg/.jpeg; also accepts .bmp/.tif extension but writes PNG content; returns False headless/on error.
- **print_scene**: renders to a temp PNG via snapshot, then QPrinter + QPrintDialog (PyQt5 QtPrintSupport); without QtPrintSupport it keeps the PNG fallback (export_view.png / _print_buffer.png).
- **STA save/load**: JSON-based flowviewer-sta v1. save_status writes MainObject display_name + each child's **declared dataclass fields** (_json_safe: tuples→{"__tuple__":true,...}, Path→str). load_status reconstructs child dataclass instances for kinds surface/plane/particle/isosurface/point/streamline/volume/light/colorbar, keeping only fields still declared (new fields default). Round-trips: all object settings incl. automove, oilflow, texture, pick, integration options. **Does not round-trip**: MainObject path/cycle/time/has_particles (load returns only the child list), camera state, overlay text, per-layer visibility.

---

## 5. Gaps & observations for scPOST parity

1. **Volume rendering — no real raycasting.** VolumeObject renders with vtkDataSetMapper + cell opacity; no vtkVolume / vtkSmartVolumeMapper, no transfer functions, no gradient lighting. MAT/Volume-Region filtering is skipped (cell_mask=None).
2. **Lighting / luster / water.** LightObject is serialized in STA but **never rendered** (no vtkLight anywhere). Luster/water are approximated only on plane contours via specular props; mesh_luster / mesh_water / surface luster/water are ignored. No shadows or per-object lighting effects.
3. **Texture mapping.** Only the plane cut supports it (vtkTextureMapToPlane + scale/rotate); texture_method (only "Plane"), texture_pos_u/v, and texture on surfaces/volume are missing.
4. **Contour labels.** Only plane has value labels (vtkLabeledDataMapper); surface and isosurface contours have none; contour_paint flag unused; global colorbar LUT is not applied to object mappers (apply_to_mapper never called) — Fix-mode ranges affect only the bar itself.
5. **Clip planes.** Only coordinate-range trim/clip (plane, surface toggles) and the X/Y clip region exist; trim_objects (trim against other objects) is not implemented; no arbitrary clip planes.
6. **Animation.** Automove works for Line/Sin/Cos/Rotation via full plane rebuild per frame, but **Custom Path (automove_csv / automove_show_path / path_sync / …) is unimplemented**; automove_standby/frames semantics partial.
7. **Oil flow quality.** Seeds span the whole-domain bounding box (not the cut extent), base spacing is a fixed max(u,v)/40; default oilflow_steps=10 yields very short traces; only Euler/RK2, no scalar coloring, no error control; "accuracy" only scales the initial step.
8. **Streamline integration quality.** FPH path properly converts cell-centred data to points for vtkStreamTracer; **FLD falls back to a naive nearest-node explicit Euler tracer** (O(N) per step, no "Both" direction, differing defaults, no interpolation — a workaround for VTK heap corruption on vtkHexahedron locators). constant_length ignored; seed_spacing semantics differ between the two paths.
9. **Vector glyph density.** Plane: vector_space_v ignored (u only), and "Uniform" vs "Actual" both use the same whole-bbox grid (the Actual clip is only nominal via probing). Surface/isosurface/volume glyphs have no density control (all nodes / all probe points); vector_scale_thickness, vector_contour_color ignored.
10. **Boundary / subline.** Boundary line = plane∩boundary polydata (FLD exterior faces reconstructed by hex-face counting — Python Counter over all cells each rebuild); subline is only the external frame box; subline_display_location, subline_automatic, boundary_auto, boundary_broken_line ignored.
11. **Per-object tab dead-ends.** Surface MAT/Volume-Region tabs ignored; particle scalar/vector selection hard-coded (velocity magnitude / VELP); volume MAT/VolRegion ignored; point labels are screen-fixed (0.02, 0.84) not anchored to the marker; integration functions (integrate_cut, integrate_surface, write_integration_csv) exist but are not reachable from any build path (GUI-only, if wired).
12. **Font/UI.** Only font_size is honored; font_name / font_float ignored everywhere; pick-tab extras (ijk, cycle graph, show-all-vars, marker shape/colors) ignored.
13. **Performance.** FPH polyhedra are built as vtkConvexPointSet with per-cell Python loops (LS_Links traversal) and FLD boundary faces are found by Counter over all hex faces each rebuild — both O(cells) in Python; every Scene.animate frame redoes the whole ugrid + cut.
