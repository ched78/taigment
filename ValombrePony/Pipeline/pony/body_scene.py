"""Scène Blender du corps : objets `Body`, `Body_high` (caché), `Eyes`, `Mouth`, `Lashes`, armature `PonyRig`,
matériaux `M_Coat`, `M_Eye`, `M_Mouth`, `M_Lashes` ; rendus de prévisualisation.

Matériaux : Principled BSDF (aperçu Blender) + propriétés `pony_*` lues par l'export (blender_extract) :
chemins de textures relatifs à Pipeline/build/textures/.
"""
from __future__ import annotations

import math
from pathlib import Path

import bpy
import numpy as np

from . import conventions as cv


# ==============================================================================================
# Maillages
# ==============================================================================================
def mesh_object(name, V, faces, face_uv=None, smooth=True, collection=None):
    V = np.asarray(V, np.float32)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.ravel())
    sizes = np.array([len(f) for f in faces], np.int32)
    loops = np.concatenate([np.asarray(f, np.int32) for f in faces])
    me.loops.add(len(loops))
    me.loops.foreach_set("vertex_index", loops)
    me.polygons.add(len(faces))
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(np.int32)
    me.polygons.foreach_set("loop_start", starts)
    me.update(calc_edges=True)
    if face_uv is not None:
        uvl = me.uv_layers.new(name="UVMap")
        uv = np.concatenate([np.asarray(u, np.float32).reshape(-1, 2) for u in face_uv])
        uvl.data.foreach_set("uv", uv.ravel())
    me.polygons.foreach_set("use_smooth", np.full(len(faces), smooth, bool))
    me.validate()
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def bm_to_object(bm, name, collection=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), bool))
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def read_mesh(ob):
    """(V, VN, faces, face_uv) depuis un objet Blender (normales de sommet lissées)."""
    me = ob.data
    n = len(me.vertices)
    V = np.zeros(n * 3)
    me.vertices.foreach_get("co", V)
    VN = np.zeros(n * 3)
    me.vertices.foreach_get("normal", VN)
    ls = np.zeros(len(me.polygons), np.int64)
    lt = np.zeros(len(me.polygons), np.int64)
    me.polygons.foreach_get("loop_start", ls)
    me.polygons.foreach_get("loop_total", lt)
    lv = np.zeros(len(me.loops), np.int64)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    faces = [lv[s:s + t] for s, t in zip(ls, lt)]
    fuv = [uv[s:s + t] for s, t in zip(ls, lt)]
    return V.reshape(-1, 3), VN.reshape(-1, 3), faces, fuv


def add_point_attribute(ob, name, values):
    me = ob.data
    if name in me.attributes:
        me.attributes.remove(me.attributes[name])
    at = me.attributes.new(name, "FLOAT", "POINT")
    at.data.foreach_set("value", np.asarray(values, np.float32))


# ==============================================================================================
# Matériaux
# ==============================================================================================
def _image(path, colorspace):
    path = Path(path)
    img = bpy.data.images.load(str(path), check_existing=True)
    img.colorspace_settings.name = colorspace
    return img


def _principled(name):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        bpy.data.materials.remove(mat)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    return mat, nt, bsdf


