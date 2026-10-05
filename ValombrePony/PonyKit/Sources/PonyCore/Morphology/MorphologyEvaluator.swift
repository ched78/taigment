import Foundation

/// Résultat de l'évaluation de la morphologie : poids de blend shapes (≥ 0) et ajustements de joints.
public struct MorphologyResult: Sendable, Equatable {
    /// Poids des formes de morphologie et de proportion, tous dans [0, 1].
    public var blendWeights: [String: Float]
    /// Décalages de translation **locale** (espace du parent) à ajouter à la pose, par joint.
    public var jointOffsets: [SIMD3<Float>]
    /// Facteurs d'échelle multiplicatifs par joint (tête, oreilles, yeux, curseurs du manifeste).
    public var jointScales: [SIMD3<Float>]

    public init(blendWeights: [String: Float], jointOffsets: [SIMD3<Float>], jointScales: [SIMD3<Float>]) {
        self.blendWeights = blendWeights
        self.jointOffsets = jointOffsets
        self.jointScales = jointScales
    }
}

/// Transforme une `MorphologyConfiguration` en poids de blend shapes + décalages/échelles de joints.
///
/// Les noms des formes et les décalages viennent des curseurs du manifeste (`morphology.sliders`) ; à défaut,
/// noms du SPEC §5 et aucun décalage. Le **même poids** est appliqué à la forme de proportion et aux décalages
/// de joints (SPEC §5) ⇒ cohérence en toute pose.
public struct MorphologyEvaluator: Sendable {
    public let skeleton: PonySkeleton
    let sliders: [String: PonyRigManifest.MorphSlider]

    /// Correspondance champ de configuration → curseurs du manifeste (identifiant, signe) → formes par défaut.
    /// Les identifiants de l'exporteur (`Pipeline/pony/runtime_export.py`, DEFAULT_SLIDERS) sont acceptés comme
    /// alias : `muscular`, `boneHeavy`, `hoovesLarge`, et `headProfile` dont le sens est inversé
    /// (plus = `head_roman`), d'où le signe −1.
    struct SliderMapping {
        var key: String
        var aliases: [(id: String, sign: Float)]
        var plus: String
        var minus: String?
    }

    static let mapping: [SliderMapping] = [
        SliderMapping(key: "legLength", aliases: [("legLength", 1)], plus: "prop_legs_long", minus: "prop_legs_short"),
        SliderMapping(key: "neckLength", aliases: [("neckLength", 1)], plus: "prop_neck_long", minus: "prop_neck_short"),
        SliderMapping(key: "bodyLength", aliases: [("bodyLength", 1)], plus: "prop_body_long", minus: "prop_body_short"),
        SliderMapping(key: "stocky", aliases: [("stocky", 1)], plus: "shape_stocky", minus: nil),
        SliderMapping(key: "refined", aliases: [("refined", 1)], plus: "shape_refined", minus: nil),
        SliderMapping(key: "condition", aliases: [("condition", 1)], plus: "shape_fat", minus: "shape_thin"),
        SliderMapping(key: "muscle", aliases: [("muscle", 1), ("muscular", 1)], plus: "shape_muscular", minus: nil),
        SliderMapping(key: "belly", aliases: [("belly", 1)], plus: "shape_belly", minus: nil),
        SliderMapping(key: "crest", aliases: [("crest", 1)], plus: "shape_crest", minus: nil),
        SliderMapping(key: "bone", aliases: [("bone", 1), ("boneHeavy", 1)], plus: "shape_bone_heavy", minus: nil),
        SliderMapping(key: "headShape", aliases: [("headShape", 1), ("headProfile", -1)], plus: "head_dished",
                      minus: "head_roman"),
        SliderMapping(key: "headShort", aliases: [("headShort", 1)], plus: "head_short", minus: nil),
        SliderMapping(key: "muzzleBroad", aliases: [("muzzleBroad", 1)], plus: "muzzle_broad", minus: nil),
        SliderMapping(key: "hoofSize", aliases: [("hoofSize", 1), ("hoovesLarge", 1)], plus: "hooves_large", minus: nil),
    ]

