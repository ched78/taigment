"""Allures : horloge de phase, trajectoires de sabots, dynamique du tronc, encolure, queue, IK des membres.

Principe (Docs/research/gaits.md §5.1, [D]) :
- horloge commune φ = t/T ; chaque membre a une phase de poser `td` et un facteur d'appui `duty` ;
- mouvement racine (entité) : vitesse constante v (repère poney) + lacet ω autour d'un pivot ;
  M(t) = [Rz(ωt) | p(t)] ; un sabot en appui est FIXE en monde : sa pose dans le repère du clip vaut
  M(t)⁻¹·P_monde (en ligne droite : il recule à exactement v m/s) ;
- pose de chaque appui : la pose « neutre » du sabot (repos + décalages) placée au milieu de l'appui
  (P_monde = M(t_milieu)·P_neutre) ⇒ appui centré, boucle exacte (M(t+T) = M(T)·M(t)) ;
- fin d'appui : bascule en pince (rotation autour de la pince, talons qui se lèvent) ;
- envol : pince en « minimum jerk » en monde (vitesse nulle au décollement et au poser), arc de levée,
  orientation du sabot guidée (poids faible), sabot à plat au poser ;
- tronc : modèle de forces d'appui en demi-sinus (Σ impulsions = poids) → rebond vertical, tangage,
  roulis, avance/recul du tronc par double intégration périodique (FFT) [D], puis gains par allure pour
  rester dans les amplitudes par défaut de gaits.md §2.3 [U] ;
- encolure/tête, bassin, colonne, queue : oscillations phasées sur les appuis + réponse d'oscillateurs
  amortis (queue) calculée en régime périodique (FFT) ⇒ boucle parfaite.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import mathutil as mu
from .clip_io import FPS, Clip
from .limb_ik import LimbFrameInput, LimbSolver, write_chain
from .skeleton import LIMB_JOINTS, LIMBS, NECK, TAIL, Skeleton

G = 9.81
D = mu.DEG


# ==============================================================================================
# Paramètres
# ==============================================================================================
@dataclass
class LimbGait:
    td: float                    # phase du poser (fraction de foulée, 0 = poser du postérieur gauche)
    duty: float                  # facteur d'appui
    dx: float = 0.0              # décalage latéral de la pince neutre (m, + = vers l'extérieur)
    dy: float = 0.0              # décalage avant/arrière de la pince au milieu de l'appui (m)
    lift: float = 0.08           # levée de la pince en envol (m)
    lift_peak: float = 0.45      # position du maximum de levée dans l'envol (0..1)
    arc_fwd: float = 0.0         # renflement vers l'avant en envol (m) (croisement en virage)
    arc_lat: float = 0.0         # renflement latéral en envol (m, + = extérieur)
    carpus: float = 60.0         # flexion max du carpe en envol (°) [antérieurs]
    carpus_peak: float = 0.40
    fet_td: float = -12.0        # préférence boulet au poser (° delta repos ; + = plus d'hyperextension)
    fet_mid: float = 2.0         # au pic de charge
    fet_lo: float = -22.0        # au décollement
    fet_swing: float = -60.0     # flexion max en envol
    coffin_swing: float = -25.0  # flexion du doigt en envol
    bo_start: float = 0.72       # début de la bascule (fraction de l'appui)
    bo_angle: float = 45.0       # angle des talons au décollement (°)
    flip: float = 80.0           # guide : rotation max du sabot en envol (°, sole vers l'arrière)
    flip_peak: float = 0.35
    w_fetlock: float = 1.0
    sw_a: float = 2.0            # forme du début d'envol (a < 2 : départ plus vif après le décollement)
    sw_b: float = 2.0            # forme de la fin d'envol (CDF bêta(2, b) ; b = 2 ⇔ smoothstep ; b < 2 :
                                 # freinage plus tardif ⇒ moins de « rétraction » avant le poser) [I]
    w_rot_on: float = 0.55       # début du retour à plat du sabot en envol (fraction d'envol)


@dataclass
class GaitSpec:
    name: str
    frames: int                  # images du clip (durée = frames/30)
    speed: float                 # m/s vers l'avant (+Y Blender) ; négatif = recul
    limbs: dict
    strides: int = 1             # foulées contenues dans le clip (période de foulée = durée/strides)
    yaw_rate: float = 0.0        # rad/s (+ = gauche)
    pivot: tuple = (0.0, 0.0)    # pivot (x, y) Blender du lacet, repère poney
    use_twist: bool = True
    body_dz: float = -0.025      # hauteur moyenne du tronc vs pose de liaison (m)
    # amplitudes cibles (demi-crête à crête) des signaux du modèle de forces : la FORME et la PHASE viennent
    # du modèle [D], l'amplitude est remise à l'échelle sur ces valeurs par défaut [U] (gaits.md §2.3)
    bob_amp: float = 0.012       # m
    pitch_amp: float = 0.8       # °
    roll_amp: float = 0.8        # °
    surge_amp: float = 0.006     # m
    sway_amp: float = 0.005      # m
    body_pitch0: float = 0.0     # tangage moyen (°, + = nez en haut)
    hips_roll: float = 0.0       # roulis du bassin (°) piloté par la charge des postérieurs
    hips_yaw: float = 0.0        # lacet du bassin (°) piloté par la protraction des postérieurs
    ls_flex: float = 0.0         # flexion lombo-sacrée (°) liée à la protraction des postérieurs
    ls_flex0: float = 0.0
    spine_lat: float = 0.0       # incurvation latérale (°) compensant le lacet du bassin
    spine_flex: float = 0.0      # flexion dorso-lombaire liée à la protraction des postérieurs (°)
    neck_base: float = 0.0       # port de l'encolure (°, − = plus bas)
    neck_amp: float = 0.0        # hochement (°)
    neck_cycles: int = 2         # oscillations par foulée
    neck_phase: float = 0.0      # phase (foulée) du point bas de la tête
    neck_lag: float = 0.04       # retard de la tête sur l'encolure (fraction de foulée)
    head_base: float = 0.0
    head_comp: float = 0.4       # compensation du tangage de la tête (0 = rigide, 1 = horizon stable)
    neck_ext: float = 0.0        # extension de l'encolure (allonger : base plus basse, nuque ouverte)
    tail_lift: float = 0.0       # port de queue (°) à la base
    tail_gain: float = 1.0
    tail_swing: float = 0.0      # balancement latéral (°) avec le lacet du bassin
    turn_bend: float = 0.0       # incurvation vers l'intérieur du virage (°, total colonne+encolure)
    breathe_locked: bool = False # respiration couplée 1:1 à la foulée (galop) [U]
    breathe_phase: float = 0.0
    fore_share: float = 0.575    # part du poids sur les antérieurs [NV]
    k_scap: float = 0.5          # couplage omoplate/protraction [A]
    notes: str = ""
    sources: str = ""


def _limbs(fl, fr, hl, hr):
    return {"fl": fl, "fr": fr, "hl": hl, "hr": hr}


# ----------------------------------------------------------------------------------------------
# Jeux de paramètres (séquences, décalages, facteurs d'appui : gaits.md §1 et §6 ; le reste [A/U])
# ----------------------------------------------------------------------------------------------
def walk_spec():
    # Pas : 4 temps PG→AG→PD→AD, retard latéral 0,22, appui ≈ 0,62 [R : Renders & Vincelette 2023,
    # Clayton & Hobbs 2019, Animal Research 2006] ; v = 1,4 m/s, T ≈ 1,05 s (SPEC §7) ⇒ SL = v·T.
    fore = dict(duty=0.62, lift=0.075, lift_peak=0.36, carpus=58.0, carpus_peak=0.42, fet_td=-14.0,
                fet_mid=1.0, fet_lo=-22.0, fet_swing=-58.0, coffin_swing=-22.0, bo_start=0.70,
                bo_angle=48.0, flip=70.0, flip_peak=0.32, dy=-0.095)
    hind = dict(duty=0.63, lift=0.06, lift_peak=0.45, fet_td=-12.0, fet_mid=2.0, fet_lo=-24.0,
                fet_swing=-50.0, coffin_swing=-20.0, bo_start=0.70, bo_angle=45.0, flip=55.0,
                flip_peak=0.38, dy=-0.08)
    return GaitSpec(
        name="walk", frames=32, speed=1.4,
        limbs=_limbs(LimbGait(td=0.22, **fore), LimbGait(td=0.72, **fore),
                     LimbGait(td=0.0, **hind), LimbGait(td=0.50, **hind)),
        body_dz=-0.055, bob_amp=0.012, pitch_amp=0.8, roll_amp=1.0, surge_amp=0.006, sway_amp=0.008,
        hips_roll=3.5, hips_yaw=3.0, ls_flex=2.0, spine_lat=1.5, spine_flex=1.0,
        neck_base=-4.0, neck_amp=3.5, neck_cycles=2, neck_phase=0.22 + 0.62 * 0.30, head_comp=0.3,
        tail_lift=0.0, tail_gain=1.0, tail_swing=3.0,
        notes="Pas 4 temps PG→AG→PD→AD ; retard latéral 0,22 ; appui 0,62/0,63 ; pas de suspension [R]. "
              "Rebond du tronc issu du modèle de forces (2 cycles/foulée) [D] ; hochement de tête 2×/foulée, "
              "roulis/lacet du bassin, port de queue : amplitudes par défaut [U].",
        sources="gaits.md §1.2, §2.3, §6")


def trot_spec():
    # Trot : diagonaux, retard 0,50 (0,44–0,56), appui < 0,5 avec suspension [R] ; appui 0,40 (valeur
    # par défaut « travail » [U]) ; v = 3,0 m/s, T ≈ 0,66 s (table poney [D]).
    fore = dict(duty=0.40, lift=0.13, lift_peak=0.38, carpus=78.0, carpus_peak=0.40, fet_td=-12.0,
                fet_mid=9.0, fet_lo=-24.0, fet_swing=-70.0, coffin_swing=-30.0, bo_start=0.66,
                bo_angle=50.0, flip=95.0, flip_peak=0.33, dy=-0.10)
    hind = dict(duty=0.40, lift=0.10, lift_peak=0.45, fet_td=-10.0, fet_mid=9.0, fet_lo=-24.0,
                fet_swing=-62.0, coffin_swing=-25.0, bo_start=0.66, bo_angle=45.0, flip=70.0,
                flip_peak=0.38, dy=-0.10)
    return GaitSpec(
        name="trot", frames=20, speed=3.0,
        limbs=_limbs(LimbGait(td=0.51, **fore), LimbGait(td=0.01, **fore),
                     LimbGait(td=0.0, **hind), LimbGait(td=0.50, **hind)),
        body_dz=-0.045, bob_amp=0.030, pitch_amp=0.8, roll_amp=0.6, surge_amp=0.008, sway_amp=0.004,
        hips_roll=1.5, hips_yaw=1.0, ls_flex=1.5, spine_lat=0.5, spine_flex=0.5,
        neck_base=0.0, neck_amp=1.2, neck_cycles=2, neck_phase=0.21, head_comp=0.6,
        tail_lift=12.0, tail_gain=1.0,
        notes="Trot diagonal 2 temps : PG+AD puis PD+AG, retard 0,50 (+0,01 : postérieur posé juste avant "
              "l'antérieur [V*]), appui 0,40 ⇒ 2 suspensions [R/U]. Tronc et tête : 2 oscillations par "
              "foulée, point bas à mi-appui [U] ; tangage de tête stabilisé ; queue portée [U].",
        sources="gaits.md §1.3, §1.9, §2.3, §6")


def canter_spec(lead="left"):
    # Galop de travail (canter), 3 temps + suspension [R]. Pied droit : PG / PD+AG / AD (0 / 0,25 / 0,5) ;
    # postérieur meneur posé 0,01 avant l'antérieur non meneur (dissociation diagonale) [D/V*].
    # Le pied gauche est le miroir ; la phase 0 reste le poser du postérieur GAUCHE (SPEC §7).
    # Appui 0,33–0,34 (bas de la plage 0,30–0,38 [D] : appui ≈ 0,18 s = 0,20–0,21 s cheval [V*] × √s)
    # — au-delà, la course d'appui (DF·v·T ≈ 1 m) dépasse la portée du membre dans les limites du SPEC ;
    # antérieur non meneur plus long que le meneur [V] ; T ≈ 0,57 s [D] ; antérieur meneur posé à 0,52
    # (au lieu de 0,50) pour garder une suspension ≤ 15 % [V : 1–15 %].
    trail_f = dict(duty=0.34, lift=0.12, lift_peak=0.40, carpus=85.0, carpus_peak=0.40, fet_td=-10.0,
                   fet_mid=16.0, fet_lo=-24.0, fet_swing=-72.0, coffin_swing=-30.0, bo_start=0.64,
                   bo_angle=50.0, flip=100.0, flip_peak=0.33, dy=-0.14, sw_a=1.7, sw_b=1.75, w_rot_on=0.70)
    lead_f = dict(trail_f, duty=0.33, fet_mid=18.0, dy=-0.12)
    trail_h = dict(duty=0.34, lift=0.10, lift_peak=0.45, fet_td=-8.0, fet_mid=14.0, fet_lo=-24.0,
                   fet_swing=-62.0, coffin_swing=-25.0, bo_start=0.64, bo_angle=45.0, flip=75.0,
                   flip_peak=0.38, dy=-0.12, sw_a=1.7, sw_b=1.75, w_rot_on=0.70)
    lead_h = dict(trail_h, duty=0.33, dy=-0.08)
    if lead == "right":
        # PG 0 (non meneur) ; PD 0,24 ; AG 0,25 ; AD 0,50
        limbs = _limbs(LimbGait(td=0.25, **trail_f), LimbGait(td=0.52, **lead_f),
                       LimbGait(td=0.0, **trail_h), LimbGait(td=0.24, **lead_h))
    else:
        # pied gauche, décalé pour PG = 0 : PD −0,24→0,76 ; PG 0 ; AD 0,01 ; AG 0,28
        limbs = _limbs(LimbGait(td=0.28, **lead_f), LimbGait(td=0.01, **trail_f),
                       LimbGait(td=0.0, **lead_h), LimbGait(td=0.76, **trail_h))
    return GaitSpec(
        name=f"canter_{lead}", frames=17, speed=4.8, limbs=limbs,
        body_dz=-0.055, bob_amp=0.035, pitch_amp=4.0, roll_amp=1.0, surge_amp=0.012, sway_amp=0.006,
        hips_roll=1.0, hips_yaw=1.0, ls_flex=5.0, ls_flex0=0.0, spine_lat=0.5, spine_flex=2.0,
        neck_base=0.0, neck_amp=6.0, neck_cycles=1, neck_phase=0.0, head_comp=0.35,
        tail_lift=16.0, tail_gain=1.2, breathe_locked=True,
        notes=f"Galop à {'gauche' if lead == 'left' else 'droite'} 3 temps + suspension [R] (séquence "
              f"{'PD / PG+AD / AG' if lead == 'left' else 'PG / PD+AG / AD'}), décalages 0 / 0,24–0,25 / 0,52 "
              "dérivés des rapports de rythme [D] ; appuis 0,33–0,34 [D] ; suspension ≈ 15 % ; phase 0 = poser du postérieur "
              "gauche (SPEC). Bercement (tangage) et rebond 1×/foulée issus du modèle de forces [D] ; "
              "balancier d'encolure : tête haute au poser des postérieurs, basse sur l'antérieur meneur [U] ; "
              "respiration couplée 1:1 à la foulée (Bramble & Carrier, non vérifié) [U].",
        sources="gaits.md §1.4, §1.9, §2.3, §4 (respiration), §6")


def gallop_spec():
    # Galop transverse pied gauche : PD → PG → AD → AG [V : séquence] ; phases [U] (défaut gaits.md §6
    # miroir : PD 0, PG 0,10, AD 0,38, AG 0,50), décalées pour PG = 0 ; appui 0,25–0,30 [U].
    f = dict(duty=0.24, lift=0.17, lift_peak=0.32, carpus=100.0, carpus_peak=0.36, fet_td=-8.0,
             fet_mid=21.0, fet_lo=-24.0, fet_swing=-85.0, coffin_swing=-32.0, bo_start=0.62,
             bo_angle=52.0, flip=115.0, flip_peak=0.30, dy=-0.14, sw_a=1.45, sw_b=1.5, w_rot_on=0.72)
    h = dict(duty=0.25, lift=0.14, lift_peak=0.38, fet_td=-6.0, fet_mid=18.0, fet_lo=-24.0,
             fet_swing=-72.0, coffin_swing=-28.0, bo_start=0.62, bo_angle=48.0, flip=90.0,
             flip_peak=0.34, dy=-0.10, sw_a=1.45, sw_b=1.6, w_rot_on=0.72)
    limbs = _limbs(LimbGait(td=0.40, **f), LimbGait(td=0.28, **f),
                   LimbGait(td=0.0, **h), LimbGait(td=0.90, **h))
    return GaitSpec(
        name="gallop", frames=14, speed=8.0, limbs=limbs,
        body_dz=-0.06, bob_amp=0.035, pitch_amp=4.5, roll_amp=0.8, surge_amp=0.015, sway_amp=0.005,
        hips_roll=1.0, hips_yaw=0.5, ls_flex=8.0, spine_lat=0.3, spine_flex=3.0,
        neck_base=-6.0, neck_ext=6.0, neck_amp=7.0, neck_cycles=1, neck_phase=0.40, head_comp=0.3,
        tail_lift=26.0, tail_gain=1.3, breathe_locked=True,
        notes="Galop transverse à gauche PD→PG→AD→AG puis une suspension (séquence [V] Biancardi & Minetti "
              "2012) ; décalages de phase et appuis (0,24/0,25) NON vérifiés [A] ; phase 0 = poser du "
              "postérieur gauche. Flexion/extension lombo-sacrée ±8° et balancier d'encolure [U] ; queue "
              "haute ; respiration 1:1 [U].",
        sources="gaits.md §1.6, §1.9, §2.3, §6")


def back_spec():
    # Reculer : diagonal 2 temps sans suspension [V : FEI] ; appui 0,65 [D/U] ; v = −0,6 m/s, T ≈ 1,2 s.
    f = dict(duty=0.65, lift=0.06, lift_peak=0.50, carpus=45.0, carpus_peak=0.45, fet_td=-12.0,
             fet_mid=0.0, fet_lo=-18.0, fet_swing=-45.0, coffin_swing=-18.0, bo_start=0.75,
             bo_angle=25.0, flip=45.0, flip_peak=0.40, dy=-0.02)
    h = dict(duty=0.65, lift=0.05, lift_peak=0.50, fet_td=-10.0, fet_mid=0.0, fet_lo=-18.0,
             fet_swing=-40.0, coffin_swing=-18.0, bo_start=0.75, bo_angle=20.0, flip=40.0,
             flip_peak=0.40, dy=-0.02)
    limbs = _limbs(LimbGait(td=0.50, **f), LimbGait(td=0.0, **f),
                   LimbGait(td=0.0, **h), LimbGait(td=0.50, **h))
    return GaitSpec(
        name="back", frames=36, speed=-0.6, limbs=limbs,
        body_dz=-0.04, bob_amp=0.008, pitch_amp=0.6, roll_amp=0.6, surge_amp=0.004, sway_amp=0.004,
        hips_roll=1.5, hips_yaw=1.0, ls_flex=2.0, ls_flex0=5.0, spine_lat=0.5, spine_flex=1.0,
        body_pitch0=-1.0, neck_base=-8.0, neck_amp=1.5, neck_cycles=2, neck_phase=0.3, head_comp=0.5,
        tail_lift=-2.0,
        notes="Reculer diagonal 2 temps sans suspension (PG+AD puis PD+AG) [V : FEI] ; appui 0,65, vitesse "
              "−0,6 m/s, T = 1,2 s [D/U] ; croupe abaissée (flexion lombo-sacrée accrue [V : Vet J 2024]), "
              "base d'appui légèrement élargie.",
        sources="gaits.md §1.7")


def turn_spec(direction="left"):
    # Pirouette au pas (demi-pirouette sur les hanches) : rythme 4 temps conservé, le postérieur
    # intérieur se pose presque sur place [V : FEI] ; antérieurs et postérieur extérieur tournent autour.
    # ω = ±1,2 rad/s (SPEC) sur 1,4 s ⇒ 3 foulées courtes (0,467 s) pour limiter le déplacement latéral
    # des antérieurs par appui [I] ; pivot = milieu des postérieurs ⇒ la racine a une vitesse latérale
    # v = ω × (origine − pivot) dans le repère du poney [I].
    s = 1.0 if direction == "left" else -1.0
    base_f = dict(duty=0.55, lift=0.075, lift_peak=0.45, carpus=55.0, carpus_peak=0.42, fet_td=-12.0,
                  fet_mid=0.0, fet_lo=-18.0, fet_swing=-50.0, coffin_swing=-20.0, bo_start=0.75,
                  bo_angle=25.0, flip=55.0, flip_peak=0.38)
    base_h = dict(duty=0.60, lift=0.04, lift_peak=0.5, fet_td=-10.0, fet_mid=0.0, fet_lo=-15.0,
                  fet_swing=-35.0, coffin_swing=-15.0, bo_start=0.80, bo_angle=15.0, flip=30.0,
                  flip_peak=0.4)
    # antérieur extérieur : se pose devant l'intérieur (croisement par l'avant) [V* USDF/FEI]
    inner_f = dict(base_f, dy=-0.02, dx=0.02)
    outer_f = dict(base_f, dy=0.10, dx=-0.01, arc_fwd=0.06)
    limbs = {}
    if direction == "left":
        limbs = _limbs(LimbGait(td=0.22, **inner_f), LimbGait(td=0.72, **outer_f),
                       LimbGait(td=0.0, **base_h), LimbGait(td=0.50, **base_h))
    else:
        limbs = _limbs(LimbGait(td=0.22, **outer_f), LimbGait(td=0.72, **inner_f),
                       LimbGait(td=0.0, **base_h), LimbGait(td=0.50, **base_h))
    return GaitSpec(
        name=f"turn_{direction}", frames=42, strides=3, speed=0.0, limbs=limbs, yaw_rate=s * 1.2,
        pivot=None, use_twist=True,
        body_dz=-0.035, bob_amp=0.008, pitch_amp=0.5, roll_amp=0.6, surge_amp=0.003, sway_amp=0.004,
        hips_roll=1.5, hips_yaw=1.0, ls_flex=1.0, ls_flex0=3.0, spine_lat=0.5, body_pitch0=0.8,
        neck_base=-2.0, neck_amp=1.5, neck_cycles=2, neck_phase=0.3, head_comp=0.4,
        turn_bend=s * 14.0, tail_lift=0.0,
        notes="Pivot sur les hanches au pas (4 temps, postérieur intérieur posé presque sur place) [V : FEI] ; "
              "antérieur extérieur croisant devant l'intérieur [V* USDF] ; incurvation vers l'intérieur "
              "[V : FEI]. ω = ±1,2 rad/s (SPEC) ; le cycle de 1,4 s contient 3 foulées de 0,467 s [I] "
              "(cette durée de cycle est portée par `frameCount`, cf. meta). Pivot = milieu des postérieurs : "
              "rootVelocity = ω × (origine − pivot), latérale [I] ; si le runtime l'ignore, le pivot devient "
              "l'origine et les postérieurs patinent d'environ ω·0,55 m/s.",
        sources="gaits.md §1.8")


# ==============================================================================================
# Mouvement racine
# ==============================================================================================
def root_motion(t, v_local, omega):
    """M(t) : (len(t), 3, 3) rotations et (len(t), 3) translations (Blender) pour v_local, ω constants."""
    t = np.asarray(t, dtype=np.float64)
    R = mu.rz(omega * t)
    v = np.asarray(v_local, dtype=np.float64)
    if abs(omega) < 1e-9:
        p = t[:, None] * v[None, :]
    else:
        s, c = np.sin(omega * t), np.cos(omega * t)
        px = (s * v[0] + (c - 1.0) * v[1]) / omega
        py = ((1.0 - c) * v[0] + s * v[1]) / omega
        p = np.stack([px, py, np.zeros_like(t)], axis=1)
    p[:, 2] = v[2] * t
    return R, p


def to_clip(R, p, P):
    """Monde -> repère du clip : R^T (P − p). R (T,3,3), p (T,3), P (T,...,3)."""
    return np.einsum("tji,t...j->t...i", R, P - p.reshape(p.shape[0], *([1] * (P.ndim - 2)), 3))


# ==============================================================================================
# Trajectoires de sabots
# ==============================================================================================
@dataclass
class HoofTrack:
    toe: np.ndarray       # (T,3) repère clip
    heel: np.ndarray      # (T,3)
    quarters: np.ndarray  # (T,2,3)
    stance: np.ndarray    # (T,) bool
    s: np.ndarray         # progression dans la phase courante (0..1)
    u: np.ndarray         # phase du membre (0..1, 0 = poser)
    w_rot: np.ndarray     # poids d'orientation
    toe_world: np.ndarray


def _breakover(s, lg: LimbGait):
    x = np.clip((s - lg.bo_start) / (1.0 - lg.bo_start), 0.0, 1.0)
    return lg.bo_angle * D * x * x


def _swing_pitch(s, lg: LimbGait, stance_dur, swing_dur):
    """Guide de rotation du sabot en envol (rad, + = talons vers le haut / sole vers l'arrière)."""
    b0 = lg.bo_angle * D
    rate0 = 2.0 * b0 / max((1.0 - lg.bo_start) * stance_dur, 1e-6)   # rad/s en fin d'appui
    fp = lg.flip_peak
    out = np.zeros_like(s)
    a = s <= fp
    out[a] = mu.hermite(b0, rate0 * swing_dur * fp, lg.flip * D, 0.0, s[a] / fp)
    b = (s > fp) & (s < 0.9)
    out[b] = lg.flip * D * (1.0 - mu.smootherstep((s[b] - fp) / (0.9 - fp)))
    return out


def hoof_track(sk: Skeleton, limb: str, lg: LimbGait, spec: GaitSpec, t, period, v_local, omega, pivot):
    side = -1.0 if limb.endswith("l") else 1.0
    rest = sk.rest_sole_world(limb)                      # (6,3)
    neutral = rest + np.array([side * lg.dx, lg.dy, 0.0])
    toe0 = neutral[0]
    heel_off = neutral[5] - neutral[0]
    quart_off = neutral[3:5] - neutral[0]
    T = period
    t = np.asarray(t, dtype=np.float64)
    ph = t / T - lg.td
    k = np.floor(ph)
    u = ph - k
    stance = u < lg.duty
    st_dur = lg.duty * T
    sw_dur = (1.0 - lg.duty) * T
    s = np.where(stance, u / lg.duty, (u - lg.duty) / (1.0 - lg.duty))

    def stance_pose(kk):
        """Pose monde (toe, heel_off_dir, yaw) de l'appui n° kk (pose neutre au milieu de l'appui)."""
        tm = (kk + lg.td + lg.duty / 2.0) * T
        R, p = root_motion(np.atleast_1d(tm), v_local, omega)
        toe_w = np.einsum("tij,j->ti", R, toe0) + p
        yaw = omega * np.atleast_1d(tm)
        return toe_w, yaw

    toe_w = np.zeros((len(t), 3))
    heel_w = np.zeros((len(t), 3))
    w_rot = np.ones(len(t))
    # appui
    tw, yaw = stance_pose(k)
    beta = _breakover(s, lg)
    pitch = np.where(stance, beta, 0.0)
    # envol : de l'appui k vers l'appui k+1
    tw1, yaw1 = stance_pose(k + 1)
    sw = ~stance
    # profil horizontal : CDF de la loi bêta(a, b) — vitesse nulle en monde au décollement et au poser ;
    # a = b = 2 donne smoothstep (dépassement/rétraction de fin d'envol ~2× plus faible qu'en minimum-jerk) ;
    # a, b < 2 : accélération plus vive au décollement et freinage plus tardif (allures rapides) [I]
    from scipy.special import betainc
    m = betainc(lg.sw_a, lg.sw_b, np.clip(s, 0.0, 1.0))
    toe_sw = tw + (tw1 - tw) * m[:, None]
    fwd = np.stack([-np.sin(yaw + (yaw1 - yaw) * m), np.cos(yaw + (yaw1 - yaw) * m), np.zeros_like(m)], 1)
    lat = np.stack([np.cos(yaw + (yaw1 - yaw) * m), np.sin(yaw + (yaw1 - yaw) * m), np.zeros_like(m)], 1) * side
    toe_sw = toe_sw + np.array([0, 0, 1.0]) * (lg.lift * mu.bump(s, lg.lift_peak))[:, None]
    toe_sw = toe_sw + fwd * (lg.arc_fwd * mu.bump(s, 0.5))[:, None] + lat * (lg.arc_lat * mu.bump(s, 0.5))[:, None]
    yaw_sw = yaw + (yaw1 - yaw) * m
    pitch_sw = _swing_pitch(s, lg, st_dur, sw_dur)
    toe_w = np.where(sw[:, None], toe_sw, tw)
    yaw_all = np.where(sw, yaw_sw, yaw)
    pitch = np.where(sw, pitch_sw, pitch)
    # talon : rotation (lacet puis tangage autour de l'axe latéral du sabot) de l'offset talon-pince
    Ryaw = mu.rz(yaw_all)
    Rp = mu.rx(-pitch)
    heel_w = toe_w + np.einsum("tij,tjk,k->ti", Ryaw, Rp, heel_off)
    quart_w = toe_w[:, None, :] + np.einsum("tij,tjk,qk->tqi", Ryaw, Rp, quart_off)
    # poids d'orientation en envol
    on = lg.w_rot_on
    wr = 1.0 - 0.97 * np.minimum(mu.smoothstep(s / 0.22), 1.0 - mu.smoothstep((s - on) / (0.97 - on)))
    w_rot = np.where(sw, wr, 1.0)
    # vers le repère du clip
    R, p = root_motion(t, v_local, omega)
    toe_c = to_clip(R, p, toe_w[:, None, :])[:, 0]
    heel_c = to_clip(R, p, heel_w[:, None, :])[:, 0]
    quart_c = to_clip(R, p, quart_w)
    return HoofTrack(toe=toe_c, heel=heel_c, quarters=quart_c, stance=stance, s=s, u=u, w_rot=w_rot, toe_world=toe_w)


# ==============================================================================================
# Dynamique du tronc (modèle de forces d'appui) [D]
# ==============================================================================================
def periodic_integrate2(a, dt):
    """Double intégrale périodique (moyenne nulle) d'un signal périodique échantillonné."""
    n = len(a)
    A = np.fft.rfft(a - a.mean())
    f = np.fft.rfftfreq(n, dt)
    w = 2 * np.pi * f
    X = np.zeros_like(A)
    X[1:] = -A[1:] / (w[1:] ** 2)
    return np.fft.irfft(X, n=n)


def periodic_integrate1(a, dt):
    n = len(a)
    A = np.fft.rfft(a - a.mean())
    f = np.fft.rfftfreq(n, dt)
    w = 2 * np.pi * f
    X = np.zeros_like(A)
    X[1:] = A[1:] / (1j * w[1:])
    return np.fft.irfft(X, n=n)


def damped_response(x, dt, f0, zeta, gain=1.0, deriv=0):
    """Réponse périodique stationnaire d'un oscillateur amorti (ω0 = 2π f0) à la force x (FFT)."""
    n = len(x)
    X = np.fft.rfft(x - x.mean())
    w = 2 * np.pi * np.fft.rfftfreq(n, dt)
    w0 = 2 * np.pi * f0
    H = w0 * w0 / (w0 * w0 - w * w + 2j * zeta * w0 * w)
    Y = X * H * gain * ((1j * w) ** deriv)
    return np.fft.irfft(Y, n=n) + (x.mean() * gain if deriv == 0 else 0.0)


def load_model(sk: Skeleton, spec: GaitSpec, tracks: dict, t, period):
    """Forces verticales en demi-sinus pendant chaque appui (masse unité) ; renvoie les signaux du tronc."""
    dt = t[1] - t[0]
    Fz = {}
    for limb in LIMBS:
        lg = spec.limbs[limb]
        share = spec.fore_share / 2 if limb.startswith("f") else (1.0 - spec.fore_share) / 2
        A = share * G * np.pi / (2.0 * lg.duty)
        tr = tracks[limb]
        Fz[limb] = np.where(tr.stance, A * np.sin(np.pi * np.clip(tr.s, 0, 1)), 0.0)
    total = sum(Fz.values())
    az = total - G
    z = periodic_integrate2(az, dt)
    # tangage
    ytoe = {l: tracks[l].toe[:, 1] for l in LIMBS}
    xtoe = {l: tracks[l].toe[:, 0] for l in LIMBS}
    num = sum((Fz[l] * ytoe[l]).sum() for l in LIMBS)
    y_com = num / total.sum()
    tau = sum(Fz[l] * (ytoe[l] - y_com) for l in LIMBS)
    k_p = 0.42   # rayon de giration en tangage (m) [A]
    pitch = periodic_integrate2(tau / k_p ** 2, dt)
    tau_r = -sum(Fz[l] * xtoe[l] for l in LIMBS)
    k_r = 0.22   # rayon de giration en roulis (m) [A]
    roll = periodic_integrate2(tau_r / k_r ** 2, dt)
    # avance/recul : force horizontale dirigée le long du membre (sabot -> articulation proximale)
    prox = {"fl": sk.head[sk.idx("scapula_l")], "fr": sk.head[sk.idx("scapula_r")],
            "hl": sk.head[sk.idx("thigh_l")], "hr": sk.head[sk.idx("thigh_r")]}
    ay = sum(Fz[l] * (prox[l][1] - ytoe[l]) / prox[l][2] for l in LIMBS)
    ax = sum(Fz[l] * (prox[l][0] - xtoe[l]) / prox[l][2] for l in LIMBS)
    surge = periodic_integrate2(ay - ay.mean(), dt)
    sway = periodic_integrate2(ax - ax.mean(), dt)
    load = {l: Fz[l] / (G * 0.25) for l in LIMBS}     # charge normalisée (1 = quart du poids)
    return dict(z=z, pitch=pitch, roll=roll, surge=surge, sway=sway, y_com=y_com, load=load, Fz=Fz)


# ==============================================================================================
# Assemblage du tronc / encolure / queue
# ==============================================================================================
def world_aligned_to_local(sk: Skeleton, joint: str, pitch, roll, yaw):
    """Rotation exprimée dans les axes « parent alignés au monde » (tangage + = nez en haut autour de X,
    roulis + = côté droit vers le bas autour de Y, lacet + = vers la gauche autour de Z) -> angles
    locaux (flex, twist, lat) de l'os (lots acceptés)."""
    j = sk.idx(joint)
    p = sk.parents[j]
    Rrel = sk.rest_world[j][:3, :3] if p < 0 else (sk.rest_world[p][:3, :3].T @ sk.rest_world[j][:3, :3])
    # axes du parent au repos exprimés en monde
    Rp = np.eye(3) if p < 0 else sk.rest_world[p][:3, :3]
    Rw = mu.rz(yaw) @ mu.rx(pitch) @ mu.ry(roll)                  # dans les axes monde
    # rotation dans le repère du parent : Rp^T Rw Rp ; puis dans le repère local de l'os
    Rpar = np.einsum("ji,...jk,kl->...il", Rp, Rw, Rp)
    Rloc = np.einsum("ji,...jk,kl->...il", Rrel, Rpar, Rrel)
    return mu.mat_to_euler(Rloc)


def tail_sagittal_to_local(sk: Skeleton, parent_pitch, world_delta):
    """Queue : angles « monde » sagittaux -> flexions locales.

    parent_pitch (F,) : tangage monde du bassin par rapport au repos (rad, + = croupe… nez en haut) ;
    world_delta (F,10) : écart de l'angle monde de chaque os de queue par rapport au repos
    (+ = sens trigonométrique vu de la droite ; pour un os pendant vers l'arrière, − = relevé).
    flex_i = (θ_i − θ_{i−1}) − (θ_i⁰ − θ_{i−1}⁰) = Δ_i − Δ_{i−1}, avec Δ_{−1} = tangage du bassin."""
    F = world_delta.shape[0]
    prev = parent_pitch
    out = np.zeros((F, len(TAIL)))
    for i in range(len(TAIL)):
        out[:, i] = world_delta[:, i] - prev
        prev = world_delta[:, i]
    return out


# port de queue : poids de relevé le long de la queue (vertèbres caudales 1-4 portent, crins 5-10 pendent)
TAIL_DOCK = np.array([1.0, 0.85, 0.65, 0.40, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
TAIL_HAIR = np.array([0.0, 0.0, 0.0, 0.0, 0.5, 0.8, 1.0, 1.0, 1.0, 1.0])


def tail_motion(sk, F, t, period, pelvis_pitch, z, spec: GaitSpec, hips_yaw=None):
    """Angles locaux (F,10,3) de la queue [U/A] : tronçon osseux relevé de `tail_lift`, crins pendants
    (compensent le relevé et le tangage du bassin) inclinés vers l'arrière par la vitesse, plus une
    petite oscillation retardée (oscillateurs amortis en régime périodique, amplitude bornée).
    Le runtime ajoute sa propre physique secondaire (SPEC §8) : le clip ne porte que le port de queue."""
    dt = t[1] - t[0]
    out = np.zeros((F, len(TAIL), 3))
    lift = -spec.tail_lift * D
    # crins : orientation monde ≈ pendante, inclinée vers l'arrière avec la vitesse [A]
    v = abs(spec.speed)
    drag = -min(45.0, 6.0 * v) * D
    world = np.zeros((F, len(TAIL)))
    # angle monde du tronçon osseux = tangage du bassin + relevé ; crins : relevé compensé + traînée
    pp = pelvis_pitch - pelvis_pitch.mean()
    for i in range(len(TAIL)):
        dock_part = TAIL_DOCK[i] * (lift + pelvis_pitch)
        hair_part = TAIL_HAIR[i] * drag + (1.0 - TAIL_HAIR[i]) * (1.0 - TAIL_DOCK[i]) * (lift * 0.4)
        world[:, i] = dock_part + hair_part
    # oscillation : réponse amortie au tangage du bassin et à l'accélération verticale, ±6° max [A]
    az = np.gradient(np.gradient(z, dt), dt) if len(z) > 3 else np.zeros_like(z)
    forcing = -0.6 * pp + 0.04 * az / G
    for i in range(len(TAIL)):
        f0 = 2.6 - 0.12 * i
        dyn = damped_response(forcing, dt, f0, 0.45, gain=0.4 + 0.08 * i) * spec.tail_gain
        lim = (2.0 + 0.6 * i) * D
        world[:, i] += lim * np.tanh(dyn / lim)
    out[:, :, 0] = tail_sagittal_to_local(sk, pelvis_pitch, world)
    if hips_yaw is not None and spec.tail_swing:
        for i in range(len(TAIL)):
            f0 = 2.0 - 0.1 * i
            lat = damped_response(hips_yaw, dt, f0, 0.4, gain=1.0)
            out[:, i, 2] = -lat / max(np.abs(hips_yaw).max(), 1e-9) * spec.tail_swing * D * (0.10 + 0.03 * i)
    return out


# ==============================================================================================
# Génération d'un clip d'allure
# ==============================================================================================
def make_gait_clip(sk: Skeleton, spec: GaitSpec, verbose=False) -> Clip:
    F = spec.frames
    T = F / FPS / spec.strides           # période de foulée
    v_local = np.array([0.0, spec.speed, 0.0])
    omega = spec.yaw_rate
    pivot = spec.pivot
    if omega != 0.0 and pivot is None:
        # pivot = milieu des postérieurs (pinces au repos)
        ph = 0.5 * (sk.rest_sole_world("hl")[0] + sk.rest_sole_world("hr")[0])
        pivot = (0.0, float(ph[1]))
    if pivot is None:
        pivot = (0.0, 0.0)
    if omega != 0.0:
        v_local = v_local + np.array([omega * pivot[1], -omega * pivot[0], 0.0])

    # échantillonnage fin pour la dynamique, puis images
    OS = 16
    Fs = F // spec.strides               # images par foulée (la dynamique est calculée sur une foulée)
    tf = np.arange(Fs * OS) / (FPS * OS)
    t = np.arange(F) / FPS
    tracks_f = {l: hoof_track(sk, l, spec.limbs[l], spec, tf, T, v_local, omega, pivot) for l in LIMBS}
    tracks = {l: hoof_track(sk, l, spec.limbs[l], spec, t, T, v_local, omega, pivot) for l in LIMBS}
    dyn = load_model(sk, spec, tracks_f, tf, T)
    sub = slice(0, None, OS)
    rep = lambda a: np.tile(a[sub], spec.strides)

    def scaled(sig, amp):
        half = 0.5 * np.ptp(sig)
        return rep(sig) * (amp / half if half > 1e-9 else 0.0)

    z = scaled(dyn["z"], spec.bob_amp)
    pitch = scaled(dyn["pitch"], spec.pitch_amp * D)
    roll = scaled(dyn["roll"], spec.roll_amp * D)
    surge = scaled(dyn["surge"], spec.surge_amp)
    sway = scaled(dyn["sway"], spec.sway_amp)
    load = {l: rep(dyn["load"][l]) for l in LIMBS}

    N = sk.N
    ang = np.zeros((F, N, 3))
    trans = np.zeros((F, N, 3))

    # --- protraction normalisée des membres (pince vs neutre), pour bassin/colonne
    def protr(limb):
        lg = spec.limbs[limb]
        y = tracks[limb].toe[:, 1] - (sk.rest_sole_world(limb)[0, 1] + lg.dy)
        span = max(abs(spec.speed) * T * lg.duty / 2.0, 0.05)
        return y / span

    p_hl, p_hr = protr("hl"), protr("hr")
    p_fl, p_fr = protr("fl"), protr("fr")
    hind_pro = 0.5 * (p_hl + p_hr)

    # --- body : translation + rotation autour du centre de masse estimé
    bj = sk.idx("body")
    pitch_tot = pitch + spec.body_pitch0 * D
    # lacet du tronc en virage : léger (l'incurvation est portée par la colonne)
    yaw_body = np.zeros(F)
    eul = world_aligned_to_local(sk, "body", pitch_tot, roll, yaw_body)
    ang[:, bj] = eul
    com = np.array([0.0, dyn["y_com"], sk.head[bj][2] - 0.05])
    head_b = sk.head[bj]
    Rb = mu.euler_to_mat(eul)
    # rotation autour du COM : t = (I − R)(com − head)
    comp = (np.eye(3)[None] - Rb) @ (com - head_b)
    trans[:, bj] = np.stack([sway, surge, z + spec.body_dz], axis=1) + comp

    # --- bassin (hips) relatif au tronc
    hips_pitch = -(spec.ls_flex * hind_pro + spec.ls_flex0) * D     # flexion LS = croupe qui s'enroule
    hips_roll = spec.hips_roll * D * np.tanh(load["hl"] - load["hr"])
    hips_yaw = -spec.hips_yaw * D * (p_hl - p_hr) / 2.0
    # le bassin pointe vers l'arrière : « tangage nez en haut » du bassin = croupe qui descend
    ang[:, sk.idx("hips")] = world_aligned_to_local(sk, "hips", -hips_pitch, hips_roll, hips_yaw)
    # --- colonne : compense le lacet du bassin et porte l'incurvation de virage
    bend = spec.turn_bend * D
    sp_flex = spec.spine_flex * D * hind_pro
    for k, jn in enumerate(["spine_01", "spine_02", "spine_03"]):
        lat = -hips_yaw * spec.spine_lat / max(spec.hips_yaw, 1e-6) * [0.5, 0.3, 0.2][k] if spec.hips_yaw else 0.0
        lat = lat + bend * [0.12, 0.12, 0.10][k]
        fl = -sp_flex * [0.5, 0.3, 0.2][k] + (spec.ls_flex0 * D * 0.3 if k == 0 else 0.0)
        ang[:, sk.idx(jn), 0] = fl
        ang[:, sk.idx(jn), 2] = lat
    # --- encolure / tête
    ph = 2 * np.pi * spec.neck_cycles * (t / T - spec.neck_phase)
    nod = -spec.neck_amp * D * np.cos(ph)              # point bas (tête basse) à neck_phase
    lag = 2 * np.pi * spec.neck_cycles * spec.neck_lag
    nod_head = -spec.neck_amp * D * np.cos(ph - lag)
    wneck = np.array([0.30, 0.25, 0.18, 0.12, 0.08, 0.07])
    for k, jn in enumerate(NECK):
        base = spec.neck_base * D * wneck[k]
        ext = spec.neck_ext * D * ([-1.0, -0.6, 0.0, 0.5, 0.8, 1.0][k]) * 0.5
        ang[:, sk.idx(jn), 0] = base + ext + nod * wneck[k]
        ang[:, sk.idx(jn), 2] = bend * [0.10, 0.12, 0.13, 0.12, 0.10, 0.09][k]
    trunk_pitch = pitch_tot + ang[:, sk.idx("spine_03"), 0] + ang[:, sk.idx("spine_02"), 0]
    neck_sum = ang[:, [sk.idx(n) for n in NECK], 0].sum(axis=1)
    head = (spec.head_base * D - spec.head_comp * (trunk_pitch + neck_sum - (neck_sum.mean()))
            + 0.35 * (nod_head - nod))
    ang[:, sk.idx("head"), 0] = head
    ang[:, sk.idx("head"), 2] = bend * 0.12
    # --- queue
    # forçage : tangage monde du bassin (tronc + flexion lombo-sacrée) et accélération verticale
    # tangage monde du bassin (nez en haut +) : tronc + flexion lombo-sacrée (+ = croupe qui s'enroule,
    # ce qui fait pivoter la base de queue vers le bas)
    pelvis_pitch = pitch_tot + (spec.ls_flex * hind_pro + spec.ls_flex0) * D
    tail = tail_motion(sk, F, t, T, pelvis_pitch, z, spec, hips_yaw=hips_yaw)
    for i, jn in enumerate(TAIL):
        ang[:, sk.idx(jn)] = tail[:, i]
        if spec.turn_bend:
            ang[:, sk.idx(jn), 2] += bend * 0.04

    # --- FK du tronc (membres au repos) pour obtenir les repères parents
    W = sk.fk(sk.basis_from_angles(ang, trans))

    # --- IK des membres
    diag = {"err_toe": {}, "err_heel": {}}
    for limb in LIMBS:
        lg = spec.limbs[limb]
        solver = LimbSolver(sk, limb, k_scap=spec.k_scap, use_twist=spec.use_twist)
        tr = tracks[limb]
        # profils (phase du membre u)
        Dd = lg.duty
        fet_keys_u = [0.0, Dd * 0.45, Dd * lg.bo_start, Dd, Dd + 0.30 * (1 - Dd), Dd + 0.62 * (1 - Dd),
                      Dd + 0.85 * (1 - Dd)]
        fet_keys_v = [lg.fet_td, lg.fet_mid, 0.5 * (lg.fet_mid + lg.fet_lo), lg.fet_lo, lg.fet_swing,
                      0.55 * lg.fet_swing, lg.fet_td - 4.0]
        fet_fn = mu.periodic_spline(fet_keys_u, np.array(fet_keys_v) * D, 1.0)
        fet = fet_fn(tr.u)
        coffin = np.where(tr.stance, 0.0, lg.coffin_swing * D * mu.bump(tr.s, 0.40))
        if limb.startswith("f"):
            # carpe : verrouillé (+2° vers la rectitude) à l'appui, flexion en envol commencée en fin de
            # bascule [R qualitatif : Back 1995 ; amplitude ~76° au trot V*]
            u0 = Dd - 0.05
            u1 = Dd + 0.86 * (1 - Dd)
            x = np.clip((tr.u - u0) / (u1 - u0), 0, 1)
            pk = (Dd + lg.carpus_peak * (1 - Dd) - u0) / (u1 - u0)
            carpus = 2.0 * D - (lg.carpus + 2.0) * D * mu.bump(x, pk)
        else:
            carpus = np.zeros(F)
        xs = np.zeros((F, len(solver.var_names)))
        errs = np.zeros((F, 2))
        x_prev = None
        order = list(range(F)) + list(range(F))     # deux passes (démarrage à chaud périodique)
        for n_it, f in enumerate(order):
            inp = LimbFrameInput(
                toe=tr.toe[f], heel=tr.heel[f], quarters=tr.quarters[f], w_rot=float(tr.w_rot[f]),
                carpus=float(carpus[f]),
                fetlock_pref=float(fet[f]), coffin_pref=float(coffin[f]), w_fetlock=lg.w_fetlock,
                w_coffin=0.15 + 0.6 * (1.0 - float(tr.w_rot[f])),
                ground_clear=0.004 if not tr.stance[f] else -1.0,
                w_ground=6000.0 if not tr.stance[f] else 0.0)
            x, chain, info = solver.solve(W[f, solver.parent], inp, x0=x_prev)
            x_prev = x
            if n_it >= F:
                xs[f] = x
                write_chain(ang, f, sk, limb, chain)
                errs[f] = (info["err_toe"], info["err_heel"])
        diag["err_toe"][limb] = errs[:, 0]
        diag["err_heel"][limb] = errs[:, 1]

    # --- évènements
    events = []
    for kstr in range(spec.strides):
        for limb in LIMBS:
            lg = spec.limbs[limb]
            tdn = ((lg.td % 1.0) + kstr) * T
            lon = (((lg.td + lg.duty) % 1.0) + kstr) * T
            events.append((round(tdn, 4), f"foot_down_{limb}"))
            events.append((round(lon, 4), f"foot_up_{limb}"))
    weights = {}
    if spec.breathe_locked:
        # inspiration au lever de l'avant-main (après le poser des postérieurs), expiration sur l'antérieur
        # meneur (piston viscéral) [U]
        phase = 2 * np.pi * (t / T - spec.breathe_phase)
        lead = max(("fl", "fr"), key=lambda l: spec.limbs[l].td % 1.0)
        tl = spec.limbs[lead].td % 1.0
        insp = 0.5 - 0.5 * np.cos(2 * np.pi * (t / T - tl - 0.5))
        weights["body_breathe"] = 0.25 + 0.6 * insp
        weights["face_nostril_flare"] = 0.35 + 0.45 * insp
    clip = Clip(name=spec.name, loop=True, ang=ang, trans=trans, weights=weights,
                root_velocity_b=tuple(v_local), root_yaw_rate=omega,
                root_pivot_b=pivot if omega else None, events=events, notes=spec.notes)
    gait_meta = {
        "phaseConvention": "phase 0 = poser du postérieur gauche (SPEC §7)",
        "strideLength": round(float(np.linalg.norm(v_local) * T), 4),
        "strideDuration": round(float(T), 6),
        "stridesPerClip": spec.strides,
        "footfalls": {l: {"touchdown": round(spec.limbs[l].td % 1.0, 4),
                          "liftoff": round((spec.limbs[l].td + spec.limbs[l].duty) % 1.0, 4),
                          "duty": spec.limbs[l].duty} for l in LIMBS},
        "phaseOffset": 0.0,
        "sources": spec.sources,
    }
    clip.extra_meta.update(gait_meta)
    clip.contacts = {l: tracks[l].stance.copy() for l in LIMBS}
    clip.diag = {"tracks": tracks, "dyn": dyn, "ik": diag, "v_local": v_local, "omega": omega,
                 "pivot": pivot}
    if verbose:
        print(f"[{spec.name}] z ±{np.ptp(z) / 2 * 100:.2f} cm, pitch ±{np.ptp(pitch) / 2 / D:.2f}°, "
              f"roll ±{np.ptp(roll) / 2 / D:.2f}°, surge ±{np.ptp(surge) / 2 * 100:.2f} cm, "
              f"IK toe err max {max(diag['err_toe'][l].max() for l in LIMBS) * 1000:.2f} mm")
    return clip
