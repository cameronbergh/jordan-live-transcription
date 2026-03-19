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
from mlx_adapter import create_mlx_adapter, MLXAdapter
from session import TranscriptionSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("mlx_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MLX transcription server...")
    adapter = create_mlx_adapter()
    try:
        await adapter.initialize(config.mlx_model)
        logger.info(f"MLX adapter initialized: {type(adapter).__name__}")
    except Exception as e:
        logger.error(f"Failed to initialize MLX adapter: {e}")
        logger.warning("Falling back to mock adapter for development/testing")
        from mlx_adapter import MockMLXAdapter

        adapter = MockMLXAdapter()
        await adapter.initialize(config.mlx_model)

    try:
        await adapter.warm_up()
        logger.info("MLX warm-up complete")
    except Exception as e:
        logger.warning(f"Warm-up failed (non-fatal): {e}")

    app.state.adapter = adapter
    logger.info(f"Server ready on {config.host}:{config.port}")
    yield
    logger.info("Shutting down server...")
    await adapter.shutdown()
    logger.info("Server shutdown complete")


app = FastAPI(title="MLX Transcription Server", lifespan=lifespan)


@app.get("/")
async def root():
    return JSONResponse({"service": "mlx-transcription", "status": "running"})


@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy", "engine": "mlx"})


@app.get("/v1/status")
async def status():
    adapter_type = type(app.state.adapter).__name__
    return JSONResponse(
        {
            "engine": "mlx",
            "adapter": adapter_type,
            "model": config.mlx_model,
            "mock": adapter_type == "MockMLXAdapter",
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

        adapter = app.state.adapter
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

        transcript_task.cancel()
        try:
            await transcript_task
        except asyncio.CancelledError:
            pass

    except Exception as e:
        logger.error(f"[{session_id}] WebSocket error: {e}")
    finally:
        await session.stop()
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
