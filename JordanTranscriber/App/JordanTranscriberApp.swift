import SwiftUI

@main
struct JordanTranscriberApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .onAppear {
                    appState.startTranscription()
                }
        }
    }
}
