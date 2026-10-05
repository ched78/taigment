"""Construction de l'armature Blender à partir du gabarit, et extraction des transformations.

Conventions (Docs/SPEC.md §1) :
- armature à l'origine, transform identité ; os en mètres, déformants ;
- roulis des os : axe X local = droite du poney (+X monde) projeté perpendiculairement à l'os ;
- transformations locales parent->enfant identiques en Blender et RealityKit, sauf `root` (C · L).
"""
from __future__ import annotations

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import conventions as cv
from . import template

ARMATURE_NAME = "PonyRig"


def build_armature(name: str = ARMATURE_NAME, wh: float = template.REFERENCE_WH, collection=None):
    """Crée (ou remplace) l'armature du poney et la renvoie (objet actif, en mode objet)."""
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    arm_data = bpy.data.armatures.new(name)
    arm_data.display_type = "OCTAHEDRAL"
    obj = bpy.data.objects.new(name, arm_data)
    (collection or bpy.context.scene.collection).objects.link(obj)
    # view_layer.objects peut contenir des entrées None tant que la vue n'est pas mise à jour
    # (objets juste créés) : on met à jour puis on ignore les entrées vides.
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    ebs = arm_data.edit_bones
    xw = np.array([1.0, 0.0, 0.0])
    for e in template.joint_table(wh):
        eb = ebs.new(e["name"])
        eb.head = Vector(e["head"])
        eb.tail = Vector(e["tail"])
        d = np.array(e["tail"]) - np.array(e["head"])
        d /= np.linalg.norm(d)
        z = np.cross(xw, d)
        if np.linalg.norm(z) < 1e-4:
            z = np.array([0.0, 0.0, 1.0])
        eb.align_roll(Vector(z / np.linalg.norm(z)))
        eb.use_deform = True
        eb.use_connect = False
    for e in template.joint_table(wh):
        if e["parent"]:
            ebs[e["name"]].parent = ebs[e["parent"]]
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def joint_names() -> list[str]:
    return list(template.JOINT_NAMES)


def _np(m: Matrix) -> np.ndarray:
    return np.array(m, dtype=np.float64)


def rest_world_b(arm) -> np.ndarray:
    """(N,4,4) repères de repos des joints en espace armature Blender (= monde, armature à l'identité)."""
    return np.stack([_np(arm.data.bones[n].matrix_local) for n in joint_names()])


def bind_world_rk(arm) -> np.ndarray:
    """(N,4,4) bindTransforms USD (monde RealityKit)."""
    return np.stack([cv.world_frame_b2rk(m) for m in rest_world_b(arm)])


def _parents() -> list[int]:
    idx = {n: i for i, n in enumerate(joint_names())}
    return [-1 if e["parent"] is None else idx[e["parent"]] for e in template.joint_table()]


PARENTS = _parents()


def locals_from_world(world: np.ndarray, to_rk: bool = True) -> np.ndarray:
    """Transformations locales (N,4,4) à partir de repères monde Blender (N,4,4)."""
    out = np.empty_like(world)
    for i, p in enumerate(PARENTS):
        if p < 0:
            out[i] = cv.root_local_b2rk(world[i]) if to_rk else world[i]
        else:
            out[i] = np.linalg.inv(world[p]) @ world[i]
    return out


def rest_local_rk(arm) -> np.ndarray:
    return locals_from_world(rest_world_b(arm))


def pose_world_b(arm) -> np.ndarray:
    """(N,4,4) repères posés (pose courante évaluée) en espace armature Blender."""
    return np.stack([_np(arm.pose.bones[n].matrix) for n in joint_names()])


def pose_local_rk(arm) -> np.ndarray:
    return locals_from_world(pose_world_b(arm))


def apply_local_pose(arm, local_b: np.ndarray):
    """Applique des transformations locales Blender (N,4,4) aux pose bones (matrix_basis)."""
    rest_w = rest_world_b(arm)
    rest_l = locals_from_world(rest_w, to_rk=False)
    for i, n in enumerate(joint_names()):
        pb = arm.pose.bones[n]
        basis = np.linalg.inv(rest_l[i]) @ local_b[i]
        pb.matrix_basis = Matrix(basis.tolist())


def decompose(m: np.ndarray):
    """4x4 -> (t[3], q[x,y,z,w], s[3]) ; suppose pas de cisaillement."""
    mm = Matrix(np.asarray(m).tolist())
    t, q, s = mm.decompose()
    return (np.array(t), np.array([q.x, q.y, q.z, q.w]), np.array(s))


def make_bone_proxies(arm, radius: float = 0.018, name: str = "BoneProxies"):
    """Mesh de visualisation (un prisme par os, poids rigides) pour prévisualiser les animations
    avant que le corps n'existe. Renvoie l'objet mesh (avec modificateur Armature)."""
    import bmesh

    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    me = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    bm = bmesh.new()
    groups = {}
    vert_groups = []
    for bi, n in enumerate(joint_names()):
        b = arm.data.bones[n]
        h = np.array(b.head_local)
        t = np.array(b.tail_local)
        d = t - h
        L = np.linalg.norm(d)
        d /= L
        a = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = np.cross(d, a)
        u /= np.linalg.norm(u)
        v = np.cross(d, u)
        r = min(radius, 0.25 * L + 0.004)
        mid = h + d * (0.2 * L)
        ring = [mid + r * (np.cos(k * np.pi / 2) * u + np.sin(k * np.pi / 2) * v) for k in range(4)]
        vh = bm.verts.new(h)
        vt = bm.verts.new(t)
        vr = [bm.verts.new(p) for p in ring]
        for k in range(4):
            bm.faces.new((vh, vr[k], vr[(k + 1) % 4]))
            bm.faces.new((vt, vr[(k + 1) % 4], vr[k]))
        groups[n] = bi
        vert_groups += [n] * 6
    bm.to_mesh(me)
    bm.free()
    for n in joint_names():
        obj.vertex_groups.new(name=n)
    for vi, n in enumerate(vert_groups):
        obj.vertex_groups[n].add([vi], 1.0, "REPLACE")
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    return obj
