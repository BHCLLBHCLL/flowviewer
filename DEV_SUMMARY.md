# flowviewer 开发技术总结

> 项目：Cradle CFD 后处理 GUI 查看器（FPH / FLD 格式）
> 版本：V0.2
> 日期：2026-08-09
> 配套文档：`DEV_PLAN.md`（规划）、本文件（开发过程技术总结）

---

## 1. 项目概况

- 纯 Python 桌面应用（PyQt5 + VTK + numpy），scPost 式后处理查看器。
- 源码 `fv/` 包，入口 `fv_gui.py`，测试 `tests/`。
- 当前里程碑：P1 骨架 + Surface / Plane / Particle 对象属性对话框全部 tab 页 UI 与数据筛选。
- 提交历史：`2d3e668` Initial → `672e81e` 规划文档 → `feaac33` P1 骨架 → `67b2be1` 入口改名 `fv_gui.py` → `7ba601b` 修 GUI 启动 UnboundLocalError → `552aa77` v0.1（对话框/对象模型/图标/轴）。

---

## 2. 关键技术点

### 2.1 CRDL 容器与解析（`fv/crdl/`）

- **容器格式**：大端 `CRDL-FLD` 魔数；命名节 `[I4=32][节名 32B 空格填充][I4=32][节体]`；`core.py` 提供 `find_section / section_end / iter_data_blocks / read_i32`，超大文件用 mmap。
- **GPH 网格**（`mesh_gph.py`）：
  - `LS_Nodes` 三轴分块存储，支持 float32 / float64 / 字反转 float64 三种方言，靠坐标幅值打分自动判别（FPH 结果为 float32）。
  - `LS_Links` 多面体面拓扑 `owner / neighbor / npe / conn`（CSR）；超 1 GiB 分段续读。
- **FLD 网格**（`mesh_fld.py`）：`LS_Nodes`(f64) + `LS_MatOfElements`(材料 ID 1–7) + `LS_Elements`(hex8 1-based 连通) + 体/面几何区与 BC 重建。
- **FPH 场量**（`fields.py`）：网格元数据后 `LS_SPHFile` 节，`EC_Scalar:NAME`（1×n_cells）先、`EC_Vector:NAME`（3×n_cells）后；矢量按 `NAMEX/Y/Z` 拆分。
- **区域划分**：`LS_SurfaceRegions`（边界区域名+全局面索引）、`LS_VolumeRegions`（体区域名）、`LS_Parts`（Part→cvol_id）、`LS_CvolIdOfElements`。

### 2.2 数据模型（`fv/model/`）

- `dataset.FieldFile`：统一封装几何（`vertices`/`link_data`/`cell_conn`）、变量（`variables: dict[str, VarInfo]`，含 scalar/vector、node/cell 分类）、区域（`surface_regions`/`volume_regions`/`bc_plan`）、cycle/time。
- `dataset.load_file` 按节布局自动判别 FLD vs FPH；`_field_kind` 由变量名判定矢量（VEL*/VECT*/HVEC*）。
- `objects.py`：`PostObject` 基类 + `MainObject`（每打开文件一个 Main 节点，默认挂 Surface(1)/Plane(1)[/Particle(1)]）+ 三个对象数据类；`_default_plane` 取最长轴中点作为默认切面。本次为三个对象补充了各 tab 的完整配置字段（region_mode、display_mats、display_volume_regions、contour/vector 变量、mesh 样式、trim 轴、积分选项、automove、intersection、字体等）。

### 2.3 对象属性对话框（`fv/gui/object_dialogs.py`）

- `_PinnedDialog` 统一 chrome（DialogHeader 标题栏 + QTabWidget + OK/Cancel）。
- 共享组件：
  - `_VarRow`：Display 复选框 + 变量下拉（按 scalar/vector 过滤，`_scalar_vars`/`_vector_vars` 从 field_file 变量表生成）。
  - `_ColorButton`：色板按钮 → QColorDialog，返回 0–1 RGB。
  - `_CheckTree`：搜索框 + 勾选树（MAT / Volume Region / Trimmed-by 复用），空选=全部。
- **Surface**（8 tab）：Region（搜索筛选 + Easy Mode）、MAT、Volume Region、Contour（Paint Front/Back + Transparent）、Vector、Mesh（颜色/厚度/透明度）、Trim（Trim all / All + 6 轴向）、Scalar Integration（投影面积）。
- **Plane**（8 tab）：Coordinate（轴 + 坐标滑条 + 范围联动 + Arbitrary 点/法向）、MAT、Volume Region、Contour、Vector、Mesh（Boundary）、Automove（Method + 速度/起止）、Trim。
- **Particle**（7 tab）：Scalar（变量/Mono 色/类型 Points|Sphere|Specify|Actual/尺寸/透明度）、Vector、Intersection（New/Modify/Delete 立方体）、Trim（粒子号/属性号/尺寸范围）、Others、Font、Special（Cloth/String、Variable generalization）。
- 每个对话框 `apply_to()` 将控件状态写回对象模型，供后续渲染接线。

