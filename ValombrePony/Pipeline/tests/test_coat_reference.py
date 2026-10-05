"""Tests du compositeur de robes de référence (numpy) sur cartes synthétiques.

Lancer : python3 -m unittest Pipeline/tests/test_coat_reference.py   (depuis ValombrePony/)
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pony import coat_reference as cr  # noqa: E402

MAPS = cr.synthetic_maps(64)


def cfg_with(diff):
    return cr.deep_merge(cr.plain_config(), diff)


def region_ids(size):
    near = cr._axis_tables(64, size)[3]
    return (MAPS["regions"][np.ix_(near, near)][..., 0].astype(np.int64) + 8) // 16


def lum(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    return 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]


class HashNoiseTests(unittest.TestCase):
    def test_hash_vector_matches_scalar(self):
        rng = np.random.default_rng(3)
        xs = rng.integers(0, 2**32, size=200, dtype=np.uint64)
        vec = cr.hash32(xs.astype(np.uint32))
        for x, v in zip(xs, vec):
            self.assertEqual(int(v), cr.hash32_int(int(x)))
        self.assertEqual(cr.hash32_int(0), 0)

    def test_hash01_range(self):
        h = cr.hash01(np.arange(5000), np.arange(5000) * 7, cr.salted(1, 5))
        self.assertGreaterEqual(float(h.min()), 0.0)
        self.assertLess(float(h.max()), 1.0)
        self.assertAlmostEqual(float(h.mean()), 0.5, delta=0.03)

    def test_value_noise_continuous_and_periodic(self):
        x = np.linspace(0, 20, 4001, dtype=np.float32)
        y = np.full_like(x, 3.3)
        n = cr.value_noise(x, y, 1234)
        self.assertTrue(np.all(n >= 0) and np.all(n < 1))
        self.assertLess(float(np.abs(np.diff(n)).max()), 0.02)
        a = cr.value_noise(np.array([0.25], np.float32), np.array([2.0], np.float32), 99, period_x=6)
        b = cr.value_noise(np.array([6.25], np.float32), np.array([2.0], np.float32), 99, period_x=6)
        self.assertEqual(float(a[0]), float(b[0]))


class ColorTests(unittest.TestCase):
    def test_hex_roundtrip(self):
        for h in ("#000000", "#FFFFFF", "#8B4A22", "#17120F", "#F3F0EA"):
            self.assertEqual(cr.srgb_to_hex(cr.hex_to_srgb(h)), h)
        self.assertEqual(cr.srgb_to_hex(cr.hex_to_srgb("8b4a22")), "#8B4A22")
        self.assertEqual(cr.srgb_to_hex(cr.hex_to_srgb("#12345")), "#000000")
        self.assertEqual(cr.srgb_to_hex(cr.hex_to_srgb("#GG0000")), "#000000")

    def test_encode_lut(self):
        self.assertEqual(int(cr.ENCODE_LUT[0]), 0)
        self.assertEqual(int(cr.ENCODE_LUT[-1]), 255)
        self.assertTrue(np.all(np.diff(cr.ENCODE_LUT.astype(int)) >= 0))
        self.assertEqual(int(cr.encode_linear(np.array([0.5], np.float32))[0]), 188)
        self.assertIn(int(cr.encode_linear(np.array([0.214], np.float32))[0]), (127, 128))


class GeneticsTests(unittest.TestCase):
    def ph(self, diff):
        return cr.phenotype(cfg_with(diff))

    def test_presets(self):
        ps = cr.preset_configs()
        self.assertGreaterEqual(len(ps), 18)
        ids = [p[0] for p in ps]
        self.assertEqual(len(ids), len(set(ids)))
        bai = dict((p[0], p[3]) for p in ps)["bai"]
        self.assertEqual(bai, cr.default_config())
        for pid, name, summary, cfg in ps:
            self.assertTrue(name and summary)
            json.loads(cr.config_to_json(cfg))
            cr.palette(cfg)

    def test_base_colors_and_manes(self):
        bay = self.ph({})
        chestnut = self.ph({"genotype": {"extensionLocus": "ee"}})
        black = self.ph({"genotype": {"agouti": "aa"}})
        self.assertLess(lum(cr.hex_to_srgb(bay["mane"])), 0.12)          # crins noirs du bai (sRGB)
        self.assertGreater(lum(cr.hex_to_srgb(chestnut["mane"])), 0.2)   # crins de l'alezan = robe
        self.assertLess(lum(cr.hex_to_srgb(black["body"])), 0.12)
        flaxen = self.ph({"genotype": {"extensionLocus": "ee"}, "expression": {"flaxen": 1.0}})
        self.assertGreater(lum(cr.hex_to_srgb(flaxen["mane"])), lum(cr.hex_to_srgb(chestnut["mane"])) + 0.2)
        # crins lavés sans effet sur un bai [NV]
        self.assertEqual(self.ph({"expression": {"flaxen": 1.0}})["mane"], bay["mane"])

    def test_silver_only_on_black_pigment(self):
        chestnut = self.ph({"genotype": {"extensionLocus": "ee"}})
        silver_chestnut = self.ph({"genotype": {"extensionLocus": "ee", "silver": "X/n"}})
        self.assertEqual(chestnut["body"], silver_chestnut["body"])
        self.assertEqual(chestnut["mane"], silver_chestnut["mane"])
        black = self.ph({"genotype": {"agouti": "aa"}})
        silver_black = self.ph({"genotype": {"agouti": "aa", "silver": "X/n"}})
        self.assertNotEqual(black["body"], silver_black["body"])
        self.assertGreater(lum(cr.hex_to_srgb(silver_black["mane"])), 0.5)   # crins lavés argentés

    def test_cream_dilutions(self):
        black = self.ph({"genotype": {"agouti": "aa"}})
        smoky = self.ph({"genotype": {"agouti": "aa", "creamPearl": "Cr/N"}})
        d = np.abs(cr.hex_to_srgb(black["body"]) - cr.hex_to_srgb(smoky["body"])).max()
        self.assertLess(float(d), 0.08)                                       # noir porteur crème ≈ noir
        palomino = self.ph({"genotype": {"extensionLocus": "ee", "creamPearl": "Cr/N"}})
        self.assertGreater(lum(cr.hex_to_srgb(palomino["body"])), 0.4)
        cremello = self.ph({"genotype": {"extensionLocus": "ee", "creamPearl": "Cr/Cr"}})
        self.assertEqual(cremello["eye"], "blue")
        self.assertTrue(cremello["pinkSkin"])
        self.assertEqual(cremello["hooves"], ["light"] * 4)
        buckskin = self.ph({"genotype": {"creamPearl": "Cr/N"}})
        self.assertLess(lum(cr.hex_to_srgb(buckskin["points"])), 0.12)       # isabelle : extrémités noires

    def test_dun_dilutes_body_not_points(self):
        bay = self.ph({})
        dun = self.ph({"genotype": {"dun": "X/n"}})
        self.assertGreater(lum(cr.hex_to_srgb(dun["body"])), lum(cr.hex_to_srgb(bay["body"])))
        self.assertEqual(dun["points"], bay["points"])
        self.assertGreater(cr.palette(cfg_with({"genotype": {"dun": "X/n"}})).primitive, 0)
        self.assertEqual(cr.palette(cfg_with({})).primitive, 0)

    def test_eyes(self):
        self.assertEqual(self.ph({})["eye"], "brown")
        self.assertEqual(self.ph({"genotype": {"champagne": "X/n"}})["eye"], "amber")
        self.assertEqual(self.ph({"genotype": {"splashedWhite": "X/n"}})["eye"], "blue")
        self.assertEqual(self.ph({"face": {"kind": "baldFace", "size": 1.4}})["eye"], "blue")
        self.assertEqual(self.ph({"irisStyle": "vairon"})["eye"], "vairon")
        self.assertEqual(self.ph({"overrides": {"eyes": "#30A060"}})["eyeColor"], "#30A060")

    def test_hooves(self):
        p = self.ph({"legs": {"frontLeft": {"height": 0.3}, "hindLeft": {"height": 0.2, "ermine": True},
                              "hindRight": {"height": 0.02}}})
        self.assertEqual(p["hooves"], ["light", "dark", "striped", "striped"])
        self.assertEqual(self.ph({"genotype": {"leopardComplex": "X/n"}})["hooves"], ["striped"] * 4)
        self.assertEqual(self.ph({"overrides": {"hooves": "#405060"}})["hooves"], ["custom"] * 4)

    def test_champagne_skin(self):
        p = cr.palette(cfg_with({"genotype": {"champagne": "X/n"}}))
        self.assertEqual(float(p.freckles), 1.0)

    def test_overrides(self):
        p = self.ph({"overrides": {"body": "#6A8FB0", "mane": "#E05080"}})
        self.assertEqual(p["body"], "#6A8FB0")
        self.assertEqual(p["mane"], "#E05080")
        js = json.loads(cr.config_to_json(cfg_with({"overrides": {"body": "#6A8FB0"}})))
        self.assertEqual(set(js["overrides"]["body"]), {"r", "g", "b"})


class CompositorTests(unittest.TestCase):
    def test_deterministic_and_seeded(self):
        cfg = cfg_with({"genotype": {"roan": "X/n"}})
        a = cr.compose_body(cfg, MAPS, 96)
        b = cr.compose_body(cfg, MAPS, 96)
        self.assertTrue(np.array_equal(a, b))
        c = cr.compose_body(cr.deep_merge(cfg, {"seed": 2}), MAPS, 96)
        self.assertFalse(np.array_equal(a, c))
        self.assertEqual(a.shape, (96, 96, 4))
        self.assertTrue(np.all(a[..., 3] == 255))

    def test_mixed_map_resolutions(self):
        maps = dict(MAPS)
        maps["shading"] = cr.synthetic_maps(128)["shading"]
        maps["patterns"] = cr.synthetic_maps(32)["patterns"]
        out = cr.compose_body(cr.default_config(), maps, 80)
        self.assertEqual(out.shape, (80, 80, 4))
        same = cr.compose_body(cr.default_config(), MAPS, 80)
        self.assertLess(float(np.abs(out.astype(int) - same.astype(int)).mean()), 6.0)

    def test_white_coverage_extremes(self):
        rid = region_ids(96)
        body = (rid == 0)
        none = cr.compose_body(cfg_with({"genotype": {"tobiano": "X/n"}, "expression": {"tobianoCoverage": 0.0}}),
                               MAPS, 96)
        plain = cr.compose_body(cr.plain_config(), MAPS, 96)
        self.assertTrue(np.array_equal(none, plain))
        full = cr.compose_body(cfg_with({"genotype": {"dominantWhite": "X/n"},
                                         "expression": {"dominantWhiteCoverage": 1.0}}), MAPS, 96)
        self.assertGreater(float(lum(full[body][:, :3] / 255.0).min()), 0.6)
        half = cr.compose_body(cfg_with({"genotype": {"tobiano": "X/n"}, "expression": {"tobianoCoverage": 0.5}}),
                               MAPS, 96)
        white = lum(half[body][:, :3] / 255.0) > 0.6
        self.assertTrue(0.1 < float(white.mean()) < 0.9)

    def test_leg_marking_and_hoof(self):
        rid = region_ids(96)
        plain = cr.compose_body(cr.plain_config(), MAPS, 96)
        marked = cr.compose_body(cfg_with({"legs": {"frontLeft": {"height": 0.3}}}), MAPS, 96)
        leg_low = (rid == 5)
        hoof = (rid == 9)
        self.assertGreater(float(lum(marked[hoof][:, :3] / 255.0).mean()),
                           float(lum(plain[hoof][:, :3] / 255.0).mean()) + 0.3)
        changed = np.any(marked != plain, axis=-1)
        self.assertTrue(changed[leg_low].any())
        self.assertFalse(changed[rid == 6].any())                # l'autre antérieur est inchangé
        self.assertFalse(changed[rid == 0].any())

    def test_face_marking_only_on_head(self):
        rid = region_ids(96)
        plain = cr.compose_body(cr.plain_config(), MAPS, 96)
        star = cr.compose_body(cfg_with({"face": {"kind": "blaze", "snip": True}}), MAPS, 96)
        changed = np.any(star != plain, axis=-1)
        self.assertTrue(changed[(rid == 1) | (rid == 2)].any())
        self.assertFalse(changed[~((rid == 1) | (rid == 2) | (rid == 14))].any())

    def test_all_presets_render(self):
        for pid, _, _, cfg in cr.preset_configs():
            out = cr.compose_body(cfg, MAPS, 48)
            self.assertEqual(out.shape, (48, 48, 4), pid)

    def test_hair_alpha_preserved(self):
        strands = cr.synthetic_strands(32, 64)
        for pid, _, _, cfg in cr.preset_configs()[:6]:
            h = cr.compose_hair(cfg, strands)
            self.assertTrue(np.array_equal(h[..., 3], strands[..., 3]), pid)
        bay = cr.compose_hair(cr.default_config(), strands)
        grey = cr.compose_hair(cfg_with({"genotype": {"grey": "X/n"}, "expression": {"greyStage": 0.9}}), strands)
        self.assertGreater(float(lum(grey[..., :3] / 255.0).mean()), float(lum(bay[..., :3] / 255.0).mean()) + 0.2)

    def test_iris(self):
        i = cr.compose_iris(cr.default_config(), None, 64)
        self.assertLess(int(i[32, 32, :3].max()), 30)             # pupille au centre
        blue = cr.compose_iris(cfg_with({"genotype": {"creamPearl": "Cr/Cr", "extensionLocus": "ee"}}), None, 64)
        ring = (slice(30, 34), slice(48, 52))                      # iris, à droite de la pupille
        self.assertGreater(float(blue[ring][..., 2].mean()), float(blue[ring][..., 0].mean()))
        lp = cr.compose_iris(cfg_with({"genotype": {"leopardComplex": "X/n"}}), None, 64)
        self.assertGreater(int(lp[1, 1, :3].min()), 180)          # sclère blanche (coin)
        self.assertLess(int(i[1, 1, :3].max()), 120)              # sclère pigmentée


class SwiftGenerationTests(unittest.TestCase):
    def test_generated_presets_contain_all_ids(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "stages"))
        import s05_coat

        src = s05_coat.swift_presets_source()
        for pid, *_ in cr.PRESETS:
            self.assertIn(f'id: "{pid}"', src)
        self.assertNotIn("None", src)


if __name__ == "__main__":
    unittest.main()
