"""Implémentation de RÉFÉRENCE (numpy) du système de robes ValombrePony.

C'est la « vérité exécutable » du compositeur Swift `PonyKit/Sources/PonyCore/Coat/` :
mêmes fonctions, mêmes constantes, même ordre des opérations en float32, même hachage entier 32 bits.
Toute modification ici doit être reportée LIGNE À LIGNE dans le Swift (et inversement), puis les vecteurs
de référence régénérés : `python3 Pipeline/stages/s05_coat.py --swift`.

Organisation (identique côté Swift) :
- couleurs : hex <-> sRGB float32, sRGB <-> linéaire, table d'encodage linéaire -> sRGB 8 bits (LUT 4096) ;
- bruit : hachage entier `hash32` (lowbias32), `hash01`, bruit de valeur 2D (`value_noise`) ;
- configuration : dictionnaires dont les clés sont EXACTEMENT les noms des propriétés Swift (JSON Codable) ;
- palette : génotype simplifié -> couleurs linéaires (dilutions par facteurs de densité optique) ;
- compositeur : corps (par texel, cartes du SPEC §4), crins (texture de mèches), iris (512²) ;
- cartes synthétiques : générateur en arithmétique ENTIÈRE (identique au bit près en Swift) pour les tests.

Légende : [A] approximation artistique (aucune source), [I] choix d'ingénierie, [NV] connaissance non vérifiée
dans cette session (Docs/research/anatomy.md §4 est entièrement [NV] ; toutes les valeurs hex y sont [A]).

Règles d'équivalence numérique avec Swift :
- tout calcul par texel est en float32 ; les constantes sont des littéraux convertis en float32 (comme `Float`) ;
- aucune fonction transcendante par texel (seulement + - * /, min, max, floor, sqrt — correctement arrondies) ;
- les fonctions transcendantes (pow, log, exp) ne servent qu'à la palette, calculée en float64 puis arrondie
  en float32 (des écarts d'1 ulp entre libm sont possibles -> les vecteurs de référence ont une tolérance) ;
- arrondis : floor(x + 0.5) explicites (jamais np.round, qui arrondit au pair).
"""
from __future__ import annotations

import copy
import json
import math

import numpy as np

F = np.float32
U32 = np.uint32
MASK32 = 0xFFFFFFFF

# ---------------------------------------------------------------------------------------------
# Couleurs
# ---------------------------------------------------------------------------------------------


def hex_to_srgb(h: str) -> np.ndarray:
    """'#RRGGBB' ou 'RRGGBB' -> sRGB float32 (0…1). Invalide -> noir (comme PonyColor(hex:))."""
    s = h.strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6:
        return np.zeros(3, dtype=F)
    try:
        v = int(s, 16)
    except ValueError:
        return np.zeros(3, dtype=F)
    r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    return np.array([F(r) / F(255), F(g) / F(255), F(b) / F(255)], dtype=F)


def srgb_to_hex(c) -> str:
    """sRGB 0…1 -> '#RRGGBB' (arrondi floor(x*255 + 0.5) en float32, comme PonyColor.hexString)."""
    out = []
    for v in c:
        x = min(max(F(v), F(0)), F(1))
        out.append(int(np.floor(x * F(255) + F(0.5))))
    return "#%02X%02X%02X" % tuple(out)


def color_srgb(v) -> np.ndarray:
    """Couleur de configuration -> sRGB float32 : '#RRGGBB' ou {"r","g","b"} (forme Codable de PonyColor)."""
    if isinstance(v, str):
        return hex_to_srgb(v)
    return np.array([F(v["r"]), F(v["g"]), F(v["b"])], dtype=F)


def color_json(v) -> dict:
    """Forme JSON Codable de PonyColor (valeurs float32 exactes)."""
    c = color_srgb(v)
    return {"r": float(c[0]), "g": float(c[1]), "b": float(c[2])}


def srgb_to_linear_f64(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb_f64(c: float) -> float:
    c = min(max(c, 0.0), 1.0)
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1.0 / 2.4) - 0.055


def srgb_to_linear(c) -> np.ndarray:
    """sRGB float32 (3,) -> linéaire float32 (calcul en float64, comme PonyColor.linear)."""
    return np.array([F(srgb_to_linear_f64(float(F(v)))) for v in c], dtype=F)


def hex_lin(h: str) -> np.ndarray:
    return srgb_to_linear(hex_to_srgb(h))


ENCODE_LUT_SIZE = 4096


def _build_encode_lut() -> np.ndarray:
    lut = np.zeros(ENCODE_LUT_SIZE, dtype=np.uint8)
    for i in range(ENCODE_LUT_SIZE):
        v = linear_to_srgb_f64(i / 4095.0)
        lut[i] = min(255, max(0, int(math.floor(v * 255.0 + 0.5))))
    return lut


ENCODE_LUT = _build_encode_lut()


def encode_linear(c: np.ndarray) -> np.ndarray:
    """Linéaire float32 (…) -> octets sRGB via la LUT : idx = Int(clamp(v,0,1)*4095 + 0.5)."""
    v = np.minimum(np.maximum(c, F(0)), F(1))
    idx = (v * F(4095) + F(0.5)).astype(np.int32)
    return ENCODE_LUT[idx]


# ---------------------------------------------------------------------------------------------
# Hachage et bruit (identiques au bit près en Swift : UInt32 avec &*, ^, >>)
# ---------------------------------------------------------------------------------------------


def hash32_int(x: int) -> int:
    """lowbias32 (C. Wellons) sur un entier Python (scalaire)."""
    x &= MASK32
    x ^= x >> 16
    x = (x * 0x7FEB352D) & MASK32
    x ^= x >> 15
    x = (x * 0x846CA68B) & MASK32
    x ^= x >> 16
    return x


def hash32(x: np.ndarray) -> np.ndarray:
    """lowbias32 vectorisé (uint32, multiplication modulo 2^32)."""
    x = x.astype(U32, copy=True)
    x ^= x >> U32(16)
    x *= U32(0x7FEB352D)
    x ^= x >> U32(15)
    x *= U32(0x846CA68B)
    x ^= x >> U32(16)
    return x


def salted(seed: int, salt: int) -> int:
    """Graine dérivée d'une couche : hash32(seed &+ salt &* 0x9E3779B9)."""
    return hash32_int((seed + (salt * 0x9E3779B9 & MASK32)) & MASK32)


def hash_u32(a, b, s: int) -> np.ndarray:
    """h(a, b, s) = hash32(a ^ hash32(b ^ s)) ; a, b entiers >= 0 (tableaux)."""
    a = np.asarray(a).astype(U32)
    b = np.asarray(b).astype(U32)
    return hash32(a ^ hash32(b ^ U32(s)))


def hash01(a, b, s: int) -> np.ndarray:
    """[0, 1) en float32 : Float(h >> 8) * 2^-24 (exact)."""
    return (hash_u32(a, b, s) >> U32(8)).astype(F) * F(5.9604644775390625e-08)


def value_noise(x: np.ndarray, y: np.ndarray, s: int, period_x: int = 0) -> np.ndarray:
    """Bruit de valeur 2D (réseau entier haché, interpolation smoothstep). x, y ramenés à >= 0.
    period_x > 0 : périodique en x (indices modulo period_x)."""
    x = np.maximum(np.asarray(x, dtype=F), F(0))
    y = np.maximum(np.asarray(y, dtype=F), F(0))
    fx = np.floor(x)
    fy = np.floor(y)
    ix = fx.astype(np.int64)
    iy = fy.astype(np.int64)
    tx = x - fx
    ty = y - fy
    sx = tx * tx * (F(3) - F(2) * tx)
    sy = ty * ty * (F(3) - F(2) * ty)
    if period_x > 0:
        ix0 = ix % period_x
        ix1 = (ix + 1) % period_x
    else:
        ix0 = ix
        ix1 = ix + 1
    iy1 = iy + 1
    a = hash01(ix0, iy, s)
    b = hash01(ix1, iy, s)
    c = hash01(ix0, iy1, s)
    d = hash01(ix1, iy1, s)
    top = a + (b - a) * sx
    bot = c + (d - c) * sx
    return top + (bot - top) * sy


def smoothstep(e0, e1, x):
    """t = clamp((x - e0)/(e1 - e0), 0, 1) ; t*t*(3 - 2t) — e0, e1 convertis en float32 AVANT la soustraction."""
    e0 = F(e0) if not isinstance(e0, np.ndarray) else e0
    e1 = F(e1) if not isinstance(e1, np.ndarray) else e1
    t = (x - e0) / (e1 - e0)
    t = np.minimum(np.maximum(t, F(0)), F(1))
    return t * t * (F(3) - F(2) * t)


def mix(a, b, t):
    """a + (b - a) * t (t scalaire ou (…,1) pour des couleurs)."""
    return a + (b - a) * t


def clamp01(x):
    return np.minimum(np.maximum(x, F(0)), F(1))


# Sels des couches de bruit (identiques en Swift, CoatNoise.Salt).
SALT = {
    "grey": 0x1001, "flea": 0x1002, "flea2": 0x1003, "roan": 0x1004, "roan2": 0x1005, "bar": 0x1006,
    "tob": 0x1007, "ov": 0x1008, "ov2": 0x1009, "sab": 0x100A, "sab2": 0x100B, "spl": 0x100C, "dw": 0x100D,
    "lp": 0x100E, "lpd": 0x100F, "var": 0x1010, "var2": 0x1011, "face": 0x1012, "mot": 0x1013, "frk": 0x1014,
    "hoof": 0x1015, "sec": 0x1016, "wht": 0x1017, "iris": 0x1018, "vair": 0x1019, "gran": 0x101A,
    "leg": 0x1020, "erm": 0x1030,
}

# ---------------------------------------------------------------------------------------------
# Configuration (clés = noms des propriétés Swift ; valeurs d'énumérations = rawValue Swift)
# ---------------------------------------------------------------------------------------------

