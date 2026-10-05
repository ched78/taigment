"""Données runtime de PonyKit : `PonyRig.json` et `PonyClips.bin` (Docs/SPEC.md §9), plus un lecteur
Python de `PonyClips.bin` (aller-retour testé par validate.py).

Module indépendant de bpy. Entrées :
- squelette (`usd_writer.SkeletonData`, espace RealityKit) ;
- clips `Pipeline/build/clips/<nom>.npz` produits par l'agent « clips » :
    `local`        (F, 70, 4, 4)  transformations LOCALES Blender (parent->enfant ; pour `root` = monde Blender)
    `weights_names` (W,)          noms de blend shapes animés (optionnel)
    `weights`       (F, W)        poids (optionnel)
    `meta`          chaîne JSON   {name, loop, fps, duration, rootVelocity | speed, rootYawRate, mask, events,
                                   phaseOffset} — toutes les clés sont optionnelles (valeurs par défaut ci-dessous).
- catalogue des pièces (SPEC §6, recopié dans PART_CATALOG) et descriptions de pièces exportées.

Conversion d'espace (SPEC §1) : les locales parent->enfant sont IDENTIQUES en Blender et en RealityKit ;
seule la locale de `root` vaut C·L (C = conventions.C4). Quaternions écrits [x, y, z, w].

Conventions de ce module, à partager avec PonyCore (choix d'ingénierie [I], le SPEC ne les fixe pas) :
- `duration` : celle du `meta` si fournie, sinon frameCount/fps pour une boucle (la frame frameCount
  serait la frame 0) et (frameCount−1)/fps sinon ;
- `mask` dans le JSON : null (corps entier) ou LISTE EXPLICITE de noms de joints (les masques nommés du
  `meta` — "upper_body", "upper_body_flanks" — sont résolus ici) ;
- pistes : pour un clip non masqué, un joint (ou un canal T/R/S) égal au repos sur toutes les frames est
  omis (« absent = repos ») ; pour un clip masqué, tous les joints du masque ont leurs 3 canaux ;
  un canal constant est stocké une fois (bits 3/4/5) ;
- `requires` d'une pièce : liste de pièces dont AU MOINS UNE doit être portée (« selle » = anglaise ou western) ;
  un seul accessoire par emplacement (`slots`) ; `slot` = premier emplacement (compatibilité avec l'exemple du SPEC).
"""
from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from . import conventions as cv
from . import template
from .usd_writer import (SkeletonData, compose_trs_batch, decompose_trs, decompose_trs_batch,
                         make_quat_continuous)

MAGIC = b"PNYC"
VERSION = 1
FLAG_T, FLAG_R, FLAG_S, FLAG_T_CONST, FLAG_R_CONST, FLAG_S_CONST = 1, 2, 4, 8, 16, 32
T_EPS = 1e-6          # m
S_EPS = 1e-6
R_EPS = 1e-6          # rad (angle entre quaternions)

# --- noms figés du SPEC --------------------------------------------------------------------------------
MORPH_SHAPES = ["shape_stocky", "shape_refined", "shape_fat", "shape_thin", "shape_muscular", "shape_belly",
                "shape_crest", "shape_bone_heavy", "head_dished", "head_roman", "head_short", "muzzle_broad",
                "hooves_large"]
PROP_SHAPES = ["prop_legs_long", "prop_legs_short", "prop_neck_long", "prop_neck_short", "prop_body_long",
               "prop_body_short"]
FACE_SHAPES = ["face_nostril_flare", "face_flehmen", "face_brow_worry", "face_mouth_open_soft", "body_breathe"]
BODY_BLEND_SHAPES = MORPH_SHAPES + PROP_SHAPES + FACE_SHAPES

CLIP_NAMES = ["idle", "idle_rest_hind", "walk", "trot", "canter_left", "canter_right", "gallop", "back",
              "turn_left", "turn_right", "jump_takeoff", "jump_air", "jump_land", "graze_down", "graze_loop",
              "graze_up", "rear", "head_shake", "neigh", "paw", "lie_down", "lying", "get_up", "roll",
              "body_shake"]