### 2.4 GUI 框架（`fv/gui/`）

- `main.py FlowViewer`：QMainWindow + 水平/垂直 QSplitter（控制窗口 | Draw | Message | Timeline）；菜单/工具栏；`enable_3d` 开关支持无头运行。
- `panes.py`：`PaneFrame`（标题栏+body）、`MessageWindow`、`ObjectTree`（对象树 + eye 显隐 + 双击激活属性对话框）、`TimelineWindow`（Static 模式）。
- `dialogs.py`：Open 对话框（类型过滤器、OpenOptions 复选框与 scPOST 默认值一致）、`DialogHeader`。
- `icons.py`：纯代码矢量 `AppIcons`，`_draw_xxx` 分派 + `(name,size)` 缓存。
- `render/axes.py`：坐标轴 actor。
- **无头测试范式**：`QT_QPA_PLATFORM=offscreen` + `enable_3d=False`；`_HAS_QT`/`_HAS_VTK` 条件导入降级；场景降级为占位 actor 名列表（`Scene.actor_names()` 仍可断言）。

### 2.5 渲染（`fv/render/scene.py`）

- `Scene.build`：网格线框（FPH 边界面 / FLD hex 边）+ Surface（共享边界线框层）+ Plane（半透明切面矩形，颜色/透明度/边色）+ Particle（占位层）。
- 分层 actor 表 `_layer_actors`，`set_layer_visible` 支持 eye 显隐；overlay 显示 File / Cycle / Time。
- `enable_3d=False` 时不建 VTK actor，只记录层名。
- `Scene.apply_to_object`（增量更新）：`remove_object_actors` 移除某对象全部 actor（renderer + 层表 + `_actor_object` 所有权）后经 `_dispatch_object` 单对象重建，`main._on_property_applied` 走此路径避免全量 rebuild。

### 2.6 载入性能优化（2026-08-09）

目标：`tr03_9.fph`（63,697 单元 / 221,786 顶点）载入 2.07s → **0.88s（提升 57%）**，全量回归通过。

| 优化点 | 原实现 | 优化后 | 收益 |
|---|---|---|---|
| Section 偏移索引缓存（`core.py`） | `section_end` 对每个节调 31 次 `find_section`，每次全文件 `bytes.find`（354 次全扫） | 首次调用建 `{节名→偏移}` 索引并缓存（含 data 强引用防 id 复用），后续 O(1) 查表 | 消除重复全文件扫描（~20% 耗时） |
| LS_Nodes 描述符扫描（`mesh_gph.py`） | `ls_nodes_descriptor_elem_bytes` + `ls_nodes_vertex_count_from_descriptors` 各自 Python 逐 4 字节扫描述区，共 133 万次 `read_i32_be` | 合并为单函数 `ls_nodes_descriptors`，整段 `np.frombuffer(>i4)` + 向量化 `==12` 过滤（`head/tc/dim0/dim1` 一次性筛选） | 消除 ~67 万次逐字 Python 读取（~45% 耗时） |

关键经验：
- CRDL 描述区可整体视为大端 int32 数组向量化，`[12, tc, dim0, dim1]` 描述符与 `[12, byte_count]` 数据头靠 `tc ∈ {4,8}` + dim 范围过滤区分，语义与原逐字判定一致。
- `bytes.find` 全文件扫描是隐性 O(N×M)（节数 × 边界名），建立一次性偏移索引是 CRDL 类容器的通用加速手段。
- 剩余热点（`_group_faces_by_cell_id` mergesort、`_renumber_by_first_use`）为 numpy 固有成本，进一步收益有限。

---

## 3. 验证过程

### 3.1 样例数据

| 文件 | 类型 | 顶点 | 单元 | 区域 | 变量 |
|---|---|---|---|---|---|
| `D:\training\cgns\examples\tr03_9.fph` | FPH | 221,786 | 63,697 | 104 面 / 5 体 | 11 |
| `D:\training\cgns\flddecoding\tests\ex1_e_from_sxemt_run.fld` | FLD | 21,145 | 18,240 | BC 若干 | 15 |

### 3.2 测试

- `pytest tests/`：**84 passed**（`test_gui.py` 66 + `test_scene_snapshot.py` 5 + crdl/mesh_fld/mesh_gph 13，2026-08-09 实测）。
- 对话框专项断言（`tests/test_gui.py` 新增）：
  - 三对话框 tab 标题序列与手册一致；
  - Surface Region 搜索筛选（`search="Rotate"` → 93/104 隐藏，可见项均含 "rotate"）；
  - Contour 变量下拉由 field_file 标量变量填充；
  - `apply_to` 写回：全不勾选 → `selected_regions == []`；
  - FLD MAT 筛选：材料 [1,2] 勾选 2 → `display_mats == [2]`；
  - Particle Intersection 解析 `(0,0,0)-(1,1,1)` → `[(0,0,0),(1,1,1)]`，非法串返回 None。