# rawValue -> nom du cas Swift (sert à générer CoatPresets.swift).
ENUMS = {
    "ExtensionGenotype": {"E": "blackAllowed", "ee": "redOnly"},
    "AgoutiGenotype": {"A": "bay", "At": "sealBrown", "aa": "black"},
    "CreamPearlGenotype": {"N/N": "noDilution", "Cr/N": "cream", "Cr/Cr": "doubleCream", "prl/N": "pearlCarrier",
                           "prl/prl": "pearl", "Cr/prl": "creamPearl"},
    "Zygosity": {"n/n": "absent", "X/n": "heterozygous", "X/X": "homozygous"},
    "FaceMarkingKind": {"none": "absent", "star": "star", "strip": "strip", "blaze": "blaze", "baldFace": "baldFace"},
    "IrisStyle": {"automatic": "automatic", "brown": "brown", "amber": "amber", "blue": "blue", "vairon": "vairon"},
}

# Type Swift de chaque champ énuméré (chemin -> type).
ENUM_FIELDS = {
    "genotype.extensionLocus": "ExtensionGenotype",
    "genotype.agouti": "AgoutiGenotype",
    "genotype.creamPearl": "CreamPearlGenotype",
    "face.kind": "FaceMarkingKind",
    "irisStyle": "IrisStyle",
}
ZYGOSITY_FIELDS = ["dun", "silver", "champagne", "grey", "roan", "tobiano", "frameOvero", "sabino",
                   "splashedWhite", "dominantWhite", "leopardComplex", "patternOne"]
for _z in ZYGOSITY_FIELDS:
    ENUM_FIELDS["genotype." + _z] = "Zygosity"

LEG_KEYS = ["frontLeft", "frontRight", "hindLeft", "hindRight"]   # ordre AG, AD, PG, PD (régions 5-8 / 9-12)


def plain_config() -> dict:
    """Configuration neutre (bai moyen, aucune marque) = `CoatConfiguration.plain` en Swift."""
    genotype = {"extensionLocus": "E", "agouti": "A", "creamPearl": "N/N"}
    for z in ZYGOSITY_FIELDS:
        genotype[z] = "n/n"
    leg = {"height": 0.0, "irregularity": 0.3, "ermine": False}
    return {
        "genotype": genotype,
        "expression": {
            "shade": 0.0, "sooty": 0.0, "pangare": 0.0, "flaxen": 0.0, "dapples": 0.0,
            "pointsHeight": 0.5, "primitiveMarkings": 1.0,
            "greyStage": 0.0, "greyDapples": 0.6, "fleabitten": 0.0,
            "roanDensity": 0.6,
            "tobianoCoverage": 0.45, "overoCoverage": 0.4, "sabinoCoverage": 0.35, "splashCoverage": 0.4,
            "dominantWhiteCoverage": 0.9,
            "leopardCoverage": 0.45, "spotSize": 0.5, "spotDensity": 0.6, "varnish": 0.0,
        },
        "face": {"kind": "none", "size": 1.0, "offsetU": 0.0, "offsetV": 0.0, "snip": False, "lips": False,
                 "irregularity": 0.4},
        "legs": {k: dict(leg) for k in LEG_KEYS},
        "hair": {"tipLightening": 0.0, "whiteStrands": 0.0, "secondaryFraction": 0.0},
        "irisStyle": "automatic",
        "overrides": {},
        "seed": 1,
    }


def default_config() -> dict:
    """`CoatConfiguration.default` : bai avec étoile (SPEC §4 : coat_albedo_default.png)."""
    c = plain_config()
    c["face"]["kind"] = "star"
    return c


