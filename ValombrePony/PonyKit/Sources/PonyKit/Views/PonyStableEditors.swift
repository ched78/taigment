import CoreGraphics
import Foundation
import PonyCore
import SwiftUI
import UniformTypeIdentifiers

// Éditeurs de l'écurie (onglets Robe, Crins, Morphologie, Taille, Sauvegardes). L'onglet Accessoires est dans
// PonyAccessoriesEditor.swift.
//
// API vérifiées : `Slider(value:in:onEditingChanged:)` (Float : BinaryFloatingPoint), `ColorPicker(_:selection:
// supportsOpacity:)` avec `Binding<CGColor>` (iOS 14 / macOS 11), `Picker`, `Toggle`, `Form`, `ShareLink(item:
// subject:message:label:)` avec une `URL` (iOS 16 / macOS 13), `fileImporter(isPresented:allowedContentTypes:
// onCompletion:)` (iOS 14 / macOS 11), `UTType.json` (iOS 14 / macOS 11).

// MARK: - Briques communes

/// Nombre au format français (virgule décimale).
func ponyFrench(_ v: Float, digits: Int = 2) -> String {
    return String(format: "%.\(digits)f", Double(v)).replacingOccurrences(of: ".", with: ",")
}

/// Curseur titré avec valeur affichée.
struct PonySliderRow: View {
    let title: String
    @Binding var value: Float
    let range: ClosedRange<Float>
    var digits = 2
    var suffix = ""
    let onEditingChanged: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(title)
                Spacer()
                Text(ponyFrench(value, digits: digits) + suffix)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
            Slider(value: $value, in: range, onEditingChanged: onEditingChanged)
        }
    }
}

/// Sélecteur de couleur lié à une `PonyColor`.
struct PonyColorRow: View {
    let title: String
    @Binding var color: PonyColor

    var body: some View {
        ColorPicker(title, selection: Binding<CGColor>(get: { color.cgColor },
                                                       set: { color = PonyColor(cgColor: $0) }),
                    supportsOpacity: false)
    }
}

/// Couleur facultative (surcharge) : interrupteur + sélecteur.
struct PonyOptionalColorRow: View {
    let title: String
    @Binding var color: PonyColor?
    let fallback: PonyColor

    var body: some View {
        HStack {
            Toggle(title, isOn: Binding(get: { color != nil },
                                        set: { on in color = on ? (color ?? fallback) : nil }))
            if color != nil {
                ColorPicker(title, selection: Binding<CGColor>(get: { (color ?? fallback).cgColor },
                                                               set: { color = PonyColor(cgColor: $0) }),
                            supportsOpacity: false)
                    .labelsHidden()
                    .frame(width: 44)
            }
        }
    }
}

/// Pastille de couleur.
struct PonySwatch: View {
    let colors: [PonyColor]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(colors.indices, id: \.self) { i in
                Rectangle().fill(colors[i].swiftUIColor)
            }
        }
        .frame(width: 34, height: 22)
        .clipShape(RoundedRectangle(cornerRadius: 5))
        .overlay(RoundedRectangle(cornerRadius: 5).stroke(Color.secondary.opacity(0.4), lineWidth: 1))
    }
}

// MARK: - Robe

struct PonyCoatEditor: View {
    @Binding var draft: PonyConfiguration
    let onEditingChanged: (Bool) -> Void

    private static var zygosityLoci: [(String, WritableKeyPath<CoatGenotype, Zygosity>)] {
        return [("Dun (TBX3)", \.dun), ("Silver (PMEL17)", \.silver), ("Champagne (SLC36A1)", \.champagne),
                ("Gris (STX17)", \.grey), ("Rouan (KIT)", \.roan), ("Tobiano", \.tobiano),
                ("Overo « frame »", \.frameOvero), ("Sabino", \.sabino), ("Splashed white", \.splashedWhite),
                ("Blanc dominant", \.dominantWhite), ("Complexe léopard (LP)", \.leopardComplex),
                ("PATN1", \.patternOne)]
    }

