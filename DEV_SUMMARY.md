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

## 4. 未解决的问题

1. **Cycle / 时间线变量注册（P3.5）**：FileSet 序列扫描、cycle 切换、Play/Pause/Loop 已接入，但 Variable Registration（算术表达式注册变量）对话框仍缺。
2. **Unit / Camera 设置对话框**：工具栏 Option→Unit、Option→Camera 仍为 NYI。
3. **CGNS / XDMF / EMT 等格式加载器**：loader 注册表已诚实区分可加载（fld/ifld/fph/gph）与探测未实现（cgns 等）；完整 CGNS HDF5 读取未实现。
4. **FPH 无材料数据**：`tr03_9.fph` 的 `material` 为 None，MAT tab 在 FPH 下显示空树；MAT 筛选仅对 FLD 有效。
5. **iFLD 局部读取 / Trimming / Remote Open**：DEV_PLAN 明确 P4 探索项，未做。
6. **真实 GL 渲染静态自动化范围有限**：`tests/test_scene_snapshot.py` 已建（offscreen 快照 PNG + 增量更新），但 CI 默认 `enable_3d=False` 降级路径为主。

---

## 5. 下一步建议

1. 将对象配置接入渲染（Surface Contour 云图 mapper、Plane 切面标量、MAT/区域显隐过滤、Trim）。
2. `main.py` 传 `main_object.children` 给 PlaneDialog，填充 Trim "Trimmed by"。
3. 建立 `scene_snapshot` 静帧测试覆盖有 GL 环境。
4. 继续按 DEV_PLAN P3（cycle 序列 / 时间线）推进。
