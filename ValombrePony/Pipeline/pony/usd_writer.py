"""Écriture des fichiers USD/USDZ du poney avec `pxr` (usd-core), indépendamment de Blender.

Pourquoi pas l'exporteur USD de Blender : cf. Docs/research/usd.md §4.4 (normal en float3, restTransforms
pris dans la pose courante, elementSize non plafonné, pas de normalOffsets, framesPerSecond absent…).
Ici tout est écrit explicitement selon Docs/SPEC.md §4 et §10 :

    #usda 1.0  (upAxis="Y", metersPerUnit=1, timeCodesPerSecond=framesPerSecond=30, defaultPrim=<racine>)
    def Xform "<racine>" (kind="component")
        def SkelRoot "Rig"
            def Skeleton "Skel"   (joints = chemins, bindTransforms = monde RK, restTransforms = locales RK)
                def SkelAnimation "<clip>"   (optionnel : fichier d'aperçu Quick Look)
            def Mesh "<nom>"      (SkelBindingAPI + MaterialBindingAPI, normales/UV faceVarying, ≤ 4 influences)
                def BlendShape "<nom>"  (offsets, normalOffsets, pointIndices creux, sans in-betweens)
                def GeomSubset "mat_<matériau>"  (si plusieurs matériaux)
        def Scope "Materials"  (UsdPreviewSurface, textures PNG)

Conventions numériques (toutes les données reçues sont DÉJÀ en espace RealityKit, Y haut, −Z avant) :
- matrices numpy en convention colonne (p' = M·p, translation dans M[:3, 3]) ; USD (Gf.Matrix4d) est en
  convention ligne (p' = p·M) : on écrit donc la transposée ;
- quaternions numpy en [x, y, z, w].

Le module n'importe PAS bpy : l'extraction depuis Blender est dans `blender_extract.py`.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

FPS = 30.0
MAX_INFLUENCES = 4                      # [I] plafond retenu (aucune limite Apple documentée, cf. usd.md §1.3)
SKEL_ROOT_NAME = "Rig"
SKELETON_NAME = "Skel"
MATERIALS_SCOPE = "Materials"
TEXTURE_SUBDIR = "textures"
SUBSET_PREFIX = "mat_"                  # [I] préfixe des GeomSubsets (évite toute collision avec un BlendShape)
# Seuils de creux des blend shapes [I] : suppriment le bruit numérique (sculpt, Surface Deform) qui rendrait
# chaque forme dense. 2 µm × 24 formes à poids 1 = 4.8e-5 m < tolérance de validation (1e-4 m).
OFFSET_EPS = 2e-6                       # m : en dessous, un point est considéré non déplacé par un blend shape
NORMAL_EPS = 1e-4                       # variation de normale (unitaire) considérée nulle (≈ 0.006°)

# --------------------------------------------------------------------------------------------------
# Structures de données (indépendantes de Blender)
# --------------------------------------------------------------------------------------------------


@dataclass
class SkeletonData:
    """Squelette en espace RealityKit. `bind_world` = repères monde (bindTransforms) ;
    `rest_local` = locales parent→enfant (restTransforms). Matrices 4x4 convention colonne."""
    names: list[str]
    parents: list[int]
    bind_world: np.ndarray            # (N, 4, 4)
    rest_local: np.ndarray            # (N, 4, 4)

    @property
    def paths(self) -> list[str]:
        """Tokens USD : chemins `root/body/spine_01/...` (parents avant enfants)."""
        out: list[str] = []
        for i, p in enumerate(self.parents):
            out.append(self.names[i] if p < 0 else out[p] + "/" + self.names[i])
        return out

    def check(self):
        n = len(self.names)
        assert len(self.parents) == n and self.bind_world.shape == (n, 4, 4) and self.rest_local.shape == (n, 4, 4)
        for i, p in enumerate(self.parents):
            if p >= i:
                raise ValueError(f"squelette : le parent de {self.names[i]} n'est pas avant lui")
        for nm in self.names:
            if any(c in nm for c in "./[]\\ ") or not nm.isascii():
                raise ValueError(f"nom de joint invalide (SPEC §1) : {nm!r}")


@dataclass
class BlendShapeData:
    """Blend shape (pas d'in-between). `offsets` denses (P,3) si `point_indices` est None, sinon (K,3).
    `normal_offsets` : calculés par le writer si None (même indexation que `offsets` en entrée)."""
    name: str
    offsets: np.ndarray
    point_indices: Optional[np.ndarray] = None
    normal_offsets: Optional[np.ndarray] = None


@dataclass
class MeshData:
    """Mesh skinné, données en espace RK, pose de liaison (base des blend shapes).
    `face_materials[f]` indexe `material_names`."""
    name: str
    points: np.ndarray                       # (P, 3)
    face_counts: np.ndarray                  # (F,)
    face_indices: np.ndarray                 # (L,)
    joint_indices: np.ndarray                # (P, k) indices dans SkeletonData.names
    joint_weights: np.ndarray                # (P, k)
    material_names: list[str]
    face_materials: Optional[np.ndarray] = None   # (F,) ; None = un seul matériau
    normals: Optional[np.ndarray] = None     # (L, 3) faceVarying ; None = normales lissées calculées
    uvs: Optional[np.ndarray] = None         # (L, 2) faceVarying (primvar `st`)
    blend_shapes: list[BlendShapeData] = field(default_factory=list)


@dataclass
class MaterialData:
    """Matériau UsdPreviewSurface (workflow métallique). Chemins de textures = fichiers PNG sur disque.
    ORM : R = occlusion, G = rugosité, B = métal (SPEC §4)."""
    name: str
    base_color: tuple = (0.8, 0.8, 0.8)
    base_color_texture: Optional[str] = None       # sRGB
    base_color_scale: Optional[tuple] = None        # teinte (r,g,b) via UsdUVTexture.scale (aperçu uniquement)
    normal_texture: Optional[str] = None            # raw, convention OpenGL (Y+)
    orm_texture: Optional[str] = None               # raw
    roughness: float = 0.7
    metallic: float = 0.0
    opacity: float = 1.0
    opacity_from_base_alpha: bool = False           # opacité = canal A de la texture de couleur
    opacity_threshold: float = 0.0                  # > 0 : découpe (cartes de crins)
    clearcoat: float = 0.0
    clearcoat_roughness: float = 0.01
    ior: Optional[float] = None

    def textures(self) -> list[str]:
        return [t for t in (self.base_color_texture, self.normal_texture, self.orm_texture) if t]


@dataclass
class AnimationData:
    """Animation squelettique (locales RK) pour le fichier d'aperçu. Les poids de blend shapes optionnels."""
    name: str
    translations: np.ndarray                  # (F, N, 3)
    rotations_xyzw: np.ndarray                # (F, N, 4)
    scales: np.ndarray                        # (F, N, 3)
    blend_shape_names: list[str] = field(default_factory=list)
    blend_shape_weights: Optional[np.ndarray] = None   # (F, W)
    loop: bool = True


# --------------------------------------------------------------------------------------------------
# Maths (numpy pur)
# --------------------------------------------------------------------------------------------------


def quat_from_matrix(r: np.ndarray) -> np.ndarray:
    """Matrice de rotation 3x3 (convention colonne) -> quaternion [x, y, z, w] unitaire, w >= 0."""
    m = np.asarray(r, dtype=np.float64)
    t = np.trace(m)
    if t > 0.0:
        s = np.sqrt(t + 1.0) * 2.0
        q = np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, 0.25 * s])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q = np.array([0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s, (m[2, 1] - m[1, 2]) / s])
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q = np.array([(m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s, (m[0, 2] - m[2, 0]) / s])
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q = np.array([(m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s, (m[1, 0] - m[0, 1]) / s])
    q /= np.linalg.norm(q)
    return -q if q[3] < 0 else q


def matrix_from_quat(q: np.ndarray) -> np.ndarray:
    x, y, z, w = np.asarray(q, dtype=np.float64) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def decompose_trs(m: np.ndarray):
    """4x4 (convention colonne, M = T·R·S, sans cisaillement) -> (t[3], q[x,y,z,w], s[3])."""
    m = np.asarray(m, dtype=np.float64)
    t = m[:3, 3].copy()
    a = m[:3, :3]
    s = np.linalg.norm(a, axis=0)
    if np.linalg.det(a) < 0:
        s[0] = -s[0]
    r = a / s
    return t, quat_from_matrix(r), s


def compose_trs(t, q, s) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = matrix_from_quat(q) * np.asarray(s, dtype=np.float64)[None, :]
    m[:3, 3] = t
    return m


def quats_from_matrices(r: np.ndarray) -> np.ndarray:
    """Version vectorisée de quat_from_matrix : (..., 3, 3) -> (..., 4) [x, y, z, w], w >= 0."""
    m = np.asarray(r, dtype=np.float64)
    shp = m.shape[:-2]
    m = m.reshape(-1, 3, 3)
    out = np.empty((len(m), 4))
    tr = m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]
    c0 = tr > 0
    c1 = ~c0 & (m[:, 0, 0] > m[:, 1, 1]) & (m[:, 0, 0] > m[:, 2, 2])
    c2 = ~c0 & ~c1 & (m[:, 1, 1] > m[:, 2, 2])
    c3 = ~c0 & ~c1 & ~c2
    if c0.any():
        a = m[c0]; s = np.sqrt(tr[c0] + 1.0) * 2.0
        out[c0] = np.stack([(a[:, 2, 1] - a[:, 1, 2]) / s, (a[:, 0, 2] - a[:, 2, 0]) / s,
                            (a[:, 1, 0] - a[:, 0, 1]) / s, 0.25 * s], 1)
    if c1.any():
        a = m[c1]; s = np.sqrt(1.0 + a[:, 0, 0] - a[:, 1, 1] - a[:, 2, 2]) * 2.0
        out[c1] = np.stack([0.25 * s, (a[:, 0, 1] + a[:, 1, 0]) / s, (a[:, 0, 2] + a[:, 2, 0]) / s,
                            (a[:, 2, 1] - a[:, 1, 2]) / s], 1)
    if c2.any():
        a = m[c2]; s = np.sqrt(1.0 + a[:, 1, 1] - a[:, 0, 0] - a[:, 2, 2]) * 2.0
        out[c2] = np.stack([(a[:, 0, 1] + a[:, 1, 0]) / s, 0.25 * s, (a[:, 1, 2] + a[:, 2, 1]) / s,
                            (a[:, 0, 2] - a[:, 2, 0]) / s], 1)
    if c3.any():
        a = m[c3]; s = np.sqrt(1.0 + a[:, 2, 2] - a[:, 0, 0] - a[:, 1, 1]) * 2.0
        out[c3] = np.stack([(a[:, 0, 2] + a[:, 2, 0]) / s, (a[:, 1, 2] + a[:, 2, 1]) / s, 0.25 * s,
                            (a[:, 1, 0] - a[:, 0, 1]) / s], 1)
    out /= np.linalg.norm(out, axis=1, keepdims=True)
    out[out[:, 3] < 0] *= -1.0
    return out.reshape(*shp, 4)


def decompose_trs_batch(m: np.ndarray):
    """(..., 4, 4) -> T (..., 3), R (..., 4) [x,y,z,w], S (..., 3) (M = T·R·S, sans cisaillement)."""
    m = np.asarray(m, dtype=np.float64)
    t = m[..., :3, 3].copy()
    a = m[..., :3, :3]
    s = np.linalg.norm(a, axis=-2)
    neg = np.linalg.det(a) < 0
    s[neg, 0] *= -1.0
    r = a / s[..., None, :]
    return t, quats_from_matrices(r), s


def matrices_from_quats(q: np.ndarray) -> np.ndarray:
    q = np.asarray(q, dtype=np.float64)
    q = q / np.linalg.norm(q, axis=-1, keepdims=True)
    x, y, z, w = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
        np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
        np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


def compose_trs_batch(t, q, s) -> np.ndarray:
    t = np.asarray(t, dtype=np.float64)
    out = np.zeros(t.shape[:-1] + (4, 4))
    out[..., :3, :3] = matrices_from_quats(q) * np.asarray(s, dtype=np.float64)[..., None, :]
    out[..., :3, 3] = t
    out[..., 3, 3] = 1.0
    return out


def make_quat_continuous(q: np.ndarray) -> np.ndarray:
    """(F, 4) : choisit le signe de chaque quaternion pour rester dans l'hémisphère du précédent."""
    q = np.array(q, dtype=np.float64)
    for f in range(1, len(q)):
        if np.dot(q[f], q[f - 1]) < 0:
            q[f] = -q[f]
    return q


def gf_matrix(m: np.ndarray):
    from pxr import Gf
    return Gf.Matrix4d(np.asarray(m, dtype=np.float64).T.tolist())


def limit_influences(indices: np.ndarray, weights: np.ndarray, k: int = MAX_INFLUENCES):
    """Limite à `k` influences par sommet de façon CONTINUE (Docs/research/blender.md §4) :
    on soustrait le (k+1)-ième plus grand poids à tous les poids, on coupe à 0 et on renormalise.
    (La troncature naïve crée des plis visibles.) Renvoie (indices (P,k), poids (P,k)) triés par poids
    décroissant, normalisés ; les emplacements vides valent (0, 0.0).
    Sommet dont tous les poids s'annulent après soustraction (k+1 poids égaux) : repli sur la troncature."""
    idx = np.asarray(indices, dtype=np.int64)
    w = np.asarray(weights, dtype=np.float64).copy()
    if idx.ndim == 1:
        idx, w = idx[:, None], w[:, None]
    w[w < 0] = 0.0
    order = np.argsort(-w, axis=1, kind="stable")
    w = np.take_along_axis(w, order, axis=1)
    idx = np.take_along_axis(idx, order, axis=1)
    if w.shape[1] > k:
        kth = w[:, k:k + 1]
        top = np.clip(w[:, :k] - kth, 0.0, None)
        dead = top.sum(1) <= 1e-12
        top[dead] = w[dead, :k]
        w, idx = top, idx[:, :k]
    elif w.shape[1] < k:
        pad = k - w.shape[1]
        w = np.concatenate([w, np.zeros((len(w), pad))], 1)
        idx = np.concatenate([idx, np.zeros((len(idx), pad), np.int64)], 1)
    s = w.sum(1, keepdims=True)
    if np.any(s <= 0):
        raise ValueError(f"{int((s <= 0).sum())} sommet(s) sans aucune influence")
    w = w / s
    idx[w <= 0] = 0
    return idx, w


def normalize_and_sort_influences(indices: np.ndarray, weights: np.ndarray, k_max: int = MAX_INFLUENCES):
    """Trie/normalise et réduit elementSize au nombre d'influences réellement utilisées (≥ 1, ≤ k_max)."""
    idx, w = limit_influences(indices, weights, k_max)
    used = int(max(1, (w > 0).sum(1).max()))
    return idx[:, :used], w[:, :used]


def vertex_normals(points: np.ndarray, counts: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Normales lissées par sommet (somme des normales de faces pondérées par l'aire, méthode de Newell)."""
    p = np.asarray(points, dtype=np.float64)
    counts = np.asarray(counts, dtype=np.int64)
    indices = np.asarray(indices, dtype=np.int64)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    face_of_loop = np.repeat(np.arange(len(counts)), counts)
    local = np.arange(len(indices)) - starts[face_of_loop]
    nxt = starts[face_of_loop] + (local + 1) % counts[face_of_loop]
    a, b = p[indices], p[indices[nxt]]
    cr = np.cross(a, b)
    fn = np.zeros((len(counts), 3))
    np.add.at(fn, face_of_loop, cr)
    vn = np.zeros_like(p)
    np.add.at(vn, indices, fn[face_of_loop])
    ln = np.linalg.norm(vn, axis=1, keepdims=True)
    ln[ln < 1e-20] = 1.0
    return vn / ln


def dense_offsets(bs: BlendShapeData, n_points: int) -> np.ndarray:
    off = np.zeros((n_points, 3))
    if bs.point_indices is None:
        off[:] = bs.offsets
    else:
        off[np.asarray(bs.point_indices, dtype=np.int64)] = bs.offsets
    return off


def sparse_blend_shape(mesh: MeshData, bs: BlendShapeData, base_normals: Optional[np.ndarray] = None):
    """-> (pointIndices, offsets, normalOffsets) creux. Les normalOffsets (par point) sont la différence
    des normales lissées du mesh déformé et du mesh de base ; ils incluent les voisins non déplacés dont la
    normale change. Si `bs.normal_offsets` est fourni, il est utilisé tel quel."""
    n = len(mesh.points)
    off = dense_offsets(bs, n)
    if bs.normal_offsets is not None:
        noff = np.zeros((n, 3))
        if bs.point_indices is None:
            noff[:] = bs.normal_offsets
        else:
            noff[np.asarray(bs.point_indices, dtype=np.int64)] = bs.normal_offsets
    else:
        if base_normals is None:
            base_normals = vertex_normals(mesh.points, mesh.face_counts, mesh.face_indices)
        moved = np.linalg.norm(off, axis=1) > OFFSET_EPS
        if moved.any():
            noff = vertex_normals(mesh.points + off, mesh.face_counts, mesh.face_indices) - base_normals
        else:
            noff = np.zeros((n, 3))
    sel = np.nonzero((np.linalg.norm(off, axis=1) > OFFSET_EPS) | (np.linalg.norm(noff, axis=1) > NORMAL_EPS))[0]
    return sel.astype(np.int32), off[sel], noff[sel]


# --------------------------------------------------------------------------------------------------
# Écriture du stage
# --------------------------------------------------------------------------------------------------


def _valid_identifier(name: str) -> bool:
    from pxr import Tf
    return Tf.IsValidIdentifier(name)


def _copy_texture(src: str, tex_dir: Path, used: dict) -> str:
    """Copie une texture à côté du stage ; renvoie le chemin d'asset relatif `./textures/<nom>.png`."""
    src = str(src)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"texture introuvable : {src}")
    if not src.lower().endswith(".png"):
        raise ValueError(f"texture non PNG (SPEC §4) : {src}")
    base = os.path.basename(src)
    digest = hashlib.sha1(open(src, "rb").read()).hexdigest()
    stem, ext = os.path.splitext(base)
    name, n = base, 1
    while name in used and used[name] != digest:
        name = f"{stem}_{n}{ext}"
        n += 1
    if name not in used:
        tex_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, tex_dir / name)
        used[name] = digest
    return f"./{TEXTURE_SUBDIR}/{name}"


def _write_material(stage, mat_path: str, md: MaterialData, tex_dir: Path, used_tex: dict):
    from pxr import Gf, Sdf, UsdShade
    if md.orm_texture and md.opacity_from_base_alpha and md.base_color_texture:
        raise ValueError(f"{md.name} : une seule texture empaquetée par matériau (RealityKit) — "
                         "ORM et alpha de la couleur ne peuvent pas coexister")
    mat = UsdShade.Material.Define(stage, mat_path)
    pbr = UsdShade.Shader.Define(stage, f"{mat_path}/PreviewSurface")
    pbr.CreateIdAttr("UsdPreviewSurface")
    pbr.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(0)
    reader_out = None

    def uv_reader():
        nonlocal reader_out
        if reader_out is None:
            rd = UsdShade.Shader.Define(stage, f"{mat_path}/uvReader")
            rd.CreateIdAttr("UsdPrimvarReader_float2")
            rd.CreateInput("varname", Sdf.ValueTypeNames.String).Set("st")
            reader_out = rd.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        return reader_out

    def texture(node: str, file: str, color_space: str, scale=None, bias=None, fallback=None):
        tx = UsdShade.Shader.Define(stage, f"{mat_path}/{node}")
        tx.CreateIdAttr("UsdUVTexture")
        tx.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(_copy_texture(file, tex_dir, used_tex))
        tx.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set(color_space)
        tx.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
        tx.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
        tx.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(uv_reader())
        if scale is not None:
            tx.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(*scale))
        if bias is not None:
            tx.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(*bias))
        if fallback is not None:
            tx.CreateInput("fallback", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(*fallback))
        return tx

    if md.base_color_texture:
        sc = None
        if md.base_color_scale is not None:
            sc = (*[float(c) for c in md.base_color_scale[:3]], 1.0)
        tc = texture("BaseColorTex", md.base_color_texture, "sRGB", scale=sc,
                     fallback=(*[float(c) for c in md.base_color], 1.0))
        pbr.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(
            tc.CreateOutput("rgb", Sdf.ValueTypeNames.Float3))
        if md.opacity_from_base_alpha:
            pbr.CreateInput("opacity", Sdf.ValueTypeNames.Float).ConnectToSource(
                tc.CreateOutput("a", Sdf.ValueTypeNames.Float))
    else:
        pbr.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*[float(c) for c in md.base_color]))
    if not (md.base_color_texture and md.opacity_from_base_alpha):
        if md.opacity < 1.0:
            pbr.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(float(md.opacity))
    if md.opacity_threshold > 0.0:
        pbr.CreateInput("opacityThreshold", Sdf.ValueTypeNames.Float).Set(float(md.opacity_threshold))

    if md.orm_texture:
        orm = texture("ORMTex", md.orm_texture, "raw")
        pbr.CreateInput("occlusion", Sdf.ValueTypeNames.Float).ConnectToSource(orm.CreateOutput("r", Sdf.ValueTypeNames.Float))
        pbr.CreateInput("roughness", Sdf.ValueTypeNames.Float).ConnectToSource(orm.CreateOutput("g", Sdf.ValueTypeNames.Float))
        pbr.CreateInput("metallic", Sdf.ValueTypeNames.Float).ConnectToSource(orm.CreateOutput("b", Sdf.ValueTypeNames.Float))
    else:
        pbr.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(md.roughness))
        pbr.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(md.metallic))

    if md.normal_texture:
        # UsdPreviewSurface §normal : texture 8 bits -> scale (2,2,2,1), bias (-1,-1,-1,0), espace "raw".
        nt = texture("NormalTex", md.normal_texture, "raw", scale=(2.0, 2.0, 2.0, 1.0), bias=(-1.0, -1.0, -1.0, 0.0))
        pbr.CreateInput("normal", Sdf.ValueTypeNames.Normal3f).ConnectToSource(
            nt.CreateOutput("rgb", Sdf.ValueTypeNames.Float3))
    if md.clearcoat > 0.0:
        pbr.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(float(md.clearcoat))
        pbr.CreateInput("clearcoatRoughness", Sdf.ValueTypeNames.Float).Set(float(md.clearcoat_roughness))
    if md.ior is not None:
        pbr.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(float(md.ior))
    mat.CreateSurfaceOutput().ConnectToSource(pbr.ConnectableAPI(), "surface")
    return mat


