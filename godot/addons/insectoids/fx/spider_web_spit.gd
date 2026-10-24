class_name SpiderWebSpit
extends Node3D
## The spider's web spit, on its spinnerets (a BoneAttachment3D on Socket_Spinneret; setup/spider_setup.gd puts it
## there). As the WebSpit clip passes its "Spit" event (0.67 s) a glob of silk is lobbed from here on a ballistic arc
## to `target`, else to the nearest node of the "spider_prey" group in front of the spider within spit_range, else to
## a point ahead; it trails a silk thread back to the spinnerets (SpiderWebGlob) and lands as a web on the ground
## (SpiderWebSnare) that holds whatever is inside it. Call spit() to lob one from a game's own AI. Hook damage and
## sound to the creature's creature_event (Bite, Strike, Spit, Dead). Unity: SpiderCombat (its web part; SpiderPrey
## is the group here).

## a glob lobbed: (where it left, where it was aimed)
signal spat(origin: Vector3, aim: Vector3)
## a glob landed and its web opened
signal snared(snare: SpiderWebSnare)

## what makes something a target (add a goblin, a sheep... to it)
const PREY_GROUP := &"spider_prey"

## the creature events that lob a glob (the clip's is "Spit")
@export var spit_events: PackedStringArray = ["Spit", "WebSpit"]
## aim here when set
@export var target: Node3D
## without a target: aim at the nearest spider_prey in front of the spider (70 degrees either side), within spit_range
@export var auto_target := true
## metres, before the spider's scale
@export var spit_range := Vector2(4.0, 12.0)
## seconds of flight per metre of distance (plus a fixed 0.35 s): lower = a flatter, faster lob
@export var flight_per_metre := 0.06
## the glob's radius (metres, before the spider's scale)
@export var glob_size := 0.16
## the web's radius where it lands (metres, before the spider's scale)
@export var snare_radius := 1.3
@export var snare_seconds := 8.0
## the glob's material (empty: InsectFx.silk_material, lit off-white silk)
@export var silk_material: Material
## the web's material (empty: InsectFx.web_material; one with an instance uniform "tint" fades with the snare)
@export var web_material: Material
## the thread's material (empty: InsectFx.thread_material; instance uniform "tint" as above)
@export var thread_material: Material

var creature: Node3D


func _ready() -> void:
	creature = _creature()
	if creature != null and creature.has_signal("creature_event"):
		creature.connect("creature_event", _on_event)


func _creature() -> Node3D:
	var n := get_parent()
	while n != null and not (n is Creature):
		n = n.get_parent()
	return n as Node3D


func _on_event(_c: Node, event_name: String) -> void:
	if spit_events.has(event_name):
		spit()


## The spinnerets' position now (where globs leave and threads start).
func origin() -> Vector3:
	return global_position


## Lob a glob now: at `at` if given, else at the target / the nearest prey / a point ahead. Null outside a running
## game.
func spit(at: Variant = null) -> SpiderWebGlob:
	if not InsectFx.can_spawn(self):
		return null
	var from := origin()
	var aim: Vector3 = at if at is Vector3 else aim_point()
	var s := InsectFx.size_of(creature if creature != null else self)
	var dist := Vector2(from.x - aim.x, from.z - aim.z).length()
	var t := 0.35 + flight_per_metre * dist
	var v := (aim - from) / t - 0.5 * InsectFx.gravity() * t
	var glob := SpiderWebGlob.launch(self, from, v, aim, glob_size * s, snare_radius * s, snare_seconds)
	spat.emit(from, aim)
	return glob


## Where a glob would go now: the target, else the nearest prey ahead in range, else a random point ahead on the
## ground (or at the spider's feet' height when there is no collider under it).
func aim_point() -> Vector3:
	if is_instance_valid(target):
		return target.global_position
	var body: Node3D = creature if creature != null else self
	var s := InsectFx.size_of(body)
	var fwd := body.global_basis.z                     # the creatures' front is +Z (glTF's)
	fwd.y = 0.0
	fwd = fwd.normalized() if fwd.length_squared() > 1e-6 else Vector3.BACK
	if auto_target:
		var best: Node3D = null
		var best_d := INF
		for n in get_tree().get_nodes_in_group(PREY_GROUP):
			var p := n as Node3D
			if p == null or not p.is_visible_in_tree():
				continue
			var d := p.global_position - body.global_position
			d.y = 0.0
			var m := d.length()
			if m < spit_range.x * s or m > spit_range.y * s:
				continue
			if rad_to_deg(fwd.angle_to(d)) > 70.0:
				continue
			if m < best_d:
				best_d = m
				best = p
		if best != null:
			return best.global_position
	var ahead := body.global_position + fwd * randf_range(spit_range.x, spit_range.y) * s
	var hit := InsectFx.ground(self, ahead + Vector3.UP * 20.0, 40.0, [body])
	if not hit.is_empty():
		return hit["position"]
	return Vector3(ahead.x, body.global_position.y, ahead.z)