    private static let legNames = ["Antérieur gauche", "Antérieur droit", "Postérieur gauche", "Postérieur droit"]

    private func zygosity(_ kp: WritableKeyPath<CoatGenotype, Zygosity>) -> Binding<Zygosity> {
        return Binding(get: { draft.coat.genotype[keyPath: kp] }, set: { draft.coat.genotype[keyPath: kp] = $0 })
    }

    private func expression(_ kp: WritableKeyPath<CoatExpression, Float>) -> Binding<Float> {
        return Binding(get: { draft.coat.expression[keyPath: kp] }, set: { draft.coat.expression[keyPath: kp] = $0 })
    }

    private func leg(_ i: Int) -> Binding<LegMarking> {
        return Binding(get: { draft.coat.legs[i] }, set: { draft.coat.legs[i] = $0 })
    }

    private func slider(_ title: String, _ kp: WritableKeyPath<CoatExpression, Float>,
                        _ range: ClosedRange<Float> = 0...1) -> some View {
        PonySliderRow(title: title, value: expression(kp), range: range, onEditingChanged: onEditingChanged)
    }

    var body: some View {
        // Sections séparées : un seul corps géant ralentirait (voire ferait échouer) la vérification de types.
        Form {
            presetsSection
            resultSection
            geneticsSection
            nuancesSection
            faceSection
            legsSection
            eyesSection
            overridesSection
        }
        .formStyle(.grouped)
    }

