import Foundation

/// Compositeur de pelage : fonctions pures qui produisent des `RGBA8Image` sRGB.
///
/// - `composeBody` : albedo du corps (UV0) à partir des cartes cuites du SPEC §4 ;
/// - `composeHair` : albedo des crins à partir de la texture de mèches (alpha conservé) ;
/// - `composeIris` : texture d'iris (512² par défaut).
///
/// Traduction LIGNE À LIGNE de `Pipeline/pony/coat_reference.py` (vérité exécutable) : mêmes formules, mêmes
/// constantes, même ordre d'opérations en Float, même hachage entier. Les vecteurs de référence
/// (`CoatReferenceVectorsTests`) vérifient l'égalité à ±3 niveaux près (écarts possibles de libm sur la palette
/// et de contraction FMA).
///
/// Performance [I] : une seule passe par texel, palette précalculée, tables bilinéaires par colonne / rangée,
/// `DispatchQueue.concurrentPerform` par bandes de rangées. Objectif < 150 ms à 2048² sur un iPhone récent :
/// NON MESURÉ (pas de matériel Apple dans l'environnement de génération). Utiliser `previewResolution` (1024)
/// pendant le glissement d'un curseur et `finalResolution` (2048) au relâcher.
public enum CoatCompositor {
    public static let previewResolution = 1024
    public static let finalResolution = 2048
    public static let irisResolution = 512

    /// Table d'encodage linéaire -> sRGB 8 bits (4096 entrées) : idx = Int(clamp(v, 0, 1)·4095 + 0,5).
    static let encodeLUT: [UInt8] = {
        var lut = [UInt8](repeating: 0, count: 4096)
        for i in 0..<4096 {
            let v = PonyColor.linearToSRGB(Double(i) / 4095.0)
            lut[i] = UInt8(min(255, max(0, Int((v * 255.0 + 0.5).rounded(.down)))))
        }
        return lut
    }()

    @inline(__always)
    static func encodeIndex(_ v: Float) -> Int {
        Int(min(max(v, 0), 1) * 4095 + 0.5)
    }

    // MARK: - Corps

