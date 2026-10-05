import Foundation

/// Runtime d'animation et de logique du poney (Swift pur) : à chaque frame, produit la pose locale des joints,
/// les poids de blend shapes, la vitesse de déplacement et le lacet souhaités de l'entité.
///
/// Ordre d'évaluation (SPEC §8, détaillé dans Docs/RUNTIME.md) :
/// 1–2. clips (locomotion / saut / comportements, fondus synchronisés en phase) + couches masquées ;
/// 3. morphologie (décalages et échelles de joints) ; 4. inclinaison/incurvation en virage
/// (+ adaptation au sol optionnelle) ; 5. regard + yeux ; 6. oreilles ; 7. clignements, respiration ;
/// 8. physique secondaire ; 9. surcharges manuelles.
///
/// Déterministe à graine égale (générateur `PonyRandom`, aucun accès à l'horloge). Tampons préalloués :
/// `update` n'alloue pas de mémoire en régime établi (cf. RUNTIME.md pour la nuance copie-sur-écriture).
/// Pas `Sendable` : à piloter depuis un seul fil (le MainActor côté PonyKit).
public final class PonyRuntime {
    public let manifest: PonyRigManifest
    public let clips: ClipLibrary
    public let skeleton: PonySkeleton
    public let seed: UInt64
    /// Noms de toutes les blend shapes pilotées (clés de `PonyFrame.blendWeights`), triés.
    public let blendShapeNames: [String]

    /// Configuration du poney ; toute modification recalcule la morphologie et l'échelle.
    public var configuration: PonyConfiguration {
        didSet { applyConfiguration() }
    }

    /// Cible du regard en espace modèle du poney (repère local de l'entité, unités du rig), `nil` = libre.
    public var lookTarget: SIMD3<Float>?

    /// Hauteur du sol (espace modèle) sous un point de l'espace modèle, pour l'adaptation des sabots.
    /// `nil` (par défaut) = sol plat y = 0, aucun calcul.
    public var groundHeightProvider: ((SIMD3<Float>) -> Float?)?

    /// Humeur imposée des oreilles (`nil` = automatique selon l'activité).
    public var earMood: EarMood?

    public var locomotionSettings: LocomotionSettings {
        get { return motion.loco.settings }
        set { motion.loco.settings = newValue }
    }

    public var jumpSettings: JumpSettings {
        get { return motion.jumpSettings }
        set { motion.jumpSettings = newValue }
    }

    public var behaviorSettings: BehaviorSettings {
        get { return motion.behaviorSettings }
        set { motion.behaviorSettings = newValue }
    }

    public var proceduralSettings: ProceduralSettings {
        didSet { secondary.applySettings(proceduralSettings, rig: rig) }
    }

    /// Si vrai, la phase aérienne du saut est tenue jusqu'à `notifyLanded()` (délai de sécurité
    /// `JumpSettings.externalLandingTimeout` après le vol calculé). Sinon le runtime atterrit seul au bout de
    /// t = 2·v0/g.
    public var usesExternalLanding: Bool {
        get { return motion.externalLanding }
        set { motion.externalLanding = newValue }
    }

    /// Temps écoulé (s) depuis la création (somme des `deltaTime` bornés).
    public private(set) var time: Double = 0

    public var jointNames: [String] {
        return skeleton.names
    }

    public var gait: PonyGait {
        return motion.reportedGait
    }

    public var currentAction: PonyAction? {
        return motion.currentAction
    }

    public var isAirborne: Bool {
        return motion.airborne
    }

    /// Vitesse avant courante (m/s réels).
    public var forwardSpeed: Float {
        return -lastVelocity.z
    }

    /// Effort courant (0 repos … 1 galop soutenu) du modèle de respiration.
    public var effort: Float {
        return breath.effort
    }

    /// Résultat courant de la morphologie (poids de formes, décalages et échelles de joints).
    public private(set) var morphology: MorphologyResult

    // MARK: État interne

