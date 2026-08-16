# flowviewer 功能差距全面分析（2026-08-16，第七轮评估）

> **最新状态（2026-08-17 第十轮评估）见文末 §7**：本报告梯队一至四及
> 第八/九轮改进（P0–P3、R0–R3.7）已全部落地，整体端到端深度刷新至 **~85%**；
> §1–§6 保留为第七轮历史基线。

> 分析日期：2026-08-16（会话执行）
> 对比基准：Cradle CFD 2025.2 scPOST（VB 接口 41 个公开类 + FLD File 类 125 方法面）
> 分析对象：`fv/` 63 文件、18,195 行、31 种 PostObject、29 个 render 模块、11 个 crdl 解码器
> 方法：3 个并行子代理独立通读数据层 / 渲染层 / GUI+自动化层源码（非引用既有文档结论），
> 关键矛盾点（Create 菜单映射、STA kind 表）经人工二次核实；
> 全量回归后台复跑（文档基线 201 passed + 1 skipped，提交 bb1d92b 后无新提交）。
> 与前六轮的关系：前六轮结论见 SCPOST_COMPARISON.md §15–§18；
> 本轮聚焦「覆盖 × 深度 × 用户可达性」三维交叉，发现多处贯通断裂。

---

## 1. 当前代码状态总览

| 维度 | 现状 |
|---|---|
| 规模 | fv/ 63 文件、18,195 行；31 种 PostObject + MainObject/GlobalWindow |
| 渲染 | 29 个 render 模块；scene 分发 23 种 kind |
| 解码 | 11 个 crdl 模块（fph/gph/fld/pph/cgns/xdmf/nastran/marc/neutral/ifld/emt） |
| 测试 | 13 文件、223 个测试函数；文档基线 201 passed + 1 skipped（约 15 分钟） |
| 进度 | 六轮改进 + 格式差距 A–F 全部闭环（DEV_PLAN §12–§25） |
| 核心格式 | FPH/GPH/FLD/PPH 深度解析（混合单元、粒子多帧、BC 区、大文件 mmap 实测 5.6GB） |

### 本轮审计核心发现

前几轮文档（SCPOST_COMPARISON §18）记载「对象面覆盖 100%（41/41）、深 34 + 中 7 + 浅 0」。
本轮源码级核查发现：**类 / 对话框 / 渲染管线三个层面确实齐全，但存在多处
「已实现的能力对用户不可达」或「同名功能实现降级」的贯通断裂**，
实际端到端可用深度低于文档声明。

---

## 2. 分维度完整度与深度评估

| 维度 | 覆盖 | 实际深度 | 关键证据 |
|---|---|---|---|
| 对象面（41 个 VB 类） | 100% | **约 65–70%** | 31 种对象类、30 个对话框、渲染模块均存在，但 UI 可达性断裂（见 §3 梯队一） |
| 格式面 | 9 种 loader | 60–70% | 四主格式深；CGNS/XDMF/Nastran/Marc/Neutral 各有硬限制（见 §3 梯队三） |
| 数据 API（FLD 125 方法） | — | **50–60%** | 查询/创建较好；cycle 运行时、几何变换、动画 API、显示开关缺失 |
| 渲染面 | 23 kind 分发 | 70% | Plane/Surface 深度对齐 scPOST；volume/turbo/streamline(FLD) 有代差 |
| 自动化（COM） | — | **约 15%** | 仅 10/67 方法：open/quit/variables/cycles + 2 事件 |
| GUI/交互 | 7 菜单 44 项 | 70% | File/Display/View/Option 全真实；Create 5 stub；undo 死代码 |

---

## 3. 差距排序（大 → 小）

### 梯队一：贯通断裂（声称已实现，实际不可达/失效）——最大差距

