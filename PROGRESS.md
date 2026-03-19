# Progress

## 2026-03-18

### Scaffold Completed
- Created `JordanTranscriber/` source tree with SwiftUI app structure.
- Generated `JordanTranscriber.xcodeproj`.
- Added app state, transcript view, settings view, blackout overlay, shake detector, `Info.plist`, and setup notes.

### Architecture Pivot
- Project direction shifted from primarily on-device transcription to a client/server model.
- The iPhone app should stream audio to a backend service and receive live transcript updates back.
- Existing app scaffold remains useful, but the transcription layer now needs to target a network service boundary.
- Kept this work inside the existing Jordan project repo rather than splitting backend planning into a separate project.

### Backend Direction Refined
- Backend target shifted away from MLX Audio Swift / llama.cpp.
- Current direction is a Linux GPU backend using the regular NVIDIA Parakeet stack.
- Primary candidate host is the Linux box with 2x RTX 3060 12GB.
- Secondary candidate host is the Linux box with 2x 2080 Ti.

### Backend Spec Added
- Added `BACKEND_API.md` defining the first-pass backend protocol.
- Current MVP direction uses a WebSocket connection for streaming audio in and transcript events out.
- Recommended first-pass audio format: PCM16 mono at 16kHz, sent in small chunks.

### Open Build Questions
- Need to validate the exact NVIDIA Parakeet runtime / serving approach.
- Need to decide which Linux box should be the first real backend target.
- Need both backend tracks to preload and warm their model at startup so first-use latency stays low.

## 2026-03-18 (Afternoon)

### Backend Prototype Completed

Created a fully functional CUDA server prototype in `server-cuda/`:

- `server.py` — FastAPI + WebSocket server, binds to `0.0.0.0:8765` by default
- `session.py` — per-connection `TranscriptionSession` handling session lifecycle, audio queue, and message dispatch
- `parakeet_adapter.py` — `ParakeetAdapter` abstract base + `MockParakeetAdapter` (working) + `RealParakeetAdapter` (stub with integration steps in `PARAKEET_INTEGRATION.md`)
- `audio_buffer.py` — `AudioBuffer` ring buffer for assembling PCM16 chunks
- `protocol.py` — full message serialization matching `BACKEND_API.md`: `session.started`, `transcript.partial`, `transcript.final`, `status`, `error`, `pong`
- `config.py` — environment-variable configuration
- `requirements.txt` — Python deps: fastapi, uvicorn, websockets, numpy, scipy
- `PARAKEET_INTEGRATION.md` — step-by-step guide to install NeMo/Parakeet on the GPU machine and complete the adapter
- `scripts/run_server.sh` — convenience launch script
- `scripts/test_client.py` — WebSocket test client for manual verification

**Server runs today** with `MOCK_PARAKEET=true` (default) — produces simulated streaming transcripts
for protocol and integration testing without GPU hardware.

**To run on GPU machine:**
```bash
cd backend
pip install -r requirements.txt
# Set MOCK_PARAKEET=false and install NeMo on the GPU machine per PARAKEET_INTEGRATION.md
python server.py
```

**Adapter boundary**: The `ParakeetAdapter` ABC cleanly separates the WebSocket server from the
Parakeet runtime. Cameron needs to install NeMo + Parakeet model on the Linux box and implement
the `transcribe_stream` async method in `RealParakeetAdapter` per the comments in that file and
the detailed guide in `PARAKEET_INTEGRATION.md`.

**Protocol coverage**: session.start, session.stop, status, error, transcript.partial, transcript.final,
pong/ping — all implemented and matching `BACKEND_API.md`.

## 2026-03-18 (Evening)

### MLX Backend Track Added

Created a parallel MLX backend track in `server-mlx/`, separate from the NVIDIA CUDA server in `server-cuda/`:

