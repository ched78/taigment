"""Prévisualisations des crins (Cycles CPU) et tests de déformation.

- Charge le corps (vrai `body.blend` si présent, sinon corps provisoire en cache) et l'armature PonyRig,
  puis ajoute les pièces depuis `Pipeline/build/parts/<id>.blend` (modificateurs Armature reciblés sur PonyRig).
- Couleurs d'aperçu : albedo calculé depuis hair_strands.png avec la formule de référence de
  `hair_texture.strands_to_albedo` (brun, puis « lavé » = crins clairs), seuil alpha 0.4 (comme `opacityThreshold`).
- Poses de test : encolure baissée (brouter), tête levée, queue relevée.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from . import conventions as cv
from . import hair as hair_mod
from . import hair_surface as hs
from . import hair_texture as htex
from . import template

PREVIEW_DIR = cv.PREVIEW_DIR / "hair"
SCRATCH = cv.BUILD_DIR / "hair_cache" / "preview"

COAT = {"brown": (0.085, 0.036, 0.014), "flaxen": (0.20, 0.068, 0.022)}   # bai / alezan, linéaire (aperçu) [A]


# ----------------------------------------------------------------------------------------------
# Scène
# ----------------------------------------------------------------------------------------------
def setup_scene(prefer_real=True, samples=24, resolution=(480, 480)):
    import bpy

    from . import render, rig

    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = rig.build_armature()
    J = hs.joints_from_armature(arm)
    if prefer_real and hs.body_available():
        _surf, body = hs.load_body_from_blend(link_into_scene=True)
        kind = "real"
        body.parent = arm
        mod = next((m for m in body.modifiers if m.type == "ARMATURE"), None) or body.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        # retire d'éventuelles armatures importées avec le corps
        for o in list(bpy.data.objects):
            if o.type == "ARMATURE" and o is not arm:
                bpy.data.objects.remove(o, do_unlink=True)
        # les clés de forme restent à 0 (pose de liaison)
    else:
        surf, d = hair_mod.provisional_surface(J, arm)
        me = bpy.data.meshes.new("Body")
        me.from_pydata(np.asarray(d["V"]).tolist(), [], np.asarray(d["F"]).tolist())
        me.update()
        me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
        body = bpy.data.objects.new("Body", me)
        bpy.context.scene.collection.objects.link(body)
        W = np.asarray(d["W"])
        for n in template.JOINT_NAMES:
            body.vertex_groups.new(name=n)
        for j, n in enumerate(template.JOINT_NAMES):
            idx = np.nonzero(W[:, j] > 0)[0]
            g = body.vertex_groups[n]
            for i in idx:
                g.add([int(i)], float(W[i, j]), "REPLACE")
        body.parent = arm
        mod = body.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        kind = "provisional"
    coat = bpy.data.materials.new("PreviewCoat")
    coat.use_nodes = True
    bsdf = coat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.55
    body.data.materials.clear()
    body.data.materials.append(coat)
    scene = render.setup_stage(engine="CYCLES", samples=samples, resolution=resolution)
    scene.cycles.transparent_max_bounces = 48
    scene.view_settings.exposure = -0.5
    scene.cycles.max_bounces = 6
    arm.hide_render = True
    return arm, body, kind


def load_parts(part_ids, arm):
    """Ajoute les pièces (objets `<id>`) et les recible sur l'armature de la scène. Matériau M_Hair unique."""
    import bpy

    objs = {}
    for pid in part_ids:
        path = str(hair_mod.PARTS_DIR / f"{pid}.blend")
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.objects = [pid]
        ob = dst.objects[0]
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = arm
        for m in ob.modifiers:
            if m.type == "ARMATURE":
                m.object = arm
        objs[pid] = ob
    for o in list(bpy.data.objects):
        if o.type == "ARMATURE" and o is not arm:
            bpy.data.objects.remove(o, do_unlink=True)
    mat = _preview_hair_material()
    for ob in objs.values():
        ob.data.materials.clear()
        ob.data.materials.append(mat)
    return objs


def _albedo_image(color_key):
    import bpy

    name = f"hair_albedo_{color_key}"
    if name in bpy.data.images:
        return bpy.data.images[name]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    path = SCRATCH / f"{name}.png"
    if not path.exists():
        from PIL import Image

        st = np.asarray(Image.open(hair_mod.TEX_DIR / "hair_strands.png")).astype(np.float64) / 255.0
        col, tip, amt = htex.HAIR_COLORS[color_key]
        htex.save_png(htex.strands_to_albedo(st, col, tip, amt), path)
    img = bpy.data.images.load(str(path))
    img.name = name
    img.alpha_mode = "STRAIGHT"
    return img


