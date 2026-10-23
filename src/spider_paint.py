"""UVs and the hand-painted texture of the spider.

UVs: every part was cut open by its builder (lofts along the belly or the underside of the leg, cones up one side;
eye domes are disks), so a plain angle-based unwrap unfolds each part as one piece. Islands are brought to one
texel density, the face, eyes, fangs and abdomen get more texels, then everything is packed.

Texture: painted per texel, not per vertex. Cycles bakes the texel's rest position, normal, part id (+ position
along the segment) and ambient occlusion into float images; numpy then paints colours, markings, hair streaks and
lighting from those. Alpha holds smoothness (URP Lit: Smoothness Source = Albedo Alpha): glossy eyes and fangs,
satin carapace, matte hair.

The family: `paint` works in the adult's coordinates (a kind's texels are mapped back through its reshape and size),
with a style per variant: hunter / pale (the adult), juvenile (the spiderling: pale, warm, glossy, a faint skull) and
brood (the broodmother: dark, greying and scarred, egg sacs, horns and the laid egg).
"""
import bpy, bmesh, math, os
import numpy as np
from mathutils import Vector
from bug_common import ROOT, smoothstep, fill_gutters, fbm, vnoise, hexc, srgb_to_lin, lin_to_srgb
import spider_body as SB
import spider_eggs as SE

TEX_DIR = os.path.join(ROOT, "textures")
UV_SCALE = {SB.PART['eye_big']: 2.6, SB.PART['eye_small']: 2.2, SB.PART['fang']: 1.8, SB.PART['chelicera']: 1.5,
            SB.PART['carapace']: 1.5, SB.PART['abdomen']: 1.5, SB.PART['palp']: 1.1, SB.PART['spine']: 0.6,
            SB.PART['spinneret']: 0.8, SB.PART['pedicel']: 0.7}
UV_SCALE_KIND = {
    "Spiderling": {**UV_SCALE, SB.PART['eye_big']: 1.6, SB.PART['eye_small']: 1.4, SB.PART['abdomen']: 1.2,
                   SB.PART['carapace']: 1.2},
    "Broodmother": {**UV_SCALE, SB.PART['abdomen']: 1.25, SB.PART['carapace']: 1.6, SB.PART['sac']: 0.85,
                    SB.PART['horn']: 0.9, SB.PART['egg']: 1.0},
}


def _part_per_vertex(me):
    att = me.color_attributes["info"]
    buf = np.empty(len(me.vertices) * 4, dtype=np.float32)
    att.data.foreach_get('color', buf)
    return np.rint(buf.reshape(-1, 4)[:, 0] * 255).astype(int)


def unwrap(ob, margin=0.0035, scales=None):
    """scales: part id -> texel density factor (default: the spider's UV_SCALE)."""
    scales = UV_SCALE_KIND.get(SB.K.name, UV_SCALE) if scales is None else scales
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


def uv_layout(ob, name="uv_layout", size=2048, texture=None):
    """renders/<name>.png. Headless Blender has no GPU drawing for the UV export: the layout is rasterised here
    instead (over `texture`, a Blender image, if given)."""
    if bpy.app.background:
        return draw_uv_layout(ob if isinstance(ob, (list, tuple)) else [ob], name, size, texture)
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


def draw_uv_layout(obs, name, size=2048, texture=None):
    """UV edges as white lines (seams red) on dark grey, or on the darkened texture."""
    img = np.full((size, size, 4), (0.12, 0.12, 0.13, 1.0), np.float32)
    if texture is not None:
        w, h = texture.size
        a = np.empty(w * h * 4, np.float32)
        texture.pixels.foreach_get(a)
        a = a.reshape(h, w, 4)
        ys = (np.arange(size) * h / size).astype(int)
        xs = (np.arange(size) * w / size).astype(int)
        img[..., :3] = a[ys][:, xs, :3] * 0.75
    for ob in obs:
        me = ob.data
        uv = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        seam = {e.key for e in me.edges if e.use_seam}
        segs, cols = [], []
        for p in me.polygons:
            ls = list(p.loop_indices)
            for a, b in zip(ls, ls[1:] + ls[:1]):
                segs.append((uv[a], uv[b]))
                ek = tuple(sorted((me.loops[a].vertex_index, me.loops[b].vertex_index)))
                cols.append((1.0, 0.25, 0.2) if ek in seam else (0.95, 0.95, 0.95))
        segs = np.array(segs)
        cols = np.array(cols, np.float32)
        L = np.linalg.norm(segs[:, 1] - segs[:, 0], axis=1) * size
        n = np.maximum(2, np.ceil(L * 1.5).astype(int))
        for k in np.unique(n):
            m = n == k
            t = np.linspace(0, 1, k)[None, :, None]
            pts = segs[m, 0][:, None] + (segs[m, 1] - segs[m, 0])[:, None] * t
            px = np.clip((pts * size).astype(int), 0, size - 1)
            c = np.repeat(cols[m][:, None], k, axis=1)
            img[px[..., 1], px[..., 0], :3] = c
    out = bpy.data.images.new("_uv_layout", size, size, alpha=True)
    out.pixels.foreach_set(img.ravel())
    path = os.path.join(ROOT, "renders", name + ".png")
    out.filepath_raw = path
    out.file_format = 'PNG'
    out.save()
    bpy.data.images.remove(out)
    return path