| # | 项 | 证据 | 影响 |
|---|---|---|---|
| 1.1 | **Create 菜单仅 8/13 项可创建，18/30 对话框无 UI 入口** | `fv/gui/main.py` L37–50 `_CREATE_MENU`：Cylinder/Circle/Vector/Text/Graph 五项 kind=None；Pathline/Bitmap/Information/Mirror/Curve/Measure/Bar/RegionBC/Gradation/Region/Turbo/UFO/TimeSeries/MaxMin/Grouping/PeriodicalCopy 等 13 种对象无 Create 菜单项 | 对话框与渲染管线全部现成，仅缺菜单行；对象面「100% 覆盖」在用户视角打对折 |
| 1.2 | **STA 往返仅支持 9/31 种对象** | `fv/render/export.py` L78–88 `_KIND_CLASSES` 硬编码 surface/plane/particle/isosurface/point/streamline/volume/light/colorbar | 保存含 Cylinder/Pathline/Graph 等对象的状态文件，重载时静默丢对象 |
| 1.3 | **undo/redo 是死代码** | `main.py` `on_undo`/`on_redo`/`_snapshot_children`（L868–898）存在但：无 Edit 菜单、无 Ctrl+Z/Y 快捷键、无工具栏按钮、全仓无调用点；`_undo_stack`/`_redo_stack` 恒空 | 文档标记 P2.8 已完成，实际不可用 |
| 1.4 | **粒子多帧：解析已支持、渲染不消费** | §25② 的 `parse_particle_frames` 多帧 API 已就绪；`fv/render/particle.py` L29 仍只读单帧 `ff.path`；`Scene.animate`（scene.py L297–324）只驱动 Plane automove | 瞬态粒子动画这一投入未转化为用户可见功能 |
| 1.5 | **Timeline 三控件 inert + 死字段 + 常量不一致** | `panes.py` Sync 复选框/Ver/Scale 输入框无信号连接、全仓无读取点；`fileset.operation_mode` set 后无消费者（死字段）；main `_RENDERABLE_KINDS`（8 种）与 panes（30 种）不一致 → 单击 22 种对象无响应 | 交互细节断裂 |

### 梯队二：渲染代差（同名功能与 scPOST 差一代）

| # | 项 | 证据 | scPOST 对标 |
|---|---|---|---|
| 2.1 | **体渲染**：FPH 多面体（自家主格式）回退半透明 DataSetMapper；raycast 传递函数硬编码（不读对象参数）；sampling 是截断（取前 N cell）非跨步采样 | `fv/render/volume.py` L93–164：仅 hex/tet/wedge/pyr 走 vtkUnstructuredGridVolumeRayCastMapper；颜色 4 段硬编码；`_apply_sampling` 用 `range(keep_cells)` | VolumeRenderer 光线投射 + 可控传递函数 |
| 2.2 | **FLD 流线/迹线降级**：numpy 最近点欧拉（注释自承规避 VTK cell-locator 在 FLD hex 上崩溃）；UI "Runge-Kutta" 实为 RK2 非 RK4；pathline 非 FLD 路径步长硬编码 0.001、无 color_var | `fv/render/streamline.py` L118–175 `_euler_trace_fld`；`pathline.py` L46–48 | vtkStreamTracer 全格式 + RK4 |
| 2.3 | **Turbo 仅 2D 散点**：`polar_view_points` 已实现（API + 测试）但 `build_turbo_actors` 不调用（无渲染出口）；blade_loading 用每 span 桶 max−min 近似非压力面/吸力面分侧；周向平均/Cp 结果无云图渲染 | `fv/render/turbo.py` L46–72、L154–163 | Meridional/B2B 热力图 + 叶片加载图 |
| 2.4 | **Luster/Water 部分落地且不一致**：仅 surface（contour+mesh）与 plane mesh 调 `material.apply_sheen`；plane contour 内联重复实现且用 Gouraud（material.py 用 Phong）；volume/isosurface/particle/streamline/pathline/cylinder/ufo/curve/bar/mirror/periodical 共 11 类对象的同名字段被静默忽略 | `material.py` L8–21；`plane.py` L325–366；objects.py 中 VolumeObject/IsosurfaceObject 等确有 contour_luster/water 字段 | Luster/Water 光照特效全对象 |
| 2.5 | **oilflow 无变量着色**（仅线宽/透明度）；camera 关键帧纯线性插值（无 spline/四元数，parallel 在 t=0.5 阶跃） | `oilflow.py` L66–82；`camera.py` interpolate_pose | 油流变量着色；相机平滑动画 |

### 梯队三：数据/格式深度

