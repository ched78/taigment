import Foundation

/// Palette résolue à partir d'une configuration : couleurs LINÉAIRES (float32) et paramètres scalaires
/// saturés, prêts pour la boucle par texel. Traduction ligne à ligne de `palette()` de `coat_reference.py`
/// (calculs en Double puis arrondis en Float, comme Python en float64 puis float32).
struct CoatPalette {
    // Robe
    var white = SIMD3<Float>(0, 0, 0)
    var body = SIMD3<Float>(0, 0, 0)
    var points = SIMD3<Float>(0, 0, 0)
    var pointsAmount: Float = 0
    var pointsHeight: Float = 0
    var sooty = SIMD3<Float>(0, 0, 0)
    var sootyAmount: Float = 0
    var pangare = SIMD3<Float>(0, 0, 0)
    var pangareAmount: Float = 0
    var innerEar = SIMD3<Float>(0, 0, 0)
    var primitive: Float = 0
    var primitiveColor = SIMD3<Float>(0, 0, 0)
    var dapples: Float = 0
    // Gris
    var greyStage: Float = 0
    var greyDapples: Float = 0
    var fleabitten: Float = 0
    var greyDark = SIMD3<Float>(0, 0, 0)
    var greyLight = SIMD3<Float>(0, 0, 0)
    var fleck = SIMD3<Float>(0, 0, 0)
    // Rouan, panachures, léopard
    var roan: Float = 0
    var tobiano: Float = 0
    var overo: Float = 0
    var sabino: Float = 0
    var splash: Float = 0
    var dominantWhite: Float = 0
    var lp: Float = 0
    var lpFull: Float = 0
    var lpCoverage: Float = 0
    var spotDensity: Float = 0
    var spotSize: Float = 0
    var varnish: Float = 0
    // Peau
    var pinkAll: Float = 0
    var skinDark = SIMD3<Float>(0, 0, 0)
    var skinPink = SIMD3<Float>(0, 0, 0)
    var freckle = SIMD3<Float>(0, 0, 0)
    var freckles: Float = 0
    var lpMottle: Float = 0
    // Membres et sabots (AG, AD, PG, PD)
    var legHeight = SIMD4<Float>(0, 0, 0, 0)
    var legIrregularity = SIMD4<Float>(0, 0, 0, 0)
    var legErmine = SIMD4<Float>(0, 0, 0, 0)
    var hoofWhite = SIMD4<Float>(0, 0, 0, 0)
    var hoofStripe = SIMD4<Float>(0, 0, 0, 0)
    var hoofDark = SIMD3<Float>(0, 0, 0)
    var hoofLight = SIMD3<Float>(0, 0, 0)
    var hoofOverride: Float = 0
    var hoofOverrideColor = SIMD3<Float>(0, 0, 0)
    var chestnutDark = SIMD3<Float>(0, 0, 0)
    var chestnutLight = SIMD3<Float>(0, 0, 0)
    // Tête
    var faceKind: Int = 0
    var faceSize: Float = 1
    var faceOffsetU: Float = 0
    var faceOffsetV: Float = 0
    var faceSnip: Float = 0
    var faceLips: Float = 0
    var faceIrregularity: Float = 0
    // Graines salées
    var seed: UInt32 = 0
    var sGrey: UInt32 = 0, sFlea: UInt32 = 0, sFlea2: UInt32 = 0, sRoan: UInt32 = 0, sRoan2: UInt32 = 0
    var sBar: UInt32 = 0, sTob: UInt32 = 0, sOv: UInt32 = 0, sOv2: UInt32 = 0, sSab: UInt32 = 0, sSab2: UInt32 = 0
    var sSpl: UInt32 = 0, sDw: UInt32 = 0, sLp: UInt32 = 0, sLpd: UInt32 = 0, sVar: UInt32 = 0, sVar2: UInt32 = 0
    var sFace: UInt32 = 0, sMot: UInt32 = 0, sFrk: UInt32 = 0, sHoof: UInt32 = 0
    var sLeg = SIMD4<UInt32>(0, 0, 0, 0)
    var sErm = SIMD4<UInt32>(0, 0, 0, 0)
    // Crins
    var mane = SIMD3<Float>(0, 0, 0)
    var maneTip = SIMD3<Float>(0, 0, 0)
    var maneTipAmount: Float = 0
    var maneWhite = SIMD3<Float>(0, 0, 0)
    var maneWhiteFraction: Float = 0
    var maneSecondary = SIMD3<Float>(0, 0, 0)
    var maneSecondaryFraction: Float = 0
    // Yeux
    var iris = CoatIrisPalette()

