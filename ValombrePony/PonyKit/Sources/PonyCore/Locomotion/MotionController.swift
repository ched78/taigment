import Foundation

/// Orchestration de la couche de base (locomotion, saut, comportements du corps entier) et des couches
/// masquées (`head_shake`, `neigh`). Produit la pose locale « clips » (étapes 1–2 du SPEC §8) et les poids
/// de blend shapes issus des clips.
final class MotionController {

    enum Mode: Equatable {
        case locomotion
        case jumpTakeoff, jumpAir, jumpLand
        case grazeDown, grazeLoop, grazeUp
        case lieDown, lying, getUp, roll
        case rear, paw, bodyShake

        var action: PonyAction? {
            switch self {
            case .grazeDown, .grazeLoop, .grazeUp: return .graze
            case .lieDown, .lying: return .lieDown
            case .getUp: return .getUp
            case .roll: return .roll
            case .rear: return .rear
            case .paw: return .paw
            case .bodyShake: return .bodyShake
            default: return nil
            }
        }

        var isJump: Bool {
            return self == .jumpTakeoff || self == .jumpAir || self == .jumpLand
        }
    }

    struct BaseSlot {
        var active = false
        var isLocomotion = false
        var clip = -1
        var time: Double = 0
        var weight: Float = 0
        var target: Float = 0
        var fadeSpeed: Float = 4
    }

    struct OverlaySlot {
        var active = false
        var clip = -1
        var action: PonyAction = .headShake
        var time: Double = 0
        var weight: Float = 0
        var fadingOut = false
        var maskIndex = 0
    }

    let library: ClipLibrary
    let skeleton: PonySkeleton
    let rest: [Transform]
    let loco: LocomotionController
    var jumpSettings: JumpSettings
    var behaviorSettings: BehaviorSettings
    /// Si vrai, le vol est tenu jusqu'à `notifyLanded()` (avec délai de sécurité).
    var externalLanding = false

    private var slots: [BaseSlot]
    private var currentSlot = 0
    private var overlays: [OverlaySlot]
    private var overlayMasks: [[Float]]
    private var rootJoints: [Int]
    private(set) var mode: Mode = .locomotion
    private(set) var modeTime: Double = 0
    private(set) var modeDuration: Double = 0
    private(set) var pendingAction: PonyAction?
    private var pendingTimer: Float = 0
    private var queuedLyingAction: PonyAction?

    // Saut
    private(set) var airborne = false
    private(set) var airTime: Float = 0
    private(set) var flightTime: Float = 0
    private(set) var takeoffVelocity: Float = 0
    private var takeoffAt: Double = 0
    private var apexEmitted = false
    private var landedFlag = false
    private(set) var jumpSpeed: Float = 0
    private var jumpGait: PonyGait = .canter
    private var sizeScale: Float = 1

    // Tampons préalloués
    private(set) var pose: [Transform]
    private var scratchA: [Transform]
    private var scratchB: [Transform]
    private var inner: PoseAccumulator
    private var outer: PoseAccumulator
    private var shapeAccumulator: ShapeAccumulator
    private(set) var shapeValues: [Float]
    /// `clipShapes[c][t]` : indice global de blend shape de la piste de poids t du clip c (−1 si inconnue).
    let clipShapes: [[Int]]

    // Sorties (unités du gabarit de référence, sauf `verticalVelocity` en m/s réels).
    private(set) var velocityReference = SIMD3<Float>(0, 0, 0)
    private(set) var yawRateReference: Float = 0
    private(set) var verticalVelocity: Float = 0

