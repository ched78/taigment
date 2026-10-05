"""Cartes du pelage (SPEC §4) calculées en 3D aux texels : chaque texel de l'UV0 est rastérisé sur le maillage
basse définition (position 3D, normale, îlot), puis les champs sont évalués dans l'espace du poney — ils sont
donc continus à travers les coutures UV. Les texels hors îlots sont remplis par le plus proche texel valide
(marge de dilatation).

Sémantique exacte des canaux (copiée dans body_meta.json « maps ») :

coat_regions.png (1024², RGBA 8 bits, R échantillonné au plus proche voisin)
  R = id × 16 : 0 corps, 1 tête, 2 bout du nez (lèvres, naseaux, intérieur de bouche/naseaux), 3 oreille ext.,
      4 oreille int., 5–8 membres AG/AD/PG/PD (sous le coude / grasset), 9–12 sabots AG/AD/PG/PD (paroi + sole),
      13 châtaignes / ergots, 14 peau péri-oculaire (bord des paupières + sac conjonctival), 15 peau nue ventrale
      (aine, périnée).
  G = masque « extrémités » (points) : 1 sur les membres (le compositeur applique la hauteur), le bord / la pointe
      des oreilles et le tronçon de la queue ; 0 ailleurs.
  B = masque pangaré : bout du nez, tour des yeux, ventre, faces internes du haut des membres, aine, arrière du coude.
  A = masque charbonné : ligne du dessus (dos, croupe, crête de l'encolure, haut des épaules), dégradé selon la normale.
coat_params.png (1024², RGBA 8 bits)
  R = hauteur de jambe : 0 au sol, 0,10 EXACTEMENT sur la couronne (ligne réelle, pince plus haute que les talons),
      puis linéaire jusqu'à 1 au coude (antérieurs) / au grasset (postérieurs) ; 1 partout ailleurs.
  G = u facial : 0,5 sur la ligne médiane dorsale de la tête ; 0 / 1 sur la ligne médiane ventrale (gauche / droite).
      u = 0,5 ∓ 0,5 · (longueur d'arc depuis la ligne dorsale) / (demi-périmètre de la section) — section ⊥ à
      l'axe de la tête. Côté gauche du poney (x < 0) : u < 0,5.
  B = v facial : 0 au bout du nez (point le plus rostral de la lèvre supérieure) → 1 au plan de la nuque
      (articulation atlanto-occipitale) ; 1 au-delà (encolure, corps).
  A = max(raie de mulet, bande cruciale) : raie de mulet = 1 − d/0,045 m (d ≈ distance à la ligne du dessus, de la
      nuque au bout du tronçon de la queue) ; bande cruciale = bande transversale sur le garrot, descendant ~20 cm sur
      chaque épaule, largeur décroissante.
coat_patterns.png (1024², RGBA 8 bits) — champs 3D continus, normalisés par rang (≈ uniformes sur la surface)
  R = champ pie A (tobiano : bruit basse fréquence + membres + flancs, bas sur la tête),
  G = champ pie B (overo / sabino / splash : bruit découpé + ventre + tête, bas sur la ligne du dos),
  B = champ de taches (léopard) : ≈ 1 au centre d'une tache (cellules de Worley, rayons 1,8–4 cm),
  A = champ de pommelures : ≈ 1 au centre d'une pommelure, 0 sur le réseau (cellules ~7 cm).
coat_shading.png (2048², RGB 8 bits)
  R = détail de luminance du poil (0,5 neutre) : stries orientées selon le sens du poil [A] ;
  G = cavité / AO (1 = aucune occlusion) issue de la cuisson AO de la haute définition ;
  B = peau apparente (0 poil … 1 peau nue).
coat_orm.png (2048², RGB 8 bits) : R occlusion (AO cuite), G rugosité, B métal (0).
coat_normal.png (2048², RGB 8 bits, OpenGL +Y) : cuisson haute → basse définition + stries du poil.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter
from scipy.spatial import cKDTree

from .body_sdf_lib import F32, unit

REGION_IDS = {"body": 0, "head": 1, "muzzle": 2, "ear_outer": 3, "ear_inner": 4, "leg_fl": 5, "leg_fr": 6,
              "leg_hl": 7, "leg_hr": 8, "hoof_fl": 9, "hoof_fr": 10, "hoof_hl": 11, "hoof_hr": 12,
              "chestnut_ergot": 13, "periocular": 14, "ventral_skin": 15}
CORONET_LEG_HEIGHT = 0.10


# ==============================================================================================
# Rastérisation UV
# ==============================================================================================
def rasterize(tri_uv, size, conservative=False):
    """tri_uv (T,3,2) en [0,1] -> (id du triangle (size,size) int64, -1 = vide ; barycentriques (size,size,3)).
    Ligne 0 de l'image = v = 1 (haut). Centre du pixel (r, c) : u = (c + 0.5)/size, v = 1 − (r + 0.5)/size."""
    T = len(tri_uv)
    X = tri_uv[..., 0] * size - 0.5
    Y = (1.0 - tri_uv[..., 1]) * size - 0.5
    tid = np.full((size, size), -1, np.int64)
    bary = np.zeros((size, size, 3), np.float32)
    eps = 0.75 if conservative else 0.0
    x0 = np.clip(np.floor(X.min(1) - eps).astype(int), 0, size - 1)
    x1 = np.clip(np.ceil(X.max(1) + eps).astype(int), 0, size - 1)
    y0 = np.clip(np.floor(Y.min(1) - eps).astype(int), 0, size - 1)
    y1 = np.clip(np.ceil(Y.max(1) + eps).astype(int), 0, size - 1)
    for t in range(T):
        xs = np.arange(x0[t], x1[t] + 1)
        ys = np.arange(y0[t], y1[t] + 1)
        if not len(xs) or not len(ys):
            continue
        gx, gy = np.meshgrid(xs, ys)
        ax, ay = X[t, 0], Y[t, 0]
        bx, by = X[t, 1], Y[t, 1]
        cx, cy = X[t, 2], Y[t, 2]
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l0 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / den
        l1 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / den
        l2 = 1.0 - l0 - l1
        if conservative:
            # tolérance en pixels : distance signée approximative à chaque arête
            e0 = np.hypot(bx - cx, by - cy)
            e1 = np.hypot(cx - ax, cy - ay)
            e2 = np.hypot(ax - bx, ay - by)
            area2 = abs(den)
            tol = np.array([0.75 * e0 / area2, 0.75 * e1 / area2, 0.75 * e2 / area2])
            inside = (l0 >= -tol[0]) & (l1 >= -tol[1]) & (l2 >= -tol[2])
        else:
            inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not inside.any():
            continue
        r, c = gy[inside], gx[inside]
        if conservative:
            free = tid[r, c] < 0
            r, c = r[free], c[free]
            if not len(r):
                continue
            L = np.stack([l0[inside][free], l1[inside][free], l2[inside][free]], -1)
        else:
            L = np.stack([l0[inside], l1[inside], l2[inside]], -1)
        L = np.clip(L, 0.0, 1.0)
        L /= np.maximum(L.sum(-1, keepdims=True), 1e-9)
        tid[r, c] = t
        bary[r, c] = L
    return tid, bary


