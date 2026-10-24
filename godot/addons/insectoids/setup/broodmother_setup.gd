@tool
extends RefCounted
## The broodmother's scene extras (data/Broodmother.json "setup"; creature_builder.gd calls setup()): first the egg
## props (spider_eggs.gd: SpiderEgg_Clutch / _Single / _Hatched.tscn), then her brood, a SpiderBrood on a
## BoneAttachment3D on Socket_Spinneret ("Spinneret") that puts SpiderEgg_Single down at her Spawn event. Unity:
## BroodmotherSetup (SpiderBrood on Spider_Broodmother; SpiderEggsSetup.MakePrefabs when her egg is missing).

const Util := preload("res://addons/insectoids/setup/insect_setup_util.gd")
const Eggs := preload("res://addons/insectoids/setup/spider_eggs.gd")


static func setup(root: Creature, model: Node, _dir: String, _data: Dictionary) -> String:
	var eggs := Eggs.build()
	var brood := SpiderBrood.new()
	brood.name = "Brood"
	var egg_path := Eggs.DIR + "SpiderEgg_Single.tscn"
	if ResourceLoader.exists(egg_path):
		brood.spawn_scene = ResourceLoader.load(egg_path, "", ResourceLoader.CACHE_MODE_REPLACE)
	if Util.attach(root, model, "Socket_Spinneret", "Spinneret", brood) == null:
		return "no Socket_Spinneret: no brood; " + eggs
	return "brood on Socket_Spinneret, spawns %s; %s" % [
			brood.spawn_scene.resource_path.get_file() if brood.spawn_scene != null else "NOTHING (no egg scene)", eggs]
