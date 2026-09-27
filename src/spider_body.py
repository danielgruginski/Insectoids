"""Giant hunting spider: anatomy, leg IK and the game mesh, all built in the bind (standing) pose.

The spider faces -Y, left side +X, metres. Horse-sized: body ~1.65 m from fangs to spinnerets, back ~0.95 m high
(abdomen top), ~3.2 m leg span. It is an exoskeleton, so every part is a rigid shell on one bone: legs are five
lofted segments (coxa, femur, patella+tibia, metatarsus, tarsus) whose rounded proximal ends sit inside the
flared end of the segment before, like real joints. Only the pedicel (waist) blends between two bones.

Bone frames (armature space, rest):
  Body      head at the cephalothorax centre, +Y forward (world -Y), +Z up.
  Abdomen   head at the pedicel, +Y backward (world +Y), +Z up.
  legs      +Y along the segment, +X the hinge (same for the whole leg: e_r x up), +Z dorsal.
            A positive rotation about +X raises a segment on either side.
"""
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from bug_common import loft, dome, cone, mesh_obj, get_coll, remove_obj, smoothstep

# ----------------------------------------------------------------------------------------- spec
SEG_NAMES = ("Coxa", "Femur", "Tibia", "Metatarsus", "Tarsus")
SEG_RATIO = np.array([0.115, 0.29, 0.30, 0.19, 0.105])
COXA_PITCH = math.radians(-18)

# per leg (left side): coxa base on the body, total length, neutral foot (yaw from +X toward the front, distance
# from the coxa base), radius factor
LEGS = [
    dict(C=(0.165, -0.545, 0.545), L=1.64, yaw=57, dist=1.00, k=0.97, femur=52),
    dict(C=(0.228, -0.425, 0.530), L=1.47, yaw=22, dist=0.93, k=0.93, femur=48),
    dict(C=(0.242, -0.290, 0.530), L=1.39, yaw=-24, dist=0.90, k=0.92, femur=48),
    dict(C=(0.205, -0.150, 0.540), L=1.75, yaw=-58, dist=1.08, k=1.00, femur=52),
]
LIFT = -0.08                          # the whole body sits this much lower than the rows below say
TARSUS_PLANT = math.radians(-36)      # tarsus angle when the foot stands on the ground
META_REST = math.radians(-72)         # preferred metatarsus angle
FEMUR_REST = math.radians(50)         # preferred femur rise: knees up at the carapace, like a hunting spider

# leg segment profiles in bone space: (t along the segment, radius) for a leg of radius factor 1
PROFILE = {
    "Coxa": [(-0.30, 0.060), (0.35, 0.080), (1.0, 0.070)],
    "Femur": [(-0.07, 0.050), (0.10, 0.061), (0.45, 0.062), (0.85, 0.056), (1.0, 0.059)],
    "Tibia": [(-0.06, 0.045), (0.06, 0.057), (0.20, 0.058), (0.34, 0.048), (0.72, 0.045), (1.0, 0.046)],
    "Metatarsus": [(-0.07, 0.035), (0.08, 0.039), (0.60, 0.034), (1.0, 0.035)],
    "Tarsus": [(-0.08, 0.028), (0.08, 0.032), (0.62, 0.029), (1.0, 0.021)],
}
SIDES_SEG = {"Coxa": 7, "Femur": 7, "Tibia": 7, "Metatarsus": 6, "Tarsus": 6}
LEG_THICK = 1.25                      # stout hunting-spider legs
FLAT = {"Coxa": 0.92, "Femur": 0.84, "Tibia": 0.90, "Metatarsus": 0.95, "Tarsus": 1.0}   # side/dorsal radius

BODY_C = Vector((0, -0.33, 0.62))       # cephalothorax centre (Body bone head)
PEDICEL = Vector((0, -0.03, 0.618))     # waist (Abdomen bone head)

