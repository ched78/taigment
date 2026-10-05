"""Outils géométriques des crins : croissance de guides (gravité + collisions avec le corps), cartes (rubans),
nappes de base, poids de peau, et écriture des pièces `.blend`.

Toutes les coordonnées sont en espace Blender (x droite du poney, y avant, z haut), mètres.
Un `PartBuilder` accumule sommets / quads / UV / attributs par sommet (paramètre racine→pointe `s`,
indice de racine, couche) puis produit le maillage, les poids et les normales.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import hair_texture as htex
from . import template

GRAVITY = np.array([0.0, 0.0, -1.0])
JOINTS = list(template.JOINT_NAMES)
JIDX = {n: i for i, n in enumerate(JOINTS)}
NJ = len(JOINTS)


def nrm(v):
    v = np.asarray(v, np.float64)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


def perp(v, axis):
    """Composante de v perpendiculaire à axis (normalisée)."""
    axis = nrm(axis)
    return nrm(v - axis * (v * axis).sum(-1, keepdims=True))


def smoothstep(e0, e1, x):
    t = np.clip((np.asarray(x, np.float64) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------------------------
# Croissance d'un guide
# ----------------------------------------------------------------------------------------------
def grow_guide(surf, root, dir0, length, nseg, offset_fn, bend=25.0, bend_fn=None, gravity=GRAVITY,
               steer_fn=None, iters=3):
    """Guide de mèche : chaîne inextensible qui part de `root` dans la direction `dir0`, se courbe vers la gravité
    (taux de courbure `bend` en rad/m, éventuellement fonction de s) et reste au-dessus de la surface d'au moins
    `offset_fn(s)` (s = 0…1 le long du guide). `steer_fn(s, p, d)` renvoie un vecteur ajouté à la direction.
    Renvoie (nseg+1, 3)."""
    seg = length / nseg
    P = [np.asarray(root, np.float64)]
    d = nrm(dir0)
    for k in range(1, nseg + 1):
        s = k / nseg
        b = bend_fn(s) if bend_fn is not None else bend
        d = nrm(d + gravity * b * seg)
        if steer_fn is not None:
            d = nrm(d + steer_fn(s, P[-1], d))
        p = P[-1] + d * seg
        off = offset_fn(s)
        for _ in range(iters):
            q, n, sd, _fi, _bc = surf.nearest(p)
            if sd >= off:
                break
            p = q + n * off
            p = P[-1] + nrm(p - P[-1]) * seg
        q, n, sd, _fi, _bc = surf.nearest(p)
        if sd < off * 0.98:
            p = q + n * off
        d = nrm(p - P[-1])
        P.append(p)
    return np.array(P)


def resample(P, n):
    """Rééchantillonne une polyligne en n points à pas constant."""
    P = np.asarray(P, np.float64)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.linspace(0.0, s[-1], n)
    return np.stack([np.interp(t, s, P[:, k]) for k in range(3)], 1)


def cut_at_length(P, L):
    """Tronque une polyligne à la longueur L (interpolée)."""
    P = np.asarray(P, np.float64)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    if L >= s[-1]:
        return P
    k = int(np.searchsorted(s, L))
    t = (L - s[k - 1]) / max(seg[k - 1], 1e-12)
    return np.vstack([P[:k], P[k - 1] + (P[k] - P[k - 1]) * t])


def polyline_length(P):
    return float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())


def tangents(P):
    T = np.gradient(P, axis=0)
    return nrm(T)


# ----------------------------------------------------------------------------------------------
# Accumulateur de maillage
# ----------------------------------------------------------------------------------------------
@dataclass
class PartBuilder:
    name: str
    V: list = field(default_factory=list)        # positions
    UV: list = field(default_factory=list)       # uv par sommet (pas de couture : chaque carte est un îlot)
    S: list = field(default_factory=list)        # paramètre racine (0) -> pointe (1)
    ROOT: list = field(default_factory=list)     # point racine associé (3,)
    TAG: list = field(default_factory=list)      # entier : couche / groupe (pour les poids)
    AUX: list = field(default_factory=list)      # flottant libre (ex. paramètre le long de la crête)
    FACING: list = field(default_factory=list)   # normale « de volume » (pour l'éclairage des cartes)
    F: list = field(default_factory=list)        # quads (indices)
    ROOTFLAG: list = field(default_factory=list)  # 1 si sommet de racine (peut pénétrer légèrement la peau)

    def add_vertex(self, p, uv, s, root, tag=0, aux=0.0, facing=(0, 0, 1), rootflag=0):
        self.V.append(np.asarray(p, np.float64))
        self.UV.append((float(uv[0]), float(uv[1])))
        self.S.append(float(s))
        self.ROOT.append(np.asarray(root, np.float64))
        self.TAG.append(int(tag))
        self.AUX.append(float(aux))
        self.FACING.append(nrm(np.asarray(facing, np.float64)))
        self.ROOTFLAG.append(int(rootflag))
        return len(self.V) - 1

    def add_grid(self, P, UVg, Sg, roots, facing, tag=0, aux=None, root_rows=(0,), flip=False, root_cols=()):
        """Grille (R lignes le long des mèches × C colonnes) : P (R,C,3), UVg (R,C,2), Sg (R,C), roots (C,3),
        facing (R,C,3). Les quads sont orientés pour que la normale géométrique suive `facing`."""
        R, C = P.shape[:2]
        idx = np.zeros((R, C), int)
        for r in range(R):
            for c in range(C):
                idx[r, c] = self.add_vertex(P[r, c], UVg[r, c], Sg[r, c], roots[c], tag,
                                            0.0 if aux is None else aux[c], facing[r, c],
                                            1 if (r in root_rows or c in root_cols) else 0)
        for r in range(R - 1):
            for c in range(C - 1):
                q = [idx[r, c], idx[r, c + 1], idx[r + 1, c + 1], idx[r + 1, c]]
                a, b, d = P[r, c], P[r, c + 1], P[r + 1, c]
                gn = np.cross(b - a, d - a)
                if gn @ facing[r, c] < 0:
                    q = q[::-1]
                self.F.append(q)
        return idx

    def add_ribbon(self, P, facing, width, uv_rect, across_dir=None, n_across=2, arch=0.0, tag=0, aux=0.0,
                   v_range=(0.0, 1.0), u_range=(0.0, 1.0), twist=None):
        """Carte le long d'une polyligne P (N,3). `facing` (N,3) : normale « de volume » ; la largeur est portée
        par `across_dir` (N,3) projeté perpendiculairement à la mèche (défaut : T × facing).
        `width` : scalaire ou (N,). `arch` : bombement relatif du centre (n_across ≥ 3).
        UV : u à travers la région, v de la racine (haut de la région) vers la pointe."""
        P = np.asarray(P, np.float64)
        N = len(P)
        T = tangents(P)
        Fc = nrm(np.asarray(facing, np.float64))
        if across_dir is None:
            Wd = nrm(np.cross(T, Fc))
        else:
            Wd = perp(np.asarray(across_dir, np.float64), T)
        if twist is not None:
            # rotation de la largeur autour de la mèche (angle en rad par point)
            ang = np.asarray(twist, np.float64)[:, None]
            Fp = nrm(np.cross(Wd, T))
            Wd = nrm(Wd * np.cos(ang) + Fp * np.sin(ang))
        Fp = nrm(np.cross(Wd, T))
        Fp = np.where(((Fp * Fc).sum(1) < 0)[:, None], -Fp, Fp)
        w = np.broadcast_to(np.asarray(width, np.float64), (N,))
        u0, v0, u1, v1 = uv_rect
        du = (u1 - u0)
        inset = 0.004 * du / 0.125
        ua = u0 + inset + (du - 2 * inset) * u_range[0]
        ub = u0 + inset + (du - 2 * inset) * u_range[1]
        G = np.zeros((N, n_across, 3))
        UVg = np.zeros((N, n_across, 2))
        Sg = np.zeros((N, n_across))
        FAC = np.zeros((N, n_across, 3))
        for j in range(n_across):
            a = j / (n_across - 1) - 0.5
            lift = arch * (0.25 - a * a) * 4.0 if n_across >= 3 else 0.0
            G[:, j] = P + Wd * (a * w)[:, None] + Fp * (lift * w * 0.25)[:, None]
            s = np.linspace(0.0, 1.0, N)
            vv = v1 - (v_range[0] + s * (v_range[1] - v_range[0])) * (v1 - v0)
            UVg[:, j, 0] = ua + (j / (n_across - 1)) * (ub - ua)
            UVg[:, j, 1] = vv
            Sg[:, j] = s
            FAC[:, j] = Fc
        roots = np.repeat(P[:1], n_across, 0)
        self.add_grid(G, UVg, Sg, roots, FAC, tag=tag, aux=[aux] * n_across)

    # -- sorties ---------------------------------------------------------------------------------
    def arrays(self):
        return dict(V=np.array(self.V), UV=np.array(self.UV), S=np.array(self.S), ROOT=np.array(self.ROOT),
                    TAG=np.array(self.TAG), AUX=np.array(self.AUX), FACING=np.array(self.FACING),
                    F=[list(map(int, f)) for f in self.F], ROOTFLAG=np.array(self.ROOTFLAG))

    @property
    def tri_count(self):
        return sum(len(f) - 2 for f in self.F)


# ----------------------------------------------------------------------------------------------
# Projection hors du corps
# ----------------------------------------------------------------------------------------------
def enforce_clearance(surf, V, S, ROOTFLAG, min_off=0.003, root_depth=0.002, root_band=0.0):
    """Repousse les sommets ordinaires (ROOTFLAG 0) à au moins `min_off` de la peau ; place les racines
    (ROOTFLAG 1) à `root_depth` sous la peau (pénétration contrôlée) ; laisse les sommets encastrés (ROOTFLAG 2,
    dessous des boutons/nattes) tels quels. Renvoie (V', stats)."""
    V = V.copy()
    pushed = 0
    for i in range(len(V)):
        if ROOTFLAG[i] == 2:
            continue
        q, n, sd, _fi, _bc = surf.nearest(V[i])
        if ROOTFLAG[i] == 1:
            V[i] = q - n * root_depth
            continue
        need = min_off if S[i] > root_band else min_off * 0.5
        if sd < need:
            V[i] = q + n * need
            pushed += 1
    return V, {"pushed": pushed}


def enforce_face_clearance(surf, V, F, ROOTFLAG, min_off=0.0015, iters=3):
    """Seconde passe : si le centre d'une face (sans sommet racine/encastré) passe sous `min_off`, ses sommets
    sont repoussés du déficit le long de la normale de la peau (surface convexe entre sommets)."""
    V = V.copy()
    moved = 0
    for _ in range(iters):
        changed = False
        for f in F:
            if (ROOTFLAG[f] != 0).any():
                continue
            c = V[f].mean(0)
            q, n, sd, _fi, _bc = surf.nearest(c)
            if sd < min_off:
                V[f] += n * (min_off - sd + 1e-4)
                moved += 1
                changed = True
        if not changed:
            break
    return V, {"faces_pushed": moved}


def penetration_report(surf, V, F, ROOTFLAG, tol=-0.0005):
    """Compte les sommets ordinaires et les centres de faces (sans sommet racine/encastré) sous la peau
    (distance signée < tol), et la profondeur moyenne des racines."""
    sd_v = np.array([surf.nearest(v)[2] for v in V])
    normal = ROOTFLAG == 0
    bad_v = int(((sd_v < tol) & normal).sum())
    bad_f = 0
    for f in F:
        if (ROOTFLAG[f] != 0).any():
            continue
        if surf.nearest(V[f].mean(0))[2] < tol:
            bad_f += 1
    roots = ROOTFLAG == 1
    return {"vertices_inside": bad_v, "faces_inside": bad_f,
            "min_sd": float(sd_v[normal].min()) if normal.any() else 0.0,
            "root_depth_mean": float(-sd_v[roots].mean()) if roots.any() else 0.0}


# ----------------------------------------------------------------------------------------------
# Poids
# ----------------------------------------------------------------------------------------------
def chain_param(points, chain_pts):
    """Projection de points sur une polyligne : renvoie (abscisse curviligne, distance)."""
    P = np.atleast_2d(points)
    A = chain_pts[:-1]
    B = chain_pts[1:]
    AB = B - A
    L = np.linalg.norm(AB, axis=1)
    cum = np.concatenate([[0.0], np.cumsum(L)])
    best_s = np.zeros(len(P))
    best_d = np.full(len(P), np.inf)
    for k in range(len(A)):
        t = np.clip(((P - A[k]) @ AB[k]) / (L[k] ** 2), 0.0, 1.0)
        Q = A[k] + t[:, None] * AB[k]
        d = np.linalg.norm(P - Q, axis=1)
        better = d < best_d
        best_d[better] = d[better]
        best_s[better] = cum[k] + t[better] * L[k]
    return best_s, best_d


def chain_weights(points, J, names, smooth=0.5):
    """Poids le long d'une chaîne d'os (liste ordonnée de noms) : fonctions chapeau centrées sur le milieu
    des os, largeur `smooth` (fraction de longueur d'os). Renvoie (n, NJ)."""
    heads = np.array([J[n][0] for n in names])
    tails = np.array([J[n][1] for n in names])
    chain_pts = np.vstack([heads, tails[-1:]])
    s, _d = chain_param(points, chain_pts)
    L = np.linalg.norm(tails - heads, axis=1)
    starts = np.concatenate([[0.0], np.cumsum(L)[:-1]])
    mids = starts + L / 2
    W = np.zeros((len(s), NJ))
    for i, si in enumerate(s):
        k = int(np.clip(np.searchsorted(mids, si) - 1, -1, len(names) - 1))
        if k < 0:
            W[i, JIDX[names[0]]] = 1.0
            continue
        if k >= len(names) - 1:
            W[i, JIDX[names[-1]]] = 1.0
            continue
        t = (si - mids[k]) / (mids[k + 1] - mids[k])
        # bande de transition réglable autour de la frontière entre os
        t = smoothstep(0.5 - smooth / 2, 0.5 + smooth / 2, t) if smooth < 1 else t
        W[i, JIDX[names[k]]] += 1 - t
        W[i, JIDX[names[k + 1]]] += t
    return W


def limit_influences(W, k=4, eps=1e-4):
    """Limite continue à k influences (soustrait la (k+1)-ième plus grande, rogne, renormalise)."""
    W = np.array(W, np.float64)
    W[W < eps] = 0.0
    if W.shape[1] > k:
        srt = np.sort(W, axis=1)[:, ::-1]
        kth = srt[:, k][:, None]
        W = np.clip(W - kth, 0.0, None)
    W[W < eps] = 0.0
    s = W.sum(1, keepdims=True)
    W = W / np.maximum(s, 1e-12)
    return W


def weight_stats(W):
    nz = (W > 0).sum(1)
    return {"max_influences": int(nz.max()), "mean_influences": float(nz.mean()),
            "sum_err": float(np.abs(W.sum(1) - 1).max()), "unweighted": int((W.sum(1) < 0.5).sum()),
            "joints": sorted({JOINTS[j] for j in np.nonzero(W.sum(0) > 1e-6)[0]})}


# ----------------------------------------------------------------------------------------------
# Écriture Blender
# ----------------------------------------------------------------------------------------------
def duplicate_report(V, UV, tol=1e-6):
    """Nombre de sommets confondus (même position ET même UV) — devrait être 0."""
    key = np.hstack([np.round(V / tol), np.round(UV / tol)]).astype(np.int64)
    _u, counts = np.unique(key, axis=0, return_counts=True)
    return int((counts - 1).sum())


HAIR_MATERIAL_NAME = "M_Hair"    # imposé par la tâche « hair » (cf. rapport : l'export attend slot_primary)


def hair_material(textures_rel: dict, name: str = HAIR_MATERIAL_NAME):
    """Matériau M_Hair (aperçu Blender) : albedo d'aperçu + alpha, normales OpenGL. Les indications runtime sont
    stockées en propriétés personnalisées."""
    import bpy

    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    img_alb = bpy.data.images.load(textures_rel["albedo_default"], check_existing=True)
    img_alb.alpha_mode = "STRAIGHT"
    talb = nt.nodes.new("ShaderNodeTexImage")
    talb.name = talb.label = "HairAlbedo"
    talb.image = img_alb
    talb.location = (-400, 150)
    nt.links.new(talb.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(talb.outputs["Alpha"], bsdf.inputs["Alpha"])
    img_n = bpy.data.images.load(textures_rel["normal"], check_existing=True)
    img_n.colorspace_settings.name = "Non-Color"
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.name = tn.label = "HairNormal"
    tn.image = img_n
    tn.location = (-400, -200)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (-100, -200)
    nm.inputs["Strength"].default_value = 0.6
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = htex.MATERIAL_HINTS["roughness"]
    bsdf.inputs["Specular IOR Level"].default_value = htex.MATERIAL_HINTS["specular"]
    bsdf.inputs["Anisotropic"].default_value = 0.4
    mat.use_backface_culling = False
    mat.blend_method = "HASHED" if hasattr(mat, "blend_method") else None
    for k, v in htex.MATERIAL_HINTS.items():
        mat[k] = v
    # propriétés reconnues par pony/blender_extract.py (MATERIAL_PROPS) ; chemins relatifs à Pipeline/build/textures
    mat["pony_base_color_tex"] = "hair_albedo_default.png"
    mat["pony_normal_tex"] = "hair_normal.png"
    mat["pony_opacity_threshold"] = float(htex.MATERIAL_HINTS["opacityThreshold"])
    mat["pony_opacity_from_alpha"] = True
    mat["pony_roughness"] = float(htex.MATERIAL_HINTS["roughness"])
    mat["pony_metallic"] = 0.0
    mat["pony_tint"] = (1.0, 1.0, 1.0)       # l'albedo par défaut est déjà coloré (brun)
    mat["hair_strands"] = textures_rel["strands"]
    mat["note"] = ("Albedo d'aperçu (brun). Au runtime l'albedo est recalculé depuis hair_strands.png "
                   "(R luminance, G racine->pointe, B aléa par mèche, A alpha).")
    return mat


def write_part_blend(part_id, arrays, W, path, textures_rel, props=None):
    """Crée une scène vide avec l'armature PonyRig et le mesh `part_id` (modificateur Armature, groupes de
    sommets = 70 joints dans l'ordre du gabarit, poids ≤ 4 normalisés, normales personnalisées), puis enregistre."""
    import bpy

    from . import rig

    bpy.ops.wm.read_factory_settings(use_empty=True)
    arm = rig.build_armature()
    V, F, UV = arrays["V"], arrays["F"], arrays["UV"]
    FACING = arrays["FACING"]
    me = bpy.data.meshes.new(part_id)
    me.from_pydata(V.tolist(), [], [list(map(int, f)) for f in F])
    if me.validate(verbose=False):
        print(f"[hair] {part_id}: Mesh.validate() a corrigé la géométrie")
    me.update(calc_edges=True)
    uvl = me.uv_layers.new(name="UVMap")
    lv = np.zeros(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    uvl.data.foreach_set("uv", UV[lv].astype(np.float32).ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    # normales « de volume » : moyenne de la normale géométrique et de la direction extérieure du volume de crins
    me.update()
    gnorm = np.zeros((len(V), 3))
    vn = np.empty(len(V) * 3, np.float32)
    me.vertices.foreach_get("normal", vn)
    gnorm = vn.reshape(-1, 3).astype(np.float64)
    gn_aligned = np.where(((gnorm * FACING).sum(1) < 0)[:, None], -gnorm, gnorm)
    cn = nrm(0.35 * gn_aligned + 0.65 * FACING)
    me.normals_split_custom_set_from_vertices(cn.astype(np.float32).tolist())
    # attributs de débogage / runtime éventuel : couche et paramètre racine->pointe
    if "TAG" in arrays:
        at = me.attributes.new("hair_layer", "INT", "POINT")
        at.data.foreach_set("value", np.asarray(arrays["TAG"], np.int32))
    if "S" in arrays:
        at = me.attributes.new("hair_s", "FLOAT", "POINT")
        at.data.foreach_set("value", np.asarray(arrays["S"], np.float32))
    if "ROOTFLAG" in arrays:   # 0 ordinaire, 1 racine (sous la peau), 2 encastré (dessous des boutons/nattes)
        at = me.attributes.new("hair_flag", "INT", "POINT")
        at.data.foreach_set("value", np.asarray(arrays["ROOTFLAG"], np.int32))
    ob = bpy.data.objects.new(part_id, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = arm
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    for n in JOINTS:
        ob.vertex_groups.new(name=n)
    for j in range(NJ):
        idx = np.nonzero(W[:, j] > 0)[0]
        if len(idx) == 0:
            continue
        g = ob.vertex_groups[JOINTS[j]]
        for i in idx:
            g.add([int(i)], float(W[i, j]), "REPLACE")
    mat = hair_material(textures_rel)
    me.materials.append(mat)
    ob["part_id"] = part_id
    ob["category"] = "hair"
    for k, v in (props or {}).items():
        ob[k] = v
    bpy.context.preferences.filepaths.save_version = 0      # pas de fichiers .blend1
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)
    bpy.ops.file.make_paths_relative()            # textures référencées en chemins relatifs (//../textures/…)
    bpy.ops.wm.save_mainfile(compress=True)
    return ob
