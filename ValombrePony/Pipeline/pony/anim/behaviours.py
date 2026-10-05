"""Comportements (clips non locomoteurs) — chorégraphies « à l'œil » [A].

Aucune donnée vérifiée n'existe dans les rapports pour ces mouvements (gaits.md §4 : tout est [U]) :
durées et amplitudes sont des approximations artistiques d'après des connaissances générales, à relire
sur vidéo de référence (SPEC §7 « Approximations assumées »). Les seules contraintes « dures » appliquées
sont physiques/anatomiques : sabots plantés sans glissement (IK), corps hors du sol, limites du SPEC §3
(bornes de l'IK ; les poses FK sont vérifiées par `checks.py`), couplage grasset↔jarret.

Conventions des angles (delta / pose de liaison, degrés) : cf. limb_ik.py et poses.py.
  encolure/tête : + = relever ; épaule : − = flexion ; coude : + = flexion ; carpe (front_cannon) :
  − = flexion ; boulet (pastern) : − = flexion ; sabot : − = flexion ; hanche (thigh) : + = flexion ;
  grasset (gaskin) : − = flexion (jarret couplé automatiquement) ; queue : − = relever ;
  latéral (Z) : + = vers la gauche pour les os orientés vers l'avant.
"""
from __future__ import annotations

import numpy as np

from .poses import Choreo, FKSpan, Step, build_choreo
from .skeleton import FORELOCK, MANE, NECK, TAIL, UPPER_BODY_MASK, Skeleton

A_NOTE = "[A] chorégraphie artistique non vérifiée (aucune donnée sourcée, cf. gaits.md §4) ; à relire sur vidéo."

# Pose debout de référence (début/fin des comportements, compatible avec `idle`)
STAND_BODY = dict(pitch=0.0, roll=0.0, yaw=0.0, x=0.0, y=0.0, z=-0.012)


def _neck(flex_total=0.0, lat_total=0.0, twist_total=0.0, w=(0.26, 0.24, 0.18, 0.14, 0.10, 0.08)):
    """Répartit une flexion / inclinaison / torsion totale sur neck_01..06 (degrés)."""
    return {n: (flex_total * wi, twist_total * wi, lat_total * wi) for n, wi in zip(NECK, w)}


def _tail(lift=0.0, lat=0.0, curl=0.0):
    """Queue : relevé du tronçon osseux, balancement latéral, enroulement des crins (degrés)."""
    dock = [1.0, 0.8, 0.6, 0.4, 0, 0, 0, 0, 0, 0]
    hang = [0, 0, 0, 0, 0.6, 0.8, 0.6, 0.4, 0.2, 0.1]
    out = {}
    for i, n in enumerate(TAIL):
        fl = -lift * dock[i] + lift * 0.9 * hang[i] / 2.7 + curl * (0.0 if i < 4 else 0.25)
        out[n] = (fl, 0.0, lat * (0.05 + 0.03 * i))
    return out


def _k(t, *dicts, **kw):
    d = {}
    for x in dicts:
        d.update(x)
    d.update(kw)
    return (t, d)


# ----------------------------------------------------------------------------------------------
def idle():
    dur = 6.0
    keys = [
        _k(0.0, _neck(-2, 0), {"head": -2, "hips": (0, 0, 0)}, _tail(0, 0),
           body=dict(STAND_BODY, x=0.0, y=0.0, roll=0.0, pitch=0.0)),
        _k(1.5, _neck(-4, 5), {"head": (-1, 0, 2), "hips": (0, 1.5, 0)}, _tail(0, -3),
           body=dict(STAND_BODY, x=0.012, y=-0.006, roll=0.7, pitch=-0.3, z=-0.014)),
        _k(3.0, _neck(-1, 2), {"head": (-3, 0, 1)}, _tail(0, 2),
           body=dict(STAND_BODY, x=0.002, y=0.004, roll=0.1, pitch=0.2, z=-0.010)),
        _k(3.8, _tail(0, 14)),
        _k(4.4, _tail(0, -10)),
        _k(4.5, _neck(-5, -4), {"head": (-2, 0, -2), "hips": (0, -1.2, 0)},
           body=dict(STAND_BODY, x=-0.010, y=-0.003, roll=-0.6, pitch=-0.2, z=-0.013)),
        _k(5.0, _tail(0, 2)),
    ]
    return Choreo(
        name="idle", duration=dur, loop=True, keys=keys,
        plants0={l: (0.0, 0.0) for l in ("fl", "fr", "hl", "hr")},
        notes="Repos debout, 4 sabots plantés : transferts de poids lents (±1,2 cm latéral, roulis ±0,7°), "
              "encolure qui regarde légèrement autour, un coup de queue. Respiration, oreilles, regard et "
              "clignements laissés au runtime (SPEC §8). " + A_NOTE)


