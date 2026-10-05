"""Pièces de la tête hors du maillage `Body` : globes oculaires (`Eyes`), bouche (`Mouth` : gencives,
incisives, langue) et cartes alpha (`Lashes` : cils + vibrisses). Géométrie numpy pure (aucun bpy) ;
la création des objets Blender est faite par `body_scene`.

Toutes les pièces sont placées à partir des descripteurs du SDF (`body_sdf.BodySDF.features`), donc du gabarit
(joints `eye_*`, `jaw`, etc.) : elles suivent les changements de forme de la tête.

Contrat UV des yeux (SPEC §4, texture d'iris de l'agent « robe » `coat_reference.compose_iris`)
-------------------------------------------------------------------------------------------------
- Chaque globe occupe tout le carré UV [0,1]² (les deux yeux partagent la texture `iris_default.png`).
- Le centre de la cornée (axe optique) est en (0.5, 0.5) ; u croît vers l'avant (canthus médial, rostral),
  v croît vers le haut (dorsal) — la granula iridica de la texture (haut de l'image) est donc en haut.
- Projection azimutale « elliptique » : un point du globe à l'angle (θx horizontal, θy vertical) de l'axe optique
  a pour UV (0.5 + IRIS_U · θx/θh, 0.5 + IRIS_V · θy/θv) tant qu'il est dans la cornée ; le limbe (bord de l'iris,
  bord de la cornée bombée) est l'ellipse angulaire θh × θv. IRIS_U / IRIS_V = demi-axes de l'iris de la texture
  (lus dans coat_reference : IRIS_RX/2, IRIS_RY/2 = 0.43 × 0.37) ; pupille horizontale le long de u
  (PUPIL_RX/2 × PUPIL_RY/2 = 0.25 × 0.095 en UV). Au-delà du limbe : sclère, rayon UV comprimé vers 0.5.
- Valeurs exactes exportées dans body_meta.json (« eyes »).

[A] Dimensions : globe R 19 mm (longueur axiale « poney » 38,9 mm, anatomy.md §2.3 [U]) ; cornée elliptique
±52° × ±38° autour de l'axe optique, bombement 1,4 mm ; incisives, gencives, langue, cils, vibrisses :
approximations artistiques non sourcées.
"""
from __future__ import annotations

import math

import numpy as np

from .body_sdf_lib import F32, unit

try:  # contrat de la texture d'iris (agent « robe »)
    from .coat_reference import IRIS_RX as _IRX, IRIS_RY as _IRY, PUPIL_RX as _PRX, PUPIL_RY as _PRY
except Exception:  # pragma: no cover - repli si le module n'est pas importable
    _IRX, _IRY, _PRX, _PRY = 0.86, 0.74, 0.50, 0.19

IRIS_U = 0.5 * _IRX          # demi-axe horizontal de l'iris en UV
IRIS_V = 0.5 * _IRY          # demi-axe vertical de l'iris en UV
PUPIL_U = 0.5 * _PRX
PUPIL_V = 0.5 * _PRY
LIMBUS_H = math.radians(52.0)   # [A] demi-angle horizontal de la cornée
LIMBUS_V = math.radians(38.0)   # [A] demi-angle vertical
CORNEA_BULGE = 0.0014           # [A] m
GLOBE_R = 0.0190                # [A] m (≈ 38 mm de longueur axiale)


class PartMesh:
    """Maillage simple : V (n,3), F (liste de tuples d'indices), UV par coin (même structure que F),
    groupes (nom -> indices de sommets), attributs par sommet."""

    def __init__(self, name):
        self.name = name
        self.V = []
        self.F = []
        self.UV = []
        self.groups = {}
        self.attrs = {}

    def add_verts(self, P, group=None):
        i0 = len(self.V)
        self.V.extend([np.asarray(p, float) for p in P])
        idx = list(range(i0, len(self.V)))
        if group:
            self.groups.setdefault(group, []).extend(idx)
        return idx

    def add_face(self, f, uv):
        self.F.append(tuple(int(i) for i in f))
        self.UV.append([tuple(float(c) for c in t) for t in uv])

    def arrays(self):
        return np.array(self.V, float), self.F, self.UV

    def tri_count(self):
        return sum(len(f) - 2 for f in self.F)


