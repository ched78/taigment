import CoreGraphics
import Foundation
import PonyCore
import RealityKit

/// Type de sol procédural (hors du type `@MainActor` pour rester utilisable par les fonctions de calcul
/// non isolées).
enum PonyGroundKind: Sendable {
    case grass, straw
}

/// Éléments de décor créés par `PonySceneBuilder`.
@MainActor
public struct PonySceneSetup {
    /// Racine du décor (à ajouter au contenu de la `RealityView`).
    public let root: Entity
    /// Sol (modèle visible) ; son enfant `GroundCollider` porte la collision (y ≤ 0).
    public let ground: Entity
    /// Soleil : `DirectionalLightComponent` + `DirectionalLightComponent.Shadow`.
    public let sun: Entity
    /// Entité d'éclairage d'ambiance (IBL) à passer à `PonyController.imageBasedLight`, si créée.
    public let imageBasedLight: Entity?
    /// Ressource d'environnement (pour `content.environment = .skybox(…)`), si créée.
    public let environment: EnvironmentResource?
}

/// Décors de démonstration : paddock (sol, clôture, cavalettis, soleil, ciel) et écurie (sol de paille, lumière
/// douce).
///
/// API vérifiées (Tools/apple_doc.py) : `MeshResource.generatePlane(width:depth:cornerRadius:)`,
/// `generateBox(width:height:depth:cornerRadius:splitFaces:)`, `generateCylinder(height:radius:)` (iOS 18),
/// `ModelEntity(mesh:materials:)`, `CollisionComponent(shapes:mode:filter:)`,
/// `ShapeResource.generateBox(width:height:depth:)`, `PhysicsBodyComponent(shapes:mass:material:mode:)` (`.static`),
/// `DirectionalLightComponent(color:intensity:isRealWorldProxy:)` (iOS 13 / macOS 10.15 ; l'initialiseur sans
/// `isRealWorldProxy` est réservé à visionOS), `DirectionalLightComponent.Shadow(shadowProjection:depthBias:cullMode:)`
/// (iOS 18), `ImageBasedLightComponent(source:intensityExponent:)` + `ImageBasedLightReceiverComponent` (iOS 18),
/// `EnvironmentResource(equirectangular:withName:)` (iOS 18, dépréciée en 27.2 seulement),
/// `GroundingShadowComponent(castsShadow:receivesShadow:)` (iOS 18), `textureCoordinateTransform` (iOS 15).
/// Note : RealityKit ignore les lumières décrites dans les USD (realitykit.md §6.3) — elles sont créées ici.
@MainActor
public enum PonySceneBuilder {

