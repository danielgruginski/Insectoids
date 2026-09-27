"""Giant centipede clips, keyed straight onto CentipedeRig. Actions are named Centipede_<Clip>. 60 fps (the legs
cycle fast).

The body is a path: a direction field over u (arc length, growing toward the front; yaw psi turns left, pitch theta
rears up) is integrated from an anchor, and every chain element sits at u_head - S[k]. Bending, rearing, curling or
diving into the ground never stretches the body. Legs: two-bone IK in each segment's Q space toward feet planted in the
world (a metachronal wave: legs step one after another down each side, left and right half a cycle apart), blended to
FK poses where a segment rears (flailing), goes underground (tucked back) or dies (curled). As for the other insectoids,
the skeleton plays in place and only the Motion bone travels (root motion).

Clips:
  Idle     3.0 s loop   slow S-sway, head searching, a ripple of leg steps down the body, antennae and claws
  Walk     0.9 s loop   root motion 1.5 m/s
  Run      0.6 s loop   root motion 4 m/s, stronger sway
  Threat   2.5 s        the front third rears like a cobra, legs flailing, claws snapping, tail legs up
  Bite     1.2 s        rears, lunges 0.45 m, strikes with the forcipules (event 'Bite' 0.55 s)
  Burrow   2.5 s        dives into the ground 0.55 m ahead and disappears (event 'Burrow' when the head goes under);
                        root motion carries the GameObject to the hole
  Emerge   2.5 s        comes up out of the ground under the GameObject and crawls out until its tail leaves the
                        hole (event 'Emerge' as the head breaks the surface); root motion follows the body
  Hit      0.5 s        a jolt runs down the body
  Death    2.0 s        rolls onto its back and curls up, legs curling (event 'Dead' 1.85 s)
  GetUp    1.5 s        uncurls, rolls back over and stands
"""
import bpy, math
import numpy as np
from mathutils import Vector, Matrix
import centipede_body as CB
import spider_body as SB
import bug_rig
from spider_anim import track, rad, ease

FPS = 60
RIG = "CentipedeRig"
EVENTS = {"Bite": [("Bite", 0.55)], "Death": [("Dead", 1.85)]}      # Burrow / Emerge are measured when built
SIDES = (1, -1)
LEGGED = range(1, CB.N_SEG + 1)

TUCK = (-72, (-4, -12))           # legs folded back along the body
FLAIL = (18, (35, -35))
CURL = (8, (-35, -150))


def action_name(clip):
    return "Centipede_" + clip