def pad_nearest(img, valid):
    """Remplit les texels invalides avec la valeur du texel valide le plus proche (dilatation infinie)."""
    _, ind = distance_transform_edt(~valid, return_indices=True)
    return img[ind[0], ind[1]]


class Texels:
    """Texels d'une résolution : position 3D, normale, îlot, triangle — pour les texels couverts."""

    def __init__(self, mesh, size):
        self.size = size
        tid, bary = rasterize(mesh.tri_uv, size, conservative=True)
        self.valid = tid >= 0
        self.rc = np.argwhere(self.valid)
        t = tid[self.valid]
        b = bary[self.valid].astype(np.float64)
        tv = mesh.tri_vert[t]
        self.P = (mesh.V[tv] * b[..., None]).sum(1)
        n = (mesh.VN[tv] * b[..., None]).sum(1)
        self.N = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        self.face = mesh.tri_face[t]
        self.isl = mesh.face_island[self.face]
        self.tri = t

    def image(self, values, fill=0.0, pad=True):
        """values (n,) ou (n,c) -> image (size,size[,c]) avec dilatation."""
        values = np.asarray(values)
        shape = (self.size, self.size) + values.shape[1:]
        img = np.full(shape, fill, values.dtype)
        img[self.valid] = values
        if pad:
            img = pad_nearest(img, self.valid)
        return img


