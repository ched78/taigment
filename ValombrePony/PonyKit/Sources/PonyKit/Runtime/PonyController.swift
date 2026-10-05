import Foundation
import Observation
import PonyCore
import RealityKit

// Dans ce fichier, `Transform` est ambigu (RealityKit / PonyCore) : toujours qualifier le module.

/// Un poney jouable : runtime d'animation `PonyCore`, entités RealityKit (corps + pièces), textures et teintes,
/// déplacement, regard, surcharges de joints, évènements.
///
/// Hiérarchie créée :
/// ```
/// root (PonyComponent ; position + lacet ; CharacterControllerComponent en mode .characterController)
///   └─ visualRoot (échelle = withersHeight / 1,30 ; décalage vertical en mode contrôleur de personnage)
///        ├─ corps (clone de Pony.usdz)        ← espace modèle du runtime (unités du rig)
///        └─ pièces (clones de Parts/<id>.usdz, transform identité, activées/désactivées)
/// ```
/// Utilisation minimale :
/// ```swift
/// let pony = PonyController(configuration: .default)
/// content.add(pony.root)          // dans RealityView { content in … }
/// await pony.load()
/// pony.input.move = [0, 1]        // ou pony.inputSource = PonyInputState()
/// ```
/// Aucun clip RealityKit n'est joué : `PonySystem` appelle `tick(deltaTime:)` à chaque frame, qui écrit la pose
/// dans `SkeletalPosesComponent` du corps ET de chaque pièce visible (SPEC §0, §6).
@MainActor
@Observable
public final class PonyController {

    /// Mode de déplacement de l'entité.
    public enum MovementMode: String, CaseIterable, Sendable {
        /// Déplacement direct de la transform ; sol plat à `groundHeight` ; saut balistique.
        case kinematic
        /// `CharacterControllerComponent` + `moveCharacter(by:deltaTime:relativeTo:collisionHandler:)`
        /// (collisions avec les entités portant un `CollisionComponent`).
        case characterController
    }

    public enum LoadState: Equatable, Sendable {
        case idle
        case loading
        case ready
        case failed(String)
    }

    // MARK: Entités

    /// Racine déplacée (position, lacet). À ajouter au contenu de la `RealityView`.
    public let root: Entity
    /// Racine visuelle (échelle de taille) : son repère local est l'« espace modèle » du runtime.
    public let visualRoot: Entity
    /// Corps importé (ou substitut primitif si `Pony.usdz` est absent).
    @ObservationIgnored public private(set) var body: Entity?

    // MARK: État observable (mis à jour seulement quand la valeur change)

    public private(set) var loadState: LoadState = .idle
    public internal(set) var configuration: PonyConfiguration
    public private(set) var gait: PonyGait = .idle
    public private(set) var currentAction: PonyAction?
    public private(set) var isAirborne = false
    /// Vitesse au sol affichable (m/s, arrondie au dixième).
    public private(set) var displaySpeed: Float = 0
    /// Vrai pendant la composition d'une texture de robe.
    public internal(set) var isComposingCoat = false
    /// Problèmes de la sélection d'accessoires courante (`AccessoryRules.validate(_:hair:)`).
    public internal(set) var accessoryIssues: [AccessoryIssue] = []
    /// Avertissements non bloquants (ressource absente, repli utilisé…).
    public private(set) var warnings: [String] = []
    /// Erreurs de chargement rencontrées (le poney peut rester jouable grâce aux replis).
    public private(set) var loadErrors: [String] = []
    /// Vrai si le corps est un substitut primitif (Pony.usdz absent ou illisible).
    public private(set) var usesPlaceholder = false

    // MARK: Réglages (non observés)

