"""Spider clips, keyed straight onto the rig (no constraints to bake).

Every frame is described by a SpiderPose: where the root is, how the body and abdomen sit, what each leg does
(foot target for the IK, or raised/curled FK angles, or a blend), and the mouthparts. `pose_matrices` turns that into
armature-space bone matrices; bug_rig.apply_pose keys them. Clips are sequences of key poses (smooth interpolation)
or, for walk and run, a gait generator (alternating tetrapod: L1 R2 L3 R4 against R1 L2 R3 L4, rear legs leading).

Clips (30 fps, spider faces -Y):
  Idle        3.0 s loop    breathing, palps and fangs twitch, a leg shifts
  Walk        0.8 s loop    root motion (on the Motion bone; the skeleton walks in place), 1.25 m/s
  Run         0.4 s loop    root motion, 3.75 m/s, body low
  Hit         0.5 s
  Death       2.0 s         collapses and rolls onto its back, legs curled
  GetUp       1.33 s        from the Death end pose: rolls back over and stands
  Bite        1.2 s         wind-up, lunge with raised front legs, fangs strike (event 'Bite' at 0.50 s)
  Strike      1.33 s        rears up, front legs slam down (event 'Strike' at 0.73 s)
  WebSpit     1.6 s         abdomen arches up over the back, web glob launched (event 'Spit' at 0.67 s)
  Threat      2.4 s         reared up, front legs spread high, fangs flexing

The family (spider_body.Kind) reuses all of this: offsets in the key-pose tracks and gaits are adult metres, scaled by
the kind's size; FAMILY gives each kind its clips, fps, tempo (duration factor on the adult's clips) and gaits, and
KIND_CLIPS the clips of its own (the kinds' slumped Death and the GetUp from it, the broodmother's Spawn). Actions are <Kind>_<clip> (the adult's bare).
"""
import bpy, math, os
import numpy as np
from mathutils import Vector, Matrix
from bug_common import ROOT
import spider_body as SB
import spider_eggs as SE
import bug_rig

FPS = 30                       # the adult's; a kind's comes from FAMILY (clip_fps())
EXPORT = os.path.join(ROOT, "export")
LEG_KEYS = [(s, i) for s in (1, -1) for i in range(4)]
EVENTS = {"Bite": [("Bite", 0.50)], "Strike": [("Strike", 0.73)], "WebSpit": [("Spit", 0.67)],
          "Death": [("Dead", 1.75)]}


def rad(d):
    return math.radians(d)


# ----------------------------------------------------------------------------------------- pose -> matrices
class Leg:
    """What one leg does. target: root-local foot position for the IK (None = neutral stance foot).
    fk: absolute plane angles in degrees [coxa, femur, tibia, metatarsus, tarsus] and a yaw (degrees from lateral
    toward the front), blended over the IK result by w (0 = IK only)."""

    def __init__(self, target=None, tarsus=None, femur=None, fk=None, fk_yaw=None, w=0.0):
        self.target, self.tarsus, self.femur = target, tarsus, femur
        self.fk, self.fk_yaw, self.w = fk, fk_yaw, w


class SpiderPose:
    def __init__(self):
        self.root = Vector((0, 0, 0))
        self.root_yaw = 0.0
        self.body = Vector((0, 0, 0))          # offset of the cephalothorax centre (root-local)
        self.pitch = self.yaw = self.roll = 0.0   # degrees; pitch > 0 = nose up
        self.abd = [0.0, 0.0, 0.0]             # abdomen pitch (> 0 = rear up), yaw, roll, degrees
        self.legs = {k: Leg() for k in LEG_KEYS}
        self.chel = [0.0, 0.0]                 # chelicerae: forward swing, spread (degrees)
        self.fang = 0.0                        # fangs unfold (degrees)
        self.palp = {1: [0.0, 0.0, 0.0], -1: [0.0, 0.0, 0.0]}   # added to the palp angles
        self.abd_scale = 1.0                   # abdomen swelling (kinds with Abdomen in Kind.scaled)
        self.egg = None                        # the broodmother's laid egg: (out along SpawnEgg +Y in m, drop 0..1,
                                               # scale, ground matrix root-local or None); None = at rest inside


def _euler(pitch, yaw, roll):
    return (Matrix.Rotation(rad(yaw), 4, 'Z') @ Matrix.Rotation(rad(-pitch), 4, 'X') @
            Matrix.Rotation(rad(roll), 4, 'Y'))


def _yaw_of(e_r, side):
    return math.atan2(-e_r.y, side * e_r.x)


def _e_r(psi, side):
    return Vector((side * math.cos(psi), -math.sin(psi), 0.0))


_REST = {}


def rest_data():
    if _REST.get('kind') != SB.K.name:
        _REST.clear()
        _REST['kind'] = SB.K.name
        B = SB.rest_bones()
        _REST['B'] = B
        _REST['pivot'] = B['Body'][0].copy()
        _REST['ped'] = B['Abdomen'][0].copy()
        for s, i in LEG_KEYS:
            C, Ls, foot, k, fp = SB.leg_spec(i, s)
            _REST[(s, i)] = (C, Ls, foot, fp)
    return _REST


def body_transform(p):
    """Root-local transform that carries the rest body to where it is now."""
    D = rest_data()
    pv = D['pivot']
    return Matrix.Translation(pv + p.body) @ _euler(p.pitch, p.yaw, p.roll) @ Matrix.Translation(-pv)


def leg_solution(p, s, i, MB):
    """MB = root @ body transform; foot targets are armature-space (they include the root's travel)."""
    D = rest_data()
    C, Ls, foot, fp = D[(s, i)]
    cmd = p.legs[(s, i)]
    tgt = cmd.target
    if tgt is None:
        M = Matrix.Translation(p.root) @ Matrix.Rotation(rad(p.root_yaw), 4, 'Z')
        tgt = M @ foot
    tl = MB.inverted() @ Vector(tgt)
    tars = rad(cmd.tarsus) if cmd.tarsus is not None else SB.TARSUS_PLANT
    if SB.K.level_feet:                                  # the angle is against the world: undo the body's tilt
        dh = Vector(((tl - C).x, (tl - C).y, 0.0))
        if dh.length > 1e-4:
            tars -= math.asin(max(-1.0, min(1.0, (MB.to_3x3() @ dh.normalized()).z)))
    e_r, ang = SB.solve_leg(C, Ls, tl, tarsus=tars, femur_pref=rad(cmd.femur) if cmd.femur is not None else fp, side=s)
    psi = _yaw_of(e_r, s)
    if cmd.fk is not None and cmd.w > 0:
        w = cmd.w
        psi_fk = rad(cmd.fk_yaw) if cmd.fk_yaw is not None else psi
        psi = psi * (1 - w) + psi_fk * w
        ang = [a * (1 - w) + rad(b) * w for a, b in zip(ang, cmd.fk)]
    return SB.leg_frames(C, Ls, _e_r(psi, s), ang)


