import XCTest
@testable import PonyCore

final class LocomotionTests: XCTestCase {

    private typealias Slot = LocomotionController.Slot

    private func makeController(seed: UInt64 = 3) -> LocomotionController {
        let m = CoreTestSupport.manifest()
        var rng = PonyRandom(seed: seed)
        return LocomotionController(library: CoreTestSupport.library(m), settings: LocomotionSettings(), random: &rng)
    }

    /// Avance à 60 Hz ; `moveX`/`moveY` sont des entrées effectives (zone morte déjà appliquée).
    private func step(_ c: LocomotionController, seconds: Float, moveX: Float = 0, moveY: Float, sprint: Bool = false,
                      check: ((LocomotionController) -> Void)? = nil) {
        var rng = PonyRandom(seed: 9)
        for _ in 0..<Int((seconds * 60).rounded()) {
            c.update(dt: 1.0 / 60.0, moveX: moveX, moveY: moveY, sprint: sprint, inputEnabled: true, timeScale: 1,
                     random: &rng)
            check?(c)
        }
    }

    func testStartsIdleThenWalksWithIdleBlendAndConsistentVelocity() {
        let c = makeController()
        XCTAssertEqual(c.gait, .idle)
        XCTAssertEqual(c.weight[Slot.idle.rawValue], 1)
        step(c, seconds: 0.2, moveY: 0.2)                       // 0,96 m/s commandés
        XCTAssertEqual(c.gait, .walk)
        step(c, seconds: 4, moveY: 0.2)
        XCTAssertEqual(c.speed, 0.96, accuracy: 0.01)
        // Sous la bande du pas : mélange idle/pas à cadence minimale ; la vitesse impliquée par la pose
        // (Σ wᵢ·cadenceᵢ·vᵢ) égale la vitesse de déplacement : pas de patinage.
        XCTAssertGreaterThan(c.weight[Slot.idle.rawValue], 0.05)
        XCTAssertEqual(c.rate[Slot.walk.rawValue], 1 - c.settings.playbackTolerance, accuracy: 1e-5)
        XCTAssertEqual(-c.poseVelocity.z, c.speed, accuracy: 0.02)
    }

    func testPlaybackRateStaysWithinTolerance() {
        let c = makeController()
        let tol = c.settings.playbackTolerance
        step(c, seconds: 10, moveY: 1) { c in
            for slot in Slot.allCases where slot.isCyclic && c.weight[slot.rawValue] > 0 {
                XCTAssertGreaterThanOrEqual(c.rate[slot.rawValue], 1 - tol - 1e-5)
                XCTAssertLessThanOrEqual(c.rate[slot.rawValue], 1 + tol + 1e-5)
            }
        }
        XCTAssertEqual(c.gait, .canter)
    }

    func testWalkTrotHysteresis() {
        let c = makeController()
        step(c, seconds: 6, moveY: 0.5)                         // 2,4 m/s → trot (seuil de montée 1,85)
        XCTAssertEqual(c.gait, .trot)
        XCTAssertEqual(c.speed, c.band(.trot).min, accuracy: 0.01)

        var changes = 0
        var last = c.gait
        let counter: (LocomotionController) -> Void = { c in
            if c.gait != last {
                changes += 1
                last = c.gait
            }
        }
        step(c, seconds: 4, moveY: 1.7 / 4.8, check: counter)  // 1,7 > seuil de descente 1,55 : reste au trot
        XCTAssertEqual(c.gait, .trot)
        XCTAssertEqual(changes, 0)

        step(c, seconds: 4, moveY: 1.3 / 4.8)                  // 1,3 < 1,55 : redescend au pas
        XCTAssertEqual(c.gait, .walk)
        last = c.gait
        changes = 0
        step(c, seconds: 4, moveY: 1.7 / 4.8, check: counter)  // 1,7 < seuil de montée 1,85 : reste au pas
        XCTAssertEqual(c.gait, .walk)
        XCTAssertEqual(changes, 0)
    }