    /// Mode de déplacement ; modifiable à chaud.
    @ObservationIgnored public var movementMode: MovementMode {
        didSet { if oldValue != movementMode { configureMovement() } }
    }
    /// Hauteur du sol en mode cinématique (m, monde).
    @ObservationIgnored public var groundHeight: Float = 0
    /// Suspend la mise à jour (pose figée, aucun déplacement).
    @ObservationIgnored public var isPaused = false
    /// Autorise le substitut primitif si `Pony.usdz` manque (sinon `loadState = .failed`).
    @ObservationIgnored public var allowsPlaceholder = true
    /// Entrées de la frame. `jumpPressed` et `action` sont consommés (remis à zéro) après chaque frame.
    @ObservationIgnored public var input = PonyInput()
    /// Source d'entrées continue (clavier + joystick), lue à chaque frame si définie (`move`, `sprint`).
    @ObservationIgnored public weak var inputSource: PonyInputState?
    /// Cible du regard en coordonnées **monde** (convertie en espace modèle à chaque frame) ; `nil` = libre.
    @ObservationIgnored public var lookTarget: SIMD3<Float>?
    /// Rappel pour chaque évènement d'animation (`foot_down_*`, `takeoff`, `landing`, `tail_swish`…).
    @ObservationIgnored public var onEvent: ((PonyEvent) -> Void)?
    /// Derniers évènements (16 au plus), du plus ancien au plus récent.
    @ObservationIgnored public private(set) var recentEvents: [PonyEvent] = []
    /// Capsule du contrôleur de personnage pour un poney de 1,30 m (multipliée par l'échelle) [A] : une capsule
    /// verticale épouse mal un corps horizontal (realitykit.md §6.4).
    @ObservationIgnored public var characterRadius: Float = 0.42
    @ObservationIgnored public var characterHeight: Float = 1.25
    /// Vitesse de plaquage au sol hors saut (m/s) en mode contrôleur de personnage [I].
    @ObservationIgnored public var groundSnapSpeed: Float = 2.0
    /// Résolutions de la texture de robe : édition interactive / définitive (Docs/COAT.md §2).
    @ObservationIgnored public var coatPreviewResolution = CoatCompositor.previewResolution
    @ObservationIgnored public var coatFinalResolution = CoatCompositor.finalResolution
    /// Seuil de découpe alpha des crins (`Pipeline/pony/hair_texture.py`, MATERIAL_HINTS) [I].
    @ObservationIgnored public var hairOpacityThreshold: Float = 0.4
    /// Entité d'éclairage d'ambiance (IBL) ; chaque entité modèle du poney reçoit un
    /// `ImageBasedLightReceiverComponent` (non hérité selon nos hypothèses [I], realitykit.md §6.3).
    @ObservationIgnored public var imageBasedLight: Entity? {
        didSet { refreshModelComponents() }
    }

    // MARK: Accès avancés

    /// Runtime PonyCore (réglages de locomotion, de saut, procéduraux, `earMood`, `groundHeightProvider`…).
    @ObservationIgnored public private(set) var runtime: PonyRuntime?
    @ObservationIgnored public private(set) var manifest: PonyRigManifest?
    @ObservationIgnored public private(set) var rules: AccessoryRules?

    // MARK: Internes

    // `let` : jamais observés par @Observable (pas besoin de @ObservationIgnored).
    let assets: PonyAssetLibrary
    let seed: UInt64
    @ObservationIgnored var coatMaps: CoatMaps?
    @ObservationIgnored var knownShapes = Set<String>()
    @ObservationIgnored var bodyBindings: [PonySkinBinding] = []
    @ObservationIgnored var bodyMaterials: PonyMaterialSet?
    @ObservationIgnored var placeholder: PonyPlaceholder?
    @ObservationIgnored var parts: [String: PonyPartInstance] = [:]
    @ObservationIgnored var failedParts = Set<String>()
    @ObservationIgnored var visiblePartIDs: [String] = []
    @ObservationIgnored var poseBuffer: [RealityKit.Transform] = []
    @ObservationIgnored var pendingJump = false
    @ObservationIgnored var pendingAction: PonyAction?
    @ObservationIgnored var jointOverrides: [String: (rotation: Quat, weight: Float)] = [:]
    @ObservationIgnored var applyGeneration = 0
    @ObservationIgnored var scheduledApply: (configuration: PonyConfiguration, interactive: Bool)?
    @ObservationIgnored var scheduleTask: Task<Void, Never>?
    // Robe
    @ObservationIgnored var coatBusy = false
    @ObservationIgnored var coatPending: PonyCoatRequest?
    @ObservationIgnored var appliedCoat: PonyCoatRequest?
    @ObservationIgnored var hairIrisCoat: CoatConfiguration?
    @ObservationIgnored var hairTexture: TextureResource?
    @ObservationIgnored var irisTexture: TextureResource?
    @ObservationIgnored var patternTextures: [String: TextureResource] = [:]

