"""Extraction des données Blender (bpy) vers les structures de `usd_writer` (espace RealityKit).

Ce qui est extrait et comment (Docs/SPEC.md §1, §3, §4, §5) :
- squelette : via `rig.py` (repères de repos `bone.matrix_local`) ; bindTransforms = C·W_B (monde RK),
  restTransforms = locales (identiques Blender/RK sauf root = C·L) ; l'armature doit être à l'identité ;
- meshes : sommets de la clé de référence (base des shape keys) en coordonnées monde Blender puis `C·p` ;
  topologie quads/ngons conservée ; normales de coins (`corner_normals`) et UV de rendu actives en
  faceVarying ; indices de matériaux par face ;
- influences : groupes de sommets portant un nom de joint (les autres groupes sont ignorés), limitées à 4
  de façon CONTINUE (on soustrait le 5e poids puis on renormalise, cf. Docs/research/blender.md §4) ;
  `apply_influence_limit` RÉÉCRIT les groupes de l'objet (en mémoire) pour que l'évaluation Blender
  utilisée par la validation numérique utilise exactement les poids exportés ;
- shape keys -> blend shapes : décalage = clé − clé relative, pondéré par le groupe de sommets de la clé ;
- matériaux : Principled BSDF (couleur/texture, alpha, rugosité/métal constants ou ORM via « Separate
  Color », normal map via « Normal Map »), surchargés par des propriétés personnalisées `pony_*` du
  matériau (cf. MATERIAL_PROPS).

Règles de sélection des objets [I] : un mesh est exporté s'il a un modificateur Armature visant
l'armature, n'est pas `hide_render` et n'a pas `pony_export = False`. Son nom USD = propriété `pony_mesh`
sinon le nom de l'objet (suffixe `.001` retiré).
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import bpy
import numpy as np

from . import conventions as cv
from . import rig, template
from .usd_writer import BlendShapeData, MaterialData, MeshData, SkeletonData, limit_influences

_SUFFIX = re.compile(r"\.\d{3}$")

# Propriétés personnalisées reconnues sur un matériau Blender (prioritaires sur les nœuds).
# Les chemins relatifs sont résolus par rapport au dossier `tex_root` (Pipeline/build/textures).
MATERIAL_PROPS = {
    "pony_base_color_tex": "texture de couleur (sRGB)",
    "pony_normal_tex": "normal map OpenGL (raw)",
    "pony_orm_tex": "texture ORM (R occlusion, G rugosité, B métal ; raw)",
    "pony_base_color": "couleur constante (r, g, b)",
    "pony_roughness": "rugosité constante",
    "pony_metallic": "métal constant",
    "pony_opacity_threshold": "seuil de découpe alpha (> 0 = cartes de crins)",
    "pony_opacity_from_alpha": "opacité = alpha de la texture de couleur (bool)",
    "pony_clearcoat": "vernis (0..1)",
    "pony_clearcoat_roughness": "rugosité du vernis",
    "pony_tint": "teinte par défaut (r, g, b) — utilisée seulement pour l'aperçu Quick Look",
}
# Alias acceptés (sans préfixe, camelCase « USD ») : roughness, metallic, opacityThreshold, clearcoat,
# clearcoatRoughness — le nom `pony_*` est prioritaire.


def clean_name(name: str) -> str:
    return _SUFFIX.sub("", name)


# --------------------------------------------------------------------------------------------------
# Armature
# --------------------------------------------------------------------------------------------------


def find_armature(name: str = rig.ARMATURE_NAME):
    """L'armature du poney : objet `name`, sinon l'unique armature du fichier."""
    if name in bpy.data.objects and bpy.data.objects[name].type == "ARMATURE":
        return bpy.data.objects[name]
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(arms) == 1:
        return arms[0]
    raise RuntimeError(f"armature introuvable : ni objet {name!r} ni armature unique (trouvé {[a.name for a in arms]})")


def check_armature(arm) -> list[str]:
    errs = []
    if np.abs(np.array(arm.matrix_world) - np.eye(4)).max() > 1e-6:
        errs.append(f"armature {arm.name} : transform objet ≠ identité (appliquer les transformations)")
    bones = set(arm.data.bones.keys())
    missing = [n for n in template.JOINT_NAMES if n not in bones]
    if missing:
        errs.append(f"armature {arm.name} : os manquants {missing[:10]}{'…' if len(missing) > 10 else ''}")
    for n in template.JOINT_NAMES:
        if n in bones:
            b = arm.data.bones[n]
            exp_parent = template.joint_table()[template.joint_index(n)]["parent"]
            got = b.parent.name if b.parent else None
            if got != exp_parent:
                errs.append(f"os {n} : parent {got} ≠ {exp_parent} (SPEC §3)")
            if b.inherit_scale != "FULL" or not b.use_inherit_rotation:
                errs.append(f"os {n} : héritage rotation/échelle non standard (UsdSkel compose les locales)")
            if not b.use_deform:
                errs.append(f"os {n} : non déformant (Blender ignorerait son groupe de sommets, USD non)")
    return errs


def extract_skeleton(arm) -> SkeletonData:
    return SkeletonData(names=list(template.JOINT_NAMES), parents=list(rig.PARENTS),
                        bind_world=rig.bind_world_rk(arm), rest_local=rig.rest_local_rk(arm))


def skinned_mesh_objects(arm) -> list:
    out = []
    for o in bpy.data.objects:
        if o.type != "MESH" or o.hide_render or o.get("pony_export", True) is False:
            continue
        if any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers):
            out.append(o)
    return sorted(out, key=lambda o: o.name)


def usd_mesh_name(obj) -> str:
    return str(obj.get("pony_mesh", clean_name(obj.name)))


def check_mesh_object(obj, arm) -> list[str]:
    errs = []
    for m in obj.modifiers:
        if not (m.show_viewport or m.show_render):
            continue
        if m.type != "ARMATURE":
            errs.append(f"{obj.name} : modificateur {m.type} « {m.name} » actif — appliquez-le avant l'export "
                        "(seul Armature est supporté, la topologie exportée est celle du mesh de base)")
        elif m.object == arm:
            if not m.use_vertex_groups or m.use_bone_envelopes or m.use_deform_preserve_volume or m.use_multi_modifier:
                errs.append(f"{obj.name} : Armature doit utiliser les groupes de sommets seuls (LBS, sans "
                            "enveloppes, sans « preserve volume »)")
            if m.invert_vertex_group or m.vertex_group:
                errs.append(f"{obj.name} : Armature avec groupe de masque — non supporté")
    arm_mods = [m for m in obj.modifiers if m.type == "ARMATURE" and m.object == arm]
    if len(arm_mods) != 1:
        errs.append(f"{obj.name} : {len(arm_mods)} modificateurs Armature visant {arm.name} (1 attendu)")
    if obj.data.shape_keys is not None and not obj.data.shape_keys.use_relative:
        errs.append(f"{obj.name} : shape keys absolues non supportées")
    return errs


# --------------------------------------------------------------------------------------------------
# Influences
# --------------------------------------------------------------------------------------------------


def read_weights(obj, joint_names: list[str]) -> np.ndarray:
    """(P, N) poids bruts des groupes qui portent un nom de joint."""
    index = {n: i for i, n in enumerate(joint_names)}
    g2j = {vg.index: index[vg.name] for vg in obj.vertex_groups if vg.name in index}
    W = np.zeros((len(obj.data.vertices), len(joint_names)), dtype=np.float64)
    for v in obj.data.vertices:
        for g in v.groups:
            j = g2j.get(g.group)
            if j is not None and g.weight > 0.0:
                W[v.index, j] += g.weight
    return W


def apply_influence_limit(obj, joint_names: list[str], k: int = 4) -> tuple[np.ndarray, np.ndarray, dict]:
    """Limite continue à k influences, normalise, et RÉÉCRIT les groupes de sommets de l'objet (en mémoire).
    Sommets sans aucun poids : liés rigidement à `root` (poids 1) — comme Blender qui ne les déforme pas
    tant que root reste au repos. Renvoie (indices (P,k), poids (P,k), statistiques)."""
    W = read_weights(obj, joint_names)
    P = len(W)
    nnz = (W > 0).sum(1)
    zero = nnz == 0
    W[zero, 0] = 1.0
    order = np.argsort(-W, axis=1, kind="stable")[:, :max(k + 1, 1)]
    vals = np.take_along_axis(W, order, axis=1)
    idx, w = limit_influences(order, vals, k)
    # écart de poids induit par la limitation (par rapport aux poids normalisés d'origine)
    Wn = W / W.sum(1, keepdims=True)
    Wl = np.zeros_like(W)
    np.add.at(Wl, (np.repeat(np.arange(P), idx.shape[1]), idx.ravel()), w.ravel())
    stats = {"vertices": int(P), "zeroWeightVertices": int(zero.sum()), "over4": int((nnz > k).sum()),
             "maxInfluencesBefore": int(nnz.max()) if P else 0,
             "maxWeightChange": float(np.abs(Wl - Wn).max()) if P else 0.0}
    # réécriture : tous les groupes de joints sont remplacés
    groups = {}
    for n in joint_names:
        vg = obj.vertex_groups.get(n)
        groups[n] = vg
    all_v = list(range(P))
    for n, vg in groups.items():
        if vg is not None:
            vg.remove(all_v)
    for j in np.unique(idx[w > 0]):
        n = joint_names[int(j)]
        vg = groups[n] or obj.vertex_groups.new(name=n)
        groups[n] = vg
        rows, cols = np.nonzero((idx == j) & (w > 0))
        for r, c in zip(rows.tolist(), cols.tolist()):
            vg.add([r], float(w[r, c]), "REPLACE")
    return idx, w, stats


# --------------------------------------------------------------------------------------------------
# Mesh
# --------------------------------------------------------------------------------------------------


def _normal_matrix(mw: np.ndarray) -> np.ndarray:
    return np.linalg.inv(mw[:3, :3]).T


def extract_mesh(obj, joint_names: list[str], influences=None, name: Optional[str] = None,
                 warnings: Optional[list] = None) -> tuple[MeshData, list]:
    """-> (MeshData en espace RK, matériaux Blender utilisés dans l'ordre de `material_names`)."""
    warnings = warnings if warnings is not None else []
    me = obj.data
    P = len(me.vertices)
    mw = np.array(obj.matrix_world, dtype=np.float64)
    keys = me.shape_keys
    co = np.empty(P * 3, np.float32)
    if keys is not None:
        keys.reference_key.data.foreach_get("co", co)
    else:
        me.vertices.foreach_get("co", co)
    base_b = co.reshape(P, 3).astype(np.float64)
    pts_w = base_b @ mw[:3, :3].T + mw[:3, 3]
    points = cv.vec_b2rk(pts_w)

    F = len(me.polygons)
    counts = np.empty(F, np.int32)
    me.polygons.foreach_get("loop_total", counts)
    L = len(me.loops)
    fidx = np.empty(L, np.int32)
    me.loops.foreach_get("vertex_index", fidx)
    starts = np.empty(F, np.int32)
    me.polygons.foreach_get("loop_start", starts)
    if not np.array_equal(starts, np.concatenate([[0], np.cumsum(counts)[:-1]]).astype(np.int32)):
        # boucles non contiguës dans l'ordre des faces : réordonner
        order = np.concatenate([np.arange(s, s + c) for s, c in zip(starts, counts)])
    else:
        order = None
    if order is not None:
        fidx = fidx[order]

    # normales de coins (Blender 4.1+ : Mesh.corner_normals) : respectent arêtes vives et normales
    # personnalisées. Mesh majoritairement à facettes (shade_smooth oublié) -> normales lissées calculées.
    smooth = np.empty(F, bool)
    me.polygons.foreach_get("use_smooth", smooth)
    if F and smooth.mean() < 0.5:
        warnings.append(f"{obj.name} : {100 * (1 - smooth.mean()):.0f} % de faces à facettes — normales lissées "
                        "calculées à l'export (appliquer shade_smooth dans Blender)")
        nrm = None                     # usd_writer calcule des normales lissées par sommet
    else:
        cn = np.empty(L * 3, np.float32)
        me.corner_normals.foreach_get("vector", cn)
        nrm = cn.reshape(L, 3).astype(np.float64) @ _normal_matrix(mw).T
        nrm = cv.vec_b2rk(nrm)
        if order is not None:
            nrm = nrm[order]

    uvs = None
    uvl = next((u for u in me.uv_layers if u.active_render), None) or (me.uv_layers[0] if len(me.uv_layers) else None)
    if uvl is None:
        warnings.append(f"{obj.name} : aucune carte UV")
    else:
        uv = np.empty(L * 2, np.float32)
        uvl.data.foreach_get("uv", uv)
        uvs = uv.reshape(L, 2).astype(np.float64)
        if order is not None:
            uvs = uvs[order]
        if len(me.uv_layers) > 1:
            warnings.append(f"{obj.name} : {len(me.uv_layers)} cartes UV, seule « {uvl.name} » est exportée (st)")

    mi = np.empty(F, np.int32)
    me.polygons.foreach_get("material_index", mi)
    slots = [s.material for s in obj.material_slots]
    used = sorted(set(mi.tolist()))
    if not slots:
        raise ValueError(f"{obj.name} : aucun matériau")
    mats, names = [], []
    for u in used:
        if u >= len(slots) or slots[u] is None:
            raise ValueError(f"{obj.name} : emplacement de matériau {u} vide")
        n = clean_name(slots[u].name)
        if n not in names:
            names.append(n)
            mats.append(slots[u])
    face_mat = np.array([names.index(clean_name(slots[u].name)) for u in mi], dtype=np.int32)

    if influences is None:
        W = read_weights(obj, joint_names)
        order_w = np.argsort(-W, axis=1)[:, :5]
        influences = limit_influences(order_w, np.take_along_axis(W, order_w, 1))
    ji, jw = influences

    shapes = []
    if keys is not None:
        ref = keys.reference_key
        for kb in keys.key_blocks:
            if kb == ref:
                continue
            kco = np.empty(P * 3, np.float32)
            kb.data.foreach_get("co", kco)
            rel = kb.relative_key
            rco = np.empty(P * 3, np.float32)
            rel.data.foreach_get("co", rco)
            off_b = (kco - rco).reshape(P, 3).astype(np.float64)
            if kb.vertex_group:
                vg = obj.vertex_groups.get(kb.vertex_group)
                m = np.zeros(P)
                if vg is not None:
                    for v in me.vertices:
                        for g in v.groups:
                            if g.group == vg.index:
                                m[v.index] = g.weight
                off_b *= m[:, None]
            if kb.mute:
                warnings.append(f"{obj.name} : shape key {kb.name} muette (exportée quand même)")
            off = cv.vec_b2rk(off_b @ mw[:3, :3].T)
            shapes.append(BlendShapeData(name=clean_name(kb.name), offsets=off))
    md = MeshData(name=name or usd_mesh_name(obj), points=points, face_counts=counts, face_indices=fidx,
                  joint_indices=ji, joint_weights=jw, material_names=names, face_materials=face_mat,
                  normals=nrm, uvs=uvs, blend_shapes=shapes)
    return md, mats


# --------------------------------------------------------------------------------------------------
# Matériaux
# --------------------------------------------------------------------------------------------------


def _upstream(socket, types, depth=6):
    """Premier nœud amont de type `types` (traverse reroutes et nœuds simples). -> (nœud, socket de sortie)."""
    if not socket.is_linked or depth <= 0:
        return None, None
    link = socket.links[0]
    node = link.from_node
    if node.type in types:
        return node, link.from_socket
    if node.type == "REROUTE":
        return _upstream(node.inputs[0], types, depth - 1)
    return None, None


def _image_png(img, work_dir: Path, warnings: list) -> str:
    """Chemin d'un PNG sur disque pour l'image Blender (copie/conversion dans work_dir si nécessaire)."""
    src = bpy.path.abspath(img.filepath) if img.filepath else ""
    if src and os.path.isfile(src) and src.lower().endswith(".png") and not img.packed_file and not img.is_dirty:
        return src
    work_dir.mkdir(parents=True, exist_ok=True)
    out = work_dir / (clean_name(Path(img.name).stem) + ".png")
    if src and os.path.isfile(src) and not img.packed_file:
        from PIL import Image
        Image.open(src).save(out)
    else:
        prev = (img.filepath_raw, img.file_format)
        img.filepath_raw = str(out)
        img.file_format = "PNG"
        img.save()
        img.filepath_raw, img.file_format = prev
    warnings.append(f"image {img.name} convertie/copiée en PNG : {out.name}")
    return str(out)


def _resolve(p, tex_root: Path) -> str:
    p = str(p)
    return p if os.path.isabs(p) else str(tex_root / p)


def extract_material(mat, tex_root: Path, work_dir: Path, warnings: list) -> MaterialData:
    md = MaterialData(name=clean_name(mat.name))
    orm_parts = {}
    if mat.use_nodes and mat.node_tree:
        nt = mat.node_tree
        out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
        bsdf, _ = _upstream(out.inputs["Surface"], {"BSDF_PRINCIPLED"}) if out else (None, None)
        if bsdf is None:
            warnings.append(f"matériau {mat.name} : pas de Principled BSDF relié à la sortie — valeurs par défaut")
        else:
            bc = bsdf.inputs["Base Color"]
            node, sock = _upstream(bc, {"TEX_IMAGE"})
            if node is not None and node.image is not None:
                md.base_color_texture = _image_png(node.image, work_dir, warnings)
                al = bsdf.inputs["Alpha"]
                an, asock = _upstream(al, {"TEX_IMAGE"})
                if an is not None and an.image == node.image and asock.name == "Alpha":
                    md.opacity_from_base_alpha = True
                elif an is not None:
                    warnings.append(f"matériau {mat.name} : alpha depuis une autre image — ignoré")
            elif bc.is_linked:
                warnings.append(f"matériau {mat.name} : Base Color reliée à un nœud non géré — couleur par défaut")
            else:
                md.base_color = tuple(float(c) for c in bc.default_value[:3])
            if not bsdf.inputs["Alpha"].is_linked:
                md.opacity = float(bsdf.inputs["Alpha"].default_value)
            for key, attr in (("Roughness", "roughness"), ("Metallic", "metallic")):
                s = bsdf.inputs[key]
                if s.is_linked:
                    sep, ssock = _upstream(s, {"SEPARATE_COLOR", "SEPRGB"})
                    if sep is not None:
                        img_node, _ = _upstream(sep.inputs[0], {"TEX_IMAGE"})
                        if img_node is not None and img_node.image is not None:
                            orm_parts[attr] = (img_node.image, ssock.name)
                            continue
                    img_node, _ = _upstream(s, {"TEX_IMAGE"})
                    if img_node is not None and img_node.image is not None:
                        orm_parts[attr] = (img_node.image, "gray")
                        continue
                    warnings.append(f"matériau {mat.name} : {key} relié à un nœud non géré — constante")
                setattr(md, attr, float(s.default_value))
            ns = bsdf.inputs["Normal"]
            nm, _ = _upstream(ns, {"NORMAL_MAP"})
            if nm is not None:
                if nm.space != "TANGENT":
                    warnings.append(f"matériau {mat.name} : normal map en espace {nm.space} (tangent attendu)")
                if abs(nm.inputs["Strength"].default_value - 1.0) > 1e-6:
                    warnings.append(f"matériau {mat.name} : force de normal map ≠ 1 (ignorée)")
                tn, _ = _upstream(nm.inputs["Color"], {"TEX_IMAGE"})
                if tn is not None and tn.image is not None:
                    md.normal_texture = _image_png(tn.image, work_dir, warnings)
            for key in ("Coat Weight", "Clearcoat"):
                if key in bsdf.inputs and not bsdf.inputs[key].is_linked and bsdf.inputs[key].default_value > 0:
                    md.clearcoat = float(bsdf.inputs[key].default_value)
                    rk = "Coat Roughness" if key == "Coat Weight" else "Clearcoat Roughness"
                    md.clearcoat_roughness = float(bsdf.inputs[rk].default_value)
            if "IOR" in bsdf.inputs and abs(bsdf.inputs["IOR"].default_value - 1.5) > 1e-3:
                md.ior = float(bsdf.inputs["IOR"].default_value)
    # ORM depuis des canaux d'image
    if orm_parts:
        imgs = {id(v[0]) for v in orm_parts.values()}
        r = orm_parts.get("roughness")
        m = orm_parts.get("metallic")
        if len(imgs) == 1 and (r is None or r[1] in ("Green", "G")) and (m is None or m[1] in ("Blue", "B")):
            md.orm_texture = _image_png(next(iter(orm_parts.values()))[0], work_dir, warnings)
        else:
            md.orm_texture = _pack_orm(md.name, orm_parts, md, work_dir, warnings)
    # surcharges par propriétés personnalisées
    if "pony_base_color_tex" in mat:
        md.base_color_texture = _resolve(mat["pony_base_color_tex"], tex_root)
    if "pony_normal_tex" in mat:
        md.normal_texture = _resolve(mat["pony_normal_tex"], tex_root)
    if "pony_orm_tex" in mat:
        md.orm_texture = _resolve(mat["pony_orm_tex"], tex_root)
    if "pony_base_color" in mat:
        md.base_color = tuple(float(c) for c in mat["pony_base_color"][:3])
    for keys, attr in ((("pony_roughness", "roughness"), "roughness"), (("pony_metallic", "metallic"), "metallic"),
                       (("pony_opacity_threshold", "opacityThreshold"), "opacity_threshold"),
                       (("pony_clearcoat", "clearcoat"), "clearcoat"),
                       (("pony_clearcoat_roughness", "clearcoatRoughness"), "clearcoat_roughness")):
        # les noms camelCase (indications « runtime » posées par d'autres agents, ex. M_Hair) sont des alias
        for key in keys:
            if key in mat:
                try:
                    setattr(md, attr, float(mat[key]))
                except (TypeError, ValueError):
                    warnings.append(f"matériau {mat.name} : propriété {key} non numérique ignorée")
                break
    if "pony_opacity_from_alpha" in mat:
        md.opacity_from_base_alpha = bool(mat["pony_opacity_from_alpha"])
    if "pony_opacity_threshold" not in mat and "opacityThreshold" not in mat and md.opacity_from_base_alpha:
        bm = getattr(mat, "blend_method", "OPAQUE")
        if bm == "CLIP":
            md.opacity_threshold = float(getattr(mat, "alpha_threshold", 0.5))
        else:
            md.opacity_threshold = 0.5   # [I] découpe plutôt que transparence (recommandation Apple, realitykit.md §5.1)
    if md.orm_texture and md.opacity_from_base_alpha:
        # une seule texture empaquetée par matériau (RealityKit) : on garde l'alpha, rugosité moyenne de l'ORM
        from PIL import Image
        g = np.asarray(Image.open(md.orm_texture).convert("RGB"), dtype=np.float64)[..., 1].mean() / 255.0
        warnings.append(f"matériau {md.name} : ORM abandonnée au profit de l'alpha (une seule texture "
                        f"empaquetée) ; rugosité constante {g:.2f}")
        md.orm_texture = None
        md.roughness = float(g)
    return md


def _pack_orm(name, parts, md: MaterialData, work_dir: Path, warnings: list) -> str:
    """Construit un PNG ORM (R=1 occlusion, G=rugosité, B=métal) depuis des images séparées."""
    from PIL import Image
    chans = {}
    size = None
    for attr, (img, ch) in parts.items():
        im = Image.open(_image_png(img, work_dir, warnings))
        size = size or im.size
        im = im.resize(size)
        if ch == "gray":
            a = np.asarray(im.convert("L"), dtype=np.uint8)
        else:
            a = np.asarray(im.convert("RGB"), dtype=np.uint8)[..., {"Red": 0, "R": 0, "Green": 1, "G": 1,
                                                                    "Blue": 2, "B": 2}.get(ch, 0)]
        chans[attr] = a
    h, w = size[1], size[0]
    o = np.full((h, w), 255, np.uint8)
    r = chans.get("roughness", np.full((h, w), int(round(md.roughness * 255)), np.uint8))
    m = chans.get("metallic", np.full((h, w), int(round(md.metallic * 255)), np.uint8))
    out = work_dir / f"{name}_orm.png"
    work_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.stack([o, r, m], -1)).save(out)
    warnings.append(f"matériau {name} : ORM empaquetée à partir d'images séparées -> {out.name}")
    return str(out)


