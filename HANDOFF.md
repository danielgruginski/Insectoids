# Handoff

Where the insectoids stand and how to pick them up. The README is the reference (rebuild, skeleton, sockets,
budget, clips). This file holds the working agreements, the conventions that bite, open issues and checks.

## Working agreements

- Same as the goblins (see `../Goblins/HANDOFF.md`): Daniel watches Blender live, reviews in Unity and sends
  screenshots, prefers the obvious fix, asks for commits in batches.
- Budget: colony camera ~40 m at 50°, no LODs. The spider is ~5k triangles and one 1024² texture; report counts
  when adding parts.
- Design calls Daniel made (2026-09-26): hunting-spider look, horse-sized and rideable, clips = idle, walk, run,
  hit, death + bite/leg strike, web spit, threat display.

## Conventions that bite

- **Rigid parts, not heat maps.** Each part is built in its bone's rest frame (`xform=_mat4(head, frame)`) and
  tagged with its bone while building; the vertex groups come from that. New parts must be tagged (`_Parts.tag`).
- **One IK for bind pose and clips.** `spider_body.solve_leg` places the bind-pose legs and every animated frame.
  Changing `FEMUR_REST`, `META_REST`, leg lengths or feet changes the mesh too: rebuild everything, then the clips.
- **Foot targets are armature space** (they include the root's travel). `leg_solution` converts with
  `(root @ body).inverted()`; converting with the body transform alone made the walk drag its feet behind.
- **UV seams are made by the builders**: lofts cut along the underside, `split=True` cuts big bodies along both
  sides (a single belly cut squashed the back, where the skull is), cones cut up one side and round the base, eye
  domes are disks. `spider_paint.unwrap` is a plain angle-based unwrap of those seams. Look at
  `renders/uv_layout.png` and `textures/T_Spider.png` after changes, not only at renders.
- **Byte images take stored (sRGB) values** in `pixels`; the painter writes sRGB directly.
- **Root motion lives on the `Motion` bone, a sibling of `Root`.** Unity (Generic) turns the motion node's travel into
  GameObject movement but also leaves it in the pose, so with `Root` as the motion node the whole spider moved twice
  as fast and snapped back ~1 m every loop (Daniel: "jittering, as if going back once the walk loops").
  `pose_matrices` keeps the skeleton in place and moves only `Motion`. In Blender the walk therefore previews on a
  treadmill.
- **The motion node must import with identity orientation** (Unity measures root motion in its frame): point it up
  with +Z toward the spider's front (world -Y). Pointing down (+Z backward) made the walk go backwards. Bone axes map
  Blender -> Unity as up = bone Y, forward = bone Z, through the geometry conversion (Blender -Y = Unity +Z).
  `setup_report.txt` must show Walk/Run `dir=(0.00, 0.00, 1.00)`.
- **Culling hides pose bugs in edit-mode tests:** the prefab culls (`CullUpdateTransforms`), so an off-screen test
  instance only gets root motion and no pose. Set `AlwaysAnimate` when tracing bones.
- `Matrix(rows).transposed()` in `rest_bones`: each row becomes a column, i.e. the bone's X, Y and Z axes.
- **MCP round trips take ~10 s**, too slow to catch a 1 s effect in Play mode: schedule renders from an
  `EditorApplication.update` callback (see the checks).
- **Mesh data is reused by name.** `mesh_obj` now deletes an orphan mesh with the same name first: vertex-group names
  live on the mesh (Blender 4), and a stale orphan (the wing mesh left behind by the join) made the new groups
  `ForewingL.001`, which match no bone, so the wings stayed at hover height while the body fell. `wasp_build`
  asserts no `.` in group names after the join.
- **UV layer names must match before a join:** the wings' layer is created as `UVMap`, like the body's unwrap;
  otherwise the join keeps two layers and the wings sample (0, 0) of the texture (transparent: invisible wings).
- **Actions are global in the .blend:** the wasp's are `Wasp_<clip>` (`wasp_anim.action_name`), so they don't replace
  the spider's `Idle`, `Hit`, `Death`, `GetUp`.
- **Poses in world space get no root on top.** The centipede's chain is computed in world space (the head travels
  along the path), so `pose_matrices` must not multiply it by the root again: that put the travel back into the
  skeleton and the walk drifted 1.3 m per loop and snapped back (the spider's jitter again). Trace every new moving
  clip in Unity: head-to-GameObject offset constant, no frame-to-frame jump.
- **Swaying paths gain less ground than their arc length:** the centipede's root moves at the ground actually gained
  (`v * mean(cos(sway))`), or the loop pops by that difference.
- **Clips that end somewhere else need root motion.** The first Burrow/Emerge left the GameObject in place, so the
  centipede dived into a hole ahead and came out of a new one where its tail had been (Daniel caught it). Now the
  root follows the body's middle to the hole (Burrow) and from it (Emerge).
- **Animation events also fire in edit mode** (a PlayableGraph evaluated from an editor script, previews). Effects
  spawn only when `SpiderFx.CanSpawn` (Play mode): a Burrow/Emerge check evaluated in edit mode once left 26 dead
  FX objects in Insectoids_Test that threw in Play mode. Pooled effects live under one `FX_Insectoids` object, drop
  themselves if copied without their setup, and their pools reset per Play session (works without domain reload).
- **Clip keys are LINEAR on every frame** (57 bones x 7 channels = 399 F-curves per clip); the smoothing is in the
  key-pose tracks, not in Blender's curves.
- **The adult must not move.** The spider family shares the adult's code (`spider_body.Kind`); every change to shared
  code keeps the adult's floats bit for bit (identity reshapes return the same object, factors of 1.0, the old
  expressions kept where float32 rounding differs). Check with `tools/spider_adult_check.py` against the last commit
  after touching it.
