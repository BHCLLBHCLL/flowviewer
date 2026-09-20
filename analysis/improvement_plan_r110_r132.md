# flowviewer 改进计划（R110–R132）· 逐轮提交推送版

> 制定日期：2026-09-13 · 依据：`analysis/code_state_review_20260913.md`（本轮全面审计）
> 仓库：`github.com:BHCLLBHCLL/flowviewer.git`（origin/main，SSH）· 当前 HEAD：`192a51b`（R108）
> 编号规则：延续项目既有 R 轮次。**工作区未提交的 plane.py 修复已自称 R109，故新计划从 R110 起。**
> 总体方针：**先修正确性、再建验证、最后补深度**。停止横向加功能，直到阶段 A/B 完成。

---

## 1. 轮次总表

| 轮次 | 主题 | 关键交付 | 提交信息（subject） | 依赖 |
|---|---|---|---|---|
| **R110** ✅ | 测试基线可信化（已推送 56a6351） | conftest 夹具隔离（消除 2.4 GB 残留与顺序依赖假失败）+ R109 遗留收尾（test_r19 期望、README 归因）+ VTK 9.6 迁移风险记录 + 测试产物泄漏修复 + `scripts/round.py` | `R110: trustworthy test baseline (fixture isolation, R109 follow-up, README attribution)` | — |
| **R111** | 错误可见化 | `load_file` 未识别容器抛错；GPH 无场显式报告；越界节点报错；宽泛 except 收敛 | `fix(crdl): fail loudly on unrecognised containers and empty field sets` | R110 |
| **R112** | FLD 几何忠实 | 面表去重（6.3×）+ FLD 表面 0-based 索引 + 表面积分用全顶点（Newell） | `fix(fld): de-duplicate face table and use 0-based surface node ids` | R111 |
| ↳ **R111b** | 测试基线加固（并入 R111） | `test_gui.py` 体渲染路径偶发原生无响应（位置漂移）定位与隔离；全量回归恢复可重复 | 并入 R111 提交 | R111 |
| **R113** | 数值正确性 | 面积/体积/壁距/谱幅值/相干/lag 符号/邻居选择统一修正 | `fix(numeric): Newell areas, owner∪neighbour volumes, wall-surface DST, one-sided PSD` | R112 |
| **R114** ✅ | golden 语料 | `tests/data/golden_*.npz/json` 入仓 + CI 不再静默 skip | `test(data): in-repo golden corpus so numeric tests run in CI` | R113 |
| **R115** ✅ | 解析解金标 | 22 项解析金标 × 三类网格（结构化/FPH/FLD） | `test(numeric): analytic ground-truth suite across structured, FPH and FLD meshes` | R114 |
| **R116** | 门禁与字段矩阵 | 真值断言占比门禁 + 字段消费矩阵测试 | `feat(tools): golden-assertion density gate and field-consumption matrix` | R115 |
| **R117** | scPOST 数值交叉验证 | 同变量双端导出 + 逐点比对（容差 1e-6） | `test(scpost): cross-validate decoded fields against scPOST COM export` | R116 |
| **R118** | 渲染输出正确性 | 体渲染 hex 路径、表面 Trim、粒子 Points、信息探针、glyph 长度 | `fix(render): volume hex path, surface trim, particle points, probe location` | R117 |
| **R119** | 拾取与显隐 | Surface/Particle 注册进拾取表；图层键统一；框选可用 | `fix(gui): register surface/particle actors for picking and unify layer keys` | R118 |
| **R120** | 交互补全 | 拖拽手柄接线；Integrate 页接 integrate_cut；死控件落地或移除 | `feat(gui): wire drag handles and the Integrate tab; retire dead controls` | R119 |
| **R121** | 状态持久化 | 全局对象（相机/灯光/背景）纳入 STA；GUI 增加 Load Status | `fix(sta): persist global objects and add a GUI Load Status path` | R120 |
| **R122** | 动画正确性 | 时间线增量重建 + 保相机；Automove frames=0 冻结修复 | `fix(timeline): incremental frame rebuild, preserved camera, automove freeze` | R121 |
| **R123** | FLD 变量忠实 | 按 `LS_Scalar:*` 命名段取变量；去 ATMS 伪造；UTF-8 区域名；BC 段补全 | `fix(fld): name fields from LS_Scalar sections, drop fabricated ATMS, UTF-8 regions` | R122 |
| **R124** ✅ | CGNS 真机可用（已推送 origin/main；提交哈希见下一轮的记录） | NGON_n/NFACE_n 多面体面表 + 全部 base + GridLocation 过滤 + zone 去重 + ZoneBC 面号归一化 | `R124: open real polyhedral Cradle CGNS exports` | R123 |
| **R125** ✅ | FPH 场可见性 | `FC_Scalar/FC_Vector` 段盘点与如实报告（附实测维度）+ 证明 EC_* 本就单帧 + 加载时写入 meta 与日志 | `R125: report the FPH field sections that are not attached` | R124 |
| **R126** ✅ | 导出诚实化 | 视频编码器由扩展名+能力决定（`.mp4`→ffmpeg，`.avi`→vtkAVIWriter，否则显式拒绝）；不再把 Ogg Theora 写进 `.mp4/.avi`；`snapshot_png` 不再偷偷改名；FBX/CVFF 补入口与测试 | `R126: write the format the filename promises` | R125 |
| **R127** ✅ | 性能 | 节索引缓存改为内容键 + 16 条 LRU（不再持有缓冲区）；索引从 40 遍扫描改为单遍（实测 2.8–5.0×）；`iter_data_blocks` **实测不需要向量化**（0.000–0.001 s/段，profile 里不出现）故不改；额外优化实测热点 `_normalise_face_nodes` 等宽快路径（1.8×，输出逐元素相同）。整文件加载实测：101 MB FLD 5.31→4.27 s、1356 MB FPH 50.64→42.93 s | `R127: stop the section index pinning files, and scan once` | R126 |
| **R128** | 大模型性能 | FLD 流线空间索引；`_cell_centers_fph` 向量化；内存峰值 | `perf(render): spatial index for FLD tracing, vectorised cell centres` | R127 |
| **R129** | 分析栈诚实化 | IDW 改名/标注；POD/DMD/谱接入金标；去误导措辞 | `refactor(analysis): label probe-interpolated fields honestly, add numeric goldens` | R128 |
| **R130** | 缺失格式决策 | `.rph` 立项或移除；binary STL；`.neu` 注册修正 | `feat(crdl): binary STL, correct .neu registry, .rph decision` | R129 |
| **R131** | scPOST 深度补齐 | 交互/对象面剩余缺口（按 R117 交叉验证后重新排序） | `feat(scpost-parity): close remaining interaction and object gaps` | R130 |
| **R132** | 文档与指标 | 删除自评百分比，落地三项可测指标 | `docs: replace self-assessed percentages with the three measurable indicators` | R131 |

