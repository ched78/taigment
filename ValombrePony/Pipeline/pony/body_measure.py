"""Mesures morphométriques du corps du poney, calculées sur le SDF (sections planes + contours).

Définitions (Docs/research/anatomy.md §3.1) : hauteur au garrot = point le plus haut du garrot ;
tour de poitrine = périmètre de la section verticale juste derrière le coude ; longueur du corps =
pointe de l'épaule → pointe de la fesse (horizontale) ; tour de canon = périmètre de la section horizontale
à mi-canon antérieur ; longueur de tête = nuque (sommet entre les oreilles) → bout de la lèvre supérieure.
"""
from __future__ import annotations

import numpy as np

from .body_sdf_lib import F32


def _section(sdf, plane, center, u_range, v_range, res=0.002):
    """Contours (liste de (n,2) en coordonnées u,v) de la section du SDF dans un plan axial.
    plane : 'x', 'y' ou 'z' (axe normal), center : valeur sur cet axe."""
    from skimage import measure

    us = np.arange(u_range[0], u_range[1], res)
    vs = np.arange(v_range[0], v_range[1], res)
    U, V = np.meshgrid(us, vs, indexing="ij")
    P = np.zeros((U.size, 3), F32)
    ax = "xyz".index(plane)
    others = [i for i in range(3) if i != ax]
    P[:, ax] = center
    P[:, others[0]] = U.ravel()
    P[:, others[1]] = V.ravel()
    d = sdf(P).reshape(U.shape)
    cs = measure.find_contours(d, 0.0)
    out = []
    for c in cs:
        uv = np.stack([u_range[0] + c[:, 0] * res, v_range[0] + c[:, 1] * res], 1)
        out.append(uv)
    return out, d


def _width(sdf, plane, center, u_range, v_range, res=0.002):
    _, d = _section(sdf, plane, center, u_range, v_range, res)
    inside = np.argwhere(d < 0)
    if len(inside) == 0:
        return float("nan")
    return float((inside[:, 0].max() - inside[:, 0].min()) * res)


def _perimeter(c):
    closed = np.vstack([c, c[:1]])
    return float(np.linalg.norm(np.diff(closed, axis=0), axis=1).sum())


