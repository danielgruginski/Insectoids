extends SceneTree
## Bakes the insects' effect textures made in code (InsectFx.web_image, hole_image) to the PNGs the effects load,
## beside fx/insect_fx.gd: T_SpiderWeb.png (256) and T_BurrowHole.png (128). They ship with the addon, so this is only
## for changing them; run --import afterwards:
##   godot --headless --path <project> --script res://addons/insectoids/setup/bake_fx_textures.gd
## Unity: SpiderSetup / CentipedeSetup writing T_Spider_Web.png and T_Centipede_Hole.png.


func _initialize() -> void:
	for pair in [[InsectFx.WEB_TEXTURE, InsectFx.web_image()], [InsectFx.HOLE_TEXTURE, InsectFx.hole_image()]]:
		var err := (pair[1] as Image).save_png(ProjectSettings.globalize_path(pair[0]))
		print("BAKE %s: %s" % [pair[0], error_string(err)])
	quit()
