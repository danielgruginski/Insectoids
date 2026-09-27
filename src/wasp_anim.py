"""Giant wasp clips, keyed straight onto WaspRig (no constraints to bake). Actions are named Wasp_<Clip>.

Each frame is a WaspPose (body offset and tilt, head, gaster curl, wings, legs, antennae, mandibles) turned into
armature-space matrices and keyed through bug_rig.apply_pose, as for the spider. The skeleton always plays in place;
only the Motion bone travels (Unity's root-motion node), so looping clips never snap back.

Wings: the stroke flips between up and down every frame (15 beats a second at 30 fps), which reads as a buzz; the
hind wings are hooked to the forewings, as in real wasps, and follow them.

Clips (30 fps, wasp faces -Y, hovers with the thorax 1.7 m up):
  Idle     2.0 s loop   hover: bob, drift, abdomen pumping, legs and antennae swaying
  Fly      1.0 s loop   nose down, legs trailing, root motion 4 m/s
  Threat   1.6 s        abdomen curled forward and pumping, mandibles snapping, louder wings
  Sting    1.3 s        rears back, lunges 0.45 m with the stinger forward (event 'Sting' at 0.60 s)
  Dive     1.8 s        climbs, dives to 0.65 m over the ground, stings (event 'Sting' at 0.90 s), climbs back
  Hit      0.5 s
  Death    2.0 s        wings stop, falls, bounces and lies on its side with the legs curled (event 'Dead' 1.75 s)
  GetUp    1.5 s        from the Death pose: wings start, rolls upright and climbs back to the hover
"""
import bpy, math
import numpy as np
from mathutils import Vector, Matrix
import wasp_body as WB
import spider_body as SB
import bug_rig
from spider_anim import track, rad

FPS = 30
RIG = "WaspRig"
PAIRS = [(s, p) for s in (1, -1) for p in range(3)]
EVENTS = {"Sting": [("Sting", 0.60)], "Dive": [("Sting", 0.90)], "Death": [("Dead", 1.75)]}

HANG = {p: (WB.LEGS[p]['yaw'], WB.LEGS[p]['pose']) for p in range(3)}
TRAIL = {0: (-5, (-35, -12, -55, -90)), 1: (-40, (-35, -10, -50, -85)), 2: (-68, (-28, -6, -38, -70))}
GRAB = {0: (68, (-20, 12, -38, -78)), 1: (22, (-32, 0, -60, -100)), 2: HANG[2]}
CURL = {p: (HANG[p][0], (-55, -65, -150, -215)) for p in range(3)}


def action_name(clip):
    return "Wasp_" + clip


class WaspPose:
    def __init__(self):
        self.root = Vector()
        self.body = Vector()                 # offset of the thorax centre (world axes)
        self.pitch = self.yaw = self.roll = 0.0
        self.head = [0.0, 0.0, 0.0]          # pitch (nose up), yaw, roll
        self.gaster = [0.0, 0.0, 0.0]        # per bone, + lifts the tip, - curls it under
        self.gaster_yaw = 0.0
        self.stroke = 0.0                    # wing upstroke (+) / downstroke (-), degrees
        self.sweep = 0.0                     # + folds the wings back along the body
        self.twist = 0.0
        self.legs = {k: HANG[k[1]] for k in PAIRS}
        self.antenna = [0.0, 0.0, 0.0]       # scape pitch, flagellum pitch, spread
        self.mandible = 0.0                  # opening, degrees


def _euler(pitch, yaw, roll):
    return (Matrix.Rotation(rad(yaw), 4, 'Z') @ Matrix.Rotation(rad(-pitch), 4, 'X') @
            Matrix.Rotation(rad(roll), 4, 'Y'))


_REST = {}


def rest():
    if not _REST:
        _REST['B'] = WB.rest_bones()
    return _REST['B']


