class_name InsectFx
extends RefCounted
## Shared pieces for the insects' effects (the spider's web spit, the centipede's burrow): the textures made in code
## (an orb web, a burrow hole; baked once to T_SpiderWeb.png and T_BurrowHole.png beside this script by
## setup/bake_fx_textures.gd), the materials (a flat unlit alpha one tinted per instance, wet silk, dirt), a lumpy glob
## mesh, a flat square, the ground under a point and the node the effects live under (FX_Insectoids in the current
## scene, so they stay out of the creatures and out of saved scenes). Unity: SpiderFx (and CentipedeBurrow's hole
## texture).

const DIR := "res://addons/insectoids/fx/"
const WEB_TEXTURE := DIR + "T_SpiderWeb.png"
const HOLE_TEXTURE := DIR + "T_BurrowHole.png"
const ALPHA_SHADER := DIR + "insect_fx_alpha.gdshader"
## the per-instance colour of the alpha material (GeometryInstance3D.set_instance_shader_parameter; Unity's
## MaterialPropertyBlock _BaseColor)
const TINT := &"tint"

static var _glob: ArrayMesh
static var _square: PlaneMesh
static var _web_material: ShaderMaterial
static var _hole_material: ShaderMaterial
static var _thread_material: ShaderMaterial
static var _silk_material: StandardMaterial3D
static var _dirt_material: StandardMaterial3D


## Effects only appear in a running game: the creatures' events don't fire in the editor anyway, and anything
## spawned there would be saved with the scene. Unity: SpiderFx.CanSpawn.
static func can_spawn(from: Node) -> bool:
	return not Engine.is_editor_hint() and from != null and from.is_inside_tree()


## The parent of the effects of `from` (a creature's component): FX_Insectoids, made when first needed, under the
## current scene, or under the creature's own viewport when it is elsewhere (a SubViewport preview), at the origin.
## Unity: SpiderFx.Container.
static func container(from: Node) -> Node3D:
	var host: Node = from.get_tree().current_scene
	if host == null or not host.is_ancestor_of(from):
		host = from.get_viewport()
	var c := host.get_node_or_null("FX_Insectoids") as Node3D
	if c == null:
		c = Node3D.new()
		c.name = "FX_Insectoids"
		host.add_child(c)
	return c


## The global scale of a creature (its size roll), for scaling its effects. Unity: transform.lossyScale.x.
static func size_of(n: Node3D) -> float:
	return n.global_basis.get_scale().x if n != null else 1.0


## The first thing a ray meets from `from` down `depth` metres, leaving out the collision objects in and under the
## nodes in `skip` (the creature's own): intersect_ray's {position, normal, collider...}, or an empty Dictionary when
## nothing is there (no colliders: callers fall back to the creature's feet).
static func ground(from_node: Node3D, from: Vector3, depth: float, skip: Array = []) -> Dictionary:
	return ray(from_node, from, from + Vector3.DOWN * depth, skip)


## A ray between two points against the world's colliders (not areas: Unity's QueryTriggerInteraction.Ignore),
## leaving out those in and under the nodes in `skip`.
static func ray(from_node: Node3D, a: Vector3, b: Vector3, skip: Array = []) -> Dictionary:
	var world := from_node.get_world_3d()
	if world == null:
		return {}
	var q := PhysicsRayQueryParameters3D.create(a, b)
	q.collide_with_areas = false
	var ex: Array[RID] = []
	for n in skip:
		if is_instance_valid(n):
			_rids(n, ex)
	q.exclude = ex
	return world.direct_space_state.intersect_ray(q)


static func _rids(n: Node, out: Array[RID]) -> void:
	if n is CollisionObject3D:
		out.append((n as CollisionObject3D).get_rid())
	for c in n.get_children():
		_rids(c, out)


## Is this something that moves about (a creature's CharacterBody3D, a RigidBody3D) rather than ground or a wall?
static func is_mover(collider: Object) -> bool:
	return collider is PhysicsBody3D and not (collider is StaticBody3D)


