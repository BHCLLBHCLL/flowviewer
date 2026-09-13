# flowviewer 全面代码状态分析 · 与 scPOST 多维度对标 · 下一步计划

> 分析日期：2026-09-13 · 基准：Cradle CFD 2025.2 scPOST（C:\Program Files\Cradle\CradleCFD2025.2）
> 方法：源码级审计（render/data/gui/automation 四层并行子代理）+ 本机实机复现验证（VTK 9.6.2 / Py3.12 / tr03_9.fph / ex1_100.fld / 真实 CGNS）+ 全量回归 pytest
> 证据原则：不采信项目自身文档结论，所有结论附 file:line 或实测命令输出

---

## 0. 结论摘要（TL;DR）

| 问题 | 结论 |
|---|---|
| 文档声称 | "覆盖 ~100%、端到端深度 ~97%"（analysis/function_gap_analysis_r17.md §3/§6） |
| 实测结论 | 核心可视化路径（plane/volume/surface/cgns/particle）在真实数据上存在崩溃或静默错误；新增的 ~14k 行分析+Web 栈建立在未验证的合成数据之上 |
| 最严重 | 已提交版本（HEAD 192a51b）打开真实 FPH 文件后创建 Plane 对象 → 进程原生崩溃（0xC0000005） |
| 第二严重 | 真实 CGNS 文件（Cradle CFD 导出的多面体 NGON_n/NFACE_n）载入 = 0 单元，项目名中的 "cgns" 实际不可用 |
| 第三严重 | 表面裁剪（Surface Trim）在 FLD 上把 34978 面的表面裁成 18 面；FLD 体渲染输出 0 像素；粒子默认 Points 显示 0 个可见单元 |
| 工作量错配 | 1308 项测试中 585 项（45%）测 Web 报告渲染；核心几何渲染只有 30 项；**全量 1307 个 test 中仅 5.4% 与独立真值比对，84.5% 只断言形状/非空/HTML 子串** |
| 数值正确性 | 解析解金标实测共 **14 项失败**：表面/切面积分差 5.6–10.3 倍、FPH 单元体积 0.42 倍、**FPH 梯度对线性场 max 误差 155.9**、DST 壁距中位 +47.7%、谱幅值差 n/2 倍、短序列相干恒 1.0、delx 在斜交/tet 网格取错邻居、DST 在 FLD 上不可用；而 POD/DMD/切面面积/FLD 单元体积/坐标保真/确定性则精确 |
| 关键反讽 | 现有解析金标（`test_r23.py:127` 涡量=2.0）**能通过**，因为跑在自建结构化 box 上；**同一核在真实多面体样例上 max 误差 155.9** —— 金标覆盖域没触及真实数据类型 |
| 未提交工作 | 工作区存在一个修复上述 FPH 崩溃的关键补丁（fv/render/plane.py + fv/__init__.py），未提交、未回归（导致 tests/test_r19.py 1 项失败） |
| 真实定位 | 一个功能面很广、但核心正确性未验证的原型；"对标 scPOST" 应从"补功能"转为"修正确性 + 建验证" |

---

## 1. 当前代码状态（实测）

### 1.1 规模

