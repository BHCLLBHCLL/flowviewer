# flowviewer Data Layer Analysis

**Scope:** `fv/crdl/*` (binary decoders) + `fv/model/*` (data model, FileSet, loader registry).
**Method:** full read of 11 files (2,513 lines total), grep for TODO/FIXME/NYI/NotImplemented/stub markers (zero hits in these packages), cross-check against `DEV_PLAN.md` for scPOST-parity intent.
**Constraint honored:** no source files modified.

---

## 1. Per-file inventory

| File | Lines | Contents |
|---|---|---|
| `fv/__init__.py` | 3 | Package docstring + `__version__ = "0.1.0"`. |
| `fv/crdl/__init__.py` | 35 | Re-exports all `core.py` primitives. |
| `fv/crdl/core.py` | 192 | CRDL-FLD big-endian container primitives (section scan, data-block iteration, typed readers, mmap threshold, cached section index). |
| `fv/crdl/mesh_gph.py` | 805 | GPH/FPH mesh parsing: LS_Nodes (auto endian/dtype), LS_Links polyhedral topology, LS_CvolIdOfElements, LS_VolumeRegions, LS_Parts, LS_SurfaceRegions, LS_Assemblies, volume-region cell masks. |
| `fv/crdl/mesh_fld.py` | 304 | FLD parser: hex8 LS_Elements + LS_MatOfElements, NGON face list + BC plan from LS_SurfaceGeometryArray, per-vertex solution fields, volume names. |
| `fv/crdl/fields.py` | 278 | Field-variable layer: LS_SPHFile cell-centred FPH variables, FLD vertex-centred fields, Cycle meta, particle section detection/parse, format dispatch. |
| `fv/model/__init__.py` | 12 | Re-exports `FieldFile`, `VarInfo`, `Region`, `load_file`, kind constants. |
| `fv/model/dataset.py` | 186 | `FieldFile`/`VarInfo`/`Region` dataclasses, format detection, `load_file`/`fld_only_load`, loader self-registration. |
| `fv/model/objects.py` | 525 | `MainObject` + PostObject family (surface/plane/particle/isosurface/point/streamline/volume/light/colorbar) with scPOST-tab-default fields. |
| `fv/model/fileset.py` | 112 | `FileSet`/`SequenceMember`, `scan_sequence`, lazy cycle/time meta refresh. |
| `fv/model/loaders.py` | 61 | Extension→loader registry, `probe_format`, `describe`. |

### Classes / functions (one-line purpose)

**core.py**
- `LARGE_FILE_BYTES` (const) — mmap threshold (512 MiB).
- `SECTION_BOUNDARY_NAMES` (const) — named sections that can terminate another section (GPH+FLD union).
- `read_i32_be` / `read_f32_be` / `read_f64_be` — scalar big-endian readers.
- `read_f64_wr` — scalar float64 stored word-reversed (middle-endian, legacy GPH).
- `find_section(data, name)` — offset of a section's `[I4=32][32B name]` marker, or −1.
- `_section_index_cache` + `_section_offsets` — per-buffer `{boundary_name: offset}` index built once (keeps buffer alive by `id(data)`).
- `section_end(data, sec_start)` — end offset = next known section start or EOF.
- `iter_data_blocks(data, sec_start, sec_end)` — generator of `(payload_start, byte_count)`; skips 16-byte `[12, tc∈{4,8}, dim0, dim1]` descriptors.
- `open_buffer(filepath)` — ctx mgr: reads files ≤512 MiB, mmaps larger ones read-only.
- `f32_be_array` / `f64_be_array` / `f64_wr_array` / `i32_be_array` — vector readers to native float64/int64 copies.
- `cell_count_from_data` — cell count from first `LS_MatOfElements` block (bytes ÷ 4).

