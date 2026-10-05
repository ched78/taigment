# Runtime d'animation — `PonyCore`

Version 1 — 2026-10-05. Ce document décrit le cœur Swift du poney jouable (`PonyKit/Sources/PonyCore`, hors
`Coat/`) : architecture, ordre d'évaluation, machine d'états, paramètres réglables et API. Il complète
`Docs/SPEC.md` (contrat pipeline ⇄ runtime) et le contrat d'API Swift partagé entre agents.

Légende : **[R]** appuyé sur la recherche (`Docs/research/*.md`), **[D]** dérivé par calcul, **[I]** choix
d'ingénierie, **[A]** approximation artistique non sourcée (à caler à l'œil / sur vidéo).

---

## 1. Rôle et périmètre

`PonyCore` est du **Swift pur** (Foundation uniquement, compile aussi sous Linux ; aucun `simd`, `RealityKit`,
`os`, `Combine`). Il :

- décode `PonyRig.json` (`PonyRigManifest`) et lit `PonyClips.bin` (`ClipLibrary`) ;
- échantillonne et mélange les clips (locomotion, saut, comportements, couches masquées) ;
- ajoute les couches procédurales (morphologie, inclinaison, plantage des pieds, regard, oreilles,
  clignements, respiration, physique secondaire, surcharges manuelles) ;
- produit à chaque frame un `PonyFrame` : pose **locale** des 70 joints, poids des blend shapes, vitesse et
  lacet souhaités de l'entité, vitesse verticale (saut), évènements ;
- gère la morphologie (curseurs → blend shapes + décalages/échelles de joints), les règles d'accessoires et
  la configuration sauvegardable (`PonyConfiguration`, JSON stable).

`PonyKit` (RealityKit, autre agent) écrit la pose dans `SkeletalPosesComponent` de chaque pièce visible, les
poids dans `BlendShapeWeightsComponent`, et déplace l'entité. **Aucun clip RealityKit n'est joué** (SPEC §0).

### Arborescence

| Dossier | Contenu |
|---|---|
| `Math/` | `PonyMath` (clamp, smoothstep, amortissement exponentiel, vecteurs), `CriticalSpring`, `PonyRandom` (SplitMix64), `Quat`, `Transform` |
| `Rig/` | `PonyRigManifest` (+ `PonyJSONValue`), `PonySkeleton` (index, parents, FK), `PonyRigDefaults` (noms figés du SPEC, valeurs de repli, squelette synthétique) |
| `Animation/` | `ClipLibrary`, lecteur binaire borné, `ClipLibraryError`, `AnimationClip`, `PoseAccumulator` / `ShapeAccumulator` |
| `Locomotion/` | `LocomotionSettings`, `JumpSettings`, `BehaviorSettings`, `LocomotionController` (allures), `MotionController` (couche de base, saut, comportements, couches masquées) |
| `Procedural/` | `ProceduralSettings`, résolution des chaînes (`ProceduralRig`), inclinaison/incurvation, `FootPlanting`, `LookAtLayer`, `EarLayer`, `BlinkLayer`, `BreathLayer`, `SecondaryMotion` |
| `Morphology/` | `MorphologyConfiguration`, `MorphologyEvaluator`, `MorphologyResult`, `MorphologyPreset` |
| `Accessories/` | `AccessorySelection`, `FabricPattern`, `HairStyle`, `AccessoryRules`, `AccessoryIssue`, `PonyPartCatalog` |
| `Configuration/` | `PonyConfiguration` |
| `Runtime/` | `PonyInput`, `PonyAction`, `PonyGait`, `EarMood`, `PonyEvent`, `PonyFrame`, `PonyRuntime` |

---

## 2. Conventions

- **Espace modèle** = repère local de l'entité poney RealityKit : +Y haut, **−Z avant**, +X droite du poney,
  sol y = 0, unités du rig (gabarit 1,30 m au garrot). L'échelle de l'entité (`withersHeight / 1,30`)
  s'applique par-dessus. `lookTarget` et `groundHeightProvider` travaillent dans cet espace.
- **Pose** : transformations locales parent → joint, ordre du tableau `joints` du manifeste ; la racine
  `root` reste à sa pose de repos (rotation C du SPEC §1).
