import Foundation
import Combine

protocol TranscriptionServiceProtocol: AnyObject {
    var transcriptPublisher: AnyPublisher<String, Never> { get }
    var statePublisher: AnyPublisher<TranscriptionState, Never> { get }
    func start() async
    func stop() async
}

final class TranscriptionService: TranscriptionServiceProtocol {
    private let transcriptSubject = CurrentValueSubject<String, Never>("")
    private let stateSubject = CurrentValueSubject<TranscriptionState, Never>(.notStarted)

    var transcriptPublisher: AnyPublisher<String, Never> {
        transcriptSubject.eraseToAnyPublisher()
    }

    var statePublisher: AnyPublisher<TranscriptionState, Never> {
        stateSubject.eraseToAnyPublisher()
    }

    private var isRunning = false

    func start() async {
        guard !isRunning else { return }
        isRunning = true
        stateSubject.send(.starting)

        await MainActor.run {
            requestMicrophonePermission { [weak self] granted in
                guard let self = self else { return }
                if granted {
                    self.beginTranscription()
                } else {
                    self.stateSubject.send(.error("Microphone access denied"))
                    self.isRunning = false
                }
            }
        }
    }

    func stop() async {
        isRunning = false
        stateSubject.send(.notStarted)
    }

    private func requestMicrophonePermission(completion: @escaping (Bool) -> Void) {
        AVAudioApplication.requestRecordPermission { granted in
            DispatchQueue.main.async {
                completion(granted)
            }
        }
    }

    private func beginTranscription() {
        stateSubject.send(.listening)
        MLXAudioService.shared.startStreaming { [weak self] text in
            guard let self = self else { return }
            let current = self.transcriptSubject.value
            let newText = current.isEmpty ? text : "\(current) \(text)"
            self.transcriptSubject.send(newText)
        }
    }
}

enum MLXAudioService {
    static let shared = MLXAudioService()

    private init() {}

    func startStreaming(onText: @escaping (String) -> Void) {
        onText("[MLX Audio Swift integration point - stubbed]")
    }

    func stopStreaming() {}
}
