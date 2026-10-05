"""Étape 4 — clips d'animation (agent « clips ») : génération, vérifications chiffrées, aperçus.

Lancement (Python 3.11 avec bpy 4.2) :
    python3 Pipeline/stages/s04_anim.py                       # tous les clips du SPEC §7 + vérifs + aperçus
    python3 Pipeline/stages/s04_anim.py --no-previews         # génération + vérifications (≈ 2-3 min, 2 processus)
    python3 Pipeline/stages/s04_anim.py --clips walk trot     # sous-ensemble (checks.json est fusionné)
    python3 Pipeline/stages/s04_anim.py --previews-only       # aperçus des .npz déjà écrits
    python3 Pipeline/stages/s04_anim.py --jobs 1              # un seul processus (CPU partagés)

Entrées : armature du gabarit, reconstruite à chaque lancement par `rig.build_armature()` (aucune position d'os
n'est codée en dur : si le gabarit bouge, relancer l'étape suffit) ; `Pipeline/build/rigged_body.blend` s'il
existe (aperçus avec le vrai corps).
Sorties :
- `Pipeline/build/clips/<nom>.npz` (format d'échange, cf. `pony/anim/clip_io.py`) : `local` float64 (F,70,4,4)
  locales Blender dans l'ordre `rig.joint_names()`, `weights_names`/`weights`, `meta` JSON ;
- `Previews/anim/checks.json` : vérifications chiffrées par clip + continuité des enchaînements ;
- `Previews/anim/<clip>.png` (planches de 8-12 images), GIF (walk, trot, canter_left, gallop, rear, roll,
  `jump.gif` enchaîné), `<clip>_body.png` si le corps skinné existe.
Code de sortie : 0 = aucune alerte bloquante ; 1 = au moins un clip en échec (cf. `checks.json`).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

import numpy as np  # noqa: E402

from pony import conventions as cv  # noqa: E402
from pony.anim import catalog, checks, clip_io  # noqa: E402
from pony.anim.skeleton import Skeleton, estimate_wh  # noqa: E402

CLIP_DIR = clip_io.CLIP_DIR
PREVIEW_DIR = cv.PREVIEW_DIR / "anim"
CHECKS_JSON = PREVIEW_DIR / "checks.json"

# Seuils d'acceptation [I] (alertes « bloquantes » : code de sortie 1)
SLIP_MAX_MM = 2.0            # patinage d'un point de sole au sol, mm/image (30 i/s)
HOOF_PEN_MM = -5.0           # pénétration des soles
BODY_PEN_MM = -5.0           # pénétration du mannequin (corps et segments distaux)

# Enchaînements attendus par le runtime (fin du premier clip → début du second) [I]
CHAINS = [
    ("idle", "graze_down"), ("graze_down", "graze_loop"), ("graze_loop", "graze_up"), ("graze_up", "idle"),
    ("idle", "lie_down"), ("lie_down", "lying"), ("lying", "get_up"), ("get_up", "idle"),
    ("lying", "roll"), ("roll", "lying"), ("idle", "rear"), ("rear", "idle"), ("idle", "body_shake"),
    ("body_shake", "idle"), ("idle", "paw"), ("paw", "idle"),
    ("jump_takeoff", "jump_air"), ("jump_air", "jump_land"), ("jump_land", "canter_left"),
    ("canter_left", "jump_takeoff"),
]

_SK = None


def _worker_init(names, parents, rest_world, lengths):
    global _SK
    _SK = Skeleton(names=list(names), parents=np.asarray(parents), rest_world=np.asarray(rest_world),
                   lengths=np.asarray(lengths))


def _gen_one(name):
    """Génère un clip, l'écrit, le relit et le vérifie (processus fils, numpy pur)."""
    t0 = time.time()
    clip = catalog.generate(_SK, name)
    path = clip.save(_SK, CLIP_DIR)
    local, wn, w, meta = clip_io.load_npz(path)
    res = checks.check_clip(_SK, local, meta, target=meta.get("specTargetDuration"))
    res["weights"] = {n: [round(float(w[:, i].min()), 3), round(float(w[:, i].max()), 3)] for i, n in enumerate(wn)}
    res["ik_err_max_mm"] = _ik_err(clip)
    res["gen_time_s"] = round(time.time() - t0, 1)
    res["npz"] = str(path.relative_to(cv.PROJECT_DIR)) if path.is_relative_to(cv.PROJECT_DIR) else str(path)
    res["npz_bytes"] = path.stat().st_size
    return name, res


