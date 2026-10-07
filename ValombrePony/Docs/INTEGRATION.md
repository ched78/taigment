# Intégrer PonyKit dans « Les Héritiers de Valombre » (Vall2)

Version 1 — 2026-10-05. Agent « kit ». Ce document explique comment ajouter le poney 3D jouable au jeu
(application SwiftUI **Vall2**, iOS 26 / macOS 26), le code minimal, l'API publique de la couche `PonyKit`
(RealityKit + SwiftUI), les réglages, les performances attendues, la liste des API Apple utilisées avec leur
disponibilité **vérifiée**, et la **checklist des tests à faire sur appareil**.

Légende : **[V]** vérifié dans la documentation Apple (`Tools/apple_doc.py`, JSON de developer.apple.com),
**[I]** choix d'ingénierie ou hypothèse non vérifiable ici, **[A]** approximation artistique.

> **Statut.** Aucun compilateur Swift ni matériel Apple dans l'environnement de génération : le code de
> `PonyKit` a été vérifié par analyse syntaxique (`Tools/swift_syntax_check.py`, 0 erreur), relecture « œil de
> compilateur » et vérification **une par une** des déclarations et disponibilités des API Apple. **Il n'a été
> ni compilé ni exécuté.** Attendez-vous à quelques corrections de typage à la première compilation dans Xcode.
> Seule logique exécutée ici : le décodeur PNG intégré (`PonyPNGDecoder`), transcrit ligne à ligne en Python et
> comparé octet pour octet (45 PNG synthétiques couvrant types de couleur 0/2/3/4/6, profondeurs 1 à 16 bits, les
> 5 filtres et des IDAT multiples ; 7 cartes réelles du pipeline identiques à Pillow) ; les motifs de tissu
> (`PonyFabricPatterns`), portés en numpy pour un aperçu visuel.

---

## 1. Ce que contient le package

```
ValombrePony/PonyKit/                (package Swift local, swift-tools-version 6.0, mode de langage Swift 5)
├─ Package.swift                     produits « PonyCore » et « PonyKit » ; plates-formes iOS 26, macOS 26
├─ Sources/PonyCore/                 Swift pur (Foundation) : runtime d'animation, robes, morphologie, règles
└─ Sources/PonyKit/
   ├─ PonyKit.swift                  PonyKit.registerSystems(), PonyLog (préfixe [PonyKit])
   ├─ Assets/                        PonyResourceLocator, PonyAssetLibrary, PonyImageIO, PonyPNGDecoder, erreurs typées
   ├─ Rendering/                     PonySkinBinding (pose/poids), PonyMaterials, PonyFabricPatterns
   ├─ Runtime/                       PonyController (+Appearance), PonyComponent, PonyCameraComponent, PonySystem
   ├─ Camera/                        PonyCameraRig (suivi 3e personne, orbite d'écurie)
   ├─ Scene/                         PonySceneBuilder (paddock, écurie, soleil, IBL), PonyPlaceholder
   ├─ Input/                         PonyInputState (clavier ZQSD/WASD/flèches, joystick)
   ├─ Support/                       couleurs, libellés FR, PonyRandomizer, PonyConfigurationStore
   ├─ Views/                         PonyPlaygroundView, PonyStableView (+ éditeurs), HUD
   └─ Resources/                     ← produit par le pipeline (NE PAS éditer à la main)
      ├─ README.md                    témoin versionné (garantit l'existence du dossier sur un clone propre)
      ├─ Pony.usdz, Pony_QuickLook.usdz, PonyRig.json, PonyClips.bin
      ├─ coat_shading.png, coat_regions.png, coat_params.png, coat_patterns.png, hair_strands.png
      └─ Parts/<id>.usdz              (crins et accessoires, SPEC §6)
```

Le dossier `Resources/` est copié tel quel dans le bundle du module (`resources: [.copy("Resources")]`) et lu via
`Bundle.module`. Il est écrit par `python3 Pipeline/stages/s09_export.py` (voir ce script). **Il doit exister
avant de compiler** : SwiftPM signale une ressource déclarée mais absente [I : erreur ou avertissement selon la
version de SwiftPM]. Git ne suivant pas les dossiers vides, `Resources/README.md` est versionné pour que le
dossier existe sur un clone propre (ne pas le supprimer) ; il est copié dans le bundle mais n'est lu par aucun
code. Ressources manquantes à l'exécution (dossier présent mais vide) : voir les replis §4.4.

---

## 2. Ajouter le package local à Vall2

### Projet Xcode (cas de Vall2)
1. Placer (ou garder) le dépôt `ValombrePony/` à côté du projet Vall2, ou dans le même dépôt.
2. Xcode → **File ▸ Add Package Dependencies…** → bouton **Add Local…** → choisir le dossier
   `ValombrePony/PonyKit` (celui qui contient `Package.swift`).
3. Cocher le produit **PonyKit** pour la cible de l'application (PonyKit dépend de PonyCore ; ajouter aussi
   **PonyCore** si le jeu manipule directement `PonyConfiguration`, `CoatPreset`, etc. — en pratique
   `import PonyCore` est nécessaire dès qu'on construit une configuration).
