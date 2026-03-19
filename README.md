# Jordan Live Transcription App

A live transcription app for Jordan — iPhone and macOS clients streaming audio to a GPU backend.

## Purpose
Open the app and immediately begin transcribing nearby speech with minimal friction.

## Current Direction
- iPhone client (`JordanTranscriber/`) and macOS client (`JordanTranscriberMac/`)
- Linux GPU backend (`server-cuda/`) running NVIDIA Parakeet on 2x RTX 3060
- Parallel Apple Silicon backend (`server-mlx/`) using MLX/Whisper
- Clients stream audio over WebSocket, backend streams transcript updates back
- Privacy blackout mode via shake gesture (iOS)
- Simple settings with logging toggle, server host/port config

## Project Layout
- `JordanTranscriber/` — iOS SwiftUI app
- `JordanTranscriberMac/` — macOS SwiftUI app (mic capture, WebSocket streaming, live transcript display)
- `server-cuda/` — NVIDIA Parakeet backend (FastAPI + WebSocket, runs on Linux GPU box)
- `server-mlx/` — MLX/Whisper backend (runs on Apple Silicon)
- `project.yml` — XcodeGen config for iOS app
- `project-mac.yml` — XcodeGen config for macOS app

## Documentation
- `SPEC.md` — product / UX spec
- `BACKEND_API.md` — streaming backend wire protocol
- `TASKS.md` — current work queue
- `PROGRESS.md` — build log and milestones
- `DECISIONS.md` — product / technical decisions
- `AGENTS.md` — instructions for coding agents working in this repo

## Status
End-to-end transcription pipeline is working. The CUDA server on `cameron-ms-7b17` runs `nvidia/parakeet-ctc-0.6b` with real-time streaming transcription over WebSocket. The macOS client captures microphone audio, streams to the server, and displays live transcript text. The iOS client scaffold exists but its transcription layer still needs to be wired to the WebSocket backend.
