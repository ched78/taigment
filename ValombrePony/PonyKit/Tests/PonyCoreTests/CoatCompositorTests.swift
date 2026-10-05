import Foundation
import XCTest
@testable import PonyCore

/// Compositeur : déterminisme, résolutions, marques, crins, iris (cartes synthétiques).
/// NB : non exécutés dans l'environnement de génération (pas de compilateur Swift) — à lancer dans Xcode.
final class CoatCompositorTests: XCTestCase {
    static let maps = CoatMaps.synthetic(size: 64)

    /// Identifiant de région (plus proche voisin) de chaque texel de sortie.
    func regionIDs(_ size: Int) -> [Int] {
        let t = CoatAxisTable(mapSize: 64, outSize: size)
        var ids = [Int](repeating: 0, count: size * size)
        for y in 0..<size {
            for x in 0..<size {
                let p = Self.maps.regions.pixel(x: Int(t.nearest[x]), y: Int(t.nearest[y]))
                ids[y * size + x] = (Int(p.x) + 8) / 16
            }
        }
        return ids
    }

    func luminance(_ img: RGBA8Image, _ i: Int) -> Float {
        (0.2126 * Float(img.pixels[i * 4]) + 0.7152 * Float(img.pixels[i * 4 + 1])
            + 0.0722 * Float(img.pixels[i * 4 + 2])) / 255
    }

    func testDeterministicAndSeeded() {
        var cfg = CoatConfiguration.default
        cfg.genotype.roan = .heterozygous
        let a = CoatCompositor.composeBody(cfg, maps: Self.maps, resolution: 96)
        let b = CoatCompositor.composeBody(cfg, maps: Self.maps, resolution: 96)
        XCTAssertEqual(a, b)
        cfg.seed = 2
        let c = CoatCompositor.composeBody(cfg, maps: Self.maps, resolution: 96)
        XCTAssertNotEqual(a, c)
        XCTAssertEqual(a.width, 96)
        XCTAssertEqual(a.height, 96)
        for i in stride(from: 3, to: a.pixels.count, by: 4) {
            XCTAssertEqual(a.pixels[i], 255)
        }
    }

    func testResolutionParameter() {
        let small = CoatCompositor.composeBody(.default, maps: Self.maps, resolution: 32)
        let big = CoatCompositor.composeBody(.default, maps: Self.maps, resolution: 128)
        XCTAssertEqual(small.pixels.count, 32 * 32 * 4)
        XCTAssertEqual(big.pixels.count, 128 * 128 * 4)
        XCTAssertEqual(CoatCompositor.previewResolution, 1024)
        XCTAssertEqual(CoatCompositor.finalResolution, 2048)
    }

    func testMixedMapResolutions() {
        var maps = Self.maps
        maps.shading = CoatMaps.synthetic(size: 128).shading
        maps.patterns = CoatMaps.synthetic(size: 32).patterns
        let mixed = CoatCompositor.composeBody(.default, maps: maps, resolution: 80)
        let same = CoatCompositor.composeBody(.default, maps: Self.maps, resolution: 80)
        var diff = 0
        for i in 0..<mixed.pixels.count { diff += abs(Int(mixed.pixels[i]) - Int(same.pixels[i])) }
        XCTAssertLessThan(Double(diff) / Double(mixed.pixels.count), 6.0)
    }

    func testCoverageExtremes() {
        let ids = regionIDs(96)
        let plain = CoatCompositor.composeBody(.plain, maps: Self.maps, resolution: 96)
        let none = CoatCompositor.composeBody(CoatConfiguration.make {
            $0.genotype.tobiano = .heterozygous
            $0.expression.tobianoCoverage = 0
        }, maps: Self.maps, resolution: 96)
        XCTAssertEqual(none, plain)
        let full = CoatCompositor.composeBody(CoatConfiguration.make {
            $0.genotype.dominantWhite = .heterozygous
            $0.expression.dominantWhiteCoverage = 1
        }, maps: Self.maps, resolution: 96)
        for i in 0..<ids.count where ids[i] == 0 {
            XCTAssertGreaterThan(luminance(full, i), 0.6)
        }
    }

