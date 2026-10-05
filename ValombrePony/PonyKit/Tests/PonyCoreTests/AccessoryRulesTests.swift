import XCTest
@testable import PonyCore

final class AccessoryRulesTests: XCTestCase {

    private let rules = AccessoryRules(manifest: PonyRigDefaults.syntheticManifest())

    private func sel(_ id: String) -> AccessorySelection {
        return AccessorySelection(partID: id)
    }

    private func ids(_ s: [AccessorySelection]) -> [String] {
        return s.map { $0.partID }
    }

    func testCatalogMatchesSpec() {
        XCTAssertEqual(rules.parts.count, 27)
        XCTAssertEqual(rules.part("boots_brushing")?.slots, ["legs_front", "legs_hind"])
        XCTAssertEqual(rules.part("saddle_english")?.materialSlots,
                       ["slot_primary", "slot_secondary", "slot_accent", "slot_metal"])
        XCTAssertTrue(rules.accessoryPartIDs.contains("halter"))
        XCTAssertFalse(rules.accessoryPartIDs.contains("mane_natural"))
    }

    func testValidSelectionHasNoIssue() {
        let s = [sel("saddle_english"), sel("saddle_pad_english"), sel("bridle_snaffle"), sel("boots_bell"),
                 sel("bandages"), sel("breastplate"), sel("plume")]
        XCTAssertEqual(rules.validate(s, hair: .default), [])
    }

    func testConflictsSlotsAndRequirementsAreReported() {
        let s = [sel("bridle_snaffle"), sel("halter"), sel("saddle_pad_western"), sel("bandages"),
                 sel("boots_brushing"), sel("unknown_part"), sel("bridle_snaffle")]
        let issues = rules.validate(s, hair: .default)
        let flagged = Set(issues.map { $0.partID })
        XCTAssertTrue(flagged.contains("halter"))                 // filet ↔ licol
        XCTAssertTrue(flagged.contains("saddle_pad_western"))     // requiert saddle_western
        XCTAssertTrue(flagged.contains("boots_brushing"))         // guêtres ↔ bandes (mêmes emplacements)
        XCTAssertTrue(flagged.contains("unknown_part"))
        XCTAssertGreaterThanOrEqual(issues.filter { $0.partID == "bridle_snaffle" }.count, 1)   // doublon
    }

    func testAddingResolvesConflictsAndSlots() {
        var s: [AccessorySelection] = [sel("bridle_snaffle"), sel("saddle_english"), sel("saddle_pad_english"),
                                       sel("quarter_sheet"), sel("breastplate")]
        // Le licol remplace le filet (même emplacement + exclusion).
        s = rules.resolving(adding: sel("halter"), to: s)
        XCTAssertFalse(ids(s).contains("bridle_snaffle"))
        XCTAssertEqual(ids(s).last, "halter")
        // La couverture exclut les selles ; tapis, couvre-reins et bricole perdent leur prérequis (cascade).
        s = rules.resolving(adding: sel("rug_stable"), to: s)
        XCTAssertEqual(Set(ids(s)), ["halter", "rug_stable"])
        XCTAssertEqual(rules.validate(s, hair: .default), [])
    }

    func testAddingAddsMissingRequirement() {
        var s: [AccessorySelection] = [sel("fly_sheet")]
        s = rules.resolving(adding: sel("saddle_pad_western"), to: s)
        XCTAssertEqual(Set(ids(s)), ["saddle_western", "saddle_pad_western"])   // selle ajoutée, chemise retirée
        XCTAssertEqual(ids(s).last, "saddle_pad_western")
        XCTAssertEqual(rules.validate(s, hair: .default), [])
        // Remplacer la selle western par l'anglaise retire le tapis western devenu invalide.
        s = rules.resolving(adding: sel("saddle_english"), to: s)
        XCTAssertEqual(ids(s), ["saddle_english"])
    }

    func testOnePartPerSlotKeepsColorsOfNewSelection() {
        let red = AccessorySelection(partID: "flowers", slotColors: ["slot_primary": PonyColor(hex: "#CC2233")])
        var s: [AccessorySelection] = [sel("plume"), sel("halter")]
        s = rules.resolving(adding: red, to: s)
        XCTAssertFalse(ids(s).contains("plume"))                  // même emplacement head_deco
        XCTAssertEqual(s.first(where: { $0.partID == "flowers" }), red)
    }

    func testHairAwareRequirements() {
        var hair = HairStyle.default
        var s: [AccessorySelection] = []
        // Rubans : requièrent la crinière tressée → appliquée à la coiffure.
        s = rules.resolving(adding: sel("ribbons_mane"), to: s, hair: &hair)
        XCTAssertEqual(hair.mane, "mane_braided")
        XCTAssertEqual(ids(s), ["ribbons_mane"])
        XCTAssertEqual(rules.validate(s, hair: hair), [])
        // Sans tresses, la validation signale le prérequis.
        XCTAssertEqual(rules.validate(s, hair: .default).map { $0.partID }, ["ribbons_mane"])
        // Changer la coiffure retire les rubans.
        var config = PonyConfiguration.default
        config.accessories = s
        config.hair = hair
        config.setHair(HairStyle(mane: "mane_natural"), rules: rules)
        XCTAssertEqual(config.accessories, [])
        // Ajouter une pièce de crins via la configuration modifie la coiffure.
        config.add(sel("tail_braided"), rules: rules)
        XCTAssertEqual(config.hair.tail, "tail_braided")
        XCTAssertEqual(config.accessories, [])
    }

    func testHiddenParts() {
        let s = [sel("tail_bow"), sel("rug_stable")]
        XCTAssertEqual(rules.hiddenPartIDs(for: s), ["tail_bow"])
        XCTAssertFalse(rules.visiblePartIDs(for: s, hair: .default).contains("tail_bow"))
        XCTAssertTrue(rules.visiblePartIDs(for: s, hair: .default).contains("mane_natural"))
        XCTAssertEqual(rules.hiddenPartIDs(for: [sel("tail_bow")]), [])
    }

    func testRemovingCascades() {
        let s = [sel("saddle_english"), sel("saddle_pad_english"), sel("quarter_sheet"), sel("halter")]
        XCTAssertEqual(ids(rules.removing("saddle_english", from: s)), ["halter"])
    }

    func testManifestPartsWithSlotStringOrArray() throws {
        let json = """
        {"joints": [], "parts": [
          {"id": "a", "slot": "x", "requires": ["b", "c"]},
          {"id": "b", "slot": ["y", "z"]},
          {"id": "c", "slot": "y", "slots": ["y", "w"], "fixedMaterials": ["fixed_x"]}
        ]}
        """
        let m = try PonyRigManifest.decode(from: Data(json.utf8))
        let r = AccessoryRules(manifest: m)
        XCTAssertEqual(r.part("b")?.slots, ["y", "z"])
        XCTAssertEqual(r.part("c")?.slots, ["y", "w"])
        XCTAssertEqual(r.part("c")?.fixedMaterials, ["fixed_x"])
        XCTAssertTrue(r.conflicts("b", "c"))                      // emplacement y partagé
        XCTAssertEqual(r.validate([sel("a"), sel("c")]), [])      // « au moins un » des prérequis
        XCTAssertEqual(r.validate([sel("a")]).map { $0.partID }, ["a"])
    }
}
