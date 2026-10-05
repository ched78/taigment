"""Générateurs des 8 pièces de crins (SPEC §6) : mane_natural, mane_braided, mane_roached, forelock_natural,
forelock_braided, tail_natural, tail_braided, feathers.

Chaque générateur renvoie (PartBuilder, W (n_sommets × 70), extra) — les poids sont déjà limités à 4 influences
et normalisés. Longueurs, volumes, nombres de cartes : approximations artistiques [A] calées sur
Docs/research/anatomy.md §2.5 (crinière 20–40 cm, toupet 20–30 cm, queue jusqu'au jarret pour un Welsh B /
Connemara) et Docs/research/tack.md §8.2 (nattes boutons en nombre impair, 9–17 ; toupet natté et replié).
"""
from __future__ import annotations

import numpy as np

from . import hair_surface as hs
from . import hair_texture as htex
from .hair_geom import (JIDX, JOINTS, NJ, PartBuilder, chain_weights, cut_at_length, grow_guide,
                        limit_influences, nrm, perp, resample, smoothstep, tangents)

MANE_CHAIN = [f"mane_{i:02d}" for i in range(1, 7)]
NECK_CHAIN = [f"neck_{i:02d}" for i in range(1, 7)]
TAIL_CHAIN = [f"tail_{i:02d}" for i in range(1, 11)]
FORELOCK_CHAIN = ["forelock_01", "forelock_02", "forelock_03"]

_VPAD = 3.0 / htex.SIZE      # marge en v (3 px) : évite le débordement du filtrage sur la région voisine


def _inset_v(rect):
    u0, v0, u1, v1 = rect
    return (u0, v0 + _VPAD, u1, v1 - _VPAD)


CARD = {k: _inset_v(htex.REGIONS[v]) for k, v in htex.CARD_VARIANTS.items()}
R_BASE = _inset_v(htex.REGIONS["base"])
R_BRAID = _inset_v(htex.REGIONS["braid"])
R_BRUSH = _inset_v(htex.REGIONS["brush"])
R_WISP = _inset_v(htex.REGIONS["wisp"])

ROOT_DEPTH = 0.0025          # pénétration contrôlée des racines dans la peau (m) [I]


# ----------------------------------------------------------------------------------------------
# Aides
# ----------------------------------------------------------------------------------------------
def tri_wave(x):
    """Onde triangle 0…1…0 de période 2 (UV en miroir, sans couture)."""
    return 1.0 - np.abs((np.asarray(x) % 2.0) - 1.0)


def crest_frame(crest, t):
    P, T, N = crest["points"], crest["tangents"], crest["normals"]
    x = float(np.clip(t, 0, 1)) * (len(P) - 1)
    i = int(min(np.floor(x), len(P) - 2))
    f = x - i
    p = P[i] * (1 - f) + P[i + 1] * f
    tg = nrm(T[i] * (1 - f) + T[i + 1] * f)
    n = nrm(N[i] * (1 - f) + N[i + 1] * f)
    r = nrm(np.cross(tg, n))
    if r[0] < 0:
        r = -r
    return p, tg, n, r


def surface_normals(surf, P):
    return np.array([surf.nearest(p)[1] for p in P])


def root_weights(surf, J, roots, fallback_chain):
    """Poids de peau du corps aux racines (transfert depuis le corps) ; repli : chaîne d'os."""
    out = np.zeros((len(roots), NJ))
    for i, r in enumerate(roots):
        w = surf.skin_weights_at(r)
        if w is None:
            w = chain_weights(r[None], J, fallback_chain)[0]
        out[i] = w
    return out


def mix_weights(Wa, Wb, alpha):
    a = np.asarray(alpha, np.float64)[:, None]
    return Wa * (1 - a) + Wb * a


def unique_roots(ROOT):
    """Indexe les racines distinctes pour ne transférer qu'une fois par mèche."""
    key = np.round(ROOT * 1e6).astype(np.int64)
    _u, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return ROOT[first], inv.ravel()


def neck_fallback():
    return ["spine_03"] + NECK_CHAIN + ["head"]


def interp_profile(ctrl, t):
    ctrl = np.asarray(ctrl, np.float64)
    return float(np.interp(t, ctrl[:, 0], ctrl[:, 1]))


# ----------------------------------------------------------------------------------------------
# Crinière naturelle
# ----------------------------------------------------------------------------------------------
MANE_LENGTH = [(0.0, 0.04), (0.03, 0.10), (0.07, 0.17), (0.15, 0.25), (0.35, 0.32), (0.65, 0.30), (0.88, 0.23), (0.96, 0.17),
               (1.0, 0.11)]   # [A]


def end_taper(t, a=0.10, b=0.12):
    """0 aux extrémités de la crête (garrot, nuque) -> 1 au milieu : les crins s'y couchent davantage."""
    return float(smoothstep(0.0, a, t) * smoothstep(1.0, 1.0 - b, t))