def _preview_hair_material():
    """M_Hair d'aperçu : albedo (couleur choisie) + alpha seuillé à 0.4 (équivalent opacityThreshold)."""
    import bpy

    mat = bpy.data.materials.new("M_Hair_preview")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = "HairAlbedo"
    tex.image = _albedo_image("brown")
    tex.interpolation = "Cubic"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = htex.MATERIAL_HINTS["opacityThreshold"]
    nt.links.new(tex.outputs["Alpha"], gt.inputs[0])
    nt.links.new(gt.outputs[0], bsdf.inputs["Alpha"])
    timg = bpy.data.images.load(str(hair_mod.TEX_DIR / "hair_normal.png"), check_existing=True)
    timg.colorspace_settings.name = "Non-Color"
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = timg
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.6
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = htex.MATERIAL_HINTS["roughness"]
    bsdf.inputs["Specular IOR Level"].default_value = htex.MATERIAL_HINTS["specular"]
    bsdf.inputs["Anisotropic"].default_value = 0.0      # pas de tangente fiable en aperçu
    mat.use_backface_culling = False
    return mat


def set_colors(color_key):
    import bpy

    mat = bpy.data.materials["M_Hair_preview"]
    mat.node_tree.nodes["HairAlbedo"].image = _albedo_image(color_key)
    coat = bpy.data.materials["PreviewCoat"]
    coat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*COAT[color_key], 1.0)


# ----------------------------------------------------------------------------------------------
# Caméras
# ----------------------------------------------------------------------------------------------
def camera(az_deg, el_deg, target, distance, lens=50.0):
    """Azimut 0 = côté gauche du poney (caméra en x < 0), 90 = arrière, 180 = droite, -90 = avant."""
    import bpy
    from mathutils import Vector

    cam = bpy.data.objects["PreviewCamera"]
    cam.data.lens = lens
    a, e = math.radians(az_deg), math.radians(el_deg)
    d = Vector((-math.cos(a) * math.cos(e), -math.sin(a) * math.cos(e), math.sin(e)))
    t = Vector(target)
    cam.location = t + d * distance
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_start = 0.01
    return cam


# vues par pièce : (nom, azimut, élévation, cible, distance)
def _views_for(pid, J):
    neck = (0.0, 0.62, 1.30)
    head = tuple(np.array(J["head"][0]) + np.array([0, 0.10, -0.06]))
    tail = (0.0, -0.88, 0.80)
    if pid.startswith("mane"):
        return [("left", 0, 6, neck, 2.4), ("right", 180, 6, neck, 2.4), ("3q", -35, 18, neck, 2.4),
                ("back", 130, 25, neck, 2.4), ("close", 205, 12, (0.03, 0.70, 1.38), 0.9)]
    if pid.startswith("forelock"):
        return [("left", 0, 5, head, 0.9), ("right", 180, 5, head, 0.9), ("3q", -45, 15, head, 0.9),
                ("front", -90, 12, head, 0.9), ("close", -70, 25, head, 0.55)]
    if pid.startswith("tail"):
        return [("left", 0, 5, tail, 2.0), ("right", 180, 5, tail, 2.0), ("3q", 45, 15, tail, 2.0),
                ("back", 90, 8, tail, 2.0), ("close", 60, 18, (0.0, -0.86, 1.02), 0.8)]
    if pid == "feathers":
        f = (-0.11, 0.0, 0.16)
        return [("left", 0, 8, f, 2.2), ("right", 180, 8, (0.11, 0.0, 0.16), 2.2),
                ("3q", -30, 15, (-0.11, 0.2, 0.16), 1.8), ("back", 90, 10, (0.0, -0.55, 0.14), 1.4),
                ("close", 30, 10, (-0.115, 0.40, 0.12), 0.5)]
    raise KeyError(pid)


def render_still(path):
    import bpy

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path


# ----------------------------------------------------------------------------------------------
# Poses de test
# ----------------------------------------------------------------------------------------------
POSES = {
    # rotations locales autour de l'axe X local (degrés) ; + = relève l'os (Y local vers Z local)
    "graze": {"neck_01": -38, "neck_02": -22, "neck_03": -12, "neck_04": -6, "head": 18},
    "head_up": {"neck_03": 6, "neck_04": 10, "neck_05": 12, "neck_06": 10, "head": 22},
    "tail_up": {"tail_01": -35, "tail_02": -25, "tail_03": -18, "tail_04": -12, "tail_05": -8},
    "rest": {},
}


