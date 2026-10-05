import Foundation
import PonyCore
import RealityKit

/// Substitut primitif affiché quand `Pony.usdz` est absent ou illisible : silhouette en boîtes (tronc, encolure,
/// tête, membres, queue) aux proportions du gabarit 1,30 m (SPEC §2), non articulée. Garde le terrain de jeu
/// utilisable (déplacement, caméra, interface) pendant le développement. Coloré d'après le phénotype de la robe.
@MainActor
final class PonyPlaceholder {
    let entity: Entity
    private var coatMaterialEntities: [ModelEntity] = []
    private var maneEntities: [ModelEntity] = []
    private var hoofEntities: [ModelEntity] = []

    init() {
        entity = Entity()
        build()
    }

    private func box(_ size: SIMD3<Float>, at p: SIMD3<Float>, pitch: Float = 0) -> ModelEntity {
        let m = ModelEntity(mesh: MeshResource.generateBox(width: size.x, height: size.y, depth: size.z),
                            materials: [PhysicallyBasedMaterial()])
        m.position = p
        if pitch != 0 {
            m.orientation = simd_quatf(angle: pitch, axis: SIMD3<Float>(1, 0, 0))
        }
        entity.addChild(m)
        return m
    }

    private func build() {
        // Repères (RealityKit : +Y haut, −Z avant), d'après SPEC §2 (gabarit 1,30 m).
        coatMaterialEntities.append(box(SIMD3<Float>(0.40, 0.50, 1.30), at: SIMD3<Float>(0, 0.98, 0.05)))   // tronc
        coatMaterialEntities.append(box(SIMD3<Float>(0.20, 0.55, 0.28), at: SIMD3<Float>(0, 1.22, -0.70),
                                        pitch: -0.6))                                                     // encolure
        coatMaterialEntities.append(box(SIMD3<Float>(0.20, 0.22, 0.52), at: SIMD3<Float>(0, 1.30, -1.05),
                                        pitch: 0.75))                                                     // tête
        for x: Float in [-0.13, 0.13] {
            for z: Float in [-0.45, 0.55] {
                coatMaterialEntities.append(box(SIMD3<Float>(0.10, 0.72, 0.10), at: SIMD3<Float>(x, 0.40, z)))
                hoofEntities.append(box(SIMD3<Float>(0.11, 0.06, 0.12), at: SIMD3<Float>(x, 0.03, z)))
            }
        }
        maneEntities.append(box(SIMD3<Float>(0.06, 0.50, 0.30), at: SIMD3<Float>(0, 1.36, -0.66), pitch: -0.6))
        maneEntities.append(box(SIMD3<Float>(0.10, 0.62, 0.10), at: SIMD3<Float>(0, 0.86, 0.78), pitch: 0.25))
    }

    /// Couleurs d'après le phénotype (corps, crins, sabot antérieur gauche).
    func recolor(_ coat: CoatConfiguration) {
        let ph = coat.phenotype
        set(coatMaterialEntities, ph.bodyColor, roughness: 0.8)
        set(maneEntities, ph.maneColor, roughness: 0.6)
        set(hoofEntities, ph.hoofColors.first ?? PonyColor(r: 0.18, g: 0.16, b: 0.15), roughness: 0.4)
    }

    private func set(_ entities: [ModelEntity], _ color: PonyColor, roughness: Float) {
        var m = PhysicallyBasedMaterial()
        m.baseColor = PhysicallyBasedMaterial.BaseColor(tint: color.platformColor, texture: nil)
        m.roughness = PhysicallyBasedMaterial.Roughness(scale: roughness)
        for e in entities {
            e.model?.materials = [m]
        }
    }
}