def coat_material(tex_dir, albedo="coat_albedo_default.png", preview_albedo="coat_albedo_preview.png"):
    """M_Coat : albedo (défaut de l'agent robe s'il existe, sinon aperçu), normal map OpenGL, ORM."""
    tex_dir = Path(tex_dir)
    mat, nt, bsdf = _principled("M_Coat")
    alb = tex_dir / albedo if (tex_dir / albedo).exists() else tex_dir / preview_albedo
    n_img = nt.nodes.new("ShaderNodeTexImage")
    n_img.location = (-700, 300)
    if alb.exists():
        n_img.image = _image(alb, "sRGB")
    nt.links.new(n_img.outputs["Color"], bsdf.inputs["Base Color"])
    if (tex_dir / "coat_orm.png").exists():
        o_img = nt.nodes.new("ShaderNodeTexImage")
        o_img.location = (-700, 0)
        o_img.image = _image(tex_dir / "coat_orm.png", "Non-Color")
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        sep.location = (-400, 0)
        nt.links.new(o_img.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    if (tex_dir / "coat_normal.png").exists():
        nm_img = nt.nodes.new("ShaderNodeTexImage")
        nm_img.location = (-700, -300)
        nm_img.image = _image(tex_dir / "coat_normal.png", "Non-Color")
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.location = (-400, -300)
        nt.links.new(nm_img.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.78
    mat["pony_base_color_tex"] = albedo
    mat["pony_normal_tex"] = "coat_normal.png"
    mat["pony_orm_tex"] = "coat_orm.png"
    mat["pony_metallic"] = 0.0
    mat.diffuse_color = (0.42, 0.24, 0.13, 1.0)
    return mat


def eye_material(tex_dir):
    tex_dir = Path(tex_dir)
    mat, nt, bsdf = _principled("M_Eye")
    p = tex_dir / "iris_default.png"
    if p.exists():
        n_img = nt.nodes.new("ShaderNodeTexImage")
        n_img.image = _image(p, "sRGB")
        nt.links.new(n_img.outputs["Color"], bsdf.inputs["Base Color"])
    else:
        bsdf.inputs["Base Color"].default_value = (0.10, 0.05, 0.03, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.25
    for nm in ("Coat Weight", "Clearcoat"):
        if nm in bsdf.inputs:
            bsdf.inputs[nm].default_value = 1.0
    for nm in ("Coat Roughness", "Clearcoat Roughness"):
        if nm in bsdf.inputs:
            bsdf.inputs[nm].default_value = 0.03
    mat["pony_base_color_tex"] = "iris_default.png"
    mat["pony_roughness"] = 0.25
    mat["pony_metallic"] = 0.0
    mat["pony_clearcoat"] = 1.0
    mat["pony_clearcoat_roughness"] = 0.03
    mat.diffuse_color = (0.08, 0.05, 0.04, 1.0)
    return mat


def simple_tex_material(name, tex_dir, tex, roughness, alpha=False, threshold=0.0):
    tex_dir = Path(tex_dir)
    mat, nt, bsdf = _principled(name)
    n_img = nt.nodes.new("ShaderNodeTexImage")
    n_img.image = _image(tex_dir / tex, "sRGB")
    nt.links.new(n_img.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    mat["pony_base_color_tex"] = tex
    mat["pony_roughness"] = roughness
    mat["pony_metallic"] = 0.0
    if alpha:
        nt.links.new(n_img.outputs["Alpha"], bsdf.inputs["Alpha"])
        mat.blend_method = "HASHED"
        mat["pony_opacity_from_alpha"] = True
        mat["pony_opacity_threshold"] = threshold
    return mat


# ==============================================================================================
# Prévisualisations
# ==============================================================================================
def preview_coat_material(tex_dir, albedo_name):
    """Matériau d'aperçu : albedo donné + vraies cartes normal / ORM (AO multipliée sur la couleur)."""
    tex_dir = Path(tex_dir)
    mat, nt, bsdf = _principled("M_CoatPreview")
    n_img = nt.nodes.new("ShaderNodeTexImage")
    n_img.image = _image(tex_dir / albedo_name, "sRGB")
    o_img = nt.nodes.new("ShaderNodeTexImage")
    o_img.image = _image(tex_dir / "coat_orm.png", "Non-Color")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(o_img.outputs["Color"], sep.inputs["Color"])
    mul = nt.nodes.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 1.0
    nt.links.new(n_img.outputs["Color"], mul.inputs[6])
    nt.links.new(sep.outputs["Red"], mul.inputs[7])
    nt.links.new(mul.outputs[2], bsdf.inputs["Base Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nm_img = nt.nodes.new("ShaderNodeTexImage")
    nm_img.image = _image(tex_dir / "coat_normal.png", "Non-Color")
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(nm_img.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = 0.25
    return mat
