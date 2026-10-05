import Foundation

/// Machine d'états des allures : idle (+ repos d'un postérieur), pas, trot, galop à gauche/droite, galop de
/// course, reculer, pivot sur place. Mélange synchronisé en phase des clips cycliques.
///
/// Toutes les vitesses internes sont exprimées pour le gabarit de référence (1,30 m) ; la mise à l'échelle
/// (Froude) est faite par le runtime via `timeScale` (cadence) et en sortie (vitesse).
final class LocomotionController {

    enum Slot: Int, CaseIterable {
        case idle = 0, idleRest, walk, trot, canterLeft, canterRight, gallop, back, turnLeft, turnRight

        var clipName: String {
            switch self {
            case .idle: return "idle"
            case .idleRest: return "idle_rest_hind"
            case .walk: return "walk"
            case .trot: return "trot"
            case .canterLeft: return "canter_left"
            case .canterRight: return "canter_right"
            case .gallop: return "gallop"
            case .back: return "back"
            case .turnLeft: return "turn_left"
            case .turnRight: return "turn_right"
            }
        }

        /// Clip cyclique de foulée (partage la phase normalisée commune).
        var isCyclic: Bool {
            return self != .idle && self != .idleRest
        }
    }

    struct SlotInfo {
        var clipIndex: Int
        var clip: AnimationClip
        /// Vitesse avant de référence (m/s, signée : négative pour reculer).
        var forwardSpeed: Float
        var velocity: SIMD3<Float>
        /// Lacet de référence (rad/s, + = gauche).
        var yawRate: Float
        var duration: Double
        var phaseOffset: Double
    }

    static let slotCount = Slot.allCases.count

    var settings: LocomotionSettings
    private(set) var info: [SlotInfo]
    private(set) var weight: [Float]
    private var target: [Float]
    private(set) var rate: [Float]
    private var clipTime: [Double]
    private var previousClipTime: [Double]

    /// Phase de foulée normalisée commune [0, 1) (0 = poser du postérieur gauche).
    private(set) var phase: Double = 0
    private(set) var previousPhase: Double = 0
    /// Vitesse avant (m/s de référence, signée).
    private(set) var speed: Float = 0
    /// Lacet de direction (rad/s de référence, + = gauche).
    private(set) var steerYaw: Float = 0
    private(set) var gait: PonyGait = .idle
    private(set) var gaitTimer: Float = 0
    private(set) var lead: Slot = .canterLeft
    private var leadMismatchTimer: Float = 0
    private var leadFadeActive = false
    private(set) var resting = false
    private var restTimer: Float = 0
    private var restLimit: Float = 20
    private var lastSteer: Float = 0

    init(library: ClipLibrary, settings: LocomotionSettings, random: inout PonyRandom) {
        self.settings = settings
        var infos: [SlotInfo] = []
        for slot in Slot.allCases {
            let name = slot.clipName
            let defaults = PonyRigDefaults.clipDefaults[name]
            var clipIndex = -1
            var clip = AnimationClip.placeholder(name: name, jointCount: library.jointCount)
            if let i = library.index(of: name) {
                clipIndex = i
                clip = library.clips[i]
            }
            var forward = -clip.rootVelocity.z
            var velocity = clip.rootVelocity
            let defaultForward = defaults?.forwardSpeed ?? 0
            if slot.isCyclic && slot != .turnLeft && slot != .turnRight && abs(forward) < 0.05 {
                // Vitesse de référence absente ou nulle pour une allure : repli sur le SPEC §7.
                forward = defaultForward
                velocity = SIMD3<Float>(0, 0, -defaultForward)
            }
            var yaw: Float = 0
            if slot == .turnLeft || slot == .turnRight {
                var magnitude = abs(clip.rootYawRate)
                if magnitude < 0.05 { magnitude = abs(defaults?.yawRate ?? 1.2) }
                yaw = slot == .turnLeft ? magnitude : -magnitude
                forward = 0
                velocity = SIMD3<Float>(0, 0, 0)
            }
            let duration = clip.duration > 0 ? clip.duration : Double(defaults?.duration ?? 1)
            infos.append(SlotInfo(clipIndex: clipIndex, clip: clip, forwardSpeed: forward, velocity: velocity,
                                  yawRate: yaw, duration: duration, phaseOffset: Double(clip.phaseOffset)))
        }
        info = infos
        let n = LocomotionController.slotCount
        weight = [Float](repeating: 0, count: n)
        target = [Float](repeating: 0, count: n)
        rate = [Float](repeating: 1, count: n)
        clipTime = [Double](repeating: 0, count: n)
        previousClipTime = [Double](repeating: 0, count: n)
        weight[Slot.idle.rawValue] = 1
        target[Slot.idle.rawValue] = 1
        restLimit = random.range(settings.idleRestDelayMin, settings.idleRestDelayMax)
    }

