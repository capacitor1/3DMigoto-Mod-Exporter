#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GI (原神 / Genshin Impact, GIMI 框架) MOD -> OBJ 导出器
单独实现（与 ZZZ / HSR / 终末地布局不同）。

用法:
    python gimi_obj_extract.py <mod.ini> <输出文件夹> [--zup] [--no-split]

布局（GIMI）:
    Position.buf  stride 40 : POSITION float3 @0, NORMAL float3 @12, TANGENT float4 @24
    Blend.buf     stride 32 : BLENDWEIGHTS float4 @0, BLENDINDICES uint4 @16
    Texcoord.buf  stride 20 : COLOR RGBA8 @0, TEXCOORD0 float2 @4, TEXCOORD1 float2 @12
                              (部分 mod 为 12 = COLOR + 1 组 UV)
    *.ib          R32_UINT trianglelist；多个 IB 共用同一套顶点缓冲(Head/Body/Dress 等)

输出:
    out/<Base>/<Part>.obj      每个 IB 一个 OBJ(按需压缩到被引用顶点)
    out/manifest.json
"""
import os, re, sys, json
import numpy as np
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def parse_ini(path):
    sections, cur = {}, None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line or line[0] in ";#":
                continue
            if line.startswith("[") and line.endswith("]"):
                cur = line[1:-1].strip(); sections.setdefault(cur, []); continue
            if cur is None:
                continue
            m = re.match(r"^([A-Za-z0-9_\.\\]+)\s*=\s*(.*)$", line)
            if m:
                sections[cur].append((m.group(1).lower(), m.group(2).strip()))
    return sections

def get(body, key, default=None):
    for k, v in body:
        if k == key:
            return v
    return default

def build_resources(sections):
    res = {}
    for name, body in sections.items():
        if not name.startswith("Resource"):
            continue
        fn = get(body, "filename")
        if not fn:
            continue
        st = get(body, "stride"); fmt = get(body, "format")
        res[name] = dict(file=fn, stride=int(st) if st and st.isdigit() else None,
                         format=fmt, is_ib=(fmt is not None and "UINT" in fmt.upper()))
    return res

def parse_position(path, stride):
    b = np.fromfile(path, dtype=np.uint8); n = len(b) // stride
    a = np.frombuffer(b[:n*stride], dtype=np.float32).reshape(n, stride//4)
    return a[:, 0:3].copy(), a[:, 3:6].copy()

def parse_uv(path, stride):
    """GIMI: COLOR@0(4B) + UV0 float2@4 (+ UV1 float2@12)"""
    b = np.fromfile(path, dtype=np.uint8); n = len(b) // stride
    a = np.frombuffer(b[:n*stride], dtype=np.float32).reshape(n, stride//4)
    if stride == 8:
        return a[:, 0:2].copy(), "float2@+0"
    if stride in (12, 20, 24):
        return a[:, 1:3].copy(), "float2@+4 (COLOR@0)"
    # 启发式
    best = None
    for off in range(4, stride-7, 4):
        uv = a[:, off//4:off//4+2]
        score = float(np.mean((uv >= -0.001) & (uv <= 1.001)))
        if best is None or score > best[0]:
            best = (score, uv, off)
    return best[1].copy(), f"float2@+{best[2]} (heuristic)"

def parse_index(path, fmt):
    b = np.fromfile(path, dtype=np.uint8)
    idx = (np.frombuffer(b, dtype=np.uint16).astype(np.uint32)
           if fmt and "R16" in fmt.upper() else np.frombuffer(b, dtype=np.uint32))
    if idx.size % 3:
        idx = idx[:idx.size//3*3]
    return idx.reshape(-1, 3)

def to_yup(p):
    q = np.empty_like(p); q[:,0]=p[:,0]; q[:,1]=p[:,2]; q[:,2]=-p[:,1]; return q

def write_obj(path, pos, nrm, uv, faces, name, zup=False):
    if not zup:
        pos, nrm = to_yup(pos), to_yup(nrm)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(f"# {name} (GIMI)\n"); f.write(f"o {name}\n")
        f.write("".join("v %.6f %.6f %.6f\n" % tuple(p) for p in pos))
        f.write("".join("vt %.6f %.6f\n" % tuple(t) for t in uv))
        f.write("".join("vn %.6f %.6f %.6f\n" % tuple(n) for n in nrm))
        f1 = (faces + 1).astype(np.int64)
        f.write("".join("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a,a,a,b,b,b,c,c,c) for a,b,c in f1))

def safe(s):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(s)).strip().strip(".")
    return s or "mesh"

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    ini, out = sys.argv[1], sys.argv[2]
    zup = "--zup" in sys.argv
    ini_dir = os.path.dirname(os.path.abspath(ini))
    sections = parse_ini(ini); res = build_resources(sections)

    comps = []
    for name, r in res.items():
        m = re.match(r"^Resource(.+)Position$", name)
        if m and r["stride"]:
            comps.append(m.group(1))
    if not comps:
        print("未找到 Resource*Position 组件。"); sys.exit(2)

    os.makedirs(out, exist_ok=True)
    manifest = {"ini": os.path.abspath(ini), "game": "GI/GIMI", "components": []}
    for base in sorted(set(comps)):
        posr = res.get(f"Resource{base}Position")
        uvr  = res.get(f"Resource{base}Texcoord")
        pos, nrm = parse_position(os.path.join(ini_dir, posr["file"]), posr["stride"])
        uv, uvdesc = (np.zeros((len(pos),2),np.float32), "none")
        if uvr:
            uv, uvdesc = parse_uv(os.path.join(ini_dir, uvr["file"]), uvr["stride"])
        ibs = [n for n, rr in res.items()
               if rr["is_ib"] and n.startswith(f"Resource{base}") and n.endswith("IB")]
        if not ibs:
            print(f"  {base}: 无 IB，跳过"); continue
        cdir = os.path.join(out, safe(base))
        entry = dict(name=base, obj=[], ibs=[])
        for ibn in sorted(ibs):
            part = ibn[len(f"Resource{base}"):-2] or "Mesh"
            faces = parse_index(os.path.join(ini_dir, res[ibn]["file"]), res[ibn]["format"])
            if faces.size == 0:
                continue
            mx = int(faces.max())
            if mx >= len(pos):
                print(f"  ! {base}/{part}: max_index {mx} >= verts {len(pos)}，已裁剪越界三角")
                faces = faces[(faces < len(pos)).all(1)]
            used = np.unique(faces)
            remap = -np.ones(len(pos), np.int64); remap[used] = np.arange(len(used))
            fname = f"{safe(base)}_{safe(part)}.obj"
            write_obj(os.path.join(cdir, fname), pos[used], nrm[used], uv[used],
                      remap[faces], f"{safe(base)}_{safe(part)}", zup=zup)
            print(f"  {fname:40s} verts={len(used):6d} tris={len(faces):6d} uv={uvdesc}")
            entry["obj"].append(os.path.join(safe(base), fname))
            entry["ibs"].append(dict(resource=ibn, part=part, file=res[ibn]["file"],
                                     vertices=int(len(used)), triangles=int(len(faces))))
        entry["texcoord_layout"] = uvdesc
        manifest["components"].append(entry)
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\n完成 ->", out)

if __name__ == "__main__":
    main()