    init(library: ClipLibrary, skeleton: PonySkeleton, locomotion: LocomotionSettings, jump: JumpSettings,
         behavior: BehaviorSettings, shapeIndex: [String: Int], shapeCount: Int, random: inout PonyRandom) {
        self.library = library
        self.skeleton = skeleton
        rest = skeleton.restLocal
        loco = LocomotionController(library: library, settings: locomotion, random: &random)
        jumpSettings = jump
        behaviorSettings = behavior
        let n = skeleton.count
        var s = [BaseSlot](repeating: BaseSlot(), count: 4)
        s[0] = BaseSlot(active: true, isLocomotion: true, clip: -1, time: 0, weight: 1, target: 1, fadeSpeed: 4)
        slots = s
        overlays = [OverlaySlot](repeating: OverlaySlot(), count: 2)
        pose = skeleton.restLocal
        scratchA = [Transform](repeating: .identity, count: n)
        scratchB = [Transform](repeating: .identity, count: n)
        inner = PoseAccumulator(jointCount: n)
        outer = PoseAccumulator(jointCount: n)
        shapeAccumulator = ShapeAccumulator(count: shapeCount)
        shapeValues = [Float](repeating: 0, count: shapeCount)
        var map: [[Int]] = []
        for clip in library.clips {
            map.append(clip.weightTracks.map { shapeIndex[$0.name] ?? -1 })
        }
        clipShapes = map
        var roots: [Int] = []
        for j in 0..<n where skeleton.parents[j] < 0 {
            roots.append(j)
        }
        rootJoints = roots
        overlayMasks = []
        overlayMasks = [makeMask(clipName: "head_shake", subtreeRoots: ["neck_01"], extra: []),
                        makeMask(clipName: "neigh", subtreeRoots: ["neck_01"], extra: ["belly"])]
    }

    /// Masque d'une couche : celui du manifeste s'il existe, sinon un masque par défaut [I] (encolure et
    /// tête entières ; + ventre pour `neigh`, « flancs » du SPEC §7).
    private func makeMask(clipName: String, subtreeRoots: [String], extra: [String]) -> [Float] {
        var mask = [Float](repeating: 0, count: skeleton.count)
        if let i = library.index(of: clipName), let m = library.clips[i].maskJoints, !m.isEmpty {
            for j in m where j >= 0 && j < mask.count {
                mask[j] = 1
            }
            return mask
        }
        for r in subtreeRoots {
            if let j = skeleton.index(of: r) {
                for k in skeleton.subtree(of: j) {
                    mask[k] = 1
                }
            }
        }
        for e in extra {
            if let j = skeleton.index(of: e) { mask[j] = 1 }
        }
        return mask
    }

    // MARK: État exposé

    var reportedGait: PonyGait {
        if mode == .locomotion { return loco.gait }
        if mode.isJump { return jumpGait }
        return .idle
    }

    var currentAction: PonyAction? {
        if let a = mode.action { return a }
        for o in overlays where o.active && !o.fadingOut {
            return o.action
        }
        return nil
    }

    func notifyLanded() {
        if airborne { landedFlag = true }
    }

    // MARK: Mise à jour