class LowMesh:
    """Données numpy du maillage basse définition nécessaires aux cartes."""

    def __init__(self, V, VN, faces, face_uv, face_island, island_names):
        self.V = np.asarray(V, float)
        self.VN = np.asarray(VN, float)
        tri_vert, tri_uv, tri_face = [], [], []
        for fi, (f, uv) in enumerate(zip(faces, face_uv)):
            for t in range(1, len(f) - 1):
                tri_vert.append([f[0], f[t], f[t + 1]])
                tri_uv.append([uv[0], uv[t], uv[t + 1]])
                tri_face.append(fi)
        self.tri_vert = np.array(tri_vert, np.int64)
        self.tri_uv = np.array(tri_uv, float)
        self.tri_face = np.array(tri_face, np.int64)
        self.face_island = np.asarray(face_island, np.int64)
        self.island_names = list(island_names)


# ==============================================================================================
# Bruits 3D (numpy, déterministes)
# ==============================================================================================
def _hash3(ix, iy, iz, seed):
    h = (ix.astype(np.int64) * 73856093) ^ (iy.astype(np.int64) * 19349663) ^ (iz.astype(np.int64) * 83492791) \
        ^ (seed * 2654435761)
    h = (h ^ (h >> 13)) * 1274126177
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def value_noise3(P, seed=0):
    P = np.asarray(P, float)
    i0 = np.floor(P).astype(np.int64)
    f = P - i0
    w = f * f * f * (f * (f * 6 - 15) + 10)
    out = np.zeros(len(P))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                h = _hash3(i0[:, 0] + dx, i0[:, 1] + dy, i0[:, 2] + dz, seed)
                wx = w[:, 0] if dx else 1 - w[:, 0]
                wy = w[:, 1] if dy else 1 - w[:, 1]
                wz = w[:, 2] if dz else 1 - w[:, 2]
                out += h * wx * wy * wz
    return out


def fbm3(P, scale, octaves=4, seed=0, gain=0.5):
    amp, tot, out = 1.0, 0.0, np.zeros(len(P))
    Q = np.asarray(P, float) / scale
    for o in range(octaves):
        out += amp * value_noise3(Q * (2.0 ** o) + 17.3 * o, seed + 101 * o)
        tot += amp
        amp *= gain
    return out / tot


def rank_normalize(x, weights=None):
    """Remplace x par sa fonction de répartition empirique (valeurs uniformes dans [0,1])."""
    o = np.argsort(x, kind="stable")
    w = np.ones(len(x)) if weights is None else np.asarray(weights, float)
    c = np.cumsum(w[o])
    c = (c - 0.5 * w[o]) / c[-1]
    out = np.empty(len(x))
    out[o] = c
    return out


def surface_samples(mesh, spacing, seed):
    """Points répartis sur la surface (tirage pondéré par l'aire + élimination de type Poisson)."""
    rng = np.random.default_rng(seed)
    T = mesh.tri_vert
    A = mesh.V[T]
    ar = 0.5 * np.linalg.norm(np.cross(A[:, 1] - A[:, 0], A[:, 2] - A[:, 0]), axis=1)
    n = int(ar.sum() / (spacing ** 2) * 3.0)
    t = rng.choice(len(T), n, p=ar / ar.sum())
    r1, r2 = rng.random(n), rng.random(n)
    s = np.sqrt(r1)
    P = A[t, 0] * (1 - s)[:, None] + A[t, 1] * (s * (1 - r2))[:, None] + A[t, 2] * (s * r2)[:, None]
    keep = []
    tree = cKDTree(P)
    taken = np.zeros(n, bool)
    blocked = np.zeros(n, bool)
    for i in rng.permutation(n):
        if blocked[i]:
            continue
        keep.append(i)
        for j in tree.query_ball_point(P[i], spacing * 0.8):
            blocked[j] = True
    return P[np.array(keep)]


