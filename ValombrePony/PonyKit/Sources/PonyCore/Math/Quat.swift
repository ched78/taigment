import Foundation

/// Quaternion de rotation (x, y, z, w) — convention de Hamilton, rotation **active** : v' = q · v · q*.
///
/// - Composition : `a * b` applique d'abord `b` puis `a` (comme les matrices colonnes).
/// - Sérialisation JSON : tableau `[x, y, z, w]` (format de `PonyRig.json`, SPEC §9).
public struct Quat: Codable, Equatable, Hashable, Sendable {
    public var x: Float
    public var y: Float
    public var z: Float
    public var w: Float

    public init(x: Float, y: Float, z: Float, w: Float) {
        self.x = x
        self.y = y
        self.z = z
        self.w = w
    }

    public init(vector v: SIMD4<Float>) {
        x = v.x
        y = v.y
        z = v.z
        w = v.w
    }

    public static let identity = Quat(x: 0, y: 0, z: 0, w: 1)

    /// Rotation d'angle `angle` (radians, sens direct) autour de `axis` (normalisé ici).
    /// Un axe nul donne l'identité.
    public init(axis: SIMD3<Float>, angle: Float) {
        let len = PonyMath.length(axis)
        var qx: Float = 0
        var qy: Float = 0
        var qz: Float = 0
        var qw: Float = 1
        if len > 1e-9 && angle.isFinite {
            let half = angle * 0.5
            let s = sin(half) / len
            qx = axis.x * s
            qy = axis.y * s
            qz = axis.z * s
            qw = cos(half)
        }
        x = qx
        y = qy
        z = qz
        w = qw
    }

    /// Plus petite rotation qui amène la direction `from` sur la direction `to`.
    /// Directions opposées : demi-tour autour d'un axe orthogonal quelconque.
    public init(from: SIMD3<Float>, to: SIMD3<Float>) {
        let a = PonyMath.normalize(from)
        let b = PonyMath.normalize(to)
        let d = PonyMath.dot(a, b)
        var qx: Float = 0
        var qy: Float = 0
        var qz: Float = 0
        var qw: Float = 1
        if d < -1 + 1e-6 {
            var axis = PonyMath.cross(SIMD3<Float>(1, 0, 0), a)
            if PonyMath.lengthSquared(axis) < 1e-8 {
                axis = PonyMath.cross(SIMD3<Float>(0, 1, 0), a)
            }
            axis = PonyMath.normalize(axis)
            qx = axis.x
            qy = axis.y
            qz = axis.z
            qw = 0
        } else if d < 1 - 1e-7 {
            let c = PonyMath.cross(a, b)
            let s = ((1 + d) * 2).squareRoot()
            let inv = 1 / s
            qx = c.x * inv
            qy = c.y * inv
            qz = c.z * inv
            qw = s * 0.5
        }
        let n = (qx * qx + qy * qy + qz * qz + qw * qw).squareRoot()
        x = qx / n
        y = qy / n
        z = qz / n
        w = qw / n
    }

    /// Quaternion d'une matrice de rotation donnée par ses trois colonnes (orthonormées).
    public init(rotationColumns c0: SIMD3<Float>, _ c1: SIMD3<Float>, _ c2: SIMD3<Float>) {
        // R[ligne][colonne] : colonne 0 = c0, etc.
        let r00 = c0.x, r10 = c0.y, r20 = c0.z
        let r01 = c1.x, r11 = c1.y, r21 = c1.z
        let r02 = c2.x, r12 = c2.y, r22 = c2.z
        let trace = r00 + r11 + r22
        var qx: Float
        var qy: Float
        var qz: Float
        var qw: Float
        if trace > 0 {
            let s = (trace + 1).squareRoot() * 2
            qw = 0.25 * s
            qx = (r21 - r12) / s
            qy = (r02 - r20) / s
            qz = (r10 - r01) / s
        } else if r00 > r11 && r00 > r22 {
            let s = (1 + r00 - r11 - r22).squareRoot() * 2
            qw = (r21 - r12) / s
            qx = 0.25 * s
            qy = (r01 + r10) / s
            qz = (r02 + r20) / s
        } else if r11 > r22 {
            let s = (1 + r11 - r00 - r22).squareRoot() * 2
            qw = (r02 - r20) / s
            qx = (r01 + r10) / s
            qy = 0.25 * s
            qz = (r12 + r21) / s
        } else {
            let s = (1 + r22 - r00 - r11).squareRoot() * 2
            qw = (r10 - r01) / s
            qx = (r02 + r20) / s
            qy = (r12 + r21) / s
            qz = 0.25 * s
        }
        let n = (qx * qx + qy * qy + qz * qz + qw * qw).squareRoot()
        if n > 1e-12 {
            qx /= n
            qy /= n
            qz /= n
            qw /= n
        } else {
            qx = 0
            qy = 0
            qz = 0
            qw = 1
        }
        x = qx
        y = qy
        z = qz
        w = qw
    }

    // MARK: Accès

    public var vector: SIMD4<Float> {
        return SIMD4<Float>(x, y, z, w)
    }

    /// Partie imaginaire (x, y, z).
    public var imaginary: SIMD3<Float> {
        return SIMD3<Float>(x, y, z)
    }

    public var lengthSquared: Float {
        return x * x + y * y + z * z + w * w
    }

    public var length: Float {
        return lengthSquared.squareRoot()
    }

