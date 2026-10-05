import Foundation

/// Aspect d'un sabot (la corne copie le pigment de la peau de la couronne [NV]).
public enum HoofAppearance: String, Codable, CaseIterable, Sendable {
    /// Corne foncée (couronne pigmentée).
    case dark
    /// Corne claire (couronne blanche, peau rose).
    case light
    /// Rayée verticalement (balzane partielle, hermine, complexe léopard).
    case striped
    /// Couleur forcée (mode libre).
    case custom
}

/// Couleurs dérivées d'une configuration (génotype -> phénotype), pour l'interface et les matériaux simples.
/// Le détail par texel (robe, marques, sabots rayés…) est produit par `CoatCompositor`.
public struct CoatPhenotype: Equatable, Sendable {
    public let baseCoat: BaseCoat
    /// Couleur moyenne du poil du corps (avant gris, rouan, panachures).
    public let bodyColor: PonyColor
    /// Couleur des extrémités.
    public let pointsColor: PonyColor
    /// Couleur des crins.
    public let maneColor: PonyColor
    /// Couleur de la peau nue (bout du nez, tour des yeux) hors marques blanches.
    public let skinColor: PonyColor
    /// Couleur dominante de l'iris.
    public let eyeColor: PonyColor
    public let eye: EyeColorKind
    /// AG, AD, PG, PD.
    public let hooves: [HoofAppearance]
    /// Couleur dominante de chaque sabot (AG, AD, PG, PD).
    public let hoofColors: [PonyColor]
    /// Peau rose sur tout le corps (double crème, blanc dominant étendu).
    public let pinkSkin: Bool
    /// Sclère blanche visible (complexe léopard).
    public let whiteSclera: Bool
    public let leopardPattern: LeopardPattern?
    /// Catégorie de chaque balzane (AG, AD, PG, PD).
    public let legCategories: [LegMarkingCategory]

    public init(_ configuration: CoatConfiguration) {
        let p = CoatPalette(configuration)
        baseCoat = configuration.genotype.baseCoat
        bodyColor = PonyColor(linear: p.body)
        pointsColor = PonyColor(linear: p.points)
        maneColor = PonyColor(linear: p.mane)
        skinColor = PonyColor(linear: p.pinkAll > 0 ? p.skinPink : p.skinDark)
        eyeColor = PonyColor(linear: p.iris.base)
        eye = p.iris.kind
        var hv: [HoofAppearance] = []
        var hc: [PonyColor] = []
        for i in 0..<4 {
            let a: HoofAppearance
            let c: SIMD3<Float>
            if p.hoofOverride > 0 {
                a = .custom
                c = p.hoofOverrideColor
            } else if p.hoofStripe[i] > 0 {
                a = .striped
                c = coatMix(p.hoofDark, p.hoofLight, 0.5)
            } else if p.hoofWhite[i] > 0 || p.pinkAll > 0 {
                a = .light
                c = p.hoofLight
            } else {
                a = .dark
                c = p.hoofDark
            }
            hv.append(a)
            hc.append(PonyColor(linear: c))
        }
        hooves = hv
        hoofColors = hc
        pinkSkin = p.pinkAll > 0
        whiteSclera = configuration.genotype.leopardComplex.isPresent
        leopardPattern = configuration.genotype.leopardPattern
        legCategories = configuration.legs.all.map { $0.category }
    }
}
