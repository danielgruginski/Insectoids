"""Spider eggs: the leathery egg shape (shared with the broodmother's egg sacs and the egg her Spawn clip lays) and three
static props on one 512 texture (T_SpiderEggs), in scene SpiderEggs:

  SpiderEgg_Clutch    nine eggs piled on the ground, half sunk in a silk mat, threads drawn over them (~1.4k tris)
  SpiderEgg_Single    one egg on a little silk pad (the egg the broodmother lays, same size and shape)
  SpiderEgg_Hatched   the bottom of an egg, torn open and empty, flaps of shell bent out, on a silk pad

Eggs are lofts along their long axis (+Y in egg space, centred on the origin), lumpy through the loft's bulge.
Silk mats are polar grids draped over the eggs (a fraction of the pile's height, so the eggs' tops come through);
threads run over the pile, kept taut (they span the gaps instead of following them). Each prop has its origin on the
ground under its middle. Painted per texel from the same data bakes as the spiders (spider_paint.bake_data).
"""
import bpy, bmesh, math, os
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from bug_common import ROOT, loft, mesh_obj, get_coll, remove_obj, smoothstep, fbm, vnoise, hexc

EGG_LEN, EGG_W, EGG_SEED = 0.38, 0.30, 3        # metres; the broodmother's laid egg and SpiderEgg_Single
PART = dict(egg=0, inner=1, rim=2, silk=3, thread=4)
PROPS = ("SpiderEgg_Clutch", "SpiderEgg_Single", "SpiderEgg_Hatched")
SPACING = 2.4                                    # props stand apart in their scene (so the AO bake keeps them apart)
TEX = "T_SpiderEggs"
MAT = "M_SpiderEggs"


# ----------------------------------------------------------------------------------------- the egg
def _radius(x, W):
    """Egg profile at x in [-1, 1] along the long axis (blunter at +1)."""
    x = np.clip(np.asarray(x, float), -1, 1)
    return 0.5 * W * np.sqrt(np.maximum(0.0, 1 - x * x)) * (1 + 0.10 * x)


def _lumps(seed, amount):
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * math.pi, 4)

    def bulge(t, th):
        return 1.0 + amount * (0.55 * math.sin(2 * th + ph[0] + 4 * t) + 0.3 * math.sin(3 * th + ph[1] - 7 * t) +
                               0.25 * math.sin(5 * th + ph[2] + 11 * t * ph[3]))
    return bulge


def egg(bm, M, L, W, seg=8, rows=5, seed=0, flat=1.0, lumps=0.05):
    """A closed lumpy egg of length L and width W along +Y of the matrix M (centred on its origin), flattened along
    its Z by `flat`. Seam down -Z. Returns the BMVerts."""
    xe = 0.78
    xs = np.linspace(-xe, xe, rows)
    rr = _radius(xs, W)
    R = [(0, x * L * 0.5, 0, r, r * flat, r * flat) for x, r in zip(xs, rr)]
    ext = L * 0.5 * (1 - xe)
    f0, f1 = ext / (rr[0] * flat), ext / (rr[-1] * flat)
    return loft(bm, R, up=(0, 0, 1), seg=seg, per_seg=1, cap0=f0, cap1=f1, capk=2, xform=M, bulge=_lumps(seed, lumps))


# ----------------------------------------------------------------------------------------- tagging
class _Tags:
    """Paint info per vertex (part, t, u) like the spiders' `info` attribute, without bones."""

    def __init__(self, bm):
        self.part = bm.verts.layers.int.new("part")
        self.t = bm.verts.layers.float.new("t")
        self.u = bm.verts.layers.float.new("u")

    def tag(self, verts, part, t=None, u=None):
        for i, v in enumerate(verts):
            v[self.part] = part
            if t is not None:
                v[self.t] = t(v) if callable(t) else t
            if u is not None:
                v[self.u] = u(v) if callable(u) else u


