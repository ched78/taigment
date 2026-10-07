import CoreGraphics
import Foundation
import PonyCore
import RealityKit

// Application d'une configuration : morphologie et taille (runtime + échelle), pièces visibles (crins à échanger,
// accessoires), teintes des slots, motifs de tissu, et robe composée hors du MainActor.

extension PonyController {

    // MARK: Application

    /// Applique une configuration complète.
    ///
    /// - morphologie et taille : `runtime.configuration` (poids de formes + décalages de joints) et échelle de
    ///   `visualRoot` = `withersHeight / 1,30` ;
    /// - crins (`hair`) et accessoires : pièces visibles = `AccessoryRules.visiblePartIDs(for:hair:)` (pièces
    ///   masquées exclues), chargées à la demande et mises en cache ; problèmes = `validate(_:hair:)` ;
    /// - teintes : `slot_primary/secondary/accent/metal` des pièces, `M_Lashes` ; motifs sur les `fabricSlots` ;
    /// - robe : `CoatCompositor` hors du MainActor (1024² si `interactive`, 2048² sinon), puis
    ///   `TextureResource(image:withName:options:)` sur `M_Coat` ; crins (`slot_primary` des pièces de crins :
    ///   albedo des mèches + `opacityThreshold` + `faceCulling = .none`) ; iris sur `M_Eye`.
    ///
    /// La configuration n'est **pas** corrigée ici : passer par `PonyConfiguration.add(_:rules:)` /
    /// `setHair(_:rules:)` pour résoudre conflits et prérequis. Un appel plus récent interrompt le précédent à
    /// ses points d'attente. Avant `load()`, la configuration est seulement mémorisée.
    public func apply(_ newConfiguration: PonyConfiguration, interactive: Bool = false) async {
        applyGeneration &+= 1
        let generation = applyGeneration
        let previous = configuration
        configuration = newConfiguration
        guard isReady, let rt = runtime, let rules = rules else { return }

        if rt.configuration != newConfiguration {
            rt.configuration = newConfiguration
        }
        if previous.entityScale != newConfiguration.entityScale || visualRoot.scale.x != newConfiguration.entityScale {
            applyScale()
        }
        let issues = rules.validate(newConfiguration.accessories, hair: newConfiguration.hair)
        if issues != accessoryIssues { accessoryIssues = issues }

        await syncParts(newConfiguration, rules: rules, generation: generation)
        guard generation == applyGeneration else { return }
        await applyPartMaterials(newConfiguration, rules: rules, generation: generation)
        guard generation == applyGeneration else { return }
        applyBodyMaterials(newConfiguration)

        let resolution = interactive ? coatPreviewResolution : coatFinalResolution
        await requestCoat(PonyCoatRequest(coat: newConfiguration.coat, resolution: resolution))
    }

    /// Variante sans attente pour l'interface : anti-rebond de 80 ms en mode interactif, la dernière demande
    /// gagne. Au relâcher d'un curseur, appeler avec `interactive: false` (texture définitive 2048²).
    public func scheduleApply(_ newConfiguration: PonyConfiguration, interactive: Bool) {
        scheduledApply = (newConfiguration, interactive)
        scheduleTask?.cancel()
        let delay: UInt64 = interactive ? 80_000_000 : 0
        scheduleTask = Task { [weak self] in
            if delay > 0 {
                try? await Task.sleep(nanoseconds: delay)
            }
            guard !Task.isCancelled, let self = self, let pending = self.scheduledApply else { return }
            self.scheduledApply = nil
            await self.apply(pending.configuration, interactive: pending.interactive)
        }
    }

    func applyScale() {
        visualRoot.scale = SIMD3<Float>(repeating: configuration.entityScale)
        if movementMode == .characterController, var cc = root.components[CharacterControllerComponent.self] {
            let s = configuration.entityScale
            cc.radius = characterRadius * s
            cc.height = characterCapsuleHeight
            root.components.set(cc)
            visualRoot.position = SIMD3<Float>(0, -characterCenterHeight, 0)
        }
    }

    // MARK: Pièces

    func syncParts(_ config: PonyConfiguration, rules: AccessoryRules, generation: Int) async {
        let wanted = rules.visiblePartIDs(for: config.accessories, hair: config.hair)
        guard let m = manifest else { return }
        for id in wanted where parts[id] == nil && !failedParts.contains(id) {
            guard let part = rules.part(id) else { continue }
            do {
                let entity = try await assets.instantiatePart(id, file: part.file)
                if parts[id] != nil { continue }   // installée entre-temps par un appel concurrent
                installPart(entity, part: part, manifest: m)
            } catch {
                failedParts.insert(id)
                appendWarning("pièce « \(id) » indisponible : "
                    + ((error as? LocalizedError)?.errorDescription ?? "\(error)"))
            }
        }
        guard generation == applyGeneration else { return }
        for (id, inst) in parts {
            let on = wanted.contains(id)
            if inst.entity.isEnabled != on { inst.entity.isEnabled = on }
        }
        visiblePartIDs = wanted.filter { parts[$0] != nil }
    }

