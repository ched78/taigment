import Foundation
import PonyCore

// Libellés français de l'interface (allures, actions, pièces, slots, génétique). Les termes équestres sont
// usuels [NV : non vérifiés auprès de l'IFCE / FFE dans cette session].

extension PonyGait {
    /// Nom affiché de l'allure. `canter` = galop de travail, `gallop` = galop de course (SPEC §7).
    public var frenchName: String {
        switch self {
        case .idle: return "Arrêt"
        case .walk: return "Pas"
        case .trot: return "Trot"
        case .canter: return "Galop"
        case .gallop: return "Galop de course"
        case .back: return "Reculer"
        case .turnInPlace: return "Pivot"
        }
    }

    /// Symbole SF Symbols indicatif de l'allure (nom vérifié à l'œil seulement [I]).
    public var symbolName: String {
        switch self {
        case .idle: return "pause.circle"
        case .walk: return "figure.walk"
        case .trot: return "hare"
        case .canter, .gallop: return "bolt.fill"
        case .back: return "arrow.uturn.backward"
        case .turnInPlace: return "arrow.triangle.2.circlepath"
        }
    }
}

extension PonyAction {
    /// Verbe affiché sur les boutons.
    public var frenchName: String {
        switch self {
        case .graze: return "Brouter"
        case .rear: return "Se cabrer"
        case .headShake: return "Secouer la tête"
        case .neigh: return "Hennir"
        case .paw: return "Gratter"
        case .lieDown: return "Se coucher"
        case .getUp: return "Se relever"
        case .roll: return "Se rouler"
        case .bodyShake: return "S'ébrouer"
        }
    }

    /// Nom de l'activité en cours (indicateur d'allure).
    public var activityName: String {
        switch self {
        case .graze: return "Broute"
        case .rear: return "Se cabre"
        case .headShake: return "Secoue la tête"
        case .neigh: return "Hennit"
        case .paw: return "Gratte le sol"
        case .lieDown: return "Couché"
        case .getUp: return "Se relève"
        case .roll: return "Se roule"
        case .bodyShake: return "S'ébroue"
        }
    }
}

/// Libellés des pièces, catégories et slots (SPEC §6).
public enum PonyPartLabels {
    /// Nom français d'une pièce ; identifiant inconnu : l'identifiant lui-même.
    public static func name(_ id: String) -> String {
        return names[id] ?? id
    }

    static let names: [String: String] = [
        "mane_natural": "Crinière libre",
        "mane_braided": "Crinière tressée",
        "mane_roached": "Crinière rasée",
        "forelock_natural": "Toupet libre",
        "forelock_braided": "Toupet tressé",
        "tail_natural": "Queue libre",
        "tail_braided": "Queue tressée",
        "feathers": "Fanons",
        "saddle_english": "Selle anglaise",
        "saddle_western": "Selle western",
        "saddle_pad_english": "Tapis de selle (anglais)",
        "saddle_pad_western": "Tapis de selle (western)",
        "bridle_snaffle": "Filet (mors simple)",
        "halter": "Licol et longe",
        "breastplate": "Collier de chasse",
        "boots_brushing": "Guêtres",
        "boots_bell": "Cloches",
        "bandages": "Bandes",
        "fly_bonnet": "Bonnet anti-mouches",
        "ribbons_mane": "Rubans de crinière",
        "pompons": "Pompons",
        "flowers": "Fleurs",
        "plume": "Plumet",
        "tail_bow": "Nœud de queue",
        "rug_stable": "Couverture d'écurie",
        "fly_sheet": "Chemise anti-mouches",
        "quarter_sheet": "Couvre-reins",
    ]

    /// Catégories d'accessoires dans l'ordre de l'interface (identifiant du manifeste → nom). Le pipeline écrit
    /// `decorative` ; `decoration` (orthographe du commentaire du manifeste) est accepté comme alias.
    public static let categoryOrder: [(id: String, name: String)] = [
        ("tack", "Sellerie"),
        ("protection", "Protections"),
        ("decorative", "Décoratifs"),
        ("rug", "Couvertures"),
    ]

