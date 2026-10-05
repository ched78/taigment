# Robes du poney — génétique simplifiée, marques, compositeur de pelage

Version 1 — 2026-10-05. Agent « coat ». Ce document décrit le système de robes : modèle génétique simplifié
(génotype → phénotype), marques en tête et balzanes, couleur des crins, des sabots, de la peau et des yeux,
présets aux noms français, et le **compositeur** qui fabrique l'albedo du corps à partir des cartes cuites du
SPEC §4.

Légende (comme le reste du projet) : **[NV]** connaissance non vérifiée dans cette session, **[A]** approximation
artistique sans source, **[I]** choix d'ingénierie, **[R]** appuyé sur la recherche documentée.

> **Statut des sources.** `Docs/research/anatomy.md` §4 (génétique des robes, marques, couleurs) est
> **entièrement [NV]** : la recherche s'est arrêtée avant cette section (quota épuisé) ; elle a été écrite de
> mémoire d'après la littérature primaire citée. **Toutes les valeurs hex sont des approximations artistiques
> [A]** (anatomy.md le dit explicitement) : aucune mesure spectrophotométrique n'a été consultée. La
> nomenclature française (aubère / rouan, souris, crème, termes de marques) reste à vérifier auprès de
> l'IFCE / SIRE. Les formes des panachures et des marques sont des heuristiques [A].

---

## 1. Fichiers

| Fichier | Rôle |
|---|---|
| `Pipeline/pony/coat_reference.py` | **Implémentation de référence numpy** (vérité exécutable) : couleurs, hachage, palette, compositeur (corps, crins, iris), cartes synthétiques, table des présets. |
| `Pipeline/stages/s05_coat.py` | Étape du pipeline : albedos, planches d'aperçu, rendus Cycles, génération du Swift dérivé. |
| `Pipeline/tests/test_coat_reference.py` | Tests Python (unittest) du compositeur de référence sur cartes synthétiques. |
| `Pipeline/tests/test_coat_swift_equivalence.py` + `coat_swift2py.py` | **Équivalence Swift ⇄ Python sans compilateur** : le Swift est traduit mécaniquement en Python float32 et comparé au bit près à la référence (§6). |
| `PonyKit/Sources/PonyCore/Coat/*.swift` | Traduction Swift **ligne à ligne** (Foundation seule, compile aussi sous Linux). |
| `PonyKit/Sources/PonyCore/Coat/CoatPresetsData.swift` | **Généré** depuis la table Python `PRESETS` (ne pas éditer). |
| `PonyKit/Tests/PonyCoreTests/Coat*Tests.swift` | Tests XCTest ; `CoatReferenceVectorsTests.swift` est **généré** (texels calculés par Python). |

Commandes (depuis `ValombrePony/`) :

```bash
python3 Pipeline/stages/s05_coat.py               # albedos + planches (+ rendus Cycles si Pipeline/build/body.blend)
python3 Pipeline/stages/s05_coat.py --no-render   # sans Blender
python3 Pipeline/stages/s05_coat.py --swift       # régénère CoatPresetsData.swift + CoatReferenceVectorsTests.swift
python3 -m unittest Pipeline/tests/test_coat_reference.py Pipeline/tests/test_coat_swift_equivalence.py
python3 Tools/swift_syntax_check.py PonyKit       # syntaxe Swift seulement (pas de compilateur ici)
```

Sorties : `Pipeline/build/textures/coat_albedo_default.png` (2048², bai avec étoile — SPEC §4),
`Pipeline/build/textures/presets/<id>.png` (1024²), `Pipeline/build/textures/iris_default.png` (512²),
`Previews/coat/presets_uv.png`, `Previews/coat/hair_iris.png`, `Previews/coat/presets_render.png`.
(`hair_albedo_default.png` appartient à l'agent « hair » et n'est pas réécrit.)

---

## 2. API Swift (contrat inter-agents de PonyKit)

```swift
let cfg = CoatPreset.named("palomino")!.configuration          // ou CoatConfiguration.default (bai, étoile)
var c = cfg; c.legs.hindLeft.height = 0.3; c.face.kind = .blaze
let albedo = CoatCompositor.composeBody(c, maps: maps, resolution: CoatCompositor.previewResolution) // 1024 en glissant
let final  = CoatCompositor.composeBody(c, maps: maps, resolution: CoatCompositor.finalResolution)   // 2048 au relâcher
let mane   = CoatCompositor.composeHair(c, strands: maps.hairStrands!)   // alpha des mèches conservé
let iris   = CoatCompositor.composeIris(c)                                // 512²
let ph = c.phenotype   // bodyColor, maneColor, eyeColor, hooves (.dark/.light/.striped/.custom), pinkSkin…
```

