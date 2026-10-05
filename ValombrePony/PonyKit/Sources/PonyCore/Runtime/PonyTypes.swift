import Foundation

/// Entrées du joueur pour une frame.
public struct PonyInput: Sendable {
    /// x = tourner (+ = droite), y = avancer (+) / reculer (−) ; chaque composante dans [−1, 1].
    public var move: SIMD2<Float>
    /// Allonger l'allure (galop de course).
    public var sprint: Bool
    /// Appui sur « sauter » pendant cette frame (front montant).
    public var jumpPressed: Bool
    /// Action demandée pendant cette frame (une seule fois, pas maintenue).
    public var action: PonyAction?

    public init() {
        move = SIMD2<Float>(0, 0)
        sprint = false
        jumpPressed = false
        action = nil
    }

    public init(move: SIMD2<Float>, sprint: Bool = false, jumpPressed: Bool = false, action: PonyAction? = nil) {
        self.move = move
        self.sprint = sprint
        self.jumpPressed = jumpPressed
        self.action = action
    }
}

/// Comportements déclenchables (SPEC §7).
public enum PonyAction: String, Codable, CaseIterable, Sendable {
    case graze, rear, headShake, neigh, paw, lieDown, getUp, roll, bodyShake
}

/// Allure courante de la machine d'états de locomotion.
public enum PonyGait: String, Codable, CaseIterable, Sendable {
    case idle, walk, trot, canter, gallop, back, turnInPlace
}

/// Humeur des oreilles (couche procédurale, SPEC §8.6).
public enum EarMood: String, Codable, CaseIterable, Sendable {
    /// Les deux oreilles en avant, orientées vers la cible du regard.
    case attentive
    /// Pivotements indépendants aléatoires (écoute de l'environnement).
    case independent
    /// Couchées en arrière (menace / mécontentement).
    case pinned
    /// Détendues, tombant sur le côté (repos).
    case relaxed
}

/// Évènement d'animation (pose de sabot, appel du saut, mastication, …).
public struct PonyEvent: Sendable, Equatable {
    public var name: String
    /// Temps du runtime (s, depuis sa création) à la fin de la frame où l'évènement a été franchi.
    public var time: Double

    public init(name: String, time: Double) {
        self.name = name
        self.time = time
    }
}

/// Résultat d'une frame du runtime.
public struct PonyFrame: Sendable {
    /// Pose locale (parent → joint) de chaque joint, dans l'ordre du manifeste.
    public var localPose: [Transform]
    /// Poids des blend shapes par nom (morphologie + expressions), tous dans [0, 1].
    public var blendWeights: [String: Float]
    /// Vitesse de déplacement souhaitée de l'entité (m/s réels, axes du poney : avant = −Z). Horizontale.
    public var rootVelocity: SIMD3<Float>
    /// Vitesse de lacet souhaitée (rad/s) autour de +Y : positif = tourne à gauche.
    public var rootYawRate: Float
    public var events: [PonyEvent]
    public var gait: PonyGait
    /// Vitesse verticale souhaitée de l'entité (m/s, +Y) : non nulle seulement pendant le vol d'un saut
    /// (profil balistique v0 − g·t calculé par le runtime). Ajout au contrat initial, cf. Docs/RUNTIME.md.
    public var verticalVelocity: Float
    /// Vrai pendant la phase aérienne d'un saut.
    public var isAirborne: Bool
    /// Comportement en cours (couche de base, sinon couche masquée), `nil` en locomotion simple.
    public var action: PonyAction?

    public init(localPose: [Transform], blendWeights: [String: Float], rootVelocity: SIMD3<Float>,
                rootYawRate: Float, events: [PonyEvent], gait: PonyGait, verticalVelocity: Float = 0,
                isAirborne: Bool = false, action: PonyAction? = nil) {
        self.localPose = localPose
        self.blendWeights = blendWeights
        self.rootVelocity = rootVelocity
        self.rootYawRate = rootYawRate
        self.events = events
        self.gait = gait
        self.verticalVelocity = verticalVelocity
        self.isAirborne = isAirborne
        self.action = action
    }
}