def _finish(name, bm, tags, coll, offset):
    bmesh.ops.recalc_face_normals(bm, faces=[f for f in bm.faces if not f.tag])
    info = [(v[tags.part], v[tags.t], v[tags.u]) for v in bm.verts]
    remove_obj(name)
    ob = mesh_obj(name, bm, coll, recalc=False)
    for p in ob.data.polygons:
        p.use_smooth = True
    att = ob.data.color_attributes.new("info", 'FLOAT_COLOR', 'POINT')
    att.data.foreach_set('color', np.array([(p / 255.0, t, u, 1.0) for p, t, u in info], np.float32).ravel())
    ob.location = offset
    return ob


# ----------------------------------------------------------------------------------------- silk
def _height_field(egg_bms):
    bvhs = [BVHTree.FromBMesh(b) for b in egg_bms]

    def h(x, y):
        best = 0.0
        for bv in bvhs:
            hit = bv.ray_cast(Vector((x, y, 3.0)), Vector((0, 0, -1)), 6.0)[0]
            if hit is not None:
                best = max(best, hit.z)
        return best
    return h


def silk_mat(bm, tags, height, R, rings=6, segs=18, drape=0.55, seed=0, lift=0.004):
    """A silk sheet over the ground and the lower part of the eggs: a polar grid whose height is `drape` of the pile's
    (smoothed), falling to the ground at an uneven rim. Returns its verts."""
    rng = np.random.default_rng(seed)
    edge = 1.0 + 0.12 * np.sin(np.arange(segs) * 2 * math.pi / segs * 3 + rng.uniform(0, 6)) + rng.uniform(-0.06, 0.06, segs)
    pts = np.zeros((rings + 1, segs, 3))
    for k in range(rings + 1):
        for j in range(segs):
            a = 2 * math.pi * (j + 0.5 * (k % 2)) / segs
            r = R * edge[j] * (k / rings) ** 0.85
            pts[k, j, :2] = (r * math.cos(a), r * math.sin(a))
    H = np.array([[height(*pts[k, j, :2]) for j in range(segs)] for k in range(rings + 1)])
    for _ in range(3):                               # taut: lift each point toward its neighbours' mean
        Hn = H.copy()
        for k in range(1, rings):
            for j in range(segs):
                m = (H[k - 1, j] + H[k + 1, j] + H[k, (j - 1) % segs] + H[k, (j + 1) % segs]) / 4
                Hn[k, j] = max(H[k, j], 0.5 * (H[k, j] + m))
        H = Hn
    for k in range(rings + 1):
        rim = smoothstep(1.0, 0.72, k / rings)
        for j in range(segs):
            pts[k, j, 2] = lift + drape * H[k, j] * rim + 0.006 * rng.uniform(-1, 1) * rim
    centre = bm.verts.new((0, 0, lift + drape * height(0, 0)))
    grid = [[bm.verts.new(tuple(pts[k, j])) for j in range(segs)] for k in range(1, rings + 1)]
    faces = []                                       # counter-clockwise from above: normals up (an open sheet, so
    for j in range(segs):                            # it is left out of the normal recalc: tagged)
        faces.append(bm.faces.new((centre, grid[0][j], grid[0][(j + 1) % segs])))
    for k in range(rings - 1):
        a, b = grid[k], grid[k + 1]
        for j in range(segs):
            faces.append(bm.faces.new((a[j], b[j], b[(j + 1) % segs], a[(j + 1) % segs])))
    for f in faces:
        f.tag = True
    vs = [centre] + [v for r in grid for v in r]
    tags.tag(vs, PART['silk'], t=lambda v: min(1.0, math.hypot(v.co.x, v.co.y) / R), u=0.5)
    return vs


def thread(bm, tags, height, a, b, r=0.007, n=11, sides=3, sag=0.0):
    """A silk thread from ground point a to ground point b over the pile, taut (spans the gaps)."""
    a, b = np.array(a, float), np.array(b, float)
    P = [a + (b - a) * (i / (n - 1)) for i in range(n)]
    z = np.array([height(p[0], p[1]) + r * 1.2 for p in P])
    z[0] = z[-1] = r
    for _ in range(12):
        z[1:-1] = np.maximum(z[1:-1], 0.5 * (z[:-2] + z[2:]) - sag)
    rows = [(p[0], p[1], zz, r, r, r) for p, zz in zip(P, z)]
    vs = loft(bm, rows, up=(0, 0, 1), seg=sides, per_seg=1, cap0=0, cap1=0)
    tags.tag(vs, PART['thread'], t=0.5, u=0.5)
    return vs


