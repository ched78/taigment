#!/usr/bin/env python3
"""Étape 01 — corps du poney : SDF anatomique → maillages haute / basse définition → UV → cuissons →
cartes du pelage (SPEC §4) → yeux, bouche, cils → body.blend + body_meta.json → prévisualisations.

Usage :
    python3 Pipeline/stages/s01_body.py                # tout (≈ 5–8 min sur 4 CPU)
    python3 Pipeline/stages/s01_body.py --no-previews  # sans les rendus
    python3 Pipeline/stages/s01_body.py --previews     # rendus seulement (relit body.blend)
    python3 Pipeline/stages/s01_body.py --quick        # haute définition grossière (essais)

Sorties : Pipeline/build/body.blend, Pipeline/build/body_meta.json, Pipeline/build/textures/coat_{normal,orm,
shading,regions,params,patterns,albedo_preview,mouth_albedo,lashes_albedo}.png, Previews/body/*.png.
Déterministe : aucune source d'aléa non graine (QuadriFlow : graines fixes, essais dans un ordre fixe).
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from pony import conventions as cv  # noqa: E402

TEX = cv.TEXTURE_BUILD_DIR
BLEND = cv.BUILD_DIR / "body.blend"
META = cv.BUILD_DIR / "body_meta.json"
PREV = cv.PREVIEW_DIR / "body"
T0 = time.perf_counter()


def log(*a):
    print(f"[{time.perf_counter() - T0:6.1f}s]", *a, flush=True)


def save_png(arr, path, mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    (Image.fromarray(arr, mode) if mode else Image.fromarray(arr)).save(path)
    return path


def to8(x):
    return (np.clip(np.asarray(x, np.float64), 0, 1) * 255.0 + 0.5).astype(np.uint8)


# ==============================================================================================
def build(args):
    import bpy
    import bmesh  # noqa: F401

    from pony import bake, body, body_maps, body_measure, body_scene, body_sdf, body_uv, head_parts, rig, template
    from pony.body_sdf_lib import F32

    cv.ensure_dirs()
    TEX.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    meta = {"format": "ValombrePonyBodyMeta", "version": 1, "units": "m", "axes": "Blender (x droite, y avant, z haut)"}
    timings = {}

    # ---------------------------------------------------------------- SDF
    joints = template.joint_table()
    params = body_sdf.BodyParams()
    sdf_full = body_sdf.build_sdf(joints, params)
    sdf_closed = body_sdf.build_sdf(joints, body_sdf.BodyParams(features=False))
    log("SDF construits")
    meas = body_measure.measure_body(sdf_full)
    log("mesures :", {k: round(v, 3) for k, v in meas.items() if isinstance(v, float)})
    timings["sdf_measure"] = time.perf_counter() - T0

    # ---------------------------------------------------------------- basse définition
    t = time.perf_counter()
    bm, sg = body.build_low(sdf_closed, sdf_full, target_faces=args.target_faces, log=log)
    bm.verts.index_update()
    bm.faces.index_update()
    groups = {k: {v.index for v in vs if v.is_valid} for k, vs in sg.groups.items()}
    pocket_sets = {"eye_l": groups["eye_sac_l"], "eye_r": groups["eye_sac_r"],
                   "nostril_l": groups["nostril_l"] - {v.index for v in sg.margin_verts if v.is_valid},
                   "nostril_r": groups["nostril_r"] - {v.index for v in sg.margin_verts if v.is_valid},
                   "mouth": groups["mouth_roof"] | groups["mouth_floor"] | groups["mouth_seam"]}
    bm.faces.ensure_lookup_table()
    pockets = {}
    for name, s in pocket_sets.items():
        pockets[name] = [f.index for f in bm.faces if all(v.index in s for v in f.verts)]
    timings["low_mesh"] = time.perf_counter() - t

    # ---------------------------------------------------------------- UV
    t = time.perf_counter()
    g = body_uv.MeshGraph(bm)
    seam_info = body_uv.compute_seams(g, sdf_full, pockets)
    # cavité buccale : couture arrière (toit / plancher)
    chain_src = [v for v in sg.groups["mouth_seam"] if v.is_valid]
    seam_vs, EL, ER = chain_src[:-2], chain_src[-2], chain_src[-1]
    chain = [ER.index] + [v.index for v in seam_vs] + [EL.index]
    for a_, b_ in zip(chain[:-1], chain[1:]):
        key = (min(a_, b_), max(a_, b_))
        if key in g.ekey:
            g.seam[g.ekey[key]] = True
    isl = body_uv.islands_from_seams(g)
    isl_names = body_uv.name_islands(g, sdf_full, isl, pockets)
    log(f"îlots : {len(isl_names)} -> {sorted(isl_names)}")
    ob = body_scene.bm_to_object(bm, "Body")
    me = ob.data
    # ordre des arêtes conservé par bm.to_mesh : vérification
    ev = np.zeros(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = np.sort(ev.reshape(-1, 2), 1)
    assert np.array_equal(ev, np.sort(g.E, 1)), "ordre des arêtes modifié par to_mesh"
    body_uv.unwrap(ob, g, sdf_full, isl, isl_names, size=2048, margin_px=args.margin_px, log=log)
    uvm = body_uv.uv_metrics(ob, isl, isl_names)
    gap = body_uv.island_gap_px(ob, isl, 2048)
    uvm["min_island_gap_px_2048"] = round(gap, 2)
    log(f"UV : distorsion d'aire p5–p95 {uvm['area_distortion_p5_p95']}, étirement médian "
        f"{uvm['conformal_stretch_median']} p95 {uvm['conformal_stretch_p95']}, écart min {gap:.1f} px")
    timings["uv"] = time.perf_counter() - t

    # ---------------------------------------------------------------- haute définition
    t = time.perf_counter()
    hi_params = body_sdf.BodyParams(micro_detail=1.0)
    sdf_hi = body_sdf.build_sdf(joints, hi_params)
    Vh, Fh = body_sdf.mesh_narrowband(sdf_hi, h=args.high_h, log=log)
    ob_hi = body_scene.mesh_object("Body_high", Vh, Fh)
    ob_hi.hide_render = True
    ob_hi.hide_set(True)
    ob_hi["pony_export"] = False
    timings["high_mesh"] = time.perf_counter() - t

    # ---------------------------------------------------------------- cuissons
    t = time.perf_counter()
    ob_hi.hide_set(False)
    nrm = bake.bake_normals(ob, ob_hi, size=2048, log=log)
    ob_hi.hide_set(True)
    ao = bake.bake_ao(ob, size=1024, samples=args.ao_samples, hide=[ob_hi], log=log)
    timings["bake"] = time.perf_counter() - t

    # ---------------------------------------------------------------- cartes
    t = time.perf_counter()
    V, VN, faces, fuv = body_scene.read_mesh(ob)
    lm = body_maps.LowMesh(V, VN, faces, fuv, isl, isl_names)
    ctx = body_maps.FieldContext(sdf_full, lm, sdf_full.rig, sdf_geo=sdf_closed)
    tx1 = body_maps.Texels(lm, 1024)
    F1 = body_maps.compute_fields(ctx, tx1, log=log)
    log(f"champs 1024² : {len(tx1.P)} texels")
    reg = np.zeros((tx1.P.shape[0], 4))
    reg[:, 0] = F1["region"] * 16 / 255.0
    reg[:, 1] = F1["extremities"]
    reg[:, 2] = F1["pangare"]
    reg[:, 3] = F1["sooty"]
    reg_img = tx1.image(reg)
    reg8 = to8(reg_img)
    reg8[..., 0] = tx1.image(F1["region"] * 16).astype(np.uint8)     # ids exacts (plus proche voisin)
    save_png(reg8, TEX / "coat_regions.png")
    par = np.stack([F1["leg_height"], F1["face_u"], F1["face_v"], F1["dorsal"]], 1)
    save_png(to8(tx1.image(par)), TEX / "coat_params.png")
    pat = np.stack([F1["pat_tobiano"], F1["pat_overo"], F1["pat_spots"], F1["pat_dapple"]], 1)
    save_png(to8(tx1.image(pat)), TEX / "coat_patterns.png")
    # 2048² : ombrage, ORM, normales
    tx2 = body_maps.Texels(lm, 2048)
    F2 = body_maps.compute_fields(ctx, tx2, log=log)
    D = body_maps.hair_flow(ctx, tx2.P, tx2.N, F2["names"], F2["leg_key"])
    streak = body_maps.streak_noise(tx2.P, D, k=sdf_full.rig.k)
    lum = 0.5 + 0.045 * streak * (1 - 0.8 * F2["bare_skin"])
    ao2 = np.asarray(Image.fromarray((np.clip(ao, 0, 1) * 65535).astype(np.uint16)).resize((2048, 2048),
                                                                                           Image.BILINEAR),
                     np.float64) / 65535.0
    ao_t = ao2[tx2.valid]
    cav = np.clip(0.25 + 0.75 * ao_t, 0, 1)
    sh = np.stack([lum, cav, F2["bare_skin"]], 1)
    save_png(to8(tx2.image(sh)), TEX / "coat_shading.png")
    orm = np.stack([np.clip(0.15 + 0.85 * ao_t, 0, 1), F2["roughness"], np.zeros(len(ao_t))], 1)
    save_png(to8(tx2.image(orm)), TEX / "coat_orm.png")
    # normales : cuisson + stries (gradient de la hauteur « poil » en espace image ≈ espace tangent)
    hgt = tx2.image(streak * (1 - F2["bare_skin"]), fill=0.0)
    hgt = body_maps.gaussian_filter(hgt, 0.6)
    gy, gx = np.gradient(hgt)
    nxy = nrm * 2.0 - 1.0
    amp = 0.035
    nxy[..., 0] -= amp * gx
    nxy[..., 1] += amp * gy          # ligne 0 = haut : +v = −ligne
    nxy /= np.maximum(np.linalg.norm(nxy, axis=-1, keepdims=True), 1e-6)
    save_png(to8(nxy * 0.5 + 0.5), TEX / "coat_normal.png")
    timings["maps"] = time.perf_counter() - t
    log("cartes écrites")

    # ---------------------------------------------------------------- yeux, bouche, cils
    feats = sdf_full.features
    eyes = head_parts.build_eyes(feats)
    mouth = head_parts.build_mouth(feats, sdf_full, log=log)
    lashes = head_parts.build_lashes(feats, sdf_full, sdf_full.rig)
    save_png(head_parts.mouth_texture(), TEX / "coat_mouth_albedo.png")
    save_png(head_parts.lashes_texture(), TEX / "coat_lashes_albedo.png")
    parts_obj = {}
    for pm in (eyes, mouth, lashes):
        Vp, Fp, UVp = pm.arrays()
        o = body_scene.mesh_object(pm.name, Vp, Fp, UVp, smooth=pm.name != "Lashes")
        parts_obj[pm.name] = o
        for gname, idx in pm.groups.items():
            vals = np.zeros(len(Vp))
            vals[idx] = 1.0
            body_scene.add_point_attribute(o, f"hint_{gname}", vals)

    # ---------------------------------------------------------------- indices pour le skinning (attributs)
    Vb = V
    mf = feats["mouth"]
    jaw_hint = np.zeros(len(Vb))
    jaw_hint[list(groups["mouth_floor"])] = 1.0
    lower_lip = {v.index for v in sg.groups["lip_lower_margin"] if v.is_valid}
    jaw_hint[list(lower_lip)] = 1.0
    body_scene.add_point_attribute(ob, "hint_jaw", jaw_hint)
    for side in "lr":
        ef = feats[f"eye_{side}"]
        mg = [v.index for v in sg.groups[f"eye_margin_{side}"] if v.is_valid]
        up = np.zeros(len(Vb))
        lo = np.zeros(len(Vb))
        for i in mg + [v.index for v in sg.groups[f"eye_margin_inner_{side}"] if v.is_valid]:
            (up if (Vb[i] - ef.C) @ ef.v > 0 else lo)[i] = 1.0
        body_scene.add_point_attribute(ob, f"hint_eyelid_upper_{side}", up)
        body_scene.add_point_attribute(ob, f"hint_eyelid_lower_{side}", lo)

    # ---------------------------------------------------------------- matériaux, armature, sauvegarde
    m_coat = body_scene.coat_material(TEX)
    ob.data.materials.append(m_coat)
    ob_hi.data.materials.append(m_coat)
    parts_obj["Eyes"].data.materials.append(body_scene.eye_material(TEX))
    parts_obj["Mouth"].data.materials.append(body_scene.simple_tex_material("M_Mouth", TEX, "coat_mouth_albedo.png", 0.35))
    parts_obj["Lashes"].data.materials.append(
        body_scene.simple_tex_material("M_Lashes", TEX, "coat_lashes_albedo.png", 0.5, alpha=True, threshold=0.35))
    arm = rig.build_armature()
    for o in bpy.data.objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = arm
    BLEND.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    log(f"écrit {BLEND}")

    # ---------------------------------------------------------------- méta
    def counts(o):
        st = body.mesh_stats(o.data)
        return dict(vertices=st["verts"], faces=st["faces"], triangles=st["tris"], quads=st["quads"])

    bm2 = bmesh.new()
    bm2.from_mesh(ob.data)
    topo = body.topology_check(bm2)
    bm2.free()
    eye_uv = {}
    for side in "lr":
        ef = feats[f"eye_{side}"]
        u, v = ctx.face_uv(ef.C[None])
        eye_uv[side] = (float(u[0]), float(v[0]))
    nu, nv = ctx.face_uv(np.array([feats["nostril_l"].Nc, feats["nostril_r"].Nc]))
    meta.update({
        "generator": "Pipeline/stages/s01_body.py",
        "params": params.to_dict(),
        "param_doc": {k: v[0] for k, v in body_sdf.PARAM_DOC.items()},
        "meshes": {"Body": {**counts(ob), "topology": topo, "uv_islands": len(isl_names)},
                   "Body_high": {**counts(ob_hi), "voxel_m": args.high_h, "note": "caché, pony_export=False"},
                   "Eyes": counts(parts_obj["Eyes"]), "Mouth": counts(parts_obj["Mouth"]),
                   "Lashes": counts(parts_obj["Lashes"])},
        "uv": {**uvm, "size": 2048, "margin_px_requested": args.margin_px, "islands_list": isl_names,
               "orientation": {"body": "+y (avant) -> +u", "head": "axe nuque->nez -> -v (v croît vers la nuque)",
                               "ear": "axe base->pointe -> +v", "leg": "+z -> +v",
                               "hoofwall": "+z (sol -> couronne) -> +v ; la CIRCONFÉRENCE du sabot suit u",
                               "sole": "pince -> +v"},
               "density_relative": body_uv.DENSITY},
        "maps": {
            "coat_regions.png": {"size": 1024, "R": "id de région × 16 (plus proche voisin)", "G": "extrémités (points)",
                                 "B": "pangaré", "A": "charbonné (sooty)"},
            "coat_params.png": {"size": 1024, "R": "hauteur de jambe (0 sol, 0.10 couronne, 1 coude/grasset ; 1 ailleurs)",
                                "G": "u facial (0.5 ligne médiane dorsale ; <0.5 côté gauche x<0 ; 0/1 ligne ventrale)",
                                "B": "v facial (0 bout du nez -> 1 nuque ; 1 au-delà)",
                                "A": "max(raie de mulet, bande cruciale)"},
            "coat_patterns.png": {"size": 1024, "R": "champ tobiano (rang normalisé)", "G": "champ overo/sabino/splash",
                                  "B": "taches (≈1 au centre)", "A": "pommelures (≈1 au centre, 0 sur le réseau)"},
            "coat_shading.png": {"size": 2048, "R": "détail de luminance du poil (0.5 neutre)",
                                 "G": "cavité/AO (1 = aucune)", "B": "peau apparente (0 poil … 1 peau nue)"},
            "coat_orm.png": {"size": 2048, "R": "occlusion", "G": "rugosité", "B": "métal (0)"},
            "coat_normal.png": {"size": 2048, "convention": "OpenGL (+Y = +v), espace tangent MikkTSpace de Blender"},
            "doc": "Sémantique détaillée : Pipeline/pony/body_maps.py (docstring)"},
        "regions": body_maps.REGION_IDS,
        "coat_landmarks": {"coronet": body_maps.CORONET_LEG_HEIGHT,
                           "faceEyeU": round(float(np.mean([abs(eye_uv[s][0] - 0.5) for s in "lr"])), 4),
                           "faceEyeV": round(float(np.mean([eye_uv[s][1] for s in "lr"])), 4),
                           "nostrilV": round(float(np.mean(nv)), 4),
                           "note": "coronet = hauteur de jambe EXACTE de la couronne (toutes les jambes) ; faceEyeU = "
                                   "|u−0.5| au centre des yeux ; faceEyeV / nostrilV = v facial au centre des yeux / "
                                   "des naseaux"},
        "hooves_uv": "parois : v = hauteur (sol en bas, couronne en haut), u = circonférence (couture aux talons) ; "
                     "soles : pince vers +v",
        "eyes": head_parts.eye_meta(feats),
        "mouth": {"cavity_center": [round(float(c), 5) for c in mf.cav_c],
                  "cavity_half_axes_m": [round(float(c), 5) for c in mf.cav_r],
                  "plane_normal": [round(float(c), 4) for c in mf.nm],
                  "min_clearance_m": mouth.attrs.get("min_clearance_m")},
        "skinning_hints": "attributs de sommet (POINT, FLOAT) : Body.hint_jaw (plancher buccal + lèvre inférieure), "
                          "Body.hint_eyelid_{upper,lower}_{l,r} (bords libres des paupières), Eyes.hint_eye_{l,r}, "
                          "Mouth.hint_jaw / hint_head, Lashes.hint_lash_{upper,lower}_{l,r} / hint_whiskers",
        "measurements": meas,
        "measurement_targets": body_measure.TARGETS,
        "timings_s": {k: round(v, 1) for k, v in timings.items()},
    })
    META.write_text(json.dumps(meta, indent=1, ensure_ascii=False, default=_json_default))
    log(f"écrit {META}")
    # disposition UV
    PREV.mkdir(parents=True, exist_ok=True)
    body_uv.draw_uv_layout(ob, PREV / "uv_layout.png", isl, isl_names, size=1024)
    # albedo d'aperçu (bai) avec le compositeur de l'agent « robe » sur les vraies cartes
    try:
        preview_albedo(meta)
    except Exception as e:  # pragma: no cover
        log(f"albedo d'aperçu non produit : {type(e).__name__}: {e}")
    log("terminé")


def _json_default(o):
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return str(o)


def preview_albedo(meta):
    from pony import coat_reference as cr

    sys.path.insert(0, str(PIPELINE / "stages"))
    import s05_coat

    maps = {}
    for nm in ("shading", "regions", "params", "patterns"):
        maps[nm] = s05_coat.read_png_any(TEX / f"coat_{nm}.png")
    lm = meta["coat_landmarks"]
    L = cr.Landmarks(coronet=lm["coronet"], face_eye_v=lm["faceEyeV"], face_eye_u=lm["faceEyeU"],
                     nostril_v=lm["nostrilV"])
    alb = cr.compose_body(cr.default_config(), maps, 2048, L)
    save_png(alb[..., :3].copy(), TEX / "coat_albedo_preview.png")
    log("coat_albedo_preview.png (bai, compositeur coat_reference) écrit")


# ==============================================================================================
def previews(args):
    import bpy

    from pony import body_scene, render as R

    bpy.ops.wm.open_mainfile(filepath=str(BLEND), load_ui=False)
    PREV.mkdir(parents=True, exist_ok=True)
    out = Path(args.preview_dir) if args.preview_dir else PREV
    body = bpy.data.objects["Body"]
    mat = body_scene.preview_coat_material(TEX, "coat_albedo_preview.png")
    body.data.materials.clear()
    body.data.materials.append(mat)
    bpy.data.objects["PonyRig"].hide_render = True
    sc = R.setup_stage("CYCLES", samples=args.samples, resolution=(720, 720))
    sc.view_settings.look = "AgX - Base Contrast" if "AgX - Base Contrast" in [
        i.identifier for i in sc.view_settings.bl_rna.properties["look"].enum_items] else sc.view_settings.look
    views = ["left", "right", "front", "back", "three_quarter", "three_quarter_back"]
    paths = []
    for v in views:
        R.place_camera(v, target=(0.0, 0.12, 0.80), distance=4.1, lens=50)
        paths.append(R.render(out / f"tt_{v}.png"))
    R.contact_sheet(paths, out / "body_turnaround.png", cols=3, labels=views, cell=(720, 720))
    close = {
        "head_three_quarter": ((-40.0, 8.0), (0.0, 1.05, 1.28), 1.15),
        "head_left": ((0.0, 2.0), (0.0, 1.05, 1.28), 1.05),
        "head_front": ((-90.0, 6.0), (0.0, 1.10, 1.26), 1.05),
        "eye_close": ((-30.0, 6.0), (-0.085, 1.02, 1.33), 0.42),
        "muzzle_close": ((-50.0, 0.0), (-0.02, 1.20, 1.10), 0.50),
        "foreleg_left": ((0.0, 3.0), (-0.12, 0.42, 0.40), 1.25),
        "hindleg_left": ((0.0, 3.0), (-0.12, -0.56, 0.48), 1.35),
        "legs_front": ((-90.0, 3.0), (0.0, 0.42, 0.40), 1.6),
        "hooves": ((-35.0, 14.0), (-0.115, 0.48, 0.08), 0.55),
    }
    cp = []
    for name, ((az, el), tgt, dist) in close.items():
        R.VIEWS[name] = (az, el)
        R.place_camera(name, target=tgt, distance=dist, lens=50)
        cp.append(R.render(out / f"close_{name}.png"))
    R.contact_sheet(cp[:5], out / "body_head.png", cols=3, labels=list(close)[:5], cell=(720, 720))
    R.contact_sheet(cp[5:], out / "body_limbs.png", cols=2, labels=list(close)[5:], cell=(720, 720))
    # fil de fer basse définition
    wire = body.copy()
    wire.data = body.data.copy()
    bpy.context.scene.collection.objects.link(wire)
    mod = wire.modifiers.new("W", "WIREFRAME")
    mod.thickness = 0.0007
    mod.use_replace = True
    wm = bpy.data.materials.new("WireMat")
    wm.use_nodes = True
    wm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.02, 0.02, 0.025, 1)
    wire.data.materials.clear()
    wire.data.materials.append(wm)
    gm = R.simple_material("GreyClay", (0.62, 0.60, 0.58), 0.6)
    body.data.materials.clear()
    body.data.materials.append(gm)
    for o in ("Lashes",):
        bpy.data.objects[o].hide_render = True
    wp = []
    for name, ((az, el), tgt, dist) in {"wire_left": ((0.0, 4.0), (0.0, 0.12, 0.80), 3.6),
                                        "wire_head": ((-40.0, 8.0), (0.0, 1.05, 1.28), 1.0),
                                        "wire_three_quarter": ((-40.0, 12.0), (0.0, 0.12, 0.80), 3.8),
                                        "wire_hoof": ((-35.0, 14.0), (-0.115, 0.48, 0.10), 0.6)}.items():
        R.VIEWS[name] = (az, el)
        R.place_camera(name, target=tgt, distance=dist, lens=50)
        wp.append(R.render(out / f"{name}.png"))
    R.contact_sheet(wp, out / "body_wireframe.png", cols=2, labels=["left", "head", "three_quarter", "hoof"],
                    cell=(720, 720))
    for p in paths + cp + wp:
        Path(p).unlink(missing_ok=True)
    print("previews done", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--previews", action="store_true", help="rendus seulement (relit body.blend)")
    ap.add_argument("--no-previews", action="store_true")
    ap.add_argument("--quick", action="store_true", help="haute définition grossière")
    ap.add_argument("--target-faces", type=int, default=9600)
    ap.add_argument("--margin-px", type=int, default=12)
    ap.add_argument("--high-h", type=float, default=0.003)
    ap.add_argument("--ao-samples", type=int, default=32)
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--preview-dir", default=None)
    args = ap.parse_args()
    if args.quick:
        args.high_h = 0.005
        args.ao_samples = 16
    if args.previews:
        previews(args)
        return
    build(args)
    if not args.no_previews:
        cmd = [sys.executable, __file__, "--previews", "--samples", str(args.samples)]
        if args.preview_dir:
            cmd += ["--preview-dir", args.preview_dir]
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"rendus : code {r.returncode}", flush=True)
    log("fin")


if __name__ == "__main__":
    main()