def pose_matrices(p):
    D = rest_data()
    B = D['B']
    R = lambda n: bug_rig.frame_matrix(B[n][0], B[n][1])
    M = Matrix.Translation(p.root) @ Matrix.Rotation(rad(p.root_yaw), 4, 'Z')
    BT = body_transform(p)
    MB = M @ BT
    out = {"Root": M @ R("Root"), "Body": MB @ R("Body")}
    ped = D['ped']
    A = MB @ Matrix.Translation(ped) @ _euler(-p.abd[0], p.abd[1], p.abd[2]) @ Matrix.Translation(-ped) @ R("Abdomen")
    out["Abdomen"] = A if p.abd_scale == 1.0 else A @ Matrix.Scale(p.abd_scale, 4)
    for s in (1, -1):
        sfx = 'L' if s > 0 else 'R'
        ch = MB @ R(f"Chelicera{sfx}") @ Matrix.Rotation(rad(-p.chel[0]), 4, 'X') @ Matrix.Rotation(rad(s * p.chel[1]), 4, 'Z')
        out[f"Chelicera{sfx}"] = ch
        rel = R(f"Chelicera{sfx}").inverted() @ R(f"Fang{sfx}")
        out[f"Fang{sfx}"] = ch @ rel @ Matrix.Rotation(rad(s * p.fang), 4, 'Z')
        pc = SB.PALP
        pn = [f"Palp{sfx}_{nm}" for nm in ('Femur', 'Tibia', 'Tarsus')]
        C = B[pn[0]][0]                                    # the kind's palp base and lengths
        e_r = _e_r(rad(pc['yaw']), s)
        ang = [rad(a + d) for a, d in zip(pc['angles'], p.palp[s])]
        for k, (h, fr) in enumerate(SB.leg_frames(C, tuple(B[n][2] for n in pn), e_r, ang)[:3]):
            out[f"Palp{sfx}_{('Femur', 'Tibia', 'Tarsus')[k]}"] = MB @ bug_rig.frame_matrix(h, fr)
    for s, i in LEG_KEYS:
        fr = leg_solution(p, s, i, MB)
        for j, seg in enumerate(SB.SEG_NAMES):
            out[SB.leg_name(i, s, seg)] = MB @ bug_rig.frame_matrix(fr[j][0], fr[j][1])
    if p.egg is not None and "SpawnEgg" in B:
        o, drop, sc, G = p.egg
        E = out["Abdomen"] @ (R("Abdomen").inverted() @ R("SpawnEgg")) @ Matrix.Translation((0, o, 0))
        loc, rot, _ = E.decompose()
        if G is not None and drop > 0:
            gl, gr, _ = (M @ G).decompose()
            loc, rot = loc.lerp(gl, drop), rot.slerp(gr, drop)
        out["SpawnEgg"] = Matrix.Translation(loc) @ rot.to_matrix().to_4x4() @ Matrix.Scale(max(sc, 1e-4), 4)
    # the skeleton plays in place; only the Motion bone travels (Unity turns it into root motion)
    Minv = M.inverted()
    out = {k: Minv @ v for k, v in out.items()}
    out["Motion"] = M @ R("Motion")
    return out


def neutral_foot(s, i):
    return rest_data()[(s, i)][2].copy()


# ----------------------------------------------------------------------------------------- interpolation
def track(keys, f, loop=None):
    """Catmull-Rom through (frame, value) keys; values are floats or sequences. loop = period for cyclic tracks."""
    ks = sorted(keys, key=lambda k: k[0])
    fr = [k[0] for k in ks]
    vals = [np.atleast_1d(np.asarray(k[1], float)) for k in ks]
    if loop:
        f = f % loop
        fr = [fr[-2] - loop] + fr + [fr[1] + loop]
        vals = [vals[-2]] + vals + [vals[1]]
    else:
        if f <= fr[0]:
            return vals[0] if len(vals[0]) > 1 else float(vals[0][0])
        if f >= fr[-1]:
            return vals[-1] if len(vals[-1]) > 1 else float(vals[-1][0])
        fr = [fr[0] - 1] + fr + [fr[-1] + 1]
        vals = [vals[0]] + vals + [vals[-1]]
    for i in range(1, len(fr) - 2):
        if fr[i] <= f <= fr[i + 1]:
            t = (f - fr[i]) / (fr[i + 1] - fr[i])
            p0, p1, p2, p3 = vals[i - 1], vals[i], vals[i + 1], vals[i + 2]
            # tangents scaled for uneven key spacing
            m1 = (p2 - p0) / (fr[i + 1] - fr[i - 1]) * (fr[i + 1] - fr[i])
            m2 = (p3 - p1) / (fr[i + 2] - fr[i]) * (fr[i + 1] - fr[i])
            t2, t3 = t * t, t * t * t
            v = (2 * t3 - 3 * t2 + 1) * p1 + (t3 - 2 * t2 + t) * m1 + (-2 * t3 + 3 * t2) * p2 + (t3 - t2) * m2
            return v if len(v) > 1 else float(v[0])
    v = vals[-1]
    return v if len(v) > 1 else float(v[0])


def ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------------------- gait
GROUP = {(1, 0): 0, (-1, 1): 0, (1, 2): 0, (-1, 3): 0, (-1, 0): 1, (1, 1): 1, (-1, 2): 1, (1, 3): 1}


def gait(f, N, stride, duty, lift, lag=0.07, move=True):
    """Foot targets for an alternating tetrapod gait at frame f of an N-frame cycle; the root travels `stride` per
    cycle along -Y (if move). Returns (root position, {leg: (target, tarsus_deg)}, swing amount per leg)."""
    fwd = Vector((0, -1, 0))
    root = fwd * (stride * f / N) if move else Vector()
    exc = stride * duty                       # how far each foot moves relative to the body during stance
    out, swing = {}, {}
    for s, i in LEG_KEYS:
        ph = (f / N + 0.5 * GROUP[(s, i)] + lag * (3 - i)) % 1.0
        F0 = neutral_foot(s, i)
        if ph < duty:
            u = 0.5 - ph / duty
            z, tars, sw = 0.0, -36.0, 0.0
        else:
            q = (ph - duty) / (1 - duty)
            u = -0.5 + ease(q)
            z = lift * math.sin(math.pi * q) ** 0.8
            tars, sw = -36.0 - 34.0 * math.sin(math.pi * q), math.sin(math.pi * q)
        tgt = root + F0 + fwd * exc * u
        tgt.z = F0.z + z
        out[(s, i)] = (tgt, tars)
        swing[(s, i)] = sw
    return root, out, swing


def gait_pose(f, N, stride, duty, lift, body_z=0.0, pitch=0.0, bob=0.012, sway=1.5, abd_swing=2.5, move=True):
    """Distances in adult metres (scaled by the kind's size)."""
    k = SB.K.size
    p = SpiderPose()
    root, feet, swing = gait(f, N, stride * k, duty, lift * k, move=move)
    p.root = root
    ph = 2 * math.pi * f / N
    p.body = Vector((0, 0, body_z * k - bob * k * math.cos(2 * ph)))
    p.pitch = pitch + 0.8 * math.sin(2 * ph)
    p.roll = sway * math.sin(ph)
    p.yaw = 1.2 * sway * math.sin(ph + 0.6)
    p.abd = [abd_swing * math.sin(2 * ph - 0.9), -2.0 * sway * math.sin(ph - 0.8), -sway * math.sin(ph - 0.5)]
    for k, (tgt, tars) in feet.items():
        p.legs[k] = Leg(target=tgt, tarsus=tars)
    for s in (1, -1):                         # palps paddle with the front legs
        sw = swing[(s, 0)]
        p.palp[s] = [10 * sw - 4, -6 * sw, -12 * sw]
    p.chel = [2 * math.sin(ph), 0.0]
    return p


