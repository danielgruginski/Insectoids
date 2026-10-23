"""Guard for shared spider code: the adult giant spider must build bit for bit as before.

    blender -b --factory-startup --python tools/spider_adult_check.py -- dump <src dir> <out.npz>
    py tools/spider_adult_check.py compare <a.npz> <b.npz>

`dump` rebuilds the adult in an empty file from <src dir> (e.g. a `git worktree` / `git archive` of the last commit, and
the working tree's src) and saves mesh co, faces, UVs, seams, weights, the info attribute, the bone table, every key of
every clip, a 256 data bake and both paints (hunter, pale). `compare` lists any array that differs. Nothing is written
to the repo's textures or export (the paint is not saved).
"""
import sys
try:
    import bpy
except ImportError:
    bpy = None

if bpy is None:
    import numpy as np
    a, b = np.load(sys.argv[2]), np.load(sys.argv[3])
    ka, kb = set(a.files), set(b.files)
    print("only in A:", sorted(ka - kb)[:20]); print("only in B:", sorted(kb - ka)[:20])
    bad = 0
    for k in sorted(ka & kb):
        x, y = a[k], b[k]
        if x.shape != y.shape:
            print("SHAPE", k, x.shape, y.shape); bad += 1; continue
        if x.dtype.kind in "US":
            if not (x == y).all(): print("DIFF", k); bad += 1
            continue
        d = np.abs(x.astype(float) - y.astype(float)).max() if x.size else 0
        if d > 0:
            print(f"DIFF {k} max {d:.3g}"); bad += 1
    print("IDENTICAL" if bad == 0 else f"{bad} differences")
else:
    args = sys.argv[sys.argv.index("--") + 1:]
    src, out = args[1], args[2]
    sys.path.insert(0, src)
    import numpy as np
    import bug_scene, spider_body, bug_rig, spider_paint, spider_anim

    res = {}
    bug_scene.setup_scene("Spider")
    body = spider_body.build_body()
    B = spider_body.rest_bones()
    rig = bug_rig.build_armature(B)
    w = bug_rig.bind(body, rig)
    spider_paint.unwrap(body)
    me = body.data
    co = np.empty(len(me.vertices) * 3, np.float64); me.vertices.foreach_get("co", co); res["co"] = co
    fv = np.array([v for p in me.polygons for v in p.vertices]); res["faces"] = fv
    uv = np.empty(len(me.loops) * 2, np.float64); me.uv_layers.active.data.foreach_get("uv", uv); res["uv"] = uv
    gw = []
    names = [g.name for g in body.vertex_groups]
    for v in me.vertices:
        for g in v.groups:
            gw.append((v.index, names.index(body.vertex_groups[g.group].name), g.weight))
    res["groups"] = np.array(gw); res["group_names"] = np.array(names)
    att = me.color_attributes["info"]; buf = np.empty(len(me.vertices) * 4, np.float32); att.data.foreach_get("color", buf)
    res["info"] = buf
    res["bones"] = np.array([[*h, *[x for r in fr for x in r], L] for n, (h, fr, L, p, d) in B.items()])
    res["bone_names"] = np.array(list(B.keys()))
    res["seams"] = np.array([e.use_seam for e in me.edges])
    # clips
    acts = spider_anim.build_clips()
    for n, a in acts.items():
        vals = []
        for fc in spider_anim._fcurves(a):
            k = np.empty(len(fc.keyframe_points) * 2, np.float64); fc.keyframe_points.foreach_get("co", k)
            vals.append((fc.data_path, fc.array_index, k))
        vals.sort(key=lambda t: (t[0], t[1]))
        res["clip_" + n] = np.concatenate([v[2] for v in vals])
        res["clipdp_" + n] = np.array([f"{v[0]}[{v[1]}]" for v in vals])
        res["clipmeta_" + n] = np.array([a["frames"], int(a["loop"])] + [a[k] for k in sorted(a.keys()) if k.startswith("event_")], float)
    spider_anim.clear()
    # paint from a fixed small bake
    D = spider_paint.bake_data(body, size=256, ao_samples=8)
    for k, v in D.items():
        res["D_" + k] = v
    for var in ("hunter", "pale"):
        col, sm = spider_paint.paint(D, var)
        res["paint_" + var] = col
        res["smooth_" + var] = sm
    res["tris"] = np.array([spider_body.tri_report(body)["total"]])
    np.savez_compressed(out, **res)
    print("DUMPED", out, w, spider_body.tri_report(body))
