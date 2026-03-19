import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        ZStack {
            TranscriptView()
                .environmentObject(appState)

            if appState.isBlackoutActive {
                BlackoutOverlay()
                    .environmentObject(appState)
            }
        }
        .onShake {
            appState.toggleBlackout()
        }
    }
}