---

## 2. 每轮固定流程（Definition of Done）

任何一轮都必须走完下列 7 步，缺一不算完成：

1. **前置核对**：先 `git log --oneline -5` 与 `grep` 源码，确认该缺陷**在当前代码中仍然存在**（本项目的文档历史多次失真，禁止按文档直接开工）。
2. **实现**：改动尽量小且可回滚；同一主题一个轮次，不混入无关改动。
3. **针对性测试**：新增/修改的测试必须包含**独立期望值**（解析解、跨工具金标或字节级比对），不接受"形状/非空/往返"式断言。
4. **回归（分层，时长为本机实测）**：
   - 快层（每轮门禁）：`python scripts/round.py --check` = ruff + mypy + `pytest tests --ignore=tests/test_gui.py` → **实测 351–362 s（5.9–6.0 分钟）**，1034–1036 passed
   - 全层（发布前门禁）：`python -m pytest tests -q` → **实测 1033.9 s（17.2 分钟）**，1302 passed
   - 静态层：ruff + mypy（已含在快层内）
   - **快层其实不"快"**：top-12 慢测试合计 ~105 s（`test_r26_plane` 17.7 s 单测、`test_scpost_samples` 13.7+7.8+7.7 s、`test_r25_export` 10.9+10.7 s、`test_r21` 9.9+9.9 s、`test_pod` 8.4 s）。**R110.5 先建立"测试可重复"基线，测试提速排在 R127 之后（已转出为 R127c）**（把重复的真实文件解析改为 session 级 fixture 共享，预计快层可降到 2 分钟内）。