def idle_rest_hind():
    # Postérieur gauche au repos : hanche basse, pince au sol, talons levés ; appui sur les 3 autres,
    # grasset droit « verrouillé » [V : appareil de soutien / blocage de la rotule, anatomy.md §1.7]
    dur = 6.0
    rest = dict(STAND_BODY, x=0.018, z=-0.020, roll=1.6, pitch=-0.6)
    keys = [
        _k(0.0, _neck(-9, 0), {"head": -6, "hips": (0.0, 4.5, 0.0)}, _tail(0, 0), body=dict(rest)),
        _k(2.0, _neck(-10, 3), {"head": (-7, 0, 1)}, _tail(0, 2), body=dict(rest, x=0.020, roll=1.8)),
        _k(3.5, _neck(-8, 1), {"head": -5}, _tail(0, -2), body=dict(rest, x=0.016, y=0.003, roll=1.5)),
        _k(5.0, _neck(-9, -2), {"head": (-6, 0, -1)}, _tail(0, 1), body=dict(rest, x=0.019, roll=1.7)),
    ]
    return Choreo(
        name="idle_rest_hind", duration=dur, loop=True, keys=keys,
        plants0={"fl": (0.0, 0.0), "fr": (0.0, 0.0), "hl": (0.025, 0.06, 38.0), "hr": (0.0, 0.0)},
        fetlock_pref={"hl": -25.0},
        notes="Repos d'un postérieur (gauche) : bassin incliné (hanche gauche basse), pince au sol talons levés "
              "~38°, boulet fléchi, poids sur les trois autres membres [R qualitatif : anatomy.md §1.7] ; "
              "tête basse (somnolence). Amplitudes " + A_NOTE)


# ----------------------------------------------------------------------------------------------
# Brouter
GRAZE_NECK = _neck()  # remplacé ci-dessous
GRAZE_NECK = {n: (v, 0.0, 0.0) for n, v in zip(NECK, (-34, -32, -26, -8, 8, 10))}
GRAZE_BODY = dict(STAND_BODY, pitch=-4.0, z=-0.058, y=0.02)
GRAZE_PLANTS = {"fl": (0.0, 0.20), "fr": (0.0, 0.0), "hl": (0.0, 0.0), "hr": (0.0, 0.0)}
SQUARE = {l: (0.0, 0.0) for l in ("fl", "fr", "hl", "hr")}


def graze_down():
    keys = [
        _k(0.0, _neck(0, 0), {"head": 0}, _tail(0, 0), body=dict(STAND_BODY)),
        _k(0.45, _neck(-14, 0), {"head": 4}, body=dict(STAND_BODY, pitch=-1.0, z=-0.02, y=0.005)),
        _k(1.15, {n: (v * 0.9, 0, 0) for n, v in zip(NECK, (-34, -32, -26, -8, 8, 10))}, {"head": 44},
           body=dict(GRAZE_BODY, z=-0.04)),
        _k(1.5, GRAZE_NECK, {"head": 52}, _tail(0, 0), body=dict(GRAZE_BODY)),
    ]
    return Choreo(
        name="graze_down", duration=1.5, keys=keys, plants0=dict(SQUARE),
        steps=[Step("fl", 0.30, 0.80, to=GRAZE_PLANTS["fl"], lift=0.05, carpus=35, flip=25)],
        events=[(0.30, "foot_up_fl"), (0.80, "foot_down_fl")],
        notes="Baisser l'encolure jusqu'à l'herbe, un antérieur (gauche) avancé de 20 cm (posture de pâturage "
              "« décalée », gaits.md §4 [U]) ; nuque ouverte, bout du nez à ~1 cm du sol. " + A_NOTE)


def graze_loop():
    dur = 5.0
    keys = []
    # base + balayage lent de l'encolure (±7°) ; arrachages d'herbe (petit coup de tête) ; mastication
    base = lambda lat=0.0, hd=52.0, hd_lat=0.0: (
        {n: (v, 0.0, lat * w) for n, v, w in zip(NECK, (-34, -32, -26, -8, 8, 10), (0.25, 0.25, 0.2, 0.15, 0.1, 0.05))},
        {"head": (hd, 0.0, hd_lat)})
    plan = [(0.0, 0.0, 52, 0), (0.55, 2.0, 55, 1), (0.70, 3.0, 47, 3), (0.85, 3.5, 52, 2),
            (1.9, 6.0, 52, 2), (2.35, 6.5, 55, 2), (2.50, 6.5, 46, 5), (2.70, 6.0, 52, 3),
            (3.6, -5.0, 52, -2), (4.05, -6.0, 55, -2), (4.20, -6.0, 47, -5), (4.40, -5.0, 52, -3)]
    for t, lat, hd, hl in plan:
        n, h = base(lat, hd, hl)
        keys.append(_k(t, n, h))
    # mâchoire : cycles de mastication ~1,5 Hz entre les arrachages [A]
    chew_t = []
    t = 0.95
    while t < dur - 0.3:
        if not any(abs(t - a) < 0.35 for a in (0.62, 2.42, 4.12)):
            keys.append(_k(t, {"jaw": -6.0, "lip_lower": -4.0}))
            keys.append(_k(t + 0.32, {"jaw": -0.5, "lip_lower": 0.0}))
            chew_t.append(round(t + 0.32, 3))
        t += 0.66
    keys.append(_k(0.0, {"jaw": 0.0, "lip_lower": 0.0, "lip_upper": 0.0}))
    for a in (0.62, 2.42, 4.12):     # préhension : lèvre supérieure
        keys.append(_k(a - 0.12, {"lip_upper": -8.0}))
        keys.append(_k(a + 0.10, {"lip_upper": 0.0}))
    keys += [_k(0.0, _tail(0, 0), body=dict(GRAZE_BODY)), _k(2.0, body=dict(GRAZE_BODY, x=0.008, roll=0.5)),
             _k(3.2, _tail(0, 18)), _k(3.6, _tail(0, -14)), _k(4.0, _tail(0, 4)),
             _k(4.0, body=dict(GRAZE_BODY, x=-0.006, roll=-0.4))]
    return Choreo(
        name="graze_loop", duration=dur, loop=True, keys=keys, plants0=dict(GRAZE_PLANTS),
        events=[(a, "chew") for a in sorted(chew_t)],
        notes="Pâturage en boucle : trois arrachages d'herbe (préhension lèvre supérieure + petit coup de tête), "
              "mastication ~1,5 Hz (évènements `chew`), balayage lent de l'encolure, un coup de queue ; "
              "sabots plantés (antérieur gauche avancé). " + A_NOTE)


