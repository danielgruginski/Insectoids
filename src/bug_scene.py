"""Scene, cameras, lights and review renders for the insectoid file (adapted from Goblins/src/gob_scene.py)."""
import bpy, math, os
from mathutils import Vector
from bug_common import ROOT

RENDERS = os.path.join(ROOT, "renders")


def setup_scene(name="Spider", prefix="", lift=0.0, scale=1.0):
    """The creature's scene (created if missing), its cameras (named prefix + CAM_*, aimed `lift` metres higher for
    fliers, framed for a creature `scale` times the adult spider's size), the shared lights and ground."""
    scn = bpy.data.scenes.get(name) or bpy.data.scenes.new(name)
    scn.unit_settings.system = 'METRIC'
    scn.view_settings.view_transform = 'Standard'
    scn.render.resolution_x = 1000
    scn.render.resolution_y = 1000
    scn.render.fps = 30
    add_cameras(scn, prefix, lift, scale)
    add_lights(scn)
    add_ground(scn)
    return scn


def _cam(scn, name, loc, target, ortho=None, lens=85):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    if cam.name not in scn.collection.objects:
        scn.collection.objects.link(cam)
    cam.location = loc
    d = Vector(target) - Vector(loc)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if ortho:
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = ortho
    else:
        cam.data.type = 'PERSP'
        cam.data.lens = lens
    cam.data.clip_start = 0.01
    cam.data.clip_end = 200
    return cam


def add_cameras(scn, prefix="", lift=0.0, scale=1.0):
    k = scale
    up = lambda v: (v[0] * k, v[1] * k, v[2] * k + lift) if k != 1.0 else (v[0], v[1], v[2] + lift)
    _cam(scn, prefix + "CAM_Front", up((0, -8, 0.6)), up((0, 0, 0.6)), ortho=3.6 * k)
    _cam(scn, prefix + "CAM_Side", up((8, 0, 0.6)), up((0, 0, 0.6)), ortho=3.6 * k)
    _cam(scn, prefix + "CAM_Top", (0, 0, 8 * k + lift), (0, 0.0001, 0), ortho=3.8 * k)
    _cam(scn, prefix + "CAM_34", up((3.6, -4.6, 2.7)), up((0, -0.1, 0.45)), lens=55)
    _cam(scn, prefix + "CAM_Face", up((0.9, -2.1, 1.05)), up((0, -0.62, 0.58)), lens=70)
    _cam(scn, prefix + "CAM_Low", up((2.2, -2.9, 0.35)), up((0, -0.2, 0.55)), lens=40)
    _cam(scn, prefix + "CAM_Colony", (0, -26, 31), (0, 0, 0.4 + lift), lens=300)   # ~40 m at 50 deg pitch
    if scn.camera is None:
        scn.camera = bpy.data.objects[prefix + "CAM_34"]


def add_lights(scn):
    for name, energy, rot in (("KEY", 3.5, (50, 0, 35)), ("FILL", 1.0, (60, 0, -140))):
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, bpy.data.lights.new(name, 'SUN'))
        if ob.name not in scn.collection.objects:
            scn.collection.objects.link(ob)
        ob.data.energy = energy
        ob.rotation_euler = tuple(math.radians(a) for a in rot)
    w = scn.world or bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scn.world = w
    w.use_nodes = True
    bg = next(n for n in w.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs[0].default_value = (0.32, 0.34, 0.38, 1)
    bg.inputs[1].default_value = 0.6


def add_ground(scn, size=12.0):
    """A dirt-coloured ground disc so stance and foot contact read in the viewport (not exported)."""
    import bmesh
    ob = bpy.data.objects.get("Ground")
    if ob is None:
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=True, segments=64, radius=size / 2)
        me = bpy.data.meshes.new("Ground")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new("Ground", me)
        m = bpy.data.materials.get("M_Ground") or bpy.data.materials.new("M_Ground")
        m.use_nodes = True
        bsdf = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        bsdf.inputs['Base Color'].default_value = (0.20, 0.17, 0.12, 1)
        bsdf.inputs['Roughness'].default_value = 1.0
        m.diffuse_color = (0.20, 0.17, 0.12, 1)
        me.materials.append(m)
        ob.hide_select = True
    if ob.name not in scn.collection.objects:
        scn.collection.objects.link(ob)
    return ob


def shot(cam="CAM_34", name=None, engine='BLENDER_WORKBENCH', res=1000, scene=None, color='TEXTURE', frame=None,
         res_y=None):
    scn = scene or bpy.context.scene
    prev_cam, prev_engine = scn.camera, scn.render.engine
    scn.camera = bpy.data.objects[cam]
    if frame is not None:
        scn.frame_set(frame)
    try:
        scn.render.engine = engine
    except TypeError:
        scn.render.engine = 'BLENDER_WORKBENCH'
    if scn.render.engine == 'BLENDER_WORKBENCH':
        sh = scn.display.shading
        sh.light = 'STUDIO'
        sh.color_type = color
        sh.show_cavity = True
        sh.cavity_type = 'WORLD'
        sh.show_shadows = False
        sh.show_object_outline = False
    scn.render.resolution_x = res
    scn.render.resolution_y = res_y or res
    scn.render.film_transparent = False
    os.makedirs(RENDERS, exist_ok=True)
    path = os.path.join(RENDERS, (name or cam) + ".png")
    scn.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=scn.name)
    scn.camera, scn.render.engine = prev_cam, prev_engine
    return path


def show_scene(scn):
    """Put the scene on Daniel's screen."""
    bpy.context.window_manager.windows[0].scene = scn


def frame_viewports(obj_names=None, shading='MATERIAL', lift=0.0):
    """Point every 3D viewport at the spider from the 3/4 view, in material preview."""
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.shading.type = shading
                    r3 = sp.region_3d
                    r3.view_location = Vector((0, -0.1, 0.45 + lift))
                    r3.view_distance = 5.5
                    r3.view_rotation = Vector((3.6, -4.6, 2.7 - 0.45)).normalized().to_track_quat('Z', 'Y')
                    r3.view_perspective = 'PERSP'


def render_sheet(name, frames, cams=("CAM_Side",), rig_name="SpiderRig", res=360, follow=True, color='TEXTURE',
                 scene=None, out=None):
    """Render clip frames (rows = cameras, columns = frames) into one PNG in renders/. With follow, cameras move
    with the Root bone so root-motion clips stay in frame."""
    import numpy as np
    scn = scene or bpy.context.scene
    rig = bpy.data.objects[rig_name]
    tiles = []
    tmp = os.path.join(RENDERS, "_tile.png")
    for cam_name in cams:
        cam = bpy.data.objects[cam_name]
        home = cam.location.copy()
        row = []
        for f in frames:
            scn.frame_set(f)
            if follow:
                off = rig.matrix_world @ rig.pose.bones["Root"].head    # clips play in place (Motion travels)
                cam.location = home + Vector((off.x, off.y, 0))
            shot(cam_name, "_tile", res=res, scene=scn, color=color)
            img = bpy.data.images.load(tmp, check_existing=False)
            a = np.array(img.pixels[:], dtype=np.float32).reshape(res, res, 4)
            bpy.data.images.remove(img)
            row.append(a)
        cam.location = home
        tiles.append(np.concatenate(row, axis=1))
    sheet = np.concatenate(tiles[::-1], axis=0)          # image rows are bottom-up
    h, w = sheet.shape[:2]
    img = bpy.data.images.new("_sheet", w, h, alpha=True)
    img.pixels.foreach_set(sheet.ravel())
    path = os.path.join(RENDERS, (out or ("sheet_" + name)) + ".png")
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    return path
