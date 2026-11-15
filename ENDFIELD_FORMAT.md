# 终末地（Arknights: Endfield）MOD 格式说明（`.buf` / `.ib`）

> 适用：终末地角色 mod（本套加载器：`Meshes0000/<uuid>-<num>-0-*.buf` + 计算着色器换肤/形态键）。
> 工具：`endfield_obj_extract.py`
> 结论：**与 ZZZ/GI/HSR 的 GIMI 系完全不同**，必须单独解析。

## 1. 文件命名与来源
```
Meshes0000/<uuid>-<num>-0-Index.buf
Meshes0000/<uuid>-<num>-0-Position.buf
Meshes0000/<uuid>-<num>-0-Texcoord.buf
Meshes0000/<uuid>-<num>-0-Blend.buf
```
- 每个 `<uuid>-<num>-0` 是一个独立 mesh 部件（身体、外套、黑丝、头发、内裙、皮肤、头发阴影……）。
- 部件名写在 ini 注释里：`; [mesh:e7022b54-525-0.头发阴影_copy] [vertex_count:145]`。
- ini 中对应资源名会把 `-` 换成 `_`：
  ```
  [Resource_<uuid>_<num>_0_Position]  stride = 16  filename = Meshes0000\...-Position.buf
  [Resource_<uuid>_<num>_0_Texcoord]  stride = 8|12
  [Resource_<uuid>_<num>_0_Blend]     stride = 12
  [Resource_<uuid>_<num>_0_Index]     format = DXGI_FORMAT_R32_UINT
  ```
- 另有一批辅助缓冲（`Position_merged_map` / `Position_freq_indices` / `Position_merged_packed_pos_delta`）供 **形态键计算着色器** 使用，静态导出不需要。

## 2. 顶点布局（实测）
### Position.buf —— stride 16
| 偏移 | 语义 | 格式 | 字节 |
|---:|---|---|---:|
| +0 | POSITION | R32G32B32_FLOAT | 12 |
| +12 | 打包载荷（mod 着色器称 `uint normal`） | 4×uint8 / uint32 | 4 |

- 第 4 个 32 位字段**不是普通 float**（有些顶点解出来是 NaN/Inf）。
- 它在相邻顶点间是**平滑的**（与几何法线平滑度 cos≈0.88，几何法线≈0.94），说明是某种逐顶点属性（大概率是游戏 VS 的打包法线/切线）。
- 但用 snorm8 / unorm8 / R10G10B10A2 / 2×snorm16 / octahedral 等标准编码都**解不出与几何一致的法线**。因此静态导出时**按几何重算法线**，该字段保留为不透明数据。
- 形态键着色器结构体为：
  ```hlsl
  struct VertexAttributes { float3 position; uint normal; };
  ```

### Texcoord.buf —— stride 8 或 12
| stride | 内容 |
|---:|---|
| 8 | `TEXCOORD0 float2 @0` |
| 12 | `TEXCOORD0 float2 @0` + 4 字节打包载荷 |

- **UV 在偏移 0**（与 GIMI 系“COLOR@0、UV@+4”相反！）。
- stride 12 的额外 4 字节实测形如 `ff 58 00 00` / `00 ff 00 00`，平滑度一般，疑似打包的顶点色/法线/描边数据，静态导出不需要。

### Blend.buf —— stride 12
| 偏移 | 语义 | 格式 | 字节 |
|---:|---|---|---:|
| +0 | BLENDWEIGHTS[0..3] | 4 × uint16（**和 = 65535**） | 8 |
| +8 | BLENDINDICES[0..3] | 4 × uint8 | 4 |

验证：连续顶点的 4 个 uint16 之和恰为 65535（如 `0xf859+0x0492+0x0314+0x0000 = 65535`），索引字节如 `20 22 23 00` → 骨骼 32/34/35。

### Index.buf
- `DXGI_FORMAT_R32_UINT`，trianglelist。
- 索引可能被 `drawindexedinstanced = count, instances, start, base, first_instance` 分多次绘制；静态导出取整个 IB 即可（实例化只重复同一几何，不重复导出）。

## 3. 与其它游戏的关键差异
| 项目 | 终末地 | ZZZ | GI / HSR |
|---|---|---|---|
| Position stride | **16**（float3 + uint） | 40 | 40 |
| UV 偏移 | **+0** | +4（COLOR 后） | +4（COLOR 后） |
| UV 精度/组数 | float2 ×1 | half2 + float2 + half2×2 | float2（1~2 组） |
| Texcoord stride | **8 / 12** | 24 / 28 | 20 / 12 / 8 |
| Blend stride | **12**（u16×4 + u8×4） | 32 | 32 |
| 资源命名 | `Resource_<uuid>_<n>_0_*` | `Resource<Vivian...>` | `Resource<Name>*` |
| 换肤/形态键 | 计算着色器 + UAV | 顶点着色器 + 多 Position 变体 | 顶点着色器 + Position 变体 |

## 4. 转换方法
```powershell
python endfield_obj_extract.py <mod.ini> <输出文件夹> [--zup] [--no-normal]
```
输出：
```
out/<uuid>_<num>_<部件名>.obj    # 每个 mesh 一个 OBJ
out/manifest.json
```
- 自动从注释里提取部件名（中文会保留在文件名中）。
- 默认 Y-up，法线按几何重算；`--no-normal` 可省略法线。
- 只导出 Position + Texcoord(UV0) + Index；Blend/打包字段不参与 OBJ。

## 5. 限制
- 该 mod 的 Position.buf 是加载器/计算着色器使用的“虚拟/合并”缓冲，位置为绑定姿态；骨架与逆绑定矩阵不在这些文件里。
- 打包的 `uint normal` 与 Texcoord 额外 4 字节未能按标准编码还原，静态导出用几何法线替代。
