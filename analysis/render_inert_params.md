# Render-layer wiring audit — dialog/object-model attributes the render layer never reads

Method: dialog plumbing grepped in `fv/gui/object_dialogs.py` / `object_dialogs2.py` (init + `apply_to`),
canonical fields from `fv/model/objects.py`, reads cross-checked against every module in `fv/render/`
(`getattr(obj,"x")`, `obj.x`, and every literal occurrence). Every line number below was
machine-verified. Scratch scripts + raw dumps: %TEMP%\\fv_audit\\.

## A. PLANE — fv/gui/object_dialogs.py (PlaneDialog) — render module fv/render/plane.py
| attr | dialog init / apply | model | verdict | render evidence |
|---|---|---|---|---|
| arbitrary_enabled | 601 / 1656 | objects.py:102 | IGNORED | arbitrary cut uses point+normal only (plane.py:364-365,1104-1105); literal absent from fv/render |
| operate_object | 592 / 1655 | :106 | IGNORED | — |
| rotate_axis | 650 / 1660 | :108 | IGNORED | rotation driven by widget value (object_dialogs.py:716-726) |
| rotate_angle | 679 / 1659 | :109 | IGNORED | same |
| usage_guide | 688 / 1662 | :111 | IGNORED | — |
| usage_hv | 695(key "hv") / 742 dynamic setattr | :112 | IGNORED | — |
| usage_axis | 695 / 742 | :113 | IGNORED | — |
| usage_line_paint | (dialog writes `usage_lp`, key "lp" @696) | :114 | IGNORED + never written | — |
| usage_color_idx | (dialog writes `usage_color`, key "color" @696) | :115 | IGNORED + never written | — |
| pick_mode | 605 / 1657 | :117 | IGNORED | — |
| pick_hide | 609 / 1658 | :118 | IGNORED | — |
| contour_paint | 819 / 1678 | :125 | HARDCODED | contour_actor paints unconditionally (plane.py:433-468) |
| vector_space_v | 895 / 1697 | :141 | HARDCODED | `_uniform_points_on_cut` uses vector_space_u for u **and** v (plane.py:850-851) |
| vector_scale_thickness | 943 / 1706 | :150 | IGNORED | — |
| mesh_paint | 1016 / 1721 | :158 | IGNORED | mesh_lines_actor uses color/thickness/transparent/luster/water only (plane.py:882-899) |
| mesh_paint_rgb | 1017 / 1722 | :159 | IGNORED | same |
| mesh_block | 1000 / 1718 | :160 | IGNORED | same |
| boundary_auto | 975 / 1712 | :167 | IGNORED | boundary_line_actor (plane.py:902-927) |
| boundary_broken_line | 978 / 1713 | :168 | HARDCODED | solid line, width from mesh_thickness (plane.py:924) |
| subline_automatic | 1037 / 1726 | :171 | IGNORED | subline_actor (plane.py:1001-1042) |
| subline_display_location | 1040 / 1727 | :172 | HARDCODED | frame color (0.5,0.5,0.5) / width 1 (plane.py:1040-1041) |
| automove_standby | 1230 / 1754 | :183 | IGNORED | — |
| automove_frames | 1235 / 1755 | :184 | HARDCODED | scene.py:479 passes `frames=fps`; fps comes from animate() caller (gui/main.py:2577 fps=0 → scalar t; export.py:242/257/315 fps=15) |
| automove_show_path | 1249 / 1773 | :189 | IGNORED | — |
| automove_path_sync | 1252 / 1774 | :190 | IGNORED | — |
| automove_path_distance | 1256 / 1775 | :191 | IGNORED | Custom Path indexes CSV rows by t only (plane.py:1352-1372) |
| automove_path_start | 1260 / 1776 | :192 | IGNORED | same |
| automove_path_end | 1264 / 1777 | :193 | IGNORED | same |
| pick_ijk | 1368 / 1790 | :230 | IGNORED | pick_point reads only pick_scalar(_var)/pick_vector(_var) (plane.py:1260-1277) |
| pick_cycle_graph | 1371 / 1791 | :231 | IGNORED | same |
| pick_show_all_vars | 1377 / 1792 | :232 | IGNORED | same |
| pick_show_numbers | 1380 / 1793 | :233 | IGNORED | same (PointObject:357 copy also dead) |
| pick_color_enabled | 1384 / 1794 | :234 | IGNORED | same |
| pick_shape | 1389 / 1795 | :235 | IGNORED | same |
| pick_line_color | 1393 / 1796 | :236 | IGNORED | same |
| pick_solid_color | 1395 / 1797 | :237 | IGNORED | same |
| integrate_scalar_enabled | 1408 / 1800 | :239 | IGNORED | GUI uses widget state (1478); render never reads attr |
| integrate_vector_enabled | 1418 / 1801 | :240 | IGNORED | GUI widget 1480 |
| integrate_output_file | 1427 / 1802 | :241 | IGNORED | GUI widget 1492 |
| integrate_output_csv | 1429 / 1803 | :242 | IGNORED | GUI widget 1493 |
| integrate_include_labels | 1437 / 1804 | :243 | IGNORED | GUI widget 1495 |
| integrate_beep | 1440 / 1805 | :244 | IGNORED | — |
| integrate_recalc_redraw | 1447 / 1806 | :245 | IGNORED | — |
| use_model_coord | 1518 / 1809 | :260 | IGNORED | — (also ParticleObject:300) |
| no_vector_contour_simultaneous | 1523 / 1810 | :261 | IGNORED | — |
| inter_surface | 1528 / 1811 | :262 | IGNORED | — |
| inter_isosurface | 1531 / 1812 | :263 | IGNORED | — |
| inter_plane | 1534 / 1813 | :264 | IGNORED | — |
| inter_undisplayed | 1537 / 1814 | :265 | IGNORED | — |
| texture_method | 1584-1587 (single item "Plane") / 1817 | :249 | HARDCODED | texture_actor = vtkTextureMapToPlane (plane.py:600) |
| texture_pos_u | 1600 / 1820 | :252 | HARDCODED | texture_actor reads scale/angle only (plane.py:602-603) |
| texture_pos_v | 1604 / 1821 | :253 | HARDCODED | same |
| font_name | 1624-1630 / 1822 | :255 | HARDCODED | SetFontFamilyToArial plane.py:636; contour labels SetFontFamilyToCourier plane.py:483; colorbar.py:143,147 Arial |
| font_float | 1635-1638 / 1824 | :257 | IGNORED | — |
| font_size | 1631-1634 / 1823 | :256 | CONSUMED | plane.py:482,556,560,627 |

