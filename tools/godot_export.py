"""Headless glTF export of the insectoids for the Godot pack (src/bug_gdx.py):

    blender.exe -b --factory-startup blender/insectoids.blend --python tools/godot_export.py -- spider spiderling broodmother wasp centipede eggs

Each creature runs its build module's own export() (spider_build.export(kind), wasp_build, centipede_build) with the
FBX writer swapped for bug_gdx.export_glb, so rig, meshes, clips and root motion are the ones Unity gets; "eggs" exports
the egg props (spider_eggs.PROPS). Nothing is saved.
"""
import os, sys, json, time, importlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import bug_export, bug_gdx

SPIDERS = {"spider": "Spider", "spiderling": "Spiderling", "broodmother": "Broodmother"}


def via_build(name):
    cap = {}

    def model(anim, rig_name, meshes, name):
        cap.update(anim=anim, rig=rig_name, meshes=tuple(meshes), name=name)
        return ""

    def clips(anim, rig_name, name, moving=(), names=None):
        cap.update(moving=set(moving), names=list(names) if names else None)
        return []

    real = bug_export.export_model, bug_export.export_clips
    bug_export.export_model, bug_export.export_clips = model, clips
    try:
        if name in SPIDERS:
            importlib.import_module("spider_build").export(SPIDERS[name])
        else:
            importlib.import_module(name + "_build").export()
    finally:
        bug_export.export_model, bug_export.export_clips = real
    return bug_gdx.export_glb(cap["anim"], cap["rig"], cap["meshes"], cap["name"], cap["moving"], cap["names"])


args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not args:
    raise SystemExit("usage: godot_export.py -- <creature|eggs> ...")
for a in args:
    t = time.time()
    if a == "eggs":
        files = bug_gdx.export_props(importlib.import_module("spider_eggs").PROPS)
    else:
        files = via_build(a.lower())
    print("GDXCREATURE " + json.dumps({"creature": a, "seconds": round(time.time() - t, 1),
                                       "files": [os.path.basename(f) for f in files]}), flush=True)