    public init(manifest: PonyRigManifest) {
        self.init(skeleton: PonySkeleton(manifest: manifest), sliders: manifest.morphology.sliders)
    }

    public init(skeleton: PonySkeleton, sliders: [PonyRigManifest.MorphSlider]) {
        self.skeleton = skeleton
        var d: [String: PonyRigManifest.MorphSlider] = [:]
        for s in sliders where d[s.id] == nil {
            d[s.id] = s
        }
        self.sliders = d
    }

    /// Valeurs effectives : composite `shetland` appliqué puis bornage.
    /// Coefficients du composite [A] ; tendances : jambes et encolure plus courtes, tronc trapu, museau large,
    /// petites oreilles (standard Shetland [R anatomy §2.4]), crâne relativement grand et yeux relativement
    /// grands (Heck et al. 2019 [R anatomy §2.3]), sabots relativement grands [R anatomy §2.4].
    public static func effectiveValues(_ input: MorphologyConfiguration) -> MorphologyConfiguration {
        let m = input.clamped
        let s = m.shetland
        if s <= 0 { return m }
        var e = m
        e.legLength -= 0.6 * s
        e.neckLength -= 0.4 * s
        e.bodyLength -= 0.2 * s
        e.stocky += 0.8 * s
        e.refined *= (1 - s)
        e.condition += 0.2 * s
        e.crest += 0.3 * s
        e.bone += 0.4 * s
        e.muzzleBroad += 0.7 * s
        e.headShort += 0.3 * s
        e.hoofSize += 0.3 * s
        e.headScale *= (1 + 0.08 * s)
        e.earScale *= (1 - 0.2 * s)
        e.eyeScale *= (1 + 0.06 * s)
        return e.clamped
    }

    /// Valeur d'un curseur par identifiant (après composite).
    static func value(of id: String, in m: MorphologyConfiguration) -> Float {
        switch id {
        case "legLength": return m.legLength
        case "neckLength": return m.neckLength
        case "bodyLength": return m.bodyLength
        case "stocky": return m.stocky
        case "refined": return m.refined
        case "condition": return m.condition
        case "muscle": return m.muscle
        case "belly": return m.belly
        case "crest": return m.crest
        case "bone": return m.bone
        case "headShape": return m.headShape
        case "headShort": return m.headShort
        case "muzzleBroad": return m.muzzleBroad
        case "hoofSize": return m.hoofSize
        default: return 0
        }
    }

