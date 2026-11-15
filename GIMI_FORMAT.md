# GIMI 格式说明（原神 Genshin Impact，`.ib` / `.buf`）

> 适用：GIMI（Genshin-Impact-Model-Importer）/ 3DMigoto 分支的 mod 资源。
> 工具：`gimi_obj_extract.py`

## 1. 文件是什么
- `.ib`：**Index Buffer**，`DXGI_FORMAT_R32_UINT`，trianglelist（每 3 个 uint32 一个三角）。
- `.buf`：**Vertex Buffer**，**无文件头的原始 GPU 缓冲**（小端）。
- 二者都不是容器格式，而是直接对应游戏 D3D11 的 Input Layout；`stride` / `format` 由 mod 的 `.ini` 中 `[Resource...]` 段声明。

## 2. 原版（vanilla）顶点布局 —— stride 84，单缓冲交错
以官方 GIMI dump 的 `vb0.txt` 为准（实测）：

| 偏移 | 语义 | 格式 | 字节 |
|---:|---|---|---:|
| +0 | POSITION | R32G32B32_FLOAT | 12 |
| +12 | NORMAL | R32G32B32_FLOAT | 12 |
| +24 | TANGENT | R32G32B32A32_FLOAT | 16 |
| +40 | BLENDWEIGHTS | R32G32B32A32_FLOAT | 16 |
| +56 | BLENDINDICES | R32G32B32A32_UINT | 16 |
| +72 | COLOR | R8G8B8A8_UNORM | 4 |
| +76 | TEXCOORD0 | R32G32_FLOAT | 8 |

合计 **84 字节**。注意：原神只有 **1 组 UV**，且 UV 是 **float2（单精度）**。

## 3. mod 常见拆分方式（本导出器支持）
GIMI 导出时通常把 84 字节按语义拆成 3 个 `.buf`：

| 文件 | stride | 内容 |
|---|---:|---|
| `*Position.buf` | **40** | POSITION(12) + NORMAL(12) + TANGENT(16) |
| `*Blend.buf` | **32** | BLENDWEIGHTS(16) + BLENDINDICES(16) |
| `*Texcoord.buf` | **20** 或 **12** | COLOR(4) + TEXCOORD0 float2(8) [+ TEXCOORD1 float2(8)] |

- stride **20**：`COLOR@0` + `UV0 float2@4` + `UV1 float2@12`（部分 mod 保留两组 UV）。
- stride **12**：`COLOR@0` + `UV0 float2@4`。
- 判定规则：UV0 永远在 `+4`（`COLOR` 之后），float2。

## 4. 索引与部件
- 一个角色通常只有 **一套顶点缓冲**，但拆成多个 IB（如 `Head.ib` / `Body.ib` / `Dress.ib`）。
- `.ini` 里常见 `drawindexed = auto`：索引数量由游戏运行时决定；每个 IB 文件本身就是该部件的完整索引，直接整块导出即可。
- 多个 IB 共用同一套顶点，所以导出时要按 IB 实际引用的顶点做压缩重映射（本工具已做）。

## 5. 转换方法
```powershell
python gimi_obj_extract.py <mod.ini> <输出文件夹> [--zup]
```
输出：
```
out/<Base>/<Base>_<Part>.obj    # 每个 IB 一个 OBJ
out/manifest.json
```
- 默认转 Y-up；`--zup` 保持游戏原生 Z-up。
- OBJ 含 `v / vt(UV0) / vn`；法线直接来自 Position.buf 的 NORMAL 分量。

## 6. 限制
- 不含骨架/逆绑定矩阵，因此是**静态网格**；`Blend.buf` 里有权重与骨骼索引，可用于后续绑定。
- 与 ZZZ / HSR / 终末地**不通用**：UV 精度、UV 组数、缓冲拆分、ini 命名空间均不同。
