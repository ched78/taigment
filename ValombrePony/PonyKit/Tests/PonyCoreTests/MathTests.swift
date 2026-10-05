import XCTest
@testable import PonyCore

final class QuatTests: XCTestCase {

    func testIdentityAndAxisAngle() {
        let v = SIMD3<Float>(1, 2, 3)
        CoreTestSupport.assertVecEqual(Quat.identity.act(v), v)
        // 90° autour de +Z : X → Y.
        let q = Quat(axis: SIMD3<Float>(0, 0, 1), angle: Float.pi / 2)
        CoreTestSupport.assertVecEqual(q.act(SIMD3<Float>(1, 0, 0)), SIMD3<Float>(0, 1, 0))
        // Axe non normalisé accepté.
        let q2 = Quat(axis: SIMD3<Float>(0, 0, 5), angle: Float.pi / 2)
        CoreTestSupport.assertQuatEqual(q, q2)
        XCTAssertEqual(q.angle, Float.pi / 2, accuracy: 1e-5)
        CoreTestSupport.assertVecEqual(q.axis, SIMD3<Float>(0, 0, 1))
        // Axe nul : identité.
        XCTAssertEqual(Quat(axis: SIMD3<Float>(0, 0, 0), angle: 1), .identity)
    }

    func testMultiplicationComposesRightToLeft() {
        let a = Quat(axis: SIMD3<Float>(0, 0, 1), angle: Float.pi / 2)   // X → Y
        let b = Quat(axis: SIMD3<Float>(1, 0, 0), angle: Float.pi / 2)   // Y → Z
        let v = SIMD3<Float>(1, 0, 0)
        // (b * a) applique a puis b : X → Y → Z.
        CoreTestSupport.assertVecEqual((b * a).act(v), SIMD3<Float>(0, 0, 1))
        CoreTestSupport.assertVecEqual((b * a).act(v), b.act(a.act(v)))
    }

    func testInverseAndConjugate() {
        let q = Quat(axis: SIMD3<Float>(1, 2, -0.5), angle: 1.234)
        CoreTestSupport.assertQuatEqual(q * q.inverse, .identity)
        CoreTestSupport.assertQuatEqual(q.conjugate, q.inverse)
        let v = SIMD3<Float>(0.3, -1, 2)
        CoreTestSupport.assertVecEqual(q.inverse.act(q.act(v)), v)
        let unnormalized = Quat(x: q.x * 3, y: q.y * 3, z: q.z * 3, w: q.w * 3)
        CoreTestSupport.assertQuatEqual(unnormalized * unnormalized.inverse, .identity)
        XCTAssertEqual(unnormalized.normalized.length, 1, accuracy: 1e-5)
    }

    func testSlerpEndpointsMidpointAndHemisphere() {
        let a = Quat.identity
        let b = Quat(axis: SIMD3<Float>(0, 1, 0), angle: 1.0)
        CoreTestSupport.assertQuatEqual(Quat.slerp(a, b, 0), a)
        CoreTestSupport.assertQuatEqual(Quat.slerp(a, b, 1), b)
        CoreTestSupport.assertQuatEqual(Quat.slerp(a, b, 0.5), Quat(axis: SIMD3<Float>(0, 1, 0), angle: 0.5))
        // Hémisphère opposé : -b représente la même rotation, le chemin reste le plus court.
        CoreTestSupport.assertQuatEqual(Quat.slerp(a, -b, 0.5), Quat(axis: SIMD3<Float>(0, 1, 0), angle: 0.5))
        CoreTestSupport.assertQuatEqual(Quat.nlerp(a, -b, 0.5), Quat(axis: SIMD3<Float>(0, 1, 0), angle: 0.5),
                                        accuracy: 1e-3)
        // Vitesse angulaire constante.
        let q = Quat.slerp(a, Quat(axis: SIMD3<Float>(1, 0, 0), angle: 2.0), 0.25)
        XCTAssertEqual(q.angle, 0.5, accuracy: 1e-4)
    }

