"""Cuissons Cycles (CPU, sans GPU) : normales haute → basse définition (espace tangent OpenGL, +Y), occlusion
ambiante du maillage basse définition. Cf. Docs/research/blender.md §5 (mesures : normales 2048² ≈ 7 s pour
290 k faces ; le nombre d'échantillons n'influe pas sur les normales).

Convention : Blender cuit les normales en espace tangent « OpenGL » (Y+ = direction +v des UV), ce qui est la
convention du SPEC §4 (normal maps OpenGL). Les tableaux renvoyés ont la ligne 0 EN HAUT (ordre PIL), c.-à-d.
v = 1 en ligne 0.
"""
from __future__ import annotations

import time

import bpy
import numpy as np


def _bake_image(name, size, float_buffer=True):
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=float_buffer)
    img.colorspace_settings.name = "Non-Color"
    return img


def _target_material(ob, img):
    mat = bpy.data.materials.new("_BakeTarget")
    mat.use_nodes = True
    nt = mat.node_tree
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    nt.nodes.active = node
    saved = [s.material for s in ob.material_slots]
    ob.data.materials.clear()
    ob.data.materials.append(mat)
    return mat, saved


def _restore(ob, mat, saved):
    ob.data.materials.clear()
    for m in saved:
        ob.data.materials.append(m)
    bpy.data.materials.remove(mat)


def _select(active, others=()):
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        if o is not None:
            o.select_set(False)
    for o in others:
        o.select_set(True)
    active.select_set(True)
    bpy.context.view_layer.objects.active = active


def _pixels(img, size):
    a = np.empty(size * size * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(size, size, 4)[::-1].copy()       # ligne 0 = haut


def _cycles(samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = False
    return sc


def bake_normals(low, high, size=2048, cage_extrusion=0.008, max_ray=0.02, margin=16, log=print):
    """Normales tangentes (OpenGL) de `high` cuites sur les UV de `low`. Renvoie (size,size,3) dans [0,1]."""
    t0 = time.perf_counter()
    _cycles(1)
    img = _bake_image("_bake_normal", size)
    mat, saved = _target_material(low, img)
    hide = high.hide_render
    high.hide_render = False
    _select(low, [high])
    bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT", normal_r="POS_X", normal_g="POS_Y",
                        normal_b="POS_Z", use_selected_to_active=True, cage_extrusion=cage_extrusion,
                        max_ray_distance=max_ray, margin=margin, use_clear=True)
    out = _pixels(img, size)[..., :3]
    high.hide_render = hide
    _restore(low, mat, saved)
    bpy.data.images.remove(img)
    log(f"[bake] normales {size}² en {time.perf_counter() - t0:.1f}s")
    return out


def bake_ao(low, size=1024, samples=32, distance=0.30, margin=16, hide=(), log=print):
    """Occlusion ambiante du maillage `low` sur lui-même (distance AO en m). Renvoie (size,size) dans [0,1]."""
    t0 = time.perf_counter()
    sc = _cycles(samples)
    world = sc.world or bpy.data.worlds.new("BakeWorld")
    sc.world = world
    world.light_settings.distance = distance
    img = _bake_image("_bake_ao", size)
    mat, saved = _target_material(low, img)
    states = [(o, o.hide_render) for o in hide]
    for o in hide:
        o.hide_render = True
    _select(low)
    bpy.ops.object.bake(type="AO", use_selected_to_active=False, margin=margin, use_clear=True)
    out = _pixels(img, size)[..., 0]
    for o, s in states:
        o.hide_render = s
    _restore(low, mat, saved)
    bpy.data.images.remove(img)
    log(f"[bake] AO {size}² ({samples} éch.) en {time.perf_counter() - t0:.1f}s")
    return out