# Clés du `meta` des clips recopiées telles quelles dans PonyRig.json (utiles au runtime : pivot des virages,
# appuis par image pour le verrouillage des pieds, synchronisation de phase des allures). [I]
CLIP_META_PASSTHROUGH = ["rootPivot", "contacts", "strideLength", "strideDuration", "stridesPerClip", "footfalls"]
EVENT_RE = re.compile(r"^((foot_down|foot_up)_(fl|fr|hl|hr)|takeoff|apex|landing|chew|snort)$")

# Régions du pelage (SPEC §4, coat_regions.R / 16). AG/AD/PG/PD = antérieur/postérieur gauche/droit.
COAT_REGIONS = ["body", "head", "muzzle", "ear_outer", "ear_inner", "leg_fl", "leg_fr", "leg_hl", "leg_hr",
                "hoof_fl", "hoof_fr", "hoof_hl", "hoof_hr", "chestnut_ergot", "eye_skin", "belly_skin"]
COAT_RUNTIME_MAPS = {"shading": "coat_shading.png", "regions": "coat_regions.png",
                     "params": "coat_params.png", "patterns": "coat_patterns.png"}
COAT_USD_MAPS = {"albedoDefault": "coat_albedo_default.png", "normal": "coat_normal.png", "orm": "coat_orm.png"}

# Masques nommés [I] (SPEC §7 : head_shake = haut du corps ; neigh = haut du corps + flancs).
_UPPER = ([f"neck_{i:02d}" for i in range(1, 7)] + ["head", "jaw", "lip_lower", "lip_upper", "ear_l", "ear_tip_l",
          "ear_r", "ear_tip_r", "eye_l", "eyelid_upper_l", "eyelid_lower_l", "eye_r", "eyelid_upper_r",
          "eyelid_lower_r"] + [f"forelock_{i:02d}" for i in range(1, 4)] + [f"mane_{i:02d}" for i in range(1, 7)])
NAMED_MASKS = {"upper_body": _UPPER, "upper_body_flanks": _UPPER + ["belly"]}

MATERIAL_SLOTS = ["slot_primary", "slot_secondary", "slot_accent", "slot_metal"]

