"""Rebuild the giant wasp from scratch: body + wings -> rig -> UVs and textures -> join -> clips. Run inside Blender
with the Wasp scene on screen (bug_scene.show_scene first, in a separate call)."""
import bpy, importlib
import bug_common, bug_scene, spider_body, bug_rig, spider_paint, wasp_body, wasp_paint, wasp_anim, bug_export

RIG = wasp_anim.RIG


def reload_all():
    for m in (bug_common, bug_scene, spider_body, bug_rig, spider_paint, wasp_body, wasp_paint, wasp_anim, bug_export):
        importlib.reload(m)


def join(target, other):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    other.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.join()
    return target


def build_all(tex=1024, clips=True):
    bug_scene.setup_scene("Wasp", prefix="WSP_", lift=1.2)
    body, wings = wasp_body.build_body()
    report = {"tris": wasp_body.tri_report([body, wings])}
    rig = bug_rig.build_armature(wasp_body.rest_bones(), name=RIG, coll_name="WSP_Rig")
    report["textures"], report["coverage"] = wasp_paint.build_textures(body, wings, size=tex)
    wing_mesh = wings.data
    body = join(body, wings)                      # one skinned mesh, two materials (shells, wings)
    if wing_mesh.users == 0:
        bpy.data.meshes.remove(wing_mesh)
    stray = [g.name for g in body.vertex_groups if "." in g.name]
    assert not stray, f"vertex groups that match no bone: {stray}"
    report["weights"] = bug_rig.bind(body, rig)
    report["materials"] = [m.name for m in body.data.materials]
    if clips:
        report["clips"] = {n: int(a["frames"]) for n, a in wasp_anim.build_clips().items()}
        wasp_anim.clear()
    rig.data.display_type = 'STICK'
    return report


def export():
    return ([bug_export.export_model(wasp_anim, RIG, ["WaspBody"], "Wasp")] +
            bug_export.export_clips(wasp_anim, RIG, "Wasp", moving={"Fly"}))