    func update(dt: Float, input: PonyInput, moveX: Float, moveY: Float, timeScale: Float, sizeScale: Float,
                now: Double, random: inout PonyRandom, events: inout [PonyEvent]) {
        self.sizeScale = sizeScale
        let sdt = Double(dt * timeScale)
        let wantsMove = moveX != 0 || moveY != 0
        if let a = input.action {
            handleRequest(a, wantsMove: wantsMove)
        }
        modeTime += sdt

        switch mode {
        case .locomotion:
            if input.jumpPressed && canJump {
                startJump()
            } else if let p = pendingAction {
                pendingTimer += dt
                if loco.isStanding {
                    pendingAction = nil
                    _ = startAction(p)
                } else if wantsMove || pendingTimer > behaviorSettings.pendingActionTimeout {
                    pendingAction = nil
                }
            }
        case .jumpTakeoff:
            if !airborne && modeTime >= takeoffAt {
                beginFlight(now: now, events: &events)
            }
            if airborne {
                updateFlight(dt: dt, now: now, events: &events)
            }
            if mode == .jumpTakeoff && modeTime >= modeDuration - Double(jumpSettings.airFade) {
                if !airborne { beginFlight(now: now, events: &events) }
                enterMode(.jumpAir, clip: "jump_air", fade: jumpSettings.airFade)
            }
        case .jumpAir:
            if airborne {
                updateFlight(dt: dt, now: now, events: &events)
            } else {
                enterMode(.jumpLand, clip: "jump_land", fade: jumpSettings.landFade)
            }
        case .jumpLand:
            if modeTime >= modeDuration - Double(jumpSettings.recoverFade) {
                finishJump(steer: moveX)
            }
        case .grazeDown:
            if wantsMove || input.jumpPressed || pendingAction != nil {
                // Demi-tour : on enchaîne `graze_up` depuis la position « miroir » de la descente.
                let u = modeDuration > 0 ? min(modeTime / modeDuration, 1) : 1
                let upDuration = clipDuration("graze_up")
                enterMode(.grazeUp, clip: "graze_up", fade: 0.2, startTime: (1 - u) * upDuration)
            } else if modeTime >= modeDuration - 0.2 {
                enterMode(.grazeLoop, clip: "graze_loop", fade: 0.2)
            }
        case .grazeLoop:
            if wantsMove || input.jumpPressed || pendingAction != nil {
                enterMode(.grazeUp, clip: "graze_up", fade: 0.25)
            }
        case .grazeUp, .getUp, .rear, .bodyShake:
            if modeTime >= modeDuration - Double(behaviorSettings.actionFade) {
                returnToLocomotion(fade: behaviorSettings.actionFade)
            }
        case .lieDown:
            if modeTime >= modeDuration - 0.3 {
                enterMode(.lying, clip: "lying", fade: 0.3)
            }
        case .lying:
            if wantsMove || queuedLyingAction == .getUp {
                queuedLyingAction = nil
                enterMode(.getUp, clip: "get_up", fade: 0.3)
            } else if queuedLyingAction == .roll {
                queuedLyingAction = nil
                if library.index(of: "roll") != nil {
                    enterMode(.roll, clip: "roll", fade: 0.3)
                }
            }
        case .roll:
            if modeTime >= modeDuration - 0.3 {
                enterMode(.lying, clip: "lying", fade: 0.3)
            }
        case .paw:
            if wantsMove || input.jumpPressed || pendingAction != nil
                || modeTime >= Double(behaviorSettings.pawDuration) {
                returnToLocomotion(fade: behaviorSettings.actionFade)
            }
        }

        loco.update(dt: dt, moveX: moveX, moveY: moveY, sprint: input.sprint,
                    inputEnabled: mode == .locomotion, timeScale: timeScale, random: &random)
        advanceSlots(dt: dt, sdt: sdt, now: now, events: &events)
        advanceOverlays(dt: dt, sdt: sdt, now: now, events: &events)
        computeOutputs()
    }

    private var canJump: Bool {
        switch loco.gait {
        case .canter, .gallop: return true
        case .trot: return jumpSettings.allowFromTrot
        default: return false
        }
    }

    private func computeOutputs() {
        switch mode {
        case .locomotion:
            velocityReference = loco.poseVelocity
            yawRateReference = loco.yawRate
        case .jumpTakeoff, .jumpAir, .jumpLand:
            velocityReference = SIMD3<Float>(0, 0, -jumpSpeed)
            yawRateReference = 0
        default:
            velocityReference = SIMD3<Float>(0, 0, 0)
            yawRateReference = 0
        }
        verticalVelocity = airborne ? takeoffVelocity - PonyMath.gravity * airTime : 0
    }

    // MARK: Requêtes d'actions

    private func handleRequest(_ a: PonyAction, wantsMove: Bool) {
        switch a {
        case .headShake:
            playOverlay(a, name: "head_shake")
        case .neigh:
            playOverlay(a, name: "neigh")
        case .getUp:
            if mode == .lying {
                enterMode(.getUp, clip: "get_up", fade: 0.3)
            } else if mode == .lieDown || mode == .roll {
                queuedLyingAction = .getUp
            }
        case .roll:
            if mode == .lying {
                if library.index(of: "roll") != nil {
                    enterMode(.roll, clip: "roll", fade: 0.3)
                }
            } else if mode == .lieDown {
                queuedLyingAction = .roll
            }
        case .graze, .rear, .paw, .lieDown, .bodyShake:
            switch mode {
            case .locomotion:
                if loco.isStanding {
                    _ = startAction(a)
                } else if !wantsMove {
                    pendingAction = a
                    pendingTimer = 0
                }
            case .grazeDown, .grazeLoop, .paw:
                if a != mode.action {
                    pendingAction = a
                    pendingTimer = 0
                }
            default:
                break       // comportements non interruptibles : la demande est ignorée
            }
        }
    }