def measure_body(sdf, wh_ref=1.30):
    m = {}
    # hauteur au garrot : max z dans la zone du garrot (y 0.15..0.45, x 0)
    zs = np.linspace(1.1, 1.45, 351)
    def top_at(y, x=0.0):
        P = np.stack([np.full_like(zs, x), np.full_like(zs, y), zs], 1).astype(F32)
        d = sdf(P)
        inside = np.flatnonzero(d < 0)
        return float(zs[inside.max()]) if len(inside) else float("nan")
    ys = np.linspace(0.10, 0.36, 27)
    tops = [top_at(y) for y in ys]
    i = int(np.nanargmax(tops))
    m["withers_height"] = tops[i]
    m["withers_y"] = float(ys[i])
    yb = np.linspace(-0.62, -0.35, 28)
    m["croup_height"] = float(np.nanmax([top_at(y) for y in yb]))
    yback = np.linspace(-0.15, 0.15, 16)
    m["back_lowest"] = float(np.nanmin([top_at(y) for y in yback]))
    # profondeur de poitrine : garrot -> dessous du sternum (y du garrot, x 0)
    zz = np.linspace(0.5, 1.0, 501)
    P = np.stack([np.zeros_like(zz), np.full_like(zz, 0.30), zz], 1).astype(F32)
    d = sdf(P)
    inside = np.flatnonzero(d < 0)
    m["sternum_z"] = float(zz[inside.min()])
    m["chest_depth"] = m["withers_height"] - m["sternum_z"]
    # tour de poitrine : section y = 0.27 (derrière le coude), contour du tronc seul (exclut les membres)
    cs, _ = _section(sdf, "y", 0.27, (-0.35, 0.35), (0.62, 1.40), 0.002)
    best = max(cs, key=lambda c: (c[:, 1].max() - c[:, 1].min()))
    # le contour du tronc peut inclure les coudes : on prend l'enveloppe à z > 0.66
    m["heart_girth"] = _perimeter(best)
    m["barrel_width"] = _width(sdf, "y", -0.08, (-0.40, 0.40), (0.60, 1.30))
    # longueur du corps : y max à la pointe de l'épaule (z 0.85..0.95, x 0.10..0.20) ; y min pointe de fesse
    def extreme_y(zr, xr, sign):
        best_v = -np.inf
        for z in np.linspace(*zr, 6):
            for x in np.linspace(*xr, 6):
                yy = np.linspace(-1.0, 1.0, 1001) * sign
                P = np.stack([np.full_like(yy, x), yy, np.full_like(yy, z)], 1).astype(F32)
                dd = sdf(P)
                ins = np.flatnonzero(dd < 0)
                if len(ins):
                    best_v = max(best_v, float((yy[ins] * sign).max()))
        return best_v * sign
    m["point_of_shoulder_y"] = extreme_y((0.86, 0.94), (-0.20, -0.15), 1.0)
    m["point_of_buttock_y"] = extreme_y((0.95, 1.05), (-0.14, -0.06), -1.0)
    m["body_length"] = m["point_of_shoulder_y"] - m["point_of_buttock_y"]
    # largeur de poitrine : |x| max autour de la pointe de l'épaule
    m["chest_width"] = _width(sdf, "z", 0.90, (-0.40, 0.40), (0.60, 0.75))
    m["hip_width"] = _width(sdf, "z", 1.15, (-0.40, 0.40), (-0.50, -0.25))
    # tour de canon antérieur (z = 0.25, membre gauche)
    cs, _ = _section(sdf, "z", 0.25, (-0.20, -0.04), (0.33, 0.52), 0.0007)
    m["cannon_circ_fore"] = _perimeter(max(cs, key=len))
    cs, _ = _section(sdf, "z", 0.27, (-0.20, -0.04), (-0.72, -0.52), 0.0007)
    m["cannon_circ_hind"] = _perimeter(max(cs, key=len))
    # sabot antérieur : largeur et longueur au sol (z = 0.004)
    cs, _ = _section(sdf, "z", 0.004, (-0.22, 0.0), (0.38, 0.62), 0.0007)
    c = max(cs, key=len)
    m["front_hoof_width"] = float(c[:, 0].max() - c[:, 0].min())
    m["front_hoof_length"] = float(c[:, 1].max() - c[:, 1].min())
    cs, _ = _section(sdf, "z", 0.004, (-0.22, 0.0), (-0.65, -0.40), 0.0007)
    c = max(cs, key=len)
    m["hind_hoof_width"] = float(c[:, 0].max() - c[:, 0].min())
    # tête : nuque (z max entre les oreilles, x=0, y 0.80..0.98) -> bout de la lèvre sup. (y max x 0)
    yy = np.linspace(0.78, 1.0, 45)
    tz = [top_at(y) if True else 0 for y in yy]
    zs2 = np.linspace(1.3, 1.6, 301)
    best = None
    for y in yy:
        P = np.stack([np.zeros_like(zs2), np.full_like(zs2, y), zs2], 1).astype(F32)
        dd = sdf(P)
        ins = np.flatnonzero(dd < 0)
        if len(ins):
            z = zs2[ins.max()]
            if best is None or z > best[1]:
                best = (y, z)
    poll = np.array([0.0, best[0], best[1]])
    ymx = np.linspace(1.0, 1.4, 801)
    tip = None
    for z in np.linspace(1.0, 1.2, 41):
        P = np.stack([np.zeros_like(ymx), ymx, np.full_like(ymx, z)], 1).astype(F32)
        dd = sdf(P)
        ins = np.flatnonzero(dd < 0)
        if len(ins) and (tip is None or ymx[ins.max()] > tip[1]):
            tip = (0.0, float(ymx[ins.max()]), float(z))
    m["poll"] = poll.tolist()
    m["muzzle_tip"] = list(tip)
    m["head_length"] = float(np.linalg.norm(np.array(tip) - poll))
    # rapports à WH
    wh = m["withers_height"]
    m["ratios"] = {k: round(m[k] / wh, 3) for k in ("body_length", "chest_depth", "heart_girth", "cannon_circ_fore",
                                                    "head_length", "chest_width", "croup_height", "hip_width")}
    return m


TARGETS = {  # anatomy.md §3.3 (WH 1.30) — [I]/[A]
    "withers_height": (1.28, 1.32), "body_length": (1.37, 1.43), "chest_depth": (0.60, 0.62),
    "heart_girth": (1.57, 1.66), "cannon_circ_fore": (0.17, 0.18), "head_length": (0.49, 0.54),
    "chest_width": (0.34, 0.36), "croup_height": (1.28, 1.32), "front_hoof_width": (0.10, 0.12),
}
