import Foundation

/// Couleur sRGB (non linéaire, composantes 0…1) : la couleur « telle qu'on la choisit » dans l'interface.
///
/// - `linear` convertit en linéaire (PBR, mélanges physiquement corrects).
/// - `init(hex:)` / `hexString` : « #RRGGBB » ; une chaîne invalide donne du noir.
/// - Codable synthétisé (`{"r":…,"g":…,"b":…}`, sans perte) : c'est aussi la forme JSON lue par
///   l'implémentation de référence Python (`Pipeline/pony/coat_reference.py`, `color_srgb`).
public struct PonyColor: Codable, Equatable, Hashable, Sendable {
    public var r: Float
    public var g: Float
    public var b: Float

    public init(r: Float, g: Float, b: Float) {
        self.r = r
        self.g = g
        self.b = b
    }

    /// « #RRGGBB » ou « RRGGBB » (espaces ignorés). Invalide -> noir.
    public init(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("#") {
            s.removeFirst()
        }
        guard s.count == 6, let v = UInt32(s, radix: 16) else {
            self.init(r: 0, g: 0, b: 0)
            return
        }
        self.init(r: Float((v >> 16) & 255) / 255,
                  g: Float((v >> 8) & 255) / 255,
                  b: Float(v & 255) / 255)
    }

    /// Couleur à partir de composantes LINÉAIRES (conversion inverse de `linear`).
    public init(linear: SIMD3<Float>) {
        self.init(r: Float(PonyColor.linearToSRGB(Double(linear.x))),
                  g: Float(PonyColor.linearToSRGB(Double(linear.y))),
                  b: Float(PonyColor.linearToSRGB(Double(linear.z))))
    }

    /// « #RRGGBB » en majuscules ; arrondi floor(x·255 + 0,5) après saturation dans 0…1.
    public var hexString: String {
        let digits: [Character] = Array("0123456789ABCDEF")
        var out = "#"
        for v in [r, g, b] {
            let x = min(max(v, 0), 1)
            let byte = Int((x * 255 + 0.5).rounded(.down))
            out.append(digits[byte >> 4])
            out.append(digits[byte & 15])
        }
        return out
    }

    /// Composantes linéaires (fonction de transfert sRGB standard, calcul en Double).
    public var linear: SIMD3<Float> {
        SIMD3<Float>(Float(PonyColor.srgbToLinear(Double(r))),
                     Float(PonyColor.srgbToLinear(Double(g))),
                     Float(PonyColor.srgbToLinear(Double(b))))
    }

    /// Interpolation composante par composante en sRGB : a + (b − a)·t.
    public static func mix(_ a: PonyColor, _ b: PonyColor, _ t: Float) -> PonyColor {
        PonyColor(r: a.r + (b.r - a.r) * t, g: a.g + (b.g - a.g) * t, b: a.b + (b.b - a.b) * t)
    }

    public static let black = PonyColor(r: 0, g: 0, b: 0)
    public static let white = PonyColor(r: 1, g: 1, b: 1)

    // MARK: - Fonctions de transfert (Double ; identiques à coat_reference.py)

    static func srgbToLinear(_ c: Double) -> Double {
        c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }

    static func linearToSRGB(_ c: Double) -> Double {
        let x = min(max(c, 0), 1)
        return x <= 0.0031308 ? 12.92 * x : 1.055 * pow(x, 1.0 / 2.4) - 0.055
    }
}
