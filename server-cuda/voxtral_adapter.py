import asyncio
import base64
import json
import logging
import time
from typing import AsyncIterator, Optional

import websockets

from config import config
from parakeet_adapter import TranscriptionAdapter, TranscriptResult, TranscriptCallback

logger = logging.getLogger("voxtral_adapter")


class VoxtralAdapter(TranscriptionAdapter):
    """Streams audio to a local vLLM instance serving Voxtral Realtime for GPU-local transcription."""

    def __init__(self):
        self._initialized = False
        self._model_name: str = ""
        self._vllm_url: str = ""
        self._sample_rate = 16000

    async def initialize(self, model_name: str = "") -> None:
        if not config.vllm_host:
            raise RuntimeError(
                "VLLM_HOST not set. VoxtralAdapter requires a running vLLM instance.\n"
                "Start vLLM with: vllm serve mistralai/Voxtral-Mini-4B-Realtime-2602 --enforce-eager"
            )

        self._model_name = model_name or config.voxtral_model
        self._vllm_url = f"ws://{config.vllm_host}:{config.vllm_port}/v1/realtime"
        self._initialized = True
        logger.info(
            f"VoxtralAdapter initialized (model={self._model_name}, "
            f"vllm={self._vllm_url})"
        )

    async def warm_up(self) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")
        try:
            async with websockets.connect(self._vllm_url) as ws:
                response = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
                if response.get("type") == "session.created":
                    logger.info(
                        f"VoxtralAdapter warm-up OK — vLLM reachable at {self._vllm_url}"
                    )
                else:
                    logger.warning(f"Unexpected warm-up response: {response}")
        except Exception as e:
            logger.warning(f"VoxtralAdapter warm-up probe failed (non-fatal): {e}")

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: TranscriptCallback,
    ) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")

        accumulated_text = ""
        segment_counter = 0
        segment_start_ms = int(time.time() * 1000)
        done_event = asyncio.Event()
        error_holder: list[str] = []

        try:
            async with websockets.connect(self._vllm_url) as ws:
                # 1. Wait for session.created
                response = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
                if response.get("type") != "session.created":
                    logger.error(f"[{session_id}] Expected session.created, got: {response}")
                    return
                logger.info(f"[{session_id}] vLLM realtime session created")

                # 2. Send session.update with model
                await ws.send(json.dumps({
                    "type": "session.update",
                    "model": self._model_name,
                }))

                # 3. Initial commit to signal ready
                await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

                # 4. Receive loop (runs concurrently with send loop)
                async def receive_loop():
                    nonlocal accumulated_text, segment_counter
                    try:
                        while not done_event.is_set():
                            try:
                                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            except asyncio.TimeoutError:
                                continue
                            msg = json.loads(raw)
                            msg_type = msg.get("type", "")

                            if msg_type == "transcription.delta":
                                accumulated_text += msg.get("delta", "")
                                segment_counter += 1
                                now_ms = int(time.time() * 1000)
                                result = TranscriptResult(
                                    segment_id=f"vox-{session_id}-{segment_counter:04d}",
                                    text=accumulated_text,
                                    start_ms=segment_start_ms,
                                    end_ms=now_ms,
                                    is_final=False,
                                )
                                await transcript_callback(result)

                            elif msg_type == "transcription.done":
                                final_text = msg.get("text", accumulated_text)
                                if final_text:
                                    segment_counter += 1
                                    now_ms = int(time.time() * 1000)
                                    result = TranscriptResult(
                                        segment_id=f"vox-{session_id}-{segment_counter:04d}",
                                        text=final_text,
                                        start_ms=segment_start_ms,
                                        end_ms=now_ms,
                                        is_final=True,
                                    )
                                    await transcript_callback(result)
                                done_event.set()
                                return

                            elif msg_type == "error":
                                err = msg.get("error", "Unknown vLLM error")
                                logger.error(f"[{session_id}] vLLM error: {err}")
                                error_holder.append(str(err))
                                done_event.set()
                                return

                    except websockets.exceptions.ConnectionClosed:
                        logger.info(f"[{session_id}] vLLM WebSocket closed")
                        done_event.set()

                recv_task = asyncio.create_task(receive_loop())

                # 5. Send loop: forward audio chunks as base64
                try:
                    async for chunk in audio_chunks:
                        if done_event.is_set():
                            break
                        b64 = base64.b64encode(chunk).decode("ascii")
                        await ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": b64,
                        }))
                except asyncio.CancelledError:
                    pass

                # 6. Signal end of audio
                if not done_event.is_set():
                    try:
                        await ws.send(json.dumps({
                            "type": "input_audio_buffer.commit",
                            "final": True,
                        }))
                    except websockets.exceptions.ConnectionClosed:
                        pass

                # 7. Wait for receive loop to finish
                try:
                    await asyncio.wait_for(recv_task, timeout=15.0)
                except asyncio.TimeoutError:
                    logger.warning(f"[{session_id}] vLLM receive loop timed out")
                    recv_task.cancel()
                    try:
                        await recv_task
                    except asyncio.CancelledError:
                        pass

                    # Emit what we have as final
                    if accumulated_text:
                        segment_counter += 1
                        now_ms = int(time.time() * 1000)
                        result = TranscriptResult(
                            segment_id=f"vox-{session_id}-{segment_counter:04d}",
                            text=accumulated_text,
                            start_ms=segment_start_ms,
                            end_ms=now_ms,
                            is_final=True,
                        )
                        await transcript_callback(result)

        except asyncio.CancelledError:
            logger.info(f"[{session_id}] Voxtral stream cancelled")
            if accumulated_text:
                segment_counter += 1
                now_ms = int(time.time() * 1000)
                result = TranscriptResult(
                    segment_id=f"vox-{session_id}-{segment_counter:04d}",
                    text=accumulated_text,
                    start_ms=segment_start_ms,
                    end_ms=now_ms,
                    is_final=True,
                )
                await transcript_callback(result)
            raise
        except Exception as e:
            logger.error(
                f"[{session_id}] Voxtral transcribe_stream error: {e}",
                exc_info=True,
            )

    async def shutdown(self) -> None:
        self._initialized = False
        logger.info("VoxtralAdapter shut down")


def create_voxtral_adapter() -> Optional[VoxtralAdapter]:
    if not config.vllm_host:
        return None
    return VoxtralAdapter()
