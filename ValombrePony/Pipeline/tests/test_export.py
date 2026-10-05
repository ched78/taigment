"""Test de bout en bout de l'export (étape 9) sur données SYNTHÉTIQUES, indépendant des autres agents.

Lancement :  python3 Pipeline/tests/test_export.py        (≈ 1 min ; aussi compatible pytest)

Ce que le test construit dans Pipeline/build/test_export/in/ :
- `rigged_body.blend` : `rig.build_armature()` (70 joints) + mesh `Body` (un tube par os : quads + bouchons
  en n-gones, UV en atlas, poids lissés entre os voisins jusqu'à 6 influences -> limitation continue à 4),
  2 shape keys (`shape_fat` dense, `head_short` creuse), matériau `M_Coat` texturé (albedo sRGB, normal map
  via nœud Normal Map, ORM via Separate Color) ; mesh `Eyes` (sphères liées rigidement à eye_l/eye_r, M_Eye) ;
- `parts/saddle_english.blend` : copie de l'armature + selle (patch sur le dos, 2 matériaux slot_primary
  texturé / slot_metal -> GeomSubsets, shape key `shape_fat` ; les coins, loin des os, n'ont volontairement
  aucun poids -> chemin « sommets sans poids liés à root ») + le corps présent dans le fichier (doit être
  ignoré) ; `parts/mane_natural.blend` : cartes de crinière à alpha, matériau `M_Hair` + propriété
  `opacityThreshold` (comme l'agent « hair » : alias -> slot_primary), sans shape key, à facettes (repli
  normales lissées) ;
- `clips/walk.npz` (boucle, tout le corps + poids `body_breathe`) et `clips/head_shake.npz` (masque
  `upper_body`) ; `textures/coat_*.png` (7 cartes du SPEC §4) ; `morphology.json`.
Puis `s09_export.run(...)` vers Pipeline/build/test_export/out/ et vérifie que TOUT passe (ARKit, UsdValidation,
structure/noms, skinning numérique sur 3 poses ≤ 1e-4 m, aller-retour PonyClips.bin, PonyRig.json, tailles).
Contrôles négatifs : le validateur doit ÉCHOUER sur un USD volontairement corrompu, sur une référence de
skinning décalée de 1 mm, et sur un PonyClips.bin tronqué.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import sys
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from pony import conventions as cv  # noqa: E402
from pony import rig, template  # noqa: E402

ROOT = cv.BUILD_DIR / "test_export"
IN = ROOT / "in"
OUT = ROOT / "out"
SIGMA = 0.05
BODY_RINGS, BODY_SEG = 4, 8          # résolution des tubes du corps synthétique
EXTRA_BODY_SHAPES: list = []         # noms supplémentaires (test de charge) : décalages pseudo-aléatoires


# --------------------------------------------------------------------------------------------------
# Données synthétiques
# --------------------------------------------------------------------------------------------------


def _textures():
    t = IN / "textures"
    t.mkdir(parents=True, exist_ok=True)
    n = 64
    yy, xx = np.mgrid[0:n, 0:n] / (n - 1)
    alb = np.stack([0.45 + 0.1 * xx, 0.28 + 0.05 * yy, 0.15 + 0 * xx], -1)
    Image.fromarray((alb * 255).astype(np.uint8)).save(t / "coat_albedo_default.png")
    nx, ny = 0.15 * np.sin(6 * xx), 0.15 * np.cos(6 * yy)
    nz = np.sqrt(1 - nx ** 2 - ny ** 2)
    Image.fromarray(((np.stack([nx, ny, nz], -1) * 0.5 + 0.5) * 255).astype(np.uint8)).save(t / "coat_normal.png")
    orm = np.stack([np.full_like(xx, 0.9), 0.6 + 0.2 * yy, np.zeros_like(xx)], -1)
    Image.fromarray((orm * 255).astype(np.uint8)).save(t / "coat_orm.png")
    for fn, ch in (("coat_shading.png", 3), ("coat_regions.png", 4), ("coat_params.png", 4), ("coat_patterns.png", 4)):
        Image.fromarray((np.random.default_rng(len(fn)).random((32, 32, ch)) * 255).astype(np.uint8)).save(t / fn)
    gray = np.clip(0.75 + 0.2 * np.sin(20 * xx) * np.cos(9 * yy), 0, 1)
    Image.fromarray((gray * 255).astype(np.uint8)).convert("RGB").save(t / "leather_detail.png")
    a = np.clip(np.sin(np.pi * xx * 9) ** 2 * (1 - yy), 0, 1)
    Image.fromarray(np.stack([(gray * 255).astype(np.uint8)] * 3 + [(a * 255).astype(np.uint8)], -1), "RGBA").save(
        t / "mane_cards.png")


def _seg_dist(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab[None]), axis=1)


def _smooth_weights(pts, arm, own=None, candidates=None, top=6):
    names = template.JOINT_NAMES
    cand = candidates or names
    D = np.stack([_seg_dist(pts, np.array(arm.data.bones[n].head_local), np.array(arm.data.bones[n].tail_local))
                  for n in cand], 1)
    W = np.exp(-(D / SIGMA) ** 2)
    if own is not None:
        W[np.arange(len(pts)), [cand.index(o) for o in own]] *= 3.0
    order = np.argsort(-W, 1)[:, :top]
    out = []
    for i in range(len(pts)):
        row = [(cand[j], float(W[i, j])) for j in order[i] if W[i, j] > 1e-3]
        out.append(row)
    return out


def _assign_groups(obj, weights):
    for i, row in enumerate(weights):
        for n, w in row:
            vg = obj.vertex_groups.get(n) or obj.vertex_groups.new(name=n)
            vg.add([i], w, "REPLACE")


def _add_armature_mod(obj, arm):
    m = obj.modifiers.new("Armature", "ARMATURE")
    m.object = arm


def _image_node(nt, path, non_color):
    img = bpy.data.images.load(str(path))
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    return node


def _mat_coat():
    m = bpy.data.materials.new("M_Coat")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    t = IN / "textures"
    alb = _image_node(nt, t / "coat_albedo_default.png", False)
    nt.links.new(alb.outputs["Color"], bsdf.inputs["Base Color"])
    nrm = _image_node(nt, t / "coat_normal.png", True)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nrm.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    orm = _image_node(nt, t / "coat_orm.png", True)
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(orm.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    m.use_backface_culling = True
    return m


def _mat_simple(name, color, rough=0.5, metal=0.0, coat=0.0, image=None, alpha=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.05
    if image is not None:
        tx = _image_node(nt, image, False)
        nt.links.new(tx.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha:
            nt.links.new(tx.outputs["Alpha"], bsdf.inputs["Alpha"])
            m.blend_method = "CLIP"
            m.alpha_threshold = 0.4
    return m


def _mesh_from(name, verts, faces, uvs_per_loop=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update(calc_edges=True)
    me.validate()
    if uvs_per_loop is not None:
        uvl = me.uv_layers.new(name="UVMap")
        uvl.data.foreach_set("uv", np.asarray(uvs_per_loop, np.float32).ravel())
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    for p in me.polygons:
        p.use_smooth = True
    return obj


def build_body(arm):
    """Un tube par os (rings × seg quads + 2 bouchons n-gones)."""
    names = template.JOINT_NAMES
    rings, seg = BODY_RINGS, BODY_SEG
    verts, faces, uvs, owner = [], [], [], []
    for bi, n in enumerate(names):
        b = arm.data.bones[n]
        h, t = np.array(b.head_local), np.array(b.tail_local)
        d = t - h
        L = np.linalg.norm(d)
        d /= L
        a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
        u = np.cross(d, a); u /= np.linalg.norm(u)
        v = np.cross(d, u)
        r = min(0.035, 0.25 * L + 0.004)
        base = len(verts)
        for ri in range(rings):
            c = h + d * L * (0.08 + 0.84 * ri / (rings - 1))
            for si in range(seg):
                ang = 2 * math.pi * si / seg
                verts.append(c + r * (math.cos(ang) * u + math.sin(ang) * v))
                owner.append(n)
        col, row = bi % 9, bi // 9
        for ri in range(rings - 1):
            for si in range(seg):
                s2 = (si + 1) % seg
                f = [base + ri * seg + si, base + ri * seg + s2, base + (ri + 1) * seg + s2, base + (ri + 1) * seg + si]
                faces.append(f)
                uu = [si, si + 1, si + 1, si]
                vv = [ri, ri, ri + 1, ri + 1]
                uvs += [((col + 0.9 * x / seg) / 9, (row + 0.9 * y / (rings - 1)) / 8) for x, y in zip(uu, vv)]
        cap0 = [base + si for si in reversed(range(seg))]
        cap1 = [base + (rings - 1) * seg + si for si in range(seg)]
        for cap in (cap0, cap1):
            faces.append(cap)
            uvs += [((col + 0.45 + 0.4 * math.cos(2 * math.pi * k / seg) * 0.1) / 9,
                     (row + 0.45 + 0.4 * math.sin(2 * math.pi * k / seg) * 0.1) / 8) for k in range(seg)]
    verts = np.array(verts)
    obj = _mesh_from("Body", verts, faces, uvs)
    _assign_groups(obj, _smooth_weights(verts, arm, own=owner))
    obj.data.materials.append(_mat_coat())
    _add_armature_mod(obj, arm)
    # shape keys
    obj.shape_key_add(name="Basis", from_mix=False)
    me = obj.data
    me.update()
    vn = np.array([v.normal for v in me.vertices])
    k1 = obj.shape_key_add(name="shape_fat", from_mix=False)
    k1.data.foreach_set("co", (verts + 0.01 * vn).astype(np.float32).ravel())
    head_set = {"head", "jaw", "lip_lower", "lip_upper", "ear_l", "ear_r", "ear_tip_l", "ear_tip_r"}
    sel = np.array([o in head_set for o in owner])
    hd = np.array(arm.data.bones["head"].tail_local) - np.array(arm.data.bones["head"].head_local)
    hd /= np.linalg.norm(hd)
    co2 = verts.copy()
    co2[sel] -= 0.02 * hd
    k2 = obj.shape_key_add(name="head_short", from_mix=False)
    k2.data.foreach_set("co", co2.astype(np.float32).ravel())
    rng = np.random.default_rng(3)
    for n in EXTRA_BODY_SHAPES:
        sel = rng.random(len(verts)) < 0.3
        co3 = verts.copy()
        co3[sel] += 0.01 * vn[sel] * rng.random((int(sel.sum()), 1))
        obj.shape_key_add(name=n, from_mix=False).data.foreach_set("co", co3.astype(np.float32).ravel())
    return obj


def build_eyes(arm):
    objs = []
    for side in ("l", "r"):
        c = np.array(arm.data.bones[f"eye_{side}"].head_local)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=0.018, location=tuple(c))
        o = bpy.context.active_object
        o.name = f"eye_tmp_{side}"
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        vg = o.vertex_groups.new(name=f"eye_{side}")
        vg.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
        objs.append(o)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    eyes = bpy.context.active_object
    eyes.name = "Eyes"
    eyes.data.name = "Eyes"
    eyes.data.materials.clear()
    eyes.data.materials.append(_mat_simple("M_Eye", (0.08, 0.05, 0.03), rough=0.2, coat=1.0))
    bpy.ops.object.shade_smooth()
    _add_armature_mod(eyes, arm)
    return eyes


def build_saddle(arm):
    """Patch 12×8 au-dessus du dos (y ∈ [−0.15, 0.30]), 2 matériaux, shape key shape_fat."""
    nu, nv = 12, 8
    verts, uvs, faces = [], [], []
    for j in range(nv):
        for i in range(nu):
            y = -0.15 + 0.45 * i / (nu - 1)
            ang = math.radians(-70 + 140 * j / (nv - 1))
            z0 = 1.16 - 0.05 * (y - 0.07) ** 2 / 0.05
            verts.append((0.20 * math.sin(ang), y, z0 + 0.06 * math.cos(ang) - 0.02))
    for j in range(nv - 1):
        for i in range(nu - 1):
            a = j * nu + i
            faces.append([a, a + 1, a + nu + 1, a + nu])
            uvs += [(i / (nu - 1), j / (nv - 1)), ((i + 1) / (nu - 1), j / (nv - 1)),
                    ((i + 1) / (nu - 1), (j + 1) / (nv - 1)), (i / (nu - 1), (j + 1) / (nv - 1))]
    verts = np.array(verts)
    o = _mesh_from("Saddle", verts, faces, uvs)
    cand = ["spine_01", "spine_02", "spine_03", "stirrup_l", "stirrup_r"]
    _assign_groups(o, _smooth_weights(verts, arm, candidates=cand, top=3))
    o.data.materials.append(_mat_simple("slot_primary", (1, 1, 1), rough=0.55, image=IN / "textures" / "leather_detail.png"))
    o.data.materials.append(_mat_simple("slot_metal", (0.8, 0.8, 0.8), rough=0.25, metal=1.0))
    for p in o.data.polygons:
        p.material_index = 1 if (p.index % (nu - 1)) in (0, nu - 2) else 0
    _add_armature_mod(o, arm)
    o.shape_key_add(name="Basis", from_mix=False)
    k = o.shape_key_add(name="shape_fat", from_mix=False)
    co = verts.copy()
    co[:, 2] += 0.01
    k.data.foreach_set("co", co.astype(np.float32).ravel())
    return o


def build_mane(arm):
    """Cartes verticales le long de la crête (une par os mane_*)."""
    verts, faces, uvs, own = [], [], [], []
    for i in range(1, 7):
        b = arm.data.bones[f"mane_{i:02d}"]
        h = np.array(b.head_local)
        base = len(verts)
        for r in range(4):
            z = h[2] - 0.05 * r
            verts += [(h[0] + 0.012 * r, h[1] - 0.04, z), (h[0] + 0.012 * r, h[1] + 0.04, z)]
            own += [f"mane_{i:02d}"] * 2
        for r in range(3):
            a = base + 2 * r
            faces.append([a, a + 1, a + 3, a + 2])
            uvs += [(0, 1 - r / 3), (1, 1 - r / 3), (1, 1 - (r + 1) / 3), (0, 1 - (r + 1) / 3)]
    verts = np.array(verts, dtype=np.float64)
    o = _mesh_from("Mane", verts, faces, uvs)
    for p in o.data.polygons:          # à facettes : exerce le repli « normales lissées calculées »
        p.use_smooth = False
    cand = [f"mane_{i:02d}" for i in range(1, 7)] + [f"neck_{i:02d}" for i in range(1, 7)]
    _assign_groups(o, _smooth_weights(verts, arm, own=own, candidates=cand, top=4))
    # nommé comme chez l'agent « hair » (M_Hair + indication opacityThreshold) : exerce l'alias -> slot_primary
    m = _mat_simple("M_Hair", (1, 1, 1), rough=0.6, image=IN / "textures" / "mane_cards.png", alpha=True)
    m["opacityThreshold"] = 0.35
    o.data.materials.append(m)
    _add_armature_mod(o, arm)
    return o


def _clip_locals(arm, F, fn):
    rest_l = rig.locals_from_world(rig.rest_world_b(arm), to_rk=False)
    out = np.repeat(rest_l[None], F, 0)
    for f in range(F):
        for j, n in enumerate(template.JOINT_NAMES):
            rot = fn(f, n)
            if rot is None:
                continue
            ax, ang, tr = rot
            ax = np.asarray(ax, float) / np.linalg.norm(ax)
            c, s = math.cos(ang), math.sin(ang)
            K = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
            R = np.eye(4)
            R[:3, :3] = np.eye(3) + s * K + (1 - c) * K @ K
            R[:3, 3] = tr
            out[f, j] = rest_l[j] @ R
    return out


def build_clips(arm):
    d = IN / "clips"
    d.mkdir(parents=True, exist_ok=True)
    F = 32

    def walk(f, n):
        ph = 2 * math.pi * f / F
        legs = {"thigh_l": 0.0, "thigh_r": 0.5, "scapula_l": 0.25, "scapula_r": 0.75,
                "forearm_l": 0.25, "forearm_r": 0.75, "gaskin_l": 0.0, "gaskin_r": 0.5}
        if n in legs:
            return ((1, 0, 0), 0.35 * math.sin(ph + 2 * math.pi * legs[n]), (0, 0, 0))
        if n.startswith("tail_"):
            return ((0, 0, 1), 0.08 * math.sin(ph), (0, 0, 0))
        if n == "body":
            return ((1, 0, 0), 0.0, (0, 0, 0.01 * math.sin(2 * ph)))
        if n == "neck_02":
            return ((1, 0, 0), 0.06 * math.sin(2 * ph), (0, 0, 0))
        return None

    def shake(f, n):
        ph = 2 * math.pi * f / 23
        if n.startswith("neck_") or n == "head":
            return ((0, 0, 1), 0.25 * math.sin(3 * ph) * math.sin(math.pi * f / 23), (0, 0, 0))
        if n.startswith("ear_"):
            return ((1, 0, 0), 0.3, (0, 0, 0))
        return None

    lw = _clip_locals(arm, F, walk)
    meta = {"name": "walk", "loop": True, "fps": 30, "speed": 1.4, "rootYawRate": 0.0, "phaseOffset": 0.0,
            "events": [{"time": 0.0, "name": "foot_down_hl"}, {"frame": 8, "name": "foot_down_fl"},
                       {"frame": 16, "name": "foot_down_hr"}, {"frame": 24, "name": "foot_down_fr"}]}
    br = 0.5 + 0.5 * np.sin(2 * np.pi * np.arange(F) / F)
    np.savez(d / "walk.npz", local=lw, weights_names=np.array(["body_breathe"]), weights=br[:, None],
             meta=np.array(json.dumps(meta)))
    ls = _clip_locals(arm, 24, shake)
    meta = {"name": "head_shake", "loop": False, "fps": 30, "mask": "upper_body",
            "events": [{"time": 0.4, "name": "snort"}]}
    np.savez(d / "head_shake.npz", local=ls, meta=np.array(json.dumps(meta)))
    return lw, ls


def build_inputs():
    if ROOT.exists():
        shutil.rmtree(ROOT)          # dossier de test créé par ce script
    (IN / "parts").mkdir(parents=True, exist_ok=True)
    _textures()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = rig.build_armature()
    build_body(arm)
    build_eyes(arm)
    build_clips(arm)
    bpy.ops.wm.save_as_mainfile(filepath=str(IN / "rigged_body.blend"))
    # pièce : selle (le corps reste dans le fichier et doit être ignoré par l'export)
    sad = build_saddle(arm)
    bpy.ops.wm.save_as_mainfile(filepath=str(IN / "parts" / "saddle_english.blend"))
    # pièce : crinière seule
    for o in list(bpy.data.objects):
        if o.type == "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    del sad
    build_mane(arm)
    bpy.ops.wm.save_as_mainfile(filepath=str(IN / "parts" / "mane_natural.blend"))
    (IN / "morphology.json").write_text(json.dumps({"sliders": [
        {"id": "condition", "plus": "shape_fat", "minus": None, "jointOffsetsPlus": {"belly": [0.0, -0.01, 0.0]},
         "jointOffsetsMinus": {}}]}))


# --------------------------------------------------------------------------------------------------
# Test
# --------------------------------------------------------------------------------------------------


def _negative_controls(report):
    """Le validateur doit détecter des fautes injectées."""
    from pony import runtime_export as rx
    from pony import usd_writer as uw
    from pony import validate as val
    neg = {}
    # (1) USD corrompu : doubleSided=true, poids non triés, normal map sans bias, upAxis Z
    src = IN / "export" / "Pony" / "Pony.usda"
    txt = src.read_text()
    bad = txt.replace("uniform bool doubleSided = 0", "uniform bool doubleSided = 1")
    bad = bad.replace('upAxis = "Y"', 'upAxis = "Z"')
    bad = re.sub(r"float4 inputs:bias = \([^)]*\)", "float4 inputs:bias = (-1, -1, -1, -1)", bad)
    m = re.search(r"float\[\] primvars:skel:jointWeights = \[([^\]]*)\]", bad)
    w = [float(x) for x in m.group(1).split(",")]
    k = int(re.search(r"primvars:skel:jointWeights = .*?elementSize = (\d+)", bad, re.S).group(1))
    w[0:k] = w[0:k][::-1]
    bad = bad.replace(m.group(0), "float[] primvars:skel:jointWeights = [" + ", ".join(repr(x) for x in w) + "]")
    bdir = ROOT / "negative"
    if bdir.exists():
        shutil.rmtree(bdir)
    shutil.copytree(src.parent, bdir)
    (bdir / "Pony.usda").write_text(bad)
    uw.package_usdz(bdir / "Pony.usda", bdir / "Pony_bad.usdz")
    exp = report["_expect_body"]
    r = val.validate_usd(bdir / "Pony_bad.usdz", "body", exp, None)
    neg["corrupt_usd"] = {"ok": r["ok"], "arkit_failed": r["arkit"]["failed"][:3],
                          "usdValidation": r["usdValidation"]["issues"][:3], "structure": r["structure"]["errors"][:6]}
    # (2) référence de skinning décalée de 1 mm
    z = dict(np.load(IN / "export" / "skin_Pony.npz"))
    z["points__Body"] = z["points__Body"] + 1e-3
    np.savez(bdir / "skin_shifted.npz", **z)
    r2 = val.validate_usd(OUT / "Pony.usdz", "body", exp, bdir / "skin_shifted.npz")
    neg["shifted_reference"] = {"ok": r2["ok"], "skinning_pass": r2["skinning"]["pass"],
                                "maxErrorQuery": r2["skinning"]["maxErrorQuery"]}
    # (3) PonyClips.bin tronqué
    data = (OUT / "PonyClips.bin").read_bytes()
    (bdir / "trunc.bin").write_bytes(data[:-7])
    try:
        rx.read_clips_bin(bdir / "trunc.bin")
        neg["truncated_bin"] = "NON DÉTECTÉ"
    except Exception as e:  # noqa: BLE001
        neg["truncated_bin"] = f"détecté : {type(e).__name__}"
    return neg


def test_export_end_to_end():
    build_inputs()
    from stages import s09_export
    rep = s09_export.run(IN, OUT, quicklook=True, do_validate=True, glb=True)
    from pony import runtime_export as rx
    # attentes du corps pour les contrôles négatifs (reconstruites depuis le rapport de validation)
    bpy.ops.wm.open_mainfile(filepath=str(IN / "rigged_body.blend"))
    from pony import blender_extract as bx
    from pony import validate as val
    sk = bx.extract_skeleton(bx.find_armature())
    exp_body = dict(joints=sk.paths, bind=sk.bind_world, rest=sk.rest_local,
                    blendShapesAllowed=rx.BODY_BLEND_SHAPES, meshMaterials=val.BODY_MESH_MATERIALS,
                    requiredMeshes=["Body"], animation=False)
    rep["_expect_body"] = exp_body
    # cohérence des conventions : locales RK d'un clip (clip_locals_rk) == locales RK relues sur l'armature
    # Blender posée avec ce clip (rig.apply_local_pose -> rig.pose_local_rk)
    arm = bx.find_armature()
    walk_src = rx.load_clip_npz(IN / "clips" / "walk.npz")
    conv_err = 0.0
    for f in (0, 5, 17):
        rig.apply_local_pose(arm, walk_src.local_b[f])
        bpy.context.view_layer.update()
        conv_err = max(conv_err, float(np.abs(rig.pose_local_rk(arm) - rx.clip_locals_rk(walk_src.local_b[f:f + 1])[0]).max()))
    print(f"\n== Conventions : max|clip_locals_rk − pose_local_rk(Blender)| = {conv_err:.2e}")
    neg = _negative_controls(rep)
    print("\n== Contrôles négatifs ==")
    print(json.dumps(neg, indent=1, ensure_ascii=False, default=str))
    # assertions
    assert rep["status"] == 0, f"statut {rep['status']} — erreurs {rep['errors']}"
    assert rep["ok"]
    assert len(rep["usd"]) == 4, [Path(r["file"]).name for r in rep["usd"]]
    assert conv_err < 1e-5, conv_err
    for r in rep["usd"]:
        assert r["ok"], val.format_usd_result(r)
        assert r["skinning"]["poses"] >= 3 and r["skinning"]["maxErrorQuery"] <= 1e-4
        assert r["skinning"]["maxErrorBake"] <= 1e-4
    ql = next(r for r in rep["usd"] if r["kind"] == "quicklook")
    assert ql["animation"]["pass"] and ql["animation"]["loopError"] is not None
    assert rep["clips"]["ok"] and rep["rig"]["ok"] and rep["sizes"]["ok"]
    assert neg["corrupt_usd"]["ok"] is False and neg["corrupt_usd"]["arkit_failed"]
    assert neg["shifted_reference"]["ok"] is False and neg["shifted_reference"]["skinning_pass"] is False
    assert neg["truncated_bin"].startswith("détecté")
    man = json.loads((OUT / "PonyRig.json").read_text())
    assert [j["name"] for j in man["joints"]] == template.JOINT_NAMES
    assert {p["id"] for p in man["parts"]} == {"saddle_english", "mane_natural"}
    sad = next(p for p in man["parts"] if p["id"] == "saddle_english")
    assert sad["materialSlots"] == ["slot_primary", "slot_metal"] and sad["blendShapes"] == ["shape_fat"]
    mane = next(p for p in man["parts"] if p["id"] == "mane_natural")
    assert mane["materialSlots"] == ["slot_primary"] and mane["category"] == "hair"
    mane_usda = (IN / "export" / "Parts" / "mane_natural" / "mane_natural.usda").read_text()
    assert 'def Material "slot_primary"' in mane_usda and "float inputs:opacityThreshold = 0.35" in mane_usda
    hs = next(c for c in man["clips"] if c["name"] == "head_shake")
    assert hs["mask"] and "head" in hs["mask"] and "thigh_l" not in hs["mask"]
    walk = next(c for c in man["clips"] if c["name"] == "walk")
    assert walk["rootVelocity"] == [0.0, 0.0, -1.4] and abs(walk["duration"] - 32 / 30) < 1e-6
    g = rep["glb"]
    assert g["skins"] == [{"joints": 70}], g["skins"]
    assert sorted(a["name"] for a in g["animations"]) == ["head_shake", "walk"], g["animations"]
    assert len(g["meshes"]) == 4, [m["name"] for m in g["meshes"]]      # Body, Eyes, Mane, Saddle
    body_glb = next(m for m in g["meshes"] if m["name"] == "Body")
    assert body_glb["morphTargets"] == ["shape_fat", "head_short"] and body_glb["joints4"]
    print("\nTEST test_export_end_to_end : OK")


def test_missing_inputs():
    """Entrées absentes : pas de plantage, message clair, statut 2 (partiel), données runtime du gabarit."""
    from stages import s09_export
    empty = ROOT / "empty_build"
    out = ROOT / "empty_out"
    for d in (empty, out):
        if d.exists():
            shutil.rmtree(d)
    empty.mkdir(parents=True)
    rep = s09_export.run(empty, out, quicklook=True, do_validate=True)
    assert rep["status"] == 2, rep["status"]
    assert len(rep["missing"]) >= 3 and not rep["errors"]
    assert (out / "PonyRig.json").is_file() and (out / "PonyClips.bin").is_file()
    assert not (out / "Pony.usdz").exists()
    print("\nTEST test_missing_inputs : OK")


if __name__ == "__main__":
    test_export_end_to_end()
    test_missing_inputs()