def mane_natural(surf, J, crest, seed=11):
    rng = np.random.default_rng(seed)
    b = PartBuilder("mane_natural")
    Lc = crest["length"]

    # --- couche de base opaque (nappe continue le long de la crête) ---
    C, NS = 54, 14
    ts = np.linspace(0.004, 0.996, C)
    grid = np.zeros((NS + 1, C, 3))
    roots = np.zeros((C, 3))
    for c, t in enumerate(ts):
        p, tg, n, r = crest_frame(crest, t)
        e = end_taper(t)
        q = surf.nearest(p + r * (-0.012 * (0.3 + 0.7 * e)))[0]
        roots[c] = q
        L = 0.70 * interp_profile(MANE_LENGTH, t)
        d0 = _poll_bias(nrm(n * 0.75 * (0.15 + 0.85 * e) + r * 0.65 - tg * 0.10), t, n, r, tg)
        grid[:, c] = grow_guide(surf, q, d0, L, NS, lambda s: 0.003 + 0.005 * s, bend=30.0)
    UVg = np.zeros((NS + 1, C, 2))
    u0, v0, u1, v1 = R_BASE
    uu = tri_wave(ts * Lc / 0.075)
    for rr in range(NS + 1):
        s = rr / NS
        UVg[rr, :, 0] = u0 + 0.004 + (u1 - u0 - 0.008) * uu
        UVg[rr, :, 1] = v1 - s * (v1 - v0) * 0.98
    Sg = np.repeat(np.linspace(0, 1, NS + 1)[:, None], C, 1)
    FAC = np.array([[surf.nearest(grid[rr, c])[1] for c in range(C)] for rr in range(NS + 1)])
    b.add_grid(grid, UVg, Sg, roots, FAC, tag=0, aux=ts)

    # --- cartes : couche interne puis externe, et quelques mèches qui tombent à gauche ---
    layers = [
        dict(tag=1, n=66, width=(0.040, 0.052), xoff=(-0.010, 0.004), up=(0.75, 0.95), side=(0.50, 0.70),
             off=lambda s: 0.008 + 0.012 * s, lenf=(0.78, 1.04), nseg=12, nacross=2, arch=0.0,
             variants=["dense", "clumped", "short", "dense"], lift=0.006, sway=0.006),
        dict(tag=2, n=62, width=(0.036, 0.048), xoff=(-0.010, 0.002), up=(0.50, 0.72), side=(0.62, 0.85),
             off=lambda s: 0.012 + 0.016 * s, lenf=(0.70, 1.12), nseg=12, nacross=3, arch=0.2,
             variants=["clumped", "wispy", "split", "pointed", "clumped"], lift=0.010, sway=0.012, bend=(30, 38)),
    ]
    for lay in layers:
        n = lay["n"]
        tt = (np.arange(n) + rng.uniform(0.1, 0.9, n)) / n          # échantillonnage stratifié
        for k in range(n):
            t = float(np.clip(tt[k], 0.015, 0.975))
            p, tg, nn, r = crest_frame(crest, t)
            e = end_taper(t)
            q = surf.nearest(p + r * rng.uniform(*lay["xoff"]) * (0.3 + 0.7 * e))[0]
            L = interp_profile(MANE_LENGTH, t) * rng.uniform(*lay["lenf"])
            d0 = nrm(nn * rng.uniform(*lay["up"]) * (0.15 + 0.85 * e) + r * rng.uniform(*lay["side"])
                     + tg * rng.uniform(-0.18, 0.08))
            d0 = _poll_bias(d0, t, nn, r, tg)
            off = lay["off"]
            P = grow_guide(surf, q, d0, L, lay["nseg"], lambda s, off=off, e=e: off(s) * (0.45 + 0.55 * e),
                           bend=rng.uniform(*lay.get("bend", (22, 30))))
            _post_card(surf, b, P, tg, rng, lay, aux=t)
    A = b.arrays()
    W = _mane_weights(surf, J, crest, A, tip_mane=0.85)
    return b, W, {}


def _poll_bias(d0, t, n, r, tg, t0=0.78):
    """Près de la nuque la normale de crête bascule vers l'avant : les crins partent alors davantage sur le côté
    et vers l'arrière (sinon ils se dressent au-dessus de la tête)."""
    k = smoothstep(t0, 1.0, t)
    return nrm(d0 * (1 - k) + nrm(n * 0.40 + r * 0.85 - tg * 0.35) * k)


def _post_card(surf, b, P, across, rng, lay, aux=0.0, facing=None):
    """Ajoute ondulation latérale, décollement des pointes, puis la carte (ruban)."""
    N = len(P)
    s = np.linspace(0, 1, N)
    T = tangents(P)
    F = surface_normals(surf, P) if facing is None else facing
    Wd = perp(np.broadcast_to(across, P.shape), T)
    ph = rng.uniform(0, 2 * np.pi)
    sway = lay.get("sway", 0.0) * np.sin(ph + s * rng.uniform(2.0, 4.5)) * s
    lift = lay.get("lift", 0.0) * rng.uniform(0.3, 1.0) * s ** 2
    P = P + Wd * sway[:, None] + F * lift[:, None]
    w0 = rng.uniform(*lay["width"])
    width = w0 * (1.0 - 0.35 * s ** 1.5)
    variant = lay["variants"][rng.integers(len(lay["variants"]))]
    rect = CARD[variant]
    flip = rng.uniform() < 0.5
    b.add_ribbon(P, F, width, rect, across_dir=np.broadcast_to(across, P.shape), n_across=lay["nacross"],
                 arch=lay.get("arch", 0.0), tag=lay["tag"], aux=aux,
                 u_range=(1.0, 0.0) if flip else (0.0, 1.0))


def neck_to_mane(W):
    """Transfère la part de chaque neck_k vers mane_k (enfant direct de neck_k) : à l'identité des mane_*,
    la déformation est inchangée ; les ressorts du runtime sur mane_* ajoutent le balancement."""
    W = W.copy()
    for k in range(1, 7):
        a, b = JIDX[f"neck_{k:02d}"], JIDX[f"mane_{k:02d}"]
        W[:, b] += W[:, a]
        W[:, a] = 0.0
    return W


def skin_weights_per_vertex(surf, J, P, fallback_chain):
    """Poids de peau du corps au point de surface le plus proche de chaque sommet (transfert)."""
    return root_weights(surf, J, P, fallback_chain)


def _mane_weights(surf, J, crest, A, tip_mane=0.85, rigid_tags=()):
    """Poids de la crinière : poids de peau du corps transférés au plus proche point de chaque sommet (les
    crins suivent la peau qu'ils recouvrent), puis la part de neck_k passe progressivement (racine -> pointe)
    à mane_k pour le balancement secondaire. Racines (s = 0) : 100 % peau."""
    Ws = skin_weights_per_vertex(surf, J, A["V"], neck_fallback())
    Wm = neck_to_mane(Ws)
    alpha = tip_mane * np.clip(A["S"], 0, 1) ** 1.3
    for tg in rigid_tags:
        alpha[A["TAG"] == tg] = 0.0
    return limit_influences(mix_weights(Ws, Wm, alpha))


# ----------------------------------------------------------------------------------------------
# Crinière rasée courte (brosse)
# ----------------------------------------------------------------------------------------------
ROACH_HEIGHT = [(0.0, 0.012), (0.08, 0.035), (0.3, 0.05), (0.75, 0.05), (0.93, 0.035), (1.0, 0.018)]  # [A]


