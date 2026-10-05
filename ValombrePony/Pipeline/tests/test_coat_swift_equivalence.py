"""Équivalence Swift ⇄ Python du système de robes, SANS compilateur Swift.

Le code Swift de `PonyKit/Sources/PonyCore/Coat/` est traduit mécaniquement en Python (`coat_swift2py.py`) puis
exécuté en float32 et comparé, au bit près, à l'implémentation de référence `Pipeline/pony/coat_reference.py` :
hachage et bruit, palette (génotype -> couleurs), ombrage par texel du corps (toutes les couches, marques),
crins, iris, palette d'iris, cartes synthétiques, tables d'échantillonnage.

Limites : la traduction ne vérifie ni les types, ni les API, ni le compilateur ; les fonctions transcendantes de la
palette (log, exp, pow) sont celles de Python des deux côtés (sur Apple, libm peut différer d'1 ulp : les vecteurs
de référence Swift ont une tolérance). Le pilote parallèle `composeBody` (bandes, pointeurs) n'est pas traduit :
ses entrées (tables d'axes, échantillonnage bilinéaire, id de région) le sont.

Lancer : python3 -m unittest Pipeline/tests/test_coat_swift_equivalence.py   (depuis ValombrePony/)
"""
from __future__ import annotations

import math
import re
import sys
import unittest
import warnings
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "stages"))
sys.path.insert(0, str(HERE))

from pony import coat_reference as cr  # noqa: E402
import coat_swift2py as s2p  # noqa: E402

F = np.float32
COAT = HERE.parent.parent / "PonyKit" / "Sources" / "PonyCore" / "Coat"
SRC = {n: (COAT / f"{n}.swift").read_text(encoding="utf-8") for n in
       ("CoatNoise", "CoatCompositor", "CoatPalette", "CoatColorTable", "PonyColor", "CoatMaps")}
MAP_NAMES = ("shading", "regions", "params", "patterns")
SALTMAP = {"sGrey": "grey", "sFlea": "flea", "sFlea2": "flea2", "sRoan": "roan", "sRoan2": "roan2", "sBar": "bar",
           "sTob": "tob", "sOv": "ov", "sOv2": "ov2", "sSab": "sab", "sSab2": "sab2", "sSpl": "spl", "sDw": "dw",
           "sLp": "lp", "sLpd": "lpd", "sVar": "var", "sVar2": "var2", "sFace": "face", "sMot": "mot",
           "sFrk": "frk", "sHoof": "hoof"}


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class Indexed(Obj):
    """Objet dont `.x`/`.y`/`.w` (traduits en [0]/[1]/[3]) sont des attributs nommés."""

    def __getitem__(self, i):
        return {0: getattr(self, "x", None), 1: getattr(self, "y", None), 3: getattr(self, "w", None)}[i]


class Wild:
    def __eq__(self, other):
        return True


class Zyg(str):
    @property
    def isPresent(self):
        return self != "absent"

    @property
    def alleleCount(self):
        return {"absent": 0, "heterozygous": 1, "homozygous": 2}[self]


class SwiftPonyColor:
    def __init__(self, hex=None, r=None, g=None, b=None):
        c = cr.hex_to_srgb(hex) if hex is not None else (r, g, b)
        self.r, self.g, self.b = F(c[0]), F(c[1]), F(c[2])


def u32(x=None, truncatingIfNeeded=None):
    v = x if x is not None else truncatingIfNeeded
    return np.uint32(int(v) & 0xFFFFFFFF)


def function_body(src: str, header: str) -> str:
    i0 = src.index(header)
    b = src.index("{", i0)
    depth, i = 0, b
    while True:
        depth += {"{": 1, "}": -1}.get(src[i], 0)
        if depth == 0 and src[i] == "}":
            return src[b + 1:i]
        i += 1


