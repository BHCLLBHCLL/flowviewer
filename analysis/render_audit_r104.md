# RENDER layer audit — fv/render (36 pipelines) — evidence-based

Scope: fv/render/*.py (31 modules, ~12.1k lines) + object model (fv/model/objects.py) + dialogs
(fv/gui/object_dialogs.py = dl, object_dialogs2.py = d2). Env: py3.12, VTK 9.6.2, numpy 1.26.
Method: source reading plus runtime probes (offscreen VTK renders, pixel diffs, API probes) on
D:\training\cgns\examples\tr03_9.fph (221,786 pts / 63,697 polyhedra) and synthetic grids.
[V] = reproduced by me at runtime; (m) = measured by a delegated deep-read of that module.
Project docs were not trusted. Companion file: analysis/render_inert_params.md.

================================================================================
1. PER-PIPELINE COMPLETENESS (implemented / approximation / stub / dead)
================================================================================

## plane — fv/render/plane.py (1649 ln) — deepest pipeline
IMPLEMENTED: FPH polyhedron grid with owner+neighbour shells :170-239; FLD/CGNS cell build :251-299;
vtkCutter slice :391-413 + LRU cut cache :374-413; contour map :433-468; isolines :490-513; colorbar
:532-562; texture map :565-620; vtkGlyph3D arrows :643-769; mesh/boundary/subline :882-1047;
trim/limit/clip :1049-1230; automove :1316-1410; scalar+vector integration :1417-1479; CSV :1482.
APPROXIMATION: trim_by_objects :1049-1077 (docstring :1055 admits "approximates"; it keeps the OUTSIDE
of the sibling although :1054 claims "inside" — vtkClipPolyData + vtkImplicitPolyDataDistance with
InsideOutOff keeps distance>0 = outside (m)); subline_actor :1001-1047 draws only the model bbox frame
(:1016-1042) although :1002 claims display-location marks, and the boundary cut computed at :1009-1015
is discarded; automove Custom Path is a nearest-row lookup, not interpolation :1369.
DEAD (no caller repo-wide): make_plane_actor :416, cut_vector_array :772, pick_point :1249 (tests only),
filter_ugrid_cells :78, _slice_field_array :107, _cell_centers :302.
VERIFIED DEFECTS: cut-cache key :378-383 ignores attached arrays, so switching contour_var reuses a cut
without the new array [V: same object returned, GetArray("TURK") is None, mapper SelectColorArray("TURK")
with range (0,1) :450/:521]; glyphs never set scale-by-vector :685-694 so vtkGlyph3D defaults to
BY_SCALAR and arrow length encodes the contour scalar; Uniform and Actual are one branch :755-761 seeded
from the VOLUME bbox :845-869 [V: 343/800 sample points probe-valid]; clip_region_actor draws in the
plane-local frame :1186-1215 while clip_cut clips in world X/Y :1155-1183; mesh lines are extracted from
the triangulated cut :882-889 + :407 (~36% diagonals, m); texture_angle is applied as a UV translation
:608-611 [V: vtkTransformTextureCoords exposes no rotation API]; integrate_cut uses only vertex ids
0,1,2 per cell :1443-1447 [V: unit quad area 0.5 instead of 1.0]; the cell-type table covers 6 VTK codes
and everything else silently becomes HEXAHEDRON :242-296.

## surface — fv/render/surface.py (501 ln)
IMPLEMENTED: FPH/FLD boundary polydata :39-124, scalar/vector attach :154-204, contour :206-230, glyph
arrows :233-268, mesh edges :271-288.
STUB/DEAD: integrate_surface :320-326 has no production caller; bump_surface_actor :334-395 has NO caller
and reads obj.bump_var / obj.bump_factor :349,:377 which exist in no model and no dialog — the R21 bump
feature is unreachable and always falls back to contour_var with 0.05 (its only exercise is
tests/test_r21.py:96-122 with SimpleNamespace).
BROKEN: trim_surface :291-313 ignores the trim VALUES (uses the polydata's own bbox :299-304) and inverts
the kept half-space for min bounds [V: trim_xmin=0.0 + trim_xmax=100.0 on tr03_9 -> 0 cells;
build_surface_actors then returns {} and scene.py:810-817 silently shows the grid wireframe].
QUALITY: glyphs :252-261 lack scale-by-vector; _vertex_normals :399-431 is correct but a 95x slower
hand-rolled Newell loop than vtkPolyDataNormals(SplittingOff) (m); :404-406 claims vtkPolyDataNormals
"may re-order geometry points" (it splits them; SplittingOff avoids that).
DOC: :42-44 promises "face_indices" but :89 returns owner CELL ids (m).

## volume — fv/render/volume.py (289 ln)
IMPLEMENTED: dispatch :97-128, transfer functions :131-164, unstructured ray cast :176-194,
vtkResampleToImage + vtkSmartVolumeMapper :197-257, translucent fallback :260-277.
BROKEN: hexahedra (the default FLD cell, plane.py:278) are routed at :118-121 to
vtkUnstructuredGridVolumeRayCastMapper whose Bunyk ray function is tetra-only
[V: 0 non-black pixels + VTK warning "Input contains more than tetrahedra"].
Operator-precedence bug :152-155 (transparent or draw_type or ("" in (...))) makes the 0.6 Solid opacity
floor unreachable [V: otf(lo)=0.25 with draw_type="Solid"].
APPROX: dispatch uses only the FIRST cell type :117 (mixed grids mis-routed); mono-colour volumes can
never use volume rendering :113-114; sampling stride-deletes cells :67-88 (holes) and the same attribute
caps the resample at 64^3 // sampling with a 16^3 floor :216-219 (sampling>4 is a no-op); NaN /
out-of-domain samples are clamped to the scalar minimum :237-240 (ghost planes); no
SetScalarOpacityUnitDistance so opacity is scale-dependent; fallback uses SetScalarModeToUseCellData
:264 (wrong for FLD point scalars, m); :143 reads the nonexistent obj.gradation (always 256).

## isosurface — fv/render/isosurface.py (175 ln)
IMPLEMENTED: vtkContourFilter levels :144-165, cell-to-point :133-141, vector glyphs :79-85, per-cycle
animation reusing one grid :91-117. vtkContourFilter is the right filter and its output carries normals.
STUB-ish: the "contour line" is vtkExtractEdges + wireframe :66-77; with scalar visibility left on the
black colour :75 is overridden (m) — coloured mesh edges, not black iso-lines.
INERT/WRONG: show_contour :34-35 (only contour_var gates), contour_auto :146-158, contour_value,
colorbar; the signature default cell_centered=True :23 mis-attaches FLD node arrays as CellData when a
caller supplies its own grid (m: 235-cell bogus iso, range [0.292,0.583] vs [0.333,0.667]).

## streamline — fv/render/streamline.py (521 ln)
IMPLEMENTED: two disjoint paths — real vtkStreamTracer for non-FLD :74-100 (RK4 when
SetIntegratorTypeToRungeKutta4 exists :83-86) and a hand-written numpy RK4 tracer for FLD :257-385 with
a trilinear hex locator + Newton solve (:158-254); tube/line actors :477-513.
APPROX: docstring :5-7 says "traced with vtkStreamTracer" but the FLD path never uses it :50-57; the
locator's bbox prefilter is a full O(n_cells) numpy scan per sample :208-209 [m: 1.15 ms per locate,
94 s for one default object on an 18k-cell FLD]; out-of-mesh samples silently use the nearest node :307
(discontinuous velocity, artificial near-wall flow); Newton convergence is judged on delta-r, not the
residual :226; seeds are never validated against the mesh; step size means model units on the FLD path
but VTK CELL_LENGTH on the tracer path (SetIntegrationStepUnit never called :96-97); no adaptive
integrator (RK45 + MaximumError) although VTK offers it; Triangle draw is faked with an 8-sided tube :486
instead of vtkRibbonFilter; constant_length / font_* unread (objects.py:381,396-398).

## pathline — fv/render/pathline.py (328 ln)
IMPLEMENTED: per-cycle continuation, VTK tracer :121-169 and numpy RK4 :174-247, tube/line actors.
DEAD FROM THE GUI: PathlineDialog has no file widget and nothing in fv/ assigns obj.files
(objects.py:833), so the empty-list guard :28-29 always fires and nothing renders.
BROKEN: seed_axis table :84 raises KeyError('ARBITRARY') for the dialog option "Arbitrary" (m).
INCONSISTENT: the VTK path never selects an integrator (VTK default RK2) :139-147 while the FLD path is
RK4 :222-227; steps_per_cycle is used as a physical propagation length :142; a new FldCellInterpolator
(KD-tree) is built per cycle file :200; step_size and color_var are read but not exposed by the dialog.

## particle — fv/render/particle.py (341 ln)
IMPLEMENTED: FPH particle buffer + frames :36-54, intersection/trim filters :67-68, scalar/vector attach
:87-99, sphere glyphs :176-183, arrows :219-224, cloth :261-270.
BROKEN BY DEFAULT: particle_type default "Points" (objects.py:279) maps a polydata that has points but no
vtkCellArray verts (:72-77; no SetVerts anywhere in the module) so the cloud is invisible
[V: no vertex cells; m: 0 px vs 1800 px with vertex cells].
INCONSISTENT: positions are filtered :67-68 but velocities :96-99 and the scalar :87-89 are not, so
per-point attributes belong to other particles (m); the "size" trim compares against |velocity| :337-339
(no diameter is read) and "Particle No" against the array index :335.
QUALITY: radius = size_px*1e-3 world units :175 although the dialog labels it pixels; glyphs BY_SCALAR
:219-224; the whole file is re-parsed once per animation frame (:36-54 + scene.py:512-514).
INERT: show_scalar, show_scalar_value, show_vector_value, display_attribute_no, trim_objects,
use_model_coord, special_variable_generalization, font_* (objects.py:275-302).

## turbo — fv/render/turbo.py (760 ln)
IMPLEMENTED: build_turbo_actors :46-110 (heatmap via hand-built quad mesh :185-233, else
vtkVertexGlyphFilter scatter :102); meridional/polar point sets :13-25,:372-381; circumferential
averages :236-277; blade loading :280-369; wall-face extraction :549-742 (L0/L1/L2 real).
APPROX: _b2b_heatmap_data returns None for cell-centred fields (vertex mask vs cell-centre mask mismatch
:142-157) so blade-to-blade silently degrades to a scatter (m); heatmap bins are a nested Python loop
with vtkIdList :207-217 (0.63 s at 256^2) and NaN bins leave holes :209-210; circumferential_average is a
count average (mesh-density weighted) :271-274 and its mass-weighted twin :500 is never used by the
actor; _face_centers_normals is a per-face/per-vertex Python loop :559-572 (0.73 s per 9,011 faces,
called twice per B2B rebuild); _estimate_pitch :687-713 documents "lag of the first autocorrelation peak
beyond min_lag" but takes the global argmax :708; blade-to-blade unwrap uses each point's own radius r*theta
:741 (non-rigid distortion) and folds on a seam :738; pitch_copies is hardcoded to 1 at the call site :89
so multi-copy is unreachable; pressure_coefficient hardcodes PRES/Pressure :438-440 and silently uses
denom=1 near V=0 :445-446; area_average's docstring :453 claims a face-area fallback that does not exist
(it is never area-weighted); mass_flow_average weights rho*|V_ax| per vertex :488-493 while
circumferential_mass_average weights rho*|V| :514 (contradictory definitions); n_r/n_z/tolerance are read
but have no dialog widgets (d2:1925-1946).

## ufo — fv/render/ufo.py (214 ln)
IMPLEMENTED: point/value extraction via ff.variable_array :38-69 (lazy CGNS variables materialise),
scatter :133, triangle surface :150-194.
APPROX: _cell_centers falls back to a per-cell Python loop :30-34; _vtk_scalars uses per-element SetTuple1
into a vtkFloatArray (float32) :101-112 (m: 0.119 s per 200k vs 0.0002 s numpy); one vtkTriangle inserted
per face :167-171 (m: 2.90 s per 100k); surface mode silently returns {} :154; the transparent branch
:209-210 is dead (no such attribute or dialog field).

## oilflow — fv/render/oilflow.py (340 ln)
NOT AN OIL-FLOW METHOD: no wall-shear computation, no surface tangency, no friction lines anywhere in fv
(grep for WallShear/friction/tangent over fv/**/*.py is empty; vtkGradientFilter unused). The module
traces the VOLUME velocity field from cut-plane seeds :44-116; the physical WSS -> wall integration step
is absent, and a plane coincident with a wall is accidental.
INCONSISTENT: on the FLD path "Euler" silently performs RK2/midpoint (rk4 flag :244-245, midpoint step
:269-271); the MAT/region rows mask is used on the VTK path :74-81 but ignored on the FLD path :68-72;
"Accuracy" maps to step = accuracy*1e-3 :113,:241-242, so a higher Accuracy means a LARGER step; seeds
cover the whole grid bbox :152,:183 (limited_width/height ignored) and are never validated (m: 20 of 200
seeds inside the mesh); per-sample full-cell scan :208-252.

