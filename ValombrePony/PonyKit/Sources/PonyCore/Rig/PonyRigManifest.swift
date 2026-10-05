import Foundation

/// Manifeste du rig : décodage de `PonyRig.json` (SPEC §9).
///
/// Toutes les données géométriques sont en espace RealityKit (Y haut, −Z avant), quaternions `[x, y, z, w]`.
/// Le décodage est **tolérant** : chaque champ absent prend une valeur par défaut (`decodeIfPresent`), pour
/// rester compatible avec les évolutions du pipeline. Seul `joints` est réellement indispensable au runtime.
public struct PonyRigManifest: Codable, Sendable {
    public var format: String
    public var version: Int
    public var units: String
    public var upAxis: String
    public var forward: String
    public var fps: Float
    public var joints: [Joint]
    /// Blend shapes par maillage : `{ "body": ["shape_stocky", …], … }`.
    public var blendShapes: [String: [String]]
    public var parts: [Part]
    public var clips: [Clip]
    public var procedural: Procedural
    public var morphology: Morphology
    public var coat: PonyJSONValue?

    public init(format: String = "ValombrePonyRig", version: Int = 1, units: String = "m",
                upAxis: String = "Y", forward: String = "-Z", fps: Float = 30,
                joints: [Joint], blendShapes: [String: [String]] = [:], parts: [Part] = [],
                clips: [Clip] = [], procedural: Procedural = Procedural(),
                morphology: Morphology = Morphology(), coat: PonyJSONValue? = nil) {
        self.format = format
        self.version = version
        self.units = units
        self.upAxis = upAxis
        self.forward = forward
        self.fps = fps
        self.joints = joints
        self.blendShapes = blendShapes
        self.parts = parts
        self.clips = clips
        self.procedural = procedural
        self.morphology = morphology
        self.coat = coat
    }

    /// Décode un manifeste à partir des octets de `PonyRig.json`.
    public static func decode(from data: Data) throws -> PonyRigManifest {
        return try JSONDecoder().decode(PonyRigManifest.self, from: data)
    }

    private enum CodingKeys: String, CodingKey {
        case format, version, units, upAxis, forward, fps, joints, blendShapes, parts, clips
        case procedural, morphology, coat
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        format = try c.decodeIfPresent(String.self, forKey: .format) ?? "ValombrePonyRig"
        version = try c.decodeIfPresent(Int.self, forKey: .version) ?? 1
        units = try c.decodeIfPresent(String.self, forKey: .units) ?? "m"
        upAxis = try c.decodeIfPresent(String.self, forKey: .upAxis) ?? "Y"
        forward = try c.decodeIfPresent(String.self, forKey: .forward) ?? "-Z"
        fps = try c.decodeIfPresent(Float.self, forKey: .fps) ?? 30
        joints = try c.decodeIfPresent([Joint].self, forKey: .joints) ?? []
        blendShapes = try c.decodeIfPresent([String: [String]].self, forKey: .blendShapes) ?? [:]
        parts = try c.decodeIfPresent([Part].self, forKey: .parts) ?? []
        clips = try c.decodeIfPresent([Clip].self, forKey: .clips) ?? []
        procedural = try c.decodeIfPresent(Procedural.self, forKey: .procedural) ?? Procedural()
        morphology = try c.decodeIfPresent(Morphology.self, forKey: .morphology) ?? Morphology()
        coat = try c.decodeIfPresent(PonyJSONValue.self, forKey: .coat)
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(format, forKey: .format)
        try c.encode(version, forKey: .version)
        try c.encode(units, forKey: .units)
        try c.encode(upAxis, forKey: .upAxis)
        try c.encode(forward, forKey: .forward)
        try c.encode(fps, forKey: .fps)
        try c.encode(joints, forKey: .joints)
        try c.encode(blendShapes, forKey: .blendShapes)
        try c.encode(parts, forKey: .parts)
        try c.encode(clips, forKey: .clips)
        try c.encode(procedural, forKey: .procedural)
        try c.encode(morphology, forKey: .morphology)
        try c.encodeIfPresent(coat, forKey: .coat)
    }

    // MARK: - Joint

    public struct Joint: Codable, Sendable, Equatable {
        public var name: String
        /// Chemin USD (`root/body/…`) ; le runtime adresse les joints par `name`.
        public var path: String
        /// Indice du parent dans `joints` (−1 pour la racine).
        public var parent: Int
        /// Transformation locale de repos (parent → joint).
        public var rest: Transform
        /// Repère de liaison en espace modèle : 16 flottants, colonnes majeures (vide si absent).
        public var bindModel: [Float]

