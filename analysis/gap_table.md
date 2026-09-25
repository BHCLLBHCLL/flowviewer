# 当前差距表（R132b 第一步，2026-09-13）

本表取代"按轮次复述"的读法：每一行是一条**尚未完成**的差距，附证据所在位置与复现方式。
已完成项的证据在 DEV_SUMMARY.md 的 §12–§34，不在此重复。

| 编号 | 差距 | 证据 / 复现 | 阻塞或前置 |
|---|---|---|---|
| R116b | 字段消费门禁按纯文本匹配，注释里的词也算"有人用"（R124 就因此蒙混过一次） | 改成注释/字符串盲匹配会一次新增 217 个未消费字段（实测），必须连同豁免清单一起重做 | 需要单独一轮 |
| R117b | scPOST COM 数值交叉验证 | 连接与 CreateObjectFLD 正常，GetNodeXYZ 报 0x80010105 (RPC_E_SERVERFAULT)、GetNodeCount(1) 返回 0 | 需要可交互 scPOST 环境 |
| R123b | 2 段 AMOM(freeslip)/AMOM(noslip) BC 未解析 | 现有 BC 名扫描只取 bc == 18 的块 | 需先探明载荷布局 |
| R124b | 元素型（非多面体）CGNS 的 BC 到区域映射 | 这类文件的 PointList 用 SIDS 隐含面编号，需要 cg_npe/cg_connect 级面枚举；多面体文件已可用（inlet 170 面 / 面积 2.804853e-3） | 需面枚举实现 |
| R125b | FPH 的 FC_Scalar/FC_Vector 面对应关系 | 实测 7 个 FC 段（YPLS 3x12537、VEL 5x12707、TURK/TEPS 3x311、PRES 3x141、TPRS 0），文件内**没有**面索引数组；重复次数与分量数/部件数都不吻合 | 需要格式文档或 scPOST 交叉验证（与 R117b 同源） |
| R126b | 视频导出的**成功**路径未经真机验证 | 本机无 ffmpeg、无 vtkAVIWriter，只有决策表、拒绝路径与 fake-run 帧数单测 | 需要有 ffmpeg 的机器 |
| R127b | _build_face_list_and_bcs_inner（2.464 s tottime）与 _trim_faces 仍是逐面 Python | profile 见 DEV_SUMMARY §29.4 | 必须先建"面表 + bc_plan 全量等价"基准 |
| R127c | 测试提速：快层 538–661 s，目标 <2 分钟 | 慢测试清单见计划 §2；session 级共享真实文件解析 | 低风险但涉及多测试文件 |
| R128b | _numeric_trace_fld 抛 ValueError: 'x' must be finite | 修复前后**都**会抛，疑为 FLD 场 NaN 哨兵进入 VTK 点 | 需定位并决定是停线还是清哨兵 |
| R129b | 分析栈弱断言：spatialreport 2/9、gui_analysis 0/9、spatialreport_dmd 3/8、spatialfield 3/8 | 用 scripts/gates.py 的 _is_independent 逐项统计 | 需要数值金标 |
| R132b | DEV_PLAN.md / function_gap_analysis.md 压缩（本表是第一步，两份历史文档未动） | 归并依据：计划 §1 轮次总表 + DEV_SUMMARY §12–§34 | 纯文档工作 |
| 指标 | 可复现正确率 51.4%（核心 65.2%）、无静默错误 0 unconsumed、字段贯通率 71.9% | python scripts/gates.py all；python scripts/round.py --check | 只许上升 |

## 已如实推翻的计划前提（不写假修复）

R125 的"节点量多帧"（实测 EC_* 本就单帧）、R127 的"iter_data_blocks 向量化"
（实测 0.000–0.001 s/段、profile 中不出现）、R129 的"IDW 改名/标注"
（实测各层文档与元数据都已写明 IDW，且插值场不注册进变量表）。
三轮均以测量结论替代改动，并把测量值记录在 DEV_SUMMARY。

## 三条可测指标的复现命令

    python scripts/gates.py all           # 真值断言占比 + 字段消费
    python scripts/round.py --check       # ruff + mypy + 105 个非 GUI 模块回归 + 门禁
