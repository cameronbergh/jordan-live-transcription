import SwiftUI
import CoreMotion

struct ShakeDetector: ViewModifier {
    let onShake: () -> Void

    private let motionManager = CMMotionManager()
    private let threshold: Double = 2.5

    func body(content: Content) -> some View {
        content
            .onAppear {
                startMonitoring()
            }
            .onDisappear {
                stopMonitoring()
            }
    }

    private func startMonitoring() {
        guard motionManager.isAccelerometerAvailable else { return }
        motionManager.accelerometerUpdateInterval = 0.1
        motionManager.startAccelerometerUpdates(to: .main) { data, _ in
            guard let data = data else { return }
            let totalAcceleration = sqrt(
                pow(data.acceleration.x, 2) +
                pow(data.acceleration.y, 2) +
                pow(data.acceleration.z, 2)
            )
            if totalAcceleration > threshold {
                onShake()
            }
        }
    }

    private func stopMonitoring() {
        motionManager.stopAccelerometerUpdates()
    }
}

extension View {
    func onShake(_ action: @escaping () -> Void) -> some View {
        modifier(ShakeDetector(onShake: action))
    }
}