def apply_pose(arm, pose: dict):
    from mathutils import Matrix

    from . import rig

    L = rig.locals_from_world(rig.rest_world_b(arm), to_rk=False)
    names = rig.joint_names()
    for n, deg in pose.items():
        i = names.index(n)
        L[i] = L[i] @ np.array(Matrix.Rotation(math.radians(deg), 4, "X"))
    rig.apply_local_pose(arm, L)
    import bpy

    bpy.context.view_layer.update()


def stretch_report(objs):
    """Étirement des arêtes entre pose de repos et pose courante (rapport max / p99), par pièce."""
    import bpy

    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for pid, ob in objs.items():
        me = ob.data
        n = len(me.vertices)
        rest = np.empty(n * 3)
        me.vertices.foreach_get("co", rest)
        rest = rest.reshape(-1, 3)
        ev = ob.evaluated_get(dg).to_mesh()
        cur = np.empty(n * 3)
        ev.vertices.foreach_get("co", cur)
        cur = cur.reshape(-1, 3)
        ob.evaluated_get(dg).to_mesh_clear()
        e = np.empty(len(me.edges) * 2, np.int64)
        me.edges.foreach_get("vertices", e)
        e = e.reshape(-1, 2)
        l0 = np.linalg.norm(rest[e[:, 0]] - rest[e[:, 1]], axis=1)
        l1 = np.linalg.norm(cur[e[:, 0]] - cur[e[:, 1]], axis=1)
        r = l1 / np.maximum(l0, 1e-9)
        out[pid] = {"max": float(r.max()), "min": float(r.min()), "p99": float(np.percentile(r, 99)),
                    "p01": float(np.percentile(r, 1))}
    return out


def posed_penetration(objs, body, sample=4):
    """Sommets de crins sous la peau du corps posé (BVH du corps évalué) — hors racines (≤ 4 mm)."""
    import bpy
    from mathutils.bvhtree import BVHTree

    dg = bpy.context.evaluated_depsgraph_get()
    bev = body.evaluated_get(dg)
    bvh = BVHTree.FromObject(bev, dg)
    out = {}
    for pid, ob in objs.items():
        ev = ob.evaluated_get(dg).to_mesh()
        n = len(ev.vertices)
        co = np.empty(n * 3)
        ev.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        ob.evaluated_get(dg).to_mesh_clear()
        deep = 0
        for p in co[::sample]:
            loc, nn, fi, d = bvh.find_nearest(p.tolist())
            if loc is None:
                continue
            sd = (np.array(p) - np.array(loc)) @ np.array(nn)
            if sd < -0.004:
                deep += 1
        out[pid] = {"checked": len(co[::sample]), "deeper_than_4mm": deep}
    return out


# ----------------------------------------------------------------------------------------------
# Planches
# ----------------------------------------------------------------------------------------------
def render_part_previews(part_ids, colors=("brown", "flaxen"), out_dir=PREVIEW_DIR, views=None, prefer_real=True,
                         samples=24, resolution=(480, 480), companions=None, sheet=True, log=print):
    """Rend chaque pièce seule sur le corps (vues profil gauche/droit, 3/4, arrière/face, gros plan) pour chaque
    couleur, et assemble une planche par pièce `<out_dir>/<id>.png`. Renvoie {id: [chemins]}."""
    from . import render

    arm, body, kind = setup_scene(prefer_real, samples, resolution)
    J = hs.joints_from_armature(arm)
    objs = load_parts(part_ids, arm)
    out = {}
    for pid in part_ids:
        for o_id, o in objs.items():
            o.hide_render = o_id != pid and not (companions and o_id in companions.get(pid, ()))
        paths, labels = [], []
        for col in colors:
            set_colors(col)
            for (vn, az, el, tgt, dist) in _views_for(pid, J):
                if views and vn not in views:
                    continue
                camera(az, el, tgt, dist)
                p = render_still(SCRATCH / "renders" / f"{pid}_{col}_{vn}.png")
                paths.append(p)
                labels.append(f"{pid} {col} {vn}")
        if sheet and paths:
            n_per = len(paths) // len(colors)
            render.contact_sheet(paths, Path(out_dir) / f"{pid}.png", cols=n_per, labels=labels)
        out[pid] = paths
        log(f"[hair] aperçus {pid} ({kind}) : {len(paths)} images")
    return out, kind