    let motion: MotionController
    let rig: ProceduralRig
    let morphologyEvaluator: MorphologyEvaluator
    var random: PonyRandom
    private var pose: [Transform]
    private var model: [Transform]
    private var morphOffsets: [SIMD3<Float>]
    private var morphScales: [SIMD3<Float>]
    private var morphShapeValues: [Float]
    private let shapeIndex: [String: Int]
    private let breatheShape: Int
    private let flareShape: Int
    private var blendWeights: [String: Float]
    private var events: [PonyEvent]
    private var overrideRotation: [Quat]
    private var overrideWeight: [Float]
    private var overrideActive: [Int]
    private var turnPosture = TurnPostureLayer()
    private var look: LookAtLayer
    private var ears = EarLayer()
    private var blink: BlinkLayer
    private var breath = BreathLayer()
    private var secondary: SecondaryMotion
    private var feet: FootPlanting
    private(set) var sizeScale: Float = 1
    private(set) var timeScale: Float = 1
    private(set) var strideScale: Float = 1
    private var lastVelocity = SIMD3<Float>(0, 0, 0)

    // MARK: Création

    public init(manifest: PonyRigManifest, clips: ClipLibrary, configuration: PonyConfiguration, seed: UInt64 = 1) {
        self.manifest = manifest
        self.clips = clips
        self.seed = seed
        self.configuration = configuration
        let skel = PonySkeleton(manifest: manifest)
        skeleton = skel
        var rng = PonyRandom(seed: seed)

        // Ensemble trié des blend shapes : manifeste + SPEC §5 + pistes de poids des clips + curseurs.
        var names = Set<String>(manifest.allBlendShapeNames)
        for n in PonyRigDefaults.morphologyShapes + PonyRigDefaults.proportionShapes
            + PonyRigDefaults.expressionShapes {
            names.insert(n)
        }
        for c in clips.clips {
            for w in c.weightTracks {
                names.insert(w.name)
            }
        }
        for s in manifest.morphology.sliders {
            if let p = s.plus { names.insert(p) }
            if let m = s.minus { names.insert(m) }
        }
        let sortedNames = names.sorted()
        blendShapeNames = sortedNames
        var index: [String: Int] = [:]
        var weights: [String: Float] = [:]
        for (i, n) in sortedNames.enumerated() {
            index[n] = i
            weights[n] = 0
        }
        shapeIndex = index
        blendWeights = weights
        breatheShape = index["body_breathe"] ?? -1
        flareShape = index["face_nostril_flare"] ?? -1

        let settings = ProceduralSettings()
        proceduralSettings = settings
        motion = MotionController(library: clips, skeleton: skel, locomotion: LocomotionSettings(),
                                  jump: JumpSettings(), behavior: BehaviorSettings(), shapeIndex: index,
                                  shapeCount: sortedNames.count, random: &rng)
        let procRig = ProceduralRig(skeleton: skel, procedural: manifest.procedural)
        rig = procRig
        morphologyEvaluator = MorphologyEvaluator(skeleton: skel, sliders: manifest.morphology.sliders)
        look = LookAtLayer(rig: procRig, skeleton: skel)
        blink = BlinkLayer(random: &rng, settings: settings)
        secondary = SecondaryMotion(rig: procRig, skeleton: skel, settings: settings, random: &rng)
        feet = FootPlanting(rig: procRig, skeleton: skel)

        let n = skel.count
        pose = skel.restLocal
        model = skel.bindModel
        morphOffsets = [SIMD3<Float>](repeating: SIMD3<Float>(0, 0, 0), count: n)
        morphScales = [SIMD3<Float>](repeating: SIMD3<Float>(1, 1, 1), count: n)
        morphShapeValues = [Float](repeating: 0, count: sortedNames.count)
        morphology = MorphologyResult(blendWeights: [:], jointOffsets: [], jointScales: [])
        events = []
        overrideRotation = [Quat](repeating: .identity, count: n)
        overrideWeight = [Float](repeating: 0, count: n)
        overrideActive = []
        random = rng
        // Toutes les propriétés sont initialisées : préallocations puis morphologie initiale.
        events.reserveCapacity(16)
        overrideActive.reserveCapacity(n)
        applyConfiguration()
    }