def build_namespace():
    """Traduit tout le Swift nécessaire et renvoie l'espace de noms d'exécution."""
    warnings.filterwarnings("ignore", category=RuntimeWarning)   # débordements uint32 voulus (&*)
    ns = {"np": np, "F": F, "U32": u32, "Obj": Obj, "math": math, "exp": math.exp, "log": math.log,
          "pow": math.pow, "_": Wild(), "_floor_": lambda x: F(np.floor(F(x))), "sq": lambda x: F(np.sqrt(F(x))),
          "V4": lambda *a: np.array(a, dtype=F), "V3": lambda *a: np.array(a, dtype=F),
          "CoatD3": lambda *a: np.array(a, dtype=np.float64), "Int32": int,
          "RGBA8Image": lambda width, height, pixels: Obj(width=width, height=height, pixels=np.asarray(pixels)),
          "CoatMaps": lambda **kw: Obj(**kw), "PonyColorCtor": SwiftPonyColor,
          "CoatCompositor": Obj(irisResolution=512, finalResolution=2048), "encodeLUT": cr.ENCODE_LUT}
    rn = {"hash32": "cn_hash32", "salted": "cn_salted", "hash": "cn_hash", "hash01": "cn_hash01",
          "valueNoise": "cn_valueNoise"}
    exec(s2p.transpile(SRC["CoatNoise"], list(rn), rename=rn), ns)
    exec(s2p.transpile(SRC["CoatNoise"], ["coatSmoothstep", "coatClamp01", "coatMix", "coatCoverMask"]), ns)
    exec(s2p.transpile(SRC["CoatCompositor"], ["encodeIndex", "bilinear4", "shadeTexel", "faceMark", "ellipseMask",
                                               "capsuleMask", "legMark"]), ns)
    S = Obj(**{k: np.uint32(int(v, 16)) for k, v in
               re.findall(r"static let (\w+): UInt32 = (0x[0-9A-F]+)", SRC["CoatNoise"])})
    ns["S"] = S
    ns["cn_Salt"] = S

    # Palette (Double)
    s2p.DOUBLE_MODE[0] = True
    try:
        exec(s2p.transpile(SRC["PonyColor"], ["srgbToLinear", "linearToSRGB"]), ns)
        ns["PonyColor"] = Obj(srgbToLinear=ns["srgbToLinear"], linearToSRGB=ns["linearToSRGB"])
        table = SRC["CoatColorTable"]
        T = Obj()
        for name, val in re.findall(r'static let (\w+) = ("#[0-9A-F]{6}")', table):
            setattr(T, name, eval(val))
        for name, val in re.findall(r'static let (\w+) = (\("#[0-9A-F]{6}", "#[0-9A-F]{6}", "#[0-9A-F]{6}"\))',
                                    table):
            setattr(T, name, eval(val))
        exec(s2p.transpile(table, ["target"]), ns)
        T.target = ns["target"]
        ns["T"] = T
        base_body = table[table.index("var base: String {"):]
        base_body = base_body[base_body.index("switch self"):base_body.index("enum Dilution")].rsplit("}", 2)[0]
        exec(("def slot_base(self):\n" + "\n".join(s2p.transpile_body(base_body, 1))).replace("CoatColorTable.", "T."),
             ns)
        math_src = table[table.index("enum CoatColorMath"):]
        names = [("srgb", 0, "srgb_hex"), ("srgb", 1, "srgb_color"), ("lin", 0, "lin_d3"), ("lin", 1, "lin_hex"),
                 ("lin", 2, "lin_color"), "ramp", "density", "dilutionFactor", "applyDensity", "densify", "mix",
                 "f32"]
        code = s2p.transpile(math_src, names).replace("PonyColor(hex=hex)", "PonyColorCtor(hex=hex)")
        code = re.sub(r"(\w+)\.base\b", r"slot_base(\1)", code).replace("CoatColorTable.", "T.")
        exec(code, ns)
        ns["srgb"] = lambda x: ns["srgb_hex"](x) if isinstance(x, str) else ns["srgb_color"](x)
        ns["lin"] = lambda x: (ns["lin_hex"](x) if isinstance(x, str) else
                               ns["lin_color"](x) if isinstance(x, SwiftPonyColor) else ns["lin_d3"](x))
        ns["white"] = ns["lin"](T.whiteHair)
        M = Obj(**{k: ns[k] for k in ("ramp", "density", "dilutionFactor", "applyDensity", "densify", "mix", "f32",
                                      "srgb", "lin", "white")})
        ns["M"] = M
        pal = SRC["CoatPalette"]
        body = function_body(pal, "    init(_ cfg: CoatConfiguration) {")
        lines = ["def palette_init(cfg):",
                 "    self = Obj(legHeight=np.zeros(4, F), legIrregularity=np.zeros(4, F), legErmine=np.zeros(4, F),"
                 " hoofWhite=np.zeros(4, F), hoofStripe=np.zeros(4, F), sLeg=np.zeros(4, np.uint32),"
                 " sErm=np.zeros(4, np.uint32))"]
        lines += s2p.transpile_body(body, 1) + ["    return self"]
        ns["CoatIrisPalette"] = lambda cfg: None
        exec("\n".join(lines).replace("CoatNoise.salted", "cn_salted"), ns)
        exec(s2p.transpile(pal[pal.index("public static func derived"):], ["derived"]), ns)
        ibody = function_body(pal, "    init(_ cfg: CoatConfiguration) {\n        typealias M = CoatColorMath\n"
                                   "        typealias T = CoatColorTable\n        let kind")
        lines = ["def iris_init(cfg):", "    self = Obj()"] + s2p.transpile_body(ibody, 1) + ["    return self"]
        code = "\n".join(lines).replace("CoatNoise.", "cn_").replace("EyeColorKind.derived(from=cfg)", "derived(cfg)")
        exec(code.replace("cn_Salt.", "S."), ns)
    finally:
        s2p.DOUBLE_MODE[0] = False

    # Crins et iris (branche « carte de détail » de l'iris neutralisée)
    comp = SRC["CoatCompositor"]
    src = comp[comp.index("public static func composeHair(_ configuration: CoatConfiguration, strands"):]
    src = src.replace("[UInt8](repeating: 0, count: count * 4)", "np.zeros(count * 4, np.uint8)")
    exec(s2p.transpile(src, ["composeHair"]).replace("CoatPalette(configuration)", "PAL(configuration)"), ns)
    src = comp[comp.index("public static func composeIris"):]
    src = re.sub(r"        var dTables.*?\n        \}\n", "", src, count=1, flags=re.S)
    src = re.sub(r"if let d = detail, let tables = dTables \{.*?\} else \{", "if false {\nlet unusedBranch = 0\n} else {",
                 src, count=1, flags=re.S)
    src = src.replace("[UInt8](repeating: 255, count: size * size * 4)", "np.full(size * size * 4, 255, np.uint8)")
    exec(s2p.transpile(src, ["composeIris"]).replace("CoatIrisPalette(configuration)", "IRIS(configuration)"), ns)
    ns["irisRadii"] = np.array([F(v) for v in re.search(r"irisRadii = SIMD2<Float>\(([\d.]+), ([\d.]+)\)",
                                                        comp).groups()])
    ns["pupilRadii"] = np.array([F(v) for v in re.search(r"pupilRadii = SIMD2<Float>\(([\d.]+), ([\d.]+)\)",
                                                         comp).groups()])
    gsrc = re.search(r"static let granula: \[\(Float, Float, Float\)\] = (\[.*?\])\n", comp, re.S).group(1)
    ns["granula"] = [tuple(F(x) for x in t) for t in eval(gsrc)]

    # Cartes synthétiques (entiers : `/` Swift -> `//`) et tables d'axe
    sm = SRC["CoatMaps"][SRC["CoatMaps"].index("enum CoatSyntheticMaps"):]
    sm = sm.replace("CoatNoise.hash(", "cn_hash(")
    sm = re.sub(r" / ", " IDIV ", sm)
    sm = sm.replace("[UInt8](repeating: 0, count: n)", "np.zeros(n, np.uint8)")
    sm = sm.replace("[UInt8](repeating: 0, count: width * height * 4)", "np.zeros(width * height * 4, np.uint8)")
    sm = sm.replace("var region = 0, ext = 0, pang = 0, soot = 0, leg = 0, fu = 0, fv = 0, dors = 0, skin = 0",
                    "\n".join(f"var {v} = 0" for v in ("region", "ext", "pang", "soot", "leg", "fu", "fv", "dors",
                                                       "skin")))
    sm = sm.replace("var pA = 0, pB = 0", "var pA = 0\nvar pB = 0")
    sm = sm.replace("UInt8(clampi(v, 0, 255))", "np.uint8(clampi(v, 0, 255))")
    sm = re.sub(r"px\[o( \+ \d)?\] = UInt8\(", r"px[o\1] = np.uint8(", sm)
    ns["salt"] = int(re.search(r"static let salt = (0x[0-9A-F]+)", sm).group(1), 16)
    exec(s2p.transpile(sm, ["h8", "inoise", "icells", "clampi", "byte", "make", "strands"]).replace(" IDIV ", " // "),
         ns)
    body = function_body(comp[comp.index("final class CoatAxisTable"):], "    init(mapSize: Int, outSize: Int) {")
    body = re.sub(r"UnsafeMutablePointer<(\w+)>\.allocate\(capacity: max\(n, 1\)\)", r"np.zeros(max(n, 1), '\1')",
                  body).replace("'Int32'", "np.int64").replace("'Float'", "np.float32")
    code = "\n".join(["def axis_init(mapSize, outSize):", "    self = Obj()"] + s2p.transpile_body(body, 1)
                     + ["    return self"])
    for f in ("i0", "i1", "w", "nearest", "count"):
        code = re.sub(r"^(\s+)" + f + r"(\[o\]| =)", r"\1self." + f + r"\2", code, flags=re.M)
    exec(code, ns)
    return ns


