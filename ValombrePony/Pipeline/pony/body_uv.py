"""UV du corps (UV0 unique, 2048²) : coutures géodésiques lisses, îlots anatomiques, dépliage ABF,
orientation et densité par îlot, rangement avec marge contrôlée, mesures de distorsion.

Coutures (toutes des chemins d'arêtes « lisses » trouvés par Dijkstra guidé, jamais des frontières en escalier) :
- anneau tête/encolure (plan ⊥ à l'axe de la tête, juste derrière la nuque et la gorge) ;
- ligne médiane ventrale de la tête (gorge → auge → menton → fente buccale) ;
- ligne médiane ventrale du corps (gorge → poitrail → ventre → entre les postérieurs → périnée → dessous de la
  queue → bout du tronçon) ;
- anneau à la base de chaque oreille + ligne arrière de l'oreille (base → pointe) ;
- anneau sur chaque membre (avant-bras / jambe) + ligne caudo-médiale jusqu'à la couronne ;
- couronne de chaque sabot, bord de la sole, ligne des talons ;
- bords des poches (sac conjonctival, conduits des naseaux, cavité buccale ; la cavité buccale est en plus
  coupée en toit / plancher le long de sa couture arrière).

Îlots : body (tronc + encolure + haut des membres + queue), head, ear_l/r, leg_fl/fr/hl/hr, hoofwall_*, sole_*,
pocket_eye_l/r, pocket_nostril_l/r, pocket_mouth_roof / pocket_mouth_floor.
Orientation [I] : body (+y avant → +u), head (axe nuque → nez → −v, donc v croît vers la nuque), oreilles et
membres (+z → +v), parois des sabots (+z → +v : la CIRCONFÉRENCE du sabot suit u), soles (pince → +v).
Densité relative de texels [I] : cf. DENSITY.
"""
from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

from .body_sdf_lib import unit

DENSITY = {"body": 1.0, "head": 1.6, "ear": 1.35, "leg": 1.3, "hoofwall": 1.15, "sole": 0.6,
           "pocket_eye": 0.6, "pocket_nostril": 0.45, "pocket_mouth": 0.45}
LEG_RING_Z = {"f": 0.60, "h": 0.62}          # [I] hauteur (gabarit de référence) des anneaux de coupe des membres
HEAD_RING_Q = (0.0, 0.835, 1.40)            # [I] point du plan de l'anneau tête/encolure (gabarit, os « head »)
HEAD_RING_N = (0.0, 0.98, -0.20)            # [I] normale du plan (presque vertical : nuque → gorge, derrière la ganache)
LOG = print