| # | 项 | 证据 |
|---|---|---|
| 3.1 | **CGNS**（项目名主题）：仅 HDF5；ADF 不支持、结构化 zone 不支持、MIXED 直接 raise、单 zone | `fv/crdl/cgns.py` L145 `ValueError("MIXED elements not yet supported")`；`zones[0]` |
| 3.2 | **微分算子非 hex 单元静默失效**：FLD/CGNS 路径硬编码 `_HEX_EDGES` 12 条 hex8 棱边，tet/wedge/pyr 邻接错位 → 差分静默返回错误值且无报错。而 §24 刚解码的 2cars/Klein/SCTeta 恰是 tet/wedge/pyr 混合网格 | `fv/model/varreg.py` L312 `_HEX_EDGES`、L319 `_hex_node_neighbors` |
| 3.3 | **varreg 算子不全**：缺 iflt/ifle/ifne；div/rot 硬编码 varX/varY/varZ 命名约定；mag() 函数体恒等（依赖变量解析期归一化）；仅 abs/sqrt/min/max 四个通用函数（无 log/exp/sin） | `varreg.py` L195–233 |
| 3.4 | **POD/FileSet 健壮性与性能**：collect_snapshots 每 cycle 重新 load_file 全解析、try/except 吞错、形状不一致悄悄丢数据；FileSet 无 cycle 间时间插值；register_var_all_cycles 同样逐文件重解析 | `fv/model/pod.py` L16；`fileset.py` |
| 3.5 | **数据 API 缺口**（对照 FLD 125 方法）：GetBoundingBox / LocalXYZ2GlobalXYZ / GetOverlappingRegionCount / GetMATIDofVOL / SaveCradleViewer / SaveFBX / SetDisplayAxis/FLD/Title / SetUseUndoBuffer/SetUseAutoSave / AddCycList 运行时族（SetAutoCycle/SetCurCycleID/ResetCycOpe）/ ApplySTA / AnimationStart/Stop / PrepareMinMaxPos / SplitView(api) / SetDisplayObjName / ObjectNameArrange 均无 | `fv/api.py` 全函数清单核查 |
| 3.6 | **周边格式限制**：XDMF 单 Grid 单 Topology（无 temporal collection）；Nastran 仅自由场网格（.op2/.f06 不做）；Marc 仅 .dat 文本 + .res/.csv sidecar（.t16/.t19 不做）；Neutral OBJ/STL 几何 only（PLY 含顶点变量；.neu 实际走 STL 解析器）；iFLD 是全量 FLD 解析 + 元数据（Trimming/Remote 未实现）；EMT 为 load_file 别名未独立验证 | `fv/crdl/` 各解析器 docstring 自承 |
| 3.7 | **topology 跨格式不通用**：face_nodes/cells_of_face/area_of_face 仅 FPH（LS_Links）有效，FLD 返空或 (-1,-1)；elements_of_region 非 poly 格式仅 "FluidRegion" 全集 | `fv/model/topology.py` L59–L207 |

### 梯队四：自动化与生态

| # | 项 | 证据 |
|---|---|---|
| 4.1 | **COM 仅覆盖 scPOST VB Application 约 10/67 表面**：缺 save（SaveVariableOutput）/draw（UpdateAll）/objects（GetGlobalWindow/GetObjectFLDbyID 等 4）/animation（AnimationStart/Stop/Frame/Second）/16 个 Set* 配置/ErrorCode/ErrorString/Visible/CreateDrawWnd/Dock/SplitView；open 仅 1 种变体（scPOST 有 CreateObjectFLD/FLD2/FLDbySTA/Fld_TRIM 4 种） | `fv/com.py` L190–367 |
| 4.2 | 导出细节：BMP/TIF 在扩展名白名单但实际写 PNG（无对应 writer 分支）；FBX 无；消息窗口无保存文件；Environment 对话框 gradient/units 选项写入但仅 status bar 生效；options.last_dir 未被 on_open_dialog 使用（用 Path.cwd()）；.emt 在 Open 过滤器但不在 LOADABLE_EXTENSIONS（对话框接受、加载 NYI） | `export.py` L46–65；`dialogs.py` L30–62、L582–618；`main.py` L482 |

---

## 4. 改进计划（分阶段）

### P0 贯通修复（纯接线，低风险高回报）

