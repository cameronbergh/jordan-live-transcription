#!/bin/bash
set -e
cd "$(dirname "$0")/.."

echo "Deploying WhisperLive..."
if [ ! -d "venv-whisperlive" ]; then
    python3 -m venv venv-whisperlive
fi

source venv-whisperlive/bin/activate
pip install -r ../WhisperLive/requirements/server.txt

echo "WhisperLive deployed successfully."
