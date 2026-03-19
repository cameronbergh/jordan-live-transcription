# MLX Integration Guide

This guide explains how to complete the MLX transcription adapter on Apple Silicon hardware.

## Overview

The `mlx_adapter.py` provides a clean adapter boundary between the WebSocket server and the MLX speech runtime. The `MockMLXAdapter` works immediately for testing. The `RealMLXAdapter` stub requires installing `mlx-audio` and completing the async integration.

## Adapter Architecture

```
WebSocket Server (server.py)
    └── TranscriptionSession (session.py)
            └── MLXAdapter (mlx_adapter.py)
                    ├── MockMLXAdapter  ← works today, no MLX needed
                    └── RealMLXAdapter ← requires mlx-audio on Apple Silicon
```

The `MLXAdapter` abstract base class defines the contract:
- `initialize(model_name)` — load model into memory
- `warm_up()` — run a dummy inference to warm up
- `transcribe_stream(audio_chunks, session_id, transcript_callback)` — streaming inference
- `shutdown()` — release resources

## Prerequisites

### Hardware
- Apple Silicon Mac (M1, M2, M3, or M4)
- macOS 13.0+ recommended
- Sufficient RAM for the model (Whisper large: ~3GB unified memory)

### Software
- Python 3.10+
- Homebrew (for installing coreutils if needed)
- Xcode command line tools

## Step 1: Install MLX

MLX is Apple's ML framework for Apple Silicon. Install it via pip:

```bash
pip install mlx
```

Verify:
```bash
python -c "import mlx.core as mx; print(mx.__version__)"
```

## Step 2: Install mlx-audio

The `mlx-audio` package provides audio ML models including Whisper:

```bash
pip install mlx-audio
```

Verify:
```bash
python -c "from mlx_audio.mlx_whisper import load_whisper_model, transcribe; print('mlx-audio OK')"
```

## Step 3: Choose a Model

Recommended models for Jordan's use case:

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| `mlx-community/whisper-large-v3-mlx` | ~3GB | slower | best |
| `mlx-community/whisper-base-mlx` | ~500MB | faster | good |
| `mlx-community/whisper-small-mlx` | ~300MB | fast | decent |

For MVP, `whisper-base` or `whisper-small` gives faster iteration.

Set via environment variable:
```bash
export MLX_MODEL="mlx-community/whisper-base-mlx"
```

Or edit `config.py` directly.

## Step 4: Verify Model Download

First run of the model downloads it from HuggingFace (~500MB-3GB depending on model size):

```bash
python -c "from mlx_audio.mlx_whisper import load_whisper_model; load_whisper_model('mlx-community/whisper-base-mlx')"
```

## Step 5: Run the Server

### Mock mode (no MLX):
```bash
MOCK_MLX=true python server.py
```

### Real MLX mode:
```bash
MOCK_MLX=false MLX_MODEL="mlx-community/whisper-base-mlx" python server.py
```

Or use the convenience script:
```bash
./scripts/run_server.sh
```

Or use the deployment script for one-shot setup:
```bash
./scripts/deploy_mlx.sh
```

## Step 6: Test

Run the WebSocket test client:

```bash
python scripts/test_client.py
```

Or connect the iOS app to `ws://<mac-ip>:8765/v1/transcription/stream`.

## How RealMLXAdapter Works

### initialize()
Loads the Whisper model onto the GPU using `mx.set_default_device(mx.gpu)` for optimal performance:

```python
from mlx_audio.mlx_whisper import load_whisper_model

self._model = load_whisper_model(model_name)
```

### warm_up()
Runs a dummy inference to trigger JIT compilation of GPU kernels:

```python
from mlx_audio.mlx_whisper import transcribe

dummy_audio = np.random.randn(self._sample_rate).astype(np.float32) * 0.01
audio_mlx = mx.array(dummy_audio)
_ = transcribe(self._model, audio_mlx)
```

### transcribe_stream()
Streams audio chunks through the model:
1. Accumulates PCM16 chunks in a buffer
2. When enough samples are collected (0.5s), runs transcription
3. Uses overlap buffer to maintain context between chunks
4. Emits partial transcripts and periodic finals

## Performance Notes

- **Memory**: Whisper large V3 uses ~3GB of unified memory. Leave headroom.
- **Latency**: First inference is slow (model loading + JIT). Subsequent chunks are faster.
- **Chunk size**: 100ms audio chunks (1600 bytes PCM16) work well.
- **Streaming**: The adapter processes chunks as they arrive, emitting partial transcripts.
- **Battery**: Expect elevated CPU/GPU usage during transcription. Not recommended for thermal-constrained mobile use.

## Troubleshooting

### "mlx-audio not found"
```bash
pip install mlx-audio
```

### "Out of memory"
- Use a smaller model (`whisper-base` or `whisper-small`)
- Reduce batch size in `config.py`
- Close other memory-heavy apps

### "Port already in use"
```bash
export PORT=8766  # use a different port
python server.py
```

### Slow inference
- Use `whisper-base` or `whisper-small` for faster iteration
- Large models like `whisper-large-v3` are more accurate but slower
- Ensure no other processes are competing for GPU memory

## Limitations of MLX Whisper Streaming

The current `RealMLXAdapter` implementation has some limitations:

1. **No word-level timestamps**: mlx-audio's `transcribe()` returns full sequence text, not word-level timestamps.
2. **No VAD integration**: Voice Activity Detection is not integrated - audio is transcribed continuously.
3. **Overlap strategy**: Simple overlap buffer maintains context, but optimal chunking strategy is model-dependent.

For production, consider:
- Integrating Apple Speech framework's VAD
- Using a streaming decoder that produces word-level hypotheses
- Adding language detection or multilingual support

## Alternative: Parakeet-CTC on MLX

If `mlx-audio` doesn't work out, consider:
- `parakeet-ctc` if an MLX-compatible version emerges
- Running a small Whisper via `coreml` on Apple Neural Engine
- llama.cpp with a Whisper GGUF model (slower but portable)

The adapter boundary makes swapping implementations straightforward.

## Backend API Compatibility

This MLX backend track implements the same WebSocket protocol as the NVIDIA CUDA server:
- Endpoint: `/v1/transcription/stream`
- Messages: `session.start`, `audio.append` (binary), `session.stop`, `ping`
- Responses: `session.started`, `transcript.partial`, `transcript.final`, `status`, `error`, `pong`

See `../BACKEND_API.md` for the full protocol specification.

The only difference is the `engine` field in `session.started`: `"mlx"` vs `"parakeet"`.
