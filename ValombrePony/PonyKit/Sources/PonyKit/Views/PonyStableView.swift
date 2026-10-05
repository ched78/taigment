import Foundation
import PonyCore
import RealityKit
import SwiftUI

/// Onglets de l'écurie.
enum PonyStableTab: String, CaseIterable, Identifiable {
    case coat, hair, morphology, size, accessories, files

    var id: String { rawValue }

    var title: String {
        switch self {
        case .coat: return "Robe"
        case .hair: return "Crins"
        case .morphology: return "Morphologie"
        case .size: return "Taille"
        case .accessories: return "Accessoires"
        case .files: return "Sauvegardes"
        }
    }

    var symbol: String {
        switch self {
        case .coat: return "paintpalette"
        case .hair: return "scissors"
        case .morphology: return "slider.horizontal.3"
        case .size: return "ruler"
        case .accessories: return "bag"
        case .files: return "tray.and.arrow.down"
        }
    }
}

/// Écurie de personnalisation : aperçu 3D en orbite + panneau d'édition (Robe, Crins, Morphologie, Taille,
/// Accessoires, Sauvegardes) + tirage « aléatoire plausible ».
///
/// Flux : chaque modification du brouillon (`PonyConfiguration`) est appliquée en mode interactif (anti-rebond
/// 80 ms, robe 1024²) ; au relâcher d'un curseur ou après 0,6 s sans modification, la configuration est appliquée
/// en définitif (robe 2048²). `onSave` reçoit la configuration validée (bouton « Valider »).
public struct PonyStableView: View {
    @State private var controller: PonyController
    @State private var camera = PonyCameraRig()
    @State private var draft: PonyConfiguration
    @State private var tab: PonyStableTab = .coat
    @State private var isEditing = false
    @State private var finalizeTask: Task<Void, Never>?
    @State private var autoRotate = false
    @State private var looksAtCamera = true
    @State private var lastDrag: CGSize = .zero
    @State private var lastMagnification: CGFloat = 1
    @State private var statusMessage: String?

    private let onSave: ((PonyConfiguration) -> Void)?

    /// - Parameters:
    ///   - configuration: configuration de départ.
    ///   - controller: poney existant (sinon un nouveau est créé).
    ///   - onSave: appelé avec la configuration quand le joueur valide.
    public init(configuration: PonyConfiguration = .default, controller: PonyController? = nil,
                onSave: ((PonyConfiguration) -> Void)? = nil) {
        let c = controller ?? PonyController(configuration: configuration)
        _controller = State(initialValue: c)
        _draft = State(initialValue: configuration)
        self.onSave = onSave
    }

    private var rules: AccessoryRules {
        return controller.rules ?? AccessoryRules(parts: PonyPartCatalog.specParts)
    }

    public var body: some View {
        GeometryReader { geo in
            let wide = geo.size.width > geo.size.height * 1.1
            Group {
                if wide {
                    HStack(spacing: 0) {
                        preview
                        Divider()
                        editor
                            .frame(width: min(440, geo.size.width * 0.45))
                    }
                } else {
                    VStack(spacing: 0) {
                        preview
                            .frame(height: geo.size.height * 0.42)
                        Divider()
                        editor
                    }
                }
            }
        }
        .task {
            await controller.load()
            await controller.apply(draft)
        }
        .onChange(of: draft) { _, newValue in
            controller.scheduleApply(newValue, interactive: true)
            scheduleFinalize()
        }
    }

    // MARK: Aperçu 3D

