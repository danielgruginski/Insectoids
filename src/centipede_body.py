"""Giant centipede (Scolopendra-like): anatomy, the body chain, leg IK, the bone table and the game mesh (bind pose).

The centipede faces -Y, left side +X, metres. ~3.5 m long, the trunk 0.17 m off the ground: a head, 18 trunk segments
with a pair of legs each, and a tail segment with the long trailing terminal legs. Like the other insectoids it is all
rigid shells, one bone each: the head and segments form a chain (Root > Head > Seg01 > ... > Seg18 > Tail); legs are
two bones (femur, tibia with the claw) on their segment.

The body is posed as a path (centipede_anim): each chain element sits at a fixed arc length behind the head along a
curve, so the body keeps its length however the curve bends, rears or dives into the ground.

Frames: every chain bone has +Y forward along the body, +Z its back (dorsal). "Q space" of an element is its frame
with the axes of the rest world (left = +X, back = +Y, up = +Z), so leg geometry can use the spider's planar tools.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
from bug_common import loft, dome, cone, mesh_obj, get_coll, remove_obj, smoothstep
from spider_body import leg_frames, _frame, _Parts, _mat4

Z0 = 0.17                                    # trunk centre height when standing
N_SEG = 18
HEAD_LEN, SEG_LEN, TAIL_LEN = 0.24, 0.165, 0.16
# half-widths along the chain (head, 18 segments, tail), dorsal and ventral half-heights
WIDTH = [0.13, 0.12, 0.14] + [0.155, 0.16, 0.165] + [0.165] * 7 + [0.16, 0.155, 0.148, 0.14, 0.13, 0.12, 0.10]
DORSAL, VENTRAL = 0.062, 0.045

ELEMENTS = ["Head"] + [f"Seg{i:02d}" for i in range(1, N_SEG + 1)] + ["Tail"]
LENGTHS = [HEAD_LEN] + [SEG_LEN] * N_SEG + [TAIL_LEN]


def arc_positions():
    """Arc length of each chain element's centre behind the head centre (head = 0)."""
    s = [0.0]
    for i in range(1, len(LENGTHS)):
        s.append(s[-1] + 0.5 * (LENGTHS[i - 1] + LENGTHS[i]))
    return np.array(s)


S = arc_positions()
BODY_LEN = S[-1] + 0.5 * (LENGTHS[0] + LENGTHS[-1])
HEAD_Y = -0.5 * S[-1]                        # rest: head centre in front, the trunk centred on the origin

# legs, per segment: hip in Q space (left side), lengths, neutral foot (Q space, on the ground at rest)
def leg_dims(i):
    """Segment i = 1..18: femur, tibia lengths and the rest foot splay (front legs reach forward, rear legs back)."""
    t = (i - 1) / (N_SEG - 1)
    L1 = 0.20 + 0.04 * t
    L2 = 0.27 + 0.05 * t
    splay = -0.10 + 0.22 * t                 # foot y offset (Q space): forward (-) for the front legs
    return L1, L2, splay


HIP_X = 0.12
FOOT_OUT = 0.33                              # foot this far outside the hip
TAIL_LEG = (0.30, 0.34)                      # terminal legs: femur, tibia
TAIL_LEG_POSE = (-72, (8, -4))               # yaw from lateral (negative = backward), plane angles (femur, tibia)
ANTENNA = (0.30, 0.30)
FORCIPULE_LEN = 0.17

PART = dict(head=0, seg=10, tail=29, femur=40, tibia=41, claw=42, tail_femur=43, tail_tibia=44, antenna=45,
            forcipule=46, eye=47)            # segments: 10 + i (i = 1..18)

LM = {}


# ----------------------------------------------------------------------------------------- frames
def element_frame(pos, fwd, up):
    """Bone frame of a chain element: +Y forward, +Z up (orthogonalised), +X = Y x Z."""
    Y = Vector(fwd).normalized()
    Zh = Vector(up)
    Z = (Zh - Y * Zh.dot(Y)).normalized()
    X = Y.cross(Z)
    return Vector(pos), Matrix((X, Y, Z)).transposed()


def q_matrix(pos, frame):
    """Q space -> world: columns (left, back, up) = (-X, -Y, Z) of the bone frame, origin at the element centre."""
    X, Y, Z = frame.col[0], frame.col[1], frame.col[2]
    M = Matrix((-X, -Y, Z)).transposed().to_4x4()
    M.translation = pos
    return M