| 项 | 实测值 |
|---|---|
| fv/ 源码 | 110 个 .py 文件 / 41,351 行 |
| 测试 | 106 个测试文件 / 1,304 个 test 函数 / 4,190 条 assert / 19,052 行 |
| 对象种类 | 32 种 PostObject |
| 格式解码器 | 15 个 fv/crdl/*.py（fld/fph/gph/ifld/pph/cgns-hdf5/cgns-adf/xdmf/nastran/op2/marc/neutral/cvff/tsmm） |
| 渲染模块 | 31 个 fv/render/*.py |
| GUI | 13 个 fv/gui/*.py（main.py 3,047 行，127 个方法） |
| 自动化面 | api.py 159 个公开函数 + com.py 178 个公开方法（+21 动态注入） |

代码分布（行）：根目录分析栈 10,854 · gui 10,337 · render 8,453 · crdl 5,747 · model 4,113 · web 1,847

即：约 32% 的代码（根目录分析栈 + web）是与 scPOST 无关的自研增量（POD/DMD/谱分析/监测/HTML 报告）。

### 1.2 质量门实测（本机）

    python -m ruff check fv/ tests/   → All checks passed!
    python -m mypy fv/model/{varreg,derived,report}.py → Success: no issues
    python -m pytest tests -q         → 1 failed, 1302 passed, 4 skipped, 2 deselected in 1033.92s (17:13)

唯一失败：tests/test_r19.py::test_fph_grid_handles_degenerate_cells —— 由工作区未提交的 plane.py 改动引起（该测试断言存在 0 点单元，新实现改为 0 面多面体）。

VTK 弃用告警（未来版本会碎）：plane.py:238/277/295 的 SetCells 已弃用；scene.py:130/576 的 AddActor2D 已弃用。

### 1.3 工作区未提交改动 = 一个未完成的正确性修复（R109）

git status：M fv/__init__.py（+31 行，conda DLL 路径修复）、M fv/render/plane.py（+74/-28）。

该改动修复的是一个致命缺陷，我逐项复现：

| 版本 | 行为（tr03_9.fph, VTK 9.6.2, Z 中位切面） |
|---|---|
| HEAD 已提交版 | vtkCutter 对 FPH 网格 → 原生访问违例 0xC0000005，进程直接死掉（无 Python 异常、无 traceback，stdout 未 flush） |
| 工作区未提交版 | 建成 63,697 个 VTK_POLYHEDRON（完整 owner+neighbour 壳）→ 切面正常，返回 4,685 单元 / 3,863 点，面积 8.8e-3 |

根因（HEAD fv/render/plane.py:194/220）：只用 owner 面（壳不闭合）构造 VTK_CONVEX_POINT_SET，触发凸包三角化路径。README 把此现象归因于 "VTK ≥9.4.2 上游缺陷，建议锁 9.3.1" —— 归因错误，实为自己构造的单元非法；新实现用 VTK_POLYHEDRON 精确面表后，在 9.6.2 上正常。

> 这意味着：FPH（Cradle STREAM 标准多面体格式）的平面切割在发布版本上完全不可用——这是后处理最核心的操作。

### 1.4 测试投入与功能投入严重错配

按测试文件归类，1304 个 test 函数：

| 领域 | test 函数数 | 占比 |
|---|---|---|
| Web 报告（R74/R82/R84–R103） | 585 | 44.9% |
| 分析栈（POD/DMD/谱/监测） | 301 | 23.1% |
| GUI/交互 | 277 | 21.2% |
| crdl 格式解码 | 54 | 4.1% |
| 渲染/几何 | 30 | 2.3% |
| 数据模型/varreg | 20 | 1.5% |

而最近 15 个提交（R94–R108）全部是 Web 报告页面的细节打磨（命中片段、mark 高亮、分页、上/下一条链接……）。

### 1.5 对象模型"已接线"假象：87/313 字段无消费者

AST 扫描 + grep 交叉验证（fv/model/objects.py 定义 vs fv/** 引用）：

- 16 字段在 objects.py 之外零引用：trim_xmin/xmax/ymin/ymax/zmin/zmax、arbitrary_normal_r/t/p、usage_guide/hv/axis/line_paint/color_idx、constant_length、keep_original、vector_space
- 71 字段只被 GUI 对话框读写（回填自身控件），渲染层从不读

典型死控件（子代理逐项给出 file:line）：
- Plane Pick 整页（pick_shape/pick_ijk/pick_show_numbers/pick_color_enabled/...）
- Plane Integrate 整页（积分代码 plane.py:1417 integrate_cut 存在，GUI 无任何调用点）
- Plane Automove 的 automove_frames/standby/show_path/path_sync/path_start/end
- Intersection 的 inter_* / Others 整页、texture_method/pos_u/pos_v
- font_name/font_float（渲染层硬编码 Arial/Courier）
- ColorbarObject.gradation/color_map（LUT 硬编码 256/"Rainbow"）
- Isosurface 的 contour_auto/show_contour/contour_value

---

## 2. 实测缺陷清单（本机复现，按影响排序）

### 【致命 / 崩溃级】

1. FPH 平面切割使进程崩溃（HEAD plane.py:194,220）——实测 exit code -1073741819 (0xC0000005)。工作区补丁已修，未提交。
2. 真实 CGNS 文件 0 单元（fv/crdl/cgns.py）——实测：

    tr03_9_orig.cgns   fmt=cgns-hdf5  cells=0  verts=968552  vars=['GridLocation','PRES','TURK',...]
    exPRE04-1_37.cgns  fmt=cgns-hdf5  cells=0  verts=853122  vars=['GridLocation','PRES','TEMP',...]
    tr03.cgns          fmt=cgns-hdf5  cells=0  verts=959911  vars=['GridLocation']

   三个真实 Cradle CFD CGNS 文件全部解出 0 单元。原始 HDF5 结构核对：单元写在 Elements_t 组，类型码在 ' data'（注意前导空格）数据集里（[22, 0] = NGON_n），解码器用 _attr_text(g,'ElementType') 找属性（不存在）→ 类型判定失败 → 整个单元块丢弃。此外 vars=['GridLocation', ...] 说明 FlowSolution 的子节点被无差别当作变量（全 NaN 的垃圾变量）。

### 【静默错误 / 功能不可用】

- **FLD 表面几何节点整体错位一位**（本轮我独立复核）：`build_surface_polydata` 用 **1-based** 节点 id 填入 **0-based** 的 `vtkPoints`（实测 used ids 1..21145、**无 id 0**、1 个越界引用），每个面都用了错误的顶点；对照 `fv/model/topology.py:126` 有减 offset。
- **FLD 面表重复 6.3×**（本轮我独立复核）：`ff.faces` 34,978 条 = 仅 5,556 个不同面（BC 的 PARTS 与 SURFACE 各列同一批面，`mesh_fld.py:411`）→ 所有按面计数/面积统计的报告被放大 6.3 倍。
- **面积/积分取"前 3 个顶点"**：FPH 壁面积分仅真值 17.9%，FLD 表面 **10.26×**（`plane.py:1437-1448`）。
- **FPH 单元体积只累加 owner 面**：中位 0.424×、总和 40%，并经 `GetVolumeOfElement` 对外暴露（`topology.py:287-313`）。
- **FPH 梯度对线性场不精确**：max 误差 155.9、中位 0.77 → FPH 上 Q/λ₂/涡量数不可信（`derived.py:104-167`）。
- **DST 壁距量到顶点**：中位 +47.7%、p99 +1292%（`varreg.py:594-622`）。
- **谱幅值差 n/2 倍**（`spectrum.py:84`）；**短序列相干恒 1.0**（`relate.py:112-114`）。
- **表面 Trim 在 FLD 上摧毁表面**：实测 trim_surface 34,978 面 → 18 面（fv/render/surface.py:291-313 用 polydata 自身 bbox、保留半空间方向反了）。UI 上勾一下 Trim 表面就消失。
- **FLD 体渲染输出 0 像素**：实测 build_volume_actors → hex 单元先被路由到 vtkUnstructuredGridVolumeRayCastMapper（Bunyk，仅支持四面体），VTK 打印 WARN| Input contains more than tetrahedra，渲染非黑像素 0 / 43200。
- **粒子默认显示全不可见**：实测 particle_type='Points'（默认）→ polydata 50 点 / 0 verts / 0 cells，VTK 不渲染点云。必须改成 Sphere 才可见。
- **Information 探针用顶点索引查单元数组**（fv/render/information.py:17-36）：实测同一探针，顶点 idx=10/50000 返回 11 个变量，idx=200000 返回 0 个变量（因 cell 数组只有 63,697 项，len(a) > idx 静默跳过）。即 FPH 上约 2/3 的模型区域探针无输出。
- **FLD 变量 ATMS 是伪造的**：mesh_fld.py:828-829 把 TEMP 复制成 ATMS，而 ex1_100.fld 中并无 ATMS（实测变量表）。用户会看到不存在的物理量。
- **FLD 变量按"块序号"而非命名段映射**（`mesh_fld.py:824-850`）；`LS_RegionName&Type`、`AMOM(*)` BC 段（实测 9 段 BC → 只返回 7）、UTF-8 区域显示名（`Xmax面` → 带替换字符）、体积区名（ex1_100.fld 实测 `volume_names == []`）均丢失。
- **varreg 表达式 ^ 优先级错误**（varreg.py:146-160）：实测 2*3^2 → 36（应 18）；4/2^2 → 4（应 1）。派生变量静默算错。
- **varreg 表达式位置判定用子串匹配**（varreg.py:363-370）：PRES(node) 与 PRESSURE(cell) 并存时，PRESSURE*2 被判为 node → 渲染器用错几何。
- 【修正/精确化】微分算子在解析场上**正确**（本轮实测：3x3x3 结构化网格上 delx(X) 与 dely(Y) 内部节点全部精确 = 1.0），仅边界/仅单胞网格返回 0（无双向邻居时按设计跳过，非缺陷）。存在的真实风险是子代理复现的边界情形：**连接为 1-based 且尾部存在一个未使用顶点时，0/1 基判定（varreg.py:430）失效 → 邻接整体错位 → 梯度静默返回错误值**（实测 13/13 节点返回 0.0，无异常）。
- **CGNS MIXED 类型码 13/14 与 SIDS 相反**（`cgns.py:33-41`）：PENTA_6 被当 5 节点金字塔消费 → 流错位、单元丢失。
- **load_file 对未识别格式静默返回空 FieldFile**：实测 1.12 GB .rph 扫描 9.8 s 后返回 0 单元空对象且不报错；.rph（实为 CRDL-FLD 容器，与 FLD/GPH 同族）完全未实现。
- **GPH 完全不支持场变量**：实测 69 MB gph → 629,637 顶点 / 482,034 单元 / 0 变量。
- **性能**：1.36 GB FPH 急切载入 149 s / 峰值 RSS 6.0 GB（文件 4.4 倍），lazy 模式 50.5 s；_section_index_cache 是永不淘汰的模块级全局字典且按 id(data) 索引（id 复用风险）；iter_data_blocks 逐 4 字节 Python 扫描；默认 FLD 流线单对象 94 s（每采样点全网格 O(n) 扫描）；_cell_centers_fph 482k 单元 20.8 s。

### 【GUI 接线断裂（本机源码核对）】

- **对象树 eye（显隐）对多数对象静默失效**：`scene._add_*_actors` 注册的层名是带命名空间的复合键（`"surface:contour"`、`"plane:contour"`、`"cylinder:cut"`、`"pathline:tube"`、`"particle:particle"`、`"bar:..."` 等，见 `fv/render/scene.py:819/829/1011/1021/872`），而 GUI 传入的是裸 kind（`fv/gui/main.py:2163-2180` 的 `layer` 映射）。`set_layer_visible`（`scene.py:367-370`）用 `_layer_actors.get(layer, [])` 精确匹配 → 只有 `grid`/`colorbar` 以及 `surface`(共享 grid 线框) 能真正生效；cylinder/circle/text/bitmap/mirror/periodical/curve/bar/turbo/region/ufo/measure/information/pathline 的勾选框点了没有任何效果（对象 `visible` 标志变了，actor 不变）。
- **拾取（pick）与框选对默认对象失效**：`register_actor_object` 在 `_add_surface_actors`(`scene.py:804-819`) 与 `_add_particle_actors`(`scene.py:864-873`) 中**从未被调用**（对照 plane/isosurface/point/streamline/... 都有），因此 `scene.pick_actor` 对 Surface 与 Particle 恒返回空 → 左键探针、橡皮筋框选、Delete/Hide Selected 对"默认打开的 Surface 对象"全部无效。
- **拖拽手柄整条链路是死代码**：`_setup_drag_handlers`（`fv/gui/main.py:2223`）无任何调用点，其下游 `_on_vtk_drag_event`/`_drag_start`/`_drag_move`/`_move_object_to_pick`/`_drag_end` 及 `Scene.move_plane_to_pick` 全部不可达。
- **确定性良好（正面结论）**：全仓随机数只有 `fv/model/pod.py:129` 的 `np.random.default_rng(seed)`，k-means 可复现。但宽泛异常吞没共 **105 处**（`com.py` 25 / `gui/main.py` 13 / `render/vr.py` 11 / `render/scene.py` 7 / `render/export.py` 6 / `crdl/cgns.py` 6），其中 CGNS 的 ZoneType 解码失败即被吞掉并静默回退为 "Unstructured"。

### 【数值正确性金标实测（独立复核，最高价值证据）】

> 对解析解/闭式解逐项跑真值比对，结果分两类。

**通过（说明数学骨架是对的）**
- POD：合成双音（A1=1·cos5Hz + A2=0.5·sin13Hz, n=400, dt=0.01）→ σ²₁ = 200.000000 **恰好等于 A1²n/2**；能量占比 0.82413/0.17587 与幅值比预测一致；主导频率 5.000000 Hz；重复运行位级一致。
- DMD：双音 → 频率 5.0000/13.0000 精确、增长率≈0、共轭对；衰减音 exp(-3t)cos(2π·9t) → 频率 9.0000、增长率 −3.0000。
- 微分算子（varreg）：6³ 轴对齐 hex 网格上 delx(x)=1.0 在 144/144 个 x 向内部节点精确；grad(x) 均值 (1,0,0) 偏差 0；rot(−y,x,0)=(0,0,2) 精确；div((x,y,z))=3.0 精确。
- 切面面积/积分：tr03_9 上 integrate_cut 面积 0.0142518722 与 VTK 三角化面积比值 **1.000000**；常值场积分 = 面积。
- FLD 单元体积：ex1_100 求和 2.15689e-05 vs VTK 质量属性 2.16e-05；单位 hex=1.0、单位 tet=0.1666667。
- 坐标保真：FLD 的 LS_Nodes 大端 f64 与 ff.vertices 逐字节一致，无单位/缩放转换。
- 确定性：velocity_gradient / 面几何 / 切面 / POD / DMD / kmeans(seed=0) 全部位级可复现。

**失败（解析解明确不符，全部为静默错误）**

| # | 项 | 解析真值 | 实测 | 位置 |
|---|---|---|---|---|
| 1 | **FLD 表面几何索引基错位**（本轮我独立复核） | 0-based | **polydata 用 1-based id 填 0-based vtkPoints**：used ids 1..21145、**无 id 0**、1 个越界，**每个面都整体错位一个节点** | `fv/render/surface.py:112-117`（对比 `fv/model/topology.py:126` 有减 offset） |
| 2 | **FLD 面表重复 6.3×**（我独立复核） | 5,556 个不同面 | `ff.faces` **34,978 条**（`mesh_fld.py:411` 的 `seg1+seg2`，BC 的 PARTS 与 SURFACE 各列一遍同一批面）→ 所有按面计数/面积统计的报告被放大 6.3× | `fv/crdl/mesh_fld.py:411` |
| 3 | **表面/切面积分取"前 3 个顶点"当面积** | 真实 Newell 面积 | FPH 壁面 21220 面：报 0.0320 vs 真 0.1783 = **17.9%**；FLD 表面 报 0.0683 vs 真 0.00666 = **10.26×** | `fv/render/plane.py:1437-1448` |
| 4 | **FPH 单元体积只累加 owner 面** | 散度定理体积 | 中位 **0.424×**（p5 0.006×），网格总和 3.71e-04 vs 9.21e-04 = **40%**；且经 `GetVolumeOfElement` 对外暴露 | `fv/model/topology.py:287-313` |
| 5 | **FPH 梯度对线性场都不精确** | grad(x+2y,3x,5z)=[[1,2,0],[3,0,0],[0,0,5]] | max‖err‖=**155.9**，中位 0.77，63697/63697 单元超差；涡量 max 误差 37.9（真值 (0,0,1)）→ **FPH 上所有 Q/λ₂/涡量数不可信** | `fv/model/derived.py:104-167`（docstring 声称精确） |
| 6 | **DST 壁面距离量到"壁面顶点"而非壁面** | vtkImplicitPolyDataDistance | 中位 **+47.7%**，p90 +568%，p99 +1292%，max +112244% | `fv/model/varreg.py:594-622` |
| 7 | **谱幅值非 Parseval 一致** | var=4.5 | Σpsd = 900 = **n/2 倍**（无双边合并、无 1/df） | `fv/spectrum.py:84` |
| 8 | **相干性对短序列恒等于 1.0** | 白噪声应≈0 | n≤256（nseg=1）时 mean/peak coherence = **1.0000**（n=512 时 0.4004）→ 假"完全相干" | `fv/relate.py:112-114` |
| 9 | **cross_correlate 的 best_lag 符号与自身 docstring 相反**（x 领先 30 采样 → 返回 −30），且 |lag|>0 时不是 Pearson r | `fv/relate.py:48,62-75` |
| 10 | **delx/dely 在斜交/tet 网格上取"任意正向邻居"** | 斜网格 delx(y) 真值 0 | 实测 2.0；tet 网格 delx(y) ∈ {−1,−0.5,0,0.5,1}（真值 0）；边界节点静默给 0 | `fv/model/varreg.py:472-548` |
| 11 | 非均匀采样按中位 dt 做 FFT，频率偏 2.3% 且无告警；DMD 的"有效秩"截断实际无效（噪声数据 r=100/100） | — | `fv/spectrum.py:76-83`、`fv/dmd.py:41-44,107` |
| 12 | `_fph_green_gauss` 标量路径按 docstring 应支持 1-D，实际分配 **682 GiB** 抛 MemoryError | — | `fv/model/derived.py:143` |
| 13 | 同一代码内两套单元体积定义（cell 6497 比值 0.819） | — | `derived.py:152-156` vs `topology.py:287` |
| 14 | 表头整数项被报成描述符维度：`Dimension`（真值 3）、`ApplicationVersion`（2023）都显示 "1x1" | — | `fv/crdl/core.py:149-190` |

**补充失败项（数值审计终版新增）**

- **DST/NORMAL 在 FLD 上直接不可用**：`ValueError: no wall faces for DST` —— `fv/model/varreg.py:575-591` 只读 `ff.surface_regions`，**完全忽略 FLD 的 `bc_plan`**（docstring 却承诺 FLD 节点回退），而 FLD 的 16 个 BC 区就在 `bc_plan` 里。
- **delx/dely/delz 在非正交/tet 网格上取"任意正向邻居"**：斜网格 `delx(y)` 真值 0 → 实测 **2.0**；tet 网格 `delx(y)` ∈ {−1,−0.5,0,0.5,1}（真值 0）；边界节点静默给 0（我的 3×3×3 网格上 72/216 节点）。
- **同一代码内两套互相矛盾的单元体积定义**（cell 6497 比值 **0.819**）：`fv/model/derived.py:152-156` vs `fv/model/topology.py:287`。
- **DMD "有效秩"截断实际无效**：阈值 σ > 1e-12·σ_max 保留了全部模态 —— 5 探针 × 300 周期噪声数据 → **r = 100 / 100**，"主导模态"是在 ~100 个噪声模态里挑的（`fv/dmd.py:41-44,107`）。
- **表头整数项显示错误**：`Dimension`（真值 3）、`ApplicationVersion`（2023）都报成 **"1x1"**（报的是描述符维度而非值）—— `fv/crdl/core.py:149-190`。
- **`_fph_green_gauss` 标量路径按 docstring 应支持 1-D 输入，实际分配 682 GiB 抛 MemoryError**（`fv/model/derived.py:143` 广播）。
- **扭曲四边形面积返回投影（Newell）面积**：两个三角形真值 1.1180340 → 实测 1.4142136（`fv/model/topology.py:267-275`）。
- **无单位语义**：`Unit:$TEMP` 只被存成 meta 字符串（`core.py:146`），**从不附着到任何变量**。

> 关键洞察：`tests/test_r23.py:127` 的解析金标（u=(−y,x,0) → ω_z=2.0, Q=1.0, λ₂=−1.0, atol 1e-9）**是通过的**，因为它跑在测试里自建的结构化 box 网格上；**同一个核在真实多面体样例上 max 误差 155.9**。这说明现有金标测试的覆盖域没有触及真实数据类型。

**验证密度（子代理派生的全量统计，106 个测试文件 / 1307 个 test 函数）**

| 类别 | 数量 | 占比 |
|---|---|---|
| A：与独立推导的期望值比对 | **71** | **5.4%** |
| 混合 C | 131 | 10.0% |
| B：无参考（形状/非空/GUI 往返/HTML 子串…） | **1105** | **84.5%** |

- **50/106 个测试文件没有任何 A 类断言**；47 个 test 函数**完全没有 assert**。
- **仓库内不存在 golden 语料**（无 golden JSON/CSV/NPZ）；`tests/data` 只有 `plate_py.op2`（仅结构检查）和一个没有任何测试引用的 `.dat`；真实参考数据全在仓库外、靠 `skipif`，**CI 上数值测试静默跳过**。
- 少数 A 类范例：`tests/test_r23.py:127`（u=(−y,x,0) → vorticity_z=2.0, Q=1.0, λ₂=−1.0, atol 1e-9）、`test_varreg.py:138`、`test_pod.py:31/34`、`test_marc_t16.py:193-197`（真实 Marc 文件金标）、`test_gui.py:3374`。

**静默吞错（数值路径，按风险排序）**
1. `fv/crdl/mesh_fld.py:341-344` `except Exception: return [], [], []` —— 布局判断失败时**静默产出无面/无 BC 的网格**（正是能掩盖上面 FLD 面表问题的机制）
2. `fv/model/dataset.py:185-193` CGNS 失败后**静默改用 ADF 读取器**重解析同一 HDF5 文件
3. `fv/crdl/cgns.py:291-294` 变量枚举失败即 `continue`（字段从变量表消失，无告警）
4. `fv/render/plane.py:1454-1461` 标量数组缺失时用 s=0.0 代入，**报出 sum=0 / average=0 而不报错**

### 【本轮解析解金标实测（正面结论）】

- 微分算子：3x3x3 结构化 hex 网格上，`delx(X)` / `dely(Y)`（X=x, Y=y）在内部节点**全部精确等于 1.0**（9/27 节点为非零，其余为边界无双向邻居按设计跳过）。
- 随机性：全仓仅 `fv/model/pod.py:129` 使用 `np.random.default_rng(seed)`，k-means 可复现（无未播种随机）。
- 表达式优先级：`2*3^2` 实测返回 36（应 18）、`4/2^2` 实测返回 4（应 1）——`^` 与 `*` `/` 同级左结合（`fv/model/varreg.py:146-160`），**确认为静默错误**。

---

## 3. 与 scPOST 多维度对标

### 3.1 维度总表（含"文档自称"与"实测"的落差）

| 维度 | 文档自称 | 实测 | 关键证据 |
|---|---|---|---|
| 对象面（41 VB 类 → 32 kind） | 100% / 深度 96% | 类覆盖约 31/32 真，但 6 种可创建不可渲染（graph/timeseries/maxmin/grouping/regionbc + folder 部分）；对象保存不含全局对象（相机/灯光） | scene.py:680-681 明写 dialog-only |
| 格式面 | 97% / 95% | FLD/FPH 深，CGNS 在真实文件上 0 单元，GPH 无场，RPH 缺失，binary STL 不可读；FLD 面表重复 6.3× 且 **表面 polydata 节点整体错位一位** | §2.2/§2.14/数值金标表 #1/#2 |
| 数据 API / COM | 100% / 100% | 名义覆盖高，但 CreateVar 缺 scPOST 的 info 形参；CreateVarALLCYC 语义不同；CreateVarCombinationVelocity 忽略两个入参；26 个公开方法未在 _public_methods_ 注册（IDispatch 不可见）；typelib 只声明 1 个方法 | 子代理 B/C file:line |
| 渲染面 | 96% / 92% | 管线齐全但多处渲染不出/渲染错（体渲染 0 像素、Trim 摧毁表面、glyph 长度编码标量而非矢量模、信息探针索引错、Cross/Plus 标记调用不存在的 VTK 方法） | §2.3–2.6 |
| 交互/GUI | 98% / 95% | 菜单 96 项 + 工具栏 24 项全部可达且无 NYI；但拖拽手柄整条链路死代码（_setup_drag_handlers 无调用点）；Surface/Particle actor 未注册进拾取表 → 默认对象点选/框选失效；64 个对话框属性无消费者 | 子代理 C |
| 动画/时间线 | — | 回放每帧全场景 teardown+rebuild+ResetCamera()（相机被重置）；Automove 平面实时回放冻结（frames=0 → t≡0） | main.py:2551-2559, scene.py:479 |
| 导出 | 93% / 89% | STL/OBJ/FBX/CVFF/VRML/glTF 有；但 .avi/.mp4 请求静默写 Ogg Theora；唯一可用的 ffmpeg MP4 导出器 export.py:760 无调用点 | 子代理 A |
| 自动化 | 100% | api.py 159 函数中 158 个无产品调用点；render_png/AutomationSession.render 恒返回 False；fv/console.py + gui/console.py 未接线；fv/timeline.py 整模块不可达；fv/present.py 只有测试导入 | 子代理 C |
| 工程化 | "超出 scPOST" | ruff/mypy 通过、CI 有、benchmark 有 —— 确实超出；但 17 分钟测试 + 1 失败 | §1.2 |
| 性能 | 93% / 89% | 见 §2.15，峰值内存 4.4× 文件、路径级 O(n²) 多处 | 子代理 B |
| 验证/可复现 | 未单列 | 无任何与外部工具/解析解对比的基准；R44–R103 栈全部喂合成 dict；旗舰 "CGNS 序列→报告" 两端都被 monkeypatch | 子代理 C §8 |

### 3.2 最有价值的"超出 scPOST"部分（应保留）

- 工程化：pyproject.toml + flowviewer CLI + scripts/check.py 四阶段门（ruff/mypy/pytest/bench 阈值）+ GitHub Actions。scPOST 无对应物。
- CradleViewer(cvw/CVFF) 逐字节往返写回（R17）——真实逆向成果，且是唯一可字节级校验的格式。
- 监测点时序分析栈（R38–R61：trace/spectrum/spectrogram/POD/DMD/相干/相关矩阵）：scPOST 完全没有。这是真正的差异化方向。
- 内存受限流式 CGNS 读取（R26/R28/R31：窗口化 tile + 延迟变量物化）——方向正确（虽然真实 CGNS 目前解不出单元，见 §2.2）。
- Python API / COM 面的宽度（若修掉"只写 flag 无消费者"问题）。

---

## 4. 根因诊断（为什么会变成这样）

1. "完成度"用文件/类/方法名计数，而非行为验证。r30_coverage_matrix.md 的判定标准是"名字级命中"（OK(exact)），因此 CreateVar（形参不符）、CreateVarCombinationVelocity（忽略入参）都被判为"精确命中"。名字匹配 ≠ 行为正确。
2. 测试数量替代了测试质量，且**没有真值语料**。1307 个 test 中只有 71 个（5.4%）与独立期望值比对，1105 个（84.5%）只断言形状/非空/往返/HTML 子串；50/106 个测试文件零真值断言，47 个函数没有 assert；仓库内无 golden JSON/CSV/NPZ，真实参考数据在仓库外靠 skipif → **CI 上数值测试静默跳过**。核心几何仅 30 项，其中 plane 的 3 项只测缓存身份。这正是"FPH 一切就崩""表面节点错位一位""积分差 10 倍"能长期存活的原因。
3. 功能面扩张压过了正确性收敛。最近 15 个提交全部是 Web 报告细节；与此同时 HEAD 上 FPH 一切就崩。
4. 未提交的关键修复滞留工作区，说明流程上缺少"改完即提交 + 全量回归"的约束（当前工作区补丁还让 1 个测试变红）。
5. 文档把"近似/替代"写成"等价"（34 处 docstring 与实现矛盾，子代理 A 逐条列出），使后续审计持续被误导。

---

## 5. 下一步计划：从"功能对标"转向"正确性对标"

总方针：停止横向加功能 2–3 轮，先做"可信基线"——让每一个已宣称的 scPOST 能力在真实数据上可复现地正确，并把这些复现固化为测试。然后再谈超越。

### 阶段 0（本周，阻断级，最高优先）

| # | 任务 | 验收标准 |
|---|---|---|
| 0.1 | 提交/完善 R109 plane.py 修复：VTK_POLYHEDRON + owner∪neighbour 完整壳；同步修 tests/test_r19.py 的"0 点单元"断言；更新 README 的 VTK 版本归因（真因是单元非法，非上游 bug） | tr03_9.fph 切面稳定返回 4,685 单元；pytest 全绿 |
| 0.2 | CGNS 真机可用：识别 Elements_t 的 ' data'（前导空格）数据集作类型码来源；实现 NGON_n(22)/NFACE_n(23) + ElementStartOffset 负引用；修 _CODE_CELLS 13/14 与 SIDS 对齐；FlowSolution 过滤 GridLocation/Descriptor 等非变量节点；读全部 base（与 ADF 路径一致） | tr03_9_orig.cgns / exPRE04-1_37.cgns 解出与 .fph 同量级的单元数与变量 |
| 0.3 | 让错误可见：load_file 遇到未识别容器必须抛错；GPH 无场变量时明确报告"该文件不含场数据"；FPH/GPH 越界节点不再 clamp 而是报错 | 1.12 GB .rph → 明确报错而非空对象 |
| 0.4 | 修 4 个"渲染不出来"：volume hex→vtkDataSetTriangleFilter/vtkProjectedTetrahedraMapper（或直接走 resample 路径）；surface trim 数值与半空间方向；particle Points 加 vertex cell；information 探针按 VariableInfo.location 分派（顶点/cell centre） | 像素级/数值级回归测试各 1 项 |
| 0.5 | 清理 R109 引入的 SetCells 弃用 + 处理 VTK 9.6 弃用告警 | 无 DeprecationWarning |
| 0.6 | **修数值正确性（与 0.4 同批，均为静默错值）**：面积用全部顶点（Newell）而非前 3 个；FLD 面表由 PARTS+SURFACE 各列一遍改为去重；FPH `volume_of_element` 用 owner∪neighbour 面；DST 改为到**壁面**的距离（vtkImplicitPolyDataDistance 或三角形 cKDTree）；谱幅值做单边化 + 1/Δf，并显式处理非均匀采样；相干性在 nseg<2 时拒绝给出结论 | 每项配一个解析/交叉金标测试 |

### 阶段 1（2–4 周）：建立"可信基线"（验证基础设施）

| # | 任务 | 说明 |
|---|---|---|
| 1.1 | **建立仓库内 golden 语料（当前完全没有）**：把真实样例转成小型 golden JSON/NPZ 提交进 `tests/data/`，使数值测试在 CI 上不再靠 `skipif` 静默跳过 | 这是"CI 上数值测试全跳过"的唯一根治办法 |
| 1.2 | 解析解/闭式金标测试集：f=x → ∂f/∂x=1；常值场在已知面积/体积上的积分；单频正弦的 FFT 幅值（Parseval 一致性、单双边、窗函数）；已知相位差的互相关/相干；POD 双模态特征值/频率/能量占比；DST 对平面壁的解析距离 | 每项 1 个 test 带解析期望值。本轮已用这套方法直接抓出 14 项失败 |
| 1.3 | **真值断言占比门禁**：把"带独立期望值的 test 占比"纳入 `scripts/check.py`（当前 71/1307 = 5.4%） | 目标 ≥25%，且核心模块 ≥60% |
| 1.4 | 几何金标：单位立方体切面面积 =1.0；FPH 切面单元数/面积守恒；表面面积和 = 解析值；FPH 单元体积和 = 模型体积 | 直接针对积分差 5.6–10.3 倍、体积 0.42 倍两类缺陷 |
| 1.3 | scPOST 交叉验证：本机装有 scPOST_Dx64net.exe；用其 COM/VB 接口对同一 fld/fph 导出同一变量到 CSV，与 flowviewer 逐点比对（容差 <1e-6） | 唯一能真正证明"对标"的手段，替代所有自评百分比 |
| 1.4 | 回归"字段消费矩阵"测试：对 32 kind × 其模型字段，断言"每个 UI 可写字段要么被渲染层消费、要么显式标注为 reserved" | 防止 87 个死字段继续增长 |
| 1.5 | **金标必须跑在真实数据类型上**：每个金标测试同时覆盖 (a) 自建结构化网格、(b) 真实 FPH 多面体、(c) 真实 FLD —— 本轮证明只测 (a) 会放过 max 误差 155.9 的缺陷 | |
| 1.6 | 收敛率门禁：把"核心正确性测试"（1.1–1.5）纳入 scripts/check.py 阻断项 | |

### 阶段 2（4–8 周）：补齐 scPOST 真正缺口（按价值/成本排序）

1. FLD 忠实解析：读 LS_Scalar:*/LS_Vector:* 名与标题段（去掉位置块映射与 ATMS 伪造）；UTF-8 区域名；AMOM(*) 等全部 BC 段；体积区名；LS_RegionName&Type
2. FPH 场完整性：FC_Scalar/FC_Vector（面心场）解码；多帧节点量不再只留最后一帧
3. 派生变量引擎正确性：^ 优先级、token 化位置判定、操作数长度校验、0/1 基显式报错
4. 交互补全（scPOST 工作流核心，成本低）：接线拖拽手柄；把 Surface/Particle actor 注册进拾取表；Integrate 页接到已有 integrate_cut；Pick/Automove/Intersect 页字段落地或从 UI 移除
5. 动画性能与正确性：回放改为增量重建（复用 Scene.apply_to_object）+ 保持相机；修 frames=0 导致 Automove 冻结
6. 导出诚实化：.mp4 走已有的 ffmpeg 路径（export_iso_video），否则明确报"不支持 AVI"
7. 未实现格式显式登记：.rph 立项（同 CRDL-FLD 容器，5 个真实样例）或从注册表移除；binary STL；.neu 误注册修正

