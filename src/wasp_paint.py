"""Textures of the giant wasp.

T_Wasp (1024): the shells, painted per texel from the same data bakes as the spider (spider_paint.bake_data):
warning-yellow and black gaster bands with the black notch, yellow face, black thorax with yellow marks, amber legs,
glossy dark-red eyes. Alpha = smoothness (chitin is glossy).
T_Wasp_Wing (512, RGBA): the wing membranes, painted directly in wing space (the wing UVs are a plain mapping of the
wing plane): smoky amber membrane, dark veins, a thick leading edge and the dark stigma. Alpha = opacity.
"""
import bpy, os, math
import numpy as np
from bug_common import ROOT, smoothstep, fbm, vnoise, hexc, fill_gutters
import spider_paint as SP
import wasp_body as WB

TEX_DIR = os.path.join(ROOT, "textures")
P = WB.PART
UV_SCALE = {P['eye']: 2.0, P['ocellus']: 1.5, P['head']: 1.7, P['mandible']: 1.5, P['thorax']: 1.35,
            P['antenna']: 0.8, P['stinger']: 1.2, P['petiole']: 0.8, **{P['plate'] + k: 1.35 for k in range(6)},
            **{P['leg'] + k: 0.9 for k in range(12)}}

PAL = {
    'yellow': hexc('#e9b421'), 'yellow_hi': hexc('#f6d24a'), 'orange': hexc('#d27a1c'), 'black': hexc('#17120e'),
    'brown': hexc('#43291a'), 'amber': hexc('#b8701e'), 'amber_lt': hexc('#dd9c32'), 'eye': hexc('#3b150f'),
    'eye_hi': hexc('#8a3a22'), 'ocellus': hexc('#c9772a'),
}


def _mix(a, b, t):
    t = np.clip(np.asarray(t, float), 0, 1)[..., None]
    return a * (1 - t) + np.asarray(b) * t