        public init(name: String, path: String = "", parent: Int, rest: Transform, bindModel: [Float] = []) {
            self.name = name
            self.path = path.isEmpty ? name : path
            self.parent = parent
            self.rest = rest
            self.bindModel = bindModel
        }

        private enum CodingKeys: String, CodingKey {
            case name, path, parent, rest, bindModel
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            name = try c.decode(String.self, forKey: .name)
            path = try c.decodeIfPresent(String.self, forKey: .path) ?? name
            parent = try c.decodeIfPresent(Int.self, forKey: .parent) ?? -1
            rest = try c.decodeIfPresent(Transform.self, forKey: .rest) ?? .identity
            bindModel = try c.decodeIfPresent([Float].self, forKey: .bindModel) ?? []
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(name, forKey: .name)
            try c.encode(path, forKey: .path)
            try c.encode(parent, forKey: .parent)
            try c.encode(rest, forKey: .rest)
            try c.encode(bindModel, forKey: .bindModel)
        }
    }

    // MARK: - Part (crins et accessoires, SPEC §6)

    public struct Part: Codable, Sendable, Equatable {
        public var id: String
        public var file: String
        /// `hair`, `tack`, `protection`, `decoration`, `rug` (texte libre côté pipeline).
        public var category: String
        /// Emplacements occupés (une pièce peut en occuper plusieurs, ex. guêtres : `legs_front`, `legs_hind`).
        public var slots: [String]
        public var materialSlots: [String]
        /// Matériaux non personnalisables (`fixed_*`).
        public var fixedMaterials: [String]
        public var fabricSlots: [String]
        public var blendShapes: [String]
        /// Identifiants de pièces **ou** noms d'emplacements incompatibles.
        public var conflicts: [String]
        /// Prérequis : au moins UN des éléments (identifiant de pièce ou nom d'emplacement) doit être présent.
        public var requires: [String]
        /// Pièces (identifiants ou emplacements) masquées quand cette pièce est portée.
        public var hides: [String]

        /// Premier emplacement (champ `slot` du SPEC).
        public var slot: String {
            return slots.first ?? ""
        }

        public init(id: String, file: String = "", category: String = "", slots: [String],
                    materialSlots: [String] = [], fixedMaterials: [String] = [], fabricSlots: [String] = [],
                    blendShapes: [String] = [], conflicts: [String] = [], requires: [String] = [],
                    hides: [String] = []) {
            self.id = id
            self.file = file.isEmpty ? "Parts/\(id).usdz" : file
            self.category = category
            self.slots = slots
            self.materialSlots = materialSlots
            self.fixedMaterials = fixedMaterials
            self.fabricSlots = fabricSlots
            self.blendShapes = blendShapes
            self.conflicts = conflicts
            self.requires = requires
            self.hides = hides
        }

