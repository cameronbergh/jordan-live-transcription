import Foundation
import Combine

struct TranscriptSegment: Identifiable {
    let id: String
    var text: String
    let isFinal: Bool
}

@MainActor
final class AppState: ObservableObject {
    @Published var transcriptSegments: [TranscriptSegment] = []
    @Published var connectionState: ConnectionState = .disconnected
    @Published var serverHost: String = "cameron-ms-7b17"
    @Published var serverPort: Int = 8765
    @Published var selectedEngine: String = "parakeet"
    @Published var fontSize: CGFloat = 18
    @Published var connectedClients: Int = 0
    @Published var activeModel: String = ""

    static let availableEngines: [(id: String, label: String)] = [
        ("parakeet", "Parakeet (Local GPU)"),
        ("whisperlive", "WhisperLive (large-v3-turbo)"),
    ]

    private let audioService = AudioCaptureService()
    private let wsService = WebSocketService()
    private var cancellables = Set<AnyCancellable>()

    var isActive: Bool {
        connectionState == .listening || connectionState == .connected || connectionState == .connecting
    }

    var fullTranscript: String {
        transcriptSegments.map(\.text).joined(separator: " ")
    }

    init() {
        wsService.stateSubject
            .receive(on: DispatchQueue.main)
            .sink { [weak self] state in
                self?.connectionState = state
            }
            .store(in: &cancellables)

        wsService.transcriptSubject
            .receive(on: DispatchQueue.main)
            .sink { [weak self] event in
                self?.handleTranscriptEvent(event)
            }
            .store(in: &cancellables)

        wsService.connectedClientsSubject
            .receive(on: DispatchQueue.main)
            .sink { [weak self] count in
                self?.connectedClients = count
            }
            .store(in: &cancellables)

        wsService.activeModelSubject
            .receive(on: DispatchQueue.main)
            .sink { [weak self] model in
                self?.activeModel = model
            }
            .store(in: &cancellables)

        audioService.onChunk = { [weak self] chunk in
            self?.wsService.sendAudioChunk(chunk)
        }
    }

    func start() {
        transcriptSegments.removeAll()
        wsService.connect(host: serverHost, port: serverPort, engine: selectedEngine)

        // Start mic capture once we're connected
        wsService.stateSubject
            .first(where: { $0 == .listening })
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in
                self?.startAudio()
            }
            .store(in: &cancellables)
    }

    func stop() {
        audioService.stop()
        wsService.disconnect()
        connectedClients = 0
        activeModel = ""
    }

    func clearTranscript() {
        transcriptSegments.removeAll()
    }

    private func startAudio() {
        do {
            try audioService.start()
        } catch {
            connectionState = .error(error.localizedDescription)
        }
    }

    private func handleTranscriptEvent(_ event: TranscriptEvent) {
        if event.isFinal {
            // Replace any existing partial with this segment ID, or append
            if let idx = transcriptSegments.firstIndex(where: { $0.id == event.segmentId }) {
                transcriptSegments[idx] = TranscriptSegment(id: event.segmentId, text: event.text, isFinal: true)
            } else {
                transcriptSegments.append(TranscriptSegment(id: event.segmentId, text: event.text, isFinal: true))
            }
        } else {
            // Update or append partial
            if let idx = transcriptSegments.firstIndex(where: { $0.id == event.segmentId }) {
                transcriptSegments[idx] = TranscriptSegment(id: event.segmentId, text: event.text, isFinal: false)
            } else {
                transcriptSegments.append(TranscriptSegment(id: event.segmentId, text: event.text, isFinal: false))
            }
        }
    }
}