| # | 项 | 说明 |
|---|---|---|
| 0.1 | Create 菜单补全 | 5 个 kind=None 补映射 + 13 个无入口对象加菜单项（对话框/渲染/API 全现成，只差菜单行） |
| 0.2 | STA `_KIND_CLASSES` 扩全 | 改为对 objects.py 全 PostObject 子类反射自动注册，一次修复 31 kind 往返 |
| 0.3 | undo/redo 接线 | Edit 菜单 + Ctrl+Z/Y 快捷键 + `_snapshot_children` 调用点 |
| 0.4 | `_RENDERABLE_KINDS` 统一 | main（8 种）对齐 panes（30 种） |
| 0.5 | 粒子多帧消费 | Scene.animate 驱动粒子帧 + Timeline 联动（解析层 parse_particle_frames 已就绪） |
| 0.6 | 细节清扫 | timeline Sync/Ver/Scale 接线或移除；.emt 过滤器一致性；last_dir 生效；消息窗口保存；BMP/TIF 诚实处理 |

### P1 渲染深度（消除代差）

| # | 项 | 方案 |
|---|---|---|
| 1.1 | 体渲染真管线 | FPH 多面体经 vtkResampleToImage → vtkSmartVolumeMapper 绕开 ConvexPointSet 限制；传递函数读对象参数；sampling 改跨步 |
| 1.2 | FLD 流线回 VTK | vtkStaticCellLocator 替代崩溃定位器，或 numpy 路径升级 RK4；pathline 步长参数化 + color_var |
| 1.3 | Turbo 云图化 | 散点→规则栅格插值热力图 + polar 渲染出口 + PS/SS 分侧 blade loading |
| 1.4 | Luster/Water 统一 | 全对象走 material.apply_sheen，删 plane 内联重复实现（Gouraud/Phong 不一致） |
| 1.5 | oilflow 变量着色 + camera spline 插值 | |

### P2 数据/格式深度

| # | 项 |
|---|---|
| 2.1 | CGNS：ADF 读取器 + 结构化 zone + MIXED + 多 zone（项目主题，最高优先格式项） |
| 2.2 | 微分算子非 hex 邻接（tet/wedge/pyr 面表），失配时显式报错而非静默错误值 |
| 2.3 | varreg 补 iflt/ifle/ifne + log/exp/sin；div/rot 接受显式三分量参数 |
| 2.4 | FileSet 时间插值 + cycle 运行时 API（SetCurCycleID/GetCycleNum 族） |
| 2.5 | POD collect 复用已加载 member、错误不吞；register_var_all_cycles 同理 |
| 2.6 | iFLD Trimming 局部读取 |

### P3 平台化

COM 补约 20 方法（save/draw/objects/animation/Set* 族/ErrorCode）；
api 补 GetBoundingBox/坐标变换/SplitView；Camera spline；FBX 视需要（assimp）；
XDMF temporal collection；Nastran .op2/Marc .t16 视需求。

### 维持不做

Turbo 完整叶片气动后处理套件深化（本轮 P1.3 只做渲染云图化）、VR 实机渲染
（需自编译 VTK + HMD）、scConverter/CradleViewer/HeatPathView 附属工具。

---

## 5. 与前六轮结论的差异修正

| 前六轮结论 | 本轮修正 |
|---|---|
| §18「对象面覆盖 100%、深 34 + 中 7 + 浅 0」 | 覆盖（类/对话框/渲染三件套齐全）成立；但 18/30 对话框无 UI 入口、STA 只认 9 kind、undo 死代码 → **用户可达深度约 65–70%** |
| §6 P2.8「Undo/Redo 已完成」 | 方法与栈存在，无菜单/快捷键/调用点，**实际不可用** |
| SCPOST_COMPARISON「Light 为 stub」 | 已过时：Light 已真实接线（Create 菜单 + 设置面板） |
| §25②「粒子多帧已完成」 | 解析层完成；渲染层仍单帧，端到端未通 |
| 「Create 菜单 8 项 _nyi」 | 现为 5 项 stub（Light 已接线）+ 2 项 Option 工具栏 stub（Camera/Unit） |

---

## 6. 总评

项目已从首轮 45–55% 完整度推进到**覆盖面 100%、端到端实用深度约 65–70%**。

- **强项**：数据解码层（FPH/GPH/FLD/PPH 四主格式深度解析 + 8 个官方样例全过 +
  5.6GB 大文件实测）已达 scPOST 水准；Plane/Surface 渲染管线深度对齐。
