# CradleViewer (CVFF) 文件格式逆向工程报告

> R17-T1 样例差分分析结论。基于 ARsample01 (3,003,452 B) / ARsample02 (1,116,951 B)
> 两个唯一样本（6 个发行目录文件 sha256 两两相同，格式跨 2023.2–2025.2 稳定）。
> 解析器验证：AR01 全部 77 块、AR02 全部 27 块记录流 100% 精确平铺。

## 1. 总体结构

CradleViewer 文件是**自包含场景包**（几何/颜色/纹理/对象树全部内嵌，无外部引用），
供 CradleViewer 免费查看器打开。

```
File := Header(12B) Block*   （块链到 EOF，最后一块为 TREE）
Block := tag:char[4] len:u32_le content:len
```

- 3 字符标签右侧以空格填充到 4 字节：`"FLD "` `"BTN "` `"ENV "` `"PNT "` `"TEX "` `"STR "`
- 块顺序无全局约束；TREE 一定在文件尾（其 len 字段不可靠，内容读到 EOF）

## 2. 文件头（12 字节）

| 偏移 | 类型 | 值（两样本一致） | 含义 |
|---|---|---|---|
| 0x00 | char[4] | `CVFF` | 魔数 |
| 0x04 | u32 | 2 | 格式版本 |
| 0x08 | u32 | 20,120,727 (0x01330497) | 写入器标识（疑为日期 2012-07-27 编码） |

## 3. 块内容 = 记录流

除 TREE 外，所有块内容都是**平铺记录流**：

```
Record := type:u32_le size:u32_le payload:size
```

对象块前 8 字节为 `(0, 214)` 头（214 = 公共记录区大小），随后依次为
公共记录 1–8 与类型专有记录 500+。全文件无对齐填充。

## 4. 公共记录（所有对象块，位于 (0,214) 头之后）

| type | size | 含义 |
|---|---|---|
| 1 | 4 | 组 ID（kind）：关联到 TREE 条目的 B 值；0/0xFFFFFFFF = 全局对象 |
| 2 | 4 | 子类型（常见 2；0xFFFFFFFF = 全局） |
| 3 | 128 | 4×4 f64 变换矩阵（同组对象共享同一矩阵） |
| 4 | 4 | f32（AR01=0.2917 / AR02=3.0，线宽或颜色分量） |
| 5 | 4 | f32（0.5/1.0，不透明度） |
| 6 | 1 | u8 标志 |
| 7 | 4 | u32 标志（0/1） |
| 8 | 1 | u8 可见性标志 |

## 5. TREE 块（文件尾）

```
Tree := count:u32 Entry[count]
Entry := namelen:u32 name:UTF16LE[namelen] B:i32 C:i32 D:i32 E:i32
```

两样本均精确平铺（334B / 226B）。字段语义（与块 kind 交叉验证）：

| 字段 | 含义 |
|---|---|
| B | 显示组 ID —— 与块公共记录 1（kind）对应：kind=B 的所有块（BTN 图标 + 几何 + 纹理）属于该树节点；-1 = 无关联块 |
| C | 节点 ID（唯一，4..N，有空洞） |
| D | 父节点 C 值（-1 = 根；AR01 中 Water Function..Marker2 的 D=4=FLD.C，Colorbar.D=13=Global.C） |
| E | 类型/图标 ID（1=FLD, 2=Global, 5=函数面, 10/11=等值/粒子, 21=Marker, 15=Colorbar） |

AR01 树：FLD(根) → Water Function/Pressure on DST/Particles/Arrows/Marker1/Marker2；Global(根) → Colorbar。
AR02 树：FLD(根) → Edge/Occulusion/Marker1/Flow/Marker2；Global(根)。

## 6. 类型专有记录（500+）

### ENCD（len=12）
单一记录 `(500, 4, 1)` —— 编码版本=1。

### FLD（len=418）
| type | size | 含义 |
|---|---|---|
| 500 | 24 | 6×f32：模型范围 xmin,xmax,ymin,ymax,zmin,zmax（AR02=-1.5,1.5,-1,1,0,2.5） |
| 501–503 | 4 | 标志（1,1,1） |
| 504 | 4 | u32 颜色 0x00FFFFFF |
| 505 | 4 | 1 |
| 508 | 4 | f32 = 1.0 |
| 509 | 36 | 9×f32：**相机** eye(3) + target(3) + up(3)（AR01 up≈(0,0,1) ✓） |
| 510 | 16 | 4×f32 = (0,0,1,1) 视口/裁剪 |

