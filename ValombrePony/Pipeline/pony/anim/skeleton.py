"""Squelette de repos (lu depuis l'armature Blender) et cinématique directe vectorisée (numpy).

Toutes les positions/longueurs d'os viennent de `rig.build_armature()` (jamais codées en dur) : le gabarit
peut être retouché par l'agent « body ». Les seules constantes géométriques de ce module sont les
primitives du « mannequin » (ellipsoïdes de collision/aperçu) exprimées en FRACTIONS d'os ou par rapport
aux repères du squelette, et les points de la sole des sabots dérivés de la géométrie de l'os du sabot.

Espace : coordonnées Blender (x droite du poney, y avant, z haut, sol z = 0), armature à l'identité.
Pose : `basis` (F, N, 4, 4) = matrix_basis Blender de chaque joint ; local = rest_local · basis ;
monde = monde_parent · local.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import mathutil as mu

LIMBS = ("fl", "fr", "hl", "hr")
LIMB_SIDE = {"fl": "l", "fr": "r", "hl": "l", "hr": "r"}
LIMB_JOINTS = {
    "fl": ["scapula_l", "upperarm_l", "forearm_l", "front_cannon_l", "front_pastern_l", "front_hoof_l"],
    "fr": ["scapula_r", "upperarm_r", "forearm_r", "front_cannon_r", "front_pastern_r", "front_hoof_r"],
    "hl": ["thigh_l", "gaskin_l", "hind_cannon_l", "hind_pastern_l", "hind_hoof_l"],
    "hr": ["thigh_r", "gaskin_r", "hind_cannon_r", "hind_pastern_r", "hind_hoof_r"],
}
HOOF = {k: v[-1] for k, v in LIMB_JOINTS.items()}
NECK = ["neck_01", "neck_02", "neck_03", "neck_04", "neck_05", "neck_06"]
TAIL = [f"tail_{i:02d}" for i in range(1, 11)]
MANE = [f"mane_{i:02d}" for i in range(1, 7)]
FORELOCK = ["forelock_01", "forelock_02", "forelock_03"]
SPINE = ["spine_01", "spine_02", "spine_03"]
UPPER_BODY_MASK = (NECK + ["head", "jaw", "lip_lower", "lip_upper", "ear_l", "ear_tip_l", "ear_r", "ear_tip_r",
                           "eye_l", "eyelid_upper_l", "eyelid_lower_l", "eye_r", "eyelid_upper_r",
                           "eyelid_lower_r"] + FORELOCK + MANE)


@dataclass
class Skeleton:
    names: list
    parents: np.ndarray          # (N,) int, -1 pour la racine
    rest_world: np.ndarray       # (N,4,4) Blender
    lengths: np.ndarray          # (N,)

    def __post_init__(self):
        # les repères de repos lus dans Blender sont en float32 : on les ré-orthonormalise (écart ~1e-7)
        # pour que toutes les rotations locales exportées soient exactement orthonormées
        self.rest_world = np.array(self.rest_world, dtype=np.float64)
        self.rest_world[:, :3, :3] = mu.orthonormalize(self.rest_world[:, :3, :3])
        self.N = len(self.names)
        self.index = {n: i for i, n in enumerate(self.names)}
        self.rest_local = np.empty_like(self.rest_world)
        for i, p in enumerate(self.parents):
            self.rest_local[i] = self.rest_world[i] if p < 0 else np.linalg.inv(self.rest_world[p]) @ self.rest_world[i]
        self.head = self.rest_world[:, :3, 3].copy()
        self.tail = self.head + self.rest_world[:, :3, 1] * self.lengths[:, None]
        self.children = {i: [] for i in range(self.N)}
        for i, p in enumerate(self.parents):
            if p >= 0:
                self.children[int(p)].append(i)
        self._sole = {}
        for limb in LIMBS:
            self._sole[limb] = self._hoof_sole_points(limb)

    # --- construction --------------------------------------------------------------------------
    @classmethod
    def from_blender(cls, wh=None):
        """Construit l'armature via `rig.build_armature()` et lit les repères de repos (nécessite bpy)."""
        import bpy  # noqa: F401
        from .. import rig, template
        arm = rig.build_armature(wh=wh or template.REFERENCE_WH)
        names = rig.joint_names()
        W = rig.rest_world_b(arm)
        L = np.array([arm.data.bones[n].length for n in names])
        sk = cls(names=names, parents=np.array(rig.PARENTS), rest_world=W, lengths=L)
        return sk, arm

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(path, names=np.array(self.names), parents=self.parents, rest_world=self.rest_world,
                 lengths=self.lengths)

    @classmethod
    def load(cls, path):
        d = np.load(path)
        return cls(names=[str(n) for n in d["names"]], parents=d["parents"], rest_world=d["rest_world"],
                   lengths=d["lengths"])

    # --- accès ----------------------------------------------------------------------------------
    def idx(self, name):
        return self.index[name]

    def identity_basis(self, F: int = 1):
        b = np.zeros((F, self.N, 4, 4))
        b[:] = np.eye(4)
        return b

    def basis_from_angles(self, ang, trans=None):
        """ang (F,N,3) [flex X, twist Y, lat Z], trans (F,N,3) -> basis (F,N,4,4)."""
        R = mu.euler_to_mat(ang)
        return mu.make_tf(R, trans)

    def fk(self, basis):
        """basis (F,N,4,4) -> monde (F,N,4,4)."""
        basis = np.asarray(basis)
        F = basis.shape[0]
        W = np.empty((F, self.N, 4, 4))
        for i in range(self.N):
            loc = self.rest_local[i] @ basis[:, i]
            p = self.parents[i]
            W[:, i] = loc if p < 0 else W[:, p] @ loc
        return W

    def locals_from_basis(self, basis):
        """Transformations locales Blender (F,N,4,4) = rest_local · basis (format d'échange)."""
        return np.einsum("nij,fnjk->fnik", self.rest_local, basis)

    def chain_world(self, parent_world, joints, ang):
        """FK d'une chaîne (indices `joints`, chaque joint enfant du précédent, le premier enfant du
        repère `parent_world`) pour des angles (n,3). Renvoie la liste des repères monde (4x4)."""
        out = []
        M = parent_world
        R = mu.euler_to_mat(ang)
        for k, j in enumerate(joints):
            B = np.eye(4)
            B[:3, :3] = R[k]
            M = M @ self.rest_local[j] @ B
            out.append(M)
        return out

    # --- sabots ---------------------------------------------------------------------------------
    def _hoof_sole_points(self, limb):
        """Points de la sole (repère local de l'os du sabot) : pince, talons, mamelles.

        Pince = queue de l'os du sabot (au sol au repos). Talon : 0,045 m en arrière de la projection
        au sol de la tête de l'os (articulation interphalangienne distale) [A]. Largeur ±0,045 m [A]
        (sabot de poney de ~10-11 cm de large, ordre de grandeur ; à recaler sur le maillage)."""
        j = self.idx(HOOF[limb])
        W = self.rest_world[j]
        head, tail = self.head[j], self.tail[j]
        fwd = np.array([0.0, 1.0, 0.0])
        lat = np.array([1.0, 0.0, 0.0])
        heel = np.array([head[0], head[1] - 0.045, 0.0])
        mid = 0.5 * (heel + np.array([tail[0], tail[1], 0.0]))
        pts_w = np.array([
            [tail[0], tail[1], 0.0],                 # 0 pince
            heel - 0.035 * lat,                       # 1 talon gauche (côté -x)
            heel + 0.035 * lat,                       # 2 talon droit
            mid - 0.045 * lat,                        # 3 mamelle -x
            mid + 0.045 * lat,                        # 4 mamelle +x
            heel,                                     # 5 talon (milieu)
        ])
        inv = np.linalg.inv(W)
        return (inv[:3, :3] @ pts_w.T).T + inv[:3, 3]

    def sole_local(self, limb):
        return self._sole[limb]

    def sole_world(self, W, limb):
        """W (F,N,4,4) -> (F,6,3) points de sole en monde."""
        j = self.idx(HOOF[limb])
        P = self._sole[limb]
        Wj = W[:, j]
        return np.einsum("fij,pj->fpi", Wj[:, :3, :3], P) + Wj[:, None, :3, 3]

    def rest_sole_world(self, limb):
        j = self.idx(HOOF[limb])
        W = self.rest_world[j]
        return (W[:3, :3] @ self._sole[limb].T).T + W[:3, 3]