def mane_roached(surf, J, crest, seed=13):
    rng = np.random.default_rng(seed)
    b = PartBuilder("mane_roached")
    Lc = crest["length"]
    Ncs = 64
    ts = np.linspace(0.0, 1.0, Ncs)
    frames = [crest_frame(crest, t) for t in ts]
    u0, v0, u1, v1 = R_BRUSH
    uu = tri_wave(ts * Lc / 0.05)
    # --- âme opaque : arche (U renversé) le long de la crête ---
    NA = 9
    al = np.linspace(-np.pi / 2, np.pi / 2, NA)
    grid = np.zeros((NA, Ncs, 3))
    FAC = np.zeros((NA, Ncs, 3))
    UVg = np.zeros((NA, Ncs, 2))
    roots = np.zeros((Ncs, 3))
    for c, (p, tg, n, r) in enumerate(frames):
        h = interp_profile(ROACH_HEIGHT, ts[c]) * 0.36
        w = 0.013 * (0.6 + 0.4 * smoothstep(0, 0.1, ts[c]) * smoothstep(1.0, 0.9, ts[c]))
        roots[c] = p
        for a_i, a in enumerate(al):
            q = p + r * (w / 2) * np.sin(a) + n * h * np.cos(a)
            if abs(a) > 1.4:      # pieds de l'arche : sur la peau
                q = surf.nearest(q)[0]
            grid[a_i, c] = q
            FAC[a_i, c] = nrm(n * np.cos(a) + r * np.sin(a) * 1.2)
            UVg[a_i, c] = (u0 + 0.004 + (u1 - u0 - 0.008) * uu[c], v1 - (v1 - v0) * 0.18 * np.cos(a))
    Sg = np.repeat(np.cos(al)[:, None] * 0.18, Ncs, 1)
    b.add_grid(grid, UVg, Sg, roots, FAC, tag=0, aux=ts, root_rows=(0, NA - 1))
    # --- ailettes alpha (silhouette en brosse) : 3 rangées ---
    for row, (lean, hf, phase) in enumerate(((0.0, 1.05, 0.0), (-0.20, 0.97, 0.37), (0.20, 0.97, 0.71),
                                              (-0.42, 0.85, 0.19), (0.42, 0.85, 0.53))):
        NR = 3
        g = np.zeros((NR, Ncs, 3))
        fac = np.zeros((NR, Ncs, 3))
        uvg = np.zeros((NR, Ncs, 2))
        rts = np.zeros((Ncs, 3))
        uw = tri_wave(ts * Lc / (0.035 + 0.006 * row) + phase)
        for c, (p, tg, n, r) in enumerate(frames):
            h = interp_profile(ROACH_HEIGHT, ts[c]) * hf * (1 + 0.06 * np.sin(ts[c] * 37 + row))
            dirv = nrm(n * np.cos(lean) + r * np.sin(lean) - tg * 0.12)
            base = surf.nearest(p + r * 0.010 * np.sin(lean))[0]
            rts[c] = base
            vs = 0.0 if lean == 0.0 else 0.42      # ailettes latérales : sans la partie opaque des racines
            side = r if lean >= 0.0 else -r
            for k in range(NR):
                s = k / (NR - 1)
                g[k, c] = base + dirv * h * s
                # normale de volume franchement latérale (enroulement cohérent des quads de l'ailette)
                fac[k, c] = nrm(n * 0.5 + side * 1.0)
                uvg[k, c] = (u0 + 0.004 + (u1 - u0 - 0.008) * uw[c], v1 - (v1 - v0) * (vs + (0.98 - vs) * s))
        Sg2 = np.repeat(np.linspace(0, 1, NR)[:, None], Ncs, 1)
        b.add_grid(g, uvg, Sg2, rts, fac, tag=1 + row, aux=ts)
    A = b.arrays()
    W = _mane_weights(surf, J, crest, A, tip_mane=0.25)
    return b, W, {}


# ----------------------------------------------------------------------------------------------
# Crinière tressée (nattes boutons / « pions »)
# ----------------------------------------------------------------------------------------------
N_BRAIDS = 13   # impair (tack.md §8.2 : 9–17 en dressage, nombre impair, toupet non compté)


def _uv_sphere_braid(b, center, axis_t, axis_n, axis_r, radii, rings=7, segs=12, tag=0, aux=0.0, root=None,
                     u_rect=R_BRAID, embed_below=-0.35):
    """Ellipsoïde dont l'axe polaire suit la crête (T) ; u = tour autour de T (la natte passe par-dessus le
    bouton de gauche à droite), v = position le long de T. Couture en dessous (θ = 0 ≡ 2π, dans la crête).
    Les pôles sont fermés par des éventails de triangles (un seul sommet par pôle). Les sommets du dessous
    (enfoncés dans la crête) sont marqués « encastrés » (ROOTFLAG = 2)."""
    rt, rn, rr = radii
    u0, v0, u1, v1 = u_rect
    root = center if root is None else root
    phis = np.linspace(0.0, np.pi, rings + 2)[1:-1]     # anneaux sans les pôles
    ids = np.zeros((len(phis), segs + 1), int)
    for i, ph in enumerate(phis):
        ct, st = -np.cos(ph), np.sin(ph)
        for j in range(segs + 1):
            th = 2 * np.pi * j / segs                    # 0 = dessous
            dn, dr = -np.cos(th), np.sin(th)
            p = center + axis_t * rt * ct + (axis_n * rn * dn + axis_r * rr * dr) * st
            fac = nrm(axis_t * ct / rt + (axis_n * dn / rn + axis_r * dr / rr) * st)
            uv = (u0 + (u1 - u0) * (0.002 + 0.996 * j / segs), v0 + (v1 - v0) * (0.04 + 0.92 * (i + 1) / (rings + 1)))
            flag = 2 if dn * st < embed_below else 0
            ids[i, j] = b.add_vertex(p, uv, 0.5, root, tag, aux, fac, flag)
    poles = []
    for sgn, vv in ((-1.0, v0 + (v1 - v0) * 0.02), (1.0, v0 + (v1 - v0) * 0.98)):
        poles.append(b.add_vertex(center + axis_t * rt * sgn, (0.5 * (u0 + u1), vv), 0.5, root, tag, aux,
                                  axis_t * sgn, 0))
    start = len(b.F)
    for i in range(len(phis) - 1):
        for j in range(segs):
            b.F.append([ids[i, j], ids[i, j + 1], ids[i + 1, j + 1], ids[i + 1, j]])
    for j in range(segs):
        b.F.append([poles[0], ids[0, j + 1], ids[0, j]])
        b.F.append([poles[1], ids[-1, j], ids[-1, j + 1]])
    _orient_last_faces(b, start)


