"""Giant wasp (hornet-like): anatomy, bone table and the game mesh, built in the bind pose, which is the hover.

The wasp faces -Y, left side +X, metres. ~1.5 m from mandibles to stinger, ~2.2 m wingspan, hovering with the
thorax 1.7 m up (Root and Motion stay on the ground below it). Like the spider it is all rigid shells:
  head (eyes, ocelli, mandibles, elbowed antennae), thorax, a thin petiole (the wasp waist, blended between Body and
  Gaster1), and a gaster of six telescoping plates on three bones (Gaster1: plates 1-2, Gaster2: 3-4, Gaster3: 5-6 and
  the stinger), so it can curl forward under the body to sting;
  six legs of four segments (coxa, femur, tibia, tarsus), hanging in flight;
  four wings: flat membranes on their own bones and material (WaspWings, joined into WaspBody after the bake).
Bone frames: Body/Head +Y forward, +Z up; gaster +Y backward along the abdomen, +Z up (positive X rotation lifts the
tip; negative curls it under); legs as the spider's (+X hinge, positive X rotation raises a segment); wings +Y along
the span, +Z the wing's upper face, positive X rotation = upstroke on either side.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from bug_common import loft, dome, cone, mesh_obj, get_coll, remove_obj, smoothstep
from spider_body import leg_frames, _frame, _Parts, _mat4

HOVER = 1.7                                   # thorax centre height in the bind pose (hover)
H = Vector((0, 0, HOVER))

THORAX_ROWS = [   # x, y, z (relative to the thorax centre), half-width, top, bottom
    (0, -0.235, 0.020, 0.075, 0.065, 0.060),
    (0, -0.200, 0.030, 0.150, 0.130, 0.120),
    (0, -0.120, 0.030, 0.190, 0.170, 0.160),
    (0, 0.000, 0.020, 0.200, 0.190, 0.170),
    (0, 0.100, 0.015, 0.190, 0.185, 0.160),
    (0, 0.180, 0.000, 0.150, 0.150, 0.130),
    (0, 0.240, -0.010, 0.080, 0.080, 0.070),
]
HEAD_C = Vector((0, -0.355, 0.010))
HEAD_ROWS = [
    (0, -0.450, -0.015, 0.105, 0.095, 0.110),
    (0, -0.425, -0.005, 0.155, 0.130, 0.145),
    (0, -0.375, 0.000, 0.175, 0.140, 0.150),
    (0, -0.315, 0.008, 0.162, 0.130, 0.125),
    (0, -0.268, 0.012, 0.095, 0.085, 0.080),
]
NECK = Vector((0, -0.255, 0.015))
PETIOLE = Vector((0, 0.262, -0.025))
GASTER_DIR = Vector((0, math.cos(math.radians(14)), -math.sin(math.radians(14))))   # back and a little down
# plates: length, front radius, widest, rear radius
PLATES = [(0.140, 0.075, 0.165, 0.172), (0.150, 0.160, 0.200, 0.196), (0.150, 0.185, 0.205, 0.190),
          (0.130, 0.175, 0.180, 0.155), (0.110, 0.140, 0.135, 0.100), (0.100, 0.090, 0.075, 0.025)]
PLATE_OVERLAP = 0.032
PLATE_BONE = ["Gaster1", "Gaster1", "Gaster2", "Gaster2", "Gaster3", "Gaster3"]
STINGER_LEN = 0.14

# legs: coxa base (left side, relative to the thorax centre), lengths, hanging pose (yaw from lateral toward the
# front; absolute plane angles of coxa, femur, tibia, tarsus from the body's horizontal)
LEG_SEGS = ("Coxa", "Femur", "Tibia", "Tarsus")
LEGS = [
    dict(C=(0.060, -0.140, -0.125), L=(0.075, 0.19, 0.20, 0.15), r=(0.034, 0.028, 0.021, 0.015), yaw=35,
         pose=(-40, -6, -62, -100)),
    dict(C=(0.075, -0.020, -0.140), L=(0.080, 0.22, 0.23, 0.17), r=(0.036, 0.030, 0.022, 0.015), yaw=-20,
         pose=(-45, -10, -72, -112)),
    dict(C=(0.070, 0.090, -0.130), L=(0.090, 0.27, 0.29, 0.22), r=(0.038, 0.032, 0.023, 0.016), yaw=-58,
         pose=(-45, -14, -80, -122)),
]

# wings: root (left, relative to the thorax centre), span direction (sweep back, dihedral), outline in the wing plane
# (u along the span, v toward the leading edge), metres
FOREWING = dict(root=(0.105, -0.075, 0.150), sweep=18, dihedral=8, outline=[
    (0.00, 0.030), (0.30, 0.060), (0.70, 0.070), (0.90, 0.050), (0.955, 0.000), (0.90, -0.080), (0.70, -0.140),
    (0.45, -0.170), (0.20, -0.140), (0.06, -0.080), (0.00, -0.030)])
HINDWING = dict(root=(0.100, 0.055, 0.130), sweep=30, dihedral=4, outline=[
    (0.00, 0.020), (0.20, 0.050), (0.45, 0.052), (0.60, 0.022), (0.625, -0.010), (0.55, -0.070), (0.35, -0.120),
    (0.15, -0.110), (0.03, -0.060), (0.00, -0.020)])

EYES = [((0.92, -0.28, 0.20), 0.075, 0.035), ((0.93, -0.25, -0.05), 0.070, 0.032)]   # two domes = one kidney eye
OCELLI = [((0.0, -0.45, 0.89), 0.017, 0.010), ((0.22, -0.28, 0.93), 0.014, 0.008)]

PART = dict(head=0, eye=1, ocellus=2, mandible=3, antenna=4, thorax=5, petiole=6, plate=10, stinger=16, leg=20,
            forewing=40, hindwing=41)         # plates 10..15, legs 20 + 4 * pair + segment

LM = {}


def _wing_frame(side, spec):
    """Rest frame of a wing: Y along the span (outward, swept back, dihedral up), Z the upper face."""
    sw, dh = math.radians(spec['sweep']), math.radians(spec['dihedral'])
    Y = Vector((side * math.cos(sw) * math.cos(dh), math.sin(sw) * math.cos(dh), math.sin(dh)))
    return _frame(H + Vector((side * spec['root'][0], spec['root'][1], spec['root'][2])), Y, (0, 0, 1))


def leg_spec(pair, side):
    s = LEGS[pair]
    C = H + Vector((side * s['C'][0], s['C'][1], s['C'][2]))
    return C, s['L'], s['yaw'], s['pose'], s['r']


def leg_name(pair, side, seg):
    return f"Leg{'L' if side > 0 else 'R'}{pair + 1}_{seg}"


def plate_axis():
    """Start point of each plate along the gaster axis (plates overlap by PLATE_OVERLAP)."""
    starts, d = [], 0.0
    for L, *_ in PLATES:
        starts.append(d)
        d += L - PLATE_OVERLAP
    return starts, d + PLATE_OVERLAP


def rest_bones():
    B = {}
    up_front = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0))).transposed()      # as the spider: identity in Unity
    B["Root"] = (Vector((0, 0, 0)), up_front, 0.25, None, False)
    B["Motion"] = (Vector((0, 0, 0)), up_front, 0.2, None, True)
    B["Body"] = (*_frame(H, (0, -1, 0), (0, 0, 1)), 0.25, "Root", True)
    B["Head"] = (*_frame(H + NECK, (0, -1, 0.1), (0, 0, 1)), 0.18, "Body", True)
    starts, total = plate_axis()
    g0 = H + PETIOLE
    for k, (name, idx) in enumerate((("Gaster1", 0), ("Gaster2", 2), ("Gaster3", 4))):
        head = g0 + GASTER_DIR * starts[idx]
        B[name] = (*_frame(head, GASTER_DIR, (0, 0, 1)), 0.2, "Body" if k == 0 else ("Gaster1", "Gaster2")[k - 1], True)
    tip = g0 + GASTER_DIR * total
    LM['gaster_tip'] = tip
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        mx = Vector((side, 1, 1))
        base = H + Vector((0.058, -0.440, -0.095)) * mx
        mtip = H + Vector((0.012, -0.505, -0.140)) * mx
        B[f"Mandible{sfx}"] = (*_frame(base, mtip - base, (0, 0, -1)), (mtip - base).length, "Head", True)
        a0 = H + Vector((0.045, -0.445, 0.070)) * mx
        a1 = H + Vector((0.075, -0.500, 0.215)) * mx                      # elbow of the antenna
        a2 = H + Vector((0.300, -0.830, 0.330)) * mx
        B[f"Antenna{sfx}_Scape"] = (*_frame(a0, a1 - a0, (0, -1, 0)), (a1 - a0).length, "Head", True)
        B[f"Antenna{sfx}_Flagellum"] = (*_frame(a1, a2 - a1, (0, 0, 1)), (a2 - a1).length, f"Antenna{sfx}_Scape", True)
        for wname, spec in (("Forewing", FOREWING), ("Hindwing", HINDWING)):
            h, fr = _wing_frame(side, spec)
            B[f"{wname}{sfx}"] = (h, fr, max(u for u, v in spec['outline']), "Body", True)
        for pair in range(3):
            C, Ls, yaw, pose, _ = leg_spec(pair, side)
            e_r = Vector((side * math.cos(math.radians(yaw)), -math.sin(math.radians(yaw)), 0))
            fr = leg_frames(C, Ls, e_r, [math.radians(a) for a in pose])
            par = "Body"
            for j, seg in enumerate(LEG_SEGS):
                n = leg_name(pair, side, seg)
                B[n] = (fr[j][0], fr[j][1], Ls[j], par, True)
                par = n
    B["Socket_Mouth"] = (*_frame(H + Vector((0, -0.52, -0.12)), (0, -1, 0), (0, 0, 1)), 0.06, "Head", False)
    B["Socket_Stinger"] = (*_frame(tip + GASTER_DIR * STINGER_LEN, GASTER_DIR, (0, 0, 1)), 0.06, "Gaster3", False)
    B["Socket_Saddle"] = (*_frame(H + Vector((0, 0.02, 0.2)), (0, 0, 1), (0, -1, 0)), 0.06, "Body", False)
    return B


# ----------------------------------------------------------------------------------------- mesh
def _ellipse_dome(bm, center, normal, ra, rb, height, up, seg=10, rings=2):
    """dome() stretched: radius ra along `up` (projected on the base plane), rb across."""
    n = Vector(normal).normalized()
    u = (Vector(up) - n * Vector(up).dot(n)).normalized()
    w = n.cross(u)
    vs = dome(bm, Vector((0, 0, 0)), n, 1.0, height / max(ra, rb), seg=seg, rings=rings)
    for v in vs:
        p = v.co
        a, b, c = p.dot(u), p.dot(w), p.dot(n)
        v.co = Vector(center) + u * a * ra + w * b * rb + n * c * max(ra, rb)
    return vs


def build_body():
    """WaspBody (the shells, one material) and WaspWings (the membranes, their own material and UVs)."""
    B = rest_bones()
    bm = bmesh.new()
    P = _Parts(bm)

    vs = loft(bm, [(x, y, z + HOVER, a, b, c) for x, y, z, a, b, c in THORAX_ROWS], up=(0, 0, 1), seg=16, per_seg=1,
              cap0=0.5, cap1=0.5, capk=2, split=True)
    P.tag(vs, "Body", PART['thorax'], t_axis=(-0.25, 0.25))
    vs = loft(bm, [(x, y, z + HOVER, a, b, c) for x, y, z, a, b, c in HEAD_ROWS], up=(0, 0, 1), seg=16, per_seg=1,
              cap0=0.6, cap1=0.4, capk=2, split=True)
    P.tag(vs, "Head", PART['head'], t_axis=(-0.46, -0.26))
    tmp = bmesh.new()
    loft(tmp, [(x, y, z + HOVER, a, b, c) for x, y, z, a, b, c in HEAD_ROWS], up=(0, 0, 1), seg=16, per_seg=1,
         cap0=0.6, cap1=0.4, capk=2)
    bvh = BVHTree.FromBMesh(tmp)
    tmp.free()
    hc = H + HEAD_C
    for side in (1, -1):
        for d, r, h in EYES:                                           # kidney-shaped compound eyes
            dv = Vector((side * d[0], d[1], d[2])).normalized()
            hit, nrm, _, _ = bvh.ray_cast(hc, dv, 1.0)
            if hit is None:
                continue
            n = (nrm.normalized() + dv).normalized()
            vs = _ellipse_dome(bm, hit - n * h * 0.4, n, r * 1.25, r * 0.8, h * 1.4, (0, 0, 1), seg=12, rings=2)
            P.tag(vs, "Head", PART['eye'], t_axis=(-0.46, -0.26))
        for d, r, h in OCELLI:
            dv = Vector((side * d[0], d[1], d[2])).normalized()
            hit, nrm, _, _ = bvh.ray_cast(hc, dv, 1.0)
            if hit is None or (d[0] == 0 and side < 0):
                continue
            n = nrm.normalized()
            vs = dome(bm, hit - n * h * 0.3, n, r, h, seg=6, rings=1)
            P.tag(vs, "Head", PART['ocellus'], t_axis=(-0.46, -0.26))
    # petiole: the wasp waist
    p0 = H + Vector((0, 0.215, -0.012))
    p1 = H + PETIOLE + GASTER_DIR * 0.06
    rows = [(p0.x, p0.y, p0.z, 0.045, 0.045, 0.045), ((p0.x + p1.x) / 2, (p0.y + p1.y) / 2, (p0.z + p1.z) / 2, 0.030, 0.030, 0.030),
            (p1.x, p1.y, p1.z, 0.045, 0.045, 0.045)]
    vs = loft(bm, rows, up=(0, 0, 1), seg=8, per_seg=1, cap0=0, cap1=0)
    P.tag(vs, "Body", PART['petiole'], t_axis=(p0.y, p1.y))
    # gaster plates, each on its bone, built along the gaster axis
    starts, total = plate_axis()
    g0 = H + PETIOLE
    for k, ((L, rf, rm, rr), s0) in enumerate(zip(PLATES, starts)):
        bone = PLATE_BONE[k]
        h, fr, _, _, _ = B[bone]
        a = g0 + GASTER_DIR * s0
        pts = [(0.0, rf), (0.25, (rf + rm) / 2 * 1.02), (0.55, rm), (0.9, (rm + rr) / 2), (1.0, rr)]
        rows = []
        for t, r in pts:
            c = a + GASTER_DIR * (t * L)
            rows.append((c.x, c.y, c.z, r, r * 0.97, r * 0.9))
        last = k == len(PLATES) - 1
        vs = loft(bm, rows, up=(0, 0, 1), seg=16 if k < 4 else 12, per_seg=1, cap0=0.35, cap1=(1.0 if last else 0.25),
                  capk=2, split=True)
        P.tag(vs, bone, PART['plate'] + k, h, fr, 0.2)
        for v in vs:                                                    # t along the plate, for the bands
            v[P.t] = max(0.0, min(1.0, (v.co - a).dot(GASTER_DIR) / L))
    h, fr, _, _, _ = B["Gaster3"]
    tip = g0 + GASTER_DIR * total
    vs = cone(bm, tip - GASTER_DIR * 0.04, tip + GASTER_DIR * STINGER_LEN, 0.022, seg=5)
    P.tag(vs, "Gaster3", PART['stinger'], h, fr, 0.2)

    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        h, fr, L, _, _ = B[f"Mandible{sfx}"]                           # curved mandibles, folded in
        vs = cone(bm, (0, -0.01, 0), (0, L, 0), 0.030, seg=5, xform=_mat4(h, fr), bend=(-side * 0.0, 0, 0.02))
        P.tag(vs, f"Mandible{sfx}", PART['mandible'], h, fr, L)
        for nm, r0, r1 in (("Scape", 0.020, 0.016), ("Flagellum", 0.017, 0.012)):
            n = f"Antenna{sfx}_{nm}"
            h, fr, L, _, _ = B[n]
            k = 5 if nm == "Scape" else 9
            rows = [(0, L * i / (k - 1), 0, r0 + (r1 - r0) * i / (k - 1), r0 + (r1 - r0) * i / (k - 1),
                     r0 + (r1 - r0) * i / (k - 1)) for i in range(k)]
            if nm == "Flagellum":
                rows = [(x, y, z, a * (1.0 if i % 2 else 0.86), b * (1.0 if i % 2 else 0.86), c * (1.0 if i % 2 else 0.86))
                        for i, (x, y, z, a, b, c) in enumerate(rows)]          # beaded segments
            vs = loft(bm, rows, up=(0, 0, 1), seg=6, per_seg=1, cap0=0.6, cap1=0.9, capk=2, xform=_mat4(h, fr))
            P.tag(vs, n, PART['antenna'], h, fr, L)
        for pair in range(3):
            C, Ls, yaw, pose, radii = leg_spec(pair, side)
            for j, seg in enumerate(LEG_SEGS):
                n = leg_name(pair, side, seg)
                h, fr, L, _, _ = B[n]
                r = radii[j]
                if seg == "Tarsus":                                   # five little beads, then a claw
                    rows = [(0, L * i / 8, 0, r * (0.8 if i % 2 else 1.0), r * (0.8 if i % 2 else 1.0),
                             r * (0.8 if i % 2 else 1.0)) for i in range(9)]
                else:
                    rows = [(0, -0.08 * L, 0, r * 0.8, r * 0.8, r * 0.8), (0, 0.1 * L, 0, r, r * 1.05, r),
                            (0, 0.6 * L, 0, r * 1.02, r * 1.05, r), (0, L, 0, r * 0.85, r * 0.85, r * 0.85)]
                vs = loft(bm, rows, up=(0, 0, 1), seg=6 if seg != "Tarsus" else 5, per_seg=1, cap0=0.6,
                          cap1=(1.0 if seg == "Tarsus" else 0.0), capk=2, xform=_mat4(h, fr))
                P.tag(vs, n, PART['leg'] + 4 * pair + j, h, fr, L)
                if seg == "Tibia":                                    # a pair of spurs at the ankle
                    for sgn in (1, -1):
                        vs = cone(bm, (0, 0.85 * L, -r * 0.5), (sgn * 0.02, 1.08 * L, -r * 1.6), r * 0.35, seg=3,
                                  xform=_mat4(h, fr))
                        P.tag(vs, n, PART['leg'] + 4 * pair + j, h, fr, L)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    names = list(P.names)
    bone = [v[P.bone] for v in bm.verts]
    info = [(v[P.part], v[P.t], v[P.u]) for v in bm.verts]
    co_y = [v.co.y for v in bm.verts]
    coll = get_coll("WSP_Body")
    remove_obj("WaspBody")
    ob = mesh_obj("WaspBody", bm, coll, recalc=False)
    for p in ob.data.polygons:
        p.use_smooth = True
    groups = {n: ob.vertex_groups.new(name=n) for n in names}
    if "Gaster1" not in groups:
        groups["Gaster1"] = ob.vertex_groups.new(name="Gaster1")
    for vi, bi in enumerate(bone):
        if info[vi][0] == PART['petiole']:
            w = float(smoothstep(0.215, 0.33, co_y[vi]))
            if w < 1:
                groups["Body"].add([vi], 1 - w, 'REPLACE')
            if w > 0:
                groups["Gaster1"].add([vi], w, 'REPLACE')
        else:
            groups[names[bi]].add([vi], 1.0, 'REPLACE')
    att = ob.data.color_attributes.new("info", 'FLOAT_COLOR', 'POINT')
    att.data.foreach_set('color', np.array([(p / 255.0, t, u, 1.0) for p, t, u in info], dtype=np.float32).ravel())
    wings = build_wings(B)
    return ob, wings


def wing_uv(spec, u, v, v0):
    """Wing-plane coordinates (metres) -> UV: forewing in the top half (v0 = 0.5), hindwing in the bottom (v0 = 0)."""
    out = spec['outline']
    umax = max(p[0] for p in out)
    vmin, vmax = min(p[1] for p in out), max(p[1] for p in out)
    return (0.02 + 0.96 * u / umax, v0 + 0.02 + 0.46 * (v - vmin) / (vmax - vmin))


WING_V0 = {"Forewing": 0.5, "Hindwing": 0.0}


def build_wings(B):
    """Four flat membranes (outline fanned from its centre). Left and right share the UVs (mirrored)."""
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")      # same name as the body's unwrap, so the join merges them
    groups = []
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        for wname, spec in (("Forewing", FOREWING), ("Hindwing", HINDWING)):
            v0 = WING_V0[wname]
            h, fr, L, _, _ = B[f"{wname}{sfx}"]
            X, Y, Z = fr.col[0], fr.col[1], fr.col[2]
            lead = X if side > 0 else -X          # v (toward the leading edge) points forward on both sides
            out = spec['outline']
            cu = sum(p[0] for p in out) / len(out)
            cv = sum(p[1] for p in out) / len(out)
            pos = lambda u, v: h + Y * u + lead * v
            ring = [bm.verts.new(pos(u, v)) for u, v in out]
            c = bm.verts.new(pos(cu, cv))
            for i in range(len(ring)):
                j = (i + 1) % len(ring)
                a, b = (i, j) if (ring[i].co - c.co).cross(ring[j].co - c.co).dot(Z) > 0 else (j, i)
                f = bm.faces.new((c, ring[a], ring[b]))
                for loop, (uu, vv) in zip(f.loops, ((cu, cv), out[a], out[b])):
                    loop[uvl].uv = wing_uv(spec, uu, vv, v0)
            groups.append((f"{wname}{sfx}", ring + [c], PART['forewing'] if wname == "Forewing" else PART['hindwing']))
    bm.verts.index_update()
    idx = {v: i for i, v in enumerate(bm.verts)}
    coll = get_coll("WSP_Body")
    remove_obj("WaspWings")
    ob = mesh_obj("WaspWings", bm, coll, recalc=False)
    for p in ob.data.polygons:
        p.use_smooth = True
    for gname, verts, pid in groups:
        g = ob.vertex_groups.new(name=gname)
        g.add([idx[v] for v in verts], 1.0, 'REPLACE')
    att = ob.data.color_attributes.new("info", 'FLOAT_COLOR', 'POINT')
    rgba = np.zeros((len(ob.data.vertices), 4), dtype=np.float32)
    for gname, verts, pid in groups:
        for v in verts:
            rgba[idx[v]] = (pid / 255.0, 0, 0.5, 1)
    att.data.foreach_set('color', rgba.ravel())
    return ob


def tri_report(obs):
    out = {}
    for ob in obs:
        me = ob.data
        att = me.color_attributes["info"]
        part = np.array([round(att.data[i].color[0] * 255) for i in range(len(me.vertices))])
        for p in me.polygons:
            pid = int(part[p.vertices[0]])
            key = ("plate" if 10 <= pid < 16 else "leg" if 20 <= pid < 32 else
                   next((k for k, v in PART.items() if v == pid), str(pid)))
            out[key] = out.get(key, 0) + len(p.vertices) - 2
    out["total"] = sum(v for k, v in out.items())
    return out
