import Foundation

/// Utilitaires mathématiques scalaires et vectoriels de PonyCore.
///
/// Swift pur (bibliothèque standard + Foundation) : aucune dépendance au module `simd` d'Apple,
/// pour compiler aussi sous Linux. Les fonctions vectorielles sont regroupées dans cet espace de noms
/// (et non en extensions de `SIMD3`) pour éviter tout conflit de noms avec d'autres modules.
public enum PonyMath {
    /// Seuil numérique générique.
    public static let epsilon: Float = 1e-6
    /// ln(2), utilisé par les amortissements exprimés en demi-vie.
    public static let ln2: Float = 0.693_147_18
    /// Accélération de la pesanteur (m/s²).
    public static let gravity: Float = 9.81

    // MARK: Scalaires

    public static func clamp(_ value: Float, _ lower: Float, _ upper: Float) -> Float {
        if value < lower { return lower }
        if value > upper { return upper }
        return value
    }

    public static func clamp01(_ value: Float) -> Float {
        return clamp(value, 0, 1)
    }

    public static func lerp(_ a: Float, _ b: Float, _ t: Float) -> Float {
        return a + (b - a) * t
    }

    /// Interpolation d'Hermite cubique entre `edge0` et `edge1` (0 avant, 1 après).
    public static func smoothstep(_ edge0: Float, _ edge1: Float, _ x: Float) -> Float {
        let span = edge1 - edge0
        if abs(span) < epsilon { return x < edge0 ? 0 : 1 }
        let t = clamp01((x - edge0) / span)
        return t * t * (3 - 2 * t)
    }

    /// Rapproche `current` de `target` d'au plus `maxDelta` (≥ 0).
    public static func moveTowards(_ current: Float, _ target: Float, maxDelta: Float) -> Float {
        let delta = target - current
        let step = max(0, maxDelta)
        if abs(delta) <= step { return target }
        return current + (delta > 0 ? step : -step)
    }

    /// Facteur d'amortissement exponentiel **indépendant du pas de temps** :
    /// `1 - 2^(-dt / demiVie)`. Appliquer `x += (cible - x) * facteur` donne le même résultat
    /// qu'on fasse un grand pas ou plusieurs petits pas de même durée totale.
    public static func dampFactor(halfLife: Float, deltaTime: Float) -> Float {
        if deltaTime <= 0 { return 0 }
        let hl = max(halfLife, 1e-5)
        return 1 - exp(-ln2 * deltaTime / hl)
    }

    /// Amortissement exponentiel de `current` vers `target` (cf. `dampFactor`).
    public static func damp(_ current: Float, toward target: Float, halfLife: Float, deltaTime: Float) -> Float {
        return current + (target - current) * dampFactor(halfLife: halfLife, deltaTime: deltaTime)
    }

    /// Ramène un angle (radians) dans ]-π, π].
    public static func wrapAngle(_ angle: Float) -> Float {
        var a = angle
        let twoPi = 2 * Float.pi
        if a > Float.pi || a <= -Float.pi {
            a = a - twoPi * (a / twoPi).rounded(.down)
            if a > Float.pi { a -= twoPi }
        }
        return a
    }

    /// Partie fractionnaire positive : résultat dans [0, 1).
    public static func fract(_ x: Double) -> Double {
        let f = x - x.rounded(.down)
        return f >= 1 ? 0 : f
    }

    public static func radians(_ degrees: Float) -> Float {
        return degrees * Float.pi / 180
    }

    public static func degrees(_ radians: Float) -> Float {
        return radians * 180 / Float.pi
    }

    /// Remplace une valeur non finie (NaN, ±∞) par `fallback`.
    public static func finite(_ value: Float, _ fallback: Float = 0) -> Float {
        return value.isFinite ? value : fallback
    }

    // MARK: Vecteurs (SIMD3<Float> de la bibliothèque standard)

    public static func dot(_ a: SIMD3<Float>, _ b: SIMD3<Float>) -> Float {
        return a.x * b.x + a.y * b.y + a.z * b.z
    }