## vector — fv/render/vector.py (183 ln)
IMPLEMENTED shared helper: apply_vector_coloring :27-75, vector_glyph_actor :78-112, _probe_vector
:115-166, _glyph_scale :169-183 (callers: isosurface.py:81, volume.py:59).
DEFECT (duplicated in plane/particle): glyphs never set scale-by-vector :105-106, so BY_SCALAR applies;
the mono/black branch :70-75 sets the property colour but never ScalarVisibilityOff, so arrows stay
LUT-coloured whenever a scalar is active (m: 0 black pixels of 215 non-white, mean RGB (112,127,202)).
The FLD branch precedes the source_grid branch :126-136, so for FLD the caller's polydata is ignored and
node vectors are copied by prefix index :131,:161 — isosurface.py:81 passes interpolated cut points, not
mesh nodes, so FLD iso-surface vectors are silently wrong.

## point — fv/render/point.py (224 ln)
IMPLEMENTED: FLD nearest-node probe :84-105, VTK probe path :108-159, marker + value label :160-224.
BROKEN: shape "Cross" calls vtkRegularPolygonSource.InnerRadiusOn() :170 and "Plus" calls
vtkLineSource.SetPoints2 :174 — neither method exists in VTK 9.6 [V: hasattr False -> AttributeError];
"Plus" also creates the line source twice (:173 then :175, with no points).
QUALITY: probe is a full O(n) argmin :92-93; radius = size*1e-3 :166; 12x12 sphere :178-179; font_name
unread (Courier hardcoded :204); label stagger constants :212.

