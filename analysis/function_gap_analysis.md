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