5. **不许留红**：若某轮改动使既有测试失败，必须同轮修正测试期望并说明原因（如 R109 的 0 点单元语义变更）。
6. **提交**：`R<n>: <一句话主题>` 作 subject（沿用 R17–R108 惯例），正文列证据与回归数字。
7. **推送**：`git push origin main`，并核对 `git status -sb` 显示 `## main...origin/main`（无 ahead/behind）。

### 自动化：`scripts/round.py`

建议新增一个轮次收尾脚本，把第 3–7 步固化，避免手工遗漏：

- `python scripts/round.py --check`：只跑快层回归 + ruff + mypy，报告通过与否。
- `python scripts/round.py --commit "R110: ..." --push`：仅在**快层全绿**时才 `git add -A`、`commit`、`push origin main`，并打印 `git status -sb`。
- 全层回归作为**发布前门禁**（`--full`），每轮末尾或每 3 轮执行一次，因为 17 分钟不适合每轮阻塞。
- 禁止 `--no-verify`；禁止在非 main 分支推送。

> 该脚本本身作为 **R110 的一部分**交付（提交信息里带 `chore(tools):`），此后每轮都用它收尾。

---

## 3. 阶段 A：正确性收敛（R110–R113）— 最高优先，不可跳过

**目标**：把"已宣称可用但实际崩溃/静默错值"的路径全部变为"要么正确、要么明确报错"。

### R110 收尾在途修复
- 确认工作区 `fv/render/plane.py`（VTK_POLYHEDRON + owner∪neighbour）与 `fv/__init__.py`（conda DLL 路径）改动完整；补充空壳/退化单元的显式处理。
- 修正 `tests/test_r19.py::test_fph_grid_handles_degenerate_cells` 的期望（0 点 → 0 面多面体）。
- 更新 README：删除"VTK ≥9.4.2 上游缺陷"的错误归因，改为"非法凸包单元导致 cutter 崩溃；已改为精确多面体面表"。
- 交付 `scripts/round.py`（轮次门禁 + 自动提交推送；已实现并通过 ruff/mypy/--help 冒烟）。
- **R110.5 测试隔离（本轮实测新发现）**：单独运行 `tests/test_r68_presets.py tests/test_r72_report_bundle.py` → **28 passed in 0.52 s**；但在全量/快层运行中二者**均失败**（`test_persists_to_file_and_reloads`、`test_open_report_bundle_roundtrip_extracts_index_and_reports`）。即**存在测试态污染/顺序依赖**（均涉及用户级 preset 存储与 bundle 临时目录）。必须定位并隔离（monkeypatch 用户目录/`tmp_path`），否则本计划的"每轮回归必须绿"无法作为可信门禁。
- **验收**：`tr03_9.fph` 建 Plane 稳定返回 4,685 单元；`python scripts/round.py --check` 与全量 `pytest tests -q` **均 0 failed**；重复运行 3 次结果一致；README 无错误归因。

### R111 错误可见化
- `fv/model/dataset.py:643-719`：`load_file` 在既非注册格式、也未探测到 `LS_Nodes/LS_Links` 时**抛 `ValueError`**（含文件头魔数），不再静默返回空 `FieldFile`。
- GPH/无场文件：返回明确 warning（`meta["no_fields"]`）+ 消息窗口提示"该文件不含场数据"。
- `fv/crdl/mesh_gph.py:862-867` 越界节点 clamp → 抛错（附越界统计）。
- 收敛 `mesh_fld.py:341`、`dataset.py:185-193`、`cgns.py:291-294` 三处高风险吞错：改为记录到 `ff.meta["warnings"]` 并至少 `warnings.warn`。
- **验收**：1.12 GB `.rph` → 立即明确报错（而非 9.8 s 扫描后返回空对象）；新增 4 项负路径测试。