- 手动脚本验证（offscreen + 真实文件）：三对话框全 tab 构建、区域筛选、MAT 筛选、Plane 坐标范围联动（Z: -0.066…0.056）、Particle 相交区增删解析均符合预期。
- 静态检查：`pyflakes fv/gui/object_dialogs.py fv/model/objects.py` 无告警。

### 3.3 运行环境（已实测）

| 项 | 值 |
|---|---|
| Python | 3.12.7（Anaconda） |
| numpy / h5py | 1.26.4 / 3.11.0 |
| PyQt5 | 5.15.10（含 QVTKRenderWindowInteractor） |
| VTK | 9.3.1 |
| 平台 | Windows win32 |

---

## 4. 未解决的问题（P0 后更新：1/2/3/4/6 保持，5 保持；新增 7/8）

1. **Cycle / 时间线变量注册（P3.5）**：FileSet 序列扫描、cycle 切换、Play/Pause/Loop 已接入，但 Variable Registration（算术表达式注册变量）对话框仍缺。
2. **Unit / Camera 设置对话框**：工具栏 Option→Unit、Option→Camera 仍为 NYI。
3. **CGNS / XDMF / EMT 等格式加载器**：loader 注册表已诚实区分可加载（fld/ifld/fph/gph）与探测未实现（cgns 等）；完整 CGNS HDF5 读取未实现。
4. **FPH 无材料数据**：tr03_9.fph 的 material 为 None，MAT tab 在 FPH 下显示空树；MAT 筛选仅对 FLD 有效（P0.5 后 Volume/Surface 的 Volume Region 过滤已生效）。
5. **iFLD 局部读取 / Trimming / Remote Open**：DEV_PLAN 明确 P4 探索项，未做。
6. **真实 GL 渲染静态自动化范围有限**：tests/test_scene_snapshot.py 已建（offscreen 快照 PNG + 增量更新），但 CI 默认 enable_3d=False 降级路径为主。
7. **P0 遗留（2026-08-09）**：FLD Surface 的 MAT 过滤未实现（面与 cell 无直接映射，需 hex 面反向关联）；Particle Intersection/Trim/Cloth tab 仍为 UI-only；平面 vector_space_v/contour_color 等渲染补项仍缺。
8. **P0 技术债**：tests/pytest_tmp 下 pytest 临时目录随会话保留；_section_index_cache 仍持有 buffer 强引用。
## 5. 下一步建议

1. 将对象配置接入渲染（Surface Contour 云图 mapper、Plane 切面标量、MAT/区域显隐过滤、Trim）。
2. `main.py` 传 `main_object.children` 给 PlaneDialog，填充 Trim "Trimmed by"。
3. 建立 `scene_snapshot` 静帧测试覆盖有 GL 环境。
4. 继续按 DEV_PLAN P3（cycle 序列 / 时间线）推进。

---

## 6. P0–P3 改进完成（2026-08-09）

按 SCPOST_COMPARISON.md 计划完成：

- **P0**：测试临时目录修复（pytest 0o700 ACL 根因）、Colorbar LUT 接线、LightObject 最小实现、Particle 变量选择、Surface/Volume 过滤、LoadWorker(QThreadPool) 异步加载。
- **P1**：变量注册表达式引擎（varreg）、CGNS-HDF5 读取器 + EMT、真体渲染（UnstructuredGridVolumeRayCastMapper）、光照 Luster/Water、Pathline、Trim-by-object。
- **P2**：Cylinder/Circle、Graph(matplotlib)、Text/Bitmap、Information、Grouping、Mirror Copy、拾取移动平面（scene 层）、Undo/Redo、Automove Custom Path、TimeSeries/MaxMin。
- **P3**：STA 私有格式声明、STL/VRML/GLTF 导出、fv/api.py 脚本接口、Compare 统计降级、ugrid 缓存。

测试从 84 项增至 121 项（+37），全量回归通过。

**遗留（2026-08-09 补齐后）**：Turbo/UFO/VR/COM 维持不做；其余（拖拽手柄/并排视图/Intersection/Cloth/FLD MAT 过滤/动画帧导出）已完成，见 DEV_PLAN §14。测试增至 129 项。

---

## 7. §16 梯队开发完成（2026-08-09）

按 DEV_PLAN §16 差距排序执行，16 个功能点全部完成并逐点推送 GitHub origin/main：

- **对象面**：Curve / Periodical Copy / Folder / Bar / RegionBC 五对象补齐（对象覆盖 26→31 类）。
- **数据面**：变量微分算子 grad/div/rot/delx（scipy cKDTree 节点场中心差分）。
- **交互面**：Measure 量测、Gradation 渐变背景、对象名气球、多对象拖拽手柄。
- **生态面**：XDMF 读取器、Nastran 文本网格、iFLD 元数据扫描、公开查询 API。
- **修复**：scene 新对象 dispatch 分支未接线的重大 bug；粒子 Intersection/Trim 过滤未接入 build。

