#!/usr/bin/env python3
import asyncio
import json
import sys
import time
import numpy as np

try:
    import websockets
except ImportError:
    print("websockets not installed. Run: pip install websockets")
    sys.exit(1)


SAMPLE_TEXT = [
    "Hello, how are you doing today?",
    "I'm just testing the MLX transcription system.",
    "This is a live demo running on Apple Silicon.",
]


async def test_client():
    uri = "ws://localhost:8765/v1/transcription/stream"
    print(f"Connecting to {uri}")

    async with websockets.connect(uri) as ws:
        print("Connected. Sending session.start...")

        session_start = {
            "type": "session.start",
            "sessionId": "test-session-001",
            "audio": {
                "encoding": "pcm_s16le",
                "sampleRate": 16000,
                "channels": 1,
                "chunkMs": 100,
            },
            "transcription": {
                "partials": True,
                "language": None,
            },
            "client": {
                "platform": "ios",
                "appVersion": "0.1.0",
            },
        }
        await ws.send(json.dumps(session_start))
        print("session.start sent.")

        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                msg_type = data.get("type")
                print(f"Received: {msg_type} - {data}")

                if msg_type == "session.started":
                    print("Session started! Sending simulated audio chunks...")
                    for i in range(20):
                        chunk_duration_ms = 100
                        chunk_size = int(16000 * chunk_duration_ms / 1000)
                        audio_chunk = (
                            (np.random.randint(-1000, 1000, chunk_size) * 10)
                            .astype(np.int16)
                            .tobytes()
                        )
                        await ws.send(audio_chunk)
                        await asyncio.sleep(0.1)

                    stop_msg = {"type": "session.stop"}
                    await ws.send(json.dumps(stop_msg))
                    print("session.stop sent.")

                elif msg_type == "transcript.final":
                    print(f"Final transcript: {data.get('text')}")

                elif msg_type in ("status", "error", "pong"):
                    pass

            except asyncio.TimeoutError:
                print("No message received (timeout). Ending test.")
                break

    print("Test complete.")


if __name__ == "__main__":
    asyncio.run(test_client())