CEPH_ROWS = [   # x, y, z, half-width, top, bottom
    (0, -0.712, 0.636, 0.070, 0.055, 0.055),
    (0, -0.690, 0.645, 0.150, 0.135, 0.100),
    (0, -0.630, 0.648, 0.212, 0.178, 0.122),
    (0, -0.540, 0.642, 0.252, 0.180, 0.132),
    (0, -0.420, 0.626, 0.280, 0.150, 0.136),
    (0, -0.290, 0.616, 0.286, 0.134, 0.130),
    (0, -0.170, 0.611, 0.256, 0.110, 0.114),
    (0, -0.080, 0.613, 0.190, 0.080, 0.085),
    (0, -0.030, 0.616, 0.110, 0.058, 0.060),
]
ABD_ROWS = [
    (0, 0.030, 0.630, 0.070, 0.060, 0.060),
    (0, 0.080, 0.645, 0.190, 0.170, 0.150),
    (0, 0.180, 0.665, 0.280, 0.250, 0.230),
    (0, 0.320, 0.675, 0.325, 0.285, 0.262),
    (0, 0.480, 0.672, 0.335, 0.290, 0.266),
    (0, 0.640, 0.655, 0.300, 0.265, 0.240),
    (0, 0.780, 0.628, 0.225, 0.200, 0.180),
    (0, 0.880, 0.600, 0.130, 0.120, 0.110),
    (0, 0.925, 0.585, 0.060, 0.060, 0.050),
]
# eyes: ray direction from the head centre, base radius, height; left side (mirrored)
EYE_ORIGIN = Vector((0, -0.50, 0.64))
EYES = [
    ("PME", (0.24, -0.93, 0.30), 0.052, 0.032),    # the big pair, facing forward
    ("PLE", (0.50, -0.45, 0.74), 0.040, 0.024),    # on the top edge, looking out and back
    ("AME", (0.09, -0.99, 0.02), 0.022, 0.013),    # front row
    ("ALE", (0.27, -0.96, -0.01), 0.020, 0.012),
]
PALP = dict(C=(0.112, -0.650, 0.530), L=(0.19, 0.16, 0.13), yaw=72, angles=(38, -28, -70), r=(0.030, 0.027, 0.025))
CHEL = dict(base=(0.066, -0.668, 0.628), tip=(0.070, -0.748, 0.452), r=0.064)
FANG = dict(tip=(0.030, -0.772, 0.382), r=0.020)

# part ids for painting (vertex attribute "info".r * 255)
PART = dict(carapace=0, abdomen=1, pedicel=2, eye_big=3, eye_small=4, chelicera=5, fang=6, palp=7, spinneret=8,
            spine=9, leg=10)          # leg segments: 10 + 5 * leg + segment

LM = {}          # landmarks filled by the build (sockets, eyes, joints)


# ----------------------------------------------------------------------------------------- leg IK
def seg_lengths(L):
    return SEG_RATIO * L


def _plane(ψ):
    """Outward horizontal unit vector for yaw ψ (from +X toward -Y for a left leg; mirrored for the right)."""
    return Vector((math.cos(ψ), -math.sin(ψ), 0.0))


def solve_leg(C, lengths, target, tarsus=TARSUS_PLANT, meta_pref=META_REST, femur_pref=FEMUR_REST, side=1):
    """Planar leg IK in the body frame. C = coxa base, target = where the tarsus tip goes (both body-local).
    Returns (e_r, angles) with angles = [coxa, femur, tibia, metatarsus, tarsus] from the horizontal (radians).
    The leg has one spare degree of freedom; the metatarsus angle is chosen so the femur rises near `femur_pref`
    (knee up) without straightening the leg, with a weak pull toward `meta_pref`."""
    Lc, Lf, Lt, Lm, Ls = lengths
    d = Vector(target) - Vector(C)
    dh = Vector((d.x, d.y, 0.0))
    if dh.length < 1e-4:
        dh = Vector((side, 0, 0))
    e_r = dh.normalized()
    Hr, Hz = Lc * math.cos(COXA_PITCH), Lc * math.sin(COXA_PITCH)
    Tr, Tz = dh.length, d.z
    ar = Tr - Ls * math.cos(tarsus) - Hr
    az = Tz - Ls * math.sin(tarsus) - Hz
    full = Lf + Lt
    lo = abs(Lf - Lt) / full + 0.05

    def chain(am):
        Ar, Az = ar - Lm * math.cos(am), az - Lm * math.sin(am)
        D = math.hypot(Ar, Az)
        Dc = min(max(D, abs(Lf - Lt) + 1e-4), full * 0.9995)
        beta = math.atan2(Az, Ar)
        gamma = math.acos(max(-1.0, min(1.0, (Lf * Lf + Dc * Dc - Lt * Lt) / (2 * Lf * Dc))))
        return Ar, Az, D / full, beta + gamma

    def cost(am):
        _, _, D, af = chain(am)
        pen = 0.0 if lo < D < 0.96 else 40.0 * (max(0.0, D - 0.96) + max(0.0, lo - D)) ** 2 + 0.5
        return (af - femur_pref) ** 2 + 0.08 * (am - meta_pref) ** 2 + pen

    grid = np.radians(np.arange(-160.0, 40.1, 2.0))
    cs = np.array([cost(a) for a in grid])
    i = int(cs.argmin())
    lo_a, hi_a = grid[max(i - 1, 0)], grid[min(i + 1, len(grid) - 1)]
    for _ in range(30):                                  # golden section around the grid minimum
        m1 = hi_a - (hi_a - lo_a) * 0.618
        m2 = lo_a + (hi_a - lo_a) * 0.618
        if cost(m1) < cost(m2):
            hi_a = m2
        else:
            lo_a = m1
    am = 0.5 * (lo_a + hi_a)
    Ar, Az, _, af = chain(am)
    Kr, Kz = Lf * math.cos(af), Lf * math.sin(af)
    at = math.atan2(Az - Kz, Ar - Kr)
    return e_r, [COXA_PITCH, af, at, am, tarsus]


