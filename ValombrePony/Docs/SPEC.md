# ValombrePony — Spécification technique (contrat pipeline ⇄ runtime)

Version 1 — 2026-10-05. Ce document est le **contrat** entre le pipeline de génération (Python/Blender, dossier `Pipeline/`)
et le runtime Swift (`PonyKit/`). Tout nom (joint, blend shape, clip, pièce, matériau, fichier) cité ici est figé :
le changer exige de mettre à jour les deux côtés.

Légende des sources : les choix marqués **[R]** s'appuient sur la recherche documentée (`Docs/RESEARCH_NOTES.md`),
**[I]** sont des choix d'ingénierie, **[A]** des approximations artistiques non sourcées.

---

## 0. Cible et contraintes

- Moteur : **RealityKit**, déploiement **iOS 26 / macOS 26** ; SwiftUI (`RealityView`).
- Réalisme : PBR (metallic workflow), poney générique type Welsh B / Connemara 1,30 m au garrot, morphologie réglable
  jusqu'à un type Shetland ~1,00 m.
- Tout est **jouable** : squelette complet, runtime d'animation maison qui écrit la pose à chaque frame,
  couches procédurales, couleurs et accessoires modifiables à l'exécution.
- Aucun outil Apple n'est disponible dans l'environnement de génération : les USDZ sont écrits avec `pxr` (usd-core)
  et validés par le vérificateur ARKit d'OpenUSD v26.05 (vendorisé) + `UsdValidation` + une vérification numérique du skinning.

### Pourquoi un runtime d'animation maison [R]
- `SkeletalPosesComponent` (iOS 18+) permet d'**écrire** la pose complète à chaque frame (documenté, WWDC24 10102).
- Quand un clip RealityKit joue, il **écrase** les écritures manuelles de joints et de blend shapes (doc `jointTransforms`
  + retours forum). L'ordre des systèmes intégrés n'est pas documenté.
- Les graphes d'animation, masques, root motion natifs sont **iOS 27** uniquement.
- ⇒ PonyKit **ne joue aucun clip RealityKit** : il échantillonne ses propres clips (`PonyClips.bin`), mélange,
  ajoute le procédural, puis écrit `SkeletalPosesComponent` + `BlendShapeWeightsComponent`. Rien ne l'écrase.

---

## 1. Conventions

| Sujet | Blender (modélisation) | USD / RealityKit (export & runtime) |
|---|---|---|
| Unités | mètres | mètres (`metersPerUnit = 1`) |
| Haut | +Z | +Y (`upAxis = "Y"`) |
| Avant du poney (nez) | **+Y** | **−Z** |
| Droite du poney | +X | +X |
| Sol | z = 0 | y = 0 |
| Origine | au sol, au centre du polygone d'appui des 4 sabots (debout carré) | idem |

Conversion Blender → RealityKit (rotation propre, det = +1) : **(x, y, z)_B → (x, z, −y)_RK**.
Matrices : `M_RK = C · M_B · C⁻¹` avec `C = [[1,0,0],[0,0,1],[0,−1,0]]`. Quaternions : conjugués par la même rotation.

