@tool
extends RefCounted
## Shared by the insects' setup scripts (data/<Name>.json "setup"; creature_builder.gd calls their setup() on the
## scene before saving it). Unity: InsectSetupUtil.


## A BoneAttachment3D named `node_name` on the model's bone `bone` (a socket; creature_builder.gd's attach(): under
## the root, following the bone as an external skeleton), and `component` under it at the socket (placed `offset` in
## the socket's frame). Null when the rig has no such bone.
static func attach(root: Node, model: Node, bone: String, node_name: String, component: Node3D,
		offset := Transform3D.IDENTITY) -> BoneAttachment3D:
	var att: BoneAttachment3D = load("res://addons/beasts/build/creature_builder.gd").attach(root, model, bone, node_name)
	if att == null:
		component.free()
		return null
	att.add_child(component)
	component.owner = root
	component.transform = offset
	return att
