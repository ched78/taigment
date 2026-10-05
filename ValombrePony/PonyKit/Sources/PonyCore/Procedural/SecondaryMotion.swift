import Foundation

/// Physique secondaire (SPEC §8.8) : queue (+ chasse-mouches), crinière, toupet, ventre, étriers.
///
/// Chaque os simulé porte une particule à sa pointe. La particule est rappelée par un ressort amorti vers la
/// **direction animée absolue** de l'os (pose animée, avant toute simulation), ancrée à la tête **simulée**
/// (pointe de l'os parent simulé) — formulation de type « Dynamic Bone ». Ce choix [I] évite la composition
/// des rotations le long de la chaîne de queue : avec une cible relative au parent simulé, la chaîne à
/// couplage unidirectionnel amplifiait le balancement de maillon en maillon (vérifié par simulation :
/// pointe de queue jusqu'à 100–180° pour ±2,3° de tangage du tronc).
///
/// Amortissement relatif à la vitesse de la cible (pas de traînée à vitesse constante), contrainte de
/// longueur, écart angulaire maximal par os, mélange vers la verticale (`gravityBlend`). Intégration Euler
/// semi-implicite en sous-pas fixes (≤ 1/120 s). Repère « monde » reconstruit en intégrant la vitesse, le
/// lacet et la vitesse verticale de sortie du runtime, à l'échelle réelle.
struct SecondaryMotion {
    enum Kind {
        case tailDock, tailHair, mane, forelock, belly, stirrup
    }

    struct Bone {
        var joint: Int
        /// Joint enfant dans la chaîne (pointe = sa position), ou −1 (pointe le long de l'axe Y local).
        var child: Int
        var length: Float
        var kind: Kind
        var params: SpringParameters
        /// Part de l'impulsion de chasse-mouches reçue (0 pour tout sauf la queue).
        var swish: Float
    }

    private(set) var bones: [Bone] = []
    private var position: [SIMD3<Float>] = []
    private var velocity: [SIMD3<Float>] = []
    private var previousTarget: [SIMD3<Float>] = []
    private var animatedDirection: [SIMD3<Float>] = []
    private var animatedLength: [Float] = []
    private var initialized = false
    private var swishTimer: Float = 10
    private var worldPosition = SIMD3<Float>(0, 0, 0)
    private var worldYaw: Float = 0

    /// Nombre de vertèbres de la queue (le reste = crins), SPEC §3 : « 4 vertèbres + 6 crins ».
    static let tailVertebrae = 4

    init() {}

    init(rig: ProceduralRig, skeleton: PonySkeleton, settings: ProceduralSettings, random: inout PonyRandom) {
        func boneLength(_ j: Int, child: Int, fallback: Float) -> Float {
            if child >= 0 && child < skeleton.count {
                let l = PonyMath.length(skeleton.restLocal[child].translation)
                if l > 1e-3 { return l }
            }
            return PonyRigDefaults.boneLengths[skeleton.names[j]] ?? fallback
        }
        var list: [Bone] = []
        func addChain(_ joints: [Int], kind: (Int) -> Kind, swish: Bool, fallback: Float) {
            for (i, j) in joints.enumerated() {
                var child = -1
                if i + 1 < joints.count && skeleton.parents[joints[i + 1]] == j {
                    child = joints[i + 1]
                }
                let s: Float = swish ? Float(i + 1) / Float(max(joints.count, 1)) : 0
                let k = kind(i)
                list.append(Bone(joint: j, child: child, length: boneLength(j, child: child, fallback: fallback),
                                 kind: k, params: SecondaryMotion.parameters(for: k, settings: settings), swish: s))
            }
        }
        addChain(rig.tail, kind: { $0 < SecondaryMotion.tailVertebrae ? .tailDock : .tailHair }, swish: true,
                 fallback: 0.1)
        for j in rig.mane {
            list.append(Bone(joint: j, child: -1, length: boneLength(j, child: -1, fallback: 0.12), kind: .mane,
                             params: settings.maneSpring, swish: 0))
        }
        addChain(rig.forelock, kind: { _ in .forelock }, swish: false, fallback: 0.08)
        if rig.belly >= 0 {
            list.append(Bone(joint: rig.belly, child: -1, length: boneLength(rig.belly, child: -1, fallback: 0.12),
                             kind: .belly, params: settings.bellySpring, swish: 0))
        }
        for j in rig.stirrups {
            list.append(Bone(joint: j, child: -1, length: boneLength(j, child: -1, fallback: 0.4), kind: .stirrup,
                             params: settings.stirrupSpring, swish: 0))
        }
        bones = list
        let zero = SIMD3<Float>(0, 0, 0)
        position = [SIMD3<Float>](repeating: zero, count: list.count)
        velocity = [SIMD3<Float>](repeating: zero, count: list.count)
        previousTarget = [SIMD3<Float>](repeating: zero, count: list.count)
        animatedDirection = [SIMD3<Float>](repeating: SIMD3<Float>(0, -1, 0), count: list.count)
        animatedLength = [Float](repeating: 0.1, count: list.count)
        swishTimer = random.range(settings.tailSwishIntervalMin, settings.tailSwishIntervalMax)
    }

    static func parameters(for kind: Kind, settings: ProceduralSettings) -> SpringParameters {
        switch kind {
        case .tailDock: return settings.tailDockSpring
        case .tailHair: return settings.tailSpring
        case .mane: return settings.maneSpring
        case .forelock: return settings.forelockSpring
        case .belly: return settings.bellySpring
        case .stirrup: return settings.stirrupSpring
        }
    }

    /// Réinitialise l'état (téléportation, changement de taille).
    mutating func reset() {
        initialized = false
        worldPosition = SIMD3<Float>(0, 0, 0)
        worldYaw = 0
    }

