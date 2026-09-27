"""Rebuild the giant spider from scratch: body -> rig -> UVs -> painted texture -> clips. Run inside Blender with the
Spider scene on screen."""
import bpy, importlib
import bug_common, bug_scene, spider_body, bug_rig, spider_paint, spider_anim


def reload_all():
    for m in (bug_common, bug_scene, spider_body, bug_rig, spider_paint, spider_anim):
        importlib.reload(m)


def build_all(tex=1024, clips=True, variants=("hunter", "pale")):
    bug_scene.setup_scene("Spider")
    body = spider_body.build_body()
    rig = bug_rig.build_armature(spider_body.rest_bones())
    report = {"weights": bug_rig.bind(body, rig), "tris": spider_body.tri_report(body)}
    spider_paint.unwrap(body)
    report["uv_layout"] = spider_paint.uv_layout(body)
    report["textures"], report["coverage"] = spider_paint.build_texture(body, size=tex, variants=variants)
    if clips:
        report["clips"] = {n: int(a["frames"]) for n, a in spider_anim.build_clips().items()}
        spider_anim.clear()
    return report