    // MARK: Création

    /// - Parameters:
    ///   - configuration: configuration initiale (appliquée par `load()`).
    ///   - assets: bibliothèque de ressources (défaut : `PonyAssetLibrary.shared`, ressources du package).
    ///   - movementMode: `.kinematic` (défaut) ou `.characterController`.
    ///   - seed: graine du runtime (déterminisme des comportements aléatoires).
    public init(configuration: PonyConfiguration = .default, assets: PonyAssetLibrary? = nil,
                movementMode: MovementMode = .kinematic, seed: UInt64 = 1) {
        let r = Entity()
        r.name = "Pony"
        let v = Entity()
        v.name = "PonyVisual"
        r.addChild(v)
        root = r
        visualRoot = v
        self.configuration = configuration
        self.assets = assets ?? PonyAssetLibrary.shared
        self.movementMode = movementMode
        self.seed = seed
        PonyKit.registerSystems()
        root.components.set(PonyComponent(controller: self))
        visualRoot.scale = SIMD3<Float>(repeating: configuration.entityScale)
    }

    var isReady: Bool {
        return loadState == .ready
    }

    // MARK: Chargement

    /// Charge manifeste, clips, cartes de robe et corps, puis applique la configuration. Idempotent.
    ///
    /// Replis (journalisés, listés dans `warnings` / `loadErrors`) : manifeste absent → squelette synthétique
    /// (`PonyRigDefaults.syntheticManifest()`) ; clips absents → bibliothèque vide (pose de repos + procédural) ;
    /// cartes de robe absentes → teinte uniforme ; `Pony.usdz` absent → substitut primitif (si
    /// `allowsPlaceholder`).
    public func load() async {
        switch loadState {
        case .loading, .ready: return
        case .idle, .failed: break
        }
        loadState = .loading
        loadErrors.removeAll()
        PonyKit.registerSystems()

        let loadedManifest: PonyRigManifest
        do {
            loadedManifest = try await assets.manifest()
        } catch {
            recordError(error)
            appendWarning("squelette synthétique utilisé (prototype) : animations et pièces indisponibles")
            loadedManifest = PonyRigDefaults.syntheticManifest()
        }
        let clips: ClipLibrary
        do {
            clips = try await assets.clips(for: loadedManifest)
        } catch {
            recordError(error)
            clips = ClipLibrary.empty(manifest: loadedManifest)
        }
        let maps = await assets.coatMaps(for: loadedManifest)

        let rt = PonyRuntime(manifest: loadedManifest, clips: clips, configuration: configuration, seed: seed)
        rt.usesExternalLanding = true
        for (joint, ov) in jointOverrides {
            rt.setJointOverride(joint, rotation: ov.rotation, weight: ov.weight)
        }
        manifest = loadedManifest
        runtime = rt
        rules = AccessoryRules(manifest: loadedManifest)
        coatMaps = maps
        knownShapes = Set(rt.blendShapeNames)

        do {
            let b = try await assets.instantiateBody()
            installBody(b, isPlaceholder: false)
        } catch {
            recordError(error)
            guard allowsPlaceholder else {
                loadState = .failed((error as? LocalizedError)?.errorDescription ?? "\(error)")
                return
            }
            let ph = PonyPlaceholder()
            placeholder = ph
            installBody(ph.entity, isPlaceholder: true)
            appendWarning("Pony.usdz indisponible : substitut primitif affiché")
        }
        for w in assets.warnings {
            appendWarning(w)
        }
        loadState = .ready
        configureMovement()
        PonyLog.info("poney chargé : \(rt.jointNames.count) joints, \(clips.names.count) clips, "
            + "\(knownShapes.count) blend shapes, cartes de robe \(maps == nil ? "absentes" : "présentes")")
        await apply(configuration)
    }