# ----------------------------------------------------------------------------------------- data bakes
def _bake_setup(obs, image_name, size, emit_builder=None):
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
    for ob in (obs if isinstance(obs, (list, tuple)) else [obs]):
        ob.data.materials.clear()
        ob.data.materials.append(m)
    return img


def _read(img):
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def bake_data(ob, size=1024, ao_samples=96, ao_dist=0.35):
    """Rest position, normal, info (part, t, u) and AO per texel. Returns dict of arrays (h, w, ...). `ob` may be a
    list of objects sharing one UV layout (the egg props): all are baked into the same images."""
    obs = list(ob) if isinstance(ob, (list, tuple)) else [ob]
    ob = obs[0]
    scn = bpy.context.scene
    prev_engine = scn.render.engine
    scn.render.engine = 'CYCLES'
    try:
        scn.cycles.device = 'GPU'
    except Exception:
        pass
    arm = [m for o in obs for m in o.modifiers if m.type == 'ARMATURE']
    for m in arm:
        m.show_render = m.show_viewport = False
    hidden = {o.name: o.hide_render for o in scn.objects}
    for o in scn.objects:
        o.hide_render = o not in obs
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = ob
    old = {o.name: list(o.data.materials) for o in obs}
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
        img = _bake_setup(obs, "_SPD_" + key, size, builder)
        bpy.ops.object.bake(type='EMIT', margin=6, use_clear=True)
        out[key] = _read(img)
    w = scn.world
    w.light_settings.distance = ao_dist
    scn.cycles.samples = ao_samples
    img = _bake_setup(obs, "_SPD_ao", size, None)
    bpy.ops.object.bake(type='AO', margin=6, use_clear=True)
    out["ao"] = _read(img)[..., 0]
    for o in obs:
        o.data.materials.clear()
        for m in old[o.name]:
            o.data.materials.append(m)
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
                m = (part == SB.PART['leg'] + 5 * i + j) & ((side_x > 0) == (side > 0))   # the active kind's bones
                if not m.any():
                    continue
                h, fr, L, _, _ = B[SB.leg_name(i, side, seg)]
                Rm = np.array(fr)
                loc[m] = (P[m] - np.array(h)) @ Rm
    return loc


def to_adult(P, part):
    """A kind's texel positions mapped back to the adult's (undo size, lift and the reshape about the pedicel), so the
    markings land where they do on the adult. Legs keep their own bone frames (see paint)."""
    K = SB.K
    q = P / K.size
    q[..., 2] -= K.lift
    head = np.isin(part, [SB.PART[k] for k in ('carapace', 'pedicel', 'eye_big', 'eye_small', 'chelicera', 'fang', 'palp')])
    head |= (part == SB.PART['horn']) & (q[..., 1] < SB.PEDICEL.y)
    rest = ~head & ~((part >= SB.LEG_PARTS[0]) & (part < SB.LEG_PARTS[1]))
    c = np.array(SB.PEDICEL)
    for m, k in ((head, K.ceph), (rest, K.abd)):
        if tuple(k) != (1.0, 1.0, 1.0):
            q[m] = c + (q[m] - c) / np.array(k)
    q[..., 2] += SB.LIFT
    return q


