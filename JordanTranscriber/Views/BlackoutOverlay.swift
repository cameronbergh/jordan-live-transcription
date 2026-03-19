import SwiftUI

struct BlackoutOverlay: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            VStack(spacing: 24) {
                Text("Privacy Blackout")
                    .font(.title2)
                    .foregroundColor(.white)

                Text("Shake again or tap to restore")
                    .font(.subheadline)
                    .foregroundColor(.gray)
            }
        }
        .onTapGesture {
            appState.toggleBlackout()
        }
        .onShake {
            appState.toggleBlackout()
        }
    }
}