    /// Albedo sRGB (resolution²) du corps. `resolution` : 1024 pendant l'édition, 2048 au relâcher.
    public static func composeBody(_ configuration: CoatConfiguration, maps: CoatMaps,
                                   resolution: Int = CoatCompositor.finalResolution) -> RGBA8Image {
        let size = max(resolution, 1)
        let P = CoatPalette(configuration)
        let LM = maps.landmarks
        let all = [maps.shading, maps.regions, maps.params, maps.patterns]
        if all.contains(where: { $0.width == 0 || $0.height == 0 }) {
            // Cartes absentes : aplat de la couleur de robe (garde-fou, ne devrait pas arriver).
            let c = P.body
            let lut = encodeLUT
            return RGBA8Image(width: size, height: size,
                              fill: (lut[encodeIndex(c.x)], lut[encodeIndex(c.y)], lut[encodeIndex(c.z)], 255))
        }
        // Tables d'axes (mémoire propre, libérée à la fin) et vues sans comptage de références pour la boucle.
        let tables = [CoatAxisTable(mapSize: maps.shading.width, outSize: size),
                      CoatAxisTable(mapSize: maps.shading.height, outSize: size),
                      CoatAxisTable(mapSize: maps.regions.width, outSize: size),
                      CoatAxisTable(mapSize: maps.regions.height, outSize: size),
                      CoatAxisTable(mapSize: maps.params.width, outSize: size),
                      CoatAxisTable(mapSize: maps.params.height, outSize: size),
                      CoatAxisTable(mapSize: maps.patterns.width, outSize: size),
                      CoatAxisTable(mapSize: maps.patterns.height, outSize: size)]
        let shX = tables[0].view, shY = tables[1].view, rgX = tables[2].view, rgY = tables[3].view
        let paX = tables[4].view, paY = tables[5].view, ptX = tables[6].view, ptY = tables[7].view
        let shW = maps.shading.width
        let rgW = maps.regions.width
        let paW = maps.params.width
        let ptW = maps.patterns.width
        let fsize = Float(size)

        var out = [UInt8](repeating: 255, count: size * size * 4)
        let lut = encodeLUT
        let bandRows = 16
        let bands = (size + bandRows - 1) / bandRows
        withExtendedLifetime(tables) {
            out.withUnsafeMutableBufferPointer { ob in
                guard let outBase = ob.baseAddress else { return }
                maps.shading.pixels.withUnsafeBufferPointer { shB in
                    maps.regions.pixels.withUnsafeBufferPointer { rgB in
                        maps.params.pixels.withUnsafeBufferPointer { paB in
                            maps.patterns.pixels.withUnsafeBufferPointer { ptB in
                                lut.withUnsafeBufferPointer { lutB in
                                    guard let sh = shB.baseAddress, let rg = rgB.baseAddress,
                                          let pa = paB.baseAddress, let pt = ptB.baseAddress,
                                          let lt = lutB.baseAddress else { return }
                                    DispatchQueue.concurrentPerform(iterations: bands) { band in
                                        let yStart = band * bandRows
                                        let yEnd = min(size, yStart + bandRows)
                                        for y in yStart..<yEnd {
                                            let vy = (Float(y) + 0.5) / fsize
                                            for x in 0..<size {
                                                let s = bilinear4(sh, shW, shX, shY, x, y)
                                                let r = bilinear4(rg, rgW, rgX, rgY, x, y)
                                                let p = bilinear4(pa, paW, paX, paY, x, y)
                                                let q = bilinear4(pt, ptW, ptX, ptY, x, y)
                                                let ni = (Int(rgY.nearest[y]) * rgW + Int(rgX.nearest[x])) * 4
                                                let rid = min((Int(rg[ni]) + 8) / 16, 15)
                                                let t = CoatTexelInput(
                                                    lum: s.x, cav: s.y, skin: s.z,
                                                    ext: r.y, pmask: r.z, smask: r.w,
                                                    leg: p.x, fu: p.y, fv: p.z, dors: p.w,
                                                    fA: q.x, fB: q.y, fS: q.z, fD: q.w,
                                                    rid: rid, x: x, y: y,
                                                    ux: (Float(x) + 0.5) / fsize, vy: vy)
                                                let c = shadeTexel(t, P, LM)
                                                let o = (y * size + x) * 4
                                                outBase[o] = lt[encodeIndex(c.x)]
                                                outBase[o + 1] = lt[encodeIndex(c.y)]
                                                outBase[o + 2] = lt[encodeIndex(c.z)]
                                                outBase[o + 3] = 255
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        return RGBA8Image(width: size, height: size, pixels: out)
    }

    /// Échantillon bilinéaire des 4 canaux (octets / 255) au texel de sortie (x, y).
    @inline(__always)
    static func bilinear4(_ px: UnsafePointer<UInt8>, _ width: Int, _ tx: CoatAxisView, _ ty: CoatAxisView,
                          _ x: Int, _ y: Int) -> SIMD4<Float> {
        let x0 = Int(tx.i0[x])
        let x1 = Int(tx.i1[x])
        let y0 = Int(ty.i0[y])
        let y1 = Int(ty.i1[y])
        let wx = tx.w[x]
        let wy = ty.w[y]
        let o00 = (y0 * width + x0) * 4
        let o10 = (y0 * width + x1) * 4
        let o01 = (y1 * width + x0) * 4
        let o11 = (y1 * width + x1) * 4
        let p00 = SIMD4<Float>(Float(px[o00]), Float(px[o00 + 1]), Float(px[o00 + 2]), Float(px[o00 + 3])) / 255
        let p10 = SIMD4<Float>(Float(px[o10]), Float(px[o10 + 1]), Float(px[o10 + 2]), Float(px[o10 + 3])) / 255
        let p01 = SIMD4<Float>(Float(px[o01]), Float(px[o01 + 1]), Float(px[o01 + 2]), Float(px[o01 + 3])) / 255
        let p11 = SIMD4<Float>(Float(px[o11]), Float(px[o11 + 1]), Float(px[o11 + 2]), Float(px[o11 + 3])) / 255
        let top = p00 + (p10 - p00) * wx
        let bot = p01 + (p11 - p01) * wx
        return top + (bot - top) * wy
    }

    /// Couleur LINÉAIRE d'un texel du corps (étapes 1 à 15, cf. Docs/COAT.md et `_compose_band` en Python).
    static func shadeTexel(_ t: CoatTexelInput, _ P: CoatPalette, _ LM: CoatLandmarks) -> SIMD3<Float> {
        let rid = t.rid
        let isHead = rid == 1 || rid == 2 || rid == 3 || rid == 4 || rid == 14
        let isLeg = rid >= 5 && rid <= 8
        let isHoof = rid >= 9 && rid <= 12
        let faceZone = rid == 1 || rid == 2 || rid == 14
        let xu = UInt32(t.x)
        let yu = UInt32(t.y)

        // 1. Base de robe (+ intérieur des oreilles plus clair)
        var c = P.body
        if rid == 4 { c = coatMix(c, P.innerEar, 0.7) }

        // 2. Charbonné (masque A des régions)
        if P.sootyAmount > 0 { c = coatMix(c, P.sooty, P.sootyAmount * t.smask) }
        // 3. Pangaré (masque B)
        if P.pangareAmount > 0 { c = coatMix(c, P.pangare, P.pangareAmount * t.pmask) }
        // 4. Extrémités (masque G ; sur les membres, limitées par la hauteur de jambe)
        var pts = t.ext
        if isLeg {
            pts = t.ext * (1 - coatSmoothstep(P.pointsHeight - 0.06, P.pointsHeight + 0.06, t.leg))
        }
        c = coatMix(c, P.points, P.pointsAmount * pts)

        // 5. Marques primitives dun : raie de mulet (params A) + zébrures des membres
        if P.primitive > 0 {
            let stripe = coatSmoothstep(0.55, 0.85, t.dors)
            var bars: Float = 0
            if isLeg {
                let tt = t.leg * 16 + CoatNoise.valueNoise(t.ux * 30, t.vy * 30, P.sBar) * 0.8
                let fr = tt - tt.rounded(.down)
                let tri = abs(fr * 2 - 1)
                bars = coatSmoothstep(0.55, 0.8, tri) * coatSmoothstep(0.30, 0.40, t.leg)
                    * (1 - coatSmoothstep(0.62, 0.80, t.leg)) * 0.8
            }
            let m = max(stripe, bars)
            c = coatMix(c, P.primitiveColor, P.primitive * m)
        }

        // 6. Pommelures saisonnières (champ A des patterns)
        if P.dapples > 0 {
            let w: Float = isHead ? 0.25 : (isLeg ? coatSmoothstep(0.45, 0.85, t.leg) : 1)
            let d = coatSmoothstep(0.40, 0.70, t.fD)
            let f = 1 + P.dapples * w * (d * 0.32 - 0.16)
            c = c * f
        }

        // 7. Gris progressif (fer -> pommelé -> clair -> truité)
        if P.greyStage > 0 {
            let speed: Float = isHead ? 1.3 : (isLeg ? 0.55 + 0.45 * t.leg : 1)
            let gi = min(P.greyStage * speed, 1)
            let grain = CoatNoise.hash01(xu, yu, P.sGrey)
            let cov = coatSmoothstep(0.0, 0.40, gi + (grain - 0.5) * 0.30)
            let ds = P.greyDapples * coatSmoothstep(0.22, 0.42, gi) * (1 - coatSmoothstep(0.58, 0.82, gi))
            let lt = coatClamp01(gi * 1.30 - 0.30 + ds * (t.fD - 0.5) * 1.4 + (grain - 0.5) * 0.10)
            let gcol = coatMix(P.greyDark, P.greyLight, lt)
            c = coatMix(c, gcol, cov)
            if P.fleabitten > 0 {
                let fl = P.fleabitten * coatSmoothstep(0.55, 0.90, gi)
                let n = CoatNoise.valueNoise(t.ux * 380, t.vy * 380, P.sFlea) * 0.75
                    + CoatNoise.hash01(xu, yu, P.sFlea2) * 0.25
                let th = 1 - fl * 0.30
                let k = coatSmoothstep(th, th + 0.05, n)
                c = coatMix(c, P.fleck, k * 0.85)
            }
        }

        // 8. Rouan (bruit par texel ; tête et bas des membres restent foncés)
        if P.roan > 0 {
            var zone: Float = isHead ? 0.10 : (isLeg ? coatSmoothstep(0.35, 0.75, t.leg) : 1)
            if rid == 2 || rid == 13 || isHoof { zone = 0 }
            let m = CoatNoise.valueNoise(t.ux * 160, t.vy * 160, P.sRoan)
            let n = CoatNoise.hash01(xu, yu, P.sRoan2)
            let rz = P.roan * zone
            let wf = coatClamp01(rz * (0.20 + 0.35 * m) + (n - 0.5) * 0.45 * min(rz * 2, 1))
            c = coatMix(c, P.white, wf)
        }

        // 9. Panachures (champs R/G des patterns, seuils de couverture, bords bruités)
        var wpie: Float = 0
        let legWhiteField: Float = isLeg ? 1 - t.leg : (isHoof ? 1 : 0)
        let headDip: Float = isHead ? 1 - t.fv : 0
        if P.tobiano > 0 {
            let n = CoatNoise.valueNoise(t.ux * 14, t.vy * 14, P.sTob) - 0.5
            wpie = max(wpie, coatCoverMask(t.fA, P.tobiano, 0.012, n * 0.05))
        }
        if P.overo > 0 {
            let n = (CoatNoise.valueNoise(t.ux * 22, t.vy * 22, P.sOv) - 0.5)
                + (CoatNoise.valueNoise(t.ux * 70, t.vy * 70, P.sOv2) - 0.5) * 0.5
            let keep = (1 - coatSmoothstep(0.15, 0.5, t.dors)) * (isLeg ? coatSmoothstep(0.55, 0.95, t.leg) * 0.6 : 1)
            wpie = max(wpie, coatCoverMask(t.fB, P.overo, 0.015, n * 0.10) * keep)
        }
        if P.sabino > 0 {
            let field = max(t.fB * 0.6 + t.pmask * 0.5, legWhiteField * 0.95)
            let n = CoatNoise.hash01(xu, yu, P.sSab) - 0.5
            let m = CoatNoise.valueNoise(t.ux * 40, t.vy * 40, P.sSab2) - 0.5
            wpie = max(wpie, coatCoverMask(field, P.sabino, 0.06, m * 0.10 + n * 0.18))
        }
        if P.splash > 0 {
            let field = max(max(t.pmask * 0.75 + t.fB * 0.25, legWhiteField), headDip)
            let n = CoatNoise.valueNoise(t.ux * 12, t.vy * 12, P.sSpl) - 0.5
            wpie = max(wpie, coatCoverMask(field, P.splash, 0.01, n * 0.03))
        }
        if P.dominantWhite > 0 {
            let field = max(max(t.fB * 0.5 + t.pmask * 0.3 + t.fA * 0.2, legWhiteField * 0.9), headDip * 0.8)
            let n = CoatNoise.valueNoise(t.ux * 18, t.vy * 18, P.sDw) - 0.5
            wpie = max(wpie, coatCoverMask(field, P.dominantWhite, 0.04, n * 0.06))
        }
        c = coatMix(c, P.white, wpie)

        // 10. Complexe léopard (champ B des patterns)
        var lpSkin: Float = 0
        if P.lp > 0 {
            var zoneW: Float
            if P.lpFull > 0 {
                zoneW = isHead ? 0.85 : (isLeg ? 0.6 + 0.4 * coatSmoothstep(0.2, 0.6, t.leg) : 1)
            } else {
                let field = t.smask * 0.75 + t.dors * 0.25
                let n = CoatNoise.valueNoise(t.ux * 20, t.vy * 20, P.sLp) - 0.5
                zoneW = coatCoverMask(field, P.lpCoverage, 0.03, n * 0.12)
                if isHead || isLeg { zoneW = 0 }
            }
            let thr = 1 - P.spotSize * 0.45 - 0.05
            let dsel = CoatNoise.valueNoise(t.ux * 25, t.vy * 25, P.sLpd)
            let sel = coatSmoothstep(1 - P.spotDensity - 0.05, 1 - P.spotDensity + 0.05, dsel)
            let spot = coatSmoothstep(thr, thr + 0.04, t.fS) * sel
            let halo = coatSmoothstep(thr - 0.08, thr, t.fS) * sel
            let white = zoneW * (1 - spot) * (1 - halo * 0.35)
            c = coatMix(c, P.white, white)
            lpSkin = zoneW * (1 - spot)
            if P.varnish > 0 {
                let z2: Float = isHead ? 0.4 : (isLeg ? coatSmoothstep(0.3, 0.8, t.leg) * 0.6 : 1)
                let m = CoatNoise.valueNoise(t.ux * 120, t.vy * 120, P.sVar)
                let n = CoatNoise.hash01(xu, yu, P.sVar2)
                let vz = P.varnish * z2
                let wf = coatClamp01(vz * (0.4 + 0.8 * m) + (n - 0.5) * 0.5 * vz)
                c = coatMix(c, P.white, wf * 0.85)
            }
        }

        // 11. Marques de tête et de membres
        var wm: Float = 0
        if faceZone && P.hasFaceMarking {
            wm = faceMark(P, LM, t.fu, t.fv, rid)
        }
        if isLeg {
            let li = rid - 5
            if P.legHeight[li] > 0 {
                wm = max(wm, legMark(P, LM, t.leg, t.ux, t.vy, li))
            }
        }
        c = coatMix(c, P.white, wm)

        // 12. Peau nue (canal B du shading) : foncée, rose sous le blanc, marbrée (léopard), tachetée (champagne)
        if t.skin > 0 {
            let whiteSkin = max(max(wpie, wm), lpSkin * 0.5)
            let pink = max(P.pinkAll, whiteSkin)
            var sk = coatMix(P.skinDark, P.skinPink, pink)
            if P.lpMottle > 0 {
                let m = CoatNoise.valueNoise(t.ux * 90, t.vy * 90, P.sMot)
                sk = coatMix(sk, P.skinPink, coatSmoothstep(0.50, 0.62, m) * 0.85)
            }
            if P.freckles > 0 {
                let m = CoatNoise.valueNoise(t.ux * 240, t.vy * 240, P.sFrk)
                sk = coatMix(sk, P.freckle, coatSmoothstep(0.66, 0.74, m))
            }
            c = coatMix(c, sk, t.skin)
        }

        // 13. Sabots (régions 9-12) : foncés / clairs / rayés
        if isHoof {
            let hi = rid - 9
            let hw = max(max(P.hoofWhite[hi], wpie), P.pinkAll)
            let partial = min(4 * wpie * (1 - wpie) * 1.5, 1)
            let stripeAmt = max(P.hoofStripe[hi], partial)
            let sn = CoatNoise.valueNoise(t.ux * 220, t.vy * 14, P.sHoof)
            let st = coatSmoothstep(0.42, 0.58, sn)
            let light = coatMix(hw, st, stripeAmt)
            var hc = coatMix(P.hoofDark, P.hoofLight, light)
            if P.hoofOverride > 0 { hc = P.hoofOverrideColor }
            c = hc
        }

        // 14. Châtaignes / ergots (région 13)
        if rid == 13 {
            c = coatMix(P.chestnutDark, P.chestnutLight, max(wpie, wm) * 0.6)
        }

        // 15. Détail final : luminance du poil (R du shading, 0,5 neutre) × cavité (G)
        let f = (0.5 + t.lum) * (0.72 + 0.28 * t.cav)
        return c * f
    }

    /// Masque blanc des marques de tête (coordonnées faciales : u 0,5 = ligne médiane, v 0 = bout du nez).
    static func faceMark(_ P: CoatPalette, _ LM: CoatLandmarks, _ fu: Float, _ fv: Float, _ rid: Int) -> Float {
        let s = P.faceSize
        let du = fu - 0.5 - P.faceOffsetU
        let dv = fv - P.faceOffsetV
        let n = (CoatNoise.valueNoise(fu * 28 + 16, fv * 28 + 16, P.sFace) - 0.5) * (P.faceIrregularity * 0.05)
        var m: Float = 0
        let ev = LM.faceEyeV
        let nv = LM.nostrilV
        switch P.faceKind {
        case 1:     // en tête (étoile)
            m = ellipseMask(du, dv - (ev + 0.07), 0.075 * s, 0.065 * s, n)
        case 2:     // liste étroite (étoile + bande fine)
            let star = ellipseMask(du, dv - (ev + 0.07), 0.06 * s, 0.055 * s, n)
            let strip = capsuleMask(du, dv, ev + 0.06, nv + 0.10, 0.022 * s, n)
            m = max(star, strip)
        case 3:     // liste (élargie sur le front, n'atteint pas les yeux)
            let hw = 0.07 * s * (1 + 0.45 * coatSmoothstep(ev - 0.10, ev + 0.10, dv))
            m = capsuleMask(du, dv, ev + 0.16, nv - 0.02, hw, n)
        case 4:     // belle face (déborde sur les yeux)
            let hw = (LM.faceEyeU + 0.06) * s
            m = capsuleMask(du, dv, ev + 0.22, -0.05, hw, n)
        default:
            break
        }
        if P.faceSnip > 0 {
            m = max(m, ellipseMask(du, dv - (nv - 0.02), 0.06 * s, 0.045 * s, n))
        }
        if P.faceLips > 0 && rid == 2 {
            m = max(m, 1 - coatSmoothstep(0.035 * s - 0.01, 0.035 * s + 0.01, fv))
        }
        return m
    }

    @inline(__always)
    static func ellipseMask(_ du: Float, _ dv: Float, _ rx: Float, _ ry: Float, _ n: Float) -> Float {
        let q = (du / rx) * (du / rx) + (dv / ry) * (dv / ry)
        let d = (q.squareRoot() - 1) * min(rx, ry)
        return 1 - coatSmoothstep(-0.006, 0.006, d + n)
    }

    @inline(__always)
    static func capsuleMask(_ du: Float, _ dv: Float, _ top: Float, _ bottom: Float, _ hw: Float,
                            _ n: Float) -> Float {
        let cv = min(max(dv, bottom), top)
        let ddv = dv - cv
        let d = (du * du + ddv * ddv).squareRoot() - hw
        return 1 - coatSmoothstep(-0.006, 0.006, d + n)
    }

    /// Masque blanc de la balzane du membre `li` (0 AG, 1 AD, 2 PG, 3 PD).
    static func legMark(_ P: CoatPalette, _ LM: CoatLandmarks, _ leg: Float, _ ux: Float, _ vy: Float,
                        _ li: Int) -> Float {
        let h = P.legHeight[li]
        let thr = LM.coronet + h * (1 - LM.coronet)
        let n = (CoatNoise.valueNoise(ux * 55, vy * 55, P.sLeg[li]) - 0.5) * 2
        let edge = thr + n * (P.legIrregularity[li] * 0.05)
        var w = 1 - coatSmoothstep(edge - 0.006, edge + 0.006, leg)
        if P.legErmine[li] > 0 {
            let e = CoatNoise.valueNoise(ux * 150, vy * 150, P.sErm[li])
            let spot = coatSmoothstep(0.70, 0.76, e)
                * (1 - coatSmoothstep(LM.coronet + 0.02, LM.coronet + 0.09, leg))
            w = w * (1 - spot)
        }
        return w
    }

    // MARK: - Crins

    /// Albedo RGBA des crins (même taille que `strands`) ; l'alpha des mèches est conservé tel quel.
    public static func composeHair(_ configuration: CoatConfiguration, strands: RGBA8Image) -> RGBA8Image {
        let P = CoatPalette(configuration)
        let sSec = CoatNoise.salted(P.seed, CoatNoise.Salt.secondary)
        let sWht = CoatNoise.salted(P.seed, CoatNoise.Salt.whiteStrand)
        let count = strands.width * strands.height
        var out = [UInt8](repeating: 0, count: count * 4)
        let lut = encodeLUT
        let src = strands.pixels
        for i in 0..<count {
            let o = i * 4
            let lum = Float(src[o]) / 255
            let t = Float(src[o + 1]) / 255
            let rb = UInt32(src[o + 2])
            let r = Float(src[o + 2]) / 255
            var c = P.mane
            if P.maneTipAmount > 0 {
                c = coatMix(c, P.maneTip, P.maneTipAmount * coatSmoothstep(0.30, 1.0, t))
            }
            if P.maneSecondaryFraction > 0 {
                let hs = CoatNoise.hash01(rb, 0, sSec)
                c = coatMix(c, P.maneSecondary, hs < P.maneSecondaryFraction ? 1 : 0)
            }
            if P.maneWhiteFraction > 0 {
                let hw = CoatNoise.hash01(rb, 1, sWht)
                c = coatMix(c, P.maneWhite, hw < P.maneWhiteFraction ? 1 : 0)
            }
            let f = (0.86 + 0.28 * r) * (0.5 + lum)
            c = c * f
            out[o] = lut[encodeIndex(c.x)]
            out[o + 1] = lut[encodeIndex(c.y)]
            out[o + 2] = lut[encodeIndex(c.z)]
            out[o + 3] = src[o + 3]
        }
        return RGBA8Image(width: strands.width, height: strands.height, pixels: out)
    }

    /// Variante qui utilise `maps.hairStrands` ; nil si la texture de mèches est absente.
    public static func composeHair(_ configuration: CoatConfiguration, maps: CoatMaps) -> RGBA8Image? {
        guard let strands = maps.hairStrands else { return nil }
        return composeHair(configuration, strands: strands)
    }

    // MARK: - Iris

    /// Demi-axes de l'iris et de la pupille (fraction de la demi-taille de la texture) [A].
    static let irisRadii = SIMD2<Float>(0.86, 0.74)
    static let pupilRadii = SIMD2<Float>(0.50, 0.19)
    /// Granula iridica : (centre x, centre y, rayon) — 4 sur le bord supérieur, 2 plus petits en bas [A].
    static let granula: [(Float, Float, Float)] = [(-0.27, -0.17, 0.075), (-0.10, -0.18, 0.095),
                                                   (0.08, -0.18, 0.09), (0.24, -0.17, 0.07),
                                                   (-0.12, 0.17, 0.05), (0.10, 0.17, 0.045)]

    /// Texture d'iris : iris centré, pupille horizontale, granula iridica, sclère hors de l'iris.
    /// `detail` : carte grise optionnelle (canal R, 0,5 neutre) ; nil = fibres procédurales.
    public static func composeIris(_ configuration: CoatConfiguration, detail: RGBA8Image? = nil,
                                   resolution: Int = CoatCompositor.irisResolution) -> RGBA8Image {
        let size = max(resolution, 1)
        let IP = CoatIrisPalette(configuration)
        var dTables: (CoatAxisTable, CoatAxisTable)?
        if let d = detail, d.width > 0, d.height > 0 {
            dTables = (CoatAxisTable(mapSize: d.height, outSize: size), CoatAxisTable(mapSize: d.width, outSize: size))
        }
        var out = [UInt8](repeating: 255, count: size * size * 4)
        let lut = encodeLUT
        let fsize = Float(size)
        for y in 0..<size {
            for x in 0..<size {
                let px = ((Float(x) + 0.5) / fsize - 0.5) * 2
                let py = ((Float(y) + 0.5) / fsize - 0.5) * 2
                let qx = px / irisRadii.x
                let qy = py / irisRadii.y
                let ri = (qx * qx + qy * qy).squareRoot()
                let ox = px / pupilRadii.x
                let oy = py / pupilRadii.y
                let rp = (ox * ox + oy * oy).squareRoot()
                let ax = abs(px)
                let ay = abs(py)
                let pa = py / (ax + ay + 1e-6)
                let ang = px >= 0 ? pa + 1 : 3 - pa             // pseudo-angle « diamant » dans [0, 4)
                let fiber = CoatNoise.valueNoise(ang * 40, ri * 6 + 16, IP.sIris, periodX: 160)
                var base = IP.base
                if IP.vairon > 0 {
                    let sv = CoatNoise.valueNoise(ang * 1.5, 16.5, IP.sVair, periodX: 6) + (fiber - 0.5) * 0.3
                    base = coatMix(base, IP.blue, coatSmoothstep(0.44, 0.64, sv))
                }
                let shade: Float
                if let d = detail, let tables = dTables {
                    let v = d.pixels.withUnsafeBufferPointer { b -> SIMD4<Float> in
                        withExtendedLifetime(tables) { bilinear4(b.baseAddress!, d.width, tables.1.view, tables.0.view, x, y) }
                    }
                    shade = 0.5 + v.x
                } else {
                    let coll = 1 + 0.25 * (coatSmoothstep(0.30, 0.42, ri) * (1 - coatSmoothstep(0.42, 0.60, ri)))
                    shade = (0.62 + 0.62 * fiber) * coll
                }
                let limbal = 1 - 0.55 * coatSmoothstep(0.80, 1.0, ri)
                let blueBoost = 1 + IP.blueFibers * 0.35 * (fiber - 0.5)
                var c = base * (shade * limbal * blueBoost)
                var g: Float = 0
                let gn = CoatNoise.valueNoise(px * 14 + 16, py * 14 + 16, IP.sGran) - 0.5
                for k in granula {
                    let dx = px - k.0
                    let dy = (py - k.1) * 1.3
                    let d = (dx * dx + dy * dy).squareRoot() / k.2
                    g = max(g, 1 - coatSmoothstep(0.80, 1.0, d + gn * 0.3))
                }
                c = coatMix(c, IP.granula * (0.8 + 0.4 * fiber), g)
                let pupil = 1 - coatSmoothstep(0.96, 1.04, rp)
                c = coatMix(c, IP.pupil, pupil)
                let scl = coatSmoothstep(0.98, 1.03, ri)
                c = coatMix(c, IP.sclera, scl)
                let o = (y * size + x) * 4
                out[o] = lut[encodeIndex(c.x)]
                out[o + 1] = lut[encodeIndex(c.y)]
                out[o + 2] = lut[encodeIndex(c.z)]
                out[o + 3] = 255
            }
        }
        return RGBA8Image(width: size, height: size, pixels: out)
    }
}

/// Entrées échantillonnées d'un texel du corps (canaux du SPEC §4, 0…1).
struct CoatTexelInput {
    var lum: Float, cav: Float, skin: Float
    var ext: Float, pmask: Float, smask: Float
    var leg: Float, fu: Float, fv: Float, dors: Float
    var fA: Float, fB: Float, fS: Float, fD: Float
    var rid: Int
    var x: Int, y: Int
    var ux: Float, vy: Float
}

/// Table d'échantillonnage d'un axe (identique à `_axis_tables` en Python) :
/// f = clamp((o + 0,5)·(taille carte / taille sortie) − 0,5, 0, taille − 1) ; plus proche voisin = Int((o + 0,5)·échelle).
/// Mémoire allouée manuellement (libérée dans `deinit`) pour que la boucle par texel n'ait aucun comptage de
/// références : elle utilise `view` (pointeurs nus) sous `withExtendedLifetime`.
final class CoatAxisTable {
    let count: Int
    let i0: UnsafeMutablePointer<Int32>
    let i1: UnsafeMutablePointer<Int32>
    let w: UnsafeMutablePointer<Float>
    let nearest: UnsafeMutablePointer<Int32>

    init(mapSize: Int, outSize: Int) {
        let n = max(outSize, 0)
        count = n
        i0 = UnsafeMutablePointer<Int32>.allocate(capacity: max(n, 1))
        i1 = UnsafeMutablePointer<Int32>.allocate(capacity: max(n, 1))
        w = UnsafeMutablePointer<Float>.allocate(capacity: max(n, 1))
        nearest = UnsafeMutablePointer<Int32>.allocate(capacity: max(n, 1))
        let scale = Float(mapSize) / Float(max(outSize, 1))
        let last = Float(max(mapSize - 1, 0))
        for o in 0..<n {
            let pos = Float(o) + 0.5
            var f = pos * scale - 0.5
            f = min(max(f, 0), last)
            let a = Int(f.rounded(.down))
            i0[o] = Int32(a)
            i1[o] = Int32(min(a + 1, max(mapSize - 1, 0)))
            w[o] = f - Float(a)
            nearest[o] = Int32(min(Int(pos * scale), max(mapSize - 1, 0)))
        }
    }

    deinit {
        i0.deallocate()
        i1.deallocate()
        w.deallocate()
        nearest.deallocate()
    }

    /// Vue sans comptage de références (valide tant que la table est vivante).
    var view: CoatAxisView {
        CoatAxisView(i0: UnsafePointer(i0), i1: UnsafePointer(i1), w: UnsafePointer(w), nearest: UnsafePointer(nearest))
    }
}

/// Pointeurs nus d'une `CoatAxisTable`.
struct CoatAxisView {
    let i0: UnsafePointer<Int32>
    let i1: UnsafePointer<Int32>
    let w: UnsafePointer<Float>
    let nearest: UnsafePointer<Int32>
}
