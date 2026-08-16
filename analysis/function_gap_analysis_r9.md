# flowviewer 功能差距全面分析（2026-08-16，第九轮评估）

> 分析日期：2026-08-16（第八轮 P0→P3 完成后，提交 d48cf5b）
> 对比基准：Cradle CFD 2025.2 scPOST
> （`C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\scPOST_Dx64net.exe`；
> 权威文档 = `analysis/vb_fldfile.txt` FLDFile 125 方法 + `analysis/vb_application.txt`
> Application 62 方法，经日文手册 HTML 独立交叉验证一致）
> 分析对象：fv/ 63 文件、31 种 PostObject、28 个 render 模块、11 个 crdl 解码器、248 测试函数
> 方法：3 个并行子代理（代码现状核查 / API 面逐方法对照 / 渲染+交互深度审计），
> 矛盾点人工核实（如 CameraDialog 是否存在——结论：存在于 object_dialogs2.py:1539，仅工具栏/树未接线）
> 前八轮结论：`function_gap_analysis.md`（第七轮基线）+ DEV_SUMMARY §10（第八轮完成记录）

---

## 1. 当前状态总览

| 维度 | 第八轮后现状 | 证据 |
|---|---|---|
| 对象面 | 30/31 kind Create 菜单可达；STA 反射注册全 kind；30 个属性面板 | main.py:44-79、export.py:76-92 |
| 数据面 | FPH/GPH/FLD/PPH 深；CGNS HDF5 含 MIXED/多zone/结构化；XDMF temporal；iFLD bounds 裁剪 | crdl/ 各解析器 |
| 数据 API | FileSet 插值 + CycleRuntime 全族；POD/ALLCYC 共享缓存 | fileset.py、pod.py |
| 自动化 | COM 52 方法（Application 形态）；api.py 84 函数 | com.py:213-234、api.py |
| 回归 | 246 passed / 1 skipped / 2 deselected（2026-08-16 实测） | DEV_SUMMARY §10.5 |
| 端到端深度估计 | **约 75–80%**（第七轮基线 65–70%） | 本轮综合 |

### 与 scPOST 的差距性质已变化

第八轮后，**"功能缺失型"差距大幅收窄，剩余差距集中三类**：

1. **接线级断裂**（实现存在、入口断开）——修复成本最低；
2. **签名/语义偏差**（方法"已实现"但不兼容 scPOST 调用约定）——VBS 脚本兼容的主要障碍；
3. **专业深度**（真实叶片表面、点探针插值、变量输出文件、视频导出）——决定最后 15–20%。

---

## 2. API 面覆盖率（逐方法对照结论）

| 类 | scPOST 方法数 | 严格对齐 | 部分对齐 | 缺失 | 覆盖率 |
|---|---|---|---|---|---|
| FLDFile | 125 + 2 属性 | ~38 | ~17 | ~70 | **44%**（严格 30%） |
| Application | 62 + 5 属性 | ~8 | ~4 | ~50 | **19%**（严格 13%） |

缺口分布（FLDFile）：MAT/VOL/RGN 互查族 16 缺、ov 参数几何族 ~13 缺、对象管理查询 ~6 缺、导出 5 缺（SaveFBX/SaveCradleViewer/Compare/SaveGLTF/SaveVRML 未封装为方法）。
缺口分布（Application）：窗口/环境族（CreateDrawWnd/Dock 等 8 个，架构不同**维持不做**）、动画帧（AnimationFrame/Second）、状态设置族 ~13、诊断杂项 ~10、**SaveVariableOutput**。

**六处"已实现"方法的重大语义偏差**（VBS 兼容必须修）：

| 方法 | scPOST 语义 | 现实现偏差 |
|---|---|---|
| LocalXYZ2GlobalXYZ | 局部坐标系从 FLD 文件内读，无变换参数 | 要求调用者传 origin/axis/angle（FieldFile 未存局部坐标系） |
| SetCycOpeMode | 数字 0–7（含 Average/SqSum/SqAvg 共 8 模式） | 字符串且仅 5 模式 |
| PrepareMinMaxPos | (mode, loop, show) 三参数 | 0 参数 |
| GetOverlappingRegionCount | 数重叠**区域**数 | 数重叠**单元**数 |
| GetMATIDofVOL | (volid, [out]n) 返回 matid，n=MAT 种数 | 取名称、无 n 输出 |
| GetBoundingBox | (name 必填, [out]6 值) 返回 LONG | name 可选、返回 tuple |

