# R3.1 / R3.5 开发难度与深度规划（2026-08-16）

> **执行状态（2026-08-16）**：
> R3.1 完成（60f1599，T1–T4 全量 + GUI 接线，7 项测试）；
> R3.5a 完成（8dbb211，pyCGNS 构建失败改纯 Python ADF 读写器 + loader 回退，5 项测试；
> cgnslib 工具链因旧 CMakeLists 与新 CMake 4 不兼容未能交叉验证）；
> R3.5b 完成（8743c86+f5e286d，pyNastran 封装 + sidecar 几何 + 真实 plate_py 夹具，5 项测试）；
> R3.5c Marc t16/t19 维持不做。全量回归 316 passed / 1 skipped / 2 deselected。

> 依据：`analysis/function_gap_analysis_r9.md` §5 的 R3 梯队定义（R3.1 = Turbo 真实叶片表面；
> R3.5 = 深格式：CGNS ADF / Nastran .op2 / Marc .t16）。
> 本规划基于对 `fv/render/turbo.py`、`fv/crdl/cgns.py` 全文复查 + 样本/依赖环境实测。

## 0. 现状核实（实测证据）

| 项 | 核实结果 |
|---|---|
| R3.1 现状 | `blade_loading_surfaces` 对**全流场顶点/单元中心**按 span 分桶后以 θ 中位数分 PS/SS（turbo.py `_field_coords` 取全体顶点，`median(thb)` 分侧）——非叶片壁面；`blade_to_blade_points` 是 |r−radius|<tol 的**体积取点** |
| R3.1 数据条件 | tr03_9.fph 已解析出 `@PartSurface_Impeller`（9011 面）、`Rotate` 部件 cvol、`link_data`（face_nodes/owner/neighbour）——**壁面面心+法向+单元值可算，夹具齐备** |
| R3.5a CGNS | HDF5 路径已深（MIXED/多 zone/结构化，提交 7c314b7）；ADF 完全缺失；**本机无任何 .adf 样例**（cgnslib 测试数据全为 HDF5） |
| R3.5b Nastran | .nas/.bdf 网格可用；**本机无 .op2 样例**；PyPI 可达（pyNastran 1.4.1） |
| R3.5c Marc | 仅 .dat 文本 + .res/.csv sidecar；**本机无 .t16/.t19 样例**；无可用库 |
| 依赖环境 | PyPI 网络可用：pyCGNS 6.3.5、pyNastran 1.4.1 可安装；两者均未装 |

---

## 1. R3.1 Turbo 真实叶片表面

**难度评级：中（算法层，无格式逆向；风险集中在几何启发式）**

### 1.1 目标定义

把 PS/SS 分侧与 B2B 取点从「全流场几何近似」升级为「真实叶片壁面」：

1. **壁面识别**（三层策略，逐层回退）：
   - L0 显式：用户/对话框指定 surface region 名（如 `@PartSurface_Impeller`）；
   - L1 名称启发：region 名命中 blade/impeller/rotor/vane/foil/翼 关键字并集；
   - L2 部件边界：faces where owner∈旋转部件 cvol ∧ neighbour∈FluidRegion（复用 `classify_volume_region_cells`），剔除 hub/shroud/周期面（法向近轴向/径向极端者）。
2. **壁面数据**：由 `link_data.face_nodes/face_offsets` 计算面心 + 外法向（owner→neighbour 方向，GPH 面节点序保证右手向），场值取 owner 单元值（cell-centred FPH 直接对应）——建立 `blade_faces = (centers, normals, values)` 三元组。
3. **PS/SS 分侧**（替换 θ 中位数）：
   - 主判据：法向周向分量 `n_θ = n·e_θ` 符号（PS 面法向指向旋转方向）；
   - 校验：同 span 桶内 θ 直方图双峰距离 ≈ 叶片厚度角（薄叶假设）；
   - 周期解卷：θ 直方图峰检测估算叶片数 → pitch=2π/N，θ 折叠到 [0,pitch) 后按 n_θ 符号两簇。
4. **B2B 面采样**：新增 `blade_to_blade_surface(ff, region, ...)`——对叶片壁面面心做 (rθ, z) 展开（可加 pitch 周期复制），替换 tol 体积取点；保留旧体积接口兼容。

### 1.2 分步实现（每步独立提交 + 测试）

| 步 | 内容 | 产出 | 估时 |
|---|---|---|---|
| T1 | `_blade_wall_faces(ff, region_names=None)`：L0/L1/L2 三层识别 + 面心/法向/owner 值 | `blade_faces` 三元组 + 单测（tr03：识别面数≈9011、法向归一、与 `@PartSurface_Impeller` 交叠率） | 0.5d |
| T2 | `blade_loading_surfaces` 重写：壁面面心 span 分桶 + n_θ 符号分侧（去中位数） | PS/SS span 曲线 + 测试断言 PS/SS 面数相当、n_θ 均值符号相反 | 0.5d |
| T3 | 周期解卷：pitch 估算（θ 峰检测）+ θ 折叠 + 双簇校验 | `pitch_angle`/`blade_count` API + 合成扇区测试 | 0.5d |
| T4 | `blade_to_blade_surface` + 渲染出口（热力图复用 `_heatmap_actor`）+ 对象字段 `blade_regions`/`blade_side` 接线 | B2B 真实壁面视图 + GUI 接线 + 快照测试 | 0.5d |
| T5 | 文档（DEV_PLAN/DEV_SUMMARY + turbo docstring 修正） | — | 0.25d |

