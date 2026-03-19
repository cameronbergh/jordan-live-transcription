import os
from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8765")))
    log_transcripts: bool = field(
        default_factory=lambda: os.getenv("LOG_TRANSCRIPTS", "false").lower() == "true"
    )
    mlx_model: str = field(
        default_factory=lambda: os.getenv(
            "MLX_MODEL", "mlx-community/whisper-large-v3-mlx"
        )
    )
    mlx_adapter_type: str = field(
        default_factory=lambda: os.getenv("MLX_ADAPTER_TYPE", "mock")
    )
    audio_chunk_ms: int = field(
        default_factory=lambda: int(os.getenv("CHUNK_MS", "100"))
    )
    enable_mock_mlx: bool = field(
        default_factory=lambda: os.getenv("MOCK_MLX", "true").lower() == "true"
    )
    server_hostname: str = field(
        default_factory=lambda: os.getenv("SERVER_HOSTNAME", "mlx-server")
    )


DEFAULT_AUDIO_CONFIG = {
    "encoding": "pcm_s16le",
    "sampleRate": 16000,
    "channels": 1,
    "chunkMs": 100,
}


config = ServerConfig()