def graze_up():
    keys = [
        _k(0.0, GRAZE_NECK, {"head": 52}, _tail(0, 0), body=dict(GRAZE_BODY)),
        _k(0.45, {n: (v * 0.55, 0, 0) for n, v in zip(NECK, (-34, -32, -26, -8, 8, 10))}, {"head": 30},
           body=dict(GRAZE_BODY, z=-0.035, pitch=-2.5)),
        _k(0.9, _neck(-3, 0), {"head": 2}, body=dict(STAND_BODY, z=-0.016)),
        _k(1.2, _neck(0, 0), {"head": 0}, _tail(0, 0), body=dict(STAND_BODY)),
    ]
    return Choreo(
        name="graze_up", duration=1.2, keys=keys, plants0=dict(GRAZE_PLANTS),
        steps=[Step("fl", 0.40, 0.90, to=(0.0, 0.0), lift=0.05, carpus=35, flip=25)],
        events=[(0.40, "foot_up_fl"), (0.90, "foot_down_fl")],
        notes="Relever la tête depuis le pâturage et ramener l'antérieur gauche (debout carré). " + A_NOTE)


# ----------------------------------------------------------------------------------------------
# Couches masquées (haut du corps)
def _osc(t0, t1, period, amp0, decay=1.0):
    """Clés alternées ± (amplitude décroissante) entre t0 et t1."""
    out = []
    n = int(round((t1 - t0) / (period / 2)))
    for i in range(n + 1):
        a = amp0 * (1.0 - decay * i / max(n, 1)) * (1 if i % 2 == 0 else -1)
        out.append((t0 + i * period / 2, a if 0 < i < n else 0.0))
    return out


def head_shake():
    dur = 1.2
    keys = [_k(0.0, _neck(0, 0), {"head": 0, "jaw": 0, "ear_l": 0, "ear_r": 0, "ear_tip_l": 0, "ear_tip_r": 0}),
            _k(0.12, _neck(-6, 0), {"head": -4})]
    # rotation rapide autour de l'axe nuque/encolure (torsion + inclinaison) ~3,3 Hz, décroissante
    for t, a in _osc(0.15, 1.05, 0.30, 26.0, decay=0.85):
        keys.append(_k(t, {n: (-3.0 if a else 0.0, a * w, a * w * 0.4)
                           for n, w in zip(NECK, (0.0, 0.05, 0.12, 0.20, 0.25, 0.28))},
                       {"head": (-3.0 if a else 0.0, a * 0.55, a * 0.25)}))
        lag = t + 0.07
        keys.append(_k(lag, {"ear_l": (0, -a * 0.6, a * 0.5), "ear_r": (0, -a * 0.6, a * 0.5),
                             "ear_tip_l": (0, 0, a * 0.6), "ear_tip_r": (0, 0, a * 0.6)}))
        keys.append(_k(t + 0.09, {m: (0, 0, -a * 0.5) for m in MANE},
                       {f: (a * 0.3, 0, -a * 0.6) for f in FORELOCK}))
    keys.append(_k(dur, _neck(0, 0), {"head": 0, "ear_l": 0, "ear_r": 0, "ear_tip_l": 0, "ear_tip_r": 0},
                   {m: 0 for m in MANE}, {f: 0 for f in FORELOCK}))
    return Choreo(
        name="head_shake", duration=dur, keys=keys, plants0=dict(SQUARE), mask=list(UPPER_BODY_MASK),
        notes="Secouement de tête : rotation rapide (~3,3 Hz, 3 oscillations décroissantes) autour de l'axe "
              "nuque/encolure, oreilles, crinière et toupet en retard (gaits.md §4 [U]). Couche MASQUÉE : "
              "encolure, tête, mâchoire, lèvres, oreilles, yeux, toupet, crinière (jouable en marchant). " + A_NOTE)


