import Foundation

/// Bibliothèque de clips : lecture de `PonyClips.bin` (SPEC §9, petit-boutiste) fusionnée avec les
/// métadonnées des clips de `PonyRig.json` (boucle, durée, vitesses, masque, évènements, phase).
///
/// Immuable après construction (d'où `@unchecked Sendable`) ; partageable entre plusieurs runtimes.
public final class ClipLibrary: @unchecked Sendable {
    public let clips: [AnimationClip]
    public let jointCount: Int
    private let indexByName: [String: Int]

    /// Limites de sécurité contre les fichiers corrompus.
    static let maxClips = 4096
    static let maxFrames = 100_000

    /// Lit `PonyClips.bin`. Les métadonnées absentes du manifeste prennent les valeurs du SPEC §7.
    public init(data: Data, manifest: PonyRigManifest) throws {
        let parsed = try ClipLibrary.parse(data: data, manifest: manifest)
        clips = parsed
        jointCount = manifest.joints.count
        indexByName = ClipLibrary.makeIndex(parsed)
    }

    /// Bibliothèque construite directement (tests, clips procéduraux).
    public init(clips: [AnimationClip], jointCount: Int) {
        self.clips = clips
        self.jointCount = jointCount
        indexByName = ClipLibrary.makeIndex(clips)
    }

    /// Bibliothèque vide : le runtime reste utilisable (pose de repos + procédural + déplacement).
    public static func empty(manifest: PonyRigManifest) -> ClipLibrary {
        return ClipLibrary(clips: [], jointCount: manifest.joints.count)
    }

    public var names: [String] {
        return clips.map { $0.name }
    }

    public func index(of name: String) -> Int? {
        return indexByName[name]
    }

    public func clip(named name: String) -> AnimationClip? {
        guard let i = indexByName[name] else { return nil }
        return clips[i]
    }

    private static func makeIndex(_ clips: [AnimationClip]) -> [String: Int] {
        var d: [String: Int] = [:]
        for (i, c) in clips.enumerated() where d[c.name] == nil {
            d[c.name] = i
        }
        return d
    }

    // MARK: Lecture

    static func parse(data: Data, manifest: PonyRigManifest) throws -> [AnimationClip] {
        let jointCount = manifest.joints.count
        var nameToJoint: [String: Int] = [:]
        for (i, j) in manifest.joints.enumerated() where nameToJoint[j.name] == nil {
            nameToJoint[j.name] = i
        }
        var reader = PonyBinaryReader(data: data)
        let magic = try reader.readBytes(4)
        if magic != [0x50, 0x4E, 0x59, 0x43] {          // « PNYC »
            throw ClipLibraryError.badMagic
        }
        let version = try reader.readU32()
        if version != 1 {
            throw ClipLibraryError.unsupportedVersion(version)
        }
        let clipCount = Int(try reader.readU32())
        if clipCount > maxClips {
            throw ClipLibraryError.tooLarge(field: "clipCount", value: clipCount)
        }
        var out: [AnimationClip] = []
        out.reserveCapacity(clipCount)
        for _ in 0..<clipCount {
            let nameLen = Int(try reader.readU16())
            let name = try reader.readString(byteCount: nameLen)
            let fps = try reader.readF32()
            if !fps.isFinite || fps <= 0 || fps > 1000 {
                throw ClipLibraryError.invalidFrameRate(clip: name, fps: fps)
            }
            let frameCount = Int(try reader.readU32())
            if frameCount < 1 || frameCount > maxFrames {
                throw ClipLibraryError.invalidFrameCount(clip: name, frameCount: frameCount)
            }
            let trackCount = Int(try reader.readU16())
            var tracks: [JointTrack] = []
            tracks.reserveCapacity(trackCount)
            for _ in 0..<trackCount {
                let jointIndex = Int(try reader.readU16())
                let flags = try reader.readU8()
                if jointIndex >= jointCount {
                    throw ClipLibraryError.invalidJointIndex(clip: name, jointIndex: jointIndex,
                                                             jointCount: jointCount)
                }
                var track = JointTrack(jointIndex: jointIndex)
                if flags & 0x01 != 0 {
                    let n = flags & 0x08 != 0 ? 1 : frameCount
                    track.translations = try reader.readVec3Array(n)
                }
                if flags & 0x02 != 0 {
                    let n = flags & 0x10 != 0 ? 1 : frameCount
                    let raw = try reader.readQuatArray(n)
                    track.rotations = ClipLibrary.continuousNormalized(raw)
                }
                if flags & 0x04 != 0 {
                    let n = flags & 0x20 != 0 ? 1 : frameCount
                    track.scales = try reader.readVec3Array(n)
                }
                if !ClipLibrary.isFinite(track) {
                    throw ClipLibraryError.nonFiniteValue(clip: name)
                }
                tracks.append(track)
            }
            let weightCount = Int(try reader.readU16())
            var weights: [WeightTrack] = []
            weights.reserveCapacity(weightCount)
            for _ in 0..<weightCount {
                let len = Int(try reader.readU16())
                let wName = try reader.readString(byteCount: len)
                let values = try reader.readFloatArray(frameCount)
                if values.contains(where: { !$0.isFinite }) {
                    throw ClipLibraryError.nonFiniteValue(clip: name)
                }
                weights.append(WeightTrack(name: wName, values: values))
            }
            out.append(makeClip(name: name, fps: fps, frameCount: frameCount, tracks: tracks,
                                weights: weights, manifest: manifest, nameToJoint: nameToJoint))
        }
        // Comme le lecteur de référence (Pipeline/pony/runtime_export.py) : aucun octet en trop.
        if !reader.isAtEnd {
            throw ClipLibraryError.trailingBytes(count: reader.remaining)
        }
        return out
    }