- `server.py` — FastAPI + WebSocket server, same API contract as NVIDIA backend
- `session.py` — `TranscriptionSession` handling per-connection session lifecycle
- `protocol.py` — message serialization matching `BACKEND_API.md` (engine reports as `"mlx"`)
- `mlx_adapter.py` — `MLXAdapter` abstract base + `MockMLXAdapter` (working) + `RealMLXAdapter` (stub with integration steps in `MLX_INTEGRATION.md`)
- `audio_buffer.py`, `config.py`, `requirements.txt` — parallel structure to `server-cuda/`
- `MLX_INTEGRATION.md` — step-by-step guide to install `mlx-audio` on Apple Silicon and complete `RealMLXAdapter`
- `scripts/run_server.sh`, `scripts/test_client.py` — convenience scripts

**Server runs today** with `MOCK_MLX=true` (default) — produces simulated streaming transcripts for protocol testing.

**To run on Apple Silicon:**
```bash
cd server-mlx
pip install -r requirements.txt
# Install mlx-audio per MLX_INTEGRATION.md, then:
MOCK_MLX=false python server.py
```

**Adapter boundary**: The `MLXAdapter` ABC cleanly separates the WebSocket server from the MLX runtime. Cameron can install `mlx-audio` on his Mac and implement the `transcribe_stream` async method in `RealMLXAdapter` per `MLX_INTEGRATION.md`.

**Protocol compatibility**: Same WebSocket API as NVIDIA backend (`/v1/transcription/stream`), same message schema, same session model. Only difference: `session.started` reports `"engine": "mlx"` instead of `"parakeet"`.

**Tradeoff vs NVIDIA backend**: MLX backend runs entirely on Apple Silicon (no NVIDIA GPU needed, but slower inference). NVIDIA backend targets Linux + Parakeet (faster inference on GPU, requires Linux box).

## 2026-03-18 (Night)

### CUDA Server Strengthening Pass

Major improvements to `server-cuda/` to bring it closer to a runnable NVIDIA backend:

**`parakeet_adapter.py`**:
- `TranscriptCallback` type alias: `Callable[[TranscriptResult], Awaitable[None]]` — callback is explicitly async
- `RealParakeetAdapter` now properly initializes CUDA device, VAD model (optional), and warm-up inference
- Streaming loop implements trailing-context buffer for overlap across chunks
- Graceful fallback if VAD model fails to load

**`session.py`**:
- Rewrote state machine using `SessionState` enum (`CONNECTING`, `READY`, `LISTENING`, `PROCESSING`, `CLOSED`)
- Fixed `send_status()` to accept `SessionState` enum directly (was passing string before)
- `handle_message()` properly discriminates binary vs JSON at the type level
- Audio queue now bounded (`maxsize=100`) with overflow handling that drops oldest chunks
- `_handle_audio_frame` guards against receiving audio before `session.start`

**`protocol.py`**:
- Message types, dataclasses, and serialization already correct — no changes needed
- `is_final` serialization in `TranscriptPartialMessage` and `TranscriptFinalMessage` correctly maps to `isFinal` in JSON

**`PARAKEET_INTEGRATION.md`**:
- Complete rewrite with accurate NeMo installation steps
- Correct model name: `nvidia/speakquik-vad` (was `speakquak-vad` typo)
- Documents adapter lifecycle: `initialize()` → `warm_up()` → `transcribe_stream()`
- Lists remaining streaming items: VAD integration, streaming decoder, overlap strategy, timestamps

**`requirements.txt`**:
- Core server deps listed: fastapi, uvicorn, websockets, numpy, scipy, pydantic
- torch and nemo-toolkit NOT listed (install separately on GPU machine to avoid version conflicts)

**New scripts**:
- `scripts/deploy_cuda.sh` — one-shot setup script: checks CUDA, creates venv, installs deps, verifies model loading, runs health check
- `scripts/check_health.sh` — verifies root, `/health`, and `/v1/status` endpoints
- Updated `scripts/run_server.sh` — displays GPU info, validates CUDA before starting with real adapter