    func testLegMarkingWhitensLegAndHoof() {
        let ids = regionIDs(96)
        let plain = CoatCompositor.composeBody(.plain, maps: Self.maps, resolution: 96)
        let marked = CoatCompositor.composeBody(CoatConfiguration.make { $0.legs.frontLeft.height = 0.3 },
                                                maps: Self.maps, resolution: 96)
        var hoofPlain: Float = 0, hoofMarked: Float = 0, n: Float = 0
        var legChanged = false
        for i in 0..<ids.count {
            let changed = (0..<4).contains { plain.pixels[i * 4 + $0] != marked.pixels[i * 4 + $0] }
            switch ids[i] {
            case 9:
                hoofPlain += luminance(plain, i)
                hoofMarked += luminance(marked, i)
                n += 1
            case 5:
                legChanged = legChanged || changed
            case 0, 6:
                XCTAssertFalse(changed, "région \(ids[i]) modifiée")
            default:
                break
            }
        }
        XCTAssertTrue(legChanged)
        XCTAssertGreaterThan(n, 0)
        XCTAssertGreaterThan(hoofMarked / n, hoofPlain / n + 0.3)
    }

    func testFaceMarkingOnlyOnHead() {
        let ids = regionIDs(96)
        let plain = CoatCompositor.composeBody(.plain, maps: Self.maps, resolution: 96)
        let blaze = CoatCompositor.composeBody(CoatConfiguration.make {
            $0.face.kind = .blaze
            $0.face.snip = true
        }, maps: Self.maps, resolution: 96)
        var headChanged = false
        for i in 0..<ids.count {
            let changed = (0..<4).contains { plain.pixels[i * 4 + $0] != blaze.pixels[i * 4 + $0] }
            if ids[i] == 1 || ids[i] == 2 {
                headChanged = headChanged || changed
            } else if ids[i] != 14 {
                XCTAssertFalse(changed)
            }
        }
        XCTAssertTrue(headChanged)
    }

    func testAllPresetsCompose() {
        for p in CoatPreset.all {
            let img = CoatCompositor.composeBody(p.configuration, maps: Self.maps, resolution: 48)
            XCTAssertEqual(img.pixels.count, 48 * 48 * 4, p.id)
        }
    }

    func testHairAlphaPreservedAndGreying() {
        let strands = CoatMaps.syntheticStrands(width: 32, height: 64)
        for p in CoatPreset.all.prefix(6) {
            let h = CoatCompositor.composeHair(p.configuration, strands: strands)
            for i in stride(from: 3, to: h.pixels.count, by: 4) {
                XCTAssertEqual(h.pixels[i], strands.pixels[i])
            }
        }
        let bay = CoatCompositor.composeHair(.default, strands: strands)
        let grey = CoatCompositor.composeHair(CoatConfiguration.make {
            $0.genotype.grey = .heterozygous
            $0.expression.greyStage = 0.9
        }, strands: strands)
        var lb: Float = 0, lg: Float = 0
        for i in 0..<(32 * 64) {
            lb += luminance(bay, i)
            lg += luminance(grey, i)
        }
        XCTAssertGreaterThan(lg / 2048, lb / 2048 + 0.2)
        XCTAssertNotNil(CoatCompositor.composeHair(.default, maps: Self.maps))
    }

    func testIris() {
        let iris = CoatCompositor.composeIris(.default, resolution: 64)
        XCTAssertEqual(iris.width, 64)
        let center = iris.pixel(x: 32, y: 32)
        XCTAssertLessThan(max(center.x, center.y, center.z), 30)          // pupille
        let corner = iris.pixel(x: 1, y: 1)
        XCTAssertLessThan(max(corner.x, corner.y, corner.z), 120)         // sclère pigmentée
        let lp = CoatCompositor.composeIris(CoatConfiguration.make { $0.genotype.leopardComplex = .heterozygous },
                                            resolution: 64)
        XCTAssertGreaterThan(min(lp.pixel(x: 1, y: 1).x, lp.pixel(x: 1, y: 1).y), 180)   // sclère blanche
        let blue = CoatCompositor.composeIris(CoatConfiguration.make {
            $0.genotype.extensionLocus = .redOnly
            $0.genotype.creamPearl = .doubleCream
        }, resolution: 64)
        let p = blue.pixel(x: 50, y: 32)
        XCTAssertGreaterThan(p.z, p.x)
    }
}
