import Foundation

/// Piste d'un joint : translation, rotation, échelle. Tableau vide = canal non animé (on garde la pose
/// de la couche inférieure ou de repos) ; 1 élément = constant ; `frameCount` éléments = une valeur par image.
public struct JointTrack: Sendable, Equatable {
    public var jointIndex: Int
    public var translations: [SIMD3<Float>]
    public var rotations: [Quat]
    public var scales: [SIMD3<Float>]

    public init(jointIndex: Int, translations: [SIMD3<Float>] = [], rotations: [Quat] = [],
                scales: [SIMD3<Float>] = []) {
        self.jointIndex = jointIndex
        self.translations = translations
        self.rotations = rotations
        self.scales = scales
    }
}

/// Piste de poids de blend shape (une valeur par image).
public struct WeightTrack: Sendable, Equatable {
    public var name: String
    public var values: [Float]

    public init(name: String, values: [Float]) {
        self.name = name
        self.values = values
    }
}

/// Clip d'animation échantillonnable (données de `PonyClips.bin` + métadonnées de `PonyRig.json`).
///
/// Convention temporelle [I] : `duration` fait foi.
/// - Clip non bouclé : l'image 0 est à t = 0 et l'image N−1 à t = `duration`.
/// - Boucle **fermée** (dernière image = première, détecté automatiquement) : même chose, t = `duration` ≡ t = 0.
/// - Boucle **ouverte** : l'image N−1 est suivie de l'image 0 ; la période vaut `duration` (= N/fps par défaut).
public struct AnimationClip: Sendable {
    public var name: String
    public var fps: Float
    public var frameCount: Int
    public var duration: Double
    public var loop: Bool
    public var isClosedLoop: Bool
    public var tracks: [JointTrack]
    public var weightTracks: [WeightTrack]
    /// Vitesse de référence (m/s, espace poney, avant = −Z).
    public var rootVelocity: SIMD3<Float>
    /// Lacet de référence (rad/s, positif = vers la gauche).
    public var rootYawRate: Float
    /// Indices des joints du masque (`nil` = corps entier).
    public var maskJoints: [Int]?
    /// Évènements triés par temps.
    public var events: [PonyRigManifest.ClipEvent]
    /// Phase de foulée au temps 0 (0 = poser du postérieur gauche).
    public var phaseOffset: Float
    /// Vrai si le clip vient réellement de données (faux pour un clip de repli vide).
    public var hasData: Bool
    /// `trackIndexByJoint[j]` = indice de piste du joint j, ou −1.
    public private(set) var trackIndexByJoint: [Int]

    public init(name: String, fps: Float, frameCount: Int, duration: Double? = nil, loop: Bool,
                tracks: [JointTrack], weightTracks: [WeightTrack] = [], jointCount: Int,
                rootVelocity: SIMD3<Float> = SIMD3<Float>(0, 0, 0), rootYawRate: Float = 0,
                maskJoints: [Int]? = nil, events: [PonyRigManifest.ClipEvent] = [], phaseOffset: Float = 0) {
        self.name = name
        self.fps = fps > 0 ? fps : 30
        self.frameCount = max(1, frameCount)
        self.loop = loop
        self.tracks = tracks
        self.weightTracks = weightTracks
        self.rootVelocity = rootVelocity
        self.rootYawRate = rootYawRate
        self.maskJoints = maskJoints
        self.events = events.sorted { $0.time < $1.time }
        self.phaseOffset = phaseOffset
        self.hasData = true
        var map = [Int](repeating: -1, count: max(0, jointCount))
        for (i, t) in tracks.enumerated() where t.jointIndex >= 0 && t.jointIndex < map.count {
            map[t.jointIndex] = i
        }
        trackIndexByJoint = map
        let closed = loop && AnimationClip.detectClosedLoop(tracks: tracks, weightTracks: weightTracks,
                                                            frameCount: max(1, frameCount))
        isClosedLoop = closed
        let n = Double(max(1, frameCount))
        let f = Double(self.fps)
        if let d = duration, d > 0, d.isFinite {
            self.duration = d
        } else if loop && !closed {
            self.duration = n / f
        } else {
            self.duration = max(n - 1, 1) / f
        }
    }

    // MARK: Temps → images

    /// Position dans les images : (image i0, image i1, fraction entre les deux).
    public func framePosition(at time: Double) -> (i0: Int, i1: Int, alpha: Float) {
        let n = frameCount
        if n <= 1 || duration <= 0 || !time.isFinite { return (0, 0, 0) }
        if loop {
            let u = PonyMath.fract(time / duration)
            if isClosedLoop {
                let f = u * Double(n - 1)
                let i0 = min(Int(f), n - 2)
                return (i0, i0 + 1, Float(f - Double(i0)))
            } else {
                let f = u * Double(n)
                let i0 = min(Int(f), n - 1)
                let i1 = (i0 + 1) % n
                return (i0, i1, Float(f - Double(i0)))
            }
        } else {
            let u = min(max(time / duration, 0), 1)
            let f = u * Double(n - 1)
            let i0 = min(Int(f), n - 2)
            return (i0, i0 + 1, Float(f - Double(i0)))
        }
    }

    /// Temps local effectivement échantillonné (bouclé ou borné) dans [0, duration].
    public func normalizedTime(_ time: Double) -> Double {
        if duration <= 0 { return 0 }
        if loop { return PonyMath.fract(time / duration) * duration }
        return min(max(time, 0), duration)
    }

    // MARK: Échantillonnage

    /// Écrit dans `pose` les canaux animés par le clip au temps `time` ; les autres canaux sont conservés
    /// (pré-remplir `pose` avec la pose de repos ou la couche inférieure). N'alloue pas.
    public func sample(at time: Double, into pose: inout [Transform]) {
        let fp = framePosition(at: time)
        sample(i0: fp.i0, i1: fp.i1, alpha: fp.alpha, into: &pose)
    }