测试从 130 增至 131+（最终全量回归见 pytest_final2）。Marc 二进制 / FBX 维持不做。

---

## 8. 差距 1–7 全量补全（2026-08-09）

解除"不做"结论，按第三轮差距清单 1–7 逐项补全并推送：Neutral File(OBJ/STL)、
FPH 单元场微分、Marc .dat、OBJ 导出、4 个部分对象深化(Camera/Region/Limited Plane/
Global Window)、Graph-Curve 联动、Turbo/UFO/COM/VR。测试增至 163 项（最终回归 161 过 1 改）。

运行时依赖：COM 需 pywin32+管理员注册；VR 真渲染需 OpenVR SDK（提供检测）；
Turbo 为几何变换 2D 视图；Marc 仅 .dat 文本（.t16/.t19 二进制未实现）；
FBX 以 OBJ 中性格式替代（无 VTK 原生 FBX 写器）。

## 9. 第七轮功能差距审计（2026-08-16）

> 配套文档：`analysis/function_gap_analysis.md`（完整证据）、`DEV_PLAN.md` §26（行动序）。
> 方法：3 个并行子代理源码级审计（数据/渲染/GUI+自动化三层），关键矛盾点人工核实，
> 非引用既有文档结论。

### 9.1 状态结论（修正此前声明）

- 规模：fv/ 63 文件、18,195 行、31 种 PostObject、29 个 render 模块、11 个 crdl 解码器、
  223 个测试函数（文档基线 201 passed + 1 skipped）。
- **对象面覆盖 100% 成立**（类/对话框/渲染三件套齐全），但存在多处
  「已实现能力对用户不可达」的贯通断裂，**端到端实用深度约 65–70%**
  （修正 SCPOST_COMPARISON §18 声明的 85–90%）。

### 9.2 关键贯通断裂（源码核实）

1. **Create 菜单仅 8/13 项可创建**：Cylinder/Circle/Vector/Text/Graph 五项 kind=None
   （gui/main.py L37–50）；Pathline/Bitmap/Information/Mirror/Curve/Measure/Turbo/UFO 等
   13 种对象对话框与渲染管线现成但无 UI 入口（合计 18/30 对话框不可达）。
2. **STA 往返仅 9/31 kind**：export.py `_KIND_CLASSES` 硬编码，其余对象保存后重载静默丢失。
3. **undo/redo 死代码**：方法与栈存在，无 Edit 菜单/Ctrl+Z/Y/调用点（§6 P2.8 标记完成，实际不可用）。
4. **粒子多帧未消费**：解析层 parse_particle_frames 已就绪（§25②），渲染仍单帧。
5. **交互细节断裂**：Timeline Sync/Ver/Scale inert；`_RENDERABLE_KINDS` main(8) vs panes(30) 不一致。

### 9.3 主要代差（摘要）

- 渲染：体渲染 FPH 回退半透明 + 传递函数硬编码；FLD 流线 numpy 欧拉（RK2 非 RK4）；
  Turbo 仅 2D 散点（polar 无渲染出口）；Luster/Water 仅 2 对象且实现不一致。
- 数据：CGNS 仅 HDF5 单 zone 非 MIXED；微分算子 hex8 硬编码——tet/wedge/pyr 混合网格上
  静默错误值（恰覆盖 §24 刚解码的 2cars/Klein/SCTeta）；POD/FileSet 每 cycle 重新解析且吞错。
- 自动化：COM 仅 10/67 表面。

### 9.4 下一步

按 DEV_PLAN §26 行动序执行：P0 贯通修复（Create 菜单/STA 反射注册/undo 接线/
常量统一/粒子帧消费/细节清扫，纯接线低风险）→ P1 渲染深度 → P2 数据格式深度。
P0 完成后实际可用完整度预计提升至 80–85%。

---

## 10. 第八轮 P0→P3 梯队改进全部完成（2026-08-16）

按 §9 审计结论与 `analysis/function_gap_analysis.md` 行动序（DEV_PLAN §26），
四个梯队 20 个功能点全部完成并逐点推送 GitHub origin/main。

### 10.1 P0 贯通修复（纯接线）

- **P0.1** Create 菜单补全（5 个 kind=None + 13 个无入口对象 → 30 对象全部可达）。
- **P0.2** STA kind 表反射注册（9 → 31 kind，状态往返不再静默丢对象）。
- **P0.3** undo/redo 接线（Edit 菜单 + Ctrl+Z/Y）。
- **P0.4** `_RENDERABLE_KINDS` 统一（main 8 → 对齐 panes 30）。
- **P0.5** 粒子多帧消费（Scene.animate 驱动粒子帧）。
- **P0.6** 细节清扫（timeline 三控件 / .emt 关联 / last_dir / 消息保存 / BMP-TIF）。

### 10.2 P1 渲染深度

