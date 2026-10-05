import CoreGraphics
import Foundation
import ImageIO
import PonyCore

/// Décodage des cartes PNG en `RGBA8Image` (tampons de `PonyCore/Coat`) et fabrication de `CGImage` pour
/// les textures. Fonctions pures, appelables hors du MainActor (`Task.detached`).
///
/// Les cartes du SPEC §4 sont des DONNÉES (« raw ») : aucune conversion de couleur ni prémultiplication ne doit
/// les altérer. On lit donc directement les octets décodés par ImageIO (`CGImage.dataProvider.data`) en
/// interprétant la disposition des pixels (8/16 bits, alpha devant/derrière, ordre des octets). Hypothèse [I] :
/// ImageIO fournit des échantillons non convertis (pas de gestion de couleur à la lecture du fournisseur de
/// données) ; les PNG du pipeline n'ont pas de profil ICC ni de bloc gAMA (vérifié avec Pillow sur l'export
/// de test). Un format inattendu passe par un dessin CoreGraphics (repli approché, journalisé).
public enum PonyImageIO {

    // MARK: Lecture

    /// Lit un PNG (ou tout format ImageIO) en RGBA 8 bits, rangées de haut en bas, valeurs brutes.
    public static func loadRGBA8(contentsOf url: URL, name: String) throws -> RGBA8Image {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
            throw PonyAssetError.invalidImage(name, reason: "ImageIO ne reconnaît pas le fichier")
        }
        guard let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
            throw PonyAssetError.invalidImage(name, reason: "décodage ImageIO impossible")
        }
        return try rgba8(from: image, name: name)
    }

    /// Lit une image pour un usage « couleur » (environnement) : `CGImage` tel que décodé par ImageIO.
    public static func loadCGImage(contentsOf url: URL) -> CGImage? {
        guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
        return CGImageSourceCreateImageAtIndex(source, 0, nil)
    }

    /// Convertit un `CGImage` en `RGBA8Image` en conservant les valeurs brutes des canaux.
    public static func rgba8(from image: CGImage, name: String = "image") throws -> RGBA8Image {
        if let raw = rawRGBA8(image, name: name) {
            return raw
        }
        PonyLog.warning("« \(name) » : disposition de pixels inattendue (\(image.bitsPerComponent) bits/composante, "
            + "\(image.bitsPerPixel) bits/pixel, alpha \(image.alphaInfo.rawValue)) — conversion par dessin "
            + "CoreGraphics, valeurs approchées [I]")
        if let drawn = drawnRGBA8(image) {
            return drawn
        }
        throw PonyAssetError.invalidImage(name, reason: "format de pixels non pris en charge")
    }

    /// Lecture directe des octets décodés. `nil` si la disposition n'est pas reconnue.
    static func rawRGBA8(_ image: CGImage, name: String) -> RGBA8Image? {
        let w = image.width
        let h = image.height
        guard w > 0, h > 0 else { return nil }
        let bpc = image.bitsPerComponent
        let bpp = image.bitsPerPixel
        guard bpc == 8 || bpc == 16, bpp % bpc == 0 else { return nil }
        if image.bitmapInfo.contains(.floatComponents) { return nil }
        let colorChannels: Int
        switch image.colorSpace?.model ?? .rgb {
        case .rgb: colorChannels = 3
        case .monochrome: colorChannels = 1
        default: return nil
        }
        var hasAlpha = false
        var alphaFirst = false
        var skip = false
        var premultiplied = false
        switch image.alphaInfo {
        case .none: break
        case .noneSkipLast: skip = true
        case .noneSkipFirst: skip = true; alphaFirst = true
        case .last: hasAlpha = true
        case .first: hasAlpha = true; alphaFirst = true
        case .premultipliedLast: hasAlpha = true; premultiplied = true
        case .premultipliedFirst: hasAlpha = true; alphaFirst = true; premultiplied = true
        case .alphaOnly: return nil
        @unknown default: return nil
        }
        let comps = bpp / bpc
        let extra = (hasAlpha || skip) ? 1 : 0
        guard comps == colorChannels + extra else { return nil }
        // Ordre des octets : en 8 bits, `order32Little` inverse les 4 composantes (BGRA…) ; en 16 bits,
        // `order16Little` = composantes petit-boutistes, défaut = gros-boutiste (convention CoreGraphics).
        var reversed = false
        var little16 = false
        let order = image.byteOrderInfo
        if bpc == 8 {
            switch order {
            case .orderDefault, .order32Big: reversed = false
            case .order32Little:
                guard comps == 4 else { return nil }
                reversed = true
            default: return nil
            }
        } else {
            switch order {
            case .orderDefault, .order16Big: little16 = false
            case .order16Little: little16 = true
            default: return nil
            }
        }
        guard let cfData = image.dataProvider?.data else { return nil }
        let data = cfData as Data
        let bpr = image.bytesPerRow
        let pixelBytes = bpp / 8
        guard bpr >= w * pixelBytes, data.count >= bpr * (h - 1) + w * pixelBytes else { return nil }

        let colorStart = (alphaFirst && extra == 1) ? 1 : 0
        let alphaIndex = hasAlpha ? (alphaFirst ? 0 : colorChannels) : -1
        let byteWidth = bpc / 8
        var out = [UInt8](repeating: 255, count: w * h * 4)
        out.withUnsafeMutableBufferPointer { dst in
            data.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
                guard let base = raw.baseAddress?.assumingMemoryBound(to: UInt8.self),
                      let o = dst.baseAddress else { return }
                @inline(__always) func read(_ p: UnsafePointer<UInt8>, _ logical: Int) -> Int {
                    let i = reversed ? (comps - 1 - logical) : logical
                    if byteWidth == 1 { return Int(p[i]) }
                    let b0 = Int(p[i * 2])
                    let b1 = Int(p[i * 2 + 1])
                    let v16 = little16 ? (b1 << 8 | b0) : (b0 << 8 | b1)
                    return (v16 * 255 + 32767) / 65535
                }
                for y in 0..<h {
                    let row = base + y * bpr
                    var d = o + y * w * 4
                    for x in 0..<w {
                        let p = row + x * pixelBytes
                        var r = read(p, colorStart)
                        var g = colorChannels == 3 ? read(p, colorStart + 1) : r
                        var b = colorChannels == 3 ? read(p, colorStart + 2) : r
                        let a = alphaIndex >= 0 ? read(p, alphaIndex) : 255
                        if premultiplied && a < 255 {
                            if a == 0 {
                                r = 0; g = 0; b = 0
                            } else {
                                r = min(255, (r * 255 + a / 2) / a)
                                g = min(255, (g * 255 + a / 2) / a)
                                b = min(255, (b * 255 + a / 2) / a)
                            }
                        }
                        d[0] = UInt8(truncatingIfNeeded: r)
                        d[1] = UInt8(truncatingIfNeeded: g)
                        d[2] = UInt8(truncatingIfNeeded: b)
                        d[3] = UInt8(truncatingIfNeeded: a)
                        d += 4
                    }
                }
            }
        }
        if premultiplied {
            PonyLog.warning("« \(name) » : alpha prémultiplié par ImageIO — RGB reconstitués (perte de précision "
                + "là où l'alpha est faible) [I]")
        }
        return RGBA8Image(width: w, height: h, pixels: out)
    }

    /// Repli : dessin dans un contexte RGBA 8 bits sRGB prémultiplié, puis « déprémultiplication ».
    static func drawnRGBA8(_ image: CGImage) -> RGBA8Image? {
        let w = image.width
        let h = image.height
        guard w > 0, h > 0, let space = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        var buffer = [UInt8](repeating: 0, count: w * h * 4)
        let ok = buffer.withUnsafeMutableBytes { raw -> Bool in
            guard let ctx = CGContext(data: raw.baseAddress, width: w, height: h, bitsPerComponent: 8,
                                      bytesPerRow: w * 4, space: space,
                                      bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue))
            else { return false }
            ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        guard ok else { return nil }
        var i = 0
        while i < buffer.count {
            let a = Int(buffer[i + 3])
            if a > 0 && a < 255 {
                buffer[i] = UInt8(min(255, (Int(buffer[i]) * 255 + a / 2) / a))
                buffer[i + 1] = UInt8(min(255, (Int(buffer[i + 1]) * 255 + a / 2) / a))
                buffer[i + 2] = UInt8(min(255, (Int(buffer[i + 2]) * 255 + a / 2) / a))
            }
            i += 4
        }
        return RGBA8Image(width: w, height: h, pixels: buffer)
    }

    // MARK: Écriture

    /// `CGImage` sRGB 8 bits à partir d'un tampon RGBA. `opaque` : alpha ignoré (`noneSkipLast`) ;
    /// sinon alpha non prémultiplié (`last`), nécessaire pour les crins (découpe par `opacityThreshold`).
    public static func makeCGImage(_ image: RGBA8Image, opaque: Bool) -> CGImage? {
        guard image.width > 0, image.height > 0, image.pixels.count == image.width * image.height * 4 else {
            return nil
        }
        let data = Data(image.pixels)
        guard let provider = CGDataProvider(data: data as CFData),
              let space = CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        let alpha: CGImageAlphaInfo = opaque ? .noneSkipLast : .last
        return CGImage(width: image.width, height: image.height, bitsPerComponent: 8, bitsPerPixel: 32,
                       bytesPerRow: image.width * 4, space: space,
                       bitmapInfo: CGBitmapInfo(rawValue: alpha.rawValue), provider: provider, decode: nil,
                       shouldInterpolate: true, intent: .defaultIntent)
    }

    /// Réduction ×2 (moyenne 2×2) pour les aperçus rapides. Taille impaire : dernière rangée/colonne ignorée.
    public static func halfSize(_ image: RGBA8Image) -> RGBA8Image {
        let w = max(image.width / 2, 1)
        let h = max(image.height / 2, 1)
        if image.width < 2 || image.height < 2 { return image }
        var out = [UInt8](repeating: 0, count: w * h * 4)
        let src = image.pixels
        let sw = image.width
        for y in 0..<h {
            for x in 0..<w {
                let i00 = ((y * 2) * sw + x * 2) * 4
                let i01 = i00 + 4
                let i10 = i00 + sw * 4
                let i11 = i10 + 4
                let o = (y * w + x) * 4
                for c in 0..<4 {
                    let s = Int(src[i00 + c]) + Int(src[i01 + c]) + Int(src[i10 + c]) + Int(src[i11 + c])
                    out[o + c] = UInt8((s + 2) / 4)
                }
            }
        }
        return RGBA8Image(width: w, height: h, pixels: out)
    }
}
