import Foundation

/// Erreurs typées de lecture de `PonyClips.bin`.
public enum ClipLibraryError: Error, Equatable, CustomStringConvertible, Sendable {
    /// Les 4 premiers octets ne valent pas « PNYC ».
    case badMagic
    case unsupportedVersion(UInt32)
    /// Fin de fichier prématurée : `needed` octets demandés à l'offset `offset`.
    case truncated(offset: Int, needed: Int)
    case invalidUTF8(offset: Int)
    case invalidJointIndex(clip: String, jointIndex: Int, jointCount: Int)
    case invalidFrameCount(clip: String, frameCount: Int)
    case invalidFrameRate(clip: String, fps: Float)
    case nonFiniteValue(clip: String)
    case tooLarge(field: String, value: Int)

    public var description: String {
        switch self {
        case .badMagic:
            return "PonyClips.bin : signature « PNYC » absente"
        case .unsupportedVersion(let v):
            return "PonyClips.bin : version \(v) non prise en charge"
        case .truncated(let offset, let needed):
            return "PonyClips.bin tronqué : \(needed) octet(s) attendus à l'offset \(offset)"
        case .invalidUTF8(let offset):
            return "PonyClips.bin : nom UTF-8 invalide à l'offset \(offset)"
        case .invalidJointIndex(let clip, let index, let count):
            return "Clip \(clip) : indice de joint \(index) hors limites (\(count) joints)"
        case .invalidFrameCount(let clip, let n):
            return "Clip \(clip) : nombre d'images invalide (\(n))"
        case .invalidFrameRate(let clip, let fps):
            return "Clip \(clip) : cadence invalide (\(fps))"
        case .nonFiniteValue(let clip):
            return "Clip \(clip) : valeur non finie (NaN/inf)"
        case .tooLarge(let field, let value):
            return "PonyClips.bin : \(field) = \(value) dépasse la limite de sécurité"
        }
    }
}

/// Lecteur binaire petit-boutiste **borné** : toute lecture vérifie la taille restante avant d'accéder
/// aux octets (aucune lecture hors limites, aucune allocation démesurée sur fichier corrompu).
struct PonyBinaryReader {
    let bytes: [UInt8]
    private(set) var offset: Int = 0

    init(data: Data) {
        bytes = [UInt8](data)
    }

    init(bytes: [UInt8]) {
        self.bytes = bytes
    }

    var remaining: Int {
        return bytes.count - offset
    }

    var isAtEnd: Bool {
        return offset >= bytes.count
    }

    mutating func require(_ count: Int) throws {
        if count < 0 || remaining < count {
            throw ClipLibraryError.truncated(offset: offset, needed: count)
        }
    }

    mutating func readU8() throws -> UInt8 {
        try require(1)
        let v = bytes[offset]
        offset += 1
        return v
    }

    mutating func readU16() throws -> UInt16 {
        try require(2)
        let b0 = UInt16(bytes[offset])
        let b1 = UInt16(bytes[offset + 1])
        offset += 2
        return b0 | (b1 << 8)
    }

    mutating func readU32() throws -> UInt32 {
        try require(4)
        let b0 = UInt32(bytes[offset])
        let b1 = UInt32(bytes[offset + 1])
        let b2 = UInt32(bytes[offset + 2])
        let b3 = UInt32(bytes[offset + 3])
        offset += 4
        return b0 | (b1 << 8) | (b2 << 16) | (b3 << 24)
    }

    mutating func readF32() throws -> Float {
        return Float(bitPattern: try readU32())
    }

    mutating func readBytes(_ count: Int) throws -> [UInt8] {
        try require(count)
        let out = Array(bytes[offset..<(offset + count)])
        offset += count
        return out
    }

    /// Chaîne UTF-8 de longueur `count` octets.
    mutating func readString(byteCount count: Int) throws -> String {
        let start = offset
        let raw = try readBytes(count)
        guard let s = String(bytes: raw, encoding: .utf8) else {
            throw ClipLibraryError.invalidUTF8(offset: start)
        }
        return s
    }

    /// `count` vecteurs de 3 flottants.
    mutating func readVec3Array(_ count: Int) throws -> [SIMD3<Float>] {
        try require(count * 12)
        var out = [SIMD3<Float>]()
        out.reserveCapacity(count)
        for _ in 0..<count {
            let x = try readF32()
            let y = try readF32()
            let z = try readF32()
            out.append(SIMD3<Float>(x, y, z))
        }
        return out
    }

    /// `count` quaternions (x, y, z, w).
    mutating func readQuatArray(_ count: Int) throws -> [Quat] {
        try require(count * 16)
        var out = [Quat]()
        out.reserveCapacity(count)
        for _ in 0..<count {
            let x = try readF32()
            let y = try readF32()
            let z = try readF32()
            let w = try readF32()
            out.append(Quat(x: x, y: y, z: z, w: w))
        }
        return out
    }

    mutating func readFloatArray(_ count: Int) throws -> [Float] {
        try require(count * 4)
        var out = [Float]()
        out.reserveCapacity(count)
        for _ in 0..<count {
            out.append(try readF32())
        }
        return out
    }
}