- **P1.1** 体渲染真管线（ResampleToImage → SmartVolumeMapper + 参数化传递函数）。
- **P1.2** FLD 流线升级（RK4 积分 + pathline 步长/着色）。
- **P1.3** Turbo 云图化（栅格热力图 + polar 渲染出口）。
- **P1.4** Luster/Water 全对象统一 `apply_sheen`。
- **P1.5** oilflow 变量着色 + camera spline 插值（b07e088）。

### 10.3 P2 数据格式深度

- **P2.1** CGNS 增强：MIXED 单元 / 多 zone / 结构化 zone（7c314b7）。
- **P2.2** 微分算子非 hex 邻接：按 per-cell vtk 类型码查边表
  （tet/wedge/pyra），5 类失配（无 conn / 类型长度 / 未知类型 / id 越界 /
  变量长度）显式 raise 不再静默（053fbaa）。
- **P2.3** varreg 算子补全：iflt/ifle/ifne + log/exp/sin（f4cb5de）。
- **P2.4** FileSet 时间插值：`interpolate_files/interpolate_at` 小数 cycle
  线性混合 + `CycleRuntime`（scPOST SetCurCycleID 1-based 语义、
  SetCurCycleID_F 插值、GetCurTime/SetAutoCycle/ResetCycOpe）（7bee306）。
- **P2.5** POD/ALLCYC 复用 `load_member` 共享缓存（同序列一次解析），
  缺变量/坏文件显式报错不吞（3dc2091）。
- **P2.6** iFLD Trimming Open：bounds 盒空间裁剪网格 + 字段切片（87e68b3）。

### 10.4 P3 自动化扩面（b758fe2）

- **COM 10 → 约 40 方法**：`open_sequence` + cycle 运行时族
  （SetCurCycleID/_F、GetCycleNum/GetCurTime、AddCycList/DelCycList、
  SetCycOpeMode）、几何查询（GetBoundingBox、LocalXYZ2GlobalXYZ/
  GlobalXYZ2LocalXYZ、GetVOLNum/GetMATNumFLD/GetMATIDofVOL、
  GetOverlappingRegionCount）、SaveSTA/ApplySTA/SaveSTL、Set* 状态族 +
  AnimationStart/Stop、ErrorCode/ErrorString 错误通道。
- **api.py 补方法**：`get_bounding_box`（cell_conn 缺失时回退 FPH/GPH
  link_data owner/neighbour 面拓扑收集区域节点）、local↔global 坐标变换
  （旋转矩阵 + 平移，单点/N×3 数组）、VOL/MAT 查询、`save_sta/apply_sta`、
  `split_view` 多视口并排渲染 PNG。
- **XDMF temporal collection**：`<Grid CollectionType="Temporal">` 共享
  拓扑多步帧解析，首帧为载入网格，全部帧经 `ff.meta["xdmf_temporal"]/
  ["xdmf_frames"]` 暴露（attribute-only 帧继承前帧网格）。

### 10.5 回归与状态

- 全量回归 **246 passed / 1 skipped / 2 deselected**（21.5 分钟，2026-08-16 实测）。
- §9 列出的 5 项贯通断裂全部闭合；端到端可用深度自 65–70% 提升至
  P0 预估的 80–85% 区间，且 P1–P3 深化后渲染/数据/自动化三层与
  scPOST 的主要代差消除。
- 遗留：timeline Time 模式 GUI 侧仍整步加载（runtime 插值已在 api 层可用，
  接线留待下轮）；`_on_timeline_step` 消费 `interpolate_at` 为已知后续项。

---

## 11. 第九轮 R3 专业深度（进行中）

### 11.1 R3.1 Turbo 真实叶片表面（60f1599）

- **壁面识别三层**（`_blade_wall_faces`）：L0 显式 region 名 → L1 关键字
  （blade/impeller/rotor/…，排除 plane/cylinder/hub/shroud）→ L2 旋转部件
  cvol 边界面（owner∈旋转部件 ∧ neighbour∉）。tr03_9 实测 L1 命中
  `@PartSurface_Impeller` 9011 面。
- **壁面几何**：Newell 法向 + 按 owner 单元中心定向（指向 owner 内部者翻转）
  并归一化；面心/法向/owner 三元组 `blade_wall_faces()` 公开。
- **PS/SS 分侧**：`blade_loading_surfaces` 改为壁面 owner 单元值 + 法向周向
  分量 `n_θ` 符号分侧（原 θ 中位数全流场启发式降级为无壁面时的回退路径）。
  tr03 实测两侧面数同量级、n_θ 均值符号相反。
- **周期解卷**：`_estimate_pitch` θ 直方图自相关峰 + 显著性门限（0.35），
  合成 4 叶片夹具恢复 pitch=2π/4，均匀分布回 2π。
- **B2B 壁面展开**：`blade_to_blade_surface`（pitch 折叠 + k·pitch 复制）
  替换体积容差取点；`build_turbo_actors` 叶片视图默认壁面采样
  （`blade_surface` 开关 + `blade_regions` 显式名单，TurboDialog 已接线）。
- 测试：`tests/test_turbo_r31.py` 7 项全过；GUI turbo 子集 12 项全过。

