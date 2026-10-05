import Foundation
import PonyCore
import RealityKit

/// Caméra de jeu : suivi à la 3e personne d'un poney (lissage, orbite manuelle, zoom) ou orbite d'écurie autour
/// d'un point. Mise à jour par `PonySystem` (après les poneys).
///
/// API vérifiées : `PerspectiveCameraComponent(near:far:fieldOfViewInDegrees:)` (iOS 13 / macOS 10.15),
/// `look(at:from:upVector:relativeTo:forward:)` (iOS 18 / macOS 15 ; `forward` passé explicitement pour lever
/// l'ambiguïté avec la surcharge iOS 13). Avec `RealityView` + `content.camera = .virtual`, l'entité portant un
/// `PerspectiveCameraComponent` sert de point de vue (modèle de l'exemple Apple « Pyro Panda », realitykit.md §6.2)
/// [I : non testé ici].
@MainActor
public final class PonyCameraRig {
    public enum Mode {
        /// Suivi derrière le poney.
        case follow
        /// Orbite autour d'un point fixe (écurie).
        case orbit(center: SIMD3<Float>)
    }

    public let entity: Entity
    public private(set) var mode: Mode = .orbit(center: SIMD3<Float>(0, 0.9, 0))
    public private(set) weak var target: PonyController?

    // Réglages du suivi (mètres pour un poney de 1,30 m ; multipliés par l'échelle du poney) [A].
    public var followDistance: Float = 4.2
    public var followHeight: Float = 1.25
    public var lookHeight: Float = 1.0
    /// Demi-vie du lissage de la position de la caméra (s). Un retard de v·demi-vie/ln 2 en résulte
    /// (≈ 1,4 m au galop de course pour 0,12 s) : sensation de vitesse [A].
    public var positionHalfLife: Float = 0.12
    /// Demi-vie du lissage du point visé (s) : court, pour garder le poney centré.
    public var focusHalfLife: Float = 0.04
    /// Demi-vie du recentrage derrière le poney (s).
    public var yawHalfLife: Float = 0.45
    /// Délai avant le recentrage automatique après une orbite manuelle (s).
    public var recenterDelay: Float = 2.5

    // Réglages de l'orbite.
    public var orbitYaw: Float = 0.6
    public var orbitPitch: Float = 0.18
    public var orbitDistance: Float = 3.6
    /// Rotation automatique (rad/s) en mode orbite ; 0 = arrêt.
    public var autoRotateSpeed: Float = 0
    /// Si défini, ce poney regarde la caméra (sa cible de regard est mise à jour à chaque frame).
    public weak var lookingPony: PonyController? {
        didSet {
            if lookingPony == nil { oldValue?.lookTarget = nil }
        }
    }

    // Bornes communes.
    public var minPitch: Float = -0.05
    public var maxPitch: Float = 1.2
    public var minZoom: Float = 0.45
    public var maxZoom: Float = 2.5

    // État.
    private var zoom: Float = 1
    private var userYaw: Float = 0
    private var userPitch: Float = 0.12
    private var smoothedYaw: Float = 0
    private var smoothedFocus = SIMD3<Float>(0, 1, 0)
    private var smoothedPosition = SIMD3<Float>(0, 2, 4)
    private var sinceUserInput: Float = 100
    private var initialized = false

    public init(fieldOfViewInDegrees: Float = 50) {
        entity = Entity()
        entity.name = "PonyCamera"
        entity.components.set(PerspectiveCameraComponent(near: 0.05, far: 400, fieldOfViewInDegrees: fieldOfViewInDegrees))
        entity.components.set(PonyCameraComponent(rig: self))
    }

    /// Suivi d'un poney (3e personne).
    public func follow(_ controller: PonyController) {
        target = controller
        mode = .follow
        initialized = false
    }

    /// Orbite autour d'un point (monde).
    public func orbit(around center: SIMD3<Float>, distance: Float? = nil) {
        if case .orbit = mode {
            // Déjà en orbite : le centre change en douceur (lissage conservé).
        } else {
            initialized = false
        }
        mode = .orbit(center: center)
        if let d = distance { orbitDistance = d }
    }

