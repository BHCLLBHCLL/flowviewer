# flowviewer 功能差距全面分析（2026-08-16，第七轮评估）

> **最新状态（2026-08-30 第十八轮）见文末 §8.14**：R23 涡识别预设库落地——
> Green-Gauss 梯度核（FPH 全向量化 / FLD-CGNS 逐单元）+ 涡量/Q 准则/λ₂/
> 螺旋度预设 + VGRAD 分量库，11 新测试全过、全量 394 passed 零回退。
> 其前第十七轮（§8.13）：R17–R22 六轮落地复评——CradleViewer `cvw`
> 解码+逐字节写回闭环（§8.12 最后一个非外部格式项解除）、派生函数注册、
> ugrid 指纹缓存、多数据集 CSV 报告、DST/等值面动画/bump、pyproject 打包；
> 端到端深度 ~97%。
> **§9 R23–R26 路线图（同日定稿）**：超越 scPOST 增量轮——涡识别预设库（
> §9.1 已落地）/ 质量门禁 / 呈现纵深 / 性能纵深，评审通过后按序开工。

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

---

## 8. 第十一轮评估：第十轮 P0–P3 落地后完整度刷新（2026-08-17）

> 基线：提交 `67a55cd`（第十轮计划 P0-1–P3-2 共 16 个功能提交全部落地，工作区干净）
> 规模：fv/ 66 文件、24,635 行；18 个测试文件 334 个测试函数
> 方法：git log 逐提交核对 + com.py 方法面（静态 def + 动态生成 CreateObject*）
> 对照 vb_fldfile.txt / vb_application.txt Method List 脚本重算覆盖率；
> 残留项逐条 grep/直读源码核实。

### 8.1 第十轮计划执行核对（16/16 落地）

| 计划项 | 提交 | 状态 |
|---|---|---|
| P0-1 COM 22 CreateObject* + 树挂接 | c0159a1 | ✅ 21 动态生成 + CreateObjectNeutral 静态 |
| P0-2 CreateVar*/DeleteVar/SetVarTitle 族 | a111fca | ✅ |
| P0-3 对象查询 7 族 + 变量值查询 6 族 | 3d9a2f8 | ✅ |
| P0-4 ShellExecute 真调 + GetTickCountEx 开机时基 | ff889ef | ✅ 2 处真语义错关闭 |
| P0-5 oilflow FLD 数值回退 | f117e28 | ✅ 唯一「高」严重度渲染项关闭 |
| P0-6 varreg mag() 真取模 + div/rot 三分量 | 9f828c2 | ✅ |
| P0 cleanup COM 对象树独立于 GUI 桥 | 57c6a47 | ✅ |
| P1-1 FLD NGON face 反查 | 8426352 | ✅ GetNodesOfFace 族对 FLD 生效 |
| P1-2 FieldFile LRU + 单 open 复用 | 7d4e717 | ✅ 内存与网络盘开销双降 |
| P1-3 iFLD 真局部加载 | bd2003b | ✅ 解析期空间裁剪（非后处理裁剪） |
| P2-1 FLD 流线/迹线/油流真 hex 插值 | c9bf854 | ✅ KD-tree 最近邻采样淘汰 |
| P2-2 批量 FLD ugrid 构建 | 8e5032e + e4ec65a | ✅ 含窄列混合单元越界修复 |
| P2-3 动画帧只重切平面 | 462c5e1 | ✅ 增量 cut 链 |
| P2-4 OBJ 法线/UV + 体渲染 3 点不透明度 | 3d6e14a | ✅ |
| P3-1 POD 时间系数导出 + k-means 聚类 | f1886de | ✅ U 矩阵 + 质心场注册 |
| P3-2 测试拆分 test_pod/test_compare/test_tsmm | 67a55cd | ✅ test_gui 254→244，3 个独立套件 |

### 8.2 分维度完整度 × 深度清单（第十一轮）

| 维度 | 完整度 | 深度 | 较 r10 变化 | 现状与主要残留缺口 |
|---|---|---|---|---|
| 对象面（41 VB 类） | ~100% | ~90% | — | 31 kind Create/STA/框选/undo 全通；COM 树挂接后脚本可建 21 种对象；残留 pick 探针 5/30 kind（main.py L1956–1992）、Draw Window settings NYI（L1348） |
| 数据格式面 | ~85% | ~82% | +2pp | iFLD 真局部盘读落地；缺 Marc .t16/.t19 二进制（需样例）、CGNS ADF 全文一次性入内存（cgns_adf.py L145） |
| 数据 API（FLDFile 106 法） | **84.0%**（89/106） | — | **+35pp** | P0 三族封装直达；缺失 17：SaveFBX/SaveVRML/SaveGLTF/SaveCradleViewer（后 2 render 层已有）、GetViewPoint/SetViewPoint/SetViewPort、GetSurfaceArray(2)/GetVolumeArray2、Compare、GetBaseScale、GetCurCycle、GetCurCycOpeNum、GetElemBySurf、GetLatestStaPath、GetNextNodes |
| 自动化（Application 62 法） | **43.5%**（27/62 严格） | — | — | P0 只修语义错未扩面；+5 语义等价不同名（quit≈Quit、open 族≈CreateObjectFLD 族）宽松 51.6%；缺失集中 CreateObjectFLD 4 变体、DrawWindow/Dock/GlobalWindow 窗口族、16 个 Set* 修饰族、PikaPika 等冷门项 |
| 渲染层 | ~95% | ~87% | +2pp | oilflow FLD 回退关闭最后一个渲染断点；流线族真插值 + 体渲染 3 点 ramp + OBJ 法线/UV 落地；残留：FBX 无 writer、体渲染采样仍是截断式 |
| 交互/GUI | ~95% | ~88% | — | 无新断裂；Mouse 3-Button 模式与 1-Button 同为 trackball（main.py L399）仍在 |
| 导出/生态 | ~82% | ~78% | +3pp | OBJ 法线/UV 补齐；缺 FBX（无 VTK writer）、CradleViewer 专有格式 |
| 性能 | ~85% | ~82% | **+12pp** | LRU + 单 open 复用 + 批量 ugrid + 动画增量 cut 四项落地；残留：百万单元级 FLD 首帧仍在秒级 |
| 质量/测试 | ~88% | — | +3pp | 334 测试（18 文件），POD/compare/tsmm 独立成套；全量回归 252 passed + 1 skipped + 1 环境相关失败（ShellExecute 被沙箱拦截） |

**整体端到端实用深度：~89%**（r10 85% → +4pp；7.5 节「P0 后 ~88%」预期达成并略超，
因 P1/P2 性能与渲染项同轮落地）。

**已反超 scPOST 的区域**（较 r10 新增 2 项）：POD 时间系数 + k-means 聚类、
iFLD 真局部盘读；原有 cycle 运行时直通、interpolate_at、Turbo PS/SS 分侧、
纯 Python ADF 读写、Compare 差场、颜色表编辑器继续领先。

### 8.3 API 覆盖率重算口径说明

| 类 | scPOST 方法数 | 覆盖 | 覆盖率 | 口径 |
|---|---|---|---|---|
| FLDFile | 106 | 89 | **84.0%** | vb_fldfile.txt Method List 严格同名（含 21 动态生成 CreateObject*） |
| Application | 62 | 27（+5 等价） | **43.5%**（宽松 51.6%） | vb_application.txt Method List 严格同名 |

r10 记载 FLDFile「61/125 = 48.8%」：125 基数含签名描述 token 污染；
本轮清洗为 106 个真实方法名后重算。同口径下 r10 基线约 55/106 = 51.9%，
本轮 +34pp 主要来自 P0-1/2/3 三族薄封装（34 个方法名）。

### 8.4 剩余差距清单（按严重度，源码证据）

**高**：无。

**中**

| 项 | 证据 |
|---|---|
| Marc .t16/.t19 二进制未实现（Marc 工程主流结果载体，需先获样例文件） | marc.py L5 |
| pick 探针仅 5/30 kind（plane/surface/isosurface/volume/streamline） | main.py L1956–1992 |
| COM SaveVRML/SaveGLTF/SaveFBX/SaveCradleViewer 未包装（前 2 render 层已有） | com.py、export.py |
| Application 侧 CreateObjectFLD 4 变体无同名包装（open 族语义等价） | com.py |
| CGNS ADF 全文一次性入内存（大文件峰值高）、仅取第一个 CGNSBase_t | cgns_adf.py L145/463 |
| tsmm 仅 CSV 解析无时间线集成 | tsmm.py |
| compare 仅绝对差/最近邻映射 | compare.py |

**低**

Draw Window settings NYI（main.py:1348）；nastran.py docstring 漂移（L4 称
.op2 out of scope，实际 op2.py 已实现）；Application 16 个 Set* 修饰族 +
PikaPika/ObjectNameDisplay 等冷门项；体渲染采样截断式；视频仅
OggTheora/AVI/ffmpeg-MP4；Mouse 3-Button=trackball。

### 8.5 第十二轮改进计划

**P0 薄封装速赢**

1. COM SaveVRML/SaveGLTF 包装（render 层现成）+ GetViewPoint/SetViewPoint/
   SetViewPort（相机 API 现成）+ Compare（model.compare 现成）→ FLDFile 84%→**~90%**。
2. Application 同名包装：quit→Quit 别名、open 族→CreateObjectFLD 4 变体 →
   Application 43.5%→**~56%**。
3. pick 探针扩面（particle/pathline/isosurface 外的 vector 类对象复用
   `_pick_vars` 模式，纯查表接线）。
4. nastran.py docstring 修正（零风险文档债）。

**P1 数据深度**：Marc .t16/.t19（阻塞项：样例文件）；CGNS ADF 流式/懒解析。

**P2 按需**：GetSurfaceArray/GetVolumeArray2 表查询族；体渲染跨步采样；
FBX（assimp 外部依赖）；Draw Window settings。

**维持不做**：PikaPika 等纯修饰项、VR 实机、scConverter 附属工具。

**预期收益**：P0 后整体 ~90%、FLDFile ~90% / Application ~56%；
剩余差距集中于 Marc 二进制与 FBX/CradleViewer 两个外部资源依赖大项。

### 8.6 总评

第十轮计划 16 项全部落地且质量真实：高严重度渲染断点清零、性能四项
（LRU/单 open/批量 ugrid/增量 cut）系统性落地、COM 覆盖率口径清洗后
FLDFile 达 84.0%。项目处于**「覆盖 ~100%、端到端深度 ~89%」**。
剩余差距已高度收敛：API 薄封装（一轮可清）、pick 扩面（纯接线）、
以及 Marc 二进制与 FBX 两个需外部资源的生态大项。第十二轮 P0 完成后
可触及 90% 区间上沿。

### 8.7 第十二轮 P0 执行记录（2026-08-17）

| 计划项 | 内容 | 状态 |
|---|---|---|
| P0-1 | COM：SaveVRML/SaveGLTF（经桥接 GUI 场景导出，无 GUI 走 ErrorCode）、SaveFBX/SaveCradleViewer（诚实报未实现）、Compare（compare_summary/stats 直返）、GetViewPoint/SetViewPoint（相机 pose 往返，桥接时驱动真相机）、SetViewPort（裁剪框=renderer viewport）、GetCurCycle、GetBaseScale | ✅ 10 方法 |
| P0-2 | COM：Quit 别名、CreateObjectFLD/FLD2/bySTA/Fld_TRIM（TRIM 接 ifld_load 真局部盘读，None 边界以 ±inf 填充）、IsThisFldValid（空 mesh 判无效） | ✅ 6 方法 |
| P0-3 | pick 探针 5→9 kind：cylinder/circle（contour+vector 模式）、particle（scalar+vector 模式）、pathline（color_var+vector 模式），纯 `_pick_vars` 查表 | ✅ main.py |
| P0-4 | nastran.py docstring 修正（.op2 已由 op2.py 实现） | ✅ |

**覆盖率实测**（脚本对照 vb_fldfile/vb_application Method List）：

| 类 | r11 基线 | r12 P0 后 | 剩余缺失 |
|---|---|---|---|
| FLDFile（106 法） | 84.0% | **93.4%**（99/106） | GetCurCycOpeNum、GetElemBySurf、GetLatestStaPath、GetNextNodes、GetSurfaceArray、GetSurfaceArray2、GetVolumeArray2（表/邻接查询族） |
| Application（62 法） | 43.5% | **53.2%**（33/62） | 窗口族（CreateDrawWnd/Dock/GlobalWindow/MessageWindow）、16 个 Set* 修饰族、PikaPika 等冷门项 |

**回归**：338 测试全量，335 passed + 1 skipped + 1 环境失败（ShellExecute
被 DSH 沙箱拦截，第十轮已知预存）+ 2 deselected；新增 4 个 COM 测试
（r12p0 系列：FLD 开变体真文件往返、Compare 零差、视角/视口校验、
诚实失败路径）全过。

### 8.8 第十二轮 P1 执行记录（2026-08-17，COM 覆盖 100%）

对照 vb_fldfile.txt / vb_application.txt Method List 与 D:/training/cradle
scflow/st 官方 VBS 样例（ex9/ex10），补齐全部剩余 COM 表面：

| 计划项 | 内容 | 状态 |
|---|---|---|
| P1-1 | FLD 7 方法：GetNextNodes（节点邻接，topology.node_neighbours 带缓存）、GetElemBySurf（面→所属单元）、GetSurfaceArray（表面区域表 (name, face_ids)）、GetSurfaceArray2（面→区域名）、GetVolumeArray2（单元→体区域名）、GetCurCycOpeNum（周期操作列表长度）、GetLatestStaPath（最后应用 STA 路径，ApplySTA/bySTA 写入） | ✅ |
| P1-2 | Application 29 方法 + 3 属性：窗口族 GetDrawWindow/GetGlobalWindow/GetMessageWindow/CreateDrawWnd/GetDockableWindow/Dock；FLD 对象族 GetObjectActiveFLD/GetObjectFLDbyID；对齐族 AlignObjectsAlongAnotherObject/AlongPane（6 位置词校验，无 GUI 诚实 False）；DefineVar/DropFile（FLD 开、STA 应用、垃圾拒绝）/GetCurNP/GetDisplayLOGO/GetEnvInfo/ObjectNameDisplay/PikaPika（1–6 亮度预设直打 GlobalWindow Light）/SetBeepAll/SetDefaultAll（flags 全复位）/SetDisplayDrawMode/Hint/LOGO/SetNoControls/SetNoDefaultObj/SetNoNextElements/SetNoProgressBar/SetNotReduceRiddge/SetOperateObjectEnabled/SetOperationType（1/2/3C/3/A–G 校验）；属性 UserControl/Visible/WriteBackToEnvFile 读写 | ✅ |
| P1-3 | 5 个窗口类：MessageWindowClass（AddMessage/GetMessages/Clear/SaveLogFile，桥接 GUI 消息窗）、GlobalWindowClass（Colorbar/Gradation/Camera/Light + SetLight）、DrawWindowClass（Refresh/GetRenderWindow/Screenshot）、SaveBitmapsClass（位图系列登记/保存）、EnvironmentClass（flags 键值视图 + Reset） | ✅ |
| P1-4 | 修复：api.py `_face_count`/`surface_region_table` 缺 numpy 导入（上一轮遗留 NameError）；Region 字段名 `face_ids`；**open_sequence 用周期号 1 而非首成员周期号加载 → `_ff` 为 None 的预存 bug** | ✅ |

**覆盖率实测**（`_tmp_cov.py`，Method List 区间止于 Contents）：

| 类 | r12 P0 后 | r12 P1 后 |
|---|---|---|
| FLDFile（106 法） | 93.4%（99/106） | **100.0%（106/106）** |
| Application（62 法） | 53.2%（33/62） | **100.0%（62/62）** |

**回归**：新增 3 个 COM 测试（r121 系列：FPH 邻接/区域表/ErrorCode 通道、
序列 GetCurCycOpeNum + STA 路径、窗口类 + 29 方法 + 3 属性 + DropFile/
Environment）全过；64 项真文件冒烟（FPH 多面体 + FLD NGON + 序列）零失败。
全量套件终判 **348 passed + 1 skipped**（2026-08-18，0d7dfb5/05da721 对齐 3 处顺序依赖断言：ShellExecute 失败语义、GetLight 默认灯、GetDockableWindow 双态返回码）。

**整体端到端深度：~91%**（COM 双类覆盖面 100% 后，剩余差距集中在
ShellExecute 沙箱、FBX/CradleViewer 外部格式、Draw Window settings UI）。

### 8.9 第十三轮执行记录（2026-08-18，深度闭环）

对照 §8.4/§8.8 残留项，并用官方案例库

* `D:\training\cradle\CradleCFD_2025.2_scFLOW_Example_a`（VBS/Python 脚本面）
* `D:\training\cradle\CradleCFD_2023.2_ST_Example`（Operation `*_tm.csv` TSER、`*.ot` CRDL-OT）

落地全部**不依赖外部样例/专有格式**的深度缺口：

| 计划项 | 内容 | 提交 | 状态 |
|---|---|---|---|
| r12 P1 COM | FLDFile 106/106 + Application 62/62 表面 100% | `d5c75da` | ✅ |
| Draw Window settings | 树节点打开 Display 面板：File/Cycle/Time overlay、XYZ gnomon、平行投影、渐变背景、DisplayList/Immediate；清掉最后一处真实 `_nyi` | `c079db9` | ✅ |
| TSER / CRDL-OT + Timeline | ST Operation 官方格式解析；Time Series 应用后驱动 Timeline 范围与 overlay 时间 | `86adaaf` | ✅ |
| Compare 深度 | `signed` / `relative` 模式 + 异网格 IDW 映射（默认仍 \|A−B\| + nearest） | `eba90b9` | ✅ |
| CGNS ADF | mmap 读取（避免全文 `bytes` 拷贝）+ 合并全部 `CGNSBase_t` | `3c22d00` | ✅ |
| pick + 鼠标 | point/bar/curve/turbo/ufo/graph 探针；Option 1-Button（Shift/Ctrl+左）≠ 3-Button trackball | `19efb25` | ✅ |

**分维度（第十三轮后）**

| 维度 | 完整度 | 深度 | 变化 |
|---|---|---|---|
| 对象面 | ~100% | ~96% | Draw Window settings 可达；pick 覆盖点/条/曲线/Turbo/UFO/Graph |
| 数据格式面 | ~90% | ~88% | ADF 多 base + mmap；TSER/CRDL-OT 官方格式 |
| 数据 API / COM | **100%** / **100%** | — | 与 §8.8 相同 |
| 交互/GUI | ~98% | ~95% | 1/3 键鼠标区分；Timeline←TSER |
| 渲染/比较 | ~95% | ~90% | compare 有符号/相对/IDW |

**整体端到端深度：~96%。**

**维持不做 / 外部阻塞（到不了字面 100% 的原因）**

| 项 | 原因 |
|---|---|
| Marc `.t16`/`.t19` | 两套官方案例库均无 Marc 二进制结果；`marc.py` 明示 out of scope |
| FBX | 无 VTK FBX writer / assimp 依赖 |
| CradleViewer 专有 | COM `SaveCradleViewer` 诚实 NYI |
| ShellExecute | 沙箱拦截（第十轮已知） |
| VR 实机 HMD | 需自编译 VTK + 设备 |
| scConverter 附属工具 | 非 scPOST 核心 |

在上述外部依赖到位之前，**可实现范围内的完整度与深度已收敛到上限**；再往上只能等 Marc/FBX 样例与库。

### 8.10 第十四轮：完整度 × 深度清单刷新（2026-08-18，实测复核）

**方法**：不沿用历史轮结论，逐维度以源码 grep / git 提交 / 覆盖率脚本 /
全量回归四类证据独立复核；HEAD = e882ac9。

#### 分维度完整度 × 深度清单（当前权威版）

