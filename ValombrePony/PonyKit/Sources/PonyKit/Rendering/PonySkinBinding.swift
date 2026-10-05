import Foundation
import PonyCore
import RealityKit

// Dans ce fichier, `Transform` est ambigu (RealityKit / PonyCore) : toujours qualifier le module.

extension RealityKit.Transform {
    /// Conversion d'une transformation locale PonyCore (quaternion `[x, y, z, w]`, mêmes axes : le runtime
    /// travaille déjà en espace RealityKit, SPEC §1).
    init(pony t: PonyCore.Transform) {
        self.init(scale: t.scale,
                  rotation: simd_quatf(ix: t.rotation.x, iy: t.rotation.y, iz: t.rotation.z, r: t.rotation.w),
                  translation: t.translation)
    }
}

extension Quat {
    /// Conversion depuis un quaternion simd (RealityKit).
    public init(_ q: simd_quatf) {
        self.init(x: q.imag.x, y: q.imag.y, z: q.imag.z, w: q.real)
    }
}

/// Parcours de hiérarchie et diagnostic des entités importées.
@MainActor
enum PonyEntityTree {
    /// L'entité et tous ses descendants (ordre préfixe).
    static func descendants(of root: Entity) -> [Entity] {
        var out: [Entity] = []
        var stack: [Entity] = [root]
        while let e = stack.popLast() {
            out.append(e)
            stack.append(contentsOf: Array(e.children).reversed())
        }
        return out
    }

    /// Entités portant un `ModelComponent`.
    static func modelEntities(in root: Entity) -> [Entity] {
        return descendants(of: root).filter { $0.components.has(ModelComponent.self) }
    }

    /// Entités portant un `SkeletalPosesComponent` (squelette importé d'un UsdSkel).
    static func poseEntities(in root: Entity) -> [Entity] {
        return descendants(of: root).filter { $0.components.has(SkeletalPosesComponent.self) }
    }

    /// Entités portant un `BlendShapeWeightsComponent`.
    static func blendEntities(in root: Entity) -> [Entity] {
        return descendants(of: root).filter { $0.components.has(BlendShapeWeightsComponent.self) }
    }

    /// Arbre lisible : nom, composants pertinents, noms de matériaux (tests sur appareil, realitykit.md §9.1).
    static func describe(_ root: Entity) -> String {
        var lines: [String] = []
        func visit(_ e: Entity, _ depth: Int) {
            var tags: [String] = []
            if e.components.has(ModelComponent.self) { tags.append("Model") }
            if e.components.has(SkeletalPosesComponent.self) { tags.append("SkeletalPoses") }
            if e.components.has(BlendShapeWeightsComponent.self) { tags.append("BlendShapeWeights") }
            if e.components.has(AnimationLibraryComponent.self) { tags.append("AnimationLibrary") }
            var extra = ""
            if let model = e.components[ModelComponent.self] {
                let names = model.materials.map { m -> String in
                    let kind = m is PhysicallyBasedMaterial ? "PBR" : "\(type(of: m))"
                    return "\(m.name ?? "∅")(\(kind))"
                }
                extra += " matériaux=[\(names.joined(separator: ", "))]"
            }
            if let poses = e.components[SkeletalPosesComponent.self], let p = poses.poses.default {
                extra += " joints=\(p.jointNames.count) (ex. \(p.jointNames.prefix(3).joined(separator: ", ")))"
            }
            if let bs = e.components[BlendShapeWeightsComponent.self] {
                var parts: [String] = []
                for data in bs.weightSet {
                    parts.append("\(data.weightNames.count) poids")
                }
                extra += " blendShapes=[\(parts.joined(separator: ", "))]"
            }
            let indent = String(repeating: "  ", count: depth)
            lines.append("\(indent)- « \(e.name) » [\(tags.joined(separator: ", "))]\(extra)")
            for c in e.children {
                visit(c, depth + 1)
            }
        }
        visit(root, 0)
        return lines.joined(separator: "\n")
    }

    /// Dernier segment d'un nom de type chemin (`root/body/hips` → `hips`).
    nonisolated static func shortName(_ s: String) -> String {
        if let last = s.split(separator: "/").last {
            return String(last)
        }
        return s
    }
}

/// Lien entre le runtime (ordre des joints du manifeste, noms de blend shapes) et UNE entité RealityKit
/// importée (corps ou pièce) : table de correspondance des joints, table des poids, écriture par frame.
///
/// - Joints : les noms de `SkeletalPose.jointNames` peuvent être des chemins USD ; on compare le dernier
///   segment au nom court du manifeste (SPEC §1), puis le chemin complet. Joints absents journalisés.
/// - Poids : table nom → (élément de `weightSet`, indice de poids) construite une fois ; noms inconnus du runtime
///   ignorés. Écriture seulement si une valeur a changé (> 1e-4).
@MainActor
final class PonySkinBinding {
    let entity: Entity
    let label: String
    /// Indice du joint du manifeste pour chaque joint de la pose RealityKit (−1 = laissé tel quel).
    private(set) var jointMap: [Int] = []
    private(set) var missingJoints: [String] = []
    private(set) var unknownJoints: [String] = []
    let hasPose: Bool

    private struct WeightEntry {
        let weightIndex: Int
        let name: String
        let flatIndex: Int
    }

    private var weightTable: [[WeightEntry]] = []
    private var lastWeights: [Float] = []
    private(set) var ignoredWeightNames: [String] = []
    let hasWeights: Bool
    private var poseWarningLogged = false