Nommage : `snake_case` ASCII, suffixes de côté `_l` / `_r` (gauche/droite **du poney**). Aucun `.`, `[`, `]`, `\`
(contrainte des `GeometricPin` RealityKit [R]). Les tokens USD des joints sont des chemins (`root/body/spine_01/...`) ;
le runtime adresse les joints par **nom court** (dernier segment), unique dans le squelette.

FPS de référence : **30** (`timeCodesPerSecond = framesPerSecond = 30`).

---

## 2. Gabarit morphologique (pose de liaison « debout carré »)

Hauteur au garrot WH = 1,30 m. Angles de repos d'après des mesures sur chevaux (épaule 99°, coude 138°, carpe 178°,
boulet antérieur 143°, grasset 115°, jarret 149°) [R] ; hauteurs articulaires dérivées des indices de poneys
(table « inférée » de la recherche) [R/I]. Valeurs en coordonnées **Blender** (x latéral, y avant, z haut), côté gauche
(x < 0) ; la droite est le miroir en x.

| Repère | Position (m) | Note |
|---|---|---|
| Garrot (sommet des processus épineux) | (0, 0.30, 1.30) | WH |
| Pointe de l'épaule | (±0.17, 0.62, 0.90) | |
| Pointe de la fesse | (±0.10, −0.77, 1.00) | longueur corps ≈ 1.39 m (1.07 WH) [R] |
| Croupe (tuber sacrale) | (0, −0.48, 1.31) | croupe ≈ WH [R] |
| Dessous du thorax (sternum) | (0, 0.30, 0.69) | profondeur ≈ 0.47 WH [R] |
| Bout du nez | (0, 1.27, 1.09) | tête ≈ 0.40 WH, portée à ~45° [R] |

Le pipeline encode ces valeurs dans `Pipeline/pony/template.py` (paramétré par WH) ; ce sont des **points de départ**
à calibrer visuellement (aucune table publiée de centres articulaires de poney n'a été trouvée).

---

## 3. Squelette (70 joints de déformation)

Ordre = ordre USD `Skeleton.joints` = ordre du tableau `joints` de `PonyRig.json` (parents avant enfants).
Tête/queue des os en coordonnées Blender (tête = position du joint).

| # | Joint | Parent | Tête (x,y,z) | Queue | Rôle |
|---|---|---|---|---|---|
| 0 | root | — | (0,0,0) | (0,0.25,0) | référence au sol ; reste identité (le déplacement est porté par l'entité) |
| 1 | body | root | (0,−0.05,0.98) | (0,0.20,0.98) | centre de gravité : rebond, roulis, tangage du tronc |
| 2 | hips | body | (0,−0.42,1.17) | (0,−0.78,1.18) | bassin (pivot lombo-sacré) |
| 3 | tail_01 | hips | (0,−0.80,1.17) | … | 10 os de queue (4 vertèbres + 6 crins), pendants |
| … | tail_02…tail_10 | chaîne | (0,−0.86,1.12) → (0,−0.94,0.36) | (0,−0.94,0.26) | |
| 13 | thigh_l | hips | (−0.13,−0.60,1.03) | grasset | fémur |
| 14 | gaskin_l | thigh_l | (−0.15,−0.42,0.76) | jarret | tibia (« jambe ») |
| 15 | hind_cannon_l | gaskin_l | (−0.12,−0.62,0.42) | boulet | métatarse |
| 16 | hind_pastern_l | hind_cannon_l | (−0.11,−0.60,0.15) | couronne | paturon (P1+P2) |
| 17 | hind_hoof_l | hind_pastern_l | (−0.11,−0.53,0.046) | (−0.11,−0.47,0.0) | sabot (P3) — queue = pince au sol |
| 18–22 | (idem _r) | | miroir | | |
| 23 | spine_01 | body | (0,−0.42,1.17) | (0,−0.14,1.15) | lombes |
| 24 | spine_02 | spine_01 | (0,−0.14,1.15) | (0,0.14,1.11) | dos (zone de selle) |
| 25 | belly | spine_02 | (0,−0.10,0.82) | (0,−0.10,0.70) | ventre (balancement secondaire) |
| 26 | stirrup_l | spine_02 | (−0.17,0.20,1.06) | (−0.20,0.20,0.66) | étrivière/étrier (pendule) |
| 27 | stirrup_r | spine_02 | miroir | | |
| 28 | spine_03 | spine_02 | (0,0.14,1.11) | (0,0.42,0.99) | garrot / thorax avant |
| 29 | scapula_l | spine_03 | (−0.08,0.33,1.20) | épaule | omoplate (glisse/rotation sur le thorax) |
| 30 | upperarm_l | scapula_l | (−0.16,0.58,0.89) | coude | humérus |
| 31 | forearm_l | upperarm_l | (−0.14,0.42,0.71) | carpe | avant-bras |
| 32 | front_cannon_l | forearm_l | (−0.12,0.42,0.35) | boulet | canon |
| 33 | front_pastern_l | front_cannon_l | (−0.115,0.42,0.137) | couronne | paturon |
| 34 | front_hoof_l | front_pastern_l | (−0.115,0.50,0.046) | (−0.115,0.565,0.0) | sabot |
| 35–40 | (idem _r) | | miroir | | |
| 41 | neck_01 | spine_03 | (0,0.46,0.93) | neck_02 | base de l'encolure (C7–T1, basse et profonde [R]) |
| 42–46 | neck_02…neck_06 | chaîne | (0,0.56,1.03) (0,0.65,1.14) (0,0.73,1.25) (0,0.80,1.34) (0,0.86,1.41) | | courbe en S |
| 47 | head | neck_06 | (0,0.91,1.46) | (0,1.27,1.09) | nuque (atlanto-occipitale) |
| 48 | jaw | head | ATM | menton | mâchoire (ouverture, mastication) |
| 49 | lip_lower | jaw | lèvre inf. | | |
| 50 | lip_upper | head | lèvre sup. | | préhension, flehmen |
| 51 | ear_l | head | base oreille | | rotation (orientation du pavillon) |
| 52 | ear_tip_l | ear_l | mi-oreille | pointe | flexion |
| 53–54 | ear_r, ear_tip_r | | | | |
| 55 | eye_l | head | centre de l'œil | | regard |
| 56 | eyelid_upper_l | head | centre de l'œil | | clignement |
| 57 | eyelid_lower_l | head | centre de l'œil | | |
| 58–60 | (idem _r) | | | | |
| 61–63 | forelock_01…03 | head | toupet | | chaîne secondaire |
| 64–69 | mane_01…mane_06 | neck_01…neck_06 (un chacun) | sur la crête | | crinière secondaire |

Les positions fines de la tête (ATM, yeux, oreilles, lèvres) sont placées par le pipeline relativement à l'axe de la tête.
Couplages anatomiques **cuits dans les clips** (RealityKit n'évalue pas les drivers Blender) [R] :
grasset ↔ jarret (appareil réciproque, Δjarret ≈ Δgrasset), boulet/paturon/sabot (« enroulement du doigt »).

### Limites articulaires (procédural & IK) [R/I]
Carpe : flexion ≤ 150° ; boulet antérieur : flexion ≤ 105°, hyperextension ≤ 60° ; paturon+sabot ≈ 50° ;
coude ≈ +65°/−10° ; épaule ≈ +40°/−20° ; hanche ≈ +40°/−25° ; encolure : latéral 25–30° par segment ;
nuque (AO) ≈ 85° de flexion/extension au total ; dos 5–7° par os.

---

## 4. Maillages, matériaux, budgets

Fichier `Pony.usdz` (corps, toujours visible) : un seul `SkelRoot`, un seul `Skeleton`.

| Mesh | Matériau | Budget (triangles) | Notes |
|---|---|---|---|
| `Body` | `M_Coat` | ≈ 30–40 k | corps + sabots + châtaignes/ergots ; UV0 unique ; ≤ 4 influences/vertex |
| `Eyes` | `M_Eye` | ≈ 2 k | globes + cornée (clearcoat) ; skinnés à `eye_l/r` |
| `Mouth` | `M_Mouth` | ≈ 2 k | gencives, incisives, langue (visibles à l'ouverture) |
| `Lashes` | `M_Lashes` | < 500 | cartes alpha (cils + vibrisses) |

Matériaux USD = `UsdPreviewSurface` (metallic workflow), textures PNG, `doubleSided = false`,
`subdivisionScheme = "none"`, normal maps OpenGL (`sourceColorSpace = raw`, scale (2,2,2,1), bias (−1,−1,−1,0)).
RealityKit n'importe pas le double face [R] : le runtime met `faceCulling = .none` sur les matériaux de crins.

Textures du corps (UV0) :

| Fichier | Format | Contenu |
|---|---|---|
| `coat_albedo_default.png` | sRGB 2048² | pelage par défaut (bai, étoile) — remplacé au runtime |
| `coat_normal.png` | raw 2048² | normales (muscles + direction du poil) |
| `coat_orm.png` | raw 2048² | R = occlusion, G = rugosité, B = métal (0) |
| `coat_shading.png` | raw 2048² RGB | R = détail de luminance du poil (0.5 neutre), G = cavité/AO, B = peau apparente (0 poil … 1 peau nue) |
| `coat_regions.png` | raw 1024² RGBA | R = id de région ×16, G = masque « extrémités » (points), B = masque pangaré, A = masque charbonné (sooty) |
| `coat_params.png` | raw 1024² RGBA | R = hauteur de jambe (0 sol → 1 coude/grasset), G = u facial (0.5 = ligne médiane), B = v facial (0 bout du nez → 1 nuque), A = raie de mulet (1 sur la ligne du dos) |
| `coat_patterns.png` | raw 1024² RGBA | R = champ pie A (tobiano), G = champ pie B (overo/sabino/splash), B = champ de taches (léopard), A = champ de pommelures |

IDs de région (`coat_regions.R / 16`) : 0 corps, 1 tête, 2 bout du nez, 3 oreille ext., 4 oreille int.,
5–8 jambes AG/AD/PG/PD, 9–12 sabots AG/AD/PG/PD, 13 châtaignes/ergots, 14 peau péri-oculaire, 15 peau nue ventrale.
La carte de régions est échantillonnée en **plus proche voisin**.

---

## 5. Blend shapes du corps (noms figés)

Formes de morphologie (poids 0…1, jamais négatifs) :

| Nom | Effet |
|---|---|
| `shape_stocky` | tronc plus profond et large, « Shetland » |
| `shape_refined` | lignes fines, poney de sport |
| `shape_fat` / `shape_thin` | état corporel (crête, côtes, base de queue, épaules) |
| `shape_muscular` | relief musculaire |
| `shape_belly` | gros ventre |
| `shape_crest` | encolure rouée/épaisse |
| `shape_bone_heavy` | canons et articulations épais |
| `head_dished` / `head_roman` | chanfrein concave / busqué |
| `head_short` | tête courte, museau fin (pédomorphe) |
| `muzzle_broad` | museau large, naseaux ouverts |
| `hooves_large` | sabots plus grands |

Formes de **proportion** (appariées à des décalages de joints, cf. §9 `morphology`) :
`prop_legs_long`, `prop_legs_short`, `prop_neck_long`, `prop_neck_short`, `prop_body_long`, `prop_body_short`.
Construction : allonger/raccourcir les os en pose de liaison, évaluer la déformation, stocker le delta ;
le runtime applique **le même poids** au blend shape et aux décalages de translation des joints ⇒ cohérent en toute pose.

Expressions : `face_nostril_flare`, `face_flehmen`, `face_brow_worry`, `face_mouth_open_soft`, `body_breathe`.

Taille globale = échelle de l'entité ; taille de la tête / des oreilles / des yeux = échelle des joints `head`, `ear_*`, `eye_*`.

**Toute pièce qui épouse le corps (crins, couvertures, tapis, selle, guêtres…) porte les blend shapes du corps
qui la concernent, avec les mêmes noms** (transfert par Surface Deform pour les formes, par déformation d'armature
pour les proportions). Le runtime applique les poids par nom à chaque entité.

---

## 6. Pièces (`parts`) : crins et accessoires

Chaque pièce est un **USDZ séparé** (`Parts/<id>.usdz`) avec **une copie du squelette complet** (mêmes tokens, même
ordre, mêmes bindTransforms). Le runtime écrit la même pose dans le `SkeletalPosesComponent` de chaque pièce visible
(enfant de l'entité poney, transform identité). Raison : les meshes sous un même SkelRoot fusionnent en un seul
`ModelComponent` et ne peuvent pas être masqués individuellement [R, communauté].

Matériaux personnalisables d'une pièce : `slot_primary`, `slot_secondary`, `slot_accent`, `slot_metal`
(+ `fixed_*` non personnalisables). Les albedos sont des détails en niveaux de gris teintés au runtime
(`baseColor.tint`) ; les tissus acceptent un motif (uni, rayures, carreaux, étoiles, cœurs) composé au runtime.

| id | Catégorie | Emplacement | Slots | Exclusions / prérequis |
|---|---|---|---|---|
| `mane_natural` | crins | `mane` | couleur crins | — |
| `mane_braided` | crins | `mane` | couleur crins | — (remplace la crinière libre) |
| `mane_roached` | crins | `mane` | couleur crins | (crinière rasée courte) |
| `forelock_natural` / `forelock_braided` | crins | `forelock` | couleur crins | |
| `tail_natural` / `tail_braided` | crins | `tail` | couleur crins | |
| `feathers` | crins | `feathers` | couleur crins | fanons (option) |
| `saddle_english` | sellerie | `saddle` | cuir, siège, accent, métal | exclut `rug_stable`, `fly_sheet` |
| `saddle_western` | sellerie | `saddle` | cuir, siège, accent (coutures), métal | idem |
| `saddle_pad_english` | sellerie | `pad` | tissu, passepoil, galon | requiert `saddle_english` |
| `saddle_pad_western` | sellerie | `pad` | tissu, bordure | requiert `saddle_western` |
| `bridle_snaffle` | sellerie | `headgear` | cuir, frontal, métal | exclut `halter` ; inclut mors + rênes |
| `halter` | sellerie | `headgear` | sangles, métal, longe | exclut `bridle_snaffle` ; inclut longe |
| `breastplate` | sellerie | `breastplate` | cuir, métal | requiert une selle |
| `boots_brushing` | protections | `legs_front`, `legs_hind` | coque, sangles, doublure | exclut `bandages` |
| `boots_bell` | protections | `hooves_front` | coque | compatible bandes et guêtres |
| `bandages` | protections | `legs_front`, `legs_hind` | tissu | exclut `boots_brushing` |
| `fly_bonnet` | protections | `ears` | tricot, galon | se porte avec `bridle_snaffle` ou `halter` |
| `ribbons_mane` | décoratif | `mane_deco` | ruban | requiert `mane_braided` |
| `pompons` | décoratif | `mane_deco` | laine | requiert `mane_braided` |
| `flowers` | décoratif | `head_deco` | fleurs, feuillage | — |
| `plume` | décoratif | `head_deco` | plumes, attache | requiert `bridle_snaffle` ou `halter` |
| `tail_bow` | décoratif | `tail_deco` | ruban | masqué par `rug_stable`/`fly_sheet` (rabat de queue) |
| `rug_stable` | couvertures | `rug` | tissu, bordure, sangles | exclut selle, `quarter_sheet` |
| `fly_sheet` | couvertures | `rug` | maille, bordure | idem |
| `quarter_sheet` | couvertures | `quarter` | tissu, bordure | requiert une selle |

Les règles d'exclusion/prérequis sont dupliquées dans `PonyRig.json` (`parts[].conflicts`, `parts[].requires`) et
appliquées par `PonyCore.AccessoryRules`.

---

## 7. Clips d'animation

Tous les clips sont **en place** (le `root` reste à l'identité) ; la vitesse de déplacement de référence est dans le
manifeste (`rootVelocity` m/s en espace poney, `rootYawRate` rad/s). Phase de foulée normalisée : 0 = poser du postérieur
gauche [R]. Vitesses de référence pour un poney 1,30 m, dérivées d'études chevaux mises à l'échelle (nombre de Froude) [R/I].

| Clip | Boucle | Durée cible | Vitesse | Notes |
|---|---|---|---|---|
| `idle` | oui | ~6 s | 0 | transferts de poids subtils |
| `idle_rest_hind` | oui | ~6 s | 0 | postérieur gauche au repos (pince au sol, hanche basse) [R] |
| `walk` | oui | ~1.05 s | 1.4 | 4 temps PG→AG→PD→AD, retard latéral ≈ 0.22 de foulée, appui ≈ 0.62 [R] |
| `trot` | oui | ~0.66 s | 3.0 | diagonaux, appui < 0.5, temps de suspension [R] |
| `canter_left` / `canter_right` | oui | ~0.57 s | 4.8 | 3 temps + suspension [R] |
| `gallop` | oui | ~0.46 s | 8.0 | transverse, pied gauche [A pour les phases] |
| `back` | oui | ~1.2 s | −0.6 | diagonal 2 temps [R] |
| `turn_left` / `turn_right` | oui | ~1.4 s | 0, ±1.2 rad/s | pivot sur les hanches [R] |
| `jump_takeoff` | non | ~0.5 s | — | appel : antérieurs puis postérieurs |
| `jump_air` | oui (tenue) | ~0.4 s | — | planer, membres repliés, bascule |
| `jump_land` | non | ~0.6 s | — | réception sur l'antérieur meneur |
| `graze_down` / `graze_loop` / `graze_up` | non/oui/non | 1.5 / ~5 / 1.2 s | 0 | |
| `rear` | non | ~2.6 s | 0 | |
| `head_shake` | non | ~1.2 s | — | **masque haut du corps** (jouable en marchant) |
| `neigh` | non | ~2.2 s | — | masque haut du corps + flancs |
| `paw` | oui | ~1.6 s | 0 | antérieur droit |
| `lie_down` / `lying` / `get_up` | non/oui/non | ~3 / ~6 / ~2.5 s | 0 | |
| `roll` | non | ~4.5 s | 0 | depuis `lying` |
| `body_shake` | non | ~1.5 s | 0 | ébrouement |

**Approximations assumées [A]** : les durées et chorégraphies du saut, des comportements (coucher, roulade, cabrer…),
les amplitudes de hochement de tête et du port de queue n'ont pas pu être vérifiées (quota de recherche épuisé) ; elles sont
authored « à l'œil » d'après des connaissances générales, et doivent être relues sur vidéo de référence.

Évènements (`clips[].events`) : `foot_down_<fl|fr|hl|hr>`, `foot_up_*`, `takeoff`, `apex`, `landing`, `chew`, `snort`.

---

## 8. Couches procédurales (runtime)

Ordre d'évaluation par frame :
1. Pose de repos → clips (machine d'états de locomotion + comportements, fondus synchronisés en phase).
2. Couches masquées (`head_shake`, `neigh`) au-dessus de la locomotion.
3. Proportions (décalages de translation des joints) et échelles (tête, oreilles, yeux).
4. Inclinaison en virage (roulis du tronc) + incurvation (colonne/encolure vers l'intérieur).
5. Regard (`lookAt`) : répartition lacet/tangage sur `neck_03…neck_06` + `head`, limites, poids de fondu ; yeux.
6. Oreilles : attentives (vers la cible), indépendantes (pivotements aléatoires), couchées (humeur), détendues.
7. Clignements (paupières), respiration (`body_breathe`, `face_nostril_flare` selon l'effort).
8. Physique secondaire (ressorts amortis) : queue (+ chasse-mouches), crinière, toupet, ventre, étriers.
9. Surcharges manuelles de joints (API publique) — « toutes les articulations sont pilotables ».

---

## 9. Formats runtime

### `PonyRig.json`
```json
{
  "format": "ValombrePonyRig", "version": 1, "units": "m", "upAxis": "Y", "forward": "-Z", "fps": 30,
  "joints": [ { "name": "root", "path": "root", "parent": -1,
                "rest": { "t": [0,0,0], "r": [0,0,0,1], "s": [1,1,1] },
                "bindModel": [16 floats, column-major] } ],
  "blendShapes": { "body": ["shape_stocky", "..."] },
  "parts": [ { "id": "saddle_english", "file": "Parts/saddle_english.usdz", "category": "tack",
               "slot": "saddle", "materialSlots": ["slot_primary","slot_secondary","slot_accent","slot_metal"],
               "fabricSlots": [], "blendShapes": ["shape_fat", "..."],
               "conflicts": ["rug_stable","fly_sheet"], "requires": [], "hides": [] } ],
  "clips": [ { "name": "walk", "loop": true, "duration": 1.05, "frameCount": 32,
               "rootVelocity": [0,0,-1.4], "rootYawRate": 0, "mask": null,
               "events": [ { "time": 0.0, "name": "foot_down_hl" } ], "phaseOffset": 0 } ],
  "procedural": { "lookChain": [ {"joint":"neck_03","weight":0.10} ], "ears": {}, "tail": [], "mane": [],
                  "forelock": [], "eyelids": {}, "eyes": [], "jaw": "jaw" },
  "morphology": { "sliders": [ { "id": "legLength", "plus": "prop_legs_long", "minus": "prop_legs_short",
                                  "jointOffsetsPlus": { "front_cannon_l": [0, 0.03, 0] } } ] },
  "coat": { "maps": { "shading": "coat_shading.png" }, "regions": ["body","head","..."] }
}
```
Toutes les données géométriques sont en **espace RealityKit** (Y haut, −Z avant). Quaternions `[x, y, z, w]`.

### `PonyClips.bin` (petit-boutiste)
```
magic "PNYC" | u32 version=1 | u32 clipCount
répété clipCount fois :
  u16 nameLen | name UTF-8 | f32 fps | u32 frameCount | u16 trackCount
  répété trackCount fois :
    u16 jointIndex | u8 flags (bit0 T, bit1 R, bit2 S, bit3 T constant, bit4 R constant, bit5 S constant)
    T : f32×3 ×(1 ou frameCount) | R : f32×4 (x,y,z,w) ×(1 ou frameCount) | S : f32×3 ×(1 ou frameCount)
  u16 weightTrackCount
  répété : u16 nameLen | name | f32 ×frameCount
