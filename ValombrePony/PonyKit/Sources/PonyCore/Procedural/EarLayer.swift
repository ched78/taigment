import Foundation

/// Contexte d'activité utilisé pour choisir automatiquement l'humeur des oreilles.
enum EarContext {
    case idle, moving, fast, grazing, lying, rear, jump
}

/// Oreilles (SPEC §8.6) : attentives (vers la cible), indépendantes (pivotements aléatoires à graine),
/// couchées, détendues. Rotations locales additives [I, axes vérifiés sur le gabarit] :
/// +X local = pointe vers l'arrière ; +Y local = pavillon tourné vers la gauche du poney.
/// Signification éthologique des positions : gaits.md §4 (non vérifiée) [U] ; amplitudes [A].
struct EarLayer {
    struct EarState {
        var tilt = CriticalSpring()
        var outward = CriticalSpring()
        var droop = CriticalSpring()
        var flickTimer: Float = 0
        var randomTilt: Float = 0
        var randomOutward: Float = 0.3
    }

    var left = EarState()
    var right = EarState()
    private(set) var mood: EarMood = .independent
    private var idleMood: EarMood = .independent
    private var moodTimer: Float = 0

    mutating func update(dt: Float, forcedMood: EarMood?, context: EarContext, looking: Bool,
                         targetAzimuth: Float, settings: ProceduralSettings, random: inout PonyRandom) {
        // Humeur automatique au repos : alternance aléatoire.
        moodTimer -= dt
        if moodTimer <= 0 {
            moodTimer = random.range(settings.earMoodDurationMin, settings.earMoodDurationMax)
            let r = random.nextFloat()
            idleMood = r < 0.5 ? .independent : (r < 0.8 ? .relaxed : .attentive)
        }
        if let f = forcedMood {
            mood = f
        } else if looking {
            mood = .attentive
        } else {
            switch context {
            case .grazing, .lying: mood = .relaxed
            case .rear: mood = .pinned
            case .fast, .jump: mood = .attentive
            case .moving: mood = .independent
            case .idle: mood = idleMood
            }
        }
        let azimuth = looking ? targetAzimuth : 0
        let currentMood = mood
        EarLayer.updateEar(&left, mood: currentMood, side: 1, dt: dt, azimuth: azimuth, settings: settings,
                           random: &random)
        EarLayer.updateEar(&right, mood: currentMood, side: -1, dt: dt, azimuth: azimuth, settings: settings,
                           random: &random)
    }

    private static func updateEar(_ ear: inout EarState, mood: EarMood, side: Float, dt: Float, azimuth: Float,
                                  settings: ProceduralSettings, random: inout PonyRandom) {
        ear.flickTimer -= dt
        if ear.flickTimer <= 0 {
            ear.flickTimer = random.range(settings.earFlickIntervalMin, settings.earFlickIntervalMax)
            ear.randomTilt = random.range(-0.15, 0.5)
            ear.randomOutward = random.range(-0.2, 1.1)
        }
        var tilt: Float
        var outward: Float
        var droop: Float = 0
        switch mood {
        case .attentive:
            tilt = -0.15
            outward = PonyMath.clamp(-0.1 + side * azimuth, -0.35, 1.2)
        case .independent:
            tilt = ear.randomTilt
            outward = ear.randomOutward
        case .pinned:
            tilt = 1.1
            outward = 0.4
        case .relaxed:
            tilt = 0.35
            outward = 0.9
            droop = 0.25
        }
        let hl = settings.earHalfLife
        ear.tilt.update(target: tilt, halfLife: hl, deltaTime: dt)
        ear.outward.update(target: outward, halfLife: hl * 1.3, deltaTime: dt)
        ear.droop.update(target: droop, halfLife: hl * 2, deltaTime: dt)
    }

    func apply(rig: ProceduralRig, pose: inout [Transform]) {
        applyEar(left, base: rig.earLeft, tip: rig.earLeftTip, side: 1, pose: &pose)
        applyEar(right, base: rig.earRight, tip: rig.earRightTip, side: -1, pose: &pose)
    }

    private func applyEar(_ ear: EarState, base: Int, tip: Int, side: Float, pose: inout [Transform]) {
        if base >= 0 {
            let q = Quat(axis: SIMD3<Float>(1, 0, 0), angle: ear.tilt.value)
                * Quat(axis: SIMD3<Float>(0, 1, 0), angle: ear.outward.value * side)
            pose[base].rotation = (pose[base].rotation * q).normalized
        }
        if tip >= 0 {
            let q = Quat(axis: SIMD3<Float>(1, 0, 0), angle: ear.droop.value)
            pose[tip].rotation = (pose[tip].rotation * q).normalized
        }
    }
}