# ----------------------------------------------------------------------------------------- key-pose clips
def keyed_pose(f, tracks, loop=None):
    """tracks: dict of parameter -> keys. Legs: 'leg:<s><i>' -> keys of dicts are awkward, so leg tracks are
    'lt:<s><i>' (target offset from the neutral foot, xyz), 'lw:<s><i>' (FK weight), with FK angles and yaw fixed per
    clip in tracks['fk'][(s, i)] = (yaw, angles)."""
    p = SpiderPose()
    g = lambda k, d: track(tracks[k], f, loop) if k in tracks else d
    sz = SB.K.size                                       # offsets are adult metres
    p.root = Vector(g('root', (0, 0, 0))) * sz
    p.body = Vector(g('body', (0, 0, 0))) * sz
    p.abd_scale = g('abs', 1.0)
    p.pitch, p.yaw, p.roll = g('pitch', 0.0), g('yaw', 0.0), g('roll', 0.0)
    p.abd = list(np.atleast_1d(g('abd', (0.0, 0.0, 0.0))))
    p.chel = list(np.atleast_1d(g('chel', (0.0, 0.0))))
    p.fang = g('fang', 0.0)
    for s in (1, -1):
        p.palp[s] = list(np.atleast_1d(g('palp', (0.0, 0.0, 0.0))))
    fk = tracks.get('fk', {})
    for s, i in LEG_KEYS:
        key = f"{'L' if s > 0 else 'R'}{i + 1}"
        off = Vector(g('lt:' + key, (0, 0, 0))) * sz
        F0 = neutral_foot(s, i)
        tgt = p.root + F0 + Vector((off.x * s, off.y, off.z))
        if SB.K.level_feet and tgt.z < F0.z:              # the tracks' spline overshoots: never below the ground
            tgt.z = F0.z
        w = g('lw:' + key, 0.0)
        tars = g('ta:' + key, -36.0)
        yaw, ang = fk.get((s, i), (None, None))
        p.legs[(s, i)] = Leg(target=tgt, tarsus=tars, femur=g('fe:' + key, None), fk=ang, fk_yaw=yaw,
                             w=max(0.0, min(1.0, w)))
    return p


def _clip_idle():
    N = 90
    T = {
        'body': [(0, (0, 0, 0)), (45, (0, 0.006, -0.012)), (90, (0, 0, 0))],
        'abd': [(0, (0, 0, 0)), (40, (2.2, 0.6, 0)), (90, (0, 0, 0))],
        'pitch': [(0, 0.0), (45, 1.0), (90, 0.0)],
        'palp': [(0, (0, 0, 0)), (20, (6, -8, -10)), (28, (0, 0, 0)), (60, (3, 4, 6)), (70, (0, 0, 0)), (90, (0, 0, 0))],
        'chel': [(0, (0, 0)), (50, (0, 0)), (55, (4, 3)), (60, (0, 0)), (90, (0, 0))],
        'fang': [(0, 0.0), (50, 0.0), (55, 12.0), (60, 0.0), (90, 0.0)],
        # L1 lifts and taps, later R2 shifts its foot a little
        'lt:L1': [(0, (0, 0, 0)), (24, (0, 0, 0)), (32, (0.02, -0.06, 0.16)), (38, (0.02, -0.08, 0.02)),
                  (42, (0.02, -0.08, 0.10)), (48, (0, 0, 0)), (90, (0, 0, 0))],
        'ta:L1': [(0, -36.0), (24, -36.0), (32, -62.0), (38, -40.0), (42, -55.0), (48, -36.0), (90, -36.0)],
        'lt:R2': [(0, (0, 0, 0)), (62, (0, 0, 0)), (68, (-0.02, -0.04, 0.10)), (74, (0, 0, 0)), (90, (0, 0, 0))],
        'ta:R2': [(0, -36.0), (62, -36.0), (68, -60.0), (74, -36.0), (90, -36.0)],
    }
    T = _tweak("Idle", T)
    return N, lambda f: keyed_pose(f, T, loop=N), True


def _gait(name):
    g = dict(family()['gait'][name])
    N = g.pop('N')
    return N, lambda f: gait_pose(f, N, **g), True


def _clip_walk():
    return _gait("Walk")


def _clip_run():
    return _gait("Run")


RAISED = (-8, 78, 34, -6, -34)             # a front leg held high
REAR_LEGS = [(1, 2), (-1, 2), (1, 3), (-1, 3)]


def _clip_hit():
    N = 15
    T = {
        'body': [(0, (0, 0, 0)), (3, (0, 0.09, 0.04)), (7, (0, 0.05, -0.03)), (15, (0, 0, 0))],
        'pitch': [(0, 0.0), (3, 9.0), (8, -2.0), (15, 0.0)],
        'roll': [(0, 0.0), (3, -4.0), (9, 1.5), (15, 0.0)],
        'abd': [(0, (0, 0, 0)), (4, (-7, 4, 0)), (9, (4, -2, 0)), (15, (0, 0, 0))],
        'chel': [(0, (0, 0)), (3, (8, 10)), (10, (0, 0)), (15, (0, 0))],
        'fang': [(0, 0.0), (3, 25.0), (10, 0.0), (15, 0.0)],
        'palp': [(0, (0, 0, 0)), (3, (18, -20, -20)), (12, (0, 0, 0)), (15, (0, 0, 0))],
        'lt:L1': [(0, (0, 0, 0)), (4, (0, 0.05, 0.08)), (9, (0, 0.02, 0)), (15, (0, 0, 0))],
        'lt:R1': [(0, (0, 0, 0)), (5, (0, 0.04, 0.06)), (10, (0, 0.02, 0)), (15, (0, 0, 0))],
    }
    T = _tweak("Hit", T)
    return N, lambda f: keyed_pose(f, T), False


def _clip_bite():
    N = 36
    lunge = -0.34
    T = {
        'body': [(0, (0, 0, 0)), (10, (0, 0.13, -0.07)), (15, (0, lunge, -0.02)), (19, (0, lunge + 0.03, -0.05)),
                 (28, (0, -0.06, 0)), (36, (0, 0, 0))],
        'pitch': [(0, 0.0), (10, 10.0), (15, -12.0), (19, -9.0), (28, 0.0), (36, 0.0)],
        'abd': [(0, (0, 0, 0)), (10, (-6, 0, 0)), (15, (8, 0, 0)), (22, (2, 0, 0)), (36, (0, 0, 0))],
        'chel': [(0, (0, 0)), (9, (-14, 16)), (13, (-18, 20)), (15, (10, -4)), (20, (6, 0)), (30, (0, 0)), (36, (0, 0))],
        'fang': [(0, 0.0), (9, 55.0), (13, 60.0), (15, -6.0), (22, 0.0), (36, 0.0)],
        'palp': [(0, (0, 0, 0)), (9, (35, -10, 10)), (15, (10, -20, -30)), (28, (0, 0, 0)), (36, (0, 0, 0))],
        'fk': {(1, 0): (58, RAISED), (-1, 0): (58, RAISED), (1, 1): (35, (-8, 64, 18, -30, -40)),
               (-1, 1): (35, (-8, 64, 18, -30, -40))},
        'lw:L1': [(0, 0.0), (8, 1.0), (13, 1.0), (16, 0.0), (36, 0.0)],
        'lw:R1': [(0, 0.0), (8, 1.0), (13, 1.0), (16, 0.0), (36, 0.0)],
        'lw:L2': [(0, 0.0), (9, 0.5), (14, 0.0), (36, 0.0)],
        'lw:R2': [(0, 0.0), (9, 0.5), (14, 0.0), (36, 0.0)],
        # front feet come down ahead to pin the prey, then step back
        'lt:L1': [(0, (0, 0, 0)), (13, (0, -0.30, 0.3)), (16, (0, -0.45, 0)), (26, (0, -0.35, 0)), (32, (0, -0.1, 0.1)),
                  (36, (0, 0, 0))],
        'lt:R1': [(0, (0, 0, 0)), (13, (0, -0.30, 0.3)), (16, (0, -0.45, 0)), (27, (0, -0.35, 0)), (33, (0, -0.1, 0.1)),
                  (36, (0, 0, 0))],
        'lt:L2': [(0, (0, 0, 0)), (14, (0, -0.25, 0.12)), (17, (0, -0.28, 0)), (29, (0, -0.25, 0)), (34, (0, -0.1, 0.08)),
                  (36, (0, 0, 0))],
        'lt:R2': [(0, (0, 0, 0)), (14, (0, -0.25, 0.12)), (17, (0, -0.28, 0)), (30, (0, -0.25, 0)), (35, (0, -0.1, 0.08)),
                  (36, (0, 0, 0))],
    }
    T = _tweak("Bite", T)
    return N, lambda f: keyed_pose(f, T), False


