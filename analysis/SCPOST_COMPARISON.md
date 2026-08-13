# flowviewer vs scPOST 功能完整度对比分析与改进计划

> **执行状态（2026-08-09 更新）**：P0（0.1–0.6）、P1（1.1–1.6）、P2（2.1–2.10）、P3（3.1–3.5）
> 已按本计划全部实施，新增 35+ 项测试；全量回归通过（详见 DEV_PLAN §12/§13）。
> 遗留：2.7 完整拖拽手柄（scene 方法已就绪）、3.4 真并排视图、P2 中 Particle Intersection/Cloth、
> FLD Surface MAT 过滤、Automove 帧导出 PNG 序列、3D-ROM/VBS 维持不做。


> 分析日期：2026-08-09（会话执行）
> 对比基准：Cradle CFD 2025.2 `Programs_x64/scPOST`（`scPOST_Dx64net.exe` / `scPOST_Sx64net.exe` + `Manuals/scPOST` 的 VB_Interface / Tools 手册）
> 分析对象：`D:/training/cgns/flowviewer`（fv 包 10,552 行 + 测试 84 项）
> 配套证据文件：`analysis/data_layer.md`、`analysis/render_layer.md`、`analysis/gui_layer.md`、
> `analysis/scpost_strings.txt`（程序字符串分类）、`analysis/vb_class_list.txt`、`analysis/vb_application.txt`、`analysis/vb_fldfile.txt`

---

## 1. 分析方法

| 输入 | 手段 | 产出 |
|---|---|---|
| flowviewer 源码（34 个 .py） | 3 个并行子代理全量通读（crdl+model / render / gui+tests），grep NYI/TODO 标记 | 三份分层报告 |
| scPOST 主程序（12.1 MB） | 字符串提取 + 关键词分类（对象类、格式、算子、特效、导出等 25 类） | `scpost_strings.txt` |
| scPOST VB 接口手册（eng） | HTML 转文本：公开类清单、Application 类、FLD File 类（125 方法） | 权威对象模型 |
| scPOST Tools 手册 toc.csv | scConverter / CradleViewer / HeatPathView 功能面 | 附属工具清单 |
| 测试基线与 git 历史 | 本会话运行 `pytest tests -q`；`git log` | 当前质量基线 |

**说明**：安装目录不含 scPOST 主功能手册 PDF（`Post_eng`，DEV_PLAN R4 曾引用），
本次以「程序字符串 + VB 接口类清单」作为 scPOST 实际功能面的权威证据，两者相互印证。

---

## 2. 当前代码状态总览

### 2.1 规模与结构

| 层 | 文件数 | 行数 | 要点 |
|---|---|---|---|
| crdl（二进制解码） | 4 | 1,348 | CRDL-FLD 容器、GPH/FPH 多面体、FLD 六面体、场量节 |
| model（数据模型） | 4 | 782 | FieldFile / 9 种 PostObject / FileSet 序列 / loader 注册表 |
| render（渲染） | 13 | ~3,900 | 每对象独立管线 + scene 分层 actor + 导出 |
| gui（界面） | 8 | ~4,500 | 主窗口 / 41 tab 平铺属性面板 / 对象树 / 时间线 |
| tests | 5 | 84 项 | test_gui 66 + scene_snapshot 5 + crdl/mesh 13 |

### 2.2 已实现能力（DEV_PLAN 历史审计 A–J 全部闭环）