    /// Quaternion unitaire (l'identité si la norme est nulle ou non finie).
    public var normalized: Quat {
        let n = length
        if n < 1e-12 || !n.isFinite { return .identity }
        let inv = 1 / n
        return Quat(x: x * inv, y: y * inv, z: z * inv, w: w * inv)
    }

    public var conjugate: Quat {
        return Quat(x: -x, y: -y, z: -z, w: w)
    }

    /// Inverse multiplicatif (égal au conjugué pour un quaternion unitaire).
    public var inverse: Quat {
        let n2 = lengthSquared
        if n2 < 1e-20 { return .identity }
        let inv = 1 / n2
        return Quat(x: -x * inv, y: -y * inv, z: -z * inv, w: w * inv)
    }

    public func dot(_ other: Quat) -> Float {
        return x * other.x + y * other.y + z * other.z + w * other.w
    }

    /// Angle de rotation dans [0, π] (le plus court).
    public var angle: Float {
        let n = normalized
        return 2 * acos(PonyMath.clamp(abs(n.w), 0, 1))
    }

    /// Axe de rotation unitaire (arbitraire, +X, si l'angle est nul), pris dans l'hémisphère w ≥ 0.
    public var axis: SIMD3<Float> {
        let n = normalized
        let sign: Float = n.w < 0 ? -1 : 1
        let v = SIMD3<Float>(n.x, n.y, n.z) * sign
        return PonyMath.normalize(v, fallback: SIMD3<Float>(1, 0, 0))
    }

    // MARK: Opérateurs

    public static func * (a: Quat, b: Quat) -> Quat {
        let rx: Float = a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y
        let ry: Float = a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x
        let rz: Float = a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w
        let rw: Float = a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z
        return Quat(x: rx, y: ry, z: rz, w: rw)
    }

    public static prefix func - (q: Quat) -> Quat {
        return Quat(x: -q.x, y: -q.y, z: -q.z, w: -q.w)
    }

    /// Applique la rotation au vecteur `v` (suppose un quaternion unitaire).
    public func act(_ v: SIMD3<Float>) -> SIMD3<Float> {
        let u = SIMD3<Float>(x, y, z)
        let t = PonyMath.cross(u, v) * 2
        let wt = t * w
        return v + wt + PonyMath.cross(u, t)
    }

    // MARK: Interpolation

    /// Interpolation linéaire normalisée, avec choix de l'hémisphère (chemin le plus court).
    public static func nlerp(_ a: Quat, _ b: Quat, _ t: Float) -> Quat {
        let sign: Float = a.dot(b) < 0 ? -1 : 1
        let s0 = 1 - t
        let s1 = t * sign
        let q = Quat(x: a.x * s0 + b.x * s1,
                     y: a.y * s0 + b.y * s1,
                     z: a.z * s0 + b.z * s1,
                     w: a.w * s0 + b.w * s1)
        return q.normalized
    }

    /// Interpolation sphérique à vitesse angulaire constante, avec choix de l'hémisphère.
    public static func slerp(_ a: Quat, _ b: Quat, _ t: Float) -> Quat {
        var bb = b
        var d = a.dot(b)
        if d < 0 {
            bb = -b
            d = -d
        }
        if d > 0.9995 {
            return nlerp(a, bb, t)
        }
        let theta0 = acos(PonyMath.clamp(d, -1, 1))
        let theta = theta0 * t
        let sinTheta0 = sin(theta0)
        let s0 = sin(theta0 - theta) / sinTheta0
        let s1 = sin(theta) / sinTheta0
        let q = Quat(x: a.x * s0 + bb.x * s1,
                     y: a.y * s0 + bb.y * s1,
                     z: a.z * s0 + bb.z * s1,
                     w: a.w * s0 + bb.w * s1)
        return q.normalized
    }

    // MARK: Outils

    /// Vrai si les deux quaternions représentent la même rotation (q et -q confondus).
    public func isApproximatelyEqual(to other: Quat, tolerance: Float = 1e-4) -> Bool {
        return abs(abs(normalized.dot(other.normalized)) - 1) <= tolerance
    }

    /// Même rotation limitée à un angle maximal `maxAngle` (radians, ≥ 0).
    public func clampedAngle(_ maxAngle: Float) -> Quat {
        let a = angle
        if a <= maxAngle || a < 1e-7 { return self }
        return Quat(axis: axis, angle: max(0, maxAngle))
    }

    /// Fraction `t` de cette rotation (0 = identité, 1 = elle-même).
    public func scaled(_ t: Float) -> Quat {
        return Quat.slerp(.identity, self, t)
    }

    /// Composante de torsion autour de `twistAxis` (décomposition swing-twist).
    public func twist(around twistAxis: SIMD3<Float>) -> Quat {
        let axisN = PonyMath.normalize(twistAxis)
        let p = axisN * PonyMath.dot(imaginary, axisN)
        let q = Quat(x: p.x, y: p.y, z: p.z, w: w)
        if q.lengthSquared < 1e-12 { return .identity }
        return q.normalized
    }

    // MARK: Codable — tableau [x, y, z, w]

    public init(from decoder: Decoder) throws {
        var c = try decoder.unkeyedContainer()
        let qx = try c.decode(Float.self)
        let qy = try c.decode(Float.self)
        let qz = try c.decode(Float.self)
        let qw = try c.decode(Float.self)
        x = qx
        y = qy
        z = qz
        w = qw
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.unkeyedContainer()
        try c.encode(x)
        try c.encode(y)
        try c.encode(z)
        try c.encode(w)
    }
}