# ----------------------------------------------------------------------------------------- the props
def _egg_at(bm, tags, centre, yaw, tilt, L, W, seed, seg=7, rows=5, lumps=0.05):
    """An egg lying with its long axis along `yaw` (deg, from +X), raised by `tilt` (deg), its centre at `centre`."""
    y, t = math.radians(yaw), math.radians(tilt)
    Y = Vector((math.cos(y) * math.cos(t), math.sin(y) * math.cos(t), math.sin(t)))
    X = Y.cross(Vector((0, 0, 1))).normalized()
    Z = X.cross(Y)
    M = Matrix.Translation(Vector(centre)) @ Matrix((X, Y, Z)).transposed().to_4x4()
    tmp = bmesh.new()
    egg(tmp, M, L, W, seg=seg, rows=rows, seed=seed, lumps=lumps)
    vs = egg(bm, M, L, W, seg=seg, rows=rows, seed=seed, lumps=lumps)
    c = Vector(centre)
    tags.tag(vs, PART['egg'], t=lambda v: max(0.0, min(1.0, 0.5 + (v.co - c).dot(Y) / L)),
             u=lambda v: 0.5 + 0.5 * max(-1.0, min(1.0, (v.co - c).dot(Z) / (0.5 * W))))
    return tmp


def build_clutch(coll, offset):
    bm = bmesh.new()
    tags = _Tags(bm)
    rng = np.random.default_rng(21)
    shapes = []
    for i in range(6):                                   # the ring on the ground, leaning in
        a = i * 60 + rng.uniform(-9, 9)
        k = rng.uniform(0.9, 1.06)
        L, W = EGG_LEN * k, EGG_W * k
        r = 0.27 + rng.uniform(-0.02, 0.02)
        c = (r * math.cos(math.radians(a)), r * math.sin(math.radians(a)), W * 0.53)
        shapes.append(_egg_at(bm, tags, c, a + 180 + rng.uniform(-14, 14), 22 + rng.uniform(-6, 6), L, W, 30 + i))
    for i in range(3):                                   # three on top, leaning out
        a = 30 + i * 120 + rng.uniform(-12, 12)
        k = rng.uniform(0.92, 1.02)
        L, W = EGG_LEN * k, EGG_W * k
        c = (0.10 * math.cos(math.radians(a)), 0.10 * math.sin(math.radians(a)), 0.33 + rng.uniform(-0.02, 0.02))
        shapes.append(_egg_at(bm, tags, c, a + rng.uniform(-20, 20), -18 + rng.uniform(-6, 6), L, W, 40 + i))
    h = _height_field(shapes)
    silk_mat(bm, tags, h, 0.64, rings=6, segs=18, drape=0.62, seed=5)
    for i, (a0, da) in enumerate([(10, 170), (75, 160), (140, 185), (215, 150), (285, 170)]):
        a, b = math.radians(a0), math.radians(a0 + da)
        r0, r1 = rng.uniform(0.45, 0.58), rng.uniform(0.45, 0.58)
        thread(bm, tags, h, (r0 * math.cos(a), r0 * math.sin(a)), (r1 * math.cos(b), r1 * math.sin(b)),
               r=rng.uniform(0.004, 0.0055), sag=0.012)
    for s in shapes:
        s.free()
    return _finish(PROPS[0], bm, tags, coll, offset)


def build_single(coll, offset):
    bm = bmesh.new()
    tags = _Tags(bm)
    shp = _egg_at(bm, tags, (0, 0, EGG_W * 0.47), 90, 8, EGG_LEN, EGG_W, EGG_SEED, seg=8, rows=5)
    h = _height_field([shp])
    silk_mat(bm, tags, h, 0.27, rings=3, segs=12, drape=0.42, seed=6)
    thread(bm, tags, h, (-0.22, -0.08), (0.20, 0.10), r=0.0045, sag=0.01)
    thread(bm, tags, h, (-0.12, 0.21), (0.10, -0.22), r=0.004, sag=0.01)
    shp.free()
    return _finish(PROPS[1], bm, tags, coll, offset)


