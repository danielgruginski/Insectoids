"""UVs and the hand-painted texture of the spider.

UVs: every part was cut open by its builder (lofts along the belly or the underside of the leg, cones up one side;
eye domes are disks), so a plain angle-based unwrap unfolds each part as one piece. Islands are brought to one
texel density, the face, eyes, fangs and abdomen get more texels, then everything is packed.

Texture: painted per texel, not per vertex. Cycles bakes the texel's rest position, normal, part id (+ position
along the segment) and ambient occlusion into float images; numpy then paints colours, markings, hair streaks and
lighting from those. Alpha holds smoothness (URP Lit: Smoothness Source = Albedo Alpha): glossy eyes and fangs,
satin carapace, matte hair.
"""
import bpy, bmesh, math, os
import numpy as np
from mathutils import Vector
from bug_common import ROOT, smoothstep, fill_gutters, fbm, vnoise, hexc, srgb_to_lin, lin_to_srgb
import spider_body as SB

TEX_DIR = os.path.join(ROOT, "textures")
UV_SCALE = {SB.PART['eye_big']: 2.6, SB.PART['eye_small']: 2.2, SB.PART['fang']: 1.8, SB.PART['chelicera']: 1.5,
            SB.PART['carapace']: 1.5, SB.PART['abdomen']: 1.5, SB.PART['palp']: 1.1, SB.PART['spine']: 0.6,
            SB.PART['spinneret']: 0.8, SB.PART['pedicel']: 0.7}


def _part_per_vertex(me):
    att = me.color_attributes["info"]
    buf = np.empty(len(me.vertices) * 4, dtype=np.float32)
    att.data.foreach_get('color', buf)
    return np.rint(buf.reshape(-1, 4)[:, 0] * 255).astype(int)


def unwrap(ob, margin=0.0035, scales=None):
    """scales: part id -> texel density factor (default: the spider's UV_SCALE)."""
    scales = UV_SCALE if scales is None else scales
    vl = bpy.context.view_layer
    for o in bpy.context.selected_objects:
        o.select_set(False)
    vl.objects.active = ob
    ob.select_set(True)
    part = _part_per_vertex(ob.data)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin=0.0)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:
        k = scales.get(int(part[f.verts[0].index]), 1.0)
        if k != 1.0:
            for l in f.loops:
                l[uv].uv *= k
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(margin=margin, rotate=True)
    bpy.ops.object.mode_set(mode='OBJECT')