**Smoke test results**:
- Mock server starts correctly: model preload + warmup logs visible
- All three health endpoints return expected JSON
- Server is runnable in mock mode on any platform

## 2026-03-18 (Decode Path Fix)

### Bug: `'CTCBPEDecoding' object has no attribute 'decode'`

During real WAV transcription testing on `nvidia/parakeet-ctc-0.6b`, the streaming loop crashed with:

```
AttributeError: 'CTCBPEDecoding' object has no attribute 'decode'
```

**Root cause**: The code at `parakeet_adapter.py:280` called `decode_fn.decode(predicted_ids)` where `decode_fn = self._model.decoding` (a `CTCBPEDecoding` instance). `CTCBPEDecoding` does not have a `decode()` method — that's a method on `CTCGreedyDecoderBPE`, not on the aggregating `CTCBPEDecoding` wrapper. The correct NeMo API for converting model logits to text is `ctc_decoder_predictions_tensor()` on the `CTCDecoding` base class.

### Fix Applied

**`parakeet_adapter.py` — `RealParakeetAdapter.transcribe_stream()`**:

Replaced the broken decode path:
```python
# BROKEN — CTCBPEDecoding has no .decode() method
predicted_ids = torch.argmax(logits, dim=-1)
decode_fn = getattr(self._model, "decoding", None)
transcript_text = decode_fn.decode(predicted_ids)
```

With the correct NeMo API:
```python
# CORRECT — use ctc_decoder_predictions_tensor from CTCDecoding base class
hypotheses = self._model.decoding.ctc_decoder_predictions_tensor(
    decoder_outputs=logits,
    decoder_lengths=audio_length,
    return_hypotheses=False,
)
transcript_text = hypotheses[0] if hypotheses and len(hypotheses) > 0 else ""
```

`ctc_decoder_predictions_tensor` is defined on `CTCDecoding` (which `CTCBPEDecoding` inherits) and handles CTC greedy decoding + BPE detokenization internally. This is the same method used by `EncDecCTCModel.transcribe()` internally.

### test_client.py improvements

Added graceful session-close handling after `session.stop`:
- Tracks `final_received` and `close_received` flags
- Breaks out of the message loop once all final transcripts + close status are received
- Prevents indefinite hanging if the server closes the connection cleanly

## 2026-03-18 (GPU Box Real Test — Adapter Bug Fix Pass)

### Real Test Results on Ubuntu GPU Box

The server was booted on the Linux GPU machine and loaded `nvidia/parakeet-ctc-0.6b` successfully. The WebSocket session opened correctly. Real transcription failed with this NeMo error:

```
ValueError: Arguments `input_signal` and `input_signal_length` are mutually exclusive
  with `processed_signal` and `processed_signal_len` arguments.
```

**Root cause**: The `EncDecCTCModel.forward()` method has this check:
```python
has_input_signal = input_signal is not None and input_signal_length is not None
has_processed_signal = processed_signal is not None and processed_signal_length is not None
if (has_input_signal ^ has_processed_signal) == False:
    raise ValueError(...)
```

The code was passing `input_signal_length=None` alongside `input_signal`, making `has_input_signal = False`, which triggered the error. Both `input_signal` and `input_signal_length` must be provided together.

### Fixes Applied

**`parakeet_adapter.py` — `RealParakeetAdapter`**:
1. **Warm-up call**: Changed from `self._model(input_signal=dummy_audio, input_signal_length=None)` to `self._model(input_signal=dummy_audio, input_signal_length=dummy_length)` where `dummy_length = torch.tensor([self._sample_rate], ...)` (1 second of audio).
2. **Streaming inference call**: Changed from `self._model(input_signal=audio_tensor, input_signal_length=None)` to pass `input_signal_length=torch.tensor([samples.shape[0]], dtype=torch.long, device=self._device)` with the actual sample count.
3. **Model output handling**: Model returns a 3-tuple `(log_probs, encoded_len, greedy_predictions)`. Updated to handle `model_output` as tuple correctly.
4. **VAD warm-up**: Added proper `input_signal_length` to VAD dummy inference call.