    private var preview: some View {
        ZStack(alignment: .top) {
            RealityView { content in
                content.camera = .virtual
                let scene = await PonySceneBuilder.makeStable()
                content.add(scene.root)
                if let env = scene.environment {
                    content.environment = .skybox(env)
                }
                controller.imageBasedLight = scene.imageBasedLight
                content.add(controller.root)
                content.add(camera.entity)
                camera.orbitYaw = -2.1
                camera.orbitPitch = 0.12
                camera.orbit(around: SIMD3<Float>(0, 0.85 * draft.entityScale, 0), distance: 3.4)
                camera.lookingPony = looksAtCamera ? controller : nil
            }
            .gesture(
                DragGesture(minimumDistance: 2)
                    .onChanged { value in
                        let dx = value.translation.width - lastDrag.width
                        let dy = value.translation.height - lastDrag.height
                        lastDrag = value.translation
                        camera.rotate(yaw: Float(-dx) * 0.01, pitch: Float(dy) * 0.006)
                    }
                    .onEnded { _ in lastDrag = .zero }
            )
            .simultaneousGesture(
                MagnifyGesture()
                    .onChanged { value in
                        // [I] `MagnifyGesture.Value.magnification` (cumulé depuis le début du geste).
                        let m = value.magnification
                        if m > 0 {
                            camera.zoom(by: Float(lastMagnification / m))
                            lastMagnification = m
                        }
                    }
                    .onEnded { _ in lastMagnification = 1 }
            )

            HStack {
                PonyLoadBanner(controller: controller)
                Spacer()
                Toggle(isOn: $autoRotate) {
                    Image(systemName: "rotate.3d")
                }
                .toggleStyle(.button)
                .help("Rotation automatique")
                Toggle(isOn: $looksAtCamera) {
                    Image(systemName: "eye")
                }
                .toggleStyle(.button)
                .help("Le poney regarde la caméra")
            }
            .padding(10)
        }
        .onChange(of: autoRotate) { _, on in
            camera.autoRotateSpeed = on ? 0.35 : 0
        }
        .onChange(of: looksAtCamera) { _, on in
            camera.lookingPony = on ? controller : nil
        }
        .onChange(of: draft.withersHeight) { _, _ in
            camera.orbit(around: SIMD3<Float>(0, 0.85 * draft.entityScale, 0))
        }
    }

    // MARK: Panneau d'édition

    private var editor: some View {
        VStack(spacing: 0) {
            header
            tabBar
            Divider()
            Group {
                switch tab {
                case .coat:
                    PonyCoatEditor(draft: $draft, onEditingChanged: editingChanged)
                case .hair:
                    PonyHairEditor(draft: $draft, rules: rules, onEditingChanged: editingChanged,
                                   statusMessage: $statusMessage)
                case .morphology:
                    PonyMorphologyEditor(draft: $draft, onEditingChanged: editingChanged)
                case .size:
                    PonySizeEditor(draft: $draft, onEditingChanged: editingChanged)
                case .accessories:
                    PonyAccessoriesEditor(draft: $draft, rules: rules, statusMessage: $statusMessage)
                case .files:
                    PonyFilesEditor(draft: $draft, statusMessage: $statusMessage)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            if let message = statusMessage {
                Text(message)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(.thinMaterial)
            }
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            TextField("Nom du poney", text: $draft.name)
                .textFieldStyle(.roundedBorder)
                .font(.headline)
            Button {
                let rules = self.rules
                let name = draft.name
                draft = PonyRandomizer().plausible(rules: rules, name: name)
                statusMessage = "Tirage aléatoire plausible : \(PonyPartLabels.name(draft.hair.mane)), "
                    + "\(draft.accessories.count) accessoire(s), \(Int((draft.withersHeight * 100).rounded())) cm."
            } label: {
                Label("Aléatoire", systemImage: "dice")
            }
            .buttonStyle(.bordered)
            if let onSave = onSave {
                Button {
                    onSave(draft)
                } label: {
                    Label("Valider", systemImage: "checkmark")
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .padding(10)
    }

    private var tabBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(PonyStableTab.allCases) { t in
                    Button {
                        tab = t
                    } label: {
                        Label(t.title, systemImage: t.symbol)
                            .font(.subheadline)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(tab == t ? Color.accentColor.opacity(0.2) : Color.clear,
                                        in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
        }
    }

    // MARK: Application différée

    private func editingChanged(_ editing: Bool) {
        isEditing = editing
        if !editing {
            finalizeTask?.cancel()
            controller.scheduleApply(draft, interactive: false)
        }
    }

    /// Application définitive après 0,6 s sans modification (sélecteurs de couleur, boutons…).
    private func scheduleFinalize() {
        finalizeTask?.cancel()
        finalizeTask = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 600_000_000)
            if Task.isCancelled || isEditing { return }
            controller.scheduleApply(draft, interactive: false)
        }
    }
}
