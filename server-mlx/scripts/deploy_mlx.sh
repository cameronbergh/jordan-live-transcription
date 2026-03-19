#!/bin/bash
#
# deploy_mlx.sh — One-shot setup and launch for the Jordan MLX transcription server
# on Apple Silicon (M-series Mac).
#
# Usage:
#   bash deploy_mlx.sh                # fresh install + verify
#   bash deploy_mlx.sh --dry-run     # show what would be done
#   bash deploy_mlx.sh --skip-mlx     # skip MLX install, use mock adapter
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="$SCRIPT_DIR"
LOG_FILE="$SERVER_DIR/deploy_mlx_$(date +%Y%m%d_%H%M%S).log"

DRY_RUN=false
SKIP_MLX=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)   DRY_RUN=true; shift ;;
    --skip-mlx)  SKIP_MLX=true; shift ;;
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

log "=== Jordan MLX Server Deployment (Apple Silicon) ==="

check python3 "Python 3 required"

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
log "Python version: $PYTHON_VERSION"

if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would create venv at $SERVER_DIR/venv"
else
  VENV_DIR="$SERVER_DIR/venv"
  if [[ -d "$VENV_DIR" && "$FORCE" != "true" ]]; then
    log "Virtual environment already exists at $VENV_DIR (use --force to recreate)"
  else
    log "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    log "Virtual environment created."
  fi
  source "$VENV_DIR/bin/activate"
fi

log "Installing core Python dependencies..."
if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would pip install: $(grep -v '^#' "$SERVER_DIR/requirements.txt" | grep -v '^$' | tr '\n' ' ')"
else
  pip install --upgrade pip setuptools wheel
  pip install -r "$SERVER_DIR/requirements.txt"
fi

if [[ "$SKIP_MLX" == "true" ]]; then
  log "Skipping MLX installation (--skip-mlx)"
elif [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would install mlx and mlx-audio"
else
  if python3 -c 'import mlx' 2>/dev/null; then
    log "MLX already installed."
  else
    log "Installing MLX..."
    pip install mlx
  fi

  if python3 -c 'from mlx_audio.mlx_whisper import load_whisper_model' 2>/dev/null; then
    log "mlx-audio already installed."
  else
    log "Installing mlx-audio..."
    pip install mlx-audio
  fi
fi

if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would verify MLX model loading"
elif ! python3 -c 'import mlx' 2>/dev/null; then
  log "WARNING: MLX not available. Install with: pip install mlx"
  log "Will run in MOCK_MLX=true mode."
elif ! python3 -c 'from mlx_audio.mlx_whisper import load_whisper_model' 2>/dev/null; then
  log "WARNING: mlx-audio not available. Will run in MOCK_MLX=true mode."
else
  log "Verifying MLX Whisper model download (first run downloads ~500MB-3GB)..."
  MLX_MODEL="${MLX_MODEL:-mlx-community/whisper-base-mlx}"
  if python3 - <<VERIFY_SCRIPT 2>&1
import sys
try:
    from mlx_audio.mlx_whisper import load_whisper_model
    model = load_whisper_model("$MLX_MODEL")
    print(f"SUCCESS: Model loaded: $MLX_MODEL", file=sys.stderr)
except Exception as e:
    print(f"FAIL: {e}", file=sys.stderr)
    sys.exit(1)
VERIFY_SCRIPT
  then
    log "MLX model verified: $MLX_MODEL"
  else
    log "WARNING: MLX model verification failed. Check network."
  fi
fi

log "Running server health check..."
export MOCK_MLX="${MOCK_MLX:-true}"
export HOST="0.0.0.0"
export PORT="8765"

if [[ "$DRY_RUN" == "true" ]]; then
  log "[DRY RUN] Would start server and check health endpoints"
else
  python3 "$SERVER_DIR/server.py" &
  SERVER_PID=$!
  sleep 5

  if curl -s http://localhost:8765/health 2>/dev/null | grep -q "healthy"; then
    log "Health check PASSED"
  else
    log "Health check FAILED — check logs above"
    kill $SERVER_PID 2>/dev/null || true
    exit 1
  fi

  if curl -s http://localhost:8765/v1/status 2>/dev/null | grep -q "mlx"; then
    log "Status endpoint PASSED"
  else
    log "Status endpoint FAILED"
  fi

  kill $SERVER_PID 2>/dev/null || true
  sleep 1
fi

log ""
log "=== Deployment Complete ==="
log ""
log "To start the server (mock mode, no MLX required):"
log "  cd $SERVER_DIR"
log "  MOCK_MLX=true python3 server.py"
log ""
log "To start with real MLX Whisper (Apple Silicon required):"
log "  cd $SERVER_DIR"
log "  MOCK_MLX=false MLX_MODEL=\"mlx-community/whisper-base-mlx\" python3 server.py"
log ""
log "Or use the convenience script:"
log "  bash $SERVER_DIR/scripts/run_server.sh"
log ""
log "Endpoints:"
log "  Health:     http://localhost:8765/health"
log "  Status:     http://localhost:8765/v1/status"
log "  WebSocket:  ws://localhost:8765/v1/transcription/stream"
log ""
if [[ "$DRY_RUN" == "true" ]]; then
  log "DRY RUN complete — no changes made."
fi
log "Full log: $LOG_FILE"