**mesh_gph.py**
- `_score_coord_axes` — plausibility score for candidate coordinate decodes (finite, magnitude, outlier fraction, axis-ratio penalties).
- `ls_nodes_descriptor_elem_bytes` / `ls_nodes_vertex_count_from_descriptors` — descriptor scans (elem size, vertex count).
- `ls_nodes_descriptors` — single numpy pass over descriptor region → `(elem_bytes, vertex_count)`.
- `parse_ls_nodes_xyz` — LS_Nodes → `(xyz N×3 float64, n)`; auto-detects BE f64 / word-reversed f64 / BE f32 by ranking scored candidates.
- `_read_conn_continuations` — LS_Links connector payload continuation blocks (bare `[bc][payload]`, 1 GiB chunks).
- `_group_faces_by_cell_id` — parallel owner/face arrays → `{cell_id: [face_index,…]}`.
- `parse_ls_links` — LS_Links → `{n_faces, npe, face_nodes, face_offsets, owner, neighbour (−1=boundary), boundary_faces, cell_owner_faces, cell_neighbour_faces, n_cells}`.
- `parse_ls_cvol_ids` — LS_CvolIdOfElements → int64 array.
- `parse_ls_string_list` — ASCII strings in a section (used for LS_VolumeRegions).
- `_ls_parts_name_blocks` / `_scan_cvol_descriptor_chain` / `part_cvol_cell_mask` / `_parse_part_cvol_membership` / `_resolve_single_part_cvol` — LS_Parts internals.
- `parse_ls_parts` — LS_Parts → `[(name, PartCvolSpec)]` where spec = single cvol id or frozenset (composite/background parts).
- `parse_ls_surface_regions` — LS_SurfaceRegions → `[(name, gph_face_ids 0-based)]`.
- `parse_ls_assemblies` — LS_Assemblies XML → `{part_paths, root_empty_prefix, has_assemblies, raw_xml}`.
- `classify_volume_region_cells` — Boolean cell mask for a volume-region/part name (`FluidRegion` = all; `@VPartRegion_` / `FPHPARTS.` name mapping; longest-name fallback).
- `_renumber_by_first_use` — vertex permutation to first-use scan order.
- `parse_gph_mesh(filepath)` — public front end; clamps out-of-range face-node ids, renumbers vertices, returns full dict (vertices, link_data, cvol_id, volume_regions, parts, parts_with_cvol, part_assembly, assembly_info, surface_regions, n_cells, file_size).

**mesh_fld.py**
- `_parse_ls_nodes` — LS_Nodes f64 → `(xyz, n)` (most-common block-size trio; no plausibility scoring).
- `_parse_hex_cells` — LS_MatOfElements + LS_Elements → `(cell_conn (n_cells,8) int64, material (n_cells,) int64)`.
- `_f64_field_blocks` — all float64 payloads in a named section.
- `_parse_volume_names` — LS_VolumeGeometryArray 256-byte slot names.
- `_filter_by_mat` / `_build_face_list_and_bcs` — NGON face list + BC plan `(name, start_0based, count)`, splitting MAT1/MAT2 segments.
- `parse_fld(filepath)` — public entry; dict with vertices, cell_conn, material, faces, bc_plan, volume_names, fields.

**fields.py**
- `parse_cycle_meta` — Cycle section → `(cycle_id, time)` (first I4 block, first R8 block).
- `has_particle_results` — detects LS_ParticlesPosition / LS_ParticleV:VELP.
- `parse_particles` — → `(positions, velocities)` (N,3) from 50×float32 payload blocks.
- `parse_fph_flow_solution(data, n_cells)` — LS_SPHFile → `{var: float64 (n_cells,)}`; `EC_Scalar:` → 1 array, `EC_Vector:` → split into `varX/varY/varZ`.
- `parse_fields_from_file` — dispatch by section layout (FLD vs FPH).
- `_fld_vertex_count` / `_estimate_cells` — best-effort counts (no reliable header).
- `_f64_field_blocks` / `_collect_fld_fields` — FLD vertex-field extraction (duplicates mesh_fld logic).