# Catalogue des pièces (SPEC §6). materialSlots dans l'ordre des colonnes « Slots » du SPEC.
_S = MATERIAL_SLOTS
_SADDLES = ["saddle_english", "saddle_western"]
_HEADGEAR = ["bridle_snaffle", "halter"]
PART_CATALOG: dict[str, dict] = {
    "mane_natural": dict(category="hair", slots=["mane"], materialSlots=_S[:1]),
    "mane_braided": dict(category="hair", slots=["mane"], materialSlots=_S[:1]),
    "mane_roached": dict(category="hair", slots=["mane"], materialSlots=_S[:1]),
    "forelock_natural": dict(category="hair", slots=["forelock"], materialSlots=_S[:1]),
    "forelock_braided": dict(category="hair", slots=["forelock"], materialSlots=_S[:1]),
    "tail_natural": dict(category="hair", slots=["tail"], materialSlots=_S[:1]),
    "tail_braided": dict(category="hair", slots=["tail"], materialSlots=_S[:1]),
    "feathers": dict(category="hair", slots=["feathers"], materialSlots=_S[:1]),
    "saddle_english": dict(category="tack", slots=["saddle"], materialSlots=_S, conflicts=["rug_stable", "fly_sheet"]),
    "saddle_western": dict(category="tack", slots=["saddle"], materialSlots=_S, conflicts=["rug_stable", "fly_sheet"]),
    "saddle_pad_english": dict(category="tack", slots=["pad"], materialSlots=_S[:3], fabricSlots=["slot_primary"],
                               requires=["saddle_english"]),
    "saddle_pad_western": dict(category="tack", slots=["pad"], materialSlots=_S[:2], fabricSlots=["slot_primary"],
                               requires=["saddle_western"]),
    "bridle_snaffle": dict(category="tack", slots=["headgear"], materialSlots=["slot_primary", "slot_secondary", "slot_metal"],
                           conflicts=["halter"]),
    "halter": dict(category="tack", slots=["headgear"], materialSlots=["slot_primary", "slot_metal", "slot_secondary"],
                   conflicts=["bridle_snaffle"]),
    "breastplate": dict(category="tack", slots=["breastplate"], materialSlots=["slot_primary", "slot_metal"],
                        requires=_SADDLES),
    "boots_brushing": dict(category="protection", slots=["legs_front", "legs_hind"], materialSlots=_S[:3],
                           conflicts=["bandages"]),
    "boots_bell": dict(category="protection", slots=["hooves_front"], materialSlots=_S[:1]),
    "bandages": dict(category="protection", slots=["legs_front", "legs_hind"], materialSlots=_S[:1],
                     fabricSlots=["slot_primary"], conflicts=["boots_brushing"]),
    # [I] « se porte avec bridle_snaffle ou halter » interprété comme compatibilité, pas comme prérequis.
    "fly_bonnet": dict(category="protection", slots=["ears"], materialSlots=_S[:2], fabricSlots=["slot_primary"]),
    "ribbons_mane": dict(category="decorative", slots=["mane_deco"], materialSlots=_S[:1], requires=["mane_braided"]),
    "pompons": dict(category="decorative", slots=["mane_deco"], materialSlots=_S[:1], requires=["mane_braided"]),
    "flowers": dict(category="decorative", slots=["head_deco"], materialSlots=_S[:2]),
    "plume": dict(category="decorative", slots=["head_deco"], materialSlots=_S[:2], requires=_HEADGEAR),
    "tail_bow": dict(category="decorative", slots=["tail_deco"], materialSlots=_S[:1]),
    "rug_stable": dict(category="rug", slots=["rug"], materialSlots=_S[:3], fabricSlots=["slot_primary"],
                       conflicts=_SADDLES + ["quarter_sheet"], hides=["tail_bow"]),
    "fly_sheet": dict(category="rug", slots=["rug"], materialSlots=_S[:2], fabricSlots=["slot_primary"],
                      conflicts=_SADDLES + ["quarter_sheet"], hides=["tail_bow"]),
    "quarter_sheet": dict(category="rug", slots=["quarter"], materialSlots=_S[:2], fabricSlots=["slot_primary"],
                          requires=_SADDLES),
}


def _r(x, nd=7):
    """Arrondi pour le JSON (précision float32)."""
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_r(v, nd) for v in x]
    v = float(x)
    return 0.0 if abs(v) < 1e-12 else float(f"{v:.{nd}g}")


# --------------------------------------------------------------------------------------------------
# Clips
# --------------------------------------------------------------------------------------------------


@dataclass
class ClipSource:
    name: str
    local_b: np.ndarray                    # (F, N, 4, 4) locales Blender
    weight_names: list[str] = field(default_factory=list)
    weights: Optional[np.ndarray] = None   # (F, W)
    meta: dict = field(default_factory=dict)

    @property
    def fps(self) -> float:
        return float(self.meta.get("fps", cv.FPS))

    @property
    def loop(self) -> bool:
        return bool(self.meta.get("loop", False))

    @property
    def frame_count(self) -> int:
        return int(self.local_b.shape[0])


def load_clip_npz(path) -> ClipSource:
    path = Path(path)
    with np.load(path, allow_pickle=False) as z:
        if "local" not in z.files:
            raise ValueError(f"{path.name} : tableau `local` absent (attendu (F,70,4,4))")
        local = np.array(z["local"], dtype=np.float64)
        meta = {}
        if "meta" in z.files:
            raw = z["meta"]
            raw = raw.item() if raw.shape == () else raw.tolist()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            if isinstance(raw, list):
                raw = "".join(raw) if all(isinstance(s, str) for s in raw) else raw[0]
            meta = json.loads(raw) if isinstance(raw, str) and raw.strip() else {}
        names = [str(s) for s in z["weights_names"].tolist()] if "weights_names" in z.files else []
        weights = np.array(z["weights"], dtype=np.float64) if "weights" in z.files else None
    if local.ndim != 4 or local.shape[1:] != (len(template.JOINT_NAMES), 4, 4):
        raise ValueError(f"{path.name} : `local` de forme {local.shape}, attendu (F,{len(template.JOINT_NAMES)},4,4)")
    if not np.all(np.isfinite(local)):
        raise ValueError(f"{path.name} : valeurs non finies dans `local`")
    if names:
        if weights is None or weights.shape != (local.shape[0], len(names)):
            raise ValueError(f"{path.name} : `weights` doit être (F={local.shape[0]}, W={len(names)})")
    name = str(meta.get("name", path.stem))
    return ClipSource(name=name, local_b=local, weight_names=names, weights=weights, meta=meta)


