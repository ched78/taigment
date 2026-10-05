import Foundation
import PonyCore

/// Motifs de tissu (uni, rayures, carreaux, étoiles, cœurs) composés au runtime pour les slots tissu des pièces
/// (`parts[].fabricSlots`, SPEC §6). Fonctions pures (appelables hors du MainActor) → `RGBA8Image` sRGB opaque.
///
/// Choix [I]/[A] :
/// - La texture de motif REMPLACE la texture de détail en niveaux de gris du slot (trame du tissu) : RealityKit
///   ne permet pas de relire les pixels d'une `TextureResource` importée sans passer par Metal ; la trame reste
///   portée par la carte de normales de l'USDZ. Pour retrouver la trame, choisir « Uni ».
/// - Les répétitions sont cuites dans l'image (`repeats` motifs par côté) : `textureCoordinateTransform`
///   s'appliquerait aussi aux normales du matériau. L'échelle réelle dépend des UV des pièces (inconnues ici) :
///   `repeats` est à caler à l'œil [A].
/// - Bords anti-crénelés par une rampe d'un texel sur une fonction de distance signée approchée.
public enum PonyFabricPatterns {
    /// Taille par défaut de la texture de motif (carrée).
    public static let defaultSize = 512
    /// Nombre de motifs par côté de l'espace UV [A].
    public static let defaultRepeats = 8

    /// Couleur de motif par défaut : contraste clair/foncé selon la luminance du fond [A].
    public static func contrastingColor(for base: PonyColor) -> PonyColor {
        return base.approximateLuminance > 0.5 ? PonyColor(r: 0.12, g: 0.12, b: 0.16)
                                               : PonyColor(r: 0.95, g: 0.94, b: 0.90)
    }

    /// Compose une texture de motif. `.plain` renvoie un aplat de `base`.
    public static func make(_ pattern: FabricPattern, base: PonyColor, motif: PonyColor,
                            size: Int = defaultSize, repeats: Int = defaultRepeats) -> RGBA8Image {
        let n = max(size, 8)
        let reps = Float(max(repeats, 1))
        var out = [UInt8](repeating: 255, count: n * n * 4)
        let b = (to8(base.r), to8(base.g), to8(base.b))
        let m = (to8(motif.r), to8(motif.g), to8(motif.b))
        // Largeur d'un texel en unités de cellule (pour l'anti-crénelage).
        let px = reps / Float(n)
        for y in 0..<n {
            for x in 0..<n {
                // Coordonnées dans la cellule : [0, 1)².
                let u = (Float(x) + 0.5) / Float(n) * reps
                let v = (Float(y) + 0.5) / Float(n) * reps
                let cu = u - u.rounded(.down)
                let cv = v - v.rounded(.down)
                let cellX = Int(u.rounded(.down))
                let cellY = Int(v.rounded(.down))
                let t = coverage(pattern, cu, cv, cellX, cellY, px)
                let o = (y * n + x) * 4
                out[o] = mix(b.0, m.0, t)
                out[o + 1] = mix(b.1, m.1, t)
                out[o + 2] = mix(b.2, m.2, t)
                out[o + 3] = 255
            }
        }
        return RGBA8Image(width: n, height: n, pixels: out)
    }

    /// Part du motif (0 fond … 1 motif) au point (cu, cv) d'une cellule.
    static func coverage(_ pattern: FabricPattern, _ cu: Float, _ cv: Float, _ cellX: Int, _ cellY: Int,
                         _ px: Float) -> Float {
        switch pattern {
        case .plain:
            return 0
        case .stripes:
            // Bande centrale couvrant 40 % de la cellule (rayures horizontales).
            let d = abs(cv - 0.5) - 0.2
            return ramp(-d, px)
        case .checks:
            // Écossais simple : deux jeux de bandes orthogonales, croisements plus denses.
            let h = ramp(-(abs(cv - 0.5) - 0.18), px)
            let w = ramp(-(abs(cu - 0.5) - 0.18), px)
            return min(1, 0.55 * h + 0.55 * w)
        case .stars:
            // Étoile à 5 branches, une cellule sur deux décalée (quinconce).
            let shift: Float = (cellY & 1) == 1 ? 0.5 : 0
            var x = cu + shift
            x -= x.rounded(.down)
            return ramp(-starDistance(x - 0.5, cv - 0.5, radius: 0.32), px)
        case .hearts:
            let shift: Float = (cellY & 1) == 1 ? 0.5 : 0
            var x = cu + shift
            x -= x.rounded(.down)
            return ramp(-heartDistance(x - 0.5, cv - 0.5, size: 0.30), px)
        }
    }

    /// Rampe d'anti-crénelage : 0 hors du motif, 1 dedans, transition sur un texel.
    @inline(__always)
    static func ramp(_ signedInside: Float, _ px: Float) -> Float {
        let w = max(px, 1e-4)
        return min(max(signedInside / w + 0.5, 0), 1)
    }

    /// Distance signée approchée à une étoile à 5 branches (positive dehors). Image : y vers le bas,
    /// pointe vers le haut.
    static func starDistance(_ x: Float, _ y: Float, radius: Float) -> Float {
        let r = (x * x + y * y).squareRoot()
        // Angle mesuré depuis le haut (−y), sens horaire.
        let a = atan2(x, -y)
        let sector = 2 * Float.pi / 5
        var k = a / sector
        k -= k.rounded(.down)            // 0…1 dans un secteur
        let f = abs(k - 0.5) * 2         // 1 sur une branche, 0 au creux
        let inner: Float = 0.45
        let edge = radius * (inner + (1 - inner) * f * f)
        return r - edge
    }

    /// Distance signée à un cœur (positive dehors), pointe vers le bas de l'image. Fonction de distance du cœur
    /// d'Inigo Quilez (pointe à l'origine, lobes jusqu'à y ≈ 1,1, repère y vers le haut), mise à l'échelle.
    /// Rendu vérifié par un portage numpy (aperçu dans le rapport de l'agent « kit »).
    static func heartDistance(_ x: Float, _ y: Float, size: Float) -> Float {
        let s = size * 1.8
        let px = abs(x / s)
        let py = -y / s + 0.55
        if px + py > 1 {
            let dx = px - 0.25
            let dy = py - 0.75
            return ((dx * dx + dy * dy).squareRoot() - Float(2).squareRoot() / 4) * s
        }
        let m = max(px + py, 0) * 0.5
        let d1 = px * px + (py - 1) * (py - 1)
        let d2 = (px - m) * (px - m) + (py - m) * (py - m)
        let sign: Float = px - py >= 0 ? 1 : -1
        return min(d1, d2).squareRoot() * sign * s
    }

    @inline(__always)
    static func to8(_ v: Float) -> Float {
        return min(max(v, 0), 1) * 255
    }

    @inline(__always)
    static func mix(_ a: Float, _ b: Float, _ t: Float) -> UInt8 {
        let v = a + (b - a) * t
        return UInt8(min(max(v.rounded(), 0), 255))
    }
}
