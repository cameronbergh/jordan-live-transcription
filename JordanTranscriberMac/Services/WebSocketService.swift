import Foundation
import Combine

struct TranscriptEvent {
    let segmentId: String
    let text: String
    let startMs: Int
    let endMs: Int
    let isFinal: Bool
}

enum ConnectionState: Equatable {
    case disconnected
    case connecting
    case connected
    case listening
    case error(String)

    var label: String {
        switch self {
        case .disconnected: return "Disconnected"
        case .connecting: return "Connecting..."
        case .connected: return "Connected"
        case .listening: return "Listening"
        case .error(let msg): return "Error: \(msg)"
        }
    }
}

final class WebSocketService: NSObject {
    private var webSocket: URLSessionWebSocketTask?
    private var urlSession: URLSession?
    private var sessionId = UUID().uuidString

    let transcriptSubject = PassthroughSubject<TranscriptEvent, Never>()
    let stateSubject = CurrentValueSubject<ConnectionState, Never>(.disconnected)

    private var reconnectAttempts = 0
    private let maxReconnectAttempts = 10
    private var reconnectWorkItem: DispatchWorkItem?
    private var shouldReconnect = false

    func connect(host: String, port: Int) {
        disconnect()
        shouldReconnect = true
        reconnectAttempts = 0
        stateSubject.send(.connecting)

        let url = URL(string: "ws://\(host):\(port)/v1/transcription/stream")!
        urlSession = URLSession(configuration: .default, delegate: self, delegateQueue: .main)
        let task = urlSession!.webSocketTask(with: url)
        task.maximumMessageSize = 10 * 1024 * 1024
        webSocket = task
        task.resume()
    }

    func disconnect() {
        shouldReconnect = false
        reconnectWorkItem?.cancel()
        reconnectWorkItem = nil

        if let ws = webSocket {
            sendJSON(["type": "session.stop"])
            ws.cancel(with: .normalClosure, reason: nil)
        }
        webSocket = nil
        urlSession?.invalidateAndCancel()
        urlSession = nil
        stateSubject.send(.disconnected)
    }

    func sendAudioChunk(_ data: Data) {
        webSocket?.send(.data(data)) { error in
            if let error = error {
                print("Audio send error: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Protocol messages

    private func sendSessionStart() {
        sessionId = UUID().uuidString
        let msg: [String: Any] = [
            "type": "session.start",
            "sessionId": sessionId,
            "audio": [
                "encoding": "pcm_s16le",
                "sampleRate": 16000,
                "channels": 1,
                "chunkMs": 100
            ],
            "transcription": [
                "partials": true,
                "language": NSNull()
            ],
            "client": [
                "platform": "macos",
                "appVersion": "1.0.0"
            ]
        ]
        sendJSON(msg)
    }

    private func sendJSON(_ dict: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: dict),
              let text = String(data: data, encoding: .utf8) else { return }
        webSocket?.send(.string(text)) { error in
            if let error = error {
                print("JSON send error: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Receive loop

    private func listenForMessages() {
        webSocket?.receive { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .success(let message):
                self.handleMessage(message)
                self.listenForMessages()
            case .failure(let error):
                let desc = error.localizedDescription
                if self.shouldReconnect {
                    print("WebSocket receive error: \(desc)")
                    self.stateSubject.send(.error(desc))
                    self.scheduleReconnect()
                }
            }
        }
    }

    private func handleMessage(_ message: URLSessionWebSocketTask.Message) {
        guard case .string(let text) = message,
              let data = text.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = json["type"] as? String else { return }

        switch type {
        case "session.started":
            stateSubject.send(.listening)

        case "transcript.partial", "transcript.final":
            let event = TranscriptEvent(
                segmentId: json["segmentId"] as? String ?? "",
                text: json["text"] as? String ?? "",
                startMs: json["startMs"] as? Int ?? 0,
                endMs: json["endMs"] as? Int ?? 0,
                isFinal: type == "transcript.final"
            )
            transcriptSubject.send(event)

        case "status":
            let state = json["state"] as? String ?? ""
            if state == "listening" {
                stateSubject.send(.listening)
            }

        case "error":
            let msg = json["message"] as? String ?? "Unknown error"
            let fatal = json["fatal"] as? Bool ?? false
            stateSubject.send(.error(msg))
            if fatal {
                disconnect()
            }

        case "pong":
            break

        default:
            break
        }
    }

    // MARK: - Reconnection

    private func scheduleReconnect() {
        guard shouldReconnect, reconnectAttempts < maxReconnectAttempts else {
            if reconnectAttempts >= maxReconnectAttempts {
                stateSubject.send(.error("Max reconnect attempts reached"))
            }
            return
        }

        reconnectAttempts += 1
        let delay = min(pow(2.0, Double(reconnectAttempts)), 30.0)
        stateSubject.send(.connecting)

        let work = DispatchWorkItem { [weak self] in
            guard let self = self, self.shouldReconnect,
                  let oldSession = self.urlSession else { return }
            // Re-use the stored host/port from the URL
            guard let url = self.webSocket?.originalRequest?.url ?? oldSession.configuration.identifier.flatMap({ URL(string: $0) }) else { return }
            self.reconnectWith(url: url)
        }
        reconnectWorkItem = work
        DispatchQueue.main.asyncAfter(deadline: .now() + delay, execute: work)
    }

    private func reconnectWith(url: URL) {
        webSocket?.cancel(with: .normalClosure, reason: nil)
        urlSession?.invalidateAndCancel()

        urlSession = URLSession(configuration: .default, delegate: self, delegateQueue: .main)
        let task = urlSession!.webSocketTask(with: url)
        task.maximumMessageSize = 10 * 1024 * 1024
        webSocket = task
        task.resume()
    }
}

// MARK: - URLSessionWebSocketDelegate

extension WebSocketService: URLSessionWebSocketDelegate {
    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        reconnectAttempts = 0
        stateSubject.send(.connected)
        sendSessionStart()
        listenForMessages()
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        if shouldReconnect {
            scheduleReconnect()
        } else {
            stateSubject.send(.disconnected)
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: (any Error)?) {
        if let error = error, shouldReconnect {
            print("WebSocket connection failed: \(error.localizedDescription)")
            stateSubject.send(.error(error.localizedDescription))
            scheduleReconnect()
        }
    }
}
