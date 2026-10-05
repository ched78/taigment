import XCTest
@testable import PonyCore

final class ClipLibraryTests: XCTestCase {

    private let rotation = Quat(axis: SIMD3<Float>(0, 1, 0), angle: 0.5)

    /// Fichier construit à la main selon SPEC §9 : 1 clip « walk », 30 fps, 4 images,
    /// joint 1 (T animée + R constante), joint 2 (S constante), 1 piste de poids.
    private func handBuiltFile(jointIndex: UInt16 = 1, version: UInt32 = 1, magic: String = "PNYC") -> [UInt8] {
        var w = CoreTestSupport.ByteWriter()
        w.raw(magic)
        w.u32(version)
        w.u32(1)
        w.string("walk")
        w.f32(30)
        w.u32(4)
        w.u16(2)
        w.u16(jointIndex)
        w.u8(0x01 | 0x02 | 0x10)
        for f in 0..<4 {
            w.f32(Float(f))
            w.f32(0)
            w.f32(0)
        }
        w.f32(rotation.x)
        w.f32(rotation.y)
        w.f32(rotation.z)
        w.f32(rotation.w)
        w.u16(2)
        w.u8(0x04 | 0x20)
        w.f32(2)
        w.f32(2)
        w.f32(2)
        w.u16(1)
        w.string("face_nostril_flare")
        for f in 0..<4 {
            w.f32(Float(f) * 0.25)
        }
        return w.bytes
    }

    func testReadsHandBuiltFile() throws {
        let manifest = PonyRigDefaults.syntheticManifest()
        let lib = try ClipLibrary(data: Data(handBuiltFile()), manifest: manifest)
        XCTAssertEqual(lib.names, ["walk"])
        let clip = try XCTUnwrap(lib.clip(named: "walk"))
        XCTAssertEqual(clip.fps, 30)
        XCTAssertEqual(clip.frameCount, 4)
        XCTAssertTrue(clip.loop)                                     // repli SPEC §7
        XCTAssertEqual(clip.duration, 4.0 / 30.0, accuracy: 1e-9)    // boucle : F / fps
        XCTAssertEqual(clip.tracks.count, 2)
        XCTAssertEqual(clip.tracks[0].translations.count, 4)
        XCTAssertEqual(clip.tracks[0].rotations.count, 1)
        XCTAssertEqual(clip.tracks[1].scales, [SIMD3<Float>(2, 2, 2)])
        XCTAssertEqual(clip.weightTracks.first?.name, "face_nostril_flare")
        CoreTestSupport.assertVecEqual(clip.rootVelocity, SIMD3<Float>(0, 0, -1.4))   // repli SPEC §7

        var pose = manifest.joints.map { $0.rest }
        clip.sample(at: 0, into: &pose)
        CoreTestSupport.assertVecEqual(pose[1].translation, SIMD3<Float>(0, 0, 0))
        CoreTestSupport.assertQuatEqual(pose[1].rotation, rotation)
        CoreTestSupport.assertVecEqual(pose[2].scale, SIMD3<Float>(2, 2, 2))
        // Joint absent : pose de repos conservée.
        XCTAssertEqual(pose[3], manifest.joints[3].rest)
    }

    func testLoopSamplingInterpolatesAndWrapsWithoutJump() throws {
        let manifest = PonyRigDefaults.syntheticManifest()
        let clip = try XCTUnwrap(ClipLibrary(data: Data(handBuiltFile()), manifest: manifest).clip(named: "walk"))
        var pose = manifest.joints.map { $0.rest }
        clip.sample(at: 1.5 / 30.0, into: &pose)
        XCTAssertEqual(pose[1].translation.x, 1.5, accuracy: 1e-4)
        // Entre l'image 3 et l'image 0 (image 4 non stockée) : interpolation, pas de saut.
        clip.sample(at: 3.5 / 30.0, into: &pose)
        XCTAssertEqual(pose[1].translation.x, 1.5, accuracy: 1e-4)
        clip.sample(at: 4.0 / 30.0 - 1e-6, into: &pose)
        XCTAssertEqual(pose[1].translation.x, 0, accuracy: 1e-3)
        clip.sample(at: 5.0 / 30.0, into: &pose)                 // deuxième tour, image 1
        XCTAssertEqual(pose[1].translation.x, 1, accuracy: 1e-4)
        clip.sample(at: -1.0 / 30.0, into: &pose)                // temps négatif : image 3
        XCTAssertEqual(pose[1].translation.x, 3, accuracy: 1e-4)
        XCTAssertEqual(clip.weightValue(track: 0, at: 1.5 / 30.0), 0.375, accuracy: 1e-5)
    }

