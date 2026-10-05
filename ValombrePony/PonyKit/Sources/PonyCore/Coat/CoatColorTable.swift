import Foundation

// Table des couleurs de référence (sRGB hex). TOUTES SONT DES APPROXIMATIONS ARTISTIQUES [A] :
// Docs/research/anatomy.md §4.2 le dit explicitement (aucune mesure spectrophotométrique publiée consultée) ;
// à recalibrer sur photographies avec charte couleur. Identique à `coat_reference.py` (HEX_*, RAMP_*, DILUTION_TARGETS).

enum CoatColorTable {
    static let whiteHair = "#F3F0EA"
    /// Rampes (clair, moyen, foncé) interpolées en sRGB par `CoatExpression.shade` (−1, 0, +1).
    static let chestnutRamp = ("#C8843F", "#A65A2A", "#5A2E1A")   // alezan clair, alezan, alezan brûlé
    static let bayRamp = ("#B06A32", "#8B4A22", "#5C3018")        // bai clair, bai cerise, bai foncé
    static let sealRamp = ("#5A3420", "#3D2216", "#2A1810")       // bai brun
    static let blackRamp = ("#2E2622", "#1A1716", "#0E0D0D")      // noir mal teint, noir, noir jais
    static let euPoints = "#17120F"
    static let euMane = "#141110"
    static let flaxen = "#E6D3A8"
    static let greyDark = "#5C5C5A"
    static let greyLight = "#ECEBE6"
    static let fleckRed = "#8B5A3C"
    static let fleckBlack = "#3A302A"
    static let mealy = "#E0C89E"
    static let skinDark = "#2B2525"
    static let skinPink = "#DCA295"
    static let skinChampagne = "#B88E7E"
    static let freckle = "#5A4038"
    static let hoofDark = "#2E2A27"
    static let hoofLight = "#D2C2A0"
    static let chestnutHorn = "#3A332E"
    static let chestnutHornLight = "#8C7F72"
    static let maneWhite = "#E8E4DC"
    static let eyeBrown = "#4A2E19"
    static let eyeBlue = "#8FB7D8"
    static let eyeAmber = "#B07A2A"
    static let eyeLight = "#B49A5E"
    static let pupil = "#070505"
    static let granula = "#1C120C"
    static let scleraDark = "#3A2A22"
    static let scleraWhite = "#E8E2D8"

    /// Emplacements pigmentaires : chaque dilution a un facteur de densité optique par emplacement.
    enum Slot: CaseIterable {
        case pheoBody, pheoBay, pheoMane, euBody, euPoints, euMane

        /// Couleur de référence non diluée de l'emplacement.
        var base: String {
            switch self {
            case .pheoBody, .pheoMane: return CoatColorTable.chestnutRamp.1
            case .pheoBay: return CoatColorTable.bayRamp.1
            case .euBody: return CoatColorTable.blackRamp.1
            case .euPoints: return CoatColorTable.euPoints
            case .euMane: return CoatColorTable.euMane
            }
        }
    }

    enum Dilution: CaseIterable {
        case cream, doubleCream, pearl, creamPearl, dun, silver, champagne
    }

    /// Couleur obtenue quand la dilution agit sur la base de l'emplacement [A] ; nil = sans effet.
    static func target(_ gene: Dilution, _ slot: Slot) -> String? {
        switch (gene, slot) {
        case (.cream, .pheoBody): return "#D6AE62"
        case (.cream, .pheoBay): return "#C6A066"
        case (.cream, .pheoMane): return "#F2EBDD"
        case (.cream, .euBody): return "#2A221D"
        case (.cream, .euPoints): return "#1E1814"
        case (.cream, .euMane): return "#1A1512"
        case (.doubleCream, .pheoBody): return "#EDE0C6"
        case (.doubleCream, .pheoBay): return "#E8D9BD"
        case (.doubleCream, .pheoMane): return "#F2E8D4"
        case (.doubleCream, .euBody): return "#E8D8C0"
        case (.doubleCream, .euPoints): return "#D2B48C"
        case (.doubleCream, .euMane): return "#D8BE98"
        case (.pearl, .pheoBody): return "#DDB08A"
        case (.pearl, .pheoBay): return "#D2AA82"
        case (.pearl, .pheoMane): return "#E4C2A0"
        case (.pearl, .euBody): return "#5E5048"
        case (.pearl, .euPoints): return "#4A3E36"
        case (.pearl, .euMane): return "#4A3E36"
        case (.creamPearl, .pheoBody): return "#EAD6B8"
        case (.creamPearl, .pheoBay): return "#E2CCAA"
        case (.creamPearl, .pheoMane): return "#EEDFC6"
        case (.creamPearl, .euBody): return "#D2C0A6"
        case (.creamPearl, .euPoints): return "#B89C7E"
        case (.creamPearl, .euMane): return "#C0A688"
        case (.dun, .pheoBody): return "#CC9566"
        case (.dun, .pheoBay): return "#BC9B6A"
        case (.dun, .euBody): return "#7A726A"
        case (.dun, _): return nil
        case (.silver, .euBody): return "#5A4A42"
        case (.silver, .euPoints): return "#4A3B33"
        case (.silver, .euMane): return "#E0D4C2"
        case (.silver, _): return nil
        case (.champagne, .pheoBody): return "#D8B37A"
        case (.champagne, .pheoBay): return "#C8A270"
        case (.champagne, .pheoMane): return "#E6D2A8"
        case (.champagne, .euBody): return "#9C8A7A"
        case (.champagne, .euPoints): return "#6E5646"
        case (.champagne, .euMane): return "#7A6252"
        }
    }
}

