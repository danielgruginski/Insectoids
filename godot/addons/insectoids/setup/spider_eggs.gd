@tool
extends RefCounted
## The spider-egg props (static, no rig) from the exports in res://insectoids/SpiderEggs/: SpiderEgg_Clutch.glb,
## _Single.glb, _Hatched.glb (origin on the ground under the middle, one material) become SpiderEgg_Clutch.tscn,
## SpiderEgg_Single.tscn (the broodmother's Spawn puts this one down) and SpiderEgg_Hatched.tscn: the model (a plain
## reference to its .glb) under a Creature root that only puts M_SpiderEggs.tres on it (the creatures' coat shader on
## T_SpiderEggs.png, smoothness from its alpha) at size 1.
## broodmother_setup.gd builds them with her; build() alone remakes them. Unity: SpiderEggsSetup.

const DIR := "res://insectoids/SpiderEggs/"
const NAMES := ["SpiderEgg_Clutch", "SpiderEgg_Single", "SpiderEgg_Hatched"]
const COAT := "res://addons/beasts/shaders/creature_coat.gdshader"


static func build() -> String:
	var tex_path := DIR + "T_SpiderEggs.png"
	if not ResourceLoader.exists(tex_path):
		return "eggs: no %s (install the exports first)" % tex_path
	var mat := ShaderMaterial.new()
	mat.resource_name = "SpiderEggs"
	mat.shader = load(COAT)
	mat.set_shader_parameter("coat", load(tex_path))
	mat.set_shader_parameter("tint", Color.WHITE)
	mat.set_shader_parameter("smoothness", 1.0)
	var mat_path := DIR + "M_SpiderEggs.tres"
	ResourceSaver.save(mat, mat_path)
	mat.take_over_path(mat_path)
	var made := PackedStringArray()
	for egg: String in NAMES:
		var glb := DIR + egg + ".glb"
		if not ResourceLoader.exists(glb):
			made.append(egg + " (no .glb)")
			continue
		var root := Creature.new()                      # only for its material on the model (one skin, size 1)
		root.name = egg
		var model := (load(glb) as PackedScene).instantiate()
		model.name = "Model"
		root.add_child(model)
		model.owner = root
		var mesh := model.find_child(egg, true, false) as MeshInstance3D
		if mesh == null:
			mesh = model.find_child("*", true, false) as MeshInstance3D
		if mesh != null:
			root.target = root.get_path_to(mesh)
			var one: Array[Material] = [mat]
			root.skins = one
		root.scale_range = Vector2.ONE
		var packed := PackedScene.new()
		var err := packed.pack(root)
		if err == OK:
			err = ResourceSaver.save(packed, DIR + egg + ".tscn")
		root.free()
		made.append("%s (%s)" % [egg, error_string(err)])
	return "eggs: " + ", ".join(made)