    /// Démarre un comportement du corps entier depuis l'arrêt. Clip absent ⇒ action ignorée (faux).
    @discardableResult
    func startAction(_ a: PonyAction) -> Bool {
        let fade = behaviorSettings.actionFade
        switch a {
        case .graze:
            if library.index(of: "graze_down") != nil {
                enterMode(.grazeDown, clip: "graze_down", fade: fade)
            } else if library.index(of: "graze_loop") != nil {
                enterMode(.grazeLoop, clip: "graze_loop", fade: fade)
            } else {
                return false
            }
        case .rear:
            if library.index(of: "rear") == nil { return false }
            enterMode(.rear, clip: "rear", fade: fade)
        case .paw:
            if library.index(of: "paw") == nil { return false }
            enterMode(.paw, clip: "paw", fade: fade)
        case .lieDown:
            if library.index(of: "lie_down") != nil {
                enterMode(.lieDown, clip: "lie_down", fade: fade)
            } else if library.index(of: "lying") != nil {
                enterMode(.lying, clip: "lying", fade: fade)
            } else {
                return false
            }
        case .bodyShake:
            if library.index(of: "body_shake") == nil { return false }
            enterMode(.bodyShake, clip: "body_shake", fade: fade)
        default:
            return false
        }
        return true
    }

    private func clipDuration(_ name: String) -> Double {
        if let i = library.index(of: name) { return library.clips[i].duration }
        return Double(PonyRigDefaults.clipDefaults[name]?.duration ?? 1)
    }

    /// Entre dans un mode en jouant son clip (s'il existe ; sinon la pose courante est conservée et la
    /// durée de repli du SPEC §7 est utilisée).
    private func enterMode(_ m: Mode, clip name: String, fade: Float, startTime: Double = 0) {
        mode = m
        modeTime = startTime
        modeDuration = clipDuration(name)
        if let i = library.index(of: name) {
            playClip(i, fade: fade, startTime: startTime)
        }
    }

    private func returnToLocomotion(fade: Float) {
        mode = .locomotion
        modeTime = 0
        modeDuration = 0
        loco.resetToIdle()
        playLocomotion(fade: fade)
    }

    // MARK: Saut

    private func startJump() {
        jumpGait = loco.gait
        jumpSpeed = max(loco.speed, loco.band(.trot).min)
        airborne = false
        airTime = 0
        apexEmitted = false
        landedFlag = false
        pendingAction = nil
        enterMode(.jumpTakeoff, clip: "jump_takeoff", fade: jumpSettings.takeoffFade)
        takeoffAt = modeDuration
        if let i = library.index(of: "jump_takeoff") {
            for e in library.clips[i].events where e.name == "takeoff" {
                takeoffAt = min(Double(e.time), modeDuration)
                break
            }
        }
    }

    private func beginFlight(now: Double, events: inout [PonyEvent]) {
        airborne = true
        airTime = 0
        apexEmitted = false
        landedFlag = false
        takeoffVelocity = jumpSettings.takeoffVelocity(sizeScale: sizeScale)
        flightTime = jumpSettings.flightTime(sizeScale: sizeScale)
        events.append(PonyEvent(name: "takeoff", time: now))
    }

    private func updateFlight(dt: Float, now: Double, events: inout [PonyEvent]) {
        if !airborne { return }
        airTime += dt
        if !apexEmitted && airTime >= flightTime * 0.5 {
            apexEmitted = true
            events.append(PonyEvent(name: "apex", time: now))
        }
        let landed: Bool
        if externalLanding {
            landed = landedFlag || airTime >= flightTime + jumpSettings.externalLandingTimeout
        } else {
            landed = landedFlag || airTime >= flightTime
        }
        if landed {
            airborne = false
            landedFlag = false
            events.append(PonyEvent(name: "landing", time: now))
            enterMode(.jumpLand, clip: "jump_land", fade: jumpSettings.landFade)
        }
    }

