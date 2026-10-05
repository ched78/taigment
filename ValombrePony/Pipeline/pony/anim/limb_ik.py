"""IK numérique des membres (aucune contrainte Blender : tout est résolu et cuit en numpy/scipy).

Modèle (Docs/research/anatomy.md §1.6-1.7, gaits.md §2, §5.1) :

Antérieur  : spine_03 → omoplate → humérus → avant-bras → canon → paturon → sabot
  - omoplate : rotation autour de son sommet (tête de l'os) liée à la protraction du membre
    (scapula = k_scap · protraction de la cible) [I/A, k_scap ≈ 0,35] ;
  - épaule (humérus) : flexion X + abduction Z (+ torsion Y optionnelle pour les virages) — inconnues ;
  - coude (avant-bras) : flexion X — inconnue ;
  - carpe (canon) : IMPOSÉ par un profil (verrouillé à l'appui, fléchi en envol) [R qualitatif] ;
  - boulet (paturon) : inconnue, préférence = profil de charge (hyperextension ∝ charge) ;
  - doigt (sabot / interphalangiennes) : inconnue, préférence couplée au boulet (« enroulement »).
Postérieur : hips → fémur → tibia → métatarse → paturon → sabot
  - hanche : flexion X + abduction Z (+ torsion) — inconnues ; grasset : flexion X — inconnue ;
  - jarret = −k_recip · grasset + δ (appareil réciproque, Δjarret ≈ Δgrasset, k ≈ 1) [R] ; δ (« jeu »)
    est une petite variable fortement pénalisée, bornée à ±8°, pour ne pas rendre l'IK infaisable aux
    extrêmes ; sa valeur max est rapportée par `checks.py` ;
  - boulet / doigt : comme l'antérieur.

Cible : pose du sabot donnée par deux points de la sole (pince = contrainte « dure », talon = poids
w_rot ; à l'appui w_rot est grand ⇒ sabot entièrement planté, en envol il diminue ⇒ l'orientation du sabot
résulte des préférences du doigt). La redondance (1 ddl dans le plan) est levée par les préférences.
Résolution : `scipy.optimize.least_squares` (TRF, bornes = limites articulaires élargies), démarrage à chaud
sur la solution de l'image précédente.

Signes (rotation autour de +X local, sens trigonométrique vu de la droite) :
  épaule +  = extension (coude vers l'avant)         coude +   = flexion
  carpe −   = flexion                                boulet +  = hyperextension (descente), − = flexion
  doigt −   = flexion                                hanche +  = flexion (grasset vers l'avant)
  grasset − = flexion                                jarret +  = flexion
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import least_squares

from . import mathutil as mu
from .skeleton import LIMB_JOINTS, Skeleton

D = mu.DEG

# Bornes de résolution (radians, delta par rapport à la pose de liaison) — volontairement un peu plus
# larges que les limites du SPEC §3 : `checks.py` signale tout dépassement des limites du SPEC.
FORE_BOUNDS = {
    "scap": (-15 * D, 15 * D),        # omoplate ±15° (anatomy.md §1.6 « Recommended rig limits ») [I]
    "sh_flex": (-40 * D, 20 * D),     # épaule : − flexion ≤ 40°, + extension ≤ 20° (SPEC §3)
    "sh_abd": (-12 * D, 12 * D),
    "sh_twist": (-15 * D, 15 * D),
    "elbow": (-10 * D, 65 * D),       # coude : + flexion ≤ 65°, − extension ≤ 10° (SPEC §3)
    "fetlock": (-105 * D, 26 * D),    # flexion ≤ 105° ; hyperextension bornée à 60° après rectitude (cf. solve)
    "coffin": (-50 * D, 15 * D),      # paturon + sabot ≈ 50° de flexion, ~15° d'extension (SPEC §3)
    "pastern_twist": (-10 * D, 10 * D),
}
HIND_BOUNDS = {
    "hip_flex": (-25 * D, 40 * D),    # hanche : + flexion ≤ 40°, − extension ≤ 25° (SPEC §3)
    "hip_abd": (-10 * D, 10 * D),     # ±10° (anatomy.md) [I]
    "hip_twist": (-15 * D, 15 * D),
    "stifle": (-75 * D, 32 * D),      # grasset : − flexion ; + extension (pas de limite SPEC) [I]
    "hock_slack": (-8 * D, 8 * D),    # écart toléré au couplage jarret = −k·grasset (pénalisé)
    "fetlock": (-105 * D, 32 * D),
    "coffin": (-50 * D, 15 * D),
    "pastern_twist": (-10 * D, 10 * D),
}
FETLOCK_HYPER_MAX = 60 * D   # hyperextension max du boulet au-delà de la rectitude (SPEC §3)


W_TOE = 3000.0          # poids de la pince (1 rad de préférence ≈ 0,3 mm) : contrainte quasi dure
HOCK_EXT_MAX = 20 * D   # extension max du jarret au-delà de la pose de liaison [I]


@dataclass
class LimbFrameInput:
    """Données d'une image pour un membre (repère monde Blender du clip)."""
    toe: np.ndarray                 # (3,) cible de la pince
    heel: np.ndarray                # (3,) cible du talon (milieu)
    w_rot: float = 1.0              # poids de l'orientation (talon)
    carpus: float = 0.0             # flexion imposée du carpe (rad, delta repos, − = flexion) [antérieur]
    fetlock_pref: float = 0.0       # préférence boulet (delta repos)
    coffin_pref: float = 0.0        # préférence doigt (delta repos)
    w_fetlock: float = 1.0
    w_coffin: float = 0.2
    scap_extra: float = 0.0         # rotation additionnelle d'omoplate (rad)
    abd_pref: float = 0.0
    twist_pref: float = 0.0
    ground_clear: float = -1.0      # si > -1 : hauteur mini des points de sole (pénalité unilatérale)
    w_ground: float = 0.0
    prox_pref: float | None = None  # préférence faible sur épaule/hanche (flex)
    mid_pref: float | None = None   # préférence faible sur coude/grasset


