# 功能差距分析 — 第十七轮（R17–R22 落地刷新）

- 分析日期：2026-08-30
- 对比基准：Cradle CFD 2025.2 scPOST（API 面权威文档：`analysis/vb_fldfile.txt`
  FLDFile 125 方法、`analysis/vb_application.txt` Application 62 方法；对象面
  41 个 VB 公开类）
- 分析对象：`fv/` 68 个 `.py`（model 11 / render 29 / gui 9 / crdl 15 / 根 4）
- 证据来源：git 提交链（R17–R22 共 8 个提交，HEAD `76e087f`）、test_r18–r21
  回归（27 项）、README 开发地图
- 说明：本文档为 `analysis/function_gap_analysis.md` §8.13 的独立快照，
  结论以后者为准，如有出入以主文档最新轮次为权威。

## 1. R17–R22 落地清单

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

## 2. 对 scPOST 清单的收敛（对照主文档 §8.9 / §8.12）

| 上轮遗留 | 本轮状态 |
|---|---|
| CradleViewer 解码（§8.12 剩余外部项） | **解除**：R17 解析/加载/逐字节写回闭环 |
| COM `SaveCradleViewer` 诚实 NYI（§8.9 表） | 激活为真实 CVFF 导出（R17-T4b） |
| FLDFile 106/106、Application 62/62 | 维持 100%；R18 为基线之外新增 API 面 |
| FBX / VR HMD / ShellExecute 沙箱 | 维持外部阻塞 |

## 3. 分维度完整度 × 深度（第十七轮权威版）

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

## 4. 剩余外部项（到不了字面 100% 的原因）

| 项 | 原因 |
|---|---|
| VR 实机 HMD | 需自编译 VTK + 设备 |
| ShellExecute | 沙箱拦截（第十轮已知） |
| FBX | 无 VTK FBX writer / assimp 依赖 |
| VTK ≥9.4.2 | vtkCutter 对 vtkConvexPointSet 网格 0xC0000005；README 建议 `vtk==9.3.1` |

## 5. 超出 scPOST 的能力（R17–R22 新增）

1. CradleViewer 格式**逐字节还原写回**（bit-faithful 往返可校验）。
2. 用户自定义派生函数注册（trusted callable）+ 向量自动标量化。
3. 平面切割网格指纹缓存 + 批量 FPH 单元构建（大模型性能工程）。
4. 多数据集聚合/差分统计与自动化 CSV 报告。
5. bump 映射曲面、等值面逐周期动画（单几何跨帧复用）。
6. pip 可安装包 + `flowviewer` CLI + 可重复性能基准。

## 6. 总评

R17–R22 将第十六轮尚存的最大格式缺口（CradleViewer 专有格式）闭环，并以
五项基线外增量（R18–R22）拓宽功能面。在可实现范围内（不含 VR HMD /
ShellExecute 沙箱 / FBX 三个纯外部项），对 scPOST 2025.2 的功能完整度为
**覆盖 ~100%、端到端深度 ~97%**；工程化维度首次超出基线。剩余差距全部为
外部依赖，可实现范围内已无已知功能缺口。

## 7. 质量基线备注

- VTK 版本约束：≥9.4.2 存在 vtkCutter 对 vtkConvexPointSet 网格崩溃的
  上游缺陷，建议锁定 `vtk==9.3.1`（已写入 README 与 pyproject 说明面）。
- R21 渲染实现要点：bump 映射弃用 `vtkPolyDataNormals`（会重排点序，
  破坏 C2P 网格点对齐），改为 numpy Newell 面法向累加的顶点法向，
  `bump_factor=0` 时严格逐点还原（测试容差 1e-9）。
- R19 缓存正确性：退化单元（空 owner 面）以 0 点单元保留，维持
  FPH 单元索引与 ugrid 单元 1:1 对齐，避免过滤型 VTK 滤波器取数错位。
