# MLX Backend Track

This is a separate MLX-based backend path for Jordan's live transcription project, optimized for Apple Silicon.

## Purpose

Explore a server implementation built around MLX / Apple-Silicon-friendly stack, separate from the Linux/NVIDIA Parakeet server in `../server-cuda/`.

## Architecture

```
iPhone App (client)
    └── WebSocket: /v1/transcription/stream
            └── MLX Transcription Server (this directory)
                    └── TranscriptionSession
                            └── MLXAdapter
                                    ├── MockMLXAdapter (works today)
                                    └── RealMLXAdapter (requires mlx-audio on Apple Silicon)
```

## Files

```
server-mlx/
├── server.py              FastAPI + WebSocket server (mirrors BACKEND_API.md contract)
├── session.py             Per-connection TranscriptionSession
├── protocol.py            Message serialization matching BACKEND_API.md
├── mlx_adapter.py         MLXAdapter ABC + MockMLXAdapter + RealMLXAdapter
├── audio_buffer.py        Ring buffer for PCM16 audio chunks
├── config.py              Environment-variable configuration
├── requirements.txt       Python dependencies (fastapi, uvicorn, websockets, numpy, scipy)
├── MLX_INTEGRATION.md     Step-by-step guide to complete RealMLXAdapter on Apple Silicon
├── scripts/
│   ├── run_server.sh      Convenience launch script
│   ├── deploy_mlx.sh      One-shot Apple Silicon setup script
│   ├── check_health.sh    Health check script
│   └── test_client.py     WebSocket test client
└── README.md (this file)
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Run in mock mode (no MLX required)
```bash
MOCK_MLX=true python server.py
```

### 3. Test with the WebSocket client
```bash
python scripts/test_client.py
```

### 4. For real MLX inference on Apple Silicon
```bash
# Install mlx-audio
pip install mlx-audio

# Run with real MLX
MOCK_MLX=false MLX_MODEL="mlx-community/whisper-base-mlx" python server.py
```

When running in real mode, the server should load the MLX model into memory at startup and keep it resident, ideally warming it before the first client session so the first transcript is not delayed by model initialization.

See `MLX_INTEGRATION.md` for full setup instructions.

## Protocol Compatibility

This server implements the same WebSocket API contract as `../BACKEND_API.md`:
- `session.start` / `session.started` handshake
- Binary PCM16 audio frames (16kHz mono)
- `transcript.partial` / `transcript.final` events
- `status`, `error`, `ping`/`pong` messages

The only protocol difference: `session.started` reports `"engine": "mlx"` instead of `"parakeet"`.

## Key Differences from NVIDIA Backend

| Aspect | MLX Track | NVIDIA Backend |
|--------|-----------|----------------|
| Hardware | Apple Silicon (M-series) | Linux + NVIDIA GPU |
| Framework | mlx-audio / Whisper | NeMo + Parakeet |
| Portability | macOS only | Linux only |
| Status | Prototype / adapter stub | Prototype / adapter stub |

Both tracks implement the same API contract and can be swapped by changing the server URL in the iOS client.

## Relation to Shared Backend API

This track follows the shared API direction from `../BACKEND_API.md` as closely as practical:
- Same WebSocket endpoint path
- Same message schema
- Same session model
- Differences noted where they exist (engine name, config vars)

## Constraints

- Keep this work separate from the NVIDIA CUDA server path (`../server-cuda/`)
- Reuse the shared backend API contract where practical
- Optimize for a backend that Cameron can realistically run on Apple Silicon
- Follow the same adapter boundary pattern as the NVIDIA backend
