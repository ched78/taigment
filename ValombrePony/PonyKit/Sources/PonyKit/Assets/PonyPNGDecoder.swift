import Compression
import Foundation
import PonyCore

/// Décodeur PNG minimal en Swift pur (spécification PNG, W3C / ISO 15948) pour les cartes « raw » du SPEC §4.
///
/// Pourquoi : les cartes de pelage sont des DONNÉES (id de région ×16, masques dans l'alpha…). Le décodage par
/// ImageIO ne documente pas s'il prémultiplie l'alpha d'un PNG RGBA ; une prémultiplication détruirait les canaux
/// RGB là où l'alpha est faible (ex. `coat_regions` : alpha = masque charbonné, souvent 0). Ce décodeur lit les
/// octets du fichier tels quels : résultat exact par construction, indépendant d'ImageIO [I].
///
/// Pris en charge : PNG non entrelacé, types de couleur 0 (gris), 2 (RGB), 3 (palette), 4 (gris + alpha),
/// 6 (RGBA), profondeurs 1/2/4/8/16 selon le type, les 5 filtres, `tRNS` (palette et couleur clé).
/// Non pris en charge (erreur → repli ImageIO) : entrelacement Adam7, PNG « CgBI » optimisés par Xcode.
/// Les CRC ne sont pas vérifiés (fichiers du bundle). 16 bits → 8 bits par arrondi `(v·255 + 32767) / 65535`.
///
/// Décompression : `compression_decode_buffer` avec `COMPRESSION_ZLIB` (framework Compression, iOS 9 /
/// macOS 10.11), documenté comme décodant le format DEFLATE « brut » (RFC 1951) : on retire l'en-tête zlib
/// (2 octets) et la somme Adler-32 finale (4 octets) du flux IDAT.
/// Vérification sans compilateur : la même logique, transcrite ligne à ligne en Python, est comparée octet pour
/// octet à Pillow sur les cartes du pipeline et sur des PNG synthétiques (tous types, profondeurs et filtres).
enum PonyPNGDecoder {

    enum DecodeError: Error, CustomStringConvertible {
        case notPNG
        case unsupported(String)
        case corrupt(String)

        var description: String {
            switch self {
            case .notPNG: return "signature PNG absente"
            case .unsupported(let r): return "PNG non pris en charge : \(r)"
            case .corrupt(let r): return "PNG corrompu : \(r)"
            }
        }
    }

    static let signature: [UInt8] = [137, 80, 78, 71, 13, 10, 26, 10]

    /// Vrai si les données commencent par la signature PNG.
    static func isPNG(_ data: Data) -> Bool {
        return data.count >= 8 && data.prefix(8).elementsEqual(signature)
    }

    @inline(__always)
    static func be32(_ b: [UInt8], _ i: Int) -> Int {
        return Int(b[i]) << 24 | Int(b[i + 1]) << 16 | Int(b[i + 2]) << 8 | Int(b[i + 3])
    }