STYLE = {
    "hunter": {}, "pale": {},
    "juvenile": dict(skull=0.45, pal=dict(
        dark='#a48d6c', brown='#c9b18a', tan='#e6d4ad', pale='#f2e7c9', bone='#f4ecd6', bone_dark='#d9ccae',
        socket='#6f5940', belly='#b39b78', rust='#c99266', rust_light='#e0b085', fang='#5a3524', fang_tip='#8c5a3c',
        scopula='#8a7457')),
    "brood": dict(skull=1.0, pal=dict(
        dark='#221b14', brown='#423427', tan='#75624a', pale='#a29077', bone='#d8cba4', bone_dark='#9b8b69',
        socket='#0c0805', belly='#1a1510', rust='#5f2d15', rust_light='#7e4222', scopula='#110d0a')),
}


def paint(D, variant="hunter"):
    P, N, part, t, u, ao, valid = D['P'], D['N'], D['part'], D['t'], D['u'], D['ao'], D['valid']
    P0 = P
    if SB.K.name != "Spider":
        P = to_adult(P, part)
    st = STYLE.get(variant, {})
    pal = dict(PAL, **{k: hexc(v) for k, v in st['pal'].items()}) if st.get('pal') else PAL
    ks = st.get('skull', 1.0)
    H, W = part.shape
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    ax = np.abs(x)
    col = np.tile(pal['dark'], (H, W, 1)).astype(float)
    smooth = np.full((H, W), 0.2)
    lift = SB.LIFT
    is_leg = (part >= SB.LEG_PARTS[0]) & (part < SB.LEG_PARTS[1])
    seg = np.where(is_leg, (part - SB.PART['leg']) % 5, -1)
    n_big = fbm(P * 7.0, 3, seed=11)
    n_mid = fbm(P * 22.0, 3, seed=12)

    # ---------------------------------------------------------------- legs
    loc = _leg_local(P0, part, x)
    if SB.K.size != 1.0:
        loc = loc / SB.K.size
    streak = fbm(loc * np.array([140.0, 9.0, 140.0]), 3, seed=21)            # hair running along each segment
    fine = vnoise(loc * np.array([320.0, 26.0, 320.0]), seed=22)
    leg_base = _mix(np.tile(pal['brown'], (H, W, 1)), pal['dark'], 0.55 + 0.35 * n_big)
    leg_base = _mix(leg_base, pal['dark'], np.clip(-u, 0, 1) * 0.55)          # darker underneath
    band = np.zeros((H, W))
    for s_i in (1, 2, 3):                                                     # pale ring at the far end of femur, tibia, metatarsus
        band = np.maximum(band, (seg == s_i) * smoothstep(0.80, 0.9, t))
    band = np.maximum(band, (seg == 2) * smoothstep(0.26, 0.16, t) * 0.75)    # the patella knob
    band = np.maximum(band, (seg == 0) * smoothstep(0.7, 1.0, t) * 0.5)
    leg_col = _mix(leg_base, pal['tan'], band * (0.8 + 0.2 * streak))
    leg_col = _mix(leg_col, pal['pale'], band * smoothstep(0.1, 0.8, u) * 0.45)
    leg_col = _mix(leg_col, pal['scopula'], (seg == 4) * smoothstep(0.45, 0.8, t))   # hairy dark tarsus tips
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
    c = _mix(np.tile(pal['brown'], (H, W, 1)), pal['dark'], 0.45 + 0.3 * n_big)
    median = smoothstep(0.085, 0.045, ax - 0.03 * smoothstep(-0.35, -0.6, y)) * top * (y < -0.02) * (y > -0.66)
    c = _mix(c, pal['tan'], 0.9 * median)
    rim = smoothstep(0.30, 0.05, N[..., 2]) * smoothstep(-0.25, 0.05, N[..., 2])     # pale bands along the margin
    c = _mix(c, pal['tan'], 0.55 * rim * (y > -0.62))
    striae = smoothstep(0.55, 0.9, np.cos(ang * 8)) * smoothstep(0.04, 0.12, r) * smoothstep(0.30, 0.18, r)
    c = _mix(c, pal['dark'] * 0.7, 0.65 * striae * top * (1 - median))
    c = _mix(c, pal['dark'] * 0.55, 0.8 * smoothstep(0.025, 0.012, r) * top)      # the fovea groove
    head = smoothstep(-0.56, -0.66, y) * smoothstep(0.0, 0.6, N[..., 2] + 0.4)
    c = _mix(c, pal['dark'] * 0.8, 0.6 * head * (1 - median * 0.5))            # dark eye region
    c = _mix(c, pal['belly'], smoothstep(-0.1, -0.5, N[..., 2]))              # sternum
    hair = fbm(np.stack([ang * 9, r * 60, z * 20], -1), 3, seed=31)
    c = c * (0.88 + 0.2 * hair[..., None])
    col = np.where(cara[..., None], c, col)
    smooth = np.where(cara, 0.34, smooth)

    # ---------------------------------------------------------------- abdomen: dark, mottled, a bone-white skull
    abd = part == SB.PART['abdomen']
    hair_a = fbm(np.stack([x * 90, y * 12, z * 90], -1), 3, seed=41)
    a = _mix(np.tile(pal['dark'], (H, W, 1)), pal['brown'], 0.35 + 0.45 * n_big + 0.25 * n_mid)
    speck = smoothstep(0.55, 0.75, fbm(P * 40, 2, seed=44))
    a = _mix(a, pal['tan'], 0.5 * speck * smoothstep(-0.2, 0.3, N[..., 2]))
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
    bone = _mix(np.tile(pal['bone'], (H, W, 1)), pal['bone_dark'], 0.3 + 0.35 * n_mid + brow + under)
    edge = smoothstep(1.35, 1.05, np.minimum(cran, cheek)) * (1 - skull) * dorsal     # dark halo around it
    a = _mix(a, pal['socket'], 0.6 * edge * ks)
    a = _mix(a, bone, skull * (0.9 + 0.1 * hair_a) * ks)
    a = _mix(a, pal['socket'], skull * np.maximum.reduce([holes, nose, tooth_gap, mouth]) * ks)
    cv = np.zeros((H, W))                                                        # chevrons behind the skull
    for yc, wdt in ((0.70, 0.16), (0.78, 0.12), (0.855, 0.08)):
        d = np.abs(sy - (yc - 0.35 * sx))
        cv = np.maximum(cv, smoothstep(0.018, 0.008, d) * (sx < wdt))
    a = _mix(a, pal['pale'], 0.85 * cv * dorsal * ks)
    a = _mix(a, pal['belly'], smoothstep(-0.15, -0.6, N[..., 2]))
    a = a * (0.86 + 0.2 * hair_a[..., None])
    col = np.where(abd[..., None], a, col)
    smooth = np.where(abd, 0.22 + 0.08 * skull, smooth)

    # ---------------------------------------------------------------- mouthparts, eyes, small bits
    chel = part == SB.PART['chelicera']
    front = smoothstep(0.0, -0.6, N[..., 1])
    cc = _mix(np.tile(pal['dark'], (H, W, 1)), pal['rust'], 0.85 * front * (0.7 + 0.3 * n_mid))
    cc = _mix(cc, pal['rust_light'], 0.35 * front * smoothstep(0.3, 0.8, fbm(P * np.array([80, 80, 12]), 2, seed=51)))
    col = np.where(chel[..., None], cc, col)
    fang = part == SB.PART['fang']
    col = np.where(fang[..., None], _mix(np.tile(pal['fang'], (H, W, 1)), pal['fang_tip'], t), col)
    smooth = np.where(fang, 0.8, np.where(chel, 0.15, smooth))
    palp = part == SB.PART['palp']
    pc = _mix(np.tile(pal['brown'], (H, W, 1)), pal['dark'], 0.5 + 0.3 * n_mid)
    pc = _mix(pc, pal['tan'], smoothstep(0.82, 0.92, t) * 0.8)
    col = np.where(palp[..., None], pc, col)
    eye = (part == SB.PART['eye_big']) | (part == SB.PART['eye_small'])
    L1 = np.array([-0.35, -0.55, 0.76])
    L1 /= np.linalg.norm(L1)
    L2 = np.array([0.5, -0.7, 0.5])
    L2 /= np.linalg.norm(L2)
    hl = np.maximum(smoothstep(0.955, 0.985, N @ L1), 0.5 * smoothstep(0.975, 0.992, N @ L2))
    ec = _mix(np.tile(pal['eye'], (H, W, 1)), pal['eyeshine'], 0.35 * smoothstep(0.75, 0.95, N @ np.array([0, -0.7, -0.7])))
    ec = _mix(ec, np.ones(3) * 0.95, hl)
    col = np.where(eye[..., None], ec, col)
    smooth = np.where(eye, 0.95, smooth)
    spine = part == SB.PART['spine']
    col = np.where(spine[..., None], _mix(np.tile(pal['dark'] * 0.7, (H, W, 1)), pal['tan'], smoothstep(0.5, 1.0, t)), col)
    spin = part == SB.PART['spinneret']
    col = np.where(spin[..., None], np.tile(pal['tan'], (H, W, 1)), col)
    ped = part == SB.PART['pedicel']
    col = np.where(ped[..., None], np.tile(pal['belly'], (H, W, 1)), col)

    if variant == "pale":                                       # a washed-out cave variant
        lum = col @ np.array([0.3, 0.55, 0.15])
        col = _mix(col, lum[..., None] * np.array([1.25, 1.2, 1.1]) + 0.18, 0.7)

    if variant == "juvenile":
        col, smooth = _juvenile(P, N, part, t, u, col, smooth, is_leg, seg, eye, fang, pal)
    elif variant == "brood":
        col, smooth = _brood(P, N, part, t, u, ao, col, smooth, is_leg, seg, eye, fang, pal)

    # ---------------------------------------------------------------- painted light
    if variant == "juvenile":                                   # thin, translucent cuticle: softer occlusion, warm
        light = 0.80 + 0.26 * (N[..., 2] * 0.5 + 0.5)           # (subsurface) shadows instead of cool ones
        aot = 0.60 + 0.40 * np.clip(ao, 0, 1)
        shaded = col * (light * aot)[..., None] + ((1 - aot) * 0.22)[..., None] * np.array([0.62, 0.36, 0.18])
    else:
        light = 0.74 + 0.36 * (N[..., 2] * 0.5 + 0.5)
        aot = 0.40 + 0.60 * np.clip(ao, 0, 1)
        shaded = col * (light * aot)[..., None] + ((1 - aot) * 0.10)[..., None] * np.array([0.25, 0.2, 0.35])
    shaded = np.where(eye[..., None], col * (0.85 + 0.15 * aot[..., None]), shaded)
    return np.clip(shaded, 0, 1), np.clip(smooth, 0, 1)