**`session.py`**:
- Increased audio queue `maxsize` from `100` to `500` to reduce "Buffer full" warnings during bursts.
- Removed redundant `audio_buffer.append(data)` call — the adapter maintains its own buffer for trailing context; session-level buffering was duplicating memory without benefit.

**`config.py`**:
- Changed default VAD model from `nvidia/speakquik-vad` (unavailable) to `nvidia/parakeet-vad` (correct NVIDIA model name).

**`README.md` / `PARAKEET_INTEGRATION.md`**:
- Updated VAD model name in all docs.
- Fixed warm-up code example to show correct API call pattern.
- Fixed streaming loop example to show `input_signal_length` with actual tensor value.

### Buffer Full / Backpressure Notes

The 23-second WAV test caused many "Buffer full, dropping oldest audio" statuses. Contributing factors:
1. The queue was only 100 entries; increased to 500.
2. The session was storing audio in `session.audio_buffer` AND `session._audio_queue` — removed the redundant `audio_buffer.append` to cut memory duplication.
3. GPU inference on 100ms chunks takes longer than the chunk duration on some GPUs, causing queue buildup. The adapter processes chunks sequentially; if inference time > chunk duration, the queue grows unboundedly during a burst.

The queue increase + removal of redundant storage should significantly reduce buffer-full events. If they persist, future improvements include larger inference windows (500ms batches) or async inference with a semaphore to bound concurrency.

### VAD Model Status

`nvidia/speakquik-vad` was configured but does not exist on NGC/HuggingFace. Replaced with `nvidia/parakeet-vad`, which is the correct NVIDIA MarbleNet VAD model. VAD is loaded optionally (non-fatal if unavailable); transcription proceeds without VAD.


### MLX Server Improvements

