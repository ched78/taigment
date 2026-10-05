"""Validation stricte des livrables (Docs/SPEC.md §10 : « Validation obligatoire à chaque build »).

Pour chaque USD/USDZ (exécuté dans un PROCESSUS SÉPARÉ : `Usd.Stage.Open` renverrait sinon une couche
déjà ouverte/éditée dans le processus courant et masquerait des erreurs — piège documenté dans
Docs/research/usd.md §3.2) :
  1. vérificateur ARKit vendorisé (OpenUSD v26.05, `Pipeline/vendor/complianceChecker_v26_05.py`,
     `arkit=True`) — on lit `GetFailedChecks()` ET `GetErrors()` (les échecs de règles sont dans le premier) ;
  2. `UsdValidation` : tous les validateurs enregistrés (28 dans usd-core 26.8) ;
  3. structure et noms (SPEC §1, §3, §4, §5, §6, §10) : métadonnées, un seul SkelRoot/Skeleton, tokens et
     bindTransforms identiques au squelette de référence, influences ≤ 4 triées/normalisées, normales et UV
     faceVarying, doubleSided=false, subdivisionScheme=none, blend shapes (normalOffsets, pointIndices, pas
     d'in-between), matériaux (PNG, espaces de couleur, normal map scale/bias, wrap repeat, ≤ 1 texture
     empaquetée), noms de meshes/matériaux/blend shapes ;
  4. skinning numérique : UsdSkel (SkinningQuery + BlendShapeQuery, et BakeSkinning en contre-vérification)
     comparé aux positions évaluées par Blender pour K ≥ 3 poses (tolérance 1e-4 m).
Hors USD (dans le processus courant) : aller-retour de `PonyClips.bin`, cohérence de `PonyRig.json`,
tailles de fichiers.

Usage interne du processus enfant : `python3 validate.py --child <args.json>` (imprime une ligne JSON
préfixée par RESULT_MARK). Le mode enfant n'importe que la bibliothèque standard, numpy, PIL et pxr.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
VENDOR_CHECKER = HERE.parent / "vendor" / "complianceChecker_v26_05.py"
RESULT_MARK = "@@PONY_VALIDATE@@"
SKIN_TOL = 1e-4                 # m (SPEC §10)
MIN_POSES = 3

# Limites de taille [I] : garde-fous du pipeline, pas des limites Apple documentées.
SIZE_LIMITS = {
    "Pony.usdz": 60e6, "Pony_QuickLook.usdz": 80e6, "PonyClips.bin": 16e6, "PonyRig.json": 2e6,
    "part": 15e6, "coat_png": 8e6,
}

BODY_MESH_MATERIALS = {"Body": ["M_Coat"], "Eyes": ["M_Eye"], "Mouth": ["M_Mouth"], "Lashes": ["M_Lashes"]}
PART_MATERIALS = ["slot_primary", "slot_secondary", "slot_accent", "slot_metal"]


# ==================================================================================================
# Côté parent
# ==================================================================================================


def write_skinning_npz(path, t, r, s, bs_names, bs_weights, points: dict):
    """Poses de contrôle (K poses) : locales RK décomposées t (K,N,3), r (K,N,4 xyzw), s (K,N,3),
    poids de blend shapes (K,W) et positions attendues (évaluées par Blender, espace RK) par mesh USD."""
    arrays = {"t": np.asarray(t, np.float64), "r": np.asarray(r, np.float64), "s": np.asarray(s, np.float64),
              "bs_names": np.array(list(bs_names), dtype=str),
              "bs_weights": np.asarray(bs_weights, np.float64).reshape(len(t), len(bs_names))}
    for name, p in points.items():
        arrays["points__" + name] = np.asarray(p, np.float64)
    np.savez(path, **arrays)


def validate_usd(path, kind: str, expect: dict, skin_npz=None, timeout: int = 900, anim_npz=None) -> dict:
    """Valide un USD/USDZ dans un processus séparé. `kind` ∈ {body, part, quicklook}.
    `expect` : {"joints": [chemins], "bind": (N,4,4) RK, "rest": (N,4,4) RK, "blendShapesAllowed": [...] | None,
                "meshMaterials": {mesh: [matériaux]} | None, "materialsAllowed": [...] | None,
                "materialPrefixAllowed": [...], "requiredMeshes": [...], "animation": bool}"""
    path = str(path)
    with tempfile.TemporaryDirectory(prefix="pony_validate_") as td:
        ref = os.path.join(td, "ref.npz")
        np.savez(ref, bind=np.asarray(expect["bind"], np.float64), rest=np.asarray(expect["rest"], np.float64))
        args = {"path": path, "kind": kind, "ref_npz": ref, "skin_npz": str(skin_npz) if skin_npz else None,
                "anim_npz": str(anim_npz) if anim_npz else None,
                "checker": str(VENDOR_CHECKER),
                "expect": {k: v for k, v in expect.items() if k not in ("bind", "rest")}}
        a = os.path.join(td, "args.json")
        Path(a).write_text(json.dumps(args))
        t0 = time.time()
        env = dict(os.environ)
        env.setdefault("PYTHONWARNINGS", "ignore::DeprecationWarning")
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", a], capture_output=True,
                              text=True, timeout=timeout, env=env)
    res = None
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_MARK):
            res = json.loads(line[len(RESULT_MARK):])
    if res is None:
        return {"file": path, "kind": kind, "ok": False,
                "fatal": f"processus de validation sans résultat (code {proc.returncode})",
                "stderr": proc.stderr[-4000:], "stdout": proc.stdout[-2000:]}
    res["seconds"] = round(time.time() - t0, 2)
    res["ok"] = _usd_ok(res)
    return res


def _usd_ok(res: dict) -> bool:
    if res.get("fatal"):
        return False
    if not res["arkit"]["pass"]:
        return False
    if res["usdValidation"]["count"] != 0:
        return False
    if res["structure"]["errors"]:
        return False
    sk = res.get("skinning")
    if sk is not None and not sk.get("pass", False):
        return False
    an = res.get("animation")
    if an is not None and not an.get("pass", False):
        return False
    return True


def validate_clips_roundtrip(bin_path, sources, bins, skeleton) -> dict:
    """Relit PonyClips.bin et compare (1) aux structures écrites, (2) aux poses sources reconstruites."""
    from .runtime_export import clip_locals_rk, expand_clip, read_clips_bin, resolve_mask
    errors = []
    read = read_clips_bin(bin_path)
    if [c.name for c in read] != [c.name for c in bins]:
        errors.append(f"noms des clips relus {[c.name for c in read]} ≠ écrits {[c.name for c in bins]}")
    stats = []
    for src, wb, rb in zip(sources, bins, read):
        e = {}
        if (rb.frame_count, rb.fps) != (wb.frame_count, np.float32(wb.fps)):
            errors.append(f"{rb.name} : frameCount/fps relus {rb.frame_count}/{rb.fps}")
        if [(t.joint, t.flags) for t in rb.tracks] != [(t.joint, t.flags) for t in wb.tracks]:
            errors.append(f"{rb.name} : pistes (joint, flags) différentes après relecture")
        bit = 0.0
        for tw, tr in zip(wb.tracks, rb.tracks):
            for a, b in ((tw.t, tr.t), (tw.r, tr.r), (tw.s, tr.s)):
                if a is not None:
                    bit = max(bit, float(np.abs(np.asarray(a, np.float32) - b).max()))
        e["writtenVsRead"] = bit
        mask = resolve_mask(src.meta.get("mask"), skeleton.names)
        rec = expand_clip(rb, skeleton.rest_local)
        ref = clip_locals_rk(src.local_b)
        cols = list(range(len(skeleton.names))) if mask is None else [skeleton.names.index(m) for m in mask]
        err = float(np.abs(rec[:, cols] - ref[:, cols]).max())
        e["poseReconstruction"] = err
        if bit > 0.0:
            errors.append(f"{rb.name} : relecture binaire non exacte ({bit:.2e})")
        if err > 1e-5:
            errors.append(f"{rb.name} : poses reconstruites ≠ source ({err:.2e} > 1e-5)")
        wsrc = dict(wb.weights)
        for wn, w in rb.weights:
            d = float(np.abs(np.asarray(wsrc[wn], np.float32) - w).max())
            e.setdefault("weights", 0.0)
            e["weights"] = max(e["weights"], d)
            if d > 0:
                errors.append(f"{rb.name} : poids {wn} différents après relecture")
        e.update(name=rb.name, tracks=len(rb.tracks), frames=rb.frame_count,
                 constTracks=sum(1 for t in rb.tracks if t.flags & 56))
        stats.append(e)
    return {"ok": not errors, "errors": errors, "clips": stats}


def validate_rig_json(path, skeleton, clip_bins, resources_dir) -> dict:
    """Cohérence de PonyRig.json avec le squelette, les clips et les fichiers présents."""
    from . import template
    from .runtime_export import BODY_BLEND_SHAPES, COAT_REGIONS, MATERIAL_SLOTS
    from .usd_writer import compose_trs
    errors, warns = [], []
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    for k in ("format", "version", "units", "upAxis", "forward", "fps", "joints", "blendShapes", "parts", "clips",
              "procedural", "morphology", "coat"):
        if k not in m:
            errors.append(f"clé manquante : {k}")
    if m.get("format") != "ValombrePonyRig" or m.get("version") != 1 or m.get("upAxis") != "Y" \
            or m.get("forward") != "-Z" or m.get("fps") != 30:
        errors.append("en-tête différent du SPEC §9")
    joints = m.get("joints", [])
    if [j["name"] for j in joints] != list(template.JOINT_NAMES):
        errors.append("joints : noms/ordre ≠ template.JOINT_NAMES (SPEC §3)")
    for i, j in enumerate(joints):
        if j["parent"] != skeleton.parents[i] or j["path"] != skeleton.paths[i]:
            errors.append(f"joint {j['name']} : parent/chemin incohérent")
        bm = np.array(j["bindModel"], dtype=np.float64).reshape(4, 4).T
        if np.abs(bm - skeleton.bind_world[i]).max() > 1e-5:
            errors.append(f"joint {j['name']} : bindModel ≠ bindTransform")
        rl = compose_trs(j["rest"]["t"], j["rest"]["r"], j["rest"]["s"])
        if np.abs(rl - skeleton.rest_local[i]).max() > 1e-5:
            errors.append(f"joint {j['name']} : rest ≠ restTransform")
    names = set(template.JOINT_NAMES)
    for grp, lst in m.get("blendShapes", {}).items():
        bad = [b for b in lst if b not in BODY_BLEND_SHAPES]
        if bad:
            errors.append(f"blendShapes.{grp} : noms hors SPEC §5 {bad}")
    body_bs = set(m.get("blendShapes", {}).get("body", []))
    for p in m.get("parts", []):
        f = Path(resources_dir) / p["file"]
        if not f.is_file():
            errors.append(f"pièce {p['id']} : fichier absent {p['file']}")
        bad = [s for s in p.get("materialSlots", []) if s not in MATERIAL_SLOTS]
        if bad:
            errors.append(f"pièce {p['id']} : slots invalides {bad}")
        if body_bs and not set(p.get("blendShapes", [])) <= body_bs:
            errors.append(f"pièce {p['id']} : blend shapes absents du corps {sorted(set(p['blendShapes']) - body_bs)}")
        ids = {q["id"] for q in m["parts"]}
        for ref in p.get("conflicts", []) + p.get("requires", []) + p.get("hides", []):
            if ref not in ids:
                warns.append(f"pièce {p['id']} : référence {ref} non exportée (règle conservée)")
    clips = m.get("clips", [])
    if [c["name"] for c in clips] != [c.name for c in clip_bins]:
        errors.append("clips du manifeste ≠ clips de PonyClips.bin (noms/ordre)")
    for c, b in zip(clips, clip_bins):
        if c["frameCount"] != b.frame_count:
            errors.append(f"clip {c['name']} : frameCount {c['frameCount']} ≠ binaire {b.frame_count}")
        if c.get("mask") is not None and any(x not in names for x in c["mask"]):
            errors.append(f"clip {c['name']} : masque avec joints inconnus")
        if len(c.get("rootVelocity", [])) != 3:
            errors.append(f"clip {c['name']} : rootVelocity doit avoir 3 composantes")
    proc = m.get("procedural", {})
    pj = [d["joint"] for d in proc.get("lookChain", [])] + proc.get("tail", []) + proc.get("mane", []) \
        + proc.get("forelock", []) + proc.get("eyes", []) + [proc.get("jaw")]
    bad = [x for x in pj if x not in names]
    if bad:
        errors.append(f"procedural : joints inconnus {bad}")
    for s in m.get("morphology", {}).get("sliders", []):
        for key in ("jointOffsetsPlus", "jointOffsetsMinus"):
            for jn, v in (s.get(key) or {}).items():
                if jn not in names or len(v) != 3:
                    errors.append(f"morphologie {s.get('id')} : décalage invalide {jn}={v}")
    if m.get("coat", {}).get("regions") != COAT_REGIONS:
        errors.append("coat.regions ≠ liste du SPEC §4")
    for grp in ("coat", "hair"):
        for k, fn in m.get(grp, {}).get("maps", {}).items():
            if not (Path(resources_dir) / fn).is_file():
                errors.append(f"{grp}.maps.{k} : fichier absent {fn}")
    return {"ok": not errors, "errors": errors, "warnings": warns}


def check_sizes(files: dict) -> dict:
    """files : {chemin: limite en octets}."""
    out, errors = {}, []
    for p, lim in files.items():
        p = Path(p)
        if not p.exists():
            continue
        sz = p.stat().st_size
        out[p.name if p.parent.name != "Parts" else "Parts/" + p.name] = sz
        if sz > lim:
            errors.append(f"{p.name} : {sz / 1e6:.1f} Mo > limite {lim / 1e6:.0f} Mo [I]")
    return {"ok": not errors, "errors": errors, "bytes": out}


def format_usd_result(r: dict) -> str:
    lines = [f"[{'PASS' if r['ok'] else 'FAIL'}] {Path(r['file']).name} ({r['kind']}, {r.get('seconds', '?')} s)"]
    if r.get("fatal"):
        lines.append(f"    FATAL : {r['fatal']}\n    {r.get('stderr', '')[-1500:]}")
        return "\n".join(lines)
    a = r["arkit"]
    lines.append(f"    ARKit v26.05 : {'PASS' if a['pass'] else 'FAIL'} failed={a['failed']} errors={a['errors']}"
                 + (f" warnings={a['warnings']}" if a['warnings'] else ""))
    u = r["usdValidation"]
    lines.append(f"    UsdValidation : {u['count']} problème(s) {u['issues'][:6]}")
    st = r["structure"]
    lines.append(f"    Structure : {len(st['errors'])} erreur(s) {st['errors'][:8]}"
                 + (f" ; avertissements {st['warnings'][:6]}" if st['warnings'] else ""))
    inf = st.get("info", {})
    if inf:
        lines.append(f"    Contenu : {json.dumps(inf, ensure_ascii=False)[:600]}")
    an = r.get("animation")
    if an is not None:
        lines.append(f"    Animation : {'PASS' if an.get('pass') else 'FAIL'} frames={an.get('frames')} "
                     f"max|locales USD − clip|={an.get('maxLocalError', float('nan')):.2e} "
                     f"bouclage={an.get('loopError')}")
    sk = r.get("skinning")
    if sk is not None:
        lines.append(f"    Skinning : {'PASS' if sk.get('pass') else 'FAIL'} poses={sk.get('poses')} "
                     f"max|USD−Blender| SkinningQuery={sk.get('maxErrorQuery', float('nan')):.3e} m, "
                     f"BakeSkinning={sk.get('maxErrorBake', float('nan')):.3e} m (tol {SKIN_TOL:g})"
                     + (f" ; {sk.get('errors')}" if sk.get("errors") else ""))
    return "\n".join(lines)


# ==================================================================================================
# Côté enfant (processus séparé) — stdlib + numpy + PIL + pxr uniquement
# ==================================================================================================


def _child_main(args_path: str):
    import importlib.util
    import warnings as _w
    args = json.loads(Path(args_path).read_text())
    path = args["path"]
    out = {"file": path, "kind": args["kind"]}
    try:
        from pxr import Usd, UsdValidation

        # 1. ARKit (fichier sur disque, avant toute ouverture dans ce processus)
        spec = importlib.util.spec_from_file_location("cc2605", args["checker"])
        cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cc)
        with _w.catch_warnings():
            _w.simplefilter("ignore", DeprecationWarning)
            c = cc.ComplianceChecker(arkit=True)
        c.CheckCompliance(path)
        failed, errors, warns = list(c.GetFailedChecks()), list(c.GetErrors()), list(c.GetWarnings())
        out["arkit"] = {"pass": not failed and not errors, "failed": failed, "errors": errors, "warnings": warns}

        # 2. UsdValidation
        stage = Usd.Stage.Open(path)
        ctx = UsdValidation.ValidationContext(UsdValidation.ValidationRegistry().GetOrLoadAllValidators())
        issues = ctx.Validate(stage)
        out["usdValidation"] = {"count": len(issues),
                                "issues": [f"{e.GetName()}: {e.GetMessage()[:200]}" for e in issues]}

        # 3. structure
        ref = np.load(args["ref_npz"])
        out["structure"] = _child_structure(stage, args["kind"], args["expect"], ref["bind"], ref["rest"])

        # 4. animation d'aperçu (avant toute édition de la couche de session)
        if args.get("anim_npz"):
            out["animation"] = _child_animation(stage, args["anim_npz"])
        # 5. skinning
        if args.get("skin_npz"):
            out["skinning"] = _child_skinning(stage, args["skin_npz"])
    except Exception as e:  # noqa: BLE001
        import traceback
        out["fatal"] = f"{type(e).__name__}: {e}"
        out["traceback"] = traceback.format_exc()[-3000:]
    print(RESULT_MARK + json.dumps(out, default=float))


def _gf_to_np(m) -> np.ndarray:
    """Gf.Matrix4d (convention ligne) -> numpy convention colonne."""
    return np.array(m, dtype=np.float64).T


def _child_structure(stage, kind, expect, ref_bind, ref_rest) -> dict:
    from pxr import Ar, Sdf, Usd, UsdGeom, UsdShade, UsdSkel
    E, W, info = [], [], {}
    # --- métadonnées (SPEC §1, §10)
    if UsdGeom.GetStageUpAxis(stage) != "Y":
        E.append("upAxis ≠ Y")
    if UsdGeom.GetStageMetersPerUnit(stage) != 1.0:
        E.append("metersPerUnit ≠ 1")
    if stage.GetTimeCodesPerSecond() != 30 or stage.GetFramesPerSecond() != 30:
        E.append(f"timeCodesPerSecond/framesPerSecond = {stage.GetTimeCodesPerSecond()}/{stage.GetFramesPerSecond()} ≠ 30")
    dp = stage.GetDefaultPrim()
    if not dp:
        E.append("defaultPrim absent")
    elif Usd.ModelAPI(dp).GetKind() != "component":
        E.append("defaultPrim : kind ≠ component")
    if dp and dp.GetName() != "Pony":
        E.append(f"defaultPrim = {dp.GetName()} (attendu Pony)")

    prims = list(stage.Traverse())
    roots = [p for p in prims if p.IsA(UsdSkel.Root)]
    skels = [p for p in prims if p.IsA(UsdSkel.Skeleton)]
    anims = [p for p in prims if p.IsA(UsdSkel.Animation)]
    meshes = [p for p in prims if p.IsA(UsdGeom.Mesh)]
    if len(roots) != 1 or len(skels) != 1:
        E.append(f"attendu 1 SkelRoot et 1 Skeleton, trouvé {len(roots)} / {len(skels)}")
        return {"errors": E, "warnings": W, "info": info}
    skel = UsdSkel.Skeleton(skels[0])
    joints = list(skel.GetJointsAttr().Get())
    if joints != list(expect["joints"]):
        E.append("Skeleton.joints ≠ tokens attendus (noms/ordre, SPEC §3)")
    ok, why = UsdSkel.Topology(skel.GetJointsAttr().Get()).Validate()
    if not ok:
        E.append(f"topologie invalide : {why}")
    bind = np.array([_gf_to_np(m) for m in skel.GetBindTransformsAttr().Get()])
    rest = np.array([_gf_to_np(m) for m in skel.GetRestTransformsAttr().Get()])
    if bind.shape != ref_bind.shape or np.abs(bind - ref_bind).max() > 1e-6:
        E.append("bindTransforms ≠ squelette de référence (copie du squelette complet exigée, SPEC §6)")
    if rest.shape != ref_rest.shape or np.abs(rest - ref_rest).max() > 1e-6:
        E.append("restTransforms ≠ squelette de référence")
    # cohérence repos/liaison : composer les locales de repos redonne les repères de liaison
    parents = [-1 if "/" not in j else joints.index(j.rsplit("/", 1)[0]) for j in joints]
    world = np.empty_like(rest)
    for i, p in enumerate(parents):
        world[i] = rest[i] if p < 0 else world[p] @ rest[i]
    d = float(np.abs(world - bind).max()) if len(bind) else 0.0
    info["restVsBind"] = d
    if d > 1e-5:
        E.append(f"restTransforms composés ≠ bindTransforms ({d:.2e})")

    want_anim = bool(expect.get("animation", False))
    if want_anim and not anims:
        E.append("animation attendue (aperçu Quick Look) absente")
    if not want_anim and anims:
        E.append("SkelAnimation présente dans un fichier runtime (PonyKit écrit lui-même les poses, SPEC §0)")
    if anims:
        src = UsdSkel.BindingAPI(skels[0]).GetAnimationSourceRel().GetTargets()
        if not src or src[0] != anims[0].GetPath():
            E.append("skel:animationSource ne cible pas la SkelAnimation")
        a = UsdSkel.Animation(anims[0])
        info["animation"] = {"name": anims[0].GetName(), "samples": a.GetRotationsAttr().GetNumTimeSamples(),
                             "range": [stage.GetStartTimeCode(), stage.GetEndTimeCode()]}
        for attr in (a.GetTranslationsAttr(), a.GetRotationsAttr(), a.GetScalesAttr()):
            if not attr.HasAuthoredValue() and attr.GetNumTimeSamples() == 0:
                E.append(f"SkelAnimation : {attr.GetName()} non authored")

    allowed_bs = expect.get("blendShapesAllowed")
    mesh_mats = expect.get("meshMaterials")
    mats_allowed = expect.get("materialsAllowed")
    prefixes = tuple(expect.get("materialPrefixAllowed", []))
    n_joints = len(joints)
    info["meshes"] = {}
    for mp in meshes:
        name = mp.GetName()
        mesh = UsdGeom.Mesh(mp)
        mi = {}
        if mesh_mats is not None and name not in mesh_mats:
            E.append(f"mesh {name} : nom non prévu (attendus {sorted(mesh_mats)})")
        if UsdSkel.Root.Find(mp).GetPrim() != roots[0]:
            E.append(f"mesh {name} hors du SkelRoot")
        applied = mp.GetAppliedSchemas()
        for api in ("SkelBindingAPI", "MaterialBindingAPI"):
            if api not in applied:
                E.append(f"mesh {name} : {api} non appliqué")
        b = UsdSkel.BindingAPI(mp)
        if [str(t) for t in b.GetSkeletonRel().GetTargets()] != [str(skels[0].GetPath())]:
            E.append(f"mesh {name} : skel:skeleton ne cible pas le Skeleton")
        pts = np.array(mesh.GetPointsAttr().Get(), dtype=np.float64)
        counts = np.array(mesh.GetFaceVertexCountsAttr().Get())
        n_loops = int(counts.sum())
        mi.update(points=len(pts), faces=len(counts), triangles=int((counts - 2).sum()))
        if mesh.GetDoubleSidedAttr().Get() is not False or not mesh.GetDoubleSidedAttr().HasAuthoredValue():
            E.append(f"mesh {name} : doubleSided doit être authored à false")
        if mesh.GetSubdivisionSchemeAttr().Get() != "none" or not mesh.GetSubdivisionSchemeAttr().HasAuthoredValue():
            E.append(f"mesh {name} : subdivisionScheme doit être authored à none")
        nrm = mesh.GetNormalsAttr().Get()
        if nrm is None or mesh.GetNormalsInterpolation() != "faceVarying" or len(nrm) != n_loops:
            E.append(f"mesh {name} : normales faceVarying absentes ou mal dimensionnées")
        st = UsdGeom.PrimvarsAPI(mp).GetPrimvar("st")
        if not st:
            W.append(f"mesh {name} : pas d'UV `st`")
        elif st.GetInterpolation() != "faceVarying" or len(st.Get()) != n_loops:
            E.append(f"mesh {name} : primvar st non faceVarying")
        # influences
        ji, jw = b.GetJointIndicesPrimvar(), b.GetJointWeightsPrimvar()
        if not ji or not jw:
            E.append(f"mesh {name} : jointIndices/jointWeights absents")
        else:
            k = ji.GetElementSize()
            mi["influences"] = k
            if ji.GetInterpolation() != "vertex" or jw.GetInterpolation() != "vertex":
                E.append(f"mesh {name} : influences non `vertex`")
            if k > 4 or jw.GetElementSize() != k:
                E.append(f"mesh {name} : elementSize {k} > 4 ou incohérent")
            I = np.array(ji.Get()).reshape(-1, k)
            Wt = np.array(jw.Get(), dtype=np.float64).reshape(-1, k)
            if len(I) != len(pts):
                E.append(f"mesh {name} : nombre d'influences ≠ nombre de points")
            else:
                sums = Wt.sum(1)
                if np.abs(sums - 1.0).max() > 1e-5:
                    E.append(f"mesh {name} : poids non normalisés (écart max {np.abs(sums - 1).max():.2e})")
                if np.any(np.diff(Wt, axis=1) > 1e-7):
                    E.append(f"mesh {name} : poids non triés par ordre décroissant")
                if I.min() < 0 or I.max() >= n_joints:
                    E.append(f"mesh {name} : indice de joint hors limites")
                if np.any(Wt < 0):
                    E.append(f"mesh {name} : poids négatifs")
        gb = b.GetGeomBindTransformAttr().Get()
        if gb is None or np.abs(np.array(gb) - np.eye(4)).max() > 1e-9:
            E.append(f"mesh {name} : geomBindTransform ≠ identité")
        # blend shapes
        names = list(b.GetBlendShapesAttr().Get() or [])
        targets = b.GetBlendShapeTargetsRel().GetTargets()
        mi["blendShapes"] = names
        if len(names) != len(targets):
            E.append(f"mesh {name} : skel:blendShapes et blendShapeTargets de tailles différentes")
        if allowed_bs is not None:
            bad = [x for x in names if x not in allowed_bs]
            if bad:
                E.append(f"mesh {name} : blend shapes hors liste autorisée {bad}")
        for t in targets:
            bs = UsdSkel.BlendShape(stage.GetPrimAtPath(t))
            if not bs:
                E.append(f"mesh {name} : cible de blend shape invalide {t}")
                continue
            off = bs.GetOffsetsAttr().Get()
            noff = bs.GetNormalOffsetsAttr().Get()
            pi = bs.GetPointIndicesAttr().Get()
            if off is None or noff is None or pi is None:
                E.append(f"{t} : offsets/normalOffsets/pointIndices non authored")
                continue
            if not (len(off) == len(noff) == len(pi)):
                E.append(f"{t} : tailles offsets/normalOffsets/pointIndices différentes")
            pi = np.array(pi)
            if len(pi) and (pi.min() < 0 or pi.max() >= len(pts) or len(np.unique(pi)) != len(pi)):
                E.append(f"{t} : pointIndices invalides")
            if bs.GetInbetweens():
                E.append(f"{t} : in-betweens présents (non supportés de façon documentée)")
            if not np.all(np.isfinite(np.array(off))):
                E.append(f"{t} : offsets non finis")
        # matériaux
        subsets = UsdShade.MaterialBindingAPI(mp).GetMaterialBindSubsets()
        bound = []
        if subsets:
            ok_fam, why_fam = UsdGeom.Subset.ValidateFamily(mesh, UsdGeom.Tokens.face, "materialBind")
            if not ok_fam:
                E.append(f"mesh {name} : famille de GeomSubsets invalide : {why_fam}")
            covered = np.zeros(len(counts), bool)
            for ss in subsets:
                covered[np.array(ss.GetIndicesAttr().Get())] = True
                m, _ = UsdShade.MaterialBindingAPI(ss.GetPrim()).ComputeBoundMaterial()
                if not m:
                    E.append(f"mesh {name} : subset {ss.GetPrim().GetName()} sans matériau")
                else:
                    bound.append(m.GetPrim().GetName())
            if not covered.all():
                E.append(f"mesh {name} : {int((~covered).sum())} faces sans GeomSubset de matériau")
        else:
            m, _ = UsdShade.MaterialBindingAPI(mp).ComputeBoundMaterial()
            if not m:
                E.append(f"mesh {name} : aucun matériau lié")
            else:
                bound.append(m.GetPrim().GetName())
        mi["materials"] = sorted(set(bound))
        if mesh_mats is not None and name in mesh_mats and sorted(set(bound)) != sorted(mesh_mats[name]):
            E.append(f"mesh {name} : matériaux {sorted(set(bound))} ≠ attendus {mesh_mats[name]} (SPEC §4)")
        if mats_allowed is not None:
            bad = [x for x in bound if x not in mats_allowed and not x.startswith(prefixes or ("\0",))]
            if bad:
                E.append(f"mesh {name} : matériaux non conformes {bad}")
        info["meshes"][name] = mi
    for rm in expect.get("requiredMeshes", []):
        if rm not in info["meshes"]:
            E.append(f"mesh requis absent : {rm}")

    # --- shaders
    resolver = Ar.GetResolver()
    tex_info = {}
    for p in prims:
        if not p.IsA(UsdShade.Material):
            continue
        scalar_tex = set()
        for sp in Usd.PrimRange(p):
            if not sp.IsA(UsdShade.Shader):
                continue
            sh = UsdShade.Shader(sp)
            sid = sh.GetIdAttr().Get()
            if sid not in ("UsdPreviewSurface", "UsdUVTexture", "UsdPrimvarReader_float2"):
                E.append(f"{sp.GetPath()} : shader {sid} inattendu")
            if sid == "UsdPreviewSurface":
                n = sh.GetInput("normal")
                if n and n.GetTypeName() != Sdf.ValueTypeNames.Normal3f:
                    E.append(f"{sp.GetPath()} : inputs:normal n'est pas normal3f")
                uw = sh.GetInput("useSpecularWorkflow")
                if uw and uw.Get() not in (0, None):
                    E.append(f"{sp.GetPath()} : workflow spéculaire (non supporté par RealityKit)")
                feeds = {}
                for inp in sh.GetInputs():
                    for src in inp.GetConnectedSources()[0]:
                        tsh = UsdShade.Shader(src.source.GetPrim())
                        if tsh.GetIdAttr().Get() == "UsdUVTexture":
                            feeds.setdefault(str(tsh.GetPath()), (tsh, []))[1].append((inp.GetBaseName(), src.sourceName))
                for tpath, (tsh, uses) in feeds.items():
                    cs = tsh.GetInput("sourceColorSpace").Get()
                    color = [u for u in uses if u[0] in ("diffuseColor", "emissiveColor")]
                    if color:
                        # texture de couleur : sRGB ; son canal alpha (linéaire) peut piloter l'opacité
                        if cs != "sRGB":
                            E.append(f"{tpath} : texture de couleur non sRGB")
                        extra = [u for u in uses if u not in color and u != ("opacity", "a")]
                        if extra:
                            E.append(f"{tpath} : texture de couleur réutilisée pour {extra}")
                    elif cs != "raw":
                        E.append(f"{tpath} : texture de données ({[u[0] for u in uses]}) non raw")
                    for base, out_name in uses:
                        if base == "normal":
                            sc = tsh.GetInput("scale").Get() if tsh.GetInput("scale") else None
                            bi = tsh.GetInput("bias").Get() if tsh.GetInput("bias") else None
                            if sc is None or bi is None or tuple(sc) != (2, 2, 2, 1) or tuple(bi) != (-1, -1, -1, 0):
                                E.append(f"{tsh.GetPath()} : normal map sans scale (2,2,2,1)/bias (-1,-1,-1,0)")
                        if out_name in ("r", "g", "b", "a"):
                            scalar_tex.add(str(tsh.GetPath()))
            if sid == "UsdUVTexture":
                f = sh.GetInput("file").Get()
                fp = f.path if f is not None else ""
                if not fp.lower().endswith(".png"):
                    E.append(f"{sp.GetPath()} : texture non PNG {fp}")
                for wname in ("wrapS", "wrapT"):
                    wi = sh.GetInput(wname)
                    if not wi or wi.Get() != "repeat":
                        E.append(f"{sp.GetPath()} : {wname} ≠ repeat")
                rp = f.resolvedPath if f is not None else ""
                if not rp:
                    E.append(f"{sp.GetPath()} : texture non résolue {fp}")
                else:
                    try:
                        import io
                        from PIL import Image
                        asset = resolver.OpenAsset(Ar.ResolvedPath(rp))
                        buf = bytes(memoryview(asset.GetBuffer()))
                        im = Image.open(io.BytesIO(buf))
                        tex_info[os.path.basename(fp)] = {"size": list(im.size), "mode": im.mode, "bytes": len(buf)}
                        w_, h_ = im.size
                        if (w_ & (w_ - 1)) or (h_ & (h_ - 1)):
                            W.append(f"{fp} : dimensions non puissances de 2 {im.size}")
                        if max(im.size) > 4096:
                            W.append(f"{fp} : texture > 4096 px")
                    except Exception as e:  # noqa: BLE001
                        E.append(f"{sp.GetPath()} : texture illisible {fp} ({e})")
        if len(scalar_tex) > 1:
            E.append(f"{p.GetPath()} : {len(scalar_tex)} textures empaquetées (RealityKit : une seule par matériau)")
    info["textures"] = tex_info
    return {"errors": E, "warnings": W, "info": info}


def _child_animation(stage, npz_path) -> dict:
    """La SkelAnimation authored doit redonner les locales attendues (F,N,4,4) à chaque frame."""
    from pxr import Usd, UsdSkel
    z = np.load(npz_path)
    ref = z["locals"]
    skel_prim = next(p for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton))
    root_prim = next(p for p in stage.Traverse() if p.IsA(UsdSkel.Root))
    cache = UsdSkel.Cache()
    cache.Populate(UsdSkel.Root(root_prim), Usd.PrimDefaultPredicate)
    aq = cache.GetSkelQuery(UsdSkel.Skeleton(skel_prim)).GetAnimQuery()
    if not aq:
        return {"pass": False, "errors": ["pas d'animation liée"]}
    err = 0.0
    for f in range(len(ref)):
        loc = np.array([_gf_to_np(m) for m in aq.ComputeJointLocalTransforms(Usd.TimeCode(f))])
        err = max(err, float(np.abs(loc - ref[f]).max()))
    # boucle : la clé finale doit reprendre la première
    last = int(stage.GetEndTimeCode())
    loop_err = None
    if last == len(ref):
        loc = np.array([_gf_to_np(m) for m in aq.ComputeJointLocalTransforms(Usd.TimeCode(last))])
        loop_err = float(np.abs(loc - ref[0]).max())
    tol = 1e-4   # quatf/float3 + échelles half3 (1 exactement représentable)
    ok = err <= tol and (loop_err is None or loop_err <= tol)
    return {"pass": ok, "frames": int(len(ref)), "maxLocalError": err, "loopError": loop_err, "errors": []}


def _child_skinning(stage, npz_path) -> dict:
    """Compare l'évaluation UsdSkel (LBS + blend shapes) aux positions Blender pour K poses."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdSkel, Vt
    z = np.load(npz_path)
    T, R, S = z["t"], z["r"], z["s"]
    K = len(T)
    bs_names = [str(x) for x in z["bs_names"]]
    bs_w = z["bs_weights"]
    expected = {k[len("points__"):]: z[k] for k in z.files if k.startswith("points__")}
    res = {"poses": K, "meshes": {}, "errors": []}
    if K < MIN_POSES:
        res["errors"].append(f"{K} poses < {MIN_POSES}")
    skel_prim = next(p for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton))
    root_prim = next(p for p in stage.Traverse() if p.IsA(UsdSkel.Root))
    joints = list(UsdSkel.Skeleton(skel_prim).GetJointsAttr().Get())
    if T.shape[1] != len(joints):
        res["errors"].append(f"poses à {T.shape[1]} joints, squelette à {len(joints)}")
        res["pass"] = False
        return res
    # Couche de session : même timeCodesPerSecond que la racine (sinon USD rééchelonne les échantillons).
    sess = stage.GetSessionLayer()
    sess.timeCodesPerSecond = stage.GetRootLayer().timeCodesPerSecond
    sess.framesPerSecond = stage.GetRootLayer().framesPerSecond
    stage.SetEditTarget(sess)
    anim = UsdSkel.Animation.Define(stage, skel_prim.GetPath().AppendChild("ValidationPoses"))
    anim.CreateJointsAttr(Vt.TokenArray(joints))
    if bs_names:
        anim.CreateBlendShapesAttr(Vt.TokenArray(bs_names))
    for k in range(K):
        anim.CreateTranslationsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*map(float, v)) for v in T[k]]), k)
        anim.CreateRotationsAttr().Set(Vt.QuatfArray([Gf.Quatf(float(q[3]), float(q[0]), float(q[1]), float(q[2]))
                                                      for q in R[k]]), k)
        anim.CreateScalesAttr().Set(Vt.Vec3hArray([Gf.Vec3h(*map(float, v)) for v in S[k]]), k)
        if bs_names:
            anim.CreateBlendShapeWeightsAttr().Set(Vt.FloatArray([float(x) for x in bs_w[k]]), k)
    UsdSkel.BindingAPI.Apply(skel_prim).CreateAnimationSourceRel().SetTargets([anim.GetPath()])

    # Méthode A : SkinningQuery + BlendShapeQuery
    cache = UsdSkel.Cache()
    root = UsdSkel.Root(root_prim)
    cache.Populate(root, Usd.PrimDefaultPredicate)
    bindings = cache.ComputeSkelBindings(root, Usd.PrimDefaultPredicate)
    max_a = 0.0
    seen = set()
    for binding in bindings:
        sq_skel = cache.GetSkelQuery(binding.GetSkeleton())
        anim_q = sq_skel.GetAnimQuery()
        for sq in binding.GetSkinningTargets():
            prim = sq.GetPrim()
            name = prim.GetName()
            if name not in expected:
                res["errors"].append(f"pas de positions Blender pour le mesh {name}")
                continue
            seen.add(name)
            errs = []
            for k in range(K):
                tc = Usd.TimeCode(k)
                pts = Vt.Vec3fArray(UsdGeom.Mesh(prim).GetPointsAttr().Get(tc))
                if sq.HasBlendShapes():
                    w = anim_q.ComputeBlendShapeWeights(tc)
                    mapper = sq.GetBlendShapeMapper()
                    mapped = mapper.Remap(w) if not mapper.IsNull() else w
                    bq = UsdSkel.BlendShapeQuery(UsdSkel.BindingAPI(prim))
                    sub_w, bs_idx, sub_idx = bq.ComputeSubShapeWeights(mapped)
                    bq.ComputeDeformedPoints(sub_w, bs_idx, sub_idx, bq.ComputeBlendShapePointIndices(),
                                             bq.ComputeSubShapePointOffsets(), pts)
                xf = sq_skel.ComputeSkinningTransforms(tc)
                if not sq.ComputeSkinnedPoints(xf, pts, tc):
                    res["errors"].append(f"{name} : ComputeSkinnedPoints a échoué (pose {k})")
                    errs.append(float("inf"))
                    continue
                skel_xf = UsdGeom.Xformable(binding.GetSkeleton().GetPrim()).ComputeLocalToWorldTransform(tc)
                p = np.array(pts, dtype=np.float64)
                p = p @ np.array(skel_xf)[:3, :3] + np.array(skel_xf)[3, :3]
                ref = expected[name][k]
                if ref.shape != p.shape:
                    res["errors"].append(f"{name} : {len(p)} points USD ≠ {len(ref)} Blender")
                    errs.append(float("inf"))
                    continue
                errs.append(float(np.abs(p - ref).max()))
            res["meshes"][name] = {"query": errs}
            max_a = max([max_a] + errs)
    for name in expected:
        if name not in seen:
            res["errors"].append(f"mesh {name} attendu mais non skinné dans le USD")

    # Méthode B : UsdSkel.BakeSkinning (écrit dans la couche de session ; le fichier n'est pas modifié)
    max_b = float("nan")
    try:
        ok = UsdSkel.BakeSkinning(Usd.PrimRange(root_prim), Gf.Interval(0, K - 1))
        if ok:
            max_b = 0.0
            for name in seen:
                prim = next(p for p in Usd.PrimRange(root_prim) if p.GetName() == name and p.IsA(UsdGeom.Mesh))
                errs = []
                for k in range(K):
                    pts = np.array(UsdGeom.Mesh(prim).GetPointsAttr().Get(Usd.TimeCode(k)), dtype=np.float64)
                    xf = np.array(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode(k)))
                    pw = pts @ xf[:3, :3] + xf[3, :3]
                    errs.append(float(np.abs(pw - expected[name][k]).max()))
                res["meshes"][name]["bake"] = errs
                max_b = max([max_b] + errs)
        else:
            res["errors"].append("BakeSkinning a renvoyé False")
    except Exception as e:  # noqa: BLE001
        res["errors"].append(f"BakeSkinning : {e}")
    res["maxErrorQuery"] = max_a
    res["maxErrorBake"] = max_b
    res["pass"] = (not res["errors"]) and max_a <= SKIN_TOL and (np.isnan(max_b) or max_b <= SKIN_TOL) \
        and K >= MIN_POSES and bool(seen)
    return res


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        _child_main(sys.argv[2])
    else:
        print("usage interne : validate.py --child <args.json>  (appelé par validate_usd)")
        sys.exit(2)
