import SwiftUI

struct MainView: View {
    @ObservedObject var appState: AppState
    @State private var showSettings = false

    var body: some View {
        VStack(spacing: 0) {
            TranscriptArea(appState: appState)

            Divider()

            StatusBar(appState: appState)
        }
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Button {
                    if appState.isActive {
                        appState.stop()
                    } else {
                        appState.start()
                    }
                } label: {
                    Label(
                        appState.isActive ? "Stop" : "Start",
                        systemImage: appState.isActive ? "stop.circle.fill" : "mic.circle.fill"
                    )
                }
                .keyboardShortcut(.return, modifiers: .command)
                .help(appState.isActive ? "Stop transcription (⌘↩)" : "Start transcription (⌘↩)")

                Button {
                    appState.clearTranscript()
                } label: {
                    Label("Clear", systemImage: "trash")
                }
                .disabled(appState.transcriptSegments.isEmpty)
                .help("Clear transcript")

                Button {
                    showSettings.toggle()
                } label: {
                    Label("Settings", systemImage: "gearshape")
                }
                .popover(isPresented: $showSettings) {
                    SettingsPopover(appState: appState)
                }
                .help("Server settings")
            }
        }
        .frame(minWidth: 480, minHeight: 360)
    }
}

// MARK: - Transcript area with auto-scroll

struct TranscriptArea: View {
    @ObservedObject var appState: AppState

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2) {
                    if appState.transcriptSegments.isEmpty {
                        Text("Waiting for speech...")
                            .foregroundStyle(.secondary)
                            .font(.system(size: appState.fontSize))
                            .padding()
                    } else {
                        // Render segments as flowing inline text
                        TranscriptTextView(
                            segments: appState.transcriptSegments,
                            fontSize: appState.fontSize
                        )
                        .padding()

                        // Invisible anchor at the bottom
                        Color.clear
                            .frame(height: 1)
                            .id("bottom")
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .onChange(of: appState.transcriptSegments.count) { _ in
                withAnimation(.easeOut(duration: 0.15)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
            .onChange(of: appState.transcriptSegments.last?.text ?? "") { _ in
                withAnimation(.easeOut(duration: 0.15)) {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
        }
        .background(Color(nsColor: .textBackgroundColor))
    }
}

// MARK: - Flowing text rendering

struct TranscriptTextView: View {
    let segments: [TranscriptSegment]
    let fontSize: CGFloat

    var body: some View {
        let combined = segments.enumerated().reduce(Text("")) { result, pair in
            let (idx, segment) = pair
            let separator = idx > 0 ? Text(" ") : Text("")
            let styledText = Text(segment.text)
                .foregroundColor(segment.isFinal ? .primary : .secondary)
            return result + separator + styledText
        }

        combined
            .font(.system(size: fontSize))
            .textSelection(.enabled)
            .lineSpacing(4)
    }
}

// MARK: - Status bar

struct StatusBar: View {
    @ObservedObject var appState: AppState

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)

            Text(appState.connectionState.label)
                .font(.caption)
                .foregroundStyle(.secondary)

            if !appState.activeModel.isEmpty {
                Text("·")
                    .foregroundStyle(.quaternary)
                Text(modelDisplayName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if appState.connectedClients > 0 {
                Text("·")
                    .foregroundStyle(.quaternary)
                Text("\(appState.connectedClients) client\(appState.connectedClients == 1 ? "" : "s")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if !appState.transcriptSegments.isEmpty {
                Text("\(appState.transcriptSegments.count) segments")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.bar)
    }

    private var modelDisplayName: String {
        switch appState.activeModel {
        case "parakeet": return "Parakeet"
        case "whisperlive": return "WhisperLive"
        default: return appState.activeModel
        }
    }

    private var statusColor: Color {
        switch appState.connectionState {
        case .listening: return .green
        case .connecting, .connected: return .yellow
        case .error: return .red
        case .disconnected: return .gray
        }
    }
}

// MARK: - Settings popover

struct SettingsPopover: View {
    @ObservedObject var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Server Settings")
                .font(.headline)

            LabeledContent("Host") {
                TextField("hostname", text: $appState.serverHost)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 200)
            }

            LabeledContent("Port") {
                TextField("port", value: $appState.serverPort, format: .number)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 80)
            }

            Divider()

            Text("Engine")
                .font(.headline)

            Picker("Model", selection: $appState.selectedEngine) {
                ForEach(AppState.availableEngines, id: \.id) { engine in
                    Text(engine.label).tag(engine.id)
                }
            }
            .pickerStyle(.radioGroup)
            .disabled(appState.isActive)

            Divider()

            Text("Display")
                .font(.headline)

            LabeledContent("Font Size") {
                Slider(value: $appState.fontSize, in: 12...48, step: 2) {
                    Text("\(Int(appState.fontSize))pt")
                }
                .frame(width: 160)
            }

            Text("\(Int(appState.fontSize)) pt")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding()
        .frame(width: 300)
    }
}
