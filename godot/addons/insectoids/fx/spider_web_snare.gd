class_name SpiderWebSnare
extends MeshInstance3D
## A splat of web where a glob landed: a flat square of the orb-web texture lying on what it hit, unlit. It slaps
## open to `radius` with a little overshoot, holds for its duration and fades over the last 1.5 s. Gameplay hook:
## the spitter's `snared` signal fires once per snare, `all` lists the live ones and is_snared() tells whether a point
## is inside any of them (slow or root units there). Lives under FX_Insectoids and frees itself. Unity:
## SpiderWebSnare (pooled there; a flat disc as here, so it lies flat on uneven ground, as in Unity).

## every live snare
static var all: Array[SpiderWebSnare] = []

## the spider's spitter that made it (null if it died)
var spitter: SpiderWebSpit
var radius := 1.3
## 1 while it holds, falling to 0 as it fades
var strength := 1.0

var _age := 0.0
var _duration := 8.0


## Open one at `at` on a surface facing `normal` (material null: InsectFx.web_material()).
static func spawn(from: Node, by: SpiderWebSpit, at: Vector3, normal: Vector3, snare_radius: float, snare_seconds: float,
		material: Material = null) -> SpiderWebSnare:
	var s := SpiderWebSnare.new()
	s.spitter = by
	s.radius = snare_radius
	s._duration = snare_seconds
	s.name = "FX_WebSnare"
	InsectFx.container(from).add_child(s)
	InsectFx.splat(s, material if material != null else InsectFx.web_material(), at, normal, 0.02)
	s._apply()
	all.append(s)
	return s


## Is the point inside a live snare (flat distance, the inner 90 %, while it still holds)?
static func is_snared(p: Vector3) -> bool:
	for s in all:
		var d := p - s.global_position
		d.y = 0.0
		if d.length_squared() <= s.radius * s.radius * 0.8 and s.strength > 0.3:
			return true
	return false


func _exit_tree() -> void:
	all.erase(self)


func _process(delta: float) -> void:
	_age += delta
	_apply()
	if _age >= _duration:
		queue_free()


func _apply() -> void:
	var open := clampf(_age / 0.18, 0.0, 1.0)
	var k := 1.0 + 0.12 * sin(open * PI)                # a little overshoot as it slaps open
	var b := basis.orthonormalized()
	basis = b.scaled_local(Vector3.ONE * radius * lerpf(0.2, 1.0, open) * k)
	var fade_start := _duration - 1.5
	strength = 1.0 if _age < fade_start else clampf(1.0 - (_age - fade_start) / 1.5, 0.0, 1.0)
	set_instance_shader_parameter(InsectFx.TINT, Color(1, 1, 1, 0.95 * strength))
