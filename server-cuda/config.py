import os
from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8765")))
    log_transcripts: bool = field(
        default_factory=lambda: os.getenv("LOG_TRANSCRIPTS", "false").lower() == "true"
    )
    parakeet_model: str = field(
        default_factory=lambda: os.getenv("PARAKEET_MODEL", "nvidia/parakeet-qn-params")
    )
    gpu_device_id: int = field(
        default_factory=lambda: int(os.getenv("GPU_DEVICE_ID", "0"))
    )
    vad_model: str = field(
        default_factory=lambda: os.getenv("VAD_MODEL", "nvidia/parakeet-vad")
    )
    audio_chunk_ms: int = field(
        default_factory=lambda: int(os.getenv("CHUNK_MS", "100"))
    )
    inference_batch_size: int = field(
        default_factory=lambda: int(os.getenv("BATCH_SIZE", "1"))
    )
    enable_mock_parakeet: bool = field(
        default_factory=lambda: os.getenv("MOCK_PARAKEET", "true").lower() == "true"
    )
    server_hostname: str = field(
        default_factory=lambda: os.getenv("SERVER_HOSTNAME", "cameron-ms-7b17")
    )
    vllm_host: str = field(
        default_factory=lambda: os.getenv("VLLM_HOST", "")
    )
    vllm_port: int = field(
        default_factory=lambda: int(os.getenv("VLLM_PORT", "8000"))
    )
    voxtral_model: str = field(
        default_factory=lambda: os.getenv(
            "VOXTRAL_MODEL", "mistralai/Voxtral-Mini-4B-Realtime-2602"
        )
    )


DEFAULT_AUDIO_CONFIG = {
    "encoding": "pcm_s16le",
    "sampleRate": 16000,
    "channels": 1,
    "chunkMs": 100,
}


config = ServerConfig()
