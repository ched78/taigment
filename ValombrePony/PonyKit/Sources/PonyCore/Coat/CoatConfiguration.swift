import Foundation

/// Paramètres d'expression (modificateurs polygéniques, stades, couvertures). Toutes les valeurs sont saturées
/// dans leur domaine par le compositeur ; un paramètre lié à un gène absent est ignoré.
public struct CoatExpression: Codable, Equatable, Hashable, Sendable {
    /// Nuance −1 clair … 0 moyen … +1 foncé (alezan clair → brûlé, bai clair → foncé, noir mal teint → jais).
    public var shade: Float
    /// Charbonné (sooty) : voile foncé sur la ligne du dos (masque A de coat_regions).
    public var sooty: Float
    /// Pangaré : bout du nez, tour des yeux, ventre, flancs, intérieur des membres clairs (masque B).
    public var pangare: Float
    /// Crins lavés (flaxen) — n'agit que sur un alezan [NV].
    public var flaxen: Float
    /// Pommelures saisonnières (champ A des patterns) sur une robe non grise.
    public var dapples: Float
    /// Hauteur (0…1, unités de hauteur de jambe) jusqu'où montent les extrémités noires du bai.
    public var pointsHeight: Float
    /// Intensité des marques primitives quand le dun est présent (raie de mulet, zébrures).
    public var primitiveMarkings: Float
    /// Stade de grisonnement 0 (robe de naissance) … 1 (blanc / truité), si gris.
    public var greyStage: Float
    /// Importance de la phase pommelée du gris.
    public var greyDapples: Float
    /// Mouchetures « truité » (fleabitten) aux stades avancés du gris.
    public var fleabitten: Float
    /// Densité de poils blancs du rouan.
    public var roanDensity: Float
    public var tobianoCoverage: Float
    public var overoCoverage: Float
    public var sabinoCoverage: Float
    public var splashCoverage: Float
    public var dominantWhiteCoverage: Float
    /// Étendue de la couverture blanche (léopard sans PATN1).
    public var leopardCoverage: Float
    public var spotSize: Float
    public var spotDensity: Float
    /// Marmoré (varnish roan) : poils blancs progressifs du complexe léopard.
    public var varnish: Float

    public init(shade: Float = 0, sooty: Float = 0, pangare: Float = 0, flaxen: Float = 0, dapples: Float = 0,
                pointsHeight: Float = 0.5, primitiveMarkings: Float = 1,
                greyStage: Float = 0, greyDapples: Float = 0.6, fleabitten: Float = 0,
                roanDensity: Float = 0.6,
                tobianoCoverage: Float = 0.45, overoCoverage: Float = 0.4, sabinoCoverage: Float = 0.35,
                splashCoverage: Float = 0.4, dominantWhiteCoverage: Float = 0.9,
                leopardCoverage: Float = 0.45, spotSize: Float = 0.5, spotDensity: Float = 0.6, varnish: Float = 0) {
        self.shade = shade
        self.sooty = sooty
        self.pangare = pangare
        self.flaxen = flaxen
        self.dapples = dapples
        self.pointsHeight = pointsHeight
        self.primitiveMarkings = primitiveMarkings
        self.greyStage = greyStage
        self.greyDapples = greyDapples
        self.fleabitten = fleabitten
        self.roanDensity = roanDensity
        self.tobianoCoverage = tobianoCoverage
        self.overoCoverage = overoCoverage
        self.sabinoCoverage = sabinoCoverage
        self.splashCoverage = splashCoverage
        self.dominantWhiteCoverage = dominantWhiteCoverage
        self.leopardCoverage = leopardCoverage
        self.spotSize = spotSize
        self.spotDensity = spotDensity
        self.varnish = varnish
    }
}

/// Marque principale de la tête (terminologie FR à vérifier auprès de l'IFCE / SIRE [NV]).
public enum FaceMarkingKind: String, Codable, CaseIterable, Sendable {
    case absent = "none"
    /// En tête (étoile) : sur le front.
    case star
    /// Liste étroite (étoile prolongée d'une bande fine).
    case strip
    /// Liste : plus large, n'atteint pas les yeux.
    case blaze
    /// Belle face : déborde sur les yeux.
    case baldFace

    public var frenchName: String {
        switch self {
        case .absent: return "Aucune"
        case .star: return "En tête"
        case .strip: return "Liste étroite"
        case .blaze: return "Liste"
        case .baldFace: return "Belle face"
        }
    }
}

