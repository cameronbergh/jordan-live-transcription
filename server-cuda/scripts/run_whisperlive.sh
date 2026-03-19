#!/bin/bash
set -e
cd "$(dirname "$0")/.."

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"

source venv-whisperlive/bin/activate

echo "Starting WhisperLive on GPU $CUDA_VISIBLE_DEVICES"
python3 ../WhisperLive/run_server.py \
    --port 9090 \
    --backend faster_whisper
