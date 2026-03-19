#!/bin/bash
#
# deploy_cuda.sh — One-shot setup and launch for the Jordan CUDA transcription server
# on a fresh Linux GPU machine (e.g. cameron-ms-7b17).
#
# Usage:
#   bash <(curl -sL https://.../deploy_cuda.sh)   # remote
#   bash deploy_cuda.sh                           # local
#
# Run as the user who will run the server (not root).
set -e

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$SERVER_DIR/venv"
LOG_FILE="$SERVER_DIR/deploy_$(date +%Y%m%d_%H%M%S).log"

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
DRY_RUN=false
SKIP_NEMO=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)   DRY_RUN=true; shift ;;
    --skip-nemo) SKIP_NEMO=true; shift ;;
    --force)     FORCE=true; shift ;;
    *)           echo "Unknown option: $1"; exit 1 ;;
  esac
done

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

check() {
  local cmd="$1"; shift
  if ! command -v "$cmd" &>/dev/null; then
    log "ERROR: '$cmd' not found. $*"
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
log "=== Jordan CUDA Server Deployment ==="

if [[ "$EUID" -eq 0 && "$DRY_RUN" != "true" ]]; then
  log "WARNING: Running as root. Prefer a regular user with CUDA access."
fi

check python3 "Python 3 required"
check pip3 "pip3 required"

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
log "Python version: $PYTHON_VERSION"

# ---------------------------------------------------------------------------
# CUDA check
# ---------------------------------------------------------------------------
if python3 -c 'import torch; assert torch.cuda.is_available()' 2>/dev/null; then
  GPU_COUNT=$(python3 -c 'import torch; print(torch.cuda.device_count())')
  GPU_NAME=$(python3 -c 'import torch; print(torch.cuda.get_device_name(0))')
  log "CUDA available: YES ($GPU_COUNT GPU(s): $GPU_NAME)"
else
  log "WARNING: CUDA not available or torch not installed."
  log "Install CUDA + torch before running with real Parakeet, or use MOCK_PARAKEET=true."
fi

# ---------------------------------------------------------------------------
# Virtual environment
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would create venv at $VENV_DIR"
else
  if [[ -d "$VENV_DIR" && "$FORCE" != "true" ]]; then
    log "Virtual environment already exists at $VENV_DIR (use --force to recreate)"
  else
    log "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    log "Virtual environment created."
  fi
  source "$VENV_DIR/bin/activate"
fi

# ---------------------------------------------------------------------------
# Core Python dependencies
# ---------------------------------------------------------------------------
log "Installing core Python dependencies..."
if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would pip install: $(grep -v '^#' "$SERVER_DIR/requirements.txt" | grep -v '^$' | tr '\n' ' ')"
else
  pip install --upgrade pip setuptools wheel
  pip install -r "$SERVER_DIR/requirements.txt"
fi

# ---------------------------------------------------------------------------
# PyTorch with CUDA (if CUDA is available on the host)
# ---------------------------------------------------------------------------
if python3 -c 'import torch; exit(0 if torch.cuda.is_available() else 1)' 2>/dev/null; then
  log "torch with CUDA already installed."
elif [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would install torch with CUDA support"
else
  log "Installing PyTorch with CUDA 12.x support..."
  pip install torch --index-url https://download.pytorch.org/whl/cu121
fi

# ---------------------------------------------------------------------------
# NeMo / Parakeet
# ---------------------------------------------------------------------------
if [[ "$SKIP_NEMO" == "true" ]]; then
  log "Skipping NeMo installation (--skip-nemo)"
elif [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would install: nemo-toolkit[asr]"
else
  if python3 -c 'import nemo.collections.asr' 2>/dev/null; then
    log "NeMo ASR already installed."
  else
    log "Installing NeMo Toolkit with ASR support..."
    pip install nemo-toolkit[asr]
  fi
fi

# ---------------------------------------------------------------------------
# Verify Parakeet model loads (dry run or real)
# ---------------------------------------------------------------------------
if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would verify Parakeet model loading"
elif python3 -c 'import nemo.collections.asr.models' 2>/dev/null; then
  log "Verifying Parakeet model download (first run downloads ~2GB)..."
  if python3 - <<'VERIFY_SCRIPT'
import sys
try:
    from nemo.collections.asr.models import EncDecCTCModel
    model = EncDecCTCModel.from_pretrained(model_name="nvidia/parakeet-qn-params")
    print(f"SUCCESS: Model loaded: {type(model).__name__}", file=sys.stderr)
except Exception as e:
    print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
VERIFY_SCRIPT
  then
    log "Parakeet model verified."
  else
    log "WARNING: Parakeet model verification failed. Check network / CUDA."
  fi
else
  log "Skipping Parakeet verification (NeMo not installed)."
fi

# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
log "Running server health check..."
export MOCK_PARAKEET=true
export HOST=0.0.0.0
export PORT=8765

if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would start server and check health endpoints"
else
  # Start server in background, check health, then stop
  python3 "$SERVER_DIR/server.py" &
  SERVER_PID=$!
  sleep 5

  if curl -s http://localhost:8765/health | grep -q "healthy"; then
    log "Health check PASSED"
  else
    log "Health check FAILED — check logs above"
    kill $SERVER_PID 2>/dev/null || true
    exit 1
  fi

  if curl -s http://localhost:8765/v1/status | grep -q "parakeet"; then
    log "Status endpoint PASSED"
  else
    log "Status endpoint FAILED"
  fi

  kill $SERVER_PID 2>/dev/null || true
  sleep 1
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
log ""
log "=== Deployment Complete ==="
log ""
log "To start the server:"
log "  source $VENV_DIR/bin/activate"
log "  cd $SERVER_DIR"
log "  MOCK_PARAKEET=false python server.py"
log ""
log "Or use the convenience script:"
log "  bash $SERVER_DIR/scripts/run_server.sh"
log ""
log "Endpoints:"
log "  Health:  http://localhost:8765/health"
log "  Status:  http://localhost:8765/v1/status"
log "  WebSocket: ws://localhost:8765/v1/transcription/stream"
log ""
if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN complete — no changes made."
fi
log "Full log: $LOG_FILE"
