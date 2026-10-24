class_name SpiderWebGlob
extends Node3D
## A glob of silk in flight (SpiderWebSpit.spit lobs it): ballistic, wobbling, trailing a silk thread back to the
## spinnerets. At the first collider it meets (or, with no collider under its aim point, as it falls through the
## height it was aimed at) it bursts into a SpiderWebSnare; one that hits something moving (a CharacterBody3D or
## RigidBody3D: the prey) lays its web on the ground under it, round its feet. The thread then drops toward the web
## and fades. Lives under FX_Insectoids and frees itself. Unity: SpiderWebGlob (pooled there; here made per spit and
## freed; Unity's lies on whatever it hit, the prey's collider included).

## the spider's spitter (the thread starts at its spinnerets while it lives)
var spitter: SpiderWebSpit
var velocity := Vector3.ZERO
var size := 0.16
var radius := 1.3
var seconds := 8.0

var _age := 0.0
var _fade := -1.0                       # >= 0: landed, the thread fading
var _floor_y := -INF                    # no colliders under the aim: land as it falls through this height
var _start := Vector3.ZERO              # the thread's ends
var _end := Vector3.ZERO
var _skip: Array = []                   # the spider (its own colliders)
var _ball: MeshInstance3D
var _thread: MeshInstance3D
var _lines: ImmediateMesh

const THREAD_COLOR := Color(0.95, 0.94, 0.88, 0.85)


## Lob one from `from` at `vel` (aimed at `aim`); sizes in metres, already scaled to the spider.
static func launch(by: SpiderWebSpit, from: Vector3, vel: Vector3, aim: Vector3, glob_size: float, snare_radius: float,
		snare_seconds: float) -> SpiderWebGlob:
	var g := SpiderWebGlob.new()
	g.name = "FX_WebGlob"
	g.spitter = by
	g.velocity = vel
	g.size = glob_size
	g.radius = snare_radius
	g.seconds = snare_seconds
	g._skip = [by.creature] if by.creature != null else []
	InsectFx.container(by).add_child(g)
	g.global_position = from
	g._build(by)
	if InsectFx.ray(g, aim + Vector3.UP, aim + Vector3.DOWN * 50.0, g._skip).is_empty():
		g._floor_y = aim.y
	g._start = from
	g._end = from
	g._draw_thread()
	return g


func _build(by: SpiderWebSpit) -> void:
	_ball = MeshInstance3D.new()
	_ball.name = "FX_Glob"
	_ball.mesh = InsectFx.glob_mesh()
	_ball.material_override = by.silk_material if by.silk_material != null else InsectFx.silk_material()
	_ball.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_ball.scale = Vector3.ONE * size
	add_child(_ball)
	_lines = ImmediateMesh.new()
	_thread = MeshInstance3D.new()
	_thread.name = "FX_SilkThread"
	_thread.mesh = _lines
	_thread.top_level = true                        # its vertices are in world space
	_thread.material_override = by.thread_material if by.thread_material != null else InsectFx.thread_material()
	_thread.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_thread.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	add_child(_thread)
	_thread.global_transform = Transform3D.IDENTITY
	_thread.set_instance_shader_parameter(InsectFx.TINT, THREAD_COLOR)


func _thread_start() -> Vector3:
	return spitter.origin() if is_instance_valid(spitter) and spitter.is_inside_tree() else _end


func _process(delta: float) -> void:
	_age += delta
	if _fade >= 0.0:                                # landed: the thread sags toward the web and fades
		_fade += delta / 0.6
		_start = _start.lerp(_end, minf(1.0, delta * 2.0))
		var c := THREAD_COLOR
		c.a *= maxf(0.0, 1.0 - _fade)
		_thread.set_instance_shader_parameter(InsectFx.TINT, c)
		_draw_thread()
		if _fade >= 1.0:
			queue_free()
		return
	velocity += InsectFx.gravity() * delta
	var p := global_position
	var step := velocity * delta
	var hit := InsectFx.ray(self, p, p + step + step.normalized() * 1e-3, _skip)
	if not hit.is_empty():
		if InsectFx.is_mover(hit["collider"]):     # the prey: its web goes on the ground round it
			var under := InsectFx.ground(self, hit["position"], 50.0, _skip + [hit["collider"]])
			if not under.is_empty():
				hit = under
			else:                                       # nothing under it to lie on: at its feet' height
				var feet: Vector3 = hit["position"]
				feet.y = (hit["collider"] as Node3D).global_position.y
				hit = {"position": feet, "normal": Vector3.UP}
		_land(hit["position"], hit["normal"])
		return
	if velocity.y < 0.0 and p.y + step.y <= _floor_y:   # no collider there: the ground is where it was aimed
		var k := clampf((p.y - _floor_y) / maxf(-step.y, 1e-6), 0.0, 1.0)
		_land(p + step * k, Vector3.UP)
		return
	p += step
	global_position = p
	if p.y < -20.0 or _age > 6.0:
		_land(p, Vector3.UP)
		return
	var wob := 1.0 + 0.12 * sin(_age * 31.0)
	var dir := velocity.normalized() if velocity.length_squared() > 1e-4 else Vector3.BACK
	var up := Vector3.UP if absf(dir.dot(Vector3.UP)) < 0.999 else Vector3.RIGHT
	_ball.basis = Basis.looking_at(dir, up, true).scaled_local(Vector3(size * wob, size / wob, size * wob))
	_start = _thread_start()
	_end = p
	_draw_thread()


func _land(at: Vector3, normal: Vector3) -> void:
	var mat: Material = null
	if is_instance_valid(spitter) and spitter.web_material != null:
		mat = spitter.web_material
	var snare := SpiderWebSnare.spawn(self, spitter if is_instance_valid(spitter) else null, at, normal, radius, seconds, mat)
	if is_instance_valid(spitter):
		spitter.snared.emit(snare)
	_ball.visible = false
	global_position = at
	_start = _thread_start()
	_end = at
	_fade = 0.0
	_draw_thread()


## The thread: a flat ribbon between its ends, turned to face the camera (Unity: LineRenderer, View alignment).
func _draw_thread() -> void:
	_lines.clear_surfaces()
	var d := _end - _start
	if d.length_squared() < 1e-6:
		return
	var w := 0.035 * size / 0.16 * 0.5
	var cam := get_viewport().get_camera_3d() if get_viewport() != null else null
	var view := ((_start + _end) * 0.5 - cam.global_position) if cam != null else Vector3.DOWN
	var side := d.cross(view)
	if side.length_squared() < 1e-8:
		side = d.cross(Vector3.UP if absf(d.normalized().y) < 0.99 else Vector3.RIGHT)
	side = side.normalized() * w
	_lines.surface_begin(Mesh.PRIMITIVE_TRIANGLE_STRIP)
	_lines.surface_set_uv(Vector2(0, 0))
	_lines.surface_add_vertex(_start - side)
	_lines.surface_set_uv(Vector2(1, 0))
	_lines.surface_add_vertex(_start + side)
	_lines.surface_set_uv(Vector2(0, 1))
	_lines.surface_add_vertex(_end - side)
	_lines.surface_set_uv(Vector2(1, 1))
	_lines.surface_add_vertex(_end + side)
	_lines.surface_end()
