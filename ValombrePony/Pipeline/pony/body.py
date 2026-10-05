"""Maillages du corps : haute définition (marching cubes du SDF) et basse définition « jeu »
(QuadriFlow + subdivision régionale + projection + ouvertures : yeux, naseaux, bouche).

Chaîne basse définition (cf. rapport) :
  SDF variante « fermée » → marching cubes 7 mm → remove_doubles(1e-4) + dissolve_degenerate(3e-4)
  → QuadriFlow (≈ 10,5 k quads, symétrie X ; échec silencieux vérifié) → subdivision ×2 (tête, bas des
  membres) puis ×2 (yeux, naseaux, lèvres, oreilles) → projection sur le SDF fermé → découpes et poches
  (sac conjonctival, conduits des naseaux, cavité buccale toit/plancher) → projection sur le SDF complet
  → relaxation tangentielle → contrôles (variété, 1 composante, normales).
"""
from __future__ import annotations

import math
import time

import bmesh
import bpy
import numpy as np

from . import body_sdf
from .body_sdf_lib import F32, ray_surface_batch, unit

LOG = print


# ==============================================================================================
# Utilitaires numpy <-> Blender
# ==============================================================================================
def make_active(ob):
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)


def mesh_from_numpy(name, V, F, collection=None):
    V = np.asarray(V, np.float32)
    F = np.asarray(F, np.int32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.ravel())
    n = F.shape[1]
    me.loops.add(F.size)
    me.loops.foreach_set("vertex_index", F.ravel())
    me.polygons.add(len(F))
    me.polygons.foreach_set("loop_start", np.arange(0, F.size, n, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate()
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def bm_coords(bm):
    bm.verts.ensure_lookup_table()
    return np.array([v.co[:] for v in bm.verts], np.float64)


def bm_set_coords(bm, co, idx=None):
    bm.verts.ensure_lookup_table()
    if idx is None:
        idx = range(len(bm.verts))
    for i, p in zip(idx, co):
        bm.verts[i].co = p


def face_centers(bm):
    bm.faces.ensure_lookup_table()
    return np.array([f.calc_center_median()[:] for f in bm.faces], np.float64)


def mesh_stats(me):
    nl = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", nl)
    tris = int((nl - 2).sum())
    return dict(verts=len(me.vertices), faces=len(me.polygons), tris=tris,
                quads=int((nl == 4).sum()), triangles_faces=int((nl == 3).sum()), ngons=int((nl > 4).sum()))


def topology_check(bm):
    """Variété, bords, composantes connexes."""
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    bd = sum(1 for e in bm.edges if e.is_boundary)
    nmv = sum(1 for v in bm.verts if not v.is_manifold)
    bm.verts.ensure_lookup_table()
    seen = np.zeros(len(bm.verts), bool)
    comps = 0
    for v0 in bm.verts:
        if seen[v0.index]:
            continue
        comps += 1
        stack = [v0]
        seen[v0.index] = True
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                o = e.other_vert(v)
                if not seen[o.index]:
                    seen[o.index] = True
                    stack.append(o)
    V, E, Fn = len(bm.verts), len(bm.edges), len(bm.faces)
    return dict(non_manifold_edges=nm, boundary_edges=bd, non_manifold_verts=nmv, components=comps,
                euler=V - E + Fn)


# ==============================================================================================
# Haute définition
# ==============================================================================================
def build_high(sdf_full, h=0.003):
    V, F = body_sdf.mesh_narrowband(sdf_full, h=h, log=LOG)
    return V, F


# ==============================================================================================
# Basse définition : QuadriFlow
# ==============================================================================================
def quadriflow(V, F, target_faces=11000, seed=0):
    ob = mesh_from_numpy("QF_tmp", V, F)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=3e-4)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bm.to_mesh(ob.data)
    bm.free()
    n0 = len(ob.data.polygons)
    ob.data.use_mirror_x = True   # indispensable : sinon use_mesh_symmetry n'a aucun effet (mesuré)
    make_active(ob)
    t0 = time.perf_counter()
    bpy.ops.object.quadriflow_remesh(target_faces=target_faces, mode="FACES", use_mesh_symmetry=True,
                                     use_preserve_sharp=False, use_preserve_boundary=False,
                                     preserve_attributes=False, smooth_normals=False, seed=seed)
    n1 = len(ob.data.polygons)
    if n1 == n0:
        raise RuntimeError("QuadriFlow a échoué silencieusement (nombre de faces inchangé)")
    me = ob.data
    # la symétrie de QuadriFlow laisse les deux moitiés non soudées sur le plan x = 0 : on les soude
    bm = bmesh.new()
    bm.from_mesh(me)
    mid = [v for v in bm.verts if abs(v.co.x) < 1e-4]
    for v in mid:
        v.co.x = 0.0
    bmesh.ops.remove_doubles(bm, verts=mid, dist=1e-5)
    chk = topology_check(bm)
    bm.to_mesh(me)
    bm.free()
    if chk["boundary_edges"] or chk["non_manifold_edges"] or chk["components"] != 1:
        raise RuntimeError(f"QuadriFlow : maillage non fermé après soudure {chk}")
    st = mesh_stats(me)
    LOG(f"[low] QuadriFlow {n0} -> {n1} faces ({st}) en {time.perf_counter() - t0:.1f}s")
    co = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    nl = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", nl)
    fl = np.zeros(int(nl.sum()), np.int32)
    me.polygons.foreach_get("vertices", fl)
    faces = np.split(fl, np.cumsum(nl)[:-1])
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.meshes.remove(me)
    return co.reshape(-1, 3).astype(np.float64), faces


def bm_from_faces(V, faces):
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in V]
    bm.verts.ensure_lookup_table()
    for f in faces:
        try:
            bm.faces.new([vs[i] for i in f])
        except ValueError:
            pass
    bm.normal_update()
    return bm