# ==============================================================================================
# Yeux
# ==============================================================================================
def _eye_dir(ef, q, phi, q_max=3.0):
    """Direction (unitaire) sur le globe pour la coordonnée elliptique (q, φ) ; q = 1 au limbe."""
    lim = math.hypot(LIMBUS_H * math.cos(phi), LIMBUS_V * math.sin(phi))   # angle du limbe dans la direction φ
    az = math.atan2(LIMBUS_V * math.sin(phi), LIMBUS_H * math.cos(phi))
    if q <= 1.0:
        th = q * lim
    else:
        th = lim + (q - 1.0) / (q_max - 1.0) * (math.pi - lim)
    d = math.cos(th) * ef.g + math.sin(th) * (math.cos(az) * ef.h + math.sin(az) * ef.v)
    return unit(d), th


def _eye_uv(q, phi, q_max=3.0):
    if q <= 1.0:
        return 0.5 + IRIS_U * q * math.cos(phi), 0.5 + IRIS_V * q * math.sin(phi)
    # sclère : de l'ellipse de l'iris vers le bord du carré (rayon UV ≤ 0.49), compression douce
    t = (q - 1.0) / (q_max - 1.0)
    ru = IRIS_U + (0.49 - IRIS_U) * (1.0 - (1.0 - t) ** 2)
    rv = IRIS_V + (0.49 - IRIS_V) * (1.0 - (1.0 - t) ** 2)
    return 0.5 + ru * math.cos(phi), 0.5 + rv * math.sin(phi)


def build_eyes(features, scale=1.0, n_phi=36):
    """Deux globes (≈ 1,2 k triangles chacun) centrés sur les joints eye_l / eye_r."""
    pm = PartMesh("Eyes")
    qs = [0.0, 0.07, 0.15, 0.24, 0.34, 0.45, 0.57, 0.70, 0.84, 0.95, 1.0, 1.06, 1.18, 1.35, 1.6, 1.95, 2.35, 2.7, 3.0]
    Rg = GLOBE_R * scale
    for side in ("l", "r"):
        ef = features[f"eye_{side}"]
        grp = f"eye_{side}"
        rows = []
        for q in qs[1:-1]:
            ring = []
            for k in range(n_phi):
                phi = 2 * math.pi * k / n_phi
                d, _ = _eye_dir(ef, q, phi)
                r = Rg + (CORNEA_BULGE * scale * max(0.0, 1.0 - q * q) ** 1.5 if q < 1.0 else 0.0)
                ring.append(ef.C + r * d)
            rows.append(pm.add_verts(ring, grp))
        apex = pm.add_verts([ef.C + (Rg + CORNEA_BULGE * scale) * ef.g], grp)[0]
        back = pm.add_verts([ef.C - Rg * ef.g], grp)[0]
        # orientation : faces vers l'extérieur du globe (vérifiée par le test de normales de body_scene)
        q1 = qs[1]
        for k in range(n_phi):
            k2 = (k + 1) % n_phi
            p1, p2 = 2 * math.pi * k / n_phi, 2 * math.pi * (k + 1) / n_phi
            pm.add_face((apex, rows[0][k], rows[0][k2]), [(0.5, 0.5), _eye_uv(q1, p1), _eye_uv(q1, p2)])
        for i in range(len(rows) - 1):
            qa, qb = qs[i + 1], qs[i + 2]
            for k in range(n_phi):
                k2 = (k + 1) % n_phi
                p1, p2 = 2 * math.pi * k / n_phi, 2 * math.pi * (k + 1) / n_phi
                pm.add_face((rows[i][k], rows[i + 1][k], rows[i + 1][k2], rows[i][k2]),
                            [_eye_uv(qa, p1), _eye_uv(qb, p1), _eye_uv(qb, p2), _eye_uv(qa, p2)])
        ql = qs[-2]
        for k in range(n_phi):
            k2 = (k + 1) % n_phi
            p1, p2 = 2 * math.pi * k / n_phi, 2 * math.pi * (k + 1) / n_phi
            u1, u2 = _eye_uv(ql, p1), _eye_uv(ql, p2)
            pm.add_face((rows[-1][k], back, rows[-1][k2]), [u1, (0.5 + 0.49 * math.cos(0.5 * (p1 + p2)),
                                                                0.5 + 0.49 * math.sin(0.5 * (p1 + p2))), u2])
    _orient_outward(pm, {s: features[f"eye_{s}"].C for s in "lr"}, "eye_")
    return pm


