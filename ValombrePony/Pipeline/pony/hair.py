"""Crins du poney (agent « hair ») : orchestration de la génération des pièces de crins (SPEC §6).

Pièces produites (une par fichier `Pipeline/build/parts/<id>.blend`, objet mesh nommé `<id>`, modificateur
Armature vers `PonyRig` construit par `rig.build_armature()`, 70 groupes de sommets = joints, ≤ 4 influences,
poids normalisés, matériau unique `M_Hair`) :
  mane_natural, mane_braided, mane_roached, forelock_natural, forelock_braided, tail_natural, tail_braided, feathers
+ `mane_braided_anchors.json` (position, repère et joint de chaque natte bouton, pour rubans/pompons)
+ textures `Pipeline/build/textures/hair_strands.png`, `hair_normal.png`, `braid_detail.png`,
  `hair_albedo_default.png` (albedo d'aperçu brun dérivé de hair_strands, pour Blender / Quick Look).

Ajustement au corps : si `Pipeline/build/body.blend` (objet `Body`) existe, les racines sont recalées sur sa surface
réelle (plus proche point / rayons) avec une pénétration contrôlée de ROOT_DEPTH (2,5 mm), les mèches restent
au-dessus de la peau (collisions pendant la croissance + passes de dégagement des sommets et des centres de faces),
et les poids sont transférés depuis les poids de peau du corps (au plus proche point de chaque sommet pour la
crinière et le toupet). Sinon, un corps PROVISOIRE est utilisé — la SDF anatomique de l'agent « body »
(`body_sdf`, variante fermée) si elle est importable, sinon une SDF grossière — avec des poids automatiques Blender
(chaleur) ; le rapport l'indique (`body_source = "provisional"`).

Poids (≤ 4 influences, limite continue) :
  crinières : peau du corps sous chaque sommet, puis la part de neck_k passe progressivement (racine → pointe,
              jusqu'à 85 %) à mane_k (enfant de neck_k) : déformation identique à la peau quand les mane_* sont au
              repos, balancement secondaire par les ressorts du runtime. Boutons des nattes : rigides (peau sous
              le bouton).
  toupets   : peau (tête) puis chaîne forelock_01…03 par projection (jusqu'à 92 % aux pointes ; 35 % pour la natte).
  queues    : peau à la racine puis dégradé le long de tail_01…tail_10 (projection sur la chaîne).
  fanons    : peau à la racine puis *_cannon_* / *_pastern_* par projection.

Indications runtime pour M_Hair [I] : `opacityThreshold` 0,4 (alpha testé, pas de mélange), `faceCulling = .none`
(cartes simples, pas de double face dans l'USD), rugosité ≈ 0,48 ; albedo recalculé par le compositeur depuis
`hair_strands.png` (canaux : voir hair_texture.py). Les normales des cartes sont des normales « de volume »
(65 % direction extérieure de la masse de crins + 35 % normale géométrique) pour un éclairage cohérent des deux faces.

Les positions des joints sont toujours lues sur l'armature construite par `rig.build_armature()`.
Déterminisme : graines fixes (hair_texture.SEED, une graine par générateur).
Relance : `python3 Pipeline/stages/s03_hair.py` (cf. ce script pour les options).
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
PROVISIONAL_CACHE = CACHE_DIR / "provisional_body.npz"

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


def _provisional_mesh(J, log=print):
    """Maillage du corps provisoire : de préférence la SDF anatomique de l'agent « body » (`body_sdf`, variante
    fermée `features=False`, bande étroite h = 8 mm) ; à défaut, la SDF grossière de `hair_surface`."""
    try:
        from . import body_sdf

        sdf = body_sdf.build_sdf(joints=template.joint_table(), params=body_sdf.BodyParams(features=False))
        V, F = body_sdf.mesh_narrowband(sdf, h=0.008, log=lambda *a, **k: None)
        return np.asarray(V, np.float64), np.asarray(F, np.int64), "body_sdf"
    except Exception as e:      # module absent / en cours de modification par l'agent body
        log(f"[hair] body_sdf indisponible ({type(e).__name__}: {e}) -> SDF grossière de hair_surface")
        V, F = hs.provisional_body(J)
        return V, F, "hair_surface"


def _provisional_key(J):
    import hashlib

    h = hashlib.sha1(_joint_signature(J).tobytes())
    for f in ("body_sdf.py", "body_sdf_lib.py", "hair_surface.py"):
        p = Path(__file__).resolve().parent / f
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def provisional_surface(J, arm, log=print, use_cache=True):
    key = _provisional_key(J)
    if use_cache and PROVISIONAL_CACHE.exists():
        d = np.load(PROVISIONAL_CACHE, allow_pickle=False)
        if str(d["key"]) == key:
            return hs.BodySurface(d["V"], d["F"], d["W"], source=f"provisoire {d['kind']} (cache)"), d
    t0 = time.time()
    V, F, kind = _provisional_mesh(J, log)
    W, unweighted = _auto_skin_weights(V, F, arm)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(PROVISIONAL_CACHE, V=V, F=F, W=W, key=key, kind=kind)
    log(f"[hair] corps provisoire ({kind}) : {len(V)} sommets, {len(F)} triangles, {unweighted} sans poids "
        f"({time.time() - t0:.1f}s)")
    return hs.BodySurface(V, F, W, source=f"provisoire {kind}"), {"V": V, "F": F, "W": W, "kind": kind}


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
        V, fcl = hg.enforce_face_clearance(surf, V, A["F"], A["ROOTFLAG"])
        cl.update(fcl)
        A["V"] = V
        pen = hg.penetration_report(surf, V, A["F"], A["ROOTFLAG"])
        ws = hg.weight_stats(W)
        st = {
            "vertices": len(V), "triangles": b.tri_count, "budget": hst.BUDGETS[pid],
            "uv_in_unit": bool((A["UV"] >= 0).all() and (A["UV"] <= 1).all()),
            "duplicate_vertices": hg.duplicate_report(V, A["UV"]),
            "pushed_out": cl["pushed"], "faces_pushed": cl["faces_pushed"], **pen, **{k: v for k, v in ws.items() if k != "joints"},
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
            np_arrays = {k: A[k] for k in ("V", "F", "UV", "FACING", "TAG", "S", "ROOTFLAG")}
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


# ----------------------------------------------------------------------------------------------
# Vérification indépendante des fichiers écrits
# ----------------------------------------------------------------------------------------------
def verify_part_file(pid, path=None):
    """Rouvre `<id>.blend` et vérifie le contrat de la tâche. Renvoie (ok, dict de mesures, liste d'erreurs)."""
    import bpy

    path = Path(path or PARTS_DIR / f"{pid}.blend")
    errors = []
    bpy.ops.wm.open_mainfile(filepath=str(path))
    ob = bpy.data.objects.get(pid)
    if ob is None or ob.type != "MESH":
        return False, {}, [f"objet mesh {pid!r} absent"]
    mods = [m for m in ob.modifiers]
    arm_mods = [m for m in mods if m.type == "ARMATURE"]
    if len(mods) != 1 or len(arm_mods) != 1:
        errors.append(f"modificateurs : {[m.type for m in mods]} (attendu : un seul ARMATURE)")
    arm = arm_mods[0].object if arm_mods else None
    if arm is None or arm.name != "PonyRig" or arm.type != "ARMATURE":
        errors.append("le modificateur Armature ne cible pas l'armature PonyRig")
    else:
        names = [b.name for b in arm.data.bones]     # ordre hiérarchique de Blender : comparaison d'ensembles
        if sorted(names) != sorted(template.JOINT_NAMES):
            errors.append("os de PonyRig différents du gabarit (noms)")
            names = [n for n in names if n in template.JOINT_NAMES]
        jt = {e["name"]: e for e in template.joint_table()}
        dev = max(float(np.abs(np.array(arm.data.bones[n].head_local) - np.array(jt[n]["head"])).max())
                  for n in names)
        if dev > 1e-5:
            errors.append(f"positions de repos de PonyRig ≠ gabarit (écart {dev:.2e} m)")
    vg = [g.name for g in ob.vertex_groups]
    if vg != list(template.JOINT_NAMES):
        errors.append(f"groupes de sommets ≠ 70 joints dans l'ordre ({len(vg)} groupes)")
    me = ob.data
    n = len(me.vertices)
    W = np.zeros((n, len(vg)))
    for v in me.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    nz = (W > 0).sum(1)
    sums = W.sum(1)
    if nz.max() > 4:
        errors.append(f"{int((nz > 4).sum())} sommets avec > 4 influences")
    if np.abs(sums - 1).max() > 1e-3:
        errors.append(f"poids non normalisés (écart max {np.abs(sums - 1).max():.2e})")
    uvl = me.uv_layers.active
    uv = np.zeros(len(me.loops) * 2)
    if uvl is None:
        errors.append("pas de carte UV")
    else:
        uvl.data.foreach_get("uv", uv)
        if uv.min() < 0 or uv.max() > 1:
            errors.append(f"UV hors [0,1] ({uv.min():.4f}…{uv.max():.4f})")
    mats = [m.name for m in me.materials if m]
    if mats != [hg.HAIR_MATERIAL_NAME]:
        errors.append(f"matériaux {mats} (attendu [{hg.HAIR_MATERIAL_NAME}])")
    missing_tex = []
    for img in bpy.data.images:
        if img.filepath and not Path(bpy.path.abspath(img.filepath)).exists():
            missing_tex.append(img.filepath)
    if missing_tex:
        errors.append(f"textures introuvables : {missing_tex}")
    me.calc_loop_triangles()
    co = np.zeros(n * 3)
    me.vertices.foreach_get("co", co)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    vuv = np.zeros((n, 2))
    vuv[lv] = uv.reshape(-1, 2)
    dups = hg.duplicate_report(co.reshape(-1, 3), vuv)
    if dups:
        errors.append(f"{dups} sommets dupliqués (même position et même UV)")
    used = np.zeros(n, bool)
    used[lv] = True
    if (~used).any():
        errors.append(f"{int((~used).sum())} sommets isolés (sans face)")
    m = {"triangles": len(me.loop_triangles), "vertices": n, "max_influences": int(nz.max()),
         "weight_sum_err": float(np.abs(sums - 1).max()), "uv_range": [float(uv.min()), float(uv.max())],
         "materials": mats, "image_paths": sorted({i.filepath for i in bpy.data.images if i.filepath}),
         "joints_used": sorted(template.JOINT_NAMES[j] for j in np.nonzero(W.sum(0) > 0)[0])}
    if m["triangles"] > hst.BUDGETS[pid]:
        errors.append(f"budget dépassé : {m['triangles']} > {hst.BUDGETS[pid]} triangles")
    return not errors, m, errors


def verify_all(part_ids=None, log=print):
    out = {}
    for pid in part_ids or PART_IDS:
        ok, m, errs = verify_part_file(pid)
        out[pid] = {"ok": ok, **m, "errors": errs}
        log(f"[hair] vérif {pid}: {'OK' if ok else 'ÉCHEC'} — {m.get('triangles')} tris, "
            f"infl. max {m.get('max_influences')}, Σw err {m.get('weight_sum_err', 0):.1e}"
            + ("" if ok else f" — {errs}"))
    if ANCHORS_JSON.exists():
        d = json.loads(ANCHORS_JSON.read_text())
        ok = d.get("count") == hst.N_BRAIDS and d["count"] % 2 == 1
        out["anchors"] = {"ok": ok, "count": d.get("count")}
        log(f"[hair] vérif ancres : {d.get('count')} nattes (impair : {d.get('count', 0) % 2 == 1})")
    return out
