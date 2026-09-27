"""Texture of the giant centipede (T_Centipede, 1024), painted per texel from the data bakes (spider_paint.bake_data).

Scolopendra-like warning colours that read from the colony camera: glossy blue-black trunk plates with a pale rim at
the back of each, a paler ochre belly, red-orange head, last segments and terminal legs, yellow legs with dark claws,
dark-red venom claws. Alpha = smoothness.
"""
import numpy as np
from bug_common import smoothstep, fbm, vnoise, hexc
import spider_paint as SP
import centipede_body as CB

P = CB.PART
UV_SCALE = {P['head']: 1.6, P['eye']: 1.5, P['forcipule']: 1.4, P['tail']: 1.2, P['antenna']: 0.7,
            P['femur']: 0.8, P['tibia']: 0.8, P['claw']: 0.6, P['tail_femur']: 1.0, P['tail_tibia']: 1.0,
            **{P['seg'] + i: 1.2 for i in range(1, CB.N_SEG + 1)}}

PAL = {
    'black': hexc('#121720'), 'blue': hexc('#1d2a3d'), 'rim': hexc('#3b4a5e'), 'belly': hexc('#8a6d3c'),
    'red': hexc('#b8381c'), 'red_dk': hexc('#6e1d10'), 'orange': hexc('#d9621e'), 'yellow': hexc('#e3aa2a'),
    'yellow_dk': hexc('#b0741a'), 'claw': hexc('#2a1810'), 'eye': hexc('#0d0b0b'),
}


def _mix(a, b, t):
    t = np.clip(np.asarray(t, float), 0, 1)[..., None]
    return a * (1 - t) + np.asarray(b) * t


def paint(D):
    Pp, N, part, t, ao = D['P'], D['N'], D['part'], D['t'], D['ao']
    H, W = part.shape
    x, y = Pp[..., 0], Pp[..., 1]
    ax = np.abs(x)
    n1 = fbm(Pp * 8.0, 3, seed=81)
    speck = vnoise(Pp * 160.0, seed=82)
    top = smoothstep(-0.1, 0.4, N[..., 2])
    col = np.tile(PAL['black'], (H, W, 1)).astype(float)
    smooth = np.full((H, W), 0.65)

    # trunk plates: blue-black, a pale rim at the back edge, a faint midline; ochre belly; the last plates go red
    seg_idx = part - P['seg']
    trunk = (seg_idx >= 1) & (seg_idx <= CB.N_SEG)
    c = _mix(np.tile(PAL['black'], (H, W, 1)), PAL['blue'], 0.35 + 0.35 * n1)
    c = _mix(c, PAL['rim'], smoothstep(0.16, 0.05, t) * top)                        # back edge rim
    c = _mix(c, PAL['black'] * 0.7, smoothstep(0.02, 0.008, ax) * top * 0.6)       # midline groove
    c = _mix(c, PAL['rim'] * 0.8, smoothstep(0.04, 0.02, np.abs(ax - 0.08)) * top * 0.35)   # two faint keels
    c = _mix(c, PAL['belly'], smoothstep(0.0, -0.45, N[..., 2]))
    redness = np.clip((seg_idx - (CB.N_SEG - 2)) / 2.0, 0, 1)                      # last two plates
    c = _mix(c, _mix(np.tile(PAL['red'], (H, W, 1)), PAL['red_dk'], 0.3 + 0.3 * n1), redness * top)
    col = np.where(trunk[..., None], c, col)
    smooth = np.where(trunk, 0.72, smooth)

    # head and tail: red-orange, darker at the front of the head
    hd = part == P['head']
    tl = part == P['tail']
    c = _mix(np.tile(PAL['red'], (H, W, 1)), PAL['orange'], 0.35 + 0.3 * n1)
    c = _mix(c, PAL['red_dk'], smoothstep(0.7, 1.0, t) * hd)
    c = _mix(c, PAL['belly'] * 0.8, smoothstep(0.0, -0.45, N[..., 2]))
    col = np.where((hd | tl)[..., None], c, col)
    smooth = np.where(hd | tl, 0.68, smooth)
    ey = part == P['eye']
    col = np.where(ey[..., None], np.tile(PAL['eye'], (H, W, 1)), col)
    smooth = np.where(ey, 0.92, smooth)

    # legs: yellow, darker toward the tip; claws dark
    lg = (part == P['femur']) | (part == P['tibia'])
    c = _mix(np.tile(PAL['yellow'], (H, W, 1)), PAL['yellow_dk'], 0.2 + 0.3 * n1 + 0.4 * (part == P['tibia']) * t)
    col = np.where(lg[..., None], c, col)
    smooth = np.where(lg, 0.5, smooth)
    cl = part == P['claw']
    col = np.where(cl[..., None], np.tile(PAL['claw'], (H, W, 1)), col)
    tlg = (part == P['tail_femur']) | (part == P['tail_tibia'])
    c = _mix(np.tile(PAL['red'], (H, W, 1)), PAL['claw'], smoothstep(0.6, 1.0, t) * (part == P['tail_tibia']))
    col = np.where(tlg[..., None], c, col)
    an = part == P['antenna']
    col = np.where(an[..., None], _mix(np.tile(PAL['orange'], (H, W, 1)), PAL['yellow'], t), col)
    fc = part == P['forcipule']
    col = np.where(fc[..., None], _mix(np.tile(PAL['red_dk'], (H, W, 1)), PAL['claw'], smoothstep(0.5, 0.95, t)), col)
    smooth = np.where(fc | cl, 0.8, smooth)

    col = col * (0.94 + 0.08 * speck[..., None])
    light = 0.74 + 0.36 * (N[..., 2] * 0.5 + 0.5)
    aot = 0.42 + 0.58 * np.clip(ao, 0, 1)
    shaded = col * (light * aot)[..., None] + ((1 - aot) * 0.08)[..., None] * np.array([0.25, 0.2, 0.35])
    return np.clip(shaded, 0, 1), np.clip(smooth, 0, 1)


def build_texture(body, size=1024):
    SP.unwrap(body, scales=UV_SCALE)
    D = SP.bake_data(body, size=size)
    col, smooth = paint(D)
    return SP.write_texture(D, col, smooth, "T_Centipede", body, "M_Centipede"), float(D['valid'].mean())