# ==============================================================================================
# Graphe du maillage
# ==============================================================================================
class MeshGraph:
    def __init__(self, bm):
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.verts.index_update()
        bm.edges.index_update()
        bm.faces.index_update()
        bm.normal_update()
        self.bm = bm
        self.V = np.array([v.co[:] for v in bm.verts], float)
        self.N = np.array([v.normal[:] for v in bm.verts], float)
        self.E = np.array([[e.verts[0].index, e.verts[1].index] for e in bm.edges], np.int64)
        self.L = np.linalg.norm(self.V[self.E[:, 0]] - self.V[self.E[:, 1]], axis=1)
        self.faces = [np.array([v.index for v in f.verts]) for f in bm.faces]
        self.face_edges = [np.array([e.index for e in f.edges]) for f in bm.faces]
        self.edge_faces = [[f.index for f in e.link_faces] for e in bm.edges]
        self.ekey = {(min(a, b), max(a, b)): i for i, (a, b) in enumerate(self.E)}
        self.FC = np.array([self.V[f].mean(0) for f in self.faces])
        self.FN = np.array([f.normal[:] for f in bm.faces])
        self.seam = np.zeros(len(self.E), bool)
        self.mean_edge = float(np.median(self.L))

    def csr(self, w):
        n = len(self.V)
        ok = np.isfinite(w)
        E = self.E[ok]
        ww = w[ok]
        return coo_matrix((np.r_[ww, ww], (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n)).tocsr()

    def path(self, G, a, b):
        """Liste d'arêtes du plus court chemin a → b (ou None)."""
        dist, pred = dijkstra(G, indices=int(a), return_predecessors=True)
        if not np.isfinite(dist[b]):
            return None
        out = []
        v = int(b)
        while v != a:
            u = int(pred[v])
            if u < 0:
                return None
            out.append(self.ekey[(min(u, v), max(u, v))])
            v = u
        return out[::-1]

    def path_verts(self, edges, start):
        vs = [int(start)]
        for e in edges:
            a, b = self.E[e]
            vs.append(int(b) if a == vs[-1] else int(a))
        return vs


# ==============================================================================================
# Coutures : anneaux iso-valeur et chemins guidés
# ==============================================================================================
def iso_loop(g: MeshGraph, f, level, mask, center_fn, axis, ref, band=None, n_anchor=12, name="loop"):
    """Boucle fermée d'arêtes suivant l'iso-valeur f = level (sommets de `mask`), faisant une fois le tour de
    `axis` (center_fn(P) = point de l'axe pour chaque sommet).

    Méthode : plus court chemin dans le revêtement double du graphe de la bande |f − level| < band (les arêtes
    qui traversent le demi-plan « barrière » d'angle θ0 changent de feuillet) ; le plus court chemin d'un sommet
    a (feuillet 0) à sa copie (feuillet 1) est la plus courte boucle passant par a qui fait le tour de l'axe.
    Coût d'une arête : longueur × (1 + 12 (écart à l'iso-valeur / bande)²). Renvoie les sommets ordonnés."""
    band0 = band or 2.5 * g.mean_edge
    axis = unit(axis)
    ref = unit(np.asarray(ref, float) - np.dot(ref, axis) * axis)
    w3 = np.cross(axis, ref)
    nV = len(g.V)
    last = ""
    for band in (band0, 1.5 * band0, 2.2 * band0, 3.2 * band0):
        ok_v = mask & (np.abs(f - level) < band)
        idx = np.flatnonzero(ok_v)
        if len(idx) < 8:
            last = "bande vide"
            continue
        R = g.V - center_fn(g.V)
        R -= (R @ axis)[:, None] * axis
        ang = np.arctan2(R @ w3, R @ ref)            # 0 = direction ref ; barrière à θ0 = π (opposé de ref)
        E = g.E
        ok_e = ok_v[E[:, 0]] & ok_v[E[:, 1]]
        fm = 0.5 * (f[E[:, 0]] + f[E[:, 1]])
        w = g.L * (1.0 + 12.0 * ((fm - level) / band) ** 2)
        a0, a1 = ang[E[:, 0]], ang[E[:, 1]]
        cross = ok_e & (np.abs(a0) > 0.5 * math.pi) & (np.abs(a1) > 0.5 * math.pi) & (np.sign(a0) != np.sign(a1))
        keep = ok_e & ~cross
        rows = np.r_[E[keep, 0], E[keep, 0] + nV, E[cross, 0], E[cross, 0] + nV]
        cols = np.r_[E[keep, 1], E[keep, 1] + nV, E[cross, 1] + nV, E[cross, 1]]
        ww = np.r_[w[keep], w[keep], w[cross], w[cross]]
        G = coo_matrix((np.r_[ww, ww], (np.r_[rows, cols], np.r_[cols, rows])), shape=(2 * nV, 2 * nV)).tocsr()
        # sommet de départ : près de l'iso-valeur, du côté opposé à la barrière
        sc = np.abs(f[idx] - level) / band + 0.5 * np.abs(ang[idx]) / math.pi
        a = int(idx[np.argmin(sc)])
        dist, pred = dijkstra(G, indices=a, return_predecessors=True)
        if not np.isfinite(dist[a + nV]):
            last = "pas de boucle autour de l'axe"
            continue
        seq = [a + nV]
        while seq[-1] != a:
            q = int(pred[seq[-1]])
            if q < 0:
                break
            seq.append(q)
        verts = [v % nV for v in seq[::-1]][:-1]
        if len(verts) != len(set(verts)):
            last = f"boucle non simple ({len(verts)} sommets, {len(set(verts))} distincts)"
            continue
        loop_edges = [g.ekey[(min(p, q), max(p, q))] for p, q in zip(verts, verts[1:] + verts[:1])]
        g.seam[loop_edges] = True
        dev = np.abs(f[verts] - level).max()
        LOG(f"[uv] couture {name} : {len(verts)} sommets, écart max à l'iso-valeur {dev * 1000:.1f} mm")
        return verts
    raise RuntimeError(f"couture {name} : aucune boucle simple ({last})")


def guided_path(g: MeshGraph, a, b, cost, allowed=None, name="path"):
    w = g.L * cost
    if allowed is not None:
        w = np.where(allowed, w, np.inf)
    G = g.csr(w)
    p = g.path(G, a, b)
    if p is None:
        raise RuntimeError(f"couture {name} : pas de chemin")
    g.seam[p] = True
    return g.path_verts(p, a)


def head_ring_value(rig, P):
    """> 0 du côté de la tête, < 0 du côté de l'encolure (plan nuque → gorge, porté par l'os « head »)."""
    Q = rig.p("head", np.array(HEAD_RING_Q))
    n = unit(rig.v("head", unit(np.array(HEAD_RING_N))))
    return (np.asarray(P, float) - Q) @ n, Q, n


def _edge_mid(g):
    return 0.5 * (g.V[g.E[:, 0]] + g.V[g.E[:, 1]]), 0.5 * (g.N[g.E[:, 0]] + g.N[g.E[:, 1]])


def _leg_axis_fn(rig, side, front):
    """Fonction : points -> point de l'axe du membre à la même hauteur (polyligne des joints)."""
    names = (["upperarm", "forearm", "front_cannon", "front_pastern", "front_hoof"] if front else
             ["thigh", "gaskin", "hind_cannon", "hind_pastern", "hind_hoof"])
    pts = [rig.jh(f"{n}_{side}") for n in names] + [rig.jt(f"{names[-1]}_{side}")]
    pts = np.array(pts)
    order = np.argsort(pts[:, 2])
    z, xs, ys = pts[order, 2], pts[order, 0], pts[order, 1]

    def fn(P):
        zz = P[:, 2]
        return np.stack([np.interp(zz, z, xs), np.interp(zz, z, ys), zz], 1)
    return fn


# ==============================================================================================
# Construction des coutures
# ==============================================================================================
def compute_seams(g: MeshGraph, sdf, pockets):
    """pockets : dict nom -> ensemble d'indices de faces (poches). Renvoie un dict d'infos (anneaux…)."""
    rig = sdf.rig
    feats = sdf.features
    V, N = g.V, g.N
    k = rig.k
    info = {}
    # --- bords des poches : frontières faces poche / peau
    pocket_of_face = np.full(len(g.faces), "", object)
    for name, fs in pockets.items():
        pocket_of_face[list(fs)] = name
    for i, fl in enumerate(g.edge_faces):
        if len(fl) == 2 and pocket_of_face[fl[0]] != pocket_of_face[fl[1]]:
            g.seam[i] = True
    pocket_vert = np.zeros(len(V), bool)
    for name, fs in pockets.items():
        for fi in fs:
            pocket_vert[g.faces[fi]] = True
    skin_vert = np.zeros(len(V), bool)
    for fi, f in enumerate(g.faces):
        if not pocket_of_face[fi]:
            skin_vert[f] = True
    boundary_vert = pocket_vert & skin_vert
    # --- anneau tête / encolure
    H = rig.jh("head")
    a = unit(rig.jt("head") - H)
    dn = unit(np.array([0.0, -a[2], a[1]]))
    fr, Q, nr = head_ring_value(rig, V)
    up = unit(np.array([0.0, 0.0, 1.0]) - np.dot([0.0, 0.0, 1.0], nr) * nr)
    mask = skin_vert & (np.linalg.norm((V - Q) - fr[:, None] * nr, axis=1) < 0.35 * k)
    head_ring = iso_loop(g, fr, 0.0, mask, lambda P: Q + ((P - Q) @ nr)[:, None] * nr + 0.0, nr, up,
                         n_anchor=12, name="head_ring")
    info["head_ring"] = head_ring
    hr = np.array(head_ring)
    # côtés de l'anneau : composantes connexes du graphe des sommets privé de l'anneau
    from scipy.sparse.csgraph import connected_components

    cut = np.zeros(len(V), bool)
    cut[hr] = True
    ke = ~cut[g.E[:, 0]] & ~cut[g.E[:, 1]]
    Gc = coo_matrix((np.ones(ke.sum()), (g.E[ke, 0], g.E[ke, 1])), shape=(len(V), len(V)))
    _, comp = connected_components(Gc, directed=False)
    withers = int(np.argmin(np.linalg.norm(V - rig.p("spine_03", (0.0, 0.25, 1.30)), axis=1)))
    body_side = (comp == comp[withers]) | cut
    head_side = (~(comp == comp[withers])) | cut
    throat_v = int(hr[np.argmin(V[hr, 2] + 5.0 * np.abs(V[hr, 0]))])
    # --- oreilles : anneau de base + ligne arrière
    for side in "lr":
        ea = feats[f"ear_{side}"]
        t = (V - ea.B) @ ea.e
        rad = np.linalg.norm((V - ea.B) - t[:, None] * ea.e, axis=1)
        m = skin_vert & (rad < 0.06 * k) & (t > -0.04 * k) & (t < 0.06 * k)
        ring = iso_loop(g, t, 0.012 * k, m, lambda P, ea=ea: ea.B + ((P - ea.B) @ ea.e)[:, None] * ea.e, ea.e, ea.f,
                        band=0.006 * k, n_anchor=8, name=f"ear_ring_{side}")
        info[f"ear_ring_{side}"] = ring
        mid, nm = _edge_mid(g)
        tt = (mid - ea.B) @ ea.e
        R = (mid - ea.B) - tt[:, None] * ea.e
        Rn = R / np.maximum(np.linalg.norm(R, axis=1, keepdims=True), 1e-9)
        ang = np.arccos(np.clip(Rn @ (-ea.f), -1, 1))
        allowed = (tt > 0.005 * k) & (np.linalg.norm(R, axis=1) < 0.06 * k)
        rr = np.array(ring)
        Rv = V[rr] - ea.B
        Rv -= (Rv @ ea.e)[:, None] * ea.e
        start = int(rr[np.argmax(unit_rows(Rv) @ (-ea.f))])
        tip = int(np.argmin(np.linalg.norm(V - (ea.B + ea.e * ea.length), axis=1) + 10 * (~skin_vert)))
        guided_path(g, start, tip, 1.0 + 6.0 * ang ** 2, allowed, name=f"ear_back_{side}")
    # --- tête : ligne médiane ventrale (gorge → bord de la poche buccale, lèvre inférieure)
    mf = feats["mouth"]
    mid, nm = _edge_mid(g)
    lower_mouth = boundary_vert & (((V - mf.O) @ mf.nm) < 0) & (np.linalg.norm(V - mf.O, axis=1) < 0.12 * k)
    cand = np.flatnonzero(lower_mouth)
    if len(cand) == 0:
        raise RuntimeError("bord inférieur de la poche buccale introuvable")
    mouth_v = int(cand[np.argmin(np.abs(V[cand, 0]) * 10 - (V[cand] - mf.O) @ mf.am)])
    sm, _, _ = head_ring_value(rig, mid)
    cost = 1.0 + 120.0 * np.abs(mid[:, 0]) / k + 3.0 * np.clip(nm @ dn + 0.3, 0, None)
    allowed = head_side[g.E[:, 0]] & head_side[g.E[:, 1]] & skin_vert[g.E[:, 0]] & skin_vert[g.E[:, 1]]
    guided_path(g, throat_v, mouth_v, cost, allowed, name="head_ventral")
    # --- corps : ligne médiane ventrale (gorge → bout de la queue)
    sternum = np.array([0.0, 0.30 * k, 0.66 * k])
    belly = np.array([0.0, -0.10 * k, 0.60 * k])
    groin = np.array([0.0, -0.50 * k, 0.80 * k])
    perineum = rig.p("hips", (0.0, -0.80, 1.06))
    tail_tip = rig.jt("tail_04")
    body_ok = skin_vert & body_side

    def nearest(p, m):
        idx = np.flatnonzero(m)
        return int(idx[np.argmin(np.linalg.norm(V[idx] - p, axis=1))])

    allowed_e = body_ok[g.E[:, 0]] & body_ok[g.E[:, 1]]
    cost_v = 1.0 + 80.0 * np.abs(mid[:, 0]) / k + 4.0 * np.clip(nm[:, 2] + 0.2, 0, None)
    pts = [throat_v]
    midline = body_ok & (np.abs(V[:, 0]) < 0.012 * k)
    for p, cond in ((sternum, N[:, 2] < -0.3), (belly, N[:, 2] < -0.5), (groin, N[:, 2] < -0.2),
                    (perineum, N[:, 1] < -0.2)):
        pts.append(nearest(p, midline & cond))
    for i in range(len(pts) - 1):
        guided_path(g, pts[i], pts[i + 1], cost_v, allowed_e, name=f"body_ventral_{i}")
    # dessous de la queue : face tournée vers le périnée (+y) / le bas
    tail_end = nearest(tail_tip, body_ok)
    cost_t = 1.0 + 80.0 * np.abs(mid[:, 0]) / k + 3.0 * np.clip(-(nm[:, 1] - nm[:, 2]) + 0.5, 0, None)
    guided_path(g, pts[-1], tail_end, cost_t, allowed_e, name="tail_ventral")
    # --- membres : anneau, ligne caudo-médiale, couronne, sole, talons
    for key in ("fl", "fr", "hl", "hr"):
        side = key[1]
        front = key[0] == "f"
        sx = -1.0 if side == "l" else 1.0
        axis_fn = _leg_axis_fn(rig, side, front)
        zc = LEG_RING_Z[key[0]] * k
        ac = axis_fn(V)
        dxy = np.linalg.norm((V - ac)[:, :2], axis=1)
        m = skin_vert & (dxy < (0.15 if front else 0.20) * k) & (np.abs(V[:, 2] - zc) < 0.06 * k)
        ring = iso_loop(g, V[:, 2], zc, m, axis_fn, np.array([0, 0, 1.0]), np.array([0, 1.0, 0]), n_anchor=8,
                        name=f"leg_ring_{key}")
        info[f"leg_ring_{key}"] = ring
        hf = feats[f"hoof_{key}"]
        # couronne : iso-valeur z − z_couronne(azimut)
        fl = (V - hf.O) @ hf.fwd
        zcor = hf.coronet_heel + (hf.coronet_toe - hf.coronet_heel) * np.clip((fl + hf.Lb) / (hf.Lf + hf.Lb), 0, 1)
        hd = np.linalg.norm((V - hf.O)[:, :2], axis=1)
        mh = skin_vert & (hd < 0.11 * k) & (V[:, 2] < 0.13 * k)
        cfn = lambda P, hf=hf: np.stack([np.full(len(P), hf.O[0]), np.full(len(P), hf.O[1]), P[:, 2]], 1)
        cor = iso_loop(g, V[:, 2] - zcor, 0.0012 * k, mh, cfn, np.array([0, 0, 1.0]), hf.fwd, band=0.006 * k,
                       n_anchor=10, name=f"coronet_{key}")
        info[f"coronet_{key}"] = cor
        ms = skin_vert & (hd < 0.11 * k) & (V[:, 2] < 0.045 * k)
        sole = iso_loop(g, N[:, 2], -0.55, ms, cfn, np.array([0, 0, 1.0]), hf.fwd, band=0.45,
                        name=f"sole_{key}")
        info[f"sole_{key}"] = sole
        # ligne caudo-médiale : anneau du membre → couronne
        tgt = unit(np.array([-sx * 0.75, -1.0, 0.0]))
        R = mid - axis_fn(mid)
        R[:, 2] = 0
        Rn = R / np.maximum(np.linalg.norm(R, axis=1, keepdims=True), 1e-9)
        ang = np.arccos(np.clip(Rn @ tgt, -1, 1))
        dmid = np.linalg.norm((mid - axis_fn(mid))[:, :2], axis=1)
        allowed = (mid[:, 2] < zc + 0.005 * k) & (dmid < 0.13 * k)
        rr = np.array(ring)
        Rv = V[rr] - axis_fn(V[rr])
        Rv[:, 2] = 0
        start = int(rr[np.argmax(unit_rows(Rv) @ tgt)])
        cc = np.array(cor)
        Rc = V[cc] - hf.O
        Rc[:, 2] = 0
        end = int(cc[np.argmax(unit_rows(Rc) @ unit(-hf.fwd + 0.6 * np.array([-sx, 0, 0]) * 0))])
        # extrémité : sommet de la couronne côté talon (milieu), la ligne passe ensuite derrière le boulet
        guided_path(g, start, end, 1.0 + 5.0 * ang ** 2, allowed, name=f"leg_back_{key}")
        # talons : de la couronne (talon) au bord de la sole, au milieu de l'arrière
        sl = np.array(sole)
        Rs = V[sl] - hf.O
        Rs[:, 2] = 0
        end2 = int(sl[np.argmax(unit_rows(Rs) @ (-hf.fwd))])
        bk = unit(-hf.fwd)
        Rh = mid - np.array([hf.O[0], hf.O[1], 0.0])
        Rh[:, 2] = 0
        angh = np.arccos(np.clip(unit_rows(Rh) @ bk, -1, 1))
        allowed = (np.linalg.norm(Rh, axis=1) < 0.11 * k) & (mid[:, 2] < hf.coronet_toe + 0.01 * k)
        guided_path(g, end, end2, 1.0 + 8.0 * angh ** 2, allowed, name=f"heel_{key}")
    # --- cavité buccale : couture arrière (toit / plancher)
    return info


def unit_rows(A):
    A = np.asarray(A, float)
    return A / np.maximum(np.linalg.norm(A, axis=1, keepdims=True), 1e-12)


# ==============================================================================================
# Îlots
# ==============================================================================================
def islands_from_seams(g: MeshGraph):
    parent = np.arange(len(g.faces))

    def find(i):
        r = i
        while parent[r] != r:
            r = parent[r]
        while parent[i] != r:
            parent[i], i = r, parent[i]
        return r

    for ei, fl in enumerate(g.edge_faces):
        if g.seam[ei] or len(fl) != 2:
            continue
        a, b = find(fl[0]), find(fl[1])
        if a != b:
            parent[a] = b
    roots = np.array([find(i) for i in range(len(g.faces))])
    _, lab = np.unique(roots, return_inverse=True)
    return lab


def name_islands(g: MeshGraph, sdf, isl, pockets):
    """Nom de chaque îlot d'après des sondes anatomiques (face la plus proche d'un point caractéristique)."""
    rig = sdf.rig
    feats = sdf.features
    k = rig.k
    names = {}
    face_pocket = {}
    for name, fs in pockets.items():
        for fi in fs:
            face_pocket[fi] = name
    probes = {"body": rig.p("spine_02", (0.0, 0.0, 1.25)), "head": rig.jh("head") + 0.25 * unit(
        rig.jt("head") - rig.jh("head")) + np.array([0.0, 0.0, 0.08]) * k}
    for side in "lr":
        ea = feats[f"ear_{side}"]
        probes[f"ear_{side}"] = ea.B + ea.e * 0.7 * ea.length
    for key in ("fl", "fr", "hl", "hr"):
        hf = feats[f"hoof_{key}"]
        side = key[1]
        probes[f"leg_{key}"] = rig.p(("front_cannon_" if key[0] == "f" else "hind_cannon_") + side,
                                     rig.rh(("front_cannon_" if key[0] == "f" else "hind_cannon_") + side) * 0.5 +
                                     rig.rt(("front_cannon_" if key[0] == "f" else "hind_cannon_") + side) * 0.5)
        probes[f"hoofwall_{key}"] = hf.O + hf.fwd * hf.Lf * 0.9 + np.array([0, 0, 0.5 * hf.coronet_toe])
        probes[f"sole_{key}"] = hf.O + np.array([0, 0, -0.01])
    cand_all = np.array([i for i in range(len(g.faces)) if i not in face_pocket])
    for nm_, p in probes.items():
        cand = cand_all
        if nm_.startswith("sole_"):
            cand = cand[g.FN[cand, 2] < -0.7]
        elif nm_.startswith("hoofwall_"):
            cand = cand[np.abs(g.FN[cand, 2]) < 0.6]
        fi = cand[np.argmin(np.linalg.norm(g.FC[cand] - p, axis=1))]
        names.setdefault(isl[fi], nm_)
    # poches
    for name, fs in pockets.items():
        ids = np.unique(isl[list(fs)])
        for i in ids:
            if i in names:
                continue
            if name == "mouth":
                fs_i = [f for f in fs if isl[f] == i]
                up = np.mean([(g.FC[f] - feats["mouth"].cav_c) @ feats["mouth"].nm for f in fs_i])
                names[i] = "pocket_mouth_roof" if up > 0 else "pocket_mouth_floor"
            else:
                names[i] = f"pocket_{name}"
    out = []
    for i in range(isl.max() + 1):
        out.append(names.get(i, f"misc_{i}"))
    return out


# ==============================================================================================
# Dépliage
# ==============================================================================================
def _loop_arrays(me):
    uv = np.zeros(len(me.loops) * 2, np.float64)
    me.uv_layers.active.data.foreach_get("uv", uv)
    ls = np.zeros(len(me.polygons), np.int64)
    lt = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    return uv.reshape(-1, 2), ls, lt, lv


def _orient_and_scale(me, isl, isl_names, rig, sdf):
    """Rotation de chaque îlot (direction 3D choisie → axe UV choisi) et mise à l'échelle (densité)."""
    uv, ls, lt, lv = _loop_arrays(me)
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    H = rig.jh("head")
    a = unit(rig.jt("head") - H)
    targets = {}
    for i, nm in enumerate(isl_names):
        if nm == "body":
            targets[i] = (np.array([0, 1.0, 0]), np.array([1.0, 0]))
        elif nm == "head":
            targets[i] = (a, np.array([0, -1.0]))
        elif nm.startswith("ear_"):
            ea = sdf.features[nm]
            targets[i] = (ea.e, np.array([0, 1.0]))
        elif nm.startswith(("leg_", "hoofwall_")):
            targets[i] = (np.array([0, 0, 1.0]), np.array([0, 1.0]))
        elif nm.startswith("sole_"):
            targets[i] = (sdf.features["hoof_" + nm[5:]].fwd, np.array([0, 1.0]))
    # triangles (éventail) : Jacobiennes 3D -> UV
    acc = {i: np.zeros(2) for i in range(len(isl_names))}
    area3 = np.zeros(len(isl_names))
    area2 = np.zeros(len(isl_names))
    for f in range(len(ls)):
        idx = np.arange(ls[f], ls[f] + lt[f])
        P = co[lv[idx]]
        U = uv[idx]
        i = isl[f]
        for t in range(1, lt[f] - 1):
            e1, e2 = P[t] - P[0], P[t + 1] - P[0]
            n = np.cross(e1, e2)
            A3 = 0.5 * np.linalg.norm(n)
            if A3 < 1e-12:
                continue
            d1, d2 = U[t] - U[0], U[t + 1] - U[0]
            A2 = 0.5 * abs(d1[0] * d2[1] - d1[1] * d2[0])
            area3[i] += A3
            area2[i] += A2
            if i in targets:
                D = targets[i][0]
                nn = n / (2 * A3)
                Dt = D - np.dot(D, nn) * nn
                if np.linalg.norm(Dt) < 1e-6:
                    continue
                # Dt = α e1 + β e2 -> image α d1 + β d2
                M = np.stack([e1, e2], 1)
                ab, *_ = np.linalg.lstsq(M, Dt, rcond=None)
                img = ab[0] * d1 + ab[1] * d2
                nrm = np.linalg.norm(img)
                if nrm > 1e-12:
                    acc[i] += img / nrm * A3
    # rotation + échelle par îlot
    for i, nm in enumerate(isl_names):
        loops = np.concatenate([np.arange(ls[f], ls[f] + lt[f]) for f in np.flatnonzero(isl == i)])
        U = uv[loops]
        c = U.mean(0)
        rot = 0.0
        if i in targets and np.linalg.norm(acc[i]) > 1e-12:
            cur = math.atan2(acc[i][1], acc[i][0])
            want = math.atan2(targets[i][1][1], targets[i][1][0])
            rot = want - cur
        cr, sr = math.cos(rot), math.sin(rot)
        Rm = np.array([[cr, -sr], [sr, cr]])
        base = nm.split("_")[0]
        dens = DENSITY.get(nm, DENSITY.get(base, DENSITY.get("_".join(nm.split("_")[:2]), 1.0)))
        if nm.startswith("pocket_mouth"):
            dens = DENSITY["pocket_mouth"]
        sc = math.sqrt(area3[i] / max(area2[i], 1e-15)) * dens
        uv[loops] = (U - c) @ Rm.T * sc + c
    me.uv_layers.active.data.foreach_set("uv", uv.ravel())


def unwrap(ob, g: MeshGraph, sdf, isl, isl_names, size=2048, margin_px=12, log=print):
    me = ob.data
    me.edges.foreach_set("use_seam", g.seam)
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(o is ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, correct_aspect=True, margin=0.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    _orient_and_scale(me, isl, isl_names, sdf.rig, sdf)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=False, scale=True, margin_method="FRACTION", margin=margin_px / size,
                            shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")


# ==============================================================================================
# Mesures
# ==============================================================================================
def uv_metrics(ob, isl, isl_names, size=2048):
    """Distorsion par triangle : densité de texels (px/m) rapportée à la densité cible de l'îlot,
    étirement conforme σ1/σ2 ; écart minimal entre îlots (px) mesuré par rastérisation."""
    me = ob.data
    uv, ls, lt, lv = _loop_arrays(me)
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    rows = []
    for f in range(len(ls)):
        idx = np.arange(ls[f], ls[f] + lt[f])
        P = co[lv[idx]]
        U = uv[idx]
        for t in range(1, lt[f] - 1):
            e1, e2 = P[t] - P[0], P[t + 1] - P[0]
            n = np.cross(e1, e2)
            A3 = 0.5 * np.linalg.norm(n)
            if A3 < 1e-12:
                continue
            x = e1 / np.linalg.norm(e1)
            y = np.cross(n / (2 * A3), x)
            Pm = np.array([[e1 @ x, e2 @ x], [e1 @ y, e2 @ y]])
            Um = np.array([U[t] - U[0], U[t + 1] - U[0]]).T
            J = Um @ np.linalg.inv(Pm)
            sv = np.linalg.svd(J, compute_uv=False)
            det = np.linalg.det(J)
            rows.append((isl[f], A3, sv[0], sv[1], det))
    R = np.array(rows)
    isl_t = R[:, 0].astype(int)
    A3 = R[:, 1]
    dens = np.sqrt(np.abs(R[:, 4])) * size            # px / m
    stretch = R[:, 2] / np.maximum(R[:, 3], 1e-12)
    flipped = float(A3[R[:, 4] < 0].sum() / A3.sum())
    per = {}
    rel = np.zeros_like(dens)
    for i, nm in enumerate(isl_names):
        m = isl_t == i
        if not m.any():
            continue
        dmed = float(np.median(dens[m]))
        rel[m] = dens[m] / dmed
        per[nm] = dict(faces=int(m.sum()), texel_density_px_per_m=round(dmed, 1),
                       area_ratio_p5_p95=[round(float(np.percentile(rel[m] ** 2, 5)), 3),
                                          round(float(np.percentile(rel[m] ** 2, 95)), 3)],
                       stretch_median=round(float(np.median(stretch[m])), 3),
                       stretch_p95=round(float(np.percentile(stretch[m], 95)), 3))
    w = A3 / A3.sum()

    def wpct(x, q):
        o = np.argsort(x)
        c = np.cumsum(w[o])
        return float(x[o][np.searchsorted(c, q / 100.0)])

    return dict(
        triangles=int(len(R)),
        area_distortion_p5_p95=[round(wpct(rel ** 2, 5), 3), round(wpct(rel ** 2, 95), 3)],
        area_distortion_note="(aire UV / aire 3D) / médiane de l'îlot, pondérée par l'aire 3D ; 1 = aucune",
        conformal_stretch_median=round(wpct(stretch, 50), 3), conformal_stretch_p95=round(wpct(stretch, 95), 3),
        conformal_stretch_note="σ1/σ2 de la Jacobienne 3D→UV, pondéré par l'aire ; 1 = conforme",
        flipped_area_fraction=round(flipped, 5),
        uv_coverage=round(float((np.abs(R[:, 4]) * A3).sum()), 4),
        islands=per)


def island_gap_px(ob, isl, size=2048):
    """Écart minimal (px, à `size`) entre deux îlots différents : rastérisation + transformée de distance."""
    from scipy.ndimage import distance_transform_edt

    from .body_maps import rasterize

    me = ob.data
    uv, ls, lt, lv = _loop_arrays(me)
    tri_uv, tri_face = [], []
    for f in range(len(ls)):
        for t in range(1, lt[f] - 1):
            tri_uv.append([uv[ls[f]], uv[ls[f] + t], uv[ls[f] + t + 1]])
            tri_face.append(f)
    tri_uv = np.array(tri_uv)
    tri_face = np.array(tri_face)
    tid, _ = rasterize(tri_uv, size, conservative=True)
    lab = np.full(tid.shape, -1, np.int64)
    m = tid >= 0
    lab[m] = isl[tri_face[tid[m]]]
    best = np.inf
    for i in np.unique(lab[m]):
        mi = lab == i
        d = distance_transform_edt(~mi)
        other = m & ~mi
        if other.any():
            best = min(best, float(d[other].min()))
    return best


def draw_uv_layout(ob, path, isl=None, isl_names=None, size=1024):
    """Dessin PIL de la disposition UV (uv.export_layout ne fonctionne pas en arrière-plan)."""
    from PIL import Image, ImageDraw

    me = ob.data
    uv, ls, lt, lv = _loop_arrays(me)
    img = Image.new("RGB", (size, size), (24, 24, 28))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(3)
    pal = {}
    for f in range(len(ls)):
        key = isl_names[isl[f]].split("_")[0] if isl is not None else "x"
        if key not in pal:
            pal[key] = tuple(int(c) for c in rng.integers(70, 210, 3))
        pts = [(float(u * size), float((1 - v) * size)) for u, v in uv[ls[f]:ls[f] + lt[f]]]
        d.polygon(pts, fill=pal[key], outline=(225, 225, 225))
    img.save(path)
    return path