def _orient_outward(pm, centers, prefix):
    """Retourne les faces dont la normale pointe vers le centre de leur groupe (globe convexe)."""
    V = np.array(pm.V)
    owner = np.zeros(len(V), object)
    for side, c in centers.items():
        for i in pm.groups.get(f"{prefix}{side}", []):
            owner[i] = side
    newF, newUV = [], []
    for f, uv in zip(pm.F, pm.UV):
        P = V[list(f)]
        n = np.cross(P[1] - P[0], P[2] - P[0])
        c = centers[owner[f[0]]]
        if np.dot(n, P.mean(0) - c) < 0:
            f = tuple(reversed(f))
            uv = list(reversed(uv))
        newF.append(f)
        newUV.append(uv)
    pm.F, pm.UV = newF, newUV


def eye_meta(features):
    out = {}
    for side in "lr":
        ef = features[f"eye_{side}"]
        out[side] = dict(center=[round(float(c), 5) for c in ef.C], optical_axis=[round(float(c), 4) for c in ef.g],
                         u_axis=[round(float(c), 4) for c in ef.h], v_axis=[round(float(c), 4) for c in ef.v])
    return dict(globe_radius_m=GLOBE_R, cornea_bulge_m=CORNEA_BULGE,
                limbus_half_angles_deg=[math.degrees(LIMBUS_H), math.degrees(LIMBUS_V)],
                uv_center=[0.5, 0.5], iris_uv_half_axes=[IRIS_U, IRIS_V], pupil_uv_half_axes=[PUPIL_U, PUPIL_V],
                uv_axes="u = horizontal vers l'avant (canthus médial), v = dorsal (haut) ; pupille horizontale le long de u",
                uv_sclera="hors de l'ellipse de l'iris : sclère, rayon UV comprimé ≤ 0.49 (arrière du globe)",
                per_eye=out)


# ==============================================================================================
# Bouche : gencives, incisives, langue
# ==============================================================================================
MOUTH_UV = {  # zones de la texture coat_mouth_albedo.png (u0, v0, u1, v1)
    "gum": (0.0, 0.5, 0.5, 1.0),
    "tooth": (0.5, 0.5, 1.0, 1.0),
    "tongue": (0.0, 0.0, 1.0, 0.5),
}


def _zone_uv(zone, a, b):
    u0, v0, u1, v1 = MOUTH_UV[zone]
    return (u0 + (u1 - u0) * min(max(a, 0.0), 1.0), v0 + (v1 - v0) * min(max(b, 0.0), 1.0))