# ==============================================================================================
# Subdivision régionale + projection
# ==============================================================================================
def project_bm(bm, sdf, idx=None, iters=4, max_step=0.015, constrain_normal=False):
    co = bm_coords(bm)
    if idx is None:
        idx = np.arange(len(co))
    idx = np.asarray(idx)
    if len(idx) == 0:
        return
    P = co[idx]
    if constrain_normal:
        bm.normal_update()
        bm.verts.ensure_lookup_table()
        N = np.array([bm.verts[i].normal[:] for i in idx])
    for _ in range(iters):
        d = sdf(P)
        g = sdf.gradient(P)
        gg = np.maximum((g * g).sum(1), 1e-8)
        step = (d / gg)[:, None] * g
        if constrain_normal:
            # ne garde que la composante le long de la normale du sommet (évite de sauter sur l'autre lèvre)
            gn = g / np.sqrt(gg)[:, None]
            ok = (gn * N).sum(1) > 0.3
            step = np.where(ok[:, None], (step * N).sum(1)[:, None] * N, 0.0)
        n = np.linalg.norm(step, axis=1)
        s = np.minimum(1.0, max_step / np.maximum(n, 1e-12))
        P = P - step * s[:, None]
    bm_set_coords(bm, P, idx)


def subdivide_faces(bm, faces):
    """Subdivise (×4) un ensemble de faces ; les faces voisines sont recousues (triangles/quads)."""
    faces = [f for f in faces if f.is_valid]
    if not faces:
        return
    edges = set()
    for f in faces:
        for e in f.edges:
            edges.add(e)
    bmesh.ops.subdivide_edges(bm, edges=list(edges), cuts=1, use_grid_fill=True, use_single_edge=True,
                              use_only_quads=False)
    ngons = [f for f in bm.faces if len(f.verts) > 4]
    if ngons:
        bmesh.ops.triangulate(bm, faces=ngons, quad_method="BEAUTY", ngon_method="BEAUTY")