    /// Paddock en herbe de `size` m de côté, clôture circulaire (rayon `fenceRadius`), quelques cavalettis
    /// (visuels seulement : sans collision pour pouvoir être sautés en mode contrôleur de personnage [I]).
    public static func makePaddock(size: Float = 80, fenceRadius: Float = 16,
                                   locator: PonyResourceLocator? = PonyResourceLocator.bundled) async -> PonySceneSetup {
        let root = Entity()
        root.name = "Paddock"
        let grass = await groundMaterial(kind: .grass, tiles: size / 3)
        let ground = makeGround(size: size, material: grass)
        root.addChild(ground)

        // Clôture : poteaux (avec collision) et lisses (sans).
        let fence = Entity()
        fence.name = "Fence"
        var post = PhysicallyBasedMaterial()
        post.baseColor = PhysicallyBasedMaterial.BaseColor(tint: PonyColor(hex: "#7A5A3C").platformColor, texture: nil)
        post.roughness = PhysicallyBasedMaterial.Roughness(scale: 0.85)
        let postMesh = MeshResource.generateCylinder(height: 1.2, radius: 0.06)
        let count = 36
        for i in 0..<count {
            let a = Float(i) / Float(count) * 2 * Float.pi
            let p = ModelEntity(mesh: postMesh, materials: [post])
            p.position = SIMD3<Float>(cos(a) * fenceRadius, 0.6, sin(a) * fenceRadius)
            p.components.set(CollisionComponent(shapes: [ShapeResource.generateBox(width: 0.14, height: 1.2, depth: 0.14)]))
            p.components.set(GroundingShadowComponent(castsShadow: true))
            fence.addChild(p)
            // Lisses entre deux poteaux.
            let a2 = Float(i + 1) / Float(count) * 2 * Float.pi
            let p2 = SIMD3<Float>(cos(a2) * fenceRadius, 0, sin(a2) * fenceRadius)
            let p1 = SIMD3<Float>(cos(a) * fenceRadius, 0, sin(a) * fenceRadius)
            let mid = (p1 + p2) * 0.5
            let length = simd_length(p2 - p1)
            for h: Float in [0.55, 1.0] {
                let rail = ModelEntity(mesh: MeshResource.generateBox(width: length, height: 0.08, depth: 0.04),
                                       materials: [post])
                rail.position = SIMD3<Float>(mid.x, h, mid.z)
                let dir = p2 - p1
                rail.orientation = simd_quatf(angle: atan2(-dir.z, dir.x), axis: SIMD3<Float>(0, 1, 0))
                fence.addChild(rail)
            }
        }
        root.addChild(fence)

        // Cavalettis (barre à 0,5 m) [A].
        var pole = PhysicallyBasedMaterial()
        pole.baseColor = PhysicallyBasedMaterial.BaseColor(tint: PonyColor(hex: "#E9E4D8").platformColor, texture: nil)
        pole.roughness = PhysicallyBasedMaterial.Roughness(scale: 0.6)
        var stripe = PhysicallyBasedMaterial()
        stripe.baseColor = PhysicallyBasedMaterial.BaseColor(tint: PonyColor(hex: "#B3262E").platformColor, texture: nil)
        stripe.roughness = PhysicallyBasedMaterial.Roughness(scale: 0.6)
        for (i, spot) in [SIMD3<Float>(0, 0, -8), SIMD3<Float>(7, 0, 3), SIMD3<Float>(-7, 0, 4)].enumerated() {
            let jump = Entity()
            jump.name = "Cavaletti\(i)"
            jump.position = spot
            jump.orientation = simd_quatf(angle: Float(i) * 1.1, axis: SIMD3<Float>(0, 1, 0))
            for x: Float in [-1.4, 1.4] {
                let standard = ModelEntity(mesh: MeshResource.generateBox(width: 0.12, height: 0.9, depth: 0.12),
                                           materials: [stripe])
                standard.position = SIMD3<Float>(x, 0.45, 0)
                standard.components.set(GroundingShadowComponent(castsShadow: true))
                jump.addChild(standard)
            }
            let bar = ModelEntity(mesh: MeshResource.generateBox(width: 2.8, height: 0.08, depth: 0.08), materials: [pole])
            bar.position = SIMD3<Float>(0, 0.5, 0)
            bar.components.set(GroundingShadowComponent(castsShadow: true))
            jump.addChild(bar)
            root.addChild(jump)
        }

        let sun = makeSun(intensity: 3000, direction: SIMD3<Float>(4, 7, 3))
        root.addChild(sun)
        let (ibl, env) = await makeImageBasedLight(locator: locator, sky: true)
        if let ibl = ibl {
            root.addChild(ibl)
            applyReceiver(ibl, to: root)
        }
        return PonySceneSetup(root: root, ground: ground, sun: sun, imageBasedLight: ibl, environment: env)
    }

    /// Écurie : sol de paille de `size` m, lumière douce, fond clair.
    public static func makeStable(size: Float = 14,
                                  locator: PonyResourceLocator? = PonyResourceLocator.bundled) async -> PonySceneSetup {
        let root = Entity()
        root.name = "Stable"
        let straw = await groundMaterial(kind: .straw, tiles: size / 2)
        let ground = makeGround(size: size, material: straw)
        root.addChild(ground)
        let sun = makeSun(intensity: 2200, direction: SIMD3<Float>(-3, 6, 4))
        root.addChild(sun)
        let (ibl, env) = await makeImageBasedLight(locator: locator, sky: false)
        if let ibl = ibl {
            root.addChild(ibl)
            applyReceiver(ibl, to: root)
        }
        return PonySceneSetup(root: root, ground: ground, sun: sun, imageBasedLight: ibl, environment: env)
    }

    // MARK: Briques

    static func makeGround(size: Float, material: PhysicallyBasedMaterial) -> Entity {
        let ground = ModelEntity(mesh: MeshResource.generatePlane(width: size, depth: size), materials: [material])
        ground.name = "Ground"
        ground.components.set(GroundingShadowComponent(castsShadow: false, receivesShadow: true))
        let collider = Entity()
        collider.name = "GroundCollider"
        collider.position = SIMD3<Float>(0, -0.05, 0)
        let shape = ShapeResource.generateBox(width: size, height: 0.1, depth: size)
        collider.components.set(CollisionComponent(shapes: [shape]))
        collider.components.set(PhysicsBodyComponent(shapes: [shape], mass: 0, material: nil, mode: .static))
        ground.addChild(collider)
        return ground
    }