- **格式解析**：FPH/GPH（LS_Nodes 三方言自动判别、LS_Links 多面体、Part/Cvol/区域/装配）、FLD（hex8 + 材料 + NGON 面 + BC 计划 + 节点场）；loader 注册表诚实区分可加载与探测（CGNS-HDF5/ADF 探测、EMT 别名）。
- **对象模型 + 渲染管线**：Main/Surface/Plane/Particle/Isosurface/Point/Streamline/Volume/Colorbar/Light（10 kind），其中 9 个有独立渲染管线；Plane 16-tab 全映射（Contour 云图/等值线/数值标注、Vector 4 种位置+投影+定长、Mesh/Boundary/Subline、Oil Flow、Trim/Clip、Automove 动画、Pick、标量/矢量积分、Texture、Font）。
- **GUI 贯通**：Create 菜单/工具栏真实创建对象、对象树 eye 显隐/双击激活、PropertyHost 平铺面板 + pin、Draw 锤子按钮提交、时间线 Static/Cycle/Time + Play/Pause/Loop + 序列联动、状态栏坐标。
- **周边**：STA 保存/读取（JSON 全字段往返）、PNG/JPEG 截图、打印、Environment 对话框、QSettings 选项、LoadWorker 线程（未接线）、全局 Colorbar LUT 注册表、坐标系/等轴视图、无头测试范式（enable_3d=False）。

### 2.3 质量基线

- 测试 84 项收集；本会话沙箱内执行：**76 通过、1 失败 + 7 错误均为环境性**（沙箱拒绝写入 `Temp/opencode` 与 pytest basetemp；非代码缺陷）。真实环境（DEV_PLAN 记录）84 全过。
- 源码 grep TODO/FIXME/NYI/NotImplemented：**0 命中**——stub 均为行为性、无标注（见 §7 建议）。
- 提交历史活跃，最近提交：性能优化（载入 2.07s→0.88s）、增量 `Scene.apply_to_object`、loader 诚实化等。

---

## 3. scPOST（2025.2）功能基线

### 3.1 对象模型（VB 接口权威清单，38 个类）

**Application / 窗口类**：Application、Global Window、Message Window、Draw Window、Environment。
**数据类**：FLD File、Neutral File、Time Series（TM，CSV 导入）、Max and Min（OT，.ot 文件）、RegionBC。
**几何对象（30 种）**：Surface(FullSurf)、Isosurface、Plane（Unlimited + Limited 两种）、Colorbar、Streamline(FlowLines)、Pathline(PCL)、Particle、Point、Volume(Whole)、Cylinder、Circle、Curve(Line)、Region、Bar(Stick)、Text、Bitmap、Gradation(Sky)、Grouping、Information、Light、Mirror Copy、Periodical Copy、UFO、Compare Scales(Measure)、Folder、Graph(1DGraph)、Camera(SaveBmp)、Turbo（含 Meridional / Blade-to-Blade / Turbo2DView / TurboSurface / TurboLine）。

程序字符串佐证：`OpenGLObject*` 类 40+（含 `OpenGLObjectVolumeRenderer` 体渲染、`OpenGLObjectUFO`、`OpenGLObjectTurbo*` 家族、`OpenGLObjectSky` 渐变背景、`CutPlaneHandle` 交互手柄）。

### 3.2 数据层能力（FLD File 类 125 方法）

- **Cycle 管理**：AddCycList / DelCycList / SetAutoCycle / SetCurCycleID / GetCurTime / GetCycleNum / ResetCycOpe。
- **变量注册引擎**：CreateVar / CreateVarALLCYC / CreateVarCombinationVelocity / CreateVarDST / CreateVarNORMAL / DeleteVar / SetVarTitle；表达式算子（字符串证据）：ifeq()、积分结果命名（IntegNumeRes）、梯度/旋度/散度/涡量（Gradient of…、Vorticity）。
- **几何查询 API**：GetNodeXYZ / GetNodesOfElement / GetNodesOfFace / GetNodesOfSurfaceRegion / GetElementsOfVolumeRegion / GetAdjacentElementOfFace / GetBoundingBox / GetScalar(Array) / GetVecteor(Array) / GetScalarMinMaxByVol / GetVariableMin/Max。
- **区域/MAT 映射**：GetMATNOfElement / GetMATIDofVOL / GetVOLIDbyElement / GetRgnName / GetOverlappingRegionCount。
- **导出**：SaveSTA / SaveCradleViewer / SaveFBX / SaveGLTF / SaveSTL / SaveVRML；ApplySTA（按对象/全局应用模式）。
- **杂项**：SplitView（并排对比）、SetUseUndoBuffer / SetUseAutoSave（undo + 自动备份）、PrepareMinMaxPos、AnimationStart/Stop（Easy Animation）、SetDisplayObjName（对象名气球显示）、ObjectNameArrange。

