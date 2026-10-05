import Foundation
import PonyCore
import SwiftUI

/// Joystick tactile : glisser depuis le centre ; la direction est transmise à `PonyInputState.joystick`
/// (x = tourner, y = avancer, haut = avant). API : `DragGesture(minimumDistance:coordinateSpace:)` (iOS 17).
struct PonyJoystick: View {
    let state: PonyInputState
    var diameter: CGFloat = 150
    @State private var knob: CGSize = .zero

    var body: some View {
        let radius = diameter / 2
        ZStack {
            Circle()
                .fill(.ultraThinMaterial)
                .overlay(Circle().stroke(Color.white.opacity(0.35), lineWidth: 1.5))
            Circle()
                .fill(Color.white.opacity(0.85))
                .frame(width: diameter * 0.38, height: diameter * 0.38)
                .shadow(radius: 3)
                .offset(knob)
        }
        .frame(width: diameter, height: diameter)
        .contentShape(Circle())
        .gesture(
            DragGesture(minimumDistance: 0, coordinateSpace: .local)
                .onChanged { value in
                    var dx = value.location.x - radius
                    var dy = value.location.y - radius
                    let len = (dx * dx + dy * dy).squareRoot()
                    let maxLen = radius * 0.8
                    if len > maxLen {
                        dx *= maxLen / len
                        dy *= maxLen / len
                    }
                    knob = CGSize(width: dx, height: dy)
                    state.joystick = SIMD2<Float>(Float(dx / maxLen), Float(-dy / maxLen))
                }
                .onEnded { _ in
                    knob = .zero
                    state.joystick = SIMD2<Float>(0, 0)
                }
        )
        .accessibilityLabel("Joystick de déplacement")
    }
}

/// Indicateur d'allure : nom, vitesse, activité en cours, saut.
struct PonyGaitIndicator: View {
    let controller: PonyController

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: controller.gait.symbolName)
                .font(.title3)
            VStack(alignment: .leading, spacing: 2) {
                Text(controller.isAirborne ? "Saut" : controller.gait.frenchName)
                    .font(.headline)
                HStack(spacing: 6) {
                    Text(String(format: "%.1f m/s", controller.displaySpeed))
                        .monospacedDigit()
                    if let a = controller.currentAction {
                        Text("· \(a.activityName)")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }
}

/// Bandeau d'état du chargement (progression, replis, erreurs) ; rien n'est affiché quand tout va bien.
struct PonyLoadBanner: View {
    let controller: PonyController

    private var status: (text: String, icon: String?, busy: Bool, isError: Bool)? {
        switch controller.loadState {
        case .idle, .loading:
            return ("Chargement du poney…", nil, true, false)
        case .failed(let message):
            return (message, "exclamationmark.triangle", false, true)
        case .ready:
            if controller.usesPlaceholder {
                return ("Modèle 3D indisponible : substitut affiché", "cube.transparent", false, false)
            }
            if controller.isComposingCoat {
                return ("Robe…", nil, true, false)
            }
            return nil
        }
    }

    var body: some View {
        if let s = status {
            HStack(spacing: 8) {
                if s.busy {
                    ProgressView()
                }
                if let icon = s.icon {
                    Image(systemName: icon)
                }
                Text(s.text)
            }
            .font(.footnote)
            .foregroundStyle(s.isError ? Color.red : Color.primary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(.ultraThinMaterial, in: Capsule())
        }
    }
}
