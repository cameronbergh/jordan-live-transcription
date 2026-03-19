# NVIDIA Parakeet Integration Guide

## Overview

`parakeet_adapter.py` defines the interface between the WebSocket transcription server and
the NVIDIA Parakeet speech recognition runtime. This guide covers installation, configuration,
and the exact implementation surface that remains for live streaming Parakeet inference.

---

## What is NVIDIA Parakeet?

NVIDIA Parakeet is an open-source automatic speech recognition (ASR) model family developed by
NVIDIA, built on the FastConformer architecture. It is distributed via the
[NVIDIA NeMo Toolkit](https://github.com/NVIDIA/NeMo).

Available model sizes:
- **Parakeet-QN** (quantized, ~800M params) — single-GPU serving, good balance of speed/accuracy
- **Parakeet-TDT** (tightened, ~1.1B params) — higher accuracy, more VRAM required

---

## Hardware Requirements

| Component | Requirement |
|-----------|-------------|
| GPU | NVIDIA GPU with CUDA 11.8+ / CUDA 12.x |
| VRAM | 8GB+ for Parakeet-QN, 16GB+ for larger variants |
| cuDNN | 8.9+ recommended |
| RAM | 16GB+ host RAM |
| Tested | 2x RTX 3060 12GB on `cameron-ms-7b17` |

---

## Installation

### 1. System Dependencies

```bash
# CUDA 12.x (adjust for your distribution)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get install cuda-runtime-12-8 cuda-toolkit-12-8
```

### 2. Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
```

### 3. NeMo Toolkit

```bash
pip install nemo-toolkit[asr]
```

This installs NeMo with ASR support, including Parakeet models and the VAD (MarbleNet) model.

### 4. Verify Installation

```python
python -c "
import torch
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA devices: {torch.cuda.device_count()}')

from nemo.collections.asr.models import EncDecCTCModel
model = EncDecCTCModel.from_pretrained(model_name='nvidia/parakeet-qn-params')
print(f'Model loaded: {type(model).__name__}')
print(f'Model device: {next(model.parameters()).device}')
"
```

Expected output on a working GPU machine:
```
CUDA available: True
CUDA devices: 2
Model loaded: EncDecCTCModel
Model device: cuda:0
```

---

## Server Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `PARAKEET_MODEL` | `nvidia/parakeet-qn-params` | NeMo model name |
| `GPU_DEVICE_ID` | `0` | CUDA device index (0 or 1 for multi-GPU) |
| `VAD_MODEL` | `nvidia/parakeet-vad` | MarbleNet VAD model name |
| `CHUNK_MS` | `100` | Audio chunk duration in ms |
| `MOCK_PARAKEET` | `true` | Set to `false` to use real Parakeet |
| `LOG_TRANSCRIPTS` | `false` | Enable server-side transcript logging |

---

## Adapter Lifecycle (Model Preload + Warmup)

The server initializes the Parakeet adapter during the FastAPI lifespan startup (not on first request):

```
server startup
  └── adapter.initialize(model_name)     # load model to GPU, takes ~30-60s
  └── adapter.warm_up()                 # run dummy inference, compile kernels, ~5-10s
  └── app.state.adapter = adapter
  └── server accepts WebSocket connections

server shutdown
  └── adapter.shutdown()               # free GPU memory
```

This is implemented in `server.py` `lifespan()`.

---

## Adapter Interface

The `ParakeetAdapter` abstract class (`parakeet_adapter.py`) defines the contract:

```python
class ParakeetAdapter(ABC):
    async def initialize(self, model_name: str) -> None:
        """Load model onto GPU. Called once at server startup."""

    async def warm_up(self) -> None:
        """Run dummy inference to warm up GPU kernels. Called once at startup."""

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: Callable[[TranscriptResult], Awaitable[None]],
    ) -> None:
        """Consume audio chunks, emit transcript results via callback."""

    async def shutdown(self) -> None:
        """Release model resources. Called at server shutdown."""
```

---

## RealParakeetAdapter Implementation Notes

The `RealParakeetAdapter` in `parakeet_adapter.py` is the production implementation. Key details:

### Model Loading

```python
self._model = EncDecCTCModel.from_pretrained(model_name=model_name)
self._model = self._model.to(self._device)  # cuda:N
self._model.eval()
```

### VAD (Voice Activity Detection)

```python
self._vad_model = EncDecClassificationModel.from_pretrained(
    model_name=config.vad_model
)
self._vad_model = self._vad_model.to(self._device)
self._vad_model.eval()
```

VAD is optional — if it fails to load, the server starts without it and logs a warning.

### Warm-up Inference

```python
dummy_audio = torch.randn(1, self._sample_rate, dtype=torch.float32, device=self._device)
dummy_length = torch.tensor([self._sample_rate], dtype=torch.long, device=self._device)
with torch.no_grad():
    self._model(input_signal=dummy_audio, input_signal_length=dummy_length)
