"""Export GLB (aperçu web, optionnel) avec l'exporteur glTF de Blender 4.2.

Usage : depuis l'étape 9 (`s09_export.py --glb`) ou directement :
    export_preview_glb(build_dir, out_path, parts=[...], clips=[...])
Contenu : corps (`rigged_body.blend`) + pièces choisies (`parts/<id>.blend`, armature re-ciblée sur celle du
corps) + clips `clips/*.npz` convertis en actions Blender (une piste NLA par clip ; les poids de blend shapes
du clip sont posés sur une piste de shape keys de MÊME nom, que l'exporteur fusionne dans la même animation,
cf. Docs/research/blender.md §9).
Réglages (blender.md §9) : `export_apply=False` (sinon les shape keys sont perdues), 4 influences,
`shade_smooth` avant export (un mesh à facettes est éclaté par sommet : ×4 en taille).
Axes : glTF est Y haut ; `export_yup=True` applique (x, y, z)_B -> (x, z, −y), la même conversion que le SPEC §1
(le nez regarde −Z ; la convention glTF « l'avant regarde +Z » n'est PAS appliquée [I] : aperçu seulement).
Le GLB n'est pas livré dans le package Swift (aperçu web) : sortie par défaut `Pipeline/build/export/`.

Processus séparé : avec bpy 4.2 en module, l'interpréteur se termine par une erreur de segmentation APRÈS un
export glTF (observé ici : export complet et correct, puis code 139 à la fermeture). `run_in_subprocess`
lance donc l'export dans un processus enfant (`python3 -m pony.gltf_export ...`) qui imprime son résultat
puis quitte par `os._exit(0)`.
"""
from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import bpy
import numpy as np

from . import rig
from .usd_writer import decompose_trs_batch, make_quat_continuous

BODY_MESH_NAMES = {"Body", "Eyes", "Mouth", "Lashes"}
BODY_MATERIALS = {"M_Coat", "M_Eye", "M_Mouth", "M_Lashes"}


def _select_only(objs):
    bpy.context.view_layer.update()
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def append_part(path: Path, arm) -> list:
    """Ajoute les meshes skinnés d'une pièce à la scène courante, Armature re-ciblée sur `arm`."""
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    keep, drop = [], []
    for o in dst.objects:
        if o is None:
            continue
        mods = [m for m in getattr(o, "modifiers", []) if m.type == "ARMATURE"]
        mats = [s.material.name for s in getattr(o, "material_slots", []) if s.material]
        is_body = o.name.split(".")[0] in BODY_MESH_NAMES or any(m.split(".")[0] in BODY_MATERIALS for m in mats)
        if o.type == "MESH" and mods and not is_body and not o.hide_render and o.get("pony_export", True) is not False:
            for m in mods:
                m.object = arm
            o.name = f"{path.stem}__{o.name.split('.')[0]}"
            bpy.context.scene.collection.objects.link(o)
            keep.append(o)
        else:
            drop.append(o)
    for o in drop:
        bpy.data.objects.remove(o, do_unlink=True)
    return keep


def _fcurves(action, data_path, values, frames, group):
    """values (F, C) -> C fcurves linéaires."""
    for c in range(values.shape[1]):
        fc = action.fcurves.new(data_path, index=c, action_group=group)
        fc.keyframe_points.add(len(frames))
        co = np.empty(2 * len(frames), np.float32)
        co[0::2] = frames
        co[1::2] = values[:, c]
        fc.keyframe_points.foreach_set("co", co)
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.update()


def clips_to_actions(arm, clips, meshes) -> list[str]:
    """Une action d'armature (+ une action de shape keys par mesh concerné) par clip, chacune sur une piste
    NLA nommée comme le clip. `clips` : liste de runtime_export.ClipSource (locales Blender)."""
    rest_l = rig.locals_from_world(rig.rest_world_b(arm), to_rk=False)
    inv_rest = np.linalg.inv(rest_l)
    names = rig.joint_names()
    arm.animation_data_create()
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    out = []
    for clip in clips:
        F = clip.frame_count
        frames = np.arange(1, F + 1, dtype=np.float32)
        basis = inv_rest[None] @ clip.local_b
        T, R, S = decompose_trs_batch(basis)
        act = bpy.data.actions.new(clip.name)
        act.id_root = "OBJECT"
        for j, n in enumerate(names):
            q = make_quat_continuous(R[:, j])
            _fcurves(act, f'pose.bones["{n}"].location', T[:, j], frames, n)
            _fcurves(act, f'pose.bones["{n}"].rotation_quaternion', q[:, [3, 0, 1, 2]], frames, n)
            _fcurves(act, f'pose.bones["{n}"].scale', S[:, j], frames, n)
        tr = arm.animation_data.nla_tracks.new()
        tr.name = clip.name
        tr.strips.new(clip.name, 1, act)
        for o in meshes:
            ks = o.data.shape_keys
            if ks is None or not clip.weight_names:
                continue
            present = [n for n in clip.weight_names if n in ks.key_blocks]
            if not present:
                continue
            ka = bpy.data.actions.new(f"{clip.name}__{o.name}")
            ka.id_root = "KEY"
            for n in present:
                w = clip.weights[:, clip.weight_names.index(n)][:, None]
                _fcurves(ka, f'key_blocks["{n}"].value', w, frames, "shapes")
            ks.animation_data_create()
            t2 = ks.animation_data.nla_tracks.new()
            t2.name = clip.name
            t2.strips.new(clip.name, 1, ka)
        out.append(clip.name)
    arm.animation_data.action = None
    return out