    /// La face porte-t-elle une marque (sinon le calcul est sauté) ?
    var hasFaceMarking: Bool { faceKind != 0 || faceSnip > 0 || faceLips > 0 }

    init(_ cfg: CoatConfiguration) {
        typealias M = CoatColorMath
        typealias T = CoatColorTable
        let g = cfg.genotype
        let e = cfg.expression
        let ov = cfg.overrides
        func cl(_ v: Float, _ lo: Double = 0, _ hi: Double = 1) -> Double { min(max(Double(v), lo), hi) }
        let shade = cl(e.shade, -1, 1)
        let red = g.extensionLocus == .redOnly
        let agouti = g.agouti
        let cp = g.creamPearl

        // Gènes de dilution actifs (ordre identique à Python).
        var genes: [T.Dilution] = []
        switch cp {
        case .cream: genes.append(.cream)
        case .doubleCream: genes.append(.doubleCream)
        case .pearl: genes.append(.pearl)
        case .creamPearl: genes.append(.creamPearl)
        case .noDilution, .pearlCarrier: break
        }
        if g.silver.isPresent { genes.append(.silver) }
        if g.champagne.isPresent { genes.append(.champagne) }
        let dun = g.dun.isPresent

        func factor(_ slot: T.Slot, includeDun: Bool = true) -> CoatD3 {
            var k = CoatD3(1, 1, 1)
            for gene in genes {
                k = k * M.dilutionFactor(gene, slot)
            }
            if dun && includeDun {
                k = k * M.dilutionFactor(.dun, slot)
            }
            return k
        }

        let white = M.lin(T.whiteHair)
        let euPoints = M.applyDensity(M.lin(T.euPoints), factor(.euPoints, includeDun: false))
        let euMane = M.applyDensity(M.lin(T.euMane), factor(.euMane, includeDun: false))

        var body: CoatD3
        var points: CoatD3
        var pointsAmount: Double
        var mane: CoatD3
        let primitiveColor: CoatD3
        let fleck: CoatD3
        if red {
            let base = M.lin(M.ramp(T.chestnutRamp, shade))
            body = M.applyDensity(base, factor(.pheoBody))
            let bodyNoDun = M.applyDensity(base, factor(.pheoBody, includeDun: false))
            points = M.densify(bodyNoDun, 1.12)
            pointsAmount = 0.35
            mane = M.densify(M.applyDensity(base, factor(.pheoMane, includeDun: false)), 1.08)
            let flax = M.applyDensity(M.lin(T.flaxen), factor(.pheoMane, includeDun: false))
            mane = M.mix(mane, flax, cl(e.flaxen))
            primitiveColor = M.densify(bodyNoDun, 1.25)
            fleck = M.lin(T.fleckRed)
        } else {
            switch agouti {
            case .bay:
                let base = M.lin(M.ramp(T.bayRamp, shade))
                body = M.applyDensity(base, factor(.pheoBay))
                fleck = M.mix(M.lin(T.fleckRed), M.lin(T.fleckBlack), 0.5)
            case .sealBrown:
                let base = M.lin(M.ramp(T.sealRamp, shade))
                body = M.applyDensity(base, factor(.euBody))
                fleck = M.lin(T.fleckBlack)
            case .black:
                let base = M.lin(M.ramp(T.blackRamp, shade))
                body = M.applyDensity(base, factor(.euBody))
                fleck = M.lin(T.fleckBlack)
            }
            points = euPoints
            pointsAmount = 1
            mane = euMane
            primitiveColor = euPoints
        }

        // Surcharges libres : couleur finale du poil, avant modificateurs.
        if let c = ov.body { body = M.lin(c) }
        if let c = ov.points {
            points = M.lin(c)
            pointsAmount = 1
        }

        // Modificateurs
        var sooty = M.densify(body, 1.8)
        if !red { sooty = M.mix(sooty, points, 0.25) }
        let mealy = M.mix(M.densify(body, 0.30), M.lin(T.mealy), 0.4)
        var pangareAmount = cl(e.pangare)
        var pangare = mealy
        if !red && agouti == .sealBrown && ov.body == nil {
            // Bai brun : zones « feu » = pigment rouge du bai, via le masque pangaré.
            let tan = M.applyDensity(M.lin(M.ramp(T.bayRamp, shade - 0.4)), factor(.pheoBay))
            pangare = M.mix(tan, mealy, pangareAmount)
            pangareAmount = max(pangareAmount, 0.55)
        }

        self.white = M.f32(white)
        self.body = M.f32(body)
        self.points = M.f32(points)
        self.pointsAmount = Float(pointsAmount)
        self.pointsHeight = Float(cl(e.pointsHeight))
        self.sooty = M.f32(sooty)
        self.sootyAmount = Float(cl(e.sooty))
        self.pangare = M.f32(pangare)
        self.pangareAmount = Float(pangareAmount)
        self.innerEar = M.f32(M.mix(M.densify(body, 0.55), white, 0.25))
        self.primitive = Float(dun ? cl(e.primitiveMarkings) : 0)
        self.primitiveColor = M.f32(primitiveColor)
        self.dapples = Float(cl(e.dapples))

        let greyOn = g.grey.isPresent
        self.greyStage = Float(greyOn ? cl(e.greyStage) : 0)
        self.greyDapples = Float(cl(e.greyDapples))
        self.fleabitten = Float(greyOn ? cl(e.fleabitten) : 0)
        self.greyDark = M.f32(M.mix(M.lin(T.greyDark), body, 0.2))
        self.greyLight = M.f32(M.lin(T.greyLight))
        self.fleck = M.f32(fleck)

        self.roan = Float(g.roan.isPresent ? cl(e.roanDensity) : 0)
        self.tobiano = Float(g.tobiano.isPresent ? cl(e.tobianoCoverage) : 0)
        self.overo = Float(g.frameOvero.isPresent ? cl(e.overoCoverage) : 0)
        var sab = g.sabino.isPresent ? cl(e.sabinoCoverage) : 0
        if g.sabino == .homozygous { sab = min(1, sab + 0.35) }        // Sb1/Sb1 : quasi blanc [NV]
        self.sabino = Float(sab)
        var spl = g.splashedWhite.isPresent ? cl(e.splashCoverage) : 0
        if g.splashedWhite == .homozygous { spl = min(1, spl + 0.2) }
        self.splash = Float(spl)
        self.dominantWhite = Float(g.dominantWhite.isPresent ? cl(e.dominantWhiteCoverage) : 0)

        let lpCount = g.leopardComplex.alleleCount
        let patn = g.patternOne.isPresent
        self.lp = lpCount > 0 ? 1 : 0
        self.lpFull = (lpCount > 0 && patn) ? 1 : 0                    // léopard / peu taché
        self.lpCoverage = Float(cl(e.leopardCoverage))
        var spotDensity = cl(e.spotDensity)
        if lpCount == 2 { spotDensity *= 0.15 }                         // LP/LP : peu taché [NV]
        self.spotDensity = Float(spotDensity)
        self.spotSize = Float(cl(e.spotSize))
        self.varnish = Float(lpCount > 0 ? cl(e.varnish) : 0)

        // Peau
        var pinkAll: Double = 0
        if cp == .doubleCream || cp == .creamPearl { pinkAll = 1 }
        if self.dominantWhite >= 0.85 { pinkAll = 1 }
        self.pinkAll = Float(pinkAll)
        var skinDark = M.lin(T.skinDark)
        self.freckles = 0
        if g.champagne.isPresent {
            skinDark = M.lin(T.skinChampagne)
            self.freckles = 1
        }
        if let c = ov.skin { skinDark = M.lin(c) }
        self.skinDark = M.f32(skinDark)
        self.skinPink = M.f32(M.lin(T.skinPink))
        self.freckle = M.f32(M.lin(T.freckle))
        self.lpMottle = lpCount > 0 ? 1 : 0

        // Membres et sabots
        for i in 0..<4 {
            let leg = cfg.legs[i]
            let h = cl(leg.height)
            self.legHeight[i] = Float(h)
            self.legIrregularity[i] = Float(cl(leg.irregularity))
            self.legErmine[i] = leg.ermine ? 1 : 0
            self.hoofWhite[i] = h > 0 ? 1 : 0
            var stripe: Float = (h > 0 && (leg.ermine || h < 0.04)) ? 1 : 0
            if lpCount > 0 { stripe = 1 }
            self.hoofStripe[i] = stripe
        }
        self.hoofDark = M.f32(M.lin(T.hoofDark))
        self.hoofLight = M.f32(M.lin(T.hoofLight))
        if let c = ov.hooves {
            self.hoofOverride = 1
            self.hoofOverrideColor = M.f32(M.lin(c))
        } else {
            self.hoofOverride = 0
            self.hoofOverrideColor = SIMD3<Float>(0, 0, 0)
        }
        self.chestnutDark = M.f32(M.lin(T.chestnutHorn))
        self.chestnutLight = M.f32(M.lin(T.chestnutHornLight))

        // Tête
        let face = cfg.face
        switch face.kind {
        case .absent: self.faceKind = 0
        case .star: self.faceKind = 1
        case .strip: self.faceKind = 2
        case .blaze: self.faceKind = 3
        case .baldFace: self.faceKind = 4
        }
        self.faceSize = Float(cl(face.size, 0.3, 2.0))
        self.faceOffsetU = Float(cl(face.offsetU, -0.2, 0.2))
        self.faceOffsetV = Float(cl(face.offsetV, -0.2, 0.2))
        self.faceSnip = face.snip ? 1 : 0
        self.faceLips = face.lips ? 1 : 0
        self.faceIrregularity = Float(cl(face.irregularity))

        // Graines
        let seed = cfg.seed
        typealias S = CoatNoise.Salt
        self.seed = seed
        self.sGrey = CoatNoise.salted(seed, S.grey)
        self.sFlea = CoatNoise.salted(seed, S.flea)
        self.sFlea2 = CoatNoise.salted(seed, S.flea2)
        self.sRoan = CoatNoise.salted(seed, S.roan)
        self.sRoan2 = CoatNoise.salted(seed, S.roan2)
        self.sBar = CoatNoise.salted(seed, S.bar)
        self.sTob = CoatNoise.salted(seed, S.tob)
        self.sOv = CoatNoise.salted(seed, S.ov)
        self.sOv2 = CoatNoise.salted(seed, S.ov2)
        self.sSab = CoatNoise.salted(seed, S.sab)
        self.sSab2 = CoatNoise.salted(seed, S.sab2)
        self.sSpl = CoatNoise.salted(seed, S.spl)
        self.sDw = CoatNoise.salted(seed, S.dw)
        self.sLp = CoatNoise.salted(seed, S.lp)
        self.sLpd = CoatNoise.salted(seed, S.lpd)
        self.sVar = CoatNoise.salted(seed, S.varnish)
        self.sVar2 = CoatNoise.salted(seed, S.varnish2)
        self.sFace = CoatNoise.salted(seed, S.face)
        self.sMot = CoatNoise.salted(seed, S.mottle)
        self.sFrk = CoatNoise.salted(seed, S.freckle)
        self.sHoof = CoatNoise.salted(seed, S.hoof)
        for i in 0..<4 {
            self.sLeg[i] = CoatNoise.salted(seed, S.leg + UInt32(i))
            self.sErm[i] = CoatNoise.salted(seed, S.ermine + UInt32(i))
        }

        // Crins
        let hair = cfg.hair
        var maneC = mane
        if let c = ov.mane { maneC = M.lin(c) }
        self.mane = M.f32(maneC)
        self.maneTip = M.f32(M.mix(maneC, M.lin(T.flaxen), 0.6))
        self.maneTipAmount = Float(cl(hair.tipLightening))
        self.maneWhite = M.f32(M.lin(T.maneWhite))
        var whiteStrands = cl(hair.whiteStrands)
        if greyOn {
            let gs = cl(e.greyStage)
            let t = min(max((gs - 0.05) / 0.70, 0), 1)
            whiteStrands = max(whiteStrands, t * t * (3 - 2 * t))      // les crins grisonnent plus vite [NV]
        }
        if self.dominantWhite >= 0.85 {
            whiteStrands = max(whiteStrands, 0.9)                       // blanc dominant étendu [NV]
        }
        self.maneWhiteFraction = Float(whiteStrands)
        if let sec = hair.secondaryColor {
            self.maneSecondary = M.f32(M.lin(sec))
            self.maneSecondaryFraction = Float(cl(hair.secondaryFraction))
        } else {
            self.maneSecondary = M.f32(maneC)
            self.maneSecondaryFraction = 0
        }

        // Yeux
        self.iris = CoatIrisPalette(cfg)
    }
}