    func testPhaseIsContinuousAcrossGaitTransitions() {
        let c = makeController()
        var previous = c.cycles
        var maxStep = 0.0
        var minStep = 1.0
        var sawWalkTrotBlend = false
        var sawTrotCanterBlend = false
        step(c, seconds: 9, moveY: 0.9) { c in
            let d = c.cycles - previous
            maxStep = max(maxStep, d)
            minStep = min(minStep, d)
            previous = c.cycles
            if c.weight[Slot.walk.rawValue] > 0.1 && c.weight[Slot.trot.rawValue] > 0.1 { sawWalkTrotBlend = true }
            if c.weight[Slot.trot.rawValue] > 0.1 && c.weight[Slot.canterLeft.rawValue] > 0.1 {
                sawTrotCanterBlend = true
            }
        }
        XCTAssertTrue(sawWalkTrotBlend)
        XCTAssertTrue(sawTrotCanterBlend)
        // Phase monotone, sans remise à zéro ni saut pendant les fondus (≤ fréquence max × dt).
        XCTAssertGreaterThanOrEqual(minStep, 0)
        XCTAssertLessThan(maxStep, 0.05)
        XCTAssertEqual(c.gait, .canter)
        XCTAssertEqual(c.lead, .canterLeft)                    // ligne droite : pied gauche par défaut
    }

    func testCanterLeadFollowsTurnAndFlyingChange() {
        let c = makeController()
        step(c, seconds: 9, moveX: 0.6, moveY: 1)              // virage à droite
        XCTAssertEqual(c.gait, .canter)
        XCTAssertEqual(c.lead, .canterRight)
        step(c, seconds: 2, moveX: -0.6, moveY: 1)             // virage à gauche soutenu → changement de pied
        XCTAssertEqual(c.lead, .canterLeft)
        XCTAssertEqual(c.weight[Slot.canterLeft.rawValue], 1, accuracy: 1e-5)
        XCTAssertEqual(c.weight[Slot.canterRight.rawValue], 0, accuracy: 1e-5)
    }

    func testTurnRateLimitedByGaitRadius() {
        let c = makeController()
        step(c, seconds: 4, moveX: 1, moveY: 1.4 / 4.8)
        XCTAssertEqual(c.gait, .walk)
        let walkLimit = min(c.settings.maxYawRate, max(c.speed, c.settings.minTurnSpeed) / c.settings.walkMinTurnRadius)
        XCTAssertEqual(c.yawRate, -walkLimit, accuracy: 0.02)   // droite = lacet négatif
        step(c, seconds: 14, moveX: 1, moveY: 1, sprint: true)
        XCTAssertEqual(c.gait, .gallop)
        let gallopLimit = c.speed / c.settings.gallopMinTurnRadius
        XCTAssertLessThanOrEqual(abs(c.yawRate), gallopLimit + 1e-3)
        XCTAssertGreaterThan(abs(c.yawRate), 0.5)
    }

    func testBackAndTurnInPlace() {
        let c = makeController()
        step(c, seconds: 2, moveY: -1)
        XCTAssertEqual(c.gait, .back)
        XCTAssertGreaterThan(c.poseVelocity.z, 0.3)            // recule : +Z
        step(c, seconds: 2, moveY: 0)
        XCTAssertEqual(c.gait, .idle)
        step(c, seconds: 2, moveX: 1, moveY: 0)
        XCTAssertEqual(c.gait, .turnInPlace)
        XCTAssertEqual(c.yawRate, -1.2 * (1 + c.settings.playbackTolerance), accuracy: 0.01)
        XCTAssertEqual(c.poseVelocity.z, 0, accuracy: 1e-5)
        step(c, seconds: 2, moveX: -1, moveY: 0)
        XCTAssertGreaterThan(c.yawRate, 1.0)
    }

    func testIdleRestVariantAppearsAfterAWhile() {
        let c = makeController()
        var rested = false
        step(c, seconds: 45, moveY: 0) { c in
            if c.weight[Slot.idleRest.rawValue] > 0.9 { rested = true }
        }
        XCTAssertTrue(rested)
        step(c, seconds: 1, moveY: 0.5)                         // le mouvement interrompt le repos
        XCTAssertFalse(c.resting)
    }

    func testResumeAfterJumpUsesCanterBand() {
        let c = makeController()
        c.resume(gait: .canter, speed: 1.0, steer: 0.5)
        XCTAssertEqual(c.gait, .canter)
        XCTAssertEqual(c.lead, .canterRight)
        XCTAssertEqual(c.speed, c.band(.canter).min, accuracy: 1e-5)
        XCTAssertEqual(c.weight[Slot.canterRight.rawValue], 1)
    }
}
