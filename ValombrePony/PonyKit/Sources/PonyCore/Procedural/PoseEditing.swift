import Foundation

/// Outils d'édition d'une pose locale à partir de cibles exprimées en espace modèle.
/// `pose` = transformations locales, `model` = FK correspondante (tenue à jour pour les joints édités).
enum PoseEditing {

    /// Applique une rotation `delta` exprimée en espace modèle autour de l'origine du joint `j` :
    /// locale' = P⁻¹ · Δ · P · locale (P = rotation modèle du parent). Met à jour `model[j]`
    /// (rotation ; la position du joint ne change pas). Les descendants ne sont PAS mis à jour.
    static func rotateInModelSpace(_ j: Int, _ delta: Quat, pose: inout [Transform], model: inout [Transform],
                                   parents: [Int]) {
        let p = parents[j]
        let parentRotation = p >= 0 ? model[p].rotation : Quat.identity
        let local = parentRotation.inverse * delta * parentRotation * pose[j].rotation
        pose[j].rotation = local.normalized
        model[j].rotation = (delta * model[j].rotation).normalized
    }

    /// Recalcule `model[j]` à partir du modèle (à jour) de son parent.
    static func refresh(_ j: Int, pose: [Transform], model: inout [Transform], parents: [Int]) {
        let p = parents[j]
        model[j] = p >= 0 ? model[p] * pose[j] : pose[j]
    }

    /// Impose la transformation modèle `target` au joint `j` (calcule la locale correspondante).
    static func setModel(_ j: Int, _ target: Transform, pose: inout [Transform], model: inout [Transform],
                         parents: [Int]) {
        let p = parents[j]
        pose[j] = p >= 0 ? model[p].inverse * target : target
        model[j] = target
    }

    /// Azimut (rad) d'une direction en espace modèle : 0 = avant (−Z), positif = vers la gauche (−X).
    static func azimuth(_ v: SIMD3<Float>) -> Float {
        return atan2(-v.x, -v.z)
    }

    /// Élévation (rad) d'une direction : positive vers le haut.
    static func elevation(_ v: SIMD3<Float>) -> Float {
        let h = (v.x * v.x + v.z * v.z).squareRoot()
        return atan2(v.y, h)
    }
}

/// Inclinaison du tronc et incurvation de l'encolure en virage (SPEC §8.4).
struct TurnPostureLayer {
    var lean = CriticalSpring()
    var bend = CriticalSpring()

    /// - Parameters: `speed` vitesse avant réelle (m/s), `yawRate` lacet réel (rad/s, + = gauche).
    mutating func update(dt: Float, speed: Float, yawRate: Float, enabled: Bool, settings: LocomotionSettings) {
        var targetLean: Float = 0
        var targetBend: Float = 0
        if enabled {
            // θ = atan(v·ω/g) : inclinaison du centre de masse vers l'intérieur [D, gaits.md §5.3].
            targetLean = PonyMath.clamp(atan(speed * yawRate / PonyMath.gravity),
                                        -settings.maxLeanAngle, settings.maxLeanAngle)
            let maxYaw = max(settings.maxYawRate, 0.1)
            targetBend = PonyMath.clamp(yawRate / maxYaw, -1, 1) * settings.maxNeckBend
        }
        lean.update(target: targetLean, halfLife: settings.leanHalfLife, deltaTime: dt)
        bend.update(target: targetBend, halfLife: 0.25, deltaTime: dt)
    }

    /// Roulis du joint `body` autour de l'origine du modèle (centre du polygone d'appui au sol), donc des
    /// sabots : tout le poney s'incline dans le virage. `model` doit être à jour pour `body` et son parent.
    func applyLean(rig: ProceduralRig, pose: inout [Transform], model: inout [Transform], parents: [Int]) {
        let b = rig.body
        if b < 0 || abs(lean.value) < 1e-5 { return }
        let d = Quat(axis: SIMD3<Float>(0, 0, 1), angle: lean.value)
        var m = model[b]
        m.translation = d.act(m.translation)
        m.rotation = (d * m.rotation).normalized
        PoseEditing.setModel(b, m, pose: &pose, model: &model, parents: parents)
    }

    /// Incurvation : lacet réparti sur la base de l'encolure (vers l'intérieur du virage) [A].
    func applyBend(rig: ProceduralRig, pose: inout [Transform], model: inout [Transform], parents: [Int]) {
        let count = rig.neckBend.count
        if count == 0 || abs(bend.value) < 1e-5 { return }
        let share = bend.value / Float(count)
        for j in rig.neckBend {
            PoseEditing.refresh(j, pose: pose, model: &model, parents: parents)
            let d = Quat(axis: SIMD3<Float>(0, 1, 0), angle: share)
            PoseEditing.rotateInModelSpace(j, d, pose: &pose, model: &model, parents: parents)
        }
    }
}