- `PonyColor` : sRGB 0…1, `init(hex:)` (invalide → noir), `hexString`, `linear`, `mix` (en sRGB), `init(linear:)`.
- `RGBA8Image` : RGBA 8 bits, rangées de haut en bas.
- `CoatConfiguration` (Codable/Equatable/Hashable/Sendable) : `genotype`, `expression`, `face`, `legs`, `hair`,
  `irisStyle`, `overrides` (mode libre), `seed`. `plain` = bai sans marque ; `default` = bai avec étoile.
  Contient aussi la couleur des crins / sabots / yeux (dérivées, ou forcées via `overrides`).
- `CoatMaps` : les 4 cartes du SPEC §4 + `hairStrands` + `irisDetail` optionnels + `landmarks`.
  `CoatMaps.synthetic(size:)` fournit des cartes de test.
- `CoatPreset.all` (24 présets), `CoatPreset.named(_:)`.

Le JSON Codable est **partagé** avec Python (mêmes clés ; `PonyColor` = `{"r","g","b"}`) : les vecteurs de
référence décodent en Swift des configurations écrites par Python.

---

## 3. Génotype simplifié (`CoatGenotype`) [NV]

| Locus (gène) | Valeurs | Effet modélisé |
|---|---|---|
| Extension (MC1R) | `E` (E/_), `ee` | e/e : pigment rouge seulement → **alezan**. |
| Agouti (ASIP) | `A`, `At`, `aa` | A : noir cantonné aux extrémités (**bai**) ; At : **bai brun** (zones feu) ; a/a : **noir**. |
| Crème / perle (SLC45A2) | `N/N`, `Cr/N`, `Cr/Cr`, `prl/N`, `prl/prl`, `Cr/prl` | 2 allèles du même gène. Cr/N dilue fort le rouge, à peine le noir ; Cr/Cr dilue tout (peau rose, yeux bleus) ; prl/prl dilue modérément [A] ; Cr/prl ≈ pseudo-double dilution (peau rose, yeux clairs). |
| Dun (TBX3) | Zygosity | Dilue le **corps** (pas les extrémités ni les crins) + marques primitives. |
| Silver (PMEL17) | Zygosity | Dilue le **pigment noir seulement** (chocolat, crins lavés argentés) ; invisible sur un alezan. |
| Champagne (SLC36A1) | Zygosity | Dilue les deux pigments ; peau rose tachetée ; yeux ambre. |
| Gris (STX17) | Zygosity | Grisonnement progressif selon `greyStage` (la peau reste foncée). |
| Rouan (KIT) | Zygosity | Poils blancs mêlés, tête et bas des membres foncés ; stable (pas de progression). |
| Tobiano, overo (frame), sabino, splashed white, blanc dominant | Zygosity + couverture | Panachures (§6). O/O est létal : traité comme O/n. Sb1/Sb1 : +0,35 de couverture ; SW/SW : +0,2 [NV]. |
| Complexe léopard (LP) + PATN1 | Zygosity | LP sans PATN1 → **couverture** ; LP/n + PATN1 → **léopard** ; LP/LP + PATN1 → **peu taché** (densité de taches × 0,15). Marmoré = `varnish`. |

Paramètres d'expression (`CoatExpression`) : nuance `shade` (−1 clair … +1 foncé), charbonné `sooty`, `pangare`,
crins lavés `flaxen` (alezan seulement [NV]), pommelures saisonnières `dapples`, hauteur des extrémités
`pointsHeight`, intensité des marques primitives, gris (`greyStage`, `greyDapples`, `fleabitten`),
`roanDensity`, couvertures des panachures, léopard (`leopardCoverage`, `spotSize`, `spotDensity`, `varnish`).
Un paramètre d'un gène absent est ignoré.

### Couleurs : modèle de dilution par densité optique [I]

Les couleurs de base sont des **rampes** [A] interpolées en sRGB par la nuance (−1, 0, +1) :
alezan `#C8843F / #A65A2A / #5A2E1A`, bai `#B06A32 / #8B4A22 / #5C3018`, bai brun `#5A3420 / #3D2216 / #2A1810`,
noir `#2E2622 / #1A1716 / #0E0D0D` ; extrémités `#17120F`, crins noirs `#141110`, poil blanc `#F3F0EA`.

