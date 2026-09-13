
# DATA/DECODER LAYER AUDIT — flowviewer (`fv/crdl/*`, `fv/model/*`) vs scPOST 2025.2

Auditor: delegated subagent. Every claim below comes from source reading **plus executed probes** on real corpus
files under `D:\training\cgns\examples\` and `D:\training\cradle\laptop\` (Anaconda python 3.12, h5py 3.11,
numpy 1.26, pyNastran 1.4.1, scipy 1.13). Items marked *(measured)* were produced by running the project's own
code. Project docs (`analysis/*.md`) were used only to locate claims, never as evidence.

## 0. Baseline framing

* scPOST's string table names only **`.fld`, `.fph`, `.gph`** as Cradle field files
  (`analysis/scpost_strings.txt:194-196`, `:2722-2724`; directory globs `:591-592`).
* Case-insensitive grep for `rph` over the whole repo: **no hit** (only false positives such as `AfterPhotoDraw`).
  There is no scPOST baseline for `.rph`; it exists only as sample data
  (`D:\training\cgns\examples\laptop_thermal_steady_scaled_v3_100.rph`, 1.12 GB).
* CGNS / XDMF / Nastran / Marc / neutral / CVFF / TSER are **beyond-baseline** additions — no scPOST reference,
  so only internal correctness can be judged for them.
* Corpus used: `ex1_100.fld` (4.2 MB), `tr03_9.fph` (18 MB), `tr03.gph` (16.6 MB),
  `laptop_simplified_voxel_less.gph` (69 MB), `laptop_thermal_steady_scaled_v3_200.fph` (1.36 GB),
  `*.rph` (1.1–2.0 GB), 5 HDF5 CGNS files (`tr03_9.cgns` 60 MB), `tests/data/plate_py.op2`/`plate_py.dat`,
  `tests/pytest_tmp/**/*.cgns` (ADF), `CradleCFD_2023.2_ST_Example/*_tm.csv`/`*.ot`.

## 1. Format coverage matrix

| Format | Loader (file) | Status | Decoded | Ignored / wrong | Evidence |
|---|---|---|---|---|---|
| **FLD** `.fld` | `fv/crdl/mesh_fld.py:660` + `fv/crdl/fields.py` | **partial** | container header; `LS_Nodes` (f64/f32, descriptor-guided); `LS_MatOfElements`; `LS_Elements` (hex/wedge/pyra/tet, mixed codes 34/35/36/38, descriptor-dense "minimal" variant); `LS_SurfaceGeometryArray` → NGON face list + reconstructed BC plan; `LS_VolumeGeometryArray` (best-effort); fields `Pressure/Temperature/CN01/VECT/HVEC` **by block index**; `Cycle` (cycle+time); particle sections; named BC-zone payloads; header meta | `LS_Scalar:<V>`/`LS_Vector:<V>` name+title sections; `LS_RegionName&Type`; `AMOM(*)` BC zones; `LS_STREAMcoc`/`LS_STREAMmultiblock`; `OverlapStart_0`/`OverlapEnd`; `Unit:$TEMP` units; `LS_SFile` body (SDAT magic only) | `ex1_100.fld` section list *(measured)*: `LS_Scalar:PRES`@1776, `LS_RegionName&Type`@4237019, `AMOM(noslip)`@4237599, `LS_STREAMcoc`@2372312 — none parsed. `mesh_fld.py:469-471` lacks `AMOM(` → 9 BC zones in file, 7 returned, AMOM×2 dropped *(measured)* |
| **FPH** `.fph` | `mesh_gph.py:813` + `fields.py:226` | **partial (deep mesh, shallow fields)** | `LS_Nodes` (f32/f64/word-reversed, heuristic dialect pick), `LS_Links` (owner/neighbour/npe/face nodes + 1 GiB continuation blocks), `LS_CvolIdOfElements`, `LS_Parts`, `LS_VolumeRegions`, `LS_SurfaceRegions`, `LS_Assemblies` XML, `Element_InformationFlag`, `Element_Center`; `LS_SPHFile` `EC_Scalar:*`/`EC_Vector:*` (f32); `Cycle`; `LS_ParticlesPosition`, `LS_ParticleV:*` | **`FC_Scalar:*` / `FC_Vector:*` (face-centred) silently dropped** — on `tr03_9.fph` 6 FC variables (YPLS, USTR, …) are in the file and absent from the result *(measured; filter `fields.py:253`)*; `LS_MaterialOfParts`; `LS_SolverUnusedRegions`; per-zone BC settings; unit semantics; only the **last** nodal/particle frame kept (`fields.py:162-171`) | `fields.py:253`; treated section inventory of `tr03_9.fph` *(measured)*; `mesh_gph.py:845-848` |
| **GPH** `.gph` | same | **partial** | mesh + parts/regions/assemblies | **no field sections at all** | *(measured)* 69 MB `laptop…voxel_less.gph` → 629 637 v / 482 034 c / 15 surface regions / **0 variables** |
| **iFLD** `.ifld` | `fv/crdl/ifld.py:15` + `dataset.py:457` | **partial / alias** | full FLD parse + `_scan` summary (`n_cells`, `n_vertices`, 5 hardcoded variable names) + optional spatial trim | no metadata-only fast path; with `bounds` the **geometry is fully materialised before trimming** (`mesh_fld.py:695-698` then `:713-734`) → "true partial load" (P1-3) is false for mesh data; `_scan`'s vertex count = "largest block not 4/8 bytes" → wrong on f32 files | `ifld.py:24-49`, `:54-119`; `dataset.py:473-487` |
| **PPH** `.pph` | `fv/crdl/pph.py:43` | **partial (mesh only)** | zip member list, `main.xml` project name, largest `*.gph` member → `parse_gph_mesh` | `main.js/main.prp/main.sctsnapshot/main.xenv`, `<group>_part.mdl`/`_ridge.mdl` display geometry, `<group>.oct` octree, all project settings | `pph.py:23-76` (docstring admits the omissions); `dataset.py:433-454` |
| **CGNS-HDF5** `.cgns` | `fv/crdl/cgns.py:490` | **stub for the real corpus** (partial for single-Elements files) | first zone-bearing base; `GridCoordinates`; `Elements_t` with **string** `ElementType` or int code; `MIXED` stream; Structured→HEXA_8 via dims; `FlowSolution`; `ZoneBC/PointList`; multi-zone merge with NaN padding | **`NGON_n`(22)/`NFACE_n`(23) polyhedral sections → 0 cells**; `ElementType` read from the node data array only (`_CODE_TO_NAME` has no 22/23); only the **first** base; `PointRange` BCs; `GridLocation` misread as a variable; `BaseIterativeData`/time; `ElementStartOffset`, `ParentData`; BC face list; `ZoneType` never decoded correctly | *(measured)* `read_cgns("tr03_9.cgns")` → `n_vertices 473983, n_cells 0, fields {'GridLocation'}`; same for `box_ansa_fph_test.cgns`, `_copy_default.cgns`. `cgns.py:516-527` (first base only, `break`); `cgns.py:27-30` |
| **CGNS-ADF** `.cgns` (AdF0) | `fv/crdl/cgns_adf.py:534`, reader `:144` | **partial** | full ADF tree (mmap, chunk tables, B/L/N endianness), **all** `CGNSBase_t`/zones, coordinates, volume sections, `MIXED`, Structured, `FlowSolution`, `ZoneBC` PointList | same NGON_n/NFACE_n hole (`_read_cells_adf` reuses `cgns.py:_VOLUME_TYPES`); `PointRange` treated as an id list → range 1..100 becomes **2** ids `[0,99]` *(measured, `cgns_adf.py:456-460`)*; ADF links; time data | `cgns_adf.py:364-392`, `:447-461`, `:553-601`, `:641-654` |
| **XDMF** `.xdmf/.xmf` | `fv/crdl/xdmf.py:121` | **partial, fragile** | inline XML DataItems; HDF5 DataItems with *relative* paths; Hexahedron/Tetrahedron/Wedge/Pyramid/Triangle/Quadrilateral; `Attribute` by size; temporal collections (first frame + frame list) | unknown `TopologyType` ⇒ **silently assumed HEXA_8** → `ValueError: cannot reshape array of size 4 into shape (8)` escapes `xdmf_load` *(measured)*; **absolute HDF paths fail on Windows** — `partition(":")` splits the drive letter, grid skipped, `parse_xdmf` returns None *(measured)*; `<Time>` on a non-collection grid ignored *(measured)*; `X_Y_Z`/`VXVYVZ` geometry, `Mixed`/`Polyhedron`/`Node`/`Edge` topology, `Center="Edge"/"Face"`, `Information`, `XInclude` unreachable; deprecated `np.fromstring` at `:42` | `xdmf.py:9-16`, `:26-38`, `:39-45`, `:54-55` |
| **Nastran `.nas/.bdf`** | `fv/crdl/nastran.py:17` | **stub** | free-field comma `GRID` + `CHEXA/CTETRA/CPENTA/CPYRAM` only | **fixed-field (8-column) decks unsupported** — `plate_py.dat`, the repo's only real deck, returns None *(measured)*; `CQUAD4/CQUAD8/CTRIA3/CTRIA6/CROD/CBAR` absent from `_VTK` (`nastran.py:13-14`) → shell models yield 0 cells; continuation lines, `GRID*`, coordinate systems (`CORD2C`), RBE/SPC/MPC, properties, case control | `nastran.py:13-14`, `:22-45`; `parse_nastran("tests/data/plate_py.dat") → None` *(measured)* |
| **Nastran `.op2`** | `fv/crdl/op2.py:178` | **partial (dep-gated)** | via pyNastran: geometry (nodes + solids/shells/rods from `_VTK_FOR`), sidecar `.dat/.bdf/.nas` geometry, eigenvectors → `MODE<n>` node **magnitudes**, displacements → `DISPMAG(SUB<n>)`, solid stress families → `VONMISES(SUB<n>)` cell | no vectors (magnitude only, `op2.py:107`), no eigen-frequency metadata, no time/cycle, no shell/beam stresses, no strain/force/thermal tables (they exist in the table list *(measured)*), `MODE<n>` keys collide across subcases (`op2.py:139-146`), `vm[:n_cells]` truncates the stress array onto geometry element order (`op2.py:174`), node coords prefer `xyz` over `xyz_cid0` → wrong for CD≠0 (`op2.py:50-54`) | *(measured)* `plate_py.op2` → 231 v / 200 CQUAD4 / `MODE1..MODE10` (231 finite each); `displacements: []` |
| **Marc `.dat`** | `fv/crdl/marc.py:82` | **partial** | Mentat `connectivity`/`coordinates`; comma fallback; `elements <type>` default; node/element id mapping | all other Mentat blocks (materials, BCs, load steps); **planar meshes silently re-typed 2-D**: `ncrd = 2 if all(|z|<1e-12)` (`marc.py:178`) → a hex mesh lying in z=0 becomes QUAD4 with 4 nodes dropped *(measured)* | `marc.py:124-191`, `:774-813` |
| **Marc `.t16/.t19`** | `marc.py:280` | **partial** | PLDUMP-2000 `=beg=` text/binary section splitter; 50200/506xx/507xx/50800/517xx/518xx/52300/524xx; last-increment nodal vector; element post-codes; increment table (times) | only **one** nodal quantity (last block found, `marc.py:517-527`); only the **last** increment's data; K7 classic path is record-size sniffing (`:831-867`); tensor families beyond `52300`; no `=end=` validation | `marc.py:434-584`, `:645-693`, `:816-912` |
| **Marc `.res/.csv`** | `dataset.py:419-430` | **stub** | node-id → scalar columns (`RES1..n`) sibling import | titles/column names, element results, per-increment | `marc.py:218-266` |
| **Neutral OBJ** | `neutral.py:14` | **partial** | `v`, `f` (n-gons kept, no triangulation) | `vt/vn/usemtl/o/g/s`; relative (negative) OBJ indices off by one: `int(tok)-1` (`neutral.py:30`) maps `-1` to `-2` semantics | `neutral.py:24-32` |
| **Neutral STL** | `neutral.py:38` | **stub** | ASCII `vertex…endfacet` only; **no vertex dedup** (3 new vertices per triangle) | **binary STL (the common case) unreadable** → `parse_stl` returns None → `neutral_load` raises "not a readable neutral mesh" *(measured)* | `neutral.py:38-59`; `dataset.py:290-291` |
| **Neutral PLY** | `neutral.py:108` | **partial** | ascii + binary LE/BE, per-vertex scalar properties → node variables | element/face properties, texture coords, non-face list props, other elements, per-face scalars; binary reader is a per-property Python `struct.unpack_from` loop (`:201-210`) | `neutral.py:62-219` |
| **Neutral `.neu`** | registered to `neutral_load` (`dataset.py:524`) | **misregistered** | nothing — `.neu` is routed to `parse_stl` (`dataset.py:290-291`) and only "works" if the file is ASCII STL | whole HyperMesh format | `dataset.py:524`, `neutral.py:38` |
| **CVFF** `.CradleViewer/.cvw` | `fv/crdl/cvff.py:506` + `dataset.py:308` | **implemented, geometry only (no fields)** | header, block chain, TREE (UTF-16), common records 1-8 (incl. 4×4 matrix), POLY/LINE (bbox-quantised u16 verts + aux), PNT, PTC3 particles, TEX, BTN icons, LIGH, FLD camera/model range, ENV/ENCD/LOGO verbatim | **4×4 `props.matrix` parsed but never applied** (loader asserts "already in model space", `dataset.py:314-317`); `aux` normals/UV unused; textures/icons/lights not exposed; particles only in `meta["cvff_particles"]`; no scalar/vector fields; no index validation in `_faces_from` | `cvff.py:252-289`, `:341-373`, `:403-500`, `:506-546`; `dataset.py:331-383` |
| **TSER / CRDL-OT (tsmm)** | `fv/model/tsmm.py:69`/`:168` | **partial, not registered** | `TSER` probe table + CYCL/TIME columns; `CRDL-OT` PARTS blocks; CSV fallbacks | `.tm`/`.ot` absent from `LOADERS` (`dataset.py:507-534`) so `can_load/probe_format` report nothing; column↔probe pairing is **positional** (`tsmm.py:119-126`) → mislabeled columns; OT cycle numbers synthesised (`tsmm.py:185`) | `tsmm.py:83-138`, `:181-222`; `loaders.py:33-73` |
| **RPH** `.rph` | — | **not implemented** | — | everything: the file **is a CRDL-FLD container** (`\x00\x00\x00\x08CRDL-FLD` *(measured)*) with sections `FileSpec`, `Ph_R1_BasicData1`, `EL_Data:VEL[0]…`; not in `LOADERS`, not in `probe_format`, no RPH name in `SECTION_BOUNDARY_NAMES` | `loaders.py:33-73`; `core.py:29-42`; *(measured)* header + section dump of both `.rph` samples |
| **EMT** `.emt` | `dataset.py:517` | **stub/alias** | routed to `load_file` as an FPH-family CRDL file; no sample, no dedicated decode | everything format-specific | `dataset.py:517`, `loaders.py:59-60` |

### 1b. Silent "empty load" for anything unregistered (verified)

`load_file` (`dataset.py:643-719`) falls through to `mesh_gph.parse_gph_mesh` for **any** extension not in the
registry; with no `LS_Nodes`/`LS_Links` found, `parse_gph_mesh` returns `vertices=None` and the function returns a
**FieldFile(kind="fph", 0 vertices / 0 cells / 0 variables) without raising**. *(measured)* a 1.3 KB random
`.txt` → empty FieldFile; a **1.12 GB `.rph` → empty FieldFile after a 9.8 s full-file scan**. There is no
"unrecognised format" error path.

## 2. What each format skips (detail)

**FLD**
* `LS_Scalar:<NAME>` / `LS_Vector:<NAME>` sections (authoritative name + the following 32-byte title block, e.g.
  `Turbulence K`, `WALL HEAT FLUX`) are never read; variables are hardcoded and located **by block index**:
  `temp_blocks[0]/[3]/[6]`, `cn01_blocks[0]/[3]/[6]/[9]`, `vect_blocks[:3]` (`mesh_fld.py:824-850`; lazy twin
  `:771-795`). Any layout drift renames fields silently — the `_size_ok` guard only rejects length mismatches.
* `ATMS` is fabricated as a **copy of `TEMP`** (`mesh_fld.py:828-829`, `fields.py:363-364`) — the GUI shows a
  variable that does not exist in the file.
* `LS_RegionName&Type` (region name → type/display-name table) unparsed; the BC plan is a *reconstruction*
  (labels `@UNDEFINEDENTB/PARTS/SURFACE/Xmax…`, `mesh_fld.py:347-466`) whose segment counts come from a
  positional `meta1[2..17]` descriptor list — a different writer layout silently yields wrong sizes.
* Region display names are 18-byte **UTF-8** fields decoded with `errors="replace"` as ASCII (`mesh_fld.py:414-416`)
  → `Xmax面` becomes `Xmax\ufffd\ufffd\ufffd` *(measured in `bc_plan`)*.
* `_parse_volume_names` requires a ≥256-byte fully-printable block (`mesh_fld.py:310`); on `ex1_100.fld` the
  1024-byte name block contains the same UTF-8 bytes → returns `[]` → **volume region names lost** *(measured:
  `volume_names []` although `LS_VolumeGeometryArray` holds `PARTS1` plus a 145 920-byte per-cell region map)*.
* `section_end` over-extends because `SECTION_BOUNDARY_NAMES` (`core.py:29-42`) lacks `LS_RegionName&Type`,
  `LS_Scalar:*`, `Element_Center`, `FC_*`, `LS_MaterialOfParts`, `FileSpec`, …: *(measured)*
  `LS_SurfaceGeometryArray`@3758447 → end 4238129 (= `LS_SFile`), swallowing `LS_RegionName&Type` + 9 BC zones;
  the BC parser then relies on `blocks[8:]` + `bc == 18` scanning inside that span (`mesh_fld.py:414`).
* `OverlapStart_0`/`OverlapEnd` (multi-block/CHT overlap) ignored → overlapping zones neither detected nor stitched.
* `has_particle_results`/`parse_particle_variable_frames` locate sections by raw `data.find` on name bytes
  (`fields.py:75-85`, `:189-196`) — a name-like byte pattern inside float payload is a false-positive risk.

**FPH/GPH**
* Face-centred (`FC_*`) variables dropped (see matrix); `LS_MaterialOfParts` (23/6/6 B in `tr03_9.fph`, *(measured)*) unparsed.
* `n_cells` inferred as `max(owner)+1` (`mesh_gph.py:459`) — no cross-check against `LS_CvolIdOfElements`; sparse or
  1-based owner ids silently give a wrong cell count.
* Out-of-range face nodes **clamped to `n_vertices-1`** (`mesh_gph.py:862-867`) — silent geometry corruption. Vertices
  are then renumbered by first use (`:869-872`), so "vertex id" ≠ file order for any consumer that assumes it.
* Word-reversed float64 coordinates get a `[:, [0,2,1]]` **Y/Z axis swap** (`mesh_gph.py:238-241`) — a heuristic that is
  wrong whenever the file's word order is a plain byte swap.
* `LS_Links` block identification = "most common size appearing ≥3×" (`mesh_gph.py:383-392`), connectivity block =
  "largest remaining block" fallback (`:424-432`) — no structural validation.
* `boundary_faces` materialised as a Python list (`np.flatnonzero(...).tolist()`, `mesh_gph.py:474`): ≈204 k ints on the
  482 k-cell sample, ≈7 M on the 6.8 M-cell sample.

**CGNS (HDF5 + ADF)**
* Polyhedral (`NGON_n`=22, `NFACE_n`=23, `ElementStartOffset`, negative face refs) is the format of **every** real
  HDF5 sample → 0 cells, no fields *(measured)*. `_CODE_TO_NAME` (`cgns.py:27-30`) knows only 3/5/7/10/12/14/17/20.
* MIXED stream type table **wrong for pyramid/penta**: `_CODE_CELLS` (`cgns.py:33-41`) maps 13→(PENTA_6,6) and
  14→(PYRA_5,5); CGNS 4.5.1 SIDS (`CGNS-4.5.1/src/cgnslib.h:764-775`) is `PYRA_5=12, PYRA_14=13, PENTA_6=14`. A code-14
  PENTA_6 is consumed as a 5-node pyramid (6 words) → stream desync, later elements lost: *(measured)*
  `[5,1,2,3, 14,1,2,3,4,5,6, 17,…]` → 2 rows / 12 of 20 words, types `[5,14]` instead of `[5,13,12]`.
* Only the **first** zone-bearing base is read (`cgns.py:516-527`, `break`); the ADF path reads **all** bases
  (`cgns_adf.py:553-562`) → the two backends disagree on the same model.
* `ZoneType` decoded via `b"".join(np.asarray(arr).ravel())` (`cgns.py:114`, `:97`), which raises TypeError on h5py
  integer byte arrays → swallowed by `except`, so every zone falls back to "Unstructured" *(measured:
  `_attr_text(ZoneType,'data') == ''` on a real Unstructured zone)*. A real Structured zone would be decoded with the
  unstructured branch (`cgns.py:342-353`) → vertices, no cells.
* `FlowSolution` children are all treated as variables, including `GridLocation`/`Descriptor` (`cgns.py:275-298`) →
  *(measured)* `fields = {'GridLocation': …}` (all-NaN float garbage) exposed as a variable on every real sample; the
  `GridLocation` node is never used to *place* fields.
* `ZoneBC/PointList` returned as `ids-1` with no face list carried by the loader (`cgns.py:302-320`); `PointRange`
  unhandled in HDF5 and mis-handled in ADF (`cgns_adf.py:456-460`, measured `[1,100] → [0,99]`). Because
  `FieldFile.poly` is False for `kind="cgns"` (`dataset.py:66-68`), `boundary_regions()` (`dataset.py:112-117`)
  ignores `surface_regions` and returns **empty** → CGNS BCs never reach the surface renderer (`render/surface.py:130`).
* `is_cgns_hdf5` contains a dead expression `any("ZoneType" in (g or {}) for g in [])` (`cgns.py:625-628`);
  `_read_bcs(zone, n_faces)` ignores its second argument (`cgns.py:302`).

**Others** — see matrix rows: single-topology assumption (XDMF), fixed-field/continuation cards (Nastran), planar⇒2-D
re-typing (Marc), binary STL / no dedup (neutral), ignored transforms (CVFF), positional probe pairing (TSER),
`.neu` misregistration.

## 3. Analysis / derived-variable engine vs scPOST `CreateVar`

### 3.1 Registered operators and functions (`fv/model/varreg.py`)

| Kind | Names | Location |
|---|---|---|
| binary ops | `+ - * / ^ & @` (`^`=power, `&`=and, `@`=or) | `varreg.py:32`, `:119-160` |
| unary | `-` (and `+` accepted) | `:49`, `:162-167` |
| functions (arity) | `abs(1) sqrt(1) min(2) max(2) mag(1) ifgt(2) ifet(2) ifeq(2) iflt(2) ifle(2) ifne(2) log(1) exp(1) sin(1)` | `:34-39`, `:255-294` |
| differential ops | `delx/dely/delz(V)`, `grad(V)`, `div(VEC)` or `div(UX,UY,UZ)`, `rot(VEC)` or `rot(UX,UY,UZ)` | `:41-47`, `:213-253` |
| registration API | `register_variable`, `register_derived_function` (python callable), `auto_scalarize` (`<BASE>_mag`, `<BASE>_X/Y/Z`), `delete_variable`, `set_variable_title`, `register_var_all_cycles` | `:306-333`, `:708-741`, `:769-787`, `:675-686`, `:688-705` |
| extended variables | `register_dst` (DST), `register_normal` (NORMALX/Y/Z), `register_combination_velocity` (CMBVEL) | `:594-655`, `:658-672` |
| vortex presets (`fv/model/derived.py`) | `velocity_gradient`, `VGRADXX…VGRADZZ` (9 scalars), `VORT` (vector), `QCRIT`, `LAMBDA2`, `HELI`; Green–Gauss kernels for FPH (face-based) and FLD/CGNS (per-cell + vertex average) | `derived.py:104-167`, `:190-254`, `:349-421` |

Not present: any trigonometric set beyond `sin` (`cos/tan/asin/acos/atan`), `tanh`, `atan2`, `floor/ceil/round`,
`sign`, `pow` as a function, `average/integral` operators, region-scoped reduction/averaging operators.

### 3.2 scPOST `CreateVar*` family vs this implementation

Local baseline evidence: `analysis/vb_fldfile.txt:749-839` (signatures) and `analysis/scpost_strings.txt:2520` —
the only expression fragment in the string table, `CreateVar(newLNAM, info, text)` with `ifeq(…)`.

| scPOST | Local | Verdict |
|---|---|---|
| `CreateVar(newLNAM, info, text)` — 3 args (short name, **long name**, equation) | `com.py:1637 CreateVar(lnam, expr)`; a title needs a separate `SetVarTitle` | **signature mismatch**; scripts passing 3 args break. `r30_coverage_matrix.md:40` marks it "OK(exact)" — false |
| `CreateVarALLCYC(lnam)` — collect an existing variable over all cycles | `com.py:1645 CreateVarALLCYC(lnam, expr)` → `register_var_all_cycles` re-evaluates an expression per member (`varreg.py:688-705`) | **semantics differ** (aggregation vs re-registration); extra required arg |
| `CreateVarCombinationVelocity(static_lnam, volid_array, lnam_array)` — combine static + rotating-region vectors | `com.py:1661-1669` accepts and **ignores** both arrays; `register_combination_velocity` returns `sqrt(VELX²+VELY²+VELZ²)` (scalar speed) | **degenerate/wrong**: the rotating-frame combination is not implemented |
| `CreateVarDST(maxlen)` — max distance from wall, all-region if negative | `register_dst` has no `maxlen`; `com.py:1671-1677` drops it | clipping/max-length semantics missing |
| `CreateVarDST2(surfaces, maxlen)` | `com.py:1679-1692` maps `surfaces`→`surface_regions`, **ignores `maxlen`** | partial |
| `CreateVarNORMAL(region_names)` | `com.py:1694-1705` → `register_normal` | implemented (FPH only — see 3.3/4) |
| — | `DeleteVar` (`varreg.py:675`), `SetVarTitle` (`:680`) | present |

### 3.3 Wrong or degenerate items (each verified by running the code)

1. **`^` has the precedence of `*` and `/`** (`varreg.py:146-160`, left-assoc): *(measured)* `2*3^2 → 36` (should be
   18), `4/2^2 → 4` (should be 1), `-2^2 → 4` (should be −4). Silently wrong user expressions.
2. **`_source_location` matches variable names as substrings of the expression** (`varreg.py:363-370`): *(measured)*
   with `PRES`(node) and `PRESSURE`(cell) both present, `PRESSURE*2` is registered with `location="node"` → the
   renderer samples the field against the wrong geometry/array.
3. **Operand lengths are never validated** (`varreg.py:299-333`): *(measured)* `A(3 cells) + B(1)` → `[11,12,13]` with
   `location="cell"` — a silent broadcast instead of an error.
4. **DST/NORMAL are unreachable for non-polyhedral files**: `_wall_points` fills ids only inside
   `if getattr(ff, "poly", False)` (`varreg.py:582-588`), so the FLD branch at `:616-620` advertised in the docstring
   is dead code; *(measured)* `register_dst(fld_only_load("ex1_100.fld"))` → `ValueError: no wall faces for DST` even
   though the file has 16 BC regions. FLD never populates `surface_regions` (`dataset.py:583-585` sets only `bc_plan`).
5. **DST measures distance to wall *vertices*, not wall faces** (`varreg.py:575-591`, cKDTree over a point cloud) →
   systematically overestimates near concave walls; `NORMAL` degenerates to `(0,0,0)` exactly at wall points (`:649-651`).
6. **`ifet` ≡ `>=`** (`varreg.py:276-277`) although the name reads "if equal to" and `ifeq` also exists — a user trap.
   (scPOST's own meaning is not recoverable from local evidence; flagged, not asserted.)
7. **Differential operators rely on a 0/1-base guess** (`varreg.py:424-437`, `derived.py:172-187`,
   `mesh_fld.py:606-609`): *(measured)* 1-based connectivity with **one unused trailing vertex** (n_vertices 13, ids
   1..12) is treated as 0-based → adjacency shifted by one node → `dT/dy` of `T=y` returns **0.0 at all 13 nodes** with
   no exception; with a shorter vertex array it raises `IndexError: index 12 is out of bounds`.
8. **Vector detection is a hardcoded name list** (`dataset.py:731-736`): only `VEL*/VECT*/HVEC*` become
   `FIELD_KIND_VECTOR`. *(measured)* on `tr03_9.fph` `LNAM_RV001X/Y/Z` stay scalars, `_resolved_vars` builds no base,
   and `mag(LNAM_RV001)` raises `unknown variable or function` while `mag(VEL)` works.
9. `_cell_centers_fph` fallback (`varreg.py:551-570`) is a per-cell Python loop over `ld["cell_owner_faces"].items()`
   → *(measured)* 20.8 s for 482 k cells.
10. `derived._conn_green_gauss_node` (`derived.py:222-250`) is a per-cell Python loop with per-face numpy ops —
    structurally correct, unusable at multi-million-cell scale.
11. No unit or basis handling anywhere: `Unit:$TEMP` is parsed as a *name list* only (`core.py:146`) and the header
    `Dimension` is broken (see 4/15), so 2-D/3-D and units are implicit.
12. `derived` boundary behaviour: for FPH the boundary face value is a one-sided copy of the owner cell
    (`derived.py:145-150`), so ω/Q/λ₂ at boundary cells are first-order only (documented, but it matters when
    comparing against scPOST).

## 4. Numerical correctness risks (ranked by "silently wrong")

| # | Risk | Where | Consequence | Evidence |
|---|---|---|---|---|
| 1 | CGNS MIXED type codes 13/14 swapped vs SIDS | `cgns.py:33-41` | stream desync, wrong cells, lost elements — **silent** | measured decode vs `cgnslib.h:764-775` |
| 2 | varreg 0/1-base guess fails with an unused trailing vertex | `varreg.py:424-437` | all differentials shifted → zero/wrong gradients — **silent** | measured: 13/13 nodes wrong |
| 3 | `^` precedence | `varreg.py:146-160` | wrong derived variables — **silent** | measured 36 vs 18 |
| 4 | expression location via substring match | `varreg.py:363-370` | cell field rendered as node field — **silent** | measured |
| 5 | CGNS polyhedral ⇒ 0 cells; `GridLocation` exposed as a variable | `cgns.py:180-218`, `:275-298` | "successful" load of an empty model | measured on 3 real files |
| 6 | Marc planar ⇒ 2-D re-typing | `marc.py:178`, `:774-813` | hex→quad, nodes dropped | measured |
| 7 | `compare.difference_field` treats equal *shapes* as the same mesh/location | `compare.py:124-126` | differences two unrelated meshes element-wise, or node−cell | code; no mesh/location check |
| 8 | OP2 `vm[:n_cells]` truncation; `MODE<n>` key collisions | `op2.py:174`, `:139-146` | stress attached to the wrong cells; modes overwritten across subcases | code |
| 9 | GPH out-of-range node clamp + first-use renumbering | `mesh_gph.py:862-872` | corrupted geometry, id/order mismatch vs file | code |
| 10 | PPH picks the largest `.gph` member, ignores group identity | `pph.py:55-59` | wrong mesh when several groups exist | code |
| 11 | FLD fields mapped by positional block index | `mesh_fld.py:824-850` | layout drift renames variables | measured layout (32-byte titles interleaved) |
| 12 | `ATMS` == `TEMP` alias | `mesh_fld.py:828-829` | fabricated variable shown to the user | code + file has only TEMP/TURK/TEPS |
| 13 | `topology.volume_of_element` sums `abs(det)/6` | `topology.py:305-313` | wrong volume for non-convex cells | code |
| 14 | `topology.elements_of_region` returns all-False for non-poly meshes | `topology.py:226-237` | silently empty region selections on FLD/CGNS | code |
| 15 | header metadata: `Dimension`=`1x1`, `FileRevision`=`1x1`, … | `core.py:149-193` | shape descriptor reported instead of the value; `Dimension` should be 3 | measured on `ex1_100.fld` |
| 16 | CVFF 4×4 transform ignored, u16-quantised vertices, no index validation | `dataset.py:314-317`, `cvff.py:341-373` | misplaced/corrupt geometry | code |
| 17 | TSER column↔probe pairing positional; OT cycles synthesised | `tsmm.py:119-126`, `:185` | mislabeled time-series columns and cycle numbers | code |
| 18 | f32-vs-f64 and BE-vs-word-reversed coordinate choice is a *scored heuristic* | `mesh_gph.py:189-241`, `mesh_fld.py:34-57` | wrong dialect ⇒ plausible-looking garbage coordinates, no error | code |

## 5. Performance characteristics (measured)

| Case | Result |
|---|---|
| `ex1_100.fld` (4.2 MB, 21 145 v / 18 240 c) | `parse_fld` + fields ≈0.6 s; the 34 978-quad face list is built as a **Python list of tuples** (`mesh_fld.py:374`) plus a `dict` keyed by node tuples (`:461-465`) |
| `tr03_9.fph` (18 MB, 221 786 v / 63 697 c / 323 827 faces) | `parse_gph_mesh` **1.12 s**, SPH fields 0.01 s |
| `laptop_simplified_voxel_less.gph` (69 MB, 629 637 v / 482 034 c / 1 591 840 faces) | `load_file` **4.09 s**; `_cell_centers_fph` fallback **20.8 s** (5× the whole load) — every DST/NORMAL/differential op from cell centres pays it |
| `laptop_thermal_steady_scaled_v3_200.fph` (1.36 GB, 7.72 M v / 6.83 M c / 21.39 M faces) | eager `load_file` **149 s**, `lazy_vars=True` **50.5 s**, materialising one lazy variable **6.6 s**; peak RSS **≈6.0 GB = 4.4× file size** |
| 1.12 GB `.rph` opened by mistake | 9.8 s full-file scan, then an empty FieldFile (no error) |

Structural causes:
* `open_buffer` reads the whole file into RAM for ≤512 MiB and mmaps above (`core.py:196-211`).
* `_section_index_cache` (`core.py:86-101`) is a **module-global dict that keeps the full buffer alive and has no
  eviction**: *(measured)* after 3 files it still retains 38.9 MB, and the 1.36 GB FPH buffer stays pinned after
  close. Its key is `id(data)` (guarded by a length check) — an accidental id reuse after GC would silently return
  stale section offsets.
* `section_end` = "smallest known boundary name after this offset" (`core.py:104-110`) — one `bytes.find` per boundary
  name, cached, but wrong for every real section name missing from the 31-entry list.
* `iter_data_blocks` (`core.py:113-141`) walks each section body **4 bytes at a time in Python** with a `read_i32_be`
  per step, and every parser calls it repeatedly (`_f64_field_blocks`, `_parse_volume_names`, `_parse_bc_sections`,
  `parse_ls_surface_regions`, `_n_cells_array`, `parse_element_centers`, …). On the 1.36 GB file this dominates the
  fixed cost (50 s even in lazy mode).
* Per-element/per-face Python loops: `mesh_fld._build_face_list_and_bcs_inner:374-466`,
  `mesh_gph._group_faces_by_cell_id:339-363` (3 sorts + dict of slices), `mesh_gph._ls_parts_name_blocks:518-531`,
  `varreg._cell_centers_fph:551-570`, `derived._conn_green_gauss_node:222-250`, `neutral._parse_ply_binary:201-210`,
  `render/surface.py:112-117` (`ff.faces[fi]` per face into a VTK cell array).
* Python containers where arrays belong: `boundary_faces` (`.tolist()`), FLD `faces` (list of tuples), Marc node
  dicts (`{gid: [x,y,z]}`, one Python list per node), neutral `faces`.
* `pod.kmeans` materialises `X[:,None,:] - centroids[None,:,:]` (`pod.py:134`) = `n_cycles × k × n_fields × 8 B`
  (≈1.6 GB for 10 cycles × 3 clusters × 6.8 M cells) before the argmin.

## 6. Project claims falsified by this audit

* `analysis/format_gaps.md:52` — "CGNS HDF5 reader works (3213 nodes/2560 hex)": false for the actual corpus — all
  real HDF5 CGNS files here are polyhedral NGON_n/NFACE_n and load with **0 cells** *(measured)*.
* `analysis/format_gaps.md:19` / `SCPOST_COMPARISON.md` FLD rows — "15 variables / 8-of-8 official samples" hides that
  the mapping is positional, `ATMS` is an alias, volume names are lost and 2 of 9 BC zones (`AMOM(*)`) are dropped
  *(measured on `ex1_100.fld`)*.
* `analysis/format_gaps.md:20` (PPH "完全缺失") is stale — `fv/crdl/pph.py` exists and loads the embedded GPH.
* `analysis/r30_coverage_matrix.md:40-45` — `CreateVar`/`CreateVarDST`/`CreateVarDST2` marked "OK(exact)":
  the `info` and `maxlen` arguments are ignored and `CreateVarCombinationVelocity` ignores both scPOST arguments.
* `dataset.py:457-470` docstring "true partial load (P1-3)": geometry is fully read before trimming.
* `varreg.py:594-600` docstring: the FLD fallback for DST is unreachable code.
* Loader registry `dataset.py:522-524` advertises `neu` as loadable — no HyperMesh parser exists.

## 7. Highest-value fixes (ordered)

1. CGNS: implement `NGON_n`/`NFACE_n` (+`ElementStartOffset`), fix `_CODE_CELLS` (13→PYRA_14/14, 14→PENTA_6/6, add
   22/23), stop treating `GridLocation` as a variable, decode `ZoneType` from the h5py attribute/byte array, read all
   bases like the ADF path, and populate `bc_plan` so CGNS BCs become regions.
2. Fail loudly: `load_file` must raise when no container is recognised (removes the silent empty FieldFile and the
   1.12 GB `.rph` no-op).
3. varreg: fix `^` precedence, replace substring location inference with token-based lookup, validate operand lengths,
   turn the 0/1-base detection into an explicit error.
4. FLD: read `LS_Scalar:*`/`LS_Vector:*` + title blocks for names, parse `LS_RegionName&Type` as UTF-8, add the
   `AMOM(` prefix, fix `_parse_volume_names` for UTF-8 blocks.
5. FPH: decode `FC_Scalar/FC_Vector`; keep every nodal quantity/frame; vectorise `_cell_centers_fph` or always use
   `Element_Center`.
6. Performance: evict `_section_index_cache`, vectorise `iter_data_blocks`, keep faces/curves in arrays.
7. Register or explicitly reject `.rph` (same CRDL-FLD container as FLD/GPH); drop `neu` from the registry until a
   parser exists; add binary STL.