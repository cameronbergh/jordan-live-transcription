#!/bin/bash
#
# run_vllm.sh — Start vLLM serving Voxtral Realtime 4B.
#
# By default uses cuda:1 so Parakeet can stay on cuda:0.
# Override with VLLM_GPU=0 if sharing a single GPU.
#
# Usage:
#   bash scripts/run_vllm.sh
#
set -e

cd "$(dirname "$0")/.."

VLLM_VENV_DIR="${VLLM_VENV_DIR:-$(pwd)/venv-vllm}"
VOXTRAL_MODEL="${VOXTRAL_MODEL:-mistralai/Voxtral-Mini-4B-Realtime-2602}"
VLLM_PORT="${VLLM_PORT:-8000}"
VLLM_GPU="${VLLM_GPU:-1}"

if [[ -d "$VLLM_VENV_DIR" ]]; then
  source "$VLLM_VENV_DIR/bin/activate"
fi

echo "============================================"
echo "Voxtral Realtime 4B — vLLM Server"
echo "============================================"
echo "  Model:      $VOXTRAL_MODEL"
echo "  Port:       $VLLM_PORT"
echo "  GPU:        cuda:$VLLM_GPU"
echo "  Endpoint:   ws://localhost:$VLLM_PORT/v1/realtime"
echo "============================================"
echo ""

export CUDA_VISIBLE_DEVICES="$VLLM_GPU"

exec vllm serve "$VOXTRAL_MODEL" \
  --enforce-eager \
  --port "$VLLM_PORT"
