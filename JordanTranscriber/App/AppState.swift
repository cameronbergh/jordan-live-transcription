import Foundation
import Combine

@MainActor
final class AppState: ObservableObject {
    @Published var transcriptText: String = ""
    @Published var isBlackoutActive: Bool = false
    @Published var transcriptionState: TranscriptionState = .notStarted
    @Published var settings: AppSettings = AppSettings()

    private let transcriptionService: TranscriptionServiceProtocol
    private var cancellables = Set<AnyCancellable>()

    init(transcriptionService: TranscriptionServiceProtocol = TranscriptionService()) {
        self.transcriptionService = transcriptionService
        setupBindings()
    }

    private func setupBindings() {
        transcriptionService.transcriptPublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] text in
                self?.transcriptText = text
            }
            .store(in: &cancellables)

        transcriptionService.statePublisher
            .receive(on: DispatchQueue.main)
            .sink { [weak self] state in
                self?.transcriptionState = state
            }
            .store(in: &cancellables)
    }

    func startTranscription() {
        Task {
            await transcriptionService.start()
        }
    }

    func stopTranscription() {
        Task {
            await transcriptionService.stop()
        }
    }

    func toggleBlackout() {
        isBlackoutActive.toggle()
    }

    func appendTranscript(_ text: String) {
        if !transcriptText.isEmpty {
            transcriptText += " "
        }
        transcriptText += text
    }
}

enum TranscriptionState: Equatable {
    case notStarted
    case starting
    case listening
    case paused
    case error(String)

    var statusText: String {
        switch self {
        case .notStarted: return "Not Started"
        case .starting: return "Starting..."
        case .listening: return "Listening"
        case .paused: return "Paused"
        case .error(let msg): return "Error: \(msg)"
        }
    }
}