def leg_frames(C, lengths, e_r, angles):
    """Armature-space (or body-local) frames of the five segments: list of (head, Matrix3 [X hinge, Y along, Z dorsal])."""
    up = Vector((0, 0, 1))
    X = e_r.cross(up).normalized()
    p = Vector(C)
    out = []
    for L, a in zip(lengths, angles):
        Y = (e_r * math.cos(a) + up * math.sin(a)).normalized()
        Z = X.cross(Y)
        out.append((p.copy(), Matrix((X, Y, Z)).transposed()))
        p = p + Y * L
    out.append((p.copy(), None))                        # tarsus tip
    return out


def leg_spec(i, side):
    """Rest data of leg i (0..3) on side +1 (left) / -1 (right)."""
    s = LEGS[i]
    C = Vector((side * s['C'][0], s['C'][1], s['C'][2] + LIFT))
    yaw = math.radians(s['yaw'])
    foot = C + Vector((side * math.cos(yaw), -math.sin(yaw), 0.0)) * s['dist']
    foot.z = 0.0
    return C, seg_lengths(s['L']), foot, s['k'], math.radians(s['femur'])


def leg_name(i, side, seg):
    return f"Leg{'L' if side > 0 else 'R'}{i + 1}_{seg}"


# ----------------------------------------------------------------------------------------- bone table
def _frame(head, Y, Zhint):
    Y = Vector(Y).normalized()
    X = Y.cross(Vector(Zhint)).normalized()
    Z = X.cross(Y)
    return (Vector(head), Matrix((X, Y, Z)).transposed())


