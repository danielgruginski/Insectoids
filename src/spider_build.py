"""Rebuild the spider family from scratch: body -> rig -> UVs -> painted texture -> clips. Run inside Blender with the
kind's scene on screen (bug_scene.show_scene first, in a separate call; tools/spider_family_run.py does it headless).

    build_all()                         the adult giant spider (scene Spider), exactly as before the family
    build_all(kind="Spiderling")        scene Spiderling, T_Spiderling (512)
    build_all(kind="Broodmother")       scene Broodmother, T_Broodmother (1024)
    spider_eggs.build_props()           scene SpiderEggs: SpiderEgg_Clutch / _Single / _Hatched, T_SpiderEggs (512)
    export(kind)                        export/<Kind>.fbx, export/Anims/<Kind>@<clip>.fbx + <kind>_clips.json

The review helpers (review, lowest, sheets, trace, family_lineup) write to renders/.
"""
import bpy, importlib, math, os
import numpy as np
from mathutils import Vector
import bug_common, bug_scene, spider_eggs, spider_body, bug_rig, spider_paint, spider_anim, bug_export

# per kind: texture size, paint variants (first = its own, on M_<Kind>), camera framing (x the adult's)
SETUP = {
    "Spider": dict(tex=1024, variants=("hunter", "pale"), cam=1.0),
    "Spiderling": dict(tex=512, variants=("juvenile",), cam=0.32),
    "Broodmother": dict(tex=1024, variants=("brood",), cam=1.9),
}


def reload_all():
    for m in (bug_common, bug_scene, spider_eggs, spider_body, bug_rig, spider_paint, spider_anim, bug_export):
        importlib.reload(m)


def build_all(tex=None, clips=True, variants=None, kind="Spider"):
    K = spider_body.use(kind)
    st = SETUP[K.name]
    scn = bug_scene.setup_scene(K.name, prefix=K.cams, scale=st['cam'])
    assert bpy.context.scene == scn, f"put scene {K.name} on screen first (bug_scene.show_scene)"
    body = spider_body.build_body()
    rig = bug_rig.build_armature(spider_body.rest_bones(), name=K.rig, coll_name=K.key + "_Rig")
    report = {"weights": bug_rig.bind(body, rig), "tris": spider_body.tri_report(body)}
    stray = [g.name for g in body.vertex_groups if g.name not in rig.data.bones]
    assert not stray, f"vertex groups that match no bone: {stray}"
    spider_paint.unwrap(body)
    layout = "uv_layout" if K.name == "Spider" else K.name.lower() + "_uv_layout"
    if not bpy.app.background:
        report["uv_layout"] = spider_paint.uv_layout(body, name=layout)
    report["textures"], report["coverage"] = spider_paint.build_texture(body, size=tex or st['tex'],
                                                                         variants=variants or st['variants'])
    if bpy.app.background:                                  # headless: drawn over the painted texture
        report["uv_layout"] = spider_paint.uv_layout(body, name=layout, texture=bpy.data.images[spider_paint.texture_name(st['variants'][0] if not variants else variants[0])])
    if clips:
        report["clips"] = {n: int(a["frames"]) for n, a in spider_anim.build_clips().items()}
        spider_anim.clear()
    return report


def export(kind="Spider"):
    K = spider_body.use(kind)
    fam = spider_anim.family()
    return ([bug_export.export_model(spider_anim, K.rig, [K.body], K.name)] +
            bug_export.export_clips(spider_anim, K.rig, K.name, moving=set(fam['moving']), names=spider_anim.clip_names()))


# ----------------------------------------------------------------------------------------- review
R = bug_scene.RENDERS


def review(kind, res=1400, cams=("CAM_34", "CAM_Side", "CAM_Front", "CAM_Top", "CAM_Face", "CAM_Low")):
    """Bind-pose renders (Workbench, texture colour) from the kind's cameras."""
    K = spider_body.use(kind)
    spider_anim.clear()
    return [bug_scene.shot(K.cams + c, f"{K.name.lower()}_{c}", res=res) for c in cams]