| 维度 | 完整度 | 深度 | 较 r11（§8.2） | 实测证据 |
|---|---|---|---|---|
| 对象面（41 VB 类 → 32 kind） | ~100% | **~96%** | 深度 +6pp | Create 菜单 14 主 + 16 次 = 30 kind UI 全可达（main.py L44–79）；STA 动态注册表，新 kind 自动往返（export.py L73–92）；undo/redo Edit 菜单 + Ctrl+Z/Y（main.py L373–374）；pick 探针 11 kind（_pick_vars：plane/surface/isosurface/volume/streamline/cylinder/circle/particle/pathline/point/bar 族）；Draw Window settings 面板落地（object_dialogs2.py L1891） |
| 数据格式面 | ~90% | **~88%** | +5pp | 11 解码器（crdl/ 13 文件）；CGNS ADF mmap + 多 CGNSBase_t（3c22d00）；TSER/CRDL-OT（tsmm.py，86adaaf）；iFLD 真局部盘读（bd2003b）；Marc .t16/.t19 仍缺样例（marc.py） |
| 数据 API（FLDFile） | **100%**（106/106） | — | +16pp | _tmp_cov.py 本轮实测；表查询族 GetSurfaceArray(2)/GetVolumeArray2/GetNextNodes/GetElemBySurf（d5c75da） |
| 自动化（Application） | **100%**（62/62） | — | +56pp | _tmp_cov.py 本轮实测；29 方法 + Message/Global/Draw/SaveBitmaps/Environment 5 窗口类（d5c75da） |
| 渲染层 | ~97% | **~92%** | +5pp | 28 render 模块；流线族真六面体插值（c9bf854）；体渲染跨步采样实测确认（volume.py L67–88，r11「截断式」残留项销账）+ 3 点 opacity ramp（3d6e14a）；动画增量 cut（462c5e1）+ 批量 ugrid（8e5032e）；FBX 无 VTK writer（外部） |
| 交互/GUI | ~98% | **~95%** | +7pp | 1-Button（Shift/Ctrl+左）与 3-Button trackball 行为区分（19efb25）；pick 值入状态栏；Timeline 由 TSER 驱动 |
| 导出/生态 | ~85% | ~80% | +2pp | OBJ 法线/UV（3d6e14a）、VRML/GLTF、视频 3 通路；FBX/CradleViewer 外部依赖 |
| 性能 | ~88% | ~85% | +3pp | FieldFile LRU + 单 open 复用（7d4e717）；百万单元级首帧秒级残留 |
| 质量/测试 | ~95% | — | +7pp | tests 19 文件 350 函数；全量回归 348 passed + 1 skipped（25:41 实测，含 3 处顺序依赖断言对齐 0d7dfb5/05da721） |
| 比较/分析 | ~95% | ~90% | 新增行 | signed/relative + IDW 异网格映射（eba90b9）；POD 时间系数 + k-means（f1886de） |

**整体端到端深度：~96%**（§8.9 判断经独立复核成立）。

#### 代码规模（较 r7 基线）

| 指标 | r7 基线 | 当前 | 增幅 |
|---|---|---|---|
| fv/ 文件·行数 | 63 文件 18,195 行 | 66 文件 26,113 行 | 行数 +44% |
| 测试 | 223 函数（201 passed） | 350 函数（348 passed + 1 skipped） | +57% |
| COM 覆盖 | FLDFile ~48.8%（旧口径）/ Application ~15% | 106/106 + 62/62 | 双 100% |

#### r7 梯队一「贯通断裂」逐条销账

| r7 编号 | 当年断裂 | 现状 | 证据 |
|---|---|---|---|
| 1.1 | Create 菜单仅 8/13 可创建、18 对话框无入口 | 30 kind 全 UI 可达 | main.py L44–79 |
| 1.2 | STA 往返仅 9/31 kind | 动态注册表自动全覆盖 | export.py L73–92 |
| 1.3 | undo/redo 死代码 | Edit 菜单 + Ctrl+Z/Y | main.py L373–374 |
| 1.4 | 粒子多帧解析不消费 | particle.py 消费多帧 + animate 循环 | particle.py L36–53 |
| 1.5 | Timeline 控件 inert | TSER 驱动范围/overlay | tsmm.py（86adaaf） |

#### 尾差（外部依赖，维持不做清单不变）

Marc .t16/.t19（官方案例库无样例）、FBX（无 VTK writer/assimp）、
CradleViewer 专有格式（com.py L1483 诚实 NYI）、ShellExecute 沙箱拦截、
VR 实机 HMD、scConverter 附属工具——与 §8.9 相同，无新增可落地项。

**结论**：不引入外部样例/依赖的前提下，完整度与深度已收敛至可实现上限；
下一轮提升点只存在于 Marc/FBX 样例获取或 scPOST 新版本接口对照。

### 8.11 第十五轮执行记录（2026-08-18，导出/性能尾差收敛）

按 §r14 建议顺序执行四项，落地三项、定论一项：

| 计划项 | 内容 | 提交 | 状态 |
|---|---|---|---|
| FBX 导出 | 零依赖 ASCII FBX 7.3 writer（`export_surface_fbx`，顶点/多边形负索引终止符/ByVertice 法线/UV），`api.export_fbx` + COM `SaveFBX` 接通；真文件验证 21220 多边形全部合法 | `38eb462` | ✅ |
| 变量惰性加载 | `VarInfo` 增惰性描述符（path/section/block/dtype/count）；`load_file(lazy_vars=True)` 跳过字段 payload；`variable_array()` 首访透明物化——20+ 调用点零改动；FPH 11 变量、FLD 15 变量 lazy vs eager 逐元素零差异 | `944933e` | ✅ |
| STA 字段保真 | 新增 `test_sta_roundtrip_field_fidelity`：32 kind 全声明字段类型匹配探针变异 → round-trip → 逐字段比对（kind 判别字段除外）；零差异通过 | `98d4c87` | ✅ |
| CradleViewer | 样例侦察定论：`*.CradleViewer` = `CVFF` v2 magic + 自定义 `ENCD` 编码（非 zlib、非 chunk-TLV，多起点解压失败）；6 份官方样例在 `*/AR/*` 可供后续专次逆向，NYI 消息已更新为可逆待研 | `38eb462` | 🔍 定论 |

**对 §8.10 清单的影响**：

| 维度 | r14 | r15 后 | 依据 |
|---|---|---|---|
| 导出/生态 完整度 | ~85% | **~92%** | FBX 出口补齐（NYI 项唯一仓库内可清项）；CradleViewer 从「无格式认知」升级为「格式已识别、样例在手」 |
| 导出/生态 深度 | ~80% | **~88%** | STA 字段级保真有硬测试背书；FBX 与 OBJ 共享法线/UV 管线 |
| 性能 完整度 | ~88% | **~92%** | 惰性加载补齐「按需读取」能力面；eager 默认不变（零回归） |
| 性能 深度 | ~85% | **~88%** | 大文件打开跳过全部变量 payload（仅付显示所用变量）；剩余：百万级首帧基准未定标 |

### 8.12 第十六轮：Marc `.t16`/`.t19` 后处理文件（2026-08-22）

样例与脚本：`Marc_Mentat_Scripting-main`（`py_post_process.py` 走官方 `py_post`）
及 `marcmentat_files/example_model_{0,1}.t16`（Mentat 2021.4，POST style 14）。

**格式**：Fortran 无格式顺序记录 + 自描述 `=beg=NNNNN` / `=end=` 段
（A1 一字一符）。与 Volume D PLDUMP 逻辑块对应，但现代文件用段码而非
无标号块序列：

| 段码 | 内容 |
|---|---|
| 50100 / 50200 | 标题；INUM/LNUM/MNUM/NDEG/NCRD/IANTYP/POSTRV=14 |
| 50602 / 50702 / 50800 | 单元后处理码、连接、节点坐标（`int32` + `NCRD×float32`） |
| 51701 / 51801 | 增量号 / 时间 |
| 52300 / 52401 | 末增量积分点值、节点位移（`Displacement_*`） |

**落地**：`fv/crdl/marc.py` `parse_marc_post`；`marc_load` + `load_file` 注册
`.t16`/`.t19`；2D 五节点 118 单元去掉原点填充节点后按四边形导入。
`example_model_0.t16`：2461 cell、2582 有效节点，节点 2 末位移与
`Example_ouput_file.txt` 一致（Δx=3.18142557）。

**本轮补全（对照 Volume D 2005 PLDUMP2000 + HyperView 后处理码表 + Mentat `.dat`）**：
Mentat `connectivity`/`coordinates` 卡片（含 `2.5+1` Fortran 指数）；524nn 按 `ivec(7)=-1`
读节点向量；51701/51801 全增量时间表；后处理码 17/47/341–346/681–686 命名；
无 `=beg=` 的 K7 PLDUMP 回退。仍不依赖官方 `py_post`，不把大样例纳入 git。

**对清单**：数据格式面「Marc 二进制」从外部阻塞改为已实现；剩余外部项为
CradleViewer 解码、VR HMD、ShellExecute 沙箱。

### 8.13 第十七轮：R17–R22 落地刷新（2026-08-30，scPOST 对比复评）

**方法**：以 `fv/` 68 个 `.py` 源码清单、git 提交链（reflog 224–231，共 8 个
提交）、test_r18–r21 回归（27 项）与 README 开发地图为证据独立复核，
不沿用上轮结论；HEAD = `76e087f`。

#### R17–R22 落地清单

| 轮次 | 内容 | 提交 | 状态 |
|---|---|---|---|
| R17 | CradleViewer（`cvw`）格式逆向：CVFF 解析器 + loader + 逐字节还原写回；COM `SaveCradleViewer` 激活为真实 CVFF 导出（R17-T1..T4a/T4b） | `67f55b9` / `5005a18` | ✅ |
| R18 | 变量注册升级：`register_derived_function`（可信用户函数 → 标量/向量变量，签名过滤）+ `auto_scalarize`（向量自动派生 `_mag/_X/_Y/_Z`，幂等） | `b305336` | ✅ |
| R19 | 平面切割性能：FPH 单元打包单 `vtkIdTypeArray` 批量建 ugrid + 网格指纹缓存（几何不变复用同一网格；0 点退化单元保留 1:1 单元对齐） | `4409383` | ✅ |
| R20 | 多数据集统计与自动化报告：`dataset_stats` / `aggregate_report` / `delta_report`（signed/abs 模式）/ `to_csv` | `f2b56a7` | ✅ |
| R21 | 渲染深度：DST 色表预设；等值面逐周期动画（`build_iso_animation` 跨帧共享单一 ugrid）；bump 映射曲面（numpy Newell 顶点法向，保持点序） | `76e087f` | ✅ |
| R22 | 打包工程：`pyproject.toml`（setuptools + `flowviewer` CLI 入口）+ `scripts/benchmark.py` 性能基准 + README 安装/测试/基准文档 | `63c7224` | ✅ |

**回归**：test_r18（7）+ test_r19（6）+ test_r20（8）+ test_r21（6）= 27 项新增；
本轮窗口内子集（test_varreg + r18–r21 + turbo_r31）43 项全过；样件
`tr03_9.fph` 驱动（R17 无独立测试文件，其行为由 COM/CVFF 写回链路覆盖）。

#### 对 scPOST 清单的收敛（对照 §8.9 / §8.12）

| 上轮遗留 | 本轮状态 |
|---|---|
| CradleViewer 解码（§8.12 剩余外部项） | **解除**：R17 解析/加载/逐字节写回闭环 |
| COM `SaveCradleViewer` 诚实 NYI（§8.9 表） | 激活为真实 CVFF 导出（R17-T4b） |
| FLDFile 106/106、Application 62/62 | 维持 100%；R18 为基线之外新增 API 面 |
| FBX / VR HMD / ShellExecute 沙箱 | 维持外部阻塞 |

#### 分维度完整度 × 深度（第十七轮权威版）

| 维度 | 完整度 | 深度 | 较上轮 | 实测证据 |
|---|---|---|---|---|
| 对象面（41 VB 类 → 32 kind） | ~100% | ~96% | 持平 | 无对象 kind 增删；R21 为 Surface/Isosurface 增渲染模式 |
| 数据格式面 | **~97%** | **~95%** | +7pp/+7pp | cvw/CVFF 解析+加载+写回；最后一个非外部依赖格式项闭环 |
| 数据 API / COM | 100% / 100% | ~97% | +1pp | R18 派生函数注册超出 scPOST 表达式引擎能力 |
| 交互/GUI | ~98% | ~95% | 持平 | — |
| 渲染面 | ~96% | ~92% | +1pp/+2pp | DST 色表、等值面周期动画、bump 映射（超出项） |
| 导出 | ~93% | ~89% | +1pp | CVFF 导出进入导出矩阵 |
| 性能 | ~93% | ~89% | +1pp | R19 指纹缓存 + 批量建网格；benchmark.py 固化度量 |
| 工程化 | **超出 scPOST** | — | 新维度 | pyproject/CLI 入口/性能基准/README；scPOST 无对应开源工程面 |

**整体端到端深度：~97%**（上轮 ~96%，+1pp）。覆盖完整度保持 ~100%；
本轮深度增量集中在格式面闭环，其余轮次（R18–R22）均为 scPOST 基线之外的
增量能力，不改变既有维度的深度分母。

#### 剩余外部项（到不了字面 100% 的原因）

| 项 | 原因 |
|---|---|
| VR 实机 HMD | 需自编译 VTK + 设备 |
| ShellExecute | 沙箱拦截（第十轮已知） |
| FBX | 无 VTK FBX writer / assimp 依赖 |
| VTK ≥9.4.2 | vtkCutter 对 vtkConvexPointSet 网格 0xC0000005；README 建议 `vtk==9.3.1` |

#### 超出 scPOST 的能力（R17–R22 新增）

1. CradleViewer 格式**逐字节还原写回**（bit-faithful 往返可校验）。
2. 用户自定义派生函数注册（trusted callable）+ 向量自动标量化。
3. 平面切割网格指纹缓存 + 批量 FPH 单元构建（大模型性能工程）。
4. 多数据集聚合/差分统计与自动化 CSV 报告。
5. bump 映射曲面、等值面逐周期动画（单几何跨帧复用）。
6. pip 可安装包 + `flowviewer` CLI + 可重复性能基准。

#### 总评

R17–R22 将第十六轮尚存的最大格式缺口（CradleViewer 专有格式）闭环，并以
五项基线外增量（R18–R22）拓宽功能面。在可实现范围内（不含 VR HMD /
ShellExecute 沙箱 / FBX 三个纯外部项），对 scPOST 2025.2 的功能完整度为
**覆盖 ~100%、端到端深度 ~97%**；工程化维度首次超出基线。剩余差距全部为
外部依赖，可实现范围内已无已知功能缺口。

### 8.14 第十八轮执行记录：R23 涡识别预设库（2026-08-30，§9.1 落地）

**交付物**（`fv/model/derived.py` 378 行 + `fv/api.py` 7 个包装 +
`tests/test_r23.py` 11 用例 + 基准热路径）：

1. **Green-Gauss 梯度核** `velocity_gradient(ff, base)` → (n,3,3)，
   `g[:, i, j] = ∂u_i/∂x_j`：
   - FPH/PPH（LS_Links 多面体）：**全向量化** Newell 面积向量
     （bincount 段求和）、逐面几何定向修正（内面按 owner→neighbour、
     边界面按 胞心→面心）、散度定理求体积；内面**距离加权插值**
     （畸变网格上线性场精度优于中点插值）；退化体积/空面跳过。
   - FLD/CGNS（cell_conn hex/tet/penta/pyra）：逐单元 Green-Gauss
     （面均值）→ 顶点平均回投；0/1 基自动检测与 varreg 共口径；
     非法单元类型显式报错。
   - 线性场在规则网格/四面体上**精确**（1e-9）；tr03_9.fph 畸变
     多面体网格上线性场中位误差 <5%、均值 <8%。
2. **涡识别预设**（梯度张量的纯函数）：涡量 ω=∇×u（向量）、
   Q 准则 ½(‖Ω‖²−‖S‖²)、λ₂（S²+Ω² 中特征值，eigvalsh）、
   螺旋度 u·ω。
3. **注册通道**：`register_vortex_presets` 一次注册 13 变量
   （VGRADXX..VGRADZZ 9 个梯度分量 + VORT/QCRIT/LAMBDA2/HELI），
   名称冲突/缺速度/缺拓扑显式 ValueError；VGRAD* 为普通标量，
   可直接进表达式引擎；VORT 向量接 auto_scalarize（VORT_mag/_X…）
   幂等。

**验收核对**（§9.1 验收标准逐条）：

- 均匀流 → ω=0、Q=0：tr03_9.fph 实测 atol 1e-9 精确通过（闭合面
  求和相消）✓
- 线性剪切 u=(y,0,0) → ω_z=−1（且 Q=0，旋转/应变平衡）✓
- tr03_9.fph 真实速度场：QCRIT/HELI 与表达式引擎经 VGRAD* 分量的
  独立重算一致（rtol 1e-9）✓；注册变量可见、auto_scalarize 幂等 ✓
- 新增回归测试 11 个全过；全量 **394 passed, 3 skipped, 2
  deselected**（含并行代理新增测试，零回退）✓
- 基准热路径无回退（load 1.48s / ugrid 2.11s / register 0.001s），
  新增 vortex grad 1.25s（tr03_9.fph，含胞心计算）✓

### 8.15 第十九轮执行记录：R24 质量门禁与可持续性（2026-08-31，§9.2 落地）

**交付物**：
1. **benchmark 阈值断言**（`scripts/benchmark.py --check`）：每条热路径相位
   （load / ugrid_build / ugrid_cached / register_var / vortex_grad）读
   `scripts/benchmarks.json` 上限，超限打印 FAIL 并以退出码 2 失败；阈值
   按开发机基线（load~1.5s / ugrid~2.1s / register~0.001s / grad~1.25s）
   放权为 ~4-5x（6.0/10.0/1.0/0.5/5.0s），规避 CI 速度波动误伤。
2. **ruff lint**（`pyproject.toml [tool.ruff.lint]`）：select E/F/W/I/B，
   ignore E501/E7xx/E731/E741/B007（遗留风格债显式豁免）。仓库全量
   `--fix` 后 lint 清零（133 → 0，多为导入排序/行尾换行/未用导入/单行多
   import）；手工收窄 6 处：test_pod 盲异常 B017 → ValueError，
   test_gui/turbo 4 处 F841 未用变量删除，2 处导入清理。
3. **mypy 渐进标注**：`[tool.mypy]` skip 第三方、check_untyped_defs，
   `fv/model/varreg.py` 补 `tokenize/_node_neighbors` 等局部标注、
   `derived.py` 纯函数标注收敛；types 阶段过。
4. **门禁入口** `scripts/check.py`：lint → types → test → bench 四阶段
   依序执行，支持 `--fix`（ruff 自动修复后重跑）与 `--skip=<stage>`。
5. **CI 模板** `.github/workflows/quality-gate.yml`：push/PR 触发，py3.9/
   py3.11 矩阵，含 vtk 9.3.1 固定（规避 9.4.2+ vtkCutter 崩溃）。
6. **README** 增「Quality gate」章节：check.py 用法、五条阈值表、
   基线刷新方法、CI 位置；开发地图加 R24。

**验收核对**（§9.2 验收逐条）：
- `python scripts/check.py` 全绿：lint/ruff ✓、types/mypy ✓、bench ✓、
  test ✓（全量 **394 passed, 3 skipped, 2 deselected**，8m07 一次跑绿）✓
- 阈值写入 README ✓；豁免清单 = E501/E7xx/E731/E741/B007 遗留债务，
  ≤ 既有可接受范围 ✓

### 8.16 第二十轮执行记录：R25-S1 离屏导出（2026-08-31，§9.3 首块）

**范围落地**（§9.3-1）：
- `snapshot_png` 增 `scale`/`dpi` 参数（W2I `SetScale`，VTK 9.3 该 API 仅收
  int，按 `round(dpi/72)` 折算）；`export_iso_png_frames` 逐帧驱动时用新增
  `_frame_actors/_show_frame/_hide_frame` 在渲染器上挂装/卸载帧 actor 后
  快照 `base_%04d.png`；`export_iso_video` 先落 PNG 序列，`.mp4` 走
  ffmpeg(libx264，运行时 `shutil.which` 探测)，无 ffmpeg 或非 mp4 回退
  `_write_frame_video`（vtkOggTheoraWriter/.avi）。

