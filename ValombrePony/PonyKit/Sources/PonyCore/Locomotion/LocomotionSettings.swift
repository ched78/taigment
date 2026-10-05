import Foundation

/// Réglages de la machine d'états de locomotion. Vitesses en m/s pour le gabarit de référence (1,30 m) :
/// le runtime les met à l'échelle de la taille réelle (similitude de Froude, cf. Docs/RUNTIME.md).
///
/// Sources : seuils pas↔trot d'après le nombre de Froude ≈ 0,35 (Griffin et al. 2004, gaits.md §1.9) [R/D] ;
/// autres seuils, accélérations, rayons de virage : choix de jeu [I] ; tolérance de cadence ±18 %
/// (heuristique de métier ±15–20 %, gaits.md §5.3) [U].
public struct LocomotionSettings: Sendable, Equatable {
    /// Zone morte du joystick (|x|, |y| en dessous = 0).
    public var stickDeadZone: Float = 0.12
    /// Écart maximal de cadence de lecture autour de la vitesse de référence d'un clip (±).
    public var playbackTolerance: Float = 0.18
    /// Vitesse commandée pour y = 1 sans sprint (galop de travail).
    public var cruiseSpeed: Float = 4.8
    /// Vitesse commandée pour y = 1 avec sprint (galop de course).
    public var sprintSpeed: Float = 8.0

    // Seuils d'hystérésis sur la vitesse commandée (monter / redescendre d'allure).
    public var walkUp: Float = 0.15
    public var walkDown: Float = 0.06
    public var trotUp: Float = 1.85
    public var trotDown: Float = 1.55
    public var canterUp: Float = 4.0
    public var canterDown: Float = 3.5
    public var gallopUp: Float = 6.4
    public var gallopDown: Float = 5.6

    // Accélérations (m/s²) par allure ; la décélération vaut accélération × `decelerationFactor`.
    public var walkAcceleration: Float = 1.2
    public var trotAcceleration: Float = 2.0
    public var canterAcceleration: Float = 2.5
    public var gallopAcceleration: Float = 3.0
    public var backAcceleration: Float = 1.0
    public var decelerationFactor: Float = 1.5

    // Rayons de virage minimaux (m) par allure : lacet max = vitesse / rayon.
    public var walkMinTurnRadius: Float = 1.2
    public var trotMinTurnRadius: Float = 3.0
    public var canterMinTurnRadius: Float = 5.0
    public var gallopMinTurnRadius: Float = 9.0
    public var backMinTurnRadius: Float = 1.0
    /// Vitesse plancher utilisée pour le lacet à très basse vitesse (évite un virage bloqué au départ).
    public var minTurnSpeed: Float = 0.5
    /// Lacet maximal absolu (rad/s).
    public var maxYawRate: Float = 1.5
    /// Accélération angulaire du lacet (rad/s²).
    public var yawAcceleration: Float = 4.0

    /// Durée des fondus entre allures (s).
    public var gaitFadeDuration: Float = 0.3
    /// Temps minimal passé dans une allure avant d'en changer (anti-oscillation).
    public var minGaitDuration: Float = 0.35
    /// Durée du fondu de changement de pied au galop (s).
    public var leadChangeFadeDuration: Float = 0.25
    /// Durée pendant laquelle le virage doit contredire le pied avant un changement de pied (s).
    public var leadChangeDelay: Float = 0.6

    // Variante de repos `idle_rest_hind` [A].
    public var idleRestDelayMin: Float = 12
    public var idleRestDelayMax: Float = 30
    public var idleRestDurationMin: Float = 8
    public var idleRestDurationMax: Float = 20
    public var restFadeDuration: Float = 1.0

    // Inclinaison et incurvation en virage.
    /// Inclinaison maximale du tronc (rad) ; θ = atan(v·ω/g) [D, gaits.md §5.3], bornée [A].
    public var maxLeanAngle: Float = 0.2
    public var leanHalfLife: Float = 0.15
    /// Incurvation maximale de l'encolure vers l'intérieur du virage (rad, total) [A].
    public var maxNeckBend: Float = 0.2

    public init() {}
}

/// Réglages du saut (SPEC §7, gaits.md §3 : estimations physiques [D] et chorégraphie [U]).
public struct JumpSettings: Sendable, Equatable {
    /// Hauteur de l'obstacle à franchir (m réels).
    public var obstacleHeight: Float = 0.7
    /// Hauteur des sabots repliés au-dessus du plan de la racine pendant `jump_air`, gabarit 1,30 m [A].
    public var tuckClearance: Float = 0.35
    /// Marge de franchissement (m).
    public var clearanceMargin: Float = 0.05
    /// Montée minimale de l'entité (m).
    public var minimumApex: Float = 0.15
    /// Si vrai, `jump_air` est tenu jusqu'à `notifyLanded()` (avec ce délai de sécurité après le vol calculé).
    public var externalLandingTimeout: Float = 2.0
    public var takeoffFade: Float = 0.12
    public var airFade: Float = 0.08
    public var landFade: Float = 0.08
    public var recoverFade: Float = 0.25
    /// Autoriser le saut depuis le trot (sinon galop seulement).
    public var allowFromTrot: Bool = true

    public init() {}

    /// Montée de l'entité au sommet du vol (m) pour une taille relative `sizeScale` (= WH / 1,30).
    public func apexHeight(sizeScale: Float) -> Float {
        return max(minimumApex, obstacleHeight - tuckClearance * sizeScale + clearanceMargin)
    }

    /// Vitesse verticale d'appel v0 = √(2·g·h).
    public func takeoffVelocity(sizeScale: Float) -> Float {
        return (2 * PonyMath.gravity * apexHeight(sizeScale: sizeScale)).squareRoot()
    }

    /// Temps de vol balistique t = 2·v0/g.
    public func flightTime(sizeScale: Float) -> Float {
        return 2 * takeoffVelocity(sizeScale: sizeScale) / PonyMath.gravity
    }
}

/// Réglages des comportements.
public struct BehaviorSettings: Sendable, Equatable {
    /// Délai pendant lequel une action demandée en mouvement attend l'arrêt du poney (s).
    public var pendingActionTimeout: Float = 2.0
    /// Durée du grattage du sol (`paw`, clip en boucle) avant retour automatique (s) [A].
    public var pawDuration: Float = 4.8
    /// Fondu d'entrée/sortie des comportements du corps entier (s).
    public var actionFade: Float = 0.25
    /// Fondus des couches masquées (`head_shake`, `neigh`).
    public var overlayFadeIn: Float = 0.15
    public var overlayFadeOut: Float = 0.25

    public init() {}
}
