"""Headless driver for the spider family (src/spider_build.py, src/spider_eggs.py), in blender/insectoids.blend:

    blender.exe -b --factory-startup blender/insectoids.blend --python tools/spider_family_run.py -- Spiderling build review lowest trace sheets export
    blender.exe -b --factory-startup blender/insectoids.blend --python tools/spider_family_run.py -- Broodmother build review lowest trace sheets export
    blender.exe -b --factory-startup blender/insectoids.blend --python tools/spider_family_run.py -- SpiderEggs props review export
    blender.exe -b --factory-startup blender/insectoids.blend --python tools/spider_family_run.py -- Family lineup nosave

The first word is the target (Spiderling, Broodmother, Spider, SpiderEggs, Family); its scene is put on screen first.
Steps, in the order given: build (model, rig, UVs, texture, clips), body (model, rig and UVs only), clips, review
(bind-pose renders), lowest (lowest vertex per clip), trace (Walk/Run root motion), sheets (clip contact sheets),
export; props (the egg props); lineup (the four from the game camera, in a throwaway scene: use with nosave). The file
is saved compressed afterwards unless 'nosave'. The adult (Spider) builds exactly as before; leave it alone unless its
code changed.
"""
import os, sys, time, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import bpy
import bug_scene, spider_body, spider_anim, spider_build as SB, spider_eggs as SE

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
target, steps = args[0], args[1:]
t0 = time.time()
out = {}
if target not in ("Family",):
    scn = bpy.data.scenes.get(target) or bpy.data.scenes.new(target)
    bug_scene.show_scene(scn)
for st in steps:
    t = time.time()
    if st == "build":
        out[st] = SB.build_all(kind=target)
    elif st == "body":
        out[st] = SB.build_all(kind=target, clips=False)
    elif st == "clips":
        spider_body.use(target)
        out[st] = {n: int(a["frames"]) for n, a in spider_anim.build_clips().items()}
        spider_anim.clear()
    elif st == "review":
        if target == "SpiderEggs":
            out[st] = [bug_scene.shot("EGG_" + c, "eggs_" + c, res=1400) for c in ("CAM_34", "CAM_Top", "CAM_Low", "CAM_Front")]
        else:
            out[st] = SB.review(target)
    elif st == "lowest":
        out[st] = SB.lowest(target)
    elif st == "trace":
        spider_body.use(target)
        out[st] = {c: SB.trace(target, c) for c in spider_anim.family()['moving']}
    elif st == "sheets":
        out[st] = SB.sheets(target)
    elif st == "export":
        out[st] = SE.export_props() if target == "SpiderEggs" else SB.export(target)
    elif st == "props":
        out[st] = SE.build_props()
    elif st == "lineup":
        out[st] = SB.family_lineup()
    elif st == "nosave":
        continue
    else:
        raise SystemExit("unknown step " + st)
    print(f"STEP {st} {time.time() - t:.1f}s", flush=True)
if "nosave" not in steps:
    spider_body.use("Spider")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "blender", "insectoids.blend"), compress=True)
print("RESULT " + json.dumps(out, default=str))
print(f"DONE {time.time() - t0:.1f}s")