    init(entity: Entity, label: String, manifest: PonyRigManifest, knownShapes: Set<String>) {
        self.entity = entity
        self.label = label
        var byName: [String: Int] = [:]
        var byPath: [String: Int] = [:]
        for (i, j) in manifest.joints.enumerated() {
            byName[j.name] = i
            byPath[j.path] = i
        }

        // Joints.
        if let poses = entity.components[SkeletalPosesComponent.self], let pose = poses.poses.default {
            hasPose = true
            var map: [Int] = []
            var found = Set<Int>()
            for raw in pose.jointNames {
                let idx = byName[PonyEntityTree.shortName(raw)] ?? byPath[raw] ?? -1
                map.append(idx)
                if idx >= 0 { found.insert(idx) } else { unknownJoints.append(raw) }
            }
            jointMap = map
            missingJoints = manifest.joints.enumerated().filter { !found.contains($0.offset) }.map { $0.element.name }
            if !missingJoints.isEmpty {
                PonyLog.warning("\(label) : \(missingJoints.count) joint(s) du manifeste absents du squelette importé "
                    + "(\(missingJoints.prefix(6).joined(separator: ", "))…)")
            }
            if !unknownJoints.isEmpty {
                PonyLog.warning("\(label) : \(unknownJoints.count) joint(s) importés inconnus du manifeste, laissés "
                    + "à leur pose (\(unknownJoints.prefix(4).joined(separator: ", "))…)")
            }
        } else {
            hasPose = false
        }

        // Poids des blend shapes.
        if let bs = entity.components[BlendShapeWeightsComponent.self] {
            var table: [[WeightEntry]] = []
            var flat = 0
            var ignored: [String] = []
            for data in bs.weightSet {
                var entries: [WeightEntry] = []
                for (wi, raw) in data.weightNames.enumerated() {
                    let name = PonyEntityTree.shortName(raw)
                    if knownShapes.contains(name) {
                        entries.append(WeightEntry(weightIndex: wi, name: name, flatIndex: flat))
                        flat += 1
                    } else if knownShapes.contains(raw) {
                        entries.append(WeightEntry(weightIndex: wi, name: raw, flatIndex: flat))
                        flat += 1
                    } else {
                        ignored.append(raw)
                    }
                }
                table.append(entries)
            }
            weightTable = table
            lastWeights = [Float](repeating: -1, count: flat)
            ignoredWeightNames = ignored
            hasWeights = flat > 0
            if !ignored.isEmpty {
                PonyLog.info("\(label) : blend shapes non pilotées par le runtime : \(ignored.prefix(8).joined(separator: ", "))")
            }
        } else {
            hasWeights = false
        }
    }

    /// Écrit la pose locale (ordre du manifeste, déjà convertie) dans `SkeletalPosesComponent.poses.default`.
    func writePose(_ pose: [RealityKit.Transform]) {
        guard hasPose, var component = entity.components[SkeletalPosesComponent.self],
              var skeletal = component.poses.default else { return }
        var transforms = skeletal.jointTransforms
        let count = transforms.count
        if count < jointMap.count {
            // Pose importée sans transformations (non documenté) : on reconstruit un tableau complet [I].
            if !poseWarningLogged {
                poseWarningLogged = true
                PonyLog.warning("\(label) : pose importée incomplète (\(count)/\(jointMap.count)), reconstruite")
            }
            var full = [RealityKit.Transform](repeating: RealityKit.Transform(), count: jointMap.count)
            for (i, m) in jointMap.enumerated() where m >= 0 && m < pose.count {
                full[i] = pose[m]
            }
            transforms = JointTransforms(full)
        } else {
            let base = transforms.startIndex
            for i in 0..<jointMap.count {
                let m = jointMap[i]
                if m >= 0 && m < pose.count {
                    transforms[base + i] = pose[m]
                }
            }
        }
        skeletal.jointTransforms = transforms
        component.poses.default = skeletal
        entity.components.set(component)
    }

    /// Écrit les poids (noms → valeurs 0…1). Sans changement depuis la dernière écriture : rien n'est fait.
    func writeWeights(_ weights: [String: Float], force: Bool = false) {
        guard hasWeights, var component = entity.components[BlendShapeWeightsComponent.self] else { return }
        var changed = force
        if !changed {
            outer: for entries in weightTable {
                for e in entries {
                    let v = weights[e.name] ?? 0
                    if abs(v - lastWeights[e.flatIndex]) > 1e-4 {
                        changed = true
                        break outer
                    }
                }
            }
        }
        if !changed { return }
        var set = component.weightSet
        var idx = set.startIndex
        var k = 0
        while idx != set.endIndex && k < weightTable.count {
            let entries = weightTable[k]
            if !entries.isEmpty {
                var data = set[idx]
                var values = data.weights
                let base = values.startIndex
                for e in entries where e.weightIndex < values.count {
                    let v = weights[e.name] ?? 0
                    values[base + e.weightIndex] = v
                    lastWeights[e.flatIndex] = v
                }
                data.weights = values
                set[idx] = data
            }
            idx = set.index(after: idx)
            k += 1
        }
        component.weightSet = set
        entity.components.set(component)
    }

    var summary: String {
        return "\(label) : pose=\(hasPose ? "\(jointMap.count) joints, \(missingJoints.count) manquants" : "non"), "
            + "poids=\(hasWeights ? "\(lastWeights.count)" : "non")"
    }
}