def _ellipsoid_part(pm, c, R, r, group, zone, n_u=16, n_v=10, squash=None):
    """Ellipsoïde (centre c, axes colonnes de R, demi-axes r) en grille lat-long."""
    idx_rows = []
    for j in range(1, n_v):
        th = math.pi * j / n_v
        ring = []
        for i in range(n_u):
            ph = 2 * math.pi * i / n_u
            q = np.array([math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)])
            if squash is not None:
                q = squash(q)
            ring.append(c + R @ (q * r))
        idx_rows.append(pm.add_verts(ring, group))
    top = pm.add_verts([c + R @ np.array([0, 0, r[2]])], group)[0]
    bot = pm.add_verts([c + R @ np.array([0, 0, -r[2]])], group)[0]
    for i in range(n_u):
        i2 = (i + 1) % n_u
        pm.add_face((top, idx_rows[0][i], idx_rows[0][i2]),
                    [_zone_uv(zone, (i + 0.5) / n_u, 1.0), _zone_uv(zone, i / n_u, 1 - 1 / n_v),
                     _zone_uv(zone, (i + 1) / n_u, 1 - 1 / n_v)])
    for j in range(len(idx_rows) - 1):
        for i in range(n_u):
            i2 = (i + 1) % n_u
            va, vb = 1 - (j + 1) / n_v, 1 - (j + 2) / n_v
            pm.add_face((idx_rows[j][i], idx_rows[j + 1][i], idx_rows[j + 1][i2], idx_rows[j][i2]),
                        [_zone_uv(zone, i / n_u, va), _zone_uv(zone, i / n_u, vb),
                         _zone_uv(zone, (i + 1) / n_u, vb), _zone_uv(zone, (i + 1) / n_u, va)])
    for i in range(n_u):
        i2 = (i + 1) % n_u
        pm.add_face((bot, idx_rows[-1][i2], idx_rows[-1][i]),
                    [_zone_uv(zone, (i + 0.5) / n_u, 0.0), _zone_uv(zone, (i + 1) / n_u, 1 / n_v),
                     _zone_uv(zone, i / n_u, 1 / n_v)])
    return [*sum(idx_rows, []), top, bot]


def _box_part(pm, c, R, half, group, zone, round_k=0.6):
    """Petite boîte arrondie (dent) : ellipsoïde « carré » (super-ellipsoïde) 8×6."""
    def sq(q):
        e = 0.45
        return np.sign(q) * np.abs(q) ** e
    return _ellipsoid_part(pm, c, R, half, group, zone, n_u=10, n_v=6, squash=sq)