### R112 FLD 几何忠实
- `fv/crdl/mesh_fld.py:411` 的 `faces = seg1 + seg2` → 去重（保持面→cell 映射一致），`ff.faces` 从 34,978 → 5,556。
- `fv/render/surface.py:112-117` 加 0/1-based 归一（与 `topology.py:126` 同一套），实测 used ids 必须包含 0、无越界。
- `fv/render/plane.py:1437-1448` 面积改用**全部顶点**的 Newell 公式（当前只用前 3 个顶点）。
- **验收**：FLD 表面 polydata 节点基正确；表面积分与 VTK 三角化面积比值 ∈ [0.999, 1.001]（FPH 与 FLD 各 1 项金标）。

### R113 数值正确性（一次性对齐）
| 项 | 现状 | 目标 |
|---|---|---|
| 面积/积分 | 只用前 3 顶点；FPH 17.9%、FLD 10.26× | Newell 全顶点；误差 <0.1% |
| FPH `volume_of_element` | 仅 owner 面，中位 0.424× | owner∪neighbour；总和误差 <0.5% |
| DST | 量到顶点，中位 +47.7% | 到**壁面**（vtkImplicitPolyDataDistance 或三角形 cKDTree）；并支持 FLD `bc_plan` |
| 谱幅值 | 差 n/2 倍、非密度 | 单边化 + 1/Δf，Parseval 一致；非均匀采样显式告警 |
| 相干性 | n≤256 恒 1.0 | nseg<2 时拒绝给结论（返回 NaN + 原因） |
| `cross_correlate` lag 符号 | 与 docstring 相反 | 修正符号 + 文档；|lag|>0 时用重叠段归一 |
| delx/dely/delz | 斜交/tet 取任意正向邻居 | 按面法向/最小夹角选真实轴向邻居；不可判定时报错 |
| 单元体积两套定义 | 比值 0.819 | 统一为单一实现，删除重复定义 |
| 表头整数项 | `Dimension` 显示 "1x1" | 显示真实值 |
- **验收**：14 项解析解失败全部转为通过；每项一个金标测试。

---

## 4. 阶段 B：真值验证体系（R114–R117）— 让"对标"可证伪

### R114 golden 语料入仓
- 把真实样例转成小型 golden 资产提交：`tests/data/golden/{fph_small.npz, fld_small.npz, fields.json}`（坐标/连通/变量/区域 + 期望统计量），单文件 <2 MB。
- 调整 `.gitignore`（当前 `tests/*` 全忽略、只放行 `tests/*.py` 与 `tests/data/*`）。
- 把现有靠 `skipif` 跳过用户路径的数值测试改为**读入仓 golden**，使 CI 真正执行。
- **验收**：CI 上数值测试执行数从"几乎全跳过"提升到 ≥30 项。

### R115 解析解金标
22 项金标，**每项必须同时覆盖三类网格**（结构化 hex / 真实 FPH 多面体 / 真实 FLD）：
微分算子、梯度/散度/旋度、涡量/Q/λ₂/螺旋度、切面面积与积分、单元体积与总体积、表面积分、POD 特征值/能量/频率、DMD 频率/增长率、FFT 幅值与 Parseval、互相关 lag、相干性、DST 壁距、IDW 插值权重。
- **验收**：金标测试数 ≥22，且每项含解析或跨工具期望值。

### R116 门禁与字段矩阵
- `scripts/check.py` 增加两个阻断项：
  1. **真值断言占比**：脚本按 AST 统计"含独立期望值断言"的 test 占比，当前 71/1307 = 5.4%，门禁 ≥25%（核心模块 ≥60%）。
  2. **字段消费矩阵**：对 32 kind 逐个断言"每个 UI 可写字段要么被渲染层消费，要么显式标注 reserved"，杜绝 87 个死字段再生。
- **验收**：门禁能在人为删掉一个真值断言时失败。