    /// Création directe depuis les octets de `PonyRig.json` et de `PonyClips.bin` (`nil` = sans clips).
    public convenience init(rigJSON: Data, clipsBinary: Data?, configuration: PonyConfiguration = .default,
                            seed: UInt64 = 1) throws {
        let manifest = try PonyRigManifest.decode(from: rigJSON)
        let library: ClipLibrary
        if let data = clipsBinary {
            library = try ClipLibrary(data: data, manifest: manifest)
        } else {
            library = ClipLibrary.empty(manifest: manifest)
        }
        self.init(manifest: manifest, clips: library, configuration: configuration, seed: seed)
    }

    // MARK: API

    /// Surcharge manuelle de la rotation **locale** d'un joint (mélangée par slerp avec la pose calculée,
    /// `weight` 0…1). `rotation == nil` ou `weight <= 0` retire la surcharge. Joint inconnu : ignoré.
    public func setJointOverride(_ joint: String, rotation: Quat?, weight: Float) {
        guard let j = skeleton.index(of: joint) else { return }
        if let r = rotation, weight > 0, weight.isFinite {
            overrideRotation[j] = r.normalized
            overrideWeight[j] = PonyMath.clamp01(weight)
            if !overrideActive.contains(j) { overrideActive.append(j) }
        } else {
            overrideWeight[j] = 0
            overrideActive.removeAll(where: { $0 == j })
        }
    }

    /// Retire toutes les surcharges de joints.
    public func clearJointOverrides() {
        for j in overrideActive {
            overrideWeight[j] = 0
        }
        overrideActive.removeAll(keepingCapacity: true)
    }

    /// À appeler par PonyKit quand l'entité touche le sol pendant un saut (atterrissage anticipé).
    public func notifyLanded() {
        motion.notifyLanded()
    }

    /// À appeler après une téléportation de l'entité : réinitialise la physique secondaire.
    public func resetSecondaryMotion() {
        secondary.reset()
        feet.reset()
    }

