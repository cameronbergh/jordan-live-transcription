# Jordan Live Transcription — CUDA Backend Server

WebSocket server for live speech-to-text transcription, designed to run on a Linux GPU machine
with NVIDIA Parakeet as the speech recognition engine.

## Quick Start

### 1. On the GPU Machine

```bash
cd server-cuda

# Install system + Python dependencies (one-time setup)
bash scripts/deploy_cuda.sh

# Activate virtual environment
source venv/bin/activate

# Run the server
bash scripts/run_server.sh
```

Or manually:

```bash
pip install -r requirements.txt
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install nemo-toolkit[asr]
MOCK_PARAKEET=false python server.py
```

### 2. Verify

```bash
# Check server is up
bash scripts/check_health.sh

# Test with mock (no GPU needed)
python scripts/test_client.py --host localhost --port 8765
```

Server binds to `0.0.0.0:8765` by default.

---

## Architecture

```
iPhone client  <--WebSocket-->  CUDA server  <-->  NVIDIA Parakeet (NeMo)
                                        |
                                   session manager
                                   audio buffer
                                   parakeet adapter
```

### Key Components

| File | Purpose |
|------|---------|
| `server.py` | FastAPI app + WebSocket endpoint, lifespan lifecycle (model preload/warmup) |
| `session.py` | Per-connection session: state machine, audio queue, message dispatch |
| `parakeet_adapter.py` | `ParakeetAdapter` ABC + `MockParakeetAdapter` + `RealParakeetAdapter` |
| `audio_buffer.py` | Ring buffer for assembling PCM16 chunks |
| `protocol.py` | JSON message serialization matching `BACKEND_API.md` |
| `config.py` | Environment-variable configuration |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8765` | WebSocket port |
| `PARAKEET_MODEL` | `nvidia/parakeet-qn-params` | NeMo model name |
| `GPU_DEVICE_ID` | `0` | CUDA device index |
| `VAD_MODEL` | `nvidia/parakeet-vad` | MarbleNet VAD model |
| `MOCK_PARAKEET` | `true` | Set `false` for real GPU inference |
| `LOG_TRANSCRIPTS` | `false` | Enable server-side transcript logging |
| `SERVER_HOSTNAME` | `cameron-ms-7b17` | Reported in `session.started` messages |

---

## Model Preload + Warmup

The server loads the Parakeet model **at startup** (not on first request):

1. `adapter.initialize()` — loads model from NeMo onto GPU (~30-60s)
2. `adapter.warm_up()` — runs dummy inference to compile GPU kernels (~5-10s)
3. Server accepts connections

This ensures first real audio session has no cold-start delay.

---

## Protocol

Full wire protocol documented in `BACKEND_API.md` at repo root.

### Session Flow

```
1. Client connects to /v1/transcription/stream
2. Client sends session.start (JSON)
3. Server sends session.started (JSON) + status (listening)
4. Client streams binary PCM16 16kHz mono audio chunks
5. Server sends transcript.partial / transcript.final events
6. Client sends session.stop (JSON) or disconnects
```

### Server Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Service info |
| `/health` | GET | Simple health check |
| `/v1/status` | GET | Detailed engine/adapter status |
| `/v1/transcription/stream` | WS | WebSocket streaming endpoint |

---

## Testing

### With Mock Adapter (no GPU needed)

```bash
MOCK_PARAKEET=true python server.py
python scripts/test_client.py --host localhost --port 8765
```

### With Real Parakeet

```bash
MOCK_PARAKEET=false python server.py
# In another terminal:
python scripts/test_client.py --host localhost --port 8765 --audio /path/to/audio.wav
```

### Health Checks

```bash
bash scripts/check_health.sh
```

---

## Deployment on `cameron-ms-7b17`

```bash
# SSH to the machine
ssh user@cameron-ms-7b17

# Clone or copy the server-cuda directory
cd ~/jordan-live-transcription-ios/server-cuda

# Run the deployment script (installs everything, verifies GPU)
bash scripts/deploy_cuda.sh

# Start the server
bash scripts/run_server.sh
```

---

## Privacy

- Raw audio is **not persisted** by default
- Transcript text is **not persisted** by default
- Set `LOG_TRANSCRIPTS=true` to enable server-side transcript logging

---

## Troubleshooting

**Server won't start with `MOCK_PARAKEET=false`**
- Verify CUDA: `python3 -c "import torch; print(torch.cuda.is_available())"`
- Verify NeMo: `python3 -c "from nemo.collections.asr.models import EncDecCTCModel"`

**Model download is slow**
- First run downloads ~2GB. Check network connectivity.
- Use `nvidia/parakeet-qn-params` (smaller) vs larger variants.

**CUDA out of memory**
- Reduce batch size or use a smaller Parakeet variant
- Check `GPU_DEVICE_ID` if using multi-GPU

---

## Project Structure

```
server-cuda/
  server.py              FastAPI + WebSocket entry point
  session.py             Per-connection session state machine
  parakeet_adapter.py    Adapter interface + mock + real implementation
  audio_buffer.py        Ring buffer for PCM audio chunks
  protocol.py            JSON message serialization
  config.py              Environment-variable configuration
  requirements.txt       Python dependencies
  README.md              This file
  PARAKEET_INTEGRATION.md  Detailed Parakeet setup guide
  scripts/
    run_server.sh         Convenience launch script
    deploy_cuda.sh       One-shot setup + health check script
    check_health.sh      Server health verification
    test_client.py        WebSocket test client
```
