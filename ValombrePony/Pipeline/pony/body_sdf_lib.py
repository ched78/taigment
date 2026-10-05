"""Bibliothèque SDF (numpy, float32) pour le corps du poney : primitives, opérateurs lisses,
arbre d'évaluation avec élagage spatial (AABB) et évaluation par blocs.

Conventions : coordonnées Blender (x droite du poney, y avant, z haut), mètres.
Toutes les fonctions prennent des points (N, 3) et renvoient des distances signées (N,)
(négatif = intérieur). Les distances sont des approximations « bornées » (Inigo Quilez) :
exactes sur l'iso-surface 0, approximatives ailleurs [I].
"""
from __future__ import annotations

import math

import numpy as np

F32 = np.float32
BIG = F32(10.0)


# ----------------------------------------------------------------------------------------------
# Opérateurs lisses
# ----------------------------------------------------------------------------------------------
def smin(a, b, k):
    """Union lisse polynomiale (quadratique). k = largeur du raccord (m)."""
    if k <= 0.0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b + (a - b) * h - k * h * (1.0 - h)


def smax(a, b, k):
    if k <= 0.0:
        return np.maximum(a, b)
    return -smin(-a, -b, k)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def frame_from_axis(axis, ref=(1.0, 0.0, 0.0)):
    """Repère orthonormé (colonnes) : col0 = ref projeté ⊥ axis, col1 = axis, col2 = col0 × col1."""
    e = unit(axis)
    r = np.asarray(ref, dtype=np.float64)
    u = r - np.dot(r, e) * e
    if np.linalg.norm(u) < 1e-6:
        r = np.array([0.0, 0.0, 1.0]) if abs(e[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = r - np.dot(r, e) * e
    u = unit(u)
    w = np.cross(u, e)
    return np.stack([u, e, w], axis=1)


def superellipse_dist(x, z, w, h, n):
    """Distance approchée (F/|∇F|) à la super-ellipse |x/w|^n + |z/h|^n = 1 (2D)."""
    ax = np.abs(x) / w + 1e-7
    az = np.abs(z) / h + 1e-7
    pa = np.power(ax, n)
    pz = np.power(az, n)
    G = pa + pz
    Gn = np.power(G, 1.0 / n)
    F = Gn - 1.0
    gx = pa / ax / w
    gz = pz / az / h
    grad = Gn / G * np.sqrt(gx * gx + gz * gz)
    return F / np.maximum(grad, 1e-9)


# ----------------------------------------------------------------------------------------------
# Primitives
# ----------------------------------------------------------------------------------------------
class Prim:
    lo: np.ndarray
    hi: np.ndarray
    pad = 0.0  # pour les déplacements : amplitude max (élargit l'élagage)

    def eval(self, P):  # pragma: no cover - abstrait
        raise NotImplementedError


class Ellipsoid(Prim):
    """Ellipsoïde (approximation IQ). R : colonnes = axes locaux (monde)."""

    def __init__(self, c, r, R=None):
        self.c = np.asarray(c, F32)
        self.r = np.maximum(np.asarray(r, F32), F32(1e-4))
        self.R = np.eye(3, dtype=F32) if R is None else np.asarray(R, F32)
        ext = np.sqrt(((self.R * self.r[None, :]) ** 2).sum(1))
        self.lo, self.hi = self.c - ext, self.c + ext

    def eval(self, P):
        q = (P - self.c) @ self.R
        k0 = np.sqrt(((q / self.r) ** 2).sum(1))
        k1 = np.sqrt(((q / (self.r * self.r)) ** 2).sum(1))
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


class Segment(Prim):
    """Segment effilé à section elliptique et bouts ellipsoïdaux (« ellipsoïde allongé »).

    r1 = (r1a, r1b) : demi-axe selon `lat` (projeté ⊥ à l'axe) ; r2 = (r2a, r2b) : demi-axe selon
    u2 = e × u1 (dans le plan sagittal pour un membre). caps : longueur des bouts (défaut = min des rayons).
    """

    def __init__(self, a, b, r1, r2, caps=None, lat=(1.0, 0.0, 0.0)):
        self.a = np.asarray(a, F32)
        b = np.asarray(b, F32)
        e = b - self.a
        self.L = F32(np.linalg.norm(e))
        R = frame_from_axis(e, lat)
        self.u1, self.e, self.u2 = (R[:, 0].astype(F32), R[:, 1].astype(F32), R[:, 2].astype(F32))
        self.r1a, self.r1b = F32(r1[0]), F32(r1[1])
        self.r2a, self.r2b = F32(r2[0]), F32(r2[1])
        if caps is None:
            caps = (min(r1[0], r2[0]), min(r1[1], r2[1]))
        self.ca, self.cb = F32(caps[0]), F32(caps[1])
        m = max(r1[0], r1[1], r2[0], r2[1], caps[0], caps[1])
        self.lo = np.minimum(self.a, b) - m
        self.hi = np.maximum(self.a, b) + m

    def eval(self, P):
        D = P - self.a
        t = D @ self.e
        q1 = D @ self.u1
        q2 = D @ self.u2
        h = np.clip(t / self.L, 0.0, 1.0)
        r1 = self.r1a + (self.r1b - self.r1a) * h
        r2 = self.r2a + (self.r2b - self.r2a) * h
        ex = np.where(t < 0, -t, np.where(t > self.L, t - self.L, 0.0))
        rc = np.where(t < 0, self.ca, self.cb)
        a0 = q1 / r1
        a1 = q2 / r2
        a2 = ex / rc
        k0 = np.sqrt(a0 * a0 + a1 * a1 + a2 * a2)
        k1 = np.sqrt((a0 / r1) ** 2 + (a1 / r2) ** 2 + (a2 / rc) ** 2)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


class RoundCone(Prim):
    """Cône arrondi exact (IQ) : sphères de rayons r1 en a et r2 en b, tangentes."""

    def __init__(self, a, b, r1, r2):
        self.a = np.asarray(a, F32)
        self.b = np.asarray(b, F32)
        self.r1, self.r2 = F32(r1), F32(r2)
        ba = self.b - self.a
        self.ba = ba
        self.l2 = F32(ba @ ba)
        self.rr = F32(r1 - r2)
        self.a2 = F32(self.l2 - self.rr * self.rr)
        assert self.a2 > 0, "RoundCone : |r1-r2| doit être < longueur"
        m = max(r1, r2)
        self.lo = np.minimum(self.a, self.b) - m
        self.hi = np.maximum(self.a, self.b) + m

    def eval(self, P):
        il2 = 1.0 / self.l2
        pa = P - self.a
        y = pa @ self.ba
        z = y - self.l2
        v = pa * self.l2 - y[:, None] * self.ba[None, :]
        x2 = (v * v).sum(1)
        y2 = y * y * self.l2
        z2 = z * z * self.l2
        k = np.sign(self.rr) * self.rr * self.rr * x2
        d1 = np.sqrt(x2 + z2) * il2 - self.r2
        d2 = np.sqrt(x2 + y2) * il2 - self.r1
        d3 = (np.sqrt(np.maximum(x2 * self.a2 * il2, 0.0)) + y * self.rr) * il2 - self.r1
        return np.where(np.sign(z) * self.a2 * z2 > k, d1, np.where(np.sign(y) * self.a2 * y2 < k, d2, d3))


class RoundBox(Prim):
    def __init__(self, c, half, rad, R=None):
        self.c = np.asarray(c, F32)
        self.half = np.asarray(half, F32)
        self.rad = F32(rad)
        self.R = np.eye(3, dtype=F32) if R is None else np.asarray(R, F32)
        ext = np.abs(self.R) @ self.half
        self.lo, self.hi = self.c - ext, self.c + ext

    def eval(self, P):
        q = np.abs((P - self.c) @ self.R) - (self.half - self.rad)
        qp = np.maximum(q, 0.0)
        return np.sqrt((qp * qp).sum(1)) + np.minimum(q.max(1), 0.0) - self.rad


class Sphere(Prim):
    def __init__(self, c, r):
        self.c = np.asarray(c, F32)
        self.r = F32(r)
        self.lo, self.hi = self.c - r, self.c + r

    def eval(self, P):
        D = P - self.c
        return np.sqrt((D * D).sum(1)) - self.r


class Loft(Prim):
    """Corps de révolution « plat » le long d'un axe : sections super-elliptiques asymétriques.

    Stations (s_i le long de `axis` depuis O) : top/bot (le long de `normal`), w (demi-largeur latérale),
    wf (fraction de hauteur où la largeur est maximale, depuis bot), nt/nb (exposants haut/bas).
    Interpolation monotone (PCHIP). La distance est calculée dans le plan de section [I].
    """

    def __init__(self, O, axis, normal, s, top, bot, w, wf, nt, nb, cap0=0.0, cap1=0.0):
        from scipy.interpolate import PchipInterpolator

        self.cap0, self.cap1 = F32(cap0), F32(cap1)

        self.O = np.asarray(O, F32)
        self.ax = unit(axis).astype(F32)
        n = np.asarray(normal, np.float64)
        n = unit(n - np.dot(n, self.ax) * self.ax)
        self.nm = n.astype(F32)
        self.xh = unit(np.cross(self.ax, self.nm)).astype(F32)
        s = np.asarray(s, np.float64)
        order = np.argsort(s)
        tab = np.stack([np.asarray(v, np.float64)[order] for v in (top, bot, w, wf, nt, nb)], 1)
        self.s = s[order]
        self.s0, self.s1 = F32(self.s[0]), F32(self.s[-1])
        self.interp = PchipInterpolator(self.s, tab, axis=0)
        ss = np.linspace(self.s[0], self.s[-1], 64)
        tb = self.interp(ss)
        pts = []
        for sv, row in zip(ss, tb):
            for vv in (row[0], row[1]):
                for xx in (-row[2], row[2]):
                    pts.append(self.O + sv * self.ax + vv * self.nm + xx * self.xh)
        pts = np.array(pts)
        capm = max(cap0, cap1)
        self.lo = pts.min(0).astype(F32) - 0.01 - capm
        self.hi = pts.max(0).astype(F32) + 0.01 + capm

    def params(self, s):
        return self.interp(np.clip(s, self.s[0], self.s[-1])).astype(F32)

    def eval(self, P):
        D = P - self.O
        s = D @ self.ax
        v = D @ self.nm
        x = D @ self.xh
        prm = self.params(s)
        top, bot, w, wf, nt, nb = (prm[:, i] for i in range(6))
        zc = bot + wf * (top - bot)
        up = v >= zc
        h = np.where(up, top - zc, zc - bot)
        n = np.where(up, nt, nb)
        # bouts arrondis (dôme ellipsoïdal de longueur cap) ou plats
        e0 = self.s0 - s
        e1 = s - self.s1
        sh = np.ones_like(s)
        if self.cap0 > 0:
            k = np.clip(e0 / self.cap0, 0.0, 0.999)
            sh = np.where(e0 > 0, np.sqrt(1.0 - k * k), sh)
        if self.cap1 > 0:
            k = np.clip(e1 / self.cap1, 0.0, 0.999)
            sh = np.where(e1 > 0, np.sqrt(1.0 - k * k), sh)
        d2 = superellipse_dist(x, v - (zc - (1 - sh) * 0.0), np.maximum(w * sh, 1e-4), np.maximum(h * sh, 1e-4), n)
        e = np.maximum(e0 - (self.cap0 if self.cap0 > 0 else 0.0), e1 - (self.cap1 if self.cap1 > 0 else 0.0))
        flat = np.where(e > 0, np.where(d2 > 0, np.sqrt(d2 * d2 + e * e), e), d2)
        return flat.astype(F32)


class VLoft(Prim):
    """Membre « vertical » : sections horizontales à 4 quadrants super-elliptiques.

    Stations en z : centre (xc, yc), demi-étendues avant F (+y), arrière Bk (−y), latérale Lt
    (côté extérieur, signe `sx`), médiale Md, exposant n. Interpolation PCHIP en z. Permet de régler
    directement les silhouettes de profil (F/Bk) et de face (Lt/Md). Bouts plans (fondus ailleurs) [I].
    """

    def __init__(self, z, xc, yc, F, Bk, Lt, Md, n, sx=1.0):
        from scipy.interpolate import PchipInterpolator

        z = np.asarray(z, np.float64)
        order = np.argsort(z)
        tab = np.stack([np.asarray(v, np.float64)[order] for v in (xc, yc, F, Bk, Lt, Md, n)], 1)
        self.z = z[order]
        self.z0, self.z1 = F32(self.z[0]), F32(self.z[-1])
        self.interp = PchipInterpolator(self.z, tab, axis=0)
        self.sx = F32(sx)
        zz = np.linspace(self.z[0], self.z[-1], 64)
        tb = self.interp(zz)
        xs = np.concatenate([tb[:, 0] + sx * tb[:, 4], tb[:, 0] - sx * tb[:, 5]])
        ys = np.concatenate([tb[:, 1] + tb[:, 2], tb[:, 1] - tb[:, 3]])
        self.lo = np.array([xs.min(), ys.min(), self.z[0]], F32) - 0.01
        self.hi = np.array([xs.max(), ys.max(), self.z[-1]], F32) + 0.01

    def params(self, z):
        return self.interp(np.clip(z, self.z[0], self.z[-1])).astype(F32)

    def eval(self, P):
        z = P[:, 2]
        prm = self.params(z)
        xc, yc, Fr, Bk, Lt, Md, n = (prm[:, i] for i in range(7))
        dx = (P[:, 0] - xc) * self.sx
        dy = P[:, 1] - yc
        ay = np.where(dy >= 0, Fr, Bk)
        axx = np.where(dx >= 0, Lt, Md)
        d2 = superellipse_dist(dx, dy, np.maximum(axx, 1e-4), np.maximum(ay, 1e-4), n)
        e = np.maximum(self.z0 - z, z - self.z1)
        return np.where(e > 0, np.where(d2 > 0, np.sqrt(d2 * d2 + e * e), e), d2).astype(F32)


class Hoof(Prim):
    """Sabot : tronc de cône à section super-elliptique, paroi en pince inclinée, talons, couronne inclinée.

    Repère : O au sol au centre de l'appui, fwd (vers la pince, horizontal), up (+Z).
    """

    def __init__(self, O, fwd, Lf, Lb, W0, Ht, Hh, ang_toe, ang_heel, flare, ex=2.2, toe_narrow=0.0,
                 k_ground=0.003, k_top=0.002):
        self.O = np.asarray(O, F32)
        f = np.asarray(fwd, np.float64)
        f[2] = 0.0
        self.f = unit(f).astype(F32)
        self.up = np.array([0, 0, 1], F32)
        self.l = np.cross(self.f, self.up).astype(F32)
        self.Lf, self.Lb, self.W0, self.Ht, self.Hh = (F32(v) for v in (Lf, Lb, W0, Ht, Hh))
        self.tt, self.th = F32(1.0 / math.tan(ang_toe)), F32(1.0 / math.tan(ang_heel))
        self.flare, self.ex, self.tn = F32(flare), F32(ex), F32(toe_narrow)
        self.kg, self.kt = k_ground, k_top
        m = max(Lf, Lb, W0) + 0.01
        self.lo = self.O + np.array([-m, -m, -0.005], F32)
        self.hi = self.O + np.array([m, m, Ht + 0.01], F32)

    def eval(self, P):
        D = P - self.O
        f = D @ self.f
        l = D @ self.l
        z = D[:, 2]
        zc = np.clip(z, 0.0, self.Ht)
        ff = self.Lf - zc * self.tt
        fb = -self.Lb + zc * self.th
        A = np.maximum((ff - fb) * 0.5, 1e-3)
        cf = (ff + fb) * 0.5
        W = self.W0 - zc * self.flare
        rel = np.clip((f - cf) / A, -1.0, 1.0)
        Weff = W * (1.0 - self.tn * np.maximum(rel, 0.0) ** 2)
        d2 = superellipse_dist(l, f - cf, Weff, A, self.ex) * 0.85
        zcor = self.Hh + (self.Ht - self.Hh) * np.clip((f + self.Lb) / (self.Lf + self.Lb), 0.0, 1.0)
        d = smax(d2, -z, self.kg)
        d = smax(d, z - zcor, self.kt)
        return d.astype(F32)


class Bump(Prim):
    """Déplacement gaussien le long d'un segment (crête si amp > 0, sillon si amp < 0).

    Utilisé avec l'opération 'D' : d ← d − valeur.
    """

    def __init__(self, a, b, width, amp, taper=0.25):
        self.a = np.asarray(a, F32)
        b = np.asarray(b, F32)
        e = b - self.a
        self.L = F32(max(np.linalg.norm(e), 1e-6))
        self.e = (e / self.L).astype(F32)
        self.w = F32(width)
        self.amp = F32(amp)
        self.tp = F32(max(taper, 1e-3))
        self.pad = abs(amp)
        m = 3.0 * width
        self.lo = np.minimum(self.a, b) - m
        self.hi = np.maximum(self.a, b) + m

    def eval(self, P):
        D = P - self.a
        tt = (D @ self.e) / self.L
        t = np.clip(tt, 0.0, 1.0)
        R = D - (t * self.L)[:, None] * self.e[None, :]
        r2 = (R * R).sum(1)
        win = smoothstep(0.0, self.tp, tt) * smoothstep(0.0, self.tp, 1.0 - tt)
        return self.amp * np.exp(-r2 / (self.w * self.w)) * win


class PolyBump(Prim):
    """Déplacement gaussien le long d'une polyligne (fenêtre lissée sur l'abscisse curviligne totale)."""

    def __init__(self, pts, width, amp, taper=0.15):
        self.pts = np.asarray(pts, F32)
        seg = self.pts[1:] - self.pts[:-1]
        self.len = np.linalg.norm(seg, axis=1).astype(F32)
        self.cum = np.concatenate([[0.0], np.cumsum(self.len)]).astype(F32)
        self.total = F32(self.cum[-1])
        self.dir = (seg / np.maximum(self.len[:, None], 1e-9)).astype(F32)
        self.w = F32(width)
        self.amp = F32(amp)
        self.tp = F32(max(taper, 1e-3))
        self.pad = abs(amp)
        m = 3.0 * width
        self.lo = self.pts.min(0) - m
        self.hi = self.pts.max(0) + m

    def eval(self, P):
        best = np.full(len(P), np.inf, F32)
        arc = np.zeros(len(P), F32)
        for i in range(len(self.len)):
            D = P - self.pts[i]
            t = np.clip(D @ self.dir[i], 0.0, self.len[i])
            R = D - t[:, None] * self.dir[i][None, :]
            r2 = (R * R).sum(1)
            m = r2 < best
            best = np.where(m, r2, best)
            arc = np.where(m, self.cum[i] + t, arc)
        u = arc / self.total
        win = smoothstep(0.0, self.tp, u) * smoothstep(0.0, self.tp, 1.0 - u)
        return self.amp * np.exp(-best / (self.w * self.w)) * win


class BlobBump(Prim):
    """Déplacement gaussien ellipsoïdal (bosse/creux local). Opération 'D'."""

    def __init__(self, c, r, amp, R=None):
        self.c = np.asarray(c, F32)
        self.r = np.asarray(r, F32)
        self.R = np.eye(3, dtype=F32) if R is None else np.asarray(R, F32)
        self.amp = F32(amp)
        self.pad = abs(amp)
        ext = np.sqrt(((self.R * (2.5 * self.r)[None, :]) ** 2).sum(1))
        self.lo, self.hi = self.c - ext, self.c + ext

    def eval(self, P):
        q = (P - self.c) @ self.R / self.r
        return self.amp * np.exp(-(q * q).sum(1))


class Func(Prim):
    """Primitive définie par une fonction arbitraire (avec AABB fournie)."""

    def __init__(self, fn, lo, hi, pad=0.0):
        self.fn = fn
        self.lo = np.asarray(lo, F32)
        self.hi = np.asarray(hi, F32)
        self.pad = pad

    def eval(self, P):
        return self.fn(P).astype(F32)


# ----------------------------------------------------------------------------------------------
# Arbre d'évaluation
# ----------------------------------------------------------------------------------------------
OPS = ("U", "S", "I", "D")  # union lisse, soustraction lisse, intersection lisse, déplacement additif


class Group:
    """Groupe ordonné d'opérations. Un groupe est lui-même une primitive (récursif)."""

    def __init__(self, name: str):
        self.name = name
        self.nodes = []  # (op, child, k, lo, hi)
        self.lo = np.full(3, np.inf, F32)
        self.hi = np.full(3, -np.inf, F32)
        self.pad = 0.0

    def add(self, op, child, k=0.0):
        assert op in OPS
        if child is None:
            return child
        lo = np.asarray(child.lo, F32)
        hi = np.asarray(child.hi, F32)
        self.nodes.append((op, child, float(k), lo, hi))
        if op == "U":
            self.lo = np.minimum(self.lo, lo - k)
            self.hi = np.maximum(self.hi, hi + k)
        return child

    def _arrays(self):
        c = getattr(self, "_cache", None)
        if c is None or c[0] != len(self.nodes):
            lo = np.array([n[3] for n in self.nodes], F32).reshape(-1, 3)
            hi = np.array([n[4] for n in self.nodes], F32).reshape(-1, 3)
            ext = np.array([n[2] + getattr(n[1], "pad", 0.0) for n in self.nodes], F32)
            self._cache = c = (len(self.nodes), lo, hi, ext)
        return c

    def eval_box(self, P, lo, hi, margin):
        _, nlo, nhi, ext = self._arrays()
        m = (ext + margin)[:, None]
        rel = ~(np.any(nlo - m > hi, axis=1) | np.any(nhi + m < lo, axis=1))
        d = None
        for j in np.flatnonzero(rel):
            op, ch, k, clo, chi = self.nodes[j]
            v = ch.eval_box(P, lo, hi, margin) if isinstance(ch, Group) else ch.eval(P)
            if d is None:
                if op == "U":
                    d = v
                    continue
                d = np.full(len(P), BIG, F32)
            if op == "U":
                d = smin(d, v, k)
            elif op == "S":
                d = smax(d, -v, k)
            elif op == "I":
                d = smax(d, v, k)
            else:  # 'D'
                d = d - v
        if d is None:
            d = np.full(len(P), BIG, F32)
        return d.astype(F32, copy=False)

    def eval(self, P):
        P = np.asarray(P, F32)
        if len(P) == 0:
            return np.zeros(0, F32)
        return self.eval_box(P, P.min(0), P.max(0), 1e3)

    def find(self, name):
        if self.name == name:
            return self
        for _, ch, *_ in self.nodes:
            if isinstance(ch, Group):
                r = ch.find(name)
                if r is not None:
                    return r
        return None

    def groups(self):
        out = [self]
        for _, ch, *_ in self.nodes:
            if isinstance(ch, Group):
                out += ch.groups()
        return out


def evaluate(root: Group, P, margin=0.05, cell=0.08):
    """Évaluation par blocs spatiaux (élagage AABB par bloc). Précise pour |d| < margin − k,
    signe correct ailleurs [I]."""
    P = np.ascontiguousarray(np.asarray(P, F32))
    N = len(P)
    out = np.empty(N, F32)
    if N == 0:
        return out
    lo = P.min(0)
    # taille de bloc adaptée à la densité (évite des milliers de blocs presque vides)
    ext = np.maximum(P.max(0) - lo, 1e-3)
    occ = N / max(1.0, float(np.prod(np.ceil(ext / cell))))
    if occ < 64.0:
        cell = float(min(0.35, cell * (64.0 / max(occ, 1e-3)) ** (1.0 / 3.0)))
    key3 = np.floor((P - lo) / cell).astype(np.int64)
    dims = key3.max(0) + 1
    key = (key3[:, 0] * dims[1] + key3[:, 1]) * dims[2] + key3[:, 2]
    order = np.argsort(key, kind="stable")
    ks = key[order]
    cuts = np.flatnonzero(np.diff(ks)) + 1
    for idx in np.split(order, cuts):
        Q = P[idx]
        out[idx] = root.eval_box(Q, Q.min(0), Q.max(0), margin)
    return out


_TET = np.array([[1, -1, -1], [-1, -1, 1], [-1, 1, -1], [1, 1, 1]], F32)


def gradient(fn, P, eps=4e-4):
    """Gradient par la méthode du tétraèdre (4 évaluations). fn : (N,3) -> (N,)."""
    P = np.asarray(P, F32)
    N = len(P)
    Q = (P[None, :, :] + eps * _TET[:, None, :]).reshape(-1, 3)
    v = fn(Q).reshape(4, N)
    g = (_TET[:, None, :] * v[:, :, None]).sum(0) / (4.0 * eps)
    return g


def project(fn, P, iters=4, eps=4e-4, max_step=0.02):
    """Projette des points sur l'iso-surface 0 (pas de Newton d/|∇d|², bornés)."""
    P = np.array(P, F32)
    for _ in range(iters):
        d = fn(P)
        g = gradient(fn, P, eps)
        gg = np.maximum((g * g).sum(1), 1e-6)
        step = (d / gg)[:, None] * g
        n = np.linalg.norm(step, axis=1)
        s = np.minimum(1.0, max_step / np.maximum(n, 1e-12))
        P -= step * s[:, None]
    return P


def ray_surface(fn, origin, direction, t_max=0.5, n=200):
    """Premier point où fn change de signe (de l'intérieur vers l'extérieur) le long d'un rayon."""
    origin = np.asarray(origin, np.float64)
    d = unit(direction)
    ts = np.linspace(0.0, t_max, n)
    P = (origin[None, :] + ts[:, None] * d[None, :]).astype(F32)
    v = fn(P)
    idx = np.flatnonzero((v[:-1] <= 0) & (v[1:] > 0))
    if len(idx) == 0:
        idx = np.flatnonzero(np.sign(v[:-1]) != np.sign(v[1:]))
        if len(idx) == 0:
            return None
    i = idx[0]
    a, b = ts[i], ts[i + 1]
    fa = v[i]
    for _ in range(30):
        m = 0.5 * (a + b)
        fm = fn((origin + m * d)[None, :].astype(F32))[0]
        if (fm <= 0) == (fa <= 0):
            a, fa = m, fm
        else:
            b = m
    return origin + 0.5 * (a + b) * d


def ray_surface_batch(fn, origins, dirs, t_max=0.3, n=160, iters=22):
    """Version vectorisée de ray_surface : premier passage intérieur→extérieur le long de chaque rayon.
    Renvoie (points (R,3), ok (R,) bool)."""
    O = np.asarray(origins, np.float64)
    D = np.asarray(dirs, np.float64)
    D = D / np.linalg.norm(D, axis=1, keepdims=True)
    R = len(O)
    ts = np.linspace(0.0, t_max, n)
    P = (O[:, None, :] + ts[None, :, None] * D[:, None, :]).reshape(-1, 3).astype(F32)
    v = fn(P).reshape(R, n)
    cross = (v[:, :-1] <= 0) & (v[:, 1:] > 0)
    ok = cross.any(1)
    i = np.argmax(cross, axis=1)
    a = ts[i].copy()
    b = ts[np.minimum(i + 1, n - 1)].copy()
    for _ in range(iters):
        m = 0.5 * (a + b)
        fm = fn((O + m[:, None] * D).astype(F32))
        inside = fm <= 0
        a = np.where(inside, m, a)
        b = np.where(inside, b, m)
    return O + (0.5 * (a + b))[:, None] * D, ok
