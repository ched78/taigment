import Foundation

/// Image RGBA 8 bits par canal, rangées de HAUT en BAS (convention PNG / CGImage), pixels entrelacés RGBA.
/// Pour les albedos, les canaux RGB sont en sRGB ; pour les cartes « raw » du SPEC §4, ce sont des données.
public struct RGBA8Image: Sendable, Equatable {
    public let width: Int
    public let height: Int
    /// RGBA entrelacé, `count == width * height * 4`.
    public var pixels: [UInt8]

    public init(width: Int, height: Int, pixels: [UInt8]) {
        precondition(width >= 0 && height >= 0, "RGBA8Image : dimensions négatives")
        precondition(pixels.count == width * height * 4, "RGBA8Image : pixels.count != width * height * 4")
        self.width = width
        self.height = height
        self.pixels = pixels
    }

    public init(width: Int, height: Int, fill: (UInt8, UInt8, UInt8, UInt8)) {
        precondition(width >= 0 && height >= 0, "RGBA8Image : dimensions négatives")
        var p = [UInt8](repeating: 0, count: width * height * 4)
        var i = 0
        while i < p.count {
            p[i] = fill.0
            p[i + 1] = fill.1
            p[i + 2] = fill.2
            p[i + 3] = fill.3
            i += 4
        }
        self.init(width: width, height: height, pixels: p)
    }

    /// Pixel (x, y) ; y = 0 est la rangée du haut.
    public func pixel(x: Int, y: Int) -> SIMD4<UInt8> {
        let i = (y * width + x) * 4
        return SIMD4<UInt8>(pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3])
    }

    /// Modifie le pixel (x, y).
    public mutating func setPixel(x: Int, y: Int, _ value: SIMD4<UInt8>) {
        let i = (y * width + x) * 4
        pixels[i] = value.x
        pixels[i + 1] = value.y
        pixels[i + 2] = value.z
        pixels[i + 3] = value.w
    }
}