def pose_matrices(p):
    B = rest()
    R = lambda n: bug_rig.frame_matrix(B[n][0], B[n][1])
    rel = lambda a, b: R(a).inverted() @ R(b)
    M = Matrix.Translation(p.root)
    pv = B["Body"][0]
    MB = M @ Matrix.Translation(pv + p.body) @ _euler(p.pitch, p.yaw, p.roll) @ Matrix.Translation(-pv)
    X = lambda d: Matrix.Rotation(rad(d), 4, 'X')
    Y = lambda d: Matrix.Rotation(rad(d), 4, 'Y')
    Z = lambda d: Matrix.Rotation(rad(d), 4, 'Z')
    out = {"Root": M @ R("Root"), "Body": MB @ R("Body")}
    out["Head"] = MB @ R("Head") @ X(p.head[0]) @ Z(p.head[1]) @ Y(p.head[2])
    g = MB @ R("Gaster1") @ Z(p.gaster_yaw) @ X(p.gaster[0])
    out["Gaster1"] = g
    g = g @ rel("Gaster1", "Gaster2") @ X(p.gaster[1]) @ Z(p.gaster_yaw * 0.5)
    out["Gaster2"] = g
    out["Gaster3"] = g @ rel("Gaster2", "Gaster3") @ X(p.gaster[2])
    for s in (1, -1):
        sfx = 'L' if s > 0 else 'R'
        for w in ("Forewing", "Hindwing"):
            out[w + sfx] = MB @ R(w + sfx) @ X(p.stroke) @ Z(s * p.sweep) @ Y(s * p.twist)
        sc = out["Head"] @ rel("Head", f"Antenna{sfx}_Scape") @ X(p.antenna[0]) @ Z(s * p.antenna[2])
        out[f"Antenna{sfx}_Scape"] = sc
        out[f"Antenna{sfx}_Flagellum"] = sc @ rel(f"Antenna{sfx}_Scape", f"Antenna{sfx}_Flagellum") @ X(p.antenna[1])
        out[f"Mandible{sfx}"] = out["Head"] @ rel("Head", f"Mandible{sfx}") @ Z(s * p.mandible)
        for pair in range(3):
            C, Ls, _, _, _ = WB.leg_spec(pair, s)
            yaw, ang = p.legs[(s, pair)]
            e_r = Vector((s * math.cos(rad(yaw)), -math.sin(rad(yaw)), 0))
            fr = SB.leg_frames(C, Ls, e_r, [rad(a) for a in ang])
            for j, seg in enumerate(WB.LEG_SEGS):
                out[WB.leg_name(pair, s, seg)] = MB @ bug_rig.frame_matrix(fr[j][0], fr[j][1])
    Minv = M.inverted()                               # the skeleton plays in place; Motion travels
    out = {k: Minv @ v for k, v in out.items()}
    out["Motion"] = M @ R("Motion")
    return out


# ----------------------------------------------------------------------------------------- clip tracks
def _blend(a, b, w):
    return (a[0] + (b[0] - a[0]) * w, tuple(x + (y - x) * w for x, y in zip(a[1], b[1])))


def keyed(f, T, loop=None, period=60):
    """period: frames per leg-sway cycle pair (a loop's length, so looping clips stay seamless)."""
    p = WaspPose()
    g = lambda k, d: track(T[k], f, loop) if k in T else d
    p.root = Vector(g('root', (0, 0, 0)))
    p.body = Vector(g('body', (0, 0, 0)))
    p.pitch, p.yaw, p.roll = g('pitch', 0.0), g('yaw', 0.0), g('roll', 0.0)
    p.head = list(np.atleast_1d(g('head', (0.0, 0.0, 0.0))))
    p.gaster = list(np.atleast_1d(g('gaster', (0.0, 0.0, 0.0))))
    p.gaster_yaw = g('gyaw', 0.0)
    p.antenna = list(np.atleast_1d(g('antenna', (0.0, 0.0, 0.0))))
    p.mandible = g('mandible', 0.0)
    buzz, amp, base = g('buzz', 1.0), g('wamp', 40.0), g('wbase', 5.0)
    beat = 1.0 if int(round(f)) % 2 == 0 else -1.0
    p.stroke = base + amp * beat * buzz
    p.sweep = g('sweep', 0.0)
    p.twist = -12.0 * beat * buzz
    wt, wg, wc = g('trail', 0.0), g('grab', 0.0), g('curl', 0.0)
    sway = g('sway', 1.0)
    for s, pair in PAIRS:
        leg = HANG[pair]
        leg = _blend(leg, TRAIL[pair], wt)
        leg = _blend(leg, GRAB[pair], wg)
        leg = _blend(leg, CURL[pair], wc)
        ph = 4 * math.pi * f / period + pair * 1.7 + (0 if s > 0 else 2.3)
        yaw, ang = leg
        ang = (ang[0], ang[1] + 4 * sway * math.sin(ph), ang[2] + 5 * sway * math.sin(ph + 0.8), ang[3] + 6 * sway * math.sin(ph + 1.5))
        p.legs[(s, pair)] = (yaw, ang)
    return p


