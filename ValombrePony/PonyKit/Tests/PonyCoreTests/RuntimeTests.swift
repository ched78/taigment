import XCTest
@testable import PonyCore

final class RuntimeTests: XCTestCase {

    private func isFinite(_ t: Transform) -> Bool {
        let values: [Float] = [t.translation.x, t.translation.y, t.translation.z, t.rotation.x, t.rotation.y,
                               t.rotation.z, t.rotation.w, t.scale.x, t.scale.y, t.scale.z]
        return values.allSatisfy { $0.isFinite }
    }

    func testFirstFrameShape() {
        let r = CoreTestSupport.runtime()
        let f = r.update(deltaTime: 1.0 / 60.0, input: PonyInput())
        XCTAssertEqual(f.localPose.count, 70)
        XCTAssertEqual(Set(f.blendWeights.keys), Set(r.blendShapeNames))
        for name in PonyRigDefaults.morphologyShapes + PonyRigDefaults.expressionShapes {
            XCTAssertNotNil(f.blendWeights[name], name)
        }
        for (_, w) in f.blendWeights {
            XCTAssertGreaterThanOrEqual(w, 0)
            XCTAssertLessThanOrEqual(w, 1)
        }
        XCTAssertEqual(f.gait, .idle)
        XCTAssertEqual(f.rootVelocity, SIMD3<Float>(0, 0, 0))
        XCTAssertEqual(f.verticalVelocity, 0)
        XCTAssertFalse(f.isAirborne)
        XCTAssertEqual(f.localPose[0], r.skeleton.restLocal[0])           // racine au repos
        XCTAssertTrue(f.localPose.allSatisfy(isFinite))
    }

    private func scriptedInput(_ i: Int) -> PonyInput {
        var input = PonyInput()
        switch i {
        case 120..<300: input.move = SIMD2<Float>(0.3, 0.6)
        case 300..<420: input.move = SIMD2<Float>(0, 1)
            input.sprint = true
        case 420..<520: input.move = SIMD2<Float>(0, 0)
        case 600..<700: input.move = SIMD2<Float>(-0.5, 0.5)
        default: break
        }
        if i == 200 { input.action = .neigh }
        if i == 400 { input.jumpPressed = true }
        if i == 540 { input.action = .graze }
        return input
    }

    func testDeterministicWithSameSeed() {
        let a = CoreTestSupport.runtime(seed: 5)
        let b = CoreTestSupport.runtime(seed: 5)
        a.lookTarget = SIMD3<Float>(-1, 1.2, -2)
        b.lookTarget = SIMD3<Float>(-1, 1.2, -2)
        for i in 0..<720 {
            let input = scriptedInput(i)
            let fa = a.update(deltaTime: 1.0 / 60.0, input: input)
            let fb = b.update(deltaTime: 1.0 / 60.0, input: input)
            XCTAssertEqual(fa.localPose, fb.localPose, "frame \(i)")
            XCTAssertEqual(fa.blendWeights, fb.blendWeights, "frame \(i)")
            XCTAssertEqual(fa.events, fb.events, "frame \(i)")
            XCTAssertEqual(fa.rootVelocity, fb.rootVelocity, "frame \(i)")
            if fa.localPose != fb.localPose { break }
        }
    }

    func testWalkingMovesForwardAndEmitsFootEvents() {
        let r = CoreTestSupport.runtime()
        let input = PonyInput(move: SIMD2<Float>(0, 0.4))
        let events = CoreTestSupport.run(r, seconds: 4, input: input)
        XCTAssertEqual(r.gait, .walk)
        let f = r.update(deltaTime: 1.0 / 60.0, input: input)
        XCTAssertLessThan(f.rootVelocity.z, -0.5)                      // avance vers −Z
        XCTAssertLessThanOrEqual(-f.rootVelocity.z, 1.4 * 1.18 + 1e-3)
        XCTAssertEqual(f.rootVelocity.y, 0)
        XCTAssertTrue(events.contains(where: { $0.name == "foot_down_hl" }))
    }

    func testFroudeScalingWithWithersHeight() {
        var small = PonyConfiguration.default
        small.withersHeight = 1.0
        let a = CoreTestSupport.runtime()
        let b = CoreTestSupport.runtime(configuration: small)
        let input = PonyInput(move: SIMD2<Float>(0.4, 1))
        CoreTestSupport.run(a, seconds: 6, input: input)
        CoreTestSupport.run(b, seconds: 6, input: input)
        let fa = a.update(deltaTime: 1.0 / 60.0, input: input)
        let fb = b.update(deltaTime: 1.0 / 60.0, input: input)
        let s: Float = 1.0 / 1.3
        XCTAssertEqual(fb.rootVelocity.z / fa.rootVelocity.z, s.squareRoot(), accuracy: 1e-3)
        XCTAssertEqual(fb.rootYawRate / fa.rootYawRate, 1 / s.squareRoot(), accuracy: 1e-3)
    }