def neigh():
    dur = 2.2
    keys = [
        _k(0.0, _neck(0, 0), {"head": 0, "jaw": 0, "lip_lower": 0, "lip_upper": 0, "belly": 0},
           **{"w:face_nostril_flare": 0.0, "w:face_mouth_open_soft": 0.0, "w:body_breathe": 0.3}),
        _k(0.30, **{"w:body_breathe": 0.95}),                       # inspiration
        _k(0.35, _neck(14, 0), {"head": 6}, **{"w:face_nostril_flare": 1.0}),
        _k(0.45, {"jaw": -7.0, "lip_lower": -4}, **{"w:face_mouth_open_soft": 0.75}),
        _k(1.55, {"jaw": -6.0, "lip_lower": -3}, **{"w:face_mouth_open_soft": 0.65}),
        _k(1.40, _neck(12, 2), {"head": (4, 0, 2)}),
        _k(1.85, {"jaw": 0.0, "lip_lower": 0}, **{"w:face_mouth_open_soft": 0.0, "w:face_nostril_flare": 0.5}),
        _k(2.2, _neck(0, 0), {"head": 0, "belly": 0}, **{"w:face_nostril_flare": 0.0, "w:body_breathe": 0.3}),
    ]
    # cri : contractions rythmiques des flancs (~5 Hz) pendant l'expiration [A]
    t = 0.50
    i = 0
    while t < 1.55:
        lvl = 0.85 - 0.6 * (t - 0.5) / 1.05
        keys.append(_k(t, {"belly": 2.0 if i % 2 == 0 else -1.0, "jaw": -7.0 if i % 2 == 0 else -5.5},
                       **{"w:body_breathe": lvl - (0.12 if i % 2 == 0 else 0.0)}))
        t += 0.1
        i += 1
    return Choreo(
        name="neigh", duration=dur, keys=keys, plants0=dict(SQUARE), mask=list(UPPER_BODY_MASK) + ["belly"],
        notes="Hennissement : encolure et tête relevées, naseaux dilatés (`face_nostril_flare`), bouche "
              "entrouverte (`jaw` + `face_mouth_open_soft`), contractions rythmiques des flancs (`body_breathe`, "
              "joint `belly`) ; gaits.md §4 [U]. Couche MASQUÉE haut du corps + flancs (`belly` et la piste "
              "`body_breathe`). Durée du cri non vérifiée. " + A_NOTE)


# ----------------------------------------------------------------------------------------------
def paw():
    dur = 1.6
    keys = [_k(0.0, _neck(-16, 0), {"head": 6}, _tail(0, 0),
               body=dict(STAND_BODY, x=-0.015, y=-0.012, roll=-1.0, pitch=-0.5, z=-0.016)),
            _k(0.8, _neck(-18, 2), {"head": 7}, body=dict(STAND_BODY, x=-0.016, y=-0.014, roll=-1.1, z=-0.017))]
    # pince AD (dx, dy, dz, tangage°, carpe°) : lever, tendre vers l'avant, frapper, racler vers l'arrière
    tr = []
    for k0 in (0.0, 0.8):
        tr += [(k0 + 0.00, (0.0, 0.00, 0.000, 25.0, 30.0)),
               (k0 + 0.18, (0.0, 0.08, 0.130, 60.0, 80.0)),
               (k0 + 0.34, (0.0, 0.22, 0.060, 10.0, 15.0)),
               (k0 + 0.44, (0.0, 0.24, 0.000, 4.0, 2.0)),
               (k0 + 0.66, (0.0, 0.02, 0.000, 10.0, 4.0))]
    return Choreo(
        name="paw", duration=dur, loop=True, keys=keys,
        plants0={"fl": (0.0, 0.0), "hl": (0.0, 0.0), "hr": (0.0, 0.0), "fr": (0.0, 0.0)},
        tracks={"fr": tr},
        events=[(0.0, "foot_up_fr"), (0.44, "foot_down_fr"), (0.80, "foot_up_fr"), (1.24, "foot_down_fr")],
        notes="Grattage de l'antérieur droit, 2 coups par boucle (~1,25 Hz) : lever, tendre vers l'avant, "
              "frapper puis racler le sol vers l'arrière (contact glissant VOULU, hors contrôle de patinage) ; "
              "tête basse, poids reporté à gauche et en arrière (gaits.md §4 [U]). " + A_NOTE)


# ----------------------------------------------------------------------------------------------
# Se coucher / couché / se relever / se rouler
# Pose « couché sternal » optimisée numériquement dans les limites du SPEC (scratch t_lieopt) : avec un carpe
# ≤ 150° [V : Adair 2016] et un coude ≤ 65°, un antérieur replié ne peut pas descendre le coude à moins de
# ~18 cm du sol : le poitrail repose sur les antérieurs repliés (~10 cm), l'arrière-main sur les postérieurs
# repliés, tronc incliné de 15° sur le côté gauche [A].
def fore_fold(side, carpus=150.0, k=1.0):
    """Antérieur replié sous le poitrail : avant-bras vers l'avant-bas, carpe en flexion maximale."""
    return {f"scapula_{side}": 5 * k, f"upperarm_{side}": -5 * k, f"forearm_{side}": 65 * k,
            f"front_cannon_{side}": -carpus * k, f"front_pastern_{side}": -60 * k, f"front_hoof_{side}": -30 * k}


