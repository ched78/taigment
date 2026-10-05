import Foundation
import os
import RealityKit

/// Couche RealityKit + SwiftUI du poney des « Héritiers de Valombre ».
///
/// - `PonyController` : un poney jouable (runtime `PonyCore`, entités RealityKit, pièces, textures, déplacement).
/// - `PonyPlaygroundView` : terrain de jeu (joystick tactile, clavier, actions).
/// - `PonyStableView` : écurie de personnalisation (robe, crins, morphologie, taille, accessoires).
/// - `PonySceneBuilder` : paddock, lumière, éclairage d'ambiance.
///
/// Aucun clip RealityKit n'est joué (SPEC §0) : la pose est écrite à chaque frame dans
/// `SkeletalPosesComponent` par `PonySystem`.
public enum PonyKit {
    /// Version de la couche PonyKit (indépendante de la version du manifeste).
    public static let version = "1.0.0"

    @MainActor private static var systemsRegistered = false

    /// Enregistre les composants et le système de PonyKit auprès de RealityKit. Idempotent : peut être appelé
    /// plusieurs fois (les vues et `PonyController.init` l'appellent eux-mêmes).
    @MainActor public static func registerSystems() {
        if systemsRegistered { return }
        systemsRegistered = true
        PonyComponent.registerComponent()
        PonyCameraComponent.registerComponent()
        PonySystem.registerSystem()
        PonyLog.info("systèmes enregistrés (PonyKit \(version))")
    }
}

/// Journalisation de PonyKit (`os.Logger`, sous-système `fr.valombre.ponykit`), préfixe `[PonyKit]`.
public enum PonyLog {
    private static let logger = Logger(subsystem: "fr.valombre.ponykit", category: "PonyKit")

    /// Recopie aussi chaque message sur la sortie standard (`print`), pratique hors Xcode. Désactivé par défaut.
    nonisolated(unsafe) public static var mirrorToStandardOutput = false

    public static func info(_ message: String) {
        logger.info("[PonyKit] \(message, privacy: .public)")
        mirror("info", message)
    }

    public static func warning(_ message: String) {
        logger.warning("[PonyKit] \(message, privacy: .public)")
        mirror("attention", message)
    }

    public static func error(_ message: String) {
        logger.error("[PonyKit] \(message, privacy: .public)")
        mirror("erreur", message)
    }

    private static func mirror(_ level: String, _ message: String) {
        if mirrorToStandardOutput {
            print("[PonyKit] \(level) : \(message)")
        }
    }
}