    func testJumpSequence() {
        let r = CoreTestSupport.runtime()
        let run = PonyInput(move: SIMD2<Float>(0, 1))
        CoreTestSupport.run(r, seconds: 8, input: run)
        XCTAssertEqual(r.gait, .canter)
        var jump = run
        jump.jumpPressed = true
        var events = r.update(deltaTime: 1.0 / 60.0, input: jump).events
        var sawUp = false
        var sawDown = false
        var sawAirborne = false
        events += CoreTestSupport.run(r, seconds: 3, input: run) { f in
            if f.verticalVelocity > 0.5 { sawUp = true }
            if f.verticalVelocity < -0.5 { sawDown = true }
            if f.isAirborne { sawAirborne = true }
            XCTAssertEqual(f.rootVelocity.y, 0)
        }
        let names = events.map { $0.name }.filter { ["takeoff", "apex", "landing"].contains($0) }
        XCTAssertEqual(names, ["takeoff", "apex", "landing"])
        XCTAssertTrue(sawUp && sawDown && sawAirborne)
        let t0 = events.first(where: { $0.name == "takeoff" })!.time
        let t1 = events.first(where: { $0.name == "landing" })!.time
        let expected = Double(JumpSettings().flightTime(sizeScale: 1))
        XCTAssertEqual(expected, 2 * (2 * 9.81 * 0.4).squareRoot() / 9.81, accuracy: 1e-4)   // t = 2·v0/g, h = 0,40 m
        XCTAssertEqual(t1 - t0, expected, accuracy: 2.0 / 60.0)
        XCTAssertFalse(r.isAirborne)
        XCTAssertTrue(r.gait == .canter || r.gait == .gallop)
    }

    func testExternalLandingHoldsAirPhase() {
        let r = CoreTestSupport.runtime()
        r.usesExternalLanding = true
        let run = PonyInput(move: SIMD2<Float>(0, 1))
        CoreTestSupport.run(r, seconds: 8, input: run)
        var jump = run
        jump.jumpPressed = true
        _ = r.update(deltaTime: 1.0 / 60.0, input: jump)
        CoreTestSupport.run(r, seconds: 1.5, input: run)
        XCTAssertTrue(r.isAirborne)                                    // vol calculé dépassé, tenue
        r.notifyLanded()
        let f = r.update(deltaTime: 1.0 / 60.0, input: run)
        XCTAssertFalse(f.isAirborne)
        XCTAssertTrue(f.events.contains(where: { $0.name == "landing" }))
    }

    func testGrazeIsInterruptedByMovement() {
        let r = CoreTestSupport.runtime()
        _ = r.update(deltaTime: 1.0 / 60.0, input: PonyInput(move: SIMD2<Float>(0, 0), action: .graze))
        CoreTestSupport.run(r, seconds: 3)
        XCTAssertEqual(r.currentAction, .graze)
        XCTAssertEqual(r.motion.mode, .grazeLoop)
        CoreTestSupport.run(r, seconds: 0.1, input: PonyInput(move: SIMD2<Float>(0, 0.6)))
        XCTAssertEqual(r.motion.mode, .grazeUp)
        CoreTestSupport.run(r, seconds: 3, input: PonyInput(move: SIMD2<Float>(0, 0.6)))
        XCTAssertNil(r.currentAction)
        XCTAssertNotEqual(r.gait, .idle)
    }

    func testRollOnlyFromLyingAndGetUp() {
        let r = CoreTestSupport.runtime()
        _ = r.update(deltaTime: 1.0 / 60.0, input: PonyInput(move: SIMD2<Float>(0, 0), action: .roll))
        CoreTestSupport.run(r, seconds: 1)
        XCTAssertNil(r.currentAction)                                  // debout : roulade refusée
        _ = r.update(deltaTime: 1.0 / 60.0, input: PonyInput(move: SIMD2<Float>(0, 0), action: .lieDown))
        CoreTestSupport.run(r, seconds: 4)
        XCTAssertEqual(r.motion.mode, .lying)
        _ = r.update(deltaTime: 1.0 / 60.0, input: PonyInput(move: SIMD2<Float>(0, 0), action: .roll))
        CoreTestSupport.run(r, seconds: 0.5)
        XCTAssertEqual(r.currentAction, .roll)
        CoreTestSupport.run(r, seconds: 5)
        XCTAssertEqual(r.motion.mode, .lying)
        _ = r.update(deltaTime: 1.0 / 60.0, input: PonyInput(move: SIMD2<Float>(0, 0), action: .getUp))
        CoreTestSupport.run(r, seconds: 3)
        XCTAssertNil(r.currentAction)
        XCTAssertEqual(r.motion.mode, .locomotion)
    }