def _ik_err(clip):
    d = clip.diag
    if "ik" in d:      # allure : erreurs de pince sur les appuis
        e = [float(d["ik"]["err_toe"][l][clip.contacts[l]].max()) for l in clip.contacts if clip.contacts[l].any()]
    elif "ik_err" in d:      # chorégraphie : seulement les images d'appui pur (hors fondus IK↔FK voulus)
        e = [float(v[clip.contacts[l]].max()) for l, v in d["ik_err"].items() if clip.contacts[l].any()]
    else:
        e = [0.0]
    return round(max(e) * 1000, 3)


def skeleton_from_rig():
    sk, _arm = Skeleton.from_blender()
    return sk


def chain_checks(sk: Skeleton, clip_dir: Path):
    """Écart de pose (repère du clip) entre la dernière image du premier clip et la première du second :
    rotation monde max des joints (°) et déplacement max (mm). Les fondus du runtime (0,1-0,3 s) absorbent
    de petits écarts ; un grand écart signale une pose de départ/fin incohérente."""
    out = {}
    cache = {}

    def load(n):
        if n not in cache:
            p = clip_dir / f"{n}.npz"
            cache[n] = clip_io.load_npz(p) if p.is_file() else None
        return cache[n]
    for a, b in CHAINS:
        A, B = load(a), load(b)
        if A is None or B is None:
            continue
        la, ma = A[0], A[3]
        lb = B[0]
        # fin de A : dernière image (non bouclé) ou image 0 (boucle : l'image F = image 0)
        fa = la[0] if ma["loop"] else la[-1]
        Wa = checks.world_from_local(sk, fa[None])[0]
        Wb = checks.world_from_local(sk, lb[0][None])[0]
        from pony.anim import mathutil as mu
        rot = float(mu.rot_angle_between(Wa[:, :3, :3], Wb[:, :3, :3]).max() / mu.DEG)
        pos = float(np.linalg.norm(Wa[:, :3, 3] - Wb[:, :3, 3], axis=1).max() * 1000)
        jr = int(np.argmax(mu.rot_angle_between(Wa[:, :3, :3], Wb[:, :3, :3])))
        jp = int(np.argmax(np.linalg.norm(Wa[:, :3, 3] - Wb[:, :3, 3], axis=1)))
        out[f"{a}->{b}"] = {"rot_deg_max": round(rot, 2), "rot_joint": sk.names[jr],
                            "pos_mm_max": round(pos, 1), "pos_joint": sk.names[jp]}
    return out


LEGEND = {
    "slip_mm_per_frame": "patinage : déplacement horizontal (monde, mouvement racine réappliqué) des points de sole au "
                         "sol (z < 3 mm aux deux images) entre deux images d'un même appui prévu (meta.contacts)",
    "stance_toe_z_max_mm": "hauteur max de la pince pendant les appuis prévus (sabot « planté » décollé)",
    "hoof_min_z_mm": "z minimal des points de sole (pince, talons, mamelles) sur tout le clip",
    "body_min_z_mm / distal_min_z_mm": "z minimal du mannequin d'ellipsoïdes [A] (corps / canons+paturons)",
    "limit_violations": "angles hors des limites du SPEC §3 (deltas / pose de liaison, cf. checks.LIMITS)",
    "carpus_flex_max_deg / fetlock_hyper_max_deg": "carpe (≤ 150°) et hyperextension des boulets (≤ 60°) mesurés "
                                                  "depuis la rectitude",
    "recip_dev_max_deg": "écart max au couplage grasset↔jarret |Δjarret − Δgrasset|",
    "loop_seam_step / loop_other_step_max": "continuité de position : saut de pose à la jointure (image F−1 → 0) vs "
                                            "plus grand pas entre images ailleurs (rotation monde max °, déplacement mm)",
    "loop_seam_acc_mm / loop_acc_max_other_mm": "continuité de vitesse : variation de vitesse (différence seconde des "
                                                "positions des joints, mm/image²) à la jointure vs ailleurs",
    "quat_norm_err / rot_orthonormal_err / rot_det_min": "rotations locales : écart à une norme 1 des quaternions, "
                                                         "orthonormalité, déterminant",
    "ik_err_max_mm": "erreur de la pince plantée vs sa cible (IK) sur les images d'appui pur",
    "chains": "écart de pose fin du clip A → début du clip B (rotation monde max, déplacement max) ; les fondus du "
              "runtime absorbent les petits écarts",
    "jump_sequence": "saut enchaîné simulé comme le runtime (fondus, arc balistique) devant un obstacle de 0,70 m : "
                     "marge minimale au-dessus de la barre (crins exclus) et pénétration des soles pendant les fondus",
}


def _jump_check(sk):
    try:
        from pony.anim import sequence
        return sequence.jump_clearance(sk, CLIP_DIR)
    except FileNotFoundError as e:
        return {"error": str(e)}