def rest_bones():
    """name -> (head, Matrix3 frame, length, parent, deform). Everything in the bind pose."""
    B = {}
    # Root points up with +Z toward the spider's front (world -Y), so it lands in Unity with identity orientation
    # (up = +Y, forward = +Z). Unity measures root motion in this bone's frame: pointing down (+Z backward), it made
    # the walk come out backwards. (Matrix(rows).transposed(): each row is a column = the bone's X, Y, Z.)
    B["Root"] = (Vector((0, 0, 0)), Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0))).transposed(), 0.25, None, False)
    # Motion carries the root motion (Unity's motion node). It is a sibling of Root, not its parent: Unity leaves the
    # motion node's own travel in the pose, so anything hanging from it would move twice and snap back every loop.
    # Exported clips keep the skeleton in place and move only Motion. Deform so the FBX export keeps it (no weights).
    B["Motion"] = (Vector((0, 0, 0)), Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0))).transposed(), 0.2, None, True)
    lz = Vector((0, 0, LIFT))
    B["Body"] = (*_frame(BODY_C + lz, (0, -1, 0), (0, 0, 1)), 0.30, "Root", True)
    B["Abdomen"] = (*_frame(PEDICEL + lz, (0, 1, 0.02), (0, 0, 1)), 0.45, "Body", True)
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        mx = Vector((side, 1, 1))
        b = Vector(CHEL['base']) * mx + lz
        t = Vector(CHEL['tip']) * mx + lz
        B[f"Chelicera{sfx}"] = (*_frame(b, t - b, (0, -1, 0)), (t - b).length, "Body", True)
        ft = Vector(FANG['tip']) * mx + lz
        B[f"Fang{sfx}"] = (*_frame(t, ft - t, (0, 0, -1)), (ft - t).length, f"Chelicera{sfx}", True)
        # palp: three segments in a plane, FK angles
        C = Vector(PALP['C']) * mx + lz
        yaw = math.radians(PALP['yaw'])
        e_r = Vector((side * math.cos(yaw), -math.sin(yaw), 0))
        fr = leg_frames(C, PALP['L'], e_r, [math.radians(a) for a in PALP['angles']])
        par = "Body"
        for k, nm in enumerate(("Femur", "Tibia", "Tarsus")):
            n = f"Palp{sfx}_{nm}"
            B[n] = (fr[k][0], fr[k][1], PALP['L'][k], par, True)
            par = n
        for i in range(4):
            C, Ls, foot, k, fp = leg_spec(i, side)
            e_r, ang = solve_leg(C, Ls, foot, femur_pref=fp, side=side)
            fr = leg_frames(C, Ls, e_r, ang)
            par = "Body"
            for j, seg in enumerate(SEG_NAMES):
                n = leg_name(i, side, seg)
                B[n] = (fr[j][0], fr[j][1], Ls[j], par, True)
                par = n
            LM[f"foot_{sfx}{i + 1}"] = fr[5][0]
    # sockets: head = attach point
    B["Socket_Saddle"] = (*_frame(Vector((0, -0.24, 0.790)) + lz, (0, 0, 1), (0, -1, 0)), 0.08, "Body", False)
    B["Socket_Mouth"] = (*_frame(Vector((0, -0.775, 0.470)) + lz, (0, -1, 0), (0, 0, 1)), 0.08, "Body", False)
    B["Socket_Abdomen"] = (*_frame(Vector((0, 0.40, 0.955)) + lz, (0, 0, 1), (0, -1, 0)), 0.08, "Abdomen", False)
    B["Socket_Spinneret"] = (*_frame(Vector((0, 0.965, 0.548)) + lz, (0, 1, -0.35), (0, 0, 1)), 0.08, "Abdomen", False)
    return B


# ----------------------------------------------------------------------------------------- mesh
class _Parts:
    """Collects verts per bone and paint info while the parts are built into one bmesh."""

    def __init__(self, bm):
        self.bm = bm
        self.bone = bm.verts.layers.int.new("bone")
        self.part = bm.verts.layers.int.new("part")
        self.t = bm.verts.layers.float.new("t")
        self.u = bm.verts.layers.float.new("u")
        self.names = []

    def idx(self, name):
        if name not in self.names:
            self.names.append(name)
        return self.names.index(name)

    def tag(self, verts, bone, part, head=None, frame=None, length=None, t_axis=None):
        bi = self.idx(bone)
        for v in verts:
            v[self.bone] = bi
            v[self.part] = part
            if frame is not None:
                loc = frame.transposed() @ (v.co - head)
                v[self.t] = max(0.0, min(1.0, loc.y / length))
                r = math.hypot(loc.x, loc.z)
                v[self.u] = 0.5 + 0.5 * (loc.z / r if r > 1e-6 else 0.0)
            elif t_axis is not None:
                a, b = t_axis
                v[self.t] = max(0.0, min(1.0, (v.co.y - a) / (b - a)))
                v[self.u] = 0.5 + 0.5 * max(-1.0, min(1.0, v.normal.z if v.normal.length > 0 else 0.0))


def _mat4(head, frame):
    return Matrix.Translation(head) @ frame.to_4x4()


def _segment_rows(seg, L, k):
    prof = PROFILE[seg]
    f = FLAT[seg]
    k = k * LEG_THICK
    return [(0, t * L, 0, r * k * f, r * k, r * k) for t, r in prof]