def build_hatched(coll, offset, seg=16, rows=4, thick=0.009):
    """The bottom of an egg standing a little tilted, torn open and empty: outer shell, inner shell and the torn edge
    between them (one closed piece, so the normal recalc gets both sides right); the rim's teeth peel outward."""
    bm = bmesh.new()
    tags = _Tags(bm)
    L, W = EGG_LEN * 1.02, EGG_W * 1.02
    tilt = math.radians(12)
    Rm = Matrix.Rotation(tilt, 3, 'X') @ Matrix.Rotation(math.radians(90), 3, 'X')      # egg +Y up, leaning
    lift = Vector((0, 0, L * 0.5 * 0.97 + 0.01))
    rng = np.random.default_rng(7)
    rim = np.clip(0.30 + 0.16 * np.sin(np.arange(seg) * 2.4 + 0.7) * rng.uniform(0.4, 1.0, seg)
                  + rng.uniform(-0.12, 0.12, seg), -0.05, 0.55)
    rim[[3, 4, 11]] = (-0.12, 0.0, -0.06)                    # two deep tears
    rim = list(rim)
    lo, hi = min(rim), max(rim)

    def pt(x, th, inset=0.0, peel=0.0):
        r = float(_radius(x, W)) - inset + 0.07 * peel
        return Rm @ Vector((r * math.cos(th), x * L * 0.5 - 0.03 * peel, r * math.sin(th))) + lift

    outer, inner = [], []
    for k in range(1, rows + 1):
        ro, ri = [], []
        for j in range(seg):
            th = 2 * math.pi * j / seg
            x = -1 + (rim[j] + 1) * (k / rows) ** 0.85
            w = ((rim[j] - lo) / (hi - lo)) ** 1.5 * (1.0 if k == rows else 0.35 if k == rows - 1 else 0.0)
            ro.append(bm.verts.new(pt(x, th, peel=w)))
            ri.append(bm.verts.new(pt(x, th, inset=thick, peel=w)))
        outer.append(ro)
        inner.append(ri)
    po = bm.verts.new(pt(-1.0, 0))
    pi = bm.verts.new(pt(-1.0, 0) + Rm @ Vector((0, thick, 0)))
    eo = [bm.verts.new(v.co) for v in outer[-1]]          # the torn edge has its own verts (its own paint part)
    ei = [bm.verts.new(v.co) for v in inner[-1]]
    faces = []                                            # wound by hand: outer out, inner into the cavity, edge up
    for j in range(seg):
        j1 = (j + 1) % seg
        faces.append(bm.faces.new((po, outer[0][j], outer[0][j1])))
        faces.append(bm.faces.new((pi, inner[0][j1], inner[0][j])))
        for k in range(rows - 1):
            faces.append(bm.faces.new((outer[k][j], outer[k + 1][j], outer[k + 1][j1], outer[k][j1])))
            faces.append(bm.faces.new((inner[k][j], inner[k][j1], inner[k + 1][j1], inner[k + 1][j])))
        faces.append(bm.faces.new((eo[j], ei[j], ei[j1], eo[j1])))
    for f in faces:
        f.tag = True
    for pole, ring in ((po, outer), (pi, inner)):        # seams: up one side, and round the rim on both shells
        line = [pole] + [r[0] for r in ring]
        for p, q in zip(line[:-1], line[1:]):
            e = bm.edges.get((p, q))
            if e:
                e.seam = True
        for j in range(seg):
            e = bm.edges.get((ring[-1][j], ring[-1][(j + 1) % seg]))
            if e:
                e.seam = True
    tags.tag([po] + [v for r in outer for v in r], PART['egg'], t=0.0, u=0.5)
    tags.tag([pi] + [v for r in inner for v in r], PART['inner'], t=0.0, u=0.5)
    for k in range(rows):                                # t = how far up the shell, for the paint
        for j in range(seg):
            outer[k][j][tags.t] = inner[k][j][tags.t] = (k + 1) / rows
    tags.tag(eo + ei, PART['rim'], t=1.0, u=0.5)
    e = bm.edges.get((eo[0], ei[0]))                    # the edge band unwraps as one strip
    if e:
        e.seam = True
    silk_mat(bm, tags, lambda x, y: 0.0, 0.29, rings=3, segs=12, drape=0.0, seed=8)      # flat: under the cup
    return _finish(PROPS[2], bm, tags, coll, offset)


