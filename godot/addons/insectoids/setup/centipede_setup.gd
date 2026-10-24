@tool
extends RefCounted
## The giant centipede's scene extras (data/Centipede.json "setup"; creature_builder.gd calls setup()): its burrow, a
## CentipedeBurrow on a BoneAttachment3D on Socket_Mouth ("Mouth"). The Burrow and Emerge events open the holes;
## CreatureWanderer's Burrow pool moves it 3-8 m underground in between. Unity: CentipedeSetup (CentipedeBurrow on
## Centipede_Giant, M_Centipede_Hole / _Dirt: here the fx defaults).

const Util := preload("res://addons/insectoids/setup/insect_setup_util.gd")


static func setup(root: Creature, model: Node, _dir: String, _data: Dictionary) -> String:
	var burrow := CentipedeBurrow.new()
	burrow.name = "Burrow"
	if Util.attach(root, model, "Socket_Mouth", "Mouth", burrow) == null:
		return "no Socket_Mouth: no burrow"
	return "burrow on Socket_Mouth"
