import Foundation
import XCTest
@testable import PonyCore

/// Règles génétiques -> phénotype, présets, Codable.
/// NB : non exécutés dans l'environnement de génération (pas de compilateur Swift) — à lancer dans Xcode.
final class CoatGeneticsTests: XCTestCase {
    func make(_ edit: (inout CoatConfiguration) -> Void) -> CoatPhenotype {
        CoatConfiguration.make(edit).phenotype
    }

    func luminance(_ c: PonyColor) -> Float {
        0.2126 * c.r + 0.7152 * c.g + 0.0722 * c.b
    }

    func testPresetsList() {
        let all = CoatPreset.all
        XCTAssertGreaterThanOrEqual(all.count, 18)
        XCTAssertEqual(Set(all.map(\.id)).count, all.count)
        for p in all {
            XCTAssertFalse(p.name.isEmpty)
            XCTAssertFalse(p.summary.isEmpty)
        }
        XCTAssertEqual(CoatPreset.named("bai")?.configuration, CoatConfiguration.default)
        XCTAssertEqual(CoatPreset.defaultPreset.id, "bai")
        for id in ["alezan", "alezan_crins_laves", "alezan_brule", "bai", "bai_brun", "noir", "palomino", "isabelle",
                   "souris", "creme", "gris_pommele", "gris_truite", "rouan", "aubere", "pie_tobiano", "pie_overo",
                   "appaloosa_leopard", "appaloosa_couverture", "pangare", "champagne_dore", "silver_noir",
                   "bai_dun"] {
            XCTAssertNotNil(CoatPreset.named(id), id)
        }
    }

    func testDefaultIsBayWithStar() {
        let d = CoatConfiguration.default
        XCTAssertEqual(d.genotype.baseCoat, .bay)
        XCTAssertEqual(d.face.kind, .star)
        XCTAssertEqual(d.phenotype.bodyColor.hexString, "#8B4A22")
    }

    func testBaseCoats() {
        XCTAssertEqual(CoatGenotype(extensionLocus: .redOnly, agouti: .black).baseCoat, .chestnut)
        XCTAssertEqual(CoatGenotype(agouti: .sealBrown).baseCoat, .sealBrown)
        XCTAssertEqual(CoatGenotype(agouti: .black).baseCoat, .black)
    }

    func testManeColors() {
        let bay = make { _ in }
        let chestnut = make { $0.genotype.extensionLocus = .redOnly }
        XCTAssertLessThan(luminance(bay.maneColor), 0.12)                  // crins noirs du bai
        XCTAssertGreaterThan(luminance(chestnut.maneColor), 0.2)           // crins de l'alezan
        let flaxen = make { $0.genotype.extensionLocus = .redOnly; $0.expression.flaxen = 1 }
        XCTAssertGreaterThan(luminance(flaxen.maneColor), luminance(chestnut.maneColor) + 0.2)
        let bayFlaxen = make { $0.expression.flaxen = 1 }
        XCTAssertEqual(bayFlaxen.maneColor, bay.maneColor)                 // sans effet sur un bai [NV]
    }

    func testSilverOnlyOnBlackPigment() {
        let chestnut = make { $0.genotype.extensionLocus = .redOnly }
        let silverChestnut = make { $0.genotype.extensionLocus = .redOnly; $0.genotype.silver = .heterozygous }
        XCTAssertEqual(chestnut.bodyColor, silverChestnut.bodyColor)
        XCTAssertEqual(chestnut.maneColor, silverChestnut.maneColor)
        let black = make { $0.genotype.agouti = .black }
        let silverBlack = make { $0.genotype.agouti = .black; $0.genotype.silver = .heterozygous }
        XCTAssertNotEqual(black.bodyColor, silverBlack.bodyColor)
        XCTAssertGreaterThan(luminance(silverBlack.maneColor), 0.5)
    }

    func testCreamDilutions() {
        let black = make { $0.genotype.agouti = .black }
        let smoky = make { $0.genotype.agouti = .black; $0.genotype.creamPearl = .cream }
        XCTAssertLessThan(abs(black.bodyColor.r - smoky.bodyColor.r), 0.08)
        let palomino = make { $0.genotype.extensionLocus = .redOnly; $0.genotype.creamPearl = .cream }
        XCTAssertGreaterThan(luminance(palomino.bodyColor), 0.4)
        let cremello = make { $0.genotype.extensionLocus = .redOnly; $0.genotype.creamPearl = .doubleCream }
        XCTAssertEqual(cremello.eye, .blue)
        XCTAssertTrue(cremello.pinkSkin)
        XCTAssertEqual(cremello.hooves, [.light, .light, .light, .light])
        let buckskin = make { $0.genotype.creamPearl = .cream }
        XCTAssertLessThan(luminance(buckskin.pointsColor), 0.12)          // isabelle : extrémités noires
    }

