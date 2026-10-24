class_name CentipedeBurrow
extends Node3D
## The centipede's burrow, on its mouth (a BoneAttachment3D on Socket_Mouth; setup/centipede_setup.gd puts it there).
## Its Burrow and Emerge clips raise "Burrow" / "Emerge" as the head crosses the ground: this opens a dark hole there
## (it stays hole_seconds, then fades) and throws out a burst of dirt clods. Between the two the centipede is
## underground (`underground`; untargetable in a game) while CreatureWanderer's Burrow pool relocates it 3-8 m before
## the Emerge. `burrowed` / `emerged` give the hole's position for gameplay. Unity: CentipedeBurrow (holes and clods
## pooled there; made per burrow here and freed).

signal burrowed(at: Vector3)
signal emerged(at: Vector3)

## the hole's look (empty: InsectFx.hole_material(), the baked hole texture; an instance uniform "tint" fades it)
@export var hole_material: Material
## the clods' material (empty: InsectFx.dirt_material())
@export var dirt_material: Material
## metres, before the centipede's scale
@export var hole_radius := 0.55
@export var hole_seconds := 6.0
@export var clods := 12

var underground := false
var creature: Node3D


func _ready() -> void:
	var n := get_parent()
	while n != null and not (n is Creature):
		n = n.get_parent()
	creature = n as Node3D
	if creature != null and creature.has_signal("creature_event"):
		creature.connect("creature_event", _on_event)


func _on_event(_c: Node, event_name: String) -> void:
	if event_name == "Burrow" or event_name == "Emerge":
		dig(event_name == "Burrow")


## A hole and a burst of dirt under the mouth now (going under, or coming up); returns where.
func dig(going_under: bool) -> Vector3:
	underground = going_under
	var p := global_position
	var body: Node3D = creature if creature != null else self
	var at := p
	var normal := Vector3.UP
	var hit := InsectFx.ground(self, p + Vector3.UP * 3.0, 10.0, [body])
	if not hit.is_empty():
		at = hit["position"]
		normal = hit["normal"]
	else:
		at.y = body.global_position.y                  # no collider: the ground is at its feet
	if InsectFx.can_spawn(self):
		var s := InsectFx.size_of(body)
		Hole.open(self, at, normal, hole_radius * s, hole_seconds, hole_material if hole_material != null else InsectFx.hole_material())
		Dirt.burst(self, at, clods, 0.09 * s, dirt_material if dirt_material != null else InsectFx.dirt_material())
	if going_under:
		burrowed.emit(at)
	else:
		emerged.emit(at)
	return at


## The hole: a flat square of the hole texture on the ground that opens fast, stays, and fades over its last 1.5 s.
class Hole extends MeshInstance3D:
	var age := 0.0
	var life := 6.0
	var radius := 0.55

	static func open(from: Node, at: Vector3, normal: Vector3, r: float, seconds: float, material: Material) -> void:
		var h := Hole.new()
		h.name = "FX_BurrowHole"
		h.life = seconds
		h.radius = r
		InsectFx.container(from).add_child(h)
		InsectFx.splat(h, material, at, normal, 0.015)
		h._apply()

	func _process(delta: float) -> void:
		age += delta
		_apply()
		if age >= life:
			queue_free()

	func _apply() -> void:
		var t := clampf(age / 0.25, 0.0, 1.0)                # opens fast, easing out
		var k := radius * lerpf(0.3, 1.0, 1.0 - (1.0 - t) * (1.0 - t))
		basis = basis.orthonormalized().scaled_local(Vector3.ONE * k)
		set_instance_shader_parameter(InsectFx.TINT, Color(1, 1, 1, clampf((life - age) / 1.5, 0.0, 1.0)))


## The dirt thrown out: lumpy clods flying up and out, tumbling, shrinking away as they fall.
class Dirt extends Node3D:
	var age := 0.0
	var _clods: Array[MeshInstance3D] = []
	var _vel: Array[Vector3] = []
	var _spin: Array[Vector3] = []
	var _size := PackedFloat32Array()
	var _floor := 0.0

	static func burst(from: Node, at: Vector3, n: int, size: float, material: Material) -> void:
		var d := Dirt.new()
		d.name = "FX_Dirt"
		d._floor = at.y - 1.0
		InsectFx.container(from).add_child(d)
		for i in n:
			var c := MeshInstance3D.new()
			c.name = "FX_Clod"
			c.mesh = InsectFx.glob_mesh()
			c.material_override = material
			c.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
			d.add_child(c)
			var a := randf() * TAU
			var out := randf_range(1.2, 2.8)
			d._vel.append(Vector3(cos(a) * out, randf_range(2.5, 4.5), sin(a) * out))
			var spin := Vector3(randf_range(-1, 1), randf_range(-1, 1), randf_range(-1, 1)).limit_length(1.0)
			d._spin.append(spin * deg_to_rad(540.0))
			var sz := size * randf_range(0.6, 1.4)
			d._size.append(sz)
			c.global_transform = Transform3D(Basis.from_scale(Vector3.ONE * sz), at + Vector3(cos(a), 0.3, sin(a)) * 0.15)
			d._clods.append(c)

	func _process(delta: float) -> void:
		age += delta
		var g := InsectFx.gravity()
		var shrink := clampf(1.0 - (age - 0.9) / 0.4, 0.001, 1.0) if age > 0.9 else 1.0
		for i in _clods.size():
			var c := _clods[i]
			_vel[i] += g * delta
			var b := c.global_basis.orthonormalized()
			var w := _spin[i]
			if w.length_squared() > 1e-8:
				b = Basis(w.normalized(), w.length() * delta) * b
			c.global_transform = Transform3D(b.scaled_local(Vector3.ONE * _size[i] * shrink), c.global_position + _vel[i] * delta)
			if c.global_position.y < _floor:
				c.visible = false
		if age > 1.3:
			queue_free()
