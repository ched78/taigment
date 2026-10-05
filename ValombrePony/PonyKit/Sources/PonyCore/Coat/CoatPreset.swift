import Foundation

/// Préset de robe nommé en français. La liste `all` est GÉNÉRÉE (`CoatPresetsData.swift`) à partir de la table
/// `PRESETS` de `Pipeline/pony/coat_reference.py` pour garantir l'identité avec l'implémentation de référence.
/// Les couleurs sous-jacentes sont des approximations artistiques [A] (cf. `CoatColorTable`).
public struct CoatPreset: Sendable, Equatable, Hashable, Identifiable {
    /// Identifiant stable (ASCII), aussi nom de fichier des aperçus (`Pipeline/build/textures/presets/<id>.png`).
    public let id: String
    /// Nom affiché (français).
    public let name: String
    /// Génotype simplifié et description courte (français).
    public let summary: String
    public let configuration: CoatConfiguration

    public init(id: String, name: String, summary: String, configuration: CoatConfiguration) {
        self.id = id
        self.name = name
        self.summary = summary
        self.configuration = configuration
    }

    /// Préset d'identifiant donné.
    public static func named(_ id: String) -> CoatPreset? {
        all.first { $0.id == id }
    }

    /// Préset par défaut (« bai », identique à `CoatConfiguration.default`).
    public static var defaultPreset: CoatPreset {
        named("bai") ?? CoatPreset(id: "bai", name: "Bai", summary: "", configuration: .default)
    }
}
