# USD/USDZ authoring for RealityKit skinned characters, and Blender 4.2 USD export

Research report for the pony character in *Les Héritiers de Valombre* (RealityKit, iOS 26 / macOS 26).
Date: 2026-10-05. Environment: Linux container, `bpy 4.2.0` (it embeds its own USD, namespace `pxrInternal_v0_24`), `usd-core 26.8` (pxr), numpy, pillow.

Labels used below:
- **VERIFIED**: backed by a cited primary source (Apple docs, WWDC transcript, OpenUSD source or docs, Blender source) and/or by an experiment I ran here, with the output pasted.
- **UNCERTAIN / INFERRED**: my inference, a third-party source, or something I could not test. RealityKit itself cannot run in this container, so **nothing here was tested on iOS or macOS**.

> Network note: `openusd.org`, `docs.blender.org`, `projects.blender.org`, `stepinto.vision` and `blog.studiolanes.com` were blocked by the egress proxy. I read the OpenUSD docs from their **source files in the OpenUSD GitHub repository at tag v26.08**, which are the same texts rendered on openusd.org. I read Blender 4.2.0 behaviour from its **C++ source on the GitHub mirror at tag v4.2.0**. I read Apple docs through the developer.apple.com documentation JSON, which is the same content as the HTML pages.

---

## 0. TL;DR: decisions and recommendations

1. **Use Blender 4.2 `wm.usd_export` for geometry, skin weights, blend shapes and baked clips, then run a pxr post-processing pass.** The UsdSkel data it writes is numerically correct: UsdSkel LBS plus blend shapes reproduce Blender's evaluated mesh to within 2.4e-7 m (§5, exp. B). It has several defects that a pxr pass must fix (§4.4):
   - `inputs:normal` is typed `float3` instead of `normal3f`, which fails both checkers.
   - Normal-map `scale`/`bias` alpha components are wrong.
   - `restTransforms` are taken from the *current pose*, not the rest pose.
   - `elementSize` is inflated by non-bone vertex groups and is not capped at 4.
   - `framesPerSecond` is missing.
   - Meshes are `doubleSided` unless backface culling is enabled.
   - It exports only the scene timeline: one SkelAnimation per file.