    // MARK: Vitesses de référence et bandes

    var walkSpeed: Float { return max(0.1, abs(info[Slot.walk.rawValue].forwardSpeed)) }
    var trotSpeed: Float { return max(0.1, abs(info[Slot.trot.rawValue].forwardSpeed)) }
    var canterSpeed: Float {
        let l = abs(info[Slot.canterLeft.rawValue].forwardSpeed)
        let r = abs(info[Slot.canterRight.rawValue].forwardSpeed)
        return max(0.1, 0.5 * (l + r))
    }
    var gallopSpeed: Float { return max(0.1, abs(info[Slot.gallop.rawValue].forwardSpeed)) }
    var backSpeed: Float { return max(0.1, abs(info[Slot.back.rawValue].forwardSpeed)) }

    /// Bande de vitesses (min, max) jouable par une allure sans sortir de la tolérance de cadence.
    func band(_ g: PonyGait) -> (min: Float, max: Float) {
        let tol = settings.playbackTolerance
        switch g {
        case .idle, .turnInPlace: return (0, 0)
        case .walk: return (0, walkSpeed * (1 + tol))
        case .trot: return (trotSpeed * (1 - tol), trotSpeed * (1 + tol))
        case .canter: return (canterSpeed * (1 - tol), canterSpeed * (1 + tol))
        case .gallop: return (gallopSpeed * (1 - tol), gallopSpeed * (1 + tol))
        case .back: return (-backSpeed * (1 + tol), 0)
        }
    }

    static func level(_ g: PonyGait) -> Int {
        switch g {
        case .idle, .back, .turnInPlace: return 0
        case .walk: return 1
        case .trot: return 2
        case .canter: return 3
        case .gallop: return 4
        }
    }

    static func gait(atLevel l: Int) -> PonyGait {
        switch l {
        case 1: return .walk
        case 2: return .trot
        case 3: return .canter
        case 4: return .gallop
        default: return .idle
        }
    }

    private func upThreshold(_ level: Int) -> Float {
        switch level {
        case 0: return settings.walkUp
        case 1: return settings.trotUp
        case 2: return settings.canterUp
        default: return settings.gallopUp
        }
    }

    private func downThreshold(_ level: Int) -> Float {
        // Seuil pour redescendre du niveau (level + 1) au niveau `level`.
        switch level {
        case 0: return settings.walkDown
        case 1: return settings.trotDown
        case 2: return settings.canterDown
        default: return settings.gallopDown
        }
    }

    /// Allure souhaitée pour une vitesse commandée, avec hystérésis relative à l'allure courante.
    func desiredForwardGait(command: Float) -> PonyGait {
        var l = LocomotionController.level(gait)
        while l < 4 && command > upThreshold(l) {
            l += 1
        }
        while l > 0 && command < downThreshold(l - 1) {
            l -= 1
        }
        return LocomotionController.gait(atLevel: l)
    }

    private func acceleration(_ g: PonyGait) -> Float {
        switch g {
        case .walk, .idle, .turnInPlace: return settings.walkAcceleration
        case .trot: return settings.trotAcceleration
        case .canter: return settings.canterAcceleration
        case .gallop: return settings.gallopAcceleration
        case .back: return settings.backAcceleration
        }
    }

    private func minTurnRadius(_ g: PonyGait) -> Float {
        switch g {
        case .walk, .idle, .turnInPlace: return settings.walkMinTurnRadius
        case .trot: return settings.trotMinTurnRadius
        case .canter: return settings.canterMinTurnRadius
        case .gallop: return settings.gallopMinTurnRadius
        case .back: return settings.backMinTurnRadius
        }
    }

    var isStanding: Bool {
        return gait == .idle && abs(speed) < 0.05
    }

    // MARK: Mise à jour