## The project's gravity (Unity: Physics.gravity).
static func gravity() -> Vector3:
	return ProjectSettings.get_setting("physics/3d/default_gravity_vector", Vector3.DOWN) \
			* float(ProjectSettings.get_setting("physics/3d/default_gravity", 9.8))


# --- materials ---------------------------------------------------------------------------------------------------

## Unlit, alpha blended, both faces, no depth write, no shadows: `texture` x the instance's `tint` (fade it with
## set_instance_shader_parameter(InsectFx.TINT, colour)). Unity: SpiderFx.AlphaMaterial (URP Particles/Unlit).
static func alpha_material(texture: Texture2D) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load(ALPHA_SHADER)
	if texture != null:
		m.set_shader_parameter("albedo_texture", texture)
	return m


## The snare's material: the orb web on the alpha material.
static func web_material() -> ShaderMaterial:
	if _web_material == null:
		_web_material = alpha_material(load(WEB_TEXTURE))
		_web_material.resource_name = "SpiderWeb"
	return _web_material


## The burrow hole's material: the hole texture on the alpha material.
static func hole_material() -> ShaderMaterial:
	if _hole_material == null:
		_hole_material = alpha_material(load(HOLE_TEXTURE))
		_hole_material.resource_name = "CentipedeHole"
	return _hole_material


## The silk thread's material: plain white on the alpha material (the tint gives it its colour).
static func thread_material() -> ShaderMaterial:
	if _thread_material == null:
		_thread_material = alpha_material(null)
		_thread_material.resource_name = "SpiderSilkLine"
	return _thread_material


## Wet, sticky silk for the glob: lit, off-white and fairly glossy. Unity: SpiderFx.SilkMaterial.
static func silk_material() -> StandardMaterial3D:
	if _silk_material == null:
		_silk_material = StandardMaterial3D.new()
		_silk_material.resource_name = "SpiderSilk"
		_silk_material.albedo_color = Color(0.9, 0.88, 0.8)
		_silk_material.roughness = 0.3                  # Unity smoothness 0.7
	return _silk_material


## Fresh dirt for the burrow's clods: lit, brown, matte. Unity: CentipedeBurrow's dirt material.
static func dirt_material() -> StandardMaterial3D:
	if _dirt_material == null:
		_dirt_material = StandardMaterial3D.new()
		_dirt_material.resource_name = "CentipedeDirt"
		_dirt_material.albedo_color = Color(0.36, 0.28, 0.19)
		_dirt_material.roughness = 0.95
	return _dirt_material


# --- meshes ------------------------------------------------------------------------------------------------------

## A lumpy ball of radius ~1 (scale it to the glob's or clod's size). Unity: SpiderFx.GlobMesh.
static func glob_mesh() -> ArrayMesh:
	if _glob != null:
		return _glob
	const LAT := 6
	const LON := 9
	var rng := RandomNumberGenerator.new()
	rng.seed = 3
	var v := PackedVector3Array()
	for i in LAT + 1:
		for j in LON:
			var th := PI * i / LAT
			var ph := TAU * j / LON
			var k := 1.0 if i == 0 or i == LAT else 0.85 + 0.3 * rng.randf()
			v.append(Vector3(sin(th) * cos(ph), cos(th), sin(th) * sin(ph)) * k)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for p in v:
		st.add_vertex(p)
	for i in LAT:
		for j in LON:
			var a := i * LON + j
			var b := i * LON + (j + 1) % LON
			var c := (i + 1) * LON + j
			var d := (i + 1) * LON + (j + 1) % LON
			for idx in [a, c, b, b, c, d]:          # Unity's order turned round (Godot's front faces wind the other way)
				st.add_index(idx)
	st.generate_normals()
	_glob = st.commit()
	_glob.resource_name = "FX_Glob"
	return _glob


## A square of side 2 in the XZ plane facing +Y (a radius-1 disc for a round texture). Unity: SpiderFx.DiscMesh.
static func square_mesh() -> PlaneMesh:
	if _square == null:
		_square = PlaneMesh.new()
		_square.size = Vector2(2, 2)
	return _square


