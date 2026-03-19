#!/usr/bin/env python3
"""WebSocket test client for the Jordan transcription server.

Streams a 16kHz mono WAV file (or synthetic silence) to the server and
prints transcript events in real time.  Send and receive run concurrently
so partial transcripts appear while audio is still being streamed.
"""
import argparse
import asyncio
import json
import sys
import uuid
import wave
import time
from pathlib import Path
from typing import Optional

import numpy as np

SAMPLE_RATE = 16000
CHUNK_MS = 100
SAMPLES_PER_CHUNK = int(SAMPLE_RATE * CHUNK_MS / 1000)


def generate_silent_pcm(duration_ms: int) -> bytes:
    num_samples = int(SAMPLE_RATE * duration_ms / 1000)
    return np.zeros(num_samples, dtype=np.int16).tobytes()


async def send_json(ws, obj: dict) -> None:
    await ws.send(json.dumps(obj))


async def receiver(ws, done_event: asyncio.Event):
    """Read and print server messages until the connection closes."""
    final_received = False
    close_received = False
    try:
        async for msg in ws:
            if isinstance(msg, str):
                data = json.loads(msg)
                t = data.get("type", "")
                if t == "session.started":
                    print(f"\n[session.started] sessionId={data.get('sessionId')} engine={data.get('server', {}).get('engine')}")
                elif t == "transcript.partial":
                    print(f"  [partial] {data.get('text', '')}")
                elif t == "transcript.final":
                    print(f"\n>>> [FINAL] {data.get('text', '')}")
                    final_received = True
                elif t == "status":
                    state = data.get("state", "")
                    print(f"  [status] state={state} message={data.get('message', '')}")
                    if state in ("ready", "closed"):
                        close_received = True
                elif t == "error":
                    print(f"\n  [ERROR] {data.get('code')}: {data.get('message')}")
                elif t == "pong":
                    print(f"  [pong] timestamp={data.get('timestamp')}")
                else:
                    print(f"  [unknown] {data}")
            elif isinstance(msg, bytes):
                print(f"  [binary] {len(msg)} bytes")

            if final_received and close_received:
                print("\nAll final transcripts and close status received.")
                break
    except Exception as e:
        if "closed" not in str(e).lower():
            print(f"\n[receiver error] {e}")
    finally:
        done_event.set()


async def sender(ws, audio_file: Optional[Path], done_event: asyncio.Event):
    """Send session.start, stream audio, then send session.stop."""
    session_id = str(uuid.uuid4())
    print(f"Session ID: {session_id}")

    await send_json(ws, {
        "type": "session.start",
        "sessionId": session_id,
        "audio": {
            "encoding": "pcm_s16le",
            "sampleRate": SAMPLE_RATE,
            "channels": 1,
            "chunkMs": CHUNK_MS,
        },
        "transcription": {"partials": True, "language": None},
        "client": {"platform": "test", "appVersion": "0.1.0"},
    })

    await asyncio.sleep(0.2)

    if audio_file:
        print(f"Streaming audio from {audio_file}")
        with wave.open(str(audio_file), "rb") as wf:
            if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != SAMPLE_RATE:
                print(f"WARNING: WAV is {wf.getnchannels()}ch, {wf.getsampwidth()*8}bit, {wf.getframerate()}Hz — expected 1ch 16bit {SAMPLE_RATE}Hz")
            total_sent = 0
            while True:
                chunk = wf.readframes(SAMPLES_PER_CHUNK)
                if not chunk:
                    break
                await ws.send(chunk)
                total_sent += len(chunk)
                await asyncio.sleep(CHUNK_MS / 1000 * 0.9)
        print(f"\nFinished sending {total_sent} bytes of audio")
    else:
        print("Streaming 5s of synthetic silence (no file provided)...")
        chunk = generate_silent_pcm(CHUNK_MS)
        for i in range(50):
            await ws.send(chunk)
            await asyncio.sleep(CHUNK_MS / 1000 * 0.9)
        print("\nFinished sending synthetic audio")

    await asyncio.sleep(0.5)

    print("Sending session.stop...")
    await send_json(ws, {"type": "session.stop"})

    try:
        await asyncio.wait_for(done_event.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        print("\nTimed out waiting for server to finish (15s). Closing.")


async def test_session(host: str, port: int, audio_file: Optional[Path] = None):
    import websockets

    uri = f"ws://{host}:{port}/v1/transcription/stream"
    print(f"Connecting to {uri}")

    async with websockets.connect(uri, max_size=10 * 1024 * 1024) as ws:
        done_event = asyncio.Event()

        recv_task = asyncio.create_task(receiver(ws, done_event))
        send_task = asyncio.create_task(sender(ws, audio_file, done_event))

        await asyncio.gather(send_task, recv_task, return_exceptions=True)

    print("\nConnection closed. Test complete.")


def main():
    parser = argparse.ArgumentParser(description="Jordan transcription test client")
    parser.add_argument("--host", default="localhost", help="Server host")
    parser.add_argument("--port", type=int, default=8765, help="Server port")
    parser.add_argument(
        "--audio",
        type=Path,
        default=None,
        help="Path to a 16kHz mono WAV file to stream",
    )
    args = parser.parse_args()

    asyncio.run(test_session(args.host, args.port, args.audio))


if __name__ == "__main__":
    main()
