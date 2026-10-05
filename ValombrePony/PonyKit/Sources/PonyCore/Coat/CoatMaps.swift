import Foundation

/// Repères dans l'espace des cartes (unités des canaux du SPEC §4). Valeurs par défaut [I] dérivées du gabarit
/// (`Pipeline/pony/template.py`, poney 1,30 m) ; à remplacer par celles de `body_meta.json` si elles diffèrent.
public struct CoatLandmarks: Codable, Equatable, Hashable, Sendable {
    /// Hauteur de jambe (coat_params R) du bord supérieur de la couronne (≈ 0,07 m / coude 0,71 m).
    public var coronet: Float
    /// v facial (coat_params B) des yeux.
    public var faceEyeV: Float
    /// |u facial − 0,5| des yeux.
    public var faceEyeU: Float
    /// v facial des naseaux.
    public var nostrilV: Float

    public init(coronet: Float = 0.10, faceEyeV: Float = 0.62, faceEyeU: Float = 0.36, nostrilV: Float = 0.10) {
        self.coronet = coronet
        self.faceEyeV = faceEyeV
        self.faceEyeU = faceEyeU
        self.nostrilV = nostrilV
    }

    public static let `default` = CoatLandmarks()
}

/// Cartes d'entrée du compositeur (SPEC §4), chargées par PonyKit depuis les PNG « raw » :
/// - `shading` (2048²) : R détail de luminance du poil (0,5 neutre), G cavité (1 = aucune), B peau nue (0…1) ;
/// - `regions` (1024²) : R = id de région × 16 (plus proche voisin), G extrémités, B pangaré, A charbonné ;
/// - `params` (1024²) : R hauteur de jambe (0 sol → 1 coude/grasset), G u facial, B v facial, A raie de mulet ;
/// - `patterns` (1024²) : R champ pie A (tobiano), G champ pie B (overo/sabino/splash), B taches, A pommelures.
/// Les résolutions peuvent différer entre elles et de la sortie (échantillonnage bilinéaire).
public struct CoatMaps: Sendable {
    public var shading: RGBA8Image
    public var regions: RGBA8Image
    public var params: RGBA8Image
    public var patterns: RGBA8Image
    /// Texture de mèches des crins (R luminance 0,5 neutre, G racine→pointe, B aléa par mèche, A alpha).
    public var hairStrands: RGBA8Image?
    /// Carte grise de détail d'iris (R, 0,5 neutre) ; nil = iris procédural.
    public var irisDetail: RGBA8Image?
    public var landmarks: CoatLandmarks

    public init(shading: RGBA8Image, regions: RGBA8Image, params: RGBA8Image, patterns: RGBA8Image,
                hairStrands: RGBA8Image? = nil, irisDetail: RGBA8Image? = nil,
                landmarks: CoatLandmarks = .default) {
        self.shading = shading
        self.regions = regions
        self.params = params
        self.patterns = patterns
        self.hairStrands = hairStrands
        self.irisDetail = irisDetail
        self.landmarks = landmarks
    }

    /// Identifiants de région du SPEC §4.
    public enum Region: Int, CaseIterable, Sendable {
        case body = 0, head, muzzle, earOuter, earInner
        case legFrontLeft, legFrontRight, legHindLeft, legHindRight
        case hoofFrontLeft, hoofFrontRight, hoofHindLeft, hoofHindRight
        case chestnuts, periocularSkin, ventralSkin
    }

    // MARK: - Cartes synthétiques (tests, aperçus sans les cartes réelles)

    /// Cartes synthétiques « poupée de papier » (corps, tête, 4 membres, 4 sabots, châtaignes, peau ventrale),
    /// calculées en arithmétique ENTIÈRE : identiques au bit près à `synthetic_maps()` de `coat_reference.py`.
    public static func synthetic(size: Int) -> CoatMaps {
        CoatSyntheticMaps.make(size: size)
    }

    /// Texture de mèches synthétique (identique à `synthetic_strands()` en Python).
    public static func syntheticStrands(width: Int = 128, height: Int = 256) -> RGBA8Image {
        CoatSyntheticMaps.strands(width: width, height: height)
    }
}