```

**Important**: `input_signal` and `input_signal_length` must **both** be provided together. Passing `input_signal_length=None` triggers NeMo's mutual exclusivity check and raises a `ValueError`. The model internally runs the preprocessor to convert the raw waveform into mel-spectrograms before passing to the encoder.

### Streaming Loop

The streaming loop consumes audio chunks from the queue, accumulates them in a buffer, and runs inference when enough samples are available:

```python
buffer = b""
min_samples = int(0.1 * self._sample_rate)  # 100ms @ 16kHz

async for chunk in audio_chunks:
    buffer += chunk
    samples = np.frombuffer(buffer, dtype=np.int16)

    if len(samples) >= min_samples:
        audio_tensor = (
            torch.from_numpy(samples.astype(np.float32) / 32768.0)
            .unsqueeze(0)
            .to(self._device)
        )
        audio_length = torch.tensor([samples.shape[0]], dtype=torch.long, device=self._device)

        with torch.no_grad():
            model_output = self._model(input_signal=audio_tensor, input_signal_length=audio_length)

        if isinstance(model_output, tuple):
            logits = model_output[0]
        elif hasattr(model_output, "log_softmax"):
            logits = model_output.log_softmax(dim=-1)
        else:
            logits = model_output

        if hasattr(logits, "transpose"):
            logits = logits.transpose(0, 1)

        predicted_ids = torch.argmax(logits, dim=-1)
        transcript_text = self._model.decoding.decode(predicted_ids)

        # emit result via transcript_callback

        # Keep trailing context (last min_samples for next window overlap)
        kept_samples = max(0, len(samples) - min_samples)
        buffer = buffer[-kept_samples * 2 :]  # keep last N samples as int16 bytes
```

**Key**: Always pass `input_signal_length` as a tensor containing the actual sample count. The NeMo CTC model requires both `input_signal` and `input_signal_length` to be provided together; they are mutually exclusive with `processed_signal`/`processed_signal_len`.

### Trailing Context

After each inference, the last `min_samples` samples are kept in the buffer to maintain context for the next window:
```python
kept_samples = max(0, len(samples) - min_samples)
buffer = buffer[-kept_samples * 2:]  # keep last N samples as int16 bytes
```

---

## Known Issues and Fixes

### `decode_ids_to_str` returning nested list structures (list vs int comparison error)

**Symptom**: Runtime error `"not supported between instances of list and int"` during transcription.

**Root cause**: NeMo's `decode_ids_to_str` can return nested list structures depending on model version/configuration (e.g., `[['transcript']]` instead of `['transcript']`). Direct indexing `decoded[0]` then yields a list instead of a string, causing downstream comparison errors.

**Fix** (`parakeet_adapter.py`): Normalize the decoded output before use:
```python
decoded = self._model.decoding.decode_ids_to_str(greedy_predictions)
while isinstance(decoded, list) and len(decoded) > 0 and isinstance(decoded[0], list):
    decoded = [item for sublist in decoded for item in sublist]
if isinstance(decoded, list) and len(decoded) > 0:
    result_item = decoded[0]
    if isinstance(result_item, str):
        transcript_text = result_item.strip()
    elif hasattr(result_item, "text"):
        transcript_text = str(result_item.text).strip()
```

---

## What Remains for Full Live Streaming

The `RealParakeetAdapter` is now a functional production-ready implementation. Remaining refinement items:

1. **VAD integration** — VAD is loaded but not yet wired into the transcription loop. Adding VAD would improve accuracy by only running ASR on speech regions, and reduce false positives on silence.

2. **Streaming decoder** — Parakeet CTC currently runs on fixed-window chunks. For lower latency, consider incremental/streaming decode.

3. **Overlap strategy** — The 100ms buffer shift works for MVP. Better overlap (e.g., 50% overlap with 50ms shift) reduces word-boundary artifacts.

4. **Timestamps** — The current implementation estimates `start_ms` from wall-clock time. Parakeet CTC doesn't provide word-level timestamps natively; VAD + chunk indexing can approximate this.

5. **Multi-GPU** — The current adapter targets a single GPU (`GPU_DEVICE_ID`). For multi-GPU serving, session affinity or a load-balancing wrapper is needed.

---

## Running the Server

```bash
# From the server-cuda directory
cd server-cuda

# Install dependencies
pip install -r requirements.txt

# Install NeMo (one-time setup on the GPU machine)
pip install nemo-toolkit[asr]

# Run with real Parakeet
export MOCK_PARAKEET=false
export GPU_DEVICE_ID=0
python server.py
```

Or use the convenience script:
```bash
bash scripts/run_server.sh
```

---

## Verifying the Installation

```bash
# Check health endpoint
curl http://localhost:8765/health

# Check detailed status
curl http://localhost:8765/v1/status

# Run the test client
python scripts/test_client.py --host localhost --port 8765
```

Expected status output:
```json
{
  "engine": "parakeet",
  "adapter": "RealParakeetAdapter",
  "model": "nvidia/parakeet-qn-params",
  "gpu_device": 0,
  "mock": false
}
```
