#!/bin/bash
#
# run_server.sh — Convenience launcher for the Jordan CUDA transcription server.
#
# Usage:
#   bash scripts/run_server.sh
#
set -e

cd "$(dirname "$0")/.."

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8765}"
export MOCK_PARAKEET="${MOCK_PARAKEET:-true}"
export LOG_TRANSCRIPTS="${LOG_TRANSCRIPTS:-false}"
export SERVER_HOSTNAME="${SERVER_HOSTNAME:-cameron-ms-7b17}"
export GPU_DEVICE_ID="${GPU_DEVICE_ID:-0}"
export PARAKEET_MODEL="${PARAKEET_MODEL:-nvidia/parakeet-qn-params}"

echo "============================================"
echo "Jordan CUDA Transcription Server"
echo "============================================"
echo "  Host:            $HOST"
echo "  Port:            $PORT"
echo "  GPU device:      cuda:$GPU_DEVICE_ID"
echo "  Parakeet model:  $PARAKEET_MODEL"
echo "  Mock mode:       $MOCK_PARAKEET"
echo "  Server hostname: $SERVER_HOSTNAME"
echo "  Log transcripts: $LOG_TRANSCRIPTS"
echo "============================================"
echo ""

if [[ "$MOCK_PARAKEET" != "true" ]]; then
  if python3 -c 'import torch; assert torch.cuda.is_available()' 2>/dev/null; then
    GPU_NAME=$(python3 -c 'import torch; print(torch.cuda.get_device_name(0))')
    echo "GPU detected: $GPU_NAME"
  else
    echo "WARNING: MOCK_PARAKEET=false but CUDA not available."
    echo "Set MOCK_PARAKEET=true for testing without GPU."
    echo ""
  fi
fi

python3 server.py