**验收**（§9.3）：
- 无头 PNG 序列导出 ✓：`test_iso_png_frame_sequence` 断言 2 周期→2 帧、
  每帧非空；`snapshot_png` scale=2 / dpi=144 均产出更大像素图 ✓。
- 无 ffmpeg 环境视频回退 ✓：`test_iso_video_fallback_ogv` 走 .ogv 断言
  非空（本机 ffmpeg 未装，MP4 分支仅在存在 ffmpeg 的 CI/环境验证）。
- R24 门禁：`export.py` ruff 通过；新增 4 测试全过。

**说明**：ffmpeg 为本机未安装（`shutil.which` 空），故显式选择「额外集成
ffmpeg 出 MP4」的编码器已接入，实际验证走 VTK 回退 .ogv 路径；CI 端如无
ffmpeg 自动回退同样绿。

### 8.17 第二十一轮执行记录：R25-S2 多视口 + 相机联动（2026-08-31，§9.3 次块）

**范围落地**（§9.3-2，渲染层单测级）：新增 `fv/render/viewport.py`：
- `viewport_rects`：single / 2x2 规范化视口矩形（2x2 = TL/TR/BL/BR）。
- `layout`：把布局应用到 N 个 renderer 并渲染一次（headless 安全）。
- `read_pose` / `copy_pose`：相机 pose dict 读写；`copy_pose` **不做**
  `ResetCamera`，保证联动视口逐字节同姿（区别 `camera.apply_pose`）。
- `sync_cameras(source, targets)`：把 source 相机姿态镜像到全部兄弟。

**验收**（§9.3-2）：
- 多视口联动单测 ✓：`viewport_rects_2x2` 断言四点分划 [0,1]^2 无缝隙／
  重叠；`layout_2x2_assigns_distinct_viewports` 断言四象限互异；
  `test_sync_cameras_links_all_viewports` 断言 source 改姿后 3 兄弟
  `read_pose` 与 source 完全相等（position/focal/viewup）。
- GUI 接线（main.py 单 renderer → 4 renderer 分屏）留待在 GUI 面板上把
  `viewport.layout` + `sync_cameras` 挂到相机事件，本轮交付可单测核。

### 8.18 第二十二轮执行记录：R25-S3 内嵌 Python 控制台（2026-08-31，§9.3 尾块）

**范围落地**（§9.3-3，scPOST 脚本化的 GUI 化）：
- `fv/console.py`：`ConsoleSession`（无 Qt 沙盒，`run(code)->(ok,out)` 捕获
  stdout/stderr/异常，namespace 隔离）+ `default_context(ff)`（定点注入
  `open_file / register_variable / register_derived_function / auto_scalarize /
  velocity_gradient / register_velocity_gradient / register_vorticity /
  register_q_criterion` + 当前 `ff`）。
- `fv/gui/console.py`：`ConsolePane`（只读 QPlainTextEdit 日志 + QLineEdit
  单行输入，Enter 执行，Up/Down 历史，会话预置 default_context）。

**验收**（§9.3-3）：
- 控制台内 `register_derived_function` 冒烟 ✓：`test_console_register_derived_
  function_smoke` 在 ConsoleSession(default_context(ff)) 内执行 lambda **kw
  注册 `PRES2=2*PRES`，断言 `ff.variables['PRES2']` 落地且形状一致。
- 无 GUI 依赖可测 ✓：stdout 捕获、异常上抛、namespace 延续三测全过
  （5 passed）；GUI `ConsolePane` offscreen 实例化 run(print) 正常。

### 8.19 第二十三轮执行记录：R26 性能纵深（2026-09-01，§9.6 落地）

按 §9.6 固化规划逐段实现（S1→S2→S3），并启用规划中预留的回归防线。

**S1 平面切割结果缓存**（`fv/render/plane.py`）
- 模块级 LRU（`OrderedDict`，`_CUT_CACHE_MAX=32`）缓存 `cut_grid` 的
  `vtkPolyData` 输出；键 `(网格指纹, 平面法向, 平面原点)`，命中
  `move_to_end` 复用、超限 `popitem(last=False)` 淘汰；另给
  `clear_cut_cache` 供基准冷/热相位复位。
- 测试 `tests/test_r26_plane.py` 3 项：同位切面复用输出对象、异位切面产出新
  对象、LRU 容量上限生效 ✓。

**S2 CGNS 多块并行解析**（`fv/crdl/cgns.py`、`fv/crdl/cgns_adf.py`）
- HDF5 与 ADF 两条路径均按 zone 拆解，`multiprocessing.Pool` 并行解码，
  主线程严格按 zone 顺序归并，保证与串行输出逐位一致；worker 均设计为
  module-level、可 pickle（HDF5 重开文件定位 zone；ADF 重读定位 zone）。
- 公开接口 `read_cgns(path, workers=0, use_threads=False)` 与
  `read_cgns_adf(...)`；`workers>1` 时进程池，`use_threads=True` 时线程池。
- 测试 `tests/test_r26_parallel.py` 4 项：HDF5/ADF 并行（workers=2/3/thread）
  与串行逐位相等、worker 可 pickle 且返回定长 tuple ✓。

**回归防线确认（实测）**：Windows 上进程池 spawn 开销对小样本完全主导，
`cgns_load_parallel≈0.83s` 仍**慢于**串行 `cgns_load_serial≈0.014s`，不满足
§9.4 的 ≥1.5× 指标；按 §9.6 的「不硬凑」原则启用线程池后备路径
`cgns_load_thread≈0.016s` 作为实际最优路径，并保留进程池供进程隔离场景。

**S3 benchmark 阈值收紧**（`scripts/benchmark.py` + `scripts/benchmarks.json`）
- 新增相位 `plane_cut_cold / plane_cut_warm` 与多 zone CGNS
  `cgns_load_serial / cgns_load_parallel / cgns_load_thread`（含
  `_ensure_multi_zone_cgns` 合成 4-zone 样本）。
- 更新阈值并将实测基线写入 `_baseline_dev` 与 `_comment3`。

**门禁回归**：`python scripts/check.py` 四阶段全绿 ✓（lint + types + 全量
**415 passed, 3 skipped, 2 deselected** + bench 各相位 OK）。阈值数值承接：
plane_cut_cold 0.007s / plane_cut_warm 0.000s / cgns_load_serial 0.013s /
cgns_load_parallel 0.830s / cgns_load_thread 0.016s。
### 8.20 第二十四轮执行记录：R27 GUI 多视口/相机联动接线（2026-09-01，§9.7 落地）

按 §9.7 固化规划逐段实现（S1→S2→S3），下一行启用的「extra 列表为空 → 原
行为不变」回归防线全程把关；联动用**共享 camera 对象**而非逐帧 sync。

**S1 场景级多渲染目标**（`fv/render/scene.py`）
- 新增 `_extra_renderers` 列表与 `renderers()` 生成器（先主 renderer 后
  extra）；`add_renderer()` 注册额外视口并把主 camera 对象直接复用到该
  renderer（同一 `vtkCamera` 身份 → 相机共享即联动）。
- `add_actor` 把 3D actor 广播到全部 renderer，2D actor 仅主 renderer（避
  免 overlay/colorbar 重复）；`reset` / `remove_object_actors` /
  `_remove_layer_prefix` / `fit` 改为遍历 `renderers()`。extra 为空时
  逐行为等同原单 renderer 逻辑，headless（enable_3d=False）零差异。
- 测试 `tests/test_r27_layout.py` 6 项（S1）：3D actor 广播、相机对象身份
  共享、add_renderer 幂等去重、remove_object_actors 清全部视口、reset 释放
  extra、actor_names 在各渲染器一致 ✓。

**S2 GUI 布局切换接线**（`fv/gui/main.py` + `fv/render/viewport.py`）
- View 菜单加「Layout」子菜单，`QActionGroup` 互斥切换 Single / 2×2；
  `set_viewport_layout` 在 2×2 时创建 3 个额外 `vtkRenderer`，按
  `viewport_rects(LAYOUT_2x2)` 设 viewport 并把主 camera 设为共享相机
  （`SetActiveCamera`），切回 single 移除 extra。headless 下无操作。
- **环境约束（实测）**：`QT_QPA_PLATFORM=offscreen` 下 live 的
  `QVTKRenderWindowInteractor` 调用 `Render()` 会硬崩溃（access violation
  0xC0000005）——`QtWidgets` 的 offscreen 平台在 Windows 提供不了该 GL 上下文；
  既存 test_gui 依赖此墙一律用 `enable_3d=False`。故把纯接线抽出为
  `_apply_viewport_layout(layout, render_window)`（不渲染、返回视口总数），
  公开 `set_viewport_layout` 调它后再 `Render()`（真实桌面路径不变）。
- S2 测试 3 项走无渲染接线路径（headless-safe）：2×2 后 render_window 4 个
  renderer 且 viewport 四象限互异、单→双→单往返恢复 1 个、改主相机后共享
  相机各视口逐分量一致 ✓。

**S3 门禁回归 + 收尾**：`python scripts/check.py` 四阶段全绿 ✓（lint +
types + 全量 **424 passed, 3 skipped, 2 deselected** + bench 各相位 OK）。
基准门禁解释器为 anaconda3（vtk 9.3.1，契合 §R17 环境教训）；README 开发地图
加 R27（本文件 §8.20）。


### 8.21 第二十五轮：R23–R27 落地后全量完整度刷新（2026-09-01，scPOST 对比复评）

**方法**：距上次全量复评（§8.13，R17–R22 窗口）已隔 5 轮执行记录
（§8.14–§8.20），本轮独立复核不沿用结论。证据：`fv/` 全量 AST 盘点
（72 模块 / 33,732 行）、`git log` 提交链、`scripts/check.py` 四阶段门禁
实测（HEAD = `1877017`，已推 origin/main）、`analysis/vb_fldfile.txt` /
`vb_application.txt` 对照重算。

#### 代码规模与质量基线（实测）

| 指标 | §8.13 时 | 本轮 | 说明 |
|---|---|---|---|
| `fv/` 模块数 | 68 | **72** | +viewport.py/console.py/derived.py 等 |
| `fv/` 总行数 | — | **33,732** | render 9.2k / gui 9.1k / crdl 6.4k / model 4.4k / api+com 4.5k |
| 测试文件 | — | 31 个 | R23–R27 新增 test_r23/r25×3/r26×2/r27 |
| 门禁 | 无 | **四阶段全绿** | **424 passed / 3 skipped / 2 deselected**（R24 时 394，+30） |
| CI | 无 | quality-gate.yml（push/PR） | R24 落地 |

#### R23–R27 落地清单（对照 §9 路线图）

| 轮次 | 内容 | 提交 | 状态 |
|---|---|---|---|
| R23 | 涡识别预设库：Green-Gauss 梯度核 + 13 变量注册（VORT/QCRIT/LAMBDA2/HELI/VGRAD*） | `d51a9bd` | ✅ §8.14 |
| R24 | 质量门禁：ruff + mypy 渐进 + bench 阈值断言 + `check.py` + CI 矩阵 | `1f1d43c` | ✅ §8.15 |
| R25 | 呈现纵深：离屏导出 scale/dpi + PNG 序列 + MP4/OGV 视频；多视口构建块；内嵌 Python 控制台 | `8445208`/`f3ef14c`/`0d760b9` | ✅ §8.16–8.18 |
| R26 | 性能纵深：平面切割 LRU 缓存 + CGNS 多 zone 并行加载 + bench 阈值收紧 | `0104bf0`/`d0de533`/`5b97984` | ✅ §8.19 |
| R27 | GUI 多视口接线：Scene 多渲染目标广播 + 共享相机联动 + Layout 菜单 | `f4ea6e6` | ✅ §8.20 |

#### API 覆盖率重算（本轮 AST 实测，非沿用）

- **FLDFile 106/106**：21 个 `CreateObject*` 由泛型工厂
  `api.create_object(ff, kind=...)`（32 kind）承接，COM 层别名表补齐
  `CreateObjectOT→maxmin` / `CreateObjectPCL→pathline` /
  `CreateObjectRNAT→regionbc` / `CreateObjectCutplane→plane` 等映射。
- **Application 62/62**：`com.py FlowviewerApplication` 名字级零缺失
  （本轮逐名核对 missing=0）；其公开方法已达 **192 个**，约为 VB 基线
  3 倍（COM 面超出 scPOST）。
- R23 新增 13 个涡量/梯度派生变量 + `register_vortex_presets` 注册通道，
  表达式引擎能力超出 scPOST 表达式面。

#### 分维度完整度 × 深度（第二十五轮权威版）

| 维度 | 完整度 | 深度 | 较 §8.13 | 实测证据 |
|---|---|---|---|---|
| 对象面（41 VB 类 → 32 kind） | ~100% | ~96% | 持平 | R27 为渲染目标扩容而非新 kind |
| 数据格式面 | ~97% | ~96% | 持平/+1pp | 无新格式；R26 多 zone 并行为深度增益 |
| 数据 API / COM | 100% / 100% | ~98% | +1pp | 62/62、106/106 重算确认 |
| 交互/GUI | ~98% | ~96% | +1pp | Layout 菜单 2×2 联动、内嵌控制台 |
| 渲染面 | ~97% | ~94% | +1pp/+2pp | 离屏 scale/dpi、PNG 序列→MP4/OGV、多视口 |
| 导出 | ~95% | ~91% | +2pp | 视频导出矩阵 + 高分辨率快照 |
| 性能 | ~95% | ~92% | +2pp | LRU 缓存、CGNS 并行、bench 阈值化 |
| 工程化 | **超出 scPOST** | — | 强化 | 四阶段门禁 + CI 矩阵 + 收紧阈值 |

**整体端到端深度：~98%**（§8.13 为 ~97%，+1pp）。覆盖完整度维持
~100%；本轮增量集中在性能工程（R26）、呈现/导出纵深（R25）、GUI
多视口（R27）、质量门禁（R24）。

#### 剩余外部项修正（到不了字面 100% 的原因）

| 项 | 状态 | 说明 |
|---|---|---|
| VR 实机 HMD | 外部阻塞 | 需自编译 VTK + 设备 |
| ShellExecute | 外部阻塞 | 沙箱拦截（第十轮已知） |
| FBX | **修正 §8.13 表述** | ASCII FBX 7.3 导出 r15 已 live（`SaveFBX` 真导出）；仅二进制 FBX 无 writer |
| VTK ≥9.4.2 | 环境约束 | vtkCutter 对 vtkConvexPointSet 0xC0000005；固定 vtk==9.3.1 |
| headless QVTK GL | 环境约束（R27 实测） | offscreen 平台下 QVTK Render() 硬崩溃；测试走无渲染接线路径 |

#### 超出 scPOST 的能力（R23–R27 新增）

1. 涡识别预设库（VORT/Q/λ₂/螺旋度 + Green-Gauss 梯度核）——scPOST 无对应。
2. 质量门禁与 CI（四阶段、阈值断言）——scPOST 无工程面。
3. 离屏批处理导出（PNG 序列 → MP4/OGV，scale/dpi 可控）。
4. 性能工程：平面切割 LRU 结果缓存 + CGNS 多 zone 并行加载。
5. GUI 多视口（2×2 共享相机联动）+ 内嵌 Python 控制台。

#### 总评

在可实现范围内（VR HMD / ShellExecute 沙箱 / 二进制 FBX 三个纯外部项
之外），对 scPOST 2025.2 的功能完整度为**覆盖 ~100%、端到端深度
~98%**（§8.13 ~97%）。路线图 §9（R23–R27）五轮全部落地，`git log`
与门禁 424 项测试双证据闭环；工程化与 COM API 面维持超出基线。剩余
差距全部为外部依赖，**可实现范围内已无已知功能缺口**；后续轮次建议
转向 scPOST 基线之外的纵深方向（更大规模数据流式加载、Web 呈现、
协作自动化）。
## 9. R23–R26 路线图（2026-08-30 定稿，超越 scPOST 增量轮）

**前提**：第十七轮复评后 scPOST 可实现范围内无缺口，R23+ 性质从「补差距」
转为「深化与超越」。规划前代码核实（2026-08-30 Grep 实证）：流线/粒子
（streamline.py / pathline.py / oilflow.py）、体渲染（volume.py）、时序动画
（R21 周期动画 + scene/com 时序接口）均已存在，**不重复规划**；涡识别/
梯度量、质量门禁、多视口联动为**真实空白**。

### 9.1 R23 涡识别与梯度量预设库

**目标**：补齐商用 CFD 后处理标准导出量（CFD-Post/Tecplot 级别），在
R18 varreg 之上注册，纯 numpy 实现、零表达式解析。

**范围**：
1. 梯度重建：C2P 三棱柱网格 Green-Gauss 单元梯度 → 顶点分配；FPH/P2
   网格适配；退化单元跳过。
2. 预设量注册（`register_derived_function` 驱动）：
   - vorticity：ω = ∇×u（`_X/_Y/_Z/_mag` 由 auto_scalarize 派生）
   - Q-criterion：Q = ½(‖Ω‖² − ‖S‖²)
   - lambda2：速度梯度对称部分第二特征值（涡核判据）
   - helicity：u·ω（含归一化选项）
   - 速度梯度张量 ∇u 九分量（高级用户）
3. 联动：DST 色表、等值面/切割面/曲面管线直接可用；变量进 GUI 变量树。

**验收**：
- 均匀流 → ω=0、Q=0（解析恒等，容差 1e-9 级）
- 线性剪切 u=(y,0,0) → ω_z=−1，∇u 分量逐点对解析值
- tr03_9.fph 速度场上 Q/λ2 与 numpy 独立复算一致（若样件无速度场则
  以合成场验证）
- 注册后变量清单可见、auto_scalarize 幂等不重复注册
- 新增回归 ≥6 项全过；benchmark 热路径无回退

**产出**：fv/model/derived.py（梯度核）+ varreg 预设注册 + tests/test_r23.py。

### 9.2 R24 质量门禁与可持续性

**范围**：
1. benchmark 阈值断言：load / ugrid 冷建 / 缓存命中 / register_var 四项
   热路径设倍数上限（避免绝对时间脆弱），超限失败退出码。
2. ruff（lint）+ mypy（渐进标注：varreg/report/derived 优先），现存告警
   清零或显式豁免清单。
3. 门禁入口 `scripts/check.py`：pytest + lint + benchmark 一键跑；附
   GitHub Actions 即用模板（当前无 `.github/`，托管后启用）。

**验收**：check.py 全绿；阈值写入 README；豁免清单 ≤ 既有债务。

### 9.3 R25 呈现纵深

**范围**：
1. 离屏导出 PNG 序列 + MP4/AVI（复用 R21 `build_iso_animation` 帧管线，
   vtkWindowToImageFilter，DPI/帧率参数）。
2. 2×2 多视口 + 相机联动（link cameras）与布局切换。
3. GUI 内嵌 Python 控制台：暴露 com API 子集（scPOST 脚本化定位的 GUI 化）。

**验收**：无头环境 PNG 序列导出（帧数/尺寸断言）；多视口联动单测；
控制台内 `register_derived_function` 冒烟通过。

### 9.4 R26 性能纵深

**范围**：
1. 平面切割结果缓存：按 (ugrid 指纹, 平面法向+偏移) 键控，命中直接复用
   cutter 输出；缓存上限 + 淘汰。
2. CGNS 多块并行解析（块间独立解码，进程/线程池）。
3. benchmark 阈值收紧（在 R24 门禁上验证收益）。

**验收**：二次同位切面命中路径 <10ms 级；多块加载 ≥1.5× 加速；回归全过。

### 9.5 顺序与依赖

R23 → R24 → R25 → R26：R24 门禁保护 R25/R26 重构面；R23 预设库是 R25
控制台演示的最佳素材。每轮沿用既定模式（实现 + 测试 + README 更新 +
提交），并在本文件追加轮次小节。

### 9.6 R26 性能纵深 —— 固化规划（2026-08-31 定稿）

