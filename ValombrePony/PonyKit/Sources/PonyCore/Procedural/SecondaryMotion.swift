import Foundation

/// Physique secondaire (SPEC §8.8) : queue (+ chasse-mouches), crinière, toupet, ventre, étriers.
///
/// Chaque os simulé porte une particule à sa pointe, rappelée vers la pointe animée par un ressort amorti
/// (amortissement relatif à la vitesse de la cible : pas de traînée à vitesse constante), contrainte à la
/// longueur de l'os et à un écart angulaire maximal. Intégration Euler semi-implicite en sous-pas fixes
/// (≤ 1/120 s) : stable pour les raideurs utilisées (ω·h ≤ 0,15). La simulation se fait dans un repère
/// « monde » reconstruit en intégrant la vitesse et le lacet de sortie du runtime, à l'échelle réelle.
struct SecondaryMotion {
    struct Bone {
        var joint: Int
        /// Joint enfant dans la chaîne (pointe = sa position), ou −1 (pointe le long de l'axe Y local).
        var child: Int
        var length: Float
        var params: SpringParameters
        /// Part de l'impulsion de chasse-mouches reçue (0 pour tout sauf la queue).
        var swish: Float
    }

    private(set) var bones: [Bone] = []
    private var position: [SIMD3<Float>] = []
    private var velocity: [SIMD3<Float>] = []
    private var previousTarget: [SIMD3<Float>] = []
    private var initialized = false
    private var swishTimer: Float = 10
    private var worldPosition = SIMD3<Float>(0, 0, 0)
    private var worldYaw: Float = 0

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
        func addChain(_ joints: [Int], params: SpringParameters, swish: Bool, fallback: Float) {
            for (i, j) in joints.enumerated() {
                var child = -1
                if i + 1 < joints.count && skeleton.parents[joints[i + 1]] == j {
                    child = joints[i + 1]
                }
                let s: Float = swish ? Float(i + 1) / Float(max(joints.count, 1)) : 0
                list.append(Bone(joint: j, child: child, length: boneLength(j, child: child, fallback: fallback),
                                 params: params, swish: s))
            }
        }
        addChain(rig.tail, params: settings.tailSpring, swish: true, fallback: 0.1)
        for j in rig.mane {
            list.append(Bone(joint: j, child: -1, length: boneLength(j, child: -1, fallback: 0.12),
                             params: settings.maneSpring, swish: 0))
        }
        addChain(rig.forelock, params: settings.forelockSpring, swish: false, fallback: 0.08)
        if rig.belly >= 0 {
            list.append(Bone(joint: rig.belly, child: -1, length: boneLength(rig.belly, child: -1, fallback: 0.12),
                             params: settings.bellySpring, swish: 0))
        }
        for j in rig.stirrups {
            list.append(Bone(joint: j, child: -1, length: boneLength(j, child: -1, fallback: 0.4),
                             params: settings.stirrupSpring, swish: 0))
        }
        bones = list
        position = [SIMD3<Float>](repeating: SIMD3<Float>(0, 0, 0), count: list.count)
        velocity = position
        previousTarget = position
        swishTimer = random.range(settings.tailSwishIntervalMin, settings.tailSwishIntervalMax)
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
            let j = bones[i].joint
            if rig.tail.contains(j) {
                bones[i].params = settings.tailSpring
            } else if rig.mane.contains(j) {
                bones[i].params = settings.maneSpring
            } else if rig.forelock.contains(j) {
                bones[i].params = settings.forelockSpring
            } else if j == rig.belly {
                bones[i].params = settings.bellySpring
            } else {
                bones[i].params = settings.stirrupSpring
            }
        }
    }

    /// - Parameters:
    ///   - velocity: vitesse de l'entité (m/s réels, axes du poney), `yawRate` (rad/s), `verticalVelocity` (m/s).
    ///   - sizeScale: échelle de l'entité (unités du rig → mètres réels).
    ///   - swishAllowed: chasse-mouches autorisé (arrêt, broutage).
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
            PoseEditing.refresh(j, pose: pose, model: &model, parents: parents)
            let headModel = model[j].translation
            var tipModel: SIMD3<Float>
            if bone.child >= 0 {
                tipModel = (model[j] * pose[bone.child]).translation
            } else {
                tipModel = model[j].transformPoint(SIMD3<Float>(0, bone.length, 0))
            }
            let headWorld = worldPosition + frameRotation.act(headModel * s)
            let tipWorld = worldPosition + frameRotation.act(tipModel * s)
            let animDir = PonyMath.normalize(tipWorld - headWorld)
            let length = max(PonyMath.length(tipWorld - headWorld), 1e-4)
            let targetDir = PonyMath.normalize(PonyMath.lerp(animDir, down, bone.params.gravityBlend), fallback: animDir)
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

            let animModel = inverseFrame.act(animDir)
            let simModel = inverseFrame.act(simDir)
            let delta = Quat(from: animModel, to: simModel)
            PoseEditing.rotateInModelSpace(j, delta, pose: &pose, model: &model, parents: parents)
        }
        initialized = true
        return swished
    }
}

/// Adaptation au sol optionnelle (`groundHeightProvider`) : abaisse le tronc du plus petit décalage des
/// quatre membres puis corrige chaque membre en appui par IK à deux os (haut du membre → milieu → canon).
/// Choix d'ingénierie [I] : le tangage du tronc selon la pente n'est pas géré.
struct GroundAdaptation {
    private var bodyOffset = CriticalSpring()
    private var legOffsets: [CriticalSpring] = []
    private var restHoofHeights: [Float] = []
    private var raw: [Float] = []
    private var stance: [Float] = []

