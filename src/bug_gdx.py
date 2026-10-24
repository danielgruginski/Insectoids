"""glTF export for Godot (2026-10-24: the creatures pack for Godot; the FBX path for Unity is bug_export):

export/godot/<Name>/<Name>.glb          the rig and its meshes in the bind pose, every clip an animation named after it
                                        (each clip's action on an NLA track of its own while exporting:
                                        export_animation_mode NLA_TRACKS, sampled every frame)
export/godot/<Name>/<name>_clips.json   per clip: frames, fps, loop, root motion, events (name, time in seconds), as the
                                        FBX path's
export/godot/<Name>/T_*.png             the creature's textures
export/godot/SpiderEggs/<prop>.glb      the egg props (no rig), each with its origin on the ground under its middle

glTF is +Y up with the model's front +Z (Godot's), metres; every bone goes; materials by name only (the pack builds its
own). tools/install_to_godot.py copies export/godot into the pack's project (res://insectoids/). Same as the Beasts
repo's beast_gdx.
"""
import bpy, json, os, shutil
from mathutils import Matrix
from bug_common import ROOT

GODOT = os.path.join(ROOT, "export", "godot")

GLTF = dict(export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_skins=True,
            export_def_bones=False, export_rest_position_armature=True, export_morph=True, export_morph_normal=False,
            export_morph_tangent=False, export_materials="EXPORT", export_image_format="NONE", export_extras=True,
            export_animations=True, export_animation_mode="NLA_TRACKS", export_force_sampling=True,
            export_frame_step=1, export_anim_slide_to_zero=True, export_optimize_animation_size=False,
            export_reset_pose_bones=True, export_anim_single_armature=True)


def _select(objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def _textures(name, out):
    tex = os.path.join(ROOT, "textures")
    written = []
    for fn in sorted(os.listdir(tex)):
        if fn.endswith(".png") and (fn == f"T_{name}.png" or fn.startswith(f"T_{name}_")):   # not T_Spiderling for T_Spider
            shutil.copy2(os.path.join(tex, fn), os.path.join(out, fn))
            written.append(os.path.join(out, fn))
    return written


def export_glb(anim, rig_name, meshes, name, moving=(), names=None):
    """anim: the clip module (CLIPS, FPS or clip_fps(), action_name or the clip as the action's name, clear)"""
    out = os.path.join(GODOT, name)
    os.makedirs(out, exist_ok=True)
    rig = bpy.data.objects[rig_name]
    objs = [bpy.data.objects[m] for m in meshes]
    scn = rig.users_scene[0]
    win = bpy.context.window
    prev_scene = win.scene if win else None
    if win: win.scene = scn
    hidden = rig.hide_get()
    keep = (scn.frame_start, scn.frame_end, scn.render.fps, scn.frame_current)
    fps = anim.clip_fps() if hasattr(anim, "clip_fps") else anim.FPS
    rig.animation_data_create()
    ad = rig.animation_data
    old_action = ad.action
    old_tracks = [(t, t.mute) for t in ad.nla_tracks]
    tracks, meta = [], []
    path = os.path.join(out, name + ".glb")
    try:
        anim.clear(rig)
        ad.action = None
        for t, _ in old_tracks: t.mute = True
        for pb in rig.pose.bones: pb.matrix_basis = Matrix.Identity(4)
        scn.render.fps = fps
        for clip in (names or anim.CLIPS):
            act = bpy.data.actions[anim.action_name(clip) if hasattr(anim, "action_name") else clip]
            tr = ad.nla_tracks.new()
            tr.name = clip
            st = tr.strips.new(clip, int(act.frame_range[0]), act)
            if hasattr(st, "action_slot") and len(getattr(act, "slots", [])) > 0:
                st.action_slot = act.slots[0]            # Blender 4.4: a strip plays nothing without its slot
            tracks.append(tr)
            meta.append({
                "name": clip, "frames": int(act["frames"]), "fps": fps, "loop": bool(act["loop"]),
                "rootMotion": clip in moving,
                "events": [{"name": k[len("event_"):], "time": float(act[k])} for k in act.keys() if k.startswith("event_")],
            })
        bpy.context.view_layer.update()
        _select([rig] + objs)
        bpy.ops.export_scene.gltf(filepath=path, use_active_scene=True, **GLTF)
    finally:
        for tr in tracks: ad.nla_tracks.remove(tr)
        for t, m in old_tracks: t.mute = m
        ad.action = old_action
        scn.frame_start, scn.frame_end, scn.render.fps = keep[:3]
        scn.frame_set(keep[3])
        for o in [rig] + objs: o.select_set(False)
        rig.hide_set(hidden)
        if win and prev_scene is not None: win.scene = prev_scene
    written = [path]
    with open(os.path.join(out, f"{name.lower()}_clips.json"), "w", encoding="utf-8") as f:
        json.dump({"clips": meta}, f, indent=1)
    written.append(f.name)
    return written + _textures(name, out)


def export_props(props, folder="SpiderEggs", tex="SpiderEggs"):
    """the egg props: one .glb each, its origin on the ground under its middle (as spider_eggs.export_props)"""
    out = os.path.join(GODOT, folder)
    os.makedirs(out, exist_ok=True)
    written = []
    for n in props:
        ob = bpy.data.objects[n]
        scn = ob.users_scene[0]
        win = bpy.context.window
        prev = win.scene if win else None
        if win: win.scene = scn
        keep = ob.location.copy()
        ob.location = (0, 0, 0)
        bpy.context.view_layer.update()
        _select([ob])
        path = os.path.join(out, n + ".glb")
        opts = dict(GLTF, export_animations=False, export_skins=False)
        bpy.ops.export_scene.gltf(filepath=path, use_active_scene=True, **opts)
        ob.select_set(False)
        ob.location = keep
        if win and prev is not None: win.scene = prev
        written.append(path)
    return written + _textures(tex, out)