def rest_elements():
    """(position, frame) of every chain element in the bind pose: a straight body, head at -Y."""
    return [element_frame((0, HEAD_Y + s, Z0), (0, -1, 0), (0, 0, 1)) for s in S]


# ----------------------------------------------------------------------------------------- leg IK
def solve_leg2(C, L1, L2, target, side):
    """Two-bone planar IK in Q space (knee up). Returns (e_r, [femur, tibia] plane angles)."""
    d = Vector(target) - Vector(C)
    dh = Vector((d.x, d.y, 0.0))
    if dh.length < 1e-4:
        dh = Vector((side, 0, 0))
    e_r = dh.normalized()
    r, z = dh.length, d.z
    D = min(max(math.hypot(r, z), abs(L1 - L2) + 1e-4), (L1 + L2) * 0.999)
    beta = math.atan2(z, r)
    gamma = math.acos(max(-1.0, min(1.0, (L1 * L1 + D * D - L2 * L2) / (2 * L1 * D))))
    a1 = beta + gamma
    kx, kz = L1 * math.cos(a1), L1 * math.sin(a1)
    # the knee sits on the (r, z) line toward the target, so aim the tibia at the target scaled onto reach
    scale = D / max(math.hypot(r, z), 1e-6)
    a2 = math.atan2(z * scale - kz, r * scale - kx)
    return e_r, [a1, a2]


def leg_name(i, side, seg):
    return f"Leg{'L' if side > 0 else 'R'}{i:02d}_{seg}"


def rest_foot_q(i, side, z0=Z0):
    L1, L2, splay = leg_dims(i)
    return Vector((side * (HIP_X + FOOT_OUT), splay, -z0))


def hip_q(side):
    return Vector((side * HIP_X, 0.0, -0.01))


# ----------------------------------------------------------------------------------------- bone table
def rest_bones():
    B = {}
    up_front = Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0))).transposed()      # identity in Unity (see the spider)
    B["Root"] = (Vector((0, 0, 0)), up_front, 0.25, None, False)
    B["Motion"] = (Vector((0, 0, 0)), up_front, 0.2, None, True)
    els = rest_elements()
    par = "Root"
    for name, (p, fr), L in zip(ELEMENTS, els, LENGTHS):
        B[name] = (p, fr, L * 0.8, par, True)
        par = name
    for i in range(1, N_SEG + 1):
        p, fr = els[i]
        Q = q_matrix(p, fr)
        L1, L2, _ = leg_dims(i)
        for side in (1, -1):
            e_r, ang = solve_leg2(hip_q(side), L1, L2, rest_foot_q(i, side), side)
            frs = leg_frames(hip_q(side), (L1, L2), e_r, ang)
            for j, seg in enumerate(("Femur", "Tibia")):
                h, f3 = frs[j]
                M = Q @ _mat4(h, f3)
                n = leg_name(i, side, seg)
                B[n] = (M.translation.copy(), M.to_3x3().normalized(), (L1, L2)[j], f"Seg{i:02d}" if j == 0 else leg_name(i, side, "Femur"), True)
    p, fr = els[-1]
    Q = q_matrix(p, fr)
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        yaw, ang = TAIL_LEG_POSE
        e_r = Vector((side * math.cos(math.radians(yaw)), -math.sin(math.radians(yaw)), 0))
        frs = leg_frames(Vector((side * 0.08, 0.05, 0.0)), TAIL_LEG, e_r, [math.radians(a) for a in ang])
        for j, seg in enumerate(("Femur", "Tibia")):
            h, f3 = frs[j]
            M = Q @ _mat4(h, f3)
            B[f"TailLeg{sfx}_{seg}"] = (M.translation.copy(), M.to_3x3().normalized(), TAIL_LEG[j],
                                        "Tail" if j == 0 else f"TailLeg{sfx}_Femur", True)
    p, fr = els[0]
    Q = q_matrix(p, fr)
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        a0 = Q @ Vector((side * 0.075, -0.115, 0.03))
        a1 = Q @ Vector((side * 0.20, -0.38, 0.10))
        a2 = Q @ Vector((side * 0.34, -0.64, 0.14))
        B[f"Antenna{sfx}_1"] = (*_frame(a0, a1 - a0, (0, 0, 1)), ANTENNA[0], "Head", True)
        B[f"Antenna{sfx}_2"] = (*_frame(a1, a2 - a1, (0, 0, 1)), ANTENNA[1], f"Antenna{sfx}_1", True)
        f0 = Q @ Vector((side * 0.075, -0.07, -0.035))
        f1 = Q @ Vector((side * 0.015, -0.22, -0.05))
        B[f"Forcipule{sfx}"] = (*_frame(f0, f1 - f0, (0, 0, 1)), FORCIPULE_LEN, "Head", True)
    B["Socket_Mouth"] = (*_frame(Q @ Vector((0, -0.2, -0.04)), (0, -1, 0), (0, 0, 1)), 0.06, "Head", False)
    p, fr = els[4]
    B["Socket_Saddle"] = (*_frame(p + Vector((0, 0, DORSAL)), (0, 0, 1), (0, -1, 0)), 0.06, "Seg04", False)
    p, fr = els[-1]
    B["Socket_Tail"] = (*_frame(p + Vector((0, 0.08, 0)), (0, 1, 0), (0, 0, 1)), 0.06, "Tail", False)
    return B


