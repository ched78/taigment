import Foundation
import PonyCore

/// Sauvegarde / chargement des configurations en JSON (`PonyConfiguration.jsonData()`, clés triées) dans
/// `Documents/ValombrePony/Poneys/` de l'application. Erreurs typées en français.
public struct PonyConfigurationStore: Sendable {
    public enum StoreError: Error, LocalizedError, Sendable {
        case folderUnavailable(String)
        case writeFailed(String)
        case readFailed(String)
        case invalidJSON(String)

        public var errorDescription: String? {
            switch self {
            case .folderUnavailable(let r): return "Dossier de sauvegarde indisponible : \(r)."
            case .writeFailed(let r): return "Sauvegarde impossible : \(r)."
            case .readFailed(let r): return "Lecture impossible : \(r)."
            case .invalidJSON(let r): return "Fichier de poney invalide : \(r)."
            }
        }
    }

    /// Fichier sauvegardé.
    public struct Entry: Identifiable, Hashable, Sendable {
        public var id: URL { url }
        public let url: URL
        public let name: String
        public let modified: Date?
    }

    public let folder: URL

    /// Dossier par défaut : `Documents/ValombrePony/Poneys`.
    public init() throws {
        do {
            let docs = try FileManager.default.url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil,
                                                   create: true)
            folder = docs.appendingPathComponent("ValombrePony", isDirectory: true)
                .appendingPathComponent("Poneys", isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        } catch {
            throw StoreError.folderUnavailable(error.localizedDescription)
        }
    }

    public init(folder: URL) {
        self.folder = folder
    }

    /// Fichiers `.json` du dossier, du plus récent au plus ancien.
    public func list() -> [Entry] {
        let keys: [URLResourceKey] = [.contentModificationDateKey]
        guard let urls = try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: keys)
        else { return [] }
        let entries = urls.filter { $0.pathExtension.lowercased() == "json" }.map { url -> Entry in
            let date = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
            return Entry(url: url, name: url.deletingPathExtension().lastPathComponent, modified: date)
        }
        return entries.sorted { ($0.modified ?? .distantPast) > ($1.modified ?? .distantPast) }
    }

    /// Écrit la configuration sous un nom de fichier dérivé de son nom ; renvoie l'URL.
    @discardableResult
    public func save(_ configuration: PonyConfiguration) throws -> URL {
        let url = folder.appendingPathComponent(PonyConfigurationStore.fileName(for: configuration.name))
        do {
            let data = try configuration.jsonData(pretty: true)
            try data.write(to: url, options: .atomic)
            PonyLog.info("configuration sauvegardée : \(url.lastPathComponent)")
            return url
        } catch {
            throw StoreError.writeFailed(error.localizedDescription)
        }
    }

    /// Lit une configuration (fichier du dossier ou importé ; accès « security-scoped » géré).
    public func load(_ url: URL) throws -> PonyConfiguration {
        let scoped = url.startAccessingSecurityScopedResource()
        defer {
            if scoped { url.stopAccessingSecurityScopedResource() }
        }
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            throw StoreError.readFailed(error.localizedDescription)
        }
        do {
            return try PonyConfiguration.decode(from: data)
        } catch {
            throw StoreError.invalidJSON(error.localizedDescription)
        }
    }

    public func delete(_ entry: Entry) throws {
        do {
            try FileManager.default.removeItem(at: entry.url)
        } catch {
            throw StoreError.writeFailed(error.localizedDescription)
        }
    }

    /// Nom de fichier sûr (lettres, chiffres, `-`, `_`), « poney » si vide.
    static func fileName(for name: String) -> String {
        let folded = name.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "fr_FR"))
        var out = ""
        for ch in folded.unicodeScalars {
            if CharacterSet.alphanumerics.contains(ch) && ch.isASCII {
                out.unicodeScalars.append(ch)
            } else if ch == " " || ch == "-" || ch == "_" {
                out.append("_")
            }
        }
        if out.isEmpty { out = "poney" }
        return String(out.prefix(60)) + ".json"
    }
}