### POLY（三角形网格）
| type | size | 含义 |
|---|---|---|
| 500 | 4 | 标志/样式位域 |
| 501 | 4 | u32 颜色 0xRRGGBB（0x7C7C7C 灰、0xFF、0xFFFFFF） |
| 502 | 12 | 3×f32 bbox min |
| 503 | 12 | 3×f32 bbox **size**（min+size = 上界；AR01 主 POLY min+size 精确复现 FLD 500 模型范围，差 ≤4e-9 ✓） |
| 504 | N×10 | 顶点记录，10B/个；**顶点数 = 506 索引最大值+1**（AR02: 615 = max 614+1 ✓）。前 3×u16 坐标线性量化到 bbox（0→min，65535→min+size，AR02 角点解码值精确落界 ✓）；第 4/5 u16 编码未定（法线/UV，解析器保留原始值） |
| 505 | T | 每面 1 字节**顶点数**（3=三角形 / 4=四边形；字节数 = 面数。AR01 主块 9,268 面 = 9,024 三角 + 244 四边 ✓；AR02 全三角 1,019 = 3057/3 ✓） |
| 506 | Σsize×2 | 变长面顶点索引（u16 串联，Σ(每面顶点数)×2 = 记录字节数 ✓） |
| 508/509 | — | 可选（小 POLY：40B/32B 双精度对，颜色渐变？） |

### LINE（折线）
| type | size | 含义 |
|---|---|---|
| 500–505 | 4 | 样式（500 位域, 501 颜色, 502–504 f32=1） |
| 506 | 12 | 3×f32 bbox min |
| 507 | 12 | 3×f32 bbox **size**（AR02 Edge 线框 min+size 精确复现 FLD 模型范围 ✓） |
| 508 | N×10 | 顶点池（10B/顶点；顶点数 = 510.max+1 ✓ AR01: 2,727） |
| 509 | S | 每折线 1 字节顶点数（样例均为 2 = 独立线段；S = 线段数） |
| 510 | Σsize×2 | u16 折线顶点索引串联（成对即线段；AR01: 2,744/2=1,372=S ✓） |

### PNT（锚点标记；每个对象组各一块）
| type | size | 含义 |
|---|---|---|
| 500 | 4 | 样式位域（0x881=2177 常规 / 1 简化） |
| 501 | 4 | u32 颜色（0x00FF00 绿 / 0 黑） |
| 502/503 | 4 | 0xFFFFFF / 0 |
| 504 | 4 | 7 / 0 |
| 505 | 24 | 6×f32 位置（均为 0 = 对象原点） |
| 506 | 8 | 2×u32 = 0x888888 |

### PTC3（粒子云）
| type | size | 含义 |
|---|---|---|
| 500 | 4 | 3（显示类型） |
| 501 | 4 | 35,332（模拟总粒子数？显示 3,600） |
| 502/503 | 4 | 0 / 3 |
| 504 | 4 | 0x3F800000 = 1.0f |
| 505 | 4 | 999,999 |
| 506 | 4 | f32 粒子尺寸 0.175 |
| 507/508 | 4 | 60 / 60（图标尺寸） |
| 509 | 4 | 0x888888 颜色 |
| 510 | 4N | 每粒子 RGBA（N=3,600） |
| 511 | 4N | 每粒子 4 字节标志（0/255） |
| 512 | 12N | 每粒子 XYZ f32（无效粒子坐标为约 -4.3e8 哨兵值） |

### TEX（纹理）
| type | size | 含义 |
|---|---|---|
| 500 | 4 | 纹理边长（256；519=256²×4B ✓） |
| 501 | 4 | 0/3 |
| 502 | 8 | 2×f32 |
| 503–509 | — | 材质参数（漫反射(1,1,1)、法线(0,0,1)等） |
| 513–518 | 8 | f64 ×6 |
| 519 | 4S² | **RGBA8888 原始像素** |
| 520–523 | 4/12 | 附加参数 |

小 TEX（546B）519=16B=2×2 像素最小纹理。

### LIGH（光源，kind=11/8，sub=0xFFFFFFFF）
| type | size | 含义 |
|---|---|---|
| 500 | 4 | f32 = 180（角度范围） |
| 501 | 12 | 3×f32 环境光（AR01 0.2 / AR02 0.5） |
| 502 | 12 | 3×f32 漫反射 |
| 503 | 12 | 3×f32 高光 |
| 504 | 8 | 2×f32（30, 1） |
| 505 | 12 | 3×f32 方向 (0.1,0.1,3.0) |
| 506 | 12 | 3×f32 反方向 (-0.1,-0.1,-3.0) |