### 11.2 R3.5 深格式（ADF + op2）

- **CGNS ADF（8dbb211）**：pyCGNS 因需 HDF5 C 库+pkg-config 无法在 Windows 构建；
  改为**纯 Python ADF 读取器+写入器**（`fv/crdl/cgns_adf.py`），磁盘布局逐字节
  转写自 cgnslib 4.5.1 `src/adf/ADF_internals.c` 格式注释块（文件头 186B/节点头
  246B/ASCII-hex DISK_POINTER/DaTa 块/DCtb 分块表/SNTb 子节点表）。`read_cgns_adf`
  复用 HDF5 路径的 MIXED/结构化/多 zone 逻辑；`cgns_load` 探测回退（HDF5→ADF），
  `probe_format` 区分 cgns-hdf5/cgns-adf。校验：写读 round-trip 双端序测试
  （cgnslib 工具链因旧 CMakeLists 与新 CMake 4 不兼容未能构建，留作后续交叉验证）。
- **Nastran .op2（8743c86 + f5e286d）**：`fv/crdl/op2.py` 经 pyNastran 1.4.1
  （可选依赖：cpylog/docopt-ng）：几何取自 op2 GEOM 表或同 stem .dat/.bdf/.nas
  sidecar（results-only POST 文件常态）；结果映射：eigenvectors→MODE1..N 节点场、
  displacements→DISPMAG(SUB#) 节点场、solid 应力族→VONMISES(SUB#) 单元场。
  真实夹具 vendor `tests/data/plate_py.op2/.dat`（pyNastran models/plate_py，
  NASTRAN 官方示例）：231 节点/200 CQUAD4/10 阶模态实测全通。
- Marc .t16/.t19 维持不做（零样例+无库，plan_r31_r35.md 已记录立项前提）。

---

## 12. R110：测试基线可信化与归因更正（2026-09-13）

> 背景：`analysis/code_state_review_20260913.md`（全量审计）发现"13xx 项全绿"并不可信。
> 计划：`analysis/improvement_plan_r110_r132.md`（R110–R132 逐轮）。

### 12.1 测试夹具隔离（`tests/conftest.py`）

- **根因**：`tmp_path_factory` 用 `{request.node.name}{counter}` 命名，counter 每次会话从 1 开始
  → 重复运行落到**同名目录**并看到上次遗留文件。`tests/pytest_tmp` 累积到
  **2.4 GB / 14,853 文件**；`test_persists_to_file_and_reloads` 因 `assert not p.exists()` 必然失败。
  这解释了"单独跑通过、全量跑失败"的顺序依赖假失败。
- **修复**：会话唯一根目录 `session-<pid>-<uuid>` + 每测试目录先清空；会话结束删除根目录。
- **验证**：原先失败的 `test_r68_presets` + `test_r72_report_bundle` 连续两次运行
  **28 passed**；会话结束后 `tests/pytest_tmp` 残留 **0 文件**。

### 12.2 R109 遗留收尾

- `tests/test_r19.py`：`test_fph_grid_handles_degenerate_cells` 的"0 点单元"期望已过时
  （R109 用 owner∪neighbour 完整壳后，实测 63,697 单元**全部为闭合多面体、零个无面单元**）。
  改名为 `test_fph_grid_is_closed_polyhedra_with_1to1_cell_indexing`，断言
  VTK_POLYHEDRON 类型 + 1:1 单元索引 + 每单元 ≥4 面。
- `README.md`：更正 VTK 归因 —— 不是"VTK ≥9.4.2 上游缺陷、需锁 9.3.1"，而是
  **自己构造的凸包单元非法**（仅 owner 面、壳不闭合）；R109 后 VTK ≥9.3 均可，无需锁版本。

### 12.3 VTK 9.6 迁移风险（记录为 R118 前置）

`vtkCellArray.SetCells` 在 VTK ≥9.6 已弃用，文档建议换 `ImportLegacyFormat`。
本轮实测：在本机 9.6.2 上替换后，重放 `tests/test_gui.py` 前 66 个测试会出现
**原生堆损坏（0xCFFFFFFF）**，位置在体渲染相关测试；回退后即恢复。
**保留弃用但稳定的调用**，并在 `fv/render/plane.py` 就地写明复现方式，迁移留待 R118。

### 12.4 测试产物泄漏

`test_r12p0_scene_export_honest_fail` 用相对路径 `out.fbx/out.cvw` 导出，
每次运行都往仓库根目录丢文件。改为写入 `tmp_path` 并断言文件存在。

### 12.5 轮次门禁脚本（`scripts/round.py`）

固化每轮流程：`--check`（ruff + mypy + 去掉 test_gui 的 pytest）、`--commit "R<n>: …" --push`
（**快层不绿拒绝提交**；强制 `R<num>:` subject；强制 main 分支；推送后回读分支状态）。

### 12.6 回归数字（本机实测）

| 层级 | 命令 | 结果 |
|---|---|---|
| 快层（每轮门禁） | `python scripts/round.py --check` | **1037 passed / 0 failed / 3 skipped**，310 s |
| 非 GUI 全量（105 模块） | `pytest tests --ignore=tests/test_gui.py` | **1037 passed / 0 failed**，345 s |
| 全量 | `pytest tests -q` | `test_gui.py` 内部存在**偶发无响应**（原生层，位置漂移）；其余模块全绿 |

> 注：`test_gui.py` 的偶发无响应为本轮新发现，已登记为 R118 前置项（体渲染路径 + VTK 9.6 兼容）。

---

## 13. R111：加载失败必须响亮（2026-09-13）

> 问题：`load_file` 对无法识别的容器**静默返回空 FieldFile**（0 顶点 / 0 单元 / 0 变量），
> 与“合法但空”的模型无法区分。实测 1.1 GB `.rph` 扫描 10.3 s 后给出空白视口且无任何提示。

### 13.1 容器与节布局识别

- 新增 `_looks_like_gph`（FPH/GPH 必有 `LS_Nodes` + `LS_Links`）。
- 都不匹配时抛 `ValueError`，并在消息里说明**看到了什么**：
  - 非 CRDL-FLD 容器 → 打印前 12 字节；
  - CRDL-FLD 但带 `Ph_R*` 节 → 明确指认“这是 RPH 相/结果文件，尚无解析器”；
  - 其他未知布局 → 列出实际扫到的节名。
- 实测真实 `.rph`（1.1 GB）消息：CRDL-FLD container carrying Ph_R* result sections (Ph_R1_BasicData1) -- this is an RPH phase/result file and no RPH parser is implemented

### 13.2 网格与场缺失

- CRDL-FLD 网格容器缺 `LS_Nodes` → 抛错（而非返回空模型）。
- GPH 载入后若无场变量：`meta['no_fields']=True` + `RuntimeWarning`（GPH 只有几何，可渲染但无可等值面的量）。

### 13.3 越界连接不再被钳位

- `mesh_gph` 原先把越界面-节点 id **钳到 `n_vertices-1`**，把不同节点塌陷到同一顶点 → 几何静默损坏（距离、切面面积、梯度全错且无诊断）。
- 改为提取 `validate_face_nodes()` 并**抛错**（含越界计数与最大 id）。

### 13.4 静默吞错收敛

- `mesh_fld._build_face_list_and_bcs`：保留“网格仍可载入”的降级，但**记录日志**说明面/BC 重建失败（空面表曾与“该文件没有 BC”无法区分）。
- `cgns._read_flow_solution`：不可读字段不再无声消失，记录 `__skipped__` 并逐条 warning。

### 13.5 顺带修正的 SIDS 表错误

`_CODE_CELLS` 的 13/14 与 SIDS 相反（cgnslib：`PYRA_5=12, PYRA_14=13, PENTA_6=14`）：旧表把 PENTA_6 当 5 节点金字塔消费 → **MIXED 流错位、后续单元丢失**。已修正并加注释。

### 13.6 门禁扩展到 scripts/

`scripts/round.py` 的 lint 阶段纳入 `scripts/`，并修掉其中既有的 3 处 lint 问题（此前不在门禁范围内）。

### 13.7 测试与回归

- 新增 `tests/test_r111_errors.py`（8 项）：非容器抛错、未知节布局抛错、RPH 被点名、**绝不返回空 FieldFile**、GPH 无场告警、越界 face-node 抛错、FPH 有场不误报、SIDS 码表。
- 回归：105 个非 GUI 模块全通过。
---

## 14. R112：FLD 几何忠实（2026-09-13）

### 14.1 面节点索引基错位（每个面都用错顶点）

`LS_SurfaceGeometryArray` 的面 id 是 **1-based**，而同一文件的顶点是 0-based；
原来的 `parse_fld` 只对**单元连接**做了归一化，面表原样透传。结果 `surface.py` 把
1..N 直接塞进 0-based `vtkPoints` —— **每个面都整体错位一个节点**。

实测 ex1_100.fld：face ids `1..21145`、**无 0**、1 个越界引用。
修复后：`0..21144`、无越界（新增 `_normalise_face_nodes`，优先用连接推断基、
退化时用与单元 id 相同的启发式；已 0-based 的文件不受影响）。

### 14.2 面表按区域重复（面积被放大 6.3×）

`ff.faces` 是**按 BC 区域拼接**的：同一个物理面在其所属的每个区域里各出现一次。
实测 ex1_100.fld：**34,978 条 = 5,556 个不同面**。表面渲染原样绘制 → 每个面画了 ~6.3 次，
所有面积/逐面统计被放大相同倍数（而“与 VTK 比值”仍是 1.0，所以此前看不出来）。

修复：`_fld_surface_polydata` 先按排序后的节点元组去重再建 cell。
实测：polydata 面数 34,978 → **5,556**，面积 **0.00666**（与 VTK 一致，比值 1.0000）。

### 14.3 面积/积分只取前 3 个顶点

`integrate_cut` 对每个多边形只用前三个顶点算面积 → n 边形少算 (n-2)/n：
单位四边形积出 **0.5**，FPH 壁面只有真值的 **17.9%**，FLD 表面更是偏高 10.26 倍。

修复：改为扇形三角化后累加。解析解验证：

| 用例 | 解析真值 | 实测 |
|---|---|---|
| 单位四边形面积 | 1.0 | **1.0** |
| 五边形（shoelace） | 2.5 | **2.5** |
| 2×2 四边形、a=3 | area 4.0 / sum 12.0 | **4.0 / 12.0** |

真实数据（与 VTK `vtkMassProperties` 比对）：

| 文件 | 面数 | 报出面积 | VTK 真值 | 比值 |
|---|---|---|---|---|
| ex1_100.fld | 5,556 | 0.00666000 | 0.00666000 | **1.0000** |
| tr03_9.fph | 21,220 | 0.17834324 | 0.17847403 | **0.9993** |

### 14.4 测试

新增 `tests/test_r112_fld_geometry.py`（6 项）：单位四边形面积精确、五边形对 shoelace、
缩放四边形按面积加权标量、FLD 面 id 0-based 且不越界、表面每面只画一次、表面面积对 VTK 与绝对值。
---

## 15. R113：数值正确性（2026-09-13）

### 15.1 FPH 单元体积只累加 owner 面（中位 0.424×）

FPH 单元一部分面是 owner、其余是 neighbour，只有两者合起来才是闭合壳。
`faces_of_cell` 只返回 owner 面，导致 `volume_of_element` 在**开曲面**上积分。
修复后抽样 400 单元与独立实现的散度定理体积比对，**中位比值 1.000000**，
网格总体积两者完全一致（0.0007726440468528445）。

### 15.2 DST 量到顶点而非壁面（中位 +47.7%）、FLD 上直接报错

旧实现取壁面**顶点云**的最近邻距离；新增 `fv/model/wallgeom.py` 构建真实的
**壁面三角化表面**并用 `vtkImplicitPolyDataDistance` 量到面。

| 指标 | 旧（顶点云/真值） | 新 |
|---|---|---|
| 中位 | 1.470 | **1.000000** |
| p90 | 6.705 | — |
| p99 | 14.428 | — |
| max | 3888.1 | **max abs diff 0.0** |

同时 FLD 不再报错：壁面来自 `bc_plan`（该文件有 16 个 BC 区），
实测 FLD DST 输出 21,145 个节点值（min 0、max 5.818e-03、全部有限）。

### 15.3 谱：幅度约定未文档化、密度不满足 Parseval

实测确认**内部标度本身是对的**（对 A·sin 精确恢复 A），但字段名叫 `psd` 却是
每 bin 的功率。现在显式区分并给出三个字段：

- `power`（= 历史 `psd`，逐 bin 功率，`sum = var*n/2`）
- `density`（单边功率谱密度，**`sum(density)*df == var`**，跨记录长度可比）
- `amplitude`（该频率正弦的幅值，`sqrt(4*power/n)`）

解析验证：n=400 / dt=0.01 / A=3 / f=7Hz → 主导频率 7.000000、幅值 **3.000000000**
（精确）；n=256/512/1024 且频率对齐到 bin 时幅值同样精确。

### 15.4 短序列相干性恒为 1.0（假“完全相干”）

单段 Welch 相干把互谱除以自身幅值，任意两信号每个 bin 都是 1.0。
实测白噪声 n=50/100/256 全部报 mean/peak = 1.0000。
现在 nseg<2 时返回 NaN 并给出原因（提示缩短 nperseg）；n=512（3 段）仍正常。

### 15.5 互相关 lag 峰值选点

- 归一化改为**逐 lag 各自的重叠窗**（原先用全长模，lag 非零时不是 Pearson r）。
- 周期性信号在多个周期处并列 rho≈1，argmax 会返回最极端者（完全相同的正弦报 -98）。
  现在返回**并列峰中 |lag| 最小者**；实测 `cross_correlate(x, x)` 给出 lag 0。
- lag 符号经构造性验证：y[n]=x[n-k] 时返回 **+k**（正 lag = x 领先 y），与 docstring 一致。

### 15.6 未完成项（转入 R113b）

节点差分算子的**邻居选择**在斜交/四面体网格上仍可能取到对角邻居。
本轮尝试了「横向偏移 + 距离」两级准则，在正交网格与斜网格上互有得失，
未达到可同时满足两者的实现，**已整体回退**（`fv/model/varreg.py` 回到 R112 状态），
相关测试一并撤下，待 R113b 用「按单元面构造节点邻接 + 轴向投影择优」重做。

### 15.7 测试

新增 `tests/test_r113_numeric.py`（8 项）：谱幅值/频率、跨记录长度幅值可比、
Parseval 密度、短序列相干拒绝、lag 符号、并列峰取最小 lag、FPH 单元体积对独立实现、
DST 对表面真值、FLD DST 可用。
