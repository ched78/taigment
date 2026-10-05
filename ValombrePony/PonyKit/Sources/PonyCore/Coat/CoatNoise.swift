import Foundation

// Hachage entier et bruit de valeur — identiques au bit près à `coat_reference.py`
// (hash32 = « lowbias32 » de C. Wellons ; arithmétique UInt32 modulo 2^32 via &*, &+).
// Aucune fonction transcendante : seulement + − × ÷, min, max, floor, sqrt (correctement arrondies en IEEE 754),
// pour que Swift et numpy (float32) produisent les mêmes valeurs.

enum CoatNoise {
    /// Sels des couches de bruit (même table que `SALT` en Python).
    enum Salt {
        static let grey: UInt32 = 0x1001
        static let flea: UInt32 = 0x1002
        static let flea2: UInt32 = 0x1003
        static let roan: UInt32 = 0x1004
        static let roan2: UInt32 = 0x1005
        static let bar: UInt32 = 0x1006
        static let tob: UInt32 = 0x1007
        static let ov: UInt32 = 0x1008
        static let ov2: UInt32 = 0x1009
        static let sab: UInt32 = 0x100A
        static let sab2: UInt32 = 0x100B
        static let spl: UInt32 = 0x100C
        static let dw: UInt32 = 0x100D
        static let lp: UInt32 = 0x100E
        static let lpd: UInt32 = 0x100F
        static let varnish: UInt32 = 0x1010
        static let varnish2: UInt32 = 0x1011
        static let face: UInt32 = 0x1012
        static let mottle: UInt32 = 0x1013
        static let freckle: UInt32 = 0x1014
        static let hoof: UInt32 = 0x1015
        static let secondary: UInt32 = 0x1016
        static let whiteStrand: UInt32 = 0x1017
        static let iris: UInt32 = 0x1018
        static let vairon: UInt32 = 0x1019
        static let granula: UInt32 = 0x101A
        static let leg: UInt32 = 0x1020      // + indice du membre (0…3)
        static let ermine: UInt32 = 0x1030   // + indice du membre (0…3)
    }

    @inline(__always)
    static func hash32(_ v: UInt32) -> UInt32 {
        var x = v
        x ^= x >> 16
        x = x &* 0x7FEB_352D
        x ^= x >> 15
        x = x &* 0x846C_A68B
        x ^= x >> 16
        return x
    }

    /// Graine d'une couche : hash32(seed &+ salt &* 0x9E3779B9).
    @inline(__always)
    static func salted(_ seed: UInt32, _ salt: UInt32) -> UInt32 {
        hash32(seed &+ salt &* 0x9E37_79B9)
    }

    /// h(a, b, s) = hash32(a ^ hash32(b ^ s)).
    @inline(__always)
    static func hash(_ a: UInt32, _ b: UInt32, _ s: UInt32) -> UInt32 {
        hash32(a ^ hash32(b ^ s))
    }

    /// [0, 1) : Float(h >> 8) · 2^-24 (exact).
    @inline(__always)
    static func hash01(_ a: UInt32, _ b: UInt32, _ s: UInt32) -> Float {
        Float(hash(a, b, s) >> 8) * 5.9604644775390625e-08
    }

    /// Bruit de valeur 2D (réseau entier haché, interpolation smoothstep). x, y ramenés à >= 0.
    /// `periodX > 0` : périodique en x (indices modulo periodX).
    @inline(__always)
    static func valueNoise(_ xIn: Float, _ yIn: Float, _ s: UInt32, periodX: UInt32 = 0) -> Float {
        let x = max(xIn, 0)
        let y = max(yIn, 0)
        let fx = x.rounded(.down)
        let fy = y.rounded(.down)
        let ix = UInt32(fx)
        let iy = UInt32(fy)
        let tx = x - fx
        let ty = y - fy
        let sx = tx * tx * (3 - 2 * tx)
        let sy = ty * ty * (3 - 2 * ty)
        let ix0: UInt32
        let ix1: UInt32
        if periodX > 0 {
            ix0 = ix % periodX
            ix1 = (ix &+ 1) % periodX
        } else {
            ix0 = ix
            ix1 = ix &+ 1
        }
        let iy1 = iy &+ 1
        let a = hash01(ix0, iy, s)
        let b = hash01(ix1, iy, s)
        let c = hash01(ix0, iy1, s)
        let d = hash01(ix1, iy1, s)
        let top = a + (b - a) * sx
        let bot = c + (d - c) * sx
        return top + (bot - top) * sy
    }
}

// MARK: - Fonctions scalaires partagées (mêmes formules que coat_reference.py)

@inline(__always)
func coatSmoothstep(_ e0: Float, _ e1: Float, _ x: Float) -> Float {
    var t = (x - e0) / (e1 - e0)
    t = min(max(t, 0), 1)
    return t * t * (3 - 2 * t)
}

@inline(__always)
func coatClamp01(_ x: Float) -> Float {
    min(max(x, 0), 1)
}

@inline(__always)
func coatMix(_ a: Float, _ b: Float, _ t: Float) -> Float {
    a + (b - a) * t
}

@inline(__always)
func coatMix(_ a: SIMD3<Float>, _ b: SIMD3<Float>, _ t: Float) -> SIMD3<Float> {
    a + (b - a) * t
}

/// Seuil de couverture : cov = 0 -> rien ; cov = 1 -> tout (pour un champ dans [0, 1]) ; e = demi-largeur du bord.
@inline(__always)
func coatCoverMask(_ field: Float, _ cov: Float, _ e: Float, _ noise: Float) -> Float {
    let thr = (1 - cov) * (1 + 2 * e) - e
    return coatSmoothstep(-e, e, field + noise - thr)
}