    func installBody(_ entity: Entity, isPlaceholder: Bool) {
        entity.stopAllAnimations(recursive: true)
        entity.name = isPlaceholder ? "PonyPlaceholder" : "PonyBody"
        visualRoot.addChild(entity)
        body = entity
        usesPlaceholder = isPlaceholder
        if let m = manifest, !isPlaceholder {
            bodyBindings = makeBindings(for: entity, label: "corps", manifest: m)
            if bodyBindings.isEmpty {
                appendWarning("corps : aucun SkeletalPosesComponent ni BlendShapeWeightsComponent trouvé — pose figée")
            }
        }
        bodyMaterials = PonyMaterialSet(root: entity, label: "corps")
        prepareModels(in: entity)
        if !isPlaceholder {
            let names = bodyMaterials?.materialNames ?? []
            for expected in [PonyMaterialNames.coat, PonyMaterialNames.eye] where !names.contains(expected) {
                appendWarning("corps : matériau « \(expected) » introuvable (matériaux : \(names.joined(separator: ", ")))")
            }
            PonyLog.info("hiérarchie du corps importé :\n" + PonyEntityTree.describe(entity))
        }
    }

    /// Une liaison par entité portant une pose ou des poids (corps ou pièce).
    func makeBindings(for entity: Entity, label: String, manifest: PonyRigManifest) -> [PonySkinBinding] {
        var seen = Set<ObjectIdentifier>()
        var out: [PonySkinBinding] = []
        for e in PonyEntityTree.poseEntities(in: entity) + PonyEntityTree.blendEntities(in: entity) {
            let key = ObjectIdentifier(e)
            if seen.contains(key) { continue }
            seen.insert(key)
            let suffix = e === entity ? "" : " (« \(e.name) »)"
            out.append(PonySkinBinding(entity: e, label: label + suffix, manifest: manifest, knownShapes: knownShapes))
        }
        return out
    }

    /// Ombre de contact (non héritée par la hiérarchie, realitykit.md §6.3) et éclairage d'ambiance sur chaque
    /// entité modèle. API : `GroundingShadowComponent(castsShadow:)` (iOS 18 / macOS 15),
    /// `ImageBasedLightReceiverComponent(imageBasedLight:)` (iOS 18 / macOS 15).
    func prepareModels(in entity: Entity) {
        for m in PonyEntityTree.modelEntities(in: entity) {
            m.components.set(GroundingShadowComponent(castsShadow: true))
            if let ibl = imageBasedLight {
                m.components.set(ImageBasedLightReceiverComponent(imageBasedLight: ibl))
            }
        }
    }

    func refreshModelComponents() {
        if let b = body { prepareModels(in: b) }
        for p in parts.values {
            prepareModels(in: p.entity)
        }
    }

    // MARK: Entrées et commandes

    /// Demande un saut (front montant, consommé à la frame suivante).
    public func jump() {
        pendingJump = true
    }

    /// Demande un comportement (consommé à la frame suivante ; refus éventuels : Docs/RUNTIME.md §8).
    public func perform(_ action: PonyAction) {
        pendingAction = action
    }

    /// Se coucher, ou se relever si le poney est couché.
    public func toggleLying() {
        if currentAction == .lieDown || currentAction == .roll {
            perform(.getUp)
        } else {
            perform(.lieDown)
        }
    }

    /// Surcharge la rotation **locale** d'un joint (nom court du SPEC §3), mélangée par slerp (`weight` 0…1).
    /// `nil` ou `weight <= 0` retire la surcharge. Conservée si le runtime n'est pas encore chargé.
    public func setJointOverride(_ joint: String, rotation: simd_quatf?, weight: Float) {
        if let q = rotation, weight > 0, weight.isFinite {
            let pq = Quat(q)
            jointOverrides[joint] = (pq, weight)
            runtime?.setJointOverride(joint, rotation: pq, weight: weight)
        } else {
            jointOverrides[joint] = nil
            runtime?.setJointOverride(joint, rotation: nil, weight: 0)
        }
    }