@dataclass
class LimbSolver:
    sk: Skeleton
    limb: str
    k_scap: float = 0.35            # [I/A] couplage omoplate / protraction
    k_recip: float = 1.0            # [R] Δjarret ≈ Δgrasset
    use_twist: bool = True          # rotation axiale épaule/hanche + paturon (pénalisées) : sans elles, le
                                    # lacet du sabot planté n'est pas contrôlable (os légèrement obliques)
    joints: list = field(init=False)

    def __post_init__(self):
        self.front = self.limb.startswith("f")
        self.joints = [self.sk.idx(n) for n in LIMB_JOINTS[self.limb]]
        self.parent = int(self.sk.parents[self.joints[0]])
        self.sole = self.sk.sole_local(self.limb)
        if self.front:
            self.var_names = ["sh_flex", "sh_abd", "elbow", "fetlock", "coffin", "scap"]
            bounds = FORE_BOUNDS
        else:
            self.var_names = ["hip_flex", "hip_abd", "stifle", "fetlock", "coffin", "hock_slack"]
            bounds = HIND_BOUNDS
        if self.use_twist:
            self.var_names += ["sh_twist" if self.front else "hip_twist", "pastern_twist"]
        self.lb = np.array([bounds[n][0] for n in self.var_names])
        self.ub = np.array([bounds[n][1] for n in self.var_names])
        # borne d'hyperextension du boulet : 60° après rectitude, convertie en delta / repos
        from .checks import rest_anatomy
        side = self.limb[1]
        hyper0 = rest_anatomy(self.sk)[f"{'front' if self.front else 'hind'}_fetlock_hyper_{side}"]
        k = self.var_names.index("fetlock")
        self.ub[k] = min(self.ub[k], FETLOCK_HYPER_MAX - hyper0 - 0.2 * D)
        # repère de repos du sommet de l'omoplate / de la hanche (pour la protraction)
        top = self.joints[0]
        self.top_rest = self.sk.head[top]
        self.rest_toe = self.sk.rest_sole_world(self.limb)[0]

    # --- angles complets de la chaîne -----------------------------------------------------------
    def chain_angles(self, x, inp: LimbFrameInput, scap_flex: float):
        """Vecteur de variables -> angles (n_joints, 3) [flex, twist, lat]."""
        n = len(self.joints)
        ang = np.zeros((n, 3))
        v = dict(zip(self.var_names, x))
        if self.front:
            ang[0, 0] = v["scap"]
            ang[1, 0] = v["sh_flex"]
            ang[1, 2] = v["sh_abd"]
            ang[1, 1] = v.get("sh_twist", 0.0)
            ang[2, 0] = v["elbow"]
            ang[3, 0] = inp.carpus
            ang[4, 0] = v["fetlock"]
            ang[4, 1] = v.get("pastern_twist", 0.0)
            ang[5, 0] = v["coffin"]
        else:
            ang[0, 0] = v["hip_flex"]
            ang[0, 2] = v["hip_abd"]
            ang[0, 1] = v.get("hip_twist", 0.0)
            ang[1, 0] = v["stifle"]
            ang[2, 0] = -self.k_recip * v["stifle"] + v["hock_slack"]
            ang[3, 0] = v["fetlock"]
            ang[3, 1] = v.get("pastern_twist", 0.0)
            ang[4, 0] = v["coffin"]
        return ang

    def scap_flex_for(self, parent_world, toe_target, extra=0.0):
        """Rotation d'omoplate = k_scap × protraction de la cible (angle sagittal pince/sommet)."""
        if not self.front:
            return 0.0
        inv = np.linalg.inv(parent_world)
        # positions exprimées dans le repère du parent (thorax) pour être insensibles au tangage du tronc
        top_p = (np.linalg.inv(self.sk.rest_world[self.parent]) @ np.append(self.top_rest, 1))[:3]
        toe_p = (inv @ np.append(toe_target, 1))[:3]
        rest_toe_p = (np.linalg.inv(self.sk.rest_world[self.parent]) @ np.append(self.rest_toe, 1))[:3]
        # angles dans le plan (y,z) local du parent
        a = np.arctan2(toe_p[1] - top_p[1], -(toe_p[2] - top_p[2]))
        a0 = np.arctan2(rest_toe_p[1] - top_p[1], -(rest_toe_p[2] - top_p[2]))
        # le repère local du parent (spine_03) a son Y le long de l'os (incliné) : on mesure l'angle
        # dans ce repère, la différence a-a0 est une protraction relative au repos.
        return self.k_scap * (a - a0) + extra

    def world_chain(self, parent_world, x, inp, scap_flex):
        ang = self.chain_angles(x, inp, scap_flex)
        return self.sk.chain_world(parent_world, self.joints, ang), ang

    def sole_points(self, Ms):
        H = Ms[-1]
        return (H[:3, :3] @ self.sole.T).T + H[:3, 3]

    # --- résolution -----------------------------------------------------------------------------
    def residuals(self, x, parent_world, inp: LimbFrameInput, scap_flex: float):
        Ms, _ = self.world_chain(parent_world, x, inp, scap_flex)
        sole = self.sole_points(Ms)
        r = [W_TOE * (sole[0] - inp.toe), W_TOE * inp.w_rot * (sole[5] - inp.heel)]
        v = dict(zip(self.var_names, x))
        r.append(np.array([inp.w_fetlock * (v["fetlock"] - inp.fetlock_pref),
                           inp.w_coffin * (v["coffin"] - inp.coffin_pref)]))
        if self.front:
            # omoplate : préférence = couplage à la protraction (k_scap), poids fort mais pas dur
            r.append(np.array([2.0 * (v["scap"] - scap_flex)]))
        if not self.front:
            # couplage réciproque « souple » : écart pénalisé ; extension du jarret limitée à ~20° au-delà
            # du repos (≈ 169° d'angle articulaire) [I]
            hock = -self.k_recip * v["stifle"] + v["hock_slack"]
            r.append(np.array([3.0 * v["hock_slack"], 20.0 * min(0.0, hock + HOCK_EXT_MAX)]))
        abd = v["sh_abd"] if self.front else v["hip_abd"]
        r.append(np.array([0.3 * (abd - inp.abd_pref)]))
        if self.use_twist:
            tw = v["sh_twist"] if self.front else v["hip_twist"]
            r.append(np.array([0.3 * (tw - inp.twist_pref), 0.5 * v["pastern_twist"]]))
        if inp.prox_pref is not None:
            px = v["sh_flex"] if self.front else v["hip_flex"]
            r.append(np.array([0.15 * (px - inp.prox_pref)]))
        if inp.mid_pref is not None:
            md = v["elbow"] if self.front else v["stifle"]
            r.append(np.array([0.15 * (md - inp.mid_pref)]))
        if inp.w_ground > 0:
            # pénalité unilatérale : points de sole + articulation du boulet au-dessus du sol
            zmin = np.concatenate([sole[:, 2], [Ms[-2][2, 3] - 0.02]])
            pen = np.minimum(0.0, zmin - inp.ground_clear)
            r.append(inp.w_ground * pen)
        return np.concatenate([np.atleast_1d(a) for a in r])

    def solve(self, parent_world, inp: LimbFrameInput, x0=None):
        scap = self.scap_flex_for(parent_world, inp.toe, inp.scap_extra)
        if x0 is None:
            x0 = np.zeros(len(self.var_names))
        x0 = np.clip(x0, self.lb + 1e-9, self.ub - 1e-9)
        res = least_squares(self.residuals, x0, bounds=(self.lb, self.ub), args=(parent_world, inp, scap),
                            method="trf", xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=400)
        Ms, ang = self.world_chain(parent_world, res.x, inp, scap)
        sole = self.sole_points(Ms)
        err_toe = float(np.linalg.norm(sole[0] - inp.toe))
        err_heel = float(np.linalg.norm(sole[5] - inp.heel))
        return res.x, ang, {"err_toe": err_toe, "err_heel": err_heel, "sole": sole, "Ms": Ms, "scap": scap}


def write_chain(ang_full, frame, sk: Skeleton, limb: str, chain_ang):
    """Écrit les angles (n,3) d'une chaîne dans le tableau d'angles complet (F,N,3)."""
    for k, n in enumerate(LIMB_JOINTS[limb]):
        ang_full[frame, sk.idx(n)] = chain_ang[k]
