import Foundation

/// Configuration complète d'un poney (sauvegarde du jeu) : nom, taille, robe, crins, morphologie, accessoires.
///
/// JSON stable : clés triées (`jsonData()`), décodage tolérant (champ absent → valeur par défaut), champ
/// `version` pour les migrations futures (version courante : `PonyConfiguration.currentVersion`).
public struct PonyConfiguration: Codable, Equatable, Sendable {
    public static let currentVersion = 1
    /// Bornes de la hauteur au garrot (m) : Shetland ~1,00 m … grand poney 1,48 m (SPEC §0, brief).
    public static let withersHeightRange: ClosedRange<Float> = 1.00...1.48

    public var version: Int
    public var name: String
    /// Hauteur au garrot (m), 1,00…1,48 → échelle de l'entité = `withersHeight / 1,30`.
    public var withersHeight: Float
    public var coat: CoatConfiguration
    public var hair: HairStyle
    public var morphology: MorphologyConfiguration
    public var accessories: [AccessorySelection]

    public init(version: Int = PonyConfiguration.currentVersion, name: String = "Poney",
                withersHeight: Float = PonyRigDefaults.referenceWithersHeight,
                coat: CoatConfiguration = CoatConfiguration.default, hair: HairStyle = HairStyle.default,
                morphology: MorphologyConfiguration = MorphologyConfiguration.default,
                accessories: [AccessorySelection] = []) {
        self.version = version
        self.name = name
        self.withersHeight = withersHeight
        self.coat = coat
        self.hair = hair
        self.morphology = morphology
        self.accessories = accessories
    }

    public static let `default` = PonyConfiguration()

    /// Échelle de l'entité RealityKit (le rig est modélisé pour 1,30 m).
    public var entityScale: Float {
        return clampedWithersHeight / PonyRigDefaults.referenceWithersHeight
    }

    /// Hauteur au garrot bornée (valeur non finie → 1,30 m).
    public var clampedWithersHeight: Float {
        let r = PonyConfiguration.withersHeightRange
        if !withersHeight.isFinite { return PonyRigDefaults.referenceWithersHeight }
        return PonyMath.clamp(withersHeight, r.lowerBound, r.upperBound)
    }

    /// Applique un préréglage de morphologie (et sa hauteur au garrot).
    public mutating func apply(preset: MorphologyPreset) {
        morphology = preset.morphology
        withersHeight = preset.withersHeight
    }

    /// Ajoute (ou remplace) un accessoire en résolvant conflits, prérequis et emplacements ; une pièce de
    /// crins modifie `hair`.
    public mutating func add(_ selection: AccessorySelection, rules: AccessoryRules) {
        var h = hair
        accessories = rules.resolving(adding: selection, to: accessories, hair: &h)
        hair = h
    }

    /// Retire un accessoire (et ceux qui en dépendaient).
    public mutating func removeAccessory(_ partID: String, rules: AccessoryRules) {
        accessories = rules.removing(partID, from: accessories, hair: hair)
    }

    /// Change la coiffure et retire les accessoires devenus invalides (ex. rubans sans crinière tressée).
    public mutating func setHair(_ newHair: HairStyle, rules: AccessoryRules) {
        hair = newHair
        accessories = rules.resolving(hair: newHair, accessories: accessories)
    }

    // MARK: JSON

    /// Encodage JSON stable (clés triées), lisible si `pretty`.
    public func jsonData(pretty: Bool = true) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = pretty ? [.sortedKeys, .prettyPrinted] : [.sortedKeys]
        return try encoder.encode(self)
    }

    public static func decode(from data: Data) throws -> PonyConfiguration {
        return try JSONDecoder().decode(PonyConfiguration.self, from: data)
    }

    private enum CodingKeys: String, CodingKey {
        case version, name, withersHeight, coat, hair, morphology, accessories
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // Version absente : sauvegarde antérieure au versionnage → traitée comme la version courante.
        version = (try? c.decodeIfPresent(Int.self, forKey: .version)) ?? PonyConfiguration.currentVersion
        name = (try? c.decodeIfPresent(String.self, forKey: .name)) ?? "Poney"
        withersHeight = (try? c.decodeIfPresent(Float.self, forKey: .withersHeight))
            ?? PonyRigDefaults.referenceWithersHeight
        coat = (try? c.decodeIfPresent(CoatConfiguration.self, forKey: .coat)) ?? CoatConfiguration.default
        hair = (try? c.decodeIfPresent(HairStyle.self, forKey: .hair)) ?? HairStyle.default
        morphology = (try? c.decodeIfPresent(MorphologyConfiguration.self, forKey: .morphology))
            ?? MorphologyConfiguration.default
        // Accessoires : une entrée illisible est ignorée sans faire échouer toute la sauvegarde.
        let lenient = (try? c.decodeIfPresent([LenientAccessory].self, forKey: .accessories)) ?? nil
        accessories = (lenient ?? []).compactMap { $0.value }
        if version < PonyConfiguration.currentVersion {
            migrate(from: version)
        }
    }

    /// Migrations entre versions (aucune pour l'instant : la version 1 est la première).
    private mutating func migrate(from oldVersion: Int) {
        version = PonyConfiguration.currentVersion
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(version, forKey: .version)
        try c.encode(name, forKey: .name)
        try c.encode(withersHeight, forKey: .withersHeight)
        try c.encode(coat, forKey: .coat)
        try c.encode(hair, forKey: .hair)
        try c.encode(morphology, forKey: .morphology)
        try c.encode(accessories, forKey: .accessories)
    }
}

/// Élément de liste décodé sans jamais échouer (entrée invalide → `nil`), pour la tolérance de la sauvegarde.
private struct LenientAccessory: Decodable {
    let value: AccessorySelection?

    init(from decoder: Decoder) throws {
        value = try? AccessorySelection(from: decoder)
    }
}