def paint(D):
    Pp, N, part, t, ao = D['P'], D['N'], D['part'], D['t'], D['ao']
    Hh, Ww = part.shape
    x, y, z = Pp[..., 0], Pp[..., 1], Pp[..., 2] - WB.HOVER
    ax = np.abs(x)
    col = np.tile(PAL['black'], (Hh, Ww, 1)).astype(float)
    smooth = np.full((Hh, Ww), 0.5)
    n1 = fbm(Pp * 9.0, 3, seed=61)
    fuzz = vnoise(Pp * 260.0, seed=62)
    top = smoothstep(0.1, 0.5, N[..., 2])

    # gaster plates: black front, yellow band behind with a black notch on the midline and side spots
    for k in range(6):
        m = part == P['plate'] + k
        if not m.any():
            continue
        start = {0: 0.62, 5: 0.0}.get(k, 0.42)
        band = smoothstep(start, start + 0.06, t)
        notch = smoothstep(0.055, 0.03, ax - 0.05 * (1 - np.clip((t - start) / 0.45, 0, 1))) * top * (k < 5)
        spot = np.exp(-(((ax - 0.12) / 0.03) ** 2 + ((t - (start + 0.18)) / 0.08) ** 2)) * (k in (1, 2, 3)) * top
        yel = _mix(np.tile(PAL['yellow'], (Hh, Ww, 1)), PAL['orange'], 0.25 + 0.2 * n1)
        c = _mix(np.tile(PAL['black'], (Hh, Ww, 1)), yel, band * (1 - np.maximum(notch, spot)))
        if k == 5:
            c = _mix(c, PAL['black'], smoothstep(0.55, 0.8, t))          # dark tip
        c = _mix(c, PAL['yellow_hi'], 0.25 * band * smoothstep(0.85, 0.99, t))   # pale rim of each plate
        col = np.where(m[..., None], c, col)
        smooth = np.where(m, 0.6, smooth)

    # thorax: black, fuzzy, two yellow stripes on the scutum, yellow scutellum and side flecks
    th = part == P['thorax']
    stripes = sum(np.exp(-((ax - 0.06) / 0.018) ** 2 * 1.0) * smoothstep(-0.16, -0.10, y) * smoothstep(0.08, 0.02, y)
                  for _ in (0,)) * top
    scut = np.exp(-(((x) / 0.09) ** 2 + ((y - 0.15) / 0.035) ** 2)) * top
    pron = smoothstep(0.02, 0.0, np.abs(y + 0.19)) * smoothstep(0.3, 0.9, N[..., 2] * 0.6 + 0.5)    # yellow collar
    flecks = np.exp(-(((ax - 0.17) / 0.03) ** 2 + ((y + 0.02) / 0.05) ** 2 + ((z - 0.03) / 0.05) ** 2))
    c = _mix(np.tile(PAL['black'], (Hh, Ww, 1)), PAL['brown'], 0.3 + 0.3 * n1)
    c = _mix(c, PAL['yellow'], np.clip(stripes + scut + 0.8 * pron + flecks, 0, 1))
    c = c * (0.85 + 0.2 * fuzz[..., None])
    col = np.where(th[..., None], c, col)
    smooth = np.where(th, 0.35, smooth)

    # head: yellow face and cheeks, dark crown behind the ocelli
    hd = part == P['head']
    face = smoothstep(-0.25, -0.65, N[..., 1])
    crown = smoothstep(0.2, 0.6, N[..., 2]) * smoothstep(-0.37, -0.30, y)
    c = _mix(np.tile(PAL['orange'], (Hh, Ww, 1)), PAL['yellow'], face)
    c = _mix(c, PAL['black'], 0.9 * crown)
    c = _mix(c, PAL['brown'], 0.5 * np.exp(-((x / 0.02) ** 2)) * face * smoothstep(-0.02, 0.05, z))   # clypeus line
    col = np.where(hd[..., None], c, col)
    smooth = np.where(hd, 0.55, smooth)
    eye = part == P['eye']
    L1 = np.array([-0.3, -0.5, 0.8])
    L1 /= np.linalg.norm(L1)
    hl = smoothstep(0.95, 0.985, N @ L1)
    ec = _mix(np.tile(PAL['eye'], (Hh, Ww, 1)), PAL['eye_hi'], 0.4 * smoothstep(0.3, -0.3, N[..., 2]))
    col = np.where(eye[..., None], _mix(ec, np.ones(3) * 0.9, hl), col)
    smooth = np.where(eye, 0.92, smooth)
    col = np.where((part == P['ocellus'])[..., None], np.tile(PAL['ocellus'], (Hh, Ww, 1)), col)
    smooth = np.where(part == P['ocellus'], 0.9, smooth)
    md = part == P['mandible']
    col = np.where(md[..., None], _mix(np.tile(PAL['orange'], (Hh, Ww, 1)), PAL['black'], smoothstep(0.55, 0.9, t)), col)
    an = part == P['antenna']
    col = np.where(an[..., None], _mix(np.tile(PAL['brown'], (Hh, Ww, 1)), PAL['orange'], 0.35 + 0.3 * n1), col)
    col = np.where((part == P['stinger'])[..., None], np.tile(PAL['black'], (Hh, Ww, 1)), col)
    smooth = np.where((part == P['stinger']) | md, 0.75, smooth)
    col = np.where((part == P['petiole'])[..., None], np.tile(PAL['black'], (Hh, Ww, 1)), col)

    # legs: amber, darker at the coxa and the base of the femur, pale tarsi
    lg = (part >= P['leg']) & (part < P['leg'] + 12)
    seg = (part - P['leg']) % 4
    c = _mix(np.tile(PAL['amber'], (Hh, Ww, 1)), PAL['amber_lt'], 0.3 + 0.3 * n1)
    c = _mix(c, PAL['black'], (seg == 0) * 0.85 + (seg == 1) * smoothstep(0.35, 0.0, t) * 0.8)
    c = _mix(c, PAL['yellow'], (seg == 3) * 0.45)
    col = np.where(lg[..., None], c, col)
    smooth = np.where(lg, 0.45, smooth)

    light = 0.74 + 0.36 * (N[..., 2] * 0.5 + 0.5)
    aot = 0.42 + 0.58 * np.clip(ao, 0, 1)
    shaded = col * (light * aot)[..., None] + ((1 - aot) * 0.08)[..., None] * np.array([0.25, 0.2, 0.35])
    shaded = np.where(eye[..., None], col * (0.85 + 0.15 * aot[..., None]), shaded)
    return np.clip(shaded, 0, 1), np.clip(smooth, 0, 1)


# ----------------------------------------------------------------------------------------- wings
def _seg_dist(px, py, a, b):
    ax_, ay_ = a
    bx_, by_ = b
    dx, dy = bx_ - ax_, by_ - ay_
    L2 = dx * dx + dy * dy + 1e-12
    t = np.clip(((px - ax_) * dx + (py - ay_) * dy) / L2, 0, 1)
    return np.hypot(px - (ax_ + t * dx), py - (ay_ + t * dy))