NS = build_namespace()
ENUM_CASES = {k: dict(v) for k, v in cr.ENUMS.items()}


def swift_config(d: dict) -> Obj:
    """Configuration telle que la verrait le Swift (cas d'énumération, Float, PonyColor?)."""
    def color(v):
        if v is None:
            return None
        c = cr.color_srgb(v)
        return SwiftPonyColor(r=c[0], g=c[1], b=c[2])

    g = d["genotype"]
    gen = Obj(extensionLocus=ENUM_CASES["ExtensionGenotype"][g["extensionLocus"]],
              agouti=ENUM_CASES["AgoutiGenotype"][g["agouti"]],
              creamPearl=ENUM_CASES["CreamPearlGenotype"][g["creamPearl"]])
    for z in cr.ZYGOSITY_FIELDS:
        setattr(gen, z, Zyg(ENUM_CASES["Zygosity"][g[z]]))
    legs = [Obj(height=F(d["legs"][k]["height"]), irregularity=F(d["legs"][k]["irregularity"]),
                ermine=bool(d["legs"][k]["ermine"])) for k in cr.LEG_KEYS]
    f = d["face"]
    h = d["hair"]
    ov = d.get("overrides") or {}
    return Obj(genotype=gen, expression=Obj(**{k: F(v) for k, v in d["expression"].items()}), legs=legs,
               face=Obj(kind=ENUM_CASES["FaceMarkingKind"][f["kind"]], size=F(f["size"]), offsetU=F(f["offsetU"]),
                        offsetV=F(f["offsetV"]), snip=f["snip"], lips=f["lips"], irregularity=F(f["irregularity"])),
               hair=Obj(tipLightening=F(h["tipLightening"]), whiteStrands=F(h["whiteStrands"]),
                        secondaryFraction=F(h["secondaryFraction"]), secondaryColor=color(h.get("secondaryColor"))),
               overrides=Obj(**{k: color(ov.get(k)) for k in ("body", "points", "mane", "hooves", "eyes", "skin")}),
               irisStyle=d.get("irisStyle", "automatic"), seed=np.uint32(d["seed"]))