// MARK: - Arithmétique de couleur en Double (palette ; identique aux fonctions _*64 de coat_reference.py)

typealias CoatD3 = SIMD3<Double>

enum CoatColorMath {
    /// sRGB float32 promu en Double (comme `_srgb64` en Python).
    static func srgb(_ hex: String) -> CoatD3 {
        srgb(PonyColor(hex: hex))
    }

    static func srgb(_ c: PonyColor) -> CoatD3 {
        CoatD3(Double(c.r), Double(c.g), Double(c.b))
    }

    static func lin(_ s: CoatD3) -> CoatD3 {
        CoatD3(PonyColor.srgbToLinear(s.x), PonyColor.srgbToLinear(s.y), PonyColor.srgbToLinear(s.z))
    }

    static func lin(_ hex: String) -> CoatD3 {
        lin(srgb(hex))
    }

    static func lin(_ c: PonyColor) -> CoatD3 {
        lin(srgb(c))
    }

    /// Rampe clair (−1) / moyen (0) / foncé (+1), interpolée en sRGB.
    static func ramp(_ r: (String, String, String), _ shade: Double) -> CoatD3 {
        let light = srgb(r.0)
        let mid = srgb(r.1)
        let dark = srgb(r.2)
        let t = min(max(shade, -1), 1)
        if t < 0 {
            return CoatD3(mid.x + (light.x - mid.x) * (-t), mid.y + (light.y - mid.y) * (-t),
                          mid.z + (light.z - mid.z) * (-t))
        }
        return CoatD3(mid.x + (dark.x - mid.x) * t, mid.y + (dark.y - mid.y) * t, mid.z + (dark.z - mid.z) * t)
    }

    static let white: CoatD3 = lin(CoatColorTable.whiteHair)

    /// Densité optique relative au poil blanc : D = −ln(clamp(c / blanc, 1e-4, 1)).
    static func density(_ c: CoatD3) -> CoatD3 {
        let w = white
        return CoatD3(-log(min(max(c.x / w.x, 1e-4), 1)), -log(min(max(c.y / w.y, 1e-4), 1)),
                      -log(min(max(c.z / w.z, 1e-4), 1)))
    }

    /// Facteur de dilution k = D(cible) / D(base) par canal (1 si la dilution n'agit pas sur l'emplacement).
    static func dilutionFactor(_ gene: CoatColorTable.Dilution, _ slot: CoatColorTable.Slot) -> CoatD3 {
        guard let tgt = CoatColorTable.target(gene, slot) else { return CoatD3(1, 1, 1) }
        let db = density(lin(slot.base))
        let dt = density(lin(tgt))
        return CoatD3(db.x > 1e-6 ? dt.x / db.x : 1, db.y > 1e-6 ? dt.y / db.y : 1, db.z > 1e-6 ? dt.z / db.z : 1)
    }

    /// c' = blanc · exp(−D(c) · k).
    static func applyDensity(_ c: CoatD3, _ k: CoatD3) -> CoatD3 {
        let w = white
        let d = density(c)
        return CoatD3(w.x * exp(-d.x * k.x), w.y * exp(-d.y * k.y), w.z * exp(-d.z * k.z))
    }

    static func densify(_ c: CoatD3, _ k: Double) -> CoatD3 {
        applyDensity(c, CoatD3(k, k, k))
    }

    static func mix(_ a: CoatD3, _ b: CoatD3, _ t: Double) -> CoatD3 {
        CoatD3(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t)
    }

    static func f32(_ v: CoatD3) -> SIMD3<Float> {
        SIMD3<Float>(Float(v.x), Float(v.y), Float(v.z))
    }
}
