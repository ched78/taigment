import Foundation
import Observation
import PonyCore
import SwiftUI
#if os(macOS)
import AppKit
#endif

/// Entrées continues du joueur (clavier + joystick tactile), lues à chaque frame par `PonyController`
/// (`controller.inputSource = state`).
///
/// Clavier (SwiftUI `onKeyPress(phases:action:)`, iOS 17 / macOS 14, phases `.down`, `.repeat`, `.up`) :
/// - avancer : Z / W / ↑ ; reculer : S / ↓ ; tourner : Q / A / ← et D / → (AZERTY ZQSD et QWERTY WASD ensemble,
///   par caractère produit) ;
/// - Maj : galop de course (macOS : `NSEvent.modifierFlags`, lu à chaque frame ; iOS : modificateurs des
///   évènements clavier [I : Maj seule ne produit pas d'évènement `onKeyPress`]) ;
/// - Espace : saut ; B brouter, H hennir, C se cabrer, T secouer la tête, G gratter, L se coucher / se relever,
///   R se rouler, E s'ébrouer.
/// Les commandes ponctuelles (saut, actions) sont transmises au contrôleur via `onCommand`.
///
/// `@Observable` pour que l'interface suive `sprintLatched` (bouton « Galop ») ; les états à haute fréquence
/// (joystick, touches) sont exclus de l'observation (aucune invalidation de vue à chaque mouvement).
@MainActor
@Observable
public final class PonyInputState {
    public enum Command: Equatable {
        case jump
        case action(PonyAction)
        case toggleLying
    }

    /// Joystick tactile : x = tourner (+ droite), y = avancer (+), composantes dans [−1, 1].
    @ObservationIgnored public var joystick = SIMD2<Float>(0, 0)
    /// Galop verrouillé (bouton tactile) — observé par l'interface.
    public var sprintLatched = false
    /// Commandes ponctuelles (saut, actions).
    @ObservationIgnored public var onCommand: ((Command) -> Void)?

    @ObservationIgnored private var forwardKeys = Set<String>()
    @ObservationIgnored private var backKeys = Set<String>()
    @ObservationIgnored private var leftKeys = Set<String>()
    @ObservationIgnored private var rightKeys = Set<String>()
    @ObservationIgnored private var shiftFromEvents = false

    public init() {}

    /// Direction combinée (clavier + joystick), bornée à [−1, 1].
    public var move: SIMD2<Float> {
        var x = joystick.x
        var y = joystick.y
        if !forwardKeys.isEmpty { y += 1 }
        if !backKeys.isEmpty { y -= 1 }
        if !rightKeys.isEmpty { x += 1 }
        if !leftKeys.isEmpty { x -= 1 }
        return SIMD2<Float>(min(max(x, -1), 1), min(max(y, -1), 1))
    }

    public var sprint: Bool {
        if sprintLatched { return true }
        #if os(macOS)
        if NSEvent.modifierFlags.contains(.shift) { return true }
        #endif
        return shiftFromEvents
    }

    /// Relâche toutes les touches (perte de focus).
    public func releaseAll() {
        forwardKeys.removeAll()
        backKeys.removeAll()
        leftKeys.removeAll()
        rightKeys.removeAll()
        shiftFromEvents = false
    }

    /// Traitement d'un évènement clavier SwiftUI. Renvoie `.handled` pour les touches du jeu.
    public func handle(_ press: KeyPress) -> KeyPress.Result {
        shiftFromEvents = press.modifiers.contains(.shift)
        let isDown = press.phase == .down || press.phase == .repeat
        let isUp = press.phase == .up
        let id: String
        if press.key == .upArrow {
            id = "↑"
        } else if press.key == .downArrow {
            id = "↓"
        } else if press.key == .leftArrow {
            id = "←"
        } else if press.key == .rightArrow {
            id = "→"
        } else if press.key == .space {
            id = " "
        } else {
            id = String(press.key.character).lowercased()
        }

        switch id {
        case "z", "w", "↑":
            update(&forwardKeys, id, down: isDown, up: isUp)
        case "s", "↓":
            update(&backKeys, id, down: isDown, up: isUp)
        case "q", "a", "←":
            update(&leftKeys, id, down: isDown, up: isUp)
        case "d", "→":
            update(&rightKeys, id, down: isDown, up: isUp)
        case " ":
            if press.phase == .down { onCommand?(.jump) }
        case "b":
            if press.phase == .down { onCommand?(.action(.graze)) }
        case "h":
            if press.phase == .down { onCommand?(.action(.neigh)) }
        case "c":
            if press.phase == .down { onCommand?(.action(.rear)) }
        case "t":
            if press.phase == .down { onCommand?(.action(.headShake)) }
        case "g":
            if press.phase == .down { onCommand?(.action(.paw)) }
        case "l":
            if press.phase == .down { onCommand?(.toggleLying) }
        case "r":
            if press.phase == .down { onCommand?(.action(.roll)) }
        case "e":
            if press.phase == .down { onCommand?(.action(.bodyShake)) }
        default:
            return .ignored
        }
        return .handled
    }

    private func update(_ set: inout Set<String>, _ id: String, down: Bool, up: Bool) {
        if down { set.insert(id) }
        if up { set.remove(id) }
    }
}

extension PonyController {
    /// Branche une source d'entrées : déplacement continu + commandes ponctuelles.
    public func connect(_ state: PonyInputState) {
        inputSource = state
        state.onCommand = { [weak self] command in
            guard let self = self else { return }
            switch command {
            case .jump: self.jump()
            case .action(let a): self.perform(a)
            case .toggleLying: self.toggleLying()
            }
        }
    }
}