def _inside(px, py, poly):
    """Even-odd point in polygon (vectorised)."""
    inside = np.zeros(px.shape, bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = ((y1 > py) != (y2 > py)) & (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1)
        inside ^= cond
    return inside


# veins in wing-plane metres (u along the span from the root, v toward the leading edge), per wing
VEINS = {
    "Forewing": [[(0.0, 0.02), (0.55, 0.062), (0.62, 0.064)],                      # costa + subcosta
                 [(0.02, 0.0), (0.45, 0.03), (0.62, 0.03), (0.86, 0.025)],
                 [(0.03, -0.02), (0.30, -0.03), (0.52, -0.02), (0.62, 0.03)],
                 [(0.30, -0.03), (0.40, -0.09), (0.62, -0.11), (0.80, -0.10)],
                 [(0.52, -0.02), (0.55, -0.07), (0.62, -0.11)],
                 [(0.05, -0.05), (0.22, -0.10), (0.40, -0.14)],
                 [(0.62, 0.03), (0.66, -0.02), (0.64, -0.11)]],
    "Hindwing": [[(0.0, 0.015), (0.40, 0.045), (0.55, 0.035)],
                 [(0.02, -0.01), (0.25, -0.02), (0.45, -0.03)],
                 [(0.10, -0.03), (0.22, -0.07), (0.34, -0.10)],
                 [(0.25, -0.02), (0.30, -0.06)]],
}


def paint_wings(size=512):
    """RGBA wing texture; returns the image path."""
    img = np.zeros((size, size, 4), float)
    vv, uu = np.mgrid[0:size, 0:size]
    U = (uu + 0.5) / size
    V = (vv + 0.5) / size
    for wname, spec in (("Forewing", WB.FOREWING), ("Hindwing", WB.HINDWING)):
        v0 = WB.WING_V0[wname]
        out = spec['outline']
        umax = max(p[0] for p in out)
        vmin, vmax = min(p[1] for p in out), max(p[1] for p in out)
        # texel -> wing-plane metres (inverse of wasp_body.wing_uv)
        wu = (U - 0.02) / 0.96 * umax
        wv = (V - v0 - 0.02) / 0.46 * (vmax - vmin) + vmin
        half = (V >= v0) & (V < v0 + 0.5)
        ins = _inside(wu, wv, out) & half
        edge = np.full(U.shape, 1e9)
        for i in range(len(out)):
            edge = np.minimum(edge, _seg_dist(wu, wv, out[i], out[(i + 1) % len(out)]))
        vein = np.full(U.shape, 1e9)
        for line in VEINS[wname]:
            for a, b in zip(line[:-1], line[1:]):
                vein = np.minimum(vein, _seg_dist(wu, wv, a, b))
        texel = umax / (0.96 * size)
        vw = np.clip(1.5 - vein / (texel * 1.3), 0, 1)
        lead = np.clip(1.4 - edge / (texel * (2.4 if wname == "Forewing" else 1.8)), 0, 1) * (wv > 0.0)
        rim = np.clip(1.3 - edge / (texel * 1.2), 0, 1)
        stig = np.exp(-(((wu - 0.62) / 0.035) ** 2 + ((wv - 0.055) / 0.012) ** 2)) if wname == "Forewing" else 0 * wu
        smoke = 0.55 + 0.25 * smoothstep(0.1, 0.9, wu / umax) + 0.1 * fbm(np.stack([wu * 30, wv * 30, 0 * wu], -1), 2, seed=71)
        membrane = np.array([0.62, 0.46, 0.24])
        c = membrane[None, None, :] * smoke[..., None]
        a = 0.26 + 0.1 * smoothstep(0.4, 1.0, wu / umax)
        dark = np.array([0.20, 0.12, 0.06])
        k = np.clip(np.maximum.reduce([vw, lead, rim * 0.6, stig * 1.2]), 0, 1)
        c = c * (1 - k[..., None]) + dark * k[..., None]
        a = a * (1 - k) + 0.95 * k
        img[..., :3] = np.where(ins[..., None], c, img[..., :3])
        img[..., 3] = np.where(ins, a, img[..., 3])
    # gutters: spread colour outward, keep the alpha of the islands (0 outside, so the outline stays crisp)
    name = "T_Wasp_Wing"
    im = bpy.data.images.get(name)
    if im is not None:
        bpy.data.images.remove(im)
    im = bpy.data.images.new(name, size, size, alpha=True)
    im.alpha_mode = 'STRAIGHT'
    alpha = img[..., 3].copy()
    im.pixels.foreach_set(img.astype(np.float32).ravel())
    fill_gutters(im, alpha > 0)
    buf = np.empty(size * size * 4, np.float32)
    im.pixels.foreach_get(buf)
    buf = buf.reshape(size, size, 4)
    buf[..., 3] = alpha
    im.pixels.foreach_set(buf.ravel())
    path = os.path.join(TEX_DIR, name + ".png")
    im.filepath_raw = path
    im.file_format = 'PNG'
    im.save()
    return im, path


def wing_material(ob, img, name="M_Wasp_Wing"):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.35
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    for attr, val in (("surface_render_method", 'BLENDED'), ("blend_method", 'BLEND')):
        try:
            setattr(m, attr, val)
        except Exception:
            pass
    m.use_backface_culling = False
    ob.data.materials.clear()
    ob.data.materials.append(m)
    return m


def build_textures(body, wings, size=1024):
    SP.unwrap(body, scales=UV_SCALE)
    D = SP.bake_data(body, size=size)
    col, smooth = paint(D)
    body_path = SP.write_texture(D, col, smooth, "T_Wasp", body, "M_Wasp")
    img, wing_path = paint_wings()
    wing_material(wings, img)
    return [body_path, wing_path], float(D['valid'].mean())
