"""Giant hunting spider and its family: anatomy, leg IK and the game mesh, all built in the bind (standing) pose.

The spider faces -Y, left side +X, metres. Horse-sized: body ~1.65 m from fangs to spinnerets, back ~0.95 m high
(abdomen top), ~3.2 m leg span. It is an exoskeleton, so every part is a rigid shell on one bone: legs are five
lofted segments (coxa, femur, patella+tibia, metatarsus, tarsus) whose rounded proximal ends sit inside the
flared end of the segment before, like real joints. Only the pedicel (waist) blends between two bones.

The family (spiderling, broodmother) is the same anatomy changed by a `Kind` (see the end of the spec): the tables
below are the adult's, in its metres; `use(name)` picks the kind that every function here (and spider_anim,
spider_paint) builds. The adult is the default and builds exactly as before the kinds existed.

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
import spider_eggs

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
            spine=9, leg=10,      # leg segments: 10 + 5 * leg + segment (10..29)
            sac=40, horn=41, egg=42)   # the broodmother's egg sacs, abdomen spines + carapace ridge, the laid egg
LEG_PARTS = (10, 30)

LM = {}          # landmarks filled by the build (sockets, eyes, joints)


# ----------------------------------------------------------------------------------------- the family
class Kind:
    """A member of the spider family, as changes to the adult (the tables above stay the adult's, in its metres).

    Building one: the carapace (with the eyes, mouthparts and the leg sockets) and the abdomen are scaled about the
    pedicel by `ceph` / `abd`, the body sits at `lift`, then everything is scaled by `size` about the ground. Legs get
    `leg_len`, `leg_thick` and `foot` (stance radius); `femur` (degrees) is added to every knee's rise. `spines` scales
    the legs' macrosetae (0 = none). Resolution (`seg`, `sides`, `profile`, the `ceph_rows` / `abd_rows` subsets,
    `abd_per_seg`, `simple_mouth`) sets the triangle budget. `extras(bm, parts, bones, absolute)` adds parts,
    `extra_bones(bones)` bones; `scaled` lists the bones whose scale the clips key. Clip settings (fps, tempo, gaits)
    live in spider_anim, paint settings in spider_paint."""

    def __init__(self, name, **kw):
        self.name = name                     # FBX, scene, texture prefix; actions are <name>_<clip> (the adult's bare)
        self.key = "SPD"                     # collection prefix
        self.cams = ""                       # camera name prefix in its scene
        self.size = 1.0
        self.ceph = (1.0, 1.0, 1.0)
        self.abd = (1.0, 1.0, 1.0)
        self.lift = LIFT
        self.leg_len = 1.0
        self.leg_thick = 1.0
        self.foot = 1.0
        self.femur = 0.0
        self.eye = 1.0
        self.spines = 1.0
        self.foot_z = 0.0                    # planted tarsus tips this high, so the tip's mesh rests on the ground
        self.level_feet = False              # tarsus angle against the world, not the tilted body (clips)
        self.seg = dict(ceph=16, abd=20, ped=8, chel=10, palp=6, eye_big=(10, 2), eye_small=(7, 1), fang=5,
                        spinneret=5)
        self.sides = SIDES_SEG
        self.profile = PROFILE
        self.ceph_rows = None
        self.abd_rows = None
        self.abd_per_seg = 1
        self.simple_mouth = False
        self.extras = None
        self.extra_bones = None
        self.scaled = ()
        self.__dict__.update(kw)

    body = property(lambda s: s.name + "Body")
    rig = property(lambda s: s.name + "Rig")
    action_prefix = property(lambda s: "" if s.name == "Spider" else s.name + "_")


def _same(k):
    return tuple(k) == (1.0, 1.0, 1.0)


def _about(p, k):
    """An adult point (unlifted) with the carapace or abdomen reshaped about the pedicel. Unchanged parts pass through
    as the same object, so the adult's numbers stay bit for bit what they were."""
    if _same(k):
        return p
    c = PEDICEL
    return Vector((c.x + (p[0] - c.x) * k[0], c.y + (p[1] - c.y) * k[1], c.z + (p[2] - c.z) * k[2]))


