# RealityKit on iOS 26 / macOS 26 — API research for a rigged, playable, customisable pony

Project: "Les Héritiers de Valombre" (SwiftUI app). Research date: 2026-10-05.

## How this was researched, and the labels used

- **Primary source**: Apple's documentation. Every symbol below was read from the same JSON that renders the public doc page (`https://developer.apple.com/tutorials/data/documentation/<path>.json`). Each claim cites the human-readable URL (`https://developer.apple.com/documentation/<path>`). Minimum OS versions come from the `platforms` metadata of those pages. Apple's docs today show the **iOS 27 SDK** (WWDC26 shipped in June 2026). Each API is therefore marked with its real minimum OS, and **anything that is iOS 27-only is flagged so you don't use it with a 26 deployment target.**
- **Secondary sources**: WWDC session transcripts on developer.apple.com, Apple sample-code articles, and Apple Developer Forums threads. Answers from Apple engineers are quoted. Answers from community members are labelled as such.
- **Local experiment**: Blender 4.2 (`bpy`) USD export, run in this container and inspected with `pxr`. See §2.6.
- No Swift was compiled (there is no toolchain here), so every Swift snippet is **untested**.

Labels:
- **[V]**: verified. A primary Apple source (docs, WWDC transcript, Apple sample, or an Apple engineer's forum reply) is cited next to it.
- **[C]**: reported by the community (a forum post from a non-Apple developer, or a third-party tool). Plausible, but Apple has not confirmed it.
- **[I]**: my inference or an open question. Not verified; needs an on-device test.

---

## 0. Executive summary (the most important points)

1. **Skinning and USD import [V]**: RealityKit imports UsdSkel skeletons, skeletal animation and blend shapes ([Validating feature support for USD files](https://developer.apple.com/documentation/usd/validating-usd-files)). Apple asks for **one skeleton per rigged model** and for `SkelBindingAPI` and `MaterialBindingAPI` to be applied ([Creating USD files for Apple devices](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices)). Every skinned mesh imported from USD automatically gets a `SkeletalPosesComponent` ([WWDC24 10102](https://developer.apple.com/videos/play/wwdc2024/10102/)). A model that has blend shapes automatically gets a `BlendShapeWeightsComponent`, and its USD animations are exposed in an `AnimationLibraryComponent` ([BOT-anist sample](https://developer.apple.com/documentation/visionos/bot-anist)).
2. **No documented limit on joints or influences per vertex.** Apple does not publish a maximum joint count or a maximum number of influences per vertex. The API takes any `influencesPerVertex`. **Plan for ≤ 4 influences per vertex and a modest joint count, then measure on device** [I].
3. **Clips**: one USD file gives one timeline (Reality Composer Pro calls it the "default subtree animation"). Use `AnimationView(source:…trimStart:trimEnd:…)` plus `AnimationResource.generate(with:)` to cut clips in code [V]. Clips stored in **separate files can be played on the same skeleton when the joint hierarchy is the same** [V] (BOT-anist).
4. **Blending limits [V]**: `playAnimation` documents that **"RealityKit supports blending up to two different animations at the same time"**, and `blendLayerOffset` is documented as 0 or 1. For locomotion blends, use `BlendTreeAnimation<JointTransforms>` with `BlendWeight.parameter("…")` driven through `entity.parameters` [V]. Use `transitionDuration` and `AnimationHandoffType` for cross-fades [V].
5. **Procedural layering on top of clips.** Apple does **not** document when a custom `System` runs relative to the built-in animation system. Community reports say playing clips overwrite manual joint or blend-shape edits [C]. The **Apple-recommended route** for look-at and similar overrides while a clip plays is **`IKComponent` constraints with `animationOverrideWeight`** (an Apple engineer said this on the forum [V]). The IK solver takes the animated pose in `SkeletalPosesComponent` as its forward-kinematics input [V]. `AnimationEvents.SkeletalPoseUpdateComplete` (iOS 18) is "raised immediately after the SkeletalPoseSystem has been updated" [V]. Whether writing the pose there is honoured in the same frame is **unverified** [I].
6. **Blender export keys every joint.** Blender 4.2's USD exporter writes keys for **every joint**, and for **every shape-key weight**, in every exported `SkelAnimation`. I checked this locally (§2.6). As exported, each clip therefore overrides the whole skeleton and the morphology sliders. Fix: post-process with `pxr` to remove `blendShapes`/`blendShapeWeights` (and optionally ear, tail and head joints) from clip `SkelAnimation`s. Whether RealityKit honours sparse joint animation is [I] and must be tested.
7. **Accessories**:
   - Rigid tack (saddle, stirrups, bit, plume): use the **iOS 26** `Entity.attach(_:to:)` / `AttachedTransformComponent` with a `GeometricPin` created on a skeletal joint (`pins.set(named:skeletalJointName:…)`, iOS 18). An Apple engineer calls this "the new, recommended way" [V].
   - Skinned accessories (rugs, boots, bandages): there is no documented API. Community reports say every mesh under one SkelRoot is merged into **one** `ModelComponent`, so `removeFromParent()` on a child does not hide it [C]. Options: export each skinned accessory as its own SkelRoot with the **same joint names** and keep its pose in sync, or rebuild `MeshResource.Contents` without the hidden parts [I].
8. **Materials [V]**:
   - `PhysicallyBasedMaterial` (iOS 15/macOS 12) has baseColor tint × texture, roughness, metallic, normal, clearcoat, sheen, anisotropy, `opacityThreshold` (alpha-mask, overrides `blending`), `faceCulling` (default `.back`), and `readsDepth`/`writesDepth` (iOS 18).
   - **The RealityKit USD importer does not support "double-sided"**, so mane cards need `faceCulling = .none` set in code (or real two-sided geometry).
   - `ShaderGraphMaterial` and `setParameter` need iOS 18/macOS 15.
   - `TextureResource(image:withName:options:)` is `async throws` (iOS 18). `TextureResource.generate(from:withName:options:)` is **deprecated since iOS 18/macOS 15**.
   - `LowLevelTexture` (iOS 18) with Metal compute covers real-time recolouring.
   - **`CustomMaterial` exists on iOS 15+, macOS 12+ and Mac Catalyst. It is not available on visionOS.**
   - Subsurface scattering, bent normals and `HairLightingModel` are **iOS 27-only**.
9. **Playable character [V]**:
   - `CharacterControllerComponent` and `moveCharacter(by:deltaTime:relativeTo:collisionHandler:)` (iOS 15/macOS 12) give a capsule aligned with `upVector`. It is **incompatible with `PhysicsBodyComponent` and `CollisionComponent` on the same entity**. Drive it from `PhysicsSimulationEvents.WillSimulate` (iOS 18).
   - A vertical capsule fits a long horizontal pony body poorly [I].
   - Apple's iOS 26 **"Bringing your SceneKit projects to RealityKit" (Pyro Panda)** sample is a third-person platformer with character movement, a state/animation component and a follow camera. Use it as the architectural reference.
10. **Rendering setup on iOS/macOS 26 [V]**:
    - `RealityView(make:update:)` with `RealityViewCameraContent`: `content.camera = .virtual` (`.spatialTracking` exists on iOS only), `.realityViewCameraControls(.orbit)` (iOS 18/macOS 15), `content.environment = .skybox(EnvironmentResource)`, and `content.renderingEffects`. Custom post-processing needs iOS 26.
    - Shadows: `GroundingShadowComponent` (iOS 18; **per entity, not inherited by the hierarchy**), or `DirectionalLightComponent` plus `DirectionalLightComponent.Shadow`.
    - IBL: `ImageBasedLightComponent` plus `ImageBasedLightReceiverComponent` (iOS 18).
    - **RealityKit ignores lights authored in USD.**
11. **Don't use with a 26 target (iOS 27-only)**: `AnimationGraphComponent`/`AnimationGraphResource`, `SkeletonResource`, `RetargetingConfiguration` (including `automatchQuadruped`), `MeshDeformerComponent`/`SkinningDeformer`/`BlendShapeDeformer`, `AnimationEvents.RootMotionDidUpdate`, `BindTarget.rootMotion`, `AnimationLibraryComponent.automaticallyPlaysDefaultAnimation`, `IKRig(named:rootJoint:)`, PBR subsurface and bent normals, `HairLightingModel`, `DirectionalLightComponent.Shadow.cascades`, and `NavigationComponent`.

---

## 1. Skeletal meshes

### 1.1 `HasModel.jointNames` / `jointTransforms` (on `ModelEntity`) — [V]

| Symbol | Declaration | Min OS |
|---|---|---|
| `jointNames` | `var jointNames: [String] { get }` | iOS 13, macOS 10.15 |
| `jointTransforms` | `var jointTransforms: [Transform] { get set }` | iOS 13, macOS 10.15 |
| `blendWeightNames` | `var blendWeightNames: [[String]] { get }` | iOS 18, macOS 15 |
| `blendWeights` | `var blendWeights: [[Float]] { get set }` | iOS 18, macOS 15 |

Sources: [jointNames](https://developer.apple.com/documentation/realitykit/hasmodel/jointnames), [jointTransforms](https://developer.apple.com/documentation/realitykit/hasmodel/jointtransforms), [blendWeightNames](https://developer.apple.com/documentation/realitykit/hasmodel/blendweightnames), [blendWeights](https://developer.apple.com/documentation/realitykit/hasmodel/blendweights).

- `jointTransforms` is **settable**. The transforms are "relative", meaning local to the parent joint.
- Apple's note: **"Active animations may override the joint transforms set using this property."** [V]
- **Performance**: Apple doesn't document it [I]. Each set copies the whole array, so for per-frame procedural work prefer `SkeletalPosesComponent` or IK (see below).

### 1.2 `SkeletalPosesComponent`, `SkeletalPose`, `SkeletalPoseSet` — iOS 18 / macOS 15 / visionOS 2 [V]

Source: [SkeletalPosesComponent](https://developer.apple.com/documentation/realitykit/skeletalposescomponent), [SkeletalPose](https://developer.apple.com/documentation/realitykit/skeletalpose), [SkeletalPoseSet](https://developer.apple.com/documentation/realitykit/skeletalposeset).

- Purpose (doc): "Use the entity's skeletal poses to either read the pose evaluated from animations bound to `BindTarget.jointTransforms` and `BindTarget.skeletalPose(_:)`, or write your own pose to animate the skeletal model."
- API:
  - `SkeletalPosesComponent(poses: SkeletalPoseSet)`, `var poses`.
  - `SkeletalPoseSet`: `default` (the first pose), `contains(_:)`, `index(of:)`, `set(_:)`, Collection conformance.
  - `SkeletalPose`: `init(id:from:)` (from the rest pose of a `MeshResource.Skeleton`), `init(id:joints:)`, `id`, `jointNames`, `jointTransforms`, `subscript(_:)`.
- Write rules (doc):
  - If `jointNames` is reordered, later animation updates match the new order.
  - Extra `jointTransforms` beyond `jointNames` are ignored.
  - If there are fewer transforms than names, the remaining joints are not updated.
  - "`poses.default` is the same skeletal pose as exposed by `jointNames` and `jointTransforms`."
- **Auto-attached**: "Any skinned mesh that's imported into RealityKit from a USD file will already have a SkeletalPosesComponent attached to the entity." The joint rotation you write "is in local space". The speaker updates it "from RealityKit's update function", i.e. a System, at most once per frame ([WWDC24 10102 transcript](https://developer.apple.com/videos/play/wwdc2024/10102/)) [V].
- Bind targets: `BindTarget.skeletalPose(String)` (iOS 18) and `BindTarget.jointTransforms` (iOS 15) ([skeletalPose(_:)](https://developer.apple.com/documentation/realitykit/bindtarget/skeletalpose(_:)), [jointTransforms](https://developer.apple.com/documentation/realitykit/bindtarget/jointtransforms)).

Apple's snippet from WWDC24 10102 (shown verbatim in the session code):
```swift
guard var component = entity.components[SkeletalPosesComponent.self] else { return }
component.poses.default?.jointTransforms[neckJointIndex].rotation = neckRotation
// then entity.components.set(component)  (the session says "commit the updated values to the component")
```

### 1.3 `MeshResource.Skeleton` and skinning data — iOS 18 / macOS 15 [V]

- `MeshResource.Skeleton` ([doc](https://developer.apple.com/documentation/realitykit/meshresource/skeleton)): `id`, `joints: [MeshResource.Skeleton.Joint]`, and these initialisers:
  - `init?(id: String, jointNames: [String], inverseBindPoseMatrices: [simd_float4x4], restPoseTransforms: [Transform]? = nil, parentIndices: [Int?]? = nil)` ([doc](https://developer.apple.com/documentation/realitykit/meshresource/skeleton/init(id:jointnames:inversebindposematrices:restposetransforms:parentindices:))). Rules: "A parent joint needs to precede all of its child joints"; "All the arrays … need to have the same length"; if `parentIndices` is nil, the parent is inferred from path-like names (`root/hips_joint`).
  - `init(id:joints:)`.
- Joint naming: the docs use **path-style names** (`root/hips_joint/left_upLeg_joint`). Blender's USD export also writes path-style joint tokens (`"root/neck/ear"`); I checked this locally (§2.6).
- `MeshResource.Part` ([doc](https://developer.apple.com/documentation/realitykit/meshresource/part)) has `skeletonID` and `jointInfluences: MeshResource.JointInfluences`, which is `init(influences:influencesPerVertex:)`. Doc: "Each vertex is associated with a fixed number of influences… padded with zero-weight influences" ([doc](https://developer.apple.com/documentation/realitykit/meshresource/jointinfluences)). `MeshJointInfluence(jointIndex:weight:)` describes linear-blend skinning whose weights sum to 1 ([doc](https://developer.apple.com/documentation/realitykit/meshjointinfluence)).
- `MeshResource.Contents` ([doc](https://developer.apple.com/documentation/realitykit/meshresource/contents-swift.struct)) has `models`, `instances` and `skeletons: MeshSkeletonCollection` (iOS 15; skeletons iOS 18). `MeshResource.generate(from: Contents)` and `replace(with: Contents)` (iOS 15) exist ([replace(with:)](https://developer.apple.com/documentation/realitykit/meshresource/replace(with:))).
- `MeshBufferContainer` (which `Part` conforms to) has `blendShapeNames`, `blendShapeOffsets(named:)` and `setBlendShapeOffsets(named:buffer:)` (iOS 18) ([doc](https://developer.apple.com/documentation/realitykit/meshbuffercontainer)). Contents-level editing therefore *can* carry blend shapes. Whether a rebuilt mesh keeps working with `BlendShapeWeightsComponent` is [I].
- `LowLevelMesh` (iOS 18) has **no joint/skin vertex semantic** (`VertexSemantic` lists position, normal, tangent, bitangent, color, uv0–uv7) ([doc](https://developer.apple.com/documentation/realitykit/lowlevelmesh/vertexsemantic)). So **LowLevelMesh cannot be skinned on iOS 26** [I, inferred from the API surface]. GPU deformers for this arrive only in iOS 27 (`MeshDeformerComponent`, `SkinningDeformer`).

### 1.4 How a UsdSkel USDZ loads

Verified Apple statements:
- RealityKit supports Skeletons, Skeleton animation and Blend Shapes from USD. **Double-sided meshes, vertex animation, USD lights, physics joints and Points are not supported by RealityKit** ([validating-usd-files](https://developer.apple.com/documentation/usd/validating-usd-files)) [V].
- "**Limit rigged models to a single skeleton** … merge all the skeletons into a single joint or bone hierarchy." "USD requires … any geometry that has a skeleton use the `SkelBindingAPI`" ([creating-usd-files](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices)) [V].
- `Entity(named:in:)` / `load` "preserve the entity hierarchy" and return the root. `loadModel(named:)` "flatten[s] the entity hierarchy into a single entity" ([Loading entities from a file](https://developer.apple.com/documentation/realitykit/loading-entities-from-a-file)) [V].
- An Apple engineer wrote: "In RealityKit, the skeleton joint positions are **not separate entities** with transform components" ([forum 792613](https://developer.apple.com/forums/thread/792613), [forum 798309](https://developer.apple.com/forums/thread/798309)) [V].
- A DTS engineer said USD Physics Joints/Constraints (e.g. a sword constrained to a hand) are not supported ([forum 772965](https://developer.apple.com/forums/thread/772965)) [V]. So **do not use Blender "Child Of" constraints for tack**. Use skinning to the bone, or attach at runtime.

Community-observed (not documented):
- **Every mesh skinned to one armature ends up in ONE `ModelEntity`.** Its `ModelComponent` plus `SkeletalPosesComponent` sit on the SkelRoot/armature entity. The per-mesh child entities have no geometry, so `cube.removeFromParent()` leaves the cube visible ([forum 784756](https://developer.apple.com/forums/thread/784756)) [C].
- Consequence [I]: "one ModelEntity per skinned mesh" is **not** what happens for meshes under one SkelRoot. Several meshes share one skeleton by living in one `MeshResource` (several models and parts, each part with `skeletonID`). To hide or show skinned accessories, either:
  - (a) rebuild the mesh from `contents` without those instances/parts (once per customisation change, not per frame), or
  - (b) export them as separate SkelRoot assets.

### 1.5 Maximum joints and influences per vertex — NOT documented

- No Apple page found states a maximum joint count or a maximum number of influences per vertex [V: absence after searching the docs, WWDC transcripts and forums].
- OpenUSD: "No restrictions are placed on the _elementSize_ when defining joint influences"; it offers `UsdSkelResizeInfluences` to enforce a client limit. Weights should be normalised and sorted largest first ([OpenUSD UsdSkel schemas doc, source on GitHub](https://github.com/PixarAnimationStudios/OpenUSD/blob/release/pxr/usd/usdSkel/doxygen/schemas.dox)) [V].
- The third-party `fbx2usd` converter, built "for RealityKit", limits output to 4 influences per vertex. That is the tool's own limit, not Apple's ([apparata/fbx2usd README](https://github.com/apparata/fbx2usd)) [C].
- **Recommendation [I]**:
  - Bake **≤ 4 influences per vertex**, normalised and sorted, in the Blender pipeline. Use `UsdSkelResizeInfluences` / `UsdSkelNormalizeWeights` in pxr post-processing.
  - Keep the deform skeleton lean, with helper and control bones excluded.
  - Test a worst case (the full skeleton plus ears, tail chain and mane chain) on the oldest target device with the RealityKit statistics overlay.

### 1.6 Joint pins and attaching entities to joints

- `Entity.pins: EntityGeometricPins` (iOS 18/macOS 15) ([doc](https://developer.apple.com/documentation/realitykit/entity/pins)) [V]. It provides:
  - `set(named:skeletalJointName:position:orientation:) -> GeometricPin` (iOS 18), where the position and orientation are "in local space of the joint" ([doc](https://developer.apple.com/documentation/realitykit/entitygeometricpins/set(named:skeletaljointname:position:orientation:))).
  - `set(named:position:orientation:)` and `remove(named:)`.
  - The doc says: "Pins for skeletal pose joints are not predefined, they need to be set … pass … full pose joint name or … leaf joint name". The pin pose is "the current pose of the joint in the coordinate frame of the Entity … While the skeletal pose is animated, the GeometricPin pose change[s] on every frame". Escape `.`, `[`, `]` and `\` in joint names.
  - ⚠️ Contradiction: the BOT-anist article says "RealityKit also automatically creates a collection of pins to represent the joints in a rigged model" ([BOT-anist](https://developer.apple.com/documentation/visionos/bot-anist)). **Assume you must create pins explicitly**, which the API reference says.
- **iOS 26 / macOS 26 (new at WWDC25)**: `func attach(_ source: GeometricPin? = nil, to target: GeometricPin)`, which is equivalent to adding `AttachedTransformComponent(source:target:)` ([attach(_:to:)](https://developer.apple.com/documentation/realitykit/entity/attach(_:to:)), [AttachedTransformComponent](https://developer.apple.com/documentation/realitykit/attachedtransformcomponent)) [V].
  - WWDC25: it "greatly simplifies attaching meshes to the joints of an animated skeleton … will also avoid expensive hierarchical transform updates" ([WWDC25 287](https://developer.apple.com/videos/play/wwdc2025/287/)).
  - Apple engineer: "In visionOS 26 we introduced `attach(_ to:)`, which is the new, recommended way to attach an Entity to a GeometricPin on another Entity" ([forum 798309](https://developer.apple.com/forums/thread/798309)).
- Before iOS 26, the pattern was the BOT-anist `JointPinSystem`, which multiplies the chain of `jointTransforms` matrices from root to joint every frame ([BOT-anist](https://developer.apple.com/documentation/visionos/bot-anist)) [V].

Sketch [I, untested]:
```swift
let headPin = pony.pins.set(named: "bridle_pin", skeletalJointName: "head",
                            position: [0, 0.02, 0.05], orientation: simd_quatf(ix:0,iy:0,iz:0,r:1))
bridleEntity.attach(to: headPin)            // iOS 26+ / macOS 26+
```

---

## 2. Animation

### 2.1 Resources and libraries — [V]

- `AnimationResource` (iOS 13) ([doc](https://developer.apple.com/documentation/realitykit/animationresource)):
  - `generate(with: any AnimationDefinition) throws` (iOS 15), `sequence(with:)`, `group(with:)`, `repeat(count:)`, `repeat(duration:)`. "The latter loops indefinitely if you omit the duration."
  - `name`, `definition`, `store(in:)`.
  - `makeActionAnimation(for:duration:…)` for `EntityAction`s (WWDC24 10102).
- `Entity.availableAnimations: [AnimationResource]` (iOS 13): "When you import an entity from a file … the entity might contain associated animations. Any that RealityKit supports appear" ([doc](https://developer.apple.com/documentation/realitykit/entity/availableanimations)).
- `AnimationLibraryComponent` (iOS 18/macOS 15) ([doc](https://developer.apple.com/documentation/realitykit/animationlibrarycomponent)): `init()`, `init(animations:)`, dictionary literal, `animations` (a keyed collection), `unkeyedResources`, `defaultAnimation`, `defaultKey`, `removeAll(resource:)`. The doc shows building a library from several files (`Entity(named:"idle").availableAnimations.first`) and saving with `write(to:)` into a `.reality` file.
  - "When a USD file has animations, RealityKit exposes them in an AnimationLibraryComponent" ([WWDC25 288](https://developer.apple.com/videos/play/wwdc2025/288/)).
  - BOT-anist builds one library per body by loading one USDZ per clip and reading `defaultAnimation` from the entity named `rig_grp` ([BOT-anist](https://developer.apple.com/documentation/visionos/bot-anist)).
  - ⚠️ `automaticallyPlaysDefaultAnimation` and `init(automaticallyPlaysDefaultAnimation:)` are **iOS 27** ([doc](https://developer.apple.com/documentation/realitykit/animationlibrarycomponent/automaticallyplaysdefaultanimation)).
- **Same skeleton, other file**: "As long as two rigged entities have the same joint hierarchy, they can use each other's animations" ([BOT-anist](https://developer.apple.com/documentation/visionos/bot-anist)) [V].
  - A forum report of "Invalid bind path: Ann_Body_anim_Neutral.RootNode.root.Root_M_bnd…" shows that bind paths include prim and entity names as well as joint names ([forum 719891](https://developer.apple.com/forums/thread/719891)) [C].
  - → **Export every clip file with identical SkelRoot/Skeleton prim names and identical joint tokens** [I].

### 2.2 Playing, cross-fading, layering — [V]

```swift
@discardableResult func playAnimation(_ animation: AnimationResource,
    transitionDuration: TimeInterval = 0, blendLayerOffset: Int = 0,
    separateAnimatedValue: Bool = false, startsPaused: Bool = false,
    clock: CMClockOrTimebase? = nil,
    handoffType: AnimationHandoffType = .default) -> AnimationPlaybackController   // iOS 18 / macOS 15
```
Source: [playAnimation(…handoffType:)](https://developer.apple.com/documentation/realitykit/entity/playanimation(_:transitionduration:blendlayeroffset:separateanimatedvalue:startspaused:clock:handofftype:)). The iOS 15 overload has no `handoffType` ([doc](https://developer.apple.com/documentation/realitykit/entity/playanimation(_:transitionduration:blendlayeroffset:separateanimatedvalue:startspaused:clock:))).

- Doc: "**RealityKit supports blending up to two different animations at the same time.** … Use the `blendLayerOffset` parameter to specify the order". The iOS 15 overload states: "Valid values are `0` or `1`."
- `separateAnimatedValue: true` writes to an interim value and resets to the base value when the animation completes.
- `AnimationHandoffType` (iOS 18) ([doc](https://developer.apple.com/documentation/realitykit/animationhandofftype)):
  - `.default`, which the doc says is `.snapshotAndReplace(applyToAllLayers: true)`.
  - `.replace(applyToAllLayers:)`: keeps playing the current animation during the transition and blends from its live value.
  - `.snapshotAndReplace(applyToAllLayers:)`.
  - `.compose`: adds to the existing animations.
  - `.stop`.
- `AnimationPlaybackController` ([doc](https://developer.apple.com/documentation/realitykit/animationplaybackcontroller)):
  - `speed`, `time`, `blendFactor` (`get set`, iOS 15). `blendFactor` sets the influence when several animations drive the same property ([doc](https://developer.apple.com/documentation/realitykit/animationplaybackcontroller/blendfactor)).
  - `pause()`, `resume()`, `stop()`, `stop(blendOutDuration:)` (iOS 18; the controller becomes invalid afterwards).
  - `isPlaying`, `isComplete`, `duration`.
  - The docs list it as `Observable`. WWDC25 says it "is now Observable" (stated for visionOS 26) ([WWDC25 274](https://developer.apple.com/videos/play/wwdc2025/274/)). That this also applies on iOS 26 is [I].
- `Entity.playAnimation(named:transitionDuration:startsPaused:recursive:)` is marked deprecated ([doc](https://developer.apple.com/documentation/realitykit/entity/playanimation(named:transitionduration:startspaused:recursive:))).
- Forum report: "Calling `playAnimation()` before the Entity is active in the scene" makes the controller complete immediately [C]. Play only after the entity has been added to the scene.

### 2.3 Cutting clips from one timeline — `AnimationView` (iOS 15 / macOS 12) [V]

```swift
init(source: any AnimationDefinition, name: String = "", bindTarget: BindTarget? = nil,
     blendLayer: Int32 = 0, repeatMode: AnimationRepeatMode = .none, fillMode: AnimationFillMode = [],
     trimStart: TimeInterval? = nil, trimEnd: TimeInterval? = nil, trimDuration: TimeInterval? = nil,
     offset: TimeInterval = 0, delay: TimeInterval = 0, speed: Float = 1.0)
```
Source: [AnimationView](https://developer.apple.com/documentation/realitykit/animationview) and [its init](https://developer.apple.com/documentation/realitykit/animationview/init(source:name:bindtarget:blendlayer:repeatmode:fillmode:trimstart:trimend:trimduration:offset:delay:speed:)). The doc example is `AnimationView(source:…, trimStart: 1.0, trimEnd: 2.0, …)` followed by `AnimationResource.generate(with: view)`.

Pony pipeline sketch [I, untested]:
```swift
let master = pony.availableAnimations.first!            // or AnimationLibraryComponent.defaultAnimation
func clip(_ name: String, _ f0: Double, _ f1: Double, fps: Double = 30, loop: Bool) throws -> AnimationResource {
    let v = AnimationView(source: master.definition, name: name,
                          repeatMode: loop ? .repeat : .none,
                          trimStart: f0 / fps, trimEnd: f1 / fps)
    return try AnimationResource.generate(with: v)
}
```
- Reality Composer Pro can slice the imported "default subtree animation" into named clips with the scissors tool ([WWDC24 10102](https://developer.apple.com/videos/play/wwdc2024/10102/)) [V].
- The USD schema RCP writes for clips appears to be a `RealityKitComponent "AnimationLibrary"` with `info:id = "RealityKit.AnimationLibrary"`, a `RealityKitClipDefinition` child (`clipNames`, `sourceAnimationName = "default subtree animation"`, `startTimes`), or `RealityKitAnimationFile` children (`file`, `name`). This comes from a third-party tool that says it "matches Reality Composer Pro's pattern" ([fbx2usd source](https://github.com/apparata/fbx2usd)) [C].
  - Apple does not publicly document this schema. Whether RealityKit honours it when loading a plain `.usdz` at runtime (outside an RCP-compiled `.reality`) is [I]. **Prefer trimming in code, or one USD file per clip as BOT-anist does.**

### 2.4 Procedural and blend-tree animation types — [V]

- `JointTransforms` (iOS 15): an animatable collection of `Transform` for one skeletal pose ([doc](https://developer.apple.com/documentation/realitykit/jointtransforms)).
- `FromToByAnimation<JointTransforms>(jointNames:name:isScaleAnimated:isRotationAnimated:isTranslationAnimated:from:to:by:duration:timing:isAdditive:bindTarget:blendLayer:repeatMode:fillMode:trimStart:trimEnd:trimDuration:offset:delay:speed:)` (iOS 15) ([doc](https://developer.apple.com/documentation/realitykit/fromtobyanimation/init(jointnames:name:isscaleanimated:isrotationanimated:istranslationanimated:from:to:by:duration:timing:isadditive:bindtarget:blendlayer:repeatmode:fillmode:trimstart:trimend:trimduration:offset:delay:speed:))). It has `isAdditive`. Use `bindTarget: .jointTransforms`.
- `SampledAnimation<JointTransforms>(jointNames:frames:…frameInterval:isAdditive:…)` (iOS 15), for runtime-generated clips such as procedural head shakes ([doc](https://developer.apple.com/documentation/realitykit/sampledanimation)).
- `FromToByAnimation(weightNames:…)` for blend-shape weights (iOS 18) ([doc](https://developer.apple.com/documentation/realitykit/fromtobyanimation/init(weightnames:name:from:to:by:duration:timing:isadditive:bindtarget:blendlayer:repeatmode:fillmode:trimstart:trimend:trimduration:offset:delay:speed:))).
- `AnimationGroup(group:name:repeatMode:fillMode:trimStart:trimEnd:trimDuration:offset:delay:speed:)` (iOS 15). Ordering rule: "The framework processes animations with a lower `blendLayer` first … If two animations on the same property overlap … the one that the framework processes second overwrites the first" ([doc](https://developer.apple.com/documentation/realitykit/animationgroup)).
- `BlendTreeAnimation<Value>` (iOS 15), with `BlendTreeBlendNode`, `BlendTreeSourceNode(source:name:weight:)`, `isAdditive`, and `BlendWeight.value(_:)` / `.parameter(String, defaultWeight:)` / `.bindTarget(_:defaultWeight:)` ([BlendTreeAnimation](https://developer.apple.com/documentation/realitykit/blendtreeanimation), [BlendWeight](https://developer.apple.com/documentation/realitykit/blendweight)). The doc example blends two `JointTransforms` animations 25/75. Its tip: "To modify the weights for each frame, create a source node with a dynamic `BlendWeight`, such as … `BlendWeight.parameter(_:defaultWeight:)`." Parameters live in `Entity.parameters: Entity.ParameterSet` (iOS 15; "a reference and does not have copy-on-write semantics") ([doc](https://developer.apple.com/documentation/realitykit/entity/parameters)).
  - → A walk/trot/canter blend tree whose weights are driven by speed is possible on iOS 26 [I: the exact subscript/value type for writing a Float parameter is not shown in the iOS 26 docs. The iOS 27 docs show `entity.parameters["MoveSpeed"] = BindableValue(Float(1.0))` for animation graphs ([AnimationGraphResource](https://developer.apple.com/documentation/realitykit/animationgraphresource)), which suggests the same pattern].
  - Phase sync between gaits of different lengths is not documented [I]. Author the gait cycles with normalised phase, for example by speeding up or slowing down the clips to match lengths.
- `BindTarget` cases ([doc](https://developer.apple.com/documentation/realitykit/bindtarget)): `.transform`, `.jointTransforms`, `.parameter(_)`, `.path(_)`, `.entity(_)…`, `.opacity`, `.blendShapeWeights`, `.blendShapeWeightsAtIndex`, `.blendShapeWeightsWithID`, `.skeletalPose(_)`, `.material(_)`, and `IkSolverPath` (iOS 18: `constraintTarget(_:)`, `constraintLookAtTarget(_:)`). That makes IK targets animatable ([doc](https://developer.apple.com/documentation/realitykit/bindtarget/iksolverpath)). `.rootMotion` is iOS 27.

### 2.5 Can a custom System override joints after animation? Is ordering defined?

- `System` ([doc](https://developer.apple.com/documentation/realitykit/system)) [V]:
  - "Systems and their dependencies form a directed acyclic graph (DAG). **Custom systems are executed in dependency order.** Systems without dependencies are updated in the order they were registered. If there are conflicting dependencies or cycles, RealityKit ignores some … and logs a warning. Each system instance is only run once per simulation step."
  - `static var dependencies: [SystemDependency]` with `.before(System.Type)` and `.after(System.Type)` ([doc](https://developer.apple.com/documentation/realitykit/systemdependency)).
- **Ordering relative to built-in systems (animation, skeletal pose, IK, physics) is NOT documented.** RealityKit exposes no public system type for the animation system to depend on [V: absence in the docs].
- `AnimationEvents.SkeletalPoseUpdateComplete` (iOS 18/macOS 15): "**Raised immediately after the SkeletalPoseSystem has been updated**". It has `deltaTime` ([doc](https://developer.apple.com/documentation/realitykit/animationevents/skeletalposeupdatecomplete)) [V].
  - An Apple engineer used it to *read* final `jointTransforms` and copy them to proxy entities ([forum 761893](https://developer.apple.com/forums/thread/761893)) [V].
  - Whether *writing* `SkeletalPosesComponent` inside this event is honoured in the same frame or overwritten next frame is **unknown** [I] → test on device.
- Community evidence: playing a skeletal clip overwrites programmatic joint and blend-shape changes ([forum 793431](https://developer.apple.com/forums/thread/793431), [forum 797407](https://developer.apple.com/forums/thread/797407)) [C]. Community workarounds: clips that don't animate certain joints, plus separate `FromToByAnimation`s on other blend layers [C].
- **Apple-recommended solution [V]**: "creating a constraint for the head or neck joint and increasing its `animationOverrideWeight` to 1 should allow you to freely orient the character's head using inverse kinematics while other animations are playing" (Apple engineer, [forum 797407](https://developer.apple.com/forums/thread/797407)).
- ⚠️ Doc contradiction on the direction of `.before`/`.after`. The enum doc and the code sample (`.after(SystemA.self) // Run SystemB after SystemA`) agree that `.after(X)` means *this system runs after X*. The article prose ("To tell RealityKit that a dependency must update before your system, use `.before`") says the opposite ([Implementing systems](https://developer.apple.com/documentation/realitykit/implementing-systems-for-entities-in-a-scene)). Follow the code sample, and verify with logging [I].

### 2.6 Local check: what Blender 4.2 writes into a USD `SkelAnimation` (relevant to layering)

Experiment, run in this container with bpy 4.2.0 + `wm.usd_export(export_animation=True, export_armatures=True, export_shapekeys=True)`:
- Setup: a 3-bone armature (root → neck → ear) where **only `neck` is keyed**, and a cube with one shape key `Fat`.
- Output:
  - `def SkelRoot "Armature"` contains `def Skeleton` with `uniform token[] joints = ["root", "root/neck", "root/neck/ear"]` and `rel skel:animationSource`.
  - `def SkelAnimation "Anim"` contains `joints` = **all 3 joints**, `rotations`/`translations`/`scales` timeSamples for all of them at every frame, **and** `blendShapes = ["Fat"]` plus `blendShapeWeights.timeSamples` (all 0).
  - The mesh carries `skel:blendShapes`, `skel:blendShapeTargets` and `skel:skeleton`, plus `def BlendShape "Fat"`.
- Implication [I]: every clip exported from Blender drives **every joint and every blend-shape weight**. Played on the pony, a clip would reset the morphology sliders, the ears and the tail. This matches the forum symptom "BlendShapes don't animate while playing animation" ([forum 793431](https://developer.apple.com/forums/thread/793431)) [C].
- Mitigation: post-process each clip USD with `pxr` and remove `blendShapes`/`blendShapeWeights` from the `SkelAnimation`.
  - Optionally author a **sparse** `joints` subset. UsdSkel explicitly allows an animation to be "a sparse subset of joints" ([UsdSkel schemas.dox](https://github.com/PixarAnimationStudios/OpenUSD/blob/release/pxr/usd/usdSkel/doxygen/schemas.dox)) [V for USD]. **Whether RealityKit leaves unlisted joints free for procedural control is [I] and must be tested.**

### 2.7 iOS 27-only animation features (do not use with a 26 deployment target) [V]
- `AnimationGraphResource` / `AnimationGraphComponent`: state machines, blending, tags, and parameters set via `entity.parameters` ([doc](https://developer.apple.com/documentation/realitykit/animationgraphcomponent)).
- `SkeletonResource`: blend masks, IK bundled with the skeleton.
- `RetargetingConfiguration`, including `automatchQuadruped(_:sourceTransform:to:targetTransform:jointOffsets:)` ([doc](https://developer.apple.com/documentation/realitykit/retargetingconfiguration)).
- `AnimationEvents.RootMotionDidUpdate` and `BindTarget.rootMotion`. The event "fires after animation evaluation but before the resulting skeletal pose is applied to the mesh" ([doc](https://developer.apple.com/documentation/realitykit/animationevents/rootmotiondidupdate)).
- `MeshDeformerComponent`, `SkinningDeformer`, `BlendShapeDeformer`, `SubdivisionSurfaceDeformer` and `LowLevelDeformation` ([Mesh deformation](https://developer.apple.com/documentation/realitykit/scene-content-mesh-deformation)).
- `IKRig(named:rootJoint:)`.

These would solve several of the problems above (layering, masks, root motion). They are worth considering if the deployment target can move to 27.

---

## 3. Inverse kinematics — `IKRig`, `IKResource`, `IKComponent` (iOS 18 / macOS 15 / visionOS 2) [V]

Sources: [IKComponent](https://developer.apple.com/documentation/realitykit/ikcomponent), [IKRig](https://developer.apple.com/documentation/realitykit/ikrig), [IKResource](https://developer.apple.com/documentation/realitykit/ikresource), [IKRig.Constraint](https://developer.apple.com/documentation/realitykit/ikrig/constraint), [IKRig.Joint](https://developer.apple.com/documentation/realitykit/ikrig/joint), [IKComponent.Constraint](https://developer.apple.com/documentation/realitykit/ikcomponent/constraint), [WWDC24 10102](https://developer.apple.com/videos/play/wwdc2024/10102/).

- **Rig**:
  - Create it with `init(for skeleton: MeshResource.Skeleton) throws`, where the skeleton comes from `modelComponent.mesh.contents.skeletons[0]` ([doc](https://developer.apple.com/documentation/realitykit/ikrig/init(for:))).
  - Properties: `maxIterations: Int` (0 or less keeps the last solved pose), `globalFkWeight`, `globalLimitsWeight`, `joints: IKRig.JointCollection` (indexable by joint name), and `constraints`.
- **`IKRig.Joint`**: `active`, `fkWeightPerAxis`, `rotationStiffness`, `limits: IKRig.Joint.LimitsDefinition?`, and `restTransform`.
  - `LimitsDefinition(weight:boneAxis:minimumAngles:maximumAngles:)`, in radians, as deltas from the rest pose; "minimum angles need to be less than the maximum angles" ([doc](https://developer.apple.com/documentation/realitykit/ikrig/joint/limitsdefinition)).
- **Constraint factories (`IKRig.Constraint`)**:
  - `.point(named:on:positionWeight:)`
  - `.orient(named:on:orientationWeight:)`
  - `.parent(named:on:positionWeight:orientationWeight:)`
  - `.lookAtAbsolute(named:on:lookingAlong:orientationWeight:)`, where the target axis is in **model space**
  - `.lookAtAdditive(named:on:lookingAlong:orientationWeight:)`, where the axis is in the **joint's local space** ([doc](https://developer.apple.com/documentation/realitykit/ikrig/constraint/lookatadditive(named:on:lookingalong:orientationweight:)))
- **Resource and component**: `IKResource(rig:) throws`, then `IKComponent(resource:)`.
- **Runtime**: `component.solvers[0]` is an `IKComponent.Solver`, with `constraints`, `joints`, `globalFkWeight`, `maxIterations` and `reset()`. Each constraint is an `IKComponent.Constraint` with:
  - `target: Transform`: "targets … in **model space**".
  - `lookAtTargetPosition: SIMD3<Float>`: model space; "The computed demand overrides the rotation part of `target`".
  - `animationOverrideWeight: (position: Float, rotation: Float)`: 0 = from the FK (animation) pose, 1 = your target. **The defaults are 0.**
  - `offset` and `demands`.
- **The forward-kinematics input is the animation pose**: "The solver uses the animation pose stored in the `SkeletalPosesComponent`." IK therefore runs on top of clips.
- "Any value updates won't be reflected until the modified `IKComponent` is set on the `Entity`." Call `entity.components.set(component)` every frame.
- WWDC24: "RealityKit's IK solver will solve over the **full character skeleton simultaneously**". Their tuning was `maxIterations = 30` and `globalFkWeight = 0.02`.
- An Apple engineer showed a skeleton built with `MeshResource.Skeleton(...)` plus a dummy mesh to drive IK on non-skinned hierarchies ([forum 761893](https://developer.apple.com/forums/thread/761893)).

Pony recipes [I, untested sketches]:
- **Head/neck look-at**:
  - Add `lookAtAdditive(named:"look", on:".../head", lookingAlong:[0,0,1], orientationWeight:[w,w,w])`, plus lighter constraints or stiffness on the neck joints.
  - Each frame, set `lookAtTargetPosition` (converted to the pony's model space with `entity.convert(position:from:)`) and ramp `animationOverrideWeight.rotation` 0→1.
  - Clamp with joint `limits`.
- **Foot/hoof IK on uneven ground**:
  - Add `.point` constraints on the four hoof joints and a `.parent` on the pelvis/withers.
  - Per frame, raycast down from each hoof using `scene.raycast(origin:direction:length:query:mask:relativeTo:)` (iOS 13; hits only entities with `CollisionComponent`) ([doc](https://developer.apple.com/documentation/realitykit/scene/raycast(origin:direction:length:query:mask:relativeto:))).
  - Set `target.translation` and blend `animationOverrideWeight.position` by the stance phase. Swing feet stay at 0.
- **Ears and tail**: use IK orient constraints, or (if sparse clips are confirmed to work, §2.6) direct `SkeletalPosesComponent` writes on joints that the clips don't animate.

---

## 4. Blend shapes (morphology sliders, facial expressions)

### 4.1 Runtime API — iOS 18 / macOS 15 / visionOS 2 [V]

- `BlendShapeWeightsMapping` (a class, and a `Resource`) ([doc](https://developer.apple.com/documentation/realitykit/blendshapeweightsmapping)):
  - `init(meshResource:)`: the mapping "map[s] exactly to the MeshResource's structure".
  - `init(blendShapeName:weightNames:)`: "RealityKit expects the ModelComponent to already be assigned … If a weight name does not match any of the mesh weight names then it is ignored".
- `BlendShapeWeightsComponent(weightsMapping:)` with `var weightSet: BlendShapeWeightsSet` ([doc](https://developer.apple.com/documentation/realitykit/blendshapeweightscomponent), [weightSet](https://developer.apple.com/documentation/realitykit/blendshapeweightscomponent/weightset)). Rules for assigning:
  - A new set must have the same count and the same names.
  - Changed names are ignored, and a wrong count is ignored.
- `BlendShapeWeightsSet` ([doc](https://developer.apple.com/documentation/realitykit/blendshapeweightsset)) is a collection of `BlendShapeWeightsData` (`id`, `weightNames`, `weights: BlendShapeWeights`). It has `default`, `subscript(blendShapeName:)`, `set(_:)`, and index access. "does not support addition/removal of elements".
- `BlendShapeWeights` is an animatable collection of Float (`init(_:)`, array literal) ([doc](https://developer.apple.com/documentation/realitykit/blendshapeweights)).
- Alternative accessors: `HasModel.blendWeightNames` / `blendWeights` (iOS 18).
- Animation: bind targets `.blendShapeWeights`, `.blendShapeWeightsAtIndex`, `.blendShapeWeightsWithID`, and `FromToByAnimation(weightNames:…)`.
- **Auto-creation**: "RealityKit automatically creates a `BlendShapeWeightsComponent` for any model entity it loads from a USDZ file that contains blend shapes. It also adds any blend shape animations in the USDZ file to the entity's `AnimationLibraryComponent`" ([BOT-anist](https://developer.apple.com/documentation/visionos/bot-anist)).
- BOT-anist code: `blendComponent.weightSet[0].weights = BlendShapeWeights([0, 1, 0, 0, 0, 0, 0])`.
- ⚠️ Doc inconsistency: the component overview uses `weightSets[0]` but the property is `weightSet`. Use `weightSet`.

Sketch [I, untested]:
```swift
var bsc = pony.components[BlendShapeWeightsComponent.self]!
var set = bsc.weightSet
if let i = set[0].weightNames.firstIndex(of: "body_stocky") { set[0].weights[i] = slider }
bsc.weightSet = set
pony.components.set(bsc)
```

### 4.2 USD requirements for import

- **[V, OpenUSD]** ([UsdSkel schemas.dox](https://github.com/PixarAnimationStudios/OpenUSD/blob/release/pxr/usd/usdSkel/doxygen/schemas.dox)):
  - The mesh must be under a `SkelRoot`: "bindings defined on any primitives that do not have a UsdSkelRoot primitive as one of their ancestors have no meaning".
  - `UsdSkelBindingAPI` must be applied, with `skel:skeleton`.
  - Blend shapes are bound with `uniform token[] skel:blendShapes` plus `rel skel:blendShapeTargets` pointing at `BlendShape` prims (`offsets`, optional `pointIndices`, optional `normalOffsets`, optional `inbetweens:*`). These properties "are *not* inherited … relevant only when specified directly on primitives".
  - Weight animation lives in the `SkelAnimation` `blendShapes`/`blendShapeWeights`. "Blend shape application precedes the effect of skinning."
- **[V, Apple]**: Blend shapes are supported by RealityKit, and `SkelBindingAPI` is needed for skinned geometry ([validating-usd-files](https://developer.apple.com/documentation/usd/validating-usd-files), [creating-usd-files](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices)).
- **[V, local]**: Blender 4.2's exporter writes exactly this structure (§2.6).
- **[I]**:
  - RealityKit support for **in-between shapes** and **normalOffsets** is not documented. Avoid in-betweens, or test them.
  - Blend shapes on a mesh **without** a skeleton (rigid prop with shape keys) are not documented. Keep everything under the SkelRoot.
  - Sparse `pointIndices`: supported by USD, unverified in RealityKit.
- Morphology design note [I]: blend shapes deform the mesh before skinning, so **proportion changes such as leg length need joint/bone changes too**, otherwise the joints won't follow the deformed mesh. Options:
  - Scale joints in a "base pose" by writing rest-pose offsets through the `SkeletalPose` each frame on top of the animation (but see §2.5), or
  - Use IK, or
  - Limit sliders to volume/shape changes (girth, neck thickness, head shape) and handle size through uniform entity scale.

---

## 5. Materials and textures

### 5.1 `PhysicallyBasedMaterial` (iOS 15 / macOS 12; tvOS 26) [V]

Source: [PhysicallyBasedMaterial](https://developer.apple.com/documentation/realitykit/physicallybasedmaterial); [Applying realistic material and lighting effects](https://developer.apple.com/documentation/realitykit/applying-realistic-material-and-lighting-effects-to-entities).

| Property | Notes | Min OS |
|---|---|---|
| `baseColor: BaseColor(tint:texture:)` | "multiplying the color at any given pixel by `tint`"; `tint` is `UIColor` on iOS/Catalyst and `NSColor` on macOS ([doc](https://developer.apple.com/documentation/realitykit/physicallybasedmaterial/basecolor-swift.struct/init(tint:texture:)-2wriz)) | 15/12 |
| `roughness`, `metallic`, `normal`, `ambientOcclusion`, `specular` | scalar or texture | 15/12 |
| `clearcoat`, `clearcoatRoughness`, `clearcoatNormal` | patent leather, varnished hooves | 15/12 |
| `sheen: SheenColor?` | "subtle reflections … on … fabrics" → saddle pads, rugs, polo wraps | 15/12 |
| `anisotropyLevel`, `anisotropyAngle` | "straight hair" highlights (the doc uses this example) | 15/12 |
| `emissiveColor`, `emissiveIntensity` | — | 15/12 |
| `blending: .opaque / .transparent(opacity:)` | — | 15/12 |
| `opacityThreshold: Float?` | alpha mask: "discards pixels with opacity values less than the `opacityThreshold` … renders [others] fully opaque … the blend mode of the `blending` property is ignored" ([doc](https://developer.apple.com/documentation/realitykit/physicallybasedmaterial/opacitythreshold)). The article says "less than or equal" — a minor inconsistency | 15/12 |
| `faceCulling` | default `.back`; can cull front or none ([doc](https://developer.apple.com/documentation/realitykit/physicallybasedmaterial/faceculling-swift.property)) | 15/12 |
| `textureCoordinateTransform`, `secondaryTextureCoordinateTransform` | — | 15/12 |
| `readsDepth`, `writesDepth` | — | 18/15 |
| `triangleFillMode`, `init(program:)`, `Program` | — | 18/15 |
| `subsurfaceColor/Weight/Radius…`, `bentNormal`, `enableSpecularOcclusion` | **iOS 27 only** | 27 |

Mane, tail and forelock cards [V facts + I advice]:
- The USD import table lists **"Double-sided meshes: not supported" for RealityKit** ([validating-usd-files](https://developer.apple.com/documentation/usd/validating-usd-files)). After loading, set `faceCulling = .none` on the hair materials, or model both sides.
- Prefer `opacityThreshold` (alpha test) over blending. Apple: "Use geometry instead of alpha-clipped cards … Limit the use of semi-transparent materials" ([creating-usd-files](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices)). Apple's character article (written for iOS 27 features, but the hair advice is generic) recommends:
  - an opaque base layer for the scalp, i.e. the mane root;
  - cards fitted tightly to the alpha;
  - fewer overlapping translucent layers ([Rendering high-fidelity characters](https://developer.apple.com/documentation/realitykit/rendering-high-fidelity-characters)).
- For sorting translucent layers: `ModelSortGroupComponent` (iOS 18) ([doc](https://developer.apple.com/documentation/realitykit/modelsortgroupcomponent)).

USD-import material facts [V] ([validating-usd-files](https://developer.apple.com/documentation/usd/validating-usd-files), [creating-usd-files](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices)):
- "When you import models from USDZ files, RealityKit automatically creates one or more `PhysicallyBasedMaterial` instances".
- Use the metallic workflow; the specular workflow is unsupported.
- **2 UV sets max**.
- "only a single packed texture per material", though multiple scalar channels of it can be referenced.
- A single `UsdTransform2d` per material.
- No texture scale on normal maps.
- Normal maps in **OpenGL convention**.
- sRGB for colour textures, linear for data.
- USDZ textures can only be **JPEG, PNG, EXR or AVIF**.
- **The default `subdivisionScheme` is catmullClark, so set `none` explicitly.**

### 5.2 `ShaderGraphMaterial` (iOS 18 / macOS 15 / visionOS 1) [V]

Source: [ShaderGraphMaterial](https://developer.apple.com/documentation/realitykit/shadergraphmaterial).
- Initialisers:
  - `init(named name: String, from file: String, in bundle: Bundle? = nil) async throws`. `name` is "the full path of the material prim (such as "/Root/MyMaterial")". Formats: .usd, .usda, .usdc, .usdz and .reality ([doc](https://developer.apple.com/documentation/realitykit/shadergraphmaterial/init(named:from:in:))).
  - `init(named:from: Data) async throws`.
  - `init(materialXLabel:data:) async throws`.
  - `init(program:)`.
- Parameters: `parameterNames`, `mutating func setParameter(name: String, value: MaterialParameters.Value) throws`, `getParameter(name:)`, and `static func parameterHandle(name:)` with `setParameter(handle:value:)`.
- `MaterialParameters.Value` cases: `.bool`, `.int`, `.float`, `.simd2Float/3/4`, `.color`, `.float2x2/3x3/4x4`, `.texture`, `.textureResource` ([doc](https://developer.apple.com/documentation/realitykit/materialparameters/value)).
- Also exposes `faceCulling`, `readsDepth`, `writesDepth` and `triangleFillMode`.
- To use it from a Reality Composer Pro package: `try await ShaderGraphMaterial(named: "/Root/CoatMat", from: "Pony.usda", in: realityKitContentBundle)` [I: the bundle symbol is the RCP package's generated bundle].
- RealityKit applies subdivision only to objects with a USD preview surface shader. "Objects with custom MaterialX materials use standard polygonal meshes" ([validating-usd-files](https://developer.apple.com/documentation/usd/validating-usd-files)).

### 5.3 Runtime textures [V]

Source: [TextureResource](https://developer.apple.com/documentation/realitykit/textureresource).
- `convenience init(image: CGImage, withName: String? = nil, options: TextureResource.CreateOptions) async throws` (**iOS 18/macOS 15**). Note that the real label is `image:withName:options:` and **`options` has no default** ([doc](https://developer.apple.com/documentation/realitykit/textureresource/init(image:withname:options:))).
- `static func generate(from:withName:options:) throws` is **deprecated since iOS 18 / macOS 15 / visionOS 2** ([doc](https://developer.apple.com/documentation/realitykit/textureresource/generate(from:withname:options:))).
- Replacing contents:
  - `func replace(withImage: CGImage, options:) throws` (iOS 15). It "blocks until the resource updates. **Don't use this method for updates at frame-rate frequency**."
  - `func replace(using: CGImage, options:) async throws` (iOS 18).
  - `replace(withDrawables:)` for frame-rate updates.
  - `replace(with: LowLevelTexture)` (iOS 18). It "marks the asset as mutated, preventing newly loaded entities from sharing the texture" ([doc](https://developer.apple.com/documentation/realitykit/textureresource/replace(with:))).
- Other creation paths:
  - `TextureResource(dimensions:format:contents:) async throws` (iOS 18), from raw bytes or an `MTLBuffer` with mip levels ([doc](https://developer.apple.com/documentation/realitykit/textureresource/init(dimensions:format:contents:))).
  - `CreateOptions(semantic:mipmapsMode:)` and `CreateOptions(semantic:compression:mipmapsMode:)`.
  - `texture2DArray(slices:…)`, `cube(slices:…)`, `texture3D(slices:…)`.
- `LowLevelTexture` (iOS 18/macOS 15) ([doc](https://developer.apple.com/documentation/realitykit/lowleveltexture)):
  - Create it with `LowLevelTexture(descriptor:)` (`textureType`, `width`, `height`, `pixelFormat`, `textureUsage`, `mipmapLevelCount`, `swizzle`).
  - Wrap it with `TextureResource(from:)`. The declaration is `async throws` even though the doc sample omits `await`.
  - GPU writes go through `let mtlTex = texture.replace(using: commandBuffer)` plus a compute encoder. "When the command buffer completes, RealityKit automatically applies the changes."
- Recommended recolouring options for the pony [I]:
  - (a) Author **mask textures** (coat, white markings, dapples, points) and a ShaderGraph or CustomMaterial that mixes the colour parameters. This is cheapest at runtime: only `setParameter` calls.
  - (b) Composite with CoreGraphics on customisation change, then `replace(using:options:)`.
  - (c) Run a `LowLevelTexture` compute kernel for live painting.

### 5.4 `CustomMaterial` [V]

- Available on **iOS 15, iPadOS 15, Mac Catalyst 15, macOS 12 and tvOS 26. It is not available on visionOS** ([doc](https://developer.apple.com/documentation/realitykit/custommaterial)). It is therefore usable for both of this game's targets.
- Surface shaders and geometry modifiers, written in Metal (`init(from:surfaceShader:geometryModifier:)`, `init(surfaceShader:geometryModifier:lightingModel:)`).
- Shader data: `custom` and `withMutableUniforms(ofType:stage:_:)`.
- Also exposes `opacityThreshold`, `blending`, `faceCulling`, `readsDepth` and `writesDepth`.
- Its property list has no `sheen`.
- Interaction with skinning, i.e. whether a geometry modifier runs before or after skinning, is not documented [I].

---

## 6. Systems, components, views, lighting, physics

### 6.1 ECS [V]

- `System` (iOS 15/macOS 12): `init(scene:)`, `update(context: SceneUpdateContext)`, `static var dependencies`, and `registerSystem()` ([doc](https://developer.apple.com/documentation/realitykit/system)). `Component.registerComponent()` is needed for custom component types ([doc](https://developer.apple.com/documentation/realitykit/component/registercomponent())).
- `EntityQuery(where: .has(MyComponent.self))` plus `context.entities(matching:updatingSystemWhen: .rendering)` (iOS 18) ([doc](https://developer.apple.com/documentation/realitykit/sceneupdatecontext/entities(matching:updatingsystemwhen:))). `SystemUpdateCondition` documents only `.rendering` ([doc](https://developer.apple.com/documentation/realitykit/systemupdatecondition)). `SceneUpdateContext` exposes `scene` and `deltaTime`.
- Systems are created per scene by RealityKit. "Properties of a system are never serialized … store data on entities using components" ([doc](https://developer.apple.com/documentation/realitykit/system)).
- iOS 26 additions:
  - `Entity.observable` (Observation of transform, children and components) ([doc](https://developer.apple.com/documentation/realitykit/entity/observable-swift.property)).
  - `Entity.animate(_:body:completion:)`, which animates component changes with SwiftUI animations ([doc](https://developer.apple.com/documentation/realitykit/entity/animate(_:body:completion:)), [WWDC25 274](https://developer.apple.com/videos/play/wwdc2025/274/)).
  - `GestureComponent` (listed for iOS 26) ([doc](https://developer.apple.com/documentation/realitykit/gesturecomponent)).

### 6.2 `RealityView` on iOS / macOS [V]

- Initialiser: `RealityView(make: (inout RealityViewCameraContent) async -> Void, update: ((inout RealityViewCameraContent) -> Void)? = nil)` (iOS 18/macOS 15) ([doc](https://developer.apple.com/documentation/realitykit/realityview/init(make:update:)-234sv)). `RealityViewContent` is visionOS-only.
- `RealityViewCameraContent` ([doc](https://developer.apple.com/documentation/realitykit/realityviewcameracontent)):
  - `camera: RealityViewCamera`: `.virtual`, plus `.spatialTracking`, which is **iOS/iPadOS only** ([doc](https://developer.apple.com/documentation/realitykit/realityviewcamera)).
  - `cameraTarget: Entity?` (the orbit target).
  - `environment: RealityViewEnvironment`: `.default` or `.skybox(EnvironmentResource)`.
  - `renderingEffects`: `antialiasing`, `cameraGrain`, `depthOfField`, `dynamicRange`, `motionBlur` (iOS 18), and `customPostProcessing` (**iOS 26**, with `PostProcessEffect`) ([doc](https://developer.apple.com/documentation/realitykit/realityviewrenderingeffects)).
  - `audioListener` and `subscribe(to:on:componentType:_:)`.
- `.realityViewCameraControls(_ controls: CameraControls)` (iOS 18, macOS 15, Catalyst; **not tvOS**). Options are `.orbit`, `.pan`, `.tilt`, `.dolly` and `.none`, driven by "a drag gesture from a mouse, trackpad, or screen touches" ([doc](https://developer.apple.com/documentation/swiftui/view/realityviewcameracontrols(_:))).
- For a game camera: use `PerspectiveCameraComponent` (`near`, `far`, `fieldOfViewInDegrees`) on your own follow-camera entity. Apple's iOS 26 Pyro Panda sample uses a `WorldCameraComponent` (azimuth/elevation/radius) plus a `FollowComponent`, and adds `PerspectiveCameraComponent` `#if !os(visionOS)` ([Bringing your SceneKit projects to RealityKit](https://developer.apple.com/documentation/realitykit/bringing-your-scenekit-projects-to-realitykit)).
- Non-AR anchoring [I]: with `.virtual`, you `content.add(entity)` directly. `AnchorEntity(world:)` is optional. No Apple page states that anchoring is required for virtual content.

### 6.3 Ground, shadows, lighting [V]

- `GroundingShadowComponent` (iOS 18/macOS 15) ([doc](https://developer.apple.com/documentation/realitykit/groundingshadowcomponent)):
  - `init(castsShadow:)`, `init(castsShadow:receivesShadow:)`, `castsShadow`, `receivesShadow`.
  - "**the grounding shadow component doesn't apply to hierarchies**" → add it to every model entity, including the merged pony mesh and each accessory.
  - "Neither virtual nor physical light sources affect grounding shadows."
  - One-sided geometry casts only if its faces point towards the receiver.
  - `fadeBehaviorNearPhysicalObjects` is listed for iOS/visionOS only.
- Dynamic lights:
  - `DirectionalLightComponent` (iOS 13/macOS 10.15) plus `DirectionalLightComponent.Shadow` (itself a component). Shadow options: `depthBias`, `cullModeOverride`, `shadowProjection` (iOS 18), `maximumDistance` (deprecated). `cascades` and `init(layers:)` are **iOS 27** ([doc](https://developer.apple.com/documentation/realitykit/directionallightcomponent/shadow)).
  - `SpotLightComponent` and `PointLightComponent`. "only spotlight and directional light can cast shadows" ([WWDC24 10103](https://developer.apple.com/videos/play/wwdc2024/10103/)).
  - `DynamicLightShadowComponent.castsShadow` opts entities out (iOS 18).
  - WWDC25 288: "For RealityKit, I create an entity with two components; a directional light component and a directional light shadow component" ([WWDC25 288](https://developer.apple.com/videos/play/wwdc2025/288/)).
- **RealityKit does not use lights included in a USD file** ([validating-usd-files](https://developer.apple.com/documentation/usd/validating-usd-files)).
- IBL:
  - `ImageBasedLightComponent(source: .single(EnvironmentResource) | .blend(_,_,Float) | .none, intensityExponent:)` and `inheritsRotation`, plus `ImageBasedLightReceiverComponent(imageBasedLight: Entity)` (iOS 18) ([doc](https://developer.apple.com/documentation/realitykit/imagebasedlightcomponent)). Whether receivers apply hierarchically is not documented [I].
  - `EnvironmentResource`:
    - `init(named:in:) async throws` (iOS 18; **deprecated in 27.2**, so fine for a 26 target).
    - `init(equirectangular:withName:) async throws` (iOS 18; deprecated 27.2).
    - `init(cube:options:) async throws` (iOS 18).
    - `init(named:in:skyboxMode:)` and `init(equirectangular:options:)` are **iOS 27** ([doc](https://developer.apple.com/documentation/realitykit/environmentresource)).
  - `VirtualEnvironmentProbeComponent` and `EnvironmentLightingConfigurationComponent` (iOS 18).

### 6.4 Physics and the character controller [V]

- `CharacterControllerComponent` (iOS 15/macOS 12) ([doc](https://developer.apple.com/documentation/realitykit/charactercontrollercomponent)):
  - `init(radius:height:skinWidth:slopeLimit:stepLimit:upVector:collisionFilter:)`.
  - The capsule "aligns with its `upVector`".
  - "**`PhysicsBodyComponent` and `CollisionComponent` are incompatible with `CharacterControllerComponent`, and RealityKit deactivates them if you add them to the same entity**."
  - Solid hits go through the closure; trigger volumes go through `CollisionEvents.Began`.
- `moveCharacter(by:deltaTime:relativeTo:collisionHandler:) -> CharacterControllerComponent.CollisionFlags`: "Entity.transform will be updated on the next engine tick." Also `teleportCharacter(to:relativeTo:)` ([doc](https://developer.apple.com/documentation/realitykit/entity/movecharacter(by:deltatime:relativeto:collisionhandler:))).
- `CharacterControllerStateComponent.isOnGround` / `velocity` are added automatically and computed only after `moveCharacter` ([doc](https://developer.apple.com/documentation/realitykit/charactercontrollerstatecomponent)).
- Recommended loop: `content.subscribe(to: PhysicsSimulationEvents.WillSimulate.self, on: player)` (iOS 18). "You can also use `SceneEvents.Update` … but avoid using it to control physics-based motion."
- Pony-specific [I]:
  - The capsule is vertical, so a long body needs either (a) a capsule radius ≈ half the body length, which is too wide sideways, or (b) the controller on a root entity plus extra kinematic collision shapes (on child entities) for the head and hindquarters, used only for queries and raycasts.
  - Put the controller on a parent entity, and the skinned pony on a child offset so the hooves sit at the capsule bottom.
  - Drive the animation state machine (idle/walk/trot/canter/gallop) from `characterControllerState.velocity` and `isOnGround`, and the jump phases from `isOnGround` transitions. Pyro Panda's `CharacterMovementComponent`/`CharacterStateComponent` pattern is the reference.

---

## 7. WWDC25 / iOS 26 RealityKit additions relevant here (verified availability)

| API | Min OS | Relevance | Source |
|---|---|---|---|
| `Entity.attach(_:to:)`, `AttachedTransformComponent` | iOS/macOS 26 | tack and accessories pinned to joints | [doc](https://developer.apple.com/documentation/realitykit/entity/attach(_:to:)) |
| `MeshInstancesComponent`, `LowLevelInstanceData`, `LowLevelBuffer` | iOS/macOS 26 | GPU instancing of the paddock (grass, fences, flowers). "a single entity" (break up large areas for culling). LowLevelBuffer feeds `CustomMaterial` per-instance data on iOS/macOS/tvOS | [doc](https://developer.apple.com/documentation/realitykit/meshinstancescomponent), [WWDC25 287](https://developer.apple.com/videos/play/wwdc2025/287/) |
| `PostProcessEffect`, `RealityViewRenderingEffects.customPostProcessing` | iOS/macOS 26 | bloom, colour grading | [doc](https://developer.apple.com/documentation/realitykit/postprocesseffect) |
| `Entity.observable`, `Entity.animate(_:body:completion:)` | iOS/macOS 26 | SwiftUI ↔ RealityKit state (customisation UI) | [doc](https://developer.apple.com/documentation/realitykit/entity/observable-swift.property) |
| `GestureComponent` | iOS/macOS 26 (docs) | tap or drag on the pony | [doc](https://developer.apple.com/documentation/realitykit/gesturecomponent) |
| `Entity(from: Data, named:)` | iOS 26 (deprecated 27.2) | download content packs | [doc](https://developer.apple.com/documentation/realitykit/entity/init(from:named:)) |
| AVIF textures in USD | 26 | smaller USDZ ("quality similar to jpeg … 10 bit"); use `usdcrush` or Preview | [WWDC25 287](https://developer.apple.com/videos/play/wwdc2025/287/) |
| tvOS support | tvOS 26 | — | [WWDC25 287](https://developer.apple.com/videos/play/wwdc2025/287/) |
| `EnvironmentBlendingComponent` | **visionOS 26 only** | n/a on iOS/macOS | [doc](https://developer.apple.com/documentation/realitykit/environmentblendingcomponent) |
| `ManipulationComponent`, `ViewAttachmentComponent`, `ImagePresentationComponent` | **visionOS only** | n/a | docs |

No new skeletal-animation or IK API was introduced at WWDC25 for iOS 26. The new animation stack (animation graphs, skeleton resources, retargeting, deformers, root motion) arrived with **iOS 27 / WWDC26** ([WWDC26 279](https://developer.apple.com/videos/play/wwdc2026/279/) and the docs above) [V: availability metadata].

---

## 8. Documentation contradictions found (verify on device)

1. **Joint pins**: the API reference says skeletal pins "are not predefined, they need to be set" ([pins](https://developer.apple.com/documentation/realitykit/entity/pins)). The BOT-anist article says RealityKit "automatically creates a collection of pins to represent the joints" ([BOT-anist](https://developer.apple.com/documentation/visionos/bot-anist)).
2. **`SystemDependency.before`/`.after`**: the prose in the "Implementing systems" article contradicts its own code sample and the enum abstracts (§2.5).
3. **`BlendShapeWeightsComponent`**: the overview uses `weightSets[0]`; the property is `weightSet`.
4. **`opacityThreshold`**: "less than" (API reference) vs "less than or equal to" (article).
5. **`TextureResource(from: LowLevelTexture)`**: declared `async throws`, but the sample omits `await`.
6. **Tint initialiser abstracts**: "Creates a base color object … on macOS" also appears on the UIColor (iOS) overload. This is a doc typo.

---

## 9. Open uncertainties → experiments to run on device (iOS 26 / macOS 26)

1. **Entity structure of the exported pony USDZ**: dump `entity.children` recursively along with each entity's components. Check that all skinned meshes merge into one `ModelEntity` [C] and where `AnimationLibraryComponent` sits.
2. **Joint and influence limits**: load test skeletons with 64/128/256 joints and 4 vs 8 influences per vertex. Inspect `MeshResource.contents.models[*].parts[*].jointInfluences` after load to see whether RealityKit truncates.
3. **Sparse `SkelAnimation`** (clip joints = a subset): does RealityKit leave the unlisted joints writable by `SkeletalPosesComponent`? Does stripping `blendShapeWeights` from clips keep the sliders alive?
4. **Writing the pose in `SkeletalPoseUpdateComplete`**: is it rendered the same frame, and does it persist?
5. **IK cost**: a full-body solver with 4 hoof points, a pelvis parent constraint and a head look-at at `maxIterations` 10/20/30 on the oldest supported device.
6. **Blend-tree locomotion**: write a Float parameter through `entity.parameters[...]` for `BlendWeight.parameter`, and check phase alignment.
7. **Accessory toggling**: compare `MeshResource.generate(from: editedContents)` (with skeleton and blend shapes preserved) against separate SkelRoot accessory assets with pose sync.
8. **RCP clip schema** (`RealityKitClipDefinition`) honoured in a runtime-loaded `.usdz`?
9. **USD in-betweens and normalOffsets** in RealityKit blend shapes.
10. **`CharacterControllerComponent` with a long quadruped**: capsule sizing and slope/step behaviour.

---

## 10. Sources (all accessed 2026-10-05)

Apple documentation (RealityKit): [ModelEntity](https://developer.apple.com/documentation/realitykit/modelentity) · [HasModel](https://developer.apple.com/documentation/realitykit/hasmodel) · [SkeletalPosesComponent](https://developer.apple.com/documentation/realitykit/skeletalposescomponent) · [SkeletalPose](https://developer.apple.com/documentation/realitykit/skeletalpose) · [MeshResource.Skeleton](https://developer.apple.com/documentation/realitykit/meshresource/skeleton) · [MeshResource.JointInfluences](https://developer.apple.com/documentation/realitykit/meshresource/jointinfluences) · [MeshResource.Part](https://developer.apple.com/documentation/realitykit/meshresource/part) · [MeshBufferContainer](https://developer.apple.com/documentation/realitykit/meshbuffercontainer) · [LowLevelMesh.VertexSemantic](https://developer.apple.com/documentation/realitykit/lowlevelmesh/vertexsemantic) · [Entity.pins](https://developer.apple.com/documentation/realitykit/entity/pins) · [Entity.attach(_:to:)](https://developer.apple.com/documentation/realitykit/entity/attach(_:to:)) · [AnimationResource](https://developer.apple.com/documentation/realitykit/animationresource) · [AnimationLibraryComponent](https://developer.apple.com/documentation/realitykit/animationlibrarycomponent) · [playAnimation(…handoffType:)](https://developer.apple.com/documentation/realitykit/entity/playanimation(_:transitionduration:blendlayeroffset:separateanimatedvalue:startspaused:clock:handofftype:)) · [AnimationHandoffType](https://developer.apple.com/documentation/realitykit/animationhandofftype) · [AnimationPlaybackController](https://developer.apple.com/documentation/realitykit/animationplaybackcontroller) · [AnimationView](https://developer.apple.com/documentation/realitykit/animationview) · [JointTransforms](https://developer.apple.com/documentation/realitykit/jointtransforms) · [FromToByAnimation](https://developer.apple.com/documentation/realitykit/fromtobyanimation) · [AnimationGroup](https://developer.apple.com/documentation/realitykit/animationgroup) · [BlendTreeAnimation](https://developer.apple.com/documentation/realitykit/blendtreeanimation) · [BindTarget](https://developer.apple.com/documentation/realitykit/bindtarget) · [AnimationEvents](https://developer.apple.com/documentation/realitykit/animationevents) · [IKComponent](https://developer.apple.com/documentation/realitykit/ikcomponent) · [IKRig](https://developer.apple.com/documentation/realitykit/ikrig) · [BlendShapeWeightsComponent](https://developer.apple.com/documentation/realitykit/blendshapeweightscomponent) · [BlendShapeWeightsMapping](https://developer.apple.com/documentation/realitykit/blendshapeweightsmapping) · [PhysicallyBasedMaterial](https://developer.apple.com/documentation/realitykit/physicallybasedmaterial) · [ShaderGraphMaterial](https://developer.apple.com/documentation/realitykit/shadergraphmaterial) · [TextureResource](https://developer.apple.com/documentation/realitykit/textureresource) · [LowLevelTexture](https://developer.apple.com/documentation/realitykit/lowleveltexture) · [CustomMaterial](https://developer.apple.com/documentation/realitykit/custommaterial) · [System](https://developer.apple.com/documentation/realitykit/system) · [Implementing systems](https://developer.apple.com/documentation/realitykit/implementing-systems-for-entities-in-a-scene) · [RealityView](https://developer.apple.com/documentation/realitykit/realityview) · [RealityViewCameraContent](https://developer.apple.com/documentation/realitykit/realityviewcameracontent) · [realityViewCameraControls](https://developer.apple.com/documentation/swiftui/view/realityviewcameracontrols(_:)) · [GroundingShadowComponent](https://developer.apple.com/documentation/realitykit/groundingshadowcomponent) · [DirectionalLightComponent.Shadow](https://developer.apple.com/documentation/realitykit/directionallightcomponent/shadow) · [ImageBasedLightComponent](https://developer.apple.com/documentation/realitykit/imagebasedlightcomponent) · [EnvironmentResource](https://developer.apple.com/documentation/realitykit/environmentresource) · [CharacterControllerComponent](https://developer.apple.com/documentation/realitykit/charactercontrollercomponent) · [MeshInstancesComponent](https://developer.apple.com/documentation/realitykit/meshinstancescomponent) · [Character control, skeletons, and IK collection](https://developer.apple.com/documentation/realitykit/game-development-character-skeletons) · [Entity animations collection](https://developer.apple.com/documentation/realitykit/game-development-entity-animations) · [Mesh deformation (iOS 27)](https://developer.apple.com/documentation/realitykit/scene-content-mesh-deformation) · [Rendering high-fidelity characters](https://developer.apple.com/documentation/realitykit/rendering-high-fidelity-characters) · [Loading entities from a file](https://developer.apple.com/documentation/realitykit/loading-entities-from-a-file).

Apple documentation (USD): [Creating USD files for Apple devices](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices) · [Validating feature support for USD files](https://developer.apple.com/documentation/usd/validating-usd-files).

Apple samples: [BOT-anist](https://developer.apple.com/documentation/visionos/bot-anist) · [Bringing your SceneKit projects to RealityKit (Pyro Panda)](https://developer.apple.com/documentation/realitykit/bringing-your-scenekit-projects-to-realitykit).

WWDC: [WWDC24 10103 Discover RealityKit APIs for iOS, macOS and visionOS](https://developer.apple.com/videos/play/wwdc2024/10103/) · [WWDC24 10102 Compose interactive 3D content in Reality Composer Pro](https://developer.apple.com/videos/play/wwdc2024/10102/) · [WWDC25 287 What's new in RealityKit](https://developer.apple.com/videos/play/wwdc2025/287/) · [WWDC25 274 Better together: SwiftUI and RealityKit](https://developer.apple.com/videos/play/wwdc2025/274/) · [WWDC25 288 Bring your SceneKit project to RealityKit](https://developer.apple.com/videos/play/wwdc2025/288/) · [WWDC26 279 Explore advances in RealityKit](https://developer.apple.com/videos/play/wwdc2026/279/).

Apple Developer Forums: [797407 (IK + animation, Apple engineer)](https://developer.apple.com/forums/thread/797407) · [798309 (attach(_:to:), Apple engineer)](https://developer.apple.com/forums/thread/798309) · [792613 (joints are not entities, Apple engineer)](https://developer.apple.com/forums/thread/792613) · [761893 (custom skeleton + IK + SkeletalPoseUpdateComplete, Apple engineer)](https://developer.apple.com/forums/thread/761893) · [772965 (USD physics joints unsupported, DTS)](https://developer.apple.com/forums/thread/772965) · [784756 (merged skinned meshes, community)](https://developer.apple.com/forums/thread/784756) · [793431 (blend shapes vs clips, community)](https://developer.apple.com/forums/thread/793431) · [719891 (bind path mismatch, community)](https://developer.apple.com/forums/thread/719891).

OpenUSD: [UsdSkel schemas documentation source](https://github.com/PixarAnimationStudios/OpenUSD/blob/release/pxr/usd/usdSkel/doxygen/schemas.dox). openusd.org itself was blocked by this environment's proxy, so the same text was read from the GitHub source.

Third-party (labelled [C]): [apparata/fbx2usd](https://github.com/apparata/fbx2usd).

Local experiment: Blender 4.2.0 `bpy` USD export inspected with `pxr` (usd-core 26.8). Script and output are in `scratchpad/research/ad/blendertest/` (`t.py`, `t.usda`).
