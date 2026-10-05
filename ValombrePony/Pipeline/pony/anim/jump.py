"""Saut d'obstacle (60–80 cm) : appel, vol (bascule), réception — chorégraphie « à l'œil » [A].

Aucune donnée vérifiée (gaits.md §3 : séquence « communément décrite » [U], temps balistique [D]).
Partage des rôles avec le runtime (SPEC §7) : le RUNTIME gère l'arc balistique (altitude de l'entité) ;
les clips portent la POSE :
- `jump_takeoff` (non bouclé) : antérieurs qui freinent (non meneur puis meneur), avant-main qui se lève,
  postérieurs posés presque appariés sous le corps qui poussent ; évènement `takeoff` au décollement du
  dernier postérieur (fin de contact) : l'arc balistique doit commencer à cet instant ;
- `jump_air` (boucle « de tenue ») : membres repliés, encolure tendue vers l'avant et le bas (bascule).
  La tenue est quasi statique ; le tangage de l'entité le long de l'arc (nez en haut → nez en bas, ~±20°)
  est laissé au runtime, ou obtenu par les fondus d'entrée/sortie (fin de `jump_takeoff` à +22°, début
  de `jump_land` à −12°) ;
- `jump_land` (non bouclé) : poser de l'antérieur non meneur puis du meneur (évènement `landing` à t = 0 :
  l'arc doit se terminer, entité au sol, à cet instant), postérieurs posés sous le corps, départ au galop.
Vitesse racine : 4,0 m/s pendant les trois clips (approche ralentie par rapport au galop de travail à
4,8 m/s [A]) — les sabots plantés sont fixes en monde à cette vitesse.
Pied de départ et de réception : gauche (antérieur gauche meneur) [A].
"""
from __future__ import annotations

from .behaviours import A_NOTE, STAND_BODY, _k, _neck, _tail
from .poses import Choreo, FKSpan, Step, build_choreo
from .skeleton import Skeleton

V = 4.0


def _fore_tuck(sd, k=1.0):
    return {f"scapula_{sd}": -8 * k, f"upperarm_{sd}": -35 * k, f"forearm_{sd}": 64 * k,
            f"front_cannon_{sd}": -140 * k, f"front_pastern_{sd}": -55 * k, f"front_hoof_{sd}": -30 * k}


def _fore_reach(sd, k=1.0):
    """Antérieur tendu vers l'avant et le bas (approche de la réception)."""
    return {f"scapula_{sd}": 10 * k, f"upperarm_{sd}": 15 * k, f"forearm_{sd}": 4 * k,
            f"front_cannon_{sd}": -2 * k, f"front_pastern_{sd}": -15 * k, f"front_hoof_{sd}": -5 * k}


def _hind_trail(sd, k=1.0):
    """Postérieur qui traîne derrière après la poussée (hanche en extension, jarret fléchi)."""
    return {f"thigh_{sd}": -22 * k, f"gaskin_{sd}": -35 * k, f"hind_pastern_{sd}": -45 * k,
            f"hind_hoof_{sd}": -25 * k}


def _hind_tuck(sd, k=1.0):
    """Postérieur replié sous le corps (au-dessus de la barre)."""
    return {f"thigh_{sd}": 35 * k, f"gaskin_{sd}": -70 * k, f"hind_pastern_{sd}": -55 * k,
            f"hind_hoof_{sd}": -25 * k}


def _hind_swing(sd, k=1.0):
    """Postérieur ramené vers l'avant en fin d'envol (avant le poser)."""
    return {f"thigh_{sd}": 22 * k, f"gaskin_{sd}": -30 * k, f"hind_pastern_{sd}": -25 * k,
            f"hind_hoof_{sd}": -10 * k}


def _merge(*ds):
    out = {}
    for d in ds:
        out.update(d)
    return out