/// Marques de tête. Coordonnées faciales du SPEC §4 (coat_params G/B) : u 0,5 = ligne médiane, v 0 = bout du nez.
public struct FaceMarking: Codable, Equatable, Hashable, Sendable {
    public var kind: FaceMarkingKind
    /// Multiplicateur de taille (0,3…2).
    public var size: Float
    /// Décalage latéral / vertical en unités faciales (−0,2…0,2).
    public var offsetU: Float
    public var offsetV: Float
    /// Ladre au bout du nez (snip) : blanc entre les naseaux.
    public var snip: Bool
    /// Lèvres blanches (« boit dans son blanc »).
    public var lips: Bool
    /// Irrégularité du bord (0 net … 1 très découpé).
    public var irregularity: Float

    public init(kind: FaceMarkingKind = .absent, size: Float = 1, offsetU: Float = 0, offsetV: Float = 0,
                snip: Bool = false, lips: Bool = false, irregularity: Float = 0.4) {
        self.kind = kind
        self.size = size
        self.offsetU = offsetU
        self.offsetV = offsetV
        self.snip = snip
        self.lips = lips
        self.irregularity = irregularity
    }
}

/// Catégorie de balzane déduite de la hauteur continue (seuils [I], cf. Docs/COAT.md).
public enum LegMarkingCategory: String, Codable, CaseIterable, Sendable {
    case none, coronet, pastern, sock, stocking, highWhite

    public var frenchName: String {
        switch self {
        case .none: return "Aucune"
        case .coronet: return "Trace de balzane"
        case .pastern: return "Petite balzane"
        case .sock: return "Balzane"
        case .stocking: return "Grande balzane"
        case .highWhite: return "Balzane haut-chaussée"
        }
    }
}

/// Balzane d'un membre.
public struct LegMarking: Codable, Equatable, Hashable, Sendable {
    /// 0 = aucune ; 0…1 = du bord de la couronne jusqu'au coude / grasset (hauteur de jambe du SPEC §4).
    public var height: Float
    /// Irrégularité du bord (bruit).
    public var irregularity: Float
    /// Mouchetures d'hermine près de la couronne (sabot rayé).
    public var ermine: Bool

    public init(height: Float = 0, irregularity: Float = 0.3, ermine: Bool = false) {
        self.height = height
        self.irregularity = irregularity
        self.ermine = ermine
    }

    /// Seuils [I] en fraction de la hauteur couronne → coude (gabarit 1,30 m : boulet ≈ 0,10, mi-canon ≈ 0,28,
    /// genou/jarret ≈ 0,45–0,50).
    public var category: LegMarkingCategory {
        if height <= 0 { return .none }
        if height < 0.04 { return .coronet }
        if height < 0.11 { return .pastern }
        if height < 0.32 { return .sock }
        if height < 0.55 { return .stocking }
        return .highWhite
    }
}

/// Balzanes des quatre membres (AG, AD, PG, PD = régions 5–8, sabots 9–12).
public struct LegMarkings: Codable, Equatable, Hashable, Sendable {
    public var frontLeft: LegMarking
    public var frontRight: LegMarking
    public var hindLeft: LegMarking
    public var hindRight: LegMarking

    public init(frontLeft: LegMarking = LegMarking(), frontRight: LegMarking = LegMarking(),
                hindLeft: LegMarking = LegMarking(), hindRight: LegMarking = LegMarking()) {
        self.frontLeft = frontLeft
        self.frontRight = frontRight
        self.hindLeft = hindLeft
        self.hindRight = hindRight
    }

    /// Indice 0 AG, 1 AD, 2 PG, 3 PD (ordre des régions du SPEC §4).
    public subscript(index: Int) -> LegMarking {
        get {
            switch index {
            case 0: return frontLeft
            case 1: return frontRight
            case 2: return hindLeft
            default: return hindRight
            }
        }
        set {
            switch index {
            case 0: frontLeft = newValue
            case 1: frontRight = newValue
            case 2: hindLeft = newValue
            default: hindRight = newValue
            }
        }
    }

    public var all: [LegMarking] { [frontLeft, frontRight, hindLeft, hindRight] }
}

/// Réglages des crins (crinière, toupet, queue, fanons partagent la même couleur).
public struct CoatHairSettings: Codable, Equatable, Hashable, Sendable {
    /// Pointes décolorées (soleil) vers une teinte lavée.
    public var tipLightening: Float
    /// Fraction de mèches blanches (crins bicolores de pie, en plus du grisonnement automatique).
    public var whiteStrands: Float
    /// Couleur de mèches secondaires (mode libre) ; nil = aucune.
    public var secondaryColor: PonyColor?
    public var secondaryFraction: Float