    private var presetsSection: some View {
        Section("Présets") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 8)], alignment: .leading, spacing: 8) {
                ForEach(CoatPreset.all) { preset in
                    presetButton(preset)
                }
            }
        }
    }

    private func presetButton(_ preset: CoatPreset) -> some View {
        let ph = preset.configuration.phenotype
        return Button {
            var c = preset.configuration
            c.seed = draft.coat.seed
            draft.coat = c
        } label: {
            HStack(spacing: 6) {
                PonySwatch(colors: [ph.bodyColor, ph.maneColor])
                Text(preset.name)
                    .font(.caption)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                Spacer(minLength: 0)
            }
        }
        .buttonStyle(.plain)
        .help(preset.summary)
    }

    private var resultSection: some View {
        let phenotype = draft.coat.phenotype
        return Section("Résultat") {
            HStack {
                PonySwatch(colors: [phenotype.bodyColor, phenotype.pointsColor, phenotype.maneColor])
                Text("\(phenotype.baseCoat.frenchName) · yeux \(phenotype.eye.frenchName.lowercased())")
                    .font(.callout)
            }
        }
    }

    private var geneticsSection: some View {
        Section("Génétique (simplifiée)") {
            Picker("Extension (MC1R)", selection: $draft.coat.genotype.extensionLocus) {
                ForEach(ExtensionGenotype.allCases, id: \.self) { v in
                    Text(PonyCoatLabels.name(v)).tag(v)
                }
            }
            Picker("Agouti (ASIP)", selection: $draft.coat.genotype.agouti) {
                ForEach(AgoutiGenotype.allCases, id: \.self) { v in
                    Text(PonyCoatLabels.name(v)).tag(v)
                }
            }
            Picker("Crème / perle", selection: $draft.coat.genotype.creamPearl) {
                ForEach(CreamPearlGenotype.allCases, id: \.self) { v in
                    Text(PonyCoatLabels.name(v)).tag(v)
                }
            }
            ForEach(PonyCoatEditor.zygosityLoci.indices, id: \.self) { i in
                zygosityPicker(PonyCoatEditor.zygosityLoci[i])
            }
        }
    }

    private func zygosityPicker(_ locus: (String, WritableKeyPath<CoatGenotype, Zygosity>)) -> some View {
        Picker(locus.0, selection: zygosity(locus.1)) {
            ForEach(Zygosity.allCases, id: \.self) { z in
                Text(PonyCoatLabels.name(z)).tag(z)
            }
        }
    }

    private var nuancesSection: some View {
        let g = draft.coat.genotype
        return Section("Nuances") {
            slider("Nuance (clair → foncé)", \.shade, -1...1)
            slider("Charbonné", \.sooty)
            slider("Pangaré", \.pangare)
            slider("Pommelures saisonnières", \.dapples)
            if g.extensionLocus == .blackAllowed && g.agouti != .black {
                slider("Hauteur des extrémités noires", \.pointsHeight)
            }
            if g.extensionLocus == .redOnly {
                slider("Crins lavés", \.flaxen)
            }
            if g.dun.isPresent {
                slider("Marques primitives", \.primitiveMarkings)
            }
            if g.grey.isPresent {
                slider("Stade du gris", \.greyStage)
                slider("Gris pommelé", \.greyDapples)
                slider("Truité", \.fleabitten)
            }
            if g.roan.isPresent {
                slider("Densité du rouan", \.roanDensity)
            }
            patternCoverageSliders(g)
            Button("Nouvelle variation (bruits)") {
                draft.coat.seed = UInt32.random(in: 1...UInt32.max)
            }
        }
    }

    @ViewBuilder
    private func patternCoverageSliders(_ g: CoatGenotype) -> some View {
        if g.tobiano.isPresent { slider("Couverture tobiano", \.tobianoCoverage) }
        if g.frameOvero.isPresent { slider("Couverture overo", \.overoCoverage) }
        if g.sabino.isPresent { slider("Couverture sabino", \.sabinoCoverage) }
        if g.splashedWhite.isPresent { slider("Couverture splashed white", \.splashCoverage) }
        if g.dominantWhite.isPresent { slider("Couverture blanc dominant", \.dominantWhiteCoverage) }
        if g.leopardComplex.isPresent {
            slider("Couverture léopard", \.leopardCoverage)
            slider("Taille des taches", \.spotSize)
            slider("Densité des taches", \.spotDensity)
            slider("Marmoré", \.varnish)
        }
    }

    private var faceSection: some View {
        Section("Marques de tête") {
            Picker("Marque", selection: $draft.coat.face.kind) {
                ForEach(FaceMarkingKind.allCases, id: \.self) { k in
                    Text(k.frenchName).tag(k)
                }
            }
            if draft.coat.face.kind != .absent {
                PonySliderRow(title: "Taille", value: $draft.coat.face.size, range: 0.3...2,
                              onEditingChanged: onEditingChanged)
                PonySliderRow(title: "Décalage latéral", value: $draft.coat.face.offsetU, range: -0.2...0.2,
                              onEditingChanged: onEditingChanged)
                PonySliderRow(title: "Décalage vertical", value: $draft.coat.face.offsetV, range: -0.2...0.2,
                              onEditingChanged: onEditingChanged)
            }
            PonySliderRow(title: "Irrégularité du bord", value: $draft.coat.face.irregularity, range: 0...1,
                          onEditingChanged: onEditingChanged)
            Toggle("Ladre au bout du nez", isOn: $draft.coat.face.snip)
            Toggle("Lèvres blanches", isOn: $draft.coat.face.lips)
        }
    }

    private var legsSection: some View {
        Section("Balzanes") {
            ForEach(0..<4, id: \.self) { i in
                legRow(i)
            }
        }
    }

    private func legRow(_ i: Int) -> some View {
        let marking = draft.coat.legs[i]
        return VStack(alignment: .leading, spacing: 4) {
            PonySliderRow(title: "\(PonyCoatEditor.legNames[i]) — \(marking.category.frenchName)",
                          value: leg(i).height, range: 0...1, onEditingChanged: onEditingChanged)
            if marking.height > 0 {
                Toggle("Mouchetures d'hermine", isOn: leg(i).ermine)
                    .font(.caption)
            }
        }
    }

    private var eyesSection: some View {
        Section("Yeux") {
            Picker("Iris", selection: $draft.coat.irisStyle) {
                ForEach(IrisStyle.allCases, id: \.self) { s in
                    Text(PonyCoatLabels.name(s)).tag(s)
                }
            }
        }
    }

    private var overridesSection: some View {
        let phenotype = draft.coat.phenotype
        return Section("Couleurs libres") {
            PonyOptionalColorRow(title: "Corps", color: $draft.coat.overrides.body, fallback: phenotype.bodyColor)
            PonyOptionalColorRow(title: "Extrémités", color: $draft.coat.overrides.points,
                                 fallback: phenotype.pointsColor)
            PonyOptionalColorRow(title: "Sabots", color: $draft.coat.overrides.hooves,
                                 fallback: phenotype.hoofColors.first ?? PonyColor(hex: "#2E2A27"))
            PonyOptionalColorRow(title: "Iris", color: $draft.coat.overrides.eyes, fallback: phenotype.eyeColor)
            PonyOptionalColorRow(title: "Peau", color: $draft.coat.overrides.skin, fallback: phenotype.skinColor)
        }
    }
}