### 3.3 文件格式面

FLD / FPH / GPH / iFLD（Trimming Open / Remote Open 局部读取）/ CGNS（HDF5+ADF）/ XDMF / Adams(.res/.adm) / Nastran / Marc(.t16/.t19) / STA / TM CSV / OT 文件 / Neutral File / 粒子导出(PTCL/CSV) / FBX / GLTF / STL / VRML / CradleViewer 格式。

### 3.4 高级功能面（程序字符串证据计数）

Turbo 机械（118 条：Meridional/Blade-to-Blade/Blade Region/SmartBlades/Mass Flow all blades）、体渲染器（18 条）、Graph 1D（106 条）、Max&Min/Measure（68 条）、Pathline/OilFlow/Collision/Intersection test（68 条）、Particle（58 条，含碰撞检测、CSV 导出）、Camera/图像保存（54 条）、光照特效 Luster/Water/镜面/亮度（42 条）、Undo/自动备份（24 条）、Deform/Scaling/CycRotate（16 条）、Pick/Probe（34 条）、STA 应用模式（114 条）。

### 3.5 附属工具（Tools 手册）

scConverter（15+ 种格式互转、Mapping 映射、场文件编辑、视频编辑）、CradleViewer（VR/SteamVR/Oculus、独立查看器、OCX 嵌入 Office）、HeatPathView（热路径分析）。这些是独立 exe，scPOST 主程序仅联动。

---

## 4. 功能完整度对比矩阵

> ✅ 已实现　🟡 部分实现（有实质管线但有缺口）　❌ 缺失/仅 stub　➖ 规划明确不做

### 4.1 数据层

| scPOST 能力 | flowviewer 状态 | 缺口说明 |
|---|---|---|
| FLD/FPH/GPH 读取 | ✅ | 三方言节点判别、多面体/六面体、区域/Part/BC 齐备 |
| CGNS 读取 | ❌ | 仅 h5py/ADF 探测 + 提示；无解析器 |
| iFLD 局部读取（Trimming/Remote） | ❌ | 注册为普通 FLD loader |
| XDMF/Adams/Nastran/Marc | ❌ | 仅对话框过滤器广告 |
| EMT | ❌ | 探测为 fph 家族，无 loader |
| Neutral File | ❌ | 完全未引用 |
| Cycle 列表管理（Add/Del/Auto） | 🟡 | FileSet 扫描 + 播放；无 Add/Del/自定义 cycle 列表 |
| 变量注册表达式引擎 | ❌ | 无 CreateVar/算子/派生变量 |
| 几何/区域/MAT 查询 API | 🟡 | 内部函数有（classify_volume_region_cells 等），未组织为公开 API |
| Time Series 对象（TM CSV） | ❌ | 仅 Plane pick_cycle_graph 标志残留 |
| Max and Min 文件（OT） | ❌ | 无 |
| 粒子数据 | 🟡 | 可解析，但 FieldFile 只存 has_particles 标志，渲染层重开文件 |

### 4.2 对象模型（30 种几何对象对照）