## curve — fv/render/curve.py (104 ln)
IMPLEMENTED: vtkParametricSpline :28-45, scalar-coloured line :83-100. APPROX: SetUResolution(n-1) :40
samples uniformly in spline parameter, not arc length (vtkSplineFilter is the arc-length tool);
per-sample probe_values :62-65 is O(n_samples * n_vertices) and .get(var, 0.0) :64 fabricates 0.0 for
missing values (m: 25/64 samples zero on tr03_9); CurveObject.show_values is unread everywhere.

## bar — fv/render/bar.py (67 ln)
IMPLEMENTED: line between two points with a scalar ramp :12-52. APPROX: manual linspace plus per-sample
probe :18-21 (O(n * n_vertices), fabricated zeros), Python point/id loops :32-37, NaN-unsafe range
:47-52; obj.thickness :63 is read with default 2 although BarObject defines no thickness and the dialog
never sets it (d2:1640-1656); font_name/font_size unread.

## graph — fv/render/graph.py (134 ln)
IMPLEMENTED: matplotlib multi-series plot :57-113 plus save_graph. BROKEN BY WIRING: obj.files is never
assigned anywhere in fv/ so it falls back to [ff0.path] :51-54 and Cycle/Index graphs plot a single point;
GraphDialog writes only variable/x_mode/curve_label/title_text, leaving files/variables/show_legend/
log_scale unreachable; Curve mode ignores the requested variable (sample_along_curve uses the
CurveObject's own variable :42-48) so N series are identical; xlabel is "Index" for an arc-length axis
:88-89; load_file is re-run per cycle file with no cache :59; docstring :4-5 promises a message-log
fallback that does not exist (:119-120 returns None).

## text — fv/render/text.py (108 ln)
IMPLEMENTED: 2D vtkTextActor :15-35, world-anchored vtkBillboardTextActor3D :38-51. font_name ignored in
both (objects.py:739); bold/14/white-0.7 background hardcoded :23-31.

## bitmap — same module
IMPLEMENTED: textured quad :66-108 (uv helper :54-63 verified against vtkPlaneSource point order).
WRONG LAYER: bitmap_actor builds a WORLD-space vtkPlaneSource at pos (0.05,0.05) with size
0.25*scale x 0.25*scale :84-90 while the model documents position as "normalized display coords"
(objects.py:752) and the dialog spins 0..1 (d2:993-994) — the bitmap is model-scale dependent, always
square (no image aspect), and the module docstring :3-5 ("Both are 2D overlays added as vtkActor2D") is
false for bitmaps [V: vtkActor, world coords].

## gradation — fv/render/scene.py:232-306
IMPLEMENTED: renderer gradient :251-256 and a multi-stop image background :266-306. BROKEN: the multistop
image (dims (1,256,1) :273 + vtkImageMapper/RenderToRectangle :280-284) renders as a HORIZONTAL band, not
a vertical gradient (m, pixel probe); the two-stop path paints top_color at the BOTTOM :253-254 (m); the
internal fallback :303-304 uses the opposite order; control_points are never settable from any dialog, so
the multistop path is dead from the UI.

## grouping / folder / timeseries / maxmin / regionbc
No scene actors by design — stated at scene.py:680-681; grouping only drives tree nesting
(objects.py:606-630). GroupingObject.member_labels/subgroups, RegionBC.show_names and TimeSeries/MaxMin
state are never read by any render module.

## information — fv/render/information.py (72 ln)
IMPLEMENTED: all-variable probe :17-36 plus sphere marker :39-72. BROKEN: probe_values takes the nearest
VERTEX index :24 and indexes every array with it, ignoring VariableInfo.location and ff.variable_array()
[V: FPH PRES is cell-centred (len 63,697) but probed with a vertex index (221,786); a probe near vertex 10
returns cell #10's value]; docstring :4 ("FPH uses the nearest cell-centre value") is false; lazy CGNS
variables are skipped (reads vi.array :27). No text actor is produced, so font_name/font_size are inert.

## light — scene.py:339-359 (no module)
IMPLEMENTED: switch/intensity/colour on renderer light 0 :353-355. BROKEN: light 0 in a rendered scene is
VTK's auto-created headlight whose position/focal point VTK overwrites on every Render, and the code
never calls SetLightTypeToSceneLight, so LightObject.position is ignored (m, probe); the focal point is
hardcoded to the world origin :358; extra viewports keep their own headlights (only self.renderer is
touched).

## mirror — fv/render/mirror.py (108 ln)
IMPLEMENTED: sibling lookup :14-26, mirror transform :29-42, scalar inheritance :45-72.
APPROX: a negative-scale vtkTransformFilter without vtkReverseSense leaves the winding inverted, so
recomputed normals point inward (m) and this propagates to OBJ/FBX export; an unknown mirror_plane
silently mirrors in Z :31-37; keep_original is unread (objects.py:699).

## periodical — fv/render/periodical.py (75 ln)
IMPLEMENTED: rotated copies :41-74 (copies-1 rotated plus the original :46). APPROX: hardcoded X/Y/Z axis
table :37 (no arbitrary axis); the angle always fills 360 deg :47; the mapper input is evaluated twice
:57-59; axis_point is read :38 but exposed by no dialog, so the axis is always the world origin;
keep_original unread (objects.py:684). _find_sources duplicates mirror.py:14-26 verbatim.

## measure — fv/render/measure.py (130 ln)
IMPLEMENTED: exact distance/angle numpy :15-29, line plus billboard label :70-130. APPROX: only the first
2/3 points are used :87-101; units hardcoded in strings :39,:42; colours/width/font hardcoded :116-127;
compare_label/ratio_value are produced only by the dialog (d2:1602-1616) and never read here.

## cylinder / circle — fv/render/cylinder.py (143 ln)
IMPLEMENTED: vtkCylinder + vtkCutter :47-52 and plane cut + disk clip :114-130 with contour/vector/mesh.
BROKEN (verified): the local frame is built with RotateY/X then Translate :38-42,:100-109 but vtkTransform
concatenates M = R*T, so the cut axis passes through -center, not +center [V: t.RotateY(90);
t.Translate(1,2,3) maps (0,0,0) -> (3,2,-1)]; vtkCylinder.SetCenter/SetAxis exist in 9.6 [V] and need no
grid copy. show_vector is broken: :73 and :138 call vector_actor(cut, obj, cc) but the callee needs
(ugrid, ff, obj, cell_centered, rows) (plane.py:706-707) [V: TypeError: vector_actor() missing 1 required
positional argument]. mesh_lines_actor draws cutter triangle edges, not source-mesh face lines
(plane.py:884). contour_value/contour_thickness/font_* unread on this path.

## region — scene.py:911-931 (no module)
IMPLEMENTED inline: builds a throwaway SurfaceObject(index=1) and reuses build_surface_polydata; reads
region_name/color/transparent only; opacity 0.5 hardcoded :929. No unread RegionObject field.

## vr — fv/render/vr.py (201 ln)
IMPLEMENTED: backend detection/construction (OpenVR -> OpenXR -> generic) :22-201. STUB INTEGRATION:
gui/main.py:1610 calls create_vr_window() with renderer=None, so the VR window owns a fresh EMPTY renderer
:119-123 and the scene's actors are never attached — even with a working HMD nothing is visible;
release_vr_window :187-201 has no caller and the handle is never finalized; Initialize() exceptions are
swallowed :138-141,:159-162; vr_available only checks class existence; non-Windows silently returns False
(ctypes.WinDLL only :33-43).

## probe — fv/render/probe.py (171 ln)
Only get_probe_grid :44-62 is used (point.py:117). from_polydata :76-103, nearest_point :106-113,
probe_polydata :116-143, probe_summary :146-160, attach_probe_arrays :165-171 are dead (tests plus
fv/trace.py:33 only). The promised "nearest cell" is not implemented (:103 returns an always-empty cell
dict that :124 discards); extraction is 0th-order nearest-point :129-141; docstring :5-10 claims the memo
is shared by Information and picking, but only point.py imports it.

## axes — fv/render/axes.py (106 ln)
IMPLEMENTED: vtkAxesActor + vtkOrientationMarkerWidget gnomon :22-66 and standard-view cameras :87-106.
QUALITY: every dimension is hardcoded (shaft/tip 0.70/0.30 :26-27, radii :30-31, resolutions :32-33,
caption 16 :58); size_frac/corner are never driven by the model (main.py:2897 hardcodes bottom-left);
DrawWindowObject exposes only show_axes (objects.py:466).

## colorbar — fv/render/colorbar.py (263 ln)
IMPLEMENTED: LUT builder :72-106, registry :31-53, scalar bar :109-151, mapper hook :154-163, CSV/editor
:169-263. INERT: ColorbarRegistry hardcodes gradation 256 and "Rainbow" :31,:37, so
ColorbarObject.gradation and color_map (objects.py:862-863, written d2:551-552) never reach the rendered
LUT; font_name is ignored (Arial :143,:147); no SetUnconstrainedFontSize. QUALITY: turbo/viridis/parula
are 5-point piecewise-linear ramps (m: max channel error 0.502 / 0.135 vs matplotlib); SetTableValue is
called per entry in Python :87-106.

## material — fv/render/material.py (29 ln)
IMPLEMENTED: apply_sheen :8-29 (Phong plus specular). QUALITY: hardcoded pairs (Water 0.9/60, Luster
0.5/20, none 0.0/1.0) with no model exposure; the elif :22 lets Water silently win; the else branch wipes
an existing specular (m: 0.8/30 -> 0.0/1.0) and every actor builder calls it unconditionally, so no
highlight is possible without Luster; SetInterpolationToPhong is pixel-identical to Gouraud in VTK 9.6 (m).

## export — fv/render/export.py (855 ln)
IMPLEMENTED: STL :196-210, VRML/glTF :213-238, animation frames :240-263, iso PNG frames :687-725,
CVFF :571-633, STA save/load :136-191. HAND-ROLLED: OBJ :331-399 and ASCII FBX 7.3 :401-528
(vtkOBJWriter exists but is unused); both are O(n) Python writers (per-point GetPoint, per-cell GetCell
:368-395, :434-443); OBJ normals use SplittingOff (averaged across feature edges) and a planar UV
projection, not an unwrap. BROKEN/APPROX: .avi requests fall back to vtkOggTheoraWriter when vtkAVIWriter
is missing (it is absent in this VTK build [V]) and _write_frame_video :823-829 does the same for ANY
extension, writing Ogg Theora bytes into .mp4/.mkv; snapshot_png never enables alpha
(SetInputBufferTypeToRGB :58) and folds dpi into an integer magnification (:50-62), so scale<1 is ignored;
print_scene writes _print_buffer.png INTO the package directory :552-553 while its docstring names
export_print.png (:536); _encode_video_ffmpeg returns 1 instead of a frame count :738-757; save_status
persists only MainObject.children, never GlobalWindow objects (:145-153 vs objects.py:10-20).

## scene — fv/render/scene.py (1077 ln)
IMPLEMENTED: multi-renderer actor routing :101-133, per-object incremental rebuild :683-696,
object-to-actor pick map :135-163, global colorbar plumbing :165-209, overlays :520-580,
build/dispatch :584-1042.
DEFECTS: reset() :63-90 clears layers/caches but not _actor_object/_grad_bg_actor/_name_actor (stale
props plus an unbounded pick map); layer keys are "kind:slot" (:819,:830,:880,:1030 ...) while
set_layer_visible :367-370 matches the bare kind that main.py:2163-2180 passes, so tree visibility works
only for grid/colorbar [V by code path]; animate() :444-516 calls _remove_layer_prefix("plane:") inside
the automove-only loop :496, so the first animated frame deletes every non-automove plane's
contour/vector/mesh/boundary actors; fps is really a frame count (:479 passes frames=fps) contradicting
:447-449, and with fps=0 a frame index >= 1 is clamped, pinning planes at the end pose; area_pick :394-422,
overlay_text :579 and numpy_to_vtk_array :1044 are unused; _polydata_boundary :716-729 and
_build_neutral_wireframe :739-750 are per-face Python builds where the same package uses batched
vtkCellArray imports.

## viewport — fv/render/viewport.py (200 ln)
IMPLEMENTED: viewport_rects, unlink_camera, copy_pose, read_pose, apply_standard_views.
DEAD: layout() :59 and apply_viewport() :52 (main.py applies rects itself) and sync_cameras() :185
(tests only). APPROX: the eye distance is always the bbox DIAGONAL :148-149 (flat or elongated models are
framed too far); the iso eye :164 is not normalised; only two layouts exist :33-41; copy_pose :92-109
omits ParallelScale and the clipping range (unlike unlink_camera :125,:131) although :96-97 promises a
byte-for-byte pose. There is no ViewportObject; layout and camera mode are not persisted.

## camera — fv/render/camera.py (183 ln)
IMPLEMENTED: linear lerp :23-25, SLERP on view_up :28-53, Catmull-Rom :56-67, keyframe expansion with
auto/linear/spline :100-142, capture_camera_sequence :161-183. BROKEN: apply_pose :155 calls
renderer.ResetCamera() AFTER setting the pose, overwriting position/focal with the bounds-fitted pose
(m: keyframes at distance 12 and 7 both render from 11.58; only direction survives) and every captured
frame routes through it :178. CameraObject.position/focal_point/view_up/parallel_projection are never
applied by this module; the global CameraObject is never applied anywhere; frames are written at 1x with
no scale/dpi :181.

================================================================================
2. WIRED-BUT-INERT PARAMETERS (dialog -> model -> render)
================================================================================
IGNORED = no render module reads it; HARDCODED = the renderer uses a literal instead.
dl = fv/gui/object_dialogs.py, d2 = fv/gui/object_dialogs2.py, m = fv/model/objects.py.

PLANE: arbitrary_enabled dl:601/1656 m:102 IGNORED; operate_object dl:592/1655 m:106 IGNORED;
rotate_axis/rotate_angle dl:650,679/1659-1660 m:108-109 IGNORED; usage_guide/hv/axis dl:688-696/742-1662
m:111-113 IGNORED; usage_line_paint/usage_color_idx m:114-115 IGNORED (the dialog writes usage_lp /
usage_color); pick_mode/pick_hide dl:605,609/1657-1658 m:117-118 IGNORED; contour_paint dl:819/1678 m:125
HARDCODED (plane.py:433-468 paints unconditionally); vector_space_v dl:895/1697 m:141 HARDCODED
(plane.py:850 uses vector_space_u for u and v); vector_scale_thickness dl:943/1706 m:150 IGNORED;
mesh_paint/mesh_paint_rgb/mesh_block dl:1000-1017/1718-1722 m:158-160 IGNORED; boundary_auto dl:975/1712
m:167 IGNORED; boundary_broken_line dl:978/1713 m:168 HARDCODED (solid, width from mesh_thickness
plane.py:924); subline_automatic dl:1037/1726 m:171 IGNORED; subline_display_location dl:1040/1727 m:172
HARDCODED (plane.py:1040-1041); automove_standby/frames/show_path/path_sync/path_distance/start/end
dl:1230-1264/1754,1773-1777 m:183-193 IGNORED (frame count comes from the caller);
pick_ijk/pick_cycle_graph/pick_show_all_vars/pick_show_numbers/pick_color_enabled/pick_shape/
pick_line_color/pick_solid_color dl:1367-1395/1790-1797 m:230-237 IGNORED; integrate_scalar_enabled/
integrate_vector_enabled/integrate_output_file/integrate_output_csv/integrate_include_labels/
integrate_beep/integrate_recalc_redraw dl:1408-1447/1800-1806 m:239-245 IGNORED (the GUI reads its
widgets); texture_method dl:1817 m:249 HARDCODED; texture_pos_u/pos_v dl:1600-1604/1820-1821 m:252-253
HARDCODED (only scale/angle are read); font_name dl:1624-1630/1822 m:255 HARDCODED (Arial plane.py:636,
Courier :483); font_float dl:1635/1824 m:257 IGNORED; use_model_coord / no_vector_contour_simultaneous /
inter_surface / inter_isosurface / inter_plane / inter_undisplayed dl:1518-1537/1809-1814 m:260-265
IGNORED. (trim_* m:197-202 ARE read at plane.py:1135-1136 but have no dialog control.)

SURFACE: region_mode dl:320/481 m:46 IGNORED; mesh_front/mesh_back dl:401-403/493-494 m:65-66 IGNORED (no
culling in mesh_lines_actor); integrate_scalar/projected_area dl:460-463/502-503 m:79-80 IGNORED
(integrate_surface has no caller); font_name/font_float m:82,84 IGNORED. Read but GUI-unreachable:
contour_luster/contour_water/mesh_luster/mesh_water m:57-58,69-70 (no widget); show_mesh m:63 is read
(surface.py:477) but has no Display checkbox, so surface mesh lines cannot be switched off.

PARTICLE: show_scalar dl:1894/2088 m:275 IGNORED by particle.py; show_scalar_value/show_vector_value
dl:1896-1956/2090-2101 m:277,287 IGNORED; display_attribute_no dl:2013/2105 m:293 IGNORED; trim_objects
dl:2021/2107 m:295 IGNORED (only the plane's copy is read); use_model_coord m:300 IGNORED;
special_variable_generalization dl:2069/2113 m:302 IGNORED; font_name/size/float dl:2040-2054/2109-2111
m:297-299 IGNORED; particle_type "Specify" dl:1912/2098 m:279 falls into the points branch
particle.py:102-105 HARDCODED.

ISOSURFACE: contour_auto d2:119/179 m:318 HARDCODED (isosurface.py:146-158); show_contour d2:110/177
m:314 PARTIAL (isosurface.py:34-36); contour_value m:319 IGNORED; vector_space m:330 IGNORED;
font_name/size/float m:332-334 IGNORED; colorbar m:335 IGNORED.

COLORBAR: gradation d2:517-520/551 m:862 HARDCODED (colorbar.py:31,37 = 256/"Rainbow"); color_map
d2:521-526/552 m:863 HARDCODED in render; font_name/font_float m:870,872 IGNORED; visible m:861 IGNORED.

VOLUME: vector_space m:422 IGNORED; font_name/size/float m:424-426 IGNORED; obj.gradation read at
volume.py:143 is a PHANTOM attribute (not in VolumeObject); transparent m:416 is read (volume.py:109) but
has no dialog control; colorbar m:427 is read as a palette name while the dialog treats it as free text.

OTHERS: Measure.compare_label / ratio_value d2:1556-1614 m:714-715 IGNORED by measure.py;
RegionBC.show_names d2:1696 m:548 IGNORED (no regionbc dispatch); TimeSeries.columns / MaxMin.history
d2:1211/1271 m:658-670 dialog-only kinds; Grouping.member_labels / subgroups d2:1349-1370 m:602-603
IGNORED; DrawWindow.display_list d2:2081/2109 m:465 GUI-only; DrawWindow show_file/show_cycle/show_time/
show_axes/parallel_projection/gradient_background are GUI-MEDIATED (main.py:2365-2385 -> scene.py:527-535);
Camera.frame_count/keyframe_interp are GUI-MEDIATED into camera.py:100,171 (NOT inert);
MirrorCopy.keep_original m:699 and PeriodicalCopy.keep_original m:684 IGNORED; PeriodicalCopy.axis_point
m:682 is read (periodical.py:38) but no dialog sets it; CurveObject.show_values m:579,
PointObject.pick_show_numbers m:357, arbitrary_normal_r/t/p m:103-105, constant_length m:381,
StreamlineObject.vector_space m:330 and VolumeObject.vector_space m:422 are dead in BOTH layers.
REVERSE GAP (render reads, no dialog can set): colorbar_contour/colorbar_vector plane.py:1601,1607
(the PlaneDialog combos dl:1507-1514 are never populated); GradationObject.control_points scene.py:246;
ColorbarObject.title/show_title/num_labels/label_color/label_format colorbar.py:126-150;
GraphObject.log_scale/show_legend/variables; StreamlineObject.max_steps/seed_spacing/seed_normal;
PathlineObject.step_size/files; TurboObject.tolerance/n_r/n_z; TextObject.anchor_3d/anchor_position;
VolumeObject.colorbar. Also: font_size is exposed for 12 kinds but read by only a few modules;
contour_thickness/contour_value exist only on the plane path.

================================================================================
3. QUALITY OF IMPLEMENTATION
================================================================================
3a. Hardcoded constants that should be data-driven (sample; each is a literal in the render layer)
- plane.py:495 SetNumberOfContours(10) (iso-line levels never derive from the range or a setting);
  :851 seed step max(u,v)/40; :875 arrow scale 0.05*extent; :659-666 cone 0.4/0.15/0.04 and tip formulas
  arrow_angle*0.35 / arrow_size*0.1; :545-551 colorbar 7 labels, 256 colours, 0.55x0.06 at (0.12,0.03);
  :461-465 opacities 0.5/0.65; :701,:925 0.5; :1494-1503 CSV unit strings ("[m^2]", "[m^3/s]", ...).
- surface.py:222 0.5; :378 default bump 0.05; :500-501 0.05*width glyph scale.
- volume.py:108 0.35; :110/:152 floors 0.25/0.6; :157 0.75; :219 64^3 with a 16^3 floor; :190-192 0.25/0.8/0.3.
- streamline.py:169 1e-6; :221 24 Newton iterations; :226 1e-12; seed defaults 6/6 :402 vs 10/10 :452;
  :474 tube radius 0.002*diag; :486 3/8 sides. pathline.py:41 step 0.001; :299 max(1e-4, thickness*1e-3).
- oilflow.py:113 accuracy*1e-3; :157/:188 max(u,v)/40 (duplicated from plane); :131/:327 tube sides.
- particle.py:175 size_px*1e-3; :177-178 12/12 sphere; :229 arrow colour (0.1,0.1,0.1) ignoring mono_color.
- point.py:166 size*1e-3; :178-179 12/12; :212 label stagger. information.py:48/55 radius 0.002 or
  0.005*diag; :62 12/12. axes.py:26-33, :58 caption 16. measure.py:116-127 red, width 2.0, font 14,
  " m"/" deg". colorbar.py:31/:37 256/"Rainbow"; :143/:147 Arial. text.py:23/:43 font 14; :30-31 white 0.7;
  :85-86 0.25*scale square. turbo.py:27 tol 0.005; :108-109 size 2, colour (0.2,0.2,0.8); :696-711 720
  bins, gate 0.35; :89 pitch_copies=1. export.py:445 "%.9g"; :746-748 libx264/yuv420p; :799 frame_%04d.png.
- scene.py:58-61 background and ParallelProjectionOn (DrawWindowObject never consulted); :270 n=256;
  :315-317 billboard 12; :570-575 overlay Courier 14 at (0.02,0.92); :759-801 wireframe colour/width x3.

3b. Python O(n)/O(n^2) loops over mesh/point arrays (measured where noted)
- plane.py:201-225 FPH grid build 4.18 s vs 0.01 s for the batched hex build; :284-292 FLD/CGNS type-code
  path 0.214 s vs 0.004 s (54x) for 18,240 cells; :864-867 double InsertNextPoint loop; :947-974 vtkIdList
  per face; :987-998 Counter over 6*n_cells twice, 0.719 s per render, never cached (boundary_line
  defaults True); :1437-1468 integrate_cut per-cell/per-vertex Python.
- surface.py:76-85 per-face inserts 1.576 s vs 0.022 s batched (200k quads); :112-117 same; :69
  [owner[fi] in keep_set] 0.166 s vs np.isin 0.0072 s; :414-428 Newell normals 8.7 s per 172k polys.
- scene.py:720-726 and :743-747 per-face boundary/neutral polydata; :275-279 256x3 scalar component calls.
- turbo.py:207-217 n_r*n_z vtkIdList loop (0.63 s at 256^2); :559-572 per-face/per-vertex centres+normals
  (0.73 s per 9,011 faces, twice per B2B rebuild -> build_turbo_actors(B2B) ~1.94 s).
- ufo.py:110-111 SetTuple1 per element (0.119 s per 200k vs 0.0002 s numpy); :167-171 one vtkTriangle per
  face (2.90 s per 100k). particle.py:264-265 per-point SetId. curve.py:59 and :63-64 list comprehension
  over all points plus a per-sample probe (1.14 s per 64 samples on 221k vertices); bar.py:21 the same
  pattern (0.25 s per 32 samples).
- export.py:368-395 OBJ per-point/per-cell; :434-449 FBX; :594-626 CVFF per-region Python passes.
- Per-sample work in tracers: streamline.py:208-209 full-cell bbox scan per sample (1.15 ms per locate,
  94 s for one default object); oilflow.py:208-252 the same; pathline.py:163 per-point GetPoint plus a
  fresh KD-tree per cycle file :200.

3c. VTK filter/mapper choices that undercut quality or waste work
- vtkUnstructuredGridVolumeRayCastMapper with non-tetra input (volume.py:182) renders nothing for hex [V];
  vtkDataSetTriangleFilter, vtkProjectedTetrahedraMapper or the existing resample+SmartVolumeMapper path
  are the correct routes.
- vtkGlyph3D without SetScaleModeToScaleByVector in plane.py:691, surface.py:252, vector.py:105,
  particle.py:223 -> arrow length tracks the active scalar, not |v|.
- vtkExtractEdges used for "mesh lines" on a triangulated cut (plane.py:884) -> diagonals.
- vtkImageMapper + RenderToRectangle for the multistop background (scene.py:280-284) -> horizontal band.
- vtkCleanPolyData in contour_value_actor (plane.py:474) is pointless work.
- Default mapper LUTs in surface.py:206-230, isosurface.py:48-52 and plane.py:444-451 vs three other
  colour conventions (volume.build_lut, ColorbarRegistry, colorbar.py): the same scalar is coloured
  differently per object kind.
- vtkVertexGlyphFilter + vtkPolyDataMapper for 10^5-10^6 point clouds (turbo.py:102, ufo.py:133) where
  vtkPointGaussianMapper / vtkGlyph3DMapper are cheaper.
- vector_actor re-cuts and re-runs vtkCellDataToPointData on the whole grid (plane.py:728-739) although
  the caller already holds the cut (0.484 s of a 1.008 s plane build).
- No caching for plane-independent work: _boundary_polydata (plane.py:930-998, 0.175 s FPH / 0.807 s FLD
  per render), turbo wall extraction (:747 then again :756), pathline KD-tree per file.
- mirror.py negative-scale transform without vtkReverseSense -> inward normals.

3d. Numerical methods that are low-order or crude
- Cut-plane contour for cell-centred (FPH) fields is piecewise CONSTANT: the cut copies the owner cell's
  value (m: 4,928 cut cells / 1,707 distinct values) while the vector path explicitly interpolates
  (plane.py:729-733); docstring plane.py:437-439 implies a proper map.
- integrate_cut uses only the first triangle of each cell for area/normal (plane.py:1443-1447)
  [V: unit quad -> area 0.5 and sum 0.5 instead of 1.0]; surface integration delegates to it
  (surface.py:320-326), so the error applies there too.
- Volume opacity ramp is 3 points with a broken floor (volume.py:152-155 [V]); no
  SetScalarOpacityUnitDistance, so opacity is scale-dependent; NaN clamped to the scalar minimum.
- Streamline/pathline/oilflow FLD tracers: fixed-step RK4 in model units, no adaptive stepping, no error
  control, no boundary termination or end-point interpolation; samples outside the mesh silently fall back
  to the nearest node (streamline.py:307, oilflow.py:247-252), injecting artificial flow.
- VTK tracer paths use default step UNITS (cell length) while the FLD paths use model units, so
  obj.step_size means different things per file kind (streamline.py:96-97).
- pathline's VTK path never selects an integrator -> RK2 (pathline.py:139-147) vs RK4 on the FLD path.
- oilflow "Euler" is RK2/midpoint on the FLD path (oilflow.py:244-271).
- Turbo circumferential averages are unweighted count averages (turbo.py:271-274) and the "mass-flow
  weighted" variants use per-vertex weights only (turbo.py:488-493, :514) with contradictory definitions.
- automove Sin/Cos are ease-in/ease-out, not oscillation (plane.py:1382-1385); Custom Path is nearest-row
  (plane.py:1369); Rotation adds automove_offset unconditionally so t=0 differs from the start pose (:1346).
- curve.py samples the spline uniformly in parameter, not arc length (:40); glyph/normal conventions
  differ per module (surface 0.05*width vs vector 0.03*diag/|v|max).
- camera.apply_pose's ResetCamera discards keyframe distance/zoom (camera.py:155).

================================================================================
4. WHERE THE CODE SAYS X BUT DOES Y
================================================================================
1. plane.py:374-383 "the cut is a pure function of (grid identity, plane pose)" — it also depends on the
   arrays attached to the grid; the cache serves a stale cut after a variable switch [V].
2. plane.py:645-647 "Orient + scale arrow glyphs ... from PointData vectors" — no scale-by-vector is set
   (:685-694); length follows the active scalar.
3. plane.py:715-717 "Uniform ... over the cut bounding box; Actual ... clipped to the cut extent" — one
   shared branch (:755-761) seeded from the VOLUME bounds (:847); ~57% of samples miss the cut.
4. plane.py:568-569 texture "scaled/rotated" — rotation is implemented as a UV translation (:608-611) [V].
5. plane.py:1002 "External frame + display-location marks" — only a bbox frame (:1016-1042).
6. plane.py:1054 "kept on the inside (distance <= 0)" — vtkClipPolyData keeps the outside (:1074).
7. plane.py:1157-1160 clip bounds are "world-coordinate bounds" — clip_region_actor treats them as
   plane-local offsets (:1198-1215).
8. plane.py:1352-1353 "interpolate along a CSV path" — nearest row (:1369).
9. plane.py:270-271 "batch-insert the whole grid ... instead of a per-cell Python loop" — only the
   plain-hex branch; the CGNS/mixed path still loops per cell (:284-292, 54x slower).
10. plane.py:440-443 contour_actor "Honour flags" — contour_paint is never read.
11. surface.py:42-44 "face_indices are the selected boundary-face indices" — owner cell ids (:89).
12. surface.py:292 "Clip the surface against Trim tab X/Y/Z min/max planes" — clips against the surface's
    own bbox and deletes the surface [V].
13. surface.py:341-343 "diag is the model diagonal" — max bbox side (:374-376).
14. surface.py:404-406 "vtkPolyDataNormals may re-order geometry points" — it splits points; SplittingOff
    avoids that and is 95x faster.
15. volume.py:100 "hex/tet/wedge/pyramid -> ray-cast volume" — tetra-only mapper; hexes render nothing [V].
16. volume.py:136-137 "at the colorbar gradation" — obj.gradation does not exist (:143, always 256).
17. volume.py:138-139 "mid point level is taken from obj.opacity_mid" — it is an opacity multiplier at a
    fixed level (:156-162).
18. volume.py:201-202 "1 -> 64^3, 2 -> 32^3 ..." — hidden 16^3 floor (:219), so sampling>4 is a no-op.
19. streamline.py:5-7 "traced through the volume vector field with vtkStreamTracer" — false for FLD
    (:50-57, numpy tracer); :260-261 "RK4 ... with explicit Euler as the fallback" while the else branch is
    RK2 (:86).
20. isosurface.py:24-29 / :5-6 document Auto levels and stacked contour lines — contour_auto and
    show_contour are inert and the "lines" are coloured triangulation edges (:66-77).
21. text.py:3-5 "Both are 2D overlays added as vtkActor2D" — bitmap_actor returns a world-space vtkActor
    (:84-90), contradicting objects.py:752 "normalized display coords" [V].
22. information.py:4 "FPH uses the nearest cell-centre value" — a vertex index is used for every array
    (:21-35) [V].
23. oilflow.py:65-67 "nearest-node sampling + RK4" — trilinear first (:247-252); and the object name
    "Oil Flow" over-promises: no wall shear or friction line exists.
24. particle.py:79-80 "Point id scalars: ... used for Display particle No.-style scalar colouring" —
    PointId is only AddArray'd (:84) and display_particle_no is a filter (:333-335).
25. pathline.py:129 / :179-180 "nearest-node RK4" — trilinear first (:200, :208-212); :24-26 "later files
    only need to supply the velocity field" — load_file re-parses all.
26. turbo.py:3-6 "Both return 2D point sets rendered as scatter actors" — the heatmap path builds quad
    meshes (:80-83); :453 "Falls back to arithmetic binning when no face-area metric is available" — no
    face-area code exists; :687-688 "lag of the first autocorrelation peak" — global argmax (:708).
27. graph.py:4-5 "falls back to a simple text summary in the message log" — bare except -> None (:119-120).
28. export.py:30-39 "dpi is honoured" — folded into an integer pixel magnification with no metadata
    (:50-62); :532-536 promises export_print.png but writes fv/render/_print_buffer.png (:552-553);
    :738-740 says the ffmpeg helper returns a frame count but it returns 1 (:750-757); :402-407 "Shares ...
    per-vertex normals and planar UVs" — FBX UVs come from the pre-normal pd (:428) unlike OBJ (:359-360).
29. camera.py:145-146 "best-effort" pose — ResetCamera (:155) discards the requested distance.
30. viewport.py:96-97 "byte-for-byte the same pose" — copy_pose omits ParallelScale/clipping (:92-109).
31. cylinder.py:4-5 "with optional half-height planes" — the +-height clip is unconditional (:55-65).
32. probe.py:13-14 / :119-120 "nearest point and nearest cell" / "merged point+cell values" — cell arrays
    are never read (:103, :124).
33. scene.py:234-238/:267 "full-screen image gradient" and :276 "top colour = first stop" — the multistop
    background renders as a horizontal band with the last stop on the left (m); :340-345 "mirrors the
    scPOST Brightness tab ... directional light vector" — the position is ignored for the auto headlight
    and the focal point is hardcoded; :447-449 "fps ... divides it to a normalised [0,1] time" — it is a
    frame count (:479, plane.py:1324-1325).
34. material.py presents apply_sheen as a quality knob; SetInterpolationToPhong is pixel-identical to
    Gouraud in VTK 9.6 (m) and the else branch destroys an existing specular.

================================================================================
5. TRIAGE — highest-severity, reproduced defects
================================================================================
1. plane.py:378-413 — a contour-variable switch re-renders the cached cut without the new array [V].
2. volume.py:118-121 — every hex (default FLD) volume renders 0 pixels [V].
3. surface.py:291-313 — enabling any surface trim deletes the whole surface [V].
4. cylinder.py:38-42/:100-109 — the cut axis is mirrored through the origin unless center == 0 [V].
5. cylinder.py:73/:138 — show_vector raises TypeError (argument arity) [V].
6. volume.py:152-155 — precedence bug: Solid volumes get the transparent opacity floor [V].
7. plane.py:1443-1447 / surface.py:320-326 — n-gon integration under-reports area by (n-2)/n [V].
8. scene.py:367-370 vs :819-1039 — tree visibility only works for grid/colorbar [V by code path].
9. scene.py:496 — the first animated frame deletes all non-automove plane actors.
10. camera.py:155 — keyframe zoom/pan discarded by ResetCamera.
11. scene.py:253-254, :266-306 — gradation: multistop renders horizontally, two-stop top/bottom swapped.
12. particle.py:72-105 — the default Points/Specify particle display is invisible (no vertex cells).
13. information.py:21-35 — FPH probes read the wrong index space (vertex index into cell arrays) [V].
14. point.py:170/:174 — Cross/Plus marker shapes raise AttributeError (nonexistent VTK methods) [V].
15. colorbar.py:31/:37 — ColorbarObject.gradation/color_map have no effect on the rendered LUT.
16. pathline.py:84 — the dialog's "Arbitrary" seed axis raises KeyError.
17. export.py:280-283/:823-829 — .avi/.mp4 requests silently write Ogg Theora (vtkAVIWriter absent) [V].
18. plane.py:685-694 (+ surface:252, vector:105, particle:223) — glyph length encodes the scalar, not |v|.
19. streamline.py:208-209 — O(n_cells)-per-sample locate (94 s for one default FLD streamline).
20. scene.py:63-90 — reset() leaks _actor_object/_grad_bg_actor/_name_actor (stale props across files).