## B. SURFACE — fv/gui/object_dialogs.py (SurfaceDialog) — fv/render/surface.py
| attr | dialog | model | verdict | render evidence |
|---|---|---|---|---|
| region_mode | 320 / 481 | objects.py:46 | IGNORED | surface.py:131 uses selected_regions only |
| mesh_front | 401 / 493 | :65 | IGNORED | mesh_lines_actor sets no culling (surface.py:271-288) |
| mesh_back | 403 / 494 | :66 | IGNORED | same |
| integrate_scalar | 460 / 502 | :79 | IGNORED | `integrate_surface` (surface.py:320) has **zero callers**; no build path reads it |
| projected_area | 463 / 503 | :80 | IGNORED | — |
| (consumed) contour_paint_front/back | 372,374 / 488,489 | :54,55 | CONSUMED | surface.py:223,225 |
| (consumed) display_mats / display_volume_regions | 483,484 | :48,50 | CONSUMED | cell_filter_mask surface.py:65-66,98-99 |
| (consumed) trim_* bools | 443 / 500 | :72-77 | CONSUMED | dynamic getattr surface.py:294-296 |

## C. PARTICLE — fv/gui/object_dialogs.py (ParticleDialog) — fv/render/particle.py
| attr | dialog | model | verdict | render evidence |
|---|---|---|---|---|
| show_scalar | 1894 / 2088 | objects.py:275 | IGNORED for particle (PARTIAL) | particle.py:136-153 attaches scalar whenever scalar_var is non-empty; VolumeObject.show_scalar IS read (volume.py:44) |
| show_scalar_value | 1896-1898 / 2090 | :277 | IGNORED | no label actor in particle.py |
| show_vector_value | 1954-1956 / 2101 | :287 | IGNORED | — |
| display_attribute_no | 2013 / 2105 | :293 | IGNORED | only display_particle_no / display_particle_size read (particle.py:333,336) |
| trim_objects | 2021-2022 / 2107 | :295 | IGNORED for particle | plane.py:1057 reads the plane's copy only |
| use_model_coord | 2031 / 2108 | :300 | IGNORED | — |
| font_name | 2040-2046 / 2109 | :297 | IGNORED | no font read in particle.py |
| font_size | 2047-2050 / 2110 | :298 | IGNORED for particle (PARTIAL) | — |
| font_float | 2051-2054 / 2111 | :299 | IGNORED | — |
| special_variable_generalization | 2069 / 2113 | :302 | IGNORED | only special_cloth is read (particle.py:116) |
| particle_type "Specify" | 1912 / 2098 | :279 | HARDCODED | branch only Sphere|Actual else points (particle.py:102-105) |

