import XCTest
@testable import PonyCore

final class ConfigurationTests: XCTestCase {

    private func sample() -> PonyConfiguration {
        var c = PonyConfiguration.default
        c.name = "Étoile de Valombre"
        c.withersHeight = 1.22
        c.hair = HairStyle(mane: "mane_braided", forelock: "forelock_braided", tail: "tail_natural", feathers: true)
        c.morphology.legLength = -0.3
        c.morphology.shetland = 0.4
        c.morphology.earScale = 0.9
        c.accessories = [
            AccessorySelection(partID: "saddle_english",
                               slotColors: ["slot_primary": PonyColor(hex: "#5A3A22"),
                                            "slot_metal": PonyColor(r: 0.8, g: 0.8, b: 0.82)]),
            AccessorySelection(partID: "saddle_pad_english", slotColors: [:], pattern: .stars),
            AccessorySelection(partID: "ribbons_mane", slotColors: ["slot_primary": PonyColor(hex: "1E50C8")]),
        ]
        return c
    }

    func testDefaultRoundTrip() throws {
        let data = try PonyConfiguration.default.jsonData()
        let back = try PonyConfiguration.decode(from: data)
        XCTAssertEqual(back, PonyConfiguration.default)
        XCTAssertEqual(back.version, PonyConfiguration.currentVersion)
    }

    func testCustomRoundTripAndStableJSON() throws {
        let c = sample()
        let data = try c.jsonData()
        let back = try PonyConfiguration.decode(from: data)
        XCTAssertEqual(back, c)
        // JSON stable : deux encodages identiques, clés triées.
        XCTAssertEqual(try back.jsonData(), data)
        let text = String(data: try c.jsonData(pretty: false), encoding: .utf8) ?? ""
        let accessoriesKey = text.range(of: "\"accessories\"")
        let versionKey = text.range(of: "\"version\"")
        XCTAssertNotNil(accessoriesKey)
        XCTAssertNotNil(versionKey)
        if let a = accessoriesKey, let v = versionKey {
            XCTAssertLessThan(a.lowerBound, v.lowerBound)
        }
    }

    func testTolerantDecoding() throws {
        let minimal = try PonyConfiguration.decode(from: Data("{}".utf8))
        XCTAssertEqual(minimal.version, PonyConfiguration.currentVersion)
        XCTAssertEqual(minimal.name, "Poney")
        XCTAssertEqual(minimal.withersHeight, 1.30)
        XCTAssertEqual(minimal.morphology, .default)
        XCTAssertEqual(minimal.hair, .default)
        XCTAssertEqual(minimal.accessories, [])

        let partial = """
        {"name": "Biscotte", "withersHeight": 1.05, "morphology": {"shetland": 1, "futureSlider": 3},
         "accessories": [{"partID": "halter"}, {"bogus": true}, {"partID": "flowers", "pattern": "unknownPattern"}],
         "unknownKey": [1, 2, 3]}
        """
        let p = try PonyConfiguration.decode(from: Data(partial.utf8))
        XCTAssertEqual(p.name, "Biscotte")
        XCTAssertEqual(p.withersHeight, 1.05)
        XCTAssertEqual(p.morphology.shetland, 1)
        XCTAssertEqual(p.morphology.legLength, 0)
        XCTAssertEqual(p.accessories.map { $0.partID }, ["halter", "flowers"])
        XCTAssertNil(p.accessories[1].pattern)
    }

    func testEntityScaleClampsHeight() {
        var c = PonyConfiguration.default
        XCTAssertEqual(c.entityScale, 1, accuracy: 1e-6)
        c.withersHeight = 3
        XCTAssertEqual(c.clampedWithersHeight, 1.48)
        c.withersHeight = .nan
        XCTAssertEqual(c.clampedWithersHeight, 1.30)
    }

