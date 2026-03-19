import AVFoundation
import Foundation

final class AudioCaptureService {
    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?

    private let targetSampleRate: Double = 16000
    private let targetChannels: AVAudioChannelCount = 1
    private let chunkSamples = 1600 // 100ms at 16kHz
    private let chunkBytes: Int

    private var pcmBuffer = Data()
    private let bufferLock = NSLock()

    var onChunk: ((Data) -> Void)?

    private(set) var isRunning = false

    init() {
        chunkBytes = chunkSamples * 2 // 16-bit = 2 bytes per sample
    }

    func start() throws {
        guard !isRunning else { return }

        let inputNode = engine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)

        guard inputFormat.sampleRate > 0 else {
            throw AudioCaptureError.noInputDevice
        }

        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: targetSampleRate,
            channels: targetChannels,
            interleaved: true
        ) else {
            throw AudioCaptureError.formatError
        }

        guard let audioConverter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
            throw AudioCaptureError.converterError
        }
        converter = audioConverter

        let bufferSize = AVAudioFrameCount(inputFormat.sampleRate * 0.1) // 100ms of input
        inputNode.installTap(onBus: 0, bufferSize: bufferSize, format: inputFormat) { [weak self] buffer, _ in
            self?.processInputBuffer(buffer)
        }

        try engine.start()
        isRunning = true
    }

    func stop() {
        guard isRunning else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        converter = nil
        isRunning = false

        bufferLock.lock()
        pcmBuffer.removeAll()
        bufferLock.unlock()
    }

    private func processInputBuffer(_ inputBuffer: AVAudioPCMBuffer) {
        guard let converter = converter else { return }

        let ratio = targetSampleRate / inputBuffer.format.sampleRate
        let outputFrameCapacity = AVAudioFrameCount(Double(inputBuffer.frameLength) * ratio) + 1

        guard let outputBuffer = AVAudioPCMBuffer(
            pcmFormat: converter.outputFormat,
            frameCapacity: outputFrameCapacity
        ) else { return }

        var error: NSError?
        var allConsumed = false
        converter.convert(to: outputBuffer, error: &error) { _, outStatus in
            if allConsumed {
                outStatus.pointee = .noDataNow
                return nil
            }
            allConsumed = true
            outStatus.pointee = .haveData
            return inputBuffer
        }

        if let error = error {
            print("Audio conversion error: \(error)")
            return
        }

        guard outputBuffer.frameLength > 0 else { return }

        let byteCount = Int(outputBuffer.frameLength) * 2 // Int16 = 2 bytes
        guard let int16Data = outputBuffer.int16ChannelData else { return }

        let data = Data(bytes: int16Data[0], count: byteCount)

        bufferLock.lock()
        pcmBuffer.append(data)

        while pcmBuffer.count >= chunkBytes {
            let chunk = pcmBuffer.prefix(chunkBytes)
            pcmBuffer.removeFirst(chunkBytes)
            bufferLock.unlock()
            onChunk?(Data(chunk))
            bufferLock.lock()
        }
        bufferLock.unlock()
    }
}

enum AudioCaptureError: LocalizedError {
    case noInputDevice
    case formatError
    case converterError

    var errorDescription: String? {
        switch self {
        case .noInputDevice: return "No audio input device available"
        case .formatError: return "Could not create target audio format"
        case .converterError: return "Could not create audio converter"
        }
    }
}