    /// Met à jour les paramètres de ressort (réglages modifiés à chaud).
    mutating func applySettings(_ settings: ProceduralSettings, rig: ProceduralRig) {
        for i in bones.indices {
            bones[i].params = SecondaryMotion.parameters(for: bones[i].kind, settings: settings)
        }
    }

    /// Pointe de l'os `bone` d'après `model` (enfant de chaîne, sinon le long de l'axe Y local).
    private static func tip(of bone: Bone, pose: [Transform], model: [Transform]) -> SIMD3<Float> {
        if bone.child >= 0 {
            return (model[bone.joint] * pose[bone.child]).translation
        }
        return model[bone.joint].transformPoint(SIMD3<Float>(0, bone.length, 0))
    }

    /// - Parameters:
    ///   - velocity: vitesse de l'entité (m/s réels, axes du poney), `yawRate` (rad/s), `verticalVelocity` (m/s).
    ///   - sizeScale: échelle de l'entité (unités du rig → mètres réels).
    ///   - swishAllowed: chasse-mouches autorisé (arrêt, broutage).
    ///   - model: FK à jour de la pose animée (avant simulation).
    /// - Returns: vrai si un coup de queue a été déclenché pendant cette frame.
    @discardableResult
    mutating func update(dt: Float, velocity rootVelocity: SIMD3<Float>, yawRate: Float, verticalVelocity: Float,
                         sizeScale: Float, settings: ProceduralSettings, swishAllowed: Bool,
                         random: inout PonyRandom, pose: inout [Transform], model: inout [Transform],
                         parents: [Int]) -> Bool {
        if bones.isEmpty || dt <= 0 { return false }
        if dt > 0.25 { initialized = false }

        // Repère « monde » reconstruit.
        let yawQ = Quat(axis: SIMD3<Float>(0, 1, 0), angle: worldYaw)
        worldPosition += yawQ.act(rootVelocity) * dt + SIMD3<Float>(0, verticalVelocity * dt, 0)
        worldYaw = PonyMath.wrapAngle(worldYaw + yawRate * dt)
        let frameRotation = Quat(axis: SIMD3<Float>(0, 1, 0), angle: worldYaw)
        let inverseFrame = frameRotation.inverse
        let s = max(sizeScale, 0.01)

        // Directions animées (espace modèle), avant toute modification de la pose.
        for i in bones.indices {
            let b = bones[i]
            let head = model[b.joint].translation
            let d = SecondaryMotion.tip(of: b, pose: pose, model: model) - head
            let l = PonyMath.length(d)
            animatedLength[i] = max(l, 1e-4)
            animatedDirection[i] = l > 1e-6 ? d / l : SIMD3<Float>(0, -1, 0)
        }

        // Chasse-mouches.
        var swished = false
        var swishImpulse = SIMD3<Float>(0, 0, 0)
        swishTimer -= dt
        if swishTimer <= 0 {
            swishTimer = random.range(settings.tailSwishIntervalMin, settings.tailSwishIntervalMax)
            if swishAllowed {
                let side: Float = random.chance(0.5) ? 1 : -1
                swishImpulse = frameRotation.act(SIMD3<Float>(side, 0, 0)) * settings.tailSwishStrength * s
                swished = true
            }
        }

        let steps = max(1, min(8, Int((dt * 120).rounded(.up))))
        let h = dt / Float(steps)
        let down = SIMD3<Float>(0, -1, 0)

        for i in bones.indices {
            let bone = bones[i]
            let j = bone.joint
            // Tête et direction courantes, héritées du parent simulé.
            PoseEditing.refresh(j, pose: pose, model: &model, parents: parents)
            let headModel = model[j].translation
            let currentDirModel = PonyMath.normalize(SecondaryMotion.tip(of: bone, pose: pose, model: model) - headModel,
                                                     fallback: animatedDirection[i])
            let headWorld = worldPosition + frameRotation.act(headModel * s)
            let length = animatedLength[i] * s
            let animDirWorld = frameRotation.act(animatedDirection[i])
            let targetDir = PonyMath.normalize(PonyMath.lerp(animDirWorld, down, bone.params.gravityBlend),
                                               fallback: animDirWorld)
            let target = headWorld + targetDir * length

            if !initialized {
                position[i] = target
                velocity[i] = SIMD3<Float>(0, 0, 0)
                previousTarget[i] = target
            }
            let targetVelocity = (target - previousTarget[i]) / dt
            if bone.swish > 0 && swished {
                velocity[i] += swishImpulse * bone.swish
            }
            let k = bone.params.stiffness
            let c = bone.params.damping
            var p = position[i]
            var v = velocity[i]
            for _ in 0..<steps {
                let a = (target - p) * k - (v - targetVelocity) * c
                v += a * h
                p += v * h
                p = headWorld + PonyMath.normalize(p - headWorld, fallback: targetDir) * length
            }
            // Limite angulaire autour de la direction cible.
            var simDir = PonyMath.normalize(p - headWorld, fallback: targetDir)
            let limited = Quat(from: targetDir, to: simDir).clampedAngle(bone.params.maxAngle)
            simDir = limited.act(targetDir)
            p = headWorld + simDir * length
            // Vitesse : on retire la composante radiale (le long de l'os).
            v = v - simDir * PonyMath.dot(v, simDir)
            position[i] = p
            velocity[i] = v
            previousTarget[i] = target

            let simModel = inverseFrame.act(simDir)
            let delta = Quat(from: currentDirModel, to: simModel)
            PoseEditing.rotateInModelSpace(j, delta, pose: &pose, model: &model, parents: parents)
        }
        initialized = true
        return swished
    }
}