    /// - Parameters:
    ///   - moveX, moveY: entrées déjà débarrassées de la zone morte, dans [−1, 1].
    ///   - inputEnabled: faux pendant un comportement ou un saut (le poney s'arrête).
    ///   - timeScale: facteur de cadence (Froude) appliqué à la lecture des clips.
    func update(dt: Float, moveX: Float, moveY: Float, sprint: Bool, inputEnabled: Bool,
                timeScale: Float, random: inout PonyRandom) {
        let tol = settings.playbackTolerance
        var command: Float = 0
        var steer: Float = 0
        if inputEnabled {
            if moveY > 0 {
                command = moveY * (sprint ? settings.sprintSpeed : settings.cruiseSpeed)
            } else if moveY < 0 {
                command = moveY * backSpeed * (1 + tol)
            }
            steer = moveX
        }
        lastSteer = steer
        gaitTimer += dt

        // 1. Allure souhaitée.
        var desired: PonyGait
        if command < -0.01 {
            desired = .back
        } else if command <= 0.01 && steer != 0 && abs(speed) < 0.15 {
            desired = .turnInPlace
        } else {
            desired = desiredForwardGait(command: command)
        }

        // 2. Transitions d'allure (une marche à la fois, quand la vitesse atteint la limite de la bande).
        var goal: Float = 0
        switch gait {
        case .idle:
            goal = 0
            if desired == .back {
                setGait(.back)
            } else if desired == .turnInPlace {
                setGait(.turnInPlace)
            } else if LocomotionController.level(desired) > 0 {
                setGait(.walk)
            }
        case .turnInPlace:
            goal = 0
            if desired != .turnInPlace {
                setGait(.idle)
            }
        case .back:
            if desired == .back {
                goal = max(command, band(.back).min)
            } else {
                goal = 0
                if speed > -0.03 { setGait(.idle) }
            }
        case .walk, .trot, .canter, .gallop:
            let lc = LocomotionController.level(gait)
            let ld = LocomotionController.level(desired)
            let b = band(gait)
            if ld > lc {
                goal = b.max
                if speed >= b.max - 0.05 && gaitTimer >= settings.minGaitDuration {
                    setGait(LocomotionController.gait(atLevel: lc + 1))
                }
            } else if ld < lc {
                goal = b.min
                if speed <= b.min + 0.05 && gaitTimer >= settings.minGaitDuration {
                    setGait(LocomotionController.gait(atLevel: lc - 1))
                }
            } else {
                goal = PonyMath.clamp(command, b.min, b.max)
            }
        }

        // 3. Vitesse (accélération limitée par allure).
        var accel = acceleration(gait)
        if abs(goal) < abs(speed) { accel *= settings.decelerationFactor }
        speed = PonyMath.moveTowards(speed, goal, maxDelta: accel * dt)
        if gait == .idle || gait == .turnInPlace {
            speed = PonyMath.moveTowards(speed, 0, maxDelta: accel * settings.decelerationFactor * dt)
        }

        // 4. Pied au galop (changement de pied si le virage contredit le pied assez longtemps).
        if gait == .canter {
            var wanted: Slot? = nil
            if steer < -0.3 { wanted = .canterLeft }
            if steer > 0.3 { wanted = .canterRight }
            if let w = wanted, w != lead {
                leadMismatchTimer += dt
                if leadMismatchTimer >= settings.leadChangeDelay {
                    lead = w
                    leadMismatchTimer = 0
                    leadFadeActive = true
                }
            } else {
                leadMismatchTimer = 0
            }
        }

        // 5. Repos d'un postérieur après un moment d'immobilité.
        updateRest(dt: dt, random: &random)

        // 6. Poids cibles et fondus.
        computeTargets(steer: steer)
        let gaitFade = dt / max(settings.gaitFadeDuration, 0.01)
        let restFade = dt / max(settings.restFadeDuration, 0.01)
        let leadFade = dt / max(settings.leadChangeFadeDuration, 0.01)
        for k in 0..<LocomotionController.slotCount {
            var step = gaitFade
            if gait == .idle && (k == Slot.idle.rawValue || k == Slot.idleRest.rawValue) {
                step = restFade
            }
            if leadFadeActive && (k == Slot.canterLeft.rawValue || k == Slot.canterRight.rawValue) {
                step = leadFade
            }
            weight[k] = PonyMath.moveTowards(weight[k], target[k], maxDelta: step)
        }
        if leadFadeActive && weight[lead.rawValue] >= 1 {
            leadFadeActive = false
        }

        // 7. Cadences de lecture (±tolérance autour de la vitesse de référence).
        for slot in Slot.allCases {
            let k = slot.rawValue
            switch slot {
            case .idle, .idleRest:
                rate[k] = 1
            case .turnLeft, .turnRight:
                rate[k] = (1 - tol) + 2 * tol * PonyMath.clamp01(abs(steer))
            default:
                let ref = abs(info[k].forwardSpeed)
                rate[k] = ref > 0.01 ? PonyMath.clamp(abs(speed) / ref, 1 - tol, 1 + tol) : 1
            }
        }

        // 8. Phase commune (moyenne pondérée des fréquences de foulée des clips cycliques actifs).
        previousPhase = phase
        var cyclicWeight: Float = 0
        var frequency: Double = 0
        for slot in Slot.allCases where slot.isCyclic {
            let k = slot.rawValue
            let w = weight[k]
            if w <= 0 { continue }
            cyclicWeight += w
            frequency += Double(w * rate[k]) / max(info[k].duration, 1e-3)
        }
        if cyclicWeight > 1e-4 {
            let f = frequency / Double(cyclicWeight)
            phase = PonyMath.fract(phase + f * Double(dt * timeScale))
        } else {
            phase = 0
            previousPhase = 0
        }
        for k in 0..<2 {
            previousClipTime[k] = clipTime[k]
            clipTime[k] += Double(dt * timeScale)
        }

        // 9. Direction (lacet limité par le rayon de virage de l'allure).
        var commandYaw: Float = 0
        switch gait {
        case .walk, .trot, .canter, .gallop:
            let v = max(abs(speed), settings.minTurnSpeed)
            let maxYaw = min(settings.maxYawRate, v / max(minTurnRadius(gait), 0.1))
            commandYaw = -steer * maxYaw
        case .back:
            let v = max(abs(speed), 0.3)
            commandYaw = -steer * min(settings.maxYawRate, v / max(settings.backMinTurnRadius, 0.1))
        default:
            commandYaw = 0
        }
        steerYaw = PonyMath.moveTowards(steerYaw, commandYaw, maxDelta: settings.yawAcceleration * dt)
    }