/// Clignements (SPEC §8.7) : minuterie aléatoire, fermeture rapide puis réouverture plus lente [A].
struct BlinkLayer {
    private var timer: Float
    private var blinkTime: Float = -1
    private var duration: Float = 0.2
    private var amplitude: Float = 1
    private(set) var closure: Float = 0

    init(random: inout PonyRandom, settings: ProceduralSettings) {
        timer = random.range(settings.blinkIntervalMin, settings.blinkIntervalMax)
    }

    mutating func update(dt: Float, settings: ProceduralSettings, random: inout PonyRandom) {
        if blinkTime >= 0 {
            blinkTime += dt
            let u = blinkTime / max(duration, 0.01)
            if u >= 1 {
                blinkTime = -1
                closure = 0
                timer = random.range(settings.blinkIntervalMin, settings.blinkIntervalMax)
            } else if u < 0.35 {
                closure = amplitude * PonyMath.smoothstep(0, 0.35, u)
            } else {
                closure = amplitude * (1 - PonyMath.smoothstep(0.35, 1, u))
            }
        } else {
            closure = 0
            timer -= dt
            if timer <= 0 {
                blinkTime = 0
                duration = random.range(settings.blinkDurationMin, settings.blinkDurationMax)
                amplitude = random.chance(settings.halfBlinkProbability) ? 0.5 : 1
            }
        }
    }

    /// Ferme les paupières de `closure + extra` (0 ouvert … 1 fermé).
    func apply(rig: ProceduralRig, settings: ProceduralSettings, extraClosure: Float, pose: inout [Transform]) {
        let c = PonyMath.clamp01(closure + extraClosure)
        if c <= 0 { return }
        let upper = -(rig.upperLidAngle ?? settings.upperLidCloseAngle) * c
        let lower = (rig.lowerLidAngle ?? settings.lowerLidCloseAngle) * c
        let qu = Quat(axis: SIMD3<Float>(1, 0, 0), angle: upper)
        let ql = Quat(axis: SIMD3<Float>(1, 0, 0), angle: lower)
        BlinkLayer.rotate(rig.lidUpperLeft, by: qu, pose: &pose)
        BlinkLayer.rotate(rig.lidUpperRight, by: qu, pose: &pose)
        BlinkLayer.rotate(rig.lidLowerLeft, by: ql, pose: &pose)
        BlinkLayer.rotate(rig.lidLowerRight, by: ql, pose: &pose)
    }

    private static func rotate(_ j: Int, by q: Quat, pose: inout [Transform]) {
        if j >= 0 && j < pose.count {
            pose[j].rotation = (pose[j].rotation * q).normalized
        }
    }
}

/// Respiration (SPEC §8.7) : modèle d'effort (monte avec l'allure, redescend lentement), fréquence
/// respiratoire croissante avec l'effort, couplée 1:1 à la foulée au galop [U] ; sorties `body_breathe`
/// et `face_nostril_flare` (0…1).
struct BreathLayer {
    private(set) var effort: Float = 0
    private(set) var phase: Double = 0
    private(set) var breathe: Float = 0
    private(set) var flare: Float = 0

    mutating func update(dt: Float, effortTarget: Float, strideLocked: Bool, stridePhase: Double,
                         settings: ProceduralSettings) {
        let tau = effortTarget > effort ? settings.effortRiseTime : settings.effortRecoveryTime
        effort += (PonyMath.clamp01(effortTarget) - effort) * (1 - exp(-dt / max(tau, 0.01)))
        if strideLocked && settings.lockBreathToStride {
            phase = stridePhase
        } else {
            let rate = PonyMath.lerp(settings.restingBreathRate, settings.maxBreathRate, effort)
            phase = PonyMath.fract(phase + Double(rate * dt))
        }
        let curve = 0.5 - 0.5 * Float(cos(2 * Double.pi * phase))
        let targetBreathe = PonyMath.clamp01((0.25 + 0.75 * effort) * curve)
        let targetFlare = PonyMath.clamp01(effort * (0.5 + 0.5 * curve))
        breathe = PonyMath.damp(breathe, toward: targetBreathe, halfLife: 0.05, deltaTime: dt)
        flare = PonyMath.damp(flare, toward: targetFlare, halfLife: 0.08, deltaTime: dt)
    }
}