**dataset.py**
- `FIELD_KIND_SCALAR` / `FIELD_KIND_VECTOR` — constants.
- `VarInfo` — one registered variable: `name`, `kind`, `location` ('cell'|'node'|'face'), `array`.
- `Region` — `name` + `face_ids` (int64).
- `FieldFile` — viewable dataset wrapper (fields listed in `3).
- `_looks_like_fld` — presence of LS_Elements/LS_MatOfElements → FLD.
- `_register_loaders` — module side effect registering fld/ifld/fph/gph (best-effort, wrapped in try/except).
- `fld_only_load` — direct FLD path.
- `load_file` — detect + parse → `FieldFile`.
- `_cycle_from_filename` — fallback cycle from trailing filename digits (`tr03_9` → 9).
- `_field_kind` — vector vs scalar by variable name (heuristic).

**objects.py** — see `3 for per-kind fields; module also has `MainObject.from_field_file` (magic open: default Surface(1) all regions + mid-span Plane(1) + Particle(1) if present) and helpers `_short_display_path`, `_bounds`, `_default_plane`, `_point_on_axis`, `_normal_for_axis`.

**fileset.py** — see `4.

**loaders.py** — see `5.

---

## 2. Format support matrix

**Shared container (CRDL-FLD, all big-endian):**
`[I4=8]["CRDL-FLD"][I4=8][dims…]`, then named sections `[I4=32][name padded to 32B][I4=32][body]`. Payloads inside a section: `[I4=12][I4=byte_count][payload][I4=byte_count]`, interleaved with 16-byte descriptors `[12, type_code(4|8), dim0, dim1]` (descriptor vs data-header disambiguated heuristically: dim bounds < 10,000,000, byte-count echo check).

| Format | Parse | Sections consumed | Loader |
|---|---|---|---|
| **FPH** (.fph) | ✅ | LS_Nodes (f32/f64 auto), LS_Links, LS_CvolIdOfElements, LS_VolumeRegions, LS_Parts, LS_SurfaceRegions, LS_Assemblies, LS_SPHFile (EC_Scalar:/EC_Vector:), Cycle, LS_ParticlesPosition / LS_ParticleV:VELP (detected) | `load_file` (fph) |
| **GPH** (.gph) | ✅ | Same mesh/regions/parts sections (geometry; LS_SPHFile typically absent) | `load_file` (gph) |
| **FLD** (.fld) | ✅ | LS_Nodes (f64), LS_Elements, LS_MatOfElements, LS_VolumeGeometryArray, LS_SurfaceGeometryArray, Temperature, CN01, Pressure, VECT, HVEC, Cycle | `fld_only_load` (fld) |
| **iFLD** (.ifld) | ⚠️ partial | Registered to `fld_only_load` — same as FLD; **partial/trimming open is NYI** (DEV_PLAN P4 exploration) | `fld_only_load` (ifld) |
| **EMT** (.emt) | ❌ | Probe only → "fph" family alias; **no loader** | — |
| **CGNS** (.cgns) | ❌ | Probe distinguishes `cgns-hdf5` (h5py) vs `cgns-adf`; **parser not implemented** (`describe` says so) | — |
| XDMF / Nastran / others (GUI filter) | ❌ | Not in registry; `describe` → "no loader registered" | — |
| Neutral file | ❌ | Not referenced anywhere | — |

**Sections recognized as boundaries but NOT parsed** (listed in `SECTION_BOUNDARY_NAMES` only): `LS_CoordinateSystem`, `LS_SolverUnusedRegions`, `LS_SFile`, `LS_STREAMcoc`, `LS_STREAMmultiblock`, `Element_InformationFlag`, `OverlapStart_0`/`OverlapEnd`, header blocks (FileRevision, Application, GridType, Dimension, Bias, Date, Comments, Encoding, HeaderDataEnd, Unused, ReleaseDate).

**Endianness / dtype handling:** everything big-endian. Scalar: `read_i32_be`/`read_f32_be`/`read_f64_be`. Arrays: `f32_be_array` (`>f4`→float64 copy), `f64_be_array` (`>f8`), `i32_be_array` (`>i4`→int64). Special: **word-reversed (middle-endian) float64** supported both scalar (`read_f64_wr`) and vector (`f64_wr_array`, bit-manipulated via uint32 words → `>f8` view). GPH LS_Nodes auto-detection ranks three decodes (BE f64 / WR f64 / BE f32) with a plausibility scorer; FLD assumes plain f64.

**mmap usage:** `open_buffer` mmaps files > 512 MiB (`LARGE_FILE_BYTES`), reads smaller files fully. All parsing operates on bytes/mmap slices; `data.find` used for section markers. Caveat: `_section_index_cache` is keyed by `id(data)` and holds a strong reference to the buffer, so every opened file's buffer stays alive (unbounded memory growth across many files in one process).

**Lazy loading:** per-section lazy parsing (each function locates only its own section), but the file is re-opened per pass — `load_file` opens the buffer twice (mesh, then fields+cycle+particles) and `fld_only_load` twice; `SequenceMember.refresh_meta` opens each member once. No cross-pass buffer reuse, no partial (trimming/remote) reads. GPH vertex renumbering materializes full `(N,3)` float64.

---

## 3. Data model

### FieldFile (fv/model/dataset.py)
| Attribute | Type / meaning |
|---|---|
| `path` | str |
| `kind` | 'fph' | 'fld' |
| `vertices` | (N,3) float64 or None |
| `n_vertices` / `n_cells` | int |
| `link_data` | dict — GPH/FPH LS_Links topology (n_faces, npe, face_nodes, face_offsets, owner, neighbour, boundary_faces, cell_owner_faces, cell_neighbour_faces, n_cells) |
| `cell_conn` | FLD (n_cells,8) int64 |
| `material` | FLD (n_cells,) int64 |
| `faces` | list — NGON face tuples (FLD) |
| `bc_plan` | list[(name, start_0based, count)] (FLD) |
| `surface_regions` | list[(name, face_ids)] (FPH) |
| `volume_regions` | list of region names (strings) |
| `parts` | list of part names |
| `cvol_id` | (n_cells,) int64 or None |
| `parts_with_cvol` | list[(name, PartCvolSpec)] |
| `variables` | dict[str, VarInfo] |
| `file_size` | int |
| `cycle` / `time` | Optional[int] / Optional[float] |
| `has_particles` | bool |
Helpers: `boundary_regions()` → list[Region] (FPH: from surface_regions; FLD: arange over bc_plan), `variable_names()`, `variable_array(name)`.

### VarInfo
`name` (str), `kind` ('scalar' | 'vector'), `location` ('cell' | 'node' | 'face'), `array` (float64 ndarray). Note: **vector kind is only a label** — FPH vector components are stored as three separate `varX/varY/varZ` VarInfos; no component grouping for VTK vector tuples. `'face'` location is declared but never produced (FPH=cell, FLD=node).

### Regions / BC plan
- FPH/GPH: `surface_regions` = [(name, 0-based gph face_ids)]; `volume_regions` = names only — cell masks are computed on demand via `mesh_gph.classify_volume_region_cells` (not exposed on FieldFile).
- FLD: `bc_plan` = [(name, start, count)] into the NGON face list, including MAT1/MAT2 split entries (`@UNDEFINEDENTB(MAT1/2)`, `PARTS(MAT1/2)`, `SURFACE(MAT1/2)`, `Ymax(MAT1/2)`); faces built by a magic-number segmentation of LS_SurfaceGeometryArray blocks (meta1 indices 2,3,7,10–17).

### Cycle / time
`parse_cycle_meta` reads the header Cycle section (first I4 payload = cycle id, first R8 payload = physical time); `load_file`/`fld_only_load` fall back to trailing filename digits (`_cycle_from_filename`). FileSet members refresh the same header lazily.

### PostObject kinds (fv/model/objects.py)
Base `PostObject`: `kind`, `index`, `visible`, `title`, `label` property. (`MainObject` is a separate dataclass, not a PostObject.)

| Kind | Class | Key fields |
|---|---|---|
| main | `MainObject` | path, display_name, cycle, time, has_particles, children: list[PostObject]; classmethod `from_field_file` (magic open → Surface(1) + Plane(1) + optional Particle(1)) |
| surface | `SurfaceObject` | selected_regions, region_mode, display_mats, display_volume_regions, show_contour/contour_var/paint_front/back/transparent, show_vector/vector_var, show_mesh/mesh_color/front/back/thickness, trim_xmin…zmax, integrate_scalar/projected_area, font |
| plane | `PlaneObject` | axis/coordinate/point/normal/arbitrary (spherical R/T/P), rotate, usage_guide/hv/axis/line/color, pick_mode, display_mats/volume_regions, full contour tab, vector tab (location/space/type/scale/thickness/arrow), mesh/boundary/subline, automove (Line/Sin/Cos/Rotation/Custom CSV path), trim (objects + coord ranges), oilflow (var/space/length/draw_type/integration/steps), clip, pick tab, scalar/vector integration, texture, font, colorbar refs |
| particle | `ParticleObject` | show_scalar/scalar_var/value, mono_color, particle_type (Points|Sphere|Specify|Actual), size_px, transparent, show_vector/vector_var/value, intersection_regions, display_particle_no/attribute_no/size, trim_objects, font, special_cloth/special_variable_generalization |
| isosurface | `IsosurfaceObject` | show_contour, contour_var, contour_number/values/auto/value, transparent/line/mono, show_vector/vector_var/scale/space, font, colorbar |
| point | `PointObject` | position, shape (Sphere|Cross|Plus), size, color, transparent, probe_scalar/vector + vars, probe_show_values, pick_show_numbers, font |
| streamline | `StreamlineObject` | seed_center/normal/axis/coordinate/density_u/v/spacing, vector_var, direction (Forward|Backward|Both), constant_length/length, integration_method (Runge-Kutta|Euler), max_steps, step_size, draw_type (Line|Triangle|Tube), color_var, mono_color, transparent, thickness, font |
| volume | `VolumeObject` | display_mats/volume_regions, draw_type (Solid|Transparent|Sampled), show_scalar/scalar_var/opacity/mono, transparent, show_vector/vector_var/scale/space, sampling, font, colorbar |
| light | `LightObject` | kind only (no fields) |
| colorbar | `ColorbarObject` | gradation (256), color_map (Rainbow|Gray|Spectrum|Invert), range_mode (Auto|Fix), min/max, title/show_title, orientation, font, visible, position |

---

## 4. FileSet / sequence scanning (fv/model/fileset.py)

- `_TRAILING_DIGITS = ^(.*?)([0-9]+)$`; `_split_stem('tr03_9')` → `('tr03_', 9)`.
- `scan_sequence(first_file, limit=500)`: takes the first opened file as anchor (directory, extension, stem prefix), globs `{prefix}*.{ext}` in the same directory, keeps only files whose stem ends in digits, builds `SequenceMember(path=absolute, cycle=from filename)`, sorts by cycle. Meta (header Cycle/Time) is **not** read during scan.
- `SequenceMember.refresh_meta()`: lazily opens the file, reads Cycle/Time via `parse_cycle_meta`; silent on error; only overwrites cycle when the header has one.
- `FileSet`: `directory`, `members`; `bool`/`len`; `cycles()`; `min_cycle()`/`max_cycle()` from sorted first/last; `find(cycle)` returns first member with `cycle >= target` (nearest at-or-after; playback wrap handled by caller); `refresh_meta()` refreshes all members.
- **Gap:** no `load_sequence()` / `FileSet→FieldFile` loading in the data layer (DEV_PLAN P3.1 lists `load_sequence` as a target; GUI builds FileSets and drives the Timeline). Cycle ordering is filename-derived until meta refresh. 500-member hard cap.

---

## 5. Loader registry (fv/model/loaders.py)

- `LOADERS: dict[str, Callable]` — extension (lowercase, no dot) → loader fn returning a FieldFile.
- Registered formats (populated at import time by the module side effect `dataset._register_loaders()`): **fld, ifld** → `fld_only_load`; **fph, gph** → `load_file`. (Registration is wrapped in try/except "best-effort".)
- `can_load(path)` — suffix ∈ registry.
- `probe_format(path)` — suffix-based diagnostic tag: `cgns` → `cgns-hdf5` (h5py.is_hdf5) or `cgns-adf` (ImportError → bare `cgns`); `fph`/`gph`/`emt` → `fph` (EMT = Cradle binary, fph-family alias); `fld`/`ifld` → `fld`; else `other`.
- `describe(path)` — loadable → `"loadable (fld, fph, gph, ifld)"`; CGNS → `"CGNS file detected (tag) — parser not yet implemented"`; other → `"<ext> — no loader registered"`.

---

## 6. Gaps & observations

**Stub markers:** grep for TODO/FIXME/NYI/NotImplemented/_nyi/pass-#-stub across both packages → **zero hits**. Stubs are behavioral, not annotated:

1. **CGNS parser missing** — probe + describe only; the GUI filter advertises it (scPOST catalogue parity) but `describe` admits "parser not yet implemented".
2. **EMT** — probed as fph-family alias but no loader registered; DEV_PLAN lists "EMT alias" as an increment item.
3. **iFLD partial read NYI** — registered as a plain FLD loader; Trimming Open / Remote Open (DEV_PLAN P4, 2025.2 manual) not implemented.
4. **No time-series object** — scPOST TimeSeries / cycle-graph data object absent; only `PlaneObject.pick_cycle_graph` flag hints at it.
5. **No max/min file** handling (.max/.min) anywhere in the data layer.
6. **No variable-registration / expression engine** — scPOST "define calculated variable" unsupported; `_field_kind` is a name heuristic and vectors are stored as split `varX/Y/Z` scalars, never grouped into VTK vector tuples.
7. **No neutral file** support (not even probed).
8. **FPH material data absent** — `LS_MatOfElements` is only parsed for FLD; FPH surfaces are face-id lists, and volume-region cell masks depend on cvol_id/parts heuristics.
9. **Unparsed recognized sections** — LS_SFile, LS_STREAMcoc/multiblock (streamlines), LS_CoordinateSystem, LS_SolverUnusedRegions, Element_InformationFlag exist only as boundary names.
10. **Particles decoupled** — `fields.parse_particles` exists but `FieldFile` only carries `has_particles`; the render layer must re-open the file to call it (no cached arrays).
11. **Duplicated FLD field logic** — `_collect_fld_fields` (fields.py) ≈ `parse_fld` field section (mesh_fld.py); drift risk.
12. **Multiple re-opens per load** — `load_file` opens the buffer 2×, `fld_only_load` 2×; no single-buffer reuse across mesh+fields+meta passes.
13. **Section-index cache holds buffers** — `_section_index_cache` keyed by `id(data)` with a strong ref; unbounded retention when many files are opened.
14. **Heuristic brittleness** — `iter_data_blocks` descriptor detection (dim bounds, byte-count echo), FLD face-list segmentation magic indices (meta1[2,3,7,10–17]), FLD `_parse_ls_nodes` picks the most-common block size with no plausibility scoring (unlike GPH's `_score_coord_axes`).
15. **No units, no variable metadata** (min/max/component mapping) beyond name strings.
16. **FieldFile.volume_regions** is names-only for both formats; cell-mask classification lives in crdl and isn't exposed on the model object.