def tangential_relax(bm, sdf, idx, iters=3, lam=0.5, fixed=None):
    """Lissage laplacien tangentiel (répartit les sommets) puis re-projection."""
    idx = np.asarray(idx)
    if len(idx) == 0:
        return
    fixed = set() if fixed is None else set(fixed)
    bm.verts.ensure_lookup_table()
    idx = np.array([i for i in idx if i not in fixed])
    nbrs = [[e.other_vert(bm.verts[i]).index for e in bm.verts[i].link_edges] for i in idx]
    for _ in range(iters):
        co = bm_coords(bm)
        bm.normal_update()
        N = np.array([bm.verts[i].normal[:] for i in idx])
        avg = np.array([co[nb].mean(0) for nb in nbrs])
        dlt = avg - co[idx]
        dlt -= (dlt * N).sum(1)[:, None] * N
        bm_set_coords(bm, co[idx] + lam * dlt, idx)
        project_bm(bm, sdf, idx, iters=2)


# ==============================================================================================
# Ouvertures (chirurgie topologique)
# ==============================================================================================
def _face_adjacency_components(faces_sel):
    sel = set(faces_sel)
    comps = []
    seen = set()
    for f0 in faces_sel:
        if f0 in seen:
            continue
        comp = []
        stack = [f0]
        seen.add(f0)
        while stack:
            f = stack.pop()
            comp.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g in sel and g not in seen:
                        seen.add(g)
                        stack.append(g)
        comps.append(comp)
    return comps


def make_disk_selection(bm, mask):
    """Sélection de faces (masque booléen) → plus grande composante, trous comblés (disque)."""
    bm.faces.ensure_lookup_table()
    faces = [bm.faces[i] for i in np.flatnonzero(mask)]
    if not faces:
        return []
    comps = _face_adjacency_components(faces)
    sel = set(max(comps, key=len))
    # composantes du complémentaire au voisinage : on garde la plus grande (l'extérieur)
    region = set()
    for f in sel:
        for v in f.verts:
            for g in v.link_faces:
                region.add(g)
    for _ in range(3):
        grow = set()
        for f in region:
            for v in f.verts:
                for g in v.link_faces:
                    grow.add(g)
        region |= grow
    comp_out = [f for f in region if f not in sel]
    if comp_out:
        cc = _face_adjacency_components(comp_out)
        # composantes ne touchant pas le bord de la région = trous intérieurs
        border = set()
        for f in region:
            for e in f.edges:
                for g in e.link_faces:
                    if g not in region:
                        border.add(f)
        for c in cc:
            if not any(f in border for f in c):
                sel |= set(c)
    return list(sel)


def boundary_loop(bm, near=None):
    """Boucle ordonnée (liste de BMVert) formée par les arêtes de bord."""
    edges = [e for e in bm.edges if e.is_boundary]
    if near is not None:
        edges = [e for e in edges if near(np.array(e.verts[0].co))]
    if not edges:
        return []
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    start = edges[0].verts[0]
    loop = [start]
    prev, cur = None, start
    while True:
        nxt = [v for v in adj[cur] if v is not prev]
        if not nxt:
            break
        nv = nxt[0]
        if nv is start:
            break
        loop.append(nv)
        prev, cur = cur, nv
        if len(loop) > len(adj) + 2:
            raise RuntimeError("boucle de bord non simple")
    return loop


