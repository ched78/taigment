import Foundation

/// Noms figés du SPEC (joints §3, blend shapes §5, clips §7) et valeurs de repli quand le manifeste
/// ou les clips ne fournissent pas une donnée.
public enum PonyRigDefaults {

    /// Hauteur au garrot du gabarit de référence (SPEC §2), en mètres.
    public static let referenceWithersHeight: Float = 1.30

    // MARK: Joints (SPEC §3) — ordre USD / PonyRig.json

    /// Table du squelette synthétique : (nom, parent, translation locale, rotation locale [x,y,z,w], longueur d'os).
    ///
    /// Générée à partir de `Pipeline/pony/template.py` (WH = 1,30 m) avec la convention de roulis de
    /// `Pipeline/pony/rig.py` (Y le long de l'os, Z = X_monde × Y, X = Y × Z) et la conversion C du SPEC §1
    /// (locale de `root` = C). Sert de **repli pour les tests et le prototypage** ; le runtime de production
    /// utilise les poses de repos de `PonyRig.json`, qui font foi.
    static let table: [(String, Int, [Float], [Float], Float)] = [
        ("root", -1, [0.000000, 0.000000, 0.000000], [-0.707107, 0.000000, 0.000000, 0.707107], 0.250000),
        ("body", 0, [0.000000, -0.050000, 0.980000], [0.000000, 0.000000, 0.000000, 1.000000], 0.250000),
        ("hips", 1, [0.000000, -0.370000, 0.190000], [-0.999892, -0.000000, -0.000000, 0.014701], 0.340147),
        ("tail_01", 2, [0.000000, 0.369252, -0.030869], [0.369060, 0.000000, 0.000000, 0.929406], 0.084853),
        ("tail_02", 3, [0.000000, 0.084853, 0.000000], [0.160182, 0.000000, 0.000000, 0.987087], 0.089443),
        ("tail_03", 4, [0.000000, 0.089443, 0.000000], [0.109117, 0.000000, 0.000000, 0.994029], 0.082462),
        ("tail_04", 5, [0.000000, 0.082462, 0.000000], [0.067110, 0.000000, 0.000000, 0.997746], 0.090554),
        ("tail_05", 6, [0.000000, 0.090554, 0.000000], [0.030345, 0.000000, 0.000000, 0.999539], 0.100125),
        ("tail_06", 7, [0.000000, 0.100125, -0.000000], [-0.000000, 0.000000, 0.000000, 1.000000], 0.100125),
        ("tail_07", 8, [0.000000, 0.100125, 0.000000], [0.024977, 0.000000, 0.000000, 0.999688], 0.100000),
        ("tail_08", 9, [0.000000, 0.100000, 0.000000], [0.000000, 0.000000, 0.000000, 1.000000], 0.100000),
        ("tail_09", 10, [0.000000, 0.100000, 0.000000], [0.000000, 0.000000, 0.000000, 1.000000], 0.100000),
        ("tail_10", 11, [0.000000, 0.100000, 0.000000], [0.000000, 0.000000, 0.000000, 1.000000], 0.100000),
        ("thigh_l", 2, [-0.130000, 0.184038, 0.134648], [0.874625, -0.033217, 0.018355, 0.483313], 0.329610),
        ("gaskin_l", 13, [-0.000000, 0.329610, -0.000000], [-0.538888, -0.003094, -0.068712, 0.839565], 0.400961),
        ("hind_cannon_l", 14, [0.000000, 0.400961, 0.000000], [0.305778, 0.019116, 0.023762, 0.951614], 0.266938),
        ("hind_pastern_l", 15, [0.000000, 0.266938, 0.000000], [0.265224, 0.004970, 0.018063, 0.964005], 0.127063),
        ("hind_hoof_l", 16, [0.000000, 0.127063, 0.000000], [0.170617, 0.000000, 0.000000, 0.985337], 0.079630),
        ("thigh_r", 2, [0.130000, 0.184038, 0.134648], [0.874625, 0.033217, -0.018355, 0.483313], 0.329610),
        ("gaskin_r", 18, [0.000000, 0.329610, -0.000000], [-0.538888, 0.003094, 0.068712, 0.839565], 0.400961),
        ("hind_cannon_r", 19, [0.000000, 0.400961, 0.000000], [0.305778, -0.019116, -0.023762, 0.951614], 0.266938),
        ("hind_pastern_r", 20, [0.000000, 0.266938, 0.000000], [0.265224, -0.004970, -0.018063, 0.964005], 0.127063),
        ("hind_hoof_r", 21, [0.000000, 0.127063, 0.000000], [0.170617, 0.000000, 0.000000, 0.985337], 0.079630),
        ("spine_01", 1, [0.000000, -0.370000, 0.190000], [-0.035646, 0.000000, 0.000000, 0.999364], 0.280713),
        ("spine_02", 23, [0.000000, 0.280713, 0.000000], [-0.035287, 0.000000, 0.000000, 0.999377], 0.282843),
        ("belly", 24, [0.000000, 0.086267, -0.321026], [-0.655202, 0.000000, 0.000000, 0.755454], 0.120000),
        ("stirrup_l", 24, [-0.170000, 0.333754, 0.067882], [-0.653220, 0.050922, 0.058713, 0.753169], 0.516236),
        ("stirrup_r", 24, [0.170000, 0.333754, 0.067882], [-0.653220, -0.050922, -0.058713, 0.753169], 0.516236),
        ("spine_03", 24, [0.000000, 0.282843, 0.000000], [-0.131119, 0.000000, 0.000000, 0.991367], 0.304631),
        ("scapula_l", 28, [-0.070000, 0.139185, 0.157568], [-0.239730, 0.026751, 0.107625, 0.964485], 0.408289),
        ("upperarm_l", 29, [0.000000, 0.408289, -0.000000], [-0.644675, 0.045007, -0.115969, 0.754268], 0.241661),
        ("forearm_l", 30, [-0.000000, 0.241661, 0.000000], [0.354692, 0.022108, 0.019260, 0.934523], 0.360312),
        ("front_cannon_l", 31, [-0.000000, 0.360312, 0.000000], [0.000000, 0.000000, -0.002636, 0.999997], 0.213235),
        ("front_pastern_l", 32, [-0.000000, 0.213235, 0.000000], [0.340839, 0.007997, 0.022050, 0.939829], 0.118562),
        ("front_hoof_l", 33, [0.000000, 0.118562, 0.000000], [0.142996, 0.000000, 0.000000, 0.989723], 0.082928),
        ("scapula_r", 28, [0.070000, 0.139185, 0.157568], [-0.239730, -0.026751, -0.107625, 0.964485], 0.408289),
        ("upperarm_r", 35, [-0.000000, 0.408289, -0.000000], [-0.644675, -0.045007, 0.115969, 0.754268], 0.241661),
        ("forearm_r", 36, [0.000000, 0.241661, 0.000000], [0.354692, -0.022108, -0.019260, 0.934523], 0.360312),
        ("front_cannon_r", 37, [0.000000, 0.360312, 0.000000], [0.000000, 0.000000, 0.002636, 0.999997], 0.213235),
        ("front_pastern_r", 38, [0.000000, 0.213235, 0.000000], [0.340839, -0.007997, -0.022050, 0.939829], 0.118562),
        ("front_hoof_r", 39, [0.000000, 0.118562, 0.000000], [0.142996, 0.000000, 0.000000, 0.989723], 0.082928),
        ("neck_01", 28, [0.000000, 0.357153, -0.021009], [0.538666, 0.000000, 0.000000, 0.842519], 0.134536),
        ("neck_02", 41, [0.000000, 0.134536, 0.000000], [0.052559, 0.000000, 0.000000, 0.998618], 0.134536),
        ("neck_03", 42, [0.000000, 0.134536, 0.000000], [0.051986, 0.000000, 0.000000, 0.998648], 0.136015),
        ("neck_04", 43, [0.000000, 0.136015, 0.000000], [-0.016123, 0.000000, 0.000000, 0.999870], 0.114018),
        ("neck_05", 44, [0.000000, 0.114018, 0.000000], [-0.062137, 0.000000, 0.000000, 0.998068], 0.084853),
        ("neck_06", 45, [0.000000, 0.084853, -0.000000], [-0.070889, 0.000000, 0.000000, 0.997484], 0.050000),
        ("head", 46, [0.000000, 0.050000, -0.000000], [-0.655202, 0.000000, 0.000000, 0.755454], 0.494975),
        ("jaw", 47, [0.000000, 0.079974, -0.020011], [-0.070003, 0.000000, 0.000000, 0.997547], 0.393901),
        ("lip_lower", 48, [0.000000, 0.383327, 0.003579], [0.070003, 0.000000, 0.000000, 0.997547], 0.049922),
        ("lip_upper", 47, [0.000000, 0.450003, -0.010041], [-0.070184, 0.000000, 0.000000, 0.997534], 0.070700),
        ("ear_l", 47, [-0.055000, -0.000000, 0.070004], [0.872223, -0.065013, 0.036033, 0.483427], 0.067454),
        ("ear_tip_l", 51, [0.000000, 0.067454, 0.000000], [0.036833, -0.004155, -0.036425, 0.998649], 0.065955),
        ("ear_r", 47, [0.055000, -0.000000, 0.070004], [0.872223, 0.065013, -0.036033, 0.483427], 0.067454),
        ("ear_tip_r", 53, [-0.000000, 0.067454, 0.000000], [0.036833, 0.004155, 0.036425, 0.998649], 0.065955),
        ("eye_l", 47, [-0.080000, 0.170059, 0.020011], [0.336143, -0.182906, 0.441575, 0.811520], 0.030012),
        ("eyelid_upper_l", 47, [-0.080000, 0.170059, 0.020011], [0.336435, -0.182368, 0.440276, 0.812226], 0.026017),
        ("eyelid_lower_l", 47, [-0.080000, 0.170059, 0.020011], [0.336260, -0.182691, 0.441054, 0.811803], 0.022051),
        ("eye_r", 47, [0.080000, 0.170059, 0.020011], [0.336143, 0.182906, -0.441575, 0.811520], 0.030012),
        ("eyelid_upper_r", 47, [0.080000, 0.170059, 0.020011], [0.336435, 0.182368, -0.440276, 0.812226], 0.026017),
        ("eyelid_lower_r", 47, [0.080000, 0.170059, 0.020011], [0.336260, 0.182691, -0.441054, 0.811803], 0.022051),
        ("forelock_01", 47, [0.000000, 0.020011, 0.075024], [0.061975, 0.000000, 0.000000, 0.998078], 0.080593),
        ("forelock_02", 61, [0.000000, 0.080593, 0.000000], [-0.030662, 0.000000, 0.000000, 0.999530], 0.080131),
        ("forelock_03", 62, [0.000000, 0.080131, 0.000000], [-0.031342, 0.000000, 0.000000, 0.999509], 0.080044),
        ("mane_01", 41, [0.000000, 0.154605, 0.291371], [-0.880354, -0.243844, -0.108599, 0.392076], 0.116619),
        ("mane_02", 42, [0.000000, 0.154605, 0.246774], [-0.899744, -0.249215, -0.095633, 0.345264], 0.116619),
        ("mane_03", 43, [0.000000, 0.144837, 0.191891], [-0.916476, -0.253849, -0.082548, 0.298023], 0.116619),
        ("mane_04", 44, [0.000000, 0.097353, 0.151731], [-0.911552, -0.252485, -0.086630, 0.312761], 0.116619),
        ("mane_05", 45, [0.000000, 0.049497, 0.120208], [-0.890356, -0.246614, -0.102151, 0.368798], 0.116619),
        ("mane_06", 46, [0.000000, 0.022000, 0.096000], [-0.861973, -0.238753, -0.119376, 0.430986], 0.116619),
    ]