# ==============================================================================================
# Calcul des champs
# ==============================================================================================
class FieldContext:
    def __init__(self, sdf, mesh, rig, sdf_geo=None):
        self.sdf = sdf
        self.geo = sdf_geo or sdf          # SDF fermé (sans cavités) pour les requêtes géométriques
        self.mesh = mesh
        self.rig = rig
        self.k = rig.k
        f = sdf.features
        self.H = rig.jh("head")
        self.a = unit(rig.jt("head") - self.H)
        self.dn = unit(np.array([0.0, -self.a[2], self.a[1]]))
        # bout du nez : point le plus rostral (axe de la tête) de la lèvre supérieure
        tips = mesh.V[np.argsort(-(mesh.V - self.H) @ self.a)[:50]]
        self.s_tip = float(((tips - self.H) @ self.a).max())
        self.s_poll = 0.0
        self.nostril_s = float(np.mean([(f[f"nostril_{s}"].Nc - self.H) @ self.a for s in "lr"]))
        self._face_table()
        self._topline()

    # --- coordonnées faciales -----------------------------------------------------------
    def _face_table(self):
        """Table (s, φ) -> longueur d'arc depuis la ligne dorsale, sur la section ⊥ à l'axe de la tête."""
        from .body_sdf_lib import ray_surface_batch

        sdf = self.geo
        X = np.array([1.0, 0.0, 0.0])
        ss = np.linspace(-0.02 * self.k, self.s_tip - 0.012 * self.k, 70)
        phis = np.linspace(0.0, math.pi, 49)
        R = np.zeros((len(ss), len(phis)))
        for i, s in enumerate(ss):
            # centre de la section : milieu entre le dessus et le dessous sur la ligne médiane
            c0 = self.H + s * self.a
            up, ok1 = ray_surface_batch(lambda P: sdf(P), c0[None] - 0.0 * self.dn, self.dn[None], t_max=0.3)
            dw, ok2 = ray_surface_batch(lambda P: sdf(P), c0[None], -self.dn[None], t_max=0.3)
            c = 0.5 * (up[0] + dw[0]) if (ok1[0] and ok2[0]) else c0
            dirs = np.array([math.cos(p) * self.dn + math.sin(p) * X for p in phis])
            pts, ok = ray_surface_batch(lambda P: sdf(P), np.repeat(c[None], len(phis), 0), dirs, t_max=0.35)
            r = np.linalg.norm(pts - c, axis=1)
            r[~ok] = np.nan
            if np.isnan(r).all():
                r[:] = 0.05
            r = np.where(np.isnan(r), np.nanmedian(r), r)
            R[i] = r
            if i == 0:
                self._centers = []
            self._centers.append(c)
        self._centers = np.array(self._centers)
        dphi = phis[1] - phis[0]
        arc = np.zeros_like(R)
        for j in range(1, len(phis)):
            dr = R[:, j] - R[:, j - 1]
            rm = 0.5 * (R[:, j] + R[:, j - 1])
            arc[:, j] = arc[:, j - 1] + np.sqrt((rm * dphi) ** 2 + dr ** 2)
        self._ss, self._phis, self._frac = ss, phis, arc / arc[:, -1:]

    def face_uv(self, P):
        s = (P - self.H) @ self.a
        si = np.clip(np.interp(s, self._ss, np.arange(len(self._ss))), 0, len(self._ss) - 1)
        i0 = np.floor(si).astype(int)
        i1 = np.minimum(i0 + 1, len(self._ss) - 1)
        t = si - i0
        c = self._centers[i0] * (1 - t)[:, None] + self._centers[i1] * t[:, None]
        D = P - c
        D -= (D @ self.a)[:, None] * self.a
        phi = np.arccos(np.clip(unit_rows(D) @ self.dn, -1, 1))
        pj = np.interp(phi, self._phis, np.arange(len(self._phis)))
        j0 = np.clip(np.floor(pj).astype(int), 0, len(self._phis) - 1)
        j1 = np.minimum(j0 + 1, len(self._phis) - 1)
        tj = pj - j0
        fr = ((self._frac[i0, j0] * (1 - tj) + self._frac[i0, j1] * tj) * (1 - t) +
              (self._frac[i1, j0] * (1 - tj) + self._frac[i1, j1] * tj) * t)
        sign = np.sign(P[:, 0] - c[:, 0])
        u = 0.5 + 0.5 * sign * fr
        v = np.clip((self.s_tip - s) / (self.s_tip - self.s_poll), 0.0, 1.0)
        return u, v

    # --- ligne du dessus ------------------------------------------------------------------
    def _topline(self):
        from .body_sdf_lib import ray_surface_batch

        ys = np.linspace(-0.95 * self.k, 0.95 * self.k, 191)
        zs = np.linspace(2.0 * self.k, 0.3 * self.k, 1701)
        Y, Z = np.meshgrid(ys, zs, indexing="ij")
        Pq = np.stack([np.zeros(Y.size), Y.ravel(), Z.ravel()], 1).astype(F32)
        d = self.geo(Pq).reshape(Y.shape)
        inside = d <= 0
        first = np.argmax(inside, axis=1)
        top = np.where(inside.any(1), zs[first], np.nan)
        self._top_y, self._top_z = ys, top

    def topline_drop(self, P):
        zt = np.interp(P[:, 1], self._top_y, np.nan_to_num(self._top_z, nan=0.0))
        return zt - P[:, 2]


