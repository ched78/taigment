"""Crins du poney (agent « hair ») : orchestration de la génération des pièces de crins (SPEC §6).

Pièces produites (une par fichier `Pipeline/build/parts/<id>.blend`, objet mesh nommé `<id>`, modificateur
Armature vers `PonyRig` construit par `rig.build_armature()`, 70 groupes de sommets = joints, ≤ 4 influences,
poids normalisés, matériau unique `M_Hair`) :
  mane_natural, mane_braided, mane_roached, forelock_natural, forelock_braided, tail_natural, tail_braided, feathers
+ `mane_braided_anchors.json` (position, repère et joint de chaque natte bouton, pour rubans/pompons)
+ textures `Pipeline/build/textures/hair_strands.png`, `hair_normal.png`, `braid_detail.png`,
  `hair_albedo_default.png` (albedo d'aperçu brun dérivé de hair_strands, pour Blender / Quick Look).

Ajustement au corps : si `Pipeline/build/body.blend` (objet `Body`) existe, les racines sont recalées sur sa surface
réelle (plus proche point / rayons) avec une pénétration contrôlée de ROOT_DEPTH, les mèches restent au-dessus de
la peau (collisions pendant la croissance + passe de dégagement), et les poids des racines sont transférés depuis
les poids de peau du corps. Sinon, un corps PROVISOIRE (SDF approximative alignée sur les joints, poids
automatiques Blender) est utilisé et le rapport l'indique (`body_source = "provisional"`).

Les positions des joints sont toujours lues sur l'armature construite par `rig.build_armature()`.
Déterminisme : graines fixes (hair_texture.SEED, une graine par générateur).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import conventions as cv
from . import hair_geom as hg
from . import hair_styles as hst
from . import hair_surface as hs
from . import hair_texture as htex
from . import template

PART_IDS = list(hst.GENERATORS)
PARTS_DIR = cv.BUILD_DIR / "parts"
TEX_DIR = cv.TEXTURE_BUILD_DIR
CACHE_DIR = cv.BUILD_DIR / "hair_cache"
ANCHORS_JSON = PARTS_DIR / "mane_braided_anchors.json"
PROVISIONAL_CACHE = CACHE_DIR / "provisional_body_v1.npz"

# Os non déformants pour la peau du corps provisoire (os secondaires / accessoires) [I]
_NON_SKIN = ("mane_", "forelock_", "stirrup_", "eye_", "eyelid_")


# ----------------------------------------------------------------------------------------------
# Textures
# ----------------------------------------------------------------------------------------------
def ensure_textures(force: bool = False, log=print):
    names = {"strands": "hair_strands.png", "normal": "hair_normal.png", "braid_detail": "braid_detail.png",
             "albedo_default": "hair_albedo_default.png"}
    paths = {k: TEX_DIR / v for k, v in names.items()}
    if force or not all(p.exists() for p in paths.values()):
        t0 = time.time()
        htex.write_textures(TEX_DIR)
        log(f"[hair] textures écrites dans {TEX_DIR} ({time.time() - t0:.1f}s)")
    return paths


# ----------------------------------------------------------------------------------------------
# Corps
# ----------------------------------------------------------------------------------------------
def _auto_skin_weights(V, F, arm):
    """Poids de peau du corps provisoire : chaleur Blender (ARMATURE_AUTO) sur les os du corps, limités à 4."""
    import bpy

    me = bpy.data.meshes.new("ProvisionalBody")
    me.from_pydata(V.tolist(), [], F.tolist())
    me.update()
    ob = bpy.data.objects.new("ProvisionalBody", me)
    bpy.context.scene.collection.objects.link(ob)
    saved = {}
    for b in arm.data.bones:
        saved[b.name] = b.use_deform
        if b.name.startswith(_NON_SKIN) or b.name == "root":
            b.use_deform = False
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    for b in arm.data.bones:
        b.use_deform = saved[b.name]
    W = np.zeros((len(V), hg.NJ))
    gidx = {g.index: g.name for g in ob.vertex_groups}
    for v in me.vertices:
        for g in v.groups:
            nm = gidx.get(g.group)
            if nm in hg.JIDX:
                W[v.index, hg.JIDX[nm]] = g.weight
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    unweighted = int((W.sum(1) < 1e-6).sum())
    return hg.limit_influences(W), unweighted


def provisional_surface(J, arm, log=print, use_cache=True):
    if use_cache and PROVISIONAL_CACHE.exists():
        d = np.load(PROVISIONAL_CACHE)
        if np.allclose(d["J"], _joint_signature(J)):
            return hs.BodySurface(d["V"], d["F"], d["W"], source="provisoire (cache)"), d
    t0 = time.time()
    V, F = hs.provisional_body(J)
    W, unweighted = _auto_skin_weights(V, F, arm)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PROVISIONAL_CACHE, V=V, F=F, W=W, J=_joint_signature(J))
    log(f"[hair] corps provisoire : {len(V)} sommets, {len(F)} triangles, {unweighted} sans poids "
        f"({time.time() - t0:.1f}s)")
    return hs.BodySurface(V, F, W, source="provisoire"), {"V": V, "F": F, "W": W}


def _joint_signature(J):
    return np.array([np.concatenate(J[n]) for n in template.JOINT_NAMES])


def get_surface(J, arm, prefer_real=True, log=print):
    """Renvoie (BodySurface, kind) avec kind ∈ {"real", "provisional"}."""
    if prefer_real and hs.body_available():
        surf, _obj = hs.load_body_from_blend()
        if surf.weights is None:
            log("[hair] ATTENTION : body.blend sans poids de peau exploitables -> poids des racines par chaînes d'os")
        if not hs.outward_check(surf):
            log("[hair] ATTENTION : normales du corps apparemment inversées (test du rayon vertical)")
        return surf, "real"
    surf, _ = provisional_surface(J, arm, log)
    return surf, "provisional"


# ----------------------------------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------------------------------
def _anchor_json(anchors, J, arm):
    from . import rig

    rest = {n: np.array(arm.data.bones[n].matrix_local, np.float64) for n in template.JOINT_NAMES}
    out = []
    for a in anchors:
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = a["right"], a["tangent"], a["normal"], a["top"]
        Mrk = cv.world_frame_b2rk(M)
        loc = np.linalg.inv(rest[a["joint"]]) @ M
        t, q, s = rig.decompose(Mrk)
        tl, ql, sl = rig.decompose(loc)
        out.append({
            "index": a["index"],
            "joint": a["joint"],
            "weights": a["weights"],
            "radius": round(a["radius"], 5),
            "crest_t": round(a["crest_t"], 4),
            "position_blender": [round(float(v), 5) for v in a["top"]],
            "center_blender": [round(float(v), 5) for v in a["center"]],
            "normal_blender": [round(float(v), 5) for v in a["normal"]],
            "tangent_blender": [round(float(v), 5) for v in a["tangent"]],
            "position_rk": [round(float(v), 5) for v in cv.vec_b2rk(a["top"])],
            "center_rk": [round(float(v), 5) for v in cv.vec_b2rk(a["center"])],
            "normal_rk": [round(float(v), 5) for v in cv.vec_b2rk(a["normal"])],
            "tangent_rk": [round(float(v), 5) for v in cv.vec_b2rk(a["tangent"])],
            "orientation_rk_xyzw": [round(float(v), 6) for v in q],
            "joint_local": {"t": [round(float(v), 5) for v in tl], "r_xyzw": [round(float(v), 6) for v in ql]},
        })
    return {
        "format": "ValombrePonyBraidAnchors", "version": 1, "part": "mane_braided", "count": len(out),
        "frame": ("Repère de chaque ancre : X = droite du poney (latéral), Y = tangente de la crête vers la tête, "
                  "Z = normale de la crête (vers l'extérieur) ; origine = sommet du bouton. "
                  "*_blender : espace Blender (Z haut, +Y avant) ; *_rk : espace RealityKit (Y haut, -Z avant) ; "
                  "orientation_rk_xyzw = rotation monde RK du repère ; joint_local = repère exprimé dans le repère "
                  "de repos (bind) du joint, identique en Blender et en RK (axes locaux conservés, SPEC §1)."),
        "anchors": out,
    }


def build_parts(part_ids=None, prefer_real=True, write=True, log=print, textures_force=False):
    """Génère les pièces demandées ; renvoie un dict de statistiques par pièce."""
    import bpy

    from . import rig

    part_ids = part_ids or PART_IDS
    tex = ensure_textures(textures_force, log)
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = rig.build_armature()
    J = hs.joints_from_armature(arm)
    surf, kind = get_surface(J, arm, prefer_real, log)
    log(f"[hair] surface du corps : {surf.source} ({kind})")
    crest = hs.crest_line(surf, J)
    log(f"[hair] crête : {crest['length']:.3f} m, de {np.round(crest['points'][0], 3)} à "
        f"{np.round(crest['points'][-1], 3)}")
    textures_rel = {k: str(Path(v).resolve()) for k, v in tex.items()}   # rendus relatifs à l'enregistrement
    stats = {"body_source": kind, "body": surf.source, "crest_length": crest["length"], "parts": {}}
    anchors_doc = None
    for pid in part_ids:
        t0 = time.time()
        b, W, extra = hst.GENERATORS[pid](surf, J, crest)
        A = b.arrays()
        V, cl = hg.enforce_clearance(surf, A["V"], A["S"], A["ROOTFLAG"], min_off=0.003,
                                     root_depth=hst.ROOT_DEPTH)
        A["V"] = V
        pen = hg.penetration_report(surf, V, A["F"], A["ROOTFLAG"])
        ws = hg.weight_stats(W)
        st = {
            "vertices": len(V), "triangles": b.tri_count, "budget": hst.BUDGETS[pid],
            "uv_in_unit": bool((A["UV"] >= 0).all() and (A["UV"] <= 1).all()),
            "duplicate_vertices": hg.duplicate_report(V, A["UV"]),
            "pushed_out": cl["pushed"], **pen, **{k: v for k, v in ws.items() if k != "joints"},
            "joints": ws["joints"], "seconds": round(time.time() - t0, 2),
        }
        stats["parts"][pid] = st
        log(f"[hair] {pid}: {st['triangles']} tris (budget {st['budget']}), {st['vertices']} v, "
            f"intérieur v/f={pen['vertices_inside']}/{pen['faces_inside']}, racines -{pen['root_depth_mean'] * 1000:.1f} mm, "
            f"influences max {ws['max_influences']}, {st['seconds']}s")
        if pid == "mane_braided":
            anchors_doc = extra.get("anchors")
        if write:
            # sauvegarde : nouvelle scène vide (la surface BVH est indépendante de bpy.data)
            np_arrays = {k: A[k] for k in ("V", "F", "UV", "FACING", "TAG", "S")}
            hg.write_part_blend(pid, np_arrays, W, PARTS_DIR / f"{pid}.blend", textures_rel,
                                props={"body_source": kind, "triangles": b.tri_count})
            # write_part_blend réinitialise la scène : on reconstruit l'armature pour les pièces suivantes
            arm = bpy.data.objects["PonyRig"]
    if anchors_doc is not None and write:
        doc = _anchor_json(anchors_doc, J, bpy.data.objects["PonyRig"])
        doc["body_source"] = kind
        ANCHORS_JSON.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
        log(f"[hair] {ANCHORS_JSON.name} : {doc['count']} ancres")
    return stats


def main(argv=None):
    import argparse

    ap = argparse.ArgumentParser(description="Génère les pièces de crins (Pipeline/build/parts/*.blend)")
    ap.add_argument("--parts", nargs="*", default=None, help=f"sous-ensemble de {PART_IDS}")
    ap.add_argument("--provisional", action="store_true", help="ignore body.blend et utilise le corps provisoire")
    ap.add_argument("--textures", action="store_true", help="régénère les textures")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--stats", default=None, help="chemin JSON des statistiques")
    a = ap.parse_args(argv)
    st = build_parts(a.parts, prefer_real=not a.provisional, write=not a.no_write, textures_force=a.textures)
    if a.stats:
        Path(a.stats).write_text(json.dumps(st, indent=1, ensure_ascii=False, default=float))
    return st