Chaque dilution est définie par des **paires [A]** « base de référence → couleur diluée » par emplacement
pigmentaire (rouge du corps d'alezan, rouge du corps de bai, crins rouges, noir du corps, extrémités noires,
crins noirs), tirées du tableau d'anatomy.md §4.2 (ex. alezan `#A65A2A` → palomino `#D6AE62`, bai `#8B4A22` →
isabelle `#C6A066`, noir → souris `#7A726A`, noir → silver `#5A4A42`, crins noirs → crins silver `#E0D4C2`).
On en tire, par canal, un facteur de densité `k = D(cible) / D(base)` avec `D(c) = −ln(c_lin / blanc_lin)` ;
il s'applique à n'importe quelle nuance : `c' = blanc · (c / blanc)^k`. Les dilutions **se cumulent** en
multipliant leurs facteurs (dunalino, isabelle dun, champagne crème…) : c'est une extrapolation plausible [I],
pas une mesure. Les paires sont dans `CoatColorTable.swift` / `DILUTION_TARGETS`.

Modificateurs dérivés [A] : charbonné = robe densifiée ×1,8 (mêlée aux extrémités sur base noire) ; pangaré
(« mealy ») = robe éclaircie (densité ×0,3) mêlée à `#E0C89E` ; bai brun : zones feu = rouge du bai plus clair,
appliqué par le masque pangaré (≥ 0,55).

---

## 4. Phénotype dérivé (`CoatPhenotype`) [NV]

- **Crins** : noirs pour bai / isabelle / souris / noir (dilués par crème double, silver → lavés, champagne) ;
  comme la robe (un peu plus foncés) pour l'alezan ; crins lavés optionnels (`flaxen`, alezan seulement) ;
  le gris blanchit les crins plus vite que le corps (fraction de mèches blanches = smoothstep(0,05…0,75 du
  stade)) ; blanc dominant étendu → crins blancs ; mèches blanches / secondaires réglables (crins bicolores).
- **Peau** (zones nues, canal B du shading) : foncée `#2B2525` ; **rose `#DCA295` sous tout blanc** (panachures,
  marques, blanc du léopard à 50 %) ; rose partout avec Cr/Cr, Cr/prl, blanc dominant ≥ 0,85 ; marbrée (taches
  roses) avec LP ; champagne : peau rosée `#B88E7E` tachetée de `#5A4038`.
- **Sabots** (régions 9–12) : la corne copie la peau de la couronne — foncés `#2E2A27`, **clairs `#D2C2A0` sous
  une balzane** ou un blanc de panachure, **rayés** si balzane partielle (trace < 0,04), hermine, complexe
  léopard, ou bord de panachure ; couleur forçable (`overrides.hooves`).
