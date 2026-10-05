import Foundation
import XCTest
@testable import PonyCore

/// Outils partagés par les tests du cœur (préfixés pour ne pas entrer en collision avec les tests du pelage).
enum CoreTestSupport {

    /// Écrivain binaire petit-boutiste minimal, indépendant de `ClipLibrary.encodeBinary` (pour tester le
    /// lecteur contre une construction « à la main » du format SPEC §9).
    struct ByteWriter {
        var bytes: [UInt8] = []

        mutating func u8(_ v: UInt8) {
            bytes.append(v)
        }

        mutating func u16(_ v: UInt16) {
            bytes.append(UInt8(v & 0xFF))
            bytes.append(UInt8(v >> 8))
        }

        mutating func u32(_ v: UInt32) {
            for shift in [0, 8, 16, 24] {
                bytes.append(UInt8((v >> UInt32(shift)) & 0xFF))
            }
        }

        mutating func f32(_ v: Float) {
            u32(v.bitPattern)
        }

        mutating func string(_ s: String) {
            let b = Array(s.utf8)
            u16(UInt16(b.count))
            bytes += b
        }

        mutating func raw(_ s: String) {
            bytes += Array(s.utf8)
        }

        var data: Data {
            return Data(bytes)
        }
    }

    /// Métadonnées de clips de test : valeurs du SPEC §7 + quelques évènements.
    static func clipMetadata() -> [PonyRigManifest.Clip] {
        var out: [PonyRigManifest.Clip] = []
        for name in PonyRigDefaults.clipNames {
            guard let d = PonyRigDefaults.clipDefaults[name] else { continue }
            var events: [PonyRigManifest.ClipEvent] = []
            if name == "walk" {
                events = [PonyRigManifest.ClipEvent(time: 0, name: "foot_down_hl"),
                          PonyRigManifest.ClipEvent(time: 0.25, name: "foot_down_fl")]
            }
            if name == "jump_takeoff" {
                events = [PonyRigManifest.ClipEvent(time: 0.35, name: "takeoff")]
            }
            if name == "neigh" {
                events = [PonyRigManifest.ClipEvent(time: 0.5, name: "snort")]
            }
            out.append(PonyRigManifest.Clip(name: name, loop: d.loop, duration: d.duration,
                                            rootVelocity: SIMD3<Float>(0, 0, -d.forwardSpeed),
                                            rootYawRate: d.yawRate, events: events))
        }
        return out
    }

    /// Manifeste synthétique (squelette du gabarit) + métadonnées des clips du SPEC.
    static func manifest() -> PonyRigManifest {
        var m = PonyRigDefaults.syntheticManifest()
        m.clips = clipMetadata()
        return m
    }

    /// Clip synthétique : la rotation locale de `joint` encode la phase du clip (angle = 2π·u autour de X,
    /// u = temps normalisé), ce qui permet de vérifier la synchronisation de phase.
    static func makeClip(name: String, manifest: PonyRigManifest, frames: Int = 16, joint: String = "neck_03",
                         weightTrack: String? = nil) -> AnimationClip {
        let d = PonyRigDefaults.clipDefaults[name]
        let loop = d?.loop ?? false
        let duration = Double(d?.duration ?? 1)
        let j = manifest.jointIndex(named: joint) ?? 1
        let rest = manifest.joints[j].rest.rotation
        var rotations: [Quat] = []
        for f in 0..<frames {
            let u = loop ? Float(f) / Float(frames) : Float(f) / Float(max(frames - 1, 1))
            rotations.append(rest * Quat(axis: SIMD3<Float>(1, 0, 0), angle: 0.4 * sin(2 * Float.pi * u)))
        }
        var weights: [WeightTrack] = []
        if let w = weightTrack {
            weights.append(WeightTrack(name: w, values: (0..<frames).map { Float($0) / Float(max(frames - 1, 1)) }))
        }
        let meta = manifest.clip(named: name)
        return AnimationClip(name: name, fps: Float(frames) / Float(duration), frameCount: frames,
                             duration: duration, loop: loop,
                             tracks: [JointTrack(jointIndex: j, rotations: rotations)], weightTracks: weights,
                             jointCount: manifest.joints.count,
                             rootVelocity: meta?.rootVelocity ?? SIMD3<Float>(0, 0, -(d?.forwardSpeed ?? 0)),
                             rootYawRate: meta?.rootYawRate ?? (d?.yawRate ?? 0),
                             events: meta?.events ?? [], phaseOffset: meta?.phaseOffset ?? 0)
    }

    /// Bibliothèque contenant un clip synthétique pour chaque nom du SPEC §7.
    static func library(_ manifest: PonyRigManifest) -> ClipLibrary {
        var clips: [AnimationClip] = []
        for name in PonyRigDefaults.clipNames {
            clips.append(makeClip(name: name, manifest: manifest,
                                  weightTrack: name == "neigh" ? "face_mouth_open_soft" : nil))
        }
        return ClipLibrary(clips: clips, jointCount: manifest.joints.count)
    }

    static func runtime(seed: UInt64 = 1, configuration: PonyConfiguration = .default) -> PonyRuntime {
        let m = manifest()
        return PonyRuntime(manifest: m, clips: library(m), configuration: configuration, seed: seed)
    }

    /// Fait avancer le runtime `seconds` secondes à 60 Hz avec une entrée constante ; renvoie les évènements.
    @discardableResult
    static func run(_ runtime: PonyRuntime, seconds: Float, input: PonyInput = PonyInput(),
                    onFrame: ((PonyFrame) -> Void)? = nil) -> [PonyEvent] {
        var events: [PonyEvent] = []
        let steps = Int((seconds * 60).rounded())
        for _ in 0..<steps {
            let frame = runtime.update(deltaTime: 1.0 / 60.0, input: input)
            events += frame.events
            onFrame?(frame)
        }
        return events
    }

    static func assertQuatEqual(_ a: Quat, _ b: Quat, accuracy: Float = 1e-4,
                                file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(a.isApproximatelyEqual(to: b, tolerance: accuracy), "\(a) ≠ \(b)", file: file, line: line)
    }

    static func assertVecEqual(_ a: SIMD3<Float>, _ b: SIMD3<Float>, accuracy: Float = 1e-4,
                               file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertLessThanOrEqual(PonyMath.length(a - b), accuracy, "\(a) ≠ \(b)", file: file, line: line)
    }
}
