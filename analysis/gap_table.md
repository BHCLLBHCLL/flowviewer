# 当前差距表（R132b 第一步，2026-09-13）

本表取代"按轮次复述"的读法：每一行是一条**尚未完成**的差距，附证据所在位置与复现方式。
已完成项的证据在 DEV_SUMMARY.md 的 §12–§37，不在此重复。

| 编号 | 差距 | 证据 / 复现 | 阻塞或前置 |
|---|---|---|---|
| R116b | 字段消费门禁按纯文本匹配，注释里的词也算"有人用"（R124 就因此蒙混过一次） | 改成注释/字符串盲匹配会一次新增 217 个未消费字段（实测），必须连同豁免清单一起重做 | 需要单独一轮 |
| R117b | scPOST COM 数值交叉验证 | 连接与 CreateObjectFLD 正常，GetNodeXYZ 报 0x80010105 (RPC_E_SERVERFAULT)、GetNodeCount(1) 返回 0 | 需要可交互 scPOST 环境 |
| R123b | 2 段 AMOM(freeslip)/AMOM(noslip) BC 未解析 | 现有 BC 名扫描只取 bc == 18 的块 | 需先探明载荷布局 |
| R124b | 元素型（非多面体）CGNS 的 BC 到区域映射 | 这类文件的 PointList 用 SIDS 隐含面编号，需要 cg_npe/cg_connect 级面枚举；多面体文件已可用（inlet 170 面 / 面积 2.804853e-3） | 需面枚举实现 |
| R125b | FPH 的 FC_Scalar/FC_Vector 面对应关系 | 实测 7 个 FC 段（YPLS 3x12537、VEL 5x12707、TURK/TEPS 3x311、PRES 3x141、TPRS 0），文件内**没有**面索引数组；重复次数与分量数/部件数都不吻合 | 需要格式文档或 scPOST 交叉验证（与 R117b 同源） |
| R126b | 视频导出的**成功**路径未经真机验证 | 本机无 ffmpeg、无 vtkAVIWriter，只有决策表、拒绝路径与 fake-run 帧数单测 | 需要有 ffmpeg 的机器 |
| R127b | _build_face_list_and_bcs_inner（2.464 s tottime）与 _trim_faces 仍是逐面 Python | profile 见 DEV_SUMMARY §29.4 | 必须先建"面表 + bc_plan 全量等价"基准 |
| R127c | 测试提速：目标 <2 分钟。**瓶颈被误判过两次**：(a) 计划 §2 的慢测试清单（test_r26_plane 17.7 s、test_r25_export、test_r21、test_pod 8.4 s）在本机**已全部 skip**，因为样例目录搬迁（见 R127d）；(b) 让门禁变成 37:07 / 50:43 的是**外部负载**——本机同时跑 8 个 chtMultiRegionSimpleFoam，CPU 100% | 第一步（session 级 load_cached 夹具）已完成：提交 `e2087f4`，test_scpost_samples **98.70 → 51.46 s**。本轮改用 `--durations` 重新实测快层（DEV_SUMMARY §35.3），不再引用失效数字 | 需先决定样例路径（R127d），再定提速目标；报耗时必须同时报机器负载 |
| R128b | _numeric_trace_fld 抛 ValueError: 'x' must be finite | 修复前后**都**会抛，疑为 FLD 场 NaN 哨兵进入 VTK 点 | 需定位并决定是停线还是清哨兵 |
| R129b | 分析栈弱断言：spatialreport 2/9、gui_analysis 0/9、spatialreport_dmd 3/8、spatialfield 3/8 | 用 scripts/gates.py 的 _is_independent 逐项统计 | 需要数值金标 |
| R127d | 真实样例搬迁：`D:/training/cgns/examples/` 已空（只剩一个“见E盘cradle目录.txt”），样例现在在 `E:/cradle` 与 `D:/training/cradle/laptop/...`。**约 27 个测试模块仍写旧路径**：多数带 skipif 静默跳过，test_pod.py 没有守卫，于是在 R133/R133b 那两次门禁里是 **4 个 FAIL**（本轮开场即撞上） | 本轮新增 `tests/samples.py`（按 ROOTS 依次解析，缺失返回 None），已接进 test_pod.py：5 passed / 21.8 s，实文件真的跑了。复现：`python -m pytest tests/test_pod.py -q` | 需决定“逐模块重接路径”还是“接受跳过”；重接会把 20+ 个实文件测试拉回快层，直接影响 R127c 的时间预算 |
| R127e | 被中断的测试会话不再清理 `tests/pytest_tmp`（conftest 只在正常退出时删 session 根），会累积到数 GB | 本轮清理前实测 **20 个会话目录 / 3.3 GB**（单个最大 644 MB；三次被 kill 的门禁各留一份 ~200 MB）。复现：`Get-ChildItem tests/pytest_tmp -Directory` | 需要在 conftest 里补异常退出清理（或每次门禁开头先清），本轮只做了人工清理 |
| R133e | Surface / Cylinder / Circle 的对象模型里根本没有 Type / Arrow Angle / Arrow Size / Thickness 字段（实测 `__dataclass_fields__`：Plane 有 15 个 `vector_*`，Surface 只有 `vector_var`，Cylinder/Circle 只有 `vector_var` + `vector_scale_length`），所以这几个对象的 Vector 页没有可写入口 | R133d 实测；scPOST 对应 tab 是否提供这些控件**未核对**（COM 仍阻塞，R117b） | 先核对 scPOST 手册/界面，再决定是否加字段；加字段就会进字段消费门禁 |
| R133f | streamline / pathline / oilflow 只验证了解析与失败路径（合成数据），真机整链路（真 ugrid + 追踪）仍未覆盖 | R133d：真机只补了 Cylinder；这三条要么需要真实样例的追踪时间，要么需要在慢层跑 | 需要在慢层加真机追踪用例（或在 test_gui.py 里补） |
| R132b | DEV_PLAN.md / function_gap_analysis.md 压缩（本表是第一步，两份历史文档未动） | 归并依据：计划 §1 轮次总表 + DEV_SUMMARY §12–§36 | 纯文档工作 |
| 指标 | 可复现正确率 51.4%（核心 65.2%）、无静默错误 0 unconsumed、字段贯通率 71.9% | python scripts/gates.py all；python scripts/round.py --check | 只许上升 |

## 已如实推翻的计划前提（不写假修复）

R125 的"节点量多帧"（实测 EC_* 本就单帧）、R127 的"iter_data_blocks 向量化"
（实测 0.000–0.001 s/段、profile 中不出现）、R129 的"IDW 改名/标注"
（实测各层文档与元数据都已写明 IDW，且插值场不注册进变量表）。
三轮均以测量结论替代改动，并把测量值记录在 DEV_SUMMARY。

## 门禁绿的适用范围（R133d 实测，写给下一次读表的人）

R133c 让 surface 的矢量源复用 plane 的 `vector_glyph_source`，而后者直接读 `obj.vector_type`；
只有 PlaneObject 有该字段，于是**所有 Surface 开矢量都会 AttributeError**，
而当轮门禁仍是 1143 passed / 0 failed——覆盖这条路径的实文件测试全在 skip（R127d）。
结论：门禁只能证明**被覆盖**的路径；报绿时必须同时报 skip 数（本轮 92），
新增路径要么带合成单测，要么进慢层真机用例。

## 三条可测指标的复现命令

    python scripts/gates.py all           # 真值断言占比 + 字段消费
    python scripts/round.py --check       # ruff + mypy + 105 个非 GUI 模块回归 + 门禁