## D. ISOSURFACE — fv/gui/object_dialogs2.py (IsosurfaceDialog) — fv/render/isosurface.py
| attr | dialog | model | verdict | render evidence |
|---|---|---|---|---|
| contour_auto | 119 / 179 | objects.py:318 | HARDCODED | isosurface.py:146-158 branches on whether contour_values is non-empty, else contour_number; flag never consulted |
| show_contour | 110 / 177 | :314 | PARTIAL | isosurface.py:34-36 gates on contour_var only; read for plane/surface/cylinder/circle (plane.py:1533, surface.py:456, cylinder.py:32) |

## E. COLORBAR — fv/gui/object_dialogs2.py (ColorbarDialog) — fv/render/colorbar.py
| attr | dialog | model | verdict | render evidence |
|---|---|---|---|---|
| gradation | 517-520 / 551 | objects.py:862 | HARDCODED | ColorbarRegistry.lut() hardcodes 256 (colorbar.py:31,37); colorbar_actor never reads it (colorbar.py:109-151); volume.py:143 reads `gradation` on a VolumeObject that has no such field |
| color_map | 521-526 / 552 | :863 | HARDCODED in render | colorbar.py:37 `build_lut(cls._gradation, "Rainbow")`; only GUI reads obj.color_map (main.py:2115) |

## F. OTHER KINDS
| kind | attr | dialog | model | verdict | render evidence |
|---|---|---|---|---|---|
| Measure | compare_label | od2:1556 / 1586 | objects.py:714 | IGNORED | measure.py:34-35,80-81 reads points/mode only |
| Measure | ratio_value | od2:1614 (write) | :715 | IGNORED | never read anywhere |
| Region BC | show_names | od2:1696 (forced True) | :548 | IGNORED | no regionbc dispatch (scene.py:680-681) |
| Time Series | columns | od2:1211 | :658 | IGNORED by render | dialog-only kind |
| MaxMin | history | od2:1271 | :669 | IGNORED by render | dialog-only kind |
| Grouping | member_labels | od2:1349 / 1369 | :602 | IGNORED | model helper `grouping_members` (objects.py:606) has no callers; FolderObject.member_labels used only for GUI tree nesting (panes.py:281) |
| Grouping | subgroups | od2:1360 / 1370 | :603 | IGNORED | same |
| Draw Window | display_list | od2:2081 / 2109 | :465 | IGNORED | GUI only renames the tree node (main.py:2388 → panes.py:224-233) |
| Draw Window | show_file / show_cycle / show_time | od2:2087,2090,2093 / 2111-2113 | :467-469 | GUI-MEDIATED | render reads its own dict via scene.set_overlay_flags (main.py:2365-2368 → scene.py:527-535) |
| Draw Window | show_axes | od2:2084 / 2110 | :466 | GUI-MEDIATED | main.py:2375 → render/axes.py:69 |
| Draw Window | parallel_projection | od2:2096 / 2114 | :470 | GUI-MEDIATED | main.py:2378-2381 sets the VTK camera |
| Draw Window | gradient_background | od2:2099 / 2115 | :471 | GUI-MEDIATED | main.py:2382-2385 |
| Camera | frame_count | od2:1774 / 1867 | :485 | GUI-MEDIATED | used as n at od2:1866/1876 → camera.py:161,100 |
| Camera | keyframe_interp | od2:1778 / 1836 | :486 | GUI-MEDIATED | od2:1874-1876 passes mode= → camera.py:171,100 |

