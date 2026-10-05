"""Étape 3 — crins (agent « hair ») : textures, 8 pièces de crins, ancres des nattes, vérifications, aperçus.

Lancement (Python 3.11 avec bpy 4.2) :
    python3 Pipeline/stages/s03_hair.py                 # tout (≈ 10 min CPU avec les aperçus Cycles)
    python3 Pipeline/stages/s03_hair.py --no-previews   # génération + vérification seulement (≈ 1 min)
    python3 Pipeline/stages/s03_hair.py --provisional   # ignore body.blend (corps provisoire)
    python3 Pipeline/stages/s03_hair.py --parts mane_natural tail_natural

Entrées : armature du gabarit (`rig.build_armature()`), `Pipeline/build/body.blend` (objet `Body`) s'il existe,
sinon corps provisoire (SDF de l'agent body si importable, sinon SDF grossière ; mis en cache dans
`Pipeline/build/hair_cache/`).
Sorties : `Pipeline/build/parts/<id>.blend` (8 pièces), `Pipeline/build/parts/mane_braided_anchors.json`,
`Pipeline/build/textures/hair_strands.png`, `hair_normal.png`, `braid_detail.png`, `hair_albedo_default.png`,
`Previews/hair/hair_styles.png` (planche), `Previews/hair/<id>.jpg`, `Previews/hair/hair_poses.jpg`,
`Previews/hair/hair_report.json` (statistiques, vérifications, mesures de déformation).
Code de sortie : 0 = toutes les vérifications passent ; 1 = au moins une vérification en échec.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent.parent
if str(PIPELINE) not in sys.path:
    sys.path.insert(0, str(PIPELINE))

from pony import hair  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--parts", nargs="*", default=None)
    ap.add_argument("--provisional", action="store_true")
    ap.add_argument("--textures", action="store_true", help="force la régénération des textures")
    ap.add_argument("--no-previews", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    prefer_real = not a.provisional
    report = {"build": hair.build_parts(a.parts, prefer_real=prefer_real, textures_force=a.textures)}
    report["verify"] = hair.verify_all(a.parts)
    if not a.no_previews:
        from pony import hair_preview as hp

        out = hp.PREVIEW_DIR
        out.mkdir(parents=True, exist_ok=True)
        hp.render_part_previews(a.parts or hair.PART_IDS, colors=("brown", "flaxen"), out_dir=out,
                                prefer_real=prefer_real, samples=16, resolution=(360, 360), ext="jpg")
        report["poses"] = hp.pose_tests(out / "hair_poses.jpg", prefer_real=prefer_real)
        hp.styles_board(out / "hair_styles.png", prefer_real=prefer_real)
        (out / "hair_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=float))
    ok = all(v.get("ok", False) for v in report["verify"].values())
    print(f"[hair] terminé en {time.time() - t0:.0f}s — vérifications : {'OK' if ok else 'ÉCHEC'} "
          f"(corps : {report['build']['body_source']})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
