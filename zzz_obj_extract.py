#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZZZ (绝区零) ZZMI .ib/.buf -> OBJ 通用解析器

用法:
    python zzz_obj_extract.py <mod.ini> <输出文件夹> [--no-split] [--zup]

参数:
    <mod.ini>     ZZMI mod 的 ini(内含 Resource* / TextureOverride* 定义)
    <输出文件夹>  不存在会自动创建
    --no-split    只导出整块 mesh(默认会额外按 ini 的 drawindexed 区段拆分部件)
    --zup         保持游戏原生 Z-up(默认转成 Y-up, 便于常规引擎/查看器)

输出结构:
    out/
      <Component>/<Component>.obj      整块网格
      <Component>/parts/*.obj          按 ini 区段+drawindexed 拆分的部件(默认)
      manifest.json                    解析清单(组件、源文件、stride、统计)
"""
import os, re, sys, json
import numpy as np
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ----------------------------------------------------------------------------
# 1) 极简 ini 解析
# ----------------------------------------------------------------------------
def parse_ini(path):
    sections = {}          # name -> list of (key, value)  (key 小写)
    order = []
    cur = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line[0] in ";#":
                continue
            if line.startswith("[") and line.endswith("]"):
                cur = line[1:-1].strip()
                if cur not in sections:
                    sections[cur] = []
                    order.append(cur)
                continue
            if cur is None:
                continue
            # 只取 key = value；忽略 if/endif/else/run 等指令
            m = re.match(r"^([A-Za-z0-9_\.\\]+)\s*=\s*(.*)$", line)
            if m:
                sections[cur].append((m.group(1).lower(), m.group(2).strip()))
    return sections, order

def get(section, key, default=None):
    for k, v in section:
        if k == key:
            return v
    return default

def get_all(section, key):
    return [v for k, v in section if k == key]

# ----------------------------------------------------------------------------
# 2) 资源/组件发现
# ----------------------------------------------------------------------------
def build_resources(sections):
    """返回 {resource_name: {stride, filename, format, kind}}"""
    res = {}
    for name, body in sections.items():
        if not name.startswith("Resource"):
            continue
        typ = (get(body, "type") or "").lower()
        fn  = get(body, "filename")
        if not fn:
            continue                      # 别名/引用型资源跳过
        stride = get(body, "stride")
        fmt    = get(body, "format")
        res[name] = dict(
            stride=int(stride) if stride and stride.isdigit() else None,
            filename=fn, format=fmt, type=typ,
            is_ib=(fmt is not None and "UINT" in fmt.upper()) or fn.lower().endswith(".ib"),
        )
    return res

def discover_components(resources):
    """
    以 *Position 资源为锚点, 聚合同名 Base 的 Blend / Texcoord / IB。
    返回 [ {base, position, blend, texcoord, ibs[]} ]
    """
    comps = []
    for name, r in resources.items():
        m = re.match(r"^Resource(.+?)Position$", name)
        if not m or r["stride"] is None:
            continue
        base = m.group(1)
        blend = resources.get(f"Resource{base}Blend")
        tex   = resources.get(f"Resource{base}Texcoord")
        # IB 归属: 名字 = Resource<base><后缀>IB, 后缀通常为空/A/B/0 等(避免误吞 VivianbodyLowAIB)
        ibs = [n for n, rr in resources.items()
               if rr["is_ib"] and n.startswith(f"Resource{base}")
               and re.match(r"^Resource" + re.escape(base) + r"[A-Za-z0-9]{0,2}IB$", n)]
        if not ibs:   # 退化匹配
            ibs = [n for n, rr in resources.items()
                   if rr["is_ib"] and n.startswith(f"Resource{base}") and n.endswith("IB")]
        comps.append(dict(base=base, position=name, blend=blend and f"Resource{base}Blend",
                          texcoord=tex and f"Resource{base}Texcoord", ibs=sorted(ibs)))
    # 去重(可能因 .1/.2 shapekey 变体触发, 但那些不匹配 ^...Position$)
    uniq, seen = [], set()
    for c in comps:
        if c["base"] in seen:
            continue
        seen.add(c["base"]); uniq.append(c)
    return uniq

# ----------------------------------------------------------------------------
# 3) 缓冲解析
# ----------------------------------------------------------------------------
def read_buf(path, stride):
    b = np.fromfile(path, dtype=np.uint8)
    n = len(b) // stride
    return b[:n * stride].reshape(n, stride)

def parse_position(buf, stride):
    a = np.frombuffer(buf.tobytes(), dtype=np.float32).reshape(-1, stride // 4)
    return a[:, 0:3].copy(), a[:, 3:6].copy()          # POSITION, NORMAL

def _in01(x):
    x = x[np.isfinite(x)]
    if x.size == 0:
        return 0.0
    return float(np.mean((x >= -0.001) & (x <= 1.001)))

def parse_texcoord(buf, stride):
    """
    推断 UV0 位置。ZZZ 常见:
      stride 24: COLOR(4) + half2 UV0@4 + float2 UV1@8 + half2 UV2@16 + half2 UV3@20
      stride 28: COLOR(4) + float2 UV0@4 + float2 UV1@12 + float2 UV2@20
      stride 12: COLOR(4) + float2 UV0@4
    其它 stride 用启发式扫描(在 [0,1] 内占比最高、且方差足够的候选)。
    """
    n = len(buf)
    def half2(off):
        return np.frombuffer(buf[:, off:off+4].tobytes(), dtype=np.float16).astype(np.float32).reshape(-1, 2)
    def float2(off):
        return np.frombuffer(buf[:, off:off+8].tobytes(), dtype=np.float32).reshape(-1, 2)

    known = {24: (half2, 4), 28: (float2, 4), 12: (float2, 4), 16: (half2, 4)}
    if stride in known:
        fn, off = known[stride]
        uv = fn(off)
        if _in01(uv) > 0.5:
            return uv, f"{'half2' if fn is half2 else 'float2'}@+{off}"

    # 启发式
    best = (None, -1, "")
    for off in range(4, stride - 3):
        for fn, tag in ((half2, "half2"), (float2, "float2")):
            if off + (4 if fn is half2 else 8) > stride:
                continue
            try:
                uv = fn(off)
            except Exception:
                continue
            with np.errstate(over="ignore", invalid="ignore"):
                _uv_f = uv[np.isfinite(uv).all(1)].astype(np.float64)
                _std = float(np.mean(np.std(_uv_f, axis=0))) if len(_uv_f) else 0.0
            score = _in01(uv) - 0.02 * abs(_std - 0.15)
            if score > best[1]:
                best = (uv, score, f"{tag}@+{off}")
    if best[0] is not None:
        return best[0], best[2] + " (heuristic)"
    raise RuntimeError(f"无法推断 stride={stride} 的 UV 布局")

def parse_index(path, fmt):
    b = np.fromfile(path, dtype=np.uint8)
    if fmt and "R16" in fmt.upper():
        idx = np.frombuffer(b, dtype=np.uint16).astype(np.uint32)
    else:
        idx = np.frombuffer(b, dtype=np.uint32)
    return idx.reshape(-1, 3)

# ----------------------------------------------------------------------------
# 4) drawindexed 区段
# ----------------------------------------------------------------------------
def collect_draw_ranges(sections, resources):
    """返回 [(section_name, ib_resource, start, count, base_vertex)]，按 IB 去重。"""
    out = []
    for name, body in sections.items():
        if not name.startswith("TextureOverride"):
            continue
        ib = get(body, "ib")
        if not ib or ib not in resources:
            continue
        for v in get_all(body, "drawindexed"):
            nums = [int(x.strip()) for x in v.split(",") if x.strip().lstrip("-").isdigit()]
            if len(nums) >= 2:
                cnt, start = nums[0], nums[1]
                basev = nums[2] if len(nums) >= 3 else 0
                out.append((name, ib, start, cnt, basev))
    # 去重
    seen, uniq = set(), []
    for r in out:
        key = (r[1], r[2], r[3], r[4])
        if key in seen:
            continue
        seen.add(key); uniq.append(r)
    return uniq

# ----------------------------------------------------------------------------
# 5) 导出
# ----------------------------------------------------------------------------
def to_yup(p):
    q = np.empty_like(p); q[:, 0] = p[:, 0]; q[:, 1] = p[:, 2]; q[:, 2] = -p[:, 1]
    return q

def write_obj(path, pos, nrm, uv, faces, name, zup=False, compact=False):
    if compact:
        used = np.unique(faces)
        remap = -np.ones(len(pos), np.int64); remap[used] = np.arange(len(used))
        pos, nrm, uv = pos[used], nrm[used], uv[used]
        faces = remap[faces]
    if not zup:
        pos, nrm = to_yup(pos), to_yup(nrm)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(f"# {name}  (ZZZ ZZMI .ib/.buf)\n")
        f.write(f"o {name}\n")
        f.write("".join("v %.6f %.6f %.6f\n" % (p[0], p[1], p[2]) for p in pos))
        f.write("".join("vt %.6f %.6f\n" % (t[0], t[1]) for t in uv))
        f.write("".join("vn %.6f %.6f %.6f\n" % (n[0], n[1], n[2]) for n in nrm))
        f1 = (faces + 1).astype(np.int64)
        f.write("".join("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a,a,a,b,b,b,c,c,c)
                        for a, b, c in f1))

def safe(name):
    return re.sub(r'[^A-Za-z0-9_\.\-]+', '_', name)

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    ini_path = sys.argv[1]
    out_dir  = sys.argv[2]
    split = "--no-split" not in sys.argv
    zup   = "--zup" in sys.argv

    sections, order = parse_ini(ini_path)
    resources = build_resources(sections)
    comps = discover_components(resources)
    if not comps:
        print("未在 ini 中找到任何 Position/Blend/Texcoord 组件。"); sys.exit(2)

    ini_dir = os.path.dirname(os.path.abspath(ini_path))
    manifest = dict(ini=os.path.abspath(ini_path), components=[])

    for c in comps:
        base = c["base"]
        print(f"==== 组件 {base}")
        pr = resources[c["position"]]
        if not pr["filename"]:
            print("  跳过: Position 无 filename"); continue
        pos_buf = read_buf(os.path.join(ini_dir, pr["filename"]), pr["stride"])
        pos, nrm = parse_position(pos_buf, pr["stride"])

        uv = np.zeros((len(pos), 2), np.float32); uv_desc = "none"
        if c["texcoord"]:
            tr = resources[c["texcoord"]]
            tb = read_buf(os.path.join(ini_dir, tr["filename"]), tr["stride"])
            uv, uv_desc = parse_texcoord(tb, tr["stride"])

        # 索引
        faces_list, ib_info = [], []
        for ibn in c["ibs"]:
            ir = resources[ibn]
            f = parse_index(os.path.join(ini_dir, ir["filename"]), ir["format"])
            faces_list.append(f)
            ib_info.append(dict(resource=ibn, file=ir["filename"], tris=len(f)))
        if not faces_list:
            print("  跳过: 无 IB"); continue
        faces = np.concatenate(faces_list, 0)
        if int(faces.max()) >= len(pos):
            print(f"  警告: max_index {int(faces.max())} >= verts {len(pos)}")

        cdir = os.path.join(out_dir, safe(base))
        write_obj(os.path.join(cdir, safe(base) + ".obj"),
                  pos, nrm, uv, faces, safe(base), zup=zup)
        print(f"  verts={len(pos)} tris={len(faces)} uv={uv_desc}")

        entry = dict(name=base, vertices=int(len(pos)), triangles=int(len(faces)),
                     position=dict(resource=c["position"], file=pr["filename"], stride=pr["stride"]),
                     texcoord=dict(resource=c["texcoord"], uv_layout=uv_desc) if c["texcoord"] else None,
                     ib=ib_info, obj=os.path.relpath(os.path.join(cdir, safe(base) + ".obj"), out_dir))

        # 按 ini drawindexed 拆分
        if split:
            ranges = [r for r in collect_draw_ranges(sections, resources)
                      if r[1] in c["ibs"]]
            parts = []
            pdir = os.path.join(cdir, "parts")
            for (sec, ibn, start, cnt, basev) in ranges:
                ir = resources[ibn]
                full = parse_index(os.path.join(ini_dir, ir["filename"]), ir["format"])
                # start/count 是"索引个数", 转成三角
                tri = full[start // 3:(start + cnt) // 3]
                if len(tri) == 0:
                    continue
                if basev:
                    tri = tri + basev
                nm = f"{safe(sec)}__{start}_{cnt}"
                write_obj(os.path.join(pdir, nm + ".obj"), pos, nrm, uv, tri, nm, zup=zup, compact=True)
                parts.append(dict(section=sec, ib=ibn, start_index=start,
                                  index_count=cnt, triangles=int(len(tri)),
                                  obj=os.path.relpath(os.path.join(pdir, nm + ".obj"), out_dir)))
            entry["parts"] = parts
            print(f"  拆分部件 {len(parts)} 个 -> {os.path.relpath(pdir, out_dir)}")

        manifest["components"].append(entry)

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\n完成 ->", out_dir)

if __name__ == "__main__":
    main()
