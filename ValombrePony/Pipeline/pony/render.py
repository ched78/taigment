"""Rendus de prévisualisation headless (Cycles CPU + OIDN par défaut) et planches contact.

Mesures (Docs/research/blender.md) : Cycles 640² ≈ 5 s à 32 échantillons ; Workbench ≈ 0,3 s
(nécessite libegl1 + libegl-mesa0 ; un échec EGL tue le processus -> lancer Workbench/EEVEE dans un
sous-processus si l'environnement n'est pas garanti).
"""
from __future__ import annotations

import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

PREVIEW_COLLECTION = "PreviewStage"


def _stage_collection():
    if PREVIEW_COLLECTION in bpy.data.collections:
        return bpy.data.collections[PREVIEW_COLLECTION]
    col = bpy.data.collections.new(PREVIEW_COLLECTION)
    bpy.context.scene.collection.children.link(col)
    return col


def setup_stage(engine: str = "CYCLES", samples: int = 32, resolution=(640, 640), ground: bool = True,
                sun_dir=(-0.55, -0.35, -0.75), world_strength: float = 0.7):
    """Prépare caméra, lumières, sol et monde. Idempotent."""
    scene = bpy.context.scene
    col = _stage_collection()
    scene.render.engine = engine
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX" if "AgX" in [
        i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    if engine == "CYCLES":
        scene.cycles.device = "CPU"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        try:
            scene.cycles.denoiser = "OPENIMAGEDENOISE"
        except TypeError:
            pass
    elif engine == "BLENDER_WORKBENCH":
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"

    world = scene.world or bpy.data.worlds.new("PreviewWorld")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.62, 0.68, 0.75, 1.0)
        bg.inputs["Strength"].default_value = world_strength

    if "PreviewSun" not in bpy.data.objects:
        sun = bpy.data.lights.new("PreviewSun", "SUN")
        sun.energy = 3.2
        sun.angle = math.radians(4.0)
        so = bpy.data.objects.new("PreviewSun", sun)
        col.objects.link(so)
    so = bpy.data.objects["PreviewSun"]
    d = Vector(sun_dir).normalized()
    so.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

    if ground and "PreviewGround" not in bpy.data.objects:
        bpy.ops.mesh.primitive_plane_add(size=40.0, location=(0, 0, 0))
        g = bpy.context.active_object
        g.name = "PreviewGround"
        for c in g.users_collection:
            c.objects.unlink(g)
        col.objects.link(g)
        mat = bpy.data.materials.new("PreviewGroundMat")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (0.42, 0.40, 0.36, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.9
        g.data.materials.append(mat)

    if "PreviewCamera" not in bpy.data.objects:
        cam = bpy.data.cameras.new("PreviewCamera")
        cam.lens = 50
        co = bpy.data.objects.new("PreviewCamera", cam)
        col.objects.link(co)
    scene.camera = bpy.data.objects["PreviewCamera"]
    return scene


VIEWS = {
    # nom : (azimut en degrés autour de Z, 0 = vue de profil gauche ; élévation en degrés)
    "left": (0.0, 4.0),
    "right": (180.0, 4.0),
    "front": (-90.0, 6.0),
    "back": (90.0, 6.0),
    "three_quarter": (-40.0, 12.0),
    "three_quarter_back": (40.0, 12.0),
    "top": (0.0, 85.0),
    "head_close": (-55.0, 8.0),
}


def place_camera(view: str = "three_quarter", target=(0.0, 0.1, 0.8), distance: float = 4.2,
                 lens: float = 50.0):
    """Place la caméra autour de `target`. Azimut 0 = caméra côté gauche du poney (x < 0)."""
    az, el = VIEWS[view]
    cam = bpy.data.objects["PreviewCamera"]
    cam.data.lens = lens
    a, e = math.radians(az), math.radians(el)
    # côté gauche du poney = -X ; az tourne autour de Z
    direction = Vector((-math.cos(a) * math.cos(e), math.sin(a) * math.cos(e), math.sin(e)))
    t = Vector(target)
    cam.location = t + direction * distance
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    return cam


def render(path, view: str | None = None, **camera_kwargs):
    if view:
        place_camera(view, **camera_kwargs)
    scene = bpy.context.scene
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return path


def contact_sheet(paths, out_path, cols: int = 4, labels=None, cell=None, bg=(30, 30, 30)):
    """Assemble des images en planche (PIL), avec étiquettes optionnelles."""
    from PIL import Image, ImageDraw

    ims = [Image.open(p).convert("RGB") for p in paths]
    if not ims:
        return None
    w, h = cell or ims[0].size
    rows = int(math.ceil(len(ims) / cols))
    sheet = Image.new("RGB", (cols * w, rows * h), bg)
    draw = ImageDraw.Draw(sheet)
    for i, im in enumerate(ims):
        im = im.resize((w, h))
        x, y = (i % cols) * w, (i // cols) * h
        sheet.paste(im, (x, y))
        if labels:
            draw.rectangle([x, y, x + 8 * len(str(labels[i])) + 10, y + 18], fill=(0, 0, 0))
            draw.text((x + 5, y + 3), str(labels[i]), fill=(255, 255, 255))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return out_path


def simple_material(name: str, color=(0.55, 0.45, 0.38), roughness: float = 0.6):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def bounds_center(objs) -> np.ndarray:
    pts = []
    for o in objs:
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    p = np.array(pts)
    return (p.min(0) + p.max(0)) / 2