def mane_braided(surf, J, crest, seed=17):
    rng = np.random.default_rng(seed)
    b = PartBuilder("mane_braided")
    Lc = crest["length"]
    # --- base : crins courts tirés vers les nattes, plaqués sur la crête ---
    C, NS = 54, 6
    ts = np.linspace(0.004, 0.996, C)
    grid = np.zeros((NS + 1, C, 3))
    roots = np.zeros((C, 3))
    for c, t in enumerate(ts):
        p, tg, n, r = crest_frame(crest, t)
        e = end_taper(t, 0.06, 0.06)
        q = surf.nearest(p + r * (-0.013 * (0.4 + 0.6 * e)))[0]
        roots[c] = q
        d0 = nrm(n * 0.45 * e + r * 0.9)
        grid[:, c] = grow_guide(surf, q, d0, 0.050 * (0.35 + 0.65 * e), NS, lambda s: 0.0025 + 0.002 * s, bend=35.0)
    u0, v0, u1, v1 = R_BASE
    uu = tri_wave(ts * Lc / 0.06)
    UVg = np.zeros((NS + 1, C, 2))
    for rr in range(NS + 1):
        UVg[rr, :, 0] = u0 + 0.004 + (u1 - u0 - 0.008) * uu
        UVg[rr, :, 1] = v1 - (rr / NS) * (v1 - v0) * 0.78       # le bas atteint la frange (bord irrégulier)
    Sg = np.repeat(np.linspace(0, 0.3, NS + 1)[:, None], C, 1)
    FAC = np.array([[surf.nearest(grid[rr, c])[1] for c in range(C)] for rr in range(NS + 1)])
    b.add_grid(grid, UVg, Sg, roots, FAC, tag=0, aux=ts)
    # --- boutons ---
    anchors = []
    tb = np.linspace(0.075, 0.935, N_BRAIDS)
    for k, t in enumerate(tb):
        p, tg, n, r = crest_frame(crest, t)
        q, nq = surf.nearest(p)[:2]
        sc = rng.uniform(0.94, 1.06)
        radii = np.array([0.0170, 0.0145, 0.0180]) * sc        # (le long de T, hauteur N, latéral R) [A]
        center = q + nq * (radii[1] * 0.62) + r * 0.004
        # légère rotation aléatoire autour de N
        ang = rng.uniform(-0.12, 0.12)
        tq = nrm(tg * np.cos(ang) + r * np.sin(ang))
        rq = nrm(np.cross(tq, nq))
        if rq[0] < 0:
            rq = -rq
        _uv_sphere_braid(b, center, tq, nq, rq, radii, rings=6, segs=12, tag=10 + k, aux=t, root=q)
        top = center + nq * radii[1]
        anchors.append(dict(index=k, crest_t=float(t), center=center, top=top, normal=nq, tangent=tq, right=rq,
                            radius=float(radii[2]), root=q))
    A = b.arrays()
    # poids : base -> peau sous chaque sommet (+ un soupçon de mane_*) ; boutons rigides sur la peau sous le bouton
    W = _mane_weights(surf, J, crest, A, tip_mane=0.15)
    roots_u, inv = unique_roots(A["ROOT"])
    Wr = limit_influences(root_weights(surf, J, roots_u, neck_fallback()))[inv]
    btn = A["TAG"] >= 10
    W[btn] = Wr[btn]
    for a in anchors:
        w = surf.skin_weights_at(a["root"])
        if w is None:
            w = chain_weights(a["root"][None], J, neck_fallback())[0]
        w = limit_influences(w[None])[0]
        a["weights"] = {JOINTS[j]: float(w[j]) for j in np.nonzero(w)[0]}
        a["joint"] = JOINTS[int(np.argmax(w))]
    return b, W, {"anchors": anchors}


# ----------------------------------------------------------------------------------------------
# Toupet naturel
# ----------------------------------------------------------------------------------------------
def _forelock_roots(surf, J, s_rng, x_rng, n_s, n_x):
    pts = []
    for s in np.linspace(*s_rng, n_s):
        for x in np.linspace(*x_rng, n_x):
            h = hs.head_surface_point(surf, J, s, x)
            if h is not None:
                pts.append((h[0], h[1], s, x))
    return pts


def forelock_natural(surf, J, crest, seed=19):
    rng = np.random.default_rng(seed)
    b = PartBuilder("forelock_natural")
    o, ax, dor, lat = hs.head_frame(J)
    # --- base opaque ---
    C, NS = 13, 10
    xs = np.linspace(-0.021, 0.021, C)
    grid = np.zeros((NS + 1, C, 3))
    roots = np.zeros((C, 3))
    for c, x in enumerate(xs):
        q, n = hs.head_surface_point(surf, J, 0.012, x)
        roots[c] = q
        L = 0.17 * (1.0 - 0.25 * (x / 0.021) ** 2)
        d0 = nrm(ax * 0.65 + dor * 0.70 + lat * x * 5.0)
        grid[:, c] = grow_guide(surf, q, d0, L, NS, lambda s: 0.003 + 0.005 * s, bend=20.0,
                                steer_fn=lambda s, p, d, x=x: lat * x * 0.15 * s)
    u0, v0, u1, v1 = R_BASE
    UVg = np.zeros((NS + 1, C, 2))
    for rr in range(NS + 1):
        UVg[rr, :, 0] = u0 + 0.004 + (u1 - u0 - 0.008) * (xs - xs[0]) / (xs[-1] - xs[0])
        UVg[rr, :, 1] = v1 - (rr / NS) * (v1 - v0) * 0.98
    Sg = np.repeat(np.linspace(0, 1, NS + 1)[:, None], C, 1)
    FAC = np.array([[surf.nearest(grid[rr, c])[1] for c in range(C)] for rr in range(NS + 1)])
    b.add_grid(grid, UVg, Sg, roots, FAC, tag=0)
    # --- cartes ---
    layers = [
        dict(tag=1, n=15, width=(0.024, 0.032), x=(-0.022, 0.022), s=(0.0, 0.03), off=lambda s: 0.007 + 0.009 * s,
             L=(0.20, 0.25), nseg=10, nacross=2, variants=["dense", "clumped", "pointed"], lift=0.004, sway=0.006,
             spread=(0.35, 0.6)),
        dict(tag=2, n=13, width=(0.022, 0.030), x=(-0.024, 0.024), s=(-0.005, 0.025),
             off=lambda s: 0.012 + 0.012 * s, L=(0.19, 0.26), nseg=10, nacross=3, arch=0.3,
             variants=["pointed", "wispy", "clumped", "split"], lift=0.008, sway=0.009, spread=(0.45, 0.8)),
    ]
    for lay in layers:
        xs_ = np.linspace(*lay["x"], lay["n"]) + rng.uniform(-0.002, 0.002, lay["n"])
        for x in xs_:
            h = hs.head_surface_point(surf, J, rng.uniform(*lay["s"]), float(np.clip(x, -0.023, 0.023)))
            if h is None:
                continue
            q, n = h
            L = rng.uniform(*lay["L"]) * (1.0 - 0.2 * (x / 0.024) ** 2)
            d0 = nrm(ax * rng.uniform(0.5, 0.75) + dor * rng.uniform(0.6, 0.8) + lat * x * rng.uniform(4, 7))
            spread = x * rng.uniform(*lay["spread"])
            P = grow_guide(surf, q, d0, L, lay["nseg"], lay["off"], bend=rng.uniform(17, 24),
                           steer_fn=lambda s, p, d, sp=spread: lat * sp * s)
            _post_card(surf, b, P, lat, rng, lay)
    A = b.arrays()
    Ws = skin_weights_per_vertex(surf, J, A["V"], ["head"])
    Wc = chain_weights(A["V"], J, FORELOCK_CHAIN, smooth=0.8)
    alpha = 0.92 * smoothstep(0.0, 0.45, A["S"])
    W = limit_influences(mix_weights(Ws, Wc, alpha))
    return b, W, {}


