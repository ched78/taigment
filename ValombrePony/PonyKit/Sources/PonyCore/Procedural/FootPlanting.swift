import Foundation

/// Plantage des pieds (SPEC §8.4, complément [I]) : compense par IK à deux os les déplacements verticaux des
/// sabots en appui causés (a) par l'inclinaison du tronc en virage et (b) par un sol non plat
/// (`groundHeightProvider`, optionnel).
///
/// Méthode : on mémorise la hauteur des sabots AVANT l'inclinaison ; après, la correction voulue par membre
/// vaut `sol − (hauteur après − hauteur avant)`. Le tronc est abaissé du plus petit décalage (aucun membre
/// n'a à s'allonger au-delà de sa longueur), puis chaque membre en appui est corrigé par IK
/// (haut du membre → milieu → canon), le canon gardant son orientation pour que le sabot suive exactement.
/// Les membres en phase de soutien (sabot levé dans le clip) ne sont pas corrigés.
/// Limite [I] : le tangage du tronc selon la pente n'est pas géré ; un membre déjà presque tendu ne peut
/// pas s'allonger davantage (la cible est alors atteinte partiellement).
struct FootPlanting {
    private var bodyOffset = CriticalSpring()
    private var legOffsets: [CriticalSpring] = []
    private var restHoofHeights: [Float] = []
    private var referenceHeights: [Float] = []
    private var corrections: [Float] = []
    private var stance: [Float] = []
    /// Demi-écartement latéral moyen des sabots (unités du rig) : pivot de l'inclinaison.
    private(set) var hoofHalfWidth: Float = 0.115

    init() {}

    init(rig: ProceduralRig, skeleton: PonySkeleton) {
        let n = rig.legs.count
        legOffsets = [CriticalSpring](repeating: CriticalSpring(), count: n)
        restHoofHeights = rig.legs.map { skeleton.bindModel[$0.hoof].translation.y }
        referenceHeights = restHoofHeights
        corrections = [Float](repeating: 0, count: n)
        stance = [Float](repeating: 0, count: n)
        if n > 0 {
            var sum: Float = 0
            for leg in rig.legs {
                sum += abs(skeleton.bindModel[leg.hoof].translation.x)
            }
            hoofHalfWidth = sum / Float(n)
        }
    }

    mutating func reset() {
        bodyOffset.reset(to: 0)
        for i in legOffsets.indices {
            legOffsets[i].reset(to: 0)
        }
    }

    /// Hauteurs des sabots avant l'inclinaison (`model` à jour).
    mutating func recordReference(rig: ProceduralRig, model: [Transform]) {
        for i in 0..<min(rig.legs.count, referenceHeights.count) {
            referenceHeights[i] = model[rig.legs[i].hoof].translation.y
        }
    }

    /// `model` doit être à jour (FK, après l'inclinaison) ; il est recalculé si la pose change.
    mutating func apply(provider: ((SIMD3<Float>) -> Float?)?, dt: Float, settings: ProceduralSettings,
                        rig: ProceduralRig, skeleton: PonySkeleton, pose: inout [Transform],
                        model: inout [Transform]) {
        let n = min(rig.legs.count, legOffsets.count)
        if n == 0 { return }
        let limit = settings.groundMaxOffset
        var minimum: Float = .greatestFiniteMagnitude
        var anyWork = false
        for i in 0..<n {
            let leg = rig.legs[i]
            let hoof = model[leg.hoof].translation
            var ground: Float = 0
            if let p = provider {
                ground = PonyMath.clamp(PonyMath.finite(p(hoof) ?? 0), -limit, limit)
            }
            let leanDelta = hoof.y - referenceHeights[i]
            corrections[i] = ground - leanDelta
            let lift = referenceHeights[i] - restHoofHeights[i]
            stance[i] = 1 - PonyMath.smoothstep(0.03, 0.12, lift)
            minimum = min(minimum, corrections[i] * stance[i])
            if abs(corrections[i]) > 1e-4 || abs(legOffsets[i].value) > 1e-4 { anyWork = true }
        }
        // Le tronc ne descend que pour le sol (jamais pour l'inclinaison, déjà gérée par le pivot).
        let bodyTarget: Float = provider != nil ? min(0, minimum) : 0
        bodyOffset.update(target: bodyTarget, halfLife: settings.groundHalfLife, deltaTime: dt)
        if !anyWork && abs(bodyOffset.value) < 1e-5 { return }
        let parents = skeleton.parents
        if rig.body >= 0 && abs(bodyOffset.value) > 1e-5 {
            var m = model[rig.body]
            m.translation.y += bodyOffset.value
            PoseEditing.setModel(rig.body, m, pose: &pose, model: &model, parents: parents)
            skeleton.computeModel(local: pose, into: &model)
        }
        var changed = false
        for i in 0..<n {
            legOffsets[i].update(target: (corrections[i] - bodyOffset.value) * stance[i],
                                 halfLife: settings.groundHalfLife, deltaTime: dt)
            let d = PonyMath.clamp(legOffsets[i].value, -limit, limit)
            if abs(d) < 1e-4 { continue }
            let leg = rig.legs[i]
            let a = model[leg.upper].translation
            let b = model[leg.mid].translation
            let c = model[leg.lower].translation
            let lowerModelRotation = model[leg.lower].rotation
            let t = c + SIMD3<Float>(0, d, 0)
            guard let solved = FootPlanting.twoBoneIK(a: a, b: b, c: c, target: t,
                                                      aModel: model[leg.upper].rotation,
                                                      bModel: model[leg.mid].rotation,
                                                      aLocal: pose[leg.upper].rotation,
                                                      bLocal: pose[leg.mid].rotation) else { continue }
            pose[leg.upper].rotation = solved.0
            pose[leg.mid].rotation = solved.1
            // Le canon garde son orientation modèle : le bas du membre se translate sans pivoter.
            PoseEditing.refresh(leg.upper, pose: pose, model: &model, parents: parents)
            PoseEditing.refresh(leg.mid, pose: pose, model: &model, parents: parents)
            pose[leg.lower].rotation = (model[leg.mid].rotation.inverse * lowerModelRotation).normalized
            changed = true
        }
        if changed {
            skeleton.computeModel(local: pose, into: &model)
        }
    }

    /// IK analytique à deux os (forme de D. Holden, « Simple Two Joint IK ») en espace modèle : renvoie les
    /// nouvelles rotations locales du premier et du deuxième os, ou `nil` si la chaîne est dégénérée.
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