    func testFromToVectors() {
        let from = SIMD3<Float>(1, 0, 0)
        let to = SIMD3<Float>(0, 0, -3)
        let q = Quat(from: from, to: to)
        CoreTestSupport.assertVecEqual(q.act(from), SIMD3<Float>(0, 0, -1))
        // Vecteurs opposés : demi-tour valide.
        let half = Quat(from: SIMD3<Float>(0, 1, 0), to: SIMD3<Float>(0, -1, 0))
        CoreTestSupport.assertVecEqual(half.act(SIMD3<Float>(0, 1, 0)), SIMD3<Float>(0, -1, 0))
        XCTAssertEqual(half.angle, Float.pi, accuracy: 1e-4)
        // Identiques : identité.
        CoreTestSupport.assertQuatEqual(Quat(from: from, to: from * 2), .identity)
    }

    func testClampedAngleAndRotationMatrix() {
        let q = Quat(axis: SIMD3<Float>(0, 1, 0), angle: 1.5)
        XCTAssertEqual(q.clampedAngle(0.5).angle, 0.5, accuracy: 1e-5)
        XCTAssertEqual(q.clampedAngle(2).angle, 1.5, accuracy: 1e-5)
        let r = Quat(axis: SIMD3<Float>(0.2, -0.7, 0.4), angle: 2.2)
        let c0 = r.act(SIMD3<Float>(1, 0, 0))
        let c1 = r.act(SIMD3<Float>(0, 1, 0))
        let c2 = r.act(SIMD3<Float>(0, 0, 1))
        CoreTestSupport.assertQuatEqual(Quat(rotationColumns: c0, c1, c2), r)
    }

    func testCodableAsArray() throws {
        let q = Quat(x: 0.1, y: 0.2, z: 0.3, w: 0.9)
        let data = try JSONEncoder().encode(q)
        XCTAssertEqual(String(data: data, encoding: .utf8)?.first, "[")
        let back = try JSONDecoder().decode(Quat.self, from: data)
        XCTAssertEqual(back, q)
        let decoded = try JSONDecoder().decode(Quat.self, from: Data("[0,0,0,1]".utf8))
        XCTAssertEqual(decoded, .identity)
    }
}

final class TransformTests: XCTestCase {

    func testCompositionParentChild() {
        let parent = Transform(translation: SIMD3<Float>(1, 0, 0),
                               rotation: Quat(axis: SIMD3<Float>(0, 0, 1), angle: Float.pi / 2),
                               scale: SIMD3<Float>(2, 2, 2))
        let child = Transform(translation: SIMD3<Float>(1, 0, 0))
        let world = parent * child
        // Point (1,0,0) de l'enfant : échelle 2 → (2,0,0), rotation → (0,2,0), translation → (1,2,0).
        CoreTestSupport.assertVecEqual(world.translation, SIMD3<Float>(1, 2, 0))
        CoreTestSupport.assertVecEqual(world.scale, SIMD3<Float>(2, 2, 2))
        CoreTestSupport.assertVecEqual(parent.transformPoint(child.translation), world.translation)
    }

    func testInverse() {
        let t = Transform(translation: SIMD3<Float>(0.5, -2, 3),
                          rotation: Quat(axis: SIMD3<Float>(1, 1, 0), angle: 0.8),
                          scale: SIMD3<Float>(1.5, 1.5, 1.5))
        let id = t * t.inverse
        XCTAssertTrue(id.isApproximatelyEqual(to: .identity, tolerance: 1e-4))
        let p = SIMD3<Float>(0.2, 0.4, -0.9)
        CoreTestSupport.assertVecEqual(t.inverse.transformPoint(t.transformPoint(p)), p)
        CoreTestSupport.assertVecEqual(t.inverseTransformPoint(t.transformPoint(p)), p)
    }

    func testInterpolation() {
        let a = Transform(translation: SIMD3<Float>(0, 0, 0))
        let b = Transform(translation: SIMD3<Float>(2, 0, 0), rotation: Quat(axis: SIMD3<Float>(0, 1, 0), angle: 1),
                          scale: SIMD3<Float>(3, 3, 3))
        let m = Transform.interpolate(a, b, 0.5)
        CoreTestSupport.assertVecEqual(m.translation, SIMD3<Float>(1, 0, 0))
        CoreTestSupport.assertVecEqual(m.scale, SIMD3<Float>(2, 2, 2))
        XCTAssertEqual(m.rotation.angle, 0.5, accuracy: 1e-4)
    }