# ----------------------------------------------------------------------------------------------
# Tubes de natte (toupet tressé, queue tressée)
# ----------------------------------------------------------------------------------------------
def braid_tube(b, C, Fn, radius, sides=8, tag=0, aux=0.0, root=None, s_values=None, tile_len=None):
    """Tube de natte le long de la ligne C (N,3) ; Fn (N,3) : direction « dessus » (opposée à la peau).
    u (région braid) le long de la natte, avec un anneau dupliqué à chaque fin de tuile (couture UV nécessaire) ;
    v autour du tube (couture dessous, contre la peau). Les sommets du dessous sont marqués « encastrés »."""
    C = np.asarray(C, np.float64)
    N = len(C)
    T = tangents(C)
    Up = perp(Fn, T)
    Lat = nrm(np.cross(T, Up))
    rad = np.broadcast_to(np.asarray(radius, np.float64), (N,))
    seg = np.linalg.norm(np.diff(C, axis=0), axis=1)
    arc = np.concatenate([[0.0], np.cumsum(seg)])
    tile = tile_len if tile_len is not None else 12.0 * float(rad.mean())
    u0, v0, u1, v1 = R_BRAID
    s_values = np.linspace(0, 1, N) if s_values is None else s_values
    root = C[0] if root is None else root
    start = len(b.F)
    rings = []              # (indice d'échantillon, liste des sommets)
    prev_tile = 0
    for i in range(N):
        x = arc[i] / tile
        ti = int(np.floor(x))
        fus = []
        if ti > prev_tile and i > 0:
            fus.append(1.0)   # fin de la tuile précédente
            prev_tile = ti
        fus.append(x - ti)
        if i == N - 1 and len(fus) == 2:
            fus = [1.0]       # couture sur le dernier échantillon : pas d'anneau de départ orphelin
        for fu in fus:
            ring = []
            for j in range(sides + 1):
                a = -np.pi + 2 * np.pi * j / sides           # 0 = dessus, ±π = dessous
                dirv = Up[i] * np.cos(a) + Lat[i] * np.sin(a)
                p = C[i] + dirv * rad[i]
                uv = (u0 + (u1 - u0) * (0.002 + 0.996 * fu), v0 + (v1 - v0) * (0.02 + 0.96 * j / sides))
                flag = 2 if abs(a) > 2.2 else 0
                ring.append(b.add_vertex(p, uv, s_values[i], root, tag, aux, dirv, flag))
            rings.append((i, ring))
    for k in range(len(rings) - 1):
        i0, r0 = rings[k]
        i1, r1 = rings[k + 1]
        if i1 == i0:          # paire d'anneaux de couture (même position) : pas de face
            continue
        for j in range(sides):
            b.F.append([r0[j], r1[j], r1[j + 1], r0[j + 1]])
    _orient_last_faces(b, start)
    return rings


def _orient_last_faces(b, start):
    V = np.array(b.V)
    Fa = np.array(b.FACING)
    for fi in range(max(start, 0), len(b.F)):
        q = b.F[fi]
        pts = V[q]
        gn = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        if len(q) == 4:
            gn = gn + np.cross(pts[2] - pts[0], pts[3] - pts[0])
        if gn @ Fa[q].sum(0) < 0:
            b.F[fi] = q[::-1]


def knob(b, center, ax_t, ax_n, ax_r, radii, tag, root, aux=0.0):
    _uv_sphere_braid(b, center, ax_t, ax_n, ax_r, radii, rings=5, segs=10, tag=tag, aux=aux, root=root)


def forelock_braided(surf, J, crest, seed=23):
    rng = np.random.default_rng(seed)
    b = PartBuilder("forelock_braided")
    o, ax, dor, lat = hs.head_frame(J)
    s_start, s_end = 0.050, 0.150
    # ligne de la natte sur le chanfrein
    ss = np.linspace(s_start, s_end, 12)
    surf_pts = [hs.head_surface_point(surf, J, s, 0.0) for s in ss]
    rad = np.linspace(0.0095, 0.0075, len(ss))
    Cl = np.array([q + n * r for (q, n), r in zip(surf_pts, rad)])
    Fn = np.array([n for _q, n in surf_pts])
    root0 = surf_pts[0][0]
    # --- base : crins rassemblés des racines (entre les oreilles) vers le début de la natte ---
    Cc, NS = 11, 5
    xs = np.linspace(-0.020, 0.020, Cc)
    grid = np.zeros((NS + 1, Cc, 3))
    roots = np.zeros((Cc, 3))
    FAC = np.zeros((NS + 1, Cc, 3))
    target = Cl[0] - Fn[0] * rad[0] * 0.3
    for c, x in enumerate(xs):
        q, n = hs.head_surface_point(surf, J, -0.004, x)
        roots[c] = q
        for k in range(NS + 1):
            f = k / NS
            p = q * (1 - f) + (target + lat * x * 0.25) * f
            qq, nn, sd = surf.nearest(p)[:3]
            p = qq + nn * (0.0025 + 0.004 * np.sin(np.pi * f))
            grid[k, c] = p
            FAC[k, c] = nn
    u0, v0, u1, v1 = CARD["dense"]
    UVg = np.zeros((NS + 1, Cc, 2))
    for k in range(NS + 1):
        UVg[k, :, 0] = u0 + 0.004 + (u1 - u0 - 0.008) * (xs - xs[0]) / (xs[-1] - xs[0])
        UVg[k, :, 1] = v1 - (k / NS) * (v1 - v0) * 0.45
    Sg = np.repeat(np.linspace(0, 0.3, NS + 1)[:, None], Cc, 1)
    b.add_grid(grid, UVg, Sg, roots, FAC, tag=0)
    # --- natte ---
    braid_tube(b, Cl, Fn, rad, sides=8, tag=1, root=root0, s_values=np.linspace(0.3, 0.9, len(Cl)),
               tile_len=0.10)
    # --- bout replié (« plié en trois ») : petit bouton au bas de la natte ---
    qe, ne = hs.head_surface_point(surf, J, s_end + 0.012, 0.0)
    T_end = nrm(Cl[-1] - Cl[-2])
    rq = nrm(np.cross(T_end, ne))
    knob(b, qe + ne * 0.010, T_end, ne, rq, np.array([0.019, 0.0115, 0.0135]), tag=2, root=qe)
    A = b.arrays()
    Ws = skin_weights_per_vertex(surf, J, A["V"], ["head"])
    Wc = chain_weights(A["V"], J, FORELOCK_CHAIN, smooth=0.8)
    alpha = np.where(A["TAG"] == 0, 0.0, 0.35 * A["S"])
    W = limit_influences(mix_weights(Ws, Wc, alpha))
    # bouton replié : rigide (mêmes poids pour tous ses sommets : moyenne du bouton)
    knob_m = A["TAG"] == 2
    if knob_m.any():
        W[knob_m] = limit_influences(W[knob_m].mean(0, keepdims=True))[0]
    return b, W, {}