# ----------------------------------------------------------------------------------------- paint
def shell_colour(P, N, shape):
    """Leathery egg shell: cream, mottled, freckled, finely wrinkled. Shared by the props and the broodmother's laid
    egg. Returns (colour, smoothness) arrays of `shape`."""
    from bug_common import smoothstep as ss
    c0, c1, c2 = hexc('#eadfc2'), hexc('#cdbd96'), hexc('#a08b66')
    mot = fbm(P * 9.0, 3, seed=81)
    col = np.tile(c0, shape + (1,)) * 1.0
    m = np.clip(0.45 + 0.6 * mot, 0, 1)[..., None]
    col = col * (1 - m * 0.55) + c1 * (m * 0.55)
    frk = ss(0.66, 0.82, fbm(P * 55.0, 2, seed=82))[..., None]
    col = col * (1 - 0.5 * frk) + c2 * (0.5 * frk)
    wr = vnoise(np.stack([P[..., 0] * 140, P[..., 1] * 40, P[..., 2] * 140], -1), seed=83)
    col = col * (0.93 + 0.1 * wr[..., None])
    col = col * (0.95 + 0.08 * ss(0.0, 0.9, N[..., 2])[..., None])
    smooth = 0.34 + 0.06 * mot
    return col, smooth


def paint_props(D):
    import spider_paint as SP
    P, N, part, t, u, ao = D['P'], D['N'], D['part'], D['t'], D['u'], D['ao']
    shape = part.shape
    col, smooth = shell_colour(P, N, shape)
    egg = part == PART['egg']
    wisp = np.maximum(1 - np.abs(fbm(np.stack([P[..., 0] * 30 + P[..., 2] * 12, P[..., 1] * 30, P[..., 2] * 9], -1), 3, seed=91)) * 9,
                      1 - np.abs(fbm(np.stack([P[..., 1] * 28 - P[..., 2] * 10, P[..., 0] * 26, P[..., 2] * 11], -1), 3, seed=92)) * 9)
    wisp = np.clip(wisp, 0, 1) * smoothstep(0.75, 0.2, u)                      # thicker toward the bottom
    col = SP._mix(col, hexc('#f3f0e8'), 0.75 * wisp * egg)
    smooth = np.where(egg, smooth * (1 - 0.5 * wisp), smooth)
    inner = part == PART['inner']
    ic = SP._mix(np.tile(hexc('#5f4c3c'), shape + (1,)), hexc('#8a775a'), 0.4 + 0.4 * fbm(P * 20, 3, seed=84))
    goo = smoothstep(0.55, 0.8, fbm(P * 35, 2, seed=85))
    ic = SP._mix(ic, hexc('#a39465'), 0.5 * goo)
    ic = SP._mix(ic, hexc('#3b2e24'), 0.5 * smoothstep(0.6, 0.15, t))          # dark at the bottom of the cup
    col = np.where(inner[..., None], ic, col)
    smooth = np.where(inner, 0.62, smooth)
    rim = part == PART['rim']
    col = np.where(rim[..., None], SP._mix(np.tile(hexc('#efe3c0'), shape + (1,)), hexc('#c8b487'), 0.5 + 0.4 * fbm(P * 60, 2, seed=86)), col)
    smooth = np.where(rim, 0.2, smooth)
    silk = part == PART['silk']
    fib = fbm(np.stack([P[..., 0] * 70 + P[..., 1] * 30, P[..., 1] * 70 - P[..., 0] * 25, P[..., 2] * 40], -1), 3, seed=87)
    fib2 = fbm(np.stack([P[..., 0] * 25 - P[..., 1] * 80, P[..., 1] * 25 + P[..., 0] * 80, P[..., 2] * 40], -1), 3, seed=88)
    sc = SP._mix(np.tile(hexc('#e6e1d4'), shape + (1,)), hexc('#c5bba5'), 0.3 + 0.4 * fbm(P * 8, 2, seed=89))
    sc = sc * (0.88 + 0.1 * fib[..., None] + 0.08 * fib2[..., None])
    sc = SP._mix(sc, hexc('#8a7a60'), 0.65 * smoothstep(0.6, 1.0, t))         # earth caught in the edge
    sc = SP._mix(sc, hexc('#a7987a'), 0.35 * smoothstep(0.62, 0.35, ao))       # grime where it meets the eggs
    col = np.where(silk[..., None], sc, col)
    smooth = np.where(silk, 0.18, smooth)
    thr = part == PART['thread']
    col = np.where(thr[..., None], np.tile(hexc('#f5f2ea'), shape + (1,)), col)
    smooth = np.where(thr, 0.3, smooth)
    light = 0.76 + 0.32 * (N[..., 2] * 0.5 + 0.5)
    aot = 0.42 + 0.58 * np.clip(ao, 0, 1)
    shaded = col * (light * aot)[..., None] + ((1 - aot) * 0.10)[..., None] * np.array([0.25, 0.2, 0.35])
    return np.clip(shaded, 0, 1), np.clip(smooth, 0, 1)