    /// Avance le runtime de `deltaTime` secondes (borné à [0, 0,1] s ; NaN → 0) et renvoie la frame.
    public func update(deltaTime: Float, input: PonyInput) -> PonyFrame {
        var dt = deltaTime.isFinite ? deltaTime : 0
        dt = PonyMath.clamp(dt, 0, 0.1)
        time += Double(dt)
        events.removeAll(keepingCapacity: true)
        let parents = skeleton.parents
        let n = pose.count

        // 1–2. Clips : machine d'états + couches masquées.
        let deadZone = motion.loco.settings.stickDeadZone
        let mx = PonyRuntime.applyDeadZone(input.move.x, deadZone)
        let my = PonyRuntime.applyDeadZone(input.move.y, deadZone)
        motion.update(dt: dt, input: input, moveX: mx, moveY: my, timeScale: timeScale, sizeScale: sizeScale,
                      now: time, random: &random, events: &events)
        motion.evaluate()
        for j in 0..<n {
            pose[j] = motion.pose[j]
        }

        // 3. Morphologie : décalages de translation locale + échelles (tête, oreilles, yeux).
        for j in 0..<n where parents[j] >= 0 {
            pose[j].translation += morphOffsets[j]
            pose[j].scale = pose[j].scale * morphScales[j]
        }

        // Vitesses réelles de l'entité (Froude : vitesse × √échelle ; lacet × 1/√échelle).
        let velocity = motion.velocityReference * (sizeScale.squareRoot() * strideScale)
        let yawRate = motion.yawRateReference * timeScale
        lastVelocity = velocity

        // 4. Inclinaison du tronc + incurvation de l'encolure en virage.
        turnPosture.update(dt: dt, speed: -velocity.z, yawRate: yawRate, enabled: motion.mode == .locomotion,
                           settings: motion.loco.settings)
        skeleton.computeModel(local: pose, into: &model)
        feet.recordReference(rig: rig, model: model)
        if abs(turnPosture.lean.value) > 1e-5 {
            turnPosture.applyLean(rig: rig, hoofHalfWidth: feet.hoofHalfWidth, pose: &pose, model: &model,
                                  parents: parents)
            skeleton.computeModel(local: pose, into: &model)
        }
        // 4 bis. Plantage des pieds : compensation de l'inclinaison + sol (optionnel).
        feet.apply(provider: groundHeightProvider, dt: dt, settings: proceduralSettings, rig: rig,
                   skeleton: skeleton, pose: &pose, model: &model)
        turnPosture.applyBend(rig: rig, pose: &pose, model: &model, parents: parents)

        // 5. Regard (encolure + tête), puis yeux.
        look.applyNeck(target: lookTarget, factor: lookFactor, dt: dt, settings: proceduralSettings, rig: rig,
                       pose: &pose, model: &model, parents: parents)
        skeleton.computeModel(local: pose, into: &model)
        look.applyEyes(target: lookTarget, dt: dt, settings: proceduralSettings, rig: rig, pose: &pose,
                       model: model, random: &random)

        // 6. Oreilles.
        ears.update(dt: dt, forcedMood: earMood, context: earContext,
                    looking: lookTarget != nil && look.weight > 0.3, targetAzimuth: look.targetAzimuth,
                    settings: proceduralSettings, random: &random)
        ears.apply(rig: rig, pose: &pose)

        // 7. Clignements et respiration.
        blink.update(dt: dt, settings: proceduralSettings, random: &random)
        let drowsy: Float = motion.mode == .lying ? 0.35 : 0
        blink.apply(rig: rig, settings: proceduralSettings, extraClosure: drowsy, pose: &pose)
        let strideLocked = motion.mode == .locomotion && (motion.loco.gait == .canter || motion.loco.gait == .gallop)
        breath.update(dt: dt, effortTarget: effortTarget, strideLocked: strideLocked,
                      stridePhase: motion.loco.phase, settings: proceduralSettings)

        // 8. Physique secondaire (le modèle est à jour pour les parents des os simulés).
        if proceduralSettings.secondaryEnabled {
            let swished = secondary.update(dt: dt, velocity: velocity, yawRate: yawRate,
                                           verticalVelocity: motion.verticalVelocity, sizeScale: sizeScale,
                                           settings: proceduralSettings, swishAllowed: swishAllowed,
                                           random: &random, pose: &pose, model: &model, parents: parents)
            if swished {
                events.append(PonyEvent(name: "tail_swish", time: time))
            }
        }

        // 9. Surcharges manuelles.
        for j in overrideActive {
            let w = overrideWeight[j]
            pose[j].rotation = w >= 1 ? overrideRotation[j] : Quat.slerp(pose[j].rotation, overrideRotation[j], w)
        }

        // Poids des blend shapes : morphologie + clips + respiration.
        let clipShapes = motion.shapeValues
        for i in 0..<blendShapeNames.count {
            var v = morphShapeValues[i] + (i < clipShapes.count ? clipShapes[i] : 0)
            if i == breatheShape { v = max(v, breath.breathe) }
            if i == flareShape { v = max(v, breath.flare) }
            blendWeights[blendShapeNames[i]] = PonyMath.clamp01(PonyMath.finite(v))
        }

        return PonyFrame(localPose: pose, blendWeights: blendWeights, rootVelocity: velocity, rootYawRate: yawRate,
                         events: events, gait: motion.reportedGait, verticalVelocity: motion.verticalVelocity,
                         isAirborne: motion.airborne, action: motion.currentAction)
    }

    // MARK: Configuration

