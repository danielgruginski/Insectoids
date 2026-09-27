"""Rebuild the giant centipede from scratch: body -> rig -> UVs and texture -> clips. Run inside Blender with the
Centipede scene on screen (bug_scene.show_scene first, in a separate call)."""
import bpy, importlib
import bug_common, bug_scene, spider_body, bug_rig, spider_paint, centipede_body, centipede_paint, centipede_anim, bug_export

RIG = centipede_anim.RIG


def reload_all():
    for m in (bug_common, bug_scene, spider_body, bug_rig, spider_paint, centipede_body, centipede_paint, centipede_anim,
              bug_export):
        importlib.reload(m)


def build_all(tex=1024, clips=True):
    bug_scene.setup_scene("Centipede", prefix="CEN_", lift=0.0)
    body = centipede_body.build_body()
    report = {"tris": centipede_body.tri_report(body)}
    rig = bug_rig.build_armature(centipede_body.rest_bones(), name=RIG, coll_name="CEN_Rig")
    report["texture"], report["coverage"] = centipede_paint.build_texture(body, size=tex)
    report["weights"] = bug_rig.bind(body, rig)
    if clips:
        acts = centipede_anim.build_clips()
        report["clips"] = {n: (int(a["frames"]), {k[6:]: a[k] for k in a.keys() if k.startswith("event_")})
                           for n, a in acts.items()}
        centipede_anim.clear()
    rig.data.display_type = 'STICK'
    return report


def export():
    return ([bug_export.export_model(centipede_anim, RIG, ["CentipedeBody"], "Centipede")] +
            bug_export.export_clips(centipede_anim, RIG, "Centipede", moving={"Walk", "Run", "Burrow", "Emerge"}))