    func testNonLoopClampsAndUsesManifestMetadata() throws {
        var manifest = PonyRigDefaults.syntheticManifest()
        manifest.clips = [PonyRigManifest.Clip(name: "walk", loop: false, rootVelocity: SIMD3<Float>(0, 0, -2),
                                               mask: ["head", "jaw"], phaseOffset: 0.25)]
        let clip = try XCTUnwrap(ClipLibrary(data: Data(handBuiltFile()), manifest: manifest).clip(named: "walk"))
        XCTAssertFalse(clip.loop)
        XCTAssertEqual(clip.duration, 3.0 / 30.0, accuracy: 1e-9)    // non bouclé : (F − 1) / fps
        XCTAssertEqual(clip.maskJoints ?? [], [manifest.jointIndex(named: "head")!, manifest.jointIndex(named: "jaw")!])
        XCTAssertEqual(clip.phaseOffset, 0.25)
        CoreTestSupport.assertVecEqual(clip.rootVelocity, SIMD3<Float>(0, 0, -2))
        var pose = manifest.joints.map { $0.rest }
        clip.sample(at: 3.0 / 30.0, into: &pose)
        XCTAssertEqual(pose[1].translation.x, 3, accuracy: 1e-4)
        clip.sample(at: 10, into: &pose)
        XCTAssertEqual(pose[1].translation.x, 3, accuracy: 1e-4)
        clip.sample(at: -10, into: &pose)
        XCTAssertEqual(pose[1].translation.x, 0, accuracy: 1e-4)
    }

    func testTypedErrors() {
        let manifest = PonyRigDefaults.syntheticManifest()
        XCTAssertThrowsError(try ClipLibrary(data: Data(handBuiltFile(magic: "PNYX")), manifest: manifest)) { e in
            XCTAssertEqual(e as? ClipLibraryError, .badMagic)
        }
        XCTAssertThrowsError(try ClipLibrary(data: Data(handBuiltFile(version: 2)), manifest: manifest)) { e in
            XCTAssertEqual(e as? ClipLibraryError, .unsupportedVersion(2))
        }
        XCTAssertThrowsError(try ClipLibrary(data: Data(handBuiltFile(jointIndex: 999)), manifest: manifest)) { e in
            XCTAssertEqual(e as? ClipLibraryError,
                           .invalidJointIndex(clip: "walk", jointIndex: 999, jointCount: manifest.joints.count))
        }
        var truncated = handBuiltFile()
        truncated.removeLast(3)
        XCTAssertThrowsError(try ClipLibrary(data: Data(truncated), manifest: manifest)) { e in
            guard case .truncated? = e as? ClipLibraryError else {
                return XCTFail("erreur inattendue \(e)")
            }
        }
        var trailing = handBuiltFile()
        trailing.append(0)
        XCTAssertThrowsError(try ClipLibrary(data: Data(trailing), manifest: manifest)) { e in
            XCTAssertEqual(e as? ClipLibraryError, .trailingBytes(count: 1))
        }
        XCTAssertThrowsError(try ClipLibrary(data: Data(), manifest: manifest))
    }

    func testEncodeBinaryRoundTrip() throws {
        let manifest = CoreTestSupport.manifest()
        let original = CoreTestSupport.library(manifest)
        let data = ClipLibrary.encodeBinary(original.clips)
        let reread = try ClipLibrary(data: data, manifest: manifest)
        XCTAssertEqual(reread.names, original.names)
        for (a, b) in zip(original.clips, reread.clips) {
            XCTAssertEqual(a.frameCount, b.frameCount)
            XCTAssertEqual(a.loop, b.loop)
            XCTAssertEqual(a.duration, b.duration, accuracy: 1e-6)
            XCTAssertEqual(a.tracks.count, b.tracks.count)
            for (ta, tb) in zip(a.tracks, b.tracks) {
                XCTAssertEqual(ta.jointIndex, tb.jointIndex)
                for (qa, qb) in zip(ta.rotations, tb.rotations) {
                    CoreTestSupport.assertQuatEqual(qa, qb, accuracy: 1e-5)
                }
            }
            XCTAssertEqual(a.weightTracks, b.weightTracks)
        }
    }

    func testEventsAcrossLoopBoundary() {
        let manifest = CoreTestSupport.manifest()
        let clip = CoreTestSupport.makeClip(name: "walk", manifest: manifest)
        var names: [String] = []
        clip.forEachEvent(from: 0.9, to: 1.1) { names.append($0.name) }
        XCTAssertEqual(names, ["foot_down_hl"])                   // t = 1,05 ≡ 0 du cycle suivant
        names = []
        clip.forEachEvent(from: 0.0, to: 0.3) { names.append($0.name) }
        XCTAssertEqual(names, ["foot_down_fl"])                   // intervalle (from, to]
    }

