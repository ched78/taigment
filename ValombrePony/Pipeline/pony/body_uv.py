"""UV du corps (UV0 unique) : îlots anatomiques, coutures procédurales, dépliage ABF, densité, rangement.

Îlots : pelage (tronc + encolure + haut des membres + queue), tête (×1,5 de densité), oreilles (conque /
dos), bas des membres (×4), parois et soles des sabots (×4), poches intérieures (sac conjonctival, conduits
des naseaux, cavité buccale ; ×0,5). Coutures : ligne médiane ventrale (gorge → poitrail → ventre → entre
les postérieurs → dessous de la queue), faces internes des membres, couronne des sabots, sous la ganache,
derrière les oreilles, talons. [I]
"""
from __future__ import annotations

import math

import bmesh
import bpy
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from .body_sdf_lib import unit

REGION_SCALE = {"head": 1.5, "ear": 1.5, "pocket": 0.45}


# ----------------------------------------------------------------------------------------------
# Classification des faces en îlots
# ----------------------------------------------------------------------------------------------
def classify_faces(bm, sdf, pocket_faces, leg_cut=(0.66, 0.68)):
    """Renvoie une liste de noms d'îlot (une par face) et le dictionnaire des repères utiles."""
    bm.faces.ensure_lookup_table()
    C = np.array([f.calc_center_median()[:] for f in bm.faces])
    N = np.array([f.normal[:] for f in bm.faces])
    nF = len(C)
    lab = np.array(["body"] * nF, dtype=object)
    rig = sdf.rig
    feats = sdf.features
    H = rig.jh("head")
    a = unit(rig.jt("head") - H)
    s = (C - H) @ a
    head = (s > -0.055) & (C[:, 2] > 1.0)
    lab[head] = "head"
    # oreilles : conque (intérieur) / dos (indépendant du masque « tête » : la pointe est derrière la nuque)
    for side in "lr":
        ea = feats[f"ear_{side}"]
        D = C - ea.B
        t = D @ ea.e
        rad = np.linalg.norm(D - np.clip(t, 0, ea.length)[:, None] * ea.e, axis=1)
        ear = (t > 0.010) & (rad < 0.05) & (C[:, 2] > 1.3)
        cav = sdf.region_groups[f"ear_{side}"].nodes[1][1] if len(sdf.region_groups[f"ear_{side}"].nodes) > 1 \
            else None
        if cav is not None:
            dc = cav.eval(C.astype(np.float32))
            inner = ear & (np.abs(dc) < 0.0025) & ((N @ ea.f) > -0.2)
        else:
            inner = np.zeros(nF, bool)
        lab[ear & ~inner] = f"ear_out_{side}"
        lab[inner] = f"ear_in_{side}"
    # sabots (paroi / sole) puis bas des membres
    for key in ("fl", "fr", "hl", "hr"):
        hg = sdf.region_groups[f"hoof_{key}"]
        dh = hg.eval(C.astype(np.float32))
        hf = feats[f"hoof_{key}"]
        hoof = (dh < 0.0018) & (C[:, 2] < hf.coronet_toe + 0.006) & (np.linalg.norm(C[:, :2] - hf.O[:2], axis=1) < 0.12)
        sole = hoof & (N[:, 2] < -0.6) & (C[:, 2] < 0.006)
        lab[hoof & ~sole] = f"hoofwall_{key}"
        lab[sole] = f"sole_{key}"
    for key, sx, front in (("fl", -1, True), ("fr", 1, True), ("hl", -1, False), ("hr", 1, False)):
        zc = leg_cut[0] if front else leg_cut[1]
        sel = (C[:, 2] < zc) & (np.sign(C[:, 0]) == sx) & ((C[:, 1] > 0.0) == front) & (lab == "body")
        lab[sel] = f"leg_{key}"
    for name, fs in pocket_faces.items():
        lab[list(fs)] = f"pocket_{name}"
    return lab