# --- Mannequin : ellipsoïdes attachés aux os (aperçus + contrôle de pénétration du corps) -------
# Chaque entrée : (os, centre en fraction de longueur d'os le long de l'os, rayons (rx, ry, rz) en
# FRACTION de la hauteur au garrot WH dans les axes de l'os, décalage du centre (dx, dz) en fraction de
# WH dans les axes MONDE au repos). Formes approximatives d'un poney [A] — servent à voir la silhouette et à détecter
# un corps qui traverse le sol ; le vrai maillage (agent « body ») les remplace dès qu'il existe.
MANNEQUIN = [
    # tronc (calé sur les repères du SPEC §2 : sternum 0,53 WH, ventre 0,51 WH, garrot/croupe ≈ WH)
    ("spine_03", 0.45, (0.160, 0.235, 0.200), (0.0, -0.080)),
    ("spine_03", 0.20, (0.070, 0.130, 0.085), (0.0, 0.045)),      # garrot
    ("spine_02", 0.50, (0.170, 0.235, 0.230), (0.0, -0.130)),
    ("spine_01", 0.45, (0.160, 0.200, 0.190), (0.0, -0.120)),
    ("hips", 0.35, (0.160, 0.195, 0.190), (0.0, -0.090)),
    # encolure (vertèbres basses et profondes à la base [NV] : volume décalé vers le haut/la crête)
    ("neck_01", 0.5, (0.105, 0.110, 0.150), (0.0, 0.060)),
    ("neck_02", 0.5, (0.090, 0.100, 0.130), (0.0, 0.050)),
    ("neck_03", 0.5, (0.075, 0.090, 0.110), (0.0, 0.035)),
    ("neck_04", 0.5, (0.062, 0.080, 0.095), (0.0, 0.025)),
    ("neck_05", 0.5, (0.055, 0.070, 0.085), (0.0, 0.015)),
    ("head", 0.30, (0.072, 0.120, 0.090), (0.0, -0.010)),
    ("head", 0.75, (0.050, 0.110, 0.060), (0.0, -0.010)),
    ("ear_l", 0.9, (0.012, 0.055, 0.020), (0.0, 0.0)),
    ("ear_r", 0.9, (0.012, 0.055, 0.020), (0.0, 0.0)),
    # queue
    ("tail_01", 0.5, (0.030, 0.060, 0.035), (0.0, 0.0)),
    ("tail_02", 0.5, (0.030, 0.050, 0.032), (0.0, 0.0)),
    ("tail_03", 0.5, (0.034, 0.050, 0.030), (0.0, 0.0)),
    ("tail_04", 0.5, (0.040, 0.055, 0.030), (0.0, 0.0)),
    ("tail_05", 0.5, (0.045, 0.055, 0.030), (0.0, 0.0)),
    ("tail_06", 0.5, (0.048, 0.055, 0.028), (0.0, 0.0)),
    ("tail_07", 0.5, (0.048, 0.055, 0.026), (0.0, 0.0)),
    ("tail_08", 0.5, (0.045, 0.055, 0.024), (0.0, 0.0)),
    ("tail_09", 0.5, (0.040, 0.055, 0.022), (0.0, 0.0)),
    ("tail_10", 0.5, (0.032, 0.055, 0.018), (0.0, 0.0)),
]
for _s in ("l", "r"):
    MANNEQUIN += [
        (f"scapula_{_s}", 0.50, (0.040, 0.190, 0.090), (0.0, 0.0)),
        (f"upperarm_{_s}", 0.50, (0.055, 0.110, 0.070), (0.0, 0.0)),
        (f"forearm_{_s}", 0.35, (0.045, 0.110, 0.050), (0.0, 0.0)),
        (f"forearm_{_s}", 0.85, (0.030, 0.050, 0.035), (0.0, 0.0)),
        (f"front_cannon_{_s}", 0.50, (0.022, 0.090, 0.026), (0.0, 0.0)),
        (f"front_pastern_{_s}", 0.15, (0.026, 0.030, 0.030), (0.0, 0.0)),
        (f"front_pastern_{_s}", 0.60, (0.020, 0.045, 0.020), (0.0, 0.0)),
        (f"thigh_{_s}", 0.45, (0.075, 0.190, 0.095), (0.0, -0.035)),
        (f"gaskin_{_s}", 0.40, (0.045, 0.140, 0.060), (0.0, 0.0)),
        (f"hind_cannon_{_s}", 0.50, (0.022, 0.110, 0.028), (0.0, 0.0)),
        (f"hind_pastern_{_s}", 0.15, (0.026, 0.030, 0.030), (0.0, 0.0)),
        (f"hind_pastern_{_s}", 0.60, (0.020, 0.045, 0.020), (0.0, 0.0)),
    ]