### STR（kind=13，292B）
500=0x80201 位域, 501=0xFFFFFF, 502=28B（含 (1,1,1) f32）, 503=2B(" ")。

### BTN（树节点图标，每 B≠-1 的树节点一块）
| type | size | 含义 |
|---|---|---|
| 500 | 8 | (w:u32, h:u32) 图标尺寸（86×59 / 108×74） |
| 501 | stride×h | **RGB888 DIB 位图**（行序自底向上），每行 stride=⌈w×3/4⌉×4 **字节**（86→260B×59=15,340 ✓；108→324B×74=23,976 ✓） |

### LOGO / ENV（全局对象，kind=0）
仅公共记录（LOGO）+ 少量设置（ENV: 500=2, 501=1, 502=0.3, 503=(868,600), 509=10）。

## 7. 对象分组模型

- 块的 kind（公共记录 1）= 所属树节点的 B 值
- 每个树节点：1× BTN 图标 + 若干 POLY/LINE/PTC3/TEX/PNT 几何纹理块
- 全局块（LOGO/ENV/LIGH，sub=0xFFFFFFFF）不属于任何树节点
- kind 分配有空洞（AR01 缺 4/10/12；AR02 缺 5/8），为动态分配 ID
- 屏幕覆盖层（AR01 尾部 kind=14/15 的 4 顶点 POLY+TEX 对，sub=0xFFFFFFFF）与 LIGH（AR01 kind=11 / AR02 kind=8）不映射任何树节点
- AR01：8 BTN ↔ 8 个 B≠-1 节点；AR02：6 BTN ↔ 6 节点 ✓

## 8. 待 T2–T4 解决

1. **T2 完成**：`fv/crdl/cvff.py` 解析器（块链 + 记录流 + TREE + 各类型记录 → dataclass）；6 样例经 `analysis/_r17_t11.py` 全部通过 11 项结构不变量（2026-08-24）
2. **T3**：POLY/LINE 10B 顶点记录的精确编码（u16-bbox 量化假设待渲染验证）；PNT/PTC3 映射到 FieldFile 几何层
3. **T4a 完成**：写出器（`serialize_scene`/`write_cvff`/`build_scene`，2026-08-24）；6 样例 54/54 验证（字节级 round-trip + 量化逆变换 + 新场景构建）；**T4b**：SaveCradleViewer COM 活化 + round-trip 测试

## 9. 分析脚本

- `analysis/_r17_t1.py`–`_r17_t9.py`：递进分析（统计/hexdump/熵/TLV/记录流/TREE/几何）
- 关键验证输出：`_r17_t7.out`（全块记录平铺）、`_r17_t8.out`（TREE 平铺+kind 映射）、`_r17_t9.out`（几何编码）

## 10. 写出器（R17-T4a，2026-08-24）

### 10.1 保真模式 `serialize_scene(scene)` / `write_cvff(path, scene)`

- 记录负载**逐字节透传**（`records` 字典保持插入序 = 文件序），块链按
  `scene.blocks` 原顺序重建 → 解析→再序列化与原文件**字节级一致**
- 唯一规范化：TREE 长度字段。原写入器**多声明**（AR01: 384 vs 实际 334，
  AR02: 262 vs 226，差值 50/36 无结构规律）；写出器写真实内容长度，
  解析器两种都接受（TREE 内容始终读到 EOF）
- 6 样例 54/54 验证通过（`analysis/_r17_t13.py`）：
  - A 前缀字节一致 / TREE 仅长度字段差异（≤4 字节）
  - B 再解析场景与原场景全等（stats/tree/几何）
  - C `encode_vertices(decode(rec504/508)) == 原记录字节`（含量化 bbox
    退化轴的平面覆盖块：全零轴 t 恒 0，无信息损失）

### 10.2 量化逆变换 `encode_vertices(v, vmin, vsize, aux)`

- `t = rint((v - vmin) / vsize * 65535)`，clip 到 [0, 65535]；f64 算术
  误差 ~1e-11 ≪ 0.5，rint 精确复原原始 u16
