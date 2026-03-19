import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MessageType(str, Enum):
    SESSION_START = "session.start"
    SESSION_STARTED = "session.started"
    SESSION_STOP = "session.stop"
    AUDIO_APPEND = "audio.append"
    TRANSCRIPT_PARTIAL = "transcript.partial"
    TRANSCRIPT_FINAL = "transcript.final"
    STATUS = "status"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    SERVER_INFO = "server.info"


@dataclass
class SessionStartMessage:
    type: str = "session.start"
    sessionId: str = ""
    audio: dict = field(
        default_factory=lambda: {
            "encoding": "pcm_s16le",
            "sampleRate": 16000,
            "channels": 1,
            "chunkMs": 100,
        }
    )
    transcription: dict = field(
        default_factory=lambda: {
            "partials": True,
            "language": None,
        }
    )
    client: dict = field(
        default_factory=lambda: {
            "platform": "ios",
            "appVersion": "0.1.0",
        }
    )


@dataclass
class SessionStartedMessage:
    type: str = "session.started"
    sessionId: str = ""
    server: dict = field(
        default_factory=lambda: {
            "engine": "parakeet",
            "host": "cameron-ms-7b17",
        }
    )


@dataclass
class TranscriptPartialMessage:
    type: str = "transcript.partial"
    segmentId: str = ""
    startMs: int = 0
    endMs: int = 0
    text: str = ""
    isFinal: bool = False


@dataclass
class TranscriptFinalMessage:
    type: str = "transcript.final"
    segmentId: str = ""
    startMs: int = 0
    endMs: int = 0
    text: str = ""
    isFinal: bool = True


@dataclass
class StatusMessage:
    type: str = "status"
    state: str = "connecting"
    message: str = ""


@dataclass
class ErrorMessage:
    type: str = "error"
    code: str = ""
    message: str = ""
    fatal: bool = False


@dataclass
class PongMessage:
    type: str = "pong"
    timestamp: int = 0


@dataclass
class ServerInfoMessage:
    type: str = "server.info"
    connectedClients: int = 0
    engines: list = field(default_factory=list)


def serialize_message(obj: Any) -> str:
    if hasattr(obj, "__dataclass_fields__"):
        return json.dumps(_dataclass_to_dict(obj), ensure_ascii=False)
    return json.dumps(obj, ensure_ascii=False)


def _dataclass_to_dict(obj: Any) -> dict:
    result = {}
    for name, field in obj.__dataclass_fields__.items():
        value = getattr(obj, name)
        if isinstance(value, Enum):
            result[name] = value.value
        elif isinstance(value, dict):
            result[name] = value
        else:
            result[name] = value
    return result


def parse_message(data: str | bytes) -> Optional[dict]:
    try:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def is_binary_audio_frame(data: str | bytes) -> bool:
    return isinstance(data, bytes) and len(data) > 0


def build_session_started(
    session_id: str, server_host: str, engine: str = "parakeet",
    connected_clients: int = 0,
) -> SessionStartedMessage:
    return SessionStartedMessage(
        sessionId=session_id,
        server={"engine": engine, "host": server_host, "connectedClients": connected_clients},
    )


def build_status(state: str, message: str = "") -> StatusMessage:
    return StatusMessage(state=state, message=message)


def build_error(code: str, message: str, fatal: bool = False) -> ErrorMessage:
    return ErrorMessage(code=code, message=message, fatal=fatal)


def build_partial_transcript(
    segment_id: str, start_ms: int, end_ms: int, text: str
) -> TranscriptPartialMessage:
    return TranscriptPartialMessage(
        segmentId=segment_id,
        startMs=start_ms,
        endMs=end_ms,
        text=text,
        isFinal=False,
    )


def build_final_transcript(
    segment_id: str, start_ms: int, end_ms: int, text: str
) -> TranscriptFinalMessage:
    return TranscriptFinalMessage(
        segmentId=segment_id,
        startMs=start_ms,
        endMs=end_ms,
        text=text,
        isFinal=True,
    )


def build_pong(timestamp: int) -> PongMessage:
    return PongMessage(timestamp=timestamp)


def build_server_info(connected_clients: int, engines: list[str]) -> ServerInfoMessage:
    return ServerInfoMessage(connectedClients=connected_clients, engines=engines)