    func testHeadShakeIsMaskedOverWalk() {
        let a = CoreTestSupport.runtime(seed: 2)
        let b = CoreTestSupport.runtime(seed: 2)
        let walk = PonyInput(move: SIMD2<Float>(0, 0.4))
        CoreTestSupport.run(a, seconds: 2, input: walk)
        CoreTestSupport.run(b, seconds: 2, input: walk)
        var shake = walk
        shake.action = .headShake
        _ = a.update(deltaTime: 1.0 / 60.0, input: shake)
        _ = b.update(deltaTime: 1.0 / 60.0, input: walk)
        CoreTestSupport.run(a, seconds: 0.3, input: walk)
        CoreTestSupport.run(b, seconds: 0.3, input: walk)
        XCTAssertEqual(a.currentAction, .headShake)
        XCTAssertEqual(a.gait, .walk)
        let fa = a.update(deltaTime: 1.0 / 60.0, input: walk)
        let fb = b.update(deltaTime: 1.0 / 60.0, input: walk)
        let neck = a.skeleton.index(of: "neck_03")!
        let thigh = a.skeleton.index(of: "thigh_l")!
        XCTAssertNotEqual(fa.localPose[neck], fb.localPose[neck])      // dans le masque : modifié
        XCTAssertEqual(fa.localPose[thigh], fb.localPose[thigh])      // hors masque : intact
        XCTAssertEqual(fa.rootVelocity, fb.rootVelocity)
    }

    func testJointOverride() {
        let r = CoreTestSupport.runtime()
        let q = Quat(axis: SIMD3<Float>(1, 0, 0), angle: 0.5)
        r.setJointOverride("jaw", rotation: q, weight: 1)
        let jaw = r.skeleton.index(of: "jaw")!
        var f = r.update(deltaTime: 1.0 / 60.0, input: PonyInput())
        CoreTestSupport.assertQuatEqual(f.localPose[jaw].rotation, q)
        r.setJointOverride("jaw", rotation: q, weight: 0.5)
        f = r.update(deltaTime: 1.0 / 60.0, input: PonyInput())
        let angle = Quat(x: -q.x, y: -q.y, z: -q.z, w: q.w) * f.localPose[jaw].rotation
        XCTAssertGreaterThan(angle.angle, 0.01)                        // à mi-chemin, pas égal à la surcharge
        r.setJointOverride("jaw", rotation: nil, weight: 1)
        f = r.update(deltaTime: 1.0 / 60.0, input: PonyInput())
        CoreTestSupport.assertQuatEqual(f.localPose[jaw].rotation, r.skeleton.restLocal[jaw].rotation)
        r.setJointOverride("inexistant", rotation: q, weight: 1)      // ignoré sans plantage
    }

    func testLookTargetTurnsHeadTowardTarget() {
        let a = CoreTestSupport.runtime()
        let b = CoreTestSupport.runtime()
        let head = a.skeleton.index(of: "head")!
        let headModel = a.skeleton.bindModel[head]
        a.lookTarget = headModel.translation + SIMD3<Float>(-2, 0, -0.5)   // à gauche
        CoreTestSupport.run(a, seconds: 2)
        CoreTestSupport.run(b, seconds: 2)
        let fa = a.update(deltaTime: 1.0 / 60.0, input: PonyInput())
        let fb = b.update(deltaTime: 1.0 / 60.0, input: PonyInput())
        let ma = a.skeleton.modelTransforms(local: fa.localPose)
        let mb = b.skeleton.modelTransforms(local: fb.localPose)
        let dirA = ma[head].rotation.act(SIMD3<Float>(0, 1, 0))
        let dirB = mb[head].rotation.act(SIMD3<Float>(0, 1, 0))
        let yawA = PoseEditing.azimuth(dirA)
        let yawB = PoseEditing.azimuth(dirB)
        XCTAssertGreaterThan(yawA - yawB, 0.4)                          // la tête tourne vers la gauche
        XCTAssertLessThanOrEqual(yawA - yawB, ProceduralSettings().lookMaxYaw + 0.05)
    }