def smooth(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------------------- the path
def path_points(psi, theta, lo, hi, u_anchor, p_anchor, du=0.004):
    """The curve of a direction field on [lo, hi], through p_anchor at u_anchor: (grid, points)."""
    lo, hi = min(lo, u_anchor) - 0.05, max(hi, u_anchor) + 0.05
    grid = np.arange(lo, hi + du, du)
    ps = np.array([psi(u) for u in grid])
    th = np.array([theta(u) for u in grid])
    d = np.stack([np.sin(ps) * np.cos(th), -np.cos(ps) * np.cos(th), np.sin(th)], 1)
    acc = np.vstack([np.zeros(3), np.cumsum(0.5 * (d[1:] + d[:-1]) * du, axis=0)])
    a = np.interp(u_anchor, grid, np.arange(len(grid)))
    base = np.array([np.interp(a, np.arange(len(grid)), acc[:, j]) for j in range(3)])
    return grid, acc - base + np.array(p_anchor)


def ground_crossing(psi, theta, u_anchor, p_anchor, lo, hi, z=0.05):
    """World y where the curve crosses height z (where the head goes under / comes up; the Burrow and Emerge events
    use the same height)."""
    grid, P = path_points(psi, theta, lo, hi, u_anchor, p_anchor)
    below = P[:, 2] < z
    i = int(np.nonzero(below[1:] != below[:-1])[0][0])
    t = (z - P[i, 2]) / (P[i + 1, 2] - P[i, 2])
    return float(P[i, 1] + t * (P[i + 1, 1] - P[i, 1]))


def mid_y(els):
    """World y of the body's middle (arc MID_ARC behind the head), interpolated between elements."""
    k = int(np.searchsorted(CB.S, MID_ARC)) - 1
    t = (MID_ARC - CB.S[k]) / (CB.S[k + 1] - CB.S[k])
    return els[k][0].y * (1 - t) + els[k + 1][0].y * t


def chain(u_head, u_anchor, p_anchor, psi, theta, roll=None, du=0.004):
    """Chain element frames (world): list of (pos, frame, Q). psi(u), theta(u) give the direction field; the curve
    passes through p_anchor at u_anchor. roll(k) in radians rolls element k about its axis."""
    us = u_head - CB.S
    grid, P = path_points(psi, theta, us.min(), us.max(), u_anchor, p_anchor, du)
    out = []
    for k, u in enumerate(us):
        pos = Vector([np.interp(u, grid, P[:, j]) for j in range(3)])
        p_, t_ = psi(u), theta(u)
        fwd = Vector((math.sin(p_) * math.cos(t_), -math.cos(p_) * math.cos(t_), math.sin(t_)))
        up = Vector((-math.sin(p_) * math.sin(t_), math.cos(p_) * math.sin(t_), math.cos(t_)))
        r = roll(k) if roll is not None else 0.0
        if r:
            up = up * math.cos(r) + fwd.cross(up) * math.sin(r)
        pos_, fr = CB.element_frame(pos, fwd, up)
        out.append((pos_, fr, CB.q_matrix(pos_, fr)))
    return out


REST_ELS = None


def rest_feet():
    """World foot positions of the bind pose, per (segment, side)."""
    global REST_ELS
    if REST_ELS is None:
        REST_ELS = CB.rest_elements()
    out = {}
    for i in LEGGED:
        p, fr = REST_ELS[i]
        Q = CB.q_matrix(p, fr)
        for s in SIDES:
            out[(i, s)] = Q @ CB.rest_foot_q(i, s)
    return out


# ----------------------------------------------------------------------------------------- a pose
class CPose:
    def __init__(self):
        self.root = Vector()
        self.els = None                   # [(pos, frame, Q)] world
        self.feet = {}                    # (i, side) -> world foot target
        self.fk = {}                      # (i, side) -> (weight, (yaw, (a1, a2)))
        self.tail = (0.0, 0.0, 0.0)       # tail legs: yaw offset, femur, tibia offsets (degrees)
        self.antenna = (0.0, 0.0, 0.0)    # sweep up, bend, spread (degrees)
        self.forcipule = 0.0              # opening (degrees)


def _blend_fk(a, b, w):
    return (a[0] + (b[0] - a[0]) * w, tuple(x + (y - x) * w for x, y in zip(a[1], b[1])))


def pose_matrices(p):
    B = rest()
    R = lambda n: bug_rig.frame_matrix(B[n][0], B[n][1])
    rel = lambda a, b: R(a).inverted() @ R(b)
    M = Matrix.Translation(p.root)
    out = {"Root": M @ R("Root")}
    for name, (pos, fr, Q) in zip(CB.ELEMENTS, p.els):       # the chain is already in world space (it includes
        out[name] = bug_rig.frame_matrix(pos, fr)             # the travel along the path): no root on top of it
    for i in LEGGED:
        pos, fr, Q = p.els[i]
        L1, L2, _ = CB.leg_dims(i)
        for s in SIDES:
            hip = CB.hip_q(s)
            tgt = Q.inverted() @ p.feet[(i, s)]
            e_r, ang = CB.solve_leg2(hip, L1, L2, tgt, s)
            w, fk = p.fk.get((i, s), (0.0, None))
            if fk is not None and w > 0:
                yaw_ik = math.atan2(-e_r.y, s * e_r.x)
                yaw = yaw_ik * (1 - w) + rad(fk[0]) * w
                ang = [a * (1 - w) + rad(b) * w for a, b in zip(ang, fk[1])]
                e_r = Vector((s * math.cos(yaw), -math.sin(yaw), 0))
            frs = SB.leg_frames(hip, (L1, L2), e_r, ang)
            for j, seg in enumerate(("Femur", "Tibia")):
                out[CB.leg_name(i, s, seg)] = Q @ bug_rig.frame_matrix(frs[j][0], frs[j][1])
    pos, fr, Q = p.els[-1]
    for s in SIDES:
        sfx = 'L' if s > 0 else 'R'
        yaw, (a1, a2) = CB.TAIL_LEG_POSE
        yaw, a1, a2 = yaw + p.tail[0], a1 + p.tail[1], a2 + p.tail[2]
        e_r = Vector((s * math.cos(rad(yaw)), -math.sin(rad(yaw)), 0))
        frs = SB.leg_frames(Vector((s * 0.08, 0.05, 0.0)), CB.TAIL_LEG, e_r, [rad(a1), rad(a2)])
        for j, seg in enumerate(("Femur", "Tibia")):
            out[f"TailLeg{sfx}_{seg}"] = Q @ bug_rig.frame_matrix(frs[j][0], frs[j][1])
    X = lambda d: Matrix.Rotation(rad(d), 4, 'X')
    Z = lambda d: Matrix.Rotation(rad(d), 4, 'Z')
    head = out["Head"]
    for s in SIDES:
        sfx = 'L' if s > 0 else 'R'
        a1 = head @ rel("Head", f"Antenna{sfx}_1") @ X(p.antenna[0]) @ Z(s * p.antenna[2])
        out[f"Antenna{sfx}_1"] = a1
        out[f"Antenna{sfx}_2"] = a1 @ rel(f"Antenna{sfx}_1", f"Antenna{sfx}_2") @ X(p.antenna[1])
        out[f"Forcipule{sfx}"] = head @ rel("Head", f"Forcipule{sfx}") @ Z(-s * p.forcipule)
    Minv = M.inverted()                       # the skeleton plays in place; Motion travels
    out = {k: Minv @ v for k, v in out.items()}
    out["Motion"] = M @ R("Motion")
    return out


_REST = {}


def rest():
    if not _REST:
        _REST['B'] = CB.rest_bones()
    return _REST['B']


# ----------------------------------------------------------------------------------------- gait
def gait_feet(p, t, v, T_leg, duty=0.6, lift=0.10, lag=0.19):
    """Feet for a metachronal wave: leg i steps `lag` of a cycle after leg i+1 (the wave runs forward), the right side
    half a cycle after the left. Feet stay where they were put down while the body moves on at v."""
    exc = v * T_leg * duty
    for i in LEGGED:
        pos, fr, Q = p.els[i]
        fwd = Vector((fr.col[1].x, fr.col[1].y, 0))
        fwd = fwd.normalized() if fwd.length > 1e-6 else Vector((0, -1, 0))
        for s in SIDES:
            F0 = Q @ CB.rest_foot_q(i, s)
            ph = (t / T_leg + lag * (CB.N_SEG - i) + (0.0 if s > 0 else 0.5)) % 1.0
            if ph < duty:
                u, z = 0.5 - ph / duty, 0.0
            else:
                q = (ph - duty) / (1 - duty)
                u, z = -0.5 + ease(q), lift * math.sin(math.pi * q)
            f = F0 + fwd * exc * u
            f.z = z
            p.feet[(i, s)] = f


def tuck_underground(p):
    """Legs of elements near or below the ground fold back along the body."""
    for i in LEGGED:
        z = p.els[i][0].z
        w = smooth(0.12, 0.02, z)
        if w > 0:
            for s in SIDES:
                p.fk[(i, s)] = (w, TUCK)


# ----------------------------------------------------------------------------------------- clips
HEAD_REST = Vector((0, CB.HEAD_Y, CB.Z0))
TAIL_ARC = float(CB.S[-1])
MID_ARC = TAIL_ARC / 2


def _clip_idle():
    N = 180
    feet0 = rest_feet()
    def pose(f):
        t = f / FPS
        w = 2 * math.pi * f / N
        p = CPose()
        psi = lambda u: (0.07 * math.sin(2 * math.pi * u / 2.2 + w) +
                         0.30 * math.sin(2 * w + 0.5) * smooth(-0.6, 0.0, u) + 0.12 * math.sin(w) * smooth(-0.4, 0.0, u))
        theta = lambda u: 0.14 * (0.5 + 0.5 * math.sin(3 * w)) * smooth(-0.35, 0.0, u)
        p.els = chain(0.0, -MID_ARC, (0, 0, CB.Z0), psi, theta)
        wave = (f / N) * 1.5 - 0.25                          # one ripple of steps runs down the body per loop
        for i in LEGGED:
            for s in SIDES:
                x = (i - 1) / (CB.N_SEG - 1) - wave + (0.04 if s < 0 else 0)
                bump = math.exp(-(x / 0.06) ** 2)
                pos, fr, Q = p.els[i]
                f0 = Q @ CB.rest_foot_q(i, s)
                ft = feet0[(i, s)] * 0.35 + Vector((f0.x, f0.y, 0)) * 0.65     # feet follow the sway a little
                p.feet[(i, s)] = Vector((ft.x, ft.y, 0.07 * bump))
        p.antenna = (10 * math.sin(3 * w), 14 * math.sin(3 * w + 1.2), 8 * math.sin(2 * w))
        p.forcipule = 8 * max(0.0, math.sin(4 * w)) ** 4
        p.tail = (6 * math.sin(w + 1.0), 6 * math.sin(2 * w), 4 * math.sin(2 * w + 1))
        return p
    return N, pose, True


def _walk(v, T_leg, cycles, amp, lift):
    N = int(round(T_leg * cycles * FPS))
    T = N / FPS
    lam = v * T                                              # one sway wavelength per clip, so it loops
    k = 2 * math.pi / lam
    us = np.linspace(0.0, lam, 2001)                         # on the swaying path the head gains a little less
    fwd = float(np.mean(np.cos(np.arctan(amp * k * np.cos(k * us)))))    # ground than it travels: the root
    v_root = v * fwd                                         # matches the ground gained, so the loop doesn't pop
    def pose(f):
        t = f / FPS
        p = CPose()
        p.root = Vector((0, -v_root * t, 0))
        psi = lambda u: math.atan(amp * k * math.cos(k * u))
        theta = lambda u: 0.0
        p.els = chain(v * t, 0.0, HEAD_REST, psi, theta)
        gait_feet(p, t, v, T_leg, lift=lift)
        p.antenna = (-8, 6 * math.sin(4 * math.pi * t / T), 6 * math.sin(2 * math.pi * t / T))
        p.tail = (-6, 4 * math.sin(2 * math.pi * t / T), 0)
        return p
    return N, pose, True


def _clip_walk():
    return _walk(1.5, 0.3, 3, 0.035, 0.10)


def _clip_run():
    return _walk(4.0, 0.2, 3, 0.09, 0.08)


def _rear(theta_r, u_r=-1.0, yaw=0.0, bend=0.8, tip=0.45):
    """Direction field for the front rearing up from about u_r behind the head: a long, soft bend, and the top tipping
    forward again (tip = fraction of the rear angle) so the head looks down at its target like a cobra's."""
    psi = lambda u: yaw * smooth(u_r, 0.0, u)
    theta = lambda u: theta_r * (smooth(u_r - 0.6 * bend, u_r + 0.4 * bend, u) - tip * smooth(-0.5, 0.0, u))
    return psi, theta


def _clip_threat():
    N = 150
    feet0 = rest_feet()
    def pose(f):
        t = f / FPS
        r = track([(0, 0.0), (25, 72.0), (60, 66.0), (95, 74.0), (125, 70.0), (150, 0.0)], f)
        sway = track([(0, 0.0), (30, 0.0), (60, 12.0), (95, -12.0), (125, 6.0), (150, 0.0)], f)
        p = CPose()
        psi, theta = _rear(rad(r), yaw=rad(sway))
        p.els = chain(0.0, -TAIL_ARC, HEAD_REST + Vector((0, TAIL_ARC, 0)), psi, theta)
        for i in LEGGED:
            h = p.els[i][0].z
            w = smooth(0.24, 0.45, h)
            for s in SIDES:
                p.feet[(i, s)] = feet0[(i, s)].copy()
                fl = (FLAIL[0] + 15 * math.sin(t * 9 + i + (0 if s > 0 else 1.6)),
                      (FLAIL[1][0] + 12 * math.sin(t * 11 + i * 0.7), FLAIL[1][1] + 15 * math.sin(t * 13 + i)))
                if w > 0:
                    p.fk[(i, s)] = (w, fl)
        p.forcipule = track([(0, 0.0), (20, 30.0), (40, 35.0), (46, 0.0), (60, 32.0), (80, 34.0), (86, 0.0),
                             (100, 30.0), (130, 30.0), (150, 0.0)], f)
        p.antenna = (track([(0, 0.0), (25, 25.0), (125, 25.0), (150, 0.0)], f), 10 * math.sin(t * 7), 10.0)
        p.tail = (track([(0, 0.0), (30, 25.0), (125, 25.0), (150, 0.0)], f), track([(0, 0.0), (30, 35.0), (125, 35.0), (150, 0.0)], f), 0)
        return p
    return N, pose, False


def _clip_bite():
    N = 72
    feet0 = rest_feet()
    def pose(f):
        r = track([(0, 0.0), (22, 38.0), (33, -12.0), (44, -8.0), (72, 0.0)], f)
        slide = track([(0, 0.0), (22, -0.08), (33, 0.45), (46, 0.40), (72, 0.0)], f)
        p = CPose()
        psi, theta = _rear(rad(r), u_r=-0.75, bend=0.6, tip=0.3)
        p.els = chain(0.0, -TAIL_ARC, HEAD_REST + Vector((0, TAIL_ARC - slide, 0)), psi, theta)
        shuffle = track([(0, 0.0), (26, 0.0), (33, 1.0), (40, 1.0), (60, 0.2), (72, 0.0)], f)
        for i in LEGGED:
            for s in SIDES:
                ph = (f / 8.0 + i * 0.35 + (0 if s > 0 else 0.5)) % 1.0
                lift = 0.07 * math.sin(math.pi * ph) * min(1.0, abs(slide) * 3) if ph < 0.5 else 0.0
                ft = feet0[(i, s)] + Vector((0, -slide * 0.85 * shuffle, 0))
                p.feet[(i, s)] = Vector((ft.x, ft.y, lift))
            h = p.els[i][0].z
            w = smooth(0.24, 0.40, h)
            if w > 0:
                for s in SIDES:
                    p.fk[(i, s)] = (w, (35, (25, -20)))
        p.forcipule = track([(0, 0.0), (22, 40.0), (31, 42.0), (33, -4.0), (46, 0.0), (72, 0.0)], f)
        p.antenna = (track([(0, 0.0), (22, 20.0), (33, -10.0), (72, 0.0)], f), 0.0, 8.0)
        p.tail = (0, track([(0, 0.0), (22, 15.0), (72, 0.0)], f), 0)
        return p
    return N, pose, False


ENTRY = 0.55                    # the burrow hole: this far ahead of the rest head, along the body line


def _burrow_u(f, N):
    return track([(0, 0.0), (20, 0.25), (N - 20, TAIL_ARC + 1.4), (N, TAIL_ARC + 1.7)], f)


def _clip_burrow():
    """Root motion: the GameObject follows the body's middle forward and stops over the hole, so it ends where the
    centipede went under (and Emerge, played there, comes back out of the same hole)."""
    N = 150
    psi = lambda u: 0.0
    theta = lambda u: -rad(62) * smooth(ENTRY - 0.15, ENTRY + 0.30, u)
    hole_y = ground_crossing(psi, theta, 0.0, HEAD_REST, -0.5, 3.0)
    def pose(f):
        u_h = _burrow_u(f, N)
        v = (_burrow_u(f + 1, N) - _burrow_u(f - 1, N)) * FPS / 2
        p = CPose()
        p.els = chain(u_h, 0.0, HEAD_REST, psi, theta)
        p.root = Vector((0, max(hole_y, mid_y(p.els)), 0))
        gait_feet(p, f / FPS, max(v, 0.3), 0.28)
        tuck_underground(p)
        p.antenna = (track([(0, 0.0), (20, -20.0), (N, -30.0)], f), -10.0, -15.0)
        p.tail = (track([(0, 0.0), (N, 20.0)], f), 0, 0)
        return p
    return N, pose, False


def _emerge_u(f, N):
    """Head arc from the level start of the path (u = 0): from 1.3 m underground to a body length out."""
    return track([(0, -1.3), (15, -1.05), (N - 25, TAIL_ARC - 0.1), (N, TAIL_ARC)], f)


def _clip_emerge():
    """The head breaks the ground right under the GameObject; the GameObject follows the body's middle forward until
    the centipede stands with its tail at the hole (root motion)."""
    N = 150
    psi = lambda u: 0.0
    theta = lambda u: rad(62) * (1 - smooth(-0.45, 0.02, u))          # steep underground, level from u = 0 on
    shift = -ground_crossing(psi, theta, 0.0, (0, 0, CB.Z0), -3.5, 0.5)
    anchor = (0, shift, CB.Z0)                                       # so the head comes up at y = 0
    root_end = shift - MID_ARC                                       # the middle, standing, tail at the hole
    def pose(f):
        u_h = _emerge_u(f, N)
        v = (_emerge_u(f + 1, N) - _emerge_u(f - 1, N)) * FPS / 2
        p = CPose()
        p.els = chain(u_h, 0.0, anchor, psi, theta)
        p.root = Vector((0, min(0.0, max(root_end, mid_y(p.els))), 0))
        gait_feet(p, f / FPS, max(v, 0.3), 0.28)
        tuck_underground(p)
        p.antenna = (track([(0, 20.0), (40, 10.0), (N, 0.0)], f), 0.0, 10.0)
        p.forcipule = track([(0, 20.0), (60, 0.0), (N, 0.0)], f)
        return p
    return N, pose, False


def _clip_hit():
    N = 30
    feet0 = rest_feet()
    def pose(f):
        pulse = track([(0, 0.2), (30, -TAIL_ARC - 0.4)], f)          # a kink running from head to tail
        amp = track([(0, 0.0), (3, 0.45), (18, 0.3), (30, 0.0)], f)
        p = CPose()
        psi = lambda u: amp * math.exp(-((u - pulse) / 0.35) ** 2)
        theta = lambda u: rad(track([(0, 0.0), (4, 14.0), (14, 0.0), (30, 0.0)], f)) * smooth(-0.5, 0.0, u)
        p.els = chain(0.0, -MID_ARC, (0, 0, CB.Z0), psi, theta)
        for i in LEGGED:
            for s in SIDES:
                x = (i - 1) / (CB.N_SEG - 1) * (TAIL_ARC + 0.6) - (0.2 - pulse)
                p.feet[(i, s)] = feet0[(i, s)] + Vector((0, 0, 0.08 * math.exp(-(x / 0.35) ** 2)))
        p.forcipule = track([(0, 0.0), (3, 35.0), (15, 0.0), (30, 0.0)], f)
        p.antenna = (track([(0, 0.0), (3, 25.0), (20, 0.0), (30, 0.0)], f), 0.0, 15.0)
        p.tail = (0, track([(0, 0.0), (6, 30.0), (30, 0.0)], f), 0)
        return p
    return N, pose, False


DEAD_Z = CB.DORSAL + 0.012        # lying on its back: the back plates on the ground


def _clip_death():
    N = 120
    feet0 = rest_feet()
    def pose(f):
        roll_t = track([(0, 0.0), (10, 0.0), (55, 1.0), (120, 1.0)], f)
        curl = track([(0, 0.0), (8, 0.3), (50, 1.4), (80, 2.1), (120, 2.2)], f)          # rad per metre
        z = CB.Z0 + (DEAD_Z - CB.Z0) * roll_t + 0.08 * math.sin(math.pi * min(1.0, f / 30.0)) * (f < 30)
        p = CPose()
        psi = lambda u: curl * (u + MID_ARC) + 0.25 * math.sin(f * 0.9) * (f < 12) * smooth(-0.6, 0.0, u)
        theta = lambda u: 0.0
        roll = lambda k: math.pi * min(1.0, max(0.0, roll_t * 1.6 - 0.6 * k / len(CB.S)))
        p.els = chain(0.0, -MID_ARC, (0, 0, z), psi, theta, roll)
        wc = track([(0, 0.0), (12, 0.3), (60, 1.0), (120, 1.0)], f)
        for i in LEGGED:
            for s in SIDES:
                p.feet[(i, s)] = feet0[(i, s)].copy()
                tw = 14 * math.sin(f * 0.8 + i * 1.3 + (0 if s > 0 else 2)) * (1 - smooth(70, 110, f))
                p.fk[(i, s)] = (wc, (CURL[0], (CURL[1][0] + tw, CURL[1][1] + tw)))
        p.forcipule = track([(0, 0.0), (6, 40.0), (60, 20.0), (120, 18.0)], f)
        p.antenna = (track([(0, 0.0), (40, -30.0), (120, -35.0)], f), track([(0, 0.0), (120, -40.0)], f), 20.0)
        p.tail = (track([(0, 0.0), (60, 40.0), (120, 45.0)], f), track([(0, 0.0), (60, -40.0), (120, -45.0)], f), -30)
        return p
    return N, pose, False


def _clip_getup():
    N = 90
    feet0 = rest_feet()
    def pose(f):
        roll_t = track([(0, 1.0), (10, 1.0), (55, 0.0), (90, 0.0)], f)
        curl = track([(0, 2.2), (35, 0.9), (70, 0.0), (90, 0.0)], f)
        z = CB.Z0 + (DEAD_Z - CB.Z0) * roll_t
        p = CPose()
        psi = lambda u: curl * (u + MID_ARC)
        theta = lambda u: 0.0
        roll = lambda k: math.pi * min(1.0, max(0.0, roll_t * 1.6 - 0.6 * (1 - k / len(CB.S))))
        p.els = chain(0.0, -MID_ARC, (0, 0, z), psi, theta, roll)
        wc = track([(0, 1.0), (15, 1.0), (50, 0.4), (72, 0.0), (90, 0.0)], f)
        for i in LEGGED:
            for s in SIDES:
                p.feet[(i, s)] = feet0[(i, s)].copy()
                if wc > 0:
                    p.fk[(i, s)] = (wc, CURL)
        p.forcipule = track([(0, 18.0), (60, 0.0), (90, 0.0)], f)
        p.antenna = (track([(0, -35.0), (70, 0.0), (90, 0.0)], f), track([(0, -40.0), (70, 0.0), (90, 0.0)], f),
                     track([(0, 20.0), (90, 0.0)], f))
        p.tail = (track([(0, 45.0), (70, 0.0)], f), track([(0, -45.0), (70, 0.0)], f), track([(0, -30.0), (70, 0.0)], f))
        return p
    return N, pose, False


CLIPS = {"Idle": _clip_idle, "Walk": _clip_walk, "Run": _clip_run, "Threat": _clip_threat, "Bite": _clip_bite,
         "Burrow": _clip_burrow, "Emerge": _clip_emerge, "Hit": _clip_hit, "Death": _clip_death, "GetUp": _clip_getup}


# ----------------------------------------------------------------------------------------- build / use
def rig():
    return bpy.data.objects[RIG]


def _surface_time(N, fn, going_down):
    """Seconds at which the head crosses the ground (for the Burrow / Emerge events)."""
    prev = None
    for f in range(N + 1):
        z = fn(f).els[0][0].z
        if prev is not None and ((going_down and prev >= 0.05 > z) or (not going_down and prev < 0.05 <= z)):
            return f / FPS
        prev = z
    return None


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
    events = list(EVENTS.get(name, []))
    if name in ("Burrow", "Emerge"):
        t = _surface_time(N, fn, going_down=(name == "Burrow"))
        if t is not None:
            events.append((name, round(t, 3)))
    for ev, t in events:
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
    scn.render.fps = FPS
    scn.frame_start, scn.frame_end = 0, int(act["frames"])
    scn.frame_set(0)


def clear(rig_ob=None):
    rig_ob = rig_ob or rig()
    if rig_ob.animation_data:
        rig_ob.animation_data.action = None
    bug_rig.reset_pose(rig_ob)
