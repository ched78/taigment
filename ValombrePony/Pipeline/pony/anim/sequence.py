"""Enchaînement du saut tel que le runtime PonyKit le joue (aperçu et contrôle de franchissement, numpy pur).

Reproduit la logique de `PonyKit/Sources/PonyCore/Locomotion/MotionController.swift` et `JumpSettings`
(valeurs par défaut lues dans le code Swift au moment de l'écriture — à resynchroniser si elles changent) :
- `jump_takeoff` entre en fondu (0,12 s) depuis le galop ; l'arc balistique commence à l'évènement `takeoff` ;
- `jump_air` entre à `durée(takeoff) − 0,08 s` (fondu 0,08 s) ;
- `jump_land` entre quand le temps de vol balistique est écoulé (fondu 0,08 s) ;
- reprise du galop à `durée(land) − 0,25 s` (fondu 0,25 s).
Altitude de l'entité : montée au sommet h = max(0,15 ; obstacle − 0,35 + 0,05) avec un obstacle de 0,70 m,
v0 = √(2 g h), vol t = 2 v0 / g. Vitesse horizontale : celle des clips (meta `rootVelocity`).
Les fondus sont des nlerp de poses locales (même principe que le runtime ; sa courbe exacte de fondu n'est pas
reproduite) [I].
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import clip_io
from . import mathutil as mu

G = 9.81
TAKEOFF_FADE, AIR_FADE, LAND_FADE, RECOVER_FADE = 0.12, 0.08, 0.08, 0.25
OBSTACLE_H, TUCK_CLEARANCE, CLEARANCE_MARGIN, MIN_APEX = 0.70, 0.35, 0.05, 0.15


class _Player:
    def __init__(self, local, meta):
        self.local, self.meta = local, meta
        self.F = local.shape[0]
        self.fps = meta["fps"]
        self.loop = meta["loop"]
        self.dur = meta["duration"]

    def sample(self, t):
        """Pose locale au temps t (interpolation linéaire entre images ; boucle ou maintien à la fin)."""
        x = t * self.fps
        if self.loop:
            x = np.mod(x, self.F)
            a = int(np.floor(x))
            b = (a + 1) % self.F
        else:
            x = float(np.clip(x, 0.0, self.F - 1))
            a = int(np.floor(x))
            b = min(a + 1, self.F - 1)
        w = x - a
        return mu.blend_locals(self.local[a], self.local[b], w) if w > 1e-9 else self.local[a].copy()

    @property
    def speed(self):
        v = self.meta["rootVelocity"]
        return float(-v[2])        # avant RK = −Z


def jump_sequence(clip_dir, fps=30, approach=0.62, after=0.7, approach_clip="canter_left"):
    """Liste d'images : dict(local (N,4,4), y (avance, m, Blender +Y), z (altitude entité), label, t).
    Renvoie aussi les infos du vol (position de l'obstacle au milieu du vol)."""
    clip_dir = Path(clip_dir)
    P = {n: _Player(*[clip_io.load_npz(clip_dir / f"{n}.npz")[i] for i in (0, 3)])
         for n in (approach_clip, "jump_takeoff", "jump_air", "jump_land")}
    canter, tko, air, land = P[approach_clip], P["jump_takeoff"], P["jump_air"], P["jump_land"]
    t_takeoff = next((e["time"] for e in tko.meta["events"] if e["name"] == "takeoff"), tko.dur)
    apex = max(MIN_APEX, OBSTACLE_H - TUCK_CLEARANCE + CLEARANCE_MARGIN)
    v0 = (2 * G * apex) ** 0.5
    flight = 2 * v0 / G
    dt = 1.0 / fps
    frames = []
    y = 0.0
    # états : (mode, temps dans le mode, clip précédent pour le fondu, temps du précédent, durée du fondu)
    t = 0.0
    mode, mt = "approach", 0.0
    prev, pt, fade = None, 0.0, 0.0
    air_t = None
    info = {"apex_m": apex, "v0": v0, "flight_s": flight, "takeoff_y": None, "land_y": None}
    end_after = None
    cur = canter
    while True:
        pose = cur.sample(mt)
        if prev is not None and fade > 0 and mt < fade:
            pose = mu.blend_locals(prev.sample(pt), pose, mu.smoothstep(mt / fade))
        z = 0.0
        if air_t is not None:
            z = max(0.0, v0 * air_t - 0.5 * G * air_t ** 2)
        frames.append(dict(local=pose, y=y, z=z, label=f"{mode} {mt:.2f}s", t=t))
        # avance
        v = cur.speed if mode != "approach" else canter.speed
        y += v * dt
        t += dt
        mt += dt
        pt += dt
        if air_t is not None:
            air_t += dt
        # transitions (même ordre que le runtime)
        if mode == "approach" and mt >= approach - 1e-9:
            prev, pt, fade = cur, mt, TAKEOFF_FADE
            mode, mt, cur = "jump_takeoff", 0.0, tko
        elif mode == "jump_takeoff":
            if air_t is None and mt >= t_takeoff - 1e-9:
                air_t = 0.0
                info["takeoff_y"] = y
            if mt >= tko.dur - AIR_FADE - 1e-9:
                if air_t is None:
                    air_t = 0.0
                prev, pt, fade = cur, mt, AIR_FADE
                mode, mt, cur = "jump_air", 0.0, air
        elif mode == "jump_air" and air_t is not None and air_t >= flight - 1e-9:
            air_t = None
            info["land_y"] = y
            prev, pt, fade = cur, mt, LAND_FADE
            mode, mt, cur = "jump_land", 0.0, land
        elif mode == "jump_land" and mt >= land.dur - RECOVER_FADE - 1e-9:
            prev, pt, fade = cur, mt, RECOVER_FADE
            mode, mt, cur = "canter", 0.0, canter
            end_after = t + after
        if end_after is not None and t >= end_after - 1e-9:
            break
        if t > 10:
            break
    info["fence_y"] = 0.5 * (info["takeoff_y"] + info["land_y"]) if info["land_y"] is not None else None
    return frames, info


def jump_clearance(sk, clip_dir, rail_half=0.03):
    """Franchissement de l'obstacle (0,70 m) dans l'enchaînement simulé : marge verticale minimale (mm) des
    points du mannequin et des soles au-dessus de la barre, pour les points situés à ±`rail_half` (+ leur
    rayon implicite) de l'axe de la barre ; plus la pénétration du sol des soles pendant tout l'enchaînement
    (fondus compris)."""
    from .checks import world_from_local
    from .skeleton import LIMBS, body_sample_points, transform_points
    frames, info = jump_sequence(clip_dir)
    L = np.stack([f["local"] for f in frames])
    W = world_from_local(sk, L)
    off = np.stack([[0.0, f["y"], f["z"]] for f in frames])
    js, ps, _ = body_sample_points(sk, n_per=48)
    P = transform_points(W, js, ps) + off[:, None, :]
    S = np.concatenate([sk.sole_world(W, l) for l in LIMBS], axis=1) + off[:, None, :]
    names = np.array(sk.names)[js]
    keep = ~np.char.startswith(names, "tail_")       # crins de queue : souples (physique au runtime), exclus
    P, names = P[:, keep], names[keep]
    fy = info["fence_y"]
    best = (np.inf, None, None)
    for pts, lab in ((P, names), (S, None)):
        near = np.abs(pts[..., 1] - fy) < rail_half
        if near.any():
            dz = np.where(near, pts[..., 2] - OBSTACLE_H, np.inf)
            k = np.unravel_index(np.argmin(dz), dz.shape)
            if dz[k] < best[0]:
                best = (float(dz[k]), int(k[0]), str(lab[k[1]]) if lab is not None else "sole")
    sole_min = float(S[..., 2].min())
    kf = int(np.argmin(S[..., 2].min(axis=1)))
    return {"sequence_sole_min_frame": kf, "sequence_sole_min_label": frames[kf]["label"],"obstacle_m": OBSTACLE_H, "entity_apex_m": round(info["apex_m"], 3), "flight_s": round(info["flight_s"], 3),
            "clearance_mm": round(best[0] * 1000, 1), "clearance_frame": best[1], "clearance_part": best[2],
            "sequence_sole_min_z_mm": round(sole_min * 1000, 1), "frames": len(frames),
            "note": "crins de queue exclus ; soles pendant les fondus simulés (nlerp) inclus"}