**flowviewer 反超区**（scPOST 没有的能力）：cycle 运行时全族直通 Python、几何查询 api、turbo 后处理、POD、interpolate_at 独立 API、GlobalXYZ2LocalXYZ 逆变换、事件连接点。

### 两个核心"工作流闭环"缺口

| 缺口 | scPOST 对应 | 现状 |
|---|---|---|
| **点探针**：任意 (x,y,z) 定位单元 + 变量插值 | GetVariableInfo(LNAM,x,y,z,[out]ov,elem,mat,...) | `api.variable_info` 名不符实（返回元数据）；Information 对象仅最近节点 |
| **变量输出文件**：对象/探针的 title/coords/scalar/vector 落盘 | Application.SaveVariableOutput(path, items) | 完全缺失——scPOST"算完导出"主通道，flowviewer 只能"算完截图" |

---

## 3. 端到端断点（第八轮遗留 + 本轮新发现）

| # | 断点 | 证据 | 类型 |
|---|---|---|---|
| B1 | Timeline Time/Cycle 模式仍整步 `load_file`，未接 `interpolate_at`（API 已就绪） | main.py:1286-1314，GUI 零调用 interpolate_at | 纯接线 |
| B2 | **GUI 无删除对象入口**（api.remove_object 存在但 gui/ 无调用）；Edit 菜单无 Delete/Copy/Paste | api.py:574-600 vs panes.py 无右键菜单 | 纯接线 |
| B3 | undo 快照仅在 `_create_object` 一处，属性编辑/删除不入栈 | main.py:1268 唯一调用点 | 纯接线 |
| B4 | 工具栏 Camera 按钮 `_nyi` 而 **CameraDialog 已存在**；树双击 4 处 NYI | main.py:490,492,1062-1068 vs object_dialogs2.py:1539 | 纯接线（Unit 对话框需小实现） |
| B5 | COM `FlowviewerApplication` 无头单例，13 个 Set*/Animation 方法仅存 flag 不驱动渲染 | com.py:246-261,676-728 | 中（COM→Scene 桥） |
| B6 | mirror/periodical copy 的 mapper 不继承源对象 scalar/LUT → 副本永远灰色 | mirror.py:58-68、periodical.py:54-64 | 纯接线 |
| B7 | vector 箭头硬编码黑色，不按幅值/变量着色 | vector.py:60 | 纯接线 |
| B8 | 拾取查询值仅 plane 分支，surface/volume/isosurface 点击无响应 | main.py:1466 | 中 |
| B9 | Select 鼠标模式完全 inert | main.py:1382-1383 | 中 |
| B10 | 对象树无右键菜单 | panes.py:142 | 中 |

---

## 4. 渲染/交互/导出深度差距摘要

**渲染**（详见审计，摘影响最大项）：
- turbo PS/SS 按 θ 中位数几何分侧 + B2B 容差取点——非真实叶片表面（turbo.py:295-307、42-43）【大】
- camera view_up 笛卡尔插值非四元数 SLERP——过顶视角跳变（camera.py:43-56）【中】
- colorbar 仅 Rainbow/Gray/Invert 三色表、标签黑色写死 7 个（colorbar.py:49-54,115-122）【中】
- graph 单系列无图例/保存（graph.py:75-85）【中】
- measure 无 3D 标注 actor（measure.py 全文件）【中】
- oilflow 仅 RK2 与 streamline RK4 不一致（oilflow.py:76-80）【接线】
- 硬编码族：information 球半径 0.002（information.py:45）、streamline tube 半径 1e-3（streamline.py:356）、point 标签位置（point.py:185）、粒子球不按矢量缩放（particle.py:176）【接线】

**交互**：Camera preset 缺（object_dialogs2.py:1539-1564 已有 position/focal，缺 7 个 preset 按钮）【接线】；Measure 端点不能点击拾取（object_dialogs2.py:1374-1385）【中】；状态栏仅模式/坐标【接线】。