/// Couleur d'œil dérivée.
public enum EyeColorKind: String, Codable, CaseIterable, Sendable {
    case brown, amber, blue, light, vairon

    public var frenchName: String {
        switch self {
        case .brown: return "Brun"
        case .amber: return "Ambre"
        case .blue: return "Bleu"
        case .light: return "Clair"
        case .vairon: return "Vairon"
        }
    }

    /// Règles [NV] (anatomy.md §4.3) : brun par défaut ; bleu avec Cr/Cr, splashed white, belle face très large
    /// ou overo étendu (blanc qui couvre l'œil) ; clair avec Cr/prl ; ambre avec champagne.
    public static func derived(from cfg: CoatConfiguration) -> EyeColorKind {
        switch cfg.irisStyle {
        case .brown: return .brown
        case .amber: return .amber
        case .blue: return .blue
        case .vairon: return .vairon
        case .automatic: break
        }
        let g = cfg.genotype
        if g.creamPearl == .doubleCream { return .blue }
        if g.splashedWhite.isPresent { return .blue }
        if cfg.face.kind == .baldFace && cfg.face.size >= 1.25 { return .blue }
        if g.frameOvero.isPresent && cfg.expression.overoCoverage >= 0.75 { return .blue }
        if g.creamPearl == .creamPearl { return .light }
        if g.champagne.isPresent { return .amber }
        return .brown
    }
}