def _clip_idle():
    N = 60
    def pose(f):
        w = 2 * math.pi * f / N
        T = {}
        p = keyed(f, T)
        p.body = Vector((0.03 * math.sin(w + 1.0), 0.02 * math.sin(w), 0.05 * math.sin(w)))
        p.pitch = 2.0 * math.sin(w + 0.5)
        p.roll = 1.5 * math.sin(w + 2.0)
        p.yaw = 2.5 * math.sin(w)
        p.gaster = [3.0 * math.sin(2 * w), 2.5 * math.sin(2 * w - 0.6), 2.0 * math.sin(2 * w - 1.2)]
        p.gaster_yaw = 3.0 * math.sin(w - 0.7)
        p.head = [2.0 * math.sin(2 * w), 5.0 * math.sin(w + 0.3), 0.0]
        p.antenna = [6.0 * math.sin(3 * w), 8.0 * math.sin(3 * w + 1.0), 4.0 * math.sin(w)]
        return p
    return N, pose, True


def _clip_fly():
    N = 30
    speed = 4.0
    def pose(f):
        w = 2 * math.pi * f / N
        p = keyed(f, {'trail': [(0, 1.0)], 'wamp': [(0, 46.0)], 'wbase': [(0, 8.0)], 'sweep': [(0, -4.0)],
                      'sway': [(0, 0.4)]}, period=N)
        p.root = Vector((0, -speed * f / N, 0))
        p.body = Vector((0, 0, -0.05 + 0.03 * math.sin(2 * w)))
        p.pitch = -16.0 + 1.5 * math.sin(2 * w)
        p.roll = 3.0 * math.sin(w)
        p.gaster = [10.0 + 2 * math.sin(2 * w - 0.5), 4.0, 2.0]
        p.antenna = [-12.0, 8.0, -6.0]
        p.head = [-4.0, 0.0, -2.0 * math.sin(w)]
        return p
    return N, pose, True


def _clip_threat():
    N = 48
    T = {
        'body': [(0, (0, 0, 0)), (8, (0, 0.10, 0.10)), (40, (0, 0.10, 0.10)), (48, (0, 0, 0))],
        'pitch': [(0, 0.0), (8, 10.0), (40, 10.0), (48, 0.0)],
        'gaster': [(0, (0, 0, 0)), (10, (-35, -40, -35)), (16, (-45, -45, -40)), (22, (-28, -35, -30)),
                   (28, (-45, -45, -40)), (34, (-28, -35, -30)), (40, (-40, -40, -35)), (48, (0, 0, 0))],
        'mandible': [(0, 0.0), (10, 28.0), (14, 0.0), (20, 30.0), (24, 0.0), (30, 30.0), (34, 0.0), (48, 0.0)],
        'antenna': [(0, (0, 0, 0)), (10, (-20, 15, 10)), (40, (-20, 15, 10)), (48, (0, 0, 0))],
        'head': [(0, (0, 0, 0)), (10, (-8, 0, 0)), (40, (-8, 0, 0)), (48, (0, 0, 0))],
        'wamp': [(0, 40.0), (8, 52.0), (40, 52.0), (48, 40.0)],
        'grab': [(0, 0.0), (10, 0.5), (40, 0.5), (48, 0.0)],
    }
    return N, lambda f: keyed(f, T), False