4. Cible de déploiement de l'application : **iOS 26 / macOS 26** minimum (celle du package).
5. Compiler une première fois : Xcode résout le package local ; le dossier apparaît sous « Package Dependencies ».

### Autre package Swift
```swift
dependencies: [ .package(path: "../ValombrePony/PonyKit") ],
targets: [ .target(name: "Vall2Core", dependencies: [
    .product(name: "PonyKit", package: "PonyKit"),
    .product(name: "PonyCore", package: "PonyKit") ]) ]
```

### Mettre à jour les ressources
Relancer l'export du pipeline (`python3 Pipeline/stages/s09_export.py`), puis dans Xcode **File ▸ Packages ▸
Reset Package Caches** si les nouveaux fichiers ne sont pas pris en compte [I].

---

## 3. Code minimal

### Écrans prêts à l'emploi
```swift
import SwiftUI
import PonyCore
import PonyKit

struct HarasView: View {
    @State private var configuration = PonyConfiguration.default
    @State private var playing = false

    var body: some View {
        if playing {
            PonyPlaygroundView(configuration: configuration)          // paddock jouable
        } else {
            PonyStableView(configuration: configuration) { saved in  // écurie de personnalisation
                configuration = saved                                 // à persister dans la sauvegarde du jeu
                playing = true
            }
        }
    }
}
```
La configuration est un `Codable` stable (`PonyConfiguration.jsonData()` / `decode(from:)`) : la stocker dans la
sauvegarde du jeu telle quelle.

### Intégration dans votre propre `RealityView`
```swift
import RealityKit
import SwiftUI
import PonyCore
import PonyKit

struct MaScene: View {
    @State private var pony = PonyController(configuration: .default)   // @Observable, @MainActor
    @State private var camera = PonyCameraRig()
    @State private var input = PonyInputState()

    var body: some View {
        RealityView { content in
            content.camera = .virtual
            let decor = await PonySceneBuilder.makePaddock()             // ou votre propre décor
            content.add(decor.root)
            pony.imageBasedLight = decor.imageBasedLight
            content.add(pony.root)
            content.add(camera.entity)
            camera.follow(pony)
            pony.connect(input)                                          // clavier/joystick → poney
        }
        .task { await pony.load() }
        .focusable()
        .onKeyPress(phases: .all) { input.handle($0) }
    }
}
```
Exemple complet (écurie → paddock → intégration manuelle) : `Examples/PonyDemoApp.swift`.