    public init(tipLightening: Float = 0, whiteStrands: Float = 0, secondaryColor: PonyColor? = nil,
                secondaryFraction: Float = 0) {
        self.tipLightening = tipLightening
        self.whiteStrands = whiteStrands
        self.secondaryColor = secondaryColor
        self.secondaryFraction = secondaryFraction
    }
}

/// Style d'iris ; `.automatic` = dérivé du génotype (brun, bleu, ambre, clair).
public enum IrisStyle: String, Codable, CaseIterable, Sendable {
    case automatic, brown, amber, blue
    /// Vairon : secteur bleu dans un iris brun (hétérochromie sectorielle ; une seule texture pour les deux yeux).
    case vairon
}

/// Surcharges libres (mode « libre ») : chaque couleur non nil remplace la couleur génétique correspondante.
public struct CoatOverrides: Codable, Equatable, Hashable, Sendable {
    /// Couleur du poil du corps (avant modificateurs, gris, rouan, panachures et marques).
    public var body: PonyColor?
    /// Couleur des extrémités (bas des membres, bord des oreilles).
    public var points: PonyColor?
    /// Couleur des crins.
    public var mane: PonyColor?
    /// Couleur forcée des sabots (sinon dérivée : foncés / clairs / rayés).
    public var hooves: PonyColor?
    /// Couleur forcée de l'iris.
    public var eyes: PonyColor?
    /// Couleur de la peau pigmentée (la peau sous le blanc reste rose).
    public var skin: PonyColor?

    public init(body: PonyColor? = nil, points: PonyColor? = nil, mane: PonyColor? = nil, hooves: PonyColor? = nil,
                eyes: PonyColor? = nil, skin: PonyColor? = nil) {
        self.body = body
        self.points = points
        self.mane = mane
        self.hooves = hooves
        self.eyes = eyes
        self.skin = skin
    }

    public var isEmpty: Bool {
        body == nil && points == nil && mane == nil && hooves == nil && eyes == nil && skin == nil
    }
}

/// Toute la « couleur » du poney : robe (génotype + expression), marques, crins, sabots, yeux, surcharges.
/// Codable synthétisé : le JSON est partagé avec `coat_reference.py` (mêmes clés).
public struct CoatConfiguration: Codable, Equatable, Hashable, Sendable {
    public var genotype: CoatGenotype
    public var expression: CoatExpression
    public var face: FaceMarking
    public var legs: LegMarkings
    public var hair: CoatHairSettings
    public var irisStyle: IrisStyle
    public var overrides: CoatOverrides
    /// Graine des bruits (rouan, poils blancs, bords irréguliers) : même graine = même image.
    public var seed: UInt32

    public init(genotype: CoatGenotype = CoatGenotype(), expression: CoatExpression = CoatExpression(),
                face: FaceMarking = FaceMarking(), legs: LegMarkings = LegMarkings(),
                hair: CoatHairSettings = CoatHairSettings(), irisStyle: IrisStyle = .automatic,
                overrides: CoatOverrides = CoatOverrides(), seed: UInt32 = 1) {
        self.genotype = genotype
        self.expression = expression
        self.face = face
        self.legs = legs
        self.hair = hair
        self.irisStyle = irisStyle
        self.overrides = overrides
        self.seed = seed
    }

    /// Configuration neutre (bai moyen, aucune marque) : base des présets (`plain_config()` en Python).
    public static let plain = CoatConfiguration()

    /// Préset par défaut du SPEC §4 (`coat_albedo_default.png`) : bai avec étoile.
    public static let `default`: CoatConfiguration = {
        var c = CoatConfiguration()
        c.face.kind = .star
        return c
    }()

    /// Construit une configuration à partir de `plain` (utilisé par les présets générés).
    public static func make(_ edit: (inout CoatConfiguration) -> Void) -> CoatConfiguration {
        var c = CoatConfiguration.plain
        edit(&c)
        return c
    }

    /// Couleurs dérivées (robe, crins, sabots, yeux, peau).
    public var phenotype: CoatPhenotype { CoatPhenotype(self) }

    /// Couleur des crins (dérivée ou forcée).
    public var maneColor: PonyColor { phenotype.maneColor }

    /// Couleur dominante de l'iris (dérivée ou forcée).
    public var eyeColor: PonyColor { phenotype.eyeColor }

    /// Couleur dominante de chaque sabot (AG, AD, PG, PD), dérivée des balzanes ou forcée.
    public var hoofColors: [PonyColor] { phenotype.hoofColors }
}