def unit_rows(A):
    return A / np.maximum(np.linalg.norm(A, axis=1, keepdims=True), 1e-12)


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def leg_height(ctx, P, key):
    """Hauteur de jambe (0 sol, 0.10 couronne, 1 coude / grasset) pour le membre `key`."""
    hf = ctx.sdf.features[f"hoof_{key}"]
    rig = ctx.rig
    side = key[1]
    zref = rig.jh(("forearm_" if key[0] == "f" else "gaskin_") + side)[2]
    fl = (P - hf.O) @ hf.fwd
    zcor = hf.coronet_heel + (hf.coronet_toe - hf.coronet_heel) * np.clip((fl + hf.Lb) / (hf.Lf + hf.Lb), 0, 1)
    z = P[:, 2]
    below = CORONET_LEG_HEIGHT * np.clip(z / zcor, 0, 1)
    above = CORONET_LEG_HEIGHT + (1 - CORONET_LEG_HEIGHT) * np.clip((z - zcor) / (zref - zcor), 0, 1)
    return np.where(z < zcor, below, above)


def compute_fields(ctx: FieldContext, tx: Texels, log=print):
    """Renvoie un dict de tableaux (n,) par champ, pour les texels `tx`."""
    sdf = ctx.sdf
    rig = ctx.rig
    k = ctx.k
    P, N = tx.P, tx.N
    names = np.array(ctx.mesh.island_names, object)[tx.isl]
    n = len(P)
    out = {}
    feats = sdf.features
    # distances aux groupes anatomiques
    groups = ["trunk", "neck", "head", "tail"] + [f"fore_{s}" for s in "lr"] + [f"hind_{s}" for s in "lr"] + \
             [f"chestnut_{l}{s}" for l in "fh" for s in "lr"] + [f"ergot_{l}{s}" for l in "fh" for s in "lr"]
    dist = sdf.region_distances(P.astype(F32), groups)
    rid = np.zeros(n, np.int64)
    s_ax = (P - ctx.H) @ ctx.a
    # --- membres et hauteur de jambe
    legh = np.ones(n)
    leg_key = np.full(n, "", object)
    trunk_d = np.minimum(np.minimum(dist["trunk"], dist["neck"]), dist["tail"])
    for key, grp in (("fl", "fore_l"), ("fr", "fore_r"), ("hl", "hind_l"), ("hr", "hind_r")):
        isleg = (names == f"leg_{key}") | (names == f"hoofwall_{key}") | (names == f"sole_{key}")
        h = leg_height(ctx, P, key)
        near = (names == "body") & (dist[grp] < trunk_d - 0.002) & (h < 1.0) & \
               (np.sign(P[:, 0]) == (-1 if key[1] == "l" else 1))
        m = isleg | near
        legh = np.where(m, h, legh)
        leg_key[m] = key
        rid[m] = REGION_IDS[f"leg_{key}"]
        hoof = (names == f"hoofwall_{key}") | (names == f"sole_{key}")
        rid[hoof] = REGION_IDS[f"hoof_{key}"]
        legh = np.where(hoof, np.minimum(h, CORONET_LEG_HEIGHT), legh)
    # châtaignes / ergots
    horn = np.zeros(n, bool)
    for gname in groups:
        if gname.startswith(("chestnut", "ergot")):
            horn |= dist[gname] < 0.0012 * k
    rid[horn & (rid >= 5) & (rid <= 8)] = REGION_IDS["chestnut_ergot"]
    # --- tête, bout du nez, oreilles, yeux
    head = names == "head"
    rid[head] = REGION_IDS["head"]
    muzzle_s = ctx.nostril_s - 0.035 * k
    muzzle = head & (s_ax > muzzle_s)
    rid[muzzle] = REGION_IDS["muzzle"]
    inner = np.zeros(n, bool)
    for side in "lr":
        ea = feats[f"ear_{side}"]
        m = names == f"ear_{side}"
        inn = m & ((N @ ea.f) > 0.15)
        rid[m] = REGION_IDS["ear_outer"]
        rid[inn] = REGION_IDS["ear_inner"]
        inner |= inn
    peri = np.zeros(n, bool)
    eye_prox = np.zeros(n)
    for side in "lr":
        ef = feats[f"eye_{side}"]
        r = np.linalg.norm(P - ef.C, axis=1)
        fs = ef.fissure_sdf(P)
        rim = (r < ef.R_out + 0.004 * k) & (fs < 0.006 * k)
        peri |= rim | (names == f"pocket_eye_{side}")
        eye_prox = np.maximum(eye_prox, np.exp(-np.maximum(r - ef.R_out, 0) / (0.022 * k)))
    rid[peri] = REGION_IDS["periocular"]
    for nm in ("pocket_nostril_l", "pocket_nostril_r", "pocket_mouth_roof", "pocket_mouth_floor"):
        rid[names == nm] = REGION_IDS["muzzle"]
    # --- peau nue ventrale (aine / périnée)
    groin = (names == "body") & (np.abs(P[:, 0]) < 0.075 * k) & (P[:, 1] < -0.28 * k) & (P[:, 1] > -0.66 * k) & \
            (N[:, 2] < -0.25) & (P[:, 2] < 0.98 * k)
    anus_c = rig.p("hips", (0.0, -0.785, 1.10))
    perineum = (names == "body") & (np.linalg.norm(P - anus_c, axis=1) < 0.035 * k)
    rid[groin | perineum] = REGION_IDS["ventral_skin"]
    out["region"] = rid
    # --- extrémités (points)
    tail = dist["tail"] < np.minimum(dist["trunk"], 1.0) - 0.004
    ext = np.zeros(n)
    ext[(rid >= 5) & (rid <= 8)] = 1.0
    ext[rid == 13] = 1.0
    for side in "lr":
        ea = feats[f"ear_{side}"]
        m = names == f"ear_{side}"
        t = ((P - ea.B) @ ea.e) / ea.length
        rimv = np.abs(N @ ea.g)
        e = np.maximum(_smooth(0.62, 0.85, t), _smooth(0.55, 0.85, rimv) * (rid == REGION_IDS["ear_outer"]))
        ext[m] = e[m]
    ext[tail & (names == "body")] = 1.0
    out["extremities"] = ext
    # --- pangaré
    pan = np.zeros(n)
    pan = np.maximum(pan, _smooth(muzzle_s - 0.03 * k, muzzle_s + 0.03 * k, s_ax) * (head | muzzle))
    pan = np.maximum(pan, eye_prox * (head | peri))
    belly = _smooth(-0.15, -0.75, N[:, 2]) * _smooth(0.95 * k, 0.80 * k, P[:, 2]) * (names == "body")
    pan = np.maximum(pan, belly)
    for key, grp in (("fl", "fore_l"), ("fr", "fore_r"), ("hl", "hind_l"), ("hr", "hind_r")):
        sx = -1.0 if key[1] == "l" else 1.0
        med = _smooth(0.2, 0.7, N[:, 0] * -sx) * (leg_key == key) * _smooth(0.45, 0.70, legh)
        pan = np.maximum(pan, med)
    pan = np.maximum(pan, (rid == REGION_IDS["ventral_skin"]) * 1.0)
    out["pangare"] = np.clip(pan, 0, 1)
    # --- charbonné
    drop = ctx.topline_drop(P)
    dorsal = _smooth(0.10, 0.75, N[:, 2]) * _smooth(0.32 * k, 0.05 * k, drop)
    sooty = dorsal * ((names == "body") & ~tail) * (0.75 + 0.25 * fbm3(P, 0.12 * k, 3, seed=31))
    out["sooty"] = np.clip(sooty, 0, 1)
    # --- coordonnées faciales
    fu, fv = ctx.face_uv(P)
    facial = head | muzzle | inner | (rid == REGION_IDS["ear_outer"]) | peri | \
        np.isin(names, ["pocket_nostril_l", "pocket_nostril_r", "pocket_mouth_roof", "pocket_mouth_floor",
                        "pocket_eye_l", "pocket_eye_r"])
    near_head = (names == "body") & (s_ax > -0.12 * k)
    out["face_u"] = np.where(facial | near_head, fu, 0.5)
    out["face_v"] = np.where(facial | near_head, fv, 1.0)
    out["leg_height"] = legh
    # --- raie de mulet + bande cruciale
    lat = np.abs(P[:, 0])
    d = np.sqrt(lat ** 2 + np.maximum(drop, 0) ** 2)
    poll_y = rig.jh("head")[1]
    on_back = ((names == "body") & ~tail) & (P[:, 1] < poll_y - 0.01 * k)
    stripe = np.clip(1.0 - d / (0.045 * k), 0, 1) * on_back * _smooth(0.0, 0.3, N[:, 2] + 0.2)
    # queue : face postérieure du tronçon
    tstripe = np.clip(1.0 - lat / (0.022 * k), 0, 1) * tail * _smooth(0.0, 0.5, -N[:, 1] + 0.2 * N[:, 2])
    w_top = rig.p("spine_03", (0.0, 0.27, 1.30))
    yb = w_top[1] - 0.15 * (P[:, 2] - w_top[2])
    zz = (w_top[2] - P[:, 2]) / k
    width = (0.034 - 0.10 * np.clip(zz, 0, 0.22)) * k
    bar = np.clip(1.0 - np.abs(P[:, 1] - yb) / np.maximum(width, 1e-3), 0, 1) * _smooth(0.24, 0.12, zz) * \
        (names == "body") * (np.abs(P[:, 0]) < 0.26 * k)
    out["dorsal"] = np.clip(np.maximum(np.maximum(stripe, tstripe), bar), 0, 1)
    # --- motifs (champs 3D)
    w_area = np.ones(n)
    n1 = fbm3(P, 0.32 * k, 3, seed=1)
    flank = _smooth(0.95 * k, 0.75 * k, P[:, 2]) * (names == "body")
    tob = 0.60 * n1 + 0.40 * (1 - legh) * (leg_key != "") + 0.20 * flank - 0.45 * (head | muzzle)
    out["pat_tobiano"] = rank_normalize(tob, w_area)
    n2 = fbm3(P, 0.16 * k, 4, seed=2, gain=0.6)
    ventral = _smooth(1.05 * k, 0.65 * k, P[:, 2])
    ov = 0.55 * n2 + 0.45 * ventral * (names == "body") + 0.30 * (head | muzzle) - 0.5 * _smooth(0.4, 0.9, N[:, 2]) * (
        drop < 0.15 * k)
    out["pat_overo"] = rank_normalize(ov, w_area)
    # taches (léopard) : cellules de Worley sur la surface
    cen = surface_samples(ctx.mesh, 0.085 * k, seed=3)
    rng = np.random.default_rng(4)
    rad = rng.uniform(0.018, 0.040, len(cen)) * k
    tree = cKDTree(cen)
    dd, ii = tree.query(P, k=4)
    spot = np.max(np.clip(1.0 - dd / rad[ii], 0, 1), axis=1) ** 0.7
    out["pat_spots"] = spot
    cen2 = surface_samples(ctx.mesh, 0.070 * k, seed=5)
    d2, _ = cKDTree(cen2).query(P, k=2)
    dap = np.clip((d2[:, 1] - d2[:, 0]) / (0.5 * 0.070 * k), 0, 1) ** 0.8
    out["pat_dapple"] = dap
    # --- peau nue
    skin = np.zeros(n)
    skin = np.maximum(skin, _smooth(ctx.nostril_s - 0.02 * k, ctx.nostril_s + 0.015 * k, s_ax) * (head | muzzle) * 0.85)
    for side in "lr":
        nf = feats[f"nostril_{side}"]
        skin = np.maximum(skin, np.exp(-(np.linalg.norm(P - nf.Nc, axis=1) / (0.022 * k)) ** 2))
    for side in "lr":
        ef = feats[f"eye_{side}"]
        fs = ef.fissure_sdf(P)
        r = np.linalg.norm(P - ef.C, axis=1)
        skin = np.maximum(skin, _smooth(0.007 * k, 0.001 * k, fs) * (r < ef.R_out + 0.006 * k))
    pocket = np.array([nm.startswith("pocket_") for nm in names])
    skin[pocket] = 1.0
    skin = np.maximum(skin, 0.75 * (rid == REGION_IDS["ventral_skin"]))
    skin = np.maximum(skin, 0.35 * inner)
    out["bare_skin"] = np.clip(skin, 0, 1)
    # --- rugosité
    rough = np.full(n, 0.78)
    rough = rough * (1 - skin) + 0.52 * skin
    rough[pocket] = 0.32
    rough[(rid >= 9) & (rid <= 12)] = 0.62
    rough[rid == 13] = 0.70
    out["roughness"] = rough
    out["names"] = names
    out["tail"] = tail
    out["head_like"] = facial
    out["leg_key"] = leg_key
    return out