    /// Décode un PNG en RGBA 8 bits (rangées de haut en bas), sans aucune conversion de couleur.
    static func decode(_ data: Data) throws -> RGBA8Image {
        let bytes = [UInt8](data)
        guard bytes.count >= 8, Array(bytes[0..<8]) == signature else { throw DecodeError.notPNG }

        var width = 0
        var height = 0
        var bitDepth = 0
        var colorType = -1
        var palette: [UInt8] = []
        var paletteAlpha: [UInt8] = []
        var colorKey: [Int] = []          // tRNS des types 0 (1 valeur) et 2 (3 valeurs), échantillons bruts
        var idat: [UInt8] = []
        var sawHeader = false
        var pos = 8
        while pos + 12 <= bytes.count {
            let length = be32(bytes, pos)
            let type = String(decoding: bytes[(pos + 4)..<(pos + 8)], as: UTF8.self)
            let start = pos + 8
            guard length >= 0, start + length + 4 <= bytes.count else {
                throw DecodeError.corrupt("bloc « \(type) » tronqué")
            }
            let body = Array(bytes[start..<(start + length)])
            switch type {
            case "IHDR":
                guard body.count == 13 else { throw DecodeError.corrupt("IHDR de \(body.count) octets") }
                width = be32(body, 0)
                height = be32(body, 4)
                bitDepth = Int(body[8])
                colorType = Int(body[9])
                guard body[10] == 0, body[11] == 0 else {
                    throw DecodeError.unsupported("méthode de compression/filtrage \(body[10])/\(body[11])")
                }
                guard body[12] == 0 else { throw DecodeError.unsupported("entrelacement Adam7") }
                sawHeader = true
            case "CgBI":
                throw DecodeError.unsupported("PNG optimisé par Xcode (CgBI, alpha prémultiplié)")
            case "PLTE":
                palette = body
            case "tRNS":
                if colorType == 3 {
                    paletteAlpha = body
                } else if colorType == 0 && body.count >= 2 {
                    colorKey = [Int(body[0]) << 8 | Int(body[1])]
                } else if colorType == 2 && body.count >= 6 {
                    colorKey = [Int(body[0]) << 8 | Int(body[1]), Int(body[2]) << 8 | Int(body[3]),
                                Int(body[4]) << 8 | Int(body[5])]
                }
            case "IDAT":
                idat.append(contentsOf: body)
            default:
                break
            }
            pos = start + length + 4
            if type == "IEND" { break }
        }
        guard sawHeader else { throw DecodeError.corrupt("IHDR absent") }
        guard width > 0, height > 0, width <= 16384, height <= 16384 else {
            throw DecodeError.unsupported("dimensions \(width) × \(height)")
        }

        let channels: Int
        let allowedDepths: [Int]
        switch colorType {
        case 0: channels = 1; allowedDepths = [1, 2, 4, 8, 16]
        case 2: channels = 3; allowedDepths = [8, 16]
        case 3: channels = 1; allowedDepths = [1, 2, 4, 8]
        case 4: channels = 2; allowedDepths = [8, 16]
        case 6: channels = 4; allowedDepths = [8, 16]
        default: throw DecodeError.unsupported("type de couleur \(colorType)")
        }
        guard allowedDepths.contains(bitDepth) else {
            throw DecodeError.unsupported("profondeur \(bitDepth) pour le type \(colorType)")
        }
        if colorType == 3 && (palette.isEmpty || palette.count % 3 != 0) {
            throw DecodeError.corrupt("palette absente ou invalide")
        }

        let bitsPerPixel = channels * bitDepth
        let rowBytes = (width * bitsPerPixel + 7) / 8
        let bpp = max(1, bitsPerPixel / 8)            // écart du filtre, en octets
        let expected = height * (rowBytes + 1)

        // --- Décompression (flux zlib = en-tête 2 octets + DEFLATE brut + Adler-32 4 octets).
        guard idat.count >= 6 else { throw DecodeError.corrupt("données IDAT absentes") }
        let cmf = Int(idat[0])
        let flg = Int(idat[1])
        guard cmf & 0x0F == 8, (cmf * 256 + flg) % 31 == 0, flg & 0x20 == 0 else {
            throw DecodeError.corrupt("en-tête zlib invalide")
        }
        var raw = [UInt8](repeating: 0, count: expected + 1)
        let sourceCount = idat.count - 6
        let written = raw.withUnsafeMutableBufferPointer { dst -> Int in
            idat.withUnsafeBufferPointer { src -> Int in
                guard let d = dst.baseAddress, let s = src.baseAddress else { return 0 }
                let scratchSize = max(compression_decode_scratch_buffer_size(COMPRESSION_ZLIB), 1)
                let scratch = UnsafeMutableRawPointer.allocate(byteCount: scratchSize, alignment: 16)
                defer { scratch.deallocate() }
                return compression_decode_buffer(d, expected + 1, s + 2, sourceCount, scratch, COMPRESSION_ZLIB)
            }
        }
        guard written == expected else {
            throw DecodeError.corrupt("\(written) octets décompressés au lieu de \(expected)")
        }

        // --- Défiltrage. Rangée y stockée à (y + 1)·rowBytes ; la rangée 0 du tampon reste nulle (« précédente »
        // de la première rangée).
        var rows = [UInt8](repeating: 0, count: (height + 1) * rowBytes)
        try rows.withUnsafeMutableBufferPointer { rowBuf in
            try raw.withUnsafeBufferPointer { rawBuf in
                guard let o = rowBuf.baseAddress, let r = rawBuf.baseAddress else { return }
                for y in 0..<height {
                    let filter = r[y * (rowBytes + 1)]
                    let src = r + y * (rowBytes + 1) + 1
                    let dst = o + (y + 1) * rowBytes
                    let prev = o + y * rowBytes
                    switch filter {
                    case 0:
                        for i in 0..<rowBytes { dst[i] = src[i] }
                    case 1:
                        for i in 0..<rowBytes {
                            let a: UInt8 = i >= bpp ? dst[i - bpp] : 0
                            dst[i] = src[i] &+ a
                        }
                    case 2:
                        for i in 0..<rowBytes { dst[i] = src[i] &+ prev[i] }
                    case 3:
                        for i in 0..<rowBytes {
                            let a = i >= bpp ? Int(dst[i - bpp]) : 0
                            let b = Int(prev[i])
                            dst[i] = src[i] &+ UInt8((a + b) >> 1)
                        }
                    case 4:
                        for i in 0..<rowBytes {
                            let a = i >= bpp ? Int(dst[i - bpp]) : 0
                            let b = Int(prev[i])
                            let c = i >= bpp ? Int(prev[i - bpp]) : 0
                            let p = a + b - c
                            let pa = abs(p - a)
                            let pb = abs(p - b)
                            let pc = abs(p - c)
                            let pred = (pa <= pb && pa <= pc) ? a : (pb <= pc ? b : c)
                            dst[i] = src[i] &+ UInt8(pred)
                        }
                    default:
                        throw DecodeError.corrupt("filtre de rangée \(filter) inconnu (rangée \(y))")
                    }
                }
            }
        }

        // --- Conversion en RGBA 8 bits.
        let maxSample = (1 << bitDepth) - 1
        var out = [UInt8](repeating: 255, count: width * height * 4)
        try out.withUnsafeMutableBufferPointer { outBuf in
            try rows.withUnsafeBufferPointer { rowBuf in
                guard let o = outBuf.baseAddress, let base = rowBuf.baseAddress else { return }
                for y in 0..<height {
                    let row = base + (y + 1) * rowBytes
                    var d = o + y * width * 4
                    for x in 0..<width {
                        // Échantillons bruts (profondeur d'origine) des `channels` canaux du pixel x.
                        var s = (0, 0, 0, 0)
                        if bitDepth == 8 {
                            let p = row + x * channels
                            s.0 = Int(p[0])
                            if channels > 1 { s.1 = Int(p[1]) }
                            if channels > 2 { s.2 = Int(p[2]) }
                            if channels > 3 { s.3 = Int(p[3]) }
                        } else if bitDepth == 16 {
                            let p = row + x * channels * 2
                            s.0 = Int(p[0]) << 8 | Int(p[1])
                            if channels > 1 { s.1 = Int(p[2]) << 8 | Int(p[3]) }
                            if channels > 2 { s.2 = Int(p[4]) << 8 | Int(p[5]) }
                            if channels > 3 { s.3 = Int(p[6]) << 8 | Int(p[7]) }
                        } else {
                            // 1, 2 ou 4 bits : un seul canal (gris ou indice de palette), bits de poids fort d'abord.
                            let bit = x * bitDepth
                            let byte = Int(row[bit >> 3])
                            s.0 = (byte >> (8 - bitDepth - (bit & 7))) & maxSample
                        }
                        var rr = 0, gg = 0, bb = 0, aa = 255
                        switch colorType {
                        case 3:
                            let idx = s.0
                            guard idx * 3 + 2 < palette.count else {
                                throw DecodeError.corrupt("indice de palette \(idx) hors limites")
                            }
                            rr = Int(palette[idx * 3])
                            gg = Int(palette[idx * 3 + 1])
                            bb = Int(palette[idx * 3 + 2])
                            aa = idx < paletteAlpha.count ? Int(paletteAlpha[idx]) : 255
                        case 0:
                            let v = PonyPNGDecoder.to8(s.0, bitDepth: bitDepth, maxSample: maxSample)
                            rr = v; gg = v; bb = v
                            if colorKey.count == 1 && s.0 == colorKey[0] { aa = 0 }
                        case 4:
                            let v = PonyPNGDecoder.to8(s.0, bitDepth: bitDepth, maxSample: maxSample)
                            rr = v; gg = v; bb = v
                            aa = PonyPNGDecoder.to8(s.1, bitDepth: bitDepth, maxSample: maxSample)
                        case 2:
                            rr = PonyPNGDecoder.to8(s.0, bitDepth: bitDepth, maxSample: maxSample)
                            gg = PonyPNGDecoder.to8(s.1, bitDepth: bitDepth, maxSample: maxSample)
                            bb = PonyPNGDecoder.to8(s.2, bitDepth: bitDepth, maxSample: maxSample)
                            if colorKey.count == 3 && s.0 == colorKey[0] && s.1 == colorKey[1] && s.2 == colorKey[2] {
                                aa = 0
                            }
                        default:   // 6
                            rr = PonyPNGDecoder.to8(s.0, bitDepth: bitDepth, maxSample: maxSample)
                            gg = PonyPNGDecoder.to8(s.1, bitDepth: bitDepth, maxSample: maxSample)
                            bb = PonyPNGDecoder.to8(s.2, bitDepth: bitDepth, maxSample: maxSample)
                            aa = PonyPNGDecoder.to8(s.3, bitDepth: bitDepth, maxSample: maxSample)
                        }
                        d[0] = UInt8(truncatingIfNeeded: rr)
                        d[1] = UInt8(truncatingIfNeeded: gg)
                        d[2] = UInt8(truncatingIfNeeded: bb)
                        d[3] = UInt8(truncatingIfNeeded: aa)
                        d += 4
                    }
                }
            }
        }
        return RGBA8Image(width: width, height: height, pixels: out)
    }

    /// Échantillon brut → 8 bits : identité en 8 bits, arrondi en 16 bits, mise à l'échelle sous 8 bits.
    @inline(__always)
    static func to8(_ v: Int, bitDepth: Int, maxSample: Int) -> Int {
        if bitDepth == 8 { return v }
        if bitDepth == 16 { return (v * 255 + 32767) / 65535 }
        return v * 255 / maxSample
    }
}
