import asyncio
import json
import logging
from typing import AsyncGenerator, Callable, Any

import numpy as np
import websockets
from websockets.exceptions import ConnectionClosed
from parakeet_adapter import TranscriptionAdapter, TranscriptResult

logger = logging.getLogger("whisperlive_adapter")

class WhisperLiveAdapter(TranscriptionAdapter):
    def __init__(self, host="localhost", port=9090):
        self._url = f"ws://{host}:{port}"
        self._model = "large-v3-turbo"

    async def initialize(self, model: str):
        self._model = model

    async def warm_up(self):
        pass

    async def shutdown(self):
        pass

    async def transcribe_stream(
        self,
        audio_chunks: AsyncGenerator[bytes, None],
        session_id: str,
        transcript_callback: Callable[[dict[str, Any]], Any],
    ):
        try:
            async with websockets.connect(self._url) as ws:
                config = {
                    "uid": session_id,
                    "language": "en",
                    "task": "transcribe",
                    "model": self._model,
                    "use_vad": True,
                    "send_last_n_segments": 10,
                    "no_speech_thresh": 0.45,
                    "clip_audio": False,
                    "same_output_threshold": 10,
                    "enable_translation": False,
                    "target_language": "fr"
                }
                await ws.send(json.dumps(config))

                async def receive_loop():
                    try:
                        async for message in ws:
                            data = json.loads(message)
                            if "segments" in data:
                                segments = data["segments"]
                                if not segments:
                                    continue
                                
                                for seg in segments:
                                    is_final = seg.get("completed", False)
                                    # Create a unique but stable ID for this segment's approximate start time
                                    start_ms = int(float(seg.get("start", 0)) * 1000)
                                    segment_id = f"wl-{start_ms}"

                                    await transcript_callback(
                                        TranscriptResult(
                                            segment_id=segment_id,
                                            start_ms=start_ms,
                                            end_ms=int(float(seg.get("end", 0)) * 1000),
                                            text=seg.get("text", "").strip(),
                                            is_final=is_final,
                                        )
                                    )
                    except ConnectionClosed:
                        pass
                    except Exception as e:
                        logger.error(f"[{session_id}] Receive loop error: {e}")

                recv_task = asyncio.create_task(receive_loop())

                try:
                    async for chunk in audio_chunks:
                        if len(chunk) % 2 != 0:
                            chunk = chunk[:-1]
                        raw_data = np.frombuffer(chunk, dtype=np.int16)
                        float_data = raw_data.astype(np.float32) / 32768.0
                        await ws.send(float_data.tobytes())
                finally:
                    await ws.send(b"END_OF_AUDIO")
                    try:
                        await asyncio.wait_for(recv_task, timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                    
        except Exception as e:
            logger.error(f"[{session_id}] WhisperLive transcribe error: {e}")

def create_whisperlive_adapter() -> WhisperLiveAdapter | None:
    from config import config
    host = config.whisperlive_host
    if not host:
        return None
    return WhisperLiveAdapter(host=host, port=config.whisperlive_port)