    func testMorphologyCodableRoundTrip() throws {
        let m = MorphologyConfiguration(legLength: 0.25, condition: -0.5, headShape: 0.75, headScale: 1.1,
                                        shetland: 0.5)
        let data = try JSONEncoder().encode(m)
        XCTAssertEqual(try JSONDecoder().decode(MorphologyConfiguration.self, from: data), m)
    }
}

final class ManifestTests: XCTestCase {

    /// Extrait au format de l'exporteur (Pipeline/pony/runtime_export.py) avec clés supplémentaires.
    private let json = """
    {
     "format": "ValombrePonyRig", "version": 1, "units": "m", "upAxis": "Y", "forward": "-Z", "fps": 30,
     "joints": [
      {"name": "root", "path": "root", "parent": -1, "rest": {"t": [0,0,0], "r": [-0.7071068,0,0,0.7071068], "s": [1,1,1]},
       "bindModel": [1,0,0,0, 0,0,-1,0, 0,1,0,0, 0,0,0,1]},
      {"name": "body", "path": "root/body", "parent": 0, "rest": {"t": [0,-0.05,0.98], "r": [0,0,0,1], "s": [1,1,1]},
       "bindModel": [1,0,0,0, 0,0,-1,0, 0,1,0,0, 0,0.98,0.05,1]}
     ],
     "blendShapes": {"body": ["shape_stocky", "body_breathe"], "mane_natural": ["shape_crest"]},
     "parts": [{"id": "mane_natural", "file": "Parts/mane_natural.usdz", "category": "hair", "slot": "mane",
                "slots": ["mane"], "materialSlots": ["slot_primary"], "fixedMaterials": [], "fabricSlots": [],
                "blendShapes": ["shape_crest"], "conflicts": [], "requires": [], "hides": []}],
     "clips": [{"name": "walk", "loop": true, "duration": 1.0666667, "frameCount": 32, "fps": 30,
                "rootVelocity": [0, 0, -1.4], "rootYawRate": 0, "mask": null,
                "events": [{"time": 0, "name": "foot_down_hl"}], "phaseOffset": 0,
                "strideLength": 1.47, "strideDuration": 0.5333333, "stridesPerClip": 2,
                "footfalls": {"hl": 0.0, "fl": 0.23}, "contacts": [[1,0,1,1]], "rootPivot": [0, 0, 0.3]}],
     "procedural": {"lookChain": [{"joint": "body", "weight": 1}],
                    "ears": {"left": {"base": "ear_l", "tip": "ear_tip_l"}, "right": {"base": "ear_r", "tip": "ear_tip_r"}},
                    "tail": [], "mane": [], "forelock": [],
                    "eyelids": {"upper_l": "eyelid_upper_l", "lower_l": "eyelid_lower_l"},
                    "eyes": ["eye_l", "eye_r"], "jaw": "jaw", "lips": {"upper": "lip_upper", "lower": "lip_lower"},
                    "secondary": {"belly": "belly", "stirrups": ["stirrup_l", "stirrup_r"]}},
     "morphology": {"sliders": [{"id": "headProfile", "plus": "head_roman", "minus": null,
                                 "jointOffsetsPlus": {}, "jointOffsetsMinus": {}}]},
     "coat": {"maps": {"shading": "coat_shading.png"}, "usdMaps": {"normal": "coat_normal.png"},
              "regions": ["body", "head"], "regionScale": 16, "regionSampling": "nearest"},
     "hair": {"maps": {"strands": "hair_strands.png"}}
    }
    """

