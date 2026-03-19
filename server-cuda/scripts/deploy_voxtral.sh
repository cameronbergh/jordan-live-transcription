#!/bin/bash
#
# deploy_voxtral.sh — Install vLLM and set up Voxtral Realtime 4B serving
# on the GPU box alongside the existing Jordan CUDA server.
#
# Prerequisites:
#   - CUDA-capable GPU with >= 12GB VRAM (one RTX 3060 is sufficient)
#   - Python 3.10+ with CUDA-enabled torch already installed
#   - The Parakeet venv at ../venv/ (created by deploy_cuda.sh)
#
# Usage:
#   bash scripts/deploy_voxtral.sh              # full install
#   bash scripts/deploy_voxtral.sh --dry-run    # preview only
#   bash scripts/deploy_voxtral.sh --skip-download  # skip model pre-download
#
set -e

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLLM_VENV_DIR="$SERVER_DIR/venv-vllm"
LOG_FILE="$SERVER_DIR/deploy_voxtral_$(date +%Y%m%d_%H%M%S).log"
VOXTRAL_MODEL="${VOXTRAL_MODEL:-mistralai/Voxtral-Mini-4B-Realtime-2602}"
VLLM_PORT="${VLLM_PORT:-8000}"
VLLM_GPU="${VLLM_GPU:-1}"

DRY_RUN=false
SKIP_DOWNLOAD=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)         DRY_RUN=true; shift ;;
    --skip-download)   SKIP_DOWNLOAD=true; shift ;;
    *)                 echo "Unknown option: $1"; exit 1 ;;
  esac
done

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Voxtral Realtime 4B Deployment ==="
log "Model:    $VOXTRAL_MODEL"
log "vLLM GPU: cuda:$VLLM_GPU"
log "vLLM port: $VLLM_PORT"
log "Venv:     $VLLM_VENV_DIR"

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
if ! command -v python3 &>/dev/null; then
  log "ERROR: python3 not found"
  exit 1
fi

if ! python3 -c 'import torch; assert torch.cuda.is_available()' 2>/dev/null; then
  log "WARNING: CUDA not available. vLLM requires CUDA."
fi

GPU_COUNT=$(python3 -c 'import torch; print(torch.cuda.device_count())' 2>/dev/null || echo "0")
log "GPUs detected: $GPU_COUNT"

if [[ "$GPU_COUNT" -lt 2 ]]; then
  log "WARNING: Only $GPU_COUNT GPU(s) detected. Parakeet uses cuda:0; vLLM defaults to cuda:$VLLM_GPU."
  log "You may need to set VLLM_GPU=0 if only one GPU is available (will share with Parakeet)."
fi

# ---------------------------------------------------------------------------
# Create separate venv for vLLM (avoids NeMo dependency conflicts)
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would create venv at $VLLM_VENV_DIR"
else
  if [[ -d "$VLLM_VENV_DIR" ]]; then
    log "vLLM venv already exists at $VLLM_VENV_DIR"
  else
    log "Creating vLLM virtual environment..."
    python3 -m venv "$VLLM_VENV_DIR"
  fi
  source "$VLLM_VENV_DIR/bin/activate"
fi

# ---------------------------------------------------------------------------
# Install vLLM + audio deps
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would install: vllm, soxr, librosa, soundfile"
else
  log "Installing vLLM..."
  pip install --upgrade pip setuptools wheel
  pip install vllm soxr librosa soundfile
fi

# ---------------------------------------------------------------------------
# Pre-download model weights (~9GB)
# ---------------------------------------------------------------------------
if [[ "$SKIP_DOWNLOAD" == "true" ]]; then
  log "Skipping model pre-download (--skip-download)"
elif [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would pre-download $VOXTRAL_MODEL"
else
  log "Pre-downloading Voxtral model weights (first run downloads ~9GB)..."
  python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('$VOXTRAL_MODEL')
print('Model downloaded successfully')
" || log "WARNING: Model pre-download failed. vLLM will download on first serve."
fi

# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would verify vLLM import"
else
  if python3 -c 'import vllm; print(f"vLLM version: {vllm.__version__}")' 2>/dev/null; then
    log "vLLM import OK"
  else
    log "WARNING: vLLM import failed — check installation"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log ""
log "=== Voxtral Deployment Complete ==="
log ""
log "To start vLLM serving Voxtral:"
log "  source $VLLM_VENV_DIR/bin/activate"
log "  CUDA_VISIBLE_DEVICES=$VLLM_GPU vllm serve $VOXTRAL_MODEL --enforce-eager --port $VLLM_PORT"
log ""
log "Or use the convenience script:"
log "  bash $SERVER_DIR/scripts/run_vllm.sh"
log ""
log "Then start the Jordan server (in a separate terminal) with:"
log "  source $SERVER_DIR/venv/bin/activate"
log "  VLLM_HOST=localhost VLLM_PORT=$VLLM_PORT MOCK_PARAKEET=false python3 server.py"
log ""
log "The client can select 'Voxtral Realtime 4B (Local GPU)' in the engine picker."
log ""
log "Full log: $LOG_FILE"
