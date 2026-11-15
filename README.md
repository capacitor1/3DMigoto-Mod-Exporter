# 游戏 MOD 网格格式档案（`.ib` / `.buf`）

本目录收录 4 款游戏 mod 资源的格式说明与静态网格导出工具。它们都基于 3DMigoto 系加载器，
但**顶点布局、缓冲拆分、索引与 ini 约定各不相同，不能混用**。

| 游戏 | 框架 | 导出工具 | 格式说明 | 顶点总 stride（vanilla） | UV |
|---|---|---|---|---:|---|
| 绝区零 ZZZ | ZZMI / XXMI | `zzz_obj_extract.py` | `ZZMI_FORMAT.md` | 96 | 4 组（half2/float2/half2/half2） |
| 原神 GI | GIMI | `gimi_obj_extract.py` | `GIMI_FORMAT.md` | 84 | 1 组 float2 |
| 崩坏:星穹铁道 HSR | SRMI | `srmi_obj_extract.py` | `SRMI_FORMAT.md` | 84 | 1 组 float2 |
| 终末地 Endfield | EFMI | `endfield_obj_extract.py` | `ENDFIELD_FORMAT.md` | 16（Position 单独） | 1 组 float2 @0 |

## 统一用法
```powershell
# ZZZ
python zzz_obj_extract.py <mod.ini> <输出文件夹> [--no-split] [--zup]
# GI
python gimi_obj_extract.py <mod.ini> <输出文件夹> [--zup]
# HSR（身体与 hair 通常各有一个 ini）
python srmi_obj_extract.py <mod.ini> <输出文件夹> [--zup]
# 终末地
python endfield_obj_extract.py <mod.ini> <输出文件夹> [--zup] [--no-normal]
```

共同点：
- 输入都是 **ini**（工具从 `[Resource...]` 读取 stride / format / filename）。
- 输出都是 **OBJ**（`v / vt / vn`），默认转 **Y-up**，`--zup` 保留游戏原生坐标。
- 每个组件/部件单独一个 OBJ，并附 `manifest.json` 记录来源与统计。
- 都是**静态网格**：骨架与逆绑定矩阵不在这些缓冲里。

## 为什么不能通用
1. **UV 打包不同**：ZZZ 用 half2 + 4 组；GI/HSR 用 float2（HSR 头发用 half2）；终末地 UV 在偏移 0。
2. **缓冲拆分不同**：ZZZ/GI/HSR 把 Position(40)/Blend(32)/Texcoord(24|20|8) 拆开；终末地是 Position(16)/Texcoord(8|12)/Blend(12)。
3. **索引约定不同**：HSR 的 A/B/C 共用全局顶点编号；GI 用多个独立 IB；终末地用 `drawindexedinstanced`。
4. **ini 命名空间与 hash 体系不同**：`\ZZMI\` / `\GIMI\` / `\SRMI\` / 终末地的 `Resource_<uuid>_<n>_0_*`。
