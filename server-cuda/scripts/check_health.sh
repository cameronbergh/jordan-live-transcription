#!/bin/bash
#
# check_health.sh — Verify the CUDA server is running and healthy.
# Run from the server-cuda directory.
set -e

HOST="${HOST:-localhost}"
PORT="${PORT:-8765}"
TIMEOUT=5

fail() {
  echo "FAIL: $1"
  exit 1
}

pass() {
  echo "PASS: $1"
}

echo "Checking Jordan CUDA Transcription Server..."
echo "  Host: $HOST"
echo "  Port: $PORT"
echo ""

# Check root endpoint
STATUS=$(curl -s --max-time "$TIMEOUT" "http://${HOST}:${PORT}/" 2>/dev/null || echo "")
if echo "$STATUS" | grep -q "jordan-transcription"; then
  pass "Root endpoint returns correct service name"
else
  fail "Root endpoint unexpected response: $STATUS"
fi

# Check /health
STATUS=$(curl -s --max-time "$TIMEOUT" "http://${HOST}:${PORT}/health" 2>/dev/null || echo "")
if echo "$STATUS" | grep -q '"status"'; then
  pass "Health endpoint responding"
else
  fail "Health endpoint unexpected response: $STATUS"
fi

# Check /v1/status
STATUS=$(curl -s --max-time "$TIMEOUT" "http://${HOST}:${PORT}/v1/status" 2>/dev/null || echo "")
if echo "$STATUS" | grep -q '"engine"'; then
  ENGINE=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('engine','?'))" 2>/dev/null || echo "?")
  ADAPTER=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('adapter','?'))" 2>/dev/null || echo "?")
  MOCK=$(echo "$STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('mock','?'))" 2>/dev/null || echo "?")
  pass "Status endpoint: engine=$ENGINE adapter=$ADAPTER mock=$MOCK"
else
  fail "Status endpoint unexpected response: $STATUS"
fi

echo ""
echo "All checks passed."