```
Les joints absents d'un clip gardent la pose de repos (ou la pose de la couche inférieure pour les clips masqués).

---

## 10. Structure USD

```
#usda 1.0  (upAxis="Y", metersPerUnit=1, timeCodesPerSecond=framesPerSecond=30, defaultPrim="Pony")
def Xform "Pony" (kind="component")
    def SkelRoot "Rig"
        def Skeleton "Skel"   (joints = chemins, bindTransforms = monde, restTransforms = local)
        def Mesh "Body"       (SkelBindingAPI, MaterialBindingAPI, elementSize ≤ 4, normalisés, triés)
            def BlendShape "<nom>" (offsets, normalOffsets, pointIndices)
        def Mesh "Eyes" / "Mouth" / "Lashes"
    def Scope "Materials"
```
Validation obligatoire à chaque build : vérificateur ARKit (v26.05 vendorisé) **PASS**, `UsdValidation` 0 erreur,
écart de skinning USD ↔ Blender < 1e-4 m sur 3 poses.

Fichier d'aperçu `Pony_QuickLook.usdz` : corps + crins naturels + filet + selle + pelage par défaut + clip `walk`
en animation par défaut (ouvrable directement dans Aperçu / AR Quick Look sur iPhone/Mac).

---

## 11. Runtime Swift (`PonyKit`)

- `PonyCore` (Swift pur, sans RealityKit, testable) : maths (Vec3/Quat/Transform), manifeste, lecteur de clips,
  échantillonnage/mélange, machine d'états (allures + comportements + saut), procédural, morphologie,
  génétique & compositeur de pelage (tampons RGBA), règles d'accessoires, configuration `Codable`.
- `PonyKit` (RealityKit + SwiftUI) : chargement des USDZ, `PonySystem` (mise à jour par frame),
  écriture `SkeletalPosesComponent` / `BlendShapeWeightsComponent`, application des textures et teintes,
  contrôleur jouable (`CharacterControllerComponent`), caméra suiveuse, vues SwiftUI de démo
  (personnalisation, terrain de jeu avec joystick tactile/clavier).
- Mode de langage Swift 5 dans le package (évite les erreurs de concurrence stricte avec les API RealityKit `@MainActor`).