def jump_takeoff():
    dur = 0.5
    keys = [
        _k(0.0, _neck(-8, 0), {"head": 4, "hips": 0}, _tail(14, 0), _hind_swing("l"), _hind_swing("r"), _fore_reach("l"),
           body=dict(STAND_BODY, pitch=-3.0, z=-0.04)),
        _k(0.09, _neck(-10, 0), {"head": 6}, body=dict(STAND_BODY, pitch=-4.0, z=-0.07, y=0.02)),     # freinage
        _k(0.13, _fore_tuck("r", 0.0), _fore_tuck("l", 0.0)),
        _k(0.24, _neck(8, 0), {"head": -4, "hips": 6}, _fore_tuck("r", 0.8), _fore_tuck("l", 0.7),
           body=dict(STAND_BODY, pitch=10.0, z=-0.03, pivot=(-0.55, 1.0))),
        _k(0.35, _neck(10, 0), {"head": -6, "hips": -4}, _fore_tuck("r"), _fore_tuck("l"), _tail(18, 0),
           body=dict(STAND_BODY, pitch=20.0, z=0.03, pivot=(-0.55, 1.0))),
        _k(0.5, _neck(0, 0), {"head": -2, "hips": -6}, _hind_trail("l"), _hind_trail("r"),
           body=dict(STAND_BODY, pitch=22.0, z=0.06, pivot=(-0.55, 1.0))),
        # bascule en pince en fin d'appui (talons qui se lèvent autour de la pince)
        _k(0.0, hoofpitch_fr=0.0, hoofpitch_fl=0.0, hoofpitch_hl=0.0, hoofpitch_hr=0.0),
        _k(0.07, hoofpitch_fr=0.0), _k(0.12, hoofpitch_fr=40.0),
        _k(0.10, hoofpitch_fl=0.0), _k(0.16, hoofpitch_fl=40.0),
        _k(0.25, hoofpitch_hl=0.0, hoofpitch_hr=0.0), _k(0.34, hoofpitch_hl=45.0), _k(0.35, hoofpitch_hr=45.0),
    ]
    fk = [FKSpan("hl", 0.0, 0.10, blend_out=1e-3), FKSpan("hr", 0.0, 0.11, blend_out=1e-3),
          FKSpan("fl", 0.0, 0.02, blend_out=1e-3),
          FKSpan("fr", 0.12, dur, blend_in=0.08), FKSpan("fl", 0.16, dur, blend_in=0.08),
          FKSpan("hl", 0.34, dur, blend_in=0.10), FKSpan("hr", 0.35, dur, blend_in=0.10)]
    steps = [Step("fl", 0.02, 0.05, to=(0.0, 0.34), lift=0.0, flip=0, from_fk=True),   # meneur posé à 0,05 s
             Step("hl", 0.10, 0.21, to=(0.0, 0.22), lift=0.03, flip=10, from_fk=True),
             Step("hr", 0.11, 0.22, to=(0.0, 0.18), lift=0.03, flip=10, from_fk=True)]
    return Choreo(
        name="jump_takeoff", duration=dur, keys=keys, fk=fk, steps=steps, root_velocity=V,
        plants0={"fr": (0.0, 0.26), "fl": (0.0, 0.48), "hl": (0.0, 0.0), "hr": (0.0, 0.0)},
        events=[(0.0, "foot_down_fr"), (0.05, "foot_down_fl"), (0.12, "foot_up_fr"), (0.16, "foot_up_fl"),
                (0.21, "foot_down_hl"), (0.22, "foot_down_hr"), (0.34, "foot_up_hl"), (0.35, "foot_up_hr"),
                (0.35, "takeoff")],
        extra_meta={"jump": {"phase": "takeoff", "bodyPitchEndDeg": 22.0,
                             "note": "arc balistique géré par le runtime à partir de l'évènement `takeoff`"}},
        notes="Appel : antérieurs (non meneur droit puis meneur gauche) qui freinent, avant-main qui se lève (+22°), "
              "postérieurs posés presque appariés sous le corps puis poussée ; `takeoff` = décollement du dernier "
              "postérieur (0,35 s). L'altitude n'est PAS dans le clip (arc balistique au runtime). Vitesse 4,0 m/s. "
              "gaits.md §3 [U]. " + A_NOTE)


AIR = _merge(_fore_tuck("l"), _fore_tuck("r"), _hind_tuck("l", 0.8), _hind_tuck("r", 0.8))


def jump_air():
    dur = 0.4
    keys = [
        _k(0.0, AIR, _neck(-18, 0), {"head": 8, "hips": 6, "spine_01": -3, "spine_02": -2}, _tail(10, 0),
           body=dict(STAND_BODY, pitch=0.0, z=0.05)),
        _k(0.2, _neck(-20, 0), {"head": 9}, _tail(12, 3), body=dict(STAND_BODY, pitch=0.0, z=0.05)),
    ]
    return Choreo(
        name="jump_air", duration=dur, loop=True, keys=keys, root_velocity=V, ground_fix=False,
        fk=[FKSpan(l, 0.0, dur) for l in ("fl", "fr", "hl", "hr")], drape_tail=False,
        events=[(0.0, "apex")],
        extra_meta={"jump": {"phase": "air", "hold": True,
                             "note": "tenue en boucle pendant l'arc ; tangage de l'entité le long de l'arc au runtime"}},
        notes="Vol / bascule : antérieurs repliés serrés (carpes ~140°), postérieurs repliés, encolure tendue vers "
              "l'avant et le bas, dos arrondi ; tenue quasi statique en boucle (le runtime joue ce clip pendant "
              "l'arc balistique et peut incliner l'entité). gaits.md §3 [U]. " + A_NOTE)


