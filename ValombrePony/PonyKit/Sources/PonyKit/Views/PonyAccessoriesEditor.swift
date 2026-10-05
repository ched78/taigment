import CoreGraphics
import Foundation
import PonyCore
import SwiftUI

/// Onglet « Accessoires » de l'écurie : pièces par catégorie, ajout/retrait résolus par `AccessoryRules`
/// (variantes tenant compte de la coiffure : `resolving(adding:to:hair:)`, `removing(_:from:hair:)`,
/// `validate(_:hair:)`, `hiddenPartIDs(for:hair:)`), conséquences expliquées AVANT l'ajout (pièces remplacées,
/// prérequis ajoutés, coiffure modifiée), couleurs par slot (`ColorPicker`) et motif des slots tissu.
struct PonyAccessoriesEditor: View {
    @Binding var draft: PonyConfiguration
    let rules: AccessoryRules
    @Binding var statusMessage: String?

    private struct Effect {
        var removed: [String] = []
        var added: [String] = []
        var hairChanges: [String] = []

        var isEmpty: Bool { removed.isEmpty && added.isEmpty && hairChanges.isEmpty }
    }

    private var categories: [(id: String, name: String)] {
        var out = PonyPartLabels.categoryOrder
        let known = Set(out.map { $0.id })
        let others = rules.accessoryPartIDs.compactMap { rules.part($0) }
            .map { PonyPartLabels.normalizedCategory($0.category) }
            .filter { !known.contains($0) }
        if !others.isEmpty {
            out.append(("other", "Autres"))
        }
        return out
    }

    private func parts(in category: String) -> [PonyRigManifest.Part] {
        let known = Set(PonyPartLabels.categoryOrder.map { $0.id })
        return rules.accessoryPartIDs.compactMap { rules.part($0) }.filter { p in
            let c = PonyPartLabels.normalizedCategory(p.category)
            return category == "other" ? !known.contains(c) : c == category
        }
    }

    private func isWorn(_ id: String) -> Bool {
        return draft.accessories.contains(where: { $0.partID == id })
    }

    /// Conséquences d'un ajout, calculées sur une copie.
    private func effect(ofAdding id: String) -> Effect {
        var hair = draft.hair
        let after = rules.resolving(adding: AccessorySelection(partID: id), to: draft.accessories, hair: &hair)
        let before = Set(draft.accessories.map { $0.partID })
        let afterIDs = Set(after.map { $0.partID })
        var e = Effect()
        e.removed = draft.accessories.map { $0.partID }.filter { !afterIDs.contains($0) }
        e.added = after.map { $0.partID }.filter { !before.contains($0) && $0 != id }
        if hair.mane != draft.hair.mane { e.hairChanges.append(PonyPartLabels.name(hair.mane)) }
        if hair.forelock != draft.hair.forelock { e.hairChanges.append(PonyPartLabels.name(hair.forelock)) }
        if hair.tail != draft.hair.tail { e.hairChanges.append(PonyPartLabels.name(hair.tail)) }
        return e
    }

    private func reason(removing other: String, for id: String) -> String {
        guard let a = rules.part(id), let b = rules.part(other) else { return "incompatible" }
        let shared = a.slots.filter { b.slots.contains($0) }
        return shared.isEmpty ? "incompatible" : "même emplacement"
    }

    private func describe(_ e: Effect, adding id: String) -> String {
        var parts: [String] = []
        if !e.removed.isEmpty {
            parts.append("remplace " + e.removed.map { "\(PonyPartLabels.name($0)) (\(reason(removing: $0, for: id)))" }
                .joined(separator: ", "))
        }
        if !e.added.isEmpty {
            parts.append("ajoute " + e.added.map { "\(PonyPartLabels.name($0)) (requis)" }.joined(separator: ", "))
        }
        if !e.hairChanges.isEmpty {
            parts.append("coiffure : " + e.hairChanges.joined(separator: ", "))
        }
        return parts.joined(separator: " ; ")
    }

    /// Pièce portée qui masque `id` (ex. couverture sur le nœud de queue).
    private func hider(of id: String) -> String? {
        guard let target = rules.part(id) else { return nil }
        for sel in draft.accessories where sel.partID != id {
            guard let p = rules.part(sel.partID) else { continue }
            if p.hides.contains(id) || p.hides.contains(where: { target.slots.contains($0) }) {
                return p.id
            }
        }
        return nil
    }

