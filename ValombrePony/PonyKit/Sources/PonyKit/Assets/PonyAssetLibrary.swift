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

    private var manifestTask: Task<PonyRigManifest, Error>?
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
            return try await t.value
        }
        let loc = try requireLocator()
        let task = Task.detached(priority: .userInitiated) { () throws -> PonyRigManifest in
            let data = try loc.data(PonyResourceNames.manifest)
            do {
                return try PonyRigManifest.decode(from: data)
            } catch {
                throw PonyAssetError.invalidManifest(reason: String(describing: error))
            }
        }
        manifestTask = task
        do {
            let m = try await task.value
            if m.joints.isEmpty {
                throw PonyAssetError.invalidManifest(reason: "aucun joint")
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
        let names = PonyAssetLibrary.coatMapNames(manifest)
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
                            hairStrands: strands, irisDetail: iris)
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

    /// Noms des cartes : `coat.maps` / `hair.maps` du manifeste, sinon noms par défaut du SPEC.
    nonisolated static func coatMapNames(_ manifest: PonyRigManifest)
        -> (shading: String, regions: String, params: String, patterns: String, strands: String) {
        let maps = manifest.coat?["maps"]
        return (maps?["shading"]?.stringValue ?? PonyResourceNames.coatShading,
                maps?["regions"]?.stringValue ?? PonyResourceNames.coatRegions,
                maps?["params"]?.stringValue ?? PonyResourceNames.coatParams,
                maps?["patterns"]?.stringValue ?? PonyResourceNames.coatPatterns,
                PonyResourceNames.hairStrands)
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
        clipsTask = nil
        coatMapsTask = nil
        templateTasks.removeAll()
        warnings.removeAll()
    }
}