def build_mouth(features, sdf_full=None, scale=1.0, log=print):
    """Gencives + 2 × 6 incisives + langue dans la cavité buccale (lentille du SDF), ≈ 2 k triangles.

    Repère : centre de la cavité cav_c, axes am (rostral), xh (latéral), nm (haut). Les pièces « inférieures »
    (incisives inférieures, gencive inférieure, langue) forment le groupe `jaw` (suivent la mâchoire)."""
    mf = features["mouth"]
    pm = PartMesh("Mouth")
    am, xh, nm = unit(mf.am), unit(mf.xh), unit(mf.nm)
    a, b, c = mf.cav_r                       # demi-axes de la cavité (am, xh, nm)
    O = np.asarray(mf.cav_c, float)
    R0 = np.stack([am, xh, nm], 1)

    def P(s, x, z):
        return O + s * am + x * xh + z * nm

    # arcade incisive : demi-cercle de rayon ra, centre (sa, 0), dans le plan buccal
    ra = min(0.40 * a, 0.72 * b)
    sa = 0.80 * a - ra
    tooth_h = 0.42 * c
    for jaw_side, sgn in (("upper", 1.0), ("lower", -1.0)):
        grp = "jaw" if sgn < 0 else "head"
        # incisives : 6 dents réparties sur ±75° de l'arcade
        for k in range(6):
            ang = math.radians(-75 + 30 * k)
            cpos = P(sa + ra * math.cos(ang), ra * math.sin(ang), sgn * (0.6 * tooth_h + 0.0008))
            radial = unit(math.cos(ang) * am + math.sin(ang) * xh)
            tang = unit(np.cross(nm, radial))
            Rt = np.stack([radial, tang, nm], 1)
            half = np.array([0.0042, 0.0058, 0.55 * tooth_h]) * scale
            _box_part(pm, cpos, Rt, half, grp, "tooth")
        # gencive : boudin en arc (tube) au-dessus/dessous des dents, prolongé vers les barres
        n_arc = 14
        arc = []
        for k in range(n_arc):
            ang = math.radians(-95 + 190 * k / (n_arc - 1))
            arc.append((sa + ra * math.cos(ang) - 0.0012, ra * math.sin(ang)))
        gum_rows = []
        for (s0, x0) in arc:
            radial = unit((s0 - sa) * am + x0 * xh) if abs(s0 - sa) + abs(x0) > 1e-6 else am
            ring = []
            for j in range(6):
                t = 2 * math.pi * j / 6
                rr = np.array([0.0040, 0.0035]) * scale
                off = math.cos(t) * rr[0] * radial + math.sin(t) * rr[1] * nm
                ring.append(P(s0, x0, sgn * (1.15 * tooth_h + 0.0005)) + off)
            gum_rows.append(pm.add_verts(ring, grp))
        for i in range(len(gum_rows) - 1):
            for j in range(6):
                j2 = (j + 1) % 6
                f = (gum_rows[i][j], gum_rows[i + 1][j], gum_rows[i + 1][j2], gum_rows[i][j2])
                uv = [_zone_uv("gum", i / n_arc, j / 6), _zone_uv("gum", (i + 1) / n_arc, j / 6),
                      _zone_uv("gum", (i + 1) / n_arc, (j + 1) / 6), _zone_uv("gum", i / n_arc, (j + 1) / 6)]
                pm.add_face(f if sgn > 0 else f[::-1], uv if sgn > 0 else uv[::-1])
        # bouchons des extrémités du boudin
        for row in (gum_rows[0], gum_rows[-1]):
            cidx = pm.add_verts([np.mean([pm.V[i] for i in row], 0)], grp)[0]
            for j in range(6):
                j2 = (j + 1) % 6
                pm.add_face((cidx, row[j], row[j2]), [_zone_uv("gum", 0.5, 0.5)] * 3)
    # langue : ellipsoïde aplati sur le plancher, pointe arrondie vers l'avant
    tc = P(-0.05 * a, 0.0, -0.40 * c)
    _ellipsoid_part(pm, tc, R0, np.array([0.62 * a, 0.52 * b, 0.26 * c]), "jaw", "tongue", n_u=20, n_v=12)
    V = np.array(pm.V)
    # contrôle : tout doit être dans la cavité (SDF complet > 0 = vide)
    if sdf_full is not None:
        d = sdf_full(V.astype(F32))
        bad = int((d < 0.0003).sum())
        if bad:
            # rapproche les sommets fautifs du centre de la cavité (homothétie locale) jusqu'à les loger
            for _ in range(8):
                d = sdf_full(np.array(pm.V, F32))
                idx = np.flatnonzero(d < 0.0003)
                if not len(idx):
                    break
                for i in idx:
                    pm.V[i] = O + 0.93 * (pm.V[i] - O)
            d = sdf_full(np.array(pm.V, F32))
            log(f"[mouth] {bad} sommets hors cavité corrigés ; restants {int((d < 0.0003).sum())}")
        pm.attrs["min_clearance_m"] = float(sdf_full(np.array(pm.V, F32)).min())
    return pm


# ==============================================================================================
# Cils et vibrisses (cartes alpha)
# ==============================================================================================
LASH_UV = {"lash": (0.0, 0.0, 0.75, 1.0), "whisker": (0.75, 0.0, 1.0, 1.0)}


def _card(pm, root, direction, side_vec, length, w0, w1, bend, zone, group, segs=3):
    """Carte en ruban : racine `root`, direction de pousse, axe de largeur `side_vec`, courbure `bend` (vecteur)."""
    u0, v0, u1, v1 = LASH_UV[zone]
    rows = []
    d = unit(direction)
    sv = unit(side_vec - np.dot(side_vec, d) * d)
    pts = []
    for k in range(segs + 1):
        t = k / segs
        p = root + d * length * t + bend * (t * t)
        pts.append(p)
    for k, p in enumerate(pts):
        t = k / segs
        w = w0 + (w1 - w0) * t
        rows.append(pm.add_verts([p - 0.5 * w * sv, p + 0.5 * w * sv], group))
    for k in range(segs):
        ta, tb = k / segs, (k + 1) / segs
        pm.add_face((rows[k][0], rows[k][1], rows[k + 1][1], rows[k + 1][0]),
                    [(u0, v0 + (v1 - v0) * ta), (u1, v0 + (v1 - v0) * ta), (u1, v0 + (v1 - v0) * tb),
                     (u0, v0 + (v1 - v0) * tb)])


