# Decisions

## Confirmed
- App is iPhone-first.
- App should begin live transcription immediately when opened.
- Core UX should be minimal and utility-focused.
- Transcription processing should happen on a backend server rather than entirely on-device.
- The phone should stream audio to the backend and receive live transcript updates back.
- Privacy blackout should be triggered by a shake gesture.
- Settings should include a logging toggle.
- Logging defaults to OFF (privacy-first).
- Blackout is a full-screen black overlay (not screen-off).
- Font size options: Small/Medium/Large/Extra Large.
- The existing Jordan project repo remains the single project home; no separate repo/project split for backend planning yet.
- The backend should target Linux GPU hardware, not MLX Audio Swift and not llama.cpp/GGUF.
- NVIDIA Parakeet is the preferred backend speech stack direction for now.
- Backend servers should preload and keep their transcription model resident in memory at startup to avoid first-request load delay.

## Implementation Decisions
- Protocol-based transcription service boundary in the client is still the right abstraction.
- The client should be able to swap backend endpoints later if needed.
- WebSocket is the transport for MVP (confirmed).
- Audio format: PCM16 mono, 16kHz, 100ms chunks (confirmed).
- Backend emits both partial (interim) and final transcript segments; client renders partials live and merges with finals (confirmed).
- Shake detection remains client-side.
- Blackout remains client-side.

## Backend / Speech Engine Direction
- Primary architecture: streaming backend service + iPhone client.
- Backend role: accept live audio, run ASR, and stream transcript words/segments back.
- Primary host candidates: Linux GPU box with 2x RTX 3060 12GB, and another Linux box with 2x 2080 Ti as backup/alternative.
- Speech engine direction: regular NVIDIA Parakeet ecosystem / repo.
- Detailed first-pass protocol is documented in `BACKEND_API.md`.
- Backend server stack: Python + FastAPI + websockets (async).
- Parakeet adapter boundary cleanly separates Parakeet runtime from WebSocket session management.
- Server ships with working `MockParakeetAdapter` for protocol testing; `RealParakeetAdapter` has functional CUDA initialization, warmup, and streaming loop. A bug in the NeMo API call pattern (`input_signal_length=None`) was discovered and fixed during real GPU testing on `nvidia/parakeet-ctc-0.6b`.
- `RealParakeetAdapter` runs VAD model if available (optional, non-fatal if unavailable); correct VAD model name is `nvidia/parakeet-vad`. Warmup inference triggers GPU kernel compilation at startup.

## MLX Backend Track (Parallel Alternative)
- A separate MLX backend track exists in `server-mlx/` for Apple Silicon deployment.
- Mirrors the structure of `server-cuda/` but uses `mlx-audio` / Whisper instead of Parakeet.
- Runs on Cameron's Mac (M-series chip) without needing Linux/NVIDIA GPU.
- Same WebSocket API contract, same session model, same message schema.
- `MockMLXAdapter` works immediately; `RealMLXAdapter` requires `mlx-audio` installation per `MLX_INTEGRATION.md`.
- Tradeoff: MLX inference is slower than GPU inference, but avoids needing the Linux GPU box.
- `RealMLXAdapter` limitations: no word-level timestamps, no VAD integration (documented in `MLX_INTEGRATION.md`).
- MLX server includes deploy script (`deploy_mlx.sh`) and health check script (`check_health.sh`) for Apple Silicon setup.

## macOS Client
- A native macOS SwiftUI client (`JordanTranscriberMac/`) was built alongside the iOS app.
- Uses `AVAudioEngine` for mic capture, `AVAudioConverter` to resample to 16kHz mono PCM16, `URLSessionWebSocketTask` for WebSocket.
- Same `BACKEND_API.md` protocol as the iOS client — server is agnostic to which platform connects.
- Settings popover allows configuring server host/port and font size at runtime.
- No third-party dependencies — only Apple frameworks (SwiftUI, AVFoundation, Foundation, Combine).
- XcodeGen config at `project-mac.yml`, targets macOS 14+ (Sonoma).

## CTC Decoding
- NeMo's `ctc_decoder_predictions_tensor()` is the correct API for decoding CTC logits to text. It handles blank removal, consecutive duplicate collapse, and BPE detokenization internally.
- Manual CTC decode approaches were tried and failed due to: wrong blank token ID assumption (0 vs 1024), missing CTC deduplication, and inability to locate the tokenizer on the model object.
- On NeMo 2.7.0 (GPU box), `ctc_decoder_predictions_tensor` works correctly.

## Open
- Which Linux box should be the first real deployment target? (dual-3060 box is currently in use)
- Exact restore gesture for blackout mode.
- Local persistence design when logging is enabled.
- Haptic feedback on blackout toggle.
- Streaming transcript quality: each 0.5s chunk is transcribed independently, producing fragmented text. Larger inference windows or sliding-window overlap would improve coherence.
