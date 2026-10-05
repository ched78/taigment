"""Gabarit squelettique du poney (cf. Docs/SPEC.md §2-§3).

Coordonnées Blender (x = droite du poney, y = avant, z = haut), mètres, pour une hauteur au garrot
WH = 1.30 m (type Welsh B / Connemara). Côté gauche = x < 0 ; la droite est générée par miroir.

Sources : angles de repos mesurés sur chevaux, hauteurs articulaires inférées des indices de poneys
(Docs/research/anatomy.md §1.3-1.5). Ce sont des POINTS DE DÉPART à calibrer visuellement.
L'ordre de JOINTS est l'ordre USD/runtime (parents avant enfants) et ne doit pas changer.
"""
from __future__ import annotations

import numpy as np

REFERENCE_WH = 1.30

# Repères de surface utiles à la modélisation (coordonnées Blender, WH = 1.30).
LANDMARKS = {
    "withers_top": (0.0, 0.30, 1.30),
    "point_of_shoulder_l": (-0.17, 0.62, 0.90),
    "point_of_buttock_l": (-0.10, -0.77, 1.00),
    "croup_top": (0.0, -0.48, 1.31),
    "tail_head": (0.0, -0.79, 1.20),
    "sternum_bottom": (0.0, 0.30, 0.69),
    "belly_bottom": (0.0, -0.10, 0.66),
    "poll_top": (0.0, 0.88, 1.49),
    "muzzle_tip": (0.0, 1.27, 1.09),
}

# Axe de la tête : de l'articulation atlanto-occipitale vers le centre du bout du nez.
HEAD_JOINT = np.array([0.0, 0.90, 1.43])
MUZZLE_CENTER = np.array([0.0, 1.25, 1.08])
_HEAD_AXIS = (MUZZLE_CENTER - HEAD_JOINT) / np.linalg.norm(MUZZLE_CENTER - HEAD_JOINT)
_HEAD_DORSAL = np.array([0.0, -_HEAD_AXIS[2], _HEAD_AXIS[1]])  # perpendiculaire, côté chanfrein


def head_point(s: float, d: float, x: float = 0.0) -> tuple:
    """Point dans le repère de la tête : s le long de l'axe nuque→nez, d vers le chanfrein, x latéral."""
    p = HEAD_JOINT + s * _HEAD_AXIS + d * _HEAD_DORSAL + np.array([x, 0.0, 0.0])
    return tuple(float(round(v, 4)) for v in p)


def _tail_chain():
    pts = [(0.0, -0.79, 1.19), (0.0, -0.85, 1.13), (0.0, -0.89, 1.05), (0.0, -0.91, 0.97),
           (0.0, -0.92, 0.88), (0.0, -0.925, 0.78), (0.0, -0.93, 0.68), (0.0, -0.93, 0.58),
           (0.0, -0.93, 0.48), (0.0, -0.93, 0.38), (0.0, -0.93, 0.28)]
    out = []
    for i in range(10):
        parent = "hips" if i == 0 else f"tail_{i:02d}"
        out.append((f"tail_{i + 1:02d}", parent, pts[i], pts[i + 1]))
    return out


def _neck_chain():
    pts = [(0.0, 0.46, 0.95), (0.0, 0.56, 1.04), (0.0, 0.65, 1.14), (0.0, 0.73, 1.25),
           (0.0, 0.80, 1.34), (0.0, 0.86, 1.40), tuple(HEAD_JOINT)]
    out = []
    for i in range(6):
        parent = "spine_03" if i == 0 else f"neck_{i:02d}"
        out.append((f"neck_{i + 1:02d}", parent, pts[i], pts[i + 1]))
    return out


# (nom, parent, tête, queue) — côté gauche uniquement pour les membres ; "_r" ajouté par miroir.
_HIND_L = [
    ("thigh_l", "hips", (-0.13, -0.60, 1.03), (-0.155, -0.417, 0.757)),
    ("gaskin_l", "thigh_l", (-0.155, -0.417, 0.757), (-0.12, -0.625, 0.416)),
    ("hind_cannon_l", "gaskin_l", (-0.12, -0.625, 0.416), (-0.11, -0.605, 0.150)),
    ("hind_pastern_l", "hind_cannon_l", (-0.11, -0.605, 0.150), (-0.11, -0.532, 0.046)),
    ("hind_hoof_l", "hind_pastern_l", (-0.11, -0.532, 0.046), (-0.11, -0.467, 0.0)),
]
_FRONT_L = [
    ("scapula_l", "spine_03", (-0.07, 0.33, 1.20), (-0.16, 0.58, 0.89)),
    ("upperarm_l", "scapula_l", (-0.16, 0.58, 0.89), (-0.14, 0.42, 0.71)),
    ("forearm_l", "upperarm_l", (-0.14, 0.42, 0.71), (-0.125, 0.42, 0.35)),
    ("front_cannon_l", "forearm_l", (-0.125, 0.42, 0.35), (-0.115, 0.42, 0.137)),
    ("front_pastern_l", "front_cannon_l", (-0.115, 0.42, 0.137), (-0.115, 0.496, 0.046)),
    ("front_hoof_l", "front_pastern_l", (-0.115, 0.496, 0.046), (-0.115, 0.565, 0.0)),
]


def _mirror(entries):
    out = []
    for name, parent, head, tail in entries:
        out.append((name[:-2] + "_r",
                    parent[:-2] + "_r" if parent.endswith("_l") else parent,
                    (-head[0], head[1], head[2]), (-tail[0], tail[1], tail[2])))
    return out