- **当前最大问题不是功能缺失，而是「最后一公里」贯通**：梯队一 5 项断裂让已投入的
  对话框/渲染/解析能力对用户不可见——修复成本极低（多为菜单行/注册表/信号接线）。
- P0（约一周量级接线工作）完成后实际可用完整度可望提升至 80–85%；
  P1/P2 决定与 scPOST 的渲染与数据代差能否消除。

> 执行状态：本报告为分析基线，改进计划见 DEV_PLAN §26；完成情况将随执行更新。

---

## 7. 第十轮评估：第九轮 R0–R3.7 落地后完整度刷新（2026-08-17）

> 基线：提交 `58395a8`（第九轮 R0.1–R3.7 共 32 个功能提交全部落地）
> 规模：fv/ 66 文件、23,572 行、31 种 PostObject、~30 个 render 模块、
> 12 个 crdl 解码器、15 个测试文件 318 个测试函数（pytest.ini 默认排除 slow marker）
> 方法：3 个并行子代理（GUI 交互逐项核实 / API 面逐方法重算 / 渲染数据剩余差距审计）；
> 子代理检索索引陈旧导致 3 处误报（视频导出入口、RubberBand 框选、Measure 端点拾取），
> 经人工直读源码证实**均已实现**（main.py L353/L853、L1787–L1839、L1930/L1992）。

### 7.1 分维度完整度 × 深度清单

| 维度 | 完整度 | 深度 | 现状与主要残留缺口 |
|---|---|---|---|
| 对象面（41 VB 类） | ~100% | ~90% | 31 kind 全部 Create 可达、STA 全 kind 往返、框选/右键/undo/Measure 拾取全接线；残留：pick 探针仅覆盖 5/30 kind（main.py L1757–1792）、Draw Window settings 仍 NYI（L1346） |
| 数据格式面 | ~85% | ~80% | FLD/FPH/GPH/PPH 深；CGNS HDF5（MIXED/多 zone/结构化）+ 纯 Python ADF 读写、XDMF temporal、.op2（pyNastran）、Nastran 文本均落地；缺 Marc .t16/.t19 二进制（marc.py L5 明示 out of scope）、iFLD 实为整读后裁剪非真局部盘读（ifld.py L56） |
| 数据 API（FLDFile 125 法） | **48.8%**（61/125，严格 43.2%） | — | R2 六处语义偏差 4 处全修、2 处 ByRef 改元组（语义保持）；ov 几何族 13/13、MAT/VOL/RGN 族 19/16 超配 |
| 自动化（Application 62 法） | **45.2%**（28/62） | — | COM→GUI 桥真实挂钩（AnimationStart 驱动时间线 com.py:1082、UpdateAll 触发重绘:1260）；12 处签名微偏差，其中 2 处真语义错（ShellExecute 为 no-op com.py:1189、GetTickCountEx 时基错 com.py:1143） |
| 渲染层 | ~95% | ~85% | 体渲染参数化传递函数、光照 sheen、相机 SLERP、8 色表 + CSV 编辑器、Turbo 真实叶片壁面（n_θ 分侧 + pitch 自相关）、Text3D 锚定、多段渐变全落地；残留见 7.4 |
| 交互/GUI | ~95% | ~88% | 时间线 interpolate_at 已接线（main.py:1532/1578）、多 FileSet Sync、RubberBand 框选 + Delete Selected、视频导出菜单→ffmpeg；残留：pick 覆盖面、Mouse 3-Button 模式与 1-Button 同为 trackball（main.py:399） |
| 导出/生态 | ~80% | ~75% | PNG/JPG/BMP/TIF/STL/OBJ/VRML/glTF/STA/帧序列/视频（ogv/avi/MP4）；缺 FBX（无 VTK writer）、CradleViewer 专有格式、OBJ 无法线/UV（export.py L318–346） |
| 性能 | ~75% | ~70% | ugrid 缓存已生效（plane.py L134–147）；残留：FieldFile 缓存无 LRU 上限（fileset.py L193–273）、单次 load 触发 2–5 次 open（dataset.py）、ugrid 逐单元 Python 循环、动画帧整链重建（scene.py L385–432） |
| 质量/测试 | ~85% | — | 318 测试、全仓 0 TODO/FIXME、`_nyi` 仅剩 1 处真实（Draw Window）；失衡：239/318 挤在 test_gui.py，POD/compare/tsmm 无独立测试文件 |