    func installPart(_ entity: Entity, part: PonyRigManifest.Part, manifest m: PonyRigManifest) {
        entity.stopAllAnimations(recursive: true)
        entity.isEnabled = false
        visualRoot.addChild(entity)
        let bindings = makeBindings(for: entity, label: "pièce \(part.id)", manifest: m)
        let materials = PonyMaterialSet(root: entity, label: "pièce \(part.id)")
        prepareModels(in: entity)
        parts[part.id] = PonyPartInstance(part: part, entity: entity, bindings: bindings, materials: materials)
        if !bindings.contains(where: { $0.hasPose }) {
            appendWarning("pièce « \(part.id) » : aucun squelette importé, elle ne suivra pas la pose")
        }
        // Diagnostic des noms de matériaux (`Material.name` importé : nom court ou chemin USD [I]) : sans
        // correspondance, la pièce garde ses couleurs d'export (aucune teinte ni texture runtime).
        let found = materials.materialNames
        let expected = rules?.isHairPart(part) == true ? [PonyMaterialNames.primary, "M_Hair"]
                                                       : (part.materialSlots.isEmpty ? PonyMaterialNames.slots
                                                                                     : part.materialSlots)
        if !expected.contains(where: { found.contains($0) }) {
            appendWarning("pièce « \(part.id) » : aucun matériau personnalisable reconnu (attendus : "
                + "\(expected.joined(separator: ", ")) ; importés : "
                + "\(found.isEmpty ? "aucun nom" : found.joined(separator: ", "))) — teintes non appliquées")
        }
        PonyLog.info("pièce « \(part.id) » chargée : matériaux \(materials.materialNames.joined(separator: ", "))")
    }

    /// Slots de matériaux personnalisables d'une pièce : ceux du manifeste, complétés par les `slot_*` trouvés
    /// dans l'USDZ.
    func materialSlots(of inst: PonyPartInstance) -> [String] {
        var slots = inst.part.materialSlots
        for n in inst.materials.materialNames where n.hasPrefix("slot_") && !slots.contains(n) {
            slots.append(n)
        }
        return slots
    }

    func applyPartMaterials(_ config: PonyConfiguration, rules: AccessoryRules, generation: Int) async {
        for id in visiblePartIDs {
            guard let inst = parts[id] else { continue }
            if rules.isHairPart(inst.part) {
                applyHairMaterial(inst, config: config)
                continue
            }
            let selection = config.accessories.first(where: { $0.partID == id })
            inst.materials.removeAllOverrides()
            for slot in materialSlots(of: inst) {
                let color = selection?.slotColors[slot] ?? PonyDefaultColors.color(for: inst.part, slot: slot)
                var ov = PonyMaterialOverride(tint: color)
                if inst.part.fabricSlots.contains(slot), let pattern = selection?.pattern, pattern != .plain {
                    let motif = PonyDefaultColors.motifColor(selection: selection, fabricSlot: slot, base: color)
                    if let tex = await patternTexture(pattern, base: color, motif: motif) {
                        guard generation == applyGeneration else { return }
                        ov = PonyMaterialOverride(tint: PonyColor.white, baseColorTexture: tex)
                    }
                }
                inst.materials.setOverride(slot, ov)
            }
            inst.materials.commit()
        }
    }

    /// Crins : matériau unique exporté sous `slot_primary` (alias `M_Hair` accepté [I]) ; albedo composé depuis
    /// `hair_strands.png`, découpe alpha, double face (SPEC §4, §9).
    func applyHairMaterial(_ inst: PonyPartInstance, config: PonyConfiguration) {
        let ov: PonyMaterialOverride
        if let tex = hairTexture {
            ov = PonyMaterialOverride(tint: PonyColor.white, baseColorTexture: tex, opacityThreshold: hairOpacityThreshold,
                                      doubleSided: true)
        } else {
            // Repli sans texture de mèches : teinte de la couleur des crins sur l'albedo d'aperçu de l'USDZ.
            ov = PonyMaterialOverride(tint: config.coat.maneColor, opacityThreshold: hairOpacityThreshold,
                                      doubleSided: true)
        }
        inst.materials.removeAllOverrides()
        inst.materials.setOverride(PonyMaterialNames.primary, ov)
        if inst.materials.contains("M_Hair") {
            inst.materials.setOverride("M_Hair", ov)
        }
        inst.materials.commit()
    }

