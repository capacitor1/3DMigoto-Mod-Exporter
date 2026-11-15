# ZZMI 格式说明（绝区零 Zenless Zone Zero，`.ib` / `.buf`）

> 适用：ZZMI / XXMI（3DMigoto 分支）的 mod 资源。
> 工具：`zzz_obj_extract.py`

## 1. 文件是什么
- `.ib`：**Index Buffer**，`DXGI_FORMAT_R32_UINT`，trianglelist（每 3 个 uint32 一个三角）。
- `.buf`：**Vertex Buffer**，**无文件头的原始 GPU 缓冲**（小端）。
- 二者都不是容器格式，而是直接对应游戏 D3D11 的 Input Layout；`stride` / `format` 由 mod 的 `.ini` 中 `[Resource...]` 段声明。

## 2. 原版（vanilla）顶点布局 —— stride 96，单缓冲交错
以官方 ZZMI dump 的 `vb0.txt` 为准（实测，hash `cd609d98` 等与 mod 一致）：

| 偏移 | 语义 | 格式 | 字节 |
|---:|---|---|---:|
| +0 | POSITION | R32G32B32_FLOAT | 12 |
| +12 | NORMAL | R32G32B32_FLOAT | 12 |
| +24 | TANGENT | R32G32B32A32_FLOAT | 16 |
| +40 | BLENDWEIGHTS | R32G32B32A32_FLOAT | 16 |
| +56 | BLENDINDICES | R32G32B32A32_UINT | 16 |
| +72 | COLOR | R8G8B8A8_UNORM | 4 |
| +76 | TEXCOORD0 | R16G16_FLOAT | 4 |
| +80 | TEXCOORD1 | R32G32_FLOAT | 8 |
| +88 | TEXCOORD2 | R16G16_FLOAT | 4 |
| +92 | TEXCOORD3 | R16G16_FLOAT | 4 |

合计 **96 字节**。注意：ZZZ 有 **4 组 UV**，且 TEXCOORD0 是 **half2（半精度）**，TEXCOORD1 才是 float2。

## 3. mod 常见拆分方式（本导出器支持）
ZZMI 导出时通常把 96 字节按语义拆成 3 个 `.buf`：

| 文件 | stride | 内容 |
|---|---:|---|
| `*Position.buf` | **40** | POSITION(12) + NORMAL(12) + TANGENT(16) |
| `*Blend.buf` | **32** | BLENDWEIGHTS(16) + BLENDINDICES(16) |
| `*Texcoord.buf` | **24** | COLOR(4) + TEXCOORD0 half2(4) + TEXCOORD1 float2(8) + TEXCOORD2 half2(4) + TEXCOORD3 half2(4) |

- `COLOR` 实测为中灰 `(0.502,0.502,0,0)`；`TEXCOORD1` 范围 `[-1,1]`，是描边专用 UV。
- 宝石/挂饰部件布局不同：`Position` 40、`Blend` **8**（`BLENDINDICES` u32 + `BLENDWEIGHTS` u32）、`Texcoord` **28**（COLOR + 3× float2）。
- 判定规则：Texcoord 中 `COLOR` 永远在 `+0`，UV0 在 `+4`。

## 4. 索引与部件
- 一个角色通常只有 **一套顶点缓冲**，但拆成多个 IB（`bodyA.ib` / `hairA.ib` / `hairB.ib` / `jewelA.ib`）。
- 头发 A/B 共用同一套顶点缓冲，索引是**全局的**（A 到 80120，B 从 80121 开始），导出时按 IB 实际引用压缩重映射。
- `.ini` 用 `drawindexed = count, start, base` 选择服装/形态部件；`zzz_obj_extract.py` 默认会把每个 `drawindexed` 区段单独导出为 `parts/*.obj`。

## 5. 转换方法
```powershell
python zzz_obj_extract.py <mod.ini> <输出文件夹> [--no-split] [--zup]
```
输出：
```
out/<Component>/<Component>.obj        # 整块网格
out/<Component>/parts/*.obj            # 按 drawindexed 拆分的部件（默认）
out/manifest.json
```
- 默认转 Y-up；`--zup` 保持游戏原生 Z-up；`--no-split` 只导整块网格。
- OBJ 含 `v / vt(UV0) / vn`；法线直接来自 Position.buf 的 NORMAL 分量。

## 6. 限制
- 不含骨架/逆绑定矩阵，因此是**静态网格**；`Blend.buf` 里有权重与骨骼索引，可用于后续绑定。
- `*Position.{boobs,butt,preg,vagina}.buf` 等是**形态键（Shape Key）变形后**的位置，基线为 `Position.buf`。
- `.dds` 为 BC7 纹理（Diffuse 为 sRGB，其余 Linear），可直接作为材质贴图。
- 与 GI / HSR / 终末地**不通用**：UV 精度（half2 vs float2）、UV 组数（4 vs 1）、缓冲拆分、ini 命名空间均不同。
  - GI 请用 `gimi_obj_extract.py` + `GIMI_FORMAT.md`
  - HSR 请用 `srmi_obj_extract.py` + `SRMI_FORMAT.md`
  - 终末地请用 `endfield_obj_extract.py` + `ENDFIELD_FORMAT.md`
