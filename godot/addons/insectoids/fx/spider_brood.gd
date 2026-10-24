class_name SpiderBrood
extends Node3D
## The broodmother's end of her Spawn clip, on her spinnerets (a BoneAttachment3D on Socket_Spinneret;
## setup/broodmother_setup.gd puts it there). The clip squeezes an egg out of the spinnerets and sets it down; at
## that moment (event "Spawn", 3.0 s) the clip's egg shrinks away and this puts `spawn_scene` (an egg prop,
## SpiderEgg_Single.tscn, or a spiderling, Spiderling.tscn) on the ground under the socket, turned like the mother, as
## a sibling of the mother. Hook `spawned` for gameplay (hatching, AI). Unity: SpiderBrood.

## (the new egg or spiderling)
signal spawned(node: Node3D)

## what the Spawn event puts down: SpiderEgg_Single.tscn, or Spiderling.tscn
@export var spawn_scene: PackedScene
## scale it with the mother's size roll (the egg in her clip is hers)
@export var match_scale := true
## the oldest one goes when there would be more than this many (0 = no limit)
@export var max_alive := 6
## seconds before a spawned one is removed (0 = keep)
@export var lifetime := 30.0

var creature: Node3D
var _alive: Array[Node3D] = []


func _ready() -> void:
	var n := get_parent()
	while n != null and not (n is Creature):
		n = n.get_parent()
	creature = n as Node3D
	if creature != null and creature.has_signal("creature_event"):
		creature.connect("creature_event", _on_event)


func _on_event(_c: Node, event_name: String) -> void:
	if event_name == "Spawn":
		spawn()


## Put one down now, under the spinnerets; null outside a running game or without a scene.
func spawn() -> Node3D:
	if not InsectFx.can_spawn(self) or spawn_scene == null:
		return null
	for i in range(_alive.size() - 1, -1, -1):              # gone already (their lifetime, or the game's doing)
		if not is_instance_valid(_alive[i]) or _alive[i].is_queued_for_deletion():
			_alive.remove_at(i)
	if max_alive > 0 and _alive.size() >= max_alive:
		_alive.pop_front().queue_free()
	var mother: Node3D = creature if creature != null else self
	var p := global_position
	var ground := mother.global_position.y                 # no collider below: the mother's feet level
	var hit := InsectFx.ground(self, p + Vector3.UP * 0.5, 6.0, [mother])
	if not hit.is_empty():
		ground = hit["position"].y
	var go := spawn_scene.instantiate() as Node3D
	var host: Node = mother.get_parent() if mother.get_parent() != null else InsectFx.container(self)
	host.add_child(go, true)                               # a Creature (a spiderling) rolls its own size here
	var yaw := mother.global_rotation.y + deg_to_rad(12.0)  # Unity: the mother's yaw - 12 (its yaw turns the other way)
	var k := go.scale * (InsectFx.size_of(mother) if match_scale else 1.0)
	go.global_transform = Transform3D(Basis(Vector3.UP, yaw).scaled_local(k), Vector3(p.x, ground, p.z))
	_alive.append(go)
	if lifetime > 0.0:
		var t := Timer.new()                               # on the egg itself: it goes even if the mother does first
		t.name = "Lifetime"
		t.wait_time = lifetime
		t.one_shot = true
		t.autostart = true
		go.add_child(t)
		t.timeout.connect(go.queue_free)
	spawned.emit(go)
	return go
