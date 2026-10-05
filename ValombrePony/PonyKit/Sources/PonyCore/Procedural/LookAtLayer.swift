import Foundation

/// Regard (SPEC §8.5) : lacet/tangage répartis sur la chaîne `neck_03…neck_06` + `head` (poids du manifeste),
/// limités et lissés par ressorts critiques ; orientation des yeux ; micro-saccades sans cible [A].
struct LookAtLayer {
    var yaw = CriticalSpring()
    var pitch = CriticalSpring()
    private(set) var weight: Float = 0
    /// Erreur de lacet (rad, + = gauche) vers la cible, relative à la tête animée (pour les oreilles).
    private(set) var targetAzimuth: Float = 0
    /// Élévation de l'axe de la tête au repos (la pose de repos « regarde » à l'horizontale).
    let restHeadElevation: Float
    private var saccadeTimer: Float = 0
    private var saccadeGoal = SIMD2<Float>(0, 0)
    private var saccadeX = CriticalSpring()
    private var saccadeY = CriticalSpring()

    init(rig: ProceduralRig, skeleton: PonySkeleton) {
        if rig.head >= 0 && rig.head < skeleton.bindModel.count {
            let dir = skeleton.bindModel[rig.head].rotation.act(SIMD3<Float>(0, 1, 0))
            restHeadElevation = PoseEditing.elevation(dir)
        } else {
            restHeadElevation = 0
        }
    }

    private func lookOrigin(rig: ProceduralRig, model: [Transform]) -> SIMD3<Float> {
        if rig.eyeLeft >= 0 && rig.eyeRight >= 0 {
            return (model[rig.eyeLeft].translation + model[rig.eyeRight].translation) * 0.5
        }
        return model[rig.head].translation
    }

    /// Met à jour les angles et applique la répartition sur la chaîne. `model` doit être à jour (FK).
    /// `factor` module le poids selon l'activité (0 pendant une roulade, réduit en broutant…).
    mutating func applyNeck(target: SIMD3<Float>?, factor: Float, dt: Float, settings: ProceduralSettings,
                            rig: ProceduralRig, pose: inout [Transform], model: inout [Transform], parents: [Int]) {
        let wanted: Float = target != nil ? PonyMath.clamp01(factor) : 0
        weight = PonyMath.moveTowards(weight, wanted, maxDelta: dt / max(settings.lookFadeDuration, 0.01))
        var yawError: Float = 0
        var pitchError: Float = 0
        targetAzimuth = 0
        if let t = target, rig.head >= 0 {
            let origin = lookOrigin(rig: rig, model: model)
            let v = t - origin
            if PonyMath.lengthSquared(v) > 1e-6 {
                let headDir = model[rig.head].rotation.act(SIMD3<Float>(0, 1, 0))
                let rawYaw = PonyMath.wrapAngle(PoseEditing.azimuth(v) - PoseEditing.azimuth(headDir))
                targetAzimuth = PonyMath.clamp(rawYaw, -1.5, 1.5)
                yawError = PonyMath.clamp(rawYaw, -settings.lookMaxYaw, settings.lookMaxYaw)
                let carriage = PoseEditing.elevation(headDir) - restHeadElevation
                pitchError = PonyMath.clamp(PoseEditing.elevation(v) - carriage,
                                            -settings.lookMaxPitchDown, settings.lookMaxPitchUp)
            }
        }
        yaw.update(target: yawError, halfLife: settings.lookHalfLife, deltaTime: dt)
        pitch.update(target: pitchError, halfLife: settings.lookHalfLife, deltaTime: dt)
        let appliedYaw = yaw.value * weight
        let appliedPitch = pitch.value * weight
        if abs(appliedYaw) + abs(appliedPitch) < 1e-5 { return }
        let up = SIMD3<Float>(0, 1, 0)
        for entry in rig.lookChain {
            let j = entry.joint
            PoseEditing.refresh(j, pose: pose, model: &model, parents: parents)
            let lateral = model[j].rotation.act(SIMD3<Float>(1, 0, 0))
            // Tangage autour de l'axe latéral courant du joint (+ = nez vers le haut), puis lacet autour de +Y.
            let delta = Quat(axis: up, angle: appliedYaw * entry.weight)
                * Quat(axis: lateral, angle: appliedPitch * entry.weight)
            PoseEditing.rotateInModelSpace(j, delta, pose: &pose, model: &model, parents: parents)
        }
    }

    /// Oriente les yeux (rotation locale additive, limitée) ; micro-saccades quand aucune cible n'est suivie.
    /// `model` doit être à jour après `applyNeck` (FK recalculée).
    mutating func applyEyes(target: SIMD3<Float>?, dt: Float, settings: ProceduralSettings, rig: ProceduralRig,
                            pose: inout [Transform], model: [Transform], random: inout PonyRandom) {
        saccadeTimer -= dt
        if saccadeTimer <= 0 {
            saccadeTimer = random.range(settings.saccadeIntervalMin, settings.saccadeIntervalMax)
            let a = settings.saccadeAmplitude
            saccadeGoal = SIMD2<Float>(random.range(-a, a), random.range(-0.5 * a, 0.5 * a))
        }
        saccadeX.update(target: saccadeGoal.x, halfLife: 0.03, deltaTime: dt)
        saccadeY.update(target: saccadeGoal.y, halfLife: 0.03, deltaTime: dt)
        let free = 1 - weight
        applyEye(rig.eyeLeft, target: target, free: free, settings: settings, pose: &pose, model: model)
        applyEye(rig.eyeRight, target: target, free: free, settings: settings, pose: &pose, model: model)
    }

    private func applyEye(_ j: Int, target: SIMD3<Float>?, free: Float, settings: ProceduralSettings,
                          pose: inout [Transform], model: [Transform]) {
        if j < 0 { return }
        var delta = Quat.identity
        if let t = target, weight > 0 {
            let local = model[j].rotation.inverse.act(t - model[j].translation)
            if PonyMath.lengthSquared(local) > 1e-8 {
                delta = Quat(from: SIMD3<Float>(0, 1, 0), to: local).clampedAngle(settings.eyeMaxAngle).scaled(weight)
            }
        }
        // Axe local Z de l'œil ≈ haut (saccade horizontale), axe X ≈ latéral (saccade verticale) [I].
        let saccade = Quat(axis: SIMD3<Float>(0, 0, 1), angle: saccadeX.value * free)
            * Quat(axis: SIMD3<Float>(1, 0, 0), angle: saccadeY.value * free)
        pose[j].rotation = (pose[j].rotation * delta * saccade).normalized
    }
}