def clip_locals_rk(local_b: np.ndarray) -> np.ndarray:
    """(F,N,4,4) locales Blender -> RK : seule la racine change (C·L)."""
    out = np.array(local_b, dtype=np.float64)
    out[:, 0] = cv.C4 @ out[:, 0]
    return out


def resolve_mask(mask, joint_names: list[str]) -> Optional[list[str]]:
    if mask in (None, "", "none", "full", "full_body"):
        return None
    if isinstance(mask, str):
        if mask not in NAMED_MASKS:
            raise ValueError(f"masque inconnu {mask!r} (connus : {sorted(NAMED_MASKS)} ou liste de joints)")
        mask = NAMED_MASKS[mask]
    mask = [str(m) for m in mask]
    unknown = [m for m in mask if m not in joint_names]
    if unknown:
        raise ValueError(f"masque : joints inconnus {unknown}")
    return [n for n in joint_names if n in set(mask)]   # ordre du squelette


@dataclass
class Track:
    joint: int
    flags: int
    t: Optional[np.ndarray] = None     # (1|F, 3)
    r: Optional[np.ndarray] = None     # (1|F, 4) x,y,z,w
    s: Optional[np.ndarray] = None     # (1|F, 3)


@dataclass
class ClipBinary:
    name: str
    fps: float
    frame_count: int
    tracks: list[Track]
    weights: list[tuple[str, np.ndarray]]   # (nom, (F,))


