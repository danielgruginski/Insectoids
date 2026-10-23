"""Armature for the insectoids (Unity Generic rig) and the pose math the clips are keyed with.

The bone table comes from the creature module (spider_body.rest_bones()): name -> (head, frame, length, parent,
deform). Clips are not posed through constraints: each frame, the animation code computes where every bone should
be (armature space) and `apply_pose` converts that to matrix_basis and keys it. Nothing needs baking on export.
"""
import bpy, math
from mathutils import Vector, Matrix, Quaternion
from bug_common import get_coll, remove_obj

RIG = "SpiderRig"


def build_armature(table, name=RIG, coll_name="SPD_Rig"):
    coll = get_coll(coll_name)
    remove_obj(name)
    ad = bpy.data.armatures.get(name)
    if ad is not None and ad.users == 0:
        bpy.data.armatures.remove(ad)
    ad = bpy.data.armatures.new(name)
    ad.display_type = 'OCTAHEDRAL'
    ob = bpy.data.objects.new(name, ad)
    coll.objects.link(ob)
    ob.show_in_front = True
    vl = bpy.context.view_layer
    for o in bpy.context.selected_objects:
        o.select_set(False)
    vl.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    eb = ad.edit_bones
    for n, (h, fr, L, par, deform) in table.items():
        b = eb.new(n)
        b.head = h
        b.tail = h + fr.col[1] * L
        b.align_roll(fr.col[2])
        b.use_deform = deform or n.startswith("Socket_")      # sockets export as (unweighted) deform bones
    for n, (h, fr, L, par, deform) in table.items():
        if par:
            eb[n].parent = eb[par]
            eb[n].use_connect = False
    bpy.ops.object.mode_set(mode='OBJECT')
    cols = {c: ad.collections.new(c) for c in ("Body", "Legs", "Mouth", "Sockets")}
    for b in ad.bones:
        n = b.name
        if n.startswith("Socket_"):
            cols["Sockets"].assign(b)
            b.color.palette = 'THEME09'
        elif n.startswith("Leg"):
            cols["Legs"].assign(b)
            b.color.palette = 'THEME03' if "L" in n[3:4] else 'THEME04'
        elif n.startswith(("Chel", "Fang", "Palp")):
            cols["Mouth"].assign(b)
            b.color.palette = 'THEME06'
        else:
            cols["Body"].assign(b)
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return ob


def bind(mesh, rig):
    """Parent with an Armature modifier; the vertex groups (named after bones) are already on the mesh."""
    for m in [m for m in mesh.modifiers if m.type == 'ARMATURE']:
        mesh.modifiers.remove(m)
    mesh.parent = rig
    mesh.matrix_parent_inverse = rig.matrix_world.inverted()
    mod = mesh.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    return weight_report(mesh)


def weight_report(ob):
    zero = sum(1 for v in ob.data.vertices if sum(g.weight for g in v.groups) < 1e-4)
    over = sum(1 for v in ob.data.vertices if len(v.groups) > 4)
    return {"verts": len(ob.data.vertices), "unweighted": zero, "over4": over, "groups": len(ob.vertex_groups)}


# ----------------------------------------------------------------------------------------- pose math
def rest(rig):
    return {b.name: b.matrix_local.copy() for b in rig.data.bones}


def to_basis(rig, desired, R=None):
    """Armature-space matrices for some bones -> matrix_basis for every bone. Bones not in `desired` keep their
    rest pose relative to their parent."""
    R = R or rest(rig)
    world = {}
    basis = {}
    for b in sorted(rig.data.bones, key=lambda b: len(b.parent_recursive)):     # parents before children
        n = b.name
        if b.parent is None:
            parent_now = Matrix.Identity(4)
            rel = R[n]
        else:
            p = b.parent.name
            parent_now = world[p]
            rel = R[p].inverted() @ R[n]
        if n in desired:
            world[n] = desired[n]
            basis[n] = (parent_now @ rel).inverted() @ desired[n]
        else:
            world[n] = parent_now @ rel
            basis[n] = Matrix.Identity(4)
    return basis, world


def apply_pose(rig, desired, frame=None, R=None, keys=True, scaled=()):
    """scaled: bones whose scale is posed and keyed too (the broodmother's swelling abdomen, her laid egg); every other
    bone keeps scale 1 and gets no scale keys."""
    basis, world = to_basis(rig, desired, R)
    for n, m in basis.items():
        pb = rig.pose.bones[n]
        loc, rot, sca = m.decompose()
        pb.location = loc
        q = rot
        if keys and frame is not None and pb.rotation_quaternion.dot(q) < 0:
            q = -q                      # keep quaternions on one hemisphere so the curves don't flip
        pb.rotation_quaternion = q
        pb.scale = sca if n in scaled else (1, 1, 1)
        if keys and frame is not None:
            pb.keyframe_insert("location", frame=frame, group=n)
            pb.keyframe_insert("rotation_quaternion", frame=frame, group=n)
            if n in scaled:
                pb.keyframe_insert("scale", frame=frame, group=n)
    return world


def reset_pose(rig):
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def frame_matrix(head, frame3):
    return Matrix.Translation(Vector(head)) @ frame3.to_4x4()
