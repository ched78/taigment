import Foundation

// Génotype SIMPLIFIÉ des robes (Docs/research/anatomy.md §4.1, entièrement [NV] : non vérifié dans cette session,
// écrit d'après la littérature primaire citée de mémoire). Les rawValue sont les valeurs JSON (Codable) partagées
// avec l'implémentation de référence Python (`coat_reference.py`, ENUMS).

/// Nombre de copies d'un allèle dominant (n/n, X/n, X/X).
public enum Zygosity: String, Codable, CaseIterable, Sendable {
    case absent = "n/n"
    case heterozygous = "X/n"
    case homozygous = "X/X"

    public var alleleCount: Int {
        switch self {
        case .absent: return 0
        case .heterozygous: return 1
        case .homozygous: return 2
        }
    }

    public var isPresent: Bool { self != .absent }
}

/// Locus Extension (MC1R) : E/_ autorise le pigment noir ; e/e = rouge seulement (alezan).
public enum ExtensionGenotype: String, Codable, CaseIterable, Sendable {
    case blackAllowed = "E"
    case redOnly = "ee"
}

/// Locus Agouti (ASIP) : A/_ cantonne le noir aux extrémités (bai) ; At = bai brun ; a/a = noir.
public enum AgoutiGenotype: String, Codable, CaseIterable, Sendable {
    case bay = "A"
    case sealBrown = "At"
    case black = "aa"
}

/// Locus SLC45A2 : crème (Cr) et perle (prl) sont des allèles du même gène (2 copies au plus).
public enum CreamPearlGenotype: String, Codable, CaseIterable, Sendable {
    case noDilution = "N/N"
    case cream = "Cr/N"
    case doubleCream = "Cr/Cr"
    case pearlCarrier = "prl/N"
    case pearl = "prl/prl"
    case creamPearl = "Cr/prl"
}

/// Génotype simplifié. Les gènes « à expression variable » (panachures, léopard, gris, rouan) sont complétés par
/// des paramètres d'expression (`CoatExpression` : couverture, stade, densité).
public struct CoatGenotype: Codable, Equatable, Hashable, Sendable {
    public var extensionLocus: ExtensionGenotype
    public var agouti: AgoutiGenotype
    public var creamPearl: CreamPearlGenotype
    /// Dun (TBX3) : dilue le corps (pas les extrémités) + marques primitives.
    public var dun: Zygosity
    /// Silver (PMEL17) : dilue le pigment NOIR seulement (sans effet visible sur un alezan).
    public var silver: Zygosity
    /// Champagne (SLC36A1) : dilue les deux pigments ; peau rose tachetée, yeux ambre.
    public var champagne: Zygosity
    /// Gris (STX17) : grisonnement progressif (stade dans `CoatExpression.greyStage`).
    public var grey: Zygosity
    /// Rouan (KIT) : poils blancs mêlés, tête et bas des membres foncés.
    public var roan: Zygosity
    public var tobiano: Zygosity
    /// Overo « frame » (EDNRB). O/O est létal (syndrome du poulain blanc létal) : traité comme O/n.
    public var frameOvero: Zygosity
    public var sabino: Zygosity
    public var splashedWhite: Zygosity
    public var dominantWhite: Zygosity
    /// Complexe léopard (TRPM1, « LP »).
    public var leopardComplex: Zygosity
    /// PATN1 : avec LP, étend le blanc à tout le corps (léopard ; LP/LP + PATN1 = peu taché).
    public var patternOne: Zygosity

    public init(extensionLocus: ExtensionGenotype = .blackAllowed,
                agouti: AgoutiGenotype = .bay,
                creamPearl: CreamPearlGenotype = .noDilution,
                dun: Zygosity = .absent,
                silver: Zygosity = .absent,
                champagne: Zygosity = .absent,
                grey: Zygosity = .absent,
                roan: Zygosity = .absent,
                tobiano: Zygosity = .absent,
                frameOvero: Zygosity = .absent,
                sabino: Zygosity = .absent,
                splashedWhite: Zygosity = .absent,
                dominantWhite: Zygosity = .absent,
                leopardComplex: Zygosity = .absent,
                patternOne: Zygosity = .absent) {
        self.extensionLocus = extensionLocus
        self.agouti = agouti
        self.creamPearl = creamPearl
        self.dun = dun
        self.silver = silver
        self.champagne = champagne
        self.grey = grey
        self.roan = roan
        self.tobiano = tobiano
        self.frameOvero = frameOvero
        self.sabino = sabino
        self.splashedWhite = splashedWhite
        self.dominantWhite = dominantWhite
        self.leopardComplex = leopardComplex
        self.patternOne = patternOne
    }

    /// Couleur de base avant dilutions et motifs.
    public var baseCoat: BaseCoat {
        if extensionLocus == .redOnly { return .chestnut }
        switch agouti {
        case .bay: return .bay
        case .sealBrown: return .sealBrown
        case .black: return .black
        }
    }

    /// Le motif léopard résultant (nil sans LP).
    public var leopardPattern: LeopardPattern? {
        guard leopardComplex.isPresent else { return nil }
        if patternOne.isPresent {
            return leopardComplex == .homozygous ? .fewSpot : .leopard
        }
        return .blanket
    }
}

/// Couleur de base (Extension × Agouti).
public enum BaseCoat: String, Codable, CaseIterable, Sendable {
    case chestnut, bay, sealBrown, black

    /// Nom français.
    public var frenchName: String {
        switch self {
        case .chestnut: return "Alezan"
        case .bay: return "Bai"
        case .sealBrown: return "Bai brun"
        case .black: return "Noir"
        }
    }
}

/// Motif du complexe léopard dérivé du génotype (la couverture / marmoré dépend aussi de `CoatExpression`).
public enum LeopardPattern: String, Codable, CaseIterable, Sendable {
    case blanket, leopard, fewSpot

    public var frenchName: String {
        switch self {
        case .blanket: return "Couverture"
        case .leopard: return "Léopard"
        case .fewSpot: return "Peu taché"
        }
    }
}
