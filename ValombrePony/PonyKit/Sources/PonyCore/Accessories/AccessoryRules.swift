import Foundation

/// Problème détecté dans une sélection d'accessoires.
public struct AccessoryIssue: Sendable, Equatable {
    public var partID: String
    public var message: String

    public init(partID: String, message: String) {
        self.partID = partID
        self.message = message
    }
}

/// Catalogue des pièces du SPEC §6, utilisé quand le manifeste n'en déclare aucune (tests, prototypage).
/// Recopie de `PART_CATALOG` de `Pipeline/pony/runtime_export.py` (exporteur validé) : mêmes catégories,
/// emplacements, slots de matériaux, conflits, prérequis (« au moins une ») et masquages. En particulier
/// `fly_bonnet` « se porte avec filet ou licol » est une compatibilité, pas un prérequis [I, exporteur].
public enum PonyPartCatalog {
    static func make(_ id: String, _ category: String, _ slots: [String], _ materials: [String],
                     fabric: [String] = [], conflicts: [String] = [], requires: [String] = [],
                     hides: [String] = []) -> PonyRigManifest.Part {
        return PonyRigManifest.Part(id: id, file: "Parts/\(id).usdz", category: category, slots: slots,
                                    materialSlots: materials, fabricSlots: fabric, blendShapes: [],
                                    conflicts: conflicts, requires: requires, hides: hides)
    }

    public static let specParts: [PonyRigManifest.Part] = {
        let p = "slot_primary", s = "slot_secondary", a = "slot_accent", m = "slot_metal"
        let saddles = ["saddle_english", "saddle_western"]
        let headgear = ["bridle_snaffle", "halter"]
        return [
            make("mane_natural", "hair", ["mane"], [p]),
            make("mane_braided", "hair", ["mane"], [p]),
            make("mane_roached", "hair", ["mane"], [p]),
            make("forelock_natural", "hair", ["forelock"], [p]),
            make("forelock_braided", "hair", ["forelock"], [p]),
            make("tail_natural", "hair", ["tail"], [p]),
            make("tail_braided", "hair", ["tail"], [p]),
            make("feathers", "hair", ["feathers"], [p]),
            make("saddle_english", "tack", ["saddle"], [p, s, a, m], conflicts: ["rug_stable", "fly_sheet"]),
            make("saddle_western", "tack", ["saddle"], [p, s, a, m], conflicts: ["rug_stable", "fly_sheet"]),
            make("saddle_pad_english", "tack", ["pad"], [p, s, a], fabric: [p], requires: ["saddle_english"]),
            make("saddle_pad_western", "tack", ["pad"], [p, s], fabric: [p], requires: ["saddle_western"]),
            make("bridle_snaffle", "tack", ["headgear"], [p, s, m], conflicts: ["halter"]),
            make("halter", "tack", ["headgear"], [p, m, s], conflicts: ["bridle_snaffle"]),
            make("breastplate", "tack", ["breastplate"], [p, m], requires: saddles),
            make("boots_brushing", "protection", ["legs_front", "legs_hind"], [p, s, a], conflicts: ["bandages"]),
            make("boots_bell", "protection", ["hooves_front"], [p]),
            make("bandages", "protection", ["legs_front", "legs_hind"], [p], fabric: [p],
                 conflicts: ["boots_brushing"]),
            make("fly_bonnet", "protection", ["ears"], [p, s], fabric: [p]),
            make("ribbons_mane", "decorative", ["mane_deco"], [p], requires: ["mane_braided"]),
            make("pompons", "decorative", ["mane_deco"], [p], requires: ["mane_braided"]),
            make("flowers", "decorative", ["head_deco"], [p, s]),
            make("plume", "decorative", ["head_deco"], [p, s], requires: headgear),
            make("tail_bow", "decorative", ["tail_deco"], [p]),
            make("rug_stable", "rug", ["rug"], [p, s, a], fabric: [p],
                 conflicts: saddles + ["quarter_sheet"], hides: ["tail_bow"]),
            make("fly_sheet", "rug", ["rug"], [p, s], fabric: [p],
                 conflicts: saddles + ["quarter_sheet"], hides: ["tail_bow"]),
            make("quarter_sheet", "rug", ["quarter"], [p, s], fabric: [p], requires: saddles),
        ]
    }()
}