    func refreshHairMaterials() {
        guard let rules = rules else { return }
        for id in visiblePartIDs {
            guard let inst = parts[id], rules.isHairPart(inst.part) else { continue }
            applyHairMaterial(inst, config: configuration)
        }
    }

    /// Texture de motif (cache par motif + couleurs ; 32 entrées au plus).
    func patternTexture(_ pattern: FabricPattern, base: PonyColor, motif: PonyColor) async -> TextureResource? {
        let key = "\(pattern.rawValue)-\(base.hexString)-\(motif.hexString)"
        if let t = patternTextures[key] { return t }
        let image = await Task.detached(priority: .userInitiated) { () -> PonyCGImageBox in
            let rgba = PonyFabricPatterns.make(pattern, base: base, motif: motif)
            return PonyCGImageBox(image: PonyImageIO.makeCGImage(rgba, opaque: true))
        }.value
        guard let cg = image.image else { return nil }
        do {
            let tex = try await TextureResource(image: cg, withName: "pony_pattern_\(key)",
                                                options: TextureResource.CreateOptions(semantic: .color))
            if patternTextures.count >= 32 { patternTextures.removeAll() }
            patternTextures[key] = tex
            return tex
        } catch {
            appendWarning("motif \(pattern.rawValue) : création de texture impossible (\(error.localizedDescription))")
            return nil
        }
    }

    // MARK: Corps

    func applyBodyMaterials(_ config: PonyConfiguration) {
        if let ph = placeholder {
            ph.recolor(config.coat)
            return
        }
        guard let mats = bodyMaterials else { return }
        // Cils et vibrisses : cartes alpha, double face ; teinte dérivée des crins assombris [A].
        mats.setOverride(PonyMaterialNames.lashes,
                         PonyMaterialOverride(tint: PonyColor.mix(config.coat.maneColor, PonyColor.black, 0.45),
                                              doubleSided: true))
        // M_Mouth (gencives, dents, langue) : laissé tel qu'exporté (pas de teinte pertinente).
        mats.commit()
    }

    // MARK: Robe

    /// Demande la robe ; si une composition est en cours, la demande la plus récente sera traitée ensuite
    /// (les passes de composition sont pures et ne peuvent pas être interrompues).
    func requestCoat(_ request: PonyCoatRequest) async {
        coatPending = request
        if coatBusy { return }
        coatBusy = true
        isComposingCoat = true
        while let next = coatPending {
            coatPending = nil
            // Robe inchangée et texture déjà au moins aussi fine : rien à refaire (ex. curseur de morphologie en
            // mode interactif après une robe définitive 2048² — sinon deux compositions inutiles).
            if let done = appliedCoat, done.coat == next.coat, done.resolution >= next.resolution { continue }
            await composeAndApplyCoat(next)
        }
        coatBusy = false
        isComposingCoat = false
    }

    func composeAndApplyCoat(_ request: PonyCoatRequest) async {
        if placeholder != nil {
            placeholder?.recolor(request.coat)
            appliedCoat = request
            return
        }
        let maps = coatMaps
        let needHairIris = request.coat != hairIrisCoat
        let started = Date()
        let images = await Task.detached(priority: .userInitiated) { () -> PonyComposedCoatImages in
            return PonyController.composeImages(request, maps: maps, hairAndIris: needHairIris)
        }.value
        let composeTime = Date().timeIntervalSince(started)

        if let cg = images.body {
            do {
                let tex = try await TextureResource(image: cg, withName: "pony_coat_\(request.resolution)",
                                                    options: TextureResource.CreateOptions(semantic: .color))
                bodyMaterials?.setOverride(PonyMaterialNames.coat,
                                           PonyMaterialOverride(tint: PonyColor.white, baseColorTexture: tex))
            } catch {
                appendWarning("robe : création de texture impossible (\(error.localizedDescription))")
            }
        } else if maps == nil {
            // Repli sans cartes : teinte unie de la robe, sauf pour la robe par défaut (albedo de l'USDZ).
            if request.coat == CoatConfiguration.default {
                bodyMaterials?.setOverride(PonyMaterialNames.coat, nil)
            } else {
                bodyMaterials?.setOverride(PonyMaterialNames.coat,
                                           PonyMaterialOverride(tint: request.coat.phenotype.bodyColor,
                                                                removeBaseColorTexture: true))
            }
        }
        if needHairIris {
            hairTexture = nil
            if let cg = images.hair {
                hairTexture = try? await TextureResource(image: cg, withName: "pony_hair",
                                                         options: TextureResource.CreateOptions(semantic: .color))
            }
            if let cg = images.iris {
                irisTexture = try? await TextureResource(image: cg, withName: "pony_iris",
                                                         options: TextureResource.CreateOptions(semantic: .color))
            }
            hairIrisCoat = request.coat
        }
        if let iris = irisTexture {
            // Contrat UV (Docs/COAT.md §7, repris par Pipeline/pony/head_parts.py) : chaque globe occupe le carré
            // UV [0,1]², iris centré ; rendu à vérifier sur appareil [I].
            bodyMaterials?.setOverride(PonyMaterialNames.eye,
                                       PonyMaterialOverride(tint: PonyColor.white, baseColorTexture: iris))
        }
        bodyMaterials?.commit()
        if needHairIris {
            refreshHairMaterials()
        }
        appliedCoat = request
        PonyLog.info("robe composée en \(Int(composeTime * 1000)) ms (\(request.resolution)², crins/iris : "
            + "\(needHairIris ? "recalculés" : "inchangés"))")
    }