### 1.3 深度与风险

- **深度目标（本轮）**：叶片壁面 PS/SS 分侧加载 + B2B 壁面展开 + 渲染出口；**不做**全叶片气动套件（SmartBlades/多叶排/损失模型，维持不做项）。
- **风险**：① 面节点绕向不一致 → 法向符号翻转（对策：法向一致性传播——相邻面点积同号，翻转孤立面）；② 部件 cvol 不含壁面边界（对策：L2 回退到 region 名称）；③ hub/shroud 混入（对策：法向轴向分量过滤 + L0 显式覆盖）。
- **夹具**：tr03_9.fph（`@PartSurface_Impeller` 9011 面 + `Rotate` cvol）为主夹具；laptop fan 工程（pphdecoding，`impeller1`）为二次验证。

---

## 2. R3.5 深格式（三个独立子项）

### 2.1 CGNS ADF —— 难度：中（依赖 pyCGNS 适配）／高（从零逆向，不推荐）

- **方案**：`pip install pyCGNS==6.3.5`（含 ADF 读写）→ 把 `cgns.py` 的 zone/BC/field 逻辑抽到「树接口适配层」（children/data/attr 三原语），h5py 与 pyCGNS.ADF 两个后端共享——HDF5 路径已具备 MIXED/多 zone/结构化，ADF 后端自动对齐。
- **夹具**：本机无 ADF 样例 → 用 pyCGNS 把现有 HDF5 样例（cgnslib_vers-4400.cgns 等 9 个）**写成 ADF 再读回**，round-trip 测试（节点数/单元数/场一致）；如用户提供真实 ADF（老版本商用输出）再补验。
- **深度**：对齐 HDF5 路径；ADF 多 base/link 节点后置（先单 base）。
- **估时**：重构 1d + ADF 适配 1d + round-trip 夹具与测试 0.5d ≈ **2.5d**；依赖装不上则降级为「维持不做」。

### 2.2 Nastran .op2 —— 难度：中低（依赖 pyNastran 薄封装）

- **方案**：`pip install pyNastran==1.4.1` → `read_op2`（几何 + OUGV1 位移/速度/加速度、应力应变张量、模态振型、多 subcase）→ 映射到 mesh-dict：节点/单元 + `fields`（von Mises 由张量派生标量、振型按 subcase 存）。loader：`.op2` 独立加载（op2 自带几何），或与同 stem `.nas/.bdf` 合并。
- **夹具**：pyNastran GitHub 仓库自带小 op2 样例（vendor 1–2 个到 tests/data，注明来源）；无样例则用 pyNastran 写器生成最小 op2。
- **深度**：位移/应力（含 von Mises 派生）/模态/多工况选择；**不做**流固耦合/超单元等稀见表。
- **估时**：封装+映射 1d + 夹具/测试 0.5d ≈ **1.5d**。

### 2.3 Marc .t16/.t19 —— 建议维持不做（缺样例 + 缺库 + 文档仅 MSC 手册）

- 本机零样例、无开源库、格式未公开文档化（仅 Marc 用户手册）→ 从零逆向 = **极高难度且无法验证**（5d+，成功率低）。
- **立项前提**：用户提供 ≥2 个带已知结果的 .t16/.t19 样例 + 手册章节（或 Mentor 支持文档）。满足后再单独立项（预计难度：高；深度：节点/积分点结果 + 增量步时间序列）。

---

## 3. 依赖与工程约定

- pyCGNS/pyNastran 均为**可选依赖**：仿 h5py 模式 try-import + 降级（probe/describe 诚实报「ADF 需 pyCGNS」）；`requirements-optional.txt` 登记；测试 skipif。
- 每子项独立提交推送；T 步完成跑相关子集回归，子项完成跑全量（慢测试照旧排除）。

## 4. 执行序与总工作量

| 序 | 项 | 难度 | 估时 | 理由 |
|---|---|---|---|---|
| 1 | R3.1 Turbo（T1–T5） | 中 | 2.25d | 夹具现成、纯算法、与 scPOST 专业深度差距直接相关 |
| 2 | R3.5b .op2 | 中低 | 1.5d | 依赖封装薄、pyNastran 成熟 |
| 3 | R3.5a ADF | 中 | 2.5d | 需先做树接口重构；round-trip 夹具自造 |
| 4 | R3.5c .t16/.t19 | 极高 | 维持不做 | 缺样例/缺库；等用户提供素材再立项 |

> 合计可执行工作量约 **6.25 人日**（R3.1 + ADF + op2）；完成后 Turbo 达到真实叶片表面深度、
> 格式面补上 CGNS ADF 与 Nastran 二进制结果两格（R9 文档预计 +R3 后深度 ~90%）。
