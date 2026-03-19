# Jordan Transcriber - Xcode Setup Guide

## Prerequisites

- **Xcode 15+** required
- **CocoaPods** or **Swift Package Manager** for MLX Audio Swift (see below)
- iOS 17.0+ deployment target

## MLX Audio Swift Integration

MLX Audio Swift is the Apple's MLX framework for on-device audio transcription using the Parakeet model.

### Option A: Swift Package Manager (Recommended if available)

Add to your `Package.swift` or via Xcode File > Add Package Dependencies:

```
https://github.com/ml-explore/mlx-audio-swift
```

### Option B: CocoaPods

Add to your `Podfile`:
```ruby
pod 'MLXAudioSwift'
```

Then run `pod install`.

### Integration Point

In `JordanTranscriber/Services/TranscriptionService.swift`, the `MLXAudioService` singleton is the integration boundary:

```swift
enum MLXAudioService {
    static let shared = MLXAudioService()
    
    func startStreaming(onText: @escaping (String) -> Void) {
        // TODO: Wire MLX Audio Swift here
        onText("[MLX Audio Swift integration point - stubbed]")
    }
    
    func stopStreaming() {}
}
```

## Generating the Xcode Project

1. Install XcodeGen if not already installed:
   ```bash
   brew install xcodegen
   ```

2. Generate the Xcode project:
   ```bash
   xcodegen generate
   ```

3. Open `JordanTranscriber.xcodeproj` in Xcode

4. Configure signing (select your team in project settings)

5. Build and run on iPhone simulator or device

## Project Structure

```
JordanTranscriber/
├── App/
│   ├── JordanTranscriberApp.swift    # @main entry point
│   └── AppState.swift                # Central state management
├── Models/
│   └── AppSettings.swift             # Settings model
├── Services/
│   └── TranscriptionService.swift    # Transcription boundary + MLX integration point
├── Views/
│   ├── ContentView.swift            # Root view with blackout logic
│   ├── TranscriptView.swift         # Main transcript display
│   ├── SettingsView.swift           # Settings screen
│   ├── BlackoutOverlay.swift        # Privacy blackout view
│   └── ShakeDetector.swift          # Shake gesture detection
└── Resources/
    └── Info.plist                    # App configuration
```

## Key Design Decisions

- **Protocol-based transcription service**: `TranscriptionServiceProtocol` allows easy mocking and swapping implementations
- **Combine-based state**: Reactive streams for transcript updates and state changes
- **CMMotionManager for shake**: Uses accelerometer to detect shake gestures
- **Privacy-first defaults**: Logging OFF by default