    private func applyConfiguration() {
        let result = morphologyEvaluator.evaluate(configuration.morphology)
        let n = skeleton.count
        for j in 0..<n {
            morphOffsets[j] = j < result.jointOffsets.count ? result.jointOffsets[j] : SIMD3<Float>(0, 0, 0)
            morphScales[j] = j < result.jointScales.count ? result.jointScales[j] : SIMD3<Float>(1, 1, 1)
        }
        for i in 0..<morphShapeValues.count {
            morphShapeValues[i] = 0
        }
        for name in result.blendWeights.keys.sorted() {
            if let i = shapeIndex[name] { morphShapeValues[i] = result.blendWeights[name] ?? 0 }
        }

        // Compensation au sol : les sabots de la pose de repos déformée doivent rester à la hauteur de repos [I].
        var restPose = skeleton.restLocal
        let restModel = skeleton.modelTransforms(local: restPose)
        for j in 0..<n where skeleton.parents[j] >= 0 {
            restPose[j].translation += morphOffsets[j]
            restPose[j].scale = restPose[j].scale * morphScales[j]
        }
        let morphModel = skeleton.modelTransforms(local: restPose)
        var compensation: Float = 0
        if !rig.hooves.isEmpty {
            var restMin: Float = .greatestFiniteMagnitude
            var morphMin: Float = .greatestFiniteMagnitude
            for h in rig.hooves {
                restMin = min(restMin, restModel[h].translation.y)
                morphMin = min(morphMin, morphModel[h].translation.y)
            }
            compensation = restMin - morphMin
        }
        var stride: Float = 1
        if rig.body >= 0 && abs(compensation) > 1e-6 {
            let parent = skeleton.parents[rig.body]
            let parentModel = parent >= 0 ? restModel[parent] : Transform.identity
            let localUp = parentModel.rotation.inverse.act(SIMD3<Float>(0, compensation, 0))
            let s = parentModel.scale
            morphOffsets[rig.body] += SIMD3<Float>(localUp.x / max(abs(s.x), 1e-6), localUp.y / max(abs(s.y), 1e-6),
                                                   localUp.z / max(abs(s.z), 1e-6))
            // Foulée proportionnelle à la hauteur du tronc (approximation de longueur de membre) [I].
            let bodyHeight = restModel[rig.body].translation.y
            if bodyHeight > 0.1 {
                stride = PonyMath.clamp((bodyHeight + compensation) / bodyHeight, 0.7, 1.3)
            }
        }
        strideScale = stride
        sizeScale = configuration.entityScale
        timeScale = 1 / max(sizeScale, 0.1).squareRoot()
        morphology = MorphologyResult(blendWeights: result.blendWeights, jointOffsets: morphOffsets,
                                      jointScales: morphScales)
        secondary.reset()
        feet.reset()
    }

    // MARK: Contexte des couches procédurales

    static func applyDeadZone(_ value: Float, _ deadZone: Float) -> Float {
        if !value.isFinite { return 0 }
        let a = abs(value)
        if a <= deadZone { return 0 }
        let scaled = (min(a, 1) - deadZone) / max(1 - deadZone, 1e-3)
        return value < 0 ? -scaled : scaled
    }

    /// Poids du regard selon l'activité [A].
    private var lookFactor: Float {
        switch motion.mode {
        case .locomotion: return 1
        case .lying: return 0.6
        case .paw: return 0.7
        case .grazeLoop: return 0.3
        case .jumpTakeoff, .jumpAir, .jumpLand: return 0.3
        default: return 0
        }
    }

    private var earContext: EarContext {
        switch motion.mode {
        case .grazeDown, .grazeLoop, .grazeUp: return .grazing
        case .lieDown, .lying, .roll, .getUp: return .lying
        case .rear: return .rear
        case .jumpTakeoff, .jumpAir, .jumpLand: return .jump
        case .paw, .bodyShake: return .idle
        case .locomotion:
            switch motion.loco.gait {
            case .idle, .turnInPlace: return .idle
            case .walk, .back: return .moving
            case .trot, .canter, .gallop: return .fast
            }
        }
    }

    /// Effort cible du modèle de respiration selon l'activité [A].
    private var effortTarget: Float {
        switch motion.mode {
        case .locomotion:
            switch motion.loco.gait {
            case .idle: return 0
            case .turnInPlace: return 0.05
            case .walk, .back: return 0.1
            case .trot: return 0.4
            case .canter: return 0.65
            case .gallop: return 1.0
            }
        case .jumpTakeoff, .jumpAir, .jumpLand: return 0.9
        case .rear: return 0.6
        case .roll: return 0.5
        case .lieDown, .getUp: return 0.35
        case .bodyShake: return 0.3
        case .paw: return 0.2
        case .grazeDown, .grazeLoop, .grazeUp, .lying: return 0
        }
    }

    private var swishAllowed: Bool {
        switch motion.mode {
        case .grazeDown, .grazeLoop, .grazeUp, .lying: return true
        case .locomotion: return motion.loco.isStanding
        default: return false
        }
    }
}