    func testMorphologyKeepsHoovesOnTheGround() {
        var manifest = CoreTestSupport.manifest()
        manifest.morphology.sliders = [PonyRigManifest.MorphSlider(
            id: "legLength", plus: "prop_legs_long", minus: "prop_legs_short",
            jointOffsetsPlus: ["front_cannon_l": SIMD3<Float>(0, 0.04, 0), "front_cannon_r": SIMD3<Float>(0, 0.04, 0),
                               "hind_cannon_l": SIMD3<Float>(0, 0.04, 0), "hind_cannon_r": SIMD3<Float>(0, 0.04, 0)])]
        var config = PonyConfiguration.default
        config.morphology.legLength = 1
        let r = PonyRuntime(manifest: manifest, clips: CoreTestSupport.library(manifest), configuration: config)
        let f = r.update(deltaTime: 1.0 / 60.0, input: PonyInput())
        XCTAssertEqual(f.blendWeights["prop_legs_long"], 1)
        XCTAssertEqual(f.blendWeights["prop_legs_short"], 0)
        let model = r.skeleton.modelTransforms(local: f.localPose)
        let rest = r.skeleton.bindModel
        let hooves = ["front_hoof_l", "front_hoof_r", "hind_hoof_l", "hind_hoof_r"].map { r.skeleton.index(of: $0)! }
        let minPosed = hooves.map { model[$0].translation.y }.min()!
        let minRest = hooves.map { rest[$0].translation.y }.min()!
        XCTAssertEqual(minPosed, minRest, accuracy: 2e-3)
        let body = r.skeleton.index(of: "body")!
        XCTAssertGreaterThan(model[body].translation.y, rest[body].translation.y + 0.02)   // tronc relevé
        // Retour au neutre : plus de décalage.
        r.configuration.morphology.legLength = 0
        XCTAssertEqual(r.morphology.jointOffsets[body], SIMD3<Float>(0, 0, 0))
    }

    func testBreathingEffortRisesAtGallop() {
        let r = CoreTestSupport.runtime()
        var maxFlare: Float = 0
        CoreTestSupport.run(r, seconds: 15, input: PonyInput(move: SIMD2<Float>(0, 1), sprint: true)) { f in
            maxFlare = max(maxFlare, f.blendWeights["face_nostril_flare"] ?? 0)
        }
        XCTAssertEqual(r.gait, .gallop)
        XCTAssertGreaterThan(r.effort, 0.5)
        XCTAssertGreaterThan(maxFlare, 0.3)
        let effortAtGallop = r.effort
        CoreTestSupport.run(r, seconds: 10)
        XCTAssertLessThan(r.effort, effortAtGallop)                    // récupération
    }

    func testRobustToInvalidInput() {
        let r = CoreTestSupport.runtime()
        let bad = PonyInput(move: SIMD2<Float>(Float.nan, Float.infinity))
        let f1 = r.update(deltaTime: Float.nan, input: bad)
        let f2 = r.update(deltaTime: 10, input: bad)
        let f3 = r.update(deltaTime: -1, input: PonyInput())
        for f in [f1, f2, f3] {
            XCTAssertTrue(f.localPose.allSatisfy(isFinite))
            XCTAssertTrue(f.blendWeights.values.allSatisfy { $0.isFinite })
        }
    }

    func testRuntimeWithoutClipsStillMoves() {
        let m = PonyRigDefaults.syntheticManifest()
        let r = PonyRuntime(manifest: m, clips: .empty(manifest: m), configuration: .default)
        CoreTestSupport.run(r, seconds: 3, input: PonyInput(move: SIMD2<Float>(0, 0.5)))
        let f = r.update(deltaTime: 1.0 / 60.0, input: PonyInput(move: SIMD2<Float>(0, 0.5)))
        XCTAssertLessThan(f.rootVelocity.z, -0.5)                      // vitesses de repli du SPEC §7
        XCTAssertTrue(f.localPose.allSatisfy(isFinite))
    }

    /// Mesure indicative (le budget de 0,3 ms/frame vise un build optimisé sur appareil ; non vérifiable ici).
    func testUpdateCostIsReasonable() {
        let r = CoreTestSupport.runtime()
        r.lookTarget = SIMD3<Float>(0, 1.2, -2)
        let input = PonyInput(move: SIMD2<Float>(0.3, 0.8))
        CoreTestSupport.run(r, seconds: 1, input: input)
        let frames = 600
        let start = Date()
        for _ in 0..<frames {
            _ = r.update(deltaTime: 1.0 / 60.0, input: input)
        }
        let perFrame = Date().timeIntervalSince(start) / Double(frames)
        print("PonyRuntime.update : \(perFrame * 1000) ms/frame")
        XCTAssertLessThan(perFrame, 0.005)
    }
}
