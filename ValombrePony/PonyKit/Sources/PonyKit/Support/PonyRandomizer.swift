import Foundation
import PonyCore

/// Tirage d'un poney « plausible » : préréglage de morphologie légèrement varié, robe tirée parmi les présets
/// (avec quelques contraintes de race, Docs/COAT.md §8), marques et crins aux probabilités modestes,
/// harnachement cohérent résolu par `AccessoryRules`. Probabilités et amplitudes : [A].
public struct PonyRandomizer {
    public init() {}

    public func plausible<G: RandomNumberGenerator>(using rng: inout G, rules: AccessoryRules,
                                                     name: String = "Poney") -> PonyConfiguration {
        var config = PonyConfiguration(name: name)

        // Morphologie : un préréglage + variations.
        let preset = MorphologyPreset.all.randomElement(using: &rng) ?? MorphologyPreset.welshB
        config.apply(preset: preset)
        func jitter(_ v: Float, _ amount: Float, _ range: ClosedRange<Float>) -> Float {
            let d = Float.random(in: -amount...amount, using: &rng)
            return min(max(v + d, range.lowerBound), range.upperBound)
        }
        var m = config.morphology
        let bi = MorphologyConfiguration.bipolarRange
        let unit = MorphologyConfiguration.unitRange
        m.legLength = jitter(m.legLength, 0.15, bi)
        m.neckLength = jitter(m.neckLength, 0.15, bi)
        m.bodyLength = jitter(m.bodyLength, 0.10, bi)
        m.condition = jitter(m.condition, 0.25, bi)
        m.muscle = jitter(m.muscle, 0.2, unit)
        m.crest = jitter(m.crest, 0.2, unit)
        m.belly = jitter(m.belly, 0.15, unit)
        m.headShape = jitter(m.headShape, 0.2, bi)
        m.earScale = jitter(m.earScale, 0.06, MorphologyConfiguration.earScaleRange)
        m.eyeScale = jitter(m.eyeScale, 0.03, MorphologyConfiguration.eyeScaleRange)
        config.morphology = m
        config.withersHeight = jitter(config.withersHeight, 0.04, PonyConfiguration.withersHeightRange)

        // Robe : présets, sans robes tachetées pour le Shetland (COAT.md §8 : « tout sauf tacheté »).
        var candidates = CoatPreset.all
        if preset.id == MorphologyPreset.shetland.id {
            candidates = candidates.filter { $0.configuration.genotype.leopardPattern == nil }
        }
        var coat = (candidates.randomElement(using: &rng) ?? CoatPreset.defaultPreset).configuration
        coat.seed = UInt32.random(in: 1...UInt32.max, using: &rng)
        // Marques de tête : réutilise celle du préset une fois sur deux, sinon tirage.
        if Bool.random(using: &rng) {
            let kinds: [FaceMarkingKind] = [.absent, .star, .star, .strip, .blaze, .absent]
            coat.face.kind = kinds.randomElement(using: &rng) ?? .absent
            coat.face.size = Float.random(in: 0.7...1.3, using: &rng)
            coat.face.snip = Float.random(in: 0...1, using: &rng) < 0.15
        }
        // Balzanes : chaque membre 25 %, plus souvent aux postérieurs.
        for i in 0..<4 {
            let p: Float = i >= 2 ? 0.30 : 0.18
            var leg = coat.legs[i]
            if Float.random(in: 0...1, using: &rng) < p {
                leg.height = Float.random(in: 0.02...0.45, using: &rng)
                leg.ermine = Float.random(in: 0...1, using: &rng) < 0.1
            }
            coat.legs[i] = leg
        }
        coat.expression.shade = jitter(coat.expression.shade, 0.3, -1...1)
        config.coat = coat

        // Crins.
        var hair = HairStyle()
        let roll = Float.random(in: 0...1, using: &rng)
        if roll < 0.15 {
            hair.mane = "mane_braided"
            hair.forelock = Bool.random(using: &rng) ? "forelock_braided" : "forelock_natural"
            hair.tail = Float.random(in: 0...1, using: &rng) < 0.4 ? "tail_braided" : "tail_natural"
        } else if roll < 0.22 {
            hair.mane = "mane_roached"
        }
        hair.feathers = preset.id == MorphologyPreset.shetland.id && Float.random(in: 0...1, using: &rng) < 0.5
        config.setHair(hair, rules: rules)

        // Harnachement : nu, au licol, sellé à l'anglaise ou en western, ou au repos sous couverture.
        let kit = Float.random(in: 0...1, using: &rng)
        var picks: [AccessorySelection] = []
        if kit < 0.25 {
            picks = []
        } else if kit < 0.45 {
            picks = [AccessorySelection(partID: "halter")]
        } else if kit < 0.75 {
            picks = [AccessorySelection(partID: "saddle_english"), AccessorySelection(partID: "saddle_pad_english"),
                     AccessorySelection(partID: "bridle_snaffle")]
            if Bool.random(using: &rng) { picks.append(AccessorySelection(partID: "boots_brushing")) }
        } else if kit < 0.88 {
            picks = [AccessorySelection(partID: "saddle_western"), AccessorySelection(partID: "saddle_pad_western"),
                     AccessorySelection(partID: "bridle_snaffle")]
        } else {
            picks = [AccessorySelection(partID: "rug_stable"), AccessorySelection(partID: "halter")]
        }
        if hair.mane == "mane_braided" && Bool.random(using: &rng) {
            picks.append(AccessorySelection(partID: Bool.random(using: &rng) ? "ribbons_mane" : "pompons"))
        }
        let palette = PonyRandomizer.fabricPalette
        let fabric = palette.randomElement(using: &rng) ?? PonyDefaultColors.navy
        let accent = palette.randomElement(using: &rng) ?? PonyDefaultColors.cream
        for var sel in picks where rules.part(sel.partID) != nil {
            if let part = rules.part(sel.partID), !part.fabricSlots.isEmpty {
                sel.slotColors[PonyMaterialNames.primary] = fabric
                sel.slotColors[PonyMaterialNames.accent] = accent
                if Float.random(in: 0...1, using: &rng) < 0.3 {
                    sel.pattern = FabricPattern.allCases.randomElement(using: &rng)
                }
            }
            config.add(sel, rules: rules)
        }
        return config
    }

    /// Variante avec le générateur système.
    public func plausible(rules: AccessoryRules, name: String = "Poney") -> PonyConfiguration {
        var g = SystemRandomNumberGenerator()
        return plausible(using: &g, rules: rules, name: name)
    }

    static let fabricPalette: [PonyColor] = [
        PonyColor(hex: "#1F3566"), PonyColor(hex: "#6E1E2C"), PonyColor(hex: "#2F5D3A"), PonyColor(hex: "#3A3A3A"),
        PonyColor(hex: "#C7A24B"), PonyColor(hex: "#8E5BA8"), PonyColor(hex: "#3E8DBF"), PonyColor(hex: "#E7E3D8"),
        PonyColor(hex: "#D9677F"),
    ]
}