/// Règles des accessoires (SPEC §6) : conflits, prérequis, un seul par emplacement, résolution automatique
/// et pièces masquées.
///
/// Sémantique [I] :
/// - `conflicts` et `hides` contiennent des identifiants de pièces **ou** des noms d'emplacements ;
///   un conflit déclaré d'un seul côté vaut dans les deux sens.
/// - `requires` est une **disjonction** : au moins un des éléments (pièce ou emplacement) doit être porté
///   (ex. `breastplate` requiert `saddle_english` ou `saddle_western`).
/// - Deux pièces partageant un emplacement sont incompatibles.
/// - Les crins (`HairStyle`) comptent comme pièces portées : utiliser les variantes `hair:` pour que les
///   prérequis du type « requiert `mane_braided` » soient vérifiés. Sans `hair`, ces prérequis sur des pièces
///   de crins sont considérés comme satisfaits (information indisponible).
public struct AccessoryRules: Sendable {
    public let parts: [String: PonyRigManifest.Part]
    /// Ordre du catalogue (stable, pour l'interface).
    public let partOrder: [String]

    static let hairSlots: Set<String> = ["mane", "forelock", "tail", "feathers"]

    public init(manifest: PonyRigManifest) {
        self.init(parts: manifest.parts.isEmpty ? PonyPartCatalog.specParts : manifest.parts)
    }

    public init(parts: [PonyRigManifest.Part]) {
        var d: [String: PonyRigManifest.Part] = [:]
        var order: [String] = []
        for p in parts where d[p.id] == nil {
            d[p.id] = p
            order.append(p.id)
        }
        self.parts = d
        partOrder = order
    }

    public func part(_ id: String) -> PonyRigManifest.Part? {
        return parts[id]
    }

    public func isHairPart(_ p: PonyRigManifest.Part) -> Bool {
        if p.category == "hair" { return true }
        for s in p.slots where AccessoryRules.hairSlots.contains(s) {
            return true
        }
        return false
    }

    /// Pièces d'accessoires du catalogue (hors crins), dans l'ordre du manifeste.
    public var accessoryPartIDs: [String] {
        return partOrder.filter { id in
            guard let p = parts[id] else { return false }
            return !isHairPart(p)
        }
    }

    // MARK: Relations élémentaires

    func matches(_ entry: String, _ p: PonyRigManifest.Part) -> Bool {
        return entry == p.id || p.slots.contains(entry)
    }

    /// Vrai si les deux pièces ne peuvent pas être portées ensemble.
    public func conflicts(_ a: PonyRigManifest.Part, _ b: PonyRigManifest.Part) -> Bool {
        if a.id == b.id { return false }
        for s in a.slots where b.slots.contains(s) {
            return true
        }
        for e in a.conflicts where matches(e, b) {
            return true
        }
        for e in b.conflicts where matches(e, a) {
            return true
        }
        return false
    }

    public func conflicts(_ a: String, _ b: String) -> Bool {
        guard let pa = parts[a], let pb = parts[b] else { return false }
        return conflicts(pa, pb)
    }

    /// Prérequis satisfait parmi `present` (crins compris si `hairKnown`).
    func requirementSatisfied(_ p: PonyRigManifest.Part, present: [PonyRigManifest.Part], hairKnown: Bool) -> Bool {
        if p.requires.isEmpty { return true }
        for e in p.requires {
            for q in present where q.id != p.id && matches(e, q) {
                return true
            }
            if !hairKnown, let req = parts[e], isHairPart(req) {
                return true
            }
            if !hairKnown && AccessoryRules.hairSlots.contains(e) {
                return true
            }
        }
        return false
    }

    private func hairParts(_ hair: HairStyle?) -> [PonyRigManifest.Part] {
        guard let h = hair else { return [] }
        return h.partIDs.compactMap { parts[$0] }
    }