    private func toggle(_ part: PonyRigManifest.Part) {
        if isWorn(part.id) {
            let before = draft.accessories.map { $0.partID }
            draft.removeAccessory(part.id, rules: rules)
            let also = before.filter { id in id != part.id && !draft.accessories.contains(where: { $0.partID == id }) }
            statusMessage = "Retiré : \(PonyPartLabels.name(part.id))"
                + (also.isEmpty ? "" : " — retiré aussi (en dépendait) : "
                    + also.map { PonyPartLabels.name($0) }.joined(separator: ", "))
        } else {
            let e = effect(ofAdding: part.id)
            draft.add(AccessorySelection(partID: part.id), rules: rules)
            statusMessage = "Ajouté : \(PonyPartLabels.name(part.id))" + (e.isEmpty ? "" : " — " + describe(e, adding: part.id))
        }
    }

    private func slotColor(_ part: PonyRigManifest.Part, _ slot: String) -> Binding<CGColor> {
        let id = part.id
        return Binding<CGColor>(
            get: {
                let c = draft.accessories.first(where: { $0.partID == id })?.slotColors[slot]
                return (c ?? PonyDefaultColors.color(for: part, slot: slot)).cgColor
            },
            set: { newValue in
                if let i = draft.accessories.firstIndex(where: { $0.partID == id }) {
                    draft.accessories[i].slotColors[slot] = PonyColor(cgColor: newValue)
                }
            })
    }

    private func pattern(_ id: String) -> Binding<FabricPattern> {
        return Binding<FabricPattern>(
            get: { draft.accessories.first(where: { $0.partID == id })?.pattern ?? .plain },
            set: { newValue in
                if let i = draft.accessories.firstIndex(where: { $0.partID == id }) {
                    draft.accessories[i].pattern = newValue == .plain ? nil : newValue
                }
            })
    }

    var body: some View {
        let issues = rules.validate(draft.accessories, hair: draft.hair)
        Form {
            if !issues.isEmpty {
                Section("À corriger") {
                    ForEach(issues.indices, id: \.self) { i in
                        Label(issues[i].message, systemImage: "exclamationmark.triangle")
                            .foregroundStyle(.orange)
                    }
                }
            }
            let cats = categories
            ForEach(cats.indices, id: \.self) { ci in
                let category = cats[ci]
                let list = parts(in: category.id)
                if !list.isEmpty {
                    Section(category.name) {
                        ForEach(list, id: \.id) { part in
                            row(part)
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    private func row(_ part: PonyRigManifest.Part) -> some View {
        let worn = isWorn(part.id)
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(PonyPartLabels.name(part.id))
                    if worn, let h = hider(of: part.id) {
                        Text("Masqué par : \(PonyPartLabels.name(h))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else if !worn {
                        let e = effect(ofAdding: part.id)
                        if !e.isEmpty {
                            let text = describe(e, adding: part.id)
                            Text(text.prefix(1).uppercased() + text.dropFirst())
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if !part.requires.isEmpty {
                            Text("Requiert : " + part.requires.map { PonyPartLabels.name($0) }.joined(separator: " ou "))
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                    }
                }
                Spacer()
                Button(worn ? "Retirer" : "Ajouter") {
                    toggle(part)
                }
                .buttonStyle(.bordered)
                .tint(worn ? Color.red : Color.accentColor)
            }
            if worn {
                DisclosureGroup("Couleurs\(part.fabricSlots.isEmpty ? "" : " et motif")") {
                    ForEach(part.materialSlots, id: \.self) { slot in
                        ColorPicker(PonyPartLabels.slotLabel(part: part, slot: slot), selection: slotColor(part, slot),
                                    supportsOpacity: false)
                    }
                    if !part.fabricSlots.isEmpty {
                        Picker("Motif", selection: pattern(part.id)) {
                            ForEach(FabricPattern.allCases, id: \.self) { p in
                                Text(p.displayName).tag(p)
                            }
                        }
                    }
                }
                .font(.callout)
            }
        }
    }
}