def _write_mesh(stage, path: str, md: MeshData, skel_prim, materials: dict, n_joints: int):
    from pxr import Gf, Sdf, UsdGeom, UsdShade, UsdSkel, Vt
    pts = np.asarray(md.points, dtype=np.float64)
    counts = np.asarray(md.face_counts, dtype=np.int64)
    fidx = np.asarray(md.face_indices, dtype=np.int64)
    n_loops = int(counts.sum())
    if len(fidx) != n_loops:
        raise ValueError(f"{md.name} : faceVertexIndices ({len(fidx)}) ≠ somme des faceVertexCounts ({n_loops})")
    if fidx.min() < 0 or fidx.max() >= len(pts):
        raise ValueError(f"{md.name} : indice de sommet hors limites")
    if counts.min() < 3:
        raise ValueError(f"{md.name} : face de moins de 3 sommets")

    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(pts.astype(np.float32)))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(counts.astype(np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(fidx.astype(np.int32)))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateDoubleSidedAttr(False)
    mesh.CreateOrientationAttr(UsdGeom.Tokens.rightHanded)
    mesh.CreateExtentAttr(UsdGeom.PointBased.ComputeExtent(Vt.Vec3fArray.FromNumpy(pts.astype(np.float32))))

    if md.normals is not None:
        nrm = np.asarray(md.normals, dtype=np.float64)
        if nrm.shape != (n_loops, 3):
            raise ValueError(f"{md.name} : normales attendues faceVarying ({n_loops},3), reçu {nrm.shape}")
    else:
        nrm = vertex_normals(pts, counts, fidx)[fidx]
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    ln[ln < 1e-20] = 1.0
    mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy((nrm / ln).astype(np.float32)))
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)

    if md.uvs is not None:
        uv = np.asarray(md.uvs, dtype=np.float32)
        if uv.shape != (n_loops, 2):
            raise ValueError(f"{md.name} : UV attendues faceVarying ({n_loops},2), reçu {uv.shape}")
        pv = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray,
                                                    UsdGeom.Tokens.faceVarying)
        pv.Set(Vt.Vec2fArray.FromNumpy(uv))

    # --- skinning
    ji, jw = normalize_and_sort_influences(md.joint_indices, md.joint_weights)
    if ji.max() >= n_joints:
        raise ValueError(f"{md.name} : indice de joint hors limites ({ji.max()} ≥ {n_joints})")
    k = ji.shape[1]
    binding = UsdSkel.BindingAPI.Apply(mesh.GetPrim())
    binding.CreateSkeletonRel().SetTargets([skel_prim.GetPath()])
    binding.CreateJointIndicesPrimvar(False, k).Set(Vt.IntArray.FromNumpy(ji.astype(np.int32).ravel()))
    binding.CreateJointWeightsPrimvar(False, k).Set(Vt.FloatArray.FromNumpy(jw.astype(np.float32).ravel()))
    binding.CreateGeomBindTransformAttr(Gf.Matrix4d(1.0))

    # --- blend shapes
    info_bs = []
    if md.blend_shapes:
        names = [b.name for b in md.blend_shapes]
        if len(set(names)) != len(names):
            raise ValueError(f"{md.name} : noms de blend shapes en double")
        base_n = vertex_normals(pts, counts, fidx)
        targets = []
        for bs in md.blend_shapes:
            if not _valid_identifier(bs.name):
                raise ValueError(f"{md.name} : nom de blend shape invalide {bs.name!r}")
            sel, off, noff = sparse_blend_shape(md, bs, base_n)
            if len(sel) == 0:
                # [I] forme sans effet : on garde le nom (contrat) avec un seul point à décalage nul.
                sel, off, noff = np.array([0], np.int32), np.zeros((1, 3)), np.zeros((1, 3))
            prim = UsdSkel.BlendShape.Define(stage, f"{path}/{bs.name}")
            prim.CreateOffsetsAttr(Vt.Vec3fArray.FromNumpy(off.astype(np.float32)))
            prim.CreateNormalOffsetsAttr(Vt.Vec3fArray.FromNumpy(noff.astype(np.float32)))
            prim.CreatePointIndicesAttr(Vt.IntArray.FromNumpy(sel.astype(np.int32)))
            targets.append(prim.GetPath())
            info_bs.append({"name": bs.name, "points": int(len(sel)),
                            "maxOffset": float(np.linalg.norm(off, axis=1).max())})
        binding.CreateBlendShapesAttr(Vt.TokenArray(names))
        binding.CreateBlendShapeTargetsRel().SetTargets(targets)

    # --- matériaux
    mba = UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim())
    mat_names = list(md.material_names)
    for mn in mat_names:
        if mn not in materials:
            raise ValueError(f"{md.name} : matériau inconnu {mn!r}")
    if md.face_materials is None or len(set(np.asarray(md.face_materials).tolist())) <= 1:
        used = mat_names[int(md.face_materials[0])] if md.face_materials is not None and len(md.face_materials) else mat_names[0]
        mba.Bind(materials[used])
        subsets = []
    else:
        fm = np.asarray(md.face_materials, dtype=np.int64)
        if len(fm) != len(counts):
            raise ValueError(f"{md.name} : face_materials doit avoir une entrée par face")
        mba.Bind(materials[mat_names[int(np.bincount(fm).argmax())]])  # repli (toutes les faces sont couvertes)
        subsets = []
        for mi in sorted(set(fm.tolist())):
            faces = np.nonzero(fm == mi)[0].astype(np.int32)
            ss = mba.CreateMaterialBindSubset(SUBSET_PREFIX + mat_names[mi], Vt.IntArray.FromNumpy(faces),
                                              UsdGeom.Tokens.face)
            UsdShade.MaterialBindingAPI.Apply(ss.GetPrim()).Bind(materials[mat_names[mi]])
            subsets.append(mat_names[mi])
        mba.SetMaterialBindSubsetsFamilyType(UsdGeom.Tokens.partition)
    return mesh, {
        "name": md.name, "points": int(len(pts)), "faces": int(len(counts)),
        "triangles": int((counts - 2).sum()), "influences": int(k), "blendShapes": info_bs,
        "materials": sorted(set(mat_names if md.face_materials is None else
                                [mat_names[i] for i in set(np.asarray(md.face_materials).tolist())])),
        "subsets": subsets,
    }


