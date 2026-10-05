import Foundation

/// Paramètres d'un ressort secondaire (raideur k en 1/s², amortissement c en 1/s).
/// Pulsation propre ω = √k ; taux d'amortissement ζ = c / (2√k).
public struct SpringParameters: Sendable, Equatable {
    public var stiffness: Float
    public var damping: Float
    /// Part de la direction « vers le bas » mélangée à la direction animée (0 = suit l'animation, 1 = pendule).
    public var gravityBlend: Float
    /// Écart angulaire maximal par rapport à la direction animée (rad).
    public var maxAngle: Float

    public init(stiffness: Float, damping: Float, gravityBlend: Float, maxAngle: Float) {
        self.stiffness = stiffness
        self.damping = damping
        self.gravityBlend = gravityBlend
        self.maxAngle = maxAngle
    }
}

/// Réglages des couches procédurales (SPEC §8). Valeurs **[A]** (artistiques, à caler à l'œil) sauf mention.
public struct ProceduralSettings: Sendable, Equatable {
    // Regard (étape 5).
    /// Lacet total maximal du regard (rad) — encolure 25–30° par segment latéralement [R anatomy §1.6] ;
    /// la limite globale est un choix de jeu [I].
    public var lookMaxYaw: Float = 1.2
    public var lookMaxPitchUp: Float = 0.6
    public var lookMaxPitchDown: Float = 0.8
    public var lookHalfLife: Float = 0.18
    public var lookFadeDuration: Float = 0.4
    public var eyeMaxAngle: Float = 0.44
    public var saccadeIntervalMin: Float = 1.0
    public var saccadeIntervalMax: Float = 3.5
    public var saccadeAmplitude: Float = 0.07

    // Oreilles (étape 6).
    public var earHalfLife: Float = 0.07
    public var earMoodDurationMin: Float = 4
    public var earMoodDurationMax: Float = 12
    public var earFlickIntervalMin: Float = 0.8
    public var earFlickIntervalMax: Float = 3.5

    // Clignements (étape 7) : intervalle 3–10 s, durée 0,15–0,25 s, demi-clignements occasionnels
    // (valeurs « placeholder » de gaits.md §4, non vérifiées) [U/A].
    public var blinkIntervalMin: Float = 3
    public var blinkIntervalMax: Float = 10
    public var blinkDurationMin: Float = 0.15
    public var blinkDurationMax: Float = 0.25
    public var halfBlinkProbability: Float = 0.2
    /// Angle de fermeture de la paupière supérieure (rotation −X locale) [A].
    public var upperLidCloseAngle: Float = 0.9
    /// Angle de fermeture de la paupière inférieure (rotation +X locale) [A].
    public var lowerLidCloseAngle: Float = 0.25

    // Respiration (étape 7) : 8–16 /min au repos (fourchette clinique courante, non vérifiée) [U] ;
    // couplage 1:1 avec la foulée au galop (Bramble & Carrier 1983, non vérifié) [U].
    public var restingBreathRate: Float = 0.2
    public var maxBreathRate: Float = 1.0
    public var effortRiseTime: Float = 4
    public var effortRecoveryTime: Float = 25
    public var lockBreathToStride: Bool = true

    // Physique secondaire (étape 8).
    public var secondaryEnabled: Bool = true
    public var tailSpring = SpringParameters(stiffness: 60, damping: 7, gravityBlend: 0.25, maxAngle: 1.0)
    public var maneSpring = SpringParameters(stiffness: 120, damping: 10, gravityBlend: 0.15, maxAngle: 0.6)
    public var forelockSpring = SpringParameters(stiffness: 90, damping: 9, gravityBlend: 0.2, maxAngle: 0.6)
    public var bellySpring = SpringParameters(stiffness: 200, damping: 18, gravityBlend: 0, maxAngle: 0.15)
    public var stirrupSpring = SpringParameters(stiffness: 30, damping: 3, gravityBlend: 0.9, maxAngle: 1.2)
    /// Chasse-mouches : intervalle aléatoire entre deux coups de queue à l'arrêt (s) et intensité (m/s).
    public var tailSwishIntervalMin: Float = 6
    public var tailSwishIntervalMax: Float = 20
    public var tailSwishStrength: Float = 2.5

    // Adaptation au sol (optionnelle, `groundHeightProvider`).
    public var groundMaxOffset: Float = 0.15
    public var groundHalfLife: Float = 0.08

    public init() {}
}

/// Indices résolus des joints utilisés par le procédural (noms du manifeste `procedural`, repli SPEC §3).
struct ProceduralRig {
    var body = -1
    var head = -1
    var lookChain: [(joint: Int, weight: Float)] = []
    var neckBend: [Int] = []
    var earLeft = -1
    var earLeftTip = -1
    var earRight = -1
    var earRightTip = -1
    var eyes: [Int] = []
    var eyeLeft = -1
    var eyeRight = -1
    var lidUpperLeft = -1
    var lidLowerLeft = -1
    var lidUpperRight = -1
    var lidLowerRight = -1
    var upperLidAngle: Float? = nil
    var lowerLidAngle: Float? = nil
    var jaw = -1
    var tail: [Int] = []
    var mane: [Int] = []
    var forelock: [Int] = []
    var belly = -1
    var stirrups: [Int] = []
    /// Membres pour l'adaptation au sol : (haut, milieu, bas, sabot).
    var legs: [(upper: Int, mid: Int, lower: Int, hoof: Int)] = []
    var hooves: [Int] = []

