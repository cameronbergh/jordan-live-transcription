#!/bin/bash
#
# check_health.sh — Verify the MLX transcription server is healthy
#
# Usage:
#   bash check_health.sh              # check default localhost:8765
#   HOST=192.168.1.100 PORT=8766 bash check_health.sh
#
set -e

HOST="${HOST:-localhost}"
PORT="${PORT:-8765}"

check() {
  local url="$1"
  local name="$2"
  echo -n "  $name... "
  if curl -s --max-time 5 "$url" | grep -q "healthy\|mlx"; then
    echo "OK"
    return 0
  else
    echo "FAILED"
    return 1
  fi
}

echo "Checking MLX server at $HOST:$PORT..."

PASS=0
FAIL=0

if check "http://$HOST:$PORT/" "Root endpoint"; then ((PASS++)); else ((FAIL++)); fi
if check "http://$HOST:$PORT/health" "Health endpoint"; then ((PASS++)); else ((FAIL++)); fi
if check "http://$HOST:$PORT/v1/status" "Status endpoint"; then ((PASS++)); else ((FAIL++)); fi

echo ""
echo "Results: $PASS passed, $FAIL failed"

if [[ "$FAIL" -gt 0 ]]; then
  echo "Server may not be running. Start with:"
  echo "  cd $(dirname "$0")/.."
  echo "  MOCK_MLX=true python3 server.py"
  exit 1
fi

exit 0