def _juvenile(P, N, part, t, u, col, smooth, is_leg, seg, eye, fang, pal):
    """Spiderling: fresh from the moult. The heart mark shows through the abdomen, the legs glow amber between
    pale joints, a milky sheen on top, glossy all over."""
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    abd = part == SB.PART['abdomen']
    dorsal = smoothstep(0.2, 0.6, N[..., 2])
    w = 0.055 * np.maximum(np.sin(np.clip((y - 0.08) / 0.55, 0, 1) * math.pi), 0.0) ** 0.8
    heart = smoothstep(0.012, -0.006, np.abs(x) - w) * (y > 0.08) * (y < 0.63) * dorsal
    col = _mix(col, hexc('#8d6d48'), 0.55 * heart * abd)
    cv = np.zeros(part.shape)                                    # faint paired dots along the heart mark
    for yc in (0.30, 0.42, 0.54):
        cv = np.maximum(cv, smoothstep(0.03, 0.018, np.hypot(np.abs(x) - 0.085, y - yc)))
    col = _mix(col, hexc('#9a7b56'), 0.4 * cv * dorsal * abd)
    mid = is_leg & (seg >= 1) & (seg <= 3)
    amber = smoothstep(0.15, 0.4, t) * smoothstep(0.85, 0.6, t)
    col = _mix(col, hexc('#d29a5c'), 0.38 * amber * mid)
    col = _mix(col, hexc('#c58a50'), 0.25 * (seg == 4) * smoothstep(0.3, 0.9, t))
    top = smoothstep(0.35, 0.95, N[..., 2]) * ~eye
    col = _mix(col, hexc('#f6eedb'), 0.16 * top)
    smooth = np.where(eye, smooth, np.where(fang, 0.75, np.maximum(smooth, 0.42)))
    return col, smooth