    /// Composition pure (hors MainActor) : corps (si cartes), crins (si mèches), iris (toujours).
    nonisolated static func composeImages(_ request: PonyCoatRequest, maps: CoatMaps?,
                                          hairAndIris: Bool) -> PonyComposedCoatImages {
        var out = PonyComposedCoatImages()
        if let m = maps {
            let body = CoatCompositor.composeBody(request.coat, maps: m, resolution: request.resolution)
            out.body = PonyImageIO.makeCGImage(body, opaque: true)
        }
        if hairAndIris {
            if let m = maps, let hair = CoatCompositor.composeHair(request.coat, maps: m) {
                // Alpha non prémultiplié (`.last`) conservé pour la découpe `opacityThreshold` ; acceptation de ce
                // format par `TextureResource(image:…)` non documentée [I : checklist INTEGRATION.md].
                out.hair = PonyImageIO.makeCGImage(hair, opaque: false)
            }
            let iris = CoatCompositor.composeIris(request.coat, detail: maps?.irisDetail)
            out.iris = PonyImageIO.makeCGImage(iris, opaque: true)
        }
        return out
    }
}

/// Images composées transmises du fil de calcul au MainActor. `CGImage` est immuable : transfert sûr
/// (`@unchecked` faute de garantie `Sendable` documentée pour `CGImage`).
struct PonyComposedCoatImages: @unchecked Sendable {
    var body: CGImage?
    var hair: CGImage?
    var iris: CGImage?
}

struct PonyCGImageBox: @unchecked Sendable {
    var image: CGImage?
}

/// Couleurs par défaut des slots d'accessoires [A] (cuir havane, accents crème, métal acier, tissus marine).
public enum PonyDefaultColors {
    public static let leather = PonyColor(hex: "#5A3A22")
    public static let darkLeather = PonyColor(hex: "#2E1F16")
    public static let cream = PonyColor(hex: "#D9CBA8")
    public static let steel = PonyColor(hex: "#B8BCC2")
    public static let navy = PonyColor(hex: "#1F3566")
    public static let burgundy = PonyColor(hex: "#6E1E2C")
    public static let white = PonyColor(hex: "#EEEDE8")

    /// Couleur par défaut d'un slot selon la catégorie de la pièce.
    public static func color(for part: PonyRigManifest.Part, slot: String) -> PonyColor {
        if slot == PonyMaterialNames.metal { return steel }
        let category = PonyPartLabels.normalizedCategory(part.category)
        switch (category, slot) {
        case ("tack", PonyMaterialNames.primary): return part.fabricSlots.contains(slot) ? navy : leather
        case ("tack", PonyMaterialNames.secondary): return part.fabricSlots.isEmpty ? darkLeather : white
        case ("tack", _): return cream
        case ("protection", PonyMaterialNames.primary): return navy
        case ("protection", _): return darkLeather
        case ("decorative", PonyMaterialNames.primary): return burgundy
        case ("decorative", _): return cream
        case ("rug", PonyMaterialNames.primary): return navy
        case ("rug", _): return burgundy
        default: return slot == PonyMaterialNames.primary ? leather : cream
        }
    }

    /// Couleur du motif d'un slot tissu : `slot_accent`, sinon `slot_secondary` (si différents du slot tissu),
    /// sinon couleur contrastée.
    public static func motifColor(selection: AccessorySelection?, fabricSlot: String, base: PonyColor) -> PonyColor {
        for candidate in [PonyMaterialNames.accent, PonyMaterialNames.secondary] where candidate != fabricSlot {
            if let c = selection?.slotColors[candidate] { return c }
        }
        return PonyFabricPatterns.contrastingColor(for: base)
    }
}