def jump_land():
    dur = 0.6
    keys = [
        _k(0.0, _neck(-6, 0), {"head": 4, "hips": 4}, _fore_reach("l"), _hind_tuck("l", 0.6), _hind_tuck("r", 0.6),
           _tail(10, 0), body=dict(STAND_BODY, pitch=-12.0, z=-0.02, pivot=(0.45, 1.0))),
        _k(0.10, _neck(10, 0), {"head": -4}, body=dict(STAND_BODY, pitch=-8.0, z=-0.06, pivot=(0.45, 1.0))),
        _k(0.22, _neck(12, 0), {"head": -6, "hips": 6}, _hind_swing("l"), _hind_swing("r"),
           body=dict(STAND_BODY, pitch=-2.0, z=-0.06)),
        _k(0.40, _neck(2, 0), {"head": 0, "hips": 2}, body=dict(STAND_BODY, pitch=2.0, z=-0.04)),
        _k(0.6, _neck(0, 0), {"head": 0, "hips": 0}, _tail(14, 0), body=dict(STAND_BODY, pitch=0.0, z=-0.04)),
    ]
    fk = [FKSpan("fl", 0.0, 0.0, blend_out=1e-3), FKSpan("hl", 0.0, 0.20, blend_out=1e-3),
          FKSpan("hr", 0.0, 0.23, blend_out=1e-3)]
    # reprise du galop : appuis courts (≤ 0,15 s à 4 m/s), pas suivants (la fin du clip est en l'air pour
    # les postérieurs et l'antérieur droit)
    steps = [Step("fl", 0.0, 0.07, to=(0.0, 0.36), lift=0.0, flip=0, from_fk=True),
             Step("fr", 0.13, 0.40, to=(0.0, 0.30), lift=0.10, carpus=70, flip=60),
             Step("fl", 0.20, 0.47, to=(0.0, 0.30), lift=0.10, carpus=70, flip=60),
             Step("fr", 0.53, 0.80, to=(0.0, 0.30), lift=0.10, carpus=70, flip=60),
             Step("hl", 0.20, 0.30, to=(0.0, 0.18), lift=0.02, flip=5, from_fk=True),
             Step("hr", 0.23, 0.33, to=(0.0, 0.12), lift=0.02, flip=5, from_fk=True),
             Step("hl", 0.42, 0.70, to=(0.0, 0.20), lift=0.09, flip=40),
             Step("hr", 0.46, 0.74, to=(0.0, 0.16), lift=0.09, flip=40)]
    return Choreo(
        name="jump_land", duration=dur, keys=keys, fk=fk, steps=steps, root_velocity=V,
        plants0={"fr": (0.0, 0.30), "fl": (0.0, 0.36), "hl": (0.0, 0.0), "hr": (0.0, 0.0)},
        events=[(0.0, "landing"), (0.0, "foot_down_fr"), (0.07, "foot_down_fl"), (0.13, "foot_up_fr"),
                (0.20, "foot_up_fl"), (0.30, "foot_down_hl"), (0.33, "foot_down_hr"), (0.40, "foot_down_fr"),
                (0.42, "foot_up_hl"), (0.46, "foot_up_hr"), (0.47, "foot_down_fl"), (0.53, "foot_up_fr")],
        extra_meta={"jump": {"phase": "land", "bodyPitchStartDeg": -12.0,
                             "note": "l'arc balistique doit amener l'entité au sol à t = 0 (évènement `landing`)"}},
        notes="Réception : antérieur non meneur (droit) puis meneur (gauche), avant-main qui se relève, postérieurs "
              "posés sous le corps, reprise du galop à gauche ; `landing` à t = 0 (premier contact). Vitesse 4,0 m/s. "
              "gaits.md §3 [U]. " + A_NOTE)


ALL = {"jump_takeoff": jump_takeoff, "jump_air": jump_air, "jump_land": jump_land}


def make(sk: Skeleton, name: str, verbose=False):
    return build_choreo(sk, ALL[name](), verbose=verbose)