### 阶段 3（并行推进）：把"超出 scPOST"的独有能力做成真的差异化

保留并深化监测点时序分析栈（POD/DMD/谱/相干/相关矩阵）——这是 scPOST 完全没有的面，且不依赖未验证的场插值：

1. 停止把 IDW（反距离加权）铺开的探针模态称为"全场重构"：当前 modalfield.idw_field 用 4 近邻把探针权重铺到 63k 顶点上，物理上是插值而非重构；文档/UI 必须改名并标注"probe-interpolated（非物理场）"
2. 补 1.1 的数值金标（POD/DMD/FFT 解析验证）
3. 与 scPOST 的 Time Series (TM)/监测能力做功能对齐式对比（而非数量对比）

### 阶段 4（持续）：工程与流程

1. 提交纪律：任何修复必须"提交 + 全量回归绿"后才进入下一项；工作区不留未提交的功能性改动
2. 文档去水：把 function_gap_analysis.md（350 KB / 100+ 轮"执行记录"）压缩为"当前差距表 + 证据"，删除自我评分百分比；正确性结论只能用实测/交叉验证支撑
3. 测试瘦身：Web 报告子串断言（约 585 项）合并压缩，腾出的时间预算投给核心正确性测试
4. 性能专项：_section_index_cache 淘汰策略 + id() 键改为路径键；iter_data_blocks 向量化；FLD 流线空间索引（当前 94 s/对象）；_cell_centers_fph 向量化