// MARK: - Crins

struct PonyHairEditor: View {
    @Binding var draft: PonyConfiguration
    let rules: AccessoryRules
    let onEditingChanged: (Bool) -> Void
    @Binding var statusMessage: String?

    private func options(_ slot: String) -> [String] {
        let ids = rules.partOrder.filter { id in
            guard let p = rules.part(id) else { return false }
            return rules.isHairPart(p) && p.slots.contains(slot)
        }
        return ids
    }

    /// Change la coiffure via `setHair(_:rules:)` et explique les accessoires retirés.
    private func setHair(_ edit: (inout HairStyle) -> Void) {
        var h = draft.hair
        edit(&h)
        let before = draft.accessories.map { $0.partID }
        var next = draft
        next.setHair(h, rules: rules)
        let removed = before.filter { id in !next.accessories.contains(where: { $0.partID == id }) }
        draft = next
        if !removed.isEmpty {
            statusMessage = "Retiré (requiert une autre coiffure) : "
                + removed.map { PonyPartLabels.name($0) }.joined(separator: ", ")
        }
    }

    private func picker(_ title: String, slot: String, current: String,
                        assign: @escaping (inout HairStyle, String) -> Void) -> some View {
        let ids = options(slot)
        return Picker(title, selection: Binding(get: { current },
                                                set: { v in setHair { assign(&$0, v) } })) {
            ForEach(ids, id: \.self) { id in
                Text(PonyPartLabels.name(id)).tag(id)
            }
            if !ids.contains(current) {
                Text(PonyPartLabels.name(current)).tag(current)
            }
        }
    }