def deep_merge(base: dict, diff: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in diff.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "overrides":
            out[k] = deep_merge(out[k], v)
        elif isinstance(v, dict) and k == "overrides":
            o = dict(out.get(k) or {})
            o.update(v)
            out[k] = o
        else:
            out[k] = copy.deepcopy(v)
    return out


def config_to_json(cfg: dict) -> str:
    """JSON compatible avec le décodeur Codable synthétisé (optionnels nil = clés absentes ; couleurs {r,g,b})."""
    c = copy.deepcopy(cfg)
    c["overrides"] = {k: color_json(v) for k, v in (c.get("overrides") or {}).items() if v is not None}
    if c["hair"].get("secondaryColor") is not None:
        c["hair"]["secondaryColor"] = color_json(c["hair"]["secondaryColor"])
    else:
        c["hair"].pop("secondaryColor", None)
    return json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------------------------
# Présets (noms FR). Différences par rapport à plain_config(). Couleurs hex : [A].
# ---------------------------------------------------------------------------------------------

def _legs(fl=0.0, fr=0.0, hl=0.0, hr=0.0, ermine=()):
    d = {}
    for k, h in zip(LEG_KEYS, (fl, fr, hl, hr)):
        if h > 0 or k in ermine:
            d[k] = {"height": float(h)}
            if k in ermine:
                d[k]["ermine"] = True
    return d


RED = {"extensionLocus": "ee"}
HET = "X/n"
HOM = "X/X"

PRESETS = [
    ("alezan", "Alezan", "e/e — robe rouge uniforme, crins de la même couleur.",
     {"genotype": RED, "face": {"kind": "star", "size": 0.8}, "legs": _legs(hl=0.18)}),
    ("alezan_crins_laves", "Alezan crins lavés", "e/e + crins lavés (flaxen, polygénique).",
     {"genotype": RED, "expression": {"shade": -0.2, "flaxen": 0.9}, "face": {"kind": "blaze"},
      "legs": _legs(hl=0.25, hr=0.12), "hair": {"tipLightening": 0.2}}),
    ("alezan_brule", "Alezan brûlé", "e/e, nuance foncée (liver) + léger charbonné.",
     {"genotype": RED, "expression": {"shade": 1.0, "sooty": 0.3}, "face": {"kind": "star", "size": 0.6}}),
    ("bai", "Bai", "E/_ A/_ — corps rouge, extrémités noires (préset par défaut).",
     {"face": {"kind": "star"}}),
    ("bai_brun", "Bai brun", "E/_ At/_ — presque noir, zones feu (bout du nez, flancs).",
     {"genotype": {"agouti": "At"}, "expression": {"sooty": 0.3}, "legs": _legs(hr=0.08)}),
    ("noir", "Noir", "E/_ a/a — eumélanine partout.",
     {"genotype": {"agouti": "aa"}, "face": {"kind": "star", "size": 0.7, "offsetV": 0.02}}),
    ("palomino", "Palomino", "e/e Cr/n — alezan dilué en doré, crins presque blancs.",
     {"genotype": {"extensionLocus": "ee", "creamPearl": "Cr/N"}, "face": {"kind": "blaze", "snip": True},
      "legs": _legs(fl=0.15, hl=0.3, hr=0.3)}),
    ("isabelle", "Isabelle", "E/_ A/_ Cr/n — bai dilué, extrémités noires.",
     {"genotype": {"creamPearl": "Cr/N"}, "face": {"kind": "star", "size": 0.6}}),
    ("souris", "Souris", "E/_ a/a D/_ — noir dilué par le dun, marques primitives.",
     {"genotype": {"agouti": "aa", "dun": HET}}),
    ("creme", "Crème (cremello)", "e/e Cr/Cr — double dilution : peau rose, yeux bleus.",
     {"genotype": {"extensionLocus": "ee", "creamPearl": "Cr/Cr"}, "face": {"kind": "blaze"}}),
    ("gris_pommele", "Gris pommelé", "G/_ (stade moyen) — pommelures sur base noire.",
     {"genotype": {"agouti": "aa", "grey": HET}, "expression": {"greyStage": 0.5, "greyDapples": 1.0},
      "face": {"kind": "star", "size": 0.7}}),
    ("gris_truite", "Gris truité", "G/_ (stade avancé) — blanc moucheté de poils colorés.",
     {"genotype": {"extensionLocus": "ee", "grey": HET}, "expression": {"greyStage": 0.95, "fleabitten": 0.8}}),
    ("rouan", "Rouan (bai)", "E/_ A/_ Rn/_ — poils blancs mêlés, tête et bas des membres foncés.",
     {"genotype": {"roan": HET}, "expression": {"roanDensity": 0.7}, "face": {"kind": "star", "size": 0.6}}),
    ("aubere", "Aubère", "e/e Rn/_ — rouan sur base alezane.",
     {"genotype": {"extensionLocus": "ee", "roan": HET}, "expression": {"roanDensity": 0.65, "flaxen": 0.3},
      "face": {"kind": "strip"}, "legs": _legs(hl=0.15)}),
    ("pie_tobiano", "Pie tobiano (bai)", "To/_ — plaques blanches franches qui croisent le dos.",
     {"genotype": {"tobiano": HET}, "expression": {"tobianoCoverage": 0.5}, "face": {"kind": "star"},
      "legs": _legs(0.55, 0.55, 0.6, 0.6), "hair": {"whiteStrands": 0.35}}),
    ("pie_overo", "Pie overo (alezan)", "e/e O/n — blanc horizontal sur les flancs, belle face.",
     {"genotype": {"extensionLocus": "ee", "frameOvero": HET}, "expression": {"overoCoverage": 0.5},
      "face": {"kind": "baldFace", "size": 1.1}, "irisStyle": "vairon"}),
    ("appaloosa_leopard", "Appaloosa léopard", "LP/n PATN1/_ — blanc couvert de taches ovales.",
     {"genotype": {"leopardComplex": HET, "patternOne": HET}, "expression": {"spotSize": 0.5, "spotDensity": 0.75},
      "face": {"kind": "strip"}}),
    ("appaloosa_couverture", "Appaloosa couverture", "LP/n — couverture blanche tachetée sur le dos et la croupe.",
     {"genotype": {"leopardComplex": HET}, "expression": {"leopardCoverage": 0.5, "spotSize": 0.45,
                                                          "spotDensity": 0.6},
      "face": {"kind": "blaze", "size": 0.8}, "legs": _legs(hl=0.2, hr=0.2)}),
    ("pangare", "Pangaré (type Exmoor)", "E/_ A/_ + pangaré : bout du nez, tour des yeux, ventre clairs ; sans blanc.",
     {"expression": {"pangare": 0.95, "shade": 0.2, "sooty": 0.2, "pointsHeight": 0.35}}),
    ("champagne_dore", "Champagne doré", "e/e Ch/_ — doré, peau rose tachetée, yeux ambre.",
     {"genotype": {"extensionLocus": "ee", "champagne": HET}, "face": {"kind": "blaze", "size": 0.9},
      "legs": _legs(fl=0.12, fr=0.12)}),
    ("silver_noir", "Silver (noir)", "E/_ a/a Z/_ — noir dilué en chocolat, crins lavés argentés.",
     {"genotype": {"agouti": "aa", "silver": HET}, "expression": {"dapples": 0.6}, "face": {"kind": "star"}}),
    ("bai_dun", "Bai dun", "E/_ A/_ D/_ — corps sable, raie de mulet, zébrures.",
     {"genotype": {"dun": HET}, "face": {"kind": "star", "size": 0.5}}),
    ("gris_fer", "Gris fer", "G/_ (début) — poils blancs mêlés sur base noire.",
     {"genotype": {"agouti": "aa", "grey": HET}, "expression": {"greyStage": 0.25}}),
    ("pie_sabino", "Pie sabino (bai)", "Sb1/n — balzanes hautes, liste large, bords rouannés.",
     {"genotype": {"sabino": HET}, "expression": {"sabinoCoverage": 0.4}, "face": {"kind": "blaze", "size": 1.3,
                                                                                  "lips": True},
      "legs": _legs(0.6, 0.45, 0.7, 0.65)}),
]


def preset_configs() -> list:
    """[(id, nom, résumé, config complète)] dans l'ordre de CoatPreset.all."""
    base = plain_config()
    return [(pid, name, summary, deep_merge(base, diff)) for pid, name, summary, diff in PRESETS]


# ---------------------------------------------------------------------------------------------
# Palette : génotype -> couleurs linéaires (float64 puis float32)
# ---------------------------------------------------------------------------------------------

# Tables de couleurs sRGB. TOUTES [A] (approximations artistiques d'après anatomy.md §4.2, elles-mêmes [A]).
HEX_WHITE_HAIR = "#F3F0EA"
RAMP_CHESTNUT = ("#C8843F", "#A65A2A", "#5A2E1A")      # clair, moyen, brûlé
RAMP_BAY = ("#B06A32", "#8B4A22", "#5C3018")           # bai clair, cerise/moyen, foncé
RAMP_SEAL = ("#5A3420", "#3D2216", "#2A1810")          # bai brun
RAMP_BLACK = ("#2E2622", "#1A1716", "#0E0D0D")         # noir mal teint, noir, noir jais
HEX_EU_POINTS = "#17120F"
HEX_EU_MANE = "#141110"
HEX_FLAXEN = "#E6D3A8"
HEX_GREY_DARK = "#5C5C5A"
HEX_GREY_LIGHT = "#ECEBE6"
HEX_FLECK_RED = "#8B5A3C"
HEX_FLECK_BLACK = "#3A302A"
HEX_MEALY = "#E0C89E"
HEX_SKIN_DARK = "#2B2525"
HEX_SKIN_PINK = "#DCA295"
HEX_SKIN_CHAMPAGNE = "#B88E7E"
HEX_FRECKLE = "#5A4038"
HEX_HOOF_DARK = "#2E2A27"
HEX_HOOF_LIGHT = "#D2C2A0"
HEX_CHESTNUT_HORN = "#3A332E"
HEX_CHESTNUT_HORN_LIGHT = "#8C7F72"
HEX_MANE_WHITE = "#E8E4DC"
HEX_EYE_BROWN = "#4A2E19"
HEX_EYE_BLUE = "#8FB7D8"
HEX_EYE_AMBER = "#B07A2A"
HEX_EYE_LIGHT = "#B49A5E"
HEX_PUPIL = "#070505"
HEX_GRANULA = "#1C120C"
HEX_SCLERA_DARK = "#3A2A22"
HEX_SCLERA_WHITE = "#E8E2D8"

# Bases de référence des facteurs de densité (pigment non dilué) par « emplacement ».
SLOT_BASE = {"pheoBody": RAMP_CHESTNUT[1], "pheoBay": RAMP_BAY[1], "pheoMane": RAMP_CHESTNUT[1],
             "euBody": RAMP_BLACK[1], "euPoints": HEX_EU_POINTS, "euMane": HEX_EU_MANE}
# Cibles [A] : couleur obtenue quand la dilution agit sur la base de référence de l'emplacement.
# Facteur par canal k = D(cible) / D(base), D(c) = -ln(lin(c) / lin(blanc)) ; appliqué : c' = blanc * (c/blanc)^k.
DILUTION_TARGETS = {
    "cream": {"pheoBody": "#D6AE62", "pheoBay": "#C6A066", "pheoMane": "#F2EBDD", "euBody": "#2A221D", "euPoints": "#1E1814",
              "euMane": "#1A1512"},
    "doubleCream": {"pheoBody": "#EDE0C6", "pheoBay": "#E8D9BD", "pheoMane": "#F2E8D4", "euBody": "#E8D8C0", "euPoints": "#D2B48C",
                    "euMane": "#D8BE98"},
    "pearl": {"pheoBody": "#DDB08A", "pheoBay": "#D2AA82", "pheoMane": "#E4C2A0", "euBody": "#5E5048", "euPoints": "#4A3E36",
              "euMane": "#4A3E36"},
    "creamPearl": {"pheoBody": "#EAD6B8", "pheoBay": "#E2CCAA", "pheoMane": "#EEDFC6", "euBody": "#D2C0A6", "euPoints": "#B89C7E",
                   "euMane": "#C0A688"},
    "dun": {"pheoBody": "#CC9566", "pheoBay": "#BC9B6A", "euBody": "#7A726A"},
    "silver": {"euBody": "#5A4A42", "euPoints": "#4A3B33", "euMane": "#E0D4C2"},
    "champagne": {"pheoBody": "#D8B37A", "pheoBay": "#C8A270", "pheoMane": "#E6D2A8", "euBody": "#9C8A7A", "euPoints": "#6E5646",
                  "euMane": "#7A6252"},
}
SLOTS = ("pheoBody", "pheoBay", "pheoMane", "euBody", "euPoints", "euMane")


def _srgb64(h):
    """'#RRGGBB' ou {r,g,b} -> composantes sRGB float32 promues en float64 (comme Double(Float) en Swift)."""
    return [float(v) for v in color_srgb(h)]


def _lin64(srgb):
    return [srgb_to_linear_f64(v) for v in srgb]


def _ramp64(ramp, shade: float):
    """Interpolation sRGB (float64) clair(-1) / moyen(0) / foncé(+1)."""
    light, mid, dark = (_srgb64(h) for h in ramp)
    t = min(max(shade, -1.0), 1.0)
    if t < 0:
        return [m + (l - m) * (-t) for m, l in zip(mid, light)]
    return [m + (d - m) * t for m, d in zip(mid, dark)]


_W64 = None


def _white64():
    global _W64
    if _W64 is None:
        _W64 = _lin64(_srgb64(HEX_WHITE_HAIR))
    return _W64


def _density64(lin):
    w = _white64()
    return [-math.log(min(max(c / wc, 1e-4), 1.0)) for c, wc in zip(lin, w)]


def _dilution_factor64(gene: str, slot: str):
    tgt = DILUTION_TARGETS[gene].get(slot)
    if tgt is None:
        return [1.0, 1.0, 1.0]
    db = _density64(_lin64(_srgb64(SLOT_BASE[slot])))
    dt = _density64(_lin64(_srgb64(tgt)))
    return [t / b if b > 1e-6 else 1.0 for t, b in zip(dt, db)]


def _apply_density64(lin, k):
    """c' = blanc * exp(-D(c) * k) (float64)."""
    w = _white64()
    d = _density64(lin)
    return [wc * math.exp(-dc * kc) for wc, dc, kc in zip(w, d, k)]


def _densify64(lin, k: float):
    return _apply_density64(lin, [k, k, k])


def _mix64(a, b, t: float):
    return [x + (y - x) * t for x, y in zip(a, b)]


def _f32v(v) -> np.ndarray:
    return np.array([F(x) for x in v], dtype=F)


ZYG = {"n/n": 0, "X/n": 1, "X/X": 2}


class Landmarks:
    """Repères des cartes (CoatLandmarks en Swift). Valeurs par défaut [I] d'après Pipeline/pony/template.py :
    couronne ≈ 0.07 m / coude 0.71 m ≈ 0.10 en hauteur de jambe ; yeux à v facial ≈ 0.62, |u - 0.5| ≈ 0.36."""

    def __init__(self, coronet=0.10, face_eye_v=0.62, face_eye_u=0.36, nostril_v=0.10):
        self.coronet = F(coronet)
        self.face_eye_v = F(face_eye_v)
        self.face_eye_u = F(face_eye_u)
        self.nostril_v = F(nostril_v)

    def to_dict(self):
        return {"coronet": float(self.coronet), "faceEyeV": float(self.face_eye_v),
                "faceEyeU": float(self.face_eye_u), "nostrilV": float(self.nostril_v)}


def f32(v) -> float:
    """Valeur de configuration telle que stockée en Swift (Float), promue en float64."""
    return float(F(v))


def _clamp(v, lo=0.0, hi=1.0):
    return min(max(f32(v), lo), hi)


class Palette:
    """Palette résolue (CoatPalette en Swift). Couleurs linéaires float32 (3,), scalaires float32."""


def palette(cfg: dict) -> Palette:
    """Génotype + expression -> palette linéaire. Calculs en float64 puis float32 (comme Swift en Double)."""
    g = cfg["genotype"]
    e = cfg["expression"]
    ov = cfg.get("overrides") or {}
    z = {k: ZYG[g[k]] for k in ZYGOSITY_FIELDS}
    shade = _clamp(e["shade"], -1.0, 1.0)
    red = g["extensionLocus"] == "ee"
    agouti = g["agouti"]
    cp = g["creamPearl"]

    # Gènes de dilution actifs (ordre fixe : leurs facteurs se multiplient, l'ordre n'importe pas).
    genes = []
    if cp == "Cr/N":
        genes.append("cream")
    elif cp == "Cr/Cr":
        genes.append("doubleCream")
    elif cp == "prl/prl":
        genes.append("pearl")
    elif cp == "Cr/prl":
        genes.append("creamPearl")
    if z["silver"] > 0:
        genes.append("silver")
    if z["champagne"] > 0:
        genes.append("champagne")
    dun = z["dun"] > 0

    def factor(slot, include_dun=True):
        k = [1.0, 1.0, 1.0]
        for gene in genes:
            f = _dilution_factor64(gene, slot)
            k = [a * b for a, b in zip(k, f)]
        if dun and include_dun:
            f = _dilution_factor64("dun", slot)
            k = [a * b for a, b in zip(k, f)]
        return k

    white = _lin64(_srgb64(HEX_WHITE_HAIR))
    eu_points = _apply_density64(_lin64(_srgb64(HEX_EU_POINTS)), factor("euPoints", include_dun=False))
    eu_mane = _apply_density64(_lin64(_srgb64(HEX_EU_MANE)), factor("euMane", include_dun=False))

    if red:
        base = _lin64(_ramp64(RAMP_CHESTNUT, shade))
        body = _apply_density64(base, factor("pheoBody"))
        body_nodun = _apply_density64(base, factor("pheoBody", include_dun=False))
        points = _densify64(body_nodun, 1.12)
        points_amount = 0.35
        mane = _densify64(_apply_density64(base, factor("pheoMane", include_dun=False)), 1.08)
        flaxen = _apply_density64(_lin64(_srgb64(HEX_FLAXEN)), factor("pheoMane", include_dun=False))
        mane = _mix64(mane, flaxen, _clamp(e["flaxen"]))
        primitive_color = _densify64(body_nodun, 1.25)
        fleck = _lin64(_srgb64(HEX_FLECK_RED))
    else:
        if agouti == "A":
            base = _lin64(_ramp64(RAMP_BAY, shade))
            body = _apply_density64(base, factor("pheoBay"))
            fleck = _mix64(_lin64(_srgb64(HEX_FLECK_RED)), _lin64(_srgb64(HEX_FLECK_BLACK)), 0.5)
        elif agouti == "At":
            base = _lin64(_ramp64(RAMP_SEAL, shade))
            body = _apply_density64(base, factor("euBody"))
            fleck = _lin64(_srgb64(HEX_FLECK_BLACK))
        else:
            base = _lin64(_ramp64(RAMP_BLACK, shade))
            body = _apply_density64(base, factor("euBody"))
            fleck = _lin64(_srgb64(HEX_FLECK_BLACK))
        points = eu_points
        points_amount = 1.0
        mane = eu_mane
        primitive_color = eu_points

    # Surcharges libres (mode « libre ») : couleur finale du poil, avant modificateurs.
    if ov.get("body"):
        body = _lin64(_srgb64(ov["body"]))
    if ov.get("points"):
        points = _lin64(_srgb64(ov["points"]))
        points_amount = 1.0

    # Modificateurs
    sooty = _densify64(body, 1.8)
    if not red:
        sooty = _mix64(sooty, points, 0.25)
    mealy = _mix64(_densify64(body, 0.30), _lin64(_srgb64(HEX_MEALY)), 0.4)
    pangare_amount = _clamp(e["pangare"])
    pangare = mealy
    if (not red) and agouti == "At" and not ov.get("body"):
        # Bai brun : zones « feu » (bout du nez, flancs, coudes) = pigment rouge du bai, via le masque pangaré.
        tan = _apply_density64(_lin64(_ramp64(RAMP_BAY, shade - 0.4)), factor("pheoBay"))
        pangare = _mix64(tan, mealy, pangare_amount)
        pangare_amount = max(pangare_amount, 0.55)

    P = Palette()
    P.white = _f32v(white)
    P.body = _f32v(body)
    P.points = _f32v(points)
    P.pointsAmount = F(points_amount)
    P.pointsHeight = F(_clamp(e["pointsHeight"]))
    P.sooty = _f32v(sooty)
    P.sootyAmount = F(_clamp(e["sooty"]))
    P.pangare = _f32v(pangare)
    P.pangareAmount = F(pangare_amount)
    P.innerEar = _f32v(_mix64(_densify64(body, 0.55), white, 0.25))
    P.primitive = F(_clamp(e["primitiveMarkings"]) if dun else 0.0)
    P.primitiveColor = _f32v(primitive_color)
    P.dapples = F(_clamp(e["dapples"]))

    grey_on = z["grey"] > 0
    P.greyStage = F(_clamp(e["greyStage"]) if grey_on else 0.0)
    P.greyDapples = F(_clamp(e["greyDapples"]))
    P.fleabitten = F(_clamp(e["fleabitten"]) if grey_on else 0.0)
    P.greyDark = _f32v(_mix64(_lin64(_srgb64(HEX_GREY_DARK)), body, 0.2))
    P.greyLight = _f32v(_lin64(_srgb64(HEX_GREY_LIGHT)))
    P.fleck = _f32v(fleck)

    P.roan = F(_clamp(e["roanDensity"]) if z["roan"] > 0 else 0.0)
    P.tobiano = F(_clamp(e["tobianoCoverage"]) if z["tobiano"] > 0 else 0.0)
    P.overo = F(_clamp(e["overoCoverage"]) if z["frameOvero"] > 0 else 0.0)
    sab = _clamp(e["sabinoCoverage"]) if z["sabino"] > 0 else 0.0
    if z["sabino"] == 2:
        sab = min(1.0, sab + 0.35)       # Sb1/Sb1 : quasi blanc [NV]
    P.sabino = F(sab)
    spl = _clamp(e["splashCoverage"]) if z["splashedWhite"] > 0 else 0.0
    if z["splashedWhite"] == 2:
        spl = min(1.0, spl + 0.2)
    P.splash = F(spl)
    P.dominantWhite = F(_clamp(e["dominantWhiteCoverage"]) if z["dominantWhite"] > 0 else 0.0)

    lp = z["leopardComplex"]
    patn = z["patternOne"] > 0
    P.lp = F(1.0 if lp > 0 else 0.0)
    P.lpFull = F(1.0 if (lp > 0 and patn) else 0.0)          # léopard / peu taché : tout le corps blanc
    P.lpCoverage = F(_clamp(e["leopardCoverage"]))
    spot_density = _clamp(e["spotDensity"])
    if lp == 2:
        spot_density *= 0.15                                  # LP/LP : peu taché / « snowcap » [NV]
    P.spotDensity = F(spot_density)
    P.spotSize = F(_clamp(e["spotSize"]))
    P.varnish = F(_clamp(e["varnish"]) if lp > 0 else 0.0)

    # Peau
    pink_all = 0.0
    if cp in ("Cr/Cr", "Cr/prl"):
        pink_all = 1.0
    if P.dominantWhite >= F(0.85):
        pink_all = 1.0
    P.pinkAll = F(pink_all)
    skin_dark = _lin64(_srgb64(HEX_SKIN_DARK))
    P.freckles = F(0.0)
    if z["champagne"] > 0:
        skin_dark = _lin64(_srgb64(HEX_SKIN_CHAMPAGNE))
        P.freckles = F(1.0)
    if ov.get("skin"):
        skin_dark = _lin64(_srgb64(ov["skin"]))
    P.skinDark = _f32v(skin_dark)
    P.skinPink = _f32v(_lin64(_srgb64(HEX_SKIN_PINK)))
    P.freckle = _f32v(_lin64(_srgb64(HEX_FRECKLE)))
    P.lpMottle = F(1.0 if lp > 0 else 0.0)

    # Membres : seuils de balzane, irrégularité, hermine ; sabots
    face = cfg["face"]
    legs = cfg["legs"]
    P.legHeight = np.array([F(_clamp(legs[k]["height"])) for k in LEG_KEYS], dtype=F)
    P.legIrregularity = np.array([F(_clamp(legs[k]["irregularity"])) for k in LEG_KEYS], dtype=F)
    P.legErmine = np.array([F(1.0 if legs[k]["ermine"] else 0.0) for k in LEG_KEYS], dtype=F)
    hw = []
    hs = []
    for k in LEG_KEYS:
        h = _clamp(legs[k]["height"])
        hw.append(1.0 if h > 0 else 0.0)
        stripe = 1.0 if (h > 0 and (legs[k]["ermine"] or h < 0.04)) else 0.0
        if lp > 0:
            stripe = 1.0
        hs.append(stripe)
    P.hoofWhite = np.array([F(v) for v in hw], dtype=F)
    P.hoofStripe = np.array([F(v) for v in hs], dtype=F)
    P.hoofDark = _f32v(_lin64(_srgb64(HEX_HOOF_DARK)))
    P.hoofLight = _f32v(_lin64(_srgb64(HEX_HOOF_LIGHT)))
    P.hoofOverride = F(1.0 if ov.get("hooves") else 0.0)
    P.hoofOverrideColor = _f32v(_lin64(_srgb64(ov["hooves"])) if ov.get("hooves") else [0.0, 0.0, 0.0])
    P.chestnutDark = _f32v(_lin64(_srgb64(HEX_CHESTNUT_HORN)))
    P.chestnutLight = _f32v(_lin64(_srgb64(HEX_CHESTNUT_HORN_LIGHT)))

    # Marques de tête
    kinds = {"none": 0, "star": 1, "strip": 2, "blaze": 3, "baldFace": 4}
    P.faceKind = kinds[face["kind"]]
    P.faceSize = F(_clamp(face["size"], 0.3, 2.0))
    P.faceOffsetU = F(_clamp(face["offsetU"], -0.2, 0.2))
    P.faceOffsetV = F(_clamp(face["offsetV"], -0.2, 0.2))
    P.faceSnip = F(1.0 if face["snip"] else 0.0)
    P.faceLips = F(1.0 if face["lips"] else 0.0)
    P.faceIrregularity = F(_clamp(face["irregularity"]))

    seed = int(cfg["seed"]) & MASK32
    P.seed = seed
    P.s = {k: salted(seed, v) for k, v in SALT.items() if k not in ("leg", "erm")}
    P.sLeg = [salted(seed, SALT["leg"] + i) for i in range(4)]
    P.sErm = [salted(seed, SALT["erm"] + i) for i in range(4)]

    # Crins
    hair = cfg["hair"]
    mane_c = mane
    if ov.get("mane"):
        mane_c = _lin64(_srgb64(ov["mane"]))
    P.mane = _f32v(mane_c)
    tip_target = _mix64(mane_c, _lin64(_srgb64(HEX_FLAXEN)), 0.6)
    P.maneTip = _f32v(tip_target)
    P.maneTipAmount = F(_clamp(hair["tipLightening"]))
    P.maneWhite = _f32v(_lin64(_srgb64(HEX_MANE_WHITE)))
    white_strands = _clamp(hair["whiteStrands"])
    if grey_on:
        gs = _clamp(e["greyStage"])
        t = min(max((gs - 0.05) / 0.70, 0.0), 1.0)
        white_strands = max(white_strands, t * t * (3.0 - 2.0 * t))    # les crins grisonnent plus vite [NV]
    if P.dominantWhite >= F(0.85):
        white_strands = max(white_strands, 0.9)          # blanc dominant étendu : crins blancs [NV]
    P.maneWhiteFraction = F(white_strands)
    sec = hair.get("secondaryColor")
    P.maneSecondary = _f32v(_lin64(_srgb64(sec)) if sec else mane_c)
    P.maneSecondaryFraction = F(_clamp(hair["secondaryFraction"]) if sec else 0.0)

    # Yeux
    P.iris = iris_palette(cfg)
    return P


def eye_kind(cfg: dict) -> str:
    """Couleur d'œil dérivée : 'brown' | 'amber' | 'blue' | 'light' | 'vairon' (IrisStyle.automatic résolu)."""
    style = cfg.get("irisStyle", "automatic")
    if style != "automatic":
        return style
    g = cfg["genotype"]
    e = cfg["expression"]
    cp = g["creamPearl"]
    if cp == "Cr/Cr":
        return "blue"
    if ZYG[g["splashedWhite"]] > 0:
        return "blue"
    face = cfg["face"]
    if face["kind"] == "baldFace" and f32(face["size"]) >= 1.25:
        return "blue"
    if ZYG[g["frameOvero"]] > 0 and f32(e["overoCoverage"]) >= 0.75:
        return "blue"
    if cp == "Cr/prl":
        return "light"
    if ZYG[g["champagne"]] > 0:
        return "amber"
    return "brown"


def iris_palette(cfg: dict) -> dict:
    ov = cfg.get("overrides") or {}
    kind = eye_kind(cfg)
    base = {"brown": HEX_EYE_BROWN, "amber": HEX_EYE_AMBER, "blue": HEX_EYE_BLUE, "light": HEX_EYE_LIGHT,
            "vairon": HEX_EYE_BROWN}[kind]
    col = _lin64(_srgb64(ov["eyes"])) if ov.get("eyes") else _lin64(_srgb64(base))
    lp = ZYG[cfg["genotype"]["leopardComplex"]] > 0
    return {
        "kind": kind,
        "base": _f32v(col),
        "blue": _f32v(_lin64(_srgb64(HEX_EYE_BLUE))),
        "vairon": F(1.0 if kind == "vairon" else 0.0),
        "pupil": _f32v(_lin64(_srgb64(HEX_PUPIL))),
        "granula": _f32v(_lin64(_srgb64(HEX_GRANULA))),
        "sclera": _f32v(_lin64(_srgb64(HEX_SCLERA_WHITE if lp else HEX_SCLERA_DARK))),
        "blueFibers": F(1.0 if kind in ("blue", "light") else 0.0),
        "sIris": salted(int(cfg["seed"]) & MASK32, SALT["iris"]),
        "sVair": salted(int(cfg["seed"]) & MASK32, SALT["vair"]),
        "sGran": salted(int(cfg["seed"]) & MASK32, SALT["gran"]),
    }


def phenotype(cfg: dict) -> dict:
    """Résumé lisible (sRGB hex) des couleurs dérivées : utile pour l'UI et les tests (CoatPhenotype en Swift)."""
    P = palette(cfg)

    def hx(lin):
        return srgb_to_hex([linear_to_srgb_f64(float(v)) for v in lin])

    hooves = []
    for i in range(4):
        if P.hoofOverride > 0:
            hooves.append("custom")
        elif P.hoofStripe[i] > 0:
            hooves.append("striped")
        elif P.hoofWhite[i] > 0 or P.pinkAll > 0:
            hooves.append("light")
        else:
            hooves.append("dark")
    return {"body": hx(P.body), "points": hx(P.points), "mane": hx(P.mane), "eye": eye_kind(cfg),
            "eyeColor": hx(P.iris["base"]), "skin": hx(P.skinPink if P.pinkAll > 0 else P.skinDark), "hooves": hooves,
            "pinkSkin": bool(P.pinkAll > 0)}


# ---------------------------------------------------------------------------------------------
# Échantillonnage des cartes
# ---------------------------------------------------------------------------------------------


def _axis_tables(map_size: int, out_size: int):
    """Tables bilinéaires (i0, i1, w) et plus-proche-voisin pour un axe. Identique à CoatAxisTable (Swift)."""
    scale = F(map_size) / F(out_size)
    pos = np.arange(out_size, dtype=F) + F(0.5)
    f = pos * scale - F(0.5)
    f = np.minimum(np.maximum(f, F(0)), F(map_size - 1))
    i0 = np.floor(f).astype(np.int64)
    i1 = np.minimum(i0 + 1, map_size - 1)
    w = f - i0.astype(F)
    nearest = np.minimum((pos * scale).astype(np.int64), map_size - 1)
    return i0, i1, w.astype(F), nearest


def _bilinear_band(img: np.ndarray, rows, cols) -> np.ndarray:
    """img uint8 (H, W, 4) ; rows/cols = tables d'axe restreintes à la bande. -> float32 (h, w, 4)."""
    y0, y1, wy, _ = rows
    x0, x1, wx, _ = cols
    p00 = img[np.ix_(y0, x0)].astype(F) / F(255)
    p10 = img[np.ix_(y0, x1)].astype(F) / F(255)
    p01 = img[np.ix_(y1, x0)].astype(F) / F(255)
    p11 = img[np.ix_(y1, x1)].astype(F) / F(255)
    wxb = wx[None, :, None]
    wyb = wy[:, None, None]
    top = p00 + (p10 - p00) * wxb
    bot = p01 + (p11 - p01) * wxb
    return top + (bot - top) * wyb


def _slice_axis(t, a, b):
    return tuple(v[a:b] for v in t)


# ---------------------------------------------------------------------------------------------
# Marques (tête et membres)
# ---------------------------------------------------------------------------------------------


def _ellipse_mask(du, dv, rx, ry, n):
    q = (du / rx) * (du / rx) + (dv / ry) * (dv / ry)
    d = (np.sqrt(q) - F(1)) * np.minimum(rx, ry)
    return F(1) - smoothstep(-0.006, 0.006, d + n)


def _capsule_mask(du, dv, top, bottom, hw, n):
    cv = np.minimum(np.maximum(dv, bottom), top)
    ddv = dv - cv
    d = np.sqrt(du * du + ddv * ddv) - hw
    return F(1) - smoothstep(-0.006, 0.006, d + n)


def face_mark(P, LM, fu, fv, rid):
    """Masque blanc des marques de tête (coordonnées faciales du SPEC : u 0.5 = ligne médiane, v 0 = bout du nez)."""
    s = P.faceSize
    du = fu - F(0.5) - P.faceOffsetU
    dv = fv - P.faceOffsetV
    n = (value_noise(fu * F(28) + F(16), fv * F(28) + F(16), P.s["face"]) - F(0.5)) * (P.faceIrregularity * F(0.05))
    m = np.zeros_like(fu)
    k = P.faceKind
    ev = LM.face_eye_v
    nv = LM.nostril_v
    if k == 1:      # en tête (étoile)
        m = _ellipse_mask(du, dv - (ev + F(0.07)), F(0.075) * s, F(0.065) * s, n)
    elif k == 2:    # liste étroite (étoile + bande fine)
        star = _ellipse_mask(du, dv - (ev + F(0.07)), F(0.06) * s, F(0.055) * s, n)
        strip = _capsule_mask(du, dv, ev + F(0.06), nv + F(0.10), F(0.022) * s, n)
        m = np.maximum(star, strip)
    elif k == 3:    # liste (plus large, élargie sur le front, n'atteint pas les yeux)
        hw = F(0.07) * s * (F(1) + F(0.45) * smoothstep(ev - F(0.10), ev + F(0.10), dv))
        m = _capsule_mask(du, dv, ev + F(0.16), nv - F(0.02), hw, n)
    elif k == 4:    # belle face (déborde sur les yeux)
        hw = (LM.face_eye_u + F(0.06)) * s
        m = _capsule_mask(du, dv, ev + F(0.22), F(-0.05), hw, n)
    if P.faceSnip > 0:
        m = np.maximum(m, _ellipse_mask(du, dv - (nv - F(0.02)), F(0.06) * s, F(0.045) * s, n))
    if P.faceLips > 0:
        lip = (F(1) - smoothstep(F(0.035) * s - F(0.01), F(0.035) * s + F(0.01), fv)) * (rid == 2)
        m = np.maximum(m, lip.astype(F))
    return m


def leg_mark(P, LM, leg, ux, vy, li):
    """Masque blanc de la balzane du membre li (0..3) : hauteur continue + bord bruité + hermine."""
    h = P.legHeight[li]
    if not h > 0:
        return np.zeros_like(leg)
    thr = LM.coronet + h * (F(1) - LM.coronet)
    n = (value_noise(ux * F(55), vy * F(55), P.sLeg[li]) - F(0.5)) * F(2)
    edge = thr + n * (P.legIrregularity[li] * F(0.05))
    w = F(1) - smoothstep(edge - F(0.006), edge + F(0.006), leg)
    if P.legErmine[li] > 0:
        e = value_noise(ux * F(150), vy * F(150), P.sErm[li])
        spot = smoothstep(0.70, 0.76, e) * (F(1) - smoothstep(LM.coronet + F(0.02), LM.coronet + F(0.09), leg))
        w = w * (F(1) - spot)
    return w


def cover_mask(field, cov, e, noise):
    """Seuil de couverture : cov = 0 -> rien ; cov = 1 -> tout (pour field dans [0, 1])."""
    e = F(e)
    thr = (F(1) - cov) * (F(1) + F(2) * e) - e
    return smoothstep(-e, e, field + noise - thr)


# ---------------------------------------------------------------------------------------------
# Compositeur du corps
# ---------------------------------------------------------------------------------------------

BAND_ROWS = 128


def compose_body(cfg: dict, maps: dict, size: int, landmarks: Landmarks | None = None) -> np.ndarray:
    """Albedo sRGB RGBA8 (size, size, 4) du corps à partir des cartes du SPEC §4 (uint8 RGBA)."""
    P = palette(cfg)
    LM = landmarks or Landmarks()
    out = np.zeros((size, size, 4), dtype=np.uint8)
    tabs = {}
    for name in ("shading", "regions", "params", "patterns"):
        m = maps[name]
        tabs[name] = (_axis_tables(m.shape[0], size), _axis_tables(m.shape[1], size))
    for y0 in range(0, size, BAND_ROWS):
        y1 = min(size, y0 + BAND_ROWS)
        lin = _compose_band(P, LM, maps, tabs, size, y0, y1)
        out[y0:y1, :, :3] = encode_linear(lin)
        out[y0:y1, :, 3] = 255
    return out


def _sample(maps, tabs, name, y0, y1):
    rows, cols = tabs[name]
    return _bilinear_band(maps[name], _slice_axis(rows, y0, y1), cols)


def _compose_band(P, LM, maps, tabs, size, y0, y1):
    SH = _sample(maps, tabs, "shading", y0, y1)
    RG = _sample(maps, tabs, "regions", y0, y1)
    PA = _sample(maps, tabs, "params", y0, y1)
    PT = _sample(maps, tabs, "patterns", y0, y1)
    rrows, rcols = tabs["regions"]
    rid_byte = maps["regions"][np.ix_(rrows[3][y0:y1], rcols[3])][..., 0].astype(np.int64)
    rid = np.minimum((rid_byte + 8) // 16, 15)

    h = y1 - y0
    xs = np.broadcast_to(np.arange(size, dtype=np.int64)[None, :], (h, size))
    ys = np.broadcast_to(np.arange(y0, y1, dtype=np.int64)[:, None], (h, size))
    ux = (xs.astype(F) + F(0.5)) / F(size)
    vy = (ys.astype(F) + F(0.5)) / F(size)

    lum, cav, skin_a = SH[..., 0], SH[..., 1], SH[..., 2]
    ext, pmask, smask = RG[..., 1], RG[..., 2], RG[..., 3]
    leg, fu, fv, dors = PA[..., 0], PA[..., 1], PA[..., 2], PA[..., 3]
    fA, fB, fS, fD = PT[..., 0], PT[..., 1], PT[..., 2], PT[..., 3]

    is_head = (rid == 1) | (rid == 2) | (rid == 3) | (rid == 4) | (rid == 14)
    is_leg = (rid >= 5) & (rid <= 8)
    is_hoof = (rid >= 9) & (rid <= 12)
    face_zone = (rid == 1) | (rid == 2) | (rid == 14)

    def col(v):
        return np.broadcast_to(v.astype(F), (h, size, 3)).copy()

    def T(t):
        return t[..., None]

    # 1. Base de robe (+ intérieur des oreilles plus clair)
    c = col(P.body)
    c = np.where(T(rid == 4), mix(c, P.innerEar, F(0.7)), c)

    # 2. Charbonné (masque A des régions)
    if P.sootyAmount > 0:
        c = mix(c, P.sooty, T(P.sootyAmount * smask))
    # 3. Pangaré (masque B)
    if P.pangareAmount > 0:
        c = mix(c, P.pangare, T(P.pangareAmount * pmask))
    # 4. Extrémités (masque G ; sur les membres, limitées par la hauteur de jambe)
    leg_pts = F(1) - smoothstep(P.pointsHeight - F(0.06), P.pointsHeight + F(0.06), leg)
    pts = np.where(is_leg, ext * leg_pts, ext)
    c = mix(c, P.points, T(P.pointsAmount * pts))

    # 5. Marques primitives dun : raie de mulet (params A) + zébrures des membres
    if P.primitive > 0:
        stripe = smoothstep(0.55, 0.85, dors)
        t = leg * F(16) + value_noise(ux * F(30), vy * F(30), P.s["bar"]) * F(0.8)
        fr = t - np.floor(t)
        tri = np.abs(fr * F(2) - F(1))
        bars = smoothstep(0.55, 0.8, tri) * smoothstep(0.30, 0.40, leg) * (F(1) - smoothstep(0.62, 0.80, leg)) * F(0.8)
        bars = np.where(is_leg, bars, F(0))
        m = np.maximum(stripe, bars)
        c = mix(c, P.primitiveColor, T(P.primitive * m))

    # 6. Pommelures saisonnières (champ A des patterns)
    if P.dapples > 0:
        w = np.where(is_head, F(0.25), np.where(is_leg, smoothstep(0.45, 0.85, leg), F(1)))
        d = smoothstep(0.40, 0.70, fD)
        f = F(1) + P.dapples * w * (d * F(0.32) - F(0.16))
        c = c * T(f)

    # 7. Gris progressif (fer -> pommelé -> clair -> truité)
    if P.greyStage > 0:
        speed = np.where(is_head, F(1.3), np.where(is_leg, F(0.55) + F(0.45) * leg, F(1)))
        gi = np.minimum(P.greyStage * speed, F(1))
        grain = hash01(xs, ys, P.s["grey"])
        cov = smoothstep(0.0, 0.40, gi + (grain - F(0.5)) * F(0.30))
        ds = P.greyDapples * smoothstep(0.22, 0.42, gi) * (F(1) - smoothstep(0.58, 0.82, gi))
        lt = clamp01(gi * F(1.30) - F(0.30) + ds * (fD - F(0.5)) * F(1.4) + (grain - F(0.5)) * F(0.10))
        gcol = mix(P.greyDark, P.greyLight, T(lt))
        c = mix(c, gcol, T(cov))
        if P.fleabitten > 0:
            fl = P.fleabitten * smoothstep(0.55, 0.90, gi)
            n = value_noise(ux * F(380), vy * F(380), P.s["flea"]) * F(0.75) + hash01(xs, ys, P.s["flea2"]) * F(0.25)
            th = F(1) - fl * F(0.30)
            k = smoothstep(th, th + F(0.05), n)
            c = mix(c, P.fleck, T(k * F(0.85)))

    # 8. Rouan (bruit par texel ; tête et bas des membres restent foncés)
    if P.roan > 0:
        zone = np.where(is_head, F(0.10), np.where(is_leg, smoothstep(0.35, 0.75, leg), F(1)))
        zone = np.where((rid == 2) | (rid == 13) | is_hoof, F(0), zone)
        m = value_noise(ux * F(160), vy * F(160), P.s["roan"])
        n = hash01(xs, ys, P.s["roan2"])
        rz = P.roan * zone
        wf = clamp01(rz * (F(0.20) + F(0.35) * m) + (n - F(0.5)) * F(0.45) * np.minimum(rz * F(2), F(1)))
        c = mix(c, P.white, T(wf))

    # 9. Panachures (champs R/G des patterns, seuils de couverture, bords bruités)
    wpie = np.zeros((h, size), dtype=F)
    leg_white_field = np.where(is_leg, F(1) - leg, np.where(is_hoof, F(1), F(0)))
    head_dip = np.where(is_head, F(1) - fv, F(0))
    if P.tobiano > 0:
        n = value_noise(ux * F(14), vy * F(14), P.s["tob"]) - F(0.5)
        wpie = np.maximum(wpie, cover_mask(fA, P.tobiano, 0.012, n * F(0.05)))
    if P.overo > 0:
        n = (value_noise(ux * F(22), vy * F(22), P.s["ov"]) - F(0.5)) + (value_noise(ux * F(70), vy * F(70), P.s["ov2"]) - F(0.5)) * F(0.5)
        keep = (F(1) - smoothstep(0.15, 0.5, dors)) * np.where(is_leg, smoothstep(0.55, 0.95, leg) * F(0.6), F(1))
        wpie = np.maximum(wpie, cover_mask(fB, P.overo, 0.015, n * F(0.10)) * keep)
    if P.sabino > 0:
        field = np.maximum(fB * F(0.6) + pmask * F(0.5), leg_white_field * F(0.95))
        n = hash01(xs, ys, P.s["sab"]) - F(0.5)
        m = value_noise(ux * F(40), vy * F(40), P.s["sab2"]) - F(0.5)
        wpie = np.maximum(wpie, cover_mask(field, P.sabino, 0.06, m * F(0.10) + n * F(0.18)))
    if P.splash > 0:
        field = np.maximum(np.maximum(pmask * F(0.75) + fB * F(0.25), leg_white_field), head_dip)
        n = value_noise(ux * F(12), vy * F(12), P.s["spl"]) - F(0.5)
        wpie = np.maximum(wpie, cover_mask(field, P.splash, 0.01, n * F(0.03)))
    if P.dominantWhite > 0:
        field = np.maximum(np.maximum(fB * F(0.5) + pmask * F(0.3) + fA * F(0.2), leg_white_field * F(0.9)), head_dip * F(0.8))
        n = value_noise(ux * F(18), vy * F(18), P.s["dw"]) - F(0.5)
        wpie = np.maximum(wpie, cover_mask(field, P.dominantWhite, 0.04, n * F(0.06)))
    c = mix(c, P.white, T(wpie))

    # 10. Complexe léopard (champ B des patterns)
    lp_skin = np.zeros((h, size), dtype=F)
    if P.lp > 0:
        if P.lpFull > 0:
            zone_w = np.where(is_head, F(0.85), np.where(is_leg, F(0.6) + F(0.4) * smoothstep(0.2, 0.6, leg), F(1)))
        else:
            field = smask * F(0.75) + dors * F(0.25)
            n = value_noise(ux * F(20), vy * F(20), P.s["lp"]) - F(0.5)
            zone_w = cover_mask(field, P.lpCoverage, 0.03, n * F(0.12))
            zone_w = np.where(is_head | is_leg, F(0), zone_w)
        thr = F(1) - P.spotSize * F(0.45) - F(0.05)
        dsel = value_noise(ux * F(25), vy * F(25), P.s["lpd"])
        sel = smoothstep(F(1) - P.spotDensity - F(0.05), F(1) - P.spotDensity + F(0.05), dsel)
        spot = smoothstep(thr, thr + F(0.04), fS) * sel
        halo = smoothstep(thr - F(0.08), thr, fS) * sel
        white = zone_w * (F(1) - spot) * (F(1) - halo * F(0.35))
        c = mix(c, P.white, T(white))
        lp_skin = zone_w * (F(1) - spot)
        if P.varnish > 0:
            z2 = np.where(is_head, F(0.4), np.where(is_leg, smoothstep(0.3, 0.8, leg) * F(0.6), F(1)))
            m = value_noise(ux * F(120), vy * F(120), P.s["var"])
            n = hash01(xs, ys, P.s["var2"])
            vz = P.varnish * z2
            wf = clamp01(vz * (F(0.4) + F(0.8) * m) + (n - F(0.5)) * F(0.5) * vz)
            c = mix(c, P.white, T(wf * F(0.85)))

    # 11. Marques de tête et de membres
    wm = np.where(face_zone, face_mark(P, LM, fu, fv, rid), F(0))
    wleg = np.zeros((h, size), dtype=F)
    for li in range(4):
        sel = rid == (5 + li)
        if sel.any() and P.legHeight[li] > 0:
            wleg = np.where(sel, leg_mark(P, LM, leg, ux, vy, li), wleg)
    wm = np.maximum(wm, wleg)
    c = mix(c, P.white, T(wm))

    # 12. Peau nue (canal B du shading) : foncée, rose sous le blanc, marbrée (léopard) / tachetée (champagne)
    white_skin = np.maximum(np.maximum(wpie, wm), lp_skin * F(0.5))
    pink = np.maximum(P.pinkAll, white_skin)
    sk = mix(P.skinDark, P.skinPink, T(pink))
    if P.lpMottle > 0:
        m = value_noise(ux * F(90), vy * F(90), P.s["mot"])
        sk = mix(sk, P.skinPink, T(smoothstep(0.50, 0.62, m) * F(0.85)))
    if P.freckles > 0:
        m = value_noise(ux * F(240), vy * F(240), P.s["frk"])
        sk = mix(sk, P.freckle, T(smoothstep(0.66, 0.74, m)))
    c = mix(c, sk, T(skin_a))

    # 13. Sabots (régions 9-12) : foncés / clairs / rayés
    if is_hoof.any():
        hi = np.clip(rid - 9, 0, 3)
        hw = np.maximum(np.maximum(P.hoofWhite[hi], wpie), P.pinkAll)
        partial = np.minimum(F(4) * wpie * (F(1) - wpie) * F(1.5), F(1))
        stripe_amt = np.maximum(P.hoofStripe[hi], partial)
        sn = value_noise(ux * F(220), vy * F(14), P.s["hoof"])
        st = smoothstep(0.42, 0.58, sn)
        light = mix(hw, st, stripe_amt)
        hc = mix(P.hoofDark, P.hoofLight, T(light))
        if P.hoofOverride > 0:
            hc = col(P.hoofOverrideColor)
        c = np.where(T(is_hoof), hc, c)

    # 14. Châtaignes / ergots (région 13)
    chest = mix(P.chestnutDark, P.chestnutLight, T(np.maximum(wpie, wm) * F(0.6)))
    c = np.where(T(rid == 13), chest, c)

    # 15. Détail final : luminance du poil (R du shading, 0.5 neutre) × cavité (G)
    f = (F(0.5) + lum) * (F(0.72) + F(0.28) * cav)
    return c * T(f)


# ---------------------------------------------------------------------------------------------
# Crins (texture de mèches) et iris
# ---------------------------------------------------------------------------------------------


def compose_hair(cfg: dict, strands: np.ndarray) -> np.ndarray:
    """Albedo RGBA des crins. strands RGBA8 : R luminance (0.5 neutre), G racine->pointe, B aléa par mèche,
    A alpha (conservé tel quel)."""
    P = palette(cfg)
    hgt, wid = strands.shape[:2]
    lum = strands[..., 0].astype(F) / F(255)
    t = strands[..., 1].astype(F) / F(255)
    rb = strands[..., 2].astype(np.int64)
    r = strands[..., 2].astype(F) / F(255)
    c = np.broadcast_to(P.mane, (hgt, wid, 3)).astype(F).copy()
    if P.maneTipAmount > 0:
        c = mix(c, P.maneTip, (P.maneTipAmount * smoothstep(0.30, 1.0, t))[..., None])
    if P.maneSecondaryFraction > 0:
        hs = hash01(rb, np.zeros_like(rb), salted(P.seed, SALT["sec"]))
        sel = (hs < P.maneSecondaryFraction).astype(F)
        c = mix(c, P.maneSecondary, sel[..., None])
    if P.maneWhiteFraction > 0:
        hw = hash01(rb, np.ones_like(rb), salted(P.seed, SALT["wht"]))
        sel = (hw < P.maneWhiteFraction).astype(F)
        c = mix(c, P.maneWhite, sel[..., None])
    f = (F(0.86) + F(0.28) * r) * (F(0.5) + lum)
    c = c * f[..., None]
    out = np.zeros((hgt, wid, 4), dtype=np.uint8)
    out[..., :3] = encode_linear(c)
    out[..., 3] = strands[..., 3]
    return out


IRIS_RX = 0.86
IRIS_RY = 0.74
PUPIL_RX = 0.50
PUPIL_RY = 0.19
GRANULA = [(-0.27, -0.17, 0.075), (-0.10, -0.18, 0.095), (0.08, -0.18, 0.09), (0.24, -0.17, 0.07),
           (-0.12, 0.17, 0.05), (0.10, 0.17, 0.045)]


def compose_iris(cfg: dict, detail: np.ndarray | None = None, size: int = 512) -> np.ndarray:
    """Texture d'iris (size², RGBA8) : iris centré (demi-axes 0.86 × 0.74 de la demi-taille), pupille
    horizontale, granula iridica sur le bord supérieur, sclère hors de l'iris. detail : carte grise optionnelle
    (R, 0.5 neutre) échantillonnée en bilinéaire."""
    IP = iris_palette(cfg)
    ys, xs = np.meshgrid(np.arange(size, dtype=np.int64), np.arange(size, dtype=np.int64), indexing="ij")
    px = ((xs.astype(F) + F(0.5)) / F(size) - F(0.5)) * F(2)
    py = ((ys.astype(F) + F(0.5)) / F(size) - F(0.5)) * F(2)
    qx = px / F(IRIS_RX)
    qy = py / F(IRIS_RY)
    ri = np.sqrt(qx * qx + qy * qy)
    ox = px / F(PUPIL_RX)
    oy = py / F(PUPIL_RY)
    rp = np.sqrt(ox * ox + oy * oy)
    ax = np.abs(px)
    ay = np.abs(py)
    pa = py / (ax + ay + F(1e-6))
    ang = np.where(px >= 0, pa + F(1), F(3) - pa)            # pseudo-angle « diamant » dans [0, 4)
    fiber = value_noise(ang * F(40), ri * F(6) + F(16), IP["sIris"], period_x=160)
    base = np.broadcast_to(IP["base"], (size, size, 3)).astype(F).copy()
    if IP["vairon"] > 0:
        sv = value_noise(ang * F(1.5), np.full_like(ang, F(16.5)), IP["sVair"], period_x=6) + (fiber - F(0.5)) * F(0.3)
        base = mix(base, IP["blue"], smoothstep(0.44, 0.64, sv)[..., None])
    if detail is not None:
        rows = _axis_tables(detail.shape[0], size)
        cols = _axis_tables(detail.shape[1], size)
        shade = F(0.5) + _bilinear_band(detail, rows, cols)[..., 0]
    else:
        coll = F(1) + F(0.25) * (smoothstep(0.30, 0.42, ri) * (F(1) - smoothstep(0.42, 0.60, ri)))
        shade = (F(0.62) + F(0.62) * fiber) * coll
    limbal = F(1) - F(0.55) * smoothstep(0.80, 1.0, ri)
    blue_boost = F(1) + IP["blueFibers"] * F(0.35) * (fiber - F(0.5))
    c = base * (shade * limbal * blue_boost)[..., None]
    g = np.zeros_like(px)
    gn = value_noise(px * F(14) + F(16), py * F(14) + F(16), IP["sGran"]) - F(0.5)
    for cx, cy, rr in GRANULA:
        dx = px - F(cx)
        dy = (py - F(cy)) * F(1.3)
        d = np.sqrt(dx * dx + dy * dy) / F(rr)
        g = np.maximum(g, F(1) - smoothstep(0.80, 1.0, d + gn * F(0.3)))
    c = mix(c, IP["granula"] * (F(0.8) + F(0.4) * fiber)[..., None], g[..., None])
    pupil = F(1) - smoothstep(0.96, 1.04, rp)
    c = mix(c, IP["pupil"], pupil[..., None])
    scl = smoothstep(0.98, 1.03, ri)
    c = mix(c, IP["sclera"], scl[..., None])
    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[..., :3] = encode_linear(c)
    out[..., 3] = 255
    return out


# ---------------------------------------------------------------------------------------------
# Cartes synthétiques (arithmétique ENTIÈRE : identiques au bit près en Swift, CoatSyntheticMaps)
# ---------------------------------------------------------------------------------------------
# Disposition « poupée de papier » en pour-mille d'UV : corps (rectangle), tête (coordonnées faciales),
# 4 membres (hauteur de jambe), 4 sabots, châtaignes, peau nue ventrale. Sert aux tests et aux aperçus
# tant que les cartes réelles de l'agent « body » n'existent pas.

SYN_SALT = 0x5EED


def _h8(a, b, salt):
    """Octet pseudo-aléatoire 0..255 : hash_u32(a, b, salt) >> 24."""
    return (hash_u32(a, b, salt) >> U32(24)).astype(np.int64)


def _inoise(px, py, cell, salt):
    """Bruit de valeur ENTIER (0..255), réseau de pas `cell` (pour-mille), interpolation bilinéaire entière."""
    gx = px // cell
    gy = py // cell
    fx = px % cell
    fy = py % cell
    a = _h8(gx, gy, salt)
    b = _h8(gx + 1, gy, salt)
    c = _h8(gx, gy + 1, salt)
    d = _h8(gx + 1, gy + 1, salt)
    top = (a * (cell - fx) + b * fx) // cell
    bot = (c * (cell - fx) + d * fx) // cell
    return (top * (cell - fy) + bot * fy) // cell


def _icells(px, py, cell, radius, salt):
    """Champ cellulaire entier (0..255) : 255 au centre (décalé aléatoirement) de chaque cellule, 0 à `radius`."""
    gx = px // cell
    gy = py // cell
    cx = gx * cell + cell // 4 + (_h8(gx, gy, salt) * (cell // 2)) // 256
    cy = gy * cell + cell // 4 + (_h8(gx, gy, salt + 1) * (cell // 2)) // 256
    dx = px - cx
    dy = py - cy
    d2 = dx * dx + dy * dy
    r2 = radius * radius
    return np.maximum(0, 255 - (d2 * 255) // r2)


def synthetic_maps(size: int) -> dict:
    """Cartes synthétiques RGBA8 (size²) : shading, regions, params, patterns. Arithmétique entière seulement."""
    y, x = np.meshgrid(np.arange(size, dtype=np.int64), np.arange(size, dtype=np.int64), indexing="ij")
    ux = ((2 * x + 1) * 1000) // (2 * size)       # pour-mille, 0..999
    vy = ((2 * y + 1) * 1000) // (2 * size)
    region = np.zeros_like(ux)
    ext = np.zeros_like(ux)
    pang = np.zeros_like(ux)
    soot = np.zeros_like(ux)
    leg = np.zeros_like(ux)
    fu = np.zeros_like(ux)
    fv = np.zeros_like(ux)
    dors = np.zeros_like(ux)
    skin = np.zeros_like(ux)
    pA = np.zeros_like(ux)
    pB = np.zeros_like(ux)

    n1 = _inoise(ux, vy, 120, SYN_SALT)
    n2 = _inoise(ux, vy, 90, SYN_SALT + 7)
    spots = _icells(ux, vy, 36, 14, SYN_SALT + 11)
    dapples = _icells(ux, vy, 28, 15, SYN_SALT + 13)

    # Corps : ux 40..739, vy 40..439 (bx 0 = arrière, by 0 = ligne du dos)
    body = (ux >= 40) & (ux < 740) & (vy >= 40) & (vy < 440)
    bx = np.clip((ux - 40) * 1000 // 700, 0, 999)
    by = np.clip((vy - 40) * 1000 // 400, 0, 999)
    soot = np.where(body, np.maximum(0, 600 - by) * 255 // 600, soot)
    pang = np.where(body, np.maximum(0, by - 550) * 255 // 450, pang)
    dors = np.where(body, np.maximum(0, 120 - by) * 255 // 120, dors)
    cross = 255 - np.abs(bx - 500) * 255 // 500
    pA = np.where(body, (n1 * 2 + cross) // 3, pA)
    pB = np.where(body, (n2 + by * 255 // 1000 * 2) // 3, pB)
    ventral = body & (bx >= 100) & (bx < 180) & (by >= 900)
    region = np.where(ventral, 15, region)
    skin = np.where(ventral, 255, skin)

    # Tête : ux 760..979, vy 40..439
    head = (ux >= 760) & (ux < 980) & (vy >= 40) & (vy < 440)
    hu = np.clip((ux - 760) * 1000 // 220, 0, 999)
    hv = np.clip((440 - vy) * 1000 // 400, 0, 999)
    region = np.where(head, 1, region)
    fu = np.where(head, hu * 255 // 1000, fu)
    fv = np.where(head, hv * 255 // 1000, fv)
    muzzle = head & (hv < 150)
    region = np.where(muzzle, 2, region)
    skin = np.where(muzzle, 150, skin)
    pang = np.where(head, np.maximum(0, 220 - hv) * 255 // 220, pang)
    ex = np.abs(hu - 500) - 360
    ey = hv - 620
    eye = head & (ex * ex + ey * ey < 45 * 45)
    region = np.where(eye, 14, region)
    skin = np.where(eye, 255, skin)
    ear = head & (hv > 930) & (np.abs(hu - 500) > 250)
    region = np.where(ear, 3, region)
    ext = np.where(ear, 255, ext)
    inner = ear & (np.abs(hu - 500) > 300) & (np.abs(hu - 500) < 400) & (hv > 955)
    region = np.where(inner, 4, region)
    pA = np.where(head, n1 // 4, pA)
    pB = np.where(head, (255 - hv * 255 // 1000) // 2 + n2 // 4, pB)

    # Membres : 4 colonnes ux [40 + 180 i, 160 + 180 i), vy 480..899 ; sabots vy 900..959
    for i in range(4):
        x0 = 40 + 180 * i
        col = (ux >= x0) & (ux < x0 + 120)
        pad = (ux >= x0 - 20) & (ux < x0 + 140) & (vy >= 470) & (vy < 960)   # marge (comme une cuisson avec marge)
        lg = col & (vy >= 480) & (vy < 900)
        hf = col & (vy >= 900) & (vy < 960)
        lh = 1000 - np.maximum(vy - 480, 0) * 900 // 420          # 1000 en haut -> 100 à la couronne
        lhp = np.where(vy >= 900, np.maximum(960 - vy, 0) * 100 // 60, lh)
        leg = np.where(pad, np.clip(lhp, 0, 1000) * 255 // 1000, leg)
        region = np.where(lg, 5 + i, region)
        ext = np.where(lg, np.clip(700 - lh, 0, 100) * 255 // 100, ext)
        pA = np.where(lg, 190 + n1 // 4, pA)
        pB = np.where(lg, (255 - np.clip(lh, 0, 1000) * 255 // 1000 + n2) // 2, pB)
        region = np.where(hf, 9 + i, region)
        pA = np.where(hf, 230, pA)
        pB = np.where(hf, 200, pB)
        clo, chi = (550, 620) if i < 2 else (300, 360)
        chestnut = lg & (ux >= x0 + 80) & (ux < x0 + 110) & (lh >= clo) & (lh < chi)
        region = np.where(chestnut, 13, region)

    lum = 128 + (_h8(x, y, SYN_SALT + 3) >> 4) - 8
    cav = 255 - (_h8(x // 4, y // 4, SYN_SALT + 5) >> 3)
    shading = np.stack([lum, cav, skin, np.full_like(lum, 255)], axis=-1)
    regions = np.stack([region * 16, ext, pang, soot], axis=-1)
    params = np.stack([leg, fu, fv, dors], axis=-1)
    patterns = np.stack([pA, pB, spots, dapples], axis=-1)
    return {k: np.clip(v, 0, 255).astype(np.uint8) for k, v in
            (("shading", shading), ("regions", regions), ("params", params), ("patterns", patterns))}


def synthetic_strands(width: int = 128, height: int = 256) -> np.ndarray:
    """Texture de mèches synthétique (RGBA8, entière) : 1 mèche = 4 colonnes ; G = racine (0) -> pointe (255)."""
    y, x = np.meshgrid(np.arange(height, dtype=np.int64), np.arange(width, dtype=np.int64), indexing="ij")
    sid = x // 4
    r = 128 + (_h8(x, y // 8, SYN_SALT + 21) >> 3) - 16
    g = y * 255 // (height - 1)
    b = _h8(sid, np.zeros_like(sid), SYN_SALT + 23)
    tip = height * 4 // 5
    a = np.where(x % 4 == 3, 0, np.where(y < tip, 255, np.maximum(0, 255 - (y - tip) * 255 // (height - tip))))
    return np.clip(np.stack([r, g, b, a], axis=-1), 0, 255).astype(np.uint8)