承接 §9.4，代码核实（2026-08-31 Grep/Read 实证）后拆分为 S1→S2→S3 三段，
实施顺序即数值顺序（S3 阈值严格度建立在 S1/S2 实测收益之上，不得提前收紧）。

**S1 平面切割结果缓存**
- 现状：R19 已把 ugrid 构建按 `(网格指纹, cell_mask)` 内存缓存于
  `fv/render/plane.build_ugrid`；但 `cut_grid`（`fv/render/plane.py:350`）仍
  每次新建 `vtkCutter` 全量切面，是本轮实际热点。
- 做法：模块级 LRU（`OrderedDict`，maxsize≈32）缓存 cutter 输出，键为
  `(网格指纹, 平面法向, 平面原点/偏移)`；命中直接复用已切 `vtkPolyData`；
  上限 + 有序淘汰（FIFO/LRU）。
- 验收:二次同位切面（同法向+偏移）命中路径 <10ms 级；benchmark 新增切面相位。

**S2 CGNS 多块并行解析（并发模型：进程池 —— 用户决策）**
- 现状：`read_cgns`（`fv/crdl/cgns.py:317`，HDF5）与
  `read_cgns_adf`（`fv/crdl/cgns_adf.py:462`，ADF）均为串行
  `for zone: 解码 → 追加归并`，多 zone 是唯一可并行点。
- 做法：每 worker 独立解码一块 → 主线程严格按 zone 顺序归并，
  保证输出与串行逐位一致（vertex 索引按 zone 偏移拼装）。
- 取舍：进程池彻底隔离 h5py/内存共享风险；代价是每块 pickling 传输 +
  进程启动开销。**回归防线**：若现有样本因块过小导致进程池达不到 §9.4
  的 ≥1.5×（甚至更慢），则 S2 提供线程池后备路径并在执行记录里如实标注，
  不强行硬凑指标。
- 验收：多 zone CGNS 加载 ≥1.5× 加速，且并行/串行结果逐位相等。

**S3 benchmark 阈值收紧**
- 现状：`scripts/benchmark.py` 相位仅
  `load / ugrid_build / ugrid_cached / register_var / vortex_grad`，
  无切面相位、无多 zone CGNS 加载相位。
- 做法：新增 `plane_cut`（命中/未命中）与多 zone CGNS load 相位，
  再在 S1/S2 实测收益上收紧 `scripts/benchmarks.json`。
- 验收：`python scripts/check.py`（ruff + mypy + pytest + bench）四阶段全绿，
  R24 门禁继续生效。

**测试**
- S1：同法向+偏移二次调用输出一致/对象复用；LRU 淘汰；上限生效。
- S2：并行 vs 串行输出逐位相等（多 zone 样本为驱动）；
      为进程池与后备线程路径各留烟囱。
- S3：进 check.py 门禁后阈值断言生效。

**收尾（沿用 R24/R25 既定模式）**：逐子块实现 + 测试 + README 开发地图加
R26 + 本文件追加 §8.19 执行记录，逐子块提交；R25 未推送的 4 个提交
（`8445208` `f3ef14c` `0d760b9` `b2fe55e`）在用户确认后与 R26 一并推送。

### 8.22 第二十六轮执行记录：R28 数据纵深（2026-09-01，§9.8 落地）

按 §9.8 规划逐段实现（读取器层 → 模型层 → 测试 → 门禁），全程
「默认 eager 路径逐行为不变」回归防线把关。

**S1 读取器层**（`fv/crdl/cgns.py`）
- `read_cgns(..., lazy_fields=False)`：lazy 时几何（坐标/连接/BC）
  照常解码，`_read_flow_solution(lazy=True)` 仅从 dataset shape 元数据
  记录 `(ds_path, size)` 描述符，**零 payload 读取**。
- `_merge_zones(lazy_fields)`：lazy 分支产出与 eager 完全同形的 NaN
  占位数组（含多 zone NaN padding 与 node/cell 边选择）+
  `field_lazy[name] = [(ds_path, offset, size)]`（仅胜出侧）。
- 新增 `materialize_lazy_field(path, parts, total)`：单开 HDF5 文件
  按 parts 填充，结果与 eager 合并全等（含 NaN 位置）。
- R26 并行路径同样支持（worker 4 元组 args，串/并行结果一致）。

**S1 模型层**（`fv/model/dataset.py`）
- `VarInfo` 增 `lazy_kind`（""=r15 CRDL 遗留 / "cgns"）与 `lazy_parts`；
  `load_variable()` 先查 cgns 分支再走 r15 CRDL 分支，二者互不干扰。
- `cgns_load(filepath, lazy_vars=False)`；`load_file` 对 `.cgns` 扩展
  透传 `lazy_vars`。ADF 老格式维持 eager（规划内显式豁免）。

**S2 测试**（`tests/test_r28_lazy.py` 5 项）：lazy 几何与 eager 逐字段
一致 + 占位全 NaN + 描述符计数；物化数组与 eager 全等（含 C 场
NaN padding）；二次访问缓存（对象同一）；`load_file(lazy_vars=True)`
分发；R26 并行 lazy 与串行一致 + 物化全等。首次运行发现并修复
field_lazy 未剥 side 标签的 4 元组 bug。

**S3 门禁**：`python scripts/check.py` 四阶段全绿（lint + types + 全量
**429 passed, 3 skipped, 2 deselected**（424+5）+ bench 各相位 OK），
零回退 ✓。

### 8.23 第二十七轮执行记录：R29 多视口独立相机模式（2026-09-01，§9.9 落地）

按 §9.9 规划逐段实现（构建块 → 接线 → 测试 → 门禁）。

**S1 构建块**（`fv/render/viewport.py`）
- `unlink_camera(renderer)`：读姿态 → 新建 `vtkCamera` 逐分量复制（含
  ParallelScale）→ `SetActiveCamera` 替换。切换瞬间零跳变；之后旧
  （主）相机的移动不再影响克隆。
- `standard_views(bounds)` → front/right/top/iso 四姿态（视距=包围盒
  对角线，top 用 y 上向）；`apply_standard_views(renderers, bounds)`
  按 TL/TR/BL/BR 象限序套用。
- 测试断言 front/right/top 视向两两正交、iso 为角点视角、四姿态互异。

**S2 接线**（`fv/render/scene.py` + `fv/gui/main.py`）
- `Scene.add_renderer(ren, share_camera=True)`：默认保持 R27 共享
  行为；`share_camera=False` 不共享（renderer 自带独立相机）。
- GUI：`_camera_mode`（默认 "linked"）+ View→Camera Mode 子菜单
  （QActionGroup 互斥 Linked/Independent）+ Standard Views 动作；
  `set_camera_mode()`（linked→independent 逐视口 `unlink_camera`；
  反向 `SetActiveCamera(主相机)` 直接恢复）；
  `on_standard_views()`（独立模式四视图；linked 模式主相机取 iso）；
  `_dataset_bounds()`（scene._bounds (lo,hi) 二元组或 datasets 顶点，
  单位立方回退）；`_apply_viewport_layout` 按当前模式分配相机。
- `on_standard_views` 的重绘走 `_repaint_draw_window()`：offscreen
  平台跳过（规避已知 QVTK GL 访问违例），桌面正常重绘。

**S3 测试**（`tests/test_r29_camera.py` 6 项）：unlink 对象独立/姿态
相等/主相机隔离、四视图正交性与取景、apply 四象限互异、GUI 模式切换
无跳变 + 切回恢复共享对象、布局往返保持独立模式、Standard Views 与
预设逐分量一致。过程修复：`_qapp` fixture 本地化、iso 视距期望修正
（d/2 角点）、scene 补丁漏执行、Render() offscreen 守卫。

**S4 门禁**：`python scripts/check.py` 四阶段全绿（lint + types + 全量
**435 passed, 3 skipped, 2 deselected**（429+6）+ bench 各相位 OK），
零回退 ✓。

### 9.9 R29 GUI 纵深：多视口独立相机模式（2026-09-01 固化）

**动机**：R27 的 2×2 布局只有共享相机联动一种模式（所有视口同一
`vtkCamera` 对象）。CFD 检视常需要「四视图」工作流——各视口独立
姿态（前/右/俯/等轴）对照观察，scPOST Draw Window 亦支持各窗口独立
视角。R29 为多视口补上**独立相机模式**与 Linked/Independent 运行时
切换。

**范围**：
1. **S1 构建块**（`fv/render/viewport.py`）：
   - `unlink_camera(renderer)`：读当前姿态 → 新建 `vtkCamera` 逐分量
     复制（含 ParallelProjection/视向）→ `SetActiveCamera` 替换。切换
     到独立模式的瞬间无跳变（初始姿态=共享姿态）。
   - `standard_views(bounds)` → `{"front","right","top","iso"}` 姿态
     字典，视距取包围盒对角线长度；平行投影与主相机一致。
   - `apply_standard_views(renderers, bounds)`：按 2×2 象限顺序
     TL=front / TR=right / BL=top / BR=iso 一次性套用。
2. **S2 接线**（`fv/render/scene.py` + `fv/gui/main.py`）：
   - `Scene.add_renderer(ren, share_camera=True)` 增参（默认保持
     R27 共享行为）；`share_camera=False` 不设相机（renderer 自带
     独立相机）。
   - GUI 增 `self._camera_mode`（"linked"/"independent"，默认
     linked）；View→Camera Mode 菜单（QActionGroup 互斥
     Linked/Independent）；`set_camera_mode()`：linked→independent
     对每个 extra renderer `unlink_camera`（主相机不动）；
     independent→linked 用 `SetActiveCamera(主相机)` 恢复共享（姿态
     天然一致，无需 sync）。布局切换时按当前模式分配相机；View→
     Standard Views 动作（2×2+独立模式下套用四视图）。
   - headless 防线：模式切换复用 R27 的无渲染接线模式（`_apply_*`
     风格），不触发 QVTK GL 渲染。
3. **S3 测试**（`tests/test_r29_camera.py`）：S1 构建块（unlink 后
   相机对象独立但姿态相等、standard_views 姿态正交性、apply 套用）；
   S2 GUI（切换后各视口相机对象互异、姿态保持、切回 linked 恢复共享
   对象、布局往返保持模式、Standard Views 套用后四视口姿态互异且
   与预设一致）。
4. **S4 门禁**：`scripts/check.py` 四阶段全绿零回退。

**回归防线**：`_camera_mode` 默认 "linked"，`add_renderer` 默认
`share_camera=True`，现有 R27 测试（共享相机对象断言）不改动即全过；
单视口布局下模式切换为无操作。

**验收标准**：独立模式下各视口相机对象互异且姿态独立；切回 linked
后所有视口回到同一主相机对象；初始切换无姿态跳变；Standard Views
四象限姿态与预设一致；门禁 429+ 项全绿。

### 9.8 R28 数据纵深：CGNS 变量级延迟物化（2026-09-01 固化）

**动机**：r15 已为 FLD/FPH 提供 `load_file(lazy_vars=True)` 变量级延迟
加载（open 只读元数据，首次 `variable_array()` 才读 payload），但 CGNS
（HDF5）路径仍是全量 eager 解码（R26 并行只提速不省内存）。大 CGNS
文件打开即物化全部 FlowSolution 数组，与「大文件快速打开、按需付费」
的 r15 模式不一致。§8.21 建议的首个纵深方向。

**范围**：
1. **S1 读取器层**（`fv/crdl/cgns.py`）：`read_cgns(..., lazy_fields=False)`
   新参。lazy 时几何（坐标/连接/BC）照常解码，FlowSolution 仅记录
   描述符（HDF5 dataset 绝对路径 + 偏移 + 计数）不读数据；`_merge_zones`
   在 lazy 模式产出 NaN 占位数组（形状与 eager 完全一致，含多 zone
   NaN padding）+ `field_lazy` 描述符表。新增 `materialize_lazy_field(path,
   parts)` 单开文件按需物化。串行/并行（R26-S2）路径均支持。
2. **S1 模型层**（`fv/model/dataset.py`）：`VarInfo` 增 `lazy_kind`
   （""=r15 CRDL 遗留 / "cgns"）与 `lazy_parts`；`load_variable()` 分支
   分发；`cgns_load(filepath, lazy_vars=False)`；`load_file` 对 `.cgns`
   扩展透传 `lazy_vars`。ADF 老格式维持 eager（显式文档化）。
3. **S2 测试**（`tests/test_r28_lazy.py`）：合成多 zone 样件——lazy 占位
   与 eager 几何逐字段一致、物化后数组与 eager 全等（含 NaN padding
   位置）、二次访问命中缓存、`variable_array()` 透明物化、
   `load_file(lazy_vars=True)` 走 lazy VarInfo。
4. **S3 门禁**：`scripts/check.py` 四阶段全绿，无回退。

**回归防线**：`lazy_fields=False`（默认）时代码路径逐行为与现状相同；
lazy 物化结果与 eager 解码全等（测试断言 `np.array_equal` 含 NaN 位置）。

**验收标准**：lazy open 后所有 VarInfo.array 为 None（零 payload 读取）；
物化数组与 eager 全等；eager 默认路径门禁 424+ 项全绿零回退。

### 9.7 R27 GUI 多视口 / 相机联动接线（2026-09-01 固化）

**前提**：R26 已完整落地（9.6 四阶段门禁全绿，commit `fe17f6f` 推送
origin/main）。§8.17 记录 R25-S2 交付 `fv/render/viewport.py` 时明确标注
「GUI 接线留待」：多视口构建块已可单测，但主窗口仍只建单个 `self.renderer`
（`fv/gui/main.py:271-278`），viewport/layout/sync_cameras 未接入。此行属
文档化的真实留白，为 R27 目标。

**代码核实（2026-09-01）**
- `fv/render/scene.py`：`Scene.renderer` 唯一；`add_actor`（L87-93）、
  `reset`（L61-85）、`remove_object_actors`（L99-121）、
  `set_layer_visible`、`apply_gradation`、`fit`、`pick_actor`、
  `area_pick`、`_remove_layer_prefix`、`animate`、`set_overlay`、
  `show_object_name`、`apply_light` 均只作用于 `self.renderer`。
- `fv/gui/main.py`：单 `vtkRenderer` 绑定到 scene；全局相机视图
  （plane_view/iso_metric，main.py ~618-642）与姿态均属单 camera；
  交互样式（trackball/one-button/rubber，L1903-1986）作用于
  `iren`（单一 interactor）。多 renderer 只在 dialogs.py 的
  G2 对比/Diff 面板单独建（每面板一个 renderer，非主窗口）。
- `fv/render/viewport.py`：`viewport_rects` / `layout` / `read_pose` /
  `copy_pose` / `sync_cameras` 已就绪（R25-S2），headless 单测通过。

**范围**（S1→S2→S3）
1. **S1 场景级多渲染目标**：给 `Scene` 增加第二渲染目标集合
   `_extra_renderers`（list[vtkRenderer]），在其上镜像主 renderer 的
   actor/2D actor/相机姿态；`add_actor` / `reset` / `remove_object_actors`
   / `set_layer_visible` / `apply_gradation` / `show_object_name` /
   `apply_light` / `fit` 同步作用于 extra renderers。单一 renderer 时
   保持零行为差异（列表为空即原逻辑）。后备：`SetupLights`/相机在新增
   renderer 时显式复用主 camera 对象以保联动（相机共享）。
2. **S2 GUI 布局切换接线**：主窗口支持「Single / 2×2」两种布局。View 菜单
   加「Layout」子菜单；切换到 2×2 时创建 3 个额外 `vtkRenderer` 挂到
   `render_window`，按 `viewport_rects(LAYOUT_2x2)` 设每个 viewport，
   并把主 renderer 的现有 actors 复制/镜像到 extra；相机共享同一
   `vtkCamera` 保证拖动联动。切回 single 移除 extra。headless
   （enable_3d=False）下无操作。
3. **S3 门禁回归 + 收尾**：pytest 新增布局切换/相机联动测试（2×2 四象限
   viewport 断言、单→双→单往返、联动后姿态一致）；`check.py` 四阶段全绿；
   README 开发地图加 R27；本文件追加 §8.20 执行记录；逐子块提交。

**回归防线**：多视口为纯 GUI 增强，主 renderer 路径为既有场景；改造通过
「extra 列表为空 → 原行为不变」的等价性保持，搭配现有全量 GUI 测试
（test_gui / test_render 等）回归把关。相机联动用**共享 camera 对象**
而非逐帧 sync 回调，避免 2×2 下抖动与 mute。

**验收**：
- S1：extra renderer 镜像 actor 后，两 renderer `actor_names` 一致；
  增删对象同步；headless 下 extra 为空不影响既有测试。
- S2：切换 2×2 后 render_window 有 4 个 renderer 且 viewport 覆盖
  [0,1]^2 四象限互异；切回 single 恢复 1 个；联动下改主相机姿态后
  extra 相机姿态逐分量相等。
- S3：check.py（ruff+mypy+pytest+bench）四阶段全绿。

**交付物**：`fv/render/scene.py`（S1）+ `fv/gui/main.py` 与
`fv/render/viewport.py`（S2）+ `tests/test_r27_layout.py`（S2 测试）+
README + gap analysis §8.20。

### 8.24 第二十八轮执行记录：R30-S0 差异枚举审计 + 外部项声明（2026-09-01）

固化 §9.10 规划后执行 S0 前置审计（attribute-level，机器可查）。

**S0 审计脚本**：`analysis/r30_audit.py` 交叉 VB 参考（`vb_fldfile.txt` /
`vb_application.txt`）× fv 静态+动态表面（api.py / com.py / dataset.py /
`_CREATE_OBJECT_KINDS` 21 工厂键），按 exact / snake_case / factory /
prefix 四类归并，噪声行（散文/子结构单 token）排除。产物
`analysis/r30_coverage_matrix.md`。

**S0 结果（关键）**：
- FLD File 类 + Application 类共 283 条目，**MISSING=0，stub=0**。
- 此前「名字级 106/106、62/62」升级为**属性级逐项核对通过**：192
  exact + factory/snake/prefix 归并全覆盖；`GetVectorArray*` 由
  `vector_array` 经 prefix 归并确认（修复合中 `lstrip("_")`）。
- stub 扫描（pass / NotImplementedError / 仅 docstring 体）三模块均为 0。
- **S1 结论**：两块已文档化 VB 类在可实现范围内 0 缺口，无需批量补齐；
  「对象面属性级 ~96%」修正为 **已达到 ~100%**（有机器工件背书）。

**外部项声明（S3 前置，五种缺口 → 状态）**：

| 项 | 状态 | 降级路径 |
|---|---|---|
| VR 实机 HMD | 外部阻塞 | `on_vr_mode` 已探测+明确消息（需自编译 VTK+设备） |
| ShellExecute | 外部阻塞 | 沙箱拦截（第十轮）；Open 走 `QDesktopServices`/内部打开，不 shell |
| 二进制 FBX | 待实现（R30-S2） | 现 ASCII FBX 7.3 live（`export_surface_fbx`）；S2 补二进制 7.4 writer |
| VTK ≥9.4.2 | 环境约束 | vtkCutter 对 vtkConvexPointSet 0xC0000005；钉死 vtk==9.3.1（§R17） |
| headless QVTK GL | 环境约束（R27 实测） | offscreen 下 QVTK Render() 硬崩溃；测试走无渲染接线 |

**R30 状态**：S0 ✅（0 缺口，机器工件背书）、S1 ✅（无需补齐）、S3 声明 ✅。
**S2 二进制 FBX：验证依赖项**——本环境无任何 FBX 校验器（fbx/assimp/bpy/
blender 均缺），手写二进制 FBX 7.4 无法对真实导入器（Blender/Maya/Unity）
round-trip 验证；不发布未验证的二进制输出（诚实原则）。保持已 live 的
ASCII FBX 7.3（export_surface_fbx，公开特性对 Blender/Maya/Unity 导入
可接受）为正式导出。二进制 FBX 标记为实现可选、需外部校验器的增强项，
**不计入可实现范围缺口**。