    private func presentParts(_ selections: [AccessorySelection], hair: HairStyle?) -> [PonyRigManifest.Part] {
        var out = hairParts(hair)
        for s in selections {
            if let p = parts[s.partID], !out.contains(where: { $0.id == p.id }) {
                out.append(p)
            }
        }
        return out
    }

    // MARK: Validation

    /// Valide une sélection (sans connaissance des crins : cf. `validate(_:hair:)`).
    public func validate(_ selections: [AccessorySelection]) -> [AccessoryIssue] {
        return validate(selections, hairStyle: nil)
    }

    /// Valide une sélection en tenant compte de la coiffure.
    public func validate(_ selections: [AccessorySelection], hair: HairStyle) -> [AccessoryIssue] {
        return validate(selections, hairStyle: hair)
    }

    func validate(_ selections: [AccessorySelection], hairStyle: HairStyle?) -> [AccessoryIssue] {
        var issues: [AccessoryIssue] = []
        var seen = Set<String>()
        var known: [PonyRigManifest.Part] = hairParts(hairStyle)
        for s in selections {
            if seen.contains(s.partID) {
                issues.append(AccessoryIssue(partID: s.partID, message: "Pièce « \(s.partID) » sélectionnée deux fois."))
                continue
            }
            seen.insert(s.partID)
            guard let p = parts[s.partID] else {
                issues.append(AccessoryIssue(partID: s.partID, message: "Pièce inconnue « \(s.partID) »."))
                continue
            }
            if !known.contains(where: { $0.id == p.id }) {
                known.append(p)
            }
        }
        for i in 0..<known.count {
            for j in (i + 1)..<max(i + 1, known.count) where conflicts(known[i], known[j]) {
                let shared = known[i].slots.filter { known[j].slots.contains($0) }
                let why = shared.isEmpty ? "est incompatible avec" : "occupe le même emplacement (\(shared.joined(separator: ", "))) que"
                issues.append(AccessoryIssue(partID: known[j].id,
                                             message: "« \(known[j].id) » \(why) « \(known[i].id) »."))
            }
        }
        for p in known where !requirementSatisfied(p, present: known, hairKnown: hairStyle != nil) {
            issues.append(AccessoryIssue(partID: p.id,
                                         message: "« \(p.id) » requiert : \(p.requires.joined(separator: " ou "))."))
        }
        return issues
    }

    // MARK: Résolution automatique

    /// Ajoute une pièce en résolvant les règles (sans connaissance des crins).
    public func resolving(adding: AccessorySelection, to selections: [AccessorySelection]) -> [AccessorySelection] {
        var hair: HairStyle? = nil
        return resolve(adding: adding, to: selections, hair: &hair, depth: 0)
    }

    /// Ajoute une pièce en résolvant les règles, coiffure comprise : une pièce de crins remplace celle de son
    /// emplacement dans `hair` ; un prérequis de crins (ex. `mane_braided`) est appliqué à `hair`.
    public func resolving(adding: AccessorySelection, to selections: [AccessorySelection],
                          hair: inout HairStyle) -> [AccessorySelection] {
        var h: HairStyle? = hair
        let out = resolve(adding: adding, to: selections, hair: &h, depth: 0)
        if let newHair = h { hair = newHair }
        return out
    }

    /// Retire une pièce et, en cascade, celles dont les prérequis ne sont plus satisfaits.
    public func removing(_ partID: String, from selections: [AccessorySelection],
                         hair: HairStyle? = nil) -> [AccessorySelection] {
        var out = selections.filter { $0.partID != partID }
        removeBroken(&out, hair: hair, keep: nil)
        return out
    }

    /// Après un changement de coiffure : retire les accessoires devenus invalides (ex. rubans sans tresses).
    public func resolving(hair: HairStyle, accessories: [AccessorySelection]) -> [AccessorySelection] {
        var out = accessories
        removeBroken(&out, hair: hair, keep: nil)
        return out
    }