def uv_layout(ob, name="uv_layout", size=2048):
    vl = bpy.context.view_layer
    for o in bpy.context.selected_objects:
        o.select_set(False)
    vl.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    path = os.path.join(ROOT, "renders", name + ".png")
    bpy.ops.uv.export_layout(filepath=path, size=(size, size), opacity=0.25, export_all=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    return path


# ----------------------------------------------------------------------------------------- data bakes
def _bake_setup(ob, image_name, size, emit_builder=None):
    img = bpy.data.images.get(image_name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(image_name, size, size, alpha=True, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    m = bpy.data.materials.get("_SPD_Bake") or bpy.data.materials.new("_SPD_Bake")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    if emit_builder is not None:
        em = nt.nodes.new('ShaderNodeEmission')
        nt.links.new(emit_builder(nt), em.inputs['Color'])
        nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    else:
        bs = nt.nodes.new('ShaderNodeBsdfDiffuse')
        nt.links.new(bs.outputs['BSDF'], out.inputs['Surface'])
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    nt.nodes.active = tex
    ob.data.materials.clear()
    ob.data.materials.append(m)
    return img


def _read(img):
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def bake_data(ob, size=1024, ao_samples=96, ao_dist=0.35):
    """Rest position, normal, info (part, t, u) and AO per texel. Returns dict of arrays (h, w, ...)."""
    scn = bpy.context.scene
    prev_engine = scn.render.engine
    scn.render.engine = 'CYCLES'
    try:
        scn.cycles.device = 'GPU'
    except Exception:
        pass
    arm = [m for m in ob.modifiers if m.type == 'ARMATURE']
    for m in arm:
        m.show_render = m.show_viewport = False
    hidden = {o.name: o.hide_render for o in scn.objects}
    for o in scn.objects:
        o.hide_render = o is not ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.hide_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    old = list(ob.data.materials)
    out = {}

    def geo(nt, socket, add=None, mul=None):
        g = nt.nodes.new('ShaderNodeNewGeometry')
        v = g.outputs[socket]
        if mul is not None:
            n = nt.nodes.new('ShaderNodeVectorMath')
            n.operation = 'MULTIPLY'
            n.inputs[1].default_value = mul
            nt.links.new(v, n.inputs[0])
            v = n.outputs[0]
        if add is not None:
            n = nt.nodes.new('ShaderNodeVectorMath')
            n.operation = 'ADD'
            n.inputs[1].default_value = add
            nt.links.new(v, n.inputs[0])
            v = n.outputs[0]
        return v

    def attr(nt):
        a = nt.nodes.new('ShaderNodeAttribute')
        a.attribute_name = "info"
        return a.outputs['Color']

    scn.cycles.samples = 1
    for key, builder in (("pos", lambda nt: geo(nt, 'Position', add=(2, 2, 2))),
                         ("nrm", lambda nt: geo(nt, 'Normal', mul=(0.5, 0.5, 0.5), add=(0.5, 0.5, 0.5))),
                         ("info", attr)):
        img = _bake_setup(ob, "_SPD_" + key, size, builder)
        bpy.ops.object.bake(type='EMIT', margin=6, use_clear=True)
        out[key] = _read(img)
    w = scn.world
    w.light_settings.distance = ao_dist
    scn.cycles.samples = ao_samples
    img = _bake_setup(ob, "_SPD_ao", size, None)
    bpy.ops.object.bake(type='AO', margin=6, use_clear=True)
    out["ao"] = _read(img)[..., 0]
    ob.data.materials.clear()
    for m in old:
        ob.data.materials.append(m)
    for m in arm:
        m.show_render = m.show_viewport = True
    for o in scn.objects:
        o.hide_render = hidden.get(o.name, o.hide_render)
    scn.render.engine = prev_engine
    P = out["pos"][..., :3] - 2.0
    valid = out["pos"][..., :3].sum(-1) > 0.5
    N = out["nrm"][..., :3] * 2 - 1
    N /= np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-6)
    return dict(P=P, N=N, part=np.rint(out["info"][..., 0] * 255).astype(int), t=out["info"][..., 1],
                u=out["info"][..., 2] * 2 - 1, ao=out["ao"], valid=valid)


# ----------------------------------------------------------------------------------------- painting
PAL = {
    'dark': hexc('#2b2118'), 'brown': hexc('#4c3824'), 'tan': hexc('#8f7049'), 'pale': hexc('#b8a078'),
    'bone': hexc('#dcd0ae'), 'bone_dark': hexc('#a89a78'), 'socket': hexc('#130d09'), 'belly': hexc('#221c17'),
    'rust': hexc('#8e421c'), 'rust_light': hexc('#b8652c'), 'fang': hexc('#1a0e0b'), 'fang_tip': hexc('#4a1a10'),
    'eye': hexc('#0b0909'), 'eyeshine': hexc('#3f5a3c'), 'scopula': hexc('#16120e'),
}


def _mix(a, b, t):
    t = np.clip(np.asarray(t, float), 0, 1)[..., None]
    return a * (1 - t) + np.asarray(b) * t


def _leg_local(P, part, side_x):
    """Bone-local coordinates of texels on leg segments (and palps), for streaks along each segment."""
    B = SB.rest_bones()
    loc = np.zeros_like(P)
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        for i in range(4):
            for j, seg in enumerate(SB.SEG_NAMES):
                m = (part == SB.PART['leg'] + 5 * i + j) & ((side_x > 0) == (side > 0))
                if not m.any():
                    continue
                h, fr, L, _, _ = B[SB.leg_name(i, side, seg)]
                Rm = np.array(fr)
                loc[m] = (P[m] - np.array(h)) @ Rm
    return loc


def paint(D, variant="hunter"):
    P, N, part, t, u, ao, valid = D['P'], D['N'], D['part'], D['t'], D['u'], D['ao'], D['valid']
    H, W = part.shape
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    ax = np.abs(x)
    col = np.tile(PAL['dark'], (H, W, 1)).astype(float)
    smooth = np.full((H, W), 0.2)
    lift = SB.LIFT
    is_leg = part >= SB.PART['leg']
    seg = np.where(is_leg, (part - SB.PART['leg']) % 5, -1)
    n_big = fbm(P * 7.0, 3, seed=11)
    n_mid = fbm(P * 22.0, 3, seed=12)

    # ---------------------------------------------------------------- legs
    loc = _leg_local(P, part, x)
    streak = fbm(loc * np.array([140.0, 9.0, 140.0]), 3, seed=21)            # hair running along each segment
    fine = vnoise(loc * np.array([320.0, 26.0, 320.0]), seed=22)
    leg_base = _mix(np.tile(PAL['brown'], (H, W, 1)), PAL['dark'], 0.55 + 0.35 * n_big)
    leg_base = _mix(leg_base, PAL['dark'], np.clip(-u, 0, 1) * 0.55)          # darker underneath
    band = np.zeros((H, W))
    for s_i in (1, 2, 3):                                                     # pale ring at the far end of femur, tibia, metatarsus
        band = np.maximum(band, (seg == s_i) * smoothstep(0.80, 0.9, t))
    band = np.maximum(band, (seg == 2) * smoothstep(0.26, 0.16, t) * 0.75)    # the patella knob
    band = np.maximum(band, (seg == 0) * smoothstep(0.7, 1.0, t) * 0.5)
    leg_col = _mix(leg_base, PAL['tan'], band * (0.8 + 0.2 * streak))
    leg_col = _mix(leg_col, PAL['pale'], band * smoothstep(0.1, 0.8, u) * 0.45)
    leg_col = _mix(leg_col, PAL['scopula'], (seg == 4) * smoothstep(0.45, 0.8, t))   # hairy dark tarsus tips
    leg_col = leg_col * (0.86 + 0.22 * streak[..., None]) * (0.94 + 0.08 * fine[..., None])
    col = np.where(is_leg[..., None], leg_col, col)
    smooth = np.where(is_leg, 0.16 + 0.1 * band, smooth)

    # ---------------------------------------------------------------- carapace
    cara = part == SB.PART['carapace']
    fov = np.array([0.0, -0.27, 0.745 + lift])                                 # the fovea: striae radiate from it
    dx, dy = x - fov[0], y - fov[1]
    r = np.hypot(dx, dy)
    ang = np.arctan2(dy, dx)
    top = smoothstep(0.1, 0.55, N[..., 2])
    c = _mix(np.tile(PAL['brown'], (H, W, 1)), PAL['dark'], 0.45 + 0.3 * n_big)
    median = smoothstep(0.085, 0.045, ax - 0.03 * smoothstep(-0.35, -0.6, y)) * top * (y < -0.02) * (y > -0.66)
    c = _mix(c, PAL['tan'], 0.9 * median)
    rim = smoothstep(0.30, 0.05, N[..., 2]) * smoothstep(-0.25, 0.05, N[..., 2])     # pale bands along the margin
    c = _mix(c, PAL['tan'], 0.55 * rim * (y > -0.62))
    striae = smoothstep(0.55, 0.9, np.cos(ang * 8)) * smoothstep(0.04, 0.12, r) * smoothstep(0.30, 0.18, r)
    c = _mix(c, PAL['dark'] * 0.7, 0.65 * striae * top * (1 - median))
    c = _mix(c, PAL['dark'] * 0.55, 0.8 * smoothstep(0.025, 0.012, r) * top)      # the fovea groove
    head = smoothstep(-0.56, -0.66, y) * smoothstep(0.0, 0.6, N[..., 2] + 0.4)
    c = _mix(c, PAL['dark'] * 0.8, 0.6 * head * (1 - median * 0.5))            # dark eye region
    c = _mix(c, PAL['belly'], smoothstep(-0.1, -0.5, N[..., 2]))              # sternum
    hair = fbm(np.stack([ang * 9, r * 60, z * 20], -1), 3, seed=31)
    c = c * (0.88 + 0.2 * hair[..., None])
    col = np.where(cara[..., None], c, col)
    smooth = np.where(cara, 0.34, smooth)

    # ---------------------------------------------------------------- abdomen: dark, mottled, a bone-white skull
    abd = part == SB.PART['abdomen']
    hair_a = fbm(np.stack([x * 90, y * 12, z * 90], -1), 3, seed=41)
    a = _mix(np.tile(PAL['dark'], (H, W, 1)), PAL['brown'], 0.35 + 0.45 * n_big + 0.25 * n_mid)
    speck = smoothstep(0.55, 0.75, fbm(P * 40, 2, seed=44))
    a = _mix(a, PAL['tan'], 0.5 * speck * smoothstep(-0.2, 0.3, N[..., 2]))
    dorsal = smoothstep(0.15, 0.55, N[..., 2])
    sx, sy = ax, y                                                              # skull, crown toward the head
    cran = (sx / 0.19) ** 2 + ((sy - 0.33) / 0.175) ** 2                         # domed cranium
    cheek = (sx / 0.165) ** 2 + ((sy - 0.47) / 0.07) ** 2                        # cheekbones
    jw = 0.105 - 0.03 * smoothstep(0.52, 0.64, sy)
    jaw = smoothstep(0.01, -0.01, sx - jw) * smoothstep(0.44, 0.46, sy) * smoothstep(0.645, 0.625, sy)
    skull = np.maximum.reduce([smoothstep(1.06, 0.94, cran), smoothstep(1.1, 0.9, cheek), jaw]) * dorsal
    sock = ((sx - 0.076) / 0.056) ** 2 + ((sy - 0.415) / 0.05) ** 2
    holes = smoothstep(1.1, 0.88, sock)
    nose = smoothstep(0.006, -0.004, sx * 1.6 - (sy - 0.47) * 0.9) * (sy > 0.47) * (sy < 0.515)
    teeth = (sy > 0.55) * (sy < 0.615) * (sx < jw - 0.012)
    tooth_gap = teeth * smoothstep(0.0055, 0.0025, np.abs(((sx + 0.0125) % 0.025) - 0.0125))
    mouth = smoothstep(0.006, 0.003, np.abs(sy - 0.582)) * (sx < jw - 0.008)
    under = smoothstep(0.012, 0.004, np.abs(sy - 0.54)) * (sx < jw) * 0.5          # shadow under the cheekbones
    brow = smoothstep(0.03, 0.0, np.abs(cran - 0.72)) * (sy < 0.30) * 0.3
    bone = _mix(np.tile(PAL['bone'], (H, W, 1)), PAL['bone_dark'], 0.3 + 0.35 * n_mid + brow + under)
    edge = smoothstep(1.35, 1.05, np.minimum(cran, cheek)) * (1 - skull) * dorsal     # dark halo around it
    a = _mix(a, PAL['socket'], 0.6 * edge)
    a = _mix(a, bone, skull * (0.9 + 0.1 * hair_a))
    a = _mix(a, PAL['socket'], skull * np.maximum.reduce([holes, nose, tooth_gap, mouth]))
    cv = np.zeros((H, W))                                                        # chevrons behind the skull
    for yc, wdt in ((0.70, 0.16), (0.78, 0.12), (0.855, 0.08)):
        d = np.abs(sy - (yc - 0.35 * sx))
        cv = np.maximum(cv, smoothstep(0.018, 0.008, d) * (sx < wdt))
    a = _mix(a, PAL['pale'], 0.85 * cv * dorsal)
    a = _mix(a, PAL['belly'], smoothstep(-0.15, -0.6, N[..., 2]))
    a = a * (0.86 + 0.2 * hair_a[..., None])
    col = np.where(abd[..., None], a, col)
    smooth = np.where(abd, 0.22 + 0.08 * skull, smooth)

    # ---------------------------------------------------------------- mouthparts, eyes, small bits
    chel = part == SB.PART['chelicera']
    front = smoothstep(0.0, -0.6, N[..., 1])
    cc = _mix(np.tile(PAL['dark'], (H, W, 1)), PAL['rust'], 0.85 * front * (0.7 + 0.3 * n_mid))
    cc = _mix(cc, PAL['rust_light'], 0.35 * front * smoothstep(0.3, 0.8, fbm(P * np.array([80, 80, 12]), 2, seed=51)))
    col = np.where(chel[..., None], cc, col)
    fang = part == SB.PART['fang']
    col = np.where(fang[..., None], _mix(np.tile(PAL['fang'], (H, W, 1)), PAL['fang_tip'], t), col)
    smooth = np.where(fang, 0.8, np.where(chel, 0.15, smooth))
    palp = part == SB.PART['palp']
    pc = _mix(np.tile(PAL['brown'], (H, W, 1)), PAL['dark'], 0.5 + 0.3 * n_mid)
    pc = _mix(pc, PAL['tan'], smoothstep(0.82, 0.92, t) * 0.8)
    col = np.where(palp[..., None], pc, col)
    eye = (part == SB.PART['eye_big']) | (part == SB.PART['eye_small'])
    L1 = np.array([-0.35, -0.55, 0.76])
    L1 /= np.linalg.norm(L1)
    L2 = np.array([0.5, -0.7, 0.5])
    L2 /= np.linalg.norm(L2)
    hl = np.maximum(smoothstep(0.955, 0.985, N @ L1), 0.5 * smoothstep(0.975, 0.992, N @ L2))
    ec = _mix(np.tile(PAL['eye'], (H, W, 1)), PAL['eyeshine'], 0.35 * smoothstep(0.75, 0.95, N @ np.array([0, -0.7, -0.7])))
    ec = _mix(ec, np.ones(3) * 0.95, hl)
    col = np.where(eye[..., None], ec, col)
    smooth = np.where(eye, 0.95, smooth)
    spine = part == SB.PART['spine']
    col = np.where(spine[..., None], _mix(np.tile(PAL['dark'] * 0.7, (H, W, 1)), PAL['tan'], smoothstep(0.5, 1.0, t)), col)
    spin = part == SB.PART['spinneret']
    col = np.where(spin[..., None], np.tile(PAL['tan'], (H, W, 1)), col)
    ped = part == SB.PART['pedicel']
    col = np.where(ped[..., None], np.tile(PAL['belly'], (H, W, 1)), col)

    if variant == "pale":                                       # a washed-out cave variant
        lum = col @ np.array([0.3, 0.55, 0.15])
        col = _mix(col, lum[..., None] * np.array([1.25, 1.2, 1.1]) + 0.18, 0.7)

    # ---------------------------------------------------------------- painted light
    light = 0.74 + 0.36 * (N[..., 2] * 0.5 + 0.5)
    aot = 0.40 + 0.60 * np.clip(ao, 0, 1)
    shaded = col * (light * aot)[..., None] + ((1 - aot) * 0.10)[..., None] * np.array([0.25, 0.2, 0.35])
    shaded = np.where(eye[..., None], col * (0.85 + 0.15 * aot[..., None]), shaded)
    return np.clip(shaded, 0, 1), np.clip(smooth, 0, 1)


def write_texture(D, col, smooth, image_name="T_Spider", ob=None, material_name="M_Spider"):
    os.makedirs(TEX_DIR, exist_ok=True)
    H, W = D['part'].shape
    img = bpy.data.images.get(image_name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(image_name, W, H, alpha=True)
    img.colorspace_settings.name = 'sRGB'
    img.alpha_mode = 'CHANNEL_PACKED'
    rgba = np.concatenate([col, smooth[..., None]], -1).astype(np.float32)   # byte image: stored (sRGB) values
    img.pixels.foreach_set(rgba.ravel())
    fill_gutters(img, D['valid'])
    path = os.path.join(TEX_DIR, image_name + ".png")
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    if ob is not None:
        game_material(ob, img, material_name)
    return path


def game_material(ob, img, name="M_Spider"):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    inv = nt.nodes.new('ShaderNodeMath')
    inv.operation = 'SUBTRACT'
    inv.inputs[0].default_value = 1.0
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tex.outputs['Alpha'], inv.inputs[1])
    nt.links.new(inv.outputs[0], bsdf.inputs['Roughness'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    nt.nodes.active = tex
    ob.data.materials.clear()
    ob.data.materials.append(m)
    return m


def build_texture(ob, size=1024, variants=("hunter",)):
    D = bake_data(ob, size=size)
    paths = []
    for v in variants:
        col, smooth = paint(D, v)
        name = "T_Spider" if v == "hunter" else "T_Spider_" + v.title()
        paths.append(write_texture(D, col, smooth, name, ob if v == "hunter" else None))
    return paths, float(D['valid'].mean())