# ----------------------------------------------------------------------------------------------
# Queue
# ----------------------------------------------------------------------------------------------
TAIL_RADIUS = [(0.0, 0.042), (0.10, 0.062), (0.30, 0.070), (0.60, 0.068), (0.85, 0.056), (1.0, 0.042)]  # [A]


def _dock_frame(J, a):
    """Point de l'axe du tronçon (a = 0 tête de tail_01 … 1 queue de tail_04), tangente, dorsal."""
    D, L = hs.dock_axis(J, 60)
    x = float(np.clip(a, 0, 1)) * (len(D) - 1)
    i = int(min(np.floor(x), len(D) - 2))
    f = x - i
    p = D[i] * (1 - f) + D[i + 1] * f
    t = nrm(D[i + 1] - D[i])
    dor = np.array([0.0, -t[2], t[1]])
    if dor @ np.array([0.0, -1.0, 1.0]) < 0:
        dor = -dor
    return p, t, dor


def dock_root(surf, J, a, phi, max_dist=0.09):
    """Point de la peau du tronçon à l'abscisse a et à l'angle phi (0 = dessus, + = droite)."""
    p, t, dor = _dock_frame(J, a)
    lat = np.array([1.0, 0.0, 0.0])
    radial = nrm(dor * np.cos(phi) + lat * np.sin(phi))
    h = surf.ray(p, radial, max_dist)
    if h is None:
        return None
    return h[0], h[1], t, radial


def _tail_axis_at_z(J, z):
    ch = hs.tail_chain(J)
    order = np.argsort(ch[:, 2])
    return np.array([np.interp(z, ch[order, 2], ch[order, 0]), np.interp(z, ch[order, 2], ch[order, 1]), z])


def _tail_facing(J, P):
    """Normale « de volume » de la queue : radiale depuis la chaîne tail_01…tail_10."""
    ch = hs.tail_chain(J)
    out = []
    for p in P:
        best = None
        for k in range(len(ch) - 1):
            a, bb = ch[k], ch[k + 1]
            t = np.clip((p - a) @ (bb - a) / ((bb - a) @ (bb - a)), 0, 1)
            q = a + (bb - a) * t
            d = np.linalg.norm(p - q)
            if best is None or d < best[0]:
                best = (d, q, nrm(bb - a))
        v = p - best[1]
        v = v - best[2] * (v @ best[2])
        if np.linalg.norm(v) < 1e-5:
            v = np.array([0.0, -1.0, 0.0])
        out.append(nrm(v))
    return np.array(out)


def tail_guide(surf, J, a, phi, rfac, off_fn, rng, z_end, z_dock_end, dock_follow=True, rprof=TAIL_RADIUS,
               nout=16, start_gather=None):
    r = dock_root(surf, J, a, phi)
    if r is None:
        return None
    q, n, t, radial = r
    d0 = nrm(t * 1.0 + radial * 0.25)
    P = grow_guide(surf, q, d0, 1.4, 56, off_fn, bend=rng.uniform(5, 9))
    # mise en forme du volume sous le tronçon
    psi = None
    out = []
    span = max(z_dock_end - z_end, 0.1)
    for k, p in enumerate(P):
        if p[2] < z_dock_end - 0.005:
            ax = _tail_axis_at_z(J, p[2])
            if psi is None:
                v = p[:2] - ax[:2]
                psi = np.arctan2(v[1], v[0]) if np.linalg.norm(v) > 1e-4 else -np.pi / 2
                psi += rng.uniform(-0.15, 0.15)
                drift = rng.uniform(-0.25, 0.25)
                noise_ph = rng.uniform(0, 6.28)
            f = np.clip((z_dock_end - p[2]) / span, 0, 1)
            ps = psi + drift * f + 0.05 * np.sin(noise_ph + f * 7)
            rr = np.interp(f, [c[0] for c in rprof], [c[1] for c in rprof]) * rfac * rng.uniform(0.97, 1.03)
            target = np.array([ax[0] + np.cos(ps) * rr * 1.0, ax[1] + np.sin(ps) * rr * 0.78, p[2]])
            wblend = smoothstep(0.0, 0.10, (z_dock_end - p[2]))
            p = p * (1 - wblend) + target * wblend
        out.append(p)
        if p[2] <= z_end:
            break
    P = np.array(out)
    # recolle exactement à z_end
    if P[-1][2] < z_end and len(P) >= 2:
        a0, a1 = P[-2], P[-1]
        f = (a0[2] - z_end) / max(a0[2] - a1[2], 1e-9)
        P[-1] = a0 + (a1 - a0) * f
    return resample(P, nout), q


def tail_natural(surf, J, crest, seed=29, part_id="tail_natural"):
    rng = np.random.default_rng(seed)
    b = PartBuilder(part_id)
    z_dock_end = J["tail_04"][1][2]
    z_end0 = J["tail_10"][0][2] - 0.035
    # --- âme opaque (nappe en C autour du tronçon puis tube interne) ---
    phis = np.radians(np.linspace(-150, 150, 21))
    NS = 18
    grid = np.zeros((NS, len(phis), 3))
    roots = np.zeros((len(phis), 3))
    ok = np.ones(len(phis), bool)
    for c, ph in enumerate(phis):
        g = tail_guide(surf, J, 0.06, ph, 0.55, lambda s: 0.003 + 0.004 * s, rng, z_end0 + 0.05, z_dock_end,
                       nout=NS)
        if g is None:
            ok[c] = False
            continue
        grid[:, c], roots[c] = g
    grid, roots, phis = grid[:, ok], roots[ok], phis[ok]
    u0, v0, u1, v1 = R_BASE
    uu = tri_wave(np.linspace(0, 1, len(phis)) * 4.0)
    UVg = np.zeros((NS, len(phis), 2))
    for rr in range(NS):
        UVg[rr, :, 0] = u0 + 0.004 + (u1 - u0 - 0.008) * uu
        UVg[rr, :, 1] = v1 - (rr / (NS - 1)) * (v1 - v0) * 0.98
    Sg = np.repeat(np.linspace(0, 1, NS)[:, None], len(phis), 1)
    FAC = np.stack([_tail_facing(J, grid[rr]) for rr in range(NS)])
    b.add_grid(grid, UVg, Sg, roots, FAC, tag=0)
    # --- cartes ---
    layers = [
        dict(tag=1, n=58, a=(0.0, 0.90), phi=150, rfac=0.80, off=lambda s: 0.007 + 0.006 * s, width=(0.032, 0.045),
             nacross=2, variants=["dense", "clumped", "dense", "short"], dz=0.035),
        dict(tag=2, n=72, a=(0.0, 0.85), phi=158, rfac=1.0, off=lambda s: 0.010 + 0.008 * s, width=(0.030, 0.042),
             nacross=2, variants=["clumped", "wispy", "split", "pointed", "clumped"], dz=0.05),
        # mèches folles clairsemées en surface : adoucissent la silhouette (cartes étroites, texture « wispy »)
        dict(tag=3, n=36, a=(0.0, 0.8), phi=160, rfac=1.10, off=lambda s: 0.014 + 0.010 * s, width=(0.016, 0.024),
             nacross=2, variants=["wispy", "pointed"], dz=0.07),
    ]
    for lay in layers:
        _tail_cards(surf, J, b, rng, lay, z_end0, z_dock_end, TAIL_RADIUS, a_pow=1.3)
    A = b.arrays()
    W = _tail_weights(surf, J, A)
    return b, W, {}