    /// Soleil orienté vers l'origine depuis `direction` ; la lumière éclaire selon −Z de l'entité [I : convention
    /// supposée, `look(at:from:…forward: .negativeZ)`].
    static func makeSun(intensity: Float, direction: SIMD3<Float>) -> Entity {
        let sun = Entity()
        sun.name = "Sun"
        sun.components.set(DirectionalLightComponent(color: PonyColor(hex: "#FFF4E2").platformColor,
                                                     intensity: intensity, isRealWorldProxy: false))
        sun.components.set(DirectionalLightComponent.Shadow(shadowProjection: .automatic(maximumDistance: 30),
                                                            depthBias: 1.0))
        sun.look(at: SIMD3<Float>(0, 0, 0), from: direction, upVector: SIMD3<Float>(0, 1, 0), relativeTo: nil,
                 forward: .negativeZ)
        return sun
    }

    static func applyReceiver(_ ibl: Entity, to root: Entity) {
        for m in PonyEntityTree.modelEntities(in: root) {
            m.components.set(ImageBasedLightReceiverComponent(imageBasedLight: ibl))
        }
    }

    /// Éclairage d'ambiance : image `environment.*` du dossier de ressources si présente, sinon ciel dégradé
    /// généré (512 × 256, équirectangulaire) [A].
    static func makeImageBasedLight(locator: PonyResourceLocator?, sky: Bool) async -> (Entity?, EnvironmentResource?) {
        var image: CGImage?
        if let loc = locator {
            for name in PonyResourceNames.environmentCandidates where loc.exists(name) {
                image = PonyImageIO.loadCGImage(contentsOf: loc.url(for: name))
                if image != nil {
                    PonyLog.info("éclairage d'ambiance : \(name)")
                    break
                }
            }
        }
        if image == nil {
            let rgba = await Task.detached(priority: .userInitiated) { () -> RGBA8Image in
                return PonySceneBuilder.skyGradient(width: 512, height: 256, outdoor: sky)
            }.value
            image = PonyImageIO.makeCGImage(rgba, opaque: true)
        }
        guard let cg = image else { return (nil, nil) }
        do {
            let env = try await EnvironmentResource(equirectangular: cg, withName: sky ? "valombre_sky" : "valombre_stable")
            let e = Entity()
            e.name = "ImageBasedLight"
            e.components.set(ImageBasedLightComponent(source: .single(env), intensityExponent: sky ? 0.4 : 0.6))
            return (e, env)
        } catch {
            PonyLog.warning("éclairage d'ambiance indisponible : \(error.localizedDescription)")
            return (nil, nil)
        }
    }

    // MARK: Textures procédurales [A]

    static func groundMaterial(kind: PonyGroundKind, tiles: Float) async -> PhysicallyBasedMaterial {
        var m = PhysicallyBasedMaterial()
        m.roughness = PhysicallyBasedMaterial.Roughness(scale: 0.95)
        let rgba = await Task.detached(priority: .userInitiated) { () -> RGBA8Image in
            return PonySceneBuilder.noiseTexture(kind: kind, size: 256)
        }.value
        if let cg = PonyImageIO.makeCGImage(rgba, opaque: true),
           let tex = try? await TextureResource(image: cg, withName: kind == .grass ? "valombre_grass" : "valombre_straw",
                                                options: TextureResource.CreateOptions(semantic: .color)) {
            m.baseColor = PhysicallyBasedMaterial.BaseColor(tint: PonyColor.white.platformColor,
                                                           texture: PhysicallyBasedMaterial.Texture(tex))
            m.textureCoordinateTransform = PhysicallyBasedMaterial.TextureCoordinateTransform(
                offset: SIMD2<Float>(0, 0), scale: SIMD2<Float>(tiles, tiles), rotation: 0)
        } else {
            let c = kind == .grass ? PonyColor(hex: "#5F7A3A") : PonyColor(hex: "#C9AE6B")
            m.baseColor = PhysicallyBasedMaterial.BaseColor(tint: c.platformColor, texture: nil)
        }
        return m
    }