2. **Alternatively, write the final USD ourselves with pxr** (exp. H shows a complete, checker-clean skinned asset with two meshes, a blend shape, two SkelAnimations and an animation variant set, all in about 150 lines). I recommend a **hybrid**: Blender for modelling, rigging, weighting and animation; extract data with bpy; *author* the final USD with pxr. This gives full control over joint naming, rest pose, normal offsets, clip layout, materials and metadata.
3. **Target conventions for RealityKit:** `upAxis = "Y"`, `metersPerUnit = 1`, `-Z` forward ([WWDC24 10186](https://developer.apple.com/videos/play/wwdc2024/10186/)). The other required conventions are:
   - A single skeleton (merge all rigs) ([Apple](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices)).
   - `MaterialBindingAPI` and `SkelBindingAPI` applied.
   - `subdivisionScheme = "none"` and `doubleSided = false`.
   - Metallic workflow only.
   - Textures: PNG/JPEG (EXR, AVIF also allowed in USDZ).
   - Normal maps in OpenGL convention, with `sourceColorSpace = raw`.
4. **Multiple clips.** Apple's documented way is `AnimationLibraryComponent` (iOS 18+). You fill it from several animation files (Reality Composer Pro, or code via `availableAnimations`), or from a USD that RealityKit "exposes" as a library ([WWDC25 288](https://developer.apple.com/videos/play/wwdc2025/288/)). Robust fallbacks I can recommend:
   - (a) One USDZ per clip, sharing the same skeleton, collected into an `AnimationLibraryComponent` in code.
   - (b) One concatenated timeline plus a JSON clip table, trimmed with `AnimationView(trimStart:trimEnd:)` ([docs](https://developer.apple.com/documentation/realitykit/animationview)).
   - (c) Variant sets switching `skel:animationSource` (Apple's own `variant_combiner.py` support script).

   Which of these behaves best at runtime is **UNCERTAIN** and must be tested on a device.
5. **Compliance checking from Python.** `UsdUtils.ComplianceChecker` was **removed in OpenUSD 26.08**, which is the installed `usd-core 26.8`. The new `UsdValidation` framework has **no ARKit rules**: it passes a Z-up file. I vendored `complianceChecker.py` from OpenUSD v26.05; it runs unchanged on pxr 26.8 with `arkit=True` (§3, exp. C). Use both checkers.
6. **Runtime features** relevant to the pony (all VERIFIED API existence; behaviour UNCERTAIN until tested):
   - Since iOS 18: `BlendShapeWeightsComponent` (morph sliders), `SkeletalPosesComponent` and `IKComponent` (procedural look-at, ears, tail), and `GeometricPin` with `skeletalJointName`.
   - Since iOS 26: `Entity.attach(_:to:)`, the recommended way to attach rigid accessories to joints.

---

## 1. UsdSkel structure that RealityKit consumes

### 1.1 Schema facts (VERIFIED: OpenUSD docs, source at v26.08)
Sources: [`schemas.dox`](https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/pxr/usd/usdSkel/doxygen/schemas.dox) (= [openusd.org UsdSkel Schemas In-Depth](https://openusd.org/release/api/_usd_skel__schemas.html)), [`schema.usda`](https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/pxr/usd/usdSkel/schema.usda).

| Item | Rule (quoted or paraphrased from the source) |
|---|---|
| `SkelRoot` | "used to **encapsulate** primitives with skeletal skinning behaviors, and is required when authoring skeletal data." Skinned prims and the Skeleton live under it. Authoring extents on it is recommended. |
| `Skeleton.joints` (`uniform token[]`) | Joint *paths* (`A`, `A/B`, …). "required to be authored such that all parent joints come before any of their children in the array." Multiple root joints are allowed. You can validate with `UsdSkel.Topology(paths).Validate()`. |
| `bindTransforms` (`uniform matrix4d[]`) | "bind-pose transforms of each joint in **world space**", in `joints` order. |
| `restTransforms` (`uniform matrix4d[]`) | "rest-pose transforms of each joint in **local space** … fallback values for joint transforms when a Skeleton either has no bound animation source, or when that animation source only contains animation for a subset". |
| `SkelAnimation` | `translations float3[]`, `rotations quatf[]` ("Joint-local unit quaternion rotations … 32-bit"), `scales half3[]` ("16 bit precision"), `blendShapes token[]`, `blendShapeWeights float[]`. Composed "scale-rotate-translate", joint-local. "An animation source is only valid if its *translation*, *rotation*, and *scale* components are all authored". The animation's own `joints` may be a sparse subset in any order. |
| Binding | `SkelBindingAPI` provides: `skel:skeleton` (rel), `skel:animationSource` (rel, on Skeleton or SkelRoot), `primvars:skel:jointIndices` (int[]), `primvars:skel:jointWeights` (float[]), and `primvars:skel:geomBindTransform` (matrix4d, "world space transform of a skinned primitive at bind time"). It also provides an optional `skel:joints` for a per-mesh sparse joint order. |
| Influences | `vertex` interpolation with `elementSize` = fixed influences per point. Unused slots are filled with 0. `constant` interpolation means rigid binding. "**No restrictions are placed on the elementSize** … for clients that require a strict limit … `UsdSkelResizeInfluences`". "joint influences should be normalized when they are written … UsdSkel does *not* automatically normalize". Sorting by weight is recommended (`UsdSkelSortInfluences`). |
| Xforms on skinned prims | "any transform on the prim authored by way of the typical UsdGeomXformable schema has **no effect** on the rendered results" (rendered in skeleton space). |
| BlendShape | `offsets vector3f[]` (**Required**), `normalOffsets vector3f[]` (marked **Required** in the schema doc), `pointIndices int[]` (optional, sparse), and in-betweens as `inbetweens:<name>` attributes. "blend shape application precedes the effect of skinning". |
| Mesh blend-shape binding | `skel:blendShapes` (token[] names) plus `skel:blendShapeTargets` (rel to BlendShape prims), matched by order. Weights come from `SkelAnimation.blendShapeWeights`, matched by name. |

### 1.2 What RealityKit says about skeletons (VERIFIED, Apple)
- [Validating feature support for USD files](https://developer.apple.com/documentation/usd/validating-usd-files):
  - RealityKit column: **Skeletons ✔, Skeleton animation ✔, Blend Shapes ✔, Transform animation ✔**.
  - **Vertex animation ✗** (time-sampled points), so all deformation must go through UsdSkel.
  - **Double-sided meshes ✗**.
  - Lights are not used: "it doesn't use any lights included in a USD file".
  - **Point instancing ✗**.
- [Creating USD files for Apple devices](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices):
  - "**Limit rigged models to a single skeleton** … merge all the skeletons into a single joint or bone hierarchy."
  - "any geometry that has a skeleton use the `SkelBindingAPI` … any geometry with an applied material use the `MaterialBindingAPI`".
  - "RealityKit uses **Y-up orientation and meters**".
  - Set `subdivisionScheme` to `none` explicitly.
  - Review `doubleSided`.
- RealityKit's runtime skeleton model, [MeshResource.Skeleton](https://developer.apple.com/documentation/realitykit/meshresource/skeleton) (iOS 18):
  - Joint names are paths (`root/hips_joint/...`).
  - Each joint has an inverse bind pose matrix and a rest pose "relative to the joint's parent".
- [MeshJointInfluence](https://developer.apple.com/documentation/realitykit/meshjointinfluence): influences per vertex have "weights [that] sum to 1"; skinning is linear blend.
- [MeshResource.JointInfluences](https://developer.apple.com/documentation/realitykit/meshresource/jointinfluences): "Each vertex is associated with a fixed number of influences … padded with zero-weight influences" (`influencesPerVertex`), the same model as UsdSkel `elementSize`.

### 1.3 Limits: what is NOT documented (UNCERTAIN)
- **Max influences per vertex:** no Apple page I found states a cap; I searched the RealityKit docs JSON, the USD pages and the forums. **Recommendation (inferred): cap at 4, sorted and normalized.** Four is the common real-time convention, and third-party RealityKit tooling also uses it (e.g. [apparata/fbx2usd](https://github.com/apparata/fbx2usd): "up to 4 influences per vertex"). Exp. G shows how to enforce it with `UsdSkel.SortInfluences` and `UsdSkel.ResizeInfluences`.
- **Max joints per skeleton:** not documented by Apple. Keep the pony rig lean, roughly ≤ 128 deform joints. This is an inference, not a documented limit.
- **Weights must be normalized:** VERIFIED as required for correct LBS ([MeshJointInfluence](https://developer.apple.com/documentation/realitykit/meshjointinfluence) "sum to 1"; UsdSkel "should be normalized"). Blender normalizes on export (§4.3).
- **Rotations:** must be `quatf[]` (VERIFIED, schema). Blender writes `quatf[]` (VERIFIED, exp. A).
- **Time codes / fps:** USD uses `timeCodesPerSecond` to convert time codes to seconds. How RealityKit maps `startTimeCode`/`endTimeCode` to the start of the `AnimationResource`, and whether it reads `framesPerSecond`, is **UNCERTAIN**: no Apple doc found. Blender writes `timeCodesPerSecond` but not `framesPerSecond` (exp. B shows `fps: 24.0`, the fallback). The post-pass sets both.
- **`normalOffsets` missing:** Blender 4.2 does not write them (VERIFIED, exp. B: `normalOffsets authored=False`). How RealityKit shades a blend shape without normal offsets is **UNCERTAIN**. When we author ourselves, compute real normal deltas.

### 1.4 Multiple skinned meshes bound to one skeleton (VERIFIED in USD, UNCERTAIN in RealityKit)
- UsdSkel allows any number of meshes under one SkelRoot with `skel:skeleton` pointing to the same Skeleton (schema).
- **Exp. D/E:** Blender 4.2 with a Body and a Mane, both with an Armature modifier on the same rig, writes **one SkelRoot, one Skeleton, one SkelAnimation**, and both meshes bound to it:
  ```
  SkelRoot      /root/Rig
  Skeleton      /root/Rig/Rig
  SkelAnimation /root/Rig/Rig/Anim blendShapes=['Fat', 'Fat2']
  Mesh          /root/Rig/Body/Body skel:skeleton=['/root/Rig/Rig'] blendShapes=['Fat']
  Mesh          /root/Rig/Mane/Mane skel:skeleton=['/root/Rig/Rig'] blendShapes=['Fat2']
  ```
  The same shape-key name on two meshes is **renamed** (`Fat2`) on the merged SkelAnimation. This is VERIFIED in the Blender source: "In case of name collisions, we must generate unique blend shape names" ([usd_blend_shape_utils.cc v4.2.0](https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_blend_shape_utils.cc)). A morphology slider that must move body and mane together therefore has to drive both names (or we author names ourselves).
- How RealityKit maps this to entities is **UNCERTAIN**: one ModelEntity per mesh, or one merged model. `jointNames`/`jointTransforms` live on `HasModel` ([docs](https://developer.apple.com/documentation/realitykit/hasmodel/jointtransforms)). Test on device.

### 1.5 Multiple animations in one file and how RealityKit exposes them
VERIFIED facts:
- [`Entity.availableAnimations`](https://developer.apple.com/documentation/realitykit/entity/availableanimations) is "The list of animations associated with the entity". Files loaded via `Entity(named:)`/`load(named:)` populate it.
- [`AnimationLibraryComponent`](https://developer.apple.com/documentation/realitykit/animationlibrarycomponent) (iOS 18 / macOS 15) is "a collection of animations that an entity can play". You populate it in Reality Composer Pro (Add Component → Animation Library → add USD files with animations) or in code from several entities' `availableAnimations`. You play by name: `library.animations["walk"]`.
- [WWDC25 "Bring your SceneKit project to RealityKit" (288)](https://developer.apple.com/videos/play/wwdc2025/288/):
  - "When a USD file has animations, RealityKit exposes them in an AnimationLibraryComponent."
  - Xcode 26's `xcrun scntool --convert max.scn --format usdz --append-animation max_spin.scn` appends extra animations into one USDZ.
  - **This scntool route needs macOS + Xcode 26; it was not available here.**
- [`AnimationView`](https://developer.apple.com/documentation/realitykit/animationview) (iOS 15+) builds a clip of an existing animation with `trimStart`/`trimEnd`, then `AnimationResource.generate(with:)`. This is the documented way to cut a concatenated timeline into clips.
- Apple's [USD Support Scripts](https://developer.apple.com/download/files/USD-Support-Scripts.zip) `variant_combiner.py` (VERIFIED by reading it) combines files as **animation variants**: a variant set on the default prim whose variants retarget `skel:animationSource`. Apple's page says variants on the default prim are user-selectable in QuickLook, and RealityKit supports "changing the variant after loading the asset but this depends on the context" ([validating page](https://developer.apple.com/documentation/usd/validating-usd-files)).

UNCERTAIN / third-party:
- How Reality Composer Pro serialises an animation library in USDA is **not documented by Apple**. Third-party reverse engineering ([apparata/fbx2usd](https://github.com/apparata/fbx2usd), Jan 2026) writes:
  - a `def RealityKitComponent "AnimationLibrary"` with `token info:id = "RealityKit.AnimationLibrary"`;
  - children `RealityKitAnimationFile` (`asset file`, `string name`), or a `RealityKitClipDefinition` (`clipNames`, `startTimes`, `sourceAnimationName = "default subtree animation"`).

  The OpenUSD ARKit checker explicitly allows prim types starting with `RealityKit`. **Treat this as unofficial and possibly unstable.**
- Older forum answer (2020, Apple staff): "Currently there is no way of storing multiple animations in a single USDZ file" ([thread 650515](https://developer.apple.com/forums/thread/650515)). WWDC25 288 supersedes it for iOS 18+/26 via AnimationLibrary.
- Community workflow, Blender → RCP (2025): export each NLA strip as its own USD, then add them to an Animation Library in RCP ([thread 758179](https://developer.apple.com/forums/thread/758179); not an Apple answer). The same thread reports an RCP-bundle playback issue.

Recommendation (INFERRED):
- Primary: **one base USDZ (mesh, skeleton, materials, rest pose, no animation) plus one small animation-only USDZ per clip.** All share the identical skeleton (same joint tokens and order). At load time, build an `AnimationLibraryComponent` in code from each clip entity's `availableAnimations.first`. This matches Apple's documented code path.
- Fallback: concatenated timeline plus JSON clip table plus `AnimationView` trimming. Exp. G writes such a sidecar.

---

## 2. Materials in USDZ for RealityKit

### 2.1 Facts
- [Creating USD files for Apple devices](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices) (VERIFIED, Apple):
  - Use the **metallic workflow**: "Only Storm and Raytracer support the specular workflow".
  - "USDZ files may only include **JPEG, PNG, EXR, and AVIF**. Use AVIF textures where possible".
  - Pack grayscale maps (roughness, metallic, AO) into RGB channels.
  - Use sRGB for base color and unlit color. Use linear/raw for roughness, metallic, AO and normal maps.
  - "**RealityKit expects normal maps in OpenGL format**" (DirectX: invert green).
  - Minimise alpha transparency.
  - "When building your app in Xcode, textures are compressed automatically." (UNCERTAIN whether this applies to a raw `.usdz` in the bundle versus an RCP package.)
- [Validating feature support](https://developer.apple.com/documentation/usd/validating-usd-files), RealityKit column (VERIFIED, Apple):
  - USD preview surface ✔, Material graph ✔, MaterialX ✔ (see ShaderGraph), Textures ✔, AVIF ✔, Texture wrap modes ✔, ColorSpace ✔.
  - Specular workflow ✗, **Bias ✗**, Displacement ✗.
  - Partial:
    - "RealityKit supports only a **single packed texture per material**. You can, however, reference multiple scalar channels within a single texture."
    - "a **single `UsdTransform2d` per material**".
    - "Multiple UV sets: RealityKit supports **two** UV Sets."
    - "Scale: RealityKit supports USD texture scaling **except for normal map textures**."
    - colorSpace names "srgb_texture", "lin_srgb", "srgb_displayp3", "lin_displayp3". Otherwise `sourceColorSpace` ("sRGB"/"raw") is used. Otherwise the embedded profile is used.
  - Subdivision is supported for UsdPreviewSurface materials only.
- [UsdPreviewSurface spec](https://openusd.org/release/spec_usdpreviewsurface.html) (VERIFIED, OpenUSD; [source v26.08](https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/docs/spec_usdpreviewsurface.rst)):
  - Inputs (spec v2.5): `diffuseColor`, `emissiveColor`, `useSpecularWorkflow`, `specularColor`, `metallic`, `roughness`, `clearcoat`, `clearcoatRoughness`, `opacity`, `opacityMode`, `opacityThreshold`, `ior`, `normal (normal3f, tangent space)`, `displacement`, `occlusion`.
  - `opacityThreshold > 0` gives cut-out: "the opacity values less than the opacityThreshold will not be rendered". Use it for mane/tail cards and braids.
  - Normal: "If the texture has 8 bits per component, then scale and bias must be adjusted to be (2.0, 2.0, 2.0, 1.0) and (-1, -1, -1, 0) … the sourceColorSpace must also be set to 'raw'."
  - `UsdUVTexture`:
    - `wrapS/wrapT`: `black|clamp|repeat|mirror|useMetadata` (default `useMetadata`, which falls back to `black`, so **always author `repeat`**).
    - `sourceColorSpace`: `raw|sRGB|auto`.
    - `scale`/`bias` are `float4`.
    - Outputs `r,g,b,a,rgb`.
  - `UsdPrimvarReader_float2` with `varname`.
  - Texture coordinate origin is bottom-left. glTF data must be t-flipped.
- [USDZ spec](https://openusd.org/release/spec_usdz.html) (VERIFIED, [source](https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/docs/spec_usdz.rst)):
  - Uncompressed, unencrypted zip.
  - Each file's data starts at a 64-byte offset.
  - The first file is the default layer.
  - Allowed: usda/usdc/usd, png/jpeg/exr/avif, M4A/MP3/WAV.
  - Note: "Apple's current usdz implementation allows only a single usdc file".
- **KTX/ASTC are not allowed inside a USDZ** (not in the list above). VERIFIED by omission in both specs.
- Checkers: the vendored ARKit checker (v26.05) accepts `exr, jpg, jpeg, png` only. `UsdValidation`'s `FileExtensionValidator` also lists ".exr, .jpg, .jpeg, .png" (VERIFIED, exp. C registry dump). **AVIF would be flagged by these checkers** even though Apple's page allows it. **UNCERTAIN whether AVIF-in-USDZ works on iOS 26 specifically**, since the Apple page now also documents macOS 27. **Use PNG/JPEG for safety.**

### 2.2 Normal maps: a contradiction to be aware of (VERIFIED facts, INFERRED consequence)
The UsdPreviewSurface spec and the `usdShadeValidators:NormalMapTextureValidator` want `scale=(2,2,2,1)` and `bias=(-1,-1,-1,0)` on 8-bit normal maps. Apple's table says RealityKit does **not** support *Bias* and does not apply *Scale* to normal maps.

WWDC24 10186 says the RealityKit material expects [-1, 1] and shows a "Normal Map Decode" ShaderGraph node. That is for ShaderGraph materials. Inference: for UsdPreviewSurface imports, RealityKit treats the `normal` input specially and ignores scale/bias. **Author the spec values for portability and checker compliance, use OpenGL-convention (Y+) maps, and verify visually on device.**

### 2.3 Runtime colour changes (player-chosen coat, markings, etc.): INFERRED
- UsdPreviewSurface gives a static `PhysicallyBasedMaterial` on load. To recolour at runtime, either:
  - replace material parameters in Swift (`PhysicallyBasedMaterial.baseColor.tint`/texture), or
  - use a Reality Composer Pro ShaderGraph (MaterialX) material with promoted parameters (`ShaderGraphMaterial.setParameter`).
- **Because RealityKit supports only one packed texture per material,** keep coat colour masks such as markings (white socks, blaze) in a single RGBA mask texture and blend in ShaderGraph. This is a design inference; not tested.

---

## 3. ARKit / RealityKit compliance, units and axes

### 3.1 Stage metadata (VERIFIED)
- `upAxis = "Y"` and `metersPerUnit = 1.0`: "RealityKit uses Y-up orientation and meters" ([Apple](https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices)).
- The ARKit checker fails `upAxis 'Z'` ("upAxis should be 'Y'"), a missing `metersPerUnit`, and a missing `defaultPrim` (exp. C negative control).
- Forward: "Reality Kit uses a coordinate system that assumes **-Z is forward, Y is up, and +X is to the right**. Whereas Blender uses Z as up and Y as forward." ([WWDC24 10186](https://developer.apple.com/videos/play/wwdc2024/10186/)). RealityKit also has [`Entity.ForwardDirection`](https://developer.apple.com/documentation/realitykit/entity/forwarddirection) `.negativeZ/.positiveZ` (iOS 18) for `look(at:)`-style APIs.

### 3.2 Running the checker from Python with usd-core 26.8 (VERIFIED, exp. C)
- `UsdUtils.ComplianceChecker` **no longer exists** in pxr 26.8:
  ```
  1) hasattr(UsdUtils, 'ComplianceChecker') = False
     import failed: cannot import name 'complianceChecker' from 'pxr.UsdUtils'
  ```
  The OpenUSD [CHANGELOG 26.08](https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/CHANGELOG.md) says "Removed previously deprecated UsdUtils.ComplianceChecker. Clients are expected to migrate to the UsdValidation framework." `usdchecker` and `usdzip` both had "Removed deprecated `--arkit` command line option."
- The new framework (`pxr.UsdValidation`) has 28 validators in this build. They cover:
  - stage metadata (requires `upAxis`/`metersPerUnit` to be *present*, not Y);
  - `SkelBindingAPI`/`MaterialBindingAPI` applied;
  - shader Sdr conformance, normal-map encoding, usdz packaging;
  - file extensions, missing references, encapsulation, GeomSubset families.

  **It has no ARKit prim-type, shader-id or Y-up rules.** Verified: a Z-up Blender file gives "0 issue(s)" under UsdValidation but FAILs the ARKit checker.
- **Working method:** vendor [`complianceChecker.py` from v26.05](https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.05/pxr/usd/usdUtils/complianceChecker.py) (stored as `experiments/usd/complianceChecker_v26_05.py`) and call:
  ```python
  spec = importlib.util.spec_from_file_location("cc", "complianceChecker_v26_05.py")
  cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
  c = cc.ComplianceChecker(arkit=True)           # emits a DeprecationWarning
  c.CheckCompliance("pony.usdz")
  fails = c.GetFailedChecks() + c.GetErrors()     # NOTE: rule failures are in GetFailedChecks(), not GetErrors()
  ```
  Plus the new framework:
  ```python
  ctx = UsdValidation.ValidationContext(UsdValidation.ValidationRegistry().GetOrLoadAllValidators())
  errors = ctx.Validate(Usd.Stage.Open("pony.usdz"))
  ```
  Negative control (exp. C) proves the vendored checker really checks: 11 failed checks on a deliberately bad file, including `SphereLight` and `PointInstancer` (unsupported type), `MyCustomShader` (unsupported info:id), `.tga` (non-portable), the missing SkelBindingAPI, Z-up, and missing metersPerUnit/defaultPrim.
- ARKit rules in that checker (VERIFIED by reading the source):
  - **Allowed prim types:** `'', Scope, Xform, Camera, Shader, Material, Mesh, Sphere, Cube, Cylinder, Cone, Capsule, GeomSubset, Points, SkelRoot, Skeleton, SkelAnimation, BlendShape, SpatialAudio, PhysicsScene, Preliminary_*`, plus any type starting with `RealityKit`.
  - **Shader ids:** `UsdPreviewSurface`, `UsdUVTexture`, `UsdTransform2d`, `UsdPrimvarReader_*`, `ND_*` (MaterialX). Shader inputs may have at most one connection.
  - **Layers and package:** layer formats usd/usda/usdc/usdz; package files limited to those plus png/jpg/jpeg/exr.
  - Its ARKit checks were "Updated … to match spec from WWDC 2023" (CHANGELOG).
- A pitfall I hit and fixed: `Usd.Stage.Open(path)` in the same process returns the **already-open, edited in-memory layer**. Checking a file after editing it in-process hides the original errors. Run checks before editing, or in a fresh process.
- An alternative (UNTESTED): install `usd-core==26.5` in a separate venv to get the original `ComplianceChecker`.

### 3.3 Packaging (VERIFIED)
- `UsdUtils.CreateNewARKitUsdzPackage(Sdf.AssetPath(src), "x.usdz")` works in 26.8. From `.usda` it writes a `.usdc` default layer plus textures, all uncompressed and 64-byte aligned (exp. C: `compress=0 data_offset%64=0`).
- Header doc ([usdzPackage.h](https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/pxr/usd/usdUtils/usdzPackage.h)): "this may involve more transformations to the data, which may cause loss of features such as VariantSets". In exp. H, a **single-layer** source kept its `animation` variant set inside the usdz (verified).
- **Do not use `stage.Export()` (flatten) before packaging.** It turned `./textures/*.png` into absolute paths, which the packager relocated into a `0/` folder (observed in exp. G, first run). Export the **root layer** (`stage.GetRootLayer().Export(...)`) when the source has no composition.

---

## 4. Blender 4.2 USD exporter (`bpy.ops.wm.usd_export`)

### 4.1 Options: dumped from the installed operator (VERIFIED, `bpy 4.2.0`)
Defaults are in parentheses. These are the authoritative property names for headless scripts.

| Option | Default | Notes |
|---|---|---|
| `export_animation` | False | "Export all frames in the render frame range" |
| `export_armatures` | **True** | "armatures and meshes with armature modifiers as USD skeletons and skinned meshes" |
| `only_deform_bones` | False | "Only export deform bones and their parents" |
| `export_shapekeys` | **True** | "shape keys as USD blend shapes" |
| `export_uvmaps` / `rename_uvmaps` | True / True | active render UV map renamed to `st` |
| `export_normals` | True | faceVarying normals |
| `export_mesh_colors` | True | |
| `export_materials` | True | |
| `generate_preview_surface` | True | |
| `generate_materialx_network` | False | |
| `export_textures` | True | copies to `./textures` |
| `overwrite_textures` | False | |
| `relative_paths` | True | |
| `usdz_downscale_size` | KEEP | 256…4096 or CUSTOM, plus `usdz_downscale_custom_size` |
| `convert_orientation` | False | |
| `export_global_forward_selection` | NEGATIVE_Z | |
| `export_global_up_selection` | Y | |
| `root_prim_path` | "/root" | |
| `xform_op_mode` | TRS | TRS/TOS/MAT |
| `export_subdivision` | BEST_MATCH | IGNORE/TESSELLATE/BEST_MATCH |
| `triangulate_meshes` | False | `quad_method`, `ngon_method` |
| `evaluation_mode` | RENDER | |
| `selected_objects_only` | False | |
| `visible_objects_only` | True | |
| `collection` | "" | |
| `export_meshes` / `export_lights` / `export_cameras` / `export_curves` / `export_volumes` / `export_hair` | True ×5, hair False | |
| `use_instancing` | False | |
| `export_custom_properties` | True | `custom_properties_namespace` = userProperties |
| `author_blender_name` | True | |
| `convert_world_material` | **True** | writes a DomeLight; Apple engineer advises disabling it ([forum 766484](https://developer.apple.com/forums/thread/766484)) |
| `allow_unicode` | False | |

- There is **no units / metersPerUnit option in 4.2**. `metersPerUnit` = `scene.unit.scale_length` (VERIFIED, [usd_capi_export.cc v4.2.0](https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_capi_export.cc)).
- Blender 4.4 reportedly added "Units"/"Meters Per Unit" options ([PR #122804](https://projects.blender.org/blender/blender/pulls/122804), via search snippet; page not fetched, so UNCERTAIN).
- `.usdz` output: give the filepath a `.usdz` extension. Blender then calls `UsdUtilsCreateNewUsdzPackage` (the *non*-ARKit variant; VERIFIED in source).

### 4.2 Answers to the specific questions (VERIFIED by experiment and source)
- **Blend shapes from shape keys: yes.** The relative shape keys become one `BlendShape` prim per key with `offsets` and `pointIndices`, plus `skel:blendShapes`/`skel:blendShapeTargets` on the mesh. Weights (`kb->curval`) are sampled every frame into `SkelAnimation.blendShapeWeights`.
  - No `normalOffsets` and no in-betweens are written.
  - If a shape-keyed mesh has no authored joint influences, Blender writes dummy `jointIndices = 0` / `jointWeights = 1` primvars (elementSize 1): "Some DCCs seem to require joint indices and weights to bind the skeleton for blend-shapes" (source). What skeleton such a mesh gets when it has no armature was not tested.
  - Skinned and blend-shaped meshes are written at the **basis / rest shape** ("pre-modified mesh").
- **Animation: only the scene timeline.** The exporter loops `for frame = sfra..efra` (step 1, integer frames, every frame baked), evaluates the depsgraph, and writes TRS samples per joint (`SetTransforms`) into one `SkelAnimation` named `Anim` under the Skeleton. It sets `skel:animationSource` on the Skeleton, and stage `timeCodesPerSecond = fps`, `startTimeCode = sfra`, `endTimeCode = efra`.
  - **It does not iterate actions.** Exp. D: an NLA timeline (Walk at 1–10, Graze at 11–30, no active action) exported as one 30-sample animation with `animationSource` set. A per-action loop (set `animation_data.action`, set the frame range to `action.frame_range`, export) produced one file per clip.
- **Orientation conversion** puts a rotation on the top prim; the data stays Z-up internally. Example: `xformOp:rotateXYZ = (-90,0,0)` for the defaults (forward −Z, up Y), and `(90,0,180)` for forward Z, up Y. `upAxis` metadata is changed. It also works with `root_prim_path=""`: the rotation then goes on the armature prim (exp. D1).
  - **Where the pony's face ends up (exp. D1/E):** a joint at Blender −Y (the front view, i.e. where a character's face is when modelled facing the front view) lands at **USD +Z with the defaults**, and at **USD −Z with `export_global_forward_selection="Z"`**. Per WWDC24, RealityKit's forward is −Z, so use `forward="Z", up="Y"` if the pony is modelled facing Blender −Y.
- **Joint names:** paths of bone names, made into valid identifiers with `TfMakeValidIdentifier` (e.g. `Leg.L` becomes `Leg_L`) unless `allow_unicode`.
  - RealityKit pins need escaping of `.`, `[`, `]`, `\` in joint names ([Entity.pins](https://developer.apple.com/documentation/realitykit/entity/pins)). Name bones with `_` from the start.
- **Root structure:** `/root` (Xform, default prim) contains `SkelRoot` (the armature object, with an authored but static TRS xform) and `/root/_materials`. Under the SkelRoot: `Skeleton` (with SkelBindingAPI) / `Anim` (SkelAnimation), and `Xform <mesh object>` / `Mesh <mesh data>` (MaterialBindingAPI, SkelBindingAPI) / `BlendShape` children. Validated topology is OK.

### 4.3 Numerical correctness (VERIFIED, exp. B)
For frames 1, 5 and 10 I compared Blender's evaluated world-space vertices (armature + shape key) with UsdSkel's own evaluation of the exported file. I used two methods: `SkinningQuery.ComputeSkinnedPoints` plus `BlendShapeQuery`, and an independent `UsdSkel.BakeSkinning`. Result: max error **≤ 2.4e-7** for the Z-up, Y-up (after undoing the root rotation), usdz and triangulated variants. Joint weights are normalised by Blender (`UsdSkelNormalizeWeights` in source; sums are 1.000000).

### 4.4 Defects and limitations found (VERIFIED by experiment/source, with workarounds)

| # | Problem | Evidence | Workaround |
|---|---|---|---|
| 1 | `UsdPreviewSurface.inputs:normal` authored as **`float3`** (spec: `normal3f`), so both checkers fail (`MismatchedPropertyType` / `ShaderPropertyTypeConformanceChecker`) | exp. E/G | pxr: re-create the input as `normal3f` with the same connection (exp. G) |
| 2 | Normal-map `scale=(2,2,2,2)`, `bias=(-1,-1,-1,-1)` (spec: alpha 1 and 0) | exp. E; source `set_normal_texture_range` | pxr: set alpha components to 1 and 0 |
| 3 | **`restTransforms` = pose at the export frame**, not the rest pose (`parent_relative_pose_mat(pchan)`) | exp. D4: a posed export differs by 0.17 in restTransforms, while bindTransforms are identical | set `armature.data.pose_position='REST'` for the model export, **or** recompute rest from bind with `UsdSkel.ComputeJointLocalTransforms` (exp. I: error 0.17 → 0) |
| 4 | `elementSize` = max number of vertex groups on any vertex, **including non-bone groups** (zero-weight slots); no cap | exp. D3: Body elementSize 7 (6 bones + mask group); after `vertex_group_limit_total(4)` still 5 | delete non-deform vertex groups before export; `vertex_group_limit_total(limit=4)` + `vertex_group_normalize_all`; or pxr `SortInfluences`/`ResizeInfluences` |
| 5 | `framesPerSecond` not written (fallback 24 while `timeCodesPerSecond`=30) | exp. B | pxr: `stage.SetFramesPerSecond(stage.GetTimeCodesPerSecond())` |
| 6 | `doubleSided = true` unless the first material has **Backface Culling** on, or if there is no material | source + exp. E (Body False, Mane True) | `mat.use_backface_culling = True`, or pxr set to False |
| 7 | Only one timeline per file; clips not named | source + exp. D5 | per-clip export loop, or NLA concatenation + JSON clip table |
| 8 | Lights, cameras and the world DomeLight are exported by default; UsdLux is not allowed by the ARKit checker | checker source | `export_lights=False, export_cameras=False, convert_world_material=False` |
| 9 | Non-deform bones exported as joints unless `only_deform_bones=True` | exp. A: `CTRL_helper` joint | `only_deform_bones=True`; make procedural-control joints deform bones (or parents of them) |
| 10 | Shape-key name collision across meshes is renamed (`Fat2`) | exp. E | name keys uniquely per mesh, or author names in pxr |
| 11 | No `normalOffsets`, no in-betweens | exp. B, source | author with pxr if needed |
| 12 | `.usdz` written with the non-ARKit packager | source | export `.usdc` and package with `CreateNewARKitUsdzPackage` |

Third-party reports (UNCERTAIN, not reproduced here):
- "active action overrides NLA" and "NLA export sometimes forgets `skel:animationSource`" (stepinto.vision article, blocked; seen only as a search snippet). In my exp. D5, with no active action, the NLA export set `skel:animationSource` correctly.
- RCP bundle animation and blendWeights naming mismatch ([forum 758179](https://developer.apple.com/forums/thread/758179)).
- Blank blend-shape weight names in RealityKit for some files ([forum 766484](https://developer.apple.com/forums/thread/766484)).

### 4.5 Blender export versus writing the USD ourselves with pxr

| | Blender 4.2 `usd_export` | Our own pxr writer (data read with bpy) |
|---|---|---|
| Effort | minimal | ~150–400 lines (exp. H is a complete small prototype) |
| Skin / blend-shape correctness | verified numerically | we must get it right ourselves (verifiable the same way as exp. B) |
| Joint naming and order | Blender names, sanitized | full control (stable names for Swift) |
| Rest pose | buggy (#3) | exact (`bind`/`rest` from edit bones) |
| Influences cap, sorting | manual pre-steps | `SortInfluences`/`ResizeInfluences` |
| normalOffsets, in-betweens | no | yes |
| Multiple clips | one timeline per file | separate SkelAnimations, variant set, per-clip files or AnimationLibrary prims, as desired |
| Materials | approximate Principled → PreviewSurface, with bugs #1/#2 | exactly what RealityKit supports (one packed ORM texture, raw normal map, `opacityThreshold` for hair cards) |
| Metadata (fps, kind, defaultPrim, doubleSided, subdivisionScheme) | partial | complete |

**Recommendation.** Hybrid. Author the rig and animations in Blender. Then either:
- (A, quick) export with Blender, using the settings below, then run the pxr fix-up pass from exp. G plus the rest-pose fix from exp. I; or
- (B, target) a custom pxr writer that reads the evaluated Blender data (bones' `matrix_local`, vertex groups, shape keys, per-frame pose matrices per action) and writes exactly the structure in §6.

Validate both with the two checkers and the numeric skinning comparison from exp. B.

Recommended Blender 4.2 export call (VERIFIED to run headless):
```python
bpy.ops.wm.usd_export(filepath="pony_clip.usdc", check_existing=False,
    export_animation=True, export_armatures=True, only_deform_bones=True, export_shapekeys=True,
    convert_orientation=True, export_global_forward_selection="Z", export_global_up_selection="Y",
    root_prim_path="/Pony", export_lights=False, export_cameras=False, convert_world_material=False,
    export_materials=True, generate_preview_surface=True, export_textures=True, relative_paths=True,
    export_subdivision="IGNORE")   # pre-steps: rest pose, limit_total(4), remove non-bone vgroups, backface culling
```
I tested the subset used in exp. F. `export_subdivision="IGNORE"` comes from the option list; its effect was not separately tested. `BEST_MATCH` already wrote `subdivisionScheme = "none"` when there was no Subdivision modifier (exp. A).

---

## 5. Experiments (all run in this container)

Scripts: `/tmp/claude-0/-home-user-taigment/d20146b6-2488-5713-a201-7967cf012183/scratchpad/experiments/usd/`. Re-run everything with `sh run_all.sh`. Logs are `out_exp_*.log`. Reference sources (Apple support scripts, OpenUSD docs, Blender 4.2 io/usd source, fbx2usd) are in `_refs/`.

| Script | What it does | Result |
|---|---|---|
| `exp_a_bpy_export.py` | bpy: 2-bone armature (+1 non-deform bone), skinned 9-ring cylinder (blend zone), shape key "Belly", textured Principled material, two actions (Bend active, Twist in a muted NLA strip), 10 frames at 30 fps; 5 exports (default Z-up anim, deform-only Y-up, direct .usdz, static, triangulated .usdc) | **All exports FINISHED** |
| `exp_b_inspect.py` | pxr: metadata, prim tree, UsdSkel structure, numeric check vs Blender | **SkelRoot / Skeleton / SkelAnimation / BlendShape all present**; error ≤ 2.4e-7 |
| `exp_c_compliance.py` | old API probe; vendored ARKit checker; ARKit packaging; UsdValidation; negative control | see below |
| `exp_d_bpy_gotchas.py` + `exp_e_inspect_d.py` | orientation, 2 meshes on 1 rig, influences, rest pose, clips, materials | see §4.2/§4.4 |
| `exp_f_export_yup.py` + `exp_g_fixup_package.py` | production-like Y-up export → pxr fixes → `CreateNewARKitUsdzPackage` → checks | **FAIL before fix → PASS after** |
| `exp_h_pxr_author.py` | full asset authored with pxr only (2 meshes, 4 influences, sparse blend shape with normalOffsets, 2 SkelAnimations + `animation` variant set, PreviewSurface + raw normal map) | **PASS both checkers**; variants switch the animation |
| `exp_i_fix_rest.py` | recompute restTransforms from bindTransforms | error 0.1736 → 0 |

Key outputs (verbatim excerpts):

```
# exp A/B: a1_default_anim.usda
 upAxis: Z  metersPerUnit: 1.0  defaultPrim: /root  start/end: 1.0 10.0  tcps: 30.0  fps: 24.0
 prim type counts: {'Xform': 2, 'SkelRoot': 1, 'Skeleton': 1, 'SkelAnimation': 1, 'Mesh': 1, 'BlendShape': 1, 'Scope': 1, 'Material': 1, 'Shader': 3}
 Skeleton /root/PonyRig/PonyRig joints=['Root', 'Root/Tip', 'CTRL_helper']
   SkelAnimation.translations type=float3[] nSamples=10
   SkelAnimation.rotations type=quatf[] nSamples=10
   SkelAnimation.scales type=half3[] nSamples=10
   SkelAnimation.blendShapeWeights type=float[] nSamples=10
 Mesh /root/PonyRig/Body/Body pts=108 faces=98 applied=['MaterialBindingAPI', 'SkelBindingAPI']
   jointIndices elementSize=2 interp=vertex  weights sum min/max=1.000000/1.000000
   frame 1: max |USD-skinned - Blender-evaluated| = 1.49e-07
   frame 5: max |USD-skinned - Blender-evaluated| = 1.79e-07
   frame 10: max |USD-skinned - Blender-evaluated| = 2.38e-07
 BlendShape /root/PonyRig/Body/Body/Belly offsets=108 pointIndices=108 normalOffsets authored=False inbetweens=[]
UsdSkel.BakeSkinning cross-check:  frame 10: max |baked - Blender| = 2.38e-07

# exp C: compliance
1) hasattr(UsdUtils, 'ComplianceChecker') = False
3) UsdUtils.CreateNewARKitUsdzPackage(a2_deform_yup.usda) -> True
   c_arkit_pkg.usdz entry 'a2_deform_yup.usdc' compress=0 data_offset%64=0
   c_arkit_pkg.usdz entry 'textures/coat_basecolor.png' compress=0 data_offset%64=0
   [ARKit ComplianceChecker v26.05] a1_default_anim.usda: FAIL  -> Stage specifies upAxis 'Z'. upAxis should be 'Y'.
   [ARKit ComplianceChecker v26.05] a2_deform_yup.usda: PASS
   [ARKit ComplianceChecker v26.05] a3_direct.usdz: PASS
   [ARKit ComplianceChecker v26.05] c_arkit_pkg.usdz: PASS
   [ARKit ComplianceChecker v26.05] c_bad.usda: FAIL  failedChecks=11 (SphereLight, PointInstancer, MyCustomShader, tga, missing SkelBindingAPI, ...)
4) UsdValidation framework: a1_default_anim.usda: 0 issue(s)   <- does NOT enforce Y-up
   c_bad.usda: 6 issue(s) (MissingMetersPerUnitMetadata, MissingDefaultPrim, InvalidResourcePath, MissingShaderIdInRegistry, UnresolvableDependency, MissingSkelBindingAPI)

# exp E (Blender gotchas)
 d1_conv_default_root.usda: upAxis=Y rootOps=[('xformOp:rotateXYZ', (-90, 0, 0))]  Nose joint head (world) = (0, 1, 1)   # Blender -Y -> USD +Z
  d3_influences_raw.usda Body: elementSize=7 max non-zero/vertex=6
  d3_influences_limit4.usda Body: elementSize=5 max non-zero/vertex=4
  max |restTransforms(posed export) - restTransforms(rest export)| = 0.1736
  d5_nla_timeline.usda: start/end=1.0/30.0 samples=30 animationSource=[/root/Rig/Rig/Anim]
  ARKit(v26.05) d3_influences_raw.usda: FAIL - Incorrect type for .../Principled_BSDF.inputs:normal. Expected 'normal3f'; got 'float3'.

# exp G (fix-up + package)
 [before fix] ARKit(v26.05) f_timeline.usda: FAIL ["Incorrect type for /Pony/_materials/Coat/Principled_BSDF.inputs:normal ..."]
 FIX: framesPerSecond := 30.0 / Mane doubleSided -> false / inputs:normal float3 -> normal3f / scale/bias alpha -> (1, 0)
 CreateNewARKitUsdzPackage -> True
 [after fix] ARKit(v26.05) pony.usdz: PASS []
 [after fix] UsdValidation pony.usdz: 0 issue(s) []
 usdz stage: upAxis Y mpu 1.0 tcps 30.0 fps 30.0 range 1.0 30.0

# exp H (pure pxr authoring)
 variant=walk: animQuery prim=/Pony/Rig/Skel/Walk ...   variant=graze: animQuery prim=/Pony/Rig/Skel/Graze ...
 ARKit(v26.05) pony_authored.usdz: PASS []   UsdValidation pony_authored.usdz: 0 issue(s) []
```

What failed or needed fixing during the experiments (honest log):
- My first blend-shape evaluation wrongly assumed `AnimMapper.Remap` writes in place. In Python it **returns** the remapped array. Fixed.
- My first `BakeSkinning` cross-check wrote into the session layer, whose `timeCodesPerSecond` is 24 against the root's 30. USD rescaled the samples (times 1.25), causing a false mismatch. Fixed by matching the session layer's tcps.
- In my first compliance run I read only `GetErrors()`. Rule failures are in `GetFailedChecks()`. Fixed, and added a negative control.
- `stage.Export()` flattening produced absolute texture paths, which the packager relocated into `0/`. Fixed by exporting the root layer.
- In-process re-open of an edited layer hid errors (see §3.2). Fixed by ordering the checks.
- My reading of the Blender source suggested that orientation conversion needs a root prim. **The experiment disproved that** (it works with `root_prim_path=""`). The report states the tested behaviour.

---

## 6. Recommended target structure for the pony USD (INFERRED design, checker-clean pattern from exp. H)
```
#usda 1.0  (upAxis="Y", metersPerUnit=1, timeCodesPerSecond=framesPerSecond=30, defaultPrim="Pony")
def Xform "Pony" (kind = "component")                      # entity root in RealityKit
    def SkelRoot "Rig"
        def Skeleton "Skel"  (SkelBindingAPI; joints = stable "_"-named paths, parents first;
                              bindTransforms = world rest; restTransforms = local rest; rel skel:animationSource)
            def SkelAnimation "<Clip>"   (only in clip files, or several + variant set)
        def Mesh "Body"  (SkelBindingAPI + MaterialBindingAPI; elementSize<=4 sorted+normalized;
                          geomBindTransform; subdivisionScheme="none"; doubleSided=false; primvars:st [+ st1])
            def BlendShape "<morph>"  (offsets, normalOffsets, pointIndices)   # morphology sliders
        def Mesh "Mane" / "Tail" / "Eyes" / "Hooves" ... (same skeleton)
        def Mesh "Acc_SaddlePad" ... skinned accessories bound to the same skeleton, toggled at runtime
    def Scope "Materials"  (UsdPreviewSurface: diffuse sRGB, ORM packed raw, normal raw OpenGL, opacityThreshold for hair cards)
```
- Rigid accessories (stirrups, plume, flowers, bell boots): separate entities attached at runtime with `entity.pins.set(named:skeletalJointName:)` and `attach(_:to:)` (iOS 26; [docs](https://developer.apple.com/documentation/realitykit/entity/attach(_:to:)); [WWDC25 287](https://developer.apple.com/videos/play/wwdc2025/287/): "greatly simplifies attaching meshes to the joints of an animated skeleton"). An Apple engineer confirmed this as "the new, recommended way" ([forum 798309](https://developer.apple.com/forums/thread/798309)).
- Deforming accessories (blankets, saddle pad, bandages): skinned meshes bound to the **same** Skeleton in the same file. Whether a separately loaded skinned accessory can follow another entity's skeleton is **UNCERTAIN** (not documented).
- Procedural layer:
  - `SkeletalPosesComponent` (iOS 18; read and write poses);
  - `IKComponent` (iOS 18; full-body IK);
  - `jointTransforms` ("Active animations may override the joint transforms set using this property", [docs](https://developer.apple.com/documentation/realitykit/hasmodel/jointtransforms));
  - `BlendShapeWeightsComponent` (iOS 18; weight names from the asset are immutable, [BlendShapeWeightsSet](https://developer.apple.com/documentation/realitykit/blendshapeweightsset)).

---

## 7. Open uncertainties: tests to run on a Mac or device
1. RealityKit cap on influences per vertex and joints per skeleton (none documented). Test 4 versus 8 influences and 60 versus 200 joints.
2. Which multi-clip encoding RealityKit exposes in `availableAnimations` / `AnimationLibraryComponent` on iOS 26:
   - (a) per-clip USDZ files;
   - (b) variant set on `skel:animationSource`;
   - (c) several SkelAnimation prims;
   - (d) the unofficial `RealityKitComponent "AnimationLibrary"` prims;
   - (e) `scntool --append-animation` output. Inspect its USD with `usdcat` to learn Apple's real encoding.
3. The time origin of a USD-loaded `AnimationResource` (`startTimeCode` versus 0), needed for `AnimationView.trimStart` values. Also whether `framesPerSecond` is read.
4. Whether RealityKit ignores UsdUVTexture `scale`/`bias` on normal maps (Apple says Bias ✗, Scale ✗ for normal maps), i.e. whether spec-compliant values render correctly.
5. Shading of blend shapes without `normalOffsets`.
6. How multiple meshes under one SkelRoot become entities (one ModelEntity or several), and whether `jointTransforms` writes affect all of them.
7. AVIF textures inside USDZ on iOS 26 (Apple lists AVIF, but the OpenUSD checkers reject it).
8. Whether Xcode's automatic texture compression applies to a plain `.usdz` resource or only to RCP / `.reality` content.

---

## 8. Sources
Apple:
- https://developer.apple.com/documentation/usd/creating-usd-files-for-apple-devices
- https://developer.apple.com/documentation/usd/validating-usd-files
- https://developer.apple.com/download/files/USD-Support-Scripts.zip (usd_conditioner.py, variant_combiner.py, read locally)
- https://developer.apple.com/documentation/realitykit/animationlibrarycomponent
- https://developer.apple.com/documentation/realitykit/entity/availableanimations
- https://developer.apple.com/documentation/realitykit/animationview
- https://developer.apple.com/documentation/realitykit/animationresource
- https://developer.apple.com/documentation/realitykit/blendshapeweightscomponent
- https://developer.apple.com/documentation/realitykit/blendshapeweightsmapping
- https://developer.apple.com/documentation/realitykit/blendshapeweightsset
- https://developer.apple.com/documentation/realitykit/meshjointinfluence
- https://developer.apple.com/documentation/realitykit/meshresource/jointinfluences
- https://developer.apple.com/documentation/realitykit/meshresource/skeleton
- https://developer.apple.com/documentation/realitykit/skeletalposescomponent
- https://developer.apple.com/documentation/realitykit/ikcomponent
- https://developer.apple.com/documentation/realitykit/hasmodel/jointtransforms
- https://developer.apple.com/documentation/realitykit/geometricpin
- https://developer.apple.com/documentation/realitykit/entity/pins
- https://developer.apple.com/documentation/realitykit/entity/attach(_:to:)
- https://developer.apple.com/documentation/realitykit/entity/forwarddirection
- WWDC24 10186 "Optimize your 3D assets for spatial computing": https://developer.apple.com/videos/play/wwdc2024/10186/
- WWDC25 288 "Bring your SceneKit project to RealityKit": https://developer.apple.com/videos/play/wwdc2025/288/
- WWDC25 287 "What's new in RealityKit": https://developer.apple.com/videos/play/wwdc2025/287/
- Forums: https://developer.apple.com/forums/thread/766484 , https://developer.apple.com/forums/thread/758179 , https://developer.apple.com/forums/thread/798309 , https://developer.apple.com/forums/thread/650515 , https://developer.apple.com/forums/thread/761021

OpenUSD (read from GitHub source at the stated tags; the same docs as openusd.org):
- UsdSkel schemas: https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/pxr/usd/usdSkel/doxygen/schemas.dox (= https://openusd.org/release/api/_usd_skel__schemas.html)
- UsdSkel schema.usda: https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/pxr/usd/usdSkel/schema.usda
- UsdPreviewSurface spec: https://openusd.org/release/spec_usdpreviewsurface.html (source docs/spec_usdpreviewsurface.rst @v26.08)
- USDZ spec: https://openusd.org/release/spec_usdz.html (source docs/spec_usdz.rst @v26.08)
- CHANGELOG: https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/CHANGELOG.md
- complianceChecker.py (last version): https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.05/pxr/usd/usdUtils/complianceChecker.py
- usdzPackage.h: https://github.com/PixarAnimationStudios/OpenUSD/blob/v26.08/pxr/usd/usdUtils/usdzPackage.h

Blender 4.2.0 source (GitHub mirror, tag v4.2.0):
- https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_writer_armature.cc
- https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_writer_mesh.cc
- https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_skel_convert.cc
- https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_blend_shape_utils.cc
- https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_writer_material.cc
- https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_capi_export.cc
- https://github.com/blender/blender/blob/v4.2.0/source/blender/io/usd/intern/usd_armature_utils.cc
- Manual (blocked here, not read): https://docs.blender.org/manual/en/4.2/files/import_export/usd.html
- PR "USD: Support armature and shape key export" (search snippet only): https://projects.blender.org/blender/blender/pulls/111931
- PR "USD: Add an option to convert the scene's meters per unit value" (search snippet only): https://projects.blender.org/blender/blender/pulls/122804

Third-party (UNCERTAIN, for orientation only):
- https://github.com/apparata/fbx2usd (RealityKit AnimationLibrary USDA layout, reverse-engineered; commit 9443dd1, Jan 2026)