**导出**：无 AVI/MP4 视频导出（export.py:227-250 仅 PNG 序列）【中】；OBJ 无法线/材质（export.py:253-281）【中】；FBX 无原生 writer【维持 OBJ 替代或 assimp 立项】。

**数据层小缺陷**：varreg `mag()` 恒等（varreg.py:232-233，`mag(表达式)` 会错）；div/rot 硬编码 X/Y/Z 后缀命名（varreg.py:206-216）；FLD face_id 反查返回空/(-1,-1)（topology.py:59-63,133-136）；CGNS ADF / Nastran .op2 / Marc .t16 二进制不支持（范围限制，维持不做或立项）。

---

## 5. 新改进计划（第九轮 R0–R3）

> 设计原则：先接线后实现、先兼容后超越；每梯队完成即全量回归 + 提交推送。

### R0 接线速赢（成本极低、感知极高，一轮完成）

| # | 项 | 方案 | 对应断点 |
|---|---|---|---|
| R0.1 | Timeline Time 模式接 `interpolate_at` | `_on_timeline_step` Time 模式改调 `api.interpolate_at(fs, cycle_id, cache)`，Cycle 模式走 `load_member` 缓存 | B1 |
| R0.2 | 对象删除 + Edit/右键菜单 | 对象树 `customContextMenuRequested` → Delete/Duplicate/Copy/Paste；Edit 菜单补 Delete/Duplicate；接 `api.remove_object` | B2 |
| R0.3 | undo 覆盖属性编辑与删除 | `_on_property_applied` 与删除路径前调 `_snapshot_children` | B3 |
| R0.4 | Camera 入口接线 + Unit 对话框 | 工具栏/树 Camera → 已有 CameraDialog；Unit 对话框最小实现（长度/角度单位映射显示） | B4 |
| R0.5 | mirror/periodical 继承源场 | mapper 加 `SelectColorArray`/`SetScalarRange` + 源对象 colorbar LUT | B6 |
| R0.6 | vector 箭头按幅值/变量着色 | 读 `obj.vector_color`/scalar map，接 LUT | B7 |
| R0.7 | 硬编码参数化 | information 半径/tube 半径按 `ff.bounds` 自适应；point 标签错位排布；粒子球按矢量幅值缩放 | §4 |
| R0.8 | oilflow RK4 + Camera preset + 状态栏增强 | oilflow `SetIntegratorTypeToRungeKutta4()`；CameraDialog 加 Front/Back/Top/Bottom/Left/Right/Iso 按钮；状态栏加拾取值/n_cells | §4 |

### R1 交互深度（scPOST 工作流核心）

| # | 项 | 方案 |
|---|---|---|
| R1.1 | 拾取全对象化 | `_move_object_to_pick`/查询按 kind 分发到 surface/volume/isosurface/streamline/bar（复用 probe 逻辑） |
| R1.2 | Select 框选 + 对象树右键扩展 | RubberBand pick → 批量显隐/删除；右键加 Rename/Lock |
| R1.3 | Measure 3D 标注 + 端点拾取 | 距离/角度画线/弧 + 文本 actor；对话框坐标框支持 Draw Window 点击回填 |
| R1.4 | colorbar 专业化 | 色表扩 Jet/Hot/Cool/Turbo/Parula/Viridis（vtkColorSeries）；标签色/刻度数/格式参数化 |
| R1.5 | graph 多曲线 + 保存 | 多系列/图例/对数轴/savefig |
| R1.6 | Compare 量化 | 并排视图加 |A−B| 差场与 min/max/均值统计 |

### R2 API/COM 兼容（VBS 脚本可移植目标）

