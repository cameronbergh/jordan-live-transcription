# AGENTS.md

## Project
Jordan Live Transcription App — iPhone and macOS clients with a GPU transcription backend.

## Current Goal
Complete the live transcription pipeline: clients stream mic audio over WebSocket to the server, select between Parakeet (NeMo TDT) and WhisperLive (large-v3-turbo) engines, and display streaming transcript text in real time.

## Architecture
- **iOS client** (`JordanTranscriber/`): SwiftUI app scaffold exists, transcription layer still stubbed — needs WebSocket integration.
- **macOS client** (`JordanTranscriberMac/`): SwiftUI app with working mic capture → WebSocket streaming → live transcript display. Engine selector in settings (Parakeet / WhisperLive).
- **CUDA backend** (`server-cuda/`): FastAPI + WebSocket server with multi-engine support on the GPU box (`cameron-ms-7b17`, 2x RTX 3060):
  - **Parakeet engine** — `nvidia/parakeet-tdt-0.6b-v2` via NeMo, runs in-process on `cuda:0`. End-to-end transcription confirmed working.
  - **WhisperLive engine** — `large-v3-turbo` via Collabora WhisperLive + `faster-whisper` on `cuda:1`. Jordan server proxies audio to local WhisperLive WebSocket (port 9090).
- **MLX backend** (`server-mlx/`): Parallel Apple Silicon track using MLX/Whisper. Mock mode works; real mode requires `mlx-audio` install.
- **Wire protocol**: Defined in `BACKEND_API.md` — WebSocket, PCM16 mono 16kHz audio in, `transcript.partial` / `transcript.final` events out. Client selects engine via `transcription.engine` in `session.start`.

## Rules
- Prefer simple, readable SwiftUI structure over over-engineering.
- Optimize for fast app launch and immediate transcription UX.
- Keep privacy front and center.
- Update `PROGRESS.md`, `TASKS.md`, and `DECISIONS.md` as meaningful milestones are reached.
- When modifying `server-cuda/`, deploy to the GPU box via `scp` or `rsync` to `/home/openclaw/jordan-live-transcription-ios/server-cuda/` and restart the server.
- Test real transcription with `judge_23sec_16k_mono.wav` using `scripts/test_client.py`.

## MVP Requirements
- Starts transcription immediately on app open
- Large readable transcript UI
- Shake-triggered privacy blackout overlay (iOS)
- Settings screen with logging toggle, server host/port config
- Mic audio streams to GPU backend, transcript streams back in real time

## Notes for Coding Agents
- The CUDA server is live on `cameron-ms-7b17:8765` with `MOCK_PARAKEET=false` and `nvidia/parakeet-tdt-0.6b-v2`.
- The Parakeet venv is at `/home/openclaw/jordan-live-transcription-ios/server-cuda/venv/` (NeMo 2.7.0, torch 2.10.0+cu128).
- The WhisperLive venv is at `/home/openclaw/jordan-live-transcription-ios/server-cuda/venv-whisperlive/` — separate to avoid dependency conflicts.
- WhisperLive serves on port 9090 (`cuda:1`); the Jordan server connects via `WHISPERLIVE_HOST=localhost WHISPERLIVE_PORT=9090`.
- The macOS client builds with `xcodegen generate --spec project-mac.yml && xcodebuild`.
- The iOS client builds with `xcodegen generate --spec project.yml && xcodebuild`.
- Deploy updated server code with `rsync` to `/home/openclaw/jordan-live-transcription-ios/server-cuda/` and restart both services.
- Keep commits / changes focused and explain tradeoffs in `PROGRESS.md`.
