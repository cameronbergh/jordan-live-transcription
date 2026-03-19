import asyncio
import uuid
from enum import Enum, auto
from typing import Optional, Callable, Awaitable

from audio_buffer import AudioBuffer
from parakeet_adapter import TranscriptResult
from protocol import (
    SessionStartMessage,
    parse_message,
    serialize_message,
    build_session_started,
    build_status,
    build_error,
    build_partial_transcript,
    build_final_transcript,
    build_pong,
    is_binary_audio_frame,
)
from config import config


class SessionState(Enum):
    CONNECTING = auto()
    READY = auto()
    LISTENING = auto()
    PROCESSING = auto()
    CLOSED = auto()


class TranscriptionSession:
    def __init__(
        self,
        websocket,
        session_id: Optional[str] = None,
        send_callback: Optional[Callable[[str], Awaitable[None]]] = None,
        connected_clients_getter: Optional[Callable[[], int]] = None,
    ):
        self.websocket = websocket
        self.session_id = session_id or str(uuid.uuid4())
        self.state = SessionState.CONNECTING
        self.audio_buffer = AudioBuffer(sample_rate=16000)
        self.audio_config: dict = {}
        self.transcription_config: dict = {}
        self._send_callback = send_callback or websocket.send_text
        self._is_running = False
        self._is_session_started = False
        self._audio_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._segment_counter = 0
        self._session_start_ms: int = 0
        self.engine: str = "parakeet"
        self._connected_clients_getter = connected_clients_getter

    async def send_json(self, obj) -> None:
        await self._send_callback(serialize_message(obj))

    async def send_status(self, state: SessionState, message: str = "") -> None:
        self.state = state
        await self.send_json(build_status(state.name.lower(), message))

    async def send_error(self, code: str, message: str, fatal: bool = False) -> None:
        await self.send_json(build_error(code, message, fatal))

    async def send_session_started(self, connected_clients: int = 0) -> None:
        self._is_session_started = True
        msg = build_session_started(
            self.session_id, config.server_hostname, engine=self.engine,
            connected_clients=connected_clients,
        )
        await self.send_json(msg)

    async def handle_message(self, data: str | bytes) -> bool:
        if isinstance(data, bytes) and len(data) > 0:
            return await self._handle_audio_frame(data)

        msg = parse_message(data)
        if msg is None:
            await self.send_error(
                "invalid_message", "Could not parse message", fatal=False
            )
            return True

        msg_type = msg.get("type", "")

        if msg_type == "session.start":
            await self._handle_session_start(msg)
        elif msg_type == "session.stop":
            await self._handle_session_stop()
            return False
        elif msg_type == "ping":
            timestamp = msg.get("timestamp", 0)
            await self.send_json(build_pong(timestamp))
        else:
            await self.send_error(
                "unknown_message_type",
                f"Unknown message type: {msg_type}",
                fatal=False,
            )

        return True

    async def _handle_session_start(self, msg: dict) -> None:
        self.session_id = msg.get("sessionId", self.session_id)
        self.audio_config = msg.get("audio", {})
        self.transcription_config = msg.get("transcription", {})
        self.engine = self.transcription_config.get("engine", "parakeet")
        count = self._connected_clients_getter() if self._connected_clients_getter else 0
        await self.send_session_started(connected_clients=count)
        await self.send_status(SessionState.LISTENING, "Listening for audio")
        self._is_running = True
        self._session_start_ms = int(asyncio.get_event_loop().time() * 1000)

    async def _handle_audio_frame(self, data: bytes) -> bool:
        if not self._is_session_started:
            await self.send_error(
                "session_not_started",
                "Received audio before session.start",
                fatal=False,
            )
            return True

        if self.state != SessionState.LISTENING:
            await self.send_status(SessionState.LISTENING, "Receiving audio")

        try:
            self._audio_queue.put_nowait(data)
        except asyncio.QueueFull:
            await self.send_status(
                SessionState.PROCESSING, "Buffer full, dropping oldest audio"
            )
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(data)
            except asyncio.QueueEmpty:
                pass

        return True

    async def _handle_session_stop(self) -> None:
        self._is_running = False
        await self.send_status(SessionState.READY, "Session ended")

    async def start(self) -> None:
        self._is_running = True
        await self.send_status(SessionState.READY, "Ready to receive audio")

    async def stop(self) -> None:
        self._is_running = False
        self.state = SessionState.CLOSED

    async def emit_transcript_result(self, result: TranscriptResult) -> None:
        if result.is_final:
            await self.send_json(
                build_final_transcript(
                    segment_id=result.segment_id,
                    start_ms=result.start_ms,
                    end_ms=result.end_ms,
                    text=result.text,
                )
            )
        else:
            await self.send_json(
                build_partial_transcript(
                    segment_id=result.segment_id,
                    start_ms=result.start_ms,
                    end_ms=result.end_ms,
                    text=result.text,
                )
            )

    @property
    def is_running(self) -> bool:
        return self._is_running

    def get_audio_queue(self) -> asyncio.Queue:
        return self._audio_queue