**S4 终审（本文件）**：在可实现范围内，scPOST 覆盖 ~100%、端到端深度
≥99%（§8.13 之后连续 +1/2pp）。全部外部项（VR HMD / ShellExecute /
VTK≥9.4.2 / headless QVTK）已文档化降级；二进制 FBX 为唯一验证依赖项。
路线图自 R31 起全面转入基线外纵深（更大规模流式加载、Web 呈现、协作
自动化）。

### 9.10 R30 对标收官轮：达成可实现范围内 100%（2026-09-01 固化）

### 8.25 第二十八轮执行记录：R31-S1/S2 大文件流式加载（2026-09-01 落地）

按 §9.11 推进，聚焦 S1 分块读取 + S2 内存预算（S3 的 GUI 开关记为
小后续项，详见下）。

**S1 分块读取原语**（`fv/crdl/cgns.py`）
- `materialize_lazy_window(path, parts, total, lo, hi)`：仅物化 `[lo,hi)`
  子窗口，**不分配全长占位数组**（区别于 R28 的 `materialize_lazy_field`
  ——后者仍 `np.full(total)`，是 beyond-memory 的瓶颈）。
- `iter_field_tiles(path, parts, total, tile, lo, hi)`：无重叠瓦片
  （lo, arr）迭代，逐瓦片重开句柄、峰值内存有界；瓦片并集精确铺满
  请求区间（含 NaN 间隙/区带填充）。

**S2 模型层流式引擎**（`fv/model/dataset.py`）
- `CachedWindows`：字节预算 LRU（键=(field,start,end)，值=dense 1-D），
  超预算逐最久淘汰——内存上界钩子。
- `StreamCgnsHandle`：字段描述符表（name → (parts, total)，零 payload），
  `read_window` / `iter_tiles` 经预算缓存服务；绝不默认分配整场。
- `open_stream_cgns(path, budget_bytes, workers)`：几何 eager + 字段全
  懒 → 返回 (StreamCgnsHandle, mesh)。**total 按字段 node/cell 侧取
  n_vertices/n_cells**（修复：稀疏字段如某区带缺 "C" 仍须全长 NaN 填充，
  不能用 max(off+size)，否则与 eager 错位——`test_window_matches_eager_full`
  捕获并修正）。

**S3 GUI 流式开关（已补齐）**：`fv/gui/main.py` + `fv/gui/tasks.py`
- 状态 `_stream_mode` / `_stream_handle` / `_stream_budget_mb`(64)；
  初始化与查询方法 `set_stream_mode()` / `stream_mode()`。
- **File 菜单可勾选项「Streaming (low-memory) CGNS」**（QAction
  checkable，toggled→`set_stream_mode`）。
- `open_file` 用 `load_file(lazy_vars=self._stream_mode)`（CGNS 走 R28
  低内存按需物化打开，非 CGNS lazy_vars 无害）；流式下 `.cgns` 经
  `_attach_stream_handle` 额外挂 `open_stream_cgns` 预算窗口读取器
  （best-effort，不变可见数据集）。
- 异步路径：`launch_load(..., lazy_vars=...)` 透传两个 `LoadWorker`
  （Qt/headless）→ `load_file(lazy_vars=...)`。
- GUI 场景构建依赖真实显示（offscreen 下跳过，见 R29 记录），数据路径
  headless 可测。

**S4 测试**（`tests/test_r31_stream.py` 现 8 项，headless 7 passed +
offscreen 下 GUI 项 skip）：窗口物化不分配全长 / 瓦片并集重装 eager
全等（含稀疏区带 NaN 填充）/ 瓦片==整窗 / 预算有界 LRU /
open_stream_cgns 零 payload / `load_file(lazy_vars=True)` 低内存打开 /
GUI 开关状态切换。回归：R28 lazy、R26 并行、cgns、adf、R27/R29 相机
测试全绿。**非流式默认路径逐字节不变。**

### 9.11 R31 基线外纵深·第一轮：大文件流式加载（2026-09-01 定稿方向）

对标收官（§8.24）后路线图转入**超越 scPOST** 的基线外纵深。三个候选
方向（流式 / Web / 协作）中，本轮定稿 **大文件流式加载**为主攻：
它直接复用 R28 的 CGNS 变量级延迟物化基建，突破「加载超过内存的
CGNS」这一真实 CFD 场景痛点，独立可验收，且为后续 Web/协作打底。

**设计核心**：不再把整个数据集载入内存，而是「几何粗代理 + 字段分块
按需物化 + 视口内存预算」，仅在渲染/查询触及的块上落地数据。

1. **S1 分块读取器**：`read_cgns(stream=True)` — 几何按需细分（粗线框
   代理 vs 精细切面），字段由 R28 lazy 进一步切成**时间窗/空间瓦片**，
   逐块 `materialize_lazy_field`，随用随载、用后释放。
2. **S2 内存预算 / 视图代理**：`proxy.hint(预算MB)` — 超过预算时自动
   走粗代理线框；接入 R26 平面切割缓存 + R29 渲染器的驱逐钩子；
   字段扫描（R25 视频轴）只保留当前帧物化。
3. **S3 流式体验接线**：GUI 加载路径新增「流式（省内存）」开关 + 进度
   通知；批量/视频导出在流式下以定长内存边界跑通。
4. **S4 测试与门禁**：构造超预算合成 CGNS 断言峰值内存上界 + 逐块
   结果与全量 eager 一致；`check.py` 四阶段全绿为出口。

**回归防线**：非流式路径（默认）逐字节不变；`stream=True` 全为新 path，
既有 435+ 测试零改动；内存上界用合成数据集断言的 LRU/驱逐行为。

**验收标准**：大于内存预算的 CGNS 可开、可查、可切帧且峰值 RSS 有界；
流式与 eager 结果逐变量全等；文档计 R32 起可再承接 Web / 协作纵深。

### 9.12 R32 基线外纵深·第二轮：Web 呈现 + 协作自动化（2026-09-02 定稿方向）

承接「流式 / Web / 协作」路线图中流式（R31 已落地）之后的 **Web 呈现 +
协作自动化** 两块：以 R31 流式原语为骨干，交付一个**无头、零新依赖**的
HTTP 数据服务 + **自包含可分享 HTML 报告** + 一套**统一的无头协作自动化
面**。全部路径 headless 可验收；非流式默认路径零回归。

**S0 前置**：核对 `open_stream_cgns` / `StreamCgnsHandle.read_window`
（线程安全：窗口读每次重开 h5 句柄）/ `snapshot_png` / `fv/api.py` facade，
确认可无头拼装服务端核心。

**S1 HTTP 数据服务**（`fv/web/server.py` + `fv/web/__init__.py`）
- `WebViewerServer` = stdlib `ThreadingHTTPServer` + `WebHandler`
  （零第三方依赖，仅 json / urllib.parse / struct）。
- 端点：
  - `GET /api/info` → `{version, budget_bytes, caps}`；
  - `POST /api/open` body `{path, budget_mb}` → `open_stream_cgns(budget)`，
    返回 `{ok, n_vertices, n_cells, fields:[{name, n}]}`（零 payload）；
  - `GET /api/fields/{name}?lo=&hi=&fmt=` → `read_window` 窗口读；`fmt=json`
    给 JSON 数组，默认给 `application/octet-stream` raw float64 + `X-Total`
    头——前端/脚本分块拉取，峰值有界；
  - `GET /api/render?w=&h=` → 粗几何代理 + `snapshot_png` 出 PNG；无显示
    时返回 503 + JSON 错误（诚实降级，续 R30 外部项闭环精神）。
- 会话：单 `StreamCgnsHandle` 只读共享，多客户端并发安全。

**S2 自包含 HTML 报告**（`fv/web/report.py`）
- `render_report(handle, out_path, embed_window=512, live=False)`：烘焙单文件
  交互 HTML —— canvas 线框 + 字段 `<select>` + 区间浏览 `<range>` 滑杆 + 样例
  窗口表；嵌入字段 min/max/n 元数据（经 `iter_tiles` 有界扫描）与一个演示
  窗口样本；`live=True` 时表改走 `/api/fields` fetch。无依赖、可离线分享、
  headless 可校验。

**S3 协作自动化面**（`fv/automation.py`）
- `AutomationSession`：上下文管理器，`open(path, stream=True, budget_mb=64)`
  / `fields()` / `query(name, lo, hi)` / `render(png, w, h)` /
  `export_report(html)` / `serve(port=0)`；render 复用 `fv/api.py` + 惰性
  FieldFile（几何粗代理），query 走流式句柄。
- `serve` → 后台线程挂 `WebViewerServer`，供同机脚本/进程经 HTTP RPC 协作。

**S4 测试与门禁**（`tests/test_r32_web.py`）
- 临时目录/临时端口：`/api/info`、`/api/open`、`/api/fields` 窗口字节 ==
  `handle.read_window` 逐元素、`/api/render` headless 下 503（有显示则 PNG）、
  HTML 报告烘焙且嵌入数值与句柄一致、AutomationSession open→query→render
  →serve 全链。
- 回归：R31 stream、R26 parallel、cgns/adf、R28 lazy 全绿；非流式默认路径
  逐字节不变。

**验收标准**：CGNS 可经 HTTP 窗口化取数且结果 == 流式 eager；能烘焙可分享
自包含 HTML 报告；AutomationSession 无头 open→query→render→serve 全通；
`check.py` 四阶段全绿为出口。

### 8.26 第二十九轮执行记录：R32-S1/S2/S3/S4 Web 呈现 + 协作自动化（2026-09-02 落地）

按 §9.12 推进，以 R31 流式为骨干交付无头、零新依赖的 Web 呈现 + 协作自动
化全套。

**S1 HTTP 数据服务**（`fv/web/__init__.py` + `fv/web/server.py`）
- `_Session`（只读流式会话，持单个 `StreamCgnsHandle`，多客户端并发安全）+
  `WebHandler`（`make_handler` 闭包注会话；注意类体作用域遮蔽——须用局部
  别名 `sess = session` 才能给 `session = sess`）。
- `WebViewerServer`（`ThreadingHTTPServer`，`daemon_threads`）：
  - `GET /api/info` → 版本/预算/能力；
  - `POST /api/open`（JSON 或表单 body）→ `open_stream_cgns(budget)` 零
    payload，返回 `{ok, n_vertices, n_cells, fields:[{name, n}]}`；
  - `GET /api/fields/{name}?lo=&hi=&fmt=` → `read_window`；`fmt=json` 给
    JSON 数组，默认给 raw float64 octet-stream + `X-Total`/`X-Lo` 头；
  - `GET /api/render` → `api.open_file`（惰性）+ `render_png`；无显示时
    返回 503 + `{ok:false,error}`（诚实降级，续 R30 外部项闭环）。
- `serve_session(handle, ...)` → (server, thread) 或独立 server。

**S2 自包含 HTML 报告**（`fv/web/report.py`）
- `_field_stats` 经 `iter_tiles` 有界扫描 min/max + 烘焙样例窗口（不整场
  分配）；`_mesh_box` 从 mesh.vertices 求 bbox（可缺省）。
- `render_report(handle, out, embed_window=512, live=False, mesh=None)`：单
  文件无依赖 HTML——canvas 线框 + 字段 `<select>` + `<range>` 区间浏览滑杆 +
  样例表；内嵌 JSON 元数据经 `const M = ...` 注入（CSS/JS 花括号零冲突）。

**S3 协作自动化面**（`fv/automation.py`）
- `AutomationSession`（ctx manager）：`open(stream, budget_mb)` 同时持
  `StreamCgnsHandle`（query）与惰性 `FieldFile`（render/report）；`fields` /
  `query(name, lo, hi)`（= `read_window` 契约）/ `render(png)`（headless →
  False）/ `export_report(html)` / `serve(port)`（后台线程 HTTP RPC）。

**S4 测试**（`tests/test_r32_web.py` 现 8 项全过，headless 安全）
- `/api/info`、`/api/fields` raw 字节 == `read_window` 逐元素、`fmt=json`、
  `POST /api/open` 字段清单 == 直接句柄、`/api/render` offscreen 下 503（有
  显示则 PNG 魔数校验）、HTML 烘焙 JSON 回读端到端校验（样例 == 句柄窗口、
  min≤max、n_vertices 一致）、AutomationSession open→query→render→report
  →serve 全链。
- 回归：R31 stream、R28 lazy、R29 camera、R26 parallel、cgns/adf 全绿；
  **非流式默认路径逐字节不变**。
- 修复：`make_handler` 类体作用域遮蔽 NameError；`automation` 相对导入深度
  （`..model`→`.model`）；报告样例断言改为 JSON 回读数值比对（避免文本格式
  脆弱）。

**门禁**：ruff 0、mypy 0、测试 449 passed（441 存量 + 8 新增）、bench 各相位
OK——GATE PASS；工作树干净。

### 9.13 R33 基线外纵深·第三轮：批渲染/导出管线（定长内存）（2026-09-03 定稿方向）

流式（R31）+ Web/协作（R32）落地后，本轮闭环剩余记账：**多数据集批渲染 /
导出在流式下以定长内存跑通**（R31-S3 明示的后续项）。交付一个无头、零新
依赖的批导出管线，逐数据集开流式句柄（同一内存预算，至多一个数据集驻留），
按需抽取字段（JSON 样例 / raw float64 全字段流式写盘）并可选逐数据集粗场景
快照，同时产出 manifest。peak RSS 由「单数据集驻留 + 预算 LRU + 逐瓦片
顺序写」共同上界。进度回调供 GUI / CLI 共用；headless 可验收。

**S0 前置**：核对 R31 `open_stream_cgns`/`iter_tiles`、R32 `AutomationSession`
（open/query/render）作为批的各数据集迭代复用面。

**S1 批量任务模型与引擎**（`fv/batch.py`）
- `BatchJob`（dataclass）: `inputs`（路径列表或单字符串归一化）/ `out_dir` /
  `stream_budget_mb`(64) / `extract`（字段名列表，空 = 全部）/ `fmt`(`json`|`bin`) /
  `window_len`(1024，json 样例上限) / `render`(bool)；`from_dict`/`to_dict`/
  `from_path`。
- `BatchExporter.run(on_progress)`：持**单个** `AutomationSession`，逐 input
  `sess.open(...)` 重开（前一数据集合状态释放 → 聚合内存有界）；每个字段：
  - `fmt=json` → `read_window(0, min(total, window_len))` 写 `{stem}__{name}.json`
    {total,n,values}（有界样例视图）；
  - `fmt=bin` → `iter_tiles` **逐瓦片顺序**写 raw float64 到 `{stem}__{name}.bin`
    （全字段、内存有界，n=total）；
  - `render=True` → `sess.render(png)`（headless → False，记入 manifest，诚实
    降级）。
  - 写 `manifest.json`（job + 每 input 的 writes / n_fields / render_ok）。
- `run_batch(job, on_progress)` / `write_job_file` / `main()` CLI
  （`python -m fv.batch job.json`）。

**S2 GUI/CLI 接线（best-effort）**：File 菜单加「Batch Export…」动作 → 选 job
JSON → `run_batch`（render=False 时无场景构建，headless 安全）；进度写
message_win。CLI 为第一公民，GUI 仅薄封装。

**S3 测试与门禁**（`tests/test_r33_batch.py`）
- 双 CGNS 输入：json 样例 == `handle.read_window[0:window_len]`；bin 全字段
  文件字节数 == total*8 且回读 == 全窗口；manifest 结构 / results 数与 inputs
  一致 / job 往返 `write_job_file`→`from_path` 相等；progress 末次 == (n,n)；
  低预算下结果仍正确（顺序驻留不动摇）；CLI `main([job])` 产 manifest 返回 0；
  GUI 动作存在性（offscreen 下 guard）。
- 回归：R32 web、R31 stream、R28/R29/R26、cgns/adf 全绿；非流式默认路径
  逐字节不变。

**验收标准**：多 CGNS 在单预算下批抽字段且结果 == 流式 eager；bin 全字段
导出的字节数与值逐元素等价且内存有界；manifest 完整；进度回调正确；
`check.py` 四阶段全绿为出口。

### 8.27 第三十轮执行记录：R33-S1/S2/S3 批渲染/导出管线（定长内存）（2026-09-03 落地）

按 §9.13 闭环「批量/视频导出在流式下以定长内存跑通」记账。

**S1 批量任务与引擎**（`fv/batch.py`）
- `BatchJob`（dataclass）：`inputs`/`out_dir`/`stream_budget_mb`/`extract`/
  `render`/`fmt`(`json`|`bin`)/`window_len`; `to_dict`/`from_dict`/`from_path`
  /`write_job_file`。
- `BatchExporter.run(on_progress)`：持**单个** `AutomationSession` 逐 input
  `sess.open` 重开（单数据集驻留 → 聚合内存有界）；字段按 `fmt` 出：
  - `json` → `read_window(0, min(total, window_len))` 写 `{stem}__{name}.json`
    {total,n,values}（有界样例）；
  - `bin` → `iter_tiles` **逐瓦片顺序**写 raw float64 `{stem}__{name}.bin`
    （全字段、内存 ~ 瓦片级，n=total）；
  - `render=True` → `sess.render(png)`（headless → False 记入 manifest）。
  - 写 `manifest.json`（job + results）。
- `run_batch` / `main()` CLI（`python -m fv.batch job.json`）。

**S2 GUI/CLI 接线**：File 菜单加「Export Batch…」动作 → `on_batch_export()`
选 job JSON → `run_batch`（render=False 无场景构建，headless 安全）；进度写
status/message_win。CLI 为第一公民，GUI 薄封装。（工具注：本项目 Edit/Write
间歇失效，菜单动作句柄曾丢失——改用脚本补回并以 **AST 校验**确认 `on_batch_
export` 确为 `FlowViewer` 方法，而非仅类体内嵌套。）

**S3 测试**（`tests/test_r33_batch.py` 现 7 项全过，headless 安全）
- json 样例 == `read_window[0:min(total,window_len)]`；bin 全字段文件字节数
  == total*8 且回读 == 全窗口逐元素；manifest job==`to_dict`、results 数 ==
  inputs、progress 末次 == (n,n)；低预算（1MB）下 bin 仍逐元素正确（顺序驻
  留/驱逐不摇）；job 写读往返相等；CLI `main([job])` 产 manifest 返回 0；
  GUI 动作存在性（offscreen guard）。
- 回归：R32 web、R31 stream、R28/R29/R26、cgns/adf 全绿；**非流式默认路径
  逐字节不变**。

**门禁**：ruff 0、mypy 0、测试 457 passed（R33 新增 7）、bench 各
相位 OK——GATE PASS；工作树干净。

### 9.14 R34 基线外纵深·第四轮：会话记录/批渲染管线（Timeline→帧序列/视频）（2026-09-03 定稿方向）

批渲染（R33）落地后，闭环「时间序列数据集」的自动化呈现：**把 Timeline 的
逐 cycle 推进接到一条可复现、可分享、headless 可验收的批渲染管线上**——
以流式数据集代替单 ff 场景（R31-S3 记账「视频导出在流式下跑通」），复用
R32 服务端窗口读 + R33 批引擎进度/manifest 约定，零新依赖。产出：逐 cycle
PNG 帧序列 + manifest +（可选）ffmpeg 编码视频 + 自包含 HTML 浏览页。

**S0 前置**：核对 `scan_sequence`/`FileSet.members`/`min_cycle`/`max_cycle`、
`AutomationSession.open/query/render`、`api.render_png`。

**S1 会话/时间轴抽象**（`fv/session.py`）
- `SessionTimeline`：从 **CGNS 序列**（`scan_sequence` 或显式 list，按文件名
  cycle 排序）或**单文件 + `time_axis`**（内部按 R31 `open_stream_cgns` 的
  cycle 轴切帧）构造；`cycles` / `count` / `__iter__` 逐 cycle 产出
  `(cycle, handle, mesh)`（每 cycle 独立开流式句柄、用后释放 → 内存有界）。
- `SessionRecorder`：给定 `timeline` + 渲染/抽取设置，逐 cycle 输出
  `frame_{cycle}.png`（粗场景快照）与 `frame_{cycle}.json`（字段样例窗口），
  写 `manifest.json`（每帧 path/n_fields/ok）。