def write_asset(usda_path, *, root_name: str, skeleton: SkeletonData, meshes: Sequence[MeshData],
                materials: Sequence[MaterialData], animation: Optional[AnimationData] = None,
                doc: str = "") -> dict:
    """Écrit `usda_path` (+ dossier `textures/` à côté). Renvoie un résumé (dict)."""
    from pxr import Gf, Kind, Sdf, Usd, UsdGeom, UsdShade, UsdSkel, Vt

    skeleton.check()
    usda_path = Path(usda_path)
    usda_path.parent.mkdir(parents=True, exist_ok=True)
    tex_dir = usda_path.parent / TEXTURE_SUBDIR
    if tex_dir.exists():
        shutil.rmtree(tex_dir)       # dossier de staging créé par ce module : on repart de zéro
    for nm in [root_name] + [m.name for m in meshes] + [m.name for m in materials]:
        if not _valid_identifier(nm):
            raise ValueError(f"identifiant USD invalide : {nm!r}")
    if len({m.name for m in meshes}) != len(meshes):
        raise ValueError("noms de meshes en double")
    if len({m.name for m in materials}) != len(materials):
        raise ValueError("noms de matériaux en double")
    reserved = {SKELETON_NAME}
    if any(m.name in reserved for m in meshes):
        raise ValueError(f"nom de mesh réservé : {reserved}")

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, UsdGeom.LinearUnits.meters)
    stage.SetTimeCodesPerSecond(FPS)
    stage.SetFramesPerSecond(FPS)
    if doc:
        stage.GetRootLayer().documentation = doc

    root = UsdGeom.Xform.Define(stage, f"/{root_name}")
    stage.SetDefaultPrim(root.GetPrim())
    Usd.ModelAPI(root).SetKind(Kind.Tokens.component)
    skel_root = UsdSkel.Root.Define(stage, f"/{root_name}/{SKEL_ROOT_NAME}")
    skel = UsdSkel.Skeleton.Define(stage, f"/{root_name}/{SKEL_ROOT_NAME}/{SKELETON_NAME}")
    paths = skeleton.paths
    skel.CreateJointsAttr(Vt.TokenArray(paths))
    skel.CreateBindTransformsAttr(Vt.Matrix4dArray([gf_matrix(m) for m in skeleton.bind_world]))
    skel.CreateRestTransformsAttr(Vt.Matrix4dArray([gf_matrix(m) for m in skeleton.rest_local]))
    ok, why = UsdSkel.Topology(Vt.TokenArray(paths)).Validate()
    if not ok:
        raise ValueError(f"topologie de squelette invalide : {why}")

    # matériaux
    UsdGeom.Scope.Define(stage, f"/{root_name}/{MATERIALS_SCOPE}")
    used_tex: dict = {}
    mats = {}
    for md in materials:
        mats[md.name] = _write_material(stage, f"/{root_name}/{MATERIALS_SCOPE}/{md.name}", md, tex_dir, used_tex)

    mesh_info = []
    all_pts = []
    for md in meshes:
        _, info = _write_mesh(stage, f"/{root_name}/{SKEL_ROOT_NAME}/{md.name}", md, skel.GetPrim(), mats,
                              len(paths))
        mesh_info.append(info)
        all_pts.append(np.asarray(md.points))

    # animation (aperçu)
    anim_info = None
    if animation is not None:
        anim_info = _write_animation(stage, skel, paths, animation)

    # étendue du SkelRoot : union des étendues des meshes (pose de liaison) [I]
    if all_pts:
        p = np.concatenate(all_pts)
        lo, hi = p.min(0), p.max(0)
        if animation is not None:
            # marge pour l'animation : déplacement max des joints animés (UsdSkel) [I]
            lo, hi = _animated_extent(stage, skel, skeleton.bind_world[:, :3, 3], lo, hi)
        skel_root.CreateExtentAttr(Vt.Vec3fArray([Gf.Vec3f(*map(float, lo)), Gf.Vec3f(*map(float, hi))]))

    stage.GetRootLayer().Export(str(usda_path))
    # si une couche portant ce chemin est déjà ouverte dans ce processus (export précédent), la recharger
    lyr = Sdf.Layer.Find(str(usda_path))
    if lyr is not None:
        lyr.Reload(force=True)
    return {
        "file": str(usda_path), "root": root_name, "joints": len(paths), "meshes": mesh_info,
        "materials": [m.name for m in materials], "textures": sorted(used_tex), "animation": anim_info,
        "triangles": int(sum(m["triangles"] for m in mesh_info)),
    }


