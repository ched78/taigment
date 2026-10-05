import XCTest
@testable import PonyCore

final class MorphologyTests: XCTestCase {

    private let evaluator = MorphologyEvaluator(manifest: PonyRigDefaults.syntheticManifest())

    func testNeutralGivesZeroWeightsAndUnitScales() {
        let r = evaluator.evaluate(.default)
        for (name, w) in r.blendWeights {
            XCTAssertEqual(w, 0, name)
        }
        XCTAssertTrue(r.jointScales.allSatisfy { $0 == SIMD3<Float>(1, 1, 1) })
        XCTAssertTrue(r.jointOffsets.allSatisfy { $0 == SIMD3<Float>(0, 0, 0) })
    }

    func testBipolarSlidersMapToPlusOrMinusShape() {
        var m = MorphologyConfiguration.default
        m.legLength = 0.6
        m.condition = -0.4
        m.headShape = -1        // busqué
        let r = evaluator.evaluate(m)
        XCTAssertEqual(r.blendWeights["prop_legs_long"] ?? -1, 0.6, accuracy: 1e-6)
        XCTAssertEqual(r.blendWeights["prop_legs_short"] ?? -1, 0, accuracy: 1e-6)
        XCTAssertEqual(r.blendWeights["shape_thin"] ?? -1, 0.4, accuracy: 1e-6)
        XCTAssertEqual(r.blendWeights["shape_fat"] ?? -1, 0, accuracy: 1e-6)
        XCTAssertEqual(r.blendWeights["head_roman"] ?? -1, 1, accuracy: 1e-6)
        XCTAssertEqual(r.blendWeights["head_dished"] ?? -1, 0, accuracy: 1e-6)
    }

    func testWeightsNeverNegativeOrAboveOne() {
        var rng = PonyRandom(seed: 11)
        for _ in 0..<500 {
            let m = MorphologyConfiguration(
                legLength: rng.range(-3, 3), neckLength: rng.range(-3, 3), bodyLength: rng.range(-3, 3),
                stocky: rng.range(-2, 2), refined: rng.range(-2, 2), condition: rng.range(-3, 3),
                muscle: rng.range(-2, 2), belly: rng.range(-2, 2), crest: rng.range(-2, 2), bone: rng.range(-2, 2),
                headShape: rng.range(-3, 3), headShort: rng.range(-2, 2), muzzleBroad: rng.range(-2, 2),
                hoofSize: rng.range(-2, 2), headScale: rng.range(0, 3), earScale: rng.range(0, 3),
                eyeScale: rng.range(0, 3), shetland: rng.range(-2, 3))
            let r = evaluator.evaluate(m)
            for (name, w) in r.blendWeights {
                XCTAssertTrue(w.isFinite, name)
                XCTAssertGreaterThanOrEqual(w, 0, name)
                XCTAssertLessThanOrEqual(w, 1, name)
            }
            for s in r.jointScales {
                XCTAssertTrue(s.x > 0.5 && s.x < 2, "\(s)")
            }
        }
        let nan = MorphologyConfiguration(legLength: .nan, headScale: .infinity)
        let r = evaluator.evaluate(nan)
        XCTAssertEqual(r.blendWeights["prop_legs_long"], 0)
        XCTAssertTrue(r.jointScales.allSatisfy { $0 == SIMD3<Float>(1, 1, 1) })
    }