# ----------------------------------------------------------------------------------------- mesh
def _element_rows(k):
    """Loft rows (element space: +Y forward, +Z up) for chain element k: flat plates, the front tucked under the
    element before."""
    L, w = LENGTHS[k], WIDTH[k]
    if k == 0:                                               # head: rounded front, flat
        return [(0, 0.55 * L, -0.005, w * 0.55, DORSAL * 0.6, VENTRAL * 0.6), (0, 0.35 * L, 0, w * 0.92, DORSAL * 0.9, VENTRAL * 0.9),
                (0, 0.0, 0, w, DORSAL, VENTRAL), (0, -0.4 * L, 0, w * 0.95, DORSAL * 0.9, VENTRAL * 0.95),
                (0, -0.6 * L, -0.003, w * 0.7, DORSAL * 0.7, VENTRAL * 0.7)]
    if k == len(LENGTHS) - 1:                                # tail: tapers to a blunt end
        return [(0, 0.6 * L, -0.004, w * 0.95, DORSAL * 0.85, VENTRAL * 0.85), (0, 0.2 * L, 0, w, DORSAL * 0.9, VENTRAL * 0.9),
                (0, -0.3 * L, 0, w * 0.8, DORSAL * 0.75, VENTRAL * 0.8), (0, -0.55 * L, 0, w * 0.45, DORSAL * 0.45, VENTRAL * 0.5)]
    return [(0, 0.62 * L, -0.006, w * 0.9, DORSAL * 0.8, VENTRAL * 0.85), (0, 0.45 * L, 0, w * 0.98, DORSAL * 0.95, VENTRAL),
            (0, -0.2 * L, 0, w, DORSAL, VENTRAL), (0, -0.5 * L, 0.002, w * 0.97, DORSAL * 1.02, VENTRAL * 0.9)]


