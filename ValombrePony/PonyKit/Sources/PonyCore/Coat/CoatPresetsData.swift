// GÉNÉRÉ par `python3 Pipeline/stages/s05_coat.py --swift` à partir de `Pipeline/pony/coat_reference.py`
// (table PRESETS). NE PAS ÉDITER À LA MAIN : modifier la table Python puis régénérer (les vecteurs de
// référence de CoatReferenceVectorsTests en dépendent). Couleurs sous-jacentes : approximations [A].

import Foundation

extension CoatPreset {
    /// 24 présets aux noms français, dans l'ordre d'affichage.
    public static let all: [CoatPreset] = [
        CoatPreset(id: "alezan", name: "Alezan",
                   summary: "e/e — robe rouge uniforme, crins de la même couleur.",
                   configuration: CoatConfiguration.make { c in
                       c.face.kind = .star
                       c.face.size = 0.8
                       c.genotype.extensionLocus = .redOnly
                       c.legs.hindLeft.height = 0.18
                   }),
        CoatPreset(id: "alezan_crins_laves", name: "Alezan crins lavés",
                   summary: "e/e + crins lavés (flaxen, polygénique).",
                   configuration: CoatConfiguration.make { c in
                       c.expression.flaxen = 0.9
                       c.expression.shade = -0.2
                       c.face.kind = .blaze
                       c.genotype.extensionLocus = .redOnly
                       c.hair.tipLightening = 0.2
                       c.legs.hindLeft.height = 0.25
                       c.legs.hindRight.height = 0.12
                   }),
        CoatPreset(id: "alezan_brule", name: "Alezan brûlé",
                   summary: "e/e, nuance foncée (liver) + léger charbonné.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.flaxen = 0.25
                       c.expression.shade = 1.0
                       c.expression.sooty = 0.3
                       c.face.kind = .star
                       c.face.size = 0.6
                       c.genotype.extensionLocus = .redOnly
                   }),
        CoatPreset(id: "bai", name: "Bai",
                   summary: "E/_ A/_ — corps rouge, extrémités noires (préset par défaut).",
                   configuration: CoatConfiguration.make { c in
                       c.face.kind = .star
                   }),
        CoatPreset(id: "bai_brun", name: "Bai brun",
                   summary: "E/_ At/_ — presque noir, zones feu (bout du nez, flancs).",
                   configuration: CoatConfiguration.make { c in
                       c.expression.sooty = 0.3
                       c.genotype.agouti = .sealBrown
                       c.legs.hindRight.height = 0.08
                   }),
        CoatPreset(id: "noir", name: "Noir",
                   summary: "E/_ a/a — eumélanine partout.",
                   configuration: CoatConfiguration.make { c in
                       c.face.kind = .star
                       c.face.offsetV = 0.02
                       c.face.size = 0.7
                       c.genotype.agouti = .black
                   }),
        CoatPreset(id: "palomino", name: "Palomino",
                   summary: "e/e Cr/n — alezan dilué en doré, crins presque blancs.",
                   configuration: CoatConfiguration.make { c in
                       c.face.kind = .blaze
                       c.face.snip = true
                       c.genotype.creamPearl = .cream
                       c.genotype.extensionLocus = .redOnly
                       c.legs.frontLeft.height = 0.15
                       c.legs.hindLeft.height = 0.3
                       c.legs.hindRight.height = 0.3
                   }),
        CoatPreset(id: "isabelle", name: "Isabelle",
                   summary: "E/_ A/_ Cr/n — bai dilué, extrémités noires.",
                   configuration: CoatConfiguration.make { c in
                       c.face.kind = .star
                       c.face.size = 0.6
                       c.genotype.creamPearl = .cream
                   }),
        CoatPreset(id: "souris", name: "Souris",
                   summary: "E/_ a/a D/_ — noir dilué par le dun, marques primitives.",
                   configuration: CoatConfiguration.make { c in
                       c.genotype.agouti = .black
                       c.genotype.dun = .heterozygous
                   }),
        CoatPreset(id: "creme", name: "Crème (cremello)",
                   summary: "e/e Cr/Cr — double dilution : peau rose, yeux bleus.",
                   configuration: CoatConfiguration.make { c in
                       c.face.kind = .blaze
                       c.genotype.creamPearl = .doubleCream
                       c.genotype.extensionLocus = .redOnly
                   }),
        CoatPreset(id: "gris_pommele", name: "Gris pommelé",
                   summary: "G/_ (stade moyen) — pommelures sur base noire.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.greyDapples = 1.0
                       c.expression.greyStage = 0.5
                       c.face.kind = .star
                       c.face.size = 0.7
                       c.genotype.agouti = .black
                       c.genotype.grey = .heterozygous
                   }),
        CoatPreset(id: "gris_truite", name: "Gris truité",
                   summary: "G/_ (stade avancé) — blanc moucheté de poils colorés.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.fleabitten = 0.8
                       c.expression.greyStage = 0.95
                       c.genotype.extensionLocus = .redOnly
                       c.genotype.grey = .heterozygous
                   }),
        CoatPreset(id: "rouan", name: "Rouan (bai)",
                   summary: "E/_ A/_ Rn/_ — poils blancs mêlés, tête et bas des membres foncés.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.roanDensity = 0.7
                       c.face.kind = .star
                       c.face.size = 0.6
                       c.genotype.roan = .heterozygous
                   }),
        CoatPreset(id: "aubere", name: "Aubère",
                   summary: "e/e Rn/_ — rouan sur base alezane.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.flaxen = 0.3
                       c.expression.roanDensity = 0.65
                       c.face.kind = .strip
                       c.genotype.extensionLocus = .redOnly
                       c.genotype.roan = .heterozygous
                       c.legs.hindLeft.height = 0.15
                   }),
        CoatPreset(id: "pie_tobiano", name: "Pie tobiano (bai)",
                   summary: "To/_ — plaques blanches franches qui croisent le dos.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.tobianoCoverage = 0.5
                       c.face.kind = .star
                       c.genotype.tobiano = .heterozygous
                       c.hair.whiteStrands = 0.35
                       c.legs.frontLeft.height = 0.55
                       c.legs.frontRight.height = 0.55
                       c.legs.hindLeft.height = 0.6
                       c.legs.hindRight.height = 0.6
                   }),
        CoatPreset(id: "pie_overo", name: "Pie overo (alezan)",
                   summary: "e/e O/n — blanc horizontal sur les flancs, belle face.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.overoCoverage = 0.5
                       c.face.kind = .baldFace
                       c.face.size = 1.1
                       c.genotype.extensionLocus = .redOnly
                       c.genotype.frameOvero = .heterozygous
                       c.irisStyle = .vairon
                   }),
        CoatPreset(id: "appaloosa_leopard", name: "Appaloosa léopard",
                   summary: "LP/n PATN1/_ — blanc couvert de taches ovales.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.spotDensity = 0.75
                       c.face.kind = .strip
                       c.genotype.leopardComplex = .heterozygous
                       c.genotype.patternOne = .heterozygous
                   }),
        CoatPreset(id: "appaloosa_couverture", name: "Appaloosa couverture",
                   summary: "LP/n — couverture blanche tachetée sur le dos et la croupe.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.leopardCoverage = 0.5
                       c.expression.spotSize = 0.45
                       c.face.kind = .blaze
                       c.face.size = 0.8
                       c.genotype.leopardComplex = .heterozygous
                       c.legs.hindLeft.height = 0.2
                       c.legs.hindRight.height = 0.2
                   }),
        CoatPreset(id: "pangare", name: "Pangaré (type Exmoor)",
                   summary: "E/_ A/_ + pangaré : bout du nez, tour des yeux, ventre clairs ; sans blanc.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.pangare = 0.95
                       c.expression.pointsHeight = 0.35
                       c.expression.shade = 0.2
                       c.expression.sooty = 0.2
                   }),
        CoatPreset(id: "champagne_dore", name: "Champagne doré",
                   summary: "e/e Ch/_ — doré, peau rose tachetée, yeux ambre.",
                   configuration: CoatConfiguration.make { c in
                       c.face.kind = .blaze
                       c.face.size = 0.9
                       c.genotype.champagne = .heterozygous
                       c.genotype.extensionLocus = .redOnly
                       c.legs.frontLeft.height = 0.12
                       c.legs.frontRight.height = 0.12
                   }),
        CoatPreset(id: "silver_noir", name: "Silver (noir)",
                   summary: "E/_ a/a Z/_ — noir dilué en chocolat, crins lavés argentés.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.dapples = 0.6
                       c.face.kind = .star
                       c.genotype.agouti = .black
                       c.genotype.silver = .heterozygous
                   }),
        CoatPreset(id: "bai_dun", name: "Bai dun",
                   summary: "E/_ A/_ D/_ — corps sable, raie de mulet, zébrures.",
                   configuration: CoatConfiguration.make { c in
                       c.face.kind = .star
                       c.face.size = 0.5
                       c.genotype.dun = .heterozygous
                   }),
        CoatPreset(id: "gris_fer", name: "Gris fer",
                   summary: "G/_ (début) — poils blancs mêlés sur base noire.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.greyStage = 0.25
                       c.genotype.agouti = .black
                       c.genotype.grey = .heterozygous
                   }),
        CoatPreset(id: "pie_sabino", name: "Pie sabino (bai)",
                   summary: "Sb1/n — balzanes hautes, liste large, bords rouannés.",
                   configuration: CoatConfiguration.make { c in
                       c.expression.sabinoCoverage = 0.4
                       c.face.kind = .blaze
                       c.face.lips = true
                       c.face.size = 1.3
                       c.genotype.sabino = .heterozygous
                       c.legs.frontLeft.height = 0.6
                       c.legs.frontRight.height = 0.45
                       c.legs.hindLeft.height = 0.7
                       c.legs.hindRight.height = 0.65
                   }),
    ]
}
