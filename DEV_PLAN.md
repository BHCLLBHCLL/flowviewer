# flowviewer 技术开发规划文档

> 项目：Cradle CFD 后处理 GUI 查看器（FPH / FLD 格式）
> 版本：V0.2
> 日期：2026-08-08
> 状态：参考分析完成，规划待评审

## 参考来源

| 编号 | 来源 | 用途 |
|---|---|---|
| R1 | `D:\training\cgns\gphdecoding`（gph_model.py / fph2cgns.py / gphviewer.py / GPH_FORMAT_SPEC.md） | GPH 多面体网格 + FPH 求解结果（`LS_SPHFile`）解码 |
| R2 | `D:\training\cgns\flddecoding`（fld_model.py / fld_parser.py / FLD_FORMAT.md） | FLD 六面体网格 + 节点场 + BC 解码 |
| R3 | `D:\training\cns\cabdecoding`（cab_gui.py / cab_panes.py / cab_vtk.py / cab_icons.py / tests/test_gui.py） | PyQt5+VTK 桌面 GUI 技术框架与无头测试范式 |
| R4 | Cradle CFD 2025.2 手册 `Post_eng`（460 页）、`Operation_eng`、`Exercise_eng` | scPost 界面与功能规范 |
| R5 | `scPOST_Dx64net.exe` 字符串逆向 | 对象模型 / 类结构参考 |

---

## 1. 目标与边界

### 1.1 目标

开发一个纯 Python（PyQt5 + VTK + numpy）的 **scPost 式后处理桌面应用**，支持：

- 打开 **FPH**（scFLOW 结果，多面体网格 + 单元/面中心场量）与 **FLD**（scSTREAM/scFLOW，六面体网格 + 节点场量）文件；
- 在 3D 视口渲染网格 / 区域 / 变量；
- 创建 scPost 风格对象：**Surface、Plane、Isosurface、Streamline、Volume、Vector、Point、Colorbar** 等；
- 多文件时序序列（`ex1_100.fld → ex1_200.fld`）的 **cycle 管理、时间线与动画**；
- 对齐 scPost *Layout of Windows*：绘图窗口 / 控制窗口（对象树）/ 消息窗口 / 时间线窗口 / 状态栏。

### 1.2 明确不做（P0 范围外，菜单保留入口并 `_nyi` 记日志）

完整涡轮机械（Turbo / Blade-to-Blade / Meridional）、体积渲染器、粒子 / Pathline 完整向导、3D-ROM、UFO、光影物理完整化、VBS 宏自动化、**大规模优化文件（iFLD）的局部读取**（2025.2 手册 `File-Open` 的 Trimming Open / Remote Open 属 P4 探索项）。所有未实现入口统一 `_nyi(name)` 记日志与状态栏公告。

### 1.3 目录规划

仓库根 `D:\training\cgns\flowviewer`，源码置于 `fv/` 包，测试 `tests/`，详见 §3.1。

---

## 2. 参考分析

### 2.1 数据解码参考（R1 / R2）

#### GPH / FPH（R1）

- **容器**：CRDL 大端格式。文件头 `I4=8 + "CRDL-FLD" + I4=8 + dims`；命名节 `[I4=32][节名 32B 空格填充][I4=32][节体]`。
- **GPH 网格**：
  - `LS_Nodes`：三元坐标，按 X/Y/Z 三块存储；支持 float32 / float64 / 字反转 float64 三种方言（`parse_ls_nodes_xyz` 用坐标幅值打分自动判别；FPH 结果为 float32）。
  - `LS_Links`：多面体面拓扑 `owner / neighbor / npe / conn`（CSR）；超大网格在 1 GiB 处分段（`_read_conn_continuations`）。
- **FPH 场**：网格元数据后 `LS_SPHFile` 节，逐变量记录 `EC_Scalar:NAME`（1×n_cells×4B float32）或 `EC_Vector:NAME`（3×n_cells×4B）；标量先、矢量后；矢量变量命名 `NAMEX/NAMEY/NAMEZ`（见 `fph2cgns._parse_fph_flow_solution`）。
- 区域划分：`LS_CvolIdOfElements`（每 cell cvol_id）+ `LS_Parts`（Part→cvol_id，含复合 Part）+ `LS_VolumeRegions`（体区域名）+ `LS_SurfaceRegions`（边界区域名 + 全局面索引）+ `LS_Assemblies`（XML 装配树）。
- **mmap 阈值** 512 MiB；`parse_` 函数对超大文件抽样返回预览。

#### FLD

- 与 GPH 共享 CRDL-FLD 容器，但存储**六面体连通 + 顶点中心场量**。
- `LS_Nodes` 三轴 **f64**；`LS_MatOfElements` 每 cell **材料 ID（1–7）**；`LS_Elements` 六面体 8 节点连通（1-based, `I4[n_cells×8]`）。
- `LS_VolumeGeometryArray` / `LS_SurfaceGeometryArray`：体区域名 + block1 桶计数 + 每 cell vol-flag 对 + 四边形面；`fld_model._build_face_list_and_bcs` 重建 NGON 面与 BC 计划。
- 场量节：`Pressure`(PRES)、`Temperature`(TEMP + TURK/TEPS)、`CN01`（HTRC/SURT/HTFX）、`VECT`(VECTX/Y/Z)、`HVEC`；每节 48B 前导区 + n_vertices × f64 块。
- **FPH 场量类型差异**：FLD 变量为节点中心，FPH 为单元/面中心（手册 `Objects`）。

