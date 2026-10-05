import Foundation

/// Squelette résolu : noms, parents, poses de repos, index par nom et cinématique directe (FK) en espace modèle.
///
/// « Espace modèle » = repère local de l'entité poney dans RealityKit (Y haut, −Z avant), en unités du rig
/// (mètres pour le gabarit de 1,30 m ; l'échelle de l'entité s'applique par-dessus).
public struct PonySkeleton: Sendable {
    public let names: [String]
    public let parents: [Int]
    public let restLocal: [Transform]
    /// Repères de liaison en espace modèle (décodés de `bindModel`, sinon FK de la pose de repos).
    public let bindModel: [Transform]
    public let indexByName: [String: Int]
    public let children: [[Int]]
    /// Ordre d'évaluation garantissant parent avant enfant (identité si le manifeste est déjà ordonné).
    public let evaluationOrder: [Int]

    public var count: Int {
        return names.count
    }

    public init(names: [String], parents: [Int], restLocal: [Transform], bindModel: [Transform]? = nil) {
        let n = min(names.count, min(parents.count, restLocal.count))
        let ns = Array(names.prefix(n))
        var ps = Array(parents.prefix(n))
        for i in 0..<n where ps[i] < -1 || ps[i] >= n || ps[i] == i {
            ps[i] = -1
        }
        self.names = ns
        self.parents = ps
        self.restLocal = Array(restLocal.prefix(n))
        var index: [String: Int] = [:]
        for (i, name) in ns.enumerated() where index[name] == nil {
            index[name] = i
        }
        indexByName = index
        var ch = [[Int]](repeating: [], count: n)
        for i in 0..<n where ps[i] >= 0 {
            ch[ps[i]].append(i)
        }
        children = ch
        evaluationOrder = PonySkeleton.topologicalOrder(parents: ps)
        if let b = bindModel, b.count == n {
            self.bindModel = b
        } else {
            var model = [Transform](repeating: .identity, count: n)
            PonySkeleton.forwardKinematics(parents: ps, order: evaluationOrder,
                                           local: Array(restLocal.prefix(n)), into: &model)
            self.bindModel = model
        }
    }

    public init(manifest: PonyRigManifest) {
        let names = manifest.joints.map { $0.name }
        let parents = manifest.joints.map { $0.parent }
        let rest = manifest.joints.map { $0.rest }
        var binds: [Transform]? = nil
        if !manifest.joints.isEmpty && manifest.joints.allSatisfy({ $0.bindModel.count == 16 }) {
            binds = manifest.joints.map { Transform(columnMajor: $0.bindModel) }
        }
        self.init(names: names, parents: parents, restLocal: rest, bindModel: binds)
    }

    public func index(of name: String) -> Int? {
        return indexByName[name]
    }

    /// Cinématique directe sans allocation : `model[i] = model[parent] · local[i]`.
    public func computeModel(local: [Transform], into model: inout [Transform]) {
        PonySkeleton.forwardKinematics(parents: parents, order: evaluationOrder, local: local, into: &model)
    }

    /// Cinématique directe (alloue le tableau résultat ; pratique hors boucle de jeu).
    public func modelTransforms(local: [Transform]) -> [Transform] {
        var model = [Transform](repeating: .identity, count: count)
        computeModel(local: local, into: &model)
        return model
    }

    /// Transformation modèle du parent de `joint` (identité pour la racine).
    public func parentModel(of joint: Int, model: [Transform]) -> Transform {
        let p = parents[joint]
        return p >= 0 ? model[p] : .identity
    }

    /// Joint et tous ses descendants (ordre parent avant enfant).
    public func subtree(of joint: Int) -> [Int] {
        var out: [Int] = []
        var stack: [Int] = [joint]
        while let j = stack.popLast() {
            out.append(j)
            for c in children[j].reversed() {
                stack.append(c)
            }
        }
        return out
    }

    /// Vrai si `ancestor` est un ancêtre strict de `joint`.
    public func isAncestor(_ ancestor: Int, of joint: Int) -> Bool {
        var p = parents[joint]
        var guardCount = 0
        while p >= 0 && guardCount < count {
            if p == ancestor { return true }
            p = parents[p]
            guardCount += 1
        }
        return false
    }

    // MARK: Implémentation

    static func forwardKinematics(parents: [Int], order: [Int], local: [Transform], into model: inout [Transform]) {
        let n = min(parents.count, local.count)
        if model.count != n {
            model = [Transform](repeating: .identity, count: n)
        }
        for i in order where i < n {
            let p = parents[i]
            if p >= 0 {
                model[i] = model[p] * local[i]
            } else {
                model[i] = local[i]
            }
        }
    }

    static func topologicalOrder(parents: [Int]) -> [Int] {
        let n = parents.count
        var ordered = true
        for i in 0..<n where parents[i] >= i {
            ordered = false
            break
        }
        if ordered { return Array(0..<n) }
        var order: [Int] = []
        order.reserveCapacity(n)
        var placed = [Bool](repeating: false, count: n)
        var progress = true
        while order.count < n && progress {
            progress = false
            for i in 0..<n where !placed[i] {
                let p = parents[i]
                if p < 0 || placed[p] {
                    placed[i] = true
                    order.append(i)
                    progress = true
                }
            }
        }
        // Cycle éventuel (manifeste corrompu) : on ajoute le reste tel quel.
        for i in 0..<n where !placed[i] {
            order.append(i)
        }
        return order
    }
}
