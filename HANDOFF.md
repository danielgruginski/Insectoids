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

## State (2026-09-26)

Spider, wasp and centipede: done in Blender and Unity (shared InsectSetupUtil, combined Insectoids_Test scene). Not a git repo yet; Daniel
will make it once the creatures are done.

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
- `bug_scene.render_sheet(clip, frames, cams=("CAM_Side", "CAM_34"), color='TEXTURE')` after `spider_anim.use(clip)`
  (`follow=True` keeps root-motion clips in frame).
- Colony read: `bug_scene.shot("CAM_Colony", ...)`.