    /// Bruit de valeur à deux octaves + grain par texel, périodique (texture répétable).
    nonisolated static func noiseTexture(kind: PonyGroundKind, size: Int) -> RGBA8Image {
        let n = max(size, 16)
        var px = [UInt8](repeating: 255, count: n * n * 4)
        let (dark, light): (SIMD3<Float>, SIMD3<Float>) = kind == .grass
            ? (SIMD3<Float>(0.27, 0.36, 0.16), SIMD3<Float>(0.45, 0.56, 0.26))
            : (SIMD3<Float>(0.62, 0.50, 0.28), SIMD3<Float>(0.86, 0.75, 0.48))
        func hash(_ x: Int, _ y: Int, _ s: UInt32) -> Float {
            var h = UInt32(truncatingIfNeeded: x) &* 0x8DA6B343 ^ UInt32(truncatingIfNeeded: y) &* 0xD8163841 ^ s
            h ^= h >> 15
            h = h &* 0x2C1B3C6D
            h ^= h >> 12
            return Float(h & 0xFFFF) / 65535
        }
        func value(_ fx: Float, _ fy: Float, cells: Int, _ s: UInt32) -> Float {
            let x = fx * Float(cells)
            let y = fy * Float(cells)
            let x0 = Int(x.rounded(.down))
            let y0 = Int(y.rounded(.down))
            let tx = x - Float(x0)
            let ty = y - Float(y0)
            let sx = tx * tx * (3 - 2 * tx)
            let sy = ty * ty * (3 - 2 * ty)
            func h(_ i: Int, _ j: Int) -> Float {
                return hash(((i % cells) + cells) % cells, ((j % cells) + cells) % cells, s)
            }
            let a = h(x0, y0) + (h(x0 + 1, y0) - h(x0, y0)) * sx
            let b = h(x0, y0 + 1) + (h(x0 + 1, y0 + 1) - h(x0, y0 + 1)) * sx
            return a + (b - a) * sy
        }
        for y in 0..<n {
            for x in 0..<n {
                let fx = Float(x) / Float(n)
                let fy = Float(y) / Float(n)
                var t = 0.55 * value(fx, fy, cells: 4, 11) + 0.30 * value(fx, fy, cells: 16, 23)
                t += 0.15 * hash(x, y, 37)
                if kind == .straw {
                    // Brins : stries obliques.
                    let s = (fx * 40 + fy * 12)
                    t = t * 0.7 + 0.3 * (s - s.rounded(.down))
                }
                let c = dark + (light - dark) * min(max(t, 0), 1)
                let o = (y * n + x) * 4
                px[o] = UInt8(min(max(c.x * 255, 0), 255))
                px[o + 1] = UInt8(min(max(c.y * 255, 0), 255))
                px[o + 2] = UInt8(min(max(c.z * 255, 0), 255))
            }
        }
        return RGBA8Image(width: n, height: n, pixels: px)
    }

    /// Ciel équirectangulaire : zénith → horizon → sol (extérieur), ou intérieur chaud et uniforme.
    nonisolated static func skyGradient(width: Int, height: Int, outdoor: Bool) -> RGBA8Image {
        var px = [UInt8](repeating: 255, count: width * height * 4)
        let zenith = outdoor ? SIMD3<Float>(0.36, 0.56, 0.82) : SIMD3<Float>(0.80, 0.74, 0.64)
        let horizon = outdoor ? SIMD3<Float>(0.83, 0.89, 0.94) : SIMD3<Float>(0.93, 0.88, 0.78)
        let groundNear = outdoor ? SIMD3<Float>(0.42, 0.48, 0.30) : SIMD3<Float>(0.55, 0.45, 0.30)
        let groundFar = outdoor ? SIMD3<Float>(0.30, 0.34, 0.22) : SIMD3<Float>(0.40, 0.33, 0.24)
        for y in 0..<height {
            let v = (Float(y) + 0.5) / Float(height)      // 0 = zénith, 1 = nadir
            let c: SIMD3<Float>
            if v < 0.5 {
                let t = v / 0.5
                c = zenith + (horizon - zenith) * (t * t)
            } else {
                let t = (v - 0.5) / 0.5
                c = groundNear + (groundFar - groundNear) * t
            }
            for x in 0..<width {
                let o = (y * width + x) * 4
                px[o] = UInt8(min(max(c.x * 255, 0), 255))
                px[o + 1] = UInt8(min(max(c.y * 255, 0), 255))
                px[o + 2] = UInt8(min(max(c.z * 255, 0), 255))
            }
        }
        return RGBA8Image(width: width, height: height, pixels: px)
    }
}