/// Générateur entier des cartes synthétiques (traduction ligne à ligne de coat_reference.py).
enum CoatSyntheticMaps {
    static let salt = 0x5EED

    @inline(__always)
    static func h8(_ a: Int, _ b: Int, _ s: Int) -> Int {
        Int(CoatNoise.hash(UInt32(truncatingIfNeeded: a), UInt32(truncatingIfNeeded: b),
                           UInt32(truncatingIfNeeded: s)) >> 24)
    }

    /// Bruit de valeur entier 0…255 (pas `cell`, pour-mille).
    static func inoise(_ px: Int, _ py: Int, _ cell: Int, _ s: Int) -> Int {
        let gx = px / cell
        let gy = py / cell
        let fx = px % cell
        let fy = py % cell
        let a = h8(gx, gy, s)
        let b = h8(gx + 1, gy, s)
        let c = h8(gx, gy + 1, s)
        let d = h8(gx + 1, gy + 1, s)
        let top = (a * (cell - fx) + b * fx) / cell
        let bot = (c * (cell - fx) + d * fx) / cell
        return (top * (cell - fy) + bot * fy) / cell
    }

    /// Champ cellulaire entier 0…255 (255 au centre décalé de chaque cellule, 0 à `radius`).
    static func icells(_ px: Int, _ py: Int, _ cell: Int, _ radius: Int, _ s: Int) -> Int {
        let gx = px / cell
        let gy = py / cell
        let cx = gx * cell + cell / 4 + (h8(gx, gy, s) * (cell / 2)) / 256
        let cy = gy * cell + cell / 4 + (h8(gx, gy, s + 1) * (cell / 2)) / 256
        let dx = px - cx
        let dy = py - cy
        let d2 = dx * dx + dy * dy
        let r2 = radius * radius
        return max(0, 255 - (d2 * 255) / r2)
    }

    @inline(__always)
    static func clampi(_ v: Int, _ lo: Int, _ hi: Int) -> Int { min(max(v, lo), hi) }

    @inline(__always)
    static func byte(_ v: Int) -> UInt8 { UInt8(clampi(v, 0, 255)) }