def _resample_closed(T, n, offset=0.0):
    """n points régulièrement espacés (abscisse curviligne) sur une polyligne fermée T (m,3)."""
    Tc = np.vstack([T, T[:1]])
    seg = np.linalg.norm(np.diff(Tc, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    L = cum[-1]
    s = (offset + np.arange(n) / n) % 1.0 * L
    out = np.empty((n, 3))
    for k in range(3):
        out[:, k] = np.interp(s, cum, Tc[:, k])
    return out


def snap_loop_to_curve(loop_co, T):
    """Associe les sommets d'une boucle (ordre conservé) à une courbe fermée cible (même sens, décalage optimal)."""
    n = len(loop_co)
    Tc = np.vstack([T, T[:1]])
    seg = np.linalg.norm(np.diff(Tc, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    L = cum[-1]
    # paramètre du point le plus proche pour chaque sommet
    dens = _resample_closed(T, 2048)
    from scipy.spatial import cKDTree

    _, j = cKDTree(dens).query(loop_co)
    u = j / 2048.0
    du = np.diff(np.unwrap(u * 2 * np.pi)) / (2 * np.pi)
    if np.median(du) < 0:
        T = T[::-1]
        dens = dens[::-1]
        u = 1.0 - u
    target = np.arange(n) / n
    off = np.angle(np.exp(1j * 2 * np.pi * (u - target)).mean()) / (2 * np.pi)
    return _resample_closed(T, n, off % 1.0)


def _surface_point(sdf, origin, direction, t_max=0.2):
    from .body_sdf_lib import ray_surface

    return ray_surface(lambda P: sdf(P), origin, direction, t_max=t_max, n=400)


class Surgery:
    """Ouvertures sur le maillage basse définition (bm), à partir des descripteurs du SDF."""

    def __init__(self, bm, sdf_closed, sdf_full, feats):
        self.bm = bm
        self.sc = sdf_closed
        self.sf = sdf_full
        self.feats = feats
        self.pocket_verts = set()     # sommets intérieurs (non projetés sur la peau)
        self.margin_verts = set()     # sommets de bord d'ouverture (positions analytiques)
        self.groups = {}              # nom -> liste d'indices de sommets (pour les poids / régions)

    # -------------------------------------------------------------- générique
    def _cut(self, mask, target_curve, name):
        bm = self.bm
        sel = make_disk_selection(bm, mask)
        if len(sel) < 2:
            raise RuntimeError(f"ouverture {name} : sélection vide")
        bmesh.ops.delete(bm, geom=sel, context="FACES")
        loop = boundary_loop(bm)
        co = np.array([v.co[:] for v in loop])
        snapped = snap_loop_to_curve(co, target_curve)
        for v, p in zip(loop, snapped):
            v.co = p
        return loop

    def _relax_around(self, loop, rings=2, sdf=None):
        bm = self.bm
        ring = set(loop)
        allv = set()
        for _ in range(rings):
            nxt = set()
            for v in ring:
                for e in v.link_edges:
                    o = e.other_vert(v)
                    if o not in allv and o not in loop:
                        nxt.add(o)
            allv |= nxt
            ring = nxt
        bm.verts.index_update()
        idx = [v.index for v in allv if v.index not in self.pocket_verts]
        tangential_relax(bm, sdf or self.sc, idx, iters=4, lam=0.45)

    @staticmethod
    def _face(bm, vs):
        try:
            return bm.faces.new(vs)
        except ValueError:
            return None

    # -------------------------------------------------------------- yeux
    def eye(self, side):
        ef = self.feats[f"eye_{side}"]
        bm = self.bm
        bm.faces.ensure_lookup_table()
        C = face_centers(bm)
        r = np.linalg.norm(C - ef.C, axis=1)
        mask = (ef.fissure_sdf(C) < 0.0) & (r < ef.R_out + 0.012)
        T = ef.margin_curve(n=96, radius=ef.R_out)
        loop = self._cut(mask, T, f"eye_{side}")
        n = len(loop)
        # bord : on recale exactement sur la sphère extérieure
        D = np.array([(np.array(v.co) - ef.C) for v in loop])
        W = D / np.linalg.norm(D, axis=1, keepdims=True)
        for v, w in zip(loop, W):
            v.co = ef.C + ef.R_out * w
        self.margin_verts |= {v for v in loop}
        # anneau 1 : bord libre intérieur de la paupière (R_in) ; anneaux 2.. : sac conjonctival vers −g
        rings = [loop]
        dirs = [W]
        fr = [0.0, 0.28, 0.55, 0.80]
        for k, f in enumerate(fr):
            if k == 0:
                Wk = W
                rad = ef.R_in
            else:
                Wk = np.array([_slerp(w, -ef.g, f) for w in W])
                rad = ef.R_in
            vs = [bm.verts.new(ef.C + rad * w) for w in Wk]
            rings.append(vs)
        for k in range(len(rings) - 1):
            a, b = rings[k], rings[k + 1]
            for i in range(n):
                self._face(bm, [a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]])
        pole = bm.verts.new(ef.C - ef.R_in * ef.g)
        last = rings[-1]
        for i in range(n):
            self._face(bm, [last[i], last[(i + 1) % n], pole])
        newv = [v for rr in rings[1:] for v in rr] + [pole]
        bm.verts.index_update()
        self.pocket_verts |= {v.index for v in newv}
        self.groups[f"eye_sac_{side}"] = newv
        self.groups[f"eye_margin_{side}"] = list(loop)
        self.groups[f"eye_margin_inner_{side}"] = list(rings[1])
        self._relax_around(loop)
        LOG(f"[low] œil {side} : bord {n} sommets, sac {len(newv)} sommets")

    # -------------------------------------------------------------- naseaux
    def nostril(self, side):
        nf = self.feats[f"nostril_{side}"]
        bm = self.bm
        C = face_centers(bm)
        D = C - nf.Nc
        q1, q2, q3 = D @ nf.e1, D @ nf.e2, D @ nf.n_out
        mask = ((q1 / nf.a1) ** 2 + (q2 / nf.a2) ** 2 < 1.0) & (np.abs(q3) < 0.015)
        phi = np.linspace(0, 2 * np.pi, 128, endpoint=False)
        T0 = nf.Nc + nf.a1 * np.cos(phi)[:, None] * nf.e1 + nf.a2 * np.sin(phi)[:, None] * nf.e2
        T = self.sc.project(T0, iters=6)
        loop = self._cut(mask, T, f"nostril_{side}")
        n = len(loop)
        self.margin_verts |= set(loop)
        # angle de chaque sommet de bord dans le repère de l'ouverture
        L = np.array([v.co[:] for v in loop]) - nf.Nc
        ang = np.arctan2((L @ nf.e2) / nf.a2, (L @ nf.e1) / nf.a1)
        rings = [loop]
        for k in range(1, len(nf.ring_c)):
            c = nf.ring_c[k]
            nxt = nf.ring_c[min(k + 1, len(nf.ring_c) - 1)]
            prv = nf.ring_c[k - 1]
            axis = unit(nxt - prv) if k + 1 < len(nf.ring_c) else unit(c - prv)
            u1 = unit(nf.e1 - np.dot(nf.e1, axis) * axis)
            u2 = unit(np.cross(axis, u1))
            if np.dot(u2, nf.e2) < 0:
                u2 = -u2
            s = nf.ring_s[k]
            vs = [bm.verts.new(c + s * (nf.a1 * math.cos(a) * u1 + nf.a2 * math.sin(a) * u2)) for a in ang]
            rings.append(vs)
        for k in range(len(rings) - 1):
            a, b = rings[k], rings[k + 1]
            for i in range(n):
                self._face(bm, [a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]])
        end = bm.verts.new(nf.ring_c[-1] + 0.006 * unit(nf.ring_c[-1] - nf.ring_c[-2]))
        last = rings[-1]
        for i in range(n):
            self._face(bm, [last[i], last[(i + 1) % n], end])
        newv = [v for rr in rings[1:] for v in rr] + [end]
        bm.verts.index_update()
        self.pocket_verts |= {v.index for v in newv}
        self.groups[f"nostril_{side}"] = newv + list(loop)
        self._relax_around(loop)
        LOG(f"[low] naseau {side} : bord {n} sommets, conduit {len(newv)} sommets")

    # -------------------------------------------------------------- bouche
    def mouth(self):
        mf = self.feats["mouth"]
        bm = self.bm
        sc = self.sc
        # ligne des lèvres L(t) : surface du SDF fermé dans le plan buccal, depuis le centre de la fente
        ts = np.linspace(-2.6, 2.6, 521)

        def lip_points(tt, vv):
            tt = np.asarray(tt, float)
            vv = np.broadcast_to(np.asarray(vv, float), tt.shape)
            o = mf.O[None, :] + vv[:, None] * mf.nm[None, :]
            d = np.cos(tt)[:, None] * mf.am[None, :] * mf.A_s + np.sin(tt)[:, None] * mf.xh[None, :] * mf.A_x
            p, ok = ray_surface_batch(lambda P: sc(P), o, d, t_max=0.2, n=200)
            return p, ok

        pts, ok = lip_points(ts, 0.0)
        u0, x0, _ = mf.local(pts)
        rho = np.where(ok, np.sqrt((u0 / mf.A_s) ** 2 + (x0 / mf.A_x) ** 2), 9.0)
        inside = np.flatnonzero(rho < 1.0)
        i0, i1 = inside.min(), inside.max()
        t_lo, t_hi = ts[i0], ts[i1]
        # sélection : bande |v| < 3.5 mm le long de la ligne des lèvres, dans l'ellipse de la fente
        C = face_centers(bm)
        u, x, v = mf.local(C)
        rr = np.sqrt((u / mf.A_s) ** 2 + (x / mf.A_x) ** 2)
        band = 0.0036
        mask = (np.abs(v) < band) & (rr < 1.0) & (np.abs(sc(C)) < 0.01)
        sel = make_disk_selection(bm, mask)
        bmesh.ops.delete(bm, geom=sel, context="FACES")
        loop = boundary_loop(bm)
        Lc = np.array([vv.co[:] for vv in loop])
        lu, lx, lv = mf.local(Lc)
        az = np.arctan2(lx / mf.A_x, lu / mf.A_s)
        iL = int(np.argmin(az))
        iR = int(np.argmax(az))
        n = len(loop)
        # deux chemins : de iL à iR dans les deux sens ; celui de v moyen > 0 = lèvre supérieure
        def path(a, b, step):
            out = [a]
            i = a
            while i != b:
                i = (i + step) % n
                out.append(i)
            return out
        p1, p2 = path(iL, iR, 1), path(iL, iR, -1)
        if lv[p1[1:-1]].mean() < lv[p2[1:-1]].mean():
            p1, p2 = p2, p1
        up_idx, lo_idx = p1, p2
        tau = mf.tau

        def margin_curve(sign, m):
            tt = np.linspace(t_lo, t_hi, m)
            mid = 0.5 * (t_lo + t_hi)
            half = 0.5 * (t_hi - t_lo)
            taper = np.sqrt(np.clip(1.0 - ((tt - mid) / half) ** 6, 0.0, 1.0))
            p, _ = lip_points(tt, sign * tau * taper)
            return p

        Uc = margin_curve(+1, 200)
        Dc = margin_curve(-1, 200)

        def place(idx_list, curve):
            seg = np.linalg.norm(np.diff(curve, axis=0), axis=1)
            cum = np.concatenate([[0.0], np.cumsum(seg)])
            s = np.linspace(0, cum[-1], len(idx_list))
            for k in range(3):
                pass
            P = np.stack([np.interp(s, cum, curve[:, k]) for k in range(3)], 1)
            for i, p in zip(idx_list, P):
                loop[i].co = p

        place(up_idx, Uc)
        place(lo_idx, Dc)
        cmL, cmR = loop[iL], loop[iR]
        mf.commissure_l, mf.commissure_r = (np.array(cmL.co), np.array(cmR.co)) if cmL.co.x < 0 else (
            np.array(cmR.co), np.array(cmL.co))
        upper = [loop[i] for i in up_idx]
        lower = [loop[i] for i in lo_idx]
        self.margin_verts |= set(upper) | set(lower)
        # cavité : lentille (centre cav_c, demi-axes cav_r dans le repère am, xh, nm)
        r0, r1, r2 = mf.cav_r
        cc = mf.cav_c

        def lens(t, e):
            return cc + mf.am * r0 * math.cos(e) * math.cos(t) + mf.xh * r1 * math.cos(e) * math.sin(t) \
                + mf.nm * r2 * math.sin(e)

        def lens_az(p):
            d = p - cc
            return math.atan2((d @ mf.xh) / r1, (d @ mf.am) / r0)

        e_tau = math.asin(min(0.9, tau / r2))
        # entrée de la fente (sur la lentille) pour chaque sommet des deux chemins
        def entrance(verts, sign):
            out = []
            for k, vv in enumerate(verts):
                if k == 0 or k == len(verts) - 1:
                    out.append(None)
                    continue
                t = lens_az(np.array(vv.co))
                out.append(bm.verts.new(lens(t, sign * e_tau)))
            return out

        entU = entrance(upper, +1)
        entD = entrance(lower, -1)
        tL = lens_az(np.array(upper[0].co))
        tR = lens_az(np.array(upper[-1].co))
        EL = bm.verts.new(lens(tL, 0.0))
        ER = bm.verts.new(lens(tR, 0.0))
        entU[0], entU[-1] = EL, ER
        entD[0], entD[-1] = EL, ER
        # bandes lèvre -> entrée
        for path_v, ent, flip in ((upper, entU, False), (lower, entD, True)):
            for k in range(len(path_v) - 1):
                quad = [path_v[k], path_v[k + 1], ent[k + 1], ent[k]]
                if path_v[k] is cmL and k == 0:
                    pass
                self._face(bm, quad[::-1] if flip else quad)
        # couture arrière (partagée toit / plancher)
        if tR < tL:
            tR += 2 * math.pi
        span_back = 2 * math.pi - (tR - tL)
        seg_len = np.mean([np.linalg.norm(np.array(entU[i + 1].co) - np.array(entU[i].co)) for i in
                           range(len(entU) - 1)])
        m = max(6, int(span_back * 0.5 * (r0 + r1) / max(seg_len, 1e-3)))
        seam_t = tR + span_back * np.arange(1, m) / m
        seam = [bm.verts.new(lens(t, 0.0)) for t in seam_t]

        def cap(ring0, sign):
            """Anneaux successifs vers le pôle (toit sign=+1, plancher sign=-1) puis éventail."""
            az = [lens_az(np.array(v.co)) for v in ring0]
            el = []
            for v in ring0:
                d = np.array(v.co) - cc
                el.append(math.asin(max(-1, min(1, (d @ mf.nm) / r2))))
            rings = [ring0]
            for f in (0.30, 0.58, 0.82):
                vs = [bm.verts.new(lens(a, e + f * (sign * math.pi / 2 - e))) for a, e in zip(az, el)]
                rings.append(vs)
            nn = len(ring0)
            for k in range(len(rings) - 1):
                a, b = rings[k], rings[k + 1]
                for i in range(nn):
                    q = [a[i], a[(i + 1) % nn], b[(i + 1) % nn], b[i]]
                    self._face(bm, q if sign > 0 else q[::-1])
            pole = bm.verts.new(cc + sign * r2 * mf.nm)
            for i in range(nn):
                t3 = [rings[-1][i], rings[-1][(i + 1) % nn], pole]
                self._face(bm, t3 if sign > 0 else t3[::-1])
            return [v for rr in rings[1:] for v in rr] + [pole]

        roof0 = entU + seam
        floor0 = entD + seam
        roof = cap(roof0, +1)
        floor = cap(floor0, -1)
        newv = [v for v in entU[1:-1] + entD[1:-1]] + [EL, ER] + seam + roof + floor
        bm.verts.index_update()
        self.pocket_verts |= {v.index for v in newv}
        self.groups["mouth_roof"] = [v for v in entU[1:-1]] + roof
        self.groups["mouth_floor"] = [v for v in entD[1:-1]] + floor
        self.groups["mouth_seam"] = seam + [EL, ER]
        self.groups["lip_upper_margin"] = upper
        self.groups["lip_lower_margin"] = lower
        self._relax_around(upper + lower[1:-1])
        LOG(f"[low] bouche : lèvre sup {len(upper)} / inf {len(lower)} sommets, cavité {len(newv)} sommets")


def _slerp(a, b, t):
    a = unit(a)
    b = unit(b)
    d = np.clip(np.dot(a, b), -1.0, 1.0)
    om = math.acos(d)
    if om < 1e-6:
        return a
    if abs(om - math.pi) < 1e-3:
        # antipodaux : passer par un axe perpendiculaire quelconque
        perp = unit(np.cross(a, [0.0, 0.0, 1.0]) if abs(a[2]) < 0.9 else np.cross(a, [1.0, 0.0, 0.0]))
        b = unit(math.cos(math.pi - 1e-3) * a + math.sin(math.pi - 1e-3) * perp)
        om = math.acos(np.clip(np.dot(a, b), -1, 1))
    return (math.sin((1 - t) * om) * a + math.sin(t * om) * b) / math.sin(om)


# ==============================================================================================
# Chaîne complète basse définition
# ==============================================================================================
def build_low(sdf_closed, sdf_full, h_qf=0.007, target_faces=11000, log=print):
    global LOG
    LOG = log
    t0 = time.perf_counter()
    V, F = body_sdf.mesh_narrowband(sdf_closed, h=h_qf, log=log)
    Vq, faces = quadriflow(V, F, target_faces)
    bm = bm_from_faces(Vq, faces)
    project_bm(bm, sdf_closed, iters=3)
    feats = sdf_full.features
    H = np.array(sdf_full.rig.jh("head"))
    a = unit(sdf_full.rig.jt("head") - H)

    # --- niveau 1 : tête (en avant de la nuque) + bas des membres
    def lvl1(P):
        s = (P - H) @ a
        return (s > -0.010) & (P[:, 2] > 1.0) | (P[:, 2] < 0.40)

    C = face_centers(bm)
    bm.faces.ensure_lookup_table()
    sel1 = np.flatnonzero(lvl1(C))
    log(f"[low] subdivision niveau 1 : {len(sel1)} faces")
    subdivide_faces(bm, [bm.faces[i] for i in sel1])
    project_bm(bm, sdf_closed, iters=4)

    # --- niveau 2 : yeux, naseaux, lèvres, oreilles
    def lvl2(P):
        m = np.zeros(len(P), bool)
        for side in "lr":
            ef = feats[f"eye_{side}"]
            m |= np.linalg.norm(P - ef.C, axis=1) < ef.R_out + 0.012
            nf = feats[f"nostril_{side}"]
            m |= np.linalg.norm(P - nf.Nc, axis=1) < 0.027
            ea = feats[f"ear_{side}"]
            D = P - ea.B
            t = np.clip(D @ ea.e, -0.01, ea.length)
            m |= (np.linalg.norm(D - t[:, None] * ea.e, axis=1) < 0.040) & (D @ ea.e > -0.005)
        mf = feats["mouth"]
        u, x, v = mf.local(P)
        rr = np.sqrt((u / mf.A_s) ** 2 + (x / mf.A_x) ** 2)
        m |= (np.abs(v) < 0.016) & (rr < 1.10)
        return m

    C = face_centers(bm)
    bm.faces.ensure_lookup_table()
    sel2 = np.flatnonzero(lvl2(C))
    log(f"[low] subdivision niveau 2 : {len(sel2)} faces")
    subdivide_faces(bm, [bm.faces[i] for i in sel2])
    project_bm(bm, sdf_closed, iters=4)
    bm.verts.index_update()
    tangential_relax(bm, sdf_closed, np.arange(len(bm.verts)), iters=2, lam=0.3)
    log(f"[low] après subdivisions : {len(bm.verts)} sommets, {len(bm.faces)} faces")

    # --- ouvertures
    sg = Surgery(bm, sdf_closed, sdf_full, feats)
    for side in "lr":
        sg.eye(side)
    for side in "lr":
        sg.nostril(side)
    sg.mouth()
    bm.verts.index_update()
    # --- projection finale de la peau sur le SDF complet (oreilles creusées, etc.)
    margin_idx = {v.index for v in sg.margin_verts if v.is_valid}
    skin = np.array([i for i in range(len(bm.verts)) if i not in sg.pocket_verts and i not in margin_idx])
    project_bm(bm, sdf_full, skin, iters=5, constrain_normal=False)
    # relaxation tangentielle douce (sauf bords d'ouvertures)
    tangential_relax(bm, sdf_full, skin, iters=2, lam=0.35, fixed=margin_idx)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    chk = topology_check(bm)
    log(f"[low] maillage : {len(bm.verts)} sommets, {len(bm.faces)} faces, {chk}, {time.perf_counter() - t0:.1f}s")
    return bm, sg