def all_cases():
    import s05_coat

    base = cr.plain_config()
    extra = [("pearl_noir", cr.deep_merge(base, {"genotype": {"agouti": "aa", "creamPearl": "prl/prl"}})),
             ("silver_bai_dun_creme", cr.deep_merge(base, {"genotype": {"silver": "X/X", "dun": "X/n",
                                                                          "creamPearl": "Cr/N"}})),
             ("bai_brun_surcharge", cr.deep_merge(base, {"genotype": {"agouti": "At"},
                                                         "overrides": {"body": "#336699", "points": "#AA2200"},
                                                         "expression": {"shade": 0.7, "pangare": 0.3}}))]
    return [(pid, cfg) for pid, _, _, cfg in cr.preset_configs()] + s05_coat._extra_cases() + extra


def adapter(P):
    a = Obj(**dict(P.__dict__))
    for sw, py in SALTMAP.items():
        setattr(a, sw, np.uint32(P.s[py]))
    a.sLeg = [np.uint32(v) for v in P.sLeg]
    a.sErm = [np.uint32(v) for v in P.sErm]
    a.hasFaceMarking = P.faceKind != 0 or P.faceSnip > 0 or P.faceLips > 0
    return a


class SwiftEquivalenceTests(unittest.TestCase):
    def setUp(self):
        # Les débordements uint32 (&* en Swift) sont voulus : unittest réactive les avertissements à chaque test.
        self._warn = warnings.catch_warnings()
        self._warn.__enter__()
        warnings.simplefilter("ignore", RuntimeWarning)

    def tearDown(self):
        self._warn.__exit__(None, None, None)

    def test_hash_and_noise(self):
        for v in (0, 1, 2, 12345, 0xFFFFFFFF, 0x9E3779B9):
            self.assertEqual(int(NS["cn_hash32"](np.uint32(v))), cr.hash32_int(v))
        for seed, salt in ((1, 0x1001), (77, 0x1030), (0xFFFFFFFF, 0x1020)):
            self.assertEqual(int(NS["cn_salted"](np.uint32(seed), np.uint32(salt))), cr.salted(seed, salt))
        pts = np.random.default_rng(1).uniform(0, 300, size=(300, 2)).astype(F)
        for x, y in pts:
            self.assertEqual(NS["cn_valueNoise"](x, y, np.uint32(4242)),
                             cr.value_noise(np.array([x]), np.array([y]), 4242)[0])
            self.assertEqual(NS["cn_valueNoise"](x, y, np.uint32(7), periodX=np.uint32(160)),
                             cr.value_noise(np.array([x]), np.array([y]), 7, period_x=160)[0])

    def test_palette(self):
        for name, d in all_cases():
            P = cr.palette(d)
            Q = NS["palette_init"](swift_config(d))
            for k, v in P.__dict__.items():
                if k in ("s", "sLeg", "sErm", "iris"):
                    continue
                self.assertTrue(hasattr(Q, k), f"{name}: {k} absent du Swift")
                a = np.asarray(v, dtype=np.float64)
                b = np.asarray(getattr(Q, k), dtype=np.float64)
                self.assertEqual(a.shape, b.shape, f"{name}.{k}")
                self.assertTrue(np.allclose(a, b, rtol=2e-7, atol=1e-9), f"{name}.{k}: {v} != {getattr(Q, k)}")
            for sw, py in SALTMAP.items():
                self.assertEqual(int(getattr(Q, sw)), P.s[py], f"{name}.{sw}")
            self.assertEqual([int(x) for x in Q.sLeg], P.sLeg)
            self.assertEqual([int(x) for x in Q.sErm], P.sErm)

    def test_body_texels_bit_identical(self):
        maps64 = cr.synthetic_maps(64)
        mixed = dict(maps64)
        mixed["shading"] = cr.synthetic_maps(128)["shading"]
        mixed["patterns"] = cr.synthetic_maps(48)["patterns"]
        size = 40
        for name, d in all_cases():
            maps = mixed if name == "libre_surcharges" else maps64
            P = cr.palette(d)
            A = adapter(P)
            LM = cr.Landmarks()
            LMs = Obj(coronet=LM.coronet, faceEyeV=LM.face_eye_v, faceEyeU=LM.face_eye_u, nostrilV=LM.nostril_v)
            tabs = {k: (cr._axis_tables(maps[k].shape[0], size), cr._axis_tables(maps[k].shape[1], size))
                    for k in MAP_NAMES}
            ref = cr._compose_band(P, LM, maps, tabs, size, 0, size)
            flat = {k: maps[k].reshape(-1) for k in MAP_NAMES}
            views = {k: (Indexed(i0=c[0], i1=c[1], w=c[2], nearest=c[3]), Indexed(i0=r[0], i1=r[1], w=r[2], nearest=r[3]))
                     for k, (r, c) in tabs.items()}
            for y in range(size):
                for x in range(size):
                    s, r, p, q = (NS["bilinear4"](flat[k], maps[k].shape[1], views[k][0], views[k][1], x, y)
                                  for k in MAP_NAMES)
                    tx, ty = views["regions"]
                    ni = (int(ty.nearest[y]) * maps["regions"].shape[1] + int(tx.nearest[x])) * 4
                    rid = min((int(flat["regions"][ni]) + 8) // 16, 15)
                    t = Indexed(lum=s[0], cav=s[1], skin=s[2], ext=r[1], pmask=r[2], smask=r[3], leg=p[0], fu=p[1],
                                fv=p[2], dors=p[3], fA=q[0], fB=q[1], fS=q[2], fD=q[3], rid=rid, x=x, y=y,
                                ux=(F(x) + F(0.5)) / F(size), vy=(F(y) + F(0.5)) / F(size))
                    c = NS["shadeTexel"](t, A, LMs)
                    self.assertTrue(np.array_equal(np.asarray(c, dtype=F), ref[y, x]),
                                    f"{name} texel ({x}, {y}) : Swift {c} != Python {ref[y, x]}")

    def test_hair_iris_and_eye_rules(self):
        strands = cr.synthetic_strands(32, 64)
        for name, d in all_cases():
            P = cr.palette(d)
            NS["PAL"] = lambda c, P=P: P
            ip = cr.iris_palette(d)
            IS = NS["iris_init"](swift_config(d))
            self.assertEqual(IS.kind, ip["kind"], name)
            for k in ("base", "blue", "vairon", "pupil", "granula", "sclera", "blueFibers", "sIris", "sVair", "sGran"):
                self.assertTrue(np.array_equal(np.asarray(getattr(IS, k), dtype=np.float64),
                                               np.asarray(ip[k], dtype=np.float64)), f"{name} iris.{k}")
            NS["IRIS"] = lambda c, IS=IS: IS
            hair = NS["composeHair"](swift_config(d), Obj(width=32, height=64, pixels=strands.reshape(-1)))
            self.assertTrue(np.array_equal(hair.pixels.reshape(64, 32, 4), cr.compose_hair(d, strands)), name)
            iris = NS["composeIris"](swift_config(d), None, 48)
            self.assertTrue(np.array_equal(iris.pixels.reshape(48, 48, 4), cr.compose_iris(d, None, 48)), name)

    def test_synthetic_maps_and_axis_tables(self):
        for size in (16, 64, 100):
            m = NS["make"](size)
            ref = cr.synthetic_maps(size)
            for k in MAP_NAMES:
                self.assertTrue(np.array_equal(np.asarray(getattr(m, k).pixels, dtype=np.uint8).reshape(size, size, 4),
                                               ref[k]), f"{k} {size}")
        for w, h in ((32, 64), (128, 256)):
            s = np.asarray(NS["strands"](w, h).pixels, dtype=np.uint8).reshape(h, w, 4)
            self.assertTrue(np.array_equal(s, cr.synthetic_strands(w, h)))
        for ms, os_ in ((64, 96), (1024, 2048), (2048, 1024), (1024, 1024), (48, 48), (7, 3)):
            t = NS["axis_init"](ms, os_)
            r = cr._axis_tables(ms, os_)
            for a, b in zip((t.i0, t.i1, t.w, t.nearest), r):
                self.assertTrue(np.array_equal(np.asarray(a)[:os_], b), (ms, os_))


if __name__ == "__main__":
    unittest.main()
