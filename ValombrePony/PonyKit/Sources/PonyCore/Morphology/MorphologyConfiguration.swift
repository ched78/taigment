import Foundation

/// Curseurs de morphologie (SPEC §5). Tous les champs sont bornés à l'évaluation (valeurs hors bornes tolérées
/// dans la sauvegarde, jamais propagées aux blend shapes).
///
/// - Curseurs bipolaires −1…+1 : `legLength`, `neckLength`, `bodyLength`, `condition` (−1 maigre … +1 gras),
///   `headShape` (−1 busqué … +1 concave/camus).
/// - Curseurs 0…1 : `stocky`, `refined`, `muscle`, `belly`, `crest`, `bone`, `headShort`, `muzzleBroad`,
///   `hoofSize`, et le composite `shetland`.
/// - Échelles multiplicatives (1 = gabarit) : `headScale` 0,85…1,2 ; `earScale` 0,7…1,3 ; `eyeScale` 0,85…1,2.
public struct MorphologyConfiguration: Codable, Equatable, Sendable {
    public var legLength: Float
    public var neckLength: Float
    public var bodyLength: Float
    public var stocky: Float
    public var refined: Float
    public var condition: Float
    public var muscle: Float
    public var belly: Float
    public var crest: Float
    public var bone: Float
    public var headShape: Float
    public var headShort: Float
    public var muzzleBroad: Float
    public var hoofSize: Float
    public var headScale: Float
    public var earScale: Float
    public var eyeScale: Float
    /// Curseur composite « type Shetland » (0…1) : jambes et encolure plus courtes, tronc trapu, museau large,
    /// petites oreilles, os et sabots forts [A pour les coefficients].
    public var shetland: Float

    public init(legLength: Float = 0, neckLength: Float = 0, bodyLength: Float = 0, stocky: Float = 0,
                refined: Float = 0, condition: Float = 0, muscle: Float = 0, belly: Float = 0, crest: Float = 0,
                bone: Float = 0, headShape: Float = 0, headShort: Float = 0, muzzleBroad: Float = 0,
                hoofSize: Float = 0, headScale: Float = 1, earScale: Float = 1, eyeScale: Float = 1,
                shetland: Float = 0) {
        self.legLength = legLength
        self.neckLength = neckLength
        self.bodyLength = bodyLength
        self.stocky = stocky
        self.refined = refined
        self.condition = condition
        self.muscle = muscle
        self.belly = belly
        self.crest = crest
        self.bone = bone
        self.headShape = headShape
        self.headShort = headShort
        self.muzzleBroad = muzzleBroad
        self.hoofSize = hoofSize
        self.headScale = headScale
        self.earScale = earScale
        self.eyeScale = eyeScale
        self.shetland = shetland
    }

    /// Gabarit neutre (Welsh B / Connemara générique du SPEC §0).
    public static let `default` = MorphologyConfiguration()

    // Bornes publiques (pour l'interface).
    public static let bipolarRange: ClosedRange<Float> = -1...1
    public static let unitRange: ClosedRange<Float> = 0...1
    public static let headScaleRange: ClosedRange<Float> = 0.85...1.2
    public static let earScaleRange: ClosedRange<Float> = 0.7...1.3
    public static let eyeScaleRange: ClosedRange<Float> = 0.85...1.2

    /// Copie dont chaque curseur est ramené dans ses bornes (valeurs non finies → neutre).
    public var clamped: MorphologyConfiguration {
        func c(_ v: Float, _ r: ClosedRange<Float>, _ neutral: Float) -> Float {
            if !v.isFinite { return neutral }
            return PonyMath.clamp(v, r.lowerBound, r.upperBound)
        }
        let b = MorphologyConfiguration.bipolarRange
        let u = MorphologyConfiguration.unitRange
        return MorphologyConfiguration(
            legLength: c(legLength, b, 0), neckLength: c(neckLength, b, 0), bodyLength: c(bodyLength, b, 0),
            stocky: c(stocky, u, 0), refined: c(refined, u, 0), condition: c(condition, b, 0),
            muscle: c(muscle, u, 0), belly: c(belly, u, 0), crest: c(crest, u, 0), bone: c(bone, u, 0),
            headShape: c(headShape, b, 0), headShort: c(headShort, u, 0), muzzleBroad: c(muzzleBroad, u, 0),
            hoofSize: c(hoofSize, u, 0),
            headScale: c(headScale, MorphologyConfiguration.headScaleRange, 1),
            earScale: c(earScale, MorphologyConfiguration.earScaleRange, 1),
            eyeScale: c(eyeScale, MorphologyConfiguration.eyeScaleRange, 1),
            shetland: c(shetland, u, 0))
    }

    // MARK: Codable tolérant (champs absents → neutre)

    private enum CodingKeys: String, CodingKey {
        case legLength, neckLength, bodyLength, stocky, refined, condition, muscle, belly, crest, bone
        case headShape, headShort, muzzleBroad, hoofSize, headScale, earScale, eyeScale, shetland
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        func f(_ k: CodingKeys, _ d: Float) -> Float {
            return (try? c.decodeIfPresent(Float.self, forKey: k)) ?? d
        }
        self.init(legLength: f(.legLength, 0), neckLength: f(.neckLength, 0), bodyLength: f(.bodyLength, 0),
                  stocky: f(.stocky, 0), refined: f(.refined, 0), condition: f(.condition, 0),
                  muscle: f(.muscle, 0), belly: f(.belly, 0), crest: f(.crest, 0), bone: f(.bone, 0),
                  headShape: f(.headShape, 0), headShort: f(.headShort, 0), muzzleBroad: f(.muzzleBroad, 0),
                  hoofSize: f(.hoofSize, 0), headScale: f(.headScale, 1), earScale: f(.earScale, 1),
                  eyeScale: f(.eyeScale, 1), shetland: f(.shetland, 0))
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(legLength, forKey: .legLength)
        try c.encode(neckLength, forKey: .neckLength)
        try c.encode(bodyLength, forKey: .bodyLength)
        try c.encode(stocky, forKey: .stocky)
        try c.encode(refined, forKey: .refined)
        try c.encode(condition, forKey: .condition)
        try c.encode(muscle, forKey: .muscle)
        try c.encode(belly, forKey: .belly)
        try c.encode(crest, forKey: .crest)
        try c.encode(bone, forKey: .bone)
        try c.encode(headShape, forKey: .headShape)
        try c.encode(headShort, forKey: .headShort)
        try c.encode(muzzleBroad, forKey: .muzzleBroad)
        try c.encode(hoofSize, forKey: .hoofSize)
        try c.encode(headScale, forKey: .headScale)
        try c.encode(earScale, forKey: .earScale)
        try c.encode(eyeScale, forKey: .eyeScale)
        try c.encode(shetland, forKey: .shetland)
    }
}
