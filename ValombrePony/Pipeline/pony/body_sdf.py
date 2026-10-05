"""Champ de distance signée (SDF) anatomique du poney — paramétrique, positionné depuis le gabarit.

API principale
--------------
    from pony import body_sdf, template
    sdf = body_sdf.build_sdf(joints=template.joint_table(), params=body_sdf.BodyParams())
    d = sdf(P)                 # P (N,3) float -> distances (N,), négatif = intérieur (mètres)
    g = sdf.gradient(P)        # gradient (N,3) (différences finies, tétraèdre)
    Q = sdf.project(P)         # projection de points sur l'iso-surface 0 (Newton borné)
    sdf.region_distances(P)    # distances par groupe anatomique (étiquetage des régions)
    sdf.features               # descripteurs géométriques (yeux, bouche, naseaux, oreilles, sabots…)

Toutes les primitives sont positionnées à partir des joints passés en argument (`joints`, format de
`template.joint_table()`) : chaque point de contrôle est défini dans le gabarit de référence (WH 1,30 m)
puis transporté par l'application affine de l'os auquel il est attaché (rotation + étirement le long
de l'os + échelle globale ; cf. `RigMap`). Un gabarit aux membres / encolure / corps allongés donne donc
un corps cohérent (formes de proportion `prop_*`).

Paramètres morphologiques (`BodyParams`, valeurs par défaut = poney de base Welsh B / Connemara)
-------------------------------------------------------------------------------------------------
| nom            | unité / plage sûre | effet |
|----------------|--------------------|-------|
| trunk_width    | facteur, 0.85–1.20 | largeur du tronc (côtes, poitrail, croupe) ; >1 « stocky », <1 « refined » |
| trunk_depth    | facteur, 0.90–1.12 | profondeur du tronc (ligne du dessous abaissée/remontée sous la ligne du dessus) |
| fat            | −1 … +1            | état corporel : + crête, couverture des côtes, coussinets de base de queue, épaules, ventre ; − côtes, pointes des hanches, épine dorsale et garrot saillants, flanc creux |
| muscle         | 0 … 1              | relief musculaire (masses plus volumineuses, sillons inter-musculaires plus marqués) |
| belly          | 0 … 1              | gros ventre (abaissement + élargissement de la ligne du dessous) |
| crest          | 0 … 1              | encolure rouée / crête épaisse |
| bone           | 0 … 1              | canons, genoux, jarrets, boulets plus épais |
| head_profile   | −1 … +1            | −1 chanfrein concave (« dished »), +1 busqué (« roman ») |
| head_short     | 0 … 1              | face raccourcie (≈ −12 % au-delà des yeux), museau affiné |
| muzzle_width   | 0 … 1              | museau élargi, naseaux plus ouverts |
| hoof_size      | facteur, 0.85–1.25 | dimensions des sabots |
| nostril_flare  | 0 … 1              | dilatation des naseaux (expression) |
| flehmen        | 0 … 1              | retroussement de la lèvre supérieure (expression ; approximation, cf. rapport) |
| brow_worry     | 0 … 1              | ride d'inquiétude au-dessus de l'œil (expression) |
| mouth_soft     | 0 … 1              | bouche détendue : lèvre inférieure pendante (expression) |
| breathe        | 0 … 1              | expansion respiratoire du thorax et du flanc |
| micro_detail   | 0 … 1              | veines, plis et rides fines (réservé à la haute définition cuite ; 0 pour la basse déf.) |
| features       | bool               | True = fentes/cavités ouvertes (bouche, yeux, naseaux, conque des oreilles) ; False = variante « fermée » pour la retopologie |

Toutes les valeurs anatomiques sont des approximations artistiques [A] calées sur les cibles chiffrées
de Docs/research/anatomy.md (§1.3, §1.4, §3.3) ; les positions viennent du gabarit (template.py).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from . import template
from .body_sdf_lib import (BIG, F32, BlobBump, Bump, PolyBump, Ellipsoid, Func, Group, Hoof, Loft, RoundBox, RoundCone,
                           Segment, Sphere, VLoft, evaluate, frame_from_axis, gradient, project, ray_surface, smax,
                           smin, smoothstep, unit)


# ==============================================================================================
# Paramètres
# ==============================================================================================
@dataclass
class BodyParams:
    trunk_width: float = 1.0
    trunk_depth: float = 1.0
    fat: float = 0.0
    muscle: float = 0.0
    belly: float = 0.0
    crest: float = 0.0
    bone: float = 0.0
    head_profile: float = 0.0
    head_short: float = 0.0
    muzzle_width: float = 0.0
    hoof_size: float = 1.0
    nostril_flare: float = 0.0
    flehmen: float = 0.0
    brow_worry: float = 0.0
    mouth_soft: float = 0.0
    breathe: float = 0.0
    micro_detail: float = 0.0
    features: bool = True

    def to_dict(self):
        return asdict(self)


PARAM_DOC = {
    "trunk_width": ("facteur", (0.85, 1.20)), "trunk_depth": ("facteur", (0.90, 1.12)),
    "fat": ("-1..1", (-1.0, 1.0)), "muscle": ("0..1", (0.0, 1.0)), "belly": ("0..1", (0.0, 1.0)),
    "crest": ("0..1", (0.0, 1.0)), "bone": ("0..1", (0.0, 1.0)), "head_profile": ("-1..1", (-1.0, 1.0)),
    "head_short": ("0..1", (0.0, 1.0)), "muzzle_width": ("0..1", (0.0, 1.0)),
    "hoof_size": ("facteur", (0.85, 1.25)), "nostril_flare": ("0..1", (0.0, 1.0)),
    "flehmen": ("0..1", (0.0, 1.0)), "brow_worry": ("0..1", (0.0, 1.0)), "mouth_soft": ("0..1", (0.0, 1.0)),
    "breathe": ("0..1", (0.0, 1.0)), "micro_detail": ("0..1", (0.0, 1.0)), "features": ("bool", (0, 1)),
}


# ==============================================================================================
# Transport des points de contrôle par les os
# ==============================================================================================
def _rot_between(u0, u1):
    u0, u1 = unit(u0), unit(u1)
    v = np.cross(u0, u1)
    c = float(np.dot(u0, u1))
    s = np.linalg.norm(v)
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        a = unit(np.cross(u0, [1.0, 0.0, 0.0] if abs(u0[0]) < 0.9 else [0.0, 1.0, 0.0]))
        return 2.0 * np.outer(a, a) - np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / (s * s))


class RigMap:
    """Application affine par os : p_new = h1 + R·S·(p_ref − h0).

    R tourne la direction de l'os de référence vers la nouvelle ; S étire le long de l'os
    (rapport des longueurs) et met à l'échelle globale k perpendiculairement. k = médiane des
    rapports de longueur des os (= 1 pour le gabarit de référence, = wh/1.30 pour un gabarit mis à
    l'échelle, ≈ 1 pour une forme de proportion qui n'allonge que quelques os) [I].
    """

    def __init__(self, joints, ref=None):
        ref = ref or template.joint_table(template.REFERENCE_WH)
        self.ref = {e["name"]: e for e in ref}
        self.new = {e["name"]: e for e in joints}
        ratios = []
        for n, e in self.ref.items():
            L0 = np.linalg.norm(np.subtract(e["tail"], e["head"]))
            L1 = np.linalg.norm(np.subtract(self.new[n]["tail"], self.new[n]["head"]))
            ratios.append(L1 / L0)
        self.k = float(np.median(ratios))
        self.maps = {}
        for n, e in self.ref.items():
            h0, t0 = np.array(e["head"], float), np.array(e["tail"], float)
            h1, t1 = np.array(self.new[n]["head"], float), np.array(self.new[n]["tail"], float)
            u0, u1 = unit(t0 - h0), unit(t1 - h1)
            L0, L1 = np.linalg.norm(t0 - h0), np.linalg.norm(t1 - h1)
            R = _rot_between(u0, u1)
            S = self.k * np.eye(3) + (L1 / L0 - self.k) * np.outer(u0, u0)
            self.maps[n] = (h0, h1, R @ S, R)

    def p(self, bone, x):
        h0, h1, A, _ = self.maps[bone]
        return h1 + A @ (np.asarray(x, float) - h0)

    def pw(self, weights, x):
        out = np.zeros(3)
        tot = 0.0
        for b, w in weights:
            out += w * self.p(b, x)
            tot += w
        return out / tot

    def v(self, bone, vec):
        return self.maps[bone][3] @ np.asarray(vec, float)

    def r(self, x):
        return x * self.k

    def jh(self, n):
        return np.array(self.new[n]["head"], float)

    def jt(self, n):
        return np.array(self.new[n]["tail"], float)

    def rh(self, n):
        return np.array(self.ref[n]["head"], float)

    def rt(self, n):
        return np.array(self.ref[n]["tail"], float)


def _spine_weights(y):
    """Poids d'attache d'un point du tronc (y de référence) aux os du rachis (fonctions chapeau)."""
    anchors = [("hips", -0.60), ("spine_01", -0.28), ("spine_02", 0.0), ("spine_03", 0.28), ("neck_01", 0.62)]
    ys = np.array([a[1] for a in anchors])
    if y <= ys[0]:
        return [(anchors[0][0], 1.0)]
    if y >= ys[-1]:
        return [(anchors[-1][0], 1.0)]
    i = int(np.searchsorted(ys, y)) - 1
    t = (y - ys[i]) / (ys[i + 1] - ys[i])
    return [(anchors[i][0], 1.0 - t), (anchors[i + 1][0], t)]


# ==============================================================================================
# Descripteurs de caractéristiques (partagés avec body.py / head_parts.py)
# ==============================================================================================
@dataclass
class EyeFeature:
    side: str
    C: np.ndarray       # centre du globe (= joint eye_*)
    g: np.ndarray       # axe optique (vers l'extérieur)
    h: np.ndarray       # tangente horizontale vers le canthus médial (rostral) = axe de fermeture des paupières
    v: np.ndarray       # tangente « haut » de la fente
    R_globe: float      # rayon du globe (visible) ~ 19,5 mm
    R_in: float         # rayon intérieur de la coque palpébrale (cavité)
    R_out: float        # rayon extérieur de la coque palpébrale
    a_lat: float        # azimut du canthus latéral (rad, <0)
    a_med: float        # azimut du canthus médial (rad, >0)
    b_up: float         # élévation max de la paupière supérieure (rad)
    b_lo: float         # élévation max (en valeur absolue) de la paupière inférieure (rad)
    p_up: float = 0.62
    p_lo: float = 0.72
    peak_up: float = -0.12
    peak_lo: float = 0.15

    def _t(self, alpha):
        c = 0.5 * (self.a_med + self.a_lat)
        hw = 0.5 * (self.a_med - self.a_lat)
        return (alpha - c) / hw

    def beta_up(self, t):
        u = np.clip(np.abs(t - self.peak_up * (1 - t * t)), 0, 1)
        return self.b_up * np.power(np.clip(1 - u * u, 0, 1), self.p_up)

    def beta_lo(self, t):
        u = np.clip(np.abs(t - self.peak_lo * (1 - t * t)), 0, 1)
        return self.b_lo * np.power(np.clip(1 - u * u, 0, 1), self.p_lo)

    def angles(self, P):
        D = np.asarray(P, np.float64) - self.C
        r = np.linalg.norm(D, axis=-1)
        w = D / np.maximum(r[..., None], 1e-9)
        alpha = np.arctan2(w @ self.h, w @ self.g)
        beta = np.arcsin(np.clip(w @ self.v, -1, 1))
        return alpha, beta, r

    def direction(self, alpha, beta):
        alpha = np.asarray(alpha, float)[..., None]
        beta = np.asarray(beta, float)[..., None]
        return np.cos(beta) * (np.cos(alpha) * self.g + np.sin(alpha) * self.h) + np.sin(beta) * self.v

    def margin_curve(self, n=48, radius=None, which="both"):
        """Points de la bordure de la fente (coque extérieure par défaut), boucle fermée :
        canthus latéral → paupière supérieure → canthus médial → paupière inférieure."""
        radius = self.R_out if radius is None else radius
        c = 0.5 * (self.a_med + self.a_lat)
        hw = 0.5 * (self.a_med - self.a_lat)
        m = n // 2
        t_up = np.linspace(-1, 1, m + 1)
        t_lo = np.linspace(1, -1, n - m + 1)[1:-1]
        pts = []
        for t in t_up:
            pts.append(self.direction(c + t * hw, self.beta_up(t)))
        for t in t_lo:
            pts.append(self.direction(c + t * hw, -self.beta_lo(t)))
        pts = np.array(pts)
        return self.C + radius * pts

    def fissure_sdf(self, P):
        """Distance (≈ m) au cône de la fente palpébrale (négatif à l'intérieur du cône)."""
        alpha, beta, r = self.angles(P)
        c = 0.5 * (self.a_med + self.a_lat)
        hw = 0.5 * (self.a_med - self.a_lat)
        t = (alpha - c) / hw
        tc = np.clip(t, -1, 1)
        da = (np.abs(t) - 1.0) * hw
        db = np.maximum(beta - self.beta_up(tc), -self.beta_lo(tc) - beta)
        d = np.maximum(da, db)
        D = np.asarray(P, np.float64) - self.C
        front = (D @ self.g) / np.maximum(r, 1e-9)
        d = np.maximum(d, 0.15 - front)
        return d * np.maximum(r, 0.01)


@dataclass
class MouthFeature:
    O: np.ndarray        # centre de l'ellipse de la fente (plan buccal)
    am: np.ndarray       # axe rostral dans le plan buccal
    xh: np.ndarray       # latéral
    nm: np.ndarray       # normale du plan buccal (vers le haut / chanfrein)
    A_s: float           # demi-axe de la fente le long de am
    A_x: float           # demi-axe latéral de la fente
    tau: float           # demi-épaisseur de la fente aux lèvres
    cav_c: np.ndarray    # centre de la cavité buccale (lentille)
    cav_r: np.ndarray    # demi-axes (am, x, nm) de la cavité
    commissure_l: np.ndarray = None
    commissure_r: np.ndarray = None

    def local(self, P):
        D = np.asarray(P, np.float64) - self.O
        return D @ self.am, D @ self.xh, D @ self.nm


@dataclass
class NostrilFeature:
    side: str
    Nc: np.ndarray        # centre de l'ouverture (sur la surface)
    n_out: np.ndarray     # normale sortante
    e1: np.ndarray        # grand axe de l'ouverture
    e2: np.ndarray
    a1: float
    a2: float
    ring_c: list          # centres des anneaux du conduit (de l'ouverture vers le fond)
    ring_s: list          # facteurs d'échelle des anneaux


@dataclass
class EarFeature:
    side: str
    B: np.ndarray
    e: np.ndarray        # axe de l'oreille (base → pointe)
    f: np.ndarray        # direction d'ouverture du pavillon
    g: np.ndarray        # latéral du pavillon
    length: float


@dataclass
class HoofFeature:
    leg: str             # fl, fr, hl, hr
    O: np.ndarray        # centre de l'appui au sol
    fwd: np.ndarray
    coronet_toe: float   # hauteur de la couronne à la pince
    coronet_heel: float
    Lf: float
    Lb: float
    W0: float


# ==============================================================================================
# Construction
# ==============================================================================================
class BodySDF:
    def __init__(self, root: Group, features: dict, params: BodyParams, rig: RigMap, region_groups: dict):
        self.root = root
        self.features = features
        self.params = params
        self.rig = rig
        self.region_groups = region_groups
        self.lo = root.lo
        self.hi = root.hi

    def __call__(self, P, margin=0.05, cell=0.08):
        return evaluate(self.root, P, margin=margin, cell=cell)

    def gradient(self, P, eps=4e-4):
        return gradient(lambda Q: self(Q), P, eps)

    def normal(self, P, eps=4e-4):
        g = self.gradient(P, eps)
        return g / np.maximum(np.linalg.norm(g, axis=1, keepdims=True), 1e-9)

    def project(self, P, iters=4, max_step=0.02):
        return project(lambda Q: self(Q), P, iters=iters, max_step=max_step)

    def region_distances(self, P, names=None):
        names = names or list(self.region_groups)
        return {n: evaluate(self.region_groups[n], P, margin=0.08) for n in names}


def build_sdf(joints=None, params: BodyParams | None = None) -> BodySDF:
    joints = joints or template.joint_table()
    prm = params or BodyParams()
    M = RigMap(joints)
    B = _Builder(M, prm)
    return B.build()


class _Builder:
    def __init__(self, M: RigMap, prm: BodyParams):
        self.M = M
        self.p = prm
        self.k = M.k
        self.features = {}
        self.regions = {}
        self.details = []
        self.openings = []
        self.shoulders = []

    # ------------------------------------------------------------------ utilitaires
    def r(self, x):
        return np.asarray(x, float) * self.k if isinstance(x, (list, tuple, np.ndarray)) else x * self.k

    def tp(self, y, z, lat=0.0, sx=1.0):
        """Point du tronc (référence) transporté par le rachis."""
        return self.M.pw(_spine_weights(y), (sx * lat, y, z))

    def head_frame(self):
        M = self.M
        H0 = M.rh("head")
        a0 = unit(M.rt("head") - H0)
        d0 = unit(np.array([0.0, -a0[2], a0[1]]))
        return H0, a0, d0

    def hp(self, s, d, x=0.0):
        """Point du repère tête (s le long de l'axe nuque→nez, d vers le chanfrein, x latéral)."""
        H0, a0, d0 = self.head_frame()
        hs = self.p.head_short
        if hs > 0 and s > 0.12:
            s = 0.12 + (s - 0.12) * (1.0 - 0.12 * hs)
        return self.M.p("head", H0 + s * a0 + d * d0 + np.array([x, 0.0, 0.0]))

    def hv(self, s, d, x=0.0):
        H0, a0, d0 = self.head_frame()
        return self.M.v("head", s * a0 + d * d0 + np.array([x, 0.0, 0.0]))

    # ------------------------------------------------------------------ assemblage
    def build(self):
        p = self.p
        root = Group("body")
        trunk = self.trunk()
        neck = self.neck()
        head = self.head()
        tail = self.tail()
        root.add("U", trunk, 0.0)
        root.add("U", neck, 0.06)
        root.add("U", head, 0.045)
        root.add("U", tail, 0.035)
        self.regions.update(trunk=trunk, neck=neck, head=head, tail=tail)
        for side, sx in (("l", -1.0), ("r", 1.0)):
            fl = self.foreleg(side, sx)
            hl = self.hindleg(side, sx)
            root.add("U", fl["leg"], 0.045)
            root.add("U", hl["leg"], 0.05)
            for leg, parts in (("f", fl), ("h", hl)):
                root.add("U", parts["hoof"], 0.004)
                root.add("U", parts["chestnut"], 0.003)
                root.add("U", parts["ergot"], 0.003)
            ear = self.ear(side, sx)
            root.add("U", ear, 0.012)
        for sg in self.shoulders:
            root.add("U", sg, 0.06)
        # reliefs, sillons, creux (après les unions)
        for op, prim, k in self.details:
            root.add(op, prim, k)
        # caractéristiques ouvertes (en dernier : rien ne doit les reboucher)
        for op, prim, k in self.openings:
            root.add(op, prim, k)
        return BodySDF(root, self.features, p, self.M, self.regions)

    # ------------------------------------------------------------------ tronc
    def trunk(self):
        p = self.p
        g = Group("trunk")
        tw, td = p.trunk_width, p.trunk_depth
        fat, mus = p.fat, p.muscle
        # Stations : y, dessus, dessous, demi-largeur, fraction de la largeur max, exposants haut / bas [A]
        S = np.array([
            # y      top    bot     w      wf    nt   nb
            [0.66, 1.030, 0.875, 0.050, 0.50, 2.0, 2.0],
            [0.62, 1.120, 0.815, 0.120, 0.46, 1.8, 2.0],
            [0.54, 1.195, 0.745, 0.160, 0.44, 1.7, 1.9],
            [0.42, 1.235, 0.705, 0.178, 0.42, 1.7, 1.9],
            [0.30, 1.248, 0.690, 0.192, 0.40, 1.8, 1.9],
            [0.15, 1.245, 0.678, 0.214, 0.40, 2.0, 2.0],
            [0.00, 1.236, 0.668, 0.232, 0.40, 2.2, 2.1],
            [-0.10, 1.236, 0.662, 0.238, 0.41, 2.3, 2.1],
            [-0.20, 1.240, 0.670, 0.234, 0.43, 2.4, 2.1],
            [-0.30, 1.254, 0.705, 0.222, 0.46, 2.5, 2.1],
            [-0.40, 1.272, 0.772, 0.206, 0.50, 2.4, 2.0],
            [-0.50, 1.284, 0.850, 0.196, 0.52, 2.2, 2.0],
            [-0.60, 1.276, 0.910, 0.180, 0.52, 2.1, 2.0],
            [-0.70, 1.238, 0.960, 0.145, 0.52, 2.0, 2.0],
            [-0.78, 1.175, 1.000, 0.080, 0.50, 2.0, 2.0],
            [-0.83, 1.125, 1.040, 0.030, 0.50, 2.0, 2.0],
        ], float)
        ys, top, bot, w = S[:, 0].copy(), S[:, 1].copy(), S[:, 2].copy(), S[:, 3].copy()
        # paramètres morphologiques
        barrel = np.exp(-((ys + 0.05) / 0.32) ** 2)
        belly_zone = np.exp(-((ys + 0.10) / 0.22) ** 2)
        w = w * tw * (1.0 + 0.045 * fat * barrel) * (1.0 + 0.03 * p.belly * belly_zone)
        w = w * (1.0 + 0.022 * p.breathe * np.exp(-((ys - 0.05) / 0.28) ** 2))
        bot = top - (top - bot) * td
        bot = bot - (0.05 * p.belly + 0.012 * max(fat, 0.0)) * belly_zone - 0.006 * p.breathe * belly_zone
        tops, bots = [], []
        for y, t, b in zip(ys, top, bot):
            tops.append(self.tp(y, t))
            bots.append(self.tp(y, b))
        tops, bots = np.array(tops), np.array(bots)
        s_new = 0.5 * (tops[:, 1] + bots[:, 1])
        loft = Loft((0, 0, 0), (0, 1, 0), (0, 0, 1), s_new, tops[:, 2], bots[:, 2], self.r(w), S[:, 4], S[:, 5],
                    S[:, 6])
        g.add("U", loft)
        self.trunk_loft = loft
        # garrot : crête des processus épineux
        wr = 1.0 + 0.25 * max(-fat, 0.0)
        g.add("U", Ellipsoid(self.tp(0.275, 1.222), self.r(np.array([0.040, 0.175, 0.080]) * [1.0, 1.0, wr])), 0.05)
        # muscles longs du dos (deux bandes)
        for sx in (-1.0, 1.0):
            a = self.tp(0.22, 1.172, 0.058 * tw, sx)
            b = self.tp(-0.40, 1.196, 0.060 * tw, sx)
            rr = self.r(0.058 * (1 + 0.08 * mus))
            g.add("U", Segment(a, b, (rr * 1.05, rr * 1.05), (rr, rr)), 0.05)
        # sacrum / sommet de croupe
        g.add("U", Ellipsoid(self.tp(-0.50, 1.250), self.r([0.055 * tw, 0.20, 0.058])), 0.05)
        # poitrail : masse centrale + pectoraux descendants (V)
        g.add("U", Ellipsoid(self.tp(0.575, 0.865), self.r([0.095 * tw, 0.065, 0.110])), 0.05)
        for sx, side in ((-1.0, "l"), (1.0, "r")):
            a = self.M.pw([("spine_03", 0.5), (f"forearm_{side}", 0.5)], (sx * 0.058 * tw, 0.630, 0.905))
            b = self.M.p(f"forearm_{side}", (sx * 0.102, 0.495, 0.690))
            rr = 1.0 + 0.08 * mus
            g.add("U", Segment(a, b, (self.r(0.050 * rr), self.r(0.040 * rr)), (self.r(0.046 * rr), self.r(0.040))),
                  0.04)
            # pectoral ascendant (sous le thorax, entre les membres)
            g.add("U", Ellipsoid(self.tp(0.38, 0.715, 0.075, sx), self.r([0.055, 0.12, 0.035])), 0.05)
        # creux du flanc (fosse paralombaire) et sillon de la sangle
        for sx in (-1.0, 1.0):
            depth = 0.85 + 0.6 * max(-fat, 0.0) - 0.5 * max(fat, 0.0)
            c = self.tp(-0.285, 1.080, 0.235 * tw + 0.012, sx)
            self.details.append(("S", Ellipsoid(c, self.r(np.array([0.030, 0.085, 0.075]) * depth)), 0.04))
            # sillon de la sangle juste derrière le coude
            a = self.tp(0.30, 0.86, 0.19 * tw + 0.006, sx)
            b = self.tp(0.33, 0.70, 0.15 * tw + 0.004, sx)
            self.details.append(("D", Bump(a, b, self.r(0.030), -self.r(0.0025), taper=0.35), 0.0))
            # côtes (visibles si maigre ; très légères sinon)
            amp = 0.0003 + 0.0045 * max(-fat, 0.0)
            for i in range(9):
                y0 = 0.18 - i * 0.052
                a = self.tp(y0 + 0.015, 1.13, 0.215 * tw, sx)
                b = self.tp(y0 + 0.075, 0.80, 0.215 * tw, sx)
                self.details.append(("D", Bump(a, b, self.r(0.011), self.r(amp), taper=0.35), 0.0))
            # oblique externe de l'abdomen : léger pli bas du flanc
            a = self.tp(-0.32, 0.90, 0.215 * tw, sx)
            b = self.tp(0.05, 0.74, 0.225 * tw, sx)
            self.details.append(("D", Bump(a, b, self.r(0.018), -self.r(0.0015 + 0.002 * mus)), 0.0))
        # ligne du dos (épine dorsale) si maigre
        if fat < 0:
            self.details.append(("D", Bump(self.tp(0.10, 1.25), self.tp(-0.45, 1.265), self.r(0.012),
                                           self.r(0.006 * -fat)), 0.0))
        return g

    # ------------------------------------------------------------------ encolure
    def neck(self):
        p = self.p
        M = self.M
        g = Group("neck")
        O_ref = M.rh("neck_01")
        O = M.jh("neck_01")
        ax = unit(M.jh("head") - O)
        nm = unit(np.array([0.0, -ax[2], ax[1]]))
        # ligne de crête et ligne du dessous (référence, y-z), attachées aux os de l'encolure [A]
        crest_ref = [(0.20, 1.282), (0.30, 1.296), (0.38, 1.280), (0.46, 1.296), (0.55, 1.340), (0.64, 1.392),
                     (0.72, 1.436), (0.79, 1.468), (0.85, 1.488), (0.90, 1.494), (0.95, 1.480)]
        under_ref = [(0.615, 0.840), (0.638, 0.910), (0.668, 0.985), (0.705, 1.060), (0.742, 1.130), (0.773, 1.200),
                     (0.795, 1.255), (0.812, 1.296), (0.830, 1.338), (0.848, 1.375), (0.868, 1.440)]

        def attach(yz):
            y, z = yz
            pt = np.array([0.0, y, z])
            # os le plus proche (par la tête du joint)
            best = min(["spine_03", "neck_01", "neck_02", "neck_03", "neck_04", "neck_05", "neck_06", "head"],
                       key=lambda n: np.linalg.norm(M.rh(n) - pt))
            return M.p(best, pt)

        crest = np.array([attach(c) for c in crest_ref])
        under = np.array([attach(c) for c in under_ref])

        def cut(poly, s):
            # intersection de la droite O + s·ax + t·nm avec une polyligne (plan sagittal)
            c = O + s * ax
            best = None
            for i in range(len(poly) - 1):
                a, b = poly[i], poly[i + 1]
                # résoudre c + t nm = a + u (b - a)
                A = np.array([[nm[1], -(b - a)[1]], [nm[2], -(b - a)[2]]])
                rhs = np.array([(a - c)[1], (a - c)[2]])
                try:
                    t, u = np.linalg.solve(A, rhs)
                except np.linalg.LinAlgError:
                    continue
                if -1e-6 <= u <= 1 + 1e-6:
                    best = t
                    break
            return best

        L = np.linalg.norm(M.jh("head") - O)
        L0 = np.linalg.norm(M.rh("head") - O_ref)
        s_ref = np.array([0.06, 0.12, 0.18, 0.24, 0.30, 0.36, 0.42, 0.48, 0.53, 0.57, 0.62])
        # demi-largeurs [A] (base fondue dans les épaules → nuque)
        w_ref = np.array([0.150, 0.140, 0.128, 0.116, 0.105, 0.096, 0.089, 0.082, 0.077, 0.072, 0.060])
        wf = np.array([0.42, 0.42, 0.42, 0.42, 0.42, 0.43, 0.45, 0.48, 0.52, 0.55, 0.55])
        nt = np.array([2.10, 2.05, 1.95, 1.85, 1.78, 1.75, 1.75, 1.80, 1.90, 2.0, 2.0])
        nb = np.array([1.90, 1.90, 1.95, 2.00, 2.00, 2.05, 2.10, 2.10, 2.10, 2.1, 2.1])
        ss, tops, bots, keep = [], [], [], []
        for i0, s0 in enumerate(s_ref):
            s = s0 * L / L0
            t = cut(crest, s)
            b = cut(under, s)
            if t is None or b is None:
                continue
            keep.append(i0)
            ss.append(s)
            # crête : épaisseur variable (graisse / crête)
            bell = math.exp(-((s0 - 0.36) / 0.16) ** 2)
            t += self.r(0.035 * p.crest * bell + 0.012 * p.fat * bell)
            tops.append(t)
            bots.append(b)
        kp = np.array(keep)
        w = self.r(w_ref[kp] * (1.0 + 0.06 * p.fat + 0.03 * p.muscle) * (1 + 0.15 * p.crest * np.exp(
            -((s_ref[kp] - 0.36) / 0.2) ** 2) * 0.3))
        loft = Loft(O, ax, nm, ss, tops, bots, w, wf[kp], nt[kp], nb[kp])
        g.add("U", loft)
        self.neck_loft = loft
        self.neck_frame = (O, ax, nm)
        fn = lambda P: loft.eval(np.asarray(P, F32))
        # Sillon jugulaire, brachio-céphalique, splénius : placés sur la surface par lancer de rayons
        for sx in (-1.0, 1.0):
            pts_j, pts_b, pts_s = [], [], []
            for s0, fj, fb in ((0.12, 0.30, 0.52), (0.24, 0.27, 0.50), (0.36, 0.25, 0.48), (0.48, 0.24, 0.47),
                               (0.58, 0.26, 0.50)):
                s = s0 * L / L0
                t = cut(crest, s)
                b = cut(under, s)
                if t is None or b is None:
                    continue
                for f, store in ((fj, pts_j), (fb, pts_b), (0.80, pts_s)):
                    c = O + s * ax + (b + f * (t - b)) * nm
                    hit = ray_surface(fn, c, (sx, 0.0, 0.0), t_max=0.3)
                    if hit is not None:
                        store.append(hit)
            if len(pts_j) >= 3:
                self.details.append(("D", PolyBump(np.array(pts_j), self.r(0.017),
                                                   -self.r(0.0032 + 0.002 * p.muscle), taper=0.2), 0.0))
            if len(pts_b) >= 3:
                self.details.append(("D", PolyBump(np.array(pts_b), self.r(0.026),
                                                   self.r(0.0018 + 0.003 * p.muscle), taper=0.25), 0.0))
            if len(pts_s) >= 3:
                pts_s = np.array(pts_s)
                self.details.append(("D", Bump(pts_s[1], pts_s[3], self.r(0.045),
                                               self.r(0.002 + 0.003 * p.muscle)), 0.0))
        return g

    # ------------------------------------------------------------------ tête
    def head(self):
        p = self.p
        M = self.M
        g = Group("head")
        H = M.jh("head")
        H0, a0, d0 = self.head_frame()
        ax = self.hv(1.0, 0.0)
        ax = unit(ax)
        dn = unit(self.hv(0.0, 1.0))
        # Profil (s, dessus, dessous, demi-largeur, wf, nt, nb) dans le repère tête [A]
        T = np.array([
            [-0.140, -0.075, -0.115, 0.040, 0.50, 2.0, 2.0],
            [-0.085, 0.004, -0.078, 0.062, 0.55, 2.0, 2.0],
            [-0.045, 0.046, -0.072, 0.071, 0.58, 2.2, 2.0],
            [0.000, 0.073, -0.082, 0.078, 0.60, 2.4, 2.1],
            [0.035, 0.080, -0.105, 0.083, 0.62, 2.5, 2.2],
            [0.065, 0.085, -0.136, 0.088, 0.63, 2.5, 2.3],
            [0.100, 0.088, -0.146, 0.091, 0.64, 2.6, 2.3],
            [0.150, 0.090, -0.142, 0.093, 0.64, 2.6, 2.3],
            [0.200, 0.088, -0.134, 0.088, 0.62, 2.6, 2.3],
            [0.250, 0.082, -0.123, 0.077, 0.60, 2.6, 2.3],
            [0.300, 0.074, -0.110, 0.070, 0.55, 2.4, 2.2],
            [0.350, 0.065, -0.100, 0.062, 0.52, 2.4, 2.2],
            [0.400, 0.056, -0.095, 0.057, 0.50, 2.3, 2.2],
            [0.440, 0.051, -0.095, 0.056, 0.48, 2.2, 2.2],
            [0.470, 0.042, -0.090, 0.055, 0.46, 2.2, 2.2],
            [0.492, 0.022, -0.072, 0.046, 0.45, 2.0, 2.0],
            [0.500, 0.004, -0.050, 0.028, 0.50, 2.0, 2.0],
        ], float)
        s, top, bot, w = T[:, 0].copy(), T[:, 1].copy(), T[:, 2].copy(), T[:, 3].copy()
        # profil de chanfrein : concave (dished) / busqué (roman)
        prof = p.head_profile
        if prof != 0:
            if prof > 0:
                top += 0.011 * prof * np.exp(-((s - 0.33) / 0.08) ** 2)
            else:
                top += 0.010 * prof * np.exp(-((s - 0.255) / 0.05) ** 2)
        mz = np.clip((s - 0.36) / 0.06, 0, 1)
        w = w * (1.0 + 0.12 * p.muzzle_width * mz) * (1.0 - 0.08 * p.head_short * mz)
        hs = p.head_short
        if hs > 0:
            s = np.where(s > 0.12, 0.12 + (s - 0.12) * (1 - 0.12 * hs), s)
        loft = Loft(H, ax, dn, self.r(s), self.r(top), self.r(bot), self.r(w), T[:, 4], T[:, 5], T[:, 6])
        g.add("U", loft)
        hp = self.hp
        X = np.array([1.0, 0.0, 0.0])
        Rh = np.stack([ax, dn, X], 1)  # colonnes : axe, dorsal, latéral
        mus = p.muscle
        for sx in (-1.0, 1.0):
            # ganaches (masséters) : larges et plates
            Rm = np.stack([unit(self.hv(1.0, 0.35)), unit(self.hv(-0.35, 1.0)), X], 1)
            g.add("U", Ellipsoid(hp(0.100, -0.085, sx * 0.064), self.r([0.076 * (1 + 0.04 * mus), 0.076, 0.027]), Rm),
                  0.03)
            # angle de la mandibule (contour arrondi de la ganache)
            g.add("U", Ellipsoid(hp(0.072, -0.118, sx * 0.058), self.r([0.048, 0.044, 0.022]), Rm), 0.025)
            # bord ventral de la mandibule (rami)
            a = hp(0.07, -0.140, sx * 0.050)
            b = hp(0.36, -0.092, sx * 0.034)
            g.add("U", Segment(a, b, (self.r(0.016), self.r(0.012)), (self.r(0.012), self.r(0.010)), lat=X), 0.02)
            # arcade sourcilière (processus supra-orbitaire)
            a = hp(0.120, 0.062, sx * 0.060)
            b = hp(0.200, 0.050, sx * 0.076)
            g.add("U", Segment(a, b, (self.r(0.012), self.r(0.009)), (self.r(0.011), self.r(0.008)), lat=dn), 0.022)
            # arcade zygomatique derrière l'œil (bord orbitaire caudal) -> rejoint la crête faciale
            a = hp(0.125, 0.030, sx * 0.080)
            b = hp(0.185, -0.012, sx * 0.090)
            g.add("U", Segment(a, b, (self.r(0.011), self.r(0.010)), (self.r(0.010), self.r(0.010)), lat=X), 0.016)
            # crête faciale (zygomatique)
            self.details.append(("D", Bump(hp(0.175, -0.024, sx * 0.090), hp(0.275, -0.040, sx * 0.074),
                                           self.r(0.009), self.r(0.0028 + 0.002 * mus), taper=0.35), 0.0))
            # salière (fosse supra-orbitaire)
            self.details.append(("D", BlobBump(hp(0.100, 0.052, sx * 0.080), self.r(np.array([0.026, 0.014, 0.010])),
                                               -self.r(0.0045 + 0.004 * max(-p.fat, 0)), Rh), 0.0))
            # sillon entre masséter et joue (bord rostral du masséter)
            self.details.append(("D", Bump(hp(0.170, -0.040, sx * 0.086), hp(0.200, -0.125, sx * 0.072),
                                           self.r(0.008), -self.r(0.0025), taper=0.3), 0.0))
        # auge (espace intermandibulaire)
        self.details.append(("S", Segment(hp(0.080, -0.172), hp(0.330, -0.118),
                                          (self.r(0.030), self.r(0.017)), (self.r(0.020), self.r(0.016)), lat=X),
                             0.02))
        # lèvres et menton
        self.mouth_parts(g)
        # nuque / toupet : légère crête nucale
        g.add("U", Ellipsoid(hp(-0.025, 0.040), self.r([0.032, 0.026, 0.055]), Rh), 0.035)
        # yeux, naseaux (et ouvertures)
        for side, sx in (("l", -1.0), ("r", 1.0)):
            self.eye(g, side, sx)
        self.nostrils(g, loft)
        self.regions["head_core"] = g
        return g

    def mouth_parts(self, g):
        p = self.p
        hp = self.hp
        X = np.array([1.0, 0.0, 0.0])
        ax = unit(self.hv(1.0, 0.0))
        dn = unit(self.hv(0.0, 1.0))
        Rh = np.stack([ax, dn, X], 1)
        fl = p.flehmen
        # lèvre supérieure (mobile, épaisse) — flehmen : rotation vers le haut autour d'un axe latéral
        c_up = hp(0.468, -0.018)
        if fl > 0:
            piv = hp(0.420, 0.030)
            ang = math.radians(38.0 * fl)
            Rx = _axis_rot(X, ang)
            c_up = piv + Rx @ (c_up - piv)
            Rh_up = Rx @ Rh
        else:
            Rh_up = Rh
        g.add("U", Ellipsoid(c_up, self.r([0.034, 0.030, 0.048]), Rh_up), 0.022)
        # lèvre inférieure + menton (attachés à la mâchoire)
        ms = p.mouth_soft
        c_lo = hp(0.462 + 0.004 * ms, -0.062 - 0.008 * ms)
        g.add("U", Ellipsoid(c_lo, self.r([0.030, 0.022 + 0.003 * ms, 0.038]), Rh), 0.018)
        g.add("U", Ellipsoid(hp(0.423, -0.083 - 0.003 * ms), self.r([0.040, 0.021, 0.031]), Rh), 0.02)
        # sillon du menton
        self.details.append(("D", Bump(hp(0.445, -0.090, -0.03), hp(0.445, -0.090, 0.03), self.r(0.006),
                                       -self.r(0.002)), 0.0))
        # --- fente buccale ---
        s_c, d_c, s_f, d_f = 0.36, -0.047, 0.50, -0.039
        slope = (d_f - d_c) / (s_f - s_c)
        am = unit(ax + slope * dn)
        nm = unit(dn - slope * ax)
        O = hp(0.430, d_c + slope * (0.430 - s_c))
        A_s, A_x = self.r(0.088), self.r(0.064)
        tau = self.r(0.0021 + 0.0025 * ms)
        cav_c = hp(0.405, d_c + slope * (0.405 - s_c) - 0.002)
        cav_r = np.array([self.r(0.062), self.r(0.036), self.r(0.0225)])
        mf = MouthFeature(O=O, am=am, xh=X, nm=nm, A_s=A_s, A_x=A_x, tau=tau, cav_c=cav_c, cav_r=cav_r)
        self.features["mouth"] = mf
        Rmo = np.stack([am, X, nm], 1)
        if p.features:
            def slit(P, mf=mf):
                D = np.asarray(P, np.float64) - mf.O
                u, x, v = D @ mf.am, D @ mf.xh, D @ mf.nm
                rho = np.sqrt((u / mf.A_s) ** 2 + (x / mf.A_x) ** 2)
                d_plane = (rho - 1.0) * min(mf.A_s, mf.A_x)
                return np.maximum(d_plane, np.abs(v) - mf.tau)

            ext = np.array([A_s + 0.01, A_s + 0.01, A_s + 0.01])
            self.openings.append(("S", Func(slit, O - ext, O + ext), 0.0012))
            self.openings.append(("S", Ellipsoid(cav_c, cav_r, Rmo), 0.004))
        else:
            # variante fermée : léger sillon le long de la commissure des lèvres
            pass

    def eye(self, g, side, sx):
        p = self.p
        M = self.M
        C = M.jh(f"eye_{side}")
        ax = unit(self.hv(1.0, 0.0))
        dn = unit(self.hv(0.0, 1.0))
        # axe optique = direction de l'os de la paupière supérieure (gabarit) ; h = axe de la fente (vers
        # le canthus médial) = X local de l'os (règle de roulis) au signe près ; v = « haut » de la fente.
        gdir = unit(M.jt(f"eyelid_upper_{side}") - C)
        Xw = np.array([1.0, 0.0, 0.0])
        h = unit(Xw - np.dot(Xw, gdir) * gdir)
        if np.dot(h, ax) < 0:
            h = -h
        v = unit(np.cross(h, gdir))
        if np.dot(v, dn) < 0:
            v = -v
        # globe : sclère R 19 mm + cornée bombée (apex 20,4 mm) ; coque palpébrale R_in 20,8 / R_out 25 mm
        Rg, Ri, Ro = self.r(0.0190), self.r(0.0208), self.r(0.0250)
        ef = EyeFeature(side=side, C=C, g=gdir, h=h, v=v, R_globe=Rg, R_in=Ri, R_out=Ro,
                        a_lat=-0.95, a_med=1.00, b_up=0.58, b_lo=0.40)
        self.features[f"eye_{side}"] = ef
        # coque palpébrale (sphère) fondue dans la tête
        g.add("U", Sphere(C, Ro), 0.011)
        # pli de la paupière supérieure + ride d'inquiétude
        cmid = 0.5 * (ef.a_med + ef.a_lat)
        chw = 0.5 * (ef.a_med - ef.a_lat)
        ts = np.linspace(-0.8, 0.8, 9)
        crease = [C + (Ro + 0.0004) * ef.direction(cmid + t * chw * 1.02, ef.beta_up(t) + 0.24) for t in ts]
        for i in range(len(crease) - 1):
            self.details.append(("D", Bump(crease[i], crease[i + 1], self.r(0.0024), -self.r(0.0012), taper=0.01),
                                 0.0))
        if p.brow_worry > 0:
            a = C + 0.032 * ef.v + 0.012 * ef.h + 0.012 * ef.g
            b = C + 0.024 * ef.v - 0.006 * ef.h + 0.02 * ef.g
            self.details.append(("D", Bump(a, b, self.r(0.004), self.r(0.004 * p.brow_worry), taper=0.3), 0.0))
            a2 = C + 0.040 * ef.v + 0.018 * ef.h + 0.004 * ef.g
            self.details.append(("D", Bump(a2, a, self.r(0.0025), -self.r(0.0025 * p.brow_worry), taper=0.3), 0.0))
        if p.features:
            ext = np.array([Ro + 0.012] * 3)
            cav = Group(f"eye_cavity_{side}")
            cav.add("U", Sphere(C, Ri))

            def cone(P, ef=ef):
                d = ef.fissure_sdf(P)
                r = np.linalg.norm(np.asarray(P, np.float64) - ef.C, axis=-1)
                return np.maximum(d, np.maximum(ef.R_in - 0.003 - r, r - (ef.R_out + 0.009)))

            cav.add("U", Func(cone, C - ext, C + ext), 0.0)
            self.openings.append(("S", cav, 0.0015))

    def nostrils(self, g, loft):
        p = self.p
        hp = self.hp
        ax = unit(self.hv(1.0, 0.0))
        dn = unit(self.hv(0.0, 1.0))
        fl = p.nostril_flare
        mw = p.muzzle_width
        fn = lambda P: loft.eval(np.asarray(P, F32))
        for side, sx in (("l", -1.0), ("r", 1.0)):
            lat = np.array([sx, 0.0, 0.0])
            o = hp(0.448, 0.004, 0.0)
            dirn = unit(0.78 * lat + 0.55 * ax + 0.10 * dn)
            Nc = ray_surface(fn, o, dirn, t_max=0.12)
            if Nc is None:
                Nc = o + 0.05 * dirn
            n_out = unit(np.asarray(_num_grad(fn, Nc), float))
            e1 = unit(0.92 * dn - 0.30 * ax + 0.22 * lat)
            e1 = unit(e1 - np.dot(e1, n_out) * n_out)
            e2 = unit(np.cross(n_out, e1))
            if np.dot(e2, ax) < 0:
                e2 = -e2
            a1 = self.r(0.0215 * (1 + 0.20 * fl + 0.08 * mw))
            a2 = self.r(0.0085 * (1 + 0.80 * fl + 0.25 * mw))
            # renflement du naseau (cartilage alaire + diverticule) autour de l'ouverture
            Rn = np.stack([e1, e2, n_out], 1)
            g.add("U", Ellipsoid(Nc - 0.006 * n_out + 0.004 * e2, self.r(np.array([0.030, 0.020, 0.012]) *
                                                                         (1 + 0.12 * fl)), Rn), 0.014)
            # aile (bord médial-rostral de l'ouverture, en « C »)
            g.add("U", Ellipsoid(Nc + 0.6 * a2 * e2 + 0.002 * n_out - 0.004 * e1,
                                 self.r(np.array([0.016, 0.0055, 0.006]) * (1 + 0.1 * fl)), Rn), 0.005)
            # conduit : anneaux de l'ouverture vers le fond (vers la nuque et la ligne médiane)
            inward = unit(-n_out * 0.75 - ax * 0.55 - 0.15 * lat)
            ring_c = [Nc + 0.012 * n_out, Nc - 0.006 * n_out, Nc + 0.022 * inward, Nc + 0.040 * inward,
                      Nc + 0.055 * inward - 0.006 * dn]
            ring_s = [1.08, 1.0, 0.82, 0.62, 0.38]
            nf = NostrilFeature(side=side, Nc=Nc, n_out=n_out, e1=e1, e2=e2, a1=a1, a2=a2, ring_c=ring_c,
                                ring_s=ring_s)
            self.features[f"nostril_{side}"] = nf
            if p.features:
                grp = Group(f"nostril_pocket_{side}")
                for i in range(len(ring_c) - 1):
                    s0, s1 = ring_s[i], ring_s[i + 1]
                    grp.add("U", Segment(ring_c[i], ring_c[i + 1], (a1 * s0, a1 * s1), (a2 * s0, a2 * s1),
                                         lat=e1), 0.004)
                self.openings.append(("S", grp, 0.003))
            else:
                self.details.append(("S", Segment(Nc + 0.010 * n_out, Nc - 0.002 * n_out, (a1 * 0.9, a1 * 0.9),
                                                  (a2 * 0.8, a2 * 0.8), lat=e1), 0.004))
            # fausse narine : léger creux au-dessus/latéral de l'ouverture
            self.details.append(("D", BlobBump(Nc + 0.014 * e1 + 0.004 * lat * 0, self.r(np.array([0.008, 0.008,
                                                                                                    0.008])),
                                               -self.r(0.0015)), 0.0))
            # rides du naseau (micro-détail)
            if p.micro_detail > 0:
                for i in range(3):
                    a = Nc + (0.012 + 0.006 * i) * e2 - 0.012 * e1 - 0.003 * n_out
                    b = Nc + (0.016 + 0.006 * i) * e2 + 0.012 * e1 - 0.003 * n_out
                    self.details.append(("D", Bump(a, b, self.r(0.0012), -self.r(0.0006 * p.micro_detail),
                                                   taper=0.3), 0.0))

    # ------------------------------------------------------------------ oreilles
    def ear(self, side, sx):
        p = self.p
        M = self.M
        g = Group(f"ear_{side}")
        B = M.jh(f"ear_{side}")
        T = M.jt(f"ear_tip_{side}")
        e = unit(T - B)
        Le = np.linalg.norm(T - B)
        lat = np.array([sx, 0.0, 0.0])
        f = unit(np.array([0.0, 1.0, 0.0]) * 0.86 + 0.50 * lat)
        f = unit(f - np.dot(f, e) * e)
        gl = unit(np.cross(e, f))
        self.features[f"ear_{side}"] = EarFeature(side=side, B=B, e=e, f=f, g=gl, length=Le)
        t = np.array([-0.06, 0.0, 0.12, 0.30, 0.50, 0.68, 0.82, 0.92, 1.0])
        w = np.array([0.016, 0.017, 0.022, 0.0285, 0.0290, 0.0250, 0.0180, 0.0105, 0.0030])
        top = np.array([0.010, 0.011, 0.014, 0.0170, 0.0160, 0.0130, 0.0090, 0.0050, 0.0015])
        bot = -np.array([0.016, 0.017, 0.019, 0.0210, 0.0200, 0.0165, 0.0120, 0.0070, 0.0020])
        k = Le / 0.133
        outer = Loft(B, e, f, t * Le, top * k, bot * k, w * k, np.full(9, 0.45), np.full(9, 2.0),
                     np.full(9, 2.1))
        g.add("U", outer)
        th = self.r(0.0047)
        if p.features:
            tc = np.array([0.10, 0.20, 0.35, 0.50, 0.68, 0.82, 0.90, 0.96])
            wc = np.interp(tc, t, w) * k - th
            botc = np.interp(tc, t, bot) * k + th
            topc = np.interp(tc, t, top) * k + 0.03
            wc = np.maximum(wc, 0.0008)
            cav = Loft(B, e, f, tc * Le, topc, botc, wc, np.full(8, 0.30), np.full(8, 2.0), np.full(8, 2.1))
            g.add("S", cav, 0.0018)
        else:
            tc = np.array([0.14, 0.24, 0.38, 0.52, 0.68, 0.80, 0.88])
            wc = np.interp(tc, t, w) * k - 0.012
            topc = np.interp(tc, t, top) * k + 0.02
            botc = np.interp(tc, t, top) * k - 0.010
            wc = np.maximum(wc, 0.002)
            cav = Loft(B, e, f, tc * Le, topc, botc, wc, np.full(7, 0.30), np.full(7, 2.0), np.full(7, 2.0))
            g.add("S", cav, 0.004)
        self.regions[f"ear_{side}"] = g
        return g

    # ------------------------------------------------------------------ membres antérieurs
    # Profils du membre antérieur gauche (référence) : z, avant (y), arrière (y), latéral |x|, médial |x|, exposant,
    # os d'attache. [A] calés sur les joints du gabarit et anatomy.md (§1.3, §3.3).
    FORE_PROFILE = [
        (0.960, 0.575, 0.345, 0.140, 0.100, 2.2, "upperarm"),
        (0.900, 0.590, 0.330, 0.172, 0.103, 2.2, "upperarm"),
        (0.860, 0.580, 0.330, 0.188, 0.100, 2.2, "upperarm"),
        (0.810, 0.555, 0.337, 0.193, 0.098, 2.2, "upperarm"),
        (0.760, 0.515, 0.343, 0.190, 0.095, 2.2, "forearm"),
        (0.710, 0.492, 0.356, 0.187, 0.093, 2.2, "forearm"),
        (0.640, 0.482, 0.368, 0.181, 0.093, 2.3, "forearm"),
        (0.560, 0.474, 0.377, 0.173, 0.093, 2.3, "forearm"),
        (0.480, 0.465, 0.385, 0.165, 0.092, 2.3, "forearm"),
        (0.420, 0.458, 0.390, 0.159, 0.093, 2.4, "forearm"),
        (0.380, 0.459, 0.388, 0.159, 0.092, 2.45, "front_cannon"),
        (0.350, 0.459, 0.383, 0.160, 0.091, 2.5, "front_cannon"),
        (0.315, 0.455, 0.388, 0.155, 0.096, 2.4, "front_cannon"),
        (0.280, 0.452, 0.391, 0.148, 0.101, 2.3, "front_cannon"),
        (0.220, 0.451, 0.390, 0.146, 0.102, 2.3, "front_cannon"),
        (0.175, 0.452, 0.386, 0.146, 0.100, 2.2, "front_cannon"),
        (0.140, 0.454, 0.375, 0.147, 0.084, 2.1, "front_pastern"),
        (0.115, 0.469, 0.392, 0.146, 0.085, 2.1, "front_pastern"),
        (0.090, 0.492, 0.426, 0.148, 0.083, 2.1, "front_pastern"),
        (0.065, 0.515, 0.441, 0.153, 0.077, 2.2, "front_pastern"),
        (0.048, 0.524, 0.446, 0.157, 0.073, 2.3, "front_hoof"),
    ]
    HIND_PROFILE = [
        (1.120, -0.460, -0.742, 0.130, 0.000, 2.0, "hips"),
        (1.060, -0.420, -0.750, 0.172, 0.000, 2.0, "hips"),
        (1.000, -0.400, -0.758, 0.192, 0.000, 2.0, "thigh"),
        (0.920, -0.376, -0.756, 0.204, 0.012, 2.1, "thigh"),
        (0.850, -0.361, -0.745, 0.206, 0.030, 2.2, "thigh"),
        (0.780, -0.356, -0.738, 0.199, 0.052, 2.2, "gaskin"),
        (0.720, -0.378, -0.712, 0.189, 0.068, 2.2, "gaskin"),
        (0.650, -0.425, -0.694, 0.177, 0.080, 2.2, "gaskin"),
        (0.580, -0.480, -0.692, 0.164, 0.084, 2.2, "gaskin"),
        (0.520, -0.525, -0.700, 0.158, 0.084, 2.3, "gaskin"),
        (0.470, -0.554, -0.712, 0.157, 0.083, 2.35, "hind_cannon"),
        (0.420, -0.578, -0.688, 0.158, 0.082, 2.4, "hind_cannon"),
        (0.380, -0.587, -0.672, 0.146, 0.094, 2.4, "hind_cannon"),
        (0.320, -0.589, -0.664, 0.142, 0.096, 2.3, "hind_cannon"),
        (0.250, -0.589, -0.656, 0.139, 0.095, 2.3, "hind_cannon"),
        (0.190, -0.587, -0.650, 0.138, 0.093, 2.2, "hind_cannon"),
        (0.150, -0.575, -0.660, 0.141, 0.080, 2.1, "hind_pastern"),
        (0.120, -0.553, -0.655, 0.139, 0.081, 2.1, "hind_pastern"),
        (0.095, -0.535, -0.618, 0.139, 0.081, 2.1, "hind_pastern"),
        (0.070, -0.518, -0.594, 0.145, 0.076, 2.2, "hind_pastern"),
        (0.050, -0.506, -0.588, 0.149, 0.071, 2.3, "hind_hoof"),
    ]

    def leg_loft(self, side, sx, table, scale_fn):
        """Construit un VLoft à partir d'un profil : chaque station est transportée par son os."""
        M = self.M
        rows = []
        for z, fy, by, lt, md, n, bone in table:
            b = f"{bone}_{side}" if bone not in ("hips",) else bone
            fr, bk, lt2, md2 = scale_fn(z, fy, by, lt, md)
            yc = 0.5 * (fr + bk)
            xc = 0.5 * (lt2 + md2)
            pc = M.p(b, (sx * xc, yc, z))
            pf = M.p(b, (sx * xc, fr, z))
            pb = M.p(b, (sx * xc, bk, z))
            pl = M.p(b, (sx * lt2, yc, z))
            pm = M.p(b, (sx * md2, yc, z))
            rows.append((pc[2], pc[0] * sx, pc[1], pf[1] - pc[1], pc[1] - pb[1], (pl[0] - pc[0]) * sx,
                         (pc[0] - pm[0]) * sx, n))
        R = np.array(rows)
        return VLoft(R[:, 0], sx * R[:, 1], R[:, 2], R[:, 3], R[:, 4], R[:, 5], R[:, 6], R[:, 7], sx=sx)

    def foreleg(self, side, sx):
        p = self.p
        M = self.M
        bn = lambda n: f"{n}_{side}"
        L = lambda lat, y, z: np.array([sx * lat, y, z])
        g = Group(f"fore_{side}")
        tw = p.trunk_width
        dl = (tw - 1.0) * 0.20
        mus, bone, fat = p.muscle, p.bone, p.fat
        rb = 1.0 + 0.15 * bone
        rm = 1.0 + 0.07 * mus
        P_ = lambda b, lat, y, z: M.p(bn(b), L(lat, y, z))

        def scale(z, fy, by, lt, md):
            yc, xc = 0.5 * (fy + by), 0.5 * (lt + md)
            f = rb if z < 0.42 else (rm if z > 0.45 else 1.0)
            sh = dl if z > 0.70 else 0.0
            return yc + (fy - yc) * f, yc + (by - yc) * f, xc + (lt - xc) * f + sh, xc + (md - xc) * f + sh * 0.5

        leg = self.leg_loft(side, sx, self.FORE_PROFILE, scale)
        g.add("U", leg)
        latv = np.array([sx, 0.0, 0.0])
        sg = Group(f"shoulder_{side}")
        self.shoulders.append(sg)
        # épaule : plaque (omoplate + supra/infra-épineux + deltoïde), en grande partie noyée dans le thorax
        S0 = P_("scapula", 0.070, 0.330, 1.200)
        Sh = P_("upperarm", 0.160, 0.580, 0.890)
        e = unit(Sh - S0)
        wv = unit(np.cross(e, latv))
        Rsc = np.stack([e, wv, unit(np.cross(e, wv))], 1)
        c = 0.46 * S0 + 0.54 * Sh + latv * (-0.013 + dl + 0.004 * max(fat, 0)) * self.k - wv * 0.012 * self.k
        sg.add("U", Ellipsoid(c, self.r(np.array([0.205, 0.112, 0.050]) * [1, 1, rm]), Rsc))
        # brachio-céphalique + base de l'encolure : comble la transition encolure → pointe de l'épaule
        a = P_("upperarm", 0.118 + dl, 0.598, 0.950)
        b2 = M.p("neck_02", L(0.062, 0.705, 1.160))
        e3 = unit(b2 - a)
        w3 = unit(np.cross(e3, latv))
        Rb = np.stack([e3, w3, unit(np.cross(e3, w3))], 1)
        sg.add("U", Ellipsoid(0.55 * a + 0.45 * b2, self.r(np.array([0.150, 0.070, 0.048]) * [1, 1, rm]), Rb), 0.05)
        # trapèze / rhomboïde : relie la crête de l'encolure au garrot et au cartilage de l'omoplate
        a = self.tp(0.250, 1.215, 0.050, sx)
        b2 = M.p("neck_02", L(0.058, 0.560, 1.250))
        sg.add("U", Segment(a, b2, (self.r(0.050), self.r(0.045)), (self.r(0.060), self.r(0.050))), 0.05)
        # pointe de l'épaule (tubercule majeur)
        sg.add("U", Ellipsoid(P_("upperarm", 0.140 + dl, 0.586, 0.895), self.r([0.030, 0.032, 0.042])), 0.04)
        # triceps (noyé, relief arrière du bras)
        a = P_("scapula", 0.118 + dl, 0.385, 1.020)
        b = P_("upperarm", 0.150 + dl, 0.372, 0.790)
        e2 = unit(b - a)
        w2 = unit(np.cross(e2, latv))
        Rt = np.stack([e2, w2, unit(np.cross(e2, w2))], 1)
        sg.add("U", Ellipsoid(0.5 * (a + b) + latv * 0.004 * self.k, self.r(np.array([0.150, 0.080, 0.048]) * [1, rm, rm]),
                              Rt), 0.05)
        # épine de l'omoplate (crête discrète) et sillon caudal du deltoïde
        amp = self.r(0.0020 + 0.0030 * mus - 0.0015 * max(fat, 0))
        self.details.append(("D", Bump(0.80 * S0 + 0.20 * Sh + latv * 0.055 * self.k,
                                       0.25 * S0 + 0.75 * Sh + latv * 0.062 * self.k - wv * 0.01 * self.k,
                                       self.r(0.012), amp, taper=0.3), 0.0))
        self.details.append(("D", Bump(P_("upperarm", 0.190 + dl, 0.540, 0.900), P_("upperarm", 0.192 + dl, 0.430, 0.790),
                                       self.r(0.010), -self.r(0.0018 + 0.002 * mus), taper=0.3), 0.0))
        # olécrane (pointe du coude)
        g.add("U", Ellipsoid(P_("forearm", 0.142, 0.358, 0.752), self.r([0.024, 0.024, 0.030])), 0.03)
        # avant-bras : extenseur radial du carpe (devant), fléchisseurs (derrière) — reliefs discrets
        self.details.append(("D", BlobBump(P_("forearm", 0.150, 0.470, 0.610), self.r(np.array([0.030, 0.020, 0.075])),
                                           self.r(0.0035 * rm)), 0.0))
        self.details.append(("D", Bump(P_("forearm", 0.188, 0.420, 0.660), P_("forearm", 0.162, 0.420, 0.450),
                                       self.r(0.007), -self.r(0.0018 + 0.002 * mus)), 0.0))
        # genou : os accessoire du carpe (arrière-latéral), face antérieure plate
        g.add("U", Ellipsoid(P_("front_cannon", 0.129, 0.386, 0.372), self.r(np.array([0.011, 0.012, 0.018]) * rb)), 0.016)
        # sillon entre os du canon et tendons (ligament suspenseur)
        for sgn in (-1.0, 1.0):
            off = 0.0235 if sgn > 0 else -0.0225
            self.details.append(("D", Bump(P_("front_cannon", 0.123 + off, 0.410, 0.305),
                                           P_("front_cannon", 0.116 + off, 0.410, 0.175),
                                           self.r(0.0045), -self.r(0.0016), taper=0.2), 0.0))
        # talons (glômes)
        for dz in (-1.0, 1.0):
            g.add("U", Ellipsoid(P_("front_hoof", 0.115 + dz * 0.020, 0.462, 0.036), self.r([0.018, 0.018, 0.019])),
                  0.014)
        hoof, hf = self.hoof(side, sx, front=True)
        g.add("U", Ellipsoid(hf["corona_c"], hf["corona_r"], hf["corona_R"]), 0.008)
        if p.micro_detail > 0:
            md = p.micro_detail
            self.details.append(("D", Bump(P_("forearm", 0.094, 0.440, 0.640), P_("forearm", 0.093, 0.438, 0.420),
                                           self.r(0.0035), self.r(0.0012 * md), taper=0.2), 0.0))
            self.details.append(("D", Bump(P_("front_cannon", 0.098, 0.430, 0.300), P_("front_cannon", 0.093, 0.432, 0.170),
                                           self.r(0.0028), self.r(0.0008 * md), taper=0.2), 0.0))
        chestnut = Group(f"chestnut_f{side}")
        Rc = np.stack([latv, np.array([0, 1.0, 0]), np.array([0, 0, 1.0])], 1)
        chestnut.add("U", Ellipsoid(P_("forearm", 0.0935, 0.420, 0.455), self.r([0.0060, 0.0120, 0.020]), Rc))
        ergot = Group(f"ergot_f{side}")
        ergot.add("U", Ellipsoid(P_("front_pastern", 0.115, 0.3825, 0.110), self.r([0.0095, 0.0062, 0.0085])))
        self.regions[f"fore_{side}"] = g
        self.regions[f"hoof_f{side}"] = hoof
        self.regions[f"chestnut_f{side}"] = chestnut
        self.regions[f"ergot_f{side}"] = ergot
        return dict(leg=g, hoof=hoof, chestnut=chestnut, ergot=ergot)

    def hoof(self, side, sx, front=True):
        p = self.p
        M = self.M
        hsz = p.hoof_size
        if front:
            bone = f"front_hoof_{side}"
            toe_ref = np.array([sx * 0.115, 0.565, 0.0])
            Lf, Lb, W0, Ht, Hh, at, ah, flare, ex, tn = 0.060, 0.055, 0.0545, 0.066, 0.036, 52.0, 63.0, 0.24, 2.25, 0.04
        else:
            bone = f"hind_hoof_{side}"
            toe_ref = np.array([sx * 0.110, -0.467, 0.0])
            Lf, Lb, W0, Ht, Hh, at, ah, flare, ex, tn = 0.058, 0.054, 0.0500, 0.068, 0.038, 55.0, 64.0, 0.20, 2.1, 0.14
        Lf, Lb, W0, Ht, Hh = (v * hsz * self.k for v in (Lf, Lb, W0, Ht, Hh))
        toe = M.p(bone, toe_ref)
        fwd = unit(M.v(bone, (0.0, 1.0, 0.0)) * np.array([1, 1, 0]))
        O = toe - fwd * Lf
        O[2] = 0.0 if abs(toe[2]) < 1e-6 else toe[2]
        g = Group(f"hoof_{'f' if front else 'h'}{side}")
        hp_ = Hoof(O, fwd, Lf, Lb, W0, Ht, Hh, math.radians(at), math.radians(ah), flare, ex=ex, toe_narrow=tn)
        g.add("U", hp_)
        # encoche des talons (entre les glômes, au-dessus de la fourchette)
        up = np.array([0, 0, 1.0])
        g.add("S", Ellipsoid(O - fwd * (Lb * 0.98) + up * 0.012 * self.k, self.r([0.013, 0.016, 0.022]) * hsz), 0.004)
        # couronne : ellipsoïde aplati suivant le plan de la couronne
        front_top = O + fwd * (Lf - Ht / math.tan(math.radians(at))) + up * Ht
        back_top = O - fwd * (Lb - Hh / math.tan(math.radians(ah))) + up * Hh
        cc = 0.5 * (front_top + back_top)
        ev = unit(front_top - back_top)
        lat = unit(np.cross(fwd, up))
        nrm = unit(np.cross(lat, ev))
        clen = 0.5 * np.linalg.norm(front_top - back_top)
        wtop = W0 - flare * 0.5 * (Ht + Hh)
        Rc = np.stack([ev, lat, nrm], 1)
        hf = dict(corona_c=cc + nrm * 0.003 * self.k, corona_r=np.array([clen + 0.0025, wtop + 0.002, 0.0065 * self.k]),
                  corona_R=Rc)
        self.features[f"hoof_{'f' if front else 'h'}{side}"] = HoofFeature(
            leg=("f" if front else "h") + side, O=O, fwd=fwd, coronet_toe=Ht, coronet_heel=Hh, Lf=Lf, Lb=Lb, W0=W0)
        return g, hf

    # ------------------------------------------------------------------ membres postérieurs
    def hindleg(self, side, sx):
        p = self.p
        M = self.M
        bn = lambda n: f"{n}_{side}"
        L = lambda lat, y, z: np.array([sx * lat, y, z])
        P_ = lambda b, lat, y, z: M.p(bn(b), L(lat, y, z))
        g = Group(f"hind_{side}")
        tw = p.trunk_width
        dl = (tw - 1.0) * 0.20
        mus, bone, fat = p.muscle, p.bone, p.fat
        rb = 1.0 + 0.15 * bone
        rm = 1.0 + 0.06 * mus
        latv = np.array([sx, 0.0, 0.0])

        def scale(z, fy, by, lt, md):
            yc, xc = 0.5 * (fy + by), 0.5 * (lt + md)
            f = rb if z < 0.45 else rm * (1.0 + 0.03 * fat if z > 0.7 else 1.0)
            sh = dl if z > 0.75 else 0.0
            return yc + (fy - yc) * f, yc + (by - yc) * f, xc + (lt - xc) * f + sh, xc + (md - xc) * f

        g.add("U", self.leg_loft(side, sx, self.HIND_PROFILE, scale))
        # fessiers (croupe ronde), noyés
        cg = Group(f"croup_{side}")
        self.shoulders.append(cg)
        cg.add("U", Ellipsoid(M.p("hips", L(0.088 + dl * 0.5, -0.500, 1.175)),
                              self.r(np.array([0.110 * tw, 0.245, 0.112]) * [rm, 1, rm * (1 + 0.04 * fat)])))
        # pointe de la hanche (tuber coxae)
        ph = 1.0 + 0.30 * max(-fat, 0.0)
        g.add("U", Ellipsoid(M.p("hips", L(0.188 + dl, -0.355, 1.150)), self.r(np.array([0.034, 0.042, 0.032]) * ph)),
              0.045 - 0.02 * max(-fat, 0))
        # tenseur du fascia lata (de la pointe de la hanche vers le grasset), noyé
        a = M.p("hips", L(0.178 + dl, -0.365, 1.110))
        b = P_("thigh", 0.168 + dl, -0.380, 0.880)
        g.add("U", Segment(a, b, (self.r(0.026), self.r(0.024)), (self.r(0.038 * rm), self.r(0.036 * rm)), lat=latv),
              0.06)
        # grasset (rotule) : relief discret
        self.details.append(("D", BlobBump(P_("gaskin", 0.175, -0.372, 0.780), self.r(np.array([0.022, 0.020, 0.030])),
                                           self.r(0.004 * rb)), 0.0))
        # sillon du biceps fémoral / semi-tendineux (face latérale de la cuisse)
        self.details.append(("D", Bump(M.p("hips", L(0.150, -0.690, 1.060)), P_("gaskin", 0.168, -0.630, 0.720),
                                       self.r(0.011), -self.r(0.0025 + 0.003 * mus), taper=0.3), 0.0))
        # sillon entre biceps fémoral et vaste latéral (devant)
        self.details.append(("D", Bump(P_("thigh", 0.200, -0.520, 1.020), P_("thigh", 0.200, -0.450, 0.830),
                                       self.r(0.012), -self.r(0.0018 + 0.002 * mus), taper=0.3), 0.0))
        # gastrocnémien : relief à l'arrière haut de la jambe
        self.details.append(("D", BlobBump(P_("gaskin", 0.150, -0.640, 0.650), self.r(np.array([0.030, 0.030, 0.060])),
                                           self.r(0.003 * rm)), 0.0))
        # creux du jarret entre tendon calcanéen et tibia (deux faces)
        for so in (-1.0, 1.0):
            self.details.append(("S", Ellipsoid(P_("gaskin", 0.121 + so * 0.044, -0.648, 0.540),
                                                self.r([0.012, 0.022, 0.055])), 0.012))
        # calcanéum (pointe du jarret)
        g.add("U", RoundCone(P_("hind_cannon", 0.120, -0.650, 0.440), P_("hind_cannon", 0.120, -0.694, 0.482),
                             self.r(0.020 * rb), self.r(0.0165 * rb)), 0.014)
        # sillon os du canon / tendons
        for sgn in (-1.0, 1.0):
            off = 0.0245 if sgn > 0 else -0.0235
            self.details.append(("D", Bump(P_("hind_cannon", 0.118 + off, -0.632, 0.360),
                                           P_("hind_cannon", 0.111 + off, -0.622, 0.190),
                                           self.r(0.0045), -self.r(0.0016), taper=0.2), 0.0))
        for dz in (-1.0, 1.0):
            g.add("U", Ellipsoid(P_("hind_hoof", 0.110 + dz * 0.018, -0.574, 0.038), self.r([0.017, 0.017, 0.019])),
                  0.014)
        hoof, hf = self.hoof(side, sx, front=False)
        g.add("U", Ellipsoid(hf["corona_c"], hf["corona_r"], hf["corona_R"]), 0.008)
        if p.micro_detail > 0:
            md = p.micro_detail
            self.details.append(("D", Bump(P_("gaskin", 0.095, -0.470, 0.700), P_("gaskin", 0.090, -0.590, 0.480),
                                           self.r(0.0035), self.r(0.0012 * md), taper=0.2), 0.0))
        chestnut = Group(f"chestnut_h{side}")
        Rc = np.stack([latv, np.array([0, 1.0, 0]), np.array([0, 0, 1.0])], 1)
        chestnut.add("U", Ellipsoid(P_("hind_cannon", 0.0935, -0.622, 0.370), self.r([0.0055, 0.0110, 0.016]), Rc))
        ergot = Group(f"ergot_h{side}")
        ergot.add("U", Ellipsoid(P_("hind_pastern", 0.110, -0.6545, 0.118), self.r([0.0095, 0.0062, 0.0085])))
        if fat > 0:
            self.details.append(("D", BlobBump(M.p("hips", L(0.060, -0.700, 1.215)),
                                               self.r(np.array([0.040, 0.06, 0.04])), self.r(0.010 * fat)), 0.0))
        self.regions[f"hind_{side}"] = g
        self.regions[f"hoof_h{side}"] = hoof
        self.regions[f"chestnut_h{side}"] = chestnut
        self.regions[f"ergot_h{side}"] = ergot
        return dict(leg=g, hoof=hoof, chestnut=chestnut, ergot=ergot)

    # ------------------------------------------------------------------ queue
    def tail(self):
        M = self.M
        g = Group("tail")
        names = ["tail_01", "tail_02", "tail_03", "tail_04"]
        pts = [M.jh(n) for n in names] + [M.jt("tail_04")]
        radii = [0.036, 0.031, 0.026, 0.021, 0.016]
        root = M.p("hips", (0.0, -0.745, 1.215))
        g.add("U", RoundCone(root, pts[0], self.r(0.045), self.r(radii[0])))
        for i in range(4):
            g.add("U", RoundCone(pts[i], pts[i + 1], self.r(radii[i]), self.r(radii[i + 1])), 0.01)
        # anus / périnée : léger relief sous la base de la queue
        g.add("U", Ellipsoid(M.p("hips", (0.0, -0.782, 1.100)), self.r([0.024, 0.018, 0.026])), 0.02)
        return g


def _axis_rot(axis, ang):
    a = unit(axis)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(ang) * K + (1 - math.cos(ang)) * K @ K


def _num_grad(fn, p, eps=5e-4):
    p = np.asarray(p, float)
    out = []
    for i in range(3):
        d = np.zeros(3)
        d[i] = eps
        out.append((fn((p + d)[None].astype(F32))[0] - fn((p - d)[None].astype(F32))[0]) / (2 * eps))
    return np.array(out)


# ==============================================================================================
# Échantillonnage en bande étroite + marching cubes par super-blocs
# ==============================================================================================
def mesh_narrowband(sdf, h=0.004, lo=None, hi=None, block=8, superblock=8, log=print):
    """Maillage de l'iso-surface 0 par marching cubes (scikit-image) en bande étroite.

    1) grille grossière (pas h·block) ; 2) échantillons fins évalués une seule fois (index global) dans
    les blocs proches de la surface ; 3) marching cubes par super-bloc en espace d'indices, sommets
    fusionnés exactement aux frontières. Renvoie (V (n,3) float64, F (m,3) int64), maillage fermé.
    """
    import time

    from skimage import measure

    t0 = time.perf_counter()
    lo = np.asarray(sdf.lo if lo is None else lo, float) - 2 * h
    hi = np.asarray(sdf.hi if hi is None else hi, float) + 2 * h
    lo[2] = min(lo[2], -2 * h)
    hc = h * block
    nc = np.ceil((hi - lo) / hc).astype(int) + 1
    nf = (nc - 1) * block + 1                      # nombre d'échantillons fins par axe
    gx = [lo[i] + hc * np.arange(nc[i]) for i in range(3)]
    G = np.stack(np.meshgrid(*gx, indexing="ij"), -1).reshape(-1, 3)
    dc = sdf(G, margin=0.12, cell=0.30).reshape(nc)
    t1 = time.perf_counter()
    thr = hc * 1.9
    near = np.abs(dc) < thr
    sgn = dc > 0
    act = np.zeros(nc - 1, bool)
    mixed = np.zeros(nc - 1, bool)
    s0 = sgn[:-1, :-1, :-1]
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                sl = (slice(dx, nc[0] - 1 + dx), slice(dy, nc[1] - 1 + dy), slice(dz, nc[2] - 1 + dz))
                act |= near[sl]
                mixed |= sgn[sl] != s0
    act |= mixed
    blocks = np.argwhere(act)
    log(f"[mesh] grille grossière {tuple(int(v) for v in nc)} en {t1 - t0:.1f}s ; blocs actifs {len(blocks)}")
    # échantillons fins uniques (index global)
    lx = np.arange(block + 1)
    LL = np.stack(np.meshgrid(lx, lx, lx, indexing="ij"), -1).reshape(-1, 3)
    keys = []
    for chunk in np.array_split(blocks, max(1, len(blocks) // 2000)):
        ijk = (chunk[:, None, :] * block + LL[None, :, :]).reshape(-1, 3).astype(np.int64)
        keys.append((ijk[:, 0] * nf[1] + ijk[:, 1]) * nf[2] + ijk[:, 2])
    keys = np.unique(np.concatenate(keys))
    kk = keys.copy()
    k2 = kk % nf[2]
    kk //= nf[2]
    k1 = kk % nf[1]
    k0 = kk // nf[1]
    P = lo + np.stack([k0, k1, k2], 1) * h
    vals = sdf(P, margin=4 * h + 0.01).astype(np.float32)
    t2 = time.perf_counter()
    log(f"[mesh] {len(keys) / 1e6:.2f} M échantillons fins évalués en {t2 - t1:.1f}s")
    # super-blocs
    nsb = np.ceil((nc - 1) / superblock).astype(int)
    Vs, Fs = [], []
    voff = 0
    sb_of_block = blocks // superblock
    order = np.lexsort((sb_of_block[:, 2], sb_of_block[:, 1], sb_of_block[:, 0]))
    sbk = (sb_of_block[order, 0] * nsb[1] + sb_of_block[order, 1]) * nsb[2] + sb_of_block[order, 2]
    cuts = np.flatnonzero(np.diff(sbk)) + 1
    for grp in np.split(order, cuts):
        sbi = sb_of_block[grp[0]]
        b0 = sbi * superblock                       # premier bloc du super-bloc
        nb = np.minimum(superblock, (nc - 1) - b0)
        n = nb * block + 1
        f0 = b0 * block                             # premier échantillon fin
        cs = dc[b0[0]:b0[0] + nb[0] + 1, b0[1]:b0[1] + nb[1] + 1, b0[2]:b0[2] + nb[2] + 1]
        ix = [np.minimum((np.arange(n[a]) + block // 2) // block, cs.shape[a] - 1) for a in range(3)]
        vol = (np.sign(cs[np.ix_(ix[0], ix[1], ix[2])]) * hc).astype(np.float32)
        loc = (blocks[grp] - b0)[:, None, :] * block + LL[None, :, :]
        loc = np.unique(loc.reshape(-1, 3), axis=0)
        gi = loc + f0
        gk = (gi[:, 0].astype(np.int64) * nf[1] + gi[:, 1]) * nf[2] + gi[:, 2]
        pos = np.searchsorted(keys, gk)
        vol[loc[:, 0], loc[:, 1], loc[:, 2]] = vals[pos]
        if vol.min() > 0 or vol.max() < 0:
            continue
        try:
            V, Fc, _, _ = measure.marching_cubes(vol, 0.0, allow_degenerate=False)
        except (ValueError, RuntimeError):
            continue
        Vs.append(V.astype(np.float64) + f0)
        Fs.append(Fc + voff)
        voff += len(V)
    V = np.concatenate(Vs)
    Fm = np.concatenate(Fs)
    key = np.round(V * 4096.0).astype(np.int64)     # coordonnées en espace d'indices : exactes entre super-blocs
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = np.asarray(inv).ravel()
    V2 = lo + V[first] * h
    Fm = inv[Fm].reshape(-1, 3)
    good = (Fm[:, 0] != Fm[:, 1]) & (Fm[:, 1] != Fm[:, 2]) & (Fm[:, 0] != Fm[:, 2])
    Fm = Fm[good]
    t3 = time.perf_counter()
    log(f"[mesh] h={h * 1000:.1f} mm : {len(V2)} sommets, {len(Fm)} triangles, {t3 - t0:.1f}s")
    return V2, Fm
