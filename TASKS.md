# Tasks

## Now
- [x] Create initial iOS / SwiftUI app scaffold
- [x] Build main live transcription screen
- [x] Add microphone permission flow
- [x] Add privacy blackout overlay + shake detection
- [x] Add settings screen with logging toggle
- [x] Keep this work inside the existing Jordan project repo
- [x] Choose Linux GPU backend direction instead of MLX Audio Swift / llama.cpp
- [x] Define backend streaming API shape (audio in, transcript out)
- [x] Build first backend transcription server prototype on Linux
- [x] Integrate the regular NVIDIA Parakeet stack into the backend (adapter boundary + mock; real integration documented)
- [x] Build separate MLX backend track for Apple Silicon (`server-mlx/`)
- [x] Strengthen CUDA server: session state machine, async callback, adapter lifecycle, scripts, docs
- [x] Add deploy_cuda.sh and check_health.sh scripts for GPU machine deployment
- [x] Verify mock server startup and protocol end-to-end (session → transcript → stop)
- [x] Strengthen MLX server: session state machine fix, audio queue bounds, adapter fixes, scripts
- [x] Add deploy_mlx.sh and check_health.sh scripts for Apple Silicon setup
- [x] Ensure backend servers preload and warm their model at startup (done in server lifespan)
- [x] Fix CTC decoding in RealParakeetAdapter (use `ctc_decoder_predictions_tensor`)
- [x] Add final transcript flush at end of audio stream
- [x] Fix test_client.py for concurrent send/receive and robust exit
- [x] Verify real end-to-end transcription on GPU box with judge_23sec WAV file
- [x] Build macOS native client app (`JordanTranscriberMac/`) with mic capture, WebSocket streaming, live transcript display
- [x] ~~Add Voxtral Realtime 4B as second transcription engine~~ (removed — vLLM incompatible)
- [x] Clone WhisperLive and integrate as second transcription engine
- [x] Create whisperlive_adapter.py, deploy_whisperlive.sh, run_whisperlive.sh
- [x] Deploy WhisperLive to GPU box and verify end-to-end transcription with large-v3-turbo
- [ ] Lock primary host choice between the dual-3060 box and dual-2080 Ti box
- [ ] Refactor iOS client transcription layer to talk to backend service

## Next
- [x] Choose transport for streaming (WebSocket — confirmed)
- [x] Decide audio chunking / encoding format (PCM16 mono 16kHz — confirmed)
- [x] Determine whether transcript should show partial text, finalized text, or both (both — partials + finals)
- [ ] Evaluate scrollback for current session transcript
- [ ] Add lightweight local transcript persistence behind logging toggle
- [ ] Add haptics when blackout toggles
- [ ] Complete iOS client to WebSocket backend integration
- [ ] Improve streaming transcript quality (larger inference windows, sliding window with overlap)
- [ ] Compare Parakeet vs WhisperLive transcription quality and latency on same audio

## Blockers
- `RealParakeetAdapter` CTC decoding — **FIXED**: Replaced broken manual decode with NeMo's `ctc_decoder_predictions_tensor()`. End-to-end real transcription confirmed working on `nvidia/parakeet-ctc-0.6b` via GPU box.
- `RealParakeetAdapter` `input_signal_length` — **FIXED**: Model now receives proper tensor for both warm-up and streaming inference.
- Server session cleanup — **FIXED**: `server.py` now waits for the adapter to flush final transcripts before closing (was cancelling the task immediately).
- Voxtral vLLM incompatibility — **RESOLVED**: Removed Voxtral entirely. Replaced with WhisperLive (`large-v3-turbo` via `faster-whisper`). End-to-end streaming confirmed working.
- Remaining `RealParakeetAdapter` items: VAD not yet wired into transcription loop; streaming decoder could use larger batches; overlap strategy; word-level timestamps.
- `RealMLXAdapter` is functional but limited: no word-level timestamps, no VAD integration. Documented in `server-mlx/MLX_INTEGRATION.md`.

## Later
- [ ] Adjustable text size (partially done via macOS settings popover; iOS needs UI)
- [ ] Copy transcript
- [ ] Compare Parakeet vs WhisperLive quality/latency side-by-side
- [ ] Export transcript
- [ ] Session history
- [ ] Battery / thermal profiling
- [ ] Improve partial transcript coherence (accumulate longer audio windows)