/// Palette de l'iris (`iris_palette()` en Python).
struct CoatIrisPalette {
    var kind: EyeColorKind = .brown
    var base = SIMD3<Float>(0, 0, 0)
    var blue = SIMD3<Float>(0, 0, 0)
    var vairon: Float = 0
    var pupil = SIMD3<Float>(0, 0, 0)
    var granula = SIMD3<Float>(0, 0, 0)
    var sclera = SIMD3<Float>(0, 0, 0)
    var blueFibers: Float = 0
    var sIris: UInt32 = 0
    var sVair: UInt32 = 0
    var sGran: UInt32 = 0

    init() {}

    init(_ cfg: CoatConfiguration) {
        typealias M = CoatColorMath
        typealias T = CoatColorTable
        let kind = EyeColorKind.derived(from: cfg)
        self.kind = kind
        let baseHex: String
        switch kind {
        case .brown, .vairon: baseHex = T.eyeBrown
        case .amber: baseHex = T.eyeAmber
        case .blue: baseHex = T.eyeBlue
        case .light: baseHex = T.eyeLight
        }
        if let c = cfg.overrides.eyes {
            self.base = M.f32(M.lin(c))
        } else {
            self.base = M.f32(M.lin(baseHex))
        }
        let lp = cfg.genotype.leopardComplex.isPresent
        self.blue = M.f32(M.lin(T.eyeBlue))
        self.vairon = kind == .vairon ? 1 : 0
        self.pupil = M.f32(M.lin(T.pupil))
        self.granula = M.f32(M.lin(T.granula))
        self.sclera = M.f32(M.lin(lp ? T.scleraWhite : T.scleraDark))
        self.blueFibers = (kind == .blue || kind == .light) ? 1 : 0
        self.sIris = CoatNoise.salted(cfg.seed, CoatNoise.Salt.iris)
        self.sVair = CoatNoise.salted(cfg.seed, CoatNoise.Salt.vairon)
        self.sGran = CoatNoise.salted(cfg.seed, CoatNoise.Salt.granula)
    }
}