def hair_flow(ctx: FieldContext, P, N, names, leg_key):
    """Direction du poil (tangente unitaire) [A] : vers le bas et l'arrière sur le corps, vers le bas sur les
    membres, vers le nez sur la tête, vers la pointe sur les oreilles."""
    D = np.tile(unit(np.array([0.0, -0.80, -0.60])), (len(P), 1))
    legm = leg_key != ""
    D[legm] = [0.0, 0.0, -1.0]
    headm = np.isin(names, ["head"])
    D[headm] = unit(ctx.a + 0.25 * np.array([0, 0, -1.0]))
    for side in "lr":
        ea = ctx.sdf.features[f"ear_{side}"]
        D[names == f"ear_{side}"] = ea.e
    D -= (D * N).sum(1)[:, None] * N
    return unit_rows(D)


def streak_noise(P, D, k=1.0, seed=9):
    """Bruit strié le long de D (moyenne de bruits isotropes le long du poil) : ≈ centré sur 0, écart-type ~1."""
    acc = np.zeros(len(P))
    for j, t in enumerate(np.linspace(-0.006, 0.006, 5) * k):
        Q = P + t * D
        acc += value_noise3(Q / (0.0016 * k), seed) + 0.5 * value_noise3(Q / (0.0007 * k), seed + 7)
    acc /= 5 * 1.5
    acc -= acc.mean()
    return acc / max(acc.std(), 1e-6)