#### 对 flowviewer 的关键语义

- **FLD 序列**：文件名 `ex1_100.fld`（cycle 100）。**首个文件含几何，后续文件可只含场量**（Operation: Loading FLD file）。需检测 `has_geometry`。
- 同一目录、同前缀的序列文件应一并注册为 cycle 列表。

### 2.2 GUI 框架参考（R3 cabdecoding）

| 项 | 方案 |
|---|---|
| 主窗口 | `QMainWindow` + 水平 QSplitter：左控制 | 右（垂直 Draw|Message）；不用 QDockWidget |
| 面板 | `PaneFrame`（QFrame 标题栏+body）+ `objectName` 级 QSS |
| VTK 嵌入 | `QVTKRenderWindowInteractor`，手动建 renderer；**`showEvent` 里延迟 `Initialize`**（规避首绘为空） |
| 无头测试 | `QT_QPA_PLATFORM=offscreen` + `enable_3d=False`（VTK widget→QLabel）；`_HAS_*` 条件导入降级 |
| 图标 | 纯代码矢量 `AppIcons`（`_draw_xxx` 分派，缓存 `(name,size)`） |
| 面板信号 | `pyqtSignal` 出口 + 主窗口处理业务；面板不直接改 model |
| 状态栏 | permanent 段（坐标+模式）+ 临时 `showMessage`；鼠标 Move 用 `vtkWorldPointPicker` |
| 依赖 | numpy / PyQt5>=5.15 / vtk>=9.3 / h5py（可选） |
| 测试 | pytest offscreen + module 级 qapp/viewer fixture |

**须改造**：
- cabdecoding 全同步加载不适用于 GB 级场文件 → 增加 `QThread` worker + 进度条。
- 树结构从“部件/条件”变为 scPost 对象树（Main → 对象）。
- `_rebuild_scene` 全量重建 → 增加**增量更新**路径（改 cycle/标量只重填 mapper 数据）。

### 2.3 scPost 手册功能要点（R4）

- **布局**：控制窗口（左）+ 绘图窗口（中）+ 消息窗口（下）+ 时间线窗口；均可浮动 / 改大小。
- **控制窗口**（`Control Window`）：左侧树 `POST application → Unit / Drawing window / Message Window / Global object / 各 Main(场文件) → 对象`；设置对话框在下方。eye=显示/隐藏，hand=individual（个体操作）模式。右键菜单 Delete/Property/Copy/Paste/Save STA as file|as object/Modify title/Transparency 等。
- **对象**（`Objects`）：Main、Plane、Cylinder、Surface、Circle、Point、Volume、Isosurface、Streamline、Light、Gradation、Particle、Pathline、Colorbar、Mirror Copy、Periodical Copy、Information、Curve、UFO、Grouping、Graph、Text、Bitmap、Max and Min、Option、Camera、Time Series 等；**本地对象 vs 全局对象**之分（Colorbar/Graph 为全局对象）。
- **Surface 对象**：`Region` 页（按 registered region 勾选、Search、Front/Back）；`Contour` 页（Variable / Paint[Front|Back|Transparent|Luster|Water] / Line / Contour line）；`Vector` 页（箭头映射、密度）；`Mesh` 页。
- **Plane 对象**：法向+一点定义，`Mesh` tab 帧自动消失；可切面绘制 Contour/Vector。
- **Isosurface**：标量常量值面，可叠加 Contour/Vector。
- **Streamline**：起点面/起点点，方向场（速度）；`Real time` 选项。
- **Volume**：整个计算域体绘制标量/矢量。
- **Colorbar**（全局）：`Gradation`（颜色方案/标题/边界线）、`Display`（范围类型：Fix / Max/Min / Auto Justify）、`Range`。
- **Main 对象**：`Cycle`（automatic/Loop/Step/Fast Update/Add/Del/Update/Synchronize time）；`Variable Registration`（算术/微分/矢量算子：+ - * / ^ grad div rot ifgt ifet ifeq & @ delx…）；`Grid`（Autospacing）；`Deform`（位移+缩放）；`Scaling`（Linear/Cylinder/Cone/Sphere/Revolved）；`Others`（FPH 元素值 vs 节点插值等）。
- **菜单**：File（Open/Save Status/Print/Exit）· Create · Display · View（Fit、XY/YZ/ZX、Iso、Compare、多视图）· Option（Mouse 1/2/3-Button、环境设置、Diagnostics）· Help。工具栏分组：File/Create/View/Display/Mouse/Option。
- **时间线窗口**：Static/Cycle/Time 三模式、Slider、Sync。
- **消息窗口**：进度/警告，可保存文本，右键 `Illustrate Log`。
- **文件**：`File-Open` 支持 FLD/FPH/GPH/CGNS/XDMF/Adams/Nastran/Marc 等；**打开对话框右侧显示文件信息**（大小/节点/单元/连接数/面数/部件数/变量数）。
- **STA**：记录对象显示状态，可复用。

