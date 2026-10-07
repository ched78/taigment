import Foundation
import PonyCore
import RealityKit

/// Bibliothèque partagée des ressources du poney : manifeste, clips, cartes de pelage et modèles USDZ
/// (corps + pièces), chargés à la demande et mis en cache. Les entités en cache servent de **gabarits** :
/// chaque poney en reçoit un clone (`clone(recursive: true)`), si bien que plusieurs poneys partagent maillages
/// et textures d'origine tout en ayant leurs propres composants (pose, poids, matériaux).
///
/// Les décodages lourds (JSON, binaire des clips, PNG) se font hors du MainActor (`Task.detached`).
@MainActor
public final class PonyAssetLibrary {
    /// Bibliothèque par défaut (ressources du bundle du module).
    public static let shared = PonyAssetLibrary()

    public let locator: PonyResourceLocator?
    /// Avertissements non bloquants accumulés (ressource optionnelle absente, repli utilisé…).
    public private(set) var warnings: [String] = []

    private var manifestTask: Task<PonyLoadedManifest, Error>?
    /// Nom de la texture de mèches lu dans `hair.maps.strands` du manifeste (clé ignorée par `PonyRigManifest`).
    private var hairStrandsFileName: String?
    private var clipsTask: Task<ClipLibrary, Error>?
    private var coatMapsTask: Task<CoatMaps?, Never>?
    private var templateTasks: [String: Task<Entity, Error>] = [:]

    public init(locator: PonyResourceLocator? = PonyResourceLocator.bundled) {
        self.locator = locator
        if locator == nil {
            PonyLog.error(PonyAssetError.resourceFolderMissing.errorDescription ?? "ressources absentes")
        }
    }

    private func requireLocator() throws -> PonyResourceLocator {
        guard let l = locator else { throw PonyAssetError.resourceFolderMissing }
        return l
    }

    private func warn(_ message: String) {
        if !warnings.contains(message) {
            warnings.append(message)
            PonyLog.warning(message)
        }
    }

    // MARK: Manifeste et clips

    /// `PonyRig.json` décodé (erreur typée si absent ou invalide).
    public func manifest() async throws -> PonyRigManifest {
        if let t = manifestTask {
            return try await t.value.manifest
        }
        let loc = try requireLocator()
        let task = Task.detached(priority: .userInitiated) { () throws -> PonyLoadedManifest in
            let data = try loc.data(PonyResourceNames.manifest)
            let manifest: PonyRigManifest
            do {
                manifest = try PonyRigManifest.decode(from: data)
            } catch {
                throw PonyAssetError.invalidManifest(reason: String(describing: error))
            }
            // Clé `hair.maps.strands` (écrite par s09_export.py, ignorée par `PonyRigManifest`) : relue à part.
            let top = try? JSONDecoder().decode([String: PonyJSONValue].self, from: data)
            let strands = top?["hair"]?["maps"]?["strands"]?.stringValue
            return PonyLoadedManifest(manifest: manifest, hairStrands: strands)
        }
        manifestTask = task
        do {
            let loaded = try await task.value
            let m = loaded.manifest
            if m.joints.isEmpty {
                throw PonyAssetError.invalidManifest(reason: "aucun joint")
            }
            if let name = loaded.hairStrands, !name.isEmpty {
                hairStrandsFileName = name
            }
            for issue in m.validationIssues().prefix(8) {
                warn("PonyRig.json : \(issue)")
            }
            return m
        } catch {
            manifestTask = nil  // nouvel essai possible
            throw error
        }
    }

    /// Bibliothèque de clips. Fichier absent : bibliothèque vide (le poney reste jouable : pose de repos,
    /// procédural, déplacement) et avertissement. Fichier invalide : erreur typée.
    public func clips(for manifest: PonyRigManifest) async throws -> ClipLibrary {
        if let t = clipsTask {
            return try await t.value
        }
        let loc = try requireLocator()
        if !loc.exists(PonyResourceNames.clips) {
            warn("PonyClips.bin absent : poney sans animations de clips (pose de repos + procédural)")
            let empty = ClipLibrary.empty(manifest: manifest)
            clipsTask = Task { () throws -> ClipLibrary in empty }
            return empty
        }
        let task = Task.detached(priority: .userInitiated) { () throws -> ClipLibrary in
            let data = try loc.data(PonyResourceNames.clips)
            do {
                return try ClipLibrary(data: data, manifest: manifest)
            } catch {
                throw PonyAssetError.invalidClips(reason: String(describing: error))
            }
        }
        clipsTask = task
        do {
            return try await task.value
        } catch {
            clipsTask = nil
            throw error
        }
    }

    // MARK: Cartes de pelage

