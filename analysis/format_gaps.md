# 格式解析完整度再评估（2026-08-10）

> **执行状态（2026-08-10）**：A–F 六项已按序实施（提交 4627570/93e707e/70ab368/
> 1d04a87/bb1d92b，见 DEV_PLAN §25）：① PPH 接入 ✅；② 粒子描述符引导多帧 ✅；
> ③ FLD 命名 BC 区 + LS_SFile SDAT ✅；④ 头部元数据/Element_InformationFlag/
> Element_Center/gph kind/ply ✅；⑤ 大文件 mmap 实测通过（box.gph 11 分钟，GC 压力修复）✅；
> ⑥ iFLD 扫描接线 + EMT 别名实测 ✅。残余：BC 载荷内部格式、iFLD Trimming、
> CGNS-ADF、EMT 真样本、Marc t16/t19。

> 方法：全仓 73 个 .py 通读骨架 + 真实样本节级清点（tr03_9.fph / tr03.gph / box.gph 5.6GB /
> laptop gph 6GB / 8 个 scPOST 官方 FLD / pphdecoding 与 gphdecoding 参考仓对照）。

## 1. 四格式解析现状（实测证据）

| 格式 | 解析器 | 已消费节 | 未消费节（文件里真实存在） | 状态 |
|---|---|---|---|---|
| **GPH** (.gph) | `mesh_gph.parse_gph_mesh` | LS_Nodes、LS_Links、LS_CvolIdOfElements、LS_VolumeRegions、LS_Parts、LS_SurfaceRegions、LS_Assemblies | `Element_InformationFlag`（逐单元标志）、`LS_SolverUnusedRegions`（tr03.gph）、头部元数据（GridType/Dimension/Comments） | ✅ 深（多面体全拓扑；tr03.gph 0.64s 载入 220333 节点/63882 单元/323146 面） |
| **FPH** (.fph) | `mesh_gph` + `fields.parse_fph_flow_solution` | 同上 + LS_SPHFile（EC_Scalar:/EC_Vector:）、Cycle、LS_ParticlesPosition / LS_ParticleV:* | `Element_Center`（预计算单元中心，改为由面重建）、`Unit:$TEMP` 等单位元数据、EC_* 之外的记录类型未知 | ✅ 深（tr03_9: 221786 节点/63697 单元/11 变量，载入 0.88s） |
| **FLD** (.fld) | `mesh_fld.parse_fld` + 字段收集 | LS_Nodes(f32/f64)、LS_Elements(34/35/36/38 混合)、LS_MatOfElements、LS_VolumeGeometryArray、LS_SurfaceGeometryArray（NGON 面+BC 计划）、Pressure/Temperature/CN01/VECT/HVEC（15 变量） | **命名 BC 节**（SCTeta: `FLUX(velocity)` 13.3KB / `WALL(static)` 11.1KB / `THERM(adiabatic)` 7.8KB，1020B 面数据块）、`LS_SFile`、`LS_STREAMcoc`/`LS_STREAMmultiblock`、LS_Scalar:*/LS_Vector:* 重复变体 | ✅ 深（8/8 官方样例全网格；2cars 1671037 混合单元；minimumHexa 描述符密集；result-only 网格继承） |
| **PPH** (.pph) | **无** | — | ZIP 项目容器：main.js/prp/sctsnapshot/xenv/xml + `meshinggroup1.gph` + `.oct` + `_part/_ridge.mdl` | ❌ 完全缺失 |

## 2. 差距排序（按投入产出比）

### A. PPH 完全缺失（最大单一差距）
- 无探测、无 loader、GUI 过滤器无 .pph。
- 参考实现完整：`D:\training\cgns\pphdecoding`（pph_parser 488 行 + sctsnapshot/oct/mdl/pphxml + 40 项测试，含 LZMS 解压、Blowfish-LE 解密 Parasolid、八叉树）。
- 最小可行增量：pph loader = zipfile 解包 → 内嵌 .gph 交给 `parse_gph_mesh`（+ 可选 part.mdl 显示几何）。风险低、可一次打开 scFLOW 项目。

### B. FPH 粒子数据截断（真实缺陷）
- `parse_particles`/`parse_particle_variables` 只取前 3 个 200B 块 = 固定 50 粒子、单帧。
- 实测 tr03_9.fph 有 **6 个** 200B 块（两组 X/Y/Z，疑似双时间帧），当前只解析第一帧 50 个。
- FieldFile 仅存 has_particles 标志，渲染层重开文件。修法：按 3 块一组累积全部帧。

### C. FLD 边界条件节被丢弃（数据在文件中、解析器不读）
- SCTeta 的命名 BC 节（FLUX/WALL/THERM × 4）携带逐面区 BC 数据（1020B 块），全部忽略；
  `LS_SFile`、`LS_STREAMcoc`/`LS_STREAMmultiblock` 仅作节边界名。
- BC 计划面名是合成标签（@UNDEFINEDENTB…），非文件内真名。

### D. GPH/FPH 元数据层薄
- `Element_InformationFlag`（逐单元标志，所有 GPH 都有）未解析（参考仓也只贴标签）。
- `Element_Center`（FPH 预计算单元中心）由面重建替代——正确但慢、无保真校验。
- 头部元数据（GridType/Dimension/Comments/Unit:$TEMP）不解析，单位/轴标签丢失。
- 独立 .gph 载入后 kind 报 fph（外观问题）；`ply` 未注册（neutral_load 支持 PLY）。

### E. 大文件路径未验证
- mmap(>512MiB)+节索引缓存已实现，但只在 18MB tr03_9.fph 上测过。
- 5.6GB box.gph / 6.0GB laptop gph 端到端未跑（LS_Links 续块逻辑已按 1GiB 分块就绪）。

### F. 周边格式半成品
- **iFLD**：ifld.py 元数据扫描器(D3)有了，loader 仍直落 fld_only_load，Trimming/局部读取未接线。
- **EMT**：探测为 fph 家族、注册到 load_file，但无真实 .emt 验证。
- **CGNS**：HDF5 读取器可用（cgnslib_vers-4400 实测 3213 节点/2560 hex），限单 Elements 节单类型、MIXED 尽力而为；ADF 遗留格式不支持；结构化 zone 未支持。
- XDMF/Nastran/Marc(.dat)/Neutral(obj/stl/neu) 有 loader 但测试只在 test_gui 合成文件里（各 1-2 项）；Marc .t16/.t19 二进制结果在范围外。

## 3. 测试深度

| 解析器 | 专项测试 | 覆盖 |
|---|---|---|
| mesh_gph | 4 | 仅 tr03_9.fph 单样本；无独立 .gph、无大文件、无粒子多帧 |
| mesh_fld | 4 + 7(scPOST 样例) | 8 官方样例全网格+混合分布+继承；无 BC 节、无 LS_SFile |
| fields | 0 专项 | 粒子截断、多变量 LS_ParticleV:* 均无断言 |
| cgns/xdmf/nastran/marc/neutral | 1-2/每 | 合成或官方小样本 |
| pph | 0 | — |

## 4. 结论

GPH/FPH/FLD 三格式已达到『完整网格 + 主要场量』深度（混合单元、续块、方言判别、
区域/Part/装配、官方样例全过），当前可行动的差距按序为：**A PPH 接入 → B 粒子多帧 →
C FLD BC 节 → D 元数据（Element_InformationFlag/单位）→ E 大文件回归 → F iFLD/EMT 收尾**。
