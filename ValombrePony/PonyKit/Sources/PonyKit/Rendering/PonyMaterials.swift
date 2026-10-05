import Foundation
import PonyCore
import RealityKit

/// Noms de matériaux du contrat pipeline ⇄ runtime (SPEC §4 et §6).
public enum PonyMaterialNames {
    public static let coat = "M_Coat"
    public static let eye = "M_Eye"
    public static let lashes = "M_Lashes"
    public static let mouth = "M_Mouth"
    public static let primary = "slot_primary"
    public static let secondary = "slot_secondary"
    public static let accent = "slot_accent"
    public static let metal = "slot_metal"
    public static let slots = [primary, secondary, accent, metal]
}

/// Modification déclarative d'un matériau `PhysicallyBasedMaterial`, appliquée par-dessus le matériau
/// **d'origine** (importé de l'USDZ) : appliquer deux fois la même surcharge donne le même résultat.
struct PonyMaterialOverride {
    /// Teinte multipliée à la texture (`baseColor.tint`). `nil` = teinte d'origine.
    var tint: PonyColor?
    /// Texture de couleur de base remplaçant celle de l'USDZ. `nil` = texture d'origine.
    var baseColorTexture: TextureResource?
    /// Retire la texture de couleur de base (repli « teinte unie »).
    var removeBaseColorTexture = false
    /// Découpe alpha (`opacityThreshold`) ; `nil` = valeur d'origine.
    var opacityThreshold: Float?
    /// Double face (`faceCulling = .none`) : l'import USD de RealityKit ignore `doubleSided` (realitykit.md §5.1).
    var doubleSided = false

    init(tint: PonyColor? = nil, baseColorTexture: TextureResource? = nil, removeBaseColorTexture: Bool = false,
         opacityThreshold: Float? = nil, doubleSided: Bool = false) {
        self.tint = tint
        self.baseColorTexture = baseColorTexture
        self.removeBaseColorTexture = removeBaseColorTexture
        self.opacityThreshold = opacityThreshold
        self.doubleSided = doubleSided
    }

    func apply(to material: inout PhysicallyBasedMaterial) {
        if let tex = baseColorTexture {
            material.baseColor.texture = PhysicallyBasedMaterial.Texture(tex)
        } else if removeBaseColorTexture {
            material.baseColor.texture = nil
        }
        if let t = tint {
            material.baseColor.tint = t.platformColor
        }
        if let threshold = opacityThreshold {
            material.opacityThreshold = threshold
        }
        if doubleSided {
            material.faceCulling = .none
        }
    }
}

/// Matériaux d'une hiérarchie importée (corps ou pièce). Mémorise les matériaux d'origine de chaque entité
/// portant un `ModelComponent`, puis reconstruit la liste à partir des originaux + surcharges par nom.
///
/// Identification par `Material.name` (iOS 18 / macOS 15, `String?`, lecture seule) : on compare le nom
/// complet puis son dernier segment (le nom importé peut être un chemin USD, ex. `/Pony/Materials/M_Coat`) [I].
/// Seuls les `PhysicallyBasedMaterial` sont modifiés (type créé par l'import USDZ, realitykit.md §5.1) ; un autre
/// type est laissé tel quel et journalisé une fois.
@MainActor
final class PonyMaterialSet {
    private struct Entry {
        let entity: Entity
        let original: [any Material]
        let names: [String]
    }

    let label: String
    private var entries: [Entry] = []
    private var overrides: [String: PonyMaterialOverride] = [:]
    private var warnedNonPBR = Set<String>()

    init(root: Entity, label: String) {
        self.label = label
        for e in PonyEntityTree.modelEntities(in: root) {
            guard let model = e.components[ModelComponent.self] else { continue }
            let names = model.materials.map { PonyMaterialSet.shortName($0.name) }
            entries.append(Entry(entity: e, original: model.materials, names: names))
        }
    }

    static func shortName(_ name: String?) -> String {
        guard let n = name, !n.isEmpty else { return "" }
        return PonyEntityTree.shortName(n)
    }

    /// Noms (courts) des matériaux présents, sans doublon, ordre de découverte.
    var materialNames: [String] {
        var out: [String] = []
        for e in entries {
            for n in e.names where !n.isEmpty && !out.contains(n) {
                out.append(n)
            }
        }
        return out
    }

    func contains(_ name: String) -> Bool {
        return entries.contains { $0.names.contains(name) }
    }

    /// Entités modèles (pour les ombres de contact et l'éclairage d'ambiance).
    var modelEntities: [Entity] {
        return entries.map { $0.entity }
    }

    /// Définit (ou retire avec `nil`) la surcharge d'un matériau ; effective au prochain `commit()`.
    func setOverride(_ name: String, _ override: PonyMaterialOverride?) {
        overrides[name] = override
    }

    func override(for name: String) -> PonyMaterialOverride? {
        return overrides[name]
    }

    func removeAllOverrides() {
        overrides.removeAll()
    }

    /// Reconstruit les matériaux de chaque entité (originaux + surcharges) et réécrit les `ModelComponent`.
    func commit() {
        for entry in entries {
            guard var model = entry.entity.components[ModelComponent.self] else { continue }
            var materials: [any Material] = []
            materials.reserveCapacity(entry.original.count)
            for (i, original) in entry.original.enumerated() {
                let name = i < entry.names.count ? entry.names[i] : ""
                guard let ov = overrides[name] else {
                    materials.append(original)
                    continue
                }
                if var pbr = original as? PhysicallyBasedMaterial {
                    ov.apply(to: &pbr)
                    materials.append(pbr)
                } else {
                    if !warnedNonPBR.contains(name) {
                        warnedNonPBR.insert(name)
                        PonyLog.warning("\(label) : matériau « \(name) » de type \(type(of: original)) non modifiable "
                            + "(PhysicallyBasedMaterial attendu) — laissé tel quel")
                    }
                    materials.append(original)
                }
            }
            // Le nombre de matériaux doit rester celui du maillage (une entrée par partie).
            if materials.count == model.materials.count {
                model.materials = materials
                entry.entity.components.set(model)
            }
        }
    }
}