    /// Assemble un clip à partir des données binaires et des métadonnées du manifeste (repli : SPEC §7).
    static func makeClip(name: String, fps: Float, frameCount: Int, tracks: [JointTrack], weights: [WeightTrack],
                         manifest: PonyRigManifest, nameToJoint: [String: Int]) -> AnimationClip {
        let meta = manifest.clip(named: name)
        let defaults = PonyRigDefaults.clipDefaults[name]
        let loop = meta?.loop ?? defaults?.loop ?? false
        var duration: Double? = nil
        if let d = meta?.duration, d > 0 {
            duration = Double(d)
        }
        let velocity = meta?.rootVelocity ?? SIMD3<Float>(0, 0, -(defaults?.forwardSpeed ?? 0))
        let yaw = meta?.rootYawRate ?? defaults?.yawRate ?? 0
        var mask: [Int]? = nil
        if let m = meta?.mask {
            mask = m.compactMap { nameToJoint[$0] }
        }
        return AnimationClip(name: name, fps: fps, frameCount: frameCount, duration: duration, loop: loop,
                             tracks: tracks, weightTracks: weights, jointCount: manifest.joints.count,
                             rootVelocity: velocity, rootYawRate: yaw, maskJoints: mask,
                             events: meta?.events ?? [], phaseOffset: meta?.phaseOffset ?? 0,
                             stridesPerClip: meta?.resolvedStridesPerClip ?? 1)
    }

    /// Normalise et rend la suite de quaternions continue (même hémisphère d'une image à l'autre).
    static func continuousNormalized(_ q: [Quat]) -> [Quat] {
        var out = q
        for i in 0..<out.count {
            out[i] = out[i].normalized
            if i > 0 && out[i].dot(out[i - 1]) < 0 {
                out[i] = -out[i]
            }
        }
        return out
    }

    static func isFinite(_ t: JointTrack) -> Bool {
        for v in t.translations where !(v.x.isFinite && v.y.isFinite && v.z.isFinite) { return false }
        for v in t.scales where !(v.x.isFinite && v.y.isFinite && v.z.isFinite) { return false }
        for q in t.rotations where !(q.x.isFinite && q.y.isFinite && q.z.isFinite && q.w.isFinite) { return false }
        return true
    }

    // MARK: Écriture (outil de test / génération)

    /// Encode des clips au format `PonyClips.bin` (version 1). Les canaux de 1 élément sont marqués constants.
    public static func encodeBinary(_ clips: [AnimationClip]) -> Data {
        var bytes: [UInt8] = [0x50, 0x4E, 0x59, 0x43]
        appendU32(&bytes, 1)
        appendU32(&bytes, UInt32(clips.count))
        for clip in clips {
            let nameBytes = Array(clip.name.utf8)
            appendU16(&bytes, UInt16(nameBytes.count))
            bytes += nameBytes
            appendF32(&bytes, clip.fps)
            appendU32(&bytes, UInt32(clip.frameCount))
            appendU16(&bytes, UInt16(clip.tracks.count))
            for t in clip.tracks {
                appendU16(&bytes, UInt16(t.jointIndex))
                var flags: UInt8 = 0
                if !t.translations.isEmpty { flags |= 0x01 }
                if !t.rotations.isEmpty { flags |= 0x02 }
                if !t.scales.isEmpty { flags |= 0x04 }
                if t.translations.count == 1 { flags |= 0x08 }
                if t.rotations.count == 1 { flags |= 0x10 }
                if t.scales.count == 1 { flags |= 0x20 }
                bytes.append(flags)
                for v in t.translations {
                    appendF32(&bytes, v.x)
                    appendF32(&bytes, v.y)
                    appendF32(&bytes, v.z)
                }
                for q in t.rotations {
                    appendF32(&bytes, q.x)
                    appendF32(&bytes, q.y)
                    appendF32(&bytes, q.z)
                    appendF32(&bytes, q.w)
                }
                for v in t.scales {
                    appendF32(&bytes, v.x)
                    appendF32(&bytes, v.y)
                    appendF32(&bytes, v.z)
                }
            }
            appendU16(&bytes, UInt16(clip.weightTracks.count))
            for w in clip.weightTracks {
                let wb = Array(w.name.utf8)
                appendU16(&bytes, UInt16(wb.count))
                bytes += wb
                for i in 0..<clip.frameCount {
                    appendF32(&bytes, i < w.values.count ? w.values[i] : (w.values.last ?? 0))
                }
            }
        }
        return Data(bytes)
    }

    static func appendU16(_ b: inout [UInt8], _ v: UInt16) {
        b.append(UInt8(v & 0xFF))
        b.append(UInt8(v >> 8))
    }

    static func appendU32(_ b: inout [UInt8], _ v: UInt32) {
        b.append(UInt8(v & 0xFF))
        b.append(UInt8((v >> 8) & 0xFF))
        b.append(UInt8((v >> 16) & 0xFF))
        b.append(UInt8(v >> 24))
    }

    static func appendF32(_ b: inout [UInt8], _ v: Float) {
        appendU32(&b, v.bitPattern)
    }
}