    public func evaluate(_ configuration: MorphologyConfiguration) -> MorphologyResult {
        let m = MorphologyEvaluator.effectiveValues(configuration)
        let n = skeleton.count
        var weights: [String: Float] = [:]
        var offsets = [SIMD3<Float>](repeating: SIMD3<Float>(0, 0, 0), count: n)
        var scales = [SIMD3<Float>](repeating: SIMD3<Float>(1, 1, 1), count: n)

        for entry in MorphologyEvaluator.mapping {
            var v = MorphologyEvaluator.value(of: entry.key, in: m)
            var slider: PonyRigManifest.MorphSlider? = nil
            for alias in entry.aliases {
                if let s = sliders[alias.id] {
                    slider = s
                    v *= alias.sign
                    break
                }
            }
            // Curseur déclaré par le manifeste : ses noms font foi (`null` = forme absente du corps).
            let plusName: String? = slider != nil ? slider?.plus : entry.plus
            let minusName: String? = slider != nil ? slider?.minus : entry.minus
            let wPlus = max(0, v)
            let wMinus = max(0, -v)
            if let pn = plusName {
                weights[pn] = PonyMath.clamp01((weights[pn] ?? 0) + wPlus)
            }
            if let mn = minusName {
                weights[mn] = PonyMath.clamp01((weights[mn] ?? 0) + wMinus)
            }
            guard let sl = slider else { continue }
            // Décalages : côté moins absent ⇒ symétrique du côté plus [I].
            let minusOffsets = sl.jointOffsetsMinus.isEmpty ? nil : sl.jointOffsetsMinus
            for name in sl.jointOffsetsPlus.keys.sorted() {
                guard let j = skeleton.index(of: name), let o = sl.jointOffsetsPlus[name] else { continue }
                if wPlus > 0 {
                    offsets[j] += o * wPlus
                } else if wMinus > 0 && minusOffsets == nil {
                    offsets[j] -= o * wMinus
                }
            }
            if let mo = minusOffsets, wMinus > 0 {
                for name in mo.keys.sorted() {
                    guard let j = skeleton.index(of: name), let o = mo[name] else { continue }
                    offsets[j] += o * wMinus
                }
            }
            if wPlus > 0 {
                for name in sl.jointScalesPlus.keys.sorted() {
                    guard let j = skeleton.index(of: name), let f = sl.jointScalesPlus[name] else { continue }
                    scales[j] *= SIMD3<Float>(1, 1, 1) + (f - SIMD3<Float>(1, 1, 1)) * wPlus
                }
            }
            if wMinus > 0 {
                for name in sl.jointScalesMinus.keys.sorted() {
                    guard let j = skeleton.index(of: name), let f = sl.jointScalesMinus[name] else { continue }
                    scales[j] *= SIMD3<Float>(1, 1, 1) + (f - SIMD3<Float>(1, 1, 1)) * wMinus
                }
            }
        }

        // Échelles de la tête, des oreilles et des yeux (SPEC §5 : échelle des joints).
        func scale(_ names: [String], _ f: Float) {
            if abs(f - 1) < 1e-6 { return }
            for name in names {
                if let j = skeleton.index(of: name) { scales[j] *= SIMD3<Float>(f, f, f) }
            }
        }
        scale(["head"], m.headScale)
        scale(["ear_l", "ear_r"], m.earScale)
        // Les paupières tournent autour du centre de l'œil : même échelle que le globe.
        scale(["eye_l", "eye_r", "eyelid_upper_l", "eyelid_lower_l", "eyelid_upper_r", "eyelid_lower_r"], m.eyeScale)

        for (k, v) in weights {
            weights[k] = PonyMath.clamp01(PonyMath.finite(v))
        }
        return MorphologyResult(blendWeights: weights, jointOffsets: offsets, jointScales: scales)
    }
}

/// Préréglages de morphologie (noms français). Coefficients **[A]** (à caler sur photos de référence) ;
/// hauteurs au garrot dans les fourchettes des standards de race [R anatomy §3.2] : Welsh B ≤ 1,37 m,
/// Connemara 1,28–1,48 m, Shetland ≤ 1,07 m ; « poney de sport » : choix de jeu.
public struct MorphologyPreset: Sendable, Equatable, Identifiable {
    public var id: String
    public var name: String
    public var withersHeight: Float
    public var morphology: MorphologyConfiguration

    public init(id: String, name: String, withersHeight: Float, morphology: MorphologyConfiguration) {
        self.id = id
        self.name = name
        self.withersHeight = withersHeight
        self.morphology = morphology
    }

    public static let welshB = MorphologyPreset(
        id: "welsh_b", name: "Welsh B", withersHeight: 1.30,
        morphology: MorphologyConfiguration(refined: 0.2, muscle: 0.2, crest: 0.1, headShape: 0.3, headShort: 0.2,
                                            earScale: 0.95, eyeScale: 1.03))

    public static let connemara = MorphologyPreset(
        id: "connemara", name: "Connemara", withersHeight: 1.40,
        morphology: MorphologyConfiguration(bodyLength: 0.1, stocky: 0.15, refined: 0.1, muscle: 0.35, bone: 0.3,
                                            hoofSize: 0.1))

    public static let shetland = MorphologyPreset(
        id: "shetland", name: "Shetland", withersHeight: 1.00,
        morphology: MorphologyConfiguration(condition: 0.1, shetland: 1.0))

    public static let sportPony = MorphologyPreset(
        id: "sport_pony", name: "Poney de sport", withersHeight: 1.46,
        morphology: MorphologyConfiguration(legLength: 0.3, neckLength: 0.25, bodyLength: 0.05, refined: 0.7,
                                            muscle: 0.4, headShape: 0.2, headScale: 0.97))

    public static let all: [MorphologyPreset] = [welshB, connemara, shetland, sportPony]
}