    func testShetlandCompositeAndScales() {
        let m = MorphologyConfiguration(shetland: 1)
        let e = MorphologyEvaluator.effectiveValues(m)
        XCTAssertLessThan(e.legLength, 0)
        XCTAssertGreaterThan(e.stocky, 0.5)
        XCTAssertLessThan(e.earScale, 1)
        let r = evaluator.evaluate(m)
        XCTAssertGreaterThan(r.blendWeights["prop_legs_short"] ?? 0, 0.5)
        XCTAssertGreaterThan(r.blendWeights["muzzle_broad"] ?? 0, 0.5)
        let skeleton = evaluator.skeleton
        let ear = skeleton.index(of: "ear_l")!
        let head = skeleton.index(of: "head")!
        let eyelid = skeleton.index(of: "eyelid_upper_r")!
        let eye = skeleton.index(of: "eye_r")!
        XCTAssertLessThan(r.jointScales[ear].x, 1)
        XCTAssertGreaterThan(r.jointScales[head].x, 1)
        XCTAssertEqual(r.jointScales[eyelid], r.jointScales[eye])       // paupières à l'échelle de l'œil
    }

    func testManifestSliderOffsetsAndExporterAliases() {
        let skeleton = PonySkeleton(manifest: PonyRigDefaults.syntheticManifest())
        let sliders = [
            PonyRigManifest.MorphSlider(id: "neckLength", plus: "prop_neck_long", minus: "prop_neck_short",
                                        jointOffsetsPlus: ["neck_02": SIMD3<Float>(0, 0.02, 0)]),
            // Format de l'exporteur : `headProfile` (plus = busqué), forme `null` absente du corps.
            PonyRigManifest.MorphSlider(id: "headProfile", plus: "head_roman", minus: "head_dished"),
            PonyRigManifest.MorphSlider(id: "hoovesLarge", plus: nil, minus: nil),
            PonyRigManifest.MorphSlider(id: "bodyLength", plus: "prop_body_long", minus: "prop_body_short",
                                        jointOffsetsPlus: ["spine_02": SIMD3<Float>(0, 0.05, 0)],
                                        jointScalesPlus: ["belly": SIMD3<Float>(1.2, 1.2, 1.2)]),
        ]
        let ev = MorphologyEvaluator(skeleton: skeleton, sliders: sliders)
        var m = MorphologyConfiguration.default
        m.neckLength = 0.5
        m.headShape = 0.8           // concave → head_dished (sens inversé de headProfile)
        m.hoofSize = 1
        m.bodyLength = -1           // côté moins sans décalages déclarés : symétrique du côté plus
        let r = ev.evaluate(m)
        let neck2 = skeleton.index(of: "neck_02")!
        let spine2 = skeleton.index(of: "spine_02")!
        let belly = skeleton.index(of: "belly")!
        CoreTestSupport.assertVecEqual(r.jointOffsets[neck2], SIMD3<Float>(0, 0.01, 0), accuracy: 1e-6)
        CoreTestSupport.assertVecEqual(r.jointOffsets[spine2], SIMD3<Float>(0, -0.05, 0), accuracy: 1e-6)
        XCTAssertEqual(r.jointScales[belly], SIMD3<Float>(1, 1, 1))        // échelle « plus » non appliquée
        XCTAssertEqual(r.blendWeights["head_dished"] ?? -1, 0.8, accuracy: 1e-6)
        XCTAssertEqual(r.blendWeights["head_roman"] ?? -1, 0, accuracy: 1e-6)
        XCTAssertNil(r.blendWeights["hooves_large"])                       // forme déclarée absente
        XCTAssertEqual(r.blendWeights["prop_body_short"] ?? -1, 1, accuracy: 1e-6)
    }

    func testPresets() {
        XCTAssertEqual(MorphologyPreset.all.map { $0.name }, ["Welsh B", "Connemara", "Shetland", "Poney de sport"])
        for p in MorphologyPreset.all {
            XCTAssertTrue(PonyConfiguration.withersHeightRange.contains(p.withersHeight), p.name)
            let r = evaluator.evaluate(p.morphology)
            XCTAssertTrue(r.blendWeights.values.allSatisfy { $0 >= 0 && $0 <= 1 })
        }
        var config = PonyConfiguration.default
        config.apply(preset: .shetland)
        XCTAssertEqual(config.withersHeight, 1.0)
        XCTAssertEqual(config.entityScale, 1.0 / 1.3, accuracy: 1e-6)
    }
}