    func testStrideCyclesMapping() {
        var clip = CoreTestSupport.makeClip(name: "walk", manifest: CoreTestSupport.manifest())
        clip.stridesPerClip = 2
        clip.phaseOffset = 0
        // Deux foulées par clip : 1,5 foulée ⇒ 3/4 du clip.
        XCTAssertEqual(clip.time(forStrideCycles: 1.5), 0.75 * clip.duration, accuracy: 1e-9)
        XCTAssertEqual(clip.strideFrequency, 2 / clip.duration, accuracy: 1e-9)
    }
}

final class PoseBlendingTests: XCTestCase {

    func testWeightedBlendOfTwoAndThreePoses() {
        let a = [Transform(translation: SIMD3<Float>(0, 0, 0)), Transform()]
        let b = [Transform(translation: SIMD3<Float>(4, 0, 0), rotation: Quat(axis: SIMD3<Float>(0, 1, 0), angle: 1)),
                 Transform(scale: SIMD3<Float>(3, 3, 3))]
        var acc = PoseAccumulator(jointCount: 2)
        acc.add(a, weight: 0.75)
        acc.add(b, weight: 0.25)
        var out = [Transform](repeating: .identity, count: 2)
        acc.resolve(into: &out, fallback: a)
        CoreTestSupport.assertVecEqual(out[0].translation, SIMD3<Float>(1, 0, 0))
        CoreTestSupport.assertVecEqual(out[1].scale, SIMD3<Float>(1.5, 1.5, 1.5))
        // nlerp N-aire : proche de slerp pour de petits angles.
        XCTAssertEqual(out[0].rotation.angle, 0.25, accuracy: 0.01)
        // Poids non normalisés : même résultat.
        acc.reset()
        acc.add(a, weight: 3)
        acc.add(b, weight: 1)
        var out2 = [Transform](repeating: .identity, count: 2)
        acc.resolve(into: &out2, fallback: a)
        XCTAssertTrue(out2[0].isApproximatelyEqual(to: out[0]))
        // Trois poses égales : identité du mélange.
        acc.reset()
        for _ in 0..<3 {
            acc.add(b, weight: 0.3)
        }
        acc.resolve(into: &out2, fallback: a)
        XCTAssertTrue(out2[0].isApproximatelyEqual(to: b[0]))
    }

    func testHemisphereAlignment() {
        let q = Quat(axis: SIMD3<Float>(1, 0, 0), angle: 0.7)
        let p1 = [Transform(rotation: q)]
        let p2 = [Transform(rotation: -q)]                      // même rotation, autre signe
        var acc = PoseAccumulator(jointCount: 1)
        acc.add(p1, weight: 0.5)
        acc.add(p2, weight: 0.5)
        var out = [Transform.identity]
        acc.resolve(into: &out, fallback: p1)
        CoreTestSupport.assertQuatEqual(out[0].rotation, q)
    }

    func testZeroWeightUsesFallbackAndMaskedLayer() {
        var acc = PoseAccumulator(jointCount: 3)
        let fallback = [Transform(translation: SIMD3<Float>(9, 9, 9)), Transform(), Transform()]
        let layer = [Transform(translation: SIMD3<Float>(1, 0, 0)), Transform(translation: SIMD3<Float>(2, 0, 0)),
                     Transform(translation: SIMD3<Float>(3, 0, 0))]
        acc.add(layer, weight: 1, mask: [0, 1, 1])
        var out = [Transform](repeating: .identity, count: 3)
        acc.resolve(into: &out, fallback: fallback)
        CoreTestSupport.assertVecEqual(out[0].translation, SIMD3<Float>(9, 9, 9))   // masque nul → repli
        CoreTestSupport.assertVecEqual(out[2].translation, SIMD3<Float>(3, 0, 0))

        var base = [Transform](repeating: .identity, count: 3)
        PoseAccumulator.blendLayer(base: &base, layer: layer, weight: 0.5, mask: [1, 0, 1])
        CoreTestSupport.assertVecEqual(base[0].translation, SIMD3<Float>(0.5, 0, 0))
        CoreTestSupport.assertVecEqual(base[1].translation, SIMD3<Float>(0, 0, 0))     // hors masque : intact
        CoreTestSupport.assertVecEqual(base[2].translation, SIMD3<Float>(1.5, 0, 0))
    }
}