def _write_animation(stage, skel, paths, an: AnimationData) -> dict:
    from pxr import Gf, Usd, UsdSkel, Vt
    F, N = an.translations.shape[:2]
    if N != len(paths):
        raise ValueError(f"animation {an.name} : {N} joints, squelette {len(paths)}")
    if not _valid_identifier(an.name):
        raise ValueError(f"nom d'animation invalide : {an.name!r}")
    a = UsdSkel.Animation.Define(stage, skel.GetPath().AppendChild(an.name))
    a.CreateJointsAttr(Vt.TokenArray(paths))
    rot = np.stack([make_quat_continuous(an.rotations_xyzw[:, j]) for j in range(N)], 1)
    frames = list(range(F))
    if an.loop:
        frames.append(0)              # boucle sans à-coup dans Quick Look : la dernière clé reprend la première
    t_attr, r_attr, s_attr = a.CreateTranslationsAttr(), a.CreateRotationsAttr(), a.CreateScalesAttr()
    w_attr = None
    if an.blend_shape_names:
        a.CreateBlendShapesAttr(Vt.TokenArray(list(an.blend_shape_names)))
        w_attr = a.CreateBlendShapeWeightsAttr()
    for tc, f in enumerate(frames):
        t_attr.Set(Vt.Vec3fArray.FromNumpy(an.translations[f].astype(np.float32)), tc)
        q = rot[f]
        if an.loop and tc == F:
            # même hémisphère que la clé précédente
            q = np.where((np.sum(q * rot[F - 1], 1) < 0)[:, None], -q, q)
        r_attr.Set(Vt.QuatfArray([Gf.Quatf(float(w), float(x), float(y), float(z)) for x, y, z, w in q]), tc)
        s_attr.Set(Vt.Vec3hArray([Gf.Vec3h(*map(float, s)) for s in an.scales[f]]), tc)
        if w_attr is not None:
            w_attr.Set(Vt.FloatArray.FromNumpy(np.asarray(an.blend_shape_weights[f], np.float32)), tc)
    stage.SetStartTimeCode(0)
    stage.SetEndTimeCode(len(frames) - 1)
    UsdSkel.BindingAPI.Apply(skel.GetPrim()).CreateAnimationSourceRel().SetTargets([a.GetPath()])
    return {"name": an.name, "frames": F, "timeSamples": len(frames), "loop": an.loop,
            "blendShapes": list(an.blend_shape_names)}