def _clip_sting():
    N = 39
    T = {
        'body': [(0, (0, 0, 0)), (12, (0, 0.25, 0.15)), (18, (0, -0.45, -0.10)), (22, (0, -0.40, -0.08)),
                 (30, (0, -0.10, 0.02)), (39, (0, 0, 0))],
        'pitch': [(0, 0.0), (12, 18.0), (18, -22.0), (24, -12.0), (39, 0.0)],
        'gaster': [(0, (0, 0, 0)), (12, (-30, -35, -30)), (18, (-45, -50, -45)), (24, (-35, -40, -35)), (39, (0, 0, 0))],
        'mandible': [(0, 0.0), (12, 30.0), (18, 5.0), (39, 0.0)],
        'grab': [(0, 0.0), (12, 0.4), (18, 1.0), (26, 0.6), (39, 0.0)],
        'antenna': [(0, (0, 0, 0)), (12, (-15, 10, 8)), (26, (-10, 5, 4)), (39, (0, 0, 0))],
        'wamp': [(0, 40.0), (12, 48.0), (18, 50.0), (39, 40.0)],
    }
    return N, lambda f: keyed(f, T), False


def _clip_dive():
    N = 54
    T = {
        'body': [(0, (0, 0, 0)), (14, (0, 0.20, 0.45)), (27, (0, -0.90, -1.05)), (31, (0, -0.85, -1.00)),
                 (40, (0, -0.60, -0.30)), (54, (0, 0, 0))],
        'pitch': [(0, 0.0), (14, 20.0), (22, -40.0), (27, -32.0), (34, 12.0), (44, 6.0), (54, 0.0)],
        'gaster': [(0, (0, 0, 0)), (14, (-10, -10, -5)), (24, (-45, -50, -45)), (30, (-35, -40, -35)), (44, (0, 0, 0)),
                   (54, (0, 0, 0))],
        'grab': [(0, 0.0), (18, 0.3), (26, 1.0), (32, 0.6), (44, 0.0), (54, 0.0)],
        'trail': [(0, 0.0), (10, 0.6), (18, 0.2), (26, 0.0), (36, 0.4), (48, 0.0), (54, 0.0)],
        'mandible': [(0, 0.0), (22, 28.0), (27, 4.0), (40, 0.0), (54, 0.0)],
        'wamp': [(0, 40.0), (14, 50.0), (27, 36.0), (36, 52.0), (54, 40.0)],
        'antenna': [(0, (0, 0, 0)), (20, (-18, 10, -5)), (40, (-8, 5, 0)), (54, (0, 0, 0))],
    }
    return N, lambda f: keyed(f, T), False


def _clip_hit():
    N = 15
    T = {
        'body': [(0, (0, 0, 0)), (3, (0.05, 0.18, 0.06)), (8, (0.02, 0.10, -0.03)), (15, (0, 0, 0))],
        'roll': [(0, 0.0), (3, 18.0), (8, -6.0), (15, 0.0)],
        'pitch': [(0, 0.0), (3, 12.0), (9, -3.0), (15, 0.0)],
        'gaster': [(0, (0, 0, 0)), (3, (15, 10, 8)), (9, (-6, -4, -3)), (15, (0, 0, 0))],
        'wamp': [(0, 40.0), (2, 18.0), (6, 22.0), (10, 40.0), (15, 40.0)],
        'head': [(0, (0, 0, 0)), (3, (8, 6, 0)), (10, (0, 0, 0)), (15, (0, 0, 0))],
        'mandible': [(0, 0.0), (3, 25.0), (9, 0.0), (15, 0.0)],
    }
    return N, lambda f: keyed(f, T), False


DEAD_BODY = (0.15, 0.05, -1.5)      # lying on its side: thorax half-width above the ground