UV_SCALE = {PART['egg']: 1.0, PART['inner']: 0.8, PART['rim']: 0.7, PART['silk']: 0.9, PART['thread']: 0.5}


def unwrap(obs, margin=0.006):
    """One UV layout for all the props (they share T_SpiderEggs)."""
    vl = bpy.context.view_layer
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in obs:
        o.select_set(True)
    vl.objects.active = obs[0]
    parts = {}
    for o in obs:
        att = o.data.color_attributes["info"]
        buf = np.empty(len(o.data.vertices) * 4, dtype=np.float32)
        att.data.foreach_get('color', buf)
        parts[o.name] = np.rint(buf.reshape(-1, 4)[:, 0] * 255).astype(int)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.unwrap(method='ANGLE_BASED', fill_holes=True, correct_aspect=True, margin=0.0)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode='OBJECT')             # (bmesh.from_edit_mesh mixes the objects up in multi-edit)
    for o in obs:
        me = o.data
        uv = np.empty(len(me.loops) * 2, np.float32)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        for p in me.polygons:
            k = UV_SCALE.get(int(parts[o.name][p.vertices[0]]), 1.0)
            if k != 1.0:
                uv[p.loop_start:p.loop_start + p.loop_total] *= k
        me.uv_layers.active.data.foreach_set("uv", uv.ravel())
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(margin=margin, rotate=True)
    bpy.ops.object.mode_set(mode='OBJECT')


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def build_props(size=512):
    """Scene SpiderEggs: the three props, one UV layout, T_SpiderEggs, M_SpiderEggs. Returns a report."""
    import bug_scene, spider_paint as SP
    scn = bug_scene.setup_scene("SpiderEggs", prefix="EGG_", scale=0.42)
    bug_scene.show_scene(scn)
    coll = get_coll("EGG_Props")
    obs = [build_clutch(coll, (-SPACING, 0, 0)), build_single(coll, (0, 0, 0)), build_hatched(coll, (SPACING, 0, 0))]
    unwrap(obs)
    rep = {"tris": {o.name: tri_count(o) for o in obs}}
    D = SP.bake_data(obs, size=size, ao_samples=96, ao_dist=0.22)
    col, smooth = paint_props(D)
    rep["texture"] = SP.write_texture(D, col, smooth, TEX, obs[0], MAT)
    rep["uv_layout"] = SP.draw_uv_layout(obs, "eggs_uv_layout", 1024, bpy.data.images[TEX])
    m = bpy.data.materials[MAT]
    for o in obs[1:]:
        o.data.materials.clear()
        o.data.materials.append(m)
    SP.clean_bakes()
    rep["coverage"] = float(D['valid'].mean())
    return rep


def export_props():
    """export/SpiderEgg_*.fbx, each with its origin on the ground under its middle."""
    import bug_export
    out = []
    os.makedirs(bug_export.EXPORT, exist_ok=True)
    for n in PROPS:
        ob = bpy.data.objects[n]
        keep = ob.location.copy()
        ob.location = (0, 0, 0)
        bpy.context.view_layer.update()
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.hide_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        path = os.path.join(bug_export.EXPORT, n + ".fbx")
        opts = dict(bug_export.FBX)
        opts.pop("use_armature_deform_only", None)
        bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'}, **opts)
        ob.select_set(False)
        ob.location = keep
        out.append(path)
    return out