    /// Cartes du compositeur de robe (SPEC §4) + mèches des crins. `nil` si une carte obligatoire manque
    /// (la robe est alors rendue par simple teinte, repli journalisé).
    public func coatMaps(for manifest: PonyRigManifest) async -> CoatMaps? {
        if let t = coatMapsTask {
            return await t.value
        }
        guard let loc = locator else {
            warn(PonyAssetError.resourceFolderMissing.errorDescription ?? "ressources absentes")
            return nil
        }
        let names = PonyAssetLibrary.coatMapNames(manifest, hairStrands: hairStrandsFileName)
        let landmarks = PonyAssetLibrary.coatLandmarks(manifest)
        let task = Task.detached(priority: .userInitiated) { () -> CoatMaps? in
            func load(_ file: String) -> RGBA8Image? {
                guard loc.exists(file) else { return nil }
                do {
                    return try PonyImageIO.loadRGBA8(contentsOf: loc.url(for: file), name: file)
                } catch {
                    PonyLog.error((error as? LocalizedError)?.errorDescription ?? "\(file) : \(error)")
                    return nil
                }
            }
            guard let shading = load(names.shading), let regions = load(names.regions),
                  let params = load(names.params), let patterns = load(names.patterns) else {
                return nil
            }
            let strands = load(names.strands)
            let iris = load(PonyResourceNames.irisDetail)
            return CoatMaps(shading: shading, regions: regions, params: params, patterns: patterns,
                            hairStrands: strands, irisDetail: iris, landmarks: landmarks)
        }
        coatMapsTask = task
        let maps = await task.value
        if maps == nil {
            warn("cartes de pelage absentes ou illisibles (\(names.shading), \(names.regions), \(names.params), "
                + "\(names.patterns)) : robe rendue par teinte uniforme")
        } else if maps?.hairStrands == nil {
            warn("\(names.strands) absent : crins teintés sans recalcul de l'albedo")
        }
        return maps
    }

    /// Noms des cartes : `coat.maps` / `hair.maps.strands` du manifeste, sinon noms par défaut du SPEC.
    nonisolated static func coatMapNames(_ manifest: PonyRigManifest, hairStrands: String? = nil)
        -> (shading: String, regions: String, params: String, patterns: String, strands: String) {
        let maps = manifest.coat?["maps"]
        return (maps?["shading"]?.stringValue ?? PonyResourceNames.coatShading,
                maps?["regions"]?.stringValue ?? PonyResourceNames.coatRegions,
                maps?["params"]?.stringValue ?? PonyResourceNames.coatParams,
                maps?["patterns"]?.stringValue ?? PonyResourceNames.coatPatterns,
                hairStrands ?? PonyResourceNames.hairStrands)
    }

    /// Repères des cartes (`coat.landmarks` du manifeste, clés camelCase ou snake_case comme `s05_coat.py`), sinon
    /// `CoatLandmarks.default` [I] : l'export v1 n'écrit pas encore cette clé.
    nonisolated static func coatLandmarks(_ manifest: PonyRigManifest) -> CoatLandmarks {
        guard let lm = manifest.coat?["landmarks"] else { return CoatLandmarks.default }
        var out = CoatLandmarks.default
        if let v = lm.firstFloat(["coronet"]), v.isFinite { out.coronet = v }
        if let v = lm.firstFloat(["faceEyeV", "face_eye_v"]), v.isFinite { out.faceEyeV = v }
        if let v = lm.firstFloat(["faceEyeU", "face_eye_u"]), v.isFinite { out.faceEyeU = v }
        if let v = lm.firstFloat(["nostrilV", "nostril_v"]), v.isFinite { out.nostrilV = v }
        return out
    }

    // MARK: Modèles

    /// Gabarit (non cloné) d'un USDZ du dossier de ressources. Usage interne : préférer `instantiate…`.
    func template(_ relativePath: String) async throws -> Entity {
        if let t = templateTasks[relativePath] {
            return try await t.value
        }
        let loc = try requireLocator()
        let url = try loc.requireURL(relativePath)
        let task = Task { () throws -> Entity in
            do {
                return try await Entity(contentsOf: url, withName: nil)
            } catch {
                throw PonyAssetError.modelLoadFailed(relativePath, reason: error.localizedDescription)
            }
        }
        templateTasks[relativePath] = task
        do {
            return try await task.value
        } catch {
            templateTasks[relativePath] = nil
            throw error
        }
    }

    /// Nouveau clone du corps (`Pony.usdz`).
    public func instantiateBody() async throws -> Entity {
        let t = try await template(PonyResourceNames.body)
        return t.clone(recursive: true)
    }

    /// Nouveau clone d'une pièce (`Parts/<id>.usdz`, ou chemin `file` du manifeste).
    public func instantiatePart(_ id: String, file: String? = nil) async throws -> Entity {
        let path = (file?.isEmpty == false) ? file! : PonyResourceNames.part(id)
        let t = try await template(path)
        let e = t.clone(recursive: true)
        e.name = "part_\(id)"
        return e
    }

    /// Précharge des pièces (ex. crins par défaut) pour éviter un temps de chargement à la première sélection.
    public func preloadParts(_ ids: [String]) async {
        for id in ids {
            _ = try? await template(PonyResourceNames.part(id))
        }
    }

    /// Vide les caches (les poneys existants gardent leurs clones).
    public func purge() {
        manifestTask = nil
        hairStrandsFileName = nil
        clipsTask = nil
        coatMapsTask = nil
        templateTasks.removeAll()
        warnings.removeAll()
    }
}

/// Manifeste décodé + clés supplémentaires lues dans le JSON brut.
struct PonyLoadedManifest: Sendable {
    var manifest: PonyRigManifest
    var hairStrands: String?
}