Points d'attention :
- `PonyKit.registerSystems()` est idempotent et appelé par `PonyController.init` et `PonyCameraRig.init`, en
  tête de chacun, avant de poser `PonyComponent` / `PonyCameraComponent` (Apple, `registerComponent()` : « before
  you use it ») ;
  l'appeler aussi au démarrage de l'application (`App.init`) garantit qu'il précède la création de la première
  `RealityView` (un système enregistré après la création d'une scène y est-il ajouté ? non documenté [I]).
- `@State private var pony = PonyController(…)` : comme pour tout `@State` initialisé dans une vue, SwiftUI peut
  évaluer l'initialiseur plusieurs fois et ne garder que la première instance ; les instances jetées ne coûtent
  que deux `Entity` vides (aucun chargement avant `load()`).
- Le contrôleur est référencé **faiblement** par son entité (`PonyComponent`) : gardez-le vivant (`@State`,
  modèle de jeu), sinon le poney se fige.
- Ne jouez **aucune** animation RealityKit sur le poney (`playAnimation`) : la pose est écrite à chaque frame par
  `PonySystem` (SPEC §0). `load()` appelle `stopAllAnimations(recursive:)` sur chaque USDZ chargé.

---

## 4. API publique (PonyKit)

### 4.1 `PonyController` — `@MainActor @Observable final class`

| Membre | Rôle |
|---|---|
| `init(configuration:assets:movementMode:seed:)` | Crée `root` (déplacement) et `visualRoot` (échelle). |
| `root`, `visualRoot`, `body` | Entités ; `visualRoot` = espace modèle du runtime (unités du rig, Y haut, −Z avant). |
| `load() async` | Manifeste, clips, cartes de robe, corps ; replis §4.4 ; applique la configuration. Idempotent. |
| `apply(_:interactive:) async` | Configuration complète (morphologie, taille, crins, accessoires, teintes, motifs, robe). |
| `scheduleApply(_:interactive:)` | Variante sans attente pour l'UI (anti-rebond 80 ms ; la dernière demande gagne). |
| `configuration` | Dernière configuration appliquée (observable). |
| `input` (`PonyInput`), `inputSource` (`PonyInputState`), `connect(_:)` | Entrées : `move` (x tourner, y avancer), `sprint` ; `jumpPressed`/`action` consommés après une frame. |
| `jump()`, `perform(_:)`, `toggleLying()` | Commandes ponctuelles (saut, comportements `PonyAction`). |
| `lookTarget: SIMD3<Float>?` | Cible du regard **en coordonnées monde** (convertie en espace modèle à chaque frame). |
| `setJointOverride(_:rotation:weight:)`, `clearJointOverrides()` | Rotation **locale** imposée à un joint (nom court SPEC §3), mélangée par slerp. |
| `earMood` | Humeur des oreilles imposée (`EarMood`) ou `nil`. |
| `onEvent`, `recentEvents` | Évènements d'animation (`foot_down_*`, `takeoff`, `apex`, `landing`, `tail_swish`, `chew`, `snort`…). |
| `movementMode` (`.kinematic` / `.characterController`), `groundHeight`, `teleport(to:yaw:)` | Déplacement (§5). |
| `gait`, `currentAction`, `isAirborne`, `displaySpeed` | État observable (mis à jour seulement quand il change ; `displaySpeed` : vitesse horizontale en m/s arrondie au dixième). |
| `loadState`, `loadErrors`, `warnings`, `usesPlaceholder`, `isComposingCoat`, `accessoryIssues` | Diagnostic observable. |
| `runtime` (`PonyRuntime`), `manifest`, `rules` (`AccessoryRules`) | Accès avancés (réglages du runtime, catalogue de pièces). |
| `imageBasedLight` | Entité IBL : ajoute `ImageBasedLightReceiverComponent` à chaque entité modèle du poney. |
| `diagnosticReport()` | Hiérarchie importée, matériaux, liaisons de squelette, pièces (tests sur appareil). |
| `isPaused`, `allowsPlaceholder`, `characterRadius`, `characterHeight`, `groundSnapSpeed`, `coatPreviewResolution`, `coatFinalResolution`, `hairOpacityThreshold` | Réglages (§6). |

### 4.2 Autres types
| Type | Rôle |
|---|---|
| `PonyKit.registerSystems()` | Enregistre `PonyComponent`, `PonyCameraComponent`, `PonySystem` (idempotent). |
| `PonySystem` | `System` RealityKit : `tick` de chaque poney puis de chaque caméra, à chaque frame de rendu. |
| `PonyComponent`, `PonyCameraComponent` | Liens faibles entité → contrôleur / caméra. |
| `PonyCameraRig` | `follow(_:)`, `orbit(around:distance:)`, `rotate(yaw:pitch:)`, `zoom(by:)`, `recenter()`, `lookingPony`, réglages de distance/hauteur/lissage. |
| `PonySceneBuilder` | `makePaddock(size:fenceRadius:locator:) async`, `makeStable(size:locator:) async` → `PonySceneSetup` (`root`, `ground`, `sun`, `imageBasedLight`, `environment`). |
| `PonyInputState` (`@MainActor @Observable`) | Clavier (`handle(_ KeyPress)`), `joystick`, `sprintLatched` (seul état observé), `move`, `sprint`, `onCommand`, `releaseAll()`. |
| `PonyAssetLibrary` (`.shared`) | Cache des ressources (`manifest()`, `clips(for:)`, `coatMaps(for:)`, `instantiateBody()`, `instantiatePart(_:file:)`, `preloadParts(_:)`, `purge()`, `warnings`). |
| `PonyResourceLocator` | Dossier de ressources (`.bundled` = `Bundle.module`) ; un autre dossier peut être passé (contenu téléchargé). |
| `PonyAssetError` | Erreurs typées (messages FR) : dossier absent, ressource absente/illisible, manifeste/clips invalides, image, USDZ. |
| `PonyImageIO` | Cartes « raw » → `RGBA8Image` octet pour octet : PNG par le décodeur intégré `PonyPNGDecoder` (exact, indépendant de la gestion d'alpha d'ImageIO), sinon ImageIO ; `RGBA8Image` → `CGImage`. |
| `PonyConfigurationStore` | JSON dans `Documents/ValombrePony/Poneys/` (`list`, `save`, `load`, `delete`). |
| `PonyRandomizer` | `plausible(rules:name:)` : poney aléatoire plausible (préréglage, robe, marques, crins, harnachement). |
| `PonyFabricPatterns` | Motifs de tissu (uni, rayures, carreaux, étoiles, cœurs) → `RGBA8Image`. |
| `PonyDefaultColors`, `PonyPartLabels`, `PonyCoatLabels`, `PonyMaterialNames` | Couleurs par défaut [A], libellés FR, noms de matériaux du contrat. |
| `PonyPlaygroundView(controller:configuration:)` | Terrain de jeu (joystick iOS, clavier, actions, indicateur d'allure). |
| `PonyStableView(configuration:controller:onSave:)` | Écurie (onglets Robe, Crins, Morphologie, Taille, Accessoires, Sauvegardes ; aléatoire plausible). |
| `PonyLog` | Journal `os.Logger` (`fr.valombre.ponykit`), préfixe `[PonyKit]` ; `mirrorToStandardOutput`. |

### 4.3 Ce que fait `apply`
1. `runtime.configuration` (morphologie : poids de formes + décalages/échelles de joints) ; échelle de
   `visualRoot` = `withersHeight / 1,30` (la vitesse de déplacement est déjà à l'échelle réelle, RUNTIME.md §6).
2. Pièces visibles = `AccessoryRules.visiblePartIDs(for:hair:)` (crins de `HairStyle` + accessoires, moins les
   pièces masquées comme `tail_bow` sous une couverture) ; chargées à la demande (`Parts/<id>.usdz`), mises en
   cache (désactivées quand elles ne sont plus portées), une pièce introuvable n'est plus redemandée (avertissement).
   Problèmes : `validate(_:hair:)` → `accessoryIssues`. **`apply` ne corrige pas la sélection** : utiliser
   `PonyConfiguration.add(_:rules:)` / `removeAccessory(_:rules:)` / `setHair(_:rules:)` (variantes « hair »).
3. Teintes par `Material.name` [V iOS 18] (nom complet ou dernier segment de chemin [I]) : `slot_primary`,
   `slot_secondary`, `slot_accent`, `slot_metal` des accessoires (`AccessorySelection.slotColors`, sinon
   `PonyDefaultColors`) ; motifs sur les `fabricSlots` (texture 512² composée hors MainActor, remplace la texture de
   trame en niveaux de gris [I]) ; `M_Lashes` (teinte dérivée des crins, double face).
4. Robe : `CoatCompositor.composeBody` **hors MainActor** (`Task.detached`), 1024² si `interactive`, 2048² sinon,
   puis `TextureResource(image:withName:options:)` (`.color`) sur `M_Coat` ; crins (`composeHair`) sur le
   `slot_primary` de chaque pièce de crins avec `opacityThreshold` 0,4 et `faceCulling = .none` ; iris
   (`composeIris`) sur `M_Eye`. Une seule composition à la fois ; la demande la plus récente est traitée ensuite ;
   une robe inchangée déjà composée à une résolution au moins égale n'est pas recomposée (un curseur de
   morphologie ne relance donc pas le compositeur). `M_Mouth` est laissé tel qu'exporté.
5. Données lues dans `PonyRig.json` en plus de `PonyRigManifest` : `coat.maps` (noms des cartes), `hair.maps.strands`
   (texture de mèches, écrite par `s09_export.py`), `coat.landmarks` (`coronet`, `faceEyeV`, `faceEyeU`, `nostrilV`,
   ou en snake_case) → `CoatMaps.landmarks` ; absents → valeurs par défaut (l'export v1 n'écrit pas encore
   `coat.landmarks` [I]).

### 4.4 Replis (le jeu reste utilisable)
| Situation | Repli |
|---|---|
| Dossier `Resources/` absent | `PonyAssetError.resourceFolderMissing` journalisé ; manifeste synthétique + substitut primitif. |
| `PonyRig.json` absent/invalide | `PonyRigDefaults.syntheticManifest()` (squelette du gabarit, catalogue de pièces du SPEC §6, aucun clip) ; les pièces présentes dans `Parts/` restent chargeables (noms de joints du gabarit). |
| `PonyClips.bin` absent / invalide | `ClipLibrary.empty` : pose de repos + procédural ; le poney se déplace quand même. |
| Cartes de robe absentes | Robe par défaut de l'USDZ si `coat == .default`, sinon teinte unie (`phenotype.bodyColor`). |
| `hair_strands.png` absent | Crins teintés (`maneColor`) sur l'albedo d'aperçu de l'USDZ. |
| `Pony.usdz` absent | `PonyPlaceholder` (silhouette en boîtes colorée d'après la robe) si `allowsPlaceholder`, sinon `.failed`. |
| Pièce absente | Ignorée, avertissement unique dans `warnings`. |
| Aucun matériau `slot_*` (ou `slot_primary`/`M_Hair` pour les crins) reconnu dans une pièce | Couleurs d'export conservées ; avertissement listant les noms importés (diagnostic de `Material.name`). |
| PNG entrelacé, « CgBI » (optimisé par Xcode) ou autre format | Repli ImageIO (avertissement « décodeur PNG intégré en échec ») ; alpha prémultiplié éventuel « déprémultiplié » (approché). |

---

## 5. Déplacement

- **`.kinematic`** (défaut) : lacet `rootYawRate·dt` autour de +Y, pas `orientation.act(rootVelocity)·dt`,
  sol plat à `groundHeight` ; saut : `y += verticalVelocity·dt` pendant le vol, `runtime.notifyLanded()` quand
  l'entité retouche le sol (`usesExternalLanding = true`).
- **`.characterController`** : `CharacterControllerComponent(radius:height:)` sur `root` (capsule verticale
  0,42 × 1,25 m pour 1,30 m, × échelle [A]) et `moveCharacter(by:deltaTime:relativeTo:collisionHandler:)` ;
  hors saut, plaquage au sol à `groundSnapSpeed` ; atterrissage sur `CollisionFlags.bottom`. Le décor doit porter
  des `CollisionComponent` (le paddock en a : sol et poteaux ; les cavalettis n'en ont pas, pour pouvoir être
  sautés). `height` est la hauteur TOTALE de la capsule (doc Apple de `CharacterControllerComponent.height` :
  « The capsule height includes radii »), bornée à `2 × radius` [I] : `visualRoot` est abaissé de `height/2`
  (× échelle), soit 0,625 m par défaut ; centre de la capsule supposé à l'origine de `root` [I, à vérifier §9].
- Une capsule verticale épouse mal un corps horizontal (realitykit.md §6.4) : la tête et la croupe peuvent entrer
  dans les obstacles. Pour un jeu exigeant, ajouter des formes de requête (raycasts) devant/derrière [I].

## 6. Réglages utiles

| Réglage | Où | Défaut |
|---|---|---|
| Allures, accélérations, rayons de virage, seuils | `controller.runtime?.locomotionSettings` (RUNTIME.md §6) | gabarit 1,30 m |
| Saut | `runtime?.jumpSettings` | RUNTIME.md §7 |
| Comportements | `runtime?.behaviorSettings` | RUNTIME.md §8 |
| Regard, oreilles, clignements, respiration, ressorts | `runtime?.proceduralSettings` | RUNTIME.md §9–10 |
| Sol non plat (IK des sabots) | `runtime?.groundHeightProvider` (espace modèle) | `nil` = sol plat |
| Résolution de la robe | `coatPreviewResolution` / `coatFinalResolution` | 1024 / 2048 |
| Découpe alpha des crins | `hairOpacityThreshold` | 0,4 |
| Capsule du contrôleur (`characterHeight` = hauteur totale, hémisphères compris) | `characterRadius`, `characterHeight`, `groundSnapSpeed` | 0,42 / 1,25 / 2 m/s |
| Caméra de suivi | `PonyCameraRig.followDistance/followHeight/lookHeight/positionHalfLife/focusHalfLife/yawHalfLife/recenterDelay` | 4,2 m / 1,25 / 1,0 / 0,12 s / 0,04 s / 0,45 s / 2,5 s |
| Orbite d'écurie | `orbitYaw/orbitPitch/orbitDistance/autoRotateSpeed`, `minZoom/maxZoom` | — |
| Journal sur la sortie standard | `PonyLog.mirrorToStandardOutput = true` | `false` |

---

## 7. Performances (estimations NON MESURÉES)

| Poste | Coût attendu | Remarques |
|---|---|---|
| Runtime PonyCore | < 0,3 ms/frame visé (RUNTIME.md §14) | non mesuré ; 70 joints, tampons préalloués |
| Écriture de pose | (1 + pièces visibles) × copie de 70 `Transform` + `components.set` | 6 à 12 entités typiques |
| Poids de formes | écriture seulement si un poids change de plus de 1e-4 | la respiration change à chaque frame |
| Robe 1024² / 2048² | objectif < 150 ms à 2048² (COAT.md §6), hors MainActor | + création de texture sur le MainActor |
| Mémoire robe | 2048² RGBA ≈ 16 Mo (tampon) + copie `CGImage` + texture GPU avec mipmaps | libérés après création |
| Motifs de tissu | 512² par combinaison motif/couleurs, cache de 32 | composés hors MainActor |
| Pièces | une instance (clone) par pièce portée, gabarits partagés entre poneys | `preloadParts(_:)` pour éviter un à-coup |

Conseils : profiler avec Instruments (**RealityKit Trace**, **Time Profiler**) sur l'appareil le plus ancien
visé ; si la robe à 2048² est trop lente, garder 1024² (`coatFinalResolution = 1024`).

---

## 8. API Apple utilisées — déclaration et disponibilité vérifiées [V]

Source : JSON de la documentation Apple via `python3 Tools/apple_doc.py <chemin>` (2026-10-05). Toutes sont
disponibles sur iOS 26 / macOS 26 ; aucune n'est réservée à visionOS ni à iOS 27.

### RealityKit
| API | Disponibilité | Utilisation |
|---|---|---|
| `Entity(contentsOf:withName:) async throws` (`@MainActor`) | iOS 18 / macOS 15 | chargement des USDZ |
| `Entity.clone(recursive:)`, `stopAllAnimations(recursive:)`, `name`, `isEnabled`, `scene` | iOS 13 / macOS 10.15 | gabarits, pièces |
| `HasHierarchy.addChild(_:preservingWorldTransform:)`, `children`, `parent` | iOS 13 / macOS 10.15 | hiérarchie |
| `HasTransform.position/orientation/scale`, `position(relativeTo:)`, `orientation(relativeTo:)`, `convert(position:from:)` | iOS 13 / macOS 10.15 | déplacement, regard |
| `HasTransform.look(at:from:upVector:relativeTo:forward:)` | iOS 18 / macOS 15 | caméra, soleil |
| `Entity.ComponentSet` : `set(_:)`, `has(_:)`, `remove(_:)`, `subscript(_:)` | iOS 13 / macOS 10.15 | composants |
| `SkeletalPosesComponent.poses`, `SkeletalPoseSet.default { get set }`, `SkeletalPose.jointNames`, `jointTransforms` | iOS 18 / macOS 15 | pose par frame |
| `JointTransforms` (MutableCollection, `Index = Int`, `init(_:)`) | iOS 15 / macOS 12 | pose |
| `BlendShapeWeightsComponent.weightSet`, `BlendShapeWeightsSet` (Collection, `subscript(index:) { get set }`), `BlendShapeWeightsData.weightNames/weights`, `BlendShapeWeights` (MutableCollection, `Index = Int`) | iOS 18 / macOS 15 | blend shapes |
| `ModelComponent.materials`, `HasModel.model` | iOS 13 / macOS 10.15 | matériaux |
| `Material.name: String? { get }` | iOS 18 / macOS 15 | identification des slots |
| `PhysicallyBasedMaterial` : `baseColor` (`BaseColor(tint:texture:)`, `tint` UIColor/NSColor, `texture`), `opacityThreshold`, `faceCulling` (`.none`), `roughness` (`Roughness(scale:)`), `textureCoordinateTransform` (`init(offset:scale:rotation:)`) | iOS 15 / macOS 12 | teintes, textures |
| `MaterialParameters.Texture(_:)` | iOS 15 / macOS 12 | textures |
| `TextureResource(image:withName:options:) async throws` (`@MainActor`, `options` sans défaut) | iOS 18 / macOS 15 | robe, crins, iris, motifs |
| `TextureResource.CreateOptions(semantic:mipmapsMode:)`, `Semantic.color` | iOS 15 / macOS 12 | textures couleur |
| `System` (`init(scene:)`, `update(context:)`, `registerSystem()`), `Component.registerComponent()` | iOS 15 / macOS 12 (Component : iOS 13) | `PonySystem` |
| `EntityQuery(where:)`, `QueryPredicate.has(_:)`, `SceneUpdateContext.deltaTime` | iOS 15 / macOS 12 | requêtes |
| `SceneUpdateContext.entities(matching:updatingSystemWhen:)`, `SystemUpdateCondition.rendering` | iOS 18 / macOS 15 | requêtes |
| `CharacterControllerComponent(radius:height:…)`, `radius`, `height` (« The capsule height includes radii ») | iOS 15 / macOS 12 | déplacement |
| `Entity.moveCharacter(by:deltaTime:relativeTo:collisionHandler:)` → `CollisionFlags` (`.bottom`) | iOS 15 / macOS 12 | déplacement |
| `Entity.teleportCharacter(to:relativeTo:)` | iOS 15 / macOS 12 | téléportation |
| `PerspectiveCameraComponent(near:far:fieldOfViewInDegrees:)` | iOS 13 / macOS 10.15 | caméra |
| `DirectionalLightComponent(color:intensity:isRealWorldProxy:)` | iOS 13 / macOS 10.15 (la variante sans `isRealWorldProxy` est visionOS) | soleil |
| `DirectionalLightComponent.Shadow(shadowProjection:depthBias:cullMode:)`, `.automatic(maximumDistance:)` | iOS 18 / macOS 15 | ombres |
| `GroundingShadowComponent(castsShadow:)` ; `(castsShadow:receivesShadow:)` | iOS 18 / macOS 15 | ombres de contact |
| `ImageBasedLightComponent(source:intensityExponent:)`, `.single(_:)`, `ImageBasedLightReceiverComponent(imageBasedLight:)` | iOS 18 / macOS 15 | IBL |
| `EnvironmentResource(equirectangular:withName:) async throws` | iOS 18 / macOS 15 (dépréciée en 27.2 seulement) | IBL, ciel |
| `MeshResource.generatePlane(width:depth:cornerRadius:)`, `generateBox(width:height:depth:cornerRadius:splitFaces:)` | iOS 13 / macOS 10.15 | décor, substitut |
| `MeshResource.generateCylinder(height:radius:)` | iOS 18 / macOS 15 | poteaux |
| `ModelEntity(mesh:materials:)` | iOS 13 / macOS 10.15 | décor |
| `CollisionComponent(shapes:mode:filter:)`, `ShapeResource.generateBox(width:height:depth:)`, `PhysicsBodyComponent(shapes:mass:material:mode:)`, `PhysicsBodyMode.static` | iOS 13 / macOS 10.15 | sol, clôture |
| `RealityView(make:update:)` pour `RealityViewCameraContent` ; `camera = .virtual` ; `environment = .skybox(_:)` ; `add(_:)` | iOS 18 / macOS 15 | vues |

### SwiftUI, Observation
| API | Disponibilité |
|---|---|
| `@Observable`, `@ObservationIgnored` (`PonyController`, `PonyInputState`) | iOS 17 / macOS 14 |
| `onKeyPress(phases:action:)`, `KeyPress.phase/key/modifiers`, `KeyPress.Phases` (`.down/.up/.repeat/.all`), `KeyPress.Result` | iOS 17 / macOS 14 |
| `KeyEquivalent.upArrow/downArrow/leftArrow/rightArrow/space`, `character` ; `EventModifiers.shift` | iOS 14 / macOS 11 ; iOS 13 / macOS 10.15 |
| `focusable(_:)` (iOS 17 / macOS 12), `focused(_:)` (iOS 15 / macOS 12), `focusEffectDisabled(_:)` (iOS 17 / macOS 14) | — |
| `DragGesture(minimumDistance:coordinateSpace:)` ; `Value.translation/location` | iOS 17 / macOS 14 ; iOS 13 |
| `MagnifyGesture` | iOS 17 / macOS 14 (**`Value.magnification` : propriété non trouvée dans la doc consultable [I]**) |
| `ColorPicker(_:selection:supportsOpacity:)` avec `Binding<CGColor>` | iOS 14 / macOS 11 |
| `Slider(value:in:onEditingChanged:)` | iOS 13 / macOS 10.15 |
| `onChange(of:initial:_:)` (2 paramètres) ; `task(name:priority:file:line:_:)` ; `onAppear/onDisappear` | iOS 17 / macOS 14 ; iOS 15 / macOS 12 ; iOS 13 |
| `formStyle(_:)` + `.grouped` | iOS 16 / macOS 13 |
| `toggleStyle(.button)`, `buttonStyle(.borderedProminent)`, `monospacedDigit()`, `.ultraThinMaterial` | iOS 15 / macOS 12 |
| `tint(_:)` (ShapeStyle) | iOS 16 / macOS 13 |
| `DisclosureGroup`, `fileImporter(isPresented:allowedContentTypes:onCompletion:)`, `UTType.json` | iOS 14 / macOS 11 |
| `ShareLink(item:subject:message:label:)` (URL) | iOS 16 / macOS 13 |
| `Color(_:red:green:blue:opacity:)` + `.sRGB` | iOS 13 / macOS 10.15 |
| `Date.formatted(date:time:)` | iOS 15 / macOS 12 |

### UIKit / AppKit / CoreGraphics / ImageIO / Foundation / os
| API | Disponibilité |
|---|---|
| `UIColor(red:green:blue:alpha:)` | iOS 2 |
| `NSColor(red:green:blue:alpha:)` (composantes étendues = sRGB étendu, comme UIColor) | macOS 10.9 |
| `NSEvent.modifierFlags` (classe), `.shift` | macOS 10.6 |
| `CGColor(srgbRed:green:blue:alpha:)` | iOS 13 / macOS 10.15 |
| `CGColor.converted(to:intent:options:)`, `components` | iOS 9 / macOS 10.11 |
| `CGImage(width:height:bitsPerComponent:bitsPerPixel:bytesPerRow:space:bitmapInfo:provider:decode:shouldInterpolate:intent:)`, `CGDataProvider(data:)`, `CGImage.dataProvider` | iOS 2 / macOS 10.0–10.4 |
| `CGImage.byteOrderInfo` | iOS 12 / macOS 10.14 |
| `CGImageSourceCreateWithURL`, `CGImageSourceCreateWithData`, `CGImageSourceCreateImageAtIndex` | iOS 4 / macOS 10.4 |
| Compression : `compression_decode_buffer(_:_:_:_:_:_:)`, `compression_decode_scratch_buffer_size(_:)`, `COMPRESSION_ZLIB` (documenté : DEFLATE « brut », RFC 1951) | iOS 9 / macOS 10.11 |
| `URL.startAccessingSecurityScopedResource()` | iOS 8 / macOS 10.10 |
| `FileManager.url(for:in:appropriateFor:create:)` | iOS 4 / macOS 10.6 |
| `os.Logger` | iOS 14 / macOS 11 |

### Points NON vérifiés dans le code (marqués [I])
- `MagnifyGesture.Value.magnification` (pincement de zoom).
- `Bundle.module.url(forResource: "Resources", withExtension: nil)` trouve un dossier copié par `.copy` (repli sur
  `resourceURL/Resources`).
- Format des noms importés : `SkeletalPose.jointNames` = chemins USD (`root/body/…`), `Material.name` = nom ou
  chemin du matériau, noms de poids = noms des `BlendShape`. Le code accepte nom court et chemin.
- `PerspectiveCameraComponent` d'une entité de la scène utilisé comme point de vue par `RealityView` `.virtual`.
- Lumière directionnelle orientée selon −Z de son entité.
- Capsule du contrôleur de personnage centrée sur l'entité (la doc Apple dit seulement que `height` inclut les
  rayons, pas où se trouve l'origine) ; comportement si `height < 2 × radius` (on borne à `2 × radius`).
- Marge de contact `skinWidth` (« contact offset », `defaultSkinWidth` sans valeur documentée) : elle peut laisser
  les sabots légèrement au-dessus du sol en mode `.characterController` ; non compensée.
- `ImageBasedLightReceiverComponent` non hérité (posé sur chaque entité modèle par précaution).
- `CGImage` RGBA non prémultiplié (`.last`) accepté par `TextureResource(image:…)` pour l'alpha des crins.
- UV de l'œil : iris centré dans le carré UV (COAT.md §7 ; contrat repris par `Pipeline/pony/head_parts.py`).
- Repli ImageIO seulement (le décodeur PNG intégré lit les octets du fichier) : ImageIO ne convertit pas les
  échantillons et ne prémultiplie pas l'alpha.
- `compression_decode_buffer` n'exige pas que la source s'arrête exactement à la fin du flux : on lui passe déjà le
  flux DEFLATE exact (sans en-tête zlib ni Adler-32), hypothèse donc sans effet.
- Maj seule ne produit pas d'évènement `onKeyPress` sur iOS (utiliser le bouton « Galop »).

---

## 9. Checklist de tests sur appareil (iOS 26 et macOS 26)

Reprend les incertitudes de `Docs/research/realitykit.md` §9 et `Docs/research/usd.md` §7, plus celles de
PonyKit. Pour chaque point : appeler `print(controller.diagnosticReport())` et relever les journaux `[PonyKit]`
(Console.app, sous-système `fr.valombre.ponykit`).

**Chargement et structure (realitykit §9.1, usd §7.6)**
- [ ] `Pony.usdz` se charge ; noter la hiérarchie (une seule entité `ModelComponent` + `SkeletalPosesComponent`
      pour les 4 maillages ? où est `BlendShapeWeightsComponent` ?). Aucun avertissement « joint(s) du manifeste
      absents » ni « pose importée incomplète ».
- [ ] Noms importés : `jointNames` (chemins ?), `Material.name` (`M_Coat` ou chemin ?), noms des poids.
- [ ] Les matériaux importés sont des `PhysicallyBasedMaterial` (sinon avertissement « non modifiable »).
- [ ] Chaque pièce `Parts/<id>.usdz` se charge, suit la pose (pas de pièce figée en T) et se masque/affiche.

**Pose et poids (realitykit §9.3–9.4, usd §7.5)**
- [ ] La pose écrite dans `SkeletalPosesComponent` est rendue la même frame et persiste (aucun clip ne joue).
- [ ] Les curseurs de morphologie déforment corps ET pièces (mêmes noms de blend shapes) ; ombrage correct sans
      `normalOffsets`.
- [ ] Écrire les poids à chaque frame ne fait pas chuter la cadence (respiration).

**Limites (realitykit §9.2, usd §7.1)**
- [ ] 70 joints et ≤ 4 influences par sommet : pas de troncature visible (comparer avec `Pony_QuickLook.usdz`).

**Cartes de pelage**
- [ ] Aucun avertissement « décodeur PNG intégré en échec » au chargement (sinon : les PNG du bundle ont été
      retraités — vérifier que `Resources/` est bien copié tel quel, `.copy`, sans optimisation PNG d'Xcode,
      usd §7.8) ; journal « robe composée en … ms » présent.

**Matériaux et textures (usd §7.4, §7.7–7.8)**
- [ ] Robe composée appliquée sur `M_Coat` (pas de couture ni de décalage d'UV) ; temps de composition 1024² et
      2048² (journal « robe composée en … ms ») ; mémoire.
- [ ] Crins : découpe alpha nette (`opacityThreshold` 0,4), double face, pas de tri incorrect.
- [ ] Iris : centré et orienté (hypothèse UV) ; cils double face.
- [ ] Normal maps (scale/bias ignorés ?) correctes ; textures AVIF/compression éventuelles.
- [ ] Motifs de tissu : échelle (8 répétitions par côté UV [A]) et perte acceptable de la trame.

**Animation, déplacement, caméra**
- [ ] Allures (pas → galop de course) sans patinage ; virages ; reculer ; pivot.
- [ ] Saut cinématique : décollage, apex, réception (`notifyLanded`), pas de rebond.
- [ ] Mode `.characterController` : sabots au sol (sinon vérifier l'hypothèse « centre de la capsule à l'origine
      de `root` », décalage `height/2`), collisions avec la clôture, saut, pentes et marches (realitykit §9.10).
- [ ] Caméra de suivi active (le `PerspectiveCameraComponent` est bien utilisé), lissage, orbite, zoom pincé.
- [ ] Soleil : direction et ombres ; ombres de contact ; IBL (ciel généré) ; `.skybox` affiché.

**Entrées et interface**
- [ ] macOS : ZQSD (AZERTY) et WASD (QWERTY), flèches, Maj, Espace, raccourcis B/H/C/T/G/L/R/E ; focus clavier
      au lancement ; touches relâchées à la perte de focus.
- [ ] iOS : joystick, boutons Galop/Sauter/actions ; clavier matériel.
- [ ] Écurie : chaque onglet, sélecteurs de couleur, conflits d'accessoires expliqués, aléatoire plausible,
      sauvegarde/chargement/partage/import JSON.

**Hors périmètre PonyKit mais listés par la recherche (non utilisés : pas d'animations RealityKit)**
- [ ] (realitykit §9.6, §9.8 ; usd §7.2–7.3) blend trees, schéma de clips RCP, origine des temps d'un clip USD :
      seulement si l'on joue un jour `Pony_QuickLook.usdz` en animation native.
- [ ] (realitykit §9.5) coût d'un `IKComponent` plein corps : non utilisé (IK maison dans PonyCore).

---

## 10. Dépannage

| Symptôme | Piste |
|---|---|
| Poney figé | Contrôleur libéré (référence faible) ? `PonyKit.registerSystems()` appelé ? `isPaused` ? clip RealityKit joué par erreur ? |
| Poney en T / pièces décalées | Noms de joints non reconnus : voir l'avertissement « joint(s) … absents » et `diagnosticReport()`. |
| Robe grise ou uniforme | Cartes `coat_*.png` absentes (avertissement), ou `M_Coat` introuvable. |
| Crins invisibles | Alpha prémultiplié très faible (avertissement `PonyImageIO`), seuil trop haut (`hairOpacityThreshold`). |
| « Ressources du poney introuvables » | Lancer `Pipeline/stages/s09_export.py`, vérifier `PonyKit/Sources/PonyKit/Resources/`. |
| Clavier sans effet | La vue n'a pas le focus : cliquer dans la vue (macOS) ; `focusable()` + `focused`. |