---

## 6. 建议的"100% 对标"重新定义

现有"N% 完整度"没有可证伪含义。建议改为三条可测指标：

| 指标 | 定义 | 当前 | 目标 |
|---|---|---|---|
| A. 可复现正确率 | 抽查 scPOST 的 N 个具体操作，在真实样例上做数值级比对（阶段 1.3 的交叉验证）。**现有测试密度基准：仅 5.4% 的 test 带独立真值** | 约 0 项跨工具交叉验证；已知解析解失败 ≥14 项 | ≥95% 通过；真值断言占比 ≥25% |
| B. 无静默错误率 | 所有失败路径必须报错而非返回空/错值（load_file 空对象、探针静默跳过、ATMS 伪造、^ 优先级…） | 已知 ≥12 处静默错误 | 0 处 |
| C. 字段贯通率 | UI 可写字段中被渲染层消费的比例 | 226/313 = 72%（87 未消费） | ≥95%（其余显式标注 reserved） |

---

## 附：本次分析的证据文件（已落盘）

- analysis/render_audit_r104.md（579 行）——渲染层 36 条管线逐条审计，含 34 处 docstring 与实现矛盾
- analysis/render_inert_params.md——"对话框写了但渲染层不读"的字段全表
- analysis/audit_data_layer_r32.md（271 行）——15 种格式解码深度、数值风险与性能实测
- .audit/gui_automation_audit.md（524 行）——GUI/自动化可达性、死代码、inert 控件、测试诚实度

> 以上四份为本次审计新增；其余结论均可在本机用 python + D:\training\cgns\examples\* 样例复现。