def eye_axes(sign: float):
    """Axe optique g (horizontal, vers l'extérieur) et axe de la fente h (horizontal, vers le canthus médial).

    [A] axe optique horizontal à 33° en avant de la latérale. Les os de l'œil et des paupières sont orientés
    le long de g : avec la règle de roulis du projet (X local = X monde projeté ⊥ à l'os), leur axe X local
    est exactement ±h, l'axe de la fente palpébrale ⇒ une rotation autour de X local ferme les paupières
    (cf. rapport de l'agent « body » pour le sens).
    """
    import math as _m
    beta = _m.radians(33.0)
    g = np.array([sign * _m.cos(beta), _m.sin(beta), 0.0])
    h = np.array([-sign * _m.sin(beta), _m.cos(beta), 0.0])
    return g, h


def _eye(side: str, sign: float):
    # Centre du globe : ajusté au maillage du corps (body_sdf), cf. rapport de l'agent « body ».
    c = np.array(head_point(0.17, 0.02, sign * 0.080))
    gh, _ = eye_axes(sign)
    rnd = lambda v: tuple(float(round(x, 4)) for x in v)
    return [
        (f"eye_{side}", "head", rnd(c), rnd(c + 0.030 * gh)),
        (f"eyelid_upper_{side}", "head", rnd(c), rnd(c + 0.026 * gh)),
        (f"eyelid_lower_{side}", "head", rnd(c), rnd(c + 0.022 * gh)),
    ]


def _ear(side: str, sign: float):
    base = head_point(0.0, 0.07, sign * 0.055)
    mid = (base[0] + sign * 0.010, base[1] + 0.015, base[2] + 0.065)
    tip = (base[0] + sign * 0.015, base[1] + 0.025, base[2] + 0.13)
    return [(f"ear_{side}", "head", base, mid), (f"ear_tip_{side}", f"ear_{side}", mid, tip)]


def _mane():
    crest = [(0.0, 0.38, 1.27), (0.0, 0.48, 1.32), (0.0, 0.58, 1.37), (0.0, 0.67, 1.42),
             (0.0, 0.75, 1.46), (0.0, 0.82, 1.49)]
    # La crinière tombe traditionnellement du côté droit (+x).
    return [(f"mane_{i + 1:02d}", f"neck_{i + 1:02d}", p, (p[0] + 0.06, p[1], p[2] - 0.10))
            for i, p in enumerate(crest)]


def _forelock():
    pts = [head_point(0.02, 0.075), head_point(0.10, 0.085), head_point(0.18, 0.09), head_point(0.26, 0.09)]
    return [(f"forelock_{i + 1:02d}", "head" if i == 0 else f"forelock_{i:02d}", pts[i], pts[i + 1])
            for i in range(3)]


def joint_table(wh: float = REFERENCE_WH):
    """Liste ordonnée de dicts {name, parent, head, tail} (coordonnées Blender, mètres)."""
    j = [
        ("root", None, (0.0, 0.0, 0.0), (0.0, 0.25, 0.0)),
        ("body", "root", (0.0, -0.05, 0.98), (0.0, 0.20, 0.98)),
        ("hips", "body", (0.0, -0.42, 1.17), (0.0, -0.76, 1.16)),
    ]
    j += _tail_chain()
    j += _HIND_L + _mirror(_HIND_L)
    j += [
        ("spine_01", "body", (0.0, -0.42, 1.17), (0.0, -0.14, 1.15)),
        ("spine_02", "spine_01", (0.0, -0.14, 1.15), (0.0, 0.14, 1.11)),
        ("belly", "spine_02", (0.0, -0.10, 0.82), (0.0, -0.10, 0.70)),
        ("stirrup_l", "spine_02", (-0.17, 0.20, 1.17), (-0.25, 0.20, 0.66)),
        ("stirrup_r", "spine_02", (0.17, 0.20, 1.17), (0.25, 0.20, 0.66)),
        ("spine_03", "spine_02", (0.0, 0.14, 1.11), (0.0, 0.42, 0.99)),
    ]
    j += _FRONT_L + _mirror(_FRONT_L)
    j += _neck_chain()
    j += [
        ("head", "neck_06", tuple(HEAD_JOINT), tuple(MUZZLE_CENTER)),
        # ATM et lèvres : ajustés au maillage du corps (face raccourcie, body_sdf.FACE_K) — agent « body »
        ("jaw", "head", head_point(0.075, -0.035), head_point(0.445, -0.080)),
        ("lip_lower", "jaw", head_point(0.425, -0.075), head_point(0.470, -0.072)),
        ("lip_upper", "head", head_point(0.422, -0.020), head_point(0.476, -0.026)),
    ]
    j += _ear("l", -1.0) + _ear("r", 1.0)
    j += _eye("l", -1.0) + _eye("r", 1.0)
    j += _forelock()
    j += _mane()

    k = wh / REFERENCE_WH
    out = []
    for name, parent, head, tail in j:
        out.append({
            "name": name,
            "parent": parent,
            "head": tuple(float(v) * k for v in head),
            "tail": tuple(float(v) * k for v in tail),
        })
    names = [e["name"] for e in out]
    assert len(names) == len(set(names)) == 70, (len(names), len(set(names)))
    index = {n: i for i, n in enumerate(names)}
    for e in out:
        if e["parent"] is not None:
            assert index[e["parent"]] < index[e["name"]], f"parent après enfant: {e['name']}"
    return out


JOINT_NAMES = [e["name"] for e in joint_table()]


def joint_index(name: str) -> int:
    return JOINT_NAMES.index(name)


if __name__ == "__main__":
    for i, e in enumerate(joint_table()):
        print(f"{i:2d} {e['name']:18s} parent={str(e['parent']):16s} head={e['head']} tail={e['tail']}")
