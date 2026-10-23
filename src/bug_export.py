"""FBX export for Unity (settings as the goblins': -Z forward / Y up, FBX_SCALE_ALL, deform bones only).

Per creature (Spider, Spiderling, Broodmother, Wasp, Centipede; the egg props: spider_eggs.export_props):
export/<Name>.fbx                   rig + meshes, bind pose (Generic rig in Unity, faces +Z)
export/Anims/<Name>@<Clip>.fbx      the skeleton with one baked take each
export/Anims/<name>_clips.json      {clips: [{name, frames, fps, loop, rootMotion, events: [{name, time}]}]} (read by
                                    the Unity setup)
The animation module passed in (spider_anim, wasp_anim) provides CLIPS, FPS (or clip_fps()), use(name, rig), clear(rig).
"""
import bpy, json, os
from bug_common import ROOT

EXPORT = os.path.join(ROOT, "export")

FBX = dict(apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', use_armature_deform_only=True,
           add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X', armature_nodetype='NULL',
           bake_anim=False, mesh_smooth_type='FACE', use_mesh_modifiers=True, use_custom_props=True,
           path_mode='STRIP', embed_textures=False)


def _select(objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_model(anim, rig_name, meshes, name):
    os.makedirs(EXPORT, exist_ok=True)
    rig = bpy.data.objects[rig_name]
    objs = [bpy.data.objects[m] for m in meshes]
    hidden = rig.hide_get()
    anim.clear(rig)
    _select([rig] + objs)
    path = os.path.join(EXPORT, name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE', 'MESH'}, **FBX)
    for o in [rig] + objs:
        o.select_set(False)
    rig.hide_set(hidden)
    return path


def export_clips(anim, rig_name, name, moving=(), names=None):
    os.makedirs(os.path.join(EXPORT, "Anims"), exist_ok=True)
    rig = bpy.data.objects[rig_name]
    hidden = rig.hide_get()
    scn = bpy.context.scene
    keep = (scn.frame_start, scn.frame_end, scn.render.fps)
    meta, written = [], []
    try:
        for clip in names or anim.CLIPS:
            act = bpy.data.actions[anim.action_name(clip) if hasattr(anim, "action_name") else clip]
            anim.use(clip, rig)
            fps = anim.clip_fps() if hasattr(anim, "clip_fps") else anim.FPS
            scn.render.fps = fps
            _select([rig])
            path = os.path.join(EXPORT, "Anims", f"{name}@{clip}.fbx")
            opts = dict(FBX)
            opts.update(bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
                        bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0,
                        bake_anim_simplify_factor=0.0)
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE'}, **opts)
            written.append(path)
            meta.append({
                "name": clip, "frames": int(act["frames"]), "fps": fps, "loop": bool(act["loop"]),
                "rootMotion": clip in moving,
                "events": [{"name": k[len("event_"):], "time": float(act[k])} for k in act.keys() if k.startswith("event_")],
            })
    finally:
        scn.frame_start, scn.frame_end, scn.render.fps = keep
        anim.clear(rig)
        rig.select_set(False)
        rig.hide_set(hidden)
    with open(os.path.join(EXPORT, "Anims", f"{name.lower()}_clips.json"), "w", encoding="utf-8") as f:
        json.dump({"clips": meta}, f, indent=1)          # a list, so Unity's JsonUtility can read it
    return written


def export_spider():
    import spider_anim, spider_body, bug_rig
    spider_body.use("Spider")
    return ([export_model(spider_anim, bug_rig.RIG, ["SpiderBody"], "Spider")] +
            export_clips(spider_anim, bug_rig.RIG, "Spider", moving={"Walk", "Run"}))


def export_all():
    """Kept for the spider's README command."""
    return export_spider()
