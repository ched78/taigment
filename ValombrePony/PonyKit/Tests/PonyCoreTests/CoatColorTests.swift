import Foundation
import XCTest
@testable import PonyCore

/// Couleurs, hex, conversions sRGB/linéaire, images RGBA8, hachage.
/// NB : non exécutés dans l'environnement de génération (pas de compilateur Swift) — à lancer dans Xcode.
final class CoatColorTests: XCTestCase {
    func testHexRoundTrip() {
        for h in ["#000000", "#FFFFFF", "#8B4A22", "#17120F", "#F3F0EA"] {
            XCTAssertEqual(PonyColor(hex: h).hexString, h)
        }
        XCTAssertEqual(PonyColor(hex: "8b4a22").hexString, "#8B4A22")
        XCTAssertEqual(PonyColor(hex: "  #8B4A22 ").hexString, "#8B4A22")
    }

    func testInvalidHexIsBlack() {
        XCTAssertEqual(PonyColor(hex: "#12345"), PonyColor.black)
        XCTAssertEqual(PonyColor(hex: "#GG0000"), PonyColor.black)
        XCTAssertEqual(PonyColor(hex: ""), PonyColor.black)
    }

    func testHexComponents() {
        let c = PonyColor(hex: "#FF8000")
        XCTAssertEqual(c.r, 1)
        XCTAssertEqual(c.g, 128.0 / 255.0, accuracy: 1e-6)
        XCTAssertEqual(c.b, 0)
    }

    func testLinearConversion() {
        XCTAssertEqual(PonyColor(r: 0.5, g: 0, b: 1).linear.x, 0.21404, accuracy: 1e-4)
        XCTAssertEqual(PonyColor(r: 0.5, g: 0, b: 1).linear.y, 0)
        XCTAssertEqual(PonyColor(r: 0.5, g: 0, b: 1).linear.z, 1, accuracy: 1e-6)
        XCTAssertEqual(PonyColor(r: 0.02, g: 0, b: 0).linear.x, 0.02 / 12.92, accuracy: 1e-7)
        let c = PonyColor(hex: "#8B4A22")
        let back = PonyColor(linear: c.linear)
        XCTAssertEqual(back.hexString, "#8B4A22")
    }

    func testMix() {
        let m = PonyColor.mix(.black, .white, 0.25)
        XCTAssertEqual(m.r, 0.25, accuracy: 1e-6)
        XCTAssertEqual(PonyColor.mix(.black, .white, 0), .black)
    }

    func testCodableRoundTrip() throws {
        let c = PonyColor(r: 0.1, g: 0.2, b: 0.3)
        let data = try JSONEncoder().encode(c)
        XCTAssertEqual(try JSONDecoder().decode(PonyColor.self, from: data), c)
    }

    func testEncodeLUT() {
        let lut = CoatCompositor.encodeLUT
        XCTAssertEqual(lut.count, 4096)
        XCTAssertEqual(lut[0], 0)
        XCTAssertEqual(lut[4095], 255)
        for i in 1..<lut.count {
            XCTAssertGreaterThanOrEqual(lut[i], lut[i - 1])
        }
        XCTAssertEqual(lut[CoatCompositor.encodeIndex(0.5)], 188)
    }

    func testImageFillAndPixel() {
        var img = RGBA8Image(width: 3, height: 2, fill: (10, 20, 30, 40))
        XCTAssertEqual(img.pixels.count, 24)
        XCTAssertEqual(img.pixel(x: 2, y: 1), SIMD4<UInt8>(10, 20, 30, 40))
        img.setPixel(x: 1, y: 0, SIMD4<UInt8>(1, 2, 3, 4))
        XCTAssertEqual(img.pixel(x: 1, y: 0), SIMD4<UInt8>(1, 2, 3, 4))
        XCTAssertEqual(Array(img.pixels[4..<8]), [1, 2, 3, 4])
    }

    func testHashMatchesReference() {
        // lowbias32(0) = 0 ; mêmes valeurs que hash32_int en Python (vérifiées par les vecteurs de référence).
        XCTAssertEqual(CoatNoise.hash32(0), 0)
        XCTAssertNotEqual(CoatNoise.hash32(1), CoatNoise.hash32(2))
        var sum: Float = 0
        for i in 0..<4000 {
            let h = CoatNoise.hash01(UInt32(i), UInt32(i * 7), CoatNoise.salted(1, 5))
            XCTAssertGreaterThanOrEqual(h, 0)
            XCTAssertLessThan(h, 1)
            sum += h
        }
        XCTAssertEqual(sum / 4000, 0.5, accuracy: 0.03)
    }

    func testValueNoisePeriodic() {
        let a = CoatNoise.valueNoise(0.25, 2, 99, periodX: 6)
        let b = CoatNoise.valueNoise(6.25, 2, 99, periodX: 6)
        XCTAssertEqual(a, b)
        var prev = CoatNoise.valueNoise(0, 3.3, 1234)
        var x: Float = 0
        while x < 20 {
            x += 0.005
            let v = CoatNoise.valueNoise(x, 3.3, 1234)
            XCTAssertLessThan(abs(v - prev), 0.02)
            prev = v
        }
    }
}