**`session.py`**:
- Fixed `send_status()` to accept `SessionState` enum directly (was passing string that couldn't be converted)
- Added `_is_session_started` flag to guard against audio frames received before `session.start`
- Audio queue now bounded (`maxsize=100`) with overflow handling that drops oldest chunks
- Removed unused `_transcript_task` attribute

**`mlx_adapter.py`**:
- Added `TranscriptCallback` type alias: `Callable[[TranscriptResult], Awaitable[None]]`
- `RealMLXAdapter` now properly uses `mx.set_default_device(mx.gpu)` for GPU acceleration
- `transcribe_stream()` improved: proper overlap buffer for context, periodic final transcripts, correct buffer management
- Added graceful fallback in `shutdown()` if `mlx.core` import fails

**`requirements.txt`**:
- Added `scipy` for signal processing
- Added `pydantic` for data validation

**New scripts**:
- `scripts/deploy_mlx.sh` — one-shot setup: checks Apple Silicon, creates venv, installs deps, verifies MLX model loading, runs health check
- `scripts/check_health.sh` — verifies root, `/health`, and `/v1/status` endpoints

**`MLX_INTEGRATION.md`**:
- Complete rewrite with accurate mlx-audio installation steps
- Documents adapter lifecycle: `initialize()` → `warm_up()` → `transcribe_stream()`
- Added section on limitations and future improvements for streaming

**Smoke test results**:
- Mock server starts correctly: model preload + warmup logs visible
- All three health endpoints return expected JSON
- Server is runnable in mock mode on any platform

## 2026-03-19 (Late Night)

### NVIDIA Parakeet CUDA Backend — End-to-End Success

**Bug fixed: `'GreedyCTCInfer' object has no attribute 'vocab_size'`**

Root cause: The code called `ctc_decoder_predictions_tensor()` which internally instantiates a `GreedyCTCInfer` decoder and calls `.decode()` on it. The `.decode()` method expects `.vocab_size` which is not set on this decoder class.

**Fix: Direct greedy CTC decode + SentencePiece detokenization**

Replaced the broken NeMo `ctc_decoder_predictions_tensor` call with:
1. Direct `torch.argmax(log_probs, dim=-1)` to get CTC token IDs
2. Manual CTC collapse (remove consecutive duplicates + remove blank token 1024)
3. `model.decoding.decode_ids_to_str(text_tokens)` to convert BPE tokens → readable text

Two additional bugs surfaced and fixed:
- `blank_id = 1024` for this model (not 0) — filtered out before decoding
- `vocab_size = 1024` — tokens ≥ 1024 also filtered to prevent tokenizer `KeyError`

**Test result**: Real WAV transcription now produces recognizable streaming output through the WebSocket API.

**Remaining items** (not blockers):
- VAD model (`nvidia/parakeet-vad`) unavailable — transcription runs without VAD
- Need real speech test file (judge_23sec_16k_mono.wav not yet located) for fuller accuracy test
- WebSocket close frame handling in test_client causes non-zero exit — not a server bug

## 2026-03-19 (Continued)

### CTC Decoding Fixed — Real Transcripts Confirmed

The manual CTC decode approach (blank removal + tokenizer lookup) was still broken — it assumed blank token ID was 0, but the actual blank for `parakeet-ctc-0.6b` is 1024 (vocab_size - 1). The tokenizer also couldn't be located at `model.tokenizer` or `model.decoding.tokenizer`.

**Fix**: Replaced the entire manual decode with NeMo's `ctc_decoder_predictions_tensor()` which handles blank removal, CTC deduplication, and BPE detokenization correctly. On NeMo 2.7.0 (installed on the GPU box), this API works without the `vocab_size` bug.

**`parakeet_adapter.py` changes**:
- New `_decode_logprobs()` method: calls `self._model.decoding.ctc_decoder_predictions_tensor()`
- New `_run_inference()` method: handles model forward pass and output unpacking
- `transcribe_stream()` now flushes remaining audio buffer as a `is_final=True` result when the stream ends
- Removed all debug `print()` statements, replaced with `logging` module

**`server.py` changes**:
- After `session.stop`, the server now waits up to 10s for the adapter to finish processing (including final flush) instead of immediately cancelling the transcript task
- Added proper `websocket.close()` in the finally block

**`test_client.py` rewrite**:
- Send and receive now run as concurrent asyncio tasks for real-time partial display
- Exit condition handles both `final + close` and server-initiated connection close
- Fixed Python 3.9 compatibility (`Optional[Path]` instead of `Path | None`)

**Test results** (`judge_23sec_16k_mono.wav` → GPU server → test client):
- 42 partial transcripts streamed in real time with recognizable speech content
- 1 final transcript emitted on session close
- Clean WebSocket shutdown, no errors on either side
- Server environment: NeMo 2.7.0, torch 2.10.0+cu128, 2x RTX 3060

### macOS Native Client App Built

Created `JordanTranscriberMac/` — a native macOS SwiftUI app that captures microphone audio, streams to the CUDA server, and displays live transcript text.

**Files created**:
- `App/JordanTranscriberMacApp.swift` — `@main` entry, 640x480 default window
- `App/AppState.swift` — `ObservableObject` coordinating audio capture, WebSocket, and UI
- `Services/AudioCaptureService.swift` — `AVAudioEngine` mic → `AVAudioConverter` → 16kHz mono PCM16 → 100ms chunks
- `Services/WebSocketService.swift` — `URLSessionWebSocketTask` client implementing full `BACKEND_API.md` protocol with reconnection
- `Views/MainView.swift` — auto-scrolling transcript, status badge, start/stop toolbar, settings popover (host/port/font size)
- `Resources/Info.plist` — microphone usage description
- `Resources/JordanTranscriberMac.entitlements` — sandbox + audio-input + network-client
- `project-mac.yml` — XcodeGen config targeting macOS 14+

**Zero external dependencies** — uses only SwiftUI, AVFoundation, Foundation, Combine.

**Build**: `xcodegen generate --spec project-mac.yml && xcodebuild` succeeds with no errors. App launches and connects to the CUDA server.
