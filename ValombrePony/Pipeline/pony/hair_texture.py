"""Atlas de texture des crins (`hair_strands.png`, `hair_normal.png`, `braid_detail.png`).

Tout est généré en numpy, de façon déterministe (graines fixes). Aucune dépendance à bpy.

Sémantique des canaux de `hair_strands.png` (1024², PNG 8 bits RGBA, **données linéaires / non-couleur**) —
contrat avec le compositeur de robe du runtime (agent « coat ») :
  R = luminance des mèches, **0.5 = neutre** (convention du compositeur : facteur = 0.5 + R, cf.
      `coat_reference.compose_hair` et `CoatMaps.swift`) ; ~0 = creux/ombre entre mèches et occlusion près des
      racines, ~0.8 = mèches claires du dessus. Valeurs typiques 0…0.85.
  G = position racine → pointe le long de la carte, 0 à la racine, 1 à la pointe de la carte (spatial, identique
      pour toutes les mèches d'une carte). Couches de base : 0 → 0.75 ; brosse : 0 → 0.3 ; tresse : ≈ 0.45.
  B = aléa par mèche : identifiant 8 bits (1…255) constant le long d'une mèche et jamais mélangé entre mèches
      (le compositeur le hache pour choisir des mèches secondaires / blanches et module la teinte ±14 %).
  A = alpha (couverture). Les zones opaques (couche de base, tresses) valent 1. Seuil de découpe conseillé
      au runtime : `opacityThreshold` ≈ 0.4 [I].
Les pixels transparents reçoivent les valeurs R/G/B de la mèche la plus proche (dilatation) pour éviter les liserés
sombres dans les mipmaps.

Disposition de l'atlas (coordonnées UV, v vers le haut ; la rangée 0 du PNG correspond à v = 1) :
  cartes  : 6 colonnes u ∈ [k/8, (k+1)/8], k = 0…5, v ∈ [0.25, 1] ; racine en haut (v = 1), pointe en bas (v = 0.25)
  base    : u ∈ [0.75, 1], v ∈ [0.25, 1] ; couche de base dense, opaque sur ~60 %, frange en bas ; périodique en u
  braid   : u ∈ [0, 0.5], v ∈ [0, 0.25] ; tresse à 3 brins, la natte court le long de u (périodique en u) ; opaque
  brush   : u ∈ [0.5, 0.75], v ∈ [0, 0.25] ; crins courts en brosse, racine en haut ; périodique en u
  wisp    : u ∈ [0.75, 1], v ∈ [0, 0.25] ; mèches fines et frisottantes (fanons), racine en haut

`braid_detail.png` (512×256, données) couvre exactement la région `braid` :
  R = hauteur du relief (0…1), G = cavité/occlusion (1 = dégagé, 0 = creux), B = identifiant du brin (0, 0.5, 1),
  A = 1. Le même relief est intégré à `hair_normal.png` (normales OpenGL, espace tangent, tout l'atlas).

Les formes, densités et proportions des mèches sont des approximations artistiques [A].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SIZE = 1024
SEED = 20261005
LUM_NOMINAL = 0.72       # facteur interne de luminance qui correspond à R = 0.5 (neutre) [I]

# Régions de l'atlas en UV (u0, v0, u1, v1)
CARD_COLUMNS = 6
REGIONS = {f"card{k}": (k / 8.0, 0.25, (k + 1) / 8.0, 1.0) for k in range(CARD_COLUMNS)}
REGIONS.update({
    "base": (0.75, 0.25, 1.0, 1.0),
    "braid": (0.0, 0.0, 0.5, 0.25),
    "brush": (0.5, 0.0, 0.75, 0.25),
    "wisp": (0.75, 0.0, 1.0, 0.25),
})
# Variantes de cartes (nom -> région) ; documentation de l'intention artistique [A]
CARD_VARIANTS = {
    "dense": "card0",      # mèche pleine, légère agglomération
    "clumped": "card1",    # 3 à 4 mèches agglomérées, longueurs variées
    "wispy": "card2",      # mèche clairsemée, pointes effilées, quelques crins folets
    "split": "card3",      # deux mèches qui divergent
    "short": "card4",      # mèche dense mais plus courte (60-80 % de la carte)
    "pointed": "card5",    # mèche qui converge en pointe (bout de queue, toupet)
}

# Paramètres conseillés du matériau M_Hair (aperçu Blender et runtime) [I]
MATERIAL_HINTS = {
    "roughness": 0.48,
    "opacityThreshold": 0.4,
    "faceCulling": "none",
    "specular": 0.35,
    "anisotropyLevel": 0.6,   # PhysicallyBasedMaterial.anisotropyLevel (réalité : « straight hair ») [I]
}


def region_px(name: str, size: int = SIZE):
    """Rectangle de pixels (x0, y0, x1, y1) d'une région (y0 = rangée du haut dans l'image)."""
    u0, v0, u1, v1 = REGIONS[name]
    return (int(round(u0 * size)), int(round((1.0 - v1) * size)),
            int(round(u1 * size)), int(round((1.0 - v0) * size)))


def region_uv(name: str):
    return REGIONS[name]


# ----------------------------------------------------------------------------------------------
# Rendu de mèches
# ----------------------------------------------------------------------------------------------
@dataclass
class Strand:
    x: np.ndarray          # (L,) position horizontale (px, flottant) pour chaque rangée y = 0…L-1
    w: np.ndarray          # (L,) largeur (px)
    lum: np.ndarray        # (L,) luminance R
    rid: float             # aléa par mèche (B)
    height: float = 1.0    # hauteur relative pour la carte de normales
    y0: int = 0            # rangée de départ


@dataclass
class Layer:
    H: int
    W: int
    wrap: bool = False
    rgba: np.ndarray = field(init=False)
    height: np.ndarray = field(init=False)

    def __post_init__(self):
        self.rgba = np.zeros((self.H, self.W, 4), np.float64)
        self.height = np.zeros((self.H, self.W), np.float64)

    def draw(self, s: Strand):
        L = len(s.x)
        if L <= 0:
            return
        rows = np.arange(s.y0, s.y0 + L)
        keep = (rows >= 0) & (rows < self.H)
        if not keep.any():
            return
        rows = rows[keep]
        x = s.x[keep]
        w = np.maximum(s.w[keep], 1e-3)
        lum = s.lum[keep]
        K = int(np.ceil(w.max() / 2.0)) + 2
        dx = np.arange(-K, K + 1)
        c0 = np.floor(x).astype(int)
        cols = c0[:, None] + dx[None, :]
        # couverture exacte du pixel [c, c+1] par l'intervalle [x - w/2, x + w/2]
        lo = x[:, None] - w[:, None] / 2.0
        hi = x[:, None] + w[:, None] / 2.0
        cov = np.clip(np.minimum(cols + 1.0, hi) - np.maximum(cols.astype(float), lo), 0.0, 1.0)
        # profil cylindrique pour la hauteur (normales)
        rel = (cols + 0.5 - x[:, None]) / (w[:, None] / 2.0 + 0.35)
        prof = np.sqrt(np.clip(1.0 - rel ** 2, 0.0, 1.0)) * s.height
        if self.wrap:
            cols = np.mod(cols, self.W)
            valid = np.ones_like(cols, bool)
        else:
            valid = (cols >= 0) & (cols < self.W)
        rr = np.broadcast_to(rows[:, None], cols.shape)[valid]
        cc = cols[valid]
        a = cov[valid]
        pr = prof[valid]
        lm = np.broadcast_to(lum[:, None], cols.shape)[valid]
        dst = self.rgba[rr, cc]
        # composition « over » (la nouvelle mèche passe devant) ; B = identifiant de la mèche dominante,
        # jamais mélangé (le compositeur du runtime le hache par mèche)
        dst[:, 0] = dst[:, 0] * (1 - a) + lm * a
        dst[:, 2] = np.where(a >= 0.5, s.rid, dst[:, 2])
        first = dst[:, 3] < 1e-6
        dst[:, 2] = np.where(first & (a > 0), s.rid, dst[:, 2])
        dst[:, 3] = dst[:, 3] + a * (1 - dst[:, 3])
        self.rgba[rr, cc] = dst
        hh = self.height[rr, cc]
        self.height[rr, cc] = np.maximum(hh * (1 - 0.5 * a), pr)

    def straight(self):
        """Renvoie RGBA « droit » (non prémultiplié) : R accumulé en prémultiplié est divisé par A."""
        out = self.rgba.copy()
        a = out[..., 3]
        nz = a > 1e-6
        out[..., 0][nz] /= a[nz]
        return out


def _smooth_noise(rng, n, scale, octaves=3):
    """Bruit 1D lisse (somme de sinusoïdes) de longueur n, amplitude ~1."""
    t = np.arange(n) / max(scale, 1e-6)
    out = np.zeros(n)
    amp = 1.0
    for o in range(octaves):
        f = (o + 1) ** 1.6
        out += amp * np.sin(2 * np.pi * f * t / 4.0 + rng.uniform(0, 2 * np.pi))
        amp *= 0.5
    return out / 1.75


def _smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _fill_transparent(rgba: np.ndarray, thresh: float = 0.02, wrap: bool = False):
    """Recopie R/G/B du pixel couvert le plus proche dans les pixels transparents (anti-liseré)."""
    from scipy import ndimage

    mask = rgba[..., 3] > thresh
    if mask.all() or not mask.any():
        return rgba
    src = rgba
    if wrap:
        src = np.concatenate([rgba, rgba, rgba], axis=1)
        mask = np.concatenate([mask, mask, mask], axis=1)
    _, (iy, ix) = ndimage.distance_transform_edt(~mask, return_indices=True)
    filled = src[iy, ix]
    if wrap:
        W = rgba.shape[1]
        filled = filled[:, W:2 * W]
        mask = mask[:, W:2 * W]
    out = rgba.copy()
    tm = ~mask
    out[..., 0][tm] = filled[..., 0][tm]
    out[..., 2][tm] = filled[..., 2][tm]
    return out


# ----------------------------------------------------------------------------------------------
# Générateurs de régions
# ----------------------------------------------------------------------------------------------
def _card_strands(rng, H, W, variant: str):
    """Liste de mèches pour une variante de carte (racine en haut, rangée 0)."""
    strands = []
    margin = 4.0
    if variant == "dense":
        n, n_clumps, attract, len_rng, wid = 170, 6, 0.28, (0.82, 1.0), (1.6, 2.6)
    elif variant == "clumped":
        n, n_clumps, attract, len_rng, wid = 150, 4, 0.55, (0.70, 1.0), (1.6, 2.5)
    elif variant == "wispy":
        n, n_clumps, attract, len_rng, wid = 100, 5, 0.38, (0.60, 1.0), (1.3, 2.1)
    elif variant == "split":
        n, n_clumps, attract, len_rng, wid = 150, 2, 0.50, (0.78, 1.0), (1.6, 2.5)
    elif variant == "short":
        n, n_clumps, attract, len_rng, wid = 160, 5, 0.32, (0.58, 0.82), (1.6, 2.6)
    elif variant == "pointed":
        n, n_clumps, attract, len_rng, wid = 160, 1, 0.68, (0.80, 1.0), (1.6, 2.5)
    else:
        raise ValueError(variant)

    # centres d'agglomération (en px) à la pointe, avec une dérive lente le long de la carte
    if n_clumps == 1:
        centers = np.array([W / 2.0 + rng.uniform(-6, 6)])
    else:
        centers = np.linspace(margin + 10, W - margin - 10, n_clumps) + rng.uniform(-6, 6, n_clumps)
    clump_len = rng.uniform(len_rng[0], len_rng[1], n_clumps)
    if variant in ("clumped", "split"):
        clump_len[rng.integers(0, n_clumps)] = len_rng[1]
    y = np.arange(H)
    for i in range(n):
        x0 = rng.uniform(margin, W - margin)
        # densité réduite près des bords (la carte ne doit pas montrer un bord rectiligne)
        edge = min(x0 - margin, W - margin - x0) / (W * 0.18)
        if rng.uniform() > np.clip(edge, 0.25, 1.0):
            x0 = W / 2 + (x0 - W / 2) * 0.7
        k = int(np.argmin(np.abs(centers - x0))) if n_clumps > 1 else 0
        if rng.uniform() < 0.12:            # quelques crins rejoignent l'agglomération voisine
            k = int(np.clip(k + rng.choice([-1, 1]), 0, n_clumps - 1))
        Ls = clump_len[k] * (1.0 - 0.42 * rng.uniform() ** 1.6)   # pointes effilochées (longueurs variées)
        ue = min(x0 - margin, W - margin - x0) / W                  # 0 au bord … 0.5 au centre
        if ue < 0.12:                                               # bords effilochés : crins plus courts
            Ls *= rng.uniform(0.45, 1.0) if rng.uniform() < 0.6 else 1.0
        if variant == "wispy" and rng.uniform() < 0.25:
            Ls *= rng.uniform(0.5, 0.8)
        L = int(H * min(Ls, 1.0))
        t = y[:L] / H
        a = attract * _smoothstep(0.05, 0.85, t) * rng.uniform(0.75, 1.1)
        xc = centers[k] + 5.0 * _smooth_noise(rng, L, H * 0.6)
        sway = rng.uniform(0.8, 3.2) * _smooth_noise(rng, L, H * rng.uniform(0.15, 0.40))
        x = x0 * (1 - a) + xc * a + sway * (0.4 + t)
        if variant == "split":
            x += (x0 - W / 2) * 0.10 * t
        if variant == "wispy" and rng.uniform() < 0.10:   # crin folet qui s'écarte
            x += rng.choice([-1, 1]) * 14 * _smoothstep(0.4, 1.0, t)
        w0 = rng.uniform(*wid)
        taper = 1.0 - _smoothstep(0.50, 1.0, t / max(Ls, 1e-3)) * 0.85
        w = w0 * taper
        # luminance : occlusion près de la racine, variation par mèche et le long de la mèche
        base = rng.uniform(0.58, 1.0)
        occl = 0.55 + 0.45 * _smoothstep(0.0, 0.30, t)
        lum = base * occl * (1.0 + 0.06 * _smooth_noise(rng, L, H * 0.1))
        strands.append(Strand(x=x, w=w, lum=np.clip(lum, 0.0, 1.0), rid=rng.uniform(), height=rng.uniform(0.6, 1.0)))
    # ordre de dessin : les mèches dessinées en dernier sont devant ; les premières sont assombries (ombre interne)
    order = rng.permutation(len(strands))
    out = []
    for rank, idx in enumerate(order):
        s = strands[idx]
        s.lum = s.lum * (0.78 + 0.22 * rank / len(strands))
        out.append(s)
    return out


def gen_card(rng, H, W, variant):
    lay = Layer(H, W, wrap=False)
    for s in _card_strands(rng, H, W, variant):
        lay.draw(s)
    rgba = lay.straight()
    rgba[..., 1] = (np.arange(H) / (H - 1))[:, None]
    rgba = _fill_transparent(rgba)
    return rgba, lay.height


def gen_base(rng, H, W):
    """Couche de base dense : opaque sur la partie haute, frange irrégulière en bas. Périodique en u."""
    lay = Layer(H, W, wrap=True)
    # fond sombre (profondeur entre les mèches) sur la partie opaque
    y = np.arange(H)
    t = y / H
    n = 420
    for i in range(n):
        x0 = rng.uniform(0, W)
        Ls = rng.uniform(0.62, 1.0) if rng.uniform() < 0.7 else rng.uniform(0.45, 0.7)
        L = int(H * Ls)
        tt = t[:L]
        sway = rng.uniform(0.6, 1.8) * _smooth_noise(rng, L, H * rng.uniform(0.2, 0.4))
        x = x0 + sway * (0.3 + tt)
        w = rng.uniform(1.7, 2.8) * (1.0 - _smoothstep(0.6, 1.0, tt / Ls) * 0.85)
        base = rng.uniform(0.62, 0.95)
        lum = base * (0.55 + 0.45 * _smoothstep(0.0, 0.35, tt)) * (1 + 0.05 * _smooth_noise(rng, L, H * 0.1))
        lay.draw(Strand(x=x, w=w, lum=np.clip(lum, 0, 1), rid=rng.uniform(), height=rng.uniform(0.6, 1.0)))
    rgba = lay.straight()
    # opacité forcée sur la partie haute (couche de base opaque près des racines, recommandation Apple)
    opaque = (1.0 - _smoothstep(0.50, 0.62, t))[:, None]
    a = rgba[..., 3]
    under = 0.30  # creux sombres entre les mèches
    rgba[..., 0] = np.where(a > 1e-6, rgba[..., 0], under)
    rgba[..., 0] = rgba[..., 0] * (1 - opaque) + (rgba[..., 0] * a + under * (1 - a)) * opaque
    rgba[..., 3] = np.maximum(a, opaque)
    rgba[..., 1] = (0.75 * t)[:, None]
    rgba = _fill_transparent(rgba, wrap=True)
    return rgba, lay.height


def gen_brush(rng, H, W):
    """Crins courts en brosse (crinière rasée, crête des tresses). Racine en haut, périodique en u.
    Mèches fines et nombreuses, pointes irrégulières (pas de « dents » régulières)."""
    lay = Layer(H, W, wrap=True)
    y = np.arange(H)
    t = y / H
    for i in range(760):
        x0 = rng.uniform(0, W)
        Ls = 1.0 - 0.38 * rng.uniform() ** 1.4
        L = int(H * Ls)
        tt = t[:L]
        lean = rng.uniform(-3, 3)
        x = x0 + lean * tt ** 1.3 + 1.0 * _smooth_noise(rng, L, H * 0.5)
        w = rng.uniform(1.4, 2.3) * (1.0 - _smoothstep(0.6, 1.0, tt / Ls) * 0.75)
        lum = rng.uniform(0.66, 1.0) * (0.72 + 0.28 * _smoothstep(0.0, 0.5, tt))
        lay.draw(Strand(x=x, w=w, lum=lum, rid=rng.uniform(), height=rng.uniform(0.6, 1.0)))
    rgba = lay.straight()
    opaque = (1.0 - _smoothstep(0.40, 0.60, t))[:, None]
    a = rgba[..., 3]
    under = 0.45
    rgba[..., 0] = np.where(a > 1e-6, rgba[..., 0], under)
    rgba[..., 0] = rgba[..., 0] * (1 - opaque) + (rgba[..., 0] * a + under * (1 - a)) * opaque
    rgba[..., 3] = np.maximum(a, opaque)
    rgba[..., 1] = (0.3 * t)[:, None]
    rgba = _fill_transparent(rgba, wrap=True)
    return rgba, lay.height


def gen_wisp(rng, H, W):
    """Mèches fines légèrement ondulées (fanons), clairsemées. Racine en haut."""
    lay = Layer(H, W, wrap=False)
    y = np.arange(H)
    t = y / H
    for i in range(110):
        x0 = W / 2 + (rng.uniform(-1, 1) ** 3 * 0.5 + rng.uniform(-0.35, 0.35)) * (W - 24)
        y0 = int(H * rng.uniform(0.0, 0.30) ** 1.5)          # haut effiloché (pas de ligne de racine nette)
        Ls = (1.0 - 0.6 * rng.uniform() ** 1.3) * (1.0 - y0 / H)
        L = int(H * Ls)
        tt = t[:L] + y0 / H
        curl = rng.uniform(2, 6) * np.sin(2 * np.pi * tt * rng.uniform(1.2, 2.6) + rng.uniform(0, 6.28))
        x = x0 + (W / 2 - x0) * 0.35 * _smoothstep(0.2, 1.0, tt) + curl * tt
        w = rng.uniform(1.2, 1.9) * (1.0 - _smoothstep(0.35, 1.0, tt / Ls) * 0.85)
        lum = rng.uniform(0.68, 1.0) * (0.6 + 0.4 * _smoothstep(0.0, 0.3, tt))
        lay.draw(Strand(x=x, w=w, lum=lum, rid=rng.uniform(), height=rng.uniform(0.6, 1.0), y0=y0))
    rgba = lay.straight()
    rgba[..., 1] = t[:, None]
    rgba = _fill_transparent(rgba)
    return rgba, lay.height


def gen_braid(rng, H, W, periods: int = 4):
    """Tresse à 3 brins vue de dessus : lobes allongés et inclinés, alternés gauche/droite (chevrons).
    La natte court le long de x (périodique en x) ; y traverse la natte.

    Renvoie (rgba, height, detail) ; detail = (H, W, 4) pour braid_detail.png.
    """
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    yc = (yy + 0.5) / H - 0.5             # -0.5…0.5 à travers la natte
    height = np.zeros((H, W))
    lum = np.zeros((H, W))
    sid = np.zeros((H, W))
    rid = np.zeros((H, W))
    theta = np.radians(52.0)              # inclinaison des lobes par rapport à l'axe de la natte [A]
    nlobes = periods * 2 * 3 // 2 * 2     # nombre pair -> périodique
    step = W / nlobes
    ra = 0.50 * H / np.sin(theta)         # demi-grand axe : le lobe va du bord jusqu'au-delà du centre
    rb = step * 0.95                      # demi-petit axe
    for k in range(nlobes):
        side = 1.0 if k % 2 == 0 else -1.0
        cx = (k + 0.5) * step
        cy = side * 0.12 * H
        ax = np.array([np.cos(theta), -side * np.sin(theta)])
        dxp = (xx + 0.5) - cx
        dxp = (dxp + W / 2) % W - W / 2   # périodique
        dyp = yc * H - cy
        a = dxp * ax[0] + dyp * ax[1]
        b = -dxp * ax[1] + dyp * ax[0]
        q = (a / ra) ** 2 + (b / rb) ** 2
        dome = np.sqrt(np.clip(1.0 - q, 0.0, 1.0))
        # le lobe plonge sous le suivant vers son extrémité avant (a > 0) : relief incliné
        dome = dome * (0.80 + 0.20 * np.clip(-a / ra, -1, 1))
        # stries de crins parallèles au grand axe du lobe
        ph = rng.uniform(0, 6.28)
        stri = 0.80 + 0.20 * np.sin(b / rb * 11.0 + ph + 0.8 * np.sin(a / ra * 4.0))
        stri *= 0.94 + 0.06 * np.sin(b / rb * 29.0 + 2 * ph)
        better = dome > height + 0.02
        height = np.where(better, dome, height)
        lum = np.where(better, (0.38 + 0.62 * dome ** 0.7) * stri, lum)
        sid = np.where(better, (k % 3) / 2.0, sid)
        rid = np.where(better, rng.uniform(), rid)
    edge = 1.0 - _smoothstep(0.38, 0.5, np.abs(yc))     # les bords de la bande s'assombrissent (côtés de la natte)
    cav = np.clip(0.30 + 0.70 * height ** 0.5, 0.0, 1.0) * (0.55 + 0.45 * edge)
    lum = np.clip(lum * (0.55 + 0.45 * edge) + 0.03 * rng.standard_normal((H, W)), 0.0, 1.0)
    rgba = np.zeros((H, W, 4))
    rgba[..., 0] = np.maximum(lum, 0.20)
    rgba[..., 1] = 0.45
    rgba[..., 2] = rid
    rgba[..., 3] = 1.0
    detail = np.zeros((H, W, 4))
    detail[..., 0] = height
    detail[..., 1] = cav
    detail[..., 2] = sid
    detail[..., 3] = 1.0
    return rgba, height, detail


# ----------------------------------------------------------------------------------------------
# Assemblage
# ----------------------------------------------------------------------------------------------
def _height_to_normal(h: np.ndarray, strength: float, wrap_x: bool = False):
    """Normales OpenGL (+Y = haut de l'image = +v) depuis une hauteur. Renvoie (H, W, 3) dans [0,1]."""
    if wrap_x:
        gx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    else:
        gx = np.gradient(h, axis=1)
    gy = -np.gradient(h, axis=0)          # rangée 0 = haut -> dérivée en v = -d/dy
    n = np.dstack([-gx * strength, -gy * strength, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def build_atlas(size: int = SIZE, seed: int = SEED):
    """Renvoie dict(strands=(S,S,4) float, normal=(S,S,3) float, braid_detail=(h,w,4) float)."""
    rng = np.random.default_rng(seed)
    strands = np.zeros((size, size, 4))
    normal = np.zeros((size, size, 3))
    normal[..., :] = (0.5, 0.5, 1.0)
    detail = None
    for name in list(REGIONS):
        x0, y0, x1, y1 = region_px(name, size)
        H, W = y1 - y0, x1 - x0
        sub = np.random.default_rng(rng.integers(1 << 31))
        wrap = name in ("base", "brush", "braid")
        if name.startswith("card"):
            variant = [v for v, r in CARD_VARIANTS.items() if r == name][0]
            rgba, h = gen_card(sub, H, W, variant)
            nstr = 2.2
        elif name == "base":
            rgba, h = gen_base(sub, H, W)
            nstr = 2.2
        elif name == "brush":
            rgba, h = gen_brush(sub, H, W)
            nstr = 2.2
        elif name == "wisp":
            rgba, h = gen_wisp(sub, H, W)
            nstr = 2.0
        elif name == "braid":
            rgba, h, detail = gen_braid(sub, H, W)
            nstr = 9.0
        strands[y0:y1, x0:x1] = rgba
        nm = _height_to_normal(h, nstr, wrap_x=wrap)
        # hors des mèches : normale plate
        a = rgba[..., 3:4] if name != "braid" else np.ones((H, W, 1))
        normal[y0:y1, x0:x1] = nm * np.clip(a * 1.5, 0, 1) + np.array([0.5, 0.5, 1.0]) * (1 - np.clip(a * 1.5, 0, 1))
    # R : facteur interne m (1 = nominal) -> convention du compositeur « 0.5 neutre » (facteur = 0.5 + R)
    strands[..., 0] = np.clip(strands[..., 0] / LUM_NOMINAL - 0.5, 0.0, 1.0)
    # B : quantifié sur 8 bits (identifiant de mèche) — 0 réservé
    strands[..., 2] = np.clip(np.round(strands[..., 2] * 254.0) + 1.0, 1, 255) / 255.0
    return {"strands": np.clip(strands, 0, 1), "normal": np.clip(normal, 0, 1), "braid_detail": np.clip(detail, 0, 1)}


def save_png(arr: np.ndarray, path):
    from PIL import Image

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    a8 = np.round(np.clip(arr, 0, 1) * 255.0).astype(np.uint8)
    mode = "RGBA" if a8.shape[2] == 4 else "RGB"
    Image.fromarray(a8, mode).save(path, optimize=True)
    return path


# ----------------------------------------------------------------------------------------------
# Albedo d'aperçu (formule de référence pour le compositeur ; approximation artistique [A])
# ----------------------------------------------------------------------------------------------
def srgb_to_linear(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(np.asarray(c, np.float64), 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def strands_to_albedo(strands: np.ndarray, color_srgb, tip_srgb=None, tip_amount: float = 0.0):
    """Albedo sRGB (H, W, 4) à partir de hair_strands, avec la MÊME formule que le compositeur du runtime
    (`coat_reference.compose_hair`, lu le 2026-10-05) sans mèches secondaires ni blanches :

        c = mane (linéaire) ; c = mix(c, tip, tip_amount · smoothstep(0.30, 1, G))
        albedo_lin = c · (0.86 + 0.28·B) · (0.5 + R) ;  alpha = A
    """
    R, G, B, A = (strands[..., i] for i in range(4))
    c = np.broadcast_to(srgb_to_linear(color_srgb), strands.shape[:2] + (3,)).copy()
    if tip_srgb is not None and tip_amount > 0:
        k = (tip_amount * _smoothstep(0.30, 1.0, G))[..., None]
        c = c * (1 - k) + srgb_to_linear(tip_srgb) * k
    f = ((0.86 + 0.28 * B) * (0.5 + R))[..., None]
    lin = np.clip(c * f, 0, 1)
    return np.dstack([linear_to_srgb(lin), A])


HAIR_COLORS = {
    # couleurs d'aperçu sRGB (couleur, pointes, part d'éclaircissement des pointes) [A]
    "brown": ((0.16, 0.095, 0.06), (0.30, 0.20, 0.12), 0.25),     # crins bruns foncés (bai)
    "flaxen": ((0.80, 0.69, 0.50), (0.93, 0.87, 0.72), 0.35),     # crins lavés
    "black": ((0.055, 0.047, 0.042), (0.12, 0.10, 0.08), 0.15),
}


def write_textures(out_dir, size: int = SIZE, seed: int = SEED):
    """Écrit hair_strands.png, hair_normal.png, braid_detail.png, hair_albedo_default.png. Renvoie les chemins."""
    out_dir = Path(out_dir)
    atlas = build_atlas(size, seed)
    paths = {
        "strands": save_png(atlas["strands"], out_dir / "hair_strands.png"),
        "normal": save_png(atlas["normal"], out_dir / "hair_normal.png"),
        "braid_detail": save_png(atlas["braid_detail"], out_dir / "braid_detail.png"),
    }
    col, tip, amt = HAIR_COLORS["brown"]
    st8 = np.round(atlas["strands"] * 255.0) / 255.0          # même quantification que le PNG
    paths["albedo_default"] = save_png(strands_to_albedo(st8, col, tip, amt), out_dir / "hair_albedo_default.png")
    return paths, atlas


if __name__ == "__main__":
    import sys
    import time

    t0 = time.time()
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "build" / "textures"
    p, _ = write_textures(out)
    print({k: str(v) for k, v in p.items()}, f"{time.time() - t0:.2f}s")
