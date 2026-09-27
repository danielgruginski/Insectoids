"""Shared helpers for the insectoid builds: lofted tubes that mark their own UV seams, mesh objects, collections,
vectorised noise for per-texel painting.

Coordinates: metres, Z up, the creature faces -Y (Blender front view), its left side is +X.
Adapted from Goblins/src/gob_common.py.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix

ROOT = r"E:\Unity\Projects\GameArtGeneration\Insectoids"


def _cr(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)


def spline(ctrl, per_seg=4):
    """Uniform Catmull-Rom through the control rows (any number of columns)."""
    c = np.asarray(ctrl, float)
    if per_seg <= 1:
        return c.copy()
    ext = np.vstack([2 * c[0] - c[1], c, 2 * c[-1] - c[-2]])
    out = []
    for i in range(len(c) - 1):
        for k in range(per_seg):
            out.append(_cr(ext[i], ext[i + 1], ext[i + 2], ext[i + 3], k / per_seg))
    out.append(c[-1])
    return np.array(out)


def loft(bm, rows, up=(0, 0, 1), seg=16, per_seg=4, cap0=0.8, cap1=0.8, capk=3, shape=1.0, seam=-0.5 * math.pi,
         xform=None, bulge=None, split=False):
    """Closed tube through control rows (x, y, z, a, b, c); returns its BMVerts.

    a = radius along the side axis S, b = radius toward +N, c = radius toward -N, where N is `up` made
    perpendicular to the path and S = T x N. cap0/cap1 scale the rounded end caps (0 = flat pole), capk rings each.
    `seam` is the angle (0 = +S, pi/2 = +N) of the one line cut open for the UVs; it runs pole to pole, so every
    tube unwraps as one piece. split=True cuts along both sides instead (a quarter turn either way from `seam`), so
    a big rounded body unwraps as a top and a bottom half without squashing the middle of its back. xform (Matrix) maps the tube from its build space. bulge(t, th) -> radius factor.
    """
    rows = spline(rows, per_seg)
    P = rows[:, :3].copy()
    n = len(P)
    T = np.gradient(P, axis=0)
    T /= np.linalg.norm(T, axis=1)[:, None]
    U = np.array(up, float)
    rings = []
    for i in range(n):
        t = T[i]
        N = U - np.dot(U, t) * t
        N /= np.linalg.norm(N)
        S = np.cross(t, N)
        a, b, c = rows[i, 3], rows[i, 4], rows[i, 5]
        ring = []
        for j in range(seg):
            th = seam + 2 * math.pi * j / seg
            s, u = math.cos(th), math.sin(th)
            if shape != 1.0:
                s = math.copysign(abs(s) ** shape, s)
                u = math.copysign(abs(u) ** shape, u)
            k = bulge(i / (n - 1), th) if bulge is not None else 1.0
            ring.append(P[i] + (S * a * s + N * (b if u >= 0 else c) * u) * k)
        rings.append((np.array(ring), P[i], t, min(a, b, c)))

    def cap_rings(ring, center, t, r, sign, f):
        out = []
        for k in range(1, capk):
            ph = (k / capk) * math.pi / 2
            out.append(center + (ring - center) * math.cos(ph) + sign * t * r * f * math.sin(ph))
        return out, center + sign * t * r * f

    all_rings = [r[0] for r in rings]
    if cap0 > 0:
        extra, pole0 = cap_rings(rings[0][0], rings[0][1], rings[0][2], rings[0][3], -1, cap0)
        all_rings = extra[::-1] + all_rings
    else:
        pole0 = rings[0][1]
    if cap1 > 0:
        extra, pole1 = cap_rings(rings[-1][0], rings[-1][1], rings[-1][2], rings[-1][3], 1, cap1)
        all_rings = all_rings + extra
    else:
        pole1 = rings[-1][1]

    M = xform if xform is not None else Matrix.Identity(4)
    vr = [[bm.verts.new(M @ Vector(p)) for p in ring] for ring in all_rings]
    v0 = bm.verts.new(M @ Vector(pole0))
    v1 = bm.verts.new(M @ Vector(pole1))
    for i in range(len(vr) - 1):
        a, b = vr[i], vr[i + 1]
        for j in range(seg):
            j1 = (j + 1) % seg
            bm.faces.new((a[j], a[j1], b[j1], b[j]))
    for j in range(seg):
        bm.faces.new((v0, vr[0][(j + 1) % seg], vr[0][j]))
        bm.faces.new((v1, vr[-1][j], vr[-1][(j + 1) % seg]))
    # the UV cut: pole -> ring 0 -> ... -> last ring -> pole, along j = 0 (or along both sides)
    for jc in ((seg // 4, (3 * seg) // 4) if split else (0,)):
        line = [v0] + [r[jc] for r in vr] + [v1]
        for p, q in zip(line[:-1], line[1:]):
            e = bm.edges.get((p, q))
            if e is not None:
                e.seam = True
    return [v for r in vr for v in r] + [v0, v1]


def dome(bm, center, normal, radius, height, seg=10, rings=3, xform=None):
    """Open spherical cap (an eye): base circle of `radius` sunk into the surface, apex `height` out along normal.
    Disk topology, so it unwraps without seams. Returns its BMVerts."""
    n = Vector(normal).normalized()
    t = n.orthogonal().normalized()
    b = n.cross(t)
    c = Vector(center)
    # sphere through the base circle and the apex
    R = (radius * radius + height * height) / (2 * height)
    th_max = math.asin(min(1.0, radius / R))
    M = xform if xform is not None else Matrix.Identity(4)
    verts = []
    ring_prev = None
    apex = bm.verts.new(M @ (c + n * height))
    for k in range(1, rings + 1):
        th = th_max * k / rings
        r = R * math.sin(th)
        h = height - R * (1 - math.cos(th))
        ring = [bm.verts.new(M @ (c + n * h + (t * math.cos(2 * math.pi * j / seg) + b * math.sin(2 * math.pi * j / seg)) * r))
                for j in range(seg)]
        if ring_prev is None:
            for j in range(seg):
                bm.faces.new((apex, ring[j], ring[(j + 1) % seg]))
        else:
            for j in range(seg):
                j1 = (j + 1) % seg
                bm.faces.new((ring_prev[j], ring[j], ring[j1], ring_prev[j1]))
        verts += ring
        ring_prev = ring
    return [apex] + verts


def cone(bm, base, tip, r0, seg=4, xform=None, bend=None):
    """Closed pointed cone (spine, claw, fang). bend = sideways offset vector for the tip half (curved fang).
    Returns its BMVerts."""
    base, tip = Vector(base), Vector(tip)
    d = tip - base
    L = d.length
    z = d.normalized()
    x = z.orthogonal().normalized()
    y = z.cross(x)
    M = xform if xform is not None else Matrix.Identity(4)
    rows = 3 if bend is not None else 1
    rings = []
    for k in range(rows):
        f = k / rows
        off = Vector(bend) * (f * f) if bend is not None else Vector()
        r = r0 * (1 - f)
        rings.append([bm.verts.new(M @ (base + d * f + off + (x * math.cos(2 * math.pi * j / seg) + y * math.sin(2 * math.pi * j / seg)) * r))
                      for j in range(seg)])
    apex = bm.verts.new(M @ (tip + (Vector(bend) if bend is not None else Vector())))
    for a, b in zip(rings[:-1], rings[1:]):
        for j in range(seg):
            j1 = (j + 1) % seg
            bm.faces.new((a[j], a[j1], b[j1], b[j]))
    for j in range(seg):
        bm.faces.new((rings[-1][j], rings[-1][(j + 1) % seg], apex))
    bm.faces.new(list(reversed(rings[0])))
    line = [r[0] for r in rings] + [apex]              # UV cut: up one side, and around the base
    for p, q in zip(line[:-1], line[1:]):
        e = bm.edges.get((p, q))
        if e is not None:
            e.seam = True
    for j in range(seg):
        e = bm.edges.get((rings[0][j], rings[0][(j + 1) % seg]))
        if e is not None:
            e.seam = True
    return [v for r in rings for v in r] + [apex]


def mesh_obj(name, bm, coll=None, recalc=True):
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.get(name)
    if me is not None and me.users == 0:          # an orphan (e.g. left by a join) keeps its vertex-group names
        bpy.data.meshes.remove(me)                # on the mesh (Blender 4): start fresh, or new groups get .001
        me = None
    if me is None:
        me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, me)
    else:
        ob.data = me
    if coll is not None and ob.name not in coll.objects:
        coll.objects.link(ob)
    return ob


def get_coll(name, parent=None, scene=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    par = parent if parent is not None else (scene or bpy.context.scene).collection
    if c.name not in [x.name for x in par.children]:
        par.children.link(c)
    return c


def remove_obj(name):
    ob = bpy.data.objects.get(name)
    if ob is not None:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Armature):
                bpy.data.armatures.remove(data)


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def fill_gutters(img, mask):
    """Fill every texel outside the UV islands (mask False) with the colour of the nearest island (push-pull),
    so mip-maps never mix the background into the edges. Keeps alpha as it is inside the islands."""
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    a = a.reshape(h, w, 4)
    m = np.asarray(mask).astype(np.float32)

    def pushpull(col, wt):
        hh, ww = wt.shape
        if hh <= 1 and ww <= 1:
            return col
        h2, w2 = (hh + 1) // 2, (ww + 1) // 2
        C = col.shape[-1]
        cp = np.zeros((h2 * 2, w2 * 2, C), np.float32)
        wp = np.zeros((h2 * 2, w2 * 2), np.float32)
        cp[:hh, :ww] = col * wt[..., None]
        wp[:hh, :ww] = wt
        cs = cp.reshape(h2, 2, w2, 2, C).sum((1, 3))
        ws = wp.reshape(h2, 2, w2, 2).sum((1, 3))
        coarse = np.where(ws[..., None] > 0, cs / np.maximum(ws, 1e-6)[..., None], 0.0)
        coarse = pushpull(coarse, np.minimum(ws, 1.0))
        up = np.repeat(np.repeat(coarse, 2, 0), 2, 1)[:hh, :ww]
        return np.where(wt[..., None] > 0.5, col, up)

    a[...] = pushpull(a, m)
    img.pixels.foreach_set(a.ravel())
    return float(m.mean())


# ----------------------------------------------------------------------------------------- noise (numpy)
def _hash3(ix, iy, iz, seed):
    h = (ix * 374761393 + iy * 668265263 + iz * 2147483647 + seed * 144665) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFF) / 65535.0


def vnoise(p, seed=0):
    """Smooth value noise in [-1, 1] at points p (..., 3)."""
    p = np.asarray(p, float)
    i = np.floor(p).astype(np.int64)
    f = p - i
    u = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = ((u[..., 0] if dx else 1 - u[..., 0]) * (u[..., 1] if dy else 1 - u[..., 1]) *
                     (u[..., 2] if dz else 1 - u[..., 2]))
                out = out + w * _hash3(i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz, seed)
    return out * 2 - 1


def fbm(p, octaves=4, seed=0, lac=2.0, gain=0.5):
    p = np.asarray(p, float)
    tot, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        tot = tot + amp * vnoise(p * (lac ** o), seed + o * 31)
        norm += amp
        amp *= gain
    return tot / norm


def hexc(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def srgb_to_lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)
