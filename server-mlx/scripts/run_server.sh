#!/bin/bash
set -e

cd "$(dirname "$0")/.."

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8765}"
export MOCK_MLX="${MOCK_MLX:-true}"
export MLX_MODEL="${MLX_MODEL:-mlx-community/whisper-large-v3-mlx}"
export SERVER_HOSTNAME="${SERVER_HOSTNAME:-mlx-server}"

echo "Starting MLX Transcription Server"
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Mock: $MOCK_MLX"
echo "  Model: $MLX_MODEL"

pip install -q -r requirements.txt

if [ "$MOCK_MLX" != "true" ]; then
    pip install -q mlx-audio
fi

python server.py