def material_tint(mat) -> Optional[tuple]:
    return tuple(float(c) for c in mat["pony_tint"][:3]) if "pony_tint" in mat else None


# --------------------------------------------------------------------------------------------------
# Évaluation (validation numérique)
# --------------------------------------------------------------------------------------------------


def set_pose_and_shapes(arm, objs, local_b: np.ndarray, shape_weights: dict):
    rig.apply_local_pose(arm, local_b)
    for o in objs:
        ks = o.data.shape_keys
        if ks is None:
            continue
        for kb in ks.key_blocks:
            if kb != ks.reference_key:
                kb.slider_min = min(kb.slider_min, 0.0)
                kb.slider_max = max(kb.slider_max, 1.0)
                kb.value = float(shape_weights.get(clean_name(kb.name), 0.0))
    bpy.context.view_layer.update()


def evaluated_points_rk(objs) -> dict:
    """Positions évaluées (armature + shape keys) en espace RK, par nom de mesh USD."""
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        co = np.empty(len(me.vertices) * 3, np.float32)
        me.vertices.foreach_get("co", co)
        ev.to_mesh_clear()
        mw = np.array(o.matrix_world, dtype=np.float64)
        p = co.reshape(-1, 3).astype(np.float64) @ mw[:3, :3].T + mw[:3, 3]
        out[usd_mesh_name(o)] = cv.vec_b2rk(p)
    return out