def _sized(v):
    return v if K.size == 1.0 else v * K.size


def _mean(k):
    return (k[0] + k[1] + k[2]) / 3.0


def _rows(rows, k):
    """Loft rows (x, y, z, half-width, top, bottom) reshaped about the pedicel (adult unlifted space)."""
    if _same(k):
        return rows
    out = []
    for x, y, z, a, b, c in rows:
        q = _about((x, y, z), k)
        out.append((q.x, q.y, q.z, a * k[0], b * k[2], c * k[2]))
    return out


def _subset(rows, idx):
    return rows if idx is None else [rows[i] for i in idx]


def _ty(ab, k):
    """A y range (adult) reshaped about the pedicel, for the paint's t axis."""
    if _same(k):
        return ab
    return tuple(PEDICEL.y + (y - PEDICEL.y) * k[1] for y in ab)


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
    """Rest data of leg i (0..3) on side +1 (left) / -1 (right), for the active kind."""
    s = LEGS[i]
    if _same(K.ceph):
        C = Vector((side * s['C'][0], s['C'][1], s['C'][2] + K.lift))
    else:
        C = _about(Vector((side * s['C'][0], s['C'][1], s['C'][2])), K.ceph) + Vector((0, 0, K.lift))
    C = _sized(C)
    yaw = math.radians(s['yaw'])
    foot = C + Vector((side * math.cos(yaw), -math.sin(yaw), 0.0)) * (s['dist'] * (K.foot * K.leg_len * K.size))
    foot.z = K.foot_z
    return C, seg_lengths(s['L'] * (K.leg_len * K.size)), foot, s['k'], math.radians(s['femur'] + K.femur)


def leg_name(i, side, seg):
    return f"Leg{'L' if side > 0 else 'R'}{i + 1}_{seg}"


# ----------------------------------------------------------------------------------------- bone table
def _frame(head, Y, Zhint):
    Y = Vector(Y).normalized()
    X = Y.cross(Vector(Zhint)).normalized()
    Z = X.cross(Y)
    return (Vector(head), Matrix((X, Y, Z)).transposed())


def rest_bones():
    """name -> (head, Matrix3 frame, length, parent, deform). Everything in the bind pose, for the active kind."""
    B = {}
    sz = K.size
    # Root points up with +Z toward the spider's front (world -Y), so it lands in Unity with identity orientation
    # (up = +Y, forward = +Z). Unity measures root motion in this bone's frame: pointing down (+Z backward), it made
    # the walk come out backwards. (Matrix(rows).transposed(): each row is a column = the bone's X, Y, Z.)
    B["Root"] = (Vector((0, 0, 0)), Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0))).transposed(), 0.25 * sz, None, False)
    # Motion carries the root motion (Unity's motion node). It is a sibling of Root, not its parent: Unity leaves the
    # motion node's own travel in the pose, so anything hanging from it would move twice and snap back every loop.
    # Exported clips keep the skeleton in place and move only Motion. Deform so the FBX export keeps it (no weights).
    B["Motion"] = (Vector((0, 0, 0)), Matrix(((1, 0, 0), (0, 0, 1), (0, -1, 0))).transposed(), 0.2 * sz, None, True)
    lz = Vector((0, 0, K.lift))
    hc, ab = K.ceph, K.abd
    B["Body"] = (*_frame(_sized(_about(BODY_C, hc) + lz), (0, -1, 0), (0, 0, 1)), 0.30 * sz, "Root", True)
    B["Abdomen"] = (*_frame(_sized(PEDICEL + lz), (0, 1, 0.02), (0, 0, 1)), 0.45 * sz, "Body", True)
    pl = _mean(hc) * sz                                   # palp lengths follow the carapace
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        mx = Vector((side, 1, 1))
        b = _sized(_about(Vector(CHEL['base']) * mx, hc) + lz)
        t = _sized(_about(Vector(CHEL['tip']) * mx, hc) + lz)
        B[f"Chelicera{sfx}"] = (*_frame(b, t - b, (0, -1, 0)), (t - b).length, "Body", True)
        ft = _sized(_about(Vector(FANG['tip']) * mx, hc) + lz)
        B[f"Fang{sfx}"] = (*_frame(t, ft - t, (0, 0, -1)), (ft - t).length, f"Chelicera{sfx}", True)
        # palp: three segments in a plane, FK angles
        C = _sized(_about(Vector(PALP['C']) * mx, hc) + lz)
        yaw = math.radians(PALP['yaw'])
        e_r = Vector((side * math.cos(yaw), -math.sin(yaw), 0))
        Lp = PALP['L'] if pl == 1.0 else tuple(l * pl for l in PALP['L'])
        fr = leg_frames(C, Lp, e_r, [math.radians(a) for a in PALP['angles']])
        par = "Body"
        for k, nm in enumerate(("Femur", "Tibia", "Tarsus")):
            n = f"Palp{sfx}_{nm}"
            B[n] = (fr[k][0], fr[k][1], Lp[k], par, True)
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
    sk = 0.08 * sz
    B["Socket_Saddle"] = (*_frame(_sized(_about(Vector((0, -0.24, 0.790)), hc) + lz), (0, 0, 1), (0, -1, 0)), sk, "Body", False)
    B["Socket_Mouth"] = (*_frame(_sized(_about(Vector((0, -0.775, 0.470)), hc) + lz), (0, -1, 0), (0, 0, 1)), sk, "Body", False)
    B["Socket_Abdomen"] = (*_frame(_sized(_about(Vector((0, 0.40, 0.955)), ab) + lz), (0, 0, 1), (0, -1, 0)), sk, "Abdomen", False)
    B["Socket_Spinneret"] = (*_frame(_sized(_about(Vector((0, 0.965, 0.548)), ab) + lz), (0, 1, -0.35), (0, 0, 1)), sk, "Abdomen", False)
    if K.extra_bones is not None:
        K.extra_bones(B)
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
    prof = K.profile[seg]
    f = FLAT[seg]
    k = k * LEG_THICK * (K.leg_thick * K.size)
    return [(0, t * L, 0, r * k * f, r * k, r * k) for t, r in prof]