| scPOST 对象 | flowviewer | 说明 |
|---|---|---|
| Surface | ✅ | 8-tab；Region/Contour/Vector/Mesh/Trim/积分管线存在（积分未接入 build） |
| Plane（Unlimited/Limited） | ✅ | 16-tab 最完整管线；Limited=Trim 语义靠坐标范围实现 |
| Isosurface | ✅ | Contour/Line/Vector |
| Streamline(FlowLines) | 🟡 | FPH 走 vtkStreamTracer；FLD 退化 numpy 最近点 Euler（规避 VTK hex 定位器崩溃）；constant_length 忽略 |
| Pathline(PCL) | ❌ | 完全缺失（scPOST 为独立对象） |
| Particle | 🟡 | Points/Sphere/箭头；标量/矢量选择、Intersection、Trim、Cloth 等 tab 控件不生效 |
| Point | ✅ | 标记 + 探针；标注固定屏幕位（不锚定 marker） |
| Volume(Whole) | 🟡 | vtkDataSetMapper 半透明 cell；无体渲染光线投射；MAT/区域过滤硬编码关闭 |
| Colorbar | 🟡 | 全局 LUT + ScalarBarActor；LUT 未接到各对象 mapper（Fix 范围只影响 bar 本身） |
| Cylinder / Circle | ❌ | Create 菜单 _nyi stub |
| Curve(Line) | ❌ | 无 |
| Region 对象 | 🟡 | 数据层有 Region，无独立可创建对象 |
| Bar(Stick) | ❌ | 无 |
| Text / Bitmap | ❌ | Create 菜单 stub（Text）/完全缺失（Bitmap） |
| Gradation(Sky) | ❌ | 无（场景渐变背景近似 Sky 效果） |
| Grouping | ❌ | 无 |
| Information | ❌ | 无（仅打开对话框文件信息预览 + Diagnostics 转储） |
| Light | ❌ | 模型有 LightObject 空壳，树有 Light (1) 节点但不可激活；luster/water 仅 Plane 轮廓镜面近似 |
| Mirror Copy | ❌ | 无 |
| Periodical Copy | ❌ | 无 |
| UFO | ❌ | 无 |
| Compare Scales(Measure) | 🟡 | View→Compare 仅日志 TBD |
| Folder | ❌ | 无（对象树分组缺失） |
| Graph(1D) | ❌ | Create 菜单 stub |
| Camera(SaveBmp) | 🟡 | 视图导航有；Camera 设置对话框 stub；连续截图/动画帧导出无 |
| Turbo 家族 | ❌ | 无（明确 P0 之外） |
| RegionBC(RNAT) | ❌ | 无 |

### 4.3 GUI / 交互

| scPOST 能力 | flowviewer 状态 | 说明 |
|---|---|---|
| 窗口布局（Control/Draw/Message/Timeline/Status） | ✅ | 与手册 Layout 对齐 |
| 菜单 File/Create/Display/View/Option/Help | 🟡 | 8 项 _nyi（Cylinder/Circle/Vector/Light/Text/Graph/Camera/Unit） |
| 对象树 eye/hand（individual 模式） | 🟡 | 有 eye 显隐；无 hand/个体模式语义 |
| 平铺属性面板 | ✅ | 41 tab 全接线（自定义 UX，非 scPOST 弹窗式） |
| 时间线（Static/Cycle/Time/Sync） | 🟡 | 播放/循环可用；Sync、Ver/Scale 编辑 inert |
| Pick / 探针 | 🟡 | 有 vtkPropPicker + Plane Pick tab；无全局拾取标注流程 |
| 交互手柄（CutPlaneHandle 拖动） | ❌ | 切面只能面板/旋转按钮操作 |
| Undo / 自动备份 | ❌ | 无 undo buffer、无 auto save |
| 并排 SplitView 对比 | ❌ | Compare 未实现 |
| 消息窗口保存文件/Illustrate Log | ❌ | 仅内存日志 |
| Mouse 1/2/3-Button | ✅ | Trackball/Rubber 已接；Select 模式 inert |
| 动画（Easy Animation/AutoMove） | 🟡 | Automove Line/Sin/Cos/Rotation 可播；Custom Path(CSV) 未实现；每帧全量重建 |
| 对象名气球显示（ObjectNameDisplay） | ❌ | 无 |