def _clip_death():
    N = 60
    fall = [(5, 0.0), (10, -0.12), (15, -0.45), (20, -0.95), (24, -1.5), (27, -1.42), (30, -1.5), (60, -1.5)]
    T = {
        'body': [(0, (0, 0, 0)), (3, (0.04, 0.12, 0.05))] + [(f, (0.15 * min(1, f / 30), 0.05, z)) for f, z in fall[1:]],
        'roll': [(0, 0.0), (3, 15.0), (12, 40.0), (22, 110.0), (27, 92.0), (32, 100.0), (60, 100.0)],
        'pitch': [(0, 0.0), (3, 10.0), (16, 25.0), (26, 8.0), (60, 6.0)],
        'yaw': [(0, 0.0), (20, 25.0), (60, 25.0)],
        'buzz': [(0, 1.0), (4, 1.0), (6, 0.0), (60, 0.0)],
        'wbase': [(0, 5.0), (6, -10.0), (60, -10.0)],
        'sweep': [(0, 0.0), (8, 40.0), (26, 70.0), (60, 70.0)],
        'gaster': [(0, (0, 0, 0)), (4, (12, 8, 5)), (24, (-25, -30, -25)), (44, (-30, -35, -30)), (47, (-20, -25, -20)),
                   (50, (-30, -35, -30)), (60, (-30, -35, -30))],
        'curl': [(0, 0.0), (8, 0.2), (30, 0.85), (40, 1.0), (45, 0.8), (48, 1.0), (51, 0.9), (60, 1.0)],
        'sway': [(0, 1.0), (30, 0.2), (60, 0.0)],
        'mandible': [(0, 0.0), (4, 30.0), (30, 12.0), (60, 12.0)],
        'antenna': [(0, (0, 0, 0)), (20, (15, 30, 10)), (60, (20, 35, 12))],
    }
    return N, lambda f: keyed(f, T), False


def _clip_getup():
    N = 45
    T = {
        'body': [(0, DEAD_BODY), (6, DEAD_BODY), (14, (0.12, 0.05, -1.30)), (22, (0.05, 0.02, -0.90)),
                 (34, (0, 0, -0.15)), (45, (0, 0, 0))],
        'roll': [(0, 100.0), (6, 100.0), (18, 30.0), (24, -6.0), (30, 2.0), (45, 0.0)],
        'pitch': [(0, 6.0), (12, 10.0), (24, 5.0), (45, 0.0)],
        'yaw': [(0, 25.0), (30, 5.0), (45, 0.0)],
        'buzz': [(0, 0.0), (4, 0.0), (6, 1.0), (45, 1.0)],
        'wamp': [(0, 10.0), (6, 20.0), (14, 50.0), (34, 45.0), (45, 40.0)],
        'wbase': [(0, -10.0), (8, 5.0), (45, 5.0)],
        'sweep': [(0, 70.0), (6, 60.0), (14, 5.0), (45, 0.0)],
        'gaster': [(0, (-30, -35, -30)), (16, (-10, -10, -8)), (30, (5, 3, 2)), (45, (0, 0, 0))],
        'curl': [(0, 1.0), (6, 1.0), (24, 0.1), (32, 0.0), (45, 0.0)],
        'sway': [(0, 0.0), (20, 0.3), (45, 1.0)],
        'mandible': [(0, 12.0), (20, 0.0), (45, 0.0)],
        'antenna': [(0, (20, 35, 12)), (20, (0, 10, 0)), (45, (0, 0, 0))],
    }
    return N, lambda f: keyed(f, T), False


CLIPS = {"Idle": _clip_idle, "Fly": _clip_fly, "Threat": _clip_threat, "Sting": _clip_sting, "Dive": _clip_dive,
         "Hit": _clip_hit, "Death": _clip_death, "GetUp": _clip_getup}


# ----------------------------------------------------------------------------------------- build / use
def rig():
    return bpy.data.objects[RIG]


def build_clip(name, rig_ob=None):
    rig_ob = rig_ob or rig()
    N, fn, loop = CLIPS[name]()
    an = action_name(name)
    act = bpy.data.actions.get(an)
    if act is not None:
        bpy.data.actions.remove(act)
    act = bpy.data.actions.new(an)
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
    for fc in act.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = 'LINEAR'
    act.frame_range = (0, N)
    return act


def build_clips(names=None):
    _REST.clear()
    return {n: build_clip(n) for n in (names or CLIPS)}


def use(name, rig_ob=None):
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
    rig_ob = rig_ob or rig()
    if rig_ob.animation_data:
        rig_ob.animation_data.action = None
    bug_rig.apply_pose(rig_ob, pose_matrices(p), keys=False)
    bpy.context.view_layer.update()
