"""Surface du corps pour l'ajustement des crins : requêtes (plus proche point, rayons, distance signée),
chargement du vrai corps (`Pipeline/build/body.blend`, objet `Body`) ou d'un corps PROVISOIRE, et extraction des
lignes d'implantation (crête de l'encolure, nuque/front, tronçon de queue, arrière des boulets).

Le corps provisoire est une surface implicite (union lisse d'ellipsoïdes et de capsules placés d'après les joints de
l'armature) polygonisée par marching cubes. Il ne sert qu'à développer et prévisualiser tant que l'agent « body »
n'a pas livré `body.blend` ; ses formes sont des approximations artistiques [A].
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import conventions as cv
from . import template

BODY_BLEND = cv.BUILD_DIR / "body.blend"
BODY_OBJECT = "Body"


# ----------------------------------------------------------------------------------------------
# Requêtes de surface
# ----------------------------------------------------------------------------------------------
class BodySurface:
    """Surface triangulée (coordonnées Blender) avec normales lissées et poids de peau optionnels."""

    def __init__(self, verts, tris, weights=None, joint_names=None, source="?"):
        from mathutils.bvhtree import BVHTree

        self.verts = np.asarray(verts, np.float64)
        self.tris = np.asarray(tris, np.int64)
        self.weights = None if weights is None else np.asarray(weights, np.float64)   # (V, J)
        self.joint_names = list(joint_names) if joint_names is not None else list(template.JOINT_NAMES)
        self.source = source
        self.bvh = BVHTree.FromPolygons(self.verts.tolist(), self.tris.tolist(), all_triangles=True)
        # normales de faces et de sommets (pondérées par l'aire)
        a, b, c = (self.verts[self.tris[:, i]] for i in range(3))
        fn = np.cross(b - a, c - a)
        self.face_area2 = np.linalg.norm(fn, axis=1)
        self.face_normals = fn / np.maximum(self.face_area2[:, None], 1e-20)
        vn = np.zeros_like(self.verts)
        for i in range(3):
            np.add.at(vn, self.tris[:, i], fn)
        self.vert_normals = vn / np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-20)

    # -- requêtes élémentaires ------------------------------------------------------------------
    def _bary(self, p, fi):
        a, b, c = (self.verts[self.tris[fi, i]] for i in range(3))
        v0, v1, v2 = b - a, c - a, p - a
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-30:
            return np.array([1.0, 0.0, 0.0])
        v = (d11 * d20 - d01 * d21) / den
        w = (d00 * d21 - d01 * d20) / den
        bc = np.clip(np.array([1.0 - v - w, v, w]), 0.0, 1.0)
        return bc / bc.sum()

    def nearest(self, p):
        """(point, normale lissée, distance signée, index de face, barycentriques) pour un point."""
        p = np.asarray(p, np.float64)
        loc, _n, fi, _d = self.bvh.find_nearest(p.tolist())
        if loc is None:
            return None
        q = np.array(loc)
        bc = self._bary(q, fi)
        n = (self.vert_normals[self.tris[fi]] * bc[:, None]).sum(0)
        n /= max(np.linalg.norm(n), 1e-20)
        d = p - q
        dist = np.linalg.norm(d)
        # signe : normale de face (robuste) ; si ambigu, normale lissée
        s = d @ self.face_normals[fi]
        if abs(s) < 1e-9:
            s = d @ n
        return q, n, (dist if s >= 0 else -dist), fi, bc

    def signed_distance(self, P):
        P = np.atleast_2d(P)
        return np.array([self.nearest(p)[2] for p in P])

    def ray(self, origin, direction, max_dist=10.0):
        """Premier impact (point, normale lissée, distance, face) ou None."""
        d = np.asarray(direction, np.float64)
        d = d / np.linalg.norm(d)
        loc, _n, fi, dist = self.bvh.ray_cast(np.asarray(origin, np.float64).tolist(), d.tolist(), max_dist)
        if loc is None:
            return None
        q = np.array(loc)
        bc = self._bary(q, fi)
        n = (self.vert_normals[self.tris[fi]] * bc[:, None]).sum(0)
        n /= max(np.linalg.norm(n), 1e-20)
        return q, n, dist, fi

    def ray_all(self, origin, direction, max_dist=10.0, eps=1e-5):
        """Tous les impacts le long du rayon (liste triée)."""
        hits = []
        o = np.asarray(origin, np.float64)
        d = np.asarray(direction, np.float64)
        d = d / np.linalg.norm(d)
        travelled = 0.0
        for _ in range(64):
            h = self.ray(o, d, max_dist - travelled)
            if h is None:
                break
            hits.append((h[0], h[1], travelled + h[2], h[3]))
            travelled += h[2] + eps
            o = h[0] + d * eps
        return hits

    def push_out(self, p, min_offset):
        """Repousse p à au moins `min_offset` au-dessus de la surface. Renvoie (p', normale, distance signée)."""
        q, n, sd, _fi, _bc = self.nearest(p)
        if sd < min_offset:
            return q + n * min_offset, n, min_offset
        return np.asarray(p, np.float64), n, sd

    def skin_weights_at(self, p):
        """Poids de peau du corps interpolés au point de surface le plus proche : (J,) ou None."""
        if self.weights is None:
            return None
        q, n, sd, fi, bc = self.nearest(p)
        w = (self.weights[self.tris[fi]] * bc[:, None]).sum(0)
        s = w.sum()
        return w / s if s > 1e-9 else None


# ----------------------------------------------------------------------------------------------
# Joints
# ----------------------------------------------------------------------------------------------
def joints_from_armature(arm):
    """dict nom -> (head, tail) en coordonnées Blender, lus sur l'armature (pose de repos)."""
    out = {}
    for b in arm.data.bones:
        out[b.name] = (np.array(b.head_local, np.float64), np.array(b.tail_local, np.float64))
    return out


# ----------------------------------------------------------------------------------------------
# Corps réel
# ----------------------------------------------------------------------------------------------
def body_available(path=BODY_BLEND) -> bool:
    return Path(path).exists()


def load_body_from_blend(path=BODY_BLEND, object_name=BODY_OBJECT, link_into_scene=False):
    """Charge l'objet `Body` depuis body.blend : renvoie (BodySurface, objet bpy ou None).

    La géométrie est lue en pose de repos, sans modificateurs ni formes (coordonnées de base du maillage,
    transformées par la matrice monde de l'objet). Les poids sont lus dans les groupes de sommets nommés
    comme les joints.
    """
    import bpy

    path = str(path)
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        if object_name not in src.objects:
            raise RuntimeError(f"{path} ne contient pas d'objet {object_name!r} (objets : {list(src.objects)[:20]})")
        dst.objects = [object_name]
    obj = dst.objects[0]
    me = obj.data
    mw = np.array(obj.matrix_world, np.float64)
    n = len(me.vertices)
    co = np.empty(n * 3, np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    me.calc_loop_triangles()
    tris = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get("vertices", tris)
    tris = tris.reshape(-1, 3)
    names = list(template.JOINT_NAMES)
    W = np.zeros((n, len(names)))
    gidx = {g.index: g.name for g in obj.vertex_groups}
    jidx = {nm: i for i, nm in enumerate(names)}
    for v in me.vertices:
        for g in v.groups:
            nm = gidx.get(g.group)
            if nm in jidx:
                W[v.index, jidx[nm]] = g.weight
    has_w = W.sum(1) > 1e-6
    weights = W if has_w.mean() > 0.9 else None
    if link_into_scene:
        bpy.context.scene.collection.objects.link(obj)
    surf = BodySurface(co, tris, weights, names, source=f"body.blend ({n} sommets, {len(tris)} triangles)")
    return surf, obj


# ----------------------------------------------------------------------------------------------
# Corps provisoire (SDF -> marching cubes)
# ----------------------------------------------------------------------------------------------
def _frame_from_axis(axis, up_hint=(0.0, 0.0, 1.0)):
    a = np.asarray(axis, np.float64)
    a = a / np.linalg.norm(a)
    x = np.array([1.0, 0.0, 0.0])
    if abs(a @ x) > 0.95:
        x = np.cross(a, np.asarray(up_hint))
    x = x - a * (x @ a)
    x /= np.linalg.norm(x)
    z = np.cross(x, a)
    return np.stack([x, a, z], 1)   # colonnes : latéral, axe, dorsal


def _sd_ellipsoid(p, c, r, R=None):
    q = p - np.asarray(c)
    if R is not None:
        q = q @ R
    q = q / np.asarray(r)
    r = np.asarray(r)
    k0 = np.linalg.norm(q, axis=-1)
    k1 = np.linalg.norm(q / r, axis=-1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def _sd_capsule(p, a, b, ra, rb=None):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    rb = ra if rb is None else rb
    pa = p - a
    ba = b - a
    h = np.clip((pa @ ba) / (ba @ ba), 0.0, 1.0)
    d = np.linalg.norm(pa - h[..., None] * ba, axis=-1)
    return d - (ra + (rb - ra) * h)


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def provisional_sdf(J):
    """Fonction SDF approximative du poney, alignée sur les joints J (dict nom -> (head, tail)). [A]"""
    H = lambda n: J[n][0]
    T = lambda n: J[n][1]
    head_j = H("head")
    muzzle = T("head")
    hax = muzzle - head_j
    hlen = np.linalg.norm(hax)
    hax /= hlen
    hdor = np.array([0.0, -hax[2], hax[1]])
    Rh = _frame_from_axis(hax)

    def hp(s, d, x=0.0):
        return head_j + s * hax * (hlen / 0.495) + d * hdor + np.array([x, 0, 0])

    withers = np.array(template.LANDMARKS["withers_top"])
    poll = np.array(template.LANDMARKS["poll_top"])

    def f(p):
        d = _sd_ellipsoid(p, (0, -0.07, 0.975), (0.205, 0.56, 0.29))
        d = _smin(d, _sd_ellipsoid(p, (0, 0.40, 0.99), (0.185, 0.25, 0.27)), 0.08)
        for sx in (-1, 1):
            d = _smin(d, _sd_ellipsoid(p, (sx * 0.095, 0.47, 0.98), (0.095, 0.17, 0.22)), 0.06)
            d = _smin(d, _sd_ellipsoid(p, (sx * 0.10, -0.60, 0.99), (0.11, 0.18, 0.22)), 0.07)
        d = _smin(d, _sd_capsule(p, (0, 0.10, 1.19), (0, 0.33, 1.235), 0.065), 0.08)
        d = _smin(d, _sd_ellipsoid(p, (0, -0.50, 1.075), (0.20, 0.30, 0.235)), 0.08)
        # encolure : ellipsoïdes entre la ligne du dessus (crête) et la ligne du dessous (gorge)
        A, B, C = np.array([0, 0.28, 1.25]), np.array([0, 0.62, 1.47]), poll + np.array([0, -0.02, -0.01])
        A2, B2, C2 = np.array([0, 0.66, 0.93]), np.array([0, 0.80, 1.12]), hp(0.10, -0.10)
        for t in np.linspace(0.0, 1.0, 11):
            top = (1 - t) ** 2 * A + 2 * (1 - t) * t * B + t * t * C
            bot = (1 - t) ** 2 * A2 + 2 * (1 - t) * t * B2 + t * t * C2
            c = (top + bot) / 2
            vert = top - bot
            depth = np.linalg.norm(vert) / 2
            ax = np.cross(np.array([1.0, 0, 0]), vert / np.linalg.norm(vert))   # le long de l'encolure
            R = np.stack([np.array([1.0, 0, 0]), ax, vert / np.linalg.norm(vert)], 1)
            rx = 0.135 * (1 - t) + 0.072 * t
            d = _smin(d, _sd_ellipsoid(p, c, (rx, 0.09, depth), R), 0.06)
        # tête
        d = _smin(d, _sd_ellipsoid(p, hp(0.07, 0.0), (0.083, 0.12, 0.088), Rh), 0.05)
        d = _smin(d, _sd_ellipsoid(p, hp(0.14, -0.065), (0.088, 0.12, 0.085), Rh), 0.05)
        d = _smin(d, _sd_ellipsoid(p, hp(0.27, 0.0), (0.064, 0.17, 0.068), Rh), 0.05)
        d = _smin(d, _sd_ellipsoid(p, hp(0.43, -0.025), (0.062, 0.075, 0.07), Rh), 0.04)
        for sx in (-1, 1):
            base = hp(0.0, 0.062, sx * 0.052)
            tip = base + np.array([sx * 0.02, 0.03, 0.125])
            d = _smin(d, _sd_capsule(p, base, tip, 0.026, 0.006), 0.025)
        # queue (tronçon)
        d = _smin(d, _sd_capsule(p, H("tail_01") + np.array([0, 0.03, 0.0]), H("tail_02"), 0.050, 0.045), 0.05)
        for a, b, ra, rb in (("tail_02", "tail_03", 0.045, 0.038), ("tail_03", "tail_04", 0.038, 0.032)):
            d = _smin(d, _sd_capsule(p, H(a), H(b), ra, rb), 0.02)
        d = _smin(d, _sd_capsule(p, H("tail_04"), T("tail_04"), 0.032, 0.026), 0.02)
        # membres
        for s in ("l", "r"):
            d = _smin(d, _sd_capsule(p, H(f"upperarm_{s}") + np.array([0, 0.0, 0.05]), H(f"forearm_{s}"), 0.075, 0.065), 0.06)
            d = _smin(d, _sd_capsule(p, H(f"forearm_{s}"), H(f"front_cannon_{s}"), 0.062, 0.040), 0.04)
            d = _smin(d, _sd_capsule(p, H(f"front_cannon_{s}"), H(f"front_pastern_{s}"), 0.034, 0.031), 0.02)
            d = _smin(d, _sd_ellipsoid(p, H(f"front_pastern_{s}") + np.array([0, -0.005, 0.0]), (0.036, 0.042, 0.04)), 0.02)
            d = _smin(d, _sd_capsule(p, H(f"front_pastern_{s}"), H(f"front_hoof_{s}"), 0.029, 0.033), 0.015)
            hb = H(f"front_hoof_{s}")
            d = _smin(d, _sd_capsule(p, hb, hb + np.array([0, 0.02, -0.035]), 0.036, 0.048), 0.01)
            d = _smin(d, _sd_capsule(p, H(f"thigh_{s}") + np.array([0, 0.0, 0.03]), H(f"gaskin_{s}"), 0.12, 0.085), 0.07)
            d = _smin(d, _sd_capsule(p, H(f"gaskin_{s}"), H(f"hind_cannon_{s}"), 0.075, 0.045), 0.04)
            d = _smin(d, _sd_ellipsoid(p, H(f"hind_cannon_{s}") + np.array([0, -0.02, 0.01]), (0.042, 0.06, 0.05)), 0.02)
            d = _smin(d, _sd_capsule(p, H(f"hind_cannon_{s}"), H(f"hind_pastern_{s}"), 0.034, 0.031), 0.02)
            d = _smin(d, _sd_ellipsoid(p, H(f"hind_pastern_{s}") + np.array([0, -0.005, 0.0]), (0.036, 0.042, 0.04)), 0.02)
            d = _smin(d, _sd_capsule(p, H(f"hind_pastern_{s}"), H(f"hind_hoof_{s}"), 0.029, 0.033), 0.015)
            hb = H(f"hind_hoof_{s}")
            d = _smin(d, _sd_capsule(p, hb, hb + np.array([0, 0.02, -0.035]), 0.036, 0.046), 0.01)
        # sol : coupe sous z = 0
        d = np.maximum(d, -p[..., 2])
        return d

    return f


def provisional_body(J, h=0.011):
    """(verts, tris) du corps provisoire, par marching cubes (skimage) puis lissage de Taubin."""
    from skimage import measure

    f = provisional_sdf(J)
    lo = np.array([-0.32, -1.08, -0.01])
    hi = np.array([0.32, 1.42, 1.72])
    n = np.ceil((hi - lo) / h).astype(int) + 1
    xs = [lo[i] + h * np.arange(n[i]) for i in range(3)]
    X, Y, Z = np.meshgrid(*xs, indexing="ij")
    P = np.stack([X, Y, Z], -1).reshape(-1, 3)
    vol = np.empty(len(P))
    chunk = 400000
    for i in range(0, len(P), chunk):
        vol[i:i + chunk] = f(P[i:i + chunk])
    vol = vol.reshape(X.shape)
    verts, faces, _n, _v = measure.marching_cubes(vol, 0.0, spacing=(h, h, h))
    verts = verts + lo
    # orientation de skimage : normales déjà sortantes pour une SDF négative à l'intérieur (vérifié par outward_check)
    verts = _taubin(verts, faces, 6)
    return verts, faces


def _taubin(V, F, iters=6, lam=0.5, mu=-0.53):
    from scipy import sparse

    n = len(V)
    i = np.concatenate([F[:, 0], F[:, 1], F[:, 2], F[:, 1], F[:, 2], F[:, 0]])
    j = np.concatenate([F[:, 1], F[:, 2], F[:, 0], F[:, 0], F[:, 1], F[:, 2]])
    A = sparse.coo_matrix((np.ones(len(i)), (i, j)), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    deg = np.asarray(A.sum(1)).ravel()
    deg[deg == 0] = 1
    Dinv = sparse.diags(1.0 / deg)
    L = Dinv @ A
    V = V.copy()
    for _ in range(iters):
        V = V + lam * (L @ V - V)
        V = V + mu * (L @ V - V)
    return V


def outward_check(surface: BodySurface):
    """Vérifie que les normales sont sortantes (rayon vertical depuis au-dessus du garrot)."""
    h = surface.ray(np.array([0.0, 0.0, 3.0]), np.array([0.0, 0.0, -1.0]))
    return h is not None and h[1][2] > 0


# ----------------------------------------------------------------------------------------------
# Lignes d'implantation
# ----------------------------------------------------------------------------------------------
def _polyline_resample(P, n):
    P = np.asarray(P, np.float64)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, s[-1], n)
    out = np.stack([np.interp(t, s, P[:, k]) for k in range(3)], 1)
    return out, s[-1]


def _smooth_polyline(P, iters=3):
    P = P.copy()
    for _ in range(iters):
        P[1:-1] = 0.25 * P[:-2] + 0.5 * P[1:-1] + 0.25 * P[2:]
    return P


def crest_line(surface: BodySurface, J, n=80, y_start=None, y_end=None):
    """Ligne de crête (racines de la crinière) du garrot à la nuque, sur la surface (x = 0).

    Renvoie dict(points (n,3), tangents, normals, length). Échantillonnée à pas constant.
    Rayons lancés depuis l'extérieur, vers l'axe de l'encolure, perpendiculairement à la chaîne neck_01…head.
    """
    chain = [J[f"neck_{i:02d}"][0] for i in range(1, 7)] + [J["head"][0]]
    chain = np.array(chain)
    # prolonge la chaîne vers l'arrière (garrot) pour couvrir le début de la crinière
    back = chain[0] - (chain[1] - chain[0]) * 1.2
    chain = np.vstack([back, chain])
    dense, L = _polyline_resample(chain, 160)
    pts = []
    for i in range(len(dense)):
        a = dense[i]
        tng = dense[min(i + 1, len(dense) - 1)] - dense[max(i - 1, 0)]
        tng /= np.linalg.norm(tng)
        dor = np.array([0.0, -tng[2], tng[1]])
        if dor[2] < 0:
            dor = -dor
        h = surface.ray(a + dor * 0.6, -dor, 0.65)
        if h is not None:
            pts.append(h[0])
    pts = np.array(pts)
    pts[:, 0] = 0.0
    pts = _smooth_polyline(pts, 4)
    y0 = y_start if y_start is not None else template.LANDMARKS["withers_top"][1] + 0.05
    y1 = y_end if y_end is not None else J["head"][0][1] - 0.035
    keep = (pts[:, 1] >= y0) & (pts[:, 1] <= y1)
    pts = pts[keep]
    pts, L = _polyline_resample(pts, n)
    # recale exactement sur la surface (rayon vertical/dorsal local)
    out = []
    for i, p in enumerate(pts):
        q, nrm, sd, fi, bc = surface.nearest(p)
        out.append(q)
    pts = np.array(out)
    pts[:, 0] = 0.0
    tang = np.gradient(pts, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True)
    nrms = np.array([surface.nearest(p)[1] for p in pts])
    nrms[:, 0] = 0.0
    nrms -= tang * (nrms * tang).sum(1, keepdims=True)
    nrms /= np.linalg.norm(nrms, axis=1, keepdims=True)
    return {"points": pts, "tangents": tang, "normals": nrms, "length": L}


def head_frame(J):
    """Repère de la tête : origine (joint head), axe nuque→nez, dorsal (chanfrein), latéral (+X)."""
    o = J["head"][0]
    ax = J["head"][1] - o
    ax /= np.linalg.norm(ax)
    dor = np.array([0.0, -ax[2], ax[1]])
    return o, ax, dor, np.array([1.0, 0.0, 0.0])


def head_surface_point(surface: BodySurface, J, s, x=0.0, d_from=0.4):
    """Point de la surface dorsale de la tête à l'abscisse s (m le long de l'axe) et latéral x."""
    o, ax, dor, lat = head_frame(J)
    base = o + ax * s + lat * x
    h = surface.ray(base + dor * d_from, -dor, d_from + 0.1)
    if h is None:
        return None
    return h[0], h[1]


def dock_axis(J, n=40):
    pts = [J[f"tail_{i:02d}"][0] for i in range(1, 5)] + [J["tail_04"][1]]
    return _polyline_resample(np.array(pts), n)


def tail_chain(J):
    pts = [J[f"tail_{i:02d}"][0] for i in range(1, 11)] + [J["tail_10"][1]]
    return np.array(pts)