## G. PARTIAL — read by render for one kind, silent for another
1. **font_size** — read: plane.py:482/556/560/627, text.py:23/43, point.py:205, colorbar.py:144/148. Silent: Particle (exposed od1:2047-2050/2110), Bar, Curve, Information, RegionBC, Cylinder, Circle, Pathline, Surface, Isosurface, Streamline, Volume.
2. **show_contour** — silent in isosurface.py (34-36) though exposed (od2:110/177); read for plane/surface/cylinder/circle.
3. **show_scalar** — silent in particle.py; read in volume.py:44.
4. **contour_thickness** — read only in plane.py:512 (contour_line_actor, wired only at plane.py:1591-1593); Cylinder/Circle declare it (objects.py:776,811) but cylinder.py:134,142 goes through plane.contour_actor / mesh_lines_actor.
5. **contour_value** — read only in plane.py:1594; declared for IsosurfaceObject:319 and Cylinder/Circle:775,810, never used.
6. **trim_objects** — read for Plane (plane.py:1057); declared + exposed for Particle (od1:2022/2107) but particle.py never reads it.
7. **display_mats / display_volume_regions** — consumed for surface/plane/volume/cylinder/circle via cell_filter_mask (surface.py:65-66,98-99; plane.py:1525; volume.py:36; cylinder.py:27,92); oilflow/streamline build with `cell_mask=None` (oilflow.py:61, streamline.py:44).

## H. Model fields with no dialog exposure and no consumer (dead in both layers)
arbitrary_normal_r/t/p (objects.py:103-105) · constant_length (:381) · keep_original (:684,:699) ·
vector_space (:330,:422) · usage_line_paint (:114) & usage_color_idx (:115) — dialog writes `usage_lp`/`usage_color` instead ·
show_values (:579, CurveObject; the PointDialog widget named `show_values` maps to probe_show_values at od2:267) ·
pick_show_numbers (:357, PointObject; only the plane's copy is wired).

## I. Reverse gap — render reads it, no dialog field can set it
colorbar_contour / colorbar_vector (plane.py:1601,1607 — PlaneDialog builds empty combos od1:1507-1514, `apply_to` never writes them) ·
ColorbarObject.title/show_title/num_labels/label_color/label_format (colorbar.py:126-150) · GradationObject.control_points (scene.py:246) ·
GraphObject.log_scale/show_legend/variables (graph.py:91-93,26-28) · StreamlineObject.max_steps/seed_spacing/seed_normal (streamline.py:294,454,404) ·
PathlineObject.step_size/files (pathline.py:41) · TurboObject.tolerance/n_r/n_z (turbo.py:74,59-60) · TextObject.anchor_3d/anchor_position (text.py:18,49) ·
PointObject.font_size (point.py:205) · VolumeObject.colorbar (volume.py:142) · CurveObject.show_curve (curve.py:70).

## J. Note on stale doc
`analysis/render_layer.md` (written against an older tree: plane.py 1371 / scene.py 498 lines) claims several of these are
unimplemented; re-grepping shows they ARE implemented now and only partly wired — e.g. `trim_objects` (plane.py:1049-1077),
`cell_filter_mask` for surfaces (surface.py:65-66), `mesh_luster/mesh_water` (plane.py:897-898), automove CSV path (plane.py:1352-1372),
streamline "Both" on the FLD path (streamline.py:326,352), global LUT application (scene.py:195-209). Use the checked lines above.