def _tail_cards(surf, J, b, rng, lay, z_end0, z_dock_end, rprof, a_pow=1.0):
    """Cartes de queue : racines sur le tronçon, chute par gravité, volume mis en forme, torsion aléatoire
    (les cartes ne sont pas toutes tangentes au volume : casse l'effet « planches »)."""
    for k in range(lay["n"]):
        a = lay["a"][0] + (lay["a"][1] - lay["a"][0]) * rng.uniform() ** a_pow
        ph = np.radians(rng.uniform(-lay["phi"], lay["phi"]))
        z_end = z_end0 + rng.uniform(-lay["dz"], lay["dz"] * 0.6)
        g = tail_guide(surf, J, a, ph, lay["rfac"] * rng.uniform(0.85, 1.12), lay["off"], rng, z_end, z_dock_end,
                       rprof=rprof)
        if g is None:
            continue
        P, q = g
        F = _tail_facing(J, P)
        across = nrm(np.cross(F, tangents(P)))
        s = np.linspace(0, 1, len(P))
        w = rng.uniform(*lay["width"]) * (0.70 + 0.30 * np.sin(np.pi * np.clip(s * 0.9 + 0.1, 0, 1)))
        tw0 = np.radians(rng.uniform(-28, 28))
        twist = tw0 * smoothstep(0.15, 0.45, s) + np.radians(rng.uniform(-12, 12)) * s
        variant = lay["variants"][rng.integers(len(lay["variants"]))]
        flip = rng.uniform() < 0.5
        b.add_ribbon(P, F, w, CARD[variant], across_dir=across, n_across=lay["nacross"],
                     arch=lay.get("arch", 0.0), tag=lay["tag"], u_range=(1.0, 0.0) if flip else (0.0, 1.0),
                     twist=twist)


def _tail_weights(surf, J, A, s_fade=(0.0, 0.30), skin_tags=()):
    """Poids de queue (≤ 4 influences) :
    - couches plaquées sur le tronçon (`skin_tags` : enveloppe et natte de la queue tressée) : poids de peau du corps
      transférés au plus proche point de chaque sommet ;
    - crins pendants : poids de peau à la racine RESTREINTS aux os de la queue (renormalisés ; la peau du dessous
      du tronçon mêle `hips`, ce qui déchirait les mèches quand la queue se relève), fondus le long de la mèche
      (s ∈ s_fade) vers le dégradé tail_01…tail_10 obtenu par projection sur la chaîne."""
    V = A["V"]
    tail_idx = np.array([JIDX[n] for n in TAIL_CHAIN])
    Wc = chain_weights(V, J, TAIL_CHAIN, smooth=0.7)
    roots_u, inv = unique_roots(A["ROOT"])
    Wr = root_weights(surf, J, roots_u, TAIL_CHAIN[:4])
    Wrt = np.zeros_like(Wr)
    Wrt[:, tail_idx] = Wr[:, tail_idx]
    ssum = Wrt.sum(1, keepdims=True)
    fallback = chain_weights(roots_u, J, TAIL_CHAIN[:4])
    Wrt = np.where(ssum > 0.2, Wrt / np.maximum(ssum, 1e-9), fallback)
    beta = 1.0 - smoothstep(s_fade[0], s_fade[1], A["S"])
    W = mix_weights(Wc, Wrt[inv], beta)
    m = np.isin(A["TAG"], list(skin_tags))
    if m.any():
        W[m] = skin_weights_per_vertex(surf, J, V[m], TAIL_CHAIN[:4])
    return limit_influences(W)