- bbox 经 f32 舍入（与记录 502/503 存储一致）后用于量化，保证
  decode(encode) 自洽；退化轴（size=0）量化为 0，与解码器塌缩到
  vmin 的行为互逆
- aux 两列 u16 原样回写（解析时保留原始值）

### 10.3 新场景构建 `build_scene(groups, model_range=None)`

SaveCradleViewer 导出路径，`groups = [(name, vertices, faces)]`：

```
Header(CVFF, v2, 20120727)
ENCD (500=1)
FLD  (kind=2/sub=2; 500=模型范围; 509=相机 eye+target+up;
      501-508/510 = 样例模板值; 相机由范围默认计算)
LOGO (kind=0/sub=-1, 仅公共记录)
ENV  (kind=0/sub=-1, 样例模板: 868x600 等)
每组 i: POLY(kind=3+i) ... PNT(kind=3+i)     ← 每组锚点(330B 全模板)
LIGH (kind=8, 不映射树节点; AR02 模板)
TREE: FLD(B=2,C=4,D=-1,E=1) → 组名(B=3+i,C=6+i,D=4,E=5)
      → Global(B=-1,C=6+n,D=-1,E=2)
```

- 块序遵循样例模式：ENCD → FLD → LOGO → ENV → 每组[几何+PNT] → LIGH → TREE
- **u16 索引上限**：单块 ≤65535 顶点；超限组经 `_split_faces` 贪心按面
  拆分为多 POLY 块（同 kind 多块合法，样例 AR01 kind=5 即 20+ 块）；
  拆分边界共享顶点复制，无需拆分时保持原始顶点标号
- POLY 模板：500=0x02000B1E、509=0xFFFFFFFF；记录序
  [0,500,501,502,503,504,509,505,506]（样例中 508/509 位于 505/506 之前，
  新块省略未解义的 508）
- LINE 模板：500=0x10840030、501=1、502-504=1.0f、505=颜色、
  visible=0（与样例一致）
- PNT 两变体：330B 全模板（E=5 组，样式 0x881）/ 302B 简化（E=21 Marker
  组）；新场景用 330B
- 顶点 aux 两列 u16 在样例中**全部非零**（疑法线/UV，编码未解）；新块写 0

### 10.4 样例新发现（T4a 探测补充）

- POLY 记录序**非严格升序**：主块为 [0,500,501,502,503,504,**508,509**,
  505,506]（508/509 先于 505/506）
- 记录 508 **变长**：小 POLY 32B 常量、主 POLY 数 KB（按面/顶点数据，
  含义未解）；509 恒 0xFFFFFFFF
- POLY 501 为**逐组颜色**（AR02: 0x00FFA452 / 0x00F35F18），公共记录
  opacity 分组不同（0.5/1.0）
- LINE 公共记录 visible=0；BTN 图标块每树节点一块（含 FLD 组 kind=2），
  新场景暂不合成 BTN（图标位图无法生成，树节点将无图标——解析器不依赖）

## 11. 导出链路（R17-T4b，2026-08-24）

### 11.1 `api.export_cradleviewer(ff, path)` / COM `SaveCradleViewer(filepath)`

- `fv/render/export.py: export_surface_cvff` — 按区域分组导出（与
  `cvff_load` 互逆）：
  - FPH/GPH/PPH：面表取自 `link_data`（face_nodes/face_offsets），
    仅保留边界行（`neighbour == -1`），每区域一组
  - FLD：`ff.faces` + `bc_plan` 区段；FLD 面存的是文件 **1 基节点号**，
    导出时平移到 0 基（OBJ/STL/PLY/CVFF loader 本就 0 基）
  - 每组顶点压缩重编号 -> `build_scene` -> `write_cvff`；
    无区域时整体作为单组 "Boundary"
- `.cvw` 扩展名注册为 CVFF 别名（`loaders.register("cvw", ...)`，
  probe 同步；官方样例用 `.CradleViewer`，两者均可加载）
- COM `SaveCradleViewer` 从 NotImplementedError 存根活化（r15 曾按
  "格式未逆向"诚实失败；R17 逆向完成后成为真实导出，与 SaveFBX 同构）
- Round-trip 验证（`tests/test_gui.py::test_r17t4b_cradleviewer_roundtrip`）：
  - tr03_9.fph：104 区域名称逐一保留，119,335 面与区域面数总和相等，
    bbox 误差 7.5e-9 << u16 量化步长
  - ex1 FLD：13 区域、9,238 面、bbox 误差 5.4e-9