def _clip_strike():
    N = 40
    T = {
        'body': [(0, (0, 0, 0)), (12, (0, 0.10, 0.14)), (18, (0, 0.08, 0.16)), (22, (0, -0.12, -0.06)),
                 (26, (0, -0.10, -0.04)), (40, (0, 0, 0))],
        'pitch': [(0, 0.0), (12, 20.0), (18, 23.0), (22, -8.0), (26, -5.0), (40, 0.0)],
        'abd': [(0, (0, 0, 0)), (12, (6, 0, 0)), (22, (12, 0, 0)), (30, (0, 0, 0)), (40, (0, 0, 0))],
        'chel': [(0, (0, 0)), (12, (-10, 14)), (22, (6, 0)), (32, (0, 0)), (40, (0, 0))],
        'fang': [(0, 0.0), (12, 45.0), (22, 10.0), (32, 0.0), (40, 0.0)],
        'palp': [(0, (0, 0, 0)), (12, (40, 10, 20)), (22, (0, -10, -10)), (40, (0, 0, 0))],
        'fk': {(1, 0): (54, (-8, 66, 34, 4, -24)), (-1, 0): (54, (-8, 66, 34, 4, -24)),
               (1, 1): (30, (-8, 58, 24, -6, -28)), (-1, 1): (30, (-8, 58, 24, -6, -28))},
        'lw:L1': [(0, 0.0), (10, 1.0), (18, 1.0), (21, 0.0), (40, 0.0)],
        'lw:R1': [(0, 0.0), (10, 1.0), (18, 1.0), (21, 0.0), (40, 0.0)],
        'lw:L2': [(0, 0.0), (11, 1.0), (18, 1.0), (21, 0.0), (40, 0.0)],
        'lw:R2': [(0, 0.0), (11, 1.0), (18, 1.0), (21, 0.0), (40, 0.0)],
        'lt:L1': [(0, (0, 0, 0)), (18, (0, -0.25, 0.5)), (22, (0.0, -0.40, 0)), (30, (0, -0.40, 0)), (36, (0, -0.1, 0.1)),
                  (40, (0, 0, 0))],
        'lt:R1': [(0, (0, 0, 0)), (18, (0, -0.25, 0.5)), (22, (0.0, -0.40, 0)), (31, (0, -0.40, 0)), (37, (0, -0.1, 0.1)),
                  (40, (0, 0, 0))],
        'lt:L2': [(0, (0, 0, 0)), (18, (0, -0.2, 0.4)), (22, (0.05, -0.30, 0)), (32, (0.05, -0.3, 0)), (38, (0, -0.1, 0.08)),
                  (40, (0, 0, 0))],
        'lt:R2': [(0, (0, 0, 0)), (18, (0, -0.2, 0.4)), (22, (0.05, -0.30, 0)), (33, (0.05, -0.3, 0)), (39, (0, -0.1, 0.08)),
                  (40, (0, 0, 0))],
        'ta:L1': [(0, -36.0), (22, -36.0)], 'ta:R1': [(0, -36.0), (22, -36.0)],
    }
    T = _tweak("Strike", T)
    return N, lambda f: keyed_pose(f, T), False


def _clip_webspit():
    N = 48
    T = {
        'body': [(0, (0, 0, 0)), (12, (0, -0.03, -0.05)), (18, (0, -0.05, -0.07)), (20, (0, 0.02, -0.04)),
                 (36, (0, -0.02, -0.05)), (48, (0, 0, 0))],
        'pitch': [(0, 0.0), (12, -7.0), (18, -8.0), (20, -4.0), (36, -6.0), (48, 0.0)],
        'abd': [(0, (0, 0, 0)), (12, (104, 0, 0)), (16, (96, 0, 0)), (19, (116, 0, 0)), (21, (108, 0, 0)),
                (34, (104, 0, 0)), (48, (0, 0, 0))],
        'chel': [(0, (0, 0)), (12, (-4, 6)), (36, (-4, 6)), (48, (0, 0))],
        'fang': [(0, 0.0), (12, 20.0), (36, 20.0), (48, 0.0)],
        'palp': [(0, (0, 0, 0)), (12, (20, 10, 10)), (36, (20, 10, 10)), (48, (0, 0, 0))],
        # rear legs spread and brace
        'lt:L4': [(0, (0, 0, 0)), (6, (0.05, 0.05, 0.12)), (10, (0.12, 0.14, 0)), (40, (0.12, 0.14, 0)),
                  (44, (0.06, 0.06, 0.10)), (48, (0, 0, 0))],
        'lt:R4': [(0, (0, 0, 0)), (8, (0.05, 0.05, 0.12)), (12, (0.12, 0.14, 0)), (42, (0.12, 0.14, 0)),
                  (46, (0.06, 0.06, 0.10)), (48, (0, 0, 0))],
    }
    T = _tweak("WebSpit", T)
    return N, lambda f: keyed_pose(f, T), False