    func sample(i0: Int, i1: Int, alpha: Float, into pose: inout [Transform]) {
        let count = pose.count
        for track in tracks {
            let j = track.jointIndex
            if j < 0 || j >= count { continue }
            if !track.translations.isEmpty {
                pose[j].translation = AnimationClip.interpolateVec(track.translations, i0, i1, alpha)
            }
            if !track.rotations.isEmpty {
                pose[j].rotation = AnimationClip.interpolateQuat(track.rotations, i0, i1, alpha)
            }
            if !track.scales.isEmpty {
                pose[j].scale = AnimationClip.interpolateVec(track.scales, i0, i1, alpha)
            }
        }
    }

    /// Valeur d'une piste de poids au temps `time` (0 si l'indice est invalide).
    public func weightValue(track index: Int, at time: Double) -> Float {
        if index < 0 || index >= weightTracks.count { return 0 }
        let values = weightTracks[index].values
        if values.isEmpty { return 0 }
        let fp = framePosition(at: time)
        return AnimationClip.interpolateScalar(values, fp.i0, fp.i1, fp.alpha)
    }

    /// Indice de la piste de poids nommée `name`.
    public func weightTrackIndex(named name: String) -> Int? {
        return weightTracks.firstIndex(where: { $0.name == name })
    }

    /// Piste du joint `joint`, si le clip l'anime.
    public func track(forJoint joint: Int) -> JointTrack? {
        if joint < 0 || joint >= trackIndexByJoint.count { return nil }
        let i = trackIndexByJoint[joint]
        return i >= 0 ? tracks[i] : nil
    }

    // MARK: Évènements

    /// Évènements dont le temps est franchi en passant de `from` à `to` (temps non bornés du lecteur ;
    /// gère le rebouclage). Intervalle (from, to]. Appelle `body` pour chacun, sans allocation.
    public func forEachEvent(from: Double, to: Double, _ body: (PonyRigManifest.ClipEvent) -> Void) {
        if events.isEmpty || to <= from || duration <= 0 { return }
        if !loop {
            for e in events {
                let t = Double(e.time)
                if t > from && t <= to { body(e) }
            }
            return
        }
        // Boucle : on parcourt les cycles touchés (au plus quelques-uns par frame).
        let startCycle = (from / duration).rounded(.down)
        let endCycle = (to / duration).rounded(.down)
        if endCycle - startCycle > 4 { return }       // saut temporel anormal : on ignore
        var cycle = startCycle
        while cycle <= endCycle {
            let base = cycle * duration
            for e in events {
                let t = base + Double(e.time)
                if t > from && t <= to { body(e) }
            }
            cycle += 1
        }
    }

    // MARK: Interpolation

    static func interpolateVec(_ values: [SIMD3<Float>], _ i0: Int, _ i1: Int, _ alpha: Float) -> SIMD3<Float> {
        let n = values.count
        if n == 1 { return values[0] }
        let a = values[min(i0, n - 1)]
        let b = values[min(i1, n - 1)]
        return a + (b - a) * alpha
    }

    static func interpolateQuat(_ values: [Quat], _ i0: Int, _ i1: Int, _ alpha: Float) -> Quat {
        let n = values.count
        if n == 1 { return values[0] }
        let a = values[min(i0, n - 1)]
        let b = values[min(i1, n - 1)]
        if alpha <= 0 { return a }
        if alpha >= 1 { return b }
        return Quat.slerp(a, b, alpha)
    }

    static func interpolateScalar(_ values: [Float], _ i0: Int, _ i1: Int, _ alpha: Float) -> Float {
        let n = values.count
        if n == 1 { return values[0] }
        let a = values[min(i0, n - 1)]
        let b = values[min(i1, n - 1)]
        return a + (b - a) * alpha
    }

    /// Boucle fermée si, pour tous les canaux animés image par image, la dernière image ≈ la première.
    static func detectClosedLoop(tracks: [JointTrack], weightTracks: [WeightTrack], frameCount: Int) -> Bool {
        if frameCount < 3 { return false }
        var sawAnimated = false
        let tol: Float = 1e-4
        for t in tracks {
            if t.translations.count == frameCount {
                sawAnimated = true
                if PonyMath.length(t.translations[0] - t.translations[frameCount - 1]) > tol { return false }
            }
            if t.rotations.count == frameCount {
                sawAnimated = true
                if !t.rotations[0].isApproximatelyEqual(to: t.rotations[frameCount - 1], tolerance: tol) {
                    return false
                }
            }
            if t.scales.count == frameCount {
                sawAnimated = true
                if PonyMath.length(t.scales[0] - t.scales[frameCount - 1]) > tol { return false }
            }
        }
        for w in weightTracks where w.values.count == frameCount {
            sawAnimated = true
            if abs(w.values[0] - w.values[frameCount - 1]) > tol { return false }
        }
        return sawAnimated
    }

    /// Clip vide (aucune piste) servant de repli quand un clip attendu manque : il laisse la pose intacte.
    public static func placeholder(name: String, jointCount: Int) -> AnimationClip {
        let d = PonyRigDefaults.clipDefaults[name]
        var clip = AnimationClip(name: name, fps: 30, frameCount: 1, duration: Double(d?.duration ?? 1),
                                 loop: d?.loop ?? false, tracks: [], jointCount: jointCount,
                                 rootVelocity: SIMD3<Float>(0, 0, -(d?.forwardSpeed ?? 0)),
                                 rootYawRate: d?.yawRate ?? 0)
        clip.hasData = false
        return clip
    }
}
