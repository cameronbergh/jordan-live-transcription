import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Callable, Awaitable, Optional
import time

import numpy as np

from config import config


@dataclass
class TranscriptResult:
    segment_id: str
    text: str
    start_ms: int
    end_ms: int
    is_final: bool = False


TranscriptCallback = Callable[[TranscriptResult], Awaitable[None]]


class MLXAdapter(ABC):
    @abstractmethod
    async def initialize(self, model_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def warm_up(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: TranscriptCallback,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        raise NotImplementedError


class MockMLXAdapter(MLXAdapter):
    SAMPLE_PHRASES = [
        "Hello, how are you doing today?",
        "I'm just testing the MLX transcription system.",
        "This is a live demo running on Apple Silicon.",
        "The quick brown fox jumps over the lazy dog.",
        "MLX Whisper is running efficiently on this Mac.",
        "We're streaming audio in real time.",
        "This transcript should appear word by word.",
        "Everything seems to be working correctly.",
    ]

    def __init__(self):
        self._initialized = False
        self._sample_rate = 16000
        self._segment_counter = 0

    async def initialize(
        self, model_name: str = "mlx-community/whisper-large-v3-mlx"
    ) -> None:
        await asyncio.sleep(0.1)
        self._initialized = True

    async def warm_up(self) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")
        await asyncio.sleep(0.05)

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: TranscriptCallback,
    ) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")

        buffer = b""
        chunk_count = 0
        self._segment_counter += 1
        segment_id = f"seg-{self._segment_counter:04d}"
        phrase_idx = 0
        current_phrase = self.SAMPLE_PHRASES[phrase_idx % len(self.SAMPLE_PHRASES)]
        words = current_phrase.split()
        word_index = 0
        start_ms = int(time.time() * 1000)

        async for chunk in audio_chunks:
            buffer += chunk
            chunk_count += 1

            if len(buffer) >= 1600:
                await asyncio.sleep(0.08)
                if word_index < len(words):
                    word = words[word_index]
                    partial_text = " ".join(words[: word_index + 1])
                    end_ms = int(time.time() * 1000)
                    result = TranscriptResult(
                        segment_id=segment_id,
                        text=partial_text,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        is_final=False,
                    )
                    await transcript_callback(result)
                    word_index += 1

                if word_index >= len(words) and chunk_count % 8 == 0:
                    phrase_idx += 1
                    current_phrase = self.SAMPLE_PHRASES[
                        phrase_idx % len(self.SAMPLE_PHRASES)
                    ]
                    words = current_phrase.split()
                    word_index = 0
                    self._segment_counter += 1
                    segment_id = f"seg-{self._segment_counter:04d}"
                    final_result = TranscriptResult(
                        segment_id=segment_id,
                        text=current_phrase,
                        start_ms=start_ms,
                        end_ms=int(time.time() * 1000),
                        is_final=True,
                    )
                    await transcript_callback(final_result)
                    start_ms = int(time.time() * 1000)
                    self._segment_counter += 1
                    segment_id = f"seg-{self._segment_counter:04d}"

                buffer = buffer[len(buffer) // 2 :]

    async def shutdown(self) -> None:
        self._initialized = False


class RealMLXAdapter(MLXAdapter):
    def __init__(self):
        self._initialized = False
        self._model = None
        self._sample_rate = 16000
        self._model_name: Optional[str] = None

    async def initialize(
        self, model_name: str = "mlx-community/whisper-base-mlx"
    ) -> None:
        try:
            import mlx.core as mx
            from mlx_audio.mlx_whisper import load_whisper_model
        except ImportError as e:
            raise RuntimeError(
                f"mlx-audio not installed. Install with: pip install mlx-audio\n"
                f"Or follow setup guide: MLX_INTEGRATION.md\n"
                f"Import error: {e}"
            )

        self._model_name = model_name
        mx.set_default_device(mx.gpu)
        self._model = load_whisper_model(model_name)
        self._initialized = True

    async def warm_up(self) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")

        import mlx.core as mx
        import numpy as np

        dummy_audio = np.random.randn(self._sample_rate).astype(np.float32) * 0.01
        audio_mlx = mx.array(dummy_audio)

        from mlx_audio.mlx_whisper import transcribe

        _ = transcribe(self._model, audio_mlx)

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: TranscriptCallback,
    ) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")

        import mlx.core as mx
        from mlx_audio.mlx_whisper import transcribe

        buffer = b""
        min_samples = int(0.5 * self._sample_rate)
        overlap_samples = int(0.1 * self._sample_rate)
        segment_counter = 0
        pending_text = ""
        segment_start_ms = 0

        async for chunk in audio_chunks:
            buffer += chunk

            if len(buffer) < 2:
                continue

            samples = np.frombuffer(buffer, dtype=np.int16)
            if len(samples) < min_samples:
                continue

            audio_mlx = mx.array(samples.astype(np.float32) / 32768.0)
            result_text = transcribe(self._model, audio_mlx)
            text = (
                result_text.get("text", "").strip()
                if isinstance(result_text, dict)
                else str(result_text).strip()
            )

            if text:
                segment_counter += 1
                now_ms = int(time.time() * 1000)
                if segment_start_ms == 0:
                    segment_start_ms = now_ms - int(
                        len(samples) / self._sample_rate * 1000
                    )

                result = TranscriptResult(
                    segment_id=f"seg-{session_id}-{segment_counter:04d}",
                    text=text,
                    start_ms=segment_start_ms,
                    end_ms=now_ms,
                    is_final=False,
                )
                await transcript_callback(result)
                pending_text = text
                segment_start_ms = now_ms

            kept_samples = max(0, len(samples) - overlap_samples)
            if kept_samples > 0 and len(buffer) >= 2:
                buffer = buffer[-kept_samples * 2 :]
            else:
                buffer = b""

            if segment_counter > 0 and segment_counter % 5 == 0:
                final_result = TranscriptResult(
                    segment_id=f"seg-{session_id}-{segment_counter:04d}",
                    text=pending_text,
                    start_ms=segment_start_ms
                    - int(0.5 * self._sample_rate / self._sample_rate * 1000),
                    end_ms=segment_start_ms,
                    is_final=True,
                )
                await transcript_callback(final_result)

    async def shutdown(self) -> None:
        self._initialized = False
        self._model = None
        try:
            import mlx.core as mx

            mx.metal.reset_peak_memory()
        except ImportError:
            pass


def create_mlx_adapter() -> MLXAdapter:
    if config.enable_mock_mlx:
        return MockMLXAdapter()
    return RealMLXAdapter()