    func resolve(adding: AccessorySelection, to selections: [AccessorySelection], hair: inout HairStyle?,
                 depth: Int) -> [AccessorySelection] {
        guard let newPart = parts[adding.partID] else { return selections }
        var result = selections.filter { $0.partID != adding.partID }

        if isHairPart(newPart), var h = hair {
            AccessoryRules.apply(hairPart: newPart, to: &h)
            hair = h
            removeBroken(&result, hair: hair, keep: nil)
            return result
        }

        // Retire tout ce qui entre en conflit (emplacement partagé ou exclusion explicite).
        result = result.filter { sel in
            guard let p = parts[sel.partID] else { return true }
            return !conflicts(p, newPart)
        }
        result.append(adding)

        // Prérequis : on ajoute la première pièce candidate si aucun n'est satisfait.
        if depth < 4 && !requirementSatisfied(newPart, present: presentParts(result, hair: hair),
                                              hairKnown: hair != nil) {
            if let candidate = firstCandidate(for: newPart) {
                if isHairPart(candidate) {
                    if var h = hair {
                        AccessoryRules.apply(hairPart: candidate, to: &h)
                        hair = h
                    }
                } else {
                    result = resolve(adding: AccessorySelection(partID: candidate.id), to: result, hair: &hair,
                                     depth: depth + 1)
                    // La pièce ajoutée doit rester en dernière position (ordre d'ajout).
                    if let idx = result.firstIndex(where: { $0.partID == adding.partID }) {
                        let sel = result.remove(at: idx)
                        result.append(sel)
                    } else {
                        result.append(adding)
                    }
                }
            }
        }
        removeBroken(&result, hair: hair, keep: adding.partID)
        return result
    }

    private func firstCandidate(for p: PonyRigManifest.Part) -> PonyRigManifest.Part? {
        for e in p.requires {
            if let q = parts[e] { return q }
            // Emplacement : première pièce du catalogue qui l'occupe.
            for id in partOrder {
                if let q = parts[id], q.slots.contains(e) { return q }
            }
        }
        return nil
    }

    static func apply(hairPart p: PonyRigManifest.Part, to hair: inout HairStyle) {
        if p.slots.contains("mane") {
            hair.mane = p.id
        } else if p.slots.contains("forelock") {
            hair.forelock = p.id
        } else if p.slots.contains("tail") {
            hair.tail = p.id
        } else if p.slots.contains("feathers") {
            hair.feathers = true
        }
    }

    /// Retire itérativement les sélections dont les prérequis ne sont pas satisfaits (sauf `keep`).
    func removeBroken(_ selections: inout [AccessorySelection], hair: HairStyle?, keep: String?) {
        var changed = true
        var guardCount = 0
        while changed && guardCount < 64 {
            changed = false
            guardCount += 1
            let present = presentParts(selections, hair: hair)
            for (i, s) in selections.enumerated() {
                if s.partID == keep { continue }
                guard let p = parts[s.partID] else { continue }
                if !requirementSatisfied(p, present: present, hairKnown: hair != nil) {
                    selections.remove(at: i)
                    changed = true
                    break
                }
            }
        }
    }

    // MARK: Pièces masquées

    /// Pièces portées mais masquées par une autre (ex. `tail_bow` sous `rug_stable`).
    public func hiddenPartIDs(for selections: [AccessorySelection], hair: HairStyle? = nil) -> Set<String> {
        let present = presentParts(selections, hair: hair)
        var hidden = Set<String>()
        for p in present {
            for e in p.hides {
                for q in present where q.id != p.id && matches(e, q) {
                    hidden.insert(q.id)
                }
            }
        }
        return hidden
    }

    /// Identifiants des pièces à afficher (crins + accessoires, moins les pièces masquées), ordre stable.
    public func visiblePartIDs(for selections: [AccessorySelection], hair: HairStyle) -> [String] {
        let hidden = hiddenPartIDs(for: selections, hair: hair)
        var out: [String] = []
        for p in presentParts(selections, hair: hair) where !hidden.contains(p.id) {
            out.append(p.id)
        }
        return out
    }
}