| # | 项 | 方案 |
|---|---|---|
| R2.1 | 修六处语义偏差 | SetCycOpeMode 数字 0–7 八模式（兼容字符串入参）；PrepareMinMaxPos(mode,loop,show)；GetOverlappingRegionCount 改数区域；GetMATIDofVOL(volid,[out]n)；GetBoundingBox 保留可选 name + COM 侧按 ByRef 约定包装；LocalXYZ2GlobalXYZ 从 ff.meta 读局部坐标系（FLD 解析层补存） |
| R2.2 | ov 参数几何族（~13 方法） | FieldFile 建 ov 索引（cvol part 序）；GetNodeCount/GetElementCount/GetNodesOfElement/GetFaceCountOfElement/GetNodesOfFace/GetAdjacentElementOfFace/GetAreaOfFace/GetNodeOfs 等薄封装 |
| R2.3 | MAT/VOL/RGN 互查族（~16 方法） | 建 id↔orgname↔emtname 三向映射（FLD/PPH 解析层补 EMT 名表）；GetVOLIDby*/GetMAT*by*/GetRgnName/GetRgnNum 逐一实现 |
| R2.4 | **GetVariableInfo 点探针** | vtkStaticCellLocator（或 scipy cKDTree 回退）定位 (x,y,z) 单元 + 反距离/形函数插值；GUI 侧并入 Information 对象 |
| R2.5 | **SaveVariableOutput** | 定义输出格式（CSV：title/coords/scalar/vector/elem/node 列）；遍历对象探针点/采样点落盘；COM+api 双入口 |
| R2.6 | Application 杂项族 | GetPID/GetTickCount(Ex)/CreateFolder/Get(All/OneOf)FilesForWildCard/GetRandomFilename/ShellExecute/GetEnvFilePath/GetHomeFolder/IsThisPathValid（皆薄封装）；AnimationFrame/Second 接 timeline 帧驱动；SetLogFilename/SetMessageLevel/Open(Close)MessageLogFile；UpdateAll 触发场景重建 |
| R2.7 | COM→GUI 桥 | FlowviewerApplication 可选挂接运行中的 FlowViewer 实例（单例注册表），Set*/Animation/SaveSTA 驱动真实渲染；无 GUI 时维持 flag 降级 |

### R3 专业深度（大项，按需立项）

| # | 项 | 说明 |
|---|---|---|
| R3.1 | Turbo 真实叶片表面 | 用周期对称角区间 + 壁面 BC 面（非 θ 中位数）识别 PS/SS；B2B 由面采样替代体积容差取点 |
| R3.2 | 视频导出 | vtkAVIWriter（VTK 自带）或 ffmpeg 帧序列封装；Animation 对话框加导出选项 |
| R3.3 | Camera 四元数 SLERP | view_up 过顶跳变修复 |
| R3.4 | Text 3D 锚定 + 背景多色渐变 | vtkBillboardTextActor3D；gradation 多控制点 |
| R3.5 | 深格式 | CGNS ADF 读取器、Nastran .op2、Marc .t16（各独立立项，按样例可得性排期） |
| R3.6 | Timeline Sync 多 FileSet | 多序列同步播放 |
| R3.7 | 颜色表编辑器 | 控制点增删/CSV 导入 |

### 维持不做

- COM 窗口管理系统（CreateDrawWnd/Dock/GetDockableWindow/GetDrawWindow）——单窗口架构不同，不模拟；
- CradleViewer 专有格式导出、VR 实机渲染（需自编译 VTK+HMD）、FBX 原生 writer（OBJ 中性格式替代，除非引入 assimp）；
- scConverter/HeatPathView 附属工具。

### 数据层修缮（随 R0–R2 顺带）

- `mag()` 改真取模（矢量参数按分量合成）；div/rot 接受显式三分量参数（`div(UX,UY,UZ)`）；
- FLD face_id 反查：由 cell_conn 生成 hex 面反向索引填充 `face_cells`/face 表（mesh_fld 已有 face_cells 雏形，补 face_nodes）。

---

## 6. 预期收益

| 梯队 | 完成后端到端深度 | API 覆盖率 |
|---|---|---|
| 现状 | 75–80% | FLDFile 44% / Application 19% |
| +R0 | ~82% | — |
| +R1 | ~85% | — |
| +R2 | ~88% | FLDFile ~75% / Application ~55% |
| +R3 | ~90%+ | 视立项而定 |

> R2 完成后即可宣称"常用 VBS 脚本可移植"；R0+R1 一至两轮即可完成；R2 约两轮；R3 按需。
> 执行约定沿用前八轮：逐项提交推送、每梯队末全量回归、DEV_SUMMARY 增量记录。
