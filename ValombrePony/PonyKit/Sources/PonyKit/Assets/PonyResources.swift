import Foundation

/// Erreurs de chargement des ressources du poney. Les messages (`errorDescription`) sont en français et
/// destinés à être affichés tels quels par le jeu, qui peut alors montrer un repli (portrait 2D, etc.).
public enum PonyAssetError: Error, LocalizedError, Equatable, Sendable {
    /// Le dossier `Resources/` est introuvable dans le bundle du module (package mal intégré).
    case resourceFolderMissing
    /// Un fichier attendu est absent (chemin relatif au dossier de ressources).
    case missingResource(String)
    /// Le fichier existe mais n'a pas pu être lu.
    case unreadableResource(String, reason: String)
    /// `PonyRig.json` illisible ou incohérent.
    case invalidManifest(reason: String)
    /// `PonyClips.bin` illisible.
    case invalidClips(reason: String)
    /// Image PNG illisible ou dans un format non pris en charge.
    case invalidImage(String, reason: String)
    /// RealityKit n'a pas pu charger un USDZ.
    case modelLoadFailed(String, reason: String)

    public var errorDescription: String? {
        switch self {
        case .resourceFolderMissing:
            return "Ressources du poney introuvables : le dossier « Resources » du module PonyKit est absent. "
                + "Lancez l'export du pipeline (Pipeline/stages/s09_export.py) puis recompilez."
        case .missingResource(let path):
            return "Ressource du poney manquante : « \(path) »."
        case .unreadableResource(let path, let reason):
            return "Ressource du poney illisible : « \(path) » (\(reason))."
        case .invalidManifest(let reason):
            return "Description du squelette (PonyRig.json) invalide : \(reason)."
        case .invalidClips(let reason):
            return "Animations (PonyClips.bin) invalides : \(reason)."
        case .invalidImage(let path, let reason):
            return "Image « \(path) » illisible : \(reason)."
        case .modelLoadFailed(let path, let reason):
            return "Impossible de charger le modèle 3D « \(path) » : \(reason)."
        }
    }
}

/// Noms de fichiers du dossier de ressources (SPEC §9, sorties de `Pipeline/stages/s09_export.py`).
public enum PonyResourceNames {
    public static let manifest = "PonyRig.json"
    public static let clips = "PonyClips.bin"
    public static let body = "Pony.usdz"
    public static let quickLook = "Pony_QuickLook.usdz"
    /// Cartes de pelage par défaut (le manifeste peut les renommer : `coat.maps`).
    public static let coatShading = "coat_shading.png"
    public static let coatRegions = "coat_regions.png"
    public static let coatParams = "coat_params.png"
    public static let coatPatterns = "coat_patterns.png"
    /// Texture de mèches des crins (le manifeste peut la renommer : `hair.maps.strands`).
    public static let hairStrands = "hair_strands.png"
    /// Carte grise optionnelle de détail d'iris (non exportée en v1) [I].
    public static let irisDetail = "iris_detail.png"
    /// Images d'environnement équirectangulaires optionnelles (IBL) cherchées dans cet ordre [I] :
    /// aucune n'est produite par le pipeline v1 ; sans elles, un ciel dégradé est généré.
    public static let environmentCandidates = ["environment.exr", "environment.hdr", "environment.png",
                                               "environment.jpg"]

    /// Chemin relatif d'une pièce (`Parts/<id>.usdz`).
    public static func part(_ id: String) -> String {
        return "Parts/\(id).usdz"
    }
}

/// Localise les ressources du poney. Par défaut : dossier `Resources/` copié dans le bundle du module
/// (`resources: [.copy("Resources")]` dans `Package.swift`). Un autre dossier peut être fourni (contenu
/// téléchargé, tests).
public struct PonyResourceLocator: Sendable, Equatable {
    public var baseURL: URL

    public init(baseURL: URL) {
        self.baseURL = baseURL
    }

    /// Dossier `Resources/` du bundle du module PonyKit, ou `nil` s'il est introuvable.
    public static var bundled: PonyResourceLocator? {
        // `.copy("Resources")` conserve le dossier : on le cherche comme une ressource nommée « Resources »,
        // puis sous `resourceURL` (structure de bundle macOS `Contents/Resources/Resources`) [I].
        if let url = Bundle.module.url(forResource: "Resources", withExtension: nil) {
            return PonyResourceLocator(baseURL: url)
        }
        if let res = Bundle.module.resourceURL {
            let candidate = res.appendingPathComponent("Resources", isDirectory: true)
            if FileManager.default.fileExists(atPath: candidate.path) {
                return PonyResourceLocator(baseURL: candidate)
            }
        }
        return nil
    }

    /// URL d'un fichier (chemin relatif au dossier de ressources, `/` autorisé).
    public func url(for relativePath: String) -> URL {
        return baseURL.appendingPathComponent(relativePath)
    }

    public func exists(_ relativePath: String) -> Bool {
        return FileManager.default.fileExists(atPath: url(for: relativePath).path)
    }

    /// URL d'un fichier existant ; sinon `PonyAssetError.missingResource`.
    public func requireURL(_ relativePath: String) throws -> URL {
        let u = url(for: relativePath)
        guard FileManager.default.fileExists(atPath: u.path) else {
            throw PonyAssetError.missingResource(relativePath)
        }
        return u
    }

    /// Lit un fichier entier ; erreurs typées.
    public func data(_ relativePath: String) throws -> Data {
        let u = try requireURL(relativePath)
        do {
            return try Data(contentsOf: u)
        } catch {
            throw PonyAssetError.unreadableResource(relativePath, reason: error.localizedDescription)
        }
    }
}
