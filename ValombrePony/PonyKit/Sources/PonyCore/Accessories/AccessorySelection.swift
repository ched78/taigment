import Foundation

/// Motif des slots tissu (composé au runtime par PonyKit).
public enum FabricPattern: String, Codable, CaseIterable, Sendable {
    case plain, stripes, checks, stars, hearts

    /// Nom affiché (français).
    public var displayName: String {
        switch self {
        case .plain: return "Uni"
        case .stripes: return "Rayures"
        case .checks: return "Carreaux"
        case .stars: return "Étoiles"
        case .hearts: return "Cœurs"
        }
    }
}

/// Une pièce portée et sa personnalisation.
public struct AccessorySelection: Codable, Equatable, Hashable, Sendable {
    public var partID: String
    /// Couleurs par slot de matériau : clés `slot_primary`, `slot_secondary`, `slot_accent`, `slot_metal`.
    public var slotColors: [String: PonyColor]
    /// Motif pour les slots tissu (`nil` = uni / non applicable).
    public var pattern: FabricPattern?

    public init(partID: String, slotColors: [String: PonyColor] = [:], pattern: FabricPattern? = nil) {
        self.partID = partID
        self.slotColors = slotColors
        self.pattern = pattern
    }

    private enum CodingKeys: String, CodingKey {
        case partID, slotColors, pattern
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        partID = try c.decode(String.self, forKey: .partID)
        slotColors = (try? c.decodeIfPresent([String: PonyColor].self, forKey: .slotColors)) ?? [:]
        pattern = try? c.decodeIfPresent(FabricPattern.self, forKey: .pattern)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(partID, forKey: .partID)
        try c.encode(slotColors, forKey: .slotColors)
        try c.encodeIfPresent(pattern, forKey: .pattern)
    }
}

/// Coiffure : identifiants des pièces de crins (SPEC §6) + fanons.
public struct HairStyle: Codable, Equatable, Hashable, Sendable {
    /// `mane_natural`, `mane_braided`, `mane_roached`.
    public var mane: String
    /// `forelock_natural`, `forelock_braided`.
    public var forelock: String
    /// `tail_natural`, `tail_braided`.
    public var tail: String
    /// Fanons (`feathers`).
    public var feathers: Bool

    public init(mane: String = "mane_natural", forelock: String = "forelock_natural", tail: String = "tail_natural",
                feathers: Bool = false) {
        self.mane = mane
        self.forelock = forelock
        self.tail = tail
        self.feathers = feathers
    }

    public static let `default` = HairStyle()

    /// Identifiants des pièces de crins à afficher (chaînes vides ignorées).
    public var partIDs: [String] {
        var ids: [String] = []
        for id in [mane, forelock, tail] where !id.isEmpty {
            ids.append(id)
        }
        if feathers { ids.append("feathers") }
        return ids
    }

    private enum CodingKeys: String, CodingKey {
        case mane, forelock, tail, feathers
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        mane = (try? c.decodeIfPresent(String.self, forKey: .mane)) ?? "mane_natural"
        forelock = (try? c.decodeIfPresent(String.self, forKey: .forelock)) ?? "forelock_natural"
        tail = (try? c.decodeIfPresent(String.self, forKey: .tail)) ?? "tail_natural"
        feathers = (try? c.decodeIfPresent(Bool.self, forKey: .feathers)) ?? false
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(mane, forKey: .mane)
        try c.encode(forelock, forKey: .forelock)
        try c.encode(tail, forKey: .tail)
        try c.encode(feathers, forKey: .feathers)
    }
}