    /// Catégorie normalisée (alias, catégorie vide → « other »).
    public static func normalizedCategory(_ category: String) -> String {
        switch category {
        case "decoration", "decor", "deco": return "decorative"
        case "": return "other"
        default: return category
        }
    }

    public static func categoryName(_ category: String) -> String {
        let c = normalizedCategory(category)
        if c == "hair" { return "Crins" }
        return categoryOrder.first(where: { $0.id == c })?.name ?? "Autres"
    }

    /// Libellés des slots de matériaux par pièce, dans l'ordre de `materialSlots` (SPEC §6, colonne « Slots »).
    static let slotLabelsByPart: [String: [String]] = [
        "saddle_english": ["Cuir", "Siège", "Accent", "Métal"],
        "saddle_western": ["Cuir", "Siège", "Coutures", "Métal"],
        "saddle_pad_english": ["Tissu", "Passepoil", "Galon"],
        "saddle_pad_western": ["Tissu", "Bordure"],
        "bridle_snaffle": ["Cuir", "Frontal", "Métal"],
        "halter": ["Sangles", "Métal", "Longe"],
        "breastplate": ["Cuir", "Métal"],
        "boots_brushing": ["Coque", "Sangles", "Doublure"],
        "boots_bell": ["Coque"],
        "bandages": ["Tissu"],
        "fly_bonnet": ["Tricot", "Galon"],
        "ribbons_mane": ["Ruban"],
        "pompons": ["Laine"],
        "flowers": ["Fleurs", "Feuillage"],
        "plume": ["Plumes", "Attache"],
        "tail_bow": ["Ruban"],
        "rug_stable": ["Tissu", "Bordure", "Sangles"],
        "fly_sheet": ["Maille", "Bordure"],
        "quarter_sheet": ["Tissu", "Bordure"],
    ]

    /// Libellé d'un slot de matériau d'une pièce.
    public static func slotLabel(part: PonyRigManifest.Part, slot: String) -> String {
        if let labels = slotLabelsByPart[part.id], let i = part.materialSlots.firstIndex(of: slot), i < labels.count {
            return labels[i]
        }
        switch slot {
        case "slot_primary": return "Principal"
        case "slot_secondary": return "Secondaire"
        case "slot_accent": return "Accent"
        case "slot_metal": return "Métal"
        default: return slot
        }
    }
}

/// Libellés de la génétique simplifiée (Docs/COAT.md §3, [NV]).
public enum PonyCoatLabels {
    public static func name(_ v: ExtensionGenotype) -> String {
        switch v {
        case .blackAllowed: return "E/_ (noir possible)"
        case .redOnly: return "e/e (alezan)"
        }
    }

    public static func name(_ v: AgoutiGenotype) -> String {
        switch v {
        case .bay: return "A (bai)"
        case .sealBrown: return "At (bai brun)"
        case .black: return "a/a (noir)"
        }
    }

    public static func name(_ v: CreamPearlGenotype) -> String {
        switch v {
        case .noDilution: return "N/N (sans dilution)"
        case .cream: return "Cr/N (crème simple)"
        case .doubleCream: return "Cr/Cr (double crème)"
        case .pearlCarrier: return "prl/N (porteur perle)"
        case .pearl: return "prl/prl (perle)"
        case .creamPearl: return "Cr/prl (crème + perle)"
        }
    }

    public static func name(_ v: Zygosity) -> String {
        switch v {
        case .absent: return "Absent"
        case .heterozygous: return "Une copie"
        case .homozygous: return "Deux copies"
        }
    }

    public static func name(_ v: IrisStyle) -> String {
        switch v {
        case .automatic: return "Selon la robe"
        case .brown: return "Brun"
        case .amber: return "Ambre"
        case .blue: return "Bleu"
        case .vairon: return "Vairon"
        }
    }
}