HOOF_ELLIPSOIDS = []  # les sabots sont modélisés à part (coin de sole) dans l'aperçu
DISTAL_BONES = {f"{p}_{s}" for s in ("l", "r") for p in ("front_pastern", "hind_pastern", "front_cannon",
                                                           "hind_cannon")}


def _fib_sphere(n):
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    th = np.pi * (1 + 5 ** 0.5) * i
    return np.stack([np.cos(th) * np.sin(phi), np.sin(th) * np.sin(phi), np.cos(phi)], axis=1)


def mannequin_ellipsoids(sk: Skeleton, wh: float | None = None):
    """Liste de (joint_index, centre_local (3,), rayons (3,)) en coordonnées locales de l'os."""
    if wh is None:
        wh = estimate_wh(sk)
    out = []
    for bone, frac, radii, off in MANNEQUIN:
        j = sk.idx(bone)
        # centre : point à `frac` le long de l'os + décalage (dx, dz) en axes MONDE au repos (× WH),
        # converti dans le repère local de l'os ; rayons en fraction de WH dans les axes de l'os
        # (x : latéral, y : le long de l'os, z : perpendiculaire)
        cw = sk.head[j] + frac * (sk.tail[j] - sk.head[j]) + np.array([off[0], 0.0, off[1]]) * wh
        R = sk.rest_world[j][:3, :3]
        c = R.T @ (cw - sk.head[j])
        r = np.array(radii, dtype=np.float64) * wh
        out.append((j, c, r))
    return out


