# SRMI 格式说明（崩坏:星穹铁道 Honkai: Star Rail，`.ib` / `.buf`）

> 适用：SRMI（Star-Rail-Model-Importer）/ 3DMigoto 分支的 mod 资源。
> 工具：`srmi_obj_extract.py`

## 1. 文件是什么
- `.ib`：**Index Buffer**，`DXGI_FORMAT_R32_UINT`，trianglelist。
- `.buf`：**Vertex Buffer**，**无文件头的原始 GPU 缓冲**（小端）。
- `stride` / `format` 由 `.ini` 的 `[Resource...]` 段声明。

## 2. 原版（vanilla）顶点布局 —— stride 84，单缓冲交错
以官方 SRMI dump 的 `vb0.txt` 为准（实测）：

| 偏移 | 语义 | 格式 | 字节 |
|---:|---|---|---:|
| +0 | POSITION | R32G32B32_FLOAT | 12 |
| +12 | NORMAL | R32G32B32_FLOAT | 12 |
| +24 | TANGENT | R32G32B32A32_FLOAT | 16 |
| +40 | BLENDWEIGHTS | R32G32B32A32_FLOAT | 16 |
| +56 | BLENDINDICES | R32G32B32A32_UINT | 16 |
| +72 | COLOR | R8G8B8A8_UNORM | 4 |
| +76 | TEXCOORD0 | R32G32_FLOAT | 8 |

合计 **84 字节**。vanilla 只有 1 组 float2 UV。

## 3. mod 常见拆分方式（本导出器支持）
| 文件 | stride | 内容 |
|---|---:|---|
| `*Position.buf` | **40** | POSITION(12) + NORMAL(12) + TANGENT(16) |
| `*Blend.buf` | **32** | BLENDWEIGHTS(16) + BLENDINDICES(16) |
| `*Texcoord.buf` | **20** | COLOR(4) + TEXCOORD0 float2(8) + TEXCOORD1 float2(8)（身体常见，UV1 常与 UV0 相同） |
| `*Texcoord.buf` | **8** | COLOR(4) + TEXCOORD0 **half2**(4)（头发等，实测 UV 在 +4，半精度） |
| `*Texcoord.buf` | **12** | COLOR(4) + TEXCOORD0 float2(8) |

> 关键差异：SRMI 的头发等部件会把 UV 压成 **half2**；导出器用“在 [0,1] 内占比 + 方差”自动在 `float2@0` / `half2@4` 间选择，避免把全 0 的 float2 误判成 UV。

## 4. 索引与部件
- 一个角色常只有 **一套顶点缓冲**，IB 拆成 `A.ib / B.ib / C.ib`（以及单独的 hair 子目录/ini）。
- **IB 索引是全局的**：A/B/C 共用 `0..N-1` 的顶点编号（例如 A 到 291829，B 从 291830 开始）。因此每个 IB 单独导出时必须按实际引用顶点压缩重映射（本工具已做）。
- `draw = 364040,0` 这类行给出顶点总数；`drawindexed = ...` 给出各部件索引区间。

## 5. 转换方法
```powershell
# 身体（A/B/C）
python srmi_obj_extract.py <mod.ini> <输出文件夹> [--zup]
# 头发（单独的 hair/*.ini）
python srmi_obj_extract.py <mod>\hair\Stellehair.ini <输出文件夹> [--zup]
```
输出：
```
out/<Base>/<Base>_<Part>.obj    # 每个 IB 一个 OBJ
out/manifest.json
```
默认 Y-up；OBJ 含 `v / vt(UV0) / vn`。

## 6. 限制
- 不含骨架/逆绑定矩阵，导出为**静态网格**；`Blend.buf` 提供权重+骨骼索引。
- `Position.boobs/butt/preg/...` 等是**形态键变形后**的位置，基线为 `Position.buf`。
- 与 GI 同属 GIMI 系但**不可直接互换**：SRMI 的 UV 打包（half2）、IB 全局索引、ini 命名空间不同。
