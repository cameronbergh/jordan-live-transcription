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

## CTC → TDT Model Upgrade
- Replaced `nvidia/parakeet-ctc-0.6b` with `nvidia/parakeet-tdt-0.6b-v2`.
- TDT (Token-and-Duration Transducer) predicts both tokens and durations, avoiding the CTC "blank frame" overhead. The 0.6B v2 variant is #1 on HuggingFace ASR leaderboard (6.05% WER).
- Switched from `EncDecCTCModel` to `ASRModel.from_pretrained()` which auto-detects the model class (returns `EncDecRNNTBPEModel` for TDT).
- Now use `model.transcribe()` instead of manual forward pass + CTC decode. This handles preprocessing and decoding internally, works for CTC/RNNT/TDT uniformly.
- Had to disable CUDA graph decoder on the GPU box — NeMo 2.7.0's TDT label-looping decoder calls `cu_call()` which returns fewer values than NeMo expects, producing silent empty hypotheses. Disabling forces eager-mode fallback with no quality loss.

## Streaming Buffer Strategy
- The original 0.5s context window was the primary cause of poor transcription quality — ASR models need several seconds of context.
- New approach: accumulate audio in a growing buffer, run `model.transcribe()` every 1s of new audio on the full buffer (min 2s context).
- When buffer exceeds 30s, finalize the segment and slide the window keeping 10s overlap for continuity.
- Partials reuse the same `segmentId` so the macOS client's `AppState.handleTranscriptEvent()` updates in-place; finals commit the segment.

## Multi-Engine Architecture
- The server supports multiple transcription engines via a generalized `TranscriptionAdapter` ABC.
- Engine selection is per-session: the client sends `"engine": "parakeet"` or `"engine": "whisperlive"` in the `session.start` message's `transcription` config.
- Default engine remains `"parakeet"` for backward compatibility.
- **Parakeet** runs in-process on `cuda:0` via NeMo — same as before.
- **WhisperLive** (replacing Voxtral) runs as a separate process on `cuda:1` via Collabora's WhisperLive + `faster-whisper` backend. The Jordan server's `WhisperLiveAdapter` opens a WebSocket to the local WhisperLive instance (port 9090), sends float32 audio, and maps segment JSON back to `TranscriptResult` objects.
- Voxtral Realtime 4B was removed because vLLM 0.17.1 did not recognize the `voxtral_realtime` architecture, and upgrading `transformers` caused dependency conflicts with NeMo.
- WhisperLive uses a separate venv (`venv-whisperlive/`) from Parakeet (`venv/`) to avoid dependency conflicts.
- The two GPUs on the 3060 box are now fully utilized: GPU 0 for Parakeet, GPU 1 for WhisperLive.
- WhisperLive uses the `large-v3-turbo` Whisper model — fast inference via CTranslate2 under the hood.

## Open
- Which Linux box should be the first real deployment target? (dual-3060 box is currently in use)
- Exact restore gesture for blackout mode.
- Local persistence design when logging is enabled.
- Haptic feedback on blackout toggle.
- WhisperLive vs Parakeet quality/latency comparison not yet done — need real-world A/B test.