    public func clearJointOverrides() {
        jointOverrides.removeAll()
        runtime?.clearJointOverrides()
    }

    /// Humeur imposée des oreilles (`nil` = automatique).
    public var earMood: EarMood? {
        get { return runtime?.earMood }
        set { runtime?.earMood = newValue }
    }

    /// Place le poney (pieds au sol) à une position monde, avec un lacet (rad, 0 = regarde vers −Z).
    public func teleport(to position: SIMD3<Float>, yaw: Float = 0) {
        root.orientation = simd_quatf(angle: yaw, axis: SIMD3<Float>(0, 1, 0))
        switch movementMode {
        case .kinematic:
            root.position = SIMD3<Float>(position.x, max(position.y, groundHeight), position.z)
        case .characterController:
            let center = position + SIMD3<Float>(0, characterCenterHeight, 0)
            root.position = center
            if root.scene != nil {
                root.teleportCharacter(to: center, relativeTo: nil)
            }
        }
        runtime?.resetSecondaryMotion()
    }

    // MARK: Mise à jour par frame

    /// Avance le poney d'une frame. Appelé par `PonySystem` (ne pas appeler en plus).
    func tick(deltaTime: Float) {
        guard !isPaused, isReady, let rt = runtime else { return }
        let dt = PonyMath.clamp(deltaTime.isFinite ? deltaTime : 0, 0, 0.1)
        if dt <= 0 { return }

        var frameInput = input
        if let source = inputSource {
            frameInput.move = source.move
            frameInput.sprint = source.sprint
        }
        if pendingJump { frameInput.jumpPressed = true }
        if let a = pendingAction { frameInput.action = a }
        if !(frameInput.move.x.isFinite && frameInput.move.y.isFinite) {
            frameInput.move = SIMD2<Float>(0, 0)
        }
        pendingJump = false
        pendingAction = nil
        input.jumpPressed = false
        input.action = nil

        if let target = lookTarget {
            rt.lookTarget = visualRoot.convert(position: target, from: nil)
        } else {
            rt.lookTarget = nil
        }

        let frame = rt.update(deltaTime: dt, input: frameInput)
        move(with: frame, deltaTime: dt, runtime: rt)
        writePose(frame)
        publish(frame)
    }

    func move(with frame: PonyFrame, deltaTime dt: Float, runtime rt: PonyRuntime) {
        if frame.rootYawRate != 0 && frame.rootYawRate.isFinite {
            let yaw = simd_quatf(angle: frame.rootYawRate * dt, axis: SIMD3<Float>(0, 1, 0))
            root.orientation = simd_normalize(root.orientation * yaw)
        }
        var step = root.orientation.act(frame.rootVelocity) * dt
        step.y = 0
        if !(step.x.isFinite && step.z.isFinite) { step = SIMD3<Float>(0, 0, 0) }
        let vy = frame.verticalVelocity.isFinite ? frame.verticalVelocity : 0

        switch movementMode {
        case .kinematic:
            var p = root.position + step
            if frame.isAirborne {
                p.y += vy * dt
                if p.y <= groundHeight {
                    p.y = groundHeight
                    if vy <= 0 { rt.notifyLanded() }
                }
            } else {
                p.y = groundHeight
            }
            root.position = p
        case .characterController:
            step.y = frame.isAirborne ? vy * dt : -groundSnapSpeed * dt
            let flags = root.moveCharacter(by: step, deltaTime: dt, relativeTo: nil, collisionHandler: nil)
            if frame.isAirborne && vy <= 0 && flags.contains(.bottom) {
                rt.notifyLanded()
            }
        }
    }

    func writePose(_ frame: PonyFrame) {
        let pose = frame.localPose
        if poseBuffer.count != pose.count {
            poseBuffer = [RealityKit.Transform](repeating: RealityKit.Transform.identity, count: pose.count)
        }
        for i in 0..<pose.count {
            poseBuffer[i] = RealityKit.Transform(pony: pose[i])
        }
        for b in bodyBindings {
            b.writePose(poseBuffer)
            b.writeWeights(frame.blendWeights)
        }
        for id in visiblePartIDs {
            guard let part = parts[id] else { continue }
            for b in part.bindings {
                b.writePose(poseBuffer)
                b.writeWeights(frame.blendWeights)
            }
        }
    }

