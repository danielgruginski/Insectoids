# Insectoids

Giant bugs for the colony sim, built procedurally in Blender: the **giant hunting spider** and its family (the
**spiderling**, the **broodmother** and **spider eggs**), the **giant wasp** and the **giant centipede**.
The spider is horse-sized,
rideable (saddle socket), Unity Generic rig, hand-painted texture, nine custom clips. The leg IK, gait generator and
rigid-segment construction are meant to carry over to the next bugs (ants, beetles, mantis...).

![The test scene in Unity: spiders spitting web, wasps stinging, goblins around them](docs/images/test_scene.png)

Blender file: `blender/insectoids.blend` (saved compressed), scenes **Spider**, **Spiderling**, **Broodmother**,
**SpiderEggs**, **Wasp** and **Centipede**. Everything in
it is rebuilt from `src/`.

## Rebuild

In Blender (Python console or the MCP):

```python
import sys; sys.path.insert(0, r"E:\Unity\Projects\GameArtGeneration\Insectoids\src")
import spider_build
spider_build.build_all()        # body -> rig -> UVs -> textures -> clips (~30 s)

import bug_export
bug_export.export_all()         # export/Spider.fbx, export/Anims/Spider@<clip>.fbx + spider_clips.json

import spider_anim
spider_anim.use("Walk")         # show a clip on the rig (sets the scene's frame range)
spider_anim.clear()             # back to the bind pose
```

| Script | Does |
|---|---|
| `bug_common.py` | lofted tubes that mark their own UV seams, domes (eyes), cones (spines, fangs), numpy value noise |
| `spider_body.py` | anatomy spec, planar leg IK, bind-pose bone table, the game mesh (rigid vertex groups per bone) |
| `bug_rig.py` | armature from the bone table, binding, pose math (armature-space matrices -> keyed matrix_basis) |
| `spider_paint.py` | seam-based unwrap, data bakes (position, normal, part, AO), per-texel painting, smoothness in alpha |
| `spider_anim.py` | SpiderPose -> bone matrices, key-pose tracks, the tetrapod gait, the nine clips |
| `bug_scene.py` | scene, cameras (incl. the 40 m colony camera), review renders and clip contact sheets |
| `spider_build.py` | `build_all()` |
| `bug_export.py` | FBX for Unity (goblin settings) and the clip metadata JSON (loop, root motion, events) |

## The spider

![Spider clip poses in Unity, a goblin for scale](docs/images/spider_lineup.png)
![Web spit](docs/images/spider_webspit.png)

- **Size:** ~1.65 m from fangs to spinnerets, abdomen top 0.88 m, carapace 0.72 m, leg span ~3.2 m. Goblins are ~1 m.
- **Build:** an exoskeleton, so every part is a rigid shell on one bone. Each leg is five lofted segments (coxa,
  femur, patella+tibia, metatarsus, tarsus) whose rounded ends sit inside the flared end of the segment before, like
  real joints. Only the pedicel (waist) blends between Body and Abdomen. No heat-map weights, no bleeding between legs.
- **Look:** dark mottled brown, pale bands at the knees and ankles, a pale median stripe and radiating striae on the
  carapace, rust-red chelicerae, glossy black eyes, a bone-white skull with chevrons on the abdomen. The banding and
  the skull are what read from the colony camera.

### Budget

| Part | Triangles |
|---|---|
| Legs (8 x 5 segments) | 2,960 |
| Leg spines (macrosetae) | 384 |
| Abdomen / carapace / pedicel | 440 / 352 / 48 |
| Chelicerae + fangs / palps | 336 / 312 |
| Eyes (8) / spinnerets | 148 / 32 |
| **Total** | **5,012** |

One material, one 1024² texture (`T_Spider`, plus `T_Spider_Pale` for a washed-out cave variant). Alpha =
smoothness (URP Lit, Smoothness Source = Albedo Alpha): eyes 0.95, fangs 0.8, carapace 0.34, hair ~0.2.

### Skeleton (58 bones, Unity Generic)