def _eval_min_z(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    e = ob.evaluated_get(dg)
    me = e.to_mesh()
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    e.to_mesh_clear()
    co = co.reshape(-1, 3) @ np.array(ob.matrix_world)[:3, :3].T + np.array(ob.matrix_world)[:3, 3]
    i = int(co[:, 2].argmin())
    return float(co[i, 2]), i


def lowest(kind, step=1):
    """Lowest vertex of the deformed mesh per clip: (min z in m, frame, vertex group of that vertex)."""
    K = spider_body.use(kind)
    ob = bpy.data.objects[K.body]
    rig = bpy.data.objects[K.rig]
    out = {}
    scn = bpy.context.scene
    for clip in spider_anim.clip_names():
        spider_anim.use(clip, rig)
        best = (9.0, 0, 0)
        for f in range(0, int(bpy.data.actions[spider_anim.action_name(clip)]["frames"]) + 1, step):
            scn.frame_set(f)
            z, i = _eval_min_z(ob)
            if z < best[0]:
                best = (z, f, i)
        v = ob.data.vertices[best[2]]
        g = max(v.groups, key=lambda g: g.weight).group if len(v.groups) else -1
        out[clip] = (round(best[0], 4), best[1], ob.vertex_groups[g].name if g >= 0 else "")
    spider_anim.clear(rig)
    scn.frame_set(0)
    return out


def sheets(kind, clips=None, n=7, res=520):
    K = spider_body.use(kind)
    rig = bpy.data.objects[K.rig]
    out = []
    for clip in clips or spider_anim.clip_names():
        spider_anim.use(clip, rig)
        N = int(bpy.data.actions[spider_anim.action_name(clip)]["frames"])
        frames = [round(N * i / (n - 1)) for i in range(n)]
        out.append(bug_scene.render_sheet(clip, frames, cams=(K.cams + "CAM_Side", K.cams + "CAM_34"), rig_name=K.rig,
                                          res=res, out=f"sheet_{K.name.lower()}_{clip}"))
    spider_anim.clear(rig)
    return out


def trace(kind, clip="Walk", loops=2):
    """Root-motion check of a moving loop: the skeleton must stay in place (Root fixed, Body only bobbing, no jump at
    the loop), Motion must travel the stride each loop, and planted feet must not slide in the world (skeleton foot +
    Motion travel)."""
    K = spider_body.use(kind)
    rig = bpy.data.objects[K.rig]
    spider_anim.use(clip, rig)
    act = bpy.data.actions[spider_anim.action_name(clip)]
    N = int(act["frames"])
    fps = spider_anim.clip_fps()
    scn = bpy.context.scene
    pb = rig.pose.bones
    tips = {}
    rows = []
    for f in range(N + 1):
        scn.frame_set(f)
        mot = rig.matrix_world @ pb["Motion"].head
        root = rig.matrix_world @ pb["Root"].head
        body = rig.matrix_world @ pb["Body"].head
        feet = {}
        for s, i in spider_anim.LEG_KEYS:
            b = pb[spider_body.leg_name(i, s, "Tarsus")]
            feet[(s, i)] = rig.matrix_world @ b.tail
        rows.append((f, mot.copy(), root.copy(), body.copy(), feet))
    m0, mN = rows[0][1], rows[-1][1]
    stride = (mN - m0).length
    slide = 0.0
    for k in feet:
        for a, b in zip(rows[:-1], rows[1:]):
            wa = a[4][k] + a[1]                             # world = skeleton (in place) + Motion's travel
            wb = b[4][k] + b[1]
            if a[4][k].z < K.foot_z + 0.01 * K.size and b[4][k].z < K.foot_z + 0.01 * K.size:
                slide = max(slide, (wb - wa).length * fps)
    body_jump = (rows[-1][3] - rows[0][3]).length
    root_move = max((r[2] - rows[0][2]).length for r in rows)
    spider_anim.clear(rig)
    scn.frame_set(0)
    return dict(frames=N, fps=fps, stride=round(stride, 4), speed=round(stride / (N / fps), 3),
                dir=tuple(round(c, 3) for c in (mN - m0).normalized()), root_moves=round(root_move, 5),
                body_loop_jump=round(body_jump, 5), planted_slide_mps=round(slide, 4))


def family_lineup(res=(1920, 1080)):
    """The four next to each other in a throwaway scene (don't save after this): the egg clutch, the spiderling, the
    adult and the broodmother, from the game camera (22 m, 50 deg pitch, vertical fov 30) and closer."""
    scn = bpy.data.scenes.get("_Family") or bpy.data.scenes.new("_Family")
    bug_scene.show_scene(scn)
    bug_scene.add_lights(scn)
    bug_scene.add_ground(scn)
    g = bpy.data.objects["Ground"]
    g.scale = (3, 3, 1)
    place = [("SpiderEgg_Clutch", None, -5.6), ("SpiderlingRig", "SpiderlingBody", -4.1), ("SpiderRig", "SpiderBody", -1.2),
             ("BroodmotherRig", "BroodmotherBody", 3.9)]
    for rig_name, body_name, x in place:
        ob = bpy.data.objects[rig_name]
        for o in (ob, bpy.data.objects.get(body_name) if body_name else None):
            if o is not None and o.name not in scn.collection.objects:
                scn.collection.objects.link(o)
        ob.location = (x, 0, 0)
        ob.rotation_euler = (0, 0, math.radians(28))
        if ob.type == 'ARMATURE' and ob.animation_data:
            ob.animation_data.action = None
            bug_rig.reset_pose(ob)
    for ob in (bpy.data.objects["SpiderEgg_Single"], bpy.data.objects["SpiderEgg_Hatched"]):
        if ob.name not in scn.collection.objects:
            scn.collection.objects.link(ob)
    bpy.data.objects["SpiderEgg_Single"].location = (-6.1, -0.9, 0)
    bpy.data.objects["SpiderEgg_Hatched"].location = (-5.1, -1.0, 0)
    out = []
    target = Vector((-0.6, 0, 0.5))
    for name, dist in (("family_game_22m", 22.0), ("family_game_12m", 12.0)):
        cam = bpy.data.objects.get("CAM_Game") or bpy.data.objects.new("CAM_Game", bpy.data.cameras.new("CAM_Game"))
        if cam.name not in scn.collection.objects:
            scn.collection.objects.link(cam)
        p = math.radians(50)
        cam.location = target + Vector((0, -dist * math.cos(p), dist * math.sin(p)))
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
        cam.data.type = 'PERSP'
        cam.data.sensor_fit = 'VERTICAL'
        cam.data.angle_y = math.radians(30)
        cam.data.clip_end = 300
        out.append(bug_scene.shot("CAM_Game", name, res=res[0], res_y=res[1], scene=scn))
    return out
