import Foundation
import PonyCore
import RealityKit
import SwiftUI

/// Terrain de jeu : paddock, poney jouable, caméra 3e personne.
///
/// Commandes :
/// - iOS : joystick tactile (bas gauche), boutons « Sauter » et « Galop » (bas droite), glisser ailleurs pour
///   tourner la caméra, pincer pour zoomer ; clavier matériel comme sur macOS.
/// - macOS : ZQSD / WASD / flèches, Maj = galop de course, Espace = saut, B/H/C/T/G/L/R/E = actions ;
///   glisser pour tourner la caméra, pincer (trackpad) pour zoomer.
/// - Boutons d'actions : Brouter, Hennir, Se cabrer, Secouer la tête, Gratter, Se coucher / Se relever,
///   Se rouler, S'ébrouer. Indicateur d'allure en haut à gauche.
///
/// API vérifiées : `RealityView(make:update:)` pour `RealityViewCameraContent` (iOS 18 / macOS 15),
/// `content.camera = .virtual`, `content.environment = .skybox(_:)`, `content.add(_:)`,
/// `onKeyPress(phases:action:)` (iOS 17 / macOS 14), `focusable(_:)`, `focused(_:)`, `focusEffectDisabled(_:)`,
/// `MagnifyGesture` (iOS 17 / macOS 14 ; propriété `magnification` de sa valeur non trouvée dans la doc
/// consultable [I]).
public struct PonyPlaygroundView: View {
    @State private var controller: PonyController
    @State private var camera = PonyCameraRig()
    @State private var inputState = PonyInputState()
    @State private var lastDrag: CGSize = .zero
    @State private var lastMagnification: CGFloat = 1
    @State private var showsActions = true
    @FocusState private var focused: Bool

    /// - Parameters:
    ///   - controller: poney existant (sinon un nouveau est créé avec `configuration`).
    ///   - configuration: configuration du poney créé.
    public init(controller: PonyController? = nil, configuration: PonyConfiguration = .default) {
        _controller = State(initialValue: controller ?? PonyController(configuration: configuration))
    }

    public var body: some View {
        ZStack {
            RealityView { content in
                content.camera = .virtual
                let scene = await PonySceneBuilder.makePaddock()
                content.add(scene.root)
                if let env = scene.environment {
                    content.environment = .skybox(env)
                }
                controller.imageBasedLight = scene.imageBasedLight
                content.add(controller.root)
                content.add(camera.entity)
                camera.follow(controller)
                controller.connect(inputState)
            }
            .gesture(cameraDrag)
            .simultaneousGesture(cameraZoom)
            .ignoresSafeArea()

            overlay
        }
        .focusable()
        .focused($focused)
        .focusEffectDisabled()
        .onKeyPress(phases: .all) { press in
            inputState.handle(press)
        }
        .task {
            // Chargement hors de `make` : le paddock s'affiche pendant le chargement du poney.
            await controller.load()
        }
        .onAppear {
            focused = true
        }
        .onDisappear {
            inputState.releaseAll()
        }
        .onChange(of: focused) { _, isFocused in
            if !isFocused { inputState.releaseAll() }
        }
    }

    // MARK: Interface superposée

    private var overlay: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top) {
                PonyGaitIndicator(controller: controller)
                Spacer()
                PonyLoadBanner(controller: controller)
                Spacer()
                Button {
                    showsActions.toggle()
                } label: {
                    Image(systemName: showsActions ? "chevron.down.circle" : "ellipsis.circle")
                        .font(.title2)
                }
                .buttonStyle(.plain)
                .padding(8)
                .background(.ultraThinMaterial, in: Circle())
                .accessibilityLabel(showsActions ? "Masquer les actions" : "Afficher les actions")
            }
            .padding()
            Spacer()
            HStack(alignment: .bottom) {
                #if os(iOS)
                PonyJoystick(state: inputState)
                    .padding(.leading, 24)
                    .padding(.bottom, 24)
                #elseif os(macOS)
                keyboardHelp
                    .padding(.leading, 16)
                    .padding(.bottom, 16)
                #endif
                Spacer()
                VStack(alignment: .trailing, spacing: 10) {
                    if showsActions {
                        actionGrid
                    }
                    HStack(spacing: 10) {
                        #if os(iOS)
                        Toggle(isOn: Binding(get: { inputState.sprintLatched },
                                             set: { inputState.sprintLatched = $0 })) {
                            Label("Galop", systemImage: "hare.fill")
                        }
                        .toggleStyle(.button)
                        #endif
                        Button {
                            controller.jump()
                        } label: {
                            Label("Sauter", systemImage: "arrow.up.circle.fill")
                                .font(.headline)
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
                .padding(.trailing, 20)
                .padding(.bottom, 24)
            }
        }
    }

    private var lyingLabel: String {
        let a = controller.currentAction
        return (a == .lieDown || a == .roll) ? PonyAction.getUp.frenchName : PonyAction.lieDown.frenchName
    }

    private var actionGrid: some View {
        let columns = [GridItem(.fixed(150)), GridItem(.fixed(150))]
        return LazyVGrid(columns: columns, alignment: .trailing, spacing: 8) {
            actionButton(.graze)
            actionButton(.neigh)
            actionButton(.rear)
            actionButton(.headShake)
            actionButton(.paw)
            Button(lyingLabel) {
                controller.toggleLying()
            }
            .buttonStyle(.bordered)
            actionButton(.roll)
            actionButton(.bodyShake)
        }
        .padding(10)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 14))
    }

    private func actionButton(_ action: PonyAction) -> some View {
        Button(action.frenchName) {
            controller.perform(action)
        }
        .buttonStyle(.bordered)
    }

    #if os(macOS)
    private var keyboardHelp: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("ZQSD / WASD / flèches : se déplacer")
            Text("Maj : galop de course · Espace : sauter")
            Text("B brouter · H hennir · C cabrer · T tête · G gratter")
            Text("L coucher/relever · R rouler · E s'ébrouer")
        }
        .font(.caption)
        .padding(10)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
    #endif

    // MARK: Caméra

    private var cameraDrag: some Gesture {
        DragGesture(minimumDistance: 4)
            .onChanged { value in
                let dx = value.translation.width - lastDrag.width
                let dy = value.translation.height - lastDrag.height
                lastDrag = value.translation
                camera.rotate(yaw: Float(-dx) * 0.008, pitch: Float(dy) * 0.006)
            }
            .onEnded { _ in
                lastDrag = .zero
            }
    }

    private var cameraZoom: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                // [I] `MagnifyGesture.Value.magnification` (CGFloat, cumulé depuis le début du geste).
                let m = value.magnification
                if m > 0 {
                    camera.zoom(by: Float(lastMagnification / m))
                    lastMagnification = m
                }
            }
            .onEnded { _ in
                lastMagnification = 1
            }
    }
}