def fore_reach(side, k=1.0):
    """Antérieur tendu vers l'avant (début du relever) : épaule en extension, carpe peu fléchi."""
    return {f"scapula_{side}": 12 * k, f"upperarm_{side}": 18 * k, f"forearm_{side}": 30 * k,
            f"front_cannon_{side}": -20 * k, f"front_pastern_{side}": -10 * k, f"front_hoof_{side}": 0}


def hind_fold(side, abd=0.0, k=1.0):
    """Postérieur replié. Couplage grasset↔jarret strict : le canon garde l'orientation du fémur ; il faut
    enrouler le bassin (flexion lombo-sacrée) et un jeu de couplage de 12° pour coucher le canon [I/A]."""
    return {f"thigh_{side}": (22 * k, 0.0, abd * k), f"gaskin_{side}": -90 * k, f"hock_slack_h{side}": 12 * k,
            f"hind_pastern_{side}": 10 * k, f"hind_hoof_{side}": -10 * k}


def lying_tail():
    vals = [-10, -6, -4, -2, 0, 0, 0, 0, 0, 0]
    return {n: (v, 0.0, 8.0 if i > 3 else 0.0) for i, (n, v) in enumerate(zip(TAIL, vals))}


LYING_BODY = dict(pitch=6.0, roll=-15.0, yaw=0.0, x=0.0, y=-0.02, z=-0.62)


def lying_pose(neck=-6.0, head=-6.0, lat=6.0):
    d = {}
    d.update(fore_fold("l"))
    d.update(fore_fold("r", carpus=148.0))
    d.update(hind_fold("l", abd=-8.0))
    d.update(hind_fold("r", abd=9.0))
    d.update(_neck(neck, lat))
    d["head"] = (head, 0.0, 2.0)
    d["hips"] = (10.0, 0.0, 0.0)        # flexion lombo-sacrée (bassin enroulé)
    d.update(lying_tail())
    return d


ALL_FK = lambda dur: [FKSpan(l, 0.0, dur) for l in ("fl", "fr", "hl", "hr")]


def lying():
    dur = 6.0
    keys = [
        _k(0.0, lying_pose(), snap=1.0, body=dict(LYING_BODY)),
        _k(1.5, lying_pose(-9, -8, 8), body=dict(LYING_BODY, roll=-15.5, pitch=5.8)),
        _k(3.0, lying_pose(-4, -4, 5), body=dict(LYING_BODY, roll=-14.6, pitch=6.2)),
        _k(4.5, lying_pose(-10, -10, 3), body=dict(LYING_BODY, roll=-15.2, pitch=5.9)),
        _k(3.6, {"tail_06": (0, 0, 24), "tail_08": (0, 0, 22)}),
        _k(4.1, {"tail_06": (0, 0, -4), "tail_08": (0, 0, -2)}),
    ]
    return Choreo(
        name="lying", duration=dur, loop=True, keys=keys, fk=ALL_FK(dur),
        notes="Couché en décubitus sternal (membres repliés, tronc incliné ~15° sur le côté gauche), petits "
              "mouvements d'encolure, un coup de queue ; respiration laissée au runtime. Contact au sol : le point "
              "le plus bas du mannequin est ramené à z = 0 ; la queue est posée au sol. Dans les limites du SPEC "
              "le poitrail reste ~10 cm au-dessus du sol, porté par les antérieurs repliés. " + A_NOTE)