### 4.4 渲染质量

| 能力 | flowviewer 状态 | 说明 |
|---|---|---|
| 标量云图 / 等值线 / 数值标注 | 🟡 | Plane 全有；Surface/Isosurface 无等值线数值标注；contour_paint 未用 |
| 矢量箭头 | 🟡 | glyph 共享管线；密度控制仅 Plane（space_v、thickness、contour_color 忽略）；Surface/Volume 无密度控制 |
| 体渲染（VolumeRenderer） | ❌ | 无 vtkVolume/vtkSmartVolumeMapper/传递函数 |
| 光照特效（Luster/Water/阴影） | ❌ | 仅 Plane 轮廓 specular 近似 |
| 纹理 | 🟡 | 仅 Plane 切面（Method/位置忽略）；Surface/Volume 无 |
| 字体 | 🟡 | 仅字号生效；font_name/float 忽略 |
| 裁剪 | 🟡 | 坐标范围 trim/clip；trim_objects（对其他对象裁剪）未实现 |
| 油流 | 🟡 | 有 vtkStreamTracer 管线；种子跨全域 bbox、步数默认过短、无标量着色 |
| 边界线/Subline | 🟡 | 基础实现；auto/broken/display_location 忽略 |
| 全局色标应用 | ❌ | apply_to_mapper 从未被调用 |

### 4.5 导出 / 自动化 / 生态

| 能力 | flowviewer 状态 | 说明 |
|---|---|---|
| PNG/JPEG 截图、打印 | ✅ | 含无头回退 |
| STA 保存/读取 | 🟡 | JSON 全字段往返；不存相机/图层可见性/Main 元数据；非 scPOST STA 兼容 |
| FBX/GLTF/STL/VRML/CradleViewer 导出 | ❌ | 无 |
| VBS/VBA/Python 自动化（COM） | ❌ | 无（scPOST 有完整 Application COM 接口 + 14 个官方 Python 例程） |
| scConverter / CradleViewer / HeatPathView | ➖ | 独立工具，不属主程序范围 |
| VR | ➖ | 明确不做 |

### 4.6 性能

| 项 | 状态 |
|---|---|
| 大文件 | mmap>512MiB、节偏移索引、向量化描述符扫描（0.88s 载入 tr03_9.fph）✅ |
| 懒加载 | 按节解析 ✅；但每文件开 2 次 buffer、无跨 pass 复用、节索引缓存强引用滞留 ⚠️ |
| 渲染 | FPH 多面体逐 cell Python 建 vtkConvexPointSet、FLD 边界面每次重建 Counter——O(cells) Python 循环 ⚠️ |
| 动画 | Automove 每帧重建整 ugrid+cut ⚠️ |
| UI 线程 | LoadWorker 存在但未接线，File→Open 同步加载 ⚠️ |
| FLD 探针/流线 | VTK 定位器对 hex 崩溃 → numpy O(N)/步最近点退化 ⚠️ |

---

## 5. 差距总结（按影响排序）

1. **【数据】变量注册表达式引擎缺失**——scPOST 后处理的核心差异化能力（派生变量/组合速度/梯度旋度散度/积分变量），flowviewer 完全没有；已解析矢量也以 X/Y/Z 拆分标量存放，无 VTK 矢量元组分组。
2. **【数据】CGNS 仅探测不解析**——项目名含 cgns 且 requirements 有 h5py，CGNS 读取是最大单点格式缺口；EMT/iFLD 半注册状态。
3. **【渲染】无真体渲染、无光照系统、全局色标未接线**——三个「看起来是同一功能，实际差一代」的关键点：Volume 是半透明 cell 而非光线投射；Luster/Water 仅近似；Colorbar Fix 范围不作用于云图。
4. **【对象】17/30 几何对象缺失或空壳**（Pathline/Cylinder/Circle/Curve/Bar/Text/Bitmap/Gradation/Grouping/Information/Light/Mirror/Periodical/UFO/Folder/Graph/Camera 设置），其中 Pathline/Light/Graph/Text/Bitmap 价值密度最高。
5. **【交互】无交互手柄、无 undo、无 Compare 并排、Select 模式 inert**——用户工作流差距明显。
6. **【贯通】大量 tab 字段被渲染层忽略**（Particle 6/7 tab 弱化、Surface MAT/区域过滤、mesh luster/water、Trim-by-object、Automove Custom Path、contour_paint、vector 补项）——UI 已铺好、管线未接，属低垂果实。
7. **【测试】stub 无标记、测试硬编码用户路径**——_nyi 只在 GUI 层 11 处；test_plane_integration_csv_output 硬编码 C:/Users/sdcll/... 导致沙箱/CI 环境失败（本会话实测）。
8. **【工程】单 buffer 重复打开、缓存滞留、pyflakes/CI 未固化**——质量负债。