    func testDunDilutesBodyNotPoints() {
        let bay = make { _ in }
        let dun = make { $0.genotype.dun = .heterozygous }
        XCTAssertGreaterThan(luminance(dun.bodyColor), luminance(bay.bodyColor))
        XCTAssertEqual(dun.pointsColor, bay.pointsColor)
        XCTAssertGreaterThan(CoatPalette(CoatConfiguration.make { $0.genotype.dun = .heterozygous }).primitive, 0)
        XCTAssertEqual(CoatPalette(.plain).primitive, 0)
    }

    func testEyes() {
        XCTAssertEqual(make { _ in }.eye, .brown)
        XCTAssertEqual(make { $0.genotype.champagne = .heterozygous }.eye, .amber)
        XCTAssertEqual(make { $0.genotype.splashedWhite = .heterozygous }.eye, .blue)
        XCTAssertEqual(make { $0.face.kind = .baldFace; $0.face.size = 1.4 }.eye, .blue)
        XCTAssertEqual(make { $0.genotype.creamPearl = .creamPearl }.eye, .light)
        XCTAssertEqual(make { $0.irisStyle = .vairon }.eye, .vairon)
        XCTAssertEqual(make { $0.overrides.eyes = PonyColor(hex: "#30A060") }.eyeColor.hexString, "#30A060")
        XCTAssertTrue(make { $0.genotype.leopardComplex = .heterozygous }.whiteSclera)
    }

    func testHooves() {
        let p = make {
            $0.legs.frontLeft.height = 0.3
            $0.legs.hindLeft = LegMarking(height: 0.2, ermine: true)
            $0.legs.hindRight.height = 0.02
        }
        XCTAssertEqual(p.hooves, [.light, .dark, .striped, .striped])
        XCTAssertEqual(make { $0.genotype.leopardComplex = .heterozygous }.hooves, [.striped, .striped, .striped, .striped])
        let custom = make { $0.overrides.hooves = PonyColor(hex: "#405060") }
        XCTAssertEqual(custom.hooves, [.custom, .custom, .custom, .custom])
        XCTAssertEqual(custom.hoofColors[0].hexString, "#405060")
    }

    func testLegCategories() {
        XCTAssertEqual(LegMarking(height: 0).category, .none)
        XCTAssertEqual(LegMarking(height: 0.02).category, .coronet)
        XCTAssertEqual(LegMarking(height: 0.08).category, .pastern)
        XCTAssertEqual(LegMarking(height: 0.2).category, .sock)
        XCTAssertEqual(LegMarking(height: 0.45).category, .stocking)
        XCTAssertEqual(LegMarking(height: 0.8).category, .highWhite)
        XCTAssertEqual(LegMarkingCategory.stocking.frenchName, "Grande balzane")
    }

    func testLeopardPattern() {
        XCTAssertNil(CoatGenotype().leopardPattern)
        XCTAssertEqual(CoatGenotype(leopardComplex: .heterozygous).leopardPattern, .blanket)
        XCTAssertEqual(CoatGenotype(leopardComplex: .heterozygous, patternOne: .heterozygous).leopardPattern, .leopard)
        XCTAssertEqual(CoatGenotype(leopardComplex: .homozygous, patternOne: .heterozygous).leopardPattern, .fewSpot)
    }

    func testOverrides() {
        let p = make {
            $0.overrides.body = PonyColor(hex: "#6A8FB0")
            $0.overrides.mane = PonyColor(hex: "#E05080")
        }
        XCTAssertEqual(p.bodyColor.hexString, "#6A8FB0")
        XCTAssertEqual(p.maneColor.hexString, "#E05080")
        XCTAssertTrue(CoatOverrides().isEmpty)
    }

    func testLegMarkingsSubscript() {
        var legs = LegMarkings()
        legs[2] = LegMarking(height: 0.4)
        XCTAssertEqual(legs.hindLeft.height, 0.4)
        XCTAssertEqual(legs.all.map(\.height), [0, 0, 0.4, 0])
    }

    func testConfigurationCodableRoundTrip() throws {
        for preset in CoatPreset.all {
            let data = try JSONEncoder().encode(preset.configuration)
            let back = try JSONDecoder().decode(CoatConfiguration.self, from: data)
            XCTAssertEqual(back, preset.configuration, preset.id)
        }
        var c = CoatConfiguration.default
        c.overrides.skin = PonyColor(r: 0.4, g: 0.2, b: 0.3)
        c.hair.secondaryColor = PonyColor(hex: "#20C0F0")
        let back = try JSONDecoder().decode(CoatConfiguration.self, from: try JSONEncoder().encode(c))
        XCTAssertEqual(back, c)
    }

    func testRawValuesMatchPythonReference() {
        // Valeurs JSON partagées avec coat_reference.py (ENUMS).
        XCTAssertEqual(ExtensionGenotype.redOnly.rawValue, "ee")
        XCTAssertEqual(AgoutiGenotype.sealBrown.rawValue, "At")
        XCTAssertEqual(CreamPearlGenotype.creamPearl.rawValue, "Cr/prl")
        XCTAssertEqual(Zygosity.heterozygous.rawValue, "X/n")
        XCTAssertEqual(FaceMarkingKind.absent.rawValue, "none")
        XCTAssertEqual(FaceMarkingKind.baldFace.rawValue, "baldFace")
    }
}