    func publish(_ frame: PonyFrame) {
        if frame.gait != gait { gait = frame.gait }
        if frame.action != currentAction { currentAction = frame.action }
        if frame.isAirborne != isAirborne { isAirborne = frame.isAirborne }
        let v = frame.rootVelocity
        let speed = ((v.x * v.x + v.z * v.z).squareRoot() * 10).rounded() / 10
        if speed.isFinite && abs(speed - displaySpeed) >= 0.1 { displaySpeed = speed }
        for e in frame.events {
            recentEvents.append(e)
            onEvent?(e)
        }
        if recentEvents.count > 16 {
            recentEvents.removeFirst(recentEvents.count - 16)
        }
    }

    // MARK: Déplacement

    /// Hauteur du centre de la capsule au-dessus du sol : `height / 2 + radius` en supposant, comme PhysX,
    /// que `height` exclut les hémisphères [I : à vérifier sur appareil, checklist INTEGRATION.md].
    var characterCenterHeight: Float {
        let s = configuration.entityScale
        return (characterHeight * 0.5 + characterRadius) * s
    }

    func configureMovement() {
        switch movementMode {
        case .kinematic:
            let wasController = root.components.has(CharacterControllerComponent.self)
            root.components.remove(CharacterControllerComponent.self)
            visualRoot.position = SIMD3<Float>(0, 0, 0)
            if wasController {
                root.position.y -= characterCenterHeight
            }
            root.position.y = max(root.position.y, groundHeight)
        case .characterController:
            let s = configuration.entityScale
            let wasController = root.components.has(CharacterControllerComponent.self)
            root.components.set(CharacterControllerComponent(radius: characterRadius * s, height: characterHeight * s))
            visualRoot.position = SIMD3<Float>(0, -characterCenterHeight, 0)
            if !wasController {
                root.position.y += characterCenterHeight
                if root.scene != nil {
                    root.teleportCharacter(to: root.position(relativeTo: nil), relativeTo: nil)
                }
            }
        }
    }

    // MARK: Journal

    func appendWarning(_ message: String) {
        if !warnings.contains(message) {
            warnings.append(message)
            PonyLog.warning(message)
        }
    }

    func recordError(_ error: Error) {
        let message = (error as? LocalizedError)?.errorDescription ?? "\(error)"
        loadErrors.append(message)
        PonyLog.error(message)
    }

    /// Rapport lisible (hiérarchie importée, matériaux, liaisons de squelette, pièces) pour les tests sur appareil.
    public func diagnosticReport() -> String {
        var lines: [String] = ["[PonyKit] état : \(loadState), placeholder : \(usesPlaceholder)"]
        lines.append(PonyEntityTree.describe(root))
        for b in bodyBindings {
            lines.append(b.summary)
        }
        for id in parts.keys.sorted() {
            guard let p = parts[id] else { continue }
            let visible = visiblePartIDs.contains(id) ? "visible" : "masquée"
            lines.append("pièce \(id) (\(visible)) : matériaux \(p.materials.materialNames.joined(separator: ", "))")
            for b in p.bindings {
                lines.append("  " + b.summary)
            }
        }
        if !warnings.isEmpty {
            lines.append("avertissements : " + warnings.joined(separator: " | "))
        }
        return lines.joined(separator: "\n")
    }
}

/// Pièce chargée (crins ou accessoire) attachée au poney.
@MainActor
struct PonyPartInstance {
    let part: PonyRigManifest.Part
    let entity: Entity
    let bindings: [PonySkinBinding]
    let materials: PonyMaterialSet
}

/// Demande de composition de robe (configuration + résolution).
struct PonyCoatRequest: Equatable, Sendable {
    var coat: CoatConfiguration
    var resolution: Int
}