def lie_down():
    dur = 3.0
    kneel_body = dict(STAND_BODY, pitch=-24.0, y=0.10, z=0.0, pivot=(-0.55, 1.00))
    keys = [
        _k(0.0, _neck(0, 0), {"head": 0, "hips": 0}, _tail(0, 0), snap=0.0, body=dict(STAND_BODY),
           carpus_fl=0.0, carpus_fr=0.0, hoofpitch_fl=0.0, hoofpitch_fr=0.0, fetpref_fl=0.0, fetpref_fr=0.0),
        _k(0.55, _neck(-36, 4), {"head": 22}, body=dict(STAND_BODY, pitch=-2.0, y=0.02, z=-0.03)),   # flairer le sol
        _k(0.90, _neck(-30, 2), {"head": 18}, carpus_fl=0.0, carpus_fr=0.0, hoofw_fl=1.0, hoofw_fr=1.0,
           fetpref_fl=0.0, fetpref_fr=0.0, body=dict(STAND_BODY, pitch=-3.0, y=0.03, z=-0.04)),
        _k(1.05, hoofw_fl=0.0, hoofw_fr=0.0),
        _k(1.25, carpus_fl=95.0, carpus_fr=90.0, fetpref_fl=-50.0, fetpref_fr=-50.0,
           body=dict(STAND_BODY, pitch=-9.0, y=0.06, z=-0.03, pivot=(-0.55, 1.00))),
        # agenouillement (IK) : pinces au sol (orientation du sabot libre : il bascule sur la pince), carpes
        # qui fléchissent, l'avant-main descend
        _k(1.50, _neck(-18, 2), {"head": 6}, carpus_fl=140.0, carpus_fr=138.0,
           fetpref_fl=-60.0, fetpref_fr=-60.0, body=dict(kneel_body)),
        _k(1.55, fore_fold("l"), fore_fold("r", carpus=148.0), snap=0.0),
        _k(1.85, snap=0.0, body=dict(kneel_body, pitch=-22.0, z=-0.04)),
        _k(2.05, snap=1.0),
        # l'arrière-main descend, roulis vers la gauche
        _k(2.45, hind_fold("l", abd=-8.0), hind_fold("r", abd=9.0), {"hips": 8.0},
           body=dict(LYING_BODY, pitch=2.0, roll=-10.0, z=-0.58)),
        _k(3.0, lying_pose(), snap=1.0, body=dict(LYING_BODY)),
    ]
    # antérieurs : plantés (IK) pendant l'agenouillement puis repliés (FK) ; postérieurs repliés à partir de 1,8 s
    fk = [FKSpan("fl", 1.50, dur, blend_in=0.3), FKSpan("fr", 1.52, dur, blend_in=0.3),
          FKSpan("hl", 1.80, dur, blend_in=0.55), FKSpan("hr", 1.85, dur, blend_in=0.55)]
    # rassembler les membres sous le corps avant de se coucher
    steps = [Step("fl", 0.20, 0.55, to=(0.0, -0.18), lift=0.05, carpus=35, flip=20),
             Step("fr", 0.35, 0.70, to=(0.0, -0.18), lift=0.05, carpus=35, flip=20),
             Step("hl", 0.45, 0.80, to=(0.0, 0.10), lift=0.04, flip=15),
             Step("hr", 0.60, 0.95, to=(0.0, 0.10), lift=0.04, flip=15)]
    keys += [_k(0.0, {k: v for k, v in fore_fold("l", k=0.0).items()}, {k: v for k, v in fore_fold("r", k=0.0).items()},
                {k: v for k, v in hind_fold("l", k=0.0).items()}, {k: v for k, v in hind_fold("r", k=0.0).items()})]
    return Choreo(
        name="lie_down", duration=dur, keys=keys, fk=fk, plants0=dict(SQUARE), steps=steps,
        events=[(0.20, "foot_up_fl"), (0.55, "foot_down_fl"), (0.35, "foot_up_fr"), (0.70, "foot_down_fr"),
                (0.45, "foot_up_hl"), (0.80, "foot_down_hl"), (0.60, "foot_up_hr"), (0.95, "foot_down_hr")],
        notes="Se coucher : rassembler les membres sous le corps, flairer le sol, fléchir les carpes pinces au sol "
              "et s'agenouiller (IK, sabots basculés sur la pince), replier les antérieurs, abaisser l'arrière-main "
              "puis se poser en décubitus sternal incliné à gauche (gaits.md §4 [U]). Finit dans la pose de "
              "`lying`. " + A_NOTE)


def get_up():
    dur = 2.5
    sit = dict(STAND_BODY, pitch=22.0, y=0.05, z=-0.65, roll=-3.0, pivot=(-0.55, 0.45))
    keys = [
        _k(0.0, lying_pose(), snap=1.0, body=dict(LYING_BODY)),
        # élan de l'encolure, roulis ramené, avant-main qui se soulève sur les antérieurs tendus vers l'avant
        _k(0.40, _neck(16, 0), {"head": -4, "hips": 10}, body=dict(LYING_BODY, roll=-6.0, pitch=12.0, z=-0.58)),
        _k(0.85, _neck(8, 0), {"head": -2}, snap=1.0, body=dict(sit)),
        _k(1.05, snap=0.0),
        # poussée des postérieurs : l'arrière-main monte
        _k(1.45, _neck(2, 0), {"head": 0, "hips": 2}, hind_fold("l", k=0.0), hind_fold("r", k=0.0),
           body=dict(STAND_BODY, pitch=3.0, y=0.03, z=-0.06)),
        _k(2.5, _neck(0, 0), {"head": 0, "hips": 0}, _tail(0, 0), body=dict(STAND_BODY)),
    ]
    fk = [FKSpan("fl", 0.0, 0.15, blend_out=0.45), FKSpan("fr", 0.0, 0.30, blend_out=0.45),
          FKSpan("hl", 0.0, 0.95, blend_out=0.50), FKSpan("hr", 0.0, 1.0, blend_out=0.50)]
    plants = {"fl": (0.0, 0.32), "fr": (0.0, 0.26), "hl": (0.0, 0.05), "hr": (0.0, 0.03)}
    steps = [Step("fl", 1.50, 1.95, to=(0.0, 0.0), lift=0.06, carpus=40, flip=25),
             Step("fr", 1.80, 2.25, to=(0.0, 0.0), lift=0.06, carpus=40, flip=25),
             Step("hl", 1.60, 2.00, to=(0.0, 0.0), lift=0.04, flip=15)]
    return Choreo(
        name="get_up", duration=dur, keys=keys, fk=fk, plants0=plants, steps=steps,
        events=[(0.60, "foot_down_fl"), (0.75, "foot_down_fr"), (1.45, "foot_down_hl"), (1.50, "foot_down_hr")],
        notes="Se relever depuis `lying` : antérieurs dépliés et posés vers l'avant l'un après l'autre, élan de "
              "l'encolure, position « assise », puis poussée des postérieurs (gaits.md §4 [U]) ; finit debout carré "
              "après le réajustement des antérieurs et d'un postérieur. " + A_NOTE)


