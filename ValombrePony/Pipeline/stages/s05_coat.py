#!/usr/bin/env python3
"""Étape 05 — robes : albedos du corps (défaut + présets), aperçus, rendus, et génération du Swift dérivé.

Usage :
    python3 Pipeline/stages/s05_coat.py                 # albedos + planche UV (+ rendus Cycles si body.blend existe)
    python3 Pipeline/stages/s05_coat.py --no-render     # sans rendus Blender
    python3 Pipeline/stages/s05_coat.py --swift         # régénère CoatPresetsData.swift + CoatReferenceVectorsTests.swift
    python3 Pipeline/stages/s05_coat.py --synthetic     # force les cartes synthétiques
    python3 Pipeline/stages/s05_coat.py --only bai,noir # restreint les présets (albedos et rendus)

Entrées (agent « body ») : Pipeline/build/textures/coat_{shading,regions,params,patterns}.png, body_meta.json,
body.blend ; (agent « hair ») hair_strands.png. Si les cartes manquent, cartes synthétiques (coat_reference).
Sorties : Pipeline/build/textures/coat_albedo_default.png (2048²), presets/<id>.png (1024²), iris_default.png
(512²) ; Previews/coat/presets_uv.png, hair_iris.png, presets_render.png. (hair_albedo_default.png appartient à
l'agent « hair » : on ne l'écrit pas.)
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pony import coat_reference as cr  # noqa: E402
from pony.conventions import BUILD_DIR, PREVIEW_DIR, PROJECT_DIR, TEXTURE_BUILD_DIR  # noqa: E402

COAT_PREVIEW_DIR = PREVIEW_DIR / "coat"
PRESET_DIR = TEXTURE_BUILD_DIR / "presets"
SWIFT_COAT_DIR = PROJECT_DIR / "PonyKit" / "Sources" / "PonyCore" / "Coat"
SWIFT_TEST_DIR = PROJECT_DIR / "PonyKit" / "Tests" / "PonyCoreTests"
MAP_NAMES = ("shading", "regions", "params", "patterns")

# Présets rendus dans Blender (économie CPU : 8 rendus).
RENDER_PRESETS = ["bai", "alezan_crins_laves", "palomino", "gris_pommele", "pie_tobiano", "appaloosa_leopard",
                  "rouan", "bai_dun"]


# ---------------------------------------------------------------------------------------------
# Chargement des cartes
# ---------------------------------------------------------------------------------------------


def _expand_rgba(v8: np.ndarray) -> np.ndarray:
    """(H, W, C) uint8 avec C = 1, 2, 3 ou 4 -> RGBA."""
    if v8.ndim == 2:
        v8 = v8[..., None]
    c = v8.shape[2]
    if c == 1:
        v8 = np.concatenate([v8, v8, v8, np.full_like(v8, 255)], axis=-1)
    elif c == 2:
        v8 = np.concatenate([v8[..., :1]] * 3 + [v8[..., 1:2]], axis=-1)
    elif c == 3:
        v8 = np.concatenate([v8, np.full(v8.shape[:2] + (1,), 255, dtype=np.uint8)], axis=-1)
    return np.ascontiguousarray(v8.astype(np.uint8))


def png_bitdepth(p: Path) -> int:
    head = p.read_bytes()[:33]
    assert head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR", f"PNG invalide : {p}"
    return head[24]


def read_png_any(p: Path) -> np.ndarray:
    """PNG 8 ou 16 bits (gris, gris+alpha, RGB, RGBA, palette) -> uint8 RGBA.

    16 bits -> 8 bits par arrondi floor(v·255/65535 + 0,5) [I] (≈ ce que fait un dessin CGImage dans un contexte
    8 bits côté PonyKit). Pillow tronque le RGB 16 bits : on décode alors avec PyPNG."""
    if png_bitdepth(p) == 16:
        import png  # PyPNG

        w, h, rows, info = png.Reader(filename=str(p)).asDirect()
        planes = info["planes"]
        arr = np.vstack([np.asarray(r, dtype=np.uint16) for r in rows]).reshape(h, w, planes)
        a8 = np.clip(np.floor(arr.astype(np.float64) * 255.0 / 65535.0 + 0.5), 0, 255).astype(np.uint8)
        return _expand_rgba(a8)
    with Image.open(p) as im:
        if im.mode == "P":
            im = im.convert("RGBA")
        if im.mode not in ("L", "LA", "RGB", "RGBA"):
            im = im.convert("RGBA")
        return _expand_rgba(np.asarray(im, dtype=np.uint8))


def real_maps_available() -> bool:
    return all((TEXTURE_BUILD_DIR / f"coat_{n}.png").exists() for n in MAP_NAMES)


def load_maps(force_synthetic: bool = False):
    """-> (maps dict, source str)."""
    if not force_synthetic and real_maps_available():
        maps = {n: read_png_any(TEXTURE_BUILD_DIR / f"coat_{n}.png") for n in MAP_NAMES}
        return maps, "réelles (Pipeline/build/textures/coat_*.png)"
    return cr.synthetic_maps(1024), "synthétiques (coat_reference.synthetic_maps)"


def load_landmarks() -> tuple[cr.Landmarks, str]:
    """Repères depuis body_meta.json (clé « coat » / « coat_landmarks » si présente), sinon valeurs par défaut [I]."""
    meta_path = BUILD_DIR / "body_meta.json"
    if not meta_path.exists():
        return cr.Landmarks(), "défaut (body_meta.json absent)"
    meta = json.loads(meta_path.read_text())
    cand = meta.get("coat_landmarks") or (meta.get("coat") or {}).get("landmarks") or meta.get("landmarks") or {}
    keys = {"coronet": "coronet", "faceEyeV": "face_eye_v", "faceEyeU": "face_eye_u", "nostrilV": "nostril_v"}
    kw = {}
    for js, py in keys.items():
        for k in (js, py):
            if k in cand and isinstance(cand[k], (int, float)):
                kw[py] = float(cand[k])
    if kw:
        return cr.Landmarks(**kw), f"body_meta.json ({', '.join(sorted(kw))})"
    return cr.Landmarks(), "défaut (aucun repère « coat » dans body_meta.json)"


def save_png(arr: np.ndarray, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr).save(path, optimize=False)


# ---------------------------------------------------------------------------------------------
# Albedos et planches
# ---------------------------------------------------------------------------------------------


def build_albedos(maps, landmarks, only=None):
    t0 = time.time()
    default = cr.compose_body(cr.default_config(), maps, 2048, landmarks)
    t_default = time.time() - t0
    save_png(default[..., :3], TEXTURE_BUILD_DIR / "coat_albedo_default.png")
    print(f"[coat] coat_albedo_default.png 2048² en {t_default:.1f} s (numpy, référence)")
    PRESET_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for pid, name, summary, cfg in cr.preset_configs():
        if only and pid not in only:
            continue
        t0 = time.time()
        a = cr.compose_body(cfg, maps, 1024, landmarks)
        save_png(a[..., :3], PRESET_DIR / f"{pid}.png")
        out[pid] = a
        print(f"[coat] presets/{pid}.png 1024² en {time.time() - t0:.1f} s")
    return default, out


def label_cell(im: Image.Image, text: str, sub: str | None = None):
    d = ImageDraw.Draw(im)
    h = 30 if sub else 16
    d.rectangle([0, im.height - h, im.width, im.height], fill=(0, 0, 0))
    d.text((4, im.height - h + 2), text, fill=(255, 255, 255))
    if sub:
        d.text((4, im.height - 15), sub, fill=(190, 190, 190))
    return im


def preset_sheet(albedos: dict, path: Path, cell: int = 256, cols: int = 6):
    names = {pid: name for pid, name, _, _ in cr.preset_configs()}
    items = list(albedos.items())
    rows = math.ceil(len(items) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * cell), (30, 30, 30))
    for i, (pid, a) in enumerate(items):
        im = Image.fromarray(a[..., :3]).resize((cell, cell), Image.LANCZOS)
        label_cell(im, names[pid], pid)
        sheet.paste(im, ((i % cols) * cell, (i // cols) * cell))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    print(f"[coat] planche {path}")


def hair_iris_sheet(path: Path, strands: np.ndarray, ids=("bai", "alezan_crins_laves", "palomino", "gris_pommele",
                                                          "pie_tobiano", "creme", "silver_noir", "champagne_dore")):
    cfgs = {pid: cfg for pid, _, _, cfg in cr.preset_configs()}
    cell = 160
    sheet = Image.new("RGB", (len(ids) * cell, 2 * cell + 20), (60, 60, 60))
    d = ImageDraw.Draw(sheet)
    for i, pid in enumerate(ids):
        cfg = cfgs[pid]
        hair = cr.compose_hair(cfg, strands)
        bg = Image.new("RGBA", (hair.shape[1], hair.shape[0]), (90, 110, 90, 255))
        hi = Image.alpha_composite(bg, Image.fromarray(hair, "RGBA")).convert("RGB").resize((cell, cell))
        iris = Image.fromarray(cr.compose_iris(cfg, None, 256)[..., :3]).resize((cell, cell), Image.LANCZOS)
        sheet.paste(hi, (i * cell, 0))
        sheet.paste(iris, (i * cell, cell))
        d.text((i * cell + 4, 2 * cell + 4), pid, fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    print(f"[coat] planche crins/iris {path}")


# ---------------------------------------------------------------------------------------------
# Rendus Blender (Cycles) du corps
# ---------------------------------------------------------------------------------------------


def render_presets(ids, out_path: Path, samples: int = 24, res: int = 420):
    """Lance Blender (bpy en module) dans un sous-processus : un rendu par préset, puis planche contact."""
    blend = BUILD_DIR / "body.blend"
    if not blend.exists():
        print("[coat] body.blend absent : pas de rendu Cycles")
        return None
    tmp = BUILD_DIR / "coat_renders"
    tmp.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, str(Path(__file__).resolve()), "--render-worker", "--blend", str(blend), "--out", str(tmp),
            "--samples", str(samples), "--res", str(res), "--only", ",".join(ids)]
    print("[coat] rendu :", " ".join(args))
    t0 = time.time()
    r = subprocess.run(args, capture_output=True, text=True)
    print(r.stdout[-3000:])
    if r.returncode != 0:
        print(r.stderr[-3000:])
        print("[coat] ÉCHEC du rendu Blender")
        return None
    print(f"[coat] rendus en {time.time() - t0:.0f} s")
    names = {pid: name for pid, name, _, _ in cr.preset_configs()}
    paths = [tmp / f"{pid}.png" for pid in ids if (tmp / f"{pid}.png").exists()]
    labels = [names[p.stem] for p in paths]
    cols = 4
    cell = (res, res)
    rows = math.ceil(len(paths) / cols)
    sheet = Image.new("RGB", (cols * cell[0], rows * cell[1]), (30, 30, 30))
    for i, p in enumerate(paths):
        im = label_cell(Image.open(p).convert("RGB").resize(cell), labels[i])
        sheet.paste(im, ((i % cols) * cell[0], (i // cols) * cell[1]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    print(f"[coat] planche rendus {out_path}")
    return out_path


def render_worker(blend: Path, out_dir: Path, ids, samples: int, res: int):
    """(Sous-processus) Ouvre body.blend, applique chaque albedo de préset au maillage `Body`, rend en Cycles."""
    import bpy
    from mathutils import Vector

    from pony import render as R

    bpy.ops.wm.open_mainfile(filepath=str(blend))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    body = bpy.data.objects.get("Body")
    if body is None or body.type != "MESH":
        body = max(meshes, key=lambda o: len(o.data.vertices))
    print(f"[coat-worker] maillage : {body.name} ({len(body.data.vertices)} sommets), "
          f"UV : {[u.name for u in body.data.uv_layers]}")
    mat = bpy.data.materials.new("CoatPreview")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.55
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.interpolation = "Linear"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    normal_path = TEXTURE_BUILD_DIR / "coat_normal.png"
    if normal_path.exists():
        nimg = bpy.data.images.load(str(normal_path))
        nimg.colorspace_settings.name = "Non-Color"
        ntex = nt.nodes.new("ShaderNodeTexImage")
        ntex.image = nimg
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(ntex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    body.data.materials.clear()
    body.data.materials.append(mat)
    for p in body.data.polygons:
        p.use_smooth = True
    R.setup_stage("CYCLES", samples, (res, res))
    bpy.context.scene.render.threads_mode = "FIXED"
    bpy.context.scene.render.threads = 2
    pts = [body.matrix_world @ Vector(c) for c in body.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (lo + hi) / 2
    size = max(hi - lo)
    out_dir.mkdir(parents=True, exist_ok=True)
    for pid in ids:
        img_path = PRESET_DIR / f"{pid}.png"
        if not img_path.exists():
            print(f"[coat-worker] albedo manquant : {img_path}")
            continue
        img = bpy.data.images.load(str(img_path), check_existing=False)
        img.colorspace_settings.name = "sRGB"
        tex.image = img
        R.render(out_dir / f"{pid}.png", view="three_quarter", target=tuple(center), distance=size * 1.75)
        print(f"[coat-worker] rendu {pid}")
    return 0


# ---------------------------------------------------------------------------------------------
# Génération du Swift dérivé (présets + vecteurs de référence)
# ---------------------------------------------------------------------------------------------


def _swift_float(v) -> str:
    s = repr(float(v))
    return s


def _swift_color(v) -> str:
    if isinstance(v, str):
        return f'PonyColor(hex: "{v}")'
    c = cr.color_srgb(v)
    return f"PonyColor(r: {_swift_float(c[0])}, g: {_swift_float(c[1])}, b: {_swift_float(c[2])})"


def _swift_value(path: str, v) -> str:
    if path in cr.ENUM_FIELDS:
        return "." + cr.ENUMS[cr.ENUM_FIELDS[path]][v]
    if path.startswith("overrides.") or path == "hair.secondaryColor":
        return _swift_color(v)
    if isinstance(v, bool):
        return "true" if v else "false"
    if path == "seed":
        return str(int(v))
    if isinstance(v, (int, float)):
        return _swift_float(v)
    raise TypeError(f"valeur non gérée {path}={v!r}")


def _diff(base, cfg, prefix=""):
    out = []
    keys = sorted(set(base) | set(cfg)) if isinstance(base, dict) else []
    for k in keys:
        path = f"{prefix}{k}"
        b = base.get(k)
        c = cfg.get(k)
        if isinstance(c, dict) and isinstance(b, dict) and k != "overrides":
            out += _diff(b, c, path + ".")
        elif k == "overrides":
            for ok in sorted((c or {})):
                out.append((f"overrides.{ok}", c[ok]))
        elif b != c:
            out.append((path, c))
    return out


def swift_presets_source() -> str:
    base = cr.plain_config()
    lines = [
        "// GÉNÉRÉ par `python3 Pipeline/stages/s05_coat.py --swift` à partir de `Pipeline/pony/coat_reference.py`",
        "// (table PRESETS). NE PAS ÉDITER À LA MAIN : modifier la table Python puis régénérer (les vecteurs de",
        "// référence de CoatReferenceVectorsTests en dépendent). Couleurs sous-jacentes : approximations [A].",
        "",
        "import Foundation",
        "",
        "extension CoatPreset {",
        f"    /// {len(cr.PRESETS)} présets aux noms français, dans l'ordre d'affichage.",
        "    public static let all: [CoatPreset] = [",
    ]
    for pid, name, summary, cfg in cr.preset_configs():
        diffs = _diff(base, cfg)
        lines.append(f'        CoatPreset(id: "{pid}", name: "{name}",')
        lines.append(f'                   summary: "{summary}",')
        if not diffs:
            lines.append("                   configuration: CoatConfiguration.plain),")
            continue
        lines.append("                   configuration: CoatConfiguration.make { c in")
        for path, v in diffs:
            lines.append(f"                       c.{path} = {_swift_value(path, v)}")
        lines.append("                   }),")
    lines += ["    ]", "}", ""]
    return "\n".join(lines)


def fnv1a(arr: np.ndarray) -> int:
    """FNV-1a 32 bits sur les octets (vérifie l'identité des cartes synthétiques Swift/Python)."""
    h = 0x811C9DC5
    for b in arr.tobytes():
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


VECTOR_MAP_SIZE = 64
VECTOR_OUT_SIZE = 96


def _extra_cases():
    base = cr.plain_config()
    return [
        ("libre_surcharges", cr.deep_merge(base, {
            "genotype": {"extensionLocus": "ee"},
            "overrides": {"body": "#6A8FB0", "mane": "#E05080", "hooves": "#405060", "eyes": "#30A060",
                          "skin": "#704050"},
            "face": {"kind": "strip", "snip": True, "lips": True, "offsetU": 0.03, "irregularity": 0.9},
            "legs": {"frontLeft": {"height": 0.03, "ermine": True}, "hindRight": {"height": 0.7, "ermine": True,
                                                                                "irregularity": 1.0}},
            "hair": {"tipLightening": 0.5, "secondaryColor": "#20C0F0", "secondaryFraction": 0.3},
            "seed": 77})),
        ("splash_blanc_dominant", cr.deep_merge(base, {
            "genotype": {"splashedWhite": "X/X", "dominantWhite": "X/n"},
            "expression": {"splashCoverage": 0.5, "dominantWhiteCoverage": 0.4}})),
        ("gris_alezan_pommelures", cr.deep_merge(base, {
            "genotype": {"extensionLocus": "ee", "grey": "X/X"},
            "expression": {"greyStage": 0.35, "dapples": 0.8, "shade": -0.6, "flaxen": 0.5, "sooty": 0.4}})),
        ("leopard_peu_tache_marmore", cr.deep_merge(base, {
            "genotype": {"leopardComplex": "X/X", "patternOne": "X/n", "agouti": "aa"},
            "expression": {"varnish": 0.6, "spotSize": 0.8}})),
        ("perle_dun_sabino", cr.deep_merge(base, {
            "genotype": {"extensionLocus": "ee", "creamPearl": "prl/prl", "dun": "X/X", "sabino": "X/X"},
            "expression": {"sabinoCoverage": 0.3, "primitiveMarkings": 0.7}})),
        ("champagne_creme_bai_brun", cr.deep_merge(base, {
            "genotype": {"agouti": "At", "creamPearl": "Cr/prl", "champagne": "X/n", "tobiano": "X/n"},
            "expression": {"pangare": 0.4, "tobianoCoverage": 0.8}, "irisStyle": "vairon"})),
        ("rouan_graine_9", cr.deep_merge(base, {
            "genotype": {"roan": "X/n", "frameOvero": "X/n"},
            "expression": {"roanDensity": 1.0, "overoCoverage": 0.8, "pointsHeight": 0.2}, "seed": 9})),
    ]


def _sample_points(maps64):
    """Texels témoins : pour chaque région présente, le 1er et le texel médian (ordre raster) + une grille."""
    tabs = cr._axis_tables(VECTOR_MAP_SIZE, VECTOR_OUT_SIZE)
    near = tabs[3]
    rid = (maps64["regions"][np.ix_(near, near)][..., 0].astype(np.int64) + 8) // 16
    pts = []
    for r in range(16):
        ys, xs = np.nonzero(rid == r)
        if len(ys) == 0:
            continue
        for k in (0, len(ys) // 2):
            pts.append((int(xs[k]), int(ys[k])))
    for gy in range(4, VECTOR_OUT_SIZE, 23):
        for gx in range(7, VECTOR_OUT_SIZE, 29):
            pts.append((gx, gy))
    seen = []
    for p in pts:
        if p not in seen:
            seen.append(p)
    return seen


def swift_vectors_source() -> str:
    maps64 = cr.synthetic_maps(VECTOR_MAP_SIZE)
    strands = cr.synthetic_strands(32, 64)
    sums = {k: fnv1a(maps64[k]) for k in cr_map_order()}
    pts = _sample_points(maps64)
    cases = [(pid, cfg) for pid, _, _, cfg in cr.preset_configs()] + _extra_cases()
    body_cases = []
    for name, cfg in cases:
        img = cr.compose_body(cfg, maps64, VECTOR_OUT_SIZE)
        tex = [(x, y) + tuple(int(v) for v in img[y, x]) for x, y in pts]
        mean = [float(img[..., c].astype(np.float64).mean()) for c in range(3)]
        body_cases.append((name, cr.config_to_json(cfg), tex, mean))
    hair_pts = [(x, y) for y in range(0, 64, 9) for x in range(1, 32, 7)]
    iris_pts = [(x, y) for y in range(2, 64, 10) for x in range(3, 64, 11)]
    hair_cases = []
    iris_cases = []
    for name, cfg in cases:
        if name in ("bai", "alezan_crins_laves", "gris_pommele", "pie_tobiano", "libre_surcharges"):
            h = cr.compose_hair(cfg, strands)
            hair_cases.append((name, cr.config_to_json(cfg), [(x, y) + tuple(int(v) for v in h[y, x]) for x, y in hair_pts]))
        if name in ("bai", "creme", "champagne_dore", "pie_overo", "appaloosa_leopard", "libre_surcharges"):
            i = cr.compose_iris(cfg, None, 64)
            iris_cases.append((name, cr.config_to_json(cfg), [(x, y) + tuple(int(v) for v in i[y, x]) for x, y in iris_pts]))
    # Iris avec carte de détail : on réutilise le canal R du shading synthétique (64²) comme carte grise.
    detail = maps64["shading"]
    idet = cr.compose_iris(cases[0][1], detail, 48)
    detail_case = [(x, y) + tuple(int(v) for v in idet[y, x]) for y in range(1, 48, 9) for x in range(2, 48, 9)]

    def tex_lines(tex, indent):
        out = []
        row = []
        for t in tex:
            row.append("(%d, %d, %d, %d, %d, %d)" % t)
            if len(row) == 4:
                out.append(indent + ", ".join(row) + ",")
                row = []
        if row:
            out.append(indent + ", ".join(row) + ",")
        return out

    L = [
        "// GÉNÉRÉ par `python3 Pipeline/stages/s05_coat.py --swift` : valeurs calculées par l'implémentation de",
        "// référence numpy (`Pipeline/pony/coat_reference.py`). NE PAS ÉDITER À LA MAIN.",
        "// Ces tests n'ont PAS pu être exécutés dans l'environnement de génération (pas de compilateur Swift) :",
        "// les lancer dans Xcode (`swift test` / ⌘U). Tolérance ±3 niveaux (libm de la palette, contraction FMA).",
        "",
        "import Foundation",
        "import XCTest",
        "@testable import PonyCore",
        "",
        "final class CoatReferenceVectorsTests: XCTestCase {",
        "    typealias Texel = (x: Int, y: Int, r: UInt8, g: UInt8, b: UInt8, a: UInt8)",
        "",
        f"    static let mapSize = {VECTOR_MAP_SIZE}",
        f"    static let outSize = {VECTOR_OUT_SIZE}",
        "    static let tolerance = 3",
        "    static let meanTolerance = 0.75",
        "",
        "    /// FNV-1a 32 bits des cartes synthétiques 64² (doivent être identiques au bit près).",
        "    static let mapChecksums: [String: UInt32] = [",
    ]
    for k, v in sums.items():
        L.append(f'        "{k}": 0x{v:08X},')
    L += [
        "    ]",
        f"    static let strandsChecksum: UInt32 = 0x{fnv1a(strands):08X}   // syntheticStrands(width: 32, height: 64)",
        "",
        "    static func fnv1a(_ bytes: [UInt8]) -> UInt32 {",
        "        var h: UInt32 = 0x811C_9DC5",
        "        for b in bytes {",
        "            h ^= UInt32(b)",
        "            h = h &* 0x0100_0193",
        "        }",
        "        return h",
        "    }",
        "",
        "    func decode(_ json: String) throws -> CoatConfiguration {",
        "        try JSONDecoder().decode(CoatConfiguration.self, from: Data(json.utf8))",
        "    }",
        "",
        "    func assertTexels(_ img: RGBA8Image, _ texels: [Texel], _ name: String,",
        "                      file: StaticString = #filePath, line: UInt = #line) {",
        "        for t in texels {",
        "            let p = img.pixel(x: t.x, y: t.y)",
        "            let exp = [Int(t.r), Int(t.g), Int(t.b), Int(t.a)]",
        "            let got = [Int(p.x), Int(p.y), Int(p.z), Int(p.w)]",
        "            for c in 0..<4 where abs(exp[c] - got[c]) > Self.tolerance {",
        "                XCTFail(\"\\(name) texel (\\(t.x), \\(t.y)) canal \\(c) : attendu \\(exp[c]), obtenu \\(got[c])\",",
        "                        file: file, line: line)",
        "            }",
        "        }",
        "    }",
        "",
        "    func testSyntheticMapsAreBitIdenticalToPython() {",
        "        let maps = CoatMaps.synthetic(size: Self.mapSize)",
        '        XCTAssertEqual(Self.fnv1a(maps.shading.pixels), Self.mapChecksums["shading"])',
        '        XCTAssertEqual(Self.fnv1a(maps.regions.pixels), Self.mapChecksums["regions"])',
        '        XCTAssertEqual(Self.fnv1a(maps.params.pixels), Self.mapChecksums["params"])',
        '        XCTAssertEqual(Self.fnv1a(maps.patterns.pixels), Self.mapChecksums["patterns"])',
        "        XCTAssertEqual(Self.fnv1a(CoatMaps.syntheticStrands(width: 32, height: 64).pixels), Self.strandsChecksum)",
        "    }",
        "",
        "    func testBodyTexelsMatchPythonReference() throws {",
        "        let maps = CoatMaps.synthetic(size: Self.mapSize)",
        "        for c in Self.bodyCases {",
        "            let cfg = try decode(c.json)",
        "            let img = CoatCompositor.composeBody(cfg, maps: maps, resolution: Self.outSize)",
        "            XCTAssertEqual(img.width, Self.outSize)",
        "            assertTexels(img, c.texels, c.name)",
        "            for ch in 0..<3 {",
        "                var sum = 0.0",
        "                for i in stride(from: ch, to: img.pixels.count, by: 4) { sum += Double(img.pixels[i]) }",
        "                let mean = sum / Double(img.width * img.height)",
        "                XCTAssertEqual(mean, c.mean[ch], accuracy: Self.meanTolerance, \"\\(c.name) moyenne canal \\(ch)\")",
        "            }",
        "        }",
        "    }",
        "",
        "    func testPresetsDecodeToGeneratedPresets() throws {",
        "        for c in Self.bodyCases {",
        "            guard let preset = CoatPreset.named(c.name) else { continue }",
        "            let cfg = try decode(c.json)",
        "            XCTAssertEqual(cfg, preset.configuration, \"JSON Python != préset Swift \\(c.name)\")",
        "        }",
        "    }",
        "",
        "    func testHairTexelsMatchPythonReference() throws {",
        "        let strands = CoatMaps.syntheticStrands(width: 32, height: 64)",
        "        for c in Self.hairCases {",
        "            let cfg = try decode(c.json)",
        "            let img = CoatCompositor.composeHair(cfg, strands: strands)",
        "            assertTexels(img, c.texels, \"crins \\(c.name)\")",
        "        }",
        "    }",
        "",
        "    func testIrisTexelsMatchPythonReference() throws {",
        "        for c in Self.irisCases {",
        "            let cfg = try decode(c.json)",
        "            let img = CoatCompositor.composeIris(cfg, detail: nil, resolution: 64)",
        "            assertTexels(img, c.texels, \"iris \\(c.name)\")",
        "        }",
        "        let detail = CoatMaps.synthetic(size: Self.mapSize).shading",
        "        let cfg0 = try decode(Self.bodyCases[0].json)",
        "        let img = CoatCompositor.composeIris(cfg0, detail: detail, resolution: 48)",
        "        assertTexels(img, Self.irisDetailTexels, \"iris avec détail\")",
        "    }",
        "",
        "    struct BodyCase { let name: String; let json: String; let texels: [Texel]; let mean: [Double] }",
        "    struct ImageCase { let name: String; let json: String; let texels: [Texel] }",
        "",
        "    static let bodyCases: [BodyCase] = [",
    ]
    for name, js, tex, mean in body_cases:
        L.append(f'        BodyCase(name: "{name}",')
        L.append(f'                 json: #"{js}"#,')
        L.append("                 texels: [")
        L += tex_lines(tex, "                     ")
        L.append("                 ],")
        L.append("                 mean: [%s]),"  % ", ".join("%.4f" % m for m in mean))
    L.append("    ]")
    L.append("")
    for var, cs in (("hairCases", hair_cases), ("irisCases", iris_cases)):
        L.append(f"    static let {var}: [ImageCase] = [")
        for name, js, tex in cs:
            L.append(f'        ImageCase(name: "{name}",')
            L.append(f'                  json: #"{js}"#,')
            L.append("                  texels: [")
            L += tex_lines(tex, "                      ")
            L.append("                  ]),")
        L.append("    ]")
        L.append("")
    L.append("    static let irisDetailTexels: [Texel] = [")
    L += tex_lines(detail_case, "        ")
    L.append("    ]")
    L.append("}")
    L.append("")
    return "\n".join(L)


def cr_map_order():
    return MAP_NAMES


def write_swift():
    p1 = SWIFT_COAT_DIR / "CoatPresetsData.swift"
    p1.write_text(swift_presets_source(), encoding="utf-8")
    print(f"[coat] {p1}")
    p2 = SWIFT_TEST_DIR / "CoatReferenceVectorsTests.swift"
    p2.parent.mkdir(parents=True, exist_ok=True)
    p2.write_text(swift_vectors_source(), encoding="utf-8")
    print(f"[coat] {p2}")


# ---------------------------------------------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--swift", action="store_true", help="régénère le Swift dérivé (présets + vecteurs) et s'arrête")
    ap.add_argument("--synthetic", action="store_true", help="force les cartes synthétiques")
    ap.add_argument("--no-render", action="store_true", help="pas de rendu Blender")
    ap.add_argument("--only", default="", help="liste d'ids de présets séparés par des virgules")
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--render-worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--blend", default="", help=argparse.SUPPRESS)
    ap.add_argument("--out", default="", help=argparse.SUPPRESS)
    ap.add_argument("--res", type=int, default=420, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    if args.render_worker:
        return render_worker(Path(args.blend), Path(args.out), [s for s in args.only.split(",") if s],
                             args.samples, args.res)

    if args.swift:
        write_swift()
        return 0

    only = [s for s in args.only.split(",") if s] or None
    maps, source = load_maps(args.synthetic)
    landmarks, lm_source = load_landmarks()
    print(f"[coat] cartes : {source} ; repères : {lm_source}")
    for k in MAP_NAMES:
        print(f"[coat]   {k}: {maps[k].shape}")
    _, albedos = build_albedos(maps, landmarks, only)
    preset_sheet(albedos, COAT_PREVIEW_DIR / "presets_uv.png")

    strands_path = TEXTURE_BUILD_DIR / "hair_strands.png"
    strands = read_png_any(strands_path) if strands_path.exists() else cr.synthetic_strands(128, 256)
    print(f"[coat] mèches : {'hair_strands.png (agent hair)' if strands_path.exists() else 'synthétiques'}")
    save_png(cr.compose_iris(cr.default_config(), None, 512), TEXTURE_BUILD_DIR / "iris_default.png")
    hair_iris_sheet(COAT_PREVIEW_DIR / "hair_iris.png", strands)

    if not args.no_render:
        ids = [p for p in RENDER_PRESETS if not only or p in only]
        render_presets(ids, COAT_PREVIEW_DIR / "presets_render.png", samples=args.samples)
    return 0


if __name__ == "__main__":
    sys.exit(main())