    private func computeTargets(steer: Float) {
        let tol = settings.playbackTolerance
        for k in 0..<LocomotionController.slotCount {
            target[k] = 0
        }
        switch gait {
        case .idle:
            let restAvailable = info[Slot.idleRest.rawValue].clipIndex >= 0
            target[(resting && restAvailable) ? Slot.idleRest.rawValue : Slot.idle.rawValue] = 1
        case .walk:
            let a = PonyMath.clamp01(speed / (walkSpeed * (1 - tol)))
            target[Slot.walk.rawValue] = a
            target[Slot.idle.rawValue] = 1 - a
        case .trot:
            target[Slot.trot.rawValue] = 1
        case .canter:
            target[lead.rawValue] = 1
        case .gallop:
            target[Slot.gallop.rawValue] = 1
        case .back:
            let a = PonyMath.clamp01(-speed / (backSpeed * (1 - tol)))
            target[Slot.back.rawValue] = a
            target[Slot.idle.rawValue] = 1 - a
        case .turnInPlace:
            let b = PonyMath.clamp01(abs(steer) / 0.5)
            let k = steer < 0 ? Slot.turnLeft.rawValue : Slot.turnRight.rawValue
            target[k] = b
            target[Slot.idle.rawValue] = 1 - b
        }
    }

    private func updateRest(dt: Float, random: inout PonyRandom) {
        if gait == .idle && abs(speed) < 0.01 && lastSteer == 0 {
            restTimer += dt
            if !resting && restTimer >= restLimit {
                resting = true
                restTimer = 0
                restLimit = random.range(settings.idleRestDurationMin, settings.idleRestDurationMax)
                clipTime[Slot.idleRest.rawValue] = 0
            } else if resting && restTimer >= restLimit {
                resting = false
                restTimer = 0
                restLimit = random.range(settings.idleRestDelayMin, settings.idleRestDelayMax)
            }
        } else {
            if resting {
                resting = false
                restLimit = random.range(settings.idleRestDelayMin, settings.idleRestDelayMax)
            }
            restTimer = 0
        }
    }

    private func setGait(_ g: PonyGait) {
        if g == gait { return }
        if g == .canter {
            if lastSteer < -0.05 {
                lead = .canterLeft
            } else if lastSteer > 0.05 {
                lead = .canterRight
            }
            leadMismatchTimer = 0
        }
        gait = g
        gaitTimer = 0
    }

    // MARK: Réinitialisations (retour d'un comportement ou d'un saut)

    func resetToIdle() {
        for k in 0..<LocomotionController.slotCount {
            weight[k] = 0
            target[k] = 0
        }
        weight[Slot.idle.rawValue] = 1
        target[Slot.idle.rawValue] = 1
        speed = 0
        steerYaw = 0
        gait = .idle
        gaitTimer = 0
        phase = 0
        previousPhase = 0
        resting = false
        restTimer = 0
    }