SCAR_SEED = 17


def _seg_dist(P, a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    tt = np.clip(((P - a) @ d) / (d @ d), 0, 1)
    return np.linalg.norm(P - (a + tt[..., None] * d), axis=-1)


def _brood(P, N, part, t, u, ao, col, smooth, is_leg, seg, eye, fang, pal):
    """Broodmother: old. Greying hairs, healed scars (carapace, abdomen, femurs), worn pale tips; silk wisps on the
    rear of the abdomen; the egg sacs (silk), the horns, the laid egg."""
    x, y, z = P[..., 0], P[..., 1], P[..., 2]
    shell = ~eye & ~fang & (part < SB.PART['sac'])
    grey = smoothstep(0.5, 0.78, fbm(P * 48.0, 2, seed=61)) * smoothstep(-0.3, 0.4, N[..., 2] + 0.2)
    grey = np.maximum(grey, 0.6 * smoothstep(0.62, 0.8, vnoise(P * 160.0, seed=62)))      # single grey hairs
    col = _mix(col, hexc('#8f897c'), 0.55 * grey * shell)
    rng = np.random.default_rng(SCAR_SEED)
    cara = part == SB.PART['carapace']
    abd = part == SB.PART['abdomen']
    scar = np.zeros(part.shape)
    for k in range(16):                                          # carapace and abdomen: straight healed gashes
        if k < 6:
            c = np.array([rng.uniform(-0.2, 0.2), rng.uniform(-0.55, -0.1), 0.0])
            c[2] = 0.70 + SB.LIFT
            m = cara
        else:
            c = np.array([rng.choice([-1, 1]) * rng.uniform(0.12, 0.30), rng.uniform(0.15, 0.85), 0.0])
            c[2] = 0.82 + SB.LIFT
            m = abd
        a = rng.uniform(0, math.pi)
        L = rng.uniform(0.05, 0.13)
        dv = np.array([math.cos(a), math.sin(a), rng.uniform(-0.3, 0.3)]) * L
        d = _seg_dist(P, c - dv, c + dv)
        scar = np.maximum(scar, smoothstep(0.009, 0.003, d) * m * smoothstep(0.0, 0.4, N[..., 2]))
    col = _mix(col, hexc('#a08b69'), 0.75 * scar)
    tips = is_leg & (seg == 4) & (t > 0.85)
    col = _mix(col, hexc('#4a3e30'), 0.6 * tips)
    rear = abd * smoothstep(0.55, 0.85, y)
    wisp = smoothstep(0.5, 0.8, fbm(np.stack([x * 26 + y * 9, y * 5, z * 26], -1), 3, seed=63))
    col = _mix(col, hexc('#cfc8b6'), 0.45 * wisp * rear)
    # egg sacs: silk spun round them, fibres and stains, darker where they sink into the abdomen
    sac = part == SB.PART['sac']
    fib = fbm(np.stack([P[..., 0] * 90 + P[..., 1] * 60, P[..., 1] * 90 - P[..., 2] * 50, P[..., 2] * 70], -1), 3, seed=71)
    sc = _mix(np.tile(hexc('#e3dccb'), part.shape + (1,)), hexc('#bdb08c'), 0.35 + 0.35 * fbm(P * 14, 2, seed=72))
    sc = sc * (0.9 + 0.16 * fib[..., None])
    sc = _mix(sc, hexc('#8a7a58'), 0.55 * smoothstep(0.45, 0.15, u))
    col = np.where(sac[..., None], sc, col)
    smooth = np.where(sac, 0.24, smooth)
    horn = part == SB.PART['horn']
    hc = _mix(np.tile(pal['dark'], part.shape + (1,)), hexc('#a59270'), smoothstep(0.45, 1.0, t))
    col = np.where(horn[..., None], hc, col)
    smooth = np.where(horn, 0.42, smooth)
    egg = part == SB.PART['egg']
    ec, es = SE.shell_colour(P, N, part.shape)
    col = np.where(egg[..., None], ec, col)
    smooth = np.where(egg, es, smooth)
    smooth = np.where(shell & ~horn, smooth * 0.85, smooth)      # dull, dusty
    return col, smooth


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


def texture_name(v):
    if SB.K.name == "Spider":
        return "T_Spider" if v == "hunter" else "T_Spider_" + v.title()
    return "T_" + SB.K.name if v == KIND_VARIANT[SB.K.name] else f"T_{SB.K.name}_{v.title()}"


KIND_VARIANT = {"Spider": "hunter", "Spiderling": "juvenile", "Broodmother": "brood"}


def build_texture(ob, size=1024, variants=("hunter",)):
    """Bake once, paint each variant; the first (the kind's own) goes on the object's material M_<kind>."""
    D = bake_data(ob, size=size)
    paths = []
    main = KIND_VARIANT[SB.K.name]
    for v in variants:
        col, smooth = paint(D, v)
        paths.append(write_texture(D, col, smooth, texture_name(v), ob if v == main else None, "M_" + SB.K.name))
    clean_bakes()
    return paths, float(D['valid'].mean())


def clean_bakes():
    """Drop the data-bake images and material so they don't end up in the .blend."""
    for k in ("pos", "nrm", "info", "ao"):
        img = bpy.data.images.get("_SPD_" + k)
        if img is not None:
            bpy.data.images.remove(img)
    m = bpy.data.materials.get("_SPD_Bake")
    if m is not None and m.users == 0:
        bpy.data.materials.remove(m)