`Motion` (root motion only; nothing hangs from it) beside `Root` (ground, never moves in the clips) > `Body` (cephalothorax) > `Abdomen` (at the pedicel), `CheliceraL/R` > `FangL/R`,
`PalpL/R_Femur/Tibia/Tarsus`, and eight legs `Leg{L|R}{1-4}_{Coxa|Femur|Tibia|Metatarsus|Tarsus}` (leg 1 in front).
Leg bones: +Y along the segment, +X the hinge, +Z dorsal; a positive X rotation raises a segment on either side.

### Sockets (props modelled in socket space: origin = attach point)

| Socket | Parent | Axes | For |
|---|---|---|---|
| Socket_Saddle | Body | +Y up, +Z forward, on top of the carapace | goblin rider's saddle |
| Socket_Mouth | Body | +Y forward, +Z up, between the fangs | carried prey, bite effects |
| Socket_Abdomen | Abdomen | +Y up, +Z forward, top of the abdomen | egg sac, armour, banner |
| Socket_Spinneret | Abdomen | +Y out of the spinnerets, +Z up | web-spit origin and direction |

### Clips (30 fps)

| Clip | Length | What happens | Event |
|---|---|---|---|
| `GetUp` | 1.33 s | from the Death end pose: pushes off, rolls back over, legs find the ground | |
| `Idle` | 3.0 s loop | breathing, abdomen pulse, palps and fangs twitch, L1 taps, R2 shifts | |
| `Walk` | 0.8 s loop | alternating tetrapod gait, root motion 1.25 m/s | |
| `Run` | 0.4 s loop | same gait, lower and faster, root motion 3.75 m/s | |
| `Hit` | 0.5 s | jolts back and up, legs flinch, fangs flare | |
| `Death` | 2.0 s | recoils, legs buckle, rolls onto its back, legs curl over the belly | Dead 1.75 s |
| `Bite` | 1.2 s | pulls back with front legs raised and fangs open, lunges 0.34 m, fangs strike | Bite 0.50 s |
| `Strike` | 1.33 s | rears ~20°, front legs up, slams them down ahead | Strike 0.73 s |
| `WebSpit` | 1.6 s | abdomen arches up over the back (skull facing the target), pumps, spits | Spit 0.67 s |
| `Threat` | 2.4 s | reared, front legs raised and spread, palps up, fangs flexing, sways | |

Event times are stored as custom properties on each action (`event_<Name>`). Walk and run are gait-generated
(`spider_anim.gait`): feet planted in the world during stance, rear legs leading. The other clips are key-pose tracks
interpolated per frame, with the leg IK solved every frame, so planted feet stay put while the body moves.

## Unity

Install into a Unity 6 URP project (MedievalSetting has it) with:

```
powershell -ExecutionPolicy Bypass -File tools\install_to_unity.ps1 -Project E:\Unity\Projects\MedievalSetting
```

It copies scripts, models, clips, the clip JSON and textures under `Assets/Insectoids` and keeps existing `.meta`
files. **Tools > Insectoids > Rebuild Spider** / **Rebuild Wasp** / **Rebuild Centipede** / **Rebuild Spider Eggs** /
**Rebuild Spiderling** / **Rebuild Broodmother** then build everything (each runs by itself the first
time); reports and renders go to `Logs/SpiderSetup` and `Logs/WaspSetup`. Shared editor code is in `InsectSetupUtil`.