    func testDecodesExporterFormat() throws {
        let m = try PonyRigManifest.decode(from: Data(json.utf8))
        XCTAssertEqual(m.joints.count, 2)
        XCTAssertEqual(m.joints[1].parent, 0)
        XCTAssertEqual(m.allBlendShapeNames, ["body_breathe", "shape_crest", "shape_stocky"])
        let clip = try XCTUnwrap(m.clip(named: "walk"))
        XCTAssertNil(clip.mask)
        XCTAssertEqual(clip.stridesPerClip, 2)
        XCTAssertEqual(clip.resolvedStridesPerClip, 2)
        XCTAssertEqual(clip.fps, 30)
        XCTAssertNotNil(clip.footfalls)
        XCTAssertEqual(m.procedural.belly, "belly")
        XCTAssertEqual(m.procedural.stirrups, ["stirrup_l", "stirrup_r"])
        XCTAssertEqual(m.morphology.sliders.first?.id, "headProfile")
        XCTAssertNil(m.morphology.sliders.first?.minus)
        XCTAssertEqual(m.coat?["regionScale"]?.floatValue, 16)
        // bindModel = repère monde : cohérent avec la FK de la pose de repos.
        XCTAssertEqual(m.validationIssues().filter { $0.contains("bindModel") }, [])
    }

    func testSyntheticManifestIsConsistent() {
        let m = PonyRigDefaults.syntheticManifest()
        XCTAssertEqual(m.joints.count, 70)
        XCTAssertEqual(m.joints.map { $0.name }, PonyRigDefaults.jointNames)
        XCTAssertEqual(m.validationIssues(), [])
        // Encodage puis relecture.
        let data = try? JSONEncoder().encode(m)
        XCTAssertNotNil(data)
        if let d = data {
            let back = try? PonyRigManifest.decode(from: d)
            XCTAssertEqual(back?.joints, m.joints)
            XCTAssertEqual(back?.parts, m.parts)
        }
    }

    func testProceduralRigResolvesNestedEarsAndDefaults() {
        var m = PonyRigDefaults.syntheticManifest()
        m.procedural = (try? JSONDecoder().decode(PonyRigManifest.Procedural.self, from: Data("""
        {"ears": {"left": {"base": "ear_l", "tip": "ear_tip_l"}, "right": {"base": "ear_r", "tip": "ear_tip_r"}},
         "secondary": {"belly": "belly", "stirrups": ["stirrup_l"]}}
        """.utf8))) ?? PonyRigManifest.Procedural()
        let skeleton = PonySkeleton(manifest: m)
        let rig = ProceduralRig(skeleton: skeleton, procedural: m.procedural)
        XCTAssertEqual(rig.earLeft, skeleton.index(of: "ear_l"))
        XCTAssertEqual(rig.earRightTip, skeleton.index(of: "ear_tip_r"))
        XCTAssertEqual(rig.stirrups, [skeleton.index(of: "stirrup_l")!])
        XCTAssertEqual(rig.tail.count, 10)                         // repli SPEC
        XCTAssertEqual(rig.lookChain.map { $0.joint }, ["neck_03", "neck_04", "neck_05", "neck_06", "head"].map {
            skeleton.index(of: $0)!
        })
        XCTAssertEqual(rig.lookChain.reduce(0) { $0 + $1.weight }, 1, accuracy: 1e-5)
        XCTAssertEqual(rig.legs.count, 4)
    }

    func testSkeletonFKMatchesBindAndSubtree() {
        let m = PonyRigDefaults.syntheticManifest()
        let s = PonySkeleton(manifest: m)
        let model = s.modelTransforms(local: s.restLocal)
        let hoof = s.index(of: "front_hoof_l")!
        // Sabot antérieur gauche du gabarit : Blender (−0,115 ; 0,496 ; 0,046) → RK (x, z, −y).
        CoreTestSupport.assertVecEqual(model[hoof].translation, SIMD3<Float>(-0.115, 0.046, -0.496), accuracy: 2e-4)
        let neck = s.index(of: "neck_01")!
        let sub = Set(s.subtree(of: neck))
        XCTAssertTrue(sub.contains(s.index(of: "head")!))
        XCTAssertTrue(sub.contains(s.index(of: "mane_03")!))
        XCTAssertFalse(sub.contains(s.index(of: "scapula_l")!))
        XCTAssertTrue(s.isAncestor(neck, of: s.index(of: "ear_tip_r")!))
    }
}
