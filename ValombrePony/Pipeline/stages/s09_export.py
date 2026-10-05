"""Étape 9 — export final pour RealityKit (USDZ écrits avec pxr) + données runtime + validation stricte.

Lancement (Python 3.11 avec bpy 4.2 et usd-core) :
    python3 Pipeline/stages/s09_export.py [--build-dir DIR] [--out-dir DIR] [--no-quicklook] [--no-validate] [--glb]
Code de sortie : 0 = tout exporté et validé ; 1 = au moins une validation en échec ; 2 = entrées manquantes
(export partiel, cf. le résumé) ; 3 = erreur fatale.

ENTRÉES ATTENDUES (dans --build-dir, par défaut Pipeline/build/) :
- `rigged_body.blend` : armature `PonyRig` (70 os du SPEC §3, transform identité) + meshes skinnés
  `Body` (M_Coat), `Eyes` (M_Eye), `Mouth` (M_Mouth), `Lashes` (M_Lashes) avec UN modificateur Armature
  (groupes de sommets nommés comme les joints) et les shape keys du SPEC §5 (relatives à Basis).
  Nom USD d'un mesh = propriété `pony_mesh` ou nom de l'objet ; objets `hide_render` ou `pony_export=False`
  ignorés. Les autres modificateurs doivent être appliqués.
  Optionnel : propriété `pony_morphology` (chaîne JSON {"sliders": [...]}) sur l'armature.
- `parts/<id>.blend` : une pièce par fichier (id du SPEC §6), même armature (copie du squelette complet,
  mêmes repères de repos), meshes skinnés de la pièce avec matériaux `slot_primary|slot_secondary|
  slot_accent|slot_metal|fixed_*` (alias journalisé pour les crins : M_Hair -> slot_primary) et shape keys
  nommées comme celles du corps. Un mesh du corps présent dans le fichier (nom Body/Eyes/Mouth/Lashes ou
  matériau M_Coat/M_Eye/M_Mouth/M_Lashes) est ignoré.
- `textures/` : `coat_albedo_default.png`, `coat_normal.png`, `coat_orm.png` (dans Pony.usdz ; prioritaires
  sur les textures du matériau M_Coat) et `coat_shading.png`, `coat_regions.png`, `coat_params.png`,
  `coat_patterns.png` (copiés tels quels pour le runtime). Les chemins relatifs des propriétés `pony_*_tex`
  des matériaux sont résolus dans ce dossier.
- `clips/<nom>.npz` : `local` (F,70,4,4) locales Blender, `weights_names`/`weights` optionnels, `meta` JSON
  (cf. pony/runtime_export.py).
- `morphology.json` (optionnel, prioritaire) : {"sliders": [...]} au format SPEC §9.

SORTIES (dans --out-dir, par défaut PonyKit/Sources/PonyKit/Resources/) :
`Pony.usdz`, `Parts/<id>.usdz`, `PonyRig.json`, `PonyClips.bin`, `coat_shading|regions|params|patterns.png`,
`hair_strands.png` (si présent dans textures/, pour l'albedo des crins recalculé au runtime),
`Pony_QuickLook.usdz` (corps + mane/forelock/tail_natural + bridle_snaffle + saddle_english si présents,
pelage par défaut, clip `walk` en animation). Fichiers intermédiaires et rapport de validation :
`<build-dir>/export/` (staging USDA, `validation_report.json`) ; avec --glb, aperçu web
`<build-dir>/export/Pony_preview.glb` (corps + pièces de l'aperçu + tous les clips ; non livré dans le package).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import traceback
from dataclasses import replace
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import numpy as np  # noqa: E402

from pony import conventions as cv  # noqa: E402
from pony import runtime_export as rx  # noqa: E402
from pony import usd_writer as uw  # noqa: E402
from pony import validate as val  # noqa: E402

BODY_MESHES = dict(val.BODY_MESH_MATERIALS)            # nom USD -> [matériau]
BODY_MAT_TO_MESH = {v[0]: k for k, v in BODY_MESHES.items()}
QUICKLOOK_PARTS = ["mane_natural", "forelock_natural", "tail_natural", "bridle_snaffle", "saddle_english"]
# Alias de matériaux de pièces -> slot du SPEC §6, par catégorie [I] : les crins n'ont qu'un slot
# (« couleur crins » = slot_primary) ; l'agent « hair » nomme son matériau unique M_Hair. Renommage journalisé.
PART_MATERIAL_ALIASES = {"hair": {"M_Hair": "slot_primary"}}
# Textures runtime hors pelage recopiées si présentes (clé du manifeste -> fichier) : l'agent « hair » recalcule
# l'albedo des crins au runtime depuis hair_strands.png (R luminance, G racine->pointe, B aléa, A alpha).
HAIR_RUNTIME_MAPS = {"strands": "hair_strands.png"}
COAT_SPEC_TEX = {"base_color_texture": "coat_albedo_default.png", "normal_texture": "coat_normal.png",
                 "orm_texture": "coat_orm.png"}
# Teintes par défaut de l'aperçu Quick Look [A] (les albedos des pièces sont des détails en niveaux de gris).
QL_TINTS = {"hair": {"slot_primary": (0.09, 0.065, 0.05)},
            "default": {"slot_primary": (0.36, 0.20, 0.09), "slot_secondary": (0.24, 0.13, 0.06),
                        "slot_accent": (0.85, 0.83, 0.78), "slot_metal": (0.80, 0.80, 0.80)}}


class Log:
    def __init__(self):
        self.errors, self.warnings, self.missing, self.notes = [], [], [], []

    def err(self, m):
        self.errors.append(m)
        print("  [ERREUR]", m, flush=True)

    def warn(self, m):
        self.warnings.append(m)
        print("  [avert.]", m, flush=True)

    def miss(self, m):
        self.missing.append(m)
        print("  [ENTRÉE MANQUANTE]", m, flush=True)

    def note(self, m):
        self.notes.append(m)
        print("  ", m, flush=True)


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(cv.PROJECT_DIR))
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------------------------------
# Extraction d'un fichier .blend
# --------------------------------------------------------------------------------------------------


def _open_blend(path: Path):
    import bpy
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)


def _extract_file(path: Path, kind: str, log: Log, tex_root: Path, work_dir: Path, poses_b, shape_w,
                  ref_skeleton=None):
    """Ouvre `path` et extrait squelette, meshes, matériaux et positions de validation.
    kind ∈ {body, part}. Renvoie un dict ou None (avec message)."""
    import bpy
    from pony import blender_extract as bx
    _open_blend(path)
    try:
        arm = bx.find_armature()
    except RuntimeError as e:
        log.err(f"{path.name} : {e}")
        return None
    errs = bx.check_armature(arm)
    for e in errs:
        log.err(f"{path.name} : {e}")
    if errs:
        return None
    skel = bx.extract_skeleton(arm)
    if ref_skeleton is not None:
        d = max(np.abs(skel.bind_world - ref_skeleton.bind_world).max(),
                np.abs(skel.rest_local - ref_skeleton.rest_local).max())
        if d > 1e-5:
            log.err(f"{path.name} : squelette différent de la référence (celui du corps, ou du gabarit si le corps "
                    f"est absent ; écart max des matrices {d:.2e}) — la pièce doit porter une copie exacte du squelette (SPEC §6)")
            return None
    objs = bx.skinned_mesh_objects(arm)
    sel = []
    for o in objs:
        name = bx.usd_mesh_name(o)
        mats = [bx.clean_name(s.material.name) for s in o.material_slots if s.material]
        if kind == "body":
            if name not in BODY_MESHES and len(set(mats)) == 1 and mats[0] in BODY_MAT_TO_MESH:
                log.warn(f"{path.name} : objet {o.name} nommé « {BODY_MAT_TO_MESH[mats[0]]} » d'après son matériau")
                o["pony_mesh"] = BODY_MAT_TO_MESH[mats[0]]
        else:
            if name in BODY_MESHES or any(m in BODY_MAT_TO_MESH for m in mats):
                log.note(f"{path.name} : mesh du corps « {o.name} » ignoré dans la pièce")
                continue
        sel.append(o)
    if not sel:
        log.err(f"{path.name} : aucun mesh skinné à exporter (modificateur Armature visant {arm.name})")
        return None
    bad = False
    for o in sel:
        for e in bx.check_mesh_object(o, arm):
            log.err(e)
            bad = True
    if bad:
        return None
    morph_prop = arm.get("pony_morphology")
    meshes, materials, tints, limit_stats = [], {}, {}, {}
    for o in sel:
        idx, w, st = bx.apply_influence_limit(o, skel.names, uw.MAX_INFLUENCES)
        limit_stats[bx.usd_mesh_name(o)] = st
        if st["zeroWeightVertices"]:
            log.warn(f"{path.name} : {o.name} : {st['zeroWeightVertices']} sommets sans poids -> liés à root")
        md, bmats = bx.extract_mesh(o, skel.names, influences=(idx, w), warnings=log.warnings)
        meshes.append(md)
        for bm in bmats:
            n = bx.clean_name(bm.name)
            if n not in materials:
                materials[n] = bx.extract_material(bm, tex_root, work_dir / "textures_converted", log.warnings)
                tints[n] = bx.material_tint(bm)
    # positions de validation (mêmes poses Blender pour toutes les pièces)
    expected, locals_rk = [], []
    for k, L in enumerate(poses_b):
        bx.set_pose_and_shapes(arm, sel, L, shape_w[k])
        expected.append(bx.evaluated_points_rk(sel))
        locals_rk.append(bx.posed_locals_rk(arm))
    bx.set_pose_and_shapes(arm, sel, poses_b[0], {})
    return {"skeleton": skel, "meshes": meshes, "materials": materials, "tints": tints,
            "expected": expected, "locals_rk": np.array(locals_rk), "limit": limit_stats,
            "morphology_prop": str(morph_prop) if morph_prop else None}


def _template_skeleton():
    """Squelette depuis le gabarit (corps absent) : armature construite dans une scène vide."""
    import bpy
    from pony import blender_extract as bx
    from pony import rig
    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = rig.build_armature()
    return bx.extract_skeleton(arm), arm


# --------------------------------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------------------------------


def run(build_dir: Path, out_dir: Path, quicklook: bool = True, do_validate: bool = True, glb: bool = False) -> dict:
    t0 = time.time()
    log = Log()
    build_dir, out_dir = Path(build_dir), Path(out_dir)
    stage_dir = build_dir / "export"
    stage_dir.mkdir(parents=True, exist_ok=True)
    tex_root = build_dir / "textures"
    body_blend = build_dir / "rigged_body.blend"
    part_blends = sorted((build_dir / "parts").glob("*.blend")) if (build_dir / "parts").is_dir() else []
    clip_files = sorted((build_dir / "clips").glob("*.npz")) if (build_dir / "clips").is_dir() else []
    morph_json = build_dir / "morphology.json"

    print("== Étape 9 : export USDZ + runtime ==")
    print(f"  build : {_rel(build_dir)}   sortie : {_rel(out_dir)}")
    print("== Inventaire des entrées ==")
    if not body_blend.is_file():
        log.miss(f"{_rel(body_blend)} absent : Pony.usdz et Pony_QuickLook.usdz ne seront pas produits ; "
                 "le squelette du gabarit sera utilisé pour PonyRig.json")
    if not part_blends:
        log.miss(f"aucune pièce dans {_rel(build_dir / 'parts')}/*.blend")
    if not clip_files:
        log.miss(f"aucun clip dans {_rel(build_dir / 'clips')}/*.npz (PonyClips.bin sera vide)")
    for k, fn in list(COAT_SPEC_TEX.items()) + list(rx.COAT_RUNTIME_MAPS.items()):
        if not (tex_root / fn).is_file():
            log.miss(f"texture {_rel(tex_root / fn)} absente")
    print(f"  corps : {body_blend.is_file()}  pièces : {[p.stem for p in part_blends]}  clips : {len(clip_files)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "Parts").mkdir(parents=True, exist_ok=True)

    # --- clips (indépendants de bpy) : chargés d'abord pour la pose de validation « walk »
    clip_sources = {}
    for p in clip_files:
        try:
            c = rx.load_clip_npz(p)
            clip_sources[c.name] = c
        except Exception as e:  # noqa: BLE001
            log.err(f"clip {p.name} illisible : {e}")
    walk = clip_sources.get("walk")

    # --- corps
    from pony import blender_extract as bx
    body = None
    poses_b = None
    if body_blend.is_file():
        print("== Corps ==")
        try:
            _open_blend(body_blend)
            arm = bx.find_armature()
            walk_pose = None
            if walk is not None:
                f = walk.frame_count // 3
                walk_pose = walk.local_b[f]
            poses_b = bx.validation_poses(arm, walk_pose)
            bs_names = sorted({kb.name for o in bx.skinned_mesh_objects(arm) if o.data.shape_keys
                               for kb in o.data.shape_keys.key_blocks})
            shape_w = [bx.validation_shape_weights([bx.clean_name(n) for n in bs_names], k) for k in range(len(poses_b))]
            body = _extract_file(body_blend, "body", log, tex_root, stage_dir, poses_b, shape_w)
        except Exception as e:  # noqa: BLE001
            log.err(f"extraction du corps impossible : {type(e).__name__}: {e}")
            traceback.print_exc()
            body = None
    if body is not None:
        skeleton = body["skeleton"]
    else:
        skeleton, arm = _template_skeleton()
        if poses_b is None:
            poses_b = bx.validation_poses(arm, None)
            shape_w = [bx.validation_shape_weights(list(rx.BODY_BLEND_SHAPES), k) for k in range(len(poses_b))]

    results = {"usd": []}
    expect_base = {"joints": skeleton.paths, "bind": skeleton.bind_world, "rest": skeleton.rest_local}
    body_bs_names = []
    blend_shapes_manifest = {}
    validations = []      # (chemin usdz, kind, expect, npz skinning, npz animation | None)

    def skin_npz(name, locals_rk, bs_names, expected_list):
        t, r, s = uw.decompose_trs_batch(locals_rk)
        bw = np.array([[shape_w[k].get(n, 0.0) for n in bs_names] for k in range(len(locals_rk))])
        pts = {mn: np.array([e[mn] for e in expected_list]) for mn in expected_list[0]}
        p = stage_dir / f"skin_{name}.npz"
        val.write_skinning_npz(p, t, r, s, bs_names, bw, pts)
        return p

    if body is not None:
        coat = body["materials"].get("M_Coat")
        if coat is not None:
            for attr, fn in COAT_SPEC_TEX.items():
                f = tex_root / fn
                if f.is_file():
                    setattr(coat, attr, str(f))
                elif getattr(coat, attr):
                    log.warn(f"M_Coat : {fn} absent de {_rel(tex_root)}, texture du matériau Blender utilisée")
        for md in body["meshes"]:
            for b in md.blend_shapes:
                if np.abs(b.offsets).max() < uw.OFFSET_EPS:
                    log.warn(f"corps : blend shape {md.name}/{b.name} sans effet")
            names = [b.name for b in md.blend_shapes]
            if names:
                blend_shapes_manifest[md.name.lower()] = names
        body_bs_names = blend_shapes_manifest.get("body", [])
        missing_bs = [n for n in rx.BODY_BLEND_SHAPES if n not in body_bs_names]
        if missing_bs:
            log.warn(f"corps : blend shapes du SPEC §5 absents de Body : {missing_bs}")
        mats = list(body["materials"].values())
        try:
            info = uw.export_usdz(out_dir / "Pony.usdz", stage_dir / "Pony", root_name="Pony", skeleton=skeleton,
                                  meshes=body["meshes"], materials=mats,
                                  doc="ValombrePony — corps (généré par Pipeline/stages/s09_export.py)")
        except Exception as e:  # noqa: BLE001
            log.err(f"Pony.usdz : écriture impossible : {type(e).__name__}: {e}")
            traceback.print_exc()
            info = None
        if info is not None:
            results["usd"].append(info)
            all_bs = sorted({b.name for md in body["meshes"] for b in md.blend_shapes})
            npz = skin_npz("Pony", body["locals_rk"], all_bs, body["expected"])
            validations.append((out_dir / "Pony.usdz", "body", dict(
                expect_base, blendShapesAllowed=rx.BODY_BLEND_SHAPES, meshMaterials=BODY_MESHES,
                requiredMeshes=["Body"], animation=False), npz, None))
            print(f"  Pony.usdz : {info['triangles']} triangles, {info['package']['bytes'] / 1e6:.2f} Mo")

    # --- pièces
    parts_manifest, ql_parts = [], {}
    for pb in part_blends:
        pid = pb.stem
        print(f"== Pièce {pid} ==")
        try:
            d = _extract_file(pb, "part", log, tex_root, stage_dir, poses_b, shape_w, ref_skeleton=skeleton)
        except Exception as e:  # noqa: BLE001
            log.err(f"pièce {pid} : extraction impossible : {type(e).__name__}: {e}")
            traceback.print_exc()
            d = None
        if d is None:
            continue
        aliases = PART_MATERIAL_ALIASES.get(rx.PART_CATALOG.get(pid, {}).get("category", ""), {})
        for old_name, new_name in aliases.items():
            if old_name in d["materials"] and new_name not in d["materials"]:
                log.warn(f"pièce {pid} : matériau {old_name} renommé {new_name} (SPEC §6, alias [I])")
                d["materials"][new_name] = replace(d["materials"].pop(old_name), name=new_name)
                d["tints"][new_name] = d["tints"].pop(old_name, None)
                for md in d["meshes"]:
                    md.material_names = [new_name if m == old_name else m for m in md.material_names]
        allowed = body_bs_names or rx.BODY_BLEND_SHAPES
        for md in d["meshes"]:
            keep = []
            for b in md.blend_shapes:
                if b.name not in allowed:
                    log.err(f"pièce {pid} : blend shape {b.name!r} inconnu du corps (SPEC §5 : mêmes noms)")
                    keep.append(b)
                elif np.abs(b.offsets).max() < uw.OFFSET_EPS:
                    log.note(f"pièce {pid} : blend shape {b.name} sans effet sur {md.name} — omis")
                else:
                    keep.append(b)
            md.blend_shapes = keep
        bad_mats = [m for m in d["materials"] if m not in rx.MATERIAL_SLOTS and not m.startswith("fixed_")]
        if bad_mats:
            log.err(f"pièce {pid} : matériaux hors convention slot_*/fixed_* : {bad_mats}")
        try:
            info = uw.export_usdz(out_dir / "Parts" / f"{pid}.usdz", stage_dir / "Parts" / pid, root_name="Pony",
                                  skeleton=skeleton, meshes=d["meshes"], materials=list(d["materials"].values()),
                                  doc=f"ValombrePony — pièce {pid}")
        except Exception as e:  # noqa: BLE001
            log.err(f"pièce {pid} : écriture USD impossible : {e}")
            continue
        results["usd"].append(info)
        part_bs = sorted({b.name for md in d["meshes"] for b in md.blend_shapes})
        npz = skin_npz(f"part_{pid}", d["locals_rk"], part_bs, d["expected"])
        validations.append((out_dir / "Parts" / f"{pid}.usdz", "part", dict(
            expect_base, blendShapesAllowed=list(allowed), meshMaterials=None, materialsAllowed=rx.MATERIAL_SLOTS,
            materialPrefixAllowed=["fixed_"], requiredMeshes=[], animation=False), npz, None))
        parts_manifest.append(rx.part_manifest_entry(pid, list(d["materials"]), part_bs, log.warnings))
        if pid in QUICKLOOK_PARTS:
            ql_parts[pid] = d
        print(f"  Parts/{pid}.usdz : {info['triangles']} triangles, {info['package']['bytes'] / 1e6:.2f} Mo")

    # --- clips
    print("== Clips ==")
    sources, bins, clip_entries, bin_size = rx.export_clips(clip_files, skeleton, out_dir / "PonyClips.bin",
                                                            log.warnings)
    print(f"  PonyClips.bin : {len(bins)} clip(s), {bin_size} octets")

    # --- cartes de pelage runtime
    coat_maps = {}
    for key, fn in rx.COAT_RUNTIME_MAPS.items():
        src = tex_root / fn
        if src.is_file():
            shutil.copyfile(src, out_dir / fn)
            coat_maps[key] = fn

    hair_maps = {}
    for key, fn in HAIR_RUNTIME_MAPS.items():
        src = tex_root / fn
        if src.is_file():
            shutil.copyfile(src, out_dir / fn)
            hair_maps[key] = fn

    # --- morphologie
    provided = None
    if morph_json.is_file():
        provided = json.loads(morph_json.read_text(encoding="utf-8"))
    elif body is not None and body.get("morphology_prop"):
        provided = json.loads(body["morphology_prop"])
    elif body is not None:
        log.miss(f"{_rel(morph_json)} absent (ni propriété pony_morphology) : curseurs sans décalages de joints")
    morphology = rx.build_morphology(body_bs_names, provided, skeleton.names, log.warnings)

    # --- PonyRig.json
    if not blend_shapes_manifest:
        blend_shapes_manifest = {"body": []}
    manifest = rx.build_rig_manifest(skeleton, blend_shapes_manifest, parts_manifest, clip_entries, morphology,
                                     coat_maps)
    if hair_maps:
        manifest["hair"] = {"maps": hair_maps}
    rig_size = rx.write_rig_json(out_dir / "PonyRig.json", manifest)
    print(f"  PonyRig.json : {rig_size} octets")

    # --- aperçu Quick Look
    if quicklook and body is not None:
        print("== Pony_QuickLook.usdz ==")
        ql_meshes = [replace(m) for m in body["meshes"]]
        ql_mats = [replace(m) for m in body["materials"].values()]
        expected = [dict(e) for e in body["expected"]]
        for pid in QUICKLOOK_PARTS:
            if pid not in ql_parts:
                log.note(f"aperçu : pièce {pid} absente — non incluse")
                continue
            d = ql_parts[pid]
            cat = rx.PART_CATALOG.get(pid, {}).get("category", "default")
            ren = {}
            for mn, m in d["materials"].items():
                nm = replace(m, name=f"{pid}__{mn}")
                tint = d["tints"].get(mn) or QL_TINTS.get(cat, QL_TINTS["default"]).get(mn) \
                    or QL_TINTS["default"].get(mn)
                if tint is not None:
                    # comme au runtime : teinte × texture en niveaux de gris, ou teinte seule sans texture
                    if nm.base_color_texture:
                        nm.base_color_scale = tuple(tint)
                    else:
                        nm.base_color = tuple(tint)
                ren[mn] = nm.name
                ql_mats.append(nm)
            for md in d["meshes"]:
                nmd = replace(md, name=f"{pid}__{md.name}", material_names=[ren[x] for x in md.material_names])
                ql_meshes.append(nmd)
                for k in range(len(expected)):
                    expected[k][nmd.name] = d["expected"][k][md.name]
        anim = None
        anim_npz = None
        if walk is not None:
            loc = rx.clip_locals_rk(walk.local_b)
            anim_npz = stage_dir / "anim_QuickLook.npz"
            np.savez(anim_npz, locals=loc)
            T, R, S = uw.decompose_trs_batch(loc)
            names = [n for n in walk.weight_names if n in body_bs_names]
            W = None
            if names:
                W = np.stack([walk.weights[:, walk.weight_names.index(n)] for n in names], 1)
            anim = uw.AnimationData(name="walk", translations=T, rotations_xyzw=R, scales=S,
                                    blend_shape_names=names, blend_shape_weights=W, loop=walk.loop)
        else:
            log.miss("clip walk absent : Pony_QuickLook.usdz sans animation")
        try:
            info = uw.export_usdz(out_dir / "Pony_QuickLook.usdz", stage_dir / "QuickLook", root_name="Pony",
                                  skeleton=skeleton, meshes=ql_meshes, materials=ql_mats, animation=anim,
                                  doc="ValombrePony — aperçu Quick Look (corps + crins + filet + selle, walk)")
        except Exception as e:  # noqa: BLE001
            log.err(f"Pony_QuickLook.usdz : écriture impossible : {type(e).__name__}: {e}")
            traceback.print_exc()
            info = None
        if info is not None:
            results["usd"].append(info)
            all_bs = sorted({b.name for md in ql_meshes for b in md.blend_shapes})
            npz = skin_npz("QuickLook", body["locals_rk"], all_bs, expected)
            validations.append((out_dir / "Pony_QuickLook.usdz", "quicklook", dict(
                expect_base, blendShapesAllowed=rx.BODY_BLEND_SHAPES, meshMaterials=None,
                requiredMeshes=["Body"], animation=anim is not None), npz, anim_npz))
            print(f"  Pony_QuickLook.usdz : {info['triangles']} triangles, {info['package']['bytes'] / 1e6:.2f} Mo")

    # --- validation
    ok = True
    report = {"errors": log.errors, "warnings": log.warnings, "missing": log.missing, "notes": log.notes,
              "usd": [], "clips": None, "rig": None, "sizes": None, "export": results["usd"]}
    if do_validate:
        print("== Validation ==")
        for path, kind, expect, npz, anpz in validations:
            r = val.validate_usd(path, kind, expect, npz, anim_npz=anpz)
            report["usd"].append(r)
            print(val.format_usd_result(r), flush=True)
            ok &= r["ok"]
        rt = val.validate_clips_roundtrip(out_dir / "PonyClips.bin", sources, bins, skeleton)
        report["clips"] = rt
        print(f"[{'PASS' if rt['ok'] else 'FAIL'}] PonyClips.bin aller-retour : "
              + "; ".join(f"{c['name']}: pistes={c['tracks']} (const {c['constTracks']}) bin={c['writtenVsRead']:.1e} "
                          f"pose={c['poseReconstruction']:.1e}" for c in rt["clips"]) + (f" {rt['errors']}" if rt["errors"] else ""))
        ok &= rt["ok"]
        rj = val.validate_rig_json(out_dir / "PonyRig.json", skeleton, bins, out_dir)
        report["rig"] = rj
        print(f"[{'PASS' if rj['ok'] else 'FAIL'}] PonyRig.json : {rj['errors'] or 'cohérent'}"
              + (f" ; avert. {rj['warnings']}" if rj["warnings"] else ""))
        ok &= rj["ok"]
        lim = val.SIZE_LIMITS
        files = {out_dir / "Pony.usdz": lim["Pony.usdz"], out_dir / "Pony_QuickLook.usdz": lim["Pony_QuickLook.usdz"],
                 out_dir / "PonyClips.bin": lim["PonyClips.bin"], out_dir / "PonyRig.json": lim["PonyRig.json"]}
        for p in (out_dir / "Parts").glob("*.usdz"):
            files[p] = lim["part"]
        for fn in list(rx.COAT_RUNTIME_MAPS.values()) + list(HAIR_RUNTIME_MAPS.values()):
            files[out_dir / fn] = lim["coat_png"]
        sz = val.check_sizes(files)
        report["sizes"] = sz
        print(f"[{'PASS' if sz['ok'] else 'FAIL'}] tailles : " +
              ", ".join(f"{k} {v / 1e6:.2f} Mo" for k, v in sz["bytes"].items()) + (f" {sz['errors']}" if sz["errors"] else ""))
        ok &= sz["ok"]
    if glb:
        print("== Aperçu GLB ==")
        if body is None:
            log.warn("GLB non produit : corps absent")
        else:
            try:
                from pony import gltf_export
                gi = gltf_export.run_in_subprocess(build_dir, stage_dir / "Pony_preview.glb", QUICKLOOK_PARTS,
                                                   clip_files)
                report["glb"] = gi
                print(f"  {_rel(stage_dir / 'Pony_preview.glb')} : {gi['bytes'] / 1e6:.2f} Mo, meshes "
                      f"{[(m['name'], m['vertices'], len(m['morphTargets'])) for m in gi['meshes']]}, "
                      f"skins {gi['skins']}, animations {[a['name'] for a in gi['animations']]}")
            except Exception as e:  # noqa: BLE001 — aperçu optionnel : n'invalide pas l'export
                log.warn(f"GLB : échec de l'export ({type(e).__name__}: {e})")
    ok &= not log.errors
    report["ok"] = bool(ok)
    report["seconds"] = round(time.time() - t0, 1)
    (stage_dir / "validation_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    print("== Résumé ==")
    print(f"  erreurs : {len(log.errors)}  avertissements : {len(log.warnings)}  entrées manquantes : {len(log.missing)}")
    for m in log.missing:
        print("   - manquant :", m)
    for w in dict.fromkeys(log.warnings):
        print("   - avertissement :", w)
    for e in log.errors:
        print("   - erreur :", e)
    print(f"  rapport : {_rel(stage_dir / 'validation_report.json')}  ({report['seconds']} s)")
    status = 1 if not ok else (2 if log.missing else 0)
    print(f"  STATUT : {'OK' if status == 0 else ('PARTIEL (entrées manquantes)' if status == 2 else 'ÉCHEC')}")
    report["status"] = status
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--build-dir", default=str(cv.BUILD_DIR))
    ap.add_argument("--out-dir", default=str(cv.RESOURCES_DIR))
    ap.add_argument("--no-quicklook", action="store_true")
    ap.add_argument("--no-validate", action="store_true")
    ap.add_argument("--glb", action="store_true", help="exporte aussi un aperçu web GLB (optionnel)")
    a = ap.parse_args(argv)
    try:
        rep = run(Path(a.build_dir), Path(a.out_dir), quicklook=not a.no_quicklook, do_validate=not a.no_validate,
                  glb=a.glb)
    except Exception as e:  # noqa: BLE001
        print(f"ERREUR FATALE : {type(e).__name__}: {e}")
        traceback.print_exc()
        return 3
    return int(rep["status"])


if __name__ == "__main__":
    sys.exit(main())