---

## 6. 改进计划（分阶段建议）

### P0 —— 立即修复（0.5–1 周，纯清理与接线）

| # | 项 | 依据 |
|---|---|---|
| 0.1 | 测试改为 tempfile.mkdtemp()（去掉硬编码用户路径），conftest.py 将 basetemp 指向工作区内目录，恢复沙箱/CI 全绿 | §4.6 测试基线 |
| 0.2 | 全局 Colorbar LUT 接线：ColorbarRegistry.apply_to_mapper 在 plane/surface/isosurface/volume 的 contour actor 构建后调用；Fix 范围真正作用于云图 | render 报告 G4 |
| 0.3 | LightObject 二选一：最小实现（vtkLight 三点光 + 亮度/色温设置）或从树中移除假节点 | §11B 遗留 |
| 0.4 | Particle 管线补 vector_var 选择（替换硬编码 VELP）+ scalar_var 着色 | render 报告 G7 |
| 0.5 | Surface/Volume 应用 cell_filter_mask（MAT / Volume Region tab 真实生效） | render 报告 G2/G11 |
| 0.6 | LoadWorker 接入 File→Open（大文件不冻结 UI） | gui 报告 G5 |

### P1 —— 核心差距（2–4 周）

| # | 项 | 说明 |
|---|---|---|
| 1.1 | **变量注册引擎**：表达式解析器（+ - * / ^ 及 grad/div/rot/ifgt/ifet/ifeq/&/@/delx…）+ 派生变量 VarInfo 缓存 + 对话框（Main→Variable Registration） | 最大功能差距，参考 vb_fldfile CreateVar 族 |
| 1.2 | **CGNS 读取器**：h5py ADF/HDF5 双路径 → 统一为 FieldFile（复用 loaders.probe_format 已完成的探测）；EMT loader 落实 | 项目名即 cgns |
| 1.3 | **真体渲染**：vtkSmartVolumeMapper + 传递函数（scalar_opacity 映射）+ MAT/区域过滤 | scPOST VolumeRenderer 对标 |
| 1.4 | **光照系统**：vtkLight + Luster/Water 参数映射（specular/power/opacity），mesh_luster/mesh_water 落地 | 42 条字符串证据 |
| 1.5 | **Pathline 对象**：复用 streamline 种子 + 时间插值（FileSet 多 cycle 追踪），对齐 PCL 类 | 瞬态分析刚需 |
| 1.6 | **Trim-by-object / 任意裁剪面**：vtkClipPolyData 对其他对象轮廓裁剪 | trim_objects 字段已存在 |

### P2 —— 补齐对象与交互（4–8 周）