    init() {}

    init(rig: ProceduralRig, skeleton: PonySkeleton) {
        let n = rig.legs.count
        legOffsets = [CriticalSpring](repeating: CriticalSpring(), count: n)
        restHoofHeights = rig.legs.map { skeleton.bindModel[$0.hoof].translation.y }
        raw = [Float](repeating: 0, count: n)
        stance = [Float](repeating: 0, count: n)
    }

    mutating func reset() {
        bodyOffset.reset(to: 0)
        for i in legOffsets.indices {
            legOffsets[i].reset(to: 0)
        }
    }

    /// `model` doit être à jour (FK) ; il est recalculé entièrement en sortie.
    mutating func apply(provider: (SIMD3<Float>) -> Float?, dt: Float, settings: ProceduralSettings,
                        rig: ProceduralRig, skeleton: PonySkeleton, pose: inout [Transform],
                        model: inout [Transform]) {
        let n = rig.legs.count
        if n == 0 { return }
        let limit = settings.groundMaxOffset
        var minimum: Float = .greatestFiniteMagnitude
        for i in 0..<n {
            let leg = rig.legs[i]
            let hoof = model[leg.hoof].translation
            let ground = provider(hoof) ?? 0
            raw[i] = PonyMath.clamp(PonyMath.finite(ground), -limit, limit)
            let lift = hoof.y - restHoofHeights[i]
            stance[i] = 1 - PonyMath.smoothstep(0.03, 0.12, lift)
            minimum = min(minimum, raw[i])
        }
        bodyOffset.update(target: minimum, halfLife: settings.groundHalfLife, deltaTime: dt)
        let parents = skeleton.parents
        if rig.body >= 0 && abs(bodyOffset.value) > 1e-5 {
            var m = model[rig.body]
            m.translation.y += bodyOffset.value
            PoseEditing.setModel(rig.body, m, pose: &pose, model: &model, parents: parents)
            skeleton.computeModel(local: pose, into: &model)
        }
        var changed = false
        for i in 0..<n {
            legOffsets[i].update(target: (raw[i] - bodyOffset.value) * stance[i], halfLife: settings.groundHalfLife,
                                 deltaTime: dt)
            let d = legOffsets[i].value
            if abs(d) < 1e-4 { continue }
            let leg = rig.legs[i]
            let a = model[leg.upper].translation
            let b = model[leg.mid].translation
            let c = model[leg.lower].translation
            let t = c + SIMD3<Float>(0, d, 0)
            if let solved = GroundAdaptation.twoBoneIK(a: a, b: b, c: c, target: t,
                                                       aModel: model[leg.upper].rotation,
                                                       bModel: model[leg.mid].rotation,
                                                       aLocal: pose[leg.upper].rotation,
                                                       bLocal: pose[leg.mid].rotation) {
                pose[leg.upper].rotation = solved.0
                pose[leg.mid].rotation = solved.1
                changed = true
            }
        }
        if changed {
            skeleton.computeModel(local: pose, into: &model)
        }
    }

    /// IK analytique à deux os (forme de D. Holden) en espace modèle : renvoie les nouvelles rotations
    /// locales du premier et du deuxième os, ou `nil` si la chaîne est dégénérée (membre tendu).
    static func twoBoneIK(a: SIMD3<Float>, b: SIMD3<Float>, c: SIMD3<Float>, target t: SIMD3<Float>,
                          aModel: Quat, bModel: Quat, aLocal: Quat, bLocal: Quat) -> (Quat, Quat)? {
        let eps: Float = 1e-4
        let lab = PonyMath.length(b - a)
        let lcb = PonyMath.length(b - c)
        if lab < eps || lcb < eps { return nil }
        let lat = PonyMath.clamp(PonyMath.length(t - a), eps, lab + lcb - eps)
        let ac = PonyMath.normalize(c - a)
        let ab = PonyMath.normalize(b - a)
        let ba = PonyMath.normalize(a - b)
        let bc = PonyMath.normalize(c - b)
        let at = PonyMath.normalize(t - a)
        let acAb0 = acos(PonyMath.clamp(PonyMath.dot(ac, ab), -1, 1))
        let baBc0 = acos(PonyMath.clamp(PonyMath.dot(ba, bc), -1, 1))
        let acAt0 = acos(PonyMath.clamp(PonyMath.dot(ac, at), -1, 1))
        let num1 = lcb * lcb - lab * lab - lat * lat
        let acAb1 = acos(PonyMath.clamp(num1 / (-2 * lab * lat), -1, 1))
        let num2 = lat * lat - lab * lab - lcb * lcb
        let baBc1 = acos(PonyMath.clamp(num2 / (-2 * lab * lcb), -1, 1))
        let axis0Raw = PonyMath.cross(c - a, b - a)
        if PonyMath.lengthSquared(axis0Raw) < 1e-12 { return nil }
        let axis0 = PonyMath.normalize(axis0Raw)
        let axis1Raw = PonyMath.cross(c - a, t - a)
        let r0 = Quat(axis: aModel.inverse.act(axis0), angle: acAb1 - acAb0)
        let r1 = Quat(axis: bModel.inverse.act(axis0), angle: baBc1 - baBc0)
        var r2 = Quat.identity
        if PonyMath.lengthSquared(axis1Raw) > 1e-12 {
            r2 = Quat(axis: aModel.inverse.act(PonyMath.normalize(axis1Raw)), angle: acAt0)
        }
        return ((aLocal * (r0 * r2)).normalized, (bLocal * r1).normalized)
    }
}