### 2.4 scPOST 程序字符串逆向（R5）

`scPOST_Dx64net.exe` 含 MFC/.NET 符号，观察到：
- 类：`COpenGLObjectFLD`（场文件主对象）、`COpenGLObjectCutPlane`（Plane）、`COpenGLObjectIsosurface`、`COpenGLObjectColorBar`、`COpenGLObjectMeasure`（信息量）。
- 循环：`getNumberOfCyclesInCycleList`、`Jump_START`、`BeforeCycleChanged/AfterCycleChanged`。
- 变量：`GetVar1LNAM/GetVar3LNAM`、`findVar1ID/findVar3ID`。
- 魔数 `CRDL-FLD` / `OverlapEnd` 出现多次，与 R1/R2 一致。

结论：仅作**概念/命名参考**，不反向编译；细节按 R1/R2 文档与手册为准。

### 2.5 运行环境（已验证）

| 项 | 值 |
|---|---|
| Python | 3.12.7（Anaconda） |
| numpy / h5py | 1.26.4 / 3.11.0 |
| PyQt5 | 5.15.10（含 QVTKRenderWindowInteractor） |
| VTK | 9.3.1 |
| 平台 | Windows win32 |

---

## 3. 总体架构

### 3.1 模块划分

```
flowviewer/
├── fv/
│   ├── crdl/
│   │   ├── core.py          # CRDL 容器：find_section/section_end/iter_data_blocks/read_i32、mmap
│   │   ├── mesh_gph.py      # LS_Nodes/Links/CvolId/Part/Regions/Assemblies（收敛自 gphdecoding）
│   │   ├── mesh_fld.py      # LS_Nodes(f64)/MatOfElements/Elements/VolumeGeo/SurfaceGeo（收敛自 flddecoding）
│   │   └── fields.py        # LS_SPHFile（FPH）+ FLD 场量节统一为节点/单元场
│   ├── model/
│   │   ├── dataset.py       # FieldFile：几何 + 变量 + cycle 序列；node/cell 插值策略
│   │   └── objects.py       # 对象模型：Surface/Plane/Isosurface/Volume/Streamline/Colorbar...
│   ├── render/
│   │   ├── scene.py         # VTK 场景构建：分层 actor、eye/hand、增量更新、导出截屏
│   │   ├── scalar.py        # 颜色映射：LookupTable / contour mapper
│   │   ├── vector.py        # glyph 箭头、streamline trace
│   │   ├── probe.py         # plane/isosurface/cut 几何（vtkCutter/Contour/Warp）
│   │   └── export.py        # 截图 PNG / 打印
│   ├── gui/
│   │   ├── main.py          # FlowViewer(QMainWindow)：布局/菜单/工具栏/状态栏、main()
│   │   ├── controls.py      # ObjectTree（控制窗口）、对象属性对话框
│   │   ├── panes.py         # PaneFrame / MessageWindow / TimelineWindow / StatusBar
│   │   ├── icons.py         # AppIcons（复制+新增）
│   │   ├── options.py       # QSettings + OptionsDialog
│   │   ├── dialogs.py       # Open 对话框（含文件信息）、Variable Registration、Cycle 等
│   │   └── tasks.py         # QThread 工作线程 + 进度信号
│   fv_gui.py                 # 入口：python fv_gui.py
├── tests/
│   ├── test_crdl.py
│   ├── test_mesh_gph.py     # 用 tr03_9.fph 断言
│   ├── test_mesh_fld.py     # 用 ex1_*.fld 断言
│   ├── test_gui.py          # offscreen + enable_3d=False
│   └── test_scene_snapshot.py # 有 GL 时静帧断言
├── requirements.txt          # numpy>=1.24, PyQt5>=5.15, vtk>=9.3, h5py>=3.0
├── DEV_PLAN.md
└── README.md
```

### 3.2 数据模型（`FieldFile`）

- **几何**
  - `vertices (n,3) float64`（mmap 引用，不整块拷贝）
  - FPH：`LS_Links` 多面体 CS+ 面片 / `npe`；FLD：`LS_Elements` hex8 + `LS_MatOfElements` 材料
  - `volume_regions: dict[name, cell_mask]`（FPH：cvol+Part；FLD：材料/几何体名）
  - `surface_regions: dict[name, face_ids]`（FPH：SurfaceRegions；FLD：面 BC）
- **变量**
  - `variables: dict[str, VarInfo]`，`VarInfo{kind: scalar|vector, location: node|cell|face}`
  - **按需懒加载**：只导入当前显示引用到的变量
- **序列**
  - `FileSet`：同前缀 `_NNN.ext` 序列；`load_sequence()`；`cycle(i)` 切换时仅更新变量（带网格的首文件重建几何）

### 3.3 界面布局（对齐手册 Layout）