    var body: some View {
        let phenotype = draft.coat.phenotype
        Form {
            Section("Coiffure") {
                picker("Crinière", slot: "mane", current: draft.hair.mane) { $0.mane = $1 }
                picker("Toupet", slot: "forelock", current: draft.hair.forelock) { $0.forelock = $1 }
                picker("Queue", slot: "tail", current: draft.hair.tail) { $0.tail = $1 }
                if rules.part("feathers") != nil {
                    Toggle("Fanons", isOn: Binding(get: { draft.hair.feathers },
                                                   set: { v in setHair { $0.feathers = v } }))
                }
            }
            Section("Couleur des crins") {
                HStack {
                    Text("Couleur génétique")
                    Spacer()
                    PonySwatch(colors: [phenotype.maneColor])
                }
                PonyOptionalColorRow(title: "Couleur libre", color: $draft.coat.overrides.mane,
                                     fallback: phenotype.maneColor)
                PonySliderRow(title: "Pointes décolorées", value: $draft.coat.hair.tipLightening, range: 0...1,
                              onEditingChanged: onEditingChanged)
                PonySliderRow(title: "Mèches blanches", value: $draft.coat.hair.whiteStrands, range: 0...1,
                              onEditingChanged: onEditingChanged)
                PonyOptionalColorRow(title: "Mèches secondaires", color: $draft.coat.hair.secondaryColor,
                                     fallback: PonyColor(hex: "#D8C49A"))
                if draft.coat.hair.secondaryColor != nil {
                    PonySliderRow(title: "Part des mèches secondaires", value: $draft.coat.hair.secondaryFraction,
                                  range: 0...1, onEditingChanged: onEditingChanged)
                }
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Morphologie

struct PonyMorphologyEditor: View {
    @Binding var draft: PonyConfiguration
    let onEditingChanged: (Bool) -> Void

    private func row(_ title: String, _ kp: WritableKeyPath<MorphologyConfiguration, Float>,
                     _ range: ClosedRange<Float>) -> some View {
        PonySliderRow(title: title,
                      value: Binding(get: { draft.morphology[keyPath: kp] },
                                     set: { draft.morphology[keyPath: kp] = $0 }),
                      range: range, onEditingChanged: onEditingChanged)
    }

    private var bi: ClosedRange<Float> { MorphologyConfiguration.bipolarRange }
    private var unit: ClosedRange<Float> { MorphologyConfiguration.unitRange }

    var body: some View {
        Form {
            presetsSection
            proportionsSection
            bodySection
            headSection
            Section("Pieds") {
                row("Sabots", \.hoofSize, unit)
            }
        }
        .formStyle(.grouped)
    }

    private var presetsSection: some View {
        Section("Préréglages") {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 8)], spacing: 8) {
                ForEach(MorphologyPreset.all) { preset in
                    Button {
                        draft.apply(preset: preset)
                    } label: {
                        VStack(spacing: 2) {
                            Text(preset.name).font(.callout)
                            Text("\(Int((preset.withersHeight * 100).rounded())) cm")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                }
            }
            Button("Gabarit neutre") {
                draft.morphology = MorphologyConfiguration.default
            }
        }
    }

    private var proportionsSection: some View {
        Section("Proportions") {
            row("Longueur des membres", \.legLength, bi)
            row("Longueur de l'encolure", \.neckLength, bi)
            row("Longueur du corps", \.bodyLength, bi)
        }
    }

    private var bodySection: some View {
        Section("Corps") {
            row("Trapu", \.stocky, unit)
            row("Raffiné", \.refined, unit)
            row("État (maigre → gras)", \.condition, bi)
            row("Musculature", \.muscle, unit)
            row("Ventre", \.belly, unit)
            row("Encolure rouée", \.crest, unit)
            row("Ossature", \.bone, unit)
            row("Type Shetland", \.shetland, unit)
        }
    }

    private var headSection: some View {
        Section("Tête") {
            row("Profil (busqué → camus)", \.headShape, bi)
            row("Tête courte", \.headShort, unit)
            row("Museau large", \.muzzleBroad, unit)
            row("Taille de la tête", \.headScale, MorphologyConfiguration.headScaleRange)
            row("Taille des oreilles", \.earScale, MorphologyConfiguration.earScaleRange)
            row("Taille des yeux", \.eyeScale, MorphologyConfiguration.eyeScaleRange)
        }
    }
}

// MARK: - Taille

struct PonySizeEditor: View {
    @Binding var draft: PonyConfiguration
    let onEditingChanged: (Bool) -> Void

    /// Catégories de poneys de compétition (FFE, à la toise, sans fers) [NV : barème cité de mémoire].
    private var category: String {
        let h = draft.clampedWithersHeight
        if h <= 1.07 { return "Catégorie A (≤ 1,07 m)" }
        if h <= 1.30 { return "Catégorie B (≤ 1,30 m)" }
        if h <= 1.40 { return "Catégorie C (≤ 1,40 m)" }
        return "Catégorie D (≤ 1,48 m)"
    }

    var body: some View {
        let range = PonyConfiguration.withersHeightRange
        Form {
            Section("Hauteur au garrot") {
                PonySliderRow(title: "Garrot", value: $draft.withersHeight, range: range, digits: 2, suffix: " m",
                              onEditingChanged: onEditingChanged)
                HStack {
                    Text("\(Int((draft.clampedWithersHeight * 100).rounded())) cm")
                        .font(.title2.monospacedDigit())
                    Spacer()
                    Text(category)
                        .foregroundStyle(.secondary)
                }
                Text("Échelle du modèle : × \(ponyFrench(draft.entityScale, digits: 3)) (gabarit 1,30 m). "
                    + "Allures et cadences suivent la similitude de Froude.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
            Section("Repères") {
                ForEach(MorphologyPreset.all) { preset in
                    Button {
                        draft.withersHeight = preset.withersHeight
                    } label: {
                        HStack {
                            Text(preset.name)
                            Spacer()
                            Text("\(ponyFrench(preset.withersHeight)) m").foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
    }
}

// MARK: - Sauvegardes

struct PonyFilesEditor: View {
    @Binding var draft: PonyConfiguration
    @Binding var statusMessage: String?
    @State private var entries: [PonyConfigurationStore.Entry] = []
    @State private var importing = false

    private var store: PonyConfigurationStore? {
        return try? PonyConfigurationStore()
    }

    private func refresh() {
        entries = store?.list() ?? []
    }

    private func report(_ error: Error) {
        statusMessage = (error as? LocalizedError)?.errorDescription ?? "\(error)"
        PonyLog.error(statusMessage ?? "")
    }

    var body: some View {
        Form {
            Section("Poney actuel") {
                Button {
                    guard let s = store else {
                        statusMessage = "Dossier de sauvegarde indisponible."
                        return
                    }
                    do {
                        let url = try s.save(draft)
                        statusMessage = "Sauvegardé : \(url.lastPathComponent)"
                        refresh()
                    } catch {
                        report(error)
                    }
                } label: {
                    Label("Sauvegarder « \(draft.name) »", systemImage: "square.and.arrow.down")
                }
                Button {
                    importing = true
                } label: {
                    Label("Importer un fichier JSON…", systemImage: "doc.badge.plus")
                }
                Button(role: .destructive) {
                    let name = draft.name
                    draft = PonyConfiguration.default
                    draft.name = name
                } label: {
                    Label("Réinitialiser", systemImage: "arrow.counterclockwise")
                }
            }
            Section("Sauvegardes") {
                if entries.isEmpty {
                    Text("Aucune sauvegarde.").foregroundStyle(.secondary)
                }
                ForEach(entries) { entry in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(entry.name)
                            if let d = entry.modified {
                                Text(d.formatted(date: .abbreviated, time: .shortened))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        Spacer()
                        Button("Charger") {
                            guard let s = store else { return }
                            do {
                                draft = try s.load(entry.url)
                                statusMessage = "Chargé : \(entry.name)"
                            } catch {
                                report(error)
                            }
                        }
                        .buttonStyle(.bordered)
                        ShareLink(item: entry.url) {
                            Image(systemName: "square.and.arrow.up")
                        }
                        Button(role: .destructive) {
                            do {
                                try store?.delete(entry)
                                refresh()
                            } catch {
                                report(error)
                            }
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                    }
                }
            }
        }
        .formStyle(.grouped)
        .onAppear(perform: refresh)
        .fileImporter(isPresented: $importing, allowedContentTypes: [UTType.json]) { result in
            switch result {
            case .success(let url):
                do {
                    guard let s = store else { return }
                    draft = try s.load(url)
                    statusMessage = "Importé : \(url.lastPathComponent)"
                } catch {
                    report(error)
                }
            case .failure(let error):
                report(error)
            }
        }
    }
}