        private enum CodingKeys: String, CodingKey {
            case id, file, category, slot, slots, materialSlots, fixedMaterials, fabricSlots, blendShapes
            case conflicts, requires, hides
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id)
            file = try c.decodeIfPresent(String.self, forKey: .file) ?? "Parts/\(id).usdz"
            category = try c.decodeIfPresent(String.self, forKey: .category) ?? ""
            var decodedSlots: [String] = []
            // `slot` peut être une chaîne ou un tableau ; `slots` (tableau) est aussi accepté.
            if let s = try? c.decodeIfPresent(String.self, forKey: .slot) {
                decodedSlots = [s]
            } else if let a = try? c.decodeIfPresent([String].self, forKey: .slot) {
                decodedSlots = a
            }
            if let a = try? c.decodeIfPresent([String].self, forKey: .slots) {
                for s in a where !decodedSlots.contains(s) {
                    decodedSlots.append(s)
                }
            }
            slots = decodedSlots
            materialSlots = try c.decodeIfPresent([String].self, forKey: .materialSlots) ?? []
            fixedMaterials = (try? c.decodeIfPresent([String].self, forKey: .fixedMaterials)) ?? []
            fabricSlots = try c.decodeIfPresent([String].self, forKey: .fabricSlots) ?? []
            blendShapes = try c.decodeIfPresent([String].self, forKey: .blendShapes) ?? []
            conflicts = try c.decodeIfPresent([String].self, forKey: .conflicts) ?? []
            requires = try c.decodeIfPresent([String].self, forKey: .requires) ?? []
            hides = try c.decodeIfPresent([String].self, forKey: .hides) ?? []
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(id, forKey: .id)
            try c.encode(file, forKey: .file)
            try c.encode(category, forKey: .category)
            try c.encode(slot, forKey: .slot)
            try c.encode(slots, forKey: .slots)
            try c.encode(materialSlots, forKey: .materialSlots)
            try c.encode(fixedMaterials, forKey: .fixedMaterials)
            try c.encode(fabricSlots, forKey: .fabricSlots)
            try c.encode(blendShapes, forKey: .blendShapes)
            try c.encode(conflicts, forKey: .conflicts)
            try c.encode(requires, forKey: .requires)
            try c.encode(hides, forKey: .hides)
        }
    }

    // MARK: - Clip (métadonnées, SPEC §7 et §9)

    public struct ClipEvent: Codable, Sendable, Equatable {
        public var time: Float
        public var name: String

        public init(time: Float, name: String) {
            self.time = time
            self.name = name
        }

        private enum CodingKeys: String, CodingKey {
            case time, name
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            time = try c.decodeIfPresent(Float.self, forKey: .time) ?? 0
            name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(time, forKey: .time)
            try c.encode(name, forKey: .name)
        }
    }

    public struct Clip: Codable, Sendable, Equatable {
        public var name: String
        public var loop: Bool?
        /// Durée (s) ; pour une boucle, période de la boucle. `nil` ⇒ déduite du binaire.
        public var duration: Float?
        public var frameCount: Int?
        /// Vitesse de déplacement de référence (m/s, espace poney, avant = −Z). `nil` ⇒ valeur du SPEC.
        public var rootVelocity: SIMD3<Float>?
        /// Vitesse de lacet de référence (rad/s). `nil` ⇒ valeur du SPEC.
        public var rootYawRate: Float?
        /// Masque (liste de joints) pour les couches ; `nil` ⇒ corps entier (ou masque par défaut du runtime).
        public var mask: [String]?
        public var events: [ClipEvent]
        /// Phase de foulée normalisée au temps 0 du clip (0 = poser du postérieur gauche).
        public var phaseOffset: Float
        /// Cadence d'échantillonnage déclarée (le binaire fait foi).
        public var fps: Float?
        /// Longueur (m) et durée (s) d'une foulée, nombre de foulées dans le clip (facultatifs).
        public var strideLength: Float?
        public var strideDuration: Float?
        public var stridesPerClip: Float?
        /// Données du pipeline conservées telles quelles (format libre) : séquence des appuis, contacts par
        /// image, pivot des virages.
        public var footfalls: PonyJSONValue?
        public var contacts: PonyJSONValue?
        public var rootPivot: PonyJSONValue?

        public init(name: String, loop: Bool? = nil, duration: Float? = nil, frameCount: Int? = nil,
                    rootVelocity: SIMD3<Float>? = nil, rootYawRate: Float? = nil, mask: [String]? = nil,
                    events: [ClipEvent] = [], phaseOffset: Float = 0, fps: Float? = nil,
                    strideLength: Float? = nil, strideDuration: Float? = nil, stridesPerClip: Float? = nil,
                    footfalls: PonyJSONValue? = nil, contacts: PonyJSONValue? = nil, rootPivot: PonyJSONValue? = nil) {
            self.name = name
            self.loop = loop
            self.duration = duration
            self.frameCount = frameCount
            self.rootVelocity = rootVelocity
            self.rootYawRate = rootYawRate
            self.mask = mask
            self.events = events
            self.phaseOffset = phaseOffset
            self.fps = fps
            self.strideLength = strideLength
            self.strideDuration = strideDuration
            self.stridesPerClip = stridesPerClip
            self.footfalls = footfalls
            self.contacts = contacts
            self.rootPivot = rootPivot
        }

        /// Nombre de foulées du clip : `stridesPerClip`, sinon durée / `strideDuration`, sinon 1.
        public var resolvedStridesPerClip: Double {
            if let k = stridesPerClip, k > 0, k.isFinite { return Double(k) }
            if let sd = strideDuration, sd > 0, let d = duration, d > 0 {
                let k = Double(d / sd)
                if k.isFinite && k >= 0.5 { return max(1, k.rounded()) }
            }
            return 1
        }

        private enum CodingKeys: String, CodingKey {
            case name, loop, duration, frameCount, rootVelocity, rootYawRate, mask, events, phaseOffset
            case fps, strideLength, strideDuration, stridesPerClip, footfalls, contacts, rootPivot
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            name = try c.decode(String.self, forKey: .name)
            loop = try c.decodeIfPresent(Bool.self, forKey: .loop)
            duration = try c.decodeIfPresent(Float.self, forKey: .duration)
            frameCount = try c.decodeIfPresent(Int.self, forKey: .frameCount)
            rootVelocity = try? c.decodeIfPresent(SIMD3<Float>.self, forKey: .rootVelocity)
            rootYawRate = try? c.decodeIfPresent(Float.self, forKey: .rootYawRate)
            mask = try? c.decodeIfPresent([String].self, forKey: .mask)
            events = (try? c.decodeIfPresent([ClipEvent].self, forKey: .events)) ?? []
            phaseOffset = (try? c.decodeIfPresent(Float.self, forKey: .phaseOffset)) ?? 0
            fps = try? c.decodeIfPresent(Float.self, forKey: .fps)
            strideLength = try? c.decodeIfPresent(Float.self, forKey: .strideLength)
            strideDuration = try? c.decodeIfPresent(Float.self, forKey: .strideDuration)
            stridesPerClip = try? c.decodeIfPresent(Float.self, forKey: .stridesPerClip)
            footfalls = try? c.decodeIfPresent(PonyJSONValue.self, forKey: .footfalls)
            contacts = try? c.decodeIfPresent(PonyJSONValue.self, forKey: .contacts)
            rootPivot = try? c.decodeIfPresent(PonyJSONValue.self, forKey: .rootPivot)
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(name, forKey: .name)
            try c.encodeIfPresent(loop, forKey: .loop)
            try c.encodeIfPresent(duration, forKey: .duration)
            try c.encodeIfPresent(frameCount, forKey: .frameCount)
            try c.encodeIfPresent(rootVelocity, forKey: .rootVelocity)
            try c.encodeIfPresent(rootYawRate, forKey: .rootYawRate)
            try c.encode(mask, forKey: .mask)
            try c.encode(events, forKey: .events)
            try c.encode(phaseOffset, forKey: .phaseOffset)
            try c.encodeIfPresent(fps, forKey: .fps)
            try c.encodeIfPresent(strideLength, forKey: .strideLength)
            try c.encodeIfPresent(strideDuration, forKey: .strideDuration)
            try c.encodeIfPresent(stridesPerClip, forKey: .stridesPerClip)
            try c.encodeIfPresent(footfalls, forKey: .footfalls)
            try c.encodeIfPresent(contacts, forKey: .contacts)
            try c.encodeIfPresent(rootPivot, forKey: .rootPivot)
        }
    }

    // MARK: - Procedural (noms des chaînes procédurales, SPEC §8)

    public struct LookJoint: Codable, Sendable, Equatable {
        public var joint: String
        public var weight: Float

        public init(joint: String, weight: Float) {
            self.joint = joint
            self.weight = weight
        }

        private enum CodingKeys: String, CodingKey {
            case joint, weight
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            joint = try c.decode(String.self, forKey: .joint)
            weight = try c.decodeIfPresent(Float.self, forKey: .weight) ?? 0
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(joint, forKey: .joint)
            try c.encode(weight, forKey: .weight)
        }
    }

    public struct Procedural: Codable, Sendable, Equatable {
        public var lookChain: [LookJoint]
        /// Forme libre. Formes reconnues : `{"left": {"base": "ear_l", "tip": "ear_tip_l"}, "right": {…}}`
        /// (exporteur) ou clés plates `left`/`l`, `leftTip`/`tip_l`, etc.
        public var ears: PonyJSONValue?
        public var tail: [String]
        public var mane: [String]
        public var forelock: [String]
        /// Forme libre : clés reconnues `upper_l`, `lower_l`, `upper_r`, `lower_r` (+ variantes camelCase),
        /// angles facultatifs `closeUpper`, `closeLower` (radians).
        public var eyelids: PonyJSONValue?
        public var eyes: [String]
        public var jaw: String?
        /// `{"upper": "lip_upper", "lower": "lip_lower"}` (format libre).
        public var lips: PonyJSONValue?
        /// `{"belly": "belly", "stirrups": ["stirrup_l", "stirrup_r"]}` (format libre).
        public var secondary: PonyJSONValue?
        public var belly: String?
        public var stirrups: [String]

        public init(lookChain: [LookJoint] = [], ears: PonyJSONValue? = nil, tail: [String] = [],
                    mane: [String] = [], forelock: [String] = [], eyelids: PonyJSONValue? = nil,
                    eyes: [String] = [], jaw: String? = nil, lips: PonyJSONValue? = nil,
                    secondary: PonyJSONValue? = nil, belly: String? = nil, stirrups: [String] = []) {
            self.lookChain = lookChain
            self.ears = ears
            self.tail = tail
            self.mane = mane
            self.forelock = forelock
            self.eyelids = eyelids
            self.eyes = eyes
            self.jaw = jaw
            self.lips = lips
            self.secondary = secondary
            self.belly = belly
            self.stirrups = stirrups
        }

        private enum CodingKeys: String, CodingKey {
            case lookChain, ears, tail, mane, forelock, eyelids, eyes, jaw, lips, secondary, belly, stirrups
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            lookChain = (try? c.decodeIfPresent([LookJoint].self, forKey: .lookChain)) ?? []
            ears = try? c.decodeIfPresent(PonyJSONValue.self, forKey: .ears)
            tail = (try? c.decodeIfPresent([String].self, forKey: .tail)) ?? []
            mane = (try? c.decodeIfPresent([String].self, forKey: .mane)) ?? []
            forelock = (try? c.decodeIfPresent([String].self, forKey: .forelock)) ?? []
            eyelids = try? c.decodeIfPresent(PonyJSONValue.self, forKey: .eyelids)
            eyes = (try? c.decodeIfPresent([String].self, forKey: .eyes)) ?? []
            jaw = try? c.decodeIfPresent(String.self, forKey: .jaw)
            lips = try? c.decodeIfPresent(PonyJSONValue.self, forKey: .lips)
            secondary = try? c.decodeIfPresent(PonyJSONValue.self, forKey: .secondary)
            var b = try? c.decodeIfPresent(String.self, forKey: .belly)
            var st = (try? c.decodeIfPresent([String].self, forKey: .stirrups)) ?? []
            // Forme de l'exporteur : `secondary.belly`, `secondary.stirrups`.
            if b == nil { b = secondary?["belly"]?.stringValue }
            if st.isEmpty, let arr = secondary?["stirrups"]?.arrayValue {
                st = arr.compactMap { $0.stringValue }
            }
            belly = b
            stirrups = st
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(lookChain, forKey: .lookChain)
            try c.encodeIfPresent(ears, forKey: .ears)
            try c.encode(tail, forKey: .tail)
            try c.encode(mane, forKey: .mane)
            try c.encode(forelock, forKey: .forelock)
            try c.encodeIfPresent(eyelids, forKey: .eyelids)
            try c.encode(eyes, forKey: .eyes)
            try c.encodeIfPresent(jaw, forKey: .jaw)
            try c.encodeIfPresent(lips, forKey: .lips)
            try c.encodeIfPresent(secondary, forKey: .secondary)
            try c.encodeIfPresent(belly, forKey: .belly)
            try c.encode(stirrups, forKey: .stirrups)
        }
    }

    // MARK: - Morphology (curseurs de proportion, SPEC §5 et §9)

    public struct MorphSlider: Codable, Sendable, Equatable {
        /// Identifiant du curseur (`legLength`, `neckLength`, `bodyLength`, …).
        public var id: String
        /// Blend shape appliquée pour les valeurs positives (`null` si la forme n'existe pas sur le corps).
        public var plus: String?
        /// Blend shape appliquée pour les valeurs négatives.
        public var minus: String?
        /// Décalages de translation **locale** (espace du parent) à poids 1, valeurs positives.
        public var jointOffsetsPlus: [String: SIMD3<Float>]
        public var jointOffsetsMinus: [String: SIMD3<Float>]
        /// Facteurs d'échelle à poids 1 (ex. `[1.1, 1.1, 1.1]`), interpolés depuis 1.
        public var jointScalesPlus: [String: SIMD3<Float>]
        public var jointScalesMinus: [String: SIMD3<Float>]

        public init(id: String, plus: String? = nil, minus: String? = nil,
                    jointOffsetsPlus: [String: SIMD3<Float>] = [:], jointOffsetsMinus: [String: SIMD3<Float>] = [:],
                    jointScalesPlus: [String: SIMD3<Float>] = [:], jointScalesMinus: [String: SIMD3<Float>] = [:]) {
            self.id = id
            self.plus = plus
            self.minus = minus
            self.jointOffsetsPlus = jointOffsetsPlus
            self.jointOffsetsMinus = jointOffsetsMinus
            self.jointScalesPlus = jointScalesPlus
            self.jointScalesMinus = jointScalesMinus
        }

        private enum CodingKeys: String, CodingKey {
            case id, plus, minus, jointOffsetsPlus, jointOffsetsMinus, jointScalesPlus, jointScalesMinus
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id)
            plus = try? c.decodeIfPresent(String.self, forKey: .plus)
            minus = try? c.decodeIfPresent(String.self, forKey: .minus)
            jointOffsetsPlus = (try? c.decodeIfPresent([String: SIMD3<Float>].self, forKey: .jointOffsetsPlus)) ?? [:]
            jointOffsetsMinus = (try? c.decodeIfPresent([String: SIMD3<Float>].self, forKey: .jointOffsetsMinus)) ?? [:]
            jointScalesPlus = (try? c.decodeIfPresent([String: SIMD3<Float>].self, forKey: .jointScalesPlus)) ?? [:]
            jointScalesMinus = (try? c.decodeIfPresent([String: SIMD3<Float>].self, forKey: .jointScalesMinus)) ?? [:]
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(id, forKey: .id)
            try c.encodeIfPresent(plus, forKey: .plus)
            try c.encodeIfPresent(minus, forKey: .minus)
            try c.encode(jointOffsetsPlus, forKey: .jointOffsetsPlus)
            try c.encode(jointOffsetsMinus, forKey: .jointOffsetsMinus)
            try c.encode(jointScalesPlus, forKey: .jointScalesPlus)
            try c.encode(jointScalesMinus, forKey: .jointScalesMinus)
        }
    }

    public struct Morphology: Codable, Sendable, Equatable {
        public var sliders: [MorphSlider]

        public init(sliders: [MorphSlider] = []) {
            self.sliders = sliders
        }

        private enum CodingKeys: String, CodingKey {
            case sliders
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            sliders = (try? c.decodeIfPresent([MorphSlider].self, forKey: .sliders)) ?? []
        }

        public func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(sliders, forKey: .sliders)
        }
    }

    // MARK: - Accès pratiques

    /// Indice d'un joint par nom court.
    public func jointIndex(named name: String) -> Int? {
        return joints.firstIndex(where: { $0.name == name })
    }

    /// Métadonnées d'un clip par nom.
    public func clip(named name: String) -> Clip? {
        return clips.first(where: { $0.name == name })
    }

    /// Pièce par identifiant.
    public func part(withID id: String) -> Part? {
        return parts.first(where: { $0.id == id })
    }

    /// Tous les noms de blend shapes déclarés (tous maillages), triés, sans doublon.
    public var allBlendShapeNames: [String] {
        var set = Set<String>()
        for key in blendShapes.keys.sorted() {
            for n in blendShapes[key] ?? [] {
                set.insert(n)
            }
        }
        return set.sorted()
    }

    /// Vérifications de cohérence (non bloquantes) : ordre des parents, unicité des noms, repères de liaison.
    public func validationIssues(tolerance: Float = 1e-3) -> [String] {
        var issues: [String] = []
        var seen = Set<String>()
        for (i, j) in joints.enumerated() {
            if seen.contains(j.name) { issues.append("Nom de joint dupliqué : \(j.name)") }
            seen.insert(j.name)
            if j.parent >= i { issues.append("Parent après l'enfant : \(j.name) (parent \(j.parent))") }
            if j.parent < -1 || j.parent >= joints.count { issues.append("Parent invalide : \(j.name)") }
        }
        if joints.count != PonyRigDefaults.jointNames.count {
            issues.append("Nombre de joints \(joints.count) ≠ \(PonyRigDefaults.jointNames.count) (SPEC §3)")
        }
        let skeleton = PonySkeleton(manifest: self)
        let model = skeleton.modelTransforms(local: skeleton.restLocal)
        for (i, j) in joints.enumerated() where j.bindModel.count == 16 {
            let bind = Transform(columnMajor: j.bindModel)
            if !bind.isApproximatelyEqual(to: model[i], tolerance: tolerance) {
                issues.append("bindModel ≠ FK(rest) pour \(j.name)")
            }
        }
        return issues
    }
}