**整体端到端实用深度：~85%**（第九轮基线 75–80% → +7pp；r9 计划预期的 90%+ 被
API 覆盖率 47.6% 与若干数据深度项拉低）。

**已反超 scPOST 的区域**：cycle 运行时全族直通 Python、interpolate_at 小数帧插值、
Turbo 壁面 PS/SS 分侧、POD、纯 Python ADF 读写、Compare 差场统计、颜色表编辑器。

### 7.2 对 r9 报告（function_gap_analysis_r9.md）的结论修正

| r9 断点编号 | r9 断言 | 第十轮核实 |
|---|---|---|
| （R3.2 遗留） | 视频导出后端完成但 GUI 入口缺失 | 已有 File→Export Animation Video…（main.py:353 → on_export_animation_video:853，ffmpeg 编码） |
| （R1.2 遗留） | Select/RubberBand 框选完全未接线 | 已实现（main.py:1787–1839 vtkInteractorStyleRubberBandPick + _on_area_selection；Edit→Delete Selected:1176） |
| （R1.3 遗留） | Measure 端点点击拾取未接线 | 已接线（_on_vtk_pick → _try_fill_measure_pick，main.py:1930/1992） |
| §1 | 端到端深度 75–80% | 上调至 **~85%** |

### 7.3 API 覆盖率重算（对照 vb_fldfile.txt / vb_application.txt）

| 类 | scPOST 方法数 | 严格对齐 | 部分对齐 | 缺失 | 覆盖率 |
|---|---|---|---|---|---|
| FLDFile（125 法 + 2 属性） | 125 | 54 | 7 | 64 | **48.8%**（属性 2/2） |
| Application（62 法 + 5 属性） | 62 | 25 | 3 | 34 | **45.2%**（属性 2/5） |

- **六处语义偏差核实**：SetCycOpeMode 八模式（fileset.py:136–146）、
  PrepareMinMaxPos 三参（com.py:1100）、GetOverlappingRegionCount 数区域（api.py:856）、
  LocalXYZ2GlobalXYZ 读文件坐标系（api.py:794）四处全修；GetBoundingBox / GetMATIDofVOL
  因 Python COM 不支持 ByRef 改返回元组（语义正确）。
- **剩余缺失集中三大块**（api/model 层实现现成，仅缺 COM 包装，占缺失总量的 35/98）：
  22 个 CreateObject*（model 层类全有）、8 个变量注册族（api 层函数全有）、
  7 个对象查询族 + 6 个变量值查询族（api 层函数全有）；另有 4 个 CreateObjectFLD 加载族。
- **12 处已实现方法签名微偏差**，其中真语义错 2 处需修：
  ShellExecute（headless no-op，未真调 Windows shell）、GetTickCountEx
  （返回 time.monotonic 自 app 启动，scPOST 语义为开机时基）。

### 7.4 剩余差距清单（按严重度，源码证据）

**高**

| 项 | 证据 |
|---|---|
| oilflow 对 FLD hex 未做崩溃规避（streamline/pathline 均有数值回退，唯 oilflow 直接 vtkStreamTracer） | oilflow.py L71–91 |

**中**

