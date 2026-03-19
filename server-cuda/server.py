import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse

from config import config
from parakeet_adapter import create_parakeet_adapter, TranscriptionAdapter

from session import TranscriptionSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("jordan_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Jordan transcription server...")
    adapters: dict[str, TranscriptionAdapter] = {}

    parakeet = create_parakeet_adapter()
    try:
        await parakeet.initialize(config.parakeet_model)
        logger.info(f"Parakeet adapter initialized: {type(parakeet).__name__}")
    except Exception as e:
        logger.error(f"Failed to initialize Parakeet adapter: {e}")
        logger.warning("Falling back to mock adapter for development/testing")
        from parakeet_adapter import MockParakeetAdapter
        parakeet = MockParakeetAdapter()
        await parakeet.initialize(config.parakeet_model)

    try:
        await parakeet.warm_up()
        logger.info("Parakeet warm-up complete")
    except Exception as e:
        logger.warning(f"Parakeet warm-up failed (non-fatal): {e}")

    adapters["parakeet"] = parakeet

    try:
        from whisperlive_adapter import create_whisperlive_adapter
        whisperlive = create_whisperlive_adapter()
        if whisperlive is not None:
            await whisperlive.initialize(config.whisper_model)
            adapters["whisperlive"] = whisperlive
            logger.info(f"WhisperLive adapter initialized (model={config.whisper_model})")
        else:
            logger.info("WhisperLive adapter skipped (WHISPERLIVE_HOST not set)")
    except Exception as e:
        logger.warning(f"Failed to initialize WhisperLive adapter: {e}")

    app.state.adapters = adapters
    logger.info(
        f"Server ready on {config.host}:{config.port} — "
        f"engines: {list(adapters.keys())}"
    )
    yield
    logger.info("Shutting down server...")
    for name, adapter in adapters.items():
        try:
            await adapter.shutdown()
            logger.info(f"{name} adapter shut down")
        except Exception as e:
            logger.warning(f"{name} adapter shutdown error: {e}")
    logger.info("Server shutdown complete")


app = FastAPI(title="Jordan Transcription Server", lifespan=lifespan)


@app.get("/")
async def root():
    return JSONResponse({"service": "jordan-transcription", "status": "running"})


@app.get("/health")
async def health():
    engines = list(app.state.adapters.keys())
    return JSONResponse({"status": "healthy", "engines": engines})


@app.get("/v1/status")
async def status():
    engine_info = {}
    for name, adapter in app.state.adapters.items():
        engine_info[name] = {
            "adapter": type(adapter).__name__,
            "mock": type(adapter).__name__ == "MockParakeetAdapter",
        }
    return JSONResponse(
        {
            "engines": engine_info,
            "default_engine": "parakeet",
            "model": config.parakeet_model,
            "gpu_device": config.gpu_device_id,
        }
    )


@app.websocket("/v1/transcription/stream")
async def transcription_websocket(websocket: WebSocket):
    await websocket.accept()
    session_id = str(int(time.time() * 1000))

    async def send_text(text: str):
        await websocket.send_text(text)

    session = TranscriptionSession(
        websocket=websocket,
        session_id=session_id,
        send_callback=send_text,
    )

    logger.info(f"[{session_id}] New WebSocket connection")

    try:
        await session.start()

        # Wait for session.start message to know which engine to use
        while session.is_running:
            try:
                data = await websocket.receive()
                if data["type"] == "websocket.disconnect":
                    return
                msg_data = data.get("text") or data.get("bytes")
                if msg_data is None:
                    continue
                if isinstance(msg_data, str):
                    keep_open = await session.handle_message(msg_data)
                    if not keep_open:
                        return
                    # Once session.start is handled, engine is set
                    if session._is_session_started:
                        break
                elif isinstance(msg_data, bytes):
                    keep_open = await session.handle_message(msg_data)
                    if not keep_open:
                        return
            except WebSocketDisconnect:
                logger.info(f"[{session_id}] Client disconnected before session.start")
                return

        engine_name = session.engine
        adapters = app.state.adapters
        adapter = adapters.get(engine_name)

        if adapter is None:
            available = list(adapters.keys())
            await session.send_error(
                "unknown_engine",
                f"Engine '{engine_name}' not available. Available: {available}",
                fatal=True,
            )
            return

        logger.info(f"[{session_id}] Using engine: {engine_name}")

        audio_queue = session.get_audio_queue()

        async def audio_chunks():
            while session.is_running:
                try:
                    chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
                    yield chunk
                except asyncio.TimeoutError:
                    continue

        async def transcript_callback(result):
            await session.emit_transcript_result(result)

        transcript_task = asyncio.create_task(
            adapter.transcribe_stream(
                audio_chunks=audio_chunks(),
                session_id=session_id,
                transcript_callback=transcript_callback,
            )
        )

        while session.is_running:
            try:
                data = await websocket.receive()
                if data["type"] == "websocket.disconnect":
                    break
                msg_data = data.get("text") or data.get("bytes")
                if msg_data is None:
                    continue
                if isinstance(msg_data, str):
                    keep_open = await session.handle_message(msg_data)
                    if not keep_open:
                        break
                elif isinstance(msg_data, bytes):
                    keep_open = await session.handle_message(msg_data)
                    if not keep_open:
                        break
            except WebSocketDisconnect:
                logger.info(f"[{session_id}] Client disconnected")
                break
            except Exception as e:
                logger.error(f"[{session_id}] Error handling message: {e}")
                await session.send_error("server_error", str(e), fatal=False)

        try:
            await asyncio.wait_for(transcript_task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(f"[{session_id}] Transcript task timed out, cancelling")
            transcript_task.cancel()
            try:
                await transcript_task
            except asyncio.CancelledError:
                pass
        except asyncio.CancelledError:
            pass

    except Exception as e:
        logger.error(f"[{session_id}] WebSocket error: {e}")
    finally:
        await session.stop()
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"[{session_id}] Session closed")


def main():
    uvicorn.run(
        "server:app",
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