- **Key-pose tracks overshoot** (Catmull-Rom): a foot target keyed down to the ground dips below it between keys. The
  adult's feet go 3-8 cm under in Idle/Hit/Bite/Strike and ~0.8 m during the Death/GetUp roll (legs through the
  ground); left as they are. The kinds clamp planted targets to the ground (`Kind.level_feet`).
- **BVH hits on a fresh bmesh come back with zero normals** unless `bm.normal_update()` ran first. The adult's eyes
  rely on that (their direction is the ray's); the broodmother's sacs collapsed to lines until `_surface` updated
  normals.
- **float32 `sin(pi)` is negative** (-8.7e-8): `x ** 0.8` of it is NaN, and NaN paints black. Clamp before fractional
  powers (the spiderling's heart mark).
- **Headless Blender has no GPU drawing:** `bpy.ops.uv.export_layout` fails in `-b`; `spider_paint.draw_uv_layout`
  rasterises the layout over the texture instead.
- **Multi-object edit mode:** `bmesh.from_edit_mesh` handed back the wrong object's mesh after the UV operators; the
  egg props scale their UV islands in object mode.

## State (2026-09-26)

Spider, wasp and centipede: done in Blender and Unity (shared InsectSetupUtil, combined Insectoids_Test scene). Not a git repo yet; Daniel
will make it once the creatures are done.

2026-10-23: the spider family (spiderling, broodmother, egg props) built in Blender and exported, Unity setup scripts
written and compile-checked offline, not yet installed or run in Unity; see the entry below. Git repo since 2026-10-06
(danielgruginski/Insectoids, CC0); the family is in the working tree, not committed.

## 2026-10-23: the spider family (spiderling, broodmother, eggs)

Daniel: "Keep moving on the creatures", and earlier "don't bother with adding them to the game, build the creatures".
His card game has four spider units: eggs, spiderlings, adult, broodmother. Built in Blender (headless, the live Blender
was in use), exported, Unity scripts written and compile-checked; nothing copied into MedievalSetting, not committed.

- **Parametrised, not copied:** `spider_body.Kind` (size, carapace/abdomen reshape about the pedicel, leg
  length/thickness/stance, lift, resolution, extras, extra bones, `foot_z`, `level_feet`); `spider_anim.FAMILY` (clips,
  fps, tempo on the adult's clips, gaits, track tweaks, own clips in `KIND_CLIPS`); `spider_paint.STYLE` (juvenile,
  brood) with texels mapped back to the adult's coordinates (`to_adult`) so the markings land in the same places;
  `spider_eggs.py` (egg shape, props). Scenes Spiderling, Broodmother, SpiderEggs in `blender/insectoids.blend`;
  `tools/spider_family_run.py` drives it headless.
- **Spiderling:** size 0.36, big head and abdomen, thin legs, pale/translucent paint, faint skull; 1,996 tris, 512
  texture; Idle, Walk, Run, Hit, Death, Bite at 60 fps (skittering: walk 0.33 s, run 0.2 s).
- **Broodmother:** 1.8x, bloated abdomen with 15 egg sacs, shoulder spines, carapace ridge, thick legs, old dark paint
  with the skull; 6,796 tris, 1024; Idle, Walk, Hit, Death, Bite, Threat, Spawn at 30 fps. `SpawnEgg` bone + keyed
  scale (`bug_rig.apply_pose(scaled=...)`) for the laid egg and the swelling abdomen; event Spawn (3.0 s) with the egg
  on the ground under `Socket_Spinneret`.
- **Eggs:** SpiderEgg_Clutch (1,410 tris), _Single (304, the laid egg), _Hatched (316), one 512 texture.
- **Death without the roll** (`_clip_slump`) for both kinds: the adult's roll puts its legs through the ground, and a
  bloated broodmother can't turn over.
- **Checked:** the adult unchanged (dump of the rebuilt adult and of the saved .blend's Spider scene against the last
  commit: identical); weights (0 unweighted, 0 over 4); lowest vertex per clip (spiderling: standing clips +0.2 mm,
  Death -1.9 mm; broodmother: +0.8 mm, Death -0.4 mm, Spawn +0.7 mm); Walk/Run traced
  (skeleton in place, Root fixed, no jump at the loop, planted feet 0.000 m/s slide, Motion 0.324 / 0.486 / 1.53 m
  per loop straight ahead, also after an FBX re-import); the Spawn sequence frame by frame (abdomen, egg, socket
  heights); close-ups, UV layouts and textures at full res; the four at the game camera; offline C# compile of the
  repo's Runtime and Editor scripts against MedievalSetting's references (0 errors).
- **How the adult check works:** `tools/spider_adult_check.py` (`dump` rebuilds the adult from a given `src` in an empty
  Blender and saves mesh, UVs, seams, weights, info, bones, every F-curve key, a 256 bake and both paints to .npz;
  `compare` diffs two dumps). Run it on the last commit's `src` (e.g. `git worktree add`) and the working tree's after
  any change to shared spider code. The saved .blend's Spider scene was compared the same way (mesh, UVs, all ten
  actions: identical).
- **Gotchas found:** see Conventions (track overshoot, BVH zero normals, float32 sin NaN, headless UV export,
  multi-edit bmesh). The adult's death roll legs through the ground is an old issue, not fixed for the adult.
- **Open:**
  - Not run in Unity: install, the three menu items, `setup_report.txt` (avatar valid, `dir=(0,0,1)`, the Spawn event,
    `SpawnEgg` scale curves) and a Play-mode trace of Walk/Run are still to do.
  - GetUp for the kinds: done 2026-10-23 (below). No Run, Strike or WebSpit for the broodmother; no Threat, Strike or
    WebSpit for the spiderling (not asked for).
  - `SpiderBrood` only puts down the egg prop; hatching (egg -> SpiderEgg_Hatched + a spiderling) is game logic.
  - The spiderling's leg joints are angular at 3-5 sides (budget); the brood's sacs are 6-sided and read faceted
    close up.
  - The adult's own feet (3-8 cm under in some clips) and death roll are unchanged on purpose.

## 2026-10-23 (later): GetUp for the spiderling and the broodmother

Daniel: "Do these tasks you mentioned" (from the polish list: in the test scene both popped back to Idle after dying).

- **`spider_anim._clip_rise`** (the kinds' own clip, `KIND_CLIPS[...]["GetUp"]`): starts from the slumped Death's end
  pose (`_slump_tracks`, the slump's tracks split out of `_clip_slump`; `SLUMP` holds each kind's slump arguments for
  both), the palps and fangs stir, the legs unfold and step out one by one (L1 R1 L2 R2 ..., lifting 9 cm, adult
  metres), the body pushes up off its belly and levels (a 1.4 cm overshoot, a small bob), the abdomen lifts and fills
  out (`abs` back to 1), and it ends on Idle's first frame (the femur at the kind's own preference: Idle has no `fe`
  track). Spiderling 60 frames at 60 fps = 1.0 s (N30 30), broodmother 48 at 30 fps = 1.6 s (N30 48); no events.
- **Checked:** Death's last pose -> GetUp's first and GetUp's last -> Idle's first: bone matrices identical (max
  difference 0.0); lowest vertex in GetUp +0.2 mm (spiderling, a planted tarsus) and +0.8 mm (broodmother), the body
  never lower; every other action and every mesh in the saved .blend unchanged (all 50 compared), the adult
  bit-identical (`spider_adult_check.py`: IDENTICAL); contact sheets `renders/sheet_spiderling_GetUp.png`,
  `sheet_broodmother_GetUp.png`. Built with `spider_family_run.py -- <Kind> clips lowest sheets export`; the old clip
  and model FBXs came out content-identical (only the exporter's per-run object ids differ) and were restored from git,
  so only `<Kind>@GetUp.fbx` and the two JSONs are new.
- **Unity:** `SpiderlingSetup` / `BroodmotherSetup` pools: Death `next = "GetUp"`, a `GetUp` pool (weight 0, `next =
  "Idle"`), as the adult's. `Run(false)` re-imports the clips and rewrites the animation set in place (same asset), so
  the test scene's instances pick it up without rebuilding the scene. Not run in Unity.

## 2026-10-24: the Godot pack

- **Why:** Daniel wants a Godot version of the itch Creatures pack (GDScript, every creature built so far). The Beasts
  repo holds the shared addon (import script, `Creature`, `CreatureWanderer`, coat shaders, builder, demos); this repo
  adds its creatures (README "Godot").
- **Export:** `tools/godot_export.py` captures each build's `export()` (FBX writer swapped for `bug_gdx.export_glb`),
  so rig, meshes, clips and root motion match Unity's; the eggs through `bug_gdx.export_props`. The Spider folder takes
  only `T_Spider.png` / `T_Spider_*` (a looser filter pulled in the family's textures).
- **Effects** (`godot/addons/insectoids/fx`, ported from SpiderFx / CentipedeBurrow): web glob + silk thread +
  snare (`SpiderWebSnare.is_snared(point)`, Unity's `IsSnared`), the centipede's holes and dirt, the broodmother's
  laid egg.
  They spawn into a shared container outside the creatures, and work with or without a collider under them.
- **Scenes reference the .glb:** the eggs are a `Creature` root (one skin, size 1) over the model, like the
  creatures; attachments on sockets are BoneAttachment3Ds under the root with an external skeleton
  (`insect_setup_util.attach` -> the Beasts builder's `attach()`).
- **Checked (Godot, windowed):** spit, snare, burrow and emerge, laying, the egg row, with and without a collider; the
  insectoids demo (27 creatures).

## Open / next

- **Gameplay:** snares only report (`IsSnared`); nothing slows yet. Bite/Strike events carry no damage. The spider
  does not turn toward its target before biting or spitting (the glob arcs to it anyway).
- **Goblin spider-rider:** a saddle prop on `Socket_Saddle` and a riding pose for the goblin.
- **Look:** the big front eyes read a little cute up close; the abdomen silhouette is 20-sided (faceting visible
  close up).
- **Wasp:** no ground clips (land, walk); flies at one height; the thorax marks read a little like a frowning face
  from above.
- **Centipede:** turning while walking is Unity steering only (the path is straight); no climbing.
- **More bugs:** reuse `solve_leg` / `leg_frames` / `gait` (walkers), the wasp's FK pose (fliers) or the centipede's
  path chain (worms, millipedes, snakes).

## Checks

- **Unity:** after `tools/install_to_unity.ps1` and **Tools > Insectoids > Rebuild Spider**, read
  `Logs/SpiderSetup/setup_report.txt` (avatar valid, clips with events, root speeds
  and `dir=(0,0,1)`, motion node `SpiderRig/Motion`) and look at `lineup.png`, `idle_close.png`, `lineup_colony_40m.png`.
- **Play mode:** `Application.runInBackground = true` (InsectTestUI sets it). To catch an effect, order it and
  render from a scheduled `EditorApplication.update` callback with `RenderPipeline.SubmitRenderRequest`
  (`Unity_Camera_Capture` fails in play mode).
- **Blender:** `spider_build.build_all()` report: `weights.unweighted == 0`, `over4 == 0`, triangle total.
- **Family (headless):** `tools/spider_family_run.py -- <Kind> build lowest trace sheets` and read `lowest` (nothing
  under 0 beyond a few mm) and `trace` (root_moves 0, body_loop_jump 0, planted_slide_mps 0, dir (0,-1,0)); `Family
  lineup nosave` for `renders/family_game_22m.png`.
- `bug_scene.render_sheet(clip, frames, cams=("CAM_Side", "CAM_34"), color='TEXTURE')` after `spider_anim.use(clip)`
  (`follow=True` keeps root-motion clips in frame).
- Colony read: `bug_scene.shot("CAM_Colony", ...)`.