def blocking(res):
    """Alertes bloquantes d'un clip (sous-ensemble des `warnings`)."""
    bad = []
    if res["slip_max_mm"] > SLIP_MAX_MM:
        bad.append("patinage")
    if res["hoof_min_z_mm"] < HOOF_PEN_MM:
        bad.append("pénétration sabot")
    if min(res["body_min_z_mm"], res["distal_min_z_mm"]) < BODY_PEN_MM:
        bad.append("pénétration corps")
    if res["limit_violations"]:
        bad.append("limites articulaires")
    if res["quat_norm_err"] > 1e-6 or res["rot_orthonormal_err"] > 1e-9:
        bad.append("rotations")
    if not res["duration_ok"]:
        bad.append("durée")
    if any("jointure" in w for w in res["warnings"]):
        bad.append("boucle")
    return bad


def run_previews(names, gifs, body, jobs_note=""):
    cmd = [sys.executable, "-m", "pony.anim.preview", "--clips", ",".join(names), "--gif", ",".join(gifs),
           "--body", body]
    if "jump_takeoff" in names or "jump" in gifs:
        cmd += ["--jump-gif"]
    print("[anim] aperçus :", " ".join(cmd[2:]), jobs_note, flush=True)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PIPELINE) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(cmd, cwd=str(PIPELINE), env=env)
    return r.returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clips", nargs="*", default=None, help="noms de clips (défaut : tous ceux du SPEC §7)")
    ap.add_argument("--no-previews", action="store_true")
    ap.add_argument("--previews-only", action="store_true")
    ap.add_argument("--jobs", type=int, default=2, help="processus de génération (CPU partagés : 2 par défaut)")
    ap.add_argument("--body", default="auto", choices=["auto", "none"],
                    help="aperçus avec le corps skinné (rigged_body.blend) s'il existe")
    a = ap.parse_args(argv)
    names = a.clips or list(catalog.CLIPS)
    unknown = [n for n in names if n not in catalog.CLIPS]
    if unknown:
        ap.error(f"clips inconnus : {unknown}")
    t0 = time.time()
    CLIP_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    sk = skeleton_from_rig()
    report = {}
    if CHECKS_JSON.is_file():
        try:
            report = json.loads(CHECKS_JSON.read_text())
        except json.JSONDecodeError:
            report = {}
    report.setdefault("clips", {})
    status = 0
    if not a.previews_only:
        args = (sk.names, sk.parents, sk.rest_world, sk.lengths)
        # les clips les plus longs à générer d'abord (meilleur équilibrage)
        order = sorted(names, key=lambda n: -catalog.COST.get(n, 1.0))
        if a.jobs <= 1:
            _worker_init(*args)
            results = [_gen_one(n) for n in order]
        else:
            import multiprocessing as mp
            results = []
            with ProcessPoolExecutor(max_workers=a.jobs, mp_context=mp.get_context("spawn"),
                                     initializer=_worker_init, initargs=args) as ex:
                futs = {ex.submit(_gen_one, n): n for n in order}
                for f in as_completed(futs):
                    results.append(f.result())
                    n, r = results[-1]
                    print(f"[anim] {checks.format_result(r)}  ({r['gen_time_s']} s)", flush=True)
        for n, r in results:
            r["blocking"] = blocking(r)
            report["clips"][n] = r
        report["chains"] = chain_checks(sk, CLIP_DIR)
        report["jump_sequence"] = _jump_check(sk)
        report["legend"] = LEGEND
        report["thresholds"] = {"slip_mm_per_frame": SLIP_MAX_MM, "hoof_penetration_mm": HOOF_PEN_MM,
                                "body_penetration_mm": BODY_PEN_MM}
        report["skeleton"] = {"source": "rig.build_armature()", "joints": sk.N,
                              "wh_estimate_m": round(estimate_wh(sk), 4)}
        report["missing"] = [n for n in catalog.CLIPS if not (CLIP_DIR / f"{n}.npz").is_file()]
        report["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        report["clips"] = {k: report["clips"][k] for k in catalog.CLIPS if k in report["clips"]}
        CHECKS_JSON.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=float))
        bad = {n: r["blocking"] for n, r in report["clips"].items() if r.get("blocking")}
        print(f"[anim] {len(results)} clip(s) générés ; alertes bloquantes : {bad or 'aucune'}")
        print(f"[anim] enchaînements : " + ", ".join(f"{k} {v['rot_deg_max']}°/{v['pos_mm_max']}mm"
                                                    for k, v in report["chains"].items()))
        status = 1 if bad else 0
    if not a.no_previews:
        gifs = [g for g in catalog.GIF_CLIPS if g in names]
        rc = run_previews(names, gifs, a.body)
        if rc != 0:
            print(f"[anim] aperçus : code de sortie {rc}")
            status = status or 1
    print(f"[anim] terminé en {time.time() - t0:.0f} s")
    return status


if __name__ == "__main__":
    sys.exit(main())
