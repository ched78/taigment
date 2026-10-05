// Exemple d'application de démonstration PonyKit (iOS 26 / macOS 26).
//
// Ce fichier n'appartient à aucune cible du package : le copier dans une cible d'application SwiftUI
// (par ex. un nouveau projet Xcode « App ») qui dépend du package local `ValombrePony/PonyKit`
// (produit `PonyKit`), puis supprimer le `@main` existant du gabarit Xcode.
// Mise en place détaillée : Docs/INTEGRATION.md.

import PonyCore
import PonyKit
import RealityKit
import SwiftUI

@main
struct PonyDemoApp: App {
    init() {
        // Enregistre PonySystem / PonyComponent une fois au démarrage (idempotent : les vues le font aussi).
        PonyKit.registerSystems()
        PonyLog.mirrorToStandardOutput = true
    }

    var body: some SwiftUI.Scene {   // qualifié : RealityKit définit aussi `Scene`
        WindowGroup {
            PonyDemoRootView()
        }
        #if os(macOS)
        .defaultSize(width: 1280, height: 800)
        #endif
    }
}

/// Écran d'accueil : écurie (personnalisation) et terrain de jeu partagent la même configuration.
struct PonyDemoRootView: View {
    @State private var configuration = PonyConfiguration.default
    @State private var mode: Mode = .stable

    enum Mode: String, CaseIterable, Identifiable {
        case stable = "Écurie"
        case playground = "Paddock"
        case custom = "Intégration manuelle"
        var id: String { rawValue }
    }

    var body: some View {
        VStack(spacing: 0) {
            Picker("Mode", selection: $mode) {
                ForEach(Mode.allCases) { m in
                    Text(m.rawValue).tag(m)
                }
            }
            .pickerStyle(.segmented)
            .padding(8)

            switch mode {
            case .stable:
                // `onSave` : le joueur valide sa personnalisation.
                PonyStableView(configuration: configuration) { saved in
                    configuration = saved
                    mode = .playground
                }
                .id("stable")
            case .playground:
                PonyPlaygroundView(configuration: configuration)
                    .id("playground-\(configuration.name)")
            case .custom:
                ManualIntegrationView(configuration: configuration)
            }
        }
    }
}

/// Intégration « à la main » : votre propre `RealityView`, votre décor, votre caméra et vos entrées.
struct ManualIntegrationView: View {
    @State private var pony: PonyController
    @State private var camera = PonyCameraRig()
    @State private var input = PonyInputState()

    init(configuration: PonyConfiguration) {
        _pony = State(initialValue: PonyController(configuration: configuration, movementMode: .kinematic))
    }

    var body: some View {
        ZStack(alignment: .bottom) {
            RealityView { content in
                content.camera = .virtual
                let scene = await PonySceneBuilder.makePaddock()
                content.add(scene.root)
                pony.imageBasedLight = scene.imageBasedLight
                content.add(pony.root)
                content.add(camera.entity)
                camera.follow(pony)
                pony.connect(input)
                // Le poney tourne la tête vers ce point (coordonnées monde).
                pony.lookTarget = SIMD3<Float>(3, 1.2, -4)
                pony.onEvent = { event in
                    if event.name == "landing" { print("[PonyDemo] réception du saut à \(event.time) s") }
                }
            }
            .task {
                await pony.load()
                // Exemple de surcharge de joint : oreille gauche tournée (rotation locale, mélange 60 %).
                pony.setJointOverride("ear_l", rotation: simd_quatf(angle: 0.6, axis: SIMD3<Float>(0, 1, 0)),
                                      weight: 0.6)
            }

            HStack {
                Button("Avancer (3 s)") {
                    Task { @MainActor in
                        pony.input.move = SIMD2<Float>(0, 0.6)
                        try? await Task.sleep(nanoseconds: 3_000_000_000)
                        pony.input.move = SIMD2<Float>(0, 0)
                    }
                }
                Button("Sauter") { pony.jump() }
                Button("Hennir") { pony.perform(.neigh) }
                Button("Robe aléatoire") {
                    var c = pony.configuration
                    c.coat = (CoatPreset.all.randomElement() ?? CoatPreset.defaultPreset).configuration
                    let next = c   // copie immuable capturée par la tâche (propre en mode Swift 6)
                    Task { await pony.apply(next) }
                }
                Button("Diagnostic") {
                    print(pony.diagnosticReport())
                }
            }
            .buttonStyle(.borderedProminent)
            .padding()
        }
    }
}