    /// Orbite manuelle (glisser) : `dx`, `dy` en radians.
    public func rotate(yaw dx: Float, pitch dy: Float) {
        switch mode {
        case .follow:
            userYaw = PonyMath.wrapAngle(userYaw + dx)
            userPitch = PonyMath.clamp(userPitch + dy, minPitch, maxPitch)
        case .orbit:
            orbitYaw = PonyMath.wrapAngle(orbitYaw + dx)
            orbitPitch = PonyMath.clamp(orbitPitch + dy, minPitch, maxPitch)
        }
        sinceUserInput = 0
    }

    /// Zoom multiplicatif (pincement) : < 1 rapproche.
    public func zoom(by factor: Float) {
        guard factor.isFinite, factor > 0 else { return }
        zoom = PonyMath.clamp(zoom * factor, minZoom, maxZoom)
    }

    /// Replace la caméra derrière le poney.
    public func recenter() {
        userYaw = 0
        userPitch = 0.12
        zoom = 1
    }

    /// Mise à jour par frame (appelée par `PonySystem`).
    public func tick(deltaTime: Float) {
        let dt = PonyMath.clamp(deltaTime.isFinite ? deltaTime : 0, 0, 0.1)
        sinceUserInput += dt
        let focus: SIMD3<Float>
        var desired: SIMD3<Float>
        switch mode {
        case .follow:
            guard let pony = target else { return }
            let s = pony.configuration.entityScale
            let world = pony.visualRoot.position(relativeTo: nil)
            let heading = PonyCameraRig.yaw(of: pony.root.orientation(relativeTo: nil))
            // Recentrage progressif derrière le poney quand le joueur ne touche plus à la caméra.
            if sinceUserInput > recenterDelay && pony.displaySpeed > 0.3 {
                userYaw = PonyMath.damp(userYaw, toward: 0, halfLife: yawHalfLife * 2, deltaTime: dt)
            }
            let targetYaw = heading + userYaw
            if !initialized {
                smoothedYaw = targetYaw
            } else {
                let diff = PonyMath.wrapAngle(targetYaw - smoothedYaw)
                smoothedYaw = PonyMath.wrapAngle(smoothedYaw + diff * PonyMath.dampFactor(halfLife: yawHalfLife,
                                                                                           deltaTime: dt))
            }
            focus = world + SIMD3<Float>(0, lookHeight * s, 0)
            let dist = followDistance * s * zoom
            let pitch = userPitch
            let back = SIMD3<Float>(sin(smoothedYaw), 0, cos(smoothedYaw))   // opposé de l'avant (−Z tourné)
            desired = focus + back * (dist * cos(pitch)) + SIMD3<Float>(0, (followHeight - lookHeight) * s
                                                                             + dist * sin(pitch), 0)
        case .orbit(let center):
            if autoRotateSpeed != 0 && sinceUserInput > 1.5 {
                orbitYaw = PonyMath.wrapAngle(orbitYaw + autoRotateSpeed * dt)
            }
            focus = center
            let dist = orbitDistance * zoom
            let back = SIMD3<Float>(sin(orbitYaw), 0, cos(orbitYaw))
            desired = center + back * (dist * cos(orbitPitch)) + SIMD3<Float>(0, dist * sin(orbitPitch), 0)
        }
        // Caméra jamais sous le sol (y = 0) [I : sol plat].
        desired.y = max(desired.y, 0.15)
        if !initialized {
            smoothedFocus = focus
            smoothedPosition = desired
            initialized = true
        } else {
            let kf = PonyMath.dampFactor(halfLife: focusHalfLife, deltaTime: dt)
            let kp = PonyMath.dampFactor(halfLife: positionHalfLife, deltaTime: dt)
            smoothedFocus += (focus - smoothedFocus) * kf
            smoothedPosition += (desired - smoothedPosition) * kp
        }
        entity.look(at: smoothedFocus, from: smoothedPosition, upVector: SIMD3<Float>(0, 1, 0), relativeTo: nil,
                    forward: .negativeZ)
        lookingPony?.lookTarget = smoothedPosition
    }

    /// Lacet (rad, autour de +Y) d'une orientation : 0 = regarde vers −Z, positif = vers la gauche (−X).
    static func yaw(of q: simd_quatf) -> Float {
        let f = q.act(SIMD3<Float>(0, 0, -1))
        return atan2(-f.x, -f.z)
    }
}