def roll():
    dur = 4.5
    lp = lying_pose()

    def legs_up(k=1.0, wig=0.0):
        d = {}
        for sd in ("l", "r"):
            d.update({f"upperarm_{sd}": -25 * k, f"forearm_{sd}": (50 + wig) * k, f"front_cannon_{sd}": -95 * k,
                      f"front_pastern_{sd}": -40 * k, f"front_hoof_{sd}": -20 * k, f"scapula_{sd}": 0.0,
                      f"thigh_{sd}": (30 * k + wig * 0.3, 0.0, 0.0), f"gaskin_{sd}": -60 * k,
                      f"hock_slack_h{sd}": 0.0, f"hind_pastern_{sd}": -40 * k, f"hind_hoof_{sd}": -20 * k})
        return d
    keys = [
        _k(0.0, lp, snap=1.0, body=dict(LYING_BODY)),
        _k(0.7, legs_up(0.6), _neck(-10, 16), {"head": (-8, 0, 6), "hips": 4},
           body=dict(LYING_BODY, roll=-80.0, pitch=1.0, z=-0.7)),
        # sur le dos : encolure fléchie (vers le ventre) pour garder la tête au sol, membres repliés en l'air
        _k(1.3, legs_up(1.0), _neck(-46, 20, 10), {"head": (-12, -14, 8), "hips": -4},
           body=dict(LYING_BODY, roll=-158.0, pitch=0.0, z=-0.7)),
        _k(1.65, legs_up(1.0, 15), body=dict(LYING_BODY, roll=-146.0, pitch=0.0, yaw=3.0, z=-0.7)),
        _k(2.0, legs_up(1.0, -10), body=dict(LYING_BODY, roll=-166.0, pitch=0.0, yaw=-3.0, z=-0.7)),
        _k(2.35, legs_up(1.0, 12), body=dict(LYING_BODY, roll=-150.0, pitch=0.0, yaw=2.0, z=-0.7)),
        _k(2.7, legs_up(0.9), _neck(-36, 18, 6), {"head": (-10, -8, 6)}, body=dict(LYING_BODY, roll=-122.0, z=-0.7)),
        # retour sur le flanc : membres déjà repliés avant de revenir en sternal
        _k(3.25, lp, _neck(-14, 12), {"head": (-8, 0, 4), "hips": 8},
           body=dict(LYING_BODY, roll=-78.0, pitch=2.0, z=-0.68)),
        _k(4.5, lp, body=dict(LYING_BODY)),
    ]
    return Choreo(
        name="roll", duration=dur, keys=keys, fk=ALL_FK(dur),
        notes="Se rouler depuis `lying` : bascule sur le flanc gauche, sur le dos membres repliés, frottements "
              "(oscillations de roulis ±10°), retour sur le flanc puis en décubitus sternal (pose de `lying`). "
              "Le tronc reste au contact du sol (contrainte de sol sur le mannequin) ; gaits.md §4 [U]. " + A_NOTE)


def body_shake():
    dur = 1.5
    keys = [_k(0.0, _neck(0, 0), {"head": 0, "hips": 0}, _tail(0, 0), body=dict(STAND_BODY)),
            _k(0.12, _neck(-8, 0), {"head": -4}, body=dict(STAND_BODY, z=-0.03))]
    # onde : tête/encolure (torsion) -> tronc (roulis) -> bassin/queue ; ~4,5 Hz [A]
    for t, a in _osc(0.12, 0.62, 0.22, 22.0, decay=0.6):
        keys.append(_k(t, {n: (-8 * w * 4, a * w, a * w * 0.3) for n, w in zip(NECK, (0.05, 0.1, 0.15, 0.2, 0.22, 0.28))},
                       {"head": (-4, a * 0.6, a * 0.2), "ear_l": (0, -a * 0.6, 0), "ear_r": (0, -a * 0.6, 0)},
                       {m: (0, 0, -a * 0.6) for m in MANE}))
    for t, a in _osc(0.32, 1.02, 0.22, 7.5, decay=0.7):
        keys.append(_k(t, body=dict(STAND_BODY, roll=a, z=-0.03 + 0.004 * (a != 0))))
        keys.append(_k(t + 0.03, {"spine_02": (0, a * 0.45, 0), "spine_03": (0, a * 0.4, 0), "belly": (a * 0.6, 0, 0)}))
    for t, a in _osc(0.55, 1.25, 0.22, 6.0, decay=0.7):
        keys.append(_k(t, {"hips": (0, a, 0)}, _tail(4, a * 4)))
    keys += [_k(1.12, body=dict(STAND_BODY, z=-0.02)),
             _k(1.5, _neck(0, 0), {"head": 0, "hips": 0, "spine_02": 0, "spine_03": 0, "belly": 0},
                _tail(0, 0), {m: 0 for m in MANE}, {"ear_l": 0, "ear_r": 0}, body=dict(STAND_BODY))]
    return Choreo(
        name="body_shake", duration=dur, keys=keys, plants0={"fl": (0.01, 0.0), "fr": (0.01, 0.0),
                                                             "hl": (0.0, 0.0), "hr": (0.0, 0.0)},
        events=[(1.3, "snort")],
        notes="Ébrouement : onde de torsion de la tête et de l'encolure vers le tronc (roulis rapide ±7,5°) puis "
              "le bassin et la queue, sabots plantés, posture légèrement abaissée (gaits.md §4 [U]) ; évènement "
              "`snort` à la fin (souffle) [A]. " + A_NOTE)