def ceph_rows():
    """The carapace's loft rows for the active kind (adult unlifted space)."""
    return _rows(_subset(CEPH_ROWS, K.ceph_rows), K.ceph)


def abd_rows():
    return _rows(_subset(ABD_ROWS, K.abd_rows), K.abd)


def build_body():
    """The game mesh (one object, rigid vertex groups by bone) and the landmarks, for the active kind. Returns the
    object."""
    B = rest_bones()
    bm = bmesh.new()
    P = _Parts(bm)
    hc, ab = K.ceph, K.abd
    ks = K.seg

    absolute = []                      # parts built from the absolute rows; lifted and sized afterwards
    # cephalothorax, pedicel, abdomen (lofted along Y, seam down the belly midline)
    crows = ceph_rows()
    vs = loft(bm, crows, up=(0, 0, 1), seg=ks['ceph'], per_seg=1, cap0=0.55, cap1=0.35, capk=2, split=True)
    P.tag(vs, "Body", PART['carapace'], t_axis=_ty((-0.73, -0.02), hc))
    absolute += vs
    ped = [(0, -0.075, 0.615, 0.052, 0.046, 0.046), (0, -0.005, 0.620, 0.046, 0.040, 0.040),
           (0, 0.065, 0.628, 0.054, 0.048, 0.048)]
    if not (_same(hc) and _same(ab)):
        ped = [_rows([r], hc if r[1] < PEDICEL.y else ab)[0] for r in ped]
    vs = loft(bm, ped, up=(0, 0, 1), seg=ks['ped'], per_seg=1, cap0=0, cap1=0)
    P.tag(vs, "Body", PART['pedicel'], t_axis=(ped[0][1], ped[-1][1]))
    absolute += vs
    vs = loft(bm, abd_rows(), up=(0, 0, 1), seg=ks['abd'], per_seg=K.abd_per_seg, cap0=0.5, cap1=0.6, capk=2,
              split=True)
    P.tag(vs, "Abdomen", PART['abdomen'], t_axis=_ty((0.0, 0.97), ab))
    absolute += vs

    # eyes: domes where rays from the head centre meet the carapace
    tmp = bmesh.new()
    loft(tmp, crows, up=(0, 0, 1), seg=ks['ceph'], per_seg=1, cap0=0.55, cap1=0.35, capk=2)
    bvh = BVHTree.FromBMesh(tmp)
    tmp.free()
    ek = K.eye * _mean(hc)
    for name, d, r, h in EYES:
        for side in (1, -1):
            dv = Vector((side * d[0], d[1], d[2])).normalized()
            hit, nrm, _, _ = bvh.ray_cast(_about(EYE_ORIGIN, hc), dv, 2.0)
            if hit is None:
                continue
            n = (nrm.normalized() + dv).normalized()
            dseg, drings = ks['eye_big'] if r > 0.03 else ks['eye_small']
            vs = dome(bm, hit - n * (h * ek) * 0.35, n, r * ek, (h * ek) * 1.35, seg=dseg, rings=drings)
            P.tag(vs, "Body", PART['eye_big'] if r > 0.03 else PART['eye_small'], t_axis=_ty((-0.75, -0.4), hc))
            absolute += vs
            LM[f"eye_{name}_{'L' if side > 0 else 'R'}"] = (_sized(hit + Vector((0, 0, K.lift))), n)

    # spinnerets: two pairs of short cones under the tip of the abdomen, pointing back and down
    ka = _mean(ab)
    for side in (1, -1):
        for dx, dy, dz, ln, r in ((0.030, 0.905, 0.555, 0.070, 0.021), (0.018, 0.895, 0.530, 0.050, 0.016)):
            b = _about(Vector((side * dx, dy, dz)), ab)
            tip = b + Vector((side * 0.010, 0.85, -0.52)).normalized() * (ln * ka)
            vs = cone(bm, b, tip, r * ka, seg=ks['spinneret'])
            P.tag(vs, "Abdomen", PART['spinneret'], t_axis=_ty((0.88, 0.97), ab))
            absolute += vs
    if K.extras is not None:
        K.extras(bm, P, B, absolute)
    for v in absolute:
        v.co.z += K.lift
    if K.size != 1.0:
        for v in absolute:
            v.co *= K.size

    m = _mean(hc) * K.size                                # mouthparts follow the carapace
    for side in (1, -1):
        sfx = 'L' if side > 0 else 'R'
        # chelicerae: bulging forward, and the fangs folded in under them
        h, fr, L, _, _ = B[f"Chelicera{sfx}"]
        if K.simple_mouth:
            rows = [(0, -0.02 * m, 0, 0.050 * m, 0.050 * m, 0.046 * m), (0, 0.08 * m, 0, 0.066 * m, 0.075 * m, 0.055 * m),
                    (0, L, 0, 0.036 * m, 0.040 * m, 0.034 * m)]
        else:
            rows = [(0, -0.02 * m, 0, 0.050 * m, 0.050 * m, 0.046 * m), (0, 0.05 * m, 0, 0.066 * m, 0.074 * m, 0.056 * m),
                    (0, 0.10 * m, 0, 0.066 * m, 0.076 * m, 0.054 * m), (0, 0.15 * m, 0, 0.056 * m, 0.062 * m, 0.046 * m),
                    (0, L, 0, 0.036 * m, 0.040 * m, 0.034 * m)]
        vs = loft(bm, rows, up=(0, 0, 1), seg=ks['chel'], per_seg=1, cap0=0.5, cap1=0.8, capk=2, xform=_mat4(h, fr))
        P.tag(vs, f"Chelicera{sfx}", PART['chelicera'], h, fr, L)
        h, fr, L, _, _ = B[f"Fang{sfx}"]
        M = _mat4(h, fr)
        vs = cone(bm, (0, -0.01 * m, 0), (0, L * 0.9, 0), FANG['r'] * m, seg=ks['fang'], xform=M, bend=(0.0, 0, -0.03 * m))
        P.tag(vs, f"Fang{sfx}", PART['fang'], h, fr, L)
        # palps
        for k, nm in enumerate(("Femur", "Tibia", "Tarsus")):
            n = f"Palp{sfx}_{nm}"
            h, fr, L, _, _ = B[n]
            r0 = PALP['r'][k] * m
            rows = [(0, -0.05 * L, 0, r0 * 0.8, r0 * 0.8, r0 * 0.8), (0, 0.1 * L, 0, r0, r0, r0), (0, L, 0, r0 * 0.9, r0 * 0.95, r0 * 0.9)]
            if nm == "Tarsus":
                rows = [(0, -0.05 * L, 0, r0 * 0.8, r0 * 0.8, r0 * 0.8), (0, 0.3 * L, 0, r0 * 1.15, r0 * 1.2, r0 * 1.2),
                        (0, L, 0, r0 * 0.7, r0 * 0.7, r0 * 0.7)]
            c0 = 0.6
            if K.simple_mouth:                        # one tube per segment, the club only on the tarsus
                rows = [rows[0], rows[-1]] if nm != "Tarsus" else rows
                c0 = 0.0
            vs = loft(bm, rows, up=(0, 0, 1), seg=ks['palp'], per_seg=1, cap0=c0, cap1=(0.9 if nm == "Tarsus" else 0.0), capk=2,
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
                vs = loft(bm, _segment_rows(seg, L, k), up=(0, 0, 1), seg=K.sides[seg], per_seg=1,
                          cap0=0.7, cap1=(1.1 if tip else 0.0), capk=2, xform=M)
                P.tag(vs, n, PART['leg'] + 5 * i + j, h, fr, L)
                # spines (macrosetae): ventral-lateral rows on tibia and metatarsus, a pair on top of the femur
                spines = []
                if K.spines <= 0:
                    pass
                elif seg == "Tibia":
                    spines = [(t, a) for t in (0.42, 0.62, 0.82) for a in (-125, -55)]
                elif seg == "Metatarsus":
                    spines = [(t, a) for t in (0.35, 0.72) for a in (-125, -55)]
                elif seg == "Femur":
                    spines = [(0.55, 90), (0.8, 90)]
                prof = K.profile[seg]
                st = K.leg_thick * K.size
                for t, adeg in spines:
                    r = np.interp(t, [p[0] for p in prof], [p[1] for p in prof]) * k * LEG_THICK * st
                    a = math.radians(adeg)
                    rad = Vector((math.cos(a) * FLAT[seg], 0, math.sin(a)))
                    base = Vector((0, t * L, 0)) + rad * r * 0.85
                    tipv = base + (rad * 0.55 + Vector((0, 0.84, 0))).normalized() * (0.075 if seg != "Femur" else 0.06) * k * (K.spines * K.size)
                    vs = cone(bm, base, tipv, 0.0085 * k * st, seg=3, xform=M)
                    P.tag(vs, n, PART['spine'], h, fr, L)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    names = list(P.names)
    bone = [v[P.bone] for v in bm.verts]
    info = [(v[P.part], v[P.t], v[P.u]) for v in bm.verts]
    co_y = [v.co.y for v in bm.verts]
    part_ped = PART['pedicel']
    w0, w1 = -0.06, 0.05                                  # the waist's blend, Body -> Abdomen
    if not (_same(hc) and _same(ab) and K.size == 1.0):
        w0 = (PEDICEL.y + (w0 - PEDICEL.y) * hc[1]) * K.size
        w1 = (PEDICEL.y + (w1 - PEDICEL.y) * ab[1]) * K.size

    coll = get_coll(K.key + "_Body")
    remove_obj(K.body)
    ob = mesh_obj(K.body, bm, coll, recalc=False)
    me = ob.data
    for p in me.polygons:
        p.use_smooth = True
    groups = {n: ob.vertex_groups.new(name=n) for n in names}
    for vi, bi in enumerate(bone):
        n = names[bi]
        if info[vi][0] == part_ped:                 # waist: blend Body -> Abdomen
            w = float(smoothstep(w0, w1, co_y[vi]))
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


# ----------------------------------------------------------------------------------------- the broodmother's extras
# egg sacs: (ray from the abdomen's centre (adult space), radius, turn of the long axis (deg), seed), kept off the
# skull so it still reads from above.
SACS = [
    # a cluster on the rear of the back (behind the skull, clear of the spinnerets)
    ((0.00, 0.78, 0.62), 0.130, 5, 1), ((0.32, 0.70, 0.62), 0.115, -25, 2), ((-0.32, 0.72, 0.60), 0.120, 30, 3),
    ((0.18, 0.92, 0.32), 0.110, 70, 4), ((-0.20, 0.92, 0.30), 0.105, -60, 5), ((0.52, 0.66, 0.40), 0.100, -40, 12),
    ((-0.54, 0.64, 0.38), 0.100, 45, 13),
    # and down both flanks
    ((0.95, 0.28, 0.02), 0.105, 85, 6), ((0.86, 0.50, -0.10), 0.100, 70, 7), ((0.74, 0.12, -0.24), 0.085, 95, 8),
    ((0.80, 0.62, 0.14), 0.090, 60, 14),
    ((-0.95, 0.30, 0.00), 0.100, -80, 9), ((-0.86, 0.52, -0.12), 0.095, -65, 10), ((-0.74, 0.14, -0.22), 0.085, -95, 11),
    ((-0.80, 0.60, 0.16), 0.090, -60, 15),
]
# spines on the abdomen's shoulders, both sides: (y, ray elevation (deg), length, lean back (deg))
HORNS = [(0.16, 52, 0.24, 16), (0.33, 47, 0.19, 24), (0.50, 40, 0.14, 32)]
RIDGE = [(-0.50, 0.085), (-0.43, 0.10), (-0.36, 0.09), (-0.20, 0.07)]       # carapace midline: (y, length)


def _surface(rows, seg, per_seg):
    tmp = bmesh.new()
    loft(tmp, rows, up=(0, 0, 1), seg=seg, per_seg=per_seg, cap0=0.5, cap1=0.6, capk=2)
    tmp.normal_update()                                         # (without it the BVH hits come back with zero normals)
    bvh = BVHTree.FromBMesh(tmp)
    tmp.free()
    return bvh


def _brood_extras(bm, P, B, absolute):
    """Egg sacs on the back and flanks, spines on the abdomen's shoulders and a short ridge on the carapace (adult
    unlifted space: lifted and sized with the body), and the egg the Spawn clip lays (on SpawnEgg, in its bone frame)."""
    ab = K.abd
    bvh = _surface(abd_rows(), K.seg['abd'], K.abd_per_seg)
    centre = _about(Vector((0, 0.45, 0.66)), ab)
    for d, r, turn, seed in SACS:
        dv = Vector(d).normalized()
        hit, nrm, _, _ = bvh.ray_cast(centre, dv, 5.0)
        if hit is None:
            continue
        n = nrm.normalized()
        if n.dot(dv) < 0:                                       # the temporary loft's normals may face in
            n = -n
        along = Vector((0, 1, 0)) - n * n.y                     # the body's length, in the surface
        if along.length < 1e-3:
            along = Vector((1, 0, 0)) - n * n.x
        along.normalize()
        Y = (Matrix.Rotation(math.radians(turn), 3, n) @ along).normalized()
        head, fr = _frame(hit + n * r * 0.42, Y, n)
        L = r * 2.5
        vs = spider_eggs.egg(bm, _mat4(head, fr), L, 2 * r, seg=6, rows=3, seed=seed, flat=0.82, lumps=0.07)
        P.tag(vs, "Abdomen", PART['sac'], head, fr, L)
        absolute += vs
    for y, elev, ln, lean in HORNS:
        for side in (1, -1):
            o = _about(Vector((0, y, 0.64)), ab)
            e = math.radians(elev)
            dv = Vector((side * math.cos(e), 0, math.sin(e)))
            hit, nrm, _, _ = bvh.ray_cast(o, dv, 5.0)
            if hit is None:
                continue
            n = nrm.normalized()
            if n.dot(dv) < 0:
                n = -n
            out = (n + Vector((0, 0, 0.7))).normalized()
            out = (Matrix.Rotation(math.radians(-lean), 3, Vector((side, 0, 0))) @ out).normalized()
            base = hit - n * 0.02
            L = ln * _mean(ab)
            head, fr = _frame(base, out, (0, 1, 0))
            vs = cone(bm, base, base + out * L, L * 0.24, seg=5, bend=Vector((0, L * 0.22, -L * 0.04)))
            P.tag(vs, "Abdomen", PART['horn'], head, fr, L)
            absolute += vs
    cv = _surface(ceph_rows(), K.seg['ceph'], 1)
    for y, ln in RIDGE:
        o = _about(Vector((0, y, 0.55)), K.ceph)
        hit, nrm, _, _ = cv.ray_cast(o, Vector((0, 0, 1)), 2.0)
        if hit is None:
            continue
        out = Vector((0, 0.35, 1)).normalized()
        base = hit - Vector((0, 0, 0.01))
        head, fr = _frame(base, out, (0, 1, 0))
        vs = cone(bm, base, base + out * ln, ln * 0.28, seg=4, bend=Vector((0, ln * 0.25, 0)))
        P.tag(vs, "Body", PART['horn'], head, fr, ln)
        absolute += vs
    h, fr, L, _, _ = B["SpawnEgg"]
    vs = spider_eggs.egg(bm, _mat4(h, fr), spider_eggs.EGG_LEN, spider_eggs.EGG_W, seg=8, rows=5, seed=spider_eggs.EGG_SEED)
    P.tag(vs, "SpawnEgg", PART['egg'], h, fr, L)


def _brood_bones(B):
    """SpawnEgg: the egg the Spawn clip lays, at rest inside the abdomen behind the spinnerets, +Y out of them."""
    h, fr, L, par, d = B["Socket_Spinneret"]
    axis = fr.col[1].normalized()
    head = h - axis * (spider_eggs.EGG_LEN * 0.8)
    B["SpawnEgg"] = (*_frame(head, axis, (0, 0, 1)), spider_eggs.EGG_LEN * 0.5, "Abdomen", True)


JUVENILE_PROFILE = {           # fewer rings and thinner, smoother joints than the adult's
    "Coxa": [(-0.30, 0.060), (1.0, 0.072)],
    "Femur": [(-0.07, 0.052), (0.15, 0.062), (1.0, 0.056)],
    "Tibia": [(-0.06, 0.050), (0.12, 0.058), (1.0, 0.046)],
    "Metatarsus": [(-0.07, 0.038), (1.0, 0.034)],
    "Tarsus": [(-0.08, 0.031), (1.0, 0.022)],
}

SPIDER = Kind("Spider")
SPIDERLING = Kind(
    "Spiderling", key="SPL", cams="SPL_", size=0.36, ceph=(1.12, 1.12, 1.12), abd=(1.28, 1.2, 1.3), lift=-0.13,
    leg_len=0.84, leg_thick=0.72, foot=0.95, femur=4.0, eye=1.25, spines=0.0, foot_z=0.0075, level_feet=True,
    seg=dict(ceph=10, abd=12, ped=4, chel=5, palp=4, eye_big=(8, 1), eye_small=(5, 1), fang=4, spinneret=3),
    sides=dict(Coxa=3, Femur=5, Tibia=5, Metatarsus=4, Tarsus=4), profile=JUVENILE_PROFILE,
    ceph_rows=(0, 1, 2, 3, 5, 8), abd_rows=(0, 1, 2, 3, 4, 5, 6, 8), simple_mouth=True)
BROODMOTHER = Kind(
    "Broodmother", key="BRD", cams="BRD_", size=1.8, abd=(1.5, 1.3, 1.55), lift=-0.11, leg_len=0.96,
    leg_thick=1.3, foot=1.06, femur=-4.0, spines=1.5, level_feet=True, foot_z=0.064,
    seg=dict(ceph=18, abd=24, ped=8, chel=10, palp=6, eye_big=(10, 2), eye_small=(7, 1), fang=5, spinneret=5),
    abd_per_seg=2, extras=_brood_extras, extra_bones=_brood_bones, scaled=("Abdomen", "SpawnEgg"))
KINDS = {k.name: k for k in (SPIDER, SPIDERLING, BROODMOTHER)}
K = SPIDER


def use(name):
    """Make `name` (Spider, Spiderling, Broodmother) the kind that every build function works on."""
    global K
    K = KINDS[name] if isinstance(name, str) else name
    LM.clear()
    return K