    /// Les 70 noms de joints du SPEC §3, dans l'ordre.
    public static let jointNames: [String] = table.map { $0.0 }

    /// Longueur d'os du gabarit (m, WH 1,30) par nom — sert aux chaînes secondaires quand le manifeste ne
    /// donne que les têtes d'os (pas de « queue »).
    public static let boneLengths: [String: Float] = {
        var d: [String: Float] = [:]
        for e in table {
            d[e.0] = e.4
        }
        return d
    }()

    /// Manifeste **synthétique** (squelette du gabarit, aucune pièce, aucun clip) : pour les tests et le
    /// prototypage sans `PonyRig.json`. Les `bindModel` sont la FK de la pose de repos.
    public static func syntheticManifest() -> PonyRigManifest {
        var joints: [PonyRigManifest.Joint] = []
        var paths: [String] = []
        for e in table {
            let t = SIMD3<Float>(e.2[0], e.2[1], e.2[2])
            let r = Quat(x: e.3[0], y: e.3[1], z: e.3[2], w: e.3[3]).normalized
            let path = e.1 >= 0 ? paths[e.1] + "/" + e.0 : e.0
            paths.append(path)
            joints.append(PonyRigManifest.Joint(name: e.0, path: path, parent: e.1,
                                                rest: Transform(translation: t, rotation: r)))
        }
        let skeleton = PonySkeleton(names: joints.map { $0.name }, parents: joints.map { $0.parent },
                                    restLocal: joints.map { $0.rest })
        for i in 0..<joints.count {
            joints[i].bindModel = skeleton.bindModel[i].columnMajor
        }
        return PonyRigManifest(joints: joints,
                               blendShapes: ["body": morphologyShapes + proportionShapes + expressionShapes],
                               parts: PonyPartCatalog.specParts)
    }