    private func finishJump(steer: Float) {
        mode = .locomotion
        modeTime = 0
        modeDuration = 0
        let g: PonyGait = jumpGait == .gallop ? .gallop : .canter
        loco.resume(gait: g, speed: jumpSpeed, steer: steer)
        playLocomotion(fade: jumpSettings.recoverFade)
    }

    // MARK: Emplacements de la couche de base (fondus enchaînés)

    private func allocateSlot() -> Int {
        var best = 0
        var bestWeight: Float = .greatestFiniteMagnitude
        for i in slots.indices {
            if !slots[i].active { return i }
            if slots[i].weight < bestWeight {
                bestWeight = slots[i].weight
                best = i
            }
        }
        return best
    }

    private func fadeOutAll(_ fade: Float) {
        let speed = 1 / max(fade, 0.001)
        for i in slots.indices where slots[i].active {
            slots[i].target = 0
            slots[i].fadeSpeed = speed
        }
    }

    private func playClip(_ clip: Int, fade: Float, startTime: Double) {
        fadeOutAll(fade)
        let s = allocateSlot()
        slots[s] = BaseSlot(active: true, isLocomotion: false, clip: clip, time: startTime, weight: 0, target: 1,
                            fadeSpeed: 1 / max(fade, 0.001))
        currentSlot = s
    }

    private func playLocomotion(fade: Float) {
        fadeOutAll(fade)
        var s = -1
        for i in slots.indices where slots[i].active && slots[i].isLocomotion {
            s = i
            break
        }
        if s < 0 {
            s = allocateSlot()
            slots[s] = BaseSlot(active: true, isLocomotion: true, clip: -1, time: 0, weight: 0, target: 1,
                                fadeSpeed: 1 / max(fade, 0.001))
        } else {
            slots[s].target = 1
            slots[s].fadeSpeed = 1 / max(fade, 0.001)
        }
        currentSlot = s
    }

    private static func isRuntimeEvent(_ name: String) -> Bool {
        return name == "takeoff" || name == "landing" || name == "apex"
    }

    private func advanceSlots(dt: Float, sdt: Double, now: Double, events: inout [PonyEvent]) {
        for i in slots.indices where slots[i].active {
            slots[i].weight = PonyMath.moveTowards(slots[i].weight, slots[i].target,
                                                   maxDelta: slots[i].fadeSpeed * dt)
            if !slots[i].isLocomotion {
                let previous = slots[i].time
                slots[i].time += sdt
                let c = slots[i].clip
                if i == currentSlot && c >= 0 && c < library.clips.count {
                    library.clips[c].forEachEvent(from: previous, to: slots[i].time) { e in
                        if !MotionController.isRuntimeEvent(e.name) {
                            events.append(PonyEvent(name: e.name, time: now))
                        }
                    }
                }
            }
            if slots[i].weight <= 0 && slots[i].target <= 0 {
                slots[i].active = false
            }
        }
        if mode == .locomotion && slots[currentSlot].isLocomotion {
            loco.forEachEvent { e in
                if !MotionController.isRuntimeEvent(e.name) {
                    events.append(PonyEvent(name: e.name, time: now))
                }
            }
        }
    }

    // MARK: Couches masquées

    private func playOverlay(_ action: PonyAction, name: String) {
        guard mode == .locomotion || mode == .lying else { return }
        guard let clip = library.index(of: name) else { return }
        for i in overlays.indices where overlays[i].active {
            if overlays[i].clip == clip && !overlays[i].fadingOut && overlays[i].time < 0.3 { return }
            overlays[i].fadingOut = true
        }
        var s = 0
        var bestWeight: Float = .greatestFiniteMagnitude
        for i in overlays.indices {
            if !overlays[i].active {
                s = i
                break
            }
            if overlays[i].weight < bestWeight {
                bestWeight = overlays[i].weight
                s = i
            }
        }
        overlays[s] = OverlaySlot(active: true, clip: clip, action: action, time: 0, weight: 0, fadingOut: false,
                                  maskIndex: action == .neigh ? 1 : 0)
    }

