#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
终末地 (Arknights: Endfield) MOD -> OBJ 导出器
（与 ZZZ/GI/HSR 的 GIMI 系布局完全不同，单独实现）

用法:
    python endfield_obj_extract.py <mod.ini> <输出文件夹> [--zup] [--no-normal]

输入 ini 里应有如下形式的资源（加载器会把 Meshes0000\\<uuid>-<num>-0-*.buf 映射进来）:
    [Resource_<id>_0_Index]      format = DXGI_FORMAT_R32_UINT  filename = Meshes0000\\...-Index.buf
    [Resource_<id>_0_Position]   stride = 16   filename = ...-Position.buf
    [Resource_<id>_0_Texcoord]   stride = 8|12 filename = ...-Texcoord.buf
    [Resource_<id>_0_Blend]      stride = 12   filename = ...-Blend.buf
"""
import os, re, sys, json
import numpy as np
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

def parse_ini(path):
    sections, order, cur = {}, [], None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if line.startswith(";") or line.startswith("#"):
                continue
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                cur = line[1:-1].strip()
                if cur not in sections:
                    sections[cur] = []; order.append(cur)
                continue
            if cur is None:
                continue
            m = re.match(r"^([A-Za-z0-9_\.\\]+)\s*=\s*(.*)$", line)
            if m:
                sections[cur].append((m.group(1).lower(), m.group(2).strip()))
    return sections, order

def get(body, key, default=None):
    for k, v in body:
        if k == key:
            return v
    return default

RES_RE = re.compile(r"^Resource_(.+)_0_(Position|Texcoord|Blend|Index)$")

def build_meshes(sections, ini_dir):
    """返回 {id: {position,texcoord,blend,index, name}}"""
    meshes = {}
    for name, body in sections.items():
        m = RES_RE.match(name)
        if not m:
            continue
        mid, kind = m.group(1), m.group(2).lower()
        fn = get(body, "filename")
        if not fn:
            continue
        stride = get(body, "stride")
        fmt = get(body, "format")
        d = meshes.setdefault(mid, {})
        d[kind] = dict(file=fn,
                       stride=int(stride) if stride and stride.isdigit() else None,
                       format=fmt)
    # 过滤掉缺 Position/Index 的条目
    return {k: v for k, v in meshes.items() if "position" in v and "index" in v}

def mesh_names(ini_path):
    """从注释 ; [mesh:<uuid>-<num>-<lod>.<name>] [vertex_count:N] 里取名字"""
    mp = {}
    pat = re.compile(r"\[mesh:([0-9a-fA-F\-]+?)\.([^\]]+)\]")
    with open(ini_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pat.search(line)
            if m:
                mp.setdefault(m.group(1), m.group(2).strip())
    return mp

def safe(s):
    s = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", str(s)).strip().strip(".")
    return s or "mesh"

def to_yup(p):
    q = np.empty_like(p); q[:, 0] = p[:, 0]; q[:, 1] = p[:, 2]; q[:, 2] = -p[:, 1]
    return q

def compute_normals(pos, faces):
    fn = np.cross(pos[faces[:, 1]] - pos[faces[:, 0]],
                  pos[faces[:, 2]] - pos[faces[:, 0]])
    ln = np.linalg.norm(fn, axis=1, keepdims=True)
    fn = fn / np.where(ln == 0, 1, ln)
    nrm = np.zeros_like(pos)
    for k in range(3):
        np.add.at(nrm, faces[:, k], fn)
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = nrm / np.where(ln == 0, 1, ln)
    return nrm

def read_position(path, stride):
    b = np.fromfile(path, dtype=np.uint8)
    n = len(b) // stride
    a = np.frombuffer(b[:n * stride], dtype=np.float32).reshape(n, stride // 4)
    return a[:, 0:3].copy(), a

def read_uv(path, stride):
    b = np.fromfile(path, dtype=np.uint8)
    n = len(b) // stride
    if stride < 8:
        return np.zeros((n, 2), np.float32), "none"
    a = np.frombuffer(b[:n * stride], dtype=np.float32).reshape(n, stride // 4)
    return a[:, 0:2].copy(), f"float2@+0 (stride {stride})"

def read_index(path, fmt):
    b = np.fromfile(path, dtype=np.uint8)
    if fmt and "R16" in fmt.upper():
        idx = np.frombuffer(b, dtype=np.uint16).astype(np.uint32)
    else:
        idx = np.frombuffer(b, dtype=np.uint32)
    if idx.size % 3:
        idx = idx[:idx.size // 3 * 3]
    return idx.reshape(-1, 3)

def write_obj(path, pos, nrm, uv, faces, name, zup=False):
    if not zup:
        pos, nrm = to_yup(pos), to_yup(nrm)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as f:
        f.write(f"# {name}  (Endfield .buf)\n")
        f.write(f"o {name}\n")
        f.write("".join("v %.6f %.6f %.6f\n" % tuple(p) for p in pos))
        f.write("".join("vt %.6f %.6f\n" % tuple(t) for t in uv))
        f.write("".join("vn %.6f %.6f %.6f\n" % tuple(n) for n in nrm))
        f1 = (faces + 1).astype(np.int64)
        f.write("".join("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (a,a,a,b,b,b,c,c,c) for a,b,c in f1))

def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    ini = sys.argv[1]; out = sys.argv[2]
    zup = "--zup" in sys.argv
    no_normal = "--no-normal" in sys.argv
    ini_dir = os.path.dirname(os.path.abspath(ini))

    sections, _ = parse_ini(ini)
    meshes = build_meshes(sections, ini_dir)
    names = mesh_names(ini)
    if not meshes:
        print("未找到 Resource_<id>_0_{Position,Index} 资源。"); sys.exit(2)

    os.makedirs(out, exist_ok=True)
    manifest = {"ini": os.path.abspath(ini), "game": "Endfield", "meshes": []}
    for mid in sorted(meshes):
        m = meshes[mid]
        pr = m["position"]; ir = m["index"]; tr = m.get("texcoord")
        pos_path = os.path.join(ini_dir, pr["file"].replace("/", os.sep))
        idx_path = os.path.join(ini_dir, ir["file"].replace("/", os.sep))
        if not os.path.exists(pos_path) or not os.path.exists(idx_path):
            print(f"  跳过 {mid}: 文件缺失"); continue
        pos, raw = read_position(pos_path, pr["stride"])
        faces = read_index(idx_path, ir["format"])
        if faces.size == 0:
            print(f"  跳过 {mid}: 空索引"); continue
        mx = int(faces.max())
        if mx >= len(pos):
            print(f"  ! {mid}: max_index {mx} >= verts {len(pos)} (截断越界三角)")
            faces = faces[(faces < len(pos)).all(1)]
        uv = np.zeros((len(pos), 2), np.float32); uvdesc = "none"
        if tr:
            tp = os.path.join(ini_dir, tr["file"].replace("/", os.sep))
            if os.path.exists(tp):
                uv, uvdesc = read_uv(tp, tr["stride"])
                if len(uv) < len(pos):
                    pad = np.zeros((len(pos) - len(uv), 2), np.float32)
                    uv = np.vstack([uv, pad])
        nrm = np.zeros_like(pos) if no_normal else compute_normals(pos, faces)
        # 只保留被使用的顶点
        used = np.unique(faces)
        remap = -np.ones(len(pos), np.int64); remap[used] = np.arange(len(used))
        f2 = remap[faces]
        nm = names.get(mid.replace("_", "-") + "-0") or names.get(mid.replace("_", "-"), mid)
        fname = safe(mid) + ("_" + safe(nm) if nm and nm != mid else "") + ".obj"
        write_obj(os.path.join(out, fname), pos[used], nrm[used], uv[used], f2,
                  safe(nm) or safe(mid), zup=zup)
        print(f"  {fname:55s} verts={len(used):6d} tris={len(faces):6d} uv={uvdesc}")
        manifest["meshes"].append(dict(id=mid, name=nm, obj=fname, vertices=int(len(used)),
                                       triangles=int(len(faces)),
                                       position=dict(file=pr["file"], stride=pr["stride"]),
                                       texcoord=(dict(file=tr["file"], stride=tr["stride"]) if tr else None)))
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\n完成 ->", out)

if __name__ == "__main__":
    main()