def rear():
    dur = 2.6
    up = dict(STAND_BODY, pitch=38.0, y=-0.10, z=-0.10, pivot=(-0.55, 1.0))
    fold = {}
    for sd, ph in (("l", 0.0), ("r", 1.0)):
        fold[sd] = {f"scapula_{sd}": -6, f"upperarm_{sd}": -32, f"forearm_{sd}": 58, f"front_cannon_{sd}": -105,
                    f"front_pastern_{sd}": -35, f"front_hoof_{sd}": -15}
    keys = [
        _k(0.0, _neck(0, 0), {"head": 0, "hips": 0}, _tail(0, 0), body=dict(STAND_BODY)),
        # préparation : poids vers l'arrière, postérieurs fléchis, tête haute
        _k(0.5, _neck(10, 0), {"head": 4, "hips": -4}, body=dict(STAND_BODY, pitch=3.0, y=-0.07, z=-0.07)),
        # bassin en extension lombo-sacrée (−) : garde le fémur sous le corps malgré le tronc à ~40° (hanche ≥ −25°)
        _k(1.05, _neck(-14, 0), {"head": -12, "hips": -14}, fold["l"], fold["r"], _tail(10, 0), body=dict(up)),
        _k(1.3, {"front_cannon_l": -125, "forearm_l": 62, "front_cannon_r": -95}, body=dict(up, pitch=40.0)),
        _k(1.55, {"front_cannon_l": -95, "front_cannon_r": -125, "forearm_r": 62}, body=dict(up, pitch=39.0)),
        _k(1.75, _neck(-10, 0), {"head": -8}),
        # descente : antérieurs tendus vers le sol
        _k(2.05, _neck(4, 0), {"head": 2, "hips": 4}, _tail(2, 0),  # antérieurs tendus, encore en l'air
           {f"upperarm_{s}": 10 for s in "lr"}, {f"forearm_{s}": 8 for s in "lr"},
           {f"front_cannon_{s}": -6 for s in "lr"}, {f"front_pastern_{s}": -10 for s in "lr"},
           {f"front_hoof_{s}": 0 for s in "lr"}, {f"scapula_{s}": 6 for s in "lr"},
           body=dict(STAND_BODY, pitch=9.0, y=-0.04, z=-0.04, pivot=(-0.55, 1.0))),
        _k(2.6, _neck(0, 0), {"head": 0, "hips": 0}, _tail(0, 0), body=dict(STAND_BODY)),
    ]
    fk = [FKSpan("fl", 0.55, 2.0, blend_in=0.30, blend_out=0.18), FKSpan("fr", 0.60, 2.1, blend_in=0.30, blend_out=0.2)]
    for sd in "lr":
        keys.append(_k(0.0, {f"scapula_{sd}": 0, f"upperarm_{sd}": 0, f"forearm_{sd}": 0, f"front_cannon_{sd}": 0,
                             f"front_pastern_{sd}": 0, f"front_hoof_{sd}": 0}))
    return Choreo(
        name="rear", duration=dur, keys=keys, fk=fk,
        plants0={"fl": (0.0, 0.0), "fr": (0.0, 0.0), "hl": (0.0, 0.06), "hr": (0.0, 0.06)},
        fetlock_pref={"hl": 8.0, "hr": 8.0},
        events=[(0.55, "foot_up_fl"), (0.60, "foot_up_fr"), (2.18, "foot_down_fl"), (2.30, "foot_down_fr")],
        notes="Cabrer : report du poids vers l'arrière, postérieurs fléchis et plantés, avant-main levée à ~40° "
              "autour des hanches, antérieurs repliés qui battent l'air, encolure arrondie ; descente, réception "
              "sur l'antérieur gauche puis le droit (gaits.md §4 [U]). " + A_NOTE)


ALL = {
    "idle": idle,
    "idle_rest_hind": idle_rest_hind,
    "graze_down": graze_down,
    "graze_loop": graze_loop,
    "graze_up": graze_up,
    "head_shake": head_shake,
    "neigh": neigh,
    "paw": paw,
    "lying": lying,
    "lie_down": lie_down,
    "get_up": get_up,
    "roll": roll,
    "body_shake": body_shake,
    "rear": rear,
}


def make(sk: Skeleton, name: str, verbose=False):
    return build_choreo(sk, ALL[name](), verbose=verbose)