def build_body():
    B = rest_bones()
    bm = bmesh.new()
    P = _Parts(bm)
    els = rest_elements()
    for k, (name, (p, fr)) in enumerate(zip(ELEMENTS, els)):
        M = _mat4(p, fr)
        last = k == len(ELEMENTS) - 1
        vs = loft(bm, _element_rows(k), up=(0, 0, 1), seg=10 if k == 0 else 8, per_seg=1, cap0=(0.6 if last else 0.35),
                  cap1=(0.7 if k == 0 else 0.3), capk=2, shape=0.72, split=True, xform=M)
        pid = PART['head'] if k == 0 else PART['tail'] if last else PART['seg'] + k
        P.tag(vs, name, pid, p, fr, LENGTHS[k])
        for v in vs:                                         # t: 0 at the back edge, 1 at the front edge
            loc = fr.transposed() @ (v.co - p)
            v[P.t] = max(0.0, min(1.0, loc.y / LENGTHS[k] + 0.5))
    # head: eye clusters (four ocelli a side) on the front corners
    p, fr = els[0]
    Q = q_matrix(p, fr)
    for side in (1, -1):
        for dx, dy, r in ((0.085, -0.075, 0.016), (0.100, -0.058, 0.013), (0.075, -0.052, 0.012), (0.093, -0.040, 0.011)):
            c = Q @ Vector((side * dx, dy, DORSAL * 0.72))
            n = (Q.to_3x3() @ Vector((side * 0.35, -0.3, 0.9))).normalized()
            vs = dome(bm, c, n, r, r * 0.6, seg=6, rings=1)
            P.tag(vs, "Head", PART['eye'], p, fr, LENGTHS[0])
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        for k2, (L, r0, r1) in enumerate(((ANTENNA[0], 0.016, 0.012), (ANTENNA[1], 0.012, 0.006))):
            n = f"Antenna{sfx}_{k2 + 1}"
            h, fr2, _, _, _ = B[n]
            rows = [(0, L * i / 7, 0, r0 + (r1 - r0) * i / 7, r0 + (r1 - r0) * i / 7, r0 + (r1 - r0) * i / 7) for i in range(8)]
            rows = [(x, y, z, a * (1.0 if i % 2 else 0.8), b * (1.0 if i % 2 else 0.8), c * (1.0 if i % 2 else 0.8))
                    for i, (x, y, z, a, b, c) in enumerate(rows)]    # beaded
            vs = loft(bm, rows, up=(0, 0, 1), seg=4, per_seg=1, cap0=0.5, cap1=0.8, capk=2, xform=_mat4(h, fr2),
                      seam=-0.75 * math.pi)
            P.tag(vs, n, PART['antenna'], h, fr2, L)
        n = f"Forcipule{sfx}"
        h, fr2, L, _, _ = B[n]                               # venom claws: thick base, curving to a point
        rows = [(0, -0.02, 0, 0.034, 0.030, 0.030), (0, 0.35 * L, 0, 0.032, 0.028, 0.028), (0, 0.7 * L, 0, 0.022, 0.02, 0.02)]
        vs = loft(bm, rows, up=(0, 0, 1), seg=6, per_seg=1, cap0=0.6, cap1=0.0, capk=2, xform=_mat4(h, fr2))
        P.tag(vs, n, PART['forcipule'], h, fr2, L)
        vs = cone(bm, (0, 0.68 * L, 0), (-side * 0.03 * 0, L * 1.05, 0), 0.02, seg=5, xform=_mat4(h, fr2),
                  bend=(side * -0.035, 0, 0))
        P.tag(vs, n, PART['forcipule'], h, fr2, L)
    # legs
    def leg(n, L, r0, r1, pid, claw=False):
        h, fr2, _, _, _ = B[n]
        rows = [(0, -0.06 * L, 0, r0 * 0.85, r0 * 0.85, r0 * 0.85), (0, 0.12 * L, 0, r0, r0 * 1.05, r0),
                (0, L, 0, r1, r1, r1)]
        vs = loft(bm, rows, up=(0, 0, 1), seg=4, per_seg=1, cap0=0.6, cap1=(0.0 if claw else 0.5), capk=2,
                  xform=_mat4(h, fr2), seam=-0.75 * math.pi)
        P.tag(vs, n, pid, h, fr2, L)
        if claw:
            vs = cone(bm, (0, L * 0.98, 0), (0, L * 1.18, -0.01), r1 * 1.05, seg=4, xform=_mat4(h, fr2))
            P.tag(vs, n, PART['claw'], h, fr2, L)
    for i in range(1, N_SEG + 1):
        L1, L2, _ = leg_dims(i)
        for side in (1, -1):
            leg(leg_name(i, side, "Femur"), L1, 0.024, 0.019, PART['femur'])
            leg(leg_name(i, side, "Tibia"), L2, 0.018, 0.010, PART['tibia'], claw=True)
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        leg(f"TailLeg{sfx}_Femur", TAIL_LEG[0], 0.030, 0.026, PART['tail_femur'])
        leg(f"TailLeg{sfx}_Tibia", TAIL_LEG[1], 0.024, 0.012, PART['tail_tibia'], claw=True)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    names = list(P.names)
    bone = [v[P.bone] for v in bm.verts]
    info = [(v[P.part], v[P.t], v[P.u]) for v in bm.verts]
    coll = get_coll("CEN_Body")
    remove_obj("CentipedeBody")
    ob = mesh_obj("CentipedeBody", bm, coll, recalc=False)
    for p in ob.data.polygons:
        p.use_smooth = True
    groups = {n: ob.vertex_groups.new(name=n) for n in names}
    for vi, bi in enumerate(bone):
        groups[names[bi]].add([vi], 1.0, 'REPLACE')
    att = ob.data.color_attributes.new("info", 'FLOAT_COLOR', 'POINT')
    att.data.foreach_set('color', np.array([(p / 255.0, t, u, 1.0) for p, t, u in info], dtype=np.float32).ravel())
    return ob


def tri_report(ob):
    me = ob.data
    att = me.color_attributes["info"]
    part = np.array([round(att.data[i].color[0] * 255) for i in range(len(me.vertices))])
    out = {}
    for p in me.polygons:
        pid = int(part[p.vertices[0]])
        key = ("segments" if 10 <= pid < 29 else next((k for k, v in PART.items() if v == pid), str(pid)))
        out[key] = out.get(key, 0) + len(p.vertices) - 2
    out["total"] = sum(out.values())
    return out