### R117 scPOST 数值交叉验证（关键轮）
- `tools/scpost_export.vbs`（或 pywin32）：用本机 `C:\Program Files\Cradle\CradleCFD2025.2\Programs_x64\scPOST_Dx64net.exe` 的 COM 接口对同一 `fld/fph` 导出同一变量到 CSV。
- `tests/test_scpost_crosscheck.py`：读入 scPOST CSV，与 `ff.variable_array(name)` 逐点比对（相对容差 1e-6），覆盖 ≥3 个变量 × 2 种格式。
- 产出一张**可复现的对标表**（写入 `analysis/scpost_crosscheck.md`），取代此前的自评百分比。
- **验收**：至少 6 组比对通过；不通过的项登记为后续轮次输入。

---

## 5. 阶段 C：数据层忠实（R118–R126 中的 R123/R124/R125）

| 轮次 | 交付 |
|---|---|
| **R123** | `LS_Scalar:*`/`LS_Vector:*` 命名段驱动变量名（替代块序号映射）；删除 `ATMS ← TEMP` 伪造；UTF-8 区域显示名；`AMOM(*)` 等全部 BC 段；`LS_RegionName&Type`；体积区名 |
| **R124** | CGNS：`Elements_t` 的 `' data'`（前导空格）数据集作类型码来源；`NGON_n(22)/NFACE_n(23)` + `ElementStartOffset` + 负引用（NFACE 面符号）；`_CODE_CELLS` 13/14 与 SIDS 对齐；读全部 base；`FlowSolution` 过滤 `GridLocation/Descriptor`；`ZoneBC` 接入 `bc_plan` 使 BC 成为区域 |
| **R125** ✅ | FPH：`FC_Scalar/FC_Vector` 面心段**盘点 + 如实报告**（维度、原因写进 `ff.meta["unparsed_fields"]` 并打日志）；实测证明 `EC_*` 段本来就是单帧（标量 1 个数组、矢量正好 3 个分量），"保留全部帧"这条前提在本机文件上不成立，不写假修复；解码面对应关系因文件无面索引而留 R125b |

| **R126** ✅ | 导出：`.mp4` 接既有 ffmpeg 路径（两条视频路径都接），否则**显式拒绝**；`.avi` 在没有 vtkAVIWriter 的构建上同样拒绝而不再静默写 Ogg Theora；`snapshot_png` 未知扩展名拒绝而不改名；FBX/CVFF 写入器补 GUI 入口与真文件测试（实测前后对照见 DEV_SUMMARY §28.1） |

**R124 验收（本计划最关键的一条）**：`tr03_9_orig.cgns` 与 `exPRE04-1_37.cgns` 解出的单元数与同源 `.fph` 一致（±0.1%），变量表与 `PRES/TEMP/TURK/TEPS` 等对齐，且能建出可切面的 ugrid。

> **R124 实测结果（2026-09-13）：完全相等，超过 ±0.1% 的验收线。**
> tr03_9：221786 节点 / 63697 单元 / 323827 面，11 个变量与 FPH 逐个同名，104 个区域；exPRE04：
> 585872 / 531434 / 1649182，10 个变量同名，12 个区域。修复前两个文件的单元数都是 **0**
> （NGON_n/NFACE_n 未实现），且都带一个伪造的 `GridLocation` 变量。
> 另实测出"zone 重复计数"：Cradle 把同一批单元按 region/part/FPHPARTS.* 重复写出，
> 全读会得到约两倍单元（tr03_9 127396 vs 63697），现在按单元中心精确去重并在 meta 里报告。
>
> **仅多面体文件**（面编号显式）的 ZoneBC 能变成可选区域（实测 inlet 170 面 / 面积 2.804853e-3）。
> 元素型 CGNS 的 BC 走 SIDS"隐含面编号"，需要先做面枚举，留 R124b；这类文件的行为与 R124 之前一致。
>
> **R124 顺带发现（转入 R131）**：字段消费门禁在本轮暴露 —— `GroupingObject.subgroups` 只被
> Grouping 对话框写入，唯一读取者 `objects.grouping_members()` **在应用里没有任何调用点**
> （只有 test_gui.py 直接调它），即"分组包含关系"从未生效。已按 planned R131 记入豁免原因。

---

## 6. 阶段 D：渲染与交互贯通（R118–R122）