    func testColumnMajorRoundTrip() {
        let t = Transform(translation: SIMD3<Float>(0.1, 0.98, -0.05),
                          rotation: Quat(axis: SIMD3<Float>(1, 0, 0), angle: -Float.pi / 2),
                          scale: SIMD3<Float>(1, 1, 1))
        let m = t.columnMajor
        XCTAssertEqual(m.count, 16)
        XCTAssertEqual(m[12], 0.1, accuracy: 1e-6)
        XCTAssertEqual(m[15], 1)
        XCTAssertTrue(Transform(columnMajor: m).isApproximatelyEqual(to: t, tolerance: 1e-5))
        XCTAssertEqual(Transform(columnMajor: [1, 2, 3]), Transform.identity)
    }

    func testCodableKeys() throws {
        let json = #"{"t":[1,2,3],"r":[0,0,0,1]}"#
        let t = try JSONDecoder().decode(Transform.self, from: Data(json.utf8))
        CoreTestSupport.assertVecEqual(t.translation, SIMD3<Float>(1, 2, 3))
        CoreTestSupport.assertVecEqual(t.scale, SIMD3<Float>(1, 1, 1))   // « s » absent → 1
    }
}

final class PonyMathTests: XCTestCase {

    func testClampSmoothstepWrap() {
        XCTAssertEqual(PonyMath.clamp(5, 0, 1), 1)
        XCTAssertEqual(PonyMath.clamp(-5, 0, 1), 0)
        XCTAssertEqual(PonyMath.smoothstep(0, 1, 0.5), 0.5, accuracy: 1e-6)
        XCTAssertEqual(PonyMath.smoothstep(0, 1, -1), 0)
        XCTAssertEqual(PonyMath.smoothstep(0, 1, 2), 1)
        XCTAssertEqual(abs(PonyMath.wrapAngle(3 * Float.pi)), Float.pi, accuracy: 1e-5)
        XCTAssertEqual(PonyMath.wrapAngle(2 * Float.pi + 0.5), 0.5, accuracy: 1e-5)
        XCTAssertEqual(PonyMath.wrapAngle(-Float.pi / 2), -Float.pi / 2, accuracy: 1e-6)
        XCTAssertEqual(PonyMath.fract(-0.25), 0.75, accuracy: 1e-12)
        XCTAssertEqual(PonyMath.moveTowards(0, 10, maxDelta: 3), 3)
        XCTAssertEqual(PonyMath.moveTowards(9, 10, maxDelta: 3), 10)
    }

    func testDampIsFrameRateIndependent() {
        var oneStep: Float = 0
        oneStep = PonyMath.damp(oneStep, toward: 1, halfLife: 0.2, deltaTime: 0.1)
        var manySteps: Float = 0
        for _ in 0..<10 {
            manySteps = PonyMath.damp(manySteps, toward: 1, halfLife: 0.2, deltaTime: 0.01)
        }
        XCTAssertEqual(oneStep, manySteps, accuracy: 1e-5)
        // Après une demi-vie, la moitié du chemin.
        XCTAssertEqual(PonyMath.damp(0, toward: 1, halfLife: 0.3, deltaTime: 0.3), 0.5, accuracy: 1e-5)
    }

    func testCriticalSpringConvergesWithoutOvershoot() {
        var s = CriticalSpring(value: 0)
        var maxValue: Float = 0
        for _ in 0..<600 {
            s.update(target: 1, halfLife: 0.1, deltaTime: 1.0 / 60.0)
            maxValue = max(maxValue, s.value)
        }
        XCTAssertEqual(s.value, 1, accuracy: 1e-4)
        XCTAssertLessThanOrEqual(maxValue, 1.0001)
        // Grand pas de temps : reste stable (forme analytique).
        var big = CriticalSpring(value: 0)
        big.update(target: 1, halfLife: 0.01, deltaTime: 10)
        XCTAssertTrue(big.value.isFinite)
        XCTAssertEqual(big.value, 1, accuracy: 1e-3)
    }

    func testRandomIsDeterministic() {
        var a = PonyRandom(seed: 42)
        var b = PonyRandom(seed: 42)
        var c = PonyRandom(seed: 43)
        var same = true
        var differs = false
        for _ in 0..<100 {
            let x = a.next()
            if x != b.next() { same = false }
            if x != c.next() { differs = true }
        }
        XCTAssertTrue(same)
        XCTAssertTrue(differs)
        var r = PonyRandom(seed: 7)
        for _ in 0..<1000 {
            let f = r.nextFloat()
            XCTAssertGreaterThanOrEqual(f, 0)
            XCTAssertLessThan(f, 1)
        }
    }
}
