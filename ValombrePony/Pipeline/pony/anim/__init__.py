"""Génération procédurale des clips d'animation du poney (cf. Docs/SPEC.md §7).

Modules :
- `mathutil`   : rotations, interpolations, profils lissés (numpy pur) ;
- `skeleton`   : squelette de repos lu depuis l'armature Blender, FK vectorisée, points d'échantillonnage ;
- `limb_ik`    : IK numérique des membres (couplages grasset↔jarret, enroulement du doigt, omoplate) ;
- `gait`       : allures (horloge de phase, trajectoires de sabots, tronc, encolure, queue) ;
- `poses`      : système de poses-clés (FK interpolée + IK des membres plantés + contrainte de sol) ;
- `behaviours` : comportements (brouter, cabrer, se coucher, se rouler…) ;
- `jump`       : saut (appel, vol, réception) ;
- `clip_io`    : format d'échange `.npz` pour l'agent d'export ;
- `checks`     : vérifications (patinage, sol, amplitudes, boucles, quaternions) ;
- `preview`    : planches contact et GIF (Blender, Workbench).

Le code de génération est en numpy pur (aucune dépendance à bpy) : seul le squelette de repos est lu
à chaque lancement depuis `rig.build_armature()` (aucune position d'os codée en dur), puis transmis aux processus
de génération (`stages/s04_anim.py`).
"""