    init() {}

    init(skeleton: PonySkeleton, procedural p: PonyRigManifest.Procedural) {
        func idx(_ name: String?) -> Int {
            guard let n = name else { return -1 }
            return skeleton.index(of: n) ?? -1
        }
        func list(_ names: [String], fallback: [String]) -> [Int] {
            let source = names.isEmpty ? fallback : names
            return source.compactMap { skeleton.index(of: $0) }
        }
        body = idx("body")
        head = idx("head")

        // Chaîne du regard : manifeste, sinon répartition par défaut (plus de poids vers la nuque [U]).
        var chain: [(joint: Int, weight: Float)] = []
        if !p.lookChain.isEmpty {
            for e in p.lookChain {
                if let j = skeleton.index(of: e.joint), e.weight > 0 { chain.append((joint: j, weight: e.weight)) }
            }
        }
        if chain.isEmpty {
            let defaults: [(String, Float)] = [("neck_03", 0.10), ("neck_04", 0.15), ("neck_05", 0.20),
                                               ("neck_06", 0.20), ("head", 0.35)]
            for (n, w) in defaults {
                if let j = skeleton.index(of: n) { chain.append((joint: j, weight: w)) }
            }
        }
        var total: Float = 0
        for e in chain {
            total += e.weight
        }
        if total > 0 {
            chain = chain.map { (joint: $0.joint, weight: $0.weight / total) }
        }
        // Ordre parent avant enfant (tri par profondeur dans la hiérarchie).
        func depth(_ joint: Int) -> Int {
            var d = 0
            var p = skeleton.parents[joint]
            while p >= 0 && d < skeleton.count {
                d += 1
                p = skeleton.parents[p]
            }
            return d
        }
        lookChain = chain.sorted { depth($0.joint) < depth($1.joint) }

        neckBend = ["neck_01", "neck_02", "neck_03"].compactMap { skeleton.index(of: $0) }

        let ears = p.ears
        earLeft = idx(ears?.firstString(["left", "l", "ear_l"]) ?? "ear_l")
        earLeftTip = idx(ears?.firstString(["leftTip", "tip_l", "ear_tip_l"]) ?? "ear_tip_l")
        earRight = idx(ears?.firstString(["right", "r", "ear_r"]) ?? "ear_r")
        earRightTip = idx(ears?.firstString(["rightTip", "tip_r", "ear_tip_r"]) ?? "ear_tip_r")

        eyes = list(p.eyes, fallback: ["eye_l", "eye_r"])
        eyeLeft = idx(p.eyes.first(where: { $0.hasSuffix("_l") }) ?? "eye_l")
        eyeRight = idx(p.eyes.first(where: { $0.hasSuffix("_r") }) ?? "eye_r")

        let lids = p.eyelids
        lidUpperLeft = idx(lids?.firstString(["upper_l", "upperLeft", "eyelid_upper_l"]) ?? "eyelid_upper_l")
        lidLowerLeft = idx(lids?.firstString(["lower_l", "lowerLeft", "eyelid_lower_l"]) ?? "eyelid_lower_l")
        lidUpperRight = idx(lids?.firstString(["upper_r", "upperRight", "eyelid_upper_r"]) ?? "eyelid_upper_r")
        lidLowerRight = idx(lids?.firstString(["lower_r", "lowerRight", "eyelid_lower_r"]) ?? "eyelid_lower_r")
        upperLidAngle = lids?.firstFloat(["closeUpper", "upperCloseAngle"])
        lowerLidAngle = lids?.firstFloat(["closeLower", "lowerCloseAngle"])

        jaw = idx(p.jaw ?? "jaw")
        tail = list(p.tail, fallback: (1...10).map { String(format: "tail_%02d", $0) })
        mane = list(p.mane, fallback: (1...6).map { String(format: "mane_%02d", $0) })
        forelock = list(p.forelock, fallback: ["forelock_01", "forelock_02", "forelock_03"])
        belly = idx(p.belly ?? "belly")
        stirrups = list(p.stirrups, fallback: ["stirrup_l", "stirrup_r"])

        let legNames: [(String, String, String, String)] = [
            ("upperarm_l", "forearm_l", "front_cannon_l", "front_hoof_l"),
            ("upperarm_r", "forearm_r", "front_cannon_r", "front_hoof_r"),
            ("thigh_l", "gaskin_l", "hind_cannon_l", "hind_hoof_l"),
            ("thigh_r", "gaskin_r", "hind_cannon_r", "hind_hoof_r"),
        ]
        for (u, m, l, h) in legNames {
            if let iu = skeleton.index(of: u), let im = skeleton.index(of: m), let il = skeleton.index(of: l),
               let ih = skeleton.index(of: h) {
                legs.append((upper: iu, mid: im, lower: il, hoof: ih))
                hooves.append(ih)
            }
        }
    }
}