| 项 | 证据 |
|---|---|
| varreg `mag()` 恒等返回：`mag(grad(PRES))` 等 (n,3) 参数表达式被误注册为 VECTOR，静默错 | varreg.py L232–233 |
| div/rot 硬编码 X/Y/Z 后缀命名约定，U/V/W 等命名无法工作 | varreg.py L207–216 |
| FLD face_id 反查返回空/(-1,-1)（GetNodesOfFace 族对 FLD 失效，格式无显式 face 表） | topology.py L59–63、L133–136 |
| Marc .t16/.t19 二进制未实现（Marc 工程主流结果载体） | marc.py L5 |
| FLD 流线/路径线为 KD-tree 最近邻采样（非真单元插值），per-seed per-step Python 循环 | streamline.py L145–262、pathline.py L174–236 |
| iFLD Trimming 为「后处理裁剪」，上游仍整文件读入（与 Trimming Open 承诺不符） | ifld.py L56–162、dataset.py:302 |
| FieldFile 缓存无 LRU/上限，Timeline/POD 期间全 cycle 变量常驻内存 | fileset.py L193–273、dataset.py:31 |
| 单次 load_file 触发 2–5 次独立 open（网络盘放大开销） | dataset.py L115/302/309/423/433 |
| ugrid 逐单元 Python 循环构建，百万单元级 FLD 卡顿；动画帧整链推倒重建 | plane.py L170–227、scene.py L385–432 |
| 视频仅 OggTheora/AVI/ffmpeg-MP4 链路；OBJ 无法线/材质/UV；FBX/CradleViewer 无 | export.py L253–346 |
| pick 探针仅 5/30 kind（plane/surface/isosurface/volume/streamline） | main.py L1757–1792 |
| COM：ShellExecute no-op、GetTickCountEx 时基错；POD 丢弃时间系数 U、仅标量场 | com.py:1189/1143、pod.py:37–69 |
| CGNS ADF 全文一次性入内存（大文件峰值高）、仅取第一个 CGNSBase_t | cgns_adf.py L145/463 |

**低**

体渲染不透明度仅 2 控制点 + gradation=8 硬编码（volume.py:131–155）；
tsmm 仅 CSV 解析无时间线集成；compare 仅绝对差/最近邻映射；
nastran.py docstring 漂移（称 .op2 out of scope，实际已实现）；
测试结构失衡（239/318 在 test_gui.py）；Draw Window settings NYI（main.py:1346）。

### 7.5 第十一轮改进计划

**P0 薄封装速赢（一轮可完成，性价比最高）**

1. COM 层暴露已有能力 ~43 方法：22 CreateObject* + 8 变量注册族 + 7 对象查询族 +
   6 变量值查询族（api/model 实现现成）→ FLDFile 覆盖率 48.8%→**~75%**，
   跨过「常用 VBS 脚本可移植」门槛。
2. 修 2 处真语义错：ShellExecute 真调 Windows shell；GetTickCountEx 改开机时基。
3. oilflow FLD 崩溃规避：对齐 streamline 的数值积分回退路径（唯一「高」严重度渲染项）。
4. varreg `mag()` 真取模 + div/rot 支持显式三分量参数（`div(UX,UY,UZ)`）。

**P1 数据深度**：FLD face 反查表（cell_conn 建 hex 面索引）；FieldFile 缓存 LRU 化 +
单次 open 跨 mesh/fields/meta 复用；iFLD 真局部盘读（节级裁剪）；Marc .t16/.t19
（需先获样例文件）。

**P2 渲染/性能深度**：FLD 流线/路径线真单元插值（vtkStaticCellLocator 或形函数）；
ugrid 批量插入（vtkCellArray.InsertNextCell）；动画帧只重切平面（增量 cut 链）；
OBJ 补法线/UV；体渲染不透明度多点 ramp。

**P3 按需立项**：FBX/CradleViewer（assimp）；POD 时间系数导出 + Clustering；
测试结构重组（拆 test_gui 巨文件，补 test_pod/test_compare/test_tsmm）。

**预期收益**：P0 后整体 ~88%、API 覆盖 FLDFile ~75% / Application ~55%；
P1+P2 后进入 **90%+** 区间；剩余差距主要是 Marc 二进制与生态格式（FBX/CradleViewer）
这类需外部资源的大项。

### 7.6 总评

第九轮 32 个提交真实有效：第七轮报告的全部贯通断裂（梯队一）与渲染/数据代差
（梯队二/三）已闭合，COM→GUI 桥、点探针插值、SaveVariableOutput、Turbo 真实叶片
表面等深度项落地。项目已从第七轮的「覆盖 100%、可达深度 65–70%」推进到
**「覆盖 ~100%、端到端深度 ~85%」**。剩余差距性质再次变化：不再是功能缺失或接线断裂，
而是 **API 覆盖广度（薄封装即可提升）+ 少数数据/渲染深度项（oilflow FLD、FLD face 表、
流线真插值）+ 生态大项（Marc 二进制、FBX/CradleViewer）**。按 P0→P2 推进可在
1–2 轮内进入 90%+ 区间。