def export_glb(out_path: Path, arm, meshes) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    for o in meshes:
        _select_only([o])
        bpy.ops.object.shade_smooth()
    _select_only([arm] + list(meshes))
    bpy.ops.export_scene.gltf(
        filepath=str(out_path), export_format="GLB", use_selection=True, export_animations=True,
        export_animation_mode="ACTIONS", export_skins=True, export_influence_nb=4, export_def_bones=False,
        export_morph=True, export_morph_normal=True, export_morph_animation=True, export_apply=False,
        export_yup=True, export_force_sampling=True, export_optimize_animation_size=True,
        export_lights=False, export_cameras=False)
    return out_path


def inspect_glb(path: Path) -> dict:
    """Lecture du chunk JSON du GLB (sans dépendance) : meshes, cibles de morphing, skins, animations."""
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise ValueError("en-tête GLB invalide")
    clen, ctype = struct.unpack_from("<II", data, 12)
    if ctype != 0x4E4F534A:
        raise ValueError("premier chunk non JSON")
    g = json.loads(data[20:20 + clen])
    meshes = []
    for m in g.get("meshes", []):
        prims = m.get("primitives", [])
        n_vert = sum(g["accessors"][p["attributes"]["POSITION"]]["count"] for p in prims)
        targets = (m.get("extras") or {}).get("targetNames", [])
        joints = all("JOINTS_0" in p["attributes"] and "JOINTS_1" not in p["attributes"] for p in prims)
        meshes.append({"name": m.get("name"), "vertices": n_vert, "morphTargets": targets, "joints4": joints})
    skins = [{"joints": len(s["joints"])} for s in g.get("skins", [])]
    anims = [{"name": a.get("name"), "channels": len(a.get("channels", []))} for a in g.get("animations", [])]
    return {"bytes": len(data), "meshes": meshes, "skins": skins, "animations": anims}


def export_preview_glb(build_dir: Path, out_path: Path, parts=None, clip_paths=None) -> dict:
    """Ouvre rigged_body.blend, ajoute les pièces, crée les actions, exporte et inspecte le GLB."""
    from . import blender_extract as bx
    from .runtime_export import load_clip_npz
    build_dir = Path(build_dir)
    bpy.ops.wm.open_mainfile(filepath=str(build_dir / "rigged_body.blend"), load_ui=False)
    arm = bx.find_armature()
    meshes = bx.skinned_mesh_objects(arm)
    for pid in parts or []:
        p = build_dir / "parts" / f"{pid}.blend"
        if p.is_file():
            meshes += append_part(p, arm)
    # mêmes influences que les USD (limitation continue à 4, sommets sans poids -> root) : sinon l'exporteur
    # glTF ajoute un joint « neutral_bone » et tronque lui-même à 4 influences
    names_j = rig.joint_names()
    for o in meshes:
        bx.apply_influence_limit(o, names_j, 4)
    clips = [load_clip_npz(p) for p in (clip_paths or [])]
    names = clips_to_actions(arm, clips, meshes)
    export_glb(out_path, arm, meshes)
    info = inspect_glb(out_path)
    info["clips"] = names
    return info


RESULT_MARK = "@@PONY_GLB@@"


def run_in_subprocess(build_dir: Path, out_path: Path, parts, clip_paths, timeout: int = 900) -> dict:
    """Exporte le GLB dans un processus enfant (cf. en-tête) et renvoie le résultat d'`inspect_glb`."""
    pipeline = Path(__file__).resolve().parent.parent
    args = json.dumps({"build_dir": str(build_dir), "out": str(out_path), "parts": list(parts or []),
                       "clips": [str(p) for p in (clip_paths or [])]})
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pipeline) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run([sys.executable, "-m", "pony.gltf_export", args], cwd=str(pipeline), env=env,
                          capture_output=True, text=True, timeout=timeout)
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_MARK):
            res = json.loads(line[len(RESULT_MARK):])
            if "error" in res:
                raise RuntimeError(res["error"])
            return res
    raise RuntimeError(f"export GLB sans résultat (code {proc.returncode}) : {proc.stderr[-1500:]}")


if __name__ == "__main__":
    a = json.loads(sys.argv[1])
    try:
        r = export_preview_glb(Path(a["build_dir"]), Path(a["out"]), a["parts"], [Path(p) for p in a["clips"]])
    except Exception as e:  # noqa: BLE001
        r = {"error": f"{type(e).__name__}: {e}"}
    print(RESULT_MARK + json.dumps(r), flush=True)
    sys.stderr.flush()
    os._exit(0)