```
┌─ Menu: File  Create  Display  View  Option  Help ──────────────────────┐
├─ ToolBar: File | Create | Display | View | Mouse | Option ─────────────┤
├────────────────┬───────────────────────────────────────────────┬────────┤
│ Control Window │               Draw Window                    │        │
│  ├ Main(文件)  │   (VTK 视口：网格/BC/对象/坐标轴/Fit)        │ 可浮动 │
│  ├ Plane       │                                              │        │
│  ├ Surface     │                                              │        │
│  ├ ...         │                                              ├────────┤
│  └ Iconbar         │    （右键对象 · 个体模式手柄）              │ Message│
├────────────────┴────────────────┬─────────────────────────────┴────────┤
│ Timeline Window (Static/Cycle/Time)                                  │
│ StatusBar: (x,y,z) | 选择模式 | 操作模式 | 目标 | Cycle ...             │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.4 渲染设计（VTK）

- **FLD**：`vtkUnstructuredGrid`，hex cell；按 region/material 分段 `vtkThreshold`；节点场→PointData 顶点数据原色（`vtkLookupTable`）。
- **FPH**：多面体 `LS_Links` 边界表面为默认渲染层（性能友好）；Volume 对象整体体采样 `vtkThreshold`+透明度；支持把格心变量插值到节点用于切片/等值线（`vtkCellCenters`+`vtkResampleWithDataSet`）。
- **对象**
  - Surface/Plane：`vtkCutter`/`vtkContourFilter` 切面 + 标量 mapper
  - Isosurface：`vtkContourFilter`
  - Streamline：`vtkStreamTracer`
  - Vector arrow：`vtkGlyph3D`（arrow source，抽样控制数量）
  - Colorbar：`vtkScalarBarActor` 全局
- **分层**：`_layer_actors: dict[str, actor]`；eye/hand 控制显隐与个体操作；**增量更新**（改 cycle 只更新 `mapper.SetInputData`）。

### 3.5 后台加载

`tasks.py` 的 `LoadWorker(QThread)`：解析在 worker 线程，网格/变量数组缓存到共享只读内存；完成后回主线程建 actor/populate 树；`progress(int,str)` 连状态栏；支持取消。

---

## 4. 功能规格（Milestone 拆分）

按 scPost 手册语义对齐。同一行括号内为对应手册页。

### P1 — 基础（可运行骨架）

| 编号 | 功能 | 手册/参考 |
|---|---|---|
| 1.1 | 主窗口 splitter 布局 + PaneFrame + 菜单/工具栏骨架 | Layout of Windows |
| 1.2 | File > Open（打开 FLD/FPH 单文件、文件信息显示） | File-Open |
| 1.3 | 鼠标 3-Button（中键旋转/滚轮缩放/右键平移）+ 键盘 X/Y/Z/A/I/R | Drawing Window |
| 1.4 | View：Fit/Reset/XY·YZ·ZX·Z-/Iso/平行投影 | View Menu |
| 1.5 | 网格渲染（FLD hex / FPH 边界）+ 对象树 + region 显隐 | Main-Grid |
| 1.6 | 变量读取与注册（标量/矢量、node/cell 分类） | Objects; Main-Variable |
| 1.7 | Off-screen 无头测试骨架 | cab tests/test_gui.py |

### P2 — 对象与场

| 编号 | 对象/功能 | 核心功能 | 手册页 |
|---|---|---|---|
| 2.1 | **Surface** | Region（Parts/registered Region 勾选）；Contour（Variable/Paint/Line/Transparent）；Vector（箭头） | Surface/Surface-Contour |
| 2.2 | **Plane** | 坐标+法向、Contour/Vector 切面绘制；黑色网格/Mesh tab | Plane |
| 2.3 | **Colorbar** | 全局；Range（Auto MinMax / Fix）；Gradation/Display 方案 | Colorbar |
| 2.4 | **Isosurface** | 标量+等值；叠加 Contour | Isosurface |
| 2.5 | **Point** | 坐标→局部标量/矢量探针值 | Point |
| 2.6 | **Streamline** | 起点面/点、密度、方向场 | Streamline |
| 2.7 | **Volume** | 域体标量/矢量、透明度、抽样精度 | Volume |

### P3 — 时间 / 序列

| 编号 | 功能 | 参考 |
|---|---|---|
| 3.1 | 序列扫描同前缀 `_N.ext` → 注册 cycle；首文件带几何 | Operation Loading FLD |
| 3.2 | 主对象 Cycle 页：Set/Forward/Auto/Loop/Step/Update/Add/Del | Main-Cycle |
| 3.3 | Timeline 窗口（Cycle/Time 模式、Slider、Sync） | Timeline Window |
| 3.4 | 同时打开多序列、树分组对比 | Layout |
| 3.5 | Variable Registration 算术表达式（算子集合） | Main-Variable |
| 3.6 | Deform 位移动画（静态/瞬态） | Main-Deform |

### P4 — 完善与增强

| 编号 | 功能 |
|---|---|
| 4.1 | Save PNG / 打印 / STA 保存读取 |
| 4.2 | 右键菜单（Delete/Copy/Paste/Modify title/Transparency/STA as object） |
| 4.3 | Information 探针（坐标+变量值、node/element） |
| 4.4 | 镜像拷贝 Mirror Copy、倍率 Compare Scales |
| 4.5 | CGNS 读取（ADF/HDF5，复用 fld2cgns/gph2cgns 兼容） |
| 4.6 | Option 对话框（Mouse 模式、环境设置、Assistant1 等子集）持久化 |
| 4.7 | 大网格性能：懒变量、渲染采样、增量 cycle 更新、进度线程 |

### 不做（P4 之后 / 明确不做）

Turbo/Blade-to-Blade、Volume renderer、UV、Pathfull、3D-ROM、VBS 宏等（见 §1.2）。

---

## 5. 关键设计决策（记录）

1. **网格/场分离 + 懒加载**：扫描节布局快速；只加载渲染所需变量；cycle 切换增量。
2. **FPH 多面体默认面渲染**：避免 GB 级多面体体绘制爆炸；Volume 体块为可选降级。
3. **FLD 序列「首带几何」**：`has_geometry` 标志控制 cycle 切换是否重建网格。
4. **Colorbar 全局对象**：跨场文件共享（对齐手册）。
5. **后台 worker**：加载/计算放 QThread，防止 UI 卡。
6. 依赖：PyQt5 已实测可用（5.15.10）；如遇 Qt 许可问题可换 PyQt6。

---

## 6. 边界与验收

### 验收标准

1. `python fv_gui.py` 打开后能显示边界网格（通过 File>Open 加载）；
2. 打开 FLD 序列（如 `ex1_100.fld`/`ex1_200.fld`）能切换 Cycle 并同步时间滑块；
3. 可创建 Surface/Plane 并绘制标量云图（Contour）与矢量箭头；
4. Colorbar 范围可改（Auto/Min/Max），全局共享；
5. `pytest tests/` 全部通过（CI 无显示也可以跑）；
6. `File > Open` 显示文件信息（大小/节点数/单元数/变量列表）。

---

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 超大网格内存/UI 卡顿 | mmap + 懒加载 + worker线程；多面体面渲染降级；渲染抽样 |
| 格点场插值到切面/等值线的差异 | `vtkCellCenters`+`vtkResampleWithDataSet`；记录插值口径 |
| 多面体 LS_Links 在 VTK 中性能问题 | 默认面渲染；Volume 用 `vtkThreshold`+抽样 |
| FLD 首带几何、后续仅场的加载语义 | `has_geometry` 检测 |
| Colorbar 跨文件状态同步 | 全局 Colorbar 对象 |
| headless CI 无 GL | `enable_3d=False` + offscreen；GL 测单独小步长 |
| scPOST 细节行为未知 | 以手册为准；可选 STA 对照测试 |

---

## 8. Plane 对象 16-tab 渲染映射审计（2026-08-09）

> 范围：`PlaneDialog`（`fv/gui/object_dialogs.py`）16 个 tab 的 UI 选项 →
> `PlaneObject`（`fv/model/objects.py`）字段 → `fv/render/plane.py` 渲染管线
> （`build_plane_actors` / `trim_cut` / `automove_coordinate` / `integrate_cut`）
> 的映射覆盖度审计。V0.2 已实现：Contour / Vector / Mesh / Boundary / Subline
> 基础渲染 + Automove 数学 + Scalar Integration 弹窗。

### 8.1 审计结果

| Tab | 已映射到渲染 | 未映射（缺口） |
|---|---|---|
| **Coordinate** | axis、coordinate、point/normal（`cut_grid`/`plane_from_object`）、Rotate 点击 | `operate_object`、`pick_mode`/`pick_hide`（需交互器拾取）、`arbitrary_normal_r/t/p`、`usage_*`（视图态） |
| **MAT** | — | **整 tab**（`display_mats`，需 `LS_MatOfElements` → cell 过滤） |
| **Volume Region** | — | **整 tab**（`display_volume_regions`，需 region→cell 关联） |
| **Contour** | var、transparent、line、line_transparent、broken_line、thickness | `contour_paint`、`luster`、`water`、`mono_color/rgb`、`contour_value`（标注） |
| **Vector** | var、location、space_u、type、transparent、mono_color、scale_length | `space_v`、`constant_length`、`contour_color`（按标量着色）、`projection`、`scale_thickness`、`arrow_angle/size` |
| **Mesh** | show_mesh、color、thickness、transparent | `mesh_paint/rgb`、`mesh_block`、`mesh_luster`、`mesh_water` |
| **Boundary/Subline** | boundary_line、boundary_color、boundary_transparent、subline_external | `boundary_auto`、`boundary_broken_line`、`subline_automatic`、`subline_display_location` |
| **Oil Flow** | — | **整 tab**（流线/streakline 需新增 `vtkStreamTracer` 管线） |
| **Trim** | — | **整 tab**：`trim_cut` 读 `trim_xmin/…`，但 `PlaneObject` 与 Trim tab 只有 `trim_objects`——属性名错位，实际 no-op |
| **Automove** | 数学（Line/Sin/Cos/Rotation，`automove_coordinate`） | Custom Path（csv）、`show_path`、`sync/distance/start/end`；**无动画驱动**（scene 无人调用重切） |
| **Clip** | — | **整 tab**（`clip_enabled`/`clip_x*`/`display_region` 未被 render 读取） |
| **Pick** | — | **整 tab**（需鼠标拾取 + 消息窗口/数值标注） |
| **Scalar Integration** | area/sum/average 弹窗显示（`_on_integrate`） | CSV 输出（`integrate_output_file/csv`）、`labels`、`beep`、`recalc` |
| **Vector Integration** | — | **未接线**：`_on_integrate` 恒传 `vector=None`，勾选 `int_vector` 也不计算 |
| **Others** | — | colorbar（`cb_contour/cb_vector`，无 `vtkScalarBarActor`）、`use_model_coord`、`no_vector_contour_simultaneous`、`inter_*` 交线计算 |
| **Texture** | — | **整 tab**（无 `vtkTexture`/UV 生成） |
| **Font** | — | **整 tab**（仅服务 contour_value / pick_numbers 文字标注，尚无 text actor） |

### 8.2 修改提升计划（按优先级）

> 状态（2026-08-09）：P1（1–3）、P2（4–7）、P3（8–11）**已全部完成**并提交。

**P1 — 修复错位 / 断链（低风险、立即见效）**
1. **Trim tab 属性错位**：`trim_cut` 改读 `trim_objects` 语义；或把 `trim_xmin/…` 加回 `PlaneObject` 且 Trim tab 提供坐标输入，二选一并补测试。
2. **Vector Integration 接线**：`_on_integrate` 中 `int_vector` 勾选时 attach vector（复用 CellData→PointData→probe 流程）传给 `integrate_cut`。
3. **Integration CSV 输出**：`integrate_output_file` 时把 `{var, area, sum, average}` 写入 `integrate_output_csv`。

**P2 — 直接可实现的 VTK 增强**
4. **Oil Flow**：新增 `fv/render/oilflow.py`，切面起点网格（`oilflow_space_u/v`）+ `vtkStreamTracer`（RK/Euler、`oilflow_steps`）→ Line/Standard/Triangle 流线 actor；`thickness/transparent/length` 生效。
5. **Clip tab**：`build_plane_actors` 按 `clip_enabled`+`clip_xmin/xmax/ymin/ymax` 做 `vtkClipPolyData`（与 surface.trim_surface 同款）；`display_region` 画裁剪框线。
6. **Contour 补项**：`mono_color`（纯色）、`contour_value`（`vtkLabeledDataMapper`）、`luster/water` → vtk 材质镜面/透明度。
7. **Vector 补项**：`constant_length`（ScalingOff）、`projection`（法向分量置零）、`arrow_size/angle` 传 glyph 源。

**P3 — 数据模型 + 交互**
8. **MAT / Volume Region 过滤**：解析 `LS_MatOfElements`（cell→mat）与 volume region→cell 映射，`build_ugrid` 按 `display_mats`/`display_volume_regions` 裁剪 cell。
9. **Colorbar / Font / Texture**：`vtkScalarBarActor` 接入 Others 两个下拉；字体应用到标注；`vtkTexture` 加载 `texture_file` 贴切面。
10. **Automove 动画驱动**：Scene 加 `animate(t)`，用 `automove_coordinate` 更新 plane 并重切。
11. **Pick 交互**：render window 拾取回调（`vtkPropPicker`），按 `pick_scalar/vector/shape/color` 输出到消息窗口。

**执行顺序建议**：P1（1→2→3）→ P2（4→5→6→7）→ 视需求做 P3。每项配 headless 测试（`enable_3d=False` build 层名 + `enable_3d=True` 校验 actor 数量/标量模式）。

---

## 9. 下一步（ToDo）

1. （评审）确认范围与优先级（是否包含 CGNS/Streamline/多视图等 P3–P4 项）。
2. （T1）建立骨架：`fv/` 包 + `tests/` + `requirements.txt` + 入口 `fv_gui.py`。✅
3. （T2）实现 `crdl/core.py` + `mesh_gph.py`（mmap、float32/float64 自检）。✅
4. （T3）最小 GUI：主窗口 + Open 对话框 + 渲染 FPH 边界网格 + 状态栏坐标。✅
5. （T4）FLD 解析 + 序列 cycle；逐步补齐 P2/P3。✅（Surface/Plane/Particle 渲染管线已接入 scene）
6. （T5）Plane 16-tab 审计提升：P1 → P2 → P3（见 §8.2）。
7. （T6）**scPOST 补充对象**：Isosurface / Point / Streamline / Volume / Colorbar（模型 + 渲染 + 设置面板）。✅ 完成于 2026-08-09（见 §10）。

> 本文定期依据实际开发进度更新，重大变更需更新版本号与历史表。

---

## 10. scPOST 补充对象（T6，2026-08-09）

> 范围：除 Surface / Plane / Particle 之外的核心 scPOST 对象——Isosurface、
> Point、Streamline、Volume、Colorbar，覆盖「模型字段 → 渲染管线 → 平铺设置
> 面板 → PropertyHost 接线」。

### 10.1 交付清单

| 对象 | 模型 | 渲染 | 设置面板 | 验证 |
|---|---|---|---|---|
| **Isosurface** | `IsosurfaceObject` | `fv/render/isosurface.py`（vtkContourFilter + contour_line + vector） | `IsosurfaceDialog` | FLD 管线测试 |
| **Point** | `PointObject` | `fv/render/point.py`（marker + 探针标注，FLD 走最近节点） | `PointDialog` | FPH/FLD 探针测试 |
| **Streamline** | `StreamlineObject` | `fv/render/streamline.py`（vtkStreamTracer / FLD 数值 Euler 追踪） | `StreamlineDialog` | FPH/FLD 流线测试 |
| **Volume** | `VolumeObject` | `fv/render/volume.py`（vtkDataSetMapper + 采样） | `VolumeDialog` | FPH 体积测试 |
| **Colorbar** | `ColorbarObject` | `fv/render/colorbar.py`（全局 LUT + vtkScalarBarActor） | `ColorbarDialog` | LUT / actor 测试 |

### 10.2 接线

- `fv/gui/panes.py` `PropertyHost.show_object` 收录
  `isosurface / point / streamline / volume / colorbar` 五种 kind。
- `fv/render/vector.py` 为共享箭头 glyph 工具，Isosurface / Volume 复用。
- 全局 colorbar：`fv/render/colorbar.py` 持有进程级 `ColorbarRegistry` LUT。

### 10.3 测试（tests/test_gui.py，新增 12 项）

- 对话框：tab 结构 + `apply_to` 回写（含无 / 有 field_file 两种情况）。
- 渲染管线：isosurface（FLD contour/line/vector + 显式 iso 值）、point（FPH
  probe + FLD nearest-node）、streamline（FPH vtkStreamTracer + FLD Euler）、
  volume（FPH Transparent）、colorbar（`build_lut` + `colorbar_actor`）。

---

## 11. 全面审查（2026-08-09）——未完成功能清单 A–J

> 对 `fv/`（model / render / gui / crdl）与 `tests/` 的完整代码审查 + 与
> DEV_PLAN §2/§3/§4 规划的逐项核对。结论：**渲染管线已基本齐备，主要缺口
> 在「对象 → UI 贯通」与「时间序列 / 导出」层**。以下按实现优先级 A→J 排列，
> 每项含证据行号；A–J 为工作项，J 为基准记录。

### A. 核心对象未贯通 UI（最高优先级）

| 缺口 | 证据 |
|---|---|
| Create 菜单 13 项 + 工具栏 8 项全为 `_nyi` stub | `main.py:223-230`、`main.py:320-332` |
| `MainObject.from_field_file` 只生成 Surface/Plane/Particle | `objects.py:447-468` |
| 树节点只渲染 3 种 kind | `panes.py:201-217` |
| `_on_object_activated` 仅接受 surface/plane/particle | `main.py:583`、`panes.py:281` |
| `_on_tree_visibility` 层映射不含新 kind | `main.py:550-555`、`panes.py:206-210` |

→ 目标：Create 菜单/工具栏真实创建对象并挂到 Main 子树；树激活/显隐/图标
覆盖全部 8 种 kind；`_on_object_activated` 放开。

**✅ 已完成（2026-08-09，commit c7da33b）**：`main._create_object(kind)` 创建并
挂树 + `ObjectTree._add_object_item/add_object` + `_icon_for_kind` 全 kind 图标 +
`_RENDERABLE_KINDS` 放开激活/显隐映射；Create 菜单/工具栏接线（未实现 kind
Cylinder/Circle/Vector/Light/Text/Graph 仍保留 `_nyi`）。验证：`test_create_object_menu_wiring`。

### B. 全局 Colorbar 未接线

→ 目标：`Scene.build` 遇到 kind=colorbar 子对象时渲染全局 `vtkScalarBarActor`
（含 headless 层）并应用 Fix 范围。

**✅ 已完成（2026-08-09，commit 6dc2c7a）**：`scene.build` 3D 分支新增
`elif obj.kind == "colorbar"` → `build_global_colorbar(obj, range_=Fix?obj.min/max:None)`；
headless 分支 kind 列表加入 colorbar（`_layer_actors["colorbar"]`）。
验证：`test_scene_build_renders_colorbar`（3D）与 `test_scene_build_colorbar_headless`。

| 缺口 | 证据 |
|---|---|
| `Scene.build` 无 `colorbar` 分支 | `scene.py:202-255` |
| `Scene.build_global_colorbar` 定义但从未被调用 | `scene.py:82-96` |
| `LightObject` 无渲染/无对话框/无实例化 | `objects.py:395-397`、`panes.py:222`（假节点） |

→ 目标：`build()` 内 colorbar 分支调用 `build_global_colorbar`；Light 从
对象模型移除或提供最小实现。

### C. 时间 / 序列（DEV_PLAN P3.1–3.4）

| 缺口 | 证据 |
|---|---|
| 无 `FileSet` / `load_sequence` / 序列扫描 | 全仓库 0 命中（P3.1） |
| Timeline Play 为 stub；Pause 信号未连接 | `main.py:154`、`panes.py:544-547` |
| `Sync`/`Loop`/`edit_ver`/`edit_scale` 控件未接线 | `panes.py:413-465` |
| `timeline.set_range(cyc, cyc)` 滑块单值禁用 | `main.py:468` |
| `_on_timeline_step` 不切换 cycle 场数据 | `main.py:604-615` |
| Variable Registration（P3.5 算术表达式）全缺 | 菜单/对话框/模型均无 |

→ 目标：`FileSet` 序列扫描 + cycle 切换加载场量；Play/Pause/Step 驱动；
Variable Registration 对话框。

**✅ 已完成（2026-08-09，commit db17223）**：新增 `fv/model/fileset.py`
（`scan_sequence` 按同 stem+扩展名整合兄弟文件，按 cycle 排序，`refresh_meta`
惰性读 Cycle/Time）；`open_file` 构建 FileSet 并把 `timeline.set_range` 扩展到
序列范围；`_on_timeline_step` 在 Cycle/Time 模式下加载该 step 成员场数据并重建
场景；Play/Pause 用 QTimer 驱动文件集播放（Loop 复选生效）。
验证：`test_fileset_scan_sequence`、`test_fileset_scans_real_v3_sequence`、
`test_timeline_cycle_switch`。Variable Registration（P3.5）仍缺。

### D. 导出 / 文件功能（DEV_PLAN P4.1）

| 缺口 | 证据 |
|---|---|
| Save Status (STA) 菜单/工具栏为 stub | `main.py:218`、`main.py:314` |
| Print 菜单/工具栏为 stub | `main.py:219`、`main.py:316` |
| 无 PNG/截图导出（无 `vtkWindowToImageFilter`） | — |

→ 目标：`export.py` 提供截图 PNG；STA 写入/读取；Print（QPrinter）。

**✅ 已完成（2026-08-09，commit d8b6bea）**：新增 `fv/render/export.py`：
`snapshot_png`(vtkWindowToImageFilter/JPEG) 、`save_status`/`load_status`
(JSON `.sta` 全 dataclass 字段往返) 、`print_scene`(QPrinter，缺打印支持时回退
PNG)。File 菜单与工具栏 Save/Print 接线，新增 File→Export PNG…。
验证：`test_sta_save_load_roundtrip`、`test_snapshot_png_headless_returns_false`、
`test_export_handlers_wired`。

### E. 菜单 / 视图 stub（24 项）

View→Iso Metric/Compare（`main.py:246-247`）、Display→Redraw(菜单)/Show All/
Hide All（`main.py:234-236`）、Option→Mouse 1/2-Button/Environment/Diagnostics
（`main.py:265-271`）、工具栏 Save/Print/Contour/Show/Camera/Unit/Option
（`main.py:314-380`）、Select 鼠标模式仅日志（`main.py:638`）。

→ 目标：Iso 等轴视图、Show/Hide All 场景显隐、Environment/Unit 对话框。

**✅ 已完成（2026-08-09，commit 7f656ec）**：Display→Redraw/Show All/Hide All
（接线+树显隐）、View→Iso Metric（`axes.iso_metric_camera`）/Compare、
Option→Contour（重算场景）、Environment（`dialogs.EnvironmentDialog`）/
Diagnostics（状态转储）、Mouse 1/2-Button 接入。工具栏 Save/Print/Contour/
Show/Redraw/Option 均已接线。Unit/Camera 对话框仍 NYI。

### F. 已知 inert 控件

| 控件 | 证据 |
|---|---|
| Trim "Trimmed by" 恒空（`_trim_objects` 无赋值） | `object_dialogs.py:1103-1109` |
| Particle "Run checked functions" 无 clicked 连接 | `object_dialogs.py:1967` |
| Plane Usage Guide 按钮空实现 | `object_dialogs.py:720` |
| `ObjectSettingsPanel._btn_pin` pin 状态无效果 | `object_dialogs.py:171` |

→ 目标：`main.py` 传 `main.children` 填充 Trimmed-by；Run 按钮接
`_run_special`；Usage 按钮驱动视图旋转；pin 维持面板。

### G. 文件格式夸大

| 缺口 | 证据 |
|---|---|
| 过滤器广告 CGNS/XDMF/Adams/Nastran/Marc | `dialogs.py:30-48` |
| 实际只加载 fld/ifld/fph/gph | `dialogs.py:52`、`main.py:425` |
| Magic/Trimming/Remote open、加速选项仅记日志 | `main.py:421`、`main.py:484-489` |

→ 目标：加载器注册表（fld/fph/gph 实现 + cgns 探测接入），或从过滤列表
删除未实现后缀以避免误导。

### H. 规划模块缺失（DEV_PLAN §3.1 列出但未建）

`fv/render/scalar.py`、`probe.py`、`export.py`、`fv/gui/controls.py`、
`options.py`、`tasks.py`（后台 QThread worker）均不存在。

→ 目标：按需创建 `options.py`（QSettings 持久化）、`tasks.py`（加载 worker）、
`export.py`（截图/打印）。

### I. 已记录但未解决（DEV_SUMMARY §4 延续）

增量 mapper 更新（改配置走全量 rebuild）、cycle 切换增量、EMT 别名、iFLD
局部读取、GL 静帧自动化（`test_scene_snapshot.py` 不存在）。

→ 目标：`test_scene_snapshot.py`；`Scene.apply_to_object` 增量更新路径。

### J. 已实现基准（供对照，无需开发）

- 解析：FPH/GPH/FLD（`fv/crdl/`）。
- 渲染：Surface 8-tab / Plane 16-tab / Particle 7-tab 对话框与管线、Oil Flow、
  Trim/Clip/Automove/Pick/OilFlow/Texture/Font、新 5 对象渲染管线、轴。
- 平铺设置面板 + PropertyHost 8 kind 映射。
- 测试：`tests/test_gui.py` 44 项通过。