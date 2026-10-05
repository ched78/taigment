"""Aperçus des clips : planches contact et GIF animés (Blender Workbench, à lancer en sous-processus).

Usage (depuis `stages/s04_anim.py`, ou à la main) :
    python3 -m pony.anim.preview --clips walk,trot [--gif walk,trot] [--body auto|none] [--out DIR]

Rendu : armature construite par `rig.build_armature()`, pose appliquée image par image par
`rig.apply_local_pose` avec les transformations locales du `.npz` (donc exactement ce que reçoit l'export).
Géométrie affichée : « mannequin » (ellipsoïdes rigides par os, sabots en coin, cf. skeleton.MANNEQUIN)
+ `rig.make_bone_proxies` ; si `Pipeline/build/rigged_body.blend` existe, le vrai corps skinné est aussi
rendu (planche supplémentaire `<clip>_body.png`).
Le mouvement racine (rootVelocity, rootYawRate) est appliqué à l'objet armature sur un sol en damier
de 0,25 m : un sabot qui patine se voit glisser sur les cases.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from pony import conventions as cv  # noqa: E402
from pony import rig  # noqa: E402
from pony.anim import clip_io  # noqa: E402
from pony.anim.skeleton import LIMBS, HOOF, Skeleton, mannequin_ellipsoids  # noqa: E402

PREVIEW_DIR = cv.PREVIEW_DIR / "anim"
TILE = 0.25


def _mat(name, rgb):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1.0)
    m.use_nodes = False
    return m


def build_scene(sk: Skeleton):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    arm = rig.build_armature()
    # --- mannequin
    import bmesh
    me = bpy.data.meshes.new("Mannequin")
    obj = bpy.data.objects.new("Mannequin", me)
    scene.collection.objects.link(obj)
    bm = bmesh.new()
    vg_of_vert = []
    mat_of_face = []
    mats = {"body": 0, "left": 1, "right": 2, "hoof": 3, "head": 4}
    for j, c, r in mannequin_ellipsoids(sk):
        name = sk.names[j]
        Wj = sk.rest_world[j]
        res = bmesh.ops.create_uvsphere(bm, u_segments=14, v_segments=8, radius=1.0)
        verts = res["verts"]
        for v in verts:
            p = np.array(v.co) * r + c
            v.co = Vector((Wj[:3, :3] @ p) + Wj[:3, 3])
        key = "left" if name.endswith("_l") else "right" if name.endswith("_r") else \
            "head" if name in ("head", "ear_l", "ear_r") else "body"
        faces = {f for v in verts for f in v.link_faces}
        for f in faces:
            f.material_index = mats[key]
        vg_of_vert += [(v, j) for v in verts]
    # sabots : coin entre sole et couronne
    for limb in LIMBS:
        j = sk.idx(HOOF[limb])
        sole = sk.rest_sole_world(limb)       # 0 pince, 1/2 talons, 3/4 mamelles
        top = sk.head[j]
        pts = [sole[0], sole[3], sole[1], sole[2], sole[4]]
        base = [bm.verts.new(Vector(p)) for p in pts]
        c0 = np.mean(pts, axis=0)
        ctop = np.array([top[0], top[1] - 0.004, top[2] + 0.02])
        ring = [bm.verts.new(Vector(ctop + 0.72 * (np.array(p) - c0))) for p in pts]
        n = len(pts)
        fs = [bm.faces.new(base[::-1]), bm.faces.new(ring)]
        for i in range(n):
            fs.append(bm.faces.new((base[i], base[(i + 1) % n], ring[(i + 1) % n], ring[i])))
        for f in fs:
            f.material_index = mats["hoof"]
        vg_of_vert += [(v, j) for v in base + ring]
    bm.verts.index_update()
    bm.to_mesh(me)
    idx_of = {}
    for v, j in vg_of_vert:
        idx_of[v.index] = j
    bm.free()
    for n in sk.names:
        obj.vertex_groups.new(name=n)
    for vi, j in idx_of.items():
        obj.vertex_groups[sk.names[j]].add([vi], 1.0, "REPLACE")
    for p in me.polygons:
        p.use_smooth = True
    for key, rgb in (("body", (0.55, 0.36, 0.22)), ("left", (0.25, 0.14, 0.08)),
                     ("right", (0.86, 0.74, 0.52)), ("hoof", (0.08, 0.08, 0.08)),
                     ("head", (0.50, 0.33, 0.20))):
        me.materials.append(_mat(f"MQ_{key}", rgb))
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    obj.parent = arm
    prox = rig.make_bone_proxies(arm, radius=0.012)
    prox.data.materials.append(_mat("MQ_bones", (0.95, 0.85, 0.2)))
    prox.parent = arm
    prox.hide_render = True        # ajoutées pour inspection manuelle ; masquées dans les rendus

    # --- sol en damier
    ground = bpy.data.meshes.new("Checker")
    gobj = bpy.data.objects.new("Checker", ground)
    scene.collection.objects.link(gobj)
    bm = bmesh.new()
    nx, ny = 24, 160
    x0, y0 = -nx * TILE / 2, -20.0
    for i in range(nx):
        for k in range(ny):
            vs = [bm.verts.new((x0 + i * TILE + a, y0 + k * TILE + b, 0.0))
                  for a, b in ((0, 0), (TILE, 0), (TILE, TILE), (0, TILE))]
            f = bm.faces.new(vs)
            f.material_index = (i + k) % 2
    bm.to_mesh(ground)
    bm.free()
    ground.materials.append(_mat("Tile_a", (0.62, 0.62, 0.58)))
    ground.materials.append(_mat("Tile_b", (0.48, 0.49, 0.46)))

    # --- rendu
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_shadows = True
    scene.display.shading.shadow_intensity = 0.55
    scene.display.shading.show_cavity = False
    scene.display.render_aa = "8"
    scene.render.image_settings.file_format = "PNG"
    scene.world = bpy.data.worlds.new("W")
    scene.world.color = (0.75, 0.80, 0.86)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.lens = 45
    return arm, obj, cam


def look(cam, target, az_deg, el_deg, dist):
    a, e = math.radians(az_deg), math.radians(el_deg)
    # azimut 0 = côté gauche (−X) ; −90 = face (devant le nez, +Y) ; +90 = arrière (−Y)
    d = Vector((-math.cos(a) * math.cos(e), -math.sin(a) * math.cos(e), math.sin(e)))
    t = Vector(target)
    cam.location = t + d * dist
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()


def root_matrix(meta, t):
    """Transformation de l'entité (Blender) au temps t d'après rootVelocity / rootYawRate."""
    v_rk = np.array(meta["rootVelocity"])
    v = np.array([v_rk[0], -v_rk[2], v_rk[1]])          # RK -> Blender : (x, y, z)_RK = (x, z, −y)_B
    w = meta["rootYawRate"]
    if abs(w) < 1e-9:
        p = v * t
    else:
        s, c = math.sin(w * t), math.cos(w * t)
        p = np.array([(s * v[0] + (c - 1) * v[1]) / w, ((1 - c) * v[0] + s * v[1]) / w, 0.0])
    M = Matrix.Rotation(w * t, 4, "Z")
    M.translation = Vector(p)
    return M


def render_clip(name, arm, cam, clip_dir, out_dir, n_sheet=12, gif=False, views=("left",), size=(400, 300),
                cycles=2, frames=None):
    from PIL import Image, ImageDraw
    local, wnames, weights, meta = clip_io.load_npz(Path(clip_dir) / f"{name}.npz")
    F = local.shape[0]
    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = size
    tmp = Path(out_dir) / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    fps = meta["fps"]
    loop = meta["loop"]
    moving = abs(np.linalg.norm(meta["rootVelocity"])) > 1e-6 or abs(meta["rootYawRate"]) > 1e-6
    contacts = meta.get("_contacts")

    def pose_at(k, t):
        rig.apply_local_pose(arm, local[k % F])
        arm.matrix_world = root_matrix(meta, t) if moving else Matrix.Identity(4)
        bpy.context.view_layer.update()

    def cam_for(t, view):
        M = root_matrix(meta, t) if moving else Matrix.Identity(4)
        if abs(meta["rootYawRate"]) > 1e-6:
            target = (0.0, 0.0, 0.75)
        else:
            target = tuple(M.translation + Vector((0.0, 0.05, 0.75)))
        az, el, dist = {"left": (0, 8, 4.6), "side": (0, 0, 6.0), "three_quarter": (-38, 14, 4.8),
                        "front": (-90, 8, 4.6), "back3q": (40, 14, 4.8), "top": (-10, 60, 5.0)}[view]
        cam.data.type = "ORTHO" if view == "side" else "PERSP"
        cam.data.ortho_scale = 3.0
        if view == "side":
            target = (target[0], target[1], 0.68)
        look(cam, target, az, el, dist)

    # planche contact
    idx = np.linspace(0, F - (0 if not loop else 1), n_sheet, endpoint=not loop).round().astype(int)
    idx = np.clip(idx, 0, F - 1)
    if frames is not None:
        idx = np.array(frames)
    paths, labels = [], []
    for view in views:
        for k in idx:
            t = k / fps
            pose_at(k, t)
            cam_for(t, view)
            p = tmp / f"{name}_{view}_{k:03d}.png"
            scene.render.filepath = str(p)
            bpy.ops.render.render(write_still=True)
            paths.append(p)
            labels.append(f"{name} f{k} t={t:.2f}s")
    cols = 4
    ims = [Image.open(p).convert("RGB") for p in paths]
    w, h = ims[0].size
    rows = int(math.ceil(len(ims) / cols))
    sheet = Image.new("RGB", (cols * w, rows * h + 26), (25, 25, 25))
    d = ImageDraw.Draw(sheet)
    d.text((6, 6), f"{name} — {meta['frameCount']} images, {meta['duration']:.3f} s, loop={loop}, "
                   f"v={meta['rootVelocity']}, yaw={meta['rootYawRate']}", fill=(255, 255, 255))
    for i, im in enumerate(ims):
        x, y = (i % cols) * w, (i // cols) * h + 26
        sheet.paste(im, (x, y))
        d.rectangle([x, y, x + 7 * len(labels[i]) + 8, y + 15], fill=(0, 0, 0))
        d.text((x + 4, y + 2), labels[i], fill=(255, 255, 255))
    out = Path(out_dir) / (f"{name}.png" if frames is None else f"{name}_frames.png")
    sheet.save(out)
    res = [out]
    if gif:
        frames = []
        n = F * (cycles if loop else 1)
        for k in range(n):
            t = k / fps
            pose_at(k, t)
            cam_for(t, "left")
            p = tmp / f"{name}_gif_{k:03d}.png"
            scene.render.filepath = str(p)
            bpy.ops.render.render(write_still=True)
            frames.append(Image.open(p).convert("RGB").resize((size[0] * 3 // 4, size[1] * 3 // 4)))
        g = Path(out_dir) / f"{name}.gif"
        frames[0].save(g, save_all=True, append_images=frames[1:], duration=int(round(1000 / fps)), loop=0,
                       optimize=True)
        res.append(g)
    for p in tmp.glob(f"{name}_*.png"):
        p.unlink()
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", required=True)
    ap.add_argument("--gif", default="")
    ap.add_argument("--views", default="left")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--clip-dir", default=str(clip_io.CLIP_DIR))
    ap.add_argument("--out", default=str(PREVIEW_DIR))
    ap.add_argument("--size", default="400x300")
    ap.add_argument("--frames", default="", help="images précises (ex. 0,8,16) : planche dédiée")
    a = ap.parse_args(argv)
    sk, _ = Skeleton.from_blender()
    arm, obj, cam = build_scene(sk)
    gifs = set(filter(None, a.gif.split(",")))
    size = tuple(int(v) for v in a.size.split("x"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name in filter(None, a.clips.split(",")):
        fr = [int(v) for v in a.frames.split(",")] if a.frames else None
        r = render_clip(name, arm, cam, a.clip_dir, out, n_sheet=a.n, gif=name in gifs,
                        views=tuple(a.views.split(",")), size=size, frames=fr)
        print("[preview]", name, *[str(p) for p in r], flush=True)


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else None)