def _vertex_graph(bm, allowed_edge=None, cost=None):
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    E = np.array([[e.verts[0].index, e.verts[1].index] for e in bm.edges])
    co = np.array([v.co[:] for v in bm.verts])
    L = np.linalg.norm(co[E[:, 0]] - co[E[:, 1]], axis=1)
    w = L * (1.0 if cost is None else cost)
    if allowed_edge is not None:
        w = np.where(allowed_edge, w, w * 1e4 + 10.0)
    n = len(co)
    G = coo_matrix((np.r_[w, w], (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n)).tocsr()
    return G, E, co


def shortest_path_edges(G, E, a, b):
    _, pred = dijkstra(G, indices=a, return_predecessors=True)
    lookup = {(min(p, q), max(p, q)): i for i, (p, q) in enumerate(E)}
    out = []
    v = b
    guard = 0
    while v != a and v >= 0 and guard < 100000:
        u = pred[v]
        if u < 0:
            break
        out.append(lookup[(min(u, v), max(u, v))])
        v = u
        guard += 1
    return out


def compute_seams(bm, sdf, lab):
    """Coutures = frontières d'îlots + coupes internes (chemins de Dijkstra)."""
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    seam = np.zeros(len(bm.edges), bool)
    edge_regions = []
    for i, e in enumerate(bm.edges):
        fl = [lab[f.index] for f in e.link_faces]
        edge_regions.append(fl)
        if len(set(fl)) > 1:
            seam[i] = True
    co = np.array([v.co[:] for v in bm.verts])
    vert_regions = [set(lab[f.index] for f in v.link_faces) for v in bm.verts]
    feats = sdf.features
    rig = sdf.rig
    Ev = np.array([[e.verts[0].index, e.verts[1].index] for e in bm.edges])
    mid = 0.5 * (co[Ev[:, 0]] + co[Ev[:, 1]])
    nrm = np.array([v.normal[:] for v in bm.verts])
    nm = 0.5 * (nrm[Ev[:, 0]] + nrm[Ev[:, 1]])

    def region_edges(names):
        names = set(names)
        return np.array([all(r in names for r in rr) for rr in edge_regions])

    def nearest_in(names, p, extra=None):
        idx = [i for i, rr in enumerate(vert_regions) if rr & set(names)]
        if extra is not None:
            idx = [i for i in idx if extra(i)]
        idx = np.array(idx)
        d = np.linalg.norm(co[idx] - np.asarray(p), axis=1)
        return int(idx[np.argmin(d)])

    def cut(names, a_pt, b_pt, cost, a_extra=None, b_extra=None):
        allowed = region_edges(names)
        G, E, _ = _vertex_graph(bm, allowed, cost)
        a = nearest_in(names, a_pt, a_extra)
        b = nearest_in(names, b_pt, b_extra)
        path = shortest_path_edges(G, E, a, b)
        seam[path] = True
        return path

    on_border = lambda name: (lambda i: len(vert_regions[i]) > 1 and name in vert_regions[i])
    # --- pelage : ligne médiane ventrale gorge → queue, coût faible près de x = 0 et normales vers le bas
    cost_ventral = 1.0 + 40.0 * np.abs(mid[:, 0]) + 3.0 * np.clip(nm[:, 2] + 0.2, 0, 2)
    H = rig.jh("head")
    throat = H + np.array([0.0, -0.10, -0.12])
    chest = np.array([0.0, 0.30, 0.66])
    groin = np.array([0.0, -0.40, 0.75])
    under_tail = rig.jh("tail_01") + np.array([0.0, 0.0, -0.10])
    tail_tip = rig.jt("tail_04")
    cut(["body"], throat, chest, cost_ventral, a_extra=on_border("body"))
    cut(["body"], chest, groin, cost_ventral)
    cut(["body"], groin, under_tail, cost_ventral)
    cost_tail = 1.0 + 40.0 * np.abs(mid[:, 0]) + 3.0 * np.clip(nm[:, 1] * -1 + nm[:, 2] + 0.5, 0, 3)
    cut(["body"], under_tail, tail_tip, cost_tail)
    # --- faces internes des membres (du cercle de coupe vers la ligne ventrale)
    for key, sx, front in (("fl", -1, True), ("fr", 1, True), ("hl", -1, False), ("hr", 1, False)):
        medial = 1.0 + 4.0 * np.clip(nm[:, 0] * -sx + 1.0, 0, 2)  # préfère les normales vers la ligne médiane
        leg_top = np.array([sx * 0.10, 0.42 if front else -0.60, 0.67])
        target = chest + np.array([0, 0.02, 0.05]) if front else groin
        cut(["body"], leg_top, target, medial, a_extra=on_border(f"leg_{key}"))
        # bas du membre : ligne arrière-médiale du cercle de coupe à la couronne
        back_med = 1.0 + 3.0 * np.clip(nm[:, 1] + 1.0, 0, 2) + 3.0 * np.clip(nm[:, 0] * sx + 1.0, 0, 2) * 0.5
        y0 = 0.40 if front else -0.66
        cut([f"leg_{key}"], np.array([sx * 0.10, y0, 0.66]), np.array([sx * 0.11, y0, 0.06]), back_med,
            a_extra=on_border(f"leg_{key}"), b_extra=on_border(f"leg_{key}"))
        # paroi du sabot : couture aux talons
        hf = feats[f"hoof_{key}"]
        heel = hf.O - hf.fwd * hf.Lb
        cut([f"hoofwall_{key}"], heel + np.array([0, 0, hf.coronet_heel]), heel + np.array([0, 0, 0.002]),
            None, a_extra=on_border(f"hoofwall_{key}"), b_extra=on_border(f"hoofwall_{key}"))
    # --- tête : sous la ganache (gorge → menton → lèvre inférieure) et derrière les oreilles
    a_h = unit(rig.jt("head") - H)
    d_h = unit(np.array([0.0, -a_h[2], a_h[1]]))
    hp = lambda s, d: H + s * a_h + d * d_h
    # tête coupée en deux moitiés (gauche / droite) le long des lignes médianes ventrale et dorsale
    cost_mid = 1.0 + 80.0 * np.abs(mid[:, 0])
    mf = feats["mouth"]
    cut(["head"], hp(-0.05, -0.08), hp(0.44, -0.095), cost_mid, a_extra=on_border("head"))
    chin = hp(0.44, -0.095)
    lip_lo = mf.O + mf.am * mf.A_s * 0.95 - mf.nm * 0.004
    lip_up = mf.O + mf.am * mf.A_s * 0.95 + mf.nm * 0.004
    cut(["head"], chin, lip_lo, cost_mid, b_extra=lambda i: len(vert_regions[i]) > 1)
    cut(["head"], lip_up, hp(-0.06, 0.06), cost_mid, a_extra=lambda i: len(vert_regions[i]) > 1,
        b_extra=on_border("head"))
    for side in "lr":
        ea = feats[f"ear_{side}"]
        back = 1.0 + 3.0 * np.clip((nm @ (-ea.f)) * -1 + 1.0, 0, 2)
        cut(["head"], ea.B - 0.02 * ea.f, hp(-0.06, 0.03), back,
            a_extra=lambda i, s=side: any(r.startswith(f"ear_") and r.endswith(side) for r in vert_regions[i]),
            b_extra=on_border("head"))
        # dos de l'oreille : de la base à la pointe (le long de l'arête arrière)
        cut([f"ear_out_{side}"], ea.B - 0.015 * ea.f + 0.01 * ea.e, ea.B + ea.e * ea.length * 0.97, back,
            a_extra=on_border(f"ear_out_{side}"), b_extra=on_border(f"ear_out_{side}"))
    me_seam = seam
    for i, e in enumerate(bm.edges):
        e.seam = bool(me_seam[i])
    return seam


# ----------------------------------------------------------------------------------------------
# Dépliage, mise à l'échelle par îlot, rangement
# ----------------------------------------------------------------------------------------------
def unwrap(ob, lab, margin_px=10, size=2048):
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.view_layer.objects:
        o.select_set(o is ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True, correct_aspect=True, margin=0.0)
    bpy.ops.uv.average_islands_scale()
    bpy.ops.object.mode_set(mode="OBJECT")
    # mise à l'échelle par îlot (densité de texels relative)
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()
    islands = uv_islands(bm, uvl)
    for isl in islands:
        names = {lab[f.index] for f in isl}
        name = max(names, key=lambda n: sum(1 for f in isl if lab[f.index] == n))
        sc = 1.0
        if name.startswith("head"):
            sc = REGION_SCALE["head"]
        elif name.startswith("ear"):
            sc = REGION_SCALE["ear"]
        elif name.startswith("pocket"):
            sc = REGION_SCALE["pocket"]
        if sc != 1.0:
            uvs = np.array([l[uvl].uv[:] for f in isl for l in f.loops])
            c = uvs.mean(0)
            for f in isl:
                for l in f.loops:
                    l[uvl].uv = c + (np.array(l[uvl].uv[:]) - c) * sc
    bm.to_mesh(me)
    bm.free()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    margin = margin_px / size
    bpy.ops.uv.pack_islands(rotate=True, rotate_method="ANY", scale=True, margin_method="FRACTION",
                            margin=margin, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    return len(islands)


def uv_islands(bm, uvl):
    """Îlots UV (faces connectées par des arêtes de même UV)."""
    parent = list(range(len(bm.faces)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for e in bm.edges:
        if e.seam or len(e.link_faces) != 2:
            continue
        f1, f2 = e.link_faces
        ok = True
        for v in e.verts:
            u1 = [l[uvl].uv for l in f1.loops if l.vert == v][0]
            u2 = [l[uvl].uv for l in f2.loops if l.vert == v][0]
            if (u1 - u2).length > 1e-6:
                ok = False
                break
        if ok:
            parent[find(f1.index)] = find(f2.index)
    groups = {}
    for f in bm.faces:
        groups.setdefault(find(f.index), []).append(f)
    return list(groups.values())


def uv_metrics(ob, lab, size=2048):
    """Distorsion : rapport d'aire normalisé par îlot (densité cible) et étirement (σ1/σ2)."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.faces.ensure_lookup_table()
    A3, A2, ST, LB = [], [], [], []
    for f in bm.faces:
        P = np.array([l.vert.co[:] for l in f.loops])
        U = np.array([l[uvl].uv[:] for l in f.loops])
        e1, e2 = P[1] - P[0], P[2] - P[0]
        n = np.cross(e1, e2)
        a3 = 0.5 * np.linalg.norm(n)
        if a3 < 1e-12:
            continue
        x = e1 / np.linalg.norm(e1)
        y = np.cross(n / np.linalg.norm(n), x)
        Pm = np.array([[e1 @ x, e2 @ x], [e1 @ y, e2 @ y]])
        Um = np.array([U[1] - U[0], U[2] - U[0]]).T
        try:
            J = Um @ np.linalg.inv(Pm)
        except np.linalg.LinAlgError:
            continue
        sv = np.linalg.svd(J, compute_uv=False)
        A3.append(a3)
        A2.append(abs(np.linalg.det(J)) * a3)
        ST.append(sv[0] / max(sv[1], 1e-12))
        LB.append(f.index)
    bm.free()
    A3, A2, ST = np.array(A3), np.array(A2), np.array(ST)
    dens = np.sqrt(A2 / A3) * size          # texels par mètre
    return dict(texel_density_px_per_m_median=float(np.median(dens)),
                density_ratio_p5_p95=(float(np.percentile(dens / np.median(dens), 5)),
                                      float(np.percentile(dens / np.median(dens), 95))),
                stretch_median=float(np.median(ST)), stretch_p95=float(np.percentile(ST, 95)),
                stretch_area_weighted_mean=float((ST * A3).sum() / A3.sum()),
                uv_coverage=float(A2.sum()))


def draw_uv_layout(ob, path, lab=None, size=1024):
    """Dessin PIL de la disposition UV (uv.export_layout ne fonctionne pas en arrière-plan)."""
    from PIL import Image, ImageDraw

    me = ob.data
    uv = np.zeros(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    ls = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.zeros(len(me.polygons), np.int32)
    me.polygons.foreach_get("loop_total", lt)
    img = Image.new("RGB", (size, size), (24, 24, 28))
    d = ImageDraw.Draw(img)
    palette = {}
    rng = np.random.default_rng(3)
    for i, (s, t) in enumerate(zip(ls, lt)):
        key = (lab[i] if lab is not None else "x").split("_")[0]
        if key not in palette:
            palette[key] = tuple(int(c) for c in rng.integers(70, 200, 3))
        pts = [(float(u * size), float((1 - v) * size)) for u, v in uv[s:s + t]]
        d.polygon(pts, fill=palette[key], outline=(230, 230, 230))
    img.save(path)
    return path