def _clip_threat():
    N = 72
    up = (-10, 58, 22, -8, -30)
    T = {
        'body': [(0, (0, 0, 0)), (12, (0, 0.10, 0.17)), (36, (0, 0.09, 0.18)), (60, (0, 0.10, 0.17)), (72, (0, 0, 0))],
        'pitch': [(0, 0.0), (12, 22.0), (24, 19.0), (36, 23.0), (48, 20.0), (60, 22.0), (72, 0.0)],
        'yaw': [(0, 0.0), (12, 0.0), (26, 5.0), (40, -5.0), (54, 4.0), (60, 0.0), (72, 0.0)],
        'abd': [(0, (0, 0, 0)), (12, (8, 0, 0)), (36, (12, 0, 0)), (60, (8, 0, 0)), (72, (0, 0, 0))],
        'chel': [(0, (0, 0)), (12, (-12, 18)), (20, (-18, 24)), (28, (-12, 18)), (40, (-18, 24)), (48, (-12, 18)),
                 (60, (-12, 18)), (72, (0, 0))],
        'fang': [(0, 0.0), (12, 50.0), (20, 70.0), (28, 45.0), (40, 70.0), (48, 45.0), (60, 50.0), (72, 0.0)],
        'palp': [(0, (0, 0, 0)), (12, (55, 25, 30)), (36, (60, 20, 25)), (60, (55, 25, 30)), (72, (0, 0, 0))],
        'fk': {(1, 0): (60, up), (-1, 0): (60, up), (1, 1): (32, (-10, 50, 14, -18, -34)),
               (-1, 1): (32, (-10, 50, 14, -18, -34))},
        'lw:L1': [(0, 0.0), (10, 1.0), (62, 1.0), (70, 0.0), (72, 0.0)],
        'lw:R1': [(0, 0.0), (10, 1.0), (62, 1.0), (70, 0.0), (72, 0.0)],
        'lw:L2': [(0, 0.0), (12, 1.0), (60, 1.0), (69, 0.0), (72, 0.0)],
        'lw:R2': [(0, 0.0), (12, 1.0), (60, 1.0), (69, 0.0), (72, 0.0)],
        'lt:L1': [(0, (0, 0, 0)), (10, (0, 0, 0.4)), (62, (0, 0, 0.4)), (70, (0, 0, 0.05)), (72, (0, 0, 0))],
        'lt:R1': [(0, (0, 0, 0)), (10, (0, 0, 0.4)), (62, (0, 0, 0.4)), (70, (0, 0, 0.05)), (72, (0, 0, 0))],
        'lt:L2': [(0, (0, 0, 0)), (12, (0, 0, 0.3)), (60, (0, 0, 0.3)), (69, (0, 0, 0.05)), (72, (0, 0, 0))],
        'lt:R2': [(0, (0, 0, 0)), (12, (0, 0, 0.3)), (60, (0, 0, 0.3)), (69, (0, 0, 0.05)), (72, (0, 0, 0))],
        # the back legs step in under the raised body
        'lt:L3': [(0, (0, 0, 0)), (5, (0, -0.05, 0.10)), (10, (0, -0.10, 0)), (64, (0, -0.10, 0)), (68, (0, -0.05, 0.08)),
                  (72, (0, 0, 0))],
        'lt:R3': [(0, (0, 0, 0)), (7, (0, -0.05, 0.10)), (12, (0, -0.10, 0)), (62, (0, -0.10, 0)), (66, (0, -0.05, 0.08)),
                  (72, (0, 0, 0))],
    }
    T = _tweak("Threat", T)
    return N, lambda f: keyed_pose(f, T), False


CURL = (-15, -68, -150, -212, -248)     # dead: every joint flexed, legs folded over the belly


def _clip_death():
    N = 60
    T = {
        # recoil, legs buckle, body drops, rolls over onto its back
        'body': [(0, (0, 0, 0)), (5, (0, 0.06, 0.08)), (16, (0.05, 0.05, -0.20)), (26, (0.12, 0.05, -0.12)),
                 (36, (0.18, 0.05, -0.02)), (44, (0.16, 0.05, -0.16)), (52, (0.14, 0.05, -0.20)), (60, (0.14, 0.05, -0.20))],
        'pitch': [(0, 0.0), (5, 12.0), (16, -6.0), (36, -4.0), (52, 8.0), (60, 8.0)],
        'roll': [(0, 0.0), (5, -5.0), (16, 8.0), (26, 70.0), (36, 150.0), (44, 178.0), (50, 172.0), (56, 180.0), (60, 180.0)],
        'abd': [(0, (0, 0, 0)), (5, (-12, 0, 0)), (16, (6, 4, 0)), (36, (10, -6, 0)), (52, (6, 0, 0)), (60, (6, 0, 0))],
        'chel': [(0, (0, 0)), (5, (-10, 16)), (30, (4, 6)), (60, (6, 4))],
        'fang': [(0, 0.0), (5, 50.0), (30, 20.0), (60, 30.0)],
        'palp': [(0, (0, 0, 0)), (5, (30, -20, -20)), (40, (20, -60, -70)), (60, (25, -70, -80))],
        'fk': {k: (None, CURL) for k in LEG_KEYS},
    }
    for s, i in LEG_KEYS:
        key = f"{'L' if s > 0 else 'R'}{i + 1}"
        d = 2 * i + (0 if s > 0 else 1)
        T['lw:' + key] = [(0, 0.0), (12 + d, 0.15), (24 + d, 0.75), (40, 1.0), (47, 0.9), (54 + (d % 3), 1.0), (60, 1.0)]
        T['lt:' + key] = [(0, (0, 0, 0)), (16, (0.08, 0.0, 0)), (60, (0.08, 0.0, 0))]
    T = _tweak("Death", T)
    return N, lambda f: keyed_pose(f, T), False


