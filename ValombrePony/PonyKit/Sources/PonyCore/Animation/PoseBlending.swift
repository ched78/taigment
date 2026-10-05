import Foundation

/// Accumulateur de mélange pondéré de N poses (préalloué, sans allocation par frame).
///
/// Translations et échelles : moyenne pondérée. Rotations : somme pondérée de quaternions alignés sur le
/// même hémisphère puis normalisée (moyenne « nlerp » N-aire, exacte pour 2 poses à l'échelle de vitesse près).
/// Les poids par joint permettent les couches masquées.
public struct PoseAccumulator: Sendable {
    public private(set) var translations: [SIMD3<Float>]
    public private(set) var rotations: [SIMD4<Float>]
    public private(set) var scales: [SIMD3<Float>]
    public private(set) var weights: [Float]

    public init(jointCount: Int) {
        translations = [SIMD3<Float>](repeating: SIMD3<Float>(0, 0, 0), count: jointCount)
        rotations = [SIMD4<Float>](repeating: SIMD4<Float>(0, 0, 0, 0), count: jointCount)
        scales = [SIMD3<Float>](repeating: SIMD3<Float>(0, 0, 0), count: jointCount)
        weights = [Float](repeating: 0, count: jointCount)
    }

    public var count: Int {
        return weights.count
    }

    public mutating func reset() {
        for i in 0..<weights.count {
            translations[i] = SIMD3<Float>(0, 0, 0)
            rotations[i] = SIMD4<Float>(0, 0, 0, 0)
            scales[i] = SIMD3<Float>(0, 0, 0)
            weights[i] = 0
        }
    }

    /// Ajoute toute la pose avec le poids `weight`.
    public mutating func add(_ pose: [Transform], weight: Float) {
        if weight <= 0 { return }
        let n = min(pose.count, weights.count)
        for j in 0..<n {
            addJoint(j, pose[j], weight)
        }
    }

    /// Ajoute la pose avec un poids par joint (`mask[j] * weight`).
    public mutating func add(_ pose: [Transform], weight: Float, mask: [Float]) {
        if weight <= 0 { return }
        let n = min(pose.count, min(weights.count, mask.count))
        for j in 0..<n {
            let w = mask[j] * weight
            if w > 0 { addJoint(j, pose[j], w) }
        }
    }

    public mutating func addJoint(_ j: Int, _ t: Transform, _ w: Float) {
        translations[j] += t.translation * w
        scales[j] += t.scale * w
        var q = t.rotation.vector
        let acc = rotations[j]
        let d = acc.x * q.x + acc.y * q.y + acc.z * q.z + acc.w * q.w
        if d < 0 { q = -q }
        rotations[j] += q * w
        weights[j] += w
    }

    /// Écrit la pose moyenne dans `pose`. Les joints de poids nul reçoivent `fallback[j]`.
    public func resolve(into pose: inout [Transform], fallback: [Transform]) {
        let n = min(pose.count, weights.count)
        for j in 0..<n {
            let w = weights[j]
            if w <= 1e-8 {
                if j < fallback.count { pose[j] = fallback[j] }
                continue
            }
            let inv = 1 / w
            let r = rotations[j]
            let len = (r.x * r.x + r.y * r.y + r.z * r.z + r.w * r.w).squareRoot()
            var q = Quat.identity
            if len > 1e-9 {
                q = Quat(x: r.x / len, y: r.y / len, z: r.z / len, w: r.w / len)
            } else if j < fallback.count {
                q = fallback[j].rotation
            }
            pose[j] = Transform(translation: translations[j] * inv, rotation: q, scale: scales[j] * inv)
        }
    }

    /// Mélange une couche par-dessus une pose de base, joint par joint : base = lerp(base, couche, w·masque).
    /// Les joints de masque nul gardent la base (pose de la couche inférieure).
    public static func blendLayer(base: inout [Transform], layer: [Transform], weight: Float, mask: [Float]) {
        if weight <= 0 { return }
        let n = min(base.count, min(layer.count, mask.count))
        for j in 0..<n {
            let w = PonyMath.clamp01(mask[j] * weight)
            if w <= 0 { continue }
            if w >= 1 {
                base[j] = layer[j]
            } else {
                base[j] = Transform(translation: PonyMath.lerp(base[j].translation, layer[j].translation, w),
                                    rotation: Quat.nlerp(base[j].rotation, layer[j].rotation, w),
                                    scale: PonyMath.lerp(base[j].scale, layer[j].scale, w))
            }
        }
    }

    /// Mélange de deux poses complètes (fondu enchaîné) : out = lerp(a, b, t).
    public static func blend(_ a: [Transform], _ b: [Transform], _ t: Float, into out: inout [Transform]) {
        let n = min(out.count, min(a.count, b.count))
        for j in 0..<n {
            out[j] = Transform(translation: PonyMath.lerp(a[j].translation, b[j].translation, t),
                               rotation: Quat.nlerp(a[j].rotation, b[j].rotation, t),
                               scale: PonyMath.lerp(a[j].scale, b[j].scale, t))
        }
    }
}

/// Accumulateur de poids de blend shapes indexés (préalloué).
public struct ShapeAccumulator: Sendable {
    public private(set) var sums: [Float]
    public private(set) var totalWeight: Float = 0

    public init(count: Int) {
        sums = [Float](repeating: 0, count: count)
    }

    public mutating func reset() {
        for i in 0..<sums.count {
            sums[i] = 0
        }
        totalWeight = 0
    }

    /// Déclare qu'une source de poids `weight` a contribué (même si elle n'a pas de piste pour une forme).
    public mutating func addSource(weight: Float) {
        totalWeight += max(0, weight)
    }

    public mutating func add(index: Int, value: Float, weight: Float) {
        if index < 0 || index >= sums.count || weight <= 0 { return }
        sums[index] += value * weight
    }

    /// Valeur moyenne de la forme `index` (0 sans source).
    public func value(_ index: Int) -> Float {
        if totalWeight <= 1e-8 || index < 0 || index >= sums.count { return 0 }
        return sums[index] / totalWeight
    }
}
