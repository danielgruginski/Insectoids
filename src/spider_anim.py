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
"""
import bpy, math, os
import numpy as np
from mathutils import Vector, Matrix
from bug_common import ROOT
import spider_body as SB
import bug_rig

FPS = 30
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


def _euler(pitch, yaw, roll):
    return (Matrix.Rotation(rad(yaw), 4, 'Z') @ Matrix.Rotation(rad(-pitch), 4, 'X') @
            Matrix.Rotation(rad(roll), 4, 'Y'))


def _yaw_of(e_r, side):
    return math.atan2(-e_r.y, side * e_r.x)


def _e_r(psi, side):
    return Vector((side * math.cos(psi), -math.sin(psi), 0.0))


_REST = {}


def rest_data():
    if not _REST:
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
    e_r, ang = SB.solve_leg(C, Ls, tl, tarsus=rad(cmd.tarsus) if cmd.tarsus is not None else SB.TARSUS_PLANT,
                            femur_pref=rad(cmd.femur) if cmd.femur is not None else fp, side=s)
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
    out["Abdomen"] = MB @ Matrix.Translation(ped) @ _euler(-p.abd[0], p.abd[1], p.abd[2]) @ Matrix.Translation(-ped) @ R("Abdomen")
    for s in (1, -1):
        sfx = 'L' if s > 0 else 'R'
        ch = MB @ R(f"Chelicera{sfx}") @ Matrix.Rotation(rad(-p.chel[0]), 4, 'X') @ Matrix.Rotation(rad(s * p.chel[1]), 4, 'Z')
        out[f"Chelicera{sfx}"] = ch
        rel = R(f"Chelicera{sfx}").inverted() @ R(f"Fang{sfx}")
        out[f"Fang{sfx}"] = ch @ rel @ Matrix.Rotation(rad(s * p.fang), 4, 'Z')
        pc = SB.PALP
        C = Vector(pc['C']) * Vector((s, 1, 1)) + Vector((0, 0, SB.LIFT))
        e_r = _e_r(rad(pc['yaw']), s)
        ang = [rad(a + d) for a, d in zip(pc['angles'], p.palp[s])]
        for k, (h, fr) in enumerate(SB.leg_frames(C, pc['L'], e_r, ang)[:3]):
            out[f"Palp{sfx}_{('Femur', 'Tibia', 'Tarsus')[k]}"] = MB @ bug_rig.frame_matrix(h, fr)
    for s, i in LEG_KEYS:
        fr = leg_solution(p, s, i, MB)
        for j, seg in enumerate(SB.SEG_NAMES):
            out[SB.leg_name(i, s, seg)] = MB @ bug_rig.frame_matrix(fr[j][0], fr[j][1])
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
        tgt.z = z
        out[(s, i)] = (tgt, tars)
        swing[(s, i)] = sw
    return root, out, swing


def gait_pose(f, N, stride, duty, lift, body_z=0.0, pitch=0.0, bob=0.012, sway=1.5, abd_swing=2.5, move=True):
    p = SpiderPose()
    root, feet, swing = gait(f, N, stride, duty, lift, move=move)
    p.root = root
    ph = 2 * math.pi * f / N
    p.body = Vector((0, 0, body_z - bob * math.cos(2 * ph)))
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
    p.root = Vector(g('root', (0, 0, 0)))
    p.body = Vector(g('body', (0, 0, 0)))
    p.pitch, p.yaw, p.roll = g('pitch', 0.0), g('yaw', 0.0), g('roll', 0.0)
    p.abd = list(np.atleast_1d(g('abd', (0.0, 0.0, 0.0))))
    p.chel = list(np.atleast_1d(g('chel', (0.0, 0.0))))
    p.fang = g('fang', 0.0)
    for s in (1, -1):
        p.palp[s] = list(np.atleast_1d(g('palp', (0.0, 0.0, 0.0))))
    fk = tracks.get('fk', {})
    for s, i in LEG_KEYS:
        key = f"{'L' if s > 0 else 'R'}{i + 1}"
        off = Vector(g('lt:' + key, (0, 0, 0)))
        tgt = p.root + neutral_foot(s, i) + Vector((off.x * s, off.y, off.z))
        w = g('lw:' + key, 0.0)
        tars = g('ta:' + key, -36.0)
        yaw, ang = fk.get((s, i), (None, None))
        p.legs[(s, i)] = Leg(target=tgt, tarsus=tars, fk=ang, fk_yaw=yaw, w=max(0.0, min(1.0, w)))
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
    return N, lambda f: keyed_pose(f, T, loop=N), True


def _clip_walk():
    N = 24
    return N, lambda f: gait_pose(f, N, stride=1.0, duty=0.62, lift=0.16), True


def _clip_run():
    N = 12
    return N, lambda f: gait_pose(f, N, stride=1.5, duty=0.5, lift=0.13, body_z=-0.05, pitch=-3.0, bob=0.018,
                                  sway=2.5, abd_swing=4.0), True


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
    return N, lambda f: keyed_pose(f, T), False


CLIPS = {"GetUp": _clip_getup, "Idle": _clip_idle, "Walk": _clip_walk, "Run": _clip_run, "Hit": _clip_hit, "Death": _clip_death,
         "Bite": _clip_bite, "Strike": _clip_strike, "WebSpit": _clip_webspit, "Threat": _clip_threat}


# ----------------------------------------------------------------------------------------- build / export
def rig():
    return bpy.data.objects[bug_rig.RIG]


def build_clip(name, rig_ob=None):
    rig_ob = rig_ob or rig()
    N, fn, loop = CLIPS[name]()
    act = bpy.data.actions.get(name)
    if act is not None:
        bpy.data.actions.remove(act)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    act["loop"] = loop
    act["frames"] = N
    for ev, t in EVENTS.get(name, []):
        act["event_" + ev] = t
    rig_ob.animation_data_create()
    rig_ob.animation_data.action = act
    R = bug_rig.rest(rig_ob)
    for pb in rig_ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
        pb.rotation_quaternion = (1, 0, 0, 0)
    for f in range(N + 1):
        bug_rig.apply_pose(rig_ob, pose_matrices(fn(f)), frame=f, R=R)
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
    return {n: build_clip(n) for n in (names or CLIPS)}


def use(name, rig_ob=None):
    """Show a clip on the rig and set the scene range to it."""
    rig_ob = rig_ob or rig()
    act = bpy.data.actions[name]
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