## Makes `mi` (already in the tree) a flat square lying on a surface for a web or a hole: `normal` up, turned at
## random about it, lifted `lift` off it, unlit through `material`, no shadows. Its size is then its basis scale
## (1 = radius 1 m). Unity: the FX_Disc renderers.
static func splat(mi: MeshInstance3D, material: Material, at: Vector3, normal: Vector3, lift: float) -> void:
	mi.mesh = square_mesh()
	mi.material_override = material
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	var up := normal.normalized() if normal.length_squared() > 1e-4 else Vector3.UP
	var side := up.cross(Vector3.RIGHT if absf(up.x) < 0.9 else Vector3.FORWARD).normalized()
	side = side.rotated(up, randf() * TAU)
	mi.global_transform = Transform3D(Basis(side, up, side.cross(up)).orthonormalized(), at + up * lift)


# --- textures made in code (baked to PNGs; setup/bake_fx_textures.gd) ---------------------------------------------

## Off-white orb web on transparent: 18 slightly irregular spokes and a sagging spiral, fading at the rim.
## Unity: SpiderFx.WebTexture.
static func web_image(size := 256) -> Image:
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var rng := RandomNumberGenerator.new()
	rng.seed = 5
	const SPOKES := 18
	var ang := PackedFloat32Array()
	for i in SPOKES:
		ang.append((i + rng.randf() * 0.35 - 0.17) * TAU / SPOKES)
	var pix := 2.0 / size                                           # one texel in the -1..1 square
	var gap := TAU / SPOKES
	for y in size:
		for x in size:
			var dx := (x + 0.5) / size * 2.0 - 1.0
			var dy := (y + 0.5) / size * 2.0 - 1.0
			var r := sqrt(dx * dx + dy * dy)
			var a := atan2(dy, dx)
			if a < 0.0:
				a += TAU
			var best := 10.0
			for s in ang:
				best = minf(best, absf(angle_difference(a, s)))
			var spoke_dist := best * r                                 # distance to the nearest spoke, in the square
			var spoke := clampf(1.4 - spoke_dist / (pix * 0.9), 0.0, 1.0)
			# spiral: straight threads between spokes sag toward the centre
			var sag := 1.0 - 0.07 * sin(clampf(best / (gap * 0.5), 0.0, 1.0) * PI * 0.5)
			var rr := r / sag
			var turns := rr / 0.075 + a / TAU
			var ring := absf(turns - roundf(turns)) * 0.075
			var spiral := clampf(1.3 - ring / (pix * 0.85), 0.0, 1.0) * (1.0 if rr > 0.12 else 0.0)
			var hub := clampf(1.0 - r / 0.1, 0.0, 1.0) * 0.55
			var fade := clampf((0.98 - r) / 0.1, 0.0, 1.0)
			var alpha := clampf(maxf(spoke, maxf(spiral * 0.85, hub)), 0.0, 1.0) * fade
			var shade := (215 + rng.randi_range(0, 29)) / 255.0
			img.set_pixel(x, y, Color(shade, shade, shade - 12.0 / 255.0, alpha))
	return img


## A soft dark hole with a ring of pale churned dirt round it. Unity: CentipedeBurrow.HoleTexture.
static func hole_image(size := 128) -> Image:
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var rng := RandomNumberGenerator.new()
	rng.seed = 9
	var dark := Color(0.06, 0.045, 0.03)
	var dirt := Color(0.42, 0.33, 0.22)
	for y in size:
		for x in size:
			var dx := (x + 0.5) / size * 2.0 - 1.0
			var dy := (y + 0.5) / size * 2.0 - 1.0
			var a := atan2(dy, dx)
			var r := sqrt(dx * dx + dy * dy) * (1.0 + 0.08 * sin(a * 5.0) + 0.05 * sin(a * 11.0 + 1.0))
			var hole := clampf((0.55 - r) / 0.15, 0.0, 1.0)
			var rim := clampf(1.0 - absf(r - 0.72) / 0.2, 0.0, 1.0) * (0.7 + 0.3 * rng.randf())
			var alpha := clampf(maxf(hole, rim * 0.85), 0.0, 1.0) * clampf((1.0 - r) / 0.12, 0.0, 1.0)
			var c := dirt.lerp(dark, hole)
			c.a = alpha
			img.set_pixel(x, y, c)
	return img