def posed_locals_rk(arm) -> np.ndarray:
    """Locales RK de la pose courante évaluée (à passer à USD pour la comparaison)."""
    return rig.pose_local_rk(arm)


def validation_poses(arm, clip_locals: Optional[np.ndarray] = None, seed: int = 7) -> list[np.ndarray]:
    """K = 3 poses Blender (locales) : (0) repos, (1) une frame de clip si fournie sinon aléatoire douce,
    (2) aléatoire sur TOUS les joints (rotations ±25°, translations ±2 cm, échelle 1.25 sur head et ear_l —
    valeur exacte en demi-précision, car SkelAnimation.scales est en half3)."""
    rest_l = rig.locals_from_world(rig.rest_world_b(arm), to_rk=False)
    rng = np.random.default_rng(seed)

    def rnd(amp_deg, amp_t, scale=False):
        L = rest_l.copy()
        for i in range(len(L)):
            ax = rng.normal(size=3)
            ax /= np.linalg.norm(ax)
            a = np.radians(rng.uniform(-amp_deg, amp_deg))
            from .usd_writer import matrix_from_quat
            Rm = np.eye(4)
            Rm[:3, :3] = matrix_from_quat(np.r_[ax * np.sin(a / 2), np.cos(a / 2)])
            Tm = np.eye(4)
            Tm[:3, 3] = rng.uniform(-amp_t, amp_t, 3)
            L[i] = L[i] @ Tm @ Rm
        if scale:
            for n in ("head", "ear_l"):
                i = template.joint_index(n)
                L[i] = L[i] @ np.diag([1.25, 1.25, 1.25, 1.0])
        return L

    poses = [rest_l.copy()]
    poses.append(clip_locals.copy() if clip_locals is not None else rnd(12, 0.005))
    poses.append(rnd(25, 0.02, scale=True))
    return poses


def validation_shape_weights(names: list[str], k: int) -> dict:
    """Poids de blend shapes déterministes et non nuls pour la pose k."""
    rng = np.random.default_rng(100 + k)
    if k == 0:
        return {n: 0.5 for n in names}
    return {n: float(rng.uniform(0.0, 1.0)) for n in names}