def _animated_extent(stage, skel, bind_pos, lo, hi):
    """Élargit l'étendue de liaison du déplacement max des joints animés + 10 % de la diagonale [I]
    (indication de culling seulement ; RealityKit recalcule ses bornes)."""
    from pxr import Usd, UsdGeom, UsdSkel
    cache = UsdSkel.Cache()
    cache.Populate(UsdSkel.Root(skel.GetPrim().GetParent()), Usd.PrimDefaultPredicate)
    q = cache.GetSkelQuery(skel)
    pad = 0.0
    for t in range(int(stage.GetStartTimeCode()), int(stage.GetEndTimeCode()) + 1):
        w = np.array([np.array(m)[3, :3] for m in q.ComputeJointWorldTransforms(UsdGeom.XformCache(t))])
        pad = max(pad, float(np.abs(w - bind_pos).max()))
    pad += 0.1 * float(np.linalg.norm(hi - lo))
    return lo - pad, hi + pad


# --------------------------------------------------------------------------------------------------
# Empaquetage USDZ
# --------------------------------------------------------------------------------------------------


def package_usdz(src_layer: str | Path, usdz_path: str | Path) -> dict:
    """`UsdUtils.CreateNewARKitUsdzPackage` depuis la couche racine exportée (PAS de flatten,
    cf. usd.md §3.3). Vérifie : non compressé, données alignées sur 64 octets, première entrée = couche."""
    from pxr import Sdf, UsdUtils
    src_layer, usdz_path = Path(src_layer), Path(usdz_path)
    usdz_path.parent.mkdir(parents=True, exist_ok=True)
    if usdz_path.exists():
        usdz_path.unlink()            # fichier généré par ce pipeline
    lyr = Sdf.Layer.Find(str(usdz_path))
    if lyr is not None:
        lyr.Reload(force=True)
    ok = UsdUtils.CreateNewARKitUsdzPackage(Sdf.AssetPath(str(src_layer)), str(usdz_path))
    if not ok or not usdz_path.exists():
        raise RuntimeError(f"échec de CreateNewARKitUsdzPackage({src_layer} -> {usdz_path})")
    entries = []
    with zipfile.ZipFile(usdz_path) as z:
        with open(usdz_path, "rb") as fh:
            for zi in z.infolist():
                fh.seek(zi.header_offset + 26)
                nlen, xlen = np.frombuffer(fh.read(4), dtype="<u2")
                data_off = zi.header_offset + 30 + int(nlen) + int(xlen)
                entries.append({"name": zi.filename, "compress": zi.compress_type, "size": zi.file_size,
                                "aligned64": data_off % 64 == 0})
    problems = [e for e in entries if e["compress"] != 0 or not e["aligned64"]]
    if problems:
        raise RuntimeError(f"USDZ non conforme (compression/alignement) : {problems}")
    if not entries or not entries[0]["name"].endswith((".usdc", ".usda", ".usd")):
        raise RuntimeError(f"USDZ : la première entrée n'est pas une couche USD : {entries[:1]}")
    return {"file": str(usdz_path), "bytes": usdz_path.stat().st_size, "entries": entries}


def export_usdz(usdz_path, staging_dir, **kwargs) -> dict:
    """write_asset dans `staging_dir/<stem>.usda` puis package_usdz vers `usdz_path`."""
    usdz_path = Path(usdz_path)
    staging_dir = Path(staging_dir)
    usda = staging_dir / (usdz_path.stem + ".usda")
    info = write_asset(usda, **kwargs)
    info["package"] = package_usdz(usda, usdz_path)
    return info