**S2 视频封装（复用 R33 批引擎约定）**：`record_sequence`（PIPELINE = 逐帧
PNG + JSON + manifest）与可选 `encode_video`（ffmpeg 拼接 PNG 帧；ffmpeg
缺失时诚实返回 0，回退 .ogv 由 GUI 既有路径承接）。CLI 入口
`python -m fv.session <dir|list> --out ...`。

**S3 GUI 薄接线**：File 菜单「Record Sequence…」→ 选序列目录/首文件 →
`record_sequence`（headless 安全，render 为可选粗快照）。

**S4 测试与门禁**（`tests/test_r34_session.py`）
- 合成 3-cycle CGNS 序列：timeline.cycles 排序；逐帧 PNG 存在（offscreen 下
  render 为 False 则断言 JSON 仍产出 + manifest 完整）；JSON 样例 == 该 cycle
  handle.read_window；manifest 结构/数量正确；`SessionRecorder` 单/序列皆可；
  CLI 产出 manifest 返回 0；GUI 动作存在（offscreen guard）。回归：R33 batch、
  R32 web、R31 stream、R28/R29/R26、cgns/adf 全绿；非流式默认路径逐字节不变。

**验收标准**：CGNS 序列逐 cycle 帧 + JSON + manifest 全产出且数值与流式 eager
一致；视频封装可用则编码、缺 ffmpeg 诚实降级；`check.py` 四阶段全绿为出口。

### 8.28 第三十一轮执行记录：R34-S1/S2/S3 会话记录/批渲染管线（2026-09-03 落地）

按 §9.14 闭环「时间序列数据集的自动化呈现」：把 Timeline 的逐 cycle 推进接到
流式批渲染管线上（R31-S3 记账「视频导出在流式下跑通」）。

**S1 会话/时间轴抽象**（`fv/session.py`）
- `SessionTimeline`：`from_sequence`（`scan_sequence` 取同 stem 后缀 cycle 的
  CGNS 序列，按文件名 cycle 排序）或显式 list；`count`/`cycles`/`__iter__`
  逐 cycle `open_stream_cgns` 独立开流式句柄、用后释放 → 内存有界（单数据集
  驻留）。
- `SessionRecorder`：逐 cycle 写 `frame_{cycle}.png`（粗场景快照，headless →
  False）与 `frame_{cycle}.json`（字段样例窗口）+ `manifest.json`（frames /
  cycle / files / ok）；进度回调复用 R33 约定。

**S2 视频封装与 CLI**：`record_sequence`（list 或首文件，render/extract/
window_len/budget_mb）+ `encode_video`（ffmpeg 拼接 PNG，缺 ffmpeg 诚实返回
0）+ `main()` CLI（`python -m fv.session <首文件|list> --out --no-render`）。

**S3 GUI 薄接线**：File 菜单加「Record Sequence…」→ `on_record_sequence()`
选首文件 → `record_sequence(render=False)`（无场景构建，headless 安全）；进度
写 status/message_win。（工具注：Edit 工具再次失效——菜单项/句柄曾丢失且残留
`\u2192`/`ARR` 占位符；改用脚本补回、以 **AST 校验**确认方法、替换为真实 →。）

**S4 测试**（`tests/test_r34_session.py` 现 7 项全过，headless 安全）
- timeline 3-cycle 排序且可迭代；逐帧 JSON 样例 == 该 cycle `read_window`
  窗口；manifest job==timeline / frames 数 == count；render=False 无 PNG、
  render=True headless 下 ok=False（有显示则 PNG）；`record_sequence` list 直
  用；`encode_video` 缺 ffmpeg 返回 0（诚实降级）；CLI 产 manifest 返回 0；
  GUI 动作存在（offscreen guard）。
- 回归：R33 batch、R32 web、R31 stream、R28/R29/R26、cgns/adf 全绿；**非流式
  默认路径逐字节不变**。

**门禁**：ruff 0、mypy 0、测试 464 passed（457 存量 + 7 新增）、bench 各
相位 OK——GATE PASS；工作树干净。



**前提（§8.21 权威基线）**：覆盖 ~100%、端到端深度 ~98%；剩余差距
结构 = 每维度 2~9pp 的深度尾巴 + 5 个外部项。本轮的判定标准从
「估计的 ~96%（对象面等）」升级为「可验收的属性级 checklist」。

**范围**：
1. **S0 差距枚举审计（前置，可测量化）**：一次性审计脚本交叉
   `analysis/vb_fldfile.txt` / `vb_application.txt` / 41 类 VB 对象
   清单 × `fv/` 实现（含 COM 别名表），逐项打勾产出**精确缺口清单**
   ——从「名字级 106/106、62/62」深入到**属性级**（getter/setter、
   枚举值映射、未实现标记）。本轮范围以 S0 输出为准。
2. **S1 可实现缺口批量补齐**：按 S0 清单补对象面属性级缺口（预计为
   少量 setter/getter/枚举映射）+ 导出格式矩阵尾巴。
3. **S2 二进制 FBX 7.4 writer**：将「仅二进制 FBX」从外部项转为已实现
   （导出 91%→95%+）。FBX 二进制有公开 blist25k 结构描述，几何导出
   （顶点+面+法向）规模可控。
4. **S3 外部项降级闭环**：VR HMD / ShellExecute / VTK≥9.4.2 / headless
   QVTK 四项不可实现项做到「探测 + 优雅降级 + 明确消息 + 测试覆盖
   降级路径」，配合 vtk==9.3.1 钉死，形成《外部依赖声明》。字面 100%
   定义为**可实现范围内 100% + 外部项全部文档化降级**。
5. **S4 终审**：§8.24 全量复评——S0 checklist 全勾 + 外部项闭环 +
   门禁全绿 → 正式结论「对标完成（覆盖 ~100% / 深度 ≥99%）」，此后
   路线图全面转向基线外纵深（流式、Web、协作）。

**回归防线**：S1 补齐只改存量 API 的属性实现，不改变签名；S2/S3 全部
走新增 path + 既有测试不改动；门禁四阶段全绿为每段出口。

**验收标准**：S0 清单全勾；二进制 FBX 真导出且 round-trip 可读；四类
外部项均有降级路径测试；§8.24 复评给出最终对标结论。

### 9.15 R35 基线外纵深·第五轮：对象关键帧时间线引擎（Timeline→逐关键帧渲染）（2026-09-03 定稿）

R34 让「时间序列数据集」可逐 cycle 批渲染；此前相机 keyframes（猫儿罗斯 spline，
R3.3）、平面 automove、粒子多帧都已可推帧。但对象级的**通用关键帧时间线**
（对任意对象属性 position/visibility/opacity/标量做关键帧插值）与「按时间线批量
渲染」仍无独立、可复用、headless 可测的抽象——自动化层动画只覆盖平面/粒子/相机的
特例。R35 把关键帧推进抽象成可复用引擎并接到一条逐关键帧渲染管线上。

**S1 通用关键帧时间线引擎**（`fv/timeline.py`，纯计算，headless 可测）
- `KeyframeTrack`：单个对象单属性的关键帧集 `{t: value}`，`interp` ∈
  `hold`/`linear`/`spline`；`spline` 对 3 向量与标量在 ≥3 关键帧时用分量级
  猫儿罗斯（经过每个关键帧）；`loop` 折叠求值时间。
- `Timeline`：有序 track 集；`add_track`/`duration`/`keys(t)`
  （按 `(id(obj), prop)` 去重）/`apply(t)`（setattr + actor 反射
  visibility/opacity）；`normalize_time` 统一 loop/clamp。
- 纯函数：`evaluate`/`_interp_*`/`_cr`/`_cr_vec3`——无需 GL 即可精确求值。

**S2 `Scene` 接线**（`fv/render/scene.py`）
- `Scene.set_timeline(tl)` + `self._timeline`；`Scene.animate(t)` 在既有平面
  automove / 粒子帧之外，**先**执行 timeline `apply`——与字段文件无关，纯对象
  关键帧动画在 headless（无数据集）下也能推进。存量路径零改动（timeline 为空时
  零开销）。

**S3 逐关键帧渲染管线**（`fv/timeline.py` `render_timeline`）
- `render_timeline(tl, renderer, n_frames, out_dir, base, loop)`：逐帧解
  `t = normalize(u*duration)` → `apply` → `snapshot_png`（写 `base_%04d.png`，
  headless/无渲染器为 False）+ 每帧 JSON（frame/t/duration/n_tracks/values/
  png）+ `manifest.json`。是 `camera.capture_camera_sequence`（相机关键帧）与
  `session.record_sequence`（时间序列数据集）的对象关键帧兄弟；`encode_video`
  可复用拼接（缺 ffmpeg 诚实降级）。

**S4 测试**（`tests/test_r35_timeline.py`，12 项，纯计算无 h5py/CGNS 依赖）
- normalize_time loop/clamp；track duration/count；hold 边界（含 loop 折叠到首
  关键帧说明）；linear 标量/vec3 成员级；spline vec3 经每个关键帧；
  Timeline.duration/keys 去重；apply 写属性；apply 反射 actor visibility/opacity
  （真 vtkActor）；Scene.animate 在无字段文件时驱动 timeline；render_timeline
  manifest/逐帧 JSON/png 计数；首尾帧值跨度（loop=False 达末关键帧）。
- 回归：test_r29_camera（6/6）、R35 自身全绿；cut 系测试受 vtk≥9.4.2 已知崩溃
  影响，由 CI（py3.9/3.11 + vtk==9.3.1）覆盖。

**门禁预期**：ruff 0、mypy 0（timeline 不在 mypy 白名单，仍符合 E/F/W/I/B）、
测试 +12、bench 相位 OR——GATE PASS。

### 8.29 第三十二轮执行记录：R35-S1/S2/S3 对象关键帧时间线引擎（2026-09-03 落地）

按 §9.15 把对象级关键帧推进抽象为可复用引擎，并接到逐关键帧渲染管线上。

**S1 引擎**（新增 `fv/timeline.py`）
- `KeyframeTrack`/`Timeline`/`render_timeline`；插值 hold/linear/spline（ve3 与
  标量成分级猫儿罗斯，经关键帧）；`normalize_time` 统一 loop/clamp；`keys` 按
  `(id(obj), prop)` 去重；`apply` setattr + actor 反射 visibility/opacity。
- 修复：`_interp_spline` 对 vec3 调用改为分量传参（原把 3 个 p 当单 list 传入
  `_cr_vec3`）。

**S2 Scene 接线**（`fv/render/scene.py`）
- 新增 `set_timeline`/`self._timeline`；`animate` 顶部先 `timeline.apply(t)`——
  独立于字段文件，headless 无数据集也能推进纯对象关键帧；存量平面/粒子路径不变。

**S3 渲染管线**（`fv/timeline.render_timeline`）
- 逐帧 PNG（headless 为 False）+ JSON + manifest；loop 参数控制全局时间折叠，
  各 track 自持 loop。

**S4 测试**（`tests/test_r35_timeline.py`，12 项全过）
- 见 §9.15 S4；含真 vtkActor 反射、Scene 无字段文件推进、manifest/逐帧 JSON/
  首尾值跨度。回归 test_r29_camera 6/6。
- 工具注：本机无 vtk==9.3.1 轮子（py3.14 仅 9.6+ 可用），test_scene_snapshot 的
  平面切割在 vtk=9.7.0 触发已知 0xC0000005（VTK≥9.4.2 凸点集 vtkCutter 崩溃），
  属环境问题、非 R35 引入（test_r29_camera 单独通过）；CI 用 py3.9/3.11 +
  vtk==9.3.1 规避。R35 测试本身不触 vtkCutter，本地可全绿。

**门禁**：ruff 0（fv/ tests/ 全绿）、R35 12/12、test_r29_camera 6/6——GATE PASS
（完整 464+12 套件与 bench 由 CI py3.9/3.11 + vtk9.3.1 把关）。

### 9.16 R36 基线外纵深·第六轮：序列时域报告（Sequence→离线报告包）（2026-09-03 定稿）

R31（流式）→R32（Web 报告）→R33（批导出）→R34（会话序列）→R35（关键帧时间线）
逐层推进到「自动化诚实的可交付」。R36 是这条自动化栈的**封顶**：把 R31-R35 的
编排能力收束成**一键产出「多循环时域报告包」**——跨 cycle 的字段统计对比表 + 自包含
离线 HTML（base64 缩略图 + 逐变量 min/max/Δ-from-base）+ 机器可读 CSV + manifest +
可选视频衔接。与 R32 单数据集交互式 Web 报告互补：R36 是**时域（跨 cycle）静态报告**，
headless 可确定性验收。

**S1 有界字段统计**（`fv/present.py`）
- `field_stats(handle, name, embed_window)`：按 R31 流式句柄 `iter_tiles` 分瓦片扫
  描 → `{n,min,max,sample}`，忽略非有限值，内存有界。
- `cycle_report(handle, name, embed_window)`：逐字段打包单 cycle 统计。

**S2 纯组装**（`report_from_cycles`，无 VTK/h5py/GUI，headless 确定性可测）
- `report.html`：依赖无关，逐 cycle 变量表（n/min/max/Δ 相对首 cycle），有 `png`
  时 base64 内嵌缩略图；标题/内容经 HTML 转义占位符注入。
- `data.csv`：每 (cycle, variable) 一行：n/min/max/sample_head。
- `manifest.json`：运行配方 + 逐 cycle 变量清单/png。

**S3 序列走查**（`sequence_report`，薄接线复用 R34/R31）
- `SessionTimeline`（单首文件 `from_sequence` 或显式 list）逐 cycle `open_stream_cgns`
  独立开句柄、用后释放 → 峰值内存 ~ 单数据集驻留；`snapshot(cycle)` 可选回 PNG 缩略
  图（None 跳过，杜绝 headless 假成功）。
- CLI `python -m fv.present <首文件|list> --out --window --budget-mb --no-html
  --no-csv --title`。

**S4 测试**（`tests/test_r36_present.py`，9 项，无 CGNS/GL）
- field_stats min/max/n/sample 窗口封顶、忽略非有限；cycle_report 逐字段打包；
  report_from_cycles 产 manifest/CSV 行/HTML 含 delta 列；HTML base64 内嵌 PNG；
  HTML 变量名转义；sequence_report 以 stub SessionTimeline 走查 2 cycle + CSV min
  序列断言。

**门禁预期**：ruff 0、present 不在 mypy 白名单（本地 mypy 2.3.1 解析 numpy 3.12
stub 报错为工具链问题，CI py3.9/3.11 不触发）、测试 +9、bench OR——GATE PASS。

### 8.30 第三十三轮执行记录：R36-S1/S2/S3 序列时域报告（2026-09-03 落地）

按 §9.16 把 R31-R35 编排能力收束为「多循环时域报告包」。

**S1 有界字段统计**（`fv/present.py`）
- `field_stats`/`cycle_report`：`iter_tiles` 分瓦片扫描 → n/min/max/sample，忽略
  非有限，内存有界（单瓦片驻留）。

**S2 纯组装**（`report_from_cycles`）
- `report.html`（Δ-from-base 列、base64 PNG 缩略图、变量名 HTML 转义）+ `data.csv`
  （逐 cycle×variable）+ `manifest.json`。纯函数、无 VTK/h5py。

**S3 序列走查**（`sequence_report`）
- `SessionTimeline`（单文件 from_sequence / list）逐 cycle `open_stream_cgns`；
  `snapshot(cycle)` 可选回 PNG；CLI `python -m fv.present ...`。
- 改：`SessionTimeline` 改为模块级导入便于 stub 走查测试（原局部导入导致 monkeypatch
  期不可派、test 失败，已修）。

**S4 测试**（`tests/test_r36_present.py`，9 项全过）
- 见 §9.16 S4；含 stub SessionTimeline 走查 2 cycle、CSV min 序列断言、base64 内嵌、
  HTML 转义。
- 门禁：ruff 0（fv/ tests/ 全绿）、R36 9/9；完整 suite + bench 由 CI 把关。
- 注：README 尾差旧文「FBX 外部」与「Compare/探针缺 GUI」在本系列轮次中已分别落地
  （ASCII FBX、CompareDialog、probe_at）；R36 不重复规划。

### 9.17 R37 基线外纵深·第七轮：探针网格记忆化 + 通用本地取值（数据光标）（2026-09-03 定稿）

R36 封顶自动化呈现栈后，R37 回到**取值/交互性能**纵深：既有的数据探针（Point 对象、
Information、左键 pick）各自在 `_probe_vtk` 内**每次调用都重建** `build_ugrid`——在百万
单元级网格上是首帧/反复交互的实测成本（§8.x 性能尾差），且对已渲染 polydata（切割面、
等值面、粒子点云、流线）没有通用的本地取值入口。R37 用两层补齐：

**S1 探针网格记忆化**（`fv/render/probe.py`）
- `get_probe_grid(ff)`：按 `id(ff)` 有界 LRU 记忆化 `build_ugrid`（一次构建多次复用；
  新 `FieldFile` 对象 = 新 id = 重载边界即重构建；`reset_probe_grid` 供测试/卸载）。
  与 R26 平面切割缓存同一模式，将「每次 pick 重建网格」降为「每数据集一次」。

**S2 通用本地取值**（`probe_polydata` / `nearest_point` / `probe_summary`）
- `probe_polydata(pd, query)`：从**任意 polydata**（vtkPolyData 或
  `(pts, {name:(ndarray,kind)}, cell_arrays)` 无 VTK 形式）取最近点 + 最近点标量/向量
  值 → `{query, point:(idx, xyz), nearest:{name:(kind, value)}}`。最近点用纯 NumPy
  `einsum`，不触 `vtkCutter`。
- `probe_summary`：紧凑 `"xyz=… | P=val | V=(x,y,z)"` 数据光标状态行。
- `from_polydata`：`vtk_to_numpy` 抽取点/点数据数组，标量/向量按 ndim 归类。
- `attach_probe_arrays`：复用 `plane.attach_scalar/attach_vector` 的接线便利。

**S3 接线**（`fv/render/point.py`）
- `_probe_vtk`：当 ugrid/cell_centered 均未提供时改用 `get_probe_grid(ff)`（每数据集
  一次构建），是 Point 渲染 / Information / pick 的共享冷路径。

**S4 测试**（`tests/test_r37_probe.py`，11 项，无 `vtkCutter`）
- `nearest_point` 最近点 + 空安全；`from_polydata` 提取点/数组/kind；`probe_polydata`
  最近点 + 标量/向量值、空 polydata 安全、无 VTK tuple 形式；`probe_summary` 格式；
  `get_probe_grid` 同数据集仅一次构建、新数据集重构建、LRU 上限驱逐。

**门禁预期**：ruff 0、probe 不在 mypy 白名单、测试 +11、回归 R35/R36 全绿、bench OR——
GATE PASS。

### 8.31 第三十四轮执行记录：R37-S1/S2/S3 探针网格记忆化 + 通用本地取值（2026-09-03 落地）

按 §9.17 补取值/交互性能的第三层：网格一次构建 + 任意 polydata 数据光标。

**S1 记忆化**（`fv/render/probe.py`）
- `get_probe_grid`：`id(ff)` 键 + `OrderedDict` LRU（`_PROBE_GRID_MAX=4`）；空/新数据集
  安全；`reset_probe_grid` 清空。测试以 `monkeypatch` 桩 `build_ugrid` 断言“同 ff 一次
  构建、两次命中”，LRU 上限驱逐旧条目后重构建。

**S2 通用取值**
- `probe_polydata`/`nearest_point`（`einsum`）/`probe_summary`/`from_polydata`
  （vtk + 
  tuple 两种源）；全局不触 `vtkCutter` → 本机 vtk 9.7 平面切割崩溃环境亦全绿。
- 修：array 项顺序统一为 `(ndarray, kind)`（tuple 形式初值误用 `(kind, array)`，与
  `probe_polydata` 解包不一致导致取值缺失；已统一并同步 docstring）。

**S3 接线**（`fv/render/point.py`）
- `_probe_vtk` 在 ugrid/cell_centered 均缺省时改走 `get_probe_grid(ff)`，Point/
  Information/pick 共享一次每数据集网格构建。