    public static func cross(_ a: SIMD3<Float>, _ b: SIMD3<Float>) -> SIMD3<Float> {
        let cx = a.y * b.z - a.z * b.y
        let cy = a.z * b.x - a.x * b.z
        let cz = a.x * b.y - a.y * b.x
        return SIMD3<Float>(cx, cy, cz)
    }

    public static func lengthSquared(_ v: SIMD3<Float>) -> Float {
        return dot(v, v)
    }

    public static func length(_ v: SIMD3<Float>) -> Float {
        return dot(v, v).squareRoot()
    }

    public static func distance(_ a: SIMD3<Float>, _ b: SIMD3<Float>) -> Float {
        return length(a - b)
    }

    /// Vecteur normalisé, ou `fallback` si la longueur est quasi nulle.
    public static func normalize(_ v: SIMD3<Float>,
                                 fallback: SIMD3<Float> = SIMD3<Float>(0, 1, 0)) -> SIMD3<Float> {
        let len = length(v)
        if len < 1e-9 || !len.isFinite { return fallback }
        return v / len
    }

    public static func lerp(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ t: Float) -> SIMD3<Float> {
        return a + (b - a) * t
    }

    /// Angle non signé (radians) entre deux vecteurs non nuls.
    public static func angle(between a: SIMD3<Float>, _ b: SIMD3<Float>) -> Float {
        let na = normalize(a)
        let nb = normalize(b)
        return acos(clamp(dot(na, nb), -1, 1))
    }

    /// Composante de `v` orthogonale à l'axe unitaire `axis`.
    public static func rejection(_ v: SIMD3<Float>, from axis: SIMD3<Float>) -> SIMD3<Float> {
        return v - axis * dot(v, axis)
    }
}

/// Ressort **critiquement amorti** intégré analytiquement (inconditionnellement stable, indépendant du dt).
///
/// Formulation « demi-vie » : après `halfLife` secondes, l'écart à la cible a été divisé par deux environ
/// (aux effets de vitesse près). Référence de la forme fermée : D. Holden, « Spring-It-On » (2021) [I].
public struct CriticalSpring: Sendable, Equatable {
    public var value: Float
    public var velocity: Float

    public init(value: Float = 0, velocity: Float = 0) {
        self.value = value
        self.velocity = velocity
    }

    public mutating func update(target: Float, halfLife: Float, deltaTime: Float) {
        if deltaTime <= 0 { return }
        let y: Float = 2 * PonyMath.ln2 / max(halfLife, 1e-5)
        let j0: Float = value - target
        let j1: Float = velocity + j0 * y
        let eydt: Float = exp(-y * deltaTime)
        value = eydt * (j0 + j1 * deltaTime) + target
        velocity = eydt * (velocity - j1 * y * deltaTime)
    }

    public mutating func reset(to value: Float) {
        self.value = value
        velocity = 0
    }
}

/// Générateur pseudo-aléatoire **déterministe** (SplitMix64) : même graine ⇒ même suite, sur toutes plateformes.
public struct PonyRandom: Sendable, Equatable {
    public private(set) var state: UInt64

    public init(seed: UInt64) {
        state = seed
    }

    public mutating func next() -> UInt64 {
        state = state &+ 0x9E37_79B9_7F4A_7C15
        var z = state
        z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
        z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
        return z ^ (z >> 31)
    }

    /// Flottant uniforme dans [0, 1).
    public mutating func nextFloat() -> Float {
        let bits = next() >> 40                 // 24 bits de mantisse
        return Float(bits) / Float(16_777_216)
    }

    /// Flottant uniforme dans [lower, upper).
    public mutating func range(_ lower: Float, _ upper: Float) -> Float {
        return lower + (upper - lower) * nextFloat()
    }

    /// Vrai avec la probabilité `probability`.
    public mutating func chance(_ probability: Float) -> Bool {
        return nextFloat() < probability
    }

    /// Graine dérivée (sous-générateur indépendant) pour un usage nommé.
    public mutating func derive() -> PonyRandom {
        return PonyRandom(seed: next())
    }
}