    private func advanceOverlays(dt: Float, sdt: Double, now: Double, events: inout [PonyEvent]) {
        let fadeIn = max(behaviorSettings.overlayFadeIn, 0.01)
        let fadeOut = max(behaviorSettings.overlayFadeOut, 0.01)
        let allowed = mode == .locomotion || mode == .lying
        for i in overlays.indices where overlays[i].active {
            let c = overlays[i].clip
            if c < 0 || c >= library.clips.count {
                overlays[i].active = false
                continue
            }
            let previous = overlays[i].time
            overlays[i].time += sdt
            if !allowed { overlays[i].fadingOut = true }
            if overlays[i].fadingOut {
                overlays[i].weight = PonyMath.moveTowards(overlays[i].weight, 0, maxDelta: dt / fadeOut)
                if overlays[i].weight <= 0 { overlays[i].active = false }
                continue
            }
            let t = overlays[i].time
            let duration = library.clips[c].duration
            let loop = library.clips[c].loop
            let wIn = min(1, Float(t) / fadeIn)
            var wOut: Float = 1
            if !loop {
                wOut = PonyMath.clamp01(Float(duration - t) / fadeOut)
            }
            overlays[i].weight = min(wIn, wOut)
            library.clips[c].forEachEvent(from: previous, to: t) { e in
                if !MotionController.isRuntimeEvent(e.name) {
                    events.append(PonyEvent(name: e.name, time: now))
                }
            }
            if !loop && t >= duration {
                overlays[i].active = false
                overlays[i].weight = 0
            }
        }
    }

    // MARK: Évaluation de la pose

    /// Calcule `pose` (couche de base + couches masquées) et `shapeValues`.
    func evaluate() {
        outer.reset()
        shapeAccumulator.reset()
        let n = pose.count
        for i in slots.indices where slots[i].active && slots[i].weight > 1e-4 {
            let w = slots[i].weight
            if slots[i].isLocomotion {
                loco.evaluate(rest: rest, scratch: &scratchB, accumulator: &inner, out: &scratchA,
                              shapes: &shapeAccumulator, outerWeight: w, clipShapes: clipShapes)
            } else {
                for j in 0..<n {
                    scratchA[j] = rest[j]
                }
                let c = slots[i].clip
                if c >= 0 && c < library.clips.count {
                    let t = slots[i].time
                    library.clips[c].sample(at: t, into: &scratchA)
                    if c < clipShapes.count {
                        for (ti, si) in clipShapes[c].enumerated() where si >= 0 {
                            shapeAccumulator.add(index: si, value: library.clips[c].weightValue(track: ti, at: t),
                                                 weight: w)
                        }
                    }
                }
            }
            shapeAccumulator.addSource(weight: w)
            outer.add(scratchA, weight: w)
        }
        outer.resolve(into: &pose, fallback: rest)
        for s in 0..<shapeValues.count {
            shapeValues[s] = shapeAccumulator.value(s)
        }

        // Couches masquées par-dessus la locomotion (joints hors masque : couche inférieure conservée).
        for i in overlays.indices where overlays[i].active && overlays[i].weight > 1e-4 {
            let c = overlays[i].clip
            if c < 0 || c >= library.clips.count { continue }
            let t = overlays[i].time
            let w = overlays[i].weight
            for j in 0..<n {
                scratchA[j] = pose[j]
            }
            library.clips[c].sample(at: t, into: &scratchA)
            let maskIndex = overlays[i].maskIndex
            PoseAccumulator.blendLayer(base: &pose, layer: scratchA, weight: w, mask: overlayMasks[maskIndex])
            if c < clipShapes.count {
                for (ti, si) in clipShapes[c].enumerated() where si >= 0 {
                    let v = library.clips[c].weightValue(track: ti, at: t)
                    shapeValues[si] = PonyMath.lerp(shapeValues[si], v, w)
                }
            }
        }

        // La racine reste à sa pose de repos (le déplacement est porté par l'entité, SPEC §3).
        for j in rootJoints {
            pose[j] = rest[j]
        }
    }
}