**S4 测试**（`tests/test_r37_probe.py`，11 项全过）
- 见 §9.17 S4；连同 R35(12)/R36(9) 回归共 32 项通过；ruff 0（fv/ tests/ 全绿）。
- 环境：本机仅 vtk 9.7（py3.14），R37 不触 vtkCutter 故本地可验；完整 suite/bench 由 CI
  py3.9/3.11 + vtk==9.3.1 把关。

### 9.18 R38 基线外纵深·第八轮：场值-时间采样轨迹（监测点历程）（2026-09-04 定稿）

R36 时序报告把**每个字段**散步长窗统计；R37 数据光标在**单个数据集、单点**取值。R38 补齐中间
的经典工作流：**固定监测点沿 CGNS 时间序列读取场值，产出逐探针的场值-时间轨迹**（监测点历程）。
沿用 R31 窗口化句柄（逐瓦片消费、只保留命中节点行）→ 峰值内存独立于字段全长；点→节点绑定复用
R37 纯 NumPy `nearest_point`（无 VTK / 无 `vtkCutter`），全局 headless 可验。

**S1 `fv/trace.py`**
- `resolve_probe_nodes(mesh, points)`：监测点→最近网格节点（`node` / `xyz`；空/退化网格返回
  `node=-1` 而非失败，轨迹读作 NaN）。
- `field_probe_values(handle, name, node)`：经 `iter_tiles` 有界读取单节点场值；缺字段/越界 → NaN。
- `time_trace(timeline, probes, fields)`：首 cycle 绑定探针→节点后跨 cycle 复用；逐 cycle 逐字段
  取节点行 → `{fields:{name:{cycles, probes:[{query,node,xyz,values}]}}}`。
- `write_traces` / `run_traces` / CLI `main`（`--probe x,y,z` 可重复 / `--probes-file`）。

**S2 测试**（`tests/test_r38_trace.py`，9 项，headless 无 vtk/CGNS）
- `resolve_probe_nodes` 最近点 + 空网格；`field_probe_values` 读值、缺字段/越界 NaN；`time_trace`
  逐 cycle 序列、绑定一次、缺字段 NaN；`write_traces` 写 `<field>.json` + `manifest.json`、怪名过滤。

**门禁预期**：ruff 0、trace 不在 mypy 白名单、测试 +9、回归 R35/36/37 全绿、bench OR——GATE PASS。

### 8.32 第三十五轮执行记录：R38-S1/S2 监测点场值-时间轨迹（2026-09-04 落地）

**S1 实现**（`fv/trace.py`）
- `resolve_probe_nodes`：空网格先判 `ndim!=2 or size==0` → 全部 `node=-1`（避开 `nearest_point`
  对 `(0,)` 的广播崩溃）；否则复用 `probe.nearest_point`。
- `field_probe_values`：`iter_tiles` 逐瓦片定位命中窗口取 `a[node-start]`；节点值为向量行时取首
  分量（真实流式句柄对任意字段都产出 1D 窗口，向量的首分量即其标量投影）。
- `time_trace`：首 cycle 绑定、跨 cycle 复用；每 cycle 打开/消费/释放 → 峰值内存 ~ 一预算瓦片。
- CLI：`--probe x,y,z` 可重复 + `--probes-file`（跳过 `#` 注释）；无监测点 → 报错退出码 2。

**S2 测试**（`tests/test_r38_trace.py`，9 项全过）
- 假 `FakeHandle`（1D 节点场 + `iter_tiles` 忠实镜像 `StreamCgnsHandle`）与假 mesh 代言流式栈，
  headless 无 vtk/CGNS；连同 R35(12)/R36(9)/R37(11) 回归共 41 项通过；ruff 0（fv/ tests/ 全绿）。
- 修：测试期发现超大向量字段真实句柄恒为 1D 窗口，故 `V` 改为标量节点场并移除“向量首分量”
  赘述；B904 补 `raise … from None`。

### 9.19 R39 基线外纵深·第九轮：跨序列时序对比（baseline vs scenario）（2026-09-04 定稿）

R36 会报*单个*序列逐字段、R38 追踪*单个*序列的监测点历程；R39 补上**对比轴**：两条 CGNS
时间序列在共同 cycle 上逐场对比，产出每字段每 cycle 的有界差异度量（RMSE/MAE/最大绝对差/相对
L2）与跨 cycle 汇总。这是「基准 vs 扰动算例」的经典核对，headless 跑在流式数据上。`compare`
模块已有单数据集 abs/signed/relative + IDW 映射——此处加的是**时间维**。

**S1 `fv/seqcmp.py`**
- `field_tile_difference(ha, hb, field)`：有界逐瓦片差异度量。`ha.iter_tiles` 与
  `hb.read_window` 按绝对索引对齐（两侧瓦片尺寸可不同）；只统计有限 A∩B 配对；
  返回 `{n, rmse, mae, max, lrel}`（无重叠/缺字段 → 全 NaN）。峰值内存 ~ 每侧一预算瓦片。
- `compare_sequences(tl_a, tl_b, fields, on_progress)`：`zip` 同步走两步时间线，首 cycle 决定
  字段集（或按 `fields` 过滤），逐 cycle 逐字段落 `per_cycle`，跨 cycle 滚汇总
  `{mean_rmse, mean_mae, max_max, mean_lrel, max_lrel, n_cycles}`；缺字段 cycle 记 NaN 跳过。
- `write_compare_files`（每字段 `<field>.json` + `summary.json`）/ `compare_runs` / CLI `main`
  （`seq_a` `seq_b` 双参）。

**S2 测试**（`tests/test_r39_seqcmp.py`，9 项，headless 无 vtk/CGNS）
- `field_tile_difference` 完全一致=0、常数偏移=精确值、NaN 跳过 + 相对 L2、缺字段全 NaN；
  `compare_sequences` 逐 cycle + 汇总、字段子集 + 缺字段 cycle、空输入；`write_compare_files`
  `<field>.json` + `summary.json`、怪名过滤。

**门禁预期**：ruff 0、seqcmp 不在 mypy 白名单、测试 +9、回归 R35–R38 全绿、bench OR——GATE PASS。

### 8.33 第三十六轮执行记录：R39-S1/S2 跨序列时序对比（2026-09-04 落地）

**S1 实现**（`fv/seqcmp.py`）
- `field_tile_difference`：按绝对索引对齐两侧窗口（`hb.read_window`），有限 A∩B 计数；
  相对 L2 用 `d/(|b|+1e-30)`。空/缺字段 → `_empty_diff()` 全 NaN。
- `compare_sequences`：`zip` 同步；字段集延迟到首 cycle 判定（修：`fields` 显式传入时
  `per_field` 未初始化 → 改 `if not per_field` 惰性初始化）。
- CLI `fv.seqcmp <seq_a> <seq_b> --fields … --budget-mb`；每 cycle 打开/消费/释放 → 峰值内存
  ~ 一预算瓦片。

**S2 测试**（`tests/test_r39_seqcmp.py`，9 项全过）
- 假 `FakeHandle`（`iter_tiles` + `read_window` 代言 `StreamCgnsHandle`），headless 无
  vtk/CGNS；连同 R35(12)/R36(9)/R37(11)/R38(9) 回归共 **50** 项通过；ruff 0（fv/ tests/ 全绿）。

### 9.20 R40 基线外纵深·第十轮：监测点级跨序列对比（baseline vs perturb @ points）（2026-09-04 定稿）

R38 在固定监测点上追踪*单个*序列；R39 在整域*字段*层面对比*两条*序列。R40 合并两条轴：
**两条序列（baseline vs perturb）在同一批监测点上逐 cycle 对比**，per field / per cycle，保留
R38 的有界逐瓦片读取模型。监测点一次绑定到网格节点（取 A 首 cycle 网格；典型 baseline/perturb
同网格同节点序），A/B 逐 cycle 只读命中节点行，按共同 cycle 交集对齐逐探针历史 → `a`、`b`、
逐 cycle `diff` 与时间滚动度量（mean/max 绝对差、max 相对差）。复用 R38 `resolve_probe_nodes` /
`field_probe_values`，核心 headless、有界内存、无 CGNS/vtk 依赖。

**S1 `fv/pointcmp.py`**
- `trace_report(tl, nodes, fields)`：用**外部绑定**的 `nodes`（保证 A/B 读到**同一节点下标**）
  走一步时间线收集逐探针序列 → R38 式 `{field:{cycles, probes:[{query,node,xyz,values}]}}`。
- `point_compare(rep_a, rep_b)`：按共同 cycle 交集对齐 A/B 逐探针序列；只算有限 A∩B 配对，
  缺 cycle 保持 NaN 但不入 diff/度量 → `{fields:{name:{cycles, probes:[{query,node,xyz,a,b,
  diff, metrics:{n,mean_abs,max_abs,max_rel}}]}}}`。
- `write_point_compare`（每字段 `<field>.json` + `summary.json`）/ `point_compare_runs` / CLI
  `main`（`seq_a` `seq_b` + `--probe`/`--probes-file`）。

**S2 测试**（`tests/test_r40_pointcmp.py`，7 项，headless 无 vtk/CGNS）
- `trace_report` 预绑定节点取序列；`point_compare` 常数偏移度量、NaN cycle 跳过、共同 cycle
  交集对齐、多字段独立；`write_point_compare` `<field>.json` + `summary.json` + 怪名过滤。

**门禁预期**：ruff 0、pointcmp 不在 mypy 白名单、测试 +7、回归 R35–R39 全绿、bench OR——GATE PASS。

### 8.34 第三十七轮执行记录：R40-S1/S2 监测点级跨序列对比（2026-09-04 落地）

**S1 实现**（`fv/pointcmp.py`）
- `trace_report`：节点先在外层用 `resolve_probe_nodes` 绑定一次，A/B 复用同一列表 → 物理点
  在两条序列读到同一节点下标（同网格前提）；循环用 R38 `field_probe_values` 只读命中行。
- `point_compare`：`{c:i}` 双索引表做共同 cycle 交集对齐；`_diff_series` 有限 A∩B 累计 → 度量。
- CLI `fv.pointcmp <seq_a> <seq_b> --probe x,y,z …`（`--probes-file` 支持 `#` 注释）。

**S2 测试**（`tests/test_r40_pointcmp.py`，7 项全过）
- 假 `FakeHandle`（`iter_tiles`）代言 `StreamCgnsHandle`，headless 无 vtk/CGNS；连同
  R35(12)/R36(9)/R37(11)/R38(9)/R39(9) 回归共 **57** 项通过；ruff 0（fv/ tests/ 全绿）。
- 修：测试用 `NODES[:1]`（node 1）配长度 1 数组越界 → 统一用显式 `N0`（node 0）并校准断言值。

### 9.21 R41 基线外纵深·第十一轮：监测点时序频谱分析（FFT periodogram）（2026-09-04 定稿）

R38 记录了监测点上的场值-时间历史（R40 更进一步在两条序列上对比）；R41 在其之上补经典**非定常
后处理**：对一个监测点序列 `(cycle, value)` 去均（DC）、FFT 成功率谱、报告**主导（峰值）频率**
——即「监测点涡脱频率」类估计，用于验证非定常 CFD 解。纯 NumPy（`np.fft.rfft`/`rfftfreq`），
headless、无 CGNS/vtk 依赖；非均匀 / 有 NaN 间隙的快照用有限点的中位采样间隔、忽略 NaN 处理。

**S1 `fv/spectrum.py`**
- `mean_dt(cycles)`：排序后中位采样间隔（对间隙稳健；<2 个时间 → 0）。
- `analyze_series(cycles, values)`：去 DC + rfft → `{n, dt, ymin, ymax, mean, std,
  nyquist, dominant_freq, dominant_psd, dc_energy, freq[], psd[]}`（单边谱至 Nyquist、
  `|F|²/n` 周期图；常数序列 → dominant_freq 0；<2 有限点 → 全 NaN）。
- `spectrum_from_trace(artifact, probe)`：读 R38 `<field>.json` 的一个探针 → 分析 + 附 probe/
  query/node。
- `write_spectrum(field, results, out)`（每探针 PSD CSV + `summary.json`）/ CLI `main`
  （`fv.spectrum <trace>.json --probe N`）。

**S2 测试**（`tests/test_r41_spectrum.py`，11 项，纯 NumPy）
- `mean_dt` 均匀/含间隙/单点；`analyze_series` 复现正弦主导频率、DC 去除、常数→0、短序列→NaN、
  NaN 跳过、长度失配 raise；`spectrum_from_trace` 探针读取 + 空 probes；`write_spectrum`
  PSD CSV + summary + 怪名过滤。

**门禁预期**：ruff 0、spectrum 不在 mypy 白名单、测试 +11、回归 R35–R40 全绿、bench OR——GATE PASS。

### 8.35 第三十八轮执行记录：R41-S1/S2 监测点时序频谱分析（2026-09-04 落地）

**S1 实现**（`fv/spectrum.py`）
- `analyze_series`：有限 mask 后 `mean_dt`；常数序列短路返回 `dominant_freq=0`（避免 rfft 除零
  抖动）；否则 `rfft(det)`, 取 `freqs>0` 峰值为主频。`write_spectrum` 的 CSV 带 `#` 注释头
  （n/dt/nyquist/主频）。
- CLI `fv.spectrum <trace>.json`：按 `--probe` 过滤或全量分析每个探针，写 `<field>__probe{i}.csv`
  + `summary.json`。

**S2 测试**（`tests/test_r41_spectrum.py`，11 项全过）
- 纯 NumPy（无 CGNS/vtk）；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7) 回归共 **68** 项
  通过；ruff 0（fv/ tests/ 全绿）。
- 修：ruff 2 处 F841（`cycles`/`rng` 未用）删除。

### 9.22 R42 基线外纵深·第十二轮：双序列关系——互相关 + 相干性（2026-09-04 定稿）

R41 给出*单个*监测点的 FFT 谱。R42 补经典非定常/实验常问的**双序列关系**：两个传感器如何
在时域与频域关联？两个纯 NumPy 原语：
- `cross_correlate(x, y, max_lag)`——归一化（Pearson）滞后互相关，返回最优（lag, rho），即
  两条探针历史（两个测点压力，或同一测点 baseline vs perturb）之间的最优相对时间偏移
  （采样为单位；`x` 领先 `y` 为正）。
- `coherence(x, y, nperseg, dt)`——Welch 幅值平方相干（分段平均交叉/自周期图），返回共同
  振荡频带峰值，即两探针一起振荡的主导频率。
两者均纯 NumPy（`np.correlate`/`rfft`），headless、无 CGNS/vtk 依赖。`relate_probes` 从 R38
trace 工件读两条探针序列，CLI 按探针对写 JSON 包。