    static func make(size: Int) -> CoatMaps {
        let n = size * size * 4
        var shading = [UInt8](repeating: 0, count: n)
        var regions = [UInt8](repeating: 0, count: n)
        var params = [UInt8](repeating: 0, count: n)
        var patterns = [UInt8](repeating: 0, count: n)
        let s = salt
        for y in 0..<size {
            for x in 0..<size {
                let ux = ((2 * x + 1) * 1000) / (2 * size)
                let vy = ((2 * y + 1) * 1000) / (2 * size)
                var region = 0, ext = 0, pang = 0, soot = 0, leg = 0, fu = 0, fv = 0, dors = 0, skin = 0
                var pA = 0, pB = 0
                let n1 = inoise(ux, vy, 120, s)
                let n2 = inoise(ux, vy, 90, s + 7)
                let spots = icells(ux, vy, 36, 14, s + 11)
                let dapples = icells(ux, vy, 28, 15, s + 13)

                // Corps
                if ux >= 40 && ux < 740 && vy >= 40 && vy < 440 {
                    let bx = clampi((ux - 40) * 1000 / 700, 0, 999)
                    let by = clampi((vy - 40) * 1000 / 400, 0, 999)
                    soot = max(0, 600 - by) * 255 / 600
                    pang = max(0, by - 550) * 255 / 450
                    dors = max(0, 120 - by) * 255 / 120
                    let cross = 255 - abs(bx - 500) * 255 / 500
                    pA = (n1 * 2 + cross) / 3
                    pB = (n2 + by * 255 / 1000 * 2) / 3
                    if bx >= 100 && bx < 180 && by >= 900 {
                        region = 15
                        skin = 255
                    }
                }
                // Tête
                if ux >= 760 && ux < 980 && vy >= 40 && vy < 440 {
                    let hu = clampi((ux - 760) * 1000 / 220, 0, 999)
                    let hv = clampi((440 - vy) * 1000 / 400, 0, 999)
                    region = 1
                    fu = hu * 255 / 1000
                    fv = hv * 255 / 1000
                    if hv < 150 {
                        region = 2
                        skin = 150
                    }
                    pang = max(0, 220 - hv) * 255 / 220
                    let ex = abs(hu - 500) - 360
                    let ey = hv - 620
                    if ex * ex + ey * ey < 45 * 45 {
                        region = 14
                        skin = 255
                    }
                    let ear = hv > 930 && abs(hu - 500) > 250
                    if ear {
                        region = 3
                        ext = 255
                    }
                    if ear && abs(hu - 500) > 300 && abs(hu - 500) < 400 && hv > 955 {
                        region = 4
                    }
                    pA = n1 / 4
                    pB = (255 - hv * 255 / 1000) / 2 + n2 / 4
                }
                // Membres et sabots
                for i in 0..<4 {
                    let x0 = 40 + 180 * i
                    let col = ux >= x0 && ux < x0 + 120
                    let pad = ux >= x0 - 20 && ux < x0 + 140 && vy >= 470 && vy < 960
                    let lg = col && vy >= 480 && vy < 900
                    let hf = col && vy >= 900 && vy < 960
                    let lh = 1000 - max(vy - 480, 0) * 900 / 420
                    let lhp = vy >= 900 ? max(960 - vy, 0) * 100 / 60 : lh
                    if pad {
                        leg = clampi(lhp, 0, 1000) * 255 / 1000
                    }
                    if lg {
                        region = 5 + i
                        ext = clampi(700 - lh, 0, 100) * 255 / 100
                        pA = 190 + n1 / 4
                        pB = (255 - clampi(lh, 0, 1000) * 255 / 1000 + n2) / 2
                    }
                    if hf {
                        region = 9 + i
                        pA = 230
                        pB = 200
                    }
                    let clo = i < 2 ? 550 : 300
                    let chi = i < 2 ? 620 : 360
                    if lg && ux >= x0 + 80 && ux < x0 + 110 && lh >= clo && lh < chi {
                        region = 13
                    }
                }
                let lum = 128 + (h8(x, y, s + 3) >> 4) - 8
                let cav = 255 - (h8(x / 4, y / 4, s + 5) >> 3)
                let o = (y * size + x) * 4
                shading[o] = byte(lum)
                shading[o + 1] = byte(cav)
                shading[o + 2] = byte(skin)
                shading[o + 3] = 255
                regions[o] = byte(region * 16)
                regions[o + 1] = byte(ext)
                regions[o + 2] = byte(pang)
                regions[o + 3] = byte(soot)
                params[o] = byte(leg)
                params[o + 1] = byte(fu)
                params[o + 2] = byte(fv)
                params[o + 3] = byte(dors)
                patterns[o] = byte(pA)
                patterns[o + 1] = byte(pB)
                patterns[o + 2] = byte(spots)
                patterns[o + 3] = byte(dapples)
            }
        }
        return CoatMaps(shading: RGBA8Image(width: size, height: size, pixels: shading),
                        regions: RGBA8Image(width: size, height: size, pixels: regions),
                        params: RGBA8Image(width: size, height: size, pixels: params),
                        patterns: RGBA8Image(width: size, height: size, pixels: patterns),
                        hairStrands: strands(width: 128, height: 256))
    }

    static func strands(width: Int, height: Int) -> RGBA8Image {
        var px = [UInt8](repeating: 0, count: width * height * 4)
        let s = salt
        let tip = height * 4 / 5
        for y in 0..<height {
            for x in 0..<width {
                let sid = x / 4
                let r = 128 + (h8(x, y / 8, s + 21) >> 3) - 16
                let g = y * 255 / max(height - 1, 1)
                let bb = h8(sid, 0, s + 23)
                let a: Int
                if x % 4 == 3 {
                    a = 0
                } else if y < tip {
                    a = 255
                } else {
                    a = max(0, 255 - (y - tip) * 255 / max(height - tip, 1))
                }
                let o = (y * width + x) * 4
                px[o] = UInt8(clampi(r, 0, 255))
                px[o + 1] = UInt8(clampi(g, 0, 255))
                px[o + 2] = UInt8(clampi(bb, 0, 255))
                px[o + 3] = UInt8(clampi(a, 0, 255))
            }
        }
        return RGBA8Image(width: width, height: height, pixels: px)
    }
}