def _quat_angle(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = np.clip(np.abs(np.sum(a * b, axis=-1)), 0.0, 1.0)
    return 2.0 * np.arccos(d)


def decompose_clip(local_rk: np.ndarray):
    """(F,N,4,4) -> T (F,N,3), R (F,N,4) continus en signe, S (F,N,3)."""
    T, R, S = decompose_trs_batch(local_rk)
    for j in range(R.shape[1]):
        R[:, j] = make_quat_continuous(R[:, j])
    return T, R, S


def build_clip_binary(clip: ClipSource, skeleton: SkeletonData, warnings: list) -> tuple[ClipBinary, dict]:
    names = skeleton.names
    F = clip.frame_count
    local_rk = clip_locals_rk(clip.local_b)
    T, R, S = decompose_clip(local_rk)
    rT, rR, rS = decompose_trs_batch(skeleton.rest_local)
    mask = resolve_mask(clip.meta.get("mask"), names)
    if not np.allclose(local_rk[:, 0], skeleton.rest_local[0], atol=1e-6):
        warnings.append(f"clip {clip.name} : le joint root n'est pas au repos (SPEC §7 : clips en place)")
    if np.any(np.abs(S - 1.0) > 1e-4):
        bad = sorted({names[j] for j in np.nonzero(np.any(np.abs(S - 1.0) > 1e-4, axis=(0, 2)))[0]})
        warnings.append(f"clip {clip.name} : échelles ≠ 1 sur {bad}")
    if clip.loop and F > 1 and np.abs(local_rk[-1] - local_rk[0]).max() < 1e-6:
        warnings.append(f"clip {clip.name} : boucle dont la dernière frame répète la première — convention "
                        "attendue : frame F (= frame 0) NON stockée, durée = F/fps")
    # translations constantes ≠ repos : clip probablement fait sur une autre armature que le corps
    t_const = np.abs(T - T[:1]).max(axis=(0, 2)) <= T_EPS
    off = np.linalg.norm(T[0] - rT, axis=1)
    bad_t = [names[j] for j in range(1, len(names)) if t_const[j] and off[j] > 1e-3]
    if bad_t:
        warnings.append(f"clip {clip.name} : translations constantes ≠ repos du squelette exporté pour "
                        f"{len(bad_t)} joint(s) ({bad_t[:4]}…) — clip créé sur une autre armature ?")
    joints = range(len(names)) if mask is None else [names.index(m) for m in mask]
    tracks = []
    for j in joints:
        t, r, s = T[:, j], R[:, j], S[:, j]
        if mask is None:
            want_t = np.abs(t - rT[j]).max() > T_EPS
            want_r = _quat_angle(r, rR[j][None]).max() > R_EPS
            want_s = np.abs(s - rS[j]).max() > S_EPS
        else:
            want_t = want_r = want_s = True
        if not (want_t or want_r or want_s):
            continue
        tr = Track(joint=j, flags=0)
        if want_t:
            tr.flags |= FLAG_T
            if np.abs(t - t[0]).max() <= T_EPS:
                tr.flags |= FLAG_T_CONST; tr.t = t[:1].copy()
            else:
                tr.t = t.copy()
        if want_r:
            tr.flags |= FLAG_R
            if _quat_angle(r, r[:1]).max() <= R_EPS:
                tr.flags |= FLAG_R_CONST; tr.r = r[:1].copy()
            else:
                tr.r = r.copy()
        if want_s:
            tr.flags |= FLAG_S
            if np.abs(s - s[0]).max() <= S_EPS:
                tr.flags |= FLAG_S_CONST; tr.s = s[:1].copy()
            else:
                tr.s = s.copy()
        tracks.append(tr)
    wts = []
    for wi, wn in enumerate(clip.weight_names):
        if wn not in BODY_BLEND_SHAPES:
            warnings.append(f"clip {clip.name} : poids {wn!r} hors des blend shapes du SPEC §5 — ignoré")
            continue
        if wn in MORPH_SHAPES or wn in PROP_SHAPES:
            warnings.append(f"clip {clip.name} : anime la forme de morphologie {wn!r} (inattendu)")
        wts.append((wn, np.asarray(clip.weights[:, wi], dtype=np.float64)))
    cb = ClipBinary(name=clip.name, fps=clip.fps, frame_count=F, tracks=tracks, weights=wts)
    return cb, {"mask": mask}


def write_clips_bin(path, clips: list[ClipBinary]) -> int:
    out = bytearray()
    out += MAGIC + struct.pack("<II", VERSION, len(clips))
    for c in clips:
        nb = c.name.encode("utf-8")
        out += struct.pack("<H", len(nb)) + nb
        out += struct.pack("<fIH", float(c.fps), int(c.frame_count), len(c.tracks))
        for tr in c.tracks:
            out += struct.pack("<HB", tr.joint, tr.flags)
            for bit, arr, width in ((FLAG_T, tr.t, 3), (FLAG_R, tr.r, 4), (FLAG_S, tr.s, 3)):
                if tr.flags & bit:
                    n_expected = 1 if tr.flags & (bit << 3) else c.frame_count
                    a = np.asarray(arr, dtype="<f4").reshape(-1, width)
                    assert len(a) == n_expected, (c.name, tr.joint, bit, a.shape, n_expected)
                    out += a.tobytes()
        out += struct.pack("<H", len(c.weights))
        for wn, w in c.weights:
            nb = wn.encode("utf-8")
            a = np.asarray(w, dtype="<f4")
            assert a.shape == (c.frame_count,)
            out += struct.pack("<H", len(nb)) + nb + a.tobytes()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(bytes(out))
    return len(out)


def read_clips_bin(path) -> list[ClipBinary]:
    """Lecteur de référence (miroir du format SPEC §9) : sert à l'aller-retour et de spécification exécutable."""
    data = Path(path).read_bytes()
    off = 0

    def take(fmt):
        nonlocal off
        v = struct.unpack_from(fmt, data, off)
        off += struct.calcsize(fmt)
        return v

    def floats(n):
        nonlocal off
        a = np.frombuffer(data, dtype="<f4", count=n, offset=off).astype(np.float64)
        off += 4 * n
        return a

    if data[:4] != MAGIC:
        raise ValueError("magic PNYC absent")
    off = 4
    version, count = take("<II")
    if version != VERSION:
        raise ValueError(f"version {version} non gérée")
    clips = []
    for _ in range(count):
        (nl,) = take("<H")
        name = data[off:off + nl].decode("utf-8"); off += nl
        fps, fc, tc = take("<fIH")
        tracks = []
        for _ in range(tc):
            j, fl = take("<HB")
            tr = Track(joint=j, flags=fl)
            if fl & FLAG_T:
                n = 1 if fl & FLAG_T_CONST else fc
                tr.t = floats(3 * n).reshape(n, 3)
            if fl & FLAG_R:
                n = 1 if fl & FLAG_R_CONST else fc
                tr.r = floats(4 * n).reshape(n, 4)
            if fl & FLAG_S:
                n = 1 if fl & FLAG_S_CONST else fc
                tr.s = floats(3 * n).reshape(n, 3)
            tracks.append(tr)
        (wc,) = take("<H")
        wts = []
        for _ in range(wc):
            (nl,) = take("<H")
            wn = data[off:off + nl].decode("utf-8"); off += nl
            wts.append((wn, floats(fc)))
        clips.append(ClipBinary(name=name, fps=float(fps), frame_count=int(fc), tracks=tracks, weights=wts))
    if off != len(data):
        raise ValueError(f"octets en trop en fin de fichier : {len(data) - off}")
    return clips


def expand_clip(cb: ClipBinary, rest_local: np.ndarray) -> np.ndarray:
    """Reconstruit (F,N,4,4) locales RK : canaux/joints absents = repos (sémantique d'un clip non masqué)."""
    rT, rR, rS = decompose_trs_batch(rest_local)
    F = cb.frame_count
    T, R, S = np.repeat(rT[None], F, 0), np.repeat(rR[None], F, 0), np.repeat(rS[None], F, 0)
    for tr in cb.tracks:
        if tr.t is not None:
            T[:, tr.joint] = tr.t if len(tr.t) == F else tr.t[0]
        if tr.r is not None:
            R[:, tr.joint] = tr.r if len(tr.r) == F else tr.r[0]
        if tr.s is not None:
            S[:, tr.joint] = tr.s if len(tr.s) == F else tr.s[0]
    return compose_trs_batch(T, R, S)


def clip_manifest_entry(clip: ClipSource, cb: ClipBinary, mask: Optional[list[str]], warnings: list) -> dict:
    m = clip.meta
    F, fps = cb.frame_count, cb.fps
    loop = clip.loop
    duration = float(m["duration"]) if "duration" in m else (F / fps if loop else (F - 1) / fps)
    if "rootVelocity" in m:
        vel = [float(v) for v in m["rootVelocity"]]
    elif "rootVelocityBlender" in m:
        vel = cv.vec_b2rk(m["rootVelocityBlender"]).tolist()
    elif "speed" in m:
        vel = [0.0, 0.0, -float(m["speed"])]          # avant = −Z (SPEC §1)
    else:
        vel = [0.0, 0.0, 0.0]
    events = []
    for e in m.get("events", []):
        if "time" in e:
            t = float(e["time"])
        elif "frame" in e:
            t = float(e["frame"]) / fps
        else:
            warnings.append(f"clip {clip.name} : évènement sans time/frame ignoré : {e}")
            continue
        name = str(e.get("name", ""))
        if not EVENT_RE.match(name):
            warnings.append(f"clip {clip.name} : nom d'évènement hors SPEC §7 : {name!r}")
        events.append({"time": _r(t), "name": name})
    if clip.name not in CLIP_NAMES:
        warnings.append(f"clip {clip.name!r} absent de la liste du SPEC §7")
    if "frameCount" in m and int(m["frameCount"]) != F:
        warnings.append(f"clip {clip.name} : meta.frameCount {m['frameCount']} ≠ {F} images stockées")
    entry = {
        "name": clip.name, "loop": loop, "duration": _r(duration), "frameCount": F, "fps": _r(fps),
        "rootVelocity": _r(vel), "rootYawRate": _r(float(m.get("rootYawRate", 0.0))),
        "mask": mask, "events": events, "phaseOffset": _r(float(m.get("phaseOffset", 0.0))),
    }
    for k in CLIP_META_PASSTHROUGH:
        if k in m:
            entry[k] = m[k]
    return entry


# --------------------------------------------------------------------------------------------------
# PonyRig.json
# --------------------------------------------------------------------------------------------------


def joints_manifest(skeleton: SkeletonData) -> list[dict]:
    out = []
    for i, (n, p, path) in enumerate(zip(skeleton.names, skeleton.parents, skeleton.paths)):
        t, q, s = decompose_trs(skeleton.rest_local[i])
        out.append({
            "name": n, "path": path, "parent": int(p),
            "rest": {"t": _r(t), "r": _r(q), "s": _r(np.where(np.abs(s - 1.0) < 1e-6, 1.0, s))},
            # repère monde de liaison (pas son inverse), convention colonne, aplati colonne par colonne
            "bindModel": _r(np.asarray(skeleton.bind_world[i]).T.reshape(-1)),
        })
    return out


def default_procedural() -> dict:
    """Chaînes et joints pour les couches procédurales (SPEC §8). Poids du regard : [I] (somme = 1)."""
    return {
        "lookChain": [{"joint": "neck_03", "weight": 0.10}, {"joint": "neck_04", "weight": 0.15},
                      {"joint": "neck_05", "weight": 0.20}, {"joint": "neck_06", "weight": 0.20},
                      {"joint": "head", "weight": 0.35}],
        "ears": {"left": {"base": "ear_l", "tip": "ear_tip_l"}, "right": {"base": "ear_r", "tip": "ear_tip_r"}},
        "tail": [f"tail_{i:02d}" for i in range(1, 11)],
        "mane": [f"mane_{i:02d}" for i in range(1, 7)],
        "forelock": [f"forelock_{i:02d}" for i in range(1, 4)],
        "eyelids": {"upper_l": "eyelid_upper_l", "lower_l": "eyelid_lower_l",
                    "upper_r": "eyelid_upper_r", "lower_r": "eyelid_lower_r"},
        "eyes": ["eye_l", "eye_r"],
        "jaw": "jaw",
        "lips": {"upper": "lip_upper", "lower": "lip_lower"},
        "secondary": {"belly": "belly", "stirrups": ["stirrup_l", "stirrup_r"]},
    }


# Curseurs par défaut quand aucun fichier de morphologie n'est fourni : (id, plus, minus).
DEFAULT_SLIDERS = [
    ("legLength", "prop_legs_long", "prop_legs_short"), ("neckLength", "prop_neck_long", "prop_neck_short"),
    ("bodyLength", "prop_body_long", "prop_body_short"), ("condition", "shape_fat", "shape_thin"),
    ("headProfile", "head_roman", "head_dished"), ("stocky", "shape_stocky", None),
    ("refined", "shape_refined", None), ("muscular", "shape_muscular", None), ("belly", "shape_belly", None),
    ("crest", "shape_crest", None), ("boneHeavy", "shape_bone_heavy", None), ("headShort", "head_short", None),
    ("muzzleBroad", "muzzle_broad", None), ("hoovesLarge", "hooves_large", None),
]


def build_morphology(available_shapes: list[str], provided: Optional[dict], joint_names: list[str],
                     warnings: list) -> dict:
    """`provided` : contenu d'un morphology.json ({"sliders": [...]}, format SPEC §9, décalages de
    translation LOCALE des joints, en mètres, espace du parent — identiques Blender/RK hors root)."""
    if provided:
        sliders = provided.get("sliders", [])
        for s in sliders:
            for key in ("plus", "minus"):
                if s.get(key) and s[key] not in available_shapes:
                    warnings.append(f"morphologie {s.get('id')} : blend shape {s[key]!r} absent du corps")
            for key in ("jointOffsetsPlus", "jointOffsetsMinus"):
                for j in (s.get(key) or {}):
                    if j not in joint_names:
                        raise ValueError(f"morphologie {s.get('id')} : joint inconnu {j!r}")
        return {"sliders": sliders}
    sliders = []
    for sid, plus, minus in DEFAULT_SLIDERS:
        if plus not in available_shapes and (minus is None or minus not in available_shapes):
            continue
        sliders.append({"id": sid, "plus": plus if plus in available_shapes else None,
                        "minus": minus if minus in available_shapes else None,
                        "jointOffsetsPlus": {}, "jointOffsetsMinus": {}})
        if plus.startswith("prop_"):
            warnings.append(f"morphologie {sid} : aucun décalage de joints fourni (morphology.json absent) — "
                            "la forme de proportion ne suivra pas le squelette en pose")
    return {"sliders": sliders}


def part_manifest_entry(part_id: str, material_slots: list[str], blend_shapes: list[str], warnings: list,
                        override: Optional[dict] = None) -> dict:
    cat = dict(PART_CATALOG.get(part_id, {}))
    if not cat:
        warnings.append(f"pièce {part_id!r} absente du catalogue SPEC §6")
    if override:
        cat.update(override)
    expected = cat.get("materialSlots", [])
    present = [s for s in MATERIAL_SLOTS if s in material_slots]
    if expected and set(present) != set(expected):
        warnings.append(f"pièce {part_id} : slots présents {present} ≠ catalogue {expected}")
    slots = cat.get("slots", ["misc"])
    return {
        "id": part_id, "file": f"Parts/{part_id}.usdz", "category": cat.get("category", "misc"),
        "slot": slots[0], "slots": slots, "materialSlots": present,
        "fixedMaterials": sorted(m for m in material_slots if m.startswith("fixed_")),
        "fabricSlots": [s for s in cat.get("fabricSlots", []) if s in present],
        "blendShapes": list(blend_shapes),
        "conflicts": list(cat.get("conflicts", [])), "requires": list(cat.get("requires", [])),
        "hides": list(cat.get("hides", [])),
    }


def build_rig_manifest(skeleton: SkeletonData, blend_shapes: dict, parts: list[dict], clips: list[dict],
                       morphology: dict, coat_maps: dict, procedural: Optional[dict] = None) -> dict:
    return {
        "format": "ValombrePonyRig", "version": 1, "units": "m", "upAxis": "Y", "forward": "-Z", "fps": cv.FPS,
        "joints": joints_manifest(skeleton),
        "blendShapes": blend_shapes,
        "parts": parts,
        "clips": clips,
        "procedural": procedural or default_procedural(),
        "morphology": morphology,
        "coat": {"maps": coat_maps, "usdMaps": dict(COAT_USD_MAPS), "regions": list(COAT_REGIONS),
                 "regionScale": 16, "regionSampling": "nearest"},
    }


def write_rig_json(path, manifest: dict) -> int:
    txt = json.dumps(manifest, indent=1, ensure_ascii=False)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(txt + "\n", encoding="utf-8")
    return len(txt.encode("utf-8"))


def export_clips(clip_paths: list, skeleton: SkeletonData, bin_path, warnings: list):
    """Lit les .npz, écrit PonyClips.bin ; renvoie (sources, binaires, entrées de manifeste)."""
    sources, bins, entries = [], [], []
    seen = set()
    for p in sorted(clip_paths):
        try:
            c = load_clip_npz(p)
        except Exception as e:  # noqa: BLE001 — on veut un message clair par fichier, pas un arrêt global
            warnings.append(f"clip ignoré {Path(p).name} : {e}")
            continue
        if c.name in seen:
            warnings.append(f"clip {c.name} en double ({Path(p).name}) — ignoré")
            continue
        seen.add(c.name)
        cb, extra = build_clip_binary(c, skeleton, warnings)
        sources.append(c); bins.append(cb)
        entries.append(clip_manifest_entry(c, cb, extra["mask"], warnings))
    size = write_clips_bin(bin_path, bins)
    return sources, bins, entries, size