| 轮次 | 交付 | 验收 |
|---|---|---|
| **R118** | volume 的 hex 走 `vtkDataSetTriangleFilter`+`vtkProjectedTetrahedraMapper`（或统一走 resample）；修 `volume.py:152-155` 运算符优先级；surface `trim` 数值与半空间方向；particle `Points` 加 vertex cell；`information` 按 `VariableInfo.location` 分派；glyph 统一 `SetScaleModeToScaleByVector`；`point` Cross/Plus 改用存在的 VTK API | 每项一个像素级或数值级回归测试 |
| **R119** | `register_actor_object` 覆盖 surface/particle；图层键统一（`set_layer_visible` 支持前缀匹配或改为存储复合键）；框选/Delete/Hide Selected 对默认 Surface 生效 | 树 eye 对 32 kind 全部生效（矩阵测试） |
| **R120** | `_setup_drag_handlers` 接线；Integrate 页接 `integrate_cut`/`integrate_surface`；Pick/Automove/Intersect 死字段**要么实现要么从 UI 移除**（不留装饰控件） | 字段消费矩阵门禁通过 |
| **R121** | 全局对象（camera/light/gradation/draw window）纳入 STA；GUI 增加 "Load Status" | 存盘→重载后全局状态一致（含相机位姿） |
| **R122** | 时间线改增量重建（复用 `Scene.apply_to_object`）且**不调 `ResetCamera`**；修 `frames=0` 导致 Automove 冻结；回放帧率可设 | 播放 N 帧后相机位姿不变；Automove 逐帧位移单调 |

---

## 7. 阶段 E：性能（R127–R128）

- **R127** ✅：`_section_index_cache` 加 16 条 LRU 淘汰、键从 `id(data)` 改为**内容摘要**（大小 + 三处 64 KiB 采样；路径键需要穿过所有解析器签名，理由写在码里）；索引构建从 40 遍扫描改为单遍（实测 2.8–5.0×）。
- **R127 实测更正**：`iter_data_blocks` **不需要向量化** —— 它是块到块跳转：496 MB 段 80 个块 0.001 s，38.9/52.9 MB 网格段 0.000 s，且**不出现在** load profile 里；所谓"1.36 GB 文件 50 s 固定开销"实测**不来自它**，而来自 40 遍节索引扫描（5.03 s）与字段负载解码。因此本轮改为优化实测热点（`_normalise_face_nodes` 等宽面 numpy 快路径，1.8×，输出逐元素相同），整文件加载 101 MB FLD 5.31→4.27 s、1356 MB FPH 50.64→42.93 s。
- **R127c（未做，转出）**：测试提速（session 级共享真实文件解析，目标快层 < 2 分钟）。本轮实测快层仍为 ~9.3 分钟；top-12 慢测试清单见 §2。
- **R128**：FLD 流线加空间索引（当前每采样点 O(n) 全网格扫描，单对象 94 s → 目标 <5 s）；`_cell_centers_fph` 向量化（482k 单元 20.8 s → 目标 <1 s）；大文件峰值 RSS 从 4.4× 文件降到 <2×。
- **验收**：`scripts/benchmarks.json` 阈值收紧并纳入 `scripts/check.py`。

---

## 8. 阶段 F：分析栈与文档（R129–R132）

- **R129**：`idw_field` 产物在 API/UI/报告里明确标注为 **probe-interpolated（非物理场）**，停止使用"全场重构"措辞；POD/DMD/谱接入 R115 金标；DMD 秩截断阈值改为有意义的能量准则。
- **R130**：`.rph`（实为 CRDL-FLD 容器，5 个真实样例，最大 2 GB）立项实现或从 `LOADERS` 移除；binary STL 解析；`.neu` 注册修正。
- **R131**：按 R117 交叉验证结果重排并补齐 scPOST 交互/对象面剩余缺口（此时才有资格谈"对标"）。
- **R132**：`DEV_PLAN.md`/`function_gap_analysis.md`（350 KB、100+ 轮执行记录）压缩为"当前差距表 + 证据"；删除所有自评百分比；落地三项可测指标（可复现正确率 / 无静默错误率 / 字段贯通率）。

---

## 9. 三项可测指标（替代"N% 完整度"）

