"""Puts the Godot exports (export/godot/<Name>/, src/bug_gdx.py) into the creatures pack's Godot project, as
install_to_unity.ps1 does for Unity (the Beasts repo's tools/install_to_godot.py makes the project and its Beasts addon,
which builds the scenes; run that one first):

    py tools/install_to_godot.py [Spider Wasp ...]     (default: everything in export/godot)

- the project (E:/Unity/Godot/GameArtGeneration/creatures, or CREATURES_GODOT) is made if missing: Godot 4.7, GDScript
  only, Forward+, the Beasts addon enabled;
- addons/insectoids is a directory junction to this repo's godot/addons/insectoids (its creatures' data/*.json and
  effects; edited here, never in the project);
- res://insectoids/<Name>/ gets the .glb (its .import runs addons/beasts/import/creature_import.gd), the clips JSON and
  the textures (VRAM compressed with mipmaps).
Then in Godot: Project > Tools > Beasts: Build Creature Scenes (or build/build_cli.gd headless).
"""
import os, sys, shutil, filecmp, subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "export", "godot")
PROJECT = os.environ.get("CREATURES_GODOT", r"E:\Unity\Godot\GameArtGeneration\creatures")
ADDON = os.path.join(REPO, "godot", "addons", "insectoids")

PROJECT_GODOT = """; Engine configuration file.
; It's best edited using the editor UI and not directly,
; since the parameters that go here are not all obvious.

config_version=5

[application]

config/name="Creatures"
config/description="Rigged, animated creatures (CC0): the Beasts and Insectoids packs for Godot."
config/features=PackedStringArray("4.7", "Forward Plus")

[display]

window/size/viewport_width=1600
window/size/viewport_height=900

[editor_plugins]

enabled=PackedStringArray("res://addons/beasts/plugin.cfg")

[rendering]

anti_aliasing/quality/msaa_3d=2
"""

GLB_IMPORT = """[remap]

importer="scene"
importer_version=1
type="PackedScene"

[params]

nodes/root_type=""
nodes/root_name=""
nodes/apply_root_scale=true
nodes/root_scale=1.0
meshes/ensure_tangents=true
meshes/generate_lods=false
meshes/create_shadow_meshes=true
meshes/light_baking=1
skins/use_named_skins=true
animation/import=true
animation/fps=30
animation/trimming=false
animation/remove_immutable_tracks=true
animation/import_rest_as_RESET=false
import_script/path="res://addons/beasts/import/creature_import.gd"
gltf/naming_version=2
gltf/embedded_image_handling=0
"""

TEX_IMPORT = """[remap]

importer="texture"
type="CompressedTexture2D"

[params]

compress/mode=2
compress/high_quality=true
compress/lossy_quality=0.7
compress/normal_map=%d
compress/channel_pack=0
mipmaps/generate=true
mipmaps/limit=-1
process/fix_alpha_border=true
process/premult_alpha=false
process/normal_map_invert_y=false
process/size_limit=0
detect_3d/compress_to=0
"""


def write_if_changed(path, text):
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else None
    if old is not None and "uid=" in old:            # keep the uid Godot gave the file
        uid = next(l for l in old.splitlines() if l.startswith("uid="))
        text = text.replace('type="', uid + '\ntype="', 1) if uid not in text else text
    if old != text:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def junction(link, target):
    if os.path.exists(link):
        return
    os.makedirs(os.path.dirname(link), exist_ok=True)
    try:
        import _winapi
        _winapi.CreateJunction(target, link)
    except (ImportError, OSError):
        subprocess.run(["cmd", "/c", "mklink", "/J", link, target], check=True)


def main(names):
    os.makedirs(PROJECT, exist_ok=True)
    if not os.path.exists(os.path.join(PROJECT, "project.godot")):
        raise SystemExit("no Godot project at %s: run the Beasts repo's tools/install_to_godot.py first" % PROJECT)
    junction(os.path.join(PROJECT, "addons", "insectoids"), ADDON)
    names = names or sorted(os.listdir(SRC))
    for name in names:
        src, dst = os.path.join(SRC, name), os.path.join(PROJECT, "insectoids", name)
        os.makedirs(dst, exist_ok=True)
        n = 0
        for fn in sorted(os.listdir(src)):
            a, b = os.path.join(src, fn), os.path.join(dst, fn)
            if not os.path.exists(b) or not filecmp.cmp(a, b, shallow=False):
                shutil.copy2(a, b)
                n += 1
            if fn.endswith(".glb"):
                write_if_changed(b + ".import", GLB_IMPORT)
            elif fn.endswith(".png"):
                write_if_changed(b + ".import", TEX_IMPORT % (1 if fn.endswith("_Normal.png") else 0))
        print(f"INSTALL {name}: {n} files copied -> {dst}")


if __name__ == "__main__":
    main(sys.argv[1:])
