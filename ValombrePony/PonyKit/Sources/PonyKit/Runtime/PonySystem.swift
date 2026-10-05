import Foundation
import RealityKit

/// Composant posé sur l'entité racine d'un poney : relie l'entité à son `PonyController`.
/// Référence faible : le contrôleur appartient à l'application (vue SwiftUI, modèle de jeu) ; s'il disparaît,
/// l'entité reste figée.
public struct PonyComponent: Component {
    public weak var controller: PonyController?

    public init(controller: PonyController?) {
        self.controller = controller
    }
}

/// Composant posé sur une entité caméra pilotée par un `PonyCameraRig` (suivi 3e personne ou orbite d'écurie).
public struct PonyCameraComponent: Component {
    public weak var rig: PonyCameraRig?

    public init(rig: PonyCameraRig?) {
        self.rig = rig
    }
}

/// Système de mise à jour par frame : fait avancer chaque poney (runtime `PonyCore` → pose, poids, déplacement),
/// puis les caméras (qui suivent la position mise à jour).
///
/// API vérifiées : `System` (`init(scene:)`, `update(context:)`, iOS 15 / macOS 12), `EntityQuery(where: .has(_:))`,
/// `SceneUpdateContext.entities(matching:updatingSystemWhen: .rendering)` (iOS 18 / macOS 15),
/// `SceneUpdateContext.deltaTime` (`TimeInterval`).
/// Aucune dépendance déclarée : l'ordre vis-à-vis des systèmes intégrés n'est pas documenté (realitykit.md §2.5),
/// et sans clip RealityKit en lecture rien n'écrase la pose écrite ici (SPEC §0).
public struct PonySystem: System {
    static let ponyQuery = EntityQuery(where: .has(PonyComponent.self))
    static let cameraQuery = EntityQuery(where: .has(PonyCameraComponent.self))

    @MainActor public init(scene: RealityKit.Scene) {}

    @MainActor public func update(context: SceneUpdateContext) {
        let dt = Float(context.deltaTime)
        for entity in context.entities(matching: PonySystem.ponyQuery, updatingSystemWhen: .rendering) {
            entity.components[PonyComponent.self]?.controller?.tick(deltaTime: dt)
        }
        for entity in context.entities(matching: PonySystem.cameraQuery, updatingSystemWhen: .rendering) {
            entity.components[PonyCameraComponent.self]?.rig?.tick(deltaTime: dt)
        }
    }
}