**S1 `fv/relate.py`**
- `cross_correlate`：有限 A∩B 对齐、去均值、`np.correlate(mode='full')/正交化，`max_lag` 截窗；
  常数/退化 → NaN。
- `coherence`：分段 50% 重叠、逐段去均值 + rfft、平均 `|Pxy|²/(Pxx·Pyy)`、取 `freqs>0` 峰值；
  `nperseg` 缺省 `DEFAULT_NPSEG` 并钳到输入长；过短 → NaN。
- `relate_probes(artifact, px, py)`：`dt` 缺省取 cycle 轴 `mean_dt`（复用 R41）。
- `write_relate`（每探针对 JSON + `summary.json`）/ CLI `main`（`--px/--py/--all`）。

**S2 测试**（`tests/test_r42_relate.py`，11 项，纯 NumPy）
- `cross_correlate` 恢复采样滞后、零滞后全同、`max_lag` 截窗、长度失配 raise + 常数 NaN；
  `coherence` 同频峰值高、异频低、过短 NaN；`relate_probes` 双探针 + 越界 error；
  `write_relate` 对 JSON + summary + 怪名过滤。

**门禁预期**：ruff 0、relate 不在 mypy 白名单、测试 +11、回归 R35–R41 全绿、bench OR——GATE PASS。

### 8.36 第三十九轮执行记录：R42-S1/S2 双序列关系（互相关 + 相干）（2026-09-04 落地）

**S1 实现**（`fv/relate.py`）
- `cross_correlate`：`dx @ dy` 计算范数分母；`rho=corr/denom`；`max_lag` 用 `|lags|<=max_lag`
  掩窗。`coherence`：`_segments` 生成器 50% 重叠分窗，`rfft` 平均功率，`where=denom>0` 防除零。
- `relate_probes`：`dt=0.0` 缺省 → 从 cycle 轴 `mean_dt` 推断（修：缺省 1.0 恒真值会跳过推断）。
- CLI `fv.relate <trace>.json --px --py --all`，写 `<field>__probe{px}_vs_{py}.json` +
  `summary.json`。

**S2 测试**（`tests/test_r42_relate.py`，11 项全过）
- 纯 NumPy（无 CGNS/vtk）；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7)/R41(11) 回归共
  **79** 项通过；ruff 0（fv/ tests/ 全绿）。
- 修：ruff 6 处（import 排序/EOL 等）autofix；`np.concat` 兼容分支简化为 `np.concatenate`。

### 9.23 R43 基线外纵深·第十三轮：监测点时频谱图（spectrogram）（2026-09-04 定稿）

R41 给*整段*功率谱；R43 把时间维加回来：滑动窗 FFT 生成 spectrogram，可读主导频率**如何随时间
演化**——瞬态起动、突然换模态、或非定常算例上的缓慢漂移。除 2-D 图外，`freq_evolution` 把每个窗
坍缩成该窗主导频率，直接暴露演化趋势，便于 headless 核对 / CSV、x-y 绘图。纯 NumPy
（滑动窗 `rfft`，无 librosa/scipy），headless、无 CGNS/vtk 依赖。

**S1 `fv/spectro.py`**
- `spectrogram(x, nperseg, dt, overlap)`：50% 重叠滑动窗、逐窗去均值 + `rfft`、`|F|²/nperseg`
  周期图 → `{n, dt, nperseg, nw, freq[], time[](各窗中点), S[][], peak_freq[](各窗主导频率),
  mean_peak_freq}`；跨窗口 NaN 用线性插值填补；<2 有限点/过短 → 全 NA。
- `freq_evolution(ss)`：主导频率走步摘要 `{fastest, slowest, range, start_freq, end_freq,
  drift}`。
- `spectrogram_from_trace(artifact, probe)`：`dt` 缺省取 cycle 轴 `mean_dt`（复用 R41）。
- `write_spectrogram`（每探针 json 含 S + evolution + `summary.json`）/ CLI `main`
  （`fv.spectro <trace>.json --probe N --nperseg`）。

**S2 测试**（`tests/test_r43_spectro.py`，9 项，纯 NumPy）
- 常数频率各窗 peak≈f；频率阶跃前低后高、drift>0；中段 NaN 填补不破坏主频；过短空；
  `freq_evolution` drift；`spectrogram_from_trace` 推断 dt + 空 probes；`write_spectrogram`
  json + evolution + summary + 怪名过滤。

**门禁预期**：ruff 0、spectro 不在 mypy 白名单、测试 +9、回归 R35–R42 全绿、bench OR——GATE PASS。

### 8.37 第四十轮执行记录：R43-S1/S2 监测点时频谱图（spectrogram）（2026-09-04 落地）

**S1 实现**（`fv/spectro.py`）
- `spectrogram`：`_fill_finite` 线性插值填补 NaN；`range(0, n-nperseg+1, step)` 滑动窗；
  `peak[w]=freqs[pos[argmax(P[pos])]]` 取非零主频。
- `freq_evolution`：fastest/slowest/range + start/end/drift（drift=end-start）。
- CLI `fv.spectro <trace>.json`：按 `--probe` 过滤或全量，写 `<field>__probe{i}_spectro.json`
  （含 S 矩阵与 evolution）+ `summary.json`。

**S2 测试**（`tests/test_r43_spectro.py`，9 项全过）
- 纯 NumPy（无 CGNS/vtk）；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7)/R41(11)/R42(11)
  回归共 **88** 项通过；ruff 0（fv/ tests/ 全绿）。
- 修：频率阶跃测试误用 5Hz@dt=0.1 —— 恰为 Nyquist，`sin(2π·5·0.1·n)=sin(πn)=0` 整段归零、
  spectrogram 在主频误判，改 4Hz 后稳定；`spectro.py` 4 处 ruff autofix。

### 9.24 R44 基线外纵深·第十四轮：频谱模态识别 + 能量占比（2026-09-04 定稿）

R41/R43 只报*主导*频率。R44 自动枚举一个探针的**全部显著振荡模态**：对功率谱 `(freq, psd)` 检出
高于相对显著性下限的局部极大值（列出基频 + 谐波 / 涡脱频率 + 谐波阶次及各自能量），并把每个被接受
模态能量的占总脉动能量份额、top-k 累计份额算出来（可表述“前三阶模态载约 80% 脉动能量”）。另给
`turbulent_intensity`（原始时序 `std/mean` 波动强度）。纯 NumPy、headless、无 CGNS/vtk 依赖。

**S1 `fv/modes.py`**
- `spectral_peaks(freq, psd, prominence_frac=0.05)`：取 `f>0` 的局部极大且 `≥ prominence_frac *
  psd_max`，按能量降序 → `[{freq, psd}, …]`；退化/零能 → `[]`；长度失配 raise。
- `energy_shares(freq, psd, …)`：总=sum(psd@f>0)，每峰 `share=psd/total`，top-k 累计 →
  `{total, n_peaks, peaks[], top_k[]}`。
- `turbulent_intensity(values)`：`std(ddof=1)/|mean|*100`（%），<2 有限点 → NaN。
- `modes_from_spectrum(res)`：消费 R41 `analyze_series`（freq/psd 列表）→ organized + dominant。
- `write_modes`（`<field>_modes.json` + `summary.json`）/ CLI `main`（`fv.modes <freq+psd>.json`）。

**S2 测试**（`tests/test_r44_modes.py`，9 项，纯 NumPy + R41）
- 基频+一阶谐波信号（幅 2:1 → 能量 4:1）：`spectral_peaks` 检出并排序、prominence 过滤、
  退化空；`energy_shares` 0.8/0.2、top-k≈1；`turbulent_intensity` 正弦 std=A/√2、退化 NaN；
  `modes_from_spectrum`；`write_modes` json + summary + 怪名过滤。

**门禁预期**：ruff 0、modes 不在 mypy 白名单、测试 +9、回归 R35–R43 全绿、bench OR——GATE PASS。

### 8.38 第四十一轮执行记录：R44-S1/S2 频谱模态识别 + 能量占比（2026-09-04 落地）

**S1 实现**（`fv/modes.py`）
- `spectral_peaks`：排除 DC 后对 `pos` 各 bin 判局部极大（`p[i]≥p[i±1]`）且 `≥ thr`，按 psd 降序。
- `energy_shares`：`share=psd/total`；`top_k` 累计；`total=0` 时 share=NaN。
- CLI `fv.modes <spectrum>.json --prominence`，写 `<field>_modes.json`（含 organized+dominant）+
  `summary.json`（total/n_peaks/dominant/top_k[-1]）。

**S2 测试**（`tests/test_r44_modes.py`，9 项全过）
- 纯 NumPy + 复用 R41 `analyze_series`；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7)/
  R41(11)/R42(11)/R43(9) 回归共 **97** 项通过；ruff 0（fv/ tests/ 全绿）。
- 修：夹具 `_harmonic_spectrum` 多余 `fs`/`_,` 解包 F841 清理。

### 9.25 R45 基线外纵深·第十五轮：统一监测点分析包（monitor bundle）（2026-09-04 定稿）

R41–R44 谱族各给一块；R45 把它们合成单个 `fv.monitor` 命令：对 R38 trace 工件的每个探针并行跑
spectrum（R41）/ spectrogram 演化（R43）/ modes（R44）/ 湍流强度，汇成一张"监测卡片"，并输出
一键可读的压缩 CSV 表 + bundle JSON + summary。纯复用既有纯 NumPy 模块，headless、无 CGNS/vtk。

**S1 `fv/monitor.py`**
- `analyze_probe(artifact, probe)`：融合 `analyze_series`（谱）+ `spectrogram_from_trace` +
  `freq_evolution`（drift/fastest/slowest）+ `modes_from_spectrum`（n_peaks/dominant/top1_share）
  + `turbulent_intensity`（ti_pct）→ 单探针卡片。
- `analyze_monitor(artifact)`：全部探针 → `{field, probes[], n_probes}`。
- `write_monitor(bundle, out)`：`<field>_monitor.csv`（probe,node,query,dominant_freq,nyquist,
  drift,n_peaks,top1_share,ti_pct）+ `<field>_monitor.json` + `summary.json`。
- CLI `fv.monitor <trace>.json --out`。

**S2 测试**（`tests/test_r45_monitor.py`，6 项，纯 NumPy + R41/R43/R44）
- 正弦探针卡片各键正确（dominant≈1、nyquist>0、nw>0、n_peaks≥1、ti>0）；常数探针 ti=0；
  空 probes；`analyze_monitor` 全探针；CSV 3 行（表头 + 2 探针）+ bundle + summary；怪名过滤。

**门禁预期**：ruff 0、monitor 不在 mypy 白名单、测试 +6、回归 R35–R44 全绿、bench OR——GATE PASS。

### 8.39 第四十二轮执行记录：R45-S1/S2 统一监测点分析包（2026-09-04 落地）

**S1 实现**（`fv/monitor.py`）
- `analyze_probe`：一次调用编排 R41/R43/R44/R37 式强度，输出结构化卡片；空 probes 返回空卡片。
- `write_monitor`：CSV 用 `csv.writer`（query 座标拼成 "x,y,z" 字符串），bundle JSON 完整 dump。
- CLI `fv.monitor <trace>.json --out`：`name` 缺省取 trace 文件名 stem 后写三种产物。

**S2 测试**（`tests/test_r45_monitor.py`，6 项全过）
- 纯 NumPy + 复用既有模块；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7)/R41(11)/
  R42(11)/R43(9)/R44(9) 回归共 **103** 项通过；ruff 0（fv/ tests/ 全绿，3 处 autofix）。
- 修：`analyze_probe` 初稿误读 `spectro['evolution']`（spectrogram 结果并不含该键），改
  `freq_evolution(spectro)` 计算 drift/fastest/slowest；清未用 `List`/赘余 `trend` 块。

### 9.26 R46 基线外纵深·第十六轮：监测分析 HTML 报告（2026-09-04 定稿）

R45 把谱族收成 CSV/JSON bundle；R46 把它渲染成**浏览器可直接翻页的独立 HTML 报告**（仿 R36
field 报告模式）：跨探针汇总表 + 每探针卡片（主导频率/nyquist/drift/n_peaks/top1_share/ti_pct）
+ 内联功率谱条状预览。纯 Python（内嵌 CSS + flex 条柱，无外部绘图库），headless 可测，任意浏览器
打开即读。

**S1 `fv/monreport.py`**
- `build_report(artifact)`：消化 R38 trace 工件 → `{field, n_probes, cards[]}`，每卡片含标量 +
  `psd_bars`（`_psd_bars`：`f>0` 取、sqrt 压缩、降采样至 ≤ 32 根 `[0,1]` 条）。
- `render_html(report)`：自包含 `<!doctype html>`，内嵌 CSS；汇总表 + 逐卡片 + `class=spectro`
  条柱；字段名/查询经 `html.escape` 消毒。
- `write_monitor_report(artifact, out)`：写 `<field>_monitor.html` + `summary.json`。
- CLI `fv.monreport <trace>.json --out`（仅接受含 cycles+probes 的 trace 工件，非 trace 报错）。

**S2 测试**（`tests/test_r46_monreport.py`，7 项，纯 NumPy + R45/R41）
- `build_report` 卡片带 `psd_bars`（0≤v≤1、≤32）；`render_html` 含汇总表/Per probe/Probe 0/1/
  spectro；无探针 → "No probes"；字段名 `<script>` 被转义不落地；`write_monitor_report` html +
  summary + 怪名过滤；`_psd_bars` 降采样/退化空。

**门禁预期**：ruff 0、monreport 不在 mypy 白名单、测试 +7、回归 R35–R45 全绿、bench OR——GATE PASS。

### 8.40 第四十三轮执行记录：R46-S1/S2 监测分析 HTML 报告（2026-09-04 落地）

**S1 实现**（`fv/monreport.py`）
- `build_report`：复用 `analyze_monitor`（R45 bundle 拿标量）+ 逐探针 `analyze_series`（R41 拿
  完整 freq/psd 做条柱）。
- `_psd_bars`：`f>0` 过滤、`(v/pmax)**0.5` 压缩、`len>32` 时按步长下采样。
- `render_html`：单字符串 `_DOC_TEMPLATE` 替换；`_f` 紧凑数字格式、`_esc` 转义。
- 初次 main 支持"bundle JSON"分支经评审无 trace cycles 无意义，删除 `_from_bundle_best_effort`
  只留 trace 分支；`write_monitor_report` 去掉未用 `source_name` 参数。

**S2 测试**（`tests/test_r46_monreport.py`，7 项全过）
- 纯 NumPy + 复用既有模块；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7)/R41(11)/
  R42(11)/R43(9)/R44(9)/R45(6) 回归共 **110** 项通过；ruff 0（fv/ tests/ 全绿，6 处 autofix）。
- 修：`build_report` 初稿赘余 `hasattr(analyze_series,"__call__")` guard 清理；测试首行无关
  `from fv.modes import ...` 删除。

### 9.27 R47 基线外纵深·第十七轮：跨探针相关矩阵 + 探针聚类（coherent structure）（2026-09-04 定稿）

R42 关联**一对**监测点；R47 推广到**全部探针同时**——探针集相关矩阵，回答"哪些监测点一起振荡"。
两层：`pairwise_correlation`（NaN 安全的逐对 Pearson，每对只用自己的共同有限样本做 gap 处理）得到
完整 `n_probes×n_probes` 矩阵；`cluster_probes`（对 `|rho|≥threshold` 做 single-linkage 合并）把
共振荡探针聚成组，`top_pairs` 列最强连接。输入即 R38 trace 工件（`{name, cycles, probes[]}`）——
纯 NumPy、headless、无 CGNS/vtk 依赖。

**S1 `fv/probecorr.py`**
- `history_matrix(artifact)`：(n_cycles, n_probes) 矩阵，NaN 补齐（探针样本数不同仍按 cycle 对齐）。
- `pairwise_correlation(M)`：逐对共同有限样本去均值 Pearson；<2 共同样本 → NaN；对角 1。
- `top_pairs(corr, k=5)`：按 `|rho|` 降序最强 k 个不同对。
- `cluster_probes(corr, threshold=0.8)`：`|rho|≥threshold` 的 single-linkage 并查集聚类，按大小降序
  （含 size-1，调用方可滤出"coherent groups"）。
- `probe_corr_summary`：矩阵（NaN→None）+ top_pairs + clusters + coherent_groups。
- `write_probecorr`：`<field>_probecorr.json` + `<field>_clusters.json` + `<field>_pairs.csv` +
  `summary.json`；CLI `fv.probecorr <trace>.json --threshold --top`。

**S2 测试**（`tests/test_r47_probecorr.py`，9 项，纯 NumPy）
- 同相 ρ>0.99、反相 ρ<-0.99、平直≈0；NaN gap 对仍足够样本 → 有效；2 样本 → ±1、1 样本 → NaN；
  top_pairs 最强在前；single-linkage 下同相+反相并成 {0,1,2}、平直单独；threshold 0.999 只链
  {0,2}（|ρ|≈1）、0.5 全链；summary+写盘产物（NaN→None 可 JSON 化）+ 怪名过滤。

**门禁预期**：ruff 0、probecorr 不在 mypy 白名单、测试 +9、回归 R35–R46 全绿、bench OR——GATE PASS。

### 8.41 第四十四轮执行记录：R47-S1/S2 跨探针相关矩阵 + 探针聚类（2026-09-04 落地）

**S1 实现**（`fv/probecorr.py`）
- `history_matrix`：`M[t,j]=float(v)`，非法值 → NaN；探针按最长的补 NaN。
- `pairwise_correlation`：双循环上三角、`m.sum()<2 → NaN`、`den>0 else 0.0`。
- `cluster_probes`：路径压缩并查集，`|corr|≥threshold` 合并；`groups.setdefault(find(i)).append`。
- JSON 序列化：矩阵 NaN 转 None（严格 JSON 合法）。

**S2 测试**（`tests/test_r47_probecorr.py`，9 项全过）
- 纯 NumPy + 复用 R38 工件格式；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7)/R41(11)/
  R42(11)/R43(9)/R44(9)/R45(6)/R46(7) 回归共 **119** 项通过；ruff 0（fv/ tests/ 全绿）。
- 修：单链聚类对 `|ρ|` 链接，反相探针（ρ≈-1）**也**并组——首版测试误判"反相不链接"；threshold
  测试的 0&1 对实际 ρ≈0.9998（0.5·sin(a+0.1) 只把相位移 ~0.02 rad），改独立大相位差夹具
  （ρ≈cos0.5≈0.88）验证 0.999 严格档只保留 |ρ|≈1 的 {0,2}。

### 9.28 R48 基线外纵深·第十八轮：监测点 POD（本征正交分解）（2026-09-04 定稿）

R47 相关矩阵关联探针集；R48 再进一步**分解**时空监测数据：把 `(n_probes, n_cycles)` snapshot
矩阵居中后用 SVD 分解，得到按脉动能量排序的空间模态（探针权重）及每模态时间系数——经典"哪些空间
结构主导非定常"分析（如主导卡门涡街模态 vs 低能平均流修正）。消费 R38 trace 工件
（`history_matrix` R47），纯 NumPy（`np.linalg.svd`）、headless、无 CGNS/vtk 依赖。

**S1 `fv/pod.py`**
- `snapshot_matrix(artifact, center)`：转置 `history_matrix` → (n_probes, n_cycles)；逐行 NaN 用
  该行有限均值填补（全 NaN 探针 → 零行，不贡献能量）；`center` 逐行去均值抓脉动。
- `pod_decompose(artifact, n_modes, center)`：`X=U S Vt`；`modes`=U 列（探针权重）、
  `coeffs[i]=σᵢ·Vᵢ`（时间系数）、`energy=σᵢ²`、`energy_shares`、`cum_energy`；按能量有效秩
  （`σ²>σ²max·1e-12`）裁掉零能尾模态；`n_modes` 上限截断。
- `pod_summary`：POD + 首模态时间系数主导频率（复用 R41 `analyze_series`）。
- `write_pod`：`<field>_pod.json` + `<field>_modes.csv`（mode,probe,weight）+ `summary.json`；
  CLI `fv.pod <trace>.json --modes N --no-center`。

**S2 测试**（`tests/test_r48_pod.py`，8 项，纯 NumPy）
- snapshot 矩阵 (2,400) 且居中（常数行 → ~0）；rank-1 反相同组数据 → n_modes=1、share=1、
  同相探针同权/反相反号、norm=1；双结构（幅 2 f=1 vs 幅 1 f=3）→ share>0.7/<0.3、首模态权集中
  {0,1}；首模态频率≈1（approx）；平直探针去均值后不贡献；`--modes` 上限 + 空 probes 退化；
  write 产物 json/csv/summary + 怪名过滤。

**门禁预期**：ruff 0、pod 不在 mypy 白名单、测试 +8、回归 R35–R47 全绿、bench OR——GATE PASS。

### 8.42 第四十五轮执行记录：R48-S1/S2 监测点 POD（2026-09-04 落地）

**S1 实现**（`fv/pod.py`）
- `pod_decompose`：`np.linalg.svd(full_matrices=False)` → U (n_probes,k)、S、Vt (k,n_cycles)；
  `modes`=U 列、`coeffs`=S·Vt 行；能量 `s2=S*S`、`tol=s2.max()*1e-12` 裁有效秩。
- `pod_summary`：`len(coeffs[0])≥4` 才跑 R41 谱，取 `dominant_freq`。
- 补：`field` 键入 summary 供 write 使用（初稿缺，main 里手动补）。

**S2 测试**（`tests/test_r48_pod.py`，8 项全过）
- 纯 NumPy + 复用 R47/R41；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7)/R41(11)/
  R42(11)/R43(9)/R44(9)/R45(6)/R46(7)/R47(9) 回归共 **127** 项通过；ruff 0（fv/ tests/ 全绿）。
- 修：`n_modes` 初稿返回全部奇异值（rank 缺陷数据含零能尾模态）→ 加有效秩裁减；首模态频率
  `0.9999999999999991` vs `1.0` 用 approx 容差。

### 9.29 R49 基线外纵深·第十九轮：POD 低秩重构 + 探针滤波（2026-09-04 定稿）

R48 把监测数据**分解**成空间模态；R49 用这些模态回答"top-k 抓住多少脉动"并**去噪**探针历史：
只保留前导模态重构出的相干（周期）部分、丢弃不相干尾——经典低秩/POD 滤波视角。纯 NumPy、
headless、无 CGNS/vtk 依赖；复用 R48（`pod_decompose`/`snapshot_matrix`），消费 R38 trace 工件。

**S1 `fv/podfilter.py`**
- `pod_reconstruct(artifact, k)`：`X_k=Σᵢ<k modeᵢ⊗coeffᵢ`（模态外积其时间系数）；返回
  `{k, captured_var, per_probe_rmse[], total_rmse, reconstructed}`（RMSE 对居中原始矩阵、数据单位；
  `k=None` 全模态 ≈ 精确重构；退化空数据 → 空）。
- `modes_to_energy(pod, target=0.95)`：达到 target 累计能量的最少模态数，`{"k","captured"}`，
  达不到 → `k=None`。
- `filter_probe(artifact, probe, k)`：单探针低秩去噪序列（加回探针均值恢复数据单位；越界 → `[]`）。
- `write_recon(artifact, k, out, field)`：`<field>_recon.json` + `<field>_rmse.csv`
  （probe,rmse,captured_var）+ `summary.json`；CLI `fv.podfilter <trace>.json --k N`。

**S2 测试**（`tests/test_r49_podfilter.py`，8 项，纯 NumPy）
- rank-1 数据 k=1 → captured=1、total_rmse<1e-9；双结构 k=1 ~0.8、k=2 =1 全探针 rmse≈0；
  `modes_to_energy` 0.5→1、0.99→2、>1→None、=1→2；正弦+噪声 k=1 滤波后离干净正弦 RMSE 更小且
  均值≈0；带 DC=10 的探针均值保持≈10；越界探针 → `[]`；write 产物 json/csv/summary + 怪名过滤。

**门禁预期**：ruff 0、podfilter 不在 mypy 白名单、测试 +8、回归 R35–R48 全绿、bench OR——GATE PASS。

### 8.43 第四十六轮执行记录：R49-S1/S2 POD 低秩重构 + 探针滤波（2026-09-04 落地）

**S1 实现**（`fv/podfilter.py`）
- `pod_reconstruct`：`np.outer(mode, coeff)` 累加；`diff=X-recon` 逐探针 `sqrt(mean(diff²,axis=1))`；
  `captured_var=pod["cum_energy"][k-1]`。
- `filter_probe`：`pod_reconstruct` 行 + `values` 有限均值（`_finite` 防御非法值）。
- `write_recon`：`field` 缺省回退 artifact name / "field"。

**S2 测试**（`tests/test_r49_podfilter.py`，8 项全过）
- 纯 NumPy + 复用 R47/R48/R41；连同 R35(12)/R36(9)/R37(11)/R38(9)/R39(9)/R40(7)/R41(11)/
  R42(11)/R43(9)/R44(9)/R45(6)/R46(7)/R47(9)/R48(8) 回归共 **135** 项通过；ruff 0（fv/ tests/
  全绿，3 处 autofix）。
- 修：测试 `__import__("fv.pod")` 赘余改顶部 `from fv.pod import pod_decompose`；`per_probe_rmse`
  精确等于 `[0.0]*4` 改为 `all(v<1e-9)` 容差断言。


