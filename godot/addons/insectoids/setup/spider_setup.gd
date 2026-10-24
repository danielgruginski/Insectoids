@tool
extends RefCounted
## The giant spider's scene extras (data/Spider.json "setup"; creature_builder.gd calls setup()): its web spit, a
## SpiderWebSpit on a BoneAttachment3D on Socket_Spinneret ("Spinneret"). The Spit event of its WebSpit clip lobs the
## glob. Unity: SpiderSetup (SpiderCombat on Spider_Giant, M_Spider_Web / _Silk / _SilkThread: here the fx defaults).

const Util := preload("res://addons/insectoids/setup/insect_setup_util.gd")


static func setup(root: Creature, model: Node, _dir: String, _data: Dictionary) -> String:
	var spit := SpiderWebSpit.new()
	spit.name = "WebSpit"
	if Util.attach(root, model, "Socket_Spinneret", "Spinneret", spit) == null:
		return "no Socket_Spinneret: no web spit"
	return "web spit on Socket_Spinneret"