def build_lashes(features, sdf_full, rig, scale=1.0):
    """Cils (paupière supérieure, quelques-uns à l'inférieure) + vibrisses (lèvres, menton, au-dessus de l'œil)."""
    pm = PartMesh("Lashes")
    for side in "lr":
        ef = features[f"eye_{side}"]
        c = 0.5 * (ef.a_med + ef.a_lat)
        hw = 0.5 * (ef.a_med - ef.a_lat)
        # paupière supérieure : 9 cartes, plus longues côté latéral
        for i, t in enumerate(np.linspace(-0.88, 0.62, 9)):
            a0, a1 = c + (t - 0.08) * hw, c + (t + 0.08) * hw
            pa = ef.C + (ef.R_out + 0.0006) * ef.direction(a0, ef.beta_up(t - 0.08))
            pb = ef.C + (ef.R_out + 0.0006) * ef.direction(a1, ef.beta_up(t + 0.08))
            root = 0.5 * (pa + pb)
            w_out = unit(root - ef.C)
            L = (0.0105 + 0.0065 * (1 - (t + 0.88) / 1.5)) * scale
            dirn = unit(0.75 * w_out + 0.55 * ef.g - 0.30 * ef.v)
            _card(pm, root, dirn, pb - pa, L, np.linalg.norm(pb - pa) * 1.15, np.linalg.norm(pb - pa) * 1.5,
                  -0.25 * L * ef.v, "lash", f"lash_upper_{side}")
        # paupière inférieure : 4 petites cartes
        for t in np.linspace(-0.7, 0.3, 4):
            a0, a1 = c + (t - 0.09) * hw, c + (t + 0.09) * hw
            pa = ef.C + (ef.R_out + 0.0006) * ef.direction(a0, -ef.beta_lo(t - 0.09))
            pb = ef.C + (ef.R_out + 0.0006) * ef.direction(a1, -ef.beta_lo(t + 0.09))
            root = 0.5 * (pa + pb)
            w_out = unit(root - ef.C)
            L = 0.0055 * scale
            _card(pm, root, unit(0.7 * w_out + 0.4 * ef.g + 0.2 * ef.v), pb - pa, L, np.linalg.norm(pb - pa),
                  np.linalg.norm(pb - pa) * 1.2, 0.2 * L * ef.v, "lash", f"lash_lower_{side}", segs=2)
    # vibrisses : racines sur la peau (projection sur le SDF), poussée selon la normale inclinée
    H = rig.jh("head")
    ax = unit(rig.jt("head") - H)
    dn = unit(np.array([0.0, -ax[2], ax[1]]))
    from .body_sdf import face_s, FACE_K  # noqa: F401  (même repère que le SDF)

    def head_pt(s, d, x):
        H0 = rig.rh("head")
        a0 = unit(rig.rt("head") - H0)
        d0 = unit(np.array([0.0, -a0[2], a0[1]]))
        return rig.p("head", H0 + float(face_s(s)) * a0 + d * d0 + np.array([x, 0.0, 0.0]))

    rng = np.random.default_rng(7)
    spots = []
    for sx in (-1.0, 1.0):
        # lèvre supérieure (latéral / avant)
        for k in range(9):
            s = 0.425 + 0.06 * rng.random()
            d = -0.035 + 0.03 * rng.random()
            spots.append((head_pt(s, d, sx * (0.030 + 0.012 * rng.random())), 0.026 + 0.012 * rng.random(), "muzzle"))
        # lèvre inférieure / menton
        for k in range(4):
            s = 0.43 + 0.04 * rng.random()
            spots.append((head_pt(s, -0.085 + 0.01 * rng.random(), sx * (0.010 + 0.016 * rng.random())),
                          0.020 + 0.01 * rng.random(), "chin"))
        # au-dessus et au-dessous de l'œil
        ef = features["eye_l" if sx < 0 else "eye_r"]
        for k in range(3):
            spots.append((ef.C + 0.034 * ef.v + (0.010 * (k - 1)) * ef.h + 0.012 * ef.g, 0.030, "brow"))
        for k in range(2):
            spots.append((ef.C - 0.032 * ef.v + (0.012 * (k - 0.5)) * ef.h + 0.012 * ef.g, 0.022, "cheek"))
    P = np.array([s[0] for s in spots])
    Pp = sdf_full.project(P.astype(F32), iters=6)
    N = sdf_full.normal(Pp)
    for (p0, L, kind), p, n in zip(spots, Pp, N):
        n = unit(n)
        if kind in ("muzzle", "chin"):
            dirn = unit(n + 0.35 * ax - 0.25 * dn)
        else:
            dirn = unit(n + 0.3 * ax)
        sv = np.cross(dirn, n)
        if np.linalg.norm(sv) < 1e-6:
            sv = np.cross(dirn, [0, 0, 1.0])
        L = L * scale
        _card(pm, p - 0.0008 * n, dirn, sv, L, 0.0016, 0.0008, -0.18 * L * np.array([0, 0, 1.0]), "whisker",
              "whiskers", segs=3)
    return pm