| # | 项 |
|---|---|
| 2.1 | Cylinder / Circle 对象（切圆柱面/圆周线 + 面板） |
| 2.2 | Graph（1D 曲线图：沿 Curve 或时间抽取变量 → matplotlib/QtChart 窗口） |
| 2.3 | Text / Bitmap 对象（vtkTextActor / 贴图 + 面板） |
| 2.4 | Information 对象（全局探针：坐标+变量值+node/element 报告） |
| 2.5 | Grouping / Folder（对象树分组节点） |
| 2.6 | Mirror / Periodical Copy（变换矩阵复制对象） |
| 2.7 | 交互手柄：Plane/Surface 拖拽（复用 vtkPropPicker 已建基础） |
| 2.8 | Undo buffer（对象操作栈 + 自动备份 STA，参照 scPOST ~$Undo*.sta） |
| 2.9 | Automove Custom Path（CSV 路径插值 + show_path）与动画帧导出（PNG 序列） |
| 2.10 | Max and Min 文件（OT 读取/写出）与 Time Series（TM CSV 导入） |

### P3 —— 平台化与生态（1–2 季度，视需要）

| # | 项 |
|---|---|
| 3.1 | STA 与 scPOST 兼容（双格式探测）或文档声明私有格式 |
| 3.2 | 导出 STL/VRML/GLTF/FBX（vtkSTLWriter/vtkVRMLExporter/vtkGLTFExporter） |
| 3.3 | 脚本自动化：Python API 薄封装（对象创建/查询/渲染，对齐 VB 类清单子集） |
| 3.4 | Compare 并排视图（SplitView） |
| 3.5 | 性能：ugrid 缓存复用、animation 增量重切、FPH/FLD 边界几何预缓存 |

### 明确不做（与 DEV_PLAN 一致）

Turbo 家族（Meridional/Blade-to-Blade）、UFO、VR、VBS COM 自动化、iFLD Trimming/Remote、scConverter/CradleViewer/HeatPathView 附属工具。

---

## 7. 工程建议

1. **stub 显式化**：把行为性 stub 统一改为 _nyi(...) 或 raise NotImplementedError，让 grep 可审计（当前 0 标记掩盖了 17 个缺失对象与 8 个菜单 stub）。
2. **「UI→渲染」字段消费追踪**：建立 tab 字段 × 渲染管线的消费矩阵测试（每对象加一项「字段消费断言」），防止再出现 Plane 16-tab 式的半接线（当时靠 §8 手工审计才发现 20+ 断链）。
3. **数据层重构**：统一 FLD 场解析（fields.py 与 mesh_fld.py 重复）；FieldFile 缓存粒子数组；单次 open 跨 mesh/fields/meta 复用；节索引缓存加 LRU/显式失效；volume region cell mask 提升为 FieldFile 属性。
4. **矢量元组分组**：VarInfo 增加 components 关联，把 VELX/VELY/VELZ 分组为 VTK 3 分量数组，避免每处 glyph 手工拼装。
5. **CI 固化**：工作区 pytest 基线 + pyflakes；tests/conftest.py 处理沙箱 basetemp；GL 快照测试单独标记。
6. **性能优先清单**：FPH vtkConvexPointSet 逐 cell 构建 → worker 线程预构建缓存；FLD 边界面 Counter 缓存于 FieldFile；Automove 帧间仅重切（缓存网格+标量，只更新平面）。

---

## 8. 结论

flowviewer 已在「**单一稳态场文件 → 核心对象可视化**」路径上达到 scPOST 约 **45–55% 的功能完整度**：数据解码（FPH/GPH/FLD）与 9 种核心对象渲染管线扎实、GUI 贯通度高于预期（41 tab 全接线）、工程测试与文档体系完整。剩余差距集中在四个层面：**数据层派生变量与 CGNS/EMT**（P1.1/1.2）、**渲染代差（体渲染/光照/色标接线）**（P0.2/P1.3/1.4）、**对象面广度（17 种对象缺失）**（P2）、**交互工作流（手柄/undo/对比/脚本）**（P2.7–2.8/P3.3）。按 P0→P1→P2 顺序推进，可在 2 个月内把完整度提升到约 70–80%，达到「实用型后处理工具」的定位；P3 视需求决定是否对标 scPOST 生态面。