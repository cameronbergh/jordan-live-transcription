import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        List {
            Section(header: Text("Transcription")) {
                Toggle("Enable Logging", isOn: $appState.settings.isLoggingEnabled)
                    .onChange(of: appState.settings.isLoggingEnabled) { _, newValue in
                        if newValue {
                            LogManager.shared.enableLogging()
                        } else {
                            LogManager.shared.disableLogging()
                        }
                    }
            }

            Section(header: Text("Display")) {
                Picker("Text Size", selection: $appState.settings.preferredFontSize) {
                    ForEach(AppSettings.FontSizePreference.allCases, id: \.self) { size in
                        Text(size.rawValue).tag(size)
                    }
                }
            }

            Section(header: Text("Status")) {
                HStack {
                    Text("Transcription")
                    Spacer()
                    Text(appState.transcriptionState.statusText)
                        .foregroundColor(.secondary)
                }
            }

            Section(header: Text("About")) {
                HStack {
                    Text("Version")
                    Spacer()
                    Text("1.0.0")
                        .foregroundColor(.secondary)
                }
            }
        }
        .navigationTitle("Settings")
        .navigationBarTitleDisplayMode(.inline)
    }
}

final class LogManager {
    static let shared = LogManager()
    private init() {}

    func enableLogging() {}
    func disableLogging() {}
    func logTranscript(_ text: String) {}
}