    /// Reprend directement une allure (ex. galop à la réception d'un saut) à la vitesse donnée.
    func resume(gait g: PonyGait, speed newSpeed: Float, steer: Float) {
        resetToIdle()
        lastSteer = steer
        gait = .idle
        setGait(g)
        let b = band(g)
        speed = PonyMath.clamp(newSpeed, b.min, b.max)
        for k in 0..<LocomotionController.slotCount {
            weight[k] = 0
        }
        computeTargets(steer: steer)
        for k in 0..<LocomotionController.slotCount {
            weight[k] = target[k]
        }
    }

    // MARK: Sorties

    /// Temps d'échantillonnage du clip d'un emplacement.
    func sampleTime(_ k: Int) -> Double {
        let i = info[k]
        if Slot(rawValue: k)?.isCyclic ?? false {
            return PonyMath.fract(phase - i.phaseOffset) * i.duration
        }
        return clipTime[k]
    }

    private func previousSampleTime(_ k: Int) -> Double {
        let i = info[k]
        if Slot(rawValue: k)?.isCyclic ?? false {
            return PonyMath.fract(previousPhase - i.phaseOffset) * i.duration
        }
        return previousClipTime[k]
    }

    private var totalWeight: Float {
        var s: Float = 0
        for w in weight {
            s += w
        }
        return s
    }

    /// Vitesse impliquée par la pose mélangée (m/s de référence, espace poney) : Σ wᵢ·cadenceᵢ·vᵢ / Σ wᵢ.
    var poseVelocity: SIMD3<Float> {
        let total = totalWeight
        if total <= 1e-6 { return SIMD3<Float>(0, 0, 0) }
        var v = SIMD3<Float>(0, 0, 0)
        for k in 0..<LocomotionController.slotCount where weight[k] > 0 {
            v += info[k].velocity * (weight[k] * rate[k])
        }
        return v / total
    }

    /// Lacet total (rad/s de référence) : direction + pivot sur place des clips de virage.
    var yawRate: Float {
        let total = totalWeight
        var clipYaw: Float = 0
        if total > 1e-6 {
            let l = Slot.turnLeft.rawValue
            let r = Slot.turnRight.rawValue
            clipYaw += info[l].yawRate * weight[l] * rate[l]
            clipYaw += info[r].yawRate * weight[r] * rate[r]
            clipYaw /= total
        }
        return steerYaw + clipYaw
    }

    /// Emplacement cyclique dominant (pour les évènements de foulée).
    var dominantSlot: Int {
        var best = Slot.idle.rawValue
        var bestW: Float = -1
        for k in 0..<LocomotionController.slotCount where weight[k] > bestW {
            best = k
            bestW = weight[k]
        }
        return best
    }

    /// Évènements franchis pendant la dernière mise à jour, depuis le clip dominant uniquement.
    func forEachEvent(_ body: (PonyRigManifest.ClipEvent) -> Void) {
        let k = dominantSlot
        if weight[k] < 0.25 || info[k].clipIndex < 0 { return }
        let clip = info[k].clip
        let from = previousSampleTime(k)
        var to = sampleTime(k)
        if Slot(rawValue: k)?.isCyclic ?? false {
            let dphase = PonyMath.fract(phase - previousPhase)
            if dphase <= 0 { return }
            to = from + dphase * info[k].duration
        } else if to <= from {
            return
        }
        clip.forEachEvent(from: from, to: to, body)
    }

    /// Échantillonne et mélange les clips actifs dans `out` (pose locale complète).
    /// `shapes` reçoit les pistes de poids pondérées par `outerWeight` ; `clipShapes[c][t]` = indice global
    /// de la forme de la piste t du clip c de la bibliothèque.
    func evaluate(rest: [Transform], scratch: inout [Transform], accumulator: inout PoseAccumulator,
                  out: inout [Transform], shapes: inout ShapeAccumulator, outerWeight: Float,
                  clipShapes: [[Int]]) {
        accumulator.reset()
        let total = totalWeight
        let n = min(rest.count, scratch.count)
        for k in 0..<LocomotionController.slotCount {
            let w = weight[k]
            if w <= 1e-4 { continue }
            for j in 0..<n {
                scratch[j] = rest[j]
            }
            let t = sampleTime(k)
            let i = info[k]
            if i.clipIndex >= 0 {
                i.clip.sample(at: t, into: &scratch)
                if total > 0 && i.clipIndex < clipShapes.count {
                    let map = clipShapes[i.clipIndex]
                    let sw = outerWeight * w / total
                    for (ti, shapeIndex) in map.enumerated() where shapeIndex >= 0 {
                        shapes.add(index: shapeIndex, value: i.clip.weightValue(track: ti, at: t), weight: sw)
                    }
                }
            }
            accumulator.add(scratch, weight: w)
        }
        accumulator.resolve(into: &out, fallback: rest)
    }
}