| 指标 | 当前基线 | R116 后 | R132 目标 |
|---|---|---|---|
| A. 可复现正确率（跨工具数值比对通过率） | 约 0 项已做 | ≥6 组 | ≥95% |
| B. 无静默错误（失败必须报错） | 已知 ≥12 处静默错值 | 0 处（R111+R113） | 0 处 |
| C. 字段贯通率（UI 可写字段被渲染层消费） | 226/313 = 72% | 门禁建立 | ≥95%（其余标注 reserved） |
| D. 真值断言占比（辅助） | 71/1307 = 5.4% | ≥25% | ≥35% |

---

## 10. 风险与约定

1. **每轮必须先核对源码**：项目文档历史多次夸大，禁止按文档直接开工（本轮审计已证）。
2. **不许"为绿而绿"**：修正测试期望必须在提交信息里说明理由与证据。
3. **回归时长已实测**：快层 5.9–6.0 分钟、全层 17.2 分钟。全层作发布前门禁；快层作每轮门禁。**但快层目前有顺序依赖导致的假失败（R110.5）**，在修复前不得把"快层绿"当作放行依据。测试提速（session 级共享真实文件解析）在 R127 复核后转出为 **R127c**（R127 改为先修实测出的 CRDL 节索引问题）。
4. **外部依赖项**（VR HMD / ShellExecute 沙箱 / FBX 原生 writer / scPOST 未安装环境）单独登记，不计入指标 A 的分母。
5. **R117 是分水岭**：在交叉验证跑通之前，不再新增任何"对标"声明。

---

## 11. 立即执行项（本计划启动）

1. R110：落地在途修复 + `scripts/round.py` + README 归因更正 → 提交推送。
2. R111：错误可见化 → 提交推送。
3. R112 → R113：几何与数值正确性 → 提交推送。
4. 之后按表推进，每轮完成即推送。

> 每轮完成后在 `DEV_SUMMARY.md` 追加一条（标题、证据、回归数字），保持项目既有习惯。

---

## 12. 执行记录

### R110 ✅（2026-09-13，提交 `56a6351`，已推送 origin/main）

**交付**：测试夹具隔离；R109 遗留收尾；VTK 9.6 迁移风险记录；测试产物泄漏修复；`scripts/round.py` 门禁脚本。

**证据**
- `tests/pytest_tmp` 曾累积 **2.4 GB / 14,853 文件**；`tmp_path_factory` 的 `{node.name}{counter}` 命名在每次会话从 1 重新计数 → 重复运行看到上次遗留文件。修复后：原先失败的 `test_r68_presets`+`test_r72_report_bundle` 连续两次运行均 **28 passed**；会话结束残留 **0 文件**。
- `test_r19`：实测 63,697 个 FPH 单元**全部为闭合多面体、零无面单元**（R109 用 owner∪neighbour 完整壳后旧期望失效）→ 改名并断言 VTK_POLYHEDRON + 1:1 索引 + ≥4 面。
- README：删除"VTK ≥9.4.2 上游缺陷 / 需锁 9.3.1"的错误归因。
- **VTK 9.6 迁移风险**：`SetCells`→`ImportLegacyFormat` 后，重放 `tests/test_gui.py` 前 66 个测试出现原生堆损坏（0xCFFFFFFF）于体渲染测试；回退即恢复 → 保留弃用但稳定的调用，就地写明复现方式，迁移留 R118。
- 产物泄漏：`test_r12p0_scene_export_honest_fail` 曾每次往仓库根目录写 `out.fbx/out.cvw` → 改写 `tmp_path`。

**回归**：`python scripts/round.py --check` → **1037 passed / 0 failed / 3 skipped**（310 s）；105 个非 GUI 模块 **1037 passed**（354 s）。

**遗留（转入 R111/R118）**：`test_gui.py` 体渲染路径的偶发原生无响应（位置漂移，需当作 R118 前置项处理）。

**流程改进（本轮教训）**：整文件 `write` 曾把 `fv/render/plane.py`（1457 行）与 `README.md`（1045 行）**截断**，已用 `git checkout` 恢复并改用定点 `edit`。此后大文件一律用 `edit`，写完立即校验行数与 `ruff`/`ast.parse`。