- **Yeux** : brun `#4A2E19` par défaut ; **bleu `#8FB7D8`** avec Cr/Cr, splashed white, belle face très large
  (taille ≥ 1,25) ou overo ≥ 0,75 (blanc qui couvre l'œil) ; **clair `#B49A5E`** avec Cr/prl ; **ambre `#B07A2A`**
  avec champagne ; **vairon** au choix (`irisStyle`) ; sclère blanche visible avec LP, sinon pigmentée.
- **Châtaignes / ergots** (région 13) : corne gris-brun foncé, plus claire sur un membre blanc.

Les surcharges libres (`overrides.body/points/mane/hooves/eyes/skin`) remplacent la couleur génétique
correspondante ; les modificateurs, motifs et marques continuent de s'appliquer par-dessus le corps.

---

## 5. Marques

### Tête (`FaceMarking`) — coordonnées faciales du SPEC §4 (`coat_params` G = u, 0,5 = ligne médiane ; B = v, 0 = bout du nez → 1 = nuque)

| Valeur | Nom FR | Forme [A] |
|---|---|---|
| `star` | En tête (étoile) | ellipse 0,075 × 0,065 (× taille) centrée à v = yeux + 0,07 |
| `strip` | Liste étroite | étoile réduite + bande de demi-largeur 0,022 jusqu'au-dessus des naseaux |
| `blaze` | Liste | bande de demi-largeur 0,07 (élargie de 45 % sur le front), du front au bout du nez, sans atteindre les yeux |
| `baldFace` | Belle face | bande de demi-largeur (|u_yeux| + 0,06) × taille : déborde sur les yeux |
| `snip` (option) | Ladre au bout du nez | ellipse entre les naseaux |
| `lips` (option) | Lèvres (« boit dans son blanc ») | région 2, v < 0,035 × taille |

Taille 0,3…2, décalage u/v ±0,2, bord irrégulier (bruit de valeur dans l'espace facial, continu à travers une
éventuelle couture UV de la tête). Appliquées aux régions 1, 2 et 14 (pas aux oreilles).

### Membres (`LegMarking`) — hauteur continue

Seuil en hauteur de jambe : `couronne + h·(1 − couronne)` (couronne = 0,10 par défaut [I], gabarit 1,30 m :
couronne ≈ 0,07 m, coude ≈ 0,71 m). Catégories [I] : `h < 0,04` trace de balzane ; `< 0,11` petite balzane
(jusqu'au boulet ≈ 0,19) ; `< 0,32` balzane (mi-canon) ; `< 0,55` grande balzane (genou / jarret ≈ 0,49 / 0,55) ;
au-delà balzane haut-chaussée. Bord irrégulier (bruit, ±0,05 × irrégularité), **mouchetures d'hermine**
optionnelles près de la couronne (→ sabot rayé). Appliquées aux régions 5–8 (AG, AD, PG, PD) ; le sabot
du même membre (9–12) devient clair.

---

## 6. Compositeur du corps (Swift `CoatCompositor.composeBody` = Python `compose_body`)

### Cartes d'entrée (SPEC §4) — sémantique utilisée

| Carte | R | G | B | A |
|---|---|---|---|---|
| `coat_shading` (2048²) | détail de luminance du poil, **0,5 neutre** (facteur 0,5 + R) | cavité (1 = aucune ; facteur 0,72 + 0,28 G) | peau nue 0…1 | — |
| `coat_regions` (1024², **plus proche voisin pour R**) | id × 16 | extrémités | pangaré | charbonné |
| `coat_params` (1024²) | hauteur de jambe 0 sol → 1 coude/grasset | u facial | v facial | raie de mulet (1 sur le dos) |
| `coat_patterns` (1024²) | champ tobiano | champ overo/sabino/splash | champ de taches | champ de pommelures |

Hypothèses de polarité [I] : les champs de panachure sont **dans [0, 1] et blanchissent d'abord là où ils sont
élevés** (`cover_mask` : couverture 0 → rien, 1 → tout) ; les champs de taches et de pommelures valent ~1 au
centre d'une tache / pommelure. Le masque pangaré sert aussi de champ « ventral » (splash, sabino) et le masque
charbonné de champ « ligne du dos » (couverture du léopard), faute d'une coordonnée dédiée.

Échantillonnage : chaque carte a sa propre résolution ; bilinéaire (texel de sortie au centre, bord saturé),
**plus proche voisin** pour l'id de région. Résolution de sortie paramétrable.

### Étapes par texel (couleur linéaire)

1. **Base** : couleur de robe (intérieur d'oreille, région 4, éclairci).
2. **Charbonné** : `mix(c, sooty, sooty · A_regions)`.
3. **Pangaré** : `mix(c, pangaré, pangaré · B_regions)` (zones feu du bai brun).
4. **Extrémités** : `mix(c, extrémités, G_regions × [membres : 1 − smoothstep autour de pointsHeight])`.
5. **Marques primitives dun** : raie de mulet = smoothstep(0,55, 0,85, A_params) ; zébrures = onde
   triangulaire de la hauteur de jambe (16 périodes, bruitée) entre 0,30 et 0,80.
6. **Pommelures saisonnières** : facteur 1 ± 0,16 selon le champ A des patterns (atténué sur la tête et le bas
   des membres).
7. **Gris** : vitesse ×1,3 tête, ×(0,55 + 0,45 h) membres ; couverture de poils gris par texel (grain) ; teinte
   gris fer → gris clair modulée par la phase pommelée (fenêtre de stade ≈ 0,3…0,7) ; truité : mouchetures de la couleur
   d'origine aux stades avancés.
8. **Rouan** : fraction de poils blancs = densité × zone (tête 0,1, bas des membres → 0) × bruit
   basse fréquence ± **bruit par texel** (hachage entier du texel).
9. **Panachures** : tobiano (champ R, bord net), overo (champ G, bord découpé, ne croise pas le dos, membres
   épargnés), sabino (champ G + ventral + membres, **bord rouanné** par texel), splash (ventral + membres + bas
   de la tête, « trempé »), blanc dominant (combinaison, couverture 1 = tout blanc).
10. **Léopard** : zone blanche (tout le corps avec PATN1, sinon couverture sur la ligne du dos), taches du champ B
    (taille → seuil, densité → sélection basse fréquence), halo mêlé autour des taches, marmoré (poils blancs).
11. **Marques** de tête et de membres (blanc).
12. **Peau nue** : `mix(c, peau, B_shading)` avec peau rose sous le blanc, marbrée (LP), tachetée (champagne).
13. **Sabots** (9–12) : foncé / clair / rayé (bruit anisotrope : étiré selon v de l'UV — orientation à vérifier
    sur les vraies UV), ou couleur forcée.
14. **Châtaignes** (13).
15. **Détail** : `c × (0,5 + R_shading) × (0,72 + 0,28 G_shading)`, puis encodage sRGB 8 bits par table (4096).

### Équivalence Swift ⇄ Python [I]

- Tout le calcul par texel est en `Float` / float32, sans fonction transcendante (seulement + − × ÷, min, max,
  floor, sqrt) ; même ordre d'opérations ; mêmes littéraux.
- Bruit : hachage entier 32 bits « lowbias32 » (`&*`, `^`, `>>`), bruit de valeur à réseau entier ; sels
  identiques par couche ; `seed` de la configuration.
- La palette (pow / log / exp) est calculée en Double puis arrondie : des écarts d'1 ulp de libm sont possibles.
  Les **vecteurs de référence** (`CoatReferenceVectorsTests`, ~50 texels × 31 configurations + moyennes d'image,
  crins, iris avec et sans carte de détail, sommes FNV des cartes synthétiques qui, elles, doivent être
  identiques au bit près) tolèrent ±3 niveaux.
- Les cartes synthétiques (`synthetic_maps` / `CoatMaps.synthetic`) sont calculées en arithmétique entière.
- **Vérification sans compilateur** (`test_coat_swift_equivalence.py`) : un petit transpileur (`coat_swift2py.py`,
  expressions régulières, aucune interprétation manuelle) traduit le code Swift tel qu'écrit — hachage, bruit,
  `CoatPalette.init` + `CoatColorMath` + `CoatColorTable`, `shadeTexel` / marques, échantillonnage bilinéaire,
  `composeHair`, `composeIris`, `CoatIrisPalette`, `EyeColorKind.derived`, cartes synthétiques, `CoatAxisTable` —
  puis l'exécute en float32 : **résultats identiques au bit près** à la référence numpy sur 34 configurations
  (24 présets + 10 cas extrêmes, ~1 600 texels chacun). Une mutation volontaire d'une constante du Swift est
  détectée. Ce n'est pas un compilateur : types, optionnels et API restent vérifiés par relecture seulement ;
  le pilote parallèle de `composeBody` (bandes, pointeurs) et la branche « carte de détail » de l'iris ne sont
  pas traduits (couverts par les vecteurs de référence à exécuter dans Xcode).

### Performance [I] — NON MESURÉE

Une passe unique, palette précalculée, tables bilinéaires par colonne / rangée (pointeurs nus, sans comptage de
références), `DispatchQueue.concurrentPerform` par bandes de 16 rangées. Objectif < 150 ms à 2048² sur un iPhone
récent : **non mesuré** (aucun matériel Apple ni compilateur Swift dans l'environnement de génération). La
référence numpy met ~2,5 s à 2048² (CPU partagé), ce qui ne renseigne pas sur le Swift. Si l'objectif n'est pas
tenu : 1024 pendant le glissement, cache des cartes rééchantillonnées, ou portage en ShaderGraph/Metal (même
formules).

---

## 7. Crins (`composeHair`) et iris (`composeIris`)

**Mèches** (`hair_strands.png`, agent « hair ») : R luminance (0,5 neutre), G racine (0) → pointe (1), B
identifiant par mèche (haché pour choisir les mèches blanches / secondaires), A alpha **conservé**.
`c = crins ; c = mix(c, pointes lavées, tipLightening · smoothstep(0,3, 1, G))` ; mèches secondaires / blanches
(tout ou rien par mèche) ; `c × (0,86 + 0,28 B) × (0,5 + R)`.

**Iris** (512²) : iris centré, demi-axes 0,86 × 0,74 de la demi-taille, pupille horizontale 0,50 × 0,19,
**granula iridica** (4 bosses sur le bord supérieur de la pupille, 2 plus petites en bas), fibres radiales
(bruit périodique sur un pseudo-angle), collerette, anneau limbique, sclère hors de l'iris (blanche avec LP).
Brun / ambre / bleu / clair / vairon (secteur bleu). Carte grise optionnelle (R, 0,5 neutre) à la place des
fibres. **Contrat UV à confirmer** avec l'agent « body » / « kit » : la texture suppose un iris centré dans le
carré UV de l'œil. Une seule texture pour les deux yeux : le vairon est sectoriel (pas un œil de chaque couleur).

---

## 8. Présets (24, noms FR) — génotype simplifié

| id | Nom | Génotype / réglages | Marques |
|---|---|---|---|
| `alezan` | Alezan | e/e | en tête 0,8 ; balzane PG |
| `alezan_crins_laves` | Alezan crins lavés | e/e, flaxen 0,9, nuance −0,2 | liste ; balzanes PG, PD |
| `alezan_brule` | Alezan brûlé | e/e, nuance +1, charbonné 0,3 | petite étoile |
| `bai` | Bai (**défaut**) | E A | en tête |
| `bai_brun` | Bai brun | E At, charbonné 0,3 | trace PD |
| `noir` | Noir | E aa | petite étoile |
| `palomino` | Palomino | e/e Cr/n | liste + ladre ; 3 balzanes |
| `isabelle` | Isabelle | E A Cr/n | petite étoile |
| `souris` | Souris | E aa D | — |
| `creme` | Crème (cremello) | e/e Cr/Cr | liste |
| `gris_pommele` | Gris pommelé | E aa G, stade 0,5 | étoile |
| `gris_truite` | Gris truité | e/e G, stade 0,95, truité 0,8 | — |
| `rouan` | Rouan (bai) | E A Rn, densité 0,7 | petite étoile |
| `aubere` | Aubère | e/e Rn, flaxen 0,3 | liste étroite ; balzane PG |
| `pie_tobiano` | Pie tobiano (bai) | To, couverture 0,5, crins bicolores | étoile ; 4 balzanes hautes |
| `pie_overo` | Pie overo (alezan) | e/e O/n, 0,5 | belle face ; œil vairon |
| `appaloosa_leopard` | Appaloosa léopard | LP/n PATN1 | liste étroite |
| `appaloosa_couverture` | Appaloosa couverture | LP/n, couverture 0,5 | liste ; balzanes PG, PD |
| `pangare` | Pangaré (type Exmoor) | E A, pangaré 0,95, sans blanc | — |
| `champagne_dore` | Champagne doré | e/e Ch | liste ; balzanes AG, AD |
| `silver_noir` | Silver (noir) | E aa Z, pommelures 0,6 | étoile |
| `bai_dun` | Bai dun | E A D | petite étoile |
| `gris_fer` | Gris fer | E aa G, stade 0,25 | — |
| `pie_sabino` | Pie sabino (bai) | Sb1/n, 0,4 | liste large + lèvres ; 4 balzanes hautes |

Règles de race (anatomy.md §4.3) : Shetland — tout sauf tacheté [V] ; Exmoor — bai, bai brun ou dun avec pangaré,
sans blanc [NV]. Les présets ne sont pas liés à une race.

---

## 9. Ce qui est approximatif / non fait

- **Toutes les couleurs [A]** ; génétique [NV] (citations de mémoire dans anatomy.md) ; termes FR à vérifier.
- **Bande cruciale (shoulder bar) du dun : NON implémentée** — les cartes du SPEC §4 n'ont pas de coordonnée
  longitudinale (avant/arrière du corps) permettant de la placer au garrot. Proposition : que l'agent « body »
  l'intègre au canal A de `coat_params` (raie de mulet), ce qui la rendrait automatique.
- **Couverture du léopard** : placée sur la ligne du dos (masque charbonné + raie de mulet) faute de coordonnée
  longitudinale ; une vraie couverture est centrée sur la croupe et les hanches.
- Formes des panachures : heuristiques sur deux champs de bruit (le champ G sert à trois motifs) [A].
- Les bruits « fins » (bords de balzanes, rouan basse fréquence, taches de peau) sont en espace UV : de légères
  discontinuités sont possibles aux coutures UV ; le grain par texel du rouan / gris dépend de la résolution.
- Orientation des rayures des sabots : supposée selon v des UV des sabots [A], à confirmer sur les vraies UV.
- Perle, champignon (mushroom, non modélisé), pommelures saisonnières, phases du gris : formes et teintes [A].
- Performance Swift non mesurée ; tests XCTest non exécutés ici (aucun compilateur) — syntaxe (tree-sitter),
  relecture, et équivalence de la logique par traduction mécanique (ci-dessus).