| `Assets/Insectoids/...` | Contents |
|---|---|
| `Models/Spider.fbx` | Generic rig, avatar from this model, motion node `SpiderRig/Motion`, sockets kept (no Optimize Game Objects) |
| `Models/Anims/Spider@<clip>.fbx` | one clip each, avatar copied from Spider.fbx; loop, root motion (Walk, Run) and events from `spider_clips.json` |
| `Materials/` | `M_Spider` (+ `_Rust`, `_Dark` tints and `_Pale`), URP Lit, smoothness from albedo alpha; `M_Spider_Web`, `_Silk`, `_SilkThread` |
| `Prefabs/Spider_Giant` | Animator + `SpiderAppearance` + `SpiderCombat` |
| `Animation/SpiderAnims` | clip pools for `InsectRandomAnimator` |
| `Scenes/Insectoids_Test` | spiders, wasps and centipedes on random clips, 8 goblins around them (the spiders' prey, if the goblins are installed). Press Play. |

Runtime scripts (namespace `Insectoids`; no dependency on the goblin scripts):
- **`SpiderCombat`** receives the clip events (`OnSpiderEvent`: Bite, Strike, Spit, Dead) and raises `EventFired`
  (hook damage and sound there). On **Spit** it lobs a glob of silk from `Socket_Spinneret` on a ballistic arc to
  `target`, else the nearest `SpiderPrey` in front within `spitRange`, else a point ahead.
- **`SpiderWebGlob`** flies it, trailing a silk thread back to the spinnerets; **`SpiderWebSnare`** is the orb web it
  leaves where it lands (radius 1.3 m x size, 8 s). Gameplay hook: `SpiderWebSnare.Created`, `.All`,
  `SpiderWebSnare.IsSnared(position)` to slow or root units inside. Both are pooled.
- **`SpiderAppearance`** rolls a skin (Hunter x3, Rust, Dark, Pale) and a size (0.85-1.2x) per spider. The spider is
  one skinned mesh with one material already, so there is nothing to merge.
- **`InsectRandomAnimator`** + **`InsectAnimationSet`**: random pools through a playable graph with crossfades; root
  motion moves walking and running spiders, which meander and steer home. **`InsectTestUI`**: camera presets
  (colony 40 m / mid / close), labels, reshuffle, re-roll looks, and buttons that make every spider spit, bite,
  threaten... at once.

Verified in MedievalSetting: valid Generic avatar, 58 bones, 5,012 triangles, all clips and events imported; Walk
and Run root motion 1.25 and 3.75 m/s along the spider's forward (+Z), the body at a fixed offset from the GameObject
across loops (claw tips planted: 0.000 m/s slide in Blender over two loops); in Play mode the spiders walk, spit at the
goblins and leave webs, with no console errors.

## The wasp

![The giant wasp next to a goblin](docs/images/wasp.png)

Blender scene **Wasp** (same file). Rebuild with the Wasp scene on screen:

```python
import wasp_build
wasp_build.build_all()     # body + wings -> rig -> UVs and textures -> join -> clips (~15 s)
wasp_build.export()        # export/Wasp.fbx, export/Anims/Wasp@<clip>.fbx + wasp_clips.json
```

| Script | Does |
|---|---|
| `wasp_body.py` | anatomy, bone table, shells (head, thorax, petiole, six telescoping gaster plates, legs, mandibles, antennae) and the wing membranes |
| `wasp_paint.py` | `T_Wasp` painted per texel (bands, notches, face, thorax marks, amber legs); `T_Wasp_Wing` painted in wing space |
| `wasp_anim.py` | WaspPose -> bone matrices (forward kinematics), the eight clips; actions are named `Wasp_<clip>` |
| `wasp_build.py` | `build_all()`, `export()` |

- **Size:** ~1.5 m from mandibles to stinger, ~2.2 m wingspan, hovering with the thorax 1.7 m up (Root and Motion stay
  on the ground, so the pivot is under it and its shadow shows its height).
- **Build:** rigid shells again. The gaster is six plates on three bones (Gaster1-3) that telescope as it curls
  forward to sting. The wings are flat membranes on their own bones and a second material (transparent, both faces).
- **Look:** warning yellow and black bands with the black notch, yellow face, dark red eyes, black thorax with yellow
  marks, amber legs, smoky veined wings with a dark stigma. Skins in Unity: Wasp x3, Hornet (orange), Dark.

| Part | Triangles |
|---|---|
| Gaster plates + stinger | 1,240 |
| Legs (6 x 4 segments, spurs) | 1,788 |
| Head, eyes, ocelli, mandibles | 442 |
| Antennae | 432 |
| Thorax + petiole | 336 |
| Wings (4) | 42 |
| **Total** | **4,280** |

Skeleton (44 bones): `Motion` beside `Root` > `Body` (thorax) > `Head` (`MandibleL/R`, `AntennaL/R_Scape` >
`_Flagellum`), `Gaster1` > `Gaster2` > `Gaster3`, `ForewingL/R`, `HindwingL/R`, legs `Leg{L|R}{1-3}_{Coxa|Femur|Tibia|Tarsus}`.
Sockets: `Socket_Mouth` (Head), `Socket_Stinger` (Gaster3, +Y out of the stinger), `Socket_Saddle` (Body).

| Clip | Length | What happens | Event |
|---|---|---|---|
| `Idle` | 2.0 s loop | hover: bob, drift, abdomen pumping, legs and antennae swaying | |
| `Fly` | 1.0 s loop | nose down, legs trailing, root motion 4 m/s | |
| `Threat` | 1.6 s | abdomen curled forward and pumping, mandibles snapping, louder wings | |
| `Sting` | 1.3 s | rears back, lunges 0.45 m with the stinger forward | Sting 0.60 s |
| `Dive` | 1.8 s | climbs, dives to 0.65 m over the ground, stings, climbs back | Sting 0.90 s |
| `Hit` | 0.5 s | knocked back and rolled, wings stutter | |
| `Death` | 2.0 s | wings stop, falls, bounces, lies on its side with the legs curled | Dead 1.75 s |
| `GetUp` | 1.5 s | from the Death pose: wings start, rolls upright, climbs back to the hover | |

The wings flip between up and down stroke every frame (15 beats a second), which reads as a buzz; the hind wings
follow the forewings (they are hooked together in real wasps).

In Unity: **Tools > Insectoids > Rebuild Wasp** makes `Prefabs/Wasp_Giant` (Animator, `InsectAppearance`,
`InsectEvents`), `Animation/WaspAnims` and the materials; report and renders in `Logs/WaspSetup`. Animation events call
`OnInsectEvent(name)` on both creatures; `InsectEvents.EventFired` (wasp) and `SpiderCombat.EventFired` (spider) pass
them on.

**Test scene:** `Scenes/Insectoids_Test` (Tools > Insectoids > Build Test Scene; the creature setups rebuild it): 5
spiders, 4 wasps and 8 goblins. It replaces the spider-only `Insectoids_SpiderTest`.

## The centipede

![The giant centipede next to a goblin](docs/images/centipede.png)
![Burrowing](docs/images/centipede_burrow.png)

Blender scene **Centipede** (same file). Rebuild with the Centipede scene on screen:

```python
import centipede_build
centipede_build.build_all()   # body -> rig -> UVs and texture -> clips (~20 s)
centipede_build.export()      # export/Centipede.fbx, export/Anims/Centipede@<clip>.fbx + centipede_clips.json
```

| Script | Does |
|---|---|
| `centipede_body.py` | anatomy, the body chain, two-bone leg IK, bone table, shells (head, 18 plates, tail, legs, antennae, forcipules) |
| `centipede_paint.py` | `T_Centipede`: blue-black plates with pale rims, ochre belly, red-orange head and tail end, yellow legs |
| `centipede_anim.py` | the path-following body, the metachronal leg wave, ten clips at 60 fps; actions `Centipede_<clip>` |
| `centipede_build.py` | `build_all()`, `export()` |

- **Size:** ~3.4 m long, trunk 0.17 m off the ground, ~1 m across the legs. Scolopendra-like warning colours.
- **Build:** a chain of 20 rigid elements (`Root > Head > Seg01 > ... > Seg18 > Tail`), each with a pair of two-bone
  legs (`Leg{L|R}{01-18}_{Femur|Tibia}`), long trailing `TailLeg{L|R}`, `Antenna{L|R}_1/_2`, `Forcipule{L|R}` (the venom
  claws), `Motion` for root motion. 107 bones, 5,448 triangles, one 1024² texture.
- **The body is a path:** each clip gives a direction field (sway, rear, curl, dive) that is integrated into a curve;
  every element sits at a fixed arc length behind the head, so the body never stretches. The skeleton plays in place;
  Motion carries the travel, at the ground actually gained along the swaying path (so the loop does not pop).
- **Legs:** a metachronal wave (each leg steps a fifth of a cycle after the one behind it, left and right half a cycle
  apart), feet planted in the world through IK; flailing where the body rears, tucked back along the body underground,
  curled in death.

| Clip | Length | What happens | Event |
|---|---|---|---|
| `Idle` | 3.0 s loop | slow S-sway, head searching, a ripple of leg steps down the body | |
| `Walk` / `Run` | 0.9 / 0.6 s loop | root motion 1.5 / 4 m/s (Run sways more) | |
| `Threat` | 2.5 s | the front rears like a cobra, head tipped down, legs flailing, claws snapping, tail legs up | |
| `Bite` | 1.2 s | rears, lunges 0.45 m, strikes with the forcipules | Bite 0.55 s |
| `Burrow` | 2.5 s | dives into the ground 0.55 m ahead and disappears; root motion carries the GameObject to the hole | Burrow 0.57 s |
| `Emerge` | 2.5 s | comes up out of the ground under the GameObject and crawls out until its tail leaves the hole; root motion follows the body | Emerge 0.58 s |
| `Hit` | 0.5 s | a jolt runs down the body | |
| `Death` | 2.0 s | rolls onto its back and curls up, legs curling | Dead 1.85 s |
| `GetUp` | 1.5 s | uncurls, rolls back over, stands | |

In Unity: **Tools > Insectoids > Rebuild Centipede** makes `Prefabs/Centipede_Giant` (Animator, `InsectAppearance`,
`InsectEvents`, `CentipedeBurrow`). `CentipedeBurrow` opens a dark hole and throws dirt clods at the Burrow / Emerge
events (`Burrowed` / `Emerged` events and `Underground` for gameplay). Burrow ends with the GameObject over the hole and
Emerge starts with the hole under it, so Burrow then Emerge in place uses one hole (checked: 7 cm apart); move the
GameObject while it is underground to surface elsewhere. In the test scene a burrowed centipede travels 3-8 m
underground (`InsectAnimationSet.Pool.relocate`) and comes back out 1.5 s later. Checked in Unity: Walk/Run root motion 1.5 / 4 m/s straight ahead with the head within 2 / 6 mm of its
place across loops; burrow effect and events in Play mode with no console errors.

## The spider family

![Eggs, spiderling, giant spider and broodmother from the game camera (22 m, 50 deg pitch, fov 30)](docs/images/spider_family_22m.png)
![The same, 12 m away](docs/images/spider_family.png)

Daniel's card game has four spider units: eggs, spiderlings, the adult and the broodmother. The spiderling and the
broodmother are the giant spider rebuilt with other numbers, not copies of it: `spider_body.Kind` describes a member of
the family as changes to the adult (size, the carapace and abdomen reshaped about the pedicel, leg length and
thickness, stance, resolution, extra parts and bones), and the same body, rig, IK, gait, clip, paint and export code
builds all three. `spider_body.use(name)` picks the kind; the adult is the default and builds bit for bit as before
(checked: mesh, weights, UVs, bones, every key of the ten clips, the data bakes and both paints). Clip settings per kind
(fps, tempo on the adult's clips, gaits, own clips) are `spider_anim.FAMILY`; paint styles `spider_paint.STYLE`.

Headless (the live Blender stays free), in `blender/insectoids.blend`:

```
blender -b --factory-startup blender/insectoids.blend --python tools/spider_family_run.py -- Spiderling build review lowest trace sheets export
blender -b --factory-startup blender/insectoids.blend --python tools/spider_family_run.py -- Broodmother build review lowest trace sheets export
blender -b --factory-startup blender/insectoids.blend --python tools/spider_family_run.py -- SpiderEggs props export
blender -b --factory-startup blender/insectoids.blend --python tools/spider_family_run.py -- Family lineup nosave
```

or inside Blender, with the kind's scene on screen: `spider_build.build_all(kind="Spiderling")`,
`spider_build.export("Spiderling")`, `spider_eggs.build_props()`, `spider_eggs.export_props()`.

| Script | Does |
|---|---|
| `spider_body.py` | `Kind`, the three kinds, the broodmother's extras (egg sacs, spines, the egg she lays on `SpawnEgg`) |
| `spider_anim.py` | `FAMILY` (clips, fps, tempo, gaits, tweaks per kind), the slump death, the broodmother's Spawn |
| `spider_paint.py` | paint in the adult's coordinates for every kind, styles `juvenile` and `brood` |
| `spider_eggs.py` | the leathery egg shape (shared), the three egg props, their paint and export |
| `spider_build.py` | `build_all(kind=...)`, `export(kind)`, review renders, lowest vertex per clip, root-motion trace, the family lineup |
| `tools/spider_family_run.py` | the headless driver |
| `tools/spider_adult_check.py` | proves the adult still builds bit for bit as before (dump + compare) |

All three spiders share the skeleton layout (`Motion` beside `Root` > `Body` ...; the broodmother adds `SpawnEgg`), the
sockets and the clip conventions of the adult (30 or 60 fps, root motion on `Motion` only, events `OnInsectEvent`).
Feet: the kinds lift planted tarsus tips by `Kind.foot_z` (the tip's mesh rests on the ground), keep the planted tarsus
angle against the world when the body tilts (`level_feet`) and never let a foot target dip below the ground (the key
tracks' spline overshoots; the adult's feet still go 3-8 cm under in some clips, left as they are).

**In Unity** (after `tools/install_to_unity.ps1`): **Tools > Insectoids > Rebuild Spider Eggs**, **Rebuild Spiderling**
and **Rebuild Broodmother** (each runs by itself the first time) make:

| `Assets/Insectoids/...` | Contents |
|---|---|
| `Prefabs/SpiderEgg_Clutch`, `_Single`, `_Hatched` | static props, `M_SpiderEggs` |
| `Prefabs/Spider_Spiderling` | Animator + `InsectAppearance` (skins base x2, Amber, Dusky; 0.85-1.15x) + `InsectEvents` |
| `Prefabs/Spider_Broodmother` | Animator + `InsectAppearance` (base x2, Ashen; 0.92-1.08x) + `InsectEvents` + `SpiderBrood` (Spawn puts down `SpiderEgg_Single`) |
| `Animation/SpiderlingAnims`, `BroodmotherAnims` | clip pools for `InsectRandomAnimator` (Death holds, then back to Idle: no GetUp clips) |

and add 4 spiderlings, a broodmother and 5 egg props to `Scenes/Insectoids_Test`. Reports and renders go to
`Logs/SpiderlingSetup`, `Logs/BroodmotherSetup` and `Logs/SpiderEggsSetup` (`family_game_22m.png`: the four at the game
camera). The scripts compile against MedievalSetting's editor (checked offline); they have not been run in Unity yet.

### The spiderling

- **Size:** a third of the adult (`size` 0.36), dog-sized: 0.73 m from fangs to spinnerets, back 0.34 m, 0.7 m
  across the legs (the adult: 1.75 m, 0.88 m, 2.2 m). Juvenile proportions: carapace x1.12, abdomen x1.28 / 1.2 / 1.3 (wide, long, tall), legs 0.84 as
  long and 0.72 as thick, eyes x1.25, no leg spines.
- **Look:** pale sand and cream with amber legs between pale joints, a darker heart mark showing through the abdomen,
  a milky sheen on top, warm (subsurface) shadows instead of cool ones, glossy (smoothness ~0.42), the skull only
  faint (0.45 strength). `T_Spiderling` 512.
- **Budget:** 1,996 triangles (legs 1,232 at 3-5 sides, abdomen 240, carapace 160, palps 128, chelicerae 100, fangs
  44, eyes 52, pedicel 24, spinnerets 16). 58 bones, the adult's.

| Clip | Length | What happens | Event |
|---|---|---|---|
| `Idle` | 2.1 s loop (60 fps) | the adult's idle faster, twitchier palps, a glance aside | |
| `Walk` | 0.33 s loop | skittering tetrapod gait, root motion 0.97 m/s | |
| `Run` | 0.2 s loop | root motion 2.43 m/s, low | |
| `Hit` | 0.37 s | jolts back | |
| `Death` | 1.67 s | sinks onto its belly, legs fold up and in, a last twitch curls them | Dead 1.4 s |
| `Bite` | 0.83 s | pulls back, lunges, front feet pin closer than the adult's (shorter legs) | Bite 0.35 s |

### The broodmother

- **Size:** 1.8x the adult (`size` 1.8): 3.7 m from fangs to spinnerets, the abdomen 1.9 m high (2.1 m to the tips
  of her spines), 4.1 m across the legs. Abdomen bloated (x1.5 wide, x1.3 long, x1.55 tall), legs 0.96 as long and 1.3x as thick, a wider stance,
  the body lower, bigger leg spines.
- **Silhouette:** a crown of 15 silk egg sacs over the rear of the back and down both flanks (off the skull), three
  pairs of big curved spines on the abdomen's shoulders, a short ridge of spines on the carapace.
- **Look:** darker and older than the adult: greying hairs, healed scars on the carapace and abdomen, worn pale leg
  tips, silk wisps on the rear of the abdomen; the skull at full strength. Sacs off-white silk with stains and fibres.
  `T_Broodmother` 1024.
- **Budget:** 6,796 triangles (legs 2,960, leg spines 384, abdomen 912 at 24 sides, sacs 900, carapace 396, palps 312,
  chelicerae 280, horns 256, eyes 148, laid egg 112, others 136). 59 bones: the adult's plus `SpawnEgg`.
- **Spawn:** `SpawnEgg` (child of `Abdomen`) carries the egg she lays; at rest it sits inside the abdomen behind the
  spinnerets. Its scale and the abdomen's are keyed (Kind.scaled); every other bone keeps scale 1.

| Clip | Length | What happens | Event |
|---|---|---|---|
| `Idle` | 3.9 s loop | the adult's idle slowed, the abdomen breathing (scale) | |
| `Walk` | 1.33 s loop | heavy gait (duty 0.7, low steps, more sway), root motion 1.15 m/s | |
| `Hit` | 0.67 s | jolt, the abdomen shudders | |
| `Death` | 2.6 s | too heavy to roll: sinks onto her belly, legs fold, leans over, the abdomen sags and goes slack | Dead 2.2 s |
| `Bite` | 1.5 s | the adult's bite slowed, the abdomen kept up | Bite 0.63 s |
| `Threat` | 3.13 s | rears, front legs high, the abdomen swells | |
| `Spawn` | 4.2 s | the abdomen swells and pulses, she sinks and tips it down, an egg is squeezed out of the spinnerets, drops under `Socket_Spinneret`, shrinks away 2 frames later; she rises | Spawn 3.0 s |

At the Spawn event the clip's egg lies on the ground exactly under `Socket_Spinneret` (0.15 m up, its centre); a game
puts its own egg or spiderling there. In Unity `SpiderBrood` does that (`spawnPrefab`, `Spawned` event).

### Spider eggs

Static props, one material and one 512 texture (`T_SpiderEggs`), origin on the ground under the middle:

| Prop | Triangles | What |
|---|---|---|
| `SpiderEgg_Clutch` | 1,410 | nine eggs piled on the ground (six leaning in, three on top), half sunk in a silk mat, five threads drawn over them; ~1.3 m across, 0.48 m high |
| `SpiderEgg_Single` | 304 | one egg on a little silk pad, two threads: the egg the broodmother lays (same size, 0.38 x 0.30 m) |
| `SpiderEgg_Hatched` | 316 | the bottom of an egg, torn open and empty (outer and inner shell, the torn edge peeling out), on a pad |

Eggs are leathery cream with mottles, freckles and fine wrinkles, silk wisps painted over their lower halves; inside
the hatched shell dark and wet. The egg shape (`spider_eggs.egg`) is shared with the broodmother's sacs and laid egg.

## Repository

| Path | What |
|---|---|
| `src/` | the Blender Python that builds everything |
| `blender/insectoids.blend` | the working file (compressed, ~12 MB) |
| `export/` | Unity-ready FBX (`<Creature>.fbx`, `Anims/<Creature>@<clip>.fbx`) and the clip JSON |
| `textures/` | painted textures |
| `unity/Insectoids/` | the Unity scripts (`Runtime/`, `Editor/`) |
| `tools/install_to_unity.ps1` | copies all of it into a Unity project |
| `tools/spider_family_run.py` | headless Blender driver for the spider family (build, checks, renders, export) |
| `tools/spider_adult_check.py` | dumps the adult spider's build and compares two dumps (shared code must not change it) |
| `docs/images/` | the pictures in this README |
| `HANDOFF.md` | conventions, open issues and checks for whoever picks this up next |

Not in git: `renders/` (review renders) and Blender's `.blend1` backups.