def _clip_getup():
    """From the Death end pose: push off, roll back over, legs unfold and find the ground, settle."""
    N = 40
    T = {
        'body': [(0, (0.14, 0.05, -0.20)), (8, (0.14, 0.05, -0.10)), (20, (0.07, 0.03, -0.06)), (30, (0, 0, -0.03)),
                 (40, (0, 0, 0))],
        'pitch': [(0, 8.0), (10, 4.0), (24, -4.0), (32, 2.0), (40, 0.0)],
        'roll': [(0, 180.0), (5, 182.0), (14, 120.0), (22, 25.0), (28, -4.0), (34, 1.5), (40, 0.0)],
        'abd': [(0, (6, 0, 0)), (14, (-8, 5, 0)), (26, (6, -3, 0)), (40, (0, 0, 0))],
        'chel': [(0, (6, 4)), (20, (-4, 8)), (40, (0, 0))],
        'fang': [(0, 30.0), (20, 20.0), (40, 0.0)],
        'palp': [(0, (25, -70, -80)), (22, (15, -20, -20)), (40, (0, 0, 0))],
        'fk': {k: (None, CURL) for k in LEG_KEYS},
    }
    for s, i in LEG_KEYS:
        key = f"{'L' if s > 0 else 'R'}{i + 1}"
        d = 2 * i + (0 if s > 0 else 1)
        T['lw:' + key] = [(0, 1.0), (4 + d // 2, 1.0), (16 + d, 0.45), (26 + d // 2, 0.0), (40, 0.0)]
        T['lt:' + key] = [(0, (0.08, 0.0, 0)), (24, (0.04, 0.0, 0.05)), (32 + d // 2, (0, 0, 0)), (40, (0, 0, 0))]
    T = _tweak("GetUp", T)
    return N, lambda f: keyed_pose(f, T), False


CLIPS = {"GetUp": _clip_getup, "Idle": _clip_idle, "Walk": _clip_walk, "Run": _clip_run, "Hit": _clip_hit, "Death": _clip_death,
         "Bite": _clip_bite, "Strike": _clip_strike, "WebSpit": _clip_webspit, "Threat": _clip_threat}


# ----------------------------------------------------------------------------------------- the broodmother's own clips
def _own(N30, pose30, loop=False):
    """A kind's own clip written in 30 fps frames, played at the kind's fps."""
    k = clip_fps() / 30.0
    if k == 1.0:
        return N30, pose30, loop
    return int(round(N30 * k)), (lambda f: pose30(f / k)), loop


def _clip_slump(N30=78, drop=0.31, roll=11.0, curl=0.0, sag=-9.0, nose=-7.0, recoil=-9.0):
    """Death without the roll (the adult's roll puts its legs through the ground, and a bloated broodmother can't
    turn over): recoils, the legs give way and fold up (knees high, feet drawn in), it sinks onto its belly and leans
    over, the abdomen sags onto the ground and goes slack; with `curl`, the legs then twitch in toward the body.
    Distances in adult metres, frames at 30 fps for N30 = 78 (stretched to N30)."""
    T = _slump_tracks(N30, drop, roll, curl, sag, nose, recoil)
    return _own(N30, lambda f: keyed_pose(f, T))


def _slump_tracks(N30, drop, roll, curl, sag, nose, recoil):
    """The key-pose tracks of _clip_slump (30 fps frames); _clip_rise starts from their last keys."""
    k = N30 / 78.0
    F = lambda f: f * k
    r = roll / 11.0
    sx = 0.03 if roll >= 0 else -0.03
    T = {
        'body': [(F(0), (0, 0, 0)), (F(6), (0, 0.05, 0.06)), (F(20), (0, 0.02, -drop * 0.32)),
                 (F(32), (sx * 0.6, 0.0, -drop * 0.77)), (F(44), (sx, -0.01, -drop)), (F(52), (sx, -0.01, -drop * 0.95)),
                 (F(60), (sx, -0.01, -drop)), (F(78), (sx, -0.01, -drop))],
        'pitch': [(F(0), 0.0), (F(6), 9.0), (F(20), -3.0), (F(36), nose), (F(78), nose)],
        'roll': [(F(0), 0.0), (F(6), -3.0 * r), (F(26), 5.0 * r), (F(44), 11.0 * r), (F(52), 9.5 * r), (F(60), 11.0 * r),
                 (F(78), 11.0 * r)],
        'abd': [(F(0), (0, 0, 0)), (F(6), (recoil, 0, 0)), (F(24), (-3, 3, 0)), (F(44), (sag + 1, 6, 6)), (F(60), (sag, 6, 7)),
                (F(78), (sag, 6, 7))],
        'abs': [(F(0), 1.0), (F(40), 1.0), (F(62), 0.955), (F(78), 0.955)],
        'chel': [(F(0), (0, 0)), (F(5), (-10, 16)), (F(30), (4, 6)), (F(78), (6, 4))],
        'fang': [(F(0), 0.0), (F(5), 50.0), (F(30), 20.0), (F(78), 30.0)],
        'palp': [(F(0), (0, 0, 0)), (F(5), (30, -20, -20)), (F(40), (28, 6, 14)), (F(78), (30, 12, 24))],
    }
    pull = {0: (-0.30, 0.22), 1: (-0.30, 0.10), 2: (-0.28, -0.08), 3: (-0.26, -0.18)}   # feet drawn in (adult m)
    for s_, i in LEG_KEYS:
        key = f"{'L' if s_ > 0 else 'R'}{i + 1}"
        d = (2 * i + (0 if s_ > 0 else 1)) * k
        px, py = pull[i]
        lt = [(F(0), (0, 0, 0)), (F(14) + d, (0, 0, 0.05)), (F(24) + d, (px * 0.6, py * 0.6, 0)),
              (F(46) + d / 2, (px, py, 0)), (F(78), (px, py, 0))]
        ta = [(F(0), -36.0), (F(30), -45.0), (F(60), -62.0), (F(78), -62.0)]
        if curl > 0:                                     # a last twitch: the feet curl up and in, off the ground
            c = (px - 0.08 * curl, py * (1 - 0.3 * curl), 0.10 * curl)
            lt = lt[:-1] + [(F(54) + d / 2, (px, py, 0)), (F(61) + d / 2, c),
                            (F(65) + d / 2, (c[0] * 0.9, c[1], c[2] * 0.6)), (F(70) + d / 2, c), (F(78), c)]
            ta = ta[:-1] + [(F(61) + d / 2, -110.0), (F(78), -110.0)]
        T['lt:' + key] = lt
        T['fe:' + key] = [(F(0), 50.0), (F(16) + d, 55.0), (F(40), 72.0), (F(78), 74.0)]
        T['ta:' + key] = ta
    return T


SLUMP_DEFAULTS = dict(N30=78, drop=0.31, roll=11.0, curl=0.0, sag=-9.0, nose=-7.0, recoil=-9.0)


def _clip_rise(slump, N30=40, settle=0.014):
    """GetUp for the kinds that die slumped (2026-10-23): from the slump's end pose (its tracks' last keys) the palps
    and fangs stir, the legs unfold and step out one by one, front pairs first, and plant at the stance; the body
    pushes up off its belly and levels, the abdomen lifts off the ground and fills out, a small bob as it settles; it
    ends on Idle's first frame (every track at Idle's start, the femur at the kind's own preference). `slump`: the
    kind's _clip_slump arguments. Distances in adult metres, frames at 30 fps for N30 (stretched to the kind's fps)."""
    S = _slump_tracks(**dict(SLUMP_DEFAULTS, **slump))
    end = {k: v[-1][1] for k, v in S.items()}
    n = float(N30)
    F = lambda t: t * n
    bx, by, bz = end['body']
    a0 = end['abd']
    r = 1.0 if end['roll'] >= 0 else -1.0
    T = {
        # down on the belly until the legs are out, then up (a little higher than standing) and settle
        'body': [(F(0), (bx, by, bz)), (F(0.22), (bx, by, bz + 0.02 * abs(bz))), (F(0.45), (bx * 0.6, by * 0.5, bz * 0.62)),
                 (F(0.66), (bx * 0.15, 0.0, bz * 0.12)), (F(0.80), (0.0, 0.0, settle)), (F(0.91), (0.0, 0.0, -settle * 0.3)),
                 (F(1.0), (0.0, 0.0, 0.0))],
        'pitch': [(F(0), end['pitch']), (F(0.20), end['pitch']), (F(0.48), 3.5), (F(0.70), -1.5), (F(0.86), 0.5),
                  (F(1.0), 0.0)],
        'roll': [(F(0), end['roll']), (F(0.25), end['roll'] * 0.9), (F(0.55), -2.0 * r), (F(0.75), 0.8 * r), (F(1.0), 0.0)],
        'abd': [(F(0), a0), (F(0.30), (a0[0] * 0.8, a0[1] * 0.6, a0[2] * 0.6)), (F(0.62), (5.0, -1.5, -1.0)),
                (F(0.84), (-1.5, 0.5, 0.0)), (F(1.0), (0.0, 0.0, 0.0))],
        'abs': [(F(0), end['abs']), (F(0.30), end['abs']), (F(0.62), 1.0), (F(1.0), 1.0)],
        'chel': [(F(0), end['chel']), (F(0.12), (-6.0, 10.0)), (F(0.30), (2.0, 4.0)), (F(0.65), (-3.0, 5.0)),
                 (F(1.0), (0.0, 0.0))],
        'fang': [(F(0), end['fang']), (F(0.12), 40.0), (F(0.35), 12.0), (F(0.70), 4.0), (F(1.0), 0.0)],
        'palp': [(F(0), end['palp']), (F(0.10), (34.0, 0.0, 6.0)), (F(0.22), (18.0, -10.0, -12.0)),
                 (F(0.45), (8.0, 4.0, 6.0)), (F(0.75), (2.0, -2.0, -2.0)), (F(1.0), (0.0, 0.0, 0.0))],
    }
    D = rest_data()
    for s_, i in LEG_KEYS:
        key = f"{'L' if s_ > 0 else 'R'}{i + 1}"
        d = 2 * i + (0 if s_ > 0 else 1)                  # L1 R1 L2 R2 ... : front pairs first
        t0, e = 0.06 + 0.045 * d, end['lt:' + key]
        mid = (e[0] * 0.4, e[1] * 0.4, max(e[2], 0.0) + 0.09)
        T['lt:' + key] = [(F(0), e), (F(t0), e), (F(t0 + 0.08), mid), (F(t0 + 0.16), (0, 0, 0)), (F(1.0), (0, 0, 0))]
        ta = end['ta:' + key]
        T['ta:' + key] = [(F(0), ta), (F(t0), ta), (F(t0 + 0.08), -72.0), (F(t0 + 0.16), -36.0), (F(1.0), -36.0)]
        fp = math.degrees(D[(s_, i)][3])                  # the kind's femur preference (Idle's: no 'fe' track)
        fe = end['fe:' + key]
        T['fe:' + key] = [(F(0), fe), (F(t0 + 0.16), fe - 0.25 * (fe - fp)), (F(0.80), fp), (F(1.0), fp)]
    return _own(N30, lambda f: keyed_pose(f, T))


SPAWN_DROP, SPAWN_EVENT = 84, 90          # frames: the egg leaves the spinnerets, lands (event 'Spawn' 3.0 s)


def _clip_spawn():
    """Broodmother lays an egg: the abdomen swells and pulses, she sinks and tips the abdomen down, an egg is squeezed
    out of the spinnerets, drops under Socket_Spinneret (event 'Spawn' as it lands) and is gone a frame later (a game
    puts its own egg or spiderling there), she rises. The egg goes back inside at scale 0 and is scaled up hidden."""
    N = 126
    T = {
        'body': [(0, (0, 0, 0)), (18, (0, 0, 0)), (46, (0, 0.03, -0.06)), (96, (0, 0.03, -0.06)), (116, (0, 0, 0)),
                 (126, (0, 0, 0))],
        'pitch': [(0, 0.0), (18, 0.0), (46, 2.0), (96, 2.0), (116, 0.0), (126, 0.0)],
        'abd': [(0, (0, 0, 0)), (20, (3, 0, 0)), (48, (-3, 0, 0)), (70, (-3.5, 2, 0)), (92, (-3, 0, 0)), (114, (0, 0, 0)),
                (126, (0, 0, 0))],
        'abs': [(0, 1.0), (8, 1.05), (14, 0.995), (22, 1.06), (30, 1.0), (54, 1.0), (60, 1.06), (66, 0.99), (73, 1.07),
                (79, 0.985), (85, 1.03), (92, 0.97), (110, 1.0), (126, 1.0)],
        'chel': [(0, (0, 0)), (20, (-4, 6)), (60, (-6, 8)), (100, (-4, 6)), (126, (0, 0))],
        'fang': [(0, 0.0), (20, 12.0), (74, 20.0), (100, 10.0), (126, 0.0)],
        'palp': [(0, (0, 0, 0)), (20, (12, 8, 6)), (70, (18, 10, 10)), (100, (8, 4, 4)), (126, (0, 0, 0))],
        # rear legs spread and brace, the third pair steps out
        'lt:L4': [(0, (0, 0, 0)), (8, (0.04, 0.04, 0.12)), (14, (0.14, 0.12, 0)), (104, (0.14, 0.12, 0)),
                  (110, (0.07, 0.06, 0.10)), (118, (0, 0, 0)), (126, (0, 0, 0))],
        'lt:R4': [(0, (0, 0, 0)), (11, (0.04, 0.04, 0.12)), (17, (0.14, 0.12, 0)), (106, (0.14, 0.12, 0)),
                  (112, (0.07, 0.06, 0.10)), (120, (0, 0, 0)), (126, (0, 0, 0))],
        'lt:L3': [(0, (0, 0, 0)), (18, (0, 0, 0)), (24, (0.05, 0.02, 0.10)), (30, (0.09, 0.03, 0)), (100, (0.09, 0.03, 0)),
                  (108, (0.04, 0.01, 0.08)), (116, (0, 0, 0)), (126, (0, 0, 0))],
        'lt:R3': [(0, (0, 0, 0)), (21, (0, 0, 0)), (27, (0.05, 0.02, 0.10)), (33, (0.09, 0.03, 0)), (102, (0.09, 0.03, 0)),
                  (110, (0.04, 0.01, 0.08)), (118, (0, 0, 0)), (126, (0, 0, 0))],
    }
    egg_out = [(0, 0.0), (54, 0.0), (SPAWN_DROP, 1.15)]          # x EGG_LEN, along the spinnerets' axis
    egg_scale = [(0, 1.0), (54, 0.72), (SPAWN_DROP, 1.0), (SPAWN_EVENT, 1.0), (SPAWN_EVENT + 2, 0.0), (118, 0.0),
                 (121, 1.0), (126, 1.0)]
    L = SE.EGG_LEN
    ground = {}

    def lin(keys, f):
        return float(np.interp(f, [k[0] for k in keys], [k[1] for k in keys]))

    def pose(f):
        p = keyed_pose(f, T)
        if 'G' not in ground:                                     # the egg lands under the spinnerets' socket
            q = keyed_pose(SPAWN_EVENT, T)
            m = pose_matrices(q)
            sock = m["Abdomen"] @ (bug_rig.frame_matrix(*rest_data()['B']["Abdomen"][:2]).inverted() @
                                   bug_rig.frame_matrix(*rest_data()['B']["Socket_Spinneret"][:2]))
            x, y = sock.translation.x, sock.translation.y
            a = math.radians(12)
            rot = Matrix(((math.cos(a), math.sin(a), 0), (-math.sin(a), math.cos(a), 0), (0, 0, 1))).transposed()
            ground["G"] = Matrix.Translation((x, y, SE.EGG_W * 0.485)) @ rot.to_4x4()
        if f <= SPAWN_EVENT + 2:
            drop = ease((f - SPAWN_DROP) / (SPAWN_EVENT - 2 - SPAWN_DROP)) if f > SPAWN_DROP else 0.0
            p.egg = (lin(egg_out, f) * L, drop, lin(egg_scale, f), ground['G'])
        else:                                                     # gone: back inside, scaled up hidden
            back = ease((f - SPAWN_EVENT - 3) / 20.0)
            p.egg = (1.15 * L * (1 - back), 1.0 - back, lin(egg_scale, f), ground['G'])
        return p
    return N, pose, False


SLUMP = {"Spiderling": dict(N30=50, drop=0.24, roll=-6.0, curl=0.6, sag=12.0, nose=2.0),
         "Broodmother": dict(drop=0.17, roll=9.0, sag=2.0, nose=-4.0, recoil=4.0)}
KIND_CLIPS = {"Spiderling": {"Death": lambda: _clip_slump(**SLUMP["Spiderling"]),
                             "GetUp": lambda: _clip_rise(SLUMP["Spiderling"], N30=30)},
              "Broodmother": {"Death": lambda: _clip_slump(**SLUMP["Broodmother"]), "Spawn": _clip_spawn,
                              "GetUp": lambda: _clip_rise(SLUMP["Broodmother"], N30=48)}}

# per kind: clips (in order), fps, tempo (duration factor on the adult's clip), gaits (adult metres, N in 30 fps frames),
# events (seconds, for its own clips; the adult's EVENTS scale with the tempo), tweaks (tracks merged into adult clips),
# which clips move (root motion)
FAMILY = {
    "Spider": dict(
        clips=tuple(CLIPS), fps=30, tempo={}, events={}, tweaks={}, moving=("Walk", "Run"),
        gait=dict(Walk=dict(N=24, stride=1.0, duty=0.62, lift=0.16),
                  Run=dict(N=12, stride=1.5, duty=0.5, lift=0.13, body_z=-0.05, pitch=-3.0, bob=0.018, sway=2.5,
                           abd_swing=4.0))),
    "Spiderling": dict(
        clips=("Idle", "Walk", "Run", "Hit", "Death", "GetUp", "Bite"), fps=60, moving=("Walk", "Run"),
        tempo=dict(Idle=0.7, Hit=0.75, Bite=0.7), events=dict(Death=[("Dead", 1.4)]),
        tweaks=dict(Idle={'palp': [(0, (0, 0, 0)), (10, (8, -10, -12)), (15, (0, 0, 0)), (30, (6, 6, 8)), (36, (0, 0, 0)),
                                   (52, (10, -6, -8)), (57, (0, 0, 0)), (72, (5, 8, 8)), (77, (0, 0, 0)), (90, (0, 0, 0))],
                          'yaw': [(0, 0.0), (40, 0.0), (43, 4.0), (60, 4.0), (63, 0.0), (90, 0.0)]},
                    Bite={'body': [(0, (0, 0, 0)), (10, (0, 0.13, -0.03)), (15, (0, -0.34, 0.0)), (19, (0, -0.31, -0.03)),
                                   (28, (0, -0.06, 0)), (36, (0, 0, 0))],
                          'abd': [(0, (0, 0, 0)), (10, (8, 0, 0)), (15, (12, 0, 0)), (22, (4, 0, 0)), (36, (0, 0, 0))],
                          'lt:L1': [(0, (0, 0, 0)), (13, (0, -0.22, 0.24)), (16, (0, -0.32, 0)), (26, (0, -0.25, 0)),
                                    (32, (0, -0.07, 0.08)), (36, (0, 0, 0))],
                          'lt:R1': [(0, (0, 0, 0)), (13, (0, -0.22, 0.24)), (16, (0, -0.32, 0)), (27, (0, -0.25, 0)),
                                    (33, (0, -0.07, 0.08)), (36, (0, 0, 0))]}),
        gait=dict(Walk=dict(N=10, stride=0.9, duty=0.6, lift=0.2, bob=0.014, sway=1.2, abd_swing=3.0),
                  Run=dict(N=6, stride=1.35, duty=0.5, lift=0.16, body_z=-0.04, pitch=-3.0, bob=0.02, sway=2.0,
                           abd_swing=4.5))),
    "Broodmother": dict(
        clips=("Idle", "Walk", "Hit", "Death", "GetUp", "Bite", "Threat", "Spawn"), fps=30, moving=("Walk",),
        tempo=dict(Idle=1.3, Hit=1.3, Bite=1.25, Threat=1.3),
        events=dict(Death=[("Dead", 2.2)], Spawn=[("Spawn", SPAWN_EVENT / 30.0)]),
        tweaks=dict(Idle={'abs': [(0, 1.0), (45, 1.03), (90, 1.0)]},
                    Threat={'abd': [(0, (0, 0, 0)), (12, (16, 0, 0)), (36, (20, 0, 0)), (60, (16, 0, 0)), (72, (0, 0, 0))],
                            'abs': [(0, 1.0), (12, 1.06), (60, 1.06), (72, 1.0)]},
                    Bite={'abd': [(0, (0, 0, 0)), (10, (12, 0, 0)), (15, (14, 0, 0)), (22, (6, 0, 0)), (36, (0, 0, 0))],
                          'pitch': [(0, 0.0), (10, 5.0), (15, -10.0), (19, -8.0), (28, 0.0), (36, 0.0)],
                          'body': [(0, (0, 0, 0)), (10, (0, 0.12, -0.02)), (15, (0, -0.30, 0.0)), (19, (0, -0.28, -0.03)),
                                   (28, (0, -0.06, 0)), (36, (0, 0, 0))]},
                    Hit={'abs': [(0, 1.0), (4, 0.97), (9, 1.02), (15, 1.0)],
                         'abd': [(0, (0, 0, 0)), (4, (3, 4, 0)), (9, (5, -2, 0)), (15, (0, 0, 0))]}),
        gait=dict(Walk=dict(N=40, stride=0.85, duty=0.7, lift=0.11, body_z=-0.01, bob=0.02, sway=2.2, abd_swing=3.5))),
}


def family():
    return FAMILY[SB.K.name]


def clip_fps():
    return family()['fps']


def clip_names():
    return list(family()['clips'])


def action_name(clip):
    return SB.K.action_prefix + clip


def _tweak(name, T):
    tw = family()['tweaks'].get(name)
    if tw:
        T = dict(T)
        T.update(tw)
    return T


# ----------------------------------------------------------------------------------------- build / export
def rig():
    return bpy.data.objects[SB.K.rig]


def clip_source(name):
    """(N in frames at the clip's fps, pose function of the frame, loop, events in seconds) for the active kind: the
    adult's clip played at the kind's tempo and fps, or the kind's own."""
    fam = family()
    own = KIND_CLIPS.get(SB.K.name, {})
    if name in own:
        N, fn, loop = own[name]()
        return N, fn, loop, fam['events'].get(name, [])
    N, fn, loop = CLIPS[name]()
    k = fam['tempo'].get(name, 1.0) * fam['fps'] / 30.0
    N2 = int(round(N * k))
    evs = fam['events'].get(name) or EVENTS.get(name, [])
    if N2 == N:
        return N, fn, loop, evs
    r = N / N2
    return N2, (lambda f: fn(f * r)), loop, [(e, t * (N2 / fam['fps']) / (N / 30.0)) for e, t in evs]


def build_clip(name, rig_ob=None):
    rig_ob = rig_ob or rig()
    N, fn, loop, events = clip_source(name)
    an = action_name(name)
    act = bpy.data.actions.get(an)
    if act is not None:
        bpy.data.actions.remove(act)
    act = bpy.data.actions.new(an)
    act.use_fake_user = True
    act["loop"] = loop
    act["frames"] = N
    for ev, t in events:
        act["event_" + ev] = t
    rig_ob.animation_data_create()
    rig_ob.animation_data.action = act
    R = bug_rig.rest(rig_ob)
    for pb in rig_ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1, 0, 0, 0)
    for f in range(N + 1):
        bug_rig.apply_pose(rig_ob, pose_matrices(fn(f)), frame=f, R=R, scaled=SB.K.scaled)
    for fc in _fcurves(act):
        for k in fc.keyframe_points:
            k.interpolation = 'LINEAR'
    act.frame_range = (0, N)
    return act


def _fcurves(act):
    if hasattr(act, "fcurves") and len(getattr(act, "fcurves", [])) > 0:
        return list(act.fcurves)
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                out += list(bag.fcurves)
    return out


def build_clips(names=None):
    _REST.clear()
    return {n: build_clip(n) for n in (names or clip_names())}


def use(name, rig_ob=None):
    """Show a clip on the rig and set the scene range to it."""
    rig_ob = rig_ob or rig()
    act = bpy.data.actions[action_name(name)]
    rig_ob.animation_data_create()
    rig_ob.animation_data.action = act
    scn = bpy.context.scene
    scn.frame_start, scn.frame_end = 0, int(act["frames"])
    scn.frame_set(0)


def clear(rig_ob=None):
    rig_ob = rig_ob or rig()
    if rig_ob.animation_data:
        rig_ob.animation_data.action = None
    bug_rig.reset_pose(rig_ob)


def still(p, rig_ob=None):
    """Pose the rig (no keys) from a SpiderPose, for tests."""
    rig_ob = rig_ob or rig()
    if rig_ob.animation_data:
        rig_ob.animation_data.action = None
    bug_rig.apply_pose(rig_ob, pose_matrices(p), keys=False)
    bpy.context.view_layer.update()