def estimate_wh(sk: Skeleton) -> float:
    """Hauteur au garrot estimée depuis le squelette : le sommet de l'omoplate (cartilage) est à
    ~0,92-0,95 WH (anatomy.md §1.4 [I]) ; le gabarit le place à 1,20/1,30 = 0,923 WH."""
    return float(sk.head[sk.idx("scapula_l")][2] / 0.923)


def body_sample_points(sk: Skeleton, n_per: int = 60, wh: float | None = None):
    """Points d'échantillonnage du mannequin : (joint_idx (P,), points locaux (P,3), distal (P,) bool)."""
    ell = mannequin_ellipsoids(sk, wh)
    S = _fib_sphere(n_per)
    js, ps, dist = [], [], []
    for j, c, r in ell:
        js.append(np.full(n_per, j))
        ps.append(c + S * r)
        dist.append(np.full(n_per, sk.names[j] in DISTAL_BONES))
    return np.concatenate(js), np.concatenate(ps), np.concatenate(dist)


def transform_points(W, joint_idx, local_pts):
    """W (F,N,4,4), points locaux attachés à des joints -> (F,P,3) monde."""
    Wj = W[:, joint_idx]
    R = Wj[..., :3, :3]
    t = Wj[..., :3, 3]
    return np.einsum("fpij,pj->fpi", R, local_pts) + t