    // MARK: Blend shapes (SPEC §5)

    public static let morphologyShapes: [String] = [
        "shape_stocky", "shape_refined", "shape_fat", "shape_thin", "shape_muscular", "shape_belly",
        "shape_crest", "shape_bone_heavy", "head_dished", "head_roman", "head_short", "muzzle_broad",
        "hooves_large",
    ]

    public static let proportionShapes: [String] = [
        "prop_legs_long", "prop_legs_short", "prop_neck_long", "prop_neck_short",
        "prop_body_long", "prop_body_short",
    ]

    public static let expressionShapes: [String] = [
        "face_nostril_flare", "face_flehmen", "face_brow_worry", "face_mouth_open_soft", "body_breathe",
    ]

    // MARK: Clips (SPEC §7)

    /// Valeurs de repli d'un clip (quand le manifeste ne les donne pas) : tableau du SPEC §7.
    public struct ClipDefaults: Sendable, Equatable {
        public var loop: Bool
        public var duration: Float
        /// Vitesse avant (m/s) ; négative pour le reculer.
        public var forwardSpeed: Float
        /// Lacet (rad/s), positif = vers la gauche (rotation directe autour de +Y).
        public var yawRate: Float
    }

    public static let clipDefaults: [String: ClipDefaults] = [
        "idle": ClipDefaults(loop: true, duration: 6.0, forwardSpeed: 0, yawRate: 0),
        "idle_rest_hind": ClipDefaults(loop: true, duration: 6.0, forwardSpeed: 0, yawRate: 0),
        "walk": ClipDefaults(loop: true, duration: 1.05, forwardSpeed: 1.4, yawRate: 0),
        "trot": ClipDefaults(loop: true, duration: 0.66, forwardSpeed: 3.0, yawRate: 0),
        "canter_left": ClipDefaults(loop: true, duration: 0.57, forwardSpeed: 4.8, yawRate: 0),
        "canter_right": ClipDefaults(loop: true, duration: 0.57, forwardSpeed: 4.8, yawRate: 0),
        "gallop": ClipDefaults(loop: true, duration: 0.46, forwardSpeed: 8.0, yawRate: 0),
        "back": ClipDefaults(loop: true, duration: 1.2, forwardSpeed: -0.6, yawRate: 0),
        "turn_left": ClipDefaults(loop: true, duration: 1.4, forwardSpeed: 0, yawRate: 1.2),
        "turn_right": ClipDefaults(loop: true, duration: 1.4, forwardSpeed: 0, yawRate: -1.2),
        "jump_takeoff": ClipDefaults(loop: false, duration: 0.5, forwardSpeed: 0, yawRate: 0),
        "jump_air": ClipDefaults(loop: true, duration: 0.4, forwardSpeed: 0, yawRate: 0),
        "jump_land": ClipDefaults(loop: false, duration: 0.6, forwardSpeed: 0, yawRate: 0),
        "graze_down": ClipDefaults(loop: false, duration: 1.5, forwardSpeed: 0, yawRate: 0),
        "graze_loop": ClipDefaults(loop: true, duration: 5.0, forwardSpeed: 0, yawRate: 0),
        "graze_up": ClipDefaults(loop: false, duration: 1.2, forwardSpeed: 0, yawRate: 0),
        "rear": ClipDefaults(loop: false, duration: 2.6, forwardSpeed: 0, yawRate: 0),
        "head_shake": ClipDefaults(loop: false, duration: 1.2, forwardSpeed: 0, yawRate: 0),
        "neigh": ClipDefaults(loop: false, duration: 2.2, forwardSpeed: 0, yawRate: 0),
        "paw": ClipDefaults(loop: true, duration: 1.6, forwardSpeed: 0, yawRate: 0),
        "lie_down": ClipDefaults(loop: false, duration: 3.0, forwardSpeed: 0, yawRate: 0),
        "lying": ClipDefaults(loop: true, duration: 6.0, forwardSpeed: 0, yawRate: 0),
        "get_up": ClipDefaults(loop: false, duration: 2.5, forwardSpeed: 0, yawRate: 0),
        "roll": ClipDefaults(loop: false, duration: 4.5, forwardSpeed: 0, yawRate: 0),
        "body_shake": ClipDefaults(loop: false, duration: 1.5, forwardSpeed: 0, yawRate: 0),
    ]

    /// Noms des clips du SPEC §7.
    public static var clipNames: [String] {
        return clipDefaults.keys.sorted()
    }
}
