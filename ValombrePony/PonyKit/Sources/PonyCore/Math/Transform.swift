import Foundation

/// Transformation TRS (translation, rotation, échelle) : p' = translation + rotation · (échelle ⊙ p).
///
/// C'est la représentation des poses locales de joints (comme `RealityKit.Transform`).
/// Sérialisation JSON : `{ "t": [x,y,z], "r": [x,y,z,w], "s": [x,y,z] }` (format `rest` de `PonyRig.json`).
public struct Transform: Codable, Equatable, Sendable {
    public var translation: SIMD3<Float>
    public var rotation: Quat
    public var scale: SIMD3<Float>

    public init(translation: SIMD3<Float> = SIMD3<Float>(0, 0, 0),
                rotation: Quat = .identity,
                scale: SIMD3<Float> = SIMD3<Float>(1, 1, 1)) {
        self.translation = translation
        self.rotation = rotation
        self.scale = scale
    }

    public static let identity = Transform()

    // MARK: Composition

    /// Composition parent · enfant : la transformation de l'enfant exprimée dans l'espace du parent.
    /// (Échelle non uniforme + rotation : approximation TRS habituelle des moteurs, sans cisaillement.)
    public static func * (parent: Transform, child: Transform) -> Transform {
        let t = parent.translation + parent.rotation.act(parent.scale * child.translation)
        let r = parent.rotation * child.rotation
        let s = parent.scale * child.scale
        return Transform(translation: t, rotation: r, scale: s)
    }

    /// Applique la transformation à un point.
    public func transformPoint(_ p: SIMD3<Float>) -> SIMD3<Float> {
        return translation + rotation.act(scale * p)
    }

    /// Applique rotation et échelle (sans translation) à un vecteur.
    public func transformVector(_ v: SIMD3<Float>) -> SIMD3<Float> {
        return rotation.act(scale * v)
    }

    /// Inverse. Exact pour une échelle uniforme ; approximation TRS sinon.
    public var inverse: Transform {
        let invScale = SIMD3<Float>(Transform.safeInverse(scale.x),
                                    Transform.safeInverse(scale.y),
                                    Transform.safeInverse(scale.z))
        let invRot = rotation.inverse
        let t = invScale * invRot.act(-translation)
        return Transform(translation: t, rotation: invRot, scale: invScale)
    }

    /// Point exprimé dans l'espace local de cette transformation (inverse de `transformPoint`).
    public func inverseTransformPoint(_ p: SIMD3<Float>) -> SIMD3<Float> {
        let local = rotation.inverse.act(p - translation)
        return SIMD3<Float>(local.x * Transform.safeInverse(scale.x),
                            local.y * Transform.safeInverse(scale.y),
                            local.z * Transform.safeInverse(scale.z))
    }

    private static func safeInverse(_ v: Float) -> Float {
        if abs(v) < 1e-12 { return 0 }
        return 1 / v
    }

    // MARK: Interpolation

    /// Interpolation : lerp des translations et échelles, slerp des rotations.
    public static func interpolate(_ a: Transform, _ b: Transform, _ t: Float) -> Transform {
        return Transform(translation: PonyMath.lerp(a.translation, b.translation, t),
                         rotation: Quat.slerp(a.rotation, b.rotation, t),
                         scale: PonyMath.lerp(a.scale, b.scale, t))
    }

    // MARK: Matrices 4×4 (colonnes majeures, comme `bindModel` de PonyRig.json)

    /// Décompose une matrice 4×4 en colonnes majeures (16 flottants) en TRS (sans cisaillement).
    /// Un tableau de taille incorrecte donne l'identité.
    public init(columnMajor m: [Float]) {
        if m.count < 16 {
            self.init()
            return
        }
        let c0 = SIMD3<Float>(m[0], m[1], m[2])
        let c1 = SIMD3<Float>(m[4], m[5], m[6])
        let c2 = SIMD3<Float>(m[8], m[9], m[10])
        var sx = PonyMath.length(c0)
        let sy = PonyMath.length(c1)
        let sz = PonyMath.length(c2)
        let det = PonyMath.dot(c0, PonyMath.cross(c1, c2))
        if det < 0 { sx = -sx }
        let r0 = sx != 0 ? c0 / sx : SIMD3<Float>(1, 0, 0)
        let r1 = sy != 0 ? c1 / sy : SIMD3<Float>(0, 1, 0)
        let r2 = sz != 0 ? c2 / sz : SIMD3<Float>(0, 0, 1)
        self.init(translation: SIMD3<Float>(m[12], m[13], m[14]),
                  rotation: Quat(rotationColumns: r0, r1, r2),
                  scale: SIMD3<Float>(sx, sy, sz))
    }

    /// Matrice 4×4 en colonnes majeures (16 flottants).
    public var columnMajor: [Float] {
        let q = rotation.normalized
        let xx = q.x * q.x, yy = q.y * q.y, zz = q.z * q.z
        let xy = q.x * q.y, xz = q.x * q.z, yz = q.y * q.z
        let wx = q.w * q.x, wy = q.w * q.y, wz = q.w * q.z
        let r00: Float = 1 - 2 * (yy + zz)
        let r01: Float = 2 * (xy - wz)
        let r02: Float = 2 * (xz + wy)
        let r10: Float = 2 * (xy + wz)
        let r11: Float = 1 - 2 * (xx + zz)
        let r12: Float = 2 * (yz - wx)
        let r20: Float = 2 * (xz - wy)
        let r21: Float = 2 * (yz + wx)
        let r22: Float = 1 - 2 * (xx + yy)
        return [r00 * scale.x, r10 * scale.x, r20 * scale.x, 0,
                r01 * scale.y, r11 * scale.y, r21 * scale.y, 0,
                r02 * scale.z, r12 * scale.z, r22 * scale.z, 0,
                translation.x, translation.y, translation.z, 1]
    }

    // MARK: Comparaison tolérante

    public func isApproximatelyEqual(to other: Transform, tolerance: Float = 1e-4) -> Bool {
        let dt = PonyMath.length(translation - other.translation)
        let ds = PonyMath.length(scale - other.scale)
        return dt <= tolerance && ds <= tolerance
            && rotation.isApproximatelyEqual(to: other.rotation, tolerance: tolerance)
    }

    // MARK: Codable — clés t / r / s, champs facultatifs

    private enum CodingKeys: String, CodingKey {
        case t, r, s
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let t = try c.decodeIfPresent(SIMD3<Float>.self, forKey: .t) ?? SIMD3<Float>(0, 0, 0)
        let r = try c.decodeIfPresent(Quat.self, forKey: .r) ?? .identity
        let s = try c.decodeIfPresent(SIMD3<Float>.self, forKey: .s) ?? SIMD3<Float>(1, 1, 1)
        self.init(translation: t, rotation: r, scale: s)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(translation, forKey: .t)
        try c.encode(rotation, forKey: .r)
        try c.encode(scale, forKey: .s)
    }
}
