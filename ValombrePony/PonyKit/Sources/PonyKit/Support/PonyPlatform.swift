import CoreGraphics
import Foundation
import PonyCore
import RealityKit
import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

// Pont de couleurs entre `PonyColor` (sRGB 0…1, PonyCore) et les types de la plateforme.
//
// API vérifiées (Tools/apple_doc.py) :
// - `UIColor(red:green:blue:alpha:)` (iOS 2) ; `NSColor(red:green:blue:alpha:)` (macOS 10.9 ; la doc précise que
//   les composantes « étendues » sont acceptées, comme UIColor, donc espace sRGB étendu) ;
// - `CGColor(srgbRed:green:blue:alpha:)` (iOS 13 / macOS 10.15), `CGColor.converted(to:intent:options:)`,
//   `CGColor.components` ; `Color(_:red:green:blue:opacity:)` avec `.sRGB` (iOS 13 / macOS 10.15).
// - `PhysicallyBasedMaterial.BaseColor.tint` est un `UIColor` sur iOS et un `NSColor` sur macOS.

#if os(macOS)
/// Couleur de la plateforme attendue par RealityKit (`NSColor` sur macOS, `UIColor` sur iOS).
public typealias PonyPlatformColor = NSColor
#else
/// Couleur de la plateforme attendue par RealityKit (`NSColor` sur macOS, `UIColor` sur iOS).
public typealias PonyPlatformColor = UIColor
#endif

extension PonyColor {
    /// Couleur de la plateforme (sRGB), pour `baseColor.tint` et les lumières.
    public var platformColor: PonyPlatformColor {
        #if os(macOS)
        return NSColor(red: CGFloat(r), green: CGFloat(g), blue: CGFloat(b), alpha: 1)
        #else
        return UIColor(red: CGFloat(r), green: CGFloat(g), blue: CGFloat(b), alpha: 1)
        #endif
    }

    /// Couleur SwiftUI (sRGB).
    public var swiftUIColor: Color {
        return Color(.sRGB, red: Double(r), green: Double(g), blue: Double(b), opacity: 1)
    }

    /// `CGColor` sRGB (sélecteurs de couleur).
    public var cgColor: CGColor {
        return CGColor(srgbRed: CGFloat(r), green: CGFloat(g), blue: CGFloat(b), alpha: 1)
    }

    /// Couleur depuis un `CGColor` quelconque, converti en sRGB (composantes bornées à 0…1).
    /// Conversion impossible : gris moyen (journalisé).
    public init(cgColor: CGColor) {
        if let space = CGColorSpace(name: CGColorSpace.sRGB),
           let converted = cgColor.converted(to: space, intent: .defaultIntent, options: nil),
           let c = converted.components, c.count >= 3 {
            self.init(r: PonyColor.unit(c[0]), g: PonyColor.unit(c[1]), b: PonyColor.unit(c[2]))
        } else if let c = cgColor.components, c.count == 2 {
            // Niveaux de gris + alpha.
            let v = PonyColor.unit(c[0])
            self.init(r: v, g: v, b: v)
        } else {
            PonyLog.warning("couleur non convertible en sRGB : gris moyen utilisé")
            self.init(r: 0.5, g: 0.5, b: 0.5)
        }
    }

    private static func unit(_ v: CGFloat) -> Float {
        let f = Float(v)
        if !f.isFinite { return 0 }
        return min(max(f, 0), 1)
    }

    /// Luminance relative approchée (sRGB non linéaire, coefficients Rec. 709) — pour choisir un contraste.
    public var approximateLuminance: Float {
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    }

    /// Couleur multipliée (assombrie si k < 1), bornée.
    public func scaled(_ k: Float) -> PonyColor {
        return PonyColor(r: min(max(r * k, 0), 1), g: min(max(g * k, 0), 1), b: min(max(b * k, 0), 1))
    }
}

extension simd_quatf {
    /// Conversion depuis un quaternion PonyCore (`[x, y, z, w]`).
    public init(_ q: Quat) {
        self.init(ix: q.x, iy: q.y, iz: q.z, r: q.w)
    }
}