def tail_braided(surf, J, crest, seed=31):
    rng = np.random.default_rng(seed)
    b = PartBuilder("tail_braided")
    z_dock_end = J["tail_04"][1][2]
    z_end0 = J["tail_10"][0][2] - 0.035
    # --- base plaquée sur le tronçon (crins tirés vers la natte) ---
    NA, NP = 14, 13
    As = np.linspace(0.03, 0.97, NA)
    phis = np.radians(np.linspace(-115, 115, NP))
    grid = np.zeros((NA, NP, 3))
    FAC = np.zeros((NA, NP, 3))
    for i, a in enumerate(As):
        p_ax, t_ax, dor = _dock_frame(J, a)
        r0 = dock_root(surf, J, a, 0.0)
        rad0 = np.linalg.norm(r0[0] - p_ax) if r0 is not None else 0.035
        for j, ph in enumerate(phis):
            r = dock_root(surf, J, a, ph, max_dist=rad0 * 1.35)
            radial = nrm(dor * np.cos(ph) + np.array([1.0, 0, 0]) * np.sin(ph))
            if r is None:   # la peau du tronçon se confond avec la croupe : on reste sur un cylindre local
                q, n = p_ax + radial * rad0, radial
            else:
                q, n = r[0], r[1]
            grid[i, j] = q + n * 0.003
            FAC[i, j] = n
    # mèches tirées des côtés (racines) vers la natte au centre : v suit |phi| (bord -> centre), u le tronçon,
    # avec un biais diagonal (les crins descendent vers la natte)
    u0, v0, u1, v1 = R_BASE
    arcd = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(grid[:, len(phis) // 2], axis=0), axis=1))])
    UVg = np.zeros((NA, len(phis), 2))
    fr = 1.0 - np.abs(phis) / np.abs(phis).max()          # 0 au bord, 1 au centre
    for i in range(NA):
        UVg[i, :, 0] = u0 + 0.004 + (u1 - u0 - 0.008) * tri_wave(arcd[i] / 0.05 + fr * 0.35)
        UVg[i, :, 1] = v1 - fr * (v1 - v0) * 0.45
    Sg = np.repeat(fr[None, :] * 0.4, NA, 0)
    roots = grid[0].copy()
    b.add_grid(grid, UVg, Sg, roots, FAC, tag=0, root_rows=(), root_cols=(0, len(phis) - 1))
    # --- natte le long du dessus du tronçon ---
    NB = 30
    Ab = np.linspace(0.02, 1.0, NB)
    Cl, Fn = [], []
    radb = np.linspace(0.0125, 0.0095, NB)
    for a, rb in zip(Ab, radb):
        r = dock_root(surf, J, min(a, 0.995), 0.0)
        q, n = r[0], r[1]
        Cl.append(q + n * (rb * 0.85 + 0.002))
        Fn.append(n)
    Cl, Fn = np.array(Cl), np.array(Fn)
    braid_tube(b, Cl, Fn, radb, sides=8, tag=1, root=Cl[0], s_values=np.linspace(0.2, 0.6, NB), tile_len=0.13)
    # --- extrémité libre : crins du bas du tronçon jusqu'au jarret ---
    rprof = [(0.0, 0.030), (0.12, 0.052), (0.35, 0.062), (0.65, 0.060), (0.88, 0.050), (1.0, 0.038)]
    phis2 = np.radians(np.linspace(-170, 170, 18))
    NS = 16
    grid2, roots2, ok = np.zeros((NS, len(phis2), 3)), np.zeros((len(phis2), 3)), np.ones(len(phis2), bool)
    for c, ph in enumerate(phis2):
        g = tail_guide(surf, J, 0.86, ph, 0.55, lambda s: 0.003 + 0.004 * s, rng, z_end0 + 0.05, z_dock_end,
                       rprof=rprof, nout=NS)
        if g is None:
            ok[c] = False
            continue
        grid2[:, c], roots2[c] = g
    grid2, roots2 = grid2[:, ok], roots2[ok]
    uu = tri_wave(np.linspace(0, 1, grid2.shape[1]) * 4.0)
    UVg2 = np.zeros((NS, grid2.shape[1], 2))
    for rr in range(NS):
        UVg2[rr, :, 0] = u0 + 0.004 + (u1 - u0 - 0.008) * uu
        UVg2[rr, :, 1] = v1 - (rr / (NS - 1)) * (v1 - v0) * 0.98
    FAC2 = np.stack([_tail_facing(J, grid2[rr]) for rr in range(NS)])
    b.add_grid(grid2, UVg2, np.repeat(np.linspace(0, 1, NS)[:, None], grid2.shape[1], 1), roots2, FAC2, tag=2)
    layers = [
        dict(tag=3, n=44, a=(0.74, 0.97), phi=170, rfac=0.80, off=lambda s: 0.007 + 0.006 * s, width=(0.030, 0.042),
             nacross=2, variants=["dense", "clumped", "short"], dz=0.035),
        dict(tag=4, n=56, a=(0.72, 0.97), phi=175, rfac=1.0, off=lambda s: 0.012 + 0.008 * s, width=(0.028, 0.040),
             nacross=2, variants=["clumped", "wispy", "split", "pointed"], dz=0.05),
    ]
    for lay in layers:
        _tail_cards(surf, J, b, rng, lay, z_end0, z_dock_end, rprof)
    A = b.arrays()
    W = _tail_weights(surf, J, A, skin_tags=(0, 1))
    return b, W, {}


# ----------------------------------------------------------------------------------------------
# Fanons
# ----------------------------------------------------------------------------------------------
LEGS = [("front", "l"), ("front", "r"), ("hind", "l"), ("hind", "r")]


def feathers(surf, J, crest, seed=37):
    rng = np.random.default_rng(seed)
    b = PartBuilder("feathers")
    for li, (fh, side) in enumerate(LEGS):
        cannon, pastern, hoof = f"{fh}_cannon_{side}", f"{fh}_pastern_{side}", f"{fh}_hoof_{side}"
        c = J[pastern][0]
        up = nrm(J[cannon][0] - c)
        back = perp(np.array([0.0, -1.0, 0.0]), up)
        lat = nrm(np.cross(up, back))
        n_cards = 14
        for k in range(n_cards):
            dz = rng.uniform(0.0, 0.05)
            th = np.radians(rng.uniform(-60, 60))
            radial = nrm(back * np.cos(th) + lat * np.sin(th))
            o = c + up * dz + radial * 0.15
            h = surf.ray(o, -radial, 0.2)
            if h is None:
                continue
            q = h[0]
            L = rng.uniform(0.040, 0.075) * (1.0 - 0.35 * abs(np.sin(th)))
            d0 = nrm(-up * 0.85 + radial * 0.30 + rng.normal(0, 0.08, 3))
            P = grow_guide(surf, q, d0, L, 5, lambda s: 0.003 + 0.004 * s, bend=rng.uniform(20, 30))
            F = np.array([nrm(radial * 0.7 + surf.nearest(p)[1] * 0.3) for p in P])
            tang = nrm(np.cross(up, radial))
            s = np.linspace(0, 1, len(P))
            w = rng.uniform(0.016, 0.024) * (0.55 + 0.45 * np.sin(np.pi * np.clip(0.15 + 0.7 * s, 0, 1)))
            flip = rng.uniform() < 0.5
            b.add_ribbon(P, F, w, R_WISP, across_dir=np.broadcast_to(tang, P.shape), n_across=2, tag=li,
                         u_range=(1.0, 0.0) if flip else (0.0, 1.0))
    A = b.arrays()
    W = np.zeros((len(A["V"]), NJ))
    roots_u, inv = unique_roots(A["ROOT"])
    for li, (fh, side) in enumerate(LEGS):
        m = A["TAG"] == li
        chain = [f"{fh}_cannon_{side}", f"{fh}_pastern_{side}"]
        Wr = root_weights(surf, J, roots_u, chain)[inv[m]]
        # les poids du corps à la racine peuvent inclure d'autres os voisins : on les garde (peau)
        Wc = chain_weights(A["V"][m], J, chain, smooth=0.5)
        alpha = smoothstep(0.0, 0.4, A["S"][m])
        W[m] = mix_weights(Wr, Wc, alpha)
    return b, limit_influences(W), {}


GENERATORS = {
    "mane_natural": mane_natural,
    "mane_braided": mane_braided,
    "mane_roached": mane_roached,
    "forelock_natural": forelock_natural,
    "forelock_braided": forelock_braided,
    "tail_natural": tail_natural,
    "tail_braided": tail_braided,
    "feathers": feathers,
}

BUDGETS = {   # triangles [I] (tâche) : crinière ≤ 8 k, queue ≤ 6 k, toupet ≤ 1,5 k, fanons ≤ 1 k, tressées ≤ 6 k
    "mane_natural": 8000, "mane_braided": 6000, "mane_roached": 8000, "forelock_natural": 1500,
    "forelock_braided": 1500, "tail_natural": 6000, "tail_braided": 6000, "feathers": 1000,
}