def build_body():
    """The game mesh (one object, rigid vertex groups by bone) and the landmarks. Returns the object."""
    B = rest_bones()
    bm = bmesh.new()
    P = _Parts(bm)

    absolute = []                      # parts built from the absolute rows; lifted by LIFT afterwards
    # cephalothorax, pedicel, abdomen (lofted along Y, seam down the belly midline)
    vs = loft(bm, CEPH_ROWS, up=(0, 0, 1), seg=16, per_seg=1, cap0=0.55, cap1=0.35, capk=2, split=True)
    P.tag(vs, "Body", PART['carapace'], t_axis=(-0.73, -0.02))
    absolute += vs
    vs = loft(bm, [(0, -0.075, 0.615, 0.052, 0.046, 0.046), (0, -0.005, 0.620, 0.046, 0.040, 0.040),
                   (0, 0.065, 0.628, 0.054, 0.048, 0.048)], up=(0, 0, 1), seg=8, per_seg=1, cap0=0, cap1=0)
    P.tag(vs, "Body", PART['pedicel'], t_axis=(-0.075, 0.065))
    absolute += vs
    vs = loft(bm, ABD_ROWS, up=(0, 0, 1), seg=20, per_seg=1, cap0=0.5, cap1=0.6, capk=2, split=True)
    P.tag(vs, "Abdomen", PART['abdomen'], t_axis=(0.0, 0.97))
    absolute += vs

    # eyes: domes where rays from the head centre meet the carapace
    tmp = bmesh.new()
    loft(tmp, CEPH_ROWS, up=(0, 0, 1), seg=16, per_seg=1, cap0=0.55, cap1=0.35, capk=2)
    bvh = BVHTree.FromBMesh(tmp)
    tmp.free()
    for name, d, r, h in EYES:
        for side in (1, -1):
            dv = Vector((side * d[0], d[1], d[2])).normalized()
            hit, nrm, _, _ = bvh.ray_cast(EYE_ORIGIN, dv, 2.0)
            if hit is None:
                continue
            n = (nrm.normalized() + dv).normalized()
            vs = dome(bm, hit - n * h * 0.35, n, r, h * 1.35, seg=10 if r > 0.03 else 7, rings=2 if r > 0.03 else 1)
            P.tag(vs, "Body", PART['eye_big'] if r > 0.03 else PART['eye_small'], t_axis=(-0.75, -0.4))
            absolute += vs
            LM[f"eye_{name}_{'L' if side > 0 else 'R'}"] = (hit + Vector((0, 0, LIFT)), n)

    # spinnerets: two pairs of short cones under the tip of the abdomen, pointing back and down
    for side in (1, -1):
        for dx, dy, dz, ln, r in ((0.030, 0.905, 0.555, 0.070, 0.021), (0.018, 0.895, 0.530, 0.050, 0.016)):
            b = Vector((side * dx, dy, dz))
            tip = b + Vector((side * 0.010, 0.85, -0.52)).normalized() * ln
            vs = cone(bm, b, tip, r, seg=5)
            P.tag(vs, "Abdomen", PART['spinneret'], t_axis=(0.88, 0.97))
            absolute += vs
    for v in absolute:
        v.co.z += LIFT

    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        # chelicerae: bulging forward, and the fangs folded in under them
        h, fr, L, _, _ = B[f"Chelicera{sfx}"]
        rows = [(0, -0.02, 0, 0.050, 0.050, 0.046), (0, 0.05, 0, 0.066, 0.074, 0.056), (0, 0.10, 0, 0.066, 0.076, 0.054),
                (0, 0.15, 0, 0.056, 0.062, 0.046), (0, L, 0, 0.036, 0.040, 0.034)]
        vs = loft(bm, rows, up=(0, 0, 1), seg=10, per_seg=1, cap0=0.5, cap1=0.8, capk=2, xform=_mat4(h, fr))
        P.tag(vs, f"Chelicera{sfx}", PART['chelicera'], h, fr, L)
        h, fr, L, _, _ = B[f"Fang{sfx}"]
        M = _mat4(h, fr)
        vs = cone(bm, (0, -0.01, 0), (0, L * 0.9, 0), FANG['r'], seg=5, xform=M, bend=(0.0, 0, -0.03))
        P.tag(vs, f"Fang{sfx}", PART['fang'], h, fr, L)
        # palps
        for k, nm in enumerate(("Femur", "Tibia", "Tarsus")):
            n = f"Palp{sfx}_{nm}"
            h, fr, L, _, _ = B[n]
            r0 = PALP['r'][k]
            rows = [(0, -0.05 * L, 0, r0 * 0.8, r0 * 0.8, r0 * 0.8), (0, 0.1 * L, 0, r0, r0, r0), (0, L, 0, r0 * 0.9, r0 * 0.95, r0 * 0.9)]
            if nm == "Tarsus":
                rows = [(0, -0.05 * L, 0, r0 * 0.8, r0 * 0.8, r0 * 0.8), (0, 0.3 * L, 0, r0 * 1.15, r0 * 1.2, r0 * 1.2),
                        (0, L, 0, r0 * 0.7, r0 * 0.7, r0 * 0.7)]
            vs = loft(bm, rows, up=(0, 0, 1), seg=6, per_seg=1, cap0=0.6, cap1=(0.9 if nm == "Tarsus" else 0.0), capk=2,
                      xform=_mat4(h, fr))
            P.tag(vs, n, PART['palp'], h, fr, L)
        # legs
        for i in range(4):
            k = LEGS[i]['k']
            for j, seg in enumerate(SEG_NAMES):
                n = leg_name(i, side, seg)
                h, fr, L, _, _ = B[n]
                M = _mat4(h, fr)
                tip = seg == "Tarsus"
                vs = loft(bm, _segment_rows(seg, L, k), up=(0, 0, 1), seg=SIDES_SEG[seg], per_seg=1,
                          cap0=0.7, cap1=(1.1 if tip else 0.0), capk=2, xform=M)
                P.tag(vs, n, PART['leg'] + 5 * i + j, h, fr, L)
                # spines (macrosetae): ventral-lateral rows on tibia and metatarsus, a pair on top of the femur
                spines = []
                if seg == "Tibia":
                    spines = [(t, a) for t in (0.42, 0.62, 0.82) for a in (-125, -55)]
                elif seg == "Metatarsus":
                    spines = [(t, a) for t in (0.35, 0.72) for a in (-125, -55)]
                elif seg == "Femur":
                    spines = [(0.55, 90), (0.8, 90)]
                prof = PROFILE[seg]
                for t, adeg in spines:
                    r = np.interp(t, [p[0] for p in prof], [p[1] for p in prof]) * k * LEG_THICK
                    a = math.radians(adeg)
                    rad = Vector((math.cos(a) * FLAT[seg], 0, math.sin(a)))
                    base = Vector((0, t * L, 0)) + rad * r * 0.85
                    tipv = base + (rad * 0.55 + Vector((0, 0.84, 0))).normalized() * (0.075 if seg != "Femur" else 0.06) * k
                    vs = cone(bm, base, tipv, 0.0085 * k, seg=3, xform=M)
                    P.tag(vs, n, PART['spine'], h, fr, L)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    names = list(P.names)
    bone = [v[P.bone] for v in bm.verts]
    info = [(v[P.part], v[P.t], v[P.u]) for v in bm.verts]
    co_y = [v.co.y for v in bm.verts]
    part_ped = PART['pedicel']

    coll = get_coll("SPD_Body")
    remove_obj("SpiderBody")
    ob = mesh_obj("SpiderBody", bm, coll, recalc=False)
    me = ob.data
    for p in me.polygons:
        p.use_smooth = True
    groups = {n: ob.vertex_groups.new(name=n) for n in names}
    for vi, bi in enumerate(bone):
        n = names[bi]
        if info[vi][0] == part_ped:                 # waist: blend Body -> Abdomen
            w = float(smoothstep(-0.06, 0.05, co_y[vi]))
            if w < 1:
                groups["Body"].add([vi], 1 - w, 'REPLACE')
            if w > 0:
                groups.setdefault("Abdomen", ob.vertex_groups.get("Abdomen") or ob.vertex_groups.new(name="Abdomen"))
                groups["Abdomen"].add([vi], w, 'REPLACE')
        else:
            groups[n].add([vi], 1.0, 'REPLACE')
    att = me.color_attributes.new("info", 'FLOAT_COLOR', 'POINT')
    rgba = np.array([(p / 255.0, t, u, 1.0) for p, t, u in info], dtype=np.float32).ravel()
    att.data.foreach_set('color', rgba)
    LM['tris'] = sum(len(p.vertices) - 2 for p in me.polygons)
    return ob


def tri_report(ob):
    """Triangles per part group (by paint part id)."""
    me = ob.data
    att = me.color_attributes["info"]
    part = np.array([round(att.data[i].color[0] * 255) for i in range(len(me.vertices))])
    out = {}
    for p in me.polygons:
        pid = int(part[p.vertices[0]])
        key = next((k for k, v in PART.items() if v == pid), None) or ("leg" if pid >= PART['leg'] else str(pid))
        out[key] = out.get(key, 0) + len(p.vertices) - 2
    out["total"] = sum(len(p.vertices) - 2 for p in me.polygons)
    return out