def lashes_texture(size=256):
    """RGBA uint8 : zone « cils » (u 0–0.75) et zone « vibrisse » (u 0.75–1). v = 0 racine → 1 pointe."""
    rng = np.random.default_rng(11)
    img = np.zeros((size, size, 4), np.float32)
    wl = int(size * 0.75)
    yy = (np.arange(size)[:, None] + 0.5) / size          # 0 en haut de l'image
    t = 1.0 - yy                                           # v (racine en bas de l'image : v = 0)
    xx = np.arange(wl)[None, :] + 0.5
    a = np.zeros((size, wl), np.float32)
    for k in range(34):
        x0 = rng.uniform(4, wl - 4)
        curl = rng.uniform(-12, 12)
        ln = rng.uniform(0.65, 1.0)
        xc = x0 + curl * t ** 2
        wid = 1.6 * (1 - 0.7 * np.clip(t / ln, 0, 1))
        m = np.exp(-((xx - xc) / wid) ** 2) * (t < ln)
        a = np.maximum(a, m)
    img[:, :wl, 3] = np.clip(a * 1.2, 0, 1)
    img[:, :wl, :3] = 0.06
    xw = np.arange(size - wl)[None, :] + 0.5
    cw = (size - wl) / 2
    wid = 3.0 * (1 - 0.85 * t)
    aw = np.exp(-((xw - cw) / wid) ** 2) * (t < 0.98)
    img[:, wl:, 3] = np.clip(aw * 1.3, 0, 1)
    img[:, wl:, :3] = 0.10 + 0.45 * t[..., None] ** 2      # vibrisse : base foncée, pointe plus claire
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def mouth_texture(size=256):
    """RGBA uint8 : gencive (rose foncé), dents (ivoire), langue (rose) — sRGB [A]."""
    rng = np.random.default_rng(5)
    img = np.zeros((size, size, 4), np.float32)
    h = size // 2
    n = rng.normal(0, 1, (size, size)).astype(np.float32)
    from scipy.ndimage import gaussian_filter

    n = gaussian_filter(n, 2.0)
    n /= max(1e-6, n.std())
    gum = np.array([0.55, 0.30, 0.32])
    tooth = np.array([0.86, 0.82, 0.70])
    tongue = np.array([0.62, 0.36, 0.38])
    img[:h, :h, :3] = gum * (1 + 0.05 * n[:h, :h, None])
    img[:h, h:, :3] = tooth * (1 + 0.03 * n[:h, h:, None])
    img[h:, :, :3] = tongue * (1 + 0.06 * n[h:, :, None])
    img[..., 3] = 1.0
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
