import SwiftUI

struct TranscriptView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                StatusBadge(state: appState.transcriptionState)
                Spacer()
                NavigationLink(destination: SettingsView().environmentObject(appState)) {
                    Image(systemName: "gearshape")
                        .font(.title2)
                        .foregroundColor(.secondary)
                }
            }
            .padding(.horizontal)
            .padding(.top, 8)

            ScrollView {
                Text(appState.transcriptText.isEmpty ? "Waiting for speech..." : appState.transcriptText)
                    .font(.system(size: appState.settings.preferredFontSize.pointSize))
                    .foregroundColor(appState.transcriptText.isEmpty ? .secondary : .primary)
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .id(appState.transcriptText)
            }
            .padding(.horizontal, 8)
        }
        .background(Color(.systemBackground))
    }
}

struct StatusBadge: View {
    let state: TranscriptionState

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
            Text(state.statusText)
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(12)
    }

    private var statusColor: Color {
        switch state {
        case .listening: return .green
        case .starting: return .yellow
        case .error: return .red
        default: return .gray
        }
    }
}