- **`rootVelocity`** : m/s **réels** (échelle de l'entité déjà incluse), exprimée dans les axes du poney
  (avant = −Z), horizontale (`y = 0`).
- **`rootYawRate`** : rad/s autour de +Y, **positif = tourne à gauche**. Entrée `move.x > 0` (droite) ⇒
  lacet négatif.
- **`verticalVelocity`** (ajout au contrat) : m/s, +Y, non nulle seulement pendant le vol d'un saut.
- Axes locaux des os (vérifiés numériquement sur le gabarit, convention de `Pipeline/pony/rig.py`) :
  Y le long de l'os, X = droite du poney au repos. Flexion = rotation autour de X local (SPEC §1).
  Encolure/tête : +X lève le nez. Oreille : +X local = pointe vers l'arrière, +Y local = pavillon tourné vers
  la gauche. Œil et paupières (gabarit actuel, `template.eye_axes`) : Y = axe optique horizontal (33° en avant
  de la latérale [A]), Z = haut, X = axe de la fente palpébrale ; paupière supérieure : −X ferme ;
  inférieure : +X ferme (bord de paupière vers l'avant et vers la pupille, vérifié numériquement).

---

## 3. API publique (résumé)

```swift
let manifest = try PonyRigManifest.decode(from: rigData)
let clips = try ClipLibrary(data: clipsData, manifest: manifest)      // ou ClipLibrary.empty(manifest:)
let runtime = PonyRuntime(manifest: manifest, clips: clips, configuration: .default, seed: 1)
// ou : try PonyRuntime(rigJSON: rigData, clipsBinary: clipsData)

var input = PonyInput()
input.move = SIMD2(stick.x, stick.y)     // x : + droite ; y : + avant, − reculer
input.sprint = shiftPressed
input.jumpPressed = jumpPressedThisFrame // front montant
input.action = .graze                    // une seule frame
let frame = runtime.update(deltaTime: dt, input: input)
```

| Membre | Rôle |
|---|---|
| `configuration` | `PonyConfiguration` ; toute modification recalcule morphologie, échelle et cadence (`didSet`). |
| `lookTarget: SIMD3<Float>?` | cible du regard (espace modèle) ; `nil` = libre (micro-saccades). |
| `setJointOverride(_:rotation:weight:)` | rotation **locale** imposée à un joint, mélangée par slerp (`weight` 0…1) ; `nil` / 0 retire. `clearJointOverrides()`. |
| `groundHeightProvider` | `(point modèle) -> hauteur du sol (modèle)?` ; active l'adaptation des sabots au sol. |
| `earMood: EarMood?` | humeur imposée des oreilles (`attentive`, `independent`, `pinned`, `relaxed`) ; `nil` = automatique. |
| `notifyLanded()` | signale l'atterrissage réel pendant un saut. |
| `usesExternalLanding` | si vrai, `jump_air` est tenu jusqu'à `notifyLanded()` (délai de sécurité). |
| `resetSecondaryMotion()` | après une téléportation. |
| `locomotionSettings`, `jumpSettings`, `behaviorSettings`, `proceduralSettings` | réglages modifiables à chaud. |
| `gait`, `currentAction`, `isAirborne`, `forwardSpeed`, `effort`, `morphology`, `time`, `jointNames`, `blendShapeNames` | état en lecture. |

`PonyFrame` : `localPose`, `blendWeights` (toutes les formes connues, 0…1), `rootVelocity`, `rootYawRate`,
`events`, `gait`, **`verticalVelocity`**, **`isAirborne`**, **`action`** (les trois derniers ajoutés au
contrat initial ; initialiseur public avec valeurs par défaut).

### Intégration côté PonyKit (esquisse)

Attention : dans un fichier qui importe à la fois `RealityKit` et `PonyCore`, `Transform` est ambigu
(`RealityKit.Transform` / `PonyCore.Transform`, ce dernier imposé par le contrat) : qualifier le module.
La cible `PonyKit` du `Package.swift` doit contenir au moins un fichier source pour que `swift build` /
`swift test` passent (dossier actuellement réduit à `Resources/`).

```swift
let f = runtime.update(deltaTime: dt, input: input)
entity.orientation *= simd_quatf(angle: f.rootYawRate * dt, axis: [0, 1, 0])
var step = entity.orientation.act(f.rootVelocity) * dt          // m réels, l'échelle est déjà incluse
step.y += f.verticalVelocity * dt                               // profil balistique du saut
// déplacement par CharacterControllerComponent / moveCharacter ; appeler runtime.notifyLanded()
// au contact du sol si usesExternalLanding = true.
// Pose : f.localPose → SkeletalPosesComponent (même tableau pour chaque pièce visible).
// Formes : f.blendWeights[nom] → BlendShapeWeightsComponent de chaque entité qui porte ce nom.
```

Évènements émis : ceux des clips (`foot_down_*`, `foot_up_*`, `chew`, `snort`, …) et, générés par le
runtime : `takeoff`, `apex`, `landing` (les évènements de même nom des clips sont ignorés pour éviter les
doublons) et `tail_swish` (coup de queue chasse-mouches). `PonyEvent.time` = temps du runtime en fin de frame.

---

## 4. Données d'entrée

### `PonyRig.json`
Décodage **tolérant** (`decodeIfPresent` partout ; clés inconnues ignorées). Formes de l'exporteur
(`Pipeline/pony/runtime_export.py`) prises en charge :
- `joints[].bindModel` = repère **monde** de liaison (16 flottants, colonnes majeures) ;
  `PonyRigManifest.validationIssues()` vérifie FK(repos) ≈ bindModel.
- `parts[].slot` (chaîne ou tableau) et `parts[].slots` ; `fixedMaterials` ; `requires` = « au moins une ».
- `clips[]` : `loop`, `duration`, `frameCount`, `fps`, `rootVelocity`, `rootYawRate`, `mask` (null ou liste
  explicite), `events`, `phaseOffset`, `strideLength`, `strideDuration`, `stridesPerClip`, et `footfalls`,
  `contacts`, `rootPivot` conservés tels quels (`PonyJSONValue`, non exploités en v1).
- `procedural` : `lookChain`, `ears` (`{"left": {"base","tip"}, "right": {…}}` ou clés plates), `eyelids`
  (`upper_l`…), `eyes`, `jaw`, `lips`, `secondary` (`belly`, `stirrups`), `tail`, `mane`, `forelock`.
  Toute chaîne absente retombe sur les noms du SPEC §3.
- `morphology.sliders[]` : `plus`/`minus` peuvent valoir `null` (forme absente du corps → pas de poids).
  Identifiants de l'exporteur acceptés comme alias : `muscular`, `boneHeavy`, `hoovesLarge`, `headProfile`
  (sens inversé : plus = busqué).

### `PonyClips.bin`
Lecteur borné, petit-boutiste, aligné champ par champ sur `read_clips_bin` de l'exporteur. Erreurs typées
(`ClipLibraryError`) : signature, version, troncature, UTF-8, indice de joint hors limites, nombre d'images
ou cadence invalides, valeurs non finies, **octets en trop**. Les rotations sont normalisées et rendues
continues en signe à la lecture.

**Temps** : clip bouclé de F images → période `F / fps` (l'image F, égale à l'image 0, n'est pas stockée :
interpolation de l'image F−1 vers l'image 0, aucun saut) ; non bouclé → `(F − 1) / fps`, temps borné.
La `duration` du manifeste fait foi si présente. Canaux absents = pose de repos (couche de base) ou pose de
la couche inférieure (couches masquées).

### Données manquantes (repli défensif)
- Clip de locomotion absent : vitesses/durées du SPEC §7, pose de repos pour ce clip (le poney se déplace
  quand même).
- Clip de comportement absent : l'action est ignorée (`graze` sans `graze_down` tente `graze_loop`,
  `lieDown` sans `lie_down` tente `lying`).
- Clips du saut absents : la physique du saut fonctionne avec les durées du SPEC, la pose courante est gardée.
- Pas de pièces dans le manifeste : catalogue du SPEC §6 (`PonyPartCatalog.specParts`, copie de l'exporteur).
- `PonyRigDefaults.syntheticManifest()` : squelette généré depuis `Pipeline/pony/template.py` (mêmes repères
  d'os que `rig.py`) pour tests et prototypage ; **ne remplace pas** `PonyRig.json`.

---

## 5. Ordre d'évaluation d'une frame

1. **Entrées** : `dt` borné à [0 ; 0,1] s (NaN → 0) ; zone morte du joystick (0,12) puis remise à l'échelle.
2. **Machine d'états** (`MotionController`) : requête d'action, transitions de mode, saut, mise à jour de la
   locomotion, avance des emplacements de fondu, évènements.
3. **Couche de base** : fondu enchaîné de 4 emplacements au plus (locomotion ou clip) ; la locomotion
   mélange elle-même ses clips (phase commune).
4. **Couches masquées** (`head_shake`, `neigh`) : lerp/nlerp joint par joint selon le masque.
5. **Morphologie** : décalages de translation locale + échelles (tête, oreilles, yeux et paupières).
6. **Inclinaison** du tronc en virage, puis **plantage des pieds** (compensation de l'inclinaison + sol).
7. **Incurvation** de la base de l'encolure.
8. **Regard** (encolure + tête), FK, puis **yeux**.
9. **Oreilles**. 10. **Clignements**, **respiration**. 11. **Physique secondaire**.
12. **Surcharges manuelles** (slerp vers la rotation imposée).
13. Poids de blend shapes : morphologie + pistes de poids des clips ; `body_breathe` / `face_nostril_flare`
    = max(clip, respiration) ; tout borné à [0, 1].

La FK est recalculée 3 à 4 fois par frame (70 joints) ; les chaînes éditées tiennent leur FK à jour
incrémentalement.

---

## 6. Locomotion

### Allures, bandes de vitesse et hystérésis
Vitesse commandée (gabarit 1,30 m) : `y × 4,8 m/s` (galop de travail), `y × 8 m/s` avec `sprint`,
`y × v_back × 1,18` en arrière.

Chaque allure joue son clip à une cadence **bornée à ±18 %** de sa vitesse de référence (`rootVelocity` du
manifeste, repli SPEC §7) : pas [0 ; 1,65], trot [2,46 ; 3,54], galop [3,94 ; 5,66], galop de course
[6,56 ; 9,44] m/s. Sous la bande du pas (et en reculant), le clip est mélangé avec `idle` à cadence minimale :
la vitesse impliquée par la pose reste égale à la vitesse réelle.

| Transition | Monter si v_cmd > | Redescendre si v_cmd < | Source |
|---|---|---|---|
| arrêt ↔ pas | 0,15 | 0,06 | [I] |
| pas ↔ trot | 1,85 | 1,55 | Froude ≈ 0,35 ⇒ ≈ 1,6–1,7 m/s pour le poney [R/D, gaits.md §1.9] |
| trot ↔ galop | 4,0 | 3,5 | [U/I] |
| galop ↔ galop de course | 6,4 | 5,6 | [U/I] |

Une seule marche à la fois : pour monter, le poney accélère jusqu'au haut de sa bande puis change d'allure ;
pour descendre, il ralentit jusqu'au bas de sa bande. Durée minimale dans une allure : 0,35 s.
Accélérations (m/s²) [I] : pas 1,2 ; trot 2,0 ; galop 2,5 ; course 3,0 ; reculer 1,0 ; décélération ×1,5.

### Vitesse de sortie (pas de patinage)
`rootVelocity = Σ wᵢ · cadenceᵢ · vᵢ / Σ wᵢ` (mélange courant des clips) : le déplacement de l'entité est
cohérent avec la pose affichée, y compris pendant les fondus (au sens du mélange linéaire). La variable de
vitesse interne sert uniquement à piloter allures et cadences.

### Synchronisation de phase
Compteur de foulées commun `cycles` (partie fractionnaire = phase, 0 = poser du postérieur gauche [R]).
Il avance à la moyenne pondérée des fréquences de foulée des clips cycliques actifs
(`stridesPerClip / durée × cadence`). Un clip de k foulées est échantillonné à
`fract((cycles − phaseOffset) / k) × durée`. La phase est donc conservée pendant tous les fondus entre
pas, trot, galops, reculer et pivots ; elle est remise à 0 seulement à l'arrêt complet. Les clips idle ont
leur propre horloge.

### Virages
Lacet maximal = min(1,5 rad/s ; max(v ; 0,5) / rayon minimal de l'allure) avec rayons [I] : pas 1,2 m,
trot 3 m, galop 5 m, course 9 m, reculer 1 m ; accélération angulaire 4 rad/s². Pivot sur place
(`turn_left/right`) quand le poney est arrêté et que seul x est actionné : lacet du clip (±1,2 rad/s,
signe imposé par le nom) × cadence (±18 % selon |x|).
**Pied au galop** : à l'entrée au galop, pied du côté du virage (gauche si x < 0), sinon pied conservé
(gauche par défaut, comme `gallop`). Si le virage contredit le pied pendant 0,6 s (|x| > 0,3) : changement
de pied (fondu 0,25 s).

### Repos d'un postérieur
Après 12–30 s d'immobilité (aléatoire à graine), fondu de 1 s vers `idle_rest_hind` pendant 8–20 s [A].
Tout mouvement l'interrompt.

### Mise à l'échelle (similitude de Froude) [R/D]
Taille relative s = garrot / 1,30. Cadence des clips × 1/√s, vitesses de sortie × √s, lacet × 1/√s
(gaits.md §1.9–1.10 : mêmes formes de courbes et taux d'appui, temps compressé). L'inclinaison
θ = atan(v·ω/g) est alors indépendante de la taille. Les seuils d'allure restent exprimés pour le gabarit.
Un allongement des membres par la morphologie multiplie en plus la vitesse par
(hauteur du tronc + compensation) / hauteur du tronc [I].

---

## 7. Saut

Déclenché par `jumpPressed` au trot, au galop ou au galop de course (`JumpSettings.allowFromTrot`).

1. `jump_takeoff` (fondu 0,12 s). Au temps de l'évènement `takeoff` du clip (sinon fin du clip) :
   début du vol, évènement `takeoff`.
2. `jump_air` (boucle, tenue) jusqu'à l'atterrissage.
3. `jump_land` puis reprise de la locomotion **au galop** (galop de course si le saut partait du galop de
   course), à la vitesse d'appel bornée à la bande.

Physique [D, gaits.md §3] : montée de l'entité h = max(0,15 ; H − 0,35·s + 0,05) pour un obstacle
H = 0,7 m (0,35 m = hauteur [A] des sabots repliés au-dessus de la racine pour le gabarit) ; v0 = √(2gh) ;
temps de vol t = 2·v0/g (0,57 s pour le gabarit, h = 0,40 m). `PonyFrame.verticalVelocity = v0 − g·t_vol`
pendant le vol, 0 sinon. Vitesse horizontale constante (celle de l'appel), pas de lacet pendant le saut.

Atterrissage : automatique au bout de t, ou plus tôt sur `notifyLanded()`. Avec `usesExternalLanding`,
`jump_air` est tenu (vitesse verticale qui continue de décroître) jusqu'à `notifyLanded()` ou
t + 2 s (sécurité).

---

## 8. Comportements (`PonyAction`)

| Action | Condition | Séquence | Interruption |
|---|---|---|---|
| `graze` | arrêté | `graze_down` → `graze_loop` | mouvement / saut / autre action → `graze_up` (depuis la position miroir si la descente n'est pas finie) → locomotion |
| `lieDown` | arrêté | `lie_down` → `lying` (boucle, yeux mi-clos) | mouvement ou `getUp` → `get_up` |
| `roll` | **couché seulement** (sinon ignoré ; mis en attente pendant `lie_down`) | `roll` → `lying` | non interruptible |
| `getUp` | couché (en attente pendant `lie_down`/`roll`) | `get_up` → locomotion | non interruptible |
| `rear`, `bodyShake` | arrêté | clip → locomotion | non interruptibles |
| `paw` | arrêté | `paw` en boucle pendant 4,8 s [A] | mouvement / saut / autre action |
| `headShake`, `neigh` | locomotion (toutes allures) ou couché | **couches masquées** par-dessus | fondu de sortie 0,25 s ; refusées pendant les autres comportements |

Une action du corps entier demandée en mouvement **sans** joystick actionné est mise en attente (2 s) : le
poney s'arrête puis l'exécute. Joystick actionné : demande refusée. Pendant un comportement, l'entrée de
déplacement ne déplace pas l'entité.
Masques par défaut (si le manifeste n'en donne pas) : sous-arbre de `neck_01` (encolure, tête, oreilles,
yeux, mâchoire, toupet, crinière) ; `neigh` y ajoute `belly` (« flancs »).

---

## 9. Couches procédurales

| Couche | Fonctionnement | Paramètres (`ProceduralSettings` / `LocomotionSettings`) |
|---|---|---|
| Inclinaison | roulis θ = atan(v·ω/g) [D] du joint `body` autour de la **ligne des sabots extérieurs** ; lissage critique | `maxLeanAngle` 0,2 rad [A], `leanHalfLife` 0,15 s |
| Plantage des pieds | sabots en appui ramenés à leur hauteur d'avant l'inclinaison (+ hauteur du sol si `groundHeightProvider`) par IK à deux os (bras/cuisse → avant-bras/jambe → canon, canon à orientation conservée) ; tronc abaissé du plus petit décalage de sol | `groundMaxOffset` 0,15 m, `groundHalfLife` 0,08 s |
| Incurvation | lacet de `neck_01…03` vers l'intérieur, ∝ lacet | `maxNeckBend` 0,2 rad [A] |
| Regard | erreurs de lacet/tangage mesurées sur la tête animée (la pose de repos « regarde » à l'horizontale), bornées, lissées (ressort critique), réparties sur la chaîne `lookChain` (défaut 0,10/0,15/0,20/0,20/0,35 sur `neck_03…06` + `head` [I]) ; poids modulé par l'activité | `lookMaxYaw` 1,2 rad, `lookMaxPitchUp` 0,6, `lookMaxPitchDown` 0,8, `lookHalfLife` 0,18 s, `lookFadeDuration` 0,4 s |
| Yeux | rotation locale vers la cible, bornée ; micro-saccades sans cible [A] | `eyeMaxAngle` 0,44 rad, saccades 1–3,5 s, ±0,07 rad |
| Oreilles | humeur auto selon l'activité (regard → attentives ; brouter/couché → détendues ; cabrer → couchées ; allures rapides → attentives ; arrêt → alternance aléatoire), pivotements indépendants aléatoires, ressorts rapides | `earHalfLife` 0,07 s, durées d'humeur 4–12 s, pivots 0,8–3,5 s [A] |
| Clignements | intervalle 3–10 s, durée 0,15–0,25 s, 20 % de demi-clignements [U/A, gaits.md §4] | `upperLidCloseAngle` 0,9 rad, `lowerLidCloseAngle` 0,25 rad [A] (ou `eyelids.closeUpper/closeLower` du manifeste) |
| Respiration | effort cible par activité (galop de course 1, galop 0,65, trot 0,4, saut 0,9…), montée τ 4 s, récupération τ 25 s [A] ; fréquence 0,2 Hz (12/min [U]) → 1 Hz ; couplage 1:1 à la foulée au galop [U] | `body_breathe` = (0,25 + 0,75·effort)·cycle ; `face_nostril_flare` = effort·(0,5 + 0,5·cycle) |
| Physique secondaire | cf. §10 | |
| Surcharges | slerp de la rotation locale vers la rotation imposée | API `setJointOverride` |

---

## 10. Physique secondaire

Queue (`tail_01…04` vertèbres raides + `tail_05…10` crins), crinière (`mane_01…06`, os indépendants),
toupet (`forelock_01…03`), ventre, étriers. Chaque os porte une particule à sa pointe, rappelée par un
ressort amorti vers la **direction animée absolue** de l'os (pose animée avant simulation, mélangée vers la
verticale par `gravityBlend`), **ancrée à la tête simulée** (pointe du parent simulé) — formulation de type
« Dynamic Bone ». Amortissement relatif à la vitesse de la cible (pas de traînée à vitesse constante),
contrainte de longueur, écart angulaire maximal par os. Sous-pas fixes ≤ 1/120 s (Euler semi-implicite).
La simulation se fait dans un repère « monde » reconstruit en intégrant `rootVelocity`, `rootYawRate` et
`verticalVelocity` à l'échelle réelle. Chasse-mouches : impulsion latérale sur la queue toutes les 6–20 s à
l'arrêt ou en broutant (évènement `tail_swish`).

Pourquoi pas une cible relative au parent simulé : la chaîne de 10 ressorts à couplage unidirectionnel
multipliait les gains d'un maillon à l'autre (simulation : pointe de queue à 100–180° pour ±2,3° de tangage
du tronc ; instable sans butées). Avec la cible absolue, mesures du portage Python (tangage du tronc
±2,3° à 1 / 2,2 Hz, « galop » ±3,4° + rebond 4 cm, arrêt de 4,8 m/s en 0,5 s) : pointe de queue
11° / 6° / 4–8° / 40° (butée), aucune valeur non finie ; résultats équivalents avec des pas de 1/30 s et 0,1 s (8 sous-pas).

| Chaîne | k (1/s²) | c (1/s) | ζ | `gravityBlend` | butée (rad) |
|---|---|---|---|---|---|
| Vertèbres de queue | 400 | 36 | 0,9 | 0,05 | 0,25 |
| Crins de queue | 80 | 13,4 | 0,75 | 0,2 | 0,7 |
| Crinière | 120 | 15,3 | 0,7 | 0,15 | 0,6 |
| Toupet | 100 | 15 | 0,75 | 0,2 | 0,6 |
| Ventre | 200 | 25,5 | 0,9 | 0 | 0,15 |
| Étriers | 30 | 3,3 | 0,3 | 0,9 | 1,2 |

Toutes ces valeurs sont **[A]** (aucune donnée de dynamique de queue/crins trouvée, anatomy.md §1.6 « Tail [NF] »).

---

## 11. Morphologie

`MorphologyConfiguration` → `MorphologyEvaluator.evaluate` → `MorphologyResult` (poids ≥ 0 et ≤ 1,
décalages de translation locale, échelles de joints).

| Curseur | Plage | Formes (plus / moins) |
|---|---|---|
| `legLength`, `neckLength`, `bodyLength` | −1…1 | `prop_*_long` / `prop_*_short` + décalages de joints du manifeste (même poids) |
| `condition` | −1 maigre…+1 gras | `shape_fat` / `shape_thin` |
| `headShape` | −1 busqué…+1 concave | `head_dished` / `head_roman` |
| `stocky`, `refined`, `muscle`, `belly`, `crest`, `bone`, `headShort`, `muzzleBroad`, `hoofSize` | 0…1 | `shape_stocky`, `shape_refined`, `shape_muscular`, `shape_belly`, `shape_crest`, `shape_bone_heavy`, `head_short`, `muzzle_broad`, `hooves_large` |
| `headScale` / `earScale` / `eyeScale` | 0,85–1,2 / 0,7–1,3 / 0,85–1,2 | échelle des joints `head` / `ear_*` / `eye_*` + paupières |
| `shetland` | 0…1 | composite [A] : jambes −0,6, encolure −0,4, corps −0,2, trapu +0,8, raffiné ×(1−s), état +0,2, crête +0,3, os +0,4, museau large +0,7, tête courte +0,3, sabots +0,3, tête ×1,08, oreilles ×0,8, yeux ×1,06 |

Décalages : `jointOffsetsPlus/Minus` = translation **locale** (espace du parent) à poids 1 ; côté moins
absent ⇒ symétrique du côté plus [I]. Échelles `jointScalesPlus/Minus` = facteur à poids 1, interpolé
depuis 1. Valeurs hors bornes ou non finies ramenées au neutre.
**Compensation au sol** [I] : à chaque changement de configuration, la FK de la pose de repos déformée est
comparée à celle du gabarit ; le tronc (`body`) est relevé/abaissé pour que le sabot le plus bas reste au sol.

Préréglages (`MorphologyPreset.all`, coefficients [A], hauteurs dans les standards [R anatomy §3.2]) :
« Welsh B » 1,30 m, « Connemara » 1,40 m, « Shetland » 1,00 m, « Poney de sport » 1,46 m.
`PonyConfiguration.apply(preset:)` applique morphologie et hauteur.

---

## 12. Accessoires

`AccessoryRules(manifest:)` (catalogue du manifeste, sinon SPEC §6). Sémantique [I, alignée sur l'exporteur] :
un seul accessoire par emplacement (une pièce peut en occuper plusieurs) ; `conflicts` symétriques, par
identifiant ou nom d'emplacement ; `requires` = au moins un ; `hides` masque des pièces portées
(`tail_bow` sous `rug_stable`/`fly_sheet`).

- `validate(_:)` / `validate(_:hair:)` → `[AccessoryIssue]` (doublon, pièce inconnue, conflit/emplacement,
  prérequis). **Préférer la variante `hair:`** : les crins (`HairStyle`) comptent comme pièces portées
  (`ribbons_mane`/`pompons` requièrent `mane_braided`). Sans `hair`, les prérequis portant sur des crins
  sont considérés satisfaits.
- `resolving(adding:to:)` / `resolving(adding:to:hair:)` : remplace la pièce de même emplacement, retire les
  pièces en conflit, ajoute le premier prérequis manquant (ex. tapis western ⇒ selle western ; rubans ⇒
  crinière tressée dans `hair`), puis retire en cascade ce qui n'est plus valide.
- `removing(_:from:hair:)`, `resolving(hair:accessories:)`, `hiddenPartIDs`, `visiblePartIDs`.
- Raccourcis sur `PonyConfiguration` : `add(_:rules:)`, `removeAccessory(_:rules:)`, `setHair(_:rules:)`.

---

## 13. Configuration

`PonyConfiguration` (`Codable`, `Equatable`) : `version` (1), `name`, `withersHeight` (1,00–1,48 m →
`entityScale`), `coat` (`CoatConfiguration`, agent « coat »), `hair`, `morphology`, `accessories`.
`jsonData()` : JSON à clés triées (stable) ; `decode(from:)` tolérant (champ absent → défaut, accessoire
illisible ignoré, motif inconnu → `nil`), migration par `version`.

---

## 14. Déterminisme, performances, vérifications

- **Déterminisme** : tout l'aléatoire passe par `PonyRandom(seed)` dans un ordre fixe ; aucune itération de
  dictionnaire n'influe sur les calculs (clés triées). Même graine + mêmes entrées ⇒ mêmes frames.
- **Allocation** : tampons préalloués (poses, accumulateurs, FK, particules, évènements à capacité réservée,
  dictionnaire de poids aux clés fixes). Nuance : `PonyFrame` partage ses tableaux avec le runtime
  (copie-sur-écriture) ; si l'appelant conserve la frame précédente, la frame suivante déclenche une copie.
  PonyKit doit consommer la frame puis la relâcher.
- **Budget** visé < 0,3 ms/frame (70 joints) : non mesurable ici (pas de compilateur Swift) ; le test
  `testUpdateCostIsReasonable` imprime la mesure et n'échoue qu'au-delà de 5 ms.
- **Tests** : `cd PonyKit && swift test` (macOS ou Linux, Swift 6). Couverture : maths, lecteur binaire
  (fichier construit à la main, erreurs typées, aller-retour), échantillonnage et bouclage, mélange,
  hystérésis et synchronisation de phase, pied au galop, virages, saut, comportements, couches masquées,
  surcharges, regard, morphologie (poids jamais négatifs, alias, compensation au sol), accessoires,
  configuration JSON, manifeste au format de l'exporteur.
- **Vérifié sans compilateur** : syntaxe (`Tools/swift_syntax_check.py`, 0 erreur) ; portages Python
  fidèles de la machine d'allures (scénarios des tests de locomotion : tous conformes), du regard, de l'IK,
  de l'inclinaison avec plantage des pieds (sabots replacés à 0,1 mm, dérive latérale ≤ 9 mm à 11,5°) et
  de la physique secondaire (stabilité, résonance de la queue). **La compilation Swift et l'exécution des
  tests XCTest n'ont pas pu être faites** dans l'environnement de génération.

---

## 15. Limites connues et points ouverts

- Les chorégraphies (clips) et la plupart des constantes de comportement sont [A]/[U] (SPEC §7, gaits.md §4).
- Le fondu entre allures de schémas de pas différents (pas → trot) reste un fondu synchronisé en phase, pas
  un clip de transition dédié (recommandé par gaits.md §5.2, non fourni).
- `footfalls`, `contacts`, `rootPivot` sont lus mais pas encore exploités (verrouillage des pieds par
  contacts, pivot du virage sur place).
- Le plantage des pieds ne gère pas le tangage du tronc en pente ; un membre presque tendu ne peut pas
  s'allonger au-delà de sa longueur.
- Les axes des paupières et des oreilles sont déduits de la convention de roulis du rig (vérifiés sur le
  gabarit), pas sur le maillage final : angles à caler visuellement.

---

## Annexe — régénérer le squelette synthétique

`PonyRigDefaults.table` est générée depuis `Pipeline/pony/template.py` : pour chaque os, repère Blender
Y = (queue − tête) normalisé, Z = normalise(X_monde × Y) (repli +Z si dégénéré), X = Y × Z, origine = tête ;
locale = (repère du parent)⁻¹ · repère, sauf `root` : C · repère (C du SPEC §1) ; quaternion [x, y, z, w]
avec w ≥ 0 ; dernière colonne = longueur de l'os. Le script utilisé (`gen_default_rig.py`, ~60 lignes,
numpy + `pony.template` + `pony.conventions`) est à placer dans `Tools/` si le gabarit évolue encore
(dernière génération : gabarit avec axes optiques des yeux à 33°).

