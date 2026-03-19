import SwiftUI

@main
struct JordanTranscriberMacApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            MainView(appState: appState)
        }
        .defaultSize(width: 640, height: 480)
    }
}
