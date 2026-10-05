"""Système de poses-clés : FK interpolée et lissée + IK des sabots plantés + contrainte de sol.

Une chorégraphie (`Choreo`) décrit :
- des clés `(t, {canal: valeur})` interpolées canal par canal (PCHIP sans dépassement pour les clips non
  bouclés, spline cubique périodique pour les boucles) :
    * `body` : dict(pitch, roll, yaw en degrés — axes monde : tangage + = nez en haut, roulis + = côté
      droit vers le bas, lacet + = vers la gauche —, x, y, z en m, pivot (y, z) du tangage/roulis) ;
    * `<joint>` : flexion X (°) ou triplet (flex X, torsion Y, latéral Z) en degrés (delta / liaison) ;
      pour les postérieurs en FK, le jarret suit le grasset (appareil réciproque) sauf clé `hock_slack_*` ;
    * `w:<blend shape>` : poids ;  `snap` : 0..1, poids de « mise au contact » du corps avec le sol ;
- des appuis : position initiale des pinces (`plants0`, décalages / repos), puis des `Step` (lever,
  arc, reposer ailleurs) — les sabots plantés sont résolus par IK (aucun glissement) ;
- des plages FK (`FKSpan`) : le membre suit les angles des clés (plié, en l'air…), avec fondu IK↔FK ;
- éventuellement une vitesse racine constante (saut) : les appuis sont fixes en monde.

Contrainte de sol : après IK, le point le plus bas du mannequin (hors sabots plantés, tête et queue) est
ramené à z ≥ 0 (et à z = 0 quand `snap` = 1, pour un corps couché) en translatant le tronc ; les
membres plantés sont re-résolus (2 itérations).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import mathutil as mu
from .clip_io import FPS, Clip
from .gait import world_aligned_to_local
from .limb_ik import LimbFrameInput, LimbSolver, write_chain
from .skeleton import (LIMB_JOINTS, LIMBS, TAIL, Skeleton, body_sample_points, transform_points)

D = mu.DEG
HIND_CANNON = {"hl": "hind_cannon_l", "hr": "hind_cannon_r"}
GASKIN = {"hl": "gaskin_l", "hr": "gaskin_r"}


@dataclass
class Step:
    limb: str
    t0: float
    t1: float
    to: tuple | None            # (dx, dy) de la pince / repos (repère du clip, à t1) ; None = sur place
    lift: float = 0.07
    carpus: float = 50.0        # flexion du carpe en envol (°) [antérieurs]
    flip: float = 40.0          # rotation du sabot en envol (°, guide)
    pitch_end: float = 0.0      # inclinaison du sabot à la pose (° , + = talons levés)
    yaw_end: float = 0.0
    strike: bool = False        # contact glissant voulu (grattage) : pas d'appui « planté »
    from_fk: bool = False       # le pas part de la position FK du sabot à t0 (sortie d'une plage FK)


@dataclass
class FKSpan:
    limb: str
    t0: float
    t1: float
    blend_in: float = 0.25
    blend_out: float = 0.25


@dataclass
class Choreo:
    name: str
    duration: float
    loop: bool = False
    keys: list = field(default_factory=list)
    plants0: dict = field(default_factory=dict)      # limb -> (dx, dy[, pitch°[, yaw°]])
    steps: list = field(default_factory=list)
    fk: list = field(default_factory=list)
    events: list = field(default_factory=list)
    mask: list | None = None
    notes: str = ""
    root_velocity: float = 0.0                       # m/s vers l'avant (Blender +Y)
    extra_meta: dict = field(default_factory=dict)
    ground_fix: bool = True
    drape_tail: bool = True                           # queue posée sur le sol si elle le traverserait
    fetlock_pref: dict = field(default_factory=dict)  # limb -> ° (préférence boulet des membres plantés)
    # trajectoires libres de pince (non plantées, ex. grattage) : limb -> [(t, (dx, dy, dz, pitch°, carpe°))]
    tracks: dict = field(default_factory=dict)
    # intervalles où une trajectoire libre touche le sol (contact glissant voulu) : limb -> [(t0, t1)]
    track_ground: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------------------------
def _norm_joint_val(v):
    if np.isscalar(v):
        return np.array([float(v), 0.0, 0.0])
    v = np.asarray(v, dtype=np.float64)
    return v


def _channel_series(keys, name, times, loop, period, default=None, kind="pchip"):
    merged = {}
    for t, d in keys:                     # tri par temps ; une clé répétée au même instant : la dernière gagne
        if name in d:
            merged[round(float(t), 6)] = d[name]
    ts = sorted(merged)
    vs = [merged[t] for t in ts]
    if not ts:
        return None if default is None else np.broadcast_to(default, (len(times),) + np.shape(default)).copy()
    vs = np.array(vs, dtype=np.float64)
    if len(ts) == 1:
        return np.broadcast_to(vs[0], (len(times),) + vs.shape[1:]).copy()
    ts = np.array(ts)
    if loop:
        if ts[-1] >= period - 1e-9:      # clé à t = période : identique à t = 0
            keep = ts < period - 1e-9
            ts, vs = ts[keep], vs[keep]
        if len(ts) == 1:
            return np.broadcast_to(vs[0], (len(times),) + vs.shape[1:]).copy()
        return mu.periodic_spline(ts, vs, period)(times)
    return mu.key_spline(ts, vs, kind=kind)(times)


def interpolate_keys(sk: Skeleton, ch: Choreo, times):
    """Renvoie angles (F,N,3) rad (FK de tout le squelette), corps (dict de séries), poids, snap."""
    F = len(times)
    period = ch.duration
    ang = np.zeros((F, sk.N, 3))
    names = set()
    for _, d in ch.keys:
        names |= set(d)
    for jn in sk.names:
        if jn in names and jn not in ("body", "root"):     # `body` = canal de transformation du tronc
            ks = [(t, {jn: _norm_joint_val(d[jn])}) for t, d in ch.keys if jn in d]
            ang[:, sk.idx(jn)] = _channel_series(ks, jn, times, ch.loop, period) * D
    # postérieurs en FK : jarret couplé au grasset (appareil réciproque) + jeu éventuel
    for limb in ("hl", "hr"):
        g = ang[:, sk.idx(GASKIN[limb]), 0]
        slack = _channel_series(ch.keys, f"hock_slack_{limb}", times, ch.loop, period, default=0.0) * D
        ang[:, sk.idx(HIND_CANNON[limb]), 0] = -g + slack
    # corps : chaque clé `body` (dict complet) est convertie en angles + translation EFFECTIVE (rotation autour
    # de son propre pivot) à l'instant de la clé, puis les canaux sont interpolés (pas de pivot entre clés)
    bkeys = []
    hb = sk.head[sk.idx("body")]
    for t, d in ch.keys:
        if "body" not in d:
            continue
        b = dict(pitch=0.0, roll=0.0, yaw=0.0, x=0.0, y=0.0, z=0.0)
        b.update(d["body"])
        tr = np.array([b["x"], b["y"], b["z"]], dtype=float)
        if "pivot" in b and b["pivot"] is not None:
            eul = world_aligned_to_local(sk, "body", b["pitch"] * D, b["roll"] * D, b["yaw"] * D)
            R = mu.euler_to_mat(eul)
            piv = np.array([0.0, b["pivot"][0], b["pivot"][1]])
            dv = hb - piv
            tr = tr + R @ dv - dv
        bkeys.append((t, {"pitch": b["pitch"], "roll": b["roll"], "yaw": b["yaw"],
                          "x": tr[0], "y": tr[1], "z": tr[2]}))
    body = {}
    for c in ("pitch", "roll", "yaw", "x", "y", "z"):
        s_ = _channel_series(bkeys, c, times, ch.loop, period)
        body[c] = np.zeros(F) if s_ is None else s_
    body["pivot"] = None
    weights = {}
    for n in names:
        if n.startswith("w:"):
            weights[n[2:]] = np.clip(_channel_series(ch.keys, n, times, ch.loop, period), 0.0, 1.0)
    snap = _channel_series(ch.keys, "snap", times, ch.loop, period, default=0.0)
    return ang, body, weights, np.clip(snap, 0.0, 1.0)


def body_transform(sk: Skeleton, body, F):
    """Angles locaux (F,3) et translation (F,3) du joint `body` (rotation autour d'un pivot éventuel)."""
    eul = world_aligned_to_local(sk, "body", body["pitch"] * D, body["roll"] * D, body["yaw"] * D)
    R = mu.euler_to_mat(eul)
    h = sk.head[sk.idx("body")]
    t = np.stack([body["x"], body["y"], body["z"]], axis=1)
    if body["pivot"] is not None:
        piv = np.zeros((F, 3))
        piv[:, 1:] = body["pivot"]
        d = h[None, :] - piv
        t = t + np.einsum("fij,fj->fi", R, d) - d
    return eul, t


# ----------------------------------------------------------------------------------------------
def drape_tail(sk: Skeleton, ang, trans, radius=0.06):
    """Contrainte de sol pour la queue : chaque os (de la base vers la pointe) dont l'extrémité passerait
    sous `radius` est tourné (autour de son X local, vers l'arrière) jusqu'à reposer sur le sol."""
    for jn in TAIL:
        j = sk.idx(jn)
        W = sk.fk(sk.basis_from_angles(ang, trans))
        L = sk.lengths[j]
        h = W[:, j, :3, 3]
        y = W[:, j, :3, 1]
        z = W[:, j, :3, 2]
        tip = h[:, 2] + L * y[:, 2]
        bad = tip < radius
        if not bad.any():
            continue
        A, Bc, C = L * y[:, 2], L * z[:, 2], radius - h[:, 2]
        Rn = np.hypot(A, Bc)
        phi = np.arctan2(Bc, A)
        ok = np.abs(C) <= Rn
        acs = np.arccos(np.clip(C / np.maximum(Rn, 1e-9), -1, 1))
        d1 = mu.wrap01((phi + acs) / mu.TAU + 0.5) * mu.TAU - np.pi
        d2 = mu.wrap01((phi - acs) / mu.TAU + 0.5) * mu.TAU - np.pi
        # choisir la rotation qui envoie l'extrémité vers l'ARRIÈRE (y monde décroissant)
        def back(dl):
            ny = y * np.cos(dl)[:, None] + z * np.sin(dl)[:, None]
            return ny[:, 1]
        delta = np.where(back(d1) < back(d2), d1, d2)
        delta = np.where(ok, delta, 0.0)          # base déjà trop basse : laissé tel quel (signalé par checks)
        ang[bad, j, 0] += delta[bad]
    return ang


def lift_head(sk: Skeleton, ang, trans, js, ps, clearance=0.005):
    """Contrainte de sol pour l'encolure et la tête : si un point du mannequin de la tête/encolure passe
    sous le sol, on fait pivoter neck_01/neck_02 (flexion X) du plus petit angle qui le remet au-dessus
    (recherche sur une grille, puis lissage temporel)."""
    names = np.array(sk.names)[js]
    sel = np.isin(names, ["head", "neck_03", "neck_04", "neck_05", "ear_l", "ear_r"])
    jsel, psel = js[sel], ps[sel]
    W = sk.fk(sk.basis_from_angles(ang, trans))
    zmin = transform_points(W, jsel, psel)[..., 2].min(axis=1)
    bad = np.where(zmin < 0.0)[0]
    if len(bad) == 0:
        return ang, np.zeros(len(ang))
    grid = np.deg2rad(np.concatenate([np.arange(-60, 61, 3)]))
    n1, n2 = sk.idx("neck_01"), sk.idx("neck_02")
    delta = np.zeros(len(ang))
    for f in bad:
        A = np.repeat(ang[f:f + 1], len(grid), axis=0)
        A[:, n1, 0] += grid * 0.6
        A[:, n2, 0] += grid * 0.4
        Tr = np.repeat(trans[f:f + 1], len(grid), axis=0)
        Wg = sk.fk(sk.basis_from_angles(A, Tr))
        z = transform_points(Wg, jsel, psel)[..., 2].min(axis=1)
        ok = np.where(z >= clearance)[0]
        delta[f] = grid[ok[np.argmin(np.abs(grid[ok]))]] if len(ok) else grid[np.argmax(z)]
    # lissage : on garde l'enveloppe (même signe) pour ne pas réintroduire de pénétration
    from scipy.ndimage import maximum_filter1d, minimum_filter1d
    pos = maximum_filter1d(np.maximum(delta, 0), 5)
    neg = minimum_filter1d(np.minimum(delta, 0), 5)
    d = mu.lin_smooth(pos, 1.5) + mu.lin_smooth(neg, 1.5)
    ang[:, n1, 0] += d * 0.6
    ang[:, n2, 0] += d * 0.4
    return ang, d


def lift_blending_limbs(sk: Skeleton, ang, trans, w_ik, planted):
    """Pendant un fondu IK↔FK, l'interpolation d'angles peut faire passer le sabot sous le sol : on ajoute
    alors juste assez de flexion du carpe (antérieur) ou du grasset + jarret couplés (postérieur) pour que
    la sole reste au-dessus du sol (recherche sur une grille, image par image)."""
    for l in LIMBS:
        blending = (w_ik[l] > 1e-3) & (w_ik[l] < 0.999)
        frames = np.where(blending)[0]
        if len(frames) == 0:
            continue
        W = sk.fk(sk.basis_from_angles(ang[frames], trans[frames]))
        zmin = sk.sole_world(W, l)[..., 2].min(axis=1)
        jn = f"front_cannon_{l[1]}" if l.startswith("f") else f"gaskin_{l[1]}"
        j = sk.idx(jn)
        hc = sk.idx(f"hind_cannon_{l[1]}")
        for k, f in enumerate(frames):
            if zmin[k] >= 0.0:
                continue
            for extra in np.deg2rad(np.arange(3, 91, 3)):
                A = ang[f:f + 1].copy()
                A[0, j, 0] -= extra
                if l.startswith("h"):
                    A[0, hc, 0] += extra
                z = sk.sole_world(sk.fk(sk.basis_from_angles(A, trans[f:f + 1])), l)[0, :, 2].min()
                if z >= 0.0:
                    break
            ang[f] = A[0]
    return ang


def _fk_weight(ch: Choreo, limb, times):
    """Poids IK (1) / FK (0) d'un membre : passage IK→FK sur [t0, t0+blend_in], FK→IK sur [t1, t1+blend_out]."""
    w = np.ones(len(times))
    for sp in ch.fk:
        if sp.limb != limb:
            continue
        a_in = np.zeros(len(times)) if sp.t0 <= 1e-9 else 1.0 - mu.smootherstep((times - sp.t0) / max(sp.blend_in, 1e-6))
        a_out = np.zeros(len(times)) if sp.t1 >= ch.duration - 1e-9 else \
            mu.smootherstep((times - sp.t1) / max(sp.blend_out, 1e-6))
        w = np.minimum(w, np.maximum(a_in, a_out))
    return w


def hoof_targets(sk: Skeleton, ch: Choreo, limb, times, fk_start=None):
    """Cibles de sole (pince, talon, mamelles) dans le repère du clip pour un membre + états."""
    F = len(times)
    rest = sk.rest_sole_world(limb)
    toe0 = rest[0]
    offs = rest - rest[0]
    p0 = ch.plants0.get(limb, (0.0, 0.0))
    p0 = tuple(p0) + (0.0,) * (4 - len(p0))
    cur = np.array([toe0[0] + p0[0], toe0[1] + p0[1], 0.0])
    cur_pitch, cur_yaw = p0[2] * D, p0[3] * D
    # positions « monde » (sans vitesse racine) par image
    toe = np.repeat(cur[None], F, axis=0)
    pitch = np.full(F, cur_pitch)
    yaw = np.full(F, cur_yaw)
    w_rot = np.ones(F)
    planted = np.ones(F, dtype=bool)
    carpus = np.full(F, 2.0 * D) if limb.startswith("f") else np.zeros(F)
    coffin = np.zeros(F)
    fet = np.zeros(F)
    v = ch.root_velocity
    steps = sorted([s for s in ch.steps if s.limb == limb], key=lambda s: s.t0)
    # convention : `to` est donné dans le repère du clip AU MOMENT DU POSER ; en monde = + v·t1
    cur_w = cur.copy()                                 # position monde (t = 0 : clip = monde)
    seg_start = 0.0
    for st in steps:
        a = cur_w
        fk_c = fk_f = None
        if st.from_fk and fk_start is not None and (limb, st.t0) in fk_start:
            a_toe, a_pitch, fk_c, fk_f = fk_start[(limb, st.t0)]
            a = np.array([a_toe[0], a_toe[1] + v * st.t0, max(a_toe[2], 0.0)])
            cur_pitch = a_pitch
        if st.to is None:      # rester sur place (xy de départ), descendre au sol
            b = np.array([a[0], a[1] + v * (st.t1 - st.t0), 0.0])
        else:
            b = np.array([toe0[0] + st.to[0], toe0[1] + st.to[1] + v * st.t1, 0.0])
        m = (times >= st.t0) & (times <= st.t1)
        after = times > st.t1
        s = np.clip((times[m] - st.t0) / (st.t1 - st.t0), 0, 1)
        hz = mu.smoothstep(s)
        toe[m] = a + (b - a) * hz[:, None]
        toe[m, 2] = a[2] * (1.0 - mu.smootherstep(s)) + st.lift * mu.bump(s, 0.45)
        p_a, p_b = cur_pitch, st.pitch_end * D
        pitch[m] = p_a + (p_b - p_a) * mu.smootherstep(s) + st.flip * D * mu.bump(s, 0.40)
        yaw[m] = cur_yaw + (st.yaw_end * D - cur_yaw) * mu.smootherstep(s)
        w_rot[m] = 1.0 - 0.95 * mu.bump(s, 0.5, sharp=0.5)
        planted[m] = False
        if limb.startswith("f"):
            carpus[m] = 2.0 * D - (st.carpus + 2.0) * D * mu.bump(s, 0.42)
        coffin[m] = -20 * D * mu.bump(s, 0.45)
        fet[m] = -30 * D * mu.bump(s, 0.4) * (st.lift / 0.07)
        if fk_c is not None:
            # sortie de pliage : carpe et boulet partent de leurs valeurs FK et se déplient pendant le pas
            e = mu.smootherstep(np.clip(s / 0.85, 0, 1))
            if limb.startswith("f"):
                carpus[m] = fk_c * (1 - e) + 2.0 * D * e
            fet[m] = fk_f * (1 - e)
        toe[after] = b
        pitch[after] = p_b
        yaw[after] = st.yaw_end * D
        cur_w, cur_pitch, cur_yaw = b, p_b, st.yaw_end * D
        if st.strike:
            planted[m] = False
    # canaux de clés par membre : bascule du sabot autour de la pince, flexion imposée du carpe, préférence
    # de boulet (agenouillement, relever…)
    hp = _channel_series(ch.keys, f"hoofpitch_{limb}", times, ch.loop, ch.duration)
    if hp is not None:
        pitch = pitch + hp * D
    cp = _channel_series(ch.keys, f"carpus_{limb}", times, ch.loop, ch.duration)
    if cp is not None and limb.startswith("f"):
        carpus = carpus - cp * D
    hw = _channel_series(ch.keys, f"hoofw_{limb}", times, ch.loop, ch.duration)
    free_rot = np.zeros(F, dtype=bool)
    if hw is not None:
        hw = np.clip(hw, 0.0, 1.0)
        w_rot = np.where(planted, np.minimum(w_rot, np.maximum(hw, 1e-4)), w_rot)
        free_rot = planted & (hw < 0.99)
    fp = _channel_series(ch.keys, f"fetpref_{limb}", times, ch.loop, ch.duration)
    if fp is not None:
        fet = fet + fp * D
    if limb in ch.tracks:
        tk = ch.tracks[limb]
        ts = np.array([k[0] for k in tk])
        vs = np.array([k[1] for k in tk], dtype=float)
        if ch.loop:
            ser = mu.periodic_spline(ts[ts < ch.duration - 1e-9], vs[ts < ch.duration - 1e-9], ch.duration)(times)
        else:
            ser = mu.key_spline(ts, vs)(times)
        toe = np.stack([toe0[0] + ser[:, 0], toe0[1] + ser[:, 1], np.maximum(ser[:, 2], 0.0)], axis=1)
        pitch = ser[:, 3] * D
        planted[:] = False
        w_rot = np.full(F, 0.6)
        if limb.startswith("f"):
            carpus = 2.0 * D - ser[:, 4] * D
        fet = -0.5 * ser[:, 4] * D
        coffin = -0.25 * ser[:, 4] * D
    # plantés : vitesse racine -> position dans le repère du clip
    toe_c = toe.copy()
    toe_c[:, 1] -= v * times
    # rotation de la sole : lacet puis bascule autour de la pince
    Ryaw = mu.rz(yaw)
    Rp = mu.rx(-pitch)
    sole = toe_c[:, None, :] + np.einsum("fij,fjk,pk->fpi", Ryaw, Rp, offs)
    return dict(sole=sole, planted=planted, w_rot=w_rot, carpus=carpus, coffin=coffin, fet=fet, free_rot=free_rot)


def build_choreo(sk: Skeleton, ch: Choreo, verbose=False) -> Clip:
    F = int(round(ch.duration * FPS)) + (0 if ch.loop else 1)
    times = np.arange(F) / FPS
    ang, body, weights, snap = interpolate_keys(sk, ch, times)
    eul, tb = body_transform(sk, body, F)
    bj = sk.idx("body")
    ang[:, bj] = eul
    trans = np.zeros((F, sk.N, 3))
    trans[:, bj] = tb
    fk_ang = ang.copy()
    w_ik = {l: _fk_weight(ch, l, times) for l in LIMBS}
    # départs de pas depuis la pose FK (sortie de plage FK) : position de pince et bascule du sabot en FK
    fk_start = {}
    if any(st.from_fk for st in ch.steps):
        W0 = sk.fk(sk.basis_from_angles(fk_ang, trans))
        for st in ch.steps:
            if st.from_fk:
                f0 = int(round(st.t0 * FPS))
                sole = sk.sole_world(W0[f0:f0 + 1], st.limb)[0]
                vth = sole[5] - sole[0]
                pitch0 = np.arctan2(vth[2], -vth[1]) / D
                pre = "front" if st.limb.startswith("f") else "hind"
                sd = st.limb[1]
                fc = fk_ang[f0, sk.idx(f"front_cannon_{sd}"), 0] if pre == "front" else 0.0
                ff = fk_ang[f0, sk.idx(f"{pre}_pastern_{sd}"), 0]
                fk_start[(st.limb, st.t0)] = (sole[0], pitch0, fc, ff)
    targets = {l: hoof_targets(sk, ch, l, times, fk_start) for l in LIMBS}
    solvers = {l: LimbSolver(sk, l) for l in LIMBS}
    js, ps, distal = body_sample_points(sk, n_per=48)       # mêmes points que checks.py
    excl = {sk.idx(n) for n in ["head", "ear_l", "ear_r"] + TAIL + [f"neck_{i:02d}" for i in (4, 5)]}
    use_pts = np.array([j not in excl for j in js])
    names_u = np.array(sk.names)[js[use_pts]]
    limb_pts = {l: np.isin(names_u, LIMB_JOINTS[l]) for l in LIMBS}
    dz = np.zeros(F)
    errs = {l: np.zeros(F) for l in LIMBS}
    n_iter = 4
    for it in range(n_iter):
        trans[:, bj, 2] = tb[:, 2] + dz
        W = sk.fk(sk.basis_from_angles(ang, trans))
        for l in LIMBS:
            need = w_ik[l] > 1e-4
            tg = targets[l]
            x_prev = None
            sol = np.zeros((F, len(LIMB_JOINTS[l]), 3))
            order = list(range(F)) * (2 if ch.loop else 1)
            jl = [sk.idx(n) for n in LIMB_JOINTS[l]]
            for n_it, f in enumerate(order):
                if not need[f]:
                    x_prev = None
                    continue
                if x_prev is None:
                    # amorçage sur la pose FK courante du membre (sortie de pliage, etc.)
                    x_prev = solvers[l].vars_from_chain(fk_ang[f, jl])
                inp = LimbFrameInput(
                    toe=tg["sole"][f, 0], heel=tg["sole"][f, 5], quarters=tg["sole"][f, 3:5],
                    w_rot=float(tg["w_rot"][f]), carpus=float(tg["carpus"][f]),
                    fetlock_pref=float(tg["fet"][f] + ch.fetlock_pref.get(l, 0.0) * D),
                    coffin_pref=float(tg["coffin"][f]),
                    w_coffin=0.15 + 0.6 * (1.0 - float(tg["w_rot"][f])),
                    ground_clear=0.007 if not tg["planted"][f] else (0.0 if tg["free_rot"][f] else -1.0),
                    w_ground=6000.0 if (not tg["planted"][f] or tg["free_rot"][f]) else 0.0)
                x, chain, info = solvers[l].solve(W[f, solvers[l].parent], inp, x0=x_prev)
                x_prev = x
                sol[f] = chain
                errs[l][f] = info["err_toe"] if tg["planted"][f] else 0.0
            # fondu IK / FK
            for k, jn in enumerate(LIMB_JOINTS[l]):
                j = sk.idx(jn)
                ang[:, j] = w_ik[l][:, None] * sol[:, k] + (1 - w_ik[l][:, None]) * fk_ang[:, j]
        if not ch.ground_fix or it == n_iter - 1:
            break
        # contrainte de sol sur le mannequin (hors sabots plantés : leurs points de sole sont à z = 0)
        W = sk.fk(sk.basis_from_angles(ang, trans))
        P = transform_points(W, js[use_pts], ps[use_pts])
        Pz = P[..., 2].copy()
        for l in LIMBS:
            # un membre en fondu IK↔FK ou en train de faire un pas (IK, non planté) ne soulève pas le tronc :
            # sa propre IK a une pénalité de sol
            blending = ((w_ik[l] >= 1e-3) & (w_ik[l] <= 0.999)) | ((w_ik[l] > 0.999) & ~targets[l]["planted"])
            Pz[np.ix_(blending, limb_pts[l])] = np.inf
        zmin = Pz.min(axis=1)
        for l in LIMBS:
            # seuls les membres entièrement en FK (ou non plantés) contraignent la hauteur du tronc ; un membre
            # en cours de fondu IK↔FK n'impose rien (sinon le tronc serait hissé pendant la transition)
            free = w_ik[l] < 1e-3
            sole = sk.sole_world(W, l)[..., 2].min(axis=1)
            zmin = np.where(free, np.minimum(zmin, sole), zmin)
        zt = zmin - 0.002                                      # marge de 2 mm
        corr = np.where(zt < 0.0, -zt, 0.0) + snap * np.where(zt > 0.0, -zt, 0.0)
        if np.abs(corr).max() < 2e-4:
            break
        dz = dz + corr
    trans[:, bj, 2] = tb[:, 2] + dz
    head_corr = np.zeros(F)
    if ch.ground_fix:
        ang = lift_blending_limbs(sk, ang, trans, w_ik, {l: targets[l]["planted"] for l in LIMBS})
        ang, head_corr = lift_head(sk, ang, trans, js, ps)
    if ch.drape_tail:
        ang = drape_tail(sk, ang, trans)
    W = sk.fk(sk.basis_from_angles(ang, trans))
    contacts = {}
    for l in LIMBS:
        contacts[l] = (w_ik[l] > 0.999) & targets[l]["planted"]
    clip = Clip(name=ch.name, loop=ch.loop, ang=ang, trans=trans, weights=weights,
                root_velocity_b=(0.0, ch.root_velocity, 0.0), mask=ch.mask, events=list(ch.events),
                notes=ch.notes)
    clip.contacts = contacts
    clip.extra_meta.update(ch.extra_meta)
    clip.diag = {"ik_err": errs, "dz": dz, "w_ik": w_ik, "head_corr": head_corr}
    if verbose:
        e = max(errs[l].max() for l in LIMBS) * 1000
        print(f"[{ch.name}] F={F} IK planted err max {e:.2f} mm, ground corr max {np.abs(dz).max() * 100:.1f} cm")
    return